import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import get_db
from app.core.security import get_password_hash
from app.models import Account

@pytest.fixture(scope="module")
def client():
    """
    Fixture for FastAPI TestClient using the existing seeded Postgres database.
    Ensures the test user has the correct hashed password for login tests.
    """
    db = next(get_db())

    # Ensure the seeded user has a valid hashed password
    user = db.query(Account).filter(Account.email == "test@gmail.com").first()
    if user:
        user.password_hash = get_password_hash("password")  # hash matches test login
        db.commit()

    yield TestClient(app)
