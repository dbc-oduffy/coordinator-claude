#!/usr/bin/env bash
# coordinator/dist/oss-only-skills/coordinator-update/lib/compute-update-delta.sh
#
# Purpose: compute the install-currency delta between the user's installed
# coordinator plugin and the latest published version, by wrapping the shipped
# check-install-divergence.py three-way classifier.
#
# Spec backlink: docs/plans/2026-05-30-oss-coordinator-update-skill.md § Chunk 2
#
# Invocation:
#   bash compute-update-delta.sh [--install-root <dir>] [--clone <dir>]
#
# Output:
#   stdout — single JSON object with fields from the classifier AUGMENTED with:
#     update_status   "current" | "behind" | "offline"
#     incoming_ref    the resolved tag or HEAD ref checked out
#     manual_url      the canonical publish URL (always present)
#     recommended_path "none" | "overwrite" | "cherry-pick" | "plan-to-ingest"
#
# Exit codes:
#   0   current (no incoming delta)
#   3   behind (delta present)
#   non-zero (≠3)  offline/error
#
# Negative-spec:
#   - NEVER reports update_status "current" if the network was unreachable —
#     that would be a false "you're up to date".
#   - --source passed to the classifier is the publish-repo clone ROOT, NOT a
#     plugins/ subdir. The publish repo mirrors coordinator/ directly at its root
#     (publish-targets.portable dest_subdir = empty = repo root), so git ls-files
#     already emits coordinator/... relpaths that align with --live's layout. The
#     former hardcoded-plugins-subdir assumption matched the meta-repo's internal
#     nesting but does not exist in the OSS publish repo — it caused exit 4 on
#     every real install. Verified against check-install-divergence.py:124-184.
#   - marketplace.json is installer-rewritten and always diverges from source —
#     excluded from consumer_modified advisory set.

set -euo pipefail

# ---------------------------------------------------------------------------
# Constants — sourced from lib/oss-repo-constants.sh (single source of truth)
# ---------------------------------------------------------------------------
# Spec backlink: docs/plans/2026-06-01-boot-currency-notification-hook.md § C2
# Negative-spec: DO NOT define CANONICAL_PUBLISH_URL inline here — it lives in
# lib/oss-repo-constants.sh. That file must be sourced before use.

_COMPUTE_DELTA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Marker-based walk: ascend from this script's directory until we find a parent
# that contains coordinator/lib/oss-repo-constants.sh. This resolves correctly
# in BOTH the dist-source layout
#   (coordinator/dist/oss-only-skills/coordinator-update/lib/)
# AND the post-install layout
#   (coordinator/skills/coordinator-update/lib/)
# which is two path segments shallower. A hardcoded four-../ count resolved
# only in the dist tree and broke on every real install (exit 4, constants not
# found). The marker is layout-agnostic: whatever dir sits above coordinator/
# will contain coordinator/lib/oss-repo-constants.sh.
_OSS_CONSTANTS=""
_walk="${_COMPUTE_DELTA_DIR}"
while [[ -n "$_walk" && "$_walk" != "/" ]]; do
  if [[ -f "${_walk}/coordinator/lib/oss-repo-constants.sh" ]]; then
    _OSS_CONSTANTS="${_walk}/coordinator/lib/oss-repo-constants.sh"
    break
  fi
  _walk="$(dirname "$_walk")"
done
if [[ -z "$_OSS_CONSTANTS" ]]; then
  echo "ERROR: lib/oss-repo-constants.sh not found above ${_COMPUTE_DELTA_DIR}" >&2
  exit 4
fi
# shellcheck source=../../../../lib/oss-repo-constants.sh
source "$_OSS_CONSTANTS"

CANONICAL_PUBLISH_URL="${COORDINATOR_PUBLISH_URL}"

# The marketplace.json path (relative, POSIX) that the coordinator installer always rewrites.
MARKETPLACE_JSON_PATH="coordinator/.claude-plugin/marketplace.json"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

INSTALL_ROOT="${HOME}/.claude/plugins/coordinator-claude"
CLONE_DIR=""
_OWN_TEMP=""

# Work temp dir — used for the classifier JSON temp file regardless of whether
# we own the clone temp dir. Always cleaned up on EXIT.
_WORK_TEMP="$(mktemp -d)"
trap '[[ -n "$_OWN_TEMP" ]] && rm -rf "$_OWN_TEMP"; rm -rf "$_WORK_TEMP"' EXIT

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-root)
      INSTALL_ROOT="$2"
      shift 2
      ;;
    --clone)
      CLONE_DIR="$2"
      shift 2
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      exit 4
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Resolve the python interpreter portably (python3 || python || py).
_find_python() {
  for candidate in python3 python py; do
    if command -v "$candidate" &>/dev/null; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

# Review: code-reviewer — (P1) Eager PYTHON resolution: resolve before Step 1 so _emit_offline
# (called during network failures in Steps 1-2) uses the same portable interpreter, not a
# hardcoded python3 that may be absent on Windows. Also needed before _emit_offline definition
# so the variable is in scope when the function body executes.
PYTHON="$(_find_python)" || {
  echo "ERROR: no python interpreter found (tried python3, python, py)" >&2
  exit 4
}

# Emit an offline JSON payload and exit with code 5 (non-zero, ≠3 → offline).
_emit_offline() {
  local reason="$1"
  # Review: code-reviewer — (P1) use $PYTHON (resolved above) not hardcoded python3.
  # Review: code-reviewer — (nit) pass CANONICAL_PUBLISH_URL via sys.argv[2] so a future
  # URL with a quote character cannot break the Python string literal.
  # Build a minimal payload — counts and lists are empty since we couldn't reach source.
  # verify-no-console-flash: allow — OSS install bootstrap, runs once (annotation on the spawn line below)
  # Review: code-reviewer (A-F2) — derive spawn-hidden.sh from _OSS_CONSTANTS anchor; the
  # four-../ relative path overshoots in the installed layout (coordinator/skills/…/lib/ is
  # shallower than dist/oss-only-skills/…/lib/). _OSS_CONSTANTS is in scope here.
  bash "$(dirname "$_OSS_CONSTANTS")/spawn-hidden.sh" --stdin-mode=safe "$PYTHON" -c "
import json, sys
payload = {
    'update_status': 'offline',
    'incoming_ref': None,
    'manual_url': sys.argv[2],
    'recommended_path': 'none',
    'baseline_status': 'offline — could not reach update source',
    'counts': {'unchanged': 0, 'forward_safe': 0, 'consumer_modified': 0, 'consumer_added': 0},
    'consumer_modified': [],
    'consumer_added': [],
    '_offline_reason': sys.argv[1],
}
print(json.dumps(payload, indent=2))
" "$reason" "$CANONICAL_PUBLISH_URL" 2>/dev/null || printf '{"update_status":"offline","incoming_ref":null,"manual_url":"%s","recommended_path":"none","_offline_reason":"%s"}\n' \
    "$CANONICAL_PUBLISH_URL" "$reason"
  exit 5
}

# ---------------------------------------------------------------------------
# Step 1: Locate or clone the publish repo
# ---------------------------------------------------------------------------

if [[ -n "$CLONE_DIR" ]]; then
  # Caller provided an existing clone dir — validate it is a real git repo.
  if [[ ! -d "$CLONE_DIR/.git" ]]; then
    echo "ERROR: --clone argument '$CLONE_DIR' is not a valid git repository (no .git dir)" >&2
    exit 4
  fi
  REPO_DIR="$CLONE_DIR"
else
  # Clone into a temp dir; trap already registered above handles cleanup.
  _OWN_TEMP="$(mktemp -d)"

  # Review: code-reviewer — (P2) Full clone (no --depth): the baseline SHA from version.txt
  # must be reachable for git ls-tree; a shallow clone would omit it.
  if ! git clone --quiet "$CANONICAL_PUBLISH_URL" "$_OWN_TEMP/clone" 2>/dev/null; then
    _emit_offline "git clone failed — network unreachable or repo not found at ${CANONICAL_PUBLISH_URL}"
  fi
  REPO_DIR="$_OWN_TEMP/clone"
fi

# ---------------------------------------------------------------------------
# Step 2: Fetch + resolve the incoming ref
# ---------------------------------------------------------------------------

# Fetch tags so git describe finds the latest release tag.
if ! git -C "$REPO_DIR" fetch --tags --quiet 2>/dev/null; then
  # If we own the temp clone and it just failed to fetch, it means network is down.
  # If caller provided --clone, a stale local clone is still usable; proceed with
  # whatever is already checked out rather than failing.
  if [[ -n "$_OWN_TEMP" ]]; then
    _emit_offline "git fetch --tags failed — network unreachable"
  fi
  # For caller-provided clone: use whatever HEAD is currently checked out.
fi

INCOMING_REF=""

# Try tag-first: latest release tag via git describe.
if INCOMING_REF="$(git -C "$REPO_DIR" describe --tags --abbrev=0 2>/dev/null)"; then
  : # tag found
else
  # No tags — fall back to origin/main HEAD.
  INCOMING_REF="origin/main"
fi

# Review: code-reviewer — (P2) remove || true: a failed checkout silently classifies
# against the wrong HEAD. If we own the temp clone, emit offline; if caller-provided,
# warn to stderr and proceed on current HEAD.
# Checkout the resolved ref.
if ! git -C "$REPO_DIR" checkout --quiet "$INCOMING_REF" 2>/dev/null; then
  if [[ -n "$_OWN_TEMP" ]]; then
    _emit_offline "checkout ${INCOMING_REF} failed — ref missing or corrupt in temp clone"
  else
    echo "WARNING: checkout of ref '${INCOMING_REF}' failed in caller-provided clone; proceeding on current HEAD" >&2
  fi
fi

# ---------------------------------------------------------------------------
# Step 3: Baseline reachability guard
# ---------------------------------------------------------------------------
# The classifier reads version.txt from --live to get the baseline SHA, then
# runs git ls-tree <baseline_sha> inside the source clone. A shallow clone may
# omit old commits. We cloned without --depth so this should be fine; but if
# version.txt points to a commit not reachable in the clone (e.g. force-pushed)
# the classifier degrades gracefully to baseline-free two-way (exit 2) — we
# surface that honestly via the baseline_status field. No hard-fail here.

# ---------------------------------------------------------------------------
# Step 4: Locate the classifier
# ---------------------------------------------------------------------------

CLASSIFIER="${INSTALL_ROOT}/coordinator/bin/check-install-divergence.py"

if [[ ! -f "$CLASSIFIER" ]]; then
  echo "ERROR: classifier not found at expected path: ${CLASSIFIER}" >&2
  echo "       Is --install-root set correctly? Default: \$HOME/.claude/plugins/coordinator-claude" >&2
  exit 4
fi

# ---------------------------------------------------------------------------
# Step 5: Run the classifier
# --source is the publish-repo clone ROOT (REPO_DIR itself), NOT a plugins/
# subdir. The OSS publish repo mirrors coordinator/ directly at its top level
# (publish-targets.portable dest_subdir is empty = repo root), so no plugins/
# directory exists. Passing REPO_DIR directly makes git ls-files emit
# coordinator/... relpaths that already align with --live's layout.
#
# The former hardcoded plugins-subdir assumption mirrored the meta-repo's
# internal nesting (coordinator lives under plugins/coordinator-claude/coordinator/
# in the meta-repo) but that directory does not exist in the publish repo.
# The result was exit 4 on every real install — plugins/ was never there.
# ---------------------------------------------------------------------------

SOURCE_DIR="${REPO_DIR}"

CLASSIFIER_JSON=""
CLASSIFIER_EXIT=0

CLASSIFIER_JSON="$("$PYTHON" "$CLASSIFIER" --source "$SOURCE_DIR" --live "$INSTALL_ROOT" --format json 2>/dev/null)" || CLASSIFIER_EXIT=$? # verify-no-console-flash: allow — OSS install bootstrap, runs once

# Exit 1 = invalid CLI input (should not happen with our paths).
# Exit 2 = no baseline, two-way clean.
# Exit 3 = divergence detected (consumer-modified or consumer-added).
# Any other non-zero exit is an unexpected classifier error.
if [[ $CLASSIFIER_EXIT -eq 1 ]]; then
  echo "ERROR: classifier rejected CLI arguments (bad paths?)" >&2
  exit 4
elif [[ $CLASSIFIER_EXIT -ne 0 && $CLASSIFIER_EXIT -ne 2 && $CLASSIFIER_EXIT -ne 3 ]]; then
  echo "ERROR: classifier exited with unexpected code: ${CLASSIFIER_EXIT}" >&2
  exit 4
fi

if [[ -z "$CLASSIFIER_JSON" ]]; then
  echo "ERROR: classifier produced no JSON output" >&2
  exit 4
fi

# ---------------------------------------------------------------------------
# Step 6 + 7: Apply marketplace.json exclusion and compute recommended_path.
# Augment the classifier JSON with wrapper fields and emit.
#
# Negative-spec: DO NOT interpolate CLASSIFIER_JSON into a Python heredoc via
# shell variable expansion — diff hunks contain control characters and
# backslashes that corrupt the Python string literal. Write to a temp file
# and have Python read it via sys.argv, which is safe for arbitrary content.
# ---------------------------------------------------------------------------

# Write classifier JSON to a temp file safe from shell-expansion corruption.
_JSON_TMP="${_WORK_TEMP}/classifier_output.json"
printf '%s' "${CLASSIFIER_JSON}" > "$_JSON_TMP"

"$PYTHON" - "$_JSON_TMP" "$INCOMING_REF" "$CANONICAL_PUBLISH_URL" "$CLASSIFIER_EXIT" "$MARKETPLACE_JSON_PATH" <<'PYEOF' # verify-no-console-flash: allow — OSS install bootstrap, runs once
import json, sys

json_path, incoming_ref, manual_url, classifier_exit_str, marketplace_path = sys.argv[1:6]

try:
    with open(json_path, encoding="utf-8") as fh:
        data = json.load(fh)
except (json.JSONDecodeError, OSError) as e:
    print(f"ERROR: could not parse classifier JSON: {e}", file=sys.stderr)
    sys.exit(4)

# --- marketplace.json exclusion -------------------------------------------
# the coordinator installer always rewrites this file, so it always shows up
# as consumer_modified — it is NOT a user customisation.
original_modified = data.get("consumer_modified", [])
filtered_modified = [entry for entry in original_modified if entry.get("path") != marketplace_path]
excluded_count = len(original_modified) - len(filtered_modified)
data["consumer_modified"] = filtered_modified
data["counts"]["consumer_modified"] = data["counts"].get("consumer_modified", 0) - excluded_count

# --- recommended_path computation (post-exclusion counts) -----------------
cm = data["counts"].get("consumer_modified", 0)
fs = data["counts"].get("forward_safe", 0)
ca = data["counts"].get("consumer_added", 0)

# Review: code-reviewer — (P2) drop `and ca == 0`: a consumer with only locally-added
# files and no incoming forward changes (cm==0, fs==0, ca>0) has latest upstream and
# should report "current"/"none", not fall through to "plan-to-ingest".
if cm == 0 and fs == 0:
    # No incoming delta — caller is current (may have local additions, which are fine).
    recommended_path = "none"
    update_status = "current"
elif cm == 0 and fs > 0:
    # Only forward-safe changes — tradeoff-free, safe to overwrite.
    recommended_path = "overwrite"
    update_status = "behind"
elif cm > 0 and fs > 0:
    # Mix of consumer-modified collisions and clean forward changes — cherry-pick.
    recommended_path = "cherry-pick"
    update_status = "behind"
else:
    # Consumer-modified collisions with no clean forward delta, or large delta —
    # deliberate ingestion via /plan is the right path.
    recommended_path = "plan-to-ingest"
    update_status = "behind"

# --- Augment with wrapper fields ------------------------------------------
data["update_status"] = update_status
data["incoming_ref"] = incoming_ref
data["manual_url"] = manual_url
data["recommended_path"] = recommended_path

print(json.dumps(data, indent=2))

# --- Exit with correct code for callers -----------------------------------
# 0 = current (nothing incoming), 3 = behind (delta present)
if update_status == "current":
    sys.exit(0)
else:
    sys.exit(3)
PYEOF
