Looking at your updated code, I can see you've made good progress. Let me provide a comprehensive robustness strategy that builds on what you have while ensuring maximum speed and reliability.

## Current State Assessment

Your code already has several robust features:

- File locking with `FileLockManager`
- SSL configuration handling
- Comprehensive error handling
- Git environment variables for SSL
- Activity feed with pagination

## Key Robustness Improvements Needed

### 1. Add Backup System to GitRepository

```python
import shutil
from datetime import datetime

class BackupManager:
    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.backup_dir = repo_path.parent / "repo_backups"
        self.backup_dir.mkdir(exist_ok=True)

    def create_backup(self, reason: str = "auto") -> Path:
        """Create timestamped backup with automatic cleanup"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"backup_{timestamp}_{reason}"
        backup_path = self.backup_dir / backup_name

        try:
            # Use copytree with ignore for faster copying
            def ignore_patterns(dir, files):
                return [f for f in files if f.startswith('.git/objects') or f.endswith('.tmp')]

            shutil.copytree(self.repo_path, backup_path, ignore=ignore_patterns)
            logger.info(f"Created backup: {backup_path}")

            # Keep only last 5 backups for speed
            self._cleanup_old_backups(keep=5)
            return backup_path
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            raise

    def _cleanup_old_backups(self, keep=5):
        """Keep only the most recent backups"""
        backups = sorted(self.backup_dir.glob("backup_*"),
                        key=lambda x: x.stat().st_mtime, reverse=True)
        for old_backup in backups[keep:]:
            shutil.rmtree(old_backup)
            logger.debug(f"Cleaned up old backup: {old_backup}")

# Add to GitRepository.__init__():
class GitRepository:
    def __init__(self, repo_path: Path, remote_url: str, token: str):
        # ... existing code ...
        self.backup_manager = BackupManager(repo_path)

        # Create initial backup on startup
        try:
            self.backup_manager.create_backup("startup")
        except Exception as e:
            logger.warning(f"Startup backup failed: {e}")
```

### 2. Enhanced Error Recovery in Critical Operations

Update your `commit_and_push` method:

```python
def commit_and_push(self, file_paths: List[str], message: str, author_name: str, author_email: str) -> bool:
    # Create backup before risky operations
    backup_created = False
    try:
        self.backup_manager.create_backup("pre_commit")
        backup_created = True
    except Exception as e:
        logger.warning(f"Pre-commit backup failed: {e}")

    with self.lock_manager:
        if not self.repo:
            return False
        try:
            with self.repo.git.custom_environment(**self.git_env):
                # Existing commit logic...
                to_add = [p for p in file_paths if (self.repo_path / p).exists()]
                to_remove = [p for p in file_paths if not (self.repo_path / p).exists()]

                if to_add:
                    self.repo.index.add(to_add)
                if to_remove:
                    self.repo.index.remove(to_remove)

                if not self.repo.index.diff("HEAD") and not any(self.repo.index.diff(None)) and not self.repo.untracked_files:
                    logger.info("No changes to commit.")
                    return True

                author = Actor(author_name, author_email)
                self.repo.index.commit(message, author=author)

                # Try push with retries
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        self.repo.remotes.origin.push()
                        logger.info("Changes pushed to GitLab.")
                        return True
                    except Exception as push_error:
                        if attempt < max_retries - 1:
                            logger.warning(f"Push attempt {attempt + 1} failed: {push_error}")
                            time.sleep(2 ** attempt)  # Exponential backoff
                        else:
                            raise push_error

        except Exception as e:
            logger.error(f"Git commit/push failed: {e}")

            # Emergency recovery
            if backup_created:
                logger.critical("Attempting emergency recovery from backup")
                try:
                    self._emergency_restore()
                except Exception as recovery_error:
                    logger.critical(f"Emergency recovery failed: {recovery_error}")

            return False

def _emergency_restore(self):
    """Emergency restore from most recent backup"""
    try:
        backups = sorted(self.backup_manager.backup_dir.glob("backup_*"),
                       key=lambda x: x.stat().st_mtime, reverse=True)
        if backups:
            latest_backup = backups[0]
            logger.critical(f"EMERGENCY: Restoring from backup {latest_backup}")

            # Move corrupted repo
            corrupted_path = self.repo_path.parent / f"corrupted_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            shutil.move(self.repo_path, corrupted_path)

            # Restore from backup
            shutil.copytree(latest_backup, self.repo_path)

            # Reinitialize repo object
            self.repo = git.Repo(self.repo_path)
            logger.critical("Emergency restore completed")
        else:
            logger.critical("No backups available for emergency restore!")
    except Exception as e:
        logger.critical(f"Emergency restore failed: {e}")
```

### 3. Add Health Monitoring

```python
@app.get("/health/repository")
async def repository_health():
    """Fast repository health check"""
    health_status = {
        "status": "healthy",
        "checks": {},
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    try:
        git_repo = app_state.get('git_repo')
        if not git_repo:
            health_status["status"] = "unhealthy"
            health_status["checks"]["git_repo"] = "Repository not initialized"
            return health_status

        # Quick checks only for speed
        try:
            # Check repo is valid
            git_repo.repo.head.commit
            health_status["checks"]["repo_valid"] = "OK"
        except Exception as e:
            health_status["checks"]["repo_valid"] = f"FAIL: {str(e)[:50]}"
            health_status["status"] = "unhealthy"

        # Check backup availability (fast)
        if hasattr(git_repo, 'backup_manager'):
            backup_count = len(list(git_repo.backup_manager.backup_dir.glob("backup_*")))
            health_status["checks"]["backups_available"] = backup_count
            if backup_count == 0:
                health_status["status"] = "degraded"

        # Check working directory status (fast)
        try:
            if git_repo.repo.is_dirty():
                health_status["checks"]["working_dir"] = "DIRTY"
                health_status["status"] = "degraded"
            else:
                health_status["checks"]["working_dir"] = "OK"
        except Exception:
            health_status["checks"]["working_dir"] = "UNKNOWN"

        return health_status

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        health_status["status"] = "unhealthy"
        health_status["checks"]["general"] = f"FAIL: {str(e)[:50]}"
        return health_status

@app.post("/admin/create_backup")
async def create_manual_backup():
    """Admin endpoint to create manual backup"""
    git_repo = app_state.get('git_repo')
    if not git_repo or not hasattr(git_repo, 'backup_manager'):
        raise HTTPException(status_code=500, detail="Backup system not available")

    try:
        backup_path = git_repo.backup_manager.create_backup("manual")
        return {"status": "success", "backup_path": str(backup_path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backup failed: {e}")
```

### 4. Optimize File State Loading for Speed

Update your `_get_current_file_state()` function:

```python
def _get_current_file_state() -> Dict[str, List[Dict]]:
    git_repo, metadata_manager = app_state.get('git_repo'), app_state.get('metadata_manager')
    if not git_repo or not metadata_manager:
        return {"Miscellaneous": []}

    try:
        git_repo.pull()
    except Exception as e:
        logger.warning(f"Failed to pull latest changes: {e}")

    # Cache file lists to avoid repeated filesystem operations
    file_cache = {}

    # 1. Get all supported file types with caching
    all_files_raw = []
    for ext in ALLOWED_FILE_TYPES.keys():
        if ext not in file_cache:
            pattern = f"*{ext}"
            file_cache[ext] = git_repo.list_files(pattern)
        all_files_raw.extend(file_cache[ext])

    # Create map of all files
    master_files_map = {file_data['name']: file_data for file_data in all_files_raw}

    # Process files in batches for better performance
    all_files_to_process = list(master_files_map.values())

    # 2. Process link files efficiently
    if '.link' not in file_cache:
        file_cache['.link'] = git_repo.list_files("*.link")

    link_files_raw = file_cache['.link']

    # Use batch file reading for better performance
    for link_file_data in link_files_raw:
        try:
            link_content_str = git_repo.get_file_content(link_file_data['path'])
            if not link_content_str:
                continue

            link_content = json.loads(link_content_str)
            master_filename = link_content.get("master_file")

            if master_filename and master_filename in master_files_map:
                virtual_file_name = link_file_data['name'].replace('.link', '')
                virtual_file = {
                    'name': virtual_file_name,
                    'path': virtual_file_name,
                    'size': 0,
                    'modified_at': link_file_data['modified_at'],
                    'is_link': True,
                    'master_file': master_filename
                }
                all_files_to_process.append(virtual_file)
        except Exception as e:
            logger.error(f"Could not process link file {link_file_data['name']}: {e}")

    # 3. Batch process metadata and locks
    grouped_files = {}
    current_user = app_state.get('config_manager').config.gitlab.get('username', 'demo_user')

    # Pre-load all metadata files for efficiency
    metadata_cache = {}
    locks_cache = {}

    for file_data in all_files_to_process:
        path_for_meta = file_data['name'] if file_data.get('is_link') else file_data['path']

        # Cache metadata loading
        if path_for_meta not in metadata_cache:
            meta_path = git_repo.repo_path / f"{path_for_meta}.meta.json"
            if meta_path.exists():
                try:
                    metadata_cache[path_for_meta] = json.loads(meta_path.read_text())
                except json.JSONDecodeError:
                    metadata_cache[path_for_meta] = {}
            else:
                metadata_cache[path_for_meta] = {}

        # Cache lock info loading
        if path_for_meta not in locks_cache:
            locks_cache[path_for_meta] = metadata_manager.get_lock_info(path_for_meta)

        # Apply cached data
        meta_content = metadata_cache[path_for_meta]
        file_data['description'] = meta_content.get('description')
        file_data['revision'] = meta_content.get('revision')

        lock_info = locks_cache[path_for_meta]
        status, locked_by, locked_at = "unlocked", None, None
        if lock_info:
            status = "locked"
            locked_by = lock_info.get('user')
            locked_at = lock_info.get('timestamp')
            if locked_by == current_user:
                status = "checked_out_by_user"

        file_data['filename'] = file_data.pop('name')
        file_data.update({"status": status, "locked_by": locked_by, "locked_at": locked_at})

        # Group files
        filename = file_data['filename'].strip()
        group_name = "Miscellaneous"
        if re.match(r"^\d{7}.*", filename):
            group_name = f"{filename[:2]}XXXXX"
        if group_name not in grouped_files:
            grouped_files[group_name] = []
        grouped_files[group_name].append(file_data)

    return grouped_files
```

### 5. Add Circuit Breaker Pattern for External Calls

```python
class CircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_timeout=60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

    def call(self, func, *args, **kwargs):
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "HALF_OPEN"
            else:
                raise HTTPException(status_code=503, detail="Service temporarily unavailable")

        try:
            result = func(*args, **kwargs)
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failure_count = 0
            return result
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
                logger.warning(f"Circuit breaker opened due to failures")
            raise e

# Add to GitLabAPI class
gitlab_circuit_breaker = CircuitBreaker()

class GitLabAPI:
    def test_connection(self) -> bool:
        try:
            def _test():
                config_manager = app_state.get('config_manager')
                allow_insecure = config_manager.config.security.get("allow_insecure_ssl", False)
                verify_ssl = not allow_insecure
                response = requests.get(self.api_url, headers=self.headers, timeout=10, verify=verify_ssl)
                response.raise_for_status()
                return True

            return gitlab_circuit_breaker.call(_test)
        except Exception as e:
            logger.error(f"GitLab connection test failed: {e}")
            return False
```

### 6. Performance Monitoring

Add this endpoint to track performance:

```python
@app.get("/metrics/performance")
async def get_performance_metrics():
    """Get basic performance metrics"""
    git_repo = app_state.get('git_repo')
    if not git_repo:
        return {"error": "Repository not available"}

    start_time = time.time()

    # Test file list performance
    file_count = 0
    for ext in ALLOWED_FILE_TYPES.keys():
        files = git_repo.list_files(f"*{ext}")
        file_count += len(files)

    file_list_time = time.time() - start_time

    # Test metadata loading
    start_time = time.time()
    metadata_files = list(git_repo.repo_path.glob("*.meta.json"))
    metadata_time = time.time() - start_time

    return {
        "file_count": file_count,
        "file_list_time_ms": round(file_list_time * 1000, 2),
        "metadata_files": len(metadata_files),
        "metadata_scan_time_ms": round(metadata_time * 1000, 2),
        "backups_available": len(list(git_repo.backup_manager.backup_dir.glob("backup_*"))) if hasattr(git_repo, 'backup_manager') else 0
    }
```

## Summary of Robustness Features

1. **Automatic Backups**: Before every risky operation
2. **Emergency Recovery**: Automatic restoration from backups on failure
3. **Circuit Breaker**: Prevents cascade failures from external services
4. **Health Monitoring**: Real-time system status
5. **Performance Caching**: Optimized file state loading
6. **Retry Logic**: Exponential backoff for network operations
7. **Comprehensive Logging**: Detailed error tracking

This approach ensures your system can handle failures gracefully while maintaining high performance through intelligent caching and batch operations. The backup system provides safety without significant performance impact by keeping only recent backups and using efficient copying strategies.
