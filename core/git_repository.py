"""
Git repository operations for the Mastercam GitLab Interface.
"""

import os
import git
from git import Actor
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class GitRepository:
    def __init__(self, repo_path: Path, remote_url: str, username: str, token: str):
        self.repo_path = repo_path
        self.remote_url = remote_url
        self.username = username
        self.token = token
        self.repo = None

    def _get_credential_url(self) -> str:
        """Get the URL with embedded credentials for authentication."""
        return f"https://oauth2:{self.token}@{self.remote_url.split('://')[-1]}"

    def clone_or_pull(self) -> bool:
        """Clone the repository if it doesn't exist, or pull latest changes."""
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
        """List all files matching the given pattern in the repository."""
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
        """Get the content of a file from the repository."""
        full_path = self.repo_path / file_path
        if full_path.exists():
            return full_path.read_bytes()
        return None

    def save_file(self, file_path: str, content: bytes) -> bool:
        """Save a file to the repository."""
        try:
            full_path = self.repo_path / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_bytes(content)
            return True
        except IOError as e:
            logger.error(f"Failed to save file: {e}")
            return False

    def commit_and_push(self, file_path: str, message: str, author_name: str, author_email: str) -> bool:
        """Commit changes and push to remote repository."""
        if not self.repo:
            return False
        
        try:
            self.repo.index.add([file_path])
            self.repo.index.commit(message, author=Actor(author_name, author_email))
            
            logger.info("Pushing changes to remote repository...")
            self.repo.git.push(self._get_credential_url(), f"main:{self.repo.active_branch}")
            
            logger.info("Changes successfully pushed to GitLab.")
            return True
        except git.GitCommandError as e:
            logger.error(f"Git commit/push failed: {e}")
            return False

    def get_file_history(self, file_path: str, limit: int = 10) -> List[Dict]:
        """Get the commit history for a specific file."""
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