# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""workweek-complete-drift-guards.py — /workweek-complete advisory + gate
dispatch logic, ported out of DoE-claude's coordinator/commands/workweek-complete.md
(M3 chunk WWC-3, 2026-07-23 bash-extirpation campaign).

Purpose: the DoE ceremony file previously carried the *imperative logic*
(loops, conditionals, rc-branch ladders) around a handful of already-existing
Claude-klabauter CLIs — this file is that logic's new home, callable as a single
subcommand-shaped CLI so the ceremony file can shrink each step to a thin
one-line invocation instead of a bespoke bash block.

This CLI does NOT reimplement any guard's detection logic — every subcommand
below is a thin dispatcher over a sibling `coordinator/bin/*` CLI (or, for
cve-recheck, over `git` directly) plus the control flow (existence checks, rc
branching, skip/dispatch decisions, report-and-offer messaging) that decides
WHETHER and HOW to report the sibling's result. Self-contained and
self-resolving (Path(__file__)-relative); does not depend on cwd for locating
siblings, only for the git-scoped cve-recheck subcommand, which operates
against the current repo by design (it answers "does THIS repo need this?").

Subcommands:
    description-length          — informational advisory, never blocks.
    enabled-plugins              — informational advisory, never blocks.
                                    Skips cleanly when .claude/settings.json
                                    is absent in the target repo.
    cve-recheck                  — change-aware: skips when no tracked
                                    dependency manifest exists, or none
                                    changed in the last 14 days; otherwise
                                    reports the changed set for the EM to
                                    dispatch dep-cve-auditor against.
    schema-drift-gate            — BLOCKING gate. Three-way exit-code branch
                                    (0 PASS / 1 BLOCK / 2 ERROR) over the
                                    sibling schema-drift-gate CLI — a release
                                    gate must never conflate "ran and found
                                    drift" with "could not run".
    pcli-drift-gate               — BLOCKING gate. Same three-way exit-code
                                    branch (0 PASS / 1 FAIL / 2 ERROR) over
                                    the sibling check-pcli-drift-gate CLI —
                                    dispatch_feed-vs-live-Workflow-API drift,
                                    14-day capture staleness, and C7 source-
                                    hash drift on subagent-catering-
                                    resolution.json.
    console-flash-guard          — thin dispatcher over
                                    verify-no-console-flash.py.
    multi-event-hook-guard       — thin dispatcher over
                                    check-multi-event-hook-hardcoded-event.py.

Exit-code contract per subcommand is documented in its own function docstring
below — they are NOT uniform (schema-drift-gate propagates a real block
signal; the advisory subcommands always exit 0 by design, per DoE doctrine
that advisories never block merge).

Spec backlink: DoE-claude coordinator/commands/workweek-complete.md
    §§ Step 4d (description-length), Step 4f (enabledPlugins drift),
    Step 4h (CVE recheck), Step 4k (vendored-schema drift gate),
    Step 6 (console-flash guard + multi-event-hook guard). ShellCheck sweep
    (formerly this file's `shellcheck-sweep` subcommand) was removed
    2026-08-16 — see state/kill-ledger.md K-102; the DoE ceremony's Step 6
    hand invocation of it is now dead and should be dropped from
    coordinator/commands/workweek-complete.md.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

_BIN_DIR = os.path.dirname(os.path.abspath(__file__))

# Tracked dependency-manifest globs — subset of dep-cve-auditor's own
# detection table (kept in sync manually; dep-cve-auditor is the source of
# truth for the full list, this is only the "does this repo have ANY dep
# surface at all" pre-filter).
_CVE_MANIFESTS = (
    "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "requirements.txt", "requirements.lock", "pyproject.toml", "uv.lock",
    "Cargo.toml", "Cargo.lock", "go.mod", "go.sum",
)

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _run(cmd: list[str], cwd: str | None = None) -> tuple[int, str]:
    """Run cmd, merging stdout+stderr (mirrors the bash `2>&1` capture the
    ported logic used), and return (rc, combined_output)."""
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=_NO_WINDOW,
    )
    return proc.returncode, proc.stdout or ""


def _sibling(name: str) -> str:
    return os.path.join(_BIN_DIR, name)


# ---------------------------------------------------------------------------
# Step 4d: description-length advisory
# ---------------------------------------------------------------------------

def cmd_description_length(_args: argparse.Namespace) -> int:
    """Informational — never blocks. Always exits 0; the rc of the underlying
    check is reported IN the banner text, not propagated, matching the DoE
    ceremony's own `set +e` / never-fail-the-step framing."""
    script = _sibling("check-description-length.py")
    rc, out = _run([sys.executable, script])
    print("---")
    print(f"description-length advisory (rc={rc}):")
    print(out)
    print("---")
    return 0


# ---------------------------------------------------------------------------
# Step 4f: enabledPlugins drift audit advisory
# ---------------------------------------------------------------------------

def cmd_enabled_plugins(args: argparse.Namespace) -> int:
    """Per-repo advisory — never blocks. Skips cleanly (rc=0, no dispatch)
    when .claude/settings.json is absent from the target repo root."""
    repo_root = args.repo_root or os.getcwd()
    settings_path = os.path.join(repo_root, ".claude", "settings.json")
    if os.path.isfile(settings_path):
        script = _sibling("audit-enabled-plugins.py")
        rc, out = _run([sys.executable, script], cwd=repo_root)
    else:
        rc, out = 0, "(no .claude/settings.json — skipped)"
    print("---")
    print(f"enabledPlugins drift advisory (rc={rc}):")
    print(out)
    print("---")
    return 0


# ---------------------------------------------------------------------------
# Step 4h: CVE recheck (change-aware)
# ---------------------------------------------------------------------------

def cmd_cve_recheck(args: argparse.Namespace) -> int:
    """Change-aware — dispatch is a *report*, not an in-process auditor run
    (dep-cve-auditor is a Sonnet worker the EM dispatches on the dispatch
    verdict below). Always exits 0 — advisory, never blocks merge; the
    skip-vs-dispatch distinction is carried in stdout for the EM to read.
    14-day window (not 7): covers slipped workweeks — a double-audit is a
    cheap no-op report, a missed audit is a silently-unscanned CVE."""
    repo_root = args.repo_root or os.getcwd()

    rc, out = _run(["git", "ls-files", "--", *_CVE_MANIFESTS], cwd=repo_root)
    present = [line for line in out.splitlines() if line.strip()]
    if not present:
        print("CVE recheck: no tracked dependency manifests in this repo — skipped.")
        return 0

    since = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%d")
    rc, out = _run(
        ["git", "log", f"--since={since}", "--name-only", "--pretty=format:", "--", *_CVE_MANIFESTS],
        cwd=repo_root,
    )
    changed = sorted({line.strip() for line in out.splitlines() if line.strip()})
    if not changed:
        print("CVE recheck: dependency manifests unchanged in the last 14 days — skipped.")
        return 0

    print("CVE recheck: manifests changed this week — dispatching dep-cve-auditor:")
    for path in changed:
        print(f"  - {path}")
    return 0


# ---------------------------------------------------------------------------
# Step 4k: vendored-schema drift gate (BLOCKING)
# ---------------------------------------------------------------------------

def cmd_schema_drift_gate(_args: argparse.Namespace) -> int:
    """Blocking gate. Three-way exit-code branch — a release gate must never
    conflate "ran and found drift" with "could not run":
        0 PASS  — schemas MATCH, or the gate fails open on
                  INDETERMINATE/UNRESOLVED (see sibling CLI's own stderr).
        1 BLOCK — drift positively observed; halt the release.
        2 ERROR — the gate could not run at all; halt and surface, NOT a pass.
        other   — unexpected rc from the sibling CLI; treated as ERROR (2).
    """
    script = _sibling("schema-drift-gate.py")
    if not os.path.isfile(script):
        print(f"ERROR: schema-drift-gate CLI not found at {script} — halt and surface", file=sys.stderr)
        return 2
    rc, out = _run([sys.executable, script])
    if out:
        print(out, end="" if out.endswith("\n") else "\n")
    if rc == 0:
        return 0
    if rc == 1:
        print("BLOCK: vendored-schema drift observed (see above) — halt the release, reconcile, re-run", file=sys.stderr)
        return 1
    if rc == 2:
        print("ERROR: schema-drift-gate could not run — halt and surface; this is NOT a pass", file=sys.stderr)
        return 2
    print(f"ERROR: schema-drift-gate returned unexpected rc={rc} — halt and surface", file=sys.stderr)
    return 2


# ---------------------------------------------------------------------------
# pcli-04 drift gate (BLOCKING)
# ---------------------------------------------------------------------------

def cmd_pcli_drift_gate(_args: argparse.Namespace) -> int:
    """Blocking gate. Three-way exit-code branch — same shape as
    cmd_schema_drift_gate above, a release gate must never conflate "ran and
    found drift" with "could not run":
        0 PASS  — dispatch_feed-vs-capture, staleness, and C7 hash legs all
                  clean (see sibling CLI's own stdout).
        1 FAIL  — at least one leg fired; halt the release.
        2 ERROR — the gate could not run at all; halt and surface, NOT a pass.
        other   — unexpected rc from the sibling CLI; treated as ERROR (2).
    """
    script = _sibling("check-pcli-drift-gate.py")
    if not os.path.isfile(script):
        print(f"ERROR: check-pcli-drift-gate CLI not found at {script} — halt and surface", file=sys.stderr)
        return 2
    rc, out = _run([sys.executable, script])
    if out:
        print(out, end="" if out.endswith("\n") else "\n")
    if rc == 0:
        return 0
    if rc == 1:
        print("BLOCK: pcli-04 drift gate found issues (see above) — halt the release, reconcile, re-run", file=sys.stderr)
        return 1
    if rc == 2:
        print("ERROR: check-pcli-drift-gate could not run — halt and surface; this is NOT a pass", file=sys.stderr)
        return 2
    print(f"ERROR: check-pcli-drift-gate returned unexpected rc={rc} — halt and surface", file=sys.stderr)
    return 2


# ---------------------------------------------------------------------------
# Step 6: console-flash guard
# ---------------------------------------------------------------------------

def cmd_console_flash_guard(args: argparse.Namespace) -> int:
    """Thin dispatcher over verify-no-console-flash.py. Reports OK/issues,
    or a clean skip if the sibling guard is missing (install-surface gap,
    not a ceremony failure). Always exits 0 — the DoE ceremony step reports
    and offers to fix, it does not hard-block on this guard."""
    target = args.target or os.path.join(os.path.expanduser("~"), ".claude", "plugins")
    guard = _sibling("verify-no-console-flash.py")
    if not os.path.isfile(guard):
        print(f"Console-flash guard: guard not found at {guard} — install or check CLAUDE_PLUGIN_ROOT")
        return 0
    rc, out = _run([sys.executable, guard, target])
    if out:
        print(out, end="" if out.endswith("\n") else "\n")
    if rc != 0:
        print("Console-flash guard: UNSUPPRESSED spawns found (see above). Fix before merging.")
    else:
        print("Console-flash guard: OK")
    return 0


# ---------------------------------------------------------------------------
# Step 6: multi-event hook hookEventName guard
# ---------------------------------------------------------------------------

def cmd_multi_event_hook_guard(_args: argparse.Namespace) -> int:
    """Thin dispatcher over check-multi-event-hook-hardcoded-event.py. Same
    report-and-offer shape as the console-flash guard above; always exits 0."""
    guard = _sibling("check-multi-event-hook-hardcoded-event.py")
    if not os.path.isfile(guard):
        print(f"Multi-event hookEventName guard: guard not found at {guard} — install or check CLAUDE_PLUGIN_ROOT")
        return 0
    rc, out = _run([sys.executable, guard])
    if out:
        print(out, end="" if out.endswith("\n") else "\n")
    if rc != 0:
        print("Multi-event hookEventName guard: hardcoded event name found (see above). Fix before merging — echo the incoming hook_event_name instead.")
    else:
        print("Multi-event hookEventName guard: OK")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="workweek-complete-drift-guards.py",
        description="Advisory + gate dispatch logic for /workweek-complete (ported from workweek-complete.md).",
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    sub.add_parser("description-length").set_defaults(func=cmd_description_length)

    p = sub.add_parser("enabled-plugins")
    p.add_argument("--repo-root", default=None)
    p.set_defaults(func=cmd_enabled_plugins)

    p = sub.add_parser("cve-recheck")
    p.add_argument("--repo-root", default=None)
    p.set_defaults(func=cmd_cve_recheck)

    sub.add_parser("schema-drift-gate").set_defaults(func=cmd_schema_drift_gate)

    sub.add_parser("pcli-drift-gate").set_defaults(func=cmd_pcli_drift_gate)

    p = sub.add_parser("console-flash-guard")
    p.add_argument("--target", default=None)
    p.set_defaults(func=cmd_console_flash_guard)

    sub.add_parser("multi-event-hook-guard").set_defaults(func=cmd_multi_event_hook_guard)

    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
