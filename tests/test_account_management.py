import pytest


def test_upgrade_free_to_paid(client, seed_data):
    """Test upgrading a FREE account to PAID."""
    # Login as alice (FREE account)
    login_data = {"username_or_email": "alice", "password": "password"}
    login_response = client.post("/auth/login", json=login_data)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Upgrade to $20/month (should give 60GB)
    upgrade_data = {"monthly_cost": 20.0}
    response = client.post("/account/upgrade", json=upgrade_data, headers=headers)
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["account_type"] == "PAID"
    assert data["storage_limit_gb"] == 60  # 20 * 3 = 60
    assert data["monthly_cost"] == 20.0
    assert data["renewal_date"] is not None
    assert "message" in data
    assert "upgraded to PAID" in data["message"]
    assert "60GB" in data["message"]
    
    # Verify the upgrade by checking storage usage
    usage_response = client.get("/storage/usage", headers=headers)
    assert usage_response.status_code == 200
    usage_data = usage_response.json()
    assert usage_data["account_type"] == "PAID"
    assert usage_data["storage_limit_gb"] == 60
    assert usage_data["monthly_cost"] == 20.0


def test_update_paid_account_plan(client, seed_data):
    """Test updating payment plan for an existing PAID account."""
    # Login as bob (PAID account)
    login_data = {"username_or_email": "bob", "password": "password"}
    login_response = client.post("/auth/login", json=login_data)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Update from $10/month to $20/month (should give 60GB)
    upgrade_data = {"monthly_cost": 20.0}
    response = client.post("/account/upgrade", json=upgrade_data, headers=headers)
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["account_type"] == "PAID"
    assert data["storage_limit_gb"] == 60  # 20 * 3 = 60
    assert data["monthly_cost"] == 20.0
    assert data["renewal_date"] is not None
    assert "message" in data
    assert "Payment plan updated" in data["message"]
    assert "60GB" in data["message"]
    
    # Verify the update by checking storage usage
    usage_response = client.get("/storage/usage", headers=headers)
    assert usage_response.status_code == 200
    usage_data = usage_response.json()
    assert usage_data["storage_limit_gb"] == 60
    assert usage_data["monthly_cost"] == 20.0


def test_upgrade_invalid_cost(client, seed_data):
    """Test that upgrading with invalid monthly cost fails."""
    # Login as alice (FREE account)
    login_data = {"username_or_email": "alice", "password": "password"}
    login_response = client.post("/auth/login", json=login_data)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Try with zero cost
    upgrade_data = {"monthly_cost": 0}
    response = client.post("/account/upgrade", json=upgrade_data, headers=headers)
    assert response.status_code == 400
    
    # Try with negative cost
    upgrade_data = {"monthly_cost": -10}
    response = client.post("/account/upgrade", json=upgrade_data, headers=headers)
    assert response.status_code == 400
    
    # Try with cost below minimum ($10)
    upgrade_data = {"monthly_cost": 5}
    response = client.post("/account/upgrade", json=upgrade_data, headers=headers)
    assert response.status_code == 400


def test_upgrade_requires_auth(client):
    """Test that upgrading requires authentication."""
    upgrade_data = {"monthly_cost": 20.0}
    response = client.post("/account/upgrade", json=upgrade_data)
    assert response.status_code in (401, 403)


def test_upgrade_different_tiers(client, seed_data):
    """Test upgrading to different payment tiers."""
    # Login as bob (PAID account)
    login_data = {"username_or_email": "bob", "password": "password"}
    login_response = client.post("/auth/login", json=login_data)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test $10/month -> 30GB
    upgrade_data = {"monthly_cost": 10.0}
    response = client.post("/account/upgrade", json=upgrade_data, headers=headers)
    assert response.status_code == 200
    assert response.json()["storage_limit_gb"] == 30
    
    # Test $20/month -> 60GB
    upgrade_data = {"monthly_cost": 20.0}
    response = client.post("/account/upgrade", json=upgrade_data, headers=headers)
    assert response.status_code == 200
    assert response.json()["storage_limit_gb"] == 60
    
    # Test $30/month -> 90GB
    upgrade_data = {"monthly_cost": 30.0}
    response = client.post("/account/upgrade", json=upgrade_data, headers=headers)
    assert response.status_code == 200
    assert response.json()["storage_limit_gb"] == 90


def test_downgrade_paid_to_free(client, seed_data):
    """Test downgrading a PAID account to FREE."""
    # Login as bob (PAID account)
    login_data = {"username_or_email": "bob", "password": "password"}
    login_response = client.post("/auth/login", json=login_data)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Downgrade to FREE
    downgrade_data = {"confirm": True}
    response = client.post("/account/downgrade", json=downgrade_data, headers=headers)
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["account_type"] == "FREE"
    assert data["storage_limit_gb"] == 2  # Free accounts get 2GB
    assert "message" in data
    assert "downgraded to FREE" in data["message"]
    
    # Verify the downgrade by checking storage usage
    usage_response = client.get("/storage/usage", headers=headers)
    assert usage_response.status_code == 200
    usage_data = usage_response.json()
    assert usage_data["account_type"] == "FREE"
    assert usage_data["storage_limit_gb"] == 2
    assert usage_data["monthly_cost"] is None


def test_downgrade_free_account_fails(client, seed_data):
    """Test that FREE accounts cannot downgrade."""
    # Login as alice (FREE account)
    login_data = {"username_or_email": "alice", "password": "password"}
    login_response = client.post("/auth/login", json=login_data)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Try to downgrade (should fail)
    downgrade_data = {"confirm": True}
    response = client.post("/account/downgrade", json=downgrade_data, headers=headers)
    
    assert response.status_code == 400
    assert "Only PAID accounts can downgrade" in response.json()["detail"]


def test_downgrade_requires_confirmation(client, seed_data):
    """Test that downgrade requires confirmation."""
    # Login as bob (PAID account)
    login_data = {"username_or_email": "bob", "password": "password"}
    login_response = client.post("/auth/login", json=login_data)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Try without confirmation
    downgrade_data = {"confirm": False}
    response = client.post("/account/downgrade", json=downgrade_data, headers=headers)
    assert response.status_code == 400
    assert "confirmation" in response.json()["detail"].lower()


def test_downgrade_requires_auth(client):
    """Test that downgrading requires authentication."""
    downgrade_data = {"confirm": True}
    response = client.post("/account/downgrade", json=downgrade_data)
    assert response.status_code in (401, 403)

