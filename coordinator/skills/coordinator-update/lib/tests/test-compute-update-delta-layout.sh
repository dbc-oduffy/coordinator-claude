#!/usr/bin/env bash
# coordinator/dist/oss-only-skills/coordinator-update/lib/tests/test-compute-update-delta-layout.sh
#
# Purpose: verify that compute-update-delta.sh resolves oss-repo-constants.sh
# and sets SOURCE_DIR correctly in the POST-INSTALL layout, which is shallower
# than the dist-source tree where the existing Python tests run.
#
# The existing test_compute_update_delta.py always exercises the dist-source
# layout (four-../ to coordinator/lib/) and therefore masked both layout bugs.
# This test simulates the injected installed shape:
#   coordinator/skills/coordinator-update/lib/   (not dist/oss-only-skills/…/lib/)
# and a sibling coordinator/lib/oss-repo-constants.sh at the install root,
# which is what the publish-repo install.sh injects.
#
# Spec backlink: docs/plans/2026-06-26-coordinator-install-update-friction-fix-slate.md
#               § C-R2b, AC1, AC2
#
# Assertions:
#   AC1 — script resolves oss-repo-constants.sh (no exit 4 "not found above")
#   AC2 — classifier is NOT invoked with a source path ending in /plugins
#   AC2 supplementary — SOURCE_DIR assignment in the script does not contain
#         the plugins/ subdir pattern (static code check)
#
# Negative-spec:
#   - Does NOT perform a real git clone (uses --clone to pass a pre-built fixture).
#   - Does NOT exercise the full currency delta logic — only the layout-sensitive
#     bootstrap (constants walk + SOURCE_DIR) is under test.
#   - The stub classifier validates the --source argument and emits minimal JSON
#     to let the script reach exit 0 without requiring real publish-repo content.

set -euo pipefail

# ---------------------------------------------------------------------------
# Resolve real source paths (from the dist tree, where this test lives)
# ---------------------------------------------------------------------------

_TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_DIST_LIB_DIR="$(dirname "$_TEST_DIR")"
_REAL_SCRIPT="${_DIST_LIB_DIR}/compute-update-delta.sh"

# The real oss-repo-constants.sh — walk up to find coordinator/lib/ just as
# the fixed script now does at runtime.
_CONSTANTS_WALK="${_DIST_LIB_DIR}"
_REAL_CONSTANTS=""
while [[ -n "$_CONSTANTS_WALK" && "$_CONSTANTS_WALK" != "/" ]]; do
  if [[ -f "${_CONSTANTS_WALK}/coordinator/lib/oss-repo-constants.sh" ]]; then
    _REAL_CONSTANTS="${_CONSTANTS_WALK}/coordinator/lib/oss-repo-constants.sh"
    break
  fi
  _CONSTANTS_WALK="$(dirname "$_CONSTANTS_WALK")"
done

if [[ -z "$_REAL_CONSTANTS" ]]; then
  echo "SETUP ERROR: cannot locate coordinator/lib/oss-repo-constants.sh from ${_DIST_LIB_DIR}" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Static code check (AC2 supplementary)
# The source file must not assign SOURCE_DIR to ${REPO_DIR}/plugins.
# ---------------------------------------------------------------------------

if grep -q 'SOURCE_DIR=.*REPO_DIR.*plugins' "$_REAL_SCRIPT"; then
  echo "FAIL (AC2 static): script still assigns SOURCE_DIR with a plugins/ subdir" >&2
  exit 1
fi
echo "PASS (AC2 static): no SOURCE_DIR=\${REPO_DIR}/plugins assignment in source"

# ---------------------------------------------------------------------------
# Build test fixture
# ---------------------------------------------------------------------------

TMPDIR_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_ROOT"' EXIT

# Installed layout tree:
#   coordinator/
#     lib/
#       oss-repo-constants.sh   ← sibling at install-root/coordinator/lib/
#     skills/
#       coordinator-update/
#         lib/
#           compute-update-delta.sh  ← copy of dist script at installed position
#     bin/
#       check-install-divergence.py  ← stub classifier
INSTALL_TREE="${TMPDIR_ROOT}/installed"

# Constants at the installed position
mkdir -p "${INSTALL_TREE}/coordinator/lib"
cp "$_REAL_CONSTANTS" "${INSTALL_TREE}/coordinator/lib/oss-repo-constants.sh"

# Script under test at the INSTALLED position (not dist/oss-only-skills/…/)
mkdir -p "${INSTALL_TREE}/coordinator/skills/coordinator-update/lib"
cp "$_REAL_SCRIPT" "${INSTALL_TREE}/coordinator/skills/coordinator-update/lib/compute-update-delta.sh"

# Stub classifier — validates that --source does NOT end with /plugins,
# then emits a minimal valid "current" JSON payload so the script exits 0.
mkdir -p "${INSTALL_TREE}/coordinator/bin"
cat > "${INSTALL_TREE}/coordinator/bin/check-install-divergence.py" <<'STUB_PY'
#!/usr/bin/env python3
"""Stub classifier for layout test — validates --source is the clone root."""
import sys, json

args = sys.argv[1:]
source_val = None
for i, a in enumerate(args):
    if a == "--source" and i + 1 < len(args):
        source_val = args[i + 1]
        break

if source_val is None:
    print("STUB ERROR: --source argument not provided", file=sys.stderr)
    sys.exit(1)

if source_val.endswith("/plugins"):
    print(
        f"LAYOUT-BUG DETECTED: classifier called with plugins/ subdir: {source_val}",
        file=sys.stderr,
    )
    sys.exit(1)

# Emit a minimal two-way (no-baseline) payload — exit 2 = no delta, acceptable.
payload = {
    "baseline_status": "stub-no-baseline",
    "counts": {
        "unchanged": 0,
        "forward_safe": 0,
        "consumer_modified": 0,
        "consumer_added": 0,
    },
    "consumer_modified": [],
    "consumer_added": [],
}
print(json.dumps(payload))
sys.exit(2)
STUB_PY
chmod +x "${INSTALL_TREE}/coordinator/bin/check-install-divergence.py"

# Fake publish-repo clone (git-backed, no remote — coordinator/ at repo root
# to match the publish-repo layout where no plugins/ subdir exists).
FAKE_CLONE="${TMPDIR_ROOT}/fake-clone"
mkdir -p "${FAKE_CLONE}/coordinator"
git -C "$FAKE_CLONE" init -b main --quiet 2>/dev/null || git -C "$FAKE_CLONE" init --quiet
git -C "$FAKE_CLONE" config user.email "test@layout.example"
git -C "$FAKE_CLONE" config user.name "LayoutTest"
echo "stub" > "${FAKE_CLONE}/coordinator/README.md"
git -C "$FAKE_CLONE" add .
git -C "$FAKE_CLONE" commit -m "init" --quiet

# ---------------------------------------------------------------------------
# Run the script from the INSTALLED layout position
# ---------------------------------------------------------------------------

INSTALLED_SCRIPT="${INSTALL_TREE}/coordinator/skills/coordinator-update/lib/compute-update-delta.sh"

script_output=""
script_exit=0
script_output="$(
  bash "$INSTALLED_SCRIPT" \
    --install-root "${INSTALL_TREE}" \
    --clone "${FAKE_CLONE}" \
    2>&1
)" || script_exit=$?

# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------

# AC1: constants walk succeeded — error message must NOT contain "not found above"
if echo "$script_output" | grep -q "oss-repo-constants.sh not found above"; then
  echo "FAIL (AC1): marker walk did not find oss-repo-constants.sh in installed layout" >&2
  echo "  Script output:" >&2
  echo "$script_output" >&2
  exit 1
fi
echo "PASS (AC1): oss-repo-constants.sh resolved via marker walk in installed layout"

# AC2 runtime: classifier was NOT called with a source path ending in /plugins
if echo "$script_output" | grep -q "LAYOUT-BUG DETECTED"; then
  echo "FAIL (AC2 runtime): classifier invoked with plugins/ subdir as --source" >&2
  echo "  Script output:" >&2
  echo "$script_output" >&2
  exit 1
fi
echo "PASS (AC2 runtime): classifier invoked with clone root (not plugins/ subdir)"

# AC1/AC2 combined: script must not exit 4 (which signals a layout-resolution error)
if [[ "$script_exit" -eq 4 ]]; then
  echo "FAIL: script exited 4 — layout or path resolution error" >&2
  echo "  Script output:" >&2
  echo "$script_output" >&2
  exit 1
fi
echo "PASS: script exit code is ${script_exit} (not 4 — no layout-resolution failure)"

echo ""
echo "ALL ASSERTIONS PASSED — installed layout resolves correctly."
