from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
import logging
import uuid

from app.db.session import get_db
from app.models import Account, Folder, FileObject
from app.core.security import decode_access_token
from app.routes.login import oauth2_scheme

logger = logging.getLogger(__name__)

# Router for folders
folders_router = APIRouter(prefix="/folders", tags=["folders"])

# Router for files
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
    db: Session = Depends(get_db)
) -> Account:
    """Get the current authenticated account."""
    token_str = token.credentials if hasattr(token, "credentials") else token
    payload = decode_access_token(token_str)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    account_id = payload.get("sub")
    if not account_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    account = db.query(Account).filter(Account.account_id == account_id).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return account


@folders_router.delete("/{folder_id}", response_model=DeleteFolderResponse)
def delete_folder(
    folder_id: uuid.UUID,
    current_account: Account = Depends(get_current_account),
    db: Session = Depends(get_db)
):
    """
    Delete a folder and all its children (hard delete).
    Uses CASCADE delete - all child folders will be automatically deleted.
    This action cannot be undone.
    """
    try:
        # Verify folder exists and belongs to user
        folder = db.query(Folder).filter(
            Folder.folder_id == folder_id,
            Folder.account_id == current_account.account_id
        ).first()
        
        if not folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Folder not found or you don't have permission to delete it"
            )
        
        # Store folder info for response
        folder_name = folder.name
        folder_id_str = str(folder.folder_id)
        
        # Delete the folder (CASCADE will handle child folders automatically)
        db.delete(folder)
        db.commit()
        
        return DeleteFolderResponse(
            message=f"Folder '{folder_name}' and all its contents have been permanently deleted",
            deleted_folder_id=folder_id_str,
            deleted_folder_name=folder_name
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting folder: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting folder: {str(e)}"
        )


@files_router.delete("/{file_id}", response_model=DeleteFileResponse)
def delete_file(
    file_id: uuid.UUID,
    current_account: Account = Depends(get_current_account),
    db: Session = Depends(get_db)
):
    """
    Delete a file (hard delete).
    Uses CASCADE delete - all file versions, segments, and fragments will be automatically deleted.
    This action cannot be undone.
    """
    try:
        # Verify file exists and belongs to user
        file_obj = db.query(FileObject).filter(
            FileObject.file_id == file_id,
            FileObject.account_id == current_account.account_id
        ).first()
        
        if not file_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found or you don't have permission to delete it"
            )
        
        # Store file info for response
        file_name = file_obj.file_name
        file_id_str = str(file_obj.file_id)
        
        # Delete the file (CASCADE will handle versions, segments, fragments automatically)
        db.delete(file_obj)
        db.commit()
        
        return DeleteFileResponse(
            message=f"File '{file_name}' and all its versions have been permanently deleted",
            deleted_file_id=file_id_str,
            deleted_file_name=file_name
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting file: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting file: {str(e)}"
        )

