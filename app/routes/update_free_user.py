from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional
import traceback
import logging

from app.db.session import get_db
from app.models import Account
from app.core.security import verify_password, get_password_hash, decode_access_token
from app.core.activity_logger import log_activity, get_client_ip, get_user_agent
from app.routes.login import oauth2_scheme  # using HTTPBearer now

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
# Helper - get current account
# -----------------------------
def get_current_account(
    token=Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> Account:
    """
    Get the current authenticated account from the JWT token.
    Handles HTTPBearer or string tokens safely.
    """
    try:
        # ✅ Extract raw JWT string from HTTPBearer token
        token_str = token.credentials if hasattr(token, "credentials") else token

        payload = decode_access_token(token_str)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
            )

        account_id = payload.get("sub")
        if not account_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
            )

        account = db.query(Account).filter(Account.account_id == account_id).first()
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        return account

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_current_account: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        )


# -----------------------------
# Update Profile
# -----------------------------
@router.put("/profile", response_model=UpdateUserResponse)
def update_profile(
    profile_data: UpdateProfileRequest,
    request: Request,
    current_account: Account = Depends(get_current_account),
    db: Session = Depends(get_db)
):
    """
    Update user profile information (username and/or email).
    Requires authentication.
    """
    try:
        updated_fields = []

        # Update username if provided
        if profile_data.username is not None:
            if profile_data.username.strip() == "":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Username cannot be empty",
                )
            if profile_data.username != current_account.username:
                existing_username = db.query(Account).filter(
                    Account.username == profile_data.username,
                    Account.account_id != current_account.account_id
                ).first()
                if existing_username:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Username already taken",
                    )
                current_account.username = profile_data.username
                updated_fields.append("username")

        # Update email if provided
        if profile_data.email is not None:
            if profile_data.email != current_account.email:
                existing_email = db.query(Account).filter(
                    Account.email == profile_data.email,
                    Account.account_id != current_account.account_id
                ).first()
                if existing_email:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Email already registered",
                    )
                current_account.email = profile_data.email.lower()
                updated_fields.append("email")

        if not updated_fields:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields to update",
            )

        db.commit()
        db.refresh(current_account)

        # Log profile update activity
        log_activity(
            db=db,
            account_id=current_account.account_id,
            action_type="PROFILE_UPDATE",
            resource_type="ACCOUNT",
            resource_id=current_account.account_id,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
            details={"updated_fields": updated_fields}
        )

        return UpdateUserResponse(
            account_id=str(current_account.account_id),
            username=current_account.username,
            email=current_account.email,
            account_type=current_account.account_type,
            created_at=current_account.created_at.isoformat(),
            message=f"Profile updated successfully: {', '.join(updated_fields)}",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Profile update error: {str(e)}")
        logger.error(traceback.format_exc())
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        )


# -----------------------------
# Update Password
# -----------------------------
@router.put("/password", response_model=UpdateUserResponse)
def update_password(
    password_data: UpdatePasswordRequest,
    request: Request,
    current_account: Account = Depends(get_current_account),
    db: Session = Depends(get_db)
):
    """
    Update user password.
    Requires authentication and verification of old password.
    """
    try:
        # Verify old password
        if not verify_password(password_data.old_password, current_account.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect old password",
            )

        # Check if new password is different from old password
        if verify_password(password_data.new_password, current_account.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password must be different from old password",
            )

        # Validate new password length (minimum 6 characters)
        if len(password_data.new_password) < 6:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password must be at least 6 characters long",
            )

        current_account.password_hash = get_password_hash(password_data.new_password)
        db.commit()
        db.refresh(current_account)

        # Log password change activity
        log_activity(
            db=db,
            account_id=current_account.account_id,
            action_type="PASSWORD_CHANGE",
            resource_type="ACCOUNT",
            resource_id=current_account.account_id,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
            details={}
        )

        return UpdateUserResponse(
            account_id=str(current_account.account_id),
            username=current_account.username,
            email=current_account.email,
            account_type=current_account.account_type,
            created_at=current_account.created_at.isoformat(),
            message="Password updated successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Password update error: {str(e)}")
        logger.error(traceback.format_exc())
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        )
