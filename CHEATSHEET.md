# wk cheatsheet

A tmux-based workspace manager: every workspace is one git worktree + one tmux
session of the same name, in a multi-column layout (sidebar, agent, terminal;
lazygit on demand).

---

## Common flows

### Open a branch, PR, or issue

`wk open` is the one "get me into the work" command. It takes a branch
name, a pull request (number or URL), or an issue key — it figures out
which from the shape of the argument.

You want to poke around `release/v35` in `~/_Work/credo-backend`:

```fish
cd ~/_Work/credo-backend
wk open release/v35
```

- If a worktree already exists for `release/v35` anywhere, wk reuses it.
- If only the branch exists, wk adds a worktree at
  `~/_Work/credo-backend/.worktrees/release-v35` and checks it out.
- If the branch only exists on `origin`, wk fetches and creates a local tracking
  branch.
- If neither exists, wk creates `release/v35` from `origin/main`.

### Review a pull request

Pull a PR's head branch into a workspace. A bare number is looked up in the
current repo:

```fish
cd ~/_Work/credo-backend
wk open 4670        # or: wk pr 4670
```

A full URL is opened from anywhere — wk finds the matching clone under
`~/_Work` (matched by its `origin` remote — override the search root with
`WK_PR_REPO_ROOT`) and creates the workspace there:

```fish
wk open https://github.com/credo-ai/credo-backend/pull/4670
```

- Same-repo PRs are checked out as a tracking branch (the PR's own head
  branch), exactly like `wk open <branch>`.
- Fork PRs — and PRs whose head branch has been deleted from `origin` — are
  fetched via `refs/pull/<n>/head` into a local `pr-<n>` branch.
- Requires the GitHub CLI (`gh`) to be installed and authenticated.
- `wk pr <number|url>` is the same thing as an explicit, PR-only verb.

### Start (or jump to) work from an issue tracker

Hand `wk open` an issue-tracker link (or a bare key) and it resolves to the
work for that ticket:

```fish
cd ~/_Work/credo-backend
wk open https://credo-ai.atlassian.net/browse/DEV-6266
wk open DEV-6266               # same thing, bare key
```

- It searches for a PR referencing the key — the current repo first, then
  across that repo's GitHub org (override the org with `WK_PR_SEARCH_OWNER`).
- **PR found** → opens it like a PR above (and `cd`s into the matching
  clone under `~/_Work` if the PR lives in another repo).
- **No PR yet** → starts fresh work: a new workspace on a branch named
  after the key (`dev-6266`) off `origin/main`, in the current repo.

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
still exists, it rebuilds the layout. If the session is already running,
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

wk has two layout profiles. The **widescreen** layout (3 columns) is the default
on wide displays; the **laptop** layout (2 columns) kicks in on narrow ones.
Either way, lazygit is summoned on demand with `prefix M-g` (full-screen popup),
not an always-on pane.

### Widescreen (`wide`)

```
┌──────────┬──────────────────────────┬──────────────────┐
│ sidebar  │                          │                  │
│ pane.1   │   agent (Claude Code)    │   terminal       │
│          │   pane.2                 │   pane.3         │
└──────────┴──────────────────────────┴──────────────────┘
```

- **sidebar** — passive read-only dashboard of all wk workspaces (auto-refreshes
  every 3s; tune with `WK_SIDEBAR_REFRESH`)
- **agent** — Claude Code (or whatever `WK_AGENT_CMD` is set to)
- **terminal** — a regular login shell
- **lazygit** — `prefix M-g` opens it full-screen at the active pane's cwd

### Laptop (`laptop`)

```
┌──────────┬──────────────────────────────────────┐
│ sidebar  │                                      │
├──────────┤        agent (Claude Code)           │
│ terminal │                                      │
└──────────┴──────────────────────────────────────┘
```

Two columns: the left stacks the **sidebar** over a **terminal**; the right is
a full-height **agent**. Same as `wide` minus the dedicated terminal column.

### Choosing a layout

By default wk **auto-detects** from the display width when it builds a session:
a client at least `WK_WIDE_COLS` (default 220) columns wide gets `wide`, narrower
gets `laptop`. Override per-invocation with `--layout wide|laptop` on `wk new` /
`wk open` / `wk relayout`, or globally with `WK_LAYOUT=wide|laptop` (e.g. set it
in your laptop's shell profile). Docked and undocked the same machine? Just
`wk relayout` after switching displays — it re-detects.

`prefix M-w` (`wk rebalance`) resets pane sizes to the current layout's defaults.

---

## Switching workspaces

The sidebar pane is **read-only** — you don't navigate into it. To switch:

| binding | what |
|---|---|
| `prefix W` | the **hub** — popup picker (fzf) over existing workspaces **and running tasks**; switch on Enter. A finished `--auto` task shows ✓. |
| `prefix O` | popup picker over **all git branches** (local + remote), sorted by most recent commit. Markers show wk status (●=session running, ·=worktree only). Pick one → if it has a wk workspace, switches to it; otherwise creates one. |
| `prefix W` then `ctrl-n` | prompt for a new branch and create it |
| `prefix W` then `ctrl-d` | delete the highlighted workspace |
| `prefix W` then `ctrl-x` | cancel the highlighted task (kill its session, keep the worktree) |
| `prefix W` then `ctrl-r` | refresh the list (e.g. after a task finishes) |
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

## Lazygit

Lazygit is summoned on demand, not parked in a pane:

| binding | what |
|---|---|
| `prefix M-g` | open lazygit full-screen (popup) at the active pane's cwd; `q` closes it |

Because it opens where you are, it already follows you into a subrepo or sibling
repo — there's nothing to retarget.

---

## What Claude sees inside a wk session

Every pane in a wk session has these env vars set:

| var | example |
|---|---|
| `WK_IN_WORKSPACE` | `1` |
| `WK_SESSION` | `credo-backend-release-v35` (repo-prefixed slug, no slashes) |
| `WK_BRANCH` | `release/v35` (canonical ref) |
| `WK_PATH` | `/Users/nate/_Work/credo-backend/.worktrees/release-v35` |

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
- Session names are **project-scoped**: the repo name is prefixed onto the
  branch slug, so `release/v35` in repo `credo-backend` becomes the session
  `credo-backend-release-v35`. (tmux doesn't love slashes, hence the slug;
  the prefix keeps two checkouts of *different* projects on the same branch
  — classically both `main`, e.g. via `wk adopt` — from colliding on one
  shared session.)
- Commands that take a branch (`open`, `close`, `rm`, `switch`, `cd`, …) still
  accept any of three forms: the real branch (`release/v35`), the bare slug
  (`release-v35`), or the full prefixed session name (`credo-backend-release-v35`).
- Worktree paths use the bare slug (no prefix): `<repo>/.worktrees/release-v35`.

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

# 3a. Intervene on a wedged or wrong-direction task
wk task-cancel fix-tenant-500s       # kill the agent, keep the worktree
wk task-retry  fix-tenant-500s       # re-run the agent on the same task.md

# 3b. Review and integrate
git -C ~/_Work/credo-backend/.worktrees/fix-tenant-500s diff main..
wk task-merge fix-tenant-500s         # --no-ff merge commit (default)
wk task-merge fix-tenant-500s --squash # squash into one commit
wk task-merge fix-tenant-500s --rm     # merge, then tear down the task workspace
wk task-merge fix-tenant-500s --into main  # target an orchestrator explicitly
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
wk new <branch> --layout laptop  # force a layout (wide|laptop); default auto-detects
wk open <branch>                 # create-or-attach a branch workspace (forgiving)
wk open <number|pr-url>          # open a pull request (same as `wk pr`)
wk open <issue-url|KEY>          # resolve an issue (e.g. DEV-6266) to its PR, else start a branch
wk open --pick                   # fzf over all branches, open the chosen one
wk pr <number|github-pr-url>     # open a pull request (explicit PR-only verb)
wk adopt [dir]                   # wrap an existing checkout (default: cwd) in a session
wk close [branch]                # kill session, keep worktree (default: current)
wk rm [branch]                   # destroy session + worktree + branch (default: current)
wk task <prompt>                 # Claude names a branch, launches with prompt
wk task --auto <prompt>          # headless task (claude -p, output to .wk/output.md)
wk switch [branch]               # switch to existing workspace; fzf if no arg
wk list                          # show all workspaces with status
wk rm <branch>                   # destroy session + worktree
wk restore [branch]              # rebuild tmux session(s) for existing worktrees
wk restore --list                # show which worktrees would be restored (dry-run)
wk restore                       # on a TTY: fzf multi-select picker (tab to mark)
wk restore --all                 # rebuild every missing session, skip the picker
wk relayout [--layout wide|laptop] # rebuild the layout in the current session (re-detects)
wk rebalance                     # reset pane sizes to the current layout's defaults (prefix M-w)
wk refresh-agents [branch|--all] # regenerate .wk/AGENTS.md and ORCHESTRATOR.md
wk cd [branch]                   # print worktree path (for shell cd integration)
wk task-status [branch]          # status table / detail of task workspaces
wk task-output <branch> [-n N]   # dump a task's .wk/output.md (--follow streams)
wk task-merge <branch>           # merge task branch into orchestrator's branch
wk sidebar                       # the dashboard renderer (runs in pane.1)
wk dashboard                     # cross-workspace overview session
wk version                       # print the wk version (also `wk --version` / `-V`)
```

---

## Useful env vars

| var | default | what |
|---|---|---|
| `WK_AGENT_CMD` | `claude -c \|\| claude` | command run in the agent pane |
| `WK_LAYOUT` | _(auto)_ | force a layout profile: `wide` or `laptop` (overrides auto-detect) |
| `WK_WIDE_COLS` | `220` | auto-detect threshold: clients ≥ this many cols get `wide`, else `laptop` |
| `WK_WORKTREE_ROOT` | `<repo>/.worktrees/` | where to put worktrees |
| `WK_PR_REPO_ROOT` | `~/_Work` | where `wk open`/`wk pr` look for a PR-by-URL's local clone |
| `WK_PR_SEARCH_OWNER` | current repo's `origin` owner | GitHub org `wk open <issue>` searches for the issue's PR |
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
