#!/usr/bin/env python3
"""
Configuration Manager for Mastercam GitLab Interface
Handles application configuration, settings, and user preferences
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Optional, Any
from dataclasses import dataclass, asdict, field
from cryptography.fernet import Fernet
import base64

logger = logging.getLogger(__name__)

@dataclass
class GitLabConfig:
    """GitLab connection configuration"""
    base_url: str = ""
    project_id: str = ""
    username: str = ""
    token: str = ""  # Will be encrypted when stored
    branch: str = "main"
    timeout: int = 30

@dataclass
class LocalConfig:
    """Local application configuration"""
    repo_path: str = ""
    backup_path: str = ""
    temp_path: str = ""
    max_file_size_mb: int = 500
    auto_backup: bool = True
    cleanup_temp_files: bool = True

@dataclass
class UIConfig:
    """User interface configuration"""
    theme: str = "light"  # light, dark, auto
    language: str = "en"
    auto_refresh_interval: int = 30  # seconds
    show_file_details: bool = True
    show_notifications: bool = True
    notification_sound: bool = False

@dataclass
class SecurityConfig:
    """Security and authentication settings"""
    encrypt_tokens: bool = True
    session_timeout_hours: int = 8
    max_failed_attempts: int = 3
    require_admin_confirmation: bool = True
    auto_lock_stale_files_hours: int = 24

@dataclass
class AppConfig:
    """Complete application configuration"""
    version: str = "1.0.0"
    gitlab: GitLabConfig = field(default_factory=GitLabConfig)
    local: LocalConfig = field(default_factory=LocalConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    
    def __post_init__(self):
        """Initialize default paths after creation"""
        if not self.local.repo_path:
            self.local.repo_path = str(self.get_default_repo_path())
        if not self.local.backup_path:
            self.local.backup_path = str(self.get_default_backup_path())
        if not self.local.temp_path:
            self.local.temp_path = str(self.get_default_temp_path())
    
    @staticmethod
    def get_default_repo_path() -> Path:
        """Get default repository path"""
        if os.name == 'nt':  # Windows
            base = Path.home() / 'Documents' / 'MastercamGitRepo'
        else:  # Linux/Mac
            base = Path.home() / '.mastercam_git_repo'
        return base
    
    @staticmethod
    def get_default_backup_path() -> Path:
        """Get default backup path"""
        if os.name == 'nt':  # Windows
            base = Path.home() / 'Documents' / 'MastercamGitBackups'
        else:  # Linux/Mac
            base = Path.home() / '.mastercam_git_backups'
        return base
    
    @staticmethod
    def get_default_temp_path() -> Path:
        """Get default temporary files path"""
        import tempfile
        return Path(tempfile.gettempdir()) / 'mastercam_git_interface'

class EncryptionManager:
    """Handles encryption/decryption of sensitive data"""
    
    def __init__(self, config_dir: Path):
        self.config_dir = Path(config_dir)
        self.key_file = self.config_dir / '.encryption_key'
        self._fernet = None
        self._initialize_encryption()
    
    def _initialize_encryption(self):
        """Initialize encryption key"""
        try:
            if self.key_file.exists():
                # Load existing key
                key = self.key_file.read_bytes()
            else:
                # Generate new key
                key = Fernet.generate_key()
                self.key_file.write_bytes(key)
                # Make key file read-only for owner
                if os.name != 'nt':  # Not Windows
                    os.chmod(self.key_file, 0o600)
            
            self._fernet = Fernet(key)
            logger.info("Encryption initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize encryption: {str(e)}")
            # Fall back to base64 encoding (not secure, but functional)
            self._fernet = None
    
    def encrypt(self, data: str) -> str:
        """Encrypt sensitive data"""
        try:
            if self._fernet:
                encrypted = self._fernet.encrypt(data.encode())
                return base64.b64encode(encrypted).decode()
            else:
                # Fallback to base64 (not secure)
                return base64.b64encode(data.encode()).decode()
        except Exception as e:
            logger.error(f"Encryption failed: {str(e)}")
            return data  # Return original if encryption fails
    
    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt sensitive data"""
        try:
            if self._fernet:
                encrypted_bytes = base64.b64decode(encrypted_data.encode())
                decrypted = self._fernet.decrypt(encrypted_bytes)
                return decrypted.decode()
            else:
                # Fallback from base64
                return base64.b64decode(encrypted_data.encode()).decode()
        except Exception as e:
            logger.error(f"Decryption failed: {str(e)}")
            return encrypted_data  # Return original if decryption fails

class ConfigManager:
    """Manages application configuration"""
    
    def __init__(self, config_dir: Optional[Path] = None):
        if config_dir is None:
            config_dir = self._get_default_config_dir()
        
        self.config_dir = Path(config_dir)
        self.config_file = self.config_dir / 'config.json'
        self.user_file = self.config_dir / 'user_settings.json'
        
        # Create config directory
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize encryption
        self.encryption = EncryptionManager(self.config_dir)
        
        # Load or create configuration
        self.config = self._load_config()
        self.user_settings = self._load_user_settings()
    
    @staticmethod
    def _get_default_config_dir() -> Path:
        """Get default configuration directory"""
        if os.name == 'nt':  # Windows
            base = Path.home() / 'AppData' / 'Local' / 'MastercamGitInterface'
        else:  # Linux/Mac
            base = Path.home() / '.config' / 'mastercam_git_interface'
        return base
    
    def _load_config(self) -> AppConfig:
        """Load configuration from file"""
        try:
            if self.config_file.exists():
                data = json.loads(self.config_file.read_text())
                
                # Decrypt sensitive data
                if 'gitlab' in data and 'token' in data['gitlab']:
                    if data['gitlab']['token']:
                        data['gitlab']['token'] = self.encryption.decrypt(data['gitlab']['token'])
                
                # Convert to config object
                config = AppConfig()
                self._update_config_from_dict(config, data)
                return config
            else:
                logger.info("No existing configuration found, creating default")
                return AppConfig()
                
        except Exception as e:
            logger.error(f"Failed to load configuration: {str(e)}")
            return AppConfig()
    
    def _load_user_settings(self) -> Dict:
        """Load user-specific settings"""
        try:
            if self.user_file.exists():
                return json.loads(self.user_file.read_text())
            return {}
        except Exception as e:
            logger.error(f"Failed to load user settings: {str(e)}")
            return {}
    
    def _update_config_from_dict(self, config: AppConfig, data: Dict):
        """Update config object from dictionary"""
        for section_name, section_data in data.items():
            if hasattr(config, section_name) and isinstance(section_data, dict):
                section = getattr(config, section_name)
                for key, value in section_data.items():
                    if hasattr(section, key):
                        setattr(section, key, value)
    
    def save_config(self) -> bool:
        """Save configuration to file"""
        try:
            # Convert to dictionary
            data = asdict(self.config)
            
            # Encrypt sensitive data
            if self.config.security.encrypt_tokens and self.config.gitlab.token:
                data['gitlab']['token'] = self.encryption.encrypt(self.config.gitlab.token)
            
            # Write to file
            self.config_file.write_text(json.dumps(data, indent=2))
            logger.info("Configuration saved successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save configuration: {str(e)}")
            return False
    
    def save_user_settings(self) -> bool:
        """Save user settings to file"""
        try:
            self.user_file.write_text(json.dumps(self.user_settings, indent=2))
            return True
        except Exception as e:
            logger.error(f"Failed to save user settings: {str(e)}")
            return False
    
    def update_gitlab_config(self, base_url: str, project_id: str, username: str, token: str) -> bool:
        """Update GitLab configuration"""
        try:
            self.config.gitlab.base_url = base_url.rstrip('/')
            self.config.gitlab.project_id = project_id
            self.config.gitlab.username = username
            self.config.gitlab.token = token
            
            return self.save_config()
            
        except Exception as e:
            logger.error(f"Failed to update GitLab configuration: {str(e)}")
            return False
    
    def validate_config(self) -> tuple[bool, list[str]]:
        """Validate current configuration"""
        errors = []
        
        # Check GitLab configuration
        if not self.config.gitlab.base_url:
            errors.append("GitLab base URL is required")
        
        if not self.config.gitlab.project_id:
            errors.append("GitLab project ID is required")
        
        if not self.config.gitlab.username:
            errors.append("GitLab username is required")
        
        if not self.config.gitlab.token:
            errors.append("GitLab access token is required")
        
        # Check paths
        try:
            repo_path = Path(self.config.local.repo_path)
            repo_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            errors.append(f"Invalid repository path: {str(e)}")
        
        try:
            backup_path = Path(self.config.local.backup_path)
            backup_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            errors.append(f"Invalid backup path: {str(e)}")
        
        # Check numeric values
        if self.config.local.max_file_size_mb <= 0:
            errors.append("Maximum file size must be positive")
        
        if self.config.ui.auto_refresh_interval <= 0:
            errors.append("Auto-refresh interval must be positive")
        
        return len(errors) == 0, errors
    
    def get_user_setting(self, key: str, default: Any = None) -> Any:
        """Get user-specific setting"""
        return self.user_settings.get(key, default)
    
    def set_user_setting(self, key: str, value: Any) -> bool:
        """Set user-specific setting"""
        try:
            self.user_settings[key] = value
            return self.save_user_settings()
        except Exception as e:
            logger.error(f"Failed to set user setting '{key}': {str(e)}")
            return False
    
    def export_config(self, export_path: Path, include_tokens: bool = False) -> bool:
        """Export configuration to file"""
        try:
            data = asdict(self.config)
            
            if not include_tokens:
                data['gitlab']['token'] = ""
            
            export_path.write_text(json.dumps(data, indent=2))
            logger.info(f"Configuration exported to {export_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to export configuration: {str(e)}")
            return False
    
    def import_config(self, import_path: Path) -> bool:
        """Import configuration from file"""
        try:
            if not import_path.exists():
                raise FileNotFoundError(f"Configuration file not found: {import_path}")
            
            data = json.loads(import_path.read_text())
            
            # Validate imported data
            temp_config = AppConfig()
            self._update_config_from_dict(temp_config, data)
            
            # If validation passes, update current config
            self._update_config_from_dict(self.config, data)
            
            # Save updated configuration
            success = self.save_config()
            if success:
                logger.info(f"Configuration imported from {import_path}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to import configuration: {str(e)}")
            return False
    
    def reset_to_defaults(self) -> bool:
        """Reset configuration to defaults"""
        try:
            self.config = AppConfig()
            return self.save_config()
        except Exception as e:
            logger.error(f"Failed to reset configuration: {str(e)}")
            return False
    
    def get_config_summary(self) -> Dict[str, Any]:
        """Get configuration summary for display"""
        return {
            'gitlab_url': self.config.gitlab.base_url,
            'project_id': self.config.gitlab.project_id,
            'username': self.config.gitlab.username,
            'has_token': bool(self.config.gitlab.token),
            'repo_path': self.config.local.repo_path,
            'backup_enabled': self.config.local.auto_backup,
            'theme': self.config.ui.theme,
            'auto_refresh': self.config.ui.auto_refresh_interval,
            'version': self.config.version
        }