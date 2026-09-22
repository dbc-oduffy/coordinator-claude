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
renders a sidecar as `<trailDir>/<waveSlot>/<slug(batonId)>.<slug(role)>.md` — one leaf directory
per FIRE, because a baton re-planned in a later wave fires against the same trail and a name
carrying only the baton overwrote what the earlier wave recorded. The FILENAME is unchanged by
that, which is why this reader still matches on `<slug(batonId)>.execution.md`; only the depth
moved, so the scan below recurses and a trail written flat before the slot existed still reads.
That slug collapses every run of non-alphanumerics to a
single `-`. Baton ids routinely contain `--` (a replan of a replan) and `_` (a dated stub id), so
`hnd-retire-the-11-self-satisfying--7d1f72` is on disk as
`hnd-retire-the-11-self-satisfying-7d1f72`: an id-keyed reader that does not apply the same slug
finds nothing and reports CLEAN. Measured on the same corpus: 7 of 64 candidate ids are
slug-lossy, and 0 collide — the 6-hex suffix is what keeps the mapping injective in practice, not
the slug. This is the one deliberate id-keyed consumer of the trail; everything else in the
pipeline passes `sidecarPath` verbatim. If `sidecarFor` changes, `_slug` here changes with it, and
`tests/test_plan_blitz_recycle_check.py` is what fails if it does not.

THE ARCHIVE IS THE SECOND WAY FINISHED WORK COMES BACK. A merge resolved against a pre-archive
tree restores an archived baton at its old `state/handoffs/` path, the gate reads that copy as open,
and it returns as a candidate. Measured on one consumer repo: 3 of 10 batons in one fire were such
copies, and agents were dispatched on dead work. `git mv` into `archive/handoffs/<YYYY-MM>/` keeps
the basename, so a candidate whose basename sits in the archive in a terminal state (`status:
consumed`, or a `deployment_state` in the engine's `HANDOFF_TERMINAL_DEPLOYMENT`) is RESURRECTED:
the archived copy is the truth. A candidate that shares only a `deliverable_id` with an archived
record that shipped, closed or was abandoned is SHARED-ID, listed and never a finding. Successors
and fan-out siblings share the id by design: measured on this plugin's source repo, 29 of 229
candidates share one with an archived record, all but 4 through a `continued` link, and 2 of those
4 are siblings.

Negative-spec:
  - Does NOT write, stamp, land, or mutate anything. The repair for a RECYCLED baton is
    `roadmap.blitz_land` with `shipped_in`, and for a RESURRECTED one it is removing or
    re-archiving the live copy. Both are named in the report and never performed here.
  - Does NOT decide whether to fire. It reports the set; dropping a baton from a wave is the
    driver's act, and keeping that call explicit is what stops this from silently shrinking a wave.
  - Does NOT re-derive a baton's status or call the engine. The gate report already carries every
    baton's status; re-deriving it from disk would be a second answer to a settled question. The
    one read of a live record is its identity (`deliverable_id`, `predecessor`) for the archive
    check, and an archived record is read for its terminal state alone.
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

Exit status is a verdict: 0 CLEAN (nothing in the set is recycling or resurrected; REPAIRED,
UNFINISHED and SHARED-ID rows may still be listed), 1 RECYCLED, RESURRECTED or UNVERIFIED (a
landing or an archive repair is owed, or candidacy could not be checked), 2 on a usage or
precondition failure.

Arrived from DoE-claude coordinator/skills/plan-blitz/recycle-check.py
(docs/plans/2026-09-18-doe-holds-no-scripts.md, chunk W3-C7). Path resolution: every path it
reads (`--repo-root`, `--trail-root`, `--archive-root`, `--gate-report`) is caller-supplied and
resolved against `--repo-root`, already the "session repo" class (§ Path resolution) with no seam
to retarget. `_slot_order` (review: coordinator:overengineering-reviewer, finding 5) now imports
`coordinator_core.ops.dispatch_emit.slot_order` through the standard `require_colocated_engine_on_path`
bootstrap, lazily inside the function -- the only engine import this module makes.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

EXIT_CLEAN, EXIT_RECYCLED, EXIT_USAGE = 0, 1, 2

# Mirrors workflows/plan-blitz.mjs :: slug. See the module docstring on why this is borrowed.
def _slug(text: object) -> str:
    return re.sub(r"^-|-$", "", re.sub(r"[^a-z0-9]+", "-", str(text).lower()))

# A record says its work finished in one of two vocabularies, both in service in the corpus:
# `completed: true` (the frontmatter shape) and `outcome: <word>` (the prose shape). Neither is
# canonical, so both are read, and a record matching neither is UNREADABLE rather than assumed.
_COMPLETED_TRUE = re.compile(r"completed:\s*\**\s*true\b", re.I)
_COMPLETED_FALSE = re.compile(r"completed:\s*\**\s*false\b", re.I)
_OUTCOME = re.compile(r"^\s*(?:\*\*)?outcome(?:\*\*)?:\s*(.+?)\s*$", re.I | re.M)

# `outcome:` words that mean the work is DONE. A word outside this set is reported verbatim and
# classified UNREADABLE — guessing at an unknown disposition is how a live baton gets dropped.
_TERMINAL_OUTCOMES = ("closed", "closure", "completed", "confirm-and-close", "closed-superseded")

# Words that take a terminal outcome back, wherever they appear in its value. Deliberately narrow:
# each says the work stopped short, and none of them is a word a finished record reaches for.
# `blocked` is NOT here — "not blocked" is a routine reassurance inside an honest partial.
_QUALIFIED = re.compile(r"\b(partial(?:ly)?|deferred|incomplete|unfinished)\b", re.I)

# The path an execution record names itself as written for. Agents write these records freehand,
# and the corpus spells the key `handoff:` or `record:`. Two distinct handoffs can share one
# `deliverable_id` (a legitimate sibling or fan-out); without this, one finished record for
# handoff A flags handoff B's still-open candidate as RECYCLED too, because both slug to the same
# filename stem. A record naming no path is not penalized for it -- see `_path_blocks_match`.
_HANDOFF_PATH = re.compile(r"^\s*(?:handoff|record):\s*(\S.*?)\s*$", re.M)

# Mirrors the engine's `lifecycle_constants.HANDOFF_TERMINAL_DEPLOYMENT`; a handoff is also DONE at
# `status: consumed`. `continued` hands the deliverable to a successor carrying the same
# `deliverable_id`, so only the other three END a deliverable.
_TERMINAL_DEPLOYMENT = frozenset({"shipped", "abandoned", "continued", "closed"})
_DELIVERABLE_ENDED = _TERMINAL_DEPLOYMENT - {"continued"}
_FM_KEY = re.compile(r"^([A-Za-z_]+):\s*(.*?)\s*$")


def _norm_path(p: str) -> str:
    return p.strip().replace("\\", "/")


def _record_handoff_path(text: str):
    """The handoff path an execution record's leading key block names, or None when it names none.

    A record whose frontmatter opens with `---` and never closes is still read: its key block is
    the run of lines up to the first blank line."""
    block = _frontmatter(text)
    if not block and text.startswith("---"):
        block = text[3:].lstrip("\n").split("\n\n", 1)[0]
    m = _HANDOFF_PATH.search(block)
    return _norm_path(m.group(1)) if m else None


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
    """Return (state, evidence). state is FINISHED | UNFINISHED | UNREADABLE.

    Two shapes must never read FINISHED, because RECYCLED sends the driver to stamp the baton
    shipped: an outcome whose VALUE is itself a `completed:` declaration
    (`**Outcome: completed: false — blocked**` — its first word is "completed"), and frontmatter
    declaring a terminal `outcome:` beside `completed: false`. A declaration that contradicts
    itself resolves toward UNFINISHED, the direction that re-plans rather than closes."""
    frontmatter = _frontmatter(text)
    found = _first_disposition(frontmatter) or _first_disposition(text)
    if found is None:
        return "UNREADABLE", "no completed: or outcome: line"
    _, kind, m = found
    if kind == "o":
        nested = _first_disposition(m.group(1))
        if nested is not None and nested[1] != "o":
            kind = nested[1]
    if kind == "t":
        return "FINISHED", "completed: true"
    if kind == "f":
        return "UNFINISHED", "completed: false"
    raw = m.group(1)
    if _COMPLETED_FALSE.search(frontmatter):
        return "UNFINISHED", f"completed: false beside outcome: {raw[:60]}"
    word = raw.strip().strip("`*").split()[0].rstrip(":,;(").lower()
    # Unambiguous negatives. These are not guesses: each states plainly that the work did not
    # finish, and leaving them UNREADABLE buries a clear answer under the bucket reserved for
    # words nobody can interpret. Anything outside both sets stays UNREADABLE by design.
    if word.startswith(("blocked", "pulled", "not-", "partial", "incomplete", "deferred", "failed")):
        return "UNFINISHED", f"outcome: {raw[:60]}"
    if word in _TERMINAL_OUTCOMES:
        # A terminal first word is only as good as its qualifier. `confirm-and-close (partial —
        # closure deferred, not blocked)` says plainly that closure did NOT happen, and reading its
        # first word alone reports RECYCLED, whose every prescribed repair asserts a closure the
        # tree does not show. Measured on project-rag-ue-addon: an XS verified two of four next
        # steps and deferred the rest behind a sibling baton.
        qualifier = _QUALIFIED.search(raw)
        if qualifier:
            return "UNFINISHED", f"outcome: {raw[:60]} ({qualifier.group(0).lower()})"
        return "FINISHED", f"outcome: {raw[:60]}"
    return "UNREADABLE", f"outcome: {raw[:60]}"


def _slot_order(run_dir: Path, rec: Path):
    """`coordinator_core.ops.dispatch_emit.slot_order.slot_order`, imported rather than
    re-derived.

    This function used to be the
    sole definition, loaded by `emit-wave-fire.py::_slot_order_fn` via a by-path
    `importlib.util` sibling load. It now lives in `coordinator_core` and both files import it
    from there; this wrapper stays so every existing call site in this module keeps working
    unchanged.

    Engine import happens here, inside a function, never at module scope -- keeps this module's
    body pure so `serve_classifier` still classifies this file warm-servable.
    """
    import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_colocated_engine_on_path

    require_colocated_engine_on_path(__file__)
    from coordinator_core.ops.dispatch_emit.slot_order import slot_order

    return slot_order(run_dir, rec)


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
    # timestamp-named, so lexical order is chronological order between runs; WITHIN one run the
    # records sit in per-fire slot directories and `_slot_order` puts those in wave order, because
    # a re-plan of one baton in a later wave of the SAME run is now a second record too.
    latest: dict = {}
    for run_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        if exclude_run and run_dir.name == exclude_run:
            continue
        for rec in sorted(run_dir.rglob("*.execution.md"), key=lambda r: _slot_order(run_dir, r)):
            stem = rec.name[: -len(".execution.md")]
            candidates = by_slug.get(stem, ())
            if not candidates:
                continue
            rec_path = _record_handoff_path(rec.read_text(encoding="utf-8", errors="replace"))
            for bid in candidates:
                # A sibling handoff sharing this id's slug is not this record's baton. Only
                # skip when BOTH sides name a path and they disagree -- a record or a gate row
                # naming no path falls back to the id match this check has always made, because
                # penalizing an unnamed path is how a legitimate single-candidate id starts
                # reading UNVERIFIED for no reason.
                bid_path = (live or {}).get(bid, {}).get("path")
                if rec_path and bid_path and rec_path != _norm_path(str(bid_path)):
                    continue
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


def _keys(path: Path) -> dict:
    """Top-level `key: value` pairs of a record's frontmatter, first occurrence wins."""
    out = {}
    for line in _frontmatter(path.read_text(encoding="utf-8", errors="replace")).splitlines():
        m = _FM_KEY.match(line)
        if m and m.group(1) not in out:
            out[m.group(1)] = m.group(2).strip("'\"")
    return out


def _terminal(keys: dict) -> bool:
    return keys.get("status") == "consumed" or keys.get("deployment_state") in _TERMINAL_DEPLOYMENT


def resurrected(repo_root: Path, baton_ids, live, archive_root: str = "archive/handoffs"):
    """Candidates whose record is already archived in a terminal state. Pure reads, no verdict on
    fire: RESURRECTED on a basename match, SHARED-ID (advisory) on a `deliverable_id` match against
    a record that ended its deliverable. An archived copy that is the candidate's own `predecessor`
    is its chain, not a duplicate. Without the gate report's paths and candidacy nothing is read."""
    root = repo_root / archive_root
    if live is None or not root.is_dir():
        return []
    by_name, by_deliverable = {}, {}
    for rec in sorted(root.rglob("*.md")):
        keys = _keys(rec)
        if not _terminal(keys):
            continue
        entry = (_norm_path(str(rec.relative_to(repo_root))), keys, rec.name)
        by_name.setdefault(rec.name, []).append(entry)
        if keys.get("deliverable_id") and keys.get("deployment_state") in _DELIVERABLE_ENDED:
            by_deliverable.setdefault(keys["deliverable_id"], []).append(entry)

    findings = []
    for bid in baton_ids:
        row = live.get(bid) or {}
        if not row.get("candidate") or not row.get("path"):
            continue
        record = _norm_path(str(row["path"]))
        name = Path(record).name
        state, hits = "RESURRECTED", by_name.get(name, [])
        if not hits:
            live_rec = repo_root / record
            if not live_rec.is_file():
                continue
            keys = _keys(live_rec)
            predecessor = Path(_norm_path(keys.get("predecessor", ""))).name
            state = "SHARED-ID"
            hits = [h for h in by_deliverable.get(keys.get("deliverable_id"), ()) if h[2] != predecessor]
        if hits:
            archived, akeys, _ = hits[0]
            findings.append({
                "baton": bid,
                "record": record,
                "state": state,
                "archived": archived,
                "evidence": f"status: {akeys.get('status')}, deployment_state: {akeys.get('deployment_state')}"
                + (f" (+{len(hits) - 1} more archived)" if len(hits) > 1 else ""),
            })
    return findings


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
            "path": b.get("path"),
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
    ap.add_argument("--archive-root", default="archive/handoffs", help="repo-relative baton archive")
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

    archived = resurrected(repo_root, ids, live, args.archive_root)
    finished = [f for f in findings if f["state"] == "FINISHED"]
    unverified = [f for f in findings if f["state"] == "UNVERIFIED"]
    repaired = [f for f in findings if f["state"] == "REPAIRED"]
    raised = [a for a in archived if a["state"] == "RESURRECTED"]
    shared = [a for a in archived if a["state"] == "SHARED-ID"]
    verdict = ("RECYCLED" if finished else "RESURRECTED" if raised
               else "UNVERIFIED" if unverified else "CLEAN")

    if args.json:
        print(json.dumps({"verdict": verdict, "scanned": len(ids), "recycling": len(finished),
                          "repaired": len(repaired), "unverified": len(unverified),
                          "resurrected": len(raised), "shared_id": len(shared),
                          "findings": findings, "archive_findings": archived}, indent=2))
    else:
        head = f"recycle-check: {verdict} — {len(finished)} of {len(ids)} baton(s) recycling"
        if repaired:
            head += f", {len(repaired)} already repaired"
        if unverified:
            head += f", {len(unverified)} unverified (no --gate-report, candidacy unchecked)"
        if raised:
            head += f", {len(raised)} resurrected from the archive"
        if shared:
            head += f", {len(shared)} sharing a finished deliverable_id"
        print(head)
        for a in archived:
            tag = "RESURRECT" if a["state"] == "RESURRECTED" else "shared-id"
            print(f"  {tag} {a['baton']}")
            print(f"          {a['record']}")
            print(f"          archived: {a['archived']}  {a['evidence']}")
        if raised:
            print(
                "  repair  a resurrected baton's archived copy is the truth. Remove the live copy, or\n"
                "          re-archive it if it carries edits the archive lacks; never fire on it."
            )
        if shared:
            print(
                "  note    a shared deliverable_id is advisory: successors and fan-out siblings share\n"
                "          one by design. Read the archived record; if it finished this baton's work,\n"
                "          the live one is a stale duplicate."
            )
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
                "            3. the record says the remaining work is SEQUENCED BEHIND another\n"
                "               baton, and no blocked_by edge says so — the repair is the edge, not\n"
                "               a stamp. Stamping here asserts a closure the tree does not show.\n"
                "               Adding it is a coupled write: blocked_by, deployment_state\n"
                "               awaiting_gate, and pickup_ready false, all three or none.\n"
                "          Dropping it from this wave by hand leaves the same baton to recycle into\n"
                "          the next one."
            )
    return EXIT_RECYCLED if (finished or unverified or raised) else EXIT_CLEAN


if __name__ == "__main__":
    sys.exit(main())
