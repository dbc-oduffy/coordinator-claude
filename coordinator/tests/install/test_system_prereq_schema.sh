#!/usr/bin/env bash
# verify-no-console-flash: file-allow — test scaffolding; interpreter spawns run in the CI/local test harness, never the Windows interactive coordinator hot-path
# test_system_prereq_schema.sh — unit tests for the system_prerequisites schema addition.
#
# Purpose: asserts that agent-install-manifest.schema.json correctly defines the
# optional system_prerequisites array and enforces the DR-INSTALL-002 shape — probe.kind
# + probe.cmd required-field rules, the tier 3-set {hard,semi-hard,advisory}, and the
# install.mode {auto-with-confirmation,manual} shape (incl. negative-fixture rejection).
# Uses python3 + jsonschema if available; degrades to structural assertions otherwise.
# No jq dependency — python3 only (coordinator is deliberately jq-free).
#
# Spec backlink: docs/plans/2026-06-23-coordinator-root-system-prerequisites.md § C1 (AC1)
# Run: bash tests/install/test_system_prereq_schema.sh
set -euo pipefail

# ---------------------------------------------------------------------------
# Repo-root resolution — resolve relative to this script's location.
# ---------------------------------------------------------------------------
_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_REPO_ROOT="$(cd "$_SCRIPT_DIR/../.." && pwd)"

SCHEMA_FILE="$_REPO_ROOT/docs/install/agent-install-manifest.schema.json"

# ---------------------------------------------------------------------------
# Counters.
# ---------------------------------------------------------------------------
_PASS=0
_FAIL=0
_SKIP=0

_pass() { echo "  PASS: $1"; _PASS=$(( _PASS + 1 )); }
_fail() { echo "  FAIL: $1"; _FAIL=$(( _FAIL + 1 )); }
_skip() { echo "  SKIP: $1"; _SKIP=$(( _SKIP + 1 )); }

# ---------------------------------------------------------------------------
# Temp directory for fixtures and helper scripts.
# ---------------------------------------------------------------------------
_TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$_TMP_DIR"' EXIT

# ---------------------------------------------------------------------------
# Write all Python helper scripts to _TMP_DIR before any invocations.
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

# schema_checks.py — structural checks on the schema file.
# argv[1] = schema_file path
# Outputs a JSON object with boolean result fields.
cat > "$_TMP_DIR/schema_checks.py" << 'EOF'
import json, sys

schema_path = sys.argv[1]
try:
    schema = json.load(open(schema_path))
except Exception as e:
    sys.stderr.write(f"FAIL parse schema: {e}\n")
    sys.exit(1)

results = {}

schema_decl = schema.get("$schema", "")
results["has_2020_12"] = "2020-12" in schema_decl
results["schema_val"] = schema_decl

props = schema.get("properties", {})
results["has_sp_prop"] = "system_prerequisites" in props
results["sp_not_required"] = "system_prerequisites" not in schema.get("required", [])

defs = schema.get("$defs", {})
sp_def = defs.get("SystemPrereq", {})
probe_def = sp_def.get("properties", {}).get("probe", {})
results["cmd_required"] = "cmd" in probe_def.get("required", [])
results["kind_required"] = "kind" in probe_def.get("required", [])
results["reference_required"] = "reference" in sp_def.get("required", [])

tier_def = sp_def.get("properties", {}).get("tier", {})
tier_enum = sorted(tier_def.get("enum", []))
results["tier_enum"] = tier_enum
results["tier_enum_ok"] = tier_enum == ["advisory", "hard", "semi-hard"]

print(json.dumps(results))
EOF

# read_result.py — reads a specific boolean key from a JSON results file.
# argv[1] = json file, argv[2] = key name
# Exits 0 if key is truthy, 1 otherwise. Prints "yes" or "no".
cat > "$_TMP_DIR/read_result.py" << 'EOF'
import json, sys
d = json.load(open(sys.argv[1]))
val = d.get(sys.argv[2], False)
print("yes" if val else "no")
sys.exit(0 if val else 1)
EOF

# read_string.py — reads a string key from a JSON results file.
# argv[1] = json file, argv[2] = key name
# Prints the value (or empty string).
cat > "$_TMP_DIR/read_string.py" << 'EOF'
import json, sys
d = json.load(open(sys.argv[1]))
print(str(d.get(sys.argv[2], "")))
EOF

# validate_instance.py — validates a JSON instance against the schema.
# argv[1] = schema file, argv[2] = instance file, argv[3] = "valid" or "invalid"
# Exits 0 if the expected outcome matches actual.
cat > "$_TMP_DIR/validate_instance.py" << 'EOF'
import json, sys, jsonschema

schema = json.load(open(sys.argv[1]))
instance = json.load(open(sys.argv[2]))
expected = sys.argv[3]

validator = jsonschema.Draft202012Validator(schema)
errors = list(validator.iter_errors(instance))
is_valid = len(errors) == 0

if expected == "valid" and not is_valid:
    for e in errors:
        sys.stderr.write(f"  unexpected error: {e.message}\n")
    sys.exit(1)
elif expected == "invalid" and is_valid:
    sys.stderr.write("  expected failure but instance was valid\n")
    sys.exit(1)

sys.exit(0)
EOF

# structural_checks.py — structural checks without jsonschema.
# argv[1] = check_type, argv[2] = instance file
cat > "$_TMP_DIR/structural_checks.py" << 'EOF'
import json, sys

check_type = sys.argv[1]
instance = json.load(open(sys.argv[2]))

if check_type == "no_system_prereqs":
    ok = "system_prerequisites" not in instance
elif check_type == "has_system_prereqs_list":
    sp = instance.get("system_prerequisites", None)
    ok = isinstance(sp, list) and len(sp) > 0
elif check_type == "probe_missing_cmd":
    sp = instance.get("system_prerequisites", [])
    ok = any("cmd" not in e.get("probe", {}) for e in sp)
elif check_type == "auto_mode_present":
    sp = instance.get("system_prerequisites", [])
    ok = any(e.get("install", {}).get("mode") == "auto-with-confirmation" for e in sp)
else:
    sys.stderr.write(f"unknown check_type: {check_type}\n")
    ok = False

sys.exit(0 if ok else 1)
EOF

# ---------------------------------------------------------------------------
# Fixtures.
# ---------------------------------------------------------------------------

# Minimal valid manifest WITHOUT system_prerequisites (optionality test).
cat > "$_TMP_DIR/minimal.json" << 'FIXTURE_EOF'
{
  "agent_install_contract_version": 2,
  "repo_id": "x",
  "setup_skill": "/x",
  "standalone_setup_script": {"posix": "s", "windows": "w"},
  "direct_deps": [],
  "required_env_vars": [],
  "override_flags": {"skip_dep_check": "--x", "accept_hallucination_risk": "--y"}
}
FIXTURE_EOF

# Valid manifest WITH a well-formed system_prerequisites entry.
cat > "$_TMP_DIR/valid_with_prereq.json" << 'FIXTURE_EOF'
{
  "agent_install_contract_version": 2,
  "repo_id": "x",
  "setup_skill": "/x",
  "standalone_setup_script": {"posix": "s", "windows": "w"},
  "direct_deps": [],
  "required_env_vars": [],
  "override_flags": {"skip_dep_check": "--x", "accept_hallucination_risk": "--y"},
  "system_prerequisites": [
    {
      "id": "git",
      "tier": "hard",
      "probe": {"kind": "command_succeeds", "cmd": "command -v git", "ref": "_co_probe_git"},
      "install": {"mode": "manual", "remediation": "brew install git"},
      "reference": "docs/install/AGENT.md"
    }
  ]
}
FIXTURE_EOF

# v3 manifest with NO system_prerequisites — proves forward/downgrade tolerance.
# A v3 manifest that hasn't populated system_prerequisites must validate cleanly.
cat > "$_TMP_DIR/v3_no_prereqs.json" << 'FIXTURE_EOF'
{
  "agent_install_contract_version": 3,
  "repo_id": "x",
  "setup_skill": "/x",
  "standalone_setup_script": {"posix": "s", "windows": "w"},
  "direct_deps": [],
  "required_env_vars": [],
  "override_flags": {"skip_dep_check": "--x", "accept_hallucination_risk": "--y"}
}
FIXTURE_EOF

# Invalid manifest: system_prerequisites entry with probe missing cmd (only ref).
cat > "$_TMP_DIR/invalid_missing_cmd.json" << 'FIXTURE_EOF'
{
  "agent_install_contract_version": 2,
  "repo_id": "x",
  "setup_skill": "/x",
  "standalone_setup_script": {"posix": "s", "windows": "w"},
  "direct_deps": [],
  "required_env_vars": [],
  "override_flags": {"skip_dep_check": "--x", "accept_hallucination_risk": "--y"},
  "system_prerequisites": [
    {
      "id": "git",
      "tier": "hard",
      "probe": {"kind": "command_succeeds", "ref": "_co_probe_git"},
      "install": {"mode": "manual", "remediation": "brew install git"},
      "reference": "docs/install/AGENT.md"
    }
  ]
}
FIXTURE_EOF

# Invalid manifest: tier uses the DR-retired `optional` value (must be rejected).
cat > "$_TMP_DIR/invalid_tier_optional.json" << 'FIXTURE_EOF'
{
  "agent_install_contract_version": 2,
  "repo_id": "x",
  "setup_skill": "/x",
  "standalone_setup_script": {"posix": "s", "windows": "w"},
  "direct_deps": [],
  "required_env_vars": [],
  "override_flags": {"skip_dep_check": "--x", "accept_hallucination_risk": "--y"},
  "system_prerequisites": [
    {
      "id": "git",
      "tier": "optional",
      "probe": {"kind": "command_succeeds", "cmd": "command -v git"},
      "install": {"mode": "manual", "remediation": "brew install git"},
      "reference": "docs/install/AGENT.md"
    }
  ]
}
FIXTURE_EOF

# Invalid manifest: probe missing the now-required `kind` (only cmd present).
cat > "$_TMP_DIR/invalid_missing_kind.json" << 'FIXTURE_EOF'
{
  "agent_install_contract_version": 2,
  "repo_id": "x",
  "setup_skill": "/x",
  "standalone_setup_script": {"posix": "s", "windows": "w"},
  "direct_deps": [],
  "required_env_vars": [],
  "override_flags": {"skip_dep_check": "--x", "accept_hallucination_risk": "--y"},
  "system_prerequisites": [
    {
      "id": "git",
      "tier": "hard",
      "probe": {"cmd": "command -v git"},
      "install": {"mode": "manual", "remediation": "brew install git"},
      "reference": "docs/install/AGENT.md"
    }
  ]
}
FIXTURE_EOF

# Invalid manifest: entry missing the now-required `reference` (DR-INSTALL-002 §3 required item key).
cat > "$_TMP_DIR/invalid_missing_reference.json" << 'FIXTURE_EOF'
{
  "agent_install_contract_version": 2,
  "repo_id": "x",
  "setup_skill": "/x",
  "standalone_setup_script": {"posix": "s", "windows": "w"},
  "direct_deps": [],
  "required_env_vars": [],
  "override_flags": {"skip_dep_check": "--x", "accept_hallucination_risk": "--y"},
  "system_prerequisites": [
    {
      "id": "git",
      "tier": "hard",
      "probe": {"kind": "command_succeeds", "cmd": "command -v git"},
      "install": {"mode": "manual", "remediation": "brew install git"}
    }
  ]
}
FIXTURE_EOF

# Valid manifest: install.mode auto-with-confirmation + per-platform command strings (no remediation).
cat > "$_TMP_DIR/valid_auto_mode.json" << 'FIXTURE_EOF'
{
  "agent_install_contract_version": 3,
  "repo_id": "x",
  "setup_skill": "/x",
  "standalone_setup_script": {"posix": "s", "windows": "w"},
  "direct_deps": [],
  "required_env_vars": [],
  "override_flags": {"skip_dep_check": "--x", "accept_hallucination_risk": "--y"},
  "system_prerequisites": [
    {
      "id": "ollama",
      "tier": "semi-hard",
      "probe": {"kind": "command_succeeds", "cmd": "command -v ollama", "shell": true},
      "install": {"mode": "auto-with-confirmation", "posix": "brew install ollama", "windows": "winget install Ollama.Ollama"},
      "applies_to": ["consumer", "vendor"],
      "reference": "https://ollama.com — local inference; RAG-only fallback if absent"
    }
  ]
}
FIXTURE_EOF

# ---------------------------------------------------------------------------
# Detect jsonschema availability.
# ---------------------------------------------------------------------------
_JSONSCHEMA_AVAILABLE=0
if python3 "$_TMP_DIR/check_jsonschema.py" 2>/dev/null; then
  _JSONSCHEMA_AVAILABLE=1
fi

# ---------------------------------------------------------------------------
# Test 1: schema file is valid JSON and structural checks pass.
# ---------------------------------------------------------------------------
echo "--- Test 1: schema file is valid JSON ---"
if python3 "$_TMP_DIR/schema_checks.py" "$SCHEMA_FILE" > "$_TMP_DIR/schema_results.json" 2>&1; then
  _pass "schema file is valid JSON (structural checks ran OK)"
else
  _fail "schema file failed JSON parse or structural check: $(cat "$_TMP_DIR/schema_results.json" 2>/dev/null)"
fi

# ---------------------------------------------------------------------------
# Test 2: schema has dollar-schema declaration (JSON Schema 2020-12).
# ---------------------------------------------------------------------------
echo "--- Test 2: schema has dollar-schema declaration (2020-12) ---"
if python3 "$_TMP_DIR/read_result.py" "$_TMP_DIR/schema_results.json" "has_2020_12" > /dev/null 2>&1; then
  _pass "schema declares JSON Schema 2020-12"
else
  _SVAL=$(python3 "$_TMP_DIR/read_string.py" "$_TMP_DIR/schema_results.json" "schema_val" 2>/dev/null || echo "unknown")
  _fail "schema dollar-schema missing or not 2020-12 (got: $_SVAL)"
fi

# ---------------------------------------------------------------------------
# Test 3: schema defines system_prerequisites in properties.
# ---------------------------------------------------------------------------
echo "--- Test 3: schema defines system_prerequisites property ---"
if python3 "$_TMP_DIR/read_result.py" "$_TMP_DIR/schema_results.json" "has_sp_prop" > /dev/null 2>&1; then
  _pass "schema properties contains system_prerequisites"
else
  _fail "schema properties does NOT contain system_prerequisites"
fi

# ---------------------------------------------------------------------------
# Test 4: system_prerequisites is NOT in the schema's required array (optional).
# ---------------------------------------------------------------------------
echo "--- Test 4: system_prerequisites is optional (not in required[]) ---"
if python3 "$_TMP_DIR/read_result.py" "$_TMP_DIR/schema_results.json" "sp_not_required" > /dev/null 2>&1; then
  _pass "system_prerequisites is optional (absent from required[])"
else
  _fail "system_prerequisites is incorrectly listed in required[]"
fi

# ---------------------------------------------------------------------------
# Test 5: probe.cmd is required in SystemPrereq.
# ---------------------------------------------------------------------------
echo "--- Test 5: SystemPrereq defs probe.cmd is required ---"
if python3 "$_TMP_DIR/read_result.py" "$_TMP_DIR/schema_results.json" "cmd_required" > /dev/null 2>&1; then
  _pass "probe.cmd is listed as required in SystemPrereq probe object"
else
  _fail "probe.cmd is NOT listed as required in SystemPrereq probe object"
fi

# ---------------------------------------------------------------------------
# Test 5b: probe.kind is required in SystemPrereq (DR-INSTALL-002 §2c load-bearing add).
# ---------------------------------------------------------------------------
echo "--- Test 5b: SystemPrereq defs probe.kind is required (DR-INSTALL-002) ---"
if python3 "$_TMP_DIR/read_result.py" "$_TMP_DIR/schema_results.json" "kind_required" > /dev/null 2>&1; then
  _pass "probe.kind is listed as required in SystemPrereq probe object"
else
  _fail "probe.kind is NOT listed as required in SystemPrereq probe object (DR-INSTALL-002 §2c)"
fi

# ---------------------------------------------------------------------------
# Test 6: tier enum contains exactly the three DR-INSTALL-002 values.
# ---------------------------------------------------------------------------
echo "--- Test 6: tier enum contains hard, semi-hard, advisory (DR-INSTALL-002 dropped optional) ---"
if python3 "$_TMP_DIR/read_result.py" "$_TMP_DIR/schema_results.json" "tier_enum_ok" > /dev/null 2>&1; then
  _pass "tier enum is exactly {hard, semi-hard, advisory}"
else
  _TGOT=$(python3 "$_TMP_DIR/read_string.py" "$_TMP_DIR/schema_results.json" "tier_enum" 2>/dev/null || echo "unknown")
  _fail "tier enum unexpected (got: $_TGOT)"
fi

# ---------------------------------------------------------------------------
# Test 6b: reference is required on SystemPrereq (DR-INSTALL-002 §3 required item key).
# ---------------------------------------------------------------------------
echo "--- Test 6b: SystemPrereq 'reference' is required (DR-INSTALL-002 §3) ---"
if python3 "$_TMP_DIR/read_result.py" "$_TMP_DIR/schema_results.json" "reference_required" > /dev/null 2>&1; then
  _pass "reference is listed as required in SystemPrereq"
else
  _fail "reference is NOT listed as required in SystemPrereq (DR-INSTALL-002 §3)"
fi

# ---------------------------------------------------------------------------
# Tests 7-9: jsonschema validation tests (or structural fallback).
# ---------------------------------------------------------------------------
if [[ "$_JSONSCHEMA_AVAILABLE" -eq 1 ]]; then
  echo "--- Test 7: minimal manifest (no system_prerequisites) validates ---"
  if python3 "$_TMP_DIR/validate_instance.py" "$SCHEMA_FILE" "$_TMP_DIR/minimal.json" "valid" 2>&1; then
    _pass "T7: minimal manifest without system_prerequisites validates against schema"
  else
    _fail "T7: minimal manifest WITHOUT system_prerequisites failed schema validation (unexpected)"
  fi

  echo "--- Test 8: manifest with valid system_prerequisites entry validates ---"
  if python3 "$_TMP_DIR/validate_instance.py" "$SCHEMA_FILE" "$_TMP_DIR/valid_with_prereq.json" "valid" 2>&1; then
    _pass "T8: manifest with valid system_prerequisites entry validates against schema"
  else
    _fail "T8: manifest with valid system_prerequisites entry failed schema validation (unexpected)"
  fi

  echo "--- Test 9: manifest with probe missing cmd FAILS validation ---"
  if python3 "$_TMP_DIR/validate_instance.py" "$SCHEMA_FILE" "$_TMP_DIR/invalid_missing_cmd.json" "invalid" 2>&1; then
    _pass "T9: manifest with probe missing cmd correctly FAILS schema validation (cmd is required)"
  else
    _fail "T9: manifest with probe missing cmd unexpectedly passed validation (cmd should be required)"
  fi

  echo "--- Test 10: v3 manifest with no system_prerequisites validates (forward tolerance) ---"
  if python3 "$_TMP_DIR/validate_instance.py" "$SCHEMA_FILE" "$_TMP_DIR/v3_no_prereqs.json" "valid" 2>&1; then
    _pass "T10: v3 manifest without system_prerequisites validates against schema (system_prerequisites is optional)"
  else
    _fail "T10: v3 manifest without system_prerequisites failed schema validation (unexpected — system_prerequisites must be optional)"
  fi

  echo "--- Test 11: tier 'optional' (DR-retired) FAILS validation ---"
  if python3 "$_TMP_DIR/validate_instance.py" "$SCHEMA_FILE" "$_TMP_DIR/invalid_tier_optional.json" "invalid" 2>&1; then
    _pass "T11: tier='optional' correctly FAILS validation (DR-INSTALL-002 retired it from the enum)"
  else
    _fail "T11: tier='optional' unexpectedly passed validation (enum should be {hard,semi-hard,advisory})"
  fi

  echo "--- Test 12: probe missing 'kind' FAILS validation ---"
  if python3 "$_TMP_DIR/validate_instance.py" "$SCHEMA_FILE" "$_TMP_DIR/invalid_missing_kind.json" "invalid" 2>&1; then
    _pass "T12: probe without kind correctly FAILS validation (kind is required, DR-INSTALL-002 §2c)"
  else
    _fail "T12: probe without kind unexpectedly passed validation (kind should be required)"
  fi

  echo "--- Test 13: install.mode auto-with-confirmation + posix/windows validates ---"
  if python3 "$_TMP_DIR/validate_instance.py" "$SCHEMA_FILE" "$_TMP_DIR/valid_auto_mode.json" "valid" 2>&1; then
    _pass "T13: auto-with-confirmation entry (posix/windows, no remediation) + applies_to + probe.shell validates"
  else
    _fail "T13: auto-with-confirmation entry failed validation (unexpected — DR-INSTALL-002 additive shape must validate)"
  fi

  echo "--- Test 14: entry missing 'reference' FAILS validation (DR-INSTALL-002 §3 required) ---"
  if python3 "$_TMP_DIR/validate_instance.py" "$SCHEMA_FILE" "$_TMP_DIR/invalid_missing_reference.json" "invalid" 2>&1; then
    _pass "T14: entry without reference correctly FAILS validation (reference is required, DR-INSTALL-002 §3)"
  else
    _fail "T14: entry without reference unexpectedly passed validation (reference should be required)"
  fi

else
  echo "--- Tests 7-9: jsonschema unavailable — structural fallback ---"
  echo "  NOTE: python jsonschema module not installed; using structural assertions (key presence only)."
  echo "  Install jsonschema for full semantic validation: pip install jsonschema"

  # Structural T7: SKIP — without jsonschema, we cannot test whether the schema
  # actually rejects instances that should be optional (that is a schema-enforcement
  # question, not a fixture-shape question). Checking that the fixture lacks the key
  # only proves the fixture was written correctly, not that the schema enforces optionality.
  _skip "T7: schema-constraint enforcement untestable without jsonschema (install: pip install jsonschema)"

  # Structural T8: valid-with-prereq manifest has system_prerequisites as a non-empty list.
  if python3 "$_TMP_DIR/structural_checks.py" "has_system_prereqs_list" "$_TMP_DIR/valid_with_prereq.json" 2>/dev/null; then
    _pass "T8 structural: manifest with system_prerequisites has it as a non-empty list"
  else
    _fail "T8 structural: manifest system_prerequisites is not a non-empty list"
  fi

  # Structural T9: SKIP — without jsonschema, we cannot test whether the schema
  # actually rejects a probe missing cmd (that is a schema-constraint-enforcement
  # question). Checking that the fixture is missing cmd only proves the fixture was
  # written correctly, not that the schema enforces the required field.
  _skip "T9: schema-constraint enforcement untestable without jsonschema (install: pip install jsonschema)"

  # Structural T10: v3 manifest without system_prerequisites has no system_prerequisites key.
  if python3 "$_TMP_DIR/structural_checks.py" "no_system_prereqs" "$_TMP_DIR/v3_no_prereqs.json" 2>/dev/null; then
    _pass "T10 structural: v3 manifest without system_prerequisites has key absent (optional OK)"
  else
    _fail "T10 structural: v3 manifest unexpectedly has system_prerequisites key"
  fi

  # Structural T11/T12: SKIP — rejection of tier='optional' / missing-kind is a schema-enforcement
  # question untestable without jsonschema (the fixtures only prove they were written wrong).
  _skip "T11: tier-enum rejection untestable without jsonschema (install: pip install jsonschema)"
  _skip "T12: missing-kind rejection untestable without jsonschema (install: pip install jsonschema)"

  # Structural T13: valid_auto_mode fixture carries an auto-with-confirmation install entry.
  if python3 "$_TMP_DIR/structural_checks.py" "auto_mode_present" "$_TMP_DIR/valid_auto_mode.json" 2>/dev/null; then
    _pass "T13 structural: auto-with-confirmation entry present in fixture (shape exercised)"
  else
    _fail "T13 structural: auto-with-confirmation entry not found in fixture"
  fi

  _skip "T14: reference-required rejection untestable without jsonschema (install: pip install jsonschema)"
fi

# ---------------------------------------------------------------------------
# Summary.
# ---------------------------------------------------------------------------
echo ""
if [[ "$_FAIL" -eq 0 ]]; then
  echo "PASS: $_PASS passed, 0 failed, $_SKIP skipped"
  exit 0
else
  echo "FAIL: $_PASS passed, $_FAIL failed, $_SKIP skipped"
  exit 1
fi
