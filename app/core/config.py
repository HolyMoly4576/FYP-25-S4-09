import os
from pydantic_settings import BaseSettings
from pydantic import ConfigDict, Field, AliasChoices
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE = BASE_DIR / ".env"

IS_VERCEL = os.getenv("VERCEL", None) is not None

class Settings(BaseSettings):
    master_node_url: str = Field(
        default="http://master_node:3000",
        validation_alias=AliasChoices("master_node_url", "MASTER_NODE_URL")
    )

    test_database_url: str = Field(
        default="postgresql+psycopg2://test_user:test_password@test_postgres_db:5432/test_fyp",
        validation_alias=AliasChoices("test_database_url", "TEST_DATABASE_URL")
    )

    database_url: str = Field(
        default="postgresql+psycopg2://test_user:test_password@test_postgres_db:5432/test_fyp",
        validation_alias=AliasChoices(
            "database_url", "DATABASE_URL", 
            "test_database_url", "TEST_DATABASE_URL"
        )
    )

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

    environment: str = Field(
        default="development",
        validation_alias=AliasChoices("environment", "ENVIRONMENT")
    )

    # IMPORTANT
    model_config = ConfigDict(
        env_file=None if IS_VERCEL else str(ENV_FILE),
        env_file_encoding="utf-8-sig",
        extra="ignore",
        case_sensitive=False,
    )


def get_settings(testing: bool = False):
    settings = Settings()
    if testing:
        settings.database_url = settings.test_database_url
        settings.jwt_secret_key = "testsecret"
        settings.access_token_expire_minutes = 5
    return settings