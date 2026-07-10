---
title: Hook best practices
created: 2026-05-17
type: doctrine
related:
  - plugins/coordinator/docs/wiki/daily-branch-discipline.md
  - plugins/coordinator/docs/wiki/claude-code-platform-gotchas.md
---

# Hook Best Practices

Working notes on Claude Code hook mechanics — the platform behaviors that are non-obvious and have caused silent failures.

## Editing a live Bash-matcher hook: stage, don't multi-`Edit` the live path

The harness `exec`s each hook fresh from disk on every matching tool call, so a multi-`Edit` sequence against a hook currently registered under a Bash-inclusive PreToolUse matcher briefly exposes every intermediate state as the live enforcement code for every concurrent agent's Bash tool. Use `coordinator/bin/edit-live-hook.sh stage`/`commit` (stage → edit scratch copy → `bash -n` validate → atomic swap) instead of editing the live path directly. → `docs/wiki/concurrent-em-hazards.md § H33`, `docs/wiki/coordinator-tripwires.md § LIVE-HOOK-EDIT`.

## PreToolUse deny: JSON output, not exit 2

When a PreToolUse hook needs to block a tool call, emit JSON to stdout — not a non-zero exit code.

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "<human-readable explanation>"
  }
}
```

The flat `{"permissionDecision":"deny"}` shape (no `hookSpecificOutput` wrapper) is an older API form that silently passes through. Always use the nested `hookSpecificOutput` wrapper — canonical example: `block-subagent-archive-write.sh:204-218`.

Exit codes do NOT block-with-a-clean-reason. **exit 1** is non-blocking — the tool call proceeds and stderr goes to the *user terminal* only (advisory; the model never sees it). **exit 2** at PreToolUse *does* block, but the reason is delivered as raw stderr into the model's turn, not surfaced in the Claude Code permission UI (and exit-2 semantics vary by hook event — see § Friction-as-warning for the full PreToolUse-vs-PostToolUse table). JSON deny (stdout + exit 0) is the protocol that blocks the call AND surfaces a structured reason in the Claude Code UI — prefer it for any PreToolUse block. (In-tree witness for exit-2-blocks: `check-claude-md-size.py:6`.)

The `permissionDecisionReason` field is required — hooks that omit it produce a terse "denied" with no context, which is harder to diagnose when an agent hits the block.

→ `docs/wiki/daily-branch-discipline.md` § Enforcement surfaces shows a working example of the JSON deny shape.

### Multi-hook deny aggregation: registration order, first-deny-wins

When several hooks are registered for the same event+matcher (e.g. multiple `PreToolUse` / `"matcher": "Bash"` entries), Claude Code runs them in **hooks.json registration order** and the **first hook that emits a JSON deny wins** — the tool call is blocked with that hook's `permissionDecisionReason`, and later hooks' decisions for that call do not override it. Advisory `allow` + `additionalContext` outputs from non-denying hooks are surfaced; only one decision blocks.

This ordering is a load-bearing contract when consolidating multiple same-matcher hooks into a single dispatcher process: the dispatcher must call the folded checks in the **same registration order** and short-circuit on the first deny, or the surfaced reason can change for commands that more than one guard would block. The canonical consolidation — `hooks/scripts/preuse-bash-dispatch.sh` (folds 8 `Bash` guards) — preserves this via an explicit first-deny-wins chain, and `hooks/tests/test-preuse-bash-dispatch-golden.sh` is the differential test that locks the dispatcher's `{decision, reason}` to the legacy 8-separate-hooks behavior. See `docs/plans/2026-06-30-pretooluse-bash-hook-dispatcher.md`.

**The differential's equivalence scope is the DECISION channel only — `{permissionDecision, permissionDecisionReason/additionalContext}` on stdout — NOT stderr side-output.** This distinction became load-bearing when `validate-commit.sh` was folded into the dispatcher (Phase 2, `docs/plans/2026-06-30-fold-validate-commit-into-dispatcher.md`): unlike the other folded guards, validate-commit emits content **warnings to stderr** even on the allow path. As a separate hook process, those warnings printed independently of whether another hook denied. In the folded first-deny-wins chain, if an earlier guard (e.g. block-no-verify) denies, `check_validate_commit` never runs and its stderr warnings are not printed for that invocation. **This stderr-suppression-on-prior-deny is an intentional, correct delta — not a regression:** a denied commit is not happening, so its content warnings are moot; the decision channel (what the golden test asserts) is byte-identical. The general rule: when folding a guard that side-outputs to stderr, the golden differential pins the decision channel; stderr-on-prior-deny is explicitly out of equivalence scope, because re-running a later check purely to reproduce its stderr would violate first-deny-wins.

## `async: true` on touched-files hooks races safe-commit reads

PostToolUse hooks that produce state consumed by `coordinator-safe-commit` (touched-file lists, session-scope records) must run synchronously. Setting `async: true` means the hook process is still writing when the safe-commit helper reads — files are missed from scope detection and land outside the commit scope silently.

The 70ms synchronous cost is irrelevant at the cadence commits fire. Default to `async: false` for any hook whose output feeds an adjacent operation in the same session. Use `async: true` only for fire-and-forget telemetry hooks whose output no other tool reads.

### Failure-surfacing convention for load-bearing async hooks

Async-hook stdout/stderr is best-effort — the harness may drop it, and a non-zero async exit is swallowed. A fire-and-forget hook whose failure is harmless can stay silent. A **load-bearing** async hook — one whose failure leaves persistent substrate wrong — needs an explicit read-back path.

**Convention.** Load-bearing async hooks record failures via `lib/async-hook-status.sh` (`ahs_record_failure <hook> <exit> <detail> [log]`), writing a per-hook JSON marker to `${CLAUDE_HOME:-$HOME}/.claude/.cache/async-hook-status/<hook>.json` (latest-wins; a re-fail overwrites). `session-init.sh` (sync hook — its stdout reliably reaches the operator) calls `ahs_surface_and_clear` early in its body, emitting one operator-facing line per unread marker and deleting it. Clear-after-surface + re-write-on-persist = no re-nag: if the hook keeps failing the marker re-appears on the next boot; if it was fixed it stays quiet.
<!-- Review: code-reviewer Slice-A — (F8) clarify async timing: producer and consumer run in the same Claude Code session, but async producers (bootstrap-substrate, platform-localize) typically have NOT finished by the time the sync session-init reads — so the marker written by an async producer on boot N is surfaced by session-init on boot N+1. A persistent failure re-writes each boot so it keeps re-surfacing on the following session-init. Keep the "next boot" framing; the async race is the reason it applies. -->

**Two-pronged discriminator.** A hook qualifies for this convention iff BOTH prongs hold:

(a) **Silent persistent harm** — failure mutates substrate the session depends on, and that mutation persists in a wrong state.  
(b) **No self-correction before the harm lands** — a transient failure is not corrected by a subsequent run before the operator is affected.

The discriminator is the load-bearing value of the design: applying the convention to advisory or self-healing hooks adds boot noise for no value. Guards match conditions, not containers.

**Worked counter-example — `session-heartbeat.sh` (EXEMPT).** `session-heartbeat.sh` is arguably load-bearing (it drives liveness / claim-staleness), yet it is correctly exempt. It fires on every UserPromptSubmit (×2 across PreToolUse and PostToolUse Bash), so a transient failure self-corrects on the next beat before any persistent harm accumulates — prong (b) is not met. One-shot boot hooks (`platform-localize.sh`, `bootstrap-substrate.sh`) fail both prongs: they are load-bearing AND have no self-correction opportunity before the session that depends on their output begins. The remaining async hooks — `coordinator-reminder.sh` (×2), `ue-knowledge-distrust.sh` (×2), `session-heartbeat.sh` (×2), `runtime-tripwire-stop-watcher.sh` (asyncRewake ×1) — are advisory nudges or self-healing machinery; all correctly exempt.

**Distinguish from the orphan-sweep append-rotate pattern.** `session-init.sh` also carries an unrelated marker pattern: it appends to `tasks/orphan-sweep-notes.md` (git-tracked, consumed by `/workday-start` Step 0.8, rotated by that ceremony). These two patterns are architecturally distinct — do not conflate them:

- **async-hook-status convention** — per-machine transient markers in `.cache/async-hook-status/<hook>.json`; gitignored; cleared after surface, re-written on re-fail; read by `session-init.sh` at next boot. Use when a one-shot boot hook failure needs surfacing to the operator before the next session proceeds.
- **orphan-sweep append-rotate** — git-tracked append-only log at `tasks/orphan-sweep-notes.md`; rotated by `/workday-start`; swept by `/distill`. Use when an audit trail needs review at a scheduled cadence ceremony, not at next boot.

## session_id reaches hooks but NOT hook-spawned subprocesses

Claude Code injects `CLAUDE_SESSION_ID` into the hook's own environment, but that variable is not inherited by subprocesses the hook spawns via `bash -c`, Python subprocess, or similar. A hook that forks a worker expecting to read `CLAUDE_SESSION_ID` from its environment will silently get an empty string.

Two remediation patterns:

1. **Explicit arg.** Pass `$CLAUDE_SESSION_ID` as a positional argument when launching the subprocess: `python worker.py "$CLAUDE_SESSION_ID"`.
2. **Sentinel file.** Have the hook write the session_id to a known path (e.g., `.git/coordinator-sessions/current-session-id`) before launching the subprocess; the subprocess reads from disk instead of env.

Pattern 1 is simpler for single-child spawns. Pattern 2 is better when the subprocess is a long-lived daemon that outlives the hook invocation.

## Transcript scrape: never `large-producer | grep -q` under `set -o pipefail`

A hook that scrapes the transcript — `if tail -N "$transcript" | grep -q PAT; then ...` — silently fails OPEN under `set -o pipefail` on any real-sized session. `grep -q` exits 0 on its first match and closes the pipe; `tail` (still writing the multi-MB transcript) takes SIGPIPE and dies with exit 141; `pipefail` then makes 141 the *pipeline's* status. The `if` evaluates FALSE **despite a match**, so the suppression/detection the scrape was supposed to drive never fires. It only manifests past the ~64KB pipe buffer, so small-fixture tests pass while the hook is dead in production (2026-05-30: both nudge hooks' skill-suppression branches were dead on every real-sized transcript — the `/handoff` nudge fired 100% of the time on the Skill-tool case).

**Fix — keep the early-exiting reader out of the pipeline.** Read into a variable, match via here-string:

```bash
RECENT_TAIL=$(tail -N "$transcript" 2>/dev/null || true)
if grep -qE PAT <<< "$RECENT_TAIL"; then ...
```

`tail` now runs standalone in command substitution (its SIGPIPE swallowed by `|| true`), and `grep` reads from the variable — no pipeline, no status to poison the `if`.

**Direction matters.** `grep PAT file | tail -1` is safe: `grep` is the producer and `tail` the consumer that reads to EOF, so `grep` never takes SIGPIPE. The trap is specifically the *early-exiting reader downstream of a large producer* (`grep -q`, `head`, `grep -m1`).

**Test it with a real-sized, deterministic fixture.** The repro is racy: a mid-stream match lets `grep` drain the pipe before `tail` blocks. To make a regression test that reliably fails against the bug, put the match EARLY in the byte stream (line 1) with ≫64KB queued behind it, all inside the `tail -N` window — mirroring how the real incident reproduced (an early match in a 1.4MB transcript). A 3-line fixture proves nothing.

## PreCompact false alarms: gate on ≥15% transcript size shrink

`PreCompact` fires on every event that may trigger context management — including subagent-result integration events that do not actually shrink the transcript. Emitting "context compacted" unconditionally on every `PreCompact` fire produces spurious advisory noise during normal heavy-use sessions.

Gate the message on measured shrink: compare the transcript token count before and after. Only emit if the shrink is ≥15% of pre-event size. Below that threshold the event was a housekeeping fire, not a compaction.

## Model-version gating: family fallbacks, not pinned arms

Hook scripts that branch on model name should match family prefixes, not pinned version strings.

Good:
```bash
if [[ "$CLAUDE_MODEL" == *opus* ]]; then ...
if [[ "$CLAUDE_MODEL" == *sonnet* ]]; then ...
```

Bad:
```bash
if [[ "$CLAUDE_MODEL" == *opus*4*6* ]]; then ...  # breaks on next minor release
```

Pinned arms like `opus*4*6*` break silently on the next version bump — the branch falls through to the else case with no error and wrong behavior. Family fallbacks (`*opus*`, `*sonnet*`, `*haiku*`) survive minor version bumps and new model releases.

## Disabled hook scripts: clean BOTH registration surfaces

Hook scripts have two registration surfaces: `hooks/hooks.json` (plugin-distributed, travels with the plugin) and `~/.claude/settings.json` (user-scope, machine-local). Removing or disabling a hook script on disk without cleaning BOTH surfaces is silent breakage:

- **Dangling `hooks/hooks.json` entry:** when the script (or a same-named file from a plugin reinstall) reappears, the hook re-activates — often at a much later date with no one remembering why it was disabled.
- **Dangling `settings.json` entry:** every PreToolUse/PostToolUse fire produces a `Hook error` until the entry is removed. Not a "harmless stale reference" — it fires on every tool call.

Doctrinal pair: disable in BOTH surfaces AND remove the script file in the same commit. If you remove the script first, the registration edits follow in the same commit. For temporary disable rather than permanent removal, comment out the entries rather than deleting the script.

## Friction-as-warning needs a typed override, not a toggle

When you want a hook to *change EM behavior* (not just leave a paper trail), block-with-typed-justification is the only shape that works. Warn-only fails silent — stderr at exit 0 goes to the user's terminal, not back into the model's context, so the EM never reads it.

The two effective shapes:

1. **Hard block + typed env-var override.** Hook emits a JSON deny (`{"permissionDecision":"deny", "permissionDecisionReason":"<four questions>"}`) unless `COORDINATOR_<SCOPE>_PUNT="<plain-English sentence>"` is set. Trivial overrides ("1", "ok", strings under ~12 chars) are rejected by the reason-parser — the cognitive load IS the design point. The EM must articulate *what is being punted* while the deny reason sits in context.

2. **Exit 2 with stderr.** The Claude Code runtime treats exit 2 as "feed stderr into the model's next turn." This reaches the model — but **whether it also blocks depends on the hook event:**
   - **PreToolUse `exit 2` BLOCKS** the tool call (stderr → model). Wrong altitude for a pure warn.
   - **PostToolUse `exit 2` does NOT block** — the tool already ran, the file is on disk, only the stderr reaches the model. This is the genuine warn-reaches-the-model-**without**-blocking channel.

   So a "warn, never block" hook whose audience is the EM must fire at **PostToolUse** and `exit 2`. Canonical example: `nudge-unauthorized-handoff.sh` (PostToolUse Write on `state/handoffs/`|`tasks/spinoffs/`) — see `coordinator-tripwires.md` § `NUDGE-UNAUTHORIZED-HANDOFF`.

Stderr at exit 0 is the failure mode — the message lands in the user terminal but never reaches the model that just made the decision. If the EM is the audience, the EM has to be forced to read it.

The cost isn't keystrokes — it's the moment of friction that surfaces the lazy-punt before it becomes a queue entry. If writing the override sentence feels harder than just fixing the underlying thing, the hook worked.

Pattern generalizes to any "don't reflexively reach for this surface" tripwire: `nudge-improvement-queue-write.sh` and similar advisory hooks — all use block-with-override or exit-2-with-stderr; none use stderr-at-exit-0. (`block-off-daily-branch.sh` retired 2026-07-05; replaced by the SessionStart `session-ensure-branch.sh` active-behavior hook.)

### Reliability of the gating signal must match the cost of being wrong

A *block* (PreToolUse deny / `exit 2`) gated on an unreliable signal fails **CLOSED** — it denies authorized work and trains the EM to reflexively reach for the override, defeating the point. The same unreliable signal used to SUPPRESS a *non-blocking nudge* (PostToolUse `exit 2`) fails **OPEN** — at worst the EM reads one extra nudge and proceeds.

When the detection cannot be made reliable, don't harden the signal — lower the consequence of its being wrong (block → nudge). `block-unauthorized-handoff.sh` detected "is an authoring skill active" by scraping the transcript for `<command-name>` tags / `/spinoff` strings; the Skill tool emits no `<command-name>`, and large tool outputs bury the invocation past any grep window. Two patches tried to make the *scrape* window-independent and it still false-blocked a PM-authorized `/spinoff` (2026-05-28). The third rework left the scrape exactly as unreliable as before and instead moved it from gating-a-block to suppressing-a-nudge (`nudge-unauthorized-handoff.sh`). That is the design-as-offers principle applied to hook altitude: the signal didn't get better, the blast radius of its being wrong got cheap.

## Plugin-owned hooks belong in hooks/hooks.json, not user-scope settings

Hook entries placed in user-scope `settings.json` are invisible to other machines and break marketplace distribution. Plugin hooks must live at `hooks/hooks.json` inside the plugin directory — this is the path the plugin system reads on install and the path that travels with the plugin to new machines.

User-scope `settings.json` hooks are for machine-local overrides that intentionally should not distribute. If a hook is load-bearing for a plugin's behavior, it belongs in the plugin's `hooks/hooks.json`.

**`--plugin-dir` delivery exception.** ONLY when the plugin is delivered via `--plugin-dir` (which disables plugin-declared hook auto-wire, observed behavior 2026-07-04; issue ref #38699 — approximate, spot-check before OSS publish), generate `settings.json` hooks from `hooks.json` as a machine-local delivery artifact; marketplace/OSS consumers keep `hooks.json` as SSOT with the normal auto-wire.

## Deny-hook allowlists that need per-agent maintenance should invert to blocklists of the violation class

When a PreToolUse deny hook carves out legitimate cases via a regex allowlist, and that allowlist must grow every time a new pipeline agent ships, the hook has the wrong polarity. The legitimate cases are unbounded (every new authorized agent adds one); the violation class is fixed (unauthorized mutation of a specific surface by a specific agent kind).

**Rule:** invert. Blocklist the violation class (e.g., `subagent_type = coordinator:executor`), allow everything else to pass through. The lookup chain is: back-pointer `agents/<agent_id>/em-session-id.txt → dispatched-agents.txt column 3 → subagent_type`. A growing-allowlist smell (four suffixes added over two months) is the tell.

**Design-as-offers complement:** even after inverting, the hook should be offer-shape — propose the better alternative, not just block. See `docs/wiki/eager-agent-calibration.md`. Source: 2026-06-09 block-subagent-plan-body-write.sh inversion.

## Script names encode invariants — if the invariant inverts, retire don't rename

When a hook or validator script's name encodes a now-defunct invariant (e.g., `block-X-mirror`, `verify-Y-single-tree`), the right move is retirement, not repurposing. Changing a path constant or condition inside the script while leaving the filename intact produces a script whose name lies — it will false-positive-block legitimate writes in any session where the name is read without the body.

Retirement protocol: (1) read the spec backlink to confirm the invariant is genuinely defunct, not just locally disabled; (2) retire the script file; (3) delete the hook registration from `hooks/hooks.json` and any `settings.json` entries; (4) update doctrine references — all in one commit. Running the unupdated hook post-inversion is silent breakage: the block fires on correct writes with no error message pointing at the stale invariant.

## Capability-gate hooks must fail-OPEN on capability-absent — probe key-presence, not `jq // default`

A PreToolUse gate that reads a `tool_input` field with a `// default` fallback (e.g. `.tool_input.run_in_background // false`) collapses two distinct states into one: **key-absent** (the harness build does not expose the param at all) and **key-present-but-false** (the caller deliberately set it false). When a newer harness drops the param, the gate reads absent-as-false and hard-denies with **no satisfiable escape** — the agent cannot set a param the build doesn't expose.

This is exactly how `nudge-foreground-agent-dispatch.sh` bricked EVERY `Agent` dispatch on Claude Code 2.1.176+ (the Agent tool there is async-by-default and exposes no `run_in_background`). Fixed `ce73b88d`; the background-by-default doctrine across CLAUDE.md / `dispatching-parallel-agents.md` / `runtime-tripwire.md` was reconciled in `2652ebeb`.

### …but key-presence ALONE is insufficient when the param can re-appear (2026-06-23)

The fix above keyed the deny on the *presence* of `run_in_background` in a single call's `tool_input`. That silently broke when the param's presence **flip-flopped**: Claude Code **2.1.178 re-exposed** `run_in_background`, and the normal foreground dispatch is *"just omit the param"* → key absent → the hook hit its capability-probe branch and passed → **the gate did nothing.** The deny only fired on an explicit `run_in_background: false`, which is essentially never typed.

The deeper problem: **from one call's `tool_input` an absent key is genuinely ambiguous.** Param-less build (absent = can't-honor → must pass, brick-safe) and param-ful build (absent = caller omitted it → foreground → must deny) are byte-identical in the payload. No single-call key-presence test can tell them apart.

**Resolution — LEARN the capability per session, in a brick-proof scope.** The harness leaks its capability for free: if *any* dispatch this session carries the key (either value), this build exposes the param. Record that as a **session-scoped sentinel** (`<git_root>/.git/coordinator-sessions/<session_id>/.harness-bg-capable`); thereafter an absent key is a deliberate foreground omission → DENY, and before calibration an absent key still PASSES. Session scope is load-bearing: a fresh session starts uncalibrated (brick-proof) and the sentinel never outlives the session that wrote it, so it cannot go stale across a binary up/downgrade.

```bash
# Right — calibrate capability, then discriminate; brick-proof on a param-less build
present=$(jq 'has("run_in_background")' <<<"$input")
value=$(jq '.tool_input.run_in_background // empty' <<<"$input")
sentinel="$(git rev-parse --git-dir 2>/dev/null)/coordinator-sessions/$session_id/.harness-bg-capable"
[ "$present" = "true" ] && { mkdir -p "$(dirname "$sentinel")"; : > "$sentinel"; }  # learn capability
[ "$value" = "false" ] && deny "..."                       # explicit foreground → fire (always)
[ "$present" != "true" ] && { [ -f "$sentinel" ] || exit 0; }  # absent: deny only if calibrated
# else: present-and-true → pass (already calibrated above)
```

```bash
# Wrong (v1) — collapses absent and false, bricks param-less builds
[ "$(jq '.tool_input.run_in_background // false' <<<"$input")" = "false" ] && deny "..."
# Wrong (v2) — single-call key-presence; absent always passes, so a param-ful build
# where the caller simply omits the key (the common foreground case) sails through.
```

The general principle: a gate keyed on a harness capability the build may not expose is a forward-compat hazard, **and the capability can come back** — so don't pin behavior to a single call's payload shape. Deny only the **present-and-bad** state outright; for the ambiguous absent state, calibrate from observed evidence within a scope that cannot outlive the build it observed. Source: 2026-06-21 (v1), 2026-06-23 (v2 — flip-flop + per-session calibration).

## Bare-python / console-subprocess Write hooks false-positive on PowerShell's native-command `&` operator

A PreToolUse Write/Edit hook that flags "bare console-subprocess" or "bare-python" spawns by pattern-matching `& <name>` will **false-positive on PowerShell's native-command call operator**. In PowerShell, `& winget`, `& brew`, `& sh -c` are the *call operator* invoking an external command — not a `python -c` re-spawn or a `powershell.exe` re-entry. A hook whose regex treats `&` as a subprocess-spawn sigil denies legitimate `.ps1` authoring, and the executor then bypasses the hook entirely (Bash-heredoc write), defeating it.

The tell that the block is a false positive: the **authoritative tripwire test** (`test_no_bare_python_in_shell_scripts.py` and kin) passes on the same file — it correctly finds zero `python -c` invocations, because there are none. When the hook and its own tripwire test disagree, trust the test and narrow the hook's pattern to exclude PowerShell's `&` call-operator form. Guards match conditions, not containers (§ design-as-offers; `eager-agent-calibration.md`). Source: project-rag.

## nag→action: converting detect-and-nag hooks into active-behavior DO hooks

A **detect-and-nag** hook notices that something is wrong and warns the EM about it — blocking until the EM manually corrects the situation, or just emitting a message the EM must then act on. This pattern has two failure modes: (1) the nag blocks session start or tool use, introducing ceremony the EM must perform before working; (2) the nag is advisory at exit 0, so it reaches the user terminal but never the model — silently ignored every time.

The **nag→action conversion** promotes the active behavior itself into a SessionStart DO hook that silently fixes the condition at session open, removing the ceremony entirely. The converted hook acts once, emits at most one line of context when it does something, and is silent on the common (no-op) path. The EM never sees the problem.

**Reference exemplar:** `hooks/scripts/session-ensure-branch.sh` (strang-04). This hook replaces `block-off-daily-branch.sh`, which blocked tool use and demanded the EM run `/workday-start` to cut a branch. The DO hook cuts the branch automatically at session open and injects a single `[coordinator] Branch cut: now on <branch>` line as `additionalContext`. `strang-06` copies this shape for the next batch of conversions.

### 5-step reusable shape

Every nag→action conversion copies this structure:

1. **Source the shared ensure-lib from `lib/`.** Extract the active behavior into a sourced lib function so the same logic is reusable across the SessionStart hook and any other caller (e.g., a `bin/` step script). The lib owns the mechanism; callers own the event-gate and the post-action context.

2. **Gate to `startup` and `clear` events only — never `compact`.** Read `source` from stdin JSON and `exit 0` silently for `compact` or any unknown event. The EM is already on a valid state during compaction; re-running an ensure action would be wrong and disruptive. The event gate is the SessionStart hook's primary safety valve.

3. **Call the ensure function; let it cut, push, or fix.** Pass all required inputs; the function sets output variables (`_CS_ENSURE_RESULT`, etc.) and returns 0 on success or 1 on an unrecoverable error. On non-zero return, emit a one-line stderr note and `exit 0` — a collision or partial failure must never block the session from starting.

4. **Emit a one-line heads-up on action, silent on no-op.** When the function reports it did something (e.g. `FRESH-CUT`), echo one line to stdout so it appears as `additionalContext` in the session. When nothing needed doing, emit nothing. The goal is zero noise on the happy path and one informative line when the hook acted.

5. **Never deny, never block, always `exit 0`.** A SessionStart DO hook must not stop the session. The hook's job is to improve conditions silently, not to gate entry. Any error path — missing lib, git not available, suffix collision — falls through to `exit 0` after logging at most one stderr line.
