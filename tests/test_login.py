def test_login_flow(client):
    """
    Test login with the existing seeded user.
    """
    login_data = {"username_or_email": "test@gmail.com", "password": "password"}
    response = client.post("/auth/login", json=login_data)
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_login_invalid_credentials(client):
    """
    Test login with invalid credentials.
    """
    login_data = {"username_or_email": "nonexistent@example.com", "password": "wrongpassword"}
    response = client.post("/auth/login", json=login_data)
    assert response.status_code == 401
