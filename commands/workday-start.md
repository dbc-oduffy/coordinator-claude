---
name: workday-start
description: "Morning orient — triage handoffs, staleness, priorities."
allowed-tools: ["Read", "Write", "Grep", "Glob", "Bash", "Agent", "Workflow"]
argument-hint: "[optional day focus]"
---

# Workday Start — Morning Orientation

**Announce:** "Running workday-start to prepare the day's context."

The ceremony is a deterministic run, not a checklist the EM walks. `workday-start-run launch` runs
every manifest step (branch setup, handoff triage, advisory probes, freshness, weekly group,
markers), resolves the judgment points it can by rule, routes the rest to agents, and binds a digest
onto the workflow template. `workday-start-run finish --run-id <id>` records the agents' decisions,
runs the tail and renders the briefing. The EM runs neither leg's steps by hand: a leg the run lacks
is a memo to the engine, never a line added here.

**Between `launch` and the rendered briefing the EM does not stop.** Only the run's own exit codes
halt it (`coordinator/docs/wiki/coordinator-tripwires/a-ceremony-run-halts-only-on-its-own-exit-code.md`).
Narrating the remaining steps instead of running them is the failure this command exists to prevent.

## Launch

Resolve the launcher per `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md` (Shape W on
PowerShell, the POSIX launcher form otherwise) and run, solo:

    workday-start-run launch

Route on its exit code and print the receipt either way:

- **0 with a `Workflow(` line** — fire that line verbatim, then render the returned `briefing`
  verbatim. Do not cite or re-derive the template path; the line carries it.
- **0 without a `Workflow(` line** — the printed receipt is the briefing; render it.
- **3** — a run is already in flight. Finish it: `workday-start-run finish --run-id <id>` with the
  id the receipt names. If the workflow's agents never ran, fire its `Workflow(` line first.
- **4** — the workflow template is missing. Resolve `${CLAUDE_PLUGIN_ROOT}` before calling it absent
  (`coordinator/docs/wiki/coordinator-tripwires/a-missing-workflow-script-is-an-unresolved-plugin-root.md`),
  then report the receipt and the path it names.
- **5** — a gate failed. Render the receipt; its Failed section names the step, and the failure is
  already filed.
- **Any other non-zero** — report the receipt verbatim and stop.

After the workflow returns, if it did not itself run `finish`, run
`workday-start-run finish --run-id <id>` and render its briefing verbatim.

## What the run decides, not the EM

- **Step 0 (branch setup)** — exit 2 (`STALE-NEEDS-ABC`) is decided by the run's own rules: defer
  once, then stop-and-file. Exit 3 (`RECONCILE-CONFLICT`) → PM picks A/B/C. On **A** the merge
  stays open: `RECONCILE-CONFLICT-OPEN` lists the conflicted paths and the EM dispatches one
  file-only resolver (a Sonnet executor) that reads both sides, edits each listed path and runs
  `git add -- <path>`, never merge, commit or abort. The EM then runs `reconcile-merge-conclude`;
  a refusal names what is left. Keep the window short: while `MERGE_HEAD` stands, every peer
  commit in the tree refuses. On **B** or **C** the merge is aborted by Step 0; the EM never runs
  `git merge --abort`.
- **Handoff triage, advisory probes, freshness, the weekly group, the markers** — manifest steps of
  the run. Their findings arrive in the briefing; nothing is re-queried.
- **The register stall check** — run by the launch via `coordinator-invoke requirement_register.stall_report`; findings render under `### Register stall check` in the briefing.
- **Inbox memos (`j-memo-*`) and the other judgment points** — resolved by rule or by the run's
  agents, which carry the inbox rules in their briefs.

**Dispatch authorization — invoking this skill IS the request.** The dispatches named below are constitutive steps of this skill, not a separate thing to get cleared: invoking a skill requests the actions that skill performs. A harness line permitting dispatch "unless the user requested it" is therefore **satisfied here, not overridden** — no precedence claim is needed and none is made. Re-asking spends the very context the dispatch exists to protect. The rule attaches to skill entry and dissolves no PM-authored gate: keyword-gated skills gate entry, and every gate a skill names for itself still binds — per-session cross-repo-commit assent, ask-before-external-action, and any other this skill's own body names. Tripwire: `UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`. Rationale: wiki § Skill rationale.

## Judgment points left to a person

**Report the Group EM.** From the run's `groupem-nomination-who` and `groupem-watch` rows,
say who holds the role and whether the watch is armed, or that the box has none. Report only: this
ceremony never offers, nominates or calls `groupem.enter`; the G-EM is entered from the group-em home.

**Day focus.** If `$ARGUMENTS` is provided: _"Requested focus: {arguments}"_ — carry it into
"What should today's focus be?" in the briefing.

## What This Does NOT Do

Bug-sweep / daily-code-health / deep-architecture-survey / update-docs (dedicated invocations).
Merge to main. Choose work (`/workstream-start`'s Engage section). `/update-docs` and `/bug-sweep`
are recommended, never auto-dispatched from here — a PM call. `/workday-complete` is the evening
counterpart.
