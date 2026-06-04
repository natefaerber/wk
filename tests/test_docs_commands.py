"""Anti-drift guard: every `wk <cmd>` referenced in the shipped docs must be a
real registered command.

There are several places that describe wk's command surface — the `/wk` plugin
skill (`skills/wk/SKILL.md`) and the `_AGENTS_MD` string wk writes into every
workspace's `.wk/AGENTS.md`. CHEATSHEET.md is the single source of truth for
flags; these two are routing/quick-reference and should never name a command
that doesn't exist. This test turns that rule into a build failure: rename or
remove a command and forget to update the docs, and CI goes red.

We only scan code spans (backtick + fenced) to avoid prose false positives like
"the wk session" or "wk workspace".
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# `wk <token>` where token is command-shaped (lowercase, hyphens). This skips
# `wk --help`, `wk <branch>`, `wk.conf`, and `wk-dashboard` automatically.
_WK_CMD = re.compile(r"\bwk ([a-z][a-z-]+)\b")
# Inline `code` spans and ```fenced``` blocks.
_CODE_SPANS = re.compile(r"`[^`]+`|```.*?```", re.DOTALL)


def _registered_commands(wk) -> set[str]:
    names = set()
    for c in wk.app.registered_commands:
        names.add(c.name or c.callback.__name__.replace("_", "-"))
    return names


def _referenced_commands(text: str) -> set[str]:
    refs: set[str] = set()
    for span in _CODE_SPANS.findall(text):
        refs.update(_WK_CMD.findall(span))
    return refs


def test_skill_md_references_only_real_commands(wk):
    commands = _registered_commands(wk)
    text = (REPO / "skills" / "wk" / "SKILL.md").read_text(encoding="utf-8")
    refs = _referenced_commands(text)
    assert refs, "expected to find some `wk <cmd>` references in SKILL.md"
    unknown = refs - commands
    assert not unknown, f"SKILL.md references unregistered commands: {sorted(unknown)}"


def test_agents_md_references_only_real_commands(wk):
    commands = _registered_commands(wk)
    refs = _referenced_commands(wk._AGENTS_MD)
    assert refs, "expected to find some `wk <cmd>` references in _AGENTS_MD"
    unknown = refs - commands
    assert not unknown, f"_AGENTS_MD references unregistered commands: {sorted(unknown)}"
