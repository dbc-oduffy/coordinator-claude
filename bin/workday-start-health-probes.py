# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""workday-start-health-probes.py — day-start health-probe imperative logic,
ported off DoE-claude's `coordinator/commands/workday-start.md`.

Several `/workday-start` steps wrapped a single sibling CLI invocation in
genuine bash imperative logic (rc-branching, regex date extraction, path
canonicalization, conditional dir/exec checks, capture-then-conditionally-
print) that lived nowhere lintable/testable — a `.md` fence is invisible to
ShellCheck, the test registry, and the coverage-of-the-coverage gate (see
DoE-claude `CLAUDE.local.md` § "A skill must LINK to an entrypoint"). This
CLI is the naked-Python home for that residual logic; the DoE-side fence
shrinks to a single call to this file plus the shared `_cc_trusted`/
`_cc_claude_klabauter` resolution preamble (unchanged — that preamble is D1/D2's
concern, not this chunk's).

Because this file lives co-located with its sibling probes under
`coordinator/bin/`, it resolves them via `os.path.dirname(__file__)` rather
than re-running the DoE-side CLAUDE_KLABAUTER_ROOT resolution ladder a second time —
the DoE fence already did that resolution once to find *this* file.

Subcommands (argv[1] selects):
  observer-sidecar-scan [--dir <path>]
      Ported from workday-start.md Step 1.10.64. Sweeps <path> (default
      "archive/daily-summaries", cwd-relative — the ceremony's own repo, not
      claude-klabauter's) for orphaned `*.observer.md` sidecars via the sibling
      stitch-observer-sidecar.py --scan, then (on its rc=1 "orphans found"
      contract) extracts the YYYY-MM-DD dates from its output and renders one
      collapsed WARN line naming every affected date. Silent (exit 0, no
      output) when the scan dir doesn't exist yet, or the scan finds nothing
      (rc=0), or the scan itself hit a usage error (rc=2 — the sentinel's job
      to catch, not this probe's).
      Exit: 0 clean/skip, 1 orphans found (WARN emitted to stderr), 2 passthrough
      usage error from the underlying scan.

  claude-klabauter-bin-sentinel
      Ported from workday-start.md Step 1.10.9. Confirms this script's own
      `coordinator/bin` directory exists (near-tautological when this CLI is
      running at all, but preserved for parity with a degenerate
      symlink/partial-checkout case) and that the sibling `archive-stamp-cli`
      — the sole authorized handoff/memo frontmatter writer — is present and
      executable. A partial/stale engine-repo migration can leave some
      bin/ scripts in place and others missing; this is what actually
      differs from "this script itself ran".
      Exit: 0 both checks pass, 1 either check fails (message to stderr).

  ceremony-hook <ceremony-name>
      Ported from workday-start.md Step 5.6. Thin capture-then-conditionally-
      print wrapper over the sibling coordinator-ceremony-hook.py: captures
      its stdout, WARNs to stderr (non-blocking) on a non-zero exit — dead in
      practice since coordinator-ceremony-hook.py's own contract is
      ALWAYS-exit-0 (see that file's module docstring), kept only as the same
      defensive belt-and-suspenders the bash fence carried — then re-emits
      the captured stdout verbatim to this process's stdout when non-empty.
      Exit: always 0 (the wrapped ceremony hook must never block the
      calling ceremony; see coordinator-ceremony-hook.py's own contract).

  working-repo-registration [--fix]
      Confirms `engine.working_repos.claude_klabauter` (the machine-local
      registry key `_is_engine_working_repo()` — DoE-claude
      `coordinator/hooks/scripts/_engine_root.py` — consults to decide
      whether an engine-repo session resolves the LIVE engine working
      tree or the PUBLISHED engine mirror) is registered and matches this
      repo's own root. Written only at install time by
      `scripts/setup.py::register_claude_klabauter_root()`; if wiped or
      hand-corrupted, claude-klabauter's own sessions would silently resolve the
      published engine instead (edits to `coordinator_core` stop
      executing), and the live-tree fallback rungs do not rescue it because
      the working-repo gate short-circuits first. Governing record: DR-132
      (DoE-claude `docs/decisions/DR-132-engine-working-repos-is-its-own-
      namespace-not-a-repos-star-inference.md`). Currently inert —
      `_resolve_published_engine()` returns None while
      `repos.claude_klabauter` is unregistered on this machine — and ARMS
      as soon as the OSS-release workstream registers klabauter; this probe
      lands detection ahead of that.

      Identity-gated (both the bare detector and `--fix`): reuses
      `scripts/setup.py::resolve_repo_identity()` rather than reimplementing
      its marker check. This CLI's own `coordinator/bin/` tree ships
      identically in a claude-klabauter clone (a published engine MIRROR,
      never a working repo — see `scripts/setup.py::register_claude_klabauter_root`'s
      docstring for why writing this key from that clone would invert the
      working-repo discriminant), so running this subcommand from such a
      clone must never report the key "missing" and instruct the operator
      to register that clone's root — that is the false-positive
      registration DoE's `.coordinator-dev-repo` guard exists to prevent,
      pointed at THIS key instead. When the current root does not resolve
      as the engine repo, this subcommand is a silent, zero-cost no-op
      (exit 0) for the bare detector; `--fix` additionally refuses to WRITE
      anything (fails closed) and reports the skip to stdout instead.

      Bare detector is zero-spawn: reads the registry TOML directly via
      `coordinator_core.machine_resolver.registry_get` — never shells out
      to `machine-local`. Stays safe to call in-process from the
      zero-spawn-budgeted orientation assembler (that assembler only ever
      calls the bare form, never `--fix` — see
      `coordinator_core/orient_assemble/readers_health_reaper.py`'s reader).
      Never raises: any read/parse/resolution failure degrades to pass (0)
      — a health probe on the session boot path must never itself block
      that path. Only a positively-determined absent-or-mismatched value
      fails.
      Exit (bare): 0 registered and matching, identity not the engine repo,
      or any read/parse failure; 1 absent or mismatched (message to stderr,
      remediation included verbatim).

      `--fix` is the apply half (discharge test: a probe that only hands
      the operator a command to retype has relocated the transcription,
      not discharged it). Spawns the SANCTIONED registry writer,
      `machine-local set engine.working_repos.claude_klabauter <root>` —
      never hand-edits the registry TOML (a concurrent session may be
      writing it). This is the ONE place in this subcommand a subprocess is
      spawned; the bare detector (and the orientation reader that calls it)
      stays zero-spawn. Idempotent: when the key is already correct, writes
      and spawns nothing, exit 0. Prints the old value (if any) and the new
      one to stdout for auditability.
      Exit (--fix): 0 already-correct no-op, successful write, or
      identity-refused skip (all three are "nothing left to do here",
      reported on stdout, never a failure); 1 the write itself failed (the
      `machine-local set` spawn errored or returned non-zero — surfaced so
      whatever applied the directive knows the fix did not land).

Spec backlink: DoE-claude `coordinator/commands/workday-start.md` §§
  Step 1.10.64 (Orphaned Observer Sidecar Sweep), Step 1.10.9 (Claude-Klabauter-Bin
  Sentinel Probe), Step 5.6 (Project Post-Ceremony Command Hook).
Port backlink: M3 chunk WDS-5 (bash-kill campaign, structural-bash-to-
  naked-Python residual port).

Retired 2026-07-28: the `exec-bit-check` subcommand (formerly Step 1.10.8,
Exec-Bit Drift Probe) and its wrapped `check-all-shebanged-exec-bits.py`
CLI are removed. That probe asserted "every shebanged file must be git mode
100755" -- the exact invariant the 2026-07-28 PM ruling retired (POSIX-only
execution assumptions, including reliance on the exec bit, are now a
portability defect class; Windows is the P0 primary platform). The same
violation shape (git mode 100755) is now tracked with the opposite polarity
by `coordinator_core.ops.check_posix_exec_assumptions`'s `mode_100755`
blocking class -- a frozen-baseline, shrink-only ratchet, not a daily
require-it-present probe. See `coordinator_core/ops/check_all_shebanged_exec_bits.py`'s
git history for the removed engine module.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# coordinator_core is co-located in this same (engine) repo --
# resolvable only from the repo root, which is not on sys.path when this
# file is run directly (only its own dir is).
_REPO_ROOT = os.path.dirname(os.path.dirname(_SCRIPT_DIR))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_LIB_DIR = os.path.join(_SCRIPT_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from coordinator_core.machine_resolver import registry_get  # noqa: E402
from coordinator_core.win_portability import is_executable, no_console_creationflags  # noqa: E402
from cli_shared import machine_local_impl, resolve_python  # noqa: E402

_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

_WORKING_REPO_REGISTRY_KEY = "engine.working_repos.claude_klabauter"
_SETUP_PY_PATH = os.path.join(_REPO_ROOT, "scripts", "setup.py")
_FIX_SPAWN_TIMEOUT = 30


def _usage(prog: str) -> int:
    print(
        f"usage: {prog} <subcommand> <args...>\n"
        "subcommands: observer-sidecar-scan [--dir <path>] | "
        "claude-klabauter-bin-sentinel | ceremony-hook <ceremony-name> | "
        "working-repo-registration [--fix]",
        file=sys.stderr,
    )
    return 2


def _resolve_repo_identity() -> str | None:
    """Reuse `scripts/setup.py::resolve_repo_identity` rather than
    reimplementing its marker check (module docstring's
    "working-repo-registration" entry). Loaded on demand via
    `importlib.util` — `scripts/setup.py` only runs its own `main()` under
    an `if __name__ == "__main__":` guard, so importing it here executes no
    install/registration side effects. Degrades to None on any import/call
    failure, same "never raise" contract as the rest of this subcommand."""
    try:
        spec = importlib.util.spec_from_file_location(
            "_claude_klabauter_setup_for_identity", _SETUP_PY_PATH
        )
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        # Deliberately not registered in sys.modules: this CLI is
        # spawn-per-call and does one identity check per invocation, so
        # there is no cache to win, and `scripts/setup.py` has no
        # self-referential import that would need to find itself there.
        # Revisit only if `setup.py` grows an import of its own module
        # name during exec.
        spec.loader.exec_module(module)
        return module.resolve_repo_identity(Path(_REPO_ROOT))
    except Exception:  # noqa: BLE001 — identity resolution must never raise/block
        return None


def _sibling(name: str) -> str:
    return os.path.join(_SCRIPT_DIR, name)


def _paths_match(registered: str, expected: str) -> bool:
    """Shared by both the bare-form check and the `--fix` idempotence check
    so the comparison cannot drift between the two call sites.
    `os.path.normcase` is a no-op on POSIX and lowercases (plus normalizes
    separators) on Windows — the fold-case-on-Windows-only behaviour we
    want. Do not replace with a hand-rolled `.lower()`: on case-sensitive
    Linux filesystems two paths differing only in case are genuinely
    different directories, and `.lower()` would wrongly treat them as
    equal."""
    return os.path.normcase(os.path.normpath(registered)) == os.path.normcase(
        os.path.normpath(expected)
    )


def cmd_observer_sidecar_scan(argv: list[str]) -> int:
    scan_dir = "archive/daily-summaries"
    i = 0
    while i < len(argv):
        if argv[i] == "--dir":
            if i + 1 >= len(argv):
                print("workday-start-health-probes: observer-sidecar-scan: --dir requires a value", file=sys.stderr)
                return 2
            scan_dir = argv[i + 1]
            i += 2
        else:
            print(f"workday-start-health-probes: observer-sidecar-scan: unrecognized argument {argv[i]!r}", file=sys.stderr)
            return 2

    if not os.path.isdir(scan_dir):
        # No daily-summary ceremony has ever run in this repo — not a leak.
        return 0

    proc = subprocess.run(
        [sys.executable, _sibling("stitch-observer-sidecar.py"), "--scan", scan_dir],
        capture_output=True,
        text=True,
        **no_console_creationflags(),
    )

    if proc.returncode == 1:
        combined = (proc.stdout or "") + (proc.stderr or "")
        dates = sorted(set(_DATE_RE.findall(combined)))
        date_list = ",".join(dates)
        print(
            f"[workday-start] WARN: orphaned observer sidecar(s) in {scan_dir}/ for: "
            f"{date_list} — run `stitch-observer-sidecar.py --scan {scan_dir}` for detail, "
            "or re-run Step 4d's stitch for the affected date(s) (non-blocking)",
            file=sys.stderr,
        )
        return 1

    # rc=0 (nothing found) or rc=2 (usage error — the sentinel's job to catch,
    # not this probe's) both pass through silently, matching the bash fence.
    return proc.returncode


def cmd_claude_klabauter_bin_sentinel(argv: list[str]) -> int:
    del argv  # no flags accepted
    mkb_bin = _SCRIPT_DIR
    sentinel = os.path.join(mkb_bin, "archive-stamp-cli.py")
    if not os.path.isdir(mkb_bin):
        print(
            f"CLAUDE-KLABAUTER-BIN PROBE: '{mkb_bin}' missing — wrong checkout or stale clone; "
            "confirm repos.claude_klabauter points at the repo root",
            file=sys.stderr,
        )
        return 1
    if not (os.path.isfile(sentinel) and is_executable(sentinel)):
        print(
            f"CLAUDE-KLABAUTER-BIN PROBE: sentinel '{sentinel}' missing or not executable — "
            f"stale/partial engine-repo migration; restore this one file, e.g. "
            f"`git checkout -- {sentinel}`",
            file=sys.stderr,
        )
        return 1
    return 0


def cmd_ceremony_hook(argv: list[str]) -> int:
    if not argv:
        print("usage: workday-start-health-probes.py ceremony-hook <ceremony-name>", file=sys.stderr)
        return 2
    ceremony_name = argv[0]
    proc = subprocess.run(
        [sys.executable, _sibling("coordinator-ceremony-hook.py"), ceremony_name],
        capture_output=True,
        text=True,
        **no_console_creationflags(),
    )
    if proc.returncode != 0:
        # Defensive-only: coordinator-ceremony-hook.py's own contract is
        # ALWAYS-exit-0. This branch is unreachable in practice; kept for
        # parity with the bash fence's `|| echo WARN` belt-and-suspenders.
        print("[workday-start] WARN: ceremony-hook exited non-zero (non-blocking)", file=sys.stderr)
    if proc.stdout:
        sys.stdout.write(proc.stdout)
        if not proc.stdout.endswith("\n"):
            sys.stdout.write("\n")
    # Never blocks the calling ceremony.
    return 0


def cmd_working_repo_registration(argv: list[str]) -> int:
    """Confirm `engine.working_repos.claude_klabauter` is registered and
    points at THIS repo's own root (`_REPO_ROOT`, derived from `__file__` —
    never re-derived via a resolver lookup, never cwd; see module docstring
    "working-repo-registration" entry for why re-deriving would re-enact the
    circularity `coordinator_core/install/maximalist.py`'s seeding block
    documents).

    Identity-gated first (`_resolve_repo_identity`): when this root does not
    resolve as the engine repo (e.g. a downstream clone, which ships
    this same `coordinator/bin/` tree but must NEVER register this key —
    see `scripts/setup.py::register_claude_klabauter_root`'s docstring), this
    subcommand is a no-op. Bare form: silent pass (0), same as any other
    not-applicable-here health probe. `--fix` form: refuses to write
    (fails closed) and reports the skip on stdout rather than acting.

    Bare form is zero-spawn (registry_get is a direct tomllib read, never a
    `machine-local` CLI subprocess) and never raises — any read/parse
    failure degrades to pass (0); only a positively-determined
    absent-or-mismatched value fails (1). See module docstring for the
    DR-132 backlink and the "arms when klabauter registers" rationale.

    `--fix` spawns the sanctioned `machine-local set` writer (never
    hand-edits the registry TOML) to repair a genuine absent/mismatched
    key. Idempotent — already-correct is a no-op, no spawn. This is the
    ONE place in this subcommand a subprocess is spawned; do not add a
    spawn to the bare-form path above (the zero-spawn-budgeted orientation
    assembler calls only the bare form — see
    `coordinator_core/orient_assemble/readers_health_reaper.py`).
    """
    fix = False
    for arg in argv:
        if arg == "--fix":
            fix = True
        else:
            print(
                f"workday-start-health-probes: working-repo-registration: "
                f"unrecognized argument {arg!r}",
                file=sys.stderr,
            )
            return 2

    identity = _resolve_repo_identity()
    expected = _REPO_ROOT

    if identity != "claude-klabauter":
        if fix:
            print(
                "working-repo-registration --fix: SKIP — this repo's identity resolved as "
                f"{identity!r}, not 'claude-klabauter'; engine.working_repos.claude_klabauter is "
                "not this checkout's key to write (writing it here would register a non-"
                "working-repo clone as a working repo)."
            )
        return 0

    try:
        registered = registry_get(_WORKING_REPO_REGISTRY_KEY)
    except Exception:  # noqa: BLE001 — a health probe must never itself raise/block the boot path
        return 0

    matches = bool(registered) and _paths_match(registered, expected)

    if not fix:
        if not registered:
            print(
                "WORKING-REPO PROBE: engine.working_repos.claude_klabauter is not registered — "
                "this repo will resolve the PUBLISHED engine, not its own live tree, once a "
                "published engine is registered. Fix: workday-start-health-probes.py "
                "working-repo-registration --fix  (or: machine-local set "
                f"engine.working_repos.claude_klabauter {expected}  or re-run: python3 scripts/setup.py)",
                file=sys.stderr,
            )
            return 1
        if not matches:
            print(
                "WORKING-REPO PROBE: engine.working_repos.claude_klabauter is registered as "
                f"{registered!r} but this repo's root is {expected!r} — this repo will resolve "
                "the PUBLISHED engine, not its own live tree, once a published engine is "
                "registered. Fix: workday-start-health-probes.py working-repo-registration "
                "--fix  (or: machine-local set "
                f"engine.working_repos.claude_klabauter {expected}  or re-run: python3 scripts/setup.py)",
                file=sys.stderr,
            )
            return 1
        return 0

    # --fix from here down.
    if matches:
        print(
            "working-repo-registration --fix: already correct — "
            f"engine.working_repos.claude_klabauter={registered!r} — nothing to write."
        )
        return 0

    old_value = registered
    try:
        proc = subprocess.run(
            [resolve_python(), machine_local_impl(), "set", _WORKING_REPO_REGISTRY_KEY, expected],
            capture_output=True,
            text=True,
            timeout=_FIX_SPAWN_TIMEOUT,
            **no_console_creationflags(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(
            f"working-repo-registration --fix: FAILED — could not spawn machine-local set: {exc}",
            file=sys.stderr,
        )
        return 1

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        print(
            f"working-repo-registration --fix: FAILED — machine-local set exited "
            f"{proc.returncode}: {detail}",
            file=sys.stderr,
        )
        return 1

    print(
        "working-repo-registration --fix: wrote engine.working_repos.claude_klabauter — "
        f"old={old_value!r} new={expected!r}"
    )
    return 0


_SUBCOMMANDS = {
    "observer-sidecar-scan": cmd_observer_sidecar_scan,
    "claude-klabauter-bin-sentinel": cmd_claude_klabauter_bin_sentinel,
    "ceremony-hook": cmd_ceremony_hook,
    "working-repo-registration": cmd_working_repo_registration,
}


def main(argv: list[str]) -> int:
    if not argv:
        return _usage("workday-start-health-probes.py")
    subcmd, rest = argv[0], argv[1:]
    if subcmd in ("--help", "-h", "help"):
        _usage("workday-start-health-probes.py")
        return 0
    handler = _SUBCOMMANDS.get(subcmd)
    if handler is None:
        print(f"workday-start-health-probes: unknown subcommand {subcmd!r}", file=sys.stderr)
        return _usage("workday-start-health-probes.py")
    return handler(rest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
