from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from typing import Optional
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
        k_fragments = erasure_profile["k"]  # Data fragments
        m_fragments = erasure_profile["m"]  # Parity fragments
        total_fragments = k_fragments + m_fragments
        fragment_size = erasure_profile["bytes"]
        
        # Simple fragmentation (in production, use proper erasure coding)
        fragments = []
        fragment_data_list = []
        
        # Split file into k data fragments
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
        
        # TODO: Generate parity fragments using Reed-Solomon coding
        # For now, just duplicate some data fragments as simple redundancy
        for i in range(m_fragments):
            source_fragment = fragment_data_list[i % k_fragments].copy()
            source_fragment["num_fragment"] = k_fragments + i
            fragment_data_list.append(source_fragment)
        
        # Distribute fragments via master node
        fragment_payload = {
            "version_id": version_id,
            "segment_id": str(uuid.uuid4()),  # Single segment for now
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
        
        # Store actual fragment data on storage nodes
        fragments_stored = 0
        for i, fragment_info in enumerate(fragment_data_list):
            if i >= len(distributed_fragments):
                break
                
            dist_info = distributed_fragments[i]
            try:
                # Send fragment data to assigned storage node
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
        
        logger.info(f"File upload completed: {upload_data.filename}, fragments: {fragments_stored}/{len(fragment_data_list)}")
        
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
        logger.error(f"Error uploading file: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error uploading file: {str(e)}"
        )