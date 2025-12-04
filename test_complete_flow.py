#!/usr/bin/env python3
"""
Complete End-to-End Test Script for Distributed File Storage System
Tests: Authentication, Upload, Database Metadata, Download, and Cleanup

Usage: python test_complete_flow.py
"""
import requests
import base64
import json
import hashlib
import time
import os
import sys
from typing import Dict, Optional
import psycopg2
from psycopg2.extras import RealDictCursor

# Configuration
BASE_URL = "http://localhost:8004"
MASTER_NODE_URL = "http://localhost:8001"
DB_CONFIG = {
    'host': 'localhost',
    'port': 5433,
    'database': 'database',
    'user': 'user',
    'password': 'password'
}

class FileStorageTestSuite:
    def __init__(self):
        self.access_token = None
        self.account_id = None
        self.username = None
        self.uploaded_files = {}  # Store file IDs for each profile
        self.test_file_data = None
        self.test_file_hash = None
        self.erasure_profiles = ["LOW", "MEDIUM", "HIGH"]
        
        # Create test file data
        self.create_test_file()
    
    def create_test_file(self):
        """Create test file content for upload testing."""
        self.test_file_content = f"""
# Test File for Distributed Storage System
Created at: {time.strftime('%Y-%m-%d %H:%M:%S')}
Random data: {'A' * 1000}{'B' * 500}{'C' * 300}
End of test file.
        """.strip()
        
        self.test_file_data = self.test_file_content.encode('utf-8')
        self.test_file_hash = hashlib.sha256(self.test_file_data).hexdigest()
        self.test_filename_base = f"test_file_{int(time.time())}"
        
        print(f"📝 Created test file base: {self.test_filename_base}")
        print(f"📏 File size: {len(self.test_file_data)} bytes")
        print(f"🔐 File hash: {self.test_file_hash[:16]}...")
    
    def test_1_authentication(self):
        """Test user login and authentication."""
        print("\n🔐 TESTING AUTHENTICATION")
        print("=" * 50)
        
        # Test credentials (using existing test user)
        login_data = {
            "username_or_email": "alice",
            "password": "password123"
        }
        
        try:
            response = requests.post(f"{BASE_URL}/auth/login", json=login_data)
            
            if response.status_code == 200:
                auth_result = response.json()
                self.access_token = auth_result["access_token"]
                self.account_id = auth_result["account_id"]
                self.username = auth_result["username"]
                
                print(f"✅ Login successful!")
                print(f"   Username: {self.username}")
                print(f"   Account ID: {self.account_id}")
                print(f"   Token: {self.access_token[:20]}...")
                return True
            else:
                print(f"❌ Login failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Login error: {str(e)}")
            return False
    
    def test_2_file_upload(self):
        """Test file upload with all Reed-Solomon erasure profiles."""
        print("\n📤 TESTING FILE UPLOAD")
        print("=" * 50)
        
        if not self.access_token:
            print("❌ No access token available")
            return False
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        profile_info = {
            "LOW": {"k": 4, "m": 2, "description": "4+2=6 fragments"},
            "MEDIUM": {"k": 6, "m": 3, "description": "6+3=9 fragments"},
            "HIGH": {"k": 8, "m": 4, "description": "8+4=12 fragments"}
        }
        
        success_count = 0
        
        for profile in self.erasure_profiles:
            try:
                # Prepare upload data for this profile
                test_filename = f"{self.test_filename_base}_{profile.lower()}.txt"
                file_b64 = base64.b64encode(self.test_file_data).decode('utf-8')
                
                upload_data = {
                    "filename": test_filename,
                    "data": file_b64,
                    "content_type": "text/plain",
                    "erasure_id": profile
                }
                
                print(f"\n📋 Testing {profile} profile:")
                print(f"   File: {test_filename}")
                print(f"   Profile: {profile} ({profile_info[profile]['description']})")
                
                response = requests.post(f"{BASE_URL}/files/upload", json=upload_data, headers=headers)
                
                if response.status_code == 201:
                    upload_result = response.json()
                    file_id = upload_result["file_id"]
                    self.uploaded_files[profile] = {
                        "file_id": file_id,
                        "filename": test_filename,
                        "result": upload_result
                    }
                    
                    print(f"   ✅ Upload successful!")
                    print(f"      File ID: {file_id}")
                    print(f"      Upload Status: {upload_result['upload_status']}")
                    print(f"      Fragments Stored: {upload_result['fragments_stored']}")
                    print(f"      Expected k value: {profile_info[profile]['k']}")
                    
                    success_count += 1
                else:
                    print(f"   ❌ Upload failed: {response.status_code} - {response.text}")
                    
            except Exception as e:
                print(f"   ❌ Upload error for {profile}: {str(e)}")
        
        print(f"\n📊 Upload Summary: {success_count}/{len(self.erasure_profiles)} profiles successful")
        return success_count == len(self.erasure_profiles)
    
    def test_3_database_metadata(self):
        """Test database metadata verification via master node API for all uploaded files."""
        print("\n🗄️ TESTING DATABASE METADATA")
        print("=" * 50)
        
        if not self.uploaded_files:
            print("❌ No uploaded files available")
            return False
        
        success_count = 0
        
        for profile, file_info in self.uploaded_files.items():
            try:
                file_id = file_info["file_id"]
                filename = file_info["filename"]
                
                print(f"\n🔗 Testing metadata for {profile} profile:")
                print(f"   File: {filename}")
                print(f"   File ID: {file_id}")
                
                # Query master node for file metadata
                response = requests.get(f"{MASTER_NODE_URL}/files/info/{file_id}")
                
                if response.status_code == 200:
                    file_metadata = response.json()["file"]
                    
                    print(f"   ✅ File metadata retrieved:")
                    print(f"      File Name: {file_metadata['file_name']}")
                    print(f"      File Size: {file_metadata['file_size']} bytes")
                    print(f"      Logical Path: {file_metadata['logical_path']}")
                    print(f"      Erasure ID: {file_metadata['erasure_id']}")
                    
                    # Verify file size matches
                    file_size = int(file_metadata["file_size"])  # Convert to int for comparison
                    if file_size == len(self.test_file_data):
                        print(f"   ✅ File size verification passed")
                    else:
                        print(f"   ❌ File size mismatch: expected {len(self.test_file_data)}, got {file_size}")
                        continue
                    
                    # Query fragments for this file
                    fragments_response = requests.get(f"{MASTER_NODE_URL}/fragments/{file_id}")
                    if fragments_response.status_code == 200:
                        fragments = fragments_response.json()
                        
                        print(f"   ✅ Fragments found:")
                        print(f"      Fragment Count: {len(fragments)}")
                        if fragments:
                            fragment_range = f"{min(f['num_fragment'] for f in fragments)} - {max(f['num_fragment'] for f in fragments)}"
                            print(f"      Fragment Range: {fragment_range}")
                            
                            for i, fragment in enumerate(fragments[:3]):  # Show first 3
                                print(f"      Fragment {fragment['num_fragment']}: Node {fragment['node_id'][:8]}..., Size {fragment['bytes']} bytes")
                            if len(fragments) > 3:
                                print(f"      ... and {len(fragments) - 3} more fragments")
                        
                        success_count += 1
                    else:
                        print(f"   ❌ Failed to retrieve fragments: {fragments_response.status_code}")
                        
                else:
                    print(f"   ❌ Failed to retrieve metadata: {response.status_code} - {response.text}")
                    
            except Exception as e:
                print(f"   ❌ Metadata query error for {profile}: {str(e)}")
        
        print(f"\n🔐 Metadata Summary: {success_count}/{len(self.uploaded_files)} files verified")
        return success_count == len(self.uploaded_files)
    
    def test_4_file_download(self):
        """Test file download and reconstruction for all erasure profiles."""
        print("\n📥 TESTING FILE DOWNLOAD")
        print("=" * 50)
        
        if not self.access_token or not self.uploaded_files:
            print("❌ Missing access token or uploaded files")
            return False
        
        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }
        
        success_count = 0
        
        for profile, file_info in self.uploaded_files.items():
            try:
                file_id = file_info["file_id"]
                filename = file_info["filename"]
                
                print(f"\n📋 Testing download for {profile} profile:")
                print(f"   File: {filename}")
                print(f"   File ID: {file_id}")
                
                response = requests.get(f"{BASE_URL}/files/download/{file_id}", headers=headers)
                
                if response.status_code == 200:
                    # Check if response is raw file data or JSON
                    content_type = response.headers.get('content-type', '')
                    
                    if 'application/octet-stream' in content_type or not content_type.startswith('application/json'):
                        # Raw file data response
                        downloaded_data = response.content
                        downloaded_hash = hashlib.sha256(downloaded_data).hexdigest()
                        
                        print(f"   ✅ Download successful!")
                        print(f"      Downloaded size: {len(downloaded_data)} bytes")
                        print(f"      Downloaded hash: {downloaded_hash[:16]}...")
                        
                        # Verify integrity
                        if downloaded_hash == self.test_file_hash:
                            print(f"   ✅ File integrity verification PASSED")
                        else:
                            print(f"   ❌ File integrity verification FAILED")
                            print(f"      Expected: {self.test_file_hash[:16]}...")
                            print(f"      Got: {downloaded_hash[:16]}...")
                            continue
                        
                        # Verify content
                        if downloaded_data == self.test_file_data:
                            print(f"   ✅ Content verification PASSED")
                            success_count += 1
                        else:
                            print(f"   ❌ Content verification FAILED")
                            continue
                    
                    else:
                        # JSON response (fallback to old logic)
                        try:
                            download_result = response.json()
                            
                            if 'data' in download_result:
                                downloaded_data = base64.b64decode(download_result['data'])
                                downloaded_hash = hashlib.sha256(downloaded_data).hexdigest()
                                
                                print(f"   ✅ Download successful!")
                                print(f"      Downloaded size: {len(downloaded_data)} bytes")
                                print(f"      Downloaded hash: {downloaded_hash[:16]}...")
                                
                                # Verify integrity
                                if downloaded_hash == self.test_file_hash:
                                    print(f"   ✅ File integrity verification PASSED")
                                else:
                                    print(f"   ❌ File integrity verification FAILED")
                                    print(f"      Expected: {self.test_file_hash[:16]}...")
                                    print(f"      Got: {downloaded_hash[:16]}...")
                                    continue
                                
                                # Verify content
                                if downloaded_data == self.test_file_data:
                                    print(f"   ✅ Content verification PASSED")
                                    success_count += 1
                                else:
                                    print(f"   ❌ Content verification FAILED")
                                    continue
                                    
                            elif 'content' in download_result:
                                # Handle plain text response
                                downloaded_content = download_result['content']
                                
                                if downloaded_content == self.test_file_content:
                                    print(f"   ✅ Download successful!")
                                    print(f"      Downloaded size: {len(downloaded_content)} bytes")
                                    print(f"   ✅ Content verification PASSED")
                                    success_count += 1
                                else:
                                    print(f"   ❌ Content verification FAILED")
                                    continue
                            else:
                                print(f"   ❌ No data in download response: {download_result}")
                                continue
                        except Exception as json_error:
                            print(f"   ❌ Failed to parse JSON response: {json_error}")
                            continue
                        
                else:
                    print(f"   ❌ Download failed: {response.status_code} - {response.text}")
                    
            except Exception as e:
                print(f"   ❌ Download error for {profile}: {str(e)}")
        
        print(f"\n📊 Download Summary: {success_count}/{len(self.uploaded_files)} files downloaded successfully")
        return success_count == len(self.uploaded_files)
    
    def test_5_file_info(self):
        """Test file information retrieval for all uploaded files."""
        print("\n📊 TESTING FILE INFO")
        print("=" * 50)
        
        if not self.access_token or not self.uploaded_files:
            print("❌ Missing access token or uploaded files")
            return False
        
        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }
        
        success_count = 0
        
        for profile, file_info in self.uploaded_files.items():
            try:
                file_id = file_info["file_id"]
                filename = file_info["filename"]
                
                print(f"\n📋 Testing file info for {profile} profile:")
                print(f"   File: {filename}")
                
                response = requests.get(f"{BASE_URL}/files/info/{file_id}", headers=headers)
                
                if response.status_code == 200:
                    info_result = response.json()
                    
                    print(f"   ✅ File info retrieved:")
                    print(f"      File ID: {info_result.get('file_id')}")
                    print(f"      File Name: {info_result.get('file_name')}")
                    print(f"      File Size: {info_result.get('file_size')} bytes")
                    print(f"      Logical Path: {info_result.get('logical_path')}")
                    print(f"      Uploaded At: {info_result.get('uploaded_at')}")
                    print(f"      Erasure ID: {info_result.get('erasure_id')}")
                    
                    success_count += 1
                else:
                    print(f"   ❌ File info failed: {response.status_code} - {response.text}")
                    
            except Exception as e:
                print(f"   ❌ File info error for {profile}: {str(e)}")
        
        print(f"\n📊 File Info Summary: {success_count}/{len(self.uploaded_files)} files retrieved successfully")
        return success_count == len(self.uploaded_files)
    
    def test_6_cleanup(self):
        """Clean up test data (optional)."""
        print("\n🧹 CLEANUP (Optional)")
        print("=" * 50)
        
        print("ℹ️  Test files remain in system for manual inspection")
        
        for profile, file_info in self.uploaded_files.items():
            print(f"   {profile}: File ID {file_info['file_id'][:8]}..., Filename: {file_info['filename']}")
        
        return True
        
        # Note: Add file deletion if you have a delete endpoint
        print("ℹ️  Test file remains in system for manual inspection")
        print(f"   File ID: {self.uploaded_file_id}")
        print(f"   Filename: {self.test_filename}")
        return True
    
    def run_all_tests(self):
        """Run the complete test suite."""
        print("🚀 STARTING COMPLETE FILE STORAGE TEST SUITE")
        print("=" * 60)
        
        tests = [
            ("Authentication", self.test_1_authentication),
            ("File Upload", self.test_2_file_upload),
            ("Database Metadata", self.test_3_database_metadata),
            ("File Download", self.test_4_file_download),
            ("File Info", self.test_5_file_info),
            ("Cleanup", self.test_6_cleanup)
        ]
        
        results = {}
        
        for test_name, test_func in tests:
            try:
                result = test_func()
                results[test_name] = "PASSED" if result else "FAILED"
                
                if not result and test_name in ["Authentication", "File Upload"]:
                    print(f"\n❌ Critical test '{test_name}' failed. Stopping test suite.")
                    break
                    
            except Exception as e:
                print(f"\n❌ Test '{test_name}' encountered error: {str(e)}")
                results[test_name] = "ERROR"
        
        # Print summary
        print("\n" + "=" * 60)
        print("📊 TEST SUITE SUMMARY")
        print("=" * 60)
        
        passed = sum(1 for result in results.values() if result == "PASSED")
        total = len(results)
        
        for test_name, result in results.items():
            status_emoji = "✅" if result == "PASSED" else "❌"
            print(f"{status_emoji} {test_name}: {result}")
        
        print(f"\n🎯 Overall Result: {passed}/{total} tests passed")
        
        if passed == total:
            print("🎉 ALL TESTS PASSED! Reed-Solomon implementation with all erasure profiles is working correctly!")
            print(f"   ✅ LOW profile: {len([f for f in self.uploaded_files if f == 'LOW'])} file(s)")
            print(f"   ✅ MEDIUM profile: {len([f for f in self.uploaded_files if f == 'MEDIUM'])} file(s)")  
            print(f"   ✅ HIGH profile: {len([f for f in self.uploaded_files if f == 'HIGH'])} file(s)")
        else:
            print(f"⚠️  {total - passed} test(s) failed. Check the logs above for details.")
        
        return passed == total

def main():
    """Main function to run the test suite."""
    print("🔧 Distributed File Storage System - End-to-End Test")
    print(f"📍 Base URL: {BASE_URL}")
    print(f"📍 Master Node: {MASTER_NODE_URL}")
    print(f"📍 Database: {DB_CONFIG['host']}:{DB_CONFIG['port']}")
    
    # Check if services are available
    try:
        response = requests.get(f"{BASE_URL}/auth/me", timeout=5)
        print("✅ FastAPI service is reachable")
    except:
        print("❌ FastAPI service is not reachable. Make sure docker-compose is running.")
        return False
    
    try:
        response = requests.get(f"{MASTER_NODE_URL}/health", timeout=5)
        print("✅ Master Node service is reachable")
    except:
        print("❌ Master Node service is not reachable. Make sure docker-compose is running.")
        return False
    
    # Run test suite
    test_suite = FileStorageTestSuite()
    return test_suite.run_all_tests()

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)