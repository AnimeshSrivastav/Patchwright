from __future__ import annotations

import hashlib
import re


# Normalize patterns — strip things that vary between occurrences of the same bug
# NOTE: do NOT strip short quoted strings (e.g. 'price', 'name') — those are part of
# the error identity and must distinguish different KeyErrors.
_NORMALIZE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?'), "TS"),  # timestamps first
    (re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.I), "UUID"),
    (re.compile(r'0x[0-9a-fA-F]+'), "ADDR"),
    (re.compile(r'\b\d+\b'), "N"),                          # plain numbers (after timestamps/UUIDs)
]


def _normalize(message: str) -> str:
    for pattern, replacement in _NORMALIZE_PATTERNS:
        message = pattern.sub(replacement, message)
    return message.strip()


def _top_in_repo_frames(stack_trace: str, max_frames: int = 3) -> str:
    """Extract top stack frames that look like project files (not site-packages)."""
    frames: list[str] = []
    for line in stack_trace.splitlines():
        line = line.strip()
        if line.startswith("File ") and "site-packages" not in line and ".venv" not in line:
            # Extract just filename:lineno to ignore absolute paths
            match = re.search(r'"([^"]+)", line (\d+)', line)
            if match:
                path = match.group(1)
                # Normalize to relative-style path
                parts = path.replace("\\", "/").split("/")
                short = "/".join(parts[-2:]) if len(parts) > 1 else path
                frames.append(short)  # file path only — line numbers vary for same bug
        if len(frames) >= max_frames:
            break
    return "|".join(frames)


def compute_fingerprint(error_type: str, message: str, stack_trace: str) -> str:
    """
    Stable fingerprint for an incident.
    hash(error_type + normalized_message + top_in_repo_frames)
    Identical bugs at different line numbers or with different IDs produce the same fingerprint.
    """
    normalized_msg = _normalize(message)
    frames = _top_in_repo_frames(stack_trace)
    raw = f"{error_type}::{normalized_msg}::{frames}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
