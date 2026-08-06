# Scoped Safety Commits

<!-- distilled from internal specs and dogfood session notes -->

**System:** coordinator
**Sibling:** this page's enforcement machinery defends against a symptom-indexed hazard catalog maintained alongside it — that catalog covers the *why*; this page covers the *how*.

---

## The Default: Scoped Commit Form

**The trailing pathspec is not the scope guarantee — it is a cheap proxy for one, and the proxy is only valid while the index and the worktree agree on those paths (per SC-DR-015).** When they agree — the common case, you edited, you staged, nothing else changed those paths — `git add -- <paths> && git commit -m "<subject>" -- <paths>` is the default for scoped commits (per SC-DR-008). When you deliberately staged something the worktree does not match (partial-hunk staging, `git apply --cached`, a private `GIT_INDEX_FILE`), the trailing pathspec destroys your staging silently — **and a bare pathspec-less commit against the shared index is not the fix either** (that horn absorbs whatever a peer staged in the meantime; see SC-DR-015 below). Use `ceremony.scoped_git_commit` (the coordinator engine's op) — it selects the mechanism from the index/worktree state so you don't have to classify the horn yourself — or the private-index recipe at § SC-DR-015 if the op isn't reachable. See § SC-DR-015 for the full ruling. `coordinator-safe-commit` is reserved for the authorized sites below.

**Structural floor (per SC-DR-014):** `block-blanket-git-add.sh` (folded into the coordinator engine's `coordinator_core.bash_guards` via `preuse-bash-dispatch.py`; the old shell-script version removed) (BLOCK-BLANKET-GIT-ADD tripwire) hard-denies `git add -A` / `git add .` / `git add -u` and bundled blanket-flag forms when cwd is the Claude Code meta-repo. The hook bypasses the Phase-5 warn-first soak gate (SC-DR-003) under the unambiguous-command-class carve-out — literal pattern-match, no per-session state, zero legitimate in-repo uses outside the override paths. Helper's `--blanket`/`--override` paths use `_COORDINATOR_SAFE_COMMIT_INTERNAL_BLANKET=1` to bypass; emergency callers use `COORDINATOR_OVERRIDE_BLANKET_ADD=1` (env-only, NOT inline prefix). Also: `coordinator-safe-commit` defaults to `--expected-owner em-only` when no ownership flag and no `--expected-branch` is passed — a defence-in-depth gate against executor self-commit on executors that forget the no-commit rule. See SC-DR-014 below.

| Invocation | Sites | Flag |
|---|---|---|
| `--blanket` | `/workstream-start`, `/update-docs` (Phase 0 `:51`, Phase 8b `:53`+`:71`, Phase 9 `:212`), `pipelines/relay-protocol.md:160`, `pipelines/artifact-distillation/PIPELINE.md:358` | `--blanket` with matching `CLAUDE_INVOKING_COMMAND={workstream-start, update-docs, relay-protocol, distillation}` |
| `--expected-branch` | **SUPERSEDED by M4 (see the PM's commit-model ruling)** — subagents no longer commit at all, so the carve-out this row describes has no caller; `agents/executor.md`'s self-commit path is removed | ~~`--expected-branch <name>` per **SC-DR-006** — only the bash helper fails-closed on wrong-branch; LLM executors are non-deterministic~~ |

Raw `coordinator-safe-commit "<subject>"` (no flags) is **deprecated**.

### Why plain scoped `git` is the default, not the helper

The scoped-commit helper's session-detection cannot converge on correctness under real concurrency — parallel-executor commits absorb each other, `--scope-from` fallback widens race windows, and silent no-ops ship with no FAIL signal. Plain `git add -- <paths> && git commit -m "<subject>" -- <paths>` is cheap, reliable, and carries none of that session-detection surface. The structural fix (touch-tracker, mtime fallback, scope helper — § The Structural Fix — Components below) remains in use for the authorized sweep sites, where its semantics actually fit; everywhere else, plain scoped git is the rule (per SC-DR-008). See § Carve-Outs and Why for the current authorized-site list.

---

## Commits Are Quick-Saves, Not a Verification Gate

**Diff size is not a gate — the branch IS the review buffer.** A commit on a workstream branch is
a checkpoint, not a claim that the change has been reviewed or that the full test tier has run;
review and cadence gates happen at the ceremonies that read the branch, not at every commit.

**Never `--no-verify` / `--no-gpg-sign`** unless PM-authorized (`COORDINATOR_OVERRIDE_NO_VERIFY=1`)
— skipping hooks or signature verification on a shared branch removes a safety net every
concurrent session on that branch is relying on, not just your own.

---

## Why This Exists

Blanket staging (`git add -A`) is fine for a solo session and an audit-trail lie the moment two sessions run concurrently. The failure mode is asymmetric and invisible: Session A's safety commit subject says "stub(W2): apply PM decisions" but `git add -A` also hoovers up Session B's unstaged edits. `git log` becomes useless as an audit surface — subject describes one workstream, diff contains another. **Doctrine alone cannot fix an asymmetric risk** — a disciplined Session A is still polluted when concurrent Session B runs `git add -A`. The fix is structural on two surfaces: each session tracks what it touched and commits only that (§ The Structural Fix — Components below), and no surface prescribes blanket staging outside the named carve-outs.

<!-- src: plan01-011 -->
**Every ceremony except the named carve-outs is scoped-staging-only.** § Carve-Outs and Why is the authoritative current list of blanket-staging exemptions; nothing else — pickup, handoff, mid-work safety commits, phase commits, staff-session, deep-research phases, distillation, merge-to-main pre-flight — is exempt.

---

## The Structural Fix — Components

### 1. Touch-Tracker Hook (PostToolUse)

A PostToolUse hook fires on `Write|Edit|MultiEdit|NotebookEdit` only. Every time one of these tools runs, the hook extracts `tool_input.file_path`, normalizes it to repo-relative, and appends it (deduped) to:

```
.git/coordinator-sessions/<session-id>/touched.txt
```

The session directory is created on first touch (or at `/workstream-start`). It also contains:

```
.git/coordinator-sessions/
├── <session-id>/
│   ├── started_at          # ISO timestamp
│   ├── head_at_start       # SHA at session start
│   ├── touched.txt         # a session's CURRENTLY-CLAIMED paths, not a
│   │                       #   durable history of everything it touched
│   │                       #   (ratified by a sibling-repo decision). A
│   │                       #   session writes only its OWN record.
│   │                       #   Append-only on disk; see below for the
│   │                       #   release event-log format.
│   └── meta.json           # session goal, branch, last-activity, PID
```

**Bash tool calls are not tracked by the hook.** Parsing arbitrary shell for write effects is unsound — heredocs, xargs, redirections in subshells, scripts invoking scripts. The mtime fallback (Component 2) is the sole detector for Bash-driven edits. This is intentional; the hook does not maintain a regex catalog of Bash write patterns.

**Negative-spec — this exclusion is about PARSING, never about attribution.** SC-DR-001 rejected shell-parsing on static-analysis grounds alone (see Decision Records). It does not license the inverse reading that some *other* write-time detector would be admissible if only it avoided parsing: no write-time detector attributes soundly either, because a post-hoc mtime or `git status` delta bracketing a Bash call cannot distinguish "my Bash wrote this" from "a live peer wrote it during my Bash call." **The architecture never attributes Bash writes at write time and does not need to** — detection is session-local and post-hoc; *attribution is resolved at read time, by subtraction, biased safe* (Component 2: mtime is included only where no other active session claims the path; Component 3's Foreign-set subtract; `:146`'s named residual). Any future proposal to close a Bash-write gap belongs at the read-time projection, not at the hook matcher.

**Release events (ratified by a sibling-repo decision).** `touched.txt` is a record of *currently-claimed* work, not a durable history, so a session may release a path it has committed clean. Release is an **append**, never a deletion: deletion needs read-modify-write on a file whose lock-free append discipline exists to forbid exactly that. `T <path>` claims, `R <path>` releases, last event wins per path, a bare line is a legacy `T`. Every reader therefore needs a last-event-wins projection, not a bare line set. **Confirmed against the engine writer 2026-08-03** (`coordinator_core/ops/session/scope.py` — `compute_scope` folds through `parse_touch_event`; `project_self_scope` and `project_peer_claims` both project last-event-wins rather than pruning): a reader that greps for a path and stops at the first hit reads a released path as still held.

**Historical logs carry a shape the current writer no longer emits.** Pre-2026-08-03 entries were relativized against `<repo>/.git` rather than the worktree root, producing `../`-shaped paths — roughly 40 of 50 touch-lists in the engine repo's tree at the time of the fix. The writer now derives the main worktree root from the common dir and normalizes, and the fan-out receiver fail-closed rejects absolute and `../` entries, but existing files were not retroactively repaired and no repair/regenerate decision has been taken. A reader over historical touch-lists must expect the old shape and reject rather than resolve it.

Release interacts with the Bash-write exclusion above: a path released after a clean commit and then re-dirtied through Bash has no claim re-recorded, and a co-toucher finds no owner. Resolve that at the read-time projection, and resolve it *asymmetrically* — the one log, two readers, opposite safe defaults:

- **Peer-facing** ("does anyone own this path?") — a released path that is dirty with mtime later than its `R` event projects back to CLAIMED. Over-claiming makes a co-toucher back off.
- **Self-facing** (the releasing session's own staging scope) — stays RELEASED absent a real `T`, so a peer's concurrent write can never widen `my_scope`.

The two readers want opposite answers under ambiguity, which is why "was that write mine or a peer's?" never has to be answered.

### 2. mtime Fallback at Commit Time

At commit time, the helper includes any currently dirty file whose mtime is after `started_at` — but only after cross-session set-subtraction (Component 3). This catches Bash-driven edits the hook missed (build outputs, scripted rewrites, generated files). mtime is additive input to scope computation, not a direct staging list — a file is included from mtime only if no other active session's `touched.txt` claims it.

### 3. Scoped Commit Helper (`coordinator-safe-commit`)

Replaces `git add -A && git commit -m "..."` patterns. Migrated to the coordinator engine's `coordinator/bin/` — located at:

```
coordinator engine coordinator/bin/coordinator-safe-commit
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

**A large unattributable-file count is expected noise, NEVER a reason to hold your commit.** On a hot shared `work/*` branch, dozens of dirty paths owned by concurrent peers is the normal steady state — 97 files across 11 live sessions, 28+27 growing mid-ceremony, 51 more on another occasion — all observed-normal, not anomalies. The orphan policy above exists precisely so that count cannot reach your commit: orphans are warned, never auto-staged, and sibling-claimed paths are skipped. A scoped `git add -- <your paths> && git commit -- <your paths>` is unaffected by how dirty the rest of the tree is, so **commit your own pathspec regardless** — do not wait for a "quiet window" and do not attempt to disposition peer-owned files. Deferring a finished, scoped commit because the tree looks busy is the commit-hesitancy anti-pattern, and it has real cost: the deferred work is what a crash loses, and a real `--amend`-with-no-pathspec incident (which destroyed a peer session's commit message) began as exactly this hesitation.

**`--blanket` enforcement:** The `--blanket` flag is accepted only when `$CLAUDE_INVOKING_COMMAND` is one of: `workstream-start`, `update-docs`, `relay-protocol`, `distillation`. Any other caller gets:

> "`--blanket` is only valid from the authorized sweep ceremonies. Use plain `git add -- <paths> && git commit -m \"...\" -- <paths>` for scoped commits, or `COORDINATOR_OVERRIDE_SCOPE=1` for emergencies."

This prevents `--blanket` from becoming `git add -A` by another name. `update-docs`, `relay-protocol`, `distillation` each run a single Sonnet executor serially per pipeline (no parallel fan-out, so the concurrent-callers absorption mechanism cannot recur; per SC-DR-008). `/workday-complete` is not on the allow-list — it uses `workday-complete-step2_5-dirty-tree.py`, a path-classifier that does not use `--blanket`.

### 3b. Safe-Commit Auto-Commit (`safe-commit-offer`) — stop-event mechanical aid

Motivated by TWO distinct failure shapes: (1) a session ran `git add -- <path>` then a **bare** `git commit`, twice — the bare commit inherited the whole shared index and swept a peer session's staged work into a commit describing something else; (2) the larger concern — some sessions finish their work while forgetting to commit at all, which is real data loss on a machine failure, not just misattribution. A hard deny was rejected as the fix (too blunt a salve), and an initial offer-with-one-confirmation design was rejected too — being asked whether to commit was itself the defect. Run it and report the outcome after the fact, with no confirmation gate.

`safe-commit-offer` computes this session's safe pathspec — the same `MY_SCOPE` computation Component 3 uses (`compute_scope()`, with a dispatched sub-agent's touched-files union added in as an additional candidate set, `"exact"` mode only, never `"broadened"` — see the engine module's own docstring for why: `"broadened"` returns an identical candidate union for every concurrent session, empirically confirmed, which would hand a live peer's files to whichever session's stop-event fires first under an UNATTENDED committer) — and then **commits and pushes it, with no confirmation step of any kind.** Push reuses `ceremony.scoped_git_commit`'s own push-with-retry (Component 3's `scoped-git-commit`) — not a second push path. It reports what it committed (paths, sha, push state) and what it excluded and why (`owned by session <id>` / `untouched by this session`) — as output AFTER the fact, never as a gate before it. `/handoff`'s § Safe-Commit Auto-Commit step is the consumer.

**Grouping and messaging.** Bare invocation groups mechanically by directory with a bounded subject and the full path list in the commit BODY (not the subject — an enumerated file list in the subject is unreadable past a handful of files and is worse archaeology than no automation). A caller with real judgment (an EM mid-`/handoff`) should prefer `--message`/`--groups-json` to author real per-group descriptions instead of relying on the mechanical default — any path named that isn't actually in the computed safe pathspec is silently dropped, never committed, so this is strictly additive judgment, not a way to widen scope.

**Framed explicitly as a safety net, not the primary path** — the PM's own words: "if I have to commit, it's a safety [net] because someone forgot to commit." The commit body says so plainly rather than pretending to be a curated, deliberate change; the deliberate commits an EM makes during its own session remain the good archaeology.

**Multi-session overlap on the SAME file is accepted collateral, by explicit PM ruling — not a defect this mechanism solves.** "that's a hazard of a many-EM workflow." This mechanism only prevents the bare-commit-sweep shape and the forgotten-commit shape above; it does not arbitrate two sessions that both legitimately touched one file.

**A separate, narrower hazard exists here, and its population and resolution direction are measured, not assumed (a sibling-repo measurement):** a dirty file with NO `touched.txt` record anywhere is invisible to the exact/broadened choice above (that only governs sub-agent fan-out) — it instead flows through `compute_scope()`'s own pre-existing mtime fallback. Twelve SIGKILL runs measured that the population reaching this path is **not** a crashed peer, contrary to the earlier framing here: a crashed session's `touched.txt` survives process death intact (`locked_write.locked_rmw`'s atomic mkstemp+replace under an `flock` the kernel releases on death — no held handle, no session-end flush needed), and a live peer computing scope over a dead session's files finds them still claimed by that survivor and skips them, never adopts them. What actually flows through the fallback is a healthy, running peer's Bash-mediated or engine write: `track_touched_files` records only `Write`/`Edit`/`MultiEdit`/`NotebookEdit`, so anything landed via Bash, `git apply`, or a script has no session's `touched.txt` entry — the normal path for a large class of writes, not an exceptional one. **The "or the engine itself" clause that previously stood here is stale and is struck:** an engine op routed through the dispatch chokepoint now self-reports the paths it actually wrote, so it *does* record a claim. See § SC-DR-021 for what that producer covers and, more importantly, what it deliberately does not. The resolution direction moved with the measurement: an mtime-only candidate with no owning `touched.txt` record now falls to an `orphans` bucket instead of silently joining the caller's `safe_paths` — an orphan is visible and recoverable, a misattributed commit is silent and corrupts `Session-Id`-trailer-derived coverage/chain-ancestry accounting. Declined paths are logged to the session-end diagnostics sink, bounded, advisory-only, never blocking a commit — this is the same orphan-warned-never-auto-staged pattern the rest of this doctrine already uses, not a new mechanism.

**Trigger reliability matters as much as the computation.** `/handoff` is a voluntary skill invocation — an EM that never runs it never gets the rescue. The reliable, unattended trigger is a `SessionEnd` hook (fires exactly once, when a session is genuinely over, regardless of whether `/handoff` ran — see the existing `sessionend-archive-session.py` hook for the same-shaped precedent). As of this writing that wiring is NOT yet registered in `coordinator/hooks/hooks.json` — `/handoff` is the only wired consumer. `/workday-complete`, `/workstream-complete`, and `/merge-to-main` are deliberate end-of-work ceremonies an EM chooses to run, not unattended triggers either, so a session that stops without invoking ANY of these currently has no rescue.

### 4. Bash-PreToolUse Scope Guard (the coordinator engine's `check_validate_commit` Check 5, formerly `validate-commit.sh`)

Before any `git commit` Bash call, the guard reads `MY_SCOPE` and the staged file set. If staged ⊄ MY_SCOPE, it emits a warning naming the foreign files and the likely owning session.

**This is distinct from git's `.git/hooks/pre-commit`.** The Bash-PreToolUse scope guard fires when Claude Code is about to run a Bash call that starts with `git commit` — it intercepts at the tool-use level, before the shell command runs. Git's pre-commit hook fires inside the git process, after the shell command starts. Different surfaces, different blocking semantics. Both can be active simultaneously; the Bash-PreToolUse guard is the coordinator's layer.

Default posture: warn-only. **Strict (blocking) mode IS live**, not dormant — `COORDINATOR_SCOPE_STRICT=1` promotes Check 5 from advisory to a hard DENY (`coordinator_core/bash_guards/dispatch_checks.py::check_validate_commit`; tested in `coordinator_core/bash_guards/tests/test_check_validate_commit.py::TestCheckFiveStrictModePromotion`). This supersedes the prior "never ported to the engine, dormant" claim in this section, which described the bash-era gap before the native port landed — do not cite the old claim as current. The env var is unset repo-wide by default (warn-only remains the default), so flipping it is still an explicit opt-in, not something that silently activated.

**Do NOT flip `COORDINATOR_SCOPE_STRICT=1` globally without first confirming the false-positive source below is fixed on your install.** On an unpatched install, Check 5's advisory computes `MY_SCOPE` via `compute_scope()` alone, which has no notion of `.git/coordinator-sessions/.agents/<agent_id>/touched.txt` (the per-dispatched-subagent touch record — Component 7 above) — only the EM session's own `touched.txt` plus mtime. A file edited *only* by a dispatched executor/subagent (never by an EM-context tool call) is therefore invisible to the advisory's scope set and gets warned "likely owned by orphan" even though it is legitimately the EM's own fan-out output — `coordinator-safe-commit`'s actual commit-time scope computation unions in `my_agent_touched(session_id, "broadened")` (bin/coordinator-safe-commit ~:1304-1318) and would have staged the same file cleanly. **On a patched install:** `check_validate_commit`'s Check 5 performs the same union before comparing against staged files, so the advisory previews what the real commit-time helper would actually do. On an unpatched install, a large fraction of "orphan" warnings observed in a session with any subagent dispatch are false positives of exactly this shape — under strict mode, those would hard-block every dispatch-produced commit. Verify your install has the fix (grep for `my_agent_touched` inside `check_validate_commit` in `dispatch_checks.py`) before relying on strict mode's false-positive rate being low.

**The `.agents` fix is no longer the binding constraint on a global flip — § 149's hazard class
is, and it is now measured.** A fleet-wide read of every
`.git/coordinator-sessions/*/scope-warnings.log` across nine coordinator-enabled repos
found **6197 foreign-staged warning lines across 188 sessions, of which 6078 — 98.1% —
carry no owning session at all** ("unknown owner", formerly "orphan"); only 119 (1.9%) attribute to
a named session. The distribution tracks engine-write volume, not repo size: the two doctrine
repos account for ~70% of the total. A spot-check of four such files against all 233 `touched.txt`
files in the repo that produced them confirmed them genuinely unrecorded engine-op output — the
unattributed label was *correct*, exactly as § 149 predicts, not a false positive.

**Read this as: fixing `.agents` does not open a near-term path to a global flip.** At a 98%
unattributed rate, `COORDINATOR_SCOPE_STRICT=1` set repo-wide would hard-block essentially every
commit that touches engine-written or Bash-mediated state — which is most of them. That is
consistent with the PM's 2026-08-03 warn-only ruling, and it is a property of what
`track_touched_files` records (`Write`/`Edit`/`MultiEdit`/`NotebookEdit` only), not a bug awaiting
a fix. Strict mode remains correct as a **narrow, per-invocation opt-in** on a surface whose writes
are known to be tool-mediated; the global flip is not a queued next step.

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

### 7. Agent-ID Linkage

The original touch-tracker linked file edits to the **dispatching session** via the `CLAUDE_SESSION_ID` sentinel. Probing exposed two flaws: (1) subagents have no `parent_session_id` in their PostToolUse JSON, so the hook could not associate a subagent's edits with the EM that dispatched it; (2) sibling SessionStart events overwrite the last-writer-wins sentinel, so the resolved session id can drift mid-flight.

The fix uses `agentId` (durable, opaque, mechanical — `^[a-f0-9]{12,}$`, lowercase hex, 12+ chars) as the linkage key. **Shape caveat:** the hex shape holds for UNNAMED dispatches only; named Agent-Teams teammates use the `name@session-<short>` shape (e.g. `orchestrator@session-abc12`), which does NOT match `^[a-f0-9]{12,}$`. Format guards in `track-dispatched-agents.py` and `track-touched-files.py` must accept both patterns to link named-teammate dispatches correctly. Two mechanical writers, no executor cooperation, no LLM-driven recording, no env vars:

**EM-side hook** — `track-dispatched-agents.py` (PostToolUse on the `Agent` tool). Reads `tool_response.agentId` (camelCase) and writes:
```
.git/coordinator-sessions/<em-sid>/dispatched-agents.txt   # list of agentIds
.git/coordinator-sessions/.agents/<agentId>/em-session-id.txt   # back-pointer
```

**Subagent-side hook** — modification to `track-touched-files.py`. Reads `agent_id` (snake_case, top-level — note asymmetric casing) and appends edited paths to:
```
.git/coordinator-sessions/.agents/<agentId>/touched.txt
```

**Atomic back-pointer write** — temp+rename: `echo "$SESSION_ID" > "${EM_BACKPOINTER}.tmp.$$" && mv ... > "$EM_BACKPOINTER"`. Read-side soft-recovery: empty/malformed `em-session-id.txt` → empty `em_sid` from `head -1` → membership check fails → agent dir silently skipped. No commit-time failure.

**Read path at commit time.** Build `em_candidates`: own resolved session_id PLUS any other live (PID-alive) session id via the new `cs_live_session_ids` helper (one sid per line, no headers). Enumerate `.agents/<agentId>/`, read `em-session-id.txt` back-pointer, check membership. Append matched agents' `touched.txt` to `do_scoped`'s `my_touched` array. **Deliberately NOT applied in `--scope-from` mode** — declared scope is exhaustive (Issue C contract).

**Reaper.** `cs_reap_agents` runs alongside `cs_reap_stale`: any `.agents/<agentId>/` whose `touched.txt` mtime is older than 24h is archived to `${base}/.archive/.agents-<aid>-<date>`. Bounds index growth.

**Namespace.** `.agents/` (leading dot), not `_agents/` — 4 of 6 `${base}/*/` iterators already skip `.archive` via the existing leading-dot convention, so `.agents/` inherits 4 skips for free .

**Burn-in ledger.** A burn-in ledger carries one row per successful default-mode dispatch+commit cycle: `| cycle | commit-sha | date | dispatched-agent-count | notes |`. Doctrine strike on the troubleshooting "helper misidentified your session" note requires 5 cycles (replacing the fuzzy "one verification session" wording).

### 8. `--expected-branch` Gate — **SUPERSEDED by M4**

> **SUPERSEDED.** This section describes a carve-out that let `agents/executor.md` self-commit
> under a deterministic branch guard. Per the PM's commit-model ruling (the subagent
> commit model — AC6), subagents no longer commit at all: the executor writes/edits and reports
> back, the EM commits. Claude-Klabauter's M4 PreToolUse guard (`coordinator_core/bash_guards/`) now denies
> any `git commit` — plain or via `coordinator-safe-commit` — that resolves to a Sonnet/Haiku
> subagent context, deleting the em-only-gate branch rather than bypassing it. The
> `--expected-branch` bypass this section documents is removed with it. Left in place, not
> deleted, for the decision trail — see **SC-DR-006**/**SC-DR-008** below and M4.

Probe 0.2 confirmed there is **no autonomous HEAD-mutating code** in the coordinator scripts: zero `git checkout`/`switch`/`reset`/`worktree`/`update-ref`. `coordinator-auto-push` is push-only. The session-init hook chain is read-only for branch detection. All `git checkout` instructions in `.md` files are LLM-consumed only. Wrong-branch commits did NOT result from a code-level branch-switch bug. Most plausible cause: shared working tree was on the daily branch at dispatch time (sibling-session checkout), and the dispatching EM did not verify before sending the prompt.

The fix was a deterministic gate on the helper, not a doctrine line:

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-safe-commit" --expected-branch <name> "<subject>"
```

The helper aborted before staging on mismatch, printed reflog entries for both current and expected branches, and emitted:

> Resolution: 'git checkout $EXPECTED_BRANCH' or correct dispatch prompt.

**EM dispatch-prompt convention (historical).** EM captured `git branch --show-current` at dispatch time, included `expected_branch: <current>` in the prompt. Executor passed `--expected-branch <name>` to every `coordinator-safe-commit` call. Doctrine-only / Standing-Order / dispatch-prompt convention alone was rejected — executors are LLM agents, not deterministic processes; only the bash helper failed closed. Post-M4, this whole mechanism is moot — the executor never calls `coordinator-safe-commit` at all.

### 9. Issue C — `--scope-from` is Exhaustive

The original `--scope-from` mode silently subtracted other active sessions' touch lists from the declared scope, mirroring the default mode's cross-session math. That contradicted the workstream-anchored contract: the handoff doc declared scope; subtraction made the actual commit a different (smaller) set. Three changes ship together:

- **Cross-session subtraction removed from `--scope-from`.** Declared scope is exhaustive — what the handoff says, the helper stages.
- **Runtime overlap gate.** If two active sessions claim overlapping paths, surface loudly at commit time. Helper's overlap check is the contract surface; the helper does not silently pick a winner.
- **Out-of-scope dirty files fail loud.** Files dirty in the working tree but absent from the declared `scope:` block abort the commit. Pass `--allow-out-of-scope-dirty` to proceed (logged warning).
- **Default-mode fails closed when >1 live session detected.** Resolve via `--scope-from <handoff>` (preferred) or `COORDINATOR_OVERRIDE_SCOPE=1` with explicit-path staging (emergencies). Single-session default unchanged.

#### Addendum — agent-id linkage scope in `--scope-from` mode

The agent-id linkage introduced by Issue A unions executor-edited files into the dispatching session's scope, but **only in default mode**. In `--scope-from` mode the declared `scope:` block is exhaustive per the Issue C contract: executor-edited files that fall outside the declared scope are deliberately excluded, even when the back-pointer linkage is fully wired. This is intentional, not a bug — see SC-DR-005.

When an executor produces files whose paths weren't predictable at handoff-write time (e.g., dynamically-named outputs), use `--allow-out-of-scope-dirty` to proceed with a warning, or `--include-orphans <pathspec>...` for a structured one-shot claim. A "silently extend declared scope to include executor-claimed files" mode was considered and rejected: the auditability value of exhaustive declared scope outweighs the ergonomic friction. If a workflow consistently hits this wall, the correct fix is either a richer handoff with broader `scope:` globs, or a fresh plan revisiting the Issue C contract — not a silent expansion.

---

## How to Use It (EM-Facing)

### Default scoped commit (post-SC-DR-008)

```bash
git add -- <paths>
git commit -m "<subject>" -- <paths>
```

The trailing `-- <paths>` scopes the commit to those paths regardless of index state. No helper invocation; no session-detection magic; no race window. This is what skill bodies and dispatch prompts should use for scoped commits. The scope guarantee is against a foreign *index* entry (something staged by a sibling) — the pathspec itself reads worktree content, which is a different hazard for an automated op holding its own private `GIT_INDEX_FILE`; see § The trailing pathspec reads the WORKTREE below.

`--scope-from <handoff>` callers must validate `scope:` frontmatter presence before staging — missing/empty `scope:` is a FAIL, not a fallback to staging-all.

### Sweep ceremonies (`--blanket`)

```bash
CLAUDE_INVOKING_COMMAND=workstream-start "${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-safe-commit" --blanket "chore: workstream-start sweep — pre-orientation capture"
```

Only valid when `$CLAUDE_INVOKING_COMMAND` is one of: `workstream-start`, `update-docs`, `relay-protocol`, `distillation`. The helper rejects `--blanket` from all other callers. (`/workday-complete` was removed from the allow-list — it now uses a path-classifier instead of `--blanket`; see § Carve-Outs and Why.)

### Workstream-anchored (handoff/pickup)

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-safe-commit" --scope-from state/handoffs/<workstream>/handoff.md "pickup: <workstream> — resume"
```

Pulls pathspecs from the handoff frontmatter's `scope:` field. Both bookends (handoff prep, pickup safety commit) use the same declared scope — honest and consistent.

### Dry-run preview

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-safe-commit" --dry-run "subject"
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

**`/workday-complete` is not on the allow-list.** It uses `workday-complete-step2_5-dirty-tree.py`, a path-classifier that does not use `--blanket`.

**`COORDINATOR_BLANKET_ACCEPT_FOREIGN`** means **"skip the subtract, sweep foreign too"** — the deliberate full-sweep escape hatch for operators who explicitly want the old blanket-the-whole-tree behaviour. Setting it acknowledges that sibling-claimed paths will be absorbed under the ceremony's subject.

**Why `/pickup` and `/handoff` are NOT carve-outs:** they're the bookends of a workstream-specific transfer. The handoff doc names the workstream; pickup resumes that work. They run regularly (every session pair), not irregularly. Their commits should narrate the workstream, not sweep whatever happened to be dirty. The original `/handoff:133` instruction ("stage everything, don't try to separate workstreams") was the single most concurrency-hostile line in the codebase and the primary generator of this bug. Both ceremonies now go scoped via `--scope-from`.

**Why the remaining ceremonies and not others:**
- The blanket path now subtracts live-sibling-claimed paths (Foreign = sibling-claimed − own ∪ agent-claimed) before staging, so it captures orphaned loose state without absorbing concurrent work.
- Each is (or runs serially enough) that the lessons.md:207 parallel-caller mechanism cannot arise.
- The subject genuinely describes the action — "sweep / close-out / relay" is honest.

**`git mv` + Edit sequencing in pickup.** `/pickup` Step 2's (Mutate and Commit) frontmatter mutation pattern is: (1) `git mv` handoff to destination, (2) `Edit` the destination file, (3) `git add -- <dest>`, (4) `git commit`. Reversing steps 1 and 2 (Edit-before-mv) stages only the rename: the content mutation stays in the working tree, producing a commit that records the filename change but not the consumed-frontmatter update. The correct verb order is mv → Edit destination → add → commit. (Surfaced by a `/pickup` Step 2 incident.)

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

All three at the plugin's live-install `${CLAUDE_PLUGIN_ROOT}/bin/`

**Retired 2026-07-22:** soak instrumentation (`scope-flip-readiness`, `scope-soak-enable`,
`scope-warning-resolve`) deleted as producer-less. The producer, `validate-commit.sh`, was
removed earlier (folded into the coordinator engine's `check_validate_commit` PreToolUse
dispatcher). At the time these tools were retired the strict-mode Check 5 branch they soaked
for genuinely had no port — **that has since changed: strict mode is now live** (see
§ Component 4 above). The retired soak *instrumentation* (readiness/soak-clock/resolve
tooling against the flip predicate below) has not been re-created; the predicate itself is
therefore currently unmeasured, not unmeasurable-in-principle. Preserved above for historical
context on the soak-tooling lifecycle, not as evidence strict mode is unreachable.

**Consequence for the log's resolution column: it is vestigial, and that is a deletion artifact,
not a design.** `check_validate_commit` writes every warn line with the literal
`pending-resolution`; the only thing that ever rewrote that field was `scope-warning-resolve`,
retired in the same sweep. A fleet-wide read found **6197/6197 (100%)
warn lines still `pending-resolution`** — no exceptions, because no writer remains. Do not read
that as 6197 unresolved incidents; read it as an unwritten column. **Ruling: the column stays as an
inert placeholder, and the flip predicate's two resolution-dependent criteria (FP-rate < 10%, zero
unresolved orphan-class warns in 7 days) are unmeasurable until a resolver is re-created.** Keeping
the field costs nothing and preserves the log's shape for a future resolver; deleting it would
silently rewrite the format that every archived log on the fleet is already written in. What must
not happen is a reader — human or predicate — treating the constant as signal. Anything that
consumes this log must ignore the resolution field or fail loud on it, never aggregate it.

**Pre-flip verification:** Before setting `COORDINATOR_SCOPE_STRICT=1`, empirically confirm the Claude Code PreToolUse deny contract — that a non-zero exit code from the hook is recognized as a deny and surfaces a usable message to the EM. Do not flip strict mode without this verification.

**Also verify the false-positive fix landed (2026-07-26)** before flipping — see § Component 4's
"Do NOT flip … without first confirming" paragraph. Without it, strict mode hard-blocks every
commit touching a dispatched-subagent-only edit, which is common under this project's
fan-out-by-default dispatch doctrine — a session with any executor dispatch would wedge.

**Strict mode activation:**
```bash
# In hook config / session-start env:
export COORDINATOR_SCOPE_STRICT=1
```

Rejection message (verbatim, from `check_validate_commit`'s `_deny()` call):
> "BLOCKED (strict scope): `<path>` is staged but not in this session's touch list — likely owned by `<owner>`.
>
> Unstage it (`git restore --staged <path>`) or, if it genuinely belongs to this session's work, add it to touched.txt first.
> Set COORDINATOR_SCOPE_STRICT=0 to fall back to warn-only."

(The older `COORDINATOR_OVERRIDE_SCOPE=1` bypass documented elsewhere on this page is a
*separate* emergency escape hatch for the scope guard generally — it is not the strict-mode
rejection's own printed remedy, which is the `COORDINATOR_SCOPE_STRICT=0` line above.)

---

## Troubleshooting

**"My new file isn't being staged"**

The touch-tracker hook should have caught any `Write` or `Edit` call. Check whether `.git/coordinator-sessions/<id>/touched.txt` exists and contains the file. If the file is missing from `touched.txt`:
- Verify the hook (`track-touched-files.py`) is active in your PostToolUse hook list.
- If the hook fired but the path is wrong, check that `tool_input.file_path` is resolving correctly for your tool type.
- If the file was created via a Bash command (not `Write`), it won't be in `touched.txt` by design — see next entry.

**"I'm getting a scope warning for a file I touched via Bash"**

Bash edits aren't tracked by the hook — intentionally. They fall to mtime detection at commit time. However, the mtime path cross-subtracts other sessions' touch lists: if another session claims the file in its `touched.txt`, the mtime fallback won't include it in your scope. If the file is genuinely yours and Bash-edited, use `--include-orphans` to claim it:

**Preferred — audited, overlap-checked:**

In a single-EM environment (one live session):
```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-safe-commit" --include-orphans <path> "subject"
```

In a concurrent-EM environment (multiple live sessions), combine with `--scope-from`:
```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-safe-commit" --scope-from <handoff.md> --include-orphans <path> "subject"
```

The helper resolves the pathspec, checks the runtime overlap gate (first claimant wins), writes
an audit log at `.git/coordinator-sessions/<id>/orphan-claims.log`, and annotates the file with
`(orphan-claimed)` in `print_summary`. One-shot: does not append to `touched.txt`.

**Fallback — when `--include-orphans` is unavailable (older helper version):**
```bash
git add <path>
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-safe-commit" "subject"
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

**"Resolvers always fall through to the `.current-session-id` sentinel even when running inside Claude Code"** (fixed)

Root cause: The four resolvers (`coordinator-safe-commit`, `coordinator-write-review-trail.py`, `coordinator-session-loe.py`, `cs_claim_handoff`) checked `CLAUDE_SESSION_ID` — a variable no platform version actually exports. The correct variable is `CLAUDE_CODE_SESSION_ID`, which Claude Code 2.1.150+ injects into every tool subprocess. With the wrong name checked, resolution always fell through to the last-writer-wins `.current-session-id` sentinel, making multi-session contention invisible to the fast-path.

Fix: `CLAUDE_CODE_SESSION_ID` inserted as the first resolution source above the sentinel in all four resolvers (a follow-up commit). Test suites require `env -u CLAUDE_CODE_SESSION_ID` to cover fallback paths because the test runner itself runs inside a Claude Code session.

If you are on an old coordinator version and the sentinel is racing: verify with `echo $CLAUDE_CODE_SESSION_ID` from a Bash tool call — if it prints a value, the resolver should pick it up. If the resolver still falls through, the fix is not yet installed; run `/coordinator:install` to update.

**Performance note — `cs_live_session_ids` 170× speedup (2026-05-23)**

If session-start or commit feels slow (~30s), the likely cause is the old `cs_live_session_ids` implementation: it called `_cs_read_meta_field` (sed/jq subprocesses) and `_cs_iso_to_epoch` (date/python subprocess) per session directory — ~600ms/dir on Windows Git Bash, ~29s total with 250+ accumulated dead dirs.

The rewrite: one Python invocation globs every `meta.json`, parses all in-process via stdlib `json` + `datetime.fromisoformat`, and emits TSV. The bash layer applies the elapsed filter and `kill -0`. Startup cost paid once. Expected timing: 28.9s → 0.17s.

Accumulated dead session dirs compound this. `cs_reap_stale` and `cs_reap_agents` are wired into the session-init hook chain with a 12h `.last-reap` marker gate — they clean automatically on each boot without taxing it. If you accumulated dirs before this was wired, the first `/workstream-start` after the fix performs a one-time sweep.

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

Session-init blanket commits (`coordinator-safe-commit --blanket`) previously raced with a peer session's scoped staging — the blanket call could sweep paths the peer was mid-staging. As of 2026-06-22 the blanket path subtracts live-sibling-claimed paths (Foreign set) before staging, so peer-claimed paths are unstaged via `git reset HEAD --` and left in the peer's tree. The residual race is a narrow TOCTOU window: if a peer claims a path in `touched.txt` after the Foreign snapshot but before `git add -A`, that path can still be absorbed. Mitigation: the window closes in milliseconds on a local filesystem; content always survives even if attribution shifts. → see § Carve-Outs and Why for the full escape-hatch semantics of `COORDINATOR_BLANKET_ACCEPT_FOREIGN`.

### Blanket-vs-scoped race detection

The `--blanket` path now subtracts live-sibling-claimed paths before staging (Foreign = sibling `touched.txt` claims − own ∪ agent), so sibling-staged paths are automatically excluded. The calling-skill diff-check (`git diff --cached --name-only` before `--blanket`) remains useful as a belt-and-suspenders: if unrecognized paths are staged and the sibling-subtract didn't catch them (TOCTOU edge), abort and surface to PM. The pre-check is no longer the sole mitigation — it is a secondary confirmation that the subtract worked as expected.

### Pre-staging reset hazard — `git reset` before explicit-path fallback

When `coordinator-safe-commit` fails mid-flight, the index may already carry foreign-orphan paths the helper staged during scope computation. The fallback recipe (`git add -- <paths> && git commit -m "..." -- <paths>`) trailing-pathspec scopes the **commit** but not the **index** — orphans staged by the failed helper remain in the index and leak into the next commit if the trailing `-- <paths>` is omitted on a later call. **Always run `git reset` (no `--hard`, no paths — clears the index, preserves the worktree) before the explicit-path fallback.** Then `git add -- <paths> && git commit -m "<subject>" -- <paths>` from a known-clean index. Symptom that motivates this recipe: helper exits non-zero, your next plain `git commit -m "..."` (no `-- <paths>`) lands foreign orphans under your subject.

### `git mv` + Edit ordering

`git mv <src> <dst>` stages the rename atomically. A subsequent `Edit` against `<dst>` mutates the working tree only — the staged rename is content-identical to `<src>`, and `git commit -- <dst>` lands the rename without the content change. **Correct order:** `git mv` → `Edit dst` → `git add -- <dst>` → `git commit -m "..." -- <dst>`. Reversed (`Edit src` → `git mv src dst`) is worse: the working-tree edit is silently abandoned by `git mv`, which moves the *index* version of `<src>`. `/pickup` Step 2 (Mutate and Commit) frontmatter-mutation pattern is the canonical example; the same trap fires anywhere a rename and a content edit ship in one commit. (Surfaced in a real incident, with a recurrence shortly after in a domain-plugin deployment.)

### Staged-but-uncommitted files can be absorbed by a concurrent session's blanket sweep

**On a shared work branch, staged-but-uncommitted files get absorbed by a concurrent session's blanket sweep — commit each chunk immediately (tight explicit-path add+commit), and verify that any diff-gate scope count is single-workstream before trusting it.**

*Empirical basis (a real incident from a domain-plugin deployment):* A `/update-docs` sweep commit absorbed C4-3 files that were staged-but-not-yet-committed between the `git add` and the `git commit` in a concurrent session. The content survived on-branch under the sweeper's commit subject, but per-chunk attribution was lost. Separately, a `review-brightline-gate.py --session-id` over-counted (1889 LOC / 10 commits) because both concurrent sessions resolved their session-id from the shared last-writer-wins `.current-session-id` sentinel, conflating their commits and firing a spurious PARTITION-MANDATORY verdict.

**Two rules triggered:** (1) commit each chunk immediately — a staged-but-uncommitted window of any duration on a shared branch is a sweep target; (2) when a brightline/diff-gate count looks inflated, scope it to your own files (e.g. `--session-id` or manually check `git log --oneline -- <your-paths>`) before acting on the verdict. Sister to § Atomic stage+commit gesture (the race window rule) and the `.current-session-id` sentinel note in SC-DR-009.

### Staged-but-uncommitted index is contestable — merges and sibling crash-recovery both absorb it

Beyond the blanket-sweep case above, a path-scoped `git add` left uncommitted in the shared index is claimed by two further concurrent mechanisms:

- **Partial-commit-during-merge.** While a merge is in progress, a path-scoped `git commit -- <p>` fails with *"cannot do a partial commit during a merge"* — but the preceding `git add` still STAGED the file. That staged file is then absorbed into whatever session concludes the merge, under the merge commit's subject. Verify staging state after a merge lands; do not assume a staged-but-uncommitted edit stayed yours to commit separately.
- **Sibling crash-recovery finalization.** Pre-staging files mid-ceremony (e.g. `git add`-ing a plan + completion entry during `/workstream-complete` *before* dispatching the code-reviewer, intending to fold them into the terminal commit) exposes them to a peer's crash-recovery heuristic: a concurrent EM sees staged-but-uncommitted files attributable to your session id, assumes your session crashed mid-ceremony, and commits them itself ("finalize peer &lt;sid&gt; crashed ceremony"). Even when the outcome is benign (files land on-branch), per-ceremony attribution is lost and the commit fires before your reviewer returns.

**Rule.** Keep stage+commit atomic (§ Atomic stage+commit gesture) and do NOT pre-stage ahead of a dispatch you intend to fold into a later commit. Stage a file only when you are about to commit it in the same Bash call. Sister to § Concurrent-executor commit absorption and the SC-DR-014 blanket-add floor.

### Atomic stage+commit gesture — tool-call boundaries are concurrency windows

Splitting `git add -- <paths>` and `git commit -m "..." -- <paths>` across two Bash tool calls opens a window in which a concurrent EM's `git add -A` / `coordinator-safe-commit --blanket` can sweep your staged index into their commit. Inside a single Bash call, treat stage+commit as one atomic gesture: `git add -- <paths> && git commit -m "<subject>" -- <paths>`. The trailing `-- <paths>` on `git commit` is non-negotiable **for hand-commits from the shared index where the index and worktree agree on your paths** — it scopes the commit by pathspec regardless of what else landed in the index between the `add` and `commit`, closing the cross-tool-call race window. (`lessons.md:43` — `--scope-from` fallback race documented; SC-DR-008 inversion driver.) **This is the agree-case discriminator of SC-DR-015, not a special exception to it** — the race this paragraph closes is real and the trailing pathspec still closes it, but only while index and worktree agree. If you deliberately staged something the worktree doesn't match (partial-hunk staging, `git apply --cached`, an automated op's private `GIT_INDEX_FILE`), dropping the trailing pathspec is instead the correct form — see SC-DR-015 and § The trailing pathspec reads the WORKTREE below.

### `git commit` without trailing `-- <pathspec>` is unsafe on shared branches

Path-scoped `git add` does not protect the commit. A concurrent EM's `git add -A` between your `add` and `commit` lands their staged files under your subject. **Always pass `-- <paths>` to `git commit` on shared branches when the index and worktree agree on those paths**, even after a clean `git add -- <paths>`. The trailing pathspec is the only deterministic scope guarantee under concurrent index mutation, for that case. Recurrence is the signal: this rule re-fires faster than the documentation reaches the EM at commit time — keep the trailing pathspec the default in skill bodies and dispatch prompts. **It stops being safe the moment you've deliberately staged content the worktree doesn't match** (SC-DR-015) — this framing is for the ordinary hand-commit case against an index that agrees with the worktree; index/worktree divergence for the named paths, whoever caused it, is the named carve-out — see SC-DR-015 and § The trailing pathspec reads the WORKTREE below.

### The trailing pathspec reads the WORKTREE — index/worktree divergence for the named paths must NOT pass it (FORWARD-B; generalized by SC-DR-015)

**Rule.** Both halves of the stage+commit gesture — `git add -- <paths>` and `git commit -m "..." -- <paths>` — read **working-tree** content for the named paths, not the index. The scoped-pathspec form closes absorption of a foreign *staged index entry* (§ Atomic stage+commit gesture, § `git commit` without trailing `-- <pathspec>` is unsafe on shared branches), but it does NOT close absorption of foreign *worktree* content sitting on paths you've deliberately staged something else onto.

**The triggering condition is index/worktree divergence for the named paths, whoever caused it — not "an automated op with a private index."** That framing was the boundary this section originally drew, and it is too narrow: an automated op holding its own private `GIT_INDEX_FILE` is one way to produce divergence, but a human EM produces the identical hazard by staging a partial hunk (`git apply --cached`) on the ordinary **shared** index — no private index involved. Whenever the index for a path holds content the worktree does not match, the trailing pathspec silently discards the divergence and re-reads the worktree instead. See SC-DR-015 for the full ruling and the discriminator to apply before choosing a commit form.

**Carve-out, not a reversal.** Once you've established the index and worktree diverge for your paths (correctly staged, correctly scoped), passing `-- <paths>` silently overrides your staging — it re-reads the shared worktree and absorbs whatever foreign edits happen to sit on those paths. So the trailing pathspec is not the fix here. **Neither is a bare pathspec-less `git commit` against the shared index** — that was this carve-out's original prescription (verify via `git diff --cached --name-only`, then commit with no pathspec) and it was withdrawn the same day, in the SC-DR-015 amendment below: the shared index stays mutable by peers between your check and your commit, a real TOCTOU window, not a theoretical one. The form that actually closes the hazard is a **private index**, isolated from concurrent mutation for the whole build-verify-land sequence — invoke `ceremony.scoped_git_commit` (the coordinator engine's op; it selects this mechanism automatically once it detects divergence, so you never classify the horn by hand) or hand-roll the recipe at § SC-DR-015 if the op isn't available. The scoped-pathspec guidance elsewhere on this page stays correct for the ordinary hand-commit case (index and worktree agree) — this carve-out applies only when you've deliberately created divergence.

*Empirical basis — two instances, no private index required for the second.* (1) The coordinator engine's `archive_and_commit` op followed exactly the recommended `git add -- <paths> && git commit -- <paths>` form and laundered 34 hand-edited memo frontmatter changes into commits stamped `[fleet.archive_actioned_memos]`. It held a private `GIT_INDEX_FILE` the whole time; the trailing pathspec overrode it. the engine repo named the hazard **FORWARD-B (worktree vector)** and amended its own decision record accordingly — FORWARD-B sits on the same DIRECTION axis: FORWARD is "op absorbs foreign *staged* work" (closed by the scoped pathspec); FORWARD-B is the same direction, different vector — foreign *worktree* content on paths the op owns. Their fix was subtractive: drop the trailing pathspec, let the private index be the scope. Adding `git add` in front does NOT help, for the reason above. (source: a cross-repo memo from the engine repo's EM.)

(2) A later incident, no private index at all: a human EM on this repo detected a hunk entanglement, unstaged the file, filtered the diff to its own hunk, and `git apply --cached`'d it so the ordinary shared index held exactly the right content — then ran `git commit -m ... -- <paths>` and the trailing pathspec discarded the careful staging, re-reading the worktree. Two hunks belonging to a concurrent session landed under the wrong subject. The detection was correct, the staging was correct, and the commit form threw the work away — see SC-DR-015 below for the ruling this incident produced.

**Sister sections.** § Atomic stage+commit gesture and § `git commit` without trailing `-- <pathspec>` is unsafe on shared branches both prescribe the trailing pathspec for the shared-index case this carve-out doesn't cover. § `git commit -- <paths>` pathspec silently drops modified-tracked files when mixed with new untracked files is a *different* hazard (pathspec/rename-detection asymmetry on mixed tracked/untracked state, not worktree-vs-index divergence) with a different remedy on a shared branch — its Discipline paragraph resolves to a **split, still-pathspec'd** commit (one commit per state, each keeping `-- <paths>`), not to dropping the pathspec. The bare-commit-from-staged-index shape ("let the staged index drive the commit") that section documents is a single-session-tree fallback only, not a second carve-out alongside this one.

### An EMPTY trailing pathspec means "whole index", not "nothing" — guard the empty case

The trailing `-- <paths>` guarantee above inverts dangerously when `<paths>` is empty. **`git <cmd> -- ` with zero trailing paths reverts to whole-index / all** — it does NOT scope to nothing. When code splits one path set into a narrower gate-scope set and a wider commit set (e.g. a swept-rename split, a deletion gate over a computed subset), the empty-subset branch is a footgun: emitting a bare `-- ` re-includes exactly what the scoping was meant to exclude, re-tripping the very hazard the split existed to prevent. **Rule.** Any code that computes a pathspec array and passes it to `git add`/`git commit`/`git diff -- "${arr[@]}"` MUST take an explicit skip-when-empty branch — never fall through to a bare `-- `. Corollary: relaxing a `>=1 path` precondition retroactively makes previously-safe empty-array expansions crash under `set -u` on bash < 4.4 — re-audit every array the old precondition guaranteed non-empty. (Source: `wsc-commit.sh` swept-rename split; F3 re-trip on the swept source. [universal])

### Concurrent-executor commit absorption — never call the helper in parallel

Parallel executors must NOT each call `coordinator-safe-commit` (or any touched-files-aware helper). Empirical failure mode (`lessons.md:207`, the absorbing commits): 4 of 6 simultaneous helper invocations bundled into one commit, 46 unrelated dirty files from concurrent workstreams swept under one bug-fix subject. **Pattern:** fan-out executors do their work and stop without committing; EM serializes commits with plain `git add -- <paths> && git commit -m "..." -- <paths>` after the fan-out completes. No-pathspec commits issued from inside a concurrent executor will absorb sibling pre-staged work — the helper's session-detection cannot win this race under N-way parallel callers (SC-DR-008 driver).

<!-- src: plan05-016 -->
**Named-skill instance — `/dogfood` tier commit discipline.** `coordinator:dogfood`'s super-skill is a concrete, named application of this pattern: commit doctrine is tier-dependent and EM-serial under fanout, non-negotiable. `--narrow` (single-committer tier) has the EM commit directly via `coordinator-safe-commit`. `--broad` and `--shakedown` (autonomous, multi-executor tiers) hold executors to edit-and-report only — no executor-side commit — with the EM serializing all commits at wave gates in a single fused Bash call. Same rule as above, restated per-tier so a skill author copying `/dogfood`'s shape doesn't have to re-derive it from the general principle.

### "no changes added to commit" — reflog probe before retrying

`git commit -m "..."` returning *"no changes added to commit"* when you know you just staged work means a concurrent session's commit landed between your `add` and `commit` and swept your staged index. The work is not necessarily lost — it survives in the reflog. **Probe sequence:**

```bash
git reflog --date=iso | head -20            # find the foreign commit's parent
git stash list                              # check for auto-stashed state
git fsck --lost-found                       # last-resort dangling-blob recovery
```

Identify the sibling commit; if it absorbed your files, those files are now in `HEAD` under the wrong subject — verify with `git show --stat <foreign-sha>`. Resolution: cherry-pick or amend the foreign commit's message (PM call), or revert+redo. Do NOT blindly retry `git add && git commit` — repeats the race.

### `git commit --amend` with no pathspec on a shared tree can destroy a sibling's already-landed commit


A confirmed real incident: a session "repaired" what it believed was its own mis-authored
commit subject by running `git commit --amend` with no trailing pathspec — on a shared branch,
`--amend` with no pathspec rewrites *whatever HEAD currently is*, which by that point was a
sibling session's already-landed commit. The amend silently destroyed the sibling's commit
message and content attribution. This is the same commit-hesitancy anti-pattern class as the
incident cited above (§ Touch-Tracker / orphan policy), but with `--amend` as the
destructive verb instead of a no-pathspec `add`/`commit` — **never run `git commit --amend`
without first confirming (`git show --stat HEAD`) that HEAD is actually your own most recent
commit**, not a sibling's, on any shared `work/*` branch.

### `@`-prefixed commit-subject corruption — a PowerShell here-string authored inside a POSIX-sh Bash tool


A fleet-wide defect observed on two independent commits across sessions: authoring a commit
message via a PowerShell here-string (`-m @'...'@`) inside the POSIX-sh **Bash tool** degrades
the leading `@` to a literal token in the committed subject line, because the Bash tool's shell
does not understand PowerShell's `@'...'@` here-string syntax — it's a cross-tool-shell-dialect
mismatch, not a `git` bug. **Rule.** Never author a commit message using PowerShell here-string
syntax when the invoking tool is the POSIX-sh Bash tool; use the single-quoted heredoc pattern
in § Commit Message Mechanics below instead, which is dialect-correct for the shell actually
running the command.

### Stage Bug-Sweep Fix Edits the Moment Each Lands

*Source: a real incident from a domain-plugin deployment.*

Unstaged edits are indistinguishable from unowned dirt on a shared branch. A sibling EM's authorized blanket-sweep ceremony (`coordinator-safe-commit --blanket` from `/update-docs`, `/workstream-start`, etc.) will absorb any unstaged changes it encounters — **unless** they are tracked in the sibling's own `touched.txt`. The `--blanket` path subtracts live-sibling-claimed paths (Foreign = sibling-claimed − own ∪ agent-claimed) before staging: paths the sibling session claims are unstaged via `git reset HEAD --` and left untouched. The residual hazard is a narrow TOCTOU window: if a sibling session claims a path in its `touched.txt` *after* the blanket sweep's Foreign set is snapshot but *before* the sweep's `git add -A` runs, the path can still be absorbed. This window is deliberately un-locked to preserve autonomy; the content survives in the tree even if attribution shifts. → see § Carve-Outs and Why for the full escape-hatch semantics of `COORDINATOR_BLANKET_ACCEPT_FOREIGN`.

**Rule.** Stage each bug-sweep fix edit immediately after landing it: `git add -- <edited-paths>`. Do not let fixes accumulate unstaged across tool calls on a shared branch. A staged fix is claimed; an unstaged fix is contestable. The sibling-subtract is a safety net, not a substitute for immediate staging discipline.

### Post-commit `git show --stat` verification on shared branches

Path-filtered `git status` lies under concurrent EMs — the filter hides foreign files the index actually carries. **After every commit on a shared branch**, run `git show --stat HEAD` and confirm the file list matches your intent. The unfiltered `git diff --cached --name-only` is the pre-commit equivalent. Subject says one workstream, diff contains another is the failure mode this catches — it's invisible without the post-commit audit.

### Sibling-sweep audit pass after high-concurrency dispatch (N>5)

After any fan-out with N>5 concurrent executors on a shared branch, run a `git log -p --since="<dispatch-start>"` audit before merging. Look for: commits whose diff exceeds the subject's stated scope (sibling absorption), "ghost" commits with no clear workstream attribution (helper-attribution race), and orphan files dropped by the touched-tracker. Recurrence rate is empirical: lessons.md:502 (a mise dispatch) and lessons.md:207 (a bug-blitz) both produced ghost commits at this scale. The audit is cheap (5-15 min `git log -p` read); the alternative is shipping cross-workstream contamination to main.

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

*Source: a real incident, since promoted to universal guidance.*

### EM hand-editing a file a dispatched agent is concurrently editing — the two-writer race on one file

The whole concurrency catalog above is EM-vs-EM (two interactive sessions sharing a working tree). There is a second two-writer shape that is NOT EM-vs-EM: the **EM and one of its own dispatched agents (review-integrator, executor) both editing the same file at the same time.** When the EM dispatches a review-integrator to fold findings into a plan/spec and then *also* hand-adds rows to that same file mid-flight, the two write streams race — and a commit fired between the two writes can capture both, silently producing duplicates (e.g. two AC rows with the same ID).

*Incident.* The EM hand-added AC rows to a plan while a dispatched integrator was adding the same rows; a mid-flight commit captured both write streams and landed duplicate AC IDs. It self-healed only by luck (the duplicate was visually obvious on the next read); the failure shape is silent.

**Rule.** When an integrator or executor owns a file for the duration of its dispatch, the EM **holds that file** — does not hand-edit it until the agent returns. Fold the EM's intended additions into the dispatch brief instead, or wait for the return and add them then. This is the same "active peer detected on `<path>` — pause edits on this surface" discipline as the EM-vs-EM § Large unstaged diff rule above, applied to the EM-vs-own-agent case: a file under active agent authorship is a contested surface even though the other writer is a subagent, not a sibling EM.

**Verify before committing any file an agent touched concurrently.** Run a uniqueness grep (duplicate IDs, duplicate rows, duplicate frontmatter keys) on the file before staging it. A self-dispatched agent's edits and the EM's edits both landing in one commit is the signature; the uniqueness grep is the cheap catch the luck-dependent visual read should not be relied on to replace.

*Source: sibling-repo `state/lessons.md` (central-promoted). Distinct from § Concurrent-EM Git Operations (EM-vs-EM commits) — this is the EM-vs-agent two-writer race on a single file.*

### Edit-out/commit/edit-back to scope a sibling's uncommitted change is unsafe

Manually editing a shared file to remove a sibling EM's uncommitted change, committing, then editing it back is a hazardous scope-isolation technique. If a concurrent session commits the sibling's change between your edit-out and your commit, your edit-out commit becomes a silent revert of their work when it lands. Prefer committing shared files wholesale when the sibling's change is a legitimate in-progress edit on the shared surface, or use `git stash push -- <file>` / `git stash pop` with explicit verification (see the stash-pop warning above). The edit-out/commit/edit-back pattern has no concurrency-safe execution window on a shared branch.

*Source: self `state/lessons.md` (central-promoted 2026-05-29).*

### Stash-pop primitive for cross-EM file isolation at dispatch time

The "active peer session" rule above is the read-side detect; this is the write-side hygiene when an EM dispatches an executor against a file a sibling EM has uncommitted edits in. **Sequence:** `git stash push -- <paths>` *before* the dispatch — captures the sibling's working-tree state out of the way; dispatch the executor against a clean version of the file; on executor return, `git add -- <paths> && git commit -m "..." -- <paths>` for your scope; then `git stash pop`. Without the stash, an `Edit`-then-`git add -- <path>` from the executor stages everything in the file — there is no partial-path-add escape, and your commit silently absorbs the sibling's hunks under your subject. Sibling's per-chunk commit attribution is preserved by the round-trip even if their changes shipped during your window (pop becomes a no-op; their already-committed work is unaffected). Surfaced by multi-src C3 vs sibling C6 on `mcp/project_rag_server.py` + `paths.py`.

### Pause-snapshot attribution trailer

PM-directed "pause and snapshot" blanket commits (intentional working-tree captures across sibling EMs) are legitimate, but they launder unauthorized substrate changes into history if the commit message attributes them via narrative prose. an incident commit on a sibling repo captured ~940L of `cli.py` deletion (engine-index/doctor/bp-lint/probe-readiness) with no plan-or-handoff authorization in either repo; the commit message's "Spans Wave-2b cli.py port-out" attribution was author reconstruction, and three EMs each surveyed and disclaimed authorship. **Schema:** pause-snapshot commits carry a structured `Substrate-changes-attribution:` trailer. Each path-cluster that the snapshot touches gets a named source (handoff path, plan SHA, sibling EM session id) OR the literal value `unattributed` if no source can be cited. Downstream readers MUST NOT accept narrative-prose attribution at face value; the structured trailer is the only auditable record. The point of `unattributed` is to make the absence-of-attribution explicit rather than concealed in prose — surfaces forensic auditing during merge-to-main review.

Trailer example:

```
Substrate-changes-attribution:
  server.py: handoff state/handoffs/<workstream>/multi-src.md
  cli.py: unattributed
  scripts/download-*: handoff state/handoffs/<workstream>/addon-pickup.md
```

(Surfaced by the incident commit post-mortem.)

### `git commit -- <pathspec>` drops mixed new+modified-tracked files silently

`git commit -m "..." -- <paths>` applies the pathspec as a *filter on the index*, and the filter interacts with file state in a way that silently drops paths. When `<paths>` mixes brand-new (untracked-but-just-`git add`ed) files with already-tracked-modified files, a pathspec-scoped commit can land the tracked modifications but omit the new files (or the reverse) depending on what was staged at commit time — the commit subject claims the full set, `git show --stat HEAD` shows a subset. **Rule.** After any `git add -- <paths> && git commit -m "..." -- <paths>` that mixes new and modified-tracked files, run `git status` and `git show --stat HEAD` and confirm every intended path landed; a `commit-message-says-X-but-diff-says-Y` gap is the silent failure shape. Pairs with § "Post-commit `git show --stat` verification on shared branches" — that rule catches sibling absorption; this one catches your own pathspec dropping a path it should have carried. (source: a real incident on a sibling repo.) **Same underlying bug as** § "`git commit -- <paths>` pathspec silently drops modified-tracked files when mixed with new untracked files" below — that section's Discipline paragraph gives the shared-branch-safe fix (split into two scoped, still-pathspec'd commits), which composes with the post-commit verification here rather than replacing it.

### Exec-bit does NOT survive a pathspec commit — chmod the worktree, not just the index

`git update-index --chmod=+x <path>` sets the executable bit *in the index only*. A subsequent `git commit -m "..." -- <path>` (trailing pathspec) **overrides the staged index mode with the worktree mode** — so if the worktree file is still mode `0644`, the committed blob is `0644` and the `--chmod=+x` is silently discarded. The exec bit appears set right up until the pathspec commit unsets it. **Rule.** To ship an executable bit, `chmod +x <path>` on the *worktree* file (not just `git update-index --chmod`), then commit; verify the committed mode with `git ls-tree HEAD -- <path>` (expect `100755`, not `100644`). Distinct from § "`git mv` + Edit ordering" (working-tree edit vs staged rename) — this is the file *mode* being sourced from the worktree at pathspec-commit time, the same way file *content* is. (source: a real incident.)

### Smoke-testing commit primitives without `--dry-run` is the executor failure the gate prevents

Running `coordinator-safe-commit` (or a bare `git commit`) to "see what it does" on a live shared tree — without `--dry-run` — is the same eager-helpful pattern the scope gate exists to catch in executors: a smoke test that actually commits absorbs whatever is dirty/staged in the tree into a throwaway commit under a meaningless subject. **Rule.** Probe commit primitives with `--dry-run` (`coordinator-safe-commit --dry-run "subject"` shows the staged+computed scope without committing); never invoke a real commit to inspect behavior on a shared branch. The dry-run path is the designed inspection surface — see § "Dry-run preview". (Source: the meta-repo.)

### Rename pathspec must include both sides

`git mv A B && git commit -- B` leaves A's staged deletion *orphaned* — the commit applies pathspec `B` only, so the deletion of `A` remains in the index after the commit and surprises the next `git status`. Pathspec must enumerate both sides of the rename: `git commit -- A B`. Distinct from § ``git mv` + Edit ordering` above, which is about working-tree edit ordering around the rename; this is about commit-scope enumeration after the rename is staged. Existing `feedback_git_commit_explicit_path` covers pathspec discipline generally but doesn't enumerate the rename-shape gotcha — recurring on a `git mv` within a scoped commit in a domain-plugin deployment.

---

## Plugin Distribution Note

The upstream plugin source lives in the doctrine-authoring repo, resolved via the standard `--plugin-dir` mechanism. All structural files (touch-tracker hook, `coordinator-safe-commit`, the engine's `check_validate_commit` extension) sync to the upstream source — other machines pulling this plugin pick them up on next reinstall. The wiki guide (`docs/wiki/scoped-safety-commits.md`) and memory entries live in the consuming project's user tree and do NOT sync upstream by design. This file is not part of the plugin distribution.

---

## Related Artifacts

| Artifact | Path |
|----------|------|
| Touch-tracker hook | `${CLAUDE_PLUGIN_ROOT}/hooks/scripts/track-touched-files.py` (native successor to an earlier shell-script implementation) |
| Commit helper | the coordinator engine's `coordinator/bin/coordinator-safe-commit` |
| Session lib | `coordinator_core.session` (native successor to an earlier shell-script implementation) |
| Sibling: branch discipline | [`daily-branch-discipline.md`](./daily-branch-discipline.md) — enforces commit *location* (branch); this page enforces commit *content* (files). Both hooks share the PreToolUse Bash matcher. |

---

## Decision Records

**SC-DR-001 — Bash writes excluded from touch-tracker hook**

*Problem:* Should the hook parse Bash tool calls to detect write effects (heredocs, redirections, `tee`, etc.)?

*Decision:* No. Parsing arbitrary shell for write effects is unsound and creates a growing regex catalog with false confidence. mtime fallback at commit time is the sole Bash-edit detector. Intentional gap documented here rather than papered over with an unsound heuristic.

*Alternatives considered:* Bash-write heuristic regex (rejected — too many edge cases). Requiring explicit `git add` for all Bash-driven edits (acceptable fallback, documented in Troubleshooting).

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

*Decision:* Use `agentId` (opaque, mechanical, durable per Probe 0.3 — 12+ char lowercase hex). (Named-teammate shape: `<name>@session-<short>`. Falsified for named Agent-Teams teammates: the hex-only shape does not match named-teammate ids; guards must accept both patterns.) Two mechanical writers (EM-side + subagent-side hooks) and a back-pointer file. No executor cooperation, no LLM-driven recording, no env vars.

*Alternatives considered:* Original Option 1 (parent_session_id from PostToolUse) — falsified by Probe 0.1, no parent pointer in subagent JSON. Env-var threading — not propagated. Sentinel-only resolution — overwritten by sibling SessionStart (Issue C surface).

**SC-DR-005 — Agent-id union skipped in `--scope-from` mode**

*Problem:* Should the agent-id read path apply to `--scope-from` (workstream-anchored) commits as it does to default-mode commits?

*Decision:* No. Per the Issue C contract, declared scope is exhaustive — out-of-scope dirty files fail the commit. Implicitly unioning agent-id-touched paths into a `--scope-from` commit would contradict that contract and reintroduce the silent-scope-drift bug at the workstream-transfer surface.

**SC-DR-006 — `--expected-branch` is helper-side, not doctrine-only — SUPERSEDED by M4**

> **Superseded, not deleted.** Per the PM's commit-model ruling (AC6, the subagent
> commit model) and the coordinator engine's M4 enforcement gate, executors no longer commit at all — this
> decision's premise (that *some* executor-side commit path needs a deterministic branch guard)
> no longer holds. Kept here for the decision trail; do not cite as current doctrine.

*Problem:* Wrong-branch commits from agents whose dispatching EM didn't verify branch state. Doctrine alone hadn't held.

*Decision:* Add `--expected-branch <name>` as a hard gate inside `coordinator-safe-commit`. Helper aborts before staging on mismatch.

*Alternatives considered:* Standing-order convention in agent prompts — rejected, executors are LLM agents and forget. Pre-dispatch verification by EM only — rejected, trust the deterministic surface, not the cooperative one.

**SC-DR-007 — Doctrine strike requires 5 burn-in cycles**

*Problem:* When can the troubleshooting note about "helper misidentified your session" be removed from the wiki?

*Decision:* After 5 successful default-mode dispatch+commit cycles logged to a burn-in ledger. Replaces the original fuzzy "one verification session" wording.

**SC-DR-008 — Default/fallback inversion: plain git is the default, helper is for sweep ceremonies + executor branch-gate — carve-out (2) SUPERSEDED by M4**

> **Carve-out (2), the executor branch-gate, is superseded, not deleted.** Per the PM's
> commit-model ruling (AC6) and the coordinator engine's M4 enforcement gate, `agents/executor.md`
> no longer commits — it writes/edits and reports back, the EM commits. The `--expected-branch`
> bypass this carve-out names has no caller left. Carve-out (1), the sweep-ceremony `--blanket`
> allow-list, is unaffected (those are EM-driven ceremonies, not subagent self-commit). See
> § 8 above and M4.

*Problem:* Three rounds of patching `coordinator-safe-commit` (SC-DR-001…007) did not converge. New failure modes appeared within weeks of each round:

- 2026-05-04 — session-detection inversion: helper attributed Session A's explicitly-staged files to a concurrent session B and absorbed two of B's orphan files into A's commit (`feedback_safe_commit_unreliable.md`).
- 2026-05-06 — parallel-executor concurrent-commit absorption (`lessons.md:207`, the absorbing commits): 4 of 6 simultaneous `coordinator-safe-commit` calls bundled into one commit; 46 unrelated dirty files from concurrent workstreams swept under one bug-fix message.
- 2026-05-08 — `--scope-from` fallback race (`lessons.md:43`): documented fallback (`git add -- <paths>` + plain commit) is non-atomic; a 14-file index was swept by a concurrent commit between the `add` and the `commit`.
- 2026-05-13 — silent-no-op recurrence #2 (`coordinator-improvement-queue.md` line 7): helper printed "files I'm leaving alone" and exited 0 without committing or signalling failure.

The PM-accepted empirical rule (`feedback_safe_commit_unreliable.md`) was already plain-git-as-default; doctrine had not caught up. Twelve+ skill/command/hook/pipeline call sites still invoked the helper as their primary commit path, none of them in a regime where the helper's touched-files heuristic actually fit.

*Decision:* Invert the default. **Plain `git add -- <paths> && git commit -m "<subject>" -- <paths>` is the doctrinal default for scoped commits.** `coordinator-safe-commit` is reserved for:

1. **Sweep ceremonies (`--blanket`):** `/workstream-start`, `/update-docs` (Phase 0, 8b, 9), `pipelines/relay-protocol.md`, `pipelines/artifact-distillation/PIPELINE.md`. Each runs a single executor serially per ceremony — the lessons.md:207 concurrent-callers mechanism cannot arise. `--blanket` gate accepts `CLAUDE_INVOKING_COMMAND ∈ {workstream-start, update-docs, relay-protocol, distillation}`. (`/workday-complete` was removed from this list — it migrated to `workday-complete-step2_5-dirty-tree.py` and no longer uses `--blanket`.)
2. ~~**Executor branch-gate (`--expected-branch`):** `agents/executor.md` only, preserved per **SC-DR-006** — only the bash helper fails-closed on wrong-branch; LLM executors are non-deterministic and cannot enforce branch gating via doctrine alone.~~ **SUPERSEDED by M4 (the PM's commit-model ruling) — the executor no longer commits, so this carve-out has no caller.**

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

*Empirical basis (a real incident from a domain-plugin deployment):* C8-3/C8-5/C8-5b all edited `ExecFlowLowering.cpp`, which a concurrent switch-timeline-mappers session kept leaving uncommitted SW-3/TL-3 work on. Three commits absorbed sibling hunks; each carried a NOTE crediting the workstream. Sister to § SC-DR-010 (path-scoped add doesn't scope hunks within a file) — this is the procedure when SC-DR-010 applies and interactive hunk selection is unavailable.

## SC-DR-010 — Path-Scoped `git add` Does Not Scope Hunks Within a File

*A real incident on a sibling repo's addon:* `git add -- path/to/file.py` stages the ENTIRE file, not just the hunks your executor edited. If another concurrent session also edited that file, its hunks ride your commit. The scoped-commit discipline protects against cross-file contamination but does NOT protect against cross-hunk contamination within a shared file. When a file you edited is also in another session's declared scope, use `git add -p -- path/to/file.py` (interactive hunk selection) to stage only the hunks from your changes. Treat `Edit` + path-scoped `git add` on a contested file as blanket-staging by another name — it includes every modification on disk at commit time, not just yours. (source: a real incident on a sibling repo's addon)

## SC-DR-011 — Shared Registration/Index File: Absorbed Edits Can Ship an Untracked-Import HEAD

*A real incident on a sibling repo's addon:* Committing a shared registration file (a hookimpl list, plugin registry, module index, `__init__.py`) with `git add -- <path>` is the SC-DR-010 hunk-contamination hazard with a second-order failure: the absorbed sibling edits frequently introduce `import` statements whose target modules are still `??` untracked. The resulting commit ships a HEAD that imports modules absent from git — a latent broken-clean-install, invisible on the author's disk and (if the loader graceful-fails on `ImportError`) a silent non-registration on a clean checkout.

Incident: tc-34 the incident commit was the first to land four chunker-spec registrations because `git add -- __init__.py` swept in three concurrent sessions' (tc-35/tc-5/tc-6) uncommitted edits; all four target modules were untracked, so HEAD imported four nonexistent-in-git modules.

**Rule — before committing any shared registration/index/`__init__` file under concurrent EMs:**
1. `git diff --cached --name-only` to see the FULL absorbed set (the SC-DR-010 / H1 baseline — never skip it on a shared file).
2. For every new `import` / `from … import` the commit introduces, confirm the target module is `git ls-files`-tracked. An import of an untracked sibling module is a HEAD-break, not a harmless extra.

Fix-forward when you find absorbed registrations: commit the referenced impls+tests too (if complete and green on disk) — turn the latent break into a real landing, don't revert the registration. This is the *committing-EM-as-victim-of-absorption* direction; the inverse (a sibling's session-end absorbing YOUR edit) is the complementary hazard, catalogued elsewhere. (source: a real incident on a sibling repo's addon.)

## SC-DR-013 — A `git checkout HEAD` Discard Can Resurrect via a Later `git stash pop` Into a Publish

*Source: the meta-repo. [universal]*

During a release, an unreviewed change was discarded via `git checkout HEAD -- <paths>`. Later, a `git stash pop` (the stash had captured the discarded change before the checkout) returned it to the working tree. Because the subsequent publish/percolate script copied from the **working tree** (not from a committed ref), the resurrected change percolated to the OSS repo unnoticed — caught only at cleanup.

**Rule.** A `git checkout HEAD` discard is not durable across a stash round-trip. Before any publish/percolate operation that copies the **working tree** (vs. a committed ref): re-diff the tree against HEAD (`git diff -- HEAD`) to check for changes you thought you discarded. Or publish from a committed ref explicitly, not from `$PWD`. Composes with §36 (stash-pop-after-no-op applies stale unrelated stash) — the resurrection mechanism is the same.

## SC-DR-012 — A Pre-Commit "No Stray Staged" Check That Prints But Doesn't Halt Is Theater

*A real incident from a domain-plugin deployment:*

## concurrent git add -A silently absorbs in-flight executor output

A concurrent `git add -A` sweep (lint, format, or distill ceremony) on the shared branch silently absorbs another EM's in-flight executor output — files the other executor just wrote get committed under the sweeping EM's name before the executor has a chance to commit them. Rule: commit each chunk scoped + immediately after the executor returns; verify on disk not chat. Apply: after every executor returns, run `git diff --stat` to confirm expected files are present, then commit with explicit paths `git add -- <paths>` before doing any broad sweep.

**A pre-commit "no stray staged" check that prints but doesn't halt is theater.** Under concurrent EMs, the check must unstage or abort on detection — echoing the offending path then committing anyway (the `grep … || echo` shape) re-attributes a sibling's work.

### Scoped `git add -- <paths>` silently absorbs pre-staged orphan operations from concurrent sessions

*Source: a real incident on a sibling repo. [universal]*

**Rule.** Scoped `git add -- <paths>` controls only what gets staged in *this* call. Pre-staged operations (a `git rm` deletion, an `add` from a concurrent session) are already in the index, and a subsequent `git commit -- <paths>` does NOT confine the commit to your pathspec when sibling ops are already staged — the orphan op rides along into your commit. Visible only post-facto in `git show --stat <sha>`.

*Case.* An RSS-cap commit used `git add -- <explicit-paths>` (correct discipline) but a concurrent session's handoff-archival flow had already staged a `git rm` of an unrelated handoff file. The deletion rode into the RSS-cap commit as a `delete mode` line for a file the workstream had no business deleting. (a real incident on a sibling repo)

**Discipline.** Between scoped safety-commits on a shared branch:
1. Run `git diff --cached --name-only` to enumerate the FULL staged set (not just your scope).
2. If anything is staged that isn't yours, either (a) `git reset HEAD -- <foreign-path>` to unstage before committing, or (b) push the orphan op into its own scoped commit first.

The existing "explicit paths only" language doesn't cover this pre-staged-orphan interaction — the `git diff --cached --name-only` pre-check is the fix.

### `git commit -- <paths>` pathspec silently drops modified-tracked files when mixed with new untracked files

*Source: a real incident on a sibling repo. [universal]*

**Rule.** Naming both modified-tracked and new-untracked paths in the same `git commit -m "..." -- <paths>` invocation reliably commits only a subset — often only the new files. The trailing-pathspec scope guarantee assumed elsewhere on this page is asymmetric to the index/worktree state of each named path; mixing the two states in one pathspec breaks the guarantee. **Do NOT fix this by dropping the trailing pathspec** — a bare `git commit -m "..."` (no `-- <paths>`) commits the *entire* staged index, which on a shared branch absorbs whatever a sibling session has pre-staged (§ "Scoped `git add -- <paths>` silently absorbs pre-staged orphan operations" above; § "Always pass `-- <paths>`" below) — trading a mixed-pathspec drop for a strictly worse foreign-absorption hazard. The correct remedy is the split-commit form in the Discipline paragraph immediately below: two scoped commits, each with its own trailing pathspec, one for the modified-tracked paths and one for the new-untracked paths.

*Case.* daemon-perf C5 named 7 paths in one `git commit -- <paths>` invocation; only 3 committed. The 4 silently-dropped files were the modified-tracked ones (likely a Git-for-Windows pathspec interaction with rename-detection on the mixed state). The dropped files looked committed in chat reasoning and were caught only by post-commit `git show --stat HEAD`. (a real incident on a sibling repo)

**Discipline.** On a shared branch — the default case in this repo (concurrent EM sessions are routine, not an edge case) — split the modified-tracked and new-untracked paths into **two scoped commits, each with its own trailing pathspec**: `git add -- <modified-paths> && git commit -m "<subject>" -- <modified-paths>`, then the same for `<new-paths>`. Each commit keeps the trailing-pathspec scope guarantee against foreign staged content; splitting avoids the mixed-state drop this section documents. The bare `git add -- <all-paths> && git commit -m "<subject>"` (no trailing pathspec, "let the staged index drive the commit") is a fallback for a genuinely single-session tree only — on a shared branch it reintroduces the foreign-staged-absorption hazard the trailing pathspec exists to close (§ "Always pass `-- <paths>`" below). Composes with § Post-commit `git show --stat` verification on shared branches (the catch when the mixed-pathspec trap fires anyway) and § Atomic stage+commit gesture (stage+commit for each split commit still runs in one Bash call each).

*Incident.* A broad `git add tasks/ docs/` swept a concurrent EM's plan and a 29K-line `diff.patch` into a distill commit. The grep flagged the offending paths; the commit ran regardless; fix-forward `git rm --cached` recovered — but the commit had already landed on the shared branch.

**Rule:** gate the commit on the check's exit (non-zero → abort), or stage by explicit file list only — a directory-scoped `git add` is never safe on a shared branch. A check that only prints is identical to no check for the commit that follows it. Extends the Why-This-Exists § concurrent-EM hazard catalog.

### SC-DR-014 — Unambiguous-command-class PreToolUse blocks skip the Phase-5 soak gate

**Ratified-by:** PM, following 4 cross-contamination incidents in one day.

**Decision.** A PreToolUse Bash hook that pattern-matches an unambiguous command-construction class may ship in deny-mode from day one, bypassing the SC-DR-003 / Phase-5 Readiness warn-first soak gate, **iff all three of the following hold:**

1. **Literal pattern-match on command tokens.** The hook's deny condition is a literal-string or short-regex match against the Bash command string, with no semantic interpretation.
2. **No per-session state computation.** The deny decision does not depend on `touched.txt`, `coordinator-sessions/`, session-id resolution, scope-membership math, or any other per-session state — i.e., the same command from any session yields the same outcome.
3. **Zero documented legitimate in-repo use outside the override env var or helper-internal marker env var path.** All sanctioned uses of the matched pattern are reachable through the override env var (or a helper-internal marker env var). No skill, hook, or workflow legitimately needs the raw pattern outside those override paths.

**Rationale.** The Phase-5 soak gate (SC-DR-003) was designed for the *scope guard* in `validate-commit.sh` Check 5, which performs a non-trivial scope-membership computation against `touched.txt`. That computation has real false-positive risk (session-id misidentification, orphan-class warnings, stale sentinel state) — the 14-day soak existed to bound it empirically. An unambiguous-command-class block has near-zero FP risk by construction; soaking a block whose FP rate is ≈0 wastes the 14 days during which the bug it prevents continues to occur.

**Qualifying example.** `block-blanket-git-add.sh` (folded into the coordinator engine's `coordinator_core.bash_guards` via `preuse-bash-dispatch.py`; the old shell-script version removed) (BLOCK-BLANKET-GIT-ADD tripwire) satisfies (1) literal `git add -A` / `git add -u` etc. pattern; (2) cwd-equality + env-var checks only, no per-session state; (3) the only legitimate blanket-add paths are `coordinator-safe-commit --blanket` (carve-out — uses helper-internal marker env var `_COORDINATOR_SAFE_COMMIT_INTERNAL_BLANKET`) and emergency callers (carve-out — uses public override env var `COORDINATOR_OVERRIDE_BLANKET_ADD=1`). Both satisfy criterion (3) — each reachable through the override env var or helper-internal marker env var path. Ships deny-from-day-one.

**Non-qualifying counter-example.** A hypothetical `block-git-push-force.sh` would satisfy (1) and (2) but fail (3): `git push --force-with-lease` has documented legitimate cross-branch sync use cases outside any override path. Such a block must go through the Phase-5 soak gate, not under SC-DR-014.

**Doctrine pointer.** SC-DR-003 (Phase-5 soak) still governs scope-membership-class blocks. SC-DR-014 carves out *only* unambiguous-command-class blocks. The two are complementary; SC-DR-014 does not amend or weaken SC-DR-003 for its actual domain.

**Superseded in scope by SC-DR-016 below.** Criterion (1) here reads on the Bash command string, which is one instance of the real discriminator, not the discriminator itself. A guard that qualifies under this record still qualifies; a guard that reads structured content rather than a command string is ruled by SC-DR-016, not by stretching this one.

### SC-DR-015 — The trailing pathspec is a proxy for scope, valid only while index and worktree agree

**Ratified-by:** EM, following the incident described below. Break-class
correctness fix under the EM engineering remit — not PM-ratified. SC-DR-008's PM ruling is narrowed
by a condition, not reversed, and the blanket-add prohibition is untouched; a PM overturn of this
discriminator would restore an empirically-demonstrated data-loss path.

**The ruling.** `git commit -- <paths>` commits **worktree** content for those paths and **bypasses the index**. `git commit` with no pathspec commits **the index** — including any path a concurrent session staged. Neither form is unconditionally safe on a shared tree; they fail in opposite directions.

**The trailing pathspec is not the scope guarantee — it is a cheap proxy for one, and the proxy is only valid while the index and the worktree agree on those paths.** Choose by that condition, which you can always check:

- **Index and worktree agree for your paths** (you edited, you staged, nothing else changed them) — the common case. Keep `git add -- <paths> && git commit -m "<subject>" -- <paths>` as a single atomic Bash call. SC-DR-008 is unchanged here: the trailing pathspec still closes the concurrent-`git add -A` race across the stage→commit window, and that race is real.

- **You deliberately staged something the worktree does not match** — partial-hunk staging, `git apply --cached`, or any file where a peer's uncommitted edit sits alongside yours. Here the trailing pathspec **destroys your staging silently**. **Do not fall back to a pathspec-less `git commit` on a shared branch** — see the amendment immediately below; use a private index.

**Read this before following the bullet above.** Committing from the shared index with no pathspec, even after proving the staged set is yours via `git diff --cached --name-only`, does not close the hole: the index is shared across concurrent sessions, so a peer can stage between your check and your commit — a real TOCTOU window, not a theoretical one.

**So on a shared branch there are not two options, there is one.** For the genuinely-diverged case, isolate the commit from the shared index entirely with a private one:

```bash
OLD="$(git rev-parse HEAD)"                               # resolve HEAD exactly once
TMPIDX="$(git rev-parse --git-dir)/tmp-index-$$"
cp "$(git rev-parse --git-dir)/index" "$TMPIDX"
GIT_INDEX_FILE="$TMPIDX" git reset -q HEAD -- .          # drop every peer entry
GIT_INDEX_FILE="$TMPIDX" git add -- <your-paths>          # or update-index for a hand-built blob
TREE=$(GIT_INDEX_FILE="$TMPIDX" git write-tree)
NEW=$(git commit-tree "$TREE" -p "$OLD" -m "<subject>")
git update-ref -m "<subject>" HEAD "$NEW" "$OLD"          # compare-and-swap: fails if HEAD moved
rm -f "$TMPIDX"
```

Two things about this sequence that are easy to get wrong:

- **Resolve `HEAD` once and pass it through, and land with the 4-argument `update-ref`.** A tempting shorthand is `git commit-tree "$TREE" -p HEAD -m "<subject>"` followed by the 2-argument `git update-ref HEAD <new>`. Don't — that resolves `HEAD` a second time, independently, at landing, and the 2-argument form writes whatever value you give it with no check that `HEAD` still points where you think. If a peer commits in the window between building `$TREE` and landing it, that second resolution silently lands your commit on top of a `HEAD` your composed tree never accounted for — and because the peer's commit is still reachable from the branch, nothing about the result looks wrong; the peer's changes are simply gone from the tip your commit describes. The 4-argument form — `git update-ref HEAD "$NEW" "$OLD"` — is a compare-and-swap: it only moves `HEAD` if `HEAD` still equals `$OLD`, and fails loud with a nonzero exit otherwise. **If it fails, stop and rebuild from scratch — re-resolve `$OLD`, redo the private-index staging, recompute `$TREE`, recompose `$NEW` — rather than retrying the same `update-ref`.** The tree you already built was composed against the stale parent; retrying the landing step alone re-lands a commit whose parent no longer matches reality.
- **`git commit-tree` fires no hooks at all** — not `pre-commit`, not `commit-msg`, and not `prepare-commit-msg`. If your repo's `prepare-commit-msg` hook stamps trailers into every ordinary commit (for example a session or deliverable identifier), a commit made this way will not get them; the plumbing path bypasses the entire hook chain by design. Reproduce whatever the hook would have added directly in the `-m` message (or write the message to a file and pass it via `-F`) before calling `commit-tree`, rather than assuming it will be added for you.

Verified clean on both axes: it neither reads the worktree nor touches the shared index, and it leaves a peer's staged entries and worktree edits exactly as it found them. The agree-case bullet above is unaffected — the ordinary `git add -- <paths> && git commit -- <paths>` remains correct and is still the overwhelmingly common path.

**This wanted a tool, not a third prose rule — and now has one.** Requiring an operator to hand-assemble a private index mid-commit was the same failure shape SC-DR-015 exists to name: a rule discharged by remembering. The discharge is `ceremony.scoped_git_commit` (`coordinator_core/ops/ceremony/scoped_git_commit.py`): it takes the path set, fails loud on an empty set or a directory pathspec, and computes the branch itself from `diverging_paths()` (`coordinator_core/git/divergence.py`) rather than asking the caller to classify the horn — agree takes `git add -- <paths> && git commit -F <msg> -- <paths>`; diverge takes the private-index sequence above (HEAD captured once, `commit-tree -p <old>`, 4-argument compare-and-swap `update-ref`). **Prefer the op over hand-rolling the recipe.** Where the op isn't reachable, the recipe above is still correct — it's what the op implements — but "not partial-staging on a shared tree" is no longer the fallback advice; call the op.

**Never resolve this by widening.** `git add -A` / `git add .` / `git commit -a` remain hard-denied (SC-DR-014's structural floor stands, unchanged). This ruling makes scoped committing *safer*, never optional.

**What this supersedes and what it leaves standing.**

- **SC-DR-008 is narrowed, not reversed.** Its default form remains correct for the agree-case, which is most commits: the trailing pathspec closes the sibling-staged-entry hazard there, and the `git diff --cached --name-only` check closes it in the diverge-case.
- **SC-DR-014 is untouched.** It rules on why the blanket-add hook could skip the warn-first soak gate. It says nothing about commit form. Anything citing SC-DR-014 as the source of the *scoped-commit form* is mis-citing it — the form is SC-DR-008.
- **FORWARD-B is general, not scoped to automated tooling.** § The trailing pathspec reads the WORKTREE — the hazard fires whether or not a private `GIT_INDEX_FILE` is in play, whether the caller is an automated op or a human staging a partial hunk on the shared index directly. The condition is index/worktree divergence, whoever caused it; the private-index op is one instance, not the boundary.

**Empirical basis.** A real incident in the engine repo: the EM detected the entanglement, unstaged the file, filtered the diff to its own hunk, and `git apply --cached`'d it so the index held exactly the right content — then ran `git commit -m ... -- <paths>` and discarded all of it. Two hunks belonging to a concurrent session landed under the wrong subject. Auto-push had already fired, so the commit was left in place (rewriting shared history is the worse failure) and a cross-repo memo was sent to flag the absorbed hunks.

The detection was correct, the staging was correct, and the commit form threw the work away. That is the signature of a rule whose discharge depends on the operator remembering an unwritten precondition.

<!-- spec-backlink: run 2026-08-06-14h38, nugget c8-035 -->
**One mechanism spans multiple failure shapes: the trailing pathspec makes git read the worktree, for every attribute of the named paths.** `git commit -- <file>` re-reads the worktree *mode*, silently reverting a staged `100755` (§ Exec-Bit Mechanics below). It also re-reads worktree *content*, both over a private `GIT_INDEX_FILE` (§ The trailing pathspec reads the WORKTREE) and over a hand-staged partial hunk on the shared index. SC-DR-015 is stated as a condition on the form, not a per-case exception, precisely because the mechanism is single and general. **§ Exec-Bit Mechanics Option B below reuses this section's private-index mechanism for that reason** — read it once you reach that section rather than re-deriving it.

<!-- spec-backlink: run 2026-08-06-14h38, nugget c8-033 -->
**Live guard for the diverge-case: `OFFER-PATHSPEC-DIVERGENCE`.** The control-plane engine ships a PreToolUse guard that detects index/worktree divergence for the paths a `git commit -- <pathspec>` is about to touch and offers the index-scoped form (the private-`GIT_INDEX_FILE` recipe above) as an alternative — an **advisory offer, not a block**: the operator still chooses the form. This is the operational counterpart to the SC-DR-015 ruling above — the guard surfaces the precondition the operator would otherwise have to remember unwritten.

### SC-DR-016 — The deny-from-day-one class is the self-contained oracle, not the command string

**Ratified-by:** PM, 2026-08-01, on an ask raised from the control-plane engine side. Generalizes
SC-DR-014's class; does not weaken SC-DR-003 for its own domain.

**Decision.** A guard may ship in deny-mode from day one, bypassing the SC-DR-003 / Phase-5
warn-first soak gate, iff its **oracle is self-contained** — the deny predicate is evaluated
purely over content that the write or the commit itself carries, with **no live state
consulted** — and SC-DR-014's criteria (2) *no per-session state computation* and (3) *zero
documented legitimate use outside an override path* hold unchanged.

"Live state" means anything the guard has to go outside its own payload to read: the working
tree, the git index, prior commits, sibling records, `touched.txt`, session registries, the
clock, the network. A guard that only inspects the bytes it was handed cannot be wrong about
what it was handed.

**Why this is the real line.** SC-DR-003's soak gate exists to bound an empirically-unknown
false-positive rate. A self-contained oracle's FP rate is ≈0 *by construction*, because the
evidence and the subject are the same object — nothing can drift between reading the evidence
and applying the verdict. A live-state oracle's FP rate is unknown by construction, because the
state it reads can change independently of the thing it is judging. That is the property
SC-DR-014's criterion (1) was gesturing at; "literal match on the Bash command string" is one
instance of a self-contained oracle, not the class.

The engine had already reached this conclusion in code without a doctrinal home:
`coordinator_core/bash_guards/commit_tripwires.py` (Check 12 commentary) reasons that Check 12
may hard-deny because "its oracle is a pure set-diff over this commit's own staged content —
false-positive rate is ~0 by construction," while a check whose oracle is "a live git-state
comparison (two `git diff` invocations) with real false-positive surface" is "exactly what
SC-DR-003's warn-first soak gate exists for." This record ratifies that reasoning as doctrine.

**Condition of ratification — the escape hatch is not optional.** A guard shipping deny-from-
day-one under this record must mint a public override env var and register it in the
guard-override-keys reference table in the same change. SC-DR-014's criterion (3) is *defined*
in terms of an override path; a deny with no hatch does not satisfy it and does not qualify here.
Shipping without one is a design decision that needs its own ruling, never a silent omission.

**Qualifying example.** The roadmap-baton required-graph-fields write guard
(`_cf_spinoff_roadmap_requires_graph`). It parses the frontmatter the write itself carries and
branches on `kind == roadmap-baton` → require `roadmap_id`, `stub_id`, `wave`, `blocks`,
`blocked_by`. That is structural interpretation, so it fails SC-DR-014's criterion (1) as
written, but the entire oracle is the payload — no live state. Empirical support at
ratification: 64 roadmap-baton records across the engine and doctrine planes, zero missing any
of the five; no two-phase authoring flow to break (every writer scaffolds complete in one shot
or amends an already-complete record); blast radius two test assertions, both encoding the
advisory contract being changed. Ships deny with `COORDINATOR_OVERRIDE_ROADMAP_GRAPH_FIELDS` as
its hatch.

**Non-qualifying counter-example.** A guard that compares the staged tree against `HEAD`, or
that resolves whether a sibling record already exists on disk, reads live state — its verdict
depends on facts that can change between two runs over the identical write. Soak gate applies,
under SC-DR-003.

**What this does not do.** It does not amend SC-DR-003 for live-state oracles, which remain
soak-gated. It does not touch SC-DR-015 or the scoped-commit form. And it does not license a
guard to *interpret* content freely: criteria (2) and (3) still bind, so a self-contained oracle
that varies its verdict by session, or that would deny a documented legitimate use with no
override path, is still soak-gated.

---

## Exec-Bit Mechanics — Windows `core.fileMode=false` and Pathspec Commit Hazards

### `git commit -- <pathspec>` overrides the staged index mode with the worktree mode

**Rule.** `git update-index --chmod=+x <file>` sets the index entry to mode `100755`, but `git commit -m "..." -- <file>` re-reads the **worktree** mode for the named paths and applies it to the committed tree object — the staged index mode is ignored. On Windows with `core.fileMode=false`, the worktree mode is always `100644` regardless of the actual filesystem bit, so the staged `100755` is silently reverted. The commit appears to succeed (`git ls-files -s` shows `100755` in the index), but `git ls-tree HEAD <file>` shows `100644` — the mode change was dropped.

*Empirical basis (bin-cli-sh-shebang-polyglot C6):* Staged an exec-bit fix via `git update-index --chmod=+x <f>`, then ran `git commit -- <f>`. Reported "nothing to commit"; HEAD kept mode `100644`. The index showed `100755` so the repo-wide pre-commit exec-bit check passed green, masking the miss.

**Correct mechanics for exec-bit commits:**

Option A — also `chmod +x` the worktree file so worktree == index:
```bash
chmod +x <file>
git update-index --chmod=+x <file>
git commit -m "<subject>" -- <file>
```

Option B — commit the staged mode via a private index, never the shared one:

A bare pathspec-less `git commit` reads the **shared** index — exactly the form § SC-DR-015 above
retracts as unsafe on a shared branch (a peer can stage between your check and your commit). That
retraction stands; Option B does not reopen it. What Option B actually needs — landing the staged
`100755` without the trailing pathspec re-reading the worktree's `100644` — is the same private-index
mechanism SC-DR-015's diverge-case already uses, for a different reason: SC-DR-015 isolates from the
shared index to avoid absorbing a peer's staged *content*; here it's to avoid a trailing pathspec
re-reading the worktree's *mode*. Same tool, different hazard. Use `ceremony.scoped_git_commit`
(the coordinator engine's op) — its private-index path builds the tree from the index (preserving the staged
`100755`) and never touches the worktree mode. Where the op isn't reachable, the hand-rolled private-index
recipe in SC-DR-015 above is the fallback: run `git update-index --chmod=+x <file>` first so the private
index inherits the `100755` entry, then follow that recipe verbatim (`GIT_INDEX_FILE`-scoped `add`,
`write-tree`, `commit-tree -p <old>`, 4-argument compare-and-swap `update-ref`) — never a pathspec-less
commit against the shared index.

**Verify the landed mode with `git ls-tree HEAD <file>`**, not `git ls-files -s` — `ls-files -s` reads the index (which shows `100755` correctly), not the committed tree object.

### Pre-commit exec-bit hook fires on modifications, not on new-file additions

**Rule.** The `coordinator-precommit-exec-bit-check` hook only fires on modified `.sh` files, not on first-time additions. A freshly committed `.sh` file slips through as `100644` even when all sibling bin/ files are uniformly `100755`.

*Empirical basis (workstream-complete-self-clean):* Two new `.sh` files (`check-workstream-complete-deletion-blocks.py`, `run-smoke.sh`) committed via `git commit -- <pathspec>` landed as `100644`. The hook did not fire on new-file additions; it caught only a subsequent mode-change commit.

**Mitigation.** When adding a new `.sh` file to a bin/ directory, always explicitly stage the exec bit before committing — do not rely on the pre-commit hook to catch the omission at new-file time. Use the Option A or Option B mechanics above.

---

## Rename Mechanics — `git mv` and Explicit-Path Commit Shape

### `git commit -- <new-path>` after `git mv` ships only the add half, leaving the delete staged

**Rule.** After `git mv src dst`, running `git commit -m "..." -- dst` (naming only the new path) commits the addition of `dst` but leaves `D src` still staged in the index. The rename appears as a new file rather than a rename, and `git status` on the next invocation shows the stale deletion of `src` as pending — requiring a follow-up commit to retire the old path.

*Empirical basis (setup-command-triple-collision-cleanup):* Ran `git mv plugins/.../setup.md install.md` then `git commit -m "..." -- <new-path> <other-edits>`. The deleted source was not in the working tree, so passing it errors; omitting it staged only the add half. Encountered twice in one session across sibling repos.

**Correct recipe — enumerate both sides of the rename:**
```bash
git mv src dst
# ... any edits to dst ...
git add -- dst
git commit -m "<subject>" -- dst src   # both sides; git resolves the deletion from the index
```

Alternatively, drop the trailing `-- <paths>` restriction entirely and rely on the staged index (ensure staging hygiene is clean before committing). Distinct from § `Rename pathspec must include both sides` above, which covers the same principle for index-staged renames; this entry specifically surfaces the `git mv` + pathspec shape and the "add half only" failure mode.

---

## Atomic `git add` — a Stale Pathspec Fatals and Stages NOTHING

`git add -- <paths>` is **atomic on pathspec error**: if any one pathspec no longer matches a working-tree file, the whole `add` fatals (`did not match any files`) and stages *nothing* — not "everything except the bad path". Two common triggers produce this, and both are dangerous because a commit that follows in the same `&&`-chain either short-circuits (dropping your work) or, if pathspec-less, absorbs whatever a peer pre-staged.

### Re-adding a `git mv`'d source path fatals the whole add

After `git mv a b`, the source `a` is no longer a working-tree file. Running `git add -- a b c` fatals on pathspec `a` and stages **nothing** (atomic). A following pathspec-less `git commit` then commits from whatever is already in the index — on a shared branch, that absorbs peer-staged entries under your subject. **Rule.** Never re-add a `git mv`'d source path. `git mv` already staged both halves of the rename; add only genuinely-dirty *destination* / new paths, always commit with explicit `-- <paths>`, and verify `git diff --cached --name-only` before committing. (Source: DoE, concurrent-EM `work/*`.)

### `git add` of an already-`git rm`'d path fatals and silently skips an `&&`-chained commit

Listing a path you already `git rm`'d in a later `git add -- <paths>` makes git fatal (`did not match any files`) for the same reason — the path is gone from the working tree. If the commit is `&&`-chained after the add (`git add -- <paths> && git commit ...`), the short-circuit **skips the commit entirely**, and only files staged by a *prior* call land. **Rule.** In scoped-commit ceremonies, stage deletions separately (or let the earlier `git rm` stand) and do NOT re-list removed paths in a subsequent `git add`. (Source: DoE.)

Both cases share one discipline: a pathspec list handed to `git add` must contain only paths that still exist in the working tree. Deletions and renames are already staged by `git rm` / `git mv` — re-naming them is not a no-op, it is a fatal that stages nothing.

---

## Concurrency Hazards — Shared-Branch Staging Race After Pre-Commit Hook Failure

### Blanket-commit absorption in the window between pre-commit hook failure and retry

**Rule.** When a `git add -- <paths>` + `git commit` sequence hits a pre-commit hook failure, the window between the failure and the retry commit is a concurrency race: a sibling session running `git add -A` or `coordinator-safe-commit --blanket` can sweep all your staged files into their commit under their subject. When you retry, `git status` shows "nothing to commit" — your code is correct on HEAD but misattributed to the sibling's commit message.

*Empirical basis (DoE follow-up 2):* Had 4 files Edit/Write-staged (snippet, executor.md, tripwires, fan-out-dispatch.py), ran scoped `git add -- <paths>`, hit a pre-commit exec-bit failure on a 5th file. While fixing the exec-bit, a sibling session swept all 5 files under their commit (`chunk-2(executor-no-self-commit-em-only-gate): regression-net test — 12 assertions green`). On retry: "nothing to commit." Confirmed via `git log --all -- <path>` on each file.

**Discipline on pre-commit failure in a shared branch:**
1. Immediately re-run `git status` before any retry — the staged snapshot from the failed commit is not durable.
2. Run `git log --oneline -- <path>` on each of your expected files to confirm they haven't been absorbed.
3. Treat the gap between `git add` and `git commit` as a race window that resets at every pre-commit failure; re-stage explicitly from `git status` before retrying.

This is the consuming-side failure mode of the blanket-add hazard catalogued in § `git commit` without trailing `-- <pathspec>` — your files can be absorbed even when YOUR commit discipline is correct, if a sibling violates it.

---

## Smoke-Testing the Commit Helper — Always Use `--dry-run`

### Running the commit helper without `--dry-run` IS a commit — smoke tests that don't use dry-run ship real commits

**Rule.** `coordinator-safe-commit` commits on the happy path. Invoking it without `--dry-run` to verify it works — or to confirm gate behavior — will land a real commit, including committing any staged content under whatever subject string you passed.

*Empirical basis (DoE follow-up 8):* Shipped `coordinator-safe-commit --expected-owner em-only` to prevent executor self-commits, then immediately invoked it as a smoke test with `coordinator-safe-commit --expected-owner em-only "test"` (env unset). The gate passed (correct — EM context), and the script ran through to commit, landing Chunk 1's content under subject literally `"test"` . The EM committed exactly the eager-helpful pattern the gate was designed to prevent on the executor side.

**Use `--dry-run` whenever the helper is the unit under test:**
```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-safe-commit" --dry-run "subject"   # shows scope without committing
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-safe-commit" --dry-run --expected-branch <name> "subject"  # gate test
```

The EM is subject to the same eager-helpful failure mode the doctrine attributes to executors. The gate is opt-in by caller; a test invocation IS the happy path and the happy path commits.

---

## Branch-Scoped Diff Ranges — Session-Scope vs Branch-Scope on Shared Branches

### Branch-scoped diff ranges become noise on shared-branch concurrent-EM work shapes

**Rule.** Diff ranges anchored to `origin/main..HEAD` (or equivalent branch-scope forms) span all commits from every session that has committed to the shared branch. Under concurrent EM work patterns, a branch-scoped range includes sibling sessions' commits, making workstream-attribution ambiguous and per-session scope analysis unreliable.

**Default any gate or review that uses a diff range to session-scope (session-start SHA to HEAD)**, not branch-scope, when the shared-branch concurrent-EM model is active. Session-scope isolates one EM's commits; branch-scope intermingles all EMs on the branch.

*Empirical basis (a real incident spanning two repos):* Branch-scoped diff range during a workstream-complete review surfaced commits from a sibling session, producing noise in the gate output and forcing manual filtering to recover the workstream's actual diff.

The session-start SHA is available at `.git/coordinator-sessions/<id>/head_at_start`; use `git diff <head_at_start>..HEAD` for session-scoped ranges.

---

## Commit Message Mechanics — Shell-Special Characters in `-m`

### Backticks in `git commit -m "..."` trigger shell command substitution

**Rule.** A commit message passed via `-m "..."` is a **double-quoted shell string** — backtick-quoted words in it (e.g. describing a `` `home` `` param) are run as commands (`home: command not found`) via command substitution, which can corrupt the message or abort the commit. Any message containing backticks, `$(...)`, or other shell-special characters must NOT go through `-m "..."`. Use a single-quoted heredoc piped to `git commit -F -`:

```bash
git commit -F - <<'MSG'
fix(x): correct the `home` param default

Detail lines with `backticks` and $(literals) survive verbatim.
MSG
```

The single-quoted heredoc delimiter (`'MSG'`) suppresses all expansion, so the body is committed literally. (Source: DoE.)

## SC-DR-018 — A Whole-Tree `git stash` Is a Destructive Op Against Every Live Peer

**Renumbered 2026-08-03 from SC-DR-016, which two distinct records carried.** The identifier now
belongs solely to § SC-DR-016 (the self-contained-oracle ruling, :976) — that one keeps the number
because it is cited across the engine-plane boundary (the engine's `schema_validate.py` backlink
comment and its guard-override-keys reference table) and in
`docs/wiki/coordinator-tripwires.md`. This record was cited by number nowhere, so it is the cheap
side to move. Nothing about either ruling changes. A pre-2026-08-03 citation of "SC-DR-016"
resolves to the self-contained-oracle record; if it reads on stashing, it means this one.

**Rule: on a shared working tree, stash your own paths and nothing else —
`git stash push -u -- <your paths>`. The pathspec is not optional.**

`git stash` reads as a safe, reversible, private operation. On a solo tree it is. On the shared
workstream bus — which coordinator doctrine states is the *normal* case, not an edge case — a
pathspec-less stash reaches into every concurrently-running session's uncommitted work and takes
it. `-u` widens the blast radius to their untracked files too.

**It is worse than a blanket `git add`, for one reason: it is silent.** A blanket add at least
leaves a commit in `git log` that a victim session can find and attribute. A stash leaves
nothing on the branch at all. The victim sees work that its own executors reported writing,
absent from disk, with no error — and the cheapest wrong conclusion available is "the executor
hallucinated the write," which leads to re-dispatching agents over work that already exists.

### The tell

**Tracked-file modifications reverted, untracked files survived.** That combination is close to
diagnostic. A peer commit would show in `git log`; a `git checkout -- .` or `git restore .`
reverts tracked files but a plain stash does too — the discriminator is that `git stash list` has
a new entry whose parent is a commit you recognise. Check `git stash list` *before* concluding
anything was never written.

### Recovery — extract, never `pop`

A stash entry is a commit, so nothing is lost; the danger is in how you get it back.

1. **Snapshot first:** `git stash show -p 'stash@{0}' > recovery.patch`.
2. **Enumerate:** `git stash show --name-only 'stash@{0}'`. Note the entry has multiple parents —
   `^1` is the base commit, `^2` the index state, and **`^3` the untracked-files commit when `-u`
   was used**. Untracked deliverables (new scripts, new tests, new decision records) are in `^3`
   and are invisible to `git stash show`, which reports only tracked modifications. Enumerate it
   separately with `git ls-tree -r --name-only 'stash@{0}^3'`.
3. **Classify every file as yours or a peer's** before extracting anything. Use diff *shape*, not
   memory: a mechanical backfill hunk that adds only one known field is yours; a multi-line
   semantic edit to a baton another session holds is not. Per-file diffs come from
   `git diff 'stash@{0}^1' 'stash@{0}' -- <file>` — note that `git stash show -p <stash> -- <file>`
   does **not** accept a pathspec that way and silently returns an empty diff, which reads as
   "no changes to this file" and will mislead you.
4. **Extract only your paths** into a patch and `git apply --3way` it. Pull untracked files out of
   `^3` individually with `git show 'stash@{0}^3:<path>' > <path>`, guarding each with an
   existence check so you never clobber a file a peer recreated in the interim.
5. **Commit your recovered work immediately.** The tree that ate it once will eat it again.

**Never `git stash pop`** on a shared stash: it restores the peers' files into *your* tree, where
they will be swept into your next commit, and it consumes the entry. **Never `git stash drop`** —
the peers' work is still in there and that entry is their only recovery path. Leave the stash in
place and say so, so the affected sessions can extract their own halves the same way.

### Why the rule reads as a recommendation elsewhere

The `## Concurrent-EM Git Operations` bullet in `CLAUDE.md` framed stash as the probe-isolation
idiom without a pathspec, because probe isolation is a real and good use of it. The correction is
narrow: keep the idiom, make the pathspec mandatory. A probe only ever needs its own files.

*Provenance: a real incident during a large execution wave.
A peer stashed the whole tree mid-wave and swept six executors' output; two chunks (a schema
field-set and a 32-file frontmatter backfill plus its script, test, and decision record) were
recovered by the procedure above. Third work-destruction event on that branch that day — the
predecessor handoff records two blanket-commit incidents earlier the same day.*

## SC-DR-017 — Check 7's "no signal" premise is retired; the solo bare-commit exemption must consult Check 6's touch-list comparison

**Ruling (doctrine, DoE): the guard asymmetry reported against the coordinator engine's bash-guard
dispatch checks is real, and the fix is to make the solo-bare-commit escalation (Check 7) consult
the same touch-list signal Check 6 already computes, rather than leave that shape permanently
advisory-only.**

**The premise.** Check 7's own docstring declines to escalate a solo bare `git commit` to a deny
because "no command-level signal at all" distinguishes session-own staging from a peer's for that
shape. That premise is false as stated: Check 6, ~1,200 lines earlier in the same module, already
resolves exactly this — it compares each staged path against the session's `touched.txt`, resolves
the owning session id by scanning peer touch lists, and has a deny path gated behind
`COORDINATOR_SCOPE_STRICT`. The two checks disagree about whether the signal exists, in the same
module, because they were authored at different times against different assumptions — not because
the signal is genuinely absent for the bare-commit shape. (Reported with live evidence: a
`git mv`-shaped rename absorbed into three unrelated peer commits in ~20 minutes, one session, via
an inbound cross-repo report.)


**Why the exemption is backwards.** The scoped `git add -- <paths> && git commit -- <paths>`
compound shape — the one already escalated to deny — is the shape an author uses when they are
*already practicing* scoped-commit discipline. The solo bare `git commit` — advisory-only — is the
shape with zero staging discipline behind it, and it is the shape that actually produced the
provenance-corrupting sweep. Enforcement is currently strongest on the callers already complying
and weakest on the callers who are not; that inversion is the defect, independent of any residual
false-positive-rate question.

**Decision.** Check 7 gains the same touch-list comparison Check 6 already performs (same module,
same data — not a second implementation): resolve the session's own touched-paths set, diff it
against the currently-staged paths, and treat a non-empty "staged but not mine" residue the same
way Check 6 does — a scope-warnings log entry plus a `COORDINATOR_SCOPE_STRICT`-gated deny, not an
unconditional advisory. This does not flip strict mode on globally (§ SC-DR-003's warn-before-deny
soak gate still governs that separately); it removes the asymmetry between two checks in the same
module that read the identical hazard and reach different postures for no reason tied to signal
availability.

**What this ruling does NOT do.** It does not touch SC-DR-014's structural floor (`git add -A` /
`.` / `-u` stay hard-denied) and it does not change the scoped-commit default (SC-DR-008). It rules
narrowly on Check 7's own exemption rationale.

**Implementation is the coordinator engine's** (own `bash_guards` dispatch-checks module) — this
DoE record is the ruling the engine implementation should read, per SC-DR-014/SC-DR-008 both being
DoE decision records. Route the code change onward via cross-repo memo, pinned to the sender's
cited engine-tree SHA; this repo carries no copy of that module to edit.

**The second, smaller ask in the same memo — `git add -A -- <explicit paths>` being denied when
staging a rename/deletion whose source path is already off disk — needs no guard change.** The
scoped, already-documented recipe is `git mv src dst` (stages both halves of a rename atomically,
no `-A` involved — see § Rename Mechanics above) or, for a bare deletion of an already-vanished
tracked path, `git rm -- <path>` (see § Atomic `git add` — a Stale Pathspec Fatals and Stages
NOTHING above). Neither needs `-A`, so SC-DR-014's matcher does not need a carve-out for this case;
the gap was in this page's discoverability, not in the guard.

---

## SC-DR-019 — Exposure Under a Refusal Is Duration × Dirty-Set; Shrink the Set, and Make the Pathspec Prove Its Provenance

**Ruling (doctrine, DoE): a scoped-commit refusal is per-path, not per-commit. A session honoring
a refusal commits the uncontested remainder immediately and waits holding only the contested
path. Separately: a pathspec must be provenance-bearing, not merely well-formed — and an ordinary
commit that stages a live peer's claimed path emits a derived attribution trailer.**

Every other absorption entry on this page is keyed to a sweeping **mechanism** — `git add -A`,
`--blanket`, the pre-commit-failure retry window, a pathspec staging a whole contested file — and
every remedy is addressed to the sweeper. This record is the first entry keyed to a **duration**,
and the duration is prescribed by a guard doing its job.


### The reported shape

`ceremony.scoped_git_commit` correctly refused one file because a live peer held a claim on it.
Sibling doctrine's response to that refusal is to wait, and explicitly not to reach for an
override key. The session waited, correctly, with four finished chunks uncommitted. Two peer
sessions committed during the wait; the four chunks landed inside their commits. Neither
absorbing commit used a blanket form or hit a pre-commit-failure window — both carried
well-formed explicit pathspecs and read, from the outside, as ordinary tidy scoped commits.

The reported framing was that honoring the refusal is what created the window, and that an
override would have avoided the absorption — the wrong incentive to leave standing.

### Ruling 1 — the refusal is per-path; exposure is duration × dirty-set

That framing is one factor short. Absorption exposure under a refusal is **wait duration × size of
the dirty set left sitting**. A waiting session cannot shorten the duration — the guard owns that,
and correctly. It *can* shrink the set, and in the reported incident it was holding four chunks'
worth of uncontested paths hostage to one contested file.

> **Rule.** On a scoped-commit refusal, commit the uncontested remainder immediately, then wait
> holding only the contested path(s). Do not sit on a whole dirty tree because one path is
> refused. Reducing the exposed set is always available, never requires an override, and does not
> weaken the guard by a single path.

**Negative-spec.** This is not license to hand-split the contested file — SC-DR-010 stands, and
there is no correct way to split a contested file by hand. The split is *between* paths, never
within one.

**Corollary for the refusing surface (engine-plane).** This rule is mechanical only if the refusal
names the contested paths individually. A refusal that rejects the whole invocation without a
per-path breakdown forces the waiting session to re-derive the split by hand, which is the
friction that makes sitting-on-everything the path of least resistance. Per-path refusal reporting
is the engine's surface, not this one; routed onward by memo.

**Landed engine-side 2026-08-03** (`coordinator_core/ops/session/scope_report.py` ::
`assert_paths_in_session_scope`, engine plane). The refusal had been returning
on the *first* denied path; it now enumerates every denied path with its own classification, names
the uncontested remainder as a directly re-invocable pathspec, says so in words when that
remainder is empty, and caps both lists at 25 with an explicit `(+N more)`. The
`"path outside session %s scope: %r (%s)"` prefix is unchanged, so pinned matchers still fire.
Cite this corollary as satisfied, not as an open dependency — "commit the uncontested remainder,
then wait holding only the contested path" is mechanical now, with the remainder handed to the
waiter rather than reconstructed by hand.

### Ruling 2 — a pathspec must be provenance-bearing, not merely well-formed

The consult asked whether a scoped commit should have to prove its pathspec's *provenance* rather
than its *shape*, observing that this page's rules check form and nothing checks provenance.

**Half right, and the correction relocates the problem.** This page carried no normative
provenance rule — that gap is real and closes here. But the *mechanism* has existed since
Component 1: `.git/coordinator-sessions/<sid>/touched.txt` is precisely the executor-touched-set
oracle, and Check 5 (`check_validate_commit`) fires whenever `staged ⊄ MY_SCOPE`, naming the
foreign paths and the likely owning session.

Run the reported incident against it: the swept paths were claimed in the *waiting* session's
`touched.txt`, so they are excluded from the sweeper's mtime fallback (Component 2 includes a path
only where no other active session claims it) and absent from the sweeper's own touch list.
`staged ⊄ MY_SCOPE` fires on both absorbing commits, at commit time, before either landed.

> **It warned.** The default posture is warn-only, and the sibling plane has now ratified that it
> stays (ruled sibling-side 2026-08-03 — an outage teaches operators to reach for override keys,
> which costs more than the sweep it prevents).

So the precise statement is: **pathspec provenance is checked; under warn-only it is checked and
disregarded.** The window a compliant waiter is exposed in is not a missing check — it is the
check's advisory posture, which is a ratified choice on both planes. That reframes the incentive
question too: honoring the refusal created the window, but a warning that fired and was ignored is
what let something enter it. Different owners, different fixes.

The rule made textual, because a rule that exists only as a code path is one nobody can cite in
review:

> **Rule.** A pathspec must be **provenance-bearing** — carried from an executor's touched-files
> set or a plan chunk's `surface:` list — never assembled by surveying the dirty tree.
> Form-checking a pathspec (explicit, non-blanket, no `-A`) verifies shape only; a well-formed
> pathspec sourced from `git status` is the sweeping harm laundered into a compliant-looking
> commit.

This already binds fleet EMs via `snippets/em-operating-doctrine.md`; it belongs here so it is
greppable at the point of use. **SC-DR-017 is its nearest neighbour** and reached the same
conclusion from the other end — Check 7's exemption exists precisely because it assumed the
provenance signal was absent while Check 6 was already computing it.

### Ruling 3 — the attribution trailer belongs on ordinary commits, and must be derived

§ Pause-snapshot attribution trailer has the right shape and the wrong trigger:
`Substrate-changes-attribution:` is **author-supplied**, fires only on PM-directed pause-snapshots,
and asks the author to reconstruct attribution — which is exactly what failed in the incident that
produced it, where three EMs each surveyed and disclaimed authorship of the same ~940L.

The cheap complement needs no author cooperation and no new data, because Check 5 already computes
it. At commit time, for each staged path claimed by a **live peer's** `touched.txt`, emit:

```
Absorbed-peer-claims:
  <contested/path.py>: session <peer-session-id> (claimed, live)
```

Properties that make it the right trade: **derived, not authored** — no reconstruction, so it
cannot be laundered by narrative prose; it fires on **ordinary** commits, which is where the
reported absorption happened, not only on pause-snapshots; it turns "read commits one at a time,
after the fact" into `git log --grep='Absorbed-peer-claims'`, runnable by the absorbed session on
wake; and it is **compatible with warn-only by construction**, recording rather than blocking, so
it costs the ratified posture nothing.

**Implementation is the engine's** (`coordinator_core`, alongside Check 5's existing owner
resolution) — this DoE record is the ruling that implementation should read, in the SC-DR-017
pattern. This repo carries no copy of that module to edit.

### What this ruling does NOT do

It does not weaken any guard, does not mint an override path, and does not reopen the strict-mode
posture — an override that *rewards* the sweeping behaviour is worse than the absorption, and
accepting that reasoning for the sibling-side warn-only ruling while refusing it here would be
incoherent. SC-DR-014's
structural floor and SC-DR-008's scoped-commit default are untouched.

Greppable token: `REFUSAL-EXPOSURE-IS-DURATION-TIMES-SET`. Registered in
`docs/wiki/coordinator-tripwires.md`.

---

## SC-DR-020 — A positional pathspec on `git commit` is explicit scope; the `--` separator is disambiguation, not the guarantee

**Status:** ratified 2026-08-04 (EM engineering remit — a guard-consistency correctness ruling, not
a change to the scoped-commit default). Raised by a sibling-repo EM alongside the C7 deny-inversion
fix; the two are the same defect at opposite polarity.

**The question asked.** `_bt_commit_has_explicit_pathspec` counts `-- <paths>`, `--only`/`-o`, and
`--pathspec-from-file` as scope, but **not** a bare positional pathspec — so `git commit a.py -m x`
draws an advisory. Verified live on git 2.54.0: with `a.py` and a peer's `b.txt` both staged,
`git commit a.py -m x` lands `a.py` alone and leaves `b.txt` staged, identically to `--only`. Was
the advisory-on-anything-but-`--` behaviour deliberate pedagogy to keep one spelling canonical?

**Ruling: no — count it. Positional pathspec is explicit scope.** `git commit a.py -m x` and
`git commit -m x -- a.py` are not two forms with different safety properties; they are the *same
operation*. `--` is git's revision/path disambiguation token. It disambiguates; it does not scope.
Treating its presence as the load-bearing signal is the identical mistake the sibling engine just
fixed in the `git add` half of the compound-shape deny, where the escalation fired **only** on
`git add -- a.py` and fell through to advisory on `git add a.py` — the common spelling, and the one
that actually swept. Same token, same false weight, opposite polarity: there it gated a deny, here
it gates a suppression. A guard whose verdict turns on a disambiguation token is reading syntax
where it means to read semantics.

**Pedagogy is not the guard's job here, and this shape does it harm.** SC-DR-008 ratifies
`git add -- <paths> && git commit -m "<subject>" -- <paths>` as the canonical spelling and that
stands unchanged — it is enforced by prose, by what skill bodies and dispatch prompts emit, and by
`ceremony.scoped_git_commit` being the preferred path. An advisory that fires on a form already
proven safe is not teaching the canonical spelling; it is spending the operator's attention on a
non-hazard. Warning-blindness is not a hypothetical cost on this surface — the fleet-wide
measurement above records 6197 warn lines, 98.1% of them correct-but-unactionable, and a sweep got
through anyway. Do not add a 6198th on a commit that was already scoped.

**Bounds — what must keep firing.**

- **`--include` / `-i` keeps firing, unconditionally.** It is the near-neighbour and it is genuinely
  *not* self-scoped: it merges the named paths into the existing staged content and commits both.
  This ruling must not be read as widening to it.
- **A bare `git commit` with no path operands keeps firing** (SC-DR-017). Absence of operands is
  the unscoped signal; that is unchanged.
- **`--pathspec-from-file` keeps failing open** — the predicate cannot read the pathspec, so it
  neither denies nor suppresses on it.
- **Parse conservatively; ambiguity fails open to advisory, never to suppression.** Count an
  operand as a pathspec only after option-argument consumption resolves cleanly. An operand that
  could be a revision, or one trailing an option the parser does not recognize (and therefore
  cannot know consumes a value), yields *no* suppression. The asymmetry is deliberate: a spurious
  advisory costs attention, a spurious suppression costs a peer's work.

**This does not widen the SC-DR-015 hazard.** A positional pathspec reads the **worktree**, exactly
as `-- <paths>` does — so under index/worktree divergence for the named paths it destroys deliberate
staging in precisely the same way, and the private-index form (`ceremony.scoped_git_commit`) remains
the answer for that case. Counting it as scope inherits that hazard unchanged rather than enlarging
it, which is the correct outcome: same operation, same treatment, one rule instead of two.

**Implementation is the engine's** (`coordinator_core/bash_guards`, `_bt_commit_has_explicit_pathspec`)
— this DoE record is the ruling that implementation should read, in the SC-DR-017 pattern. This repo
carries no copy of that module to edit. The escalation oracle needs rows in the *unseparated*
spelling for both halves of the compound shape; every existing row using the separator form is why
the `git add` gap went uncovered, and the same blind spot exists here until positional-form rows
are added.

### What this ruling does NOT do

It does not change the scoped-commit default (SC-DR-008), does not touch SC-DR-014's structural
floor (`git add -A` / `.` / `-u` stay hard-denied — absence of path operands still means unscoped),
does not reopen the strict-mode posture, and does not mint an override path. It narrows exactly one
thing: which spellings of a genuinely self-scoped commit the advisory should stop warning about.

Greppable token: `SEPARATOR-IS-DISAMBIGUATION-NOT-SCOPE`. Registered in
`docs/wiki/coordinator-tripwires.md`.

---

## SC-DR-021 — A claim may be self-reported, but only of writes that ACTUALLY happened; an intended `surface:` is not a claim

**Ruling (doctrine, DoE): `T` denotes a claim, not a detection — the touch hook is one producer of
claim events, never the definition of one. A second producer is therefore legitimate, and one has
landed. But the line that matters is drawn *inside* claim-space, not at its edge: a producer may
report paths it actually wrote, and may never report paths it intends to write. A dispatch-time
declaration sourced from a plan chunk's `surface:` list is NOT a real `T`, and the self-facing rule
at § Component 1 correctly refuses it.**


### The question as asked, and why it was the wrong cut

A sibling plane asked whether a set of paths, declared by a dispatching session *before* the work
is committed and sourced from provenance that session already holds, constitutes a "real `T`" for
the self-facing rule — or whether that invariant admits nothing that did not arrive through the
touch hook. The motivating defect: the fleet's only dispatchable committer denied on its
characteristic workload, four independent reports.

Framed that way the question has no good answer, because it bundles three different populations
under one verdict. Split them and each resolves cleanly:

| Population | Reaches a claim? | Verdict |
|---|---|---|
| **(a)** Engine-op writes routed through the dispatch chokepoint | Yes — self-reported | Already legitimate; seam landed |
| **(b)** A pre-declared, `surface:`-shaped intended set | No | **Refused** — see below |
| **(c)** Raw Bash/heredoc writes in an agent's own session | No | **Refused** — the ratified permanent limit, unchanged |

**The reported reproduction is (c). The proposed fix is shaped for (b). What had already landed
covers (a).** Nothing in the request addressed the population its own controlled experiment
demonstrated. Naming that mismatch is most of the value of this record.

### Why (a) is legitimate — `T` is a claim, not a detection

The touch hook produces claim events; it does not define them. `T <path>` asserts "this session
claims this path," and nothing in the event-log format ties that assertion to a tool-call
observation. Verified against the engine as written, not as wished: a self-report contract is live
at the process-level dispatch chokepoint, reuses the existing `touch()` primitive verbatim rather
than inlining a second dialect, writes only into the caller's own log, is repo-contained to the
caller's own worktree, files-only, and fail-open. **This is a clarification of existing semantics,
not a semantic change needing migration.**

This does not reopen the Bash-write limit. § Component 1's negative-spec forbids two specific
things — widening the hook matcher, and closing the gap by *write-time attribution*. A chokepoint
self-report is neither. The distinction that makes it sound: attribution *infers authorship of an
observed effect* and can therefore be raced (a post-hoc mtime or `git status` delta cannot tell "my
Bash wrote this" from "a peer wrote it during my Bash call"). A handler reporting what it wrote
infers nothing and samples no disk state — it knows, because it did it.

### Why (b) is refused — and the reason is not the invariant

The tempting refusal is "the self-facing rule holds absolutely." That is not the reason, and
resting on it would be wrong: (a) already crosses that line legitimately.

The real reason is that **a declaration and the real write set legitimately diverge** — a handler
that intended N paths writes M of them, or writes a different path on a fallback branch. Three
independent arguments converge:

1. **It breaks the safety argument the landed contract rests on.** That contract is justified on
   the ground that a wrong declaration can only *withhold* a path from other live sessions, never
   falsely *grant* one. That holds only because declarations are of actual writes. Under (b), a
   declared path a peer actually wrote **is** a false grant — the one outcome the safety argument
   asserts is impossible.
2. **Nothing catches it.** The actually-wrote rule is unenforceable at the recording site by
   construction — the validator cannot know what a handler really wrote, only what it claims, and
   an existence check passes for any pre-existing file. Handler discipline is the only thing
   holding the line, and (b) removes it.
3. **A live reader breaks.** At least one hook reads the log as plain membership ("did this session
   touch X"), filtered to plan and sizing paths — exactly the paths a chunk's `surface:` list
   names. Under (a) that reader's exposure is unchanged; under (b) it reads intent as action.

> **Rule.** A self-reported claim must name paths **actually written by the reporting call**.
> An intended surface, a plan chunk's `surface:` list, or any pre-declaration of work not yet done
> is not a claim and must never be recorded as one. This is the same discipline SC-DR-019 Ruling 2
> applies to pathspecs, one layer down: provenance means *what happened*, never *what was planned*.

**Negative-spec.** SC-DR-019 Ruling 2 permits a *pathspec* to be carried from a plan chunk's
`surface:` list. That is not license to record the same list as a claim. A pathspec is checked
against a scope computed from claims; sourcing both sides from one declaration makes the check
compare a statement to itself.

### Residual populations, named rather than resolved

Two are outside both the hook matcher and the landed self-report contract, and neither is the
ratified Bash-write limit — they are artifacts of the contract's own shape, and are not resolved
here:

- **(d1) Deletions and renames.** The recording path requires an existing regular file, so a
  deleted path can never be self-reported. This repo's queue-closure convention is `git mv` to
  `archive/<queue>/<YYYY-MM>/` — every closure leaves an unclaimed dirty deletion at the sink,
  permanently and by construction. Sister to § Rename pathspec must include both sides.
- **(d2) Cross-repo engine writes.** An engine op writing into this repo's central root is
  deliberately skipped by the sibling's containment fix — correctly, since a session id is a
  repo-local namespace key and a cross-repo claim can steal a live native session's file. The
  sibling names orphan adoption as this side's remedy for that residual; the same week, the
  request above proposed forbidding it. **That contradiction is real, is this plane's to settle,
  and was not the question asked.** Routed onward by memo rather than decided in passing.

Also unresolved and worth stating plainly: a dispatched executor's own Bash writes reach neither
the session log nor the agent-keyed log. That is the population the dispatchable committer most
often faces, and it is (c) — ratified, permanent, not pending.

### What this ruling does NOT do

It does not widen the hook matcher, does not reopen the sibling's ratification of the Bash-write
gap, does not mint an override path, and does not touch SC-DR-014's structural floor or
SC-DR-008's scoped-commit default. It does not relax the live-peer case: a path claimed by a live
peer denies, declared or not. And it does not license orphan adoption as a default — that path is
shipped and gated, and its gate emptying the orphan set under an agent-race overlap is the gate
failing *closed*, which is an argument for it rather than against.

Greppable token: `A-CLAIM-IS-WHAT-YOU-WROTE-NOT-WHAT-YOU-PLANNED`. Registered in
`docs/wiki/coordinator-tripwires.md`.

---

## SC-DR-022 — Orphan adoption is an operator's answer to a refusal, never an agent's default; the (d2) residual resolves in the adoption direction

**Ruling (doctrine, DoE), the two halves separately:**

1. **Yes** — a cross-repo engine write left unclaimed at a sink the engine deliberately refuses to
   claim into is **legitimately adopted with `--include-orphans`**, by an operator, on the *named
   paths the refusal itself enumerated*, after the refusal has happened. SC-DR-021's residual (d2)
   therefore resolves in `ipc.py`'s direction: that comment names the correct remedy.
2. **No** — a **dispatchable commit agent may never pass `--include-orphans` itself**, in any
   invocation. Not as a default, and not as its own response to a refusal it received. An agent
   that meets an orphan denial **stops and reports it**; the EM disposes it.


### What actually bounds the adoption — the operator, not the flag

The sibling's framing was *default posture vs. deliberate response to a specific refusal*, and that
distinction is right but under-specified: it locates the bound in **when** the flag is passed. The
bound is not temporal. It is **who knows the paths are theirs.**

`--include-orphans` adopts paths the scope computation could not attribute. Nothing in the
mechanism can verify the adopter authored them — that is precisely why they are orphans. What makes
a bounded adoption safe is a fact living outside the mechanism entirely: *the operator was there,
and knows what it just wrote.* An enumerated deny message supplies the **candidate list**; it never
supplies that knowledge. So the flag is safe exactly when the party passing it holds independent
provenance for every named path, and unsafe otherwise — regardless of whether a refusal preceded it.

That is why half 2 is a flat prohibition rather than "the agent may adopt after a refusal too." A
dispatched committer holds no such provenance by construction: it receives a pathspec, it did not
author the files, and its entire design (§ Pathspec provenance, SC-DR-019 Ruling 2) rests on
provenance arriving *with the brief* rather than being derived on the spot. An agent adopting an
orphan is deriving scope from a denial — the sweeping defect one level removed, laundered through a
compliant committer. The refusal is the whole signal it was dispatched to surface.

**Corollary, and it is the operative one:** a deny message that advertises re-invocation with
`include_orphans: true` is an offer addressed to an **operator**. An agent reading that sentence
must treat it as information to relay, not an instruction it is entitled to follow. The advertising
text is not authorization.

### Verified properties this ruling rests on

Read from the engine as written, not as assumed (`coordinator_core/ops/ceremony/scoped_git_commit.py`,
`ops/session/safe_commit_offer.py`, 2026-08-04):

- **Adoption never relaxes the live-peer case.** `include_orphans` threads to
  `assert_paths_in_session_scope(allow_orphans=…)`, which denies a live-peer-claimed path
  regardless. A mixed pathspec with even one peer-claimed path denies whole, and makes no offer.
  Half 1 therefore cannot become a route to committing a peer's work.
- **The offer is orphan-only and enumerated.** The re-invocation suffix appears only when *every*
  denied path is an unclaimed orphan — so the "named paths" half 1 permits are named by the engine,
  not assembled by the adopter.
- **The gate fails closed under ambiguity.** An agent-race overlap empties `orphans` outright, and
  a session failing the positive-evidence check gets `include_orphans ignored`. Both deny. As
  SC-DR-021 already recorded: that is an argument *for* the mechanism, not against it — a mechanism
  that refuses when the tree is ambiguous is the design, and rejecting it on those grounds while
  proposing a channel that *grants* under the same ambiguity is the incentive inversion SC-DR-019
  warns about.

### Half 2's enforcement — named as a gap, closed the same day

**As first recorded, half 2 had no structural clamp**: the subagent-commit guard *mirrored* the
invocation's own `--include-orphans` opt-in rather than forcing it false (a prior hard-coded `True`
had permitted what the sink refused, and mirroring was the fix for that). So the prohibition rested
on `coordinator/agents/git-commit-agent.md` and this record, and nothing else. That gap was named
here rather than assumed away, and surfaced to the sibling plane as an open question.

**It is now closed structurally** (landed on the engine plane): the agent leg passes
`allow_orphans=False` unconditionally, and `include_orphans` refuses at its own leg with prose
telling the agent to relay rather than re-invoke. The discriminator was already in hand — that leg
only ever runs for a dispatched subagent, gating on the harness-supplied, non-cooperative
`agent_id`.

**Why the provenance framing is what made it enforceable, and this is the transferable part:**
*"did the caller author these bytes"* has a structural answer at that seam. *"is this a considered
response rather than a default posture"* does not — it is a fact about intent, unavailable to any
guard. A rule stated in terms a mechanism cannot evaluate stays prose forever. Locating the bound
in provenance is what turned this one into a two-line clamp.

The agent-side prohibition stays regardless: defence in depth, and the prompt is what makes the
refusal legible to the agent rather than arriving as an unexplained denial.

### What this ruling does NOT do

It does not reopen the retirement of always-on adoption of unclaimed dirt — that stays retired, and
half 2 is the sharper edge of that same retirement rather than an exception to it. It does not
reopen the ratified Bash-write limit. It does not widen the hook matcher, mint an operator override, or touch
SC-DR-014's structural floor. It does not make adoption a *routine* step: an operator meeting an
orphan denial should first ask why the path carries no claim — SC-DR-021's (d1)/(d2) name two
structural producers, and a denial outside those is a signal worth reading before it is adopted.

Greppable token: `ADOPTION-IS-AN-OPERATORS-ANSWER-NOT-AN-AGENTS-DEFAULT`. Registered in
`docs/wiki/coordinator-tripwires.md`.
