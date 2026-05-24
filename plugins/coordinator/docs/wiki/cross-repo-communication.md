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

→ **One pattern only: `cross-repo-memo --to <receiver-em-id> --topic <slug> --title "<one-line>"`.**

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

`hooks/scripts/block-unauthorized-handoff.sh` blocks `Write` that creates a new file in `tasks/handoffs/` or `tasks/spinoffs/` unless:

- The active transcript shows recent invocation of `/handoff`, `/session-end`, or `/spinoff`, OR
- `COORDINATOR_HANDOFF_AUTHORIZED=1` is set in the environment (manual override for edge cases).

Edits to existing handoff files are always allowed (covers `/pickup` frontmatter mutation and `Step 2.10` review-marker writes).

A routing-mismatch branch in `validate-frontmatter-schema.js` (the same PreToolUse hook that enforces frontmatter schemas and the own-inbox deny guard) offers the `cross-repo-memo` CLI redirect when a Write carries a YAML `to:` field addressing a different repo than the one being written into, OR when a Write to a memo-shaped path (`*/memos/*` or a path under `cross-repo/`) carries free-form capitalized `To:`/`From:` headers. Fires as `additionalContext` (offer-shape — never deny). Central-aware: `to: claude-central-em` writing into `~/.claude` is a routing match → silent. Canonical inbox/archive writes are excluded (own-inbox guard handles `cross-repo/inbox/`; `cross-repo/archive/` holds closed actioned memos). Override: `COORDINATOR_OVERRIDE_MEMO_REDIRECT=1`. See `docs/wiki/coordinator-tripwires.md` § Routing-mismatch memo-redirect offer.

## Four coupled path declarations — keep in lockstep

The active-memo path appears in exactly **four enforced code sites** that must stay in lockstep whenever the inbox path changes:

1. **CLI write target** — `bin/cross-repo-memo:635` (`cross-repo/inbox/`)
2. **Schema `applies_to`** — `schemas/cross-repo-memo.yaml:2` (`cross-repo/inbox/[0-9]*.md`)
3. **Own-inbox guard regex** — `validate-frontmatter-schema.js:385` (`^cross-repo/inbox/[0-9]`)
4. **Surface glob** — `bin/workday-start-cross-repo-memo-surface.sh:34` (`cross-repo/inbox`)

A **fifth deliberately-broad negative-exclusion site** at `validate-frontmatter-schema.js:147` uses `^cross-repo/` (not `^cross-repo/inbox/`) — this must NOT be narrowed. It is the routing-mismatch check that must cover both `inbox/` and `archive/` writes so actioned archive memos are not wrongly offered a redirect.

Two human-facing doc declaration sites (the live `cross-repo/README.md` and `canonical-structure.yaml`) are non-enforced but should stay in sync. AC-7 in the test suite verifies the T3 round-trip.

**Why this matters:** When the own-inbox guard regex was too broad (`^cross-repo\/[0-9]` instead of `^cross-repo\/inbox\/[0-9]`), the guard silently stopped firing after the inbox/archive restructure because active memos had moved to `cross-repo/inbox/`. The guard appeared active but matched nothing. Updating one site without the others produces silent delivery-guard failures — exactly the worst class of failure for a security boundary.

## Shared constants — _CENTRAL_RECEIVER_IDS and _PUBLISH_TARGET_EM_IDS

Two frozensets in `bin/cross-repo-memo` are shared between the sender-side and receiver-side resolution paths to prevent drift:

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

### CLI

```
cross-repo-memo --to <receiver-em-id> --topic <slug> --title "<one-line>" \
  [--body-file <path>]
```

**Receiver resolution is by convention, not a hand-maintained table.** A `<receiver>-em` identity maps to the machine-local registry key `repos.<receiver, dashes→underscores>` — e.g. `project-rag-ue-addon-em → repos.project_rag_ue_addon`, `dronesim-em → repos.dronesim`. **The receiver set IS your machine-local repo list:** any repo registered under `repos.<name>` (`machine-local set repos.<name> <path>`) is automatically a valid `<name>-em` receiver with no code change — so anyone installing the coordinator gets cross-repo delivery to their own registered repos for free. Run `machine-local keys | grep '^repos\.'` to see them. The only exceptions are identities whose doctrine name diverges from the repo's registry shortname (currently just `holodeck-em → repos.claude_unreal_holodeck`), held in a tiny alias map in `bin/cross-repo-memo` that does not grow with repo count.

On machines where the receiver repo is not registered, the CLI **hard-errors** (exit 1, no file written) and lists the known receivers — a dirty memo cannot be written to a repo that isn't on this machine. There is no central-only fallback in the single-surface model; route via the PM's next session in that repo instead. (`central-only` survives only as a grandfathered `delivery_mode` value in the schema for pre-2026-05-23 memos — the CLI no longer issues it.)

On success the CLI prints the receiver path and the relay reminder:

```
Receiver-side: <abs-path>
Hand the PM this path for relay: <abs-path>
Reminder: Hand the PM the receiver path — PM-relay is still the primary channel.
```

(`--self-receipt` prints only the `Receiver-side:` line — no relay reminder, since the dispatcher is the receiver.)

### `/workday-start` Step 1.45 surfacing (receiver-inbound)

A step inserted between Step 1.4 (cross-reference completed archive) and Step 1.55 (Recent Roadmap Orientation) queries **this repo's** `cross-repo/inbox/*.md`, parses frontmatter, filters to `status: open`, and surfaces:

```
Cross-repo memos awaiting your action:
- 2026-05-23 from claude-central-em: gate-check failures — open (1 day)
```

Staleness flag: `open` >7 days appends ` [STALE]`.

Cap: ≤8 entries; `(N more — see cross-repo/inbox/ for full list)` truncation beyond that.

`actioned` memos drop off the surface. The helper script is `bin/workday-start-cross-repo-memo-surface.sh`.

### Don't re-nag the PM about already-sent memos

Once the receiver path has been handed to the PM at send time, the sender's job is done. Do not re-list memos (or doctrine-seeding direct writes) as "pending PM-relay" or "pending your action" in later session reports, `/handoff` bodies, or session openings. The receiving repo's `/workday-start` Step 1.45 surfacing is the canonical channel; sender-side action-state knowledge goes stale silently. Operative rule lives in `skills/session-end/SKILL.md` § Step 2.66.

### Grandfather cutoff

**Pre-2026-05-22 memos are grandfathered.** Step 1.45 skips memos with `created: < 2026-05-22` by design. If a pre-cutoff memo has unfinished business, re-issue via `cross-repo-memo` with `supersedes: <old-path>`.

### Worked example

Memo from `claude-central-em` to `project-rag-em`.

**Step 1 — Sender writes (2026-05-23).**

```sh
cross-repo-memo --to project-rag-em --topic gate-check-fix \
  --title "Gate-check failures in bin/check-plugin-drift.sh — recommended fix"
```

CLI writes `X:/project-rag/cross-repo/inbox/2026-05-23-gate-check-fix.md` (dirty, untracked) with:
```yaml
---
title: "Gate-check failures in bin/check-plugin-drift.sh — recommended fix"
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
decision: "Fixed gate-check exit-code handling in bin/check-plugin-drift.sh"
```
Commits: `memo: actioned 2026-05-23-gate-check-fix — accepted and implemented`

Done. Memo lives in `project-rag/cross-repo/inbox/` as the active record; once actioned it may be swept to `project-rag/cross-repo/archive/`. No further action required on either side.

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

6. **But don't send an ack-of-ack when the inbound was a confirmation, not a request.** SEND outbound when you've *unblocked* a peer (their inbound was a request gated on you). DON'T send when their inbound was a *confirmation* — the receiver-side `status` flip + git history is the audit trail; ack-of-ack is ceremony. Tell: you're drafting a memo whose body reads "Confirmed (i)/(ii)/(iii)… same as your memo" with no new information. (See also § Don't re-nag the PM about already-sent memos.)

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

**Enforcement at send time.** The CLI (`bin/cross-repo-memo`) runs `git check-ignore` on the target path in the receiver repo before writing anything. If the check confirms the path is gitignored, the CLI hard-errors loudly — "refusing to deliver to `<path>`: it is gitignored in the receiver repo and would be invisible in `git status`." The memo is NOT written. The error surfaces at send time, not silently after the receiver fails to see it. A receiver that is not a git repo at all (exit 128 from `git check-ignore`) is treated as unblocked — a non-git receiver cannot gitignore anything.

**Canonical structure doctor.** The scaffold and doctor tooling (`bin/scaffold-canonical-structure.sh`, `canonical-structure.yaml`) create the inbox and archive directories with their READMEs on first run, ensuring newly onboarded repos start with a git-tracked surface.

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

## Migration — bin/migrate-cross-repo-layout.sh

When a repo was set up under an earlier layout (flat `cross-repo/*.md`, or top-level `archive/cross-repo/`), run `bin/migrate-cross-repo-layout.sh` once to bring it to the current `inbox/` + `archive/` structure:

```sh
bash bin/migrate-cross-repo-layout.sh
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

## See also

- `skills/handoff/SKILL.md` Step 0 — handoff trigger gate (YES-tests / NO-tests)
- `skills/spinoff/SKILL.md` Step 0 — PM-authorization gate
- `skills/session-end/SKILL.md` — lessons/state capture
- `CLAUDE.md` § Handoff Lineage — single-predecessor doctrine
- `docs/wiki/install-surface-completeness.md` — the universal install-surface rule, which combines with the cross-repo doctrine differently at the two altitudes above
