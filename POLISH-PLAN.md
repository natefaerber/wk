# wk Polish Round — execution-ready spec (plan of record)

Goal: make `wk` a tmux-powered Superset-lite — easy to use, agent-drivable —
within the current architecture (single-file CLI, thin tmux layer, NO TUI, NO
daemon, passive sidebar). Reviewed via two `/autoplan` passes + a red-team.

Autonomy: **hands-off → one green PR, human merges.** Build all stories on one
feature branch; run the full suite + paste `tmux list-panes` layout evidence
into the PR; stop at PR-open-green. Do NOT merge to main or release.

## Baked decisions (do not re-litigate)
- Hub stays `wk switch` / `prefix W` (not renamed).
- `task-merge` gains `--into <session>` (default current `#S`) to kill the
  "merge into itself" bug when fired from anywhere but the orchestrator.
- `--rm` deletes the child branch only after a `git branch --merged <orch>`
  check — NEVER `-D`. If not merged, keep + warn.
- Lazygit popup bound to **`prefix M-g`** (uppercase/M- per CLAUDE.md key rules;
  `g` lowercase is reserved for sesh). `display-popup -E -w 90% -h 90% -d <@wk-path>`.
- In-fzf hub keys: reuse `enter`=switch, `ctrl-n`=new, `ctrl-d`=rm; add
  `ctrl-x`=task-cancel. Output/merge are NOT bound inside fzf (tail -f never
  returns; merge is interactive). `enter` on a task row switches into its session.
- Done glyph `✓` (green), single source of truth = `.wk/done` file. CUT the
  redundant `@wk-task-done` tmux flag.
- Completion notify: `tmux display-message -t <@wk-task-orch>` + bell, fired by
  the child's auto-task command on completion. No poller, no daemon.
- mise "bindings not installed" detector: wk.conf sets `@wk-conf-loaded 1`;
  `wk doctor` reads it and prints the install hint if absent.
- **Merge-when-done latch: DEFERRED** to a supervised follow-up. Not in this round.
- Write the layout-geometry test BEFORE the Story-C refactor (self-verify signal).

## Stories (build in order)

### Story B — Close the loop (CLI-first)  [latch deferred]
- `wk task-merge <b> --into <session>` — explicit orchestrator target; default `#S`.
- `wk task-merge <b> --rm` — merge into orch, then teardown worktree+session;
  branch delete gated on `--merged` check.
- Completion signal: child's `--auto` command, after writing `.wk/done`,
  notifies the orchestrator (`@wk-task-orch` captured at spawn) via
  display-message + bell. Sidebar renders `✓` for done tasks (reads `.wk/done`).
- Accept: `task-merge --help` shows `--into`/`--rm`; new unit tests (mock `run`)
  for the merged-check delete + the notify call; `pytest -q` green;
  `pytest tests/test_docs_commands.py` green (AGENTS.md task section updated).

### Story A — The summoned hub (generalize `wk switch`)
- Merge live tasks into the picker list with state glyphs; auto-refresh.
- Non-blocking verbs only via fzf `--bind` execute+reload: switch/new/rm/cancel.
- Extend the `--header` to teach the task keys (discoverability, no separate menu).
- CLI parity: every verb keeps a headless twin (already true for new/rm/cancel).
- Accept: `_picker_line` + `_list-once` stay byte-identical (test both producers);
  a grep test asserts no blocking command (`tail -f`, `task-merge`) in the binds;
  `wk switch <branch>` still attaches headless (exit 0).

### Story C — Simpler layout (lazygit out + collapse shell/terminal)
- **First:** add a layout-geometry test/helper (expected index→role map per
  profile) + run the CLAUDE.md §4 `list-panes` recipe as a gated manual check.
- `_build_wide` → `sidebar | agent | terminal` (mirror `_build_laptop`); drop
  lazygit + redundant shell. New named width/pct constants (no inlining).
- Rewrite `_rebalance_wide` for the new index map.
- Remove `wk lg-cd` + `prefix M-g`(old)/`M-z`/`M-y`; add `prefix M-g` lazygit popup.
- Rewrite the `_AGENTS_MD` lazygit section + CHEATSHEET/CLAUDE.md layout diagrams.
- Accept: built wide session shows exactly 3 panes sidebar/agent/terminal;
  `wk rebalance` returns target sizes; `wk lg-cd --help` exits nonzero;
  `pytest tests/test_docs_commands.py` green (proves AGENTS.md rewrite).

### Story D — Onboarding
- `wk switch` on zero workspaces inside a popup renders a create prompt instead
  of dying (branch on interactive vs headless; keep headless exit code).
- `wk doctor`: bindings-installed check via `@wk-conf-loaded`; prints install hint.
- Accept: unit test that empty interactive `switch` doesn't `Exit(1)`; `wk doctor`
  exits 0 when sentinel set, prints hint + nonzero when unset.

## Feature complete = all 4 stories on the branch, `pytest -q` green (incl. new
layout-role + doctor tests), `tmux list-panes` evidence for both layouts pasted
into the PR body, PR open for human merge. No auto-merge, no release.
