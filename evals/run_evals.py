"""
Evaluation harness for Patchwright.

Usage:
    python evals/run_evals.py [--mock] [--dataset evals/datasets/labelled_logs.jsonl]

Outputs:
    evals/reports/results_<timestamp>.md
    evals/reports/failures_<timestamp>.md
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import datetime
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from autofix.config.settings import Settings
from autofix.models.schemas import Incident
from autofix.routing.base import RepoContext
from autofix.routing.rules import apply_hard_rules
from evals.metrics.routing_metrics import routing_report, format_routing_table
from evals.metrics.fix_metrics import fix_metrics_report, format_fix_table
from evals.metrics.deepeval_metrics import format_deepeval_table

_REPORTS_DIR = Path(__file__).parent / "reports"
_REPORTS_DIR.mkdir(exist_ok=True)


def load_labelled_logs(path: str) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def build_mock_incident(entry: dict) -> Incident:
    import uuid
    from datetime import timezone
    return Incident(
        id=str(uuid.uuid4()),
        fingerprint=entry["id"],
        timestamp=datetime.datetime.now(timezone.utc),
        status_code=entry["status_code"],
        error_type=entry["error_type"],
        message=entry["message"],
        stack_trace=entry.get("stack_trace", ""),
        redacted_excerpt=f"{entry.get('method','GET')} {entry.get('path','')} -> {entry['status_code']}",
        occurrence_count=1,
        status="detected",
    )


def run_routing_eval(
    entries: list[dict],
    mock: bool = True,
) -> tuple[list[str], list[str], list[float]]:
    """
    Run routing on each labelled log entry.
    Returns (predictions, labels, confidences).
    """
    from autofix.routing.llm_router import LLMRouter

    # Always use MOCK_EXTERNAL=1 for cheap eval runs
    settings = Settings(APP_LOG_URL="http://localhost:8001/logs")
    router = LLMRouter(model=settings.model, mock=mock)
    repo_ctx = RepoContext(repo_path=".", recent_files=[])

    predictions, labels, confidences = [], [], []
    for entry in entries:
        incident = build_mock_incident(entry)
        decision = router.route(incident, repo_ctx)
        decision = apply_hard_rules(incident, decision, settings.confidence_threshold)
        predictions.append(decision.next_agent)
        labels.append(entry["expected_route"])
        confidences.append(decision.confidence)

    return predictions, labels, confidences


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Patchwright evaluation suite")
    parser.add_argument("--mock", action="store_true", default=True,
                        help="Use mock router (no real API calls)")
    parser.add_argument("--no-mock", action="store_false", dest="mock",
                        help="Use real LLM router (requires API key)")
    parser.add_argument("--dataset", default="evals/datasets/labelled_logs.jsonl")
    args = parser.parse_args()

    print(f"Loading dataset: {args.dataset}")
    entries = load_labelled_logs(args.dataset)
    print(f"Loaded {len(entries)} labelled log entries")

    print(f"Running routing eval (mock={args.mock})...")
    predictions, labels, confidences = run_routing_eval(entries, mock=args.mock)

    routing_rpt = routing_report(predictions, labels, confidences)
    print(f"Routing accuracy: {routing_rpt.accuracy:.1%}")
    print(f"False-fix rate:   {routing_rpt.false_fix_rate:.1%}")

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    # Write results report
    results_path = _REPORTS_DIR / f"results_{timestamp}.md"
    results_content = "\n\n".join([
        f"# Patchwright Eval Results — {timestamp}",
        f"**Dataset:** {args.dataset}  \n**Mock:** {args.mock}",
        format_routing_table(routing_rpt),
        format_fix_table(fix_metrics_report([])),  # fix outcomes from real runs
        format_deepeval_table([], []),
    ])
    results_path.write_text(results_content, encoding="utf-8")
    print(f"\nResults written to: {results_path}")

    # Write failure analysis
    if routing_rpt.failures:
        failures_path = _REPORTS_DIR / f"failures_{timestamp}.md"
        lines = [
            f"# Routing Failures — {timestamp}",
            "",
            f"Total failures: {len(routing_rpt.failures)} / {routing_rpt.n_samples}",
            "",
            "| # | Entry ID | Predicted | Expected | Confidence |",
            "|---|----------|-----------|----------|------------|",
        ]
        for f in routing_rpt.failures:
            entry = entries[f["index"]]
            conf = f"{f['confidence']:.2f}" if f["confidence"] is not None else "N/A"
            lines.append(
                f"| {f['index']} | {entry.get('id','?')} | {f['predicted']} | "
                f"{f['expected']} | {conf} |"
            )
        failures_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"Failure analysis: {failures_path}")

    # Exit with non-zero if headline metrics exceed thresholds
    MAX_FALSE_FIX_RATE = 0.10   # 10% threshold
    MIN_ACCURACY = 0.75          # 75% minimum accuracy

    failed = False
    if routing_rpt.false_fix_rate > MAX_FALSE_FIX_RATE:
        print(f"\nCRITICAL: false-fix rate {routing_rpt.false_fix_rate:.1%} exceeds {MAX_FALSE_FIX_RATE:.0%} threshold!")
        failed = True
    if routing_rpt.accuracy < MIN_ACCURACY:
        print(f"CRITICAL: routing accuracy {routing_rpt.accuracy:.1%} below {MIN_ACCURACY:.0%} threshold!")
        failed = True

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
