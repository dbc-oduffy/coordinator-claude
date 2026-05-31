---
title: Verification before completion
created: 2026-05-06
type: doctrine
related:
  - plugins/coordinator-claude/coordinator/CLAUDE.md
  - docs/wiki/delegate-execution.md
  - docs/wiki/round-trip-contract-tests.md
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

1. Run `git diff --stat <expected-path-glob>` — treat the diff as ground truth, not the agent's completion report.
2. **Empty diff for an agent that claimed work = re-dispatch** with the explicit list of unfinished files. Do not accept "I completed all files" alongside a zero-line diff.
3. For spec-driven dispatches that mandate a canonical phrase or pattern across N files, also run `grep -l "<canonical phrase>" <target-files>`. File count alone is not proof — the canonical content must actually appear.


### (c) Edit tool success is not proof of change

After a sequence of Edit calls — especially before claiming a fix is in or before commit — run `git diff <file>` (or `git diff --stat`) to confirm the bytes actually moved. Edit returns success on no-ops where the new_string already matched.

### (d) Subagents may "fix" things without producing diffs (fifa T1.4)

Subagents conflate "this is correct now" with "I made it correct." Before reporting fixes applied, executor prompts should include `git status --short` + `git diff --stat`; report actual diff stats, not self-narrated counts of intended changes. "No-op, target was already correct" is a valid outcome — and an honest one.

### (b) Match verification to the change you made (L274)

Verification must target the actual side effects of YOUR action. Running an unrelated expensive process ("ran the full test suite, all green") as "verification" of a one-line change is cargo-cult.

- Made a code edit? Re-Read the file and grep for the changed symbol.
- Added a pattern across files? `grep -l` the pattern across those files.
- Fixed a specific code path? Exercise that path — don't just run unrelated tests.

"I made the edit" without re-Read is an assertion, not evidence.

| Verification Claim | Must Run | Not Sufficient |
|--------------------|----------|----------------|
| N files updated by executor | `git diff --stat` showing N files | Agent chat summary |
| Canonical phrase applied across files | `grep -l "<phrase>" <targets>` | "All files processed" |
| One-line bug fix | Re-Read file + grep for change | Full test suite passing |
| Pattern applied consistently | Targeted grep on changed files | Build success |

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

## Scope-Conformance Check After Executor Returns (geneva T1.5)

Before staging any executor output: (1) run `git diff --stat` to enumerate changed paths, (2) confirm each path is within the dispatch's declared scope, (3) stash or revert any out-of-scope edits.

Out-of-scope edits are common failure modes: test file deletions, unrelated refactors, autonomous commits the executor made despite instructions. The check is mechanical and must happen before the coordinator reads the diff semantically.

See `docs/wiki/delegate-execution.md` → "Scope-Conformance Check" for the dispatch-prompt clause that enforces this on the executor side.

## Definition of Done (acceptance gate before declaring completion)

For any plan with declared acceptance criteria, "done" means more than green tests. Before claiming completion or moving to merge:

- [ ] Every **acceptance criterion** is satisfied (or explicitly waived in writing with PM acknowledgement).
- [ ] Tests/checks ran and the output is captured (link or excerpt — not "trust me").
- [ ] If user-visible: **manual demo path verified** — you actually walked the steps, not just inferred from green tests.
- [ ] Technical reviewer has run if scope mode warrants it (production-patch and feature: yes; prototype/spike: optional). The VP-of-Product lens at merge (refactor-vs-patch, shape, dumb questions) is the PM's call — not an auto-dispatched YK gate.
- [ ] **Known limitations** are documented — what *isn't* covered, what edge cases were deferred.
- [ ] **Rollback or mitigation** is named — if this turns out wrong in production, what's the recovery move?
- [ ] **Ship verdict** is staged for the PM (see `coordinator:merging-to-main`).

This is the bridge between engineering output and PM confidence. "The agent says it's done" is not the gate; this is.

**"Smoke-proven launch-ready" overstates coverage when the smoke was killed before reaching most phases.** A predecessor handoff that says "PROVEN end-to-end via a real smoke (then killed)" may mean only the first of 5+ phases actually ran. Steps 2c, 2d, Phase 5 — never executed. The "launch-ready" framing makes recovery cost feel small; in reality the subsequent run crashes on previously-untested phases (lock self-deadlock, argparse arg-shape bug, chunker source_type=unknown). Rule: "proven" means at least one end-to-end run completed all phases, even at smaller scale — not "the first phase started." Either run a tiny full-pipeline smoke or qualify the claim as "Step 2a proven; later phases unverified." (2026-05-28, from-source-engine-rebuild.)

## AC Gate Degradation and Probe Anchoring

> See coordinator/CLAUDE.md § Verification Before Done for the boot-context tripwire.

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

### Don't kill the sibling-repo daemon you depend on without a verified relaunch path

A sibling repo's running process (MCP daemon, indexer, watcher) may be the only live instance your session depends on. Before stopping/restarting/killing it, **verify the relaunch path resolves end-to-end** — the launch command exists, its config points at a valid target, and it comes back healthy — *before* taking the running one down. Killing the only running daemon you depend on without a verified relaunch path strands your own session and any concurrent one. *(2026-05-27.)* The cross-process analogue of "land regression-net tests before the refactor that depends on them": prove the recovery path before destroying working state. → [`cross-repo-communication.md`](./cross-repo-communication.md) for the cross-repo coordination framing.

### A probe or tool that spawns a sibling's daemon directly inherits none of its lifecycle-manager safety

**A probe/test/tool that spawns a sibling's daemon DIRECTLY (subprocess, not via the sibling's lifecycle manager) inherits NONE of that manager's safety machinery — park-state, crash-loop breakers, resource ceilings all live in the manager it bypassed.**

*2026-05-27, project-rag-ue-addon (daemon-parking-leak).* `doctor.py:tool_dogfood` ran the host's dogfood runner directly (`--with-addons --project-root <addon>`), which child-spawned `project_rag_server.py` outside `ensure-project-rag-server` — so on a parked host actively being fixed for a 230GB-CUDA-commit freeze it could re-spawn a 43GiB daemon with no brake and no starts-log entry.

**Rule:** when you spawn another repo's long-lived process directly, you've opted out of its lifecycle safety — either route through its manager, or replicate the manager's guard signals (park-state sentinel path + cooldown — confirm the canonical signal with the owner, as park-state may have no positive on-disk sentinel). An explicit `PROJECT_RAG_PARKED` env flag (or equivalent) checked at the spawn site is the interim guard when routing through the manager is not possible. Sibling to the direct-spawn footgun note in `implementation-standards-by-domain.md` § Cross-repo contract discipline and to detect-then-fail-loud.

**Park-state sentinel mirroring as interim guard.** When a direct-spawn is unavoidable (the sibling's lifecycle manager is not callable from the probe), the minimum guard set is: (a) mirror the sibling's crash-loop sentinel path + cooldown, (b) check an explicit park-state env flag (`PROJECT_RAG_PARKED` or equivalent) at the spawn site, and (c) confirm with the sibling owner what the canonical park signal is — park-state may have no positive on-disk sentinel, making it easy to miss. This is an interim shape; route through the manager as soon as the interface is available. (2026-05-27, project-rag-ue-addon daemon-parking-leak.)

### A disk fix is not live in a long-running daemon until it restarts — and the restart path may itself be broken

A persistent daemon holds imported modules in memory and serves the code loaded at *its* boot. A disk edit + green pytest proves the logic is correct, not that the running process serves it.

- **After fixing code a long-running daemon serves, verify through the LIVE interface** (MCP call / HTTP endpoint), not just pytest.
- **Confirm the restart primitive actually restarted** — re-query after. A `session-restart` can exit 0 and be a silent no-op (marker mechanism never reaches the HTTP daemon); the stop script can then crash on a different interpreter. "exit 0" from a restart command is not evidence the new code is live.
- Green unit tests are **necessary, not sufficient**, for runtime-readiness.

### End-to-end verify can uncover a different-mechanism bug with the same user symptom

Green tests + correct ACs ≠ user-visible problem resolved. A workstream can address every *named* bug, pass Patrik review, ship executors, and still leave the *symptom* alive via a path the substrate read never reached.

- **When a workstream targets a user symptom (not just a code defect), end-to-end verify by running the actual user action and observing the actual user-visible state** — non-skippable even when tests pass and ACs are met. (Observed: `session-restart` worked perfectly, then an addon hookspec re-spawned a sister daemon on the wrong interpreter within seconds — same symptom, new mechanism.)
- **If verify uncovers a new mechanism producing the same symptom, carve a spinoff** — do not expand scope mid-workstream.

### Editable-install import env: the finder is a frozen snapshot

setuptools editable installs (`pip install -e`) bake a top-level-package MAPPING (the `__editable__*_finder.py` + `top_level.txt`) at install time. Adding a package to `pyproject.toml` later does **not** refresh it — the new package is invisible until reinstall.

- **When an editable-installed package fails to import despite source existing AND being declared, re-run `pip install -e <root>` before deeper debugging.** Install scripts that only `pip install -r requirements.txt` must ALSO re-run the editable install, or new packages silently break on consumer boot. (See also the managed-refresh venv-state leg in global CLAUDE.md § Plugin live-install propagation.)
- **Reproducing a daemon's editable-import env requires `site.addsitedir()` or the venv's OWN python — NEVER bare interpreter + `PYTHONPATH`.** `PYTHONPATH` adds the dir to `sys.path` but does not process the `__editable__*.pth`/finder, so editable packages stay unresolvable. dist-info checks (`entry_points()`) ARE PYTHONPATH-visible; module-resolution checks (`find_spec` / `import`) are NOT — a probe using PYTHONPATH passes the dist-info half and false-fails the import half.
- **To prove "is X loaded in the daemon's env," repro from a NEUTRAL cwd with the daemon's effective interpreter.** Running from the package source tree imports it via cwd and fabricates a pass. The check must (a) use the daemon's effective interpreter (argv-injected site-packages), AND (b) run from a cwd that is NOT the package source tree (`cd /c/` then import). Trust a doctor's env-scoped FAIL over a hand-repro until the hand-repro controls for both.
- **A stale live install of an agent definition can carry a dead MCP server in its allowlist, silently breaking ALL of that subagent's MCP tool resolution.** When a subagent can't see MCP tools its source frontmatter grants, FIRST diff the live install against source for dead/retired `mcp__<server>__*` entries — don't reach for platform/dispatch-mode hypotheses until the live copy is confirmed in-sync. `refresh-plugin-live-install.sh` clears the dead ref + stale plugin cache. This is source↔install drift; diagnose against the LIVE copy, not source.

### A documented or override-gated guardrail is not an implemented one

- **Confirm script + `hooks.json` registration + trigger coverage before trusting that a guardrail exists** — a guardrail named in doctrine can be unregistered or never-wired.
- **Safety-gate failures behind override flags can be latent-broken since authoring.** Never reach for `--skip-X` / `--force` before reading the probe code — an override flag reached-for reflexively is a smoke-signal that the gate may be broken, not that the work is genuinely exempt.

### Windows launcher-stub re-exec is not a duplicate-spawn bug

When a daemon appears to spawn a "duplicate" copy on a different interpreter at exactly boot time, BEFORE searching for application code that spawns subprocesses: dump parent/child argv + CreationDate via CIM. **Identical CreationDate + parent-child link + same argv + different `ExecutablePath` = a uv launcher-stub re-exec** (spawn-and-wait on Windows, not POSIX exec-replace), not a spawn bug. Diagnostic: `Get-FileHash` the venv `python.exe`/`pythonw.exe` (identical hash + ~46 KB = uv stub); check `pyvenv.cfg::home` for the base interpreter. The fix surface is the daemon spawn site, not the suspected protocol. → `python-subprocess-patterns.md`.

## A Discriminator Guard Is Dead If It Never Matches the Value the Producer Emits

**A status/enum-discriminator guard that gates on a value the producer never actually emits is dead code — it silently passes everything it was meant to catch.** A guard like `if status == "DEGRADED": block` is only live if the producer ever emits the literal string `"DEGRADED"`; if the producer emits `"degraded"`, `"warn"`, or a structured `{level: 2}` instead, the equality never fires and the guard is a no-op that *looks* protective. The failure is invisible: the guard reads correct, tests that mock the expected-but-wrong value pass, and the gate ships open.

**Rule:** before trusting a value-discriminator guard, verify the emitted value at the producer — grep the producer for the literal it actually writes, or assert it with a wire-path test that flows a real producer output through the guard. Prefer gating on a **structural signal** (field presence, type, a typed sentinel) over a brittle string-equality on an enum the producer owns independently. This is the verification-side twin of `implementation-standards-by-domain.md` § Gate on Discriminating Signal (which governs *what* to gate on); here the discipline is *confirm the guard's condition can ever be true* before declaring the guard done. (2026-05-30, project-rag.)

## Model-Identity / Version SHA Guards Must Be Prefix-Aware, Not Exact-Equality

**A SHA / model-identity guard comparing a full hash with `==` false-fails on every legitimate abbreviation — make identity guards prefix-aware, and verify the index is queryable before trusting that the harness merely runs.** Git SHAs, model fingerprints, and content hashes are routinely surfaced abbreviated (7–12 chars) by one tool and full-length by another; an exact-equality identity check rejects the abbreviated form even when it is the same object. Use prefix containment (`full.startswith(short)` / `short` is a prefix of `full`) for identity comparison.

Separately: a harness that *runs* is not a harness that *answers*. Before trusting an eval/index-backed guard, confirm the index is actually queryable (a real query returns real rows) — a runnable-but-empty index passes "the harness executes" while silently failing "the harness has data." (2026-05-29, project-rag.)

## Reproduce a Static Root-Cause Empirically Before It Gates a Flip / Ship / Cross-Repo Decision

**A root-cause derived by reading code or reasoning statically is a hypothesis — reproduce it empirically before it drives an irreversible decision (a config flip, a ship, a cross-repo memo).** Static analysis tells you what *should* happen; it does not prove what *does*. When a diagnosed cause is about to gate a decision with reach beyond the current edit — flipping a default, shipping a fix, sending a sibling EM a memo that asserts the cause — run the reproduction first: trigger the failure, observe it, then observe the fix removing it (red→green on the actual mechanism, not a proxy). This is the decision-gating twin of the fix-code empirical-audit rule (`reviewer-premise-challenge.md` § Empirical audit before fix code) and the P0/P1 verification gate: read-confirms-plausible, but only a reproduction confirms-real, and the cost of a confidently-wrong static cause scales with the blast radius of the decision it gates. (2026-05-29, project-rag.)

## The Bottom Line

**No shortcuts for verification.**

Run the command. Read the output. THEN claim the result.

This is non-negotiable.
