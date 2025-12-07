from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from typing import Optional, List
import logging
import uuid
import traceback

from app.master_node_db import MasterNodeDB, get_master_db
from app.core.security import decode_access_token
from app.routes.login import oauth2_scheme

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])


class FileInfo(BaseModel):
    file_id: str
    file_name: str
    file_size: int
    logical_path: str
    uploaded_at: str
    version_id: Optional[str] = None
    erasure_id: Optional[str] = None
    item_type: str = "file"


class FolderInfo(BaseModel):
    folder_id: str
    name: str
    account_id: str
    parent_folder_id: Optional[str] = None
    created_at: str
    item_type: str = "folder"


class SearchResult(BaseModel):
    files: List[FileInfo]
    folders: List[FolderInfo]
    total_files: int
    total_folders: int
    total: int


def get_current_account(
    token=Depends(oauth2_scheme),
    master_db: MasterNodeDB = Depends(get_master_db)
) -> dict:
    """Get the current authenticated account from master node."""
    token_str = token.credentials if hasattr(token, "credentials") else token
    payload = decode_access_token(token_str)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    
    account_id = payload.get("sub")
    if not account_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    
    account_result = master_db.select(
        "SELECT account_id, username, email, account_type, created_at FROM account WHERE account_id = $1",
        [account_id]
    )
    
    if not account_result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    return account_result[0]


@router.get("/files-and-folders", response_model=SearchResult)
def search_files_and_folders(
    q: str = Query(..., description="Search keyword for file or folder name (partial, case-insensitive match)"),
    current_account: dict = Depends(get_current_account),
    master_db: MasterNodeDB = Depends(get_master_db)
):
    """
    Search both files and folders for the current authenticated user by partial name match.
    Returns a combined result with files and folders that match the search query.
    """
    try:
        account_id = current_account["account_id"]
        search_pattern = f"%{q}%"
        
        # Search files
        files_sql = """
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
                AND fo.file_name ILIKE $2
            ORDER BY fo.uploaded_at DESC
        """
        
        files_data = master_db.select(files_sql, [str(account_id), search_pattern])
        
        # Search folders
        folders_sql = """
            SELECT 
                folder_id, 
                name, 
                account_id, 
                parent_folder_id, 
                created_at
            FROM folder
            WHERE account_id = $1 
                AND name ILIKE $2
            ORDER BY name
        """
        
        folders_data = master_db.select(folders_sql, [str(account_id), search_pattern])
        
        # Process files
        file_list: List[FileInfo] = []
        for f in files_data:
            uploaded_at = f.get("uploaded_at")
            if isinstance(uploaded_at, str):
                uploaded_at_str = uploaded_at
            else:
                uploaded_at_str = (
                    uploaded_at.isoformat()
                    if hasattr(uploaded_at, "isoformat")
                    else str(uploaded_at)
                )
            
            file_list.append(
                FileInfo(
                    file_id=str(f.get("file_id") or f.get("FILE_ID")),
                    file_name=f.get("file_name") or f.get("FILE_NAME"),
                    file_size=int(f.get("file_size") or f.get("FILE_SIZE")),
                    logical_path=f.get("logical_path") or f.get("LOGICAL_PATH"),
                    uploaded_at=uploaded_at_str,
                    version_id=str(f.get("version_id") or f.get("VERSION_ID")) if f.get("version_id") or f.get("VERSION_ID") else None,
                    erasure_id=f.get("erasure_id") or f.get("ERASURE_ID"),
                    item_type="file"
                )
            )
        
        # Process folders
        folder_list: List[FolderInfo] = []
        for folder in folders_data:
            folder_id_val = folder.get("folder_id") or folder.get("FOLDER_ID")
            name_val = folder.get("name") or folder.get("NAME")
            account_id_val = folder.get("account_id") or folder.get("ACCOUNT_ID")
            parent_folder_id_val = folder.get("parent_folder_id") or folder.get("PARENT_FOLDER_ID")
            created_at_val = folder.get("created_at") or folder.get("CREATED_AT")
            
            if hasattr(created_at_val, "isoformat"):
                created_at_str = created_at_val.isoformat()
            else:
                created_at_str = str(created_at_val)
            
            folder_list.append(
                FolderInfo(
                    folder_id=str(folder_id_val),
                    name=name_val,
                    account_id=str(account_id_val),
                    parent_folder_id=str(parent_folder_id_val) if parent_folder_id_val else None,
                    created_at=created_at_str,
                    item_type="folder"
                )
            )
        
        total_files = len(file_list)
        total_folders = len(folder_list)
        total = total_files + total_folders
        
        return SearchResult(
            files=file_list,
            folders=folder_list,
            total_files=total_files,
            total_folders=total_folders,
            total=total
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching files and folders: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to search files and folders: {str(e)}"
        )

