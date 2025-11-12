from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import get_settings
import os

# Lazy initialization - only create when needed
_settings = None
_engine = None
_SessionLocal = None

def _get_settings():
    """Lazy load settings."""
    global _settings
    if _settings is None:
        _settings = get_settings(testing=os.getenv("TESTING") == "1")
    return _settings

def _get_engine():
    """Lazy load database engine."""
    global _engine
    if _engine is None:
        settings = _get_settings()
        _engine = create_engine(settings.database_url, pool_pre_ping=True)
    return _engine

def _get_session_local():
    """Lazy load session maker."""
    global _SessionLocal
    if _SessionLocal is None:
        engine = _get_engine()
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return _SessionLocal

def get_db():
    """Get database session."""
    SessionLocal = _get_session_local()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
