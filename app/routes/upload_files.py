from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from pydantic import BaseModel
from typing import Optional, List
import logging
import uuid
import base64
import hashlib
import requests
import os
import json

# Remove SQLAlchemy dependencies since we're using master node API
from app.core.security import decode_access_token
from app.routes.login import oauth2_scheme

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/files", tags=["files"])

# Master node configuration
MASTER_NODE_URL = os.getenv("MASTER_NODE_URL", "http://master-node:3000")

class FileUploadRequest(BaseModel):
    filename: str
    data: str  # base64 encoded file data
    content_type: Optional[str] = "application/octet-stream"
    folder_id: Optional[str] = None
    erasure_id: Optional[str] = "MEDIUM"

class FileUploadResponse(BaseModel):
    file_id: str
    version_id: str
    filename: str
    file_size: int
    content_type: str
    upload_status: str
    fragments_stored: int
    erasure_profile: str

class FileInfo(BaseModel):
    file_id: str
    file_name: str
    file_size: int
    logical_path: str
    uploaded_at: str
    version_id: Optional[str] = None
    erasure_id: Optional[str] = None

class FilesListResponse(BaseModel):
    files: List[FileInfo]
    total: int

def get_current_account_from_master(token: str):
    """Get account info from master node API."""
    try:
        # Decode token to get account_id and username
        payload = decode_access_token(token)
        if not payload:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        
        account_id = payload.get("sub")  # account_id is stored in sub
        username = payload.get("username")  # username is in username field
        
        if not account_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        
        # Query master node for account info using account_id
        response = requests.post(f"{MASTER_NODE_URL}/query", json={
            "sql": "SELECT account_id, username, email, account_type, created_at FROM account WHERE account_id = ?",
            "params": [account_id]
        })
        
        if response.status_code != 200:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Master node error")
        
        result = response.json()
        if not result.get("success") or not result.get("data"):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
        
        return result["data"][0]  # Return first account record
    except requests.exceptions.RequestException as e:
        logger.error(f"Error connecting to master node: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Master node unavailable")

def get_current_account(token=Depends(oauth2_scheme)):
    """Get the current authenticated account from master node."""
    token_str = token.credentials if hasattr(token, "credentials") else token
    return get_current_account_from_master(token_str)

@router.post("/upload", response_model=FileUploadResponse, status_code=status.HTTP_201_CREATED)
def upload_file(
    upload_data: FileUploadRequest,
    request: Request,
    current_account = Depends(get_current_account)
):
    """
    Upload a file to the distributed storage system using the new master node schema.
    Files are processed with erasure coding and distributed across storage nodes.
    """
    try:
        # Decode the base64 file data
        file_data = base64.b64decode(upload_data.data)
        file_size = len(file_data)
        
        # Generate file hash
        file_hash = hashlib.sha256(file_data).hexdigest()
        
        # Create file metadata in master node
        logical_path = f"/{upload_data.filename}"
        if upload_data.folder_id:
            logical_path = f"/folders/{upload_data.folder_id}/{upload_data.filename}"
        
        create_file_payload = {
            "account_id": current_account["account_id"],
            "file_name": upload_data.filename,
            "file_size": file_size,
            "logical_path": logical_path,
            "erasure_id": upload_data.erasure_id
        }
        
        # Create file metadata
        response = requests.post(f"{MASTER_NODE_URL}/files", json=create_file_payload)
        if response.status_code != 200:
            logger.error(f"Failed to create file metadata: {response.text}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create file metadata"
            )
        
        file_metadata = response.json()
        file_id = file_metadata["fileId"]
        version_id = file_metadata["versionId"]
        
        # Get erasure profile
        erasure_response = requests.get(f"{MASTER_NODE_URL}/erasure-profiles/{upload_data.erasure_id}")
        if erasure_response.status_code != 200:
            logger.error(f"Failed to get erasure profile: {erasure_response.text}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to get erasure profile"
            )
        
        erasure_profile = erasure_response.json()
        k_fragments = erasure_profile["k"]
        m_fragments = erasure_profile["m"]
        total_fragments = k_fragments + m_fragments
        fragment_size = erasure_profile["bytes"]
        
        # Simple fragmentation
        fragment_data_list = []
        data_per_fragment = len(file_data) // k_fragments

        for i in range(k_fragments):
            start = i * data_per_fragment
            end = start + data_per_fragment if i < k_fragments - 1 else len(file_data)
            fragment_data = file_data[start:end]
            
            fragment_info = {
                "num_fragment": i,
                "bytes": len(fragment_data),
                "content_hash": hashlib.sha256(fragment_data).hexdigest(),
                "data": base64.b64encode(fragment_data).decode()
            }
            fragment_data_list.append(fragment_info)
        
        # Mock parity: duplicate data fragments
        for i in range(m_fragments):
            source_fragment = fragment_data_list[i % k_fragments].copy()
            source_fragment["num_fragment"] = k_fragments + i
            fragment_data_list.append(source_fragment)
        
        # Tell master node to assign storage nodes
        fragment_payload = {
            "version_id": version_id,
            "segment_id": str(uuid.uuid4()),
            "fragment_data": fragment_data_list,
            "erasure_id": upload_data.erasure_id
        }
        
        distribute_response = requests.post(f"{MASTER_NODE_URL}/file-fragments", json=fragment_payload)
        if distribute_response.status_code != 200:
            logger.error(f"Failed to distribute fragments: {distribute_response.text}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to distribute file fragments"
            )
        
        distribution_result = distribute_response.json()
        distributed_fragments = distribution_result["fragments"]
        
        # Upload fragments to storage nodes
        fragments_stored = 0
        for i, fragment_info in enumerate(fragment_data_list):
            if i >= len(distributed_fragments):
                break
                
            dist_info = distributed_fragments[i]
            try:
                storage_payload = {
                    "fragmentId": dist_info["fragmentId"],
                    "data": fragment_info["data"],
                    "bytes": fragment_info["bytes"],
                    "contentHash": fragment_info["content_hash"]
                }
                
                store_response = requests.post(
                    f"{dist_info['nodeEndpoint']}/fragments",
                    json=storage_payload,
                    timeout=30
                )
                
                if store_response.status_code in [200, 201]:
                    fragments_stored += 1
                    logger.info(f"Fragment {dist_info['fragmentId']} stored on node {dist_info['nodeId']}")
                else:
                    logger.error(f"Failed to store fragment {dist_info['fragmentId']}: {store_response.text}")
                    
            except Exception as e:
                logger.error(f"Error storing fragment {dist_info['fragmentId']}: {e}")
        
        upload_status = "complete" if fragments_stored == len(fragment_data_list) else "partial"
        if fragments_stored == 0:
            upload_status = "failed"
        
        logger.info(
            f"File upload completed: {upload_data.filename}, fragments: "
            f"{fragments_stored}/{len(fragment_data_list)}"
        )
        
        return FileUploadResponse(
            file_id=file_id,
            version_id=version_id,
            filename=upload_data.filename,
            file_size=file_size,
            content_type=upload_data.content_type,
            upload_status=upload_status,
            fragments_stored=fragments_stored,
            erasure_profile=upload_data.erasure_id
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Unexpected error during file upload: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"File upload failed: {str(e)}"
        )



@router.get("", response_model=FilesListResponse)
def get_files(
    folder_id: Optional[str] = Query(None, description="Filter by folder ID. If None, returns files in root."),
    current_account: dict = Depends(get_current_account)
):
    """
    Get all files for the current authenticated user.
    Optionally filter by folder_id to get files in a specific folder.
    """
    try:
        account_id = current_account["account_id"]
        
        # Build SQL query to get files
        if folder_id:
            # Files in a specific folder
            sql = """
                SELECT 
                    fo.file_id, 
                    fo.file_name, 
                    fo.file_size, 
                    fo.logical_path, 
                    fo.uploaded_at,
                    fv.version_id,
                    fv.erasure_id
                FROM file_objects fo
                LEFT JOIN file_versions fv ON fo.file_id = fv.file_id
                WHERE fo.account_id = $1 
                    AND fo.logical_path LIKE $2
                ORDER BY fo.uploaded_at DESC
            """
            # Match files in the folder (logical_path like '/folders/{folder_id}/%')
            folder_path_pattern = f"/folders/{folder_id}/%"
            params = [str(account_id), folder_path_pattern]
        else:
            # Files in root (not in any folder)
            sql = """
                SELECT 
                    fo.file_id, 
                    fo.file_name, 
                    fo.file_size, 
                    fo.logical_path, 
                    fo.uploaded_at,
                    fv.version_id,
                    fv.erasure_id
                FROM file_objects fo
                LEFT JOIN file_versions fv ON fo.file_id = fv.file_id
                WHERE fo.account_id = $1 
                    AND fo.logical_path NOT LIKE '/folders/%'
                ORDER BY fo.uploaded_at DESC
            """
            params = [str(account_id)]
        
        # Query master node
        response = requests.post(f"{MASTER_NODE_URL}/query", json={
            "sql": sql,
            "params": params
        }, timeout=30)
        
        if response.status_code != 200:
            logger.error(f"Failed to query files from master node: {response.text}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve files"
            )
        
        result = response.json()
        if not result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("error", "Failed to retrieve files")
            )
        
        files_data = result.get("data", [])
        
        file_list = []
        for f in files_data:
            # Handle timestamp conversion
            uploaded_at = f["uploaded_at"]
            if isinstance(uploaded_at, str):
                uploaded_at_str = uploaded_at
            else:
                # If it's a datetime object, convert to ISO format
                uploaded_at_str = uploaded_at.isoformat() if hasattr(uploaded_at, "isoformat") else str(uploaded_at)
            
            file_list.append(FileInfo(
                file_id=str(f["file_id"]),
                file_name=f["file_name"],
                file_size=int(f["file_size"]),
                logical_path=f["logical_path"],
                uploaded_at=uploaded_at_str,
                version_id=str(f["version_id"]) if f.get("version_id") else None,
                erasure_id=f.get("erasure_id")
            ))
        
        return FilesListResponse(
            files=file_list,
            total=len(file_list)
        )
    except HTTPException:
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"Error connecting to master node: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Master node unavailable"
        )
    except Exception as e:
        logger.error(f"Error retrieving files: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve files"
        )


@router.get("/{file_name}", response_model=FileInfo)
def get_file(
    file_name: str,
    folder_id: Optional[str] = Query(None, description="Optional folder ID to disambiguate when multiple files have the same name"),
    current_account: dict = Depends(get_current_account)
):
    """
    Get a specific file by name for the current authenticated user.
    If multiple files have the same name, use folder_id to specify which one.
    """
    try:
        account_id = current_account["account_id"]
        
        # Build SQL query based on whether folder_id is provided
        if folder_id:
            # File in a specific folder
            sql = """
                SELECT 
                    fo.file_id, 
                    fo.file_name, 
                    fo.file_size, 
                    fo.logical_path, 
                    fo.uploaded_at,
                    fv.version_id,
                    fv.erasure_id
                FROM file_objects fo
                LEFT JOIN file_versions fv ON fo.file_id = fv.file_id
                WHERE fo.file_name = $1 
                    AND fo.account_id = $2
                    AND fo.logical_path LIKE $3
                ORDER BY fo.uploaded_at DESC
            """
            folder_path_pattern = f"/folders/{folder_id}/%"
            params = [file_name, str(account_id), folder_path_pattern]
        else:
            # File in root or search all locations (will return first match)
            sql = """
                SELECT 
                    fo.file_id, 
                    fo.file_name, 
                    fo.file_size, 
                    fo.logical_path, 
                    fo.uploaded_at,
                    fv.version_id,
                    fv.erasure_id
                FROM file_objects fo
                LEFT JOIN file_versions fv ON fo.file_id = fv.file_id
                WHERE fo.file_name = $1 AND fo.account_id = $2
                ORDER BY fo.uploaded_at DESC
            """
            params = [file_name, str(account_id)]
        
        response = requests.post(f"{MASTER_NODE_URL}/query", json={
            "sql": sql,
            "params": params
        }, timeout=30)
        
        if response.status_code != 200:
            logger.error(f"Failed to query file from master node: {response.text}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve file"
            )
        
        result = response.json()
        if not result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("error", "Failed to retrieve file")
            )
        
        files_data = result.get("data", [])
        if not files_data:
            error_msg = f"File '{file_name}' not found"
            if folder_id:
                error_msg += f" in folder {folder_id}"
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_msg
            )
        
        # Check if there are multiple files with the same name
        if len(files_data) > 1 and folder_id is None:
            logger.warning(f"Multiple files found with name '{file_name}'. Returning first match. Consider using folder_id parameter.")
        
        f = files_data[0]
        # Handle timestamp conversion
        uploaded_at = f["uploaded_at"]
        if isinstance(uploaded_at, str):
            uploaded_at_str = uploaded_at
        else:
            uploaded_at_str = uploaded_at.isoformat() if hasattr(uploaded_at, "isoformat") else str(uploaded_at)
        
        return FileInfo(
            file_id=str(f["file_id"]),
            file_name=f["file_name"],
            file_size=int(f["file_size"]),
            logical_path=f["logical_path"],
            uploaded_at=uploaded_at_str,
            version_id=str(f["version_id"]) if f.get("version_id") else None,
            erasure_id=f.get("erasure_id")
        )
    except HTTPException:
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"Error connecting to master node: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Master node unavailable"
        )
    except Exception as e:
        logger.error(f"Error retrieving file: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve file"
        )