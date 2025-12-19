from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from typing import Optional, List, Dict
import logging
import requests
import os
import traceback

from app.core.security import decode_access_token
from app.routes.login import oauth2_scheme

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/files", tags=["files"])

# Internal URLs for calling our own FastAPI endpoints
FASTAPI_INTERNAL_URL = os.getenv("FASTAPI_INTERNAL_URL", "http://localhost:8000")


# ===== DATA MODELS =====

class FileInFolder(BaseModel):
    """Represents a file within a folder structure."""
    filename: str
    data: str  # base64 encoded file data
    relative_path: str  # e.g., "subfolder1/subfolder2/file.txt"
    content_type: Optional[str] = "application/octet-stream"


class FolderUploadRequest(BaseModel):
    """Request model for uploading an entire folder."""
    folder_name: str
    files: List[FileInFolder]
    parent_folder_id: Optional[str] = None
    erasure_id: Optional[str] = "MEDIUM"


class FileUploadResult(BaseModel):
    """Result of uploading a single file."""
    filename: str
    relative_path: str
    success: bool
    file_id: Optional[str] = None
    version_id: Optional[str] = None
    file_size: Optional[int] = None
    fragments_stored: Optional[int] = None
    error: Optional[str] = None


class FolderUploadResponse(BaseModel):
    """Response model for folder upload operation."""
    success: bool
    root_folder_id: str
    folder_name: str
    total_files: int
    files_uploaded: int
    files_failed: int
    upload_results: List[FileUploadResult]
    folder_structure: Dict[str, str]  # path -> folder_id mapping
    errors: List[str]


# ===== HELPER FUNCTIONS =====

def get_current_account_from_token(token: str):
    """Get account info from token."""
    try:
        from app.master_node_db import get_master_db
        
        payload = decode_access_token(token)
        if not payload:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        
        account_id = payload.get("sub")
        if not account_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        
        # You can also use your existing master_db here
        return {"account_id": account_id, "username": payload.get("username")}
        
    except Exception as e:
        logger.error(f"Error getting account from token: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def get_current_account(token=Depends(oauth2_scheme)):
    """Get the current authenticated account."""
    token_str = token.credentials if hasattr(token, "credentials") else token
    return get_current_account_from_token(token_str)


def parse_folder_structure(files: List[FileInFolder]) -> List[Dict]:
    """
    Extract folder structure from file paths.
    Returns a list of folder definitions sorted by depth (parents before children).
    """
    folder_paths = set()
    
    # Extract all unique folder paths
    for file_data in files:
        # Split path and remove filename
        path_parts = file_data.relative_path.split('/')
        if len(path_parts) > 1:  # Has folders
            for i in range(len(path_parts) - 1):
                folder_path = '/'.join(path_parts[:i + 1])
                folder_paths.add(folder_path)
    
    # Convert to list of folder definitions
    folders = []
    for path in folder_paths:
        path_parts = path.split('/')
        folders.append({
            'path': path,
            'name': path_parts[-1],
            'parent_path': '/'.join(path_parts[:-1]) if len(path_parts) > 1 else None
        })
    
    # Sort by depth (parents before children)
    folders.sort(key=lambda f: f['path'].count('/'))
    
    return folders


async def create_single_folder_via_endpoint(
    folder_name: str,
    parent_folder_id: Optional[str],
    token: str
) -> str:
    """
    Create a single folder by calling your existing /folders endpoint.
    Returns the created folder_id.
    """
    try:
        # Prepare payload for your existing endpoint
        folder_payload = {
            "name": folder_name,
            "parent_folder_id": parent_folder_id
        }
        
        # Call your existing /folders endpoint
        response = requests.post(
            f"{FASTAPI_INTERNAL_URL}/api/folders",
            json=folder_payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            timeout=30
        )
        
        if response.status_code in [200, 201]:
            result = response.json()
            folder_id = str(result["folder_id"])
            logger.info(f"Created folder '{folder_name}' with ID: {folder_id}")
            return folder_id
        elif response.status_code == 400 and "already exists" in response.text.lower():
            # Folder already exists - try to get its ID
            logger.warning(f"Folder '{folder_name}' already exists")
            # For now, raise error - you could implement logic to fetch existing folder
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Folder '{folder_name}' already exists"
            )
        else:
            logger.error(f"Failed to create folder '{folder_name}': {response.status_code} - {response.text}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create folder: {response.text}"
            )
            
    except HTTPException:
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error creating folder '{folder_name}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create folder: {str(e)}"
        )


async def create_folder_structure_via_endpoints(
    root_folder_name: str,
    files: List[FileInFolder],
    parent_folder_id: Optional[str],
    token: str
) -> Dict[str, str]:
    """
    Create the complete folder structure by calling your existing /folders endpoint.
    Returns a mapping of folder paths to folder IDs.
    """
    folder_map = {}
    
    # Parse folder structure from file paths
    folders = parse_folder_structure(files)
    
    # Create root folder first
    try:
        root_folder_id = await create_single_folder_via_endpoint(
            folder_name=root_folder_name,
            parent_folder_id=parent_folder_id,
            token=token
        )
        folder_map[root_folder_name] = root_folder_id
        logger.info(f"Created root folder: {root_folder_name} ({root_folder_id})")
    except Exception as e:
        logger.error(f"Failed to create root folder '{root_folder_name}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create root folder: {str(e)}"
        )
    
    # Create subfolders in order (parents before children)
    for folder in folders:
        parent_path = folder['parent_path']
        # Parent is either another subfolder or the root
        parent_id = folder_map.get(parent_path, root_folder_id)
        
        try:
            folder_id = await create_single_folder_via_endpoint(
                folder_name=folder['name'],
                parent_folder_id=parent_id,
                token=token
            )
            folder_map[folder['path']] = folder_id
            logger.info(f"Created subfolder: {folder['path']} ({folder_id})")
            
        except HTTPException as e:
            if e.status_code == 409:  # Conflict - folder exists
                logger.warning(f"Folder already exists: {folder['path']}, continuing...")
                # You could implement logic here to fetch the existing folder_id
                # For now, we'll skip it
                continue
            else:
                logger.error(f"Failed to create folder {folder['path']}: {e.detail}")
                # Continue with other folders
                continue
        except Exception as e:
            logger.error(f"Error creating folder {folder['path']}: {e}")
            continue
    
    return folder_map


async def upload_file_via_existing_endpoint(
    filename: str,
    file_data_base64: str,
    folder_id: str,
    erasure_id: str,
    content_type: str,
    token: str
) -> Dict:
    """
    Upload a single file by calling your existing /files/upload endpoint.
    Returns upload result with success status and details.
    """
    try:
        # Prepare the payload for your existing upload endpoint
        upload_payload = {
            "filename": filename,
            "data": file_data_base64,  # Already base64 encoded
            "content_type": content_type,
            "folder_id": folder_id,
            "erasure_id": erasure_id
        }
        
        # Call your existing upload endpoint
        response = requests.post(
            f"{FASTAPI_INTERNAL_URL}/api/files/upload",
            json=upload_payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            timeout=300  # 5 minute timeout for large files
        )
        
        if response.status_code in [200, 201]:
            result = response.json()
            logger.info(f"Successfully uploaded {filename} via existing endpoint")
            return {
                "success": True,
                "file_id": result.get("file_id"),
                "version_id": result.get("version_id"),
                "file_size": result.get("file_size"),
                "fragments_stored": result.get("fragments_stored")
            }
        else:
            logger.error(f"Upload failed for {filename}: {response.status_code} - {response.text}")
            return {
                "success": False,
                "error": f"Upload endpoint returned {response.status_code}: {response.text}"
            }
            
    except requests.exceptions.Timeout:
        logger.error(f"Upload timeout for {filename}")
        return {
            "success": False,
            "error": "Upload timeout - file may be too large"
        }
    except requests.exceptions.RequestException as e:
        logger.error(f"Upload error for {filename}: {e}")
        return {
            "success": False,
            "error": f"Upload request failed: {str(e)}"
        }
    except Exception as e:
        logger.error(f"Unexpected error uploading {filename}: {e}")
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }


# ===== MAIN ENDPOINT =====

@router.post("/upload-folder", response_model=FolderUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_folder(
    upload_data: FolderUploadRequest,
    request: Request,
    current_account = Depends(get_current_account),
    token: str = Depends(oauth2_scheme)
):
    """
    Upload an entire folder with its structure to distributed storage.
    
    This endpoint uses your existing endpoints:
    1. POST /api/folders - Creates each folder in the hierarchy
    2. POST /api/files/upload - Uploads each file with erasure coding
    
    Benefits:
    - Zero code duplication
    - Uses all existing validation and logic
    - Easy to maintain
    """
    try:
        account_id = current_account["account_id"]
        
        # Extract token string for API calls
        token_str = token.credentials if hasattr(token, "credentials") else token
        
        logger.info(f"Starting folder upload: {upload_data.folder_name} with {len(upload_data.files)} files for account {account_id}")
        
        # Step 1: Create folder structure using existing /folders endpoint
        try:
            folder_map = await create_folder_structure_via_endpoints(
                root_folder_name=upload_data.folder_name,
                files=upload_data.files,
                parent_folder_id=upload_data.parent_folder_id,
                token=token_str
            )
            
            root_folder_id = folder_map[upload_data.folder_name]
            logger.info(f"Created folder structure with {len(folder_map)} folders")
            
        except Exception as e:
            logger.error(f"Failed to create folder structure: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create folder structure: {str(e)}"
            )
        
        # Step 2: Upload each file using existing /files/upload endpoint
        upload_results = []
        files_uploaded = 0
        files_failed = 0
        errors = []
        
        for file_data in upload_data.files:
            try:
                # Determine folder ID for this file
                path_parts = file_data.relative_path.split('/')
                if len(path_parts) > 1:
                    # File is in a subfolder
                    folder_path = '/'.join(path_parts[:-1])
                    folder_id = folder_map.get(folder_path, root_folder_id)
                else:
                    # File is in root folder
                    folder_id = root_folder_id
                
                logger.info(f"Uploading {file_data.relative_path} to folder {folder_id}")
                
                # Call existing upload endpoint
                result = await upload_file_via_existing_endpoint(
                    filename=file_data.filename,
                    file_data_base64=file_data.data,  # Pass as-is (already base64)
                    folder_id=folder_id,
                    erasure_id=upload_data.erasure_id,
                    content_type=file_data.content_type,
                    token=token_str
                )
                
                if result["success"]:
                    files_uploaded += 1
                    upload_results.append(FileUploadResult(
                        filename=file_data.filename,
                        relative_path=file_data.relative_path,
                        success=True,
                        file_id=result.get("file_id"),
                        version_id=result.get("version_id"),
                        file_size=result.get("file_size"),
                        fragments_stored=result.get("fragments_stored")
                    ))
                    logger.info(f"✅ Uploaded: {file_data.relative_path}")
                else:
                    files_failed += 1
                    error_msg = result.get("error", "Unknown error")
                    upload_results.append(FileUploadResult(
                        filename=file_data.filename,
                        relative_path=file_data.relative_path,
                        success=False,
                        error=error_msg
                    ))
                    errors.append(f"{file_data.relative_path}: {error_msg}")
                    logger.error(f"❌ Failed: {file_data.relative_path} - {error_msg}")
                    
            except Exception as e:
                files_failed += 1
                error_msg = str(e)
                upload_results.append(FileUploadResult(
                    filename=file_data.filename,
                    relative_path=file_data.relative_path,
                    success=False,
                    error=error_msg
                ))
                errors.append(f"{file_data.relative_path}: {error_msg}")
                logger.error(f"❌ Exception uploading {file_data.relative_path}: {e}")
        
        success = files_failed == 0
        
        logger.info(f"Folder upload completed: {files_uploaded}/{len(upload_data.files)} files uploaded successfully")
        
        return FolderUploadResponse(
            success=success,
            root_folder_id=root_folder_id,
            folder_name=upload_data.folder_name,
            total_files=len(upload_data.files),
            files_uploaded=files_uploaded,
            files_failed=files_failed,
            upload_results=upload_results,
            folder_structure=folder_map,
            errors=errors
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading folder: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error uploading folder: {str(e)}"
        )


# ===== FOLDER BROWSING ENDPOINTS =====
# You might already have these in create_folders.py, so these are optional

@router.get("/folders/root")
async def get_root_folders(current_account = Depends(get_current_account)):
    """
    Get all root-level folders for the current user.
    This just forwards to your existing /folders/list endpoint.
    """
    try:
        # You can call your existing endpoint or duplicate the logic here
        # For now, we'll return a simple message
        return {
            "message": "Use GET /api/folders/list to get folders",
            "account_id": current_account["account_id"]
        }
    except Exception as e:
        logger.error(f"Error getting root folders: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting root folders: {str(e)}"
        )