# Scoped Safety Commits

**System:** coordinator
**Last Updated:** 2026-05-13 (SC-DR-008 doctrine inversion)
**Related plans:** `~/.claude/docs/plans/2026-05-13-safe-commit-demote-to-sweep.md` (current); `archive/specs/2026-04-27-scoped-safety-commits.md` (original)

---

## Current Doctrine (SC-DR-008, 2026-05-13)

**Plain `git add -- <paths> && git commit -m "<subject>" -- <paths>` is the default for scoped commits.** `coordinator-safe-commit` is reserved for six authorized sites:

| Invocation | Sites | Flag |
|---|---|---|
| `--blanket` | `/session-start`, `/workday-complete`, `/update-docs` (Phase 0 `:51`, Phase 8b `:53`+`:71`, Phase 9 `:212`), `pipelines/relay-protocol.md:160`, `pipelines/artifact-distillation/PIPELINE.md:358` | `--blanket` with matching `CLAUDE_INVOKING_COMMAND={session-start, workday-complete, update-docs, relay-protocol, distillation}` |
| `--expected-branch` | `agents/executor.md` only | `--expected-branch <name>` per **SC-DR-006** — only the bash helper fails-closed on wrong-branch; LLM executors are non-deterministic |

Raw `coordinator-safe-commit "<subject>"` (no flags) is **deprecated**.

### Why this changed

Prior framing from the PM (now expanded by SC-DR-008 — the original rule named only the two ceremonies that existed at the time; the current allow-list is five, plus the executor `--expected-branch` carve-out):

> "**Default for scoped commits in this repo: plain `git add <paths> && git commit -m '...' -- <paths>`.** The trailing `-- <paths>` scopes the commit to those paths only, regardless of index state. **Use coordinator-safe-commit only for the two explicit ceremonies it's designed for:** `/session-start` and `/workday-complete`."
> — `projects/X--claude-unreal-holodeck/memory/feedback_safe_commit_unreliable.md` (PM, 2026-05-04)

Three rounds of patching the helper (`plans/safe-commit-fixes.md`, `safe-commit-fixes-5-and-6.md`, the Staff Engineer r1–r3) did not converge on session-detection correctness under concurrency. Empirical failures driving the inversion:

- `lessons.md:207` (2026-05-06) — parallel-executor concurrent-commit absorption (`/bug-blitz` wave 1 bundled 4-of-6 commits into one, swept 46 unrelated files).
- `lessons.md:43` (2026-05-08) — `--scope-from` fallback widened the race window; concurrent session swept a 14-file index.
- `coordinator-improvement-queue.md` line 7 (2026-05-13) — helper silent-no-op recurrence #2: exit 0 with no commit, no FAIL signal.

The structural fix below (touch-tracker, mtime, scope helper) remains in use for the six authorized sites. The doctrinal *default* is what changed: plain git is the cheap reliable path; the helper handles only the cases its semantics actually fit.

---

## Why This Exists (Original Rationale, 2026-04-27)

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

**`--blanket` enforcement:** The `--blanket` flag is accepted only when `$CLAUDE_INVOKING_COMMAND` is one of: `session-start`, `workday-complete`, `update-docs`, `relay-protocol`, `distillation`. Any other caller gets:

> "`--blanket` is only valid from the authorized sweep ceremonies. Use plain `git add -- <paths> && git commit -m \"...\" -- <paths>` for scoped commits, or `COORDINATOR_OVERRIDE_SCOPE=1` for emergencies."

This prevents `--blanket` from becoming `git add -A` by another name. Allow-list expansion 2026-05-13 (SC-DR-008): `update-docs`, `relay-protocol`, `distillation` added; each runs a single Sonnet executor serially per pipeline (no parallel fan-out → lessons.md:207 mechanism cannot recur).

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

**Namespace.** `.agents/` (leading dot), not `_agents/` — 4 of 6 `${base}/*/` iterators already skip `.archive` via the existing leading-dot convention, so `.agents/` inherits 4 skips for free (the Staff Engineer v2 F1).

**Burn-in ledger.** `tasks/issue-a-burn-in.md` carries one row per successful default-mode dispatch+commit cycle: `| cycle | commit-sha | date | dispatched-agent-count | notes |`. Doctrine strike on the troubleshooting "helper misidentified your session" note requires 5 cycles (the Staff Engineer F9 — replaces the fuzzy "one verification session" wording).

### 8. `--expected-branch` Gate (Issue B — shipped 2026-05-06)

Probe 0.2 confirmed there is **no autonomous HEAD-mutating code** in the coordinator scripts: zero `git checkout`/`switch`/`reset`/`worktree`/`update-ref`. `coordinator-auto-push` is push-only. `session-init.sh` is read-only for branch detection. All `git checkout` instructions in `.md` files are LLM-consumed only. Wrong-branch commits did NOT result from a code-level branch-switch bug. Most plausible cause: shared working tree was on the daily branch at dispatch time (sibling-session checkout), and the dispatching EM did not verify before sending the prompt.

The fix is a deterministic gate on the helper, not a doctrine line:

```bash
coordinator-safe-commit --expected-branch <name> "<subject>"
```

The helper aborts before staging on mismatch, prints reflog entries for both current and expected branches, and emits:

> Resolution: 'git checkout $EXPECTED_BRANCH' or correct dispatch prompt.

**EM dispatch-prompt convention.** EM captures `git branch --show-current` at dispatch time, includes `expected_branch: <current>` in the prompt. Executor passes `--expected-branch <name>` to every `coordinator-safe-commit` call. Doctrine-only / Standing-Order / dispatch-prompt convention alone was rejected — executors are LLM agents, not deterministic processes; only the bash helper fails closed (the Staff Engineer F3 carried forward).

### 9. Issue C — `--scope-from` is Exhaustive

The original `--scope-from` mode silently subtracted other active sessions' touch lists from the declared scope, mirroring the default mode's cross-session math. That contradicted the workstream-anchored contract: the handoff doc declared scope; subtraction made the actual commit a different (smaller) set. Three changes ship together:

- **Cross-session subtraction removed from `--scope-from`.** Declared scope is exhaustive — what the handoff says, the helper stages.
- **Runtime overlap gate.** If two active sessions claim overlapping paths, surface loudly at commit time. Helper's overlap check is the contract surface; the helper does not silently pick a winner.
- **Out-of-scope dirty files fail loud.** Files dirty in the working tree but absent from the declared `scope:` block abort the commit. Pass `--allow-out-of-scope-dirty` to proceed (logged warning).
- **Default-mode fails closed when >1 live session detected.** Resolve via `--scope-from <handoff>` (preferred) or `COORDINATOR_OVERRIDE_SCOPE=1` with explicit-path staging (emergencies). Single-session default unchanged.

#### Addendum — agent-id linkage scope in `--scope-from` mode

The agent-id linkage introduced by Issue A (`archive/specs/2026-05-05-issue-a-agent-id-linkage.md`) unions executor-edited files into the dispatching session's scope, but **only in default mode**. In `--scope-from` mode the declared `scope:` block is exhaustive per the Issue C contract (`archive/specs/2026-05-05-session-misidentification-fix.md`): executor-edited files that fall outside the declared scope are deliberately excluded, even when the back-pointer linkage is fully wired. This is intentional, not a bug — see SC-DR-005.

When an executor produces files whose paths weren't predictable at handoff-write time (e.g., dynamically-named outputs), use `--allow-out-of-scope-dirty` to proceed with a warning, or `--include-orphans <pathspec>...` for a structured one-shot claim. A "silently extend declared scope to include executor-claimed files" mode was considered and rejected: the auditability value of exhaustive declared scope outweighs the ergonomic friction. If a workflow consistently hits this wall, the correct fix is either a richer handoff with broader `scope:` globs, or a fresh plan revisiting the Issue C contract — not a silent expansion. (Observed case: `tasks/handoffs/2026-05-06_223721_safe-commit-session-touch-tracker-orphan-files.triage.md`.)

---

## How to Use It (EM-Facing)

### Default scoped commit (post-SC-DR-008)

```bash
git add -- <paths>
git commit -m "<subject>" -- <paths>
```

The trailing `-- <paths>` scopes the commit to those paths regardless of index state. No helper invocation; no session-detection magic; no race window. This is what skill bodies and dispatch prompts should use for scoped commits.

`--scope-from <handoff>` callers must validate `scope:` frontmatter presence before staging — missing/empty `scope:` is a FAIL, not a fallback to staging-all.

### Sweep ceremonies (`--blanket`)

```bash
CLAUDE_INVOKING_COMMAND=session-start \
  ~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-safe-commit \
  --blanket "chore: session-start sweep — pre-orientation capture"
```

Only valid when `$CLAUDE_INVOKING_COMMAND` is one of: `session-start`, `workday-complete`, `update-docs`, `relay-protocol`, `distillation`. The helper rejects `--blanket` from all other callers.

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

**`git mv` + Edit sequencing in pickup.** `/pickup` Step 5's frontmatter mutation pattern is: (1) `git mv` handoff to destination, (2) `Edit` the destination file, (3) `git add -- <dest>`, (4) `git commit`. Reversing steps 1 and 2 (Edit-before-mv) stages only the rename: the content mutation stays in the working tree, producing a commit that records the filename change but not the consumed-frontmatter update. The correct verb order is mv → Edit destination → add → commit. (Surfaced 2026-05-08 `/pickup` Step 5 incident.)

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

Bash edits aren't tracked by the hook — intentionally. They fall to mtime detection at commit time. However, the mtime path cross-subtracts other sessions' touch lists: if another session claims the file in its `touched.txt`, the mtime fallback won't include it in your scope. If the file is genuinely yours and Bash-edited, use `--include-orphans` to claim it:

**Preferred — audited, overlap-checked:**

In a single-EM environment (one live session):
```bash
coordinator-safe-commit --include-orphans <path> "subject"
```

In a concurrent-EM environment (multiple live sessions), combine with `--scope-from`:
```bash
coordinator-safe-commit --scope-from <handoff.md> --include-orphans <path> "subject"
```

The helper resolves the pathspec, checks the runtime overlap gate (first claimant wins), writes
an audit log at `.git/coordinator-sessions/<id>/orphan-claims.log`, and annotates the file with
`(orphan-claimed)` in `print_summary`. One-shot: does not append to `touched.txt`.

**Fallback — when `--include-orphans` is unavailable (older helper version):**
```bash
git add <path>
coordinator-safe-commit "subject"
```

The explicit `git add` preloads the index; the helper proceeds from there. Use this only when
the `--include-orphans` flag is not yet available — it lacks the overlap gate and audit trail.

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

## Concurrency Edges

### Per-machine files for concurrent writers

For concurrent-writer state (per-machine logs, per-EM scratch), prefer per-machine files (`tasks/<host>/foo.md`) over a shared file with merge logic. Merge conflicts under concurrent EM sessions are pure overhead; per-machine fan-out is cheap.

### Cross-platform locking (cs_claim_handoff and siblings)

`flock(1)` is unavailable on Git Bash for Windows. Use atomic `mkdir <lockdir>` as the cross-platform lock primitive — `mkdir` is atomic in POSIX file semantics on NTFS and returns nonzero if the directory already exists. Pair with `trap 'rmdir <lockdir>' EXIT`.

### Session-init blanket vs. peer scoped staging

Session-init blanket commits (`coordinator-safe-commit --blanket`) can race with a peer session's scoped staging — the blanket call may sweep up paths the peer is mid-staging. Mitigation: session-init runs the blanket pass BEFORE any peer-session activity is expected, or it skips when `cs_claim_handoff` lock detects an active peer. This is a residual edge after SC-DR-008.

### Blanket-vs-scoped race detection

Before any `--blanket` sweep runs, snapshot the staged set with `git diff --cached --name-only` and compare against the ceremony's expected scope. Files staged by a peer session (paths the ceremony didn't touch and the EM doesn't recognize) signal a concurrent scoped-staging in flight — the blanket commit will absorb them under the wrong subject. Mitigation in the calling skill: if unrecognized staging is detected, abort the `--blanket` call and surface to PM rather than committing. (Helper-side pre-check is queued separately as a script change; until it lands, the calling skill carries the diff-check.)

### Pre-staging reset hazard — `git reset` before explicit-path fallback

When `coordinator-safe-commit` fails mid-flight, the index may already carry foreign-orphan paths the helper staged during scope computation. The fallback recipe (`git add -- <paths> && git commit -m "..." -- <paths>`) trailing-pathspec scopes the **commit** but not the **index** — orphans staged by the failed helper remain in the index and leak into the next commit if the trailing `-- <paths>` is omitted on a later call. **Always run `git reset` (no `--hard`, no paths — clears the index, preserves the worktree) before the explicit-path fallback.** Then `git add -- <paths> && git commit -m "<subject>" -- <paths>` from a known-clean index. Symptom that motivates this recipe: helper exits non-zero, your next plain `git commit -m "..."` (no `-- <paths>`) lands foreign orphans under your subject.

### `git mv` + Edit ordering

`git mv <src> <dst>` stages the rename atomically. A subsequent `Edit` against `<dst>` mutates the working tree only — the staged rename is content-identical to `<src>`, and `git commit -- <dst>` lands the rename without the content change. **Correct order:** `git mv` → `Edit dst` → `git add -- <dst>` → `git commit -m "..." -- <dst>`. Reversed (`Edit src` → `git mv src dst`) is worse: the working-tree edit is silently abandoned by `git mv`, which moves the *index* version of `<src>`. `/pickup` Step 5 frontmatter-mutation pattern is the canonical example; the same trap fires anywhere a rename and a content edit ship in one commit. (Surfaced 2026-05-08 `/pickup` Step 5 incident; recurrence 2026-05-12 holodeck.)

### Atomic stage+commit gesture — tool-call boundaries are concurrency windows

Splitting `git add -- <paths>` and `git commit -m "..." -- <paths>` across two Bash tool calls opens a window in which a concurrent EM's `git add -A` / `coordinator-safe-commit --blanket` can sweep your staged index into their commit. Inside a single Bash call, treat stage+commit as one atomic gesture: `git add -- <paths> && git commit -m "<subject>" -- <paths>`. The trailing `-- <paths>` on `git commit` is non-negotiable — it scopes the commit by pathspec regardless of what else landed in the index between the `add` and `commit`, closing the cross-tool-call race window. (`lessons.md:43`, 2026-05-08 — `--scope-from` fallback race documented; SC-DR-008 inversion driver.)

### `git commit` without trailing `-- <pathspec>` is unsafe on shared branches

Path-scoped `git add` does not protect the commit. A concurrent EM's `git add -A` between your `add` and `commit` lands their staged files under your subject. **Always pass `-- <paths>` to `git commit` on shared branches**, even after a clean `git add -- <paths>`. The trailing pathspec is the only deterministic scope guarantee under concurrent index mutation. Recurrence is the signal: this rule re-fires faster than the documentation reaches the EM at commit time — keep the trailing pathspec mandatory in skill bodies and dispatch prompts.

### Concurrent-executor commit absorption — never call the helper in parallel

Parallel executors must NOT each call `coordinator-safe-commit` (or any touched-files-aware helper). Empirical failure mode (`lessons.md:207`, 2026-05-06, commits `54ca925` / `945bb4d`): 4 of 6 simultaneous helper invocations bundled into one commit, 46 unrelated dirty files from concurrent workstreams swept under one bug-fix subject. **Pattern:** fan-out executors do their work and stop without committing; EM serializes commits with plain `git add -- <paths> && git commit -m "..." -- <paths>` after the fan-out completes. No-pathspec commits issued from inside a concurrent executor will absorb sibling pre-staged work — the helper's session-detection cannot win this race under N-way parallel callers (SC-DR-008 driver).

### "no changes added to commit" — reflog probe before retrying

`git commit -m "..."` returning *"no changes added to commit"* when you know you just staged work means a concurrent session's commit landed between your `add` and `commit` and swept your staged index. The work is not necessarily lost — it survives in the reflog. **Probe sequence:**

```bash
git reflog --date=iso | head -20            # find the foreign commit's parent
git stash list                              # check for auto-stashed state
git fsck --lost-found                       # last-resort dangling-blob recovery
```

Identify the sibling commit; if it absorbed your files, those files are now in `HEAD` under the wrong subject — verify with `git show --stat <foreign-sha>`. Resolution: cherry-pick or amend the foreign commit's message (PM call), or revert+redo. Do NOT blindly retry `git add && git commit` — repeats the race.

### Post-commit `git show --stat` verification on shared branches

Path-filtered `git status` lies under concurrent EMs — the filter hides foreign files the index actually carries. **After every commit on a shared branch**, run `git show --stat HEAD` and confirm the file list matches your intent. The unfiltered `git diff --cached --name-only` is the pre-commit equivalent. Subject says one workstream, diff contains another is the failure mode this catches — it's invisible without the post-commit audit.

### Sibling-sweep audit pass after high-concurrency dispatch (N>5)

After any fan-out with N>5 concurrent executors on a shared branch, run a `git log -p --since="<dispatch-start>"` audit before merging. Look for: commits whose diff exceeds the subject's stated scope (sibling absorption), "ghost" commits with no clear workstream attribution (helper-attribution race), and orphan files dropped by the touched-tracker. Recurrence rate is empirical: lessons.md:502 (2026-05-08 mise dispatch) and lessons.md:207 (2026-05-06 bug-blitz) both produced ghost commits at this scale. The audit is cheap (5-15 min `git log -p` read); the alternative is shipping cross-workstream contamination to main.

### Stash-and-reset hook recovery after concurrent-EM sweep

Coordinator stash-and-reset safety hooks (when active) can swallow Edit'd files that landed between concurrent EMs — Session B's `git reset` after stash-pop silently absorbs Session A's working-tree edits if A's edits arrived between B's `stash push` and `stash pop`. **Recovery probe (run BEFORE retrying the failing commit):**

```bash
git stash list                              # check for stash entries you didn't author
git fsck --lost-found                       # dangling blob recovery
git reflog --date=iso                       # find the reset that swallowed your edits
```

Pair this with the post-executor verify rule: `git diff --stat` + `git log --oneline -- <expected-paths>` on every dispatch return. Substantive work on disk but missing from git history → recovery probe; zero working-tree presence → redispatch.

### Large unstaged diff in shared files = active peer session

Discovering >100 LOC of unstaged changes in a shared plugin/skill/doctrine file you didn't edit means another EM is actively working in this tree. Do NOT fix-forward their broken intermediate state, do NOT `git stash` (you'll bury their work and they won't find it), do NOT `git checkout -- <path>` (destroys their work). Surface to PM ("active peer detected on `<path>` — pausing edits on this surface"). Acceptable: edit unrelated files, run read-only tooling, write to your own tasks scratch. Resume the shared surface after the peer commits or hands off.

---

## Plugin Distribution Note

The upstream plugin source lives at `X:/coordinator-claude/`. All structural files (touch-tracker hook, `coordinator-safe-commit`, `coordinator-session.sh`, `validate-commit.sh` extension) sync to the upstream source — other machines pulling this plugin pick them up on next reinstall. The wiki guide (`docs/wiki/scoped-safety-commits.md`) and memory entries live in the consuming project's user tree and do NOT sync upstream by design. This file is not part of the plugin distribution.

---

## Related Artifacts

| Artifact | Path |
|----------|------|
| Plan | `~/.claude/plans/scoped-safety-commits.md` |
| the Staff Engineer review | `~/.claude/plans/review-scoped-safety-commits-patrik.md` |
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

*Alternatives considered:* Bash-write heuristic regex (rejected — the Staff Engineer P0-3; too many edge cases). Requiring explicit `git add` for all Bash-driven edits (acceptable fallback, documented in Troubleshooting).

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

*Alternatives considered:* Standing-order convention in agent prompts — rejected, executors are LLM agents and forget. Pre-dispatch verification by EM only — rejected, trust the deterministic surface, not the cooperative one (the Staff Engineer F3).

**SC-DR-007 — Doctrine strike requires 5 burn-in cycles**

*Problem:* When can the troubleshooting note about "helper misidentified your session" be removed from the wiki?

*Decision:* After 5 successful default-mode dispatch+commit cycles logged to `tasks/issue-a-burn-in.md` (the Staff Engineer F9). Replaces the original fuzzy "one verification session" wording.

**SC-DR-008 — Default/fallback inversion: plain git is the default, helper is for sweep ceremonies + executor branch-gate (2026-05-13)**

*Problem:* Three rounds of patching `coordinator-safe-commit` (`plans/safe-commit-fixes.md`, `safe-commit-fixes-5-and-6.md`, the Staff Engineer r1–r3, SC-DR-001…007) did not converge. New failure modes appeared within weeks of each round:

- 2026-05-04 — session-detection inversion: helper attributed Session A's explicitly-staged files to a concurrent session B and absorbed two of B's orphan files into A's commit (`feedback_safe_commit_unreliable.md`).
- 2026-05-06 — parallel-executor concurrent-commit absorption (`lessons.md:207`, commits `54ca925`, `945bb4d`): 4 of 6 simultaneous `coordinator-safe-commit` calls bundled into one commit; 46 unrelated dirty files from concurrent workstreams swept under one bug-fix message.
- 2026-05-08 — `--scope-from` fallback race (`lessons.md:43`): documented fallback (`git add -- <paths>` + plain commit) is non-atomic; a 14-file index was swept by a concurrent commit between the `add` and the `commit`.
- 2026-05-13 — silent-no-op recurrence #2 (`coordinator-improvement-queue.md` line 7): helper printed "files I'm leaving alone" and exited 0 without committing or signalling failure.

The PM-accepted empirical rule (`feedback_safe_commit_unreliable.md`, 2026-05-04) was already plain-git-as-default; doctrine had not caught up. Twelve+ skill/command/hook/pipeline call sites still invoked the helper as their primary commit path, none of them in a regime where the helper's touched-files heuristic actually fit.

*Decision:* Invert the default. **Plain `git add -- <paths> && git commit -m "<subject>" -- <paths>` is the doctrinal default for scoped commits.** `coordinator-safe-commit` is reserved for:

1. **Sweep ceremonies (`--blanket`):** `/session-start`, `/workday-complete`, `/update-docs` (Phase 0, 8b, 9), `pipelines/relay-protocol.md`, `pipelines/artifact-distillation/PIPELINE.md`. Each runs a single executor serially per ceremony — the lessons.md:207 concurrent-callers mechanism cannot arise. `--blanket` gate accepts `CLAUDE_INVOKING_COMMAND ∈ {session-start, workday-complete, update-docs, relay-protocol, distillation}`.
2. **Executor branch-gate (`--expected-branch`):** `agents/executor.md` only, preserved per **SC-DR-006** — only the bash helper fails-closed on wrong-branch; LLM executors are non-deterministic and cannot enforce branch gating via doctrine alone.

Raw `coordinator-safe-commit "<subject>"` (no flags) is deprecated.

*Cross-references:* SC-DR-002 (exhaustive-scope contract now lives in plain-git callers via path-list enumeration from handoff frontmatter `scope:` block — git-pathspec syntax works directly with `git add`). SC-DR-006 (executor branch-gate carve-out preserved). SC-DR-007 (troubleshooting-note burn-in supersession: the inversion makes the note's "helper misidentified your session" rationale moot — non-sweep callers no longer touch the helper).

*Open derivative work (not in SC-DR-008 scope):*
- Silent-no-op fix in helper: HEAD-unchanged sentinel + `if ! git commit ...; then echo FAIL; exit 2; fi` wrapper on all commit-attempting paths (`do_scoped`, `do_scope_from`, `do_override`, `do_blanket`, orphan-claim subpaths).
- pytest harness for hooks + helper (coord-improvement-queue line 272).
- Session-detection substrate rebuild — would be required only if the helper is ever re-promoted to default; demote avoids the need.
