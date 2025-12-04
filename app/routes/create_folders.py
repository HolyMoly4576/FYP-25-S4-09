from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
import logging
import uuid

from app.db.session import get_db
from app.models import Account, Folder
from app.core.security import decode_access_token
from app.core.activity_logger import log_activity, get_client_ip, get_user_agent
from app.routes.login import oauth2_scheme

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/folders", tags=["folders"])


class CreateFolderRequest(BaseModel):
    name: str
    parent_folder_id: Optional[uuid.UUID] = None


class FolderResponse(BaseModel):
    folder_id: uuid.UUID
    name: str
    account_id: uuid.UUID
    parent_folder_id: Optional[uuid.UUID] = None
    created_at: str


class FoldersListResponse(BaseModel):
    folders: List[FolderResponse]
    total: int


def get_current_account(
    token=Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> Account:
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


@router.post("", response_model=FolderResponse, status_code=status.HTTP_201_CREATED)
def create_folder(
    body: CreateFolderRequest,
    request: Request,
    current_account: Account = Depends(get_current_account),
    db: Session = Depends(get_db)
):
    # Validate name
    if body.name is None or body.name.strip() == "":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Folder name cannot be empty")

    # Validate parent if provided and ensure ownership
    if body.parent_folder_id is not None:
        parent = db.query(Folder).filter(
            Folder.folder_id == body.parent_folder_id,
            Folder.account_id == current_account.account_id
        ).first()
        if not parent:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent folder not found")

    # Optional: enforce unique name per account+parent
    existing = db.query(Folder).filter(
        Folder.account_id == current_account.account_id,
        Folder.parent_folder_id.is_(body.parent_folder_id) if body.parent_folder_id is None else Folder.parent_folder_id == body.parent_folder_id,
        Folder.name == body.name
    ).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Folder with same name already exists in this location")

    folder = Folder(
        name=body.name.strip(),
        account_id=current_account.account_id,
        parent_folder_id=body.parent_folder_id
    )
    db.add(folder)
    db.commit()
    db.refresh(folder)

    # Log folder creation activity
    log_activity(
        db=db,
        account_id=current_account.account_id,
        action_type="FOLDER_CREATE",
        resource_type="FOLDER",
        resource_id=folder.folder_id,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        details={"folder_name": folder.name, "parent_folder_id": str(folder.parent_folder_id) if folder.parent_folder_id else None}
    )

    return FolderResponse(
        folder_id=folder.folder_id,
        name=folder.name,
        account_id=folder.account_id,
        parent_folder_id=folder.parent_folder_id,
        created_at=folder.created_at.isoformat(),
    )


@router.get("", response_model=FoldersListResponse)
def get_folders(
    parent_folder_id: Optional[uuid.UUID] = Query(None, description="Filter by parent folder ID. If None, returns root folders."),
    current_account: Account = Depends(get_current_account),
    db: Session = Depends(get_db)
):
    """
    Get all folders for the current authenticated user.
    Optionally filter by parent_folder_id to get folders in a specific directory.
    """
    try:
        # Base query - only folders for current user
        query = db.query(Folder).filter(
            Folder.account_id == current_account.account_id
        )
        
        # Filter by parent folder if provided
        if parent_folder_id is not None:
            query = query.filter(Folder.parent_folder_id == parent_folder_id)
        else:
            # If parent_folder_id is None, get root folders (where parent_folder_id IS NULL)
            query = query.filter(Folder.parent_folder_id.is_(None))
        
        # Order by name
        folders = query.order_by(Folder.name).all()
        
        folder_responses = [
            FolderResponse(
                folder_id=folder.folder_id,
                name=folder.name,
                account_id=folder.account_id,
                parent_folder_id=folder.parent_folder_id,
                created_at=folder.created_at.isoformat(),
            )
            for folder in folders
        ]
        
        return FoldersListResponse(
            folders=folder_responses,
            total=len(folder_responses)
        )
    except Exception as e:
        logger.error(f"Error retrieving folders: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve folders"
        )


@router.get("/{folder_name}", response_model=FolderResponse)
def get_folder(
    folder_name: str,
    parent_folder_id: Optional[uuid.UUID] = Query(None, description="Optional parent folder ID to disambiguate when multiple folders have the same name"),
    current_account: Account = Depends(get_current_account),
    db: Session = Depends(get_db)
):
    """
    Get a specific folder by name for the current authenticated user.
    If multiple folders have the same name, use parent_folder_id to specify which one.
    """
    try:
        query = db.query(Folder).filter(
            Folder.name == folder_name,
            Folder.account_id == current_account.account_id
        )
        
        # If parent_folder_id is provided, filter by it
        if parent_folder_id is not None:
            query = query.filter(Folder.parent_folder_id == parent_folder_id)
        else:
            # If not provided, prefer root folders (where parent_folder_id IS NULL)
            # But if multiple exist, return the first one
            pass
        
        folder = query.first()
        
        if not folder:
            error_msg = f"Folder '{folder_name}' not found"
            if parent_folder_id:
                error_msg += f" in parent folder {parent_folder_id}"
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_msg
            )
        
        # Check if there are multiple folders with the same name
        count = query.count()
        if count > 1 and parent_folder_id is None:
            logger.warning(f"Multiple folders found with name '{folder_name}'. Returning first match. Consider using parent_folder_id parameter.")
        
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
        logger.error(f"Error retrieving folder: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve folder"
        )


