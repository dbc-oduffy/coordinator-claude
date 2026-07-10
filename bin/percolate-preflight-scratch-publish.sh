#!/usr/bin/env bash
# percolate-preflight-scratch-publish.sh — hook-exercising scratch-PUBLISH pre-flight (C6 gate).
#
# Runs a REAL scratch publish (publish.sh, non-dry-run, name="coordinator-claude" so the
# real percolate-hooks/coordinator-claude/post-rsync/*.sh hooks fire) into a throwaway
# temp destination — NOT a standalone `publish-time-transform.sh` invocation. That
# distinction is the point: a standalone transform-bin call exercises transform coverage
# (C3a) but NOT hook-resolution (does DEPERSONALIZE_BIN resolve via the shared resolver
# lib templates/setup/percolate-hooks/_lib/depersonalize-bin-resolve.sh — D3a/E2/E3/E4)?
# A standalone call answers "is the transform correct" but not "does publish.sh's hook
# chain find and invoke the transform at all" — the second half of the original incident
# (the Director of Engineering F2, docs/plans/2026-07-09-doe-percolation-source-prep-and-genericize.md § C6/AC8).
#
# The scratch publish targets are ALWAYS local temp directories (mktemp -d) — this script
# never rsyncs or pushes to a real mirror. Production mode still requires an explicit
# --source-dir naming the real coordinator plugin content root (so hooks resolve real
# DEPERSONALIZE_BIN via .doe-root/registry) but the DESTINATION is always scratch.
#
# Gate (AC8): GREEN iff BOTH
#   (a) check-registry-codename-leak.sh <scratch-dest> exits 0, AND
#   (b) check-persona-slug-leak.sh <scratch-dest> exits 0 (C8 persona-slug scan)
# PLUS a write-set assertion that the new templates/setup/percolate-hooks/_lib/ path and
# any new coordinator/lib/* files actually land in the scratch destination (regression
# check on the mirror copy — see NEGATIVE-SPEC below for what this does NOT prove).
#
# NEGATIVE-SPEC — what this script's default (legacy-row) scratch publish does NOT prove:
# a legacy 3-field row (name|mode|source|dest) carries NO allowlist field, so
# publish.sh's fail-closed `_build_allowlisted_source` restriction (W5.1) is never
# exercised — every file under --source-dir lands in the scratch dest regardless of the
# REAL coordinator-claude publish-mirror target's configured allowlist CSV. That write-set
# assertion is therefore a *mirror-copy regression check* (did sync_mirror faithfully copy
# nested paths), NOT proof that the real allowlist CSV includes these paths. Use
# `--check-allowlist-string` (below) for the latter — it greps the REAL resolved
# publish-mirror row's allowlist field directly, no publish run required.
#
# Usage:
#   percolate-preflight-scratch-publish.sh --self-test
#       Runs an internal RED (seeded private-codename leak) then GREEN (clean tree)
#       fixture pair against a synthetic source tree. No real registry/target config
#       required — the RED seed uses COORDINATOR_CODENAME_REGISTRY_KEYS (test-injection
#       override already supported by check-registry-codename-leak.sh) so the check does
#       not depend on the live machine-local registry's actual repos.* contents.
#
#   percolate-preflight-scratch-publish.sh --source-dir <coordinator-content-root> \
#       [--target <name>] [--scratch-dest <dir>] [--allow-dirty-source] [--keep]
#       Production mode: runs the real scratch publish against a REAL source tree
#       (still writing only to a scratch temp destination). See "EXACT EM GATE COMMAND"
#       below for the true C7-gating invocation.
#
#   percolate-preflight-scratch-publish.sh --check-allowlist-string [--target <name>]
#       Resolves the REAL publish-mirror row for <target> (default coordinator-claude)
#       from the tracked publish-targets.portable / machine-local registry and greps its
#       allowlist CSV field for "lib" and "templates" (the top-level dirs that carry
#       coordinator/lib/* and templates/setup/percolate-hooks/_lib/ respectively). No
#       publish run — pure string check against the configured allowlist.
#
# Exit codes: 0 = GREEN (all gates passed), 1 = RED (a gate failed), 2 = usage/setup error.
#
# Spec backlink: docs/plans/2026-07-09-doe-percolation-source-prep-and-genericize.md § C6/AC8
# Review note: the Director of Engineering F2 — running the transform bin directly does not exercise whether the
# 5 post-rsync hooks resolve their DEPERSONALIZE_BIN from DoE; this script closes that gap.

# Bash 4+ guard — must be parseable by bash 3.2 (macOS default), so no bash-4-only syntax
# before this check (mirrors check-registry-codename-leak.sh / publish.sh convention).
if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: percolate-preflight-scratch-publish.sh requires bash 4.0 or later." >&2
  echo "       Detected: bash ${BASH_VERSION:-unknown}" >&2
  echo "  macOS ships bash 3.2 as /bin/bash. Install a current bash and put it first on PATH:" >&2
  echo "      brew install bash" >&2
  echo '      export PATH="$(brew --prefix)/bin:$PATH"   # add to ~/.zshrc or ~/.bashrc' >&2
  exit 2
fi

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COORDINATOR_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PUBLISH_SH="$COORDINATOR_ROOT/templates/setup/publish.sh"
CODENAME_GUARD="$SCRIPT_DIR/check-registry-codename-leak.sh"
PERSONA_GUARD="$SCRIPT_DIR/check-persona-slug-leak.sh"
RESOLVE_LIB="$COORDINATOR_ROOT/templates/setup/lib/resolve-publish-target.sh"
PORTABLE_TARGETS_REAL="$COORDINATOR_ROOT/templates/setup/publish-targets.portable"

usage() {
  echo "Usage: percolate-preflight-scratch-publish.sh --self-test" >&2
  echo "       percolate-preflight-scratch-publish.sh --source-dir <dir> [--target <name>] [--scratch-dest <dir>] [--allow-dirty-source] [--keep]" >&2
  echo "       percolate-preflight-scratch-publish.sh --check-allowlist-string [--target <name>]" >&2
  exit 2
}

for f in "$PUBLISH_SH" "$CODENAME_GUARD" "$PERSONA_GUARD"; do
  if [[ ! -f "$f" ]]; then
    echo "percolate-preflight-scratch-publish.sh: required file not found: $f" >&2
    exit 2
  fi
done

# ---------------------------------------------------------------------------
# run_scratch_publish <target-name> <source-dir> <dest-dir>
# ---------------------------------------------------------------------------
# Fires a real (non-dry-run) publish.sh run confined to a scratch destination via a
# synthetic single-row PORTABLE_TARGETS_FILE (legacy 4-field shape — pass-through, no
# machine-local registry dependency). Then independently re-runs BOTH guards against the
# resulting scratch tree and asserts the _lib / coordinator/lib write-set landed.
# Sets globals: PP_PUBLISH_RC PP_CODENAME_RC PP_PERSONA_RC PP_LIB_HIT PP_COORDLIB_HIT
run_scratch_publish() {
  local target_name="$1" source_dir="$2" dest_dir="$3"

  if [[ ! -d "$source_dir" ]]; then
    echo "run_scratch_publish: source-dir not found: $source_dir" >&2
    return 2
  fi
  mkdir -p "$dest_dir"

  local tmp_targets
  tmp_targets="$(mktemp)"
  # Legacy 4-field row: name|mode|ABSsource|ABSdest — resolve_publish_row passes this
  # through verbatim (field 3 is an absolute path, not repo:/publish-mirror:).
  printf '%s|mirror|%s|%s\n' "$target_name" "$source_dir" "$dest_dir" > "$tmp_targets"

  echo "=== scratch publish: target=$target_name source=$source_dir dest=$dest_dir ==="
  PP_PUBLISH_RC=0
  PORTABLE_TARGETS_FILE="$tmp_targets" "$BASH" "$PUBLISH_SH" "$target_name" || PP_PUBLISH_RC=$?
  rm -f "$tmp_targets"
  echo "  publish.sh exit code: $PP_PUBLISH_RC"

  # Independent post-hoc guard re-checks — AC8's two gates. Run regardless of
  # PP_PUBLISH_RC: sync_mirror runs BEFORE post-rsync hooks, so even a hook-aborted
  # publish leaves a scratch dest worth inspecting (belt-and-suspenders vs. the hook's
  # own embedded check-registry-codename-leak.sh call in 10-transform.sh).
  PP_CODENAME_RC=0
  "$BASH" "$CODENAME_GUARD" "$dest_dir" || PP_CODENAME_RC=$?
  PP_PERSONA_RC=0
  "$BASH" "$PERSONA_GUARD" "$dest_dir" || PP_PERSONA_RC=$?

  # Write-set assertion: templates/setup/percolate-hooks/_lib/ and coordinator/lib/*
  # must have landed in the scratch dest (mirror-copy regression check — see
  # NEGATIVE-SPEC in the file header for what this does and does not prove).
  PP_LIB_HIT=0
  PP_COORDLIB_HIT=0
  if find "$dest_dir" -path '*templates/setup/percolate-hooks/_lib/*' -type f 2>/dev/null | grep -q .; then
    PP_LIB_HIT=1
  fi
  if find "$dest_dir" -path '*coordinator/lib/*' -type f 2>/dev/null | grep -q .; then
    PP_COORDLIB_HIT=1
  fi

  echo "  check-registry-codename-leak.sh: $( [[ $PP_CODENAME_RC -eq 0 ]] && echo GREEN || echo RED ) (exit $PP_CODENAME_RC)"
  echo "  check-persona-slug-leak.sh:      $( [[ $PP_PERSONA_RC -eq 0 ]] && echo GREEN || echo RED ) (exit $PP_PERSONA_RC)"
  echo "  templates/.../_lib/ landed:      $( [[ $PP_LIB_HIT -eq 1 ]] && echo yes || echo NO )"
  echo "  coordinator/lib/* landed:        $( [[ $PP_COORDLIB_HIT -eq 1 ]] && echo yes || echo NO )"
}

# ---------------------------------------------------------------------------
# verdict — combine the four signals from run_scratch_publish into GREEN/RED.
# Echoes GREEN or RED to stdout; returns 0/1 to match.
# ---------------------------------------------------------------------------
verdict() {
  if [[ "$PP_CODENAME_RC" -eq 0 && "$PP_PERSONA_RC" -eq 0 && "$PP_LIB_HIT" -eq 1 && "$PP_COORDLIB_HIT" -eq 1 ]]; then
    echo "GREEN"
    return 0
  fi
  echo "RED"
  return 1
}

# ---------------------------------------------------------------------------
# check_allowlist_string <target-name>
# ---------------------------------------------------------------------------
# Resolves the REAL publish-mirror row for <target-name> (tracked
# publish-targets.portable, primary; machine-local registry supplement) and greps its
# allowlist CSV field for "lib" and "templates" — the top-level source dirs that carry
# coordinator/lib/* and templates/setup/percolate-hooks/_lib/ respectively. No publish
# run — pure string check. Requires the real portable file / machine-local registry to
# be present; not runnable in a sandbox with no live registry (fails loud with
# remediation, exit 2 — distinct from a RED gate failure).
check_allowlist_string() {
  local target_name="$1"

  if [[ ! -f "$RESOLVE_LIB" ]]; then
    echo "check_allowlist_string: resolve-publish-target.sh lib not found at $RESOLVE_LIB" >&2
    return 2
  fi
  # shellcheck source=/dev/null
  source "$RESOLVE_LIB"

  if [[ ! -f "$PORTABLE_TARGETS_REAL" ]]; then
    echo "check_allowlist_string: no tracked publish-targets.portable at $PORTABLE_TARGETS_REAL" >&2
    echo "  (expected on a fresh checkout with no live registry — this is a setup gap, not a RED verdict)" >&2
    return 2
  fi

  local raw resolved rc found=0
  while IFS= read -r raw || [[ -n "$raw" ]]; do
    raw="${raw%$'\r'}"
    [[ -z "$raw" || "$raw" =~ ^[[:space:]]*# ]] && continue
    [[ "$raw" != "${target_name}|"* ]] && continue
    found=1
    rc=0
    resolved="$(resolve_publish_row "$raw")" || rc=$?
    if [[ $rc -ne 0 ]]; then
      echo "check_allowlist_string: could not resolve row for '$target_name' (rc=$rc) — see stderr above." >&2
      return 2
    fi
    # Resolved row: name|mode|ABSsource|ABSdest[|native_slugs][|allowlist] — allowlist is
    # the LAST field only when a publish-mirror row supplied one (6th positional field
    # after the 5-field legacy/mirror form). Take everything after the 4th '|' as a
    # loose superset (native_slugs or allowlist or both) — good enough for a substring
    # grep; false-positive risk (matching "lib" inside a native_slugs entry) is
    # acceptable for an informational pre-check, not the binding gate.
    local tail="${resolved#*|*|*|*|}"
    echo "=== resolved row for '$target_name' ==="
    echo "  $resolved"
    echo "  allowlist/native_slugs tail: $tail"
    if [[ "$tail" == *"lib"* ]]; then
      echo "  'lib' token found — coordinator/lib/* likely covered."
    else
      echo "  WARNING: 'lib' token NOT found in allowlist tail — coordinator/lib/* may be excluded by the fail-closed allowlist." >&2
    fi
    if [[ "$tail" == *"templates"* ]]; then
      echo "  'templates' token found — templates/setup/percolate-hooks/_lib/ likely covered."
    else
      echo "  WARNING: 'templates' token NOT found in allowlist tail — templates/setup/percolate-hooks/_lib/ may be excluded by the fail-closed allowlist." >&2
    fi
    break
  done < "$PORTABLE_TARGETS_REAL"

  if [[ "$found" -eq 0 ]]; then
    echo "check_allowlist_string: no row named '$target_name' found in $PORTABLE_TARGETS_REAL" >&2
    return 2
  fi
  return 0
}

# ---------------------------------------------------------------------------
# self_test — RED (seeded private-codename leak) then GREEN (clean) fixture pair.
# Uses a synthetic source tree + COORDINATOR_CODENAME_REGISTRY_KEYS test-injection
# override (already supported by check-registry-codename-leak.sh) so this does NOT
# depend on the live machine-local registry's real repos.* contents. Target name is
# ALWAYS "coordinator-claude" so the REAL percolate-hooks/coordinator-claude/post-rsync/
# hooks fire (10-transform.sh, 20-inject-oss-only-skills.sh) — this exercises real
# DEPERSONALIZE_BIN resolution (D3a/E2/E3/E4), not a mocked substitute.
# ---------------------------------------------------------------------------
self_test() {
  local overall_rc=0

  echo "############################################################"
  echo "# self-test 1/2: RED — seeded private-codename leak"
  echo "############################################################"
  local src1 dst1
  src1="$(mktemp -d)"
  dst1="$(mktemp -d)"
  mkdir -p "$src1/coordinator/lib" "$src1/coordinator/templates/setup/percolate-hooks/_lib"
  printf '#!/usr/bin/env bash\necho "stub lib file"\n' > "$src1/coordinator/lib/stub-new-lib-file.sh"
  printf '#!/usr/bin/env bash\necho "stub shared hook resolver"\n' > "$src1/coordinator/templates/setup/percolate-hooks/_lib/stub-resolver.sh"
  # Seed a leak: a synthetic private codename NOT present in publish-time-transform.sh's
  # rewrite tables, so it survives the --fix pass inside 10-transform.sh and is caught
  # by BOTH the hook's own embedded check-registry-codename-leak.sh call (aborting
  # publish.sh) AND this script's independent post-hoc re-check.
  printf '# reference: zzz-scratch-preflight-testleak-codename lives here\n' > "$src1/coordinator/bin_marker_leak.sh"

  local red_rc=0
  COORDINATOR_CODENAME_REGISTRY_KEYS="repos.zzz_scratch_preflight_testleak_codename" \
    run_scratch_publish "coordinator-claude" "$src1" "$dst1" || red_rc=$?

  local red_verdict
  red_verdict="$(verdict)" || true
  echo "  --> self-test 1/2 verdict: $red_verdict (expected RED)"
  if [[ "$red_verdict" != "RED" ]]; then
    echo "  FAIL: expected RED (seeded leak), got $red_verdict" >&2
    overall_rc=1
  else
    echo "  PASS"
  fi
  rm -rf "$src1" "$dst1"

  echo ""
  echo "############################################################"
  echo "# self-test 2/2: GREEN — clean scratch tree"
  echo "############################################################"
  local src2 dst2
  src2="$(mktemp -d)"
  dst2="$(mktemp -d)"
  mkdir -p "$src2/coordinator/lib" "$src2/coordinator/templates/setup/percolate-hooks/_lib"
  printf '#!/usr/bin/env bash\necho "stub lib file"\n' > "$src2/coordinator/lib/stub-new-lib-file.sh"
  printf '#!/usr/bin/env bash\necho "stub shared hook resolver"\n' > "$src2/coordinator/templates/setup/percolate-hooks/_lib/stub-resolver.sh"

  run_scratch_publish "coordinator-claude" "$src2" "$dst2" || true

  local green_verdict
  green_verdict="$(verdict)" || true
  echo "  --> self-test 2/2 verdict: $green_verdict (expected GREEN)"
  if [[ "$green_verdict" != "GREEN" ]]; then
    echo "  FAIL: expected GREEN (clean tree), got $green_verdict" >&2
    overall_rc=1
  else
    echo "  PASS"
  fi
  rm -rf "$src2" "$dst2"

  echo ""
  if [[ "$overall_rc" -eq 0 ]]; then
    echo "self-test: PASS (RED-on-seed and GREEN-on-clean both confirmed)"
  else
    echo "self-test: FAIL" >&2
  fi
  return "$overall_rc"
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
MODE=""
TARGET_NAME="coordinator-claude"
SOURCE_DIR=""
SCRATCH_DEST=""
KEEP=false
ALLOW_DIRTY=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --self-test) MODE="self-test"; shift ;;
    --check-allowlist-string) MODE="check-allowlist-string"; shift ;;
    --source-dir) SOURCE_DIR="${2:-}"; shift 2 ;;
    --target) TARGET_NAME="${2:-}"; shift 2 ;;
    --scratch-dest) SCRATCH_DEST="${2:-}"; shift 2 ;;
    --allow-dirty-source) ALLOW_DIRTY=true; shift ;;
    --keep) KEEP=true; shift ;;
    -h|--help) usage ;;
    *) echo "Unknown argument: $1" >&2; usage ;;
  esac
done

if [[ -z "$MODE" ]]; then
  if [[ -n "$SOURCE_DIR" ]]; then
    MODE="production"
  else
    usage
  fi
fi

case "$MODE" in
  self-test)
    self_test
    exit $?
    ;;
  check-allowlist-string)
    check_allowlist_string "$TARGET_NAME"
    exit $?
    ;;
  production)
    if [[ -z "$SCRATCH_DEST" ]]; then
      SCRATCH_DEST="$(mktemp -d)"
    else
      mkdir -p "$SCRATCH_DEST"
    fi
    if $ALLOW_DIRTY; then
      export COORDINATOR_OVERRIDE_DIRTY_TREE=1
    fi
    run_scratch_publish "$TARGET_NAME" "$SOURCE_DIR" "$SCRATCH_DEST"
    v="$(verdict)" || true
    echo ""
    echo "=== C6 pre-flight verdict: $v ==="
    if ! $KEEP; then
      rm -rf "$SCRATCH_DEST"
    else
      echo "  (--keep set; scratch dest retained at $SCRATCH_DEST)"
    fi
    [[ "$v" == "GREEN" ]]
    exit $?
    ;;
  *)
    usage
    ;;
esac
