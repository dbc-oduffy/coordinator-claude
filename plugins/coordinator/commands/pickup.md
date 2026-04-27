---
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

1. Run `git status` — if there are ANY uncommitted changes, commit immediately:
   ```
   git add -A && git commit -m "pickup safety commit"
   ```

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

5. **Report briefly — two lines max:**
   ```
   Picked up: {handoff heading}
   Branch: {branch} | Next: {first recommended step, abbreviated}
   ```

5. **Mark as consumed:** Append a consumed marker to the handoff file so `handoff-archival` knows it's been picked up:
   ```bash
   echo "" >> <handoff-file>
   echo "<!-- consumed: $(date +%Y-%m-%d) -->" >> <handoff-file>
   ```
   This is the signal that triggers archival on the next `/update-docs` run. The handoff stays in `tasks/handoffs/` for the duration of this session (in case you need to re-read it), but it's now marked for cleanup.

6. **Begin executing the first item in "Recommended Next Steps."** If the handoff lists multiple next steps, execute them in order unless the PM redirects. If there's an "In-Progress Work" section describing something partially complete, resume that first — it takes priority over the recommended next steps list.

---

## Notes

- This command does NOT load action items, roadmaps, project trackers, or orientation caches. That's `/session-start` territory. Pickup is laser-focused on the handoff.
- If the handoff references a plan doc (`tasks/<feature>/todo.md`), read it — but only because the handoff pointed to it, not as a general survey.
- The handoff's "Key Decisions Made" section is context you should internalize — don't re-litigate those decisions unless you find evidence they were wrong.
- **Archiving:** The consumed marker (Step 5) signals that this handoff has been picked up. It will be archived on the next `/update-docs` run. Handoffs are never archived based on age alone — only when consumed via pickup, superseded by a successor, or when the PM explicitly directs it.
- **Failure mode to avoid:** Executing items a concurrent session already shipped. The git log + plan status reconciliation in Step 3.4 is the gate — empirical baseline says 30–60% of inherited items are already closed. Skipping it means duplicate work, conflicts with landed commits, or spawned duplicate executors.
