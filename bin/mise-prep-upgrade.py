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
  falsifier nesting                     a top-level `falsifier:` block moved, bytes
                                        intact, under `prime_exit_criterion:` — the
                                        author wrote the falsifier; only its address
                                        was wrong.
  falsifier.baseline_ref bare sha       ONLY when the prose ref carries exactly one
                                        sha-shaped token and names no repo other than
                                        the plan's own. The prose survives as a YAML
                                        comment on the same line: the schema closes
                                        the falsifier object, so it has no key for it.

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
  a multi-repo or sha-less baseline_ref which sha, in which repo, the baseline was
                                        taken at is the author's to say.

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

GENERATES = []

EXIT_CLEAN = 0
EXIT_RESIDUE = 1
EXIT_USAGE = 2

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

_PLAN_KINDS = frozenset({"plan"})

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
# The gate's own sha predicates, so "already well-shaped" means what the gate means.
from coordinator_core.execute_plan_assemble.falsifier_shape import (  # noqa: E402
    _BASELINE_REF_CROSS_REPO_RE,
    _DISPOSITION_REF_SHA_RE,
)

#: A sha-shaped token inside prose. An all-digit run still counts toward
#: ambiguity (it may be a second sha) but is never itself taken as the sha.
_PROSE_SHA = re.compile(r"(?<![0-9A-Za-z])[0-9a-fA-F]{7,40}(?![0-9A-Za-z])")

#: Fleet repo names a prose ref may qualify a sha with, each to its canonical name.
_REPO_ALIASES = {
    "coordinator-content-repo": "coordinator-content-repo",
    "claude-klabauter": "claude-klabauter",
    "claude-klabauter": "claude-klabauter",
    "claude-klabauter": "claude-klabauter",
    "klabauter": "claude-klabauter",
    "project-rag": "project-rag",
    "coordinator-claude": "coordinator-claude",
}
_REPO_NAME = re.compile(
    # Any `project-*` / `claude-*` word is a repo name too, known or not: an
    # unrecognised repo is still some OTHER repo.
    r"(?<![\w-])("
    + "|".join(sorted(map(re.escape, _REPO_ALIASES), key=len, reverse=True))
    + r"|(?:project|claude)-[a-z0-9][a-z0-9-]*)(?![\w-])",
    re.I,
)
_BASELINE_LINE = re.compile(r"^(?P<indent>[ \t]+)baseline_ref:[ \t]*(?P<value>\S.*?)[ \t]*$", re.M)

_repo_cache: Dict[Path, Optional[str]] = {}

_SIDECAR_BACKREF_KEYS = ("plan",)

_PLAN_FILENAME = re.compile(r"^\d{4}-\d{2}-\d{2}-")
_SIDECAR_SUFFIX = re.compile(r"\.[A-Za-z][A-Za-z0-9_-]*$")


Parsed = Tuple[Optional[Dict[str, Any]], str, Optional[str]]


def parse_frontmatter(text: str) -> Parsed:
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

    stem = path.name[: -len(path.suffix)] if path.suffix else path.name
    if not _PLAN_FILENAME.match(stem):
        return "not a dated plan filename"
    suffix = _SIDECAR_SUFFIX.search(stem)
    if suffix:
        return f"sidecar filename suffix `{suffix.group(0)}`"
    return None


def split_frontmatter(text: str) -> Optional[Tuple[str, str]]:
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    nl = text.find("\n", end + 1)
    return text[4:end], (text[nl + 1 :] if nl != -1 else "")


def plan_repo(path: Path) -> Optional[str]:
    """Canonical name of the repo holding `path` (nearest `.git` ancestor);
    a stat per directory level, cached per plan directory — no spawn."""
    start = path.resolve().parent
    if start not in _repo_cache:
        found: Optional[str] = None
        for anc in (start, *start.parents):
            if (anc / ".git").exists():
                found = _REPO_ALIASES.get(anc.name.lower(), anc.name)
                break
        _repo_cache[start] = found
    return _repo_cache[start]


def bare_baseline_sha(ref: str, own_repo: Optional[str]) -> Optional[str]:
    """The single sha a prose `baseline_ref` unambiguously names for the
    plan's own repo, else None (sha-less, several shas, or another repo named)."""
    shas = _PROSE_SHA.findall(ref)
    if len(shas) != 1 or shas[0].isdigit():
        return None
    for name in _REPO_NAME.findall(ref):
        if _REPO_ALIASES.get(name.lower(), name) != own_repo:
            return None
    return shas[0]


def _misnested_falsifier(fm: Dict[str, Any]) -> bool:
    top = fm.get("falsifier")
    prime = fm.get("prime_exit_criterion")
    return (
        isinstance(top, dict)
        and bool(top)
        and isinstance(prime, dict)
        and "falsifier" not in prime
    )


def falsifier_report(fm: Dict[str, Any], own_repo: Optional[str]) -> Tuple[Dict[str, Any], List[str]]:
    derivable: Dict[str, Any] = {}
    residue: List[str] = []
    prime = fm.get("prime_exit_criterion")
    if not isinstance(prime, dict):
        return derivable, residue
    if _misnested_falsifier(fm):
        derivable["prime_exit_criterion.falsifier(nest)"] = True
        effective = fm["falsifier"]
    else:
        effective = prime.get("falsifier")
    if not isinstance(effective, dict):
        return derivable, residue
    ref = effective.get("baseline_ref")
    if not isinstance(ref, str) or not ref.strip():
        return derivable, residue
    ref = ref.strip()
    if _DISPOSITION_REF_SHA_RE.match(ref) or _BASELINE_REF_CROSS_REPO_RE.match(ref):
        return derivable, residue
    sha = bare_baseline_sha(ref, own_repo)
    if sha is None:
        residue.append(
            f"prime_exit_criterion.falsifier.baseline_ref: {ref!r} names no single "
            "sha of this repo — which baseline, where, is authorship"
        )
    else:
        derivable["prime_exit_criterion.falsifier.baseline_ref"] = (sha, ref)
    return derivable, residue


def _rewrite_baseline_ref(fm_text: str, sha: str, ref: str) -> Optional[str]:
    """Replace the one single-line `baseline_ref:` whose value parses to
    `ref`; None when no such line is uniquely found."""
    hits = []
    for m in _BASELINE_LINE.finditer(fm_text):
        try:
            value = yaml.safe_load(m.group("value"))
        except yaml.YAMLError:
            continue
        if isinstance(value, str) and value.strip() == ref:
            hits.append(m)
    if len(hits) != 1:
        return None
    m = hits[0]
    comment = " ".join(ref.split())
    line = f"{m.group('indent')}baseline_ref: {sha}  # was: {comment}"
    return fm_text[: m.start()] + line + fm_text[m.end() :]


def _nest_falsifier(fm_text: str) -> Optional[str]:
    """Move the top-level `falsifier:` block under a block-style
    `prime_exit_criterion:`, shifting every line by the criterion's child indent."""
    lines = fm_text.split("\n")

    def block(key: str) -> Optional[Tuple[int, int]]:
        starts = [i for i, ln in enumerate(lines) if re.match(rf"^{key}:[ \t]*(#.*)?$", ln)]
        if len(starts) != 1:
            return None
        i = starts[0]
        j = i + 1
        while j < len(lines) and (not lines[j].strip() or lines[j][:1] in (" ", "\t")):
            j += 1
        while j > i + 1 and not lines[j - 1].strip():
            j -= 1
        return i, j

    fal, pec = block("falsifier"), block("prime_exit_criterion")
    if fal is None or pec is None or pec[1] == pec[0] + 1:
        return None
    child = re.match(r"^([ \t]+)", lines[pec[0] + 1])
    if child is None:
        return None
    moved = [child.group(1) + ln if ln.strip() else ln for ln in lines[fal[0] : fal[1]]]
    if fal[0] < pec[0]:
        out = lines[: fal[0]] + lines[fal[1] : pec[1]] + moved + lines[pec[1] :]
    else:
        out = lines[: pec[1]] + moved + lines[pec[1] : fal[0]] + lines[fal[1] :]
    return "\n".join(out)


def upgrade_falsifier(fm_text: str, derivable: Dict[str, Any]) -> str:
    """Apply the falsifier derivations; each is kept only if the reparsed
    frontmatter equals the original with exactly that change made."""
    try:
        if not isinstance(yaml.safe_load(fm_text), dict):
            return fm_text
    except yaml.YAMLError:
        return fm_text
    out = fm_text
    pair = derivable.get("prime_exit_criterion.falsifier.baseline_ref")
    if pair:
        sha, ref = pair
        candidate = _rewrite_baseline_ref(out, sha, ref)
        if candidate is not None:
            expect = yaml.safe_load(out)
            target = expect["falsifier"] if _misnested_falsifier(expect) else expect["prime_exit_criterion"]["falsifier"]
            target["baseline_ref"] = sha
            if yaml.safe_load(candidate) == expect:
                out = candidate
    if derivable.get("prime_exit_criterion.falsifier(nest)"):
        candidate = _nest_falsifier(out)
        if candidate is not None:
            expect = yaml.safe_load(out)
            expect["prime_exit_criterion"]["falsifier"] = expect.pop("falsifier")
            try:
                if yaml.safe_load(candidate) == expect:
                    out = candidate
            except yaml.YAMLError:
                pass
    return out


def body_rests_on_a_count(body: str) -> List[str]:
    prose = _CODEFENCE.sub(" ", body)
    prose = _DATEISH.sub(" ", prose)
    return sorted(set(_COUNTISH.findall(prose)))


def write_targets(body: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for match in _WRITE_TARGET.finditer(body):
        path = _PAREN_TAIL.sub("", match.group("path")).strip().strip("`")
        if path and "/" in path and " " not in path:
            out[match.group("chunk")] = path
    return out


def plan_report(
    path: Path, text: Optional[str] = None, parsed: Optional[Parsed] = None
) -> Dict[str, Any]:
    if text is None:
        text = path.read_text(encoding="utf-8", errors="replace")
    fm, body, error = parsed if parsed is not None else parse_frontmatter(text)
    if error is not None:
        return {"plan": path, "error": error, "derivable": {}, "residue": ["frontmatter"]}
    assert fm is not None

    derivable: Dict[str, Any] = {}
    residue: List[str] = []

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
    f_derivable, f_residue = falsifier_report(fm, plan_repo(path))
    derivable.update(f_derivable)
    residue.extend(f_residue)

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
    match = re.search(r"```yaml plan-tasks\n(.*?)```", text, re.S)
    if not match:
        return None
    try:
        rows = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return []
    return rows if isinstance(rows, list) else []


def apply_derivable(path: Path, derivable: Dict[str, Any]) -> bool:
    text = path.read_text(encoding="utf-8", errors="replace")
    split = split_frontmatter(text)
    if split is None:
        return False
    fm_text, _ = split
    new_fm = upgrade_falsifier(fm_text, derivable)

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
        if not new_fm.endswith("\n"):
            new_fm += "\n"
        out = "---\n" + new_fm.lstrip("\n") + "---\n" + split[1]

    writes = derivable.get("spine.writes") or {}
    for chunk_id, target in writes.items():
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
    path.write_text(out, encoding="utf-8", newline="\n")
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

    targets: List[Tuple[Path, str, Parsed]] = []
    for raw in args.plans:
        p = Path(raw)
        if p.is_dir():
            for candidate in sorted(p.glob("*.md")):
                text = candidate.read_text(encoding="utf-8", errors="replace")
                parsed = parse_frontmatter(text)
                if not_a_plan_reason(candidate, text, parsed) is None:
                    targets.append((candidate, text, parsed))
        elif p.is_file():
            text = p.read_text(encoding="utf-8", errors="replace")
            parsed = parse_frontmatter(text)
            reason = not_a_plan_reason(p, text, parsed)
            if reason is not None:
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
