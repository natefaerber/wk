# Changelog

All notable changes to wk are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and wk uses
[semantic versioning](https://semver.org/). Full per-release diffs are linked
from the [GitHub releases](https://github.com/natefaerber/wk/releases).

## [Unreleased]

### Added
- **Handoff briefs.** `wk open` / `wk new` take `--task "<what and why>"`, and
  `wk task` always writes one: wk one-shots `claude -p` to turn it into a
  `.wk/task.md` with **Goal**, **Context**, and **Acceptance** sections, and
  the workspace's `.wk/AGENTS.md` now tells the agent to read it first. A
  workspace outlives the conversation that made it — without this, the agent
  that opens it later re-derives intent from a branch name. Existing briefs
  are never overwritten. Every failure path (no `claude`, timeout, malformed
  or unstructured reply) falls back to a skeleton that preserves your own
  words verbatim; workspace creation never fails over it.
- **`minimal` layout** (`--layout minimal`, alias `solo`): two panes, agent |
  terminal, no sidebar — for a single focused task, a narrow split, or a
  screen-share. `wk ls` / `prefix W` still show everything the sidebar would.
- **Per-repo config at `<repo>/.wk/config`.** `key = value` lines in the main
  checkout; `layout = minimal` sets that repo's default. Sits below `--layout`
  and `$WK_LAYOUT` in precedence, above width auto-detection.
- **`--layout` on `wk task`**, matching `wk open` / `wk new`.

### Changed
- **Generated branch names are `<type>/<slug>`** — `fix/flaky-session-test`
  rather than `fix-flaky-session-test`. Now that worktree paths preserve
  hierarchy, the `<type>/` is a real `.worktrees/fix/` subdir. Types are
  `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `perf`, `spike`,
  overridable with `WK_BRANCH_TYPES`. Unprefixed names remain valid, and the
  deterministic fallback still produces one.
- **`wk task` writes a structured brief** instead of dumping the raw prompt
  into `.wk/task.md`.
- **The `/wk` skill states the three workspace-setup non-negotiables** — never
  hand-roll the worktree, always pass the task, let wk name the branch — after
  agents were observed doing all three wrong.

- **Worktree paths preserve the branch hierarchy.** `fix/LPE-1544` now lands at
  `.worktrees/fix/LPE-1544` instead of `.worktrees/fix-LPE-1544`. Branch
  prefixes (`feat/`, `fix/`, `chore/`) stay browsable subdirs rather than
  becoming part of one long flat name, and the layout now matches what a
  hand-rolled `git worktree add <path>` produces — so wk-made and manually-made
  worktrees no longer fragment a repo across two conventions. Session names are
  unaffected and still flatten to a slug (tmux rejects `/`).

  **Existing worktrees keep working and are not migrated.** wk reads every path
  from `git worktree list`, so pre-0.10 flat worktrees open, list, and remove
  exactly as before. To adopt the new layout for one, `wk rm` it and `wk open`
  it again.

### Fixed
- `wk rm` prunes the empty prefix dirs a nested worktree leaves behind, so
  `.worktrees/` doesn't accumulate hollow `fix/` and `feat/` directories. Stops
  at the first prefix that still holds a sibling worktree.
- A failed `wk open` / `wk pr` no longer strands an empty prefix directory.
  wk now pre-creates only `.worktrees/` itself and lets `git worktree add`
  create the branch's prefix dirs, which it only does on success.

### Removed
- **`lazygit.yml`** and its install step. It tuned lazygit for the narrow side
  pane that 0.8.0 removed, and the `prefix M-g` popup never actually loaded it
  (`LAZYGIT_CMD` was dead code). The popup now uses your normal lazygit config.

## [0.9.0] - 2026-06-20

### Added
- **Global hub.** `prefix W` / `wk switch` now lists this repo's workspaces
  **plus every running wk session across all other repos** (a `repo` column
  disambiguates), so you can jump to any agent from anywhere — even from
  outside a repo. Cross-repo discovery is derived live from tmux (each session
  is tagged with its branch + path); no registry, no new state. Idle workspaces
  in other repos aren't listed (nothing running to tag them). `enter`/switch
  works on any row; `ctrl-d`/`ctrl-x` act on the current repo.

### Changed
- **Widescreen layout is `(sidebar over shell) | agent | terminal`** (4 panes).
  0.8.0 had pared `wide` to 3 panes, but on a big display the agent sprawled to
  ~two-thirds and the lone terminal looked stranded. The shell returns under the
  sidebar and the terminal column is widened, so the agent caps near ~half the
  screen. Lazygit stays a `prefix M-g` popup. (The laptop layout is unchanged.)

## [0.8.0] - 2026-06-13

The "polish round" — easier to use, more agent-drivable.

### Added
- **The hub.** `prefix W` / `wk switch` now lists running tasks alongside
  workspaces, with single-key actions: `ctrl-x` cancels a task, `ctrl-r`
  refreshes. A finished `--auto` task shows `✓`.
- **`wk task-merge --rm`** — merge a task branch into the orchestrator and tear
  the workspace down in one step. The branch is deleted only when it's
  ancestor-merged (never a blind force-delete).
- **`wk task-merge --into <orchestrator>`** — target an orchestrator explicitly,
  so a merge can be fired from outside its session.
- **Task completion signal** — a finished `--auto` task messages the
  orchestrator that spawned it.
- **`wk doctor`** — checks dependencies and whether the tmux bindings are
  actually installed (the mise-only-install trap).
- **First-run onboarding** — `prefix W` in a repo with no workspaces offers to
  create one inline (and names the repo + base it'll branch from).
- **`prefix M-g`** summons lazygit full-screen in a popup at the active pane's
  cwd.

### Changed
- **Widescreen layout is now 3 columns** (sidebar | agent | terminal) instead of
  5 panes. The redundant second shell is gone.
- `wk list` outside a git repo now says so, instead of printing "no workspaces".

### Removed
- **BREAKING: the always-on lazygit pane and `wk lg-cd`** (plus the
  `prefix M-g` / `M-z` / `M-y` retarget bindings). Lazygit is now summoned on
  demand with `prefix M-g` — it opens where you are, so there's nothing to
  retarget. Rebind muscle memory accordingly.

### Fixed
- `prefix W` and `prefix M-g` no longer flash a popup shut on error (e.g. when
  run outside a git repo); they show the message and wait for a keypress.
- `wk rebalance` (`prefix M-w`) refuses on non-wk sessions instead of resizing
  their panes.

## [0.7.0] - 2026-06-08
### Added
- `wk --version` / `wk version`, backed by a single `__version__` kept in
  lockstep with the plugin manifests (enforced by CI + a test).
- Documented the wide and laptop layouts in the README.
### Fixed
- Hardened the mise install: releases now publish arch-named asset copies so the
  bare `mise use github:natefaerber/wk` autodetects instead of erroring.

## [0.6.0] - 2026-06-08
### Added
- **Laptop layout profile** with width-based auto-detection (`--layout` /
  `$WK_LAYOUT` / `$WK_WIDE_COLS`) and `wk rebalance`.
### Changed
- Unified workspace-state rendering (one glyph vocabulary across list / switch /
  sidebar / dashboard) and added next-step hints to error messages.

## [0.5.0] - 2026-06-06
### Added
- Test suite + CI.
- Packaged wk as a Claude Code plugin (the `wk-tools` marketplace, shipping the
  `/wk` skill).
### Fixed
- Data-loss, resilience, and task-lifecycle hardening from a full review;
  hardened `workspace_status` and detached `rm`.

## [0.4.0] - 2026-06-03
- See the [v0.4.0 release](https://github.com/natefaerber/wk/releases/tag/v0.4.0).

[Unreleased]: https://github.com/natefaerber/wk/compare/v0.9.0...HEAD
[0.9.0]: https://github.com/natefaerber/wk/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/natefaerber/wk/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/natefaerber/wk/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/natefaerber/wk/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/natefaerber/wk/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/natefaerber/wk/releases/tag/v0.4.0
