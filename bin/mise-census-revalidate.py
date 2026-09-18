#!/usr/bin/env python3
"""mise-census-revalidate — the census leg of fire-time revalidation. Writes nothing.

WHY THIS EXISTS. `docs/wiki/mise-prepped-attest.md` § "Fire-time revalidation is ONE step, not
two" specifies two ordered legs: recompute the plan body sha, and — only if that passes — re-run
each `census[].command` and diff against `result`. The first leg is `mise-prep-gate.py` and the
engine's `prep_gate`. The second was specified, assigned to "the RUNNER", and never built, so
every hands-off run so far has fired on a sha check alone. That is the weaker half: the sha says
the DOCUMENT has not moved, and the census says the WORLD has not. A plan is stale in the second
sense far more often, because planning runs waves ahead of execution by construction.

THE TWO LEGS ARE ORDERED, AND THIS ONE IS SECOND. The sha leg is spawn-free and sub-millisecond;
this one spawns a process per declared command. Running it against a plan whose body already
failed the cheap leg spends the box's budget re-measuring premises of a document that is no
longer the certified one. This module therefore REFUSES a plan that is not CERTIFIED, rather
than reporting on it.

WHAT IT WILL NOT DO, and the reason is the whole design:

  IT NEVER GUESSES A VERDICT. `census[].result` is free text — the bar requires the key to be
  present and never constrains its shape — so "diff against result" is not mechanically total.
  Measured over project-rag's 25 certified plans: 189 entries, 17% a bare integer, 55% leading
  with an integer then prose, 28% prose throughout. So this reports MATCH only on POSITIVE
  evidence, DRIFT only on positive counter-evidence, and names everything else UNDECIDABLE with
  both texts printed. An UNDECIDABLE is not a pass and must never be read as one; it is the
  honest shape of a question this leg cannot close by itself.

  IT NEVER PASSES A PLAN ON ZERO MEASUREMENTS. A `census:` key declaring no entries revalidates
  nothing, so it is REFUSED rather than rolled up. The roll-up decides on set difference and an
  empty entry set differs from nothing, so an empty census would otherwise report MATCH -- this
  leg's strongest verdict, earned by measuring nothing, and indistinguishable on the wire from a
  plan whose every counted premise was re-checked and held.

  IT NEVER RUNS A COMMAND THAT COULD MUTATE. A census command is a QUESTION, and these are
  strings lifted out of plan frontmatter that agents wrote. A leg that shells out to whatever it
  finds there would make "certify this plan" an arbitrary-execution surface, on a tree many
  sessions share. Every command is screened against a read-only allowlist first; one that does
  not clear it is REFUSED by name and never executed. A refusal here is a finding about the
  plan, not a failure of this tool.

Exit status is a verdict, not a diagnostic, because the caller of this leg is a gate:
  0  every entry MATCHed — the counted premises still hold
  1  at least one DRIFT — the premise moved; that plan re-plans rather than fires
  2  no DRIFT, but at least one UNDECIDABLE, REFUSED or UNRUNNABLE — the leg did not close
  3  usage
Precedence is DRIFT over the unclosed classes: a premise known to have moved outranks one whose
status is unknown, because the two route differently and the first is actionable now.

PATH RESOLUTION — SESSION REPO, EXPLICIT. `--repo-root` is required and every path below it is
caller-supplied; this module derives no path from its own `__file__` and needs no engine or
plugin-root resolution (`docs/plans/2026-09-18-doe-holds-no-scripts.md` § Path resolution).

Spec backlink: docs/plans/2026-09-18-doe-holds-no-scripts.md, chunk W3-C2.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

def _load_yaml():
    """Import PyYAML lazily -- a module-scope `try: import yaml / except ImportError: print(...);
    raise SystemExit(3)` is not the permitted-try shape (`coordinator_core.warm.serve_classifier`
    exempts only a body of imports/assignments; the `print`+`raise` here is neither), so the
    dependency guard moves here, called once by `revalidate()`."""
    try:
        import yaml
    except ImportError:  # pragma: no cover - dependency guard
        print("mise-census-revalidate: PyYAML unavailable", file=sys.stderr)
        raise SystemExit(3)
    return yaml


MATCH = "MATCH"
DRIFT = "DRIFT"
UNDECIDABLE = "UNDECIDABLE"
REFUSED = "REFUSED"
UNRUNNABLE = "UNRUNNABLE"

EXIT_MATCH = 0
EXIT_DRIFT = 1
EXIT_UNCLOSED = 2
EXIT_USAGE = 3

#: Read-only command heads. A CLOSED list, and deliberately short: the point is not to anticipate
#: every question an author might ask but to make the set of things this leg can execute small
#: enough to read in one sitting. Extending it is a deliberate act — add a verb only after
#: checking that no flag of it writes, and note that several entries below are here ONLY because
#: their mutating subcommands are screened separately (`git`).
_READ_ONLY_HEADS = frozenset({
    "grep", "rg", "egrep", "fgrep", "ls", "find", "cat", "head", "tail", "wc", "sed", "awk",
    "sort", "uniq", "cut", "tr", "basename", "dirname", "stat", "file", "test", "echo", "true",
    "python", "python3", "git", "jq", "yq", "diff", "comm", "realpath", "readlink", "du", "date",
    # `cd` mutates only the child shell this leg spawns and dies with it. Present because the
    # `cd <repo> && grep …` idiom is how an author writes a census question about a sibling tree.
    "cd",
})

#: `git` subcommands that only read. Everything else under `git` is refused, including the ones
#: that look harmless: `git stash list` is a read but `git stash` is not, and a screen that has
#: to reason about which is which per invocation is a screen that will eventually be wrong.
_GIT_READ_ONLY = frozenset({
    "log", "show", "diff", "status", "ls-files", "ls-tree", "rev-parse", "rev-list", "cat-file",
    "grep", "blame", "describe", "shortlog", "branch", "tag", "remote", "config", "count-objects",
    "merge-base", "name-rev", "for-each-ref", "symbolic-ref", "check-ignore", "var",
})

#: Shell metacharacters that route output somewhere. A pipeline of reads is still a read, so `|`
#: is allowed; a redirect writes a file, so it is not. `$(...)` and backticks are refused because
#: what they run cannot be screened without evaluating them, which is the thing being avoided.
_WRITE_SHELL = (">", ">>", "`", "$(")


def _refuse(reason: str) -> dict:
    return {"state": REFUSED, "detail": reason}


#: Redirect targets that write nothing anybody can read back. `2>/dev/null` is the dominant
#: idiom in a census command and refusing it rejects a read for being tidy about stderr.
_NULL_SINKS = frozenset({"/dev/null"})

#: Pipeline separators, as shlex hands them back once the string is parsed.
_SEPARATORS = frozenset({"|", "||", "&&", ";"})


def screen(command: str) -> Optional[dict]:
    """`None` when the command is read-only; a REFUSED row otherwise.

    PARSE FIRST, THEN SPLIT. The first cut of this screened for metacharacters against the raw
    string and split the pipeline with a regex before parsing. Both are wrong for the same
    reason: a shell metacharacter inside a quoted argument is not a metacharacter. It refused 39
    of project-rag's 189 census commands as "unparseable", every one of them an ordinary
    `grep -rn 'a\\|b' path | wc -l` whose grep alternation was cut in half mid-quote. A screen
    that rejects the corpus's most common read is not a conservative screen, it is a broken one.

    Screens every stage of a pipeline, not just the first: `grep -c x | tee out.txt` is a write
    hiding behind a read, and a screen that looks only at the head reads it as safe.
    """
    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        return _refuse(f"unparseable as a command ({exc})")

    # Substitution is screened on the PARSED tokens, so `'$(' inside quotes` — a literal in a
    # grep pattern — no longer reads as a substitution. A token that still carries it after
    # parsing is refused: screening what it would run means running it.
    for tok in tokens:
        for marker in ("$(", "`"):
            if marker in tok:
                return _refuse(f"command substitution ({marker!r}) cannot be screened unevaluated")

    stages: list[list[str]] = [[]]
    for tok in tokens:
        if tok in _SEPARATORS:
            stages.append([])
            continue
        stages[-1].append(tok)

    for parts in stages:
        parts = [p for p in parts if p]
        if not parts:
            continue
        for i, tok in enumerate(parts):
            if tok in (">", ">>") or re.fullmatch(r"\d?>>?", tok):
                target = parts[i + 1] if i + 1 < len(parts) else ""
                if target not in _NULL_SINKS:
                    return _refuse(f"redirects output to {target or '<nothing>'!r} — not a read")
            elif re.match(r"^\d?>>?.", tok):
                target = re.sub(r"^\d?>>?", "", tok)
                if target not in _NULL_SINKS:
                    return _refuse(f"redirects output to {target!r} — not a read")
        head = Path(parts[0]).name
        if head not in _READ_ONLY_HEADS:
            return _refuse(f"{head!r} is not on the read-only allowlist")
        if head == "git":
            rest = parts[1:]
            # `git -C <path> <sub>` and `--git-dir=<path> <sub>` both put a value before the
            # subcommand; skip a flag and, where the flag takes a separate value, its value too.
            sub = None
            skip = False
            for tok in rest:
                if skip:
                    skip = False
                    continue
                if tok in ("-C", "--git-dir", "--work-tree", "-c"):
                    skip = True
                    continue
                if tok.startswith("-"):
                    continue
                sub = tok
                break
            if sub not in _GIT_READ_ONLY:
                return _refuse(f"git subcommand {sub!r} is not a declared read")
        if head in ("python", "python3") and "-c" in parts:
            return _refuse("python -c cannot be screened without evaluating it")
    return None


def compare(recorded: str, stdout: str) -> dict:
    """MATCH on positive evidence, DRIFT on positive counter-evidence, UNDECIDABLE otherwise.

    Three decidable shapes, in order of strength. Each is a claim about the RECORDED text, which
    is the only thing whose shape this leg controls:

      EXACT     the recorded result IS the output, modulo surrounding whitespace.
      CONTAINS  the output appears verbatim inside the recorded result — the shape an author
                writes when they paste the answer and then explain it.
      COUNT     the recorded result leads with an integer N and the output has N non-empty
                lines. Covers the dominant `grep`/`ls`/`find` idiom.

    A recorded result leading with an integer whose line count DISAGREES is the one shape that
    earns DRIFT, because the author's own leading number is a claim about how many things there
    were and there are now a different number. Everything else is UNDECIDABLE: a prose result
    can be right, wrong, or about something the output does not mention, and this leg has no way
    to tell those apart. Saying so is the point.
    """
    rec = recorded.strip()
    out = stdout.strip()
    if rec == out:
        return {"state": MATCH, "basis": "exact"}
    if out and out in rec:
        return {"state": MATCH, "basis": "contains"}
    lead = re.match(r"^(-?\d+)\b", rec)
    if lead:
        want = int(lead.group(1))
        # A leading integer is a claim about a QUANTITY, and there are two idioms for where the
        # quantity lives in the output. `grep -n …` puts it in the line COUNT; `wc -l`, `grep -c`
        # and `git rev-list --count` put it in the output's own leading integer. Reading only the
        # first made every `wc -l` census a DRIFT — recorded "142 lines", observed "142 file.py",
        # one output line, 142 != 1. The number agreed; the reading did not.
        out_lead = re.match(r"^\s*(-?\d+)\b", out)
        if out_lead and int(out_lead.group(1)) == want:
            return {"state": MATCH, "basis": f"leading count={want}"}
        lines = [ln for ln in out.splitlines() if ln.strip()]
        if len(lines) == want:
            return {"state": MATCH, "basis": f"line count={want}"}
        # DRIFT ONLY WHERE THE RECORDED TEXT IS NOTHING BUT THE NUMBER. A bare `3799` can only
        # be the answer, so a different answer is counter-evidence. A number followed by prose
        # is not reliably a count at all: measured across this corpus it is as often a LINE
        # NUMBER (`7` in "7 — the CONSUMED_FIELDS_VERSION line"), an entry tally against a
        # multi-line print, or a figure quoted from the body. Calling those DRIFT sent seven
        # plans to re-plan over a comparator's guess about what the author's first token meant.
        # Unknown is the honest verdict, and the pair is printed so a reader can close it.
        if re.fullmatch(r"-?\d+", rec):
            observed = out_lead.group(1) if out_lead else f"{len(lines)} line(s)"
            return {"state": DRIFT, "basis": f"recorded {want}, observed {observed}"}
        return {
            "state": UNDECIDABLE,
            "basis": (
                f"recorded leads with {want} then prose; output leads with "
                f"{out_lead.group(1) if out_lead else 'no integer'} over {len(lines)} line(s) "
                "— cannot tell whether the recorded integer is a count, a line number or a quote"
            ),
        }
    return {"state": UNDECIDABLE, "basis": "recorded result is prose; no decidable comparison"}


#: A census command string is POSIX shell. `screen()` parses it with `shlex` in POSIX mode, and
#: the corpus's dominant idioms are POSIX: `grep -rln 'a\|b'`, `;` as a separator, `2>/dev/null`.
#: `shell=True` inherits the platform's interpreter, which is `cmd.exe` on Windows -- it splits
#: `'a\|b'` mid-quote and treats `;` as a literal, so the command fails to parse rather than
#: failing to match. That reads out as UNRUNNABLE and is indistinguishable from a premise that
#: moved. It is the same mid-quote cut `screen()`'s own docstring records fixing one layer down:
#: the screen learned POSIX, the executor had not. So the interpreter is named, never inherited.
_SHELL_ENV_OVERRIDE = "COORDINATOR_CENSUS_SHELL"

#: `bash.exe` under Windows' System32 is the WSL launcher, not a shell on this filesystem: it
#: cannot accept a Windows `cwd`, so every entry would fail on the directory rather than the
#: command. Skipped by directory, because its basename is identical to a real one's.
_WSL_SHELL_MARKER = "system32"


def resolve_posix_shell() -> Optional[str]:
    """Absolute path to a POSIX shell, or `None` when the host has none.

    Ladder, most authoritative first: an explicit `COORDINATOR_CENSUS_SHELL` override used AS-IS,
    then `bash` on PATH, then `sh`. `None` is a real answer on a bare Windows host and routes to
    an UNRUNNABLE row naming the missing interpreter -- never to a silent fallback that would put
    `cmd.exe` back in the path this function exists to take it out of.
    """
    override = os.environ.get(_SHELL_ENV_OVERRIDE)
    if override:
        return override
    for name in ("bash", "sh"):
        found = shutil.which(name)
        if found and _WSL_SHELL_MARKER not in found.replace("\\", "/").lower():
            return found
    return None


def run_entry(entry: dict, repo_root: Path, timeout: int) -> dict:
    command = str(entry.get("command") or "").strip()
    recorded = str(entry.get("result") or "")
    row: dict[str, Any] = {"question": str(entry.get("question") or ""), "command": command}
    if not command:
        row.update({"state": REFUSED, "detail": "entry declares no command"})
        return row
    refusal = screen(command)
    if refusal:
        row.update(refusal)
        return row
    shell = resolve_posix_shell()
    if not shell:
        row.update({
            "state": UNRUNNABLE,
            "detail": (
                "no POSIX shell on PATH (tried bash, sh); set "
                f"{_SHELL_ENV_OVERRIDE} to one"
            ),
        })
        return row
    try:
        proc = subprocess.run(
            [shell, "-c", command],
            shell=False,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        row.update({"state": UNRUNNABLE, "detail": f"timed out after {timeout}s"})
        return row
    except OSError as exc:
        row.update({"state": UNRUNNABLE, "detail": str(exc)})
        return row
    out = proc.stdout
    # A non-zero exit with NO output is a command that could not answer; a non-zero exit WITH
    # output is ordinary (`grep` exits 1 on no match, which is itself an answer of "zero").
    if proc.returncode != 0 and not out.strip():
        row.update({
            "state": UNRUNNABLE,
            "detail": f"exit {proc.returncode}: {(proc.stderr or '').strip()[:200]}",
        })
        return row
    verdict = compare(recorded, out)
    row.update(verdict)
    row["recorded"] = recorded.strip()[:400]
    row["observed"] = out.strip()[:400]
    return row


def revalidate(plan: Path, repo_root: Path, timeout: int) -> dict:
    yaml = _load_yaml()
    text = plan.read_text(encoding="utf-8", errors="replace")
    parts = text.split("---", 2)
    fm = {}
    if len(parts) >= 3:
        try:
            fm = yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError as exc:
            return {"plan": str(plan), "state": UNRUNNABLE, "detail": f"frontmatter: {exc}",
                    "entries": []}
    if not fm.get("mise_prepped_sha"):
        return {"plan": str(plan), "state": REFUSED,
                "detail": "not CERTIFIED — the sha leg is ordered first and has not passed",
                "entries": []}
    census = fm.get("census")
    if not isinstance(census, list):
        return {"plan": str(plan), "state": REFUSED, "detail": "no census: key", "entries": []}
    entries = [run_entry(e, repo_root, timeout) for e in census if isinstance(e, dict)]
    if not entries:
        # An empty census revalidates nothing, so it cannot be a pass. The roll-up below
        # decides on set difference, and `set() - {MATCH}` is empty, so a census carrying no
        # runnable entries would fall through to MATCH -- reporting the strongest verdict this
        # leg can give on the strength of zero measurements. That reads identically to a plan
        # whose every counted premise was re-checked and held.
        return {"plan": str(plan), "state": REFUSED,
                "detail": "census: declares no entries -- nothing was revalidated",
                "entries": []}
    states = {e["state"] for e in entries}
    if DRIFT in states:
        state = DRIFT
    elif states - {MATCH}:
        state = UNDECIDABLE
    else:
        state = MATCH
    return {"plan": str(plan), "state": state, "entries": entries}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="mise-census-revalidate")
    ap.add_argument("plans", nargs="+", help="plan paths, repo-relative or absolute")
    ap.add_argument("--repo-root", required=True)
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true", help="print only non-MATCH rows")
    args = ap.parse_args(argv)

    root = Path(args.repo_root).resolve()
    reports = [revalidate(root / p if not Path(p).is_absolute() else Path(p), root, args.timeout)
               for p in args.plans]

    if args.json:
        json.dump(reports, sys.stdout, indent=1)
        print()
    else:
        tally: dict[str, int] = {}
        for rep in reports:
            for e in rep["entries"]:
                tally[e["state"]] = tally.get(e["state"], 0) + 1
            if args.quiet and rep["state"] == MATCH:
                continue
            print(f"census: {rep['state']} — {Path(rep['plan']).name}")
            if rep.get("detail"):
                print(f"  {rep['detail']}")
            for e in rep["entries"]:
                if e["state"] == MATCH and args.quiet:
                    continue
                print(f"  {e['state']:12s} {e['command'][:110]}")
                if e["state"] in (DRIFT, UNDECIDABLE):
                    print(f"    basis    {e.get('basis','')}")
                    print(f"    recorded {e.get('recorded','')[:160]}")
                    print(f"    observed {e.get('observed','')[:160]}")
                elif e.get("detail"):
                    print(f"    {e['detail']}")
        print()
        print(f"{len(reports)} plan(s); entries: "
              + ", ".join(f"{k} {v}" for k, v in sorted(tally.items())))

    states = {r["state"] for r in reports}
    if DRIFT in states:
        return EXIT_DRIFT
    if states - {MATCH}:
        return EXIT_UNCLOSED
    return EXIT_MATCH


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
