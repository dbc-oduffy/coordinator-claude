#!/usr/bin/env bash
# Cloud-environment setup script. Paste into "Setup script" at claude.ai/code.
#
# Lands coordinator-claude and its engine on a cloud VM before Claude Code launches, via a
# `directory` marketplace source in user settings -- nothing is uploaded, no admin approval
# surface is involved, no `claude` binary is needed at setup time.
#

# REPO-AGNOSTIC BY DESIGN, AND THAT IS THE POINT. This is pasted into a cloud ENVIRONMENT, which is
# the OPERATOR's surface at claude.ai/code — not a file in any repo and not a step any repo's own
# installer has to adopt. Everything it needs it clones itself, so the same paste works for a
# session on any repo.
#

# ONE EXCEPTION, LIVE TODAY: doctrine (phase 3b)'s third candidate is a published copy that, as of
# this writing, may not yet be in the plugin mirror. Status lives in README.md § Known gap, beside
# this file -- don't restate it here, it is truth-expiring.
#

# PASTE THIS ALONGSIDE — the "Environment variables" box, which reaches the SESSION but NOT this
# script (which is why every value below is also hardcoded here):
#

#     COORDINATOR_SETTINGS_HOME=/root/.coordinator-claude-settings
#
# NOT COORDINATOR_ENGINE_ROOT. It is a live-tree override, so a session-wide value pins every
# session to the manual test-and-execute rung rather than the published engine. This script writes
# the published pointer file instead.
#
# It always exits 0 -- a non-zero exit fails the whole session, so every finding is a FAIL line in
# the setup checklist, never a boot abort. A missing review payload is one such FAIL line; the
# execute path fails closed on it (emit-dispatch-workflow refuses to emit with no review stage).
# SCOPE and the verification record: README.md beside this file.

set -u

REPO_MARKETPLACE=https://github.com/dbc-oduffy/coordinator-claude
REPO_ENGINE=https://github.com/dbc-oduffy/claude-klabauter
LOG="$HOME/.coordinator-cloud-setup.log"

# Everything runs inside main() so the whole run can be tee'd to a file -- the platform does not
# persist this script's stdout anywhere else the session can reach, so the log file is the only
# durable channel for "which route did a phase take?" after the fact.
main() {

echo "=== phase 0: probe (facts unestablishable from a developer host) ==="
echo "whoami=$(whoami)  HOME=$HOME  PWD=$PWD"

# /opt is the documented seed location; $HOME is the fallback. Which one we get changes the paths
# the env-var block above must carry, so this is decided first.
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
# question -- an in-session check would not have answered it.

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
# Three routes tried in order of least surprise. --break-system-packages is deliberately NOT one
# of them: the engine's own installer refuses that path, and a setup script that took it would
# leave a machine the installer then declines to run on.

DEPS="pydantic psutil jsonschema PyYAML"
if pip3 install --user --quiet $DEPS 2>/dev/null; then
  echo "deps: OK (pip3 --user)"
elif command -v uv >/dev/null 2>&1 && uv pip install --system --quiet $DEPS 2>/dev/null; then
  echo "deps: OK (uv --system)"
else
  echo "deps: FAIL — engine will not import; coordinator loads degraded"
fi

echo "=== phase 3: register the plugin in user settings ==="
# The `directory` source is what sidesteps the hosted surface: Claude Code reads the marketplace
# manifest off local disk at launch and clones nothing. The mirror is FLAT -- its
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

echo "=== phase 3b: global doctrine into the VM's own HOME ==="

# Cloud reads the VM's $HOME/.claude normally -- what does not carry over is the machine you
# launched FROM. That is provenance, not path (tripwire
# A-VM-WRITTEN-HOME-CLAUDE-IS-NOT-YOUR-MACHINES-HOME-CLAUDE), and it is why phase 3 can register a
# plugin here at all. The same write lands global doctrine, which otherwise reaches no cloud
# session: `global-doctrine/` is deliberately absent from the OSS mirror this script clones, so the
# only copy on this VM is the one in the working repo's own clone -- present when the session runs
# on a repo that authors doctrine, absent otherwise. Copy, never mirror-and-prune: $HOME/.claude is
# the operator's, and on a self-hosted runner it may already carry seeded content this must not eat.
# Search order is authoring-copy first, sibling-checkout glob second, published copy third. They are byte-identical when the
# deriver has run, so the order only decides which one a doctrine-authoring repo uses; the
# published copy under the plugin clone is what makes every OTHER repo work, since it rides the
# percolated tree into the OSS mirror this script already clones.


DOCTRINE_SRC=""
for cand in "$PWD/global-doctrine" /workspace/*/global-doctrine \
            "$ROOT/coordinator-claude/templates/global-doctrine"; do
  [ -f "$cand/CLAUDE.md" ] && { DOCTRINE_SRC="$cand"; break; }
done
if [ -n "$DOCTRINE_SRC" ]; then
  mkdir -p "$HOME/.claude/rules"
  # The log line is the only durable verification channel this design has, so a failed copy must
  # not report OK -- check the copy's own exit status before logging.
  if cp "$DOCTRINE_SRC/CLAUDE.md" "$HOME/.claude/CLAUDE.md"; then
    # CLAUDE.md and rules are two independent outcomes, and doctrine-present-with-rules-missing
    # is a real, distinct state a reader needs to see -- no `2>/dev/null`, a copy failure's
    # stderr belongs on disk.
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
  # None of the three candidates was found -- could be a failed clone, or the published-copy
  # candidate's known gap. Loud rather than silent because a skip here looks identical to a
  # working copy, and the session that boots next is the one that pays.
  echo "doctrine: FAIL (no copy found — session runs doctrine-blind; see README.md § Known gap)"
fi

echo "=== phase 4: engine root pointer ==="
# The ordering hole: the machine-local registry's reader belongs to coordinator-claude's INSTALL,
# which has not run and cannot run here. The durable pointer file is the documented cold-box
# substitute and needs no reader at all.

if [ "$HAVE_ENGINE" -eq 0 ]; then
  # `-root`, NOT `-live-root`. Two pointers are read at different rungs and they assert different
  # things: `.claude-klabauter-root` is the PUBLISHED build (admitted only with a tracked
  # coordinator_core/_engine_stamp, which a fresh clone of the mirror carries), `-live-root` is a
  # live working tree (isdir alone). We clone the published mirror, so this is the published arm.
  # The wrong name does not fail loudly — the published arm falls through, the live arm accepts on
  # isdir, and the box resolves by asserting a published mirror is a live tree. That is DR-326's
  # manual test-and-execute carve-out, taken silently where nobody can attach a debugger.

  mkdir -p "$HOME/.coordinator-claude-settings/machine-local"
  echo "$ROOT/claude-klabauter" > "$HOME/.coordinator-claude-settings/machine-local/.claude-klabauter-root"
  echo "engine pointer: OK -> $ROOT/claude-klabauter"
else
  echo "engine pointer: SKIPPED (no engine clone)"
fi

echo "=== phase 4b: run the engine installer ==="

# The point of doing this HERE rather than asking the session to run /coordinator:install: a
# newborn cloud EM should inherit a working machine, not a chore. Both clones exist by now and the
# image's python3 carries no EXTERNALLY-MANAGED marker, so the installer's exit-96 refusal cannot
# fire — the two things that made this un-runnable at provision time are both gone.
# Best-effort by construction: a failure here degrades the session to plugin-only (skills load,
# the bin/ CLI surface does not), which is exactly where this script stood before. It must never
# take the session down with it, so the exit code is reported and swallowed.

if [ "$HAVE_ENGINE" -eq 0 ]; then
  # `--i-am-agent` plus a closed stdin: an ephemeral VM has nothing to negotiate, so this lands
  # the DEFAULT installation and takes every default silently. `< /dev/null` matters: one offer
  # still fires under --i-am-agent and relies on stdin being closed to decline it.
  ( cd "$ROOT/claude-klabauter" && COORDINATOR_ENGINE_ROOT="$ROOT/claude-klabauter" \
      COORDINATOR_SETTINGS_HOME="$HOME/.coordinator-claude-settings" \
      python3 scripts/setup.py --i-am-agent < /dev/null ) 2>&1 | tail -25
  rc=${PIPESTATUS[0]}
  # Named rather than numeric: 90 is a missing hard dependency, 95 an unresolvable repo identity,
  # 96 the interpreter refusal that should now be impossible here -- a 96 means the image changed.
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
  COORDINATOR_ENGINE_ROOT="$ROOT/claude-klabauter" python3 -c \
    "import sys; sys.path.insert(0, '$ROOT/claude-klabauter'); import coordinator_core; print('engine import: OK')" \
    2>&1 | tail -1
  
  
  python3 -c "import pydantic, psutil, jsonschema, yaml; print('deps import: OK')" 2>&1 | tail -1
fi
# The review payload, located the way the engine locates it (content_root_for: `<clone>/coordinator`
# for a source-shaped tree, the clone itself for the flat mirror).
if [ "$HAVE_PLUGIN" -eq 0 ]; then
  python3 - "$ROOT/claude-klabauter" "$ROOT/coordinator-claude" <<'PYCHECK' 2>&1
import sys
sys.path.insert(0, sys.argv[1])
try:
    from coordinator_core._content_root_primitive import content_root_for
except Exception as exc:
    print(f"review payload: FAIL -- engine unimportable, cannot resolve content root ({exc})")
    sys.exit(1)
root = content_root_for(sys.argv[2])
if root is None:
    print(f"review payload: FAIL -- {sys.argv[2]} is not a coordinator content root")
    sys.exit(1)
missing = [p for p in (root / "contract" / "review-roster-fragment.json", root / "bin")
           if not p.exists()]
if missing:
    print("review payload: FAIL -- missing " + ", ".join(map(str, missing))
          + " (execute workflows would compose no review stage)")
    sys.exit(1)
print(f"review payload: OK ({root})")
PYCHECK
else
  echo "review payload: FAIL -- no plugin clone"
fi
# The PUBLISHED-engine pointer, written here so the env block never has to carry an override to
# do this job. The published arm admits a root only if <root>/coordinator_core/_engine_stamp
# exists, and the stamp is tracked, so a fresh clone of the mirror satisfies it. The name is
# load-bearing: `-live-root` would be accepted on isdir alone and resolve the mirror AS a live
# working tree. See contract § Why the pointer name is `-root` and not `-live-root`.

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
# Everything above proves files are on disk, not that Claude Code READS them -- this script
# finishes before Claude Code launches, so hook firing is unobservable from here. The session
# that boots next is the only thing that can settle it, and cloud sessions are unattended ones.
echo "UNVERIFIED: whether plugin-declared hooks fire in this session. Two probes and a results"
echo "  table: coordinator-claude/coordinator/templates/cloud-env/verify-in-session.md"
echo "  Until a row there is filled, treat cloud hook coverage as unknown, not present."
echo "=== setup complete ==="

}

main 2>&1 | tee -a "$LOG"
echo "full log: $LOG"
exit 0
