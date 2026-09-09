#!/usr/bin/env python3
"""mise-prep-upgrade — bring a plan authored before the mise-prep bar up to it.

WHY THIS EXISTS. The bar (`coordinator_core/roadmap/prep_gate.py`) wants four
declarations. Plans authored before it existed carry none of them, because the
generator that produced them did not emit them — measured across two repos:
741 plans, 731 NOT-PREPPED, CENSUS missing on 730. That is a producer gap, not
741 authoring failures, and the producer half is fixed at
`coordinator/bin/coordinator-doc-new.py`. This is the other half: the corpus
already written.

WHAT IT WILL AND WILL NOT DO — the whole design is this line. It writes only
declarations that are ALREADY TRUE OF THE PLAN and derivable from the plan's own
text. It never invents one. The bar's value is that a declaration means
something; a converter that filled `census: []` across a corpus would make 731
plans PASS without making one of them hands-off-ready, which is the
form-filling failure the bar exists to prevent and the "the verifier was itself
wrong" class this fleet has already found instances of.

  DERIVED (written)                     SOURCE, and why it is true and not a guess
  ------------------------------------  ------------------------------------------
  prime_exit_criterion.derived_from     frontmatter `sizing_object:` — the link IS
                                        the sizing this plan was routed from, already
                                        recorded; `derived_from` asks for that link.
  spine row `writes:`                   the chunk's own `**Write target:** <path>`
                                        line, matched by chunk id. The row and the
                                        prose are the same claim in two places; this
                                        moves it to the machine-readable one.
  census: []                            ONLY when the body carries no count-shaped
                                        claim at all. `[]` asserts the plan rests on
                                        no counted premise — a claim, so it is written
                                        only where the text supports it.

  REFUSED (reported, never written)     WHY
  ------------------------------------  ------------------------------------------
  prime_exit_criterion.statement        a falsifiable outcome sentence is authorship.
                                        No placeholder: the gate refuses those now
                                        (`prep_gate.is_placeholder`), deliberately.
  census entries                        question + command + result. The command must
                                        be re-runnable; one reconstructed from prose
                                        cannot tell drift from a differently-phrased
                                        query, which is the whole reason it is recorded.
  external_gate[].requires              `landed-work` vs `commit-in-owner-repo` decides
                                        whether a plan is refused outright. That is a
                                        judgment about another repo's ownership.
  a missing spine                       a plan with no `yaml plan-tasks` block declares
                                        no scope; inventing rows would invent scope.

WHAT IS A PLAN — and what this tool refuses to have an opinion about.
`docs/plans/` is not a directory of plans. It also holds the index, the readme,
and a review/analysis sidecar per plan (`<plan-stem>.prior-art-check.md`,
`.plan-coverage-check.md`, `.sonnet-review.md`, `.node-map.md`, …). Those are
another surface's records; the mise-prep bar does not apply to them, so gating
them produced ERROR lines that were pure noise — and noise in an error tally is
worse than silence, because it hides the real defects the tally exists to show.

The discriminant is the frontmatter, and it is NOT `kind: plan` — measured, only
42 of 559 real plans across the two repos declare a `kind:` at all. The corpus
says it the other way round:

  * a SIDECAR declares what it is — `kind: prior-art-check`,
    `plan-coverage-check`, `staff-eng-review`, `eng-director-review`,
    `sonnet-review`, `roadmap-overview`;
  * a kind-less sidecar still names the plan it is ABOUT, in a top-level
    `plan:` backref. No plan in either corpus carries one;
  * a PLAN declares neither: no `kind:` (or `kind: plan`) and no `plan:` backref.

Where the frontmatter is absent or unparseable the file cannot answer, so the
FILENAME answers, conservatively: a dated `YYYY-MM-DD-…` stem with no trailing
`.<word>` sidecar suffix is still treated as a plan and still reported as an
error. A broken plan is a defect this tool must surface; only a file that is
demonstrably not a plan is dropped.

Dropped how depends on how it was named, because the two are different intents.
GLOBBED from a directory: skipped silently, and not counted in the `unreadable`
tally — it was never this tool's business. Named EXPLICITLY on the command line:
never silent. You asked about that file, so you get an answer about that file —
it says the file is not a plan and exits 2 (usage).

Exit status: 0 nothing left to author, 1 residue remains (the normal outcome),
2 usage. `--check` writes nothing and reports what would change.

Budget: pure reads plus one rewrite per plan. Zero spawns, no git, no engine
dispatch — it imports the same pure reader the gate does so the two cannot
disagree about what a plan declares.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

EXIT_CLEAN = 0
EXIT_RESIDUE = 1
EXIT_USAGE = 2

#: A chunk's write target in the body, e.g. `**Write target:** path/to/file (new)`.
#: The trailing parenthetical is the template's `(new|edit)` marker, dropped.
_WRITE_TARGET = re.compile(
    r"^###\s+(?P<chunk>[A-Za-z]+\d+[a-z]?)\b.*?^\*\*Write target:\*\*\s*(?P<path>[^\n]+?)\s*$",
    re.M | re.S,
)
_PAREN_TAIL = re.compile(r"\s*\((?:new|edit|new\|edit)\)\s*$", re.I)

#: Count-shaped claims. A bare integer >= 2 that is NOT a date part, a version, a
#: sha, a percentage-of-a-version, or a path segment. Deliberately OVER-BROAD: a
#: false positive costs one plan a hand-authored census, a false negative writes
#: `census: []` onto a plan that does rest on a count — asymmetric, so this errs
#: toward refusing to declare.
_COUNTISH = re.compile(r"(?<![\w./-])(\d{2,6})(?![\w./-])")
_DATEISH = re.compile(r"\b20\d{2}-\d{2}-\d{2}\b")
_CODEFENCE = re.compile(r"```.*?```", re.S)

#: `kind:` values that are still a plan. A file that declares any OTHER kind is
#: declaring itself a sidecar, and is taken at its word.
_PLAN_KINDS = frozenset({"plan"})

#: Top-level keys by which a kind-less sidecar names the plan it is about. A
#: plan does not point at a plan; measured, no plan in either corpus has one.
_SIDECAR_BACKREF_KEYS = ("plan",)

#: Filename fallback, used ONLY when the frontmatter cannot answer. A plan is
#: dated; a sidecar appends `.<word>` to its plan's stem. The suffix must start
#: with a letter so a version in the slug (`…-v1.2-example-repo-asks`) stays a plan.
_PLAN_FILENAME = re.compile(r"^\d{4}-\d{2}-\d{2}-")
_SIDECAR_SUFFIX = re.compile(r"\.[A-Za-z][A-Za-z0-9_-]*$")


#: `(frontmatter_mapping, body, error)` — exactly one of mapping/error is set.
Parsed = Tuple[Optional[Dict[str, Any]], str, Optional[str]]


def parse_frontmatter(text: str) -> Parsed:
    """Parse the frontmatter once. See `Parsed`.

    Every file is classified and then reported, and both need this. It is parsed
    ONCE and the result carried between them: parsing twice per file cost a
    measured ~20% of a whole-corpus run, and a cache cannot recover it because
    the two passes are a whole corpus apart, not adjacent.
    """
    split = split_frontmatter(text)
    if split is None:
        return None, "", "no frontmatter block"
    fm_text, body = split
    try:
        loaded = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as exc:
        return None, body, f"frontmatter does not parse: {type(exc).__name__}"
    if not isinstance(loaded, dict):
        return None, body, "frontmatter is not a mapping"
    return loaded, body, None


def not_a_plan_reason(path: Path, text: str, parsed: Optional[Parsed] = None) -> Optional[str]:
    """Why this file is not a plan, or None when it is one (or must be tried).

    Returning None is the conservative answer: anything that could be a plan —
    including one whose frontmatter is broken — comes back None so `plan_report`
    still reports it. Only a file that says it is something else, or is named as
    something else while unable to speak for itself, is refused.
    """
    fm, _, _ = parsed if parsed is not None else parse_frontmatter(text)

    if fm is not None:
        if "kind" in fm and fm["kind"] is not None:
            kind = str(fm["kind"]).strip()
            if kind not in _PLAN_KINDS:
                return f"frontmatter declares `kind: {kind}`"
            return None
        for key in _SIDECAR_BACKREF_KEYS:
            if key in fm:
                return f"frontmatter names the plan it is about (`{key}:`)"
        return None

    # No usable frontmatter — the file cannot say what it is, so the name does.
    stem = path.name[: -len(path.suffix)] if path.suffix else path.name
    if not _PLAN_FILENAME.match(stem):
        return "not a dated plan filename"
    suffix = _SIDECAR_SUFFIX.search(stem)
    if suffix:
        return f"sidecar filename suffix `{suffix.group(0)}`"
    return None


def split_frontmatter(text: str) -> Optional[Tuple[str, str]]:
    """`(frontmatter_text, body)` or None when there is no parseable block."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    nl = text.find("\n", end + 1)
    return text[4:end], (text[nl + 1 :] if nl != -1 else "")


def body_rests_on_a_count(body: str) -> List[str]:
    """Count-shaped claims in the prose, code fences and dates removed.

    Returns the matched numbers. Non-empty means this plan may rest on a counted
    premise, so `census: []` would be a claim the text does not support.
    """
    prose = _CODEFENCE.sub(" ", body)
    prose = _DATEISH.sub(" ", prose)
    return sorted(set(_COUNTISH.findall(prose)))


def write_targets(body: str) -> Dict[str, str]:
    """`{chunk_id: path}` from the body's `**Write target:**` lines."""
    out: Dict[str, str] = {}
    for match in _WRITE_TARGET.finditer(body):
        path = _PAREN_TAIL.sub("", match.group("path")).strip().strip("`")
        # A prose answer ("none", "n/a") is not a path and must not become one.
        if path and "/" in path and " " not in path:
            out[match.group("chunk")] = path
    return out


def plan_report(
    path: Path, text: Optional[str] = None, parsed: Optional[Parsed] = None
) -> Dict[str, Any]:
    """What this plan is missing, and which of it is derivable. Writes nothing."""
    if text is None:
        text = path.read_text(encoding="utf-8", errors="replace")
    fm, body, error = parsed if parsed is not None else parse_frontmatter(text)
    if error is not None:
        return {"plan": path, "error": error, "derivable": {}, "residue": ["frontmatter"]}
    assert fm is not None  # `error is None` is exactly the mapping case.

    derivable: Dict[str, Any] = {}
    residue: List[str] = []

    # --- CENSUS -----------------------------------------------------------
    if "census" not in fm:
        counts = body_rests_on_a_count(body)
        if counts:
            residue.append(
                f"census: body carries {len(counts)} count-shaped claim(s) "
                f"({', '.join(counts[:6])}{'…' if len(counts) > 6 else ''}) — "
                "each needs question/command/result, or an argued `census: []`"
            )
        else:
            derivable["census"] = []

    # --- PRIME_EXIT -------------------------------------------------------
    criterion = fm.get("prime_exit_criterion")
    criterion = criterion if isinstance(criterion, dict) else {}
    has_statement = bool(str(criterion.get("statement") or "").strip())
    has_derived = bool(str(criterion.get("derived_from") or "").strip())
    if not has_derived:
        sizing = str(fm.get("sizing_object") or "").strip()
        if sizing:
            derivable["prime_exit_criterion.derived_from"] = sizing
        else:
            residue.append("prime_exit_criterion.derived_from: no sizing_object to derive from")
    if not has_statement:
        residue.append("prime_exit_criterion.statement: a falsifiable outcome sentence — authorship")

    # --- SPINE ------------------------------------------------------------
    targets = write_targets(body)
    spine_rows = raw_spine_rows(text)
    if spine_rows is None:
        residue.append("spine: no `yaml plan-tasks` block — inventing rows would invent scope")
    else:
        undeclared = [r.get("id") for r in spine_rows if isinstance(r, dict) and "writes" not in r]
        # STRINGIFIED, because a row id is only a string by convention and YAML believes
        # otherwise: an unquoted `id: 0` parses as int, and every later use here — the
        # `targets` lookup, the residue join — assumed str. The join raised TypeError and
        # took the whole invocation down, so a corpus holding ONE such row could not be
        # converted at all, and the crash named a `', '.join` rather than the row. This is
        # the tool a NOT-PREPPED verdict points its author at, so it has to survive the
        # corpus it exists to repair. Falsy-but-real ids (`0`, `"0"`) survive the filter
        # for the same reason: `if i` dropped the row silently.
        undeclared = [str(i) for i in undeclared if i is not None and str(i).strip()]
        recoverable = {i: targets[i] for i in undeclared if i in targets}
        if recoverable:
            derivable["spine.writes"] = recoverable
        unrecoverable = [i for i in undeclared if i not in targets]
        if unrecoverable:
            residue.append(
                f"spine: rows with no writes: and no `**Write target:**` line — "
                f"{', '.join(unrecoverable)}"
            )
    return {"plan": path, "error": None, "derivable": derivable, "residue": residue}


def raw_spine_rows(text: str) -> Optional[List[Any]]:
    """The `yaml plan-tasks` rows, or None when the block is absent."""
    match = re.search(r"```yaml plan-tasks\n(.*?)```", text, re.S)
    if not match:
        return None
    try:
        rows = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return []
    return rows if isinstance(rows, list) else []


def apply_derivable(path: Path, derivable: Dict[str, Any]) -> bool:
    """Write the derived declarations. Returns True when the file changed.

    Frontmatter is edited as TEXT, never re-serialised from the parsed object: a
    round trip through yaml.dump would reflow every unrelated key, reorder the
    mapping and drop every comment, turning a four-line fix into a whole-file
    diff nobody can review.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    split = split_frontmatter(text)
    if split is None:
        return False
    fm_text, _ = split
    new_fm = fm_text

    if "census" in derivable:
        new_fm = new_fm.rstrip("\n") + (
            "\ncensus: []  # no counted premise found in the body at conversion time;"
            "\n            # a claim a reviewer can falsify. Bar: mise-prep-gate.py.\n"
        )
    derived_from = derivable.get("prime_exit_criterion.derived_from")
    if derived_from:
        if re.search(r"^prime_exit_criterion:\s*$", new_fm, re.M):
            new_fm = re.sub(
                r"^(prime_exit_criterion:[ \t]*\n)",
                rf"\1  derived_from: {derived_from}\n",
                new_fm,
                count=1,
                flags=re.M,
            )
        else:
            new_fm = new_fm.rstrip("\n") + (
                f"\nprime_exit_criterion:\n  derived_from: {derived_from}\n"
            )

    out = text
    if new_fm != fm_text:
        out = "---\n" + new_fm.lstrip("\n") + "---\n" + split[1]

    writes = derivable.get("spine.writes") or {}
    for chunk_id, target in writes.items():
        # Anchor on the row's own `id:` so a `writes:` lands in the right row.
        pattern = re.compile(
            rf"(^- id: {re.escape(chunk_id)}\s*$)((?:\n(?!- id:).*)*)", re.M
        )

        def _insert(match: re.Match) -> str:
            head, rest = match.group(1), match.group(2)
            if re.search(r"^\s+writes:", rest, re.M):
                return match.group(0)
            return f"{head}\n  writes: [{target}]{rest}"

        out = pattern.sub(_insert, out, count=1)

    if out == text:
        return False
    path.write_text(out, encoding="utf-8")
    return True


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="mise-prep-upgrade",
        description=(
            "Bring pre-bar plans up to the mise-prep authoring bar by writing the "
            "declarations derivable from the plan's own text. Never invents one."
        ),
    )
    parser.add_argument("plans", nargs="+", help="plan file(s) or a directory of them")
    parser.add_argument("--check", action="store_true", help="report only; write nothing")
    parser.add_argument("--quiet", action="store_true", help="summary only")
    args = parser.parse_args(argv)

    # (path, text). Non-plans are dropped here, and how depends on the intent the
    # command line expressed — see the module docstring's WHAT IS A PLAN section.
    targets: List[Tuple[Path, str, Parsed]] = []
    for raw in args.plans:
        p = Path(raw)
        if p.is_dir():
            for candidate in sorted(p.glob("*.md")):
                text = candidate.read_text(encoding="utf-8", errors="replace")
                parsed = parse_frontmatter(text)
                if not_a_plan_reason(candidate, text, parsed) is None:
                    targets.append((candidate, text, parsed))
                # else: globbed and not a plan — not this tool's business, and
                # not an `unreadable`. Silent by design.
        elif p.is_file():
            text = p.read_text(encoding="utf-8", errors="replace")
            parsed = parse_frontmatter(text)
            reason = not_a_plan_reason(p, text, parsed)
            if reason is not None:
                # Named explicitly: you asked about this file, so you get an
                # answer about this file rather than an empty run.
                print(f"mise-prep-upgrade: not a plan: {raw} — {reason}", file=sys.stderr)
                return EXIT_USAGE
            targets.append((p, text, parsed))
        else:
            print(f"mise-prep-upgrade: no such plan: {raw}", file=sys.stderr)
            return EXIT_USAGE
    if not targets:
        print("mise-prep-upgrade: no plans named", file=sys.stderr)
        return EXIT_USAGE

    changed = 0
    with_residue = 0
    errors = 0
    for path, text, parsed in targets:
        report = plan_report(path, text, parsed)
        if report["error"]:
            errors += 1
            if not args.quiet:
                print(f"  ERROR    {path.name}: {report['error']}")
            continue
        derivable, residue = report["derivable"], report["residue"]
        did = False
        if derivable and not args.check:
            did = apply_derivable(path, derivable)
            if did:
                changed += 1
        elif derivable:
            changed += 1
        if residue:
            with_residue += 1
        if not args.quiet and (derivable or residue):
            verb = "would derive" if args.check else ("derived" if did else "no change")
            print(f"  {path.name}")
            if derivable:
                print(f"    {verb}: {', '.join(sorted(derivable))}")
            for item in residue:
                print(f"    AUTHOR: {item}")

    print(
        f"\nmise-prep-upgrade: {len(targets)} plan(s); "
        f"{changed} {'would change' if args.check else 'changed'}; "
        f"{with_residue} still need authoring; {errors} unreadable"
    )
    if with_residue or errors:
        print(
            "  residue is authorship, not a conversion gap — a census entry or an "
            "exit criterion written by a script would declare what nobody checked."
        )
    return EXIT_RESIDUE if (with_residue or errors) else EXIT_CLEAN


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
