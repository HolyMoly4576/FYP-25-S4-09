from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
import bcrypt
from app.core.config import get_settings

settings = get_settings()


def verify_password(plain_password: str, hashed_password: str) -> bool:
	"""Verify a password against its hash."""
	try:
		# Check if the hash looks like a bcrypt hash (starts with $2a$, $2b$, or $2y$)
		if not hashed_password.startswith(("$2a$", "$2b$", "$2y$")):
			return False
		# Convert password to bytes and hash to bytes
		password_bytes = plain_password.encode('utf-8')
		hash_bytes = hashed_password.encode('utf-8')
		return bcrypt.checkpw(password_bytes, hash_bytes)
	except (ValueError, TypeError, Exception):
		# If verification fails or hash is invalid, return False
		return False


def get_password_hash(password: str) -> str:
	"""Hash a password."""
	# Convert password to bytes, hash it, and return as string
	password_bytes = password.encode('utf-8')
	hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
	return hashed.decode('utf-8')


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
	"""Create a JWT access token."""
	to_encode = data.copy()
	if expires_delta:
		expire = datetime.utcnow() + expires_delta
	else:
		expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
	to_encode.update({"exp": expire})
	encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
	return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
	"""Decode and verify a JWT token."""
	try:
		payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
		return payload
	except JWTError:
		return None

