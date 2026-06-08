# wk

A tmux-based workspace manager: every workspace is one git worktree + one tmux
session in a multi-pane layout that adapts to your display — a 5-pane
widescreen layout (sidebar · agent · shell · lazygit · terminal) or a 2-column
laptop layout. It's a single-file Python CLI (`uv run --script`, Typer + Rich)
plus a thin tmux-binding layer. Designed to live alongside
[sesh](https://github.com/joshmedeski/sesh) — wk sessions show up in sesh
pickers automatically.

```
wk open feat/login      # create-or-attach a worktree + tmux session for a branch
wk task "fix the 500s"  # spawn a parallel headless task on its own worktree
wk switch               # fzf-pick between running workspaces
wk rm feat/login        # tear it all down
```

---

## Which are you?

wk has two install paths for two different audiences. They are independent.

### 1. You want to run `wk` in your terminal  → install the CLI

This is the real tool. It runs in your terminal/tmux all day.

**Fastest (mise):**
```sh
mise use -g "github:natefaerber/wk[asset_pattern=wk,bin=wk]"
```
That drops the single portable `wk` script on your PATH. Requires `tmux`, `git`,
`uv`, and `fzf` (and optionally `fish`, `eza`, `lazygit`).

**Full keystroke experience (clone + install):** to also get the tmux bindings,
the narrow-pane lazygit config, and the fish `cd` helper:
```sh
git clone https://github.com/natefaerber/wk && cd wk
./install.sh            # copy files + wire up tmux.conf  (--link to symlink instead)
```
See [CHEATSHEET.md](./CHEATSHEET.md) for every binding and command.

### 2. You want Claude Code to drive `wk` for you  → install the plugin

The plugin ships the `/wk` skill so a Claude Code agent knows when and how to
open worktrees, spawn parallel tasks, and clean up — driving real tmux sessions
in your terminal.

```
/plugin marketplace add natefaerber/wk
/plugin install wk@wk-tools
```

> **The plugin does not install the `wk` CLI.** It teaches Claude to drive `wk`;
> it cannot drive a `wk` that isn't there. You still need the CLI on your PATH
> (path 1 above). The skill checks for it and tells you if it's missing.

---

## Layouts

wk picks a pane layout to match the display you open a workspace on:

- **widescreen** — the full 5-pane layout (sidebar · agent · lazygit on the
  sides, with shell + terminal), tuned for a wide monitor.
- **laptop** — 2 columns: the sidebar stacked over a terminal on the left, a
  full-height agent on the right. No lazygit or separate shell pane — on a
  narrow screen they cost more width than they're worth.

By default the layout is **auto-detected** from the display width when a session
is built. Force it per command with `--layout wide|laptop` (on `wk open` /
`wk new` / `wk relayout`), or globally with `WK_LAYOUT=wide|laptop` in your
shell profile. Docked and undocked the same machine? Just `wk relayout` after
switching displays — it re-detects. `prefix M-w` resets pane sizes to the
current layout's defaults. See [CHEATSHEET.md](./CHEATSHEET.md#pane-layout) for
the diagrams and the `WK_WIDE_COLS` auto-detect threshold.

---

## Versioning & upgrades

Two version numbers, kept in lockstep on each release tag (the release workflow
fails if `plugin.json` doesn't match the tag):

- **CLI** — released via GitHub tags. Upgrade with `mise upgrade wk`, or
  re-run `./install.sh` from a fresh clone.
- **Plugin** — `/plugin marketplace update wk-tools` then re-install.

Because the `/wk` skill defers all command flags to `wk --help` / CHEATSHEET
rather than re-listing them, a small version skew between the two is harmless.

---

## Docs

- [CHEATSHEET.md](./CHEATSHEET.md) — every binding, command, and workflow (the
  single source of truth for command flags).
- [CLAUDE.md](./CLAUDE.md) — architecture and design notes for developing wk
  itself.
- `wk --help` — Typer-generated help per command.
