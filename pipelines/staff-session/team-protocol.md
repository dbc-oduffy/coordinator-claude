# Staff Session Protocol

> Referenced by `coordinator/skills/staff-session/SKILL.md` and debater/synthesizer prompt templates. Doctrine: `coordinator/docs/wiki/dispatching-parallel-agents/chatty-workflows.md`.

## Overview

Chatty-Workflow collaborative planning and review: the EM writes a scope document, selects persona-based debaters + one synthesizer, fires ONE background `Workflow`, and is **freed**. The script runs the debate as rounds — positions and challenges, a rebuttal round, synthesis. The EM is notified by the Workflow's task notification when it completes.

## Roles

| Role | Model | Count | Responsibility |
|------|-------|-------|----------------|
| **Debater** | Opus | 2-5 | Persona agent (the Staff Engineer, the Director of Engineering, the Game Dev Reviewer, etc.). Reads scope + codebase, forms a position from their persona's perspective, appends challenges to peers' mailboxes, writes a position document. Never addresses the EM. |
| **Synthesizer (overseer)** | Opus | 1 | the Director of Engineering (eng-director). Director of Engineering. Runs after the debate rounds return. Cross-references all position documents, resolves disagreements with Director-of-Engineering authority — weighting organizational benefit, customer-serving, velocity-over-time, cross-team boundary-setting, and generic-substrate discipline. Debaters are staff-engineer altitude advocating for their domain's local optimum; the Director of Engineering's rank is the corrective. Represents all positions fairly in Dissent/Contested sections but does not default to conservative resolutions or average the loudest voices. Writes optional advisory. The only agent whose return value goes to the EM. |

## Lifecycle

```
EM: Write scope.md → Select roster → Fire Workflow → FREED
Round 1 (parallel):
  each debater → read scope.md + context → research codebase → write {persona}-position.md
               → append CHALLENGE/QUESTION lines to each peer's mailbox → return
Round 2 (continuation, bounded: 1 rebuttal round):
  each debater with unread mail → fresh continuation agent
    → reads its mailbox, its prior position file, its predecessor's return value
    → answers challenges, revises its position file → returns
Synthesis (overseer):
  → read all position documents → synthesize (plan: consensus + dissent, review: findings + verdict)
  → write advisory if applicable → return the completion summary to the EM
```

No scout phase — debaters read the EM's scope document and the codebase directly.

## Ordering

Ordering replaces `blockedBy`: round 2 starts after every round-1 `agent()` call returns; synthesis starts after round 2 returns. A wake is a continuation dispatch, never a resume — `SendMessage` cannot resume a returned workflow agent.

## Mailbox Protocol — Debate

Peers exchange through `{scratch-dir}/mail/<persona-slug>.jsonl`. To message peer X, append a line to X's file: `{"from": "<persona-slug>", "text": "<message>"}`. After reading its own file, a reader appends `{"read": true}`; it has unread mail when lines follow its last read marker. No `SendMessage` to peers, to the synthesizer, or to the EM.

| Category | `text` format | When |
|---|---|---|
| **CHALLENGE** | `"CHALLENGE: Your position on {topic} has weakness {X}. Evidence: {reasoning}."` | Disagreement with a peer's position |
| **QUESTION** | `"QUESTION: Regarding {topic}, have you considered {X}? I found {evidence}."` | Seeking clarification or raising a consideration |
| **CONCESSION** | `"CONCESSION: You're right about {topic}. Updating my position to incorporate {X}."` | Accepting a challenge, in round 2 |

**Volume governance:** Max 3 lines per peer per round. A challenge cites evidence — a file:line or a quote from the peer's position document. Round 1 debaters read peers' position files when present; peers that have not written yet are challenged in round 2 instead.

**Backstop suspension:** Persona agents' built-in backstop invocations (e.g., the Staff Engineer's "invoke the Director of Engineering at High effort") are suspended during staff sessions. The debate rounds serve the same function — multi-perspective challenge. Debater prompt templates explicitly override backstop invocation.

## Fire

The EM does not write the script. `emit-dispatch-workflow --pipeline staff-session --brief {scratch-dir}/scope.md --flag mode=<plan|review> --list roster=<slug>=<agent_type>,... --out ...` renders `staff-session.manifest.yaml` (templates: `planner-` / `reviewer-` / `mailcheck-` / `continuation-` / `synthesizer-prompt-template.md`) and prints the `Workflow` line to fire; fire procedure in `coordinator/skills/staff-session/SKILL.md` Step 6. The workflow's return value is the synthesizer's completion summary.

## Failure Handling

| Failure | Action |
|---------|--------|
| Single debater crashes (no position written) | Synthesizer works with remaining positions. Note the gap: "Missing perspective: {persona}." EM can supplement manually. |
| Majority debater failure (>50% crash) | The synthesizer does not synthesize and returns a failure summary; the EM falls back to single-reviewer dispatch via `/review` (plan artifacts) or `/review-code` (code artifacts). |
| Synthesizer fails | EM reads raw debater position documents from scratch dir. Manual synthesis is feasible — position docs are structured. |
| Workflow refuses to start | Report to PM. Fall back to single-reviewer dispatch via `/review` (plan) or `/review-code` (code), or EM-authored plan. |
| Debate does not converge | The rebuttal round is bounded at one. Position documents capture the disagreement; synthesizer resolves or presents as dissent. |

## Scratch Directory Structure

```
tasks/scratch/staff-session/{run-id}/
  scope.md                    (EM input — objectives or artifact reference)
  mail/{persona-slug}.jsonl   (peer mailboxes)
  the Staff Engineer-position.md          (debater output)
  sid-position.md             (debater output)
  [the Data Science Reviewer-position.md]       (optional debater output — full tier)
  synthesis.md                (the Director of Engineering's synthesis — backup copy)
  advisory.md                 (the Director of Engineering's advisory, optional)
```
