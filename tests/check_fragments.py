#!/usr/bin/env python3
"""
Script to trace fragment locations across storage nodes
"""
import requests
import json

def main():
    try:
        # Get JWT token by logging in
        print("🔐 Authenticating with backend...")
        auth_response = requests.post(
            'http://localhost:8004/auth/login',
            json={
                'username_or_email': 'testuser', 
                'password': 'testpassword'
            }
        )
        
        if auth_response.status_code != 200:
            print(f"❌ Authentication failed: {auth_response.text}")
            return
            
        auth_data = auth_response.json()
        token = auth_data['access_token']
        print(f"✅ Authenticated as: {auth_data['username']} ({auth_data['account_type']})")
        
        headers = {'Authorization': f'Bearer {token}'}
        
        # Check storage node status
        print("\n📊 Storage Node Status:")
        print("=" * 50)
        storage_response = requests.get(
            'http://localhost:8004/storage',
            headers=headers
        )
        
        if storage_response.status_code == 200:
            storage_data = storage_response.json()
            print(f"Total storage nodes: {len(storage_data)}")
            
            for i, node in enumerate(storage_data):
                node_url = node.get('node_url', 'Unknown')
                status = node.get('status', 'Unknown')
                capacity = node.get('capacity_bytes', 0)
                used = node.get('used_bytes', 0)
                
                print(f"  Node {i+1}: {node_url}")
                print(f"    Status: {status}")
                print(f"    Capacity: {capacity:,} bytes")
                print(f"    Used: {used:,} bytes")
                print()
        
        # Check recent files and their fragments
        print("📁 Recent Files and Fragment Distribution:")
        print("=" * 50)
        files_response = requests.get(
            'http://localhost:8004/files',
            headers=headers
        )
        
        if files_response.status_code == 200:
            files_data = files_response.json()
            
            # Show last 5 files (including our test uploads)
            recent_files = files_data[-5:] if len(files_data) >= 5 else files_data
            
            for file_info in recent_files:
                filename = file_info.get('filename', 'Unknown')
                file_id = file_info.get('file_id', 'Unknown')
                file_size = file_info.get('file_size', 0)
                erasure_profile = file_info.get('erasure_profile', 'Unknown')
                created_at = file_info.get('created_at', 'Unknown')
                
                print(f"\n📄 File: {filename}")
                print(f"   ID: {file_id}")
                print(f"   Size: {file_size:,} bytes")
                print(f"   Erasure Profile: {erasure_profile}")
                print(f"   Created: {created_at}")
                
                # Get detailed fragment information
                file_detail_response = requests.get(
                    f'http://localhost:8004/files/{file_id}',
                    headers=headers
                )
                
                if file_detail_response.status_code == 200:
                    file_detail = file_detail_response.json()
                    fragments = file_detail.get('fragments', [])
                    versions = file_detail.get('versions', [])
                    
                    print(f"   Total Fragments: {len(fragments)}")
                    
                    if versions:
                        latest_version = versions[-1]  # Get latest version
                        print(f"   Version: {latest_version.get('version_id', 'Unknown')}")
                        print(f"   Status: {latest_version.get('status', 'Unknown')}")
                    
                    print("   Fragment Distribution:")
                    for j, fragment in enumerate(fragments):
                        storage_url = fragment.get('storage_node_url', 'Unknown')
                        fragment_index = fragment.get('fragment_index', 'Unknown')
                        fragment_size = fragment.get('fragment_size', 0)
                        checksum = fragment.get('checksum', 'Unknown')[:8] + '...'
                        
                        print(f"     Fragment {j+1}: {storage_url}")
                        print(f"       Index: {fragment_index}")
                        print(f"       Size: {fragment_size:,} bytes")
                        print(f"       Checksum: {checksum}")
                else:
                    print(f"   ❌ Could not get fragment details (Status: {file_detail_response.status_code})")
        else:
            print(f"❌ Could not get files list (Status: {files_response.status_code})")
            
        # Show system statistics
        print("\n📈 System Statistics:")
        print("=" * 50)
        stats_response = requests.get(
            'http://localhost:8004/stats',
            headers=headers
        )
        
        if stats_response.status_code == 200:
            stats = stats_response.json()
            print(f"Total Accounts: {stats.get('total_accounts', 0)}")
            print(f"Total Files: {stats.get('total_files', 0)}")
            print(f"Total Fragments: {stats.get('total_fragments', 0)}")
            print(f"Total Storage Used: {stats.get('total_storage_used', 0):,} bytes")
            print(f"Active Storage Nodes: {stats.get('active_storage_nodes', 0)}")
            
        print("\n✅ Fragment tracing completed!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()