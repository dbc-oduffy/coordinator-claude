---
description: Wrap up finished work — capture lessons, update docs
allowed-tools: ["Read", "Write", "Edit", "Grep", "Glob"]
argument-hint: "[optional context]"
---

# Session End — Wrap Up Completed Work

Close out a finished vein of work: capture lessons and update documentation to reflect completion. No handoff — this is for work that's *done*, not being passed forward.

## Instructions

When invoked, capture lessons and update plan/project documentation to reflect completion status. If work is incomplete and needs to be picked up later, use `/handoff` instead.

**Design note:** Multiple agents may be running concurrently. This skill closes out ONE agent's session without heavy repo-wide operations that could conflict with other agents.

### Step 0: Tier Usage Report

Before capturing lessons, emit the tier usage summary for this session. This closes the W3 telemetry loop — the PM sees whether the tiered-context-loading doctrine was followed.

```bash
# Resolve the current session's tier-usage JSON.
# Review: the Staff Engineer — prefer CLAUDE_SESSION_ID env var (if exported) over sentinel to avoid
# sentinel race with concurrent same-repo sessions; sentinel is fallback for when env var absent.
GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
SESSION_ID="${CLAUDE_SESSION_ID:-}"
if [[ -z "$SESSION_ID" && -n "$GIT_ROOT" && -f "${GIT_ROOT}/.git/coordinator-sessions/.current-session-id" ]]; then
  SESSION_ID=$(cat "${GIT_ROOT}/.git/coordinator-sessions/.current-session-id" 2>/dev/null)
fi

if [[ -z "$SESSION_ID" ]]; then
  echo "Tier usage: telemetry unavailable (no CLAUDE_SESSION_ID and no sentinel; session-init hook may not have run)"
else
  # session_id is unique across all projects, so search by session_id and accept the first hit.
  SESSION_JSON=$(find "${HOME}/.claude/projects" -name "${SESSION_ID}.json" -path "*/tier-usage/*" 2>/dev/null | head -1)
  if [[ -z "$SESSION_JSON" || ! -f "$SESSION_JSON" ]]; then
    echo "Tier usage: telemetry unavailable (no JSON for session ${SESSION_ID:0:8} — writer hook may not have fired)"
  else
    # Resolve Python via shared lib (python3 → python → py -3).
    LIB_PATH="${HOME}/.claude/plugins/coordinator-claude/coordinator/lib/resolve-python.sh"
    [[ -f "$LIB_PATH" ]] && source "$LIB_PATH"
    if [[ -z "$PYTHON_BIN" ]]; then
      if command -v py &>/dev/null && ! py -3 --version &>/dev/null; then
        echo "Tier usage: telemetry unavailable (py launcher present but no Python 3 registered — run \`py -0\` to list installed versions)"
      else
        echo "Tier usage: telemetry unavailable (no Python on PATH — tried python3, python, py -3)"
      fi
    else
      SESSION_JSON_PATH="$SESSION_JSON" "$PYTHON_BIN" "${PYTHON_ARGS[@]}" -c "
import json, os, sys
try:
    with open(os.environ['SESSION_JSON_PATH']) as f:
        data = json.load(f)
    c = data.get('counts', {})
    t4 = data.get('tier4_dispatches', [])
    missing = sum(1 for d in t4 if not d.get('rationale_present', True))
    print(f\"Tier usage this session: tier1={c.get('tier1',0)} tier2={c.get('tier2',0)} tier3={c.get('tier3',0)} tier4={c.get('tier4',0)} ({missing} tier-4 missing rationale)\")
except Exception as e:
    print(f'Tier usage: telemetry parse failed ({type(e).__name__}: {e})', file=sys.stderr)
    sys.exit(1)
"
    fi
  fi
fi
```

If telemetry is genuinely unavailable (no session sentinel, no JSON, no Python), Step 0 prints a one-line diagnostic — never empty.

### Step 1: Capture Lessons

Read `tasks/lessons.md` (if it exists). If anything was learned this session that isn't already captured, add it — but apply the intake filter first.

**Create on first use:** `tasks/lessons.md` is not scaffolded by `/project-onboarding` (it would be empty — no lessons exist on day 1). If lessons exist to capture AND the file does not exist yet, create it now using the template header:

```markdown
# Lessons — [Project Name]

Engineering patterns worth internalizing. Bold title + 1-2 sentence rule. Max 3 lines per entry.

<!-- This file is maintained by the EM. See CLAUDE.md § Self-Improvement Loop for conventions. -->
```

Then append the new entry. If there are no lessons to capture and the file doesn't exist, do not create it.

**Feature scope:** `<feature>` is derived from the current work context:
- If a feature-scoped plan exists at `tasks/<feature>/todo.md`, use that feature name
- If on a `feature/<name>` branch, use `<name>`
- Otherwise, use `tasks/lessons.md` (global)

**What qualifies:**
- Corrections from the user (preferences, workflow, conventions)
- Surprising API behavior or tooling gotchas
- Patterns that worked well or failed
- Debugging insights that would save future sessions time

**What doesn't qualify:** One-off bug fixes, details specific to a single script/pipeline run, or anything already encoded in the code, CLAUDE.md, or MEMORY.md. Before adding, ask: *"Will this save time in the next 4 weeks, or is it just documenting what happened?"*

Add new entries in the established format (bold title + 1-2 sentence rule, max 3 lines). Prefer merging with an existing entry over adding a new one. Skip if nothing new.

### Step 1.2: Lesson Classification

For each new lesson added in Step 1, ask the tier-1 question: **"If a different project type — UE / web / data / research — also used the coordinator pipeline, would this rule apply?"** This is autonomous self-classification; no separate review step is needed.

- **If yes (tier-1 / universal):** (a) tag the entry in `tasks/lessons.md` by appending `[universal]` on the same line as the bold title; (b) append a one-liner to the global queue at `~/.claude/tasks/coordinator-improvement-queue.md`:
  ```
  - YYYY-MM-DD | <source-repo> | <source-file>:<line> | <one-line summary> | proposed target: <coordinator file>
  ```
  Use the project repo name as `<source-repo>`, and `tasks/lessons.md:<line-number>` as `<source-file>:<line>`. If the same `<source-file>:<line>` already exists in the queue, skip — the queue is append-only and that pair is the dedup key.
- **If no (tier-2 / project-specific):** no action beyond the lesson already written.
- **If nothing new was added in Step 1:** skip this step entirely.

### Step 2: Update Plan Documentation

Find and update relevant plan/task documentation to reflect what was completed:

1. **Find the plan docs — actively search, don't wait to recall.** Check these locations in order:
   - Any plan document referenced or opened during this session (you have it in context)
   - `tasks/<feature>/todo.md` — feature-scoped plans for current work
   - `tasks/plans/` — session handoff plans and tactical trackers
   - `docs/plans/` — historical and reference plans
   - `~/.claude/plans/` — plans written in plan mode (may need copying to canonical location)
   - `tasks/todo.md`, `tasks/plan.md` — legacy flat locations
   If a plan exists for the work this session touched, read it and update it. Don't rely on having opened it earlier — sessions that start from handoffs or dive straight into code often never explicitly open the plan.
2. **Mark completed items:** Check off finished tasks, update status fields, add completion notes where appropriate.
3. **Add a review section** (if not already present) summarizing outcomes — what was built, key decisions, anything notable about the result.
4. **Update other pertinent docs:** If the work affected README files, architecture docs, or other project documentation that should reflect the new state, update those too. Use judgment — only touch docs that are clearly stale as a result of this session's work.

### Step 2.5: Doc-Alignment Insurance

End of session is the last chance to ensure status fields match reality. This catches work that completed but whose status wasn't updated — common after compaction or rapid context shifts.

1. **Check active chunk/stub docs:** If this session worked on chunk stubs (files with `**Status:**` fields in `docs/active/`, `docs/plans/`, or similar), verify their status reflects what actually happened:
   - If the work is complete but status says "in progress" → update to complete
   - If the work is blocked but status says "in progress" → update to blocked with reason
   - If the status is already correct, skip
2. **Check execution tracker:** If a tactical execution tracker exists (e.g., `docs/plans/consolidated-execution-tracker.md`), verify that chunks worked on this session have accurate status entries
3. **Lightweight pass only.** Read what's in your conversation context — don't re-read every file in the project. If you have no memory of working on tracked chunks, skip this step entirely.

### Step 2.6: Archive Uncaptured Work

Sweep the session's commits for completed work that isn't already in the project tracker (`docs/project-tracker.md`) or the completion archive (`archive/completed/YYYY-MM.md`). This catches bug fixes, ad-hoc requests, and quick tasks that bypassed the spec pipeline.

1. **Scan session commits:** `git log --oneline` for commits since the session started (or since the last `/session-end`/`/update-docs`)
2. **Check against tracker + archive:** For each substantive commit (skip merge commits, doc-only commits, quick-saves), check if the work is already represented in either the tracker or the current month's archive
3. **Append missing entries:** For any untracked completed work, append to `archive/completed/YYYY-MM.md`:
   ```
   ## YYYY-MM-DD
   - **[Concise past-tense description]** — ad-hoc [bug fix|task|refactor] | commit: [hash]
   ```
4. **Judgment filter:** Not every commit is a work item. Group related commits into a single archive entry. Skip trivial commits (typo fixes, formatting). The archive records *what shipped*, not every keystroke.

**Skip if** no `archive/` directory exists and no `docs/project-tracker.md` exists — the project hasn't adopted unified tracking yet.

### Step 2.7: Archive Predecessor Handoff (if applicable)

When this session was opened with `/pickup`, the consumed handoff still lives in `tasks/handoffs/` (mutation-only at pickup time). If this session is ending via `/session-end` rather than `/handoff`, archive the predecessor now.

**Detection:** scan `tasks/handoffs/*.md`. For each file, read its frontmatter `consumed_by:` field.

- Resolve this session's id: `$CLAUDE_SESSION_ID` env var first; sentinel fallback at `.git/coordinator-sessions/.current-session-id` only when env var is empty.
- Zero matches → skip silently.
- One match → archive it (see Action below).
- More than one match → log to stderr and archive all. (A session that legitimately consumed multiple predecessors is rare but not invalid — no fail-loud.)

**Action:** `git mv tasks/handoffs/<file> archive/handoffs/<file>`. Create `archive/handoffs/` if it does not exist. On `git mv` failure (file already moved by a concurrent `/handoff` chain-archival), log to stderr and continue — idempotent treatment of already-moved files.

The move folds into the existing session-end commit at Step 3 — no separate commit for this step.

**No claim release call needed here.** `cs_archive` at Step 3.5 carries the entire session directory (including `handoff-claims/`) into `.archive/`. The claim is released structurally.

**Skip entirely if** this session is exiting via `/handoff` — `/handoff` chain-archival owns that path. `/session-end` and `/handoff` are mutually exclusive session-exit paths.

### Step 2.8: Refresh Orientation Documents

Update the documents that future sessions read for orientation — closing the read-write loop with `/session-start` and `/workday-start`. These are lightweight, targeted patches based on what THIS session accomplished, not a full regeneration.

1. **Orientation cache** (`tasks/orientation_cache.md`): If it exists, patch sections affected by this session's work:
   - Update `Active Workstreams` if workstreams completed or progressed
   - Update `Health Snapshot` if bugs were fixed, debt resolved, or issues closed
   - Update `Doc Freshness` — set `git_head_at_generation` to current HEAD, update last-run dates for any commands invoked this session
   - Don't regenerate from scratch — that's `/workday-start`'s job. Patch what changed.
   - If the cache doesn't exist, skip — the project hasn't run `/workday-start` yet.
   - **Do not claim the cache is absent based on intuition.** If the SessionStart orientation hook failed to inject output (a known past failure mode), you may have no in-context evidence of the cache. Before asserting "no orientation cache in this repo," run `ls tasks/orientation_cache.md` and read the result. Assertions about existence require a verification step, not a recollection.
   - **Stale is not a skip condition — it's a refresh trigger.** If `generated_at` is older than today, or `git_head_at_generation` doesn't match current HEAD, or the SessionStart hook flagged the cache as stale, do a full refresh (re-derive Active Workstreams, Health Snapshot, Recent Work, Doc Freshness from current repo state) before concluding session-end. Leaving a stale cache in place means the next session boots on misleading orientation. The process owns freshness.

2. **Project tracker** (`docs/project-tracker.md`): If it exists and this session completed or progressed tracked items, update their status rows. Only touch rows this session affected — don't re-derive the whole tracker.

3. **Action items** (first match: `ACTION-ITEMS.md`, `docs/active/ACTION-ITEMS.md`, `docs/ACTION-ITEMS.md`): If one exists and this session resolved any listed items, check them off or remove them per the file's existing conventions.

4. **Documentation index** (`docs/README.md`): If it exists and this session created new guides, added research files, or completed plan documents, patch the relevant table. Only touch rows this session affected.

**Concurrency note:** These are targeted patches to specific rows/sections based on this session's work — safe with concurrent agents, as long as agents work on different items (which they should by design).

### Step 2.9: Code Review Consideration

Assess whether this session's diff warrants a code review pass before committing. EM makes the call using the table below — this step is judgment, not ceremony.

**Diff-shape table:**

| Session shape | Default scale |
|---|---|
| Doc-only edits, lesson capture, no executor dispatched, no code touched | **None** |
| Single-file fix <50 LOC, no shared schema touched, no executor | **None** (but commit message names the change) |
| Any executor dispatched, OR >50 LOC code change, OR shared schema/seam touched | **Sonnet** (review-code Branch A.2 single reviewer) |
| Chain-end (started with `/pickup`, ending without `/handoff`/`/spinoff`) AND chain diff is non-trivial | **Sonnet** on chain diff (default) |
| Chain-end AND any of: chain diff >500 LOC, touches public API / schema / security-adjacent code, ≥3 segments in chain, novel external API integration | **Sonnet + the Staff Engineer** (EM-judged escalation) |

**Precedence rule:** chain-end rows (4, 5) override session-end rows (1, 2, 3) when both apply — the chain diff is the integration-risk artifact.

**Anchored-ranges note:** the numeric anchors (50 LOC, 500 LOC, ≥3 segments) are decision anchors, not hard thresholds. An EM seeing a 51-LOC change with a clean shape should not feel obliged to escalate; an EM seeing a 49-LOC change touching a public schema seam should not feel released from review.

**Anti-ceremony-bias tripwire:**
> "If you're considering Sonnet-only because escalation feels like ceremony rather than because the diff is genuinely shallow — escalate. The Staff Engineer is one dispatch away; the cost of redundant review is one Opus call. The cost of unreviewed integration risk shipping to main is hours of debugging."

**Symmetric anti-ceremony tripwire (row 3+):**
> "Plan-time review and post-implementation review catch different defect classes — complementary, not substitutional. Mechanical executor gates (grep/pytest/`bash -n`) are correctness floors, not review lenses. The anti-ceremony tripwire fires symmetrically: 'Sonnet-after-already-doing-review feels like ceremony, skip' is the same motion as 'Sonnet feels like ceremony, escalate' — running in reverse. 'We've done a lot of review already' is the shape wrap-up pressure takes at session-end. If you're drafting a waiving-with-rationale sentence on a row-3+ session, the rationale is the tell. EM keeps waive authority on genuinely shallow row-3 diffs; the test is the four-point shape above, not the row number. See `docs/wiki/session-end-review.md` § why-post-implementation-review-is-not-redundant for the worked example."

**Chain-end detection:**
- Resolve session-id: `CLAUDE_SESSION_ID` env var first; sentinel fallback at `.git/coordinator-sessions/.current-session-id` only when env var is empty.
- Chain-end signal: session opened via `/pickup` AND ending without `/handoff` or `/spinoff` invocation this session.
- **Additional escalation signal:** if `/handoff` Step 0's NO-test gate previously fired and routed the session to `/session-end`, the session is shipped/complete — that's a strong escalation signal toward Sonnet+the Staff Engineer.

**Diff scope:**
- Chain-end → `git log $(git merge-base origin/main HEAD)..HEAD`
- Mid-chain → `git log $LAST_REVIEW_SHA..HEAD` (where `$LAST_REVIEW_SHA` is the `sha_range` head from the most recent trail record, or session-start SHA if no prior review exists)

**Dispatch:** invoke `coordinator:review-code` Branch A.2 with the resolved diff scope.

**Marker write:** after review integration completes, invoke:
```bash
~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-write-review-trail.sh \
  --sha-range <A..B> --reviewer <sonnet|patrik|sonnet+patrik> \
  --scope <chain|session> --verdict <ok|warn|blocked> --diff-loc <N>
```

**Negative-spec:**
- Trivial sessions (Row 1, 2 of the table): skip the review entirely. No trail record written.
- PM-waived sessions: log waiver to trail with `--reviewer waived --verdict waived`. Greppable as `verdict=waived`.

**Staging discipline:**
> "Any files edited by `coordinator:review-integrator` during this step must be staged via explicit path in Step 3, not absorbed by a post-integration `git add -A`. This preserves the existing concurrent-EM safety property of Step 3."

### Step 3: Commit + Verify Remote

1. **Stage only paths this session touched — never `git add -A`.** With concurrent EMs active on the same branch, `git add -A` sweeps up another session's staged/modified files and silently re-attributes them. Instead:
   - Make a mental (or explicit) list of the files you edited during Steps 1/2/2.5/2.6/2.7 (typically a small set: `tasks/lessons.md`, `archive/completed/YYYY-MM.md`, `docs/project-tracker.md`, action-items file, `docs/README.md`).
   - `git add <path1> <path2> ...` — name each path explicitly.
   - If you also edited files earlier in the session that are still unstaged, stage those by path too — but only ones you know you authored this session.
   - If `git status` shows unfamiliar unstaged files you didn't touch, **leave them alone** — they belong to a concurrent session.
2. Commit with a lightweight message: `"session-end quick-save"`. (The post-commit hook will auto-push on work/feature branches.)
3. If nothing to commit, check for unpushed commits: `git log "origin/$(~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-current-branch)..HEAD" 2>/dev/null`
4. **Verify remote is synced:** confirm no unpushed commits remain. If auto-push failed, push explicitly and warn the PM.
5. If on main (shouldn't happen, but safety): push explicitly — `git push origin main`
6. If push fails (auth, network, conflicts), **warn the PM explicitly** — this is a critical failure

### Step 3.5: Archive Session Claim

Now that the final commit has landed and pushed, archive this session's claim directory so concurrent sessions don't see stale claims accumulating until the 24h reaper fires. `/session-end` is one of two session-exit pathways (the other being `/handoff`); both must clean up claims, otherwise sessions that wind down via `/session-end` leak claims that force the next concurrent EM into a 24h wait, `COORDINATOR_OVERRIDE_SCOPE=1`, or hand-archival.

Run:
```bash
sid=$(cat "$(git rev-parse --show-toplevel)/.git/coordinator-sessions/.current-session-id" 2>/dev/null) && \
  source ~/.claude/plugins/coordinator-claude/coordinator/lib/coordinator-session.sh 2>/dev/null && \
  cs_archive "$sid" 2>/dev/null || true
```

Idempotent — already-archived sessions return 0 silently (verified: a session archived by `/handoff` and re-archived here is a no-op). Failures are non-fatal (the 24h reaper is the safety net). Skip silently if the sentinel is missing or the lib is unavailable.

**Note on session_id source:** The sentinel is "last writer wins" across concurrent sessions. If `CLAUDE_SESSION_ID` is exported in your environment, prefer it over the sentinel — that's the session that actually owns this exit.

### Step 4: Final Summary

Present a brief end-of-session summary:
```
## Session Complete

**Work done:** [1-2 sentence summary]
**Lessons captured:** [N new / none]
**Work archived:** [N items added to archive/completed/YYYY-MM.md / none needed / project not using unified tracking]
**Docs updated:** [list of updated files]
**Orientation refreshed:** [orientation cache patched / tracker updated / action items checked off / nothing to update / no orientation docs exist]
**Pushed to remote:** [yes — branch name / no — reason]
```

**Flag to PM:** Explicitly note the push so they can verify nothing breaks for other consumers.

**Reminder:** Run `/update-docs` periodically for repo-wide documentation maintenance — it doesn't need to happen every session.

If `$ARGUMENTS` is provided, use it as context for what was accomplished this session.
