"""hooks/wk_hook.py — the wk plugin's Claude Code hooks.

It runs on every Claude session the plugin is installed for, in any repo, so
the properties that matter are: silent no-op outside a wk worktree, never a
non-zero exit, and the right state/context inside one.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).parent.parent / "hooks" / "wk_hook.py"


def fire(payload: dict) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                          capture_output=True, text=True)


@pytest.fixture
def wt(tmp_path):
    root = tmp_path / "wt"
    (root / ".wk").mkdir(parents=True)
    (root / ".wk" / "AGENTS.md").write_text("x")
    (root / ".wk" / "task.md").write_text("## Goal\nship the thing\n")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "src").mkdir()
    return root


def test_session_start_injects_brief_from_subdir(wt):
    r = fire({"hook_event_name": "SessionStart", "source": "startup", "cwd": str(wt / "src")})
    assert r.returncode == 0
    assert "ship the thing" in r.stdout
    assert json.loads((wt / ".wk" / "status").read_text())["state"] == "waiting"


def test_resume_does_not_repeat_brief(wt):
    r = fire({"hook_event_name": "SessionStart", "source": "resume", "cwd": str(wt)})
    assert r.returncode == 0 and r.stdout == ""


@pytest.mark.parametrize("event,state", [
    ("UserPromptSubmit", "working"),
    ("Notification", "needs-input"),
    ("Stop", "waiting"),
    ("SessionEnd", "ended"),
])
def test_events_record_state(wt, event, state):
    assert fire({"hook_event_name": event, "cwd": str(wt), "session_id": "s"}).returncode == 0
    status = json.loads((wt / ".wk" / "status").read_text())
    assert status["state"] == state and status["session_id"] == "s"


def test_outside_wk_is_silent(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    r = fire({"hook_event_name": "SessionStart", "source": "startup", "cwd": str(tmp_path)})
    assert r.returncode == 0 and r.stdout == ""
    assert not (tmp_path / ".wk").exists()


def test_nested_repo_is_not_the_workspace(wt):
    inner = wt / "vendor" / "lib"
    inner.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(inner)], check=True)
    r = fire({"hook_event_name": "Stop", "cwd": str(inner)})
    assert r.returncode == 0
    assert not (wt / ".wk" / "status").exists()


def test_garbage_input_exits_zero():
    r = subprocess.run([sys.executable, str(HOOK)], input="not json",
                       capture_output=True, text=True)
    assert r.returncode == 0


def test_hooks_json_points_at_the_script():
    cfg = json.loads((HOOK.parent / "hooks.json").read_text())
    for event in ("SessionStart", "UserPromptSubmit", "Notification", "Stop", "SessionEnd"):
        cmd = cfg["hooks"][event][0]["hooks"][0]["command"]
        assert "${CLAUDE_PLUGIN_ROOT}/hooks/wk_hook.py" in cmd
