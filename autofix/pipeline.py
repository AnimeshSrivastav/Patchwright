from __future__ import annotations

import logging
import time
from pathlib import Path

from autofix.agents.fixer import FixerAgent
from autofix.agents.pr_agent import PRAgent, PRResult
from autofix.agents.reproducer import ReproducerAgent
from autofix.agents.reporter import ReporterAgent
from autofix.agents.verifier import Verifier
from autofix.config.settings import Settings
from autofix.gitops.git_client import GitClient
from autofix.models.schemas import FixOutcome, Incident, RoutingDecision
from autofix.observability.logging import bind_incident, clear_incident
from autofix.observability.tracing import span, get_incident_cost
from autofix.routing.base import RepoContext
from autofix.routing.llm_router import LLMRouter
from autofix.routing.jev_router import JevRouter
from autofix.routing.rules import apply_hard_rules
from autofix.sandbox.docker_runner import DockerSandbox
from autofix.storage.db import transition, upsert_incident, get_open_by_fingerprint, increment_occurrence

logger = logging.getLogger(__name__)


def build_router(settings: Settings):
    mock = settings.mock_external
    if settings.router == "jev":
        return JevRouter()
    return LLMRouter(model=settings.model, mock=mock)


class Pipeline:
    """
    Orchestrates the full incident lifecycle for a single incident.
    Resumable: re-running with the same incident_id is idempotent.

    Lifecycle:
        detected -> routed -> (ignored | reported | fixing -> pr_opened | failed) -> closed
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.mock = settings.mock_external
        self.router = build_router(settings)
        self.reproducer = ReproducerAgent(model=settings.model, mock=self.mock)
        self.fixer = FixerAgent(model=settings.model, mock=self.mock)
        self.verifier = Verifier(
            max_diff_lines=settings.max_diff_lines,
            max_files_changed=settings.max_files_changed,
        )
        self.reporter = ReporterAgent(model=settings.model, mock=self.mock)
        self.pr_agent = PRAgent(
            github_repo=settings.github_repo,
            github_token=settings.github_token,
            mock=self.mock,
        )
        self.git_client = GitClient(
            repo_url=f"https://github.com/{settings.github_repo}",
            token=settings.github_token,
            mock=self.mock,
        )

    def run(self, incident: Incident) -> None:
        bind_incident(incident.id, incident.id[:8], "pipeline")
        logger.info("pipeline_start incident_id=%s fingerprint=%s", incident.id, incident.fingerprint)

        # Dedup check
        existing = get_open_by_fingerprint(incident.fingerprint)
        if existing and existing.id != incident.id:
            increment_occurrence(existing.id)
            logger.info("pipeline_duplicate incident_id=%s existing_id=%s", incident.id, existing.id)
            clear_incident()
            return

        upsert_incident(incident)
        start_time = time.time()

        try:
            with span("incident_pipeline", incident_id=incident.id):
                self._run_pipeline(incident, start_time)
        except Exception as e:
            logger.error("pipeline_unhandled_error incident_id=%s error=%s", incident.id, e)
            transition(incident.id, "failed")
        finally:
            clear_incident()

    def _run_pipeline(self, incident: Incident, start_time: float) -> None:
        s = self.settings

        # --- Route ---
        with span("routing", incident_id=incident.id):
            repo_context = RepoContext(
                repo_path=f"https://github.com/{s.github_repo}",
                recent_files=[],
            )
            routing = self.router.route(incident, repo_context)
            routing = apply_hard_rules(incident, routing, s.confidence_threshold)

        incident.route = routing.next_agent  # type: ignore[assignment]
        transition(incident.id, "routed")
        upsert_incident(incident)
        logger.info(
            "pipeline_routed incident_id=%s next=%s confidence=%.2f",
            incident.id, routing.next_agent, routing.confidence,
        )

        if routing.next_agent == "ignore":
            transition(incident.id, "ignored")
            return

        if routing.next_agent == "reporter":
            self._run_reporter(incident, routing)
            return

        # --- Fixer path ---
        self._run_fixer(incident, routing, start_time)

    def _run_reporter(self, incident: Incident, routing: RoutingDecision) -> None:
        with span("reporter", incident_id=incident.id):
            report = self.reporter.report(incident, routing)
        logger.info("pipeline_reported incident_id=%s summary=%s", incident.id, report.get("summary", ""))
        transition(incident.id, "reported")

    def _run_fixer(
        self, incident: Incident, routing: RoutingDecision, start_time: float
    ) -> None:
        s = self.settings
        transition(incident.id, "fixing")

        # Clone and create branch
        with span("git_setup", incident_id=incident.id):
            clone_path = self.git_client.clone()
            branch = self.git_client.create_branch(incident.id)

        # Start sandbox
        with DockerSandbox(repo_path=clone_path, mock=self.mock) as sandbox:
            # Reproduce
            with span("reproducer", incident_id=incident.id):
                repro = self.reproducer.reproduce(incident, sandbox, routing.suspected_files)

            if not repro.success:
                logger.warning("pipeline_cannot_reproduce incident_id=%s", incident.id)
                self._run_reporter(
                    incident,
                    routing,
                    fix_outcome=FixOutcome(
                        incident_id=incident.id, reproduced=False, root_cause="",
                        branch=branch, tests_pass=False, regression_test_added=False,
                        diff_lines=0, files_changed=0, status="cannot_reproduce",
                        iterations_used=0,
                    ),
                )
                return

            # Fixer loop (max 3 iterations — plain Python, not LoopAgent)
            fix_outcome: FixOutcome | None = None
            patch_result = None
            for iteration in range(1, s.max_iterations + 1):
                # Safety caps
                elapsed = time.time() - start_time
                if elapsed > s.max_wall_seconds:
                    logger.error("pipeline_wall_time_exceeded incident_id=%s elapsed=%.0f", incident.id, elapsed)
                    transition(incident.id, "failed")
                    return
                cost = get_incident_cost(incident.id)
                if cost > s.max_usd:
                    logger.error("pipeline_cost_exceeded incident_id=%s cost=%.4f", incident.id, cost)
                    transition(incident.id, "failed")
                    return

                with span(f"fixer_iteration_{iteration}", incident_id=incident.id):
                    patch_result = self.fixer.fix(
                        incident=incident,
                        sandbox=sandbox,
                        test_file_path=repro.test_file_path,
                        test_content=repro.test_content,
                        target_function=repro.target_function,
                        root_cause_hint=repro.expected_fix_hint,
                        iteration=iteration,
                    )

                if not patch_result.success:
                    logger.warning(
                        "pipeline_fixer_error incident_id=%s iter=%d", incident.id, iteration
                    )
                    continue

                # Apply patch to sandbox
                sandbox.write_file(patch_result.file_path, patch_result.patch_content)

                # Verify
                diff_lines, patched_files = self.git_client.get_diff_stats()
                verify_result = self.verifier.verify(
                    sandbox=sandbox,
                    test_file_path=repro.test_file_path,
                    patched_files=patched_files,
                    diff_lines=diff_lines,
                    test_failed_before=True,
                )

                if verify_result.passed:
                    fix_outcome = FixOutcome(
                        incident_id=incident.id,
                        reproduced=True,
                        root_cause=patch_result.root_cause,
                        branch=branch,
                        tests_pass=True,
                        regression_test_added=True,
                        diff_lines=diff_lines,
                        files_changed=len(patched_files),
                        status="fixed",
                        iterations_used=iteration,
                        reproducing_test_failed_before=True,
                    )
                    logger.info("pipeline_fix_verified incident_id=%s iter=%d", incident.id, iteration)
                    break
                else:
                    logger.warning(
                        "pipeline_verify_failed incident_id=%s iter=%d reason=%s",
                        incident.id, iteration, verify_result.failure_reason,
                    )

            if fix_outcome is None or fix_outcome.status != "fixed":
                logger.warning("pipeline_fix_failed incident_id=%s", incident.id)
                self._run_reporter(
                    incident,
                    routing,
                    fix_outcome=FixOutcome(
                        incident_id=incident.id, reproduced=True, root_cause="",
                        branch=branch, tests_pass=False, regression_test_added=False,
                        diff_lines=0, files_changed=0, status="unclear",
                        iterations_used=s.max_iterations,
                    ),
                )
                return

            # Commit and push
            with span("git_push", incident_id=incident.id):
                self.git_client.commit_patch(
                    patch_result.file_path,
                    patch_result.patch_content,
                    f"fix({incident.id[:8]}): {patch_result.root_cause[:72]}",
                )
                self.git_client.push_branch(branch)

            # Open draft PR
            with span("pr_creation", incident_id=incident.id):
                pr_result = self.pr_agent.create_pr(
                    incident=incident,
                    routing=routing,
                    fix_outcome=fix_outcome,
                    test_file_path=repro.test_file_path,
                    test_content=repro.test_content,
                    verification_summary=str(self.verifier),
                    trace_link=f"incident:{incident.id}",
                    cost_usd=get_incident_cost(incident.id),
                )

            transition(incident.id, "pr_opened")
            logger.info("pipeline_pr_opened incident_id=%s pr_url=%s", incident.id, pr_result.pr_url)

        self.git_client.cleanup()

    def _run_reporter(
        self,
        incident: Incident,
        routing: RoutingDecision,
        fix_outcome: FixOutcome | None = None,
    ) -> None:
        with span("reporter", incident_id=incident.id):
            self.reporter.report(incident, routing, fix_outcome)
        transition(incident.id, "reported")
