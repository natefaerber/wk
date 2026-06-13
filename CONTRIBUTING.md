# Contributing to wk

Thanks for poking at wk. It's a small, single-file tool — easy to hack on.

## Architecture & conventions

Read [CLAUDE.md](./CLAUDE.md) first. It's the contributor guide: what wk is,
how the worktree + tmux-session + `.wk/` marker triple fits together, the tmux
gotchas that drive the design, and the house style. The big rule:

> **Single-file CLI.** Everything lives in `wk` so `install.sh` can symlink one
> file. Resist the urge to refactor into a package.

## Running locally

```sh
# Symlink the source onto your PATH so edits take effect immediately:
./install.sh --link

# Or run a subcommand without installing:
uv run --script ./wk <subcommand>
```

`wk` uses `#!/usr/bin/env -S uv run --script` with inline PEP-723 deps — no
virtualenv to manage. After editing `wk.conf`, reload tmux:
`tmux source-file ~/.config/tmux/tmux.conf`.

## Tests

```sh
uv run --with typer --with rich --with pytest pytest -q
```

CI runs the same suite plus `wk --help` parse/wiring checks on every push and
PR. Add tests for pure helpers and git-touching logic; tmux/popup/layout
behavior is verified with the geometry/command-sequence tests in `tests/` and
by hand (see CLAUDE.md "Testing approach").

## Docs source of truth

Command flags live in exactly one place: **[CHEATSHEET.md](./CHEATSHEET.md)**.
`.wk/AGENTS.md` (the `_AGENTS_MD` string in `wk`) and `skills/wk/SKILL.md` are
*routing* references — they say which command fits a request and point to the
cheatsheet for flags. `tests/test_docs_commands.py` fails CI if either names a
`wk <cmd>` that isn't a real command, so renaming/removing a command surfaces
the stale doc.

## Releasing

To cut `vX.Y.Z`:

1. Rename the `## [Unreleased]` heading in `CHANGELOG.md` to
   `## [X.Y.Z] — YYYY-MM-DD` (and start a fresh empty `## [Unreleased]` above
   it). `release.yml` extracts this exact section and uses it as the GitHub
   release body, so it must exist for the tag.
2. Bump the version in all three places that must match the tag — `__version__`
   in `wk` and the `version` field in both `.claude-plugin/*.json` — enforced by
   the release workflow and `tests/test_version_lockstep.py`.
3. Tag `vX.Y.Z` and push it; `release.yml` validates, builds the assets, and
   publishes the release with that changelog section as its notes.
