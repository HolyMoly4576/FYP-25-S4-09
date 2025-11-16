def test_create_root_folder(client, seed_data):
    # Login as seeded user alice
    login_data = {"username_or_email": "alice", "password": "password"}
    login_response = client.post("/auth/login", json=login_data)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post("/folders", json={"name": "Documents"}, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Documents"
    assert data["parent_folder_id"] is None
    assert "folder_id" in data


def test_create_subfolder(client, seed_data):
    # Login
    login_data = {"username_or_email": "alice", "password": "password"}
    login_response = client.post("/auth/login", json=login_data)
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create parent folder
    parent = client.post("/folders", json={"name": "Photos"}, headers=headers)
    assert parent.status_code == 201
    parent_id = parent.json()["folder_id"]

    # Create child folder
    child = client.post("/folders", json={"name": "2025", "parent_folder_id": parent_id}, headers=headers)
    assert child.status_code == 201
    data = child.json()
    assert data["name"] == "2025"
    assert data["parent_folder_id"] == parent_id


def test_create_folder_requires_auth(client):
    resp = client.post("/folders", json={"name": "NoAuth"})
    assert resp.status_code in (401, 403)


