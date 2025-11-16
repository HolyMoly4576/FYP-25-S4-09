from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
import logging

from app.db.session import get_db
from app.models import Account
from app.core.security import get_password_hash, verify_password
from app.core.activity_logger import log_activity, get_client_ip, get_user_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    message: str
    email_verified: bool


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    new_password: str


class ResetPasswordResponse(BaseModel):
    message: str


def get_account_by_email(db: Session, email: str):
    """Get account by email."""
    return db.query(Account).filter(Account.email == email.lower()).first()


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(
    body: ForgotPasswordRequest,
    db: Session = Depends(get_db)
):
    """
    Verify email for password reset (Alpha version).
    For alpha release: just verifies if email exists.
    For beta release: will send password reset link via email.
    """
    try:
        # Normalize email to lowercase
        email_lower = body.email.lower()
        
        # Check if account exists with this email
        account = get_account_by_email(db, email_lower)
        
        if account:
            # Email exists - verified
            # TODO: In beta release, generate token and send email here
            logger.info(f"Password reset requested for email: {email_lower}")
            return ForgotPasswordResponse(
                message="Email verified. You can now reset your password.",
                email_verified=True
            )
        else:
            # Email doesn't exist
            return ForgotPasswordResponse(
                message="Email not found in our system.",
                email_verified=False
            )
    except Exception as e:
        logger.error(f"Error in forgot password: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing password reset request"
        )


@router.post("/reset-password", response_model=ResetPasswordResponse)
def reset_password(
    body: ResetPasswordRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Reset password after email verification (Alpha version).
    Requires email and new password.
    For beta release: will require token instead of email.
    """
    try:
        # Normalize email to lowercase
        email_lower = body.email.lower()
        
        # Validate password
        if not body.new_password or len(body.new_password) < 6:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password must be at least 6 characters long"
            )
        
        # Find account by email
        account = get_account_by_email(db, email_lower)
        
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account not found"
            )
        
        # Check if new password is different from current
        if verify_password(body.new_password, account.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password must be different from current password"
            )
        
        # Update password
        account.password_hash = get_password_hash(body.new_password)
        db.commit()
        db.refresh(account)
        
        # Log password reset activity
        log_activity(
            db=db,
            account_id=account.account_id,
            action_type="PASSWORD_RESET",
            resource_type="ACCOUNT",
            resource_id=account.account_id,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
            details={"method": "email_verification"}  # Alpha version
        )
        
        logger.info(f"Password reset successful for account: {account.account_id}")
        
        return ResetPasswordResponse(
            message="Password has been successfully reset. You can now login with your new password."
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error resetting password: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error resetting password"
        )

