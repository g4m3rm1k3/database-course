#!/usr/bin/env python3
"""
Mastercam GitLab Interface - Integrated Main Application
Enhanced version with Git operations, configuration management, and full functionality
"""

import os
import sys
import asyncio
import webbrowser
import threading
import logging
import tempfile
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Form, UploadFile, File, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.websockets import WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Import our custom modules
from git_operations import GitRepository, MetadataManager, GitLabAPI, GitOperationError
from config_manager import ConfigManager, AppConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('mastercam_git_interface.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Data models
class FileInfo(BaseModel):
    filename: str
    path: str
    status: str  # "unlocked", "locked", "checked_out_by_user"
    locked_by: Optional[str] = None
    locked_at: Optional[str] = None
    size: Optional[int] = None
    modified_at: Optional[str] = None
    version_info: Optional[Dict] = None

class CheckoutRequest(BaseModel):
    user: str

class AdminOverrideRequest(BaseModel):
    admin_user: str

class ConfigUpdateRequest(BaseModel):
    gitlab_url: str
    project_id: str
    username: str
    token: str

# Global application state
app_state = {
    'config_manager': None,
    'git_repo': None,
    'metadata_manager': None,
    'gitlab_api': None,
    'initialized': False,
    'current_user': 'demo_user'  # Will be replaced with proper auth
}

# Initialize FastAPI app
app = FastAPI(
    title="Mastercam GitLab Interface",
    description="User-friendly interface for managing Mastercam files with GitLab",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    """Enhanced WebSocket connection manager"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.user_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user: str = "anonymous"):
        await websocket.accept()
        self.active_connections.append(websocket)

        if user not in self.user_connections:
            self.user_connections[user] = []
        self.user_connections[user].append(websocket)

        logger.info(f"WebSocket connection established for user '{user}'. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

        # Remove from user connections
        for user, connections in self.user_connections.items():
            if websocket in connections:
                connections.remove(websocket)
                break

        logger.info(f"WebSocket connection closed. Total: {len(self.active_connections)}")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        try:
            await websocket.send_text(message)
        except:
            self.disconnect(websocket)

    async def send_to_user(self, message: str, user: str):
        """Send message to all connections for a specific user"""
        if user in self.user_connections:
            disconnected = []
            for connection in self.user_connections[user]:
                try:
                    await connection.send_text(message)
                except:
                    disconnected.append(connection)

            # Clean up disconnected connections
            for connection in disconnected:
                self.disconnect(connection)

    async def broadcast(self, message: str):
        """Send message to all connected clients"""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                disconnected.append(connection)

        # Clean up disconnected clients
        for connection in disconnected:
            self.disconnect(connection)

manager = ConnectionManager()

# Startup and shutdown events
@app.on_event("startup")
async def startup_event():
    """Initialize application on startup"""
    logger.info("Starting Mastercam GitLab Interface...")
    await initialize_application()

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on application shutdown"""
    logger.info("Shutting down Mastercam GitLab Interface...")
    await cleanup_application()

async def initialize_application():
    """Initialize application components"""
    try:
        # Initialize configuration manager
        app_state['config_manager'] = ConfigManager()
        config = app_state['config_manager'].config

        # Initialize metadata manager
        metadata_path = Path(config.local.temp_path) / 'metadata'
        app_state['metadata_manager'] = MetadataManager(metadata_path)

        # Initialize GitLab API if configured
        if config.gitlab.base_url and config.gitlab.token:
            app_state['gitlab_api'] = GitLabAPI(
                config.gitlab.base_url,
                config.gitlab.token,
                config.gitlab.project_id
            )

            # Test GitLab connection
            if app_state['gitlab_api'].test_connection():
                logger.info("GitLab connection established")

                # Initialize Git repository
                app_state['git_repo'] = GitRepository(
                    Path(config.local.repo_path),
                    f"{config.gitlab.base_url}/{config.gitlab.project_id}.git",
                    config.gitlab.username,
                    config.gitlab.token
                )

                # Clone or update repository
                if app_state['git_repo'].clone_or_pull():
                    logger.info("Repository synchronized")
                    app_state['initialized'] = True
                else:
                    logger.warning("Failed to synchronize repository")
            else:
                logger.warning("GitLab connection failed")
        else:
            logger.info("GitLab not configured, running in demo mode")

        # Cleanup stale locks
        if app_state['metadata_manager']:
            cleaned = app_state['metadata_manager'].cleanup_stale_locks()
            if cleaned > 0:
                logger.info(f"Cleaned up {cleaned} stale file locks")

        logger.info("Application initialization completed")

    except Exception as e:
        logger.error(f"Failed to initialize application: {str(e)}")

async def cleanup_application():
    """Cleanup application resources"""
    try:
        # Close WebSocket connections
        for connection in manager.active_connections:
            await connection.close()

        # Save configuration
        if app_state['config_manager']:
            app_state['config_manager'].save_config()

        logger.info("Application cleanup completed")

    except Exception as e:
        logger.error(f"Error during cleanup: {str(e)}")

# Configuration endpoints
@app.get("/config")
async def get_config():
    """Get current configuration summary"""
    try:
        if app_state['config_manager']:
            return app_state['config_manager'].get_config_summary()
        return {"error": "Configuration not available"}
    except Exception as e:
        logger.error(f"Error getting configuration: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get configuration")

@app.post("/config/gitlab")
async def update_gitlab_config(request: ConfigUpdateRequest):
    """Update GitLab configuration"""
    try:
        config_manager = app_state['config_manager']
        if not config_manager:
            raise HTTPException(status_code=500, detail="Configuration manager not available")

        # Update configuration
        success = config_manager.update_gitlab_config(
            request.gitlab_url,
            request.project_id,
            request.username,
            request.token
        )

        if success:
            # Reinitialize GitLab components
            await initialize_application()
            return {"status": "success", "message": "GitLab configuration updated"}
        else:
            raise HTTPException(status_code=500, detail="Failed to update configuration")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating GitLab configuration: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Main API endpoints
@app.get("/")
async def root():
    """Serve the main web interface"""
    return HTMLResponse(get_enhanced_html_interface())

@app.get("/files", response_model=List[FileInfo])
async def get_files():
    """Fetch all project files with their metadata"""
    try:
        files = []

        if app_state['git_repo'] and app_state['initialized']:
            # Get files from Git repository
            repo_files = app_state['git_repo'].list_files("*.mcam")

            for file_data in repo_files:
                file_info = FileInfo(
                    filename=file_data['name'],
                    path=file_data['path'],
                    status="unlocked",
                    size=file_data['size'],
                    modified_at=file_data['modified_at']
                )

                # Check lock status
                lock_info = app_state['metadata_manager'].get_lock_info(file_data['path'])
                if lock_info:
                    file_info.status = "locked"
                    file_info.locked_by = lock_info['user']
                    file_info.locked_at = lock_info['timestamp']

                    # Check if locked by current user
                    if lock_info['user'] == app_state['current_user']:
                        file_info.status = "checked_out_by_user"

                # Get version history
                if app_state['git_repo']:
                    history = app_state['git_repo'].get_file_history(file_data['path'], limit=5)
                    if history:
                        file_info.version_info = {
                            'latest_commit': history[0]['commit_hash'][:8],
                            'latest_author': history[0]['author_name'],
                            'commit_count': len(history)
                        }

                files.append(file_info)
        else:
            # Return demo data if not initialized
            files = get_demo_files()

        logger.info(f"Retrieved {len(files)} files")
        return files

    except Exception as e:
        logger.error(f"Error fetching files: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch files")

@app.post("/files/{filename}/checkout")
async def checkout_file(filename: str, request: CheckoutRequest):
    """Lock file for editing by specified user"""
    try:
        if not app_state['metadata_manager']:
            raise HTTPException(status_code=500, detail="Metadata manager not available")

        # Find file path
        file_path = find_file_path(filename)
        if not file_path:
            raise HTTPException(status_code=404, detail="File not found")

        # Create lock
        success = app_state['metadata_manager'].create_lock(file_path, request.user)
        if not success:
            lock_info = app_state['metadata_manager'].get_lock_info(file_path)
            if lock_info and lock_info['user'] != request.user:
                raise HTTPException(
                    status_code=409,
                    detail=f"File is already locked by {lock_info['user']}"
                )

        logger.info(f"File '{filename}' checked out by '{request.user}'")

        # Notify all clients
        await manager.broadcast(f"FILE_STATUS_CHANGED:{filename}:locked:{request.user}")

        return JSONResponse({
            "status": "success",
            "message": f"File '{filename}' checked out successfully",
            "download_url": f"/files/{filename}/download"
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking out file '{filename}': {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to checkout file")

@app.post("/files/{filename}/checkin")
async def checkin_file(
    filename: str,
    background_tasks: BackgroundTasks,
    user: str = Form(...),
    file: UploadFile = File(...)
):
    """Upload edited file and release lock"""
    try:
        if not app_state['metadata_manager']:
            raise HTTPException(status_code=500, detail="Metadata manager not available")

        # Find file path
        file_path = find_file_path(filename)
        if not file_path:
            raise HTTPException(status_code=404, detail="File not found")

        # Verify lock ownership
        lock_info = app_state['metadata_manager'].get_lock_info(file_path)
        if not lock_info:
            raise HTTPException(status_code=409, detail="File is not locked")

        if lock_info['user'] != user:
            raise HTTPException(
                status_code=409,
                detail="File is locked by a different user"
            )

        # Read file content
        content = await file.read()

        # Validate file
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        max_size = app_state['config_manager'].config.local.max_file_size_mb * 1024 * 1024
        if len(content) > max_size:
            raise HTTPException(
                status_code=400,
                detail=f"File size exceeds maximum allowed size ({max_size // 1024 // 1024} MB)"
            )

        # Save file and commit in background
        background_tasks.add_task(
            process_checkin,
            file_path,
            content,
            user,
            filename
        )

        # Release lock immediately
        app_state['metadata_manager'].release_lock(file_path, user)

        logger.info(f"File '{filename}' check-in initiated by '{user}'")

        # Notify clients
        await manager.broadcast(f"FILE_STATUS_CHANGED:{filename}:unlocked:")

        return JSONResponse({
            "status": "success",
            "message": f"File '{filename}' is being processed"
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking in file '{filename}': {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to checkin file")

async def process_checkin(file_path: str, content: bytes, user: str, filename: str):
    """Process file check-in in background"""
    try:
        if app_state['git_repo'] and app_state['initialized']:
            # Create backup if enabled
            if app_state['config_manager'].config.local.auto_backup:
                create_backup(file_path, content)

            # Save file to repository
            if app_state['git_repo'].save_file(file_path, content):
                # Commit and push changes
                commit_message = f"Update {filename} by {user}"
                success = app_state['git_repo'].commit_and_push(
                    file_path,
                    commit_message,
                    user,
                    f"{user}@example.com"  # TODO: Get real email from config
                )

                if success:
                    logger.info(f"File '{filename}' successfully committed and pushed")
                    # Notify clients of successful commit
                    await manager.broadcast(f"FILE_COMMITTED:{filename}:{user}")
                else:
                    logger.error(f"Failed to commit file '{filename}'")
                    await manager.broadcast(f"FILE_COMMIT_FAILED:{filename}:{user}")
            else:
                logger.error(f"Failed to save file '{filename}'")
        else:
            logger.warning(f"Repository not available, file '{filename}' not committed")

    except Exception as e:
        logger.error(f"Error processing check-in for '{filename}': {str(e)}")

def create_backup(file_path: str, content: bytes):
    """Create backup of file before overwriting"""
    try:
        backup_dir = Path(app_state['config_manager'].config.local.backup_path)
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"{Path(file_path).stem}_{timestamp}{Path(file_path).suffix}"
        backup_path = backup_dir / backup_filename

        backup_path.write_bytes(content)
        logger.info(f"Backup created: {backup_path}")

    except Exception as e:
        logger.error(f"Failed to create backup: {str(e)}")

@app.post("/files/{filename}/override")
async def admin_override(filename: str, request: AdminOverrideRequest):
    """Admin override to forcibly unlock file"""
    try:
        if not app_state['metadata_manager']:
            raise HTTPException(status_code=500, detail="Metadata manager not available")

        # Find file path
        file_path = find_file_path(filename)
        if not file_path:
            raise HTTPException(status_code=404, detail="File not found")

        # Release lock
        lock_info = app_state['metadata_manager'].get_lock_info(file_path)
        previous_user = lock_info['user'] if lock_info else 'none'

        app_state['metadata_manager'].release_lock(file_path)

        logger.info(f"Admin '{request.admin_user}' overrode lock on '{filename}' (was locked by '{previous_user}')")

        # Notify all clients
        await manager.broadcast(f"FILE_STATUS_CHANGED:{filename}:unlocked:")

        return JSONResponse({
            "status": "success",
            "message": f"File '{filename}' unlocked by admin"
        })

    except Exception as e:
        logger.error(f"Error in admin override for file '{filename}': {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to override file lock")

@app.get("/files/{filename}/download")
async def download_file(filename: str):
    """Download file for local editing"""
    try:
        # Find file path
        file_path = find_file_path(filename)
        if not file_path:
            raise HTTPException(status_code=404, detail="File not found")

        if app_state['git_repo'] and app_state['initialized']:
            # Get file content from repository
            content = app_state['git_repo'].get_file_content(file_path)
            if content is None:
                raise HTTPException(status_code=404, detail="File not found in repository")

            # Create temporary file for download
            temp_dir = Path(tempfile.gettempdir()) / 'mastercam_downloads'
            temp_dir.mkdir(exist_ok=True)

            temp_file = temp_dir / filename
            temp_file.write_bytes(content)

            logger.info(f"File '{filename}' prepared for download")

            return FileResponse(
                path=str(temp_file),
                filename=filename,
                media_type='application/octet-stream'
            )
        else:
            raise HTTPException(status_code=501, detail="Repository not available")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading file '{filename}': {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to download file")

@app.get("/files/{filename}/history")
async def get_file_history(filename: str):
    """Get file version history"""
    try:
        file_path = find_file_path(filename)
        if not file_path:
            raise HTTPException(status_code=404, detail="File not found")

        if app_state['git_repo'] and app_state['initialized']:
            history = app_state['git_repo'].get_file_history(file_path, limit=20)
            return {"filename": filename, "history": history}
        else:
            return {"filename": filename, "history": []}

    except Exception as e:
        logger.error(f"Error getting file history for '{filename}': {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get file history")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, user: str = "anonymous"):
    """WebSocket endpoint for real-time updates"""
    await manager.connect(websocket, user)
    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"WebSocket message from {user}: {data}")

            # Handle specific WebSocket commands
            if data.startswith("PING"):
                await manager.send_personal_message("PONG", websocket)
            elif data.startswith("SET_USER:"):
                new_user = data.split(":", 1)[1]
                app_state['current_user'] = new_user

    except WebSocketDisconnect:
        manager.disconnect(websocket)

def find_file_path(filename: str) -> Optional[str]:
    """Find full path for a filename in the repository"""
    try:
        if app_state['git_repo'] and app_state['initialized']:
            files = app_state['git_repo'].list_files("*.mcam")
            for file_data in files:
                if file_data['name'] == filename:
                    return file_data['path']
        return filename  # Fallback to filename
    except Exception as e:
        logger.error(f"Error finding file path for '{filename}': {str(e)}")
        return filename

def get_demo_files() -> List[FileInfo]:
    """Get demo files when repository is not available"""
    return [
        FileInfo(
            filename="part_001.mcam",
            path="parts/part_001.mcam",
            status="unlocked",
            size=2048576,
            modified_at="2024-01-15T10:30:00Z",
            version_info={"latest_commit": "abc12345", "latest_author": "demo_user", "commit_count": 3}
        ),
        FileInfo(
            filename="assembly_main.mcam",
            path="assemblies/assembly_main.mcam",
            status="unlocked",
            size=5242880,
            modified_at="2024-01-15T09:15:00Z",
            version_info={"latest_commit": "def67890", "latest_author": "demo_user", "commit_count": 7}
        ),
        FileInfo(
            filename="fixture_design.mcam",
            path="fixtures/fixture_design.mcam",
            status="unlocked",
            size=1572864,
            modified_at="2024-01-14T16:45:00Z",
            version_info={"latest_commit": "ghi11111", "latest_author": "demo_user", "commit_count": 2}
        )
    ]

def get_enhanced_html_interface():
    """Return enhanced HTML interface"""
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mastercam GitLab Interface</title>
    <style>
        * {
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }

        .header {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 20px 30px;
            margin-bottom: 20px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
        }

        .header h1 {
            margin: 0;
            color: #333;
            font-size: 2.5rem;
            text-align: center;
            background: linear-gradient(135deg, #667eea, #764ba2);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }

        .header .subtitle {
            text-align: center;
            color: #666;
            margin-top: 10px;
            font-size: 1.1rem;
        }

        .status-bar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: rgba(255, 255, 255, 0.9);
            backdrop-filter: blur(10px);
            border-radius: 10px;
            padding: 15px 25px;
            margin-bottom: 20px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
        }

        .status-item {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .status-indicator {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }

        .connected { background-color: #28a745; }
        .disconnected { background-color: #dc3545; }
        .syncing { background-color: #ffc107; }

        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.5; }
            100% { opacity: 1; }
        }

        .main-content {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
            overflow: hidden;
        }

        .controls {
            padding: 20px 30px;
            border-bottom: 1px solid #eee;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .search-box {
            position: relative;
            flex-grow: 1;
            max-width: 400px;
        }

        .search-box input {
            width: 100%;
            padding: 12px 20px 12px 45px;
            border: 2px solid #e9ecef;
            border-radius: 25px;
            font-size: 16px;
            transition: border-color 0.3s;
        }

        .search-box input:focus {
            outline: none;
            border-color: #667eea;
        }

        .search-icon {
            position: absolute;
            left: 15px;
            top: 50%;
            transform: translateY(-50%);
            color: #999;
        }

        .file-list {
            display: grid;
            gap: 1px;
            background: #f8f9fa;
        }

        .file-item {
            background: white;
            padding: 25px 30px;
            transition: all 0.3s ease;
            border-left: 4px solid transparent;
        }

        .file-item:hover {
            background: #f8f9fa;
            border-left-color: #667eea;
        }

        .file-item.locked {
            border-left-color: #dc3545;
            background: #fff5f5;
        }

        .file-item.checked-out {
            border-left-color: #28a745;
            background: #f0fff4;
        }

        .file-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 15px;
        }

        .file-title {
            display: flex;
            align-items: center;
            gap: 15px;
        }

        .file-name {
            font-size: 1.3rem;
            font-weight: 600;
            color: #333;
            margin: 0;
        }

        .status-badge {
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.85rem;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .status-unlocked {
            background: #d4edda;
            color: #155724;
        }

        .status-locked {
            background: #f8d7da;
            color: #721c24;
        }

        .status-checked-out {
            background: #d1ecf1;
            color: #0c5460;
        }

        .file-details {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 15px;
            color: #666;
            font-size: 0.95rem;
        }

        .detail-item {
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .detail-icon {
            font-size: 1.1rem;
        }

        .actions {
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
        }

        .btn {
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.95rem;
            font-weight: 500;
            transition: all 0.3s ease;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }

        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        }

        .btn-primary {
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
        }

        .btn-success {
            background: linear-gradient(135deg, #28a745, #20c997);
            color: white;
        }

        .btn-warning {
            background: linear-gradient(135deg, #ffc107, #fd7e14);
            color: #333;
        }

        .btn-secondary {
            background: linear-gradient(135deg, #6c757d, #495057);
            color: white;
        }

        .btn:disabled {
            background: #e9ecef;
            color: #6c757d;
            cursor: not-allowed;
            transform: none;
            box-shadow: none;
        }

        .config-panel {
            position: fixed;
            top: 0;
            right: -400px;
            width: 400px;
            height: 100vh;
            background: white;
            box-shadow: -4px 0 20px rgba(0, 0, 0, 0.1);
            transition: right 0.3s ease;
            z-index: 1000;
            padding: 30px;
            overflow-y: auto;
        }

        .config-panel.open {
            right: 0;
        }

        .config-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 1px solid #eee;
        }

        .config-form .form-group {
            margin-bottom: 20px;
        }

        .config-form label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #333;
        }

        .config-form input {
            width: 100%;
            padding: 12px;
            border: 2px solid #e9ecef;
            border-radius: 8px;
            font-size: 16px;
            transition: border-color 0.3s;
        }

        .config-form input:focus {
            outline: none;
            border-color: #667eea;
        }

        .notification {
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 15px 25px;
            border-radius: 8px;
            color: white;
            font-weight: 500;
            z-index: 1100;
            transform: translateX(400px);
            transition: transform 0.3s ease;
        }

        .notification.show {
            transform: translateX(0);
        }

        .notification.success {
            background: #28a745;
        }

        .notification.error {
            background: #dc3545;
        }

        .notification.info {
            background: #17a2b8;
        }

        .floating-controls {
            position: fixed;
            bottom: 30px;
            right: 30px;
            display: flex;
            flex-direction: column;
            gap: 15px;
        }

        .fab {
            width: 56px;
            height: 56px;
            border-radius: 50%;
            border: none;
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            font-size: 1.5rem;
            cursor: pointer;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
            transition: all 0.3s ease;
        }

        .fab:hover {
            transform: scale(1.1);
            box-shadow: 0 6px 30px rgba(0, 0, 0, 0.3);
        }

        #fileUpload {
            display: none;
        }

        .loading {
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 40px;
        }

        .spinner {
            width: 40px;
            height: 40px;
            border: 4px solid #f3f3f3;
            border-top: 4px solid #667eea;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        @media (max-width: 768px) {
            .container {
                padding: 10px;
            }

            .header h1 {
                font-size: 2rem;
            }

            .status-bar {
                flex-direction: column;
                gap: 10px;
                text-align: center;
            }

            .controls {
                flex-direction: column;
                gap: 15px;
            }

            .file-details {
                grid-template-columns: 1fr;
            }

            .config-panel {
                width: 100vw;
                right: -100vw;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Mastercam GitLab Interface</h1>
            <div class="subtitle">Collaborative CAM file management</div>
        </div>

        <div class="status-bar">
            <div class="status-item">
                <div class="status-indicator connected" id="connectionStatus"></div>
                <span id="connectionText">Connected</span>
            </div>
            <div class="status-item">
                <strong>User:</strong> <span id="currentUser">demo_user</span>
            </div>
            <div class="status-item">
                <strong>Repository:</strong> <span id="repoStatus">Ready</span>
            </div>
        </div>

        <div class="main-content">
            <div class="controls">
                <div class="search-box">
                    <span class="search-icon">🔍</span>
                    <input type="text" id="searchInput" placeholder="Search files...">
                </div>
                <button class="btn btn-secondary" onclick="toggleConfigPanel()">
                    ⚙️ Settings
                </button>
            </div>

            <div id="fileList" class="file-list">
                <div class="loading">
                    <div class="spinner"></div>
                </div>
            </div>
        </div>
    </div>

    <!-- Configuration Panel -->
    <div id="configPanel" class="config-panel">
        <div class="config-header">
            <h3>Settings</h3>
            <button class="btn btn-secondary" onclick="toggleConfigPanel()">✕</button>
        </div>

        <form class="config-form" id="configForm">
            <div class="form-group">
                <label for="gitlabUrl">GitLab URL</label>
                <input type="url" id="gitlabUrl" placeholder="https://gitlab.example.com" required>
            </div>

            <div class="form-group">
                <label for="projectId">Project ID</label>
                <input type="text" id="projectId" placeholder="123" required>
            </div>

            <div class="form-group">
                <label for="username">Username</label>
                <input type="text" id="username" placeholder="your.username" required>
            </div>

            <div class="form-group">
                <label for="token">Access Token</label>
                <input type="password" id="token" placeholder="glpat-xxxxxxxxxxxxxxxxxxxx" required>
            </div>

            <button type="submit" class="btn btn-primary" style="width: 100%;">
                💾 Save Configuration
            </button>
        </form>

        <div style="margin-top: 30px; padding-top: 30px; border-top: 1px solid #eee;">
            <h4>Current Status</h4>
            <div id="configStatus">
                <p><strong>Status:</strong> <span id="configStatusText">Not configured</span></p>
                <p><strong>Repository:</strong> <span id="configRepoText">Not available</span></p>
            </div>
        </div>
    </div>

    <!-- Floating Controls -->
    <div class="floating-controls">
        <button class="fab" title="Refresh" onclick="loadFiles()">🔄</button>
        <button class="fab" title="Settings" onclick="toggleConfigPanel()">⚙️</button>
    </div>

    <input type="file" id="fileUpload" accept=".mcam">

    <script>
        let currentUser = 'demo_user';
        let ws = null;
        let files = [];
        let currentConfig = null;

        // Initialize WebSocket connection
        function connectWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws?user=${encodeURIComponent(currentUser)}`;

            ws = new WebSocket(wsUrl);

            ws.onopen = function(event) {
                console.log('WebSocket connected');
                updateConnectionStatus(true);
                ws.send(`SET_USER:${currentUser}`);
            };

            ws.onmessage = function(event) {
                console.log('WebSocket message:', event.data);
                handleWebSocketMessage(event.data);
            };

            ws.onclose = function(event) {
                console.log('WebSocket disconnected');
                updateConnectionStatus(false);
                setTimeout(connectWebSocket, 3000);
            };

            ws.onerror = function(error) {
                console.error('WebSocket error:', error);
                updateConnectionStatus(false);
            };

            // Send periodic ping to keep connection alive
            setInterval(() => {
                if (ws && ws.readyState === WebSocket.OPEN) {
                    ws.send('PING');
                }
            }, 30000);
        }

        function updateConnectionStatus(connected) {
            const statusEl = document.getElementById('connectionStatus');
            const textEl = document.getElementById('connectionText');

            statusEl.className = `status-indicator ${connected ? 'connected' : 'disconnected'}`;
            textEl.textContent = connected ? 'Connected' : 'Disconnected';
        }

        function handleWebSocketMessage(message) {
            if (message.startsWith('FILE_STATUS_CHANGED:')) {
                loadFiles();
                const parts = message.split(':');
                if (parts.length >= 3) {
                    showNotification(`File ${parts[1]} status changed`, 'info');
                }
            } else if (message.startsWith('FILE_COMMITTED:')) {
                const parts = message.split(':');
                if (parts.length >= 3) {
                    showNotification(`File ${parts[1]} committed successfully`, 'success');
                }
                loadFiles();
            } else if (message.startsWith('FILE_COMMIT_FAILED:')) {
                const parts = message.split(':');
                if (parts.length >= 3) {
                    showNotification(`Failed to commit file ${parts[1]}`, 'error');
                }
            } else if (message === 'PONG') {
                // Handle ping response
                console.log('WebSocket ping successful');
            }
        }

        // Load files from server
        async function loadFiles() {
            try {
                const response = await fetch('/files');
                files = await response.json();
                renderFiles();
                updateRepoStatus('Ready');
            } catch (error) {
                console.error('Error loading files:', error);
                showNotification('Error loading files', 'error');
                updateRepoStatus('Error');
            }
        }

        function updateRepoStatus(status) {
            document.getElementById('repoStatus').textContent = status;
        }

        // Load configuration
        async function loadConfig() {
            try {
                const response = await fetch('/config');
                currentConfig = await response.json();
                updateConfigDisplay();
            } catch (error) {
                console.error('Error loading config:', error);
            }
        }

        function updateConfigDisplay() {
            if (currentConfig) {
                document.getElementById('configStatusText').textContent = 
                    currentConfig.has_token ? 'Configured' : 'Not configured';
                document.getElementById('configRepoText').textContent = 
                    currentConfig.repo_path || 'Not available';

                // Update form fields
                document.getElementById('gitlabUrl').value = currentConfig.gitlab_url || '';
                document.getElementById('projectId').value = currentConfig.project_id || '';
                document.getElementById('username').value = currentConfig.username || '';
            }
        }

        // Render files in the UI
        function renderFiles() {
            const fileListEl = document.getElementById('fileList');
            const searchTerm = document.getElementById('searchInput').value.toLowerCase();

            const filteredFiles = files.filter(file => 
                file.filename.toLowerCase().includes(searchTerm) ||
                file.path.toLowerCase().includes(searchTerm)
            );

            if (filteredFiles.length === 0) {
                fileListEl.innerHTML = `
                    <div style="text-align: center; padding: 60px; color: #666;">
                        <div style="font-size: 4rem; margin-bottom: 20px;">📁</div>
                        <h3>No files found</h3>
                        <p>No Mastercam files match your search criteria.</p>
                    </div>
                `;
                return;
            }

            fileListEl.innerHTML = '';

            filteredFiles.forEach(file => {
                const fileEl = document.createElement('div');
                fileEl.className = `file-item ${file.status.replace('_', '-')}`;

                const statusText = getStatusText(file);
                const statusClass = `status-${file.status.replace('_', '-')}`;

                fileEl.innerHTML = `
                    <div class="file-header">
                        <div class="file-title">
                            <h3 class="file-name">${file.filename}</h3>
                            <span class="status-badge ${statusClass}">${statusText}</span>
                        </div>
                        <div class="actions">
                            ${getActionButtons(file)}
                        </div>
                    </div>

                    <div class="file-details">
                        <div class="detail-item">
                            <span class="detail-icon">📄</span>
                            <span>Path: ${file.path}</span>
                        </div>
                        <div class="detail-item">
                            <span class="detail-icon">💾</span>
                            <span>Size: ${formatBytes(file.size)}</span>
                        </div>
                        <div class="detail-item">
                            <span class="detail-icon">🕒</span>
                            <span>Modified: ${formatDate(file.modified_at)}</span>
                        </div>
                        ${file.version_info ? `
                            <div class="detail-item">
                                <span class="detail-icon">🔀</span>
                                <span>Version: ${file.version_info.latest_commit} (${file.version_info.commit_count} commits)</span>
                            </div>
                        ` : ''}
                        ${file.locked_by ? `
                            <div class="detail-item">
                                <span class="detail-icon">🔒</span>
                                <span>Locked by: ${file.locked_by} at ${formatDate(file.locked_at)}</span>
                            </div>
                        ` : ''}
                    </div>
                `;

                fileListEl.appendChild(fileEl);
            });
        }

        function getStatusText(file) {
            switch (file.status) {
                case 'unlocked':
                    return 'Available';
                case 'locked':
                    return `Locked by ${file.locked_by}`;
                case 'checked_out_by_user':
                    return 'Checked out by you';
                default:
                    return file.status;
            }
        }

        function getActionButtons(file) {
            let buttons = '';

            if (file.status === 'unlocked') {
                buttons += `<button class="btn btn-primary" onclick="checkoutFile('${file.filename}')">
                    📥 Checkout
                </button>`;
            } else if (file.status === 'checked_out_by_user' || (file.status === 'locked' && file.locked_by === currentUser)) {
                buttons += `<button class="btn btn-success" onclick="showCheckinDialog('${file.filename}')">
                    📤 Check In
                </button>`;
            } else if (file.status === 'locked' && file.locked_by !== currentUser) {
                buttons += `<button class="btn btn-warning" onclick="adminOverride('${file.filename}')">
                    🔓 Admin Override
                </button>`;
            }

            buttons += `<button class="btn btn-secondary" onclick="viewFileHistory('${file.filename}')">
                📚 History
            </button>`;

            return buttons;
        }

        // File operations
        async function checkoutFile(filename) {
            try {
                const response = await fetch(`/files/${filename}/checkout`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ user: currentUser })
                });

                const result = await response.json();

                if (response.ok) {
                    showNotification(`File '${filename}' checked out successfully!`, 'success');
                    loadFiles();

                    // Offer to download file
                    if (confirm('Would you like to download the file now?')) {
                        window.location.href = `/files/${filename}/download`;
                    }
                } else {
                    showNotification(`Error: ${result.detail}`, 'error');
                }
            } catch (error) {
                console.error('Error checking out file:', error);
                showNotification('Error checking out file', 'error');
            }
        }

        function showCheckinDialog(filename) {
            const input = document.getElementById('fileUpload');
            input.onchange = function(event) {
                const file = event.target.files[0];
                if (file) {
                    checkinFile(filename, file);
                }
            };
            input.click();
        }

        async function checkinFile(filename, file) {
            try {
                showNotification(`Uploading ${filename}...`, 'info');

                const formData = new FormData();
                formData.append('user', currentUser);
                formData.append('file', file);

                const response = await fetch(`/files/${filename}/checkin`, {
                    method: 'POST',
                    body: formData
                });

                const result = await response.json();

                if (response.ok) {
                    showNotification(`File '${filename}' is being processed`, 'success');
                    loadFiles();
                } else {
                    showNotification(`Error: ${result.detail}`, 'error');
                }
            } catch (error) {
                console.error('Error checking in file:', error);
                showNotification('Error checking in file', 'error');
            }
        }

        async function adminOverride(filename) {
            if (!confirm(`Are you sure you want to override the lock on '${filename}'?`)) {
                return;
            }

            try {
                const response = await fetch(`/files/${filename}/override`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ admin_user: currentUser })
                });

                const result = await response.json();

                if (response.ok) {
                    showNotification(`File '${filename}' unlocked successfully!`, 'success');
                    loadFiles();
                } else {
                    showNotification(`Error: ${result.detail}`, 'error');
                }
            } catch (error) {
                console.error('Error overriding file lock:', error);
                showNotification('Error overriding file lock', 'error');
            }
        }

        async function viewFileHistory(filename) {
            try {
                const response = await fetch(`/files/${filename}/history`);
                const result = await response.json();

                if (response.ok) {
                    showFileHistoryModal(result);
                } else {
                    showNotification('Error loading file history', 'error');
                }
            } catch (error) {
                console.error('Error loading file history:', error);
                showNotification('Error loading file history', 'error');
            }
        }

        function showFileHistoryModal(historyData) {
            // Create modal for file history
            const modal = document.createElement('div');
            modal.style.cssText = `
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0,0,0,0.5);
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: 2000;
            `;

            const content = document.createElement('div');
            content.style.cssText = `
                background: white;
                padding: 30px;
                border-radius: 15px;
                max-width: 800px;
                max-height: 80vh;
                overflow-y: auto;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            `;

            let historyHtml = `<h3>Version History - ${historyData.filename}</h3>`;

            if (historyData.history && historyData.history.length > 0) {
                historyHtml += '<div style="margin-top: 20px;">';
                historyData.history.forEach(commit => {
                    historyHtml += `
                        <div style="padding: 15px; border: 1px solid #eee; border-radius: 8px; margin-bottom: 10px;">
                            <div style="font-weight: bold;">${commit.commit_hash}</div>
                            <div style="color: #666; margin: 5px 0;">
                                By ${commit.author_name} on ${formatDate(commit.date)}
                            </div>
                            <div>${commit.message}</div>
                        </div>
                    `;
                });
                historyHtml += '</div>';
            } else {
                historyHtml += '<p>No version history available.</p>';
            }

            historyHtml += `<button onclick="this.closest('[style*=\"position: fixed\"]').remove()" 
                           class="btn btn-secondary" style="margin-top: 20px;">Close</button>`;

            content.innerHTML = historyHtml;
            modal.appendChild(content);
            document.body.appendChild(modal);

            // Close on background click
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    modal.remove();
                }
            });
        }

        // Configuration panel
        function toggleConfigPanel() {
            const panel = document.getElementById('configPanel');
            panel.classList.toggle('open');
        }

        // Configuration form submission
        document.getElementById('configForm').addEventListener('submit', async function(e) {
            e.preventDefault();

            const formData = {
                gitlab_url: document.getElementById('gitlabUrl').value,
                project_id: document.getElementById('projectId').value,
                username: document.getElementById('username').value,
                token: document.getElementById('token').value
            };

            try {
                showNotification('Saving configuration...', 'info');

                const response = await fetch('/config/gitlab', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(formData)
                });

                const result = await response.json();

                if (response.ok) {
                    showNotification('Configuration saved successfully!', 'success');
                    loadConfig();
                    loadFiles();
                    toggleConfigPanel();
                } else {
                    showNotification(`Error: ${result.detail}`, 'error');
                }
            } catch (error) {
                console.error('Error saving configuration:', error);
                showNotification('Error saving configuration', 'error');
            }
        });

        // Search functionality
        document.getElementById('searchInput').addEventListener('input', function() {
            renderFiles();
        });

        // Notification system
        function showNotification(message, type = 'info') {
            const notification = document.createElement('div');
            notification.className = `notification ${type}`;
            notification.textContent = message;

            document.body.appendChild(notification);

            // Show notification
            setTimeout(() => {
                notification.classList.add('show');
            }, 100);

            // Hide notification after 4 seconds
            setTimeout(() => {
                notification.classList.remove('show');
                setTimeout(() => {
                    if (notification.parentNode) {
                        notification.parentNode.removeChild(notification);
                    }
                }, 300);
            }, 4000);
        }

        // Utility functions
        function formatBytes(bytes) {
            if (!bytes || bytes === 0) return '0 Bytes';
            const k = 1024;
            const sizes = ['Bytes', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        }

        function formatDate(dateString) {
            if (!dateString) return 'Unknown';
            return new Date(dateString).toLocaleString();
        }

        // Initialize application
        document.addEventListener('DOMContentLoaded', function() {
            connectWebSocket();
            loadConfig();
            loadFiles();

            // Update current user display
            document.getElementById('currentUser').textContent = currentUser;

            // Auto-refresh every 60 seconds
            setInterval(loadFiles, 60000);
        });
    </script>
</body>
</html>
    """

def open_browser(port: int = 8000):
    """Open browser to the application URL"""
    url = f"http://localhost:{port}"
    logger.info(f"Opening browser to {url}")
    webbrowser.open(url)

def main():
    """Main application entry point"""
    logger.info("Starting Mastercam GitLab Interface...")

    # Check if running as executable
    if getattr(sys, 'frozen', False):
        logger.info("Running as PyInstaller executable")
    else:
        logger.info("Running as Python script")

    port = 8000

    # Start browser in a separate thread after a short delay
    def delayed_browser_open():
        import time
        time.sleep(3)  # Wait for server to start
        open_browser(port)

    browser_thread = threading.Thread(target=delayed_browser_open, daemon=True)
    browser_thread.start()

    # Start FastAPI server
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