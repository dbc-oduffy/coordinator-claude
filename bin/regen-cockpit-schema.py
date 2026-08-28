# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""regen-cockpit-schema.py — Regenerate the canonical cockpit-contract schema.

Purpose: thin, discoverable entrypoint that regenerates
coordinator/cockpit-contract/schema/*.json by invoking claude-klabauter's Python
emitter. Claude-klabauter (claude-klabauter) owns the emitter ENGINE
(coordinator_core.contract.cockpit_schema.emit_schema) — this DoE-side
script is only a wrapper that resolves the sibling repo's SOURCE tree,
trampolines the CURRENT interpreter (sys.executable) into it by setting
CLAUDE_KLABAUTER_ROOT and prepending claude_klabauter_root to PYTHONPATH, and spawns the
emitter under it. It does NOT resolve or depend on claude-klabauter's private
virtual environment in any form — per claude-klabauter's cross-repo boundary memo
(2026-07-21), that environment's contents, location, and existence are
Claude-klabauter-internal, may change without notice, and are not a supported
consumption channel for any other repo. The supported contract is:
reach claude-klabauter's SOURCE tree, under an interpreter that satisfies
Claude-klabauter's declared requirements (pydantic>=2, psutil>=5.9). This script
fails loud with remediation when that requirement isn't met rather than
silently leaving the schema stale.

Windows de-bash campaign (Category C — inline `python -m` veneer): this
replaces the former bash forwarder (regen-cockpit-schema.sh, DoE 23d34a4c,
2026-07-19, which shelled out to a claude-klabauter-resident interpreter via
`set -euo pipefail` plumbing). No shell is spawned anywhere in this module —
the emitter is invoked directly via subprocess.run() with an argv list, never
through a shell string.

Spec backlink: DoE-claude:pln-decommission-cockpit-contract--73331e (chunk C2).
Spec backlink: docs/plans/2026-07-19-debash-coordinator-windows.md (Wave 1, Category C).

Usage:
    python coordinator/bin/regen-cockpit-schema.py
    python coordinator/bin/regen-cockpit-schema.py --advance-ref

Negative-spec: does NOT invoke bash, sh, or any shell. Does NOT resolve,
reference, or spawn any interpreter from a sibling repo's private virtual
environment — that environment is not a supported consumption channel
(2026-07-21 cross-repo boundary; this repo's own retired-venv ruling,
2026-07-21, applies equally). Does NOT fall back to a DoE-resident emitter
— a source-trampoline into claude-klabauter's SOURCE tree, run under an interpreter
satisfying claude-klabauter's declared requirements, is a hard prerequisite; there is
no legacy path to strangle back to (Category C never had a bash-fallback
leg, unlike the Category-B strangler facades). Does NOT, and must NOT ever,
execute `git push` against origin — not now, and not as a "convenience"
added later. Per claude-klabauter's emitter-ownership scope (DR-060), this module
authors and regenerates the schema BYTES; it has no relationship to pushing
a release tag. A push added here would silently hand this script a publish
responsibility it was never scoped to hold. The only guard that ever
enforced this invariant (asserting `git push` never appears in this regen
script) migrated into claude-klabauter's tree with `b644d5a9`; nothing on DoE's side
has watched this seam since, which is precisely why a future reader must
resist the temptation to "just add a push here." DoE asked claude-klabauter to take
on the publish step directly (2026-07-25); claude-klabauter declined on engineering
grounds, and DoE agreed to a push-triggered GitHub Action in its own repo
instead — ratified 2026-07-25, not yet built as of that date (see the
tag-advance section below for the current build status).

Tag-advance re-homing (AC8, docs/plans/2026-07-04-doe-emission-conformance-fixture.md;
coordinator/docs/wiki/emission-conformance-contract.md § Dedicated-Ref Freshness
Protocol): the `cockpit-contract-release` local tag advance used to live in the
now-deleted `gen-emission-conformance.sh` (removed 2026-07-08, commit 454bc0ab,
when conformance ownership moved to claude-klabauter). The advance rode along as
collateral and was never re-homed — this is the ONLY entrypoint that regenerates
the schema, so it is the correct new home. `--advance-ref` is opt-in and NEVER
the default: a bare drift-check run of this script (no flag) must not touch the
tag, or it would spuriously advance the release ref on every no-op invocation
(AC8 violation). The tag is advanced locally only — `git tag -f`, never pushed to
origin — and only when the regen actually changed the schema output. The origin
push is DoE's surface, not claude-klabauter's, and this script deliberately does not own
it and never will (see the module-level Negative-spec above for why staying
push-free is a governance requirement, not a gap). The release ref's publish
mechanism is DoE's `.github/scripts/publish_cockpit_contract.py`, which
publishes BOTH the moving `cockpit-contract-release` ref and the immutable
per-version alias (`cockpit-contract-<CONTRACT_VERSION>`) from DoE's clone to
DoE's origin. As of 2026-08-23 that script exists and has been exercised (4.0.0
published both refs), but the GitHub Action that was meant to trigger it does
not — DoE-claude has `.github/scripts/` and no `.github/workflows/` — so the
publish is an operator-run script, not an automatic one. Verify before relying
on this: the presence of a workflow file under DoE-claude's `.github/workflows/`
is the ground truth, not this docstring's age. Until it is automated, the origin tag can
sit stale relative to the local `git tag -f` advance below, and any reader
pinned to the origin ref — claude-klabauter's own freshness probe
(`coordinator_core/ops/emit/doe_drift.py`) and the default re-vendor path
(`bin/claude-klabauter-revendor-cockpit-contract.py`, which defaults to
`refs/tags/cockpit-contract-release`) — may read an OLD contract version
until DoE's side lands and starts running the Action. Claude-klabauter performs no
cross-repo remote write, here or anywhere else, and this script's no-push
invariant is unconditional regardless of what DoE's own publish mechanism is
or whether it has shipped yet. (This module previously claimed the push
"rides `/merge-to-main`"; that mechanism never existed — DoE's
`/merge-to-main` cuts and pushes `v*` release tags only, and this ref is
untouched by it.)

Two-step tag-advance contract (fixed 2026-07-22 — the tag must point at the
COMMIT that contains the regenerated schema, not the pre-schema HEAD):

    1. Regenerate, then commit the schema:
       python coordinator/bin/regen-cockpit-schema.py
       git add -- coordinator/cockpit-contract/schema/ && git commit -- coordinator/cockpit-contract/schema/
    2. Advance the tag to that commit:
       python coordinator/bin/regen-cockpit-schema.py --advance-ref

`--advance-ref` REFUSES (exit 2) when `coordinator/cockpit-contract/schema/` has
uncommitted changes — advancing the tag over a dirty schema dir would land it on
the commit BEFORE the regenerated schema, so a downstream consumer re-vendoring
from the tag would pick up stale bytes. When the schema dir is clean, the tag is
advanced only if the committed schema at HEAD actually differs from what the tag
currently points at (or the tag doesn't exist yet) — a no-op re-run of
`--advance-ref` over an already-tagged commit leaves the tag untouched.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

_BIN_DIR = os.path.dirname(os.path.abspath(__file__))

def _bootstrap_imports() -> None:
    """Import every non-stdlib dependency this module needs and bind it at
    module scope, called from main() (C6k import-motion: module bodies stay
    inert on both the warm door and the un-bootstrapped settings-home
    forwarder load routes). Order is load-bearing — preserved verbatim from
    the former module-scope sequence.
    """
    global cc_invoke, claude_klabauter_root, _DoeUnresolvable, doe_root
    global no_console_creationflags

    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    import cc_invoke

    cc_invoke.ensure_engine_on_path(__file__)

    from cli_shared import claude_klabauter_root
    from coordinator_registry import _DoeUnresolvable, doe_root
    from coordinator_core.win_portability import no_console_creationflags

_EMITTER_MODULE = "coordinator_core.contract.cockpit_schema.emit_schema"
_RELEASE_TAG = "cockpit-contract-release"
_CONTRACT_SCHEMA_FILENAME = "cockpit-contract.schema.json"


def _resolve_doe_root() -> str:
    """Resolve the DoE repo root via the shared machine-local registry ladder.

    This does NOT derive the root from this script's own location. That was
    correct while this executable lived in DoE-claude (SCRIPT_DIR/../.. IS
    the DoE root there — the old `git rev-parse --show-toplevel` with
    cwd=_BIN_DIR mirrored the retired bash oracle exactly), but this file
    has since migrated to claude-klabauter. Self-location now resolves to the
    claude-klabauter repo root, which has no `coordinator/cockpit-contract/schema/`
    at all — silently composing a nonexistent out_dir for DoE's 30 frozen
    schema files instead of failing loud. This is the sole regeneration
    path DoE's D13/D21 release gate depends on, so a silent wrong-root
    write here is the highest-stakes shape this bug takes anywhere in the
    migration. A future reader must not "restore" __file__/git-toplevel
    resolution to regain oracle parity — that is precisely what broke it.

    Resolution chain: doe_root() (DOE_ROOT env -> REPO_DOE_CLAUDE env ->
    machine-local repos.doe_claude -> raise _DoeUnresolvable). Fails loud
    (sys.exit(2)) on an unresolvable root, keeping this function's existing
    exit-2 contract with callers.
    """
    try:
        root = doe_root()
    except _DoeUnresolvable as exc:
        print(
            f"ERROR: could not resolve the coordinator doctrine repo root ({exc}). "
            "Set repos.doe_claude in the machine-local registry, or set the "
            "DOE_ROOT / REPO_DOE_CLAUDE env var.",
            file=sys.stderr,
        )
        sys.exit(2)
    if not os.path.isdir(root):
        print(f"ERROR: resolved DoE repo root does not exist: {root}", file=sys.stderr)
        sys.exit(2)
    return root


def _build_trampoline_env(mak_root: str) -> dict[str, str]:
    """Build the subprocess env for a source-trampoline spawn into the engine repo.

    Passes os.environ through, sets CLAUDE_KLABAUTER_ROOT, and prepends mak_root to
    PYTHONPATH only if not already present (idempotency fence). Mirrors
    `_build_subprocess_env()` in `coordinator/bin/lib/cc_invoke.py` — this is
    the same sanctioned source-trampoline pattern, not a fresh convention.
    This reaches the engine repo's SOURCE tree only; it never resolves or spawns
    an engine-resident interpreter (see module docstring).

    C11: also sets `COORDINATOR_ENGINE_ROOT` alongside `CLAUDE_KLABAUTER_ROOT` (same
    dual-write rename-window shape `_build_subprocess_env()` now uses), so a
    child reading either name resolves correctly during the rename window.
    """
    env: dict[str, str] = {**os.environ, "CLAUDE_KLABAUTER_ROOT": mak_root, "COORDINATOR_ENGINE_ROOT": mak_root}
    existing_pp = env.get("PYTHONPATH", "")
    _sep = os.pathsep
    if f"{_sep}{mak_root}{_sep}" not in f"{_sep}{existing_pp}{_sep}":
        env["PYTHONPATH"] = f"{mak_root}{_sep}{existing_pp}" if existing_pp else mak_root
    return env


def _schema_dir_dirty(doe_root: str, out_dir: str) -> bool:
    """Return True iff out_dir has an uncommitted working-tree change.

    Scoped to `coordinator/cockpit-contract/schema/` only — unrelated dirty
    files elsewhere in the tree must not affect the refuse-if-dirty gate.
    Uses `git status --porcelain` (covers both modified-tracked and
    untracked-new schema files) rather than `git diff --name-only`
    (tracked-only, would miss a newly-added schema file).

    Used ONLY by the `--advance-ref` refuse-if-dirty guard in `main()` — the
    tag must never advance while the schema dir is dirty, since that would
    land the tag on the commit BEFORE the regenerated schema.
    """
    rel_out_dir = os.path.relpath(out_dir, doe_root)
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--", rel_out_dir],
            cwd=doe_root,
            capture_output=True,
            text=True,
            **no_console_creationflags(),
        )
    except OSError as exc:
        print(f"ERROR: could not check git status for {rel_out_dir}: {exc}", file=sys.stderr)
        sys.exit(2)
    if result.returncode != 0:
        print(f"ERROR: 'git status --porcelain -- {rel_out_dir}' failed: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(2)
    return bool(result.stdout.strip())


def _schema_differs_from_tag(doe_root: str, out_dir: str) -> bool:
    """Return True iff the COMMITTED schema at HEAD differs from what the
    `cockpit-contract-release` tag currently points at (AC8: only a real
    change to committed schema content should advance the tag).

    Preconditions: the caller has already confirmed out_dir is clean (see
    `_schema_dir_dirty`) — this compares committed content only, never the
    working tree.

    Returns True unconditionally when the tag does not exist yet (first-time
    creation, nothing to diff against). Otherwise scopes a `git diff --quiet`
    between the tag and HEAD to out_dir: exit 0 means no diff (returns
    False), exit 1 means a diff exists (returns True), any other exit is a
    git failure and is fatal (sys.exit(2)) rather than silently treated as
    either outcome.
    """
    rel_out_dir = os.path.relpath(out_dir, doe_root)
    try:
        tag_check = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"{_RELEASE_TAG}^{{commit}}"],
            cwd=doe_root,
            capture_output=True,
            text=True,
            **no_console_creationflags(),
        )
    except OSError as exc:
        print(f"ERROR: could not check for tag {_RELEASE_TAG}: {exc}", file=sys.stderr)
        sys.exit(2)
    if tag_check.returncode != 0:
        return True

    try:
        diff = subprocess.run(
            ["git", "diff", "--quiet", _RELEASE_TAG, "HEAD", "--", rel_out_dir],
            cwd=doe_root,
            capture_output=True,
            text=True,
            **no_console_creationflags(),
        )
    except OSError as exc:
        print(f"ERROR: could not diff {_RELEASE_TAG}..HEAD for {rel_out_dir}: {exc}", file=sys.stderr)
        sys.exit(2)
    if diff.returncode == 0:
        return False
    if diff.returncode == 1:
        return True
    print(
        f"ERROR: 'git diff --quiet {_RELEASE_TAG} HEAD -- {rel_out_dir}' failed: {diff.stderr.strip()}",
        file=sys.stderr,
    )
    sys.exit(2)


def _read_contract_version(out_dir: str) -> str:
    """Read the top-level `"version"` field out of the regenerated
    `cockpit-contract.schema.json` in out_dir.

    Fails loud (sys.exit(2)) on a missing file, malformed JSON, or an absent
    `"version"` key — never falls back to a placeholder. The annotated tag
    message is only as trustworthy as this read.
    """
    schema_path = os.path.join(out_dir, _CONTRACT_SCHEMA_FILENAME)
    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
    except OSError as exc:
        print(f"ERROR: could not read {schema_path}: {exc}", file=sys.stderr)
        sys.exit(2)
    except json.JSONDecodeError as exc:
        print(f"ERROR: {schema_path} is not valid JSON: {exc}", file=sys.stderr)
        sys.exit(2)
    version = schema.get("version")
    if not version:
        print(f"ERROR: {schema_path} has no top-level \"version\" field.", file=sys.stderr)
        sys.exit(2)
    return version


def _advance_release_tag(doe_root: str, out_dir: str) -> None:
    """Force-move the LOCAL `cockpit-contract-release` ANNOTATED tag to HEAD.

    Writes an annotated tag (`git tag -f -a ... -m ...`), never a lightweight
    one — a bare `git tag -f <name>` creates a lightweight tag and either
    drops or staleifies the annotation message. The message names the actual
    CONTRACT_VERSION, read from the top-level `"version"` field of the
    regenerated `cockpit-contract.schema.json` in out_dir (see
    `_read_contract_version`), so the tag message can never silently drift
    from the schema it points at.

    Local only. Does NOT push, and must NEVER push — see the module-level
    Negative-spec: under DR-060, publishing this tag to origin is DoE's
    initiative, not claude-klabauter's, and this function adding a push would silently
    transfer the publish button to claude-klabauter's tree. Today the origin push is an
    operator-run step performed in the DoE-claude clone, via
    `.github/scripts/publish_cockpit_contract.py` — NOT a bare
    `git push origin refs/tags/cockpit-contract-release`, which advances the
    moving ref alone and skips the immutable `cockpit-contract-<version>` alias
    that consumers pin to. DoE is separately wiring a workflow to trigger that
    script; it is not shipped yet, so the push stays operator-run for now and
    will remain DoE's regardless. Never an automatic side-effect of a schema
    regen and never wired to `/merge-to-main` (that command cuts and pushes
    `v*` release tags only; this ref is a separate seam DoE owns). Fails loud
    on any git error; never swallowed.
    """
    version = _read_contract_version(out_dir)
    message = f"{_RELEASE_TAG} -> CONTRACT_VERSION {version}"
    try:
        result = subprocess.run(
            ["git", "tag", "-f", "-a", _RELEASE_TAG, "-m", message],
            cwd=doe_root,
            capture_output=True,
            text=True,
            **no_console_creationflags(),
        )
    except OSError as exc:
        print(f"ERROR: could not advance tag {_RELEASE_TAG}: {exc}", file=sys.stderr)
        sys.exit(2)
    if result.returncode != 0:
        print(f"ERROR: 'git tag -f -a {_RELEASE_TAG}' failed: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(2)
    print(
        f"Advanced local annotated tag {_RELEASE_TAG} -> HEAD (CONTRACT_VERSION {version})."
    )
    print(
        "  NOT pushed — publishing this tag to origin is DoE's step to take, not "
        "claude-klabauter's. Until DoE performs it (or their own automated publish step "
        "lands), the origin tag stays stale. In the coordinator doctrine repo clone:"
    )
    print(f"    git -C {doe_root} push origin refs/tags/{_RELEASE_TAG}")


def main(argv: list[str] | None = None) -> int:
    """
    Deliberate isolation boundary — do not convert to an in-process
    import. This is env isolation: the emitter runs under a
    trampoline_env / PYTHONPATH that this process must not adopt for
    itself, over `contract.cockpit_schema.emit_schema`, DoE's frozen-bytes
    schema contract (see CLAUDE.md's cockpit-contract note — touch
    nothing else about this neighbourhood). Reason recorded in
    state/audits/2026-08-06-self-spawn-isolation-boundary-classification.md.
    """
    _bootstrap_imports()
    parser = argparse.ArgumentParser(description="Regenerate the canonical cockpit-contract schema.")
    parser.add_argument(
        "--advance-ref",
        action="store_true",
        help=(
            f"Opt-in, two-step. Step 1: regen, then commit "
            "coordinator/cockpit-contract/schema/. Step 2: re-run with --advance-ref "
            f"to force-advance the LOCAL '{_RELEASE_TAG}' tag to HEAD. Refuses (exit 2) "
            "if the schema dir has uncommitted changes — the tag must point at the "
            "commit containing the regenerated schema, not the pre-schema HEAD. Only "
            "advances when the committed schema differs from what the tag currently "
            "points at (or the tag doesn't exist yet). Never the default — a bare "
            "drift-check run must not touch the tag (AC8). Never pushes."
        ),
    )
    args = parser.parse_args(argv)

    doe_root = _resolve_doe_root()

    mak_root = claude_klabauter_root()
    if not mak_root or not os.path.isdir(mak_root):
        print("ERROR: could not resolve the claude-klabauter repo path.", file=sys.stderr)
        print("  This script regenerates the cockpit-contract schema via claude-klabauter's Python emitter.", file=sys.stderr)
        print("  Prerequisite: a local checkout of claude-klabauter, registered as machine-local key", file=sys.stderr)
        print("  'repos.claude_klabauter' (run: machine-local set repos.claude_klabauter <path>),", file=sys.stderr)
        print("  or exported as CLAUDE_KLABAUTER_ROOT=<path>.", file=sys.stderr)
        return 2

    trampoline_env = _build_trampoline_env(mak_root)

    probe = subprocess.run(
        [sys.executable, "-c", f"import {_EMITTER_MODULE}"],
        env=trampoline_env,
        capture_output=True,
        text=True,
        **no_console_creationflags(),
    )
    if probe.returncode != 0:
        print(f"ERROR: emitter module {_EMITTER_MODULE} not importable", file=sys.stderr)
        print(f"  from this interpreter ({sys.executable}) via claude-klabauter's source tree ({mak_root}).", file=sys.stderr)
        print("  Prerequisite: the interpreter running this script must satisfy claude-klabauter's declared", file=sys.stderr)
        print("  requirements (pydantic>=2, psutil>=5.9). Provision one per claude-klabauter's own setup docs", file=sys.stderr)
        print(f"  ({mak_root}/scripts/setup.sh or setup.ps1), then re-run this script under it.", file=sys.stderr)
        return 2

    out_dir = os.path.join(doe_root, "coordinator", "cockpit-contract", "schema")
    print(f"Regenerating cockpit-contract schema via claude-klabauter emitter ({sys.executable})...")
    env = dict(trampoline_env)
    env["COCKPIT_SCHEMA_OUT_DIR"] = out_dir
    result = subprocess.run(
        [sys.executable, "-m", _EMITTER_MODULE],
        env=env,
        **no_console_creationflags(),
        capture_output=True,
        text=True,
    )
    # Success-path stdout/stderr from the claude-klabauter emitter subprocess is not
    # relayed here — this script prints its own "Done." summary below, and
    # no test/wiki contract in this repo asserts on the emitter's own
    # success-path output. `_EMITTER_MODULE` is a claude-klabauter source
    # module outside this repo; if it turns out to emit load-bearing
    # progress output on success, switch this to unconditional relay.
    # (Review: code-reviewer — Finding 6, 2026-07-22.)
    if result.returncode != 0:
        if result.stdout:
            print(result.stdout, file=sys.stderr, end="" if result.stdout.endswith("\n") else "\n")
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="" if result.stderr.endswith("\n") else "\n")
        return result.returncode

    print(
        "Done. Verify no unexpected drift: git diff --exit-code -- coordinator/cockpit-contract/schema/ "
        "(should be empty unless a real contract change occurred)."
    )

    if args.advance_ref:
        if _schema_dir_dirty(doe_root, out_dir):
            print(
                "ERROR: --advance-ref refused — coordinator/cockpit-contract/schema/ has "
                "uncommitted changes.",
                file=sys.stderr,
            )
            print(
                "  The release tag must point at the COMMIT that contains the regenerated "
                "schema, committed and clean — not the pre-schema HEAD.",
                file=sys.stderr,
            )
            print("  Commit the schema first, then re-run with --advance-ref:", file=sys.stderr)
            print(
                "    1. git add -- coordinator/cockpit-contract/schema/ && git commit -- "
                "coordinator/cockpit-contract/schema/",
                file=sys.stderr,
            )
            print(
                "    2. python coordinator/bin/regen-cockpit-schema.py --advance-ref",
                file=sys.stderr,
            )
            return 2

        if _schema_differs_from_tag(doe_root, out_dir):
            _advance_release_tag(doe_root, out_dir)
        else:
            print(
                f"--advance-ref: committed schema already matches {_RELEASE_TAG} — nothing to "
                f"signal, tag unchanged."
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
