#!/usr/bin/env python3
"""aggregate-rollup — roll a baton's constituent plans up into one fire verdict. Writes nothing.

WHY THIS EXISTS. An aggregate execution baton names N workstreams and declares the run as its
next step. Whether it may fire is not a property of the baton: it is a property of each
constituent PLAN, held in that plan's own `mise_prepped_by/_at/_sha/_findings` attest. So the
roll-up has to be a READ over the plans, performed at the moment the question is asked. A cached
roll-up verdict on the baton would go stale by precisely the mechanism the attest exists to
catch -- the stamp-to-fire window is wide by construction, because planning runs waves ahead of
execution.

THE FIRE RULE, in one line. **Fireable at >=1 certified constituent, and a fire with any
remainder is a PARTIAL-FIRE that names what it excluded.** Requiring all N would reinstate the
starvation pathology the blitz exists to escape: one stubborn plan holding six ready ones. And a
partial fire reported as a completion is the drop-shaped failure that is already recorded as
worse than a refusal.

WHY THE STORED LIST AND THE READ DO NOT FIGHT. The baton is REQUIRED to carry its uncertified
list visibly -- an operator must see the excluded work without querying anything -- and that
list is text, so it can disagree with the plans. The disagreement is made harmless by direction
rather than by freshness: **the stored lists SUBTRACT from the fire set and can never add to
it.** The fire set is `{p : recomputed-read(p) is CERTIFIED} - {p : p is listed uncertified}`,
and withheld rows are the UNION of stored and read. So a stale list can hold back a plan that
has since certified -- which is drift, reported, and a reason to re-mint the baton -- and can
never fire a plan that has not certified. No freshness window is needed and none is offered.

FOUR STATES, READ PER PLAN, and the predicate is a RECOMPUTED sha, never the presence of
`mise_prepped_by`:

  CERTIFIED   four fields present, `mise_prepped_sha` equals the recomputed body sha
  STALE       four fields present, the sha disagrees -- the body moved after the stamp
  UNSTAMPED   no `mise_prepped_*` key at all
  MALFORMED   some of the four present, not all -- a hand-written stamp

STALE and UNSTAMPED are different words on purpose: stale re-gates, unstamped stamps, and a
reader told the wrong noun sends an author to re-stamp a plan whose defects were never
re-checked.

Negative-spec:
  - Does NOT stamp, mint, or write. It returns a verdict and touches no file, ever.
  - Does NOT store its verdict anywhere. There is no roll-up field on the baton and adding one
    would be the cached-certification defect this module exists to avoid.
  - Does NOT re-derive the claimed / `in_flight` exclusion. That rule is the blitz's, applied to
    the candidate set a baton's constituents are drawn from; this module is handed one baton by
    path and enumerates nothing, so a second exclusion vocabulary here would be a second answer
    to a settled question. Those two words appear in this docstring and nowhere in the code
    below it, which is the form the pinning test checks.
  - Does NOT re-run a plan's `census[]` commands. That is the fire-time census leg and it belongs
    to the runner; this module is the pure, spawn-free half.
  - Does NOT read the engine in-process. `canonical_body_sha` is transcribed below (ten lines of
    stdlib) rather than imported, so a roll-up never depends on a sibling checkout being present;
    the transcription's parity with the engine's own recipe is asserted in
    `coordinator/tests/test_aggregate_execution_baton.py`, which may skip, where this may not.
  - Does NOT decide anything about a plan's CONTENT. It reads one attest and one findings list.
  - Does NOT name the run's command. The next step of an aggregate baton is the run by
    definition of the shape; which verb that is belongs to the run's own surface.

Zero subprocess, stdlib plus PyYAML.

Exit status is a verdict, because the caller of a roll-up is a gate, and because the partial case
must be impossible to mistake for the complete one: 0 when every constituent fires with nothing
withheld (FIRE), 1 when the baton fires with a named remainder (PARTIAL-FIRE), 2 when no
constituent certifies and there is nothing to fire (NO-FIRE), 3 on a usage error or a baton that
carries no readable `aggregate_execution` block. 1 is not an error -- it is the honest code for a
run that did part of the work, and a caller that treats 0 as "done" therefore cannot read a
partial fire as a completion.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import yaml

_SCRIPT_DIR = Path(__file__).resolve().parent
_PLUGIN_ROOT = _SCRIPT_DIR.parent.parent
_HOOKS_SCRIPTS_DIR = _PLUGIN_ROOT / "hooks" / "scripts"

CERTIFIED = "CERTIFIED"
STALE = "STALE"
UNSTAMPED = "UNSTAMPED"
MALFORMED = "MALFORMED"

FIRE = "FIRE"
PARTIAL_FIRE = "PARTIAL-FIRE"
NO_FIRE = "NO-FIRE"

EXIT_FIRE = 0
EXIT_PARTIAL_FIRE = 1
EXIT_NO_FIRE = 2
EXIT_USAGE = 3

ATTEST_FIELDS = ("mise_prepped_by", "mise_prepped_at", "mise_prepped_sha", "mise_prepped_findings")

_BODY_DELIMITER_RE = re.compile(r"^---[ \t]*$")


class RollupError(RuntimeError):
    """A fail-loud precondition. `main()` prints `str(exc)` and exits `EXIT_USAGE` -- this module
    never returns a verdict it could not actually compute."""


# ---------------------------------------------------------------------------
# The recipe
# ---------------------------------------------------------------------------


def frontmatter_body_text(file_text: str) -> str:
    """Everything below the SECOND `---` delimiter line — the engine's recipe, transcribed.

    Every line that is `---` alone (optional trailing horizontal whitespace) increments the
    delimiter counter and is itself never emitted; emitted lines are re-terminated with `\\n`
    regardless of the source line's own terminator, so a file with no trailing newline hashes
    identically. Both details are load-bearing for byte-parity, not incidental: a transcription
    that kept a later `---` or preserved the source terminator would produce a different sha for
    the same plan and report it STALE.

    Frontmatter is excluded and that exclusion is load-bearing in its own right: it is what lets a
    stamp survive its own write, and survive every later `status` flip and annotation the plan
    collects between being stamped and being fired. Only a material change to the plan BODY
    invalidates a stamp.
    """
    delimiters = 0
    out: list = []
    for line in file_text.splitlines():
        if _BODY_DELIMITER_RE.match(line):
            delimiters += 1
            continue
        if delimiters >= 2:
            out.append(line + "\n")
    return "".join(out)


def canonical_body_sha(file_text: str) -> str:
    """git-hash-object of the plan body -- the engine's shared recipe, transcribed.

    `git_blob_sha1(frontmatter_body_text(file_text))`. Transcribed rather than imported so a
    roll-up never depends on a sibling checkout; parity with the engine's implementation is
    asserted by test, which is allowed to skip where this is not. NOT a whole-file hash: a
    whole-file hash reports every plan stale the moment its own stamp lands.
    """
    body = frontmatter_body_text(file_text).encode("utf-8")
    header = f"blob {len(body)}\0".encode("ascii")
    return hashlib.sha1(header + body).hexdigest()  # noqa: S324 - git's own object-hash algorithm


def split_frontmatter(file_text: str) -> dict:
    """The document's frontmatter as a mapping, or `{}` when it has none or it does not parse."""
    lines = file_text.splitlines()
    if not lines or not _BODY_DELIMITER_RE.match(lines[0]):
        return {}
    for index in range(1, len(lines)):
        if _BODY_DELIMITER_RE.match(lines[index]):
            try:
                loaded = yaml.safe_load("\n".join(lines[1:index]))
            except yaml.YAMLError:
                return {}
            return loaded if isinstance(loaded, dict) else {}
    return {}


# ---------------------------------------------------------------------------
# The per-plan read
# ---------------------------------------------------------------------------


def certification_state(plan_text: str) -> tuple:
    """`(state, withheld_rows)` for one plan's own bytes.

    The predicate is the RECOMPUTED sha. A present `mise_prepped_by` over a changed body is
    STALE, and reporting it as absent would send its author to re-stamp a plan whose defects were
    never re-checked.
    """
    fm = split_frontmatter(plan_text)
    present = [field for field in ATTEST_FIELDS if field in fm]
    if not present:
        return UNSTAMPED, []
    if len(present) != len(ATTEST_FIELDS):
        return MALFORMED, []
    stamped = str(fm.get("mise_prepped_sha") or "")
    recomputed = canonical_body_sha(plan_text)
    # Review: code-reviewer — EXACT equality, never a prefix match. `mise_prepped_sha`'s schema
    # pattern admits 7-64 hex chars, so an abbreviated digest is a LEGAL value; under a prefix
    # test a 7-character stamp certified a body it had barely witnessed. The engine's own reader
    # for this field (`coordinator_core/roadmap/prep_gate.py :: read_stamp`) compares
    # `recorded_sha.lower() == body_sha.lower()`, and two readers of one field that disagree are
    # worse than either rule alone — this one disagreed in the fail-open direction.
    if not stamped or stamped.strip().lower() != recomputed.lower():
        return STALE, []
    findings = fm.get("mise_prepped_findings")
    rows = [str(row) for row in findings] if isinstance(findings, list) else []
    return CERTIFIED, rows


def fire_verdict(fires: list, excluded_or_uncertified: list, withheld: list) -> str:
    """The three-line FIRE/PARTIAL-FIRE/NO-FIRE rule, over the same three inputs both callers
    already compute: the fire set, whatever it excluded, and whatever it withheld.

    # Review: overengineering-reviewer — exported here so `mise-prep-entry.certify` (which already
    # imports this module by path for `certification_state`) has one place to call rather than a
    # second, identical derivation; this module's own docstring names a third copy as how one of
    # them drifts.
    """
    if not fires:
        return NO_FIRE
    if excluded_or_uncertified or withheld:
        return PARTIAL_FIRE
    return FIRE


# ---------------------------------------------------------------------------
# The roll-up
# ---------------------------------------------------------------------------


def _aggregate_block(baton_text: str) -> dict:
    fm = split_frontmatter(baton_text)
    block = fm.get("aggregate_execution")
    if not isinstance(block, dict):
        raise RollupError(
            "not an aggregate execution baton: no aggregate_execution block "
            "(a baton naming one workstream is an ordinary baton, not an aggregate of one)"
        )
    for key in ("constituents", "uncertified", "withheld_rows"):
        if key not in block:
            raise RollupError(
                f"aggregate_execution has no {key}: key "
                f"(all three are required; nothing to declare is declared as `{key}: []`)"
            )
    if not isinstance(block.get("constituents"), list) or not block["constituents"]:
        raise RollupError(
            "aggregate_execution.constituents is empty — an aggregate of nothing has nothing to run"
        )
    return block


def roll_up(baton_path: Path, repo_root: Path) -> dict:
    """The whole roll-up over one baton. Returns a report; writes nothing.

    The fire set is the recomputed-CERTIFIED plans MINUS the ones the baton lists as uncertified,
    and the withheld-row set is the UNION of what the baton lists and what each fired plan's own
    `mise_prepped_findings` says. Both directions are subtractive on purpose: the stored lists are
    an observation, and an observation may only ever narrow what runs.
    """
    block = _aggregate_block(baton_path.read_text(encoding="utf-8", errors="replace"))
    listed_uncertified = {
        str(entry.get("plan")): str(entry.get("state") or "")
        for entry in block["uncertified"]
        if isinstance(entry, dict) and entry.get("plan")
    }
    listed_withheld: dict = {}
    for entry in block["withheld_rows"]:
        if isinstance(entry, dict) and entry.get("plan"):
            rows = entry.get("rows")
            listed_withheld[str(entry["plan"])] = [str(r) for r in rows] if isinstance(rows, list) else []

    fires: list = []
    excluded: list = []
    withheld: list = []
    drift: list = []

    for entry in block["constituents"]:
        if not isinstance(entry, dict):
            continue
        plan = str(entry.get("plan") or "")
        workstream = str(entry.get("workstream") or "")
        path = plan if Path(plan).is_absolute() else str(repo_root / plan)
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            read_state, read_rows = UNSTAMPED, []
            drift.append((plan, "unreadable — treated as UNSTAMPED, which does not fire"))
        else:
            read_state, read_rows = certification_state(text)

        listed_state = listed_uncertified.get(plan)
        if read_state == CERTIFIED and listed_state is not None:
            # The list excludes what the read admits. Subtractive: the plan is held back.
            drift.append(
                (plan, f"read {CERTIFIED}, listed {listed_state} — held back; re-mint the baton")
            )
            excluded.append((plan, workstream, listed_state))
            continue
        if read_state != CERTIFIED:
            # The recomputed read is the noun, always — a wrong noun routes to the wrong repair.
            if listed_state is None:
                drift.append(
                    (plan, f"read {read_state}, not listed — held back; the baton's list is stale")
                )
            elif listed_state != read_state:
                drift.append(
                    (plan, f"read {read_state}, listed {listed_state} — the recomputed read is the noun")
                )
            excluded.append((plan, workstream, read_state))
            continue

        fires.append((plan, workstream))
        rows = sorted(set(read_rows) | set(listed_withheld.get(plan, [])))
        if rows:
            withheld.append((plan, workstream, rows))

    verdict = fire_verdict(fires, excluded, withheld)

    report = {
        "baton": str(baton_path),
        "verdict": verdict,
        "constituent_count": len(fires) + len(excluded),
        "fires": [{"plan": p, "workstream": w} for p, w in fires],
        "excluded": [{"plan": p, "workstream": w, "state": s} for p, w, s in excluded],
        "withheld": [{"plan": p, "workstream": w, "rows": r} for p, w, r in withheld],
        "drift": [{"plan": p, "note": n} for p, n in drift],
    }
    report["message"] = report_message(report)
    return report


def report_message(report: dict) -> str:
    """One fact per line, the excluded work named, and no line that reads as completion.

    A PARTIAL-FIRE message states what fires and what does not, in that order, because an
    operator who reads only the first line must still learn that something was left out -- which
    is why the count is `N of M` rather than `N`.
    """
    name = Path(report["baton"]).name
    lines = [f"aggregate: {report['verdict']} — {name}"]
    lines.append(
        f"  fires    {len(report['fires'])} of {report['constituent_count']} plan(s)"
    )
    for row in report["fires"]:
        lines.append(f"           {row['plan']}  ({row['workstream']})")
    for row in report["excluded"]:
        lines.append(
            f"  excluded {row['plan']}  {row['state']}  ({row['workstream']})"
        )
    for row in report["withheld"]:
        lines.append(
            f"  withheld {row['plan']}  rows {', '.join(row['rows'])}  ({row['workstream']})"
        )
    for row in report["drift"]:
        lines.append(f"  drift    {row['plan']}  {row['note']}")
    if report["verdict"] != FIRE:
        lines.append("  next     the run fires what is listed above it; the rest rides a successor.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _default_repo_root() -> Path:
    """The repo the invocation is standing in — cwd's git root.

    This module is plugin source resolved live from the doctrine repo, so its own parent names
    that repo from every repo on the box and would be the wrong default.
    """
    # Review: overengineering-reviewer — the cwd-upward `.git` walk is shared via
    # hooks/scripts/repo_root.py (also used by mise-prep-gate.py) rather than a seventh copy.
    if str(_HOOKS_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_HOOKS_SCRIPTS_DIR))
    from repo_root import repo_root

    return repo_root(Path(__file__).resolve().parents[3])


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(
        prog="aggregate-rollup",
        description="Roll a baton's constituent plans up into one fire verdict. Writes nothing.",
    )
    parser.add_argument("baton", help="path to the aggregate execution baton")
    parser.add_argument("--json", action="store_true", help="emit the full report as JSON")
    parser.add_argument(
        "--repo-root", default=None, help="repo to resolve plan paths against (default: cwd's git root)"
    )
    args = parser.parse_args(argv[1:])

    try:
        repo_root = Path(args.repo_root).resolve() if args.repo_root else _default_repo_root()
        baton = Path(args.baton)
        if not baton.is_absolute():
            baton = repo_root / baton
        if not baton.is_file():
            raise RollupError(f"no such baton: {args.baton}")
        report = roll_up(baton, repo_root)
    except RollupError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE

    print(json.dumps(report, indent=2) if args.json else report["message"])

    if report["verdict"] == FIRE:
        return EXIT_FIRE
    if report["verdict"] == PARTIAL_FIRE:
        return EXIT_PARTIAL_FIRE
    return EXIT_NO_FIRE


if __name__ == "__main__":
    sys.exit(main(sys.argv))
