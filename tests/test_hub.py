"""Story A — the summoned hub (generalized `wk switch` picker)."""

from __future__ import annotations

import inspect


def _ws(wk, **over):
    base = dict(
        branch="feat/x",
        path=wk.Path("/repo/.worktrees/feat-x"),
        session="repo-feat-x",
        has_session=True,
        dirty=False,
        ahead=0,
        behind=0,
    )
    base.update(over)
    return wk.Workspace(**base)


def test_picker_line_format(wk):
    line = wk._picker_line(_ws(wk), "")
    sess, tab, display = line.partition("\t")
    assert tab == "\t" and sess == "repo-feat-x"
    assert "feat/x" in display  # branch shown in the display column


def test_picker_and_listonce_share_one_formatter(wk):
    # The live picker and its --reload source MUST emit identical rows or the
    # list visually jumps on reload. Both go through `_picker_line`.
    assert "_picker_line" in inspect.getsource(wk.switch)
    assert "_picker_line" in inspect.getsource(wk.list_once)


def test_hub_binds_have_no_blocking_commands(wk):
    # The hub does non-blocking verbs only. tail -f never returns; task-merge is
    # interactive and resolves #S wrong inside a popup — neither may be bound.
    binds = "\n".join(
        l for l in inspect.getsource(wk.switch).splitlines() if "--bind=" in l
    )
    for bad in ("tail", "--follow", "task-output", "task-merge"):
        assert bad not in binds, f"hub bind must not include blocking `{bad}`"
    # the non-blocking verbs we DO expect on the hub
    for good in ("ctrl-n", "ctrl-d", "ctrl-x", "ctrl-r"):
        assert good in binds


# --------------------------------------------------------------------------- #
# Global hub — external (cross-repo) running sessions, derived live from tmux.
# --------------------------------------------------------------------------- #
import subprocess  # noqa: E402


def test_repo_label_fast_path_no_subprocess(wk):
    # `<repo>/.worktrees/<slug>` → repo name, without shelling out to git.
    assert wk._repo_label(wk.Path("/x/myrepo/.worktrees/feat-x")) == "myrepo"


def test_external_wk_sessions_parses_and_excludes_local(wk, monkeypatch):
    rows = "\n".join([
        "wk-feat-x\t1\tfeat/x\t/other/.worktrees/feat-x",   # external → keep
        "here-main\t1\tmain\t/here/repo",                    # local → excluded by path
        "wk-dashboard\t\t\t",                                # not @wk-tagged → skip
        "junk\t1\t\t/p",                                     # empty branch → skip
    ])

    def fake_run(cmd, *a, **k):
        if "ls" in cmd:
            return subprocess.CompletedProcess(cmd, 0, rows, "")
        return subprocess.CompletedProcess(cmd, 0, "", "")  # git status / rev-list

    monkeypatch.setattr(wk, "run", fake_run)
    ext = wk.external_wk_sessions({wk.Path("/here/repo").resolve()})
    assert [w.session for w in ext] == ["wk-feat-x"]
    assert ext[0].branch == "feat/x" and ext[0].has_session is True


def test_hub_workspaces_local_first(wk, monkeypatch):
    local = _ws(wk, branch="main", session="here-main", path=wk.Path("/here/repo"))
    ext = _ws(wk, branch="feat/y", session="other-feat-y",
              path=wk.Path("/other/.worktrees/feat-y"))
    monkeypatch.setattr(wk, "all_workspaces", lambda: [local])
    monkeypatch.setattr(wk, "external_wk_sessions", lambda paths: [ext])
    assert [w.session for w in wk.hub_workspaces()] == ["here-main", "other-feat-y"]


def test_preview_resolves_cross_repo_via_global_hub(wk, monkeypatch, capsys, tmp_path):
    # The preview pane must resolve external (cross-repo) sessions too, or it
    # prints "(no workspace for ...)" for them. So it uses hub_workspaces().
    w = _ws(wk, branch="feat/x", session="other-feat-x", path=tmp_path)
    monkeypatch.setattr(wk, "hub_workspaces", lambda: [w])
    monkeypatch.setattr(
        wk.subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0] if a else [], 0, "", ""),
    )
    wk.preview("other-feat-x")
    out = capsys.readouterr().out
    assert "feat/x" in out
    assert "no workspace for" not in out
