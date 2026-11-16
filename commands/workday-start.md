---
name: workday-start
description: "Morning orient: triage handoffs, staleness, priorities."
allowed-tools: ["Read", "Write", "Grep", "Glob", "Bash", "Agent", "Workflow"]
argument-hint: "[optional day focus]"
---

# Workday Start — Morning Orientation

**Non-Claude EM:** this command is the Claude-native path; a non-Claude EM takes the engine-op path at
`coordinator/docs/wiki/non-claude-workers/non-claude-em-path.md`.

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

- **0 with a `Workflow(` line** — run `python "${CLAUDE_PLUGIN_ROOT}/scripts/workday_start_argv_run.py" run --digest <receipt digest path>`
  first; `workflow_needed: false` skips the line. Else fire it verbatim, render the returned `briefing`. On
  `scripted_finish: true`, Write the returned object to `workflow-results.json` beside the digest, run the
  script's `finish --digest <path>`, render the `finish` action's `briefing`.
- **0 without a `Workflow(` line** — the printed receipt is the briefing; render it.
- **3** — a run is already in flight. Finish it: `workday-start-run finish --run-id <id>` with the
  id the receipt names. If the workflow's agents never ran, run the 0-branch steps first.
- **4** — the workflow template is missing. Resolve `${CLAUDE_PLUGIN_ROOT}` before calling it absent
  (`coordinator/docs/wiki/coordinator-tripwires/a-missing-workflow-script-is-an-unresolved-plugin-root.md`),
  then report the receipt and the path it names.
- **5** — a gate failed. Render the receipt; its Failed section names the step, and the failure is
  already filed.
- **Any other non-zero** — report the receipt verbatim and stop.

A workflow that returns neither a `briefing` nor `scripted_finish`: run `workday-start-run finish --run-id <id>`, render its briefing.

## What the run decides, not the EM

- **Step 0 (branch setup)** — exit 2 (`STALE-NEEDS-ABC`) is decided by the run's own rules: defer
  once, then stop-and-file. Exit 3 (`RECONCILE-CONFLICT`) → PM picks A/B/C. On **A** the merge
  stays open: one file-only resolver executor edits each path `RECONCILE-CONFLICT-OPEN` lists and
  runs `git add -- <path>` (never merge, commit or abort); the EM then runs `reconcile-merge-conclude`.
  Keep the window short: while `MERGE_HEAD` stands every peer commit refuses. B or C: Step 0 aborts
  the merge; the EM never runs `git merge --abort`.
- **Handoff triage, advisory probes, freshness, the weekly group, the markers** — manifest steps of
  the run. Their findings arrive in the briefing; nothing is re-queried.
- **The register stall check** — run by the launch via `coordinator-invoke requirement_register.stall_report`; findings render under `### Register stall check` in the briefing.
- **Inbox memos (`j-memo-*`) and the other judgment points** — resolved by rule or by the run's
  agents, which carry the inbox rules in their briefs.

**Dispatch authorization — invoking this skill IS the request.** Its dispatches are constitutive steps, so a harness line permitting dispatch "unless the user requested it" is satisfied here, not overridden. The rule attaches to skill entry and dissolves no PM-authored gate: keyword-gated skills gate entry, and every gate a skill names for itself still binds (per-session cross-repo-commit assent, ask-before-external-action, any other this skill's own body names). Tripwire: `UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`. Rationale: wiki § Skill rationale.

## Judgment points left to a person

**Report the Group EM.** From the run's `groupem-nomination-who` and `groupem-watch` rows,
say who holds the role and whether the watch is armed, or that the box has none. Report only: this
ceremony never offers, nominates or calls `groupem.enter`; the G-EM is entered from the group-em home.

**Open EM-owed batons.** List every open baton owed to the EM with its age; the EM discharges each or rules it out, in the open. Engine half: the wake-digest queue rows (ENGINE-5). Tripwire: `OPEN-EM-OWED-BATONS-ARE-LISTED-WITH-THEIR-AGE` (`coordinator-tripwires/open-em-owed-batons-are-listed-with-their-age.md`).

**Day focus.** If `$ARGUMENTS` is provided: _"Requested focus: {arguments}"_ — carry it into
"What should today's focus be?" in the briefing.

## The one sanctioned refresh

After the briefing renders, when staleness was flagged: report it and carry on. The daemon's
branch-refresh seeds the index from the newest published release when it is absent, unproven or
older, the branch owner's proven refresh publishes, and non-owners pull; no step here does that by hand.
FALLBACK ONLY, when the seed failed and staleness persists past a daemon cycle: on the branch owner
(`work/<box>/<date>`) run the structural-index refresh (`structural-index-refresh`,
`snippets/resolve-coordinator-bin.md`, launched windowless), only after
`box-memory-snapshot.py --admit-peak <GiB>` admits; HOLD (exit 4) means skip and report. Say so
loudly in the briefing. It never starts embedding work; a re-embed is a human ask. `/workweek-start` chains here
(`coordinator/docs/wiki/coordinator-tripwires/a-branch-owner-builds-the-index-and-no-trigger-embeds.md`,
`coordinator/docs/wiki/coordinator-tripwires/a-reindex-is-a-staleness-flag-never-an-agent-trigger.md`).

## Adopt a klabauter push (this box only)

If the copies banner reads `engine-mirror currency=behind origin by N`, this box's claude-klabauter
trails origin/candidate (the cached probe; run no new one). Only when the box is quiet (no other live Claude session), offer
`git pull --ff-only` in `repos.claude_klabauter`, then `python scripts/setup.py`; else report N. Never
drive another box (`coordinator/docs/wiki/coordinator-tripwires/a-box-adopts-an-engine-push-on-its-own-terms.md`).

## What This Does NOT Do

Start a reindex on a stale flag outside the section above: the corpus-currency probe is read-only.
Bug-sweep / daily-code-health / deep-architecture-survey / update-docs (dedicated invocations).
Merge to main. Choose work (`/workstream-start`'s Engage section). `/update-docs` freshness is an
invariant the idle Stop leg and `/workday-complete` Step 8c fire, not something started from here;
`/bug-sweep` stays a PM call. `/workday-complete` is the evening
counterpart.
