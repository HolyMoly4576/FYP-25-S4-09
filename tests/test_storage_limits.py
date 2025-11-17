import pytest


def test_get_storage_usage_free_account(client, seed_data):
    """Test getting storage usage for a FREE account."""
    # Login as alice (FREE account)
    login_data = {"username_or_email": "alice", "password": "password"}
    login_response = client.post("/auth/login", json=login_data)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/storage/usage", headers=headers)
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["account_type"] == "FREE"
    assert data["storage_limit_gb"] == 2
    assert data["used_bytes"] == 0  # No files uploaded yet
    assert data["used_gb"] == 0.0
    assert data["remaining_bytes"] == 2 * (1024 ** 3)
    assert data["remaining_gb"] == 2.0
    assert data["usage_percentage"] == 0.0
    assert data["monthly_cost"] is None
    assert data["renewal_date"] is None


def test_get_storage_usage_paid_account(client, seed_data):
    """Test getting storage usage for a PAID account."""
    # Login as bob (PAID account)
    login_data = {"username_or_email": "bob", "password": "password"}
    login_response = client.post("/auth/login", json=login_data)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/storage/usage", headers=headers)
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["account_type"] == "PAID"
    assert data["storage_limit_gb"] == 30
    assert data["used_bytes"] == 0  # No files uploaded yet
    assert data["used_gb"] == 0.0
    assert data["remaining_bytes"] == 30 * (1024 ** 3)
    assert data["remaining_gb"] == 30.0
    assert data["usage_percentage"] == 0.0
    assert data["monthly_cost"] == 10.0
    assert data["renewal_date"] is not None


def test_get_storage_usage_requires_auth(client):
    """Test that getting storage usage requires authentication."""
    response = client.get("/storage/usage")
    assert response.status_code in (401, 403)

