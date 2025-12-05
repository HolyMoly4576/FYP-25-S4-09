from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional
import logging

from app.core.security import decode_access_token
from app.routes.login import oauth2_scheme
from app.master_node_db import MasterNodeDB, get_master_db


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
    
    # Query via master node
    account_result = master_db.select(
        "SELECT account_id, username, email, account_type, created_at FROM account WHERE account_id = $1",
        [account_id]
    )
    
    if not account_result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    return account_result[0]  # Returns dict instead of SQLAlchemy Account object



@router.get("/usage", response_model=StorageUsageResponse)
def get_storage_usage(
    current_account: dict = Depends(get_current_account),
    master_db: MasterNodeDB = Depends(get_master_db)
):
    """
    Get storage usage for the current authenticated user.
    Returns used storage, limit, remaining space, and usage percentage.
    """
    try:
        # Calculate used storage via master node
        result = master_db.select(
            "SELECT COALESCE(SUM(file_size), 0) as total FROM file_objects WHERE account_id = $1",
            [str(current_account["account_id"])]
        )
        
        used_bytes = int(result[0]["total"]) if result else 0
        used_gb = used_bytes / (1024 ** 3)
        
        # Get storage limit based on account type
        storage_limit_gb = 0
        monthly_cost = None
        renewal_date = None
        
        if current_account["account_type"] == "FREE":
            # Query free_account table via master node
            free_account = master_db.select(
                "SELECT storage_limit_gb FROM free_account WHERE account_id = $1",
                [current_account["account_id"]]
            )
            
            if free_account:
                storage_limit_gb = free_account[0]["storage_limit_gb"]
            else:
                # Default for free accounts
                storage_limit_gb = 2
        
        elif current_account["account_type"] == "PAID":
            # Query paid_account table via master node
            paid_account = master_db.select(
                "SELECT storage_limit_gb, monthly_cost, renewal_date FROM paid_account WHERE account_id = $1",
                [current_account["account_id"]]
            )
            
            if paid_account:
                storage_limit_gb = paid_account[0]["storage_limit_gb"]
                monthly_cost = float(paid_account[0]["monthly_cost"])
                
                # Handle renewal_date formatting
                renewal_date_value = paid_account[0].get("renewal_date")
                if renewal_date_value:
                    if hasattr(renewal_date_value, "isoformat"):
                        renewal_date = renewal_date_value.isoformat()
                    else:
                        renewal_date = str(renewal_date_value)
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
            account_id=str(current_account["account_id"]),
            account_type=current_account["account_type"],
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
