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
  `~/_Work/credo-backend/.worktrees/release/v35` and checks it out.
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

wk has three layout profiles. The **widescreen** layout (3 columns, 4 panes) is
the default on wide displays; the **laptop** layout (2 columns) kicks in on
narrow ones; **minimal** (2 panes, no sidebar) is opt-in.
Either way, lazygit is summoned on demand with `prefix M-g` (full-screen popup),
not an always-on pane.

### Widescreen (`wide`)

```
┌──────────┬──────────────────────┬──────────────────┐
│ sidebar  │                      │                  │
│ pane.1   │   agent (Claude)     │   terminal       │
├──────────┤   pane.3             │   pane.4         │
│ shell    │                      │                  │
│ pane.2   │                      │                  │
└──────────┴──────────────────────┴──────────────────┘
```

- **sidebar** — passive read-only dashboard of all wk workspaces (auto-refreshes
  every 3s; tune with `WK_SIDEBAR_REFRESH`)
- **shell** — a login shell, stacked under the sidebar for quick commands
- **agent** — Claude Code (or whatever `WK_AGENT_CMD` is set to)
- **terminal** — the right column; a generous login shell (kept wide so the
  agent doesn't sprawl on a big display)
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

### Minimal (`minimal`)

```
┌──────────────────────────────────────┬──────────────────┐
│        agent (Claude Code)           │   terminal       │
│        pane.1                        │   pane.2         │
└──────────────────────────────────────┴──────────────────┘
```

Two panes, no sidebar — for a single focused task, a narrow split, or a
screen-share where a live workspace list is noise. `wk ls` and `prefix W` still
show everything the sidebar would, on demand instead of always-on. Aliased as
`solo`.

### Choosing a layout

Precedence, highest first:

1. `--layout wide|laptop|minimal` on `wk new` / `wk open` / `wk task` / `wk relayout`
2. `WK_LAYOUT=wide|laptop|minimal` (e.g. set in your laptop's shell profile)
3. `layout = minimal` in [`<repo>/.wk/config` or `~/.config/wk/config`](#config-files)
4. **auto-detect** from display width — a client at least `WK_WIDE_COLS`
   (default 220) columns wide gets `wide`, narrower gets `laptop`

Docked and undocked the same machine? Just `wk relayout` after switching
displays — it re-detects.

`prefix M-w` (`wk rebalance`) resets pane sizes to the current layout's defaults.

---

## Switching workspaces

The sidebar pane is **read-only** — you don't navigate into it. To switch:

| binding | what |
|---|---|
| `prefix W` | the **hub** — popup picker (fzf) over this repo's workspaces **and every running wk session across all repos** (a `repo` column disambiguates); switch on Enter, from anywhere. A finished `--auto` task shows ✓. |
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
| `WK_PATH` | `/Users/nate/_Work/credo-backend/.worktrees/release/v35` |
| `WK_ISSUE_KEY` | `LPE-1234` (only when the branch carries a configured key) |
| `WK_ISSUE_URL` | `https://linear.app/acme/issue/LPE-1234` (only when the prefix is mapped to a tracker) |

And `.wk/AGENTS.md` in the worktree root documents the layout + commands for
the agent. Reference it from your project `CLAUDE.md` to give Claude
auto-context:

```markdown
@.wk/AGENTS.md
```

---

## Branch naming gotchas

- **Generated names use `<type>/<slug>`.** When wk names a branch for you
  (`wk task`, or `wk open` without an explicit name), it asks Claude for
  `fix/flaky-session-test` — one of `feat`, `fix`, `chore`, `docs`, `refactor`,
  `test`, `perf`, `spike`, then a 2-6 word hyphenated slug. Override the type
  vocabulary with `WK_BRANCH_TYPES`. Unprefixed names stay valid; the
  deterministic fallback (used when `claude` is unavailable) produces one.
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
- Worktree paths keep the branch's hierarchy: `<repo>/.worktrees/release/v35`.
  Prefixes (`feat/`, `fix/`, `chore/`) stay browsable subdirs, and the layout
  matches a hand-rolled `git worktree add`. Only session names flatten to a
  slug — tmux rejects `/`. Worktrees created before 0.10 keep their flat
  paths and keep working; wk reads the real path from git.

---

## Issue refs (Jira / Linear)

`wk open` accepts a ticket instead of a branch. It finds the PR for that issue
(current repo, then org-wide) and opens its workspace; with no PR it starts a
branch named after the key off `--base`.

```sh
wk open https://acme.atlassian.net/browse/DEV-6266   # Jira URL
wk open https://linear.app/acme/issue/ENG-123/fix-it # Linear URL
wk open DEV-6266                                     # bare key
```

Tracker **URLs** always work. **Bare keys** are ambiguous — `API-2` could be a
ticket or a branch — so tell wk which projects are real. Your trackers follow
*you*, not one repo, so set this once globally:

```ini
# ~/.config/wk/config
issue_prefixes   = LPE:linear, DEV:jira
linear_workspace = acme                 # linear.app/<workspace>
jira_site        = acme.atlassian.net
```

The `:tracker` suffix is optional and only affects **URL building** — matching
never needs it. Tag it and wk hands the agent a link it can go read (see
below); leave it off (`issue_prefixes = LPE, DEV`) and matching still works.

A repo with its own keys can override it in `<repo>/.wk/config`, and
`WK_ISSUE_PREFIXES` beats both. With prefixes configured, matching
gets both stricter and more forgiving:

| ref | unconfigured | `issue_prefixes = LPE, ENG` |
|---|---|---|
| `LPE-1544` | ticket | ticket |
| `lpe-1544` | branch name | ticket |
| `ENG-123/fix-it` (Linear picker) | branch name | ticket |
| `eng-123-fix-it` (Linear "copy git branch name") | branch name | ticket |
| `API-2` (not a real project) | **ticket** ← false positive | branch name |

If a workspace already exists for the issue's branch, `wk open <key>` reopens it
rather than re-resolving the ticket — so you land back where you were working,
not on whatever PR the search turns up today.

### Handing the ticket to the agent

wk resolves keys against **GitHub, not the tracker** — it never reads a ticket
body, and needs no Jira/Linear credentials. What it does instead is tell the
agent where the ticket lives. Any workspace whose branch carries a configured
key (`lpe-1234`, or `fix/LPE-1234-tenant-500s`) gets:

| var | example |
|---|---|
| `WK_ISSUE_KEY` | `LPE-1234` |
| `WK_ISSUE_URL` | `https://linear.app/acme/issue/LPE-1234` |

and its `.wk/task.md` opens with a **Ticket:** link. That's what makes
"spin up a workspace for LPE-1234" work end-to-end: the agent can see from the
URL that LPE is Linear and DEV is Jira, and go read the right one. `WK_ISSUE_URL`
is omitted when the prefix has no `:tracker` — the agent is told to ask rather
than guess.

---

## Handoff briefs (`.wk/task.md`)

A workspace outlives the conversation that created it. The agent that opens it
later never saw that conversation — so wk writes the intent down.

Pass `--task` when you create one:

```sh
wk open fix/tenant-500s --task "500s on the tenant endpoint since the caching \
  change; reproduce first, don't touch the schema"
wk new  feat/bulk-export --task "..."
wk task "investigate the tenant 500s"     # task always writes one
```

wk one-shots `claude -p` to turn that into `.wk/task.md` — **Goal**, **Context**,
**Acceptance** — and the agent in the workspace is told to read it first. If
`claude` is missing, slow, or returns something unstructured, you get a skeleton
with your own words preserved verbatim under Goal; workspace creation never
fails over this.

Existing briefs are never overwritten, so reopening a workspace won't wipe notes
the agent has been keeping. Without `--task` you get the empty skeleton to fill
in yourself.

## Config files

Two layers, same format — plain `key = value` with `#` comments:

| file | scope | use it for |
|---|---|---|
| `~/.config/wk/config` | every repo | your trackers, your preferred layout |
| `<repo>/.wk/config` | one repo (**main checkout**) | a project that differs from your default |

```ini
# ~/.config/wk/config
issue_prefixes = LPE, ENG
layout = minimal
```

Precedence per key: **env var → repo → user**. Repo beats user so a project can
override your global default; an env var is a deliberate one-off, so it wins
outright. (Honours `XDG_CONFIG_HOME`.)

The repo file lives in the main checkout, not a worktree — worktree `.wk/` dirs
are wk-managed scratch, gitignored by their own `.gitignore`. The repo one is
yours to commit if you want the default shared with your team.

| key | values | env override |
|---|---|---|
| `layout` | `wide` \| `laptop` \| `minimal` | `WK_LAYOUT` |
| `issue_prefixes` | e.g. `LPE:linear, DEV:jira` | `WK_ISSUE_PREFIXES` |
| `linear_workspace` | e.g. `acme` | — |
| `jira_site` | e.g. `acme.atlassian.net` | — |

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
wk new <branch> --layout laptop  # force a layout (wide|laptop|minimal); default auto-detects
wk new <branch> --task "..."     # write a .wk/task.md handoff brief for the agent
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
wk relayout [--layout wide|laptop|minimal] # rebuild the layout in the current session (re-detects)
wk rebalance                     # reset pane sizes to the current layout's defaults (prefix M-w)
wk refresh-agents [branch|--all] # regenerate .wk/AGENTS.md and ORCHESTRATOR.md
wk cd [branch]                   # print worktree path (for shell cd integration)
wk task-status [branch]          # status table / detail of task workspaces
wk task-output <branch> [-n N]   # dump a task's .wk/output.md (--follow streams)
wk task-merge <branch>           # merge task branch into orchestrator's branch
wk sidebar                       # the dashboard renderer (runs in pane.1)
wk dashboard                     # cross-workspace overview session
wk version                       # print the wk version (also `wk --version` / `-V`)
wk doctor                        # check deps + whether the tmux bindings are installed
```

---

## Useful env vars

| var | default | what |
|---|---|---|
| `WK_AGENT_CMD` | `claude -c \|\| claude` | command run in the agent pane |
| `WK_LAYOUT` | _(auto)_ | force a layout profile: `wide`, `laptop`, or `minimal` (overrides auto-detect) |
| `WK_BRANCH_TYPES` | `feat,fix,chore,docs,refactor,test,perf,spike` | allowed `<type>/` branch prefixes |
| `WK_ISSUE_PREFIXES` | _(none)_ | project/team keys (`LPE,ENG`) that make issue-ref matching exact; usually set in `~/.config/wk/config` instead |
| `WK_WIDE_COLS` | `220` | auto-detect threshold: clients ≥ this many cols get `wide`, else `laptop` |
| `WK_WORKTREE_ROOT` | `<repo>/.worktrees/` | where to put worktrees |
| `WK_PR_REPO_ROOT` | `~/_Work` | where `wk open`/`wk pr` look for a PR-by-URL's local clone |
| `WK_PR_SEARCH_OWNER` | current repo's `origin` owner | GitHub org `wk open <issue>` searches for the issue's PR |
| `WK_SIDEBAR_REFRESH` | `3` | sidebar pane refresh interval in seconds |
| `WK_DASHBOARD_REFRESH` | `30` | `wk dashboard` refresh interval in seconds (min 1) |

---

## Install / update

### From source (full setup — installs tmux config and the fish `cd` helper)

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
