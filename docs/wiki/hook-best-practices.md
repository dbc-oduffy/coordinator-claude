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

The harness `exec`s each hook fresh from disk on every matching tool call, so a multi-`Edit` sequence against a hook currently registered under a Bash-inclusive PreToolUse matcher briefly exposes every intermediate state as the live enforcement code for every concurrent agent's Bash tool. Use claude-klabauter `coordinator/bin/edit-live-hook.py stage`/`commit` (stage → edit scratch copy → `bash -n` validate → atomic swap) instead of editing the live path directly. → `docs/wiki/concurrent-em-hazards.md § H33`, `docs/wiki/coordinator-tripwires.md § LIVE-HOOK-EDIT`.

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

The flat `{"permissionDecision":"deny"}` shape (no `hookSpecificOutput` wrapper) is an older API form that silently passes through. Always use the nested `hookSpecificOutput` wrapper.

Exit codes do NOT block-with-a-clean-reason. **exit 1** is non-blocking — the tool call proceeds and stderr goes to the *user terminal* only (advisory; the model never sees it). **exit 2** at PreToolUse *does* block, but the reason is delivered as raw stderr into the model's turn, not surfaced in the Claude Code permission UI (and exit-2 semantics vary by hook event — see § Friction-as-warning for the full PreToolUse-vs-PostToolUse table). JSON deny (stdout + exit 0) is the protocol that blocks the call AND surfaces a structured reason in the Claude Code UI — prefer it for any PreToolUse block. (In-tree witness for exit-2-blocks: `check-claude-md-size.py:6`.)

The `permissionDecisionReason` field is required — hooks that omit it produce a terse "denied" with no context, which is harder to diagnose when an agent hits the block.

→ `docs/wiki/daily-branch-discipline.md` § Enforcement surfaces shows a working example of the JSON deny shape.

### Multi-hook deny aggregation: registration order, first-deny-wins

When several hooks are registered for the same event+matcher (e.g. multiple `PreToolUse` / `"matcher": "Bash"` entries), Claude Code runs them in **hooks.json registration order** and the **first hook that emits a JSON deny wins** — the tool call is blocked with that hook's `permissionDecisionReason`, and later hooks' decisions for that call do not override it. Advisory `allow` + `additionalContext` outputs from non-denying hooks are surfaced; only one decision blocks.

This ordering is a load-bearing contract when consolidating multiple same-matcher hooks into a single dispatcher process: the dispatcher must call the folded checks in the **same registration order** and short-circuit on the first deny, or the surfaced reason can change for commands that more than one guard would block. The canonical consolidation — `hooks/scripts/preuse-bash-dispatch.py` (folds 8 `Bash` guards) — preserves this via an explicit first-deny-wins chain, and its differential test locks the dispatcher's `{decision, reason}` to the legacy 8-separate-hooks behavior. See `docs/plans/2026-06-30-pretooluse-bash-hook-dispatcher.md`.

**The differential's equivalence scope is the DECISION channel only — `{permissionDecision, permissionDecisionReason/additionalContext}` on stdout — NOT stderr side-output.** This distinction became load-bearing when `validate-commit.sh` was folded into the dispatcher (Phase 2, `docs/plans/2026-06-30-fold-validate-commit-into-dispatcher.md`): unlike the other folded guards, validate-commit emits content **warnings to stderr** even on the allow path. As a separate hook process, those warnings printed independently of whether another hook denied. In the folded first-deny-wins chain, if an earlier guard (e.g. block-no-verify) denies, `check_validate_commit` never runs and its stderr warnings are not printed for that invocation. **This stderr-suppression-on-prior-deny is an intentional, correct delta — not a regression:** a denied commit is not happening, so its content warnings are moot; the decision channel (what the golden test asserts) is byte-identical. The general rule: when folding a guard that side-outputs to stderr, the golden differential pins the decision channel; stderr-on-prior-deny is explicitly out of equivalence scope, because re-running a later check purely to reproduce its stderr would violate first-deny-wins.

## `async: true` on touched-files hooks races safe-commit reads

PostToolUse hooks that produce state consumed by `coordinator-safe-commit` (touched-file lists, session-scope records) must run synchronously. Setting `async: true` means the hook process is still writing when the safe-commit helper reads — files are missed from scope detection and land outside the commit scope silently.

The 70ms synchronous cost is irrelevant at the cadence commits fire. Default to `async: false` for any hook whose output feeds an adjacent operation in the same session. Use `async: true` only for fire-and-forget telemetry hooks whose output no other tool reads.

### Failure-surfacing convention for load-bearing async hooks

Async-hook stdout/stderr is best-effort — the harness may drop it, and a non-zero async exit is swallowed. A fire-and-forget hook whose failure is harmless can stay silent. A **load-bearing** async hook — one whose failure leaves persistent substrate wrong — needs an explicit read-back path.

**Convention.** Load-bearing async hooks record failures via the async-hook-status helper (`ahs_record_failure <hook> <exit> <detail> [log]`), writing a per-hook JSON marker to `${CLAUDE_HOME:-$HOME}/.claude/.cache/async-hook-status/<hook>.json` (latest-wins; a re-fail overwrites). A sync boot-time hook (its stdout reliably reaches the operator) calls `ahs_surface_and_clear` early in its body, emitting one operator-facing line per unread marker and deleting it. Clear-after-surface + re-write-on-persist = no re-nag: if the hook keeps failing the marker re-appears on the next boot; if it was fixed it stays quiet.
<!-- Review: code-reviewer Slice-A — (F8) clarify async timing: producer and consumer run in the same Claude Code session, but async producers (bootstrap-substrate, platform-localize) typically have NOT finished by the time the sync session-init reads — so the marker written by an async producer on boot N is surfaced by session-init on boot N+1. A persistent failure re-writes each boot so it keeps re-surfacing on the following session-init. Keep the "next boot" framing; the async race is the reason it applies. -->

**Two-pronged discriminator.** A hook qualifies for this convention iff BOTH prongs hold:

(a) **Silent persistent harm** — failure mutates substrate the session depends on, and that mutation persists in a wrong state.  
(b) **No self-correction before the harm lands** — a transient failure is not corrected by a subsequent run before the operator is affected.

The discriminator is the load-bearing value of the design: applying the convention to advisory or self-healing hooks adds boot noise for no value. Guards match conditions, not containers.

**Worked counter-example — `hooks/scripts/session-heartbeat.py` (EXEMPT).** `session-heartbeat.py` is arguably load-bearing (it drives liveness / claim-staleness), yet it is correctly exempt. It fires on every UserPromptSubmit (×2 across PreToolUse and PostToolUse Bash), so a transient failure self-corrects on the next beat before any persistent harm accumulates — prong (b) is not met. One-shot boot hooks (`coordinator/templates/bin/platform-localize.py`, and the now-removed `bootstrap-substrate` hook) fail both prongs: they are load-bearing AND have no self-correction opportunity before the session that depends on their output begins. The remaining async hooks — `coordinator-reminder.py` (×2), `session-heartbeat.py` (×2), `runtime-tripwire-stop-watcher.py` (asyncRewake ×1) — are advisory nudges or self-healing machinery; all correctly exempt. (`ue-knowledge-distrust.sh` does not exist — it and the rest of the SessionStart guardrail cohort were removed from `hooks.json` per PM directive; see `hooks.json`'s `SessionStart` `_comment`. Its naked-Python port, `ue-knowledge-distrust.py`, exists but is not wired.)

**Distinguish from the orphan-sweep append-rotate pattern.** The boot-time SessionStart hook also carried an unrelated marker pattern: it appends to `tasks/orphan-sweep-notes.md` (git-tracked, consumed by `/workday-start` Step 0.8, rotated by that ceremony). These two patterns are architecturally distinct — do not conflate them:

- **async-hook-status convention** — per-machine transient markers in `.cache/async-hook-status/<hook>.json`; gitignored; cleared after surface, re-written on re-fail; read by the boot-time SessionStart hook at next boot. Use when a one-shot boot hook failure needs surfacing to the operator before the next session proceeds.
- **orphan-sweep append-rotate** — git-tracked append-only log at `tasks/orphan-sweep-notes.md`; rotated by `/workday-start`; swept by `/distill`. Use when an audit trail needs review at a scheduled cadence ceremony, not at next boot.

## Fire-and-forget subprocess INSIDE a hot hook: background+detach, after the local write

Distinct from the hook-config `async:` field above (§ `async: true` …) — this is about a subprocess the hook body itself spawns. Wiring a **synchronous, timeout-bounded** subprocess (e.g. a network probe, a `curl` to a status endpoint) into a hot, highly-concurrent hook is a double hazard: every fire blocks on the round-trip, AND the added latency *widens benign races* in whatever concurrent writes fire alongside it — a probe that takes 300ms turns a sub-ms write window into a 300ms one during which a sibling agent's write can interleave.

**Two-part fix.** (1) Do the authoritative local write FIRST, so the persistent state is correct before anything can block. (2) Then run the fire-and-forget call backgrounded and detached — `( … ) & disown` — so the hook returns immediately and the subprocess cannot hold the fire open or extend the race window. Never place a blocking network call ahead of the local write it is supposed to report on.

## session_id reaches hooks but NOT hook-spawned subprocesses

Claude Code injects `CLAUDE_SESSION_ID` into the hook's own environment, but that variable is not inherited by subprocesses the hook spawns via `bash -c`, Python subprocess, or similar. A hook that forks a worker expecting to read `CLAUDE_SESSION_ID` from its environment will silently get an empty string.

Two remediation patterns:

1. **Explicit arg.** Pass `$CLAUDE_SESSION_ID` as a positional argument when launching the subprocess: `python worker.py "$CLAUDE_SESSION_ID"`.
2. **Sentinel file.** Have the hook write the session_id to a known path (e.g., `.git/coordinator-sessions/current-session-id`) before launching the subprocess; the subprocess reads from disk instead of env.

Pattern 1 is simpler for single-child spawns. Pattern 2 is better when the subprocess is a long-lived daemon that outlives the hook invocation.

## Transcript scrape: never `large-producer | grep -q` under `set -o pipefail`

A hook that scrapes the transcript — `if tail -N "$transcript" | grep -q PAT; then ...` — silently fails OPEN under `set -o pipefail` on any real-sized session. `grep -q` exits 0 on its first match and closes the pipe; `tail` (still writing the multi-MB transcript) takes SIGPIPE and dies with exit 141; `pipefail` then makes 141 the *pipeline's* status. The `if` evaluates FALSE **despite a match**, so the suppression/detection the scrape was supposed to drive never fires. It only manifests past the ~64KB pipe buffer, so small-fixture tests pass while the hook is dead in production (both nudge hooks' skill-suppression branches were dead on every real-sized transcript — the `/handoff` nudge fired 100% of the time on the Skill-tool case).

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

   So a "warn, never block" hook whose audience is the EM must fire at **PostToolUse** and `exit 2`. Canonical example: the unauthorized-handoff nudge, folded into `hooks/scripts/postuse-advisory-dispatch.py` (PostToolUse(*), narrows itself to Write on `state/handoffs/`|`tasks/spinoffs/`) — see `coordinator/docs/wiki/coordinator-tripwires/` § `NUDGE-UNAUTHORIZED-HANDOFF`.

Stderr at exit 0 is the failure mode — the message lands in the user terminal but never reaches the model that just made the decision. If the EM is the audience, the EM has to be forced to read it.

The cost isn't keystrokes — it's the moment of friction that surfaces the lazy-punt before it becomes a queue entry. If writing the override sentence feels harder than just fixing the underlying thing, the hook worked.

Pattern generalizes to any "don't reflexively reach for this surface" tripwire: the improvement-queue-write nudge and similar advisory hooks — all use block-with-override or exit-2-with-stderr; none use stderr-at-exit-0. (The daily-branch-block hook is retired; replaced by an active-behavior SessionStart branch-cut hook.)

### Reliability of the gating signal must match the cost of being wrong

A *block* (PreToolUse deny / `exit 2`) gated on an unreliable signal fails **CLOSED** — it denies authorized work and trains the EM to reflexively reach for the override, defeating the point. The same unreliable signal used to SUPPRESS a *non-blocking nudge* (PostToolUse `exit 2`) fails **OPEN** — at worst the EM reads one extra nudge and proceeds.

When the detection cannot be made reliable, don't harden the signal — lower the consequence of its being wrong (block → nudge). The original block-hook detected "is an authoring skill active" by scraping the transcript for `<command-name>` tags / `/spinoff` strings; the Skill tool emits no `<command-name>`, and large tool outputs bury the invocation past any grep window. Two patches tried to make the *scrape* window-independent and it still false-blocked a PM-authorized `/spinoff`. The third rework left the scrape exactly as unreliable as before and instead moved it from gating-a-block to suppressing-a-nudge (now folded into `hooks/scripts/postuse-advisory-dispatch.py`, predicate logic owned by `coordinator_core.hooks.nudge_unauthorized_handoff`). That is the design-as-offers principle applied to hook altitude: the signal didn't get better, the blast radius of its being wrong got cheap.

## Plugin-owned hooks belong in hooks/hooks.json, not user-scope settings

Hook entries placed in user-scope `settings.json` are invisible to other machines and break marketplace distribution. Plugin hooks must live at `hooks/hooks.json` inside the plugin directory — this is the path the plugin system reads on install and the path that travels with the plugin to new machines.

User-scope `settings.json` hooks are for machine-local overrides that intentionally should not distribute. If a hook is load-bearing for a plugin's behavior, it belongs in the plugin's `hooks/hooks.json`.

**`--plugin-dir` delivery exception.** ONLY when the plugin is delivered via `--plugin-dir` (which disables plugin-declared hook auto-wire, observed behavior; issue ref #38699 — approximate, spot-check before OSS publish), generate `settings.json` hooks from `hooks.json` as a machine-local delivery artifact; marketplace/OSS consumers keep `hooks.json` as SSOT with the normal auto-wire.

## Deny-hook allowlists that need per-agent maintenance should invert to blocklists of the violation class

When a PreToolUse deny hook carves out legitimate cases via a regex allowlist, and that allowlist must grow every time a new pipeline agent ships, the hook has the wrong polarity. The legitimate cases are unbounded (every new authorized agent adds one); the violation class is fixed (unauthorized mutation of a specific surface by a specific agent kind).

**Rule:** invert. Blocklist the violation class (e.g., `subagent_type = coordinator:executor`), allow everything else to pass through. The lookup chain is: back-pointer `agents/<agent_id>/em-session-id.txt → dispatched-agents.txt column 3 → subagent_type`. A growing-allowlist smell (four suffixes added over two months) is the tell.

**Design-as-offers complement:** even after inverting, the hook should be offer-shape — propose the better alternative, not just block. See `docs/wiki/eager-agent-calibration.md`. Source: block-subagent-plan-body-write.sh inversion.

### Subsuming a single-agent confinement hook into a policy hook: preserve sanctioned targets + cross-check confined-set vs offer-coverage

When you generalize a single-agent confinement hook (e.g. reviewer→`findings/`) into a policy-driven multi-agent one, three obligations that a naive port silently drops:

1. **Enumerate the OLD hook's sanctioned write-targets FIRST.** They MUST re-appear in the new policy's `sanctioned_dirs`, or the subsumed agent loses its only write dir. The reviewer's `findings/` target is the canonical case — caught at execute-time only by reading the sibling repo's binding `CONTRACT.md`, which used `findings/` as its own example. Don't infer the sanctioned set from the new policy; carry it forward from the old hook.

2. **Cross-check the confined set two ways.** (a) **Exclude broad-write / defined-output roles** — an Opus synthesizer writes its deliverable to a protocol path, not scratch, so confining it to a sandbox denies its *own output*. (b) **Every confined type that has a dispatch prompt MUST also receive the offer-preamble** — a confined agent without the offer text is *confined-blind*, which is exactly the confabulate-a-block failure the sandbox exists to prevent.

The two directions are separate: broadening who-is-confined and ensuring each confined type is offer-covered are independent checks, and a port that does one without the other regresses.

## Script names encode invariants — if the invariant inverts, retire don't rename

When a hook or validator script's name encodes a now-defunct invariant (e.g., `block-X-mirror`, `verify-Y-single-tree`), the right move is retirement, not repurposing. Changing a path constant or condition inside the script while leaving the filename intact produces a script whose name lies — it will false-positive-block legitimate writes in any session where the name is read without the body.

Retirement protocol: (1) read the spec backlink to confirm the invariant is genuinely defunct, not just locally disabled; (2) retire the script file; (3) delete the hook registration from `hooks/hooks.json` and any `settings.json` entries; (4) update doctrine references — all in one commit. Running the unupdated hook post-inversion is silent breakage: the block fires on correct writes with no error message pointing at the stale invariant.

## Capability-gate hooks must fail-OPEN on capability-absent — probe key-presence, not `jq // default`

A PreToolUse gate that reads a `tool_input` field with a `// default` fallback (e.g. `.tool_input.run_in_background // false`) collapses two distinct states into one: **key-absent** (the harness build does not expose the param at all) and **key-present-but-false** (the caller deliberately set it false). When a newer harness drops the param, the gate reads absent-as-false and hard-denies with **no satisfiable escape** — the agent cannot set a param the build doesn't expose.

This is exactly how `hooks/scripts/nudge-foreground-agent-dispatch.py` bricked EVERY `Agent` dispatch on Claude Code 2.1.176+ (the Agent tool there is async-by-default and exposes no `run_in_background`). Fixed `ce73b88d`; the background-by-default doctrine across CLAUDE.md / `dispatching-parallel-agents.md` / `runtime-tripwire.md` was reconciled in `2652ebeb`.

### …but key-presence ALONE is insufficient when the param can re-appear

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

The general principle: a gate keyed on a harness capability the build may not expose is a forward-compat hazard, **and the capability can come back** — so don't pin behavior to a single call's payload shape. Deny only the **present-and-bad** state outright; for the ambiguous absent state, calibrate from observed evidence within a scope that cannot outlive the build it observed.

## Bare-python / console-subprocess Write hooks false-positive on PowerShell's native-command `&` operator

A PreToolUse Write/Edit hook that flags "bare console-subprocess" or "bare-python" spawns by pattern-matching `& <name>` will **false-positive on PowerShell's native-command call operator**. In PowerShell, `& winget`, `& brew`, `& sh -c` are the *call operator* invoking an external command — not a `python -c` re-spawn or a `powershell.exe` re-entry. A hook whose regex treats `&` as a subprocess-spawn sigil denies legitimate `.ps1` authoring, and the executor then bypasses the hook entirely (Bash-heredoc write), defeating it.

The tell that the block is a false positive: the **authoritative tripwire test** (`test_no_bare_python_in_shell_scripts.py` and kin) passes on the same file — it correctly finds zero `python -c` invocations, because there are none. When the hook and its own tripwire test disagree, trust the test and narrow the hook's pattern to exclude PowerShell's `&` call-operator form. Guards match conditions, not containers (§ design-as-offers; `eager-agent-calibration.md`). Source: project-rag.

## Anchor pattern-matcher guards to command-position / real line-shape — never a bare substring anywhere in the payload

The PowerShell false-positive above is one instance of a recurring class: a hook whose matcher pattern-matches a *bare substring* over the whole tool payload fires on incidental occurrences of that substring — argument text, quoted prose, injected boilerplate — not just the real invocation it means to catch. Two more witnesses:

- **`BLOCK-DESTRUCTIVE-GIT-ORPHAN` fires on the trigger phrase inside quoted argument text.** The hook denies any Bash call whose *text* contains a bare forcing-push flag — so a `git commit` / `coordinator-lesson-add` whose **argument** (a lesson body, a commit message) merely *describes* one of those flags in prose gets denied, with nothing actually force-pushing. It also denies the **entire compound command**: bundling an annotated tag-move with a forcing push in one `&&` chain means the *tag-move never runs either*. Candidate hook fix: match forcing forms only in **command position**, not anywhere in the arg string. Operator workaround until then: describe these flags in prose, never as a literal command form; and advance a moving tag in two steps — (1) the annotated tag-move on its own; (2) push the explicit tag refspec with the lease form and an **explicit** value (lease target = the current remote tag-object SHA from a remote tags listing; a bare valueless lease cannot lease a tag — tags have no remote-tracking ref — and fails `stale info`).

- **A prompt-keyed skip-guard collides with unconditional boilerplate that mentions the field name.** The EN-1 double-provision skip-guard matched `'sidecar_path:'` against the whole dispatch prompt — but claude-klabauter `coordinator/bin/fan-out-dispatch.py` UNCONDITIONALLY injects an OOS-block snippet whose prose mentions `sidecar_path:`, so the guard fired on *every* fan-out dispatch and silently skipped provisioning (a fail-OPEN regression). Per-chunk review missed it — a cross-file seam: the guard's author didn't know the boilerplate mentions the token.

**Rule.** Anchor a pattern-keyed guard to the REAL shape of the line it targets — command-position for a shell flag, `newline + field + space + value` for a prompt field — not a bare field-name/flag substring that any incidental mention satisfies. And route live-injected `snippets/*.md` through the same retirement/grep-clean gates as code: they are injected code, not inert doctrine prose, and a token added to one can silently trip a guard keyed elsewhere. Guards match conditions, not containers.

## nag→action: converting detect-and-nag hooks into active-behavior DO hooks

A **detect-and-nag** hook notices that something is wrong and warns the EM about it — blocking until the EM manually corrects the situation, or just emitting a message the EM must then act on. This pattern has two failure modes: (1) the nag blocks session start or tool use, introducing ceremony the EM must perform before working; (2) the nag is advisory at exit 0, so it reaches the user terminal but never the model — silently ignored every time.

The **nag→action conversion** promotes the active behavior itself into a SessionStart DO hook that silently fixes the condition at session open, removing the ceremony entirely. The converted hook acts once, emits at most one line of context when it does something, and is silent on the common (no-op) path. The EM never sees the problem.

**Reference exemplar:** the SessionStart branch-cut hook (strang-04). This hook replaces the earlier daily-branch-block hook, which blocked tool use and demanded the EM run `/workday-start` to cut a branch. The DO hook cuts the branch automatically at session open and injects a single `[coordinator] Branch cut: now on <branch>` line as `additionalContext`. `strang-06` copies this shape for the next batch of conversions.

### 5-step reusable shape

Every nag→action conversion copies this structure:

1. **Source the shared ensure-lib from `lib/`.** Extract the active behavior into a sourced lib function so the same logic is reusable across the SessionStart hook and any other caller (e.g., a `bin/` step script). The lib owns the mechanism; callers own the event-gate and the post-action context.

2. **Gate to `startup` and `clear` events only — never `compact`.** Read `source` from stdin JSON and `exit 0` silently for `compact` or any unknown event. The EM is already on a valid state during compaction; re-running an ensure action would be wrong and disruptive. The event gate is the SessionStart hook's primary safety valve.

3. **Call the ensure function; let it cut, push, or fix.** Pass all required inputs; the function sets output variables (`_CS_ENSURE_RESULT`, etc.) and returns 0 on success or 1 on an unrecoverable error. On non-zero return, emit a one-line stderr note and `exit 0` — a collision or partial failure must never block the session from starting.

4. **Emit a one-line heads-up on action, silent on no-op.** When the function reports it did something (e.g. `FRESH-CUT`), echo one line to stdout so it appears as `additionalContext` in the session. When nothing needed doing, emit nothing. The goal is zero noise on the happy path and one informative line when the hook acted.

5. **Never deny, never block, always `exit 0`.** A SessionStart DO hook must not stop the session. The hook's job is to improve conditions silently, not to gate entry. Any error path — missing lib, git not available, suffix collision — falls through to `exit 0` after logging at most one stderr line.

### Broadening a self-heal detect-arm needs an `already-current → skip` guard, or it breaks idempotency

A DO hook's detect-arm decides *when* the ensure-function should act. Broadening that detect-arm to converge more variants (stale forms, hand-patched hooks) has a failure mode: the broadened matcher over-matches hooks that are **already on the current target form**, so the ensure-function re-mutates a correct body on every session-init — duplicating invocations, churning the file, defeating the no-op-on-happy-path contract.

**Rule.** A broadened detect-then-rewrite must gate on `body already equals the current target → no-op` BEFORE it rewrites. Broadening stale-detection and adding the already-current skip are **two separate obligations** — the first without the second is not idempotent. The self-heal must converge a divergent body toward the target *and* leave an on-target body untouched.

## Exactly-once advisory surfacing — per-session cursor, not a shared flag

A hook that lives on a high-frequency event (`Stop`, `UserPromptSubmit`, `PostToolUse`) and wants to surface a durable, backlog-bearing signal exactly once per occurrence needs an exactly-once mechanism cheap enough to run on every fire. **This is the standing answer**: a per-session byte-offset cursor file, not a shared engine-side "surfaced" flag.

**Worked example:** `coordinator/hooks/scripts/runtime-tripwire-em-check.py`'s `_check_push_failures()`. Shape:

- **Per-session cursor at `.git/coordinator-sessions/<session_id>/push-failures-cursor.txt`** — a byte offset into the append-only signal source (`.git/push-failures.log`), scoped by session id, not shared across sessions.
- **Baseline on first call in a session, no alarm.** The first check just records the current size and returns — the signal source is append-only historic state, so a naive "any content present" predicate would fire on every future session forever. Establishing baseline instead of alarming is what keeps a weeks-old backlog silent.
- **Fires only on growth past the baseline.** A later call compares current size to the stored offset; only genuinely NEW content since the last check produces a signal.
- **Advance the cursor only once the surfaced text has been handed to the emission path — never at read time, and never on the op-read alone.** Reading "there is new content" and writing "this content is now surfaced" are two different facts; collapsing them means an exception or an early return between the read and the actual `stdout` write **burns the record** — surfaced-once means it never surfaces again, so a data-loss failure wearing an exactly-once costume. In a single small function where the read and the eventual emission are only a few lines apart, this gap is negligible; it stops being negligible the moment the read and the emission are separated by real branching logic, multiple exit paths, or a fold into a larger multi-purpose hook — tighten the ordering to strictly *after* the write in that shape, not merely "later in the same function." See `_check_push_failures()`'s own docstring for how it names and accepts this tradeoff at its own (adjacent-statement) scale.
- **Cost ceiling: one `os.path.getsize` stat plus one small cursor-file read on the steady-state (nothing-new) path — no subprocess, no full-file read.** Only the rare firing path seeks to the prior offset and reads the (small) delta. This is what makes the pattern safe to hang off a high-frequency event at all; an unconditional subprocess or full-file scan on every `Stop`/`UserPromptSubmit`/`PostToolUse` would not be.

Being per-session also buys concurrency-safety for free: two EM sessions sharing a working tree each own their own cursor file, so there is no shared mutable state to race, lock, or make atomic. See `docs/wiki/concurrent-em-hazards.md` for the hazard-catalog framing of the same point.
