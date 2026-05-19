# wk — agent context

> If you're an agent landing in this repo to **develop wk itself**, read
> this first. If you're an agent landing in a wk-managed workspace inside
> *another* project, read `.wk/AGENTS.md` (and `.wk/ORCHESTRATOR.md` if it
> exists) instead — those are user-facing docs that wk writes into every
> workspace it creates.

## What this is

`wk` is a tmux-based workspace manager: every workspace is one git
worktree + one tmux session of the same name, in a 5-pane layout
(sidebar | agent | lazygit | shell | terminal). It's a single-file Python
CLI built on Typer + Rich, with a thin tmux.conf binding layer.

Designed to work alongside [sesh](https://github.com/joshmedeski/sesh) —
wk sessions appear in sesh pickers automatically.

User-facing docs:
- [CHEATSHEET.md](./CHEATSHEET.md) — every binding, command, and workflow
- [wk](./wk) `--help` — Typer-generated help per command

## Repo layout

```
wk                  Single-file Python CLI (uv run --script). The whole program.
wk.conf             tmux config — bindings, server options, pane border format.
install.sh          Installer. Copies or symlinks files to ~/.local/bin etc.
lazygit.yml         Narrow-pane lazygit config, installed to ~/.config/wk/lazygit.yml.
cdw.fish            Fish helper: `cd (wk cd <branch>)` shortcut.
wk-resurrect-filter Helper for tmux-resurrect: only saves wk-tagged sessions.
CHEATSHEET.md       User-facing reference.
CLAUDE.md           This file.
```

## Running locally

```fish
# Install symlinks so source edits take effect immediately:
./install.sh --link

# Test individual commands without installing:
uv run --script ./wk <subcommand>

# Tmux config:
tmux source-file ~/.config/tmux/tmux.conf   # reload after wk.conf edits
```

The `wk` script uses `#!/usr/bin/env -S uv run --script` and inline
`# /// script` deps (typer, rich). No virtualenv to manage.

## Key concepts

### Workspace = worktree + session + marker
A wk workspace is the triple of:
1. A git worktree on its own branch (at `<repo>.worktrees/<branch-slug>/`
   by default — override via `WK_WORKTREE_ROOT`).
2. A tmux session named after the branch (with slashes → hyphens via
   `session_name()`).
3. A `.wk/` marker directory inside the worktree (created by
   `mark_wk_workspace()`).

The 5-pane layout is built by `build_session()`. Visual pane indices
(after tmux's tree-traversal renumbering) are: 1=sidebar, 2=shell,
3=agent, 4=lazygit, 5=terminal.

### Identification: `@wk` tmux user options
A session is "a wk session" iff it has `@wk = 1` set as a tmux user
option. Plain tmux sessions that happen to share a name with a branch
are NOT wk sessions. Helper: `wk_tmux_sessions()` returns only tagged
ones; `is_wk_workspace(branch, path, ...)` checks for either a `.wk/`
marker dir OR a tagged session.

Other `@wk-*` options set on sessions:
- `@wk-branch`: canonical branch name (with slashes preserved)
- `@wk-path`: absolute path to the worktree
- `@wk-lazygit-pane`: the `%NN` id of the lazygit pane, used by `wk lg-cd`
- `@wk-task`, `@wk-task-prompt`: set by `wk task` for tracking
- `@wk-last-session` (server-scoped): for `wk cycle last` (alt-tab style)
- `@wk-dashboard`: set on the `wk-dashboard` session

### Stable pane IDs > visual indices
Tmux renumbers pane visual indices in tree-traversal order whenever the
layout changes. Numeric `work.N` targets are unstable across splits.
**Always capture and use `%NN` pane IDs** for subsequent operations,
via `tmux split-window -P -F '#{pane_id}'`. `build_session` follows this
pattern; rebalance bindings in `wk.conf` use visual indices because
they only fire after the layout is fully built and stable.

### Env vars exposed to every pane
`build_session` calls `tmux new-session -e KEY=VAL …` to set:
- `WK_IN_WORKSPACE=1`
- `WK_SESSION=<slug>`
- `WK_BRANCH=<canonical>`
- `WK_PATH=<absolute>`

Agents (claude) inside the session can detect wk via these and access
the right commands.

### Branch alias resolution
Users type branch names in either form — `feat/admin-phase-1` or
`feat-admin-phase-1` (session-form). `resolve_branch_alias()` walks
`refs/heads` and rewrites session-form input to the canonical ref before
any git operations. Without this, `wk open feat-admin-phase-1` would
create a brand-new `feat-admin-phase-1` branch alongside the real
`feat/admin-phase-1`. (We had that bug; fixed.)

### Orchestrator detection
Branches in `{main, master, develop, trunk}` (override via
`WK_ORCHESTRATOR_BRANCHES`) get an extra `.wk/ORCHESTRATOR.md` written
into their `.wk/` dir documenting the spawn → poll → review → merge
pattern. `is_orchestrator_branch()` is the predicate.

### Self-destruct for `wk rm` of the current session
Killing the tmux session your Python process is running in also kills
the Python process. So when `wk rm` (with no arg, or matching the
current session) detects self-removal, it `Popen`s `wk _rm-detached
<branch>` with `start_new_session=True` (makes the child its own
process-group leader, so SIGHUP from the dying session doesn't reach
it). The detached child does worktree removal + branch deletion in the
background.

### SIGUSR1 force-refresh
`wk dashboard` runs `wk _dashboard-render` in its tmux session — a
Python loop that sleeps between renders. Registering a no-op SIGUSR1
handler makes `time.sleep()` return early when the signal arrives. The
`prefix M-r` binding does `pkill -USR1 -f 'wk _dashboard-render'` to
trigger an immediate redraw.

## Architecture decisions worth knowing

- **Per-workspace sessions, not windows in one session.** Each workspace
  gets its own tmux session, not a window inside a shared session. This
  gives clean env-var and clipboard isolation per workspace, and lets
  sesh-style pickers see them naturally.
- **The sidebar pane is passive.** It used to be an interactive fzf
  picker, but switching workspaces from inside the pane required
  navigating into it (extra keystrokes). Now it auto-refreshes a
  read-only view; `prefix W` opens a popup picker as the input surface.
- **`fd | fzf` not yazi for the explore picker.** Yazi tripped over the
  user's personal yazi.toml schema and a `Terminal response timeout`
  inside tmux popups. fd+fzf is simpler, fast, and has no terminal
  probe.
- **Lazygit retargeting uses `tmux respawn-pane -k`.** Killing the
  pane's process and respawning with `-c <new-dir>` is cleaner than
  trying to make lazygit accept a runtime cwd change.
- **Format strings don't reach into nested single quotes in tmux
  bindings.** `display-popup "sh -c 'cmd --x=#{session_name}'"` would
  pass the literal `#{session_name}` to sh. Use `tmux display-message
  -p '#S'` from inside the spawned shell to get the real value.

## Conventions

- **Style**: 4-space indent. Type hints on public functions. Docstrings
  on public commands explain *why* the operation matters, not just what.
- **Comments above non-obvious blocks** explain the constraint that
  drives the design — e.g. "tmux renumbers pane indices via tree
  traversal" before a `-P -F '#{pane_id}'` capture. Future readers will
  forget; comments make sure they don't re-discover.
- **Single-file CLI.** Resist the urge to refactor into a package.
  Everything lives in `wk` so install.sh can symlink one file.
- **All synthetic shell commands wrap with `sh`, not the user's
  default-shell.** Fish chokes on `VAR=val cmd`, `(subshell)`, and
  bash-style `do ... done` loops. `_shell_wrap()` always returns
  `["sh", "-c", cmd]`.
- **Imports**: stdlib at module top. Inline imports inside functions
  ONLY when they're heavy (e.g. `tempfile`) or rarely used.
- **Commit messages**: explain the user-visible behavior change and
  the constraint that made the change necessary. See `git log` for
  examples; they're the model.

## Common gotchas (we hit these; you might too)

| symptom | cause | fix |
|---|---|---|
| `unknown option -p` from split-window | tmux 3.4+ removed `-p <pct>` | use `-l <pct>%` |
| Pane targeted by `work.N` ends up wrong after a layout change | tmux renumbers visual indices via tree traversal | capture `%NN` from `-P -F '#{pane_id}'` |
| `--session=#{session_name}` arrives literally at the subcommand | format substitution doesn't reach into nested `sh -c '...'` | omit `--session`; let the command call `tmux display-message -p '#S'` |
| Yazi: "Terminal response timeout" in tmux popup | tmux dropping yazi's kitty-graphics probe | `set -g allow-passthrough on` in wk.conf |
| Yazi: TOML schema errors | yazi 26.5+ broke many older personal configs | wk-scoped `YAZI_CONFIG_HOME` (then later, dropped yazi for fd+fzf) |
| `wk rm` kills its own Python process before finishing | killing the tmux session your process runs in → SIGHUP | `Popen` with `start_new_session=True` to detach |
| Sidebar/dashboard never refreshes after a state change | the render loop is asleep | SIGUSR1 wakes `time.sleep()` early; bound to `prefix M-r` |
| Two branches with similar paths got confused | `.worktrees/feat/admin-phase-1` was on a *different* branch than its path suggested | always trust `git worktree list --porcelain`'s `branch refs/heads/X` line, not the path |

## Testing approach

There's no test suite (yet). Verification is:
1. `uv run --script ./wk --help` — confirms the script parses.
2. `uv run --script ./wk <cmd> --help` — confirms each command's typer
   interface is intact.
3. Manually rebuild a session: `wk rm <branch> && wk open <branch>` —
   exercises `build_session`, marker write, env-var injection, all
   five splits.
4. For layout debugging: `tmux list-panes -t <session> -F '#{pane_index}
   %#{pane_id} cmd=#{pane_current_command} pos=#{pane_left},#{pane_top}
   size=#{pane_width}x#{pane_height}'` plus the layout string from
   `tmux list-windows -F '#{window_layout}'`.

If you add a test framework, isolated tests of pure helpers (slugify,
resolve_branch_alias, _wk_marker logic) come first; tmux/git
integration tests are awkward enough that ad-hoc verification has been
fine.

## Adding a new command

Template:
```python
@app.command()
def myverb(
    arg: str = typer.Argument(..., help="…"),
    flag: bool = typer.Option(False, "--flag", "-f", help="…"),
) -> None:
    """One-line description for `--help` and the command listing.

    Longer explanation if it matters — why this exists, when to use it,
    what guarantees it makes. Be concrete; agents reading this should
    be able to use it without source-diving.
    """
    require("git")  # or "tmux", "fzf", etc.
    # ... implementation
    console.print(f"[green]✓[/green] did the thing")
```

Then:
1. Add a binding to `wk.conf` if it deserves a keystroke
2. Add a row to the commands-reference table in `CHEATSHEET.md`
3. If it's something coding agents inside workspaces would use, add it
   to the `_AGENTS_MD` string in `wk`

## Adding a new tmux binding

In `wk.conf`, follow the existing pattern:

```tmux
# prefix X      one-line description
#               longer notes if needed — what the binding does, what
#               it's for, any caveats.
bind-key -N "wk: human label" X run-shell "wk <subcommand>"
```

For popups, use `display-popup -E -w <W%> -h <H%>` and always wrap with
`sh -c '... || { echo; echo "press any key to dismiss"; read _; }'` so
errors don't disappear before the user can read them.

Non-prefix bindings use `bind-key -n` (no prefix). Reserve uppercase
letters for non-`M-` prefix bindings (the user's lowercase letters are
reserved for sesh/window shortcuts).
