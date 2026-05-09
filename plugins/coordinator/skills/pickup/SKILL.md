---
name: pickup
description: Resume work from a handoff — grab the baton and run
allowed-tools: ["Read", "Grep", "Glob", "Bash"]
argument-hint: "[handoff-file-path]"
---

# Pickup — Resume from Handoff

Pick up a handoff document and continue executing where the previous session left off. This is a relay race — the baton has been passed. Your job is to grab it and run, not to ask what race you're in.

**Design contrast with `/session-start`:** Session-start is general orientation — "what are we doing today?" with handoffs as one option among many. Pickup is handoff-first — the PM already knows they want to continue prior work. Skip the menu, skip the ceremony, get to the work.

---

## Step 1: Safety Preflight

Minimal — just enough to not lose work.

1. Run `git status` — if there are ANY uncommitted changes, commit immediately. Pickup is workstream-specific: stage only the paths belonging to the workstream you're resuming, never `git add -A` or `git add .`. The handoff doc you'll read in Step 2 declares the workstream scope in its `scope:` frontmatter — once read, prefer the helper with `--scope-from`:
   ```
   ~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-safe-commit --scope-from <handoff-doc-path> "pickup: <workstream> — resume"
   ```
   If the handoff isn't yet identified, stage the specific files explicitly by path:
   ```
   git add <path1> <path2> ...
   ~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-safe-commit "pickup safety commit"
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

## Step 2: Identify the Handoff

**If `$ARGUMENTS` contains a file path or link:**

The PM has pointed you at a specific handoff. Read it immediately and proceed to Step 3.

**If `$ARGUMENTS` is empty:**

1. Check `tasks/handoffs/` for `.md` files.

2. **If no handoffs exist:**
   _"No active handoffs in `tasks/handoffs/`. Nothing to pick up — use `/session-start` for general orientation."_
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
  <date> (<hostname>): <Scope field value> — <Plans touched: shipped entries, if any>
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
   Counters the default assumption that a handoff describes already-in-progress work.

5. **Frontmatter mutation in place** — `/pickup` mutates frontmatter only; archival happens at the successor moment (`/handoff` chain-archival or `/session-end` Step 2.7).

   ### Pre-mutation safety gates (sequential, all must pass before any write)

   1. **`git fetch origin <branch>` + re-read frontmatter.** Closes the cross-machine race window — if a peer already mutated and pushed, the fetch pulls their version and the next gate sees `consumed_by:` populated.
   2. **`consumed_by:` idempotency check.** If frontmatter shows `consumed_by:` non-empty after fetch, exit non-zero: _"Concurrent /pickup detected on `<file>` — already claimed by `<consumed_by>`. Inspect their session before proceeding."_
   3. **`cs_claim_handoff <basename>`.** Atomic mkdir gate per the concurrent-pickup spike. Exit non-zero on live concurrent claim. Call:
      ```bash
      source ~/.claude/plugins/coordinator-claude/coordinator/lib/coordinator-session.sh
      cs_claim_handoff "$(basename tasks/handoffs/<file>)"
      ```
   4. **`pickup_ready` absent → non-blocking warning.** If the handoff frontmatter does NOT contain `pickup_ready: true`, print once to the PM-facing channel:
      _"⚠ handoff `<basename>` lacks `pickup_ready: true` — proceeding anyway. (Author may not have explicitly authorized pickup; verify the workstream is yours to resume.)"_
      Do NOT prompt. Do NOT block. Continue to mutation.

   ### Frontmatter mutation (in place at `tasks/handoffs/<file>`)

   - `status: active` → `status: consumed`
   - `deployment_state: <whatever>` → `deployment_state: in_flight`
   - Append `consumed_at: <ISO UTC timestamp>`, `consumed_by: <session-id>` — resolve the session id with `$CLAUDE_SESSION_ID` first (if exported), falling back to `cat .git/coordinator-sessions/.current-session-id` (the sentinel written by `session-init.sh`). Never the machine name. Same resolution pattern as `/session-end` Step 2.7.
   - Do NOT remove `pickup_ready: true` if present — it stays as authorial-intent record on the consumed handoff.

   ### Commit

   Single explicit-path commit of the mutation only — **no `git mv`**:
   ```bash
   git add -- tasks/handoffs/<file>
   ~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-safe-commit \
     "pickup: <workstream> — frontmatter mutation"
   ```

   The handoff remains in `tasks/handoffs/`. Archival happens at one of two successor moments:
   - **`/handoff` chain-archival** — when this session writes a successor handoff, the explicit predecessor is moved to `archive/handoffs/`.
   - **`/session-end` Step 2.7** — when this session ends without a successor handoff, Step 2.7 archives any handoff whose `consumed_by:` matches this session.

6. **Begin executing the first item in "Recommended Next Steps."** If the handoff lists multiple next steps, execute them in order unless the PM redirects. If there's an "In-Progress Work" section describing something partially complete, resume that first — it takes priority over the recommended next steps list. The picking-up session's eventual `/handoff` or `/session-end` flips `deployment_state: in_flight` to `shipped` (with `shipped_in: <sha>`) or back to `ready_to_fire` if the work paused mid-stream and another session should resume it.

---

## Notes

- This command does NOT load action items, roadmaps, project trackers, or orientation caches. That's `/session-start` territory. Pickup is laser-focused on the handoff.
- If the handoff references a plan doc (`tasks/<feature>/todo.md`), read it — but only because the handoff pointed to it, not as a general survey.
- The handoff's "Key Decisions Made" section is context you should internalize — don't re-litigate those decisions unless you find evidence they were wrong.
- **Archiving:** `/pickup` mutates frontmatter in place at `tasks/handoffs/` and commits — it does NOT move the file. Archival is deferred to the picking-up session's terminal event: `/handoff` (chain-archival of the explicit predecessor) or `/session-end` Step 2.7 (archives any handoff whose `consumed_by:` matches this session). The `session-init.sh` boot-time sweep provides a safety net for orphaned consumed handoffs (session died before archival). Handoffs are never archived based on age alone.
- **Failure mode to avoid:** Executing items a concurrent session already shipped. The git log + plan status reconciliation in Step 3.4 is the gate — empirical baseline says 30–60% of inherited items are already closed. Skipping it means duplicate work, conflicts with landed commits, or spawned duplicate executors.
