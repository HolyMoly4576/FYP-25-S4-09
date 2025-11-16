from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import logging
import uuid

from app.db.session import get_db
from app.models import Account, Folder
from app.core.security import decode_access_token
from app.core.activity_logger import log_activity, get_client_ip, get_user_agent
from app.routes.login import oauth2_scheme

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/folders", tags=["folders"])


class MoveFolderRequest(BaseModel):
    new_parent_folder_id: Optional[uuid.UUID] = None  # None means move to root


class FolderResponse(BaseModel):
    folder_id: uuid.UUID
    name: str
    account_id: uuid.UUID
    parent_folder_id: Optional[uuid.UUID] = None
    created_at: str


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


def is_descendant(db: Session, folder_id: uuid.UUID, potential_ancestor_id: uuid.UUID) -> bool:
    """
    Check if potential_ancestor_id is an ancestor of folder_id.
    This prevents circular moves (moving a folder into its own descendant).
    """
    current_id = potential_ancestor_id
    visited = set()
    
    while current_id is not None:
        if current_id == folder_id:
            return True  # Found a circular reference
        if current_id in visited:
            break  # Prevent infinite loops
        
        visited.add(current_id)
        folder = db.query(Folder).filter(Folder.folder_id == current_id).first()
        if not folder:
            break
        current_id = folder.parent_folder_id
    
    return False


@router.patch("/{folder_id}/move", response_model=FolderResponse)
def move_folder(
    folder_id: uuid.UUID,
    body: MoveFolderRequest,
    request: Request,
    current_account: Account = Depends(get_current_account),
    db: Session = Depends(get_db)
):
    """
    Move a folder to a new parent folder or to root.
    Validates ownership, prevents circular moves, and checks for name conflicts.
    """
    try:
        # 1. Verify source folder exists and belongs to user
        folder = db.query(Folder).filter(
            Folder.folder_id == folder_id,
            Folder.account_id == current_account.account_id
        ).first()
        
        if not folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Folder not found or you don't have permission to move it"
            )
        
        # 2. If moving to a parent (not root), validate destination
        if body.new_parent_folder_id is not None:
            # Verify destination folder exists and belongs to user
            destination = db.query(Folder).filter(
                Folder.folder_id == body.new_parent_folder_id,
                Folder.account_id == current_account.account_id
            ).first()
            
            if not destination:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Destination folder not found or you don't have permission to move into it"
                )
            
            # 3. Prevent circular move: cannot move folder into itself or its descendant
            if body.new_parent_folder_id == folder_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot move a folder into itself"
                )
            
            if is_descendant(db, folder_id, body.new_parent_folder_id):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot move a folder into its own descendant"
                )
            
            # 4. Check for name conflicts in destination
            existing = db.query(Folder).filter(
                Folder.account_id == current_account.account_id,
                Folder.parent_folder_id == body.new_parent_folder_id,
                Folder.name == folder.name,
                Folder.folder_id != folder_id  # Exclude the folder being moved
            ).first()
            
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"A folder with the name '{folder.name}' already exists in the destination"
                )
        else:
            # Moving to root - check for name conflicts at root level
            existing = db.query(Folder).filter(
                Folder.account_id == current_account.account_id,
                Folder.parent_folder_id.is_(None),
                Folder.name == folder.name,
                Folder.folder_id != folder_id  # Exclude the folder being moved
            ).first()
            
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"A folder with the name '{folder.name}' already exists at root level"
                )
        
        # 5. Update the folder's parent
        old_parent_id = folder.parent_folder_id
        folder.parent_folder_id = body.new_parent_folder_id
        db.commit()
        db.refresh(folder)
        
        # Log folder move activity
        log_activity(
            db=db,
            account_id=current_account.account_id,
            action_type="FOLDER_MOVE",
            resource_type="FOLDER",
            resource_id=folder_id,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
            details={
                "folder_name": folder.name,
                "old_parent_id": str(old_parent_id) if old_parent_id else None,
                "new_parent_id": str(body.new_parent_folder_id) if body.new_parent_folder_id else None
            }
        )
        
        return FolderResponse(
            folder_id=folder.folder_id,
            name=folder.name,
            account_id=folder.account_id,
            parent_folder_id=folder.parent_folder_id,
            created_at=folder.created_at.isoformat(),
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error moving folder: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error moving folder: {str(e)}"
        )

