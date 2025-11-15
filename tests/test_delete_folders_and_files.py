import pytest
import uuid
from datetime import datetime, timezone

from app.models import FileObject


def test_delete_folder_success(client, seed_data):
    """Test successfully deleting a folder."""
    # Login as alice
    login_data = {"username_or_email": "alice", "password": "password"}
    login_response = client.post("/auth/login", json=login_data)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create a folder first
    create_response = client.post("/folders", json={"name": "TestFolder"}, headers=headers)
    assert create_response.status_code == 201
    folder_id = create_response.json()["folder_id"]
    
    # Delete the folder
    delete_response = client.delete(f"/folders/{folder_id}", headers=headers)
    assert delete_response.status_code == 200
    
    data = delete_response.json()
    assert "message" in data
    assert "permanently deleted" in data["message"].lower()
    assert data["deleted_folder_id"] == str(folder_id)
    assert data["deleted_folder_name"] == "TestFolder"
    
    # Verify folder is deleted by trying to delete it again (should fail)
    delete_again_response = client.delete(f"/folders/{folder_id}", headers=headers)
    assert delete_again_response.status_code == 404


def test_delete_folder_with_children(client, seed_data):
    """Test deleting a folder with child folders (CASCADE delete)."""
    # Login as alice
    login_data = {"username_or_email": "alice", "password": "password"}
    login_response = client.post("/auth/login", json=login_data)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create parent folder
    parent_response = client.post("/folders", json={"name": "ParentFolder"}, headers=headers)
    assert parent_response.status_code == 201
    parent_id = parent_response.json()["folder_id"]
    
    # Create child folder
    child_response = client.post(
        "/folders", 
        json={"name": "ChildFolder", "parent_folder_id": parent_id}, 
        headers=headers
    )
    assert child_response.status_code == 201
    child_id = child_response.json()["folder_id"]
    
    # Delete parent folder (should cascade delete child)
    delete_response = client.delete(f"/folders/{parent_id}", headers=headers)
    assert delete_response.status_code == 200
    
    data = delete_response.json()
    assert data["deleted_folder_id"] == str(parent_id)
    assert "permanently deleted" in data["message"].lower()


def test_delete_folder_not_found(client, seed_data):
    """Test deleting a non-existent folder."""
    # Login as alice
    login_data = {"username_or_email": "alice", "password": "password"}
    login_response = client.post("/auth/login", json=login_data)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Try to delete a non-existent folder
    fake_folder_id = uuid.uuid4()
    delete_response = client.delete(f"/folders/{fake_folder_id}", headers=headers)
    
    assert delete_response.status_code == 404
    assert "not found" in delete_response.json()["detail"].lower()


def test_delete_folder_unauthorized(client, seed_data):
    """Test that users cannot delete folders belonging to other users."""
    # Login as alice
    login_data_alice = {"username_or_email": "alice", "password": "password"}
    login_response_alice = client.post("/auth/login", json=login_data_alice)
    assert login_response_alice.status_code == 200
    token_alice = login_response_alice.json()["access_token"]
    
    headers_alice = {"Authorization": f"Bearer {token_alice}"}
    
    # Create a folder as alice
    create_response = client.post("/folders", json={"name": "AliceFolder"}, headers=headers_alice)
    assert create_response.status_code == 201
    folder_id = create_response.json()["folder_id"]
    
    # Login as bob
    login_data_bob = {"username_or_email": "bob", "password": "password"}
    login_response_bob = client.post("/auth/login", json=login_data_bob)
    assert login_response_bob.status_code == 200
    token_bob = login_response_bob.json()["access_token"]
    
    headers_bob = {"Authorization": f"Bearer {token_bob}"}
    
    # Try to delete alice's folder as bob (should fail)
    delete_response = client.delete(f"/folders/{folder_id}", headers=headers_bob)
    assert delete_response.status_code == 404
    assert "not found" in delete_response.json()["detail"].lower() or "permission" in delete_response.json()["detail"].lower()


def test_delete_folder_requires_auth(client, seed_data):
    """Test that deleting a folder requires authentication."""
    # Create a folder first (with auth)
    login_data = {"username_or_email": "alice", "password": "password"}
    login_response = client.post("/auth/login", json=login_data)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    headers = {"Authorization": f"Bearer {token}"}
    create_response = client.post("/folders", json={"name": "TestFolder"}, headers=headers)
    assert create_response.status_code == 201
    folder_id = create_response.json()["folder_id"]
    
    # Try to delete without authentication
    delete_response = client.delete(f"/folders/{folder_id}")
    assert delete_response.status_code in (401, 403)


def test_delete_multiple_folders(client, seed_data):
    """Test deleting multiple folders sequentially."""
    # Login as alice
    login_data = {"username_or_email": "alice", "password": "password"}
    login_response = client.post("/auth/login", json=login_data)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create multiple folders
    folder_ids = []
    for i in range(3):
        create_response = client.post(
            "/folders", 
            json={"name": f"Folder{i}"}, 
            headers=headers
        )
        assert create_response.status_code == 201
        folder_ids.append(create_response.json()["folder_id"])
    
    # Delete all folders
    for folder_id in folder_ids:
        delete_response = client.delete(f"/folders/{folder_id}", headers=headers)
        assert delete_response.status_code == 200
        assert "permanently deleted" in delete_response.json()["message"].lower()


# File deletion tests
def test_delete_file_success(client, seed_data):
    """Test successfully deleting a file."""
    # Login as alice
    login_data = {"username_or_email": "alice", "password": "password"}
    login_response = client.post("/auth/login", json=login_data)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create a file object in the database using seed_data session
    from app.models import Account
    alice_account = seed_data.query(Account).filter(Account.username == "alice").first()
    
    file_obj = FileObject(
        account_id=alice_account.account_id,
        file_name="test_file.txt",
        file_size=1024,
        logical_path="/test/path/test_file.txt"
    )
    seed_data.add(file_obj)
    seed_data.commit()
    seed_data.refresh(file_obj)
    file_id = file_obj.file_id
    
    # Delete the file
    delete_response = client.delete(f"/files/{file_id}", headers=headers)
    assert delete_response.status_code == 200
    
    data = delete_response.json()
    assert "message" in data
    assert "permanently deleted" in data["message"].lower()
    assert data["deleted_file_id"] == str(file_id)
    assert data["deleted_file_name"] == "test_file.txt"
    
    # Verify file is deleted by trying to delete it again (should fail)
    delete_again_response = client.delete(f"/files/{file_id}", headers=headers)
    assert delete_again_response.status_code == 404


def test_delete_file_not_found(client, seed_data):
    """Test deleting a non-existent file."""
    # Login as alice
    login_data = {"username_or_email": "alice", "password": "password"}
    login_response = client.post("/auth/login", json=login_data)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Try to delete a non-existent file
    fake_file_id = uuid.uuid4()
    delete_response = client.delete(f"/files/{fake_file_id}", headers=headers)
    
    assert delete_response.status_code == 404
    assert "not found" in delete_response.json()["detail"].lower()


def test_delete_file_unauthorized(client, seed_data):
    """Test that users cannot delete files belonging to other users."""
    # Login as alice
    login_data_alice = {"username_or_email": "alice", "password": "password"}
    login_response_alice = client.post("/auth/login", json=login_data_alice)
    assert login_response_alice.status_code == 200
    token_alice = login_response_alice.json()["access_token"]
    
    headers_alice = {"Authorization": f"Bearer {token_alice}"}
    
    # Create a file as alice
    from app.models import Account
    alice_account = seed_data.query(Account).filter(Account.username == "alice").first()
    
    file_obj = FileObject(
        account_id=alice_account.account_id,
        file_name="alice_file.txt",
        file_size=2048,
        logical_path="/alice/path/alice_file.txt"
    )
    seed_data.add(file_obj)
    seed_data.commit()
    seed_data.refresh(file_obj)
    file_id = file_obj.file_id
    
    # Login as bob
    login_data_bob = {"username_or_email": "bob", "password": "password"}
    login_response_bob = client.post("/auth/login", json=login_data_bob)
    assert login_response_bob.status_code == 200
    token_bob = login_response_bob.json()["access_token"]
    
    headers_bob = {"Authorization": f"Bearer {token_bob}"}
    
    # Try to delete alice's file as bob (should fail)
    delete_response = client.delete(f"/files/{file_id}", headers=headers_bob)
    assert delete_response.status_code == 404
    assert "not found" in delete_response.json()["detail"].lower() or "permission" in delete_response.json()["detail"].lower()


def test_delete_file_requires_auth(client, seed_data):
    """Test that deleting a file requires authentication."""
    # Create a file first (with auth)
    from app.models import Account
    alice_account = seed_data.query(Account).filter(Account.username == "alice").first()
    
    file_obj = FileObject(
        account_id=alice_account.account_id,
        file_name="test_file.txt",
        file_size=1024,
        logical_path="/test/path/test_file.txt"
    )
    seed_data.add(file_obj)
    seed_data.commit()
    seed_data.refresh(file_obj)
    file_id = file_obj.file_id
    
    # Try to delete without authentication
    delete_response = client.delete(f"/files/{file_id}")
    assert delete_response.status_code in (401, 403)


def test_delete_multiple_files(client, seed_data):
    """Test deleting multiple files sequentially."""
    # Login as alice
    login_data = {"username_or_email": "alice", "password": "password"}
    login_response = client.post("/auth/login", json=login_data)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create multiple files
    from app.models import Account
    alice_account = seed_data.query(Account).filter(Account.username == "alice").first()
    
    file_ids = []
    for i in range(3):
        file_obj = FileObject(
            account_id=alice_account.account_id,
            file_name=f"file{i}.txt",
            file_size=1024 * (i + 1),
            logical_path=f"/test/path/file{i}.txt"
        )
        seed_data.add(file_obj)
        seed_data.commit()
        seed_data.refresh(file_obj)
        file_ids.append(file_obj.file_id)
    
    # Delete all files
    for file_id in file_ids:
        delete_response = client.delete(f"/files/{file_id}", headers=headers)
        assert delete_response.status_code == 200
        assert "permanently deleted" in delete_response.json()["message"].lower()

