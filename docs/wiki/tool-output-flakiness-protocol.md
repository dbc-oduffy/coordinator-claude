# Tool-Output Flakiness — Failure Shapes and Verification Protocol

When a tool call returns empty, garbled, or contradictory output, this is the
protocol. It exists because the failure is real, environmental, and dangerous —
not a reason to "be more careful" in the abstract.

Full mechanism: `docs/architecture/audit-records/2026-05-29-tool-output-flakiness-diagnosis.md`.

## The three shapes

1. **Empty return** — the call ran (side effects landed on disk) but stdout came
   back blank. Harness-side delivery drop. Most common under parallel bursts / high
   stdout volume on Windows Git-Bash.
2. **Scrambled / late association** — a burst of parallel calls returns results
   keyed to the wrong call, sometimes arriving a turn late. Harness-side routing.
3. **Fabricated-but-plausible content** — invented git SHAs, phantom merge states,
   contradictory reads of one state, **and hallucinated *file content*** (a `Read`
   returning fabricated source code / docstrings that contradict what is actually on
   disk). **Model-side confabulation** filling the hole that shape 1/2 created. This is
   the dangerous one: it looks real. See § A Flaky Read Can Hallucinate File Content for
   the file-content variant and the premise-outranks-one-flaky-read rule.

Shapes 1–2 are the trigger (harness, upstream — we cannot patch it from here).
Shape 3 is the amplifier (the model). The two compound into action on false state.

### Envelope-error variant — `[Tool result missing due to internal error]`

A close sibling to shape 1: instead of an empty stdout, the harness surfaces a literal `[Tool result missing due to internal error]` string in lieu of the tool result. The command **may have run, partially run, or never spawned** — the envelope error gives no signal between the three. Distinct from `Waiting…` (which never ran): this returned, but the return is an error string, not the tool's output.

**Discipline.** Treat as unknown state, same family as shape 1. For **state-mutating** calls (filesystem writes, git ops, cross-repo memo sends, anything with disk side-effects), **verify on-disk state before retrying** — the retry is only safe if the underlying op is idempotent OR you've confirmed the prior call left no partial effect. For read-only calls, re-run solo. *example-game-repo:* `cross-repo-memo send` returned this envelope error; on-disk check showed neither the receiver write nor the outbox-removal happened (state 3, never-ran); retry succeeded cleanly. The trap is reading "internal error" as either "hung — wait" or "failed — move on" without disk verification.

*Self-witnessed instance:* during a Part B closeout an agent narrated "the Write
succeeded" for a file that was in fact in a cancelled tool batch and never written (disk-verified
absent) — textbook shape 3, the model filling the hole a dropped/cancelled result left. The
reviewer reviewing that same plan independently hit the trigger and recovered via "re-run solo"
below. A real in-house instance, not a hypothetical.

## Not this protocol — blocked / no-return (`Waiting…`) is a different failure

The three shapes above are all *output that came back wrong* — the command **ran** (side
effects landed) and only the returned view was empty, scrambled, or confabulated. A call stuck
at `Waiting…` that never returns is the **opposite** failure: it **never ran**. Applying the
flakiness protocol to it is the trap — "re-run a different way" just starts *another* blocked
command, and the spray of `echo ALIVE` / `printf CHAN_OK` / variant `git log` probes that
follows is a self-inflicted loop, not a diagnosis.

**Discriminator.** Empty-return = call ran, side effects on disk, stdout blank → flakiness
protocol below (re-run solo). `Waiting…` / no-return = call is *blocked*, nothing landed →
command-**shape** problem, not flakiness. Different bucket, different fix.

**The two triggers — both model-side, both cheap to avoid (issuance discipline):**

1. **`cd`-prefixed / compound / line-continued Bash.** A `cd` inside a compound command
   triggers a permission prompt, which renders as `Waiting…` — the call is blocked on *human
   approval*, not a dead channel. Fix: never `cd`-prefix; use `git -C <path>` or the tool's own
   cwd, and keep each Bash call a single command.
2. **Batched redundant variant-probes.** Firing five shells in one message (Bash + PowerShell +
   plain `git` + `echo` + `printf`) to "test the channel": if the leader blocks, the rest show
   `Waiting…` queued behind it, so **one** block looks like five and the PM-interrupt clears them
   all at once. Fix: one solo command answers the question — if it returns, the channel is fine.

**Response when a call hangs:** wait it out, or diagnose the block (lock? permission prompt?) —
**never re-fire, never spray a probe to "test the channel."** A clean solo `git -C … log -1`
returns in <1s on a healthy channel; if *that* hangs you have real evidence of a platform-level
hang worth escalating upstream. **Two verification probes for the same fact is itself the stop
signal** — diagnose, don't probe a third time.

*Self-witnessed (Machine-a):* in a busy concurrent-EM repo, after each commit the EM
read `Waiting…` on `cd`-prefixed compound git commands as a flaky *channel* and sprayed
`echo ALIVE` / `printf CHAN_OK` / variant `git log` probes — five blocked calls per round, broken
only by PM interrupt, recurring all day. A single solo `git log -1 --oneline` then returned
instantly, proving the channel healthy and the trigger to be command-**shape** + batching, not a
harness bug. The earlier shapes teach "distrust the output"; this one teaches that distrust has a
*governor* (solo, once) and that a non-returning call is not an output-trust question at all.

**Enforcement (trigger 1 only).** The `cd <path> && git …` stall is caught at the tool boundary by
PreToolUse(Bash) hook `offer-git-c-over-cd.sh` (folded into claude-klabauter `coordinator_core.bash_guards`
via `preuse-bash-dispatch.py`; DoE `.sh` removed) (token `OFFER-GIT-C-OVER-CD`,
`coordinator/docs/wiki/coordinator-tripwires/`): it transparently auto-rewrites to the prompt-free `git -C <path> …`
form before the command issues (clean 2-segment case and redundant-cd case), or offers the rewrite
as a deny-with-suggestion when a non-redundant `cd` is followed by cwd-dependent commands. Either
way the stall never happens. It is *offer-shaped*, not a destructive guard. Trigger 2 (the probe-spray itself) is caught by PreToolUse(Bash) hook
`nudge-probe-spray.sh` (folded into claude-klabauter `coordinator_core.bash_guards` via
`preuse-bash-dispatch.py`; DoE `.sh` removed) (token `NUDGE-PROBE-SPRAY`): the "a per-call hook cannot see the batch"
objection is defeated by disk state — a session-keyed rolling window counts probe-shaped commands
(`echo`/`printf`/`sleep`/exact-repeat) and nudges (warn, never block) once ≥3 land within 90s, with
any real command resetting the streak. The doctrine it backs still holds and is the thing the nudge
points at: **one solo call, two probes for the same fact is the stop signal.**

## The protocol — when output looks empty, off, or contradictory

- **Before issuing a batch — keep parallel batches small and same-failure-domain.** When N tool
  calls go out in one parallel batch and **any single call errors, the harness cancels every other
  call in that batch** (observed 2026-05-29: one `exit 1` cancelled ~30 queued calls; oversized
  batches also hit `ENAMETOOLONG` on spawn). So: never co-batch *dependent* ops (e.g. Write-a-file
  + Edit-that-file — the Edit is cancelled when the Write's batchmate errors), never co-batch a
  flaky-prone call with calls whose results you need, and prefer several small batches over one
  large one. This is *issuance*-discipline (applied **before** the call); it is the trigger-side
  complement to "re-run solo" below, which is recovery-discipline.
- **Do NOT infer from absence.** An empty return is NOT evidence the thing is absent
  / clean / done. It is evidence the channel failed. Treat empty as *unknown*.
- **After a failed/empty return — re-run solo, do NOT loop.** Re-issue the single call by itself
  (not in a parallel batch). One clean re-read is the goal — blind retry-in-a-loop is part of
  the trap (it invites picking a winner between fabrications). If two reads of the
  same state disagree, **read the source a third way** (different tool / different
  command); never tiebreak between two contradictory reads. **After any batch with a cancel/error,
  treat EVERY same-batch result as unknown and re-verify from disk before narrating success** — a
  cancel-cascade is exactly the empty/ambiguous condition that triggers shape-3 confabulation.
- **Converge before acting on state that gates an irreversible op.** Before a
  reset/delete/force-push/merge/publish, the gating state must come from a read you
  re-derived *now* and corroborated — not a remembered count, not a narrated SHA,
  not a single flaky read.
- **Prefer serial over parallel for state-gating reads on Windows.** Parallelism is
  fine for independent fan-out; it is the documented trigger for shapes 1–2 on
  state reads that gate a decision.
- **Under a sustained flaky channel, prefer disk-deliverable workers + Read-back over inline
  shell output.** When the channel is dropping results across a tool-heavy stretch, restructure the
  work so the load-bearing result lands on disk: dispatch a worker that *writes a verdict file*, then
  poll the file (Read / `ls`) rather than trusting an inline shell echo. Disk is the reliable signal
  (CLAUDE.md § Scouts and Disk-First Verification); the flaky channel is the result-text return, not
  the filesystem. (2026-05-29: a central learn-lessons run's reconciliation and fold workers used
  exactly this shape and were robust to the drops while bare `echo`/`git status` calls had to be
  re-issued 2–4×.) This is the same disk-first discipline `scout-and-dispatch-discipline.md` applies
  to scout hallucination, here applied to the harness-side drop.

## Why doctrine alone is not enough — the enforcement floor

The agent that must follow this protocol is the same one that confabulates when the
channel fails. So the load-bearing surfaces are guarded at the **tool boundary**,
where the decision is re-derived shell-side and applied before the model narrates:

- **`BLOCK-DESTRUCTIVE-GIT-ORPHAN`** — committed-work loss (reset --hard / force-push
  / branch -D). → `coordinator/docs/wiki/coordinator-tripwires/`.
- **`BLOCK-DESTRUCTIVE-RM`** — uncommitted-work loss (`rm` of untracked/modified
  trees or a `.git` store). → `coordinator/docs/wiki/coordinator-tripwires/`.

These guards are the floor, not the protocol's replacement: they cover the concrete
irreversible shapes seen so far. Any NEW surface where a fabricated premise can drive
an unrecoverable action is a candidate for a sibling guard — propose one rather than
trusting the protocol to hold under flakiness.

## Uniform Result Across N Independent Items Is a Checker Bug Until Proven

**A uniform verdict across N genuinely independent items (all PASS, all FAIL, all "100% changed", all identical scores) is a checker/instrument bug until proven otherwise — verify the instrument before reporting the result.** Independent items rarely all land on the same value; when they do, the likeliest explanation is that the measuring tool is broken (a comparator always returning the same branch, a probe reading the same stale path for every item, a normalizer that nulls every input) — not that reality is uniform. Read one item by hand against the instrument's own logic before broadcasting the uniform verdict.

*project-rag-ue-addon.* An N-item check returned the same result for every item; the uniformity was the tell that the instrument — not the items — had failed. Sibling to "do not infer from absence" above: a too-clean signal is as suspect as an empty one.

*Sibling principle — deterministic signal over contextual signal.* When multi-consumer reports of *different* failures share a supervisor, read the giveup sentinel's **exit code** and `timestamps:` array before its `last_child_stderr_tail` — the tail can be evidence from a longer-lived sibling that booted further than the crashing process, so it describes a different process than the one that crashed the window. Two consumers reporting different symptoms can be one root cause in disguise. Full writeup with the empirical anchor (project-rag, exit 79 `HostProfileUnknownError`): `verification-before-completion.md` § Multi-Consumer Failure Reports May Share One Root Cause.

## Pin an External Process-Killer with a Rolling Pre-Death Process-Table Observer

**To diagnose what kills a process you don't control, pin it with a rolling pre-death process-table snapshot loop — NOT a passive liveness poll.** A liveness poll (`is the PID still alive?`) tells you *when* death happened but captures nothing about *what* caused it: by the time the poll observes the absence, the killer and its context are gone. The diagnostic that works is a rolling observer that continuously snapshots the process table (parent/child links, argv, RSS, recent spawns) into a ring buffer, so the last snapshot *before* death holds the evidence — the sibling that issued the kill, the OOM pressure, the launcher re-exec.

*project-rag.* A shared host singleton kept dying; a passive liveness poll only confirmed the death, never the cause. A pre-death process-table observer captured the killing sibling. Pairs with verification-before-completion.md § "Don't kill the sibling-repo daemon you depend on" — there the concern is *causing* a kill, here it is *catching* one.

## A Flaky Read Can Hallucinate File Content — A PM-Authored Premise Outranks One Suspicious Read

**Shape-3 confabulation is not limited to git SHAs and merge state — a flaky `Read` can return fabricated *file content* (source code, docstrings, config) that contradicts what is on disk, and that fabrication can invert an otherwise-correct handoff premise.** When a read of a file conflicts with a premise the PM authored (a handoff line, an explicit decision, a stated invariant), suspect the *channel* before retracting the *premise*. A PM-authored premise is a stronger prior than a single suspicious read: do not flip course on it until a second, different channel corroborates the contradicting read.

**How to apply.** When a `Read` returns content that contradicts a PM-authored premise (or any high-confidence prior), do **not** act on the read in isolation:

## Windows Process-Liveness Is a Flaky Channel — Never Relaunch on a "0 Processes" Read

`pgrep`/`Get-Process` can return intermittent empty results on Windows even when the process is running. Never relaunch a long job (corpus ingestion, model training, large build) based on a "0 processes" read from the process-liveness channel. The harness notification (file written, exit code returned) is the only authoritative completion signal. For interim progress, stream output to a file and read the file. Apply: treat any "0 processes" result on Windows as "liveness channel failed, status unknown" — not as "process stopped."

## Tool-self-narration is suspect when contradicting curated doctrine

Tool-output prose (MCP tool descriptions, doctor summary paragraphs, installer step descriptions) carries the trust of a third-party source — not ratified doctrine. When a tool's self-narration contradicts a wiki or CLAUDE.md rule, trust the doctrine and file the drift as a finding. Apply: never silently update your behavior based on tool narration that contradicts established doctrine; file a finding and surface to PM.

## A uniform 429 across a fan-out is self-inflicted overconcurrency, not (necessarily) a platform gate

**A uniform `429 "Server is temporarily limiting requests (not your usage limit)"` across a verify/fetch/agent fan-out — with `0-0` / abstained / "all claims refuted-or-inconclusive" results for every item — is the signature of self-inflicted overconcurrency, not a platform gate.** A concurrency-triggered server-side throttle fires when a hand-authored harness fans out web-tool callers past the safe ceiling (≤5 concurrent web-tool callers — see `dispatching-parallel-agents.md` § Concurrency Budget). The throttled agents return nothing, so the harness reports every claim as refuted/inconclusive — a **false negative**: the claims were never adjudicated, not disproven. This is the same tell as the "Uniform Result Across N Independent Items Is a Checker Bug" entry above — a uniform verdict across genuinely-independent items is an instrument failure until proven otherwise; here the instrument is throttled. <!-- Review: code-reviewer F1 — cross-ref direction was inverted; Uniform-Result section is at ~:139, 429 section at ~:165 -->

**First response is to REDUCE CONCURRENCY, not wait-and-re-fire.** Re-firing the same fan-out into the same throttle without lowering agent count changes the clock, not the variable that matters (see `coordinator/docs/wiki/coordinator-tripwires/` § RE-FIRE-INTO-THROTTLE).

**Discriminator vs. session-quota exhaustion.** Two distinct failures share the `429` surface: (1) the *concurrency-triggered* throttle here shows "temporarily limiting requests — not your usage limit" and scales with burst size — remedy is fewer concurrent callers; (2) *session-quota exhaustion* shows "session limit" / "resets HH:MM" strings and is covered by the separate QUOTA-SELF-DETECT tripwire — remedy is wait-for-reset, not concurrency reduction. Do NOT misapply QUOTA-SELF-DETECT's wait-it-out remedy to a concurrency-triggered 429.

**A single-agent probe cannot predict a concurrency-triggered throttle.** Because the limit is triggered by concurrency, a one-call liveness probe returning CLEAR says nothing about whether a subsequent burst will trip it — a single probe minutes before a burst routinely reads CLEAR right before the burst throws repeated 429s. "Probe with one live agent before bursting" is therefore unsound for this failure class; the only sound mitigation is staying under the concurrency ceiling.

(If a relative path above doesn't resolve from this file's location, adjust it — dispatching-parallel-agents.md and coordinator-tripwires.md are sibling files in the same docs/wiki/ directory.)

## API quota exhaustion looks like a clean "completed" return with error-text body

**When the user's per-window API quota is hit mid-dispatch, sub-agents return content matching service-level error strings ("session limit", "rate limit", "quota", "resets HH:MM") with zero real findings — and the runtime hook reports the task status as `completed`. Treat any sub-dispatch whose body matches those patterns as a failed-dispatch-needing-re-dispatch, not as a clean review.** Empirical: 2 of 3 partitioned `code-reviewer` slices during a `/workstream-complete` PARTITION-MANDATORY pass returned the literal "You've hit your session limit · resets HH:MM" string while one slice returned a real WARN with 4 actionable findings; the review trail would have written the empty slices as `verdict ok` had the EM not pattern-matched. Discipline: before accepting any partitioned-review slice as authoritative, grep the body for service-level error patterns; on match, wait for quota reset or escalate to PM with the partial-coverage situation — never write a trail record marking quota-exhausted slices as verdict-ok. The "agent returned" signal is distinct from "agent succeeded against its brief"; the runtime task-notification layer conflates them. (case: example-game-repo)

<!-- DoE resolved: 2026-06-15 — see snippets/quota-self-detect-preamble.md and coordinator-tripwires.md § QUOTA-SELF-DETECT-AND-EM-SCAN. Hook altitude originally proposed (v1) was rejected post-C0 substrate verification (PostToolUse-Agent is dispatch-time-only on async); shipped as two-layer detection (subagent self-detect + EM-side body scan). -->

## Tool-channel lag — git is the only oracle; dispatch delicate edits through subagents

When the main-context tool channel degrades (garbled responses, empty reads, contradictory state), subagent channels stay reliable. Git is the only oracle for what is actually on disk — verify via `git log --stat` and `git show` rather than relying on tool-channel reads during a degraded session. For delicate edits under channel uncertainty, dispatch through a subagent rather than executing in the flaky main context.

1. Treat the contradicting read as *unknown*, not *ground truth* — it may be shape-3 fabrication.
2. Re-read the same file through a **different channel** — a different tool (`Read` → PowerShell `Get-Content` / `Bash cat`), or a different command shape. The cross-channel read is the tiebreaker, exactly as "read the source a third way" applies to contradictory state reads above.
3. Hold the PM-authored premise as the operating prior **until two independent channels agree** on the contradicting content. Only then retract the premise.

*sibling-repo universal.* A flaky `Read` returned fabricated `whoami.py` docstrings that contradicted the real source; a second channel (PowerShell) confirmed the on-disk code matched the PM-authored premise all along. The trap is treating one suspicious read as authoritative enough to retract a premise the PM stated deliberately — premise-retraction is a course-inverting action, and shape-3 fabrication is precisely the condition under which one read cannot be trusted to drive it.

## Failure-mode taxonomy — harness-drop → confabulation chain

The Windows / parallel-fan-out flakiness has a consistent two-stage shape:

1. **Stage 1 — harness loss.** The Claude Code runtime drops, scrambles, or truncates a tool-call result. Triggered most often by a parallel-batch cancel-cascade: one agent in a fan-out (typical reproducer: 7-agent wave) times out, and the harness emits stale or incomplete results for siblings rather than the live transcript. The result *looks* well-formed at the protocol level — there is no "error" envelope to branch on.

2. **Stage 2 — confabulation fill.** The model receives an empty / garbled / contradictory result, and absent a structural signal that the channel failed, completes the pattern by hallucinating plausible state. The signature shape is **Shape-3 confabulation** — a complete-looking response with **no actual tool-use** behind it (phantom merge SHAs, fake green CI summaries, asserted file contents that were never read).

**Diagnostic differentiator.** Shape-3 distinguishes from the block-destructive floor cases. The floors (`BLOCK-DESTRUCTIVE-GIT-ORPHAN`, `BLOCK-DESTRUCTIVE-RM`) prevent irreversible *actions* on flaky reads. Shape-3 is the upstream *belief* failure that, absent floors, would feed those actions. Mitigation order matters: re-run SOLO (not inside the failed fan-out loop), and where two reads disagree, read a third way — never act on a single flaky read before an irreversible operation. Per `docs/decisions/DR-165-tool-output-flakiness-stop-at-current-floors.md`, the boundary holds at current floors — no new guards; the doctrine fold-in here is the *naming*, not new guard surface.

## A Pasted Transcript Is a Specimen, Not Live Session State

A transcript, quoted command output, or copy-pasted log the PM hands you is a **specimen** — a snapshot from some other context — not the live state of *this* session. Running a command derived from a quoted transcript without confirming the current identity (cwd, repo, branch, host) re-executes it against whatever this session happens to be pointed at, which may be a different repo entirely.

**Rule:** before running any command lifted from a pasted transcript or quote, confirm the session's own identity — `pwd` / `git -C <path> rev-parse --show-toplevel` / branch — and prefer `git -C <explicit-path>` over bare `git` so the command can't silently bind to the wrong working tree. The transcript tells you what happened *there*; it is not authoritative about *here*. Sibling to "do not infer from absence" — a specimen is borrowed state, treated as live, which is its own confabulation trap.

## Clock-Trap: Transcript Timestamps Are UTC — Never Eyeball "Yesterday"

**Transcript and record timestamps are UTC (`Z`). Always compare against `date -u`, NEVER against your mental "today" / "yesterday afternoon".** A timestamp that looks like "yesterday" in your local TZ may be minutes ago UTC. Run `date -u` and compare the literal clock before concluding a peer's claim is stale.

**Truncated-at-your-boot is not a crash signal.** A peer's transcript captured at YOUR session boot looks truncated because it is mid-turn — the harness snapshot captured it in flight. A truncated-looking transcript is not evidence of a crashed session; it is evidence of a concurrent live session captured at an arbitrary point. Do NOT classify a claim as orphaned on this basis.

**The three wrongful-takeover shapes — named side by side so a reader sees all three:**

1. **TZ-false-dead (lstart primitive):** the machine TZ roll corrupts `_cs_stable_pid_alive` — it computes a stale lstart comparison that returns dead for a live session. Owned by `docs/plans/2026-06-30-liveness-lstart-tz-invariant-epoch.md`. The primitive is wrong; fixing it makes `cs_claim_holder_live` return the correct answer.

2. **Human bypass (this entry):** the EM bypasses the liveness primitive entirely — eyeballs a transcript, judges the claim "crashed" on heuristic evidence (old-looking timestamps, truncated-looking transcript), and clears the lock by hand. The primitive would have returned live; it was never called. Fix: force the manual claim-clear path through `cs_claim_holder_live` / `cs_clear_claim_if_dead` before any `rm` or re-claim. → `CLAIM-CLEAR-LIVENESS` in `coordinator/docs/wiki/coordinator-tripwires/`.

3. **Legacy pid-only false-dead:** a claim dir with no `session_id` file (pre-upgrade or upgrade-era) routes `_cs_claim_holder_live` to the ephemeral-pid test, which reads "structurally always dead in-harness" regardless of whether the session is live. A legacy pid-only claim whose holder is LIVE will be classified dead and cleared — a false-dead stomp via a different door. The human stand-down (shape 2) still matters for these dirs: even when the automated path classifies the claim dead, the EM should note whether `session_id` is absent before accepting that verdict.

**2026-06-30 near-miss (project-rag) as the canonical instance of shape 2.** A fresh session read `01:1xZ` as "yesterday afternoon" when `date -u` was `01:19Z` the same night. `cs_claim_holder_live` would have returned live. The claim was stomped, mislabeled "(crashed)", and only caught downstream by a `source_memo:` collision check. Running `date -u` before eyeballing the timestamp would have prevented it.

## Red CI Is Not Always Red Code — Triage By Run-Duration First

A CI job that fails in seconds without ever starting the test runner is a **billing / quota / infrastructure gate**, not a test failure — the code never ran. Reading "CI red" as "my change broke tests" and diving into the diff wastes a cycle on a failure that lives in the billing dashboard, not the codebase.

**Rule:** on a red CI run, read the **run duration and the failing step** before the test output. A multi-second-to-zero failure at the setup/billing/auth step (quota exceeded, runner unavailable, credential expired) means the oracle never executed — the same "blocked ≠ failed" distinction the build-gate `blocked` classification draws (verification-before-completion.md). Triage by duration first: a sub-runner-startup failure is infra; a failure after the test runner started is a candidate code regression. This is the CI-channel analogue of the quota-exhaustion-looks-like-completion family above. *(case: project-rag.)*
