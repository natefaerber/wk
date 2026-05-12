#!/usr/bin/env bash
# install.sh — install (or uninstall) the `wk` tmux workspace manager.
#
# Files placed:
#   ~/.local/bin/wk                              (the CLI)
#   ~/.config/tmux/bin/wk-resurrect-filter       (resurrect hook helper)
#   ~/.config/tmux/conf/wk.conf                  (tmux bindings + hook config)
#   ~/.config/fish/functions/cdw.fish            (fish helper for `cd`)
#
# Config edits:
#   ~/.config/tmux/tmux.conf — adds a `source-file` line for wk.conf
#                              (idempotent; skipped if already present)
#
# Usage:
#   ./install.sh                  Copy files, edit tmux.conf
#   ./install.sh --link           Symlink files from this directory instead
#   ./install.sh --dry-run        Print actions, change nothing
#   ./install.sh --uninstall      Remove everything wk installed
#   ./install.sh --help           Show this help
#
# Re-running is safe. Switching between --link and --copy modes is safe
# (the installer replaces the existing file/link as needed).

set -euo pipefail

# ── colors ──────────────────────────────────────────────────────────────────
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  C_BOLD=$'\033[1m';  C_DIM=$'\033[2m';  C_RESET=$'\033[0m'
  C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'; C_RED=$'\033[31m'; C_BLUE=$'\033[34m'
else
  C_BOLD=; C_DIM=; C_RESET=; C_GREEN=; C_YELLOW=; C_RED=; C_BLUE=
fi

# shellcheck disable=SC2032  # `info` is also a tmux subcommand; calls below to `tmux info` are unrelated to this function
info()  { printf '%s•%s %s\n' "$C_BLUE" "$C_RESET" "$*"; }
ok()    { printf '%s✓%s %s\n' "$C_GREEN" "$C_RESET" "$*"; }
warn()  { printf '%s!%s %s\n' "$C_YELLOW" "$C_RESET" "$*" >&2; }
err()   { printf '%s✗%s %s\n' "$C_RED" "$C_RESET" "$*" >&2; }
step()  { printf '\n%s%s%s\n' "$C_BOLD" "$*" "$C_RESET"; }

# ── argument parsing ────────────────────────────────────────────────────────
MODE=copy        # copy | link
DRY_RUN=0
UNINSTALL=0

usage() {
  sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --link)       MODE="link" ;;
    --copy)       MODE="copy" ;;
    --dry-run|-n) DRY_RUN=1 ;;
    --uninstall)  UNINSTALL=1 ;;
    --help|-h)    usage 0 ;;
    *)            err "unknown argument: $1"; usage 1 ;;
  esac
  shift
done

# ── paths ───────────────────────────────────────────────────────────────────
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

BIN_DIR="$HOME/.local/bin"
TMUX_DIR="$HOME/.config/tmux"
TMUX_CONF_DIR="$TMUX_DIR/conf"
TMUX_BIN_DIR="$TMUX_DIR/bin"
TMUX_CONF="$TMUX_DIR/tmux.conf"
FISH_FN_DIR="$HOME/.config/fish/functions"

# (source, destination) pairs. Mode (copy/link) applies uniformly.
FILES=(
  "wk:$BIN_DIR/wk:0755"
  "wk-resurrect-filter:$TMUX_BIN_DIR/wk-resurrect-filter:0755"
  "wk.conf:$TMUX_CONF_DIR/wk.conf:0644"
  "cdw.fish:$FISH_FN_DIR/cdw.fish:0644"
)

# The line we'll add to tmux.conf. Quoted as it'll appear in the file.
TMUX_SOURCE_LINE='source-file ~/.config/tmux/conf/wk.conf'

# ── dry-run wrapper ─────────────────────────────────────────────────────────
# Echoes the command in dry-run mode, runs it otherwise. Quotes args for clarity.
do_() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '%s  $%s' "$C_DIM" "$C_RESET"
    printf ' %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}

# ── preflight ───────────────────────────────────────────────────────────────
check_source_files() {
  local missing=0
  for entry in "${FILES[@]}"; do
    IFS=: read -r src _ _ <<<"$entry"
    if [ ! -f "$SRC_DIR/$src" ]; then
      err "missing source file: $SRC_DIR/$src"
      missing=1
    fi
  done
  [ "$missing" -eq 0 ] || exit 1
}

check_link_mode_stable_path() {
  # Symlinks need a stable source path. Refuse common ephemeral locations.
  case "$SRC_DIR" in
    /tmp/*|/var/tmp/*|*/Downloads/*|*/Desktop/*)
      err "refusing to symlink from $SRC_DIR"
      err "move the source files somewhere stable first (e.g. ~/code/wk),"
      err "or re-run without --link to copy instead"
      exit 1
      ;;
  esac
}

check_dependencies() {
  local required=(tmux git uv fzf)
  local optional=(eza fish)
  local missing_req=()

  for dep in "${required[@]}"; do
    command -v "$dep" >/dev/null 2>&1 || missing_req+=("$dep")
  done
  for dep in "${optional[@]}"; do
    command -v "$dep" >/dev/null 2>&1 || warn "optional dependency missing: $dep"
  done

  if [ ${#missing_req[@]} -gt 0 ]; then
    err "missing required dependencies: ${missing_req[*]}"
    err "install them with your package manager, then re-run"
    exit 1
  fi
}

# ── install one file ────────────────────────────────────────────────────────
# Args: source-filename, dest-path, mode (e.g. "0755")
install_file() {
  local src="$SRC_DIR/$1"
  local dest="$2"
  local perm="$3"
  local dest_dir
  dest_dir="$(dirname "$dest")"

  do_ mkdir -p "$dest_dir"

  # Decide if the existing dest is already correct.
  if [ "$MODE" = link ]; then
    if [ -L "$dest" ] && [ "$(readlink "$dest")" = "$src" ]; then
      info "ok: $dest → $src"
      return
    fi
    # Anything else there (file or wrong-target symlink) must go.
    [ -e "$dest" ] || [ -L "$dest" ] && do_ rm -f "$dest"
    do_ ln -s "$src" "$dest"
    ok "linked: $dest → $src"
  else
    # copy mode
    if [ -L "$dest" ]; then
      # An old symlink from a previous --link install; replace with a copy.
      do_ rm -f "$dest"
    elif [ -f "$dest" ] && cmp -s "$src" "$dest"; then
      # Existing copy is identical; only fix perms if needed.
      do_ chmod "$perm" "$dest"
      info "ok: $dest"
      return
    fi
    do_ cp "$src" "$dest"
    do_ chmod "$perm" "$dest"
    ok "copied: $dest"
  fi
}

# ── tmux.conf editing ───────────────────────────────────────────────────────
edit_tmux_conf() {
  if [ ! -f "$TMUX_CONF" ]; then
    warn "$TMUX_CONF does not exist; skipping source-file edit"
    warn "create it and add this line manually:"
    warn "    $TMUX_SOURCE_LINE"
    return
  fi

  if grep -Fq "$TMUX_SOURCE_LINE" "$TMUX_CONF"; then
    info "ok: tmux.conf already sources wk.conf"
    return
  fi

  # Back up once, with a timestamp. Don't overwrite an existing backup from
  # an earlier run today (use a unique suffix per-install-event).
  local backup
  backup="$TMUX_CONF.wk-backup-$(date +%Y%m%d-%H%M%S)"
  do_ cp "$TMUX_CONF" "$backup"
  info "backup: $backup"

  # Find a sensible insertion point: right after the line that sources
  # bindings.conf. Falls back to end-of-file if that line isn't present.
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '%s  $%s edit %s to add %q\n' \
      "$C_DIM" "$C_RESET" "$TMUX_CONF" "$TMUX_SOURCE_LINE"
    return
  fi

  if grep -q 'bindings.conf' "$TMUX_CONF"; then
    # Insert after the *last* line containing bindings.conf.
    awk -v line="$TMUX_SOURCE_LINE" '
      { lines[NR] = $0; if ($0 ~ /bindings\.conf/) last = NR }
      END {
        for (i = 1; i <= NR; i++) {
          print lines[i]
          if (i == last) {
            print ""
            print "# wk (workspace manager) — installed by wk install.sh"
            print line
          }
        }
      }
    ' "$TMUX_CONF" > "$TMUX_CONF.new"
    mv "$TMUX_CONF.new" "$TMUX_CONF"
    ok "added source-file line after bindings.conf"
  else
    {
      printf '\n# wk (workspace manager) — installed by wk install.sh\n'
      printf '%s\n' "$TMUX_SOURCE_LINE"
    } >> "$TMUX_CONF"
    ok "appended source-file line to tmux.conf"
  fi
}

unedit_tmux_conf() {
  if [ ! -f "$TMUX_CONF" ]; then
    return
  fi
  if ! grep -Fq "$TMUX_SOURCE_LINE" "$TMUX_CONF"; then
    info "ok: tmux.conf has no wk source-file line"
    return
  fi
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '%s  $%s remove wk lines from %s\n' "$C_DIM" "$C_RESET" "$TMUX_CONF"
    return
  fi
  local backup
  backup="$TMUX_CONF.wk-backup-$(date +%Y%m%d-%H%M%S)"
  cp "$TMUX_CONF" "$backup"
  info "backup: $backup"
  # Remove both the comment marker and the source-file line, leaving
  # adjacent blank lines alone (fine for tmux).
  grep -v -F -e "$TMUX_SOURCE_LINE" \
              -e "# wk (workspace manager) — installed by wk install.sh" \
              "$TMUX_CONF" > "$TMUX_CONF.new"
  mv "$TMUX_CONF.new" "$TMUX_CONF"
  ok "removed wk lines from tmux.conf"
}

# ── verification ────────────────────────────────────────────────────────────
verify() {
  [ "$DRY_RUN" -eq 1 ] && return

  step "Verifying installation"

  # PATH check
  case ":$PATH:" in
    *":$BIN_DIR:"*)
      info "ok: $BIN_DIR is on PATH"
      ;;
    *)
      warn "$BIN_DIR is not on \$PATH"
      warn "fish:  set -Ux fish_user_paths $BIN_DIR \$fish_user_paths"
      warn "bash:  export PATH=\"$BIN_DIR:\$PATH\""
      ;;
  esac

  # CLI runs?
  if "$BIN_DIR/wk" --help >/dev/null 2>&1; then
    ok "wk --help runs successfully"
  else
    err "wk --help failed — see output of: $BIN_DIR/wk --help"
  fi

  # Reload tmux config if a server is running
  # shellcheck disable=SC2032,SC2033  # `tmux info` is a subcommand, not our info() function
  if tmux info >/dev/null 2>&1; then
    if tmux source-file "$TMUX_CONF" 2>/dev/null; then
      ok "reloaded tmux config"
    else
      warn "tmux is running but config reload failed; check syntax manually"
    fi
  else
    info "no tmux server running; config will load on next start"
  fi
}

# ── main ────────────────────────────────────────────────────────────────────
if [ "$UNINSTALL" -eq 1 ]; then
  step "Uninstalling wk"
  for entry in "${FILES[@]}"; do
    IFS=: read -r _ dest _ <<<"$entry"
    if [ -e "$dest" ] || [ -L "$dest" ]; then
      do_ rm -f "$dest"
      ok "removed: $dest"
    fi
  done
  unedit_tmux_conf
  [ "$DRY_RUN" -eq 1 ] && info "(dry run — nothing actually changed)"
  printf '\n'
  ok "uninstalled"
  exit 0
fi

if [ "$DRY_RUN" -eq 1 ]; then
  step "Installing wk (mode: $MODE, dry-run)"
else
  step "Installing wk (mode: $MODE)"
fi
check_source_files
[ "$MODE" = link ] && check_link_mode_stable_path
check_dependencies

step "Installing files"
for entry in "${FILES[@]}"; do
  IFS=: read -r src dest perm <<<"$entry"
  install_file "$src" "$dest" "$perm"
done

step "Editing tmux.conf"
edit_tmux_conf

verify

[ "$DRY_RUN" -eq 1 ] && info "(dry run — nothing actually changed)"

printf '\n'
ok "done"
printf '\nNext steps:\n'
printf '  • Try it:  %swk new test-branch%s\n' "$C_BOLD" "$C_RESET"
printf '  • Switch:  %sprefix W%s  (fzf picker of wk workspaces)\n' "$C_BOLD" "$C_RESET"
printf '  • Sesh:    your existing %sprefix K%s picker also lists wk sessions\n' "$C_BOLD" "$C_RESET"
