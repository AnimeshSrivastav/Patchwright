"""
Secondary LLM-judged metrics using DeepEval.
These are informational only — they never override programmatic results.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def run_root_cause_quality(
    incident_messages: list[str],
    root_causes: list[str],
) -> list[float]:
    """
    GEval metric: score quality of root-cause explanations (0.0 - 1.0).
    Returns list of scores, one per example.
    """
    try:
        from deepeval import evaluate  # type: ignore[import-untyped]
        from deepeval.metrics import GEval  # type: ignore[import-untyped]
        from deepeval.test_case import LLMTestCase  # type: ignore[import-untyped]
        from deepeval.metrics import GEvalCriteria  # type: ignore[import-untyped]

        metric = GEval(
            name="RootCauseQuality",
            criteria=(
                "Is the root cause explanation accurate, specific, and actionable? "
                "Does it correctly identify the failing code location and describe the fix needed?"
            ),
            evaluation_params=["input", "actual_output"],
        )
        scores = []
        for msg, root_cause in zip(incident_messages, root_causes):
            test_case = LLMTestCase(input=msg, actual_output=root_cause)
            metric.measure(test_case)
            scores.append(metric.score)
        return scores
    except Exception as e:
        logger.warning("deepeval_root_cause_error error=%s", e)
        return [0.0] * len(incident_messages)


def run_task_completion(
    tasks: list[str],
    outcomes: list[str],
) -> list[float]:
    """
    TaskCompletionMetric: did the agent complete the assigned task?
    """
    try:
        from deepeval.metrics import TaskCompletionMetric  # type: ignore[import-untyped]
        from deepeval.test_case import LLMTestCase  # type: ignore[import-untyped]

        metric = TaskCompletionMetric()
        scores = []
        for task, outcome in zip(tasks, outcomes):
            test_case = LLMTestCase(input=task, actual_output=outcome)
            metric.measure(test_case)
            scores.append(metric.score)
        return scores
    except Exception as e:
        logger.warning("deepeval_task_completion_error error=%s", e)
        return [0.0] * len(tasks)


def format_deepeval_table(
    root_cause_scores: list[float],
    task_scores: list[float],
) -> str:
    if not root_cause_scores and not task_scores:
        return "## DeepEval Metrics\n\n*(No data — DeepEval metrics skipped)*"

    avg_rc = sum(root_cause_scores) / len(root_cause_scores) if root_cause_scores else 0.0
    avg_task = sum(task_scores) / len(task_scores) if task_scores else 0.0

    return "\n".join([
        "## DeepEval Metrics (secondary, LLM-judged)",
        "",
        "> Note: These metrics are informational only. They do NOT override programmatic results.",
        "",
        "| Metric | Average Score |",
        "|--------|---------------|",
        f"| Root cause quality (GEval) | {avg_rc:.2f} |",
        f"| Task completion | {avg_task:.2f} |",
    ])
