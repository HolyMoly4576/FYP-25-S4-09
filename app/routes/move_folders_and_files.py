from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from typing import Optional
import logging
import uuid
import json
from app.master_node_db import MasterNodeDB, get_master_db
from app.core.security import decode_access_token
from app.routes.login import oauth2_scheme

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/folders", tags=["folders"])

class MoveFolderRequest(BaseModel):
    new_parent_folder_id: Optional[uuid.UUID] = None

class MoveFileRequest(BaseModel):
    new_folder_id: Optional[uuid.UUID] = None

class FolderResponse(BaseModel):
    folder_id: uuid.UUID
    name: str
    account_id: uuid.UUID
    parent_folder_id: Optional[uuid.UUID] = None
    created_at: str

class FileResponse(BaseModel):
    file_id: uuid.UUID
    filename: str
    account_id: uuid.UUID
    folder_id: Optional[uuid.UUID] = None
    file_size: int
    created_at: str
    updated_at: str

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

def is_descendant(master_db: MasterNodeDB, folder_id: uuid.UUID, potential_ancestor_id: uuid.UUID) -> bool:
    current_id = potential_ancestor_id
    visited = set()
    
    while current_id is not None:
        if current_id == folder_id:
            return True
        
        if current_id in visited:
            break
        
        visited.add(current_id)
        
        folder = master_db.select(
            "SELECT PARENT_FOLDER_ID FROM FOLDER WHERE FOLDER_ID = $1",
            [str(current_id)]
        )
        
        if not folder:
            break
        
        parent_id = folder[0].get("parent_folder_id") or folder[0].get("PARENT_FOLDER_ID")
        current_id = uuid.UUID(str(parent_id)) if parent_id else None
    
    return False

@router.patch("/{folder_id}/move", response_model=FolderResponse)
def move_folder(
    folder_id: uuid.UUID,
    body: MoveFolderRequest,
    request: Request,
    current_account: dict = Depends(get_current_account),
    master_db: MasterNodeDB = Depends(get_master_db)
):
    """
    Move a folder to a new parent folder or to root.
    Validates ownership, prevents circular moves, and checks for name conflicts.
    """
    try:
        folder = master_db.select(
            "SELECT FOLDER_ID, NAME, ACCOUNT_ID, PARENT_FOLDER_ID, CREATED_AT FROM FOLDER WHERE FOLDER_ID = $1 AND ACCOUNT_ID = $2",
            [str(folder_id), current_account["account_id"]]
        )
        
        if not folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Folder not found or you don't have permission to move it"
            )
        
        folder_data = folder[0]
        folder_name = folder_data.get("name") or folder_data.get("NAME")
        old_parent_id = folder_data.get("parent_folder_id") or folder_data.get("PARENT_FOLDER_ID")
        
        if body.new_parent_folder_id is not None:
            destination = master_db.select(
                "SELECT FOLDER_ID FROM FOLDER WHERE FOLDER_ID = $1 AND ACCOUNT_ID = $2",
                [str(body.new_parent_folder_id), current_account["account_id"]]
            )
            
            if not destination:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Destination folder not found or you don't have permission to move into it"
                )
            
            if body.new_parent_folder_id == folder_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot move a folder into itself"
                )
            
            if is_descendant(master_db, folder_id, body.new_parent_folder_id):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot move a folder into its own descendant"
                )
            
            existing = master_db.select(
                "SELECT FOLDER_ID FROM FOLDER WHERE ACCOUNT_ID = $1 AND PARENT_FOLDER_ID = $2 AND NAME = $3 AND FOLDER_ID != $4",
                [current_account["account_id"], str(body.new_parent_folder_id), folder_name, str(folder_id)]
            )
            
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"A folder with the name '{folder_name}' already exists in the destination"
                )
        else:
            existing = master_db.select(
                "SELECT FOLDER_ID FROM FOLDER WHERE ACCOUNT_ID = $1 AND PARENT_FOLDER_ID IS NULL AND NAME = $2 AND FOLDER_ID != $3",
                [current_account["account_id"], folder_name, str(folder_id)]
            )
            
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"A folder with the name '{folder_name}' already exists at root level"
                )
        
        master_db.execute(
            "UPDATE FOLDER SET PARENT_FOLDER_ID = $1 WHERE FOLDER_ID = $2",
            [str(body.new_parent_folder_id) if body.new_parent_folder_id else None, str(folder_id)]
        )
        
        try:
            client_ip = request.client.host if request.client else "unknown"
            user_agent = request.headers.get("user-agent", "unknown")
            
            details = json.dumps({
                "folder_name": folder_name,
                "old_parent_id": str(old_parent_id) if old_parent_id else None,
                "new_parent_id": str(body.new_parent_folder_id) if body.new_parent_folder_id else None
            })
            
            master_db.execute(
                """
                INSERT INTO ACTIVITY_LOG (ACTIVITY_ID, ACCOUNT_ID, ACTION_TYPE, RESOURCE_TYPE, RESOURCE_ID, IP_ADDRESS, USER_AGENT, DETAILS, CREATED_AT)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
                """,
                [str(uuid.uuid4()), current_account["account_id"], "FOLDER_MOVE", "FOLDER",
                 str(folder_id), client_ip, user_agent, details]
            )
        except Exception as log_error:
            logger.warning(f"Failed to log folder move activity: {str(log_error)}")
        
        updated_folder = master_db.select(
            "SELECT FOLDER_ID, NAME, ACCOUNT_ID, PARENT_FOLDER_ID, CREATED_AT FROM FOLDER WHERE FOLDER_ID = $1",
            [str(folder_id)]
        )
        
        if not updated_folder:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve moved folder")
        
        folder = updated_folder[0]
        folder_id_val = folder.get("folder_id") or folder.get("FOLDER_ID")
        name_val = folder.get("name") or folder.get("NAME")
        account_id_val = folder.get("account_id") or folder.get("ACCOUNT_ID")
        parent_folder_id_val = folder.get("parent_folder_id") or folder.get("PARENT_FOLDER_ID")
        created_at_val = folder.get("created_at") or folder.get("CREATED_AT")
        
        if hasattr(created_at_val, "isoformat"):
            created_at_str = created_at_val.isoformat()
        else:
            created_at_str = str(created_at_val)
        
        return FolderResponse(
            folder_id=uuid.UUID(str(folder_id_val)),
            name=name_val,
            account_id=uuid.UUID(str(account_id_val)),
            parent_folder_id=uuid.UUID(str(parent_folder_id_val)) if parent_folder_id_val else None,
            created_at=created_at_str
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error moving folder: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error moving folder: {str(e)}"
        )

@router.patch("/files/{file_id}/move", response_model=FileResponse)
def move_file(
    file_id: uuid.UUID,
    body: MoveFileRequest,
    request: Request,
    current_account: dict = Depends(get_current_account),
    master_db: MasterNodeDB = Depends(get_master_db)
):
    """
    Move a file to a different folder or to root.
    Validates ownership and checks for filename conflicts.
    """
    try:
        file = master_db.select(
            "SELECT FILE_ID, FILE_NAME, ACCOUNT_ID, FOLDER_ID, FILE_SIZE, UPLOADED_AT, UPDATED_AT FROM FILE_OBJECTS WHERE FILE_ID = $1 AND ACCOUNT_ID = $2",
            [str(file_id), current_account["account_id"]]
        )
        
        if not file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found or you don't have permission to move it"
            )
        
        file_data = file[0]
        filename = file_data.get("file_name") or file_data.get("FILE_NAME")
        old_folder_id = file_data.get("folder_id") or file_data.get("FOLDER_ID")
        
        if body.new_folder_id is not None:
            destination = master_db.select(
                "SELECT FOLDER_ID FROM FOLDER WHERE FOLDER_ID = $1 AND ACCOUNT_ID = $2",
                [str(body.new_folder_id), current_account["account_id"]]
            )
            
            if not destination:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Destination folder not found or you don't have permission to move into it"
                )
            
            existing = master_db.select(
                "SELECT FILE_ID FROM FILE_OBJECTS WHERE ACCOUNT_ID = $1 AND FOLDER_ID = $2 AND FILE_NAME = $3 AND FILE_ID != $4",
                [current_account["account_id"], str(body.new_folder_id), filename, str(file_id)]
            )
            
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"A file with the name '{filename}' already exists in the destination folder"
                )
        else:
            existing = master_db.select(
                "SELECT FILE_ID FROM FILE_OBJECTS WHERE ACCOUNT_ID = $1 AND FOLDER_ID IS NULL AND FILE_NAME = $2 AND FILE_ID != $3",
                [current_account["account_id"], filename, str(file_id)]
            )
            
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"A file with the name '{filename}' already exists at root level"
                )
        
        master_db.execute(
            "UPDATE FILE_OBJECTS SET FOLDER_ID = $1, UPDATED_AT = NOW() WHERE FILE_ID = $2",
            [str(body.new_folder_id) if body.new_folder_id else None, str(file_id)]
        )
        
        try:
            client_ip = request.client.host if request.client else "unknown"
            user_agent = request.headers.get("user-agent", "unknown")
            
            details = json.dumps({
                "filename": filename,
                "old_folder_id": str(old_folder_id) if old_folder_id else None,
                "new_folder_id": str(body.new_folder_id) if body.new_folder_id else None
            })
            
            master_db.execute(
                """
                INSERT INTO ACTIVITY_LOG (ACTIVITY_ID, ACCOUNT_ID, ACTION_TYPE, RESOURCE_TYPE, RESOURCE_ID, IP_ADDRESS, USER_AGENT, DETAILS, CREATED_AT)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
                """,
                [str(uuid.uuid4()), current_account["account_id"], "FILE_MOVE", "FILE",
                 str(file_id), client_ip, user_agent, details]
            )
        except Exception as log_error:
            logger.warning(f"Failed to log file move activity: {str(log_error)}")
        
        updated_file = master_db.select(
            "SELECT FILE_ID, FILE_NAME, ACCOUNT_ID, FOLDER_ID, FILE_SIZE, UPLOADED_AT, UPDATED_AT FROM FILE_OBJECTS WHERE FILE_ID = $1",
            [str(file_id)]
        )
        
        if not updated_file:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve moved file")
        
        file = updated_file[0]
        file_id_val = file.get("file_id") or file.get("FILE_ID")
        filename_val = file.get("file_name") or file.get("FILE_NAME")
        account_id_val = file.get("account_id") or file.get("ACCOUNT_ID")
        folder_id_val = file.get("folder_id") or file.get("FOLDER_ID")
        file_size_val = file.get("file_size") or file.get("FILE_SIZE")
        created_at_val = file.get("uploaded_at") or file.get("UPLOADED_AT")
        updated_at_val = file.get("updated_at") or file.get("UPDATED_AT")
        
        if hasattr(created_at_val, "isoformat"):
            created_at_str = created_at_val.isoformat()
        else:
            created_at_str = str(created_at_val)
        
        if hasattr(updated_at_val, "isoformat"):
            updated_at_str = updated_at_val.isoformat()
        else:
            updated_at_str = str(updated_at_val)
        
        return FileResponse(
            file_id=uuid.UUID(str(file_id_val)),
            filename=filename_val,
            account_id=uuid.UUID(str(account_id_val)),
            folder_id=uuid.UUID(str(folder_id_val)) if folder_id_val else None,
            file_size=int(file_size_val),
            created_at=created_at_str,
            updated_at=updated_at_str
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error moving file: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error moving file: {str(e)}"
        )
