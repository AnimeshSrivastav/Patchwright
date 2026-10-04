from __future__ import annotations

import re

# Patterns that must never reach a model or be stored unredacted
_PATTERNS: list[tuple[str, str]] = [
    # Bearer / API tokens
    (r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", "Bearer [REDACTED]"),
    # Generic key=value secrets
    (r'(?i)(api_?key|token|secret|password|passwd|pwd)\s*[:=]\s*\S+', r'\1=[REDACTED]'),
    # Authorization headers
    (r'(?i)(Authorization|X-Api-Key)\s*:\s*\S+', r'\1: [REDACTED]'),
    # IPv4
    (r'\b(?:\d{1,3}\.){3}\d{1,3}\b', "[IP]"),
    # Email addresses
    (r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b', "[EMAIL]"),
    # UUIDs
    (r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b', "[UUID]"),
    # Credit card numbers (16 digits, spaced or not)
    (r'\b(?:\d[ -]?){13,16}\b', "[CARD]"),
    # AWS keys
    (r'AKIA[0-9A-Z]{16}', "[AWS_KEY]"),
    # Google API keys
    (r'AIza[0-9A-Za-z\-_]{35}', "[GOOGLE_KEY]"),
    # JWT tokens
    (r'eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]*', "[JWT]"),
]

_COMPILED = [(re.compile(p), r) for p, r in _PATTERNS]


def redact(text: str) -> str:
    """Scrub all known secret/PII patterns from text. Returns safe string."""
    for pattern, replacement in _COMPILED:
        text = pattern.sub(replacement, text)
    return text


def redact_dict(data: dict) -> dict:
    """Recursively redact all string values in a dict."""
    result: dict = {}
    for k, v in data.items():
        if isinstance(v, str):
            result[k] = redact(v)
        elif isinstance(v, dict):
            result[k] = redact_dict(v)
        elif isinstance(v, list):
            result[k] = [redact(i) if isinstance(i, str) else i for i in v]
        else:
            result[k] = v
    return result
