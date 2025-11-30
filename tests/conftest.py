import warnings
from sqlalchemy import exc as sa_exc

warnings.filterwarnings(
    "ignore",
    category=sa_exc.SAWarning,
    message=".*nested transaction already deassociated.*"
)

import os
import uuid
import pytest

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from datetime import datetime, timedelta, timezone
from app.core.config import get_settings
from app.core.security import get_password_hash
from app.models import Base, Account, FreeAccount, PaidAccount
from app.main import app
from app.db.session import get_db, get_master_node_db

# -----------------------------
# Force test mode and load settings
# -----------------------------
os.environ["TESTING"] = "1"
settings = get_settings(testing=True)

# -----------------------------
# Safety check: Ensure we're using the test database, not production
# -----------------------------
test_db_url = settings.database_url
# Verify it's the test database (should contain 'test' in the URL or be on port 5432)
# Production database is on port 5433, test database is on port 5432
is_test_db = (
    "test" in test_db_url.lower() or 
    ":5432" in test_db_url or 
    "test_postgres_db" in test_db_url or
    "test_fyp" in test_db_url or
    "test_user" in test_db_url
)
is_prod_db = (
    ":5433" in test_db_url or 
    "postgres_db" in test_db_url or
    ("database" in test_db_url and "test" not in test_db_url.lower())
)

if is_prod_db or not is_test_db:
    raise RuntimeError(
        f"SAFETY CHECK FAILED: Tests are trying to use production database!\n"
        f"Database URL: {test_db_url}\n"
        f"Production database detected! This would destroy production data!\n"
        f"Tests must use test_postgres_db (port 5432), not postgres_db (port 5433).\n"
        f"Aborting tests to prevent data loss."
    )

print(f"[TEST CONFIG] ✓ Safety check passed - Using test database: {test_db_url}")

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
    Uses DROP TABLE ... CASCADE to handle foreign key dependencies.
    """
    # Drop all tables with CASCADE to handle foreign key dependencies
    with engine.begin() as conn:
        # Get all table names from metadata
        table_names = [table.name for table in Base.metadata.tables.values()]
        
        # Drop all tables with CASCADE to handle foreign key constraints
        # CASCADE will automatically drop dependent objects (foreign keys, indexes, etc.)
        for table_name in table_names:
            conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}" CASCADE'))
    
    Base.metadata.create_all(bind=engine, checkfirst=True)
    yield
    # Cleanup after all tests
    with engine.begin() as conn:
        # Drop all tables with CASCADE
        table_names = [table.name for table in Base.metadata.tables.values()]
        for table_name in table_names:
            conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}" CASCADE'))


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
        # Rollback the transaction first (before closing session to avoid deassociation warning)
        # This will undo everything including seed data, but seed_data will recreate it for each test
        try:
            trans.rollback()
        except Exception:
            pass
        # Then close the session
        try:
            session.close()
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
    try:
        savepoint.rollback()
    except Exception:
        pass


class TestMasterNodeDB:
    """Test version of MasterNodeDB that uses SQLAlchemy directly instead of HTTP requests."""
    
    def __init__(self, db_session):
        self.db = db_session
    
    def select(self, sql: str, params: list = None) -> list:
        """Execute SELECT query using SQLAlchemy."""
        from sqlalchemy import text
        import re
        # Convert PostgreSQL parameter syntax ($1, $2) to SQLAlchemy format (:param_1, :param_2)
        sql_named = sql
        param_dict = {}
        if params:
            # Replace in reverse order to avoid replacing $10 when looking for $1
            for i in range(len(params) - 1, -1, -1):
                param_num = i + 1
                param_name = f"param_{param_num}"
                # Match $N where N is the parameter number, ensuring it's not part of a larger number
                # Use (?=\D|$) to match end of string or non-digit after the number
                pattern = r'\$' + str(param_num) + r'(?=\D|$)'
                sql_named = re.sub(pattern, f':{param_name}', sql_named)
                param_dict[param_name] = params[i]
        
        try:
            query = text(sql_named)
            # Use session.execute() for raw SQL queries
            if param_dict:
                result = self.db.execute(query, param_dict)
            else:
                result = self.db.execute(query)
            
            rows = result.fetchall()
        except Exception as e:
            # Log the error for debugging
            import traceback
            print(f"Error in TestMasterNodeDB.select(): {e}")
            print(f"Original SQL: {sql}")
            print(f"Converted SQL: {sql_named}")
            print(f"Params: {param_dict}")
            print(traceback.format_exc())
            raise
        # Convert rows to dict format matching what master node returns
        if rows:
            columns = result.keys()
            result_list = []
            for row in rows:
                row_dict = {}
                for col, val in zip(columns, row):
                    # Convert UUID objects to strings for consistency with master node
                    import uuid as uuid_module
                    if isinstance(val, uuid_module.UUID):
                        row_dict[col] = str(val)
                    elif val is None:
                        row_dict[col] = None
                    else:
                        row_dict[col] = val
                result_list.append(row_dict)
            return result_list
        return []
    
    def execute(self, sql: str, params: list = None) -> dict:
        """Execute INSERT/UPDATE/DELETE query using SQLAlchemy."""
        from sqlalchemy import text
        import re
        # Convert PostgreSQL parameter syntax ($1, $2) to SQLAlchemy format
        sql_named = sql
        param_dict = {}
        if params:
            # Replace in reverse order to avoid replacing $10 when looking for $1
            for i in range(len(params) - 1, -1, -1):
                param_num = i + 1
                param_name = f"param_{param_num}"
                # Match $N where N is the parameter number, ensuring it's not part of a larger number
                pattern = r'\$' + str(param_num) + r'(?=\D|$)'
                sql_named = re.sub(pattern, f':{param_name}', sql_named)
                param_dict[param_name] = params[i]
        
        try:
            query = text(sql_named)
            # Use session.execute() for raw SQL queries
            if param_dict:
                self.db.execute(query, param_dict)
            else:
                self.db.execute(query)
            self.db.flush()
            return {"success": True}
        except Exception as e:
            import traceback
            print(f"Error in TestMasterNodeDB.execute(): {e}")
            print(f"Original SQL: {sql}")
            print(f"Converted SQL: {sql_named}")
            print(f"Params: {param_dict}")
            print(traceback.format_exc())
            raise
    
    def get_nodes(self) -> list:
        """Get all storage nodes."""
        from app.models import StorageNode
        nodes = self.db.query(StorageNode).all()
        return [{"node_id": str(n.node_id), "name": n.name, "status": n.status} for n in nodes]
    
    def get_file_fragments(self, file_id: str) -> list:
        """Get fragments for a specific file."""
        from sqlalchemy import text
        query = text("""
            SELECT f.fragment_id, f.file_id, f.fragment_order, f.fragment_size, f.fragment_hash,
                   fl.node_id, fl.storage_path
            FROM file_fragments f
            JOIN fragment_location fl ON f.fragment_id = fl.fragment_id
            WHERE f.file_id = :file_id
            ORDER BY f.fragment_order
        """)
        result = self.db.execute(query, {"file_id": file_id})
        rows = result.fetchall()
        if rows:
            columns = result.keys()
            return [dict(zip(columns, row)) for row in rows]
        return []
    
    def store_fragment_info(self, file_id: str, node_id: str, fragment_order: int,
                           fragment_size: int, fragment_hash: str) -> dict:
        """Store fragment information."""
        from app.models import FileFragment, FragmentLocation
        import uuid
        
        fragment_id = uuid.uuid4()
        fragment = FileFragment(
            fragment_id=fragment_id,
            file_id=uuid.UUID(file_id),
            fragment_order=fragment_order,
            fragment_size=fragment_size,
            fragment_hash=fragment_hash
        )
        self.db.add(fragment)
        
        location = FragmentLocation(
            fragment_id=fragment_id,
            node_id=uuid.UUID(node_id),
            storage_path=f"/fragments/{fragment_id}"
        )
        self.db.add(location)
        self.db.flush()
        
        return {"success": True, "fragment_id": str(fragment_id)}


@pytest.fixture(scope="function")
def client(db_session, seed_data):
    """
    FastAPI TestClient fixture for sending HTTP requests.
    Overrides the get_db dependency to use the test database session.
    Overrides get_master_node_db to use TestMasterNodeDB for direct database access.
    """
    def override_get_db():
        try:
            yield db_session
        finally:
            # Don't close here, let db_session fixture handle it
            pass
    
    # Create test master node DB that uses SQLAlchemy directly
    test_master_db = TestMasterNodeDB(db_session)
    
    def override_get_master_node_db():
        return test_master_db
    
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_master_node_db] = override_get_master_node_db
    
    try:
        with TestClient(app) as c:
            yield c
    finally:
        # Remove the overrides after the test
        app.dependency_overrides.clear()
