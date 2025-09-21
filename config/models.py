"""
Pydantic models for the Mastercam GitLab Interface application.
"""

from typing import Dict, List, Optional, Any
from pathlib import Path
import tempfile
from pydantic import BaseModel, Field

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