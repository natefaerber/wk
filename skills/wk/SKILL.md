---
name: wk
description: >-
  Drive `wk` — a tmux + git-worktree workspace manager — from Claude Code.
  Invoke when the user wants to open/switch a branch as a workspace, spin up a
  worktree, spawn parallel headless tasks across branches, check task status,
  merge a task branch back, or tear down a worktree — phrasings like "open a
  branch", "new worktree", "spawn a task", "run these in parallel", "switch
  workspaces", "kill this worktree". Requires the `wk` CLI on PATH (this plugin
  does not install it — see the repo README). Inside a wk session
  `WK_IN_WORKSPACE=1` is set — prefer wk commands over raw `git worktree` /
  `tmux new-session`. Skip for single-branch quick edits in the main checkout.
allowed-tools:
  - Bash
  - Read
  - AskUserQuestion
---

# wk

`wk` is a single-file Python CLI (`uv run --script`) that ties together git
worktrees and tmux sessions. One workspace = one worktree at
`<repo>/.worktrees/<branch-slug>/` + one tmux session (the slug, project-scoped
with the repo name) + a `.wk/` marker dir. Sessions are tagged with `@wk = 1`
so they show up in pickers and cycle bindings.

The user-facing cheatsheet lives in the wk repo at `CHEATSHEET.md` — it is the
single source of truth for command flags. Read it when you need full coverage.
This file is the quick-reference for deciding *which* command fits a request;
it deliberately does not re-list every flag (that would drift from CHEATSHEET).

## Preflight — is wk installed?

This plugin ships the skill, not the binary. Before doing anything, confirm the
CLI is present:

```bash
command -v wk >/dev/null 2>&1 && echo "WK_OK" || echo "WK_MISSING"
```

If you see `WK_MISSING`, stop and tell the user plainly: the `wk` CLI isn't on
PATH, so the plugin can't manage worktrees. Point them at the install options
in the wk repo README (`mise use -g "github:natefaerber/wk[asset_pattern=wk,bin=wk]"`
is the fastest). Don't flail on `command not found`.

## When to use which command

| user says… | run |
|---|---|
| "open / switch to `<branch>`" | `wk open <branch>` — forgiving: create or attach |
| "new branch off `<base>`" | `wk new <branch> --base <base>` |
| "spawn a task to do X" (from an orchestrator branch) | `wk task "<prompt>" --base main` (add `--auto` for headless) |
| "switch workspaces" / "what's running" | `wk switch` (fzf) or `wk list` |
| "kill / clean up this workspace" | `wk close` (keep worktree) or `wk rm` (full destroy) |
| "rebuild the tmux layout for `<branch>`" | `wk restore <branch>` |
| "where's the worktree for `<branch>`?" | `wk cd <branch>` (prints path) |
| "merge a finished task back" | `wk task-merge <branch> --rm` (merge + tear down) |

`wk open` is the forgiving default — it creates the branch, fetches from origin,
adds the worktree, builds the session, or just attaches, depending on what
already exists. Reach for `wk new` only when you specifically want it to error
on collision.

## Detecting context

Before running anything, check where you are:

```bash
echo "WK_IN_WORKSPACE=${WK_IN_WORKSPACE:-0} WK_BRANCH=${WK_BRANCH:-} WK_PATH=${WK_PATH:-}"
```

- `WK_IN_WORKSPACE=1` → you're inside a wk session. `WK_BRANCH` and `WK_PATH`
  are authoritative; don't infer from `git branch --show-current` if they're
  set (they handle slug↔canonical and detached-HEAD cases).
- Unset → you're in a plain shell or another tmux session. `wk open` from
  here will spawn a new session rather than reusing the current one.

To list every wk workspace (tagged sessions + worktrees with `.wk/` markers):

```bash
wk list
```

## Orchestrator pattern — when the user wants parallel work

Branches matching `WK_ORCHESTRATOR_BRANCHES` (default: main/master/develop/trunk)
are "orchestrators." From an orchestrator workspace, the user can spawn child
tasks that each get their own session + worktree + (optionally) headless
Claude. Look for `.wk/ORCHESTRATOR.md` in the worktree root — its presence is
the signal that this is the parent.

```bash
wk task "investigate tenant 500s" --base main --auto   # headless: output to .wk/output.md
wk task-status                                          # table of all child tasks
wk task-output <slug> -n 50                             # tail a child's output
wk task-merge <slug>                                    # merge child back (--squash for one commit)
```

**Never call `wk task` from inside a child workspace** — that's recursion and
breaks the orchestrator model. If you're in a child and notice subtask-shaped
work, surface it back to the user or write it into `.wk/output.md` for the
orchestrator to pick up.

## Branch name resolution

Users (and you) can type branches in either form:

- canonical: `feat/admin-phase-1`
- session slug: `feat-admin-phase-1`

wk resolves slug → canonical before any git op, so `wk open feat-admin-phase-1`
correctly opens the existing `feat/admin-phase-1` branch instead of creating a
new hyphenated one. This is internal — pass whichever form the user gave you.

## Cleanup, in order of reversibility

1. `prefix d` (or close terminal) — detach. Nothing destroyed.
2. `wk close [branch]` — kill the tmux session, keep the worktree on disk.
   Resume later with `wk open <branch>`.
3. `wk rm [branch]` — destroy session + worktree + branch ref. Refuses on
   dirty trees unless `--force`. `--keep-branch` preserves the ref.

When the user says "clean up" without specifying, **ask** whether they mean
close (keep worktree) or rm (full destroy). The distinction matters and rm
is hard to undo.

`wk rm` on the current workspace is self-destructive (kills its own tmux
session). wk handles this by detaching the cleanup into a background
process-group; you don't need to do anything special, but expect the session
to die mid-command.

## Common gotchas

- **Don't `tmux kill-session` a wk workspace directly** — `wk close`/`wk rm`
  do the right thing with the marker dir and branch ref.
- **Don't manually `git worktree remove`** for the same reason.
- **Lazygit is on demand, not a pane**: the user summons it full-screen with
  `prefix M-g` (it opens at the active pane's cwd). There's no lazygit pane to
  manage.
- **Slug vs canonical in paths**: worktree directories use slug form
  (`release-v35`), but `git branch --show-current` returns canonical
  (`release/v35`). Trust `WK_BRANCH` when both are available.

## When NOT to use wk

- Single-branch quick edits in the main checkout — `wk` adds session overhead
  that's wasted on a 30-second fix.
- Non-git directories — wk requires a git repo.
- Inside an existing wk child workspace, spawning more children (see
  orchestrator section above).

## Self-help

```bash
wk --help                  # command listing
wk <subcommand> --help     # per-command flags
```

Full reference: `CHEATSHEET.md` in the wk repo source.
