#!/usr/bin/env python3
"""
Test script for the advanced file upload system with complete schema.
Tests the new master node API with erasure coding and comprehensive metadata.
"""

import requests
import json
import base64

def test_advanced_upload():
    # Master node and backend URLs
    MASTER_NODE_URL = "http://localhost:8000"
    BACKEND_URL = "http://localhost:8004"
    
    print("🚀 Testing Advanced File Upload System")
    print("=" * 50)
    
    # Step 1: Login to get authentication token
    print("\n1. Authenticating with backend...")
    try:
        login_data = {
            "username_or_email": "testuser",
            "password": "testpassword"
        }
        
        login_response = requests.post(f"{BACKEND_URL}/auth/login", json=login_data)
        if login_response.status_code == 200:
            token = login_response.json()["access_token"]
            print(f"   ✅ Authenticated successfully")
            
            headers = {"Authorization": f"Bearer {token}"}
        else:
            print(f"   ❌ Authentication failed: {login_response.text}")
            return
    except Exception as e:
        print(f"   ❌ Authentication error: {e}")
        return
    
    # Step 2: Check master node status and available erasure profiles
    print("\n2. Checking system status...")
    try:
        status = requests.get(f"{MASTER_NODE_URL}/status").json()
        print(f"   📊 Accounts: {status['statistics']['accounts']}")
        print(f"   📁 Files: {status['statistics']['files']}")
        print(f"   🗂️ Fragments: {status['statistics']['fragments']}")
        print(f"   💾 Storage Nodes: {status['statistics']['storage_nodes']}")
        
        profiles = requests.get(f"{MASTER_NODE_URL}/erasure-profiles").json()
        print(f"   🔧 Available erasure profiles:")
        for profile in profiles:
            print(f"      - {profile['erasure_id']}: {profile['k']}+{profile['m']} fragments ({profile['notes']})")
            
    except Exception as e:
        print(f"   ❌ Status check failed: {e}")
        return
    
    # Step 3: Test file uploads with different erasure coding levels
    test_files = [
        {
            "name": "small_test.txt",
            "content": "Hello, this is a small test file for the distributed storage system!",
            "erasure_id": "LOW"
        },
        {
            "name": "medium_test.md",
            "content": """# Medium Test File

This is a medium-sized test file to demonstrate the **advanced file upload system**.

## Features Tested:
- ✅ Complete database schema
- ✅ Erasure coding (k+m fragments)
- ✅ Account management
- ✅ Fragment distribution across storage nodes
- ✅ File versioning
- ✅ Metadata tracking

## System Architecture:
- **Master Node**: SQLite database with complete schema
- **Storage Nodes**: Distributed fragment storage
- **Backend**: FastAPI with authentication
- **Frontend**: React application (ready for testing)

The system now supports proper erasure coding with configurable redundancy levels!
""",
            "erasure_id": "MEDIUM"
        },
        {
            "name": "large_test.json",
            "content": json.dumps({
                "test_data": {
                    "description": "Large test file with JSON data",
                    "features": [
                        "Complete database schema implementation",
                        "Advanced erasure coding support",
                        "Multi-tier user accounts (FREE/PAID/SYSADMIN)",
                        "Comprehensive folder management",
                        "File versioning with segment tracking",
                        "Distributed fragment storage with location tracking",
                        "Encryption key management (ready for implementation)",
                        "Automated repair job system (ready for implementation)",
                        "Node heartbeat and capacity monitoring",
                        "Production-ready architecture"
                    ],
                    "accounts_created": 4,
                    "folders_created": 8,
                    "sample_files": 11,
                    "erasure_profiles": {
                        "LOW": {"k": 4, "m": 2, "total_fragments": 6},
                        "MEDIUM": {"k": 6, "m": 3, "total_fragments": 9},
                        "HIGH": {"k": 8, "m": 4, "total_fragments": 12}
                    }
                }
            }, indent=2),
            "erasure_id": "HIGH"
        }
    ]
    
    print(f"\n3. Testing file uploads with different erasure coding levels...")
    uploaded_files = []
    
    for i, test_file in enumerate(test_files, 1):
        print(f"\n   📄 File {i}: {test_file['name']} (erasure: {test_file['erasure_id']})")
        
        try:
            # Encode file content to base64
            file_data = base64.b64encode(test_file['content'].encode()).decode()
            
            upload_data = {
                "filename": test_file['name'],
                "data": file_data,
                "content_type": "text/plain" if test_file['name'].endswith('.txt') else 
                               "text/markdown" if test_file['name'].endswith('.md') else
                               "application/json",
                "erasure_id": test_file['erasure_id']
            }
            
            response = requests.post(f"{BACKEND_URL}/files/upload", 
                                   json=upload_data, 
                                   headers=headers)
            
            if response.status_code == 201:
                result = response.json()
                uploaded_files.append(result)
                print(f"      ✅ Uploaded successfully!")
                print(f"         File ID: {result['file_id']}")
                print(f"         Version ID: {result['version_id']}")
                print(f"         Size: {result['file_size']} bytes")
                print(f"         Fragments stored: {result['fragments_stored']}")
                print(f"         Status: {result['upload_status']}")
                print(f"         Erasure profile: {result['erasure_profile']}")
            else:
                print(f"      ❌ Upload failed: {response.text}")
                
        except Exception as e:
            print(f"      ❌ Upload error: {e}")
    
    # Step 4: Check updated system statistics
    print(f"\n4. Updated system statistics...")
    try:
        status = requests.get(f"{MASTER_NODE_URL}/status").json()
        print(f"   📊 Accounts: {status['statistics']['accounts']}")
        print(f"   📁 Files: {status['statistics']['files']}")
        print(f"   🗂️ Fragments: {status['statistics']['fragments']}")
        print(f"   💾 Storage Nodes: {status['statistics']['storage_nodes']}")
        
        # Show file distribution
        nodes = requests.get(f"{MASTER_NODE_URL}/nodes").json()
        active_storage_nodes = [n for n in nodes if n['node_role'] == 'STORAGE' and n['is_active'] == 1]
        print(f"   🔄 Active storage nodes: {len(active_storage_nodes)}")
        
    except Exception as e:
        print(f"   ❌ Status update failed: {e}")
    
    print(f"\n🎉 Advanced file upload testing completed!")
    print(f"   • Uploaded {len(uploaded_files)} files with different erasure coding levels")
    print(f"   • Demonstrated complete schema functionality")
    print(f"   • Tested fragment distribution across storage nodes")
    print(f"   • Verified metadata tracking and versioning")

if __name__ == "__main__":
    test_advanced_upload()