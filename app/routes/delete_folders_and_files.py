from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
import logging
import uuid
import json
from app.master_node_db import MasterNodeDB, get_master_db
from app.core.security import decode_access_token
from app.routes.login import oauth2_scheme

logger = logging.getLogger(__name__)

folders_router = APIRouter(prefix="/folders", tags=["folders"])
files_router = APIRouter(prefix="/files", tags=["files"])

class DeleteFolderResponse(BaseModel):
    message: str
    deleted_folder_id: str
    deleted_folder_name: str

class DeleteFileResponse(BaseModel):
    message: str
    deleted_file_id: str
    deleted_file_name: str

def get_current_account(
    token=Depends(oauth2_scheme),
    master_db: MasterNodeDB = Depends(get_master_db)
) -> dict:
    token_str = token.credentials if hasattr(token, "credentials") else token
    payload = decode_access_token(token_str)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    
    account_id = payload.get("sub")
    if not account_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    
    account_result = master_db.select(
        "SELECT ACCOUNT_ID, USERNAME, EMAIL, ACCOUNT_TYPE, CREATED_AT FROM ACCOUNT WHERE ACCOUNT_ID = $1",
        [account_id]
    )
    
    if not account_result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    result = account_result[0]
    account_dict = {}
    for k, v in result.items():
        key_lower = k.lower()
        account_dict[key_lower] = v
    
    return account_dict

@folders_router.delete("/{folder_id}", response_model=DeleteFolderResponse)
def delete_folder(
    folder_id: uuid.UUID,
    request: Request,
    current_account: dict = Depends(get_current_account),
    master_db: MasterNodeDB = Depends(get_master_db)
):
    """
    Delete a folder and all its children (hard delete).
    Uses CASCADE delete - all child folders will be automatically deleted.
    This action cannot be undone.
    """
    try:
        folder = master_db.select(
            "SELECT FOLDER_ID, NAME FROM FOLDER WHERE FOLDER_ID = $1 AND ACCOUNT_ID = $2",
            [str(folder_id), current_account["account_id"]]
        )
        
        if not folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Folder not found or you don't have permission to delete it"
            )
        
        folder_data = folder[0]
        folder_name = folder_data.get("name") or folder_data.get("NAME")
        folder_id_str = str(folder_id)
        
        master_db.execute(
            "DELETE FROM FOLDER WHERE FOLDER_ID = $1",
            [str(folder_id)]
        )
        
        try:
            client_ip = request.client.host if request.client else "unknown"
            user_agent = request.headers.get("user-agent", "unknown")
            
            details = json.dumps({
                "folder_name": folder_name
            })
            
            master_db.execute(
                """
                INSERT INTO ACTIVITY_LOG (ACTIVITY_ID, ACCOUNT_ID, ACTION_TYPE, RESOURCE_TYPE, RESOURCE_ID, IP_ADDRESS, USER_AGENT, DETAILS, CREATED_AT)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
                """,
                [str(uuid.uuid4()), current_account["account_id"], "FOLDER_DELETE", "FOLDER",
                 str(folder_id), client_ip, user_agent, details]
            )
        except Exception as log_error:
            logger.warning(f"Failed to log folder deletion activity: {str(log_error)}")
        
        return DeleteFolderResponse(
            message=f"Folder '{folder_name}' and all its contents have been permanently deleted",
            deleted_folder_id=folder_id_str,
            deleted_folder_name=folder_name
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting folder: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting folder: {str(e)}"
        )

@files_router.delete("/{file_id}", response_model=DeleteFileResponse)
def delete_file(
    file_id: uuid.UUID,
    request: Request,
    current_account: dict = Depends(get_current_account),
    master_db: MasterNodeDB = Depends(get_master_db)
):
    """
    Delete a file (hard delete).
    Uses CASCADE delete - all file versions, segments, and fragments will be automatically deleted.
    This action cannot be undone.
    """
    try:
        file_obj = master_db.select(
            "SELECT FILE_ID, FILE_NAME, FILE_SIZE FROM FILE_OBJECTS WHERE FILE_ID = $1 AND ACCOUNT_ID = $2",
            [str(file_id), current_account["account_id"]]
        )
        
        if not file_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found or you don't have permission to delete it"
            )
        
        file_data = file_obj[0]
        file_name = file_data.get("file_name") or file_data.get("FILE_NAME")
        file_size = file_data.get("file_size") or file_data.get("FILE_SIZE")
        file_id_str = str(file_id)
        
        master_db.execute(
            "DELETE FROM FILE_OBJECTS WHERE FILE_ID = $1",
            [str(file_id)]
        )
        
        try:
            client_ip = request.client.host if request.client else "unknown"
            user_agent = request.headers.get("user-agent", "unknown")
            
            details = json.dumps({
                "file_name": file_name,
                "file_size": int(file_size) if file_size else 0
            })
            
            master_db.execute(
                """
                INSERT INTO ACTIVITY_LOG (ACTIVITY_ID, ACCOUNT_ID, ACTION_TYPE, RESOURCE_TYPE, RESOURCE_ID, IP_ADDRESS, USER_AGENT, DETAILS, CREATED_AT)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
                """,
                [str(uuid.uuid4()), current_account["account_id"], "FILE_DELETE", "FILE",
                 str(file_id), client_ip, user_agent, details]
            )
        except Exception as log_error:
            logger.warning(f"Failed to log file deletion activity: {str(log_error)}")
        
        return DeleteFileResponse(
            message=f"File '{file_name}' and all its versions have been permanently deleted",
            deleted_file_id=file_id_str,
            deleted_file_name=file_name
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting file: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting file: {str(e)}"
        )
