import warnings
from sqlalchemy import exc as sa_exc

# Suppress the specific SQLAlchemy warning about deassociated transactions
warnings.filterwarnings(
    "ignore",
    category=sa_exc.SAWarning,
    message=".*nested transaction already deassociated.*"
)

# Also suppress at the warnings module level for this specific message
warnings.filterwarnings(
    "ignore",
    message=".*nested transaction already deassociated.*"
)

import os
import uuid
import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from datetime import datetime, timedelta, timezone
from app.core.config import get_settings
from app.core.security import get_password_hash
from app.models import Base, Account, FreeAccount, PaidAccount, FileObject, PasswordResetToken, ActivityLog
from app.main import app
from app.db.session import get_db

# -----------------------------
# Force test mode and load settings
# -----------------------------
os.environ["TESTING"] = "1"
settings = get_settings(testing=True)

# -----------------------------
# Database engine & session
# -----------------------------
engine = create_engine(settings.database_url)
TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

# -----------------------------
# Fixtures
# -----------------------------

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """
    Drop and recreate all tables once per test session.
    """
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    # Cleanup after all tests
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session():
    """
    Provide a transactional scope around a series of operations.
    Uses savepoints to allow seed data to persist while rolling back test changes.
    """
    # Create a connection and start a transaction
    connection = engine.connect()
    trans = connection.begin()
    session = TestingSessionLocal(bind=connection)
    
    # Store connection for use in seed_data
    session._test_connection = connection
    
    try:
        yield session
    finally:
        # Close session first to avoid deassociation issues
        try:
            session.close()
        except Exception:
            pass
        
        # Rollback the transaction
        # This will undo everything including seed data, but seed_data will recreate it for each test
        try:
            if trans.is_active:
                trans.rollback()
        except (AttributeError, sa_exc.InvalidRequestError):
            # Transaction may already be rolled back
            pass
        except Exception:
            pass
        
        # Finally close the connection
        try:
            connection.close()
        except Exception:
            pass


@pytest.fixture(scope="function")
def seed_data(db_session):
    """
    Seed initial data for testing.
    Ensures each test gets predictable users.
    Uses savepoints so test changes can be rolled back while keeping seed data.
    """
    # Get the connection from the session
    connection = db_session._test_connection
    
    # Seeded user 1
    alice = Account(
        account_id=uuid.UUID("123e4567-e89b-12d3-a456-426614174000"),
        username="alice",
        email="alice@test.com",
        password_hash=get_password_hash("password"),
        account_type="FREE"
    )

    # Seeded user 2
    bob = Account(
        account_id=uuid.UUID("123e4567-e89b-12d3-a456-426614174001"),
        username="bob",
        email="bob@test.com",
        password_hash=get_password_hash("password"),
        account_type="PAID"
    )

    db_session.add_all([alice, bob])
    # Flush to make objects available
    db_session.flush()
    
    # Create FreeAccount for alice
    free_account = FreeAccount(
        account_id=alice.account_id,
        storage_limit_gb=2
    )
    
    # Create PaidAccount for bob
    now = datetime.now(timezone.utc)
    paid_account = PaidAccount(
        account_id=bob.account_id,
        storage_limit_gb=30,
        monthly_cost=10.00,
        start_date=now,
        renewal_date=now + timedelta(days=30),
        status="ACTIVE"
    )
    
    db_session.add_all([free_account, paid_account])
    db_session.flush()
    
    # Create a savepoint after seeding
    # Tests can commit/rollback within this savepoint
    savepoint = connection.begin_nested()
    
    yield db_session

    # Rollback to savepoint to undo test changes, keeping seed data
    # Suppress warnings around rollback operation
    with warnings.catch_warnings():
        # Suppress the specific warning we're trying to avoid
        warnings.simplefilter("ignore", sa_exc.SAWarning)
        warnings.filterwarnings("ignore", category=sa_exc.SAWarning, message=".*nested transaction already deassociated.*")
        warnings.filterwarnings("ignore", message=".*nested transaction already deassociated.*")
        
        try:
            # Check if savepoint is still valid before attempting rollback
            # Only attempt rollback if savepoint is active and connection is valid
            if (hasattr(savepoint, 'is_active') and 
                savepoint.is_active and 
                not connection.closed):
                try:
                    # Attempt rollback - warnings suppressed by context manager
                    savepoint.rollback()
                except (sa_exc.PendingRollbackError, 
                        sa_exc.InvalidRequestError, 
                        AttributeError, 
                        sa_exc.StatementError):
                    # Savepoint may already be rolled back, deassociated, or connection invalid
                    # This is expected in some cases - silently ignore
                    pass
        except Exception:
            # Any other exception - ignore it
            pass


@pytest.fixture(scope="function")
def client(db_session):
    """
    FastAPI TestClient fixture for sending HTTP requests.
    Overrides the get_db dependency to use the test database session.
    """
    def override_get_db():
        try:
            yield db_session
        finally:
            # Don't close here, let db_session fixture handle it
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    try:
        with TestClient(app) as c:
            yield c
    finally:
        # Remove the override after the test
        app.dependency_overrides.clear()
