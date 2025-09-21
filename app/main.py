# main.py

import os
import sys
import asyncio
import webbrowser
import threading
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates

# Import custom modules
from app.api import app_state, manager, router, initialize_application, cleanup_application
from services.git_operations import GitRepository, MetadataManager, GitLabAPI
from services.config_manager import ConfigManager
from app.models import AppConfig

logger = logging.getLogger(__name__)

# Lifespan event handler
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Mastercam GitLab Interface...")
    await initialize_application()
    yield
    logger.info("Shutting down Mastercam GitLab Interface...")
    await cleanup_application()

# FastAPI setup
app = FastAPI(
    title="Mastercam GitLab Interface",
    description="User-friendly interface for managing Mastercam files with GitLab",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Mount the API router
app.include_router(router)

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

def open_browser(port: int = 8000):
    url = f"http://localhost:{port}"
    logger.info(f"Opening browser to {url}")
    try:
        webbrowser.open(url)
    except Exception as e:
        logger.warning(f"Could not open browser automatically: {e}")

def main():
    logger.info("Starting Mastercam GitLab Interface...")
    if getattr(sys, 'frozen', False):
        logger.info("Running as PyInstaller executable")
    else:
        logger.info("Running as Python script")
    port = 8000
    def delayed_browser_open():
        import time
        time.sleep(3)
        open_browser(port)
    browser_thread = threading.Thread(target=delayed_browser_open, daemon=True)
    browser_thread.start()
    try:
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=port,
            log_level="info",
            access_log=True
        )
    except KeyboardInterrupt:
        logger.info("Application stopped by user")
    except Exception as e:
        logger.error(f"Error starting server: {str(e)}")
        raise

if __name__ == "__main__":
    main()