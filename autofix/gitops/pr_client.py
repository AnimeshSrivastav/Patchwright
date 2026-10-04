from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_BRANCH_PREFIX = "autofix/"


class GitHubPRClient:
    """
    Creates draft PRs on GitHub using PyGithub.
    Scoped to autofix/* branches only — never non-draft, never to main.
    Idempotent: checks for existing open PRs before creating.
    """

    def __init__(self, repo: str, token: str) -> None:
        self.repo_name = repo
        self.token = token

    def create_draft_pr(self, branch: str, title: str, body: str) -> tuple[str, bool]:
        """
        Create a draft PR from branch -> main (base).
        Returns (pr_url, already_existed).
        Never creates a non-draft PR. Never targets a branch other than main.
        """
        if not branch.startswith(_BRANCH_PREFIX):
            raise ValueError(
                f"Safety violation: refusing to create PR for branch '{branch}'. "
                f"Only '{_BRANCH_PREFIX}*' branches are allowed."
            )

        from github import Github  # type: ignore[import-untyped]
        gh = Github(self.token)
        repo = gh.get_repo(self.repo_name)

        # Idempotency check — return existing PR if one exists
        existing = repo.get_pulls(head=f"{repo.owner.login}:{branch}", state="open")
        if existing.totalCount > 0:
            pr = existing[0]
            logger.info("pr_client_existing branch=%s pr=%s", branch, pr.html_url)
            return pr.html_url, True

        # Safety: always draft=True, always base="main"
        pr = repo.create_pull(
            title=title,
            body=body,
            head=branch,
            base="main",
            draft=True,
        )
        logger.info("pr_client_created branch=%s pr=%s", branch, pr.html_url)
        return pr.html_url, False
