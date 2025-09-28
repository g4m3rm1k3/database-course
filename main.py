from metadata_manager import MetadataManager
from file_lock_manager import FileLockManager
from config_manager import ConfigManager
from starlette.websockets import WebSocketState
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
import git
from typing import Dict, List, Optional
from pathlib import Path
from datetime import datetime
import os
import logging
import json
import asyncio
```python


# Setup logging
logging.basicConfig(level=logging.INFO, filename='app.log', filemode='a',
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app_state = {
    "initialized": False,
    "git_repo": None,
    "lock_manager": None,
    "metadata_manager": None,
    "websockets": [],
    "config_manager": ConfigManager(),
}


class ConfigurationError(Exception):
    pass


class GitRepository:
    def __init__(self, repo_path: str, remote_url: str, config_manager: ConfigManager):
        self.repo_path = Path(repo_path)
        self.remote_url = remote_url
        self.config_manager = config_manager
        self.lock_manager = FileLockManager(self.repo_path / ".locks")
        self.metadata_manager = MetadataManager(self.repo_path / ".meta.json")
        self.git_env = {"GIT_SSL_NO_VERIFY": "true"} if config_manager.get_config().get(
            "allow_insecure_ssl", False) else {}
        self.repo = None
        self._init_repo()

    def _init_repo(self):
        try:
            with self.lock_manager:
                if not self.repo_path.exists():
                    logger.info(
                        f"Initializing sparse and shallow clone at {self.repo_path}")
                    # Initialize shallow clone with depth 1
                    self.repo = git.Repo.clone_from(
                        self.remote_url_with_token, self.repo_path, env=self.git_env,
                        depth=1, no_checkout=True
                    )
                    # Enable sparse checkout
                    self.repo.git.config('core.sparseCheckout', 'true')
                    # Create sparse-checkout file with metadata and lock files
                    sparse_checkout_file = self.repo_path / '.git' / 'info' / 'sparse-checkout'
                    sparse_checkout_file.parent.mkdir(
                        parents=True, exist_ok=True)
                    with sparse_checkout_file.open('w') as f:
                        f.write('.meta.json\n.locks/*\n*.link\n')
                    # Fetch metadata
                    self.repo.git.checkout(
                        'HEAD', '--', '.meta.json', '.locks/*', '*.link')
                else:
                    self.repo = git.Repo(self.repo_path)
                self.metadata_manager.load_metadata()
        except git.exc.GitCommandError as e:
            logger.error(f"Failed to initialize repository: {e}")
            raise ConfigurationError("Failed to initialize Git repository.")
        except Exception as e:
            logger.error(f"Unexpected error initializing repository: {e}")
            raise

    @property
    def remote_url_with_token(self):
        config = self.config_manager.get_config()
        token = config.get("token")
        gitlab_url = config.get("gitlab_url", "").rstrip('/')
        project_id = config.get("project_id")
        if not token or not project_id:
            raise ConfigurationError(
                "GitLab token or project ID not configured")
        return f"{gitlab_url}/oauth2/token:{token}@gitlab.com/{project_id}.git"

    def pull(self):
        try:
            with self.lock_manager:
                self.repo.git.fetch('--depth', '1')  # Shallow fetch
                self.repo.git.reset('--hard', 'origin/main')
                # Always pull metadata and lock files
                self.repo.git.checkout(
                    'HEAD', '--', '.meta.json', '.locks/*', '*.link')
                self.metadata_manager.load_metadata()
        except git.exc.GitCommandError as e:
            if 'network' in str(e).lower() or 'connection' in str(e).lower():
                logger.error(f"Network error during pull: {e}")
                app_state['initialized'] = False
                raise ConfigurationError(
                    "Network issue: Disconnected from GitLab.")
            raise

    def commit_and_push(self, file_paths: List[str], message: str, author_name: str, author_email: str = None) -> bool:
        try:
            with self.lock_manager:
                self.pull()
                self.repo.git.add(file_paths)
                author = f"{author_name} <{author_email or author_name + '@example.com'}>"
                self.repo.git.commit(m=message, author=author)
                self.repo.git.push()
                return True
        except git.exc.GitCommandError as e:
            logger.error(f"Git error during commit/push: {e}")
            self.repo.git.reset('--hard', 'origin/main')
            return False

    def list_files(self, pattern: str = "*.mcam") -> List[Dict]:
        files = []
        for group, group_files in self.metadata_manager.get_metadata().get("files", {}).items():
            for file in group_files:
                if file["filename"].endswith('.mcam') or file["filename"].endswith('.link'):
                    files.append({
                        "filename": file["filename"],
                        "path": file["path"],
                        "size": file.get("size", 0),
                        "modified_at": file.get("modified_at"),
                        "locked_by": file.get("locked_by"),
                        "locked_at": file.get("locked_at"),
                        "revision": file.get("revision"),
                        "description": file.get("description"),
                        "is_link": file["filename"].endswith('.link'),
                        "master_file": file.get("master_file"),
                        "status": self._get_file_status(file, app_state.get("user", "")),
                    })
        return files

    def _get_file_status(self, file: Dict, user: str) -> str:
        if file.get("locked_by") == user:
            return "checked_out_by_user"
        elif file.get("locked_by"):
            return "locked"
        return "unlocked"

    def checkout_file(self, filename: str, user: str):
        try:
            with self.lock_manager:
                self.pull()
                if self.metadata_manager.is_file_locked(filename):
                    raise HTTPException(
                        status_code=409, detail=f"File {filename} is already locked")
                # Add file to sparse-checkout
                sparse_checkout_file = self.repo_path / '.git' / 'info' / 'sparse-checkout'
                with sparse_checkout_file.open('a') as f:
                    f.write(f"{filename}\n")
                self.repo.git.checkout('HEAD', '--', filename)
                self.metadata_manager.create_lock(filename, user)
                self.commit_and_push(
                    [f".locks/{filename}.lock", ".meta.json"],
                    f"LOCK: {filename} by {user}",
                    user
                )
        except git.exc.GitCommandError as e:
            logger.error(f"Checkout error: {e}")
            raise HTTPException(
                status_code=500, detail=f"Checkout failed: {e}")

    def checkin_file(self, filename: str, user: str, file_path: Path, commit_message: str, rev_type: str, new_major_rev: Optional[str]):
        try:
            with self.lock_manager:
                self.pull()
                if not self.metadata_manager.is_file_locked_by_user(filename, user):
                    raise HTTPException(
                        status_code=403, detail="File not locked by this user")
                file_path.write(file_path.read_bytes())
                new_revision = self.metadata_manager.update_file_metadata(
                    filename, user, rev_type, new_major_rev)
                self.metadata_manager.remove_lock(filename)
                commit_files = [str(file_path), ".meta.json",
                                f".locks/{filename}.lock"]
                success = self.commit_and_push(
                    commit_files,
                    f"CHECK_IN: {filename} - REV {new_revision}: {commit_message}",
                    user
                )
                if not success:
                    self.metadata_manager.create_lock(
                        filename, user, force=True)
                    raise HTTPException(
                        status_code=500, detail="Check-in failed, file remains checked out")
                # Remove file from sparse-checkout after check-in
                sparse_checkout_file = self.repo_path / '.git' / 'info' / 'sparse-checkout'
                with sparse_checkout_file.open('r') as f:
                    lines = f.readlines()
                with sparse_checkout_file.open('w') as f:
                    f.writelines(
                        [line for line in lines if line.strip() != filename])
                file_path.unlink(missing_ok=True)  # Remove local file
                return new_revision
        except Exception as e:
            self.metadata_manager.create_lock(filename, user, force=True)
            logger.error(f"Check-in error: {e}")
            raise

    def admin_delete_file(self, filename: str, admin_user: str):
        try:
            with self.lock_manager:
                self.pull()
                file_path = self.repo_path / filename
                is_link = filename.endswith('.link')
                files_to_delete = [filename]
                if not is_link:
                    link_files = self.list_files("*.link")
                    for link_file in link_files:
                        link_content = json.loads(
                            self.get_file_content(link_file['path']))
                        if link_content.get("master_file") == filename:
                            link_path = link_file['path']
                            (self.repo_path / link_path).unlink(missing_ok=True)
                            files_to_delete.append(link_path)
                            logger.info(f"Deleted orphaned link: {link_path}")
                file_path.unlink(missing_ok=True)
                (self.repo_path /
                 f".locks/{filename}.lock").unlink(missing_ok=True)
                self.metadata_manager.remove_file_metadata(filename)
                self.commit_and_push(
                    files_to_delete + [".meta.json",
                                       f".locks/{filename}.lock"],
                    f"DELETE: {filename} by {admin_user}",
                    admin_user
                )
        except Exception as e:
            logger.error(f"Delete error: {e}")
            raise HTTPException(status_code=500, detail=f"Delete failed: {e}")

    def get_file_content(self, file_path: str) -> str:
        try:
            return (self.repo_path / file_path).read_text()
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="File not found")

# Other classes (ConfigManager, FileLockManager, MetadataManager) remain unchanged
# ...


@app.on_event("startup")
async def startup_event():
    config = app_state["config_manager"].get_config()
    if config.get("repo_path") and config.get("gitlab_url") and config.get("project_id"):
        try:
            app_state["git_repo"] = GitRepository(
                config["repo_path"], config["gitlab_url"], app_state["config_manager"]
            )
            app_state["lock_manager"] = app_state["git_repo"].lock_manager
            app_state["metadata_manager"] = app_state["git_repo"].metadata_manager
            app_state["initialized"] = True
            asyncio.create_task(git_polling_task())
            asyncio.create_task(git_gc_task())
            asyncio.create_task(backup_repo_task())
        except ConfigurationError as e:
            logger.error(f"Startup failed: {e}")
            app_state["initialized"] = False


async def git_polling_task():
    while True:
        try:
            if app_state["initialized"]:
                app_state["git_repo"].pull()
                await broadcast_file_list()
        except Exception as e:
            logger.error(f"Polling error: {e}")
        await asyncio.sleep(15)


async def git_gc_task():
    while True:
        await asyncio.sleep(7 * 24 * 3600)  # Weekly
        try:
            git_repo = app_state.get("git_repo")
            if git_repo:
                git_repo.repo.git.gc('--auto')
                logger.info("Ran git gc --auto for optimization.")
        except Exception as e:
            logger.error(f"Git gc failed: {e}")


async def backup_repo_task():
    while True:
        await asyncio.sleep(24 * 3600)  # Daily
        try:
            git_repo = app_state.get("git_repo")
            if git_repo:
                backup_path = Path.home() / 'MastercamGitBackup'
                if not backup_path.exists():
                    git.Repo.clone_from(
                        git_repo.remote_url_with_token, backup_path, depth=1)
                backup_repo = git.Repo(backup_path)
                backup_repo.git.fetch('--depth', '1')
                backup_repo.git.reset('--hard', 'origin/main')
                logger.info("Backed up repo to local clone.")
        except Exception as e:
            logger.error(f"Backup failed: {e}")


async def broadcast_file_list():
    files = app_state["git_repo"].list_files(
    ) if app_state.get("git_repo") else []
    grouped = {}
    for file in files:
        group = file["path"].split(
            "/")[0] if "/" in file["path"] else "Miscellaneous"
        if group not in grouped:
            grouped[group] = []
        grouped[group].append(file)
    data = {"type": "FILE_LIST_UPDATED", "payload": grouped}
    disconnected = []
    for ws in app_state["websockets"]:
        if ws.client_state == WebSocketState.CONNECTED:
            try:
                await ws.send_json(data)
            except Exception as e:
                logger.error(f"WebSocket broadcast error: {e}")
                disconnected.append(ws)
        else:
            disconnected.append(ws)
    app_state["websockets"] = [
        ws for ws in app_state["websockets"] if ws not in disconnected]


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    app_state["websockets"].append(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data.startswith("SET_USER:"):
                app_state["user"] = data.split(":", 1)[1]
            elif data == "REFRESH_FILES":
                await broadcast_file_list()
    except WebSocketDisconnect:
        app_state["websockets"].remove(websocket)


@app.get("/files")
async def get_files():
    if not app_state["initialized"]:
        raise HTTPException(
            status_code=503, detail="Repository not initialized")
    return app_state["git_repo"].list_files()


@app.post("/files/{filename}/checkout")
async def checkout_file(filename: str, user: str):
    if not app_state["initialized"]:
        raise HTTPException(
            status_code=503, detail="Repository not initialized")
    app_state["git_repo"].checkout_file(filename, user)
    await broadcast_file_list()
    return {"message": f"File {filename} checked out successfully"}


@app.post("/files/{filename}/checkin")
async def checkin_file(filename: str, user: str, file: UploadFile = File(...), commit_message: str = Form(...), rev_type: str = Form(...), new_major_rev: Optional[str] = Form(None)):
    if not app_state["initialized"]:
        raise HTTPException(
            status_code=503, detail="Repository not initialized")
    file_path = app_state["git_repo"].repo_path / filename
    new_revision = app_state["git_repo"].checkin_file(
        filename, user, file_path, commit_message, rev_type, new_major_rev)
    await broadcast_file_list()
    return {"message": f"File {filename} checked in successfully with revision {new_revision}"}


@app.post("/files/{filename}/delete")
async def admin_delete_file(filename: str, admin_user: str = Body(...)):
    if not app_state["initialized"]:
        raise HTTPException(
            status_code=503, detail="Repository not initialized")
    app_state["git_repo"].admin_delete_file(filename, admin_user)
    await broadcast_file_list()
    return {"message": f"File {filename} deleted successfully"}

# Other endpoints (config, history, etc.) remain unchanged
# ...
```
