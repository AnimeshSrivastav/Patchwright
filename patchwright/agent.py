"""
Patchwright root agent — entry point for `adk run patchwright` and `adk web`.

The root_agent is the ADK-visible agent for this package.
The actual pipeline work (monitor, route, fix, PR) runs via autofix.pipeline.Pipeline
and autofix.monitor.log_poller.LogPoller.

To start the polling loop:
    python -m autofix

To interact via ADK web UI:
    adk web
"""
from __future__ import annotations

import os

from google.adk.agents.llm_agent import Agent

# Model comes from environment — never hard-coded
_MODEL = os.environ.get("MODEL", "gemini-2.0-flash")

root_agent = Agent(
    model=_MODEL,
    name="patchwright",
    description=(
        "Autonomous incident-fixing agent. "
        "Monitors application logs, classifies failures, fixes system errors, "
        "and opens draft PRs for human review."
    ),
    instruction=(
        "You are the Patchwright orchestrator. "
        "You help users understand the current state of incidents, routing decisions, "
        "and fix outcomes. "
        "The actual monitoring loop runs separately via `python -m autofix`. "
        "You can answer questions about incidents stored in the SQLite database."
    ),
)
