def test_login_flow(client, seed_data):
    """
    Test login with an existing seeded user.
    """
    # Seeded user from seed_data: "alice"
    login_data = {"username_or_email": "alice", "password": "password"}
    response = client.post("/auth/login", json=login_data)
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_login_invalid_credentials(client, seed_data):
    """
    Test login with invalid credentials.
    """
    login_data = {"username_or_email": "nonexistent@example.com", "password": "wrongpassword"}
    response = client.post("/auth/login", json=login_data)
    assert response.status_code == 401


def test_login_with_email(client, seed_data):
    """
    Test login using email instead of username.
    """
    login_data = {"username_or_email": "alice@test.com", "password": "password"}
    response = client.post("/auth/login", json=login_data)
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_login_wrong_password(client, seed_data):
    """
    Test login with correct username but wrong password.
    """
    login_data = {"username_or_email": "alice", "password": "wrongpassword"}
    response = client.post("/auth/login", json=login_data)
    assert response.status_code == 401
