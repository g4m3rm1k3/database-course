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

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Form, UploadFile, File, Response, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.websockets import WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from cryptography.fernet import Fernet
import base64

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
    ".vnc": {"signature": None}
}

# --- Pydantic Data Models ---


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


class AdminRevertRequest(BaseModel):
    admin_user: str = Field(...,
                            description="Admin username performing the revert")
    commit_hash: str = Field(..., description="Git commit hash to revert")


class ActivityItem(BaseModel):
    event_type: str = Field(
        ..., description="Type of activity: CHECK_IN, CHECK_OUT, CANCEL, OVERRIDE")
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
    security: dict = Field(default_factory=lambda: {"admin_users": ["admin"]})
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

# --- Core Application Classes & Functions ---
# [Previous classes remain the same - EncryptionManager, ConfigManager, GitLabAPI, GitRepository, etc.]


async def is_valid_file_type(file: UploadFile) -> bool:
    """
    Validates a file based on its extension and magic number signature.
    """
    file_extension = Path(file.filename).suffix.lower()

    if file_extension not in ALLOWED_FILE_TYPES:
        return False

    config = ALLOWED_FILE_TYPES[file_extension]
    signature = config.get("signature")

    # If no signature is defined, we trust the extension
    if signature is None:
        return True

    # Read the first few bytes of the file to check the signature
    try:
        file_header = await file.read(len(signature))
        return file_header == signature
    finally:
        # IMPORTANT: Reset the file pointer so it can be read again later
        await file.seek(0)

# [All other classes and functions remain the same...]

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
    """,
    version="1.0.0",
    contact={
        "name": "Mastercam GitLab Interface Support",
        "email": "support@example.com",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
    lifespan=lifespan
)

app.add_middleware(CORSMiddleware, allow_origins=[
                   "*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


def resource_path(relative_path):
    base_path = getattr(sys, '_MEIPASS', os.path.abspath("."))
    return os.path.join(base_path, relative_path)


app.mount("/static", StaticFiles(directory=resource_path("static")), name="static")
templates = Jinja2Templates(directory=resource_path("templates"))

# [All initialization and helper functions remain the same...]

# --- API Endpoints with Enhanced Documentation ---


@app.get(
    "/",
    summary="Main Application Interface",
    description="Serves the main web interface for the Mastercam GitLab file management system.",
    response_class=FileResponse,
    tags=["Web Interface"]
)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get(
    "/config",
    summary="Get Current Configuration",
    description="Returns the current system configuration including GitLab settings and user permissions.",
    response_model=ConfigSummary,
    tags=["Configuration"]
)
async def get_config():
    if config_manager := app_state.get('config_manager'):
        return config_manager.get_config_summary()
    raise HTTPException(
        status_code=503, detail="Application not fully initialized.")


@app.post(
    "/config/gitlab",
    summary="Update GitLab Configuration",
    description="""
    Updates the GitLab configuration with new connection details.
    
    **Validation Process:**
    1. Validates the GitLab URL and token by connecting to the API
    2. Verifies that the provided username matches the token owner
    3. Tests project accessibility with the given project ID
    4. Saves the configuration if all validations pass
    
    **Security Note:** The access token is encrypted before storage.
    """,
    response_model=StandardResponse,
    responses={
        200: {"description": "Configuration updated successfully"},
        400: {"description": "Validation failed - username doesn't match token owner"},
        401: {"description": "Invalid GitLab URL or access token"},
        500: {"description": "Internal server error"}
    },
    tags=["Configuration"]
)
async def update_gitlab_config(request: ConfigUpdateRequest):
    # [Implementation remains the same...]
    pass


@app.get(
    "/refresh",
    summary="Manual Repository Refresh",
    description="""
    Manually triggers a refresh of the local repository from GitLab.
    
    This endpoint:
    - Pulls the latest changes from the remote GitLab repository
    - Updates the local file cache
    - Broadcasts updates to all connected WebSocket clients
    - Returns whether any changes were detected
    """,
    response_model=StandardResponse,
    tags=["Repository Management"]
)
async def manual_refresh():
    # [Implementation remains the same...]
    pass


@app.get(
    "/files",
    summary="List All Files",
    description="""
    Retrieves a comprehensive list of all files in the repository, grouped by file prefix.
    
    **File Grouping:**
    - Files starting with 7 digits are grouped by their first 2 digits (e.g., "12XXXXX")
    - Other files are placed in a "Miscellaneous" group
    
    **File Status:**
    - `unlocked`: Available for checkout
    - `locked`: Checked out by another user
    - `checked_out_by_user`: Checked out by the current user
    
    **Metadata Included:**
    - File size and modification date
    - Lock information (who, when)
    - Description and revision from metadata files
    """,
    response_model=Dict[str, List[FileInfo]],
    responses={
        200: {"description": "Successfully retrieved file list"},
        500: {"description": "Failed to retrieve files"}
    },
    tags=["File Management"]
)
async def get_files():
    # [Implementation remains the same...]
    pass


@app.get(
    "/users",
    summary="Get User List",
    description="""
    Returns a list of all users who have made commits to the repository.
    
    This is useful for:
    - Populating user selection dropdowns
    - Identifying active contributors
    - Administrative user management
    
    The list is extracted from Git commit history and sorted alphabetically.
    """,
    response_model=UserList,
    tags=["User Management"]
)
async def get_users():
    # [Implementation remains the same...]
    pass


@app.post(
    "/messages/send",
    summary="Send Message to User",
    description="""
    Allows administrators to send messages to specific users.
    
    **Admin Only:** This endpoint requires admin privileges.
    
    **Message Delivery:**
    - Messages are stored in the repository under `.messages/`
    - Recipients receive messages via WebSocket when they connect
    - Messages persist until acknowledged by the recipient
    
    **Use Cases:**
    - Notify users about system maintenance
    - Request file releases
    - General administrative communications
    """,
    response_model=StandardResponse,
    responses={
        200: {"description": "Message sent successfully"},
        403: {"description": "Permission denied - admin access required"},
        500: {"description": "Failed to send message"}
    },
    tags=["Admin", "Messaging"]
)
async def send_message(request: SendMessageRequest):
    # [Implementation remains the same...]
    pass


@app.post(
    "/messages/acknowledge",
    summary="Acknowledge Received Message",
    description="""
    Marks a message as read/acknowledged by the recipient.
    
    **Process:**
    - Removes the specified message from the user's message queue
    - Commits the change to the repository
    - Updates all connected clients via WebSocket
    
    **Parameters:**
    - `message_id`: Unique identifier of the message to acknowledge
    - `user`: Username of the person acknowledging the message
    """,
    response_model=StandardResponse,
    tags=["Messaging"]
)
async def acknowledge_message(request: AckMessageRequest):
    # [Implementation remains the same...]
    pass


@app.get(
    "/dashboard/stats",
    summary="Get Dashboard Statistics",
    description="""
    Provides real-time statistics for the dashboard view.
    
    **Current Statistics:**
    - **Active Checkouts**: List of all currently checked out files
      - File name and path
      - User who has it checked out
      - When it was checked out
      - Duration of checkout in seconds
    
    The list is sorted by checkout duration (longest first) to highlight 
    files that may need attention.
    """,
    response_model=DashboardStats,
    tags=["Dashboard", "Statistics"]
)
async def get_dashboard_stats():
    # [Implementation remains the same...]
    pass


@app.get(
    "/dashboard/activity",
    summary="Get Activity Feed",
    description="""
    Returns a chronological feed of recent repository activities.
    
    **Activity Types:**
    - `CHECK_IN`: File was checked in with new changes
    - `CHECK_OUT`: File was checked out for editing
    - `CANCEL`: User cancelled their checkout
    - `OVERRIDE`: Admin forcibly unlocked a file
    
    **Information Included:**
    - User who performed the action
    - Timestamp of the activity
    - Associated Git commit hash
    - File revision (for check-ins)
    - Commit message or action description
    
    Limited to the last 50 commits for performance.
    """,
    response_model=ActivityFeed,
    tags=["Dashboard", "Activity Tracking"]
)
async def get_activity_feed():
    # [Implementation remains the same...]
    pass


@app.post(
    "/files/new_upload",
    summary="Upload New File",
    description="""
    Uploads a brand new file to the repository.
    
    **File Validation:**
    - Filename must follow the format: `7digits_1-3letters_1-3numbers.ext`
    - Example: `1234567_AB123.mcam`
    - Maximum filename length: 15 characters (before extension)
    - Only `.mcam` and `.vnc` files are allowed
    - File content is validated against magic number signatures
    
    **Process:**
    1. Validates filename format and file type
    2. Checks that the file doesn't already exist
    3. Saves the file and creates metadata
    4. Commits and pushes to GitLab
    5. Notifies all connected clients
    
    **Metadata:**
    - Description: User-provided file description
    - Revision: Starting revision number
    """,
    response_model=StandardResponse,
    responses={
        200: {"description": "File uploaded successfully"},
        400: {"description": "Invalid filename format or file type"},
        409: {"description": "File already exists"},
        500: {"description": "Upload failed"}
    },
    tags=["File Management"]
)
async def new_upload(
    user: str = Form(..., description="Username performing the upload"),
    description: str = Form(..., description="File description for metadata"),
    rev: str = Form(..., description="Initial revision number (e.g., '1.0')"),
    file: UploadFile = File(..., description="File to upload")
):
    # [Implementation remains the same...]
    pass


@app.post(
    "/files/{filename}/checkout",
    summary="Check Out File for Editing",
    description="""
    Checks out a file for exclusive editing by a user.
    
    **Lock Mechanism:**
    - Creates a lock file in the `.locks/` directory
    - Commits the lock to GitLab for distributed synchronization
    - Prevents other users from checking out the same file
    
    **Refresh Capability:**
    - If the same user already has the file checked out, refreshes the lock timestamp
    - This is useful for extending long editing sessions
    
    **Error Conditions:**
    - File is already locked by another user
    - File doesn't exist in the repository
    - Repository synchronization fails
    """,
    response_model=StandardResponse,
    responses={
        200: {"description": "File checked out successfully"},
        404: {"description": "File not found"},
        409: {"description": "File already locked by another user"},
        500: {"description": "Checkout failed"}
    },
    tags=["File Management"]
)
async def checkout_file(
    filename: str = Path(..., description="Name of the file to check out"),
    request: CheckoutRequest = Body(...,
                                    description="Checkout request details")
):
    # [Implementation remains the same...]
    pass


@app.post(
    "/files/{filename}/checkin",
    summary="Check In Modified File",
    description="""
    Checks in a modified file with automatic versioning.
    
    **Prerequisites:**
    - User must have the file currently checked out
    - File type must match the original (validated by magic numbers)
    
    **Versioning Options:**
    - `minor`: Increments minor version (e.g., 1.2 → 1.3)
    - `major`: Increments major version and resets minor (e.g., 1.2 → 2.0)
      - Can specify exact major version number
    
    **Process:**
    1. Validates user has file locked
    2. Validates uploaded file type
    3. Saves new file content
    4. Updates metadata with new revision
    5. Releases the file lock
    6. Commits all changes to GitLab
    7. Notifies connected clients
    
    **Rollback:** If commit fails, the lock is restored to maintain consistency.
    """,
    response_model=StandardResponse,
    responses={
        200: {"description": "File checked in successfully"},
        400: {"description": "Invalid file type"},
        403: {"description": "File not locked by this user"},
        404: {"description": "File not found"},
        500: {"description": "Check-in failed"}
    },
    tags=["File Management"]
)
async def checkin_file(
    filename: str = Path(..., description="Name of the file to check in"),
    user: str = Form(..., description="Username performing the check-in"),
    commit_message: str = Form(..., description="Description of changes made"),
    rev_type: str = Form(...,
                         description="Version increment type: 'minor' or 'major'"),
    new_major_rev: Optional[str] = Form(
        None, description="Specific major version number (for major revisions)"),
    file: UploadFile = File(..., description="Modified file to check in")
):
    # [Implementation remains the same...]
    pass


@app.post(
    "/files/{filename}/cancel_checkout",
    summary="Cancel File Checkout",
    description="""
    Cancels a file checkout, releasing the lock without saving changes.
    
    **Use Cases:**
    - User finished reviewing and doesn't need to make changes
    - User wants to cancel their checkout to allow others to edit
    - Accidental checkout that needs to be reversed
    
    **Requirements:**
    - Only the user who checked out the file can cancel it
    - Admins can use the override endpoint for forced unlocks
    
    **Process:**
    1. Verifies the user has the file checked out
    2. Removes the lock file from the repository
    3. Commits the lock removal
    4. Notifies all connected clients
    """,
    response_model=StandardResponse,
    responses={
        200: {"description": "Checkout cancelled successfully"},
        403: {"description": "File not checked out by this user"},
        404: {"description": "File not found"},
        500: {"description": "Cancel failed"}
    },
    tags=["File Management"]
)
async def cancel_checkout(
    filename: str = Path(...,
                         description="Name of the file to cancel checkout"),
    request: CheckoutRequest = Body(..., description="Cancel request details")
):
    # [Implementation remains the same...]
    pass


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
async def admin_override(
    filename: str = Path(..., description="Name of the file to override"),
    request: AdminOverrideRequest = Body(...,
                                         description="Admin override request details")
):
    # [Implementation remains the same...]
    pass


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
async def admin_delete_file(
    filename: str = Path(..., description="Name of the file to delete"),
    request: AdminDeleteRequest = Body(...,
                                       description="Admin delete request details")
):
    # [Implementation remains the same...]
    pass


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
async def download_file(filename: str = Path(..., description="Name of the file to download")):
    # [Implementation remains the same...]
    pass


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
async def get_file_history(filename: str = Path(..., description="Name of the file to get history for")):
    # [Implementation remains the same...]
    pass


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
async def download_file_version(
    filename: str = Path(..., description="Name of the file"),
    commit_hash: str = Path(...,
                            description="Git commit hash of the desired version")
):
    # [Implementation remains the same...]
    pass


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
async def revert_commit(
    filename: str = Path(..., description="Name of the file to revert"),
    request: AdminRevertRequest = Body(...,
                                       description="Admin revert request details")
):
    # [Implementation remains the same...]
    pass


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

# --- Additional API Tags for Better Organization ---

# Tag definitions for better Swagger organization
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

# Update the FastAPI app initialization to include tags metadata
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
        "name": "Mastercam GitLab Interface Support",
        "email": "support@example.com",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
    openapi_tags=tags_metadata,
    lifespan=lifespan
)


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


def main():
    """
    Main entry point for the application.
    Finds an available port and launches the web interface.
    """
    try:
        port = find_available_port(8000)
        logger.info(f"Found available port: {port}")
    except IOError as e:
        logger.error(f"{e} Aborting startup.")
        return

    # Open the browser after a short delay
    threading.Timer(1.5, lambda: webbrowser.open(
        f"http://localhost:{port}")).start()

    # Start the Uvicorn server
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
