from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from decimal import Decimal
from datetime import datetime, timedelta, timezone
import logging
from app.core.security import decode_access_token
from app.routes.login import oauth2_scheme
from app.master_node_db import MasterNodeDB, get_master_db
import uuid
import json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/account", tags=["account management"])

class UpgradeAccountRequest(BaseModel):
    monthly_cost: float

class DowngradeAccountRequest(BaseModel):
    confirm: bool = True

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
        "SELECT account_id, username, email, account_type, created_at FROM account WHERE account_id = $1",
        [account_id]
    )
    
    if not account_result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    result = account_result[0]
    # Convert datetime objects to ISO strings and ensure account_id is a string
    for k, v in result.items():
        if isinstance(v, datetime):
            result[k] = v.isoformat()
        elif k == "account_id":
            result[k] = str(v)
    
    return result

def _json_default_serializer(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    return str(obj)

def safe_json_dumps(data: dict) -> str:
    return json.dumps(data, default=_json_default_serializer)

@router.post("/upgrade", response_model=UpgradeAccountResponse)
def upgrade_to_paid(
    body: UpgradeAccountRequest,
    request: Request,
    current_account: dict = Depends(get_current_account),
    master_db: MasterNodeDB = Depends(get_master_db)
):
    if body.monthly_cost <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Monthly cost must be greater than 0"
        )
    
    if body.monthly_cost < 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Minimum monthly cost is $10"
        )
    
    try:
        storage_limit_gb = int(body.monthly_cost * 3)
        message = ""
        now = datetime.now(timezone.utc)
        renewal_date = now + timedelta(days=30)
        
        # Convert datetime to ISO strings for JSON serialization
        now_iso = now.isoformat()
        renewal_date_iso = renewal_date.isoformat()
        
        # Ensure account_id is a string
        account_id = str(current_account["account_id"])
        
        account_type = current_account["account_type"].upper() if current_account.get("account_type") else "FREE"
        
        if account_type == "FREE":
            master_db.execute(
                "UPDATE account SET account_type = $1 WHERE account_id = $2",
                ["PAID", account_id]
            )
            
            master_db.execute(
                "DELETE FROM free_account WHERE account_id = $1",
                [account_id]
            )
            
            master_db.execute(
                """
                INSERT INTO paid_account (account_id, storage_limit_gb, monthly_cost, start_date, renewal_date, status)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                [account_id, storage_limit_gb, body.monthly_cost, now_iso, renewal_date_iso, "ACTIVE"]
            )
            
            try:
                client_ip = request.client.host if request.client else "unknown"
                user_agent = request.headers.get("user-agent", "unknown")
                
                details = safe_json_dumps({
                    "from": "FREE",
                    "to": "PAID",
                    "monthly_cost": float(body.monthly_cost),
                    "storage_limit_gb": int(storage_limit_gb),
                    "renewal_date": renewal_date
                })
                
                master_db.execute(
                    """
                    INSERT INTO activity_log (activity_id, account_id, action_type, resource_type, resource_id, ip_address, user_agent, details, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
                    """,
                    [str(uuid.uuid4()), account_id, "ACCOUNT_UPGRADE", "ACCOUNT",
                     account_id, client_ip, user_agent, details]
                )
            except Exception as log_error:
                logger.warning(f"Failed to log upgrade activity: {str(log_error)}")
            
            message = f"Account upgraded to PAID! You now have {storage_limit_gb}GB storage for ${body.monthly_cost}/month. Renewal date: {renewal_date.strftime('%Y-%m-%d')}"
        
        elif account_type == "PAID":
            paid_account = master_db.select(
                "SELECT storage_limit_gb, monthly_cost FROM paid_account WHERE account_id = $1",
                [account_id]
            )
            
            if not paid_account or len(paid_account) == 0:
                logger.warning(f"Account {account_id} has type PAID but no paid_account record. Creating record.")
                
                master_db.execute(
                    """
                    INSERT INTO paid_account (account_id, storage_limit_gb, monthly_cost, start_date, renewal_date, status)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    [account_id, storage_limit_gb, body.monthly_cost, now_iso, renewal_date_iso, "ACTIVE"]
                )
                
                message = f"Payment plan created! You now have {storage_limit_gb}GB storage for ${body.monthly_cost}/month. Renewal date: {renewal_date.strftime('%Y-%m-%d')}"
            else:
                old_monthly_cost = paid_account[0]["monthly_cost"]
                old_storage_limit = paid_account[0]["storage_limit_gb"]
                
                master_db.execute(
                    """
                    UPDATE paid_account
                    SET monthly_cost = $1, storage_limit_gb = $2, renewal_date = $3, status = $4
                    WHERE account_id = $5
                    """,
                    [body.monthly_cost, storage_limit_gb, renewal_date_iso, "ACTIVE", account_id]
                )
                
                try:
                    client_ip = request.client.host if request.client else "unknown"
                    user_agent = request.headers.get("user-agent", "unknown")
                    
                    details = safe_json_dumps({
                        "old_monthly_cost": float(old_monthly_cost),
                        "new_monthly_cost": float(body.monthly_cost),
                        "old_storage_limit_gb": int(old_storage_limit),
                        "new_storage_limit_gb": int(storage_limit_gb),
                        "renewal_date": renewal_date
                    })
                    
                    master_db.execute(
                        """
                        INSERT INTO activity_log (activity_id, account_id, action_type, resource_type, resource_id, ip_address, user_agent, details, created_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
                        """,
                        [str(uuid.uuid4()), account_id, "PAYMENT_PLAN_UPDATE", "ACCOUNT",
                         account_id, client_ip, user_agent, details]
                    )
                except Exception as log_error:
                    logger.warning(f"Failed to log plan update activity: {str(log_error)}")
                
                message = f"Payment plan updated! You now have {storage_limit_gb}GB storage for ${body.monthly_cost}/month. Renewal date: {renewal_date.strftime('%Y-%m-%d')}"
        
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot upgrade {account_type} accounts"
            )
        
        return UpgradeAccountResponse(
            account_id=account_id,
            account_type="PAID",
            storage_limit_gb=storage_limit_gb,
            monthly_cost=body.monthly_cost,
            renewal_date=renewal_date_iso,
            message=message
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error upgrading account: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        # Provide safe error message without exposing non-serializable objects
        error_msg = str(e) if e and isinstance(str(e), str) else "Unknown error"
        # Limit error message length to avoid issues
        if len(error_msg) > 200:
            error_msg = error_msg[:200] + "..."
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error upgrading account: {error_msg}"
        )


@router.post("/downgrade", response_model=DowngradeAccountResponse)
def downgrade_to_free(
    body: DowngradeAccountRequest,
    request: Request,
    current_account: dict = Depends(get_current_account),
    master_db: MasterNodeDB = Depends(get_master_db)
):
    if current_account["account_type"] != "PAID":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only PAID accounts can downgrade. Your account is currently {current_account['account_type']}."
        )
    
    if not body.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Downgrade requires confirmation. Set 'confirm' to true."
        )
    
    try:
        # Ensure account_id is a string
        account_id = str(current_account["account_id"])
        
        paid_account = master_db.select(
            "SELECT storage_limit_gb, monthly_cost FROM paid_account WHERE account_id = $1",
            [account_id]
        )
        
        old_monthly_cost = float(paid_account[0]["monthly_cost"]) if paid_account else None
        old_storage_limit = paid_account[0]["storage_limit_gb"] if paid_account else None
        
        master_db.execute(
            "UPDATE account SET account_type = $1 WHERE account_id = $2",
            ["FREE", account_id]
        )
        
        master_db.execute(
            "DELETE FROM paid_account WHERE account_id = $1",
            [account_id]
        )
        
        master_db.execute(
            "INSERT INTO free_account (account_id, storage_limit_gb) VALUES ($1, $2)",
            [account_id, 2]
        )
        
        try:
            client_ip = request.client.host if request.client else "unknown"
            user_agent = request.headers.get("user-agent", "unknown")
            
            details = safe_json_dumps({
                "from": "PAID",
                "to": "FREE",
                "old_monthly_cost": float(old_monthly_cost) if old_monthly_cost else None,
                "old_storage_limit_gb": old_storage_limit,
                "new_storage_limit_gb": 2
            })
            
            master_db.execute(
                """
                INSERT INTO activity_log (activity_id, account_id, action_type, resource_type, resource_id, ip_address, user_agent, details, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
                """,
                [str(uuid.uuid4()), account_id, "ACCOUNT_DOWNGRADE", "ACCOUNT",
                 account_id, client_ip, user_agent, details]
            )
        except Exception as log_error:
            logger.warning(f"Failed to log downgrade activity: {str(log_error)}")
        
        return DowngradeAccountResponse(
            account_id=account_id,
            account_type="FREE",
            storage_limit_gb=2,
            message="Account downgraded to FREE. Your storage limit is now 2GB. You can upgrade again anytime."
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downgrading account: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error downgrading account: {str(e)}"
        )
