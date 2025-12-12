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
    # Master Node Configuration (Primary database interface)
    master_node_url: str = Field(
        default="http://master_node:3000",
        validation_alias=AliasChoices("master_node_url", "MASTER_NODE_URL")
    )
    
    # Test Database URL (only for testing, bypasses master node)

    test_database_url: str = Field(
        default="postgresql+psycopg2://test_user:test_password@test_postgres_db:5432/test_fyp",
        validation_alias=AliasChoices("test_database_url", "TEST_DATABASE_URL")
    )

    # Legacy database_url field for backward compatibility (required by some parts of the code)

    database_url: str = Field(
        default="postgresql+psycopg2://test_user:test_password@test_postgres_db:5432/test_fyp",
        validation_alias=AliasChoices("database_url", "DATABASE_URL", "test_database_url", "TEST_DATABASE_URL")
    )

    # JWT Configuration

    jwt_secret_key: str = Field(
        default="your-secret-key-here-change-in-production-very-long-and-secure",
        validation_alias=AliasChoices("jwt_secret_key", "JWT_SECRET_KEY")
    )

    jwt_algorithm: str = Field(
        default="HS256",
        validation_alias=AliasChoices("jwt_algorithm", "JWT_ALGORITHM")
    )

    access_token_expire_minutes: int = Field(
        default=60,
        validation_alias=AliasChoices("access_token_expire_minutes", "ACCESS_TOKEN_EXPIRE_MINUTES")
    )

    # Environment

    environment: str = Field(
        default="development",
        validation_alias=AliasChoices("environment", "ENVIRONMENT")
    )

    model_config = ConfigDict(
        env_file=str(ENV_FILE),
        env_file=str(ENV_FILE),    # works locally
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