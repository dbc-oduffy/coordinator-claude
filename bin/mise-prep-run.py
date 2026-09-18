#!/usr/bin/env python3
"""mise-prep-run — gate and stamp a set of plans, and name each one's state.

WHY THIS EXISTS. mise-prep's two halves both shipped and neither drives the ceremony.
`plan.prep_gate` reports the authoring bar for ONE plan; `plan.stamp_prepped` writes the
attest for ONE plan and refuses unless the gate passes over the bytes it is about to
stamp. Between them, nothing — so certifying a landed wave means an EM reading the entry
query, picking plan paths out of it, and typing two op calls per plan. That is the same
retype `mise-prep-entry.py` removed at the plan-blitz seam, still standing one step later.

This is the driver: one call over a set, gate then stamp each, and one report that names
every plan's state with the repair that state routes to.

THE FOUR STATES ROUTE FOUR WAYS, which is why "not certified" is the wrong noun for three
of them and this module never prints it:

  CERTIFIED    the recomputed body sha matches the stamp. Nothing to do.
  STALE        stamped, but the body moved since — re-GATE, then re-stamp. A wave's
               review-integrator rewrites plan bodies, so STALE is the ORDINARY state
               after a landing, not an anomaly.
  UNSTAMPED    never certified. Gate and stamp.
  MALFORMED    a hand-written stamp. Repair the frontmatter; do not stamp over it.

WHAT IT DOES NOT DO. It does not decide what to fire, does not run a plan's `census[]`
commands (that is the fire-time leg, and it belongs to the runner), and does not author
anything into a plan. A plan that fails the bar is REPORTED with its failing classes and
the upgrade command that writes the declarations derivable from the plan's own text —
`mise-prep-upgrade` never invents one, and neither does this. `--upgrade` runs it for
you and re-gates; without the flag nothing under `docs/plans/` is written except an
attest the gate has just passed.

Usage:

    python3 mise-prep-run.py --repo-root <abs> [--upgrade] [--dry-run] [plan ...]

With no plan arguments the set is every APPROVED plan the engine's plan gate reports —
mise-prep's own entry set, taken from the same seam `mise-prep-entry.py` reads, never
re-derived from plan frontmatter.

Exit 0 when every plan in the set ends CERTIFIED, 1 when at least one does not (the
report names which and why), 2 on a refusal that stopped the run.

IN-PROCESS OP DISPATCH (the requirement this arrival exists to discharge). The DoE
version of this driver spawned `sys.executable coordinator-invoke.py <op> <params>` per
op call — one interpreter start per gate, per stamp. This module lives inside the
engine, so `_invoke` dispatches `plan.prep_gate`/`plan.stamp_prepped` in-process through
`coordinator_core.invoke.dispatch.dispatch_message`, the same JSON-RPC path the
subprocess route used, minus the process hop. Only `mise-prep-upgrade` — a separate CLI
this row does not move — still runs as a subprocess: it has its own resolution ladder,
unchanged, and is not this row's `writes:`.

Arrived from DoE-claude coordinator/bin/mise-prep-run.py (docs/plans/2026-09-18-doe-holds-no-
scripts.md, chunk W2-C9). `mise-prep-entry.py` lands beside this file, in coordinator/bin, not
under skills/plan-blitz, so `_ENTRY` resolves as a sibling.

Spec backlink: docs/plans/2026-09-18-doe-holds-no-scripts.md, chunk W2-C9.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_NOT_ALL_CERTIFIED = 1
EXIT_REFUSED = 2

_HERE = Path(__file__).resolve().parent
#: mise-prep's entry query, now a `coordinator/bin` sibling of this driver. Imported rather than
#: re-implemented: re-deriving the approved set from plan frontmatter would be a second answer to
#: a question the engine's gate settles.
_ENTRY = _HERE / "mise-prep-entry.py"
#: "engine" class per § Path resolution — this module lives inside the engine checkout, so its
#: own tree IS the engine root.
_ENGINE_ROOT = _HERE.parents[1]


def _load_entry():
    spec = importlib.util.spec_from_file_location("mise_prep_entry", _ENTRY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _default_engine_root() -> Path | None:
    """This module's own tree — see § Path resolution, "engine" class.

    Returns `None` only in the pathological case where this file's own on-disk location does not
    resolve, so that `_invoke`/`_upgrade` degrade to their own "no launcher" refusals rather than
    raising here."""
    return _ENGINE_ROOT if _ENGINE_ROOT.is_dir() else None


def _invoke(repo_root: Path, engine_root: Path | None, op: str, params: dict) -> dict:
    """Dispatch one op IN-PROCESS via `coordinator_core.invoke.dispatch.dispatch_message` — the
    same JSON-RPC envelope the subprocess route parsed, minus the process hop. `engine_root` is
    accepted for call-site parity with the pre-port signature (and is still consulted below to
    make coordinator_core importable on a box that invoked this file from outside the engine
    checkout); the op itself is dispatched against `repo_root`, via `_origin_worktree`, exactly as
    `coordinator_core.ops.check_auto_reconcile.get_response` dispatches `handoff.reconcile_open`.
    """
    root = engine_root or _default_engine_root()
    if root is not None and str(root) not in sys.path:
        sys.path.insert(0, str(root))
    import asyncio

    try:
        from coordinator_core.invoke.dispatch import dispatch_message
    except Exception as exc:
        raise ValueError(f"{op} failed: coordinator_core.invoke.dispatch unimportable ({exc})")

    msg = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": op,
        "params": params,
        "_origin_worktree": str(repo_root),
    }
    loop = asyncio.new_event_loop()
    try:
        reply = loop.run_until_complete(
            dispatch_message(msg, caller="coordinator_core.roadmap.mise_prep_run")
        )
    except Exception as exc:
        raise ValueError(f"{op} failed: {exc}")
    finally:
        loop.close()

    if not isinstance(reply, dict):
        raise ValueError(f"{op} failed: dispatch returned no reply envelope")
    if "error" in reply:
        err = reply["error"]
        message = str((err or {}).get("message") or err) if isinstance(err, dict) else str(err)
        raise ValueError(f"{op} refused: {message}")
    if "result" not in reply:
        raise ValueError(f"{op} returned a reply carrying neither `result` nor `error`")
    return reply["result"]


def _failing_classes(gate: dict) -> list[str]:
    return [
        f"{name}/{body.get('kind') or body.get('status')}"
        for name, body in (gate.get("classes") or {}).items()
        if body.get("status") != "PASS"
    ]


# WHAT THE CLASS ACTUALLY SAID. The repair line tells the reader to correct "the named field", and
# until this existed nothing named it: `_failing_classes` kept the class name and threw the body
# away, `--json` carried only the class string, and the one tool that would have printed detail is
# the gate — which, on the very plans that fail here, says PREPPED. So the operator was pointed at
# a class body reachable from nowhere, and example-store-repo-fb was reduced to diffing a failing plan
# against a passing one to guess at the field. A repair instruction that names an artifact the tool
# does not emit is `A-DIAGNOSTIC-THAT-NAMES-A-CAUSE-IT-DID-NOT-OBSERVE` wearing its other face.
#
# The body's shape belongs to the engine and will grow keys this does not know, so this renders
# whatever detail it carries rather than a fixed field list: preferred keys first, then any
# remaining non-bookkeeping key, so a new one surfaces instead of being silently dropped.
_DETAIL_KEYS = ("message", "reason", "detail", "details", "field", "fields", "errors", "offenders")
_CLASS_BOOKKEEPING = {"status", "kind"}


def _failing_details(gate: dict) -> list[str]:
    out = []
    for name, body in (gate.get("classes") or {}).items():
        if not isinstance(body, dict) or body.get("status") == "PASS":
            continue
        seen, parts = set(), []
        for key in _DETAIL_KEYS:
            if body.get(key) not in (None, "", [], {}):
                seen.add(key)
                parts.append(f"{key}={body[key]!r}")
        for key, value in body.items():
            if key in seen or key in _CLASS_BOOKKEEPING:
                continue
            if value not in (None, "", [], {}):
                parts.append(f"{key}={value!r}")
        if parts:
            out.append(f"{name}: {'; '.join(parts)}")
    return out


# `mise-prep-upgrade` writes DECLARATIONS DERIVABLE FROM A PLAN'S OWN TEXT. A schema class rejects
# a value the plan already states, so `--upgrade` has nothing to derive and writes nothing — the
# blanket "repair: mise-prep-upgrade <plan>" is then a no-op that sends the reader in a circle,
# reported by project-rag-4a after running it across a whole set for zero writes.
#
# This line names only what the runner OBSERVED: which class refused, and that the upgrade path
# cannot reach it. It deliberately names no cause. The first draft illustrated it with an unquoted
# YAML date, borrowed from the report that prompted the fix — and that cause turned out not to
# exist (the real validation path coerces; the census had bypassed it). A repair line that names a
# cause the runner did not measure is `A-DIAGNOSTIC-THAT-NAMES-A-CAUSE-IT-DID-NOT-OBSERVE`, and it
# would have sent every reader of a schema refusal to check their date quoting for as long as it
# stood.
_NOT_UPGRADEABLE = ("schema",)


def _sizing_object_citation(plan: str) -> str:
    """This plan's own top-level `sizing_object:`, when it resolves on disk.

    project-rag-ue-addon measured 21 SCHEMA refusals on one corpus, every one a
    `prime_exit_criterion.derived_from` carrying narrative where the schema wants an openable
    link — and in 17 of 17 repaired by hand, the correct pointer was this same field, sitting in
    the same frontmatter. Naming it costs a line-scan; not naming it cost them four dispatched
    agents. Returns "" on any read failure: a repair line may name only what was read.
    """
    try:
        with open(plan, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return ""
    if not lines or lines[0].strip() != "---":
        return ""
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if not line.startswith("sizing_object:"):
            continue
        value = line.split(":", 1)[1].strip().strip("'\"")
        return value if value and os.path.exists(value) else ""
    return ""


def _repair_line(failing: list[str], plan: str) -> str:
    """The repair for THIS row's failing classes, never one constant string."""
    blocked = sorted({
        cls.split("/", 1)[0] for cls in failing
        if cls.split("/", 1)[0].lower().startswith(_NOT_UPGRADEABLE)
    })
    if blocked:
        candidate = _sizing_object_citation(plan)
        derived = (
            f" This plan's own `sizing_object: {candidate}` resolves on disk; where the refused "
            f"field is `prime_exit_criterion.derived_from`, that is usually the value it wants. "
            f"Relocate the prose it currently holds into the plan body rather than dropping it, "
            f"and re-run — a body edit invalidates `mise_prepped_sha`."
            if candidate
            else ""
        )
        return (
            f"repair: NOT `--upgrade` — it writes declarations derivable from the plan's own "
            f"text, and {', '.join(blocked)} refuses a value the plan already states, so the "
            f"upgrade path does not write it. Read that class's own body for the named field and "
            f"correct it BY HAND in {plan} — unless the field is engine-written (`mise_prepped*`, "
            f"`execution_authorized_*`), which has a producer and must be repaired there instead."
            f"{derived}"
        )
    return f"repair: mise-prep-upgrade {plan}  (or --upgrade), then re-run"


def _resolve_upgrade_cli(settings_home: str, engine_root: Path | None) -> list[str] | None:
    """`mise-prep-upgrade` as an argv prefix, down the sanctioned rungs, or None.

    Rung 2 is the settings-home launcher, then PATH; rung 3 is the engine's own
    `coordinator/bin/` copy under the engine root this run already dispatches ops
    through (`--engine-root`, else `$COORDINATOR_ENGINE_ROOT`). A resolver that stops
    at rung 2 refuses on boxes where the tool exists. The engine copy carries no
    shebang, so the interpreter is part of the invocation.
    """
    launcher = Path(settings_home) / "bin" / "mise-prep-upgrade"
    if launcher.is_file():
        return [str(launcher)]
    found = shutil.which("mise-prep-upgrade")
    if found:
        return [found]
    if engine_root is not None:
        forwarder = engine_root / "coordinator" / "bin" / "mise-prep-upgrade.py"
        if forwarder.is_file():
            return [sys.executable, str(forwarder)]
    return None


#: `mise-prep-upgrade`'s own per-plan lines — `  {verb}: {sorted(derivable)}` where verb
#: is "derived" (a live run) or "would derive" (`--check`), and `    AUTHOR: {item}` for
#: each residue entry. Read here rather than re-derived: this driver never guesses at what
#: was written, it reads the tool's own report of it.
_UPGRADE_DERIVED_RE = re.compile(r"^(?:derived|would derive):\s*(.+)$")
_UPGRADE_AUTHOR_RE = re.compile(r"^AUTHOR:\s*(.+)$")
#: The tool's one summary line: `mise-prep-upgrade: N plan(s); M changed|would change; ...`.
#: `M` is the fact this driver actually needs — whether anything was (or would be)
#: written — because the tool's exit code conflates "wrote what it could" with "residue
#: remains" into the same EXIT_RESIDUE, its normal outcome even after a write.
_UPGRADE_SUMMARY_RE = re.compile(
    r"plan\(s\);\s*(\d+)\s+(?:changed|would change)\b"
)


def _upgrade(
    repo_root: Path, engine_root: Path | None, plan: str, dry_run: bool = False
) -> tuple[str, str]:
    """Run `mise-prep-upgrade` over one plan. Returns (state, note).

    `state` is "wrote", "declined", or "unavailable" — three outcomes, not two, and
    classified from STDOUT, never from the exit code. `mise-prep-upgrade` exits 1
    (EXIT_RESIDUE) whenever authoring residue remains, which is its NORMAL outcome even
    on a run that just wrote every field it could derive — mapping that exit straight to
    "declined" reports a write as a no-op. `wrote` fires whenever the summary line's
    changed/would-change count is nonzero; `note` then carries the derived field(s) plus
    any residue (`AUTHOR: ...`) lines, e.g. `wrote prime_exit_criterion.derived_from;
    AUTHOR: prime_exit_criterion.statement: ...`. `declined` is reserved for a run that
    wrote nothing — pure residue, or truly nothing to do. Only a launcher that is not on
    disk at any resolution rung is `unavailable`.

    `dry_run` passes `--check` through to the tool — a dry run must not let `--upgrade`
    write to disk, and `mise-prep-upgrade` writes unless told `--check`.

    Delegated, never reimplemented: what is derivable from a plan's own text is that
    tool's judgment, and a second deriver here would author declarations it never
    agreed to.
    """
    settings_home = os.environ.get("COORDINATOR_SETTINGS_HOME") or str(
        Path(os.environ.get("CLAUDE_HOME") or Path.home()) / ".coordinator-claude-settings"
    )
    # The full resolution ladder, not its top rung alone. `mise-prep-upgrade` is an
    # ENGINE CLI, so a box that never ran the installer still has it on disk under the
    # engine checkout — and reporting that as "unavailable" sends an author hunting for
    # a missing tool that is right there, the misdiagnosis this docstring warns about
    # one rung up. `unavailable` stays honest when it is genuinely absent from every rung.
    cmd = _resolve_upgrade_cli(settings_home, engine_root)
    if cmd is None:
        engine_bin = (
            engine_root / "coordinator" / "bin" / "mise-prep-upgrade.py"
            if engine_root is not None
            else "<no --engine-root>"
        )
        return "unavailable", (
            f"no mise-prep-upgrade launcher at {Path(settings_home) / 'bin'}, none on "
            f"PATH, and no copy under {engine_bin}"
        )
    # Same engine env `_invoke` injects. Without it the upgrade CLI resolves CLAUDE_KLABAUTER_ROOT
    # on its own and fails on exactly the install-less box this fallback exists for.
    env = dict(os.environ)
    if engine_root is not None:
        env.setdefault("COORDINATOR_ENGINE_ROOT", str(engine_root))
    argv = cmd + [plan] + (["--check"] if dry_run else [])
    proc = subprocess.run(
        argv, capture_output=True, text=True, env=env, cwd=str(repo_root), timeout=300,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    lines = (proc.stdout or proc.stderr).strip().splitlines()

    derived_fields = ""
    author_notes: list[str] = []
    changed = 0
    for raw in lines:
        stripped = raw.strip()
        m = _UPGRADE_DERIVED_RE.match(stripped)
        if m:
            derived_fields = m.group(1).strip()
            continue
        m = _UPGRADE_AUTHOR_RE.match(stripped)
        if m:
            author_notes.append(m.group(1).strip())
            continue
        m = _UPGRADE_SUMMARY_RE.search(stripped)
        if m:
            changed = int(m.group(1))

    if changed > 0:
        note = f"wrote {derived_fields}" if derived_fields else "wrote (fields unparsed)"
        if author_notes:
            note += "; AUTHOR: " + "; ".join(author_notes)
        return "wrote", note

    last_line = lines[-1].strip() if lines else ""
    if author_notes:
        note = "AUTHOR: " + "; AUTHOR: ".join(author_notes)
    else:
        note = last_line or "nothing to derive"
    return "declined", note


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="mise-prep-run",
        description="Gate and stamp a set of plans; name each one's certification state.",
    )
    ap.add_argument("plans", nargs="*", help="plan paths; default: every approved plan")
    ap.add_argument("--repo-root", required=True, help="ABSOLUTE repo root")
    ap.add_argument("--engine-root", help="engine checkout (default: $COORDINATOR_ENGINE_ROOT)")
    ap.add_argument("--roadmap-id", help="narrow the default set to one roadmap")
    ap.add_argument(
        "--upgrade",
        action="store_true",
        help="run mise-prep-upgrade over a plan that fails the bar, then re-gate. Writes "
        "only the declarations derivable from the plan's own text; it invents none, so a "
        "plan needing real authoring still comes back NOT-PREPPED with its classes named.",
    )
    ap.add_argument("--dry-run", action="store_true", help="gate and report; stamp nothing")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    _er = args.engine_root or os.environ.get("COORDINATOR_ENGINE_ROOT") or ""
    engine_root = Path(_er).resolve() if _er.strip() else _default_engine_root()

    def refuse(msg: str) -> int:
        print(f"mise-prep-run: REFUSED — {msg}", file=sys.stderr)
        return EXIT_REFUSED

    plans = list(args.plans)
    if not plans:
        try:
            entry = _load_entry()
            rows = entry.approved_plans(repo_root, args.roadmap_id, False)
        except Exception as exc:  # noqa: BLE001 - the entry query owns its own errors
            return refuse(f"could not read the approved-plan set: {exc}")
        plans = [r["plan"] for r in rows]
        if not plans:
            print("mise-prep-run: no approved plans — nothing to certify")
            return EXIT_OK
        # SAY WHAT THE SET IS MADE OF. The selection reads BOTH plan-blitz exits — `status:
        # approved` and the S lane's execution-ready park, whose plan stays `draft` by design — so
        # a count that moves with no approval in sight is ordinary. Reported on project-rag as
        # "39 -> 40 with no line saying a plan had entered", which cost its driver a tree diff to
        # explain a set that was correct all along.
        drafts = [
            p for p in plans
            if "status: approved" not in (repo_root / p).read_text(
                encoding="utf-8", errors="replace")[:4000]
        ] if all((repo_root / p).is_file() for p in plans) else []
        print(
            f"mise-prep-run: certification set — {len(plans)} plan(s)"
            + (f", {len(drafts)} entering from the execution-ready lane (plan still draft by "
               f"design): {', '.join(drafts[:5])}"
               f"{' …' if len(drafts) > 5 else ''}" if drafts else "")
        )

    rows = []
    for plan in plans:
        try:
            gate = _invoke(repo_root, engine_root, "plan.prep_gate", {"plan": plan})
        except ValueError as exc:
            return refuse(f"{plan}: {exc}")

        upgraded = None
        if gate.get("verdict") != "PREPPED" and args.upgrade:
            state, note = _upgrade(repo_root, engine_root, plan, dry_run=args.dry_run)
            # "ran" is kept alongside "wrote" so a test (or a caller) stubbing `_upgrade`
            # with the pre-fix vocabulary still reads as a write — the real function only
            # ever returns "wrote" now.
            wrote = state in ("wrote", "ran")
            upgraded = note if wrote else f"{state}: {note}"
            # Re-gate whenever the upgrade actually changed something, not only on a
            # tidy "ran" — the ordinary outcome is a write alongside residue, which the
            # old exit-code-keyed check reported as "declined" and never re-gated.
            # Never under `--dry-run`: `_upgrade` already ran `--check` and wrote
            # nothing, so a re-gate here would just repeat the same verdict.
            if wrote and not args.dry_run:
                try:
                    gate = _invoke(repo_root, engine_root, "plan.prep_gate", {"plan": plan})
                except ValueError as exc:
                    return refuse(f"{plan}: re-gate after upgrade: {exc}")

        # The gate already carries the attest's own four-state read (`plan.prep_gate`
        # returns `read_stamp`'s answer). Carrying it here is what makes a dry run
        # answer the question a dry run is asked: not "would these pass the bar" but
        # "how many of them does this run actually write". Without it every plan in the
        # set reads `would-stamp`, CERTIFIED ones included, and a set with nothing to do
        # is indistinguishable from a set where all of it is pending.
        row = {
            "plan": plan,
            "verdict": gate.get("verdict"),
            "failing": _failing_classes(gate),
            "detail": _failing_details(gate),
            "withheld_rows": gate.get("withheld_rows") or [],
            "upgraded": upgraded,
            "stamp_state": (gate.get("stamp") or {}).get("state"),
            "outcome": None,
        }

        if gate.get("verdict") == "PREPPED" and not args.dry_run:
            try:
                stamp = _invoke(repo_root, engine_root, "plan.stamp_prepped", {"plan": plan})
            except ValueError as exc:
                return refuse(f"{plan}: {exc}")
            # A refusal is a REPLY here, not an exception — the per-class breakdown is
            # what tells an author where the fix lands, so it is carried, not raised.
            row["outcome"] = stamp.get("outcome")
            row["mise_prepped_findings"] = stamp.get("mise_prepped_findings") or []
            if stamp.get("outcome") == "refused":
                row["verdict"] = stamp.get("verdict") or row["verdict"]
                row["failing"] = _failing_classes(stamp) or row["failing"]
                row["detail"] = _failing_details(stamp) or row["detail"]
        elif gate.get("verdict") == "PREPPED":
            row["outcome"] = (
                "already-certified"
                if row["stamp_state"] == "CERTIFIED"
                else "would-stamp"
            )

        rows.append(row)

    # In a dry run `would-stamp` IS the pass — the gate returned PREPPED and only the
    # write was withheld. Counting it as short would report a clean set as a failing one
    # and send an author to fix plans that need nothing, which is the wrong half of the
    # report to get wrong: a dry run exists to be believed before anything is written.
    passing = {"stamped", "already-certified"} | ({"would-stamp"} if args.dry_run else set())
    certified = [r for r in rows if r["outcome"] in passing]
    short = [r for r in rows if r not in certified]

    if args.json:
        print(
            json.dumps(
                {"plans": rows, "certified": len(certified), "dryRun": args.dry_run}, indent=2
            )
        )
    else:
        verb = "would certify" if args.dry_run else "certified"
        mode = " (dry run — nothing stamped)" if args.dry_run else ""
        pending = sum(1 for r in rows if r["outcome"] == "would-stamp")
        work = f" — {pending} would be written" if args.dry_run else ""
        print(f"mise-prep-run: {len(certified)} of {len(rows)} plan(s) {verb}{mode}{work}")
        for r in rows:
            if r in certified:
                held = r.get("mise_prepped_findings") or []
                tail = f"  [{len(held)} row(s) withheld: {', '.join(held)}]" if held else ""
                print(f"  {r['outcome']:<18} {r['plan']}{tail}")
            else:
                print(f"  {(r['outcome'] or r['verdict'] or 'NOT-PREPPED'):<18} {r['plan']}")
                if r["failing"]:
                    print(f"                     bar: {', '.join(r['failing'])}")
                for line in r.get("detail") or []:
                    print(f"                     said: {line}")
                if r["upgraded"]:
                    print(f"                     upgrade: {r['upgraded']}")
                elif r["verdict"] != "PREPPED":
                    print(f"                     {_repair_line(r['failing'], r['plan'])}")

    if short:
        print(
            f"\nmise-prep-run: {len(short)} plan(s) are not certified. A plan that fails the "
            "bar needs authoring, not a stamp — the classes above name where. Author it via "
            "/mise-prep: one coordinator:plan-author per plan, then re-run.",
            file=sys.stderr,
        )
        return EXIT_NOT_ALL_CERTIFIED
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
