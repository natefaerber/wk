"""Regression tests for the Tier-1 resilience / data-loss fixes."""

from __future__ import annotations

import subprocess

import pytest


class RunRecorder:
    """Records every wk.run(...) call and returns a CompletedProcess.

    `fail_match` → a substring; any command containing it (joined) returns
    `fail_rc`. Everything else returns rc 0.
    """

    def __init__(self, fail_match: str | None = None, fail_rc: int = 1):
        self.calls: list[list[str]] = []
        self.fail_match = fail_match
        self.fail_rc = fail_rc

    def __call__(self, cmd, *args, **kwargs):
        self.calls.append(list(cmd))
        joined = " ".join(str(c) for c in cmd)
        rc = self.fail_rc if (self.fail_match and self.fail_match in joined) else 0
        return subprocess.CompletedProcess(cmd, rc, "", "")

    def branch_cmds(self):
        return [c for c in self.calls if "branch" in c]


def _ws(wk, **over):
    base = dict(
        branch="feat/x",
        path=wk.Path("/repo/.worktrees/feat-x"),
        session="repo-feat-x",
        has_session=False,
        dirty=False,
        ahead=0,
        behind=0,
    )
    base.update(over)
    return wk.Workspace(**base)


# --------------------------------------------------------------------------- #
# _do_rm — branch ref must not be force-deleted unless --force, and a failed
# worktree removal must abort before touching the branch.
# --------------------------------------------------------------------------- #

def test_do_rm_uses_safe_branch_delete_without_force(wk, monkeypatch):
    rec = RunRecorder()
    monkeypatch.setattr(wk, "run", rec)
    wk._do_rm(_ws(wk), wk.Path("/repo"), force=False, keep_branch=False)
    branch = rec.branch_cmds()
    assert branch, "expected a branch-delete call"
    # safe delete: -d (refuses unmerged), never -D
    assert "-d" in branch[0] and "-D" not in branch[0]


def test_do_rm_force_uses_force_branch_delete(wk, monkeypatch):
    rec = RunRecorder()
    monkeypatch.setattr(wk, "run", rec)
    wk._do_rm(_ws(wk), wk.Path("/repo"), force=True, keep_branch=False)
    assert "-D" in rec.branch_cmds()[0]


def test_do_rm_keep_branch_skips_branch_delete(wk, monkeypatch):
    rec = RunRecorder()
    monkeypatch.setattr(wk, "run", rec)
    wk._do_rm(_ws(wk), wk.Path("/repo"), force=False, keep_branch=True)
    assert rec.branch_cmds() == []


def test_do_rm_aborts_branch_delete_when_worktree_removal_fails(wk, monkeypatch):
    # If `git worktree remove` fails, we must NOT go on to delete the branch ref
    # (that would orphan a still-present worktree).
    rec = RunRecorder(fail_match="worktree remove")
    monkeypatch.setattr(wk, "run", rec)
    wk._do_rm(_ws(wk), wk.Path("/repo"), force=False, keep_branch=False)
    assert rec.branch_cmds() == [], "branch must be untouched when worktree removal fails"


# --------------------------------------------------------------------------- #
# list_worktrees / find_existing_worktree — tolerate git failure instead of
# raising (would crash wk ls / switch / rm / the render loops).
# --------------------------------------------------------------------------- #

def test_list_worktrees_returns_empty_on_git_failure(wk, monkeypatch):
    monkeypatch.setattr(wk, "run", RunRecorder(fail_match="worktree list", fail_rc=128))
    assert wk.list_worktrees() == []


def test_find_existing_worktree_returns_none_on_git_failure(wk, monkeypatch):
    monkeypatch.setattr(wk, "run", RunRecorder(fail_match="worktree list", fail_rc=128))
    assert wk.find_existing_worktree("anything") is None


# --------------------------------------------------------------------------- #
# _task_status — "done" keys off the .wk/done sentinel FILE, not a string in
# the task's own output (which could be spoofed by the task echoing it).
# --------------------------------------------------------------------------- #

def test_task_status_done_requires_sentinel_file(wk, tmp_path, monkeypatch):
    # rc=1 for every run() so the tmux show-options probes are inert.
    monkeypatch.setattr(wk, "run", RunRecorder(fail_match="", fail_rc=1))
    wkdir = tmp_path / wk.WK_MARKER_DIR
    wkdir.mkdir()
    # Output literally contains the old completion marker string but there's no
    # sentinel file → must NOT be reported done.
    (wkdir / "output.md").write_text("working...\n── task complete ──\n", encoding="utf-8")
    w = _ws(wk, path=tmp_path, has_session=True)
    assert wk._task_status(w).state == "running"

    # Drop the sentinel → done.
    (wkdir / wk._TASK_DONE_MARKER).touch()
    assert wk._task_status(w).state == "done"


def test_task_status_failed_when_session_gone_without_sentinel(wk, tmp_path, monkeypatch):
    monkeypatch.setattr(wk, "run", RunRecorder(fail_match="", fail_rc=1))
    wkdir = tmp_path / wk.WK_MARKER_DIR
    wkdir.mkdir()
    (wkdir / "output.md").write_text("partial output\n", encoding="utf-8")
    w = _ws(wk, path=tmp_path, has_session=False)
    assert wk._task_status(w).state == "failed"


# --------------------------------------------------------------------------- #
# find_workspace / require_workspace — the shared lookup helpers.
# --------------------------------------------------------------------------- #

def test_find_and_require_workspace(wk):
    import typer

    a = _ws(wk, branch="feat/login", session="r-feat-login")
    b = _ws(wk, branch="main", session="r-main")
    ws = [a, b]
    assert wk.find_workspace("feat-login", ws) is a   # session-form slug
    assert wk.find_workspace("feat/login", ws) is a   # real branch
    assert wk.find_workspace("main", ws) is b
    assert wk.find_workspace("nope", ws) is None
    assert wk.require_workspace("feat/login", ws) is a
    with pytest.raises(typer.Exit):
        wk.require_workspace("nope", ws)


# --------------------------------------------------------------------------- #
# list outside a git repo must say so, not "no workspaces" (the resilience
# fallbacks return [] for both "no repo" and "empty repo").
# --------------------------------------------------------------------------- #

def test_list_outside_repo_says_not_a_repo(wk, monkeypatch):
    import typer
    monkeypatch.setattr(wk, "require", lambda *a, **k: None)
    monkeypatch.setattr(wk, "in_git_repo", lambda: False)
    with pytest.raises(typer.Exit):
        wk.list_cmd()


def test_list_in_repo_with_no_workspaces_does_not_raise(wk, monkeypatch):
    monkeypatch.setattr(wk, "require", lambda *a, **k: None)
    monkeypatch.setattr(wk, "in_git_repo", lambda: True)
    monkeypatch.setattr(wk, "all_workspaces", lambda: [])
    wk.list_cmd()  # prints "no workspaces", returns cleanly
