def test_update_profile_username(client, seed_data):
    """
    Test updating username with authenticated user.
    """
    # Login as seeded user alice
    login_data = {"username_or_email": "alice", "password": "password"}
    login_response = client.post("/auth/login", json=login_data)
    token = login_response.json()["access_token"]

    headers = {"Authorization": f"Bearer {token}"}
    update_data = {"username": "alice_new"}
    response = client.put("/user/profile", json=update_data, headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "alice_new"
    assert data["email"] == "alice@test.com"
    assert "message" in data


def test_update_profile_email(client, seed_data):
    """
    Test updating email with authenticated user.
    """
    login_data = {"username_or_email": "alice", "password": "password"}
    login_response = client.post("/auth/login", json=login_data)
    token = login_response.json()["access_token"]

    headers = {"Authorization": f"Bearer {token}"}
    update_data = {"email": "alice_new@test.com"}
    response = client.put("/user/profile", json=update_data, headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "alice_new@test.com"
    assert data["username"] == "alice"
    assert "message" in data


def test_update_profile_both_fields(client, seed_data):
    """
    Test updating both username and email with authenticated user.
    """
    login_data = {"username_or_email": "alice", "password": "password"}
    login_response = client.post("/auth/login", json=login_data)
    token = login_response.json()["access_token"]

    headers = {"Authorization": f"Bearer {token}"}
    update_data = {"username": "alice_final", "email": "alice_final@test.com"}
    response = client.put("/user/profile", json=update_data, headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "alice_final"
    assert data["email"] == "alice_final@test.com"


def test_update_password_success(client, seed_data):
    """
    Test updating password with correct old password.
    """
    # Login as seeded user alice_final
    login_data = {"username_or_email": "alice", "password": "password"}
    login_response = client.post("/auth/login", json=login_data)
    token = login_response.json()["access_token"]

    headers = {"Authorization": f"Bearer {token}"}
    password_data = {"old_password": "password", "new_password": "newpassword123"}
    response = client.put("/user/password", json=password_data, headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "password updated" in data["message"].lower()

    # Verify new password works
    login_data_new = {"username_or_email": "alice", "password": "newpassword123"}
    login_response_new = client.post("/auth/login", json=login_data_new)
    assert login_response_new.status_code == 200

