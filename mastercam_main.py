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
import socket
import subprocess
from datetime import datetime, timezone

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Form, UploadFile, File, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.websockets import WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from cryptography.fernet import Fernet
import base64
import time


from pathlib import Path
import os
import sys
import subprocess
import logging

logger = logging.getLogger(__name__)


def get_bundled_git_lfs_path() -> Path | None:
    """
    Return path to bundled git-lfs.exe (stable alias).
    Works in both dev mode and frozen (PyInstaller) mode.
    """
    if getattr(sys, 'frozen', False):  # running as exe
        base_path = Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent))
        git_lfs_path = base_path / 'git-lfs.exe'
    else:  # dev mode
        script_dir = Path(__file__).parent
        git_lfs_path = script_dir / 'libs' / 'git-lfs.exe'

    return git_lfs_path if git_lfs_path.exists() else None


def setup_git_lfs_path() -> bool:
    """
    Ensure git-lfs is in PATH.
    Prefer bundled version, fall back to system.
    Logs the version used.
    """
    bundled_lfs = get_bundled_git_lfs_path()

    if bundled_lfs:
        lfs_dir = str(bundled_lfs.parent)
        current_path = os.environ.get('PATH', '')
        if lfs_dir not in current_path:
            os.environ['PATH'] = f"{lfs_dir}{os.pathsep}{current_path}"
            logger.info(f"Added bundled Git LFS to PATH: {bundled_lfs}")
        return log_lfs_version("bundled", bundled_lfs)

    # fallback: system
    return log_lfs_version("system", "git-lfs")


def log_lfs_version(source: str, exe_path) -> bool:
    """Run 'git-lfs version' and log which binary is in use."""
    try:
        result = subprocess.run(
            [exe_path, "version"], capture_output=True, text=True, check=True
        )
        logger.info(f"Using {source} Git LFS: {result.stdout.strip()}")
        return True
    except Exception as e:
        logger.warning(f"Git LFS ({source}) not available: {e}")
        return False


class FileLockManager:
    """A simple file-based lock for distributed processes with force-break capability."""

    def __init__(self, lock_file_path: Path):
        self.lock_file_path = lock_file_path
        self.lock_file = None
        # Don't create parent directories here - do it on demand

    def force_break_lock(self):
        """Force remove a lock file with retries to handle Windows file access issues."""
        max_retries = 3
        retry_delay = 1  # seconds
        for attempt in range(max_retries):
            try:
                if self.lock_file_path.exists():
                    # Ensure any open file handle is closed
                    if self.lock_file:
                        try:
                            self.lock_file.close()
                        except Exception:
                            pass
                        self.lock_file = None
                    self.lock_file_path.unlink()
                    logger.info(
                        f"Force-broke lock file at {self.lock_file_path}")
                    return True
                return True  # Lock file already gone
            except PermissionError as e:
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Retry {attempt + 1}/{max_retries} to break lock: {e}")
                    time.sleep(retry_delay)
                    continue
                logger.error(
                    f"Failed to force-break lock after {max_retries} attempts: {e}")
                return False
            except Exception as e:
                logger.error(f"Unexpected error breaking lock: {e}")
                return False

    def __enter__(self):
        # Create parent directory only when acquiring lock
        try:
            self.lock_file_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"Could not create lock directory: {e}")
            # Continue anyway - we'll try to work without locking
            return self

        # Acquire the lock
        timeout = 30  # Wait a maximum of 30 seconds
        start_time = time.time()
        while True:
            try:
                # 'x' mode means create exclusively - fails if file exists
                self.lock_file = open(self.lock_file_path, 'x')
                self.lock_file.write(
                    f"Locked by process {os.getpid()} at {datetime.now()}")
                logger.info("Acquired repository lock.")
                return self
            except FileExistsError:
                # Check if the lock is stale
                if self._is_stale_lock():
                    logger.warning("Detected stale lock, breaking it...")
                    self.force_break_lock()
                    continue

                if time.time() - start_time > timeout:
                    raise TimeoutError(
                        "Could not acquire repository lock in time.")
                time.sleep(0.2)  # Wait a bit before retrying
            except FileNotFoundError:
                # Lock directory doesn't exist yet (e.g., during initial clone)
                logger.info(
                    "Lock directory doesn't exist - proceeding without lock")
                return self

    def _is_stale_lock(self) -> bool:
        """Check if a lock file is stale (older than 5 minutes)"""
        try:
            if not self.lock_file_path.exists():
                return False

            # Check file age
            file_age = time.time() - self.lock_file_path.stat().st_mtime
            if file_age > 300:  # 5 minutes
                return True

            # Try to read PID and check if process exists
            try:
                content = self.lock_file_path.read_text()
                if "process" in content:
                    import re
                    match = re.search(r'process (\d+)', content)
                    if match:
                        pid = int(match.group(1))
                        # Check if process is still running
                        if not self._is_process_running(pid):
                            return True
            except:
                pass

            return False
        except Exception as e:
            logger.error(f"Error checking stale lock: {e}")
            return False

    def _is_process_running(self, pid: int) -> bool:
        """Check if a process with given PID is running"""
        try:
            if os.name == 'nt':  # Windows
                import ctypes
                kernel32 = ctypes.windll.kernel32
                PROCESS_QUERY_INFORMATION = 0x0400
                handle = kernel32.OpenProcess(
                    PROCESS_QUERY_INFORMATION, 0, pid)
                if handle:
                    kernel32.CloseHandle(handle)
                    return True
                return False
            else:  # Unix/Linux
                os.kill(pid, 0)
                return True
        except (OSError, AttributeError):
            return False

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Release the lock
        if self.lock_file:
            try:
                self.lock_file.close()
            except:
                pass

        try:
            if self.lock_file_path.exists():
                os.remove(self.lock_file_path)
                logger.info("Released repository lock.")
        except OSError as e:
            logger.error(f"Failed to remove lock file: {e}")


# --- Basic Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler('mastercam_git_interface.log'), logging.StreamHandler()])
logger = logging.getLogger(__name__)

ADMIN_USERS = ["admin", "g4m3rm1k3"]

# +++ NEW: FILE TYPE VALIDATION CONFIG +++
# Defines allowed file extensions and their "magic number" signatures.
# 'None' means we'll fall back to only checking the extension.
ALLOWED_FILE_TYPES = {
    ".mcam": {
        "signatures": [
            b'\x89HDF\r\n\x1a\n',  # Signature for the commercial version
            b'\x89HDF\x01\x02\x03\x04'  # Example signature for the HLE version
        ]
    },
    ".vnc": {"signatures": None},
    ".emcam": {"signatures": None},
}

# --- Pydantic Data Models ---


def validate_link_filename_format(filename: str) -> tuple[bool, str]:
    """
    Validates a link filename - no extension allowed, must be exactly 7digits_3letters_3numbers
    """
    # Check if it has a file extension (shouldn't for links)
    if '.' in filename:
        return False, "Link names cannot have file extensions."

    # Check length limit
    MAX_LENGTH = 13  # 7 digits + 1 underscore + 3 letters + 3 numbers = 14 max
    if len(filename) > MAX_LENGTH:
        return False, f"Link name cannot exceed {MAX_LENGTH} characters."

    # Stricter pattern for links: exactly 7 digits, underscore, exactly 3 letters, exactly 3 numbers
    pattern = re.compile(r"^\d{7}(_[A-Z]{3}\d{3})?$")
    if not pattern.match(filename):
        return False, "Link name must follow the format: 7digits_3LETTERS_3numbers (e.g., 1234567_ABC123)."

    return True, ""


def validate_filename_format(filename: str) -> tuple[bool, str]:
    """
    Validates a regular file filename format.
    """
    stem = Path(filename).stem

    # Check length limit
    MAX_LENGTH = 15
    if len(stem) > MAX_LENGTH:
        return False, f"Filename (before extension) cannot exceed {MAX_LENGTH} characters."

    # Updated pattern to be more flexible for regular files
    pattern = re.compile(r"^\d{7}(_[A-Z]{1,3}\d{1,3})?$")
    if not pattern.match(stem):
        return False, "Filename must follow the format: 7digits_1-3LETTERS_1-3numbers (e.g., 1234567_AB123)."

    return True, ""


class FileInfo(BaseModel):
    filename: str = Field(..., description="The name of the file")
    path: str = Field(...,
                      description="The relative path of the file in the repository")
    status: str = Field(
        ..., description="File status: 'locked', 'unlocked', or 'checked_out_by_user'")
    locked_by: Optional[str] = Field(
        None, description="Username of the user who has the file locked")
    locked_at: Optional[str] = Field(
        None, description="ISO timestamp when the file was locked")
    size: Optional[int] = Field(None, description="File size in bytes")
    modified_at: Optional[str] = Field(
        None, description="ISO timestamp of last modification")
    description: Optional[str] = Field(
        None, description="File description from metadata")
    revision: Optional[str] = Field(
        None, description="Current revision number (e.g., '1.5')")
    is_link: bool = Field(
        False, description="True if this is a linked/virtual file")
    master_file: Optional[str] = Field(
        None, description="The master file this link points to")


class CheckoutInfo(BaseModel):
    filename: str = Field(..., description="Name of the checked out file")
    path: str = Field(..., description="Repository path of the file")
    locked_by: str = Field(...,
                           description="User who has the file checked out")
    locked_at: str = Field(...,
                           description="ISO timestamp when checkout occurred")
    duration_seconds: float = Field(
        ..., description="How long the file has been checked out in seconds")


class DashboardStats(BaseModel):
    active_checkouts: List[CheckoutInfo] = Field(
        ..., description="List of currently checked out files")


class CheckoutRequest(BaseModel):
    user: str = Field(..., description="Username requesting the checkout")


class AdminOverrideRequest(BaseModel):
    admin_user: str = Field(...,
                            description="Admin username performing the override")


class AdminDeleteRequest(BaseModel):
    admin_user: str = Field(...,
                            description="Admin username performing the deletion")


class SendMessageRequest(BaseModel):
    recipient: str = Field(...,
                           description="Username of the message recipient")
    message: str = Field(..., description="Message content to send")
    sender: str = Field(..., description="Username of the message sender")


class AckMessageRequest(BaseModel):
    message_id: str = Field(...,
                            description="Unique identifier of the message to acknowledge")
    user: str = Field(..., description="Username acknowledging the message")


class ConfigUpdateRequest(BaseModel):
    base_url: str = Field(
        alias="gitlab_url", description="GitLab instance URL (e.g., https://gitlab.example.com)")
    project_id: str = Field(..., description="GitLab project ID")
    username: str = Field(..., description="GitLab username")
    token: str = Field(..., description="GitLab personal access token")
    allow_insecure_ssl: bool = Field(
        False, description="Whether to allow insecure SSL connections")


class AdminRevertRequest(BaseModel):
    admin_user: str = Field(...,
                            description="Admin username performing the revert")
    commit_hash: str = Field(..., description="Git commit hash to revert")


class ActivityItem(BaseModel):
    event_type: str = Field(
        ..., description="Type of activity: CHECK_IN, CHECK_OUT, CANCEL, OVERRIDE, NEW_FILE, NEW_LINK, DELETE_FILE, DELETE_LINK, REVERT, MESSAGE, REFRESH_LOCK")
    filename: str = Field(..., description="Name of the file involved")
    user: str = Field(..., description="Username who performed the action")
    timestamp: str = Field(..., description="ISO timestamp of the activity")
    commit_hash: str = Field(...,
                             description="Git commit hash associated with the activity")
    message: str = Field(...,
                         description="Commit message or activity description")
    revision: Optional[str] = Field(
        None, description="File revision if applicable")


class ActivityFeed(BaseModel):
    activities: List[ActivityItem] = Field(...,
                                           description="List of recent activities")


class AppConfig(BaseModel):
    version: str = "1.0.0"
    gitlab: dict = Field(default_factory=dict)
    local: dict = Field(default_factory=dict)
    ui: dict = Field(default_factory=dict)
    security: dict = Field(default_factory=lambda: {
        "allow_insecure_ssl": False
    })
    polling: dict = Field(default_factory=lambda: {
                          "enabled": True, "interval_seconds": 15, "check_on_activity": True})


class StandardResponse(BaseModel):
    status: str = Field(...,
                        description="Response status: 'success' or 'error'")
    message: Optional[str] = Field(None, description="Human-readable message")


class ConfigSummary(BaseModel):
    gitlab_url: Optional[str] = Field(
        None, description="Configured GitLab URL")
    project_id: Optional[str] = Field(
        None, description="Configured GitLab project ID")
    username: Optional[str] = Field(
        None, description="Configured GitLab username")
    has_token: bool = Field(...,
                            description="Whether a GitLab token is configured")
    repo_path: Optional[str] = Field(None, description="Local repository path")
    is_admin: bool = Field(...,
                           description="Whether the current user has admin privileges")


class UserList(BaseModel):
    users: List[str] = Field(...,
                             description="List of usernames from Git history")


class FileHistory(BaseModel):
    filename: str = Field(..., description="Name of the file")
    history: List[Dict[str, Any]
                  ] = Field(..., description="List of historical commits for this file")


class ConfigurationError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status_code=503, detail=detail)

# --- Core Application Classes & Functions ---


def get_git_repo():
    if not app_state.get('initialized'):
        raise ConfigurationError(
            "Application is not configured. Please set GitLab credentials.")
    return app_state.get('git_repo')


def get_metadata_manager():
    if not app_state.get('initialized'):
        raise ConfigurationError("Application is not configured.")
    return app_state.get('metadata_manager')


def is_safe_path(basedir, path, follow_symlinks=True):
    # Resolves symbolic links if allowed
    if follow_symlinks:
        matchpath = os.path.realpath(path)
    else:
        matchpath = os.path.abspath(path)
    return basedir == os.path.commonpath((basedir, matchpath))


async def is_valid_file_type(file: UploadFile) -> bool:
    """
    Validates a file based on its extension and magic number signature.
    """
    file_extension = Path(file.filename).suffix.lower()

    if file_extension not in ALLOWED_FILE_TYPES:
        return False

    config = ALLOWED_FILE_TYPES[file_extension]
    # Corrected key from "signature" to "signatures"
    signatures = config.get("signatures")

    # If no signatures are defined for this type, we trust the extension
    if not signatures:
        return True

    try:
        # Find the length of the longest signature to know how much to read
        max_len = max(len(s) for s in signatures)
        file_header = await file.read(max_len)

        # Check if the file header starts with ANY of the valid signatures
        for s in signatures:
            if file_header.startswith(s):
                return True

        # If no signature matched
        return False
    finally:
        # IMPORTANT: Reset the file pointer so it can be read again later
        await file.seek(0)


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
            # --- THIS IS THE CHANGE ---
            # We now determine the save location based on where the app is running.
            if getattr(sys, 'frozen', False):
                # For the bundled .exe, save config in the same directory as the executable.
                base_path = Path(sys.executable).parent
            else:
                # For development (.py script), save it next to the script file.
                base_path = Path(__file__).parent
            config_dir = base_path / 'app_data'  # We'll put it in a subfolder for neatness

        self.config_dir = config_dir
        self.config_file = self.config_dir / 'config.json'
        # Create the app_data folder if it doesn't exist
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
            logger.error(
                f"!!! CRITICAL: Failed to save config file at {self.config_file}: {e}")
            raise e

    def update_gitlab_config(self, **kwargs):
        try:
            current_data = json.loads(self.config_file.read_text(
            )) if self.config_file.exists() and self.config_file.read_text() else {}
        except json.JSONDecodeError:
            current_data = {}

        if 'gitlab' not in current_data or not isinstance(current_data.get('gitlab'), dict):
            current_data['gitlab'] = {}

        # If a token is part of the update but is empty/None, we should still allow it to be cleared.
        # The logic should handle storing an empty token if that's the intent.
        # However, if the key is just missing from kwargs, we don't want to disturb an existing token.
        if 'token' in kwargs and kwargs.get('token') is None:
            kwargs['token'] = ""  # Explicitly set to empty string if None

        current_data['gitlab'].update(kwargs)
        new_config_obj = AppConfig(**current_data)
        self.config = new_config_obj
        self.save_config()

    def get_config_summary(self) -> Dict[str, Any]:
        cfg = self.config.model_dump()
        gitlab_cfg = cfg.get('gitlab', {})
        local_cfg = cfg.get('local', {})
        # --- THIS IS THE FIX ---
        # Reads from the 'security' section of the config, not the global list
        security_cfg = cfg.get('security', {})

        return {
            'gitlab_url': gitlab_cfg.get('base_url'),
            'project_id': gitlab_cfg.get('project_id'),
            'username': gitlab_cfg.get('username'),
            'has_token': bool(gitlab_cfg.get('token')),
            'repo_path': local_cfg.get('repo_path'),
            'is_admin': gitlab_cfg.get('username') in ADMIN_USERS
        }


class GitLabAPI:
    def __init__(self, base_url: str, token: str, project_id: str):
        self.api_url = f"{base_url}/api/v4/projects/{project_id}"
        self.headers = {"Private-Token": token}

    def test_connection(self) -> bool:
        try:
            # ✅ FIX: This method now reads the config for itself.
            config_manager = app_state.get('config_manager')
            allow_insecure = config_manager.config.security.get(
                "allow_insecure_ssl", False)
            verify_ssl = not allow_insecure

            response = requests.get(
                self.api_url, headers=self.headers, timeout=10, verify=verify_ssl
            )
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"GitLab connection test failed: {e}")
            return False


class GitRepository:
    def __init__(self, repo_path: Path, remote_url: str, token: str):
        self.repo_path = repo_path
        self.lock_manager = FileLockManager(repo_path / ".git" / "repo.lock")
        self.remote_url_with_token = f"https://oauth2:{token}@{remote_url.split('://')[-1]}"

        config_manager = app_state.get('config_manager')
        allow_insecure = config_manager.config.security.get(
            "allow_insecure_ssl", False)
        self.git_env = {"GIT_SSL_NO_VERIFY": "true"} if allow_insecure else {}

        self.repo = self._init_repo()
        self._configure_lfs()

    def _init_repo(self):
        max_retries = 3
        retry_delay = 1
        for attempt in range(max_retries):
            try:
                with self.lock_manager:
                    if not self.repo_path.exists():
                        logger.info(f"Cloning repository to {self.repo_path}")
                        return git.Repo.clone_from(self.remote_url_with_token, self.repo_path, env=self.git_env)

                    repo = git.Repo(self.repo_path)
                    if not repo.remotes:
                        raise git.exc.InvalidGitRepositoryError
                    return repo
            except (git.exc.InvalidGitRepositoryError, git.exc.NoSuchPathError):
                logger.warning(
                    f"Invalid repo at {self.repo_path}, re-cloning (attempt {attempt + 1}/{max_retries}).")
                with self.lock_manager:
                    # Force break any stale lock before re-cloning
                    self.lock_manager.force_break_lock()
                    if self.repo_path.exists():
                        try:
                            import shutil
                            shutil.rmtree(self.repo_path)
                        except Exception as e:
                            if attempt < max_retries - 1:
                                logger.warning(
                                    f"Retry {attempt + 1}/{max_retries}: {e}")
                                time.sleep(retry_delay)
                                continue
                            raise Exception(
                                f"Failed to delete repository after {max_retries} attempts: {e}")
                    return git.Repo.clone_from(self.remote_url_with_token, self.repo_path, env=self.git_env)
            except Exception as e:
                logger.error(f"Failed to initialize repository: {e}")
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Retrying initialization ({attempt + 1}/{max_retries})")
                    time.sleep(retry_delay)
                    continue
                return None

    def _configure_lfs(self):
        """Configure Git LFS for the repository"""
        if not self.repo:
            return

        try:
            # Check if LFS is available
            try:
                result = subprocess.run(
                    ['git', 'lfs', 'version'],
                    capture_output=True,
                    check=True,
                    text=True,
                    timeout=5
                )
                logger.info(f"Git LFS detected: {result.stdout.strip()}")
            except Exception as e:
                logger.error(f"Git LFS not available: {e}")
                self._disable_lfs_hooks()
                return

            # Use a special environment that includes our PATH
            lfs_env = self.git_env.copy()
            # Skip downloading LFS files during setup
            lfs_env['GIT_LFS_SKIP_SMUDGE'] = '1'

            with self.lock_manager:
                with self.repo.git.custom_environment(**lfs_env):
                    # Initialize LFS with skip-smudge to avoid downloading all LFS files
                    try:
                        self.repo.git.lfs(
                            'install', '--local', '--skip-smudge')
                        logger.info("LFS initialized in repository")
                    except Exception as e:
                        logger.error(f"Could not initialize LFS: {e}")
                        return

                    # Track patterns
                    lfs_patterns = ['*.mcam', '*.mcam-*',
                                    '*.emcam', '*.emcam-*', '*.vnc']
                    gitattributes_path = self.repo_path / '.gitattributes'

                    existing_lines = []
                    if gitattributes_path.exists():
                        existing_lines = gitattributes_path.read_text().splitlines()

                    existing_patterns = {
                        line.split()[0]
                        for line in existing_lines
                        if 'filter=lfs' in line
                    }

                    new_patterns = []
                    for pattern in lfs_patterns:
                        if pattern not in existing_patterns:
                            lfs_line = f"{pattern} filter=lfs diff=lfs merge=lfs -text"
                            new_patterns.append(lfs_line)

                    if new_patterns:
                        with open(gitattributes_path, 'a') as f:
                            if existing_lines:
                                f.write('\n')
                            f.write('\n'.join(new_patterns) + '\n')

                        # Commit without triggering hooks initially
                        self.repo.index.add(['.gitattributes'])
                        if self.repo.index.diff("HEAD"):
                            # Use skip_hooks to avoid the chicken-and-egg problem
                            self.repo.index.commit(
                                "Configure Git LFS for Mastercam files",
                                skip_hooks=True
                            )
                            self.repo.remotes.origin.push()

                        logger.info(
                            f"Git LFS configured - tracking {len(new_patterns)} patterns")

        except Exception as e:
            logger.error(f"Failed to configure Git LFS: {e}", exc_info=True)

    def _disable_lfs_hooks(self):
        """Remove LFS hooks that would fail without LFS installed"""
        try:
            hooks_dir = self.repo_path / '.git' / 'hooks'
            if not hooks_dir.exists():
                return

            lfs_hooks = ['post-checkout',
                         'post-commit', 'post-merge', 'pre-push']

            for hook_name in lfs_hooks:
                hook_path = hooks_dir / hook_name
                if hook_path.exists():
                    content = hook_path.read_text()
                    if 'git-lfs' in content or 'git lfs' in content:
                        # Rename instead of delete so we can restore later
                        hook_path.rename(hook_path.with_suffix('.disabled'))
                        logger.info(f"Disabled LFS hook: {hook_name}")
        except Exception as e:
            logger.warning(f"Could not disable LFS hooks: {e}")

    def pull(self):
        """Pull with LFS support"""
        try:
            with self.lock_manager:
                if self.repo:
                    with self.repo.git.custom_environment(**self.git_env):
                        # Fetch with LFS
                        self.repo.remotes.origin.fetch()

                        # Pull LFS files
                        try:
                            self.repo.git.lfs('pull')
                        except Exception as lfs_error:
                            logger.warning(
                                f"LFS pull failed (may not be configured): {lfs_error}")

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
                                 "modified_at": datetime.fromtimestamp(stat_result.st_mtime, tz=timezone.utc).isoformat()})
                except OSError:
                    continue
        return files

    def save_file(self, file_path: str, content: bytes):
        (self.repo_path / file_path).parent.mkdir(parents=True, exist_ok=True)
        (self.repo_path / file_path).write_bytes(content)

    def commit_and_push(self, file_paths: List[str], message: str, author_name: str, author_email: str) -> bool:
        """Commit and push with LFS support"""
        with self.lock_manager:
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

                    # Push with LFS
                    self.repo.remotes.origin.push()

                    # Ensure LFS files are pushed
                    try:
                        self.repo.git.lfs('push', 'origin',
                                          self.repo.active_branch.name)
                    except Exception as lfs_error:
                        logger.warning(
                            f"LFS push completed with warning: {lfs_error}")

                logger.info("Changes pushed to GitLab with LFS support.")
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
                        "date": datetime.fromtimestamp(c.committed_date, tz=timezone.utc).isoformat(), "message": c.message.strip(),
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
            for lock_file in sorted(locks_dir.glob('*.lock')):
                if lock_file.is_file():
                    lock_files_data.append(
                        f"{lock_file.name}:{lock_file.read_text()}")
        except Exception as e:
            logger.error(f"Error reading lock files: {e}")
            return ""
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
        # Store user associated with each connection
        self.active_connections: Dict[WebSocket, str] = {}

    async def connect(self, websocket: WebSocket, user: str):
        await websocket.accept()
        self.active_connections[websocket] = user

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            del self.active_connections[websocket]

    async def broadcast(self, message: str):
        # Iterating over a copy of keys to allow for disconnections during broadcast
        for connection in list(self.active_connections.keys()):
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

tags_metadata = [
    {
        "name": "Configuration",
        "description": "System configuration and GitLab integration settings"
    },
    {
        "name": "File Management",
        "description": "Core file operations including upload, download, checkout, and check-in"
    },
    {
        "name": "Admin",
        "description": "Administrative operations requiring elevated privileges"
    },
    {
        "name": "Version Control",
        "description": "Git version control operations and file history"
    },
    {
        "name": "Dashboard",
        "description": "Dashboard data and statistics"
    },
    {
        "name": "Statistics",
        "description": "System statistics and metrics"
    },
    {
        "name": "Activity Tracking",
        "description": "Activity feeds and audit trails"
    },
    {
        "name": "User Management",
        "description": "User-related operations and information"
    },
    {
        "name": "Messaging",
        "description": "Inter-user messaging system"
    },
    {
        "name": "Repository Management",
        "description": "Git repository operations and synchronization"
    },
    {
        "name": "Web Interface",
        "description": "Web interface endpoints"
    }
]


app = FastAPI(
    title="Mastercam GitLab Interface",
    description="""
    A comprehensive file management system that integrates Mastercam files with GitLab version control.
    
    ## Features
    
    * **File Management**: Upload, download, and manage Mastercam (.mcam) files
    * **Version Control**: Full Git integration with GitLab for file versioning
    * **Lock System**: Prevent concurrent edits with file checkout/checkin workflow
    * **Real-time Updates**: WebSocket-based live updates across all connected clients
    * **Admin Controls**: Administrative override and file management capabilities
    * **Activity Tracking**: Complete audit trail of all file operations
    
    ## Authentication
    
    This system uses GitLab personal access tokens for authentication and authorization.
    Admin users have additional privileges for file management and system administration.
    
    ## File Naming Convention
    
    Files must follow the format: `7digits_1-3letters_1-3numbers.ext`
    - Example: `1234567_AB123.mcam`
    - Maximum 15 characters before extension
    - Supported extensions: `.mcam`, `.vnc`
    
    ## Workflow
    
    1. **Upload**: Add new files to the repository
    2. **Checkout**: Lock a file for exclusive editing
    3. **Edit**: Make changes locally in Mastercam
    4. **Check-in**: Upload modified file with automatic versioning
    5. **History**: Track all changes and versions
    
    ## Real-time Features
    
    The system provides real-time updates via WebSocket connections:
    - File lock status changes
    - New file additions
    - Check-in/checkout activities
    - Administrative messages
    """,
    version="1.0.0",
    contact={
        "name": "Mastercam PDM Support",
        "email": "michael.mclean@sigsauer.com",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
    openapi_tags=tags_metadata,
    lifespan=lifespan
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
    app_state['initialized'] = False

    # Set up Git LFS path first
    lfs_available = setup_git_lfs_path()
    if not lfs_available:
        logger.warning(
            "Git LFS is not available. Large file tracking will be disabled.")

    try:
        app_state['config_manager'] = ConfigManager()
        cfg = app_state['config_manager'].config
        gitlab_cfg = cfg.gitlab

        if all(gitlab_cfg.get(k) for k in ['base_url', 'token', 'project_id', 'username']):
            # --- NEW: STARTUP VALIDATION BLOCK ---
            try:
                logger.info("Validating stored credentials on startup...")
                base_url_parsed = '/'.join(
                    gitlab_cfg['base_url'].split('/')[:3])
                api_url = f"{base_url_parsed}/api/v4/user"
                headers = {"Private-Token": gitlab_cfg['token']}

                security_cfg = cfg.security
                verify_ssl = not security_cfg.get("allow_insecure_ssl", False)

                response = requests.get(
                    api_url, headers=headers, timeout=10, verify=verify_ssl)
                response.raise_for_status()

                gitlab_user_data = response.json()
                real_username = gitlab_user_data.get("username")

                # Compare the username from the config with the one from the GitLab API
                if real_username != gitlab_cfg['username']:
                    logger.warning(
                        f"SECURITY ALERT: Config username ('{gitlab_cfg['username']}') does not match token owner ('{real_username}'). Invalidating session.")
                    # Invalidate the config in memory by clearing it
                    app_state['config_manager'].config.gitlab = {}
                    # This will cause initialization to fail and fall into the except block below
                    raise ValueError(
                        "Username in config does not match token owner.")

                logger.info(
                    f"Startup validation successful for user '{real_username}'.")

            except Exception as e:
                logger.error(
                    f"Startup credential validation failed: {e}. Clearing credentials.")
                # If validation fails for any reason, clear the bad config from memory
                if 'config_manager' in app_state:
                    app_state['config_manager'].config.gitlab = {}
                raise  # Re-raise to fall into the main except block
            # --- END OF VALIDATION BLOCK ---

            # If validation passes, proceed with normal initialization
            app_state['gitlab_api'] = GitLabAPI(
                base_url_parsed, gitlab_cfg['token'], gitlab_cfg['project_id'])

            if app_state['gitlab_api'].test_connection():
                logger.info("GitLab connection established.")
                repo_path = Path(cfg.local.get(
                    'repo_path', Path.home() / 'MastercamGitRepo'))
                app_state['git_repo'] = GitRepository(
                    repo_path, gitlab_cfg['base_url'], gitlab_cfg['token'])

                if app_state['git_repo'].repo:
                    app_state['metadata_manager'] = MetadataManager(repo_path)
                    git_monitor = GitStateMonitor(app_state['git_repo'])
                    app_state['initialized'] = True
                    logger.info(
                        "Repository synchronized and application fully initialized.")
                    # Start the polling task only after successful initialization
                    if not any(isinstance(t, asyncio.Task) and t.get_name() == 'git_polling_task' for t in asyncio.all_tasks()):
                        task = asyncio.create_task(git_polling_task())
                        task.set_name('git_polling_task')

    except Exception as e:
        logger.error(
            f"Initialization failed or was aborted due to invalid config: {e}")

    if not app_state.get('initialized'):
        logger.warning(
            "Running in limited/unconfigured mode. Please check your settings.")
        # Ensure a dummy metadata manager exists for basic UI functionality
        if 'metadata_manager' not in app_state:
            app_state['metadata_manager'] = MetadataManager(
                Path(tempfile.gettempdir()) / 'mastercam_git_interface_temp')


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
                logger.info("Git changes detected, broadcasting updates...")
                await broadcast_updates()  # Use the new comprehensive broadcast function
            await asyncio.sleep(poll_interval)
        except asyncio.CancelledError:
            logger.info("Git polling task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in git polling task: {e}")
            await asyncio.sleep(poll_interval * 2)


def find_file_path(filename: str) -> Optional[str]:
    """
    Find the path for a file, checking both regular files and link files.
    For link files, this returns the virtual path (just the filename).
    """
    if git_repo := app_state.get('git_repo'):
        # First check for regular files using all allowed file types
        for ext in ALLOWED_FILE_TYPES.keys():
            pattern = f"*{ext}"
            for file_data in git_repo.list_files(pattern):
                if file_data['name'] == filename:
                    return file_data['path']

        # Then check for link files
        for file_data in git_repo.list_files("*.link"):
            link_name = file_data['name'].replace('.link', '')
            if link_name == filename:
                # Return the virtual filename for links (NOT the .link path)
                return filename

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

    # 1. Get all supported file types dynamically using ALLOWED_FILE_TYPES
    all_files_raw = []
    for ext in ALLOWED_FILE_TYPES.keys():
        pattern = f"*{ext}"
        all_files_raw.extend(git_repo.list_files(pattern))

    # Create map of all files (not just mcam files)
    master_files_map = {file_data['name']                        : file_data for file_data in all_files_raw}

    # This list will hold both real and virtual (linked) files
    all_files_to_process = list(master_files_map.values())

    # 2. Find and process all .link files to create virtual file entries
    link_files_raw = git_repo.list_files("*.link")
    for link_file_data in link_files_raw:
        try:
            link_content_str = git_repo.get_file_content(
                link_file_data['path'])
            if not link_content_str:
                continue

            link_content = json.loads(link_content_str)
            master_filename = link_content.get("master_file")

            if master_filename and master_filename in master_files_map:
                # DON'T copy from master - create a clean virtual file entry
                virtual_file_name = link_file_data['name'].replace('.link', '')

                # Create a minimal virtual file entry with its own properties
                virtual_file = {
                    'name': virtual_file_name,
                    'path': virtual_file_name,  # Virtual path
                    'size': 0,  # Links have no size
                    # Use link file's timestamp
                    'modified_at': link_file_data['modified_at'],
                    'is_link': True,
                    'master_file': master_filename
                }

                all_files_to_process.append(virtual_file)
        except Exception as e:
            logger.error(
                f"Could not process link file {link_file_data['name']}: {e}")

    # 3. Process the combined list of real and virtual files
    grouped_files = {}
    current_user = app_state.get(
        'config_manager').config.gitlab.get('username', 'demo_user')

    for file_data in all_files_to_process:
        # CRITICAL FIX: For linked files, use the LINK's metadata, not the master's
        if file_data.get('is_link'):
            # Use the link's own name for metadata lookup
            path_for_meta = file_data['name']  # Use link name, not master file
        else:
            # Regular files use their actual path
            path_for_meta = file_data['path']

        meta_path = git_repo.repo_path / f"{path_for_meta}.meta.json"
        description, revision = None, None
        if meta_path.exists():
            try:
                meta_content = json.loads(meta_path.read_text())
                description = meta_content.get('description')
                revision = meta_content.get('revision')
            except json.JSONDecodeError:
                logger.warning(f"Could not parse metadata for {path_for_meta}")

        file_data['description'], file_data['revision'] = description, revision

        # CRITICAL FIX: For lock info, also use the link's name for linked files
        lock_info = metadata_manager.get_lock_info(path_for_meta)
        status, locked_by, locked_at = "unlocked", None, None
        if lock_info:
            status, locked_by, locked_at = "locked", lock_info.get(
                'user'), lock_info.get('timestamp')
            if locked_by == current_user:
                status = "checked_out_by_user"

        file_data['filename'] = file_data.pop('name')
        file_data.update(
            {"status": status, "locked_by": locked_by, "locked_at": locked_at})

        # Grouping logic remains the same
        filename = file_data['filename'].strip()
        group_name = "Miscellaneous"
        if re.match(r"^\d{7}.*", filename):
            group_name = f"{filename[:2]}XXXXX"
        if group_name not in grouped_files:
            grouped_files[group_name] = []
        grouped_files[group_name].append(file_data)

    return grouped_files


def find_available_port(start_port=8000, max_attempts=100):
    """
    Finds an open network port by checking ports sequentially.
    """
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                # Try to bind to the port. If it succeeds, the port is free.
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                # This means the port is already in use.
                logger.warning(
                    f"Port {port} is already in use, trying next...")
    raise IOError("Could not find an available port.")


async def broadcast_updates():
    try:
        logger.info("Broadcasting all updates...")
        # Small delay to ensure FS changes are settled
        await asyncio.sleep(0.2)

        # Prepare file list payload once
        grouped_data = _get_current_file_state()
        file_list_message = json.dumps({
            "type": "FILE_LIST_UPDATED",
            "payload": grouped_data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        if not manager.active_connections:
            logger.debug("No active WebSocket connections to broadcast to.")
            return

        # Iterate through a copy of connections to handle disconnections safely
        for websocket, user in list(manager.active_connections.items()):
            # 1. Send file list update to everyone
            try:
                await websocket.send_text(file_list_message)
            except Exception as e:
                logger.warning(f"Could not send file list to {user}: {e}")
                manager.disconnect(websocket)
                continue

            # 2. Check for and send specific messages to each user
            if git_repo := app_state.get('git_repo'):
                user_message_file = git_repo.repo_path / \
                    ".messages" / f"{user}.json"
                if user_message_file.exists():
                    try:
                        messages = json.loads(user_message_file.read_text())
                        if messages:
                            message_payload = json.dumps(
                                {"type": "NEW_MESSAGES", "payload": messages})
                            await websocket.send_text(message_payload)
                    except Exception as e:
                        logger.error(
                            f"Could not check or send messages to {user}: {e}")

        logger.info(
            f"Broadcast complete to {len(manager.active_connections)} clients.")

    except Exception as e:
        logger.error(f"Failed to broadcast updates: {e}")


async def handle_successful_git_operation():
    global git_monitor
    if git_monitor:
        git_monitor.initialize_state()
    await broadcast_updates()  # Use the new comprehensive broadcast function

# --- API Endpoints ---


@app.get("/")
async def root(request: Request): return templates.TemplateResponse(
    "index.html", {"request": request})


@app.get("/config")
async def get_config():
    if config_manager := app_state.get('config_manager'):
        return config_manager.get_config_summary()
    raise HTTPException(
        status_code=503, detail="Application not fully initialized.")


@app.post("/config/gitlab")
async def update_gitlab_config(request: ConfigUpdateRequest):
    # You can keep the print statement here for testing or remove it.
    print(
        f"--- DATA RECEIVED FROM FRONTEND ---\n{request.model_dump_json(indent=2)}\n---------------------------------")

    config_manager = app_state.get('config_manager')
    if not config_manager:
        raise HTTPException(
            status_code=500, detail="Configuration manager not found.")

    try:
        # --- 1. VALIDATION ---
        base_url_parsed = '/'.join(request.base_url.split('/')[:3])
        api_url = f"{base_url_parsed}/api/v4/user"
        headers = {"Private-Token": request.token}
        verify_ssl = not request.allow_insecure_ssl
        response = requests.get(api_url, headers=headers,
                                timeout=10, verify=verify_ssl)
        response.raise_for_status()
        gitlab_user_data = response.json()
        gitlab_username = gitlab_user_data.get("username")

        if gitlab_username != request.username:
            raise HTTPException(
                status_code=400,
                detail=f"Validation Failed: Username '{request.username}' does not match the token owner ('{gitlab_username}')."
            )

        # --- 2. UPDATE CONFIG IN MEMORY ---
        # ✅ This is the corrected logic. It directly modifies the live config object
        # and does NOT call the problematic update_gitlab_config helper.

        config_manager.config.gitlab['base_url'] = request.base_url
        config_manager.config.gitlab['project_id'] = request.project_id
        config_manager.config.gitlab['username'] = request.username
        config_manager.config.gitlab['token'] = request.token
        config_manager.config.security['allow_insecure_ssl'] = request.allow_insecure_ssl

        # --- 3. SAVE ONCE ---
        config_manager.save_config()

        # --- 4. RE-INITIALIZE ---
        asyncio.create_task(initialize_application())
        return {"status": "success", "message": "Configuration validated and saved."}

    except HTTPException as e:
        raise e
    except requests.exceptions.RequestException as e:
        logger.error(f"GitLab API validation request failed: {e}")
        raise HTTPException(
            status_code=401,
            detail="Could not validate with GitLab. Check your GitLab URL, Token, and SSL setting."
        )
    except Exception as e:
        error_type = type(e).__name__
        logger.error(
            f"An unexpected {error_type} occurred during config update: {e}")
        raise HTTPException(
            status_code=500, detail=f"An internal error occurred: {error_type}")


@app.get("/refresh")
async def manual_refresh():
    try:
        if git_monitor and git_monitor.check_for_changes():
            await broadcast_updates()  # Use new broadcast function
            return {"status": "success", "message": "Files refreshed"}
        else:
            await broadcast_updates()  # Resync even if no changes
            return {"status": "success", "message": "No remote changes detected, UI resynced."}
    except Exception as e:
        logger.error(f"Manual refresh failed: {e}")
        raise HTTPException(status_code=500, detail="Refresh failed")


@app.get("/files", response_model=Dict[str, List[FileInfo]])
async def get_files():
    try:
        grouped_data = _get_current_file_state()
        return {group: [FileInfo(**file_data) for file_data in files] for group, files in grouped_data.items()}
    except Exception as e:
        logger.error(f"Error in get_files endpoint: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Failed to retrieve file list.")


@app.get("/users")
async def get_users():
    try:
        git_repo = app_state.get('git_repo')
        if not git_repo:
            raise HTTPException(
                status_code=500, detail="Repository not initialized.")
        users = git_repo.get_all_users_from_history()
        return {"users": users}
    except Exception as e:
        logger.error(
            f"An unexpected error occurred in get_users: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"An internal error occurred: {e}")


@app.post("/messages/send")
async def send_message(request: SendMessageRequest):
    try:
        cfg_manager = app_state.get('config_manager')
        git_repo = app_state.get('git_repo')
        if not all([cfg_manager, git_repo]):
            raise HTTPException(
                status_code=500, detail="Repository not initialized.")

        # Verify sender is admin
        if request.sender not in ADMIN_USERS:
            raise HTTPException(status_code=403, detail="Permission denied.")

        # Verify recipient exists
        all_users = git_repo.get_all_users_from_history()
        if request.recipient not in all_users:
            raise HTTPException(
                status_code=404, detail=f"User '{request.recipient}' not found.")

        messages_dir = git_repo.repo_path / ".messages"
        messages_dir.mkdir(exist_ok=True)
        user_message_file = messages_dir / f"{request.recipient}.json"

        messages = []
        if user_message_file.exists():
            try:
                messages = json.loads(user_message_file.read_text())
            except json.JSONDecodeError:
                logger.warning(
                    f"Corrupted message file for {request.recipient}, starting fresh")
                messages = []

        new_message = {
            "id": str(uuid.uuid4()),
            "sender": request.sender,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": request.message
        }
        messages.append(new_message)

        # Write locally first
        user_message_file.write_text(json.dumps(messages, indent=2))

        # Attempt to commit and push
        commit_message = f"MSG: Send message to {request.recipient} by {request.sender}"
        relative_path = str(user_message_file.relative_to(git_repo.repo_path))

        success = git_repo.commit_and_push(
            [relative_path],
            commit_message,
            request.sender,
            f"{request.sender}@example.com"
        )

        if success:
            await handle_successful_git_operation()
            return JSONResponse({
                "status": "success",
                "message": "Message sent and synced to repository.",
                "message_id": new_message["id"]
            })
        else:
            # Rollback on failure
            if len(messages) > 1:
                messages.pop()
                user_message_file.write_text(json.dumps(messages, indent=2))
            else:
                user_message_file.unlink(missing_ok=True)
            raise HTTPException(
                status_code=500, detail="Failed to sync message to repository.")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in send_message: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"An internal error occurred: {e}")


@app.get("/dashboard/stats", response_model=DashboardStats)
async def get_dashboard_stats():
    """
    Scans the .locks directory to find all currently checked-out files
    and calculates how long they have been locked.
    """
    metadata_manager = app_state.get('metadata_manager')
    if not metadata_manager:
        raise HTTPException(
            status_code=503, detail="Metadata manager is not available."
        )

    active_checkouts = []
    now_utc = datetime.now(timezone.utc)
    locks_dir = metadata_manager.locks_dir

    if locks_dir.exists():
        for lock_file in locks_dir.glob('*.lock'):
            try:
                lock_data = json.loads(lock_file.read_text())
                file_path = lock_data.get("file")
                user = lock_data.get("user")
                timestamp_str = lock_data.get("timestamp")

                if not all([file_path, user, timestamp_str]):
                    logger.warning(
                        f"Skipping malformed lock file: {lock_file.name}")
                    continue

                # Parse the UTC timestamp string from the lock file
                locked_at_dt = datetime.fromisoformat(
                    timestamp_str.replace('Z', '+00:00'))

                # Calculate the duration
                duration = now_utc - locked_at_dt

                active_checkouts.append(CheckoutInfo(
                    filename=Path(file_path).name,
                    path=file_path,
                    locked_by=user,
                    locked_at=timestamp_str,
                    duration_seconds=duration.total_seconds()
                ))
            except (json.JSONDecodeError, TypeError, KeyError) as e:
                logger.warning(
                    f"Could not process lock file {lock_file.name}: {e}")

    # Sort the list by the longest checkout duration first
    active_checkouts.sort(key=lambda x: x.duration_seconds, reverse=True)

    return DashboardStats(active_checkouts=active_checkouts)


@app.post("/messages/acknowledge")
async def acknowledge_message(request: AckMessageRequest):
    try:
        git_repo = app_state.get('git_repo')
        if not git_repo:
            raise HTTPException(
                status_code=500, detail="Repository not initialized.")
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
                status_code=500, detail="Failed to acknowledge message.")
    except Exception as e:
        logger.error(
            f"An unexpected error occurred in acknowledge_message: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"An internal error occurred: {e}")


@app.post("/files/new_upload")
async def new_upload(
    user: str = Form(...),
    description: str = Form(...),
    rev: str = Form(...),
    # Changed to str to handle form data
    is_link_creation: str = Form("false"),
    new_link_filename: Optional[str] = Form(None),
    link_to_master: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None)
):
    """
    Handle both file uploads and link creation through a single endpoint.
    """
    git_repo = app_state.get('git_repo')
    if not git_repo or not app_state.get('initialized'):
        raise HTTPException(
            status_code=500, detail="Repository not available.")

    # Convert string to boolean
    is_link = is_link_creation.lower() in ('true', '1', 'yes')

    if is_link:
        # --- LINK CREATION LOGIC ---
        logger.info(f"Creating link: {new_link_filename} -> {link_to_master}")

        if not new_link_filename or not link_to_master:
            raise HTTPException(
                status_code=400,
                detail="Must provide both a link name and a master file to link to."
            )

        # Validate the new link filename format
        is_valid_format, error_message = validate_link_filename_format(
            new_link_filename)
        if not is_valid_format:
            raise HTTPException(status_code=400, detail=error_message)

        # Check if file or link already exists
        if find_file_path(new_link_filename) or find_file_path(f"{new_link_filename}.link"):
            raise HTTPException(
                status_code=409,
                detail=f"File or link '{new_link_filename}' already exists."
            )

        # Verify the master file exists
        master_file_path = find_file_path(link_to_master)
        if not master_file_path:
            raise HTTPException(
                status_code=404,
                detail=f"Master file '{link_to_master}' not found."
            )

        try:
            # Create the .link file
            link_data = {"master_file": link_to_master}
            link_filepath_str = f"{new_link_filename}.link"
            link_full_path = git_repo.repo_path / link_filepath_str
            link_full_path.write_text(json.dumps(link_data, indent=2))

            # Create the metadata file for the link
            meta_filename_str = f"{new_link_filename}.meta.json"
            meta_content = {
                "description": description.upper(),
                "revision": rev,
                "created_by": user,
                "created_at": datetime.utcnow().isoformat() + "Z"
            }
            meta_full_path = git_repo.repo_path / meta_filename_str
            meta_full_path.write_text(json.dumps(meta_content, indent=2))

            # Commit both files
            commit_message = f"LINK: Create '{new_link_filename}' -> '{link_to_master}' by {user}"
            files_to_commit = [link_filepath_str, meta_filename_str]

            success = git_repo.commit_and_push(
                files_to_commit, commit_message, user, f"{user}@example.com"
            )

            if success:
                await handle_successful_git_operation()
                return JSONResponse({
                    "status": "success",
                    "message": f"Link '{new_link_filename}' created successfully, pointing to '{link_to_master}'."
                })
            else:
                raise HTTPException(
                    status_code=500, detail="Failed to commit new link to repository."
                )

        except Exception as e:
            logger.error(f"Error creating link: {e}", exc_info=True)
            # Clean up on error
            (git_repo.repo_path / link_filepath_str).unlink(missing_ok=True)
            (git_repo.repo_path / meta_filename_str).unlink(missing_ok=True)
            raise HTTPException(
                status_code=500, detail=f"Failed to create link: {str(e)}"
            )

    else:
        # --- FILE UPLOAD LOGIC ---
        logger.info(f"Uploading new file: {file.filename if file else 'None'}")

        if not file or not file.filename:
            raise HTTPException(
                status_code=400, detail="A file upload is required for file creation."
            )

        # Validate file format
        is_valid_format, error_message = validate_filename_format(
            file.filename)
        if not is_valid_format:
            raise HTTPException(status_code=400, detail=error_message)

        # Check if file already exists
        if find_file_path(file.filename):
            raise HTTPException(
                status_code=409, detail=f"File '{file.filename}' already exists."
            )

        # Validate file type
        if not await is_valid_file_type(file):
            file_ext = Path(file.filename).suffix.lower()
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. The uploaded file is not a valid {file_ext} file."
            )

        try:
            # Save the file content
            content = await file.read()
            git_repo.save_file(file.filename, content)

            # Create metadata file
            meta_filename = f"{file.filename}.meta.json"
            meta_content = {
                "description": description.upper(),
                "revision": rev,
                "uploaded_by": user,
                "uploaded_at": datetime.utcnow().isoformat() + "Z"
            }
            meta_path = git_repo.repo_path / meta_filename
            meta_path.write_text(json.dumps(meta_content, indent=2))

            # Commit both files
            commit_message = f"NEW: Upload {file.filename} rev {rev} by {user}"
            files_to_commit = [file.filename, meta_filename]

            success = git_repo.commit_and_push(
                files_to_commit, commit_message, user, f"{user}@example.com"
            )

            if success:
                await handle_successful_git_operation()
                return JSONResponse({
                    "status": "success",
                    "message": f"File '{file.filename}' uploaded successfully with revision {rev}."
                })
            else:
                # Clean up on failure
                (git_repo.repo_path / file.filename).unlink(missing_ok=True)
                meta_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=500, detail="Failed to commit new file to repository."
                )

        except Exception as e:
            logger.error(f"Error uploading file: {e}", exc_info=True)
            # Clean up on error
            (git_repo.repo_path / file.filename).unlink(missing_ok=True)
            (git_repo.repo_path /
             f"{file.filename}.meta.json").unlink(missing_ok=True)
            raise HTTPException(
                status_code=500, detail=f"Failed to upload file: {str(e)}"
            )


@app.post("/files/{filename}/checkout")
async def checkout_file(filename: str, request: CheckoutRequest):
    try:
        git_repo, metadata_manager = app_state.get(
            'git_repo'), app_state.get('metadata_manager')
        if not git_repo or not metadata_manager:
            raise HTTPException(
                status_code=500, detail="Repository not initialized.")

        git_repo.pull()

        # 🔒 Prevent checkout of link files
        link_file_path = f"{filename}.link"
        is_link = (git_repo.repo_path / link_file_path).exists()
        if is_link:
            raise HTTPException(
                status_code=400,
                detail="Cannot checkout link files. Use 'View Master' to access the source file."
            )

        file_path = find_file_path(filename)
        if not file_path:
            raise HTTPException(status_code=404, detail="File not found")

        # 🔑 Check existing lock
        existing_lock = metadata_manager.get_lock_info(file_path)
        if existing_lock:
            if existing_lock.get('user') == request.user:
                # Refresh existing lock
                refreshed = metadata_manager.refresh_lock(
                    file_path, request.user)
                if not refreshed:
                    raise HTTPException(
                        status_code=500, detail="Failed to refresh existing lock.")

                relative_lock_path_str = str(refreshed.relative_to(
                    git_repo.repo_path)).replace(os.sep, '/')
                commit_message = f"REFRESH LOCK: {filename} by {request.user}"

                success = git_repo.commit_and_push(
                    [relative_lock_path_str], commit_message, request.user, f"{request.user}@example.com"
                )
                if success:
                    await handle_successful_git_operation()
                    return JSONResponse({"status": "success", "message": "Lock refreshed."})
                else:
                    raise HTTPException(
                        status_code=500, detail="Failed to push refreshed lock.")
            else:
                raise HTTPException(
                    status_code=409, detail="File is already locked by another user.")

        # 🆕 Create new lock
        lock_file_path = metadata_manager.create_lock(file_path, request.user)
        if not lock_file_path:
            raise HTTPException(
                status_code=500, detail="Failed to create lock file.")

        relative_lock_path_str = str(lock_file_path.relative_to(
            git_repo.repo_path)).replace(os.sep, '/')
        commit_message = f"LOCK: {filename} by {request.user}"

        success = git_repo.commit_and_push(
            [relative_lock_path_str], commit_message, request.user, f"{request.user}@example.com"
        )
        if success:
            await handle_successful_git_operation()
            return JSONResponse({"status": "success"})

        # Roll back lock if push fails
        metadata_manager.release_lock(file_path)
        raise HTTPException(
            status_code=500, detail="Failed to push lock file.")

    except Exception as e:
        logger.error(
            f"An unexpected error occurred in checkout_file: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"An internal error occurred: {e}")


@app.post("/files/{filename}/checkin")
async def checkin_file(filename: str, user: str = Form(...), commit_message: str = Form(...), rev_type: str = Form(...), new_major_rev: Optional[str] = Form(None), file: UploadFile = File(...)):
    # Check if this is a link file first
    git_repo = app_state.get('git_repo')
    if git_repo:
        link_file_path = f"{filename}.link"
        is_link = (git_repo.repo_path / link_file_path).exists()

        if is_link:
            raise HTTPException(
                status_code=400, detail="Cannot check in link files. Links are virtual placeholders.")

    if not await is_valid_file_type(file):
        raise HTTPException(
            status_code=400, detail=f"Invalid file type. The uploaded file is not a valid {Path(filename).suffix} file.")

    try:
        git_repo, metadata_manager = app_state.get(
            'git_repo'), app_state.get('metadata_manager')
        if not git_repo or not metadata_manager:
            raise HTTPException(
                status_code=500, detail="Repository not initialized.")
        file_path = find_file_path(filename)
        if not file_path:
            raise HTTPException(status_code=404, detail="File not found")
        lock_info = metadata_manager.get_lock_info(file_path)
        if not lock_info or lock_info['user'] != user:
            raise HTTPException(
                status_code=403, detail="You do not have this file locked.")
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
                status_code=500, detail="Failed to push changes.")
    except Exception as e:
        logger.error(
            f"An unexpected error occurred in checkin_file: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"An internal error occurred: {e}")


@app.post(
    "/files/{filename}/override",
    summary="Admin Override File Lock",
    description="""
    **Admin Only:** Forcibly removes a file lock regardless of who owns it.
    
    **Use Cases:**
    - User is offline and others need access to the file
    - System maintenance or emergency access required
    - Resolving stuck locks from system errors
    
    **Audit Trail:**
    - All overrides are logged in Git commit history
    - Includes admin username and timestamp
    - Provides full accountability for administrative actions
    
    **Safety Features:**
    - Requires admin privileges (verified against admin user list)
    - Creates permanent record in repository history
    - Notifies all connected users of the override
    """,
    response_model=StandardResponse,
    responses={
        200: {"description": "Lock overridden successfully"},
        403: {"description": "Permission denied - admin access required"},
        404: {"description": "File not found"},
        500: {"description": "Override failed"}
    },
    tags=["Admin", "File Management"]
)
async def admin_override(filename: str, request: AdminOverrideRequest):
    try:
        cfg_manager = app_state.get('config_manager')
        git_repo, metadata_manager = app_state.get(
            'git_repo'), app_state.get('metadata_manager')
        if not all([cfg_manager, git_repo, metadata_manager]):
            raise HTTPException(
                status_code=500, detail="Repository not initialized.")
        admin_users = ADMIN_USERS
        if request.admin_user not in ADMIN_USERS:
            raise HTTPException(
                status_code=403, detail="Permission denied. Admin access required.")
        file_path = find_file_path(filename)
        if not file_path:
            raise HTTPException(status_code=404, detail="File not found")
        absolute_lock_path = metadata_manager._get_lock_file_path(file_path)
        if not absolute_lock_path.exists():
            return JSONResponse({"status": "success", "message": "File was already unlocked."})
        relative_lock_path_str = str(absolute_lock_path.relative_to(
            git_repo.repo_path)).replace(os.sep, '/')
        metadata_manager.release_lock(file_path)
        commit_message = f"ADMIN OVERRIDE: Unlock {filename} by {request.admin_user}"
        success = git_repo.commit_and_push(
            [relative_lock_path_str], commit_message, request.admin_user, f"{request.admin_user}@example.com")
        if success:
            await handle_successful_git_operation()
            return JSONResponse({"status": "success"})
        else:
            lock_info = {"user": "unknown",
                         "timestamp": datetime.now(timezone.utc).isoformat()}
            absolute_lock_path.write_text(json.dumps(
                {"file": file_path, **lock_info}, indent=2))
            raise HTTPException(
                status_code=500, detail="Failed to commit lock override.")
    except Exception as e:
        logger.error(
            f"An unexpected error occurred in admin_override: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"An internal error occurred: {e}")


@app.post("/files/{filename}/cancel_checkout")
async def cancel_checkout(filename: str, request: CheckoutRequest):
    try:
        git_repo, metadata_manager = app_state.get(
            'git_repo'), app_state.get('metadata_manager')
        if not git_repo or not metadata_manager:
            raise HTTPException(
                status_code=500, detail="Repository not initialized.")
        file_path = find_file_path(filename)
        if not file_path:
            raise HTTPException(status_code=404, detail="File not found")
        lock_info = metadata_manager.get_lock_info(file_path)
        if not lock_info or lock_info['user'] != request.user:
            raise HTTPException(
                status_code=403, detail="You do not have this file checked out.")
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
                status_code=500, detail="Failed to commit checkout cancel.")
    except Exception as e:
        logger.error(
            f"An unexpected error occurred in cancel_checkout: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"An internal error occurred: {e}")


@app.delete(
    "/files/{filename}/delete",
    summary="Admin Delete File",
    description="""
    **Admin Only:** Permanently deletes a file from the repository.
    
    **⚠️ WARNING:** This action is irreversible through the normal interface.
    Files can only be recovered through Git history operations.
    
    **Safety Checks:**
    - Requires admin privileges
    - Prevents deletion of files currently checked out
    - Creates audit trail in Git history
    
    **What Gets Deleted:**
    - The main file (e.g., `example.mcam`)
    - Associated metadata file (e.g., `example.mcam.meta.json`)
    - Any existing lock files
    
    **Process:**
    1. Verifies admin privileges
    2. Checks file exists and is not locked
    3. Removes all associated files
    4. Commits deletion to Git with clear audit message
    5. Notifies all connected clients
    """,
    response_model=StandardResponse,
    responses={
        200: {"description": "File deleted successfully"},
        403: {"description": "Permission denied - admin access required"},
        404: {"description": "File not found"},
        409: {"description": "File is currently checked out"},
        500: {"description": "Deletion failed"}
    },
    tags=["Admin", "File Management"]
)
async def admin_delete_file(filename: str, request: AdminDeleteRequest):
    try:
        cfg_manager, git_repo, metadata_manager = app_state.get(
            'config_manager'), app_state.get('git_repo'), app_state.get('metadata_manager')
        if not all([cfg_manager, git_repo, metadata_manager]):
            raise HTTPException(
                status_code=500, detail="Repository not initialized.")

        admin_users = ADMIN_USERS
        if request.admin_user not in ADMIN_USERS:
            raise HTTPException(
                status_code=403, detail="Permission denied. Admin access required.")

        # Check if this is a link file first
        link_file_path = f"{filename}.link"
        is_link_file = (git_repo.repo_path / link_file_path).exists()

        if is_link_file:
            # LINK DELETION LOGIC
            logger.info(
                f"Admin {request.admin_user} deleting link: {filename}")

            # Links cannot be "locked" since they're virtual, so no lock check needed
            absolute_link_path = git_repo.repo_path / link_file_path
            meta_path = git_repo.repo_path / f"{filename}.meta.json"

            files_to_commit = [link_file_path]

            # Remove the .link file
            if absolute_link_path.exists():
                absolute_link_path.unlink()
            else:
                raise HTTPException(
                    status_code=404, detail=f"Link file {filename} not found.")

            # Remove associated metadata if it exists
            if meta_path.exists():
                files_to_commit.append(f"{filename}.meta.json")
                meta_path.unlink()

            # Commit the removal
            commit_message = f"ADMIN DELETE LINK: Remove link {filename} by {request.admin_user}"
            success = git_repo.commit_and_push(
                files_to_commit, commit_message, request.admin_user, f"{request.admin_user}@example.com"
            )

            if success:
                await handle_successful_git_operation()
                return JSONResponse({
                    "status": "success",
                    "message": f"Link '{filename}' removed successfully. Master file remains unaffected."
                })
            else:
                # Attempt to recover the files if push failed
                if not absolute_link_path.exists():
                    absolute_link_path.write_text(
                        '{"master_file": "unknown"}')  # Placeholder
                git_repo.pull()  # Sync with remote to recover
                raise HTTPException(
                    status_code=500, detail="Failed to commit link removal.")

        else:
            # REGULAR FILE DELETION LOGIC (existing code)
            file_path_str = find_file_path(filename)
            if not file_path_str:
                raise HTTPException(status_code=404, detail="File not found")

            # Safety check for locked files
            lock_info = metadata_manager.get_lock_info(file_path_str)
            if lock_info:
                raise HTTPException(
                    status_code=409,
                    detail=f"Cannot delete file. It is currently checked out by '{lock_info.get('user', 'unknown')}'."
                )

            logger.info(
                f"Admin {request.admin_user} deleting file: {filename}")

            absolute_file_path = git_repo.repo_path / file_path_str
            absolute_lock_path = metadata_manager._get_lock_file_path(
                file_path_str)
            relative_lock_path_str = str(absolute_lock_path.relative_to(
                git_repo.repo_path)).replace(os.sep, '/')

            files_to_commit = [file_path_str]

            # Include lock file if it exists
            if absolute_lock_path.exists():
                files_to_commit.append(relative_lock_path_str)

            # Include metadata file if it exists
            meta_path = git_repo.repo_path / f"{file_path_str}.meta.json"
            if meta_path.exists():
                files_to_commit.append(
                    str(meta_path.relative_to(git_repo.repo_path)))
                meta_path.unlink()

            # Remove the actual file and clean up
            absolute_file_path.unlink(missing_ok=True)
            metadata_manager.release_lock(file_path_str)  # Clean up any lock

            commit_message = f"ADMIN DELETE FILE: {filename} by {request.admin_user}"
            success = git_repo.commit_and_push(
                files_to_commit, commit_message, request.admin_user, f"{request.admin_user}@example.com"
            )

            if success:
                await handle_successful_git_operation()
                return JSONResponse({
                    "status": "success",
                    "message": f"File '{filename}' permanently deleted from repository."
                })
            else:
                git_repo.pull()  # Attempt to recover by syncing with remote
                raise HTTPException(
                    status_code=500, detail="Failed to commit file deletion.")

    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(
            f"Unexpected error in admin_delete_file: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"An internal error occurred: {e}")


@app.get(
    "/files/{filename}/download",
    summary="Download File",
    description="""
    Downloads the current version of a file from the repository.
    
    **Features:**
    - Serves the latest committed version
    - Sets appropriate headers for file download
    - Works with any file type in the repository
    
    **Use Cases:**
    - Download files for local editing in Mastercam
    - Create local backups
    - Share files with external collaborators
    
    The response includes proper Content-Disposition headers to trigger
    a download in web browsers.
    """,
    response_class=Response,
    responses={
        200: {"description": "File downloaded successfully", "content": {"application/octet-stream": {}}},
        404: {"description": "File not found"}
    },
    tags=["File Management"]
)
async def download_file(filename: str):
    git_repo, file_path = app_state.get('git_repo'), find_file_path(filename)
    if not git_repo or not file_path:
        raise HTTPException(status_code=404)
    content = git_repo.get_file_content(file_path)
    if content is None:
        raise HTTPException(status_code=404)
    return Response(content, media_type='application/octet-stream', headers={'Content-Disposition': f'attachment; filename="{filename}"'})


@app.get(
    "/files/{filename}/history",
    summary="Get File History",
    description="""
    Retrieves the complete Git history for a specific file.
    
    **Information Included:**
    - Git commit hash for each version
    - Author name and email
    - Commit timestamp
    - Commit message
    - File revision number (from metadata)
    
    **Limitations:**
    - Limited to last 10 commits for performance
    - Only shows commits that affected the specified file
    - Includes both file content changes and metadata updates
    
    **Use Cases:**
    - Track who made changes and when
    - Understand the evolution of a file
    - Identify specific versions for rollback
    - Audit trail for compliance
    """,
    response_model=FileHistory,
    responses={
        200: {"description": "File history retrieved successfully"},
        404: {"description": "File not found"}
    },
    tags=["File Management", "Version Control"]
)
async def get_file_history(filename: str):
    try:
        git_repo = app_state.get('git_repo')
        if not git_repo:
            raise HTTPException(
                status_code=500, detail="Repository not initialized.")

        # Check if this is a link file
        link_file_path = f"{filename}.link"
        is_link = (git_repo.repo_path / link_file_path).exists()

        if is_link:
            # For link files, show the history of the LINK's metadata only
            # We don't want the .link file history since it rarely changes
            meta_history = git_repo.get_file_history(
                f"{filename}.meta.json", limit=10)
            return {"filename": f"{filename} (Link)", "history": meta_history}
        else:
            # Regular file logic
            file_path = find_file_path(filename)
            if not file_path:
                raise HTTPException(status_code=404, detail="File not found")
            return {"filename": filename, "history": git_repo.get_file_history(file_path)}

    except Exception as e:
        logger.error(f"Error in get_file_history: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"An internal error occurred: {e}")


@app.get(
    "/files/{filename}/versions/{commit_hash}",
    summary="Download Specific File Version",
    description="""
    Downloads a specific historical version of a file by Git commit hash.
    
    **Version Identification:**
    - Use the commit hash from the file history endpoint
    - Both full and abbreviated commit hashes are accepted
    - File must have existed at the specified commit
    
    **Download Naming:**
    - Files are renamed to include version information
    - Format: `originalname_rev_1234567.ext`
    - This prevents confusion with current versions
    
    **Use Cases:**
    - Compare different versions
    - Recover from unwanted changes
    - Access specific revision for reference
    - Emergency rollback scenarios
    """,
    response_class=Response,
    responses={
        200: {"description": "File version downloaded successfully", "content": {"application/octet-stream": {}}},
        404: {"description": "File or version not found"}
    },
    tags=["File Management", "Version Control"]
)
async def download_file_version(filename: str, commit_hash: str):
    try:
        git_repo = app_state.get('git_repo')
        if not git_repo:
            raise HTTPException(
                status_code=500, detail="Repository not initialized.")
        file_path = find_file_path(filename)
        if not file_path:
            raise HTTPException(
                status_code=404, detail="File not found in current version.")
        content = git_repo.get_file_content_at_commit(file_path, commit_hash)
        if content is None:
            raise HTTPException(
                status_code=404, detail=f"File '{filename}' not found in commit '{commit_hash[:7]}'.")
        base, ext = os.path.splitext(filename)
        download_filename = f"{base}_rev_{commit_hash[:7]}{ext}"
        return Response(content, media_type='application/octet-stream', headers={'Content-Disposition': f'attachment; filename="{download_filename}"'})
    except Exception as e:
        logger.error(
            f"An unexpected error occurred in download_file_version: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"An internal error occurred: {e}")


@app.websocket(
    "/ws",
    name="WebSocket Connection"
)
async def websocket_endpoint(websocket: WebSocket, user: str = "anonymous"):
    """
    **Real-time WebSocket connection for live updates.**

    **Capabilities:**
    - Real-time file list updates
    - Instant lock status changes
    - Message notifications
    - System-wide activity broadcasts

    **Message Types Sent:**
    - `FILE_LIST_UPDATED`: Complete file list with current status
    - `NEW_MESSAGES`: Messages for the connected user

    **Message Types Received:**
    - `SET_USER:username`: Changes the user context for this connection
    - `REFRESH_FILES`: Requests immediate file list update

    **Connection Management:**
    - Automatic reconnection handling
    - User context switching
    - Graceful disconnection cleanup
    """

    await manager.connect(websocket, user)
    logger.info(f"WebSocket connected for user: {user}")

    if (git_repo := app_state.get('git_repo')):
        user_message_file = git_repo.repo_path / ".messages" / f"{user}.json"
        if user_message_file.exists():
            try:
                messages = json.loads(user_message_file.read_text())
                if messages:
                    await websocket.send_text(json.dumps({"type": "NEW_MESSAGES", "payload": messages}))
            except Exception as e:
                logger.error(f"Could not send messages to {user}: {e}")
    try:
        grouped_data = _get_current_file_state()
        await websocket.send_text(json.dumps({"type": "FILE_LIST_UPDATED", "payload": grouped_data}))

        while True:
            data = await websocket.receive_text()
            if data.startswith("SET_USER:"):
                new_user = data.split(":", 1)[1]
                app_state['current_user'] = new_user
                manager.active_connections[websocket] = new_user
                logger.info(f"User for WebSocket changed to: {new_user}")

                # --- THIS IS THE FIX ---
                # Added a check here to ensure git_repo exists before using it
                if (git_repo := app_state.get('git_repo')):
                    user_message_file = git_repo.repo_path / \
                        ".messages" / f"{new_user}.json"
                    if user_message_file.exists():
                        messages = json.loads(user_message_file.read_text())
                        if messages:
                            await websocket.send_text(json.dumps({"type": "NEW_MESSAGES", "payload": messages}))

                grouped_data = _get_current_file_state()
                await websocket.send_text(json.dumps({"type": "FILE_LIST_UPDATED", "payload": grouped_data}))

            elif data == "REFRESH_FILES":
                grouped_data = _get_current_file_state()
                await websocket.send_text(json.dumps({"type": "FILE_LIST_UPDATED", "payload": grouped_data}))

    except WebSocketDisconnect:
        logger.info(
            f"WebSocket disconnected for user: {manager.active_connections.get(websocket, 'unknown')}")
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(
            f"WebSocket error for user {manager.active_connections.get(websocket, 'unknown')}: {e}")
        manager.disconnect(websocket)


@app.get("/dashboard/activity", response_model=ActivityFeed)
async def get_activity_feed(limit: int = 50, offset: int = 0):
    """
    Scans Git history to create an activity feed with pagination.

    Args:
        limit: Number of activities to return (default 50, max 200)
        offset: Number of commits to skip (for pagination)
    """
    git_repo = app_state.get('git_repo')
    if not git_repo or not git_repo.repo:
        raise HTTPException(
            status_code=503, detail="Repository not available.")

    # Limit the maximum to prevent abuse
    limit = min(limit, 200)

    activities = []
    processed_count = 0

    try:
        # Use skip and max_count for efficient pagination
        # Get more commits than needed since not all will be activities
        for commit in git_repo.repo.iter_commits(skip=offset, max_count=limit * 3):
            if len(activities) >= limit:
                break

            msg = commit.message.strip()
            user = commit.author.name
            event_type = "COMMIT"
            filename = "N/A"
            revision = None

            # Parse commit messages to determine event type and filename
            if msg.startswith("REV"):
                event_type = "CHECK_IN"
                match = re.search(r"REV ([\d\.]+):\s*(.*)", msg)
                if match:
                    revision = match.group(1)

            elif msg.startswith("NEW:"):
                event_type = "NEW_FILE"
                match = re.search(r"NEW: Upload ([^\s]+)", msg)
                if match:
                    filename = match.group(1)

            elif msg.startswith("LINK:"):
                event_type = "NEW_LINK"
                match = re.search(r"LINK: Create '([^']+)'", msg)
                if match:
                    filename = match.group(1)

            elif msg.startswith("LOCK:"):
                event_type = "CHECK_OUT"
                filename = msg.replace("LOCK:", "").split(" by ")[0].strip()

            elif msg.startswith("REFRESH LOCK:"):
                event_type = "REFRESH_LOCK"
                filename = msg.replace("REFRESH LOCK:", "").split(" by ")[
                    0].strip()

            elif msg.startswith("USER CANCEL:"):
                event_type = "CANCEL"
                filename = msg.replace("USER CANCEL: Unlock", "").split(" by ")[
                    0].strip()

            elif msg.startswith("ADMIN OVERRIDE:"):
                event_type = "OVERRIDE"
                filename = msg.replace("ADMIN OVERRIDE: Unlock", "").split(" by ")[
                    0].strip()

            elif msg.startswith("ADMIN DELETE FILE:"):
                event_type = "DELETE_FILE"
                filename = msg.replace("ADMIN DELETE FILE:", "").split(" by ")[
                    0].strip()

            elif msg.startswith("ADMIN DELETE LINK:"):
                event_type = "DELETE_LINK"
                match = re.search(r"Remove link ([^\s]+)", msg)
                if match:
                    filename = match.group(1)

            elif msg.startswith("ADMIN REVERT:"):
                event_type = "REVERT"
                match = re.search(r"ADMIN REVERT: ([^\s]+)", msg)
                if match:
                    filename = match.group(1)

            elif msg.startswith("MSG:"):
                event_type = "MESSAGE"
                if "Send message to" in msg:
                    match = re.search(r"Send message to ([^\s]+)", msg)
                    if match:
                        filename = f"Message to {match.group(1)}"
                elif "Acknowledge message" in msg:
                    filename = "Message acknowledgment"

            # For check-ins, find the actual file that was changed
            if event_type == "CHECK_IN":
                for file_diff in commit.diff(commit.parents[0] if commit.parents else None):
                    if file_diff.a_path:
                        for ext in ALLOWED_FILE_TYPES.keys():
                            if file_diff.a_path.endswith(ext):
                                filename = Path(file_diff.a_path).name
                                break
                        if filename != "N/A":
                            break

            # Only add known event types to the feed
            if event_type != "COMMIT":
                activities.append(ActivityItem(
                    event_type=event_type,
                    filename=filename,
                    user=user,
                    timestamp=datetime.fromtimestamp(
                        commit.committed_date, tz=timezone.utc).isoformat(),
                    commit_hash=commit.hexsha,
                    message=msg,
                    revision=revision
                ))

        return ActivityFeed(activities=activities)

    except Exception as e:
        logger.error(f"Failed to generate activity feed: {e}")
        raise HTTPException(
            status_code=500, detail="Could not generate activity feed.")


@app.get("/debug/file_types")
async def debug_file_types():
    git_repo = app_state.get('git_repo')
    if not git_repo:
        return {"error": "No git repo"}

    debug_info = {}
    for ext in ALLOWED_FILE_TYPES.keys():
        pattern = f"*{ext}"
        files = git_repo.list_files(pattern)
        debug_info[ext] = {
            "pattern": pattern,
            "count": len(files),
            "files": [f["name"] for f in files]
        }

    return debug_info


@app.get("/system/lfs_status")
async def get_lfs_status():
    """Check if Git LFS is available and configured"""
    try:
        # Check if LFS is installed
        result = subprocess.run(['git', 'lfs', 'version'],
                                capture_output=True, text=True)
        lfs_installed = result.returncode == 0
        lfs_version = result.stdout.strip() if lfs_installed else None

        # Check if repo is using LFS
        git_repo = app_state.get('git_repo')
        lfs_configured = False
        tracked_patterns = []

        if git_repo and git_repo.repo:
            gitattributes = git_repo.repo_path / '.gitattributes'
            if gitattributes.exists():
                content = gitattributes.read_text()
                if 'filter=lfs' in content:
                    lfs_configured = True
                    tracked_patterns = [line.split()[0] for line in content.splitlines()
                                        if 'filter=lfs' in line]

        return {
            "lfs_installed": lfs_installed,
            "lfs_version": lfs_version,
            "lfs_configured": lfs_configured,
            "tracked_patterns": tracked_patterns
        }
    except Exception as e:
        logger.error(f"Error checking LFS status: {e}")
        return {
            "lfs_installed": False,
            "lfs_version": None,
            "lfs_configured": False,
            "tracked_patterns": [],
            "error": str(e)
        }


@app.post(
    "/files/{filename}/revert_commit",
    summary="Admin Revert File to Previous Version",
    description="""
    **Admin Only:** Reverts a file to the state it was in before a specific commit.
    
    **⚠️ Important:** This creates a new commit that undoes the changes,
    preserving the complete Git history while reverting the file content.
    
    **Process:**
    1. Identifies the commit to revert
    2. Checks out the file state from the parent commit
    3. Creates a new commit with the reverted content
    4. Maintains complete audit trail
    
    **Safety Features:**
    - Requires admin privileges
    - Prevents revert if file is currently checked out
    - Cannot revert the initial commit of a file
    - Preserves all Git history
    
    **Use Cases:**
    - Undo problematic changes
    - Recover from accidental modifications
    - Rollback after discovering issues
    - Emergency recovery procedures
    """,
    response_model=StandardResponse,
    responses={
        200: {"description": "Commit reverted successfully"},
        400: {"description": "Cannot revert initial commit"},
        403: {"description": "Permission denied - admin access required"},
        404: {"description": "File not found"},
        409: {"description": "File currently checked out"},
        500: {"description": "Revert failed"}
    },
    tags=["Admin", "Version Control"]
)
async def revert_commit(filename: str, request: AdminRevertRequest):
    """
    Admin action to revert a file's content to the state before a specific commit.
    This manually checks out the previous version of the file(s) and creates a new commit.
    """
    cfg_manager, git_repo, metadata_manager = app_state.get(
        'config_manager'), app_state.get('git_repo'), app_state.get('metadata_manager')

    if not all([cfg_manager, git_repo, metadata_manager]):
        raise HTTPException(
            status_code=500, detail="Repository not initialized.")

    # 1. Admin Permission Check
    admin_users = ADMIN_USERS
    if request.admin_user not in admin_users:
        raise HTTPException(
            status_code=403, detail="Permission denied. Admin access required.")

    # 2. Find file and check for existing lock
    file_path = find_file_path(filename)
    if not file_path:
        raise HTTPException(status_code=404, detail="File not found")

    if metadata_manager.get_lock_info(file_path):
        raise HTTPException(
            status_code=409, detail="Cannot revert while file is checked out by a user.")

    # 3. Perform the Git Revert using a manual checkout from the parent commit
    try:
        repo = git_repo.repo
        bad_commit = repo.commit(request.commit_hash)

        # Ensure there is a parent commit to revert to
        if not bad_commit.parents:
            raise HTTPException(
                status_code=400, detail="Cannot revert the initial commit of a file.")
        parent_commit = bad_commit.parents[0]

        # Define the paths to revert (the main file and its metadata)
        paths_to_revert = [file_path]
        meta_path_str = f"{file_path}.meta.json"

        # Check if the meta file existed in the parent commit to avoid errors
        try:
            parent_commit.tree[meta_path_str]
            paths_to_revert.append(meta_path_str)
        except KeyError:
            logger.info(
                f"No meta file found in parent commit for {filename}, reverting main file only.")

        # Use git checkout to restore the files from the parent commit's state
        with repo.git.custom_environment(**git_repo.git_env):
            repo.git.checkout(parent_commit.hexsha, '--', *paths_to_revert)

            # Stage the restored files for the new commit
            repo.index.add(paths_to_revert)

            # Create a new commit for this revert action
            author = Actor(request.admin_user,
                           f"{request.admin_user}@example.com")
            commit_message = f"ADMIN REVERT: {filename} to state before {request.commit_hash[:7]}\n\nReverted changes from commit: {bad_commit.message.strip()}"
            repo.index.commit(commit_message, author=author)

            # Push the new revert commit
            repo.remotes.origin.push()

        logger.info(
            f"Admin {request.admin_user} reverted {filename} to state before commit {request.commit_hash[:7]}")
        await handle_successful_git_operation()
        return JSONResponse({"status": "success", "message": f"Changes from commit {request.commit_hash[:7]} have been reverted."})

    except git.exc.GitCommandError as e:
        logger.error(f"Git revert (manual) failed: {e}")
        # Attempt to reset the repository to a clean state to avoid leaving it in a bad state
        try:
            with git_repo.repo.git.custom_environment(**git_repo.git_env):
                git_repo.repo.git.reset(
                    '--hard', f'origin/{git_repo.repo.active_branch.name}')
        except Exception as reset_e:
            logger.error(
                f"Failed to reset repo after revert failure: {reset_e}")

        raise HTTPException(
            status_code=500, detail=f"Failed to revert commit: {e}")


@app.post("/admin/reset_repository")
async def reset_repository(request: Request):
    """Admin endpoint to reset local repository."""
    try:
        body = await request.json()
        admin_user = body.get('admin_user')

        if admin_user not in ADMIN_USERS:
            raise HTTPException(
                status_code=403, detail="Admin access required")

        git_repo = app_state.get('git_repo')
        config_manager = app_state.get('config_manager')

        if not git_repo or not config_manager:
            raise HTTPException(
                status_code=500, detail="Repository not initialized")

        repo_path = git_repo.repo_path
        logger.info(f"Admin {admin_user} resetting repository at {repo_path}")

        # Step 1: Cancel any running git polling tasks to prevent interference
        for task in asyncio.all_tasks():
            if task.get_name() == 'git_polling_task':
                task.cancel()
                try:
                    await task  # Wait for cancellation to complete
                except asyncio.CancelledError:
                    pass
                logger.info("Cancelled git polling task")

        # Step 2: Force break any existing locks
        if git_repo.lock_manager:
            if not git_repo.lock_manager.force_break_lock():
                raise HTTPException(
                    status_code=500, detail="Failed to break repository lock")

        # Step 3: Close all repo connections
        if git_repo.repo:
            try:
                git_repo.repo.close()
                git_repo.repo.__del__()  # Force cleanup
            except Exception as e:
                logger.warning(f"Error closing repo: {e}")

        # Step 4: Clear from app state
        app_state['git_repo'] = None
        app_state['initialized'] = False

        # Step 5: Wait longer for file handles to release (increased from 0.5s)
        await asyncio.sleep(2.0)

        # Step 6: Force delete with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if repo_path.exists():
                    def handle_remove_readonly(func, path, exc):
                        """Error handler for Windows readonly files"""
                        import stat
                        if not os.access(path, os.W_OK):
                            os.chmod(path, stat.S_IWUSR)
                            func(path)
                        else:
                            raise

                    shutil.rmtree(repo_path, onerror=handle_remove_readonly)
                    logger.info(
                        f"Successfully deleted repository at {repo_path}")
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Retry {attempt + 1}/{max_retries}: {e}")
                    await asyncio.sleep(1)
                else:
                    raise Exception(
                        f"Could not delete repository after {max_retries} attempts: {e}")

        # Step 7: Re-initialize from scratch
        await asyncio.sleep(0.5)
        await initialize_application()

        return JSONResponse({
            "status": "success",
            "message": "Repository reset and re-cloned successfully"
        })

    except Exception as e:
        logger.error(f"Repository reset failed: {e}", exc_info=True)
        # Try to recover by re-initializing anyway
        try:
            await initialize_application()
        except Exception as init_e:
            logger.error(f"Recovery initialization failed: {init_e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/create_backup")
async def create_backup(request: Request):
    """Create a manual backup of the repository"""
    try:
        body = await request.json()
        admin_user = body.get('admin_user')

        if admin_user not in ADMIN_USERS:
            raise HTTPException(
                status_code=403, detail="Admin access required")

        git_repo = app_state.get('git_repo')
        if not git_repo:
            raise HTTPException(
                status_code=500, detail="Repository not initialized")

        import shutil
        from datetime import datetime

        backup_dir = Path.home() / 'MastercamBackups'
        backup_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f'mastercam_backup_{timestamp}'
        backup_path = backup_dir / backup_name

        shutil.copytree(git_repo.repo_path, backup_path)

        return JSONResponse({
            "status": "success",
            "backup_path": str(backup_path)
        })

    except Exception as e:
        logger.error(f"Backup creation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/cleanup_lfs")
async def cleanup_lfs(request: Request):
    """Cleanup old LFS objects"""
    try:
        body = await request.json()
        admin_user = body.get('admin_user')

        if admin_user not in ADMIN_USERS:
            raise HTTPException(
                status_code=403, detail="Admin access required")

        git_repo = app_state.get('git_repo')
        if not git_repo or not git_repo.repo:
            raise HTTPException(
                status_code=500, detail="Repository not initialized")

        # Run LFS prune
        with git_repo.repo.git.custom_environment(**git_repo.git_env):
            result = git_repo.repo.git.lfs('prune')

        return JSONResponse({
            "status": "success",
            "space_freed": "LFS cleanup complete"
        })

    except Exception as e:
        logger.error(f"LFS cleanup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/export_repository")
async def export_repository(request: Request):
    """Export repository as zip file"""
    try:
        body = await request.json()
        admin_user = body.get('admin_user')

        if admin_user not in ADMIN_USERS:
            raise HTTPException(
                status_code=403, detail="Admin access required")

        git_repo = app_state.get('git_repo')
        if not git_repo:
            raise HTTPException(
                status_code=500, detail="Repository not initialized")

        import shutil
        import tempfile

        # Create temporary zip
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp:
            zip_path = tmp.name

        shutil.make_archive(zip_path.replace('.zip', ''),
                            'zip', git_repo.repo_path)

        return FileResponse(
            zip_path,
            media_type='application/zip',
            filename=f'mastercam_export_{datetime.now().strftime("%Y%m%d")}.zip'
        )

    except Exception as e:
        logger.error(f"Repository export failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def main():
    """Main entry point for the application."""
    if not setup_git_lfs_path():
        logger.error("Git LFS setup failed. Some features may not work.")

    try:
        port = find_available_port(8000)
        logger.info(f"Found available port: {port}")
    except IOError as e:
        logger.error(f"{e} Aborting startup.")
        return

    threading.Timer(1.5, lambda: webbrowser.open(
        f"http://localhost:{port}")).start()

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
