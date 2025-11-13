from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import logging
import uuid

from app.db.session import get_db
from app.models import Account, Folder
from app.core.security import decode_access_token
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

    return FolderResponse(
        folder_id=folder.folder_id,
        name=folder.name,
        account_id=folder.account_id,
        parent_folder_id=folder.parent_folder_id,
        created_at=folder.created_at.isoformat(),
    )


