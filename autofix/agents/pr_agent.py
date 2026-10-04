from __future__ import annotations

import logging
from dataclasses import dataclass

from autofix.models.schemas import FixOutcome, Incident, RoutingDecision

logger = logging.getLogger(__name__)

_PR_BODY_TEMPLATE = """## Incident Report

**Incident ID:** `{incident_id}`
**Error:** `{error_type}: {message}`
**Status Code:** {status_code}
**Routing:** {error_class} → fixer

---

## Root Cause

{root_cause}

## Reproducing Test

```python
# {test_file_path}
{test_content_preview}
```

## Diff Summary

- **Files changed:** {files_changed}
- **Lines changed:** {diff_lines}

## Verification Results

{verification_results}

## Observability

- **Trace:** {trace_link}
- **Estimated cost:** ${cost_usd:.4f}
- **Iterations used:** {iterations_used}

---

*This PR was opened automatically by Patchwright. Please review before merging.*
*Never merge without human review — this PR is intentionally a draft.*
"""


@dataclass
class PRResult:
    pr_url: str
    branch: str
    already_existed: bool = False


class PRAgent:
    """
    Pushes the fixed branch and opens a draft PR with full context.
    Idempotent: if a PR for this branch already exists, returns the existing URL.
    """

    def __init__(self, github_repo: str, github_token: str, mock: bool = False) -> None:
        self.github_repo = github_repo
        self.github_token = github_token
        self.mock = mock

    def create_pr(
        self,
        incident: Incident,
        routing: RoutingDecision,
        fix_outcome: FixOutcome,
        test_file_path: str,
        test_content: str,
        verification_summary: str,
        trace_link: str,
        cost_usd: float,
    ) -> PRResult:
        branch = fix_outcome.branch

        if self.mock:
            logger.info("pr_agent_mock incident_id=%s branch=%s", incident.id, branch)
            return PRResult(
                pr_url=f"https://github.com/{self.github_repo}/pull/999",
                branch=branch,
                already_existed=False,
            )

        from autofix.gitops.pr_client import GitHubPRClient
        client = GitHubPRClient(repo=self.github_repo, token=self.github_token)

        title = f"[autofix] {incident.error_type} in {incident.id[:8]}: {incident.message[:60]}"
        body = _PR_BODY_TEMPLATE.format(
            incident_id=incident.id,
            error_type=incident.error_type,
            message=incident.message[:100],
            status_code=incident.status_code,
            error_class=routing.error_class,
            root_cause=fix_outcome.root_cause,
            test_file_path=test_file_path,
            test_content_preview=test_content[:800],
            files_changed=fix_outcome.files_changed,
            diff_lines=fix_outcome.diff_lines,
            verification_results=verification_summary,
            trace_link=trace_link or "N/A",
            cost_usd=cost_usd,
            iterations_used=fix_outcome.iterations_used,
        )

        pr_url, already_existed = client.create_draft_pr(
            branch=branch,
            title=title,
            body=body,
        )
        logger.info(
            "pr_agent_done incident_id=%s branch=%s pr_url=%s existing=%s",
            incident.id, branch, pr_url, already_existed,
        )
        return PRResult(pr_url=pr_url, branch=branch, already_existed=already_existed)
