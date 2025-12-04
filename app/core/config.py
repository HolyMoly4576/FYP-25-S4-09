from pydantic_settings import BaseSettings
from pydantic import ConfigDict, Field, AliasChoices
from pathlib import Path
import os

# Project root directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE = BASE_DIR / ".env"

# Ensure .env file exists
if not ENV_FILE.exists():
    raise FileNotFoundError(f".env file not found at {ENV_FILE}")

# Manually load .env file to ensure variables are available
# This helps with cases where Pydantic Settings might not read the file correctly
try:
    with open(ENV_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                # Only set if not already in environment (env vars take precedence)
                if key and key not in os.environ:
                    os.environ[key] = value
except Exception as e:
    # If manual loading fails, Pydantic Settings will try to load it
    pass

class Settings(BaseSettings):
    database_url: str = Field(validation_alias=AliasChoices("database_url", "DATABASE_URL"))
    test_database_url: str = Field(validation_alias=AliasChoices("test_database_url", "TEST_DATABASE_URL"))
    jwt_secret_key: str = "testsecret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=30, validation_alias=AliasChoices("access_token_expire_minutes", "ACCESS_TOKEN_EXPIRE_MINUTES"))

    model_config = ConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8-sig",
        extra="ignore",
        case_sensitive=False
    )

def get_settings(testing: bool = False):
    settings = Settings()
    if testing:
        settings.database_url = settings.test_database_url
        settings.jwt_secret_key = "testsecret"
        settings.access_token_expire_minutes = 5
    return settings
