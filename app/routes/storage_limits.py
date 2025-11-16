from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional
from decimal import Decimal
from datetime import datetime, timedelta, timezone
import logging

from app.db.session import get_db
from app.models import Account, FreeAccount, PaidAccount
from app.core.security import decode_access_token
from app.core.activity_logger import log_activity, get_client_ip, get_user_agent
from app.routes.login import oauth2_scheme

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/storage", tags=["storage"])


class StorageUsageResponse(BaseModel):
    account_id: str
    account_type: str
    used_bytes: int
    used_gb: float
    storage_limit_gb: int
    storage_limit_bytes: int
    remaining_bytes: int
    remaining_gb: float
    usage_percentage: float
    monthly_cost: Optional[float] = None
    renewal_date: Optional[str] = None


class UpdateStorageRequest(BaseModel):
    monthly_cost: float


class UpdateStorageResponse(BaseModel):
    account_id: str
    storage_limit_gb: int
    monthly_cost: float
    renewal_date: str
    message: str


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




@router.get("/usage", response_model=StorageUsageResponse)
def get_storage_usage(
    current_account: Account = Depends(get_current_account),
    db: Session = Depends(get_db)
):
    """
    Get storage usage for the current authenticated user.
    Returns used storage, limit, remaining space, and usage percentage.
    """
    try:
        # Calculate used storage
        result = db.execute(
            text("SELECT COALESCE(SUM(file_size), 0) FROM file_objects WHERE account_id = :account_id"),
            {"account_id": str(current_account.account_id)}
        )
        used_bytes = int(result.scalar() or 0)
        used_gb = used_bytes / (1024 ** 3)
        
        # Get storage limit based on account type
        storage_limit_gb = 0
        monthly_cost = None
        renewal_date = None
        
        if current_account.account_type == "FREE":
            free_account = db.query(FreeAccount).filter(
                FreeAccount.account_id == current_account.account_id
            ).first()
            if free_account:
                storage_limit_gb = free_account.storage_limit_gb
            else:
                # Default for free accounts
                storage_limit_gb = 2
        elif current_account.account_type == "PAID":
            paid_account = db.query(PaidAccount).filter(
                PaidAccount.account_id == current_account.account_id
            ).first()
            if paid_account:
                storage_limit_gb = paid_account.storage_limit_gb
                monthly_cost = float(paid_account.monthly_cost)
                if paid_account.renewal_date:
                    renewal_date = paid_account.renewal_date.isoformat()
            else:
                # Default for paid accounts
                storage_limit_gb = 30
                monthly_cost = 10.00
        else:
            # SYSADMIN or unknown - no limit
            storage_limit_gb = 0
        
        storage_limit_bytes = storage_limit_gb * (1024 ** 3)
        remaining_bytes = max(0, int(storage_limit_bytes) - used_bytes)
        remaining_gb = remaining_bytes / (1024 ** 3)
        usage_percentage = (used_bytes / storage_limit_bytes * 100) if storage_limit_bytes > 0 else 0
        
        return StorageUsageResponse(
            account_id=str(current_account.account_id),
            account_type=current_account.account_type,
            used_bytes=used_bytes,
            used_gb=round(used_gb, 2),
            storage_limit_gb=storage_limit_gb,
            storage_limit_bytes=int(storage_limit_bytes),
            remaining_bytes=remaining_bytes,
            remaining_gb=round(remaining_gb, 2),
            usage_percentage=round(usage_percentage, 2),
            monthly_cost=monthly_cost,
            renewal_date=renewal_date
        )
    except Exception as e:
        logger.error(f"Error getting storage usage: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving storage usage: {str(e)}"
        )


@router.patch("/update", response_model=UpdateStorageResponse)
def update_storage_limit(
    body: UpdateStorageRequest,
    request: Request,
    current_account: Account = Depends(get_current_account),
    db: Session = Depends(get_db)
):
    """
    Update storage limit for paid accounts based on monthly cost.
    Formula: storage_limit_gb = monthly_cost * 3
    Only available for PAID account types.
    """
    if current_account.account_type != "PAID":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Storage updates are only available for paid accounts"
        )
    
    if body.monthly_cost <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Monthly cost must be greater than 0"
        )
    
    try:
        # Calculate new storage limit: monthly_cost * 3 = GB
        new_storage_limit_gb = int(body.monthly_cost * 3)
        
        # Get or create paid account record
        paid_account = db.query(PaidAccount).filter(
            PaidAccount.account_id == current_account.account_id
        ).first()
        
        # Calculate renewal date (1 month from now, or from start_date if updating existing)
        now = datetime.now(timezone.utc)
        if not paid_account:
            # Create new paid account record
            start_date = now
            renewal_date = now + timedelta(days=30)  # 1 month from now
            paid_account = PaidAccount(
                account_id=current_account.account_id,
                storage_limit_gb=new_storage_limit_gb,
                monthly_cost=Decimal(str(body.monthly_cost)),
                start_date=start_date,
                renewal_date=renewal_date,
                status="ACTIVE"
            )
            db.add(paid_account)
        else:
            # Update existing record
            # If this is a plan change, reset renewal date to 1 month from now
            # Otherwise, keep existing renewal_date
            paid_account.storage_limit_gb = new_storage_limit_gb
            paid_account.monthly_cost = Decimal(str(body.monthly_cost))
            paid_account.status = "ACTIVE"
            # Update renewal date to 1 month from now (plan change)
            paid_account.renewal_date = datetime.now(timezone.utc) + timedelta(days=30)
        
        db.commit()
        db.refresh(paid_account)
        
        # Log storage update activity
        log_activity(
            db=db,
            account_id=current_account.account_id,
            action_type="STORAGE_UPDATE",
            resource_type="ACCOUNT",
            resource_id=current_account.account_id,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
            details={
                "storage_limit_gb": paid_account.storage_limit_gb,
                "monthly_cost": float(paid_account.monthly_cost),
                "renewal_date": paid_account.renewal_date.isoformat()
            }
        )
        
        return UpdateStorageResponse(
            account_id=str(current_account.account_id),
            storage_limit_gb=paid_account.storage_limit_gb,
            monthly_cost=float(paid_account.monthly_cost),
            renewal_date=paid_account.renewal_date.isoformat(),
            message=f"Storage limit updated to {paid_account.storage_limit_gb}GB for ${body.monthly_cost}/month. Renewal date: {paid_account.renewal_date.strftime('%Y-%m-%d')}"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating storage limit: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating storage limit: {str(e)}"
        )

