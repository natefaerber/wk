"""Story C — layout geometry safety net.

There's no way to unit-test real tmux panes, but we CAN pin the sequence of
split/resize commands each builder issues. That catches the silent failure the
red-team flagged: dropping a pane renumbers visual indices, and a stale
`_rebalance_wide` target would resize the wrong pane with no error. These tests
fail loudly if the wide layout stops being `sidebar | agent | terminal`.
"""

from __future__ import annotations

import subprocess

import pytest


class SplitRec:
    """run() mock that hands back a fresh %pane-id for every `-P` split and
    records every call, so we can assert the geometry a builder constructs."""

    def __init__(self):
        self.calls: list[list[str]] = []
        self._n = 1  # the sidebar is %1; splits start at %2

    def __call__(self, cmd, *a, **k):
        self.calls.append(list(cmd))
        out = ""
        if "split-window" in cmd and "-P" in cmd:
            self._n += 1
            out = f"%{self._n}"
        return subprocess.CompletedProcess(cmd, 0, out, "")

    def splits(self):
        return [c for c in self.calls if "split-window" in c]

    def joined(self):
        return " ".join(" ".join(map(str, c)) for c in self.calls)


def test_build_wide_is_sidebar_shell_agent_terminal(wk, monkeypatch):
    rec = SplitRec()
    monkeypatch.setattr(wk, "run", rec)
    wk._build_wide("sess", wk.Path("/wt"), "%1", "agent-cmd")

    splits = rec.splits()
    assert len(splits) == 3, "wide = sidebar + 3 splits (agent, terminal, shell)"
    horiz = [s for s in splits if "-h" in s]
    vert = [s for s in splits if "-v" in s]
    assert len(horiz) == 2, "agent + terminal are horizontal columns"
    assert len(vert) == 1, "shell is a vertical split of the left column"
    # agent carves the window minus the left column; terminal carves the right
    assert str(wk.WIDE_WINDOW_COLS - wk.WIDE_SIDEBAR_COLS) in horiz[0]
    assert str(wk.WIDE_TERMINAL_COLS) in horiz[1]
    # no lazygit pane, no @wk-lazygit-pane bookkeeping
    assert "lazygit" not in rec.joined().lower()
    assert "@wk-lazygit-pane" not in rec.joined()
    # land on the agent (the first -P split → %2)
    selects = [c for c in rec.calls if "select-pane" in c]
    assert selects and "%2" in selects[-1]


def test_rebalance_wide_targets_sidebar_and_terminal(wk, monkeypatch):
    # Visual order is 1=sidebar, 2=shell, 3=agent, 4=terminal: rebalance sets
    # the left column width + sidebar height (pane 1) and terminal width (pane 4).
    rec = SplitRec()
    monkeypatch.setattr(wk, "run", rec)
    wk._rebalance_wide("sess")
    resizes = [" ".join(map(str, c)) for c in rec.calls if "resize-pane" in c]
    assert any("sess:.1" in r and "-x" in r and str(wk.WIDE_SIDEBAR_COLS) in r for r in resizes)
    assert any("sess:.1" in r and "-y" in r for r in resizes)
    assert any("sess:.4" in r and str(wk.WIDE_TERMINAL_COLS) in r for r in resizes)


def test_build_laptop_is_two_columns(wk, monkeypatch):
    rec = SplitRec()
    monkeypatch.setattr(wk, "run", rec)
    wk._build_laptop("sess", wk.Path("/wt"), "%1", "agent-cmd")

    splits = rec.splits()
    assert len(splits) == 2
    assert any("-h" in s for s in splits), "agent is a horizontal split"
    assert any("-v" in s for s in splits), "terminal is stacked below the sidebar"
    selects = [c for c in rec.calls if "select-pane" in c]
    assert selects and "%2" in selects[-1]


def test_rebalance_refuses_non_wk_session(wk, monkeypatch):
    # prefix M-w fires globally; rebalancing a plain session would mangle it.
    import typer

    def fake_run(cmd, *a, **k):
        if "display-message" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "plain-sess", "")
        return subprocess.CompletedProcess(cmd, 0, "", "")  # @wk unset

    monkeypatch.setattr(wk, "require", lambda *a, **k: None)
    monkeypatch.setattr(wk, "in_tmux", lambda: True)
    monkeypatch.setattr(wk, "run", fake_run)
    with pytest.raises(typer.Exit):
        wk.rebalance()


def test_rebalance_runs_on_wk_session(wk, monkeypatch):
    calls = []

    def fake_run(cmd, *a, **k):
        calls.append(list(cmd))
        if "display-message" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "wk-sess", "")
        if cmd[-1] == "@wk":
            return subprocess.CompletedProcess(cmd, 0, "1", "")
        if cmd[-1] == "@wk-layout":
            return subprocess.CompletedProcess(cmd, 0, "wide", "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(wk, "require", lambda *a, **k: None)
    monkeypatch.setattr(wk, "in_tmux", lambda: True)
    monkeypatch.setattr(wk, "run", fake_run)
    wk.rebalance()
    assert any("resize-pane" in c for c in calls)


