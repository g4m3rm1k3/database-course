"""
Helper functions for application initialization and utilities.
"""

import logging
from pathlib import Path
from typing import Optional

from config.settings import ConfigManager
from core.gitlab_api import GitLabAPI
from core.git_repository import GitRepository
from core.metadata import MetadataManager
from services.file_service import FileService

logger = logging.getLogger(__name__)

async def initialize_application(app_state: dict):
    """Initialize all application components."""
    try:
        # Initialize configuration manager
        app_state['config_manager'] = ConfigManager()
        config = app_state['config_manager'].config
        
        # Initialize metadata manager
        metadata_path = Path(config.local.get('temp_path')) / 'metadata'
        app_state['metadata_manager'] = MetadataManager(metadata_path)
        
        # Initialize GitLab API if configured
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
            
            # Test GitLab connection and initialize repository
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
        
        # Initialize file service
        app_state['file_service'] = FileService(
            app_state['git_repo'],
            app_state['metadata_manager'],
            app_state['config_manager'],
            app_state['connection_manager']
        )
        
        # Clean up stale file locks
        if app_state.get('metadata_manager'):
            cleaned = app_state['metadata_manager'].cleanup_stale_locks()
            if cleaned > 0:
                logger.info(f"Cleaned up {cleaned} stale file locks")
        
        logger.info("Application initialization completed")
        
    except Exception as e:
        logger.error(f"Failed to initialize application: {str(e)}")

async def cleanup_application(app_state: dict):
    """Clean up application resources on shutdown."""
    try:
        # Close all WebSocket connections
        connection_manager = app_state.get('connection_manager')
        if connection_manager:
            for connection in connection_manager.active_connections:
                await connection.close()
        
        # Save configuration
        if app_state.get('config_manager'):
            app_state['config_manager'].save_config()
        
        logger.info("Application cleanup completed")
        
    except Exception as e:
        logger.error(f"Error during cleanup: {str(e)}")

def find_file_path(filename: str, app_state: dict) -> Optional[str]:
    """Find the full path of a file in the repository."""
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

def create_backup(file_path: str, content: bytes, config_manager) -> bool:
    """Create a backup of the file content."""
    try:
        from datetime import datetime
        
        backup_dir = Path(config_manager.config.local.get('backup_path'))
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"{Path(file_path).stem}_{timestamp}{Path(file_path).suffix}"
        backup_path = backup_dir / backup_filename
        
        backup_path.write_bytes(content)
        logger.info(f"Backup created: {backup_path}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to create backup: {str(e)}")
        return False