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

## See also

- `skills/handoff/SKILL.md` Step 0 — handoff trigger gate (YES-tests / NO-tests)
- `skills/spinoff/SKILL.md` Step 0 — PM-authorization gate
- `skills/session-end/SKILL.md` — lessons/state capture
- `CLAUDE.md` § Handoff Lineage — single-predecessor doctrine
