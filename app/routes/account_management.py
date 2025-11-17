from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from decimal import Decimal
from datetime import datetime, timedelta, timezone
import logging

from app.db.session import get_db
from app.models import Account, FreeAccount, PaidAccount
from app.core.security import decode_access_token
from app.core.activity_logger import log_activity, get_client_ip, get_user_agent
from app.routes.login import oauth2_scheme

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/account", tags=["account management"])


class UpgradeAccountRequest(BaseModel):
    monthly_cost: float  # User chooses how much they want to pay per month


class DowngradeAccountRequest(BaseModel):
    confirm: bool = True  # Confirmation flag for downgrade


class UpgradeAccountResponse(BaseModel):
    account_id: str
    account_type: str
    storage_limit_gb: int
    monthly_cost: float
    renewal_date: str
    message: str


class DowngradeAccountResponse(BaseModel):
    account_id: str
    account_type: str
    storage_limit_gb: int
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


@router.post("/upgrade", response_model=UpgradeAccountResponse)
def upgrade_to_paid(
    body: UpgradeAccountRequest,
    request: Request,
    current_account: Account = Depends(get_current_account),
    db: Session = Depends(get_db)
):
    """
    Upgrade a FREE account to PAID, or update payment plan for existing PAID accounts.
    User can choose their monthly cost, which determines storage limit.
    Formula: storage_limit_gb = monthly_cost * 3
    
    For FREE accounts, this will:
    1. Change account_type from FREE to PAID
    2. Delete the FreeAccount record
    3. Create a PaidAccount record with chosen monthly_cost
    
    For PAID accounts, this will:
    1. Update the existing PaidAccount record with new monthly_cost
    2. Recalculate storage_limit_gb based on new monthly_cost
    3. Reset renewal_date to 30 days from now
    """
    # Validate monthly_cost
    if body.monthly_cost <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Monthly cost must be greater than 0"
        )
    
    # Minimum monthly cost
    if body.monthly_cost < 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Minimum monthly cost is $10"
        )
    
    try:
        # Calculate storage limit: monthly_cost * 3 = GB
        storage_limit_gb = int(body.monthly_cost * 3)
        paid_account = None
        message = ""
        
        if current_account.account_type == "FREE":
            # FREE account upgrading to PAID
            # Get FreeAccount record (should exist for FREE accounts)
            free_account = db.query(FreeAccount).filter(
                FreeAccount.account_id == current_account.account_id
            ).first()
            
            # Update account type to PAID
            current_account.account_type = "PAID"
            
            # Delete FreeAccount record if it exists
            if free_account:
                db.delete(free_account)
            
            # Create PaidAccount record
            now = datetime.now(timezone.utc)
            renewal_date = now + timedelta(days=30)  # 1 month from now
            
            paid_account = PaidAccount(
                account_id=current_account.account_id,
                storage_limit_gb=storage_limit_gb,
                monthly_cost=Decimal(str(body.monthly_cost)),
                start_date=now,
                renewal_date=renewal_date,
                status="ACTIVE"
            )
            db.add(paid_account)
            
            # Log upgrade activity
            log_activity(
                db=db,
                account_id=current_account.account_id,
                action_type="ACCOUNT_UPGRADE",
                resource_type="ACCOUNT",
                resource_id=current_account.account_id,
                ip_address=get_client_ip(request),
                user_agent=get_user_agent(request),
                details={
                    "from": "FREE",
                    "to": "PAID",
                    "monthly_cost": body.monthly_cost,
                    "storage_limit_gb": storage_limit_gb,
                    "renewal_date": renewal_date.isoformat()
                }
            )
            
            message = f"Account upgraded to PAID! You now have {storage_limit_gb}GB storage for ${body.monthly_cost}/month. Renewal date: {renewal_date.strftime('%Y-%m-%d')}"
            
        elif current_account.account_type == "PAID":
            # PAID account updating payment plan
            paid_account = db.query(PaidAccount).filter(
                PaidAccount.account_id == current_account.account_id
            ).first()
            
            if not paid_account:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="PaidAccount record not found"
                )
            
            # Store old values for logging
            old_monthly_cost = float(paid_account.monthly_cost)
            old_storage_limit = paid_account.storage_limit_gb
            
            # Update payment plan
            now = datetime.now(timezone.utc)
            paid_account.monthly_cost = Decimal(str(body.monthly_cost))
            paid_account.storage_limit_gb = storage_limit_gb
            paid_account.renewal_date = now + timedelta(days=30)  # Reset renewal date
            paid_account.status = "ACTIVE"
            
            # Log plan update activity
            log_activity(
                db=db,
                account_id=current_account.account_id,
                action_type="PAYMENT_PLAN_UPDATE",
                resource_type="ACCOUNT",
                resource_id=current_account.account_id,
                ip_address=get_client_ip(request),
                user_agent=get_user_agent(request),
                details={
                    "old_monthly_cost": old_monthly_cost,
                    "new_monthly_cost": body.monthly_cost,
                    "old_storage_limit_gb": old_storage_limit,
                    "new_storage_limit_gb": storage_limit_gb,
                    "renewal_date": paid_account.renewal_date.isoformat()
                }
            )
            
            message = f"Payment plan updated! You now have {storage_limit_gb}GB storage for ${body.monthly_cost}/month. Renewal date: {paid_account.renewal_date.strftime('%Y-%m-%d')}"
            
        else:
            # SYSADMIN or other account types
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot upgrade {current_account.account_type} accounts"
            )
        
        db.commit()
        db.refresh(current_account)
        if paid_account:
            db.refresh(paid_account)
        
        return UpgradeAccountResponse(
            account_id=str(current_account.account_id),
            account_type=current_account.account_type,
            storage_limit_gb=storage_limit_gb,
            monthly_cost=body.monthly_cost,
            renewal_date=paid_account.renewal_date.isoformat() if paid_account else "",
            message=message
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error upgrading account: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error upgrading account: {str(e)}"
        )


@router.post("/downgrade", response_model=DowngradeAccountResponse)
def downgrade_to_free(
    body: DowngradeAccountRequest,
    request: Request,
    current_account: Account = Depends(get_current_account),
    db: Session = Depends(get_db)
):
    """
    Downgrade a PAID account to FREE.
    User will lose paid features and storage will be reduced to 2GB (free tier).
    
    This will:
    1. Change account_type from PAID to FREE
    2. Delete the PaidAccount record
    3. Create a FreeAccount record with 2GB storage limit
    """
    # Only PAID accounts can downgrade
    if current_account.account_type != "PAID":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only PAID accounts can downgrade. Your account is currently {current_account.account_type}."
        )
    
    # Require confirmation
    if not body.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Downgrade requires confirmation. Set 'confirm' to true."
        )
    
    try:
        # Get PaidAccount record (should exist for PAID accounts)
        paid_account = db.query(PaidAccount).filter(
            PaidAccount.account_id == current_account.account_id
        ).first()
        
        # Store old values for logging
        old_monthly_cost = float(paid_account.monthly_cost) if paid_account else None
        old_storage_limit = paid_account.storage_limit_gb if paid_account else None
        
        # Update account type to FREE
        current_account.account_type = "FREE"
        
        # Delete PaidAccount record if it exists
        if paid_account:
            db.delete(paid_account)
        
        # Create FreeAccount record with default 2GB storage
        free_account = FreeAccount(
            account_id=current_account.account_id,
            storage_limit_gb=2  # Default 2GB for free accounts
        )
        db.add(free_account)
        db.commit()
        db.refresh(current_account)
        db.refresh(free_account)
        
        # Log downgrade activity
        log_activity(
            db=db,
            account_id=current_account.account_id,
            action_type="ACCOUNT_DOWNGRADE",
            resource_type="ACCOUNT",
            resource_id=current_account.account_id,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
            details={
                "from": "PAID",
                "to": "FREE",
                "old_monthly_cost": old_monthly_cost,
                "old_storage_limit_gb": old_storage_limit,
                "new_storage_limit_gb": 2
            }
        )
        
        return DowngradeAccountResponse(
            account_id=str(current_account.account_id),
            account_type=current_account.account_type,
            storage_limit_gb=free_account.storage_limit_gb,
            message="Account downgraded to FREE. Your storage limit is now 2GB. You can upgrade again anytime."
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error downgrading account: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error downgrading account: {str(e)}"
        )

