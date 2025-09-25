#!/usr/bin/env python3
"""
Mastercam GitLab Interface - Final Integrated Application with Git Polling
This script handles all application logic, from server startup to Git operations,
with a focus on stability, modern practices, and user experience.
"""

import os
import sys
import asyncio
import webbrowser
import threading
import logging
import tempfile
import json
import git
import re
import hashlib
import uuid
from git import Actor
import requests
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Form, UploadFile, File, Response, status, Path as FastAPIPath
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.websockets import WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from cryptography.fernet import Fernet
import base64

# --- Basic Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler('mastercam_git_interface.log'), logging.StreamHandler()])
logger = logging.getLogger(__name__)

# --- Pydantic Data Models ---


class FileInfo(BaseModel):
    """Information about a file in the repository."""
    filename: str = Field(..., description="Name of the file")
    path: str = Field(...,
                      description="Relative path to the file in the repository")
    status: str = Field(
        ..., description="Current status of the file (locked, unlocked, checked_out_by_user)")
    locked_by: Optional[str] = Field(
        None, description="Username who has the file locked")
    locked_at: Optional[str] = Field(
        None, description="ISO timestamp when the file was locked")
    size: Optional[int] = Field(None, description="File size in bytes")
    modified_at: Optional[str] = Field(
        None, description="ISO timestamp when the file was last modified")
    description: Optional[str] = Field(
        None, description="File description from metadata")
    revision: Optional[str] = Field(
        None, description="Current revision number")


class CheckoutRequest(BaseModel):
    """Request model for file checkout operations."""
    user: str = Field(..., description="Username requesting the checkout",
                      example="john_doe")


class AdminOverrideRequest(BaseModel):
    """Request model for administrative override operations."""
    admin_user: str = Field(...,
                            description="Administrator username", example="admin")


class AdminDeleteRequest(BaseModel):
    """Request model for administrative file deletion."""
    admin_user: str = Field(
        ..., description="Administrator username performing the deletion", example="admin")


class SendMessageRequest(BaseModel):
    """Request model for sending messages between users."""
    recipient: str = Field(...,
                           description="Username of the message recipient", example="jane_doe")
    message: str = Field(..., description="Message content",
                         example="Please review the latest revision")
    sender: str = Field(...,
                        description="Username of the message sender", example="admin")


class AckMessageRequest(BaseModel):
    """Request model for acknowledging received messages."""
    message_id: str = Field(...,
                            description="Unique identifier of the message to acknowledge")
    user: str = Field(..., description="Username acknowledging the message",
                      example="jane_doe")


class ConfigUpdateRequest(BaseModel):
    """Request model for updating GitLab configuration."""
    base_url: str = Field(
        alias="gitlab_url", description="GitLab instance URL", example="https://gitlab.example.com")
    project_id: str = Field(...,
                            description="GitLab project ID", example="123")
    username: str = Field(..., description="GitLab username",
                          example="git_user")
    token: str = Field(..., description="GitLab personal access token")


class AppConfig(BaseModel):
    """Application configuration model."""
    version: str = Field(default="1.0.0", description="Application version")
    gitlab: dict = Field(default_factory=dict,
                         description="GitLab configuration settings")
    local: dict = Field(default_factory=dict,
                        description="Local repository settings")
    ui: dict = Field(default_factory=dict,
                     description="User interface settings")
    security: dict = Field(default_factory=lambda: {"admin_users": [
                           "admin"]}, description="Security settings")
    polling: dict = Field(default_factory=lambda: {
                          "enabled": True, "interval_seconds": 15, "check_on_activity": True}, description="Git polling configuration")

# --- Core Application Classes & Functions ---


def _increment_revision(current_rev: str, rev_type: str, new_major_str: Optional[str] = None) -> str:
    major, minor = 0, 0
    if not current_rev:
        current_rev = "0.0"
    parts = current_rev.split('.')
    try:
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        major, minor = 0, 0

    if rev_type == 'major':
        if new_major_str and new_major_str.isdigit():
            return f"{int(new_major_str)}.0"
        return f"{major + 1}.0"
    else:
        return f"{major}.{minor + 1}"


class EncryptionManager:
    def __init__(self, config_dir: Path):
        self.key_file = config_dir / '.encryption_key'
        self._fernet = None
        self._initialize_encryption()

    def _initialize_encryption(self):
        try:
            if self.key_file.exists():
                key = self.key_file.read_bytes()
            else:
                key = Fernet.generate_key()
                self.key_file.write_bytes(key)
                if os.name != 'nt':
                    os.chmod(self.key_file, 0o600)
            self._fernet = Fernet(key)
        except Exception as e:
            logger.error(f"Failed to initialize encryption: {e}")

    def encrypt(self, data: str) -> str:
        if self._fernet:
            return base64.b64encode(self._fernet.encrypt(data.encode())).decode()
        return data

    def decrypt(self, encrypted_data: str) -> str:
        if self._fernet:
            return self._fernet.decrypt(base64.b64decode(encrypted_data.encode())).decode()
        return encrypted_data


class ConfigManager:
    def __init__(self, config_dir: Optional[Path] = None):
        if config_dir is None:
            config_dir = Path.home() / 'AppData' / 'Local' / \
                'MastercamGitInterface' if os.name == 'nt' else Path.home() / '.config' / \
                'mastercam_git_interface'
        self.config_dir, self.config_file = config_dir, config_dir / 'config.json'
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.encryption = EncryptionManager(self.config_dir)
        self.config = self._load_config()

    def _load_config(self) -> AppConfig:
        try:
            if self.config_file.exists() and self.config_file.read_text():
                data = json.loads(self.config_file.read_text())
                if 'gitlab' in data and data.get('gitlab', {}).get('token'):
                    data['gitlab']['token'] = self.encryption.decrypt(
                        data['gitlab']['token'])
                return AppConfig(**data)
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
        return AppConfig()

    def save_config(self):
        try:
            data = self.config.model_dump()
            if data.get('gitlab', {}).get('token'):
                data['gitlab']['token'] = self.encryption.encrypt(
                    data['gitlab']['token'])
            self.config_file.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

    def update_gitlab_config(self, **kwargs):
        gitlab_config = self.config.model_dump().get('gitlab', {})
        gitlab_config.update(kwargs)
        self.config.gitlab = gitlab_config
        self.save_config()

    def get_config_summary(self) -> Dict[str, Any]:
        cfg = self.config.model_dump()
        gitlab_cfg = cfg.get('gitlab', {})
        local_cfg = cfg.get('local', {})
        security_cfg = cfg.get('security', {})
        return {
            'gitlab_url': gitlab_cfg.get('base_url'), 'project_id': gitlab_cfg.get('project_id'), 'username': gitlab_cfg.get('username'), 'has_token': bool(gitlab_cfg.get('token')), 'repo_path': local_cfg.get('repo_path'),
            'is_admin': gitlab_cfg.get('username') in security_cfg.get('admin_users', [])
        }


class GitLabAPI:
    def __init__(self, base_url: str, token: str, project_id: str):
        self.api_url = f"{base_url}/api/v4/projects/{project_id}"
        self.headers = {"Private-Token": token}

    def test_connection(self) -> bool:
        try:
            response = requests.get(
                self.api_url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"GitLab connection test failed: {e}")
            return False


class GitRepository:
    def __init__(self, repo_path: Path, remote_url: str, token: str):
        self.repo_path = repo_path
        self.remote_url_with_token = f"https://oauth2:{token}@{remote_url.split('://')[-1]}"
        self.git_env = {"GIT_SSL_NO_VERIFY": "true"}
        self.repo = self._init_repo()

    def _init_repo(self):
        try:
            if not self.repo_path.exists():
                logger.info(f"Cloning repository to {self.repo_path}")
                return git.Repo.clone_from(self.remote_url_with_token, self.repo_path, env=self.git_env)
            repo = git.Repo(self.repo_path)
            if not repo.remotes:
                raise git.exc.InvalidGitRepositoryError
            return repo
        except (git.exc.InvalidGitRepositoryError, git.exc.NoSuchPathError):
            logger.warning(f"Invalid repo at {self.repo_path}, re-cloning.")
            if self.repo_path.exists():
                import shutil
                shutil.rmtree(self.repo_path)
            return git.Repo.clone_from(self.remote_url_with_token, self.repo_path, env=self.git_env)
        except Exception as e:
            logger.error(f"Failed to initialize repository: {e}")
            return None

    def pull(self):
        try:
            if self.repo:
                with self.repo.git.custom_environment(**self.git_env):
                    self.repo.remotes.origin.fetch()
                    self.repo.git.reset(
                        '--hard', f'origin/{self.repo.active_branch.name}')
                    logger.debug(
                        "Successfully synced with remote via fetch and hard reset.")
        except Exception as e:
            logger.error(f"Git sync (fetch/reset) failed: {e}")

    def list_files(self, pattern: str = "*.mcam") -> List[Dict]:
        if not self.repo:
            return []
        files = []
        for item in self.repo.tree().traverse():
            if item.type == 'blob' and Path(item.path).match(pattern):
                try:
                    stat_result = os.stat(item.abspath)
                    files.append({"name": item.name, "path": item.path, "size": stat_result.st_size,
                                 "modified_at": datetime.utcfromtimestamp(stat_result.st_mtime).isoformat() + "Z"})
                except OSError:
                    continue
        return files

    def save_file(self, file_path: str, content: bytes):
        (self.repo_path / file_path).parent.mkdir(parents=True, exist_ok=True)
        (self.repo_path / file_path).write_bytes(content)

    def commit_and_push(self, file_paths: List[str], message: str, author_name: str, author_email: str) -> bool:
        if not self.repo:
            return False
        try:
            with self.repo.git.custom_environment(**self.git_env):
                to_add = [p for p in file_paths if (
                    self.repo_path / p).exists()]
                to_remove = [p for p in file_paths if not (
                    self.repo_path / p).exists()]
                if to_add:
                    self.repo.index.add(to_add)
                if to_remove:
                    self.repo.index.remove(to_remove)
                if not self.repo.index.diff("HEAD") and not any(self.repo.index.diff(None)) and not self.repo.untracked_files:
                    logger.info("No changes to commit.")
                    return True
                author = Actor(author_name, author_email)
                self.repo.index.commit(message, author=author)
                self.repo.remotes.origin.push()
            logger.info("Changes pushed to GitLab.")
            return True
        except Exception as e:
            logger.error(f"Git commit/push failed: {e}")
            try:
                with self.repo.git.custom_environment(**self.git_env):
                    self.repo.git.reset(
                        '--hard', f'origin/{self.repo.active_branch.name}')
            except Exception as reset_e:
                logger.error(
                    f"Failed to reset repo after push failure: {reset_e}")
            return False

    def get_file_history(self, file_path: str, limit: int = 10) -> List[Dict]:
        if not self.repo:
            return []
        history = []
        meta_path_str = f"{file_path}.meta.json"
        try:
            commits = self.repo.iter_commits(
                paths=[file_path, meta_path_str], max_count=limit)
            for c in commits:
                revision = None
                try:
                    meta_blob = c.tree / meta_path_str
                    meta_content = json.loads(
                        meta_blob.data_stream.read().decode('utf-8'))
                    revision = meta_content.get("revision")
                except Exception:
                    pass
                try:
                    author_name = c.author.name if c.author else "Unknown"
                    author_email = c.author.email if c.author else ""
                    history.append({
                        "commit_hash": c.hexsha, "author_name": author_name, "author_email": author_email,
                        "date": datetime.utcfromtimestamp(c.committed_date).isoformat() + "Z", "message": c.message.strip(),
                        "revision": revision
                    })
                except Exception as e:
                    logger.warning(
                        f"Could not parse commit details for {c.hexsha}: {e}")
            return history
        except git.exc.GitCommandError as e:
            logger.error(
                f"Git command failed while getting history for {file_path}: {e}")
            return []

    def get_all_users_from_history(self) -> List[str]:
        if not self.repo:
            return []
        try:
            authors = {c.author.name for c in self.repo.iter_commits()
                       if c.author}
            return sorted(list(authors))
        except Exception as e:
            logger.error(
                f"Could not retrieve user list from repo history: {e}")
            return []

    def get_file_content(self, file_path: str) -> Optional[bytes]:
        full_path = self.repo_path / file_path
        if full_path.exists():
            return full_path.read_bytes()
        return None

    def get_file_content_at_commit(self, file_path: str, commit_hash: str) -> Optional[bytes]:
        if not self.repo:
            return None
        try:
            commit = self.repo.commit(commit_hash)
            blob = commit.tree / file_path
            return blob.data_stream.read()
        except Exception as e:
            logger.error(
                f"Could not get file content at commit {commit_hash}: {e}")
            return None


class MetadataManager:
    def __init__(self, repo_path: Path):
        self.locks_dir = repo_path / '.locks'
        self.locks_dir.mkdir(parents=True, exist_ok=True)

    def _get_lock_file_path(self, file_path_str: str) -> Path:
        sanitized = file_path_str.replace(os.path.sep, '_').replace('.', '_')
        return self.locks_dir / f"{sanitized}.lock"

    def create_lock(self, file_path: str, user: str, force: bool = False) -> Optional[Path]:
        lock_file = self._get_lock_file_path(file_path)
        if lock_file.exists() and not force:
            return None
        lock_data = {"file": file_path, "user": user,
                     "timestamp": datetime.utcnow().isoformat() + "Z"}
        lock_file.write_text(json.dumps(lock_data, indent=2))
        return lock_file

    def refresh_lock(self, file_path: str, user: str) -> Optional[Path]:
        lock_file = self._get_lock_file_path(file_path)
        if not lock_file.exists():
            return None
        try:
            data = json.loads(lock_file.read_text())
            if data.get('user') != user:
                return None
            data['timestamp'] = datetime.utcnow().isoformat() + "Z"
            lock_file.write_text(json.dumps(data, indent=2))
            return lock_file
        except Exception as e:
            logger.error(f"Failed to refresh lock for {file_path}: {e}")
            return None

    def release_lock(self, file_path: str):
        self._get_lock_file_path(file_path).unlink(missing_ok=True)

    def get_lock_info(self, file_path: str) -> Optional[Dict]:
        lock_file = self._get_lock_file_path(file_path)
        if lock_file.exists():
            try:
                return json.loads(lock_file.read_text())
            except Exception:
                return None
        return None


class GitStateMonitor:
    def __init__(self, git_repo):
        self.git_repo = git_repo
        self.last_commit_hash = None
        self.last_locks_hash = None
        self.initialize_state()

    def initialize_state(self):
        if self.git_repo and self.git_repo.repo:
            try:
                self.last_commit_hash = self.git_repo.repo.head.commit.hexsha
                self.last_locks_hash = self._calculate_locks_hash()
            except Exception as e:
                logger.error(f"Failed to initialize git state: {e}")

    def _calculate_locks_hash(self) -> str:
        if not self.git_repo or not self.git_repo.repo:
            return ""
        locks_dir = self.git_repo.repo_path / '.locks'
        if not locks_dir.exists():
            return ""
        lock_files_data = []
        try:
            for lock_file in locks_dir.glob('*.lock'):
                if lock_file.is_file():
                    lock_files_data.append(
                        f"{lock_file.name}:{lock_file.read_text()}")
        except Exception as e:
            logger.error(f"Error reading lock files: {e}")
            return ""
        lock_files_data.sort()
        combined_data = "".join(lock_files_data)
        return hashlib.md5(combined_data.encode()).hexdigest()

    def check_for_changes(self) -> bool:
        if not self.git_repo or not self.git_repo.repo:
            return False
        try:
            self.git_repo.pull()
            current_commit = self.git_repo.repo.head.commit.hexsha
            current_locks_hash = self._calculate_locks_hash()
            commit_changed = current_commit != self.last_commit_hash
            locks_changed = current_locks_hash != self.last_locks_hash
            if commit_changed or locks_changed:
                logger.info(
                    f"Git state changed - Commit: {commit_changed}, Locks: {locks_changed}")
                self.last_commit_hash = current_commit
                self.last_locks_hash = current_locks_hash
                return True
            return False
        except Exception as e:
            logger.error(f"Error checking git changes: {e}")
            return False


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections[:]:
            try:
                await connection.send_text(message)
            except Exception:
                self.disconnect(connection)


# --- Global State and App Setup ---
manager = ConnectionManager()
app_state = {}
git_monitor = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting up...")
    await initialize_application()
    yield
    if cfg_manager := app_state.get('config_manager'):
        cfg_manager.save_config()
    logger.info("Application shutting down.")


app = FastAPI(
    title="Mastercam GitLab Interface",
    description="A comprehensive file management system for Mastercam files with GitLab integration, featuring check-in/check-out functionality, version control, and real-time collaboration.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(CORSMiddleware, allow_origins=[
                   "*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


def resource_path(relative_path):
    base_path = getattr(sys, '_MEIPASS', os.path.abspath("."))
    return os.path.join(base_path, relative_path)


app.mount("/static", StaticFiles(directory=resource_path("static")), name="static")
templates = Jinja2Templates(directory=resource_path("templates"))

# --- Initialization and Helper Functions ---


async def initialize_application():
    global git_monitor
    try:
        app_state['config_manager'] = ConfigManager()
        cfg = app_state['config_manager'].config.model_dump()
        gitlab_cfg = cfg.get('gitlab', {})
        if all(gitlab_cfg.get(k) for k in ['base_url', 'token', 'project_id']):
            base_url = '/'.join(gitlab_cfg['base_url'].split('/')[:3])
            app_state['gitlab_api'] = GitLabAPI(
                base_url, gitlab_cfg['token'], gitlab_cfg['project_id'])
            if app_state['gitlab_api'].test_connection():
                logger.info("GitLab connection established.")
                repo_path = Path(cfg.get('local', {}).get(
                    'repo_path', Path.home() / 'MastercamGitRepo'))
                app_state['git_repo'] = GitRepository(
                    repo_path, gitlab_cfg['base_url'], gitlab_cfg['token'])
                if app_state['git_repo'].repo:
                    app_state['metadata_manager'] = MetadataManager(repo_path)
                    git_monitor = GitStateMonitor(app_state['git_repo'])
                    app_state['initialized'] = True
                    logger.info("Repository synchronized.")
                    asyncio.create_task(git_polling_task())
    except Exception as e:
        logger.error(f"Initialization failed: {e}")
    if not app_state.get('initialized'):
        logger.warning(
            "Running in limited/demo mode. Check config if this is unexpected.")
        app_state['metadata_manager'] = MetadataManager(
            Path(tempfile.gettempdir()) / 'mastercam_git_interface')


async def git_polling_task():
    global git_monitor
    if not git_monitor:
        logger.error("Git monitor not initialized")
        return
    logger.info("Starting Git polling task...")
    poll_interval = 15
    while True:
        try:
            if not app_state.get('initialized'):
                await asyncio.sleep(poll_interval)
                continue
            if git_monitor.check_for_changes():
                logger.info("Git changes detected, broadcasting update...")
                await broadcast_file_list_update()
            await asyncio.sleep(poll_interval)
        except asyncio.CancelledError:
            logger.info("Git polling task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in git polling task: {e}")
            await asyncio.sleep(poll_interval * 2)


def find_file_path(filename: str) -> Optional[str]:
    if git_repo := app_state.get('git_repo'):
        for file_data in git_repo.list_files("*.mcam"):
            if file_data['name'] == filename:
                return file_data['path']
    return None


def _get_current_file_state() -> Dict[str, List[Dict]]:
    git_repo, metadata_manager = app_state.get(
        'git_repo'), app_state.get('metadata_manager')
    if not git_repo or not metadata_manager:
        return {"Miscellaneous": []}
    try:
        git_repo.pull()
    except Exception as e:
        logger.warning(f"Failed to pull latest changes: {e}")
    repo_files, grouped_files = git_repo.list_files("*.mcam"), {}
    current_user = app_state.get('current_user', 'demo_user')
    for file_data in repo_files:
        meta_path = git_repo.repo_path / f"{file_data['path']}.meta.json"
        description, revision = None, None
        if meta_path.exists():
            try:
                meta_content = json.loads(meta_path.read_text())
                description, revision = meta_content.get(
                    'description'), meta_content.get('revision')
            except json.JSONDecodeError:
                logger.warning(
                    f"Could not parse metadata for {file_data['path']}")
        file_data['description'], file_data['revision'] = description, revision
        filename = file_data['name'].strip()
        group_name = "Miscellaneous"
        if re.match(r"^\d{7}.*\.mcam$", filename):
            group_name = f"{filename[:2]}XXXXX"
        if group_name not in grouped_files:
            grouped_files[group_name] = []
        lock_info = metadata_manager.get_lock_info(file_data['path'])
        status, locked_by, locked_at = "unlocked", None, None
        if lock_info:
            status, locked_by, locked_at = "locked", lock_info.get(
                'user'), lock_info.get('timestamp')
            if locked_by == current_user:
                status = "checked_out_by_user"
        file_data['filename'] = file_data.pop('name')
        file_data.update(
            {"status": status, "locked_by": locked_by, "locked_at": locked_at})
        grouped_files[group_name].append(file_data)
    return grouped_files


async def broadcast_file_list_update():
    try:
        logger.info("Broadcasting file list update...")
        await asyncio.sleep(0.2)
        grouped_data = _get_current_file_state()
        message = json.dumps({"type": "FILE_LIST_UPDATED",
                             "payload": grouped_data, "timestamp": datetime.utcnow().isoformat() + "Z"})
        if manager.active_connections:
            await manager.broadcast(message)
            logger.info(
                f"Broadcast complete to {len(manager.active_connections)} clients.")
        else:
            logger.debug("No active WebSocket connections to broadcast to.")
    except Exception as e:
        logger.error(f"Failed to broadcast file list update: {e}")


async def handle_successful_git_operation():
    global git_monitor
    if git_monitor:
        git_monitor.initialize_state()
    await broadcast_file_list_update()

# --- API Endpoints ---


@app.get("/", include_in_schema=False)
async def root(request: Request):
    """
    Serve the main application interface.

    Returns the main HTML template for the Mastercam GitLab Interface application.
    """
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/config",
         summary="Get Configuration",
         description="Retrieve the current application configuration including GitLab settings and user permissions.",
         response_description="Current configuration summary",
         tags=["Configuration"])
async def get_config():
    """
    Get current application configuration.

    Returns:
        dict: Configuration summary including:
            - gitlab_url: GitLab instance URL
            - project_id: GitLab project ID
            - username: Current username
            - has_token: Whether authentication token is configured
            - repo_path: Local repository path
            - is_admin: Whether current user has admin privileges

    Raises:
        HTTPException: 503 if application is not fully initialized
    """
    if config_manager := app_state.get('config_manager'):
        config_manager.update_gitlab_config(
            **request.model_dump(by_alias=False))
        asyncio.create_task(initialize_application())
        return {"status": "success"}
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Configuration manager not found.")


@app.get("/refresh",
         summary="Manual Refresh",
         description="Manually trigger a refresh of the file list and sync with the remote repository.",
         response_description="Refresh operation status",
         tags=["Repository"])
async def manual_refresh():
    """
    Manually refresh the repository and file list.

    Checks for remote changes, pulls updates if available, and broadcasts
    the updated file list to all connected clients.

    Returns:
        dict: Status and message indicating the result of the refresh operation

    Raises:
        HTTPException: 500 if refresh operation fails
    """
    try:
        if git_monitor and git_monitor.check_for_changes():
            await broadcast_file_list_update()
            return {"status": "success", "message": "Files refreshed"}
        else:
            await broadcast_file_list_update()
            return {"status": "success", "message": "No remote changes detected, UI resynced."}
    except Exception as e:
        logger.error(f"Manual refresh failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Refresh failed")


@app.get("/files",
         response_model=Dict[str, List[FileInfo]],
         summary="Get File List",
         description="Retrieve all files in the repository grouped by category, with their current status and metadata.",
         response_description="Grouped file list with status information",
         tags=["Files"])
async def get_files():
    """
    Get all files in the repository with their current status.

    Files are automatically grouped by naming convention (e.g., files starting
    with 7-digit numbers are grouped by their first two digits).

    Returns:
        Dict[str, List[FileInfo]]: Dictionary where keys are group names and
        values are lists of FileInfo objects containing:
            - filename: Name of the file
            - path: Relative path in repository
            - status: Current lock status (unlocked, locked, checked_out_by_user)
            - locked_by: User who has the file locked (if applicable)
            - locked_at: ISO timestamp when file was locked
            - size: File size in bytes
            - modified_at: Last modification timestamp
            - description: File description from metadata
            - revision: Current revision number

    Raises:
        HTTPException: 500 if file retrieval fails
    """
    try:
        grouped_data = _get_current_file_state()
        return {group: [FileInfo(**file_data) for file_data in files] for group, files in grouped_data.items()}
    except Exception as e:
        logger.error(f"Error in get_files endpoint: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve file list.")


@app.get("/users",
         summary="Get Users",
         description="Retrieve list of all users who have contributed to the repository based on commit history.",
         response_description="List of usernames from repository history",
         tags=["Users"])
async def get_users():
    """
    Get list of all users from repository commit history.

    Analyzes the Git commit history to extract unique author names
    who have contributed to the repository.

    Returns:
        dict: Dictionary containing:
            - users: List of unique usernames sorted alphabetically

    Raises:
        HTTPException: 500 if repository is not initialized or user retrieval fails
    """
    try:
        git_repo = app_state.get('git_repo')
        if not git_repo:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Repository not initialized.")
        users = git_repo.get_all_users_from_history()
        return {"users": users}
    except Exception as e:
        logger.error(
            f"An unexpected error occurred in get_users: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An internal error occurred: {e}")


@app.post("/messages/send",
          summary="Send Message",
          description="Send a message to another user (admin only). Messages are stored in the repository and synchronized across all instances.",
          response_description="Message sending status",
          tags=["Messages"])
async def send_message(request: SendMessageRequest):
    """
    Send a message to another user (admin only).

    Messages are stored as JSON files in the repository under .messages/
    and are synchronized across all instances through Git commits.

    Args:
        request: Message request containing:
            - recipient: Username of the message recipient
            - message: Message content
            - sender: Username of the message sender (must be admin)

    Returns:
        JSONResponse: Success status and confirmation message

    Raises:
        HTTPException:
            - 403 if sender is not an admin user
            - 500 if repository is not initialized or message sending fails
    """
    try:
        cfg_manager = app_state.get('config_manager')
        git_repo = app_state.get('git_repo')
        if not all([cfg_manager, git_repo]):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Repository not initialized.")
        admin_users = cfg_manager.config.security.get("admin_users", [])
        if request.sender not in admin_users:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied.")
        messages_dir = git_repo.repo_path / ".messages"
        messages_dir.mkdir(exist_ok=True)
        user_message_file = messages_dir / f"{request.recipient}.json"
        messages = []
        if user_message_file.exists():
            try:
                messages = json.loads(user_message_file.read_text())
            except json.JSONDecodeError:
                pass
        new_message = {"id": str(uuid.uuid4()), "sender": request.sender, "timestamp": datetime.utcnow(
        ).isoformat() + "Z", "message": request.message}
        messages.append(new_message)
        user_message_file.write_text(json.dumps(messages, indent=2))
        commit_message = f"MSG: Send message to {request.recipient} by {request.sender}"
        success = git_repo.commit_and_push([str(user_message_file.relative_to(
            git_repo.repo_path))], commit_message, request.sender, f"{request.sender}@example.com")
        if success:
            await handle_successful_git_operation()
            return JSONResponse({"status": "success", "message": "Message sent."})
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send message.")
    except Exception as e:
        logger.error(
            f"An unexpected error occurred in send_message: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An internal error occurred: {e}")


@app.post("/messages/acknowledge",
          summary="Acknowledge Message",
          description="Mark a received message as read/acknowledged, removing it from the user's message queue.",
          response_description="Message acknowledgment status",
          tags=["Messages"])
async def acknowledge_message(request: AckMessageRequest):
    """
    Acknowledge a received message.

    Removes the specified message from the user's message queue and
    commits the change to the repository.

    Args:
        request: Acknowledgment request containing:
            - message_id: Unique identifier of the message to acknowledge
            - user: Username acknowledging the message

    Returns:
        JSONResponse: Status indicating success or no change

    Raises:
        HTTPException: 500 if repository is not initialized or acknowledgment fails
    """
    try:
        git_repo = app_state.get('git_repo')
        if not git_repo:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Repository not initialized.")
        user_message_file = git_repo.repo_path / \
            ".messages" / f"{request.user}.json"
        if not user_message_file.exists():
            return JSONResponse({"status": "success"})
        messages = json.loads(user_message_file.read_text())
        messages_after_ack = [
            msg for msg in messages if msg.get("id") != request.message_id]
        if len(messages) == len(messages_after_ack):
            return JSONResponse({"status": "no_change"})
        user_message_file.write_text(json.dumps(messages_after_ack, indent=2))
        commit_message = f"MSG: Acknowledge message by {request.user}"
        success = git_repo.commit_and_push([str(user_message_file.relative_to(
            git_repo.repo_path))], commit_message, request.user, f"{request.user}@example.com")
        if success:
            await handle_successful_git_operation()
            return JSONResponse({"status": "success"})
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to acknowledge message.")
    except Exception as e:
        logger.error(
            f"An unexpected error occurred in acknowledge_message: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An internal error occurred: {e}")


@app.post("/files/new_upload",
          summary="Upload New File",
          description="Upload a brand new file to the repository. File must not already exist.",
          response_description="Upload status",
          tags=["Files"])
async def new_upload(
    user: str = Form(..., description="Username performing the upload"),
    description: str = Form(..., description="Description of the file"),
    rev: str = Form(..., description="Initial revision number", example="1.0"),
    file: UploadFile = File(..., description="File to upload")
):
    """
    Upload a new file to the repository.

    Creates a new file entry with metadata and commits it to the repository.
    The file must not already exist in the repository.

    Args:
        user: Username performing the upload
        description: File description for metadata
        rev: Initial revision number
        file: File upload object

    Returns:
        JSONResponse: Success status

    Raises:
        HTTPException:
            - 400 if file is empty
            - 409 if file already exists
            - 500 if repository is not available or upload fails
    """
    try:
        git_repo = app_state.get('git_repo')
        if not git_repo or not app_state['initialized']:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Repository not available.")
        content, filename_str = await file.read(), file.filename
        if find_file_path(filename_str) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"File '{filename_str}' already exists. Use the check-in process for existing files.")
        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File is empty.")
        git_repo.save_file(filename_str, content)
        meta_filename_str = f"{filename_str}.meta.json"
        meta_content = {"description": description, "revision": rev}
        (git_repo.repo_path /
         meta_filename_str).write_text(json.dumps(meta_content, indent=2))
        commit_message = f"ADD: {filename_str} (Rev: {rev}) by {user}"
        success = git_repo.commit_and_push(
            [filename_str, meta_filename_str], commit_message, user, f"{user}@example.com")
        if success:
            await handle_successful_git_operation()
            return JSONResponse({"status": "success"})
        (git_repo.repo_path / meta_filename_str).unlink(missing_ok=True)
        (git_repo.repo_path / filename_str).unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to commit new file.")
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(
            f"An unexpected error occurred in new_upload: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An internal error occurred: {e}")


@app.post("/files/{filename}/checkout",
          summary="Check Out File",
          description="Lock a file for editing by the specified user. Creates or refreshes a lock.",
          response_description="Checkout operation status",
          tags=["Files"])
async def checkout_file(
    filename: str = FastAPIPath(...,
                                description="Name of the file to check out"),
    request: CheckoutRequest = ...
):
    """
    Check out (lock) a file for editing.

    Creates a lock file in the repository to prevent other users from
    simultaneously editing the same file. If the user already has the
    file locked, refreshes the lock timestamp.

    Args:
        filename: Name of the file to check out
        request: Checkout request containing the username

    Returns:
        JSONResponse: Success status and optional message

    Raises:
        HTTPException:
            - 404 if file is not found
            - 409 if file is already locked by another user
            - 500 if repository is not initialized or checkout fails
    """
    try:
        git_repo, metadata_manager = app_state.get(
            'git_repo'), app_state.get('metadata_manager')
        if not git_repo or not metadata_manager:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Repository not initialized.")
        git_repo.pull()
        file_path = find_file_path(filename)
        if not file_path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found")
        existing_lock = metadata_manager.get_lock_info(file_path)
        if existing_lock:
            if existing_lock.get('user') == request.user:
                refreshed = metadata_manager.refresh_lock(
                    file_path, request.user)
                if not refreshed:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Failed to refresh existing lock.")
                relative_lock_path_str = str(refreshed.relative_to(
                    git_repo.repo_path)).replace(os.sep, '/')
                commit_message = f"REFRESH LOCK: {filename} by {request.user}"
                success = git_repo.commit_and_push(
                    [relative_lock_path_str], commit_message, request.user, f"{request.user}@example.com")
                if success:
                    await handle_successful_git_operation()
                    return JSONResponse({"status": "success", "message": "Lock refreshed."})
                else:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Failed to push refreshed lock.")
            else:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="File is already locked by another user.")
        lock_file_path = metadata_manager.create_lock(file_path, request.user)
        if not lock_file_path:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create lock file.")
        relative_lock_path_str = str(lock_file_path.relative_to(
            git_repo.repo_path)).replace(os.sep, '/')
        commit_message = f"LOCK: {filename} by {request.user}"
        success = git_repo.commit_and_push(
            [relative_lock_path_str], commit_message, request.user, f"{request.user}@example.com")
        if success:
            await handle_successful_git_operation()
            return JSONResponse({"status": "success"})
        metadata_manager.release_lock(file_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to push lock file.")
    except Exception as e:
        logger.error(
            f"An unexpected error occurred in checkout_file: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An internal error occurred: {e}")


@app.post("/files/{filename}/checkin",
          summary="Check In File",
          description="Check in an updated version of a locked file, incrementing the revision and releasing the lock.",
          response_description="Check-in operation status",
          tags=["Files"])
async def checkin_file(
    filename: str = FastAPIPath(...,
                                description="Name of the file to check in"),
    user: str = Form(..., description="Username performing the check-in"),
    commit_message: str = Form(...,
                               description="Commit message describing the changes"),
    rev_type: str = Form(..., description="Type of revision increment",
                         regex="^(major|minor)$"),
    new_major_rev: Optional[str] = Form(
        None, description="Specific major revision number (for major increments only)"),
    file: UploadFile = File(..., description="Updated file content")
):
    """
    Check in an updated file with automatic revision incrementing.

    Updates the file content, increments the revision number according to
    the specified revision type, and releases the user's lock on the file.

    Args:
        filename: Name of the file to check in
        user: Username performing the check-in (must have file locked)
        commit_message: Description of changes made
        rev_type: Type of revision increment ('major' or 'minor')
        new_major_rev: Specific major revision number (only for major increments)
        file: Updated file content

    Returns:
        JSONResponse: Success status

    Raises:
        HTTPException:
            - 403 if user doesn't have the file locked
            - 404 if file is not found
            - 500 if check-in operation fails
    """
    try:
        git_repo, metadata_manager = app_state.get(
            'git_repo'), app_state.get('metadata_manager')
        if not git_repo or not metadata_manager:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Repository not initialized.")
        file_path = find_file_path(filename)
        if not file_path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found")
        lock_info = metadata_manager.get_lock_info(file_path)
        if not lock_info or lock_info['user'] != user:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have this file locked.")
        content = await file.read()
        git_repo.save_file(file_path, content)
        meta_path = git_repo.repo_path / f"{file_path}.meta.json"
        meta_content = {}
        if meta_path.exists():
            try:
                meta_content = json.loads(meta_path.read_text())
            except json.JSONDecodeError:
                pass
        current_rev = meta_content.get("revision", "")

        # This is the key change: passing 'new_major_rev' to the increment function
        new_rev = _increment_revision(current_rev, rev_type, new_major_rev)

        meta_content["revision"] = new_rev
        meta_path.write_text(json.dumps(meta_content, indent=2))
        absolute_lock_path = metadata_manager._get_lock_file_path(file_path)
        relative_lock_path_str = str(absolute_lock_path.relative_to(
            git_repo.repo_path)).replace(os.sep, '/')
        metadata_manager.release_lock(file_path)
        final_commit_message = f"REV {new_rev}: {commit_message}"
        files_to_commit = [file_path, str(meta_path.relative_to(
            git_repo.repo_path)), relative_lock_path_str]
        success = git_repo.commit_and_push(
            files_to_commit, final_commit_message, user, f"{user}@example.com")
        if success:
            await handle_successful_git_operation()
            return JSONResponse({"status": "success"})
        else:
            metadata_manager.create_lock(file_path, user, force=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to push changes.")
    except Exception as e:
        logger.error(
            f"An unexpected error occurred in checkin_file: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An internal error occurred: {e}")


@app.post("/files/{filename}/cancel_checkout",
          summary="Cancel File Checkout",
          description="Cancel a file checkout, releasing the lock without making changes.",
          response_description="Cancel operation status",
          tags=["Files"])
async def cancel_checkout(
    filename: str = FastAPIPath(...,
                                description="Name of the file to cancel checkout for"),
    request: CheckoutRequest = ...
):
    """
    Cancel a file checkout operation.

    Releases the user's lock on the specified file without making any
    changes to the file content or revision.

    Args:
        filename: Name of the file to cancel checkout for
        request: Request containing the username

    Returns:
        JSONResponse: Success status

    Raises:
        HTTPException:
            - 403 if user doesn't have the file checked out
            - 404 if file is not found
            - 500 if cancel operation fails
    """
    try:
        git_repo, metadata_manager = app_state.get(
            'git_repo'), app_state.get('metadata_manager')
        if not git_repo or not metadata_manager:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Repository not initialized.")
        file_path = find_file_path(filename)
        if not file_path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found")
        lock_info = metadata_manager.get_lock_info(file_path)
        if not lock_info or lock_info['user'] != request.user:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have this file checked out.")
        absolute_lock_path = metadata_manager._get_lock_file_path(file_path)
        relative_lock_path_str = str(absolute_lock_path.relative_to(
            git_repo.repo_path)).replace(os.sep, '/')
        metadata_manager.release_lock(file_path)
        commit_message = f"USER CANCEL: Unlock {filename} by {request.user}"
        success = git_repo.commit_and_push(
            [relative_lock_path_str], commit_message, request.user, f"{request.user}@example.com")
        if success:
            await handle_successful_git_operation()
            return JSONResponse({"status": "success"})
        else:
            metadata_manager.create_lock(file_path, request.user, force=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to commit checkout cancel.")
    except Exception as e:
        logger.error(
            f"An unexpected error occurred in cancel_checkout: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An internal error occurred: {e}")


@app.delete("/files/{filename}/delete",
            summary="Admin Delete File",
            description="Permanently delete a file from the repository (admin only).",
            response_description="Deletion status",
            tags=["Files", "Admin"])
async def admin_delete_file(
    filename: str = Path(..., description="Name of the file to delete"),
    request: AdminDeleteRequest = ...
):
    """
    Permanently delete a file from the repository (admin only).

    Removes the file, its metadata, and any associated locks from the
    repository. This operation cannot be undone except through Git history.

    Args:
        filename: Name of the file to delete
        request: Delete request containing the admin username

    Returns:
        JSONResponse: Success status and confirmation message

    Raises:
        HTTPException:
            - 403 if user is not an admin
            - 404 if file is not found
            - 500 if repository is not initialized or deletion fails
    """
    try:
        cfg_manager, git_repo, metadata_manager = app_state.get(
            'config_manager'), app_state.get('git_repo'), app_state.get('metadata_manager')
        if not all([cfg_manager, git_repo, metadata_manager]):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Repository not initialized.")
        admin_users = cfg_manager.config.security.get("admin_users", [])
        if request.admin_user not in admin_users:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied. Admin access required.")
        file_path_str = find_file_path(filename)
        if not file_path_str:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found")
        absolute_file_path = git_repo.repo_path / file_path_str
        absolute_lock_path = metadata_manager._get_lock_file_path(
            file_path_str)
        relative_lock_path_str = str(absolute_lock_path.relative_to(
            git_repo.repo_path)).replace(os.sep, '/')
        files_to_commit = [file_path_str]
        if absolute_lock_path.exists():
            files_to_commit.append(relative_lock_path_str)
        meta_path = git_repo.repo_path / f"{file_path_str}.meta.json"
        if meta_path.exists():
            files_to_commit.append(
                str(meta_path.relative_to(git_repo.repo_path)))
            meta_path.unlink()
        absolute_file_path.unlink(missing_ok=True)
        metadata_manager.release_lock(file_path_str)
        commit_message = f"ADMIN DELETE: {filename} by {request.admin_user}"
        success = git_repo.commit_and_push(
            files_to_commit, commit_message, request.admin_user, f"{request.admin_user}@example.com")
        if success:
            await handle_successful_git_operation()
            return JSONResponse({"status": "success", "message": f"File '{filename}' permanently deleted."})
        else:
            git_repo.pull()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to commit the file deletion.")
    except Exception as e:
        logger.error(
            f"An unexpected error occurred in admin_delete_file: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An internal error occurred: {e}")


@app.get("/files/{filename}/download",
         summary="Download File",
         description="Download the current version of a file from the repository.",
         response_description="File content as binary download",
         tags=["Files"])
async def download_file(filename: str = Path(..., description="Name of the file to download")):
    """
    Download the current version of a file.

    Args:
        filename: Name of the file to download

    Returns:
        Response: Binary file content with appropriate headers for download

    Raises:
        HTTPException: 404 if file is not found
    """
    git_repo, file_path = app_state.get('git_repo'), find_file_path(filename)
    if not git_repo or not file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    content = git_repo.get_file_content(file_path)
    if content is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return Response(content, media_type='application/octet-stream', headers={'Content-Disposition': f'attachment; filename="{filename}"'})


@app.get("/files/{filename}/history",
         summary="Get File History",
         description="Retrieve the commit history for a specific file, including revision information.",
         response_description="File commit history with revision details",
         tags=["Files"])
async def get_file_history(filename: str = Path(..., description="Name of the file to get history for")):
    """
    Get commit history for a specific file.

    Retrieves the Git commit history for the specified file, including
    revision information extracted from metadata files.

    Args:
        filename: Name of the file to get history for

    Returns:
        dict: Dictionary containing:
            - filename: The requested filename
            - history: List of commit entries with:
                - commit_hash: Git commit hash
                - author_name: Name of the committer
                - author_email: Email of the committer
                - date: ISO timestamp of the commit
                - message: Commit message
                - revision: File revision at that commit (if available)

    Raises:
        HTTPException:
            - 404 if file is not found
            - 500 if history retrieval fails
    """
    try:
        file_path = find_file_path(filename)
        if not file_path or not (git_repo := app_state.get('git_repo')):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return {"filename": filename, "history": git_repo.get_file_history(file_path)}
    except Exception as e:
        logger.error(
            f"An unexpected error occurred in get_file_history: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An internal error occurred: {e}")


@app.get("/files/{filename}/versions/{commit_hash}",
         summary="Download File Version",
         description="Download a specific historical version of a file from a particular commit.",
         response_description="Historical file version as binary download",
         tags=["Files"])
async def download_file_version(
    filename: str = Path(..., description="Name of the file"),
    commit_hash: str = Path(...,
                            description="Git commit hash of the desired version")
):
    """
    _state.get('config_manager'):
        return config_manager.get_config_summary()
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Application not fully initialized.")


@app.post("/config/gitlab",
          summary="Update GitLab Configuration",
          description="Update the GitLab connection settings and reinitialize the application.",
          response_description="Configuration update status",
          tags=["Configuration"])
async def update_gitlab_config(request: ConfigUpdateRequest):
    """
    Update GitLab configuration settings.

    Args:
        request: Configuration update request containing:
            - base_url: GitLab instance URL
            - project_id: GitLab project ID
            - username: GitLab username
            - token: GitLab personal access token

    Returns:
        dict: Status message indicating success

    Raises:
        HTTPException: 500 if configuration manager is not available
    """
    if config_manager := app
