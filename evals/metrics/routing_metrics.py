from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


@dataclass
class RoutingReport:
    accuracy: float
    false_fix_rate: float  # headline metric: predicted fixer but should not be
    per_class: dict[str, dict[str, float]]  # class -> {precision, recall, f1}
    calibration: dict[str, dict[str, float]]  # bucket -> {accuracy, count}
    confusion_matrix: dict[str, dict[str, int]]
    n_samples: int
    failures: list[dict]


def routing_report(
    predictions: list[str],
    labels: list[str],
    confidences: list[float] | None = None,
) -> RoutingReport:
    """
    Compute routing accuracy, per-class P/R/F1, false-fix rate, and calibration.

    Args:
        predictions: list of predicted routes ("fixer"|"reporter"|"ignore")
        labels: list of ground-truth routes
        confidences: optional list of router confidence scores for calibration
    """
    assert len(predictions) == len(labels), "predictions and labels must be same length"
    n = len(predictions)
    classes = ["fixer", "reporter", "ignore"]

    # Accuracy
    correct = sum(p == l for p, l in zip(predictions, labels))
    accuracy = correct / n if n > 0 else 0.0

    # False-fix rate: predicted "fixer" when label is NOT "fixer"
    false_fixes = sum(
        1 for p, l in zip(predictions, labels) if p == "fixer" and l != "fixer"
    )
    total_fixer_predictions = sum(1 for p in predictions if p == "fixer")
    false_fix_rate = false_fixes / total_fixer_predictions if total_fixer_predictions > 0 else 0.0

    # Per-class precision, recall, F1
    per_class: dict[str, dict[str, float]] = {}
    for cls in classes:
        tp = sum(1 for p, l in zip(predictions, labels) if p == cls and l == cls)
        fp = sum(1 for p, l in zip(predictions, labels) if p == cls and l != cls)
        fn = sum(1 for p, l in zip(predictions, labels) if p != cls and l == cls)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
        per_class[cls] = {"precision": precision, "recall": recall, "f1": f1}

    # Confusion matrix
    confusion: dict[str, dict[str, int]] = {c: {c2: 0 for c2 in classes} for c in classes}
    for pred, label in zip(predictions, labels):
        if pred in confusion and label in confusion:
            confusion[label][pred] += 1

    # Calibration by confidence bucket
    calibration: dict[str, dict[str, float]] = {}
    if confidences:
        buckets = [(0.0, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01)]
        for lo, hi in buckets:
            bucket_key = f"{lo:.1f}-{hi:.1f}"
            indices = [i for i, c in enumerate(confidences) if lo <= c < hi]
            if indices:
                bucket_correct = sum(
                    1 for i in indices if predictions[i] == labels[i]
                )
                calibration[bucket_key] = {
                    "accuracy": bucket_correct / len(indices),
                    "count": float(len(indices)),
                }

    # Failure analysis
    failures = [
        {
            "index": i,
            "predicted": predictions[i],
            "expected": labels[i],
            "confidence": confidences[i] if confidences else None,
        }
        for i in range(n)
        if predictions[i] != labels[i]
    ]

    return RoutingReport(
        accuracy=accuracy,
        false_fix_rate=false_fix_rate,
        per_class=per_class,
        calibration=calibration,
        confusion_matrix=confusion,
        n_samples=n,
        failures=failures,
    )


def format_routing_table(report: RoutingReport) -> str:
    lines = [
        "## Routing Metrics",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Accuracy | {report.accuracy:.1%} |",
        f"| False-fix rate (headline) | {report.false_fix_rate:.1%} |",
        f"| N samples | {report.n_samples} |",
        "",
        "### Per-Class Metrics",
        "",
        "| Class | Precision | Recall | F1 |",
        "|-------|-----------|--------|----|",
    ]
    for cls, m in report.per_class.items():
        lines.append(
            f"| {cls} | {m['precision']:.1%} | {m['recall']:.1%} | {m['f1']:.1%} |"
        )
    if report.calibration:
        lines += [
            "",
            "### Calibration",
            "",
            "| Confidence Bucket | Accuracy | Count |",
            "|-------------------|----------|-------|",
        ]
        for bucket, m in report.calibration.items():
            lines.append(f"| {bucket} | {m['accuracy']:.1%} | {int(m['count'])} |")
    return "\n".join(lines)
