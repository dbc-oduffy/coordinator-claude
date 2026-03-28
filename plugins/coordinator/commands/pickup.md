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

4. **Report briefly — two lines max:**
   ```
   Picked up: {handoff heading}
   Branch: {branch} | Next: {first recommended step, abbreviated}
   ```

5. **Begin executing the first item in "Recommended Next Steps."** If the handoff lists multiple next steps, execute them in order unless the PM redirects. If there's an "In-Progress Work" section describing something partially complete, resume that first — it takes priority over the recommended next steps list.

---

## Notes

- This command does NOT load action items, roadmaps, project trackers, or orientation caches. That's `/session-start` territory. Pickup is laser-focused on the handoff.
- If the handoff references a plan doc (`tasks/<feature>/todo.md`), read it — but only because the handoff pointed to it, not as a general survey.
- The handoff's "Key Decisions Made" section is context you should internalize — don't re-litigate those decisions unless you find evidence they were wrong.
- **Archiving:** Do NOT archive the handoff you just picked up. It stays in `tasks/handoffs/` until `/update-docs` archives it on its 48-hour sweep, or until this session writes a successor handoff via `/handoff`.
