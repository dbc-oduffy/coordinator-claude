---
name: fire-and-forget
description: "\"fire and forget\" / \"fire and forget\": a raw ask or sizing to a reviewed commit in one fire."
allowed-tools: ["Read", "Edit", "Write", "Bash", "Grep", "Glob", "Agent", "Skill", "Workflow"]
argument-hint: "<raw ask | state/sizings/<id>.yaml>"
---

# Warp-Speed-Execute

The EM's one act on an engineering ask: submit it to the engine. The engine fires the workflow —
the sizing agent, then the branch its result picks, through review, docs, commit and close. This
command forwards to no other command and no autofire hook matches it.

**Contract: one workflow, start to finish. While it is live the EM does not dispatch, poll,
monitor, verify or relay; it sits idle until the run exits.** The run's checker is the only
legitimate end of a run, and it judges against every PM verbatim and revision; on its pass the EM
reports the run as all of what the PM asked for. A run never stops to obtain the PM's own words:
every exit-criterion, scope, mode or `xl_exit` ruling goes to `coordinator:apm` in-run. Any other
halt (gate refusal, blitz refusal, a DR awaiting acceptance, or a hand-dispatched row) breaks this
command: report it as a defect, and never finish the work by hand-dispatching rows.

**PM revisions mid-run** go in verbatim through `coordinator-invoke workflow.revise '{"run_id":"<id>","verbatim":"<PM verbatim>"}'`. They
are never a new dispatch and never a second submission. Once a plan has pinned its register rows
(`register_claims.pins`), a revision whose new row changes a pinned row trips `register-pin-drift`:
plan-blitz pulls the plan and the run halts. Re-planning against the new row is not an EM step; the
engine owns it.

Any session, a peer included, steers a running Workflow only through `workflow.revise`; a peer adds
`"from":"<its session id>"`, stamped on the ledger row and read as authoritative. Check the op's
params for `from` before sending it. Editing or committing the plan or sizing is not a
revision: it races the run's scoped commits and records no ledger row. Open engine-plane gap:
revise against a held, not-yet-emitted run refuses ("no ledger-bearing run ... emit it first").

**The run commits itself.** The in-run commit is the user's commit request: its last stage is one
`coordinator:git-commit-agent` call to `dispatch.land_run` under the run token. The commit
ships the sizing and carries the run's delivery note, `docs/delivery/<run_id>.md`
(`A-RUNS-DELIVERY-NOTE-IS-COMMITTED-UNDER-DOCS-DELIVERY`). The EM runs no `dispatch.land_run` after a run that committed. Only a run that exits
uncommitted (a halt before the commit stage, or a non-`none` `next_action`) gets `coordinator-invoke
dispatch.land_run` with its `params`, unedited; the run token admits one landed commit, and a failed, refused, empty or raising commit releases it for a retry. A run that hits a usage
limit reports `halted_by: usage_limit` with `resets_at`: `TaskStop` it, then `Workflow({ scriptPath,
resumeFromRunId })`; a dead run is committed by that op with its `script_path`.

**Cross-repo deliverables.** Each row writes in the repo its path names, and the commit stage lands
one scoped commit per repo (`sibling_commits`). Cloud
(`CLAUDE_CODE_REMOTE=true`) proceeds without asking. On a local box the submission is denied at
`approve_cross_repo_write` naming the sibling repos: ask the PM; on approval resubmit with
`cross_repo_approved: true` in `args` (this session's cross-repo commit assent). Never refuse a cross-repo ask
outright. A write outside every git checkout is refused at emit. A row with an `external_gate` is
withheld and listed as incomplete at commit.

## Submit

One call is the whole submission:

- **A raw ask** — `Workflow({name: "coordinator:engine-ask", args: {ask: "<raw ask>"}})`, the
  PM's words verbatim.
- **An accepted sizing** (`state/sizings/<id>.yaml`, `exit_criterion.accepted` present) —
  `Workflow({name: "coordinator:engine-ask", args: {sizing: "<sizing path>"}})`; the run starts
  at `plan`.

Outside a repo cwd add `repo: "<abs repo path>"`; after the PM approves a local cross-repo write
add `cross_repo_approved: true`. The PreToolUse(Workflow) hook emits the run from `args` and
rewrites the call to fire it, so that call IS the background run: end the turn. A refusal is the
call's deny: relay it with the room it names (`shape`, `roadmap`, `pm-decision`; a `pm-decision`
goes to `coordinator:apm` first). The `engine-ask` stub runs only when the hook did not, and its
halt is a defect report. Never run `emit-dispatch-workflow` or dispatch `coordinator:sizing-scout`
by hand, and never pass `--fire` (a headless child the foreign-emission guard refuses).
Tripwire: `ENGINE-ASK-SUBMISSION-IS-THE-RUN`.

**Relay fallback — only when the engine refuses the submission:** `emit-wave-fire --from-sizing`,
and the closing report names the refusal. Tripwire: `NOVEL-WORK-IS-ONE-FIRE-NEVER-A-RELAY`.

Fan-out past ~50 agents needs a costed 2-13 agent slice first: `coordinator/docs/wiki/dispatching-parallel-agents/costed-slice-before-fan-out.md`.

## Touchpoints

Where the engine places a touchpoint, by interaction mode, is
`coordinator/contract/warp-touchpoints-fragment.json`; read it, never restate it. A warp run is
`ceo` mode, never hands-on: at any touchpoint that asks for the PM's words, the run's
`coordinator:apm` rules, recorded where the PM quote would go, labelled `APM ruling`, never as PM
words. Gates that stay with the PM: merge to main, publish, cross-repo commit.

A refusal names every missing field once. Relay it verbatim; never work around it by hand-running
the stages. The closing report reads the run's completion receipt.
