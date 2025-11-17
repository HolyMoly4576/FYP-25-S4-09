from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional
import traceback
import logging

from app.db.session import get_db
from app.models import Account, FreeAccount
from app.core.security import verify_password, get_password_hash, create_access_token
from app.core.activity_logger import log_activity, get_client_ip, get_user_agent
import uuid

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])
oauth2_scheme = HTTPBearer()


class LoginRequest(BaseModel):
	username_or_email: str
	password: str
	selected_role: Optional[str] = None  # "USER" or "SYSADMIN" - used for validation


class RegisterRequest(BaseModel):
	username: str
	email: EmailStr
	password: str
	# account_type removed - all new accounts are FREE by default


class TokenResponse(BaseModel):
	access_token: str
	token_type: str = "bearer"
	account_id: str
	username: str
	account_type: str


class UserResponse(BaseModel):
	account_id: str
	username: str
	email: str
	account_type: str
	created_at: str


def get_account_by_username_or_email(db: Session, username_or_email: str) -> Optional[Account]:
	"""Get account by username or email."""
	account = db.query(Account).filter(
		(Account.username == username_or_email) | (Account.email == username_or_email)
	).first()
	return account


@router.post("/login", response_model=TokenResponse)
def login(login_data: LoginRequest, request: Request, db: Session = Depends(get_db)):
	"""
	Login endpoint. Accepts username/email and password.
	Returns JWT access token on successful authentication.
	"""
	try:
		# Find account by username or email
		account = get_account_by_username_or_email(db, login_data.username_or_email)
		
		if not account:
			raise HTTPException(
				status_code=status.HTTP_401_UNAUTHORIZED,
				detail="Incorrect username/email or password",
			)
		
		# Verify password
		if not verify_password(login_data.password, account.password_hash):
			raise HTTPException(
				status_code=status.HTTP_401_UNAUTHORIZED,
				detail="Incorrect username/email or password",
			)
		
		# Ensure account_type has a value (default to 'FREE' if None)
		account_type = account.account_type if account.account_type else "FREE"
		
		# Validate selected_role against actual account type
		# If selected_role is provided, validate it matches the account
		if login_data.selected_role:
			selected_role = login_data.selected_role.upper()
			
			# SYSADMIN accounts can only login with SYSADMIN role
			if account_type == "SYSADMIN":
				if selected_role != "SYSADMIN":
					raise HTTPException(
						status_code=status.HTTP_403_FORBIDDEN,
						detail="SYSADMIN accounts must login with SYSADMIN role",
					)
			# FREE and PAID accounts can only login with USER role
			elif account_type in ["FREE", "PAID"]:
				if selected_role != "USER":
					raise HTTPException(
						status_code=status.HTTP_403_FORBIDDEN,
						detail="Regular users must login with USER role",
					)
		
		# Create access token
		access_token = create_access_token(
			data={"sub": str(account.account_id), "username": account.username}
		)
		
		# Log login activity
		log_activity(
			db=db,
			account_id=account.account_id,
			action_type="LOGIN",
			resource_type="ACCOUNT",
			resource_id=account.account_id,
			ip_address=get_client_ip(request),
			user_agent=get_user_agent(request),
			details={"username": account.username, "account_type": account_type}
		)
		
		return TokenResponse(
			access_token=access_token,
			token_type="bearer",
			account_id=str(account.account_id),
			username=account.username,
			account_type=account_type,
		)
	except HTTPException:
		# Re-raise HTTP exceptions as-is
		raise
	except Exception as e:
		# Log the full error for debugging
		logger.error(f"Login error: {str(e)}")
		logger.error(traceback.format_exc())
		# Return more detailed error in development
		error_detail = str(e)
		if hasattr(e, '__traceback__'):
			error_detail += f"\n{traceback.format_exc()}"
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=f"Internal server error: {error_detail}",
		)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(register_data: RegisterRequest, db: Session = Depends(get_db)):
	"""
	Registration endpoint. Creates a new FREE account.
	All new accounts are created as FREE by default.
	Users can upgrade to PAID later using the upgrade endpoint.
	"""
	try:
		# Check if username already exists
		existing_username = db.query(Account).filter(Account.username == register_data.username).first()
		if existing_username:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="Username already taken",
			)
		
		# Check if email already exists
		existing_email = db.query(Account).filter(Account.email == register_data.email).first()
		if existing_email:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="Email already registered",
			)
		
		# Create new account - always FREE
		hashed_password = get_password_hash(register_data.password)
		new_account = Account(
			account_id=uuid.uuid4(),
			username=register_data.username,
			email=register_data.email,
			password_hash=hashed_password,
			account_type="FREE",  # Always FREE for new registrations
		)
		
		db.add(new_account)
		db.flush()  # Flush to get the account_id
		
		# Create FreeAccount record with default 2GB storage
		free_account = FreeAccount(
			account_id=new_account.account_id,
			storage_limit_gb=2  # Default 2GB for free accounts
		)
		db.add(free_account)
		db.commit()
		db.refresh(new_account)
		
		return UserResponse(
			account_id=str(new_account.account_id),
			username=new_account.username,
			email=new_account.email,
			account_type=new_account.account_type,
			created_at=new_account.created_at.isoformat(),
		)
	except HTTPException:
		raise
	except Exception as e:
		db.rollback()
		logger.error(f"Registration error: {str(e)}")
		logger.error(traceback.format_exc())
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=f"Error creating account: {str(e)}",
		)


@router.get("/me", response_model=UserResponse)
def get_current_user(
    token = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """
    Get current authenticated user information.
    """
    from app.core.security import decode_access_token

    try:
        # ✅ Extract the raw token string from the HTTPAuthorizationCredentials object
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

        return UserResponse(
            account_id=str(account.account_id),
            username=account.username,
            email=account.email,
            account_type=account.account_type,
            created_at=account.created_at.isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in /auth/me: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )
