#!/bin/bash
# SessionStart hook: detect and auto-recover a clobbered user settings.json.
#
# Failure mode (recurring): the user-global ~/.claude/settings.json is silently
# truncated to a near-empty stub — the entire `enabledPlugins` and
# `extraKnownMarketplaces` blocks vanish, so the coordinator/deep-research/
# game-dev/holodeck/project-rag plugins all go DARK. The session runs degraded
# (no coordinator doctrine, no MCP, no domain agents) and the operator usually
# only notices when something that should work doesn't. Recovered by hand 3+
# times (git log: 1ad65df0 "chore(recovery): settings ... drop", 13ffa3db
# "... dropped ... by CRLF race").
#
# Why a sibling to check-dropped-tracked-files.sh and not an extension of it:
# that hook detects unstaged worktree DELETIONS (`git ls-files --deleted`). A
# clobber is a MODIFICATION (truncation), so the path is still present and
# tracked — it slips past the deletion detector entirely. Different signal,
# different remedy (auto-restore vs. warn).
#
# Why this lives in the PLUGIN hooks.json, not user settings.json: a guard
# configured inside settings.json would be wiped by the very clobber it exists
# to catch. Plugin hooks load from the plugin manifest, so this survives.
#
# Why it protects EVERY session (not just cwd=~/.claude): the file at risk is
# always ${CLAUDE_CONFIG_DIR:-$HOME/.claude}/settings.json regardless of the
# session's working directory. We target that fixed path, and the restore
# source is a cwd-independent snapshot — so a session opened in any project
# still gets the guard.
#
# Restore source priority:
#   1. .settings-last-good.json snapshot — refreshed on every HEALTHY boot.
#      cwd-independent; works for OSS installs where ~/.claude is not a git repo.
#   2. git HEAD of the config dir — fallback when no snapshot exists yet AND
#      ~/.claude is a git repo with a healthy committed settings.json.
#
# No-snapshot-no-opinion: the snapshot is BOTH the restore source AND the
# evidence that "this install previously had plugins enabled." A genuinely
# minimal install (0 enabled plugins) never writes a snapshot, so it never
# gets a false restore. This is what makes auto-restore safe to default on.
#
# Always exits 0 — never blocks session start. Output (raw text) becomes
# additionalContext injected into the session.

# --- Drain stdin (mirror existing hook pattern; no field needed) ---
if command -v timeout &>/dev/null; then
  timeout 2 cat >/dev/null 2>&1 || true
else
  cat >/dev/null 2>&1 || true
fi

# --- jq is the JSON-parsing norm across coordinator hooks; skip loudly if absent
#     (sentinel-to-stderr per plugin-session-start-hooks.md Rule 3) ---
if ! command -v jq &>/dev/null; then
  echo "[coordinator] guard-settings-integrity: jq not on PATH — skipped." >&2
  exit 0
fi

CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
SETTINGS="$CONFIG_DIR/settings.json"
SNAPSHOT="$CONFIG_DIR/.settings-last-good.json"
CLOBBER_BAK="$CONFIG_DIR/.settings-clobbered.bak"

[[ -f "$SETTINGS" ]] || exit 0

# --- Health predicate: parses as JSON AND .enabledPlugins is a non-empty
#     OBJECT. `jq -e` exits non-zero on false/null/empty-result/parse-error, so
#     this one call covers "corrupt JSON", "stub", and "no plugins" together.
#     The `objects` filter is load-bearing: it drops non-object values, so a
#     garbage scalar like `"enabledPlugins": "false"` (whose string length is
#     5 > 0) is correctly classified UNHEALTHY rather than passing and then
#     poisoning the snapshot. A non-empty object whose values are all `false`
#     still reads healthy by design — requiring a `true` value would
#     false-restore over a user who has legitimately disabled every plugin. ---
is_healthy() {
  jq -e '(.enabledPlugins | objects | length) > 0' "$1" >/dev/null 2>&1
}

# --- Atomic same-dir write (mv is atomic on one filesystem; PID-suffixed temp
#     avoids collision between concurrent sessions) ---
atomic_copy() {  # src dst
  local src="$1" dst="$2" tmp
  tmp="${dst}.tmp.$$"
  cp -- "$src" "$tmp" 2>/dev/null || return 1
  mv -f -- "$tmp" "$dst" 2>/dev/null || { rm -f -- "$tmp"; return 1; }
}

if is_healthy "$SETTINGS"; then
  # Healthy: keep the snapshot fresh, but only write on actual change (avoid
  # mtime churn + needless disk writes every boot). Concurrent identical writes
  # are harmless (same content, atomic mv).
  if [[ ! -f "$SNAPSHOT" ]] || ! cmp -s "$SETTINGS" "$SNAPSHOT"; then
    atomic_copy "$SETTINGS" "$SNAPSHOT" || true
  fi
  exit 0
fi

# --- Unhealthy: settings.json is a stub / corrupt / lost its plugins. Recover. ---
RESTORED_FROM=""
if [[ -f "$SNAPSHOT" ]] && is_healthy "$SNAPSHOT"; then
  # The forensic backup is best-effort: a failed backup (read-only path, lock,
  # full disk) must NOT short-circuit the actual recovery — otherwise the user
  # is left with the clobbered file AND no restore, the exact outcome the guard
  # exists to prevent. So `|| true` the backup and gate RESTORED_FROM purely on
  # the restore succeeding.
  atomic_copy "$SETTINGS" "$CLOBBER_BAK" || true
  if atomic_copy "$SNAPSHOT" "$SETTINGS"; then
    RESTORED_FROM="snapshot (.settings-last-good.json)"
  fi
elif git -C "$CONFIG_DIR" rev-parse --git-dir >/dev/null 2>&1; then
  # Snapshot absent/unusable but config dir is a git repo. Materialize the
  # committed settings.json to a temp file (avoid piping into jq via /dev/stdin
  # — unreliable on Git-Bash), health-check it, then swap it in. `HEAD:./` is
  # cwd-relative so it resolves correctly when CONFIG_DIR is not the repo root.
  HEAD_TMP="${SETTINGS}.head.$$"
  if git -C "$CONFIG_DIR" show "HEAD:./settings.json" > "$HEAD_TMP" 2>/dev/null \
     && is_healthy "$HEAD_TMP"; then
    atomic_copy "$SETTINGS" "$CLOBBER_BAK" || true   # best-effort, never blocks restore
    if mv -f -- "$HEAD_TMP" "$SETTINGS" 2>/dev/null; then
      RESTORED_FROM="git HEAD"
    else
      rm -f -- "$HEAD_TMP"
    fi
  else
    rm -f -- "$HEAD_TMP"
  fi
fi

if [[ -n "$RESTORED_FROM" ]]; then
  cat <<EOF

╔══════════════════════════════════════════════════════════════════╗
║  ✓  settings.json WAS CLOBBERED — AUTO-RESTORED from ${RESTORED_FROM}
║
║  The user settings.json had lost its \`enabledPlugins\` block (the
║  recurring stub-truncation / CRLF-race / harness-drop failure mode),
║  which silently disables ALL plugins for the session. It has been
║  restored on disk, and the clobbered copy saved to:
║      ${CLOBBER_BAK}
║
║  This session already loaded the BROKEN settings at boot, so the
║  plugins are still down RIGHT NOW.
║  Action: surface this to the PM as your first message and recommend
║  running  /reload-plugins  (or restarting the session) to pick up the
║  restored config before doing any plugin-dependent work.
╚══════════════════════════════════════════════════════════════════╝

EOF
else
  cat <<EOF

╔══════════════════════════════════════════════════════════════════╗
║  ⚠  settings.json LOOKS CLOBBERED (no \`enabledPlugins\`) — and there
║     is NO known-good snapshot or git HEAD to restore from.
║
║  Action: if plugins SHOULD be enabled, surface this to the PM — the
║  settings.json needs a hand-restore, after which this guard will
║  snapshot it on the next healthy boot. If the install genuinely has no
║  plugins enabled, this is expected; no action needed.
╚══════════════════════════════════════════════════════════════════╝

EOF
fi

exit 0
