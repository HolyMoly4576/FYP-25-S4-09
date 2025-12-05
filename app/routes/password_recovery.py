from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, EmailStr
import logging

from app.core.security import get_password_hash, verify_password
from app.master_node_db import MasterNodeDB, get_master_db
import uuid

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


def get_account_by_email(master_db: MasterNodeDB, email: str):
    """Get account by email via master node."""
    result = master_db.select(
        "SELECT account_id, username, email, password_hash, account_type, created_at FROM account WHERE LOWER(email) = LOWER($1)",
        [email]
    )
    return result[0] if result else None


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(
    body: ForgotPasswordRequest,
    master_db: MasterNodeDB = Depends(get_master_db)
):
    """
    Verify email for password reset (Alpha version).
    For alpha release: just verifies if email exists.
    For beta release: will send password reset link via email.
    """
    try:
        email_lower = body.email.lower()
        
        # Check if account exists with this email via master node
        account = get_account_by_email(master_db, email_lower)
        
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
    master_db: MasterNodeDB = Depends(get_master_db)
):
    """
    Reset password after email verification (Alpha version).
    Requires email and new password.
    For beta release: will require token instead of email.
    """
    try:
        email_lower = body.email.lower()
        
        # Validate password
        if not body.new_password or len(body.new_password) < 6:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password must be at least 6 characters long"
            )
        
        # Find account by email via master node
        account = get_account_by_email(master_db, email_lower)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account not found"
            )
        
        # Check if new password is different from current
        if verify_password(body.new_password, account["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password must be different from current password"
            )
        
        # Update password via master node
        new_password_hash = get_password_hash(body.new_password)
        master_db.execute(
            "UPDATE account SET password_hash = $1 WHERE account_id = $2",
            [new_password_hash, account["account_id"]]
        )
        
        # Log password reset activity via master node
        try:
            client_ip = request.client.host if request.client else "unknown"
            user_agent = request.headers.get("user-agent", "unknown")
            
            master_db.execute(
                """
                INSERT INTO activity_log (activity_id, account_id, action_type, resource_type, resource_id, ip_address, user_agent, details, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
                """,
                [
                    str(uuid.uuid4()),
                    str(account["account_id"]),
                    "PASSWORD_RESET",
                    "ACCOUNT",
                    str(account["account_id"]),
                    client_ip,
                    user_agent,
                    '{"method": "email_verification"}'
                ]
            )
        except Exception as log_error:
            # Don't fail the password reset if activity logging fails
            logger.warning(f"Failed to log password reset activity: {str(log_error)}")
        
        logger.info(f"Password reset successful for account: {account['account_id']}")
        return ResetPasswordResponse(
            message="Password has been successfully reset. You can now login with your new password."
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resetting password: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error resetting password"
        )
