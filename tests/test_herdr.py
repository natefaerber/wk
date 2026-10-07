"""The herdr host: identity, layouts, agent launch, and task state.

herdr is driven over its socket API, so these fake `herdr_call` / the snapshot
and assert on the requests wk makes — the shapes herdr would reject (both
`tab_id` and `workspace_id` on `layout.apply`, an over-long agent name) are
exactly the bugs worth pinning.
"""

from __future__ import annotations

import json
import re

import pytest
import typer


@pytest.fixture
def calls(wk, monkeypatch):
    """Record herdr requests; reply with just enough for wk to proceed."""
    log: list[tuple[str, dict]] = []

    def fake(method, params=None, timeout=60.0):
        log.append((method, params or {}))
        if method == "workspace.create":
            return {"workspace": {"workspace_id": "w9"}, "tab": {"tab_id": "w9:t1"}}
        if method == "layout.apply":
            root = json.loads(json.dumps(params["root"]))
            for n, leaf in enumerate(_leaves(root)):
                leaf["pane_id"] = f"w9:p{n + 2}"
            return {"layout": {"root": root}}
        return {}

    monkeypatch.setattr(wk, "herdr_call", fake)
    return log


def _leaves(node):
    if node["type"] == "pane":
        return [node]
    return _leaves(node["first"]) + _leaves(node["second"])


# --------------------------------------------------------------------------- #
# Backend selection
# --------------------------------------------------------------------------- #

def test_backend_defaults_to_tmux(wk):
    assert wk.backend() == "tmux"


def test_backend_follows_herdr_when_inside_it(wk, monkeypatch):
    monkeypatch.setenv("HERDR_ENV", "1")
    monkeypatch.setenv("HERDR_WORKSPACE_ID", "w1")
    assert wk.backend() == "herdr"


def test_backend_env_overrides(wk, monkeypatch):
    monkeypatch.setenv("HERDR_ENV", "1")
    monkeypatch.setenv("HERDR_WORKSPACE_ID", "w1")
    monkeypatch.setenv("WK_BACKEND", "tmux")
    assert wk.backend() == "tmux"


def test_backend_rejects_unknown(wk, monkeypatch):
    monkeypatch.setenv("WK_BACKEND", "screen")
    with pytest.raises(typer.Exit):
        wk.backend()


# --------------------------------------------------------------------------- #
# Identity: label + `.wk/` marker
# --------------------------------------------------------------------------- #

def test_wk_workspace_needs_label_and_marker(wk, tmp_path):
    marked = tmp_path / "marked"
    (marked / ".wk").mkdir(parents=True)
    plain = tmp_path / "plain"
    plain.mkdir()
    snap = {
        "workspaces": [
            {"workspace_id": "w1", "label": "repo-feat-a"},
            {"workspace_id": "w2", "label": "repo-feat-b"},
            {"workspace_id": "w3", "label": ""},
        ],
        "panes": [
            {"workspace_id": "w1", "cwd": str(marked)},
            {"workspace_id": "w2", "cwd": str(plain)},
            {"workspace_id": "w3", "cwd": str(marked)},
        ],
    }
    assert set(wk.herdr_workspaces(snap)) == {"repo-feat-a", "repo-feat-b"}
    assert set(wk.herdr_wk_workspaces(snap)) == {"repo-feat-a"}


def test_kill_session_closes_herdr_workspace(wk, calls, monkeypatch):
    monkeypatch.setattr(wk, "herdr_workspaces",
                        lambda snap=None: {"s": wk.HerdrWorkspace("w4", "s", [])})
    wk.kill_session("s")
    assert calls == [("workspace.close", {"workspace_id": "w4"})]


# --------------------------------------------------------------------------- #
# Agent names: herdr accepts [a-z][a-z0-9_-]{0,31}
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("session", [
    "repo-feat-x",
    "9lives-main",
    "Some.Repo-feat-UPPER",
    "a-very-long-repository-name-feat-an-even-longer-branch-description",
])
def test_agent_name_is_valid(wk, session):
    assert re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", wk.herdr_agent_name(session))


def test_truncated_agent_names_dont_collide(wk):
    a = wk.herdr_agent_name("my-repository-feat-implement-the-thing-part-one")
    b = wk.herdr_agent_name("my-repository-feat-implement-the-thing-part-two")
    assert a != b


# --------------------------------------------------------------------------- #
# Layouts
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("profile,labels", [
    ("wide", ["claude", "work"]),
    ("laptop", ["claude", "work"]),
    ("minimal", ["claude", "work"]),
])
def test_every_leaf_gets_env_and_cwd(wk, tmp_path, profile, labels):
    env = {"WK_IN_WORKSPACE": "1"}
    leaves = _leaves(wk.herdr_layout_tree(profile, tmp_path, env))
    assert [leaf["label"] for leaf in leaves] == labels
    # herdr only hands a workspace's env to its first pane.
    assert all(leaf["env"] == env and leaf["cwd"] == str(tmp_path) for leaf in leaves)


def test_laptop_stacks_vertically(wk, tmp_path):
    assert wk.herdr_layout_tree("laptop", tmp_path, {})["direction"] == "down"


# --------------------------------------------------------------------------- #
# Claude conversation pinning
# --------------------------------------------------------------------------- #

@pytest.fixture
def claude_home(tmp_path, monkeypatch):
    home = tmp_path / "claude"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home))
    return home


def test_first_launch_records_a_session_id(wk, tmp_path, claude_home):
    wt = tmp_path / "wt"
    wt.mkdir()
    args = wk.claude_session_args(wt, "feat/x")
    sid = (wt / ".wk" / "session-id").read_text().strip()
    assert args == ["--session-id", sid, "-n", "feat/x"]


def test_reopen_resumes_recorded_conversation(wk, tmp_path, claude_home):
    wt = tmp_path / "wt"
    (wt / ".wk").mkdir(parents=True)
    (wt / ".wk" / "session-id").write_text("abc\n")
    transcript = wk._claude_transcript(wt, "abc")
    transcript.parent.mkdir(parents=True)
    transcript.write_text("{}\n")
    assert wk.claude_session_args(wt, "feat/x") == ["--resume", "abc", "-n", "feat/x"]


def test_pruned_transcript_starts_fresh(wk, tmp_path, claude_home):
    wt = tmp_path / "wt"
    (wt / ".wk").mkdir(parents=True)
    (wt / ".wk" / "session-id").write_text("gone\n")
    args = wk.claude_session_args(wt, "feat/x")
    assert args[0] == "--session-id" and args[1] != "gone"


def test_transcript_path_matches_claude_encoding(wk, tmp_path, claude_home):
    wt = tmp_path / "a_b.c" / "wt"
    wt.mkdir(parents=True)
    encoded = wk._claude_transcript(wt, "x").parent.name
    assert re.fullmatch(r"[A-Za-z0-9-]+", encoded)
    assert encoded.endswith("-a-b-c-wt")


# --------------------------------------------------------------------------- #
# Building a workspace
# --------------------------------------------------------------------------- #

def test_build_requests(wk, calls, tmp_path, claude_home, monkeypatch):
    monkeypatch.delenv("WK_AGENT_CMD", raising=False)
    wk.build_herdr_session("repo-feat-x", tmp_path, wk.DEFAULT_AGENT_CMD, "feat/x",
                           wk.LAYOUTS["minimal"], prompt="do it")
    methods = [m for m, _ in calls]
    assert methods[:3] == ["workspace.create", "layout.apply", "agent.start"]
    create, apply, start = (p for _, p in calls[:3])
    assert create["label"] == "repo-feat-x" and create["env"]["WK_BRANCH"] == "feat/x"
    # herdr refuses both targets at once.
    assert apply["tab_id"] == "w9:t1" and "workspace_id" not in apply
    assert start["kind"] == "claude" and start["pane_id"] == "w9:p2"
    assert start["args"][0] == "--session-id" and start["args"][-1] == "do it"


def test_custom_agent_runs_as_pane_command(wk, calls, tmp_path):
    wk.build_herdr_session("repo-feat-x", tmp_path, "aider", "feat/x", wk.LAYOUTS["minimal"])
    apply = next(p for m, p in calls if m == "layout.apply")
    assert "aider" in " ".join(apply["root"]["first"]["command"])
    assert not any(m == "agent.start" for m, _ in calls)


def test_blocked_agent_warns_and_keeps_workspace(wk, tmp_path, claude_home, monkeypatch):
    seen = []

    def fake(method, params=None, timeout=60.0):
        seen.append(method)
        if method == "agent.start":
            raise wk.HerdrError("agent_not_ready", "blocked during startup")
        return {}

    monkeypatch.setattr(wk, "herdr_call", fake)
    wk._herdr_start_claude("s", tmp_path, "feat/x", "w9:p2", None, fresh=False)
    assert seen == ["agent.start"]


# --------------------------------------------------------------------------- #
# Tasks
# --------------------------------------------------------------------------- #

def test_auto_task_refused_on_herdr(wk, monkeypatch):
    monkeypatch.setenv("WK_BACKEND", "herdr")
    monkeypatch.setattr(wk, "require", lambda tool: None)
    with pytest.raises(typer.Exit):
        wk.task("x", branch=None, base="origin/main", auto=True, yes=True,
                no_fetch=True, no_attach=True, layout=None)


def test_task_status_reads_meta_and_herdr_state(wk, tmp_path, monkeypatch):
    (tmp_path / ".wk").mkdir()
    wk._write_task_meta(tmp_path, "fix the flake", "repo-main")
    monkeypatch.setattr(wk, "_herdr_agent_status", lambda s: "blocked")
    w = wk.Workspace(branch="fix/x", path=tmp_path, session="repo-fix-x",
                     has_session=True, dirty=False, ahead=0, behind=0)
    st = wk._task_status(w)
    assert st.is_task and st.prompt_excerpt == "fix the flake"
    assert st.state == "blocked" and st.agent_status == "blocked"


def test_missing_tmux_degrades(wk, monkeypatch):
    # A herdr-only machine has no tmux; session probes must not crash.
    monkeypatch.setenv("PATH", "/nonexistent")
    assert wk.tmux_sessions() == set()
    assert wk.is_wk_session_name("anything") is False


# --------------------------------------------------------------------------- #
# Hook-reported state (`.wk/status`, written by hooks/wk_hook.py)
# --------------------------------------------------------------------------- #

def _ws(wk, path, alive=True):
    return wk.Workspace(branch="fix/x", path=path, session="repo-fix-x",
                        has_session=alive, dirty=False, ahead=0, behind=0)


@pytest.mark.parametrize("hook_state,expected", [
    ("working", "running"),
    ("waiting", "waiting"),
    ("needs-input", "blocked"),
    ("ended", "ended"),
])
def test_hook_status_drives_task_state(wk, tmp_path, monkeypatch, hook_state, expected):
    (tmp_path / ".wk").mkdir()
    wk._write_task_meta(tmp_path, "p", "")
    (tmp_path / ".wk" / "status").write_text(json.dumps({"state": hook_state}))
    monkeypatch.setattr(wk, "_herdr_agent_status", lambda s: "idle")
    assert wk._task_status(_ws(wk, tmp_path)).state == expected


def test_stale_hook_status_ignored_without_session(wk, tmp_path, monkeypatch):
    (tmp_path / ".wk").mkdir()
    wk._write_task_meta(tmp_path, "p", "")
    (tmp_path / ".wk" / "status").write_text(json.dumps({"state": "working"}))
    assert wk._task_status(_ws(wk, tmp_path, alive=False)).state == "idle"


def test_done_sentinel_outranks_hook_status(wk, tmp_path, monkeypatch):
    (tmp_path / ".wk").mkdir()
    (tmp_path / ".wk" / "done").touch()
    (tmp_path / ".wk" / "status").write_text(json.dumps({"state": "working"}))
    monkeypatch.setattr(wk, "_herdr_agent_status", lambda s: None)
    assert wk._task_status(_ws(wk, tmp_path)).state == "done"


@pytest.mark.parametrize("agent,label", [
    ("claude -c || claude", "claude"),
    ("aider --model x", "aider"),
    ("/opt/bin/codex", "codex"),
])
def test_agent_pane_label_names_the_program(wk, agent, label):
    assert wk.herdr_agent_label(agent) == label


def test_custom_agent_pane_is_labelled_by_program(wk, calls, tmp_path):
    wk.build_herdr_session("repo-feat-x", tmp_path, "aider", "feat/x", wk.LAYOUTS["wide"])
    apply = next(p for m, p in calls if m == "layout.apply")
    assert [leaf["label"] for leaf in _leaves(apply["root"])] == ["aider", "work"]


# --------------------------------------------------------------------------- #
# Sidebar metadata
# --------------------------------------------------------------------------- #

def test_build_posts_issue_key_to_sidebar(wk, calls, tmp_path, claude_home, monkeypatch):
    monkeypatch.setattr(wk, "issue_key_in_branch", lambda b: "LPE-1544")
    wk.build_herdr_session("repo-lpe-1544", tmp_path, "aider", "lpe-1544", wk.LAYOUTS["minimal"])
    meta = [p for m, p in calls if m == "workspace.report_metadata"]
    assert meta == [{"workspace_id": "w9", "source": "wk", "tokens": {"wk_issue": "LPE-1544"}}]


def test_no_issue_key_posts_nothing(wk, calls, tmp_path, monkeypatch):
    monkeypatch.setattr(wk, "issue_key_in_branch", lambda b: None)
    wk.build_herdr_session("repo-feat-x", tmp_path, "aider", "feat/x", wk.LAYOUTS["minimal"])
    assert not any(m == "workspace.report_metadata" for m, _ in calls)


def test_sidebar_failure_never_fails_the_build(wk, tmp_path, monkeypatch):
    monkeypatch.setattr(wk, "issue_key_in_branch", lambda b: "LPE-1")

    def fake(method, params=None, timeout=60.0):
        if method == "workspace.report_metadata":
            raise wk.HerdrError("bad", "nope")
        if method == "workspace.create":
            return {"workspace": {"workspace_id": "w9"}, "tab": {"tab_id": "w9:t1"}}
        if method == "layout.apply":
            return {"layout": {"root": {"first": {"pane_id": "w9:p2"}}}}
        return {}

    monkeypatch.setattr(wk, "herdr_call", fake)
    wk.build_herdr_session("repo-lpe-1", tmp_path, "aider", "lpe-1", wk.LAYOUTS["minimal"])
