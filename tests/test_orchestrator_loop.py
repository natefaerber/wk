"""Story B — close-the-orchestrator-loop: `task-merge --into/--rm` + done glyph."""

from __future__ import annotations

import subprocess

import pytest


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
# Done glyph — `.wk/done` presence drives ✓, and ✓ wins over session state.
# --------------------------------------------------------------------------- #

def test_task_done_and_done_glyph(wk, tmp_path):
    wkdir = tmp_path / wk.WK_MARKER_DIR
    wkdir.mkdir()
    w = _ws(wk, path=tmp_path, has_session=True)
    assert wk.task_done(w) is False
    assert wk.session_marker(w, "", rich=False) != wk.GLYPH_DONE

    (wkdir / wk._TASK_DONE_MARKER).touch()
    assert wk.task_done(w) is True
    # ✓ regardless of running/current state
    assert wk.session_marker(w, "", rich=False) == wk.GLYPH_DONE
    assert wk.session_marker(w, w.session, rich=False) == wk.GLYPH_DONE


# --------------------------------------------------------------------------- #
# task-merge --rm — branch deleted ONLY when ancestor-merged into the
# orchestrator branch (never a blind -D), worktree dropped either way.
# --------------------------------------------------------------------------- #

class _MergeRec:
    """run() mock: reports the task branch as merged-into-orch iff `merged`."""

    def __init__(self, merged: bool):
        self.calls: list[list[str]] = []
        self.merged = merged

    def __call__(self, cmd, *a, **k):
        self.calls.append(list(cmd))
        if "display-message" in cmd and "-p" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "repo-main", "")
        if "branch" in cmd and "--merged" in cmd:
            out = "feat/x\nmain\n" if self.merged else "main\n"
            return subprocess.CompletedProcess(cmd, 0, out, "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    def branch_deletes(self):
        return [c for c in self.calls if "branch" in c and ("-d" in c or "-D" in c)]


def _wire_merge(wk, monkeypatch, rec):
    orch = _ws(wk, branch="main", session="repo-main", path=wk.Path("/repo"))
    task = _ws(wk, branch="feat/x", session="repo-feat-x")
    monkeypatch.setattr(wk, "all_workspaces", lambda: [orch, task])
    monkeypatch.setattr(wk, "in_tmux", lambda: True)
    monkeypatch.setattr(wk, "repo_root", lambda: wk.Path("/repo"))
    monkeypatch.setattr(wk, "run", rec)


def test_task_merge_rm_force_deletes_when_merged(wk, monkeypatch):
    rec = _MergeRec(merged=True)
    _wire_merge(wk, monkeypatch, rec)
    wk.task_merge("feat/x", squash=False, ff_only=False, no_commit=False,
                  into=None, rm=True)
    dels = rec.branch_deletes()
    assert dels, "merged task should have its branch deleted"
    # verified-merged → safe force delete
    assert "-D" in dels[0]


def test_task_merge_rm_keeps_branch_when_not_merged(wk, monkeypatch):
    rec = _MergeRec(merged=False)
    _wire_merge(wk, monkeypatch, rec)
    wk.task_merge("feat/x", squash=False, ff_only=False, no_commit=False,
                  into=None, rm=True)
    # not ancestor-merged → never force-delete the branch ref (no data loss)
    assert all("-D" not in c for c in rec.branch_deletes())


def test_task_merge_rm_rejects_squash(wk, monkeypatch):
    import typer
    rec = _MergeRec(merged=True)
    _wire_merge(wk, monkeypatch, rec)
    with pytest.raises(typer.Exit):
        wk.task_merge("feat/x", squash=True, ff_only=False, no_commit=False,
                      into=None, rm=True)


def test_task_merge_into_resolves_orchestrator_without_tmux(wk, monkeypatch):
    # With --into, no current session is needed; orchestrator is resolved by query.
    rec = _MergeRec(merged=True)
    orch = _ws(wk, branch="main", session="repo-main", path=wk.Path("/repo"))
    task = _ws(wk, branch="feat/x", session="repo-feat-x")
    monkeypatch.setattr(wk, "all_workspaces", lambda: [orch, task])
    monkeypatch.setattr(wk, "in_tmux", lambda: False)  # not in a session
    monkeypatch.setattr(wk, "repo_root", lambda: wk.Path("/repo"))
    monkeypatch.setattr(wk, "run", rec)
    # Should NOT raise (no #S needed) and should run a merge into /repo.
    wk.task_merge("feat/x", squash=False, ff_only=False, no_commit=False,
                  into="main", rm=False)
    assert any("merge" in c for c in rec.calls), "expected a git merge call"
