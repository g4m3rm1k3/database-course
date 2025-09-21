#!/usr/bin/env python3
"""
Mastercam GitLab Interface - Main Application Runner
This script serves as the single entry point for the application.
It handles dependency checks, server startup, and browser launch.
"""

import os
import sys
import threading
import webbrowser
import time
import logging
import subprocess

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Function to check for required packages
def check_dependencies():
    """Check if required packages are installed and install them if not."""
    try:
        import uvicorn
        import fastapi
        import git
        import pydantic
    except ImportError:
        logger.warning("Required packages not found. Attempting to install from requirements.txt...")
        try:
            # Use the python executable from the active environment
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
            logger.info("Successfully installed required packages. Please re-run the script.")
            # Exit to ensure the environment is refreshed
            sys.exit(0)
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to install dependencies: {e}")
            sys.exit(1)

# Function to start the Uvicorn server
def start_server():
    """Starts the FastAPI server using Uvicorn."""
    try:
        # Import the application from app.py
        from app import app
        import uvicorn
        logger.info("Starting FastAPI server...")
        # Start the Uvicorn server
        uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
    except Exception as e:
        logger.error(f"Failed to start the server: {e}")
        sys.exit(1)

# Function to open the web browser
def open_browser(port: int = 8000):
    """Opens the user's default web browser to the application URL."""
    url = f"http://localhost:{port}"
    logger.info(f"Waiting for server to start at {url}...")
    time.sleep(3)  # Give the server a moment to start
    try:
        webbrowser.open(url)
        logger.info(f"Opened browser to {url}")
    except Exception as e:
        logger.error(f"Failed to open web browser: {e}")

if __name__ == "__main__":
    # Check dependencies before starting the server
    check_dependencies()
    
    # Start the server in a separate thread
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    
    # Open the browser in the main thread
    open_browser()
    
    try:
        # Keep the main thread alive to prevent the application from exiting
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Application shutting down.")
    finally:
        sys.exit(0)