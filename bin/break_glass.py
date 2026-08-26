"""break_glass.py — Tier 1 operator-recovery diagnose-then-repair sweep for a
wedged coordinator install.

Design: DoE-claude `docs/research/2026-07-28-break-glass-recovery-design.md`.
Repo-placement note (deviation from that design doc's file table, judgment
call made at build time — see this module's own build dispatch report, not
repeated here as a changelog entry): the design doc's component table names
`coordinator/bin/break_glass.py` as a DoE-claude file. DoE-claude tracks ZERO
files under `coordinator/bin/` (`git ls-files coordinator/bin | wc -l` -> 0)
— DoE-claude's own CLAUDE.md states plainly that the executable bin surface
is claude-klabauter-resident, not DoE-claude-resident. This module therefore
lives in claude-klabauter, alongside `setup-verify.py` (one of the tools it
calls) and the `gen_settings_hooks` / `guard_foreign_platform_paths` /
`machine_resolver` modules it reuses — all of which are ALREADY claude-klabauter-side,
so placing Tier 1 here is following the evidence, not inventing a new split.
A thin `break-glass.cmd` mirror still lives at the DoE-claude repo root (per
AC-2, "whichever repo the operator opens first") and delegates to this file.

Purpose: run the 8-layer diagnose pass (AC-3) and peer-safe repair (AC-4),
report unconditionally (AC-5), stay honest about what it could not check or
fix (AC-7), and never depend on the very layer it is recovering (AC-1) — see
each check/repair function's own docstring for its specific dependency floor.
Every third-party coordinator import (gen_settings_hooks, machine_resolver,
guard_foreign_platform_paths, setup-verify subprocess) is wrapped in
try/except at the point of use, never at module top level, so a broken
plugin/venv cannot prevent this recovery tool itself from running.

No new `COORDINATOR_OVERRIDE_*` env var is introduced anywhere in this
module (AC-8 in the parent plan) — the injectable knobs below
(`--config-dir`, `--settings`, `MACHINE_LOCAL_REGISTRY_DIR`,
`COORDINATOR_SETTINGS_HOME`) are pre-existing seams the reused modules
already expose for testability, not new surface this module adds.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

GENERATES = []  # writes only ~/.claude/settings.json, its .settings-last-good.*.json backups, and machine-local registry.local.toml — all outside claude-klabauter's own tracked tree

_BIN_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BIN_DIR.parent.parent  # coordinator/bin -> coordinator -> repo root
if str(_REPO_ROOT) not in sys.path:
    # Self-resolve the repo root so `coordinator_core` imports work when this
    # file is invoked as a bare script (`python3 break_glass.py`, exactly how
    # break-glass.cmd's Tier 0 wrapper execs it) rather than via `python3 -m`
    # or from a cwd already at the repo root. Without this, every reused
    # coordinator_core import below silently degrades to its UNKNOWN
    # fallback for the WRONG reason (module not on sys.path, not a real
    # engine failure) on the exact invocation path an operator double-
    # clicking break-glass.cmd actually takes.
    sys.path.insert(0, str(_REPO_ROOT))

STATUS_OK = "OK"
STATUS_WARN = "WARN"
STATUS_BROKEN = "BROKEN"
STATUS_UNKNOWN = "UNKNOWN"

# Exit-code cap (AC-7): avoid colliding with shell-reserved 126/127/128+n.
_EXIT_CODE_CAP = 124


def _declare_write_best_effort(path: "Path | str") -> None:
    """DR-276: report `path` as an actually-written file to the session
    scope-touch recorder, when one is open (see `main()`'s
    `recording_declared_writes` wrap).

    Deferred import, wrapped in try/except at the point of use — same
    discipline as every other coordinator_core import in this module (module
    docstring): a broken plugin/venv must never prevent break-glass itself
    from completing a repair it already performed. A recording failure here
    is silently swallowed; it can only WITHHOLD the path from the session's
    own scope-touch claim, never corrupt the repair result already returned
    to the caller.
    """
    try:
        from coordinator_core.session.declared_writes import declare_write
    except Exception:  # noqa: BLE001 — defensive, see module docstring
        return
    try:
        declare_write(path)
    except Exception:  # noqa: BLE001 — never let recording fail a repair
        pass


@dataclass
class Finding:
    """One row of the diagnose-pass report table.

    `layer` is a short fixed name (`settings.json`, `kill-switch`, ...);
    `status` is one of the four STATUS_* constants; `detail` is the
    human-readable finding; `remediation` is the exact next action (a
    command, or None when `status` is OK and there is nothing to do).
    """

    layer: str
    status: str
    detail: str
    remediation: Optional[str] = None


@dataclass
class RepairOutcome:
    """Result of one repair attempt — never partial: either it ran and
    changed something (`applied=True`), no-opped because its own
    precondition was already clean (`applied=False`, no `error`), or failed
    (`error` set, `applied=False`) — see AC-5 (idempotence) and AC-7
    (honest repair failure)."""

    layer: str
    applied: bool
    detail: str
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Config-dir / settings-home resolution — pure, no external calls, testable
# via explicit args or env overlay (AC-6).
# ---------------------------------------------------------------------------


def resolve_config_dir(explicit: Optional[str] = None) -> Path:
    """Resolve the `~/.claude`-analog config dir holding `settings.json`.

    Order: --config-dir/explicit arg, then CLAUDE_CONFIG_DIR env, then
    CLAUDE_HOME env, then the platform home (Path.home(), which honours
    USERPROFILE on Windows) joined with `.claude`. Never assumes a POSIX
    HOME — this is the exact class of bug (`bare_home_or_chain`) this
    module must not reproduce, since it is the tool run when that class of
    bug has already struck.
    """
    if explicit:
        return Path(explicit)
    env_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    if env_dir:
        return Path(env_dir)
    claude_home = os.environ.get("CLAUDE_HOME")
    if claude_home:
        return Path(claude_home) / ".claude"
    return Path.home() / ".claude"


# ---------------------------------------------------------------------------
# Check 1 — settings.json presence/validity/platform-shape
# ---------------------------------------------------------------------------


def check_settings_json(
    config_dir: Path,
    settings_path: Optional[Path] = None,
    host_is_windows: Optional[bool] = None,
) -> Finding:
    """Layer 1 (AC-3 #1). Missing -> BROKEN. Invalid JSON -> BROKEN with the
    parse error. Valid -> classify every `command` string's hook paths via
    `guard_foreign_platform_paths.detect_foreign_platform_paths` (claude-klabauter's
    own module — no DoE-side import needed; this check's classifier is
    already resident in this repo, confirming the build-sequence step 1
    reusability check the design doc calls for).

    `host_is_windows` (default: `detect_foreign_platform_paths`'s own
    `os.name == "nt"` ambient detection) exists purely for AC-6 testability
    — mirrors the parameter the underlying detector already exposes one
    layer down. Production callers (`run_diagnose`/`main()`) never pass it,
    so a live run always classifies against the machine it is actually
    running on; only tests pin a platform explicitly.
    """
    path = settings_path or (config_dir / "settings.json")
    if not path.is_file():
        return Finding(
            "settings.json", STATUS_BROKEN, f"missing: {path}",
            "Regenerate via `break_glass.py --repair` (calls gen_settings_hooks.generate()), "
            "or re-run the coordinator installer.",
        )
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        return Finding(
            "settings.json", STATUS_BROKEN, f"invalid JSON at {path}: {exc}",
            "Restore from <settings-home>/.settings-last-good.*.json, or delete and "
            "regenerate via `break_glass.py --repair`.",
        )

    try:
        from coordinator_core.ops.session.guard_foreign_platform_paths import (
            detect_foreign_platform_paths,
        )
    except Exception as exc:  # noqa: BLE001 — defensive, see module docstring
        return Finding(
            "settings.json", STATUS_UNKNOWN,
            f"parsed OK but foreign-platform-path classifier unimportable: {exc}",
            None,
        )

    findings = detect_foreign_platform_paths(data, host_is_windows=host_is_windows)
    if findings:
        pointers = ", ".join(f.pointer for f in findings[:5])
        more = f" (+{len(findings) - 5} more)" if len(findings) > 5 else ""
        return Finding(
            "settings.json", STATUS_BROKEN,
            f"{len(findings)} foreign-platform-shaped hook path(s): {pointers}{more}",
            "Hand-fix the named path(s) to this machine's own coordinator clone root, "
            "or regenerate via `break_glass.py --repair`.",
        )
    return Finding("settings.json", STATUS_OK, f"present, valid JSON, no foreign-platform paths: {path}")


def repair_settings_json(
    config_dir: Path, settings_path: Optional[Path] = None, diagnose: Optional[Finding] = None,
) -> RepairOutcome:
    """Peer-safe repair (AC-4): regenerate settings.json in place from
    hooks.json via `gen_settings_hooks.generate()` — already sync-safe by
    design (writes only the local file, never touches git). Before
    overwriting, copies the existing file to
    `<settings-home>/.settings-last-good.<timestamp>.json` — the
    last-good mechanism the parent plan already names as present-but-unused;
    this is its first read+write consumer.

    Idempotent (AC-5): re-checks `check_settings_json` itself first and
    no-ops if already OK.
    """
    finding = diagnose or check_settings_json(config_dir, settings_path)
    if finding.status == STATUS_OK:
        return RepairOutcome("settings.json", applied=False, detail="already OK, no repair needed")

    path = settings_path or (config_dir / "settings.json")
    try:
        from coordinator_core.install.gen_settings_hooks import generate
        from coordinator_core._settings_home import settings_home
    except Exception as exc:  # noqa: BLE001
        return RepairOutcome(
            "settings.json", applied=False,
            detail="repair unavailable", error=f"gen_settings_hooks unimportable: {exc}",
        )

    try:
        if path.is_file():
            backup_dir = settings_home()
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup = backup_dir / f".settings-last-good.{int(time.time())}.json"
            backup.write_bytes(path.read_bytes())
            _declare_write_best_effort(backup)
        status = generate(out_path=str(path))
    except Exception as exc:  # noqa: BLE001 — repair failure must be caught, not crash the whole run
        return RepairOutcome(
            "settings.json", applied=False, detail="regeneration raised",
            error=f"{exc}\n  manual fix: cd <coordinator-root> && python3 -m "
            "coordinator_core.install.gen_settings_hooks --out "
            f"{path}",
        )
    if status.startswith("skipped"):
        # generate()'s own preconditions (positive marker, resolvable
        # coordinator root, plugin-delivery double-fire guard, ...) declined
        # to write anything -- this is a graceful no-op by that function's
        # OWN contract, not a crash, but it means THIS layer is still
        # unrepaired: report applied=False so the caller's exit-code count
        # (and a re-diagnose) correctly still see it BROKEN, rather than
        # reporting a false "fixed" against a file that was never touched.
        return RepairOutcome(
            "settings.json", applied=False,
            detail=f"generate() declined: {status} — settings.json left untouched",
            error=(
                f"generate() could not regenerate: {status}. manual fix: resolve the "
                "blocking precondition named above (e.g. create the positive marker, "
                "set COORDINATOR_ROOT, or check the coordinator clone is present), "
                "then re-run break_glass.py --repair."
            ),
        )
    _declare_write_best_effort(path)
    return RepairOutcome("settings.json", applied=True, detail=f"regenerated: {status}")


# ---------------------------------------------------------------------------
# Check 2 — kill-switch marker
# ---------------------------------------------------------------------------


def check_kill_switch(config_dir: Path) -> Finding:
    """Layer 2 (AC-3 #2). Report whether `.coordinator-hooks-disabled` is armed.

    An armed marker is reported WARN-with-context, NEVER `BROKEN`, and is
    never auto-repaired — see `repair_kill_switch` for why. It suppresses
    settings.json hook GENERATION only; it does not stop hooks from firing.
    Plugin-side delivery (`coordinator/hooks/hooks.json`, resolved via
    `--plugin-dir`) is a wholly independent path, and on a healthy install it
    is the live one. Reporting an armed marker as BROKEN on a machine whose
    hooks are all firing tells a wedged operator to go break something that
    was working -- the diagnostic equivalent of a deny message that
    misdescribes what tripped it.
    """
    marker = config_dir / ".coordinator-hooks-disabled"
    if not marker.is_file():
        return Finding("kill-switch", STATUS_OK, f"no kill-switch marker at {marker}")
    try:
        arm_note = marker.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        arm_note = "(unreadable)"
    return Finding(
        "kill-switch", STATUS_WARN,
        f"armed: {marker}" + (f" — {arm_note}" if arm_note else ""),
        "Armed markers are usually CORRECT and are left alone by --repair. This "
        "suppresses settings.json hook generation only; plugin-side delivery is "
        "independent and unaffected. Verify hooks are genuinely not firing "
        "before touching this, and read the marker's own stated disarm "
        "condition first -- on an install where plugin-side delivery is live, "
        "disarming regenerates a second copy of every hook rather than "
        "restoring anything.",
    )


def repair_kill_switch(config_dir: Path, diagnose: Optional[Finding] = None) -> RepairOutcome:
    """REPORT-ONLY by construction. Never deletes the marker.

    An earlier revision deleted it as a "repair", which is the one thing this
    function must not do. Three independent reasons, any one sufficient:

    1. The marker is deliberately non-self-disarming (the engine refuses to
       let it disarm itself). A recovery tool that deletes it on the operator's
       behalf is that same self-disarm wearing a different hat, and it fires in
       exactly the situation where the operator is least able to evaluate it.
    2. Deleting it does not restore hooks. It gates settings.json hook
       GENERATION, not hook DELIVERY -- plugin-side delivery is a separate,
       independent path. On an install where plugin-side is live, disarming
       starts emitting a duplicate copy of every hook alongside the working
       ones; the failure it produces is double-firing, not recovery.
    3. It is a deliberate operator decision carrying its own stated rationale
       and disarm condition, in the marker's own body. Machine-deleting a
       human's recorded decision, unprompted, on a machine already in trouble,
       is not a repair -- it is the destruction of the note explaining why
       things are the way they are.

    Deleting it stays available to the operator as a one-line manual action,
    which is the correct altitude for an irreversible, judgement-dependent step.
    """
    finding = diagnose or check_kill_switch(config_dir)
    if finding.status == STATUS_OK:
        return RepairOutcome("kill-switch", applied=False, detail="no marker present, no repair needed")

    marker = config_dir / ".coordinator-hooks-disabled"
    return RepairOutcome(
        "kill-switch", applied=False,
        detail=(
            f"left armed deliberately: {marker} — not auto-repairable. If you have "
            "confirmed hooks are genuinely not firing AND that plugin-side delivery "
            "is absent, delete it by hand."
        ),
    )


# ---------------------------------------------------------------------------
# Check 3 — launcher staleness (report-only; regen phase not yet built)
# ---------------------------------------------------------------------------


def check_launcher_staleness(config_dir: Path) -> Finding:
    """Layer 3 (AC-3 #3). Report-only per the design doc: the C9 launcher
    regeneration phase this check would eventually call does not exist yet
    as of this build. Rather than fabricate a staleness comparison against a
    template checksum this module has no access to, this is honestly
    reported UNKNOWN with the reason — never silently coerced to OK.

    # TODO(C9): call substrate.py's launcher-regen phase here once it
    # exists, replacing this UNKNOWN stub with a real stale/total count.
    """
    launcher_dir = config_dir / "bin"
    if not launcher_dir.is_dir():
        return Finding(
            "launcher-staleness", STATUS_UNKNOWN,
            f"{launcher_dir} does not exist — nothing to compare",
            None,
        )
    return Finding(
        "launcher-staleness", STATUS_UNKNOWN,
        "no launcher-regen phase exists yet to check against (C9 not yet built) — "
        f"{launcher_dir} present but not compared",
        None,
    )


# ---------------------------------------------------------------------------
# Check 4 — home resolution chain
# ---------------------------------------------------------------------------


_WIN_DRIVE_ABS_RE = re.compile(r"^[A-Za-z]:[\\/]")
_POSIX_ABS_RE = re.compile(r"^/[^/]")


def _looks_absolute(value: str) -> bool:
    """True for a POSIX-absolute path (`Path.is_absolute()`, or explicitly a
    leading `/segment`) OR a Windows drive-absolute path (`C:\\...`/`C:/...`).
    `Path.is_absolute()` alone is platform-dependent — a Windows-shaped
    string is NOT absolute under a POSIX-flavoured `Path`, and a POSIX-shaped
    string is NOT absolute under a Windows-flavoured `Path` (no drive
    anchor) — so a test running on macOS asserting a Windows `USERPROFILE`
    value, or a test running on Windows asserting a POSIX `HOME` value, must
    not spuriously WARN either direction. Both explicit regexes exist for
    exactly this reason — `Path.is_absolute()` alone only covers whichever
    platform this process happens to be running on.
    """
    return (
        Path(value).is_absolute()
        or bool(_WIN_DRIVE_ABS_RE.match(value))
        or bool(_POSIX_ABS_RE.match(value))
    )


def check_home_resolution(env: Optional[dict] = None) -> Finding:
    """Layer 4 (AC-3 #4). Print the full CLAUDE_HOME/HOME/USERPROFILE/
    Path.home() resolution chain and which one fired. `env` param (defaults
    to os.environ) exists purely for AC-6 env-injection testability."""
    e = env if env is not None else os.environ
    chain = [("CLAUDE_HOME", e.get("CLAUDE_HOME")), ("HOME", e.get("HOME")), ("USERPROFILE", e.get("USERPROFILE"))]
    winner_var, winner_val = None, None
    for var, val in chain:
        if val:
            winner_var, winner_val = var, val
            break
    if winner_val is None:
        winner_var, winner_val = "Path.home()", str(Path.home())

    detail = f"chain={chain}, winner={winner_var}={winner_val!r}"
    if not winner_val or not _looks_absolute(winner_val):
        return Finding(
            "home-resolution", STATUS_WARN, detail,
            f"{winner_var} resolved to a relative/empty path {winner_val!r} — every "
            "derived target anchors at cwd instead of failing loud.",
        )
    return Finding("home-resolution", STATUS_OK, detail)


# ---------------------------------------------------------------------------
# Check 5 — Defender exclusions (Windows only)
# ---------------------------------------------------------------------------


def check_defender_exclusions(is_windows: Optional[bool] = None, timeout: float = 3.0) -> Finding:
    """Layer 5 (AC-3 #5). UNKNOWN off-Windows by design (never silently
    skipped). On Windows, shells to `powershell.exe -Command "Get-MpPreference
    | Select ExclusionProcess"`; timeout so a hung PowerShell cannot hang
    break-glass itself (AC-7/"Critical details")."""
    windows = os.name == "nt" if is_windows is None else is_windows
    if not windows:
        return Finding("defender-exclusions", STATUS_UNKNOWN, "not Windows — Defender check does not apply", None)

    from shutil import which

    ps = which("powershell.exe") or which("powershell")
    if not ps:
        return Finding("defender-exclusions", STATUS_UNKNOWN, "powershell.exe not found on PATH", None)

    try:
        from coordinator_core.win_portability import no_console_creationflags

        proc = subprocess.run(
            [ps, "-NoProfile", "-Command", "Get-MpPreference | Select-Object -ExpandProperty ExclusionProcess"],
            capture_output=True, text=True, timeout=timeout,
            **no_console_creationflags(),
        )
    except subprocess.TimeoutExpired:
        return Finding("defender-exclusions", STATUS_UNKNOWN, f"powershell.exe timed out after {timeout}s", None)
    except OSError as exc:
        return Finding("defender-exclusions", STATUS_UNKNOWN, f"could not run powershell.exe: {exc}", None)

    out = (proc.stdout or "")
    missing = [name for name in ("bash.exe", "git.exe", "python.exe") if name.lower() not in out.lower()]
    if missing:
        return Finding(
            "defender-exclusions", STATUS_WARN, f"missing from ExclusionProcess: {', '.join(missing)}",
            "Add-MpPreference -ExclusionProcess " + ",".join(missing) + "  (run elevated; never auto-applied)",
        )
    return Finding("defender-exclusions", STATUS_OK, "bash.exe/git.exe/python.exe all excluded")


# ---------------------------------------------------------------------------
# Check 6 — plugin registration
# ---------------------------------------------------------------------------


def check_plugin_registered(timeout: float = 5.0) -> Finding:
    """Layer 6 (AC-3 #6). Reuses `setup-verify.py check-plugin-registered`
    as a subprocess if locatable. That subcommand's contract requires
    `--plugin`/`--marketplace` identity args break-glass has no safe
    generic default for (a wrong guess would report a false PASS/FAIL for
    a plugin that isn't coordinator) — rather than guess, this reports
    UNKNOWN with the exact command an operator should run directly, which
    is the AC-7-mandated honest-failure shape, not a skipped check."""
    setup_verify = _BIN_DIR / "setup-verify.py"
    if not setup_verify.is_file():
        return Finding("plugin-registered", STATUS_UNKNOWN, f"setup-verify.py not found at {setup_verify}", None)
    return Finding(
        "plugin-registered", STATUS_UNKNOWN,
        "requires --plugin/--marketplace identity break-glass has no safe default for",
        f"Run directly: python3 {setup_verify} check-plugin-registered "
        "--plugin coordinator --marketplace <your-marketplace>",
    )


# ---------------------------------------------------------------------------
# Check 7 — registry pollution
# ---------------------------------------------------------------------------


_TMP_SHAPE_MARKERS = ("pytest-of-", "/tmp/", "\\AppData\\Local\\Temp\\", "\\Temp\\", "T:\\pytest")


def _is_tmp_shaped(value: str) -> bool:
    if any(marker in value for marker in _TMP_SHAPE_MARKERS):
        return True
    # bare tmp<random> path segment, either separator style
    for sep in ("/", "\\"):
        for seg in value.split(sep):
            if seg.startswith("tmp") and len(seg) > 3 and seg[3:].isalnum():
                return True
    return False


def check_registry_pollution() -> Finding:
    """Layer 7 (AC-3 #7). Scans the flattened machine-local registry
    (`registry.local.toml`, the untracked/local file — `registry.toml` is
    checked too but reported separately, never auto-repaired, since it may
    be the tracked file) for values shaped like a tmp-path leak."""
    try:
        from coordinator_core.machine_resolver import registry_dir, load_flat_registry_file
    except Exception as exc:  # noqa: BLE001
        return Finding("registry-pollution", STATUS_UNKNOWN, f"machine_resolver unimportable: {exc}", None)

    reg_dir = registry_dir()
    polluted = []
    for fname in ("registry.local.toml", "registry.toml"):
        path = reg_dir / fname
        if not path.is_file():
            continue
        flat = load_flat_registry_file(path)
        for key, val in flat.items():
            if isinstance(val, str) and _is_tmp_shaped(val):
                polluted.append((fname, key, val))

    if not polluted:
        return Finding("registry-pollution", STATUS_OK, f"no tmp-path-shaped values in {reg_dir}")

    detail = "; ".join(f"{f}:{k}={v!r}" for f, k, v in polluted[:5])
    return Finding(
        "registry-pollution", STATUS_BROKEN, detail,
        "`break_glass.py --repair` removes offending keys from registry.local.toml only "
        "(registry.toml is left for manual review, never auto-stripped).",
    )


def repair_registry_pollution(diagnose: Optional[Finding] = None) -> RepairOutcome:
    """Peer-safe repair (AC-4): strips offending keys from the LOCAL
    `registry.local.toml` only — `registry.toml` (potentially tracked/
    shared) is never touched by this repair, listed in the report instead."""
    finding = diagnose or check_registry_pollution()
    if finding.status == STATUS_OK:
        return RepairOutcome("registry-pollution", applied=False, detail="no pollution found, no repair needed")

    try:
        from coordinator_core.machine_resolver import registry_dir
    except Exception as exc:  # noqa: BLE001
        return RepairOutcome("registry-pollution", applied=False, detail="repair unavailable", error=str(exc))

    local_path = registry_dir() / "registry.local.toml"
    if not local_path.is_file():
        return RepairOutcome(
            "registry-pollution", applied=False,
            detail="pollution is in registry.toml (tracked) — not auto-repaired, review by hand",
        )

    try:
        text = local_path.read_text(encoding="utf-8")
    except OSError as exc:
        return RepairOutcome("registry-pollution", applied=False, detail="read failed", error=str(exc))

    kept_lines = []
    removed = []
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if "=" in stripped and not stripped.startswith("#") and not stripped.startswith("["):
            _, _, rhs = stripped.partition("=")
            if _is_tmp_shaped(rhs.strip().strip('"')):
                removed.append(stripped)
                continue
        kept_lines.append(line)

    if not removed:
        return RepairOutcome(
            "registry-pollution", applied=False,
            detail="pollution found by TOML-table read but not by line-level rewrite — nested-table "
            "value, review registry.local.toml by hand",
        )

    try:
        local_path.write_text("".join(kept_lines), encoding="utf-8", newline="\n")
    except OSError as exc:
        return RepairOutcome(
            "registry-pollution", applied=False, detail="write failed", error=str(exc),
        )
    _declare_write_best_effort(local_path)
    return RepairOutcome("registry-pollution", applied=True, detail=f"removed {len(removed)} line(s): {removed}")


# ---------------------------------------------------------------------------
# Check 8 — ~/.claude sync divergence
# ---------------------------------------------------------------------------


def check_claude_sync(config_dir: Path, timeout: float = 5.0) -> Finding:
    """Layer 8 (AC-3 #8). `git status --porcelain` + ahead/behind counts
    inside `config_dir`, if it is a git repo at all. Also reports whether
    `settings.json`/`.doe-root`/`.coordinator-hooks-disabled` appear in
    tracked `git status` output — their presence is itself a finding (the
    0bb6812 untracking fix regressed if any of those three appear)."""
    if not (config_dir / ".git").exists():
        return Finding("claude-sync", STATUS_UNKNOWN, f"{config_dir} is not a git repo", None)

    def _run(args: List[str]) -> Optional[str]:
        try:
            proc = subprocess.run(
                ["git", "-C", str(config_dir), *args],
                capture_output=True, text=True, timeout=timeout,
            )
        except (subprocess.TimeoutExpired, OSError):
            return None
        return proc.stdout if proc.returncode == 0 else None

    status_out = _run(["status", "--porcelain"])
    if status_out is None:
        return Finding("claude-sync", STATUS_UNKNOWN, "git status failed or timed out", None)

    regressed = [name for name in ("settings.json", ".doe-root", ".coordinator-hooks-disabled") if name in status_out]
    if regressed:
        return Finding(
            "claude-sync", STATUS_BROKEN,
            f"{', '.join(regressed)} appear in `git status` — the 0bb6812 untracking fix regressed",
            f"Run `git -C {config_dir} status` and `git rm --cached <file>` for each regressed file "
            "(never `git add`/commit these back).",
        )

    ahead_behind = _run(["rev-list", "--left-right", "--count", "HEAD...@{u}"])
    dirty = bool(status_out.strip())
    detail = f"dirty={dirty}, ahead/behind={ahead_behind.strip() if ahead_behind else 'no upstream/unknown'}"
    if dirty or (ahead_behind and ahead_behind.strip() not in ("0\t0", "")):
        return Finding(
            "claude-sync", STATUS_WARN, detail,
            f"Inspect before moving: `git -C {config_dir} status` / `git -C {config_dir} diff` / "
            f"`git -C {config_dir} log <range>` — never auto pull/push/merge here.",
        )
    return Finding("claude-sync", STATUS_OK, detail)


# ---------------------------------------------------------------------------
# Orchestration — diagnose pass (complete, read-only) then optional repair.
# ---------------------------------------------------------------------------

_CHECK_ORDER: List[Callable[[Path], Finding]] = []


def run_diagnose(config_dir: Path) -> List[Finding]:
    """Run all 8 checks, in AC-3's fixed order, complete before any repair
    runs (so a later repair can never mask an earlier finding)."""
    return [
        check_settings_json(config_dir),
        check_kill_switch(config_dir),
        check_launcher_staleness(config_dir),
        check_home_resolution(),
        check_defender_exclusions(),
        check_plugin_registered(),
        check_registry_pollution(),
        check_claude_sync(config_dir),
    ]


def run_repair(config_dir: Path, findings: List[Finding]) -> List[RepairOutcome]:
    """Run the three peer-safe repair functions (AC-4), each gated on its
    own idempotent precondition (AC-5). Layers 3/5/6/8 have no auto-repair
    (see AC-4's explicit report-only list) and are skipped here entirely —
    not silently, the caller's report already carries their finding."""
    by_layer = {f.layer: f for f in findings}
    # Kill-switch repair runs BEFORE settings.json regen deliberately: an
    # armed kill-switch is one of `gen_settings_hooks.generate()`'s own
    # preconditions, so clearing it first gives the settings.json repair
    # the best chance of actually succeeding on a real machine (rather than
    # both being diagnosed independently but repaired in an order where the
    # first blocks the second).
    return [
        repair_kill_switch(config_dir, diagnose=by_layer.get("kill-switch")),
        repair_settings_json(config_dir, diagnose=by_layer.get("settings.json")),
        repair_registry_pollution(diagnose=by_layer.get("registry-pollution")),
    ]


def format_report(findings: List[Finding]) -> str:
    """Fixed-width table, one row per layer — printed unconditionally as the
    first thing break-glass does (AC-3), even on an all-OK run (AC-5)."""
    lines = [f"{'LAYER':<22} {'STATUS':<8} DETAIL", "-" * 90]
    for f in findings:
        lines.append(f"{f.layer:<22} {f.status:<8} {f.detail}")
        if f.remediation:
            lines.append(f"{'':<22} {'':<8} -> {f.remediation}")
    return "\n".join(lines)


def format_repair_report(outcomes: List[RepairOutcome]) -> str:
    lines = ["", "REPAIR", "-" * 90]
    for o in outcomes:
        if o.error:
            lines.append(f"{o.layer:<22} REPAIR FAILED — {o.error}")
        elif o.applied:
            lines.append(f"{o.layer:<22} repaired — {o.detail}")
        else:
            lines.append(f"{o.layer:<22} no-op — {o.detail}")
    return "\n".join(lines)


def _exit_code(findings: List[Finding], repairs: List[RepairOutcome]) -> int:
    """Count of BROKEN findings not resolved by a successful repair, plus
    every REPAIR FAILED — capped at 124 (AC-7)."""
    repaired_layers = {o.layer for o in repairs if o.applied}
    failed_repairs = sum(1 for o in repairs if o.error)
    still_broken = sum(1 for f in findings if f.status == STATUS_BROKEN and f.layer not in repaired_layers)
    return min(still_broken + failed_repairs, _EXIT_CODE_CAP)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="break_glass.py", description=__doc__.splitlines()[0])
    parser.add_argument("--config-dir", default=None, help="Override the ~/.claude-analog config dir (tests).")
    parser.add_argument("--settings", default=None, help="Override the settings.json path directly (tests).")
    parser.add_argument("--report-only", action="store_true", help="Skip all repair steps.")
    parser.add_argument("--verbose", action="store_true", help="Print resolver internals.")
    args = parser.parse_args(argv)

    config_dir = resolve_config_dir(args.config_dir)
    settings_path = Path(args.settings) if args.settings else None

    if args.verbose:
        print(f"[verbose] config_dir={config_dir}", file=sys.stderr)
        print(f"[verbose] settings_path={settings_path or config_dir / 'settings.json'}", file=sys.stderr)

    findings = run_diagnose(config_dir)
    # settings.json check honours an explicit --settings override; re-run
    # just that one check with the override rather than threading it through
    # every check's signature (only this layer needs it).
    if settings_path:
        findings[0] = check_settings_json(config_dir, settings_path)

    print(format_report(findings))

    if args.report_only:
        broken = sum(1 for f in findings if f.status == STATUS_BROKEN)
        print(f"\n--report-only: no repairs attempted. {broken} layer(s) reported BROKEN.")
        return min(broken, _EXIT_CODE_CAP)

    try:
        from coordinator_core.cli_entry import recording_declared_writes
    except Exception:  # noqa: BLE001 — defensive, see module docstring
        repairs = run_repair(config_dir, findings)
    else:
        with recording_declared_writes():
            repairs = run_repair(config_dir, findings)
    print(format_repair_report(repairs))

    code = _exit_code(findings, repairs)
    if code == 0:
        print(f"\nAll {len(findings)} layers OK. No repairs were needed or performed. Safe to re-run any time.")
    else:
        print(f"\n{code} layer(s) still need attention — see above.")
    return code


if __name__ == "__main__":
    sys.exit(main())
