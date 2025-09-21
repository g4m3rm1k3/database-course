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
import aiofiles
import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Form, UploadFile, File, BackgroundTasks, Header, Depends
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.websockets import WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Import our custom modules
from git_operations import GitRepository, GitLFSManager, GitLabAPI, GitOperationError
from config_manager import ConfigManager, AppConfig
from metadata_manager import MetadataManager

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

class UserInfo(BaseModel):
    username: str
    token: str

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

# --- Authentication Dependency ---
async def get_current_user(x_api_key: str = Header(None)):
    """Dependency to validate the user's API key."""
    # In a real app, validate against a secure user database.
    # For this implementation, we use a simple validation against the configured username/token.
    config = app_state['config_manager'].config
    if x_api_key == config.gitlab.token:
        app_state['current_user'] = config.gitlab.username
        return config.gitlab.username
    raise HTTPException(status_code=401, detail="Invalid API Key")

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
    # Link to the main HTML file
    return FileResponse("templates/index.html")

# Mount the static directory
app.mount("/static", StaticFiles(directory="static"), name="static")


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
async def checkout_file(filename: str, user: str = Depends(get_current_user)):
    """Lock file for editing by authenticated user"""
    try:
        if not app_state['metadata_manager']:
            raise HTTPException(status_code=500, detail="Metadata manager not available")
        
        # Find file path
        file_path = find_file_path(filename)
        if not file_path:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Check for existing lock
        lock_info = app_state['metadata_manager'].get_lock_info(file_path)
        if lock_info and lock_info['user'] != user:
            raise HTTPException(
                status_code=409,
                detail=f"File is already locked by {lock_info['user']}"
            )

        # Acquire Git LFS lock
        app_state['git_repo'].lfs_manager.lock_file(file_path)
        
        # Create metadata lock
        success = app_state['metadata_manager'].create_lock(file_path, user)
        if not success:
            # If metadata lock fails, but LFS succeeded, unlock LFS
            app_state['git_repo'].lfs_manager.unlock_file(file_path, force=True)
            raise HTTPException(status_code=409, detail="Failed to acquire metadata lock")
        
        logger.info(f"File '{filename}' checked out by '{user}'")
        
        # Notify all clients
        await manager.broadcast(json.dumps({
            "event": "file_status_changed",
            "filename": filename,
            "status": "locked",
            "locked_by": user
        }))
        
        return JSONResponse({
            "status": "success",
            "message": f"File '{filename}' checked out successfully",
            "download_url": f"/files/{filename}/download"
        })
        
    except GitOperationError as e:
        logger.error(f"Git LFS lock failed for '{filename}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Git LFS lock failed: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking out file '{filename}': {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to checkout file")

@app.post("/files/{filename}/checkin")
async def checkin_file(
    filename: str,
    background_tasks: BackgroundTasks,
    user: str = Depends(get_current_user),
    file: UploadFile = File(...)
):
    """Upload edited file, release lock, and commit changes"""
    try:
        if not app_state['metadata_manager']:
            raise HTTPException(status_code=500, detail="Metadata manager not available")
        
        # Find file path
        file_path = find_file_path(filename)
        if not file_path:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Verify lock ownership
        lock_info = app_state['metadata_manager'].get_lock_info(file_path)
        if not lock_info or lock_info['user'] != user:
            raise HTTPException(
                status_code=409,
                detail="File is not locked by the current user"
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
        
        # Process check-in in background
        background_tasks.add_task(
            process_checkin,
            file_path,
            content,
            user,
            filename,
            app_state['git_repo'],
            app_state['metadata_manager'],
            manager,
            app_state['config_manager'].config.local.auto_backup
        )
        
        return JSONResponse({
            "status": "success",
            "message": f"File '{filename}' is being processed"
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking in file '{filename}': {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to checkin file")

async def process_checkin(file_path: str, content: bytes, user: str, filename: str, git_repo: GitRepository, metadata_manager: MetadataManager, connection_manager: ConnectionManager, auto_backup: bool):
    """Process file check-in in background"""
    try:
        if git_repo and git_repo.repo:
            # Create backup if enabled
            if auto_backup:
                create_backup(file_path, content)
            
            # Save file to repository
            if git_repo.save_file(file_path, content):
                # Commit and push changes
                commit_message = f"Update {filename} by {user}"
                success = git_repo.commit_and_push(
                    file_path,
                    commit_message,
                    user,
                    f"{user}@example.com"
                )
                
                if success:
                    # Release Git LFS lock
                    git_repo.lfs_manager.unlock_file(file_path)
                    
                    logger.info(f"File '{filename}' successfully committed and pushed")
                    
                    # Release metadata lock
                    metadata_manager.release_lock(file_path, user)
                    
                    # Notify clients of successful commit
                    await connection_manager.broadcast(json.dumps({
                        "event": "file_committed",
                        "filename": filename,
                        "user": user
                    }))
                else:
                    logger.error(f"Failed to commit file '{filename}'")
                    await connection_manager.broadcast(json.dumps({
                        "event": "file_commit_failed",
                        "filename": filename,
                        "user": user
                    }))
            else:
                logger.error(f"Failed to save file '{filename}'")
        else:
            logger.warning(f"Repository not available, file '{filename}' not committed")
            
    except GitOperationError as e:
        logger.error(f"Git operation failed during check-in: {str(e)}")
        metadata_manager.release_lock(file_path, user)  # Release metadata lock
        await connection_manager.broadcast(json.dumps({
            "event": "file_commit_failed",
            "filename": filename,
            "user": user,
            "error": "Git operation failed"
        }))
    except Exception as e:
        logger.error(f"Error processing check-in for '{filename}': {str(e)}")
        metadata_manager.release_lock(file_path, user)
        await connection_manager.broadcast(json.dumps({
            "event": "file_commit_failed",
            "filename": filename,
            "user": user,
            "error": "Internal server error"
        }))

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
async def admin_override(filename: str, admin_user: str = Depends(get_current_user)):
    """Admin override to forcibly unlock file"""
    try:
        if not app_state['metadata_manager']:
            raise HTTPException(status_code=500, detail="Metadata manager not available")
        
        # Find file path
        file_path = find_file_path(filename)
        if not file_path:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Release LFS lock (forcefully)
        app_state['git_repo'].lfs_manager.unlock_file(file_path, force=True)
        
        # Release metadata lock
        lock_info = app_state['metadata_manager'].get_lock_info(file_path)
        previous_user = lock_info['user'] if lock_info else 'none'
        
        app_state['metadata_manager'].release_lock(file_path)
        
        logger.info(f"Admin '{admin_user}' overrode lock on '{filename}' (was locked by '{previous_user}')")
        
        # Notify all clients
        await manager.broadcast(json.dumps({
            "event": "file_status_changed",
            "filename": filename,
            "status": "unlocked"
        }))
        
        return JSONResponse({
            "status": "success",
            "message": f"File '{filename}' unlocked by admin"
        })
        
    except GitOperationError as e:
        logger.error(f"Git LFS unlock failed for '{filename}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Git LFS unlock failed: {str(e)}")
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
            if data == "PING":
                await websocket.send_text("PONG")
            elif data.startswith("SET_USER:"):
                # This should be handled by a secure auth system, but we'll use it for demo.
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