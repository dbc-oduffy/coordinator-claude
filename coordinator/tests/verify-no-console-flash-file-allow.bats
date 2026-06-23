#!/usr/bin/env bats
# verify-no-console-flash-file-allow.bats — coverage for the file-level allow marker
# in bin/verify-no-console-flash.sh (holodeck-em ask 2026-06-19).
#
# The `# verify-no-console-flash: file-allow — <rationale>` header marker (first 10
# lines) suppresses an entire file, for physically-Linux-only scripts where no Windows
# conhost can be allocated regardless of spawn shape. Test #3 also pins the upstream
# behavior that made the memo's proposal #2 (ps-path comment filter) already-resolved:
# a pure comment mentioning pwsh is not flagged.
#
# Determinism: fixture ROOT/coordinator-claude tree; verifier takes ROOT as $1.
# Portability (DR-148): bash >= 4 + BSD coreutils.

SCRIPT_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")" && pwd)"
SUBJECT="${SCRIPT_DIR}/../bin/verify-no-console-flash.sh"

setup() {
  TMP="$(mktemp -d)"
  TREE="${TMP}/coordinator-claude"   # COORD_ROOT = ROOT/coordinator-claude
  mkdir -p "$TREE"
}

teardown() { rm -rf "$TMP"; }

@test "flags a bare python -c spawn with no suppression (exit 1)" {
  printf '#!/usr/bin/env bash\npython -c "import sys; print(sys.version)"\n' > "${TREE}/probe.sh"
  run bash "$SUBJECT" "$TMP"
  [ "$status" -eq 1 ]
  [[ "$output" == *"probe.sh"* ]]
}

@test "file-allow header marker suppresses the whole file (exit 0)" {
  printf '#!/usr/bin/env bash\n# verify-no-console-flash: file-allow — Linux-only training pipeline\npython -c "import sys; print(sys.version)"\npython -c "import torch"\n' > "${TREE}/runpod_train.sh"
  run bash "$SUBJECT" "$TMP"
  [ "$status" -eq 0 ]
  [[ "$output" == *"OK:"* ]]
}

@test "a pure comment mentioning pwsh is not flagged (proposal #2 already handled upstream)" {
  printf '#!/usr/bin/env bash\n# we used to call pwsh here but stopped\necho hi\n' > "${TREE}/notes.sh"
  run bash "$SUBJECT" "$TMP"
  [ "$status" -eq 0 ]
  # Review: code-reviewer F10 — assert the OK summary line is present so a silent-pass
  # (empty output, no suppressed spawns at all) is distinguished from a true clean scan.
  [[ "$output" == *"OK:"* ]]
}

# ---------------------------------------------------------------------------
# Drive-letter path extraction in _is_suppressed (F7)
# ---------------------------------------------------------------------------

# Review: code-reviewer F7 — the sed in _is_suppressed strips `:lineno:content` with
#   sed -E 's/:[0-9]+:.*$//'
# which is drive-letter-safe: it strips the LAST `:lineno:` suffix, leaving `C:/path/file.sh`
# intact rather than splitting on the first `:` (which would yield `C`).
#
# A true Windows path (C:\...) cannot be created on macOS. Instead we unit-test the sed
# expression directly: feed it a synthetic `C:/path/file.sh:42:    python -c "code"` line
# and assert the extracted path is `C:/path/file.sh` (drive letter + forward-slash form,
# as written by grep on MINGW/git-bash or in fixture strings).
#
# This does not execute the verifier end-to-end (the path doesn't exist on disk so
# _is_suppressed would fall through immediately), but it pins the extraction contract so
# a future refactor that accidentally re-introduces a split-on-first-colon regression is
# caught here before it silently corrupts the Windows code path.
@test "drive-letter path extraction: sed strips :lineno:content leaving C:/path intact" {
  local input_line="C:/path/file.sh:42:    python -c \"code\""
  local extracted
  extracted="$(printf '%s' "$input_line" | sed -E 's/:[0-9]+:.*$//')"
  [ "$extracted" = "C:/path/file.sh" ]
}
