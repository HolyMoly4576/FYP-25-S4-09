from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timedelta, timezone
import uuid

from app.db.session import get_db
from app.models import Account, FileObject, Folder, RecycleBin
from app.routes.login import oauth2_scheme
from app.core.security import decode_access_token
from app.core.activity_logger import log_activity
from app.core.timezone_utils import now_utc, to_local_timezone

router = APIRouter(prefix="/bin", tags=["Recycle Bin"])

# Pydantic models for request/response
class DeleteFileRequest(BaseModel):
    file_id: str = Field(..., description="UUID of the file to delete")
    deletion_reason: Optional[str] = Field("USER_DELETE", description="Reason for deletion")

class DeleteFolderRequest(BaseModel):
    folder_id: str = Field(..., description="UUID of the folder to delete")
    deletion_reason: Optional[str] = Field("USER_DELETE", description="Reason for deletion")

class RestoreItemRequest(BaseModel):
    bin_id: str = Field(..., description="UUID of the bin item to restore")

class BinItemResponse(BaseModel):
    bin_id: str
    resource_type: str
    resource_id: str
    original_name: str
    original_path: Optional[str]
    original_size: Optional[int]
    deleted_at: datetime
    expires_at: datetime
    deletion_reason: Optional[str]
    days_remaining: int

class BinStatsResponse(BaseModel):
    total_items: int
    total_size_bytes: int
    files_count: int
    folders_count: int
    oldest_item: Optional[datetime]
    items_expiring_soon: int  # Items expiring in next 7 days

def get_current_user(
    token=Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> Account:
    """Get current authenticated user"""
    try:
        token_str = token.credentials if hasattr(token, "credentials") else token
        payload = decode_access_token(token_str)
        
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials"
            )
        
        user_id = payload.get("sub")
        user = db.query(Account).filter(Account.account_id == user_id).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )
        
        return user
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )

def build_file_path(db: Session, file_obj: FileObject) -> str:
    """Build the full path for a file based on its logical_path or folder structure"""
    if hasattr(file_obj, 'logical_path') and file_obj.logical_path:
        return file_obj.logical_path
    return f"/{file_obj.file_name}"

def build_folder_path(db: Session, folder: Folder) -> str:
    """Build the full path for a folder by traversing parent folders"""
    path_parts = []
    current_folder = folder
    
    # Traverse up the folder hierarchy
    while current_folder:
        path_parts.insert(0, current_folder.name)
        if current_folder.parent_folder_id:
            current_folder = db.query(Folder).filter(
                Folder.folder_id == current_folder.parent_folder_id
            ).first()
        else:
            break
    
    return "/" + "/".join(path_parts) if path_parts else f"/{folder.name}"

@router.post("/delete-file")
async def delete_file(
    request: DeleteFileRequest,
    current_user: Account = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Move a file to recycle bin (soft delete)"""
    
    # Verify file exists and belongs to user
    file_obj = db.query(FileObject).filter(
        and_(
            FileObject.file_id == request.file_id,
            FileObject.account_id == current_user.account_id
        )
    ).first()
    
    if not file_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found or access denied"
        )
    
    # Check if file is already in bin
    existing_bin_item = db.query(RecycleBin).filter(
        and_(
            RecycleBin.resource_id == file_obj.file_id,
            RecycleBin.resource_type == "FILE",
            RecycleBin.is_recovered == "FALSE"
        )
    ).first()
    
    if existing_bin_item:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is already in recycle bin"
        )
    
    # Build file path for context
    file_path = build_file_path(db, file_obj)
    
    # Create bin entry
    bin_item = RecycleBin(
        account_id=current_user.account_id,
        resource_type="FILE",
        resource_id=file_obj.file_id,
        original_name=file_obj.file_name,
        original_path=file_path,
        original_size=file_obj.file_size,
        deleted_by=current_user.account_id,
        expires_at=now_utc() + timedelta(days=30),
        deletion_reason=request.deletion_reason,
        bin_metadata={
            "file_type": file_obj.file_name.split('.')[-1] if '.' in file_obj.file_name else None,
            "uploaded_at": file_obj.uploaded_at.isoformat() if hasattr(file_obj, 'uploaded_at') else None
        }
    )
    
    db.add(bin_item)
    
    # Remove file from active files (but keep the record for recovery)
    # Instead of deleting, we could add a 'deleted_at' column to file_objects
    # For now, we'll keep the file record and use the bin table to track deleted state
    
    # Log the deletion activity
    log_activity(
        db=db,
        account_id=current_user.account_id,
        action_type="FILE_DELETE",
        resource_type="FILE",
        resource_id=file_obj.file_id,
        details={
            "file_name": file_obj.file_name,
            "file_path": file_path,
            "deletion_reason": request.deletion_reason,
            "retention_days": 30
        }
    )
    
    db.commit()
    
    return {
        "message": f"File '{file_obj.file_name}' moved to recycle bin",
        "bin_id": str(bin_item.bin_id),
        "expires_at": bin_item.expires_at,
        "retention_days": 30
    }

def get_folder_descendants(db: Session, folder_id, account_id) -> tuple:
    """Recursively get all files and subfolders within a folder"""
    files_to_delete = []
    folders_to_delete = []
    
    def collect_descendants(current_folder_id):
        # Get files in current folder
        files_in_folder = db.query(FileObject).filter(
            and_(
                FileObject.folder_id == current_folder_id,
                FileObject.account_id == account_id
            )
        ).all()
        files_to_delete.extend(files_in_folder)
        
        # Get subfolders in current folder
        subfolders = db.query(Folder).filter(
            and_(
                Folder.parent_folder_id == current_folder_id,
                Folder.account_id == account_id
            )
        ).all()
        
        for subfolder in subfolders:
            # Recursively collect from subfolders
            collect_descendants(subfolder.folder_id)
            folders_to_delete.append(subfolder)
    
    collect_descendants(folder_id)
    
    # Calculate total size of all files
    total_size = sum(file_obj.file_size for file_obj in files_to_delete)
    
    return files_to_delete, folders_to_delete, total_size


@router.post("/delete-folder")
async def delete_folder(
    request: DeleteFolderRequest,
    current_user: Account = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Move a folder and all its contents to recycle bin (soft delete with cascade)"""
    
    # Verify folder exists and belongs to user
    folder = db.query(Folder).filter(
        and_(
            Folder.folder_id == request.folder_id,
            Folder.account_id == current_user.account_id
        )
    ).first()
    
    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Folder not found or access denied"
        )
    
    # Check if folder is already in bin
    existing_bin_item = db.query(RecycleBin).filter(
        and_(
            RecycleBin.resource_id == folder.folder_id,
            RecycleBin.resource_type == "FOLDER",
            RecycleBin.is_recovered == "FALSE"
        )
    ).first()
    
    if existing_bin_item:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Folder is already in recycle bin"
        )
    
    # Build folder path for context
    folder_path = build_folder_path(db, folder)
    
    # Get all files and subfolders that will be deleted
    files_to_delete, subfolders_to_delete, total_files_size = get_folder_descendants(db, folder.folder_id, current_user.account_id)
    
    # Check if any files or subfolders are already in bin
    existing_file_ids = []
    existing_folder_ids = []
    
    for file_obj in files_to_delete:
        existing = db.query(RecycleBin).filter(
            and_(
                RecycleBin.resource_id == file_obj.file_id,
                RecycleBin.resource_type == "FILE",
                RecycleBin.is_recovered == "FALSE"
            )
        ).first()
        if existing:
            existing_file_ids.append(file_obj.file_name)
    
    for subfolder in subfolders_to_delete:
        existing = db.query(RecycleBin).filter(
            and_(
                RecycleBin.resource_id == subfolder.folder_id,
                RecycleBin.resource_type == "FOLDER",
                RecycleBin.is_recovered == "FALSE"
            )
        ).first()
        if existing:
            existing_folder_ids.append(subfolder.name)
    
    if existing_file_ids or existing_folder_ids:
        error_msg = "Some items are already in recycle bin: "
        if existing_file_ids:
            error_msg += f"Files: {', '.join(existing_file_ids[:3])}{'...' if len(existing_file_ids) > 3 else ''}"
        if existing_folder_ids:
            error_msg += f"{'; ' if existing_file_ids else ''}Folders: {', '.join(existing_folder_ids[:3])}{'...' if len(existing_folder_ids) > 3 else ''}"
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )
    
    # Move all files to recycle bin first
    files_moved = 0
    for file_obj in files_to_delete:
        file_path = build_file_path(db, file_obj)
        
        file_bin_item = RecycleBin(
            account_id=current_user.account_id,
            resource_type="FILE",
            resource_id=file_obj.file_id,
            original_name=file_obj.file_name,
            original_path=file_path,
            original_size=file_obj.file_size,
            deleted_by=current_user.account_id,
            expires_at=now_utc() + timedelta(days=30),
            deletion_reason=f"CASCADE_DELETE_FROM_FOLDER:{folder.name}",
            bin_metadata={
                "file_type": file_obj.file_name.split('.')[-1] if '.' in file_obj.file_name else None,
                "uploaded_at": file_obj.uploaded_at.isoformat() if hasattr(file_obj, 'uploaded_at') else None,
                "parent_folder_deletion": str(folder.folder_id),
                "cascaded": True
            }
        )
        db.add(file_bin_item)
        files_moved += 1
        
        # Log file deletion activity
        log_activity(
            db=db,
            account_id=current_user.account_id,
            action_type="FILE_DELETE",
            resource_type="FILE",
            resource_id=file_obj.file_id,
            details={
                "file_name": file_obj.file_name,
                "file_path": file_path,
                "deletion_reason": f"CASCADE_DELETE_FROM_FOLDER:{folder.name}",
                "parent_folder": folder.name,
                "cascaded": True,
                "retention_days": 30
            }
        )
    
    # Move all subfolders to recycle bin
    folders_moved = 0
    for subfolder in subfolders_to_delete:
        subfolder_path = build_folder_path(db, subfolder)
        
        subfolder_bin_item = RecycleBin(
            account_id=current_user.account_id,
            resource_type="FOLDER",
            resource_id=subfolder.folder_id,
            original_name=subfolder.name,
            original_path=subfolder_path,
            original_size=None,
            deleted_by=current_user.account_id,
            expires_at=now_utc() + timedelta(days=30),
            deletion_reason=f"CASCADE_DELETE_FROM_FOLDER:{folder.name}",
            bin_metadata={
                "created_at": subfolder.created_at.isoformat(),
                "parent_folder_deletion": str(folder.folder_id),
                "cascaded": True
            }
        )
        db.add(subfolder_bin_item)
        folders_moved += 1
        
        # Log subfolder deletion activity
        log_activity(
            db=db,
            account_id=current_user.account_id,
            action_type="FOLDER_DELETE",
            resource_type="FOLDER",
            resource_id=subfolder.folder_id,
            details={
                "folder_name": subfolder.name,
                "folder_path": subfolder_path,
                "deletion_reason": f"CASCADE_DELETE_FROM_FOLDER:{folder.name}",
                "parent_folder": folder.name,
                "cascaded": True,
                "retention_days": 30
            }
        )
    
    # Finally, move the main folder to recycle bin
    bin_item = RecycleBin(
        account_id=current_user.account_id,
        resource_type="FOLDER",
        resource_id=folder.folder_id,
        original_name=folder.name,
        original_path=folder_path,
        original_size=total_files_size,  # Total size of all files in the folder
        deleted_by=current_user.account_id,
        expires_at=now_utc() + timedelta(days=30),
        deletion_reason=request.deletion_reason,
        bin_metadata={
            "created_at": folder.created_at.isoformat(),
            "children_files_deleted": files_moved,
            "children_folders_deleted": folders_moved,
            "total_items_deleted": files_moved + folders_moved + 1,  # +1 for the folder itself
            "total_files_size": total_files_size
        }
    )
    
    db.add(bin_item)
    
    # Log the main folder deletion activity
    log_activity(
        db=db,
        account_id=current_user.account_id,
        action_type="FOLDER_DELETE",
        resource_type="FOLDER",
        resource_id=folder.folder_id,
        details={
            "folder_name": folder.name,
            "folder_path": folder_path,
            "deletion_reason": request.deletion_reason,
            "files_deleted": files_moved,
            "subfolders_deleted": folders_moved,
            "total_items_deleted": files_moved + folders_moved + 1,
            "total_files_size": total_files_size,
            "retention_days": 30
        }
    )
    
    db.commit()
    
    return {
        "message": f"Folder '{folder.name}' and all its contents moved to recycle bin",
        "bin_id": str(bin_item.bin_id),
        "expires_at": bin_item.expires_at,
        "retention_days": 30,
        "files_deleted": files_moved,
        "subfolders_deleted": folders_moved,
        "total_items_deleted": files_moved + folders_moved + 1,
        "total_files_size": total_files_size
    }

@router.get("/list", response_model=List[BinItemResponse])
async def list_bin_items(
    current_user: Account = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all items in user's recycle bin"""
    
    bin_items = db.query(RecycleBin).filter(
        and_(
            RecycleBin.account_id == current_user.account_id,
            RecycleBin.is_recovered == "FALSE"
        )
    ).order_by(RecycleBin.deleted_at.desc()).all()
    
    result = []
    for item in bin_items:
        days_remaining = (item.expires_at - now_utc()).days
        days_remaining = max(0, days_remaining)  # Don't show negative days
        
        result.append(BinItemResponse(
            bin_id=str(item.bin_id),
            resource_type=item.resource_type,
            resource_id=str(item.resource_id),
            original_name=item.original_name,
            original_path=item.original_path,
            original_size=item.original_size,
            deleted_at=item.deleted_at,
            expires_at=item.expires_at,
            deletion_reason=item.deletion_reason,
            days_remaining=days_remaining
        ))
    
    return result

@router.get("/stats", response_model=BinStatsResponse)
async def get_bin_stats(
    current_user: Account = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get statistics about user's recycle bin"""
    
    bin_items = db.query(RecycleBin).filter(
        and_(
            RecycleBin.account_id == current_user.account_id,
            RecycleBin.is_recovered == "FALSE"
        )
    ).all()
    
    total_items = len(bin_items)
    files_count = sum(1 for item in bin_items if item.resource_type == "FILE")
    folders_count = sum(1 for item in bin_items if item.resource_type == "FOLDER")
    total_size_bytes = sum(item.original_size or 0 for item in bin_items)
    
    # Find oldest item
    oldest_item = None
    if bin_items:
        oldest_item = min(item.deleted_at for item in bin_items)
    
    # Items expiring in next 7 days
    seven_days_from_now = now_utc() + timedelta(days=7)
    items_expiring_soon = sum(
        1 for item in bin_items 
        if item.expires_at <= seven_days_from_now
    )
    
    return BinStatsResponse(
        total_items=total_items,
        total_size_bytes=total_size_bytes,
        files_count=files_count,
        folders_count=folders_count,
        oldest_item=oldest_item,
        items_expiring_soon=items_expiring_soon
    )

@router.post("/restore")
async def restore_item(
    request: RestoreItemRequest,
    current_user: Account = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Restore an item from recycle bin"""
    
    # Find bin item
    bin_item = db.query(RecycleBin).filter(
        and_(
            RecycleBin.bin_id == request.bin_id,
            RecycleBin.account_id == current_user.account_id,
            RecycleBin.is_recovered == "FALSE"
        )
    ).first()
    
    if not bin_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bin item not found or already recovered"
        )
    
    # Check if item has expired
    if bin_item.expires_at <= now_utc():
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Item has expired and cannot be recovered"
        )
    
    # Verify the original resource still exists in the database
    if bin_item.resource_type == "FILE":
        resource = db.query(FileObject).filter(
            FileObject.file_id == bin_item.resource_id
        ).first()
        resource_type_name = "file"
    else:  # FOLDER
        resource = db.query(Folder).filter(
            Folder.folder_id == bin_item.resource_id
        ).first()
        resource_type_name = "folder"
    
    if not resource:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=f"Original {resource_type_name} no longer exists and cannot be recovered"
        )
    
    # Mark as recovered
    bin_item.is_recovered = "TRUE"
    bin_item.recovered_at = now_utc()
    bin_item.recovered_by = current_user.account_id
    
    # Log the recovery activity
    log_activity(
        db=db,
        account_id=current_user.account_id,
        action_type=f"{bin_item.resource_type}_RESTORE",
        resource_type=bin_item.resource_type,
        resource_id=bin_item.resource_id,
        details={
            "original_name": bin_item.original_name,
            "original_path": bin_item.original_path,
            "deleted_at": bin_item.deleted_at.isoformat(),
            "days_in_bin": (now_utc() - bin_item.deleted_at).days
        }
    )
    
    db.commit()
    
    return {
        "message": f"{resource_type_name.title()} '{bin_item.original_name}' restored successfully",
        "resource_type": bin_item.resource_type,
        "resource_id": str(bin_item.resource_id),
        "original_name": bin_item.original_name,
        "recovered_at": bin_item.recovered_at
    }

@router.delete("/empty")
async def empty_bin(
    current_user: Account = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Permanently delete all items in recycle bin"""
    
    # Get all non-recovered bin items
    bin_items = db.query(RecycleBin).filter(
        and_(
            RecycleBin.account_id == current_user.account_id,
            RecycleBin.is_recovered == "FALSE"
        )
    ).all()
    
    if not bin_items:
        return {"message": "Recycle bin is already empty", "items_deleted": 0}
    
    items_count = len(bin_items)
    
    # For each item, permanently delete the actual resource
    for bin_item in bin_items:
        try:
            if bin_item.resource_type == "FILE":
                # Delete the actual file record
                file_obj = db.query(FileObject).filter(
                    FileObject.file_id == bin_item.resource_id
                ).first()
                if file_obj:
                    db.delete(file_obj)
            else:  # FOLDER
                # Delete the actual folder record
                folder = db.query(Folder).filter(
                    Folder.folder_id == bin_item.resource_id
                ).first()
                if folder:
                    db.delete(folder)
            
            # Delete the bin item
            db.delete(bin_item)
            
        except Exception as e:
            # Log error but continue with other items
            print(f"Error permanently deleting item {bin_item.bin_id}: {e}")
    
    # Log the empty bin activity
    log_activity(
        db=db,
        account_id=current_user.account_id,
        action_type="BIN_EMPTY",
        resource_type="BIN",
        resource_id=None,
        details={
            "items_deleted": items_count,
            "action": "PERMANENT_DELETE"
        }
    )
    
    db.commit()
    
    return {
        "message": f"Recycle bin emptied. {items_count} items permanently deleted.",
        "items_deleted": items_count
    }

@router.delete("/permanent-delete/{bin_id}")
async def permanent_delete(
    bin_id: str,
    current_user: Account = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Permanently delete a specific item from recycle bin"""
    
    # Find bin item
    bin_item = db.query(RecycleBin).filter(
        and_(
            RecycleBin.bin_id == bin_id,
            RecycleBin.account_id == current_user.account_id,
            RecycleBin.is_recovered == "FALSE"
        )
    ).first()
    
    if not bin_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bin item not found"
        )
    
    # Delete the actual resource
    if bin_item.resource_type == "FILE":
        file_obj = db.query(FileObject).filter(
            FileObject.file_id == bin_item.resource_id
        ).first()
        if file_obj:
            db.delete(file_obj)
        resource_type_name = "file"
    else:  # FOLDER
        folder = db.query(Folder).filter(
            Folder.folder_id == bin_item.resource_id
        ).first()
        if folder:
            db.delete(folder)
        resource_type_name = "folder"
    
    # Log the permanent deletion
    log_activity(
        db=db,
        account_id=current_user.account_id,
        action_type=f"{bin_item.resource_type}_PERMANENT_DELETE",
        resource_type=bin_item.resource_type,
        resource_id=bin_item.resource_id,
        details={
            "original_name": bin_item.original_name,
            "original_path": bin_item.original_path,
            "deleted_at": bin_item.deleted_at.isoformat(),
            "action": "PERMANENT_DELETE"
        }
    )
    
    # Delete bin item
    db.delete(bin_item)
    db.commit()
    
    return {
        "message": f"{resource_type_name.title()} '{bin_item.original_name}' permanently deleted",
        "resource_type": bin_item.resource_type,
        "original_name": bin_item.original_name
    }

# Cleanup job endpoint (for admin or scheduled tasks)
@router.delete("/cleanup-expired")
async def cleanup_expired_items(
    current_user: Account = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Remove expired items from recycle bin (automatic cleanup)"""
    
    # Only allow admins to run this manually, or it could be a scheduled job
    if current_user.account_type != "SYSADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only system administrators can run cleanup"
        )
    
    # Find expired items
    expired_items = db.query(RecycleBin).filter(
        and_(
            RecycleBin.expires_at <= now_utc(),
            RecycleBin.is_recovered == "FALSE"
        )
    ).all()
    
    items_cleaned = 0
    
    for bin_item in expired_items:
        try:
            # Permanently delete the resource
            if bin_item.resource_type == "FILE":
                file_obj = db.query(FileObject).filter(
                    FileObject.file_id == bin_item.resource_id
                ).first()
                if file_obj:
                    db.delete(file_obj)
            else:  # FOLDER
                folder = db.query(Folder).filter(
                    Folder.folder_id == bin_item.resource_id
                ).first()
                if folder:
                    db.delete(folder)
            
            # Delete bin item
            db.delete(bin_item)
            items_cleaned += 1
            
        except Exception as e:
            print(f"Error cleaning up expired item {bin_item.bin_id}: {e}")
    
    # Log cleanup activity
    log_activity(
        db=db,
        account_id=current_user.account_id,
        action_type="BIN_CLEANUP",
        resource_type="SYSTEM",
        resource_id=None,
        details={
            "items_cleaned": items_cleaned,
            "cleanup_type": "EXPIRED_ITEMS",
            "run_by": "ADMIN"
        }
    )
    
    db.commit()
    
    return {
        "message": f"Cleanup completed. {items_cleaned} expired items permanently deleted.",
        "items_cleaned": items_cleaned
    }