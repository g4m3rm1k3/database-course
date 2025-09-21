#!/usr/bin/env python3
"""
Metadata Manager for Mastercam GitLab Interface
Manages file lock metadata in a separate repository or local storage
"""

import json
from pathlib import Path
from datetime import datetime
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class MetadataManager:
    """Manages the centralized file lock metadata."""
    
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
    
    def get_lock_info(self, file_path: str) -> Optional[Dict]:
        """Get lock information for a file"""
        try:
            locks = self._load_locks()
            return locks.get(file_path)
        except Exception as e:
            logger.error(f"Failed to get lock info for '{file_path}': {str(e)}")
            return None
    
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
    
    def cleanup_stale_locks(self, max_age_hours: int = 24) -> int:
        """Remove locks older than specified hours"""
        try:
            locks = self._load_locks()
            now = datetime.now()
            removed_count = 0
            
            stale_files = []
            for file_path, lock_info in locks.items():
                try:
                    lock_time = datetime.fromisoformat(lock_info['timestamp'])
                    age_hours = (now - lock_time).total_seconds() / 3600
                    
                    if age_hours > max_age_hours:
                        stale_files.append(file_path)
                except (ValueError, KeyError):
                    stale_files.append(file_path)  # Also clean up invalid entries
            
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