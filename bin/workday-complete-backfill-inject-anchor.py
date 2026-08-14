"""workday-complete-backfill-inject-anchor.py — Phase A0 mechanical anchor injection.

Injects covered_tip_sha/covered_machine anchors into a pre-existing daily summary that
lacks them. Called before any Phase A analyst fan-out so format-migration gap rows are
closed deterministically without dispatching agents.

Usage: workday-complete-backfill-inject-anchor.py <ROOT> <DATE> <DESCENDANT_TIP_SHA> [TODAY] [MACHINE]
  ROOT               — repo root (path; must be a git worktree)
  DATE               — date in YYYY-MM-DD format
  DESCENDANT_TIP_SHA — the per-day descendant tip SHA (caller resolves from scan row;
                       this script verifies it resolves via git rev-parse)
  TODAY              — optional override for "today" (YYYY-MM-DD); defaults to today (local)
  MACHINE            — optional machine name (caller knows from scan row; skips branch-ref enumeration)

Exit codes:
  0  — anchor injected (also covers a STALE anchor bumped to the descendant tip)
  10 — already anchored (idempotent skip; anchor present AND fresh/newer)
  20 — summary file absent (real content gap → caller routes to Phase A analyst)
  30 — content-completeness or commit-density guard fired (no anchor injected)
  1  — usage / bad DATE / bad ROOT / unresolvable SHA / malformed summary structure

Anchor format injected (bare line-start — scan greps '^covered_tip_sha:'):
  covered_tip_sha: <full-40-char-sha>
  covered_machine: <machine>
  > _Record anchor injected <TODAY> by /workday-complete backfill (mechanical) — summary content pre-existing._

Spec backlink: docs/plans/2026-07-02-backfill-anchor-injection-contract.md § Deliverable A
Negative-spec: anchors are bare line-start, NOT blockquoted ('> covered_tip_sha:') — the
  backfill scan greps '^covered_tip_sha:'; a blockquote prefix silently breaks the match.

Port of: workday-complete-backfill-inject-anchor.sh (DoE 091c0f3e, 2026-07-19).
The one incidental `python3 -c` JSON-length parse (with grep fallback) is now native json.
Coordinator_claude_klabauter_root's bash-lib bridge call (workday_ceremony_lib.lib_func) is RETIRED
(de-bash campaign, docs/2026-07-29-debash-residual-sites-spec.md § Group C) — `_completion_count()`
now resolves CLAUDE_KLABAUTER_ROOT via `cc_invoke.ensure_engine_on_path()` (the same self-location-first
resolver `_derive_machine()` below already uses) and queries the completion-log directly in-process
via `coordinator_core.ops.ceremony.records_query.query_records`, dropping the `command -v node`
gate outright rather than porting it: query-completions.py (what the gate used to guard) is
itself already fully native and spawns no node subprocess (see
coordinator_core/ops/query_completions.py's own "Node-subprocess retirement" note), so the gate
could only ever produce a false negative. This also fixes a genuine pre-existing bug the old
bridge call carried (coordinator/tests/test_workday_complete_backfill_inject_anchor.py's
`test_case4_content_gap_guard` xfail): the old call queried CLAUDE_KLABAUTER_ROOT's own archive/completed/
instead of the target repo's — the native call below queries `root` (this function's own
parameter), not claude_klabauter_root. cs_compute_machine is natively imported from
coordinator_core.machine_resolver (de-bash campaign, unit "daily-branch" — Port of:
coordinator-daily-branch.sh, DoE 2fbe0e77, 2026-07-19).
"""
from __future__ import annotations

import datetime
import glob
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "lib"))
import workday_ceremony_lib as wc  # noqa: E402

# Generator-provenance declaration (generator_provenance.py).
# _rewrite_anchor/_inject_anchor rewrite whichever
# archive/daily-summaries/<date>-<machine>.md file currently matches the
# caller's date/machine -- a data-dependent target set, not a fixed artifact.
MUTATES = ["archive/daily-summaries/*.md"]

_ANCHOR_KEY = "covered_tip_sha:"
_MACHINE_KEY = "covered_machine:"


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def _ensure_claude_klabauter_on_path() -> None:
    """Idempotently put CLAUDE_KLABAUTER_ROOT on sys.path, reusing `_derive_machine`'s /
    `_completion_count`'s own resolver (`cc_invoke.ensure_engine_on_path`,
    self-location-first) so this file has exactly one CLAUDE_KLABAUTER_ROOT resolution
    path. Best-effort: a resolution failure here is caught by the caller,
    matching the existing try/except shape those two functions already use.
    """
    import cc_invoke

    cc_invoke.ensure_engine_on_path(__file__)


def _declare_write(target_file: str) -> None:
    """Best-effort DR-276 write declaration for the two real write sites below
    (`_rewrite_anchor`, `_inject_anchor`) — never lets a resolution/import
    failure mask the anchor write that already succeeded."""
    try:
        _ensure_claude_klabauter_on_path()
        from coordinator_core.session.declared_writes import declare_write

        declare_write(target_file)
    except (RuntimeError, ImportError):
        pass


def _rewrite_anchor(target_file: str, full_sha: str, machine: str) -> None:
    """Rewrite the first covered_tip_sha / covered_machine lines in place (bump path)."""
    with open(target_file, "r", encoding="utf-8") as f:
        lines = f.read().splitlines(keepends=True)
    stip = smach = False
    out = []
    for line in lines:
        if not stip and line.startswith(_ANCHOR_KEY):
            out.append(f"covered_tip_sha: {full_sha}\n")
            stip = True
            continue
        if not smach and line.startswith(_MACHINE_KEY):
            out.append(f"covered_machine: {machine}\n")
            smach = True
            continue
        out.append(line)
    with open(target_file, "w", encoding="utf-8") as f:
        f.writelines(out)
    # DR-276: declared AFTER the write lands.
    _declare_write(target_file)


def _inject_anchor(target_file: str, full_sha: str, machine: str, today: str) -> int:
    """Insert anchor lines + prose note. Returns 0 on success, 1 on malformed structure
    (unclosed frontmatter / no H1) — mirroring the awk END-guard exits."""
    with open(target_file, "r", encoding="utf-8") as f:
        lines = f.read().splitlines(keepends=True)

    note = (
        f"> _Record anchor injected {today} by /workday-complete backfill "
        "(mechanical) — summary content pre-existing._\n"
    )
    first_line = lines[0].rstrip("\n") if lines else ""

    out: list[str] = []
    if first_line == "---":
        # YAML frontmatter: insert bare key lines before the closing --- ; prose note after the H1.
        keys_done = False
        note_done = False
        for i, line in enumerate(lines):
            if i == 0:
                out.append(line)
                continue
            if not keys_done and line.rstrip("\n") == "---":
                out.append(f"covered_tip_sha: {full_sha}\n")
                out.append(f"covered_machine: {machine}\n")
                keys_done = True
                out.append(line)
                continue
            if not note_done and line.lower().startswith("# daily summary"):
                out.append(line)
                out.append(note)
                note_done = True
                continue
            out.append(line)
        if not keys_done:
            _err("ERROR: frontmatter block not closed (no terminating ---); anchor not injected")
            return 1
    else:
        # No frontmatter: insert all three lines after the # Daily Summary H1.
        done = False
        for line in lines:
            if not done and line.lower().startswith("# daily summary"):
                out.append(line)
                out.append("\n")
                out.append(f"covered_tip_sha: {full_sha}\n")
                out.append(f"covered_machine: {machine}\n")
                out.append(note)
                done = True
                continue
            out.append(line)
        if not done:
            _err('ERROR: no "# Daily Summary" H1 found in file; cannot inject anchor')
            return 1

    with open(target_file, "w", encoding="utf-8") as f:
        f.writelines(out)
    # DR-276: declared AFTER the write lands.
    _declare_write(target_file)
    return 0


def _derive_machine(root: str, full_sha: str, machine_arg: str) -> str:
    if machine_arg:
        return machine_arg
    # git for-each-ref --contains <sha> over work/ heads and origin/work/ remotes.
    proc = wc.git(
        "-C", root, "for-each-ref", "--contains", full_sha,
        "--format=%(refname)", "refs/heads/work/", "refs/remotes/origin/work/",
        cwd=None,
    )
    for ref in proc.stdout.splitlines():
        m = re.match(r"^refs/heads/work/([^/]+)/", ref)
        if m:
            return m.group(1)
        m = re.match(r"^refs/remotes/origin/work/([^/]+)/", ref)
        if m:
            return m.group(1)
    # Fall back to the native cs_compute_machine equivalent (coordinator_core.machine_resolver).
    try:
        _ensure_claude_klabauter_on_path()
        from coordinator_core.machine_resolver import compute_machine
        m = compute_machine()
        if m:
            return m
    except (RuntimeError, ImportError):
        pass
    return "unknown"


def _completion_count(root: str, date: str) -> int:
    """Count completion-log entries for DATE, natively in-process.

    De-bash campaign, docs/2026-07-29-debash-residual-sites-spec.md § Group C: this used
    to bridge to bash twice (once to source coordinator-claude-klabauter-root.sh for CLAUDE_KLABAUTER_ROOT,
    once to gate `command -v node` before shelling out to query-completions.py). Both
    bridges are retired — CLAUDE_KLABAUTER_ROOT resolves via `cc_invoke.ensure_engine_on_path()`
    (the same self-location-first resolver `_derive_machine()` above already uses, so
    this file has exactly one CLAUDE_KLABAUTER_ROOT resolution path instead of two that could
    drift apart), and the completion-log query calls
    `coordinator_core.ops.ceremony.records_query.query_records` in-process — no `node`
    gate, because query-completions.py (what that gate used to guard) is itself already
    fully native and spawns no node subprocess.

    Return contract (unchanged from the retired bridge version): always an int; 0
    covers BOTH "query ran and found nothing" and "native query seam unavailable" —
    those two were never distinguishable in the prior bridge implementation either
    (both paths produced empty/absent stdout under its `|| true` shell fallback), so
    this preserves rather than introduces the non-distinction. Never raises.
    """
    try:
        _ensure_claude_klabauter_on_path()
        from coordinator_core.ops.ceremony.records_query import query_records
        records = query_records("completion", Path(root), where=f"created={date}")
    except (RuntimeError, ImportError, SystemExit):
        _err("WARN: content-completeness guard skipped (native records query unavailable); "
             "injecting without heuristic check")
        return 0
    return len(records)


def _bullet_count(target_file: str) -> int:
    count = 0
    in_wc = False
    with open(target_file, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if re.match(r"^##\s", line):
                in_wc = bool(re.search(r"Work\s Completed", line)) or "Work Completed" in line
                continue
            if in_wc and (re.match(r"^[-*]\s", line) or re.match(r"^###\s", line)):
                count += 1
    return count


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        _err(f"Usage: {os.path.basename(sys.argv[0])} <ROOT> <DATE> <DESCENDANT_TIP_SHA> [TODAY] [MACHINE]")
        return 1

    root_raw = argv[0]
    date = argv[1]
    descendant_tip_sha = argv[2]
    today = argv[3] if len(argv) >= 4 and argv[3] else datetime.date.today().strftime("%Y-%m-%d")
    machine_arg = argv[4] if len(argv) >= 5 else ""

    # Resolve ROOT to an absolute path (fail loud if it doesn't exist).
    if not os.path.isdir(root_raw):
        _err(f"ERROR: ROOT does not exist or is not accessible: {root_raw}")
        return 1
    root = os.path.abspath(root_raw)

    if not re.match(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$", date):
        _err(f"ERROR: DATE must be YYYY-MM-DD (got '{date}')")
        return 1

    # Verify the descendant tip SHA resolves in this repo.
    full_sha = wc.git_out("-C", root, "rev-parse", "--verify", f"{descendant_tip_sha}^{{commit}}")
    if not full_sha:
        _err(f"ERROR: DESCENDANT_TIP_SHA '{descendant_tip_sha}' does not resolve to a commit in {root}")
        return 1

    machine = _derive_machine(root, full_sha, machine_arg)

    # Resolve target summary file (per-machine → glob → legacy flat).
    ds_dir = os.path.join(root, "archive", "daily-summaries")
    target_file = ""
    cand1 = os.path.join(ds_dir, f"{date}-{machine}.md")
    if os.path.isfile(cand1):
        target_file = cand1
    if not target_file:
        for cand in sorted(glob.glob(os.path.join(ds_dir, f"{date}-*.md"))):
            if os.path.isfile(cand):
                target_file = cand
                break
    if not target_file:
        cand3 = os.path.join(ds_dir, f"{date}.md")
        if os.path.isfile(cand3):
            target_file = cand3
    if not target_file:
        _err(f"summary-absent: no summary file found for {date} in {ds_dir}/")
        return 20

    # Idempotency — already anchored, and is it FRESH?
    recorded = ""
    with open(target_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith(_ANCHOR_KEY):
                parts = line.split()
                if len(parts) >= 2:
                    recorded = parts[1]
                break
    if recorded:
        rec_full = wc.git_out("-C", root, "rev-parse", "--verify", f"{recorded}^{{commit}}")
        if rec_full and rec_full == full_sha:
            _err(f"already-anchored (fresh): {target_file}")
            return 10
        if rec_full and wc.git_ok("-C", root, "merge-base", "--is-ancestor", rec_full, full_sha):
            _rewrite_anchor(target_file, full_sha, machine)
            _err(f"bumped: {target_file}  covered_tip_sha {recorded} -> {full_sha}")
            print(f"TARGET={target_file}")
            return 0
        if not rec_full:
            _rewrite_anchor(target_file, full_sha, machine)
            _err(f"bumped: {target_file}  covered_tip_sha <unresolvable:{recorded}> -> {full_sha}")
            print(f"TARGET={target_file}")
            return 0
        _err(f"already-anchored (>= target or divergent): {target_file}")
        return 10

    # Content-completeness guard.
    completion_count = _completion_count(root, date)
    bullet_count = _bullet_count(target_file)
    _err(f"INFO: date={date} file={target_file} completions={completion_count} bullets={bullet_count}")
    if completion_count >= 3 and completion_count >= bullet_count * 2:
        _err(f"CONTENT-GAP: {target_file} — {completion_count} completion entries vs "
             f"{bullet_count} Work Completed bullets; route to Phase A content-assembly analyst")
        return 30

    # Commit-density content-gap signal.
    range_out = wc.git(
        "-C", root, "log", full_sha, "--no-merges",
        f"--since={date} 00:00:00", f"--until={date} 23:59:59", "--format=%H",
    ).stdout
    range_shas = [s for s in range_out.splitlines() if s]
    range_count = len(range_shas)
    range_set = set(range_shas)

    with open(target_file, "r", encoding="utf-8") as f:
        body = f.read()
    tokens = {t.lower() for t in re.findall(r"\b[0-9a-fA-F]{7,40}\b", body)}
    cited_full: set[str] = set()
    for tok in tokens:
        full = wc.git_out("-C", root, "rev-parse", "--verify", "-q", f"{tok}^{{commit}}")
        if not full:
            continue
        if full in cited_full:
            continue
        if full in range_set:
            cited_full.add(full)
    cited_count = len(cited_full)

    morning_signal = bool(re.search(r"morning run|wraps the tail|spilled past midnight", body, re.IGNORECASE))
    _err(f"INFO: content-density date={date} range_commits={range_count} "
         f"cited_shas={cited_count} morning_signal={1 if morning_signal else 0}")
    if range_count >= 3 and cited_count >= 1 and (cited_count * 2) < range_count:
        _err(f"CONTENT-GAP: {target_file} — summary cites {cited_count} in-range commit SHAs "
             f"vs {range_count} commits in the {date} range (<50%); route to Phase A content-assembly analyst")
        return 30
    if morning_signal and range_count >= 10:
        _err(f"CONTENT-GAP: {target_file} — morning-run/tail-wrap note anchored to a "
             f"{range_count}-commit range; route to Phase A content-assembly analyst")
        return 30

    # Inject anchors.
    rc = _inject_anchor(target_file, full_sha, machine, today)
    if rc != 0:
        return rc
    _err(f"injected: {target_file}  covered_tip_sha={full_sha}  covered_machine={machine}")
    print(f"TARGET={target_file}")
    return 0


if __name__ == "__main__":
    # DR-276: this script owns its own positional-arg main(argv) (no argparse,
    # no single-op forwarding contract run_op_main could route through), so
    # it uses recording_declared_writes() -- the sanctioned carve-out
    # (coordinator_core.cli_entry module docstring) -- to make its two real
    # write sites (_rewrite_anchor / _inject_anchor, via _declare_write
    # above) a session scope-touch claim.
    try:
        _ensure_claude_klabauter_on_path()
        from coordinator_core.cli_entry import recording_declared_writes
    except (RuntimeError, ImportError):
        sys.exit(main(sys.argv[1:]))
    else:
        with recording_declared_writes():
            _exit_code = main(sys.argv[1:])
        sys.exit(_exit_code)
