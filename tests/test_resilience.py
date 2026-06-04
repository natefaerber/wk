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
