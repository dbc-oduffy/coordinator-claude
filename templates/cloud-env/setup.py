"""Cloud-environment setup script: lands coordinator-claude and its engine on a cloud VM before
Claude Code launches, via a `directory` marketplace source in user settings. Nothing is uploaded,
no admin approval surface is involved, no `claude` binary is needed at setup time.

The "Setup script" field at claude.ai/code takes bash, so the paste is a three-line fetch-and-run
and this file is what it runs (stdlib only; the image's `python3` is the only prerequisite):

    set -u
    curl -fsSL -o /root/setup.py https://raw.githubusercontent.com/dbc-oduffy/coordinator-claude/HEAD/templates/cloud-env/setup.py
    python3 /root/setup.py
    exit 0

Repo-agnostic by design: the paste lives in a cloud ENVIRONMENT (the operator's surface), not in any
repo, so everything this needs it clones itself and the same paste works for a session on any repo.
Paste alongside it, in the "Environment variables" box (which reaches the SESSION, not this
script):

    COORDINATOR_SETTINGS_HOME=/root/.coordinator-claude-settings

Never COORDINATOR_ENGINE_ROOT: it is a live-tree override, so a session-wide value pins every
session to the manual test-and-execute rung instead of the published engine. This script writes the
published pointer file instead.

Always exits 0 -- a non-zero exit fails the whole session, so every finding is a FAIL line in the
setup checklist, never a boot abort. SCOPE and the verification record: README.md beside this file.
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_MARKETPLACE = "https://github.com/dbc-oduffy/coordinator-claude"
REPO_ENGINE = "https://github.com/dbc-oduffy/claude-klabauter"
HOME = Path.home()
LOG = HOME / ".coordinator-cloud-setup.log"
DEPS = ["pydantic", "psutil", "jsonschema", "PyYAML"]
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# The platform persists this script's stdout nowhere a session can reach, so the log file is the
# only durable channel for "which route did a phase take?" after the fact.
class _Tee:
    def __init__(self, *streams):
        self._streams = streams

    def write(self, text):
        for stream in self._streams:
            stream.write(text)
            stream.flush()
        return len(text)

    def flush(self):
        for stream in self._streams:
            stream.flush()


def _run(argv, *, cwd=None, env=None):
    """Run `argv` with stdin closed; returns (returncode, combined output). A spawn failure is
    returned as rc 127 rather than raised -- every phase here is best-effort."""
    try:
        proc = subprocess.run(
            argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
            encoding="utf-8", errors="replace", creationflags=_NO_WINDOW,
        )
    except OSError as exc:
        return 127, str(exc)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _tail(text, count):
    return "\n".join(text.rstrip("\n").splitlines()[-count:])


def _clone(url, dest):
    if (dest / ".git").is_dir():
        print(f"clone {dest}: present already")
        return True
    rc, _ = _run(["git", "clone", "--depth", "1", url, str(dest)])
    if rc == 0:
        _, short = _run(["git", "-C", str(dest), "rev-parse", "--short", "HEAD"])
        print(f"clone {dest}: OK ({short.strip()})")
        return True
    print(f"clone {dest}: FAIL — {url} unreachable under this network policy")
    return False


def _pick_root():
    # /opt is the documented seed location; $HOME is the fallback. Which one we get changes the
    # paths the env-var block must carry, so this is decided first.
    try:
        Path("/opt/coordinator").mkdir(parents=True, exist_ok=True)
        return Path("/opt/coordinator")
    except OSError:
        root = HOME / "coordinator"
        root.mkdir(parents=True, exist_ok=True)
        print("/opt not writable — falling back to $HOME")
        return root


def _phase0_probe():
    print("=== phase 0: probe (facts unestablishable from a developer host) ===")
    import getpass
    print(f"whoami={getpass.getuser()}  HOME={HOME}  PWD={os.getcwd()}")
    root = _pick_root()
    print(f"ROOT={root}")
    for tool in ("claude", "python3", "pip3", "git", "jq", "uv"):
        found = shutil.which(tool)
        print(f"tool {tool}: {found}" if found else f"tool {tool}: ABSENT")
    print(sys.version.splitlines()[0])
    # PEP 668: Ubuntu 24.04 ships EXTERNALLY-MANAGED in the system interpreter, and the engine's
    # own installer refuses such an interpreter outright (exit 96, no fallback).
    import sysconfig
    marker = Path(sysconfig.get_paths()["stdlib"]) / "EXTERNALLY-MANAGED"
    print(f"pep668: EXTERNALLY-MANAGED at {marker}" if marker.exists() else "pep668: unmanaged")
    if shutil.which("check-tools"):
        _, out = _run(["check-tools"])
        print(_tail(out, 30))
    return root


def _phase2_deps():
    print("=== phase 2: engine runtime deps ===")
    # --break-system-packages is deliberately NOT a route: the engine's own installer refuses that
    # path, and a setup script that took it would leave a machine the installer then declines.
    if shutil.which("pip3") and _run(["pip3", "install", "--user", "--quiet", *DEPS])[0] == 0:
        print("deps: OK (pip3 --user)")
    elif shutil.which("uv") and _run(["uv", "pip", "install", "--system", "--quiet", *DEPS])[0] == 0:
        print("deps: OK (uv --system)")
    else:
        print("deps: FAIL — engine will not import; coordinator loads degraded")


def _phase3_register(root, have_plugin):
    print("=== phase 3: register the plugin in user settings ===")
    # The `directory` source sidesteps the hosted surface: Claude Code reads the marketplace
    # manifest off local disk at launch and clones nothing. The mirror is FLAT -- its
    # .claude-plugin/marketplace.json sits at the repo root, unlike the doctrine source tree where the
    # manifest is one level down under coordinator/.
    (HOME / ".claude").mkdir(parents=True, exist_ok=True)
    path = HOME / ".claude" / "settings.json"
    if not have_plugin:
        print("settings: SKIPPED (no plugin clone)")
        return
    # Merged, never clobbered: Claude Code may have written this file already.
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        settings = {}
    try:
        settings.setdefault("extraKnownMarketplaces", {})["coordinator-claude"] = {
            "source": {"source": "directory", "path": str(root / "coordinator-claude")}
        }
        settings.setdefault("enabledPlugins", {})["coordinator@coordinator-claude"] = True
        path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        print("settings: OK ->", path)
    except (OSError, AttributeError, TypeError):
        print("settings: FAIL")


def _phase3b_doctrine(root):
    print("=== phase 3b: global doctrine into the VM's own HOME ===")
    # Copy, never mirror-and-prune: $HOME/.claude is the operator's and may carry seeded content.
    # Search order: authoring copy, sibling-checkout glob, then the published copy under the
    # plugin clone (which is what makes every OTHER repo work).
    candidates = [Path.cwd() / "global-doctrine", *map(Path, sorted(glob.glob("/workspace/*/global-doctrine"))),
                  root / "coordinator-claude" / "templates" / "global-doctrine"]
    source = next((c for c in candidates if (c / "CLAUDE.md").is_file()), None)
    if source is None:
        # Loud rather than silent: a skip here looks identical to a working copy.
        print("doctrine: FAIL (no copy found — session runs doctrine-blind; see README.md § Known gap)")
        return
    target = HOME / ".claude"
    try:
        (target / "rules").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / "CLAUDE.md", target / "CLAUDE.md")
    except OSError as exc:
        print(f"doctrine: FAIL (copy error: {exc}) -> $HOME/.claude/CLAUDE.md (from {source})")
        return
    # CLAUDE.md and rules are independent outcomes; doctrine-present-with-rules-missing is a real
    # state a reader needs to see.
    if (source / "rules").is_dir():
        try:
            for rule in (source / "rules").glob("*.md"):
                shutil.copyfile(rule, target / "rules" / rule.name)
            rules_status = "rules: OK"
        except OSError:
            rules_status = "rules: FAIL (copy error)"
    else:
        rules_status = f"rules: none present at {source / 'rules'}"
    print(f"doctrine: OK -> $HOME/.claude/CLAUDE.md (from {source}); {rules_status}")


def _write_engine_pointer(engine):
    # `.claude-klabauter-root`, NOT `-live-root`: the first is the PUBLISHED-build rung, the
    # second a live working tree accepted on isdir alone. We clone the published mirror; the wrong
    # name resolves it AS a live tree, silently taking the manual test-and-execute carve-out.
    pointer = HOME / ".coordinator-claude-settings" / "machine-local" / ".claude-klabauter-root"
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text(f"{engine}\n", encoding="utf-8")
    return pointer


def _phase4_pointer(engine, have_engine):
    print("=== phase 4: engine root pointer ===")
    if not have_engine:
        print("engine pointer: SKIPPED (no engine clone)")
        return
    # The machine-local registry's reader belongs to an INSTALL that has not run and cannot run
    # here; the durable pointer file is the documented cold-box substitute.
    _write_engine_pointer(engine)
    print(f"engine pointer: OK -> {engine}")


def _phase4b_install(engine, have_engine):
    print("=== phase 4b: run the engine installer ===")
    if not have_engine:
        print("engine install: SKIPPED (no engine clone)")
        return
    # A newborn cloud EM should inherit a working machine, not a chore. Best-effort by
    # construction: a failure degrades the session to plugin-only and must never take it down.
    # `--i-am-agent` plus a closed stdin takes every default silently; one offer still fires under
    # --i-am-agent and relies on stdin being closed to decline it.
    env = dict(os.environ, COORDINATOR_ENGINE_ROOT=str(engine),
               COORDINATOR_SETTINGS_HOME=str(HOME / ".coordinator-claude-settings"))
    rc, out = _run([sys.executable, "scripts/setup.py", "--i-am-agent"], cwd=engine, env=env)
    print(_tail(out, 25))
    named = {
        0: "engine install: OK",
        90: "engine install: FAIL rc=90 (hard dep missing)",
        95: "engine install: FAIL rc=95 (repo identity unresolved)",
        96: "engine install: FAIL rc=96 (interpreter refused — the image now ships a PEP-668 marker)",
    }
    print(named.get(rc, f"engine install: FAIL rc={rc}"))


_REVIEW_PAYLOAD_CHECK = '''
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
'''


def _phase5_verify(root, have_plugin, have_engine):
    print("=== phase 5: verify what the session will actually see ===")
    plugin, engine = root / "coordinator-claude", root / "claude-klabauter"
    if have_plugin:
        ok = (plugin / ".claude-plugin" / "marketplace.json").is_file()
        print("manifest: OK" if ok else "manifest: FAIL — wrong directory level for the source path")
    if have_engine:
        env = dict(os.environ, COORDINATOR_ENGINE_ROOT=str(engine))
        _, out = _run([sys.executable, "-c",
                       "import sys; sys.path.insert(0, sys.argv[1]); import coordinator_core; "
                       "print('engine import: OK')", str(engine)], env=env)
        print(_tail(out, 1))
        _, out = _run([sys.executable, "-c",
                       "import pydantic, psutil, jsonschema, yaml; print('deps import: OK')"])
        print(_tail(out, 1))
    if have_plugin:
        _, out = _run([sys.executable, "-c", _REVIEW_PAYLOAD_CHECK, str(engine), str(plugin)])
        print(out.rstrip("\n"))
    else:
        print("review payload: FAIL -- no plugin clone")
    # The PUBLISHED-engine pointer, so the env block never has to carry an override. The published
    # arm admits a root only if <root>/coordinator_core/_engine_stamp exists; the stamp is tracked,
    # so a fresh clone of the mirror satisfies it.
    if have_engine:
        if (engine / "coordinator_core" / "_engine_stamp").is_file():
            try:
                pointer = _write_engine_pointer(engine)
                print(f"engine pointer: OK ({pointer})")
            except OSError:
                print(f"engine pointer: FAIL — could not write under {HOME}/.coordinator-claude-settings/machine-local")
        else:
            print("engine pointer: SKIPPED — no _engine_stamp, so this clone is not a published build")
    # This script finishes before Claude Code launches, so hook firing is unobservable from here.
    print("UNVERIFIED: whether plugin-declared hooks fire in this session. Two probes and a results")
    print("  table: coordinator-claude/coordinator/templates/cloud-env/verify-in-session.md")
    print("  Until a row there is filled, treat cloud hook coverage as unknown, not present.")


def main():
    root = _phase0_probe()
    print("=== phase 1: clone (setup-phase egress, not the session's) ===")
    # Claude Code connects to the agent proxy AFTER this script runs, so reachability here is its
    # own question -- an in-session check would not have answered it.
    have_plugin = _clone(REPO_MARKETPLACE, root / "coordinator-claude")
    have_engine = _clone(REPO_ENGINE, root / "claude-klabauter")
    engine = root / "claude-klabauter"
    _phase2_deps()
    _phase3_register(root, have_plugin)
    _phase3b_doctrine(root)
    _phase4_pointer(engine, have_engine)
    _phase4b_install(engine, have_engine)
    _phase5_verify(root, have_plugin, have_engine)
    print("=== setup complete ===")


if __name__ == "__main__":
    with open(LOG, "a", encoding="utf-8") as log:
        sys.stdout = sys.stderr = _Tee(sys.__stdout__, log)
        try:
            main()
        except Exception as exc:  # a non-zero exit fails the whole session
            print(f"setup: FAIL — unexpected {type(exc).__name__}: {exc}")
        sys.stdout = sys.stderr = sys.__stdout__
    print(f"full log: {LOG}")
    sys.exit(0)
