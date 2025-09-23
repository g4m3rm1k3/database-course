#!/usr/bin/env python3
"""
Mastercam GitLab Interface - Runner
This script imports the application from core_app.py and starts the Uvicorn server.
"""

import uvicorn
import webbrowser
import threading
import sys

# Import the main FastAPI app object from your other file
from core_app import app

def main():
    port = 8000
    if not getattr(sys, 'frozen', False):
        threading.Timer(2.0, lambda: webbrowser.open(f"http://localhost:{port}")).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")

if __name__ == "__main__":
    main()