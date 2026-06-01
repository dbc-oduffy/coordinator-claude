#!/usr/bin/env bash
# learn-lessons-config-update.sh — append normalized $PWD to the learn-lessons config if absent.
# Normalization: absolute path, lowercase on Windows (msys/cygwin), strip trailing slash, POSIX separators.
# Idempotent — silent no-op if already present.
set -e
CONFIG="$HOME/.claude/tasks/learn-lessons-config.md"
[[ -f "$CONFIG" ]] || { echo "config missing: $CONFIG" >&2; exit 1; }

# Normalize
cwd="$(realpath "$PWD" 2>/dev/null || readlink -f "$PWD" 2>/dev/null || echo "$PWD")"
# POSIX separators (already POSIX on bash; no-op on most shells)
cwd="${cwd%/}"  # strip trailing slash
# Lowercase on Windows
case "$OSTYPE" in
  msys*|cygwin*|win32*) cwd=$(echo "$cwd" | tr '[:upper:]' '[:lower:]') ;;
esac

# Append if absent (case-insensitive grep on Windows; literal otherwise)
case "$OSTYPE" in
  msys*|cygwin*|win32*) grep -i -Fxq "- $cwd" "$CONFIG" 2>/dev/null && exit 0 ;;
  *) grep -Fxq "- $cwd" "$CONFIG" 2>/dev/null && exit 0 ;;
esac

# Insert before the closing sentinel
tmp=$(mktemp)
awk -v cwd="$cwd" '/<!-- learn-lessons-config-end -->/ && !done {print "- " cwd; done=1} {print}' "$CONFIG" > "$tmp" && mv "$tmp" "$CONFIG"
echo "appended $cwd to $CONFIG"
