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
