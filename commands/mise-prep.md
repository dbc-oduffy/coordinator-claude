---
name: mise-prep
description: "Certify approved plans; route residue to plan-author."
allowed-tools: ["Read", "Bash", "Grep", "Glob", "Agent"]
argument-hint: "[plan ...] [--roadmap-id <id>] [--dry-run]"
---

# Mise-Prep — Certify Approved Plans

The stage between `plan-blitz` and `/mise-en-place`: gate every approved plan against the
authoring bar and stamp the ones that pass. It stops at certification — it fires nothing.

## 1. Run

`python3 "<plugin root>/bin/mise-prep-run.py" --repo-root <this repo, absolute> --upgrade [plan ...] [--roadmap-id <id>] [--dry-run]`

**Resolve the plugin root to an absolute path yourself** — the directory holding this command's
sibling `bin/`. `${CLAUDE_PLUGIN_ROOT}` is a POSIX expansion, unset in a PowerShell tool shell, so
pasting it runs nothing and explains little.

Pass on only the plan paths and flags the invocation names; free text is context, never a plan
path. **No plan arguments means every plan the last landing left fireable — BOTH exits**, not only
`status: approved`: the S lane parks its spec execution-ready and leaves the plan `draft` by
design, and those certify too. A count that moves with no approval is usually one of them.
`--upgrade` writes only the declarations derivable
from a plan's own text; `plan.stamp_prepped`, inside the run, writes the stamp. Read the report:

- **exit 0** — every plan certified. Report and stop.
- **exit 2, REFUSED** — no verdict computed. Relay it verbatim and stop; an engine-root refusal is
  an engine-root defect, never NOT-PREPPED.
- **exit 1** — route each short plan by its row:
  - `NOT-PREPPED` with a `bar:` line → step 2.
  - `refused`, or a MALFORMED stamp → not authoring residue. Relay it; a MALFORMED stamp was
    hand-written, and its repair is the frontmatter, never a stamp over it.

## 2. Author the residue

NOT-PREPPED residue is authorship: the bar asks what only a plan's author knows. Dispatch one
`coordinator:plan-author` per plan, in parallel — each owns one file. Brief each with:

- the plan path and its `bar:` line verbatim;
- the bar's own refusal, naming each missing declaration and its declared-empty form:
  `python3 "<plugin root>/bin/mise-prep-gate.py" --repo-root <repo> <plan>`;
- the charter: amend this plan in place, declaring only the classes named. No scaffold, no
  `status` change, no `mise_prepped_*` key, no body edit beyond a named class. Declared-empty only
  where true. What only the PM can answer goes in the summary, class left undeclared.

Not `coordinator:enricher` — it gathers facts and never decides, and a `prime_exit_criterion` is
a decision. Tripwire: `NOT-PREPPED-RESIDUE-IS-AUTHORED-BY-PLAN-AUTHOR`.

## 3. Re-run, then stop

Run step 1 once more. A plan still NOT-PREPPED after one authoring pass is reported with its
`bar:` line and its author's summary — not re-dispatched. Report certified/short counts and stop.

Never write `mise_prepped_*` by hand, and never execute: `/mise-en-place` fires certified plans,
re-checking each stamp at Phase 0.
