

@app.post("/files/{filename}/revert_commit", response_model=StandardResponse, tags=["Admin", "Version Control"])
async def revert_commit(
    filename: str,
    request: AdminRevertRequest,
    git_repo: GitRepository = Depends(get_git_repo),
    metadata_manager: MetadataManager = Depends(get_metadata_manager)
):
    if request.admin_user not in ADMIN_USERS:
        raise HTTPException(
            status_code=403, detail="Permission denied. Admin access required.")

    # ✅ FIX: Pass git_repo to find_file_path
    file_path = find_file_path(git_repo, filename)
    if not file_path:
        raise HTTPException(status_code=404, detail="File not found")

    if metadata_manager.get_lock_info(file_path):
        raise HTTPException(
            status_code=409, detail="Cannot revert while file is checked out by a user.")

    # The rest of your revert logic is correct and can remain as is.
    # ... (rest of the logic) ...
    try:
        repo = git_repo.repo
        bad_commit = repo.commit(request.commit_hash)
        if not bad_commit.parents:
            raise HTTPException(
                status_code=400, detail="Cannot revert the initial commit of a file.")
        parent_commit = bad_commit.parents[0]

        paths_to_revert = [file_path]
        meta_path_str = f"{file_path}.meta.json"
        try:
            parent_commit.tree[meta_path_str]
            paths_to_revert.append(meta_path_str)
        except KeyError:
            logger.info(f"No meta file for {filename} in parent commit.")

        with repo.git.custom_environment(**git_repo.git_env):
            repo.git.checkout(parent_commit.hexsha, '--', *paths_to_revert)
            repo.index.add(paths_to_revert)
            author = Actor(request.admin_user,
                           f"{request.admin_user}@example.com")
            commit_message = f"ADMIN REVERT: {filename} to state before {request.commit_hash[:7]}"
            repo.index.commit(commit_message, author=author)
            repo.remotes.origin.push()

        await handle_successful_git_operation()
        return JSONResponse({"status": "success", "message": f"Changes from commit {request.commit_hash[:7]} have been reverted."})
    except git.exc.GitCommandError as e:
        logger.error(f"Git revert failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to revert commit: {e}")
