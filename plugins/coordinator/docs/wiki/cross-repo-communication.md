# Cross-Repo Communication and Handoff/Spinoff Discipline

> When the EM needs to tell another repo's EM (or session) something — or thinks it does — this is the decision tree.

<!-- Spec backlink: docs/plans/2026-05-23-cross-repo-single-surface-and-canonical-scaffold.md § Chunk 4 -->
<!-- Negative-spec: The 2026-05-19 two-surface model (separate live-consult + archival surfaces) and the 2026-05-21 dual-write/symmetric-closure lifecycle are DELETED (plan: docs/plans/2026-05-23-cross-repo-single-surface-and-canonical-scaffold.md). One surface, one pattern: cross-repo/. Hand-rolling a memo file is the named anti-pattern; use cross-repo-memo CLI. -->

## TL;DR

**Handoffs and spinoffs are session-continuity artifacts within a single repo, not cross-repo messages and not wrap-up ceremonies.** Cross-repo communication routes through the PM as a human relay.

## The four legitimate triggers for `tasks/handoffs/` or `tasks/spinoffs/`

| Trigger | Skill | Shape |
| --- | --- | --- |
| Context pressure mid-workstream | `/handoff` | Continuation — successor session resumes |
| Lessons/state capture at session end | `/session-end` | Audit trail, no successor required |
| PM-authorized fork of a different topic | `/spinoff` | New file, `kind: spinoff`, `predecessor: none` |
| Pickup of an existing handoff | `/pickup` | Mutates frontmatter in place, never creates new files |

Nothing else creates files in those directories. This routing is enforced by the skill Step-0 gates, backed at the tool boundary by the `nudge-unauthorized-handoff.sh` PostToolUse hook — a non-blocking nudge that surfaces this routing when a new handoff/spinoff file is written without an authoring skill active (see § Hook tripwire).

## Decision tree

**"I want to coordinate something — what's the primitive?"**

### Same session continuation

→ Just keep working. No artifact needed.

### Mid-workstream save forced by context pressure

→ `/handoff`. Successor in same repo resumes. NOT for tidy stopping points — see `skills/handoff/SKILL.md` Step 0 NO-tests.

### Fork to a new workstream in the same repo

→ Surface candidate to PM: `Candidate spinoff: <slug> — <topic>. Authorize?` and block. PM types `/spinoff` if they want it. Never EM-initiated.

### Tell another repo's EM about something

→ **One pattern only: `cross-repo-memo --to <receiver-em-id> --topic <slug> --title "<one-line>"`.**

**Invocation mechanics (read this before you grep the source for flags):**
- It is a **self-executing CLI already on `PATH`.** Type `cross-repo-memo …` directly. Do **not** prefix `bash` (it's Python, not a shell script) and do **not** spell out a full `$HOME/.claude/.../bin/` path (it's on PATH).
- For a multi-line body, write the body to a temp file and pass **`--body-file <path>`**. With no `--body-file`, the CLI reads the body from **stdin**.
- **`--help`** lists every flag — reach for it instead of grepping the script.
- Do **not** route it through `pythonw`/`py` to dodge the Windows console flash. `pythonw` discards stdout, and this CLI prints the **receiver path on stdout that you must hand the PM** — you'd lose it. The transient flash is covered machine-wide by the ConPTY belt (`docs/plans/2026-05-29-windows-console-flash-elimination.md`), not by per-call interpreter gymnastics.

The CLI writes ONE memo file as a dirty (uncommitted) file into the receiver's repo at `<receiver-repo>/cross-repo/inbox/YYYY-MM-DD-<topic>.md`. The file carries `status: open`. The CLI prints the receiver file path — hand the PM that path for relay to the receiving session.

The act of sending is noted naturally in your session-end notes. No sender-side artifact, no separate sender-side ceremony. The sender keeps no copy.

**Directionality — the memo goes to the RECIPIENT's inbox, never your own.** `cross-repo/inbox/` in *your* repo is *your* **inbox**: it holds memos addressed TO you. When you send, the CLI writes the memo into the **recipient's** `cross-repo/inbox/` (their inbox), in their repo — not yours. A memo you put in your own `cross-repo/inbox/` sits where the recipient will never look. You never choose the destination by hand; `--to <receiver-em-id>` resolves it. The failure mode this prevents: an EM writing an *outbound* reply into its *own* `cross-repo/inbox/` and the recipient never finding it.

**Writing into another repo's `cross-repo/inbox/` is THE canonical exception to "don't change another repo".** General doctrine (and the Director of Engineering cross-team stance below) says EMs don't make changes in repos they don't own. Delivering a memo into a recipient's `cross-repo/inbox/` is the one sanctioned, blessed exception — because it is *delivery-intent* (a message, not a change to what runs in the receiver) and it is the single primitive that makes cross-repo coordination work at all. Do not hesitate to write a memo into a sibling's `cross-repo/inbox/` out of misplaced caution about the no-cross-repo-changes rule: that write is exactly what the rule is built around. (It is also why the CLI, not a hand-write, performs it — see the Never list.)

→ **Never:**
  - Hand-roll a memo file. Writing directly to any path — `cross-repo/`, `tasks/memos/`, anywhere — without the CLI is the named anti-pattern. A branch in the `validate-frontmatter-schema.js` PreToolUse hook (Chunk G) detects routing mismatches (memo `to:` field addressing a different repo than where the write lands) and hand-rolled `To:`/`From:` headers in memo-shaped paths, and offers `cross-repo-memo --to <recipient>` as `additionalContext`. It never blocks — offer-shape, not deny. Override: `COORDINATOR_OVERRIDE_MEMO_REDIRECT=1`.
  - Write to the other repo's `tasks/handoffs/` or `tasks/spinoffs/` — you don't own that surface.
  - Write to *your* `tasks/handoffs/` "for someone to pick up later" — that's not what the folder is for.
  - Write to "a document to which a thing can be appended" — there is no shared append surface for cross-repo coordination. The PM is the only relay.

### Completion of a workstream

→ Commit and stop. Or `/workday-complete`. Or `/workweek-complete` / `/merge-to-main` at the appropriate boundary. **Not a handoff.** A handoff is by definition a mid-workstream save under pressure; using it as a wrap-up ceremony is the trap (see `skills/handoff/SKILL.md` Step 0 NO-tests).

## Why this discipline exists

Two recurring failure patterns:

1. **Handoff-as-completion-ceremony.** EMs reach for `/handoff` at "tidy stopping points" because it feels like a clean wrap. The handoff folder fills with dreck — closed work dressed as in-flight continuation — and `/session-start` / `/workday-start` surface stale entries that waste future-EM attention. Fix: handoffs only when context pressure forces it; commit-and-stop or `/workday-complete` handle clean endings.

2. **Spinoff-as-cross-repo-message.** EMs reflexively reach for `kind: spinoff` when they want to tell another repo's EM something, because `/spinoff` is what the doctrine talks about. The other repo never reads our `tasks/handoffs/`. The actual primitive is the PM as a human relay — `cross-repo-memo` CLI for the file, PM for the relay. Fix: route cross-repo coordination through the PM and the CLI, never through hand-rolled surfaces in either repo.

## Plan skill integration

`coordinator:plan` Branch C rejects any chunk that authors a handoff, spinoff, or session-end artifact. Plans that pre-authorize "Chunk N: write a spinoff to <topic>" launder the PM gate through plan approval — by execution time the EM treats it as a checklist item and the spinoff's Step 0 PM-gate never fires. Cross-EM coordination chunks should read "surface cross-repo brief to PM via `cross-repo-memo`" with the path handed to the PM for relay.

## Hook tripwire

> **Reworked block → nudge 2026-05-29.** `hooks/scripts/nudge-unauthorized-handoff.sh` is a PostToolUse(Write) hook on `tasks/handoffs/` and `tasks/spinoffs/` that **warns without blocking** when a new file is written there without an authoring skill active. It replaces the deleted PreToolUse `block-unauthorized-handoff.sh`, which twice false-blocked a PM-authorized `/spinoff` (2026-05-28): its transcript-scrape could not see a skill invoked via the `Skill` tool, and a *block* gated on that unreliable signal fails closed (denies authorized work). The rework keeps the same best-effort scrape but uses it to SUPPRESS a non-blocking nudge (fails open — at worst one extra nudge the EM proceeds past). Mechanism: PostToolUse `exit 2` feeds the offer-shaped nudge into the model's next turn without blocking (PreToolUse `exit 2` would block; `exit 0`+stderr fails silent — see `hook-best-practices.md` § Friction-as-warning). Silence in autonomous runs: `COORDINATOR_HANDOFF_NUDGE_OFF=1`. The handoff-vs-spinoff routing doctrine in this wiki is also enforced by the skill Step-0 gates (`skills/spinoff` Step 0, `skills/handoff` Step 0); the hook is defense-in-depth. Full entry: `docs/wiki/coordinator-tripwires.md` § `NUDGE-UNAUTHORIZED-HANDOFF`.

A routing-mismatch branch in `validate-frontmatter-schema.js` (the same PreToolUse hook that enforces frontmatter schemas and the own-inbox deny guard) offers the `cross-repo-memo` CLI redirect when a Write carries a YAML `to:` field addressing a different repo than the one being written into, OR when a Write to a memo-shaped path (`*/memos/*` or a path under `cross-repo/`) carries free-form capitalized `To:`/`From:` headers. Fires as `additionalContext` (offer-shape — never deny). Central-aware: `to: claude-central-em` writing into `~/.claude` is a routing match → silent. Canonical inbox/archive writes are excluded (own-inbox guard handles `cross-repo/inbox/`; `cross-repo/archive/` holds closed actioned memos). Override: `COORDINATOR_OVERRIDE_MEMO_REDIRECT=1`. See `docs/wiki/coordinator-tripwires.md` § Routing-mismatch memo-redirect offer.

## Four coupled path declarations — keep in lockstep

The active-memo path appears in exactly **four enforced code sites** that must stay in lockstep whenever the inbox path changes:

1. **CLI write target** — `cross-repo-memo:635` (`cross-repo/inbox/`)
2. **Schema `applies_to`** — `schemas/cross-repo-memo.yaml:2` (`cross-repo/inbox/[0-9]*.md`)
3. **Own-inbox guard regex** — `validate-frontmatter-schema.js:385` (`^cross-repo/inbox/[0-9]`)
4. **Surface glob** — `workday-start-cross-repo-memo-surface.sh:34` (`cross-repo/inbox`)

A **fifth deliberately-broad negative-exclusion site** at `validate-frontmatter-schema.js:147` uses `^cross-repo/` (not `^cross-repo/inbox/`) — this must NOT be narrowed. It is the routing-mismatch check that must cover both `inbox/` and `archive/` writes so actioned archive memos are not wrongly offered a redirect.

Two human-facing doc declaration sites (the live `cross-repo/README.md` and `canonical-structure.yaml`) are non-enforced but should stay in sync. AC-7 in the test suite verifies the T3 round-trip.

**Why this matters:** When the own-inbox guard regex was too broad (`^cross-repo\/[0-9]` instead of `^cross-repo\/inbox\/[0-9]`), the guard silently stopped firing after the inbox/archive restructure because active memos had moved to `cross-repo/inbox/`. The guard appeared active but matched nothing. Updating one site without the others produces silent delivery-guard failures — exactly the worst class of failure for a security boundary.

## `kind` lockstep set — keep in lockstep (surfacing-priority boundary)

<!-- Spec backlink: docs/plans/2026-05-30-pickup-cross-repo-memo-fork.md § `kind` lockstep set -->

The `kind` field appears in exactly **four enforced sites** that must stay in lockstep whenever the enum membership changes:

1. **CLI writer** — `cross-repo-memo` `_compose_frontmatter` (emits `kind: <value>` when `--kind` is given)
2. **Schema declaration** — `schemas/cross-repo-memo.yaml` (`optional:` block, enum membership)
3. **Schema validation** — `bin/lib/schema.js` (memo cross-field rules, enum membership check)
4. **Surface parser** — `bin/workday-start-cross-repo-memo-surface.sh` (reads `kind` for priority banding: `ask`/`consult` surfaces first, `fyi` last)

**CRITICALITY DISTINCTION — this lockstep set differs fundamentally from § Four coupled path declarations — keep in lockstep above:**

- **Path declarations (§ above) are a DELIVERY-GUARD / SECURITY boundary.** A desync there silently drops memos — the guard appears active but matches nothing, and the receiver never sees inbound memos. That section explicitly calls this "the worst class of failure for a security boundary." Delivery is the contract; a desync voids the contract silently.

- **`kind` lockstep governs SURFACING PRIORITY.** A desync here degrades prioritization — an `ask` might sort where an `fyi` belongs, or vice versa — but **it does NOT drop memos**. An unlabeled or mis-banded memo still arrives in the inbox and still surfaces; the receiver can still read and action it. The failure mode is "wrong urgency signal," not "message lost."

Cross-reference: when you update the `kind` enum (add, rename, or remove a value), update all four sites above. When you update the inbox path, update the four path-declaration sites in § Four coupled path declarations — keep in lockstep. These are orthogonal lockstep sets with different failure modes; conflating them understates the delivery-guard risk.

## Shared constants — _CENTRAL_RECEIVER_IDS and _PUBLISH_TARGET_EM_IDS

Two frozensets in `cross-repo-memo` are shared between the sender-side and receiver-side resolution paths to prevent drift:

```python
_CENTRAL_RECEIVER_IDS: frozenset[str] = frozenset({"claude-central-em", "central-em", "central"})
_PUBLISH_TARGET_EM_IDS: frozenset[str] = frozenset({
    "coordinator-claude-em", "coordinator-claude",
    "deep-research-claude-em", "deep-research-claude",
})
```

`_CENTRAL_RECEIVER_IDS` is consumed by both `_resolve_receiver_path` AND `_em_id_for_root` / `_repo_key_to_em_id` (the sender-identity derivation). If the two sides had separate definitions they could drift, producing a sender identity mismatch.

`_PUBLISH_TARGET_EM_IDS` mirrors the same shape; its membership is authoritative from `setup/publish-targets.sh` (per-machine, gitignored). The set is hardcoded here because it is small, stable, and cross-machine — publish targets do not vary by developer.

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

## Cross-repo memo lifecycle — single-surface, receiver-only

> PM ruling 2026-05-23 (plan `docs/plans/2026-05-23-cross-repo-single-surface-and-canonical-scaffold.md`): one surface, no dual-write, no symmetric closure.

### The single pattern

**Sender writes once, receiver closes in-place.**

1. **Sender** runs `cross-repo-memo --to <receiver-em-id> --topic <slug> --title "<one-line>"`. CLI writes ONE dirty file at `<receiver-repo>/cross-repo/inbox/YYYY-MM-DD-<topic>.md` with `status: open`. Sender keeps no copy. CLI prints the receiver path — sender hands the PM that path for relay.

2. **Receiver** sees the dirty file in `git status` at their next session. They read it, act, flip `status: open → actioned` in-place (optionally adding `decision:` and a note), then commit it into their repo. That commit is the terminal state.

3. **No move, no second side — and no `sent/`.** The memo is created in `cross-repo/inbox/` and lives there as the primary record. Once actioned, the receiver MAY sweep it to `cross-repo/archive/` for housekeeping (co-located with the inbox — the whole channel is under `cross-repo/`). `cross-repo/archive/` is the canonical closed-memo destination; `archive/cross-repo/` (the old top-level path) is removed. **There is deliberately no `sent/` subfolder** — an EM looking to file an outbound copy finds no home for it, and the absence is the signal: the sender keeps no copy; the memo lives in the *recipient's* inbox.

**`/session-end` Step 2.65 — lifecycle sweep.** At session end, before the final commit, `/session-end` runs a cross-repo memo lifecycle sweep: it scans this repo's `cross-repo/inbox/*.md` for memos whose underlying work was completed during the session (i.e., the issue they described has been resolved), and flips their `status: open → actioned` inline with a `decision:` note. This prevents the inbox from drifting from reality — memos where the work is done should not stay `open` and surface again at the next `/workday-start` Step 1.45.

**Distill integration.** `/distill` gains a `## Cross-repo archive distillation` phase: it mines `cross-repo/archive/*.md` with `status: actioned` for evergreen knowledge (folding into wiki), then clears entries older than the configured retention threshold. `/update-docs` runs a 90-day janitorial sweep on `cross-repo/archive/` — cadence is anchored at ≥3× expected distill cadence to ensure the sweep never deletes un-mined content.

### Schema

Memo files use `plugins/coordinator/schemas/cross-repo-memo.yaml`. Key fields:

- `from:` / `to:` — author EM id and receiver EM id (e.g. `claude-central-em`, `project-rag-em`). **`from:` is derived automatically** from the repo the CLI runs in — the inverse of receiver resolution (cwd git root → `repos.<name>` → `<name>-em`; the `~/.claude` meta-repo is `claude-central-em`). It is never hardcoded and never an EM self-identify step.
- `status:` — `open | actioned`
- `decision:` — optional note on the receiver's action, added when flipping to `actioned`
- `kind:` — optional sender-declared shape (`ask | consult | fyi`); absent is interpreted as `ask`. See § `kind` enum — sender-declared memo shape below.

### CLI

```
cross-repo-memo --to <receiver-em-id> --topic <slug> --title "<one-line>" \
  [--body-file <path>]
```

**Receiver resolution is by convention, not a hand-maintained table.** A `<receiver>-em` identity maps to the machine-local registry key `repos.<receiver, dashes→underscores>` — e.g. `project-rag-ue-addon-em → repos.project_rag_ue_addon`, `dronesim-em → repos.dronesim`. **The receiver set IS your machine-local repo list:** any repo registered under `repos.<name>` (`machine-local set repos.<name> <path>`) is automatically a valid `<name>-em` receiver with no code change — so anyone installing the coordinator gets cross-repo delivery to their own registered repos for free. Run `machine-local keys | grep '^repos\.'` to see them. The only exceptions are identities whose doctrine name diverges from the repo's registry shortname (currently just `holodeck-em → repos.claude_unreal_holodeck`), held in a tiny alias map in `cross-repo-memo` that does not grow with repo count.

On machines where the receiver repo is not registered, the CLI **hard-errors** (exit 1, no file written) and lists the known receivers — a dirty memo cannot be written to a repo that isn't on this machine. There is no central-only fallback in the single-surface model; route via the PM's next session in that repo instead. (`central-only` survives only as a grandfathered `delivery_mode` value in the schema for pre-2026-05-23 memos — the CLI no longer issues it.)

On success the CLI prints the receiver path and the relay reminder:

```
Receiver-side: <abs-path>
Hand the PM this path for relay: <abs-path>
Reminder: Hand the PM the receiver path — PM-relay is still the primary channel.
```

(`--self-receipt` prints only the `Receiver-side:` line — no relay reminder, since the dispatcher is the receiver.)

### `kind` enum — sender-declared memo shape

<!-- Spec backlink: docs/plans/2026-05-30-pickup-cross-repo-memo-fork.md § Pinned interface — the `kind` enum -->

The optional `kind:` frontmatter field lets the sender declare what shape of response the memo needs. Enum membership: `ask | consult | fyi`.

| Value | Meaning | Receiver disposition |
| --- | --- | --- |
| `ask` | Sender requests the receiver *do* something (action request). Surfaces with urgency. | Adjudicate-and-own: weigh against this repo's consumers; action (→ `decision: accepted` + `decision_note`) or decline (→ `decision: declined` + `decision_note`); surface to PM only on a genuine product/tradeoff/architectural fork. |
| `consult` | Sender requests the receiver's *input or opinion* — a question, not a directive. Surfaces with urgency. | Reply-in-place: capture the response in `actioned_note` directly on the memo, then mark `status: actioned`. The sender reads the response on the same machine. No return-memo. |
| `fyi` | Informational; no action or response expected. Quiet log line at surfacing. | Acknowledge only: `status: actioned` + `actioned_note: "noted — informational"`. No `decision` field. |

**`ack` is NOT a `kind` — it is receipt-state, not a sender-declared value.** An acknowledgement is the receiver flipping `status: open → actioned` (with `decision:` + note) in-place. `ack` is never a valid `kind:` value and never a return-memo. The same rule as "don't send an ack-of-ack when the inbound was a confirmation" (§ Memo content is hypothesis — verify before acting, item 8) applies here: the `status` flip IS the receipt; authoring a separate ack memo is ceremony with no value.

**Absent `kind:` defaults to `ask` at the READER.** The CLI does not stamp a default — absence stays meaningful. Every reader (surfacing helper, `/pickup` branch) applies `ask` when the field is absent. This preserves back-compat: no pre-2026-05-30 memo is silently downgraded to a quiet `fyi` by the absence of a field it never had.

### `/workday-start` Step 1.45 surfacing (receiver-inbound)

A step inserted between Step 1.4 (cross-reference completed archive) and Step 1.55 (Recent Roadmap Orientation) queries **this repo's** `cross-repo/inbox/*.md`, parses frontmatter, filters to `status: open`, and surfaces:

```
Cross-repo memos awaiting your action:
- 2026-05-23 from claude-central-em: gate-check failures — open (1 day)
```

Staleness flag: `open` >7 days appends ` [STALE]`.

Cap: ≤8 entries; `(N more — see cross-repo/inbox/ for full list)` truncation beyond that.

`actioned` memos drop off the surface. The helper script is `workday-start-cross-repo-memo-surface.sh`.

### Partial-ack memo unblocks the sender — send early, even when the main deliverable is in flight

A cross-repo memo's acknowledgement function is independent of the main deliverable's completion. When you have confirmed that you understand and accept an inbound request — even if implementation is still running — send a partial-ack memo immediately. The sender may be blocked waiting for any signal; a "received and in progress" ack is sufficient to unblock them. Do not wait until the work is fully closed to reply.

*Source: rag-ue-addon `tasks/lessons.md` (central-promoted 2026-05-29).*

### Memo-lifecycle adjudication is EM work

When an inbound memo describes a situation, proposes an action, or asks a question — read the memo body and judge the right response yourself. Do not surface the memo contents to the PM as "what should I do?" The PM's job is product authority; memo adjudication (what the memo says, what the right EM response is, whether the action is already done, whether the memo is superseded) is EM work. Escalate to PM only if the memo implicates a product decision — not for "I have a memo, what do I do?" (See also § Memo content is hypothesis — verify before acting.)

*Source: holodeck `tasks/lessons.md` (central-promoted 2026-05-29).*

### Picking up a memo — the adjudicate-and-own gate

<!-- Spec backlink: docs/plans/2026-05-30-pickup-cross-repo-memo-fork.md § C5 -->

When `/pickup` routes to the memo branch, two existing sections in this wiki constitute the contract it invokes:

- **§ Memo-lifecycle adjudication is EM work** (immediately above) — the EM reads and judges, never routes "what should I do?" to the PM.
- **§ Memo content is hypothesis — verify before acting** — premises (fix-locus, tree-state, architectural framing) are hypothesis until checked against current disk state.

These are not new rules authored for the pickup procedure; they are existing doctrine now made reachable at the moment the EM opens a memo baton. The `/pickup` memo branch is the procedure that wires them into the pickup-time moment; the doctrine lives here.

**The calibrated stance: adjudicate-and-own.**

A memo-ask is a PEER HYPOTHESIS from the sender's EM — a suggestion from a fellow EM at another repo, not a work order. The receiving EM adjudicates and OWNS the disposition for this repo's customers and consumers:

- **Tradeoff-free ask the EM endorses** → action it; mark `status: actioned` + `decision: accepted` + `decision_note: <what was done>`.
- **Disagree, or wrong for this repo's consumers** → decline; mark `status: actioned` + `decision: declined` + `decision_note: <rationale>`.
- **Genuine product/tradeoff/architectural fork** → surface to PM for direction, then act on the answer.

This is the **"reviewer findings: apply, don't ratify"** framing applied to memo-asks. It is NOT "always bounce to the PM" — § Memo-lifecycle adjudication is EM work explicitly forbids "what should I do?" escalation. Escalate only when the memo implicates a product decision, not as a default.

**`/session-start` surfaces, `/pickup` acts.** This is an architectural boundary, not a gap: `/session-start` (via `workday-start-cross-repo-memo-surface.sh`) provides awareness; lifecycle mutation and adjudication live solely in the `/pickup` memo branch. Teaching both entry points the same fork creates divergence risk.

### Don't re-nag the PM about already-sent memos

Once the receiver path has been handed to the PM at send time, the sender's job is done. Do not re-list memos (or doctrine-seeding direct writes) as "pending PM-relay" or "pending your action" in later session reports, `/handoff` bodies, or session openings. The receiving repo's `/workday-start` Step 1.45 surfacing is the canonical channel; sender-side action-state knowledge goes stale silently. Operative rule lives in `skills/session-end/SKILL.md` § Step 2.66.

### Grandfather cutoff

**Pre-2026-05-22 memos are grandfathered.** Step 1.45 skips memos with `created: < 2026-05-22` by design. If a pre-cutoff memo has unfinished business, re-issue via `cross-repo-memo` with `supersedes: <old-path>`.

### Worked example

Memo from `claude-central-em` to `project-rag-em`.

**Step 1 — Sender writes (2026-05-23).**

```sh
cross-repo-memo --to project-rag-em --topic gate-check-fix \
  --title "Gate-check failures in check-plugin-drift.sh — recommended fix"
```

CLI writes `X:/project-rag/cross-repo/inbox/2026-05-23-gate-check-fix.md` (dirty, untracked) with:
```yaml
---
title: "Gate-check failures in check-plugin-drift.sh — recommended fix"
from: claude-central-em
to: project-rag-em
created: 2026-05-23
status: open
---
```

CLI prints:
```
Receiver-side: X:/project-rag/cross-repo/inbox/2026-05-23-gate-check-fix.md
Hand the PM this path for relay: X:/project-rag/cross-repo/inbox/2026-05-23-gate-check-fix.md
Reminder: Hand the PM the receiver path — PM-relay is still the primary channel.
```

Sender notes the send in their session-end notes. No sender-side file is created.

**Step 2 — project-rag-EM sees the dirty file** at next session-start (`git status` shows `?? cross-repo/inbox/2026-05-23-gate-check-fix.md`), reads it, implements the fix, then flips status in-place:
```yaml
status: actioned
decision: "Fixed gate-check exit-code handling in check-plugin-drift.sh"
```
Commits: `memo: actioned 2026-05-23-gate-check-fix — accepted and implemented`

Done. Memo lives in `project-rag/cross-repo/inbox/` as the active record; once actioned it may be swept to `project-rag/cross-repo/archive/`. No further action required on either side.

## Memo consumer-count is the sender's floor, not the full surface

**A cross-repo memo's enumerated consumer count is the sender's view from outside — treat it as a floor and scout the full surface before planning.**
**Why:** A 2026-05-28 cutover memo named 3 `engine_root` consumers; a read-only scout found ~13 touchpoints (a 4th reader, health probes, a shared resolver seam, 6 inverting/source-asserting tests). The sender cannot see indirect resolvers, test inversions, or doctrine surfaces.
**How to apply:** on any inbound cross-repo memo enumerating consumers, dispatch a scout AND make surface-completeness an executable AC (e.g. a grep gate asserting no remaining call sites reference the old surface). Both are required, not either-or — in the source incident the dedicated scout STILL missed two readers; the post-implementation grep-gate AC caught them. The scout is necessary but not sufficient. A missed consumer breaks silently on fresh installs when the cutover has no transitional window.

*Source: holodeck `tasks/lessons.md` (holodeck-L41, central-promoted 2026-05-28).*

## Cross-repo bit-owner: defer with a verification gate

**When a user-visible behavior default hinges on a fact only another repo authoritatively knows, don't guess — defer with a verification gate and spend one cross-repo memo to buy the bit.**
**Why:** A spawn-gate decision (warn-only vs. hard-refuse) depended on whether the sibling's Job-Object cap covered the caller's process — a fact only the sibling's source could confirm. Shipping warn-only plus a one-bit cross-repo query produced a justified hard-refuse once the answer returned, rather than an assumption that might have been wrong in either direction.
**How to apply:** PM ratifies the conditional upfront ("if the answer is X, ship Y; otherwise Z"). EM fires on bit-return. This avoids both over-building (assuming the sibling covers you) and under-building (assuming it doesn't).

*Source: holodeck `tasks/lessons.md` (holodeck-L203, central-promoted 2026-05-28).*

## Memo content is hypothesis — verify before acting, replying, or closing

> Consolidated 2026-05-24 from six recurring lessons across project-rag, holodeck, and the addon. The mechanics above (CLI, lifecycle, surfacing) cover *how* a memo moves; this section covers *what not to trust about its framing*. Root cause is one: a memo is written from the sender's vantage at the moment they hit the symptom — its diagnosis, proposed fix-locus, recommended action, and `status:` field are all hypothesis until checked against current disk state.

**On receipt — before acting on an inbound memo:**

1. **Verify the cited locus exists on the alleged-responsible side.** Incoming memos arrive with proposed-fix framing; the proposed locus can be wrong even when the symptom is real. Grep the cited import path / symbol / file *in this repo* first. If it doesn't exist here, the fix-locus is probably the sibling where the asymmetric implementation lives (parallel `.sh`/`.ps1`, addon-vs-host, producer/consumer). The seven-dimension fix-locus discrimination check (CLAUDE.md § Pre-Dispatch Verification) applies to incoming memos as much as to plan-time substrate. *(Canonical: 2026-05-23 `MIN_SUPPORTED_SCHEMA` memo pointed at the host; the import never existed there — real fix was the sibling addon's download script.)*

2. **Check it hasn't already been actioned by a concurrent EM before drafting a reply.** Before authoring any cross-repo reply or relay: (a) `ls` the receiver's `cross-repo/` for an in-reply-to match, (b) `git log <our-branch> --since=<inbound-memo timestamp>` for concurrent work that changed the premise, (c) *then* draft. The `~/.claude/tasks/memos/` staging dir is session-scratch — not authoritative; the sibling's `cross-repo/` is.

3. **A costly ask on our side isn't proof we must pay it.** When a brief proposes costly work on us and cheap dead-code removal on them, the cross-repo coordination question precedes the plan-drafting question: send a one-line reply asking whether the cheaper fix on their side is feasible before drafting a migration plan. (Folds with "we don't argue against consumer asks" — but adds the inverse: check whether the asker can self-serve cheaply before paying the cost ourselves.)

**On disposition — when reporting or closing:**

4. **`status:` is a lagging indicator; grep code-evidence.** The receiver flips `status:` at *their* close-out cadence, but on-disk work can land via parallel workstreams (integrator passes, session-end fix-folds, sibling EMs) before the field flips. When reporting cross-repo disposition, grep code-evidence against target files (specific symbols, function shapes, comment fragments) — the `status:` field is the audit signal at the slowest cadence; code state is ground truth at the fastest.

**On sending — the send/don't-send distinction:**

5. **Sending the outbound completion memo IS part of "fix everything."** When a session closes a thread another team is gated on, the actionable list always includes (a) action their inbound, (b) send the outbound completion notification via `cross-repo-memo`, (c) hand the PM the receiver path for relay. The code landing is "code complete," not "thread closed."

6. **But don't send an ack-of-ack when the inbound was a confirmation, not a request.**

7. **Cross-repo plan-body state snapshots stale within hours — recheck before acting on a sibling plan's claimed state.** When a sibling plan at `../<peer-repo>/docs/plans/` claims a status (chunk progress, file landed, implementation complete), that claim is a snapshot at write time. Concurrent EM activity on the sibling can invalidate it within hours. Distinct from in-repo plan-vs-disk drift: this governs cross-repo plan-body state specifically. Mitigation: re-read peer plan frontmatter + recent `git log` before basing a decision on its claimed state.

8. **A cross-repo reply can be superseded by a sibling memo from the same correspondent — grep the archive before acting on its recommendation.** Two memos from the same sender can cross in flight; the later-arriving one may carry framing that predates the formal decision in an earlier memo. Before actioning a memo's prescription, grep `../<peer>/cross-repo/archive/` for same-topic memos from the same sender. The recommendation in-hand may be one round older than the formal decision. The right adoption is the one that combines both signals, not the most-recently-received one. SEND outbound when you've *unblocked* a peer (their inbound was a request gated on you). DON'T send when their inbound was a *confirmation* — the receiver-side `status` flip + git history is the audit trail; ack-of-ack is ceremony. Tell: you're drafting a memo whose body reads "Confirmed (i)/(ii)/(iii)… same as your memo" with no new information. (See also § Don't re-nag the PM about already-sent memos.)

## Memo framing is hypothesis at the architectural altitude too — leak/exclude/ownership claims

> Consolidated 2026-05-27 from a cluster of incoming-memo failures where the *symptom* was real but the memo's **architectural framing** was wrong. The "Memo content is hypothesis" section above governs fix-*locus*; this section governs fix-*shape* — the deeper trap where actioning the memo as written ships a regression, not just a misplaced patch.

The hypothesis discipline does not stop at "is the cited file in this repo?" It extends to the architectural premise the memo bakes in. Three recurring shapes, each verified against disk before converging:

1. **"X is leaking into Y — filter it out" can be a route-correctly problem, not an exclude problem.** Before scoping an exclusion filter, verify whether Y is *intentionally multi-state*. A minimal exclusion can be a user-visible regression. *(Canonical: 2026-05-26 — an addon memo + draft plan framed Python/TS classes in `graph.db.classes` as a leak; the table is deliberately multi-language, so a C++-only allowlist would have evicted Python/TS from L2 on polyglot projects — worse than the "leak." The right fix routed each input to its correct band/kind; a blind filter was an eviction regression.)* When a memo proposes an exclusion against a surface that might be intentionally multi-state, route the architectural-premise call to a **DoE-altitude reviewer (the Director of Engineering)** before converging — this is exactly the cross-team-architecture call the Director of Engineering carries authority for.

2. **"You own X now, just patch it" — confirm where the implementation lives (import site, not registration site) AND grep every writer of the contaminated target.** A registry/hookspec row migrating ownership does not move the *runner*; the import site is ground truth, not the registration row. And a leak in one consumer of a shared query usually has sibling writers — patching only the named consumer is a confirmed half-fix. *(Canonical: 2026-05-26 — a peer memo said "`extract_cpp` is addon-owned now, rewrite the isolation test." Both premises were wrong: the runner still lived in host core (only the registry row had migrated), and the leak had an identical sibling site — `lite_to_graph_classes`, same un-filtered `project_lite` query, no file-ext gate. Repro confirmed both leaked.)* This is the fix-locus discrimination rule (above) plus a sibling-writer sweep — grep every writer of the contaminated path, not just the one the memo names.

3. **A reviewer/memo "missing field" finding inverts once you check field OWNERSHIP — grep the consumer before adding a producer-side emit.** Absence of a *consumer-owned* field at the producer is often correct, not a gap; the producer emitting it is the redundant anti-pattern. *(Canonical: 2026-05-27 — a code-review flagged descriptor chunkers as "missing `chunk_content_hash`"; the host computes it at index time (`indexer/embed.py` overwrites any producer value with its own xxh3), so the omission was correct and the chunkers *emitting* a blake2b value were the redundancy.)* Before treating an absent field across a cross-repo seam as a defect, grep who *computes* and who *consumes* it. The seam direction inverts the finding.

The unifying rule: **a cross-repo finding names a symptom from one vantage; its proposed fix-shape, fix-locus, and ownership attribution are all hypotheses.** Verify the producer's live model, the implementation's real home, the surface's intended multiplicity, and the field's owning side on disk before building the consumer half or shipping an exclusion. → CLAUDE.md § Pre-Dispatch Verification (7-dim fix-locus discrimination); the verification is identical, the entry point is an inbound memo or review finding rather than your own plan.

## Verify cross-repo coordination as substrate, not ceremony — and verify the other team's disk before authoring

> Consolidated 2026-05-27 from the cross-EM-coordination cluster (3rd+ instance of each shape).

- **PM-relay beats copy-first-discover-disagreement.** The recurring anti-pattern: copy a sibling's file/contract into your repo, build against it, then discover at integration that the two diverged. Cheaper: send a one-line `cross-repo-memo` asking the bound question (is the cheaper fix on your side feasible? is this the contract shape?) and hand the PM the path — *before* drafting a migration plan against an assumed shape. Coordination is a question to ask, not a copy to make.
- **Cross-repo coordination dependencies are verifiable as substrate, not as ceremony.** When a plan asserts "the sister repo does X" or "the other team will provide Y," grep the sister repo at substrate-verification time instead of defaulting to async cross-EM messaging. On a single machine with both repos on disk, the sibling's code is readable now — `grep`/`Read` the actual seam beats waiting on a memo round-trip. Reserve the memo for genuine asks (a contract change you need them to make), not for facts you can read.
- **Verify "the other team missed it" on disk before authoring cross-repo work.** A premise that a sibling repo has a gap, bug, or missing field is hypothesis — confirm it against the sibling's HEAD (`git log --oneline -- <path>` + read) before authoring a memo or a fix that assumes the gap. The gap may already be closed, or may live in a different layer than the framing claims.

**PM sign-off on direction is not a license to skip cross-repo coordination.** When a phase changes a contract other repos consume (envelope schema, override-flag convention, schema-vendoring covenant), write a proposal memo to `cross-repo/archive/` and circulate to consuming teams BEFORE shipping — even when the EM recommendation is sound and the PM has approved. Circulating first surfaces factual corrections and pre-existing alternatives that unilateral execution misses. Use an in-place `## Response — <repo>` reply block so proposal and ratification co-locate in one file.

## Operational safety with sibling-repo processes — don't kill the daemon you depend on

Don't stop/restart/kill a sibling repo's running process (MCP daemon, indexer, watcher) without first verifying the relaunch path resolves end-to-end — this is process-management discipline, documented with the other runtime-readiness rules. → [`verification-before-completion.md`](./verification-before-completion.md) § Runtime Readiness vs. Green Tests.

## Peer-doctor pointer resolution — four-rung discovery cascade

→ [`cross-doctor-routing.md`](./cross-doctor-routing.md) owns the canonical four-rung cascade (machine-local registry → sibling-relative → grep → GitHub fallback, stop-at-first-hit, skip-not-flag when the peer is absent). A cross-repo memo that needs to *locate* its peer at runtime resolves the path via that cascade.

## Doctrine seeding vs. code/install-surface change — two different cross-repo altitudes

> Added 2026-05-21 under PM ruling; updated 2026-05-23 to reflect single-surface model.

Two altitudes:

### Doctrine seeding (DoE altitude)

CLAUDE.md additions, `docs/wiki/` entries, agent-prompt amendments, skill/hook authorial changes — anything that shapes *how* a sibling repo's EM works rather than *what* code runs.

- **Legitimate as direct cross-repo write** when authored from DoE / HoP altitude (central-EM acting on PM direction). The DoE has standing to seed alignment across repos.
- **Provenance required.** Commit message names the doctrine-seeding context: `"DoE doctrine-seeding under PM direction <date>; sibling EM may amend on receipt"`.
- **Sibling EM may amend on receipt.** Doctrine seeded into another repo isn't a fait-accompli; the receiving EM has the standing to refine, contextualize, or push back.

### Code / install-surface change (EM altitude)

Source edits, machine-local entries, install scripts, sentinel files, registry edits, hook execution semantics — anything that changes *what runs* on a sibling repo's install surface.

- **Routes via `cross-repo-memo` + PM-relay.** Run the CLI, hand the PM the path. **Writing the memo is half the work; handing the PM the path is the other half.** A memo written without PM-relay is a document dropped in a hole — the affected EM has no signal to look at it. The sibling EM, once briefed, lands the change with their own implementation context.
- **PM-authorized direct writes are the documented exception**, not the default. Record the authorization in the commit message when invoked.
- **Why the altitudes differ.** Doctrine is alignment work the DoE owns; code is implementation work the sibling EM owns. Conflating them produces churn in both directions — DoE doctrine that never lands because it routed through a slow memo loop, OR sibling-repo code edits that lose the implementing EM's context.

### When lifting a cross-repo primitive: separate what WE call from what OTHERS should do

**Ship what makes sense for OUR install surface; teach how OTHERS should handle theirs in a wiki — never code both sides from our repo.**

When planning a primitive that touches multiple consumer classes (e.g., a sentinel-writer for install verification), the two questions are distinct:

- **"What do WE call from OUR surface?"** — this ships as code in our repo, wired to our install path.
- **"What would we recommend OTHER consumers do?"** — this ships as a `docs/wiki/` section ("Writer location" / "Guidance for downstream consumers") plus a recommend-not-direct line in any cross-repo memo we send.

Conflating them causes the EM to wire another repo's install ceremony from our surface, which (a) muddies consumer-class boundaries, (b) locks reader-side interpretation prematurely, and (c) produces the tell: *a chunk that closes one consumer's gap by writing into a different consumer's path.*

**How to apply:** at plan-write, enumerate the consumer classes explicitly. For each class that is not OUR install surface, write a wiki section and a memo recommendation — do NOT code their ceremony into our executor. The receiving EM lands it with their own implementation context.

*Source: 2026-05-28 install-divergence lift; PM crystallized rule when EM was about to wire holodeck's install ceremony from coordinator publish surface.*

### the Director of Engineering's cross-repo stance — lean, don't diktat

The Director of Engineering (DoE) carries cross-team / cross-repo authority that EM-altitude reviewers (the Staff Engineer et al.) do not. **In meatspace, nobody likes a DoE who parades around making calls for another team.** the Director of Engineering's posture in this regime:

- **Doctrine altitude: author and seed directly.** the Director of Engineering can write doctrine that lands in sibling repos (CLAUDE.md additions, wiki entries, agent prompts) under PM direction. This is alignment authority.
- **Code/install-surface altitude: lean, name the direction, insist on coordination.** the Director of Engineering can say "the producer should expose X" or "the consumer is making an assumption that won't hold" — as a recommendation, with reasoning. Findings that implicate a sibling repo's code or install surface MUST surface as `cross_team_directive` requesting EM-coordination (memo via `cross-repo-memo` CLI **and PM-relay** — the Director of Engineering writes the memo, the EM dispatching the Director of Engineering hands the PM the path), not as a directive landed on the peer's surface.
- **The catalyst, not the implementer (for code).** Code changes that follow from the Director of Engineering's recommendations route through the standard memo channel; the sibling EM lands the change in their own repo with their own context.
- This narrows the previous the Director of Engineering framing ("Your finding stands as a directive, not a polite suggestion") to the *code-altitude* axis. Doctrine-altitude authority is preserved and made explicit.

## Git-tracked location — never gitignored

<!-- Spec backlink: docs/plans/2026-05-23-cross-repo-inbox-archive-restructure.md § D5 -->
<!-- Negative-spec: cross-repo/inbox/ must NOT appear in .gitignore. A broad deny-all ignore that swallows cross-repo/ is the concrete harm the global CLAUDE.md rule "deny-all .gitignore patterns are forbidden" is written to prevent. -->

**The delivery contract is "sender drops a dirty file → receiver sees it in `git status`."** That signal only works if the receiver's `cross-repo/inbox/` is a real, git-tracked, non-ignored surface. Two silent-failure modes if it isn't:

1. **Gitignored location.** If the receiver repo's `.gitignore` matches `cross-repo/`, `*.md` within it, or the inbox path, the dropped memo file never appears in `git status`. The sender believes delivery succeeded; the receiver never sees the memo. Silent loss — the hardest failure to debug because no error is emitted by either side.

2. **Untracked/absent directory.** If `cross-repo/inbox/` does not exist as a committed surface, a delivered memo lands in a path that may not persist across clean checkouts, and `git status` output is less predictable for agents scanning it. A committed `README.md` in each of `cross-repo/inbox/` and `cross-repo/archive/` makes the locations stable git-tracked surfaces and provides reader orientation at no extra cost.

**Doctrine:** every EM repo's `cross-repo/inbox/` and `cross-repo/archive/` must be git-tracked via committed READMEs and MUST NOT be gitignored. This is a direct consequence of the dirty-file delivery model — the location is only useful if it is visible.

**Cross-reference — global CLAUDE.md § deny-all `.gitignore` patterns are forbidden.** A `.gitignore` pattern broad enough to swallow `cross-repo/` is exactly the kind of deny-all rule the global doctrine prohibits. The prohibition names a general principle; this section names the concrete harm that drives it in the cross-repo memo context.

**Enforcement at send time.** The CLI (`cross-repo-memo`) runs `git check-ignore` on the target path in the receiver repo before writing anything. If the check confirms the path is gitignored, the CLI hard-errors loudly — "refusing to deliver to `<path>`: it is gitignored in the receiver repo and would be invisible in `git status`." The memo is NOT written. The error surfaces at send time, not silently after the receiver fails to see it. A receiver that is not a git repo at all (exit 128 from `git check-ignore`) is treated as unblocked — a non-git receiver cannot gitignore anything.

**Canonical structure doctor.** The scaffold and doctor tooling (`scaffold-canonical-structure.sh`, `canonical-structure.yaml`) create the inbox and archive directories with their READMEs on first run, ensuring newly onboarded repos start with a git-tracked surface.

## Publish-target repos are not receivers

<!-- Spec backlink: docs/plans/2026-05-23-cross-repo-inbox-archive-restructure.md § D6 -->
<!-- Negative-spec: publish-target repos (coordinator-claude, deep-research-claude) do NOT have
     a live cross-repo/inbox/ — they are outward publish.sh destinations, not EM working trees.
     The canonical-structure manifest's cross-repo/inbox/ entry applies to EM working repos
     only; publish targets do not run the scaffold. -->

Publish-target repos are outward `publish.sh` destinations — OSS distribution mirrors that receive a copy of plugin source on each publish run. They are **not** EM working trees. An EM session does not run inside a publish target repo; no EM reads `git status` there; and crucially, the next `publish.sh` run will overwrite any file dropped into a publish target's working tree. A memo delivered to a publish target is therefore doubly invisible: no EM sees the dirty file, and the publish run clobbers it before anyone could.

The operator's source of truth for which repos are publish targets is `setup/publish-targets.sh` (per-machine, gitignored). Current publish targets include `coordinator-claude` and `deep-research-claude`.

**The CLI rejects publish-target identities at parse time**, before `_resolve_receiver_path` runs. Attempting `cross-repo-memo --to coordinator-claude-em` exits 1 with a clear message redirecting to `claude-central-em` and listing the known EM receivers on this machine. The both the `-em` form and bare shortname (`coordinator-claude`, `deep-research-claude`) are in the rejection set.

If you genuinely need to drop a file into a publish target (e.g. testing publish mechanics, fixture authoring), set `COORDINATOR_OVERRIDE_PUBLISH_TARGET_RECEIVER=1`. This is rare; the normal path is to send the memo to `claude-central-em` (the coordinator meta-repo, which IS an EM working tree) or to the appropriate sibling repo.

## Migration — migrate-cross-repo-layout.sh

When a repo was set up under an earlier layout (flat `cross-repo/*.md`, or top-level `archive/cross-repo/`), run `migrate-cross-repo-layout.sh` once to bring it to the current `inbox/` + `archive/` structure:

```sh
bash migrate-cross-repo-layout.sh
```

**Idempotency basis:** the script globs `cross-repo/*.md` (non-recursive). After migration, the only file at that path is `cross-repo/README.md`, which is excluded. A second run is therefore a no-op — zero moves, zero errors.

**Collision handling:** if a same-named file already exists in `inbox/`, `git mv` fails loud. The script does NOT overwrite — it aborts on collision. Resolve conflicts manually before re-running.

**Untracked-file fallback:** the script detects files committed by concurrent EMs that appear untracked locally and falls back to `mv + git add` rather than `git mv` for those files. This handles the real-world case where 8 of 26 migration files were in this state.

Sibling repos (holodeck, project-rag, project-rag-ue-addon) each run the migration locally after `publish.sh` propagates the script — migration does not run automatically during publish.

## Shared-Byte-Equal Fixtures as Cross-Repo Contract Oracles

When two repos implement the same contract (e.g., parallel helper functions that must produce identical outputs), a shared byte-equal fixture is the cheapest round-trip oracle. Matching specs alone are insufficient — two independent implementations of the same contract drift unless the contract is encoded as an executable artifact that both repos run against. The fixture is the contract; spec prose is documentation of it. Place the fixture in the repo that owns the contract's definition, and have the peer repo consume it via the cross-repo memo channel or a shared test-data git submodule. Any divergence in fixture output surfaces as a test failure rather than as silent protocol drift discovered during integration. (Source: 2026-05-24 claude-unreal-holodeck)

## Receiver-Side Executable Oracle Before Implementing a Prescribed Fix

A cross-repo memo's fix-list is necessary but may not be sufficient. The memo is written from the sender's vantage — the sender's implementation context, the sender's observed symptom, the sender's proposed locus. Before implementing a prescribed fix, run the receiver's own executable oracle (test suite, smoke test, or type-checker) against the current code to establish a baseline. The oracle surface may catch additional failures the memo's fix-list didn't anticipate, or it may confirm that the prescribed fix is insufficient for the receiver's substrate. Implement the fix, then run the oracle again; both the pre-fix and post-fix oracle results are evidence. A prescribed fix verified only by the sender's mental model of the receiver is at best 50% verified. (Source: 2026-05-24 claude-unreal-holodeck)

## Two-Clause Hookspec Proposal Test

Before proposing a cross-repo hookspec, apply the two-clause test: (a) does the HOST's code branch on the field at runtime — i.e., does the host actually read the field and make a behavioral decision based on its value? AND (b) is the resource produced or consumed across the cross-process boundary — i.e., does the field exist in a message exchanged between the two repos, not just within one repo's internal call graph? Both clauses must hold. A field that the host reads internally but never places into the cross-repo envelope fails clause (b). A field in the envelope that the host never reads fails clause (a). Proposing a hookspec that fails either clause adds schema surface without enabling coordination — the maintenance cost of the field is real, the behavioral benefit is zero. (Source: 2026-05-24 project-rag-ue-addon)

## Inbox Memo Concurrency — `git fetch` Before Acting

Cross-repo inbox memos have no claim mechanism — two concurrent sessions can see the same `status: open` memo and begin implementing the same fix independently, shipping byte-identical duplicate work. Before starting any implementation driven by an inbox memo, run `git fetch` and scan `origin/<branch>` for commits that address the memo's topic (grep commit subjects for the memo's `--topic` slug or the cited symbol). If a peer commit has already landed the fix, flip the memo `status: open → actioned` and stop — do not duplicate the work. The `/workday-start` Step 1.45 surfacing reduces this risk (stale memos are flagged), but does not eliminate it when two sessions start within the same window. (Source: 2026-05-24 project-rag-ue-addon)

## Stale-doctrine watch — the global-CLAUDE.md cross-repo summary predates the CLI

> Consolidated 2026-05-27 from two recurring lessons (project-rag, self) flagging the same drift.

The canonical mechanism is the one this wiki documents: **`cross-repo-memo --to <receiver-em-id>` writes ONE dirty file into the RECEIVER repo's `cross-repo/inbox/`, the sender keeps no copy, and the receiver closes in-place.** Any prose still describing the *old* shape — a sender-side `archive/cross-repo/` copy, a dual-write, or a generic "PM-relay a hand-written memo" without the CLI — is stale and predates the 2026-05-23 single-surface ruling. When you encounter that older summary (notably in entry-point docs whose body lags this wiki), do not action it as written: it steers EMs toward the dropped-in-a-hole pattern (a memo written but parked in the sender's own tree, where the recipient never sees it). This wiki is the authority; treat divergent summaries as the copy to fix, not the contract to follow.

## Hookspec aggregation contracts — read the docstring (list vs singleton) before the plan body

Before authoring a plan against a cross-repo hookspec, read the hookspec's own docstring to determine its **aggregation contract**: does the host collect a *list* of all hookimpl return values (`firstresult=False`, the pluggy default), or take the *first non-None* result (`firstresult=True`)? The two shapes produce opposite consumer code — a list-aggregating spec means every registered addon contributes and the host iterates; a singleton spec means exactly one addon "wins" and ordering/precedence matters. Guessing wrong inverts the plan's data-flow assumptions. The docstring (and the `@hookspec(firstresult=...)` decorator) is ground truth; the field name alone does not disclose the contract. Pairs with the Two-Clause Hookspec Proposal Test above — that test gates *whether* to add a hookspec; this gates *how* to consume one that exists.

## Confirm Deployment-Topology Premises with the PM at /shape Time — Before Running the Full Pipeline

**A peer-EM's recommendation can rest on a deployment-topology premise that the PM knows is false — confirm the load-bearing premise with the PM at shaping time, before running the plan→review→cross-repo-contract pipeline.**

*2026-05-27, project-rag-ue-addon (engine-vector-store-consolidation).* The project-rag EM recommended consolidating the per-UE-version chroma store to kill an N×3GiB memory multiplier. The EM ran the full pipeline (plan, the Data Science Reviewer+the Staff Engineer review, a completed bilateral cross-repo contract, Chunks 1/2/3) before surfacing the one premise it all hinged on — "does a single daemon ever serve >1 UE version at once?" — to the PM, who answered "no." That single fact zeroed consolidation's only benefit while leaving its query-latency and cross-repo-maintenance cost, forcing a late reversal. The spike and the fact killed it before publish (gates worked), but a one-sentence premise-check would have saved the cycle.

**Rule:** when a peer recommendation's value depends on a deployment/usage-topology assumption (concurrency, multi-tenancy, version-span, session-affinity), confirm that assumption with the PM during `/shape` — it is PM-altitude knowledge, not something to discover after the contract is signed. Sibling to cross-repo-contract-is-hypothesis and the Receiver-Side Executable Oracle rule above.

## Read your inbox before committing — standdown memos invalidate in-flight work

**Before committing mid-session, scan `cross-repo/inbox/` for memos whose title matches your active workstream.** A standdown or contract-change memo can arrive while you are executing — and can invalidate work you are about to commit.

*Empirical (2026-05-27):* A full consolidation was executed, reviewed, and integrated while a standdown memo sat unread in the inbox. A concurrent session actioned it and reverted both commits. The read-then-commit discipline costs one `ls` and prevents a two-commit revert.

The `/workday-start` Step 1.45 surface catches memos at session open; this rule covers memos that arrive *during* a session.

**Inbox memos that re-engage a stood-down workstream need workstream-history verification BEFORE substrate engagement.** When an inbound memo re-opens contract points from a workstream the PM previously stood down, verify workstream status before responding. Run `git log --oneline --since=<plan-date> --grep="<workstream-keyword>"` and check `docs/plans/<slug>.md` frontmatter `status:` for `abandoned` / `superseded` / `stood-down`. The inbox memo's subject line is not authoritative on workstream state — the disk is. A re-opened bilateral contract that contradicts a PM-ratified stand-down is a workstream-status question that surfaces to the PM, not a substrate engagement.

## A memo's claim about the RECEIVER's own tree state is hypothesis — verify before acting

A cross-repo memo may assert a fact about the receiving repo's current state: "your tree is clean," "the consolidation branch is already reverted," "the daemon is shut down." **These claims are hypothesis, not ground truth** — the sender wrote them from their own vantage at send time, not from a live read of the receiver's working tree.

Before acting on any standdown, "safe to proceed," or "already done" framing in an inbound memo: run `git log --oneline -- <cited-paths>` and/or `git status` to verify HEAD state in your own repo. The memo is a signal to investigate, not a contract.

Extends the existing **Memo content is hypothesis** section above (which governs fix-locus); this row governs tree-state claims.

## Defer-with-verification-gate — buy the bit before building

When a user-visible default, architectural choice, or plan shape hinges on a cross-repo fact you cannot read locally, **send one memo to buy the bit rather than guessing across the repo boundary.** The memo asks the bounded question; the PM ratifies the conditional; the EM fires on the answer.

Pattern: *"Plan A if `<fact>` is true on your side; Plan B otherwise. Reply via memo — I'll proceed on receipt."* This is cheaper than building a migration plan against an assumed shape and discovering the premise is wrong at integration. (Pairs with the § Defer-with-verification-gate rule above — "PM-relay beats copy-first-discover-disagreement.")

## Inbox Memo Liveness — Archive Sweep Before Reply

**An `open` cross-repo inbox memo is hypothesis about contract state, not ground truth — same-topic archive sweep is required before treating it as live.**

`status: open` is lifecycle metadata that decays. A standdown that arrives as a separate memo does NOT retroactively flip the predecessor's status; `open` can persist against a dead workstream. Before dispatching a reply or ACK on any `status: open` inbox memo, sweep `cross-repo/archive/`, `archive/completed/`, and `docs/plans/` for same-topic terminal artifacts (standdown / abandoned / closed / completed / retracted). One grep on the topic slug across those three surfaces is the gate. The `coordinator:plan` Branch C conflict scan catches this — but it fires after the reply has already shipped, which is too late for cross-repo round-trips. Correct gate is at the memo-reply seam: precondition for "treat this memo as live" is "no same-topic terminal artifact in the archive sweep."

## Stand-Down Memos — Verify Receiver Tree Before Acting

**A cross-repo memo's claim about the RECEIVER's own tree state ("your tree is clean," "nothing has been committed") is hypothesis, not ground truth — a concurrent session may have committed exactly what the memo says hasn't happened.**

The memo author writes from their vantage at send time; your shared branch advances independently. A "clean stand-down / nothing to revert" framing is the highest-risk case because it invites a no-op when a `git revert` of committed work is actually required. Before acting on any standdown or "safe to proceed" framing in an inbound memo: run `git log --grep`/`git status` at HEAD to verify your own repo's current state.

Extends the **Memo content is hypothesis** section (which governs fix-locus) to tree-state claims. Pairs with § A memo's claim about the RECEIVER's own tree state above.

## Pre-Commit Inbox Check — Grep cross-repo/inbox/ Before Committing Cross-Repo-Coupled Work

**Read `cross-repo/inbox/` memos whose title matches the active workstream BEFORE committing — a standdown or contract-change memo can invalidate in-flight work mid-session.**

On a shared concurrent-EM branch with cross-repo coupling, an inbox memo is a live contract-change signal that outranks the plan — the premise can collapse mid-execution. A visible unread inbox file is not "another session's business"; it is a signal to open and read. Before committing a cross-repo-coupled workstream, grep `cross-repo/inbox/` for memos whose title/workstream matches the active work and READ them; a standdown there means stop, not commit.

*Pairs with § Read your inbox before committing above — that section covers the general rule; this section names the pre-commit check as a hard gate specifically on cross-repo-coupled work.*

## Protocol-version bump is coupled to the consumer range-widen — never ship a host bump alone

*2026-05-29, project-rag.* A protocol/envelope-version bump on the producer (host) side is coupled to the *consumer's accept-range widen* **independently of any symbol-import coupling**. The two halves can look decoupled — the host bumps its emitted `protocol_version`, the consumer's code doesn't import anything from the host — yet shipping the host bump alone breaks every consumer that rejects unknown versions (the reject-unknown-version contract). **Reader-first, always:** land the consumer's accept-`{old, new}` range widen first, then flip the host's emitted version. Same-machine sibling-dir + on-branch + auto-push does NOT relax this — whichever side flips first breaks the other's parse immediately. This is the cross-repo *seam* statement of install-surface-completeness's § Bilateral bump sequencing; the install-surface wiki frames it as a multi-site value-parity hazard, this frames it as a cross-repo coordination gate: the version bump is a contract change that routes reader-first regardless of whether the two repos share an import.

## A received doctrine-seed premise is hypothesis — verify against YOUR substrate, scope by ownership not syntax

*2026-05-30, claude-unreal-holodeck.* A cross-repo doctrine-seed (a CLAUDE.md/wiki/agent-prompt amendment authored at DoE altitude and landed in your repo) carries a *premise* about how your repo works — and that premise is hypothesis, not ground truth, exactly like an inbound memo's fix-locus (§ Memo content is hypothesis). Before applying a seeded sweep across your repo, verify the premise against your own substrate. *(Canonical: a seeded "scripts resolve on PATH, cite bare name" rule assumed PATH-namespace resolution; a repo whose scripts actually live at repo-root `./bin` and are invoked cwd-relative would mis-apply the sweep.)* And **scope the sweep by ownership, not by syntactic match**: a grep for the seeded pattern hits call-sites you own AND call-sites the seed does not govern (vendored code, sibling-owned shims, fixtures) — applying the rewrite to every syntactic hit over-reaches past the ownership boundary the doctrine actually addresses. The DoE has standing to seed alignment (§ Doctrine seeding vs. code/install-surface change); the receiving EM has standing — and the obligation — to verify-then-scope before executing. Pairs with the prior-art-checker premise-pass: a seeded premise gets the same disk-verification an inbound plan claim gets.

## Glob the receiver's inbox before SENDING an outbound memo — a concurrent peer may have already sent one

*2026-05-30, project-rag-ue-addon.* The hypothesis-discipline sections above (§ Memo content is hypothesis, § Inbox Memo Concurrency) and the pre-reply checks (§ Inbox Memo Liveness — Archive Sweep) all govern the **receiver/reply side** — what to verify before *acting on* or *replying to* an inbound memo. This section is the **sender/outbound complement**: what to verify before *composing and sending* a memo of your own.

**Before sending a cross-repo memo on a heavily-concurrent shared branch, glob the receiver repo's `cross-repo/inbox/` (and `cross-repo/archive/`) for the same topic FIRST.** A concurrent session in your own repo may have already sent a memo on the same subject — and the already-sent one may be *mis-framed* against a PM decision the other session didn't have.

*Canonical:* a parallel session republished a corpus and sent a "republished — restart the daemon" memo into the sibling's inbox — against the PM's explicit *no-republish* call. The duplicate-and-contradiction was caught only because the next sender read the sibling inbox before composing, saw the rogue memo, and stopped. Had they checked only their own `git log`, they'd have sent a second (correct) memo that collided with the first, leaving the receiver with two contradictory directives.

**Why local `git log` is insufficient:** your own branch history shows *your* commits, not what a concurrent EM session in the same repo wrote into the *sibling's* tree. The outbound channel's state lives in the receiver's inbox, not in your repo's log. A clean local log is not evidence that no memo on this topic is already in flight.

**How to apply:** before `cross-repo-memo --to <receiver> --topic <slug>`, run a glob/grep of `<receiver-repo>/cross-repo/inbox/*<slug>*.md` and `<receiver-repo>/cross-repo/archive/*<slug>*.md` for the topic. If a same-topic memo exists: read it. If it is correct and current, do not duplicate — the receiver already has the signal. If it is *wrong* (mis-framed, contradicts a PM decision, supersedes-worthy), supersede it explicitly (`--supersedes <old-path>` or an in-place correction the receiver can see), don't silently stack a second directive. Verify sibling-repo channel state, not just local git log, before composing.

## See also

- `skills/handoff/SKILL.md` Step 0 — handoff trigger gate (YES-tests / NO-tests)
- `skills/spinoff/SKILL.md` Step 0 — PM-authorization gate
- `skills/session-end/SKILL.md` — lessons/state capture
- `CLAUDE.md` § Handoff Lineage — single-predecessor doctrine
- `docs/wiki/install-surface-completeness.md` — the universal install-surface rule, which combines with the cross-repo doctrine differently at the two altitudes above
