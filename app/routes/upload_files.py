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
import traceback

# Import Reed-Solomon erasure coding
from app.core.erasure_coding import get_erasure_coder_for_account, get_erasure_coder_for_profile

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
            "sql": "SELECT account_id, username, email, account_type, created_at FROM ACCOUNT WHERE account_id = $1",
            "params": [account_id]
        })
        
        if response.status_code != 200:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Master node error")
        
        result = response.json()
        if not result.get("success") or not result.get("data") or len(result.get("data")) == 0:
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
        if response.status_code not in [200, 201]:
            logger.error(f"Failed to create file metadata: Status {response.status_code}, Response: {response.text}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create file metadata: {response.text}"
            )
        
        file_metadata = response.json()
        file_id = file_metadata["fileId"]
        version_id = file_metadata["versionId"]
        
        # Get erasure profile and initialize Reed-Solomon encoder
        # Always use the explicitly requested profile to respect user choice
        erasure_coder = get_erasure_coder_for_profile(upload_data.erasure_id)
        profile_info = erasure_coder.get_fragment_info()
        k_fragments = profile_info["k"]
        m_fragments = profile_info["m"]
        total_fragments = profile_info["n"]
        logger.info(f"Using requested Reed-Solomon profile {upload_data.erasure_id}: {k_fragments}+{m_fragments}={total_fragments} fragments")
        
        # Encode file data using Reed-Solomon
        try:
            fragments = erasure_coder.encode_data(file_data)
            logger.info(f"Reed-Solomon encoding produced {len(fragments)} fragments from {len(file_data)} bytes")
        except Exception as e:
            logger.error(f"Reed-Solomon encoding failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erasure coding failed: {str(e)}"
            )
        
        # Prepare fragment data for distribution
        fragment_data_list = []
        for i, fragment_data in enumerate(fragments):
            fragment_info = {
                "num_fragment": i,
                "bytes": len(fragment_data),
                "content_hash": hashlib.sha256(fragment_data).hexdigest(),
                "data": base64.b64encode(fragment_data).decode()
            }
            fragment_data_list.append(fragment_info)
        
        # First, get distribution plan from master node
        fragment_payload = {
            "version_id": version_id,
            "segment_id": str(uuid.uuid4()),  # Single segment for now
            "fragment_data": fragment_data_list,
            "erasure_id": upload_data.erasure_id
        }
        
        distribute_response = requests.post(f"{MASTER_NODE_URL}/file-fragments", json=fragment_payload)
        if distribute_response.status_code not in [200, 201]:
            logger.error(f"Failed to get distribution plan: Status {distribute_response.status_code}, Response: {distribute_response.text}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get fragment distribution plan: {distribute_response.text}"
            )
        
        distribution_result = distribute_response.json()
        
        if not distribution_result.get("success", False):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Master node failed to create distribution plan"
            )
        
        distributed_fragments = distribution_result.get("fragments", [])
        
        # Now actually store fragment data on storage nodes
        fragments_stored = 0
        for i, fragment_plan in enumerate(distributed_fragments):
            try:
                # Get the corresponding fragment data
                fragment_info = fragment_data_list[i]
                
                # Map internal Docker endpoints to host ports
                node_endpoint = fragment_plan["nodeEndpoint"]
                
                # Use internal Docker network endpoint directly since FastAPI runs in Docker
                # Example: http://storage_node_1:3000 (keep as-is for Docker network)
                storage_url = node_endpoint
                
                fragment_id = fragment_plan["fragmentId"]
                
                # Prepare fragment data for storage node
                fragment_payload = {
                    "fragmentId": fragment_id,
                    "data": fragment_info["data"],  # base64 encoded data
                    "contentHash": fragment_info["content_hash"],
                    "bytes": fragment_info["bytes"],
                    "fileId": file_id,  # Add file ID for master node notification
                    "fragmentOrder": fragment_info["num_fragment"]
                }
                
                # Store fragment on storage node using correct endpoint
                logger.info(f"Storing fragment {fragment_id} on {storage_url}")
                
                store_response = requests.post(f"{storage_url}/fragments", json=fragment_payload, timeout=30)
                
                if store_response.status_code in [200, 201]:
                    fragments_stored += 1
                    logger.info(f"✅ Fragment {fragment_id} stored successfully on {storage_url}")
                else:
                    logger.error(f"❌ Failed to store fragment {fragment_id} on {storage_url}: Status {store_response.status_code}, Response: {store_response.text}")
                    
            except Exception as e:
                logger.error(f"❌ Exception storing fragment {i}: {e}")
                continue
        
        total_fragments_expected = len(fragment_data_list)
        
        upload_status = "complete" if fragments_stored == total_fragments_expected else "partial"
        if fragments_stored == 0:
            upload_status = "failed"
        
        logger.info(f"File upload completed via master node: {upload_data.filename}, fragments: {fragments_stored}/{total_fragments_expected}")
        
        return FileUploadResponse(
            file_id=file_id,
            version_id=version_id,
            filename=upload_data.filename,
            file_size=file_size,
            content_type=upload_data.content_type,
            upload_status=upload_status,
            fragments_stored=fragments_stored,
            erasure_profile=upload_data.erasure_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading file: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error uploading file: {str(e)}",
        )