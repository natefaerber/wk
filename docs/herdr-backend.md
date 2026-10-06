# herdr backend for wk

Status: proposed (2026-10-06). Reviewed by Codex; findings folded in. Targets herdr 0.9.3, Claude Code 2.1.289.

## Decisions
- Keep tmux, behind a backend seam.
- Retire headless `wk task --auto` on the herdr backend only (open decision; see below). tmux keeps it.

## Principles (changed after review)
1. **wk owns git; herdr owns terminals.** `resolve_workspace()` / `open_pr_ref()` keep creating
   worktrees (tracking branches, fork PRs, strict-new, fetch). herdr only *opens* the resolved
   checkout via `workspace create --cwd <wt>` + `layout.apply`. `herdr worktree create` is not used.
2. **Ownership is per-workspace, recorded on disk**, not inferred from `HERDR_ENV`.
   `.wk/backend` = `{backend, herdr_workspace_id, agent_name}`; resolution reads it, then verifies
   live (workspace still exists on this server), else treats as closed.
3. **Durable state lives in `.wk/`, not in herdr.** herdr lifecycle states are UI hints only
   (`done` ≈ idle-and-unseen, not "task finished"). Pane reads are snapshots, not transcripts.

## Feature mapping
| wk | herdr backend |
|---|---|
| session build | `workspace create --cwd --label <repo>/<branch> --env WK_*` → `layout.apply` (per-leaf `env`) |
| `@wk` / `@wk-*` options | `.wk/backend` (ownership, durable) + `workspace report-metadata` tokens (display only) |
| layouts wide/laptop/minimal | `layout.apply` trees; sidebar pane dropped (herdr native sidebar) |
| `relayout` | new tab via `layout.apply`, close old tab (keep command) |
| `restore` | keep: rebuild closed workspaces from `git worktree list` + `.wk/` markers. herdr restart-resume covers only live-server restarts |
| `rebalance` | drop (no `@wk-layout` geometry to reset to under herdr) or reapply layout; decide in spike |
| sidebar, dashboard, `switch`, `cycle` | herdr sidebar / picker / agent panel. **Gaps:** `cycle last`, alpha cycling, hub's closed-worktree inventory → keep `wk list` / hub popup as a herdr `[[keys.command]] type=popup` |
| `rm` | close herdr workspace, then git remove + branch delete in a **detached** process (keep `_rm-detached`); abort on removal failure; keep `--keep-branch` |
| `close` | close herdr workspace, keep worktree |
| `task` | open workspace → `agent start <name> --kind claude` → `agent prompt`. Name = slug truncated to 32 chars with short hash on collision (`[a-z][a-z0-9_-]{0,31}`) |
| `task-cancel` | **close workspace only; keep worktree + .wk/** (current contract) |
| `task-retry` | re-prompt from `.wk/task.md` in fresh agent pane |
| `task-status` | read `.wk/status` (durable, hook-written); herdr state shown as secondary |
| `task-output [--follow]` | Claude transcript (JSONL by session id) rendered, not `agent read` |
| `cd`, `is-wk-session`, `refresh-agents`, `WK_AGENT_CMD` | keep; `is-wk-session` checks `.wk/backend` |
| wk.conf bindings | herdr `[[keys.command]]` snippet shipped by install.sh |

## Claude Code integration (wk plugin)
- **Stop / Notification / SessionEnd hooks** write `.wk/status` (`working|waiting|blocked|ended`,
  timestamp, session id). This is the durable task-result protocol replacing `.wk/done` and
  `@wk-task-orch` messaging; orchestrator polls files or `herdr agent wait` then confirms via file.
- **SessionStart hook** injects `.wk/task.md` + workspace facts as additionalContext; resolves the
  worktree root via `git rev-parse` so it works from subdirectories; no-op outside wk.
- **Resume:** `.wk/session-id` UUID; first launch `--session-id`, later `--resume`; if resume fails
  (transcript gone), fall back to fresh with a new id and record it. herdr's
  `resume_agents_on_restore` owns *server restarts*; wk owns *reopen after close*. `-n <branch>`.
- Ship herdr's skill beside wk's; `wk doctor` checks `herdr integration status` reports claude current.

## Phases
0. **Fix-first (independent PR, also benefits tmux):** in `wk new` / `wk open`, write `.wk/task.md` *before* agent launch
   (today `_build_and_attach` builds the session, then `_announce_handoff`; `wk task` already writes first).
1. **Spikes:** does `workspace create --env` reach the root shell and user-split panes; `layout.apply`
   on an existing workspace; `agent start` failure modes (`agent_not_ready`, timeouts); server
   version check (`herdr status server`) vs client; Claude hook payloads available for `.wk/status`.
2. **Backend contract + tests before moving calls:** define ops (open, close, remove, exists,
   list, start_agent, prompt, status) and test partial creation, missing server, mixed ownership,
   cancel preserves files, ambiguous agent outcomes (never blind re-prompt).
3. Move tmux code behind the contract (behaviour-neutral; existing tests green).
4. herdr backend: open/new/pr/adopt/close/rm/restore/relayout.
5. Tasks on herdr + hooks (`.wk/status`, SessionStart, session-id).
6. Docs: CHEATSHEET, `_AGENTS_MD`, SKILL.md, CLAUDE.md; herdr keys snippet in install.sh.

## Open decision: `wk task --auto` under herdr

Today `--auto` runs `claude -p "$(cat .wk/task.md)" | tee .wk/output.md`, touches `.wk/done`, and
pings the spawning orchestrator via `@wk-task-orch`. The agent is one-shot: no follow-ups, no
approvals, and the transcript is the tee'd log.

Proposal: on herdr, `wk task` always launches an interactive agent. Fan-out still works (spawn
several with `--no-attach`); completion comes from `.wk/status` (hook-written) instead of
`.wk/done`; output comes from the Claude transcript instead of `.wk/output.md`. The orchestrator can
send follow-ups with `herdr agent prompt`. Cost: an agent that hits a permission prompt waits
(`blocked`) instead of failing fast, so unattended runs need an explicit permission mode.
