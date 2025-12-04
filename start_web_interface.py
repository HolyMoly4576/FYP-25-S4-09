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
        print(f"🔗 API Backend: http://localhost:8004")
        print(f"\n📝 Default login credentials:")
        print(f"   Username: alice")
        print(f"   Password: password123")
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