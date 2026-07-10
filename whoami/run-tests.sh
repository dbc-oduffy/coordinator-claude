#!/usr/bin/env bash
# verify-no-console-flash: file-allow — test scaffolding; interpreter spawns run in the CI/local test harness, never the Windows interactive coordinator hot-path
# run-tests.sh — canonical test runner for the coordinator_whoami package.
#
# Why this exists: coordinator_whoami is a standalone installable package
# (its own pyproject.toml, editable install, jsonschema dependency) nested
# inside the ~/.claude meta-repo. Bare `pytest` under the meta-repo's ambient
# interpreter cannot run these tests — it lacks the editable install, jsonschema,
# and the correct sys.path, and may import a stale installed copy of the package.
# This wrapper provisions an isolated .venv (idempotent) and runs pytest inside it,
# so the suite is reproducible on any machine and consumable by the coordinator
# acceptance-oracle (check-acceptance-oracle.sh) via a bash: AC selector.
#
# NOTE on the `popup-safe-env-suppressed` markers below: this is a POSIX-only
# bash script (#!/usr/bin/env bash) that never executes on Windows, so the
# Windows-console-popup hazard the marker guards is structurally impossible here.
# The markers are the documented false-positive escape for the popup hook, which
# over-matches any python3 invocation regardless of host shell. (Paper-trail: the
# hook should exempt #!/usr/bin/env bash scripts.)
#
# Usage:
#   ./run-tests.sh                       # run the whole suite
#   ./run-tests.sh tests/test_machine.py # run a selector (any pytest args pass through)
#
# Exit code is pytest's — 0 == green, used directly by the acceptance gate.
set -euo pipefail

# Resolve our own dir so the wrapper works regardless of caller cwd (the oracle
# invokes it from the meta-repo root).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV="$SCRIPT_DIR/.venv"
SENTINEL="$VENV/.deps-installed"
PY="$VENV/bin/python"

# Provision the venv + deps once; subsequent runs skip straight to pytest.
if [[ ! -f "$SENTINEL" ]]; then
    # Review: code-reviewer — F3: scoped ERR trap so a mid-pip failure cleans the
    # half-provisioned venv; trap is cleared AFTER sentinel write so a pytest failure
    # (exec below) does NOT delete the venv.
    trap 'rm -rf "$VENV"' ERR
    if [[ ! -d "$VENV" ]]; then
        python3 -m venv "$VENV"  # popup-safe-env-suppressed (POSIX-only bash; no Windows console)
    fi
    # Editable install brings the package + its jsonschema dep; pytest is the runner.
    "$PY" -m pip install --quiet --upgrade pip          # popup-safe-env-suppressed (POSIX-only bash)
    "$PY" -m pip install --quiet -e .                   # popup-safe-env-suppressed (POSIX-only bash)
    "$PY" -m pip install --quiet pytest                 # popup-safe-env-suppressed (POSIX-only bash)
    touch "$SENTINEL"
    trap - ERR
fi

exec "$PY" -m pytest "$@"  # popup-safe-env-suppressed (POSIX-only bash)
