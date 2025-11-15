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


def test_update_storage_limit_paid_account(client, seed_data):
    """Test updating storage limit for a PAID account."""
    # Login as bob (PAID account)
    login_data = {"username_or_email": "bob", "password": "password"}
    login_response = client.post("/auth/login", json=login_data)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Update storage to $20/month (should give 60GB)
    update_data = {"monthly_cost": 20.0}
    response = client.patch("/storage/update", json=update_data, headers=headers)
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["storage_limit_gb"] == 60  # 20 * 3 = 60
    assert data["monthly_cost"] == 20.0
    assert data["renewal_date"] is not None
    assert "message" in data
    assert "60GB" in data["message"]
    assert "$20" in data["message"]
    
    # Verify the update by checking storage usage again
    usage_response = client.get("/storage/usage", headers=headers)
    assert usage_response.status_code == 200
    usage_data = usage_response.json()
    assert usage_data["storage_limit_gb"] == 60
    assert usage_data["monthly_cost"] == 20.0


def test_update_storage_limit_free_account_fails(client, seed_data):
    """Test that FREE accounts cannot update storage limits."""
    # Login as alice (FREE account)
    login_data = {"username_or_email": "alice", "password": "password"}
    login_response = client.post("/auth/login", json=login_data)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Try to update storage (should fail)
    update_data = {"monthly_cost": 20.0}
    response = client.patch("/storage/update", json=update_data, headers=headers)
    
    assert response.status_code == 400
    assert "only available for paid accounts" in response.json()["detail"].lower()


def test_update_storage_limit_invalid_cost(client, seed_data):
    """Test that updating with invalid monthly cost fails."""
    # Login as bob (PAID account)
    login_data = {"username_or_email": "bob", "password": "password"}
    login_response = client.post("/auth/login", json=login_data)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Try with zero cost
    update_data = {"monthly_cost": 0}
    response = client.patch("/storage/update", json=update_data, headers=headers)
    assert response.status_code == 400
    
    # Try with negative cost
    update_data = {"monthly_cost": -10}
    response = client.patch("/storage/update", json=update_data, headers=headers)
    assert response.status_code == 400


def test_update_storage_limit_requires_auth(client):
    """Test that updating storage limit requires authentication."""
    update_data = {"monthly_cost": 20.0}
    response = client.patch("/storage/update", json=update_data)
    assert response.status_code in (401, 403)


def test_update_storage_limit_different_tiers(client, seed_data):
    """Test updating storage limit to different tiers."""
    # Login as bob (PAID account)
    login_data = {"username_or_email": "bob", "password": "password"}
    login_response = client.post("/auth/login", json=login_data)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test $10/month -> 30GB
    update_data = {"monthly_cost": 10.0}
    response = client.patch("/storage/update", json=update_data, headers=headers)
    assert response.status_code == 200
    assert response.json()["storage_limit_gb"] == 30
    
    # Test $20/month -> 60GB
    update_data = {"monthly_cost": 20.0}
    response = client.patch("/storage/update", json=update_data, headers=headers)
    assert response.status_code == 200
    assert response.json()["storage_limit_gb"] == 60
    
    # Test $30/month -> 90GB
    update_data = {"monthly_cost": 30.0}
    response = client.patch("/storage/update", json=update_data, headers=headers)
    assert response.status_code == 200
    assert response.json()["storage_limit_gb"] == 90

