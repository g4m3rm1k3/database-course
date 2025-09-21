#!/usr/bin/env python3
"""
Git Operations Module for Mastercam GitLab Interface
Handles all Git and GitLab related operations including LFS support
"""

import os
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import logging
import requests
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class GitOperationError(Exception):
    """Custom exception for Git operation failures"""
    pass

class GitLabAPI:
    """GitLab API wrapper for repository operations"""

    def __init__(self, base_url: str, token: str, project_id: str):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.project_id = project_id
        self.headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }

    def test_connection(self) -> bool:
        """Test GitLab connection and permissions"""
        try:
            url = f"{self.base_url}/api/v4/projects/{self.project_id}"
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            logger.info("GitLab connection test successful")
            return True
        except Exception as e:
            logger.error(f"GitLab connection test failed: {str(e)}")
            return False

    def get_project_info(self) -> Dict:
        """Get project information from GitLab"""
        try:
            url = f"{self.base_url}/api/v4/projects/{self.project_id}"
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get project info: {str(e)}")
            raise GitOperationError(f"Failed to get project info: {str(e)}")

    def get_file_info(self, file_path: str, ref: str = 'main') -> Optional[Dict]:
        """Get file information from GitLab"""
        try:
            encoded_path = requests.utils.quote(file_path, safe='')
            url = f"{self.base_url}/api/v4/projects/{self.project_id}/repository/files/{encoded_path}"
            params = {'ref': ref}
            response = requests.get(url, headers=self.headers, params=params, timeout=10)

            if response.status_code == 404:
                return None

            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get file info for '{file_path}': {str(e)}")
            return None

class GitLFSManager:
    """Manages Git LFS operations for large binary files"""

    def __init__(self, repo_path: Path):
        self.repo_path = Path(repo_path)

    def setup_lfs(self):
        """Initialize Git LFS in the repository"""
        try:
            # Install LFS hooks
            self._run_git_command(['lfs', 'install'])

            # Track Mastercam files
            self._run_git_command(['lfs', 'track', '*.mcam'])
            self._run_git_command(['lfs', 'track', '*.mcam-*'])

            # Add .gitattributes if it doesn't exist or needs updating
            gitattributes_path = self.repo_path / '.gitattributes'
            if not gitattributes_path.exists():
                with open(gitattributes_path, 'w') as f:
                    f.write("*.mcam filter=lfs diff=lfs merge=lfs -text\n")
                    f.write("*.mcam-* filter=lfs diff=lfs merge=lfs -text\n")

                # Commit .gitattributes
                self._run_git_command(['add', '.gitattributes'])
                self._run_git_command(['commit', '-m', 'Add Git LFS tracking for Mastercam files'])

            logger.info("Git LFS setup completed")

        except Exception as e:
            logger.error(f"Failed to setup Git LFS: {str(e)}")
            raise GitOperationError(f"Failed to setup Git LFS: {str(e)}")

    def _run_git_command(self, args: List[str]) -> subprocess.CompletedProcess:
        """Run git command in repository directory"""
        cmd = ['git'] + args
        result = subprocess.run(
            cmd,
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            raise GitOperationError(f"Git command failed: {' '.join(cmd)}\nError: {result.stderr}")

        return result

class GitRepository:
    """Manages Git repository operations"""

    def __init__(self, repo_path: Path, remote_url: str, username: str, token: str):
        self.repo_path = Path(repo_path)
        self.remote_url = remote_url
        self.username = username
        self.token = token
        self.lfs_manager = GitLFSManager(repo_path)

        # Configure Git credentials
        self._configure_credentials()

    def _configure_credentials(self):
        """Configure Git credentials for authentication"""
        try:
            # Parse URL to inject credentials
            parsed = urlparse(self.remote_url)
            if parsed.scheme in ['http', 'https']:
                # Create authenticated URL
                auth_url = f"{parsed.scheme}://{self.username}:{self.token}@{parsed.netloc}{parsed.path}"
                self.authenticated_url = auth_url
            else:
                self.authenticated_url = self.remote_url

        except Exception as e:
            logger.error(f"Failed to configure credentials: {str(e)}")
            raise GitOperationError(f"Failed to configure credentials: {str(e)}")

    def clone_or_pull(self) -> bool:
        """Clone repository if it doesn't exist, otherwise pull latest changes"""
        try:
            if self.repo_path.exists() and (self.repo_path / '.git').exists():
                logger.info("Repository exists, pulling latest changes...")
                return self._pull()
            else:
                logger.info("Repository doesn't exist, cloning...")
                return self._clone()

        except Exception as e:
            logger.error(f"Failed to clone or pull repository: {str(e)}")
            return False

    def _clone(self) -> bool:
        """Clone the repository"""
        try:
            # Ensure parent directory exists
            self.repo_path.parent.mkdir(parents=True, exist_ok=True)

            # Remove existing directory if it exists but isn't a git repo
            if self.repo_path.exists():
                shutil.rmtree(self.repo_path)

            # Clone repository
            cmd = [
                'git', 'clone',
                self.authenticated_url,
                str(self.repo_path)
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120  # Longer timeout for initial clone
            )

            if result.returncode != 0:
                raise GitOperationError(f"Git clone failed: {result.stderr}")

            # Setup Git LFS
            self.lfs_manager.setup_lfs()

            logger.info("Repository cloned successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to clone repository: {str(e)}")
            return False

    def _pull(self) -> bool:
        """Pull latest changes from remote"""
        try:
            # Fetch and pull
            self._run_git_command(['fetch', 'origin'])
            self._run_git_command(['pull', 'origin', 'main'])

            logger.info("Repository updated successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to pull repository: {str(e)}")
            return False

    def commit_and_push(self, file_path: str, commit_message: str, author_name: str, author_email: str) -> bool:
        """Commit file changes and push to remote"""
        try:
            # Configure user for this commit
            self._run_git_command(['config', 'user.name', author_name])
            self._run_git_command(['config', 'user.email', author_email])

            # Add file to staging
            self._run_git_command(['add', file_path])

            # Check if there are changes to commit
            result = self._run_git_command(['diff', '--cached', '--name-only'])
            if not result.stdout.strip():
                logger.info("No changes to commit")
                return True

            # Commit changes
            self._run_git_command(['commit', '-m', commit_message])

            # Push to remote
            push_cmd = ['push', 'origin', 'main']
            self._run_git_command(push_cmd)

            logger.info(f"File '{file_path}' committed and pushed successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to commit and push file '{file_path}': {str(e)}")
            return False

    def get_file_history(self, file_path: str, limit: int = 10) -> List[Dict]:
        """Get commit history for a specific file"""
        try:
            cmd = [
                'log', '--oneline', '--follow',
                f'--max-count={limit}',
                '--pretty=format:%H|%an|%ae|%ad|%s',
                '--date=iso',
                '--', file_path
            ]

            result = self._run_git_command(cmd)

            history = []
            for line in result.stdout.strip().split('\n'):
                if line:
                    parts = line.split('|', 4)
                    if len(parts) == 5:
                        history.append({
                            'commit_hash': parts[0],
                            'author_name': parts[1],
                            'author_email': parts[2],
                            'date': parts[3],
                            'message': parts[4]
                        })

            return history

        except Exception as e:
            logger.error(f"Failed to get file history for '{file_path}': {str(e)}")
            return []

    def get_file_content(self, file_path: str) -> Optional[bytes]:
        """Get file content from repository"""
        try:
            full_path = self.repo_path / file_path
            if full_path.exists():
                return full_path.read_bytes()
            return None

        except Exception as e:
            logger.error(f"Failed to read file '{file_path}': {str(e)}")
            return None

    def save_file(self, file_path: str, content: bytes) -> bool:
        """Save file content to repository"""
        try:
            full_path = self.repo_path / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_bytes(content)
            return True

        except Exception as e:
            logger.error(f"Failed to save file '{file_path}': {str(e)}")
            return False

    def list_files(self, pattern: str = "*.mcam") -> List[Dict]:
        """List files in repository matching pattern"""
        try:
            files = []

            # Use git ls-files to get tracked files
            result = self._run_git_command(['ls-files', '--', pattern])

            for file_path in result.stdout.strip().split('\n'):
                if file_path:
                    full_path = self.repo_path / file_path
                    if full_path.exists():
                        stat = full_path.stat()
                        files.append({
                            'path': file_path,
                            'name': full_path.name,
                            'size': stat.st_size,
                            'modified_at': datetime.fromtimestamp(stat.st_mtime).isoformat()
                        })

            return files

        except Exception as e:
            logger.error(f"Failed to list files: {str(e)}")
            return []

    def _run_git_command(self, args: List[str]) -> subprocess.CompletedProcess:
        """Run git command in repository directory"""
        cmd = ['git'] + args
        result = subprocess.run(
            cmd,
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode != 0:
            raise GitOperationError(f"Git command failed: {' '.join(cmd)}\nError: {result.stderr}")

        return result

class MetadataManager:
    """Manages file lock metadata in a separate repository or local storage"""

    def __init__(self, storage_path: Path):
        self.storage_path = Path(storage_path)
        self.locks_file = self.storage_path / 'file_locks.json'
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # Initialize locks file if it doesn't exist
        if not self.locks_file.exists():
            self._save_locks({})

    def _load_locks(self) -> Dict:
        """Load locks from storage"""
        try:
            if self.locks_file.exists():
                return json.loads(self.locks_file.read_text())
            return {}
        except Exception as e:
            logger.error(f"Failed to load locks: {str(e)}")
            return {}

    def _save_locks(self, locks: Dict) -> bool:
        """Save locks to storage"""
        try:
            self.locks_file.write_text(json.dumps(locks, indent=2))
            return True
        except Exception as e:
            logger.error(f"Failed to save locks: {str(e)}")
            return False

    def create_lock(self, file_path: str, user: str) -> bool:
        """Create a lock for a file"""
        try:
            locks = self._load_locks()

            # Check if already locked
            if file_path in locks:
                existing_lock = locks[file_path]
                if existing_lock['user'] != user:
                    logger.warning(f"File '{file_path}' is already locked by '{existing_lock['user']}'")
                    return False

            # Create new lock
            locks[file_path] = {
                'user': user,
                'timestamp': datetime.now().isoformat(),
                'hostname': os.uname().nodename if hasattr(os, 'uname') else 'unknown'
            }

            return self._save_locks(locks)

        except Exception as e:
            logger.error(f"Failed to create lock for '{file_path}': {str(e)}")
            return False

    def release_lock(self, file_path: str, user: str = None) -> bool:
        """Release a lock for a file"""
        try:
            locks = self._load_locks()

            if file_path not in locks:
                return True  # Already unlocked

            # Check user permission (if specified)
            if user and locks[file_path]['user'] != user:
                logger.warning(f"User '{user}' cannot release lock owned by '{locks[file_path]['user']}'")
                return False

            # Remove lock
            del locks[file_path]
            return self._save_locks(locks)

        except Exception as e:
            logger.error(f"Failed to release lock for '{file_path}': {str(e)}")
            return False

    def get_lock_info(self, file_path: str) -> Optional[Dict]:
        """Get lock information for a file"""
        try:
            locks = self._load_locks()
            return locks.get(file_path)
        except Exception as e:
            logger.error(f"Failed to get lock info for '{file_path}': {str(e)}")
            return None

    def list_all_locks(self) -> Dict:
        """Get all current locks"""
        return self._load_locks()

    def cleanup_stale_locks(self, max_age_hours: int = 24) -> int:
        """Remove locks older than specified hours"""
        try:
            locks = self._load_locks()
            now = datetime.now()
            removed_count = 0

            stale_files = []
            for file_path, lock_info in locks.items():
                lock_time = datetime.fromisoformat(lock_info['timestamp'])
                age_hours = (now - lock_time).total_seconds() / 3600

                if age_hours > max_age_hours:
                    stale_files.append(file_path)

            for file_path in stale_files:
                del locks[file_path]
                removed_count += 1

            if removed_count > 0:
                self._save_locks(locks)
                logger.info(f"Cleaned up {removed_count} stale locks")

            return removed_count

        except Exception as e:
            logger.error(f"Failed to cleanup stale locks: {str(e)}")
            return 0