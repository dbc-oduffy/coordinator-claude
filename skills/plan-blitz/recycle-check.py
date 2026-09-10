#!/usr/bin/env python3
"""recycle-check — does this wave contain a baton whose work already finished? Writes nothing.

WHY THIS EXISTS. `roadmap.blitz_land` stamps a dispatched XS baton `shipped` with a `shipped_in`
SHA, and that stamp is what makes the baton terminal. Omit the SHA and the XS lane refuses: the
baton stays `open`, and the next gate read returns it as a candidate. The skill names this — *"that
is the recycling defect, and it is silent"* — and the refusal is reported in `refused[]`. But the
refusal is reported at LANDING, to a driver who may not read it, and nothing at all is reported at
the next FIRE. So a baton whose work is finished is re-scouted, re-sized, and re-planned at full
cost, and the only thing that notices is a sizing scout spending its whole dispatch discovering
the work is done.

Measured on project-rag, wave 0 of run 20260910T064533Z: 27 batons, 5 carrying an execution record
from a prior wave, 2 of them recording FINISHED work — `hnd-envelope-and-diagnostic-honest-b0bb8e`
(`outcome: closed`) and `hnd-portable-vectors-emit-an-encry-69a9ba` (`completed: true`) — both
still `status: open`, `deployment_state: ready_to_fire`, both re-scouted. The other 3 record
`completed: false` or `blocked-on-preflight` and are legitimately back.

This module is the fire-time half of that pair: one pure read over the trail root, run BEFORE the
wave is fired, naming the batons whose prior execution record says the work finished. It reports;
it never refuses, and it never writes — the repair is a landing, and a landing is the caller's act.

THE ID-TO-FILENAME MAPPING IS BORROWED, NOT INVENTED. `workflows/plan-blitz.mjs :: sidecarFor`
renders a sidecar as `<trailDir>/<slug(batonId)>.<slug(role)>.md`, and that slug collapses every
run of non-alphanumerics to a single `-`. Baton ids routinely contain `--` (a replan of a replan)
and `_` (a dated stub id), so `hnd-retire-the-11-self-satisfying--7d1f72` is on disk as
`hnd-retire-the-11-self-satisfying-7d1f72`: an id-keyed reader that does not apply the same slug
finds nothing and reports CLEAN. Measured on the same corpus: 7 of 64 candidate ids are
slug-lossy, and 0 collide — the 6-hex suffix is what keeps the mapping injective in practice, not
the slug. This is the one deliberate id-keyed consumer of the trail; everything else in the
pipeline passes `sidecarPath` verbatim. If `sidecarFor` changes, `_slug` here changes with it, and
`tests/test_plan_blitz_recycle_check.py` is what fails if it does not.

Negative-spec:
  - Does NOT write, stamp, land, or mutate anything. The repair for a RECYCLED baton is
    `roadmap.blitz_land` with `shipped_in`, named in the report and never performed here.
  - Does NOT decide whether to fire. It reports the set; dropping a baton from a wave is the
    driver's act, and keeping that call explicit is what stops this from silently shrinking a wave.
  - Does NOT read the baton records or call the engine. The gate report already carries every
    baton's status; re-deriving it from disk would be a second answer to a settled question.
  - Does NOT judge an INCOMPLETE record. A `completed: false` baton is correctly back in the wave,
    and calling that a finding would train the reader to ignore the ones that matter.
  - Does NOT spawn a subprocess. Pure stdlib reads over a directory of markdown.

A FINISHED record is only RECYCLING while the baton is STILL A CANDIDATE. Execution records are
history and never change, so once a landing stamps the baton terminal a trail-only reader keeps
reporting the repair it already recommended -- and a detector that cries wolf after the fix is
worse than none, because the next reader learns to skip it. Candidacy comes from the gate report's
own `candidate` verdict (hence `--gate-report`, and hence no second read of the baton records and
no engine call): a FINISHED record on a baton the engine no longer counts is REPAIRED, not a
finding. Without a gate report candidacy CANNOT be known, and the honest state is UNVERIFIED --
never a silent CLEAN, which would hide a live recycle.

Exit status is a verdict: 0 CLEAN (nothing in the set is recycling; REPAIRED and UNFINISHED rows
may still be listed), 1 RECYCLED or UNVERIFIED (a landing is owed, or candidacy could not be
checked), 2 on a usage or precondition failure.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

EXIT_CLEAN, EXIT_RECYCLED, EXIT_USAGE = 0, 1, 2

# Mirrors workflows/plan-blitz.mjs :: slug. See the module docstring on why this is borrowed.
_slug = lambda text: re.sub(r"^-|-$", "", re.sub(r"[^a-z0-9]+", "-", str(text).lower()))

# A record says its work finished in one of two vocabularies, both in service in the corpus:
# `completed: true` (the frontmatter shape) and `outcome: <word>` (the prose shape). Neither is
# canonical, so both are read, and a record matching neither is UNREADABLE rather than assumed.
_COMPLETED_TRUE = re.compile(r"completed:\s*\**\s*true\b", re.I)
_COMPLETED_FALSE = re.compile(r"completed:\s*\**\s*false\b", re.I)
_OUTCOME = re.compile(r"^\s*(?:\*\*)?outcome(?:\*\*)?:\s*(.+?)\s*$", re.I | re.M)

# `outcome:` words that mean the work is DONE. A word outside this set is reported verbatim and
# classified UNREADABLE — guessing at an unknown disposition is how a live baton gets dropped.
_TERMINAL_OUTCOMES = ("closed", "closure", "completed", "confirm-and-close", "closed-superseded")


def _frontmatter(text: str) -> str:
    """The leading `---` block, or "" when the record has none. A record's frontmatter is its own
    DECLARATION; its body is narration about the work, and the two disagree in practice — an
    execution record whose frontmatter says `outcome: closed` routinely discusses a `completed:
    false` predecessor further down. Reading the body first lets that narration outvote the
    declaration, which is how a FINISHED baton gets reported as legitimately back and recycles
    again. Measured: 2 of 5 records misclassified that way before this split existed."""
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    return text[3:end] if end != -1 else ""


def _first_disposition(chunk: str):
    """First disposition in DOCUMENT ORDER, or None. Order matters and precedence between the two
    vocabularies does not: a record states its disposition once, and whichever spelling it reaches
    for first is the one it meant. Preferring a vocabulary instead of a position is what made a
    body-level `completed:` outrank a frontmatter `outcome:`."""
    best = None
    for pat, kind in ((_COMPLETED_TRUE, "t"), (_COMPLETED_FALSE, "f"), (_OUTCOME, "o")):
        m = pat.search(chunk)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), kind, m)
    return best


def _disposition(text: str) -> tuple[str, str]:
    """Return (state, evidence). state is FINISHED | UNFINISHED | UNREADABLE."""
    found = _first_disposition(_frontmatter(text)) or _first_disposition(text)
    if found is None:
        return "UNREADABLE", "no completed: or outcome: line"
    _, kind, m = found
    if kind == "t":
        return "FINISHED", "completed: true"
    if kind == "f":
        return "UNFINISHED", "completed: false"
    raw = m.group(1)
    word = raw.strip().strip("`*").split()[0].rstrip(":,;(").lower()
    # Unambiguous negatives. These are not guesses: each states plainly that the work did not
    # finish, and leaving them UNREADABLE buries a clear answer under the bucket reserved for
    # words nobody can interpret. Anything outside both sets stays UNREADABLE by design.
    if word.startswith(("blocked", "pulled", "not-", "partial", "incomplete", "deferred", "failed")):
        return "UNFINISHED", f"outcome: {raw[:60]}"
    if word in _TERMINAL_OUTCOMES:
        return "FINISHED", f"outcome: {raw[:60]}"
    return "UNREADABLE", f"outcome: {raw[:60]}"


def scan(repo_root: Path, baton_ids, trail_root: str, exclude_run: str | None, live=None):
    root = repo_root / trail_root
    if not root.is_dir():
        return None, f"no trail root at {root}"
    by_slug = {}
    for bid in baton_ids:
        by_slug.setdefault(_slug(bid), []).append(bid)
    # LATEST RECORD WINS, per baton. A baton dispatched in more than one wave has more than one
    # execution record, and they disagree by design: the later one was written with the earlier
    # one's result already on disk. Reporting the earlier is reporting a superseded claim as
    # current -- measured 2026-09-10, where a `completed: true` from one wave had been overtaken
    # by a next-wave verification finding the work INCOMPLETE (its test had never been run), and
    # a tool reading the older record called a live baton recycling. Run directories are
    # timestamp-named, so lexical order is chronological order.
    latest: dict = {}
    for run_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        if exclude_run and run_dir.name == exclude_run:
            continue
        for rec in sorted(run_dir.glob("*.execution.md")):
            stem = rec.name[: -len(".execution.md")]
            for bid in by_slug.get(stem, ()):
                prior = latest.get(bid)
                latest[bid] = (run_dir, rec, (prior[2] + 1) if prior else 0)

    findings = []
    for bid, (run_dir, rec, superseded) in sorted(latest.items()):
            for _ in (bid,):
                state, evidence = _disposition(rec.read_text(encoding="utf-8", errors="replace"))
                # A FINISHED record only means RECYCLING while the baton is STILL a live
                # candidate. Once a landing stamps it terminal the record does not change --
                # it is history -- so a check that reads the trail alone keeps reporting the
                # repair it already recommended. A detector that cries wolf after the fix is
                # worse than none: the next reader learns to skip it. `live` is the gate
                # report's own candidacy verdict, which is why this needs no second read of
                # the baton records and no engine call.
                if state == "FINISHED":
                    if live is None:
                        state = "UNVERIFIED"
                    elif not live.get(bid, {}).get("candidate", False):
                        state = "REPAIRED"
                findings.append(
                    {
                        "baton": bid,
                        "record": str(rec.relative_to(repo_root)).replace("\\", "/"),
                        "run": run_dir.name,
                        "state": state,
                        "evidence": evidence,
                        "supersedes": superseded,
                    }
                )
    return findings, None


def _gate_body(gate_report: Path) -> dict:
    """The gate report's body, whichever shape the caller froze.

    `coordinator-invoke roadmap.plan_gate` writes a JSON-RPC envelope -- the gate's own fields
    sit under `result`, and a caller that redirects that stdout straight to disk (which is what
    the skill's step 2 tells it to do) freezes the ENVELOPE. Reading `waves` off the envelope
    finds nothing and reports `wave 0 is empty`, which is indistinguishable from a wave that
    genuinely has no members -- so the check exits USAGE and the caller reads it as "nothing to
    recycle" and fires the wave unchecked. Accept both shapes rather than making the freeze
    step's redirect a silent precondition. Tripwire:
    AN-ENVELOPE-FROZEN-AS-A-GATE-REPORT-READS-AS-AN-EMPTY-WAVE.
    """
    data = json.loads(gate_report.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "batons" not in data and isinstance(data.get("result"), dict):
        return data["result"]
    return data


def _wave_ids(gate_report: Path, wave_index: int):
    data = _gate_body(gate_report)
    waves = data.get("waves") or []
    ids = list(waves[wave_index]) if wave_index < len(waves) else []
    return ids, _live_map(data)


def _live_map(data) -> dict:
    """Per-baton candidacy off the gate report -- the engine's own verdict, not a re-derivation."""
    return {
        b["id"]: {
            "candidate": bool(b.get("candidate")),
            "deployment_state": b.get("deployment_state"),
            "status": b.get("status"),
        }
        for b in (data.get("batons") or [])
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="recycle-check",
        description="Name the batons in a wave whose prior execution record says the work finished.",
    )
    ap.add_argument("baton_ids", nargs="*", help="baton ids; default: the gate report's wave")
    ap.add_argument("--repo-root", default=".", help="repo root (default: cwd)")
    ap.add_argument("--gate-report", help="frozen roadmap.plan_gate JSON to take the wave from")
    ap.add_argument("--wave-index", type=int, default=0, help="which wave of the report (default 0)")
    ap.add_argument("--trail-root", default="state/plan-blitz", help="repo-relative trail root")
    ap.add_argument("--exclude-run", help="trail dir name to skip, normally this run's own")
    ap.add_argument("--json", action="store_true", help="emit the full report as JSON")
    args = ap.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    ids = list(args.baton_ids)
    live = None
    if args.gate_report:
        _rp = Path(args.gate_report)
        if not _rp.is_absolute():
            _rp = repo_root / _rp
        if _rp.is_file():
            live = _live_map(_gate_body(_rp))
    if not ids:
        if not args.gate_report:
            ap.error("pass baton ids or --gate-report")
        report = Path(args.gate_report)
        if not report.is_absolute():
            report = repo_root / report
        if not report.is_file():
            print(f"recycle-check: no gate report at {report}", file=sys.stderr)
            return EXIT_USAGE
        ids, live = _wave_ids(report, args.wave_index)
        if not ids:
            print(f"recycle-check: wave {args.wave_index} is empty", file=sys.stderr)
            return EXIT_USAGE

    findings, err = scan(repo_root, ids, args.trail_root, args.exclude_run, live)
    if err:
        print(f"recycle-check: {err}", file=sys.stderr)
        return EXIT_USAGE

    finished = [f for f in findings if f["state"] == "FINISHED"]
    unverified = [f for f in findings if f["state"] == "UNVERIFIED"]
    repaired = [f for f in findings if f["state"] == "REPAIRED"]
    verdict = "RECYCLED" if finished else ("UNVERIFIED" if unverified else "CLEAN")

    if args.json:
        print(json.dumps({"verdict": verdict, "scanned": len(ids), "recycling": len(finished),
                          "repaired": len(repaired), "unverified": len(unverified),
                          "findings": findings}, indent=2))
    else:
        head = f"recycle-check: {verdict} — {len(finished)} of {len(ids)} baton(s) recycling"
        if repaired:
            head += f", {len(repaired)} already repaired"
        if unverified:
            head += f", {len(unverified)} unverified (no --gate-report, candidacy unchecked)"
        print(head)
        for f in findings:
            tag = {
                "FINISHED": "RECYCLED",
                "UNFINISHED": "back    ",
                "UNREADABLE": "unread  ",
                "REPAIRED": "repaired",
                "UNVERIFIED": "unverif ",
            }[f["state"]]
            sup = f"  (latest of {f['supersedes'] + 1} records)" if f.get("supersedes") else ""
            print(f"  {tag}  {f['baton']}{sup}")
            print(f"          {f['run']}  {f['evidence']}")
            print(f"          {f['record']}")
        if finished:
            print(
                "  repair  a finished baton is open because its landing never stamped it. Two\n"
                "          causes reach this same symptom and only one is a missing SHA:\n"
                "            1. the landing ran without shipped_in — re-run roadmap.blitz_land for\n"
                "               that wave with shipped_in set to the SHA carrying its XS work, and\n"
                "               read refused[].\n"
                "            2. the readiness gate returned `pulled` on a finished dispatch —\n"
                "               landing leaves a pulled baton where it is, so re-running changes\n"
                "               nothing. Read the verdict's own reason: one that says the baton is\n"
                "               closable while the verdict says pulled is the gate having no word\n"
                "               for `done`. `ready` on a dispatch route is that word.\n"
                "          Dropping it from this wave by hand leaves the same baton to recycle into\n"
                "          the next one."
            )
    return EXIT_RECYCLED if (finished or unverified) else EXIT_CLEAN


if __name__ == "__main__":
    sys.exit(main())
