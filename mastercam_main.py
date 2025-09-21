#!/usr/bin/env python3
"""
Mastercam GitLab Interface - Final Integrated Application
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
from git import Actor  # Add this import
import requests
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Form, UploadFile, File, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.websockets import WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, ValidationError

# Pydantic-friendly dataclasses
from cryptography.fernet import Fernet
import base64

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

class AppConfig(BaseModel):
    version: str = "1.0.0"
    gitlab: dict = Field(default_factory=lambda: {
        "base_url": "",
        "project_id": "",
        "username": "",
        "token": "",
        "branch": "main",
        "timeout": 30
    })
    local: dict = Field(default_factory=lambda: {
        "repo_path": str(Path.home() / "MastercamGitRepo"),
        "backup_path": str(Path.home() / "MastercamGitBackups"),
        "temp_path": str(Path.home() / "mastercam_git_interface_temp"),
        "max_file_size_mb": 500,
        "auto_backup": True,
        "cleanup_temp_files": True
    })
    ui: dict = Field(default_factory=lambda: {
        "theme": "light",
        "language": "en",
        "auto_refresh_interval": 30,
        "show_file_details": True,
        "show_notifications": True,
        "notification_sound": False
    })
    security: dict = Field(default_factory=lambda: {
        "encrypt_tokens": True,
        "session_timeout_hours": 8,
        "max_failed_attempts": 3,
        "require_admin_confirmation": True,
        "auto_lock_stale_files_hours": 24
    })
    
    def model_post_init(self, __context: Any) -> None:
        if not self.local['repo_path']:
            self.local['repo_path'] = str(self.get_default_repo_path())
        if not self.local['backup_path']:
            self.local['backup_path'] = str(self.get_default_backup_path())
        if not self.local['temp_path']:
            self.local['temp_path'] = str(self.get_default_temp_path())

    @staticmethod
    def get_default_repo_path() -> Path:
        if os.name == 'nt':
            return Path.home() / 'Documents' / 'MastercamGitRepo'
        else:
            return Path.home() / '.mastercam_git_repo'
    
    @staticmethod
    def get_default_backup_path() -> Path:
        if os.name == 'nt':
            return Path.home() / 'Documents' / 'MastercamGitBackups'
        else:
            return Path.home() / '.mastercam_git_backups'
    
    @staticmethod
    def get_default_temp_path() -> Path:
        return Path(tempfile.gettempdir()) / 'mastercam_git_interface'

class EncryptionManager:
    def __init__(self, config_dir: Path):
        self.config_dir = Path(config_dir)
        self.key_file = self.config_dir / '.encryption_key'
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
            logger.info("Encryption initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize encryption: {str(e)}")
            self._fernet = None
    
    def encrypt(self, data: str) -> str:
        try:
            if self._fernet:
                encrypted = self._fernet.encrypt(data.encode())
                return base64.b64encode(encrypted).decode()
            else:
                return base64.b64encode(data.encode()).decode()
        except Exception as e:
            logger.error(f"Encryption failed: {str(e)}")
            return data
    
    def decrypt(self, encrypted_data: str) -> str:
        try:
            if self._fernet:
                encrypted_bytes = base64.b64decode(encrypted_data.encode())
                decrypted = self._fernet.decrypt(encrypted_bytes)
                return decrypted.decode()
            else:
                return base64.b64decode(encrypted_data.encode()).decode()
        except Exception as e:
            logger.error(f"Decryption failed: {str(e)}")
            return encrypted_data

class ConfigManager:
    def __init__(self, config_dir: Optional[Path] = None):
        if config_dir is None:
            config_dir = self._get_default_config_dir()
        
        self.config_dir = Path(config_dir)
        self.config_file = self.config_dir / 'config.json'
        self.user_file = self.config_dir / 'user_settings.json'
        
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        self.encryption = EncryptionManager(self.config_dir)
        
        self.config = self._load_config()
        self.user_settings = self._load_user_settings()
    
    @staticmethod
    def _get_default_config_dir() -> Path:
        if os.name == 'nt':
            base = Path.home() / 'AppData' / 'Local' / 'MastercamGitInterface'
        else:
            base = Path.home() / '.config' / 'mastercam_git_interface'
        return base
    
    def _load_config(self) -> AppConfig:
        try:
            if self.config_file.exists():
                content = self.config_file.read_text()
                if not content:
                    logger.warning("Configuration file is empty. Using default configuration.")
                    return AppConfig()
                
                data = json.loads(content)
                
                if 'gitlab' in data and 'token' in data['gitlab']:
                    if data['gitlab']['token']:
                        data['gitlab']['token'] = self.encryption.decrypt(data['gitlab']['token'])
                
                config = AppConfig(**data)
                return config
            else:
                logger.info("No existing configuration found, creating default")
                return AppConfig()
        except Exception as e:
            logger.error(f"Failed to load configuration: {str(e)}")
            return AppConfig()
    
    def _load_user_settings(self) -> Dict:
        try:
            if self.user_file.exists():
                return json.loads(self.user_file.read_text())
            return {}
        except Exception as e:
            logger.error(f"Failed to load user settings: {str(e)}")
            return {}
    
    def save_config(self) -> bool:
        try:
            data = self.config.model_dump()
            
            if self.config.security.get('encrypt_tokens', False) and self.config.gitlab.get('token'):
                data['gitlab']['token'] = self.encryption.encrypt(self.config.gitlab['token'])
            
            self.config_file.write_text(json.dumps(data, indent=2))
            logger.info("Configuration saved successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to save configuration: {str(e)}")
            return False
    
    def save_user_settings(self) -> bool:
        try:
            self.user_file.write_text(json.dumps(self.user_settings, indent=2))
            return True
        except Exception as e:
            logger.error(f"Failed to save user settings: {str(e)}")
            return False
    
    def update_gitlab_config(self, base_url: str, project_id: str, username: str, token: str) -> bool:
        try:
            self.config.gitlab['base_url'] = base_url.rstrip('/')
            self.config.gitlab['project_id'] = project_id
            self.config.gitlab['username'] = username
            self.config.gitlab['token'] = token
            return self.save_config()
        except Exception as e:
            logger.error(f"Failed to update GitLab configuration: {str(e)}")
            return False
    
    def validate_config(self) -> tuple[bool, list[str]]:
        errors = []
        if not self.config.gitlab['base_url']:
            errors.append("GitLab base URL is required")
        if not self.config.gitlab['project_id']:
            errors.append("GitLab project ID is required")
        if not self.config.gitlab['username']:
            errors.append("GitLab username is required")
        if not self.config.gitlab['token']:
            errors.append("GitLab access token is required")
        
        try:
            repo_path = Path(self.config.local['repo_path'])
            repo_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            errors.append(f"Invalid repository path: {str(e)}")
        
        try:
            backup_path = Path(self.config.local['backup_path'])
            backup_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            errors.append(f"Invalid backup path: {str(e)}")
        
        if self.config.local['max_file_size_mb'] <= 0:
            errors.append("Maximum file size must be positive")
        
        if self.config.ui['auto_refresh_interval'] <= 0:
            errors.append("Auto-refresh interval must be positive")
        
        return len(errors) == 0, errors
    
    def get_config_summary(self) -> Dict[str, Any]:
        return {
            'gitlab_url': self.config.gitlab['base_url'],
            'project_id': self.config.gitlab['project_id'],
            'username': self.config.gitlab['username'],
            'has_token': bool(self.config.gitlab['token']),
            'repo_path': self.config.local['repo_path'],
            'backup_enabled': self.config.local['auto_backup'],
            'theme': self.config.ui['theme'],
            'auto_refresh': self.config.ui['auto_refresh_interval'],
            'version': self.config.version
        }

class GitLabAPI:
    def __init__(self, base_url: str, token: str, project_id: str):
        self.base_url = f"{base_url}/api/v4"
        self.project_id = project_id
        self.headers = {"Private-Token": token}

    def test_connection(self) -> bool:
        try:
            response = requests.get(f"{self.base_url}/projects/{self.project_id}", headers=self.headers, timeout=10)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"GitLab connection test failed: {e}")
            return False

# class GitRepository:
#     def __init__(self, repo_path: Path, remote_url: str, username: str, token: str):
#         self.repo_path = repo_path
#         self.remote_url = remote_url
#         self.username = username
#         self.token = token
#         self.repo = None

#     def _get_credential_url(self) -> str:
#         return f"https://oauth2:{self.token}@{self.remote_url.split('://')[-1]}"

#     def clone_or_pull(self) -> bool:
#         try:
#             if not self.repo_path.exists():
#                 logger.info(f"Cloning repository from {self.remote_url} to {self.repo_path}")
#                 self.repo = git.Repo.clone_from(self._get_credential_url(), self.repo_path)
#             else:
#                 try:
#                     self.repo = git.Repo(self.repo_path)
#                     logger.info(f"Pulling latest changes from repository at {self.repo_path}")
#                     self.repo.remotes.origin.pull()
#                 except git.exc.InvalidGitRepositoryError:
#                     logger.warning(f"Local path exists but is not a Git repository. Cloning fresh...")
#                     self.repo = git.Repo.clone_from(self._get_credential_url(), self.repo_path)
#             return True
#         except git.GitCommandError as e:
#             logger.error(f"Git operation failed: {e}")
#             return False

#     def list_files(self, pattern: str = "*.mcam") -> List[Dict]:
#         if not self.repo:
#             return []
        
#         files = []
#         for root, dirs, filenames in os.walk(self.repo_path):
#             if ".git" in root:
#                 continue
            
#             for filename in filenames:
#                 file_path = Path(root) / filename
#                 if file_path.match(pattern):
#                     rel_path = str(file_path.relative_to(self.repo_path))
#                     try:
#                         file_stat = os.stat(file_path)
#                         files.append({
#                             "name": filename,
#                             "path": rel_path,
#                             "size": file_stat.st_size,
#                             "modified_at": datetime.fromtimestamp(file_stat.st_mtime).isoformat() + "Z"
#                         })
#                     except OSError:
#                         pass
#         return files
    
#     def get_file_content(self, file_path: str) -> Optional[bytes]:
#         full_path = self.repo_path / file_path
#         if full_path.exists():
#             return full_path.read_bytes()
#         return None

#     def save_file(self, file_path: str, content: bytes) -> bool:
#         try:
#             full_path = self.repo_path / file_path
#             full_path.parent.mkdir(parents=True, exist_ok=True)
#             full_path.write_bytes(content)
#             return True
#         except IOError as e:
#             logger.error(f"Failed to save file: {e}")
#             return False

#     def commit_and_push(self, file_path: str, message: str, author_name: str, author_email: str) -> bool:
#         if not self.repo:
#             return False
        
#         try:
#             self.repo.index.add([file_path])
#             self.repo.index.commit(message, author=git.Actor(author_name, author_email))
            
#             logger.info("Pushing changes to remote repository...")
#             self.repo.git.push(self._get_credential_url(), f"main:{self.repo.active_branch}")
            
#             logger.info("Changes successfully pushed to GitLab.")
#             return True
#         except git.GitCommandError as e:
#             logger.error(f"Git commit/push failed: {e}")
#             return False

#     def get_file_history(self, file_path: str, limit: int = 10) -> List[Dict]:
#         if not self.repo:
#             return []
        
#         try:
#             commits = list(self.repo.iter_commits(paths=file_path, max_count=limit))
#             history = []
#             for commit in commits:
#                 history.append({
#                     "commit_hash": commit.hexsha,
#                     "author_name": commit.author.name,
#                     "author_email": commit.author.email,
#                     "date": datetime.fromtimestamp(commit.committed_date).isoformat() + "Z",
#                     "message": commit.message.strip()
#                 })
#             return history
#         except git.exc.GitCommandError:
#             return []


# In mastercam_main.py, replace your GitRepository class with this one.
class GitRepository:
    def __init__(self, repo_path: Path, remote_url: str, username: str, token: str):
        self.repo_path = repo_path
        self.remote_url = remote_url
        self.username = username
        self.token = token
        self.repo = None

    def _get_credential_url(self) -> str:
        return f"https://oauth2:{self.token}@{self.remote_url.split('://')[-1]}"

    def clone_or_pull(self) -> bool:
        try:
            if not self.repo_path.exists():
                logger.info(f"Cloning repository from {self.remote_url} to {self.repo_path}")
                self.repo = git.Repo.clone_from(self._get_credential_url(), self.repo_path)
            else:
                try:
                    self.repo = git.Repo(self.repo_path)
                    logger.info(f"Pulling latest changes from repository at {self.repo_path}")
                    self.repo.remotes.origin.pull()
                except git.exc.InvalidGitRepositoryError:
                    logger.warning(f"Local path exists but is not a Git repository. Cloning fresh...")
                    self.repo = git.Repo.clone_from(self._get_credential_url(), self.repo_path)
            return True
        except git.GitCommandError as e:
            logger.error(f"Git operation failed: {e}")
            return False

    def list_files(self, pattern: str = "*.mcam") -> List[Dict]:
        if not self.repo:
            return []
        
        files = []
        for root, dirs, filenames in os.walk(self.repo_path):
            if ".git" in root:
                continue
            
            for filename in filenames:
                file_path = Path(root) / filename
                if file_path.match(pattern):
                    rel_path = str(file_path.relative_to(self.repo_path))
                    try:
                        file_stat = os.stat(file_path)
                        files.append({
                            "name": filename,
                            "path": rel_path,
                            "size": file_stat.st_size,
                            "modified_at": datetime.fromtimestamp(file_stat.st_mtime).isoformat() + "Z"
                        })
                    except OSError:
                        pass
        return files
    
    def get_file_content(self, file_path: str) -> Optional[bytes]:
        full_path = self.repo_path / file_path
        if full_path.exists():
            return full_path.read_bytes()
        return None

    def save_file(self, file_path: str, content: bytes) -> bool:
        try:
            full_path = self.repo_path / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_bytes(content)
            return True
        except IOError as e:
            logger.error(f"Failed to save file: {e}")
            return False

    def commit_and_push(self, file_paths: List[str], message: str, author_name: str, author_email: str) -> bool:
        """
        Stages, commits, and pushes a list of file changes to the remote repository.
        This can include new files, modified files, and deleted files.
        """
        if not self.repo:
            return False

        try:
            # The key change: add all specified file paths to the index.
            # This works for additions, modifications, and deletions (git add handles it).
            self.repo.index.add(file_paths)

            # Check if there is anything to commit
            if not self.repo.index.diff("HEAD"):
                logger.info("No changes to commit.")
                return True # Nothing to do, so operation is successful

            author = Actor(author_name, author_email)
            self.repo.index.commit(message, author=author)

            logger.info("Pushing changes to remote repository...")
            # Assuming 'main' branch, adjust if necessary
            self.repo.remotes.origin.push(refspec=f'HEAD:{self.repo.active_branch}')

            logger.info("Changes successfully pushed to GitLab.")
            return True
        except git.GitCommandError as e:
            logger.error(f"Git commit/push failed: {e}")
            # Attempt to reset HEAD if push fails to avoid inconsistent state
            self.repo.git.reset('--hard', 'origin/main')
            return False



    def get_file_history(self, file_path: str, limit: int = 10) -> List[Dict]:
        if not self.repo:
            return []
        
        try:
            commits = list(self.repo.iter_commits(paths=file_path, max_count=limit))
            history = []
            for commit in commits:
                history.append({
                    "commit_hash": commit.hexsha,
                    "author_name": commit.author.name,
                    "author_email": commit.author.email,
                    "date": datetime.fromtimestamp(commit.committed_date).isoformat() + "Z",
                    "message": commit.message.strip()
                })
            return history
        except git.exc.GitCommandError:
            return []

class MetadataManager:
    """
    Manages lock files by storing them directly within the Git repository,
    making the lock status accessible to all users via git pull/push.
    """
    def __init__(self, repo_path: Path):
        # The lock directory is now INSIDE the main repository path
        self.locks_dir = repo_path / '.locks'
        self.locks_dir.mkdir(parents=True, exist_ok=True)
        # Create a .gitignore file in the locks dir if it doesn't exist
        # This is optional but good practice if you have other metadata
        gitignore_path = self.locks_dir / '.gitignore'
        if not gitignore_path.exists():
            # This ensures only .lock files are tracked, ignoring other potential temp files.
            gitignore_path.write_text("*\n!*.lock\n")


    def _get_lock_file_path(self, file_path_str: str) -> Path:
        """Generates a safe, unique filename for the lock file."""
        # Sanitize the file path to create a valid filename
        sanitized_filename = file_path_str.replace(os.path.sep, '_').replace('.', '_')
        return self.locks_dir / f"{sanitized_filename}.lock"

    def create_lock(self, file_path_str: str, user: str) -> Optional[Path]:
        """
        Creates a new lock file. Returns the path to the lock file on success,
        or None if it already exists.
        """
        lock_file = self._get_lock_file_path(file_path_str)
        if lock_file.exists():
            return None  # Lock failed, file is already locked

        lock_data = {
            "file": file_path_str,
            "user": user,
            "timestamp": datetime.now().isoformat() + "Z"
        }
        with open(lock_file, "w") as f:
            json.dump(lock_data, f, indent=4)
        return lock_file # Return the path of the created lock file

    def release_lock(self, file_path_str: str, user: Optional[str] = None) -> bool:
        """
        Deletes a lock file, optionally verifying the user.
        """
        lock_file = self._get_lock_file_path(file_path_str)
        if not lock_file.exists():
            return True # Already unlocked

        if user:
            try:
                lock_data = json.loads(lock_file.read_text())
                if lock_data.get("user") != user:
                    return False # Locked by someone else
            except (IOError, json.JSONDecodeError):
                return False # Cannot read lock file

        os.remove(lock_file)
        return True

    def get_lock_info(self, file_path_str: str) -> Optional[Dict]:
        """Reads and returns the contents of a lock file, if it exists."""
        lock_file = self._get_lock_file_path(file_path_str)
        if not lock_file.exists():
            return None

        try:
            return json.loads(lock_file.read_text())
        except (IOError, json.JSONDecodeError):
            return None


class ConnectionManager:
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
        
        for user, connections in self.user_connections.items():
            if websocket in connections:
                connections.remove(websocket)
                if not connections:
                    del self.user_connections[user]
                break
        
        logger.info(f"WebSocket connection closed. Total: {len(self.active_connections)}")
    
    async def send_personal_message(self, message: str, websocket: WebSocket):
        try:
            await websocket.send_text(message)
        except Exception:
            self.disconnect(websocket)
    
    async def send_to_user(self, message: str, user: str):
        if user in self.user_connections:
            disconnected = []
            for connection in self.user_connections[user]:
                try:
                    await connection.send_text(message)
                except Exception:
                    disconnected.append(connection)
            
            for connection in disconnected:
                self.disconnect(connection)
    
    async def broadcast(self, message: str):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.append(connection)
            
            for connection in disconnected:
                self.disconnect(connection)

manager = ConnectionManager()
app_state = {
    'config_manager': None,
    'git_repo': None,
    'metadata_manager': None,
    'gitlab_api': None,
    'initialized': False,
    'current_user': 'demo_user'
}

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

# Helper functions
def get_demo_files() -> List[FileInfo]:
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
            status="locked",
            locked_by="other_user",
            locked_at="2024-01-15T12:00:00Z",
            size=1572864,
            modified_at="2024-01-14T16:45:00Z",
            version_info={"latest_commit": "ghi11111", "latest_author": "other_user", "commit_count": 2}
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

async def process_checkin(filename: str, content: bytes, user: str):
    try:
        if app_state.get('git_repo') and app_state['initialized']:
            if app_state['config_manager'].config.local.get('auto_backup', False):
                create_backup(filename, content)
            
            if app_state['git_repo'].save_file(filename, content):
                commit_message = f"Update {filename} by {user}"
                author_email = f"{user}@example.com"
                
                success = app_state['git_repo'].commit_and_push(filename, commit_message, user, author_email)
                
                if success:
                    logger.info(f"File '{filename}' successfully committed and pushed")
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

async def process_new_upload(filename: str, content: bytes, user: str):
    try:
        if app_state.get('git_repo') and app_state['initialized']:
            if app_state['git_repo'].save_file(filename, content):
                commit_message = f"Add new file {filename} by {user}"
                author_email = f"{user}@example.com"
                
                success = app_state['git_repo'].commit_and_push(filename, commit_message, user, author_email)
                
                if success:
                    logger.info(f"New file '{filename}' successfully committed and pushed")
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

# async def initialize_application():
#     try:
#         app_state['config_manager'] = ConfigManager()
#         config = app_state['config_manager'].config
        
#         metadata_path = Path(config.local.get('temp_path')) / 'metadata'
#         app_state['metadata_manager'] = MetadataManager(metadata_path)
        
#         user_provided_repo_url = config.gitlab.get('base_url')

#         if user_provided_repo_url and config.gitlab.get('token'):
#             try:
#                 api_base_url_parts = user_provided_repo_url.split('/')[:3]
#                 api_base_url = '/'.join(api_base_url_parts)
#                 if not api_base_url:
#                     api_base_url = "https://gitlab.com"
#             except Exception as e:
#                 logger.warning(f"Could not parse API base URL from '{user_provided_repo_url}': {e}. Defaulting to https://gitlab.com")
#                 api_base_url = "https://gitlab.com"

#             app_state['gitlab_api'] = GitLabAPI(
#                 base_url=api_base_url,
#                 token=config.gitlab.get('token'),
#                 project_id=config.gitlab.get('project_id')
#             )
            
#             if app_state['gitlab_api'].test_connection():
#                 logger.info("GitLab connection established")
                
#                 app_state['git_repo'] = GitRepository(
#                     repo_path=Path(config.local.get('repo_path')),
#                     remote_url=user_provided_repo_url,
#                     username=config.gitlab.get('username'),
#                     token=config.gitlab.get('token')
#                 )
                
#                 if app_state['git_repo'].clone_or_pull():
#                     logger.info("Repository synchronized")
#                     app_state['initialized'] = True
#                 else:
#                     logger.warning("Failed to synchronize repository")
#             else:
#                 logger.warning("GitLab connection failed")
#         else:
#             logger.info("GitLab not configured, running in demo mode")
        
#         if app_state.get('metadata_manager'):
#             cleaned = app_state['metadata_manager'].cleanup_stale_locks()
#             if cleaned > 0:
#                 logger.info(f"Cleaned up {cleaned} stale file locks")
        
#         logger.info("Application initialization completed")
        
#     except Exception as e:
#         logger.error(f"Failed to initialize application: {str(e)}")


# In mastercam_main.py, replace your `initialize_application` function with this one.
async def initialize_application():
    try:
        app_state['config_manager'] = ConfigManager()
        config = app_state['config_manager'].config
        
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
                    # FIX: Initialize the MetadataManager with the correct path
                    metadata_repo_path = Path(config.local.get('repo_path')) / '.locks'
                    app_state['metadata_manager'] = MetadataManager(metadata_repo_path)
                else:
                    logger.warning("Failed to synchronize repository")
            else:
                logger.warning("GitLab connection failed")
        else:
            logger.info("GitLab not configured, running in demo mode")
            # If not initialized, set up a dummy metadata manager
            app_state['metadata_manager'] = MetadataManager(Path(tempfile.gettempdir()) / 'mastercam_git_interface' / '.locks')
        
        # Cleanup stale locks
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

# API Endpoints
@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/files/new_upload")
async def new_upload(
    background_tasks: BackgroundTasks,
    user: str = Form(...),
    file: UploadFile = File(...)
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
            
        background_tasks.add_task(process_new_upload, filename, content, user)
        
        logger.info(f"New file '{filename}' upload initiated by '{user}'")
        return JSONResponse({"status": "success", "message": f"New file '{filename}' is being added"})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading new file '{filename}': {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to upload new file")

@app.get("/files", response_model=List[FileInfo])
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
                    history = app_state['git_repo'].get_file_history(file_data['path'], limit=5)
                    if history:
                        file_info.version_info = {
                            'latest_commit': history[0]['commit_hash'][:8],
                            'latest_author': history[0]['author_name'],
                            'commit_count': len(history)
                        }
                files.append(file_info)
        else:
            files = get_demo_files()
        logger.info(f"Retrieved {len(files)} files")
        return files
    except Exception as e:
        logger.error(f"Error fetching files: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch files")

@app.post("/files/{filename}/checkout")
async def checkout_file(filename: str, request: CheckoutRequest):
    try:
        git_repo = app_state.get('git_repo')
        metadata_manager = app_state.get('metadata_manager')

        if not git_repo or not metadata_manager:
            raise HTTPException(status_code=500, detail="Repository not properly initialized.")

        # 1. Pull latest changes to get the most recent lock status
        git_repo.repo.remotes.origin.pull()

        file_path = find_file_path(filename)
        if not file_path:
            raise HTTPException(status_code=404, detail="File not found")

        # 2. Check if file is already locked by someone else
        if metadata_manager.get_lock_info(file_path):
            lock_info = metadata_manager.get_lock_info(file_path)
            raise HTTPException(
                status_code=409,
                detail=f"File is already locked by {lock_info['user']}"
            )

        # 3. Create the lock file locally
        lock_file_path = metadata_manager.create_lock(file_path, request.user)
        if not lock_file_path:
            raise HTTPException(status_code=500, detail="Failed to create lock file.")

        # 4. Commit and push the new lock file to GitLab
        commit_message = f"LOCK: {filename} by {request.user}"
        author_email = f"{request.user}@example.com"
        success = git_repo.commit_and_push(
            file_paths=[str(lock_file_path)],
            message=commit_message,
            author_name=request.user,
            author_email=author_email
        )

        if not success:
            metadata_manager.release_lock(file_path) # Clean up local lock file on failure
            raise HTTPException(status_code=500, detail="Failed to push lock file to remote.")

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
async def checkin_file(filename: str, background_tasks: BackgroundTasks, user: str = Form(...), file: UploadFile = File(...)):
    try:
        git_repo = app_state.get('git_repo')
        metadata_manager = app_state.get('metadata_manager')

        if not git_repo or not metadata_manager:
            raise HTTPException(status_code=500, detail="Repository not properly initialized.")

        file_path_str = find_file_path(filename)
        if not file_path_str:
            raise HTTPException(status_code=404, detail="File not found")

        # 1. Verify the user holds the lock
        lock_info = metadata_manager.get_lock_info(file_path_str)
        if not lock_info or lock_info['user'] != user:
            raise HTTPException(status_code=403, detail="You do not have this file locked.")

        content = await file.read()
        # ... (add your file size validation here) ...

        # 2. Save the new file content locally
        full_file_path = git_repo.repo_path / file_path_str
        git_repo.save_file(file_path_str, content)
        
        # 3. Get the path to the lock file BEFORE deleting it
        lock_file_path = metadata_manager._get_lock_file_path(file_path_str)

        # 4. Release the lock (deletes the file locally)
        metadata_manager.release_lock(file_path_str, user)
        
        # 5. Commit and push BOTH the updated .mcam file and the deleted .lock file
        commit_message = f"UPDATE: {filename} and release lock by {user}"
        author_email = f"{user}@example.com"
        success = git_repo.commit_and_push(
            file_paths=[str(full_file_path), str(lock_file_path)], # Add both to the index
            message=commit_message,
            author_name=user,
            author_email=author_email
        )

        if not success:
            # This is tricky; ideally, you'd revert the local changes.
            # For simplicity, we'll just log an error.
            raise HTTPException(status_code=500, detail="Failed to push file changes to remote.")

        await manager.broadcast(f"FILE_STATUS_CHANGED:{filename}:unlocked:")
        return JSONResponse({"status": "success", "message": f"File '{filename}' checked in successfully"})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking in file '{filename}': {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to checkin file")
@app.post("/files/{filename}/override")
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

@app.get("/files/{filename}/download")
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

@app.get("/files/{filename}/history")
async def get_file_history(filename: str):
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

@app.get("/config")
async def get_config():
    try:
        if app_state['config_manager']:
            return app_state['config_manager'].get_config_summary()
        return {"error": "Configuration not available"}
    except Exception as e:
        logger.error(f"Error getting configuration: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get configuration")

@app.post("/config/gitlab")
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

@app.websocket("/ws")
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