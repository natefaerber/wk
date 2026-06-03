"""Pytest fixtures for the wk test suite.

`wk` is a single executable file with a `# /// script` PEP-723 header and a
`#!/usr/bin/env -S uv run --script` shebang — deliberately NOT a package (see
CLAUDE.md: "Single-file CLI. Resist the urge to refactor into a package").

Two consequences shape how we import it for tests:

1. It has no `.py` suffix, so `importlib.util.spec_from_file_location("wk", "wk")`
   can't infer a loader and returns a spec whose `.loader` is None. We hand it an
   explicit `SourceFileLoader` instead.
2. Importing it executes `import typer` / `from rich...` at module top, so the
   test runner must have those deps present. Run via:
       uv run --with typer --with rich --with pytest pytest

Importing `wk` is side-effect-free: it has a clean `if __name__ == "__main__":`
guard and no module-level git/subprocess calls. If that ever regresses, these
fixtures (and every test) will break loudly — which is the intended tripwire.
"""

from __future__ import annotations

import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest


def _load_wk():
    path = Path(__file__).parent / "wk"
    loader = SourceFileLoader("wk", str(path))
    spec = importlib.util.spec_from_loader("wk", loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules["wk"] = module
    loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def wk():
    """The imported `wk` module."""
    return _load_wk()
