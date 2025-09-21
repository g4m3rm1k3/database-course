# app/api.py

import os
import sys
import logging
import tempfile
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, Form, UploadFile, File, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.websockets import WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from services.git_operations import GitRepository, MetadataManager, GitLabAPI, GitOperationError
from services.config_manager import ConfigManager
from app.models import FileInfo, CheckoutRequest, AdminOverrideRequest, ConfigUpdateRequest
from app.websocket_manager import ConnectionManager

logger = logging.getLogger(__name__)

# Global application state
app_state = {
    'config_manager': None,
    'git_repo': None,
    'metadata_manager': None,
    'gitlab_api': None,
    'initialized': False,
    'current_user': 'demo_user'
}

manager = ConnectionManager()
router = APIRouter()

# --- Application Lifecycle Functions ---
async def initialize_application():
    try:
        app_state['config_manager'] = ConfigManager()
        config = app_state['config_manager'].config
        
        metadata_path = Path(config.local.get('temp_path')) / 'metadata'
        app_state['metadata_manager'] = MetadataManager(metadata_path)
        
        user_provided_repo_url = config.gitlab.get('base_url')

        if user_provided_repo_url and config.gitlab.get('token'):
            try:
                api_base_url_parts = user_provided_repo_url.split('/')[:3]
                api_base_url = '/'.join(api_base_url_parts)
                if not api_base_url:
                    api_base_url = "https://gitlab.com"
            except Exception as e:
                logger.warning(f"Could not parse API base URL from '{user_provided_repo_url}': {e}. Defaulting to https://gitlab.com")
                api_base_url = "https://gitlab.com"

            app_state['gitlab_api'] = GitLabAPI(
                base_url=api_base_url,
                token=config.gitlab.get('token'),
                project_id=config.gitlab.get('project_id')
            )
            
            if app_state['gitlab_api'].test_connection():
                logger.info("GitLab connection established")
                
                app_state['git_repo'] = GitRepository(
                    repo_path=Path(config.local.get('repo_path')),
                    remote_url=user_provided_repo_url,
                    username=config.gitlab.get('username'),
                    token=config.gitlab.get('token')
                )
                
                if app_state['git_repo'].clone_or_pull():
                    logger.info("Repository synchronized")
                    app_state['initialized'] = True
                else:
                    logger.warning("Failed to synchronize repository")
            else:
                logger.warning("GitLab connection failed")
        else:
            logger.info("GitLab not configured, running in demo mode")
        
        if app_state.get('metadata_manager'):
            cleaned = app_state['metadata_manager'].cleanup_stale_locks()
            if cleaned > 0:
                logger.info(f"Cleaned up {cleaned} stale file locks")
        
        logger.info("Application initialization completed")
        
    except Exception as e:
        logger.error(f"Failed to initialize application: {str(e)}")

async def cleanup_application():
    try:
        for connection in manager.active_connections:
            await connection.close()
        
        if app_state.get('config_manager'):
            app_state['config_manager'].save_config()
        
        logger.info("Application cleanup completed")
        
    except Exception as e:
        logger.error(f"Error during cleanup: {str(e)}")

# --- Helper Functions ---
def get_demo_files() -> List[FileInfo]:
    # Placeholder for demo data
    return [
        FileInfo(
            filename="part_001.mcam", path="parts/part_001.mcam", status="unlocked", size=2048576,
            modified_at="2024-01-15T10:30:00Z", version_info={"latest_commit": "abc12345", "latest_author": "demo_user", "commit_count": 3, "revision": "v1.2"}
        ),
        FileInfo(
            filename="assembly_main.mcam", path="assemblies/assembly_main.mcam", status="unlocked", size=5242880,
            modified_at="2024-01-15T09:15:00Z", version_info={"latest_commit": "def67890", "latest_author": "demo_user", "commit_count": 7, "revision": "v2.0"}
        )
    ]

def find_file_path(filename: str) -> Optional[str]:
    try:
        if app_state.get('git_repo') and app_state['initialized']:
            files = app_state['git_repo'].list_files("*.mcam")
            for file_data in files:
                if file_data['name'] == filename:
                    return file_data['path']
        return filename
    except Exception as e:
        logger.error(f"Error finding file path for '{filename}': {str(e)}")
        return filename

def get_revision_from_commit_message(message: str) -> str:
    import re
    match = re.search(r"v(\d+\.\d+)", message)
    if match:
        return match.group(0)
    return ""

async def process_checkin(filename: str, content: bytes, user: str, revision_type: str):
    try:
        if app_state.get('git_repo') and app_state['initialized']:
            if app_state['config_manager'].config.local.get('auto_backup', False):
                create_backup(filename, content)
            
            if app_state['git_repo'].save_file(filename, content):
                # FIX: Implement revision increment logic
                current_revision = get_revision_from_commit_message(app_state['git_repo'].get_file_history(filename, limit=1)[0]['message'])
                if current_revision:
                    rev_parts = current_revision[1:].split('.')
                    if revision_type == 'major':
                        new_major = int(rev_parts[0]) + 1
                        new_revision = f"v{new_major}.0"
                    else: # minor
                        new_minor = int(rev_parts[1]) + 1
                        new_revision = f"v{rev_parts[0]}.{new_minor}"
                else:
                    new_revision = "v1.0"
                
                commit_message = f"Update {filename} to {new_revision} by {user}"
                author_email = f"{user}@example.com"
                
                success = app_state['git_repo'].commit_and_push(filename, commit_message, user, author_email)
                
                if success:
                    logger.info(f"File '{filename}' successfully committed and pushed with revision {new_revision}")
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

async def process_new_upload(filename: str, content: bytes, user: str, initial_revision: str):
    try:
        if app_state.get('git_repo') and app_state['initialized']:
            if app_state['git_repo'].save_file(filename, content):
                commit_message = f"Add new file {filename} with initial revision v{initial_revision} by {user}"
                author_email = f"{user}@example.com"
                
                success = app_state['git_repo'].commit_and_push(filename, commit_message, user, author_email)
                
                if success:
                    logger.info(f"New file '{filename}' successfully committed and pushed with revision v{initial_revision}")
                    await manager.broadcast(f"FILE_ADDED:{filename}:{user}")
                else:
                    logger.error(f"Failed to commit new file '{filename}'")
                    await manager.broadcast(f"FILE_ADD_FAILED:{filename}:{user}")
            else:
                logger.error(f"Failed to save new file '{filename}'")
        else:
            logger.warning(f"Repository not available, new file '{filename}' not committed")
    except Exception as e:
        logger.error(f"Error processing new file upload for '{filename}': {str(e)}")

def create_backup(file_path: str, content: bytes):
    try:
        backup_dir = Path(app_state['config_manager'].config.local.get('backup_path'))
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"{Path(file_path).stem}_{timestamp}{Path(file_path).suffix}"
        backup_path = backup_dir / backup_filename
        
        backup_path.write_bytes(content)
        logger.info(f"Backup created: {backup_path}")
        
    except Exception as e:
        logger.error(f"Failed to create backup: {str(e)}")

# --- API Endpoints ---
@router.post("/files/new_upload")
async def new_upload(
    background_tasks: BackgroundTasks,
    user: str = Form(...),
    file: UploadFile = File(...),
    initial_revision: str = Form("1.0")
):
    try:
        if not app_state.get('git_repo') or not app_state['initialized']:
            raise HTTPException(status_code=500, detail="Repository not available or not initialized")
        
        filename = file.filename
        content = await file.read()
        
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        
        max_size = app_state['config_manager'].config.local.get('max_file_size_mb', 100) * 1024 * 1024
        if len(content) > max_size:
            raise HTTPException(status_code=400, detail=f"File size exceeds maximum allowed size ({max_size // 1024 // 1024} MB)")
            
        background_tasks.add_task(process_new_upload, filename, content, user, initial_revision)
        
        logger.info(f"New file '{filename}' upload initiated by '{user}'")
        return JSONResponse({"status": "success", "message": f"New file '{filename}' is being added"})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading new file '{filename}': {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to upload new file")

@router.get("/files", response_model=List[FileInfo])
async def get_files():
    try:
        files = []
        if app_state.get('git_repo') and app_state['initialized']:
            repo_files = app_state['git_repo'].list_files("*.mcam")
            for file_data in repo_files:
                file_info = FileInfo(
                    filename=file_data['name'],
                    path=file_data['path'],
                    status="unlocked",
                    size=file_data['size'],
                    modified_at=file_data['modified_at']
                )
                lock_info = app_state['metadata_manager'].get_lock_info(file_data['path'])
                if lock_info:
                    file_info.status = "locked"
                    file_info.locked_by = lock_info['user']
                    file_info.locked_at = lock_info['timestamp']
                    if lock_info['user'] == app_state['current_user']:
                        file_info.status = "checked_out_by_user"
                
                if app_state['git_repo']:
                    history = app_state['git_repo'].get_file_history(file_data['path'], limit=1)
                    if history:
                        latest_commit = history[0]
                        revision = get_revision_from_commit_message(latest_commit['message'])
                        file_info.version_info = {
                            'latest_commit': latest_commit['commit_hash'][:8],
                            'latest_author': latest_commit['author_name'],
                            'commit_count': len(history),
                            'revision': revision
                        }
                files.append(file_info)
        else:
            files = get_demo_files()
        logger.info(f"Retrieved {len(files)} files")
        return files
    except Exception as e:
        logger.error(f"Error fetching files: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch files")

@router.post("/files/{filename}/checkout")
async def checkout_file(filename: str, request: CheckoutRequest):
    try:
        if not app_state['metadata_manager']:
            raise HTTPException(status_code=500, detail="Metadata manager not available")
        file_path = find_file_path(filename)
        if not file_path:
            raise HTTPException(status_code=404, detail="File not found")

        lock_info = app_state['metadata_manager'].get_lock_info(file_path)
        
        # FIX: Allow checkout if the file is locked by the current user
        if lock_info and lock_info['user'] == request.user:
            logger.info(f"File '{filename}' re-checked out by '{request.user}' to get a fresh copy.")
        elif lock_info:
            raise HTTPException(status_code=409, detail=f"File is already locked by {lock_info['user']}")

        success = app_state['metadata_manager'].create_lock(file_path, request.user)
        if not success:
            logger.warning(f"Could not create lock for '{filename}' but proceeding as it's already locked by the user.")

        await manager.broadcast(f"FILE_STATUS_CHANGED:{filename}:locked:{request.user}")
        return JSONResponse({"status": "success", "message": f"File '{filename}' checked out successfully", "download_url": f"/files/{filename}/download"})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking out file '{filename}': {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to checkout file")

# Check-in endpoint that accepts a revision type
@router.post("/files/{filename}/checkin")
async def checkin_file(filename: str, background_tasks: BackgroundTasks, user: str = Form(...), file: UploadFile = File(...), revision_type: str = Form(...)):
    try:
        if not app_state['metadata_manager']:
            raise HTTPException(status_code=500, detail="Metadata manager not available")
        file_path = find_file_path(filename)
        if not file_path:
            raise HTTPException(status_code=404, detail="File not found")
        lock_info = app_state['metadata_manager'].get_lock_info(file_path)
        if not lock_info:
            raise HTTPException(status_code=409, detail="File is not locked")
        if lock_info['user'] != user:
            raise HTTPException(status_code=409, detail="File is locked by a different user")
        
        content = await file.read()
        
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        max_size = app_state['config_manager'].config.local.get('max_file_size_mb', 100) * 1024 * 1024
        if len(content) > max_size:
            raise HTTPException(status_code=400, detail=f"File size exceeds maximum allowed size ({max_size // 1024 // 1024} MB)")

        # Get current revision from history to increment it
        history = app_state['git_repo'].get_file_history(filename, limit=1)
        current_revision_str = get_revision_from_commit_message(history[0]['message']) if history else "v0.0"
        
        if current_revision_str:
            rev_parts = current_revision_str[1:].split('.')
            try:
                major = int(rev_parts[0])
                minor = int(rev_parts[1])
            except (ValueError, IndexError):
                major, minor = 0, 0 # Fallback if revision is malformed

            if revision_type == 'major':
                new_revision = f"v{major + 1}.0"
            else: # minor
                new_revision = f"v{major}.{minor + 1}"
        else:
            new_revision = "v1.0"

        background_tasks.add_task(process_checkin, filename, content, user, new_revision)

        app_state['metadata_manager'].release_lock(file_path, user)
        logger.info(f"File '{filename}' check-in initiated by '{user}'")
        await manager.broadcast(f"FILE_STATUS_CHANGED:{filename}:unlocked:")
        return JSONResponse({"status": "success", "message": f"File '{filename}' is being processed"})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking in file '{filename}': {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to checkin file")

@router.post("/files/{filename}/override")
async def admin_override(filename: str, request: AdminOverrideRequest):
    try:
        if not app_state['metadata_manager']:
            raise HTTPException(status_code=500, detail="Metadata manager not available")
        file_path = find_file_path(filename)
        if not file_path:
            raise HTTPException(status_code=404, detail="File not found")
        lock_info = app_state['metadata_manager'].get_lock_info(file_path)
        previous_user = lock_info['user'] if lock_info else 'none'
        app_state['metadata_manager'].release_lock(file_path)
        logger.info(f"Admin '{request.admin_user}' overrode lock on '{filename}' (was locked by '{previous_user}')")
        await manager.broadcast(f"FILE_STATUS_CHANGED:{filename}:unlocked:")
        return JSONResponse({"status": "success", "message": f"File '{filename}' unlocked by admin"})
    except Exception as e:
        logger.error(f"Error in admin override for file '{filename}': {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to override file lock")

@router.get("/files/{filename}/download")
async def download_file(filename: str):
    try:
        file_path = find_file_path(filename)
        if not file_path:
            raise HTTPException(status_code=404, detail="File not found")
        if app_state['git_repo'] and app_state['initialized']:
            content = app_state['git_repo'].get_file_content(file_path)
            if content is None:
                raise HTTPException(status_code=404, detail="File not found in repository")
            temp_dir = Path(tempfile.gettempdir()) / 'mastercam_downloads'
            temp_dir.mkdir(exist_ok=True)
            temp_file = temp_dir / filename
            temp_file.write_bytes(content)
            logger.info(f"File '{filename}' prepared for download")
            return FileResponse(path=str(temp_file), filename=filename, media_type='application/octet-stream')
        else:
            raise HTTPException(status_code=501, detail="Repository not available")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading file '{filename}': {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to download file")

@router.get("/files/{filename}/history")
async def get_file_history(filename: str):
    try:
        file_path = find_file_path(filename)
        if not file_path:
            raise HTTPException(status_code=404, detail="File not found")
        if app_state['git_repo'] and app_state['initialized']:
            commits = app_state['git_repo'].get_file_history(file_path, limit=20)
            # TODO: Integrate with metadata manager to show checkout/check-in events
            history = {"filename": filename, "history": commits}
            return history
        else:
            return {"filename": filename, "history": []}
    except Exception as e:
        logger.error(f"Error getting file history for '{filename}': {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get file history")

@router.get("/config")
async def get_config():
    try:
        if app_state['config_manager']:
            return app_state['config_manager'].get_config_summary()
        return {"error": "Configuration not available"}
    except Exception as e:
        logger.error(f"Error getting configuration: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get configuration")

@router.post("/config/gitlab")
async def update_gitlab_config(request: ConfigUpdateRequest):
    try:
        config_manager = app_state['config_manager']
        if not config_manager:
            raise HTTPException(status_code=500, detail="Configuration manager not available")
        success = config_manager.update_gitlab_config(request.gitlab_url, request.project_id, request.username, request.token)
        if success:
            return {"status": "success", "message": "GitLab configuration updated"}
        else:
            raise HTTPException(status_code=500, detail="Failed to update configuration")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating GitLab configuration: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, user: str = "anonymous"):
    await manager.connect(websocket, user)
    try:
        while True:
            data = await websocket.receive_text()
            if data.startswith("PING"):
                continue
            elif data.startswith("SET_USER:"):
                new_user = data.split(":", 1)[1]
                app_state['current_user'] = new_user
                logger.info(f"WebSocket message from {user}: SET_USER to {new_user}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error for user '{user}': {e}")
        manager.disconnect(websocket)