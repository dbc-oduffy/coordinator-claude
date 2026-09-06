#!/bin/bash
# Cloud-environment setup script — SPIKE. Paste into "Setup script" at claude.ai/code.
#
# PURPOSE: land coordinator-claude and its engine on an Anthropic-managed cloud VM BEFORE Claude
# Code launches, without touching the claude.ai-hosted plugin surface at all. It registers the
# plugin from a `directory` marketplace source in user settings, so the top-level-bin/ ban
# (claude-ai-hosted-plugin-constraints.md) never applies on this route — nothing is uploaded, no
# admin approval surface is involved, and no `claude` binary is needed at setup time.
#
# PASTE THIS ALONGSIDE — the "Environment variables" box, which reaches the SESSION but NOT this
# script (which is why every value below is also hardcoded here):
#
#     COORDINATOR_SETTINGS_HOME=/root/.coordinator-claude-settings
#     COORDINATOR_ENGINE_ROOT=/opt/coordinator/claude-klabauter
#
# If the report below says HOME is not /root, or /opt was not writable, change both to match the
# ROOT= line this script printed — they must name the paths it actually used.
#
# SPIKE SCOPE, stated plainly: this gets the plugin LOADED with a resolvable engine. It does NOT
# run /coordinator:install (Phase 3 substrate, machine-local registry, the restart gate). Those
# need a live session and are the next increment. Expect a degraded-but-working coordinator: hooks
# resolve, the bin/ CLI surface does not.
#
# It always exits 0. A non-zero exit fails the whole session, so every finding is a FAIL line to
# read in the setup checklist, never a boot abort. Phase 0 is the probe — it reports the facts a
# developer host cannot establish, and it runs first so its answers are on record even when a later
# phase fails.
#
# RUNS ONCE, then the filesystem is snapshotted; later sessions skip it. Re-runs only when this
# script or the allowed-host list changes, or at ~7-day expiry. Budget is ~5 minutes.

set -u

REPO_MARKETPLACE=https://github.com/dbc-oduffy/coordinator-claude
REPO_ENGINE=https://github.com/dbc-oduffy/claude-klabauter

echo "=== phase 0: probe (facts unestablishable from a developer host) ==="
echo "whoami=$(whoami)  HOME=$HOME  PWD=$PWD"

# /opt is the documented seed location; $HOME is the fallback. Which one we get changes the paths
# the env-var block above must carry, so this is the first thing decided and the first thing said.
if mkdir -p /opt/coordinator 2>/dev/null; then
  ROOT=/opt/coordinator
else
  ROOT="$HOME/coordinator"
  mkdir -p "$ROOT" 2>/dev/null
  echo "/opt not writable — falling back to \$HOME"
fi
echo "ROOT=$ROOT"

for t in claude python3 pip3 git jq uv; do
  if p="$(command -v "$t" 2>/dev/null)"; then echo "tool $t: $p"; else echo "tool $t: ABSENT"; fi
done
python3 -V 2>&1 || true

# PEP 668: Ubuntu 24.04 ships EXTERNALLY-MANAGED in the system interpreter, and the engine's own
# installer refuses such an interpreter outright (exit 96, no fallback). This script does not run
# that installer, so the marker is not fatal here — but it decides how phase 2 installs deps, and
# it decides whether the NEXT increment can run /coordinator:install at all.
if command -v python3 >/dev/null 2>&1; then
  python3 - <<'PY' 2>&1 || true
import os, sysconfig
p = os.path.join(sysconfig.get_paths()["stdlib"], "EXTERNALLY-MANAGED")
print(("pep668: EXTERNALLY-MANAGED at " + p) if os.path.exists(p) else "pep668: unmanaged")
PY
fi

command -v check-tools >/dev/null 2>&1 && check-tools 2>&1 | head -30

echo "=== phase 1: clone (setup-phase egress, not the session's) ==="
# Claude Code connects to the agent proxy AFTER this script runs, so reachability here is its own
# question — an in-session check would not have answered it.
clone() {
  local url=$1 dest=$2
  if [ -d "$dest/.git" ]; then echo "clone $dest: present already"; return 0; fi
  if git clone --depth 1 "$url" "$dest" >/dev/null 2>&1; then
    echo "clone $dest: OK ($(git -C "$dest" rev-parse --short HEAD))"
  else
    echo "clone $dest: FAIL — $url unreachable under this network policy"
    return 1
  fi
}
clone "$REPO_MARKETPLACE" "$ROOT/coordinator-claude"
HAVE_PLUGIN=$?
clone "$REPO_ENGINE" "$ROOT/claude-klabauter"
HAVE_ENGINE=$?

echo "=== phase 2: engine runtime deps ==="
# coordinator_core needs Python >=3.11 plus these four; a bare clone cannot import without them.
# Three routes tried in order of least surprise. --break-system-packages is deliberately NOT one of
# them: the engine's own installer refuses that path by PM ruling, and a setup script that took it
# would leave a machine the installer then declines to run on.
DEPS="pydantic psutil jsonschema PyYAML"
PYBIN=python3
if pip3 install --user --quiet $DEPS 2>/dev/null; then
  echo "deps: OK (pip3 --user)"
elif command -v uv >/dev/null 2>&1 && uv pip install --system --quiet $DEPS 2>/dev/null; then
  echo "deps: OK (uv --system)"
elif python3 -m venv "$ROOT/venv" 2>/dev/null && "$ROOT/venv/bin/pip" install --quiet $DEPS 2>/dev/null; then
  PYBIN="$ROOT/venv/bin/python"
  echo "deps: OK (venv at $ROOT/venv) — note this interpreter is NOT what hooks invoke as python3"
else
  echo "deps: FAIL — engine will not import; coordinator loads degraded"
fi
echo "PYBIN=$PYBIN"

echo "=== phase 3: register the plugin in user settings ==="
# The `directory` source is what sidesteps the hosted surface: Claude Code reads the marketplace
# manifest off local disk at launch and clones nothing. The mirror is FLAT — its
# .claude-plugin/marketplace.json sits at the repo root, unlike the DoE source tree where the
# manifest is one level down under coordinator/. Pointing at the wrong level fails with
# "Marketplace file not found".
mkdir -p "$HOME/.claude"
SETTINGS="$HOME/.claude/settings.json"
if [ "$HAVE_PLUGIN" -eq 0 ] && command -v python3 >/dev/null 2>&1; then
  # Merged, never clobbered: Claude Code may have written this file already, and a fresh write
  # would silently drop whatever else it holds.
  MP="$ROOT/coordinator-claude" python3 - "$SETTINGS" <<'PY' 2>&1 || echo "settings: FAIL"
import json, os, sys
path = sys.argv[1]
try:
    with open(path) as f:
        s = json.load(f)
except Exception:
    s = {}
s.setdefault("extraKnownMarketplaces", {})["coordinator-claude"] = {
    "source": {"source": "directory", "path": os.environ["MP"]}
}
s.setdefault("enabledPlugins", {})["coordinator@coordinator-claude"] = True
with open(path, "w") as f:
    json.dump(s, f, indent=2)
print("settings: OK ->", path)
PY
else
  echo "settings: SKIPPED (no plugin clone, or no python3 to merge JSON)"
fi

echo "=== phase 4: engine root pointer ==="
# The ordering hole: the machine-local registry's reader is written by coordinator-claude's
# INSTALL, which has not run and cannot run here. The durable pointer file is the documented
# cold-box substitute and needs no reader at all.
if [ "$HAVE_ENGINE" -eq 0 ]; then
  mkdir -p "$HOME/.coordinator-claude-settings/machine-local"
  echo "$ROOT/claude-klabauter" > "$HOME/.coordinator-claude-settings/machine-local/.claude-klabauter-live-root"
  echo "engine pointer: OK -> $ROOT/claude-klabauter"
else
  echo "engine pointer: SKIPPED (no engine clone)"
fi

echo "=== phase 5: verify what the session will actually see ==="
if [ "$HAVE_PLUGIN" -eq 0 ]; then
  test -f "$ROOT/coordinator-claude/.claude-plugin/marketplace.json" \
    && echo "manifest: OK" || echo "manifest: FAIL — wrong directory level for the source path"
fi
if [ "$HAVE_ENGINE" -eq 0 ]; then
  COORDINATOR_ENGINE_ROOT="$ROOT/claude-klabauter" "$PYBIN" -c \
    "import sys; sys.path.insert(0, '$ROOT/claude-klabauter'); import coordinator_core; print('engine import: OK')" \
    2>&1 | tail -1
fi
echo "REMINDER: the env-var block must carry COORDINATOR_ENGINE_ROOT=$ROOT/claude-klabauter"
echo "=== setup complete ==="
exit 0
