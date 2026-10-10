"""census-recheck — re-ask a plan's counted premises of HEAD. Writes nothing.

WHY THIS EXISTS. The mise-prep bar records a plan's counted premises as
`question` + `command` + `result` so a count can be RE-ASKED at fire time instead of
trusted. Two surfaces already say re-asking is somebody's job and neither does it:
`commands/mise-en-place.md` § Phase 0 names a certification leg that "re-runs each
`census[].command` and diffs against `result`", and
`skills/pickup/aggregate-rollup.py` states in its own negative-spec that it "does NOT
re-run a plan's `census[]` commands — that is the fire-time census leg and it belongs
to the RUNNER". The bar's runnable half says the same from the third side: it "checks
that the question is ASKABLE", never that the answer still holds.

So the leg is specified three times and implemented zero times. This is that
implementation, and nothing else: one command per entry, its real output, and a diff
against what the plan recorded.

WHAT IT CATCHES THAT THE BAR CANNOT. The bar is pure and spawn-free by design, so a
census that is complete, well-formed, re-askable and WRONG passes it. Measured on
project-rag-ue-addon: three plans gated PREPPED while their own census commands, when
actually run, reported counts contradicting the plan bodies resting on them — a row
whose premise was already discharged on disk, thirteen enumerated file:line sites that
no longer resolved, an exit criterion already satisfied at HEAD. Each would have
dispatched an executor at work that was already done. The bar is not wrong to miss
them; a gate that shells out is not a gate. They are this tool's job.

WHAT IT DELIBERATELY DOES NOT DO. It does NOT scan plan prose for count-shaped claims
and demand citations. That predicate was tried and cut, and the reasons are recorded in
`docs/wiki/lesson-triage/mise-prepped-authoring-bar.md` § What is deliberately not in the bar: it
fires on "three reviewers agreed", misses "the surface is small", teaches authors to
phrase around it, and can only report that something looked wrong rather than what was
missing. A DRIFT row here says exactly what moved, in the author's own command.

IT SPAWNS, AND THAT IS THE POINT. Do not import this into a gate, a hook, or anything
on a session hot path. The bar stays pure; this is fire-time work with a fire-time
cost, and it runs the commands a plan's author wrote — read them before running this
over a corpus you do not control, the same care any `make` target deserves.

Verdicts, one per plan:
  CURRENT     every entry re-ran and matched. The premises still hold.
  DRIFT       an entry re-ran and disagreed. The tree moved; the plan may be stale.
  UNDIFFABLE  an entry ran and its recorded result AGREES with the output, but was
              written as a paraphrase rather than as output, so no re-run can diff it.
              `plan.schema.json` says a paraphrase defeats the field; this names which
              entries did it, without pretending the premise moved.
  UNRUNNABLE  an entry did not execute as written — the field's whole promise is that
              a driver can run it without reconstructing it, so this is a defect in the
              census, not a property of the tree.
  NO-CENSUS   no `census:` key. Not this tool's finding: that is the bar's, and it
              refuses such a plan already.
  DECLARED-EMPTY  `census: []`. A claim that the plan rests on no counted premise.
              Reported distinctly from CURRENT because there is nothing to re-ask, and
              collapsing them would let an unexamined empty read as a verified one.

Exit status is a verdict, not a diagnostic: 0 CURRENT or DECLARED-EMPTY, 1 DRIFT,
2 UNRUNNABLE, 3 usage, 4 NO-CENSUS, 5 UNDIFFABLE. DRIFT and UNRUNNABLE are separated because they
route differently — DRIFT goes to whoever owns the plan's premises, UNRUNNABLE to
whoever wrote the command.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

CURRENT = "CURRENT"
DRIFT = "DRIFT"
UNRUNNABLE = "UNRUNNABLE"
UNDIFFABLE = "UNDIFFABLE"
NO_CENSUS = "NO-CENSUS"
DECLARED_EMPTY = "DECLARED-EMPTY"

EXIT_CURRENT = 0
EXIT_DRIFT = 1
EXIT_UNRUNNABLE = 2
EXIT_USAGE = 3
EXIT_NO_CENSUS = 4
EXIT_UNDIFFABLE = 5

#: A census entry is a read-only query (grep, wc -l, git ls-files), not a build;
#: this generously bounds a corpus sweep.
DEFAULT_TIMEOUT_S = 60


class RecheckError(RuntimeError):
    """A precondition this tool will not guess past."""


def _frontmatter(text: str) -> dict:
    """Local parse, not the engine's split_frontmatter: must run where the engine may
    be unresolvable (a producer box, a shallow clone, a consumer checkout)."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    try:
        loaded = yaml.safe_load(text[3:end])
    except yaml.YAMLError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _normalise(value: str) -> str:
    """Compares on content, ignoring per-line trailing whitespace and outer blank
    lines; interior structure is preserved since a lost line must read as DRIFT."""
    lines = [line.rstrip() for line in str(value).replace("\r\n", "\n").split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


#: An em-dash, or a run of four or more ordinary words. Deliberately crude — its only
#: job is to route a finding to the right person, never to judge whether it is real.
_PROSE = re.compile(r"—|(?:\b[A-Za-z']{2,}\b[ ,;:]+){4,}")


def _is_prose(recorded: str) -> bool:
    """True when the recorded result reads as an explanation rather than as output.

    A false positive costs a correct entry the word UNDIFFABLE instead of DRIFT, and
    prints both values either way — so a reader loses nothing but a label. That is the
    right direction to be wrong in: the alternative is telling someone their tree moved
    when it did not.
    """
    return bool(_PROSE.search(recorded))


def recheck_entry(entry: dict, cwd: Path, timeout_s: int) -> dict:
    """A non-zero exit is NOT itself unrunnable (e.g. `grep -c` exits 1 on a zero
    count, a legitimate recorded premise); only a failed exec or non-termination is."""
    command = str(entry.get("command") or "").strip()
    recorded = _normalise(entry.get("result") or "")
    row = {
        "question": str(entry.get("question") or "").strip(),
        "command": command,
        "recorded": recorded,
        "ref": entry.get("ref"),
    }
    if not command:
        row.update(state=UNRUNNABLE, observed="", detail="entry declares no command")
        return row
    try:
        proc = subprocess.run(
            command, shell=True, cwd=str(cwd), capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        row.update(state=UNRUNNABLE, observed="",
                   detail=f"did not terminate within {timeout_s}s")
        return row
    except (OSError, UnicodeError, subprocess.SubprocessError) as exc:
        row.update(state=UNRUNNABLE, observed="", detail=f"could not execute: {exc}")
        return row

    observed = _normalise(proc.stdout)
    row["observed"] = observed
    row["exit_code"] = proc.returncode

    # The shell ran but the command did not: no answer on stdout, a non-zero exit, and a
    # complaint on stderr. That is UNRUNNABLE, not DRIFT — comparing "" against a recorded
    # count and reporting that the tree moved would send the reader to re-measure a
    # premise when what actually broke is the command.
    #
    # All three conditions are required. Empty stdout with a non-zero exit and a SILENT
    # stderr is the ordinary no-match (`grep -n foo file` finds nothing), which is a
    # legitimate recorded premise and must stay comparable.
    if not observed and proc.returncode != 0 and proc.stderr.strip():
        row.update(state=UNRUNNABLE,
                   detail=f"produced no output and failed (exit {proc.returncode}): "
                          f"{proc.stderr.strip().splitlines()[0][:160]}")
        return row
    if observed == recorded:
        row.update(state=CURRENT, detail=None)
        return row
    # Containment in either direction still counts as a match: verbatim output and
    # output wrapped in a sentence record the same answer.
    if observed and (observed in recorded or recorded in observed):
        row.update(state=CURRENT, detail="observed output is contained in the recorded result")
        return row

    # Neither contains the other. Two very different causes, and they route to
    # different people, so the tool must not collapse them: the tree may have MOVED
    # (DRIFT — the premise owner's problem), or the author may have recorded a
    # PARAPHRASE instead of output (UNDIFFABLE — the census author's).
    #
    # The separator is a property of the RECORDED value, never a guess about whether the
    # two agree. `plan.schema.json` asks for output "verbatim enough to diff a re-run
    # against" and says a paraphrase defeats the field; so the question with a reliable
    # answer is "was this recorded as output, or as prose?" A token-overlap heuristic was
    # tried first and cut — a gloss legitimately omits most of the output, so demanding
    # every token reported DRIFT on entries a human reader could see were consistent, and
    # a check that cries drift at correct entries trains its reader to ignore it.
    if _is_prose(recorded):
        row.update(state=UNDIFFABLE,
                   detail="recorded result is prose, not output — no re-run can diff it. "
                          "Read both and re-record the command's output verbatim.\n"
                          f"      recorded: {recorded!r}\n"
                          f"      observed: {observed!r}")
        return row
    row.update(state=DRIFT,
               detail=f"recorded {recorded!r}, observed {observed!r}"
                      + (f" (exit {proc.returncode})" if proc.returncode else ""))
    return row


def recheck_plan(plan_path: Path, repo_root: Path, timeout_s: int) -> dict:
    try:
        text = plan_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise RecheckError(f"unreadable plan: {plan_path} ({exc})")
    fm = _frontmatter(text)
    if "census" not in fm:
        return {"plan": str(plan_path), "verdict": NO_CENSUS, "rows": []}
    census = fm.get("census")
    if isinstance(census, list) and not census:
        return {"plan": str(plan_path), "verdict": DECLARED_EMPTY, "rows": []}
    if not isinstance(census, list):
        return {"plan": str(plan_path), "verdict": NO_CENSUS, "rows": [],
                "detail": "census: is present but is not a list"}

    rows = [recheck_entry(e if isinstance(e, dict) else {}, repo_root, timeout_s)
            for e in census]
    if any(r["state"] == UNRUNNABLE for r in rows):
        verdict = UNRUNNABLE
    elif any(r["state"] == DRIFT for r in rows):
        verdict = DRIFT
    elif any(r["state"] == UNDIFFABLE for r in rows):
        verdict = UNDIFFABLE
    else:
        verdict = CURRENT
    return {"plan": str(plan_path), "verdict": verdict, "rows": rows}


def report(result: dict) -> str:
    """A DRIFT row prints both the recorded and observed values, since the point of
    recording the command is showing what moved."""
    name = Path(result["plan"]).name
    head = f"census-recheck: {result['verdict']} — {name}"
    if result["verdict"] in (NO_CENSUS, DECLARED_EMPTY):
        detail = result.get("detail")
        tail = {
            NO_CENSUS: "  no census: key — the bar refuses this plan already",
            DECLARED_EMPTY: "  census: [] — a claim that no counted premise exists; "
                            "nothing to re-ask",
        }[result["verdict"]]
        return head + "\n" + (f"  {detail}" if detail else tail)
    lines = [head]
    for i, row in enumerate(result["rows"], 1):
        lines.append(f"  [{i}] {row['state']:10} {row['question'][:88]}")
        if row["state"] != CURRENT:
            lines.append(f"      $ {row['command']}")
            lines.append(f"      {row['detail']}")
    return "\n".join(lines)


def _targets(args: list, repo_root: Path) -> list:
    out = []
    for raw in args:
        p = Path(raw)
        if not p.is_absolute():
            p = repo_root / raw
        if p.is_dir():
            out.extend(sorted(f for f in p.glob("*.md")))
        else:
            out.append(p)
    return out


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(
        prog="census-recheck",
        description="Re-ask a plan's counted premises of HEAD. Writes nothing.",
    )
    parser.add_argument("target", nargs="+", help="plan file(s) or a directory of them")
    parser.add_argument("--repo-root", default=None,
                        help="repo the commands run in (default: cwd)")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S,
                        help=f"per-command timeout in seconds (default {DEFAULT_TIMEOUT_S})")
    parser.add_argument("--json", action="store_true", help="emit the full report as JSON")
    args = parser.parse_args(argv[1:])

    repo_root = Path(args.repo_root).resolve() if args.repo_root else Path.cwd()
    if not repo_root.is_dir():
        print(f"census-recheck: no such repo root: {repo_root}", file=sys.stderr)
        return EXIT_USAGE

    try:
        results = [recheck_plan(p, repo_root, args.timeout)
                   for p in _targets(args.target, repo_root)]
    except RecheckError as exc:
        print(f"census-recheck: {exc}", file=sys.stderr)
        return EXIT_USAGE
    if not results:
        print("census-recheck: no plans matched", file=sys.stderr)
        return EXIT_USAGE

    if args.json:
        print(json.dumps(results, indent=2, sort_keys=True))
    else:
        print("\n".join(report(r) for r in results))

    # Worst verdict wins across a batch: unrunnable outranks drift, since unrunnable is
    # a defect in the instrument and drift is a finding the instrument produced.
    verdicts = {r["verdict"] for r in results}
    if UNRUNNABLE in verdicts:
        return EXIT_UNRUNNABLE
    if DRIFT in verdicts:
        return EXIT_DRIFT
    if UNDIFFABLE in verdicts:
        return EXIT_UNDIFFABLE
    if verdicts == {NO_CENSUS}:
        return EXIT_NO_CENSUS
    return EXIT_CURRENT


if __name__ == "__main__":
    sys.exit(main(sys.argv))
