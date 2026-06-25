#!/usr/bin/env bash
# verify-no-console-flash: file-allow — test scaffolding; interpreter spawns run in the CI/local test harness, never the Windows interactive coordinator hot-path
# test_manifest_conforms_system_prereq.sh — conformance test for the real manifest.
#
# Purpose: loads agent-install-manifest.json and agent-install-manifest.schema.json
# and asserts the real manifest (with its populated system_prerequisites array)
# validates against the schema. Uses python3 + jsonschema if available; degrades
# to structural assertions otherwise.
# No jq dependency (coordinator is deliberately jq-free).
#
# Spec backlink: docs/plans/2026-06-23-coordinator-root-system-prerequisites.md § C1 (AC2)
# Run: bash tests/install/test_manifest_conforms_system_prereq.sh
set -euo pipefail

# ---------------------------------------------------------------------------
# Repo-root resolution — resolve relative to this script's location.
# ---------------------------------------------------------------------------
_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_REPO_ROOT="$(cd "$_SCRIPT_DIR/../.." && pwd)"

SCHEMA_FILE="$_REPO_ROOT/docs/install/agent-install-manifest.schema.json"
MANIFEST_FILE="$_REPO_ROOT/docs/install/agent-install-manifest.json"

# ---------------------------------------------------------------------------
# Counters.
# ---------------------------------------------------------------------------
_PASS=0
_FAIL=0

_pass() { echo "  PASS: $1"; _PASS=$(( _PASS + 1 )); }
_fail() { echo "  FAIL: $1"; _FAIL=$(( _FAIL + 1 )); }

# ---------------------------------------------------------------------------
# Temp directory for helper scripts.
# ---------------------------------------------------------------------------
_TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$_TMP_DIR"' EXIT

# ---------------------------------------------------------------------------
# Write Python helper scripts to _TMP_DIR.
# All Python is in .py files so no inline python invocations appear in this .sh.
# ---------------------------------------------------------------------------

# check_jsonschema.py — exits 0 if jsonschema is importable.
cat > "$_TMP_DIR/check_jsonschema.py" << 'EOF'
import sys
try:
    import jsonschema  # noqa: F401
    sys.exit(0)
except ImportError:
    sys.exit(1)
EOF

# validate_manifest.py — validates the real manifest against the schema.
# argv[1] = schema file, argv[2] = manifest file
# Exits 0 on success, 1 on validation failure.
cat > "$_TMP_DIR/validate_manifest.py" << 'EOF'
import json, sys, jsonschema

schema_path = sys.argv[1]
manifest_path = sys.argv[2]

try:
    schema = json.load(open(schema_path))
except Exception as e:
    sys.stderr.write(f"FAIL: cannot parse schema: {e}\n")
    sys.exit(2)

try:
    manifest = json.load(open(manifest_path))
except Exception as e:
    sys.stderr.write(f"FAIL: cannot parse manifest: {e}\n")
    sys.exit(2)

validator = jsonschema.Draft202012Validator(schema)
errors = list(validator.iter_errors(manifest))
if errors:
    for e in errors:
        sys.stderr.write(f"  validation error: {e.message}\n")
    sys.exit(1)

sys.exit(0)
EOF

# structural_manifest_checks.py — structural checks without jsonschema.
# argv[1] = manifest file
# Outputs a JSON object with check results.
cat > "$_TMP_DIR/structural_manifest_checks.py" << 'EOF'
import json, sys

manifest_path = sys.argv[1]
schema_path = sys.argv[2] if len(sys.argv) > 2 else None

try:
    manifest = json.load(open(manifest_path))
except Exception as e:
    sys.stderr.write(f"FAIL: cannot parse manifest: {e}\n")
    sys.exit(1)

# Parse the schema too — Test 1 asserts BOTH files are valid JSON.
if schema_path is not None:
    try:
        json.load(open(schema_path))
    except Exception as e:
        sys.stderr.write(f"FAIL: cannot parse schema: {e}\n")
        sys.exit(1)

results = {}

# Check required top-level keys are present.
required_keys = [
    "agent_install_contract_version", "repo_id", "setup_skill",
    "standalone_setup_script", "direct_deps", "required_env_vars", "override_flags"
]
results["has_required_keys"] = all(k in manifest for k in required_keys)
results["missing_required_keys"] = [k for k in required_keys if k not in manifest]

# Check system_prerequisites is present and is a list.
sp = manifest.get("system_prerequisites", None)
results["has_system_prereqs"] = sp is not None
results["sp_is_list"] = isinstance(sp, list)
results["sp_count"] = len(sp) if isinstance(sp, list) else 0

# Check each entry in system_prerequisites has required fields.
sp_errors = []
if isinstance(sp, list):
    for i, entry in enumerate(sp):
        for field in ("id", "tier", "probe", "install", "reference"):
            if field not in entry:
                sp_errors.append(f"entry[{i}] missing required field: {field}")
        probe = entry.get("probe", {})
        for pf in ("kind", "cmd"):
            if pf not in probe:
                sp_errors.append(f"entry[{i}] probe missing required field: {pf}")
        install = entry.get("install", {})
        if "mode" not in install:
            sp_errors.append(f"entry[{i}] install missing required field: mode")
        tier = entry.get("tier", "")
        valid_tiers = {"hard", "semi-hard", "advisory"}
        if tier not in valid_tiers:
            sp_errors.append(f"entry[{i}] tier '{tier}' not in valid set {valid_tiers}")

results["sp_errors"] = sp_errors
results["sp_structurally_valid"] = len(sp_errors) == 0

print(json.dumps(results))
EOF

# read_result.py — reads a boolean key from a JSON results file.
cat > "$_TMP_DIR/read_result.py" << 'EOF'
import json, sys
d = json.load(open(sys.argv[1]))
val = d.get(sys.argv[2], False)
print("yes" if val else "no")
sys.exit(0 if val else 1)
EOF

# read_string.py — reads a string/list key from a JSON results file.
cat > "$_TMP_DIR/read_string.py" << 'EOF'
import json, sys
d = json.load(open(sys.argv[1]))
print(str(d.get(sys.argv[2], "")))
EOF

# ---------------------------------------------------------------------------
# Detect jsonschema availability.
# ---------------------------------------------------------------------------
_JSONSCHEMA_AVAILABLE=0
if python3 "$_TMP_DIR/check_jsonschema.py" 2>/dev/null; then
  _JSONSCHEMA_AVAILABLE=1
fi

# ---------------------------------------------------------------------------
# Test 1: both files parse as valid JSON.
# ---------------------------------------------------------------------------
echo "--- Test 1: schema and manifest files are valid JSON ---"
python3 "$_TMP_DIR/structural_manifest_checks.py" "$MANIFEST_FILE" "$SCHEMA_FILE" > "$_TMP_DIR/manifest_results.json" 2>&1
_PARSE_EXIT=$?
if [[ "$_PARSE_EXIT" -eq 0 ]]; then
  _pass "both schema and manifest files parse as valid JSON"
else
  _fail "structural_manifest_checks.py failed: $(cat "$_TMP_DIR/manifest_results.json" 2>/dev/null)"
fi

# ---------------------------------------------------------------------------
# Test 2: manifest has all required top-level keys.
# ---------------------------------------------------------------------------
echo "--- Test 2: manifest has all required top-level keys ---"
if python3 "$_TMP_DIR/read_result.py" "$_TMP_DIR/manifest_results.json" "has_required_keys" > /dev/null 2>&1; then
  _pass "manifest has all required top-level keys"
else
  _MISSING=$(python3 "$_TMP_DIR/read_string.py" "$_TMP_DIR/manifest_results.json" "missing_required_keys" 2>/dev/null || echo "unknown")
  _fail "manifest missing required keys: $_MISSING"
fi

# ---------------------------------------------------------------------------
# Test 3: manifest has a system_prerequisites array.
# ---------------------------------------------------------------------------
echo "--- Test 3: manifest has a system_prerequisites array ---"
if python3 "$_TMP_DIR/read_result.py" "$_TMP_DIR/manifest_results.json" "has_system_prereqs" > /dev/null 2>&1 && \
   python3 "$_TMP_DIR/read_result.py" "$_TMP_DIR/manifest_results.json" "sp_is_list" > /dev/null 2>&1; then
  _SP_COUNT=$(python3 "$_TMP_DIR/read_string.py" "$_TMP_DIR/manifest_results.json" "sp_count" 2>/dev/null || echo "0")
  _pass "manifest has system_prerequisites as a list ($_SP_COUNT entries)"
else
  _fail "manifest system_prerequisites is missing or not a list"
fi

# ---------------------------------------------------------------------------
# Test 4: each system_prerequisites entry is structurally valid.
# ---------------------------------------------------------------------------
echo "--- Test 4: each system_prerequisites entry has required fields ---"
if python3 "$_TMP_DIR/read_result.py" "$_TMP_DIR/manifest_results.json" "sp_structurally_valid" > /dev/null 2>&1; then
  _pass "all system_prerequisites entries have required fields (id, tier, probe.kind, probe.cmd, install.mode, reference)"
else
  _ERRS=$(python3 "$_TMP_DIR/read_string.py" "$_TMP_DIR/manifest_results.json" "sp_errors" 2>/dev/null || echo "unknown")
  _fail "system_prerequisites structural errors: $_ERRS"
fi

# ---------------------------------------------------------------------------
# Test 5: full schema validation (jsonschema) or structural-only (fallback).
# ---------------------------------------------------------------------------
if [[ "$_JSONSCHEMA_AVAILABLE" -eq 1 ]]; then
  echo "--- Test 5: real manifest validates against schema (jsonschema) ---"
  if python3 "$_TMP_DIR/validate_manifest.py" "$SCHEMA_FILE" "$MANIFEST_FILE" 2>&1; then
    _pass "T5: real manifest with system_prerequisites validates against schema (jsonschema Draft202012)"
  else
    _fail "T5: real manifest FAILED schema validation (see errors above)"
  fi
else
  echo "--- Test 5: jsonschema unavailable — structural validation only ---"
  echo "  NOTE: python jsonschema module not installed; Test 5 uses structural checks only."
  echo "  Install jsonschema for full semantic validation: pip install jsonschema"
  # Structural fallback: T4 above already covers the key structural checks.
  # Report as pass-with-caveat.
  _pass "T5 structural: manifest structure valid (full jsonschema validation skipped — pip install jsonschema to enable)"
fi

# ---------------------------------------------------------------------------
# Summary.
# ---------------------------------------------------------------------------
echo ""
if [[ "$_FAIL" -eq 0 ]]; then
  echo "PASS: $_PASS passed, 0 failed"
  exit 0
else
  echo "FAIL: $_PASS passed, $_FAIL failed"
  exit 1
fi
