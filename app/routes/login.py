from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional

from app.db.session import get_db
from app.models import Account
from app.core.security import verify_password, get_password_hash, create_access_token
from app.core.config import get_settings
import uuid

router = APIRouter(prefix="/auth", tags=["authentication"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")
settings = get_settings()


class LoginRequest(BaseModel):
	username_or_email: str
	password: str


class RegisterRequest(BaseModel):
	username: str
	email: EmailStr
	password: str
	account_type: str = "FREE"  # Default to FREE account


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
def login(login_data: LoginRequest, db: Session = Depends(get_db)):
	"""
	Login endpoint. Accepts username/email and password.
	Returns JWT access token on successful authentication.
	"""
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
	
	# Create access token
	access_token = create_access_token(
		data={"sub": str(account.account_id), "username": account.username}
	)
	
	return TokenResponse(
		access_token=access_token,
		token_type="bearer",
		account_id=str(account.account_id),
		username=account.username,
		account_type=account.type,
	)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(register_data: RegisterRequest, db: Session = Depends(get_db)):
	"""
	Registration endpoint. Creates a new account.
	"""
	# Validate account type
	if register_data.account_type not in ["FREE", "PAID"]:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Account type must be 'FREE' or 'PAID'",
		)
	
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
	
	# Create new account
	hashed_password = get_password_hash(register_data.password)
	new_account = Account(
		account_id=uuid.uuid4(),
		username=register_data.username,
		email=register_data.email,
		password_hash=hashed_password,
		type=register_data.account_type,
	)
	
	db.add(new_account)
	db.commit()
	db.refresh(new_account)
	
	return UserResponse(
		account_id=str(new_account.account_id),
		username=new_account.username,
		email=new_account.email,
		account_type=new_account.type,
		created_at=new_account.created_at.isoformat(),
	)


@router.get("/me", response_model=UserResponse)
def get_current_user(
	token: str = Depends(oauth2_scheme),
	db: Session = Depends(get_db)
):
	"""
	Get current authenticated user information.
	"""
	from app.core.security import decode_access_token
	
	payload = decode_access_token(token)
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
		account_type=account.type,
		created_at=account.created_at.isoformat(),
	)
