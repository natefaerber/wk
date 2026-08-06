"""Branch naming, per-repo config, layout selection, and handoff briefs.

These are the pieces that decide *what a workspace is* before tmux gets
involved, so they're worth testing directly: a bad branch name or a missing
handoff is invisible until an agent has already acted on it.
"""

from __future__ import annotations

import subprocess

import pytest
import typer


# --------------------------------------------------------------------------- #
# Branch names — `<type>/<slug>`, now that worktree paths keep the hierarchy.
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", [
    "fix/flaky-session-test",
    "feat/nested-worktree-paths",
    "chore/bump-deps",
    "spike/try-pyo3",
    "plain-no-prefix",          # unprefixed stays valid (slugify fallback)
])
def test_branch_re_accepts(wk, name):
    assert wk._branch_re().match(name)


@pytest.mark.parametrize("name", [
    "bogus/thing",              # not a known type
    "feat/sub/deep",            # only one prefix segment
    "Feat/Caps",
    "feat/",
    "/leading",
    "feat/ab",                  # slug under 3 chars
    "1feat/starts-with-digit",
])
def test_branch_re_rejects(wk, name):
    assert not wk._branch_re().match(name)


def test_branch_types_env_override(wk, monkeypatch):
    monkeypatch.setenv("WK_BRANCH_TYPES", "epic, bugfix")
    assert wk.branch_types() == ("epic", "bugfix")
    assert wk._branch_re().match("epic/new-thing")
    assert not wk._branch_re().match("feat/new-thing")  # defaults replaced


def test_branch_types_default_when_env_blank(wk, monkeypatch):
    monkeypatch.setenv("WK_BRANCH_TYPES", "   ")
    assert wk.branch_types() == wk.BRANCH_TYPES


def test_slugify_output_still_valid(wk):
    """The deterministic fallback must satisfy the widened regex too."""
    assert wk._branch_re().match(wk.slugify("Fix the flaky session test"))


# --------------------------------------------------------------------------- #
# pick_branch_name — the AI one-shot. Never raises; always returns something
# that passes validation.
# --------------------------------------------------------------------------- #

def _fake_claude(wk, monkeypatch, result: str, returncode: int = 0):
    def _run(cmd, *a, **k):
        payload = '{"result": %s}' % __import__("json").dumps(result)
        return subprocess.CompletedProcess(cmd, returncode, payload, "")
    monkeypatch.setattr(wk.shutil, "which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(wk.subprocess, "run", _run)


def test_pick_branch_name_keeps_type_prefix(wk, monkeypatch):
    _fake_claude(wk, monkeypatch, "fix/flaky-session-test")
    assert wk.pick_branch_name("the session test is flaky") == (
        "fix/flaky-session-test", "claude",
    )


def test_pick_branch_name_strips_decoration_around_prefix(wk, monkeypatch):
    # Claude likes wrapping the answer in backticks and stray dashes.
    _fake_claude(wk, monkeypatch, "`fix/-flaky--test-`")
    name, source = wk.pick_branch_name("flaky test")
    assert (name, source) == ("fix/flaky-test", "claude")


def test_pick_branch_name_falls_back_on_bad_type(wk, monkeypatch):
    _fake_claude(wk, monkeypatch, "nonsense/whatever")
    name, source = wk.pick_branch_name("make the thing work")
    assert source == "slug"
    assert wk._branch_re().match(name)


def test_pick_branch_name_falls_back_when_claude_missing(wk, monkeypatch):
    monkeypatch.setattr(wk.shutil, "which", lambda _: None)
    name, source = wk.pick_branch_name("make the thing work")
    assert source == "slug"
    assert wk._branch_re().match(name)


# --------------------------------------------------------------------------- #
# Handoff briefs — the fix for "the workspace has no idea what it's for".
# --------------------------------------------------------------------------- #

def test_render_handoff_uses_claude_output(wk, monkeypatch):
    body = "# Fix it\n\n## Goal\nMake it work.\n\n## Acceptance\n- [ ] works"
    _fake_claude(wk, monkeypatch, body)
    out, source = wk.render_handoff("fix/x", "make it work")
    assert source == "claude"
    assert "## Goal" in out and out.endswith("\n")


def test_render_handoff_rejects_unstructured_reply(wk, monkeypatch):
    """A reply that lost the headings reads authoritative while omitting the
    sections agents look for — the skeleton is safer."""
    _fake_claude(wk, monkeypatch, "Sure! I'd start by looking at the tests.")
    out, source = wk.render_handoff("fix/x", "make it work")
    assert source == "template"
    assert "## Goal" in out and "## Acceptance" in out


def test_render_handoff_preserves_request_on_failure(wk, monkeypatch):
    """Losing the user's own words to a failed AI call is the worst outcome."""
    _fake_claude(wk, monkeypatch, "", returncode=1)
    out, source = wk.render_handoff("fix/x", "make the flaky test stop failing")
    assert source == "template"
    assert "make the flaky test stop failing" in out


def test_render_handoff_survives_timeout(wk, monkeypatch):
    def _boom(cmd, *a, **k):
        raise subprocess.TimeoutExpired(cmd, 60)
    monkeypatch.setattr(wk.shutil, "which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(wk.subprocess, "run", _boom)
    out, source = wk.render_handoff("fix/x", "do the thing")
    assert source == "template"
    assert "do the thing" in out


def test_render_handoff_no_task_is_skeleton(wk, monkeypatch):
    def _never(*a, **k):
        raise AssertionError("must not shell out with no task text")
    monkeypatch.setattr(wk.subprocess, "run", _never)
    out, source = wk.render_handoff("fix/x", None)
    assert source == "template"
    assert "## Goal" in out


def test_write_handoff_never_clobbers(wk, tmp_path, monkeypatch):
    """Reopening a workspace must not wipe notes the agent kept."""
    monkeypatch.setattr(wk.shutil, "which", lambda _: None)
    marker = tmp_path / wk.WK_MARKER_DIR
    marker.mkdir()
    existing = marker / "task.md"
    existing.write_text("hand-edited notes\n", encoding="utf-8")
    assert wk.write_handoff(tmp_path, "fix/x", "new task") is None
    assert existing.read_text() == "hand-edited notes\n"


def test_write_handoff_creates_marker_dir(wk, tmp_path, monkeypatch):
    monkeypatch.setattr(wk.shutil, "which", lambda _: None)
    path = wk.write_handoff(tmp_path, "fix/x", "do the thing")
    assert path is not None and path.exists()
    assert "do the thing" in path.read_text()


# --------------------------------------------------------------------------- #
# Per-repo config + layout precedence.
# --------------------------------------------------------------------------- #

def _repo_with_config(wk, monkeypatch, tmp_path, text: str):
    (tmp_path / wk.WK_MARKER_DIR).mkdir(exist_ok=True)
    (tmp_path / wk.WK_MARKER_DIR / "config").write_text(text, encoding="utf-8")
    monkeypatch.setattr(wk, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(wk, "user_config", dict)  # ignore the real ~/.config
    wk._read_repo_config.cache_clear()


def test_repo_config_parses(wk, monkeypatch, tmp_path):
    _repo_with_config(wk, monkeypatch, tmp_path,
                      "# a comment\nlayout = minimal\n\nignored-line\n")
    assert wk.repo_config() == {"layout": "minimal"}


def test_repo_config_strips_quotes(wk, monkeypatch, tmp_path):
    _repo_with_config(wk, monkeypatch, tmp_path, 'layout = "laptop"\n')
    assert wk.repo_config()["layout"] == "laptop"


def test_repo_config_empty_outside_repo(wk, monkeypatch):
    def boom():
        raise SystemExit(1)
    monkeypatch.setattr(wk, "repo_root", boom)
    assert wk.repo_config() == {}


def test_layout_from_repo_config(wk, monkeypatch, tmp_path):
    _repo_with_config(wk, monkeypatch, tmp_path, "layout = minimal\n")
    monkeypatch.delenv("WK_LAYOUT", raising=False)
    assert wk.resolve_profile().name == "minimal"


def test_explicit_layout_beats_repo_config(wk, monkeypatch, tmp_path):
    _repo_with_config(wk, monkeypatch, tmp_path, "layout = minimal\n")
    monkeypatch.delenv("WK_LAYOUT", raising=False)
    assert wk.resolve_profile("wide").name == "wide"


def test_env_layout_beats_repo_config(wk, monkeypatch, tmp_path):
    _repo_with_config(wk, monkeypatch, tmp_path, "layout = minimal\n")
    monkeypatch.setenv("WK_LAYOUT", "laptop")
    assert wk.resolve_profile().name == "laptop"


def test_unknown_layout_in_repo_config_dies(wk, monkeypatch, tmp_path):
    _repo_with_config(wk, monkeypatch, tmp_path, "layout = enormous\n")
    monkeypatch.delenv("WK_LAYOUT", raising=False)
    with pytest.raises(typer.Exit):
        wk.resolve_profile()


def test_minimal_profile_has_no_sidebar(wk):
    assert wk.LAYOUTS["minimal"].has_sidebar is False
    assert wk.LAYOUTS["wide"].has_sidebar is True
    assert wk.LAYOUTS["laptop"].has_sidebar is True


@pytest.mark.parametrize("alias,expected", [
    ("minimal", "minimal"), ("solo", "minimal"),
    ("wide", "wide"), ("widescreen", "wide"),
    ("laptop", "laptop"), ("narrow", "laptop"),
])
def test_layout_aliases(wk, monkeypatch, alias, expected):
    monkeypatch.delenv("WK_LAYOUT", raising=False)
    assert wk.resolve_profile(alias).name == expected


# --------------------------------------------------------------------------- #
# Issue refs — Jira / Linear. Configured prefixes turn a plausible match into a
# precise one: unconfigured, any uppercase `AB-1` token is treated as a ticket.
# --------------------------------------------------------------------------- #

@pytest.fixture
def no_prefixes(wk, monkeypatch):
    """No config from any layer — including the developer's real
    ~/.config/wk/config, which would otherwise leak into these assertions."""
    monkeypatch.delenv("WK_ISSUE_PREFIXES", raising=False)
    monkeypatch.setattr(wk, "repo_config", dict)
    monkeypatch.setattr(wk, "user_config", dict)


@pytest.fixture
def prefixes(wk, monkeypatch):
    monkeypatch.setenv("WK_ISSUE_PREFIXES", "LPE,ENG")
    monkeypatch.setattr(wk, "repo_config", dict)
    monkeypatch.setattr(wk, "user_config", dict)


@pytest.mark.parametrize("url,key", [
    ("https://acme.atlassian.net/browse/DEV-6266", "DEV-6266"),
    ("https://linear.app/acme/issue/ENG-123/fix-the-thing", "ENG-123"),
    ("https://linear.app/acme/issue/ENG-123", "ENG-123"),
])
def test_issue_urls_match_without_config(wk, no_prefixes, url, key):
    """A tracker URL is unambiguous — it shouldn't need configuring."""
    assert wk.parse_issue_ref(url) == key


def test_issue_url_matches_even_if_prefix_not_configured(wk, prefixes):
    assert wk.parse_issue_ref("https://acme.atlassian.net/browse/DEV-6266") == "DEV-6266"


@pytest.mark.parametrize("ref,key", [
    ("DEV-6266", "DEV-6266"),
    ("ENG-123", "ENG-123"),
    ("API-2", "API-2"),      # the false-positive prefixes exist to prevent
])
def test_bare_keys_fall_back_to_generic_shape(wk, no_prefixes, ref, key):
    assert wk.parse_issue_ref(ref) == key


@pytest.mark.parametrize("ref", ["lpe-1544", "ENG-123/fix-the-thing", "feat/x"])
def test_generic_shape_rejects_lowercase_and_slugs(wk, no_prefixes, ref):
    """Unanchored to a known project, these would swallow branch names."""
    assert wk.parse_issue_ref(ref) is None


@pytest.mark.parametrize("ref,key", [
    ("LPE-1544", "LPE-1544"),
    ("lpe-1544", "LPE-1544"),                 # case-insensitive once configured
    ("ENG-123/fix-the-thing", "ENG-123"),     # Linear issue picker
    ("eng-123-fix-the-thing", "ENG-123"),     # Linear "copy git branch name"
])
def test_configured_prefixes_match(wk, prefixes, ref, key):
    assert wk.parse_issue_ref(ref) == key


@pytest.mark.parametrize("ref", ["DEV-6266", "API-2", "fix-tenant-500s", "feat/x"])
def test_configured_prefixes_reject_everything_else(wk, prefixes, ref):
    """The whole point: an unconfigured key is a branch name, not a ticket."""
    assert wk.parse_issue_ref(ref) is None


def test_issue_prefixes_from_repo_config(wk, monkeypatch):
    monkeypatch.delenv("WK_ISSUE_PREFIXES", raising=False)
    monkeypatch.setattr(wk, "user_config", dict)
    monkeypatch.setattr(wk, "repo_config", lambda: {"issue_prefixes": "lpe, eng"})
    assert wk.issue_prefixes() == ("LPE", "ENG")
    assert wk.parse_issue_ref("lpe-1544") == "LPE-1544"


def test_issue_prefixes_from_user_config(wk, monkeypatch):
    """The normal home: trackers follow you, not one repo."""
    monkeypatch.delenv("WK_ISSUE_PREFIXES", raising=False)
    monkeypatch.setattr(wk, "repo_config", dict)
    monkeypatch.setattr(wk, "user_config", lambda: {"issue_prefixes": "LPE, ENG"})
    assert wk.issue_prefixes() == ("LPE", "ENG")
    assert wk.parse_issue_ref("lpe-1544") == "LPE-1544"


def test_repo_config_beats_user_config(wk, monkeypatch):
    monkeypatch.delenv("WK_ISSUE_PREFIXES", raising=False)
    monkeypatch.setattr(wk, "user_config", lambda: {"issue_prefixes": "GLOBAL"})
    monkeypatch.setattr(wk, "repo_config", lambda: {"issue_prefixes": "REPO"})
    assert wk.issue_prefixes() == ("REPO",)


def test_env_beats_both_config_files(wk, monkeypatch):
    monkeypatch.setenv("WK_ISSUE_PREFIXES", "ZZZ")
    monkeypatch.setattr(wk, "user_config", lambda: {"issue_prefixes": "GLOBAL"})
    monkeypatch.setattr(wk, "repo_config", lambda: {"issue_prefixes": "LPE"})
    assert wk.issue_prefixes() == ("ZZZ",)


def test_layout_falls_back_to_user_config(wk, monkeypatch):
    monkeypatch.delenv("WK_LAYOUT", raising=False)
    monkeypatch.setattr(wk, "repo_config", dict)
    monkeypatch.setattr(wk, "user_config", lambda: {"layout": "minimal"})
    assert wk.resolve_profile().name == "minimal"


def test_user_config_path_honours_xdg(wk, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert wk.user_config_path() == tmp_path / "wk" / "config"


def test_user_config_missing_file_is_empty(wk, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert wk.user_config() == {}


def test_issue_prefixes_accepts_space_separated(wk, monkeypatch):
    monkeypatch.setenv("WK_ISSUE_PREFIXES", "LPE ENG")
    monkeypatch.setattr(wk, "repo_config", dict)
    monkeypatch.setattr(wk, "user_config", dict)
    assert wk.issue_prefixes() == ("LPE", "ENG")


def test_existing_workspace_short_circuits_issue_lookup(wk, monkeypatch):
    """`open_issue` names its branch `key.lower()`, so with prefixes configured
    that branch classifies as an issue again. Reopening must attach to what's
    on disk, not re-resolve the ticket to a possibly-different PR."""
    monkeypatch.setattr(wk, "find_existing_worktree",
                        lambda b: ("lpe-1544", wk.Path("/repo/.worktrees/lpe-1544")))
    assert wk._existing_workspace_for_issue("LPE-1544") is True


def test_existing_workspace_check_survives_git_failure(wk, monkeypatch):
    def boom(_):
        raise RuntimeError("git exploded")
    monkeypatch.setattr(wk, "find_existing_worktree", boom)
    assert wk._existing_workspace_for_issue("LPE-1544") is False
