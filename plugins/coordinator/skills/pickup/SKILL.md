---
name: pickup
description: Resume work from a handoff or action a cross-repo memo — grab the baton and run
allowed-tools: ["Read", "Grep", "Glob", "Bash"]
argument-hint: "[handoff-file-path | memo-file-path]"
---

# Pickup — Resume from Handoff or Action a Memo

Pick up a handoff document and continue executing where the previous session left off, OR action an inbound cross-repo memo. Both are batons from another place — you must read the artifact before acting on it. This is a relay race; your job is to grab the baton and run, not to ask what race you're in.

**Design contrast with `/workstream-start`:** Workstream-start is general orientation — "what are we doing today?" with handoffs as one option among many. Pickup is artifact-first — the PM has already pointed you at specific prior work to continue or an inbound memo to act on. Skip the menu, skip the ceremony, get to the work.

---

## Step 1: Safety Preflight

Minimal — just enough to not lose work.

1. Run `git status` — if there are ANY uncommitted changes, commit immediately. Pickup is workstream-specific: stage only the paths belonging to the workstream you're resuming, never `git add -A` or `git add .`. The handoff doc you'll read in Step 2 declares the workstream scope in its `scope:` frontmatter — once read, extract the scope and commit via plain git (SC-DR-008, lessons.md:43, lessons.md:207):
   ```bash
   HANDOFF=<handoff-doc-path>
   # Extract scope paths from YAML frontmatter (  - <path> lines under scope: key)
   SCOPE=$(awk '/^scope:/{found=1; next} found && /^  - /{print substr($0, 5)} found && /^[a-z]/{exit}' "$HANDOFF")
   if [ -z "$SCOPE" ]; then
     echo "FAIL: handoff frontmatter scope: block missing or empty — cannot enumerate paths" >&2
     exit 1
   fi
   git add -- $SCOPE && git commit -m "pickup: <workstream> — resume" -- $SCOPE
   ```
   If the handoff isn't yet identified, stage the specific files explicitly by path:
   ```bash
   git add -- <path1> <path2> ... && git commit -m "pickup safety commit" -- <path1> <path2> ...
   ```
   Leave files outside this workstream alone — they belong to another concurrent session.

2. **Branch:** If on main, create or resume today's work branch:
   - Check for existing: `git branch --list 'work/{machine}/*'` and `git branch -r --list 'origin/work/{machine}/*'`
   - Resume today's branch if it exists, otherwise create `work/{machine}/{date}`
   - If already on a non-main branch, stay on it.

3. **Branch staleness:** If diverged from main for more than 2 days, warn:
   _"This branch has been diverged from main for {N} days. Recommend merging before new work — want me to run `/merge-to-main` first?"_
   **Wait for response before proceeding.**

---

## Step 1.5: Classify the Artifact

**Read before reasoning — the anti-confabulation gate.** A bare file path arrives with no procedure attached. The failure mode this step prevents is acting on, summarizing to the PM, or editing an unread artifact — the void-filling confabulation that rewrites the memo into what the model assumes it should say. STOP: read the artifact first, before any classification or action.

Once read, classify by **path + frontmatter shape**:

| Signal | Classification | Route |
| --- | --- | --- |
| File is in `tasks/handoffs/` AND frontmatter carries `status: active\|consumed` and `deployment_state:` | **Handoff** | Continue to Step 2 (handoff flow, unchanged) |
| File is in `cross-repo/inbox/` OR frontmatter carries `from:` + `to:` + `status: open\|actioned` | **Memo** | Jump to [Memo Branch](#memo-branch) below |
| File is in `tasks/handoffs/` AND frontmatter has `kind: spinoff` | **Spinoff** | Continue to Step 2 + spinoff banner in Step 3.5 |
| Ambiguous (file exists but frontmatter is missing or malformed) | **Surface to PM** | Do not guess; report the ambiguity and stop |

**Negative-spec:** do not apply the handoff schema mutation (`status: active → consumed`, `deployment_state`) on the memo path. Those are Step 5 handoff mechanics and do not apply to memos. The memo lifecycle is `open → actioned` only.

---

## Step 2: Identify the Handoff

**If `$ARGUMENTS` contains a file path or link:**

The PM has pointed you at a specific handoff. Read it immediately and proceed to Step 3.

**If `$ARGUMENTS` is empty:**

1. Check `tasks/handoffs/` for `.md` files.

2. **If no handoffs exist:**
   _"No active handoffs in `tasks/handoffs/`. Nothing to pick up — use `/workstream-start` for general orientation."_
   **Stop here.**

3. **If exactly one handoff exists:**
   Read line 1 to get the heading and the filename.
   _"One active handoff: `{filename}` — {heading}. Loading it now."_
   Read the full file and proceed to Step 3.

4. **If multiple handoffs exist:**
   Read line 1 of each file to get headings. Present a numbered list:
   ```
   Active handoffs:
   1. {filename} — {heading} ({date})
   2. {filename} — {heading} ({date})
   ...
   ```
   _"Which handoff should I pick up?"_
   **Wait for the PM to choose.** Then read the selected file and proceed to Step 3.

---

## Step 2.5: "While You Were Away" Surface (prior-day handoffs only)

After reading the handoff, extract the handoff's date from its filename (`YYYY-MM-DD-*.md`) or its header.

- **Same day (handoff date == today):** straight baton pass — skip this step entirely.
- **Prior day (handoff date < today):** glob `tasks/week-changelog/*.md`, excluding `HEADER.md`. Filter to daily files whose filename date is strictly after the handoff date. For each matching file, emit one line:

  ```
  <date> (<hostname>): <Scope field value> — <Plans touched: implemented entries, if any>
  ```

  Cap the surface at ~10 lines. If more files exist than the cap:
  > "(N more days — see `tasks/week-changelog/` for the full record)"

  If no daily files exist since the handoff (changelog not yet in use), skip silently.

**Purpose:** ambient context across other workstreams that moved while this workstream was paused. Not a decision gate — just orientation.

---

## Step 3: Load Context and Run

The handoff is the work order. Do NOT present a menu. Do NOT ask "want me to proceed?" Do NOT summarize the handoff back and wait for approval.

1. **Load referenced files:** Read any files the handoff's "In-Progress Work," "Recommended Next Steps," or "Files Modified" sections reference that aren't already in context.

2. **Load lessons:** Read `tasks/lessons.md` if it exists. Quick context, no recitation needed.

3. **Check the handoff's branch:** If the handoff specifies a `Branch:` in its "Current State" section AND it differs from your current branch, check out that branch (unless it's already been merged to main).

4. **Reconcile handoff items against git — MANDATORY before executing anything.**

   Concurrent sessions and machines routinely close items the handoff still lists as open. Before acting on ANY item in "Recommended Next Steps," "In-Progress Work," or equivalent pending-work sections:

   a. **Git log check:** Extract the handoff's written date from its filename or header (`YYYY-MM-DD`). Then run:
      ```bash
      git log --oneline --since="<handoff-date>" --all
      ```
      Scan commit subjects for key nouns from each pending item. A commit whose subject clearly matches an item is strong evidence that item shipped.

   b. **Plan/stub status check:** For any pending item that references a plan or stub file (e.g., `docs/plans/*.md`, `tasks/*/stub.md`, `tasks/*/todo.md`), Read the file and check its `**Status:**` field. A stub the handoff calls "pending" but whose own status reads `Shipped`, `Completed`, or `Execution complete` is closed — the handoff is stale on that item.

   c. **Drop confirmed-closed items.** Items verified as already shipped do NOT go into your session execution queue. Optionally note them inline as _"verified-closed since handoff"_ for the paper trail.

   d. **Gate-source re-read for `awaiting_gate` handoffs.** If the handoff frontmatter carries `deployment_state: awaiting_gate` with a `gate_dependency: <path>` one-liner, Read the gate path before treating the handoff as still-pending. Gates clear silently between handoff-write and pickup — a PR merges, a sibling stub ships, a flag flips. If the gate has cleared, flip `deployment_state: ready_to_fire` in the mutation pass (Step 5) and proceed; if it's still closed, surface the gate status to the PM before queuing further work.

      **Aging reconcile:** compute `now − created_at` from handoff frontmatter (`created:` field per `docs/wiki/spinoff-handoffs.md` schema). If ≥14 days AND `deployment_state: awaiting_gate` AND no `last_gate_recheck:` field (or `last_gate_recheck` ≥7 days ago), the gate is **stale** — force a re-check of the named gate even if the prior re-read in this step would otherwise have been a quick literal-string match. After the re-check, write `last_gate_recheck: <ISO date>` into frontmatter in the mutation pass (Step 5). If the gate has cleared, flip to `ready_to_fire` as above; if still closed but the gate text no longer accurately names the blocker (e.g., the named sibling stub has been archived without shipping), surface to PM with the discrepancy — do NOT silently retain a stale gate. See `docs/wiki/spinoff-handoffs.md` § "Awaiting_gate aging" for full rationale and the 14d / 7d threshold derivation.

   e. **Premise verification — paths, commits, scope claims.** The handoff body is hypothesis, not ground truth (per coordinator CLAUDE.md § Verifying Handoff Premises). Before executing:

      - **Paths cited as "modified" or "needs editing":** `ls` / `Read` each one. Files move, get renamed, or get deleted between handoff-write and pickup. A handoff that says "edit `foo/bar.py`" against a renamed file is a false-premise dispatch.
      - **Commit SHAs cited as "shipped" or "landed":** `git cat-file -e <sha>` to confirm reachable; `git branch --contains <sha>` to confirm landing claim. Cherry-picks and rebases invalidate SHA assertions across sessions.
      - **Scope frontmatter pathspecs:** glob each pathspec. An empty glob means the workstream substrate has moved — surface to PM before mutation, do not proceed silently.
      - **Premises that include "X is true" / "Y already done" / "Z was decided":** for each load-bearing premise, identify the witness (a file, a commit, a doc section) and confirm it. Premise drift is the dominant failure mode for >24h-old handoffs.

      See `docs/wiki/spinoff-handoffs.md` § "Pickup-side premise check" for the full discipline. Treat unverified premises as same-session blocking gaps, not deferrals.

   f. **Stealth-skip detection — pickup-as-defer-via-rationale.** A handoff that marks an item `shipped` with prose rationale instead of a commit SHA ("rule covered semantically by adjacent bullet", "subsumed by the X workstream", "naturally addressed by Y") is the doctrine-forbidden defer disposition disguised as productive pickup. The rationale-prose `shipped_in:` value bypasses the literal acceptance criterion. **Detection:** any `shipped_in:` value that is not a 7+ hex character commit SHA (or an explicit `substantively-shipped-no-commit:<PM-ack-date>` token) is suspect. **Action:** treat such items as still-pending, re-verify the literal acceptance criterion against current `HEAD`, and surface the schema violation to the PM. Pickup means doing the work or surfacing a real blocker — never authoring a rationale that defers.

   g. **Prereq tables: executable verification, not visual checkmark.** Handoff prereq tables that list `✅ verified` against prerequisites are themselves hypothesis at pickup time, even when the checkmark is fresh. Re-run the verification commands or grep the asserted state before consuming the prereq downstream. A prereq verified at handoff-write can age out by pickup time (a sibling session merged a conflicting change, a dependency rotated, an env var got unset). Visual ✅ in a prose table is paper-trail, not gate. The actual gate is whichever command would have produced the ✅ — re-run it.

   **Empirical baseline:** Expect 30–60% of inherited items to be already closed. Skipping this step means redoing shipped work, conflicting with landed commits, or spawning duplicate executors.

   **Partial-completion claims** (DroneSim T1.2): Before redoing any work the handoff describes as "stalled", "unfinished", or "partial", verify against `git log --oneline --all -- <relevant paths>`, the `archive/completed/` log, and live artifact state. Treat the handoff's status as a hypothesis, not ground truth — work often persisted despite the handoff saying otherwise.

5. **Report briefly — two lines max:**
   ```
   Picked up: {handoff heading}
   Branch: {branch} | Next: {first recommended step, abbreviated}
   ```

   **Spinoff banner:** If the handoff frontmatter has `kind: spinoff`, prepend one extra line:
   ```
   This is a spinoff — predecessor is none by design. Treat the handoff body as ground-truth spec; do not look for in-progress work to resume.
   ```
   Counters the default assumption that a handoff describes already-in-progress work. Note: `kind: spinoff` and `kind: spinoff-roadmap` both carry `predecessor: none` — when premise verification (Step 3.4e) cannot find a continuity ancestor, that is correct by design for spinoffs and not a stale-handoff signal. See `docs/wiki/spinoff-handoffs.md` § "Pickup-side premise check — spinoff exemption".

   **Recovery banner:** If the handoff frontmatter has `kind: recovery`, prepend one extra line:
   ```
   This is a recovery handoff — prior session terminated uncleanly (crash/kill). Verify on-disk state against the handoff body before resuming; partial work may exist that the author could not commit.
   ```
   Recovery handoffs follow the standard continuation flow, but the successor's first move is disk verification (uncommitted edits, orphan `.tmp.*` files, partial executor output) per CLAUDE.md § "Verifying Executor Output After a Crash or Timeout". A null `predecessor:` on `kind: recovery` is permitted (no recoverable predecessor existed) and is NOT a stale-handoff signal.

5. **Frontmatter mutation in place** — `/pickup` mutates frontmatter only; archival happens at the successor moment (`/handoff` chain-archival or `/workstream-complete` Step 2.7).

   ### Pre-mutation safety gates (sequential, all must pass before any write)

   1. **`git fetch origin <branch>` + re-read frontmatter.** Closes the cross-machine race window — if a peer already mutated and pushed, the fetch pulls their version and the next gate sees `consumed_by:` populated.
   2. **`consumed_by:` idempotency check.** If frontmatter shows `consumed_by:` non-empty after fetch, exit non-zero: _"Concurrent /pickup detected on `<file>` — already claimed by `<consumed_by>`. Inspect their session before proceeding."_
   3. **`cs_claim_handoff <basename>`.** Atomic mkdir gate per the concurrent-pickup spike. Exit non-zero on live concurrent claim. Call:
      ```bash
      source ~/.claude/plugins/coordinator/lib/coordinator-session.sh
      cs_claim_handoff "$(basename tasks/handoffs/<file>)"
      ```
   4. **`pickup_ready` absent → non-blocking warning.** If the handoff frontmatter does NOT contain `pickup_ready: true`, print once to the PM-facing channel:
      _"⚠ handoff `<basename>` lacks `pickup_ready: true` — proceeding anyway. (Author may not have explicitly authorized pickup; verify the workstream is yours to resume.)"_
      Do NOT prompt. Do NOT block. Continue to mutation.

   ### Frontmatter mutation (in place at `tasks/handoffs/<file>`)

   - `status: active` → `status: consumed`
   - `deployment_state: <whatever>` → `deployment_state: in_flight`
   - Append `consumed_at: <ISO UTC timestamp>`, `consumed_by: <session-id>` — resolve the session id with `$CLAUDE_CODE_SESSION_ID` first (platform-injected, per-session, unclobberable by sibling sessions; Claude Code ≥ ~2.1.150), falling back to `cat .git/coordinator-sessions/.current-session-id` (the last-writer-wins sentinel written by `session-init.sh`, for older Claude Code). Never the machine name. Same resolution pattern as `/workstream-complete` Step 2.7.
   - Do NOT remove `pickup_ready: true` if present — it stays as authorial-intent record on the consumed handoff.

   ### Commit

   Single explicit-path commit of the mutation only — **no `git mv`** (SC-DR-008):
   ```bash
   git add -- tasks/handoffs/<file> && git commit -m "pickup: <workstream> — frontmatter mutation" -- tasks/handoffs/<file>
   ```

   The handoff remains in `tasks/handoffs/`. Archival happens at one of two successor moments:
   - **`/handoff` chain-archival** — when this session writes a successor handoff, the explicit predecessor is moved to `archive/handoffs/`.
   - **`/workstream-complete` Step 2.7** — when this session ends without a successor handoff, Step 2.7 archives any handoff whose `consumed_by:` matches this session.

6. **Begin executing the first item in "Recommended Next Steps."** If the handoff lists multiple next steps, execute them in order unless the PM redirects. If there's an "In-Progress Work" section describing something partially complete, resume that first — it takes priority over the recommended next steps list. The picking-up session's eventual `/handoff` or `/workstream-complete` flips `deployment_state: in_flight` to `shipped` (with `shipped_in: <sha>`) or back to `ready_to_fire` if the work paused mid-stream and another session should resume it.

---

## Memo Branch

> Entered from Step 1.5 when the artifact is classified as a memo (in `cross-repo/inbox/` OR carrying `from:` + `to:` + `status: open|actioned` frontmatter).

<!-- Spec backlink: docs/plans/2026-05-30-pickup-cross-repo-memo-fork.md § C1 -->

### M0 — Short-circuit already-actioned memos

<!-- Review: code-reviewer F1 — guard terminal memos before any re-action attempt.
     An already-actioned memo is schema-valid; the guard is behavioral, not schema-enforced. -->

**Check `status:` before any other action.** If the memo's `status:` field is already `actioned` (terminal state):

1. Read the full memo to load its existing `decision:`, `decision_note:`, and `actioned_note:` fields.
2. Report those fields to the PM as **read-only context** — e.g.: _"This memo is already actioned. Decision: `<decision>`. Note: `<decision_note or actioned_note>`."_
3. **STOP.** Do NOT re-run M3 disposition. Do NOT flip any frontmatter. A terminal memo is not re-actioned.

Re-opening a closed memo is a **sender action** via a new memo, not a receiver pickup.

---

### M1 — Read the whole memo before any other action

**STOP.** Do not summarize-to-PM. Do not act on the memo's request. Do not edit any field. Read the full memo body — title, `from:`, body text, cited locus, proposed action — before proceeding.

This is the same anti-confabulation gate as Step 1.5, applied a second time at the action boundary. Skipping this read and acting on a brief summary is the root failure the memo branch exists to prevent.

### M2 — Verify premises

Before acting on the memo's content, apply the discipline from `docs/wiki/cross-repo-communication.md` § "Memo content is hypothesis — verify before acting":

- Grep the cited locus/symbol in THIS repo — the proposed fix-locus may be wrong even when the symptom is real.
- Run `git fetch` and scan `origin/<branch>` for commits that address the memo's topic — a concurrent session may have already actioned it.
- Sweep `cross-repo/archive/`, `archive/completed/`, and `docs/plans/` for same-topic terminal artifacts (standdown / abandoned / superseded) — an `open` status is a lagging indicator, not ground truth.

### M3 — Branch on `kind`

Determine the memo's `kind` field. **If absent, treat as `ask`** — the safe default (surfaces with urgency; never silently downgrades an unlabeled memo).

**Pinned enum:** `ask | consult | fyi`. `ack` is NOT a valid `kind` — it is receipt-state, never sender-declared.

---

#### `fyi` — acknowledge only

The sender is notifying, not requesting.

1. Write in place:
   ```yaml
   status: actioned
   actioned_note: "noted — informational"
   ```
   Do NOT add a `decision:` field — none is warranted for an informational memo.
2. Commit the single-file mutation:
   ```bash
   git add -- cross-repo/inbox/<file> && git commit -m "memo: actioned <topic> — fyi noted" -- cross-repo/inbox/<file>
   ```
3. No proposal. No reply. Done.

---

#### `ask` — adjudicate-and-own

The sender is requesting action. Per `docs/wiki/cross-repo-communication.md` § "Memo-lifecycle adjudication is EM work": **do not surface to the PM with "what should I do?" — adjudicate and own the disposition for this repo's customers and consumers.** The sender's ask is a peer hypothesis from another EM, not a work order.

Weigh the request against this repo's context, then choose one of three dispositions:

**Accept** — the ask is sound and actionable. **Before performing the work, calibrate ceremony — this is the receiver's call, not the sender's.** An ask's magnitude is not knowable from its register: a sender writes every `ask` plainly and in the imperative (§ Authoring an ask, comm wiki) — that governs sender *plainness*, NOT how big a deal it is for *your* repo. You judge magnitude here, at pickup. Ceremony and channel are orthogonal: this calibration is about how much process an *accepted* ask earns, independent of whether a memo channel was the right vehicle at all (that is the §208 channel question — see comm wiki § Picking up a memo).

- **Default: mechanical-direct.** Most accepted asks are surgical follow-ups, not novel decisions. Perform the work now, commit it (on both sides where you hold authority over the offering repo — see step 3), and action the memo. **No plan, no round-trip, no back-and-forth.** Moving a document, adopting a named doctrine, applying an agreed rename are direct-dispatch work — treat them as such.
- **Escalate to a plan ONLY on a NAMED weighty signal.** Inherit the `ceremony-calibration.md` § TL;DR decider — escalate when the ask is a *novel decision* (not a surgical follow-up to one already made), *instance #1* of a pattern with downstream occupancy, or *vague enough* in framing to need shaping first. Absent a named signal, the default stands; do not manufacture ceremony to feel thorough.

Then, having calibrated:

1. Perform the work — directly (the default), or via the plan pipeline if you named a weighty signal above.
2. Write in place:
   ```yaml
   status: actioned
   decision: accepted
   decision_note: "<what was done, one line>"
   ```
3. Commit with memo mutation included (or as a follow-on single-file commit). **A mechanical cross-repo transfer commits on both sides** when you hold authority over the offering repo (comm wiki § Picking up a memo, both-sides-commit carve-out); where you lack that authority, the offering-side change routes per the altitude rules (memo + PM-relay for code, doctrine-seed for doctrine).

**Decline** — the ask is wrong for this repo's consumers, already done, or superseded:

1. Write in place:
   ```yaml
   status: actioned
   decision: declined
   decision_note: "<rationale — why it doesn't apply or was already handled>"
   ```
2. Commit the single-file mutation.

**Surface to PM** — only when the ask implicates a genuine product decision, architectural tradeoff, or scope fork that is above EM authority:

1. Surface a one-line summary: _"Inbound `ask` memo from `<from>` on `<topic>` requires a product decision: `<one-line framing>`. Proceed with [option A] or [option B]?"_
2. **Wait for PM response before writing any frontmatter.** Do not mark `actioned` until the PM has decided.
3. Once decided, write `status: actioned` + the chosen `decision:` + `decision_note:`.

**There is no fourth disposition — queuing the ask is the laundering anti-pattern, not a disposition.** Accept / Decline / Surface-to-PM are the *only* exits. Filing the inbound ask into `tasks/improvement-queue.md` (or `~/.claude/tasks/coordinator-improvement-queue.md`, or re-framing it as "a separate plan for later") is NOT a way to handle a memo — it moves the baton from one staging ground to another, adds zero value, and silently makes a *prioritization* call (deciding this ask is not-now) that belongs to the PM, not the EM. The reflex feels productive because the inbox row clears; it is not. If you cannot Accept the work this session, the honest exits are: **Decline** with an architectural rationale (the ask is wrong for this repo's consumers / already done / superseded), or **Surface-to-PM** (you'd action it but it's competing for priority — that's a PM call, so ask, don't queue around them). "Annoying to do right now" is not an architectural rationale; presume action and do it. → coordinator CLAUDE.md § Improvement Queue (admission rule); `docs/wiki/cross-repo-communication.md` § Picking up a memo.

**Critical negative-spec:** write `status: actioned` (the terminal state). NEVER write `status: action_taken` — that is a grandfathered-only schema value whose cross-field rule (`bin/lib/schema.js:664-671`) requires both `action_taken_at` AND `decision`. The `decision:` field on `actioned` is an audit choice, not a schema requirement.

---

#### `consult` — reply in place

The sender wants input or opinion, not action.

<!-- Review: code-reviewer F2 — replace ambiguous "OR" with a decision rule: short responses into
     actioned_note; longer responses into ## EM Response section with actioned_note as pointer. -->

1. Write a substantive response into the memo using the following decision rule:
   - **Response ≤ ~200 chars:** write it directly into `actioned_note`.
   - **Response > ~200 chars:** append a `## EM Response` section to the memo body AND set `actioned_note: "see ## EM Response in body"` (a pointer, not a duplicate of the long response).
2. Write in place. Short-response example:
   ```yaml
   status: actioned
   actioned_note: "<your substantive response — up to ~200 chars>"
   ```
   Long-response example (response written in body under `## EM Response`):
   ```yaml
   status: actioned
   actioned_note: "see ## EM Response in body"
   ```
3. Commit the single-file mutation.
4. **No return-memo.** The receiver-side flip + commit IS the receipt. Per `docs/wiki/cross-repo-communication.md` rule 6 ("don't send an ack-of-ack when the inbound was a confirmation, not a request") and the ack-of-ack prohibition: the sender looks at the receiver's inbox/archive on the same machine — a return memo sent back is ceremony with no new channel. Terminal: `actioned` with a substantive response captured.

### M4 — Commit shape

All memo mutations use an explicit single-file commit — no `git add -A`, no sweep:

```bash
git add -- cross-repo/inbox/<file> && git commit -m "memo: actioned <topic> — <decision|noted|replied>" -- cross-repo/inbox/<file>
```

The flip + commit IS the receipt. The sender reads it on the same machine at their next session. No ack-of-ack. No return memo.

---

### Worked memo-pickup example

The PM hands you the path `cross-repo/inbox/2026-05-30-kind-enum-proposal.md` as a naked prompt.

**Step 1.5 — Classify:** Read the file. Frontmatter shows `from: project-rag-em`, `to: claude-central-em`, `status: open`. → Memo branch.

**M1 — Read whole memo:** Body proposes adding a `kind` field to the memo schema.

**M2 — Verify premises:** Grep `kind` in `schemas/cross-repo-memo.yaml` — field absent; premise is accurate. `git fetch` + `git log` — no concurrent work on this topic. `cross-repo/archive/` sweep — no standdown or superseded memo.

**M3 — kind = `ask` (explicit).** Adjudicate: the proposal is sound and fits this repo's consumers (no product tradeoff). Disposition: accept. Perform work (e.g., ticket it or plan it — commit the frontmatter flip in the same session; if the work spans multiple sessions, flip to `actioned` immediately with `decision_note: 'in progress — see <plan path>'` so the inbox doesn't age as open). Then write in place:

<!-- Review: code-reviewer F7 — parenthetical added: same-session flip is the norm; multi-session
     work should flip immediately with an in-progress decision_note to prevent inbox aging. -->

```yaml
status: actioned
decision: accepted
decision_note: "kind enum planned for 2026-05-30 memo-fork plan — see docs/plans/2026-05-30-pickup-cross-repo-memo-fork.md"
```

**M4 — Commit:**

```bash
git add -- cross-repo/inbox/2026-05-30-kind-enum-proposal.md
git commit -m "memo: actioned 2026-05-30-kind-enum-proposal — accepted" -- cross-repo/inbox/2026-05-30-kind-enum-proposal.md
```

Done. No return memo sent.

---

## Cross-Repo MOVE and Tracker-Residual Discipline

**Cross-repo MOVE of a roadmap stub requires a source-side residual audit before archiving the original.** Scan source scope vs destination need; if any scope is not transported (e.g., framework-agnostic detector when destination only needs UE overlay), file a successor stub for the residual on the source side BEFORE archiving the original. Update downstream `blocked_by:` lists to reference the successor.

**Tracker entry naming a non-existent plan file is a closure signal, not a missing-file bug.** Verify on-disk; if the workstream shipped without leaving a plan, write a closing DR and resolve the tracker row. Do not re-author the plan from scratch.

## Notes

- **T3 handoff detection.** If ANY of the following fire, surface the recommendation below before executing:
  - The handoff frontmatter shows `cost: T3`.
  - The handoff body contains ≥7 numbered implementation steps AND ≥3 distinct architectural seams.
  - **Cross-repo signal (size-from-investigation correction).** The handoff describes multi-repo execution AND was authored from inside an investigation — detected by ANY of: (a) the handoff body or `## Recommended Next Steps` names ≥2 distinct repos (sibling-repo paths, `cross-repo/`, or `$REPO_*` registry handles), OR (b) the body contains a "investigation complete," "ready to execute," "spike done," or equivalent investigation-terminus phrase AND the scope touches more than one repo, OR (c) frontmatter `scope:` pathspecs resolve into ≥2 repos. T-shirt sizes authored from inside an investigation systematically under-read cross-repo execution scope — the investigation felt finished, but the multi-repo execution ahead is the actual work. Treat the under-sizing as the default, not the exception.

  **Disposition splits on whether the handoff prescribes a plan — and the two halves are NOT both PM-gated.**

  - **The plan is transitively authorized — do NOT ask.** A handoff handed to you for pickup is a PM-authored artifact (only the PM creates one). If its body prescribes a plan ("plan-shaped, not straight-to-executor", "invoke `/plan`", "decompose before executing", or equivalent), the act of handing you that pickup IS the plan authorization — the keyword-gate on `/plan` is satisfied transitively through the upstream gate that produced the handoff. **Invoke `coordinator:plan` directly.** Do NOT bounce back with "want me to plan?" / "proceed directly or fork-and-plan?" — that is the false-choice anti-pattern dressed up as gate-compliance (the PM already prescribed the plan; asking permission to do it re-litigates a settled decision). See coordinator CLAUDE.md § Challenging the PM ¶ `/plan` exemption. The "grab the baton and run" default applies to T1/T2 executor work; for T3 the baton you grab is the *plan*, not the executors — same run-don't-ask spirit, one altitude up.

  - **The spinoff *fork* IS still PM-gated — but it must NOT block the plan.** Forking the T3 continuation into its own spinoff handoff creates a new continuity artifact, which stays PM-authorized per `skills/spinoff` Step 0. Surface it as a separate one-line candidate (_"Candidate spinoff: <slug> — <topic>. Authorize?"_) **without gating the plan on the answer** — plan now off the pickup; the fork is an orthogonal continuity question the PM can answer in parallel or later. Conflating the two (the prior failure mode) let a PM-gated fork question hold a transitively-authorized plan hostage.

  - **Cross-repo plan obligations carry regardless.** For the cross-repo case, the plan must cross-check the file-overlap and contract-change gates per coordinator CLAUDE.md § Pre-Dispatch Verification before any parallel dispatch, and route sibling-repo edits via `cross-repo-memo` + PM relay (never direct host-session edits to the sibling). T3 cross-repo also warrants the Staff Engineer review on the plan — but that is `coordinator:plan` → `coordinator:review` pipeline work, not a reason to ask before planning.
- This command does NOT load action items, roadmaps, project trackers, or orientation caches. That's `/workstream-start` territory. Pickup is laser-focused on the handoff.
- If the handoff references a plan doc (`tasks/<feature>/todo.md`), read it — but only because the handoff pointed to it, not as a general survey.
- The handoff's "Key Decisions Made" section is context you should internalize — don't re-litigate those decisions unless you find evidence they were wrong.
- **`git mv` after Edit stages only the rename, not the content change.** If a future revision of this skill (or a sibling skill) ever needs to both rename AND edit a file, the correct order is: `git mv src dst` FIRST, THEN Edit `dst`, THEN `git add -- dst`, THEN commit. Edit-then-`git mv` stages only the rename and silently drops the content delta.
- **Archiving:** `/pickup` mutates frontmatter in place at `tasks/handoffs/` and commits — it does NOT move the file. Archival is deferred to the picking-up session's terminal event: `/handoff` (chain-archival of the explicit predecessor) or `/workstream-complete` Step 2.7 (archives any handoff whose `consumed_by:` matches this session). The `session-init.sh` boot-time sweep provides a safety net for orphaned consumed handoffs (session died before archival). Handoffs are never archived based on age alone.
- **Failure mode to avoid:** Executing items a concurrent session already shipped. The git log + plan status reconciliation in Step 3.4 is the gate — empirical baseline says 30–60% of inherited items are already closed. Skipping it means duplicate work, conflicts with landed commits, or spawned duplicate executors.
