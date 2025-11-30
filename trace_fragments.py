#!/usr/bin/env python3
"""
Script to trace fragment locations across storage nodes using actual API endpoints
"""
import requests
import json
import time

def main():
    try:
        print("📡 Checking System Status and Fragment Distribution")
        print("=" * 60)
        
        # Check master node status first
        print("🏠 Master Node Status:")
        master_response = requests.get('http://localhost:8000/status')
        if master_response.status_code == 200:
            master_status = master_response.json()
            stats = master_status['statistics']
            
            print(f"   📊 Accounts: {stats['accounts']}")
            print(f"   📁 Files: {stats['files']}")
            print(f"   🗂️  Fragments: {stats['fragments']}")
            print(f"   💾 Storage Nodes: {stats['storage_nodes']}")
            print()
        
        # Check all nodes from master
        print("💾 All Registered Nodes:")
        print("-" * 40)
        nodes_response = requests.get('http://localhost:8000/nodes')
        if nodes_response.status_code == 200:
            nodes = nodes_response.json()
            
            for i, node in enumerate(nodes):
                role = node.get('node_role', 'Unknown')
                hostname = node.get('hostname', 'Unknown')
                api_endpoint = node.get('api_endpoint', 'Unknown')
                is_active = node.get('is_active', 0)
                total_bytes = node.get('total_bytes', 0)
                used_bytes = node.get('used_bytes', 0)
                
                status_icon = "🟢" if is_active else "🔴"
                print(f"   {status_icon} {role}: {hostname}")
                print(f"      Endpoint: {api_endpoint}")
                if total_bytes > 0:
                    print(f"      Storage: {used_bytes:,} / {total_bytes:,} bytes")
                print()
        
        # Get JWT token by logging in to FastAPI
        print("🔐 Authenticating with FastAPI...")
        auth_response = requests.post(
            'http://localhost:8004/auth/login',
            json={
                'username_or_email': 'testuser', 
                'password': 'testpassword'
            }
        )
        
        if auth_response.status_code == 200:
            auth_data = auth_response.json()
            token = auth_data['access_token']
            account_id = auth_data['account_id']
            print(f"✅ Authenticated as: {auth_data['username']} ({auth_data['account_type']})")
            print(f"   Account ID: {account_id}")
            
            # Query master node for files owned by this user
            print(f"\n📁 Files owned by {auth_data['username']}:")
            print("-" * 50)
            
            files_query = {
                "sql": "SELECT fo.file_id, fo.file_name, fo.file_size, fo.logical_path, fo.uploaded_at, fv.version_id, fv.erasure_id FROM file_objects fo JOIN file_versions fv ON fo.file_id = fv.file_id WHERE fo.account_id = ? ORDER BY fo.uploaded_at DESC",
                "params": [account_id]
            }
            
            files_response = requests.post('http://localhost:8000/query', json=files_query)
            
            if files_response.status_code == 200:
                files_result = files_response.json()
                if files_result.get('success') and files_result.get('data'):
                    files = files_result['data']
                    
                    for file_info in files:
                        file_name = file_info['file_name']
                        file_size = file_info['file_size']
                        version_id = file_info['version_id']
                        erasure_id = file_info['erasure_id']
                        uploaded_at = file_info['uploaded_at']
                        
                        print(f"\n   📄 File: {file_name}")
                        print(f"      Size: {file_size:,} bytes")
                        print(f"      Erasure Profile: {erasure_id}")
                        print(f"      Uploaded: {uploaded_at}")
                        print(f"      Version ID: {version_id}")
                        
                        # Get fragment locations for this file version
                        fragments_response = requests.get(f'http://localhost:8000/fragments/locations/{version_id}')
                        
                        if fragments_response.status_code == 200:
                            fragments = fragments_response.json()
                            
                            if fragments:
                                print(f"      📦 Fragments ({len(fragments)}):")
                                for fragment in fragments:
                                    fragment_num = fragment.get('num_fragment', 'Unknown')
                                    node_hostname = fragment.get('hostname', 'Unknown')
                                    api_endpoint = fragment.get('api_endpoint', 'Unknown')
                                    fragment_bytes = fragment.get('bytes', 0)
                                    
                                    print(f"         Fragment {fragment_num}: {node_hostname}")
                                    print(f"           Node: {api_endpoint}")
                                    print(f"           Size: {fragment_bytes:,} bytes")
                            else:
                                print(f"      ⚠️  No fragments found for this file")
                else:
                    print("   📭 No files found for this user")
            else:
                print(f"   ❌ Could not query files (Status: {files_response.status_code})")
                
            # Show recent upload activity
            print(f"\n📈 Recent Upload Activity:")
            print("-" * 50)
            
            recent_query = {
                "sql": "SELECT fo.file_name, fo.file_size, fo.uploaded_at, a.username FROM file_objects fo JOIN account a ON fo.account_id = a.account_id ORDER BY fo.uploaded_at DESC LIMIT 10",
                "params": []
            }
            
            recent_response = requests.post('http://localhost:8000/query', json=recent_query)
            if recent_response.status_code == 200:
                recent_result = recent_response.json()
                if recent_result.get('success') and recent_result.get('data'):
                    recent_files = recent_result['data']
                    for i, file_info in enumerate(recent_files, 1):
                        print(f"   {i}. {file_info['file_name']} ({file_info['file_size']:,} bytes)")
                        print(f"      Uploaded by: {file_info['username']}")
                        print(f"      Date: {file_info['uploaded_at']}")
                        print()
        else:
            print(f"❌ Authentication failed: {auth_response.text}")
                
        print("✅ Fragment tracing completed!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()