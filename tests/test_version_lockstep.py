"""Anti-drift guard: the CLI version and both plugin manifests must agree.

wk carries its version in three places that ship independently — `__version__`
in the `wk` script (surfaced by `wk --version` / `wk version`), and the
`version` field in each of `.claude-plugin/plugin.json` and
`.claude-plugin/marketplace.json`. The release workflow refuses to publish
unless all three match the git tag; this test catches a half-done bump on every
PR (and locally), long before a release, so you never tag a mismatched set.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _plugin_version() -> str:
    data = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    return data["version"]


def _marketplace_version() -> str:
    data = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    return data["plugins"][0]["version"]


def test_cli_version_matches_plugin_manifests(wk):
    cli = wk.__version__
    plugin = _plugin_version()
    market = _marketplace_version()
    assert cli == plugin == market, (
        f"version drift — wk.__version__={cli!r} "
        f"plugin.json={plugin!r} marketplace.json={market!r}. "
        "Bump all three together."
    )
