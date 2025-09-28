Here's a complete implementation guide you can test at work:

## **Step 1: Test GitLab LFS Support**

First, test if your GitLab has LFS enabled:

```bash
# In any directory on your work machine
git clone <your-gitlab-repo-url> test-lfs
cd test-lfs
git lfs install
git lfs track "*.mcam"
git add .gitattributes
git commit -m "Test LFS setup"
git push
```

If this works without errors, you have LFS. If it fails, skip to the "No LFS Alternative" section below.

## **Step 2: Code Changes for LFS Integration**

Replace your `GitRepository` class `_init_repo` method:

```python
def _init_repo(self):
    try:
        if not self.repo_path.exists():
            logger.info(f"Cloning repository to {self.repo_path}")
            repo = git.Repo.clone_from(self.remote_url_with_token, self.repo_path, env=self.git_env)

            # Configure LFS
            try:
                repo.git.lfs('install')
                logger.info("Git LFS installed for repository")

                # Set up .gitattributes for LFS if not exists
                gitattributes_path = self.repo_path / '.gitattributes'
                if not gitattributes_path.exists():
                    with open(gitattributes_path, 'w') as f:
                        f.write('*.mcam filter=lfs diff=lfs merge=lfs -text\n')
                        f.write('*.vnc filter=lfs diff=lfs merge=lfs -text\n')
                        f.write('*.emcam filter=lfs diff=lfs merge=lfs -text\n')

                    repo.git.add('.gitattributes')
                    repo.git.commit('-m', 'Add LFS configuration for CAD files')
                    repo.git.push()
                    logger.info("LFS configuration added to repository")

            except git.exc.GitCommandError as e:
                logger.warning(f"LFS setup failed, continuing without LFS: {e}")

            return repo

        repo = git.Repo(self.repo_path)
        if not repo.remotes:
            raise git.exc.InvalidGitRepositoryError

        # Ensure LFS is installed for existing repos
        try:
            repo.git.lfs('install')
        except git.exc.GitCommandError:
            logger.warning("LFS not available for existing repository")

        return repo
    except (git.exc.InvalidGitRepositoryError, git.exc.NoSuchPathError):
        logger.warning(f"Invalid repo at {self.repo_path}, re-cloning.")
        if self.repo_path.exists():
            import shutil
            shutil.rmtree(self.repo_path)
        return git.Repo.clone_from(self.remote_url_with_token, self.repo_path, env=self.git_env)
    except Exception as e:
        logger.error(f"Failed to initialize repository: {e}")
        return None
```

Modify your `get_file_content` method:

```python
def get_file_content(self, file_path: str) -> Optional[bytes]:
    full_path = self.repo_path / file_path

    # If file doesn't exist locally, try to pull it with LFS
    if not full_path.exists():
        try:
            self.repo.git.lfs('pull', '--include', file_path)
            logger.info(f"LFS pulled file: {file_path}")
        except git.exc.GitCommandError as e:
            logger.warning(f"LFS pull failed for {file_path}: {e}")
            # Try regular git checkout as fallback
            try:
                self.repo.git.checkout('HEAD', '--', file_path)
            except git.exc.GitCommandError:
                logger.error(f"Could not retrieve file: {file_path}")
                return None

    if full_path.exists():
        return full_path.read_bytes()
    return None
```

Add cleanup after successful operations:

```python
def commit_and_push(self, file_paths: List[str], message: str, author_name: str, author_email: str) -> bool:
    with self.lock_manager:
        if not self.repo:
            return False
        try:
            with self.repo.git.custom_environment(**self.git_env):
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
                self.repo.remotes.origin.push()

                # NEW: Optional cleanup of large files to save disk space
                self._cleanup_large_files(file_paths)

            logger.info("Changes pushed to GitLab.")
            return True
        except Exception as e:
            logger.error(f"Git commit/push failed: {e}")
            try:
                with self.repo.git.custom_environment(**self.git_env):
                    self.repo.git.reset('--hard', f'origin/{self.repo.active_branch.name}')
            except Exception as reset_e:
                logger.error(f"Failed to reset repo after push failure: {reset_e}")
            return False

def _cleanup_large_files(self, file_paths: List[str]):
    """Remove large files after successful commit to save disk space"""
    for file_path in file_paths:
        full_path = self.repo_path / file_path
        if full_path.exists() and full_path.suffix.lower() in ['.mcam', '.vnc', '.emcam']:
            try:
                file_size = full_path.stat().st_size
                # Remove files larger than 50MB
                if file_size > 50_000_000:
                    full_path.unlink()
                    logger.info(f"Cleaned up large file after commit: {file_path} ({file_size / 1_000_000:.1f} MB)")
            except OSError as e:
                logger.warning(f"Could not clean up file {file_path}: {e}")
```

## **Step 3: No LFS Alternative (If LFS Test Fails)**

If LFS isn't available, use this sparse checkout approach instead:

```python
def _init_repo(self):
    try:
        if not self.repo_path.exists():
            logger.info(f"Cloning repository with sparse checkout to {self.repo_path}")

            # Clone without checking out files
            repo = git.Repo.clone_from(
                self.remote_url_with_token,
                self.repo_path,
                env=self.git_env,
                no_checkout=True
            )

            # Configure sparse checkout
            repo.git.config('core.sparseCheckout', 'true')

            # Create sparse-checkout file - only checkout metadata initially
            sparse_file = self.repo_path / '.git' / 'info' / 'sparse-checkout'
            sparse_file.parent.mkdir(parents=True, exist_ok=True)
            with open(sparse_file, 'w') as f:
                f.write('*.meta.json\n')
                f.write('.locks/\n')
                f.write('*.link\n')
                f.write('.gitattributes\n')

            # Checkout only the sparse files
            repo.git.read_tree('-m', '-u', 'HEAD')
            logger.info("Repository initialized with sparse checkout")
            return repo

        # For existing repos, ensure sparse checkout is enabled
        repo = git.Repo(self.repo_path)
        repo.git.config('core.sparseCheckout', 'true')
        return repo

    except Exception as e:
        logger.error(f"Failed to initialize repository: {e}")
        return None

def _ensure_file_available(self, filename: str):
    """Ensure a file is available locally by adding it to sparse checkout"""
    full_path = self.repo_path / filename
    if not full_path.exists():
        sparse_file = self.repo_path / '.git' / 'info' / 'sparse-checkout'

        # Add file to sparse checkout
        with open(sparse_file, 'a') as f:
            f.write(f'{filename}\n')

        # Checkout the file
        self.repo.git.read_tree('-m', '-u', 'HEAD')
        logger.info(f"Added {filename} to sparse checkout")

def get_file_content(self, file_path: str) -> Optional[bytes]:
    # Ensure file is available locally
    self._ensure_file_available(file_path)

    full_path = self.repo_path / file_path
    if full_path.exists():
        return full_path.read_bytes()
    return None
```

## **Step 4: Testing Plan**

1. **Back up your current working app**
2. **Test LFS first** with the commands above
3. **Apply the LFS code changes** if LFS works
4. **Test with a small .mcam file** to verify checkout/checkin works
5. **Monitor disk usage** - initial clone should be much smaller

The key benefit: Your initial repository clone will be tiny (just metadata), and large files only download when actually checked out. This solves your storage scaling problem while keeping your existing app architecture intact.

Both approaches maintain your current user experience - the LFS/sparse checkout happens transparently behind the scenes.
