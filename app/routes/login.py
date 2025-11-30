from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional
import traceback
import logging

from app.db.session import get_db, get_master_node_db
from app.models import Account
from app.core.security import verify_password, get_password_hash, create_access_token
from app.master_node_db import MasterNodeDB
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


def get_account_by_username_or_email_master_node(master_db: MasterNodeDB, username_or_email: str) -> Optional[dict]:
	"""Get account by username or email from master node database (PostgreSQL)."""
	try:
		# Query account table in master node database (PostgreSQL)
		query = """
		SELECT account_id, username, email, password_hash, account_type, created_at
		FROM account 
		WHERE username = $1 OR email = $2
		"""
		
		result = master_db.select(query, [username_or_email, username_or_email])
		
		if result:
			return result[0]  # Return first matching user
		return None
	except Exception as e:
		logger.error(f"Error querying master node for user {username_or_email}: {str(e)}")
		logger.error(f"Traceback: {traceback.format_exc()}")
		return None


@router.post("/login", response_model=TokenResponse)
def login(login_data: LoginRequest, master_db: MasterNodeDB = Depends(get_master_node_db)):
	"""
	Login endpoint using master node database (PostgreSQL). Accepts username/email and password.
	Returns JWT access token on successful authentication.
	"""
	try:
		# Find account by username or email from master node (PostgreSQL)
		account = get_account_by_username_or_email_master_node(master_db, login_data.username_or_email)
		
		if not account:
			raise HTTPException(
				status_code=status.HTTP_401_UNAUTHORIZED,
				detail="Incorrect username/email or password",
			)
		
		# Verify password
		if not verify_password(login_data.password, account["password_hash"]):
			raise HTTPException(
				status_code=status.HTTP_401_UNAUTHORIZED,
				detail="Incorrect username/email or password",
			)
		
		# Get account type (default to 'FREE' if None)
		account_type = account.get("account_type", "FREE")
		
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
			data={"sub": account["account_id"], "username": account["username"]}
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
			account_id=account["account_id"],
			username=account["username"],
			account_type=account_type
		)
		
	except HTTPException:
		# Re-raise HTTP exceptions as-is
		raise
	except Exception as e:
		logger.error(f"Login error: {str(e)}")
		logger.error(f"Traceback: {traceback.format_exc()}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Internal server error during login"
		)

# Keep the old login route as backup (commented out)
# @router.post("/login-old", response_model=TokenResponse)
# def login_old(login_data: LoginRequest, db: Session = Depends(get_db)):
#	"""
#	Login endpoint. Accepts username/email and password.
#	Returns JWT access token on successful authentication.
#	"""
#	try:
#		# Find account by username or email
#		account = get_account_by_username_or_email(db, login_data.username_or_email)
#		
#		if not account:
#			raise HTTPException(
#				status_code=status.HTTP_401_UNAUTHORIZED,
#				detail="Incorrect username/email or password",
#			)
#		
#		# Verify password
#		if not verify_password(login_data.password, account.password_hash):
#			raise HTTPException(
#				status_code=status.HTTP_401_UNAUTHORIZED,
#				detail="Incorrect username/email or password",
#			)
#		
#		# Ensure account_type has a value (default to 'FREE' if None)
#		account_type = account.account_type if account.account_type else "FREE"
#		
#		# Create access token
#		access_token = create_access_token(
#			data={"sub": str(account.account_id), "username": account.username}
#		)
#		
#		return TokenResponse(
#			access_token=access_token,
#			token_type="bearer",
#			account_id=str(account.account_id),
#			username=account.username,
#			account_type=account_type,
#		)
#	except HTTPException:
#		# Re-raise HTTP exceptions as-is
#		raise
#	except Exception as e:
#		# Log the full error for debugging
#		logger.error(f"Login error: {str(e)}")
#		logger.error(traceback.format_exc())
#		# Return more detailed error in development
#		error_detail = str(e)
#		if hasattr(e, '__traceback__'):
#			error_detail += f"\n{traceback.format_exc()}"
#		raise HTTPException(
#			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#			detail=f"Internal server error: {error_detail}",
#		)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(register_data: RegisterRequest, master_db: MasterNodeDB = Depends(get_master_node_db)):
    """
    Registration endpoint. Creates a new account through master node (PostgreSQL).
    """
    try:
        # Check if username already exists
        username_check = master_db.select(
            "SELECT account_id FROM account WHERE username = $1",
            [register_data.username]
        )
        if username_check:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken",
            )

        # Check if email already exists
        email_check = master_db.select(
            "SELECT account_id FROM account WHERE email = $1",
            [register_data.email]
        )
        if email_check:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

        # Create new account
        account_id = str(uuid.uuid4())
        hashed_password = get_password_hash(register_data.password)

        # Insert account into database via master node
        master_db.execute(
            """
            INSERT INTO account (account_id, username, email, password_hash, account_type, created_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
            """,
            [account_id, register_data.username, register_data.email, hashed_password, "FREE"]
        )

        # Create account-specific records (FREE only)
        master_db.execute(
            "INSERT INTO free_account (account_id, storage_limit_gb) VALUES ($1, $2)",
            [account_id, 2]
        )

        # Retrieve the created account to return
        account_result = master_db.select(
            """
            SELECT account_id, username, email, account_type, created_at
            FROM account 
            WHERE account_id = $1
            """,
            [account_id]
        )

        if not account_result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve created account",
            )

        account = account_result[0]

        # Format created_at properly
        created_at = account["created_at"]
        if isinstance(created_at, str):
            created_at_str = created_at
        else:
            created_at_str = created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at)

        return UserResponse(
            account_id=account["account_id"],
            username=account["username"],
            email=account["email"],
            account_type=account["account_type"],
            created_at=created_at_str,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error during registration: {str(e)}"
        )


@router.get("/me", response_model=UserResponse)
def get_current_user(
    token = Depends(oauth2_scheme),
    master_db: MasterNodeDB = Depends(get_master_node_db)
):
    """
    Get current authenticated user information from master node (PostgreSQL).
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

        # Get account from master node (PostgreSQL)
        account_result = master_db.select(
            """
            SELECT account_id, username, email, account_type, created_at
            FROM account 
            WHERE account_id = $1
            """,
            [account_id]
        )
        
        if not account_result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        account = account_result[0]
        
        # Format created_at properly
        created_at = account["created_at"]
        if isinstance(created_at, str):
            created_at_str = created_at
        else:
            created_at_str = created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at)

        return UserResponse(
            account_id=account["account_id"],
            username=account["username"],
            email=account["email"],
            account_type=account["account_type"],
            created_at=created_at_str,
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
