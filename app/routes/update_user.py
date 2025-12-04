from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional
import traceback
import logging

from app.db.session import get_db
from app.models import Account
from app.core.security import verify_password, get_password_hash, decode_access_token
from app.routes.login import oauth2_scheme

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user", tags=["user management"])


# -----------------------------
# Pydantic Schemas
# -----------------------------
class UpdateProfileRequest(BaseModel):
    """Request model for updating user profile."""
    username: Optional[str] = None
    email: Optional[EmailStr] = None


class UpdatePasswordRequest(BaseModel):
    """Request model for updating password."""
    old_password: str
    new_password: str


class UpdateUserResponse(BaseModel):
    """Response model for updated user information."""
    account_id: str
    username: str
    email: str
    account_type: str
    created_at: str
    message: str


# -----------------------------
# Helper - get current account from database
# -----------------------------
def get_current_account_from_db(token: str, db: Session):
    """Get account info from database via SQLAlchemy."""
    try:
        # Decode token to get account_id and username
        payload = decode_access_token(token)
        if not payload:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        
        account_id = payload.get("sub")  # account_id is stored in sub
        username = payload.get("username")  # username is in username field
        
        if not account_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        
        # Query database for account info using account_id
        account = db.query(Account).filter(Account.account_id == account_id).first()
        
        if not account:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
        
        return account
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting account from database: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")


def get_current_account(token=Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """Get the current authenticated account from database."""
    token_str = token.credentials if hasattr(token, "credentials") else token
    return get_current_account_from_db(token_str, db)


# -----------------------------
# Update Profile
# -----------------------------
@router.put("/profile", response_model=UpdateUserResponse)
async def update_profile(
    update_data: UpdateProfileRequest,
    request: Request,
    current_account: Account = Depends(get_current_account),
    db: Session = Depends(get_db)
):
    """
    Update user profile information.
    Allows updating username and/or email.
    """
    try:
        logger.info(f"Profile update request for account {current_account.account_id}")
        
        # Check if there's anything to update
        if not update_data.username and not update_data.email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="At least one field (username or email) must be provided"
            )
        
        updates_made = []
        
        # Update username if provided
        if update_data.username:
            if update_data.username != current_account.username:
                # Check if username is already taken
                existing_account = db.query(Account).filter(
                    Account.username == update_data.username,
                    Account.account_id != current_account.account_id
                ).first()
                
                if existing_account:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Username is already taken"
                    )
                
                current_account.username = update_data.username
                updates_made.append("username")
                logger.info(f"Username updated for account {current_account.account_id}")
        
        # Update email if provided
        if update_data.email:
            if update_data.email != current_account.email:
                # Check if email is already taken
                existing_account = db.query(Account).filter(
                    Account.email == update_data.email,
                    Account.account_id != current_account.account_id
                ).first()
                
                if existing_account:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Email is already registered"
                    )
                
                current_account.email = update_data.email
                updates_made.append("email")
                logger.info(f"Email updated for account {current_account.account_id}")
        
        # Commit changes if any updates were made
        if updates_made:
            db.commit()
            db.refresh(current_account)
            
            # Log the activity
            client_ip = request.client.host if request.client else "unknown"
            user_agent = request.headers.get("user-agent", "unknown")
            
            message = f"Profile updated successfully. Updated fields: {', '.join(updates_made)}"
            logger.info(f"Profile update completed for account {current_account.account_id}")
        else:
            message = "No changes were made to the profile"
        
        return UpdateUserResponse(
            account_id=str(current_account.account_id),
            username=current_account.username,
            email=current_account.email,
            account_type=current_account.account_type,
            created_at=current_account.created_at.isoformat(),
            message=message
        )
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating profile for account {current_account.account_id}: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update profile"
        )


# -----------------------------
# Update Password
# -----------------------------
@router.put("/password")
async def update_password(
    password_data: UpdatePasswordRequest,
    request: Request,
    current_account: Account = Depends(get_current_account),
    db: Session = Depends(get_db)
):
    """
    Update user password.
    Requires current password verification.
    """
    try:
        logger.info(f"Password update request for account {current_account.account_id}")
        
        # Verify current password
        if not verify_password(password_data.old_password, current_account.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Incorrect current password"
            )
        
        # Validate new password
        if len(password_data.new_password) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password must be at least 8 characters long"
            )
        
        if password_data.new_password == password_data.old_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password must be different from current password"
            )
        
        # Update password
        current_account.password_hash = get_password_hash(password_data.new_password)
        db.commit()
        db.refresh(current_account)
        
        # Log the activity
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        
        logger.info(f"Password updated successfully for account {current_account.account_id}")
        
        return {
            "message": "Password updated successfully",
            "account_id": str(current_account.account_id)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating password for account {current_account.account_id}: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update password"
        )

