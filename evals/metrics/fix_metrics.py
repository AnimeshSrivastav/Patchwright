from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FixMetricsReport:
    fix_success_rate: float
    cannot_reproduce_rate: float
    unclear_rate: float
    avg_iterations: float
    avg_cost_usd: float
    avg_wall_seconds: float
    n_fix_attempts: int


def fix_metrics_report(fix_outcomes: list[dict]) -> FixMetricsReport:
    """
    Compute fix success rate and cost/time metrics from a list of FixOutcome dicts.
    """
    n = len(fix_outcomes)
    if n == 0:
        return FixMetricsReport(0, 0, 0, 0, 0, 0, 0)

    fixed = sum(1 for o in fix_outcomes if o.get("status") == "fixed")
    cannot = sum(1 for o in fix_outcomes if o.get("status") == "cannot_reproduce")
    unclear = sum(1 for o in fix_outcomes if o.get("status") in ("unclear", "failed"))

    avg_iters = sum(o.get("iterations_used", 0) for o in fix_outcomes) / n
    avg_cost = sum(o.get("cost_usd", 0.0) for o in fix_outcomes) / n
    avg_wall = sum(o.get("wall_seconds", 0.0) for o in fix_outcomes) / n

    return FixMetricsReport(
        fix_success_rate=fixed / n,
        cannot_reproduce_rate=cannot / n,
        unclear_rate=unclear / n,
        avg_iterations=avg_iters,
        avg_cost_usd=avg_cost,
        avg_wall_seconds=avg_wall,
        n_fix_attempts=n,
    )


def format_fix_table(report: FixMetricsReport) -> str:
    return "\n".join([
        "## Fix Metrics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Fix success rate | {report.fix_success_rate:.1%} |",
        f"| Cannot reproduce rate | {report.cannot_reproduce_rate:.1%} |",
        f"| Unclear/failed rate | {report.unclear_rate:.1%} |",
        f"| Avg iterations | {report.avg_iterations:.1f} |",
        f"| Avg cost (USD) | ${report.avg_cost_usd:.4f} |",
        f"| Avg wall time (s) | {report.avg_wall_seconds:.1f}s |",
        f"| N fix attempts | {report.n_fix_attempts} |",
    ])
