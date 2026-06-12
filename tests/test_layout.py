"""Story C — layout geometry safety net.

There's no way to unit-test real tmux panes, but we CAN pin the sequence of
split/resize commands each builder issues. That catches the silent failure the
red-team flagged: dropping a pane renumbers visual indices, and a stale
`_rebalance_wide` target would resize the wrong pane with no error. These tests
fail loudly if the wide layout stops being `sidebar | agent | terminal`.
"""

from __future__ import annotations

import subprocess


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


def test_build_wide_is_three_columns_no_lazygit(wk, monkeypatch):
    rec = SplitRec()
    monkeypatch.setattr(wk, "run", rec)
    wk._build_wide("sess", wk.Path("/wt"), "%1", "agent-cmd")

    splits = rec.splits()
    assert len(splits) == 2, "wide = sidebar + 2 splits (agent, terminal)"
    # all full-height columns: horizontal splits only, never vertical
    assert all("-h" in s for s in splits)
    assert all("-v" not in s for s in splits)
    # agent carves the window minus the sidebar column; terminal carves the right
    assert str(wk.WIDE_WINDOW_COLS - wk.WIDE_SIDEBAR_COLS) in splits[0]
    assert str(wk.WIDE_TERMINAL_COLS) in splits[1]
    # no lazygit pane, no @wk-lazygit-pane bookkeeping
    assert "lazygit" not in rec.joined().lower()
    assert "@wk-lazygit-pane" not in rec.joined()
    # land on the agent (the first -P split → %2)
    selects = [c for c in rec.calls if "select-pane" in c]
    assert selects and "%2" in selects[-1]


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


def test_rebalance_wide_targets_match_build_order(wk, monkeypatch):
    # The rebalance indices MUST track the build: 1=sidebar, 3=terminal.
    rec = SplitRec()
    monkeypatch.setattr(wk, "run", rec)
    wk._rebalance_wide("sess")
    resizes = [" ".join(map(str, c)) for c in rec.calls if "resize-pane" in c]
    assert any("sess:.1" in r and str(wk.WIDE_SIDEBAR_COLS) in r for r in resizes)
    assert any("sess:.3" in r and str(wk.WIDE_TERMINAL_COLS) in r for r in resizes)
    # no vertical (-y) resizes — every wide pane is full height
    assert all("-y" not in r for r in resizes)
