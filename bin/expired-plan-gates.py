#!/usr/bin/env python3
"""expired-plan-gates — list gated chunk rows on plans that are still live.

WHY THIS EXISTS. `/workday-start` Step 1.2 sweeps `awaiting_gate` off *handoff* frontmatter and
flags a gate stuck past six days. A gate declared on a **plan chunk row** is read by nothing at
all, so a chunk whose gate names a ceremony as its own expiry never surfaces there — the expiry
fires only if a human happens to remember it. That is the failure mode the discharge test
(`docs/wiki/invisible-doctrine.md`) exists to name: if the operator remembering is the mechanism,
the work is not finished.

WHY IT READS TWO SPELLINGS. `awaiting_gate` is the older, UNDECLARED plan-row spelling — absent
from `plan-tasks.schema.json` (v1.10.0), which leaves `additionalProperties` unset, so it
validates clean and passing is indistinguishable from being read. The declared vocabulary is
`external_gate[]`, which the schema models structurally (`owner_repo`/`condition`/`blocks`/
`closure_key`) and which `emit-dispatch-workflow.py` Check A reads to withhold a row from a wave.
Reading only `awaiting_gate` made this sweep blind to every row using the vocabulary the rest of
the fleet actually schedules against — 11 plans here against 1, at the time this leg was widened.
A sweep whose whole job is "surface the gate nobody is watching" cannot itself watch the retired
half of the vocabulary. `awaiting_gate` stays readable rather than being dropped: under-reporting
a live gate is the one failure this mechanism exists to prevent, so a straggler row keeps
surfacing until it is migrated.

Negative-spec: a `cleared: true` `external_gate` entry is NOT reported — that is the field the
emitter treats as discharge, and a sweep that kept naming discharged gates would train the reader
to skip its own output. `closure_evidence` never clears a gate here either, matching
`emit-dispatch-workflow._uncleared_execution_gate`; the two readers must agree or a gate's
visibility depends on which one saw it first. `blocks: ac-closure` IS reported: it does not block
execution, but it is still an open gate sitting on a live plan, which is this sweep's subject.

WHY IT FILTERS RATHER THAN GREPS. A bare `grep -l awaiting_gate docs/plans/*.md` matches ~39
plans in this repo, nearly all terminal. A check that reports 39 rows to find one live gate is a
check nobody runs twice, so terminal plans are dropped here rather than left for the reader to
skip by eye. Unknown/absent `status:` is treated as LIVE — under-reporting a live gate is the
failure this whole mechanism exists to prevent, while over-reporting one costs a glance.

Zero subprocess, stdlib only: a ceremony leg runs on a machine already carrying many concurrent
sessions, and this one walks a directory of small files.

Exit status is 0 whether or not gates are found — an expired gate is a finding for the operator to
act on, not an error condition, and a non-zero exit here would read as a broken ceremony step.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_TERMINAL = {"implemented", "superseded", "abandoned", "closed", "shipped", "done"}

_STATUS = re.compile(r"^status:\s*['\"]?([A-Za-z_-]+)", re.MULTILINE)
_ROW_ID = re.compile(r"^- id:\s*(\S+)", re.MULTILINE)


def _plans_root(repo_root: Path) -> Path:
    return repo_root / "docs" / "plans"


def _status_of(text: str) -> str | None:
    head = text.split("---", 2)
    front = head[1] if text.startswith("---") and len(head) > 2 else text[:2000]
    found = _STATUS.search(front)
    return found.group(1).strip().lower() if found else None


def _awaiting_gate(block: str) -> list[str]:
    """The row's `awaiting_gate` one-liner, as a 0-or-1 list."""
    marker = block.find("awaiting_gate:")
    if marker == -1:
        return []
    gate = block[marker + len("awaiting_gate:") :].strip()
    gate = gate.split("\n  body:")[0].strip().strip("\"'")
    return [" ".join(gate.split())] if gate else []


def _external_gates(block: str) -> list[str]:
    """Each UNCLEARED `external_gate` entry's `condition`, in declaration order.

    Indent-scanned rather than YAML-parsed to hold this module's stdlib-only,
    zero-subprocess contract. The scan ends at the first line that is neither
    blank, nor indented past the `external_gate:` key, nor itself a sequence
    entry — that last clause is load-bearing and was missing on the first cut:
    YAML permits a block sequence at the SAME indent as its key, which is how
    every gate in this corpus is authored (`external_gate:` and its `- ` entries
    both at row-field indent). Ending the scan on `indent <= key_indent` alone
    therefore broke on the first entry of every well-formed gate and reported
    nothing, which in a sweep whose whole purpose is catching what nothing else
    watches is the one failure mode that does not announce itself. Entry keys
    and `closure_key`'s nested mapping sit deeper still and ride inside their
    entry.

    A `condition:` is routinely authored as a folded/literal block scalar
    (`condition: >-`, the prose on the following lines) because the conditions
    are sentences, not tokens. Taking only the inline remainder yielded the
    chomping indicator itself — a gate reported to the operator as the text
    `>-`, truthy enough to pass the non-empty check and useless to read. So a
    block-scalar opener collects its continuation lines instead.
    """
    lines = block.splitlines()
    gates: list[str] = []
    for index, line in enumerate(lines):
        if line.strip() != "external_gate:":
            continue
        key_indent = len(line) - len(line.lstrip())
        condition: str | None = None
        cleared = False
        folding_at: int | None = None
        for entry in lines[index + 1 :]:
            stripped = entry.strip()
            indent = len(entry) - len(entry.lstrip())
            if stripped and indent <= key_indent and not stripped.startswith("- "):
                break
            if folding_at is not None:
                if not stripped or indent >= folding_at:
                    condition = f"{condition} {stripped}".strip() if stripped else condition
                    continue
                folding_at = None
            if stripped.startswith("- "):
                if condition and not cleared:
                    gates.append(condition)
                condition, cleared = None, False
                indent += 2
                stripped = stripped[2:].strip()
            if stripped.startswith("condition:"):
                value = stripped[len("condition:") :].strip()
                if value.rstrip("-+0123456789") in (">", "|"):
                    condition, folding_at = "", indent + 1
                else:
                    condition = " ".join(value.strip("\"'").split())
            elif stripped.startswith("cleared:"):
                cleared = stripped[len("cleared:") :].strip().strip("\"'").lower() == "true"
        if condition and not cleared:
            gates.append(condition)
    return gates


def _gated_rows(text: str) -> list[tuple[str, str]]:
    """(chunk_id, gate_text) for every open gate on every row, either spelling."""
    rows: list[tuple[str, str]] = []
    starts = [(m.start(), m.group(1)) for m in _ROW_ID.finditer(text)]
    for index, (offset, chunk_id) in enumerate(starts):
        end = starts[index + 1][0] if index + 1 < len(starts) else len(text)
        block = text[offset:end]
        for gate in _awaiting_gate(block) + _external_gates(block):
            rows.append((chunk_id, gate))
    return rows


def main(argv: list[str]) -> int:
    repo_root = Path(argv[1]).resolve() if len(argv) > 1 else Path.cwd()
    plans = _plans_root(repo_root)
    if not plans.is_dir():
        print(f"no plans directory at {plans}", file=sys.stderr)
        return 0

    findings = 0
    for plan in sorted(plans.glob("*.md")):
        try:
            text = plan.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            # UnicodeDecodeError is a ValueError, NOT an OSError — catching only the latter lets
            # one non-UTF-8 plan crash the whole sweep with a traceback, which is exactly the
            # non-zero exit this module's contract promises never to produce.
            # Review: coordinator:code-reviewer — under-reporting is the failure that matters;
            # a genuinely live gate on an undecodable plan must leave a trace, not vanish silently.
            print(f"  skipped: {plan} ({exc.__class__.__name__})", file=sys.stderr)
            continue
        status = _status_of(text)
        if status in _TERMINAL:
            continue
        rows = _gated_rows(text)
        if not rows:
            continue
        findings += len(rows)
        print(f"\n{plan.name}  (status: {status or 'unset — treated as live'})")
        for chunk_id, gate in rows:
            print(f"  {chunk_id}: {gate[:220]}{'…' if len(gate) > 220 else ''}")

    if findings:
        print(
            f"\n{findings} open gate(s) on live plans. An expiry naming an action is a directive: "
            "fire it or record why not."
        )
    else:
        print("No open gates on live plans.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
