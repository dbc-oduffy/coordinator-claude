# Plan: Fix executor-touched-files invisibility + executor-commit branch drift

## Context

Two live failure modes in the coordinator commit/dispatch pipeline keep biting us, and the current "workarounds" are PM-load: a follow-up explicit-path commit after every executor dispatch, and a manual branch poll between waves. PM flagged these today and asked for structural fixes, not backlog entries.

**Issue A — Executor-edited files are invisible to `coordinator-safe-commit --scope-from`.**
Dispatched executor agents run as separate sessions with their own `session_id`. The PostToolUse hook (`hooks/scripts/track-touched-files.sh`) writes their edits to `.git/coordinator-sessions/<executor-session-id>/touched.txt`, not the parent EM's. When the EM later runs `coordinator-safe-commit --scope-from`, it reads only the EM's own `touched.txt` (lines 390/508 of helper) and unions it with handoff frontmatter — executor-edited files appear orphan. The cross-session subtraction logic (lines 404–429) then treats them as "owned by session X," excluding them. Documented workaround: explicit-path commit after every executor-ending dispatch. That's PM tax. Mechanism is confirmed by reading `coordinator-safe-commit` and `track-touched-files.sh`.

**Issue B — Executor commits sometimes land on a different branch than the EM intended.**
Observed today: PM created `feature/cross-consumer-standalone-decoupling`, dispatched three Wave 1 executors, their commits landed on `work/Striker/2026-05-05` (daily branch). The originally hypothesized mechanism — "executor session-start orientation flips branches" — is **not present in the code**: `SessionStart` hook does not `git checkout`, executor agent definition does not auto-invoke `/workday-start`, and the only `git checkout work/{machine}/{date}` site is `/workday-start`'s pipeline. So the actual mechanism is unconfirmed. Most plausible: tree was on the daily branch at dispatch (EM dispatched without branch-pin verification), or a sibling session checked out the daily branch in the shared tree mid-dispatch. Regardless of root cause, the EM has no pre-commit gate to catch wrong-branch executor commits.

The plan is sequenced so unverified premises are settled by a probe before code is written, and the deterministic guard (helper flag) is framed as the load-bearing piece for Issue B with doctrine + dispatch convention as supporting input.

---

## Step 0 (gating, before any code lands): plumbing + mechanism probe

Patrik review identified that two factual premises were unverified and that the platform-gotchas wiki was cited for a claim it does not make. Probe both before approving Options below.

### Probe 0.1 — Subagent → parent plumbing (gates Issue A)

Dispatch a trivial executor whose first action is to:

1. Write `env | grep -i claude` to `tmp/probe-env.txt`.
2. Read its own PostToolUse JSON payload (the hook can `tee` stdin to `tmp/probe-postuse.json` on first fire) and surface the schema. Specifically check for: `parent_session_id`, `parentSessionId`, `parent.session_id`, or any field naming a parent.
3. Print the value of `CLAUDE_SESSION_ID` and report whether it equals the *parent's* session id or its own.

Outcomes:

- **If PostToolUse JSON carries a parent session id:** Option 1 plumbing is two lines in `track-touched-files.sh` — read it from the JSON, append to the parent's touched.txt.
- **If `CLAUDE_SESSION_ID` is in the executor's env and equals the parent's session id:** the env-var fallback works. Same pattern, read from env.
- **If neither:** Option 1 has to redesign. Most likely path: the EM injects `parent_session_id: <id>` into the dispatch prompt and the executor's first action writes `parent.txt` from the prompt-supplied value. That moves the "~15 lines" estimate to "~50 lines + dispatch-prompt convention" and makes Option 1 an EM-bookkeeping shape that's no longer obviously better than rejected Option 2. Re-plan in that case.

### Probe 0.2 — Today's incident reflog (gates Issue B mechanism)

Dispatch a Sonnet `general-purpose` scout (~10 min) to:

1. Read `git reflog` for `feature/cross-consumer-standalone-decoupling` and `work/Striker/2026-05-05` from today.
2. Determine the exact `git checkout` sequence and what process did each.
3. Grep coordinator-claude hooks/skills/bin/ for any path that runs `git checkout`, `git switch`, or HEAD-mutating ops; check `coordinator-auto-push` specifically.
4. Verify whether `SessionStart` hook fires for subagent dispatches at all. (This also affects where Issue A's parent-capture lives — see Finding 5 below.)
5. Return a one-paragraph mechanism statement + file:line evidence.

If mechanism is "EM was already on wrong branch at dispatch": Issue B fix below is sufficient.
If mechanism is "code path X switches branches": fix the code path; Issue B fix is still defense in depth.

**Both probes block approval for the corresponding fix.** A doesn't ship until 0.1 closes; B doesn't ship until 0.2 closes.

---

## Issue A: Executor touched.txt visibility

**Approach: parent-aware touched-files write — shape determined by Probe 0.1.**

Two variants below; the probe determines which is feasible. Plan recommends Option 1 *if* the probe shows clean plumbing exists; otherwise reconsider.

### Option 1 (recommended IF Probe 0.1 succeeds): Executor sessions write to BOTH their own touched.txt AND their parent's

When `track-touched-files.sh` fires for a session that has a parent, it appends the file path to both `.../<my-session-id>/touched.txt` and `.../<parent-session-id>/touched.txt`. The helper requires no changes — `--scope-from` keeps reading only the EM's touched.txt and just sees more entries.

Cross-session "owned by session X" detection still works: an executor that happened to also touch a file the EM is committing won't trigger ownership conflict because both sessions are claiming it via the parent's touched.txt; the EM's union absorbs it.

**Cross-repo guard (per Patrik Finding 1).** Executors routinely cross repos (`~/.claude` ↔ project repos). Without a guard, the hook in the executor's repo could write into a non-existent / wrong parent dir.

Design: at parent-capture time, write `parent.txt` as `<parent_session_id>:<parent_git_root_abspath>`. In `track-touched-files.sh`, before appending to parent's touched.txt, check `[[ "$(realpath "$GIT_ROOT")" == "$(realpath "$parent_git_root")" ]]`. Mismatch → skip the parent-write; executor's own touched.txt still gets the entry.

**Where parent-capture lives (per Patrik Finding 5).** Probe 0.2 step 4 answers: does `SessionStart` fire for subagent dispatches?
- If **yes**: capture parent in `lib/coordinator-session.sh`'s `cs_init` (lines 171–180) — the canonical session-init path. Note that `cs_init` is invoked from BOTH `session-init.sh` and `track-touched-files.sh:92–108` (slow-path fallback), so the capture logic lives inside `cs_init` itself, not at one call site.
- If **no**: capture lives in `track-touched-files.sh`'s first-touch slow path (lines 92–108) — the only place that fires for subagent edits.

### Option 2 (rejected): `--include-executor-touched <session-id>` flag on the helper

EM passes child session ids when calling `coordinator-safe-commit`. Rejected because the EM doesn't reliably know its dispatched children's session ids — `Agent` returns an `agentId` but not a `session_id`, and there's no doctrine surface that captures children. Reconsider only if Probe 0.1 shows Option 1's plumbing is unworkable.

### Files touched

- `plugins/coordinator-claude/coordinator/hooks/scripts/track-touched-files.sh` — detect parent session, cross-repo guard, write to parent's touched.txt as well as own. ~25 lines (was estimated 15 before cross-repo design).
- `plugins/coordinator-claude/coordinator/lib/coordinator-session.sh` — `cs_init` writes `parent.txt` as `<id>:<git_root>` from the source identified by Probe 0.1.
- `tasks/coordinator-improvement-queue.md` line 113 — strike entry, replace with one-line "fixed by plan <date>" pointer (or remove if `/lesson-triage` will sweep).
- `coordinator/CLAUDE.md` — strike "After every executor-ending dispatch, follow with explicit-path commit" rule **in a separate, second commit** after one verification session passes (Patrik Finding 6).

### Verification

- Spawn an executor that writes a file. Confirm both `.../<executor-id>/touched.txt` and `.../<em-id>/touched.txt` contain the path.
- Run `coordinator-safe-commit --scope-from <handoff>` after executor returns. Confirm executor-edited file is in staged scope without explicit path.
- **Cross-repo test:** executor in a different repo (different `.git` root). Confirm parent's touched.txt does NOT receive the entry; executor's own touched.txt does.
- **Cross-repo phantom-dir test:** confirm no phantom session-id dir is created in the executor's repo for the parent.
- Concurrency: two executors dispatched in parallel — both writes land in EM's touched.txt. Duplicate entries are benign; `coordinator-safe-commit:398–401` candidate_map dedups them. Note in test report (Patrik Finding 7).

### Coupling acknowledgement (per Patrik Finding 2)

Option 1 introduces a **second sentinel-read** on the PostToolUse hot path (reading `parent.txt` per fire). This couples to the parked "session-id sentinel last-writer-wins" concurrency issue: when that rework eventually ships, both call sites — the existing session-id read and this new parent read — must be addressed together. Documented here so the next person rebasing the sentinel-rework plan sees the dependency.

---

## Issue B: Executor commits landing on wrong branch

**Approach: helper-level `--expected-branch` flag is the load-bearing deterministic gate. Doctrine + dispatch convention feed it.**

Patrik Finding 3 corrected my earlier framing. Executors are LLM agents, not deterministic processes — a doctrine line "before any git commit, run git branch --show-current" is the class of instruction that gets dropped under context pressure. Only the bash helper fails closed.

Reframed in priority order:

### Primary: helper-level `--expected-branch` flag (deterministic)

`coordinator-safe-commit` gains an optional `--expected-branch <name>` flag. When present, the helper checks `git branch --show-current` against the value **before staging anything**. Mismatch → abort with a remediation message printing current branch, expected branch, and `git reflog -3` for both. No staging, no commit, no recovery cost beyond `git checkout`. This piece cannot be forgotten by the agent — if the executor invokes the helper at all, the gate fires.

Plumbs into existing flag-parsing block (lines 43–90).

### Supporting: EM dispatch-prompt convention (input)

Doctrine line in `coordinator/CLAUDE.md` § "Concurrent-EM Git Operations": when dispatching an executor that will commit, the dispatch prompt includes `expected_branch: <current>`. The EM captures `git branch --show-current` at dispatch time and passes the value through the prompt.

This is the only piece that can't be enforced — it's a request to the EM-as-author. Doctrine + a `dispatching-parallel-agents` SKILL.md update + a one-liner in `executor.md`'s standing orders covers the surface.

### Supporting: executor.md standing order (clarity)

`agents/executor.md` gains: "If your dispatch prompt includes `expected_branch: <name>`, pass `--expected-branch <name>` to every `coordinator-safe-commit` invocation." This makes the connection explicit but is NOT the load-bearing piece — the helper flag's deterministic abort is.

### Files touched

- `plugins/coordinator-claude/coordinator/bin/coordinator-safe-commit` — add `--expected-branch` flag, mismatch abort. ~15 lines, plumbs into flag-parsing block (lines 43–90).
- `coordinator/CLAUDE.md` § "Concurrent-EM Git Operations" — add dispatch convention.
- `coordinator/skills/dispatching-parallel-agents/SKILL.md` — same convention with example.
- `plugins/coordinator-claude/coordinator/agents/executor.md` — pass-through standing order. ~3 lines.
- `tasks/coordinator-improvement-queue.md` line 153 — update entry to reference this plan.

### Verification

- `coordinator-safe-commit --expected-branch feature/test-fix` while tree is on `feature/test-fix`: succeeds.
- `coordinator-safe-commit --expected-branch feature/test-fix` while tree is on `work/host/2026-05-05`: aborts before staging, prints remediation.
- Manually `git checkout` to a different branch mid-dispatch (simulate sibling-session flip) and have an executor invoke the helper: helper aborts.
- Today's incident replayed in a sandbox: with the new flag in dispatch prompts, would have caught the wrong-branch commits before they landed.
- If Probe 0.2 finds a code-level branch-switch bug: separate fix for that root cause; helper flag remains as defense in depth.

---

## Sequencing

1. **Step 0 probes (this session, post-approval):** dispatch both probes. ~15 minutes total. Both probes are read-only / sandbox-side; safe to run in parallel.
2. **After Probe 0.1 returns:** ship Issue A using whichever plumbing the probe revealed. Self-contained, low risk once plumbing is grounded.
3. **After Probe 0.2 returns:** ship Issue B helper flag + doctrine. If probe found a code-level branch-switch root cause, fix that in the same commit.
4. **Both fixes ship as commits on the current feature branch.** A and B can be one PR; small enough.
5. **Doctrine sweep last (separate commit, after one verification session, per Patrik Finding 6):** strike obsolete workarounds in `coordinator/CLAUDE.md` and improvement queue. Until that strike, the existing "follow-up explicit-path commit" rule stays in place as a safety net.

## Out of scope

- General `--include-executor-touched <id>` flag (Option 2 above; reconsider only if Probe 0.1 collapses Option 1).
- Refactoring the session-id sentinel to fix the "last writer wins" concurrency issue. **Note coupling: Option 1 adds a second sentinel-read on the same hot path; the eventual rework must address both call sites.** (Patrik Finding 2.)
- 24h reaper / dead-PID handling (Issue 10 in PM's failure-mode list).
- mtime-fallback branch-switch ambiguity (Issue 7).
- Async PostToolUse race (Issue 5, already fixed).

## Critical files (modify)

- `plugins/coordinator-claude/coordinator/hooks/scripts/track-touched-files.sh`
- `plugins/coordinator-claude/coordinator/lib/coordinator-session.sh` (`cs_init`, lines 171–180)
- `plugins/coordinator-claude/coordinator/bin/coordinator-safe-commit` (flag block lines 43–90)
- `plugins/coordinator-claude/coordinator/agents/executor.md`
- `plugins/coordinator-claude/coordinator/CLAUDE.md`
- `plugins/coordinator-claude/coordinator/skills/dispatching-parallel-agents/SKILL.md`
- `tasks/coordinator-improvement-queue.md`

## Critical files (read for grounding during implementation)

- `plugins/coordinator-claude/coordinator/bin/coordinator-safe-commit:112–171` (session-id resolution)
- `plugins/coordinator-claude/coordinator/bin/coordinator-safe-commit:347–452` (--scope-from logic)
- `plugins/coordinator-claude/coordinator/bin/coordinator-safe-commit:404–429` (cross-session subtraction)
- `plugins/coordinator-claude/coordinator/hooks/scripts/track-touched-files.sh:64–87` (session-id + path)
- `plugins/coordinator-claude/coordinator/hooks/scripts/track-touched-files.sh:92–108` (slow-path / fallback cs_init invocation)
- `plugins/coordinator-claude/coordinator/lib/coordinator-session.sh:171–180` (cs_init meta.json write)
- `plugins/coordinator-claude/coordinator/pipelines/workday-start-internals.md:6–26` (only known checkout site in tree)
- `docs/wiki/claude-code-platform-gotchas.md` § session_id reach (NOTE: documents that `CLAUDE_SESSION_ID` is NOT in EM subprocess env — Probe 0.1 must establish what subagents actually receive; do not rely on this wiki claiming env inheritance, it does not)
