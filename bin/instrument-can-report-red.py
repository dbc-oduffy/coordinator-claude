"""instrument-can-report-red — does a computed verdict reach this instrument's exit path?

WHY THIS EXISTS. A falsifier, gate or probe that goes green is evidence only if it could have
gone red. Three sightings across two repos are one shape: **an instrument whose verdict is
computed but never wired to its exit path.** `inst-07` injects a token into its own fixture and
passes regardless; a release-gates falsifier computes a shim verdict it never feeds into its exit
code. Nothing between authoring such an instrument and trusting its green reads it.

The question is asked INTENT-FREE, and that is the whole reason one surface can serve several
readers: this module never learns what a given instrument is *for*. It reads one file and answers
whether any value the file computes can change the status the file reports. A check that had to
understand the subject would need a new implementation per subject.

THREE CONSUMERS, ONE SURFACE. The pre-review premise check (`coordinator/agents/premise-checker.md`,
question class 4) calls it on a plan's named falsifier before review; the post-hoc
falsifier-integrity review calls it on the instrument a plan shipped; the blitz-convergence corpus
carries the same tell from a shim verdict. Import `verdict_reaches_exit` rather than restating the
predicate — a second implementation is a second thing to keep true.

Negative-spec — what this is NOT:
  - NOT a claim that the instrument is correct. `ARMED` says a computed value reaches the exit,
    never that it measures the right thing. An armed instrument pointed at the wrong substrate is
    `A-DECLARATION-LEVEL-FALSIFIER-CANNOT-SEE-BEHAVIOUR`, which this cannot see.
  - NOT a runner. Nothing here executes, imports or subprocesses the file it reads; deciding
    whether an unknown instrument is safe to run is not a question a static reader gets to answer.
  - NOT a refusal. Every finding is a report, for the caller to act on as it sees fit.
  - NOT a Python-agnostic check. A file it cannot parse is `UNCHECKABLE`, never `ARMED`: an
    instrument this surface cannot read has not thereby been shown to report red.

Stdlib only, zero subprocess, one `ast` pass per file — it runs inside a planning wave alongside
many concurrent sessions, and a reader that costs a process per instrument would not be affordable
on every plan.

Exit status: 0 whenever the analysis ran, whatever it found, because a finding is a report for the
caller to act on and a non-zero exit here would read to a wave driver as a broken step. `--strict`
returns 1 when any file is other than `ARMED`, for the caller that wants this as a gate rather than
a report; 2 means no file could be read at all, which is a broken invocation rather than a finding.
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

# Ordered most-severe first. `verdict` is the first entry that fires; every finding is still
# reported, because a caller reading only the headline would lose the ones underneath it.
# DANGLING_VERDICT cut: 155 findings across 167 files,
# changes no downstream verdict (falsifier-integrity-reviewer.md already maps it to CLEAR), and
# the module's own docstring called it "a question for a reader, not a defect claim."
VERDICTS = (
    "UNCHECKABLE",
    "NO_EXIT_PATH",
    "CONSTANT_EXIT",
    "SEALED_EXIT",
    "ARMED",
)

# A `return` inside one of these is an exit site: the house shape is `sys.exit(main(sys.argv))`,
# so `main`'s return value IS the process status. Named rather than inferred from the
# `__main__` guard, which a file under test may not carry.
_ENTRYPOINT_FUNCTIONS = frozenset({"main"})

# Reading any of these is how a value from OUTSIDE the file reaches the exit. The list is
# deliberately about ORIGIN, not about I/O: `argv`, `environ` and `stdin` are reads of the world,
# and a call to anything at all is a value this reader cannot prove is a constant. That
# conservatism is the correct direction — over-reporting SEALED costs a glance, under-reporting it
# hands back a green from an instrument sealed against the tree.
_WORLD_READS = frozenset({"argv", "environ", "stdin"})


def _literal(node: ast.AST) -> bool:
    """True when the expression can only ever be the constant written here."""
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return all(_literal(e) for e in node.elts)
    if isinstance(node, ast.Dict):
        return all(_literal(k) for k in node.keys if k is not None) and all(
            _literal(v) for v in node.values
        )
    if isinstance(node, ast.UnaryOp):
        return _literal(node.operand)
    if isinstance(node, ast.BinOp):
        return _literal(node.left) and _literal(node.right)
    return False


def _names_in(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


# Pulled out of
# `_Scan._is_entrypoint_trampoline` so the "wrapped" idiom (`sys.exit(asyncio.run(main(...)))`)
# is one case rather than one fixed depth.
#
# BLOCKER) — the
# first version of this recursed through ANY single-argument call. That is not what "wrapper"
# means here: excluding a site as plumbing asserts the wrapper forwards `main`'s value unchanged,
# and an arbitrary single-arg call does not. `sys.exit(jitter(main(argv)))` where `jitter` adds
# `random.randint(...)` was read as plumbing, the site dropped from analysis, and the file
# reported CONSTANT_EXIT over a genuinely varying exit — the same false-clean the fix removed,
# one level of generality out. Only named async runners qualify now; they are the idiom that
# motivated the case, and they return their coroutine's value untouched. An unrecognised wrapper
# is NOT plumbing, so its site counts and the file falls to ARMED: loud and wrong beats quiet
# and wrong for an instrument whose whole job is refusing to certify a check that cannot fail.
_TRAMPOLINE_WRAPPERS = frozenset({
    "asyncio.run", "anyio.run", "trio.run", "asyncio.run_until_complete",
    "loop.run_until_complete",
})


def _dotted_name(func: ast.expr) -> str:
    """`asyncio.run` for an Attribute chain, `run` for a bare Name, "" for anything else."""
    parts = []
    node = func
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    elif parts:
        # A call or subscript at the root (`get_loop().run_until_complete`) — keep the tail only,
        # which will not match the dotted allowlist. Deliberate: an unrecognised root is not a
        # runner we can vouch for.
        return ".".join(reversed(parts))
    return ".".join(reversed(parts))


def _is_entrypoint_call(node: ast.expr) -> bool:
    """True when `node` calls an entrypoint function, or is a NAMED async runner wrapping one
    (`asyncio.run(main())`). Any other wrapper is not plumbing — see the note above."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    callee = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
    if callee in _ENTRYPOINT_FUNCTIONS:
        return True
    dotted = _dotted_name(func)
    if dotted in _TRAMPOLINE_WRAPPERS and len(node.args) == 1 and not node.keywords:
        return _is_entrypoint_call(node.args[0])
    return False


def _reads_the_world(node: ast.AST) -> bool:
    """True when the expression's value could come from outside this file.

    Any `Call` counts. This reader cannot see across a call boundary, and a helper that reads a
    file is indistinguishable here from one that returns a constant — so a call is treated as a
    world read rather than as proof of sealing. `SEALED_EXIT` therefore fires only on an exit
    determined by expressions this file wrote in full, which is the shape it exists to name.
    """
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            return True
        if isinstance(sub, ast.Attribute) and sub.attr in _WORLD_READS:
            return True
        if isinstance(sub, ast.Name) and sub.id in _WORLD_READS:
            return True
    return False


class _Scan(ast.NodeVisitor):
    """One pass: every exit site, every assignment, every computed verdict binding.

    Assignments are collected FLAT — one name-to-expressions map for the whole file, with no
    scope modelling. A reader that resolved scopes would answer a different, harder question
    (which binding reaches this exit) and would still be wrong on any dynamic rebinding. Flat
    over-approximates the influencer set, which errs toward calling an exit armed; the
    counter-pressure is that `SEALED_EXIT` and `CONSTANT_EXIT` are decided on the exit
    expressions themselves, which no over-approximation reaches.
    """

    def __init__(self) -> None:
        self.assigns: dict[str, list[ast.expr]] = {}
        # Each entry: (line, [what this site reports], [tests that decide whether it is reached]).
        # The two are kept APART because they answer different questions. Whether the reported
        # STATUS can vary at all is a property of the values alone — a file whose every exit
        # reports `0` reports `0` however many branches guard it. Whether a computed value
        # reaches the exit is a property of both.
        self.exits: list[tuple[int, list[ast.expr], list[ast.expr]]] = []
        self._conditions: list[ast.expr] = []
        self._function_stack: list[str] = []

    # -- bindings ----------------------------------------------------------

    def _bind(self, target: ast.expr, value: ast.expr | None) -> None:
        if value is None:
            return
        for name in (n.id for n in ast.walk(target) if isinstance(n, ast.Name)):
            self.assigns.setdefault(name, []).append(value)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._bind(target, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._bind(node.target, node.value)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self._bind(node.target, node.value)
        self.generic_visit(node)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self._bind(node.target, node.value)
        self.generic_visit(node)

    # -- branch conditions -------------------------------------------------
    #
    # An exit inside `if not ok: sys.exit(1)` reports a constant and is nonetheless wired to
    # `ok`. Enclosing tests are therefore part of what determines the exit, and omitting them
    # would call the single most common correct shape in the corpus a CONSTANT_EXIT.

    def _visit_branching(self, node: ast.If | ast.While) -> None:
        self._conditions.append(node.test)
        for stmt in node.body:
            self.visit(stmt)
        self._conditions.pop()
        for stmt in node.orelse:
            self.visit(stmt)

    def visit_If(self, node: ast.If) -> None:
        self._visit_branching(node)

    def visit_While(self, node: ast.While) -> None:
        self._visit_branching(node)

    # -- functions ---------------------------------------------------------

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self._function_stack.append(node.name)
        # Conditions do not cross a function boundary: a `def` nested under an `if` is not
        # governed by that test at call time.
        outer, self._conditions = self._conditions, []
        for stmt in node.body:
            self.visit(stmt)
        self._conditions = outer
        self._function_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_Return(self, node: ast.Return) -> None:
        if self._function_stack and self._function_stack[-1] in _ENTRYPOINT_FUNCTIONS:
            reported = [node.value] if node.value is not None else []
            self.exits.append((node.lineno, reported, list(self._conditions)))
        self.generic_visit(node)

    # -- exit sites --------------------------------------------------------

    def visit_Assert(self, node: ast.Assert) -> None:
        # An assertion IS an exit path: a false test ends the process non-zero. Its test is what
        # it reports, so an instrument built only from asserts is armed by construction.
        self.exits.append((node.lineno, [node.test], list(self._conditions)))
        self.generic_visit(node)

    def visit_Raise(self, node: ast.Raise) -> None:
        reported = [node.exc] if node.exc is not None else []
        self.exits.append((node.lineno, reported, list(self._conditions)))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        target = node.func
        name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
        if name in {"exit", "_exit"} and not self._is_entrypoint_trampoline(node):
            self.exits.append((node.lineno, list(node.args), list(self._conditions)))
        self.generic_visit(node)

    # The trampoline
    # exclusion recognized only the single literal shape `sys.exit(main(...))`. Two ordinary
    # idioms fell through it and, because CONSTANT_EXIT/SEALED_EXIT are each one verdict over the
    # union of every exit site, poisoned the WHOLE file to ARMED: the call split across a variable
    # (`code = main(...); sys.exit(code)`) and the call wrapped in another call
    # (`sys.exit(asyncio.run(main(...)))`). Widened to a call-chain check (`_is_entrypoint_call`,
    # for the wrapped shape, arbitrarily deep) plus a flat-assigns lookback (for the split shape).
    # The union-over-all-sites computation itself is the amplifier and the next unrecognized
    # idiom will hit it again the same way — escalated as an ASK rather than restructured inline;
    # see the integration report for `2026-09-08-hoexec-close/premise-check`.
    def _is_entrypoint_trampoline(self, node: ast.Call) -> bool:
        """`sys.exit(main(sys.argv))`, and the two idioms that forward the same value without
        writing that exact line, are plumbing, not a verdict site.

        The house shape forwards an entrypoint's return value to the process status, and the
        entrypoint's own returns are already collected. Counting the trampoline as an exit would
        put a Call and `sys.argv` into EVERY file's determinant set, which alone would make
        `CONSTANT_EXIT` and `SEALED_EXIT` unreachable for every script written the standard way —
        an instrument that could only ever answer `ARMED`. The same is true of a trampoline split
        across a variable or wrapped in another call: neither idiom introduces a value from
        outside `main`, so excluding neither would be the same false-armed failure one line
        further out.
        """
        if len(node.args) != 1 or node.keywords:
            return False
        arg = node.args[0]
        if _is_entrypoint_call(arg):
            return True
        if isinstance(arg, ast.Name):
            # Split form: `code = main(...); sys.exit(code)`. `self.assigns` is FLAT (no scope
            # modelling — see `_Scan`'s class docstring), so a name reused elsewhere in the file
            # for something unrelated is a real possibility; requiring EVERY binding of the name
            # to be an entrypoint call keeps the same over-approximation direction as the rest of
            # this reader — a name that MIGHT be something else is not treated as plumbing.
            bound = self.assigns.get(arg.id, ())
            return bool(bound) and all(_is_entrypoint_call(value) for value in bound)
        return False


def _influencers(
    exits: list[tuple[int, list[ast.expr], list[ast.expr]]],
    assigns: dict[str, list[ast.expr]],
) -> set[str]:
    """Every name that can reach an exit, followed backwards through assignment to a fixpoint."""
    seen: set[str] = set()
    frontier: set[str] = set()
    for _, reported, conditions in exits:
        for expr in reported + conditions:
            frontier |= _names_in(expr)
    while frontier:
        name = frontier.pop()
        if name in seen:
            continue
        seen.add(name)
        for value in assigns.get(name, ()):
            frontier |= _names_in(value) - seen
    return seen


def verdict_reaches_exit(source: str, filename: str = "<instrument>") -> dict:
    """Answer, for one file of Python, whether a computed value can change what it reports.

    Returns `{filename, verdict, findings}` where `findings` is a list of
    `{code, line, detail}`. `verdict` is the most severe code present, or `ARMED`.

    The stated boundary, because a check that overstates what it proves is what makes a reader
    stop checking: this follows names through assignment inside ONE file. A verdict laundered
    through a helper in another module, through a file the instrument writes and reads back, or
    through `exec`/`getattr` indirection is invisible here — `inst-07`'s self-fixture injection is
    caught only when the injected value is written as a literal in this file. Those residuals are
    open by construction, not by oversight, and a reader who needs them closed needs a different
    instrument, not a wider whitelist here.
    """
    try:
        tree = ast.parse(source, filename=filename)
    except (SyntaxError, ValueError) as exc:
        return {
            "filename": filename,
            "verdict": "UNCHECKABLE",
            "findings": [
                {
                    "code": "UNCHECKABLE",
                    "line": getattr(exc, "lineno", 0) or 0,
                    "detail": f"not readable as Python ({exc.__class__.__name__}); "
                    "unread is not armed",
                }
            ],
        }

    scan = _Scan()
    scan.visit(tree)
    findings: list[dict] = []
    reaching = _influencers(scan.exits, scan.assigns)

    if not scan.exits:
        findings.append(
            {
                "code": "NO_EXIT_PATH",
                "line": 0,
                "detail": "no exit, raise, assert or entrypoint return — nothing here reports a "
                "status, so nothing here can report red",
            }
        )
    else:
        reported = [expr for _, values, _ in scan.exits for expr in values]
        # Every expression that can reach the exit: the sites' own, plus the right-hand side of
        # every name they follow back to. Reading only the sites' own expressions would call
        # `ok = "TOKEN" in open(path).read()` / `if not ok: return 1` a SEALED exit, because the
        # read that feeds it is one assignment away.
        determinants = (
            reported
            + [expr for _, _, tests in scan.exits for expr in tests]
            + [expr for name in reaching for expr in scan.assigns.get(name, ())]
        )
        # A site that reports nothing at all (`raise`, a bare `return`) can report any status,
        # so it is never evidence the status is fixed.
        every_site_literal = all(
            values and all(_literal(expr) for expr in values) for _, values, _ in scan.exits
        )
        distinct = {ast.dump(expr) for expr in reported}
        if every_site_literal and len(distinct) <= 1:
            findings.append(
                {
                    "code": "CONSTANT_EXIT",
                    "line": scan.exits[0][0],
                    "detail": "every exit reports the same literal status; no computed value can "
                    "change what this file reports",
                }
            )
        elif not any(_reads_the_world(expr) for expr in determinants):
            findings.append(
                {
                    "code": "SEALED_EXIT",
                    "line": scan.exits[0][0],
                    "detail": "the exit is determined only by expressions this file writes in "
                    "full — no call, no argv, no environ, no stdin reaches it",
                }
            )

    codes = {f["code"] for f in findings}
    verdict = next((v for v in VERDICTS if v in codes), "ARMED")
    return {"filename": filename, "verdict": verdict, "findings": findings}


def _render(report: dict) -> str:
    lines = [f"{report['verdict']}  {report['filename']}"]
    for finding in report["findings"]:
        where = f":{finding['line']}" if finding["line"] else ""
        lines.append(f"  {finding['code']}{where} — {finding['detail']}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="instrument-can-report-red",
        description="Report whether a computed verdict reaches each named instrument's exit path.",
    )
    parser.add_argument("paths", nargs="+", help="instrument files to read")
    parser.add_argument("--json", action="store_true", help="emit one JSON object per file")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="return 1 when any file is other than ARMED (gate mode; the default reports)",
    )
    parsed = parser.parse_args(argv[1:])

    reports = []
    unreadable = 0
    for raw in parsed.paths:
        path = Path(raw)
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            unreadable += 1
            reports.append(
                {
                    "filename": str(path),
                    "verdict": "UNCHECKABLE",
                    "findings": [
                        {"code": "UNCHECKABLE", "line": 0, "detail": f"{exc.__class__.__name__}"}
                    ],
                }
            )
            continue
        reports.append(verdict_reaches_exit(source, str(path)))

    if parsed.json:
        print(json.dumps(reports, indent=2))
    else:
        print("\n".join(_render(r) for r in reports))

    if unreadable == len(reports):
        print("no instrument could be read", file=sys.stderr)
        return 2
    if parsed.strict and any(r["verdict"] != "ARMED" for r in reports):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
