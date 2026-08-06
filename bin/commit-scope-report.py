"""
commit-scope-report.py — READ-ONLY aggregator over the per-commit-attempt
records written by ``coordinator_core.session.commit_scope_events``.

Purpose: turn forward instrumentation into the two numbers the Check-5
strict-mode flip predicate needs and cannot currently compute — a real SWEEP
rate and a false-positive proxy. A foreign-staged WARNING is not a sweep: a
pathspec-scoped ``git commit -- <paths>`` warns about a peer's staged file
and then commits none of it. Sweep candidates are the attempts where foreign
paths were staged AND the commit was unscoped (no explicit pathspec, and not
a worktree-sweeping ``-a``/``--all``); the rest are the FP proxy.

Reads every ``.git/coordinator-sessions/*/commit-scope-events.jsonl`` in the
repo (plus ``.archive/`` session dirs, if present) and prints a summary.

Spec backlink: state/sizings/2026-08-04-forward-instrumentation-for-commit-scope.yaml

Usage:
    commit-scope-report.py [--repo <path>] [--json]

Exit codes:
    0 — report printed (including the zero-records case)
    2 — the repo path could not be resolved to a git checkout

Negative-spec:
  - READ-ONLY. This script opens nothing for write, creates no directory, and
    runs no git subcommand that mutates. It must stay safe to run at any time,
    concurrently with live sessions.
  - Does NOT read ``scope-warnings.log`` at all, and in particular never
    aggregates that log's ``resolution`` column — DoE ruled it an inert
    placeholder (2026-08-04). The JSONL is the only input.
  - Does NOT infer a sweep from a warning alone; ``pathspec_scoped`` /
    ``sweep_all`` are what separate the two populations, and an attempt
    missing those fields is counted as ``malformed``, never guessed at.
  - The ``sweep_all`` (``-a``/``--all``) population is excluded from BOTH
    the numerator AND the denominator of ``fp_proxy_rate`` — not just the
    numerator. It is undecidable (the staged snapshot cannot say what a
    worktree-wide ``-a`` will sweep), so it is reported only as its own
    separate count, never folded into the FP-proxy rate's arithmetic at all.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterator, List


def _git_common_dir(repo: Path) -> Path | None:
    """Resolve the repo's git dir WITHOUT spawning git: walk up for a `.git`
    directory (or a `.git` file naming a linked worktree's gitdir)."""
    cur = repo.resolve()
    for candidate in [cur, *cur.parents]:
        dot_git = candidate / ".git"
        if dot_git.is_dir():
            return dot_git
        if dot_git.is_file():
            try:
                text = dot_git.read_text(encoding="utf-8").strip()
            except OSError:
                return None
            if text.startswith("gitdir:"):
                gitdir = Path(text.split(":", 1)[1].strip())
                if not gitdir.is_absolute():
                    gitdir = (candidate / gitdir).resolve()
                # A linked worktree's gitdir is <common>/worktrees/<name>.
                if gitdir.parent.name == "worktrees":
                    return gitdir.parent.parent
                return gitdir
            return None
    return None


def _session_dirs(git_dir: Path) -> List[Path]:
    roots = [git_dir / "coordinator-sessions"]
    roots.append(git_dir / "coordinator-sessions" / ".archive")
    out: List[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for entry in sorted(root.iterdir()):
            if entry.is_dir() and entry.name != ".archive":
                out.append(entry)
    return out


def _records(git_dir: Path) -> Iterator[Dict[str, Any]]:
    for session_dir in _session_dirs(git_dir):
        path = session_dir / "commit-scope-events.jsonl"
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                yield {"__malformed__": True}
                continue
            if isinstance(obj, dict):
                yield obj
            else:
                yield {"__malformed__": True}


def summarize(records: Iterator[Dict[str, Any]]) -> Dict[str, Any]:
    total = 0
    malformed = 0
    foreign = 0
    sweep_candidates = 0
    warned_but_scoped = 0
    warned_but_sweep_all = 0
    verdicts: Counter = Counter()
    liveness: Counter = Counter()
    claim_source: Counter = Counter()
    sessions: set = set()

    for rec in records:
        if rec.get("__malformed__"):
            malformed += 1
            continue
        if not isinstance(rec.get("staged"), list) or not isinstance(
            rec.get("pathspec_scoped"), bool
        ):
            malformed += 1
            continue
        total += 1
        sessions.add(str(rec.get("session_id", "")))
        verdicts[str(rec.get("verdict", "none"))] += 1

        attribution = rec.get("attribution") or {}
        if isinstance(attribution, dict):
            for fact in attribution.values():
                if not isinstance(fact, dict):
                    continue
                liveness[str(fact.get("liveness", "undetermined"))] += 1
                claim_source[str(fact.get("claim_source", "unreadable"))] += 1

        warned = rec.get("warned_paths") or []
        if not warned:
            continue
        foreign += 1
        if rec.get("sweep_all"):
            # `-a`/`--all` stages from the WORKTREE at commit time; the staged
            # snapshot cannot answer what it will sweep, so it is counted
            # separately rather than folded into either population.
            warned_but_sweep_all += 1
        elif rec.get("pathspec_scoped"):
            warned_but_scoped += 1
        else:
            sweep_candidates += 1

    return {
        "sessions": len(sessions),
        "total_attempts": total,
        "malformed_records": malformed,
        "attempts_with_foreign_staged": foreign,
        "sweep_candidates": sweep_candidates,
        "warned_but_scoped": warned_but_scoped,
        "warned_but_sweep_all": warned_but_sweep_all,
        "sweep_rate": (sweep_candidates / total) if total else 0.0,
        # FP proxy = false-positive rate among DECIDABLE attempts. The
        # `-a`/`--all` bucket (`warned_but_sweep_all`) cannot be classified
        # as sweep-or-scoped from the staged snapshot alone, so it is
        # excluded from BOTH the numerator and this denominator — it stays
        # visible only as its own printed line, not folded into the rate.
        "fp_proxy_rate": (
            (warned_but_scoped / (sweep_candidates + warned_but_scoped))
            if (sweep_candidates + warned_but_scoped)
            else 0.0
        ),
        "verdicts": dict(verdicts),
        "attribution_by_liveness": dict(liveness),
        "attribution_by_claim_source": dict(claim_source),
    }


def _pct(x: float) -> str:
    return "%.1f%%" % (x * 100.0)


def render(s: Dict[str, Any]) -> str:
    lines = [
        "commit-scope report — %d session(s) with records" % s["sessions"],
        "",
        "  commit attempts observed        : %d" % s["total_attempts"],
        "  with foreign staged paths       : %d" % s["attempts_with_foreign_staged"],
        "  ... unscoped (SWEEP CANDIDATES) : %d" % s["sweep_candidates"],
        "  ... pathspec-scoped (FP proxy)  : %d" % s["warned_but_scoped"],
        "  ... -a/--all (undecidable)      : %d" % s["warned_but_sweep_all"],
        "",
        "  sweep rate (candidates/attempts): %s" % _pct(s["sweep_rate"]),
        "  FP proxy  (scoped/decidable)    : %s" % _pct(s["fp_proxy_rate"]),
        "",
        "  check-5 verdicts: %s"
        % (", ".join("%s=%d" % kv for kv in sorted(s["verdicts"].items())) or "-"),
        "  attribution by liveness: %s"
        % (
            ", ".join("%s=%d" % kv for kv in sorted(s["attribution_by_liveness"].items()))
            or "-"
        ),
        "  attribution by claim_source: %s"
        % (
            ", ".join(
                "%s=%d" % kv for kv in sorted(s["attribution_by_claim_source"].items())
            )
            or "-"
        ),
    ]
    if s["malformed_records"]:
        lines += ["", "  malformed records skipped: %d" % s["malformed_records"]]
    if not s["total_attempts"]:
        lines += [
            "",
            "  No records yet. Events are written by Check 5 of",
            "  coordinator_core.bash_guards.dispatch_checks.check_validate_commit",
            "  on each `git commit` attempt with a staged index.",
        ]
    return "\n".join(lines)


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--repo", default=os.getcwd(), help="path inside the git repo")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = ap.parse_args(argv)

    git_dir = _git_common_dir(Path(args.repo))
    if git_dir is None:
        sys.stderr.write("commit-scope-report: not a git repo: %s\n" % args.repo)
        return 2

    summary = summarize(_records(git_dir))
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(render(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
