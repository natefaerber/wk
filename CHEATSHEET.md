# wk cheatsheet

A tmux-based workspace manager: every workspace is one git worktree + one tmux
session of the same name, in a 5-pane layout (sidebar, agent, shell, lazygit,
terminal).

---

## Common flows

### Investigate an existing branch

You want to poke around `release/v35` in `~/_Work/credo-backend`:

```fish
cd ~/_Work/credo-backend
wk open release/v35
```

- If a worktree already exists for `release/v35` anywhere, wk reuses it.
- If only the branch exists, wk adds a worktree at
  `~/_Work/credo-backend.worktrees/release-v35` and checks it out.
- If the branch only exists on `origin`, wk fetches and creates a local tracking
  branch.
- If neither exists, wk creates `release/v35` from `origin/main`.

### Investigate a bug *on top of* a release branch

You want a fresh branch based on `release/v35`:

```fish
cd ~/_Work/credo-backend
wk new fix/v35-tenant-bug --base release/v35
```

Or, kick off Claude on it in one shot (Claude names the branch):

```fish
cd ~/_Work/credo-backend
wk task "investigate tenant-settings 500 errors customer reported on v35" \
  --base release/v35
```

### Resume tomorrow

`wk open <branch>` is forgiving — if the session was killed but the worktree
still exists, it rebuilds the 5-pane layout. If the session is already running,
it just attaches.

```fish
wk open release/v35
```

The agent pane uses `claude -c || claude`, so claude resumes its most recent
conversation for that worktree (or starts fresh if there isn't one).

### Clean up

Three "closes," in order of reversibility:

```fish
# 1. Detach — keep everything, just stop looking at it
#    (tmux default: prefix d, or close your terminal)

# 2. Close — kill the tmux session, keep the worktree on disk
wk close                    # current workspace
wk close release/v35        # specific workspace
#    Bound to `prefix X` for the current workspace. Resume with `wk open <branch>`.

# 3. Remove — full destruction (kill session + remove worktree + delete branch)
wk rm                       # CURRENT workspace (self-destruct, see below)
wk rm release/v35           # specific; refuses if dirty
wk rm release/v35 --force   # remove even if dirty
wk rm release/v35 --keep-branch   # remove worktree but keep the branch ref
#    From `prefix W`, ctrl-d on the highlighted row does the same.
#    From inside any wk session, `prefix D` prompts "type yes" and runs
#    `wk rm --force`. Self-removal: the rm work runs in a detached
#    background process so it survives tmux killing the session it
#    was launched from. tmux auto-switches your client to another
#    session (or detaches) once the kill lands.
```

---

## Pane layout

```
┌──────────┬──────────────────────────┬──────────────────┐
│ sidebar  │                          │   lazygit        │
│ pane.1   │                          │   pane.4         │
├──────────┤   agent (Claude Code)    ├──────────────────┤
│          │   pane.2 (visual idx 3)  │                  │
│ shell    │                          │   terminal       │
│ pane.4   │                          │   pane.5         │
└──────────┴──────────────────────────┴──────────────────┘
```

- **sidebar** — passive read-only dashboard of all wk workspaces (auto-refreshes
  every 3s; tune with `WK_SIDEBAR_REFRESH`)
- **agent** — Claude Code (or whatever `WK_AGENT_CMD` is set to)
- **shell** — a regular login shell
- **lazygit** — `lazygit -ucf ~/.config/wk/lazygit.yml` (narrow-pane config)
- **terminal** — another login shell

`prefix M-w` rebalances widths/heights back to defaults.

---

## Switching workspaces

The sidebar pane is **read-only** — you don't navigate into it. To switch:

| binding | what |
|---|---|
| `prefix W` | popup picker (fzf) over **existing wk workspaces**; switch on Enter |
| `prefix O` | popup picker over **all git branches** (local + remote), sorted by most recent commit. Markers show wk status (●=session running, ·=worktree only). Pick one → if it has a wk workspace, switches to it; otherwise creates one. |
| `prefix W` then `ctrl-n` | prompt for a new branch and create it |
| `prefix W` then `ctrl-d` | delete the highlighted workspace |
| `M-]` / `M-[` | **cycle next/prev running wk session** — no prefix, fires on bare keystroke. Like browser tabs. |
| `M-m` | **toggle to last visited wk session** — alt-tab style. Repeated presses bounce between two recent workspaces. |

CLI: `wk cycle next` / `wk cycle prev` / `wk cycle last`. Suitable for binding
to any chord — only @wk-tagged sessions are in the cycle, so plain tmux
sessions and `wk-dashboard` don't get in the way. The "last visited" pointer
is stored as a server-wide tmux option (`@wk-last-session`) so it persists
across detach/re-attach.

Inside the popup: `enter` switches, `esc` dismisses, `ctrl-p` toggles preview.

CLI equivalent (handy from Claude or scripts):

```fish
wk switch release/v35
wk list
```

---

## Retargeting lazygit at a different repo

Common when the agent is working in a subrepo or sibling repo of where wk
started.

| binding | what |
|---|---|
| `prefix M-g` | command-prompt pre-filled with the active pane's cwd; Enter to follow |
| `prefix M-z` | zoxide popup (frecency-sorted jump list) |
| `prefix M-y` | fd + fzf fuzzy picker, rooted at the active pane's cwd |

CLI equivalents (Claude can call any of these):

```fish
wk lg-cd                              # follow the calling pane's cwd
wk lg-cd ~/some/other/repo            # exact path
wk lg-cd --pick=zoxide                # zoxide jump list
wk lg-cd --pick=fd                    # fd + fzf, scoped to cwd
wk lg-cd ~/some/repo --session=feat-foo  # target a specific session
```

---

## What Claude sees inside a wk session

Every pane in a wk session has these env vars set:

| var | example |
|---|---|
| `WK_IN_WORKSPACE` | `1` |
| `WK_SESSION` | `release-v35` (slug, no slashes) |
| `WK_BRANCH` | `release/v35` (canonical ref) |
| `WK_PATH` | `/Users/nate/_Work/credo-backend.worktrees/release-v35` |

And `.wk/AGENTS.md` in the worktree root documents the layout + commands for
the agent. Reference it from your project `CLAUDE.md` to give Claude
auto-context:

```markdown
@.wk/AGENTS.md
```

---

## Branch naming gotchas

- wk accepts both slash form (`release/v35`) and slug form (`release-v35`)
  for `open`. It resolves slug → canonical (with slashes) before doing any
  git ops, so you won't accidentally create a duplicate hyphen-named branch.
- Session names always use slug form (tmux doesn't love slashes).
- Worktree paths use slug form too: `<repo>.worktrees/release-v35`.

---

## Orchestrator pattern

The workspace on your repo's long-lived branch (`main`/`master`/`develop`/
`trunk`, configurable via `WK_ORCHESTRATOR_BRANCHES`) is treated as the
**orchestrator**. It gets an extra `.wk/ORCHESTRATOR.md` documenting the
spawn → poll → review → merge workflow so Claude inside the orchestrator
knows how to drive parallel work.

Typical flow from the orchestrator:

```fish
# 1. Spawn parallel tasks (each gets its own wk session + worktree)
wk task "fix tenant-settings 500s in admin module" --base main --auto
wk task "add audit log to webhooks endpoint"      --base main --auto
wk task "extract email service to its own module" --base main --auto

# 2. Poll status
wk task-status                       # table of all task workspaces
wk task-status fix-tenant-500s       # detailed view of one
wk task-output fix-tenant-500s -n 50 # last 50 lines of stdout

# 3. Review and integrate
git -C ~/_Work/credo-backend.worktrees/fix-tenant-500s diff main..
wk task-merge fix-tenant-500s         # --no-ff merge commit (default)
wk task-merge fix-tenant-500s --squash # squash into one commit
```

| binding | what |
|---|---|
| `prefix M-t` | popup showing `wk task-status` (read-only) |
| `prefix M-r` | force-refresh the `wk dashboard` session (sends SIGUSR1) |

Claude inside an orchestrator workspace can drive all of the above via
its Bash tool: `wk task`, `wk task-status`, `wk task-output`, `wk task-merge`.

Don't run `wk task` from inside a child workspace — that's recursion and
the orchestrator pattern breaks. Surface sub-task ideas back to the user
or to the orchestrator instead.

---

## Commands reference

```
wk new <branch>                  # create + attach (errors if branch exists)
wk open <branch>                 # create-or-attach (forgiving)
wk open --pick                   # fzf over all branches, open the chosen one
wk close [branch]                # kill session, keep worktree (default: current)
wk rm [branch]                   # destroy session + worktree + branch (default: current)
wk task <prompt>                 # Claude names a branch, launches with prompt
wk task --auto <prompt>          # headless task (claude -p, output to .wk/output.md)
wk switch [branch]               # switch to existing workspace; fzf if no arg
wk list                          # show all workspaces with status
wk rm <branch>                   # destroy session + worktree
wk restore [branch]              # rebuild tmux session(s) for existing worktrees
wk refresh-agents [branch|--all] # regenerate .wk/AGENTS.md and ORCHESTRATOR.md
wk cd [branch]                   # print worktree path (for shell cd integration)
wk lg-cd [path] [--pick=...]     # retarget lazygit pane
wk task-status [branch]          # status table / detail of task workspaces
wk task-output <branch> [-n N]   # dump a task's .wk/output.md (--follow streams)
wk task-merge <branch>           # merge task branch into orchestrator's branch
wk sidebar                       # the dashboard renderer (runs in pane.1)
wk dashboard                     # cross-workspace overview session
```

---

## Useful env vars

| var | default | what |
|---|---|---|
| `WK_AGENT_CMD` | `claude -c \|\| claude` | command run in the agent pane |
| `WK_WORKTREE_ROOT` | `<repo>.worktrees/` | where to put worktrees |
| `WK_SIDEBAR_REFRESH` | `3` | sidebar pane refresh interval in seconds |
| `WK_DASHBOARD_REFRESH` | `30` | `wk dashboard` refresh interval in seconds (min 1) |

---

## Install / update

### From source (full setup — installs tmux config, fish helper, lazygit config)

```fish
cd ~/path/to/wk
./install.sh --link     # symlinks; future edits to wk source take effect immediately
./install.sh            # copy mode
./install.sh --uninstall
```

### Via mise (CLI only)

```fish
mise use -g "github:natefaerber/wk[asset_pattern=wk,bin=wk]"
```

This installs just the `wk` binary. The tmux bindings (`wk.conf`), lazygit
config, and fish `cdw` helper are not installed — clone the repo and run
`./install.sh` if you want the full keystroke experience.

Requires `uv` on `PATH` (wk's shebang is `#!/usr/bin/env -S uv run --script`).
Install with `mise use -g uv` or `brew install uv`.

### Cutting a release (maintainers)

```fish
git tag v0.1.0
git push origin v0.1.0
```

The `release` workflow validates the script, then publishes a GitHub release
with `wk` and `wk.sha256` attached.
