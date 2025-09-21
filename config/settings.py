"""
Configuration management for the Mastercam GitLab Interface.
"""

import os
import json
import base64
import logging
from pathlib import Path
from typing import Dict, Optional, Any
from cryptography.fernet import Fernet

from .models import AppConfig

logger = logging.getLogger(__name__)

class EncryptionManager:
    """Handles encryption and decryption of sensitive data."""
    
    def __init__(self, config_dir: Path):
        self.config_dir = Path(config_dir)
        self.key_file = self.config_dir / '.encryption_key'
        self._fernet = None
        self._initialize_encryption()
    
    def _initialize_encryption(self):
        """Initialize the encryption system with a key file."""
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
        """Encrypt a string and return base64 encoded result."""
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
        """Decrypt base64 encoded encrypted data."""
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
    """Manages application configuration and user settings."""
    
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
        """Get the default configuration directory based on OS."""
        if os.name == 'nt':
            base = Path.home() / 'AppData' / 'Local' / 'MastercamGitInterface'
        else:
            base = Path.home() / '.config' / 'mastercam_git_interface'
        return base
    
    def _load_config(self) -> AppConfig:
        """Load configuration from file or create default."""
        try:
            if self.config_file.exists():
                content = self.config_file.read_text()
                if not content:
                    logger.warning("Configuration file is empty. Using default configuration.")
                    return AppConfig()
                
                data = json.loads(content)
                
                # Decrypt token if it exists
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
        """Load user settings from file."""
        try:
            if self.user_file.exists():
                return json.loads(self.user_file.read_text())
            return {}
        except Exception as e:
            logger.error(f"Failed to load user settings: {str(e)}")
            return {}
    
    def save_config(self) -> bool:
        """Save configuration to file with encryption if enabled."""
        try:
            data = self.config.model_dump()
            
            # Encrypt token if encryption is enabled
            if self.config.security.get('encrypt_tokens', False) and self.config.gitlab.get('token'):
                data['gitlab']['token'] = self.encryption.encrypt(self.config.gitlab['token'])
            
            self.config_file.write_text(json.dumps(data, indent=2))
            logger.info("Configuration saved successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to save configuration: {str(e)}")
            return False
    
    def save_user_settings(self) -> bool:
        """Save user settings to file."""
        try:
            self.user_file.write_text(json.dumps(self.user_settings, indent=2))
            return True
        except Exception as e:
            logger.error(f"Failed to save user settings: {str(e)}")
            return False
    
    def update_gitlab_config(self, base_url: str, project_id: str, username: str, token: str) -> bool:
        """Update GitLab configuration settings."""
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
        """Validate the current configuration and return any errors."""
        errors = []
        
        # Validate GitLab settings
        if not self.config.gitlab['base_url']:
            errors.append("GitLab base URL is required")
        if not self.config.gitlab['project_id']:
            errors.append("GitLab project ID is required")
        if not self.config.gitlab['username']:
            errors.append("GitLab username is required")
        if not self.config.gitlab['token']:
            errors.append("GitLab access token is required")
        
        # Validate paths
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
        
        # Validate numeric settings
        if self.config.local['max_file_size_mb'] <= 0:
            errors.append("Maximum file size must be positive")
        
        if self.config.ui['auto_refresh_interval'] <= 0:
            errors.append("Auto-refresh interval must be positive")
        
        return len(errors) == 0, errors
    
    def get_config_summary(self) -> Dict[str, Any]:
        """Get a summary of the current configuration for API responses."""
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