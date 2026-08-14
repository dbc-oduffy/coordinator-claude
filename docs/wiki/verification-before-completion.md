---
title: Verification before completion
created: 2026-05-06
type: doctrine
related:
  - docs/wiki/delegate-execution.md
  - docs/wiki/dispatching-parallel-agents.md
---

# Verification Before Completion

## Overview

Claiming work is complete without verification is dishonesty, not efficiency.

**Core principle:** Evidence before claims, always.

**Violating the letter of this rule is violating the spirit of this rule.**

## The Iron Law

```
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
```

If you haven't run the verification command in this message, you cannot claim it passes.

## The Gate Function

```
BEFORE claiming any status or expressing satisfaction:

1. IDENTIFY: What command proves this claim?
2. RUN: Execute the FULL command (fresh, complete)
3. READ: Full output, check exit code, count failures
4. VERIFY: Does output confirm the claim?
   - If NO: State actual status with evidence
   - If YES: State claim WITH evidence
5. ONLY THEN: Make the claim

Skip any step = lying, not verifying
```

## Common Failures

| Claim | Requires | Not Sufficient |
|-------|----------|----------------|
| Tests pass | Test command output: 0 failures | Previous run, "should pass" |
| Linter clean | Linter output: 0 errors | Partial check, extrapolation |
| Build succeeds | Build command: exit 0 | Linter passing, logs look good |
| Bug fixed | Test original symptom: passes | Code changed, assumed fixed |
| Regression test works | Red-green cycle verified | Test passes once |
| Agent completed | VCS diff shows changes | Agent reports "success" |
| Requirements met | Line-by-line checklist | Tests passing |

## Red Flags - STOP

- Using "should", "probably", "seems to"
- Expressing satisfaction before verification ("Great!", "Perfect!", "Done!", etc.)
- About to commit/push/PR without verification
- Trusting agent success reports
- Relying on partial verification
- Thinking "just this once"
- Tired and wanting work over
- **ANY wording implying success without having run verification**

## Tripwire phrases (warn-only)

These are the recurring concrete instances of the categorical rules in Red Flags - STOP above. Each phrase, when it appears without adjacent evidence, is a tripwire — not a banned word.

When you catch yourself (or a subagent's reply) using any of these, demand the missing evidence before accepting:

- "Tests pass" — show the output
- "Everything works" — name the verification path
- "Implementation complete" — list exit-criteria with checks against each
- "Probably works" / "Should work" — either it's verified or it isn't
- "Builds clean" — show the build log
- "No errors" — show the run trace

These aren't bans on the words. They're tripwires: when the words appear without adjacent evidence, the claim is unsupported. The discipline is "evidence before assertions, always" — these phrases are common locations where that discipline lapses.

## Rationalization Prevention

| Excuse | Reality |
|--------|---------|
| "Should work now" | RUN the verification |
| "I'm confident" | Confidence ≠ evidence |
| "Just this once" | No exceptions |
| "Linter passed" | Linter ≠ compiler |
| "Agent said success" | Verify independently |
| "I'm tired" | Exhaustion ≠ excuse |
| "Partial check is enough" | Partial proves nothing |
| "Different words so rule doesn't apply" | Spirit over letter |

## Multi-File Executor Verification

Two universal rules that apply after any executor or apply-agent dispatch:

### (a) Diff is ground truth — not the agent's chat summary

Executor and apply-agents consistently under-count their own work in chat (observed repeatedly in distill and architecture-survey runs). After any multi-file executor dispatch:

1. The diff for `<expected-path-glob>` is ground truth, not the agent's completion report.
2. **Empty diff for an agent that claimed work = re-dispatch** with the explicit list of unfinished files. Do not accept "I completed all files" alongside a zero-line diff.
3. For spec-driven dispatches that mandate a canonical phrase or pattern across N files, also run `grep -l "<canonical phrase>" <target-files>`. File count alone is not proof — the canonical content must actually appear.


### (c) Edit tool success is not proof of change

After a sequence of Edit calls — especially before claiming a fix is in or before commit — the diff (`git diff <file>` or `git diff --stat`) is what confirms the bytes actually moved. Edit returns success on no-ops where the new_string already matched.

### (d) Subagents may "fix" things without producing diffs (fifa T1.4)

Subagents conflate "this is correct now" with "I made it correct." Actual diff stats (`git status --short` + `git diff --stat`), not self-narrated counts of intended changes, are what a fix-applied claim rests on. "No-op, target was already correct" is a valid outcome — and an honest one.

### (b) Match verification to the change you made (L274)

Verification must target the actual side effects of YOUR action. Running an unrelated expensive process ("ran the full test suite, all green") as "verification" of a one-line change is cargo-cult.

- Made a code edit? Re-Read the file and grep for the changed symbol.
- Added a pattern across files? `grep -l` the pattern across those files.
- Fixed a specific code path? Exercise that path — don't just run unrelated tests.

"I made the edit" without re-Read is an assertion, not evidence.

| Verification Claim | Must Run | Not Sufficient |
|--------------------|----------|----------------|
| N files updated by executor | `git --no-optional-locks diff --stat` showing N files | Agent chat summary |
| Canonical phrase applied across files | `grep -l "<phrase>" <targets>` | "All files processed" |
| One-line bug fix | Re-Read file + grep for change | Full test suite passing |
| Pattern applied consistently | Targeted grep on changed files | Build success |

### (e) A green test can be bought by WEAKENING production — read the diff for swallowed guards

A passing test is not proof the fix is correct: an executor can make a red test go green by patching the *production* code to swallow the very condition the test should surface — broadening an `except`, wrapping a storage-boundary safety guard in `try/except (AssertionError, ImportError)` and falling back to a raw client, relaxing a validation. The test goes green; the production safety property is gone. This is in-scope by construction (the executor edited its target file), so the scope-conformance check does not catch it — only reading the diff does.

**Rule:** on every executor return, read the **production** diff, not just the test diff, and ask "did the test go green because the fix is correct, or because production was weakened to stop raising?" A broadened `except`, a new fallback around a guard, or a deleted assertion paired with a newly-green test is the tell. Empirical (macos-first-class-test-parity C3b): an executor returned "12 passed" after patching `semantic_lanes.py` to `try/except`-swallow a storage-boundary guard and fall back to a raw chromadb client — to "fix" what was actually a test-isolation bug (the test mocked the whole `core` package but never stubbed `core.source_registry`). Caught by reading the diff. Composes with § (a) Diff is ground truth and test-design-discipline.md §49 (broad `except` swallows schema-drift failures silently).

## An Executor's "Green" Is Not a Gate Signal — Captured Output Is

An executor's self-reported test status is not evidence anything passes. Diff-is-ground-truth (§ (a)) governs *what changed*; this governs *what passes* — and the trustworthy answer is captured test output plus git log, never the executor's narration.

**Rule.** Never advance a gate on an executor's (or background workflow's) self-reported test-green. Read the output it captured; where that is missing or contradicts the diff, ask for it or re-run the *targeted* tests yourself.

**A re-run is not automatically a suite run.** Distrusting a self-report earns you the evidence, not the breadth: an executor's green is checked at the breadth of what it changed. A full-suite re-run is a Tier-U action, reserved to a cadence gate — clean-slate, workstream-complete, merge — and it needs a live PM grant like any other (`tier-u-grant-cli check`). A completion or clean-slate *claim* earns it; mid-work iteration and per-executor-return verification do not, and an EM that re-runs the suite after every executor return has multiplied one wave into many machine-wide events. Match verification to the change (§ (b)); a commit is not itself a verification gate.

Three recurring shapes:

- **Self-report is unreliable even when confident.** A background `/execute-plan` executor self-reported the coordinator-uninstall acceptance suite green when it was 3/7 red; the EM re-running it caught the gap and root-caused 4 real bugs. (doe-L96 — universal.)
- **Flaky / shared-resource suites need multiple cold runs, not one.** On a contention-sensitive suite, a single green run is not proof — re-run the full suite yourself several times cold, as a Tier-U action gated on a live session grant (→ `test-design-discipline.md` § Posture: Proportional Test-Running), never assumed from the conversation having discussed one. Two executors each reported 51/51 green on a flaky contract suite; the EM's cold runs showed 4-red each time, on *different* tests (the contention tell). Three cold full-suite runs, held under grant, caught both over-claims. A suite whose reds move between runs is a shared-resource contention signal, not noise to dismiss. (doe-L19.)
- **The clean-slate gate is the whole suite, not the changed cluster.** Per-slice green is necessary but not sufficient: a change that passes its own tests can still break a *different* corpus-wide contract lint. A currency-probe fix passed its own 5 tests but violated `test-claude-home-contract`'s `CLAUDE_HOME` lint — caught only by the whole-suite pass after per-cluster green. Targeted (Tier-T) green on the touched cluster is never itself a clean-slate declaration — the whole-suite pass is the gate, and running it is a Tier-U action reserved to the top-level EM (→ `test-design-discipline.md` § Posture: Proportional Test-Running). An agent that isn't the EM declares its own Tier-T green plainly and states that suite-level confirmation is pending the EM's gate run — it does not fire the suite itself to manufacture that confirmation. (doe-L72.)

The tell that this section is being read too widely: a generic verify-before-you-commit reflex reaching for the suite, then citing this page for it. That reflex is what this page replaces with captured evidence — it is not what the page licenses.

### A dispatched agent's green is narrower than a directory-shaped brief by construction — covering the brief's breadth is the EM's job, not the agent's to guarantee

A dispatched agent's test invocations are confined to file-and-node-id precision — it cannot accept a bare directory as a test-command argument, deliberately, so that a fan-out wave of agents cannot each re-run a wide suite concurrently. When an EM's dispatch brief names verification breadth in directory terms ("run `tests/foo/`"), the confinement means the agent's actual run is necessarily narrower than the breadth the brief asked for.

**This is not the agent misreporting.** An agent that falls back to the touched files' node ids and reports "N passed" is telling the truth — it ran everything it was permitted to run. The gap is that the EM reads that green against the breadth *it specified*, and the two can silently differ by an order of magnitude: one incident saw an agent's confined run cover 37 tests where the briefed directory scope covered 434.

**Rule.** Do not read a dispatched agent's narrower green as having covered the breadth the brief named. The honest move is usually to write the brief at the breadth the agent can actually run — file and node-id precision — so the two never diverge; where the wider breadth genuinely must be verified, that is EM-side work at a cadence gate, under grant, not a re-run per return. Never loosen the confinement: it exists on purpose and is not the thing to relax. This is the dispatch-breadth-specific instance of § "An Executor's 'Green' Is Not a Gate Signal" immediately above — that section governs an executor's self-reported green in general; this one names the specific, easy-to-miss case where the *reason* the green is narrower is a structural guard the agent had no way around, not carelessness on either side.


## Presence-Check Verifiers Are Blind to Guard-Placement Bugs — Verify Correctness, Not Just Presence

A companion verifier that only checks a guard's **presence** (marker within N lines of a resolve-site) reports OK on guards that are functionally dead because they were placed wrong. This is the placement-side twin of § "A Discriminator Guard Is Dead If It Never Matches the Value the Producer Emits" (dead *condition*) and § "A documented or override-gated guardrail is not an implemented one" (dead *registration*): here the guard is present, registered, and matches — but sits on the wrong variable, so it rejects its own trusted input.

**Failure shape:** a mechanical auto-fix stamped a traversal guard (`case "$VAR" in *"/.."*) _cc_trusted=0`) unconditionally onto a variable whose PRIMARY value legitimately contains `/../` — a `BASH_SOURCE`-relative sibling hop like `${_self_dir}/../bin/x.js`. The guard then always rejects its own trusted path. The safe form confines the guard to the fallback branch (`if [[ ! -f "$VAR" ]]; then VAR=fallback; <guard>; fi`). The presence-only verifier reported "delivery complete, 72 sites guarded" — hiding 6 broken lifecycle-stamping helpers.

**Rule.** A presence check ("marker appears near the resolve-site") is not a correctness check. Two nets close this: (1) a **functional test** that exercises the guarded entry points and asserts they never emit the guard-rejection string on legitimate input; (2) a **placement lint** flagging a `/../`-primary variable guarded unconditionally (excluding `$(cd … && pwd)` runtime-normalized paths). Verify the guard *does its job on real input*, not that its text is present.

## Format Validation (fifa T1.3)

For batch outputs with a known schema, existence checks are not enough. Prefer a sweep confirming each file contains the canonical block before reporting completion.

**Why this is distinct from existence checks:** A file can exist and still be schema-nonconformant. In a 64-nation pipeline, 3 nations produced prose-only syntheses (no JSON block) and 2 had non-standard JSON root keys — 5/64 files would have silently passed an existence check.

**Sweep pattern:**
```bash
# Confirm JSON block present
grep -l '```json' outputs/*.md

# Confirm expected root key (jq)
for f in outputs/*.json; do jq -e '.expected_root_key' "$f" > /dev/null || echo "FAIL: $f"; done
```

**Failure modes to check explicitly:**
- Prose-only output when structured format was required (no code fence / no JSON block)
- Non-standard root keys (e.g. `data` instead of `results`, `output` instead of expected key)
- Truncated output (file exists but JSON is incomplete / malformed)

Run this sweep before reporting batch completion — not after.

## Key Patterns

**Tests:**
```
✅ [Run test command] [See: 34/34 pass] "All tests pass"
❌ "Should pass now" / "Looks correct"
```

**Regression tests (TDD Red-Green):**
```
✅ Write → Run (pass) → Revert fix → Run (MUST FAIL) → Restore → Run (pass)
❌ "I've written a regression test" (without red-green verification)
```

**Build:**
```
✅ [Run build] [See: exit 0] "Build passes"
❌ "Linter passed" (linter doesn't check compilation)
```

**Requirements:**
```
✅ Re-read plan → Create checklist → Verify each → Report gaps or completion
❌ "Tests pass, phase complete"
```

**Agent delegation:**
```
✅ Agent reports success → Check VCS diff → Verify changes → Report actual state
❌ Trust agent report
```

## Why This Matters

From 24 failure memories:
- your human partner said "I don't believe you" - trust broken
- Undefined functions shipped - would crash
- Missing requirements shipped - incomplete features
- Time wasted on false completion → redirect → rework
- Violates: "Honesty is a core value. If you lie, you'll be replaced."

## When To Apply

**ALWAYS before:**
- ANY variation of success/completion claims
- ANY expression of satisfaction
- ANY positive statement about work state
- Committing, PR creation, task completion
- Moving to next task
- Delegating to agents

**Rule applies to:**
- Exact phrases
- Paraphrases and synonyms
- Implications of success
- ANY communication suggesting completion/correctness

## Scope-Conformance Check After Executor Returns (example-repo T1.5)

Before staging any executor output, the changed-paths diff is what enumerates scope: confirm each path is within the dispatch's declared scope, then stash or revert any out-of-scope edits.

Out-of-scope edits are common failure modes: test file deletions, unrelated refactors, autonomous commits the executor made despite instructions. The check is mechanical and must happen before the coordinator reads the diff semantically.

See `docs/wiki/delegate-execution.md` → "Scope-Conformance Check" for the dispatch-prompt clause that enforces this on the executor side.

## Definition of Done (acceptance gate before declaring completion)

For any plan with declared acceptance criteria, "done" means more than green tests. Before claiming completion or moving to merge:

- [ ] Every **acceptance criterion** is satisfied (or explicitly waived in writing with PM acknowledgement).
- [ ] Tests/checks ran and the output is captured (link or excerpt — not "trust me").
- [ ] If user-visible: **manual demo path verified** — you actually walked the steps, not just inferred from green tests.
- [ ] Technical reviewer has run if scope mode warrants it (production-patch and feature: yes; prototype/spike: optional). The VP-of-Product lens at merge (refactor-vs-patch, shape, dumb questions) is the PM's call — not an auto-dispatched the VP-Product Reviewer gate.
- [ ] **Known limitations** are documented — what *isn't* covered, what edge cases were deferred.
- [ ] **Rollback or mitigation** is named — if this turns out wrong in production, what's the recovery move?
- [ ] **Ship verdict** is staged for the PM (see `coordinator:merging-to-main`).

This is the bridge between engineering output and PM confidence. "The agent says it's done" is not the gate; this is.

**"Smoke-proven launch-ready" overstates coverage when the smoke was killed before reaching most phases.** A predecessor handoff that says "PROVEN end-to-end via a real smoke (then killed)" may mean only the first of 5+ phases actually ran. Steps 2c, 2d, Phase 5 — never executed. The "launch-ready" framing makes recovery cost feel small; in reality the subsequent run crashes on previously-untested phases (lock self-deadlock, argparse arg-shape bug, chunker source_type=unknown). Rule: "proven" means at least one end-to-end run completed all phases, even at smaller scale — not "the first phase started." Either run a tiny full-pipeline smoke or qualify the claim as "Step 2a proven; later phases unverified."

## AC Gate Degradation and Probe Anchoring

### Half-verified AC gates (L338)

When an acceptance criterion has two halves — for example, "static analysis passes" AND "runtime initialization succeeds" — a pass on the first half does NOT constitute a pass on the gate. Document the asymmetry explicitly in the plan or completion report:

- Name which direction each half covers.
- Don't mark the AC "fully passed" until both halves are verified independently.
- Static analysis tools (linters, type-checkers, build-time guards) do not verify runtime behavior. A runtime initialization step (process boot, IPC handshake, HTTP ping) is required for the runtime half.

**Failure shape:** an executor reports "AC passed" after running static analysis only. The runtime half was never exercised. The bug ships.

**Counter:** whenever an AC mixes static and runtime concerns, split it into two checkboxes in the plan. Both must be checked before the gate closes.

### Health probe anchoring (L495)

Health probes must anchor to the **canonical artifact**, never to a convenience sidecar that may be absent after an in-place migration.

- A DB schema version probe reads the canonical schema table or a version column the schema itself declares — not a sidecar `version.txt` that may have been left behind from a prior layout.
- A manifest probe reads the manifest at its canonical install path — not a copy that the installer may have moved without updating the sidecar.

**Failure shape:** an in-place migration moves the canonical artifact, leaves the sidecar behind, and the probe keeps returning green against the stale sidecar — health looks good while the runtime is broken.

**Rule:** when adding a health probe, grep for every location that writes the artifact being probed. If there's a sidecar, verify the migration path keeps the sidecar in sync — or remove the sidecar probe and anchor to the canonical path directly.

## Runtime Readiness vs. Green Tests

> **Provenance:** consolidated 2026-05-27 from learn-lessons Bucket B. Green tests prove logic is *correct on disk*; they do not prove the *running system serves it* or that the *user-visible symptom is gone*. This is the most expensive sub-pattern in the bucket — fixes that pass every test and meet every AC while the live system stays broken.

### A feature whose authorized path is unreachable is not done — "fails closed / inert" ≠ shipped

Green tests can pass on every *gate* while the feature *does nothing*, because the wiring that makes an authorized action reachable was carved out and filed to the improvement queue as a "follow-up." A gate that fails closed is *safe*, not *done* — fail-closed-but-inert is the runtime-readiness gap wearing a security hat.

A concrete case: an access-control feature shipped its read-path gates with 120 green tests; the roadmap tracker read `shipped`. But the scoping function excluded every protected band unconditionally, no verified principal was ever threaded (so no grant was ever bound), and the tier resolver defaulted everything to `'public'`. The three load-bearing enablers were filed to the improvement queue tagged *"fails closed, not a leak, PM scope call"* — a defer-via-rationale that reframed feature-completion as optional polish. The feature was inert; the roadmap said done.

**Rule.** Load-bearing enablement — the wiring without which the feature's authorized path is unreachable — is a **roadmap deliverable**, never an improvement-queue entry. If it genuinely cannot ship in the slice (e.g. it depends on an undecided contract), file it as the next gated roadmap stub with `blocked_by`/`blocks` edges, not as a queue item that ages out. The improvement queue is the opportunistic "someday" bucket; putting completion there makes a green-tested feature read as shipped while it does nothing. **Tell:** "fails closed / not a leak / PM scope call" attached to something the feature needs to actually function; "green tests + nothing works end-to-end." Enforced at `/workstream-complete`'s `enablement-vs-opportunistic-deferral` judgment point; the diff-time twin is the `code-reviewer`'s Deferred-items lens.

### Don't kill the sibling-repo daemon you depend on without a verified relaunch path

A sibling repo's running process (MCP daemon, indexer, watcher) may be the only live instance your session depends on. Before stopping/restarting/killing it, **verify the relaunch path resolves end-to-end** — the launch command exists, its config points at a valid target, and it comes back healthy — *before* taking the running one down. Killing the only running daemon you depend on without a verified relaunch path strands your own session and any concurrent one. The cross-process analogue of "land regression-net tests before the refactor that depends on them": prove the recovery path before destroying working state.

### A probe or tool that spawns a sibling's daemon directly inherits none of its lifecycle-manager safety

**A probe/test/tool that spawns a sibling's daemon DIRECTLY (subprocess, not via the sibling's lifecycle manager) inherits NONE of that manager's safety machinery — park-state, crash-loop breakers, resource ceilings all live in the manager it bypassed.**

A dogfood/smoke runner invoked an add-on host's runner directly, which child-spawned the daemon outside its own supervised launch path — so on a host actively being fixed for a resource-leak freeze it could re-spawn a multi-GB daemon with no brake and no starts-log entry.

**Rule:** when you spawn another repo's long-lived process directly, you've opted out of its lifecycle safety — either route through its manager, or replicate the manager's guard signals (park-state sentinel path + cooldown — confirm the canonical signal with the owner, as park-state may have no positive on-disk sentinel). An explicit parked-state env flag (or equivalent) checked at the spawn site is the interim guard when routing through the manager is not possible. Sibling to the direct-spawn footgun note in cross-repo contract discipline generally, and to detect-then-fail-loud.

**Park-state sentinel mirroring as interim guard.** When a direct-spawn is unavoidable (the sibling's lifecycle manager is not callable from the probe), the minimum guard set is: (a) mirror the sibling's crash-loop sentinel path + cooldown, (b) check an explicit park-state env flag (or equivalent) at the spawn site, and (c) confirm with the sibling owner what the canonical park signal is — park-state may have no positive on-disk sentinel, making it easy to miss. This is an interim shape; route through the manager as soon as the interface is available.

### A disk fix is not live in a long-running daemon until it restarts — and the restart path may itself be broken

A persistent daemon holds imported modules in memory and serves the code loaded at *its* boot. A disk edit + green pytest proves the logic is correct, not that the running process serves it.

- **After fixing code a long-running daemon serves, verify through the LIVE interface** (MCP call / HTTP endpoint), not just pytest.
- **Confirm the restart primitive actually restarted** — re-query after. A `session-restart` can exit 0 and be a silent no-op (marker mechanism never reaches the HTTP daemon); the stop script can then crash on a different interpreter. "exit 0" from a restart command is not evidence the new code is live.
- Green unit tests are **necessary, not sufficient**, for runtime-readiness.

### End-to-end verify can uncover a different-mechanism bug with the same user symptom

Green tests + correct ACs ≠ user-visible problem resolved. A workstream can address every *named* bug, pass the Staff Engineer review, ship executors, and still leave the *symptom* alive via a path the substrate read never reached.

- **When a workstream targets a user symptom (not just a code defect), end-to-end verify by running the actual user action and observing the actual user-visible state** — non-skippable even when tests pass and ACs are met. (Observed: `session-restart` worked perfectly, then an addon hookspec re-spawned a sister daemon on the wrong interpreter within seconds — same symptom, new mechanism.)
- **If verify uncovers a new mechanism producing the same symptom, carve a spinoff** — do not expand scope mid-workstream.

### Editable-install import env: the finder is a frozen snapshot

setuptools editable installs (`pip install -e`) bake a top-level-package MAPPING (the `__editable__*_finder.py` + `top_level.txt`) at install time. Adding a package to `pyproject.toml` later does **not** refresh it — the new package is invisible until reinstall.

- **When an editable-installed package fails to import despite source existing AND being declared, re-run `pip install -e <root>` before deeper debugging.** Install scripts that only `pip install -r requirements.txt` must ALSO re-run the editable install, or new packages silently break on consumer boot. (See also the managed-refresh venv-state leg in global CLAUDE.md § Plugin live-install propagation.)
- **Reproducing a daemon's editable-import env requires `site.addsitedir()` or the venv's OWN python — NEVER bare interpreter + `PYTHONPATH`.** `PYTHONPATH` adds the dir to `sys.path` but does not process the `__editable__*.pth`/finder, so editable packages stay unresolvable. dist-info checks (`entry_points()`) ARE PYTHONPATH-visible; module-resolution checks (`find_spec` / `import`) are NOT — a probe using PYTHONPATH passes the dist-info half and false-fails the import half.
- **To prove "is X loaded in the daemon's env," repro from a NEUTRAL cwd with the daemon's effective interpreter.** Running from the package source tree imports it via cwd and fabricates a pass. The check must (a) use the daemon's effective interpreter (argv-injected site-packages), AND (b) run from a cwd that is NOT the package source tree (`cd /c/` then import). Trust a doctor's env-scoped FAIL over a hand-repro until the hand-repro controls for both.
- **A stale live install of an agent definition can carry a dead MCP server in its allowlist, silently breaking ALL of that subagent's MCP tool resolution.** When a subagent can't see MCP tools its source frontmatter grants, FIRST diff the live install against source for dead/retired `mcp__<server>__*` entries — don't reach for platform/dispatch-mode hypotheses until the live copy is confirmed in-sync. A refresh-live-install script clears the dead ref + stale plugin cache. This is source↔install drift; diagnose against the LIVE copy, not source.

### A documented or override-gated guardrail is not an implemented one

- **Confirm script + `hooks.json` registration + trigger coverage before trusting that a guardrail exists** — a guardrail named in doctrine can be unregistered or never-wired.
- **Safety-gate failures behind override flags can be latent-broken since authoring.** Never reach for `--skip-X` / `--force` before reading the probe code — an override flag reached-for reflexively is a smoke-signal that the gate may be broken, not that the work is genuinely exempt.

### Windows launcher-stub re-exec is not a duplicate-spawn bug

When a daemon appears to spawn a "duplicate" copy on a different interpreter at exactly boot time, BEFORE searching for application code that spawns subprocesses: dump parent/child argv + CreationDate via CIM. **Identical CreationDate + parent-child link + same argv + different `ExecutablePath` = a uv launcher-stub re-exec** (spawn-and-wait on Windows, not POSIX exec-replace), not a spawn bug. Diagnostic: `Get-FileHash` the venv `python.exe`/`pythonw.exe` (identical hash + ~46 KB = uv stub); check `pyvenv.cfg::home` for the base interpreter. The fix surface is the daemon spawn site, not the suspected protocol.

## A Discriminator Guard Is Dead If It Never Matches the Value the Producer Emits

**A status/enum-discriminator guard that gates on a value the producer never actually emits is dead code — it silently passes everything it was meant to catch.** A guard like `if status == "DEGRADED": block` is only live if the producer ever emits the literal string `"DEGRADED"`; if the producer emits `"degraded"`, `"warn"`, or a structured `{level: 2}` instead, the equality never fires and the guard is a no-op that *looks* protective. The failure is invisible: the guard reads correct, tests that mock the expected-but-wrong value pass, and the gate ships open.

**Rule:** before trusting a value-discriminator guard, verify the emitted value at the producer — grep the producer for the literal it actually writes, or assert it with a wire-path test that flows a real producer output through the guard. Prefer gating on a **structural signal** (field presence, type, a typed sentinel) over a brittle string-equality on an enum the producer owns independently. This is the verification-side twin of "gate on discriminating signal" (which governs *what* to gate on); here the discipline is *confirm the guard's condition can ever be true* before declaring the guard done.

## Model-Identity / Version SHA Guards Must Be Prefix-Aware, Not Exact-Equality

**A SHA / model-identity guard comparing a full hash with `==` false-fails on every legitimate abbreviation — make identity guards prefix-aware, and verify the index is queryable before trusting that the harness merely runs.** Git SHAs, model fingerprints, and content hashes are routinely surfaced abbreviated (7–12 chars) by one tool and full-length by another; an exact-equality identity check rejects the abbreviated form even when it is the same object. Use prefix containment (`full.startswith(short)` / `short` is a prefix of `full`) for identity comparison.

Separately: a harness that *runs* is not a harness that *answers*. Before trusting an eval/index-backed guard, confirm the index is actually queryable (a real query returns real rows) — a runnable-but-empty index passes "the harness executes" while silently failing "the harness has data."

## Reproduce a Static Root-Cause Empirically Before It Gates a Flip / Ship / Cross-Repo Decision

**A root-cause derived by reading code or reasoning statically is a hypothesis — reproduce it empirically before it drives an irreversible decision (a config flip, a ship, a cross-repo memo).** Static analysis tells you what *should* happen; it does not prove what *does*. When a diagnosed cause is about to gate a decision with reach beyond the current edit — flipping a default, shipping a fix, sending a sibling EM a memo that asserts the cause — run the reproduction first: trigger the failure, observe it, then observe the fix removing it (red→green on the actual mechanism, not a proxy). This is the decision-gating twin of the fix-code empirical-audit rule (empirical audit before fix code) and the P0/P1 verification gate: read-confirms-plausible, but only a reproduction confirms-real, and the cost of a confidently-wrong static cause scales with the blast radius of the decision it gates.

## The Bottom Line

## verify executor output on disk even when report claims already-present

Executor self-reports are unreliable even when the report says "no work needed / already present" — an executor that detects existing content may misidentify it or may have stale context. `git diff --stat` and `ls -la <expected-path>` are the authoritative checks, regardless of the executor's narrative.

## blocked classification means indeterminate — oracle never ran

A `blocked` classification from a fail-loud build/verify gate means the oracle never ran — not that the build failed. `blocked` is indeterminate; `failed` is a verdict. Also: UBT "up to date" in ~1s after an edit means the file's mtime was not changed — `touch` the file to force real recompile. Apply: before treating a `blocked` classification as a failure, check whether the oracle actually executed; re-run with forced inputs if needed.

## Green-but-SKIPPED is not verified — run the integration the skip masks

Green-but-SKIPPED test runs are not verified — they confirm the skip condition fired, not that the implementation works. Run the integration the skip masks, especially on the producer's own platform. Apply: before declaring a workstream done, grep for `pytest.mark.skipif` and `@pytest.mark.skip` in the test suite; run any that were skipped due to platform or environment conditions in the actual target environment.

**No shortcuts for verification.**

Run the command. Read the output. THEN claim the result.

This is non-negotiable.

## Parser / Normalizer Fixes Surface Hidden Violations — Budget for the Unmasking

### Fixing a failing-closed parser exposes previously-masked downstream violations

When a parser, normalizer, or guard was failing-closed (returning null / error / skip), downstream validators never ran against that parser's output. The moment the parser is fixed, the downstream checks execute for the first time — and they will surface real violations that the broken parser was silently hiding.

**Rule:** when you fix a parser or normalizer that was failing-closed, scope the fix to include surfacing AND fixing the newly-unmasked violations downstream. Do not declare done at "the false-positive is gone." Budget for a second wave.

**Empirical basis:** `parseFrontmatter` returned null for any file leading with an HTML comment, so schema fields were never checked. Once the parser was taught to skip the leading comment, 4 real violations (missing `category`, over-length `summary`) that had been silently masked appeared. Separately, a broken `normalize()` (BSD-sed crash) produced a false MISMATCH verdict that evaporated once normalize worked.

### A null-frontmatter parse is a record-existence signal, not a lint signal

A shared frontmatter parser that returns null on certain valid inputs doesn't just trigger a lint nag — it silently deletes those records from every index that consumes the parser. `query-records` skips any record whose frontmatter parses to null, making the record invisible to `/pickup`, `/workday-start`, and any downstream consumer.

**Rule:** fix null-return bugs in a SHARED frontmatter parser (not just the linter that calls it). A too-strict parser is a silent record-deletion bug for the full index. Fix the parser once at the shared-lib level, not per-consumer.

**Empirical basis:** the line-1-frontmatter requirement false-flagged 8 seeded handoffs that carry a legitimate leading `<!-- seed comment -->`. The visible symptom was a lint nag — the silent, worse consequence was that `query-records` dropped these handoffs from the index entirely, making them invisible to `/pickup` and `/workday-start`.

## Phase 1.5 Bug-Sweep Verify: NEUTRALIZED-IN-CONTEXT Is a Third Verdict

When Phase 1.5 of a bug-sweep verifies that a finding is "still present" by matching the buggy code shape, that is not sufficient — it must also read the surrounding defensive context to determine whether the bug's practical impact is already neutralized.

**Third verdict:** beyond `still-present` and `already-fixed`, add `NEUTRALIZED-IN-CONTEXT` for bugs whose code shape is present but whose practical impact is nullified by upstream OS gates, `|| echo 0` fallbacks, `kill -0 ... 2>/dev/null` guards, or equivalent defensive patterns.

**Rule:** when verifying a finding in Phase 1.5, read ±15 lines around the flagged site and ask "does the defensive context already neutralize the practical impact, or is the bug load-bearing?" A "still-present" verdict that ignores a `|| echo 0` fallback is an over-report.

**Empirical basis:** 4 C4 P1s ("Linux data-loss-class") were confirmed still-present by the Phase 1.5 verifier, all 4 routed as backlog/cross-repo memos. A pre-send re-verify found 1 NEUTRALIZED (PID guards already shipped), 1 DEGRADES-not-crashes (`date -r` with `|| echo 0` fallback bypasses cooldowns on macOS but doesn't crash), 1 PARTIAL (powershell.exe OS-gated everywhere except one 41-line script), 1 REAL.

## Session-Limit Reply ≠ Task Failure — Check Disk Before Re-Dispatching

When Anthropic session quota hits mid-fan-out, dispatched agents return the literal string `session limit · resets <time>` on the reply channel. This is NOT evidence the agent's task failed. Agents that had already invoked `Write` BEFORE the limit fired leave their outputs on disk.

**Rule:** on any `session limit` reply string, `ls` the expected output path before re-dispatching. If the file exists at expected shape/size, the agent succeeded — the reply channel was just truncated. Re-dispatching over a successful disk output wastes a quota cycle and may corrupt valid work.

**Empirical basis:** during a `/distill` fan-out, 4 of 13 agents landed disk outputs before quota cut the reply channel. Re-dispatching from the reply string alone would have corrupted 4 of the 13 results. Disk is authoritative; the reply channel can lie under quota pressure.

## Harness-Managed / Live Files: Re-Verify Post-Executor-Return, Not From Executor's Own Check

When an executor edits a file that a live process (the Claude Code harness, a daemon, a watcher) also writes, the executor's in-run assertion on that file is unreliable — the live process may mutate the file after the executor's check passes.

**Rule:** when an executor edits a harness-managed or live-written file, re-verify the invariant from disk EM-side AFTER the executor returns, and again right before committing. A passing in-executor assertion does not bind once a concurrent writer is in play.

**Empirical basis:** portability C5 executor reported "AC8-GREEN, both marketplaces moved to local." In reality only one marketplace landed in local; the other was deleted from `settings.json` without landing in local, and the harness then re-added it — so the executor's transient green check passed but the live file changed under it. The over-report wasn't hallucination; it was a true-at-the-instant check on a file a concurrent writer mutates.

## Verification Must Use an Independent Oracle — Not the Fix's Own Assumption

A verification step that reuses the same flawed assumption the fix was built on cannot disconfirm the fix — it ratifies the premise rather than testing the outcome. If the fix assumed "field X is always populated" and the verification re-reads field X the same way, both share the blind spot.

**Rule:** the verification oracle must be independent of the fix's reasoning — a different read path, a different tool, a measured side-effect, or a real reproduction. When you cannot construct an independent oracle, say so explicitly and treat the verification as provisional. Composes with the P0/P1 verification gate (read the cited code, don't trust the paraphrase) and the general rule that two reads sharing one channel are not two independent reads.

## A Nullable-Input Gate Self-Skips in Production Until a Caller Supplies the Input

A gate guarded on an optional/nullable argument (`if payload is not None: validate(payload)`) silently self-skips on every production call that doesn't supply the argument — and unit tests that always pass the argument never catch it. The gate reads protective; in production it is a no-op until some future caller happens to populate the input.

**Rule:** when a gate is conditional on an optional input, test the **end-to-end CLI / production invocation path** (which may pass nothing), not just the gate function with the argument supplied. And **grep every caller** of the gated entry point to confirm at least one production path actually populates the input — if none does, the gate has never fired. Composes with § "A Discriminator Guard Is Dead If It Never Matches the Value the Producer Emits" and the verification-side rule that you must confirm a guard's condition can ever be true before declaring the guard done.

## "Out of Frame" / "Concurrent-Session Contamination" Is Not a Disposition

Dismissing a test failure as "out of frame," "noise," or "another session's contamination" is an attribution claim, not a disposition — and it is frequently wrong (per-cluster triage repeatedly finds ~1/3 of "test rot" reds are real source bugs, see test-design-discipline.md §71b). A red is signal until proven otherwise.

**Rule:** never close a failing test by labelling it cross-session noise. Read the failure message, name the workstream owner the failure belongs to, and write a finding / cross-repo memo / backlog entry that hands it to that owner. The only honest closures are "fixed," "attributed to owner X with a written handoff," or "reproduced-as-pre-existing against a named commit." This is the executor-output twin of the general "do not infer from absence" rule — a failure you can't explain is unknown state, not clean state.

## Multi-Consumer Failure Reports May Share One Root Cause — Trust the Supervisor Giveup Sentinel's Exit Code Over Its Stderr-Tail

When multiple consumers report what look like different failure modes from the same underlying service, treat them as potentially one root cause before scoping separate fixes. The giveup sentinel's **exit code** is the deterministic mapping; `last_child_stderr_tail` is contextual and can mislead when crash windows overlap.

**Why:** a supervisor giveup sentinel preserves the LAST process's stderr tail — which may be from a longer-lived process that succeeded further into boot than the crashing processes did. The exit code (e.g. `79 = HostProfileUnknownError`) is authoritative; the stderr tail is evidence from whichever process happened to run longest, not necessarily the one that crashed the current window.

**How to apply:** when triaging supervisor crashloops, read the `timestamps:` array AND the exit code from `supervisor.log` FIRST. Only consult `last_child_stderr_tail` after correlating timestamps — if the tail's log lines postdate the deterministic crash time, it's evidence from a different process. Pattern recurs whenever a supervisor batches multiple spawns into one giveup sentinel.

**Empirical basis:** two peer sessions reported a daemon crashloop at spawn (exit code X) and a daemon dying on first query (socket closed), respectively, and scoped them as separate failure modes. A diagnostic spike + smoke test showed the same single root cause — all spawns in the actual crashloop window hit the same startup error before the server's boot routine was even entered; the "last stderr tail" evidence field pointed at an earlier, longer-lived, unrelated run.

## Handoff Quantitative Trend Claims Need Git-Log Verification Before Designing Fixes

A handoff body that names a numerical trend ("drift +2.4 errors/day for 13 days", "stale +N/week", "memory grew N MB") can have correct numbers and wrong causes. The wrong cause leads to wrong fixes. **Run `git log --since=<window> -- <file>` against the cited substrate as Step 1 of pickup verification**, before authoring any plan.

**Rule:** if the commit count doesn't match the trend shape (e.g. one commit explains the entire delta), redo the framing before designing remediation. The same discipline applies to any claim of the form "errors per day", "stale per week", "metric grew N units" — all need git/log-level grounding before scoping the fix.

**Empirical basis:** a handoff claimed "+2.4 errors/day for 13 days" against a type-checker baseline count. `git log` against the cited baseline file revealed exactly ONE commit in that window — a platform re-anchor (one OS to another). The net delta was re-platform, not drift. A burn-rate fix schedule would have been built against a non-existent regression.

## New Helper / Capability Must Be Wired Into the Production Code Path — Not Just Defined and Unit-Tested

When an executor adds a new non-test function or helper, verify it is **called from the production code path**, not only from the test file. Implemented-but-unwired code passes its own tests while contributing nothing at runtime.

**Rule:** on executor return, for every new non-test function/capability, grep that it is invoked from the production caller (not only from the test file). A definition + a green unit test is necessary but not sufficient — "tested" ≠ "wired". Especially for header-inline helpers defined AFTER their intended caller (forward-declaration ordering means the wiring is a separate, easily-omitted edit).

**Empirical basis:** an executor defined a new helper function and wrote a passing unit test for it, but never wired it into the production synthesis path — so on real inputs the new logic would never run. The executor optimized for "my AC test passes" against the helper directly, bypassing the integration the feature needed. The EM caught it by asking "is this new function reachable from the production caller?" and grepping for the call site.

### The doc-edit twin — a chunk that describes wiring must edit the file that implements it, or it ships fiction

The same unwired-claim failure has a documentation shape: a doc-edit chunk that *describes* an invocation surface, mode, or route must edit the file that actually implements it — or the doc asserts behavior that does not exist.

**Rule.** When a chunk's deliverable is a doc that references behavior in a sibling file, either include that sibling in the chunk's write-scope, or verify it *already* implements the claim before writing the doc. A doc asserting "wiring exists elsewhere" is fiction if elsewhere was never touched — and the scope-conformance check won't catch it, because the doc edit is in-scope by construction; only reading the sibling file (or grepping for the described surface) does.

**Empirical basis:** a pipeline doc-edit documented a mode "routed via" a driver file, but never edited that driver file, so the invocation surface didn't exist — an acceptance criterion was silently unmet until code review caught it.

## EM-Verify of Delegated Stateful Code Must Check Accumulator Scope/Lifetime Across Units

When an executor delivers stateful code (a registry, an accumulator, a cache) on a host where the EM cannot compile/run it, unit tests passing is necessary-not-sufficient — cross-unit collisions are invisible to per-unit tests. A registry whose lifetime is per-call when it should be per-function (or per-process when it should be per-request) passes every isolated unit test and collides only when two units run in the same scope.

**Rule:** on every executor return of stateful code, read the accumulator's *scope and lifetime* across units — is the registry instantiated per-call or shared? Does state from unit A leak into unit B? Unit tests exercise one unit at a time and structurally cannot surface a cross-unit scope bug; the EM must trace the lifetime by hand when the host can't run the integration. Composes with `docs/wiki/dispatching-parallel-agents.md` § Executor commit-fidelity and ground-truth verification and test-design-discipline.md §62 (guard the destructive primitive on a shared singleton).

## A Mechanical Fix With a Negative Net Committed-Test Delta Is a Design Conflict, Not a Stubborn Bug

Two separately-landed doctrines can collide inside a single file, and the shim that bridges them can *itself* be the violation one of them forbids. The originating case: a "no-implicit-cwd" gate and a "de-bash-to-in-process port" doctrine met in one module — and the `os.chdir` threaded in to make the ported code run was precisely the implicit-cwd the first gate exists to reject. The "mechanical" fix satisfied gate A but **broke three committed contract tests belonging to doctrine B and inverted B's direction.** Net committed-test delta: negative — more green turned red than red turned green.

**Rule:** a fix whose net *committed*-test delta is negative is evidence of a **design conflict between two landed doctrines**, not a bug to be ground down with a bigger hammer. The signal is diagnostic, not incidental: committed tests encode a peer's ratified intent, so breaking more of them than you fix means your fix is fighting a decision, not a defect.

**When the signal fires:**
1. **Revert the fix unlanded** — do not commit a change that reds committed tests to green a gate.
2. **Trace to the root conflict** — name the two doctrines colliding and the exact bridging construct that is the violation. The principled fix usually threads the constraint explicitly rather than bridging around it (here: thread an explicit root and keep the in-process callable contract — found on the second pass, landed with all three contract tests untouched).
3. **File with the rejected alternative recorded** so the next owner does not re-derive and re-attempt the same dead-end mechanical fix.

**Especially applies when the conflicting surface belongs to a live peer workstream** — the committed tests you are breaking are that peer's contract, and reding them is a cross-session collision, not a local cleanup.
