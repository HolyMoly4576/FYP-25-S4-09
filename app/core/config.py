import os
from functools import lru_cache


class Settings:
	project_name: str = os.getenv("PROJECT_NAME", "FYP Secure File Sharing API")
	debug: bool = os.getenv("DEBUG", "true").lower() == "true"
	secret_key: str = os.getenv("SECRET_KEY", "CHANGE_ME_DEV_ONLY")
	access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
	algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")

	database_url: str = os.getenv(
		"DATABASE_URL",
		"postgresql+psycopg2://fyp_user:fyp_password@localhost:5432/fyp",
	)

	backend_cors_origins: str = os.getenv("BACKEND_CORS_ORIGINS", "*")


@lru_cache
def get_settings() -> Settings:
	return Settings()


