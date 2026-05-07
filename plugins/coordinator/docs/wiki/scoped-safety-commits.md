# Scoped Safety Commits

**System:** coordinator  
**Last Updated:** 2026-04-27  
**Related plan:** `~/.claude/plans/scoped-safety-commits.md`

---

## Why This Exists

Quick-save commits used blanket staging (`git add -A`) for years — fine for solo sessions, an audit-trail lie the moment two sessions run concurrently. The failure mode is asymmetric and invisible: Session A's safety commit subject says "stub(W2): apply PM decisions" but `git add -A` also hoovers up Session B's unstaged install-consolidation edits. `git log` is now useless as an audit surface — subject describes one workstream, diff contains another. **Doctrine cannot fix an asymmetric risk** (it happened 4 times in a single session pair before the structural fix); a disciplined Session A is still polluted when concurrent Session B runs `git add -A`. The fix is structural on two surfaces: each session tracks what it touched and commits only that, and the 27 files prescribing `git add -A` migrate to a scoped commit helper.

---

## The Structural Fix — Components

### 1. Touch-Tracker Hook (PostToolUse)

A PostToolUse hook fires on `Write|Edit|MultiEdit|NotebookEdit` only. Every time one of these tools runs, the hook extracts `tool_input.file_path`, normalizes it to repo-relative, and appends it (deduped) to:

```
.git/coordinator-sessions/<session-id>/touched.txt
```

The session directory is created on first touch (or at `/session-start`). It also contains:

```
.git/coordinator-sessions/
├── <session-id>/
│   ├── started_at          # ISO timestamp
│   ├── head_at_start       # SHA at session start
│   ├── touched.txt         # one path per line, append-only
│   └── meta.json           # session goal, branch, last-activity, PID
```

**Bash tool calls are not tracked by the hook.** Parsing arbitrary shell for write effects is unsound — heredocs, xargs, redirections in subshells, scripts invoking scripts. The mtime fallback (Component 2) is the sole detector for Bash-driven edits. This is intentional; the hook does not maintain a regex catalog of Bash write patterns.

### 2. mtime Fallback at Commit Time

At commit time, the helper includes any currently dirty file whose mtime is after `started_at` — but only after cross-session set-subtraction (Component 3). This catches Bash-driven edits the hook missed (build outputs, scripted rewrites, generated files). mtime is additive input to scope computation, not a direct staging list — a file is included from mtime only if no other active session's `touched.txt` claims it.

### 3. Scoped Commit Helper (`coordinator-safe-commit`)

Replaces `git add -A && git commit -m "..."` patterns. Located at:

```
~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-safe-commit
```

**Scope computation:**

```
MY_SCOPE = (touched.txt ∪ mtime_dirty_since_started_at) − ⋃(other_active_sessions.touched.txt)
```

The helper:
- Runs `git add -- <MY_SCOPE>` (explicit pathspec, only this session's files)
- Commits with the provided subject
- **Orphan policy:** A file is dirty, no session claims it, mtime > `started_at` → warn: "orphan dirty paths: X, Y — not staged; commit explicitly if yours." Does NOT auto-stage orphans.
- If paths are claimed by another active session's `touched.txt`, logs "skipping X — owned by session B" and continues.

**`--blanket` enforcement:** The `--blanket` flag is only accepted from `/session-start` or `/workday-complete`. Enforcement via `$CLAUDE_INVOKING_COMMAND` env var (set by those commands when invoking the helper). Any other caller gets:

> "`--blanket` is only valid from /session-start or /workday-complete. Use scoped staging or `COORDINATOR_OVERRIDE_SCOPE=1` for emergencies."

This prevents `--blanket` from becoming `git add -A` by another name.

### 4. Bash-PreToolUse Scope Guard (extends `validate-commit.sh`)

Before any `git commit` Bash call, the guard reads `MY_SCOPE` and the staged file set. If staged ⊄ MY_SCOPE, it emits a warning naming the foreign files and the likely owning session.

**This is distinct from git's `.git/hooks/pre-commit`.** The Bash-PreToolUse scope guard fires when Claude Code is about to run a Bash call that starts with `git commit` — it intercepts at the tool-use level, before the shell command runs. Git's pre-commit hook fires inside the git process, after the shell command starts. Different surfaces, different blocking semantics. Both can be active simultaneously; the Bash-PreToolUse guard is the coordinator's layer.

During rollout: warn-only. Strict (blocking) mode is activated via `COORDINATOR_SCOPE_STRICT=1` env var after the flip predicate is met (see Phase 5 section below).

### 5. Workstream-Anchored Scope (Handoff/Pickup)

`/handoff` and `/pickup` are workstream-specific. At pickup time the resuming session hasn't touched anything yet, so the touch list is empty. Solution: handoff docs declare scope in frontmatter using **git pathspec syntax** — the same syntax `git add` understands.

```yaml
# tasks/handoffs/<workstream>/handoff.md frontmatter
workstream: scoped-safety-commits
scope:
  - plugins/coordinator-claude/**
  - docs/plans/scoped-safety-commits.md
  - tasks/handoffs/scoped-safety-commits/**
```

The `scope:` values are `git pathspec` expressions (supports `**` globstar, `!negation`, `:(glob)` prefix). The helper validates pathspecs at parse time and rejects malformed expressions before attempting staging.

### 6. Agent Prompt Self-Containment

Executor (`executor.md`) and all reviewer/planner agents carry their own "Commit Discipline / Do Not Commit" prose. Subagents see only their dispatch prompt — project CLAUDE.md is invisible to them. This means the rule must be embedded in the prompt itself, not assumed from context.

### 7. Agent-ID Linkage (Issue A — shipped 2026-05-06)

The original touch-tracker linked file edits to the **dispatching session** via the `CLAUDE_SESSION_ID` sentinel. Probing exposed two flaws: (1) subagents have no `parent_session_id` in their PostToolUse JSON, so the hook could not associate a subagent's edits with the EM that dispatched it; (2) sibling SessionStart events overwrite the last-writer-wins sentinel, so the resolved session id can drift mid-flight.

The fix uses `agentId` (durable, opaque, mechanical — `^[a-f0-9]{12,}$`, lowercase hex, 12+ chars per Probe 0.3) as the linkage key. Two mechanical writers, no executor cooperation, no LLM-driven recording, no env vars:

**EM-side hook** — `track-dispatched-agents.sh` (PostToolUse on the `Agent` tool). Reads `tool_response.agentId` (camelCase) and writes:
```
.git/coordinator-sessions/<em-sid>/dispatched-agents.txt   # list of agentIds
.git/coordinator-sessions/.agents/<agentId>/em-session-id.txt   # back-pointer
```

**Subagent-side hook** — modification to `track-touched-files.sh`. Reads `agent_id` (snake_case, top-level — note asymmetric casing) and appends edited paths to:
```
.git/coordinator-sessions/.agents/<agentId>/touched.txt
```

**Atomic back-pointer write** — temp+rename: `echo "$SESSION_ID" > "${EM_BACKPOINTER}.tmp.$$" && mv ... > "$EM_BACKPOINTER"`. Read-side soft-recovery: empty/malformed `em-session-id.txt` → empty `em_sid` from `head -1` → membership check fails → agent dir silently skipped. No commit-time failure.

**Read path at commit time.** Build `em_candidates`: own resolved session_id PLUS any other live (PID-alive) session id via the new `cs_live_session_ids` helper (one sid per line, no headers). Enumerate `.agents/<agentId>/`, read `em-session-id.txt` back-pointer, check membership. Append matched agents' `touched.txt` to `do_scoped`'s `my_touched` array. **Deliberately NOT applied in `--scope-from` mode** — declared scope is exhaustive (Issue C contract).

**Reaper.** `cs_reap_agents` runs alongside `cs_reap_stale`: any `.agents/<agentId>/` whose `touched.txt` mtime is older than 24h is archived to `${base}/.archive/.agents-<aid>-<date>`. Bounds index growth.

**Namespace.** `.agents/` (leading dot), not `_agents/` — 4 of 6 `${base}/*/` iterators already skip `.archive` via the existing leading-dot convention, so `.agents/` inherits 4 skips for free (Patrik v2 F1).

**Burn-in ledger.** `tasks/issue-a-burn-in.md` carries one row per successful default-mode dispatch+commit cycle: `| cycle | commit-sha | date | dispatched-agent-count | notes |`. Doctrine strike on the troubleshooting "helper misidentified your session" note requires 5 cycles (Patrik F9 — replaces the fuzzy "one verification session" wording).

### 8. `--expected-branch` Gate (Issue B — shipped 2026-05-06)

Probe 0.2 confirmed there is **no autonomous HEAD-mutating code** in the coordinator scripts: zero `git checkout`/`switch`/`reset`/`worktree`/`update-ref`. `coordinator-auto-push` is push-only. `session-init.sh` is read-only for branch detection. All `git checkout` instructions in `.md` files are LLM-consumed only. Wrong-branch commits did NOT result from a code-level branch-switch bug. Most plausible cause: shared working tree was on the daily branch at dispatch time (sibling-session checkout), and the dispatching EM did not verify before sending the prompt.

The fix is a deterministic gate on the helper, not a doctrine line:

```bash
coordinator-safe-commit --expected-branch <name> "<subject>"
```

The helper aborts before staging on mismatch, prints reflog entries for both current and expected branches, and emits:

> Resolution: 'git checkout $EXPECTED_BRANCH' or correct dispatch prompt.

**EM dispatch-prompt convention.** EM captures `git branch --show-current` at dispatch time, includes `expected_branch: <current>` in the prompt. Executor passes `--expected-branch <name>` to every `coordinator-safe-commit` call. Doctrine-only / Standing-Order / dispatch-prompt convention alone was rejected — executors are LLM agents, not deterministic processes; only the bash helper fails closed (Patrik F3 carried forward).

### 9. Issue C — `--scope-from` is Exhaustive

The original `--scope-from` mode silently subtracted other active sessions' touch lists from the declared scope, mirroring the default mode's cross-session math. That contradicted the workstream-anchored contract: the handoff doc declared scope; subtraction made the actual commit a different (smaller) set. Three changes ship together:

- **Cross-session subtraction removed from `--scope-from`.** Declared scope is exhaustive — what the handoff says, the helper stages.
- **Runtime overlap gate.** If two active sessions claim overlapping paths, surface loudly at commit time. Helper's overlap check is the contract surface; the helper does not silently pick a winner.
- **Out-of-scope dirty files fail loud.** Files dirty in the working tree but absent from the declared `scope:` block abort the commit. Pass `--allow-out-of-scope-dirty` to proceed (logged warning).
- **Default-mode fails closed when >1 live session detected.** Resolve via `--scope-from <handoff>` (preferred) or `COORDINATOR_OVERRIDE_SCOPE=1` with explicit-path staging (emergencies). Single-session default unchanged.

---

## How to Use It (EM-Facing)

### Default scoped commit

```bash
~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-safe-commit "<subject>"
```

Stages MY_SCOPE, commits, reports what was included and what was skipped.

### Carve-out ceremonies only (`/session-start`, `/workday-complete`)

```bash
CLAUDE_INVOKING_COMMAND=session-start \
  ~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-safe-commit \
  --blanket "chore: session-start sweep — pre-orientation capture"
```

Only valid when `$CLAUDE_INVOKING_COMMAND` is `session-start` or `workday-complete`. The helper rejects `--blanket` from all other callers.

### Workstream-anchored (handoff/pickup)

```bash
coordinator-safe-commit --scope-from tasks/handoffs/<workstream>/handoff.md "pickup: <workstream> — resume"
```

Pulls pathspecs from the handoff frontmatter's `scope:` field. Both bookends (handoff prep, pickup safety commit) use the same declared scope — honest and consistent.

### Dry-run preview

```bash
coordinator-safe-commit --dry-run "subject"
```

Shows what would be staged and committed. Does not commit. Use to verify scope before important commits.

### Emergency override

```bash
COORDINATOR_OVERRIDE_SCOPE=1 git commit -m "emergency: <reason>"
```

Bypasses scope guard. Logged to `.git/coordinator-sessions/<id>/overrides.log` for audit. Document the reason in the commit body.

---

## Carve-Outs and Why

Exactly two ceremonies use blanket staging by design:

**`/session-start`** — irregular, user-initiated, often invoked when the EM doesn't yet know what workstream it's in. A blanket commit is a deliberate "capture whatever loose state exists before orienting" act. The subject (`"chore: session-start sweep — pre-orientation capture"`) is honest about this. Concurrent-sweep risk is structurally low: the user just initiated the session, and any concurrent session is incidental rather than coordinated.

**`/workday-complete`** — end-of-day close-out. Blanket staging is the point of the ceremony. The subject reflects that (`"chore: workday-complete — close out YYYY-MM-DD"`).

**Why `/pickup` and `/handoff` are NOT carve-outs:** they're the bookends of a workstream-specific transfer. The handoff doc names the workstream; pickup resumes that work. They run regularly (every session pair), not irregularly. Their commits should narrate the workstream, not sweep whatever happened to be dirty. The original `/handoff:133` instruction ("stage everything, don't try to separate workstreams") was the single most concurrency-hostile line in the codebase and the primary generator of this bug. Both ceremonies now go scoped via `--scope-from`.

**Why these two and not others:**
- Both are user-initiated, not auto-fired by the EM mid-flow.
- Both are irregular (not every 10 minutes), so blanket commits don't dominate the audit trail.
- The subject genuinely describes the action — "sweep / close-out" is honest.
- Concurrency risk at these moments is low by nature.

**Everywhere else — scoped is the default.** Mid-work safety commits, post-phase commits in pipelines, pickup, handoff prep, session-end mid-day pivots, bug-sweep checkpoints, staff-session phase boundaries, deep-research phase commits, distillation/consolidation safety commits, merge-to-main pre-flights — all stage only the current workstream.

---

## The Deny-Mode Flip — Phase 5 Readiness

The Bash-PreToolUse scope guard starts in warn-only mode. Every warning is logged to `.git/coordinator-sessions/<id>/scope-warnings.log` with: timestamp, session ID, the foreign file, the suspected owning session (or "orphan"), and the EM's resolution (committed anyway / unstaged / asked user).

**Flip predicate — ALL of the following must hold:**
- ≥10 sessions in warn-only mode have completed.
- False-positive rate (warns where the EM concluded the file was legitimately theirs) < 10% across logged sessions.
- Zero unresolved orphan-class warnings in the trailing 7 days.
- Minimum 14-day soak (floor, not the trigger).

**Tools:**

| Binary | Purpose |
|--------|---------|
| `scope-flip-readiness` | Evaluates the flip predicate; reports current session count, FP rate, open orphan warns |
| `scope-soak-enable` | Writes the soak-clock sentinel (records when warn-only mode began) |
| `scope-warning-resolve` | Updates warn-log resolutions (mark a warn as FP or TP after EM decides) |

All three at: `~/.claude/plugins/coordinator-claude/coordinator/bin/`

**Pre-flip verification:** Before setting `COORDINATOR_SCOPE_STRICT=1`, empirically confirm the Claude Code PreToolUse deny contract — that a non-zero exit code from the hook is recognized as a deny and surfaces a usable message to the EM. See `~/.claude/plugins/coordinator-claude/coordinator/docs/pretooluse-deny-contract.md`. Do not flip strict mode without this verification.

**Strict mode activation:**
```bash
# In hook config / session-start env:
export COORDINATOR_SCOPE_STRICT=1
```

Rejection message includes override syntax verbatim:
> "Set COORDINATOR_OVERRIDE_SCOPE=1 to bypass scope guard for this commit."

---

## Troubleshooting

**"My new file isn't being staged"**

The touch-tracker hook should have caught any `Write` or `Edit` call. Check whether `.git/coordinator-sessions/<id>/touched.txt` exists and contains the file. If the file is missing from `touched.txt`:
- Verify the hook (`track-touched-files.sh`) is active in your PostToolUse hook list.
- If the hook fired but the path is wrong, check that `tool_input.file_path` is resolving correctly for your tool type.
- If the file was created via a Bash command (not `Write`), it won't be in `touched.txt` by design — see next entry.

**"I'm getting a scope warning for a file I touched via Bash"**

Bash edits aren't tracked by the hook — intentionally. They fall to mtime detection at commit time. However, the mtime path cross-subtracts other sessions' touch lists: if another session claims the file in its `touched.txt`, the mtime fallback won't include it in your scope. If the file is genuinely yours and Bash-edited, stage it explicitly:

```bash
git add <path>
coordinator-safe-commit "subject"
```

The explicit `git add` preloads the index; the helper proceeds from there.

**"Helper says scope is empty"**

Your session hasn't touched any files via tracked tools, and mtime fallback found nothing after subtraction. Check:
- Does `.git/coordinator-sessions/<id>/touched.txt` exist? If not, the session directory wasn't initialized — the hook may not have fired yet (first session with no tracked edits).
- Is `CLAUDE_SESSION_ID` resolving correctly? Look at `.git/coordinator-sessions/.current-session-id` or `echo $CLAUDE_SESSION_ID`.
- Did you only make Bash-driven edits? Those fall to mtime — they'll appear if another session doesn't claim them.

**"I'm on a different branch than my session started on"**

mtime fallback becomes ambiguous across branch switches — "dirty since started_at" mixes pre- and post-checkout state. Commit before `git checkout`. If you're already in this state, use explicit `git add <paths>` to be precise, then commit normally.

**"The helper misidentified my session — it's blocking my files and/or sweeping someone else's"** (inverse failure mode)

The session-ownership tracking is asymmetric: it correctly prevents one session from sweeping another's work, but if session resolution misidentifies *your* session (wrong `CLAUDE_SESSION_ID`, stale sentinel file, PID collision, multiple-live-sessions ambiguity), the same machinery that protects against cross-session contamination causes the inverse failure — your own touched files appear "owned by another session" and get excluded from staging, while another session's mtime-dirty files may be swept under your subject.

**Symptoms:** "skipping X — owned by session Y" for files you actually edited; commit succeeds but contains files you didn't touch; staged scope is empty even though you've been writing all session.

**Fix — bypass the helper with an explicit-path commit:**

```bash
git add -- <paths-you-actually-touched>
git commit -m "<subject>"
```

This is the canonical fallback (see `feedback_git_commit_explicit_path.md`). Explicit pathspecs preserve the audit-trail discipline the helper exists to enforce — you're naming exactly what's yours — without depending on session-ownership lookup. Use this whenever the helper's session resolution is wrong and you can't quickly fix it.

`COORDINATOR_OVERRIDE_SCOPE=1` is the wrong tool here: it disables scope-checking entirely (and would happily commit other sessions' files). The override is for genuine emergencies; explicit-path is for misidentification.

After committing, if you can identify the root cause (e.g. the session sentinel pointing to a dead session), fix it so the helper works on the next commit.

**"I need to bypass for an emergency"**

```bash
COORDINATOR_OVERRIDE_SCOPE=1 git commit -m "emergency: <reason>"
```

Document why in the commit body. The override is logged to `.git/coordinator-sessions/<id>/overrides.log`.

**"Session reaper archived my active session"**

Reaper criterion requires all three: `inactive_for > 24h AND no PID in meta.json is alive AND no commits referenced this scope in last 24h`. If it archived a live session, check the PID in `meta.json` — if it was stale (process died), the reaper acted correctly. Reinitialize: the helper will recreate the session directory on next use.

---

## Plugin Distribution Note

The upstream plugin source lives at `X:/coordinator-claude/`. All structural files (touch-tracker hook, `coordinator-safe-commit`, `coordinator-session.sh`, `validate-commit.sh` extension) sync to the upstream source — other machines pulling this plugin pick them up on next reinstall. The wiki guide (`docs/wiki/scoped-safety-commits.md`) and memory entries live in the consuming project's user tree and do NOT sync upstream by design. This file is not part of the plugin distribution.

---

## Related Artifacts

| Artifact | Path |
|----------|------|
| Plan | `~/.claude/plans/scoped-safety-commits.md` |
| Patrik review | `~/.claude/plans/review-scoped-safety-commits-patrik.md` |
| Ceremony audit | `~/.claude/plans/audit-ceremony-commit-prescriptions.md` |
| Agent audit | `~/.claude/plans/audit-agent-commit-prescriptions.md` |
| Deny-contract doc | `~/.claude/plugins/coordinator-claude/coordinator/docs/pretooluse-deny-contract.md` |
| Touch-tracker hook | `~/.claude/plugins/coordinator-claude/coordinator/hooks/scripts/track-touched-files.sh` |
| Commit helper | `~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-safe-commit` |
| Session lib | `~/.claude/plugins/coordinator-claude/coordinator/lib/coordinator-session.sh` |
| Sibling: branch discipline | [`daily-branch-discipline.md`](./daily-branch-discipline.md) — enforces commit *location* (branch); this page enforces commit *content* (files). Both hooks share the PreToolUse Bash matcher. |

---

## Decision Records

**SC-DR-001 — Bash writes excluded from touch-tracker hook**

*Problem:* Should the hook parse Bash tool calls to detect write effects (heredocs, redirections, `tee`, etc.)?

*Decision:* No. Parsing arbitrary shell for write effects is unsound and creates a growing regex catalog with false confidence. mtime fallback at commit time is the sole Bash-edit detector. Intentional gap documented here rather than papered over with an unsound heuristic.

*Alternatives considered:* Bash-write heuristic regex (rejected — Patrik P0-3; too many edge cases). Requiring explicit `git add` for all Bash-driven edits (acceptable fallback, documented in Troubleshooting).

**SC-DR-002 — `/handoff` and `/pickup` are not carve-outs**

*Problem:* Should handoff/pickup use blanket staging since they're "transition" moments?

*Decision:* No. They're workstream-specific by definition. The handoff doc names the workstream; the `--scope-from` flag uses that declaration. Making them carve-outs would reintroduce the audit-trail bug at precisely the highest-traffic moments. The former `/handoff:133` instruction ("stage everything, don't try to separate workstreams") was the primary generator of the bug and was reversed in Phase 0.

*Alternatives considered:* Carve-out with "honest" subjects (rejected — doesn't solve concurrent contamination). Per-session branches (rejected — too heavyweight for regular use; worktrees are the right answer for genuinely parallel feature work).

**SC-DR-003 — Warn-only soak before deny-mode flip**

*Problem:* How do we know the scope guard's false-positive rate before committing to blocking mode?

*Decision:* Signal-gated flip: ≥10 sessions in warn-only, <10% FP rate, zero open orphan warns in 7d, 14d minimum floor. Flip on meeting the predicate — not on calendar expiry alone. `scope-warning-resolve` tool tracks EM resolutions per warn-fire.

*Alternatives considered:* Immediate strict mode (rejected — unknown FP rate could block legitimate commits). Calendar-only gate (rejected — session volume may be low, predicate more meaningful than duration).

**SC-DR-004 — Agent-id linkage uses durable agentId, not parent_session_id**

*Problem:* How to associate a subagent's edits with the dispatching EM when subagent PostToolUse JSON has no `parent_session_id` field?

*Decision:* Use `agentId` (opaque, mechanical, durable per Probe 0.3 — 12+ char lowercase hex). Two mechanical writers (EM-side + subagent-side hooks) and a back-pointer file. No executor cooperation, no LLM-driven recording, no env vars.

*Alternatives considered:* Original Option 1 (parent_session_id from PostToolUse) — falsified by Probe 0.1, no parent pointer in subagent JSON. Env-var threading — not propagated. Sentinel-only resolution — overwritten by sibling SessionStart (Issue C surface).

**SC-DR-005 — Agent-id union skipped in `--scope-from` mode**

*Problem:* Should the agent-id read path apply to `--scope-from` (workstream-anchored) commits as it does to default-mode commits?

*Decision:* No. Per the Issue C contract, declared scope is exhaustive — out-of-scope dirty files fail the commit. Implicitly unioning agent-id-touched paths into a `--scope-from` commit would contradict that contract and reintroduce the silent-scope-drift bug at the workstream-transfer surface.

**SC-DR-006 — `--expected-branch` is helper-side, not doctrine-only**

*Problem:* Wrong-branch commits from agents whose dispatching EM didn't verify branch state. Doctrine alone hadn't held.

*Decision:* Add `--expected-branch <name>` as a hard gate inside `coordinator-safe-commit`. Helper aborts before staging on mismatch.

*Alternatives considered:* Standing-order convention in agent prompts — rejected, executors are LLM agents and forget. Pre-dispatch verification by EM only — rejected, trust the deterministic surface, not the cooperative one (Patrik F3).

**SC-DR-007 — Doctrine strike requires 5 burn-in cycles**

*Problem:* When can the troubleshooting note about "helper misidentified your session" be removed from the wiki?

*Decision:* After 5 successful default-mode dispatch+commit cycles logged to `tasks/issue-a-burn-in.md` (Patrik F9). Replaces the original fuzzy "one verification session" wording.
