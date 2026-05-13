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

```fish
wk rm release/v35           # kill session + remove worktree
wk rm release/v35 --force   # skip "are you sure" prompts
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
| `prefix W` | popup picker (fzf) with preview, j/k nav, `/` to filter |
| `prefix W` then `ctrl-n` | prompt for a new branch and create it |
| `prefix W` then `ctrl-d` | delete the highlighted workspace |

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
| `prefix M-y` | yazi popup (full filesystem TUI) |

CLI equivalents (Claude can call any of these):

```fish
wk lg-cd                              # follow the calling pane's cwd
wk lg-cd ~/some/other/repo            # exact path
wk lg-cd --pick=zoxide                # interactive zoxide
wk lg-cd --pick=yazi                  # interactive yazi
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

## Commands reference

```
wk new <branch>                  # create + attach (errors if branch exists)
wk open <branch>                 # create-or-attach (forgiving)
wk task <prompt>                 # Claude names a branch, launches with prompt
wk switch [branch]               # switch to existing workspace; fzf if no arg
wk list                          # show all workspaces with status
wk rm <branch>                   # destroy session + worktree
wk restore [branch]              # rebuild tmux session(s) for existing worktrees
wk cd [branch]                   # print worktree path (for shell cd integration)
wk lg-cd [path] [--pick=...]     # retarget lazygit pane
wk sidebar                       # the dashboard renderer (runs in pane.1)
wk dashboard                     # cross-workspace overview session
```

---

## Useful env vars

| var | default | what |
|---|---|---|
| `WK_AGENT_CMD` | `claude -c \|\| claude` | command run in the agent pane |
| `WK_WORKTREE_ROOT` | `<repo>.worktrees/` | where to put worktrees |
| `WK_SIDEBAR_REFRESH` | `3` | dashboard refresh interval in seconds |

---

## Install / update

```fish
cd ~/path/to/wk
./install.sh --link     # symlinks; future edits to wk source take effect immediately
./install.sh            # copy mode
./install.sh --uninstall
```
