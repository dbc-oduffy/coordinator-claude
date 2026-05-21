# Cross-Repo Communication and Handoff/Spinoff Discipline

> When the EM needs to tell another repo's EM (or session) something — or thinks it does — this is the decision tree.

## TL;DR

**Handoffs and spinoffs are session-continuity artifacts within a single repo, not cross-repo messages and not wrap-up ceremonies.** Cross-repo communication routes through the PM as a human relay.

## The four legitimate triggers for `tasks/handoffs/` or `tasks/spinoffs/`

| Trigger | Skill | Shape |
| --- | --- | --- |
| Context pressure mid-workstream | `/handoff` | Continuation — successor session resumes |
| Lessons/state capture at session end | `/session-end` | Audit trail, no successor required |
| PM-authorized fork of a different topic | `/spinoff` | New file, `kind: spinoff`, `predecessor: none` |
| Pickup of an existing handoff | `/pickup` | Mutates frontmatter in place, never creates new files |

Nothing else creates files in those directories. The PreToolUse hook `block-unauthorized-handoff.sh` enforces this at the tool boundary.

## Decision tree

**"I want to coordinate something — what's the primitive?"**

### Same session continuation

→ Just keep working. No artifact needed.

### Mid-workstream save forced by context pressure

→ `/handoff`. Successor in same repo resumes. NOT for tidy stopping points — see `skills/handoff/SKILL.md` Step 0 NO-tests.

### Fork to a new workstream in the same repo

→ Surface candidate to PM: `Candidate spinoff: <slug> — <topic>. Authorize?` and block. PM types `/spinoff` if they want it. Never EM-initiated.

### Tell another repo's EM about something

→ **Default — copy-paste in chat.** Write the message inline; PM ferries it.

→ **If the brief is large or complex:** write directly to `archive/cross-repo/YYYY-MM-DD-<topic>.md` in the current repo. Hand the PM the link. PM pings between chats. (Create the `archive/cross-repo/` directory on first use — it's tracked alongside the other `archive/` subdirectories, no special gitignore handling needed.)

→ **For DoE-altitude cross-EM relay traffic — named-topic memos and reply memos that are part of an active consult chain:** use `tasks/memos/YYYY-MM-DD-<topic>.md` as the **living surface**. This is where live multi-memo conversations happen; the PM ferries each memo between sessions by handing the path. Once the consult resolves, the memo stays in `tasks/memos/` as a lightweight audit trail — it does not migrate to `archive/cross-repo/`. Empirical instances as of 2026-05-19: 5 memos across the whoami contract consult chain and the machine-local-registry DoE reply.

  **Surface distinction:**
  - `tasks/memos/YYYY-MM-DD-<topic>.md` — **live** consult traffic; named-topic memo + reply pairs; referenced directly during an active consult chain.
  - `archive/cross-repo/YYYY-MM-DD-<topic>.md` — **archive** destination for large or complex briefs that exit the live surface; intended as reference artifacts, not active traffic.

<!-- Amended 2026-05-19 by 2026-05-19-cross-plugin-whoami-contract.md: tasks/memos/ surface documented; live vs archive distinction added. -->

→ **Never:**
  - Write to the other repo's `tasks/handoffs/` or `tasks/spinoffs/` — you don't own that surface.
  - Write to *your* `tasks/handoffs/` "for someone to pick up later" — that's not what the folder is for.
  - Write to "a document to which a thing can be appended" — there is no shared append surface for cross-repo coordination. The PM is the only relay.

### Completion of a workstream

→ Commit and stop. Or `/workday-complete`. Or `/workweek-complete` / `/merge-to-main` at the appropriate boundary. **Not a handoff.** A handoff is by definition a mid-workstream save under pressure; using it as a wrap-up ceremony is the trap (see `skills/handoff/SKILL.md` Step 0 NO-tests).

## Why this discipline exists

Two recurring failure patterns:

1. **Handoff-as-completion-ceremony.** EMs reach for `/handoff` at "tidy stopping points" because it feels like a clean wrap. The handoff folder fills with dreck — closed work dressed as in-flight continuation — and `/session-start` / `/workday-start` surface stale entries that waste future-EM attention. Fix: handoffs only when context pressure forces it; commit-and-stop or `/workday-complete` handle clean endings.

2. **Spinoff-as-cross-repo-message.** EMs reflexively reach for `kind: spinoff` when they want to tell another repo's EM something, because `/spinoff` is what the doctrine talks about. The other repo never reads our `tasks/handoffs/`. The actual primitive is the PM as a human relay — copy-paste in chat, or archive-link for large briefs. Fix: route cross-repo coordination through the PM, never through file-system surfaces in either repo.

## Plan skill integration

`coordinator:plan` Branch C rejects any chunk that authors a handoff, spinoff, or session-end artifact. Plans that pre-authorize "Chunk N: write a spinoff to <topic>" launder the PM gate through plan approval — by execution time the EM treats it as a checklist item and the spinoff's Step 0 PM-gate never fires. Cross-EM coordination chunks should read "surface cross-repo brief to PM" with the brief written inline or to `archive/cross-repo/`.

## Hook tripwire

`hooks/scripts/block-unauthorized-handoff.sh` blocks `Write` that creates a new file in `tasks/handoffs/` or `tasks/spinoffs/` unless:

- The active transcript shows recent invocation of `/handoff`, `/session-end`, or `/spinoff`, OR
- `COORDINATOR_HANDOFF_AUTHORIZED=1` is set in the environment (manual override for edge cases).

Edits to existing handoff files are always allowed (covers `/pickup` frontmatter mutation and `Step 2.10` review-marker writes).

## In-session verification vs. cross-repo acceptance handoff

**Prefer in-session verification over cross-repo acceptance handoff when the host EM has corpus + tool access.**

The default reflex on a cross-repo deliverable is to ship the contract artifact and file an acceptance-handoff in the consumer repo. But when the host EM (the one shipping the producer) has both the consumer repo's source corpus and the tool access to run the consumer's verification commands, doing the verification in-session is strictly better — it closes the loop before the handoff is filed, eliminating:

- The **"filed but never picked up"** failure mode — acceptance handoffs that age out unread.
- The **"picked up but premise stale"** failure mode — consumer-side EM picks up a handoff whose substrate has drifted.

**File an acceptance handoff only when:**

1. The consumer repo's tooling isn't accessible from the host session.
2. The consumer-side change is architecturally weighty enough to want a fresh planning pass.
3. Consumer-side EM bandwidth is a known constraint that makes in-session closure impractical.

Otherwise: verify in-session, ship both producer and consumer halves under one workstream, file no handoff.

## Lifecycle and dirty-file backstop

> Added 2026-05-21 under PM ruling (plan `docs/plans/2026-05-21-cross-repo-memo-discoverability.md`): cross-repo memo delivery now has a belt-and-suspenders lifecycle with structural backstops.

### Cross-repo write categories — three altitudes

This plan introduces a third cross-repo write category alongside the two defined below:

- **Doctrine-seeding writes** (DoE altitude) — CLAUDE.md additions, `docs/wiki/` entries, agent-prompt amendments. Authored from DoE / HoP altitude; the sibling EM may amend on receipt. Direct cross-repo write is legitimate.
- **Implementation-intent writes** — source edits, machine-local entries, install scripts, sentinel files, registry edits, hook execution semantics. *Anything that changes what runs in the receiver repo.* These route via memo + PM-relay + sibling-EM-lands. The `## Doctrine seeding vs. code/install-surface change` section below governs these.
- **Delivery-intent writes** — addressed artifacts placed in the receiver's working tree that do NOT change what runs. Specifically: `tasks/memos/YYYY-MM-DD-<topic>.md` files whose purpose is to signal the receiver EM. The dispatching EM is the author; the receiver EM is the intended reader. The write is intentionally uncommitted so it surfaces as a dirty-file signal. This is NOT a PM-authorized exception — it is a PM-endorsed primary delivery primitive for the belt-and-suspenders lifecycle codified here.

The key carve criterion is **artifact effect**, not subject matter:

> A cross-repo write is **delivery-intent** if the artifact itself, landing in the receiver tree, does not alter what runs in the receiver repo — even if its *contents* recommend an implementation change. The recommendation, if accepted, lands as a separate commit on the receiver side under their own implementation context. Delivery-intent writes are the memo itself; implementation-intent writes are the receiver's response to it.

### Schema

Memo files use `plugins/coordinator/schemas/cross-repo-memo.yaml`. Key fields:

- `from:` / `to:` — author EM id and receiver EM id (e.g. `claude-central-em`, `project-rag-em`)
- `status:` — `open | reviewed | action_taken | closed | superseded`
- `delivery_mode:` — `receiver-repo | central-only`
- `decision:` — required at `action_taken` (`accepted | declined | partial | superseded`)
- Lifecycle timestamps: `received_at`, `reviewed_at`, `action_taken_at`, `closed_at` (ISO-8601; authoritative audit trail is the receiver's git log of the transition commit)

State machine: `open → reviewed → action_taken → closed`. Transitions happen via receiver-side Edit-and-commit on the memo file. `superseded` is an out-of-band terminal (chain via `supersedes:` / `superseded_by:`).

### Dispatcher CLI

`plugins/coordinator/bin/cross-repo-memo` writes both the receiver-side memo and the central archive copy.

```
cross-repo-memo --to <receiver-em-id> --topic <slug> --title "<one-line>" \
  [--body-file <path>] [--delivery-mode receiver-repo|central-only]
```

Receiver repo path resolves via `machine-local get repos.<key>` (e.g. `project-rag-em → repos.project_rag`). On machines where the repo isn't present, falls back to `--delivery-mode central-only` and prints an explicit warning.

The dispatcher always prints both paths and a one-line reminder: `Hand the PM both paths — PM-relay is still the primary channel.`

**`--self-receipt` mode:** when the dispatching EM is effectively the receiver (central-EM acting in a trio repo on its own behalf), pass `--self-receipt`. The memo is written and committed immediately with `status: action_taken`. The PM-relay reminder is suppressed. The archive copy is also written at `action_taken` (not `open`) — audit trail only, not delivery.

### `/workday-start` Step 1.45 surfacing

A step inserted between Step 1.4 (cross-reference completed archive) and Step 1.55 (Recent Roadmap Orientation) queries `~/.claude/archive/cross-repo/*.md`, parses frontmatter, filters to `status ∈ {open, reviewed}`, and surfaces:

```
Outstanding cross-repo memos (DoE attention):
- 2026-05-13 → holodeck-em: marker-dir collision — open (8 days)
- 2026-05-21 → project-rag-em: gate-check failures — reviewed (action pending)
```

Staleness flags:
- `open` >7 days: append ` [STALE — receiver hasn't read]`
- `reviewed` >14 days: append ` [STALE — action pending]`

Cap: ≤8 entries; `(N more — see ~/.claude/archive/cross-repo/ for full list)` truncation prompt beyond that.

`action_taken` and `closed` drop off the surface. The helper script is `bin/workday-start-cross-repo-memo-surface.sh`.

### Grandfather cutoff

**Pre-2026-05-22 memos are grandfathered.** The schema validator applies only to memos with `created: >= 2026-05-22`. Step 1.45 also skips pre-cutoff memos by design — they will not surface in `/workday-start`. If a pre-cutoff memo has unfinished business with its addressee, options are: (a) re-issue under the new schema via `cross-repo-memo` with `supersedes: <old-archive-path>` set (preferred — exercises the supersession chain), or (b) handle out-of-band. Pre-cutoff memos will not self-surface; the re-issue path is the correct routing for anything still live.

**Pre-cutoff inventory (as of 2026-05-21):**

Archive copies (in `~/.claude/archive/cross-repo/`, all grandfathered):
- `~/.claude/archive/cross-repo/2026-05-21-holodeck-em-marker-dir-collision.md`
- `~/.claude/archive/cross-repo/2026-05-21-project-rag-em-gate-check-failures.md`
- `~/.claude/archive/cross-repo/2026-05-21-project-rag-em-session-start-hook-resolver.md`
- `~/.claude/archive/cross-repo/2026-05-21-project-rag-em-three-findings-host-substrate.md`

Live consult traffic (in `~/.claude/tasks/memos/`, all with `created: <= 2026-05-21` are grandfathered):
- `~/.claude/tasks/memos/2026-05-19-machine-local-doe-reply.md`
- `~/.claude/tasks/memos/2026-05-19-project-rag-addon-em-whoami-sentinel.cover.md`
- `~/.claude/tasks/memos/2026-05-19-project-rag-em-whoami-sentinel.md`
- `~/.claude/tasks/memos/2026-05-19-project-rag-host-em-whoami-sentinel.md`
- `~/.claude/tasks/memos/2026-05-19-project-rag-host-em-whoami-sentinel.reply.md`
- `~/.claude/tasks/memos/2026-05-19-whoami-contract-ready.md`
- `~/.claude/tasks/memos/2026-05-19-whoami-ue-addon-coordination.md`
- `~/.claude/tasks/memos/2026-05-20-doe-reply-machine-local-third-criterion.md`
- `~/.claude/tasks/memos/2026-05-20-em-memo-coordinator-substrate-and-doctor.md`
- `~/.claude/tasks/memos/2026-05-21-addon-em-ack-producer-seam-disposition-4.md`
- `~/.claude/tasks/memos/2026-05-21-host-em-reply-producer-seam.md`

### Worked example

Memo from `claude-central-em` to `project-rag-em`, walked through the full `open → reviewed → action_taken → closed` lifecycle.

**Step 1 — Dispatcher writes the memo (2026-05-22).**

`~/.claude/archive/cross-repo/2026-05-22-gate-check-fix.md` (archive copy, committed by central-EM):
```yaml
---
title: "Gate-check failures in bin/check-plugin-drift.sh — recommended fix"
from: claude-central-em
to: project-rag-em
created: 2026-05-22
status: open
delivery_mode: receiver-repo
receiver_copy_path: X:/project-rag/tasks/memos/2026-05-22-gate-check-fix.md
---
```

`X:/project-rag/tasks/memos/2026-05-22-gate-check-fix.md` (receiver-side copy, NOT committed — left as `??` in project-rag's `git status`):
```yaml
---
title: "Gate-check failures in bin/check-plugin-drift.sh — recommended fix"
from: claude-central-em
to: project-rag-em
created: 2026-05-22
status: open
delivery_mode: receiver-repo
---
```

Dispatcher prints both paths and: `Hand the PM both paths — PM-relay is still the primary channel.`

**Step 2 — project-rag-EM sees the dirty file** at next session-start (`git status` shows `?? tasks/memos/2026-05-22-gate-check-fix.md`), reads it, transitions to `reviewed`:
```yaml
status: reviewed
received_at: 2026-05-23T09:15:00Z
received_by: project-rag-em
reviewed_at: 2026-05-23T09:20:00Z
```
Commits with message: `memo: mark 2026-05-22-gate-check-fix reviewed`

**Step 3 — project-rag-EM implements the fix, transitions to `action_taken`:**
```yaml
status: action_taken
action_taken_at: 2026-05-23T11:05:00Z
decision: accepted
decision_note: "Fixed gate-check exit-code handling in bin/check-plugin-drift.sh"
```
Commits alongside the fix commit.

**Step 4 — central-EM reconciles at workday-start.** Step 1.45 surfaces the memo as still `open` (archive copy hasn't been updated yet). Central-EM queries project-rag git log, sees the `action_taken` commit, updates the archive copy:
```yaml
status: closed
closed_at: 2026-05-23T14:00:00Z
action_taken_at: 2026-05-23T11:05:00Z
decision: accepted
```

Memo drops off Step 1.45 surface at next workday-start.

### "Never" list update

The existing "Never" list in the decision-tree above prohibits writing to `tasks/handoffs/` and `tasks/spinoffs/` in other repos. That prohibition remains. However, **`tasks/memos/` writes ARE permitted** under the delivery-intent lifecycle described in this section — they are the delivery primitive, not a surface you "don't own." The distinction: memos are addressed artifacts with the receiver's lifecycle control; handoffs/spinoffs are session-continuity artifacts that only the owning repo's session-start ceremonies should manage.

Closes `tasks/coordinator-improvement-queue.md:221` (2026-05-21 entry on memo shape convention).

## Doctrine seeding vs. code/install-surface change — two different cross-repo altitudes

> Added 2026-05-21 under PM ruling (see `~/.claude/docs/plans/2026-05-21-install-surface-completeness-doctrine.md` § PM-Q1 RESOLVED): not all cross-repo writes are the same. Doctrine and code live at different altitudes; conflating them produces churn.

Two altitudes:

### Doctrine seeding (DoE altitude)

CLAUDE.md additions, `docs/wiki/` entries, agent-prompt amendments, skill/hook authorial changes — anything that shapes *how* a sibling repo's EM works rather than *what* code runs.

- **Legitimate as direct cross-repo write** when authored from DoE / HoP altitude (central-EM acting on PM direction). The DoE has standing to seed alignment across repos.
- **Provenance required.** Commit message names the doctrine-seeding context: `"DoE doctrine-seeding under PM direction <date>; sibling EM may amend on receipt"`.
- **Sibling EM may amend on receipt.** Doctrine seeded into another repo isn't a fait-accompli; the receiving EM has the standing to refine, contextualize, or push back via memo if the seeded doctrine misfits.

### Code / install-surface change (EM altitude)

Source edits, machine-local entries, install scripts, sentinel files, registry edits, hook execution semantics — anything that changes *what runs* on a sibling repo's install surface.

- **Routes via memo, not direct write — and the PM relays.** `archive/cross-repo/` for archival briefs, `tasks/memos/` for live consult chains. **Writing the memo file is half the work; the other half is handing the PM the path so they ferry it to the affected sibling EM.** A memo written without PM-relay is a document dropped in a hole — the affected EM has no signal to look at it. Per the decision-tree section above ("Tell another repo's EM about something"), the PM is the only cross-repo relay; the file is the record, not the trigger. Once briefed, the sibling EM lands the change with their own implementation context.
- **PM-authorized direct writes are the documented exception**, not the default. Record the authorization in the commit message when invoked.
- **Why the altitudes differ.** Doctrine is alignment work the DoE owns; code is implementation work the sibling EM owns. Conflating them produces churn in both directions — DoE doctrine that never lands because it routed through a slow memo loop, OR sibling-repo code edits that lose the implementing EM's context.

### the Director of Engineering's cross-repo stance — lean, don't diktat

The Director of Engineering (DoE) carries cross-team / cross-repo authority that EM-altitude reviewers (the Staff Engineer et al.) do not. **In meatspace, nobody likes a DoE who parades around making calls for another team.** the Director of Engineering's posture in this regime:

- **Doctrine altitude: author and seed directly.** the Director of Engineering can write doctrine that lands in sibling repos (CLAUDE.md additions, wiki entries, agent prompts) under PM direction. This is alignment authority.
- **Code/install-surface altitude: lean, name the direction, insist on coordination.** the Director of Engineering can say "the producer should expose X" or "the consumer is making an assumption that won't hold" — as a recommendation, with reasoning. Findings that implicate a sibling repo's code or install surface MUST surface as `cross_team_directive` requesting EM-coordination (memo to `archive/cross-repo/` or `tasks/memos/` **and PM-relay to the affected EM** — the Director of Engineering writes the memo, the EM dispatching the Director of Engineering hands the PM the link), not as a directive landed on the peer's surface.
- **The catalyst, not the implementer (for code).** Code changes that follow from the Director of Engineering's recommendations route through the standard memo channel; the sibling EM lands the change in their own repo with their own context.
- This narrows the previous the Director of Engineering framing ("Your finding stands as a directive, not a polite suggestion") to the *code-altitude* axis. Doctrine-altitude authority is preserved and made explicit. The previous framing produced cleanup churn when the Director of Engineering's code-altitude directives on peer-repo surfaces landed without the affected EM's context.

## See also

- `skills/handoff/SKILL.md` Step 0 — handoff trigger gate (YES-tests / NO-tests)
- `skills/spinoff/SKILL.md` Step 0 — PM-authorization gate
- `skills/session-end/SKILL.md` — lessons/state capture
- `CLAUDE.md` § Handoff Lineage — single-predecessor doctrine
- `~/.claude/docs/wiki/install-surface-completeness.md` — the universal install-surface rule, which combines with the cross-repo doctrine differently at the two altitudes above
