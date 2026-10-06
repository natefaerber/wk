#!/usr/bin/env python3
"""Claude Code hooks for wk workspaces (shipped by the wk plugin).

Two jobs, both no-ops outside a wk worktree:

- SessionStart: hand the agent its handoff brief (`.wk/task.md`) as context,
  so it doesn't depend on the agent choosing to read `.wk/AGENTS.md`.
- Every lifecycle event: record the agent's state in `.wk/status`, the
  durable signal `wk task-status` reads. A terminal host's view of the agent
  (herdr's "done", a tmux pane's process) can't tell "finished the task"
  from "finished a turn", and is gone once the session closes; this file is
  neither.

Stdlib only, and quiet on any failure: a hook must never block or break a
Claude session.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Claude Code event -> the state an orchestrator cares about.
STATES = {
    "SessionStart": "waiting",
    "UserPromptSubmit": "working",
    "Notification": "needs-input",
    "Stop": "waiting",
    "SessionEnd": "ended",
}

# A resumed conversation already holds its brief; re-sending it would just
# duplicate context. Fresh starts, /clear and compaction need it again.
BRIEF_SOURCES = {"startup", "clear", "compact"}


def workspace_root(cwd: str) -> Path | None:
    """The wk worktree containing CWD, or None. Stops at the first git
    boundary so a repo nested inside a wk worktree isn't mistaken for it."""
    try:
        here = Path(cwd).resolve()
    except OSError:
        return None
    for d in (here, *here.parents):
        if (d / ".wk" / "AGENTS.md").is_file():
            return d
        if (d / ".git").exists():
            return None
    return None


def write_status(root: Path, event: str, payload: dict) -> None:
    status = {
        "state": STATES[event],
        "event": event,
        "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "session_id": payload.get("session_id"),
    }
    if event == "Notification" and payload.get("message"):
        status["message"] = str(payload["message"])[:200]
    target = root / ".wk" / "status"
    tmp = target.with_name(f".status.{os.getpid()}")
    tmp.write_text(json.dumps(status) + "\n", encoding="utf-8")
    os.replace(tmp, target)  # readers never see a half-written file


def brief_context(root: Path) -> str:
    branch = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True,
    ).stdout.strip() or "?"
    lines = [
        f"You are in a wk workspace: branch `{branch}`, worktree {root}. "
        "`.wk/AGENTS.md` lists the wk commands available here."
    ]
    try:
        brief = (root / ".wk" / "task.md").read_text(encoding="utf-8").strip()
    except OSError:
        brief = ""
    if brief:
        lines.append("Handoff brief for this workspace (`.wk/task.md`; you may update it as you go):")
        lines.append(brief)
    return "\n\n".join(lines)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    event = payload.get("hook_event_name", "")
    if event not in STATES:
        return 0
    root = workspace_root(payload.get("cwd") or os.getcwd())
    if root is None:
        return 0
    write_status(root, event, payload)
    if event == "SessionStart" and payload.get("source", "startup") in BRIEF_SOURCES:
        sys.stdout.write(brief_context(root) + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
