#!/usr/bin/env python3
"""
Simple HTTP server to serve the file upload interface.
This avoids CORS issues when accessing the FastAPI backend.
"""

import http.server
import socketserver
import webbrowser
import threading
import time

PORT = 8081
Handler = http.server.SimpleHTTPRequestHandler

def start_server():
    """Start the HTTP server."""
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"🌐 Starting web server at http://localhost:{PORT}")
        print(f"📁 Serving file interface: simple_file_interface.html")
        print(f"🔗 File sharing demo: file_sharing_demo.html")
        print(f"👥 Shared with me: shared_with_me_interface.html")
        print(f"🗑️ Recycle bin: recycle_bin_interface.html")
        print(f"🔗 API Backend: http://localhost:8004")
        print(f"\n📝 Default login credentials:")
        print(f"   Username: alice")
        print(f"   Password: password123")
        print(f"\n🌟 Features Available:")
        print(f"   • File upload/download with Reed-Solomon erasure coding")
        print(f"   • File sharing with one-time passwords (MEGA-style)")
        print(f"   • User-to-user sharing (Google Drive-style)")
        print(f"   • Recycle bin with 30-day retention")
        print(f"   • Share links with expiration dates")
        print(f"   • View-only and download permissions")
        print(f"\n🚀 Opening browser...")
        print(f"\nPress Ctrl+C to stop the server")
        
        # Auto-open browser after a short delay
        def open_browser():
            time.sleep(2)
            webbrowser.open(f'http://localhost:{PORT}/simple_file_interface.html')
        
        browser_thread = threading.Thread(target=open_browser)
        browser_thread.daemon = True
        browser_thread.start()
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print(f"\n🛑 Server stopped.")

if __name__ == "__main__":
    start_server()