"""Unit tests for wk's pure + git-touching helpers.

Coverage is aimed squarely at the bugs the project has actually hit (see the
"Common gotchas" table in CLAUDE.md): branch/path confusion, session-form alias
resolution, and the project-prefix collision. The genuinely pure helpers are
tested directly; the "logically pure" ones that shell out to git (session_name,
resolve_branch_alias, list_worktrees) get their `run`/`repo_root` monkeypatched.
"""

from __future__ import annotations

import subprocess

import pytest
from pathlib import Path
import typer


def fake_run(stdout: str = "", returncode: int = 0):
    """A stand-in for wk.run's CompletedProcess return value."""
    def _run(cmd, *args, **kwargs):
        return subprocess.CompletedProcess(cmd, returncode, stdout, "")
    return _run


# --------------------------------------------------------------------------- #
# slugify — pure. Fallback path is non-deterministic (timestamp), so assert
# SHAPE, never equality.
# --------------------------------------------------------------------------- #

def test_slugify_basic(wk):
    assert wk.slugify("Fix the THING!!") == "fix-the-thing"


def test_slugify_caps_words(wk):
    # max_words defaults to 5
    assert wk.slugify("one two three four five six seven") == "one-two-three-four-five"


def test_slugify_all_punctuation_uses_timestamp_fallback(wk):
    out = wk.slugify("!!!")
    assert out.startswith("task-")
    assert wk._BRANCH_RE.match(out)


def test_slugify_leading_digit_gets_task_prefix(wk):
    out = wk.slugify("123 abc")
    assert out.startswith("task-")
    assert wk._BRANCH_RE.match(out)


def test_slugify_short_input_padded(wk):
    out = wk.slugify("a")
    assert len(out) >= 3
    assert wk._BRANCH_RE.match(out)


@pytest.mark.parametrize("text", ["Fix the THING!!", "a", "!!!", "123", "x" * 200])
def test_slugify_always_matches_branch_re(wk, text):
    assert wk._BRANCH_RE.match(wk.slugify(text))


# --------------------------------------------------------------------------- #
# _normalize_session — pure. tmux names can't hold . : / → all become -.
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("raw,expected", [
    ("feat/login", "feat-login"),
    ("release.1.2", "release-1-2"),
    ("a:b", "a-b"),
    ("plain", "plain"),
    ("a/b.c:d", "a-b-c-d"),
])
def test_normalize_session(wk, raw, expected):
    assert wk._normalize_session(raw) == expected


def test_normalize_session_idempotent(wk):
    once = wk._normalize_session("feat/admin.phase:1")
    assert wk._normalize_session(once) == once


# --------------------------------------------------------------------------- #
# _query_matches — pure when `session` is passed explicitly. Accepts the real
# branch, the session-form slug, or the full project-scoped session name.
# --------------------------------------------------------------------------- #

def test_query_matches_exact_branch(wk):
    assert wk._query_matches("feat/login", "feat/login", session="x-feat-login")


def test_query_matches_session_form_slug(wk):
    # The gotcha: typing the hyphen form must still resolve the slashed branch.
    assert wk._query_matches("feat-login", "feat/login", session="x-feat-login")


def test_query_matches_full_session_name(wk):
    assert wk._query_matches("x-feat-login", "feat/login", session="x-feat-login")


def test_query_matches_rejects_unrelated(wk):
    assert not wk._query_matches("other", "feat/login", session="x-feat-login")


# --------------------------------------------------------------------------- #
# is_orchestrator_branch — pure (+ env override).
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("branch", ["main", "master", "develop", "trunk"])
def test_orchestrator_defaults(wk, branch, monkeypatch):
    monkeypatch.delenv("WK_ORCHESTRATOR_BRANCHES", raising=False)
    assert wk.is_orchestrator_branch(branch)


def test_orchestrator_non_default(wk, monkeypatch):
    monkeypatch.delenv("WK_ORCHESTRATOR_BRANCHES", raising=False)
    assert not wk.is_orchestrator_branch("feat/x")


def test_orchestrator_env_override_trims_whitespace(wk, monkeypatch):
    monkeypatch.setenv("WK_ORCHESTRATOR_BRANCHES", " release , staging ")
    assert wk.is_orchestrator_branch("release")
    assert wk.is_orchestrator_branch("staging")
    assert wk.is_orchestrator_branch("main")  # defaults still apply


# --------------------------------------------------------------------------- #
# worktree_path — pure (+ env override). `feat/foo` keeps its hierarchy on
# disk as `feat/foo`, so branch prefixes stay browsable subdirs.
# --------------------------------------------------------------------------- #

def test_worktree_path_env_override(wk, monkeypatch, tmp_path):
    monkeypatch.setenv(wk.WORKTREE_ROOT_ENV, str(tmp_path))
    assert wk.worktree_path("feat/foo") == tmp_path / "feat" / "foo"


def test_worktree_path_default_nested(wk, monkeypatch):
    monkeypatch.delenv(wk.WORKTREE_ROOT_ENV, raising=False)
    monkeypatch.setattr(wk, "repo_root", lambda: wk.Path("/repo"))
    assert wk.worktree_path("feat/foo") == wk.Path("/repo/.worktrees/feat/foo")


def test_worktree_path_flat_branch_unchanged(wk, monkeypatch):
    """A branch with no `/` sits directly in the root, exactly as before."""
    monkeypatch.delenv(wk.WORKTREE_ROOT_ENV, raising=False)
    monkeypatch.setattr(wk, "repo_root", lambda: wk.Path("/repo"))
    assert wk.worktree_path("hotfix") == wk.Path("/repo/.worktrees/hotfix")


def test_worktree_path_deep_hierarchy(wk, monkeypatch):
    monkeypatch.delenv(wk.WORKTREE_ROOT_ENV, raising=False)
    monkeypatch.setattr(wk, "repo_root", lambda: wk.Path("/repo"))
    assert wk.worktree_path("fix/LPE-1544/part-2") == wk.Path(
        "/repo/.worktrees/fix/LPE-1544/part-2"
    )


@pytest.mark.parametrize("branch", ["../escape", "feat/../../escape", "/abs", ""])
def test_worktree_path_refuses_to_escape_root(wk, monkeypatch, branch):
    """Git's ref rules forbid these, but the path is built from user input —
    never resolve one outside the worktree root."""
    monkeypatch.delenv(wk.WORKTREE_ROOT_ENV, raising=False)
    monkeypatch.setattr(wk, "repo_root", lambda: wk.Path("/repo"))
    with pytest.raises(typer.Exit):
        wk.worktree_path(branch)


def test_worktree_path_normalizes_root_with_dotdot(wk, monkeypatch, tmp_path):
    """A WK_WORKTREE_ROOT containing `..` must not trip the containment check."""
    monkeypatch.setenv(wk.WORKTREE_ROOT_ENV, str(tmp_path / "sub" / ".." / "wt"))
    assert wk.worktree_path("feat/foo") == tmp_path / "wt" / "feat" / "foo"


# --------------------------------------------------------------------------- #
# session_name / _project_prefix — the project-prefix collision fix.
# --------------------------------------------------------------------------- #

def test_project_prefix_outside_repo_is_empty(wk, monkeypatch):
    wk._project_prefix.cache_clear()

    def boom(*a, **k):
        raise subprocess.CalledProcessError(128, a[0] if a else "git")
    monkeypatch.setattr(wk, "run", boom)
    assert wk._project_prefix("/no/repo/here") == ""


def test_session_name_outside_repo_is_bare_slug(wk, monkeypatch):
    wk._project_prefix.cache_clear()
    monkeypatch.setattr(wk, "_project_prefix", lambda cwd: "")
    assert wk.session_name("feat/x") == "feat-x"


def test_session_name_is_repo_prefixed(wk, monkeypatch):
    wk._project_prefix.cache_clear()
    monkeypatch.setattr(wk, "_project_prefix", lambda cwd: "myrepo")
    assert wk.session_name("feat/x") == "myrepo-feat-x"
    # dots in the branch normalize too
    assert wk.session_name("release.1") == "myrepo-release-1"


def test_project_prefix_derives_repo_name_from_common_dir(wk, monkeypatch):
    wk._project_prefix.cache_clear()
    monkeypatch.setattr(wk, "run", fake_run(stdout="/home/u/my.repo/.git\n"))
    # repo dir name is slugified: my.repo → my-repo
    assert wk._project_prefix("/home/u/my.repo") == "my-repo"


def test_project_prefix_cache_is_keyed_on_cwd(wk, monkeypatch):
    """Cross-repo flows os.chdir mid-run; the cache must key on cwd so a new
    repo gets a fresh prefix instead of a stale cached one."""
    wk._project_prefix.cache_clear()
    calls = {"n": 0}
    outputs = ["/home/u/repo-a/.git\n", "/home/u/repo-b/.git\n"]

    def counting_run(cmd, *a, **k):
        out = outputs[min(calls["n"], len(outputs) - 1)]
        calls["n"] += 1
        return subprocess.CompletedProcess(cmd, 0, out, "")
    monkeypatch.setattr(wk, "run", counting_run)

    assert wk._project_prefix("/home/u/repo-a") == "repo-a"
    assert wk._project_prefix("/home/u/repo-a") == "repo-a"  # cached, run not called again
    assert calls["n"] == 1
    assert wk._project_prefix("/home/u/repo-b") == "repo-b"  # new key → recompute
    assert calls["n"] == 2


# --------------------------------------------------------------------------- #
# resolve_branch_alias — the phantom-branch gotcha: `wk open feat-admin-phase-1`
# must resolve to the real `feat/admin-phase-1`, not invent a new branch.
# --------------------------------------------------------------------------- #

@pytest.fixture
def aliased_repo(wk, monkeypatch):
    monkeypatch.setattr(wk, "repo_root", lambda: wk.Path("/repo"))
    monkeypatch.setattr(wk, "_project_prefix", lambda cwd: "")
    monkeypatch.setattr(
        wk, "run", fake_run(stdout="feat/login\nmain\nrelease/v2\n", returncode=0)
    )


def test_resolve_alias_slug_to_slashed(wk, aliased_repo):
    assert wk.resolve_branch_alias("feat-login") == "feat/login"


def test_resolve_alias_exact_passthrough(wk, aliased_repo):
    assert wk.resolve_branch_alias("main") == "main"


def test_resolve_alias_second_branch(wk, aliased_repo):
    assert wk.resolve_branch_alias("release-v2") == "release/v2"


def test_resolve_alias_unknown_passthrough(wk, aliased_repo):
    assert wk.resolve_branch_alias("does-not-exist") == "does-not-exist"


def test_resolve_alias_git_failure_passthrough(wk, monkeypatch):
    monkeypatch.setattr(wk, "repo_root", lambda: wk.Path("/repo"))
    monkeypatch.setattr(wk, "run", fake_run(stdout="", returncode=1))
    assert wk.resolve_branch_alias("whatever") == "whatever"


# --------------------------------------------------------------------------- #
# list_worktrees — porcelain parsing. Trust `branch refs/heads/X`, skip the
# main checkout and detached HEADs, and flush the last record without a
# trailing newline.
# --------------------------------------------------------------------------- #

PORCELAIN = """\
worktree /repo
HEAD aaaa
branch refs/heads/main

worktree /repo/.worktrees/feat-x
HEAD bbbb
branch refs/heads/feat/x

worktree /repo/.worktrees/detached
HEAD cccc
detached
"""


def _patch_list(wk, monkeypatch, porcelain):
    monkeypatch.setattr(wk, "repo_root", lambda: wk.Path("/repo"))
    monkeypatch.setattr(wk, "run", fake_run(stdout=porcelain))


def test_list_worktrees_skips_main_and_detached(wk, monkeypatch):
    _patch_list(wk, monkeypatch, PORCELAIN)
    result = wk.list_worktrees()
    assert result == [("feat/x", wk.Path("/repo/.worktrees/feat-x"))]


def test_list_worktrees_flushes_last_record_without_trailing_newline(wk, monkeypatch):
    # No trailing blank line: the `+ [""]` sentinel in list_worktrees must
    # still emit the final record. Drop the trailing newline to prove it.
    porcelain = (
        "worktree /repo\nHEAD a\nbranch refs/heads/main\n\n"
        "worktree /repo/.worktrees/feat-y\nHEAD b\nbranch refs/heads/feat/y"
    )
    _patch_list(wk, monkeypatch, porcelain)
    result = wk.list_worktrees()
    assert result == [("feat/y", wk.Path("/repo/.worktrees/feat-y"))]


def test_list_worktrees_empty(wk, monkeypatch):
    _patch_list(wk, monkeypatch, "")
    assert wk.list_worktrees() == []


# --------------------------------------------------------------------------- #
# workspace_status — regression for the check=True crash. A worktree deleted
# out-of-band makes `git -C <gone> status` exit nonzero; that must NOT raise
# (it used to crash all_workspaces() → wk ls / rm / switch / dashboard).
# --------------------------------------------------------------------------- #

def test_workspace_status_tolerates_vanished_worktree(wk, monkeypatch):
    monkeypatch.setattr(wk, "_project_prefix", lambda cwd: "")
    # git returns 128 for a missing -C path; both calls use check=False now.
    monkeypatch.setattr(wk, "run", fake_run(stdout="", returncode=128))
    ws = wk.workspace_status("feat/x", wk.Path("/repo/.worktrees/gone"), set())
    assert ws.dirty is False
    assert ws.ahead == 0 and ws.behind == 0
    assert ws.branch == "feat/x"


# --------------------------------------------------------------------------- #
# _prune_empty_parents — nested worktree paths (`.worktrees/fix/foo`) leave an
# empty `fix/` behind on `wk rm`. Prune it, but never past the root and never
# a dir that still holds a sibling worktree.
# --------------------------------------------------------------------------- #

def test_prune_empty_parents_removes_empty_prefix(wk, tmp_path):
    root = tmp_path / ".worktrees"
    wt = root / "fix" / "foo"
    wt.mkdir(parents=True)
    wt.rmdir()  # git worktree remove already took the leaf
    wk._prune_empty_parents(wt, root)
    assert not (root / "fix").exists()
    assert root.exists()  # the root itself is never removed


def test_prune_empty_parents_stops_at_sibling(wk, tmp_path):
    root = tmp_path / ".worktrees"
    (root / "fix" / "bar").mkdir(parents=True)
    wt = root / "fix" / "foo"
    wt.mkdir()
    wt.rmdir()
    wk._prune_empty_parents(wt, root)
    assert (root / "fix" / "bar").exists()  # sibling keeps the prefix alive


def test_prune_empty_parents_walks_multiple_levels(wk, tmp_path):
    root = tmp_path / ".worktrees"
    wt = root / "a" / "b" / "c"
    wt.mkdir(parents=True)
    wt.rmdir()
    wk._prune_empty_parents(wt, root)
    assert not (root / "a").exists()
    assert root.exists()


def test_prune_empty_parents_leaves_flat_layout_alone(wk, tmp_path):
    """A branch with no `/` has the root as its parent — nothing to prune."""
    root = tmp_path / ".worktrees"
    root.mkdir()
    wk._prune_empty_parents(root / "hotfix", root)
    assert root.exists()


def test_prune_empty_parents_ignores_paths_outside_root(wk, tmp_path):
    """Adopted worktrees live outside the root; never walk up into them."""
    root = tmp_path / ".worktrees"
    root.mkdir()
    elsewhere = tmp_path / "adopted" / "thing"
    elsewhere.mkdir(parents=True)
    elsewhere.rmdir()
    wk._prune_empty_parents(elsewhere, root)
    assert (tmp_path / "adopted").exists()


# --------------------------------------------------------------------------- #
# session_strip — a configured branch prefix stays out of session names.
# --------------------------------------------------------------------------- #

def test_session_name_strips_configured_prefix(wk, monkeypatch):
    monkeypatch.setattr(wk, "_project_prefix", lambda cwd: "myrepo")
    monkeypatch.setattr(wk, "_session_strip_prefixes", lambda cwd: ("nate/",))
    assert wk.session_name("nate/lpe-1516-x") == "myrepo-lpe-1516-x"
    # other branches are untouched, and a bare prefix is never stripped to nothing
    assert wk.session_name("feat/x") == "myrepo-feat-x"
    assert wk.session_name("nate/") == "myrepo-nate-"


def test_session_strip_from_env(wk, monkeypatch):
    wk._session_strip_prefixes.cache_clear()
    monkeypatch.setenv("WK_SESSION_STRIP", "nate/, bob/")
    assert wk._session_strip_prefixes("/somewhere") == ("nate/", "bob/")
    wk._session_strip_prefixes.cache_clear()


def test_session_strip_from_user_config(wk, monkeypatch, tmp_path):
    wk._session_strip_prefixes.cache_clear()
    monkeypatch.delenv("WK_SESSION_STRIP", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    (tmp_path / "wk").mkdir()
    (tmp_path / "wk" / "config").write_text("session_strip = nate/\n")
    monkeypatch.chdir(tmp_path)  # outside any repo: only the user config applies
    assert wk._session_strip_prefixes(str(tmp_path)) == ("nate/",)
    wk._session_strip_prefixes.cache_clear()


def test_query_matches_slug_without_strip_prefix(wk, monkeypatch):
    monkeypatch.setattr(wk, "_session_strip_prefixes", lambda cwd: ("nate/",))
    assert wk._query_matches("lpe-1-x", "nate/lpe-1-x", session="r-lpe-1-x")
    assert wk._query_matches("nate-lpe-1-x", "nate/lpe-1-x", session="r-lpe-1-x")


# --------------------------------------------------------------------------- #
# session_names = ticket — the issue key names the session, `KEY-<repo>` on a
# clash, and a session keeps resolving to the name it was built with.
# --------------------------------------------------------------------------- #

@pytest.fixture
def ticket_names(wk, monkeypatch):
    wk._session_lookup_cache.clear()
    monkeypatch.setattr(wk, "_project_prefix", lambda cwd: "myrepo")
    monkeypatch.setattr(wk, "_session_strip_prefixes", lambda cwd: ())
    monkeypatch.setattr(wk, "_session_names_mode", lambda cwd: "ticket")
    monkeypatch.setattr(wk, "issue_key_in_branch",
                        lambda b: "LPE-1" if "lpe-1" in b.lower() else None)
    wt = Path("/repos/myrepo/.worktrees/nate/lpe-1-x")
    monkeypatch.setattr(wk, "_branch_worktrees", lambda: {"nate/lpe-1-x": wt})

    def with_open(sessions):
        wk._session_lookup_cache.clear()
        monkeypatch.setattr(wk, "_open_session_paths", lambda: sessions)
        return wk.session_name("nate/lpe-1-x")
    with_open.wt = wt
    yield with_open
    wk._session_lookup_cache.clear()


def test_ticket_name_when_free(ticket_names):
    assert ticket_names({}) == "LPE-1"


def test_ticket_name_found_again_for_its_worktree(ticket_names):
    # herdr records pane cwds, which may sit below the worktree root
    assert ticket_names({"LPE-1": [ticket_names.wt / "apps"]}) == "LPE-1"


def test_ticket_name_taken_elsewhere_gets_repo(ticket_names):
    assert ticket_names({"LPE-1": [Path("/repos/other/.worktrees/lpe-1")]}) == "LPE-1-myrepo"


def test_ticket_name_both_taken_falls_back_to_branch_name(ticket_names):
    elsewhere = [Path("/repos/other")]
    assert ticket_names({"LPE-1": elsewhere, "LPE-1-myrepo": elsewhere}) == "myrepo-nate-lpe-1-x"


def test_ticket_name_keeps_its_suffixed_name_after_the_clash_ends(ticket_names):
    assert ticket_names({"LPE-1-myrepo": [ticket_names.wt]}) == "LPE-1-myrepo"


def test_ticket_mode_leaves_keyless_branches_alone(wk, ticket_names):
    assert wk.session_name("feat/x") == "myrepo-feat-x"


def test_branch_mode_is_the_default(wk, monkeypatch):
    wk._session_names_mode.cache_clear()
    monkeypatch.delenv("WK_SESSION_NAMES", raising=False)
    monkeypatch.setattr(wk, "config_get", lambda key, default="": default)
    assert wk._session_names_mode("/x") == "branch"
    wk._session_names_mode.cache_clear()
