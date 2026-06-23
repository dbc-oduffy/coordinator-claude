#!/usr/bin/env bats
# refresh-source-is-live-venv.bats — bats tests for the source_is_live venv-currency
# probe in bin/refresh-plugin-live-install.sh.
#
# Purpose: regression coverage for the gap holodeck-em reported 2026-06-09
#   (cross-repo/inbox/2026-06-09-source-is-live-editable-venv-currency.md): a
#   source_is_live plugin keeps file content current via the junction, but its
#   editable pip/dist-info metadata lags a pyproject version bump nobody reinstalled.
#   The probe reads the installed Version from dist-info METADATA (what `pip show`
#   reads — no subprocess, so no Windows console popup), compares it to the
#   pyproject version, and re-runs the editable install on skew.
#
# Determinism: a CLAUDE_HOME sandbox supplies a fixture registry + fake source tree;
#   the editable reinstall is stubbed via the COORDINATOR_REFRESH_VENV_INSTALL_CMD
#   seam, so no real `uv`/`pip` runs. No accidental-timing or live-junction dependence.
#
# Run: npx bats plugins/coordinator-claude/coordinator/tests/refresh-source-is-live-venv.bats
#      from the ~/.claude repo root.
#
# Portability (DR-148): bash >= 4 + BSD coreutils; no grep -P / date -d / sed -i.

SCRIPT_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")" && pwd)"
SUBJECT="${SCRIPT_DIR}/../bin/refresh-plugin-live-install.sh"

setup() {
  TMP="$(mktemp -d)"
  # CLAUDE_HOME is a $HOME substitute: .claude/ and machine-local/ resolve under it.
  export CLAUDE_HOME="${TMP}/home"
  CLAUDE_DIR="${CLAUDE_HOME}/.claude"
  mkdir -p "${CLAUDE_DIR}/machine-local" "${CLAUDE_DIR}/plugins" "${CLAUDE_DIR}/bin"
  # bin/claude-home is a forwarder to ${CLAUDE_HOME}/.claude/bin/claude-home; stage a
  # shim there that execs the real CLAUDE_HOME-aware resolver by absolute path (a
  # symlink would break the resolver's next-to-itself _claude_home.py discovery).
  _resolver="$(cd "${SCRIPT_DIR}/../lib/claude-home" && pwd)/claude-home"
  printf '#!/usr/bin/env bash\nexec "%s" "$@"\n' "$_resolver" > "${CLAUDE_DIR}/bin/claude-home"
  chmod +x "${CLAUDE_DIR}/bin/claude-home"
  REG="${CLAUDE_DIR}/machine-local/registry.local.toml"
  SRC="${TMP}/src"                  # the fake source_is_live plugin tree
  mkdir -p "$SRC"
  MARKER="${TMP}/reinstall.marker"  # touched by the install seam when it fires
}

teardown() {
  rm -rf "$TMP"
}

# ---------------------------------------------------------------------------
# Fixture writers
# ---------------------------------------------------------------------------

_write_registry() {
  cat > "$REG" <<EOF
[plugin.mirrors.testpkg]
propagation_mode = "source_is_live"
source_path = "${SRC}"
dist_name = "testpkg"
EOF
}

_write_pyproject() {  # $1 = source version
  cat > "${SRC}/pyproject.toml" <<EOF
[project]
name = "testpkg"
version = "$1"
EOF
}

_write_distinfo() {  # $1 = installed version
  local di="${SRC}/.venv/lib/python3.11/site-packages/testpkg-$1.dist-info"
  mkdir -p "$di"
  printf 'Metadata-Version: 2.1\nName: testpkg\nVersion: %s\n' "$1" > "${di}/METADATA"
}

# ---------------------------------------------------------------------------
# Skew path — stale venv metadata triggers the editable reinstall
# ---------------------------------------------------------------------------

@test "source_is_live: version skew (installed < source) triggers editable reinstall" {
  _write_registry
  _write_pyproject "0.10.0"
  _write_distinfo "0.8.0"
  run env COORDINATOR_REFRESH_VENV_INSTALL_CMD="touch '${MARKER}'" \
      bash "$SUBJECT" testpkg
  [ "$status" -eq 0 ]
  [ -f "$MARKER" ]
  [[ "$output" == *"venv STALE"* ]]
  [[ "$output" == *"installed=v0.8.0"* ]]
  [[ "$output" == *"refreshed to v0.10.0"* ]]
}

@test "source_is_live: skew refresh writes a refresh-log line" {
  _write_registry
  _write_pyproject "0.10.0"
  _write_distinfo "0.8.0"
  run env COORDINATOR_REFRESH_VENV_INSTALL_CMD="true" bash "$SUBJECT" testpkg
  [ "$status" -eq 0 ]
  grep -q "source_is_live venv-refresh v0.8.0->v0.10.0" "${CLAUDE_DIR}/plugins/.refresh-log"
}

# ---------------------------------------------------------------------------
# Current path — matching versions skip the reinstall
# ---------------------------------------------------------------------------

@test "source_is_live: matching versions skip the reinstall (no-op)" {
  _write_registry
  _write_pyproject "0.10.0"
  _write_distinfo "0.10.0"
  run env COORDINATOR_REFRESH_VENV_INSTALL_CMD="touch '${MARKER}'" \
      bash "$SUBJECT" testpkg
  [ "$status" -eq 0 ]
  [ ! -f "$MARKER" ]
  [[ "$output" == *"venv current (v0.10.0)"* ]]
}

# ---------------------------------------------------------------------------
# Not-probeable / structural-no-op paths
# ---------------------------------------------------------------------------

@test "source_is_live: no installed dist-info is a clean no-op (not probeable)" {
  _write_registry
  _write_pyproject "0.10.0"     # no .venv / dist-info created
  run env COORDINATOR_REFRESH_VENV_INSTALL_CMD="touch '${MARKER}'" \
      bash "$SUBJECT" testpkg
  [ "$status" -eq 0 ]
  [ ! -f "$MARKER" ]
  [[ "$output" == *"not probeable"* ]]
}

@test "source_is_live without a pyproject falls back to the original structural no-op" {
  _write_registry               # source_path present but no pyproject.toml
  run bash "$SUBJECT" testpkg
  [ "$status" -eq 0 ]
  [[ "$output" == *"live install IS the canonical source"* ]]
}

# ---------------------------------------------------------------------------
# Windows layout — capital Lib/site-packages (F9)
# ---------------------------------------------------------------------------

# Review: code-reviewer F9 — Windows venvs place dist-info under
# .venv/Lib/site-packages (capital Lib) rather than .venv/lib/python*/site-packages.
# The script glob covers both arms:
#   for _sp in "$SIL_VENV/Lib/site-packages" "$SIL_VENV/lib/python*/site-packages"
# This case creates the dist-info under the capital-Lib arm and asserts that a
# version skew still triggers the reinstall, proving the Windows glob path is live.
_write_distinfo_windows() {  # $1 = installed version
  local di="${SRC}/.venv/Lib/site-packages/testpkg-$1.dist-info"
  mkdir -p "$di"
  printf 'Metadata-Version: 2.1\nName: testpkg\nVersion: %s\n' "$1" > "${di}/METADATA"
}

@test "source_is_live: Windows Lib/site-packages layout (capital Lib) — skew triggers reinstall" {
  _write_registry
  _write_pyproject "0.10.0"
  _write_distinfo_windows "0.8.0"
  run env COORDINATOR_REFRESH_VENV_INSTALL_CMD="touch '${MARKER}'" \
      bash "$SUBJECT" testpkg
  [ "$status" -eq 0 ]
  [ -f "$MARKER" ]
  [[ "$output" == *"venv STALE"* ]]
  [[ "$output" == *"installed=v0.8.0"* ]]
  [[ "$output" == *"refreshed to v0.10.0"* ]]
}
