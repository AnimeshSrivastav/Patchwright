from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_BRANCH_PREFIX = "autofix/"


def _assert_autofix_branch(branch: str) -> None:
    """Hard guard: we never touch any branch that isn't autofix/*."""
    if not branch.startswith(_BRANCH_PREFIX):
        raise ValueError(
            f"Safety violation: refusing to create/push branch '{branch}'. "
            f"Only branches starting with '{_BRANCH_PREFIX}' are allowed."
        )


class GitClient:
    """
    Manages git operations for the fixer pipeline.
    Scoped to autofix/* branches only — never touches main.
    """

    def __init__(self, repo_url: str, token: str, mock: bool = False) -> None:
        self.repo_url = repo_url
        self.token = token
        self.mock = mock
        self._clone_dir: Path | None = None

    def clone(self, dest: Path | None = None) -> Path:
        """Clone the repo to a temp directory (or dest). Returns local path."""
        if self.mock:
            self._clone_dir = Path(tempfile.mkdtemp(prefix="patchwright_mock_"))
            (self._clone_dir / "app").mkdir()
            (self._clone_dir / "app" / "routes.py").write_text(
                "# mock source file\ndef get_item(item_id):\n    items = {}\n    return items[item_id]  # bug: KeyError\n"
            )
            logger.info("git_client_mock_clone dir=%s", self._clone_dir)
            return self._clone_dir

        import git as gitpython
        target = dest or Path(tempfile.mkdtemp(prefix="patchwright_clone_"))
        auth_url = self._inject_token(self.repo_url)
        gitpython.Repo.clone_from(auth_url, target)
        self._clone_dir = target
        logger.info("git_client_cloned repo=%s dir=%s", self.repo_url, target)
        return target

    def create_branch(self, incident_id: str) -> str:
        """Create and checkout branch autofix/<incident_id>. Returns branch name."""
        branch = f"{_BRANCH_PREFIX}{incident_id}"
        _assert_autofix_branch(branch)

        if self.mock:
            logger.info("git_client_mock_branch branch=%s", branch)
            return branch

        import git as gitpython
        repo = gitpython.Repo(self._clone_dir)
        # Check if branch already exists
        existing = [h.name for h in repo.heads]
        if branch in existing:
            repo.heads[branch].checkout()
            logger.info("git_client_existing_branch branch=%s", branch)
        else:
            repo.create_head(branch).checkout()
            logger.info("git_client_created_branch branch=%s", branch)
        return branch

    def commit_patch(self, file_path: str, content: str, message: str) -> None:
        """Write content to file_path and commit it."""
        if self.mock:
            return

        import git as gitpython
        repo = gitpython.Repo(self._clone_dir)
        full_path = self._clone_dir / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        repo.index.add([str(full_path)])
        repo.index.commit(message)

    def push_branch(self, branch: str) -> None:
        """Push the autofix branch to origin."""
        _assert_autofix_branch(branch)

        if self.mock:
            logger.info("git_client_mock_push branch=%s", branch)
            return

        import git as gitpython
        repo = gitpython.Repo(self._clone_dir)
        auth_url = self._inject_token(self.repo_url)
        origin = repo.remotes.origin
        origin.set_url(auth_url)
        origin.push(branch)
        logger.info("git_client_pushed branch=%s", branch)

    def get_diff_stats(self) -> tuple[int, list[str]]:
        """Return (lines_changed, files_changed) compared to main."""
        if self.mock:
            return 5, ["app/routes.py"]

        import git as gitpython
        repo = gitpython.Repo(self._clone_dir)
        diff = repo.head.commit.diff("HEAD~1", create_patch=True)
        lines = 0
        files: list[str] = []
        for d in diff:
            files.append(d.a_path or d.b_path)
            if d.diff:
                lines += d.diff.count(b"\n+") + d.diff.count(b"\n-")
        return lines, files

    def cleanup(self) -> None:
        """Remove clone directory."""
        if self._clone_dir and self._clone_dir.exists() and not self.mock:
            import shutil
            shutil.rmtree(self._clone_dir, ignore_errors=True)

    def _inject_token(self, url: str) -> str:
        """Inject token into HTTPS URL without exposing it in logs."""
        if self.token and "github.com" in url:
            return url.replace("https://", f"https://x-access-token:{self.token}@")
        return url
