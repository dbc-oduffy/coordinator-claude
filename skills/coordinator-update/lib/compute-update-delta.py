#!/usr/bin/env python3
"""coordinator-update-delta — install-currency delta computer (OSS-only).

Purpose: compute the install-currency delta between the user's installed
coordinator plugin and the latest published version, by wrapping the shipped
check-install-divergence.py three-way classifier.

Spec backlink: docs/plans/2026-05-30-oss-coordinator-update-skill.md § Chunk 2
Port backlink: docs/plans/2026-07-16-bash-clean-slate-residual-migration.md
Rename backlink: coordinator/dist/oss-only-skills/coordinator-update/lib/compute-update-delta.sh
  was already a bash-to-native-Python trampoline (see PORT-SHAPE NOTE below);
  this .sh -> .py rename (de-bash sh-suffix cleanup) carries zero logic
  change, only the file extension + callers.

PORT-SHAPE NOTE (deliberate deviation from the standard BIG_PORT template):
This script is authored under coordinator/dist/oss-only-skills/ and is
injected into the OSS publish tree at publish time (see this skill's own
SKILL.md header). It runs on END-USER machines. Porting it to
`from coordinator_core... import main` (the template-variant-1 shape used
elsewhere in this migration) would still be wrong — it would create a
runtime coordinator_core IMPORT dependency, which this script must never
carry (this trampoline stays a self-contained artifact, not an engine
consumer). This script's two runtime dependencies
(`coordinator/lib/oss-repo-constants.py` and
`coordinator/bin/check-install-divergence.py`) are resolved by FILE PATH
from the engine checkout, never by `import coordinator_core`. The engine
root itself is resolved by delegating, as a subprocess call, to the
resolver script shipped at `coordinator/hooks/scripts/_engine_root.py`
under the install root (passed in via `--install-root`) — this trampoline
cannot `import` that module directly (it ships standalone into the OSS
dist and is not on this script's `sys.path`), so it execs the resolver's
CLI entrypoint and captures its stdout instead of reimplementing its rung
ladder. This is a straight bash-to-native-Python rewrite of the same
self-contained tool, not a migration onto the engine — the only
engine-repo touchpoint is resolved file paths, never a Python import.

Invocation:
  compute-update-delta.py [--install-root <dir>] [--clone <dir>]

Output:
  stdout — single JSON object with fields from the classifier AUGMENTED with:
    update_status   "current" | "behind" | "offline"
    incoming_ref    the resolved tag or HEAD ref checked out
    manual_url      the canonical publish URL (always present)
    recommended_path "none" | "overwrite" | "cherry-pick" | "plan-to-ingest"

Exit codes (byte-exact with main()'s actual returns — verify on any edit):
  0   current (no incoming delta)
  3   behind (delta present)
  4   CLI-usage / setup error (bad flag, invalid --clone, classifier
      missing, classifier rejected our arguments, classifier produced no/
      unparseable JSON) — a business/setup failure, distinguishable from...
  5   ...offline/transport failure (network unreachable — git clone/fetch/
      checkout against the publish repo failed). Dedicated code, does NOT
      collide with 4 (setup) or 0/3 (business outcome) — porter-brief
      addendum § 3b: transport failure must never be misclassified as a
      business state by a caller.

Negative-spec:
  - NEVER reports update_status "current" if the network was unreachable —
    that would be a false "you're up to date".
  - --source passed to the classifier is the publish-repo clone ROOT, NOT a
    plugins/ subdir. The publish repo mirrors coordinator/ directly at its
    root (publish-targets.portable dest_subdir = empty = repo root), so git
    ls-files already emits coordinator/... relpaths that align with --live's
    layout. The former hardcoded-plugins-subdir assumption matched the
    meta-repo's internal nesting but does not exist in the OSS publish repo
    — it caused exit 4 on every real install. Verified against
    check-install-divergence.py:124-184.
  - marketplace.json is installer-rewritten and always diverges from source
    — excluded from consumer_modified advisory set.
  - Faithful-oracle note: the bash oracle resolved a `python3||python||py`
    interpreter separately for the classifier subprocess and for offline-JSON
    construction (via spawn-hidden.sh, a Windows-console-flash-suppressing
    bash launcher). This Python port needs neither: we ARE the resolved
    interpreter already (sys.executable is authoritative for the classifier
    subprocess), and offline JSON is built as a native dict/json.dumps call
    with zero subprocess spawn — spawn-hidden.sh's console-flash concern
    doesn't arise because no console-subsystem child is spawned for that
    step at all. Windows console-flash for the git/classifier subprocess
    calls we DO make is handled natively via subprocess.CREATE_NO_WINDOW
    (porter-brief addendum § 4), which is strictly better than the bash
    oracle's launcher-based approximation (see spawn-hidden.sh's own
    documented mechanism limits).
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path

# ---------------------------------------------------------------------------
# Windows console-flash suppression (porter-brief addendum § 4): apply
# CREATE_NO_WINDOW consistently to every subprocess.run we make. 0 (no-op) on
# non-Windows.
# ---------------------------------------------------------------------------
_CREATIONFLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Subprocess timeouts (porter-brief addendum § 2 — every subprocess.run over
# non-fully-trusted / network-touching input MUST pass timeout=). Network ops
# get a generous ceiling; local/classifier ops get a shorter one.
_NETWORK_TIMEOUT_SECS = 120
_LOCAL_TIMEOUT_SECS = 60

# The marketplace.json path (relative, POSIX) that the coordinator installer always rewrites.
MARKETPLACE_JSON_PATH = "coordinator/.claude-plugin/marketplace.json"


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """subprocess.run wrapper: enforces timeout, stdin=DEVNULL, and
    CREATE_NO_WINDOW on every call site — the single choke point so no call
    site can forget them (porter-brief addendum §§ 2, 4)."""
    kwargs.setdefault("timeout", _LOCAL_TIMEOUT_SECS)
    kwargs.setdefault("stdin", subprocess.DEVNULL)
    kwargs.setdefault("creationflags", _CREATIONFLAGS)
    return subprocess.run(cmd, **kwargs)


# ---------------------------------------------------------------------------
# Engine-root resolution — delegated, not reimplemented (see PORT-SHAPE NOTE
# above). The engine root is resolved by execing the resolver script shipped
# at coordinator/hooks/scripts/_engine_root.py under the install root and
# capturing its stdout; this file carries no rung ladder of its own.
# ---------------------------------------------------------------------------


def _resolve_engine_root(install_root: str) -> str | None:
    """Resolve the coordinator engine root by delegating to the shipped
    resolver script's CLI entrypoint, or return None on any failure (never
    raises — the caller is responsible for the fail-loud remediation)."""
    resolver = os.path.join(install_root, "coordinator", "hooks", "scripts", "_engine_root.py")
    if not os.path.isfile(resolver):
        return None
    try:
        proc = _run(
            [sys.executable, resolver],
            capture_output=True,
            text=True,
            timeout=_LOCAL_TIMEOUT_SECS,
        )
    except subprocess.TimeoutExpired:
        return None
    if proc.returncode != 0:
        return None
    out = proc.stdout.strip()
    if out and os.path.isdir(out):
        return out
    return None


_ENGINE_ROOT_REMEDIATION = (
    "Could not resolve the coordinator engine root via the shipped resolver "
    "script (coordinator/hooks/scripts/_engine_root.py under your install "
    "root). Consult your coordinator install's engine-setup documentation "
    "for how to register the engine root, then retry."
)


def _load_oss_constants(constants_path: str) -> str:
    """Return COORDINATOR_PUBLISH_URL by executing oss-repo-constants.py
    (marker-walk resolved) via importlib file-path loading and reading its
    module-level constant (this file is trusted first-party constants, not
    external input)."""
    spec = importlib.util.spec_from_file_location("oss_repo_constants", constants_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load module spec for {constants_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    url = getattr(module, "COORDINATOR_PUBLISH_URL", None)
    if url is not None:
        return url
    # Fall back to direct construction if the module's shape ever changes but
    # owner/repo are still present (defensive — matches the file's own single
    # documented construction pattern).
    owner = getattr(module, "COORDINATOR_PUBLISH_OWNER", None)
    repo = getattr(module, "COORDINATOR_PUBLISH_REPO", None)
    if owner is not None and repo is not None:
        return f"https://github.com/{owner}/{repo}.git"
    raise RuntimeError(f"could not parse COORDINATOR_PUBLISH_URL from {constants_path}")


def _emit_offline(reason: str, manual_url: str) -> int:
    """Emit an offline JSON payload and return exit code 5 (non-zero, ≠3 →
    offline). Never a subprocess — see negative-spec note above."""
    payload = {
        "update_status": "offline",
        "incoming_ref": None,
        "manual_url": manual_url,
        "recommended_path": "none",
        "baseline_status": "offline — could not reach update source",
        "counts": {"unchanged": 0, "forward_safe": 0, "consumer_modified": 0, "consumer_added": 0},
        "consumer_modified": [],
        "consumer_added": [],
        "_offline_reason": reason,
    }
    print(json.dumps(payload, indent=2))
    return 5


def main(argv: list[str]) -> int:
    # -----------------------------------------------------------------
    # Argument parsing
    # -----------------------------------------------------------------
    # Path.home() (not os.path.expanduser) -- fails loud with RuntimeError,
    # not a silent literal "~", when every home rung is unset. This is an
    # install-time CLI entrypoint (not a never-block hook), so an uncaught
    # RuntimeError here is the correct, fail-loud behaviour: --install-root
    # is always available as an explicit override below.
    install_root = os.path.join(str(Path.home()), ".claude", "plugins", "coordinator-claude")
    clone_dir = ""

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--install-root":
            if i + 1 >= len(argv):
                print("ERROR: --install-root requires a value", file=sys.stderr)
                return 4
            install_root = argv[i + 1]
            i += 2
        elif arg == "--clone":
            if i + 1 >= len(argv):
                print("ERROR: --clone requires a value", file=sys.stderr)
                return 4
            clone_dir = argv[i + 1]
            i += 2
        else:
            print(f"ERROR: unknown argument: {arg}", file=sys.stderr)
            return 4

    # -----------------------------------------------------------------
    # Resolve the engine root (delegated to the shipped resolver script —
    # see _resolve_engine_root above), then this script's two
    # engine-resident dependencies (oss-repo-constants.py,
    # check-install-divergence.py) by file path from it — must succeed
    # before we can even build an offline payload (manual_url is required
    # in every JSON path).
    # -----------------------------------------------------------------
    engine_root = _resolve_engine_root(install_root)
    if not engine_root:
        print(f"ERROR: could not resolve the coordinator engine root.\n{_ENGINE_ROOT_REMEDIATION}", file=sys.stderr)
        return 4

    constants_path = os.path.join(engine_root, "coordinator", "lib", "oss-repo-constants.py")
    if not os.path.isfile(constants_path):
        print(
            f"ERROR: resolved the coordinator engine root at {engine_root} but "
            f"coordinator/lib/oss-repo-constants.py is missing there — is this "
            f"checkout stale or the wrong repo?",
            file=sys.stderr,
        )
        return 4

    try:
        canonical_publish_url = _load_oss_constants(constants_path)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 4

    own_temp = ""

    def _cleanup() -> None:
        if own_temp:
            shutil.rmtree(own_temp, ignore_errors=True)

    try:
        # -------------------------------------------------------------
        # Step 1: Locate or clone the publish repo
        # -------------------------------------------------------------
        if clone_dir:
            if not os.path.isdir(os.path.join(clone_dir, ".git")):
                print(
                    f"ERROR: --clone argument '{clone_dir}' is not a valid git repository (no .git dir)",
                    file=sys.stderr,
                )
                return 4
            repo_dir = clone_dir
        else:
            own_temp = tempfile.mkdtemp()
            clone_target = os.path.join(own_temp, "clone")
            # Review-equivalent (P2, from bash oracle): full clone (no
            # --depth) — the baseline SHA from version.txt must be reachable
            # for git ls-tree; a shallow clone would omit it.
            try:
                proc = _run(
                    ["git", "clone", "--quiet", canonical_publish_url, clone_target],
                    capture_output=True,
                    timeout=_NETWORK_TIMEOUT_SECS,
                )
            except subprocess.TimeoutExpired:
                return _emit_offline(
                    f"git clone timed out after {_NETWORK_TIMEOUT_SECS}s — network unreachable or repo not found at {canonical_publish_url}",
                    canonical_publish_url,
                )
            if proc.returncode != 0:
                return _emit_offline(
                    f"git clone failed — network unreachable or repo not found at {canonical_publish_url}",
                    canonical_publish_url,
                )
            repo_dir = clone_target

        # -------------------------------------------------------------
        # Step 2: Fetch + resolve the incoming ref
        # -------------------------------------------------------------
        try:
            fetch_proc = _run(
                ["git", "-C", repo_dir, "fetch", "--tags", "--quiet"],
                capture_output=True,
                timeout=_NETWORK_TIMEOUT_SECS,
            )
            fetch_ok = fetch_proc.returncode == 0
        except subprocess.TimeoutExpired:
            fetch_ok = False

        if not fetch_ok:
            if own_temp:
                return _emit_offline("git fetch --tags failed — network unreachable", canonical_publish_url)
            # caller-provided clone: proceed with whatever is currently checked out.

        incoming_ref = ""
        try:
            describe_proc = _run(
                ["git", "-C", repo_dir, "describe", "--tags", "--abbrev=0"],
                capture_output=True,
                text=True,
            )
            if describe_proc.returncode == 0:
                incoming_ref = describe_proc.stdout.strip()
        except subprocess.TimeoutExpired:
            pass
        if not incoming_ref:
            incoming_ref = "origin/main"

        try:
            checkout_proc = _run(
                ["git", "-C", repo_dir, "checkout", "--quiet", incoming_ref],
                capture_output=True,
            )
            checkout_ok = checkout_proc.returncode == 0
        except subprocess.TimeoutExpired:
            checkout_ok = False

        if not checkout_ok:
            if own_temp:
                return _emit_offline(
                    f"checkout {incoming_ref} failed — ref missing or corrupt in temp clone",
                    canonical_publish_url,
                )
            print(
                f"WARNING: checkout of ref '{incoming_ref}' failed in caller-provided clone; proceeding on current HEAD",
                file=sys.stderr,
            )

        # -------------------------------------------------------------
        # Step 3: Baseline reachability guard
        # The classifier reads version.txt from --live to get the baseline
        # SHA, then runs git ls-tree <baseline_sha> inside the source clone.
        # A shallow clone may omit old commits. We cloned without --depth so
        # this should be fine; but if version.txt points to a commit not
        # reachable in the clone (e.g. force-pushed) the classifier degrades
        # gracefully to baseline-free two-way (exit 2) — surfaced honestly
        # via baseline_status. No hard-fail here.
        # -------------------------------------------------------------

        # -------------------------------------------------------------
        # Step 4: Locate the classifier (resolved from the engine root, not
        # install_root — check-install-divergence.py is never shipped inside
        # the plugin install tree).
        # -------------------------------------------------------------
        classifier = os.path.join(engine_root, "coordinator", "bin", "check-install-divergence.py")
        if not os.path.isfile(classifier):
            print(f"ERROR: classifier not found at expected path: {classifier}", file=sys.stderr)
            print(
                f"       Resolved coordinator engine root: {engine_root} — is it stale or the wrong repo?",
                file=sys.stderr,
            )
            return 4

        # -------------------------------------------------------------
        # Step 5: Run the classifier
        # --source is the publish-repo clone ROOT (repo_dir itself), NOT a
        # plugins/ subdir — see module-level negative-spec.
        # -------------------------------------------------------------
        source_dir = repo_dir

        try:
            classifier_proc = _run(
                [sys.executable, classifier, "--source", source_dir, "--live", install_root, "--format", "json"],
                capture_output=True,
                text=True,
                timeout=_LOCAL_TIMEOUT_SECS,
            )
            classifier_json = classifier_proc.stdout
            classifier_exit = classifier_proc.returncode
        except subprocess.TimeoutExpired:
            print("ERROR: classifier timed out", file=sys.stderr)
            return 4

        # Exit 1 = invalid CLI input (should not happen with our paths).
        # Exit 2 = no baseline, two-way clean.
        # Exit 3 = divergence detected (consumer-modified or consumer-added).
        # Any other non-zero exit is an unexpected classifier error.
        if classifier_exit == 1:
            print("ERROR: classifier rejected CLI arguments (bad paths?)", file=sys.stderr)
            return 4
        if classifier_exit not in (0, 2, 3):
            print(f"ERROR: classifier exited with unexpected code: {classifier_exit}", file=sys.stderr)
            return 4

        if not classifier_json:
            print("ERROR: classifier produced no JSON output", file=sys.stderr)
            return 4

        # -------------------------------------------------------------
        # Step 6 + 7: Apply marketplace.json exclusion and compute
        # recommended_path. Augment the classifier JSON with wrapper fields
        # and emit.
        # -------------------------------------------------------------
        try:
            data = json.loads(classifier_json)
        except json.JSONDecodeError as exc:
            print(f"ERROR: could not parse classifier JSON: {exc}", file=sys.stderr)
            return 4

        # --- marketplace.json exclusion -----------------------------------
        # the coordinator installer always rewrites this file, so it always
        # shows up as consumer_modified — it is NOT a user customisation.
        original_modified = data.get("consumer_modified", [])
        filtered_modified = [e for e in original_modified if e.get("path") != MARKETPLACE_JSON_PATH]
        excluded_count = len(original_modified) - len(filtered_modified)
        data["consumer_modified"] = filtered_modified
        data["counts"]["consumer_modified"] = data["counts"].get("consumer_modified", 0) - excluded_count

        # --- recommended_path computation (post-exclusion counts) ---------
        cm = data["counts"].get("consumer_modified", 0)
        fs = data["counts"].get("forward_safe", 0)

        # Review-equivalent (P2, from bash oracle): drop `and ca == 0` — a
        # consumer with only locally-added files and no incoming forward
        # changes (cm==0, fs==0, ca>0) has latest upstream and should report
        # "current"/"none", not fall through to "plan-to-ingest".
        if cm == 0 and fs == 0:
            recommended_path = "none"
            update_status = "current"
        elif cm == 0 and fs > 0:
            recommended_path = "overwrite"
            update_status = "behind"
        elif cm > 0 and fs > 0:
            recommended_path = "cherry-pick"
            update_status = "behind"
        else:
            recommended_path = "plan-to-ingest"
            update_status = "behind"

        # --- Augment with wrapper fields -----------------------------------
        data["update_status"] = update_status
        data["incoming_ref"] = incoming_ref
        data["manual_url"] = canonical_publish_url
        data["recommended_path"] = recommended_path

        print(json.dumps(data, indent=2))

        # 0 = current (nothing incoming), 3 = behind (delta present)
        return 0 if update_status == "current" else 3
    finally:
        _cleanup()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
