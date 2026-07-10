# Scoped Safety Commits

**System:** coordinator
**Last Updated:** 2026-05-27 (shared-registration-file staging hazard)
**Related plans:** `~/.claude/docs/plans/2026-05-13-safe-commit-demote-to-sweep.md` (current); `archive/specs/2026-04-27-scoped-safety-commits.md` (original)
**Sibling:** [`concurrent-em-hazards.md`](./concurrent-em-hazards.md) — the symptom-indexed hazard catalog this page's enforcement machinery defends against. Read it for the *why*; this page for the *how*.

---

## Current Doctrine (SC-DR-008, 2026-05-13; updated SC-DR-014, 2026-06-15)

**Plain `git add -- <paths> && git commit -m "<subject>" -- <paths>` is the default for scoped commits.** `coordinator-safe-commit` is reserved for five authorized sites:

**Structural floor (SC-DR-014):** `block-blanket-git-add.sh` (BLOCK-BLANKET-GIT-ADD tripwire) hard-denies `git add -A` / `git add .` / `git add -u` and bundled blanket-flag forms when cwd is the `~/.claude` meta-repo. The hook bypasses the Phase-5 warn-first soak gate (SC-DR-003) under the unambiguous-command-class carve-out — literal pattern-match, no per-session state, zero legitimate in-repo uses outside the override paths. Helper's `--blanket`/`--override` paths use `_COORDINATOR_SAFE_COMMIT_INTERNAL_BLANKET=1` to bypass; emergency callers use `COORDINATOR_OVERRIDE_BLANKET_ADD=1` (env-only, NOT inline prefix). Also: `coordinator-safe-commit` defaults to `--expected-owner em-only` when no ownership flag and no `--expected-branch` is passed — a defence-in-depth gate against executor self-commit on executors that forget the no-commit rule. See SC-DR-014 below and `docs/wiki/coordinator-tripwires.md § BLOCK-BLANKET-GIT-ADD`.

| Invocation | Sites | Flag |
|---|---|---|
| `--blanket` | `/workstream-start`, `/update-docs` (Phase 0 `:51`, Phase 8b `:53`+`:71`, Phase 9 `:212`), `pipelines/relay-protocol.md:160`, `pipelines/artifact-distillation/PIPELINE.md:358` | `--blanket` with matching `CLAUDE_INVOKING_COMMAND={workstream-start, update-docs, relay-protocol, distillation}` |
| `--expected-branch` | `agents/executor.md` only | `--expected-branch <name>` per **SC-DR-006** — only the bash helper fails-closed on wrong-branch; LLM executors are non-deterministic |

Raw `coordinator-safe-commit "<subject>"` (no flags) is **deprecated**.

### Why this changed

Prior framing from the PM (SC-DR-008 expanded the allow-list to five ceremonies; the current allow-list is four after `/workday-complete` was removed in 2026-06-22, plus the executor `--expected-branch` carve-out — see § Carve-Outs and Why):

> "**Default for scoped commits in this repo: plain `git add <paths> && git commit -m '...' -- <paths>`.** The trailing `-- <paths>` scopes the commit to those paths only, regardless of index state. **Use coordinator-safe-commit only for the two explicit ceremonies it's designed for:** `/workstream-start` and `/workday-complete`."
> — `projects/X--example-game-workbench-repo/memory/feedback_safe_commit_unreliable.md` (PM, 2026-05-04)

*(Pre-SC-DR-008 framing — `/workday-complete` was removed from the allow-list 2026-06-22; current blanket ceremonies are workstream-start, update-docs, relay-protocol, distillation. See § Carve-Outs and Why.)*

Three rounds of patching the helper (`plans/safe-commit-fixes.md`, `safe-commit-fixes-5-and-6.md`, the Staff Engineer r1–r3) did not converge on session-detection correctness under concurrency. Empirical failures driving the inversion:

- `lessons.md:207` (2026-05-06) — parallel-executor concurrent-commit absorption (`/bug-blitz` wave 1 bundled 4-of-6 commits into one, swept 46 unrelated files).
- `lessons.md:43` (2026-05-08) — `--scope-from` fallback widened the race window; concurrent session swept a 14-file index.
- `coordinator-improvement-queue.md` line 7 (2026-05-13) — helper silent-no-op recurrence #2: exit 0 with no commit, no FAIL signal.

The structural fix below (touch-tracker, mtime, scope helper) remains in use for the five authorized sites. The doctrinal *default* is what changed: plain git is the cheap reliable path; the helper handles only the cases its semantics actually fit.

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
~/.claude/plugins/coordinator/bin/coordinator-safe-commit
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

**`--blanket` enforcement:** The `--blanket` flag is accepted only when `$CLAUDE_INVOKING_COMMAND` is one of: `workstream-start`, `update-docs`, `relay-protocol`, `distillation`. Any other caller gets:

> "`--blanket` is only valid from the authorized sweep ceremonies. Use plain `git add -- <paths> && git commit -m \"...\" -- <paths>` for scoped commits, or `COORDINATOR_OVERRIDE_SCOPE=1` for emergencies."

This prevents `--blanket` from becoming `git add -A` by another name. Allow-list expansion 2026-05-13 (SC-DR-008): `update-docs`, `relay-protocol`, `distillation` added; each runs a single Sonnet executor serially per pipeline (no parallel fan-out → lessons.md:207 mechanism cannot recur). `/workday-complete` was removed from the allow-list (migrated to `workday-complete-step2_5-dirty-tree.sh`, a path-classifier that no longer uses `--blanket`).

### 4. Bash-PreToolUse Scope Guard (extends `validate-commit.sh`)

Before any `git commit` Bash call, the guard reads `MY_SCOPE` and the staged file set. If staged ⊄ MY_SCOPE, it emits a warning naming the foreign files and the likely owning session.

**This is distinct from git's `.git/hooks/pre-commit`.** The Bash-PreToolUse scope guard fires when Claude Code is about to run a Bash call that starts with `git commit` — it intercepts at the tool-use level, before the shell command runs. Git's pre-commit hook fires inside the git process, after the shell command starts. Different surfaces, different blocking semantics. Both can be active simultaneously; the Bash-PreToolUse guard is the coordinator's layer.

During rollout: warn-only. Strict (blocking) mode is activated via `COORDINATOR_SCOPE_STRICT=1` env var after the flip predicate is met (see Phase 5 section below).

### 5. Workstream-Anchored Scope (Handoff/Pickup)

`/handoff` and `/pickup` are workstream-specific. At pickup time the resuming session hasn't touched anything yet, so the touch list is empty. Solution: handoff docs declare scope in frontmatter using **git pathspec syntax** — the same syntax `git add` understands.

```yaml
# state/handoffs/<workstream>/handoff.md frontmatter
workstream: scoped-safety-commits
scope:
  - plugins/coordinator-claude/**
  - docs/plans/scoped-safety-commits.md
  - state/handoffs/scoped-safety-commits/**
```

The `scope:` values are `git pathspec` expressions (supports `**` globstar, `!negation`, `:(glob)` prefix). The helper validates pathspecs at parse time and rejects malformed expressions before attempting staging.

### 6. Agent Prompt Self-Containment

Executor (`executor.md`) and all reviewer/planner agents carry their own "Commit Discipline / Do Not Commit" prose. Subagents see only their dispatch prompt — project CLAUDE.md is invisible to them. This means the rule must be embedded in the prompt itself, not assumed from context.

**The self-contained prose is a NO-GIT block, not merely "do not commit."** A stalled executor that runs a bare `git stash` (no pathspec) on a shared tree sweeps a sibling session's uncommitted edits and loses them on a tangled `pop` — a strictly worse failure than an errant commit. Every write-capable executor brief therefore carries an ironclad NO-GIT block: no `stash` / `checkout` / `reset` / `add` / `commit`; a dirty shared tree is NORMAL, ignore unrelated files; if blocked, STOP and report rather than reaching for git. Recover a swept edit non-destructively with `git checkout stash@{0} -- <files>` and keep the stash as a backup rather than popping it.

### 7. Agent-ID Linkage (Issue A — shipped 2026-05-06)

The original touch-tracker linked file edits to the **dispatching session** via the `CLAUDE_SESSION_ID` sentinel. Probing exposed two flaws: (1) subagents have no `parent_session_id` in their PostToolUse JSON, so the hook could not associate a subagent's edits with the EM that dispatched it; (2) sibling SessionStart events overwrite the last-writer-wins sentinel, so the resolved session id can drift mid-flight.

The fix uses `agentId` (durable, opaque, mechanical — `^[a-f0-9]{12,}$`, lowercase hex, 12+ chars per Probe 0.3) as the linkage key. **Shape caveat (probe 2026-06-30, harness 2.1.185):** the hex shape holds for UNNAMED dispatches only; named Agent-Teams teammates use the `name@session-<short>` shape (e.g. `orchestrator@session-abc12`), which does NOT match `^[a-f0-9]{12,}$`. Format guards in `track-dispatched-agents.sh` and `track-touched-files.sh` must accept both patterns to link named-teammate dispatches correctly. See `docs/plans/2026-06-30-loe-dispatch-undercount-teammate-shape.md` and `tasks/loe-dispatch-undercount/subagent-side-agentid-probe.md`. Two mechanical writers, no executor cooperation, no LLM-driven recording, no env vars:

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

When an executor produces files whose paths weren't predictable at handoff-write time (e.g., dynamically-named outputs), use `--allow-out-of-scope-dirty` to proceed with a warning, or `--include-orphans <pathspec>...` for a structured one-shot claim. A "silently extend declared scope to include executor-claimed files" mode was considered and rejected: the auditability value of exhaustive declared scope outweighs the ergonomic friction. If a workflow consistently hits this wall, the correct fix is either a richer handoff with broader `scope:` globs, or a fresh plan revisiting the Issue C contract — not a silent expansion. (Observed case: `state/handoffs/2026-05-06_223721_safe-commit-session-touch-tracker-orphan-files.triage.md`.)

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
CLAUDE_INVOKING_COMMAND=workstream-start \
  ~/.claude/plugins/coordinator/bin/coordinator-safe-commit \
  --blanket "chore: workstream-start sweep — pre-orientation capture"
```

Only valid when `$CLAUDE_INVOKING_COMMAND` is one of: `workstream-start`, `update-docs`, `relay-protocol`, `distillation`. The helper rejects `--blanket` from all other callers. (`/workday-complete` was removed from the allow-list — it now uses a path-classifier instead of `--blanket`; see § Carve-Outs and Why.)

### Workstream-anchored (handoff/pickup)

```bash
coordinator-safe-commit --scope-from state/handoffs/<workstream>/handoff.md "pickup: <workstream> — resume"
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

The following ceremonies use blanket staging by design:

**`/workstream-start`** — fires autonomously ("Do not ask permission") and multiple times per day, so the original rationale ("concurrent-sweep risk is structurally low, user just initiated the session") no longer holds. The carve-out is now safe for a different reason: **the blanket path subtracts live-sibling-claimed paths by construction**. Before committing, the helper computes a Foreign set — paths claimed by a live sibling session's `touched.txt`, minus the own session's claims, minus agent-claimed paths — and **unstages those paths via `git reset HEAD --`**, leaving them untouched in the sibling's tree. True orphans (dirty files claimed by no live session, mtime > `started_at`) are still captured. The subject (`"chore: workstream-start sweep — pre-orientation capture"`) is honest about the sweep intent.

In other words: the blanket path no longer sweeps the whole tree unconditionally — it sweeps (tree minus sibling claims). `/workstream-start`'s autonomy and frequency are safe because the mechanism is **sibling-safe-by-construction**, not because concurrency is rare.

**`/update-docs`**, **`relay-protocol`**, **`distillation`** — run serially (one Sonnet executor per ceremony) so the lessons.md:207 concurrent-callers mechanism cannot arise. Also benefit from the sibling-subtract.

**`/workday-complete` was removed from the allow-list (2026-06-22).** It migrated to `workday-complete-step2_5-dirty-tree.sh`, a path-classifier that no longer uses `--blanket`. Historical note: it was previously the second named carve-out ("end-of-day close-out; blanket staging is the point of the ceremony").

**`COORDINATOR_BLANKET_ACCEPT_FOREIGN` — new semantics (2026-06-22).** This env var previously suppressed the foreign-staging warning (warn-then-proceed). It now means **"skip the subtract, sweep foreign too"** — the deliberate full-sweep escape hatch for operators who explicitly want the old blanket-the-whole-tree behaviour. Setting it acknowledges that sibling-claimed paths will be absorbed under the ceremony's subject.

**Why `/pickup` and `/handoff` are NOT carve-outs:** they're the bookends of a workstream-specific transfer. The handoff doc names the workstream; pickup resumes that work. They run regularly (every session pair), not irregularly. Their commits should narrate the workstream, not sweep whatever happened to be dirty. The original `/handoff:133` instruction ("stage everything, don't try to separate workstreams") was the single most concurrency-hostile line in the codebase and the primary generator of this bug. Both ceremonies now go scoped via `--scope-from`.

**Why the remaining ceremonies and not others:**
- The blanket path now subtracts live-sibling-claimed paths (Foreign = sibling-claimed − own ∪ agent-claimed) before staging, so it captures orphaned loose state without absorbing concurrent work.
- Each is (or runs serially enough) that the lessons.md:207 parallel-caller mechanism cannot arise.
- The subject genuinely describes the action — "sweep / close-out / relay" is honest.

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

All three at: `~/.claude/plugins/coordinator/bin/`

**Pre-flip verification:** Before setting `COORDINATOR_SCOPE_STRICT=1`, empirically confirm the Claude Code PreToolUse deny contract — that a non-zero exit code from the hook is recognized as a deny and surfaces a usable message to the EM. See `~/.claude/plugins/coordinator/docs/pretooluse-deny-contract.md`. Do not flip strict mode without this verification.

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
- Is the session id resolving correctly? `echo $CLAUDE_CODE_SESSION_ID` (the platform-injected, authoritative source) — it should match a `.git/coordinator-sessions/<id>/` dir. The `.current-session-id` sentinel is last-writer-wins and only a fallback for old Claude Code; if it flips between reads, two sessions are live and you should trust the env var.
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

**"Was my file reverted, or is it genuinely uncommitted?" — read HEAD-markers vs worktree-markers**

After a concurrent sibling stash / hard-reset, a file you edited may be missing from disk. Diagnose which case you're in by comparing whether HEAD carries your change (H) against whether the worktree does (W):

- `H>0 / W=0` = **reverted-committed** — your change is safely in HEAD, only the worktree was reverted; restore it with `git checkout HEAD -- <file>`.
- `H=0 / W>0` = **real uncommitted work** still on disk — keep it and commit immediately before the next sweep takes it.

This tells you whether to restore from git or to protect a live edit, rather than re-doing work that already landed or discarding work that hasn't. Commit each verified executor batch the instant it verifies (per-batch explicit-path commit) so the `H>0/W=0` case is the common one — never hold verified-but-uncommitted work in a shared tree waiting for a combined commit.

**"Resolvers always fall through to the `.current-session-id` sentinel even when running inside Claude Code"** (fixed 2026-05-23)

Root cause: The four resolvers (`coordinator-safe-commit`, `coordinator-write-review-trail.sh`, `coordinator-session-loe.sh`, `cs_claim_handoff`) checked `CLAUDE_SESSION_ID` — a variable no platform version actually exports. The correct variable is `CLAUDE_CODE_SESSION_ID`, which Claude Code 2.1.150+ injects into every tool subprocess. With the wrong name checked, resolution always fell through to the last-writer-wins `.current-session-id` sentinel, making multi-session contention invisible to the fast-path.

Fix: `CLAUDE_CODE_SESSION_ID` inserted as the first resolution source above the sentinel in all four resolvers (commit `031909d8`). Test suites require `env -u CLAUDE_CODE_SESSION_ID` to cover fallback paths because the test runner itself runs inside a Claude Code session.

If you are on an old coordinator version and the sentinel is racing: verify with `echo $CLAUDE_CODE_SESSION_ID` from a Bash tool call — if it prints a value, the resolver should pick it up. If the resolver still falls through, the fix is not yet installed; run `/coordinator:install` to update.

**Performance note — `cs_live_session_ids` 170× speedup (2026-05-23)**

If session-start or commit feels slow (~30s), the likely cause is the old `cs_live_session_ids` implementation: it called `_cs_read_meta_field` (sed/jq subprocesses) and `_cs_iso_to_epoch` (date/python subprocess) per session directory — ~600ms/dir on Windows Git Bash, ~29s total with 250+ accumulated dead dirs.

The rewrite: one Python invocation globs every `meta.json`, parses all in-process via stdlib `json` + `datetime.fromisoformat`, and emits TSV. The bash layer applies the elapsed filter and `kill -0`. Startup cost paid once. Expected timing: 28.9s → 0.17s.

Accumulated dead session dirs compound this. `cs_reap_stale` and `cs_reap_agents` are wired into `session-init.sh` with a 12h `.last-reap` marker gate — they clean automatically on each boot without taxing it. If you accumulated dirs before this was wired, the first `/session-start` after the fix performs a one-time sweep.

CRLF gotcha on Windows: Python text-mode stdout writes `\r\n`; bash `read` strips `\n` only, leaving `\r` in the last TSV column. This breaks arithmetic. The rewrite strips CRLF from the last column explicitly.

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

Session-init blanket commits (`coordinator-safe-commit --blanket`) previously raced with a peer session's scoped staging — the blanket call could sweep paths the peer was mid-staging. As of 2026-06-22 the blanket path subtracts live-sibling-claimed paths (Foreign set) before staging, so peer-claimed paths are unstaged via `git reset HEAD --` and left in the peer's tree. The residual race is a narrow TOCTOU window: if a peer claims a path in `touched.txt` after the Foreign snapshot but before `git add -A`, that path can still be absorbed. Mitigation: the window closes in milliseconds on a local filesystem; content always survives even if attribution shifts. → see § Carve-Outs and Why for the full escape-hatch semantics of `COORDINATOR_BLANKET_ACCEPT_FOREIGN`; consumer-side view in concurrent-em-hazards.md § H4.

### Blanket-vs-scoped race detection

The `--blanket` path now subtracts live-sibling-claimed paths before staging (Foreign = sibling `touched.txt` claims − own ∪ agent), so sibling-staged paths are automatically excluded. The calling-skill diff-check (`git diff --cached --name-only` before `--blanket`) remains useful as a belt-and-suspenders: if unrecognized paths are staged and the sibling-subtract didn't catch them (TOCTOU edge), abort and surface to PM. The pre-check is no longer the sole mitigation — it is a secondary confirmation that the subtract worked as expected.

### Pre-staging reset hazard — `git reset` before explicit-path fallback

When `coordinator-safe-commit` fails mid-flight, the index may already carry foreign-orphan paths the helper staged during scope computation. The fallback recipe (`git add -- <paths> && git commit -m "..." -- <paths>`) trailing-pathspec scopes the **commit** but not the **index** — orphans staged by the failed helper remain in the index and leak into the next commit if the trailing `-- <paths>` is omitted on a later call. **Always run `git reset` (no `--hard`, no paths — clears the index, preserves the worktree) before the explicit-path fallback.** Then `git add -- <paths> && git commit -m "<subject>" -- <paths>` from a known-clean index. Symptom that motivates this recipe: helper exits non-zero, your next plain `git commit -m "..."` (no `-- <paths>`) lands foreign orphans under your subject.

### `git mv` + Edit ordering

`git mv <src> <dst>` stages the rename atomically. A subsequent `Edit` against `<dst>` mutates the working tree only — the staged rename is content-identical to `<src>`, and `git commit -- <dst>` lands the rename without the content change. **Correct order:** `git mv` → `Edit dst` → `git add -- <dst>` → `git commit -m "..." -- <dst>`. Reversed (`Edit src` → `git mv src dst`) is worse: the working-tree edit is silently abandoned by `git mv`, which moves the *index* version of `<src>`. `/pickup` Step 5 frontmatter-mutation pattern is the canonical example; the same trap fires anywhere a rename and a content edit ship in one commit. (Surfaced 2026-05-08 `/pickup` Step 5 incident; recurrence 2026-05-12 example-game-repo.)

### Staged-but-uncommitted files can be absorbed by a concurrent session's blanket sweep

**On a shared work branch, staged-but-uncommitted files get absorbed by a concurrent session's blanket sweep — commit each chunk immediately (tight explicit-path add+commit), and verify that any diff-gate scope count is single-workstream before trusting it.**

*Empirical basis (2026-06-18, example-game-repo tc-4):* A `/update-docs` sweep commit absorbed C4-3 files that were staged-but-not-yet-committed between the `git add` and the `git commit` in a concurrent session. The content survived on-branch under the sweeper's commit subject, but per-chunk attribution was lost. Separately, a `review-brightline-gate.sh --session-id` over-counted (1889 LOC / 10 commits) because both concurrent sessions resolved their session-id from the shared last-writer-wins `.current-session-id` sentinel, conflating their commits and firing a spurious PARTITION-MANDATORY verdict.

**Two rules triggered:** (1) commit each chunk immediately — a staged-but-uncommitted window of any duration on a shared branch is a sweep target; (2) when a brightline/diff-gate count looks inflated, scope it to your own files (e.g. `--session-id` or manually check `git log --oneline -- <your-paths>`) before acting on the verdict. Sister to § Atomic stage+commit gesture (the race window rule) and the `.current-session-id` sentinel note in SC-DR-009.

### Staged-but-uncommitted index is contestable — merges and sibling crash-recovery both absorb it

Beyond the blanket-sweep case above, a path-scoped `git add` left uncommitted in the shared index is claimed by two further concurrent mechanisms:

- **Partial-commit-during-merge.** While a merge is in progress, a path-scoped `git commit -- <p>` fails with *"cannot do a partial commit during a merge"* — but the preceding `git add` still STAGED the file. That staged file is then absorbed into whatever session concludes the merge, under the merge commit's subject. Verify staging state after a merge lands; do not assume a staged-but-uncommitted edit stayed yours to commit separately.
- **Sibling crash-recovery finalization.** Pre-staging files mid-ceremony (e.g. `git add`-ing a plan + completion entry during `/workstream-complete` *before* dispatching the code-reviewer, intending to fold them into the terminal commit) exposes them to a peer's crash-recovery heuristic: a concurrent EM sees staged-but-uncommitted files attributable to your session id, assumes your session crashed mid-ceremony, and commits them itself ("finalize peer &lt;sid&gt; crashed ceremony"). Even when the outcome is benign (files land on-branch), per-ceremony attribution is lost and the commit fires before your reviewer returns.

**Rule.** Keep stage+commit atomic (§ Atomic stage+commit gesture) and do NOT pre-stage ahead of a dispatch you intend to fold into a later commit. Stage a file only when you are about to commit it in the same Bash call. Sister to § Concurrent-executor commit absorption and the SC-DR-014 blanket-add floor.

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

### Stage Bug-Sweep Fix Edits the Moment Each Lands

*Source: example-game-workbench-repo, 2026-05-28.*

Unstaged edits are indistinguishable from unowned dirt on a shared branch. A sibling EM's authorized blanket-sweep ceremony (`coordinator-safe-commit --blanket` from `/update-docs`, `/workstream-start`, etc.) will absorb any unstaged changes it encounters — **unless** they are tracked in the sibling's own `touched.txt`. As of 2026-06-22, the `--blanket` path subtracts live-sibling-claimed paths (Foreign = sibling-claimed − own ∪ agent-claimed) before staging: paths the sibling session claims are unstaged via `git reset HEAD --` and left untouched. The residual hazard is a narrow TOCTOU window: if a sibling session claims a path in its `touched.txt` *after* the blanket sweep's Foreign set is snapshot but *before* the sweep's `git add -A` runs, the path can still be absorbed. This window is deliberately un-locked to preserve autonomy; the content survives in the tree even if attribution shifts. → see § Carve-Outs and Why for the full escape-hatch semantics of `COORDINATOR_BLANKET_ACCEPT_FOREIGN`.

**Rule.** Stage each bug-sweep fix edit immediately after landing it: `git add -- <edited-paths>`. Do not let fixes accumulate unstaged across tool calls on a shared branch. A staged fix is claimed; an unstaged fix is contestable. The sibling-subtract is a safety net, not a substitute for immediate staging discipline.

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

### `git stash pop` after a no-op push applies a STALE unrelated stash

If you run `git stash push` and git reports "No local changes to save" (a no-op), the stash stack is unchanged. A subsequent `git stash pop` will apply whatever the most-recent stash entry is — which may be an unrelated stash from a prior workstream, silently polluting your working tree. **Never pop blind.** Alternatives: (a) check `git stash list` before any pop; (b) use `git checkout <commit>^ -- <path>` to isolate a committed change cleanly instead of stash-and-pop; (c) name stashes with `git stash push -m "<description>"` so the content is identifiable before popping.

*Source: project-rag `state/lessons.md` (central-promoted 2026-05-29).*

### EM hand-editing a file a dispatched agent is concurrently editing — the two-writer race on one file

The whole concurrency catalog above is EM-vs-EM (two interactive sessions sharing a working tree). There is a second two-writer shape that is NOT EM-vs-EM: the **EM and one of its own dispatched agents (review-integrator, executor) both editing the same file at the same time.** When the EM dispatches a review-integrator to fold findings into a plan/spec and then *also* hand-adds rows to that same file mid-flight, the two write streams race — and a commit fired between the two writes can capture both, silently producing duplicates (e.g. two AC rows with the same ID).

*Incident.* The EM hand-added AC rows to a plan while a dispatched integrator was adding the same rows; a mid-flight commit captured both write streams and landed duplicate AC IDs. It self-healed only by luck (the duplicate was visually obvious on the next read); the failure shape is silent.

**Rule.** When an integrator or executor owns a file for the duration of its dispatch, the EM **holds that file** — does not hand-edit it until the agent returns. Fold the EM's intended additions into the dispatch brief instead, or wait for the return and add them then. This is the same "active peer detected on `<path>` — pause edits on this surface" discipline as the EM-vs-EM § Large unstaged diff rule above, applied to the EM-vs-own-agent case: a file under active agent authorship is a contested surface even though the other writer is a subagent, not a sibling EM.

**Verify before committing any file an agent touched concurrently.** Run a uniqueness grep (duplicate IDs, duplicate rows, duplicate frontmatter keys) on the file before staging it. A self-dispatched agent's edits and the EM's edits both landing in one commit is the signature; the uniqueness grep is the cheap catch the luck-dependent visual read should not be relied on to replace.

*Source: sibling-repo `state/lessons.md` (central-promoted 2026-05-30). Distinct from § Concurrent-EM Git Operations (EM-vs-EM commits) — this is the EM-vs-agent two-writer race on a single file.*

### Edit-out/commit/edit-back to scope a sibling's uncommitted change is unsafe

Manually editing a shared file to remove a sibling EM's uncommitted change, committing, then editing it back is a hazardous scope-isolation technique. If a concurrent session commits the sibling's change between your edit-out and your commit, your edit-out commit becomes a silent revert of their work when it lands. Prefer committing shared files wholesale when the sibling's change is a legitimate in-progress edit on the shared surface, or use `git stash push -- <file>` / `git stash pop` with explicit verification (see the stash-pop warning above). The edit-out/commit/edit-back pattern has no concurrency-safe execution window on a shared branch.

*Source: self `state/lessons.md` (central-promoted 2026-05-29).*

### Stash-pop primitive for cross-EM file isolation at dispatch time

The "active peer session" rule above is the read-side detect; this is the write-side hygiene when an EM dispatches an executor against a file a sibling EM has uncommitted edits in. **Sequence:** `git stash push -- <paths>` *before* the dispatch — captures the sibling's working-tree state out of the way; dispatch the executor against a clean version of the file; on executor return, `git add -- <paths> && git commit -m "..." -- <paths>` for your scope; then `git stash pop`. Without the stash, an `Edit`-then-`git add -- <path>` from the executor stages everything in the file — there is no partial-path-add escape, and your commit silently absorbs the sibling's hunks under your subject. Sibling's per-chunk commit attribution is preserved by the round-trip even if their changes shipped during your window (pop becomes a no-op; their already-committed work is unaffected). Surfaced 2026-05-16 multi-src C3 vs sibling C6 on `mcp/project_rag_server.py` + `paths.py`.

### Pause-snapshot attribution trailer

PM-directed "pause and snapshot" blanket commits (intentional working-tree captures across sibling EMs) are legitimate, but they launder unauthorized substrate changes into history if the commit message attributes them via narrative prose. `572a548b` on project-rag captured ~940L of `cli.py` deletion (engine-index/doctor/bp-lint/probe-readiness) with no plan-or-handoff authorization in either repo; the commit message's "Spans Wave-2b cli.py port-out" attribution was author reconstruction, and three EMs each surveyed and disclaimed authorship. **Schema:** pause-snapshot commits carry a structured `Substrate-changes-attribution:` trailer. Each path-cluster that the snapshot touches gets a named source (handoff path, plan SHA, sibling EM session id) OR the literal value `unattributed` if no source can be cited. Downstream readers MUST NOT accept narrative-prose attribution at face value; the structured trailer is the only auditable record. The point of `unattributed` is to make the absence-of-attribution explicit rather than concealed in prose — surfaces forensic auditing during merge-to-main review.

Trailer example:

```
Substrate-changes-attribution:
  mcp/project_rag_server.py: handoff state/handoffs/2026-05-15_multi-src.md
  cli.py: unattributed
  scripts/download-*: handoff state/handoffs/2026-05-15_addon-pickup.md
```

(Surfaced 2026-05-15 `572a548b` post-mortem.)

### `git commit -- <pathspec>` drops mixed new+modified-tracked files silently

`git commit -m "..." -- <paths>` applies the pathspec as a *filter on the index*, and the filter interacts with file state in a way that silently drops paths. When `<paths>` mixes brand-new (untracked-but-just-`git add`ed) files with already-tracked-modified files, a pathspec-scoped commit can land the tracked modifications but omit the new files (or the reverse) depending on what was staged at commit time — the commit subject claims the full set, `git show --stat HEAD` shows a subset. **Rule.** After any `git add -- <paths> && git commit -m "..." -- <paths>` that mixes new and modified-tracked files, run `git status` and `git show --stat HEAD` and confirm every intended path landed; a `commit-message-says-X-but-diff-says-Y` gap is the silent failure shape. Pairs with § "Post-commit `git show --stat` verification on shared branches" — that rule catches sibling absorption; this one catches your own pathspec dropping a path it should have carried. (Source: project-rag, 2026-06-09.)

### Exec-bit does NOT survive a pathspec commit — chmod the worktree, not just the index

`git update-index --chmod=+x <path>` sets the executable bit *in the index only*. A subsequent `git commit -m "..." -- <path>` (trailing pathspec) **overrides the staged index mode with the worktree mode** — so if the worktree file is still mode `0644`, the committed blob is `0644` and the `--chmod=+x` is silently discarded. The exec bit appears set right up until the pathspec commit unsets it. **Rule.** To ship an executable bit, `chmod +x <path>` on the *worktree* file (not just `git update-index --chmod`), then commit; verify the committed mode with `git ls-tree HEAD -- <path>` (expect `100755`, not `100644`). Distinct from § "`git mv` + Edit ordering" (working-tree edit vs staged rename) — this is the file *mode* being sourced from the worktree at pathspec-commit time, the same way file *content* is. (Source: claude-central, 2026-06-18.)

### Smoke-testing commit primitives without `--dry-run` is the executor failure the gate prevents

Running `coordinator-safe-commit` (or a bare `git commit`) to "see what it does" on a live shared tree — without `--dry-run` — is the same eager-helpful pattern the scope gate exists to catch in executors: a smoke test that actually commits absorbs whatever is dirty/staged in the tree into a throwaway commit under a meaningless subject. **Rule.** Probe commit primitives with `--dry-run` (`coordinator-safe-commit --dry-run "subject"` shows the staged+computed scope without committing); never invoke a real commit to inspect behavior on a shared branch. The dry-run path is the designed inspection surface — see § "Dry-run preview". (Source: ~/.claude, 2026-06-15.)

### Rename pathspec must include both sides

`git mv A B && git commit -- B` leaves A's staged deletion *orphaned* — the commit applies pathspec `B` only, so the deletion of `A` remains in the index after the commit and surprises the next `git status`. Pathspec must enumerate both sides of the rename: `git commit -- A B`. Distinct from § ``git mv` + Edit ordering` above, which is about working-tree edit ordering around the rename; this is about commit-scope enumeration after the rename is staged. Existing `feedback_git_commit_explicit_path` covers pathspec discipline generally but doesn't enumerate the rename-shape gotcha — recurring 2026-05-14 example-game-repo on a `git mv` within a scoped commit.

---

## Plugin Distribution Note

The upstream plugin source lives at `X:/coordinator-claude/`. All structural files (touch-tracker hook, `coordinator-safe-commit`, `coordinator-session.sh`, `validate-commit.sh` extension) sync to the upstream source — other machines pulling this plugin pick them up on next reinstall. The wiki guide (`docs/wiki/scoped-safety-commits.md`) and memory entries live in the consuming project's user tree and do NOT sync upstream by design. This file is not part of the plugin distribution.

---

## Related Artifacts

| Artifact | Path |
|----------|------|
| Plan | `~/.claude/plans/scoped-safety-commits.md` |
| the Staff Engineer review | `~/.claude/plans/review-scoped-safety-commits-the Staff Engineer.md` |
| Ceremony audit | `~/.claude/plans/audit-ceremony-commit-prescriptions.md` |
| Agent audit | `~/.claude/plans/audit-agent-commit-prescriptions.md` |
| Deny-contract doc | `~/.claude/plugins/coordinator/docs/pretooluse-deny-contract.md` |
| Touch-tracker hook | `~/.claude/plugins/coordinator/hooks/scripts/track-touched-files.sh` |
| Commit helper | `~/.claude/plugins/coordinator/bin/coordinator-safe-commit` |
| Session lib | `~/.claude/plugins/coordinator/lib/coordinator-session.sh` |
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

*Decision:* Use `agentId` (opaque, mechanical, durable per Probe 0.3 — 12+ char lowercase hex). (Named-teammate shape: `<name>@session-<short>` — probe 2026-06-30, harness 2.1.185; see `docs/plans/2026-06-30-loe-dispatch-undercount-teammate-shape.md`. Falsified for named Agent-Teams teammates: the hex-only shape does not match named-teammate ids; guards must accept both patterns.) Two mechanical writers (EM-side + subagent-side hooks) and a back-pointer file. No executor cooperation, no LLM-driven recording, no env vars.

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

1. **Sweep ceremonies (`--blanket`):** `/workstream-start`, `/update-docs` (Phase 0, 8b, 9), `pipelines/relay-protocol.md`, `pipelines/artifact-distillation/PIPELINE.md`. Each runs a single executor serially per ceremony — the lessons.md:207 concurrent-callers mechanism cannot arise. `--blanket` gate accepts `CLAUDE_INVOKING_COMMAND ∈ {workstream-start, update-docs, relay-protocol, distillation}`. (`/workday-complete` was removed from this list — it migrated to `workday-complete-step2_5-dirty-tree.sh` and no longer uses `--blanket`.)
2. **Executor branch-gate (`--expected-branch`):** `agents/executor.md` only, preserved per **SC-DR-006** — only the bash helper fails-closed on wrong-branch; LLM executors are non-deterministic and cannot enforce branch gating via doctrine alone.

Raw `coordinator-safe-commit "<subject>"` (no flags) is deprecated.

*Cross-references:* SC-DR-002 (exhaustive-scope contract now lives in plain-git callers via path-list enumeration from handoff frontmatter `scope:` block — git-pathspec syntax works directly with `git add`). SC-DR-006 (executor branch-gate carve-out preserved). SC-DR-007 (troubleshooting-note burn-in supersession: the inversion makes the note's "helper misidentified your session" rationale moot — non-sweep callers no longer touch the helper).

*Open derivative work (not in SC-DR-008 scope):*
- Silent-no-op fix in helper: HEAD-unchanged sentinel + `if ! git commit ...; then echo FAIL; exit 2; fi` wrapper on all commit-attempting paths (`do_scoped`, `do_scope_from`, `do_override`, `do_blanket`, orphan-claim subpaths).
- pytest harness for hooks + helper (coord-improvement-queue line 272).
- Session-detection substrate rebuild — would be required only if the helper is ever re-promoted to default; demote avoids the need.

**SC-DR-009 — Session-id resolution: `CLAUDE_CODE_SESSION_ID` not `CLAUDE_SESSION_ID` (2026-05-23)**

*Problem:* Four resolvers checked `CLAUDE_SESSION_ID`, which no Claude Code version exports. The platform's actual variable is `CLAUDE_CODE_SESSION_ID` (available since Claude Code 2.1.150 for tool subprocesses). Resolution always fell through to the `.current-session-id` sentinel — a last-writer-wins file that races under concurrent sessions.

*Decision:* Insert `CLAUDE_CODE_SESSION_ID` as the highest-priority resolution source in all four resolvers. The sentinel remains as Priority-2 fallback for pre-2.1.150 deployments.

*Alternatives considered:* Removing the sentinel entirely (rejected — backward compatibility with old Claude Code). Making env-var mandatory and failing loud if absent (rejected — breaks pre-2.1.150 installs).

*Test discipline:* Test suites covering fallback paths must `env -u CLAUDE_CODE_SESSION_ID` to suppress the injected session ID — otherwise the test runner's own session short-circuits the fallback paths under test.

## Committing the Union When Hunk-Isolation Is Unavailable — Dual-Credit and PM-Relay

**When two sessions leave uncommitted edits on the SAME file and hunk-isolation is unavailable (`git add -p` is interactive/blocked), an explicit-path commit absorbs the sibling's work — commit the union with honest dual-credit + PM-relay; do not silently absorb or stall.**

`git add -- <file>` stages the WHOLE file regardless of which hunks are yours. When `git add -p` (interactive hunk selection) is blocked, there is no mechanical isolation path. Stalling (waiting for the sibling to commit) risks losing your own work if your context compacts or the session ends. Silent absorption is dishonest and misattributes the sibling's code to your subject.

**Procedure when you detect the union situation:**
1. Before committing a shared hot file, `git diff -- <file> | grep` for foreign workstream markers (commit-message keywords, variable names, function names specific to the sibling's workstream) to confirm the union.
2. Commit the file explicit-path with a commit-body `NOTE:` crediting the sibling workstream: what was absorbed, that it will be reviewed at their workstream-complete, that you authored none of the absorbed hunks.
3. Hand the PM a one-line relay so the sibling EM knows their work landed under your SHA and does not re-commit it.
4. Scope your own code review to EXCLUDE the absorbed foreign hunks — name them out-of-scope in your reviewer brief.

**De-risking context:** on a `UBT-PENDING` stack where chunks commit pre-review and review runs at each workstream's own workstream-complete, checkpointing a sibling's code under your SHA does NOT bypass their quality gate — the only real cost is attribution. The `NOTE:` in the commit body is the attribution recovery mechanism.

*Empirical basis (2026-06-19, example-game-repo tc-8):* C8-3/C8-5/C8-5b all edited `ExecFlowLowering.cpp`, which a concurrent switch-timeline-mappers session kept leaving uncommitted SW-3/TL-3 work on. Three commits absorbed sibling hunks; each carried a NOTE crediting the workstream. Sister to § SC-DR-010 (path-scoped add doesn't scope hunks within a file) — this is the procedure when SC-DR-010 applies and interactive hunk selection is unavailable.

## SC-DR-010 — Path-Scoped `git add` Does Not Scope Hunks Within a File

*2026-05-24, project-rag-ue-addon.* `git add -- path/to/file.py` stages the ENTIRE file, not just the hunks your executor edited. If another concurrent session also edited that file, its hunks ride your commit. The scoped-commit discipline protects against cross-file contamination but does NOT protect against cross-hunk contamination within a shared file. When a file you edited is also in another session's declared scope, use `git add -p -- path/to/file.py` (interactive hunk selection) to stage only the hunks from your changes. Treat `Edit` + path-scoped `git add` on a contested file as blanket-staging by another name — it includes every modification on disk at commit time, not just yours. (Source: 2026-05-24 project-rag-ue-addon)

## SC-DR-011 — Shared Registration/Index File: Absorbed Edits Can Ship an Untracked-Import HEAD

*2026-05-26, project-rag-ue-addon.* Committing a shared registration file (a hookimpl list, plugin registry, module index, `__init__.py`) with `git add -- <path>` is the SC-DR-010 hunk-contamination hazard with a second-order failure: the absorbed sibling edits frequently introduce `import` statements whose target modules are still `??` untracked. The resulting commit ships a HEAD that imports modules absent from git — a latent broken-clean-install, invisible on the author's disk and (if the loader graceful-fails on `ImportError`) a silent non-registration on a clean checkout.

Incident: tc-34 commit `526ba4705` was the first to land four chunker-spec registrations because `git add -- __init__.py` swept in three concurrent sessions' (tc-35/tc-5/tc-6) uncommitted edits; all four target modules were untracked, so HEAD imported four nonexistent-in-git modules.

**Rule — before committing any shared registration/index/`__init__` file under concurrent EMs:**
1. `git diff --cached --name-only` to see the FULL absorbed set (the SC-DR-010 / H1 baseline — never skip it on a shared file).
2. For every new `import` / `from … import` the commit introduces, confirm the target module is `git ls-files`-tracked. An import of an untracked sibling module is a HEAD-break, not a harmless extra.

Fix-forward when you find absorbed registrations: commit the referenced impls+tests too (if complete and green on disk) — turn the latent break into a real landing, don't revert the registration. This is the *committing-EM-as-victim-of-absorption* direction; the inverse (a sibling's session-end absorbing YOUR edit) is covered in [`concurrent-em-hazards.md`](./concurrent-em-hazards.md) H4. (Source: 2026-05-26 project-rag-ue-addon tc-34; catalogued as H5 in concurrent-em-hazards.md.)

## SC-DR-013 — A `git checkout HEAD` Discard Can Resurrect via a Later `git stash pop` Into a Publish

*Source: ~/.claude, 2026-05-31. [universal]*

During a release, an unreviewed change was discarded via `git checkout HEAD -- <paths>`. Later, a `git stash pop` (the stash had captured the discarded change before the checkout) returned it to the working tree. Because the subsequent publish/percolate script copied from the **working tree** (not from a committed ref), the resurrected change percolated to the OSS repo unnoticed — caught only at cleanup.

**Rule.** A `git checkout HEAD` discard is not durable across a stash round-trip. Before any publish/percolate operation that copies the **working tree** (vs. a committed ref): re-diff the tree against HEAD (`git diff -- HEAD`) to check for changes you thought you discarded. Or publish from a committed ref explicitly, not from `$PWD`. Composes with §36 (stash-pop-after-no-op applies stale unrelated stash) — the resurrection mechanism is the same.

## SC-DR-012 — A Pre-Commit "No Stray Staged" Check That Prints But Doesn't Halt Is Theater

*2026-05-24, example-game-workbench-repo.*

## concurrent git add -A silently absorbs in-flight executor output

A concurrent `git add -A` sweep (lint, format, or distill ceremony) on the shared branch silently absorbs another EM's in-flight executor output — files the other executor just wrote get committed under the sweeping EM's name before the executor has a chance to commit them. Rule: commit each chunk scoped + immediately after the executor returns; verify on disk not chat. Apply: after every executor returns, run `git diff --stat` to confirm expected files are present, then commit with explicit paths `git add -- <paths>` before doing any broad sweep.

**A pre-commit "no stray staged" check that prints but doesn't halt is theater.** Under concurrent EMs, the check must unstage or abort on detection — echoing the offending path then committing anyway (the `grep … || echo` shape) re-attributes a sibling's work.

### Scoped `git add -- <paths>` silently absorbs pre-staged orphan operations from concurrent sessions

*Source: project-rag, 2026-06-09. [universal]*

**Rule.** Scoped `git add -- <paths>` controls only what gets staged in *this* call. Pre-staged operations (a `git rm` deletion, an `add` from a concurrent session) are already in the index, and a subsequent `git commit -- <paths>` does NOT confine the commit to your pathspec when sibling ops are already staged — the orphan op rides along into your commit. Visible only post-facto in `git show --stat <sha>`.

*Case.* An RSS-cap commit used `git add -- <explicit-paths>` (correct discipline) but a concurrent session's handoff-archival flow had already staged a `git rm` of `state/handoffs/2026-06-09_114700_daemon-crash-loop-investigation.md`. The deletion rode into the RSS-cap commit as a `delete mode` line for a file the workstream had no business deleting. (case: project-rag 2026-06-09)

**Discipline.** Between scoped safety-commits on a shared branch:
1. Run `git diff --cached --name-only` to enumerate the FULL staged set (not just your scope).
2. If anything is staged that isn't yours, either (a) `git reset HEAD -- <foreign-path>` to unstage before committing, or (b) push the orphan op into its own scoped commit first.

The existing "explicit paths only" language doesn't cover this pre-staged-orphan interaction — the `git diff --cached --name-only` pre-check is the fix.

### `git commit -- <paths>` pathspec silently drops modified-tracked files when mixed with new untracked files

*Source: project-rag, 2026-06-14 — undated. [universal]*

**Rule.** Naming both modified-tracked and new-untracked paths in the same `git commit -m "..." -- <paths>` invocation reliably commits only a subset — often only the new files. The trailing-pathspec scope guarantee assumed elsewhere on this page is asymmetric to the index/worktree state of each named path; mixing the two states in one pathspec breaks the guarantee. Safer pattern: stage everything explicitly, then commit from the staged index without a trailing pathspec — `git add -- <all-paths> && git commit -m "..."` (no `-- <paths>` on commit).

*Case.* daemon-perf C5 named 7 paths in one `git commit -- <paths>` invocation; only 3 committed. The 4 silently-dropped files were the modified-tracked ones (likely a Git-for-Windows pathspec interaction with rename-detection on the mixed state). The dropped files looked committed in chat reasoning and were caught only by post-commit `git show --stat HEAD`. (case: project-rag 2026-06-14 — undated)

**Discipline.** When a commit covers both modified-tracked and new-untracked paths, `git add -- <all-paths> && git commit -m "<subject>"` — let the staged index drive the commit. Composes with § Post-commit `git show --stat` verification on shared branches (the catch when this trap fires anyway) and § Atomic stage+commit gesture (the cross-call-window concurrency rule the bare `git commit` here trades against — acceptable because the `add` and `commit` still run in one Bash call). On a shared branch under heavy concurrency, prefer splitting the modified-tracked and new-untracked paths into two scoped commits with trailing pathspec each, rather than relying on the bare-`commit` shape.

*Incident.* A broad `git add tasks/ docs/` swept a concurrent EM's plan and a 29K-line `diff.patch` into a distill commit. The grep flagged the offending paths; the commit ran regardless; fix-forward `git rm --cached` recovered — but the commit had already landed on the shared branch.

**Rule:** gate the commit on the check's exit (non-zero → abort), or stage by explicit file list only — a directory-scoped `git add` is never safe on a shared branch. A check that only prints is identical to no check for the commit that follows it. Extends the Why-This-Exists § concurrent-EM hazard catalog (see [`concurrent-em-hazards.md`](./concurrent-em-hazards.md)).

### SC-DR-014 — Unambiguous-command-class PreToolUse blocks skip the Phase-5 soak gate

**Date:** 2026-06-15
**Plan:** `docs/plans/2026-06-15-harden-safe-commit-against-sibling-add-all.md`
**Ratified-by:** PM (2026-06-15) following 4 cross-contamination incidents in one day.

**Decision.** A PreToolUse Bash hook that pattern-matches an unambiguous command-construction class may ship in deny-mode from day one, bypassing the SC-DR-003 / Phase-5 Readiness warn-first soak gate, **iff all three of the following hold:**

1. **Literal pattern-match on command tokens.** The hook's deny condition is a literal-string or short-regex match against the Bash command string, with no semantic interpretation.
2. **No per-session state computation.** The deny decision does not depend on `touched.txt`, `coordinator-sessions/`, session-id resolution, scope-membership math, or any other per-session state — i.e., the same command from any session yields the same outcome.
3. **Zero documented legitimate in-repo use outside the override env var or helper-internal marker env var path.** All sanctioned uses of the matched pattern are reachable through the override env var (or a helper-internal marker env var). No skill, hook, or workflow legitimately needs the raw pattern outside those override paths.

**Rationale.** The Phase-5 soak gate (SC-DR-003) was designed for the *scope guard* in `validate-commit.sh` Check 5, which performs a non-trivial scope-membership computation against `touched.txt`. That computation has real false-positive risk (session-id misidentification, orphan-class warnings, stale sentinel state) — the 14-day soak existed to bound it empirically. An unambiguous-command-class block has near-zero FP risk by construction; soaking a block whose FP rate is ≈0 wastes the 14 days during which the bug it prevents continues to occur.

**Qualifying example.** `block-blanket-git-add.sh` (BLOCK-BLANKET-GIT-ADD tripwire, this plan's E1) satisfies (1) literal `git add -A` / `git add -u` etc. pattern; (2) cwd-equality + env-var checks only, no per-session state; (3) the only legitimate blanket-add paths are `coordinator-safe-commit --blanket` (carve-out — uses helper-internal marker env var `_COORDINATOR_SAFE_COMMIT_INTERNAL_BLANKET`) and emergency callers (carve-out — uses public override env var `COORDINATOR_OVERRIDE_BLANKET_ADD=1`). Both satisfy criterion (3) — each reachable through the override env var or helper-internal marker env var path. Ships deny-from-day-one.

**Non-qualifying counter-example.** A hypothetical `block-git-push-force.sh` would satisfy (1) and (2) but fail (3): `git push --force-with-lease` has documented legitimate cross-branch sync use cases outside any override path. Such a block must go through the Phase-5 soak gate, not under SC-DR-014.

**Doctrine pointer.** SC-DR-003 (Phase-5 soak) still governs scope-membership-class blocks. SC-DR-014 carves out *only* unambiguous-command-class blocks. The two are complementary; SC-DR-014 does not amend or weaken SC-DR-003 for its actual domain.

---

## Exec-Bit Mechanics — Windows `core.fileMode=false` and Pathspec Commit Hazards

### `git commit -- <pathspec>` overrides the staged index mode with the worktree mode

**Rule.** `git update-index --chmod=+x <file>` sets the index entry to mode `100755`, but `git commit -m "..." -- <file>` re-reads the **worktree** mode for the named paths and applies it to the committed tree object — the staged index mode is ignored. On Windows with `core.fileMode=false`, the worktree mode is always `100644` regardless of the actual filesystem bit, so the staged `100755` is silently reverted. The commit appears to succeed (`git ls-files -s` shows `100755` in the index), but `git ls-tree HEAD <file>` shows `100644` — the mode change was dropped.

*Empirical basis (2026-06-18 bin-cli-sh-shebang-polyglot C6):* Staged an exec-bit fix via `git update-index --chmod=+x <f>`, then ran `git commit -- <f>`. Reported "nothing to commit"; HEAD kept mode `100644`. The index showed `100755` so the repo-wide pre-commit exec-bit check passed green, masking the miss.

**Correct mechanics for exec-bit commits:**

Option A — also `chmod +x` the worktree file so worktree == index:
```bash
chmod +x <file>
git update-index --chmod=+x <file>
git commit -m "<subject>" -- <file>
```

Option B — commit from the staged index without a pathspec restriction (DR-151 carve-out):
```bash
git update-index --chmod=+x <file>
git ls-files --stage <file>   # must show 100755, not 100644
git commit -m "<subject>"     # NO trailing '-- <paths>'
```

**Verify the landed mode with `git ls-tree HEAD <file>`**, not `git ls-files -s` — `ls-files -s` reads the index (which shows `100755` correctly), not the committed tree object.

### Pre-commit exec-bit hook fires on modifications, not on new-file additions

**Rule.** The `coordinator-precommit-exec-bit-check` hook only fires on modified `.sh` files, not on first-time additions. A freshly committed `.sh` file slips through as `100644` even when all sibling bin/ files are uniformly `100755`.

*Empirical basis (2026-06-15 workstream-complete-self-clean):* Two new `.sh` files (`check-workstream-complete-deletion-blocks.sh`, `run-smoke.sh`) committed via `git commit -- <pathspec>` landed as `100644`. The hook did not fire on new-file additions; it caught only a subsequent mode-change commit.

**Mitigation.** When adding a new `.sh` file to a bin/ directory, always explicitly stage the exec bit before committing — do not rely on the pre-commit hook to catch the omission at new-file time. Use the Option A or Option B mechanics above.

---

## Rename Mechanics — `git mv` and Explicit-Path Commit Shape

### `git commit -- <new-path>` after `git mv` ships only the add half, leaving the delete staged

**Rule.** After `git mv src dst`, running `git commit -m "..." -- dst` (naming only the new path) commits the addition of `dst` but leaves `D src` still staged in the index. The rename appears as a new file rather than a rename, and `git status` on the next invocation shows the stale deletion of `src` as pending — requiring a follow-up commit to retire the old path.

*Empirical basis (2026-06-15 setup-command-triple-collision-cleanup):* Ran `git mv plugins/.../setup.md install.md` then `git commit -m "..." -- <new-path> <other-edits>`. The deleted source was not in the working tree, so passing it errors; omitting it staged only the add half. Encountered twice in one session (deep-research and example-game-repo).

**Correct recipe — enumerate both sides of the rename:**
```bash
git mv src dst
# ... any edits to dst ...
git add -- dst
git commit -m "<subject>" -- dst src   # both sides; git resolves the deletion from the index
```

Alternatively, drop the trailing `-- <paths>` restriction entirely and rely on the staged index (ensure staging hygiene is clean before committing). Distinct from § `Rename pathspec must include both sides` above, which covers the same principle for index-staged renames; this entry specifically surfaces the `git mv` + pathspec shape and the "add half only" failure mode.

---

## Concurrency Hazards — Shared-Branch Staging Race After Pre-Commit Hook Failure

### Blanket-commit absorption in the window between pre-commit hook failure and retry

**Rule.** When a `git add -- <paths>` + `git commit` sequence hits a pre-commit hook failure, the window between the failure and the retry commit is a concurrency race: a sibling session running `git add -A` or `coordinator-safe-commit --blanket` can sweep all your staged files into their commit under their subject. When you retry, `git status` shows "nothing to commit" — your code is correct on HEAD but misattributed to the sibling's commit message.

*Empirical basis (2026-06-15 DoE follow-up 2):* Had 4 files Edit/Write-staged (snippet, executor.md, tripwires, fan-out-dispatch.sh), ran scoped `git add -- <paths>`, hit a pre-commit exec-bit failure on a 5th file. While fixing the exec-bit, a sibling session swept all 5 files under their commit (`chunk-2(executor-no-self-commit-em-only-gate): regression-net test — 12 assertions green`). On retry: "nothing to commit." Confirmed via `git log --all -- <path>` on each file.

**Discipline on pre-commit failure in a shared branch:**
1. Immediately re-run `git status` before any retry — the staged snapshot from the failed commit is not durable.
2. Run `git log --oneline -- <path>` on each of your expected files to confirm they haven't been absorbed.
3. Treat the gap between `git add` and `git commit` as a race window that resets at every pre-commit failure; re-stage explicitly from `git status` before retrying.

This is the consuming-side failure mode of the blanket-add hazard catalogued in § `git commit` without trailing `-- <pathspec>` — your files can be absorbed even when YOUR commit discipline is correct, if a sibling violates it.

---

## Smoke-Testing the Commit Helper — Always Use `--dry-run`

### Running the commit helper without `--dry-run` IS a commit — smoke tests that don't use dry-run ship real commits

**Rule.** `coordinator-safe-commit` commits on the happy path. Invoking it without `--dry-run` to verify it works — or to confirm gate behavior — will land a real commit, including committing any staged content under whatever subject string you passed.

*Empirical basis (2026-06-15 DoE follow-up 8):* Shipped `coordinator-safe-commit --expected-owner em-only` to prevent executor self-commits, then immediately invoked it as a smoke test with `coordinator-safe-commit --expected-owner em-only "test"` (env unset). The gate passed (correct — EM context), and the script ran through to commit, landing Chunk 1's content under subject literally `"test"` (commit `d893d0ec`). The EM committed exactly the eager-helpful pattern the gate was designed to prevent on the executor side.

**Use `--dry-run` whenever the helper is the unit under test:**
```bash
coordinator-safe-commit --dry-run "subject"   # shows scope without committing
coordinator-safe-commit --dry-run --expected-branch <name> "subject"  # gate test
```

The EM is subject to the same eager-helpful failure mode the doctrine attributes to executors. The gate is opt-in by caller; a test invocation IS the happy path and the happy path commits.

---

## Branch-Scoped Diff Ranges — Session-Scope vs Branch-Scope on Shared Branches

### Branch-scoped diff ranges become noise on shared-branch concurrent-EM work shapes

**Rule.** Diff ranges anchored to `origin/main..HEAD` (or equivalent branch-scope forms) span all commits from every session that has committed to the shared branch. Under concurrent EM work patterns, a branch-scoped range includes sibling sessions' commits, making workstream-attribution ambiguous and per-session scope analysis unreliable.

**Default any gate or review that uses a diff range to session-scope (session-start SHA to HEAD)**, not branch-scope, when the shared-branch concurrent-EM model is active. Session-scope isolates one EM's commits; branch-scope intermingles all EMs on the branch.

*Empirical basis (2026-06-15, instance #2 — project-rag + meta-repo):* Branch-scoped diff range during a workstream-complete review surfaced commits from a sibling session, producing noise in the gate output and forcing manual filtering to recover the workstream's actual diff.

The session-start SHA is available at `.git/coordinator-sessions/<id>/head_at_start`; use `git diff <head_at_start>..HEAD` for session-scoped ranges.
