#!/usr/bin/env bash


# REPO-AGNOSTIC BY DESIGN, AND THAT IS THE POINT. This is pasted into a cloud ENVIRONMENT, which is
# the OPERATOR's surface at claude.ai/code — not a file in any repo and not a step any repo's own


# ONE EXCEPTION, LIVE TODAY: doctrine (phase 3b)'s third candidate is a published copy that, as of


# PASTE THIS ALONGSIDE — the "Environment variables" box, which reaches the SESSION but NOT this


#     COORDINATOR_SETTINGS_HOME=/root/.coordinator-claude-settings

# NOT COORDINATOR_ENGINE_ROOT. It is a live-tree override, so a session-wide value pins every


set -u

REPO_MARKETPLACE=https://github.com/dbc-oduffy/coordinator-claude
REPO_ENGINE=https://github.com/dbc-oduffy/claude-klabauter
LOG="$HOME/.coordinator-cloud-setup.log"


main() {

echo "=== phase 0: probe (facts unestablishable from a developer host) ==="
echo "whoami=$(whoami)  HOME=$HOME  PWD=$PWD"


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


if command -v python3 >/dev/null 2>&1; then
  python3 - <<'PY' 2>&1 || true
import os, sysconfig
p = os.path.join(sysconfig.get_paths()["stdlib"], "EXTERNALLY-MANAGED")
print(("pep668: EXTERNALLY-MANAGED at " + p) if os.path.exists(p) else "pep668: unmanaged")
PY
fi

command -v check-tools >/dev/null 2>&1 && check-tools 2>&1 | head -30

echo "=== phase 1: clone (setup-phase egress, not the session's) ==="


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


mkdir -p "$HOME/.claude"
SETTINGS="$HOME/.claude/settings.json"
if [ "$HAVE_PLUGIN" -eq 0 ] && command -v python3 >/dev/null 2>&1; then
  
  
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

echo "=== phase 3b: global doctrine into the VM's own HOME ==="


# A-VM-WRITTEN-HOME-CLAUDE-IS-NOT-YOUR-MACHINES-HOME-CLAUDE), and it is why phase 3 can register a


DOCTRINE_SRC=""
for cand in "$PWD/global-doctrine" /workspace/*/global-doctrine \
            "$ROOT/coordinator-claude/templates/global-doctrine"; do
  [ -f "$cand/CLAUDE.md" ] && { DOCTRINE_SRC="$cand"; break; }
done
if [ -n "$DOCTRINE_SRC" ]; then
  mkdir -p "$HOME/.claude/rules"
  
  
  if cp "$DOCTRINE_SRC/CLAUDE.md" "$HOME/.claude/CLAUDE.md"; then
    
    
    if [ -d "$DOCTRINE_SRC/rules" ]; then
      if cp "$DOCTRINE_SRC/rules"/*.md "$HOME/.claude/rules/"; then
        RULES_STATUS="rules: OK"
      else
        RULES_STATUS="rules: FAIL (copy error, see above)"
      fi
    else
      RULES_STATUS="rules: none present at $DOCTRINE_SRC/rules"
    fi
    echo "doctrine: OK -> \$HOME/.claude/CLAUDE.md (from $DOCTRINE_SRC); $RULES_STATUS"
  else
    echo "doctrine: FAIL (copy error, see above) -> \$HOME/.claude/CLAUDE.md (from $DOCTRINE_SRC)"
  fi
else
  
  
  echo "doctrine: FAIL (no copy found — session runs doctrine-blind; see README.md § Known gap)"
fi

echo "=== phase 4: engine root pointer ==="


if [ "$HAVE_ENGINE" -eq 0 ]; then
  
  # things: `.claude-klabauter-root` is the PUBLISHED build (admitted only with a tracked
  
  
  mkdir -p "$HOME/.coordinator-claude-settings/machine-local"
  echo "$ROOT/claude-klabauter" > "$HOME/.coordinator-claude-settings/machine-local/.claude-klabauter-root"
  echo "engine pointer: OK -> $ROOT/claude-klabauter"
else
  echo "engine pointer: SKIPPED (no engine clone)"
fi

echo "=== phase 4b: run the engine installer ==="


# image's python3 carries no EXTERNALLY-MANAGED marker, so the installer's exit-96 refusal cannot


if [ "$HAVE_ENGINE" -eq 0 ]; then
  
  
  ( cd "$ROOT/claude-klabauter" && COORDINATOR_ENGINE_ROOT="$ROOT/claude-klabauter" \
      COORDINATOR_SETTINGS_HOME="$HOME/.coordinator-claude-settings" \
      "$PYBIN" scripts/setup.py --i-am-agent < /dev/null ) 2>&1 | tail -25
  rc=${PIPESTATUS[0]}
  
  
  case "$rc" in
    0)  echo "engine install: OK" ;;
    90) echo "engine install: FAIL rc=90 (hard dep missing)" ;;
    95) echo "engine install: FAIL rc=95 (repo identity unresolved)" ;;
    96) echo "engine install: FAIL rc=96 (interpreter refused — the image now ships a PEP-668 marker)" ;;
    *)  echo "engine install: FAIL rc=$rc" ;;
  esac
else
  echo "engine install: SKIPPED (no engine clone)"
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
  
  
  "$PYBIN" -c "import pydantic, psutil, jsonschema, yaml; print('deps import: OK')" 2>&1 | tail -1
fi
# The PUBLISHED-engine pointer, written here so the env block never has to carry an override to


if [ "$HAVE_ENGINE" -eq 0 ]; then
  if [ -f "$ROOT/claude-klabauter/coordinator_core/_engine_stamp" ]; then
    mkdir -p "$HOME/.coordinator-claude-settings/machine-local" 2>/dev/null || true
    printf '%s\n' "$ROOT/claude-klabauter" \
      > "$HOME/.coordinator-claude-settings/machine-local/.claude-klabauter-root" 2>/dev/null \
      && echo "engine pointer: OK ($HOME/.coordinator-claude-settings/machine-local/.claude-klabauter-root)" \
      || echo "engine pointer: FAIL — could not write under $HOME/.coordinator-claude-settings/machine-local"
  else
    echo "engine pointer: SKIPPED — no _engine_stamp, so this clone is not a published build"
  fi
fi


echo "UNVERIFIED: whether plugin-declared hooks fire in this session. Two probes and a results"
echo "  table: coordinator-claude/coordinator/templates/cloud-env/verify-in-session.md"
echo "  Until a row there is filled, treat cloud hook coverage as unknown, not present."
echo "=== setup complete ==="

}

main 2>&1 | tee -a "$LOG"
echo "full log: $LOG"
exit 0
