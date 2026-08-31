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
than re-running the DoE-side engine-root resolution ladder a second time —
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

  mis-channelled-box
      NEW 2026-08-16 (chunk C29). PM RULING, verbatim: "we should detect this."
      Detects a box running the PUBLISHED engine on the wrong release channel —
      the gap neither repo's plan closed on its own (DoE-claude's resolver
      diverts to a klabauter tree on the wrong channel and reports
      `resolved-engine` truthfully; nothing on either plane notices the branch
      disagrees with the box's own declaration). Catches both entry points to
      the same defect: a manual `git checkout` in the mirror
      (`klabauter-release-channels` AC11's residual) and a box INSTALLED onto
      the wrong channel (the AC8 gap, drift included).

      Only fires when `resolve_claude_klabauter_root_with_class()` answers
      `RESOLUTION_RESOLVED_ENGINE` — a live working tree isn't running a
      published channel at all, so it is out of scope by construction.
      "Actually on" is read zero-spawn, mirroring DoE-claude's
      `_read_current_branch_boot()` technique (`project-orientation.py`) — a
      direct `.git/HEAD` text read, never a `git` subprocess. "Should be on"
      is the box's own declaration, `engine.target`
      (`_resolve_claude_klabauter.resolve_engine_target`) — its two values, `main` and
      `candidate`, ARE the branch names C8 established as the channel-
      selecting fact, so no further translation is needed.

      NOT a hard block: a box legitimately sits mid-transition during a
      channel switch, so this only WARNs (non-blocking) and names the
      runnable remediation (`klabauter-channel.py --set <target>`) — never a
      slash command (cold-path rule).

      NEGATIVE SPEC: never infers the expected channel from what the mirror
      has checked out — that is the same declared-or-nothing rule C3 carries;
      inferring it here would make the probe agree with itself and detect
      nothing.

      ABSENT `engine.target` IS NOT A MISMATCH — the not-yet-rolled-out
      state (C8's own doctor probe already enumerates it); reporting it here
      would false-positive on every machine on day one. Silent (exit 0).

      Zero-spawn end to end: no subprocess is spawned by this subcommand.
      Never raises — any resolution/read failure degrades to pass (0), same
      "never block the boot path" contract as every other probe in this file.
      Exit: 0 clean/not-applicable/absent-target, 1 mismatch (WARN to stderr,
      remediation included verbatim).

  working-repo-registration [--fix]
      Confirms `engine.working_repos.claude_klabauter` (the machine-local
      registry key) is registered and matches this repo's own root.
      Written only at install time by `scripts/setup.py::register_claude_klabauter_root()`.

      2026-08-18 (C4): this key is a PURE LOCATOR on claude-klabauter's own plane —
      claude-klabauter's own resolver (`coordinator/lib/resolve-claude-klabauter/
      _resolve_claude_klabauter.py::resolve_claude_klabauter_root_with_class`) no longer
      consults `engine.working_repos.*` at all; its live-tree-vs-published
      discriminant is now structural (is the session's own root the
      resolved `repos.claude_klabauter` value?), not a lookup against this
      key. This probe still matters because OTHER consumers of this
      namespace remain (DoE-claude's own resolver, per DR-132; other
      cross-repo locator callers that resolve "where is claude-klabauter
      checked out" via this key, e.g. `coordinator_core/ops/
      setup_chain_walker.py`'s doe_claude analogue) — a wiped or
      hand-corrupted entry still breaks THOSE reads, just not claude-klabauter's own
      session resolution any more. Governing record: DR-132 (DoE-claude
      `docs/decisions/DR-132-engine-working-repos-is-its-own-
      namespace-not-a-repos-star-inference.md`). Currently inert on claude-klabauter's
      own gate — `_resolve_published_engine()` returns None while
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

  git-perf-currency [--fix]
      Confirms `core.untrackedCache` (the one adopted git-perf setting --
      see `coordinator_core/install/git_perf_config.py`'s module docstring
      for the measurement bar that justifies it) is set on every registered
      `worktree` repo, not merely the one repo `scripts/setup.py` happened to
      be invoked from. `apply_fleet()` has always been able to sweep the
      whole fleet; nothing ever called it after install, so every machine but
      the one that ran the installer carries the key nowhere -- the same
      unwired-heal drift class `hook-currency` above closed for git hooks.

      Bare detector is zero-spawn: enumerates registry roots via
      `git_perf_config._git_hook_install_registry_helpers()` (the same
      helper `apply_fleet` itself uses), skips `mirror` targets silently and
      reports `missing` ones exactly as `apply_fleet` does, then for each
      `worktree` reads `.git/config` (or, for a `.git` gitlink file --
      worktree/submodule -- resolves it to the real gitdir, following
      `commondir` when present, since a linked worktree's config lives in
      the COMMON dir) as plain text and checks for `untrackedcache = true`
      under `[core]`. An unreadable config is reported, never silently
      passed. No `git` subprocess is spawned to answer this question.

      NEGATIVE SPEC: does NOT verify the index extension (`.git/index`'s
      `UNTR` chunk), only the config key. Parsing the index binary format on
      every cadence run to re-derive a fact `apply()` already owns would
      fork the currency predicate between this detector and `apply()` --
      the exact mistake `hook-currency`'s own negative spec records for a
      different mechanism. The config key's absence is the drift signal
      that matters: a machine that never ran the sweep has neither the key
      nor the index extension, so the key alone is a faithful proxy for "has
      this machine ever seen the sweep".

      `--fix` calls `git_perf_config.apply_fleet()` in-process (no spawn --
      same shape as `hook-currency`'s in-process call to
      `ensure_hooks_fleet`) and prints its report. Idempotent by
      construction (`apply()`'s own idempotence).
      Exit (bare): 0 every worktree carries the key, or the registry
      helpers/roots could not be read (degrades to pass, same "never block
      the boot path" contract as the other bare detectors here); 1 one or
      more worktrees are missing the key (message to stderr, remediation
      included verbatim).
      Exit (--fix): 0 the sweep ran and produced no `FAILED` line; 1 the
      sweep could not run at all, or produced at least one `FAILED` line.

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
_RESOLVE_CLAUDE_KLABAUTER_DIR = os.path.join(_REPO_ROOT, "coordinator", "lib", "resolve-claude-klabauter")

_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


_BOOTSTRAP_DONE = False

_BOOTSTRAPPED_NAMES = ("_resolve_claude_klabauter",)


def _ensure_repo_root_on_path() -> None:
    """Per-call sys.path setup for this file's own coordinator_core /
    _resolve_claude_klabauter / cli_shared imports -- called from each function that
    needs one of them, never at module scope (a per-call insert still
    mutates the sys.path ~50 concurrent sessions share, only later than a
    module-scope insert would). Also binds `_resolve_claude_klabauter` as a module
    global -- `cmd_mis_channelled_box` reads it as a bare global (its own
    `import _resolve_claude_klabauter` used to make it function-local only), and
    `test_mis_channelled_box_probe.py` monkeypatches `_mod._resolve_claude_klabauter`
    before calling the subcommand."""
    global _BOOTSTRAP_DONE
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)
    if _RESOLVE_CLAUDE_KLABAUTER_DIR not in sys.path:
        sys.path.insert(0, _RESOLVE_CLAUDE_KLABAUTER_DIR)
    if _BOOTSTRAP_DONE:
        return
    global _resolve_claude_klabauter
    import _resolve_claude_klabauter
    _BOOTSTRAP_DONE = True


def __getattr__(name: str):
    """PEP 562 hook so a caller reaching for `_resolve_claude_klabauter` before any
    subcommand has run -- a test monkeypatching `_mod._resolve_claude_klabauter` --
    triggers `_ensure_repo_root_on_path()` lazily instead of finding the
    name absent.

    NEGATIVE SPEC -- the forced re-run is not belt-and-braces. The bootstrap
    short-circuits on `_BOOTSTRAP_DONE`, so a name that leaves `__dict__`
    AFTER the bootstrap has run is never rebound by a plain call.
    `mock.patch.object` does exactly that: it reads the name through this
    hook (so the value is not in `__dict__` at enter), sets its mock, and on
    exit `delattr`s rather than restoring -- then probes `hasattr`, which
    lands here with the flag already set. Without the reset that probe
    raises KeyError instead of returning the name.
    """
    if name in _BOOTSTRAPPED_NAMES:
        _ensure_repo_root_on_path()
        if name not in globals():
            global _BOOTSTRAP_DONE
            _BOOTSTRAP_DONE = False
            _ensure_repo_root_on_path()
        try:
            return globals()[name]
        except KeyError:
            raise AttributeError(
                f"module {__name__!r} has no attribute {name!r}"
            ) from None
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

_WORKING_REPO_REGISTRY_KEY = "engine.working_repos.claude_klabauter"
_SETUP_PY_PATH = os.path.join(_REPO_ROOT, "scripts", "setup.py")
_FIX_SPAWN_TIMEOUT = 30


def _usage(prog: str) -> int:
    print(
        f"usage: {prog} <subcommand> <args...>\n"
        "subcommands: observer-sidecar-scan [--dir <path>] | "
        "claude-klabauter-bin-sentinel | ceremony-hook <ceremony-name> | "
        "mis-channelled-box | working-repo-registration [--fix] | hook-currency [--check-only] | "
        "git-perf-currency [--fix]",
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
    _ensure_repo_root_on_path()
    from coordinator_core.win_portability import no_console_creationflags

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
    _ensure_repo_root_on_path()
    from coordinator_core.win_portability import is_executable

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
    _ensure_repo_root_on_path()
    from coordinator_core.win_portability import no_console_creationflags

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


def _read_current_branch_boot(repo_root: str | None) -> str:
    """Pure-Python `.git/HEAD` read — no `git` subprocess.

    Port of DoE-claude's zero-spawn technique (`coordinator/hooks/scripts/
    project-orientation.py::_read_current_branch_boot`, cited verbatim in
    this chunk's spec as prior art to reuse rather than re-derive) — module
    docstring's "mis-channelled-box" entry. `.git/HEAD` normally contains
    `ref: refs/heads/<branch>\n` on a checked-out branch, or a bare 40-char
    SHA in detached-HEAD state; this returns the branch name in the former
    case and "" (undeterminable) in the latter. Never raises."""
    if not repo_root:
        return ""
    try:
        head_text = (Path(repo_root) / ".git" / "HEAD").read_text(
            encoding="utf-8", errors="replace"
        ).strip()
    except Exception:
        return ""
    if not head_text.startswith("ref:"):
        return ""
    ref = head_text.split(":", 1)[1].strip()
    if not ref.startswith("refs/heads/"):
        return ""
    return ref[len("refs/heads/"):]


def cmd_mis_channelled_box(argv: list[str]) -> int:
    """Detect a box running the published engine on the wrong release
    channel. See module docstring's "mis-channelled-box" entry for the full
    contract (never raises, zero-spawn, non-blocking WARN on mismatch)."""
    del argv  # no flags accepted
    _ensure_repo_root_on_path()
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cli_shared import resolve_python

    try:
        root, resolution_class = _resolve_claude_klabauter.resolve_claude_klabauter_root_with_class()
    except Exception:  # noqa: BLE001 — a health probe must never itself raise/block the boot path
        return 0

    if resolution_class != _resolve_claude_klabauter.RESOLUTION_RESOLVED_ENGINE:
        # A live working tree isn't running a published channel at all.
        return 0

    try:
        declared = _resolve_claude_klabauter.resolve_engine_target()
    except Exception:  # noqa: BLE001
        return 0

    if declared is None:
        # AC20-style rule: absent/unreadable engine.target is the
        # not-yet-rolled-out state, never a mismatch.
        return 0

    actual = _read_current_branch_boot(root)
    if not actual:
        # Undeterminable (detached HEAD, unreadable .git/HEAD, ...) —
        # degrade to pass rather than false-positive on a guess.
        return 0

    if actual == declared:
        return 0

    print(
        f"[workday-start] WARN: box is running the wrong channel — declared "
        f"engine.target={declared!r}, resolved engine at {root!r} is checked "
        f"out on {actual!r}. Fix: {resolve_python()} "
        f"{_sibling('klabauter-channel.py')} "
        f"--set {declared}",
        file=sys.stderr,
    )
    return 1


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
    _ensure_repo_root_on_path()
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from coordinator_core.machine_resolver import registry_get
    from coordinator_core.win_portability import no_console_creationflags

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
        # foreign-identity: NOT-REACHABLE — basis: DELIBERATE INVOCATION, not true
        # unreachability. The session-start hot path calls only the bare (fix=False)
        # form via readers_health_reaper.py; this fix-branch print only fires when an
        # operator deliberately runs `working-repo-registration --fix` and went looking
        # for it — a third-repo session cannot hit this ambiently, but a foreign-repo
        # operator CAN reach it by typing the command.
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

    # --fix from here down. `cli_shared` is imported HERE, not at function top:
    # the bare form above promises it never raises, and a top-level import of a
    # module that needs coordinator/bin/lib bootstrapped onto sys.path breaks
    # that promise on the orient path, where `readers_health_reaper.collect()`
    # calls the bare form.
    from cli_shared import machine_local_impl, resolve_python

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


def cmd_hook_currency(argv: list[str]) -> int:
    """Install/repair the coordinator git hooks in every registered repo, or
    (with `--check-only`) DETECT staleness without writing anything.

    Purpose: `git_hook_install.ensure_hooks_fleet` compares each registered
    repo's installed hook against the generation the installer would write and
    rewrites the stale ones. Its own docstring names the `/workday-start`
    per-day self-heal as its caller; nothing actually called it, so 28 hooks
    across 14 repos sat stale until 2026-08-29. This subcommand is that caller.

    Why a stale hook body is break-class: the `post-commit` hook IS the
    auto-push. A stale body whose script ladder hands an installed `.exe`
    forwarder to a native `python.exe` dies on every commit WITHOUT failing the
    commit -- the push leg is lost silently and surfaces as an unpushed backlog
    the session banner blames on a diverged branch.

    Exit 1 when anything was repaired (or, under `--check-only`, would need
    repair) or the walk could not run; 0 when the fleet was already current.
    That code is the signal `orient_assemble/readers_health_reaper.py` keys on
    to emit its directive; a probe that returned 0 unconditionally would make a
    broken walk indistinguishable from a healthy fleet, which is the same
    silence-reads-as-health shape as the dead auto-push above.

    `--check-only`: threads `check_only=True` into `ensure_hooks_fleet`, which
    threads it into `_ensure_hook` -- the SAME currency predicate
    (`_hook_gen_stamp_line()`), the write just does not happen. Added
    2026-08-31 (C1+C2 of docs/plans/2026-08-31-orient-assemble-stops-running-
    a-fleet-re.md) so the orient-assemble read path can ask "is the fleet
    current?" without repairing fourteen sibling repositories as a side
    effect of orienting a session. The repairing bare form (no flag) is
    UNCHANGED -- default-false is byte-identical to every existing caller.

    Negative-spec:
      - Does NOT re-decide hook currency. An earlier revision carried its own
        registry walk and a `stamp not in body` test, which already diverged
        from `_ensure_hook`'s real predicate on APPEND-FORM bodies -- those
        never carry the stamp by design, so the copy would have reported them
        stale on every run, for ever. The currency decision has one owner.
      - Does NOT spawn. `coordinator-ensure-hooks-fleet`'s entire body is
        `return ensure_hooks_fleet(_BIN_DIR)`, so spawning an interpreter to
        reach it buys a process and a timeout to manage and nothing else.
      - Does NOT install into an unregistered repo: the walk reads the
        machine-local registry, and a repo absent from it is silently never
        healed. That is the registry's gap, not this probe's.
    """
    check_only = False
    for arg in argv:
        if arg == "--check-only":
            check_only = True
        else:
            print("usage: workday-start-health-probes.py hook-currency [--check-only]", file=sys.stderr)
            return 2

    _ensure_repo_root_on_path()
    import contextlib
    import importlib.util
    import io

    lib_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib", "git_hook_install.py")
    buf = io.StringIO()
    try:
        spec = importlib.util.spec_from_file_location("git_hook_install", lib_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"no loader for {lib_path}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with contextlib.redirect_stderr(buf):
            mod.ensure_hooks_fleet(os.path.dirname(os.path.abspath(__file__)), check_only=check_only)
    except Exception as exc:
        print(f"hook-currency: COULD NOT RUN the fleet hook heal: {exc}", file=sys.stderr)
        return 1

    detail = buf.getvalue().strip()
    if not detail:
        return 0
    print(detail, file=sys.stderr)
    return 1


_BIN_DIR = Path(_SCRIPT_DIR)


def _resolve_gitdir(repo_root: Path) -> Path | None:
    """Resolve `repo_root`'s real gitdir, following a `.git` gitlink file
    (worktree/submodule) and, when present, its `commondir` pointer -- a
    linked worktree's `config` lives in the COMMON dir, not its own private
    gitdir. Returns None on any unreadable/malformed layout; never raises."""
    git_path = repo_root / ".git"
    try:
        if git_path.is_dir():
            gitdir = git_path
        elif git_path.is_file():
            text = git_path.read_text(encoding="utf-8", errors="replace").strip()
            if not text.startswith("gitdir:"):
                return None
            target = text.split(":", 1)[1].strip()
            target_path = Path(target)
            gitdir = target_path if target_path.is_absolute() else (repo_root / target_path)
            gitdir = gitdir.resolve()
        else:
            return None
    except Exception:  # noqa: BLE001 — a health probe must never itself raise
        return None

    try:
        commondir_file = gitdir / "commondir"
        if commondir_file.is_file():
            common = commondir_file.read_text(encoding="utf-8", errors="replace").strip()
            common_path = Path(common)
            gitdir = (common_path if common_path.is_absolute() else (gitdir / common_path)).resolve()
    except Exception:  # noqa: BLE001
        return None

    return gitdir


def _strip_inline_comment(line: str) -> str:
    """Strip a trailing `#`/`;` comment from a config line.

    # Review: coordinator:overengineering-reviewer -- dropped a
    # quote-tracking state machine that treated `#`/`;` inside double quotes
    # as data, not a comment start. Unreachable for the one key this parser
    # reads (`core.untrackedCache`, whose value space is git's boolean
    # literals -- never a quoted string), and no fixture exercised the
    # quoted branch. A straight scan for the first `#`/`;` is what this
    # detector's actual input space needs."""
    for i, ch in enumerate(line):
        if ch in "#;":
            return line[:i]
    return line


def _config_has_untracked_cache(text: str) -> bool:
    """Text-level parse of a git config for `untrackedcache` under `[core]`.
    Deliberately hand-rolled rather than shelling out to `git config --get`
    -- see `cmd_git_perf_currency`'s NEGATIVE SPEC: this reads the same fact
    `apply()` writes, never re-derives it from the index.

    Mirrors real git config semantics on the axes that matter here:
      - a bare key with no `=` (`untrackedCache` alone on a line) is git's
        implicit-true form, same as `apply()`'s own `git config --get` read
        normalizes it.
      - `yes`/`on`/`1` are accepted spellings of true, normalized the same
        way `git config --get` would.
      - a trailing inline comment on the key/value or `[core]` header line
        is stripped before comparison.
      - LAST-WINS: git config resolves repeated keys (including across
        duplicate `[core]` blocks) to the final occurrence in the file, so
        this scans the whole file and keeps overwriting the result rather
        than returning on the first match -- returning on the first match
        would report `present` for a config whose FIRST `[core]` block says
        true and whose LATER one says false, a false-`present` that would
        silently leave that repo unswept forever (the opposite direction to
        every other divergence in this parser, which only ever reports a
        needless false-drift)."""
    in_core = False
    result = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if line.startswith("["):
            header = _strip_inline_comment(line).strip().lower()
            in_core = header.startswith("[core]") or header.startswith("[core ")
            continue
        if not in_core:
            continue
        content = _strip_inline_comment(line).strip()
        if not content:
            continue
        if "=" in content:
            k, _, v = content.partition("=")
            if k.strip().lower() == "untrackedcache":
                result = v.strip().lower() in ("true", "yes", "on", "1")
        elif content.strip().lower() == "untrackedcache":
            # Bare key, no `=` -- git's implicit-true form.
            result = True
    return result


def _git_perf_config_key_status(repo_root: Path) -> bool | None:
    """True/False the config key's value, or None when the config could not
    be read at all (missing gitdir, unreadable file) -- kept distinct from
    False ("read fine, key absent/differs") so the detector can report an
    unreadable repo rather than silently treating it as compliant or drifted
    the same way."""
    gitdir = _resolve_gitdir(repo_root)
    if gitdir is None:
        return None
    try:
        text = (gitdir / "config").read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return None
    return _config_has_untracked_cache(text)


def cmd_git_perf_currency(argv: list[str]) -> int:
    """Fleet currency of `core.untrackedCache`. See module docstring's
    "git-perf-currency" entry for the full contract (zero-spawn bare
    detector, in-process `--fix`, config-key-only negative spec)."""
    fix = False
    for arg in argv:
        if arg == "--fix":
            fix = True
        else:
            print(
                f"workday-start-health-probes: git-perf-currency: unrecognized argument {arg!r}",
                file=sys.stderr,
            )
            return 2

    _ensure_repo_root_on_path()
    from coordinator_core.install import git_perf_config

    if fix:
        try:
            report = git_perf_config.apply_fleet(_BIN_DIR)
        except Exception as exc:  # noqa: BLE001
            print(
                f"git-perf-currency --fix: COULD NOT RUN the fleet sweep: {exc}",
                file=sys.stderr,
            )
            return 1
        for line in report:
            print(line)
        if any(line.startswith("FAILED") for line in report):
            return 1
        return 0

    def _unwalkable(reason: str) -> int:
        # A WALK THAT COULD NOT RUN IS NOT A CURRENT FLEET. Exiting 0 here
        # would make a broken registry indistinguishable from a swept one --
        # the silence-reads-as-health shape `cmd_hook_currency`'s negative
        # spec names, and the one `apply_fleet` refuses by reporting an empty
        # fleet explicitly. Exit 1 emits the repair directive; it does not
        # block the ceremony, which is why this is safe on the boot path.
        print(
            f"GIT-PERF-CURRENCY PROBE: could not establish fleet currency -- {reason} "
            "-- Fix: workday-start-health-probes.py git-perf-currency --fix",
            file=sys.stderr,
        )
        return 1

    # Review: coordinator:overengineering-reviewer -- was a second,
    # hand-derived registry walk here (same helpers lookup, roots handling,
    # sorted iteration, classify, mirror-skip, missing-line wording as
    # apply_fleet's own, with nothing enforcing the two stayed in sync).
    # Extracted into git_perf_config.iter_fleet_worktrees, consumed by both
    # this detector and apply_fleet; only the per-worktree action differs.
    try:
        walk = git_perf_config.iter_fleet_worktrees(_BIN_DIR)
    except Exception as exc:  # noqa: BLE001 — a health probe must never itself raise
        return _unwalkable(f"registry walk raised: {exc}")
    if not walk.ok:
        if walk.reason == "helpers_unavailable":
            return _unwalkable("git_hook_install registry helpers unavailable")
        if walk.reason == "registry_error":
            return _unwalkable(f"could not read the repo registry: {walk.detail}")
        return _unwalkable("no registered repos -- that is not the same fact as 'every repo is current'")

    missing: list[tuple[str, str]] = []
    drifted: list[tuple[str, str, str]] = []
    for item in walk.items:
        kind, key, root = item[0], item[1], item[2]
        if kind == "missing":
            missing.append((key, root))
            continue
        if kind == "error":
            drifted.append((key, root, f"could not classify: {item[3]}"))
            continue
        status = _git_perf_config_key_status(Path(root))
        if status is None:
            drifted.append((key, root, "unreadable .git/config"))
        elif status is False:
            drifted.append((key, root, "core.untrackedCache not set"))

    if not missing and not drifted:
        return 0

    lines = [
        f"missing  {key} -> {root} (registry entry unreachable, not a git repo)"
        for key, root in missing
    ]
    lines += [f"drift    {key} -> {root} ({reason})" for key, root, reason in drifted]
    print(
        "GIT-PERF-CURRENCY PROBE: core.untrackedCache is not fleet-current -- "
        + "; ".join(lines)
        + " -- Fix: workday-start-health-probes.py git-perf-currency --fix",
        file=sys.stderr,
    )
    return 1


_SUBCOMMANDS = {
    "observer-sidecar-scan": cmd_observer_sidecar_scan,
    "claude-klabauter-bin-sentinel": cmd_claude_klabauter_bin_sentinel,
    "ceremony-hook": cmd_ceremony_hook,
    "mis-channelled-box": cmd_mis_channelled_box,
    "working-repo-registration": cmd_working_repo_registration,
    "hook-currency": cmd_hook_currency,
    "git-perf-currency": cmd_git_perf_currency,
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
