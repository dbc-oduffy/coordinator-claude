"""workday-start-reconcile-sweep.py — pending-release completion-entry
reconcile backstop for /workday-start Step 1.86.

Next-session backstop for sessions that closed mid-air without a terminal
ceremony (/workday-complete, /handoff, or /workstream-complete). Scans
`archive/completed/*/*.md` (relative to cwd — the consumer repo's root,
same cwd-relative convention the retired bash step used; this script's OWN
sibling-file resolution below is Path(__file__)-relative and carries no cwd
dependence) for `pending-release` completion entries authored TODAY or
YESTERDAY only (bounded scan — not the whole archive), and detects whether
each one has `Session-Id:`-trailer commits not yet recorded in its
`commits:` list — the gap the within-session ceremonies cannot catch when a
session ends abnormally.

Read-only / detect mode only — this script never mutates another session's
entry (it never passes --append to the co-located reconcile-completion-
commits.py helper). Keyed on each entry's own `authored_by:` frontmatter
field; works without the prior session being live.

Invocation (mirrors the retired workday-start.md Step 1.86 bash loop
verbatim in behavior):
    python3 workday-start-reconcile-sweep.py [--archive-root PATH]
        [--today YYYY-MM-DD] [--yesterday YYYY-MM-DD]

Flags exist for test determinism (--today/--yesterday) and for pointing the
sweep at a fixture tree (--archive-root); the DoE ceremony caller passes no
flags — the daily-cadence defaults (today's/yesterday's local date, and
cwd-relative `archive/completed`) exactly reproduce the retired bash step's
behavior.

Per-entry output (stdout), one line only when something is actionable:
  - Empty `authored_by:` (or literal "null" — that string would otherwise
    pass the session-id allowlist regex, so it is explicitly excluded):
        ⚠ entry <basename>: unscopable (no authored_by) — manual reconcile check
  - Reconcile helper exits non-zero:
        ⚠ reconcile helper failed for <path> (rc=<rc>) — manual check
  - Helper reports a nonzero commit delta:
        ⚠ completion entry <basename> has <N> session commit(s) not
        accounted (authored by a prior session) — reconcile.
Silent (no output) when no entry needs attention — this is the offers-not-
nags default: /workday-start renders a "Completion Reconcile" section only
when this script produces output at all.

Exit code: always 0 — this is informational hygiene, never a ceremony gate
(mirrors the retired bash step, which had no failure exit path of its own;
individual per-entry helper failures are reported inline and skipped, not
escalated to a nonzero sweep-level exit).

Spec backlink: DoE-claude coordinator/commands/workday-start.md § Step 1.86
    (Completion-Entry Reconcile Backstop)
Spec backlink: docs/plans/2026-06-27-post-summary-completion-loop-closure.md § C5
Port source: DoE-claude coordinator/commands/workday-start.md Step 1.86 bash
    fence (nested `archive/completed/*/` loop + awk frontmatter parse +
    reconcile-completion-commits.py dispatch), ported verbatim to naked
    Python as part of the bash-kill campaign (2026-07-23, chunk WDS-4).

Negative-spec: does NOT re-implement the completion-commits reconciliation
logic itself (session-id resolution, merge-base/delta computation, chain-
slug expansion) — that lives in the co-located reconcile-completion-
commits.py / claude-klabauter's coordinator_core.ops.completion_ops. This script owns
only the outer bounded-scan/frontmatter-gate/dispatch loop that the retired
bash step performed BEFORE calling that helper.
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

# Windows: suppresses the console popup a subprocess.run(...) would otherwise
# trigger under the headless Claude Code Bash-tool parent. No-op (0) elsewhere.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_DELTA_RE = re.compile(r"delta=(\d+)")


def _frontmatter_field(content: str, key: str) -> str:
    """Mirror the retired bash oracle's awk single-key frontmatter scan.

    Scans only within the first `---`...`---` fence block (awk's n==1),
    returning the first matching `^{key}:` line's value with the
    `{key}:` prefix and any immediately-following whitespace stripped.
    Returns "" if the fence block never closes or the key is never found —
    matching the bash awk script's silent-empty behavior on a miss.
    """
    n = 0
    prefix_re = re.compile(rf"^{re.escape(key)}:[ \t]*")
    for line in content.splitlines():
        if line == "---":
            n += 1
            if n == 2:
                return ""
            continue
        if n == 1:
            m = prefix_re.match(line)
            if m:
                return line[m.end():]
    return ""


def _authored_by_field(content: str) -> str:
    """Mirror the bash oracle's authored_by-specific extra scrubbing:
    strip a trailing ` # comment` and surrounding double-quotes, on top of
    the plain key-prefix strip `_frontmatter_field` already performs.
    """
    raw = _frontmatter_field(content, "authored_by")
    raw = re.sub(r"[ \t]*#.*$", "", raw)
    if len(raw) >= 2 and raw.startswith('"') and raw.endswith('"'):
        raw = raw[1:-1]
    return raw


def _iter_completion_entries(archive_root: str) -> list[str]:
    """Sorted list of `<archive_root>/*/*.md` — mirrors the bash oracle's
    `for _wds_month_dir in archive/completed/*/; do ... *.md; done` nesting,
    made deterministic (bash glob order is filesystem-dependent) via sort.
    """
    pattern = os.path.join(archive_root, "*", "*.md")
    return sorted(glob.glob(pattern))


def _run_reconcile_helper(
    reconcile_script: str, session_id: str, entry_path: str
) -> tuple[int, str]:
    """Invoke the co-located reconcile-completion-commits.py in detect-only
    mode (never --append — a different session authored this entry).
    Returns (returncode, stdout). Stderr is discarded, mirroring the bash
    oracle's `2>/dev/null` on this call.
    """
    try:
        result = subprocess.run(
            [sys.executable, reconcile_script, "--session-id", session_id, entry_path],
            capture_output=True,
            text=True,
            creationflags=_NO_WINDOW,
        )
    except OSError as exc:
        return 2, str(exc)
    return result.returncode, result.stdout


def run_sweep(
    archive_root: str,
    today: str,
    yesterday: str,
    reconcile_script: str,
    out=sys.stdout,
    err=sys.stderr,
) -> int:
    for entry_path in _iter_completion_entries(archive_root):
        try:
            content = Path(entry_path).read_text(encoding="utf-8")
        except OSError:
            continue

        # Bounded scan: today + immediately-prior day only.
        created = _frontmatter_field(content, "created")
        if created not in (today, yesterday):
            continue

        # pending-release entries only.
        status = _frontmatter_field(content, "status")
        if status != "pending-release":
            continue

        # authored_by guard: skip null/absent (literal "null" would pass the
        # session-id allowlist regex — do NOT pass it through).
        authored_by = _authored_by_field(content)
        if not authored_by or authored_by == "null":
            print(
                f"⚠ entry {os.path.basename(entry_path)}: unscopable "
                "(no authored_by) — manual reconcile check",
                file=out,
            )
            continue

        # Detect mode only — read-only; a different session authored this
        # entry, never --append.
        rc, stdout = _run_reconcile_helper(reconcile_script, authored_by, entry_path)
        if rc != 0:
            print(
                f"⚠ reconcile helper failed for {entry_path} (rc={rc}) — manual check",
                file=err,
            )
            continue

        m = _DELTA_RE.search(stdout)
        if m and int(m.group(1)) > 0:
            print(
                f"⚠ completion entry {os.path.basename(entry_path)} has "
                f"{m.group(1)} session commit(s) not accounted (authored by "
                "a prior session) — reconcile.",
                file=out,
            )

    return 0


def _default_reconcile_script() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "reconcile-completion-commits.py")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pending-release completion-entry reconcile backstop (/workday-start Step 1.86)."
    )
    parser.add_argument(
        "--archive-root",
        default="archive/completed",
        help="Root dir to scan for <root>/*/*.md completion entries (default: cwd-relative archive/completed).",
    )
    parser.add_argument(
        "--today",
        default=None,
        help="Override today's date (YYYY-MM-DD); default: local today.",
    )
    parser.add_argument(
        "--yesterday",
        default=None,
        help="Override yesterday's date (YYYY-MM-DD); default: local yesterday.",
    )
    parser.add_argument(
        "--reconcile-script",
        default=None,
        help="Path to reconcile-completion-commits.py (default: co-located sibling).",
    )
    return parser


def main(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv[1:])
    today = args.today or date.today().isoformat()
    yesterday = args.yesterday or (date.today() - timedelta(days=1)).isoformat()
    reconcile_script = args.reconcile_script or _default_reconcile_script()
    return run_sweep(args.archive_root, today, yesterday, reconcile_script)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
