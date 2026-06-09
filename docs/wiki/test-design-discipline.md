# Test Design Discipline

**Provenance:** consolidated 2026-05-05 from `tasks/lesson-triage-2026-05-05/SYNTHESIS.md` §B10. Source extracts: holodeck E18, E26, E39, E53, E56, E76, E78; project-rag E3.

Tests prove what they assert and only what they assert. The patterns below are recurring failure modes where green tests masked real bugs — or where iteration on flaky tests sent debugging in the wrong direction.

## 1. Spike Pass-Conditions Must Match the Actual Wire Path

A spike that confirms "subsystem registration succeeds" or "object lookup returns non-null" doesn't prove the subsystem's outbound code path is functional — early-return guards (`IsRunningCommandlet`, `IsRunningClientOnly`, `IsRunningDedicatedServer`) commonly leave a subsystem registered-but-half-initialized.

**Frame spike acceptance as "send a message and observe its arrival on the other side," not "look up the object and check non-null."**

A spike that confirmed `GEditor->GetEditorSubsystem<X>()` reachable failed to catch that `ConnectionManager.IsValid()` was false in commandlet mode — costing one full smoke-run cycle to surface what a round-trip pass-condition would have caught immediately.

## 2. Grep-Guard Tests Must Avoid the Forbidden Token in Their Own Source

A test that greps the handler file for `"UCableComponent"` and asserts absent will fail when the handler's own negative-spec docstring lists `# - Use UCableComponent (forbidden)` for human readers — the test's own forbidden-token sentinel fires on legitimate negative-spec mentions.

**Defense (belt-and-suspenders, neither alone is sufficient):**

1. **Runtime-assemble** the forbidden token: `FORBIDDEN = "UCable" + "Component"` so it never appears literally in the test source.
2. **Strip docstrings/comments** in the test's scanner so legitimate negative-spec mentions don't fire the guard.

Applies to any anti-pattern lint test in any language.

## 3. LIKE-Pattern AC Tables Mask Separator/Normalization Bugs

`LIKE '%suffix%'` predicates don't care about separator characters in the prefix — three live consumers can be silently broken on path comparison while the customer-sim AC table passes clean.

**Rule:** AC tables for any artifact carrying paths must include at least:

- One **full-path-equality** assertion (`= 'exact/path/here'`).
- One **read-time-consumer-output** assertion (live-source, live-signature, drift-detection populated) — not only LIKE-shaped queries.

LIKE is fine as one of several predicates. It is not fine as the only predicate.

## 4. Test Scenarios Cover Code Paths, Not Entity Names

For parameterised entry points: name scenarios after the **code path**, not the entity. Require at least one entity per uncovered placeholder/transport.

A test suite organized by entity (one test per game class, one per service, one per table) leaves placeholders and transports silently uncovered. A suite organized by code path forces the design question "which entity exercises this branch?" and surfaces gaps as missing test fixtures rather than missing assertions.

## 5. Land Regression-Net Tests BEFORE the Refactor That Depends on Them

When planning a wave touching 5+ files of similar shape, ask: "is there a test net that lets me verify byte-stability after?"

If no, **build the net first.** Investment compounds across all downstream refactors. Building the net post-hoc means proving correctness without baseline — which empirically devolves into "the diff looks right" and one-by-one regression chasing as failures surface days later.

## 6. Exit Codes That "Mean Failure" May Be Truthful Contract Reports

When a batch job returns a non-success exit code, **read the handler's exit-code contract before diagnosing a crash**, GC teardown bug, or RHI shutdown issue. A handler that returns 30 (TerminalData) when ANY item failed is correct *if* the AC table predicted some items would fail.

**Concrete failure:** state-tree-headless workstream wasted a full session diagnosing a "teardown crash" that didn't exist — handler was truthfully reporting C3's AC-expected `COLOR_NAME_COLOR_MISMATCH`. Before adding `TStrongObjectPtr` roots / GC traces / RHI-shutdown theories, read the handler's exit-code line and ask: "is this the contract reporting truthfully?"

**Fix shape:** encode AC expectations in the input data (`expected_failure: true` in the manifest item), not in a separate harness layer. Handler then distinguishes expected from unexpected failures and gates exit code on unexpected-only.

## 7. Iteration-Debugging Signal Is Failure-Mode Shift, Not Failure Count

When iterating fixes against a noisy test suite, comparing the *count* of failures across runs can mask real progress.

`postfix5` and `postfix6` of the recipe-smoke suite both reported "3 failed" but the failures were structurally different: afterAll-hook timeouts + `READINESS_TIMEOUT` cascade vs. clean per-handler MCP request timeouts. The count held steady; the failure *class* shifted from harness-defect to handler-defect — which is the harness fix succeeding.

**How to apply:** for any iterative fix loop against a flaky suite, compare run N+1's failure messages line-by-line against run N's, classify each by root-cause family, and only declare regression if a *new failure class* appears.

## 8. Contract Change → Grep ALL Assertions Over the Contract

When landing a code change that alters the runtime contract of a function (retry semantics, return shape, error type, sleep durations), grep the existing test suite for assertions ON that contract — not just ON that function — and update any test still encoding the old shape, even if it's outside the immediate WS scope.

**Concrete failure:** WS-4 introduced a 3-attempt respawn-with-backoff loop that sleeps `[1, 2]s` between attempts on `ConnectError`. The pre-existing test `test_connect_error_path_unchanged` asserted "VRAM backoff sleeps `(1, 2, 4)` must NOT appear on a ConnectError path" — written to lock down the *old* (no-retry) contract. After WS-4 landed, that assertion silently became wrong: the 1s/2s sleeps now DO appear by design. The targeted per-WS pytest invocations passed because none ran the affected test module; only a broader sweep caught it.

**Rule:** after validating a contract-changing WS via its own targeted tests, run the closest-adjacent test modules (anything that imports the changed module) before declaring done. For sleep/retry semantics specifically, grep for `sleep` + the function name, not just the function name.

## 9. Vacuous-Pass Risks: Anchor Path Inputs Outside the Test's Own Cwd

A test that calls into production code with `Path(".")` (or any cwd-relative root) passes by accident: it's scanning the test runner's working directory, not the asset under test. The assertion can be structurally satisfied by completely unrelated files that happen to live wherever pytest was invoked from.

**Rule:** test inputs that represent a "scan root" or "project root" must be a tmp_path fixture, a baked-in test-data directory, or an explicit absolute path under the repo. `Path(".")`, `Path.cwd()`, and bare relative paths in test bodies are forbidden — they make the assertion silently dependent on invocation directory.

A grep-guard for `Path("\.")` and `Path\.cwd\(\)` in `tests/` catches the common shapes; both belt-and-suspenders rules from §2 apply if the lint test itself must reference the forbidden token.

## 10. Mock at the Helper Boundary, Not the Stdlib Boundary

Patching standard-library entry points one level below where the production code calls them lets the production code reach the real layer through a sibling API and bypass the patch silently.

- **`importlib.import_module` patches leak through `importlib.resources.files()`.** A test that patches `importlib.import_module` to inject a fake module never intercepts code that resolves the same package via `importlib.resources`. The patched call returns a stub; the unpatched sibling resolves the real package and the test passes against unintended bytes.
- **Network-layer mocks leak through real subprocess spawns.** A pytest fixture that mocks `urllib`/`httpx`/`requests` does not stop a child process the production code spawns from making real network calls. The spawn itself is the leak surface — the network mock applies to the parent's address space only.

**Rule:** mock at the *helper boundary your code calls*, not at the stdlib boundary one level below. If the production code calls `our_module.load_resource(name)`, patch `our_module.load_resource`. If it calls `our_module.spawn_worker(cmd)`, patch `our_module.spawn_worker`. Patching `importlib.*`, `subprocess.*`, or `urllib.*` directly is a code smell — every sibling API in that stdlib module is now an escape hatch the test does not cover.

A test fixture that does not own a thin helper layer over the stdlib should add one before adding more patches.

## 11. Smoke Fixtures Must Clear the Agent's Pre-Flight Gates

When the rule under test is downstream of a pre-flight gate (size threshold, schema validator, format check), the smoke fixture must satisfy the gate. Otherwise the smoke validates the gate's rejection path, not the rule.

**Concrete failure:** a smoke-test fixture for an agent with a 1KB size pre-flight came in at 200 bytes. The pre-flight rejected it before the rule ever ran; the smoke "passed" because the rejection was the expected error class for malformed input. The actual rule under test was never exercised.

**Rule:** when authoring a smoke fixture for an agent or pipeline with pre-flight gates, list the gates in the fixture's docstring and confirm each one is cleared. If the rule under test *is* a pre-flight gate, the fixture must vary on inputs that exercise both sides of the gate, not just the failure side.

## 12. Regression Gates on Synthetic Baselines Are Worse Than No Gate

A regression gate that bootstraps from an all-zero, all-empty, or otherwise degenerate baseline returns false reassurance: any non-degenerate measurement looks like an improvement, and any actual regression is hidden under "still better than zero."

**Rule:** any regression-gate harness must detect synthetic/degenerate baselines (all-zero arrays, empty datasets, single-sample populations) and emit a *warning* verdict, never a pass. Pass requires a real baseline with non-trivial variance. The gate should refuse to run rather than ratify a meaningless comparison.

This composes with §1: a gate's pass-condition must be the actual signal, not a structural property the degenerate baseline already satisfies.

## 13. Buffer-and-Decide Beats State Machines for Line-Shape Data

Parsing line-shape data (log lines, CSV, key:value tuples) with a state machine is brittle — state-transition tables drift as input vocabulary widens, and each new line variant forces a fresh state plus transitions from every existing state into it. Prefer buffer-the-frame-then-decide patterns: read the full logical record into a buffer, then run a single classifier on the buffered content. State machines for line shapes are a 2010s anti-pattern; modern parsers buffer the frame and dispatch once.

## 14. Cumulative-Sweep Validation Closes Cluster-Closure Verdicts

A test cluster that runs green in isolation is not green for shipping. Sibling-test pollution (shared `sys.modules` state, namespace-package shadowing, fixture leak, autouse side-effects, monkey-patch teardown order) only surfaces under the full collection — the same modules imported in a different test-discovery order can swap green for red.

**Rule:** before declaring a cluster closed, run the cumulative sweep — the full test-suite path the CI gate uses, not just the cluster's own targeted invocation. The targeted invocation is a debugging tool; the sweep is the verdict. Applies to any test runner that maintains shared global state across collection (pytest, jest, vitest, go test with cached compilation, ctest). "Green in `pytest tests/feature_x/`" is hypothesis; "green in the full pytest invocation the CI runs" is signal.

This composes with §8 — a contract change can pass per-WS targeted tests and fail the cumulative sweep when an unrelated module imports the changed contract.

## 15. Sibling-Surface Parity Tests Catch Capability Divergence at Design Time

When a system has parallel surfaces — sibling MCP tools, sibling CLI subcommands, sibling API endpoints, sibling handler classes — capability divergence between them is a predictable bug class. One sibling gains a flag, validation rule, or output field; the others drift behind silently. Manual audits catch it eventually; parity tests catch it at design time.

**Rule:** for any N-sibling surface, write at least one **parity test** that asserts the N siblings expose the same capability set on a chosen axis (flags, output keys, error classes, validation rules). The test enumerates siblings dynamically (registry walk, glob, introspection) rather than hardcoding the list — a new sibling missing the capability fails the test on the day it lands, not three sprints later.

Parity tests are cheap relative to the bugs they prevent. Default-on for any registry of ≥3 sibling surfaces.

## 16. Real-Shell Tests for Real-Shell Semantics

A Python (or any host-language) re-implementation of shell parsing logic structurally cannot reproduce shell-language bugs — quoting, expansion order, IFS handling, glob semantics, signal propagation, exit-code masking through pipelines. A test suite that asserts "our parser matches what bash would do" by re-implementing bash's rules in Python is testing the re-implementation against itself.

**Rule:** when the production code's correctness depends on real shell behavior (process spawning, pipelines, redirection, env-var inheritance, signal handling), include at least one test that invokes the real shell — `bash -c '...'`, `pwsh -Command '...'`, etc. — and asserts on the observed result. Re-implementations are fine as fast-path unit tests, but the integration gate must touch the real interpreter.

Same logic applies to any other "we re-implemented the rules" pattern: JSON-Schema validators, regex engines, glob matchers — the canonical implementation is the gate, the re-impl is a convenience.

## 17. Name-Promises-Behavior vs Docstring-Admits-Shape-Only

A test named `test_handler_rejects_invalid_payload` whose docstring says "this verifies the handler accepts the payload structure" is a failing test masquerading as passing. The name promises behavior coverage; the docstring admits the test only checks structural shape, not the named behavior. Future readers grep the name, see green, and trust the named behavior is covered when it isn't.

**Rule:** a test's name and docstring must agree on what is verified. If a test only confirms input shape (typecheck, schema-fit, parse-success), name it `test_handler_accepts_payload_shape`, not `test_handler_rejects_invalid_payload`. EM-side recipe during code review: grep for tests whose docstring contains "shape only", "does not exercise", "stops short of", "structure not behavior" — the docstring is admitting a gap; the name probably isn't. Either rename or write the missing behavior assertion.

This composes with §1 (spike pass-conditions must match the wire path) and §11 (smoke fixtures must clear pre-flight gates) — all three are failure modes where a green test does not exercise the claimed behavior.

## 18. Test Data Degeneracy Is Not a Checker Bug

When a structural-test checker (overlap detector, schema validator, dedupe scanner) fires on test inputs that *are* degenerate by construction — synthetic fixtures with intentionally overlapping rows, fixtures shared across joinery cases — the bug is not in the checker. The checker is reporting truthfully against degenerate input.

**Rule:** before refactoring a checker that fires on test data, inspect the fixture. If the fixture is degenerate (intentionally overlapping for test purposes, shared across joinery cases, hand-rolled to exercise a corner case), fix the input or extend the checker's whitelist — don't relax the checker's signal. Composes with §6 (truthful exit-code contracts): the checker is the analogue of the exit-code-reporting handler.

## 19. Golden-Snapshot Suites Need Identifier Normalization

A golden-snapshot test that inlines file content captures per-install identifiers — git SHAs, PIDs, timestamps, install-id UUIDs — verbatim. Every commit between capture-time and run-time breaks the test until the normalizer covers the identifier shape, even though the assertion the test is *trying* to make is "this file has the expected shape," not "this file contains exactly this SHA."

**Concrete failure:** holodeck umbrella golden inlined `plugins/*/version.txt` content unnormalized. `install-plugin.sh` writes `git rev-parse HEAD` into the version file at install time. The Chunk 6 commit itself moved HEAD; the test that had been GREEN at capture-time was RED at next-commit-time with a one-character diff (`fae6464d` → `b8b758bd`). The file's *presence and 40-char-hex shape* are the install end-state contract — the *specific SHA* is per-install ephemera.

**Rule:** golden-snapshot suites must run inputs through an identifier normalizer before comparison. Standard patterns:
- 40-char hex SHA → `__GIT_SHA__` (regex: `\b[0-9a-f]{40}\b`)
- PID shapes → `__PID__`
- ISO-8601 timestamps → `__TIMESTAMP__`
- UUID4 → `__UUID__`
- Floating-point timing values → `__DURATION__`

Maintain an excluded-paths list for log/transient directories that the snapshot should not even attempt to compare — `_normalize_string` consumes those at the glob layer, not the per-line layer.

The normalizer is itself test-covered: feed in real CI outputs and assert that two captures from different installs produce byte-identical normalized output. A snapshot suite without this self-test silently re-introduces flake every time install infrastructure adds a new per-install identifier.

Composes with §1 (snapshot pass-condition must match the contract — *shape*, not *exact bytes*) and §8 (contract change → grep all assertions over the contract — installer changes ripple through every golden the installer touched).

## 20. Swappable-Sink Indirection Needs a Wire-Up Integration Test

A logging/event/metric sink with swappable indirection (`_log_fn = default_log; def log(...): _log_fn(...)`) lets tests inject a recording sink to assert the shape of what got logged. The architectural intent is good — production code stays decoupled from concrete sinks. The trap: synthesis-shape tests pass whether or not any caller actually calls the indirection. The test swaps the sink at the indirection's own boundary; the production path that should call through the indirection never does, and the test never notices.

**Concrete failure (project-rag, 2026-05-17):** T3 silent-fallback hardening introduced `_log_fn` as a swappable sink for `__embed_sidecar_fallback_event__` ledger rows. The wire-up call from the fallback path was never added — `_log_fn` had no callers in production code. Tests passed by patching `_log_fn` directly and asserting the patch's recorder. The bug surfaced four days later when a bucket-c rescue grep found zero ledger rows in real runs.

**Rule:** any swappable-sink design needs at least one **wire-up integration test** that drives the production code path end-to-end (real entry point, real argument shape) and asserts the recorder saw the call. The sink-shape unit test is the floor; the wire-up integration is the ceiling. If the only test that exercises the sink is one that patches the sink itself, the indirection is functionally inert and the test is asserting against its own patch.

Greppable smell during code review: a test that imports `_log_fn` (or the equivalent indirection variable) directly and patches it. That test alone does not prove production code calls through. Pair with a test that runs the public-API caller and asserts the indirection fired.

Composes with §10 (mock at helper boundary not stdlib): both are "patch-the-wrong-layer" failure modes — §10 patches too deep, §20 patches the swap point so the production wire-up is bypassed entirely.

## 21. Swappable-Sink Shape Tests Must Be Paired With Wire-Up Integration Tests

(This is a deeper framing of §20 for cases where the swap point is a module-level variable, not a class attribute. The principle generalizes.)

A swappable-sink hook (`_log_fn`, `_emit_fn`, `_record_fn`) is functionally inert if no production caller ever invokes it. Synthesis-shape tests pass either way — they patch the swap point directly, assert the patch recorded the call, and never exercise the production code path that is supposed to invoke the indirection. Existing tests patching the sink as the swap point will pass even when the production wire path is broken.

**Rule:** pair every sink-shape test with at least one integration test that (1) enters through the real public-API entry point, (2) drives the production code path end-to-end with real argument shapes, and (3) asserts the recording sink saw the expected call. "The only test that exercises this sink patches the sink itself" is the smell. Greppable review signal: a test file that imports `_log_fn` (or equivalent) directly without also importing the public entry point that calls through it.

Composes with §10 (mock at the helper boundary, not the stdlib boundary) and §20 (swappable-sink indirection needs a wire-up integration test).

## 22. Leakage Tests and Coverage-Floor Goldens Are Complementary Lenses

**Leakage can pass vacuously when the upstream detector emits nothing.** An engulfing ERROR node drops the scope entirely, leaving nothing to overlap with the forbidden span — so 15/15 leakage tests pass green while goldens silently encode 0-reflection across the same regions. The vacuous-pass mechanism: zero scopes → zero overlaps → zero leakage → green. The golden catches it by asserting the producer actually populates the contract.

Either lens alone is a false signal for overlay/refiner correctness:

- **Leakage-only:** an ERROR-overlap leakage test can pass vacuously when the upstream detector returns no scopes in the affected region — zero emissions, zero leakage, green. No detector, no problem — but the coverage gap is invisible.
- **Golden-only:** a coverage-floor golden pins pre-fix broken behaviour as the baseline. A golden captured before a bug is fixed treats the bug as the correct output; the gate passes until someone re-captures.

**Rule:** for any overlay or refiner component, instrument *both* lenses. The leakage test proves the overlay does not emit in regions it should not touch; the golden proves the overlay emits correctly in regions it should touch. Only with both does green carry signal.

## 23. Install-Validation Must Assert Exact Plugin ID-Sets, Not Just Absence of Errors

A hookimpl that silently swallows `ImportError` at registration time masks packaging gaps. The hookimpl registers (or appears to), the test that checks "registration didn't raise" passes, and the missing dependency never surfaces until a downstream call attempts to use the plugin.

**Rule:** install-validation tests must:
1. Run from a **clean editable install** (`pip install -e .` in a fresh venv), not a path-hacked test runner.
2. Assert the **exact set of registered plugin IDs** — not just "no exception raised." A missing plugin produces a smaller-than-expected id-set, which a set-equality assertion catches; "no exception" does not.

Fail-soft `ImportError` catches in hookimpl bodies are the common vector. When auditing a plugin registry, grep for `except ImportError: pass` or `except ImportError: return` patterns in hookimpl entry points.

## 24. Heavy-Boot CLIs Warrant Unit-Shape Integration Tests, Not Subprocess Shape

When a CLI has a heavy collaborator that dominates startup time (database initialization, model loading, MCP server bootstrap), subprocess-based integration tests are slow, flaky, and environment-sensitive — they also fail to isolate which component caused a failure.

**Rule:** for heavy-boot CLIs, write integration tests that mock the heavy collaborator at its boundary and invoke the CLI's internal entry point directly (not via subprocess). This is faster, deterministic, and exercises the same surface the subprocess test would exercise — the CLI's argument parsing, routing, and output formatting — without paying the startup cost.

Shape: `mock.patch("module.HeavyCollaborator")` + call the CLI's `main()` directly + assert stdout/stderr/return-code. Subprocess shape is appropriate only when the test's *goal* is specifically to verify the process launch path (e.g., entrypoint script resolution, shebang handling, exit-code propagation through shell).

## 25. `xfail` Markers Absorb Test-Infra Exceptions Silently

A test marked `@pytest.mark.xfail` will show as `xfail` (expected failure, green-adjacent) for *any* exception — including test-infrastructure exceptions (import failures, fixture teardown errors, conftest bugs) that have nothing to do with the cited failure mode. The marker is consuming failures you don't own.

**Rule:** before trusting the green-adjacent state of an `xfail` test, verify the cited failure mode is actually what's producing the `xfail` result:
1. Run with `--runxfail` to surface the raw exception.
2. Confirm the exception class and message match the documented failure mode.
3. If the exception is from test infrastructure (not from the production code under test), fix the infrastructure before trusting the xfail classification.

Corollary: `xfail(strict=True)` is safer — it becomes `xpass` (unexpected pass, red) when the test starts succeeding, forcing re-evaluation. Plain `xfail` stays silent on both "still broken as expected" and "broken for wrong reason."

## 26. "Pre-Existing Failure" Framing Is Provisional When a Recent Gate Could Have Created It

*2026-05-15, claude-unreal-holodeck.* A failure that appears "pre-existing at baseline" may have been *created by* a recently-introduced validation gate — the gate now lives at baseline, so failures it produces inherit the baseline's age. Attribution by file-age or grep-on-failure-string finds the test, not the cause.

**Rule:** before accepting "pre-existing failure" as a reason to defer or suppress, grep `git log --oneline -- <test-file>` and `git log --oneline -S '<gate-symbol>'` for gate-introduction commits within the suspect window. If a new gate landed adjacent to the failure's first appearance, the failure was *created by* the gate addition, not inherited. Fix the gate alignment, do not defer the failure.

## 27. Source-Level Tripwires Beat Empirical Timing Probes for Async Regression Nets

**`inspect.getsource()` substring assertions are the robust shape for "use this idiom at this call site."** Async timing probes fail when upstream `await` yield points let a sentinel fire before the blocking call starts — making the test pass under both broken and fixed code. The source-level tripwire is mechanical and deterministic: assert that `asyncio.to_thread(self._spawn_and_poll)` appears in the source AND that `= self._spawn_and_poll()` does not. If the call shape regresses, the grep fails immediately without any timing dependency.

Async timing tests have too many yield-point escape hatches. A test that "blocks the event loop for >N ms" can be defeated by adding a single `await asyncio.sleep(0)` in the middle of a sync block, or by the test environment's clock resolution being too coarse to catch the regression.

**The robust shape is a source-level tripwire:** grep the async-handler code for `time.sleep`, blocking `requests.*` calls, sync `open()` of files above threshold, `subprocess.run` without `asyncio.to_thread`, etc. — fail at static-analysis time, not at flaky test-time.

Empirical timing tests are belt-and-suspenders, not the primary contract. If both exist, the timing test supplements the tripwire; it does not replace it.

**Generalizes:** for any property best stated structurally — no sync call inside async, no allocation in a hot loop, no global state in a pure function — the source-level grep IS the primary regression net. When you find yourself writing a timing-based or sampling-based probe to enforce a structural invariant, stop and ask whether a static grep on the production source would enforce the same invariant deterministically.

*Source: project-rag-ue-addon/state/lessons.md:116, 2026-05-16.*

## 28. Awk `\b` Word-Boundary is Not POSIX-Portable — Silent Literal-Match Failure

*2026-05-18, claude-central.* Pruner Rules 5/6/7 used `\b(FIXED|...)\b` in awk to match closure keywords as whole words. Tests against em-dash-bounded fixtures passed; tests against bracketed-status fixtures and real files failed silently. Git Bash gawk treats `\b` as either a literal backspace match or a no-op depending on dialect — neither is a word boundary.

**Rule:** any awk regex using `\b`, `\<`, `\>`, `\d`, `\s`, `\w` is non-portable. Substitute POSIX character classes (`[[:alnum:]]`, `[[:space:]]`) or explicit boundary char classes:

- `\b(KEYWORD)\b` → `(^|[^A-Za-z0-9_])(KEYWORD)([^A-Za-z0-9_]|$)`
- `\b(KEYWORD)$` is OK — `$` is already a non-word anchor.
- `\d` → `[0-9]`; `\s` → `[[:space:]]`; `\w` → `[A-Za-z0-9_]`.

**Greppable signature:** `awk ... /\\b/` in any `bin/*.sh`. The failure mode is silent — the regex compiles but matches the wrong substring set. Adjacent: bash `[[ =~ ]]` with extglob is also a portability minefield; prefer explicit anchors over relying on shell-extension regex flags.

## 29. `mktemp` Filenames Defeat Basename-Allowlist Guards in Tests

*2026-05-18, claude-central.* A dry-run sweep used `mktemp /tmp/probe.bug-backlog.md.XXXXXX` to stage test copies for an allowlisted pruner. The pruner refused every copy because its allowlist matches `$(basename "$INPUT")` against exact strings (`bug-backlog.md`, `coordinator-improvement-queue.md`) — `probe.bug-backlog.md.x030` is not a match. Sweep showed 0 deltas across 10 fixtures while I assumed the new rules just hadn't fired yet.

**Rule:** any test or sweep that exercises a path-allowlisted script must preserve the basename exactly, not suffix-mangle it via `mktemp`. The correct shape is per-file subdir:

```bash
case_dir=$(mktemp -d /tmp/sweep.XXXXXX)/case$i
mkdir -p "$case_dir"
cp "$src" "$case_dir/$(basename "$src")"
```

**Greppable signature:** `mktemp .../<allowlisted-name>.XXXXXX` in any sweep/test script. Adjacent: test fixtures with random-suffix file extensions that defeat MIME-type detection have the same shape — the discriminator the script uses (basename, extension, MIME) must round-trip through the fixture's filename strategy.

## 30. Slow Tests Masquerading as Unit Tests Blow Up Default Suites

*2026-05-20, cross-repo sweep.* Default `pytest` (or jest, or `node --test`) MUST run only fast unit tests. Any test that shells out to a real script, does heavy `importlib`, hits real network or non-tmpfs filesystem, or sleeps > 100ms requires an explicit `@pytest.mark.slow` / `@pytest.mark.integration` (or framework equivalent) AND a default-exclusion mechanism (`addopts = "-m 'not slow'"`, jest `testPathIgnorePatterns`, node:test `{ skip: process.env.FAST === '1' }`).

**Empirical anchor.** Cross-repo sweep on 2026-05-20 found 200+ unmarked offenders across 10 sibling repos. `/x/project-rag` alone shipped 86 unmarked tests where `tests/install/**` and `tests/integration/**` drive real installer / venv / doctor / pip-resolver subprocesses — realistic floor is **minutes** on a clean `pytest` invocation. `/x/claude-unreal-holodeck` shipped 39 files (~290 fns) including a `time.sleep(31)` synthetic-timeout self-test. Initial premise blamed `/x/project-rag-ue-addon` (`26 s × ~1250 install tests = ~10 h`) but empirical measurement showed `tests/install/` runs in 41.6 s — the per-test setup-script invocation uses `--phase-list` / `--i-am-agent` early exits, not full installs. Lesson: docstring-promised timings are author intent, not measured truth — verify with `--durations=20` before trusting.

**Threshold heuristic.** Any test > 1 s wall-clock, or any test whose body invokes:
- `subprocess.run` / `os.system` / `execSync` / `spawnSync` / `child_process`
- `importlib.import_module(<heavy-pkg>)` (heavy tree imported at collection)
- real network: `fetch('http`, `requests.get('http`, `urllib.request`, raw `socket`
- real filesystem I/O on non-tmpfs (NOT `tmp_path` / `tempfile.NamedTemporaryFile`)
- `time.sleep > 0.1` / `setTimeout > 100`

… is **presumed slow** until proven otherwise.

**Greppable signatures:**
- pytest: `subprocess.run(...)` or `importlib.import_module(<heavy>)` in a `test_*.py` without `pytestmark = pytest.mark.slow` or per-test `@pytest.mark.slow|integration`.
- conftest / pyproject with no `addopts` AND no marker-based default exclusion.
- jest config without `testPathIgnorePatterns` for `tests/integration/**`.
- node:test files with `execSync` / `spawnSync` and no `{ skip: process.env.FAST === '1' }` guard.

**Config posture pattern (correct shape):**

```toml
[tool.pytest.ini_options]
addopts = "-m 'not slow and not integration'"
markers = [
    "slow: marks slow tests",
    "integration: marks integration tests",
]
```

```js
// jest.config.js
module.exports = {
  testPathIgnorePatterns: ["<rootDir>/tests/integration/", "<rootDir>/tests/scripts/", "<rootDir>/tests/e2e/"],
};
```

```js
// node:test
test('script syntax is valid', { skip: process.env.FAST === '1' ? 'FAST mode' : false }, async () => { ... });
```

**Adjacent (Item 24).** Heavy-boot CLIs warrant unit-shape integration tests, not subprocess shape. When a test shells out to a CLI just to assert its argparse surface, the right refactor is import-and-call. Marker placement is the cheap reversible fix; refactor is the real fix.

**Authorial intent ≠ measured truth.** Verify with `pytest --durations=20`, jest `--logHeapUsage --verbose`, or framework equivalent before trusting a docstring claim about a test's runtime.

## 31. Tests Must Assert Positively, Not Just Survive

*2026-05-20, project-rag audit.* A test whose only effective check is that the function-under-test did not raise — no `assert`, no `pytest.raises`, no `pytest.fail`, no `self.assertX` — passes even if the FUT becomes `def fut(...): pass`. The "did not raise" property carries zero signal once the FUT is silently a no-op; future refactors can gut the function and every such test stays green.

**Rule:** every test must have at least one assertion that would FAIL if the function-under-test were replaced with `def fut(...): pass`. Apply the test at write-time:

> *"If the FUT became `def fut(...): pass`, would this test still pass?"* If yes, no signal — either add the positive assertion (return-value comparison, observable side-effect, captured-arg check) or delete the test.

**Legitimate exemptions** (these genuinely retain signal under the strict standard):
- **Mock-call oracles** — `mock.assert_called_once()` / `assert_not_called()` IS the positive assertion. A FUT-becomes-`pass` would fail `assert_called_once`; spurious-call regressions would fail `assert_not_called`.
- **Domain-type contracts** — `isinstance(result, <DomainClass>)` where the class is a named domain type (not `dict`/`list`/`int` returned by a function always typed that way). FUT-becomes-`pass` returns `None`, isinstance fails.
- **Immutability contracts** — `isinstance(x, frozenset)` / `isinstance(x, tuple)` when the test name or docstring explicitly says "must be frozenset/tuple — prevents accidental in-place extension".
- **Helper-asserts-internally** — the test body calls a helper like `_assert_envelope_shape(...)` that contains real assertions inside. Verify the helper, not the caller.
- **Paired with active sibling** — an idempotency / no-op test sits in a class where a sibling test exercises the FUT positively. Cite the sibling's file:line in a comment.
- **Smoke imports** — `def test_smoke_import(): from x import y` — import-not-raising IS the signal for the file's module-load contract.
- **`xfail`-marker contracts** — `@pytest.mark.xfail(strict=True)` body whose call raises is verified via the marker; `strict=False` is weak — any exception (including test infra bugs per §25) produces `xfail`. Acceptable only when the body explicitly names the known-limit in a comment AND `xpass` surfacing is acceptable evidence when the limit is fixed.
- **Deferred placeholders** — `pytest.skip("AC-X deferred to Chunk N")` or `assert True, "deferred"` — only legitimate if the deferral is actively tracked in a plan doc, not orphaned.

**Greppable signatures** for an audit pass:
- `# (should|must|does|will) not raise` followed by the FUT call and end-of-function.
- Test docstring says "passes through" / "silent when X" / "is no-op when Y" / "is idempotent" — verify the body isn't bare-call-no-assert.
- Final statement of the test body is a call to the FUT with no following assert (AST-detectable).
- `assert isinstance(result, (dict|list|int|str|float))` as the ONLY assertion, where the FUT's type annotation already promises that return type.

**Composes with §17** (Name-Promises-Behavior vs Docstring-Admits-Shape-Only): rule 17 catches name/docstring disagreement; this rule catches body/contract disagreement. A test can pass rule 17 (name and docstring agree on "is silent when X") and still fail this rule (body has no signal that the silence-branch was actually taken).

**Empirical anchor.** *2026-05-20, project-rag no-positive-assertion audit* (consumer-side artifact: `/x/project-rag/docs/wiki/no-positive-assertion-audit-2026-05-20.md`). AST scout flagged 236 candidates across 106 test files in `project-rag/tests/`. After filter pass (helpers-that-assert-internally, contract-no-op-by-design) and triage under the strict standard, 9 real positive-signal gaps surfaced. Two of the proposed fixes had factually-wrong premises (audit conflated dedup-correctness with None-handling-graceful; audit thought regex matched when it didn't) — the executor's verify-before-edit pass caught both, illustrating that even a careful audit benefits from a literal "run the regex / check the hash" pre-flight before declaring positive-assertion shape.

## 32. Observed vs. Inferred in Evidence Prose

**Tree-sitter ERROR-byte coverage is meaningless without locus context.** Report as `(percentage, where-relative-to-consumer-query)`, never as a bare percentage. An ERROR-byte rate that sounds fatal (e.g. 24.7% on a UPROPERTY macro fixture) can be irrelevant when the errors are confined to macro argument lists while top-level structural boundaries — the only thing the consumer queries — survive intact. Bare-percentage reporting inverts signal: high-sounding numbers trigger false alarm; low-sounding numbers grant false confidence. Always pair the rate with "do these ERRORs intersect the consumer's actual query surface?"

**Distinguish observed-outcome from inferred-mechanism in evidence prose — be explicit about which claims are observed (exit code, stderr, RSS) vs. inferred (kernel primitive, root cause).**

A test verdict may be correct while the evidence file's prose explanation of *why* misframes the mechanism. The AC verdict doesn't change, but the next reader can't tell observation from inference and may act on the inferred part when it's wrong. Frame as: *observed: X. inferred: Y because Z.* When only one half is available, name the missing half explicitly.

**Rule:** evidence-file prose must separate the observed signal (what an instrument measured) from the inferred mechanism (why you believe that happened). When the inference is uncertain, say so. A confident-sounding mechanism with no observed anchor is a wishful-thinking trap.

*Source: holodeck `state/lessons.md` (holodeck-L147, central-promoted 2026-05-28).*

## 53. Hung-Run Failure Counts — Never Quote From an Incomplete Session

*Source: project-rag L10. 2026-05-28. [universal]*

**A failure count from a hung test run is the visible tip, not the total.** pytest writes junit only at `pytest_sessionfinish`; a single mid-run hang (e.g. `pytest-timeout`'s thread method can't unwind a C-blocked thread) wedges the session and kills every result after the wedge point. Quoting that count as "N failures" and acting on it produces false fixes and a false-green claim.

**Concrete failure.** A predecessor handoff said "~6 residual fast-tier failures." A hang-isolating batched runner found ~430 failures + 8 hang batches across ~7700 tests — the predecessor's run had hung at 24% and never reached the other 76%.

**Rule.** Before quoting a fast-tier failure count: confirm the run reached session end (junit file exists AND short summary line printed). When it didn't, get the inventory via batched runs — one batch = one pytest subprocess with an OS-level timeout; per-batch junit survives even when the batch hangs. Treat any "N failures so far" from a hung run as ≥N, not =N, in handoffs and decisions. Composes with §44 (bound every run; never run a known-hang surface to verify).

## 54. Class-Level Pytest Markers Over-Include When Methods Don't Share Substrate Need

*Source: project-rag L31, 2026-05-28/29. [universal]*

A `pytestmark = pytest.mark.slow` (or any marker) applied at the class level applies to every method in the class. When class methods don't share the substrate that earns the marker — some methods are fast/unit, others genuinely hit subprocess/network/heavy-load — the blanket marker either excludes fast methods from default runs (marker is `not slow`), or fails to protect slow methods from default inclusion. The marker granularity must match the substrate granularity.

**Rule.** Before applying a class-level marker, ask: do ALL methods in this class share the same substrate need? If outlier methods exist — one method hits a real subprocess, the other is a pure-unit assertion — promote the outliers out of the class or use per-method markers. A class-level marker is correct only when the substrate need is genuinely class-wide (e.g. every method calls the same heavy fixture). Composes with §30 (slow-marking discipline) and §34 (never slow-mark a guard test).

## 55. Fossilized Count Assertions Hide Drift

*Source: claude-unreal-holodeck L11 + holodeck L15, 2026-05-28/29. [universal]*

An assertion of the form `assert len(results) == 37` (or `expected: 37` in a golden) hardcodes a count that was accurate when the test was written but has no mechanism to stay accurate as the system evolves. When the count drifts, the test fails — but worse, when the system contracts (fewer results than expected), the test might not even be exercised meaningfully. The literal encodes an author's snapshot, not a semantic invariant.

**Rule.** Replace literal `expected N` count assertions with self-consistency invariants that read the system's own source of truth: `assert len(results) == len(list(registry.all()))`, or `assert all(r in known_set for r in results)`, or `assert set(results) == expected_set` where `expected_set` is derived dynamically from the registry, not hardcoded. Retain a floor assertion (`assert len(results) >= 1`) to prevent vacuous-pass over empty sets (§40). A hardcoded count is a snapshot; a self-consistency check is a contract.

## 56. Source-Migrate Without Test-Migrate Leaves Import Wall

*Source: claude-unreal-holodeck L17 + holodeck L17, 2026-05-28/29. [universal]*

When a source module is migrated (moved, renamed, restructured) without co-migrating its test suite, the tests accumulate `ImportError` failures that mask real test results. The collected-count delta is the falsification: if migrating the source caused `pytest --collect-only` to go from N to M<N collected tests, M–N tests are invisibly broken at import time, not because the code regressed but because the test's imports lag the source.

**Rule.** Co-migrate the regression net in the same commit as the source migration. Verify with `pytest --collect-only` before and after — a count drop signals import failures, not test removals. Never declare "module migrated" when the test's collected count dropped relative to the pre-migration baseline. Composes with §43 (collection errors mask large failing-test populations). See also `cleanup-sweep-hazards.md` §21 (producer-rename sweep bucket 1).

## 66. Enumerate ALL Mock-Patch Shapes Before Moving a Symbol Whose Consumers Move

*Source: project-rag L8, 2026-05-30.*

When a module-extraction refactor moves a symbol AND its consumers, every test that patches that symbol points at a target string that just became stale — and a stale `mock.patch` target fails **silent-green**: the patch resolves a path that still imports cleanly, so it never raises, but it monkeypatches the *old* binding while production now calls through the *new* one. The test passes while testing nothing.

**Rule.** Before a module-extraction or symbol-move refactor, grep the test tree for **all three patch shapes** over the moving symbol, not just `patch("mod.sym")`:

- `patch("mod.sym")` / `patch("mod.Cls.method")` — string-target patches (most common, most brittle to moves).
- `patch.object(alias, "sym")` — object-target patches via an imported alias (the alias binding may now point at the wrong module).
- `mod.sym = fake` / `monkeypatch.setattr(mod, "sym", ...)` — direct attribute resets.

Update every site to the symbol's new home, then run the suite. A stale patch does not announce itself — the chain-end review (full-suite run + a spot-check that the patched call actually intercepts the production path, §20/§21) is the net that catches the silent-green. Composes with §10 (patch the helper boundary, not the stdlib boundary) and §56 (co-migrate the regression net). See also `cleanup-sweep-hazards.md` §21.

## 57. Drift-Guard Test Must Read Source-of-Truth, Not Re-Type the Value

*Source: project-rag-ue-addon L20, 2026-05-29.*

A test written to guard against drift in a constant or configuration value (`assert TIMEOUT == 30`) re-types the value the guard is supposed to track. When the source-of-truth changes and the constant is updated, the test must be updated separately — and if it isn't, the guard stays green while the constant drifts. Worse: a test that asserts a literal can be "made green" by changing the literal in the test, defeating the guard.

**Rule.** A drift-guard test must READ the artifact it guards: `assert TIMEOUT == parse_config("timeout_seconds")`, or `assert SCHEMA_VERSION == read_version_file()`, or `assert FIELD_LIST == introspect_schema().column_names`. The test must fail if and only if the source-of-truth and the derived constant diverge — not if someone edits the test's own expected value. The source-of-truth artifact is the single point of truth; the test reads it.

## 58. `bash -n` Failure Does NOT Prove a Shipped Script Is Broken

*Source: project-rag L27 + L57 (2026-05-28/29). [universal]*

`bash -n <script>` parses for syntax errors but does NOT execute. Bash parses top-to-bottom; an early-exit code path means a syntax error in a later function body may never be reached at runtime. `bash -n` failure on a script does NOT prove the script is broken in practice — the error line may be in a branch that the script's actual code paths never enter.

Conversely, `bash -n`-clean does NOT prove the script runs correctly — it only proves it parses. A script can pass `bash -n` and fail at runtime due to unset variables, missing dependencies, or logic errors that only surface on execution.

**Rule.** Confirm real-vs-artifact by exercising the actual code path, not by running `bash -n`. When `bash -n` fires on a multi-function script, check whether the error line is reachable from any real invocation — if the function is dead code or only called in a branch that short-circuits before the error line, `bash -n` is a false alarm. For a newly-edited script, prove a region clean by confirming the error line shifts by exactly `delta_lines` between HEAD and the worktree version (line-number drift is the `bash -n` signal for "edit is in this region").

## 59. Paired NDCG Delta Is Valid on Stale Index When Both Arms Share the Index State

*Source: project-rag L35 (2026-05-29).*

An internally-controlled paired NDCG delta (A/B measurement where both arms use the same index state) is valid even on a stale index — the stale-index degradation affects both arms equally, so the delta measures only the change being evaluated. Gate cross-repo replies on index freshness only when absolute thresholds are load-bearing (e.g. "retrieval quality meets ≥0.6 NDCG"), not for paired deltas that measure relative improvement.

**Rule.** Distinguish paired deltas (both arms see the same substrate → index freshness is irrelevant to the delta) from absolute measurements (one arm vs. a fixed threshold → freshness matters). A reviewer who blocks a paired-delta result on "stale index" is confusing relative and absolute measurement contexts. When the goal is "does change X improve retrieval?" both arms should use the same stale index — refreshing the index before one arm invalidates the pairing.

## 60. Hand-Traced Refactor-Equivalence Is a Hypothesis — Run the Regression Suite

*Source: project-rag (refactor-equivalence-oracle), 2026-05-29.*

When refactoring for equivalence ("this is the same logic, just restructured"), the claim is an assertion — not an observation. Partial-input cases, null/empty guards, boundary conditions, and error paths are exactly where "equivalent" code paths diverge. A hand-trace of the happy path does not cover the full contract.

**Rule.** Before asserting equivalence to the PM, run the regression suite that pins the old behavior. If no suite exists, build a set of snapshot assertions first (the behavioral baseline), then land the refactor. "Equivalent by inspection" with no test evidence is a hypothesis the PM cannot verify and a claim that will be disproved by the next edge-case bug report. Composes with §5 (land regression-net tests before the refactor) and §41 (a test that passes because of the bug).

## 61. A Behavior-Change Regression Net Must Be Observed Red Before It Goes Green

*Source: project-rag L153, 2026-05-30. [universal]*

A test added alongside a behavior change that is only ever observed *passing* proves nothing about the change — it may be green because the change works, or green because the assertion never targeted the changed path. The proof the net is load-bearing is watching it **fail on the pre-change tree, then pass on the post-change tree** (red→green).

**Rule.** When landing a behavior change with its regression net, run the new test against the tree *without* the change (stash the change, or check out the parent) and confirm it goes **red for the right reason**, then apply the change and confirm green. A net never seen red is a hypothesis, not evidence — it can be vacuously passing (§31), targeting the wrong wire path (§1), or already-green-without-the-fix. Composes with §41 (a test that passes because of the bug), §47 (stash-recompile-rerun for attribution), and §60 (hand-traced equivalence is a hypothesis — run the suite).

## 62. Guard the Destructive Primitive on a Shared Singleton, Not the One Offending Test

*Source: project-rag L92, 2026-05-29. [universal]*

When a test suite shares a process-level singleton (a host daemon, a global connection pool, a module-level cache, a long-lived editor session), a single test that calls the singleton's **destructive primitive** (`shutdown()`, `reset()`, `kill()`, `close()`) tears it down for every sibling test that runs after it. The symptom reads as "the shared host died mid-run" or "sibling tests fail nondeterministically by collection order"; the cause is one test killing the thing everyone shares. Silencing or reordering the offending test is whack-a-mole — the next test that calls the same primitive re-opens the wound.

**Rule.** Guard the destructive primitive itself, not the test that happens to call it. Gate the teardown on an explicit opt-in signal so it only fires in the test that genuinely owns lifecycle — e.g. read `os.environ.get("PYTEST_CURRENT_TEST")` and refuse the destructive path unless the calling test is the designated lifecycle owner, or require an explicit `force=True` / dedicated fixture. The primitive becomes self-defending: any sibling that calls it incidentally is a no-op rather than a sibling-kill. Composes with §14 (cumulative-sweep validation — sibling-kill only surfaces under the full collection) and §34 (don't slow-mark the guard that protects shared state).

## 63. Test Scratch Substrate Must Mirror Prod Layout AND Caller Mode

*Source: claude-central L10, 2026-05-30.*

A flat scratch repo (`mktemp -d` with files at top level) does not exercise a code path that only triggers on a **nested** directory layout — a nested-path gate bug stays green because the fixture never produces the nesting the gate is written to catch. Symmetrically, a fixture that drives the production code through a different *caller mode* than prod uses (direct function call where prod shells out, or vice versa) exercises a different wire path than the one that ships.

**Rule.** A test scratch fixture must reproduce **both** the production substrate's directory/layout shape (nesting depth, subdir structure, sibling files) **and** the production caller's invocation mode (subprocess vs. in-process, CLI args vs. kwargs, cwd-relative vs. absolute). A flat fixture for a nested-path consumer, or an in-process call for a subprocess-spawning consumer, is a vacuous-pass shape: green proves the easy layout works, not the one prod hits. Composes with §9 (anchor path inputs outside cwd), §51 (run against the REAL shared artifact), and §63's sibling in `python-subprocess-patterns.md` (conftest spawn-flag monkeypatch doesn't reach production child-spawn sites).

## 64. Source-Location-Assertion Tests Are a Distinct Regression Class From Deleted-Path Failures

*Source: project-rag L92, 2026-05-29.*

A runtime parity gate ("both arms behave identically", "the refactored call returns the same value") does **not** cover tests that assert on *source location* — `inspect.getsource()` substring checks, `fn.__module__` assertions, `spec_from_file_location` path checks, golden file-path manifests (§27). A symbol that moves modules can pass every runtime-parity test while every source-location-assertion test over it goes red — and that red looks identical to a deleted-path `ImportError` even though the symbol still exists and works.

**Rule.** When a refactor moves symbols across files/modules, classify the resulting test failures into two buckets before triaging: **deleted-path failures** (the symbol/path genuinely no longer exists — fix the import or the path) versus **move-regressions** (the symbol still exists and behaves correctly, but a source-location assertion now points at the old home — update the assertion's expected location). Conflating them wastes a triage cycle treating a correct move as a regression. The runtime parity gate is silent on this class by construction; add a source-location sweep (`inspect.getsource` / `__module__` / loader-path assertions) to the migration checklist. Composes with §27 (source-level tripwires), §56 (source-migrate without test-migrate leaves an import wall), and `cleanup-sweep-hazards.md` §21.

## 65. Frozen A/B Env Levers in an Adopted Daemon — Zero Variance Is the False-Null Tell

*Source: project-rag L159, 2026-05-30.*

An A/B experiment that toggles behavior via an environment variable assumes the lever is **re-read per run**. When the code under test is adopted into a long-lived daemon that reads the env once at boot and caches it, both "arms" of the experiment run the *same* frozen configuration — the daemon never re-reads the toggle. The measurement then reports a clean null result ("A and B are identical, no effect") that is actually a false null: the experiment never varied anything.

**Rule.** Before trusting a null/no-effect A/B result, confirm the lever actually varied across the two arms — **zero variance between arms is a false-null tell, not evidence of no effect.** For env-lever experiments against daemonized code, verify the daemon re-reads the env per run (or restart it between arms), and assert non-zero variance on the lever's observed value as a precondition of trusting the delta. Composes with §12 (regression gates on degenerate baselines), §59 (paired deltas vs. absolute thresholds), and §40 (assert the scan's own width before asserting over its contents).

## 67. Module-Identity Pollution Is Not Value-Cache Pollution — Autouse Resets Cannot Fix Identity

*Source: cross-repo learn-lessons, 2026-05-30. [universal]*

A test that passes in isolation but fails in the full suite (§14) has two structurally distinct root causes that demand different fixes, and conflating them sends the fix in the wrong direction:

- **Value-cache pollution** — a module-level singleton, cache, or `ContextVar` holds a *value* from an earlier test. Fix: an autouse reset fixture that re-zeroes the value before each test.
- **Module-identity split** — the *same* module is imported under two different names (bare `audit` vs. `project_rag_mcp.audit`), so Python builds two distinct module objects, each with its *own* `ContextVar` / singleton / cache. A write through one name is invisible through the other. This is not a stale value — it is two objects that should be one.

**An autouse value-reset cannot fix a module-identity split.** Resetting the value on object A does nothing to object B, and `sys.modules.setdefault("alias", real_module)` inside a fixture is a **no-op if the bare module was already imported earlier in suite order** — by fixture time both module objects already exist and consumers have already bound to whichever they imported first. The dual binding is fixed at import time, not run time.

**Rule.** When a full-suite-only failure traces to a shared singleton/`ContextVar`/cache, first discriminate **identity vs. value**: check whether the symbol is reachable under two import paths (`import x` and `import pkg.x`, a bare-module alias, a `sys.path` shim that exposes the same file twice). If identities differ (`id(module_a) != id(module_b)`, or two distinct objects answer the same attribute), the fix is to **collapse the dual-import seam before any test imports it** — at conftest-import time or via `sitecustomize` / a canonical alias in the package `__init__`, not via a per-test fixture. Only once identity is single does an autouse value-reset become the correct tool for the residual value-pollution. Composes with §14 (cumulative-sweep validation surfaces both classes) and §10 (patch the helper boundary — a dual-import seam is the same "two bindings, one should exist" footgun one layer up).

## Skill Reference

`docs/wiki/test-driven-development.md` should cite items 1, 2, 3, 5, 8, 9, 10, and 11 in its preflight checklist when the planned change crosses a contract or refactors >3 files of similar shape.

## Related

- `docs/wiki/oom-reproducer-strategy.md` — multi-dimension assertions for fan-out OOM reproducers (RSS + commit count + concurrent-session count + wall-clock).
- `docs/wiki/round-trip-contract-tests.md` — producer/consumer schemas need round-trip tests, not parallel fabrications.

## 32. Autouse HOME-Isolation Fixtures Break Subprocess Tests

*2026-05-24, project-rag.* A pytest autouse fixture like `_isolate_project_rag_home` that redirects `HOME` (or its Windows equivalent) in the test process will be inherited by any subprocess spawned via `subprocess.run` / `Popen` — and if that subprocess calls `os.environ.copy()`, it picks up the hijacked directory. The test appears to pass (the in-process path is correct) while the subprocess silently uses a wrong root. Defense: add a `@pytest.mark.real_home` escape-hatch marker and skip the fixture for tests whose subject path explicitly spans a subprocess boundary. (Source: 2026-05-24 project-rag) → module-import-time capture corollary and the `monkeypatch.setattr` fix pattern: [`test-environment-discipline.md`](./test-environment-discipline.md) §4.

## 33. Fixture-Substitution Masking Production Drift

*2026-05-24, project-rag.* When a test fixture substitutes a real implementation for a stub "at test time" to make the test green, the on-disk artifact under test IS the stub — not the real impl. The test is green because the fixture swaps in the thing the stub was supposed to be; production uses the stub and is broken. Fix: the on-disk artifact must BE the real implementation; the fixture must not substitute it. If substitution is genuinely needed (e.g. costly external), the test contract must degrade gracefully without asserting on the real code path. (Source: 2026-05-24 project-rag)

**Prefer a real-data subset over a synthetic minimal fixture for at least one test case per chunker.** Synthetic fixtures pass by construction — they exercise the code path the author intended, not the shapes production data actually produces (encoding edge cases, oversized rows, schema-drifted historical data). Keep synthetics for boundary cases (empty, oversized); use real-data subsets where the file format is stable. (Source: project-rag-ue-addon L39)

**A fixture's defaults must be self-consistent across its own fields, not faithful to an illustrative memo example.** A contract memo's example can pair fields in a combination that never occurs in real data; copying it verbatim as a fixture default embeds the inconsistency. Assert internal consistency at authoring time: `path ↔ mount_root ↔ mount_class` must agree; if the memo example is a didactic sketch, don't inherit its contrived combinations. Sibling to the cross-repo-contract-is-hypothesis rule (`cross-repo-communication.md`). (Source: project-rag-ue-addon L51)

## 34. Never Mark a Guard or Contract Test `@pytest.mark.slow`

*2026-05-24, project-rag.* A guard test, tripwire test, or contract test marked `pytest.mark.slow` is deselected from the default `-m "not slow"` run. The guard is invisible to CI while the bug it guards against ships. Rule: guard tests, tripwire tests, and cross-contract tests are NEVER marked `slow` regardless of actual runtime. If runtime genuinely must be gated, extract the slow work to a helper and keep the guard assertion in an un-marked test that drives the entrypoint at minimal cost. (Source: 2026-05-24 project-rag)

**Verify the gate is actually SELECTED under the default config — green-when-force-selected is not green-when-shipped.** *(2026-05-29, claude-unreal-holodeck.)* An acceptance-gate test that passes only under `-m ''` (force-select everything) but carries a default-deselected marker is a **vacuous gate**: it never runs in the path CI and `/validate` actually take, so it can never go red on a real regression. When landing a new gate/acceptance test, confirm it appears in the *default* collection — `pytest --collect-only` (no `-m` override) must list it — not merely that it passes when explicitly selected. A gate green only under `-m ''` is the same failure as a `slow`-marked guard: present in the tree, absent from the verdict.

## 35. Mechanical AST-Walk Guards for "Every X Must Call Y" Contracts

*2026-05-24, project-rag-ue-addon.* "Every plugin module must call `register()`" and similar structural contracts enforced only by docstring-convention are not contracts — they're suggestions that decay silently. Convert them to CI-enforced rules via AST-walk: parse the module tree, assert the required call is present. This is two dozen lines of Python, catches entire missing-call classes at commit time, and turns a docstring convention into a failing test. Applies to any "all X must Y" structural invariant you'd otherwise enforce by review comment. (Source: 2026-05-24 project-rag-ue-addon)

## 36. Build a 60-Second Reproducer Before Re-Firing a 30-Minute Job

*2026-05-24, project-rag-ue-addon.* When a long-running job (build, full test suite, slow smoke) fails, resist re-firing it to see if the fix works. Build the smallest reproducer that exercises the same code path in under 60 seconds. Iterate on the reproducer until the fix is confirmed, then fire the long job once for final validation. The iteration radius must match the actual change radius — if you changed one function, a 30-minute full build is not the right feedback loop. (Source: 2026-05-24 project-rag-ue-addon)

## 37. Never `git commit` Inside a Hook Smoke Test on an Auto-Push Branch

*2026-05-24, project-rag-ue-addon.* A git-hook smoke test that calls `git commit` inside the working repo (even on a "test" branch) will trigger auto-push hooks on branches with auto-push configured — pushing phantom test commits to the remote. Fix: initialize a throwaway scratch repo via `git init` in a `tempfile.mkdtemp()` / `tmpdir` and run all hook invocations there. The smoke test should never touch the real repo's commit history. (Source: 2026-05-24 project-rag-ue-addon)

## 38. Multi-Test Failure Cluster May Be Stale-Bytecode Flake

*2026-05-24, project-rag-ue-addon.* When several unrelated tests fail together — especially after a file rename, module move, or branch switch — suspect stale `.pyc` files in `__pycache__` before triaging each failure individually. The bytecode mismatch causes import errors that look like real failures. Defense: `find . -type d -name __pycache__ | xargs rm -rf && find . -name "*.pyc" -delete` before re-running in isolation. If the failures disappear after the cache clear, the root cause was bytecode flake, not a regression. (Source: 2026-05-24 project-rag-ue-addon)

The runtime mechanics of stale-bytecode flake — plus the concurrent-shared-tree variant where a transient mid-edit file state produces a *fake* assertion failure on a constant HEAD already defines correctly — live in `docs/wiki/test-environment-discipline.md` §6. Cross-link, don't duplicate.

## 39. Graceful-Skip on a Missing Fixture Is a Hollow Pass — Make the Load-Bearing Assertion Unskippable

*Recurs: L67, L69 (project-rag), holodeck-L897, holodeck-L195. Consolidated 2026-05-27; holodeck-L195 folded in via central-promotion 2026-05-28.*

A test that `pytest.skip()`s — or silently early-returns — when its core fixture isn't loadable reports **green while proving nothing**. The skip converts a behavioral gate into a no-op that still reads as Success. Worse than red: red is signal, green-via-skip is anti-signal — a future reader greps the name, sees green, and trusts coverage that never ran.

**Concrete failures.**
- *holodeck-L897:* an MFC cross-band exporter test "passed" by skipping when an engine `UMaterialFunction` (`CheapContrast`) wasn't loadable in the bare test project — the `cross_band_reference` assertion (AC5) never ran. Swapping to an in-memory engine-transient `UMaterialFunction` made the assertion always execute and **immediately surfaced a latent test bug** (wrong JSON key `type` vs `class`) the skip had hidden.
- *L67 (hollow-pass probes):* assertions left unreachable by a wire-shape bug are dead infrastructure — the probe reports green because the assertion line is never hit.

**Rule.** A load-bearing assertion must be deterministic and unskippable. If the real fixture is genuinely unavailable (heavy engine asset, external service), **synthesize an in-memory/transient stand-in that drives the same code path** rather than skipping. "Green" must mean *the assertion that matters ran and passed* — never *nothing errored*.

**Positive-control corollary (L67).** A regression test for a forbidden condition must include a positive control that exercises the forbidden condition and confirms the test would have caught it. A guard with no positive control can be silently unreachable (wire-shape bug, wrong mock boundary) and still report green. Compose with §31 (assert positively) and §20/§21 (wire-up integration for swappable sinks).

**Live-substrate integration surfaces drift that mocks reproduce (L48, project-rag-ue-addon).** Unit-test mocks encode the substrate's shape *as the author believed it was* — they reproduce the believed contract, so they pass even when the real substrate has drifted. At least one test must run against the live substrate (real DB, real index, real sibling-repo artifact) to catch drift the mock can't see. When the live substrate is genuinely unreachable, *skip-with-a-named-reason* (substrate-reachability-skip) rather than fall back to the mock and report green — a mock-fallback green is a hollow pass per §39. The skip is honest signal ("not verified here"); the silent mock-fallback is anti-signal.

## 40. Wide-Surface Tripwire Tests Must Assert Their Own Scan Width

*Source: L69 (project-rag). 2026-05-27.*

A tripwire that scans a wide surface — "no test in `tests/` references `Path.cwd()`", "every handler file is free of `UCableComponent`", "all N sibling registries expose flag X" — silently becomes a no-op if its capture set shrinks to zero. A glob that stops matching, a directory rename, or a collection-shape drift makes `for item in captured: assert ...` pass **vacuously over an empty set**.

**Rule.** Any test that asserts a property *over a captured set* must first assert the **set is the expected size**:

```python
captured = scan_all_handlers()
assert len(captured) >= EXPECTED_MIN, f"scan captured {len(captured)}, expected ≥{EXPECTED_MIN} — glob drifted"
for item in captured:
    assert not forbidden(item)
```

Without the width assertion, capture-shape drift makes the tripwire silently no-op while reading green. This is the wide-surface variant of §31's vacuous-pass standard and §39's positive control.

## 41. A Test That Passes Because of the Bug Will Fail When the Bug Is Fixed — That Failure Is Signal

*Source: L179, L120 (consumer-side seam bugs). 2026-05-27.*

A test written against buggy behavior locks the bug in as the contract. When the bug is fixed, the test goes red — and the reflex to `xfail`/revert/"adjust the assertion to match" re-buries the fix. The red is the fix succeeding, not a regression.

**Rule.** When a test fails immediately after a fix lands, **read the cited code and the test's original intent before reverting or `xfail`-ing**. Ask: "did this test pass *because of* the condition I just fixed?" If yes, the test was encoding the bug — rewrite the assertion to the correct contract, don't suppress the failure. Migration seams are the recurring locus: a shipped migration leaves consumer-side bugs at the seam (runtime ContextVar shape, symbol-port shape) that the old test silently tolerated.

Composes with §8 (contract change → grep all assertions over the contract) and §26 ("pre-existing failure" framing is provisional when a recent gate could have created it).

## 42. Guard-Exemption / Suppression Fixtures Must Reproduce the Suppressed Condition

*Source: L334, L262. 2026-05-27.*

A test that verifies "the guard does NOT halt when exemption X is wired" passes **whether or not the exemption is actually wired** — unless the fixture also reproduces the *condition the guard fires on*. With no triggering condition present, the no-halt assertion is vacuously true: the guard had nothing to halt on, exemption or not.

**Rule.** An exemption/suppression test must (1) reproduce the condition that *would* trip the guard, then (2) assert the exemption suppresses the halt. Pair it with a sibling negative test: same condition, no exemption, guard *does* halt. Only the pair proves the exemption is load-bearing.

**Drive the entrypoint, run on a dirty tree (L262).** A guard fronting loader code must be exercised by *driving the entrypoint* (subprocess or direct call), not by a syntactic rename-tripwire grep — those can be pre-existing-red from unrelated drift and give false attribution. Run guard tests on the dirty tree before the fix to confirm they're green-for-the-right-reason.

## 43. Collection Errors + Slow-Marking Mask Large Failing-Test Populations — Validate With the FULL Run

*Recurs: L314, holodeck-L885. Consolidated 2026-05-27.*

Two independent masks compound: (a) pytest **stops at a module's collection error** before running any test underneath it — a test that can't collect reports zero signal, strictly worse than red; (b) `addopts = -m 'not slow'` **deselects an entire tier by default**. Together they let a rotting suite look healthy in routine runs.

**Concrete failure (holodeck-L885):** the doctor suite reported "1 known collection error." Fixing the retired-path import that blocked collection uncovered 10 latent assertion failures frozen in pre-W6 vocabulary; the default `-m 'not slow'` had been hiding the bulk of the rest — **34 real failures total, all masked.**

**Rule.** Before declaring a suite healthy: (1) **fix collection errors first** — they hide everything beneath them; (2) validate with the **full run including slow/integration** (`pytest -m '' ` or the explicit superset), not the default-filtered run. The default-filtered green is a debugging convenience; the full-run green is the verdict. Composes with §14 (cumulative-sweep validation) and §34 (never slow-mark a guard — a guard buried under `-m 'not slow'` ships invisibly).

## 44. Bound Every Test Run; Never Run a Surface Containing a Known-Hang to "Verify"

*Recurs: L320, projectrag-L2149, ragaddon-L6. Consolidated 2026-05-27. [universal]*

Broad "verify everything" runs maximize the chance of including a slow or hanging test, and quiet output (`-q`, `| tail`, buffered pipes) gives zero progress signal until the end — a buffered run with no output is **not evidence of progress**, it is indistinguishable from a hang.

**Concrete failures.**
- *projectrag-L2149:* re-ran the full slow install suite to verify a workstream; that surface includes a known-outstanding hang (`cli-session-restart`), and with buffered `-q` + no timeout it ran blind for ~30 min.
- *ragaddon-L6:* verifying one merge test, spawned six overlapping pytest/diagnostic shells with `| tail` (buffers until exit → looked empty = "hung"), chained blocked sleeps, scheduled redundant wakeups — degrading the terminal so the PM couldn't run anything either. This is the self-monitor-for-loops antipattern in test clothing.

**Rule.**
1. **Scope the run to files under change**; deselect/avoid known-hang tests explicitly.
2. **Hard wall-clock bound on every run** — Bash `timeout`, `pytest-timeout`. No exceptions.
3. `| tail` and pipes buffer until process exit — **empty output ≠ hung**. Don't react to silence.
4. **One launch, then wait** for the harness completion notification. Do not fire parallel runs, sleep-poll, or re-launch on a slow/backgrounded test.
5. **Two failed clean attempts = stop and reassess**, don't escalate parallelism. If in-session execution is unreliable, offer the PM `! <cmd>` or hand off with the test written-but-flagged-unverified.

## 45. Shared-Fixture Defaults Must Be Self-Consistent, Not Memo-Faithful

*Recurs: L340, ragaddon-L433. Consolidated 2026-05-27. [universal]*

A contract memo's *illustrative* example payload can pair fields in a combination that never occurs in real data — the author meant it as a sketch, not a literal constraint. Copying that example verbatim as a shared-fixture **default** embeds the inconsistency, and assertions over the fixture then record states that can't exist.

**Concrete failure (ragaddon-L433):** a seam memo example paired `class_identity=/Script/Engine.MaterialFunction` with `mount_class=engine_plugin` (a contrived illustration). Copied as the fixture default, it produced a `/Game/`-path-under-`engine_plugin` mismatch, making a "canonical round-trips to engine" assertion record a path that can't occur in real data.

**Rule.** A shared-fixture default must agree **across its own fields** (e.g. `path ↔ mount_root ↔ mount_class`). The memo example is illustrative; the fixture is a contract — different correctness bars. Validate internal consistency of fixture defaults at authoring time; don't inherit a memo's didactic inconsistencies. Sibling to the cross-repo-contract-is-hypothesis rule (`cross-repo-communication.md`).

## 46. Build-Config Is a Coverage Axis — "X/X Pass" Doesn't Prove the AC When the Matrix Omits Gate Variants

*Source: L718, claude-unreal-holodeck (god-fn-refactor PR2-B). 2026-05-27. [universal]*

A green "37/37 tests pass" proves nothing about an AC when the test matrix only exercises one value of a gating build flag. The PR2-B refactor passed 37/37 with `IKRig=1`; the Staff Engineer caught an `IKRig=0` violation that the matrix never ran — the AC spanned both flag values, the suite covered one.

**Rule.** When code branches on a build-config flag, feature toggle, or compile-time gate, the test matrix must exercise **both sides of every gate the AC spans** — not just the default-on configuration. "All tests pass" is a per-configuration claim; an AC that crosses configurations needs per-configuration evidence. Enumerate gate variants at test-design time and assert the matrix covers each. Composes with §1 (pass-condition must match the actual wire path) — a flag-gated branch is a wire path the default config never touches.

## 47. Failure-Attribution via git-stash + Recompile Beats Mental Attribution

*Source: L722, claude-unreal-holodeck. 2026-05-27.*

When a test fails after a refactor and you can't tell whether the decomposition broke it or it was pre-broken, the empirical 3-step — **stash the change, recompile, re-run** — is cheaper and more reliable than reasoning about it. The stash isolates the change's contribution; if the test still fails on the stashed (pre-change) tree, the failure is pre-existing, not yours. Reach for stash-recompile-rerun before building a mental model of which edit broke which assertion. Composes with §26 ("pre-existing failure" framing is provisional — verify against the gate-introduction commit, not file age).

## 48. Failure-Artifact Output Dirs Must Be Gitignored — `git check-ignore -v` Is the Contract

*Source: L10, project-rag (2026-05-20). 2026-05-27.*

Tests that write reproducer output, failure dumps, or diff artifacts on failure will commit those artifacts if their output dir is tracked — `tasks/` is tracked by default, so a test dumping under `tasks/` leaks artifacts into the repo. Co-locate the reproducer-output dir with the test and gitignore it explicitly. The contract verification is `git check-ignore -v <path>` — a non-zero exit means the path is NOT ignored and the artifact will commit. Add the check to the test's own setup or a guard test, not just a reviewer's memory.

## 49. Broad `except sqlite3.Error: log.debug` Swallows Schema-Drift INSERT Failures Silently

*Source: L5, project-rag (2026-05-20). 2026-05-27.*

A blanket `except sqlite3.Error: log.debug(...)` around a write swallows schema-drift failures (column added to the row but not the table, CHECK-constraint rejection, type mismatch) at DEBUG level where no one sees them — the INSERT silently no-ops and the test passes because nothing raised. This is the §31 vacuous-pass standard in exception-handling clothing: the swallowed error is exactly the signal the test should assert on.

**Rule.** Narrow the except to the specific recoverable error class, or log at `warning`/`error` so drift surfaces. A test exercising a write path must assert the row landed (read-back), not merely that the call didn't raise — `log.debug`-swallowed failures are invisible to "did not raise" assertions. Composes with §31 (assert positively) and §23 (assert exact result-sets, not absence of errors).

## 50. Hermetic Probe-Aggregator Tests Must Stub Native-Lib / `platform.*` Probes

*Source: L443, project-rag-ue-addon. 2026-05-27.*

A test that drives a probe-aggregator (doctor, health-check, capability-scanner) end-to-end will execute every real probe — including ones that call native libraries or `platform.*`. On Python 3.13 / Windows, `platform.system()` (and siblings that reach WMI) can **hang** on a thrashed host, wedging the whole test run with no output. The aggregator test is not hermetic if any sub-probe touches the OS/native layer.

**Rule.** Hermetic probe-aggregator tests must stub the native-lib / `platform.*` / WMI-touching probes at their boundary so the test exercises only aggregation logic, not the host. Always run such tests under a hard `--timeout` (`pytest-timeout`) so a hang produces a **stack dump** identifying the wedged probe rather than a silent stall. Composes with §32 (mock at the helper boundary, not the stdlib), §44 (bound every run; never run a known-hang surface to verify), and §24 (heavy-collaborator boundary mocking).

**When a test "hangs," reach for `pytest --timeout=N` for the stack dump before blaming the environment.** The WMI hang on Python 3.13 / Windows (`_probe_libclang → cdll.LoadLibrary → platform.system() → _wmi_query`) is Windows-wide and not specific to any single addon — if a probe-aggregator test stalls, a timed stack dump is the fastest locus-identifier. (Source: project-rag-ue-addon L61)

## 52. Structural-Guard Allowlists Key on Stable Markers, Never `file:line`

*Source: project-rag-em memo, 2026-05-27 (`cross-repo/archive/2026-05-27-stable-marker-allowlist-guards.md`). Empirical: 7 drifted entries across 5 files in a single project-rag session; ≥3rd occurrence with prior manual triages logged inline in the allowlists.*

A structural guard that maintains exemptions keyed by `"<relpath>:<lineno>"` drifts silently on any shared concurrent-EM branch — an edit in one workstream shifts line numbers in another's files, silently turning an allowlisted call into a false-positive violation. The breakage is invisible until the gate runs, and the gate then mis-attributes it to whoever's session happens to run next. The drift compounds *because* coordinator doctrine puts multiple concurrent EM sessions on one shared daily branch.

**Rule.** Structural-guard allowlists (spawn-site guards, lint exemptions, approved-pattern registries, AST/grep enumerators) MUST key on a **stable marker** — a fully-qualified symbol/function name, or an in-source sentinel comment/decorator the guard greps for in-place — never `file:line`. Line numbers are not identity on a shared branch.

The preferred sentinel-comment shape: `# guard-allow: <rule-id> <rationale>` on the line the guard would otherwise flag, with the guard reading the sentinel in-place. Rationale lives next to the code and travels with it under refactor; concurrent edits cannot drift the keying because the key IS the code-adjacent comment, not a line number. Composes with §5 (regression-net tests land before the refactor that depends on them) — a sentinel-keyed allowlist is itself a small regression net that survives the next refactor for free.

## 51. A New Consumer of a Shared Config Format Must Reuse the Canonical Parser and Run Against the Real Artifact

*Source: holodeck-L7. 2026-05-26.*

**A gate/parser that false-passes is worse than no gate — reuse the canonical sibling parser and run it against the REAL shared artifact before trusting green fixtures.**

*2026-05-26, claude-unreal-holodeck.* A new `bin/check-reverse-drift.sh` passed 41 fixture tests but returned a vacuous "all clean exit 0" against the real machine-local registry — three bugs: unstripped CRLF → installed plugins false `[missing]`; `IFS=$'\t'` whitespace-collapse → empty `propagation_mode` shifted `live_path` into the mode field; mixed-slash Windows `live_path` → `-d` check fails. The coordinator's `check-plugin-drift.sh` had already solved all three (tomllib both-key-shapes, `| tr -d '\r'`, `${path//\\//}`, pipe delimiter).

**Rule.** A new consumer of a shared config format (machine-local registry, BOM, manifest, schema) must: **(a)** reuse the canonical parser verbatim rather than hand-roll a regex/tab variant, and **(b)** run once against the REAL artifact before trusting fixtures — fixtures don't reproduce the format's accumulated variform reality (CRLF, both TOML key-shapes, backslash paths). A vacuous all-clear gate is the worst outcome: it ships confidence with zero coverage. Composes with the round-trip-against-reader rule in `implementation-standards-by-domain.md` § Structured-config write primitives.

## 54. Tests Must Mirror Production Substrate Layout AND the Caller's Actual Mode

*Source: ~/.claude, 2026-05-30. [universal]*

A path-resolving gate can pass flat scratch-repo tests yet be dead in the real nested layout. `check-schema-version-bump.sh --staged` returned "OK" on a staged change because its tests put the file at git-root and only exercised `--commit` mode; the real plugin nests 3 deep and the commit hook uses `--staged`.

**Rule.** Mirror production directory nesting in fixtures and test the mode the production caller actually invokes. Use `git rev-parse --show-prefix`, never a manual `${ABS#$GIT_ROOT/}` prefix-strip (breaks on Windows `C:/` vs MSYS `/c/`). When a hook or script has multiple invocation modes, the test suite must cover the production mode, not just the convenient one.

## 55. `bash -n` and Static Review Are Blind to Bash Function-Ordering Bugs

*Source: ~/.claude, 2026-05-30. [universal]*

An executor defined `_check_venv_state` at L995 but called it from a new branch at L557 (earlier in execution order). `bash -n` passed (syntax is fine), static plan review passed (logic is fine), but the live dry-run hit `_check_venv_state: command not found` → fell through to "stale" → reinstalled every run. Bash binds a function name only after its definition line executes, not at parse time.

**Rule.** For any script edit that adds a caller earlier than a definition, the gate is a real invocation, not a read or a syntax check. `bash -n` is the syntax floor; a real run is the control-flow ceiling. The test for this class of bug is: invoke the script and observe the intended path, not just `bash -n && read`.

## 53. Structural-Grep Guards Need an Integration Counterpart That Actually Invokes the Script

*Source: coordinator. 2026-05-28.*

**A grep that asserts "the restore line is still in the source" proves the source contains a string. It does NOT prove the script works. Pair every structural-grep guard on a non-trivial script with an integration harness that drives the script end-to-end against a synthetic sandbox.**

*2026-05-28, coordinator.* `refresh-plugin-live-install.sh` (996 lines) was guarded by `bin/tests/test-check-plugin-drift-copy-install.sh` Part B (`grep -F 'rm -rf "$LIVE_PATH"'` over the copy_install restore region) and dogfood-proven against `holodeck-control` via the AC-9 manual refresh. Neither test invoked the script end-to-end. The integration counterpart — `bin/tests/test-refresh-plugin-live-install-integration.sh` — was authored as a sandbox that builds synthetic source+live git repos, drives the refresh script against five propagation_mode shapes (default+venv-install, source_is_live, unregistered-plugin error, broken-build-system failure, idempotency-across-re-runs), and asserts each leg's observable effects (HEAD advancement, `.refresh-log` row content, snapshot dir count, venv-install side effects). On first run the harness uncovered a real bug: line 757 used `pathlib.os.sep` which AttributeErrors on Python 3.13 (where the `os` submodule attribute was removed from pathlib), silently making every refresh on 3.13 re-install rather than no-op. The grep guard caught zero of that.

**Rule.** A non-trivial script with multi-leg observable side effects (file writes, git ops, network calls, subprocess invocations) needs an integration harness that:
- builds synthetic upstream/downstream state in `mktemp -d`,
- exports a full env-sandbox (`HOME`, `USERPROFILE`, `XDG_*`, `UV_CACHE_DIR`, `LOCALAPPDATA`, `APPDATA`, `GIT_CONFIG_GLOBAL`, `GIT_CONFIG_SYSTEM` — not just `HOME`, because uv/git/etc default many caches under platform-specific dirs outside `$HOME`),
- drives the script unchanged (no patches, no stubs) under the sandbox,
- asserts observable effects (exit code + log content + filesystem state), not just stdout strings,
- runs in <30s so it joins the fast-test set.

The structural-grep guard is the floor; the integration harness is the ceiling. Both ship together — the grep catches when someone deletes the restore line; the harness catches when the script subtly stops working under a new Python or new uv. Sibling pattern: `bin/tests/test-check-plugin-drift-copy-install.sh` (grep) + `bin/tests/test-refresh-plugin-live-install-integration.sh` (integration).

## 67. Test Isolation Breaks at Process and Module-Global Boundaries

*Source: project-rag L32, L136, L139 (2026-05-30 / 2026-06-08). [universal]*

**conftest monkeypatches, autouse fixtures, and `with patch(...)` context managers all silently lose their scope at one of three boundaries — multiprocessing-spawn workers, module-level cache short-circuits, and concurrent `patch()` re-entry.** Each shape produces green tests that pass for the wrong reason: the patch never reached the production code path, or the cached verdict carries leaked state forward, or the second-thread patch installs itself as the "original" restore-target.

**The three boundaries, with the failure mode and the fix:**

- **`multiprocessing.Process` / `Pool` workers (spawn mode).** A Windows-spawned worker is a fresh `python.exe` that re-imports the test module from scratch — `conftest.py` is never executed there, so subprocess-popup patches, env scrubbing, and any other monkeypatch state set at collection time are absent. The worker's own subprocess calls run with default creationflags. **Fix:** the worker function itself must apply the patch (e.g. call `**no_console_creationflags()` explicitly on every `subprocess.run` inside the worker body); never rely on conftest reach. Audit pattern: grep `def .*_worker` / `multiprocessing.Process` and trace into the worker body for unsuppressed subprocess sites. (project-rag, `tests/install/test_record_setup_state.py`.)

- **Module-level verdict caches that probe-once-then-short-circuit.** Patterns like `core.torch_guard._cache`, `host_inventory`, or any `_cache: Optional[bool] = None` that's set on first call and read forever after — the first test that runs under a stub locks the cached verdict for every later test in the session. **Fix:** every probe-once-cache-global must ship with a `conftest.py` autouse fixture that resets the module global between tests, mirroring `_reset_host_inventory_cache`. The cache itself is correct as a production optimization; the test isolation gap is the missing reset hook.

- **Concurrent `with patch("mod.global", ...)` from worker threads.** Two `ThreadPoolExecutor` workers each entering `with patch(...)` on the same module global race: thread B saves the *already-installed* mock from thread A as its "original," and on context exit restores to that mock — leaving the patch live session-wide after both workers finish. **Fix:** patch ONCE in the main thread, wrapping the executor block; never `with patch()` per-worker. Symmetric to §62 (guard the destructive primitive, not the offending test).

Composes with §14 (cumulative-sweep validation surfaces sibling-test pollution) and §10 (mock at the helper boundary, not the stdlib boundary — but even a correctly-placed patch leaks across these three boundaries).

## 68. Goldens Over Third-Party Tool Output: Stamp the Version, Minor-Lock the Dep, Sweep Every Sibling

*Source: project-rag L70, L149 (2026-05-31 / 2026-06-01). [universal]*

**A golden-hash net keyed on a third-party parser/formatter's output must stamp the producing tool's version into the golden AND minor-lock the dependency AND on bump regenerate every sibling golden in the same commit.** Floor-only pins (`>=0.20.0`) plus version-less goldens turn routine dependency drift into an indistinguishable-from-logic mystery — the assertion fires weeks after the upstream wheel bump and a stash-bisect is the only way to tell environmental drift from a real regression.

**Concrete failure (project-rag, 2026-05-31).** The scope_detector goldens across four languages drifted hash-but-not-count against installed tree-sitter 0.25.x while pins were floor-only; the goldens recorded no version, so the assertion message couldn't self-classify. A separate bump (`5dbb3043`) that *did* rebaseline the scope_detector goldens missed the chunker symbol_id goldens (`test_ts_chunker`, `test_python_chunker`) — byte offsets shifted there too and the chunker reds surfaced weeks later as an unexplained full-suite failure.

**Rule.** For any golden capturing output from a parser/formatter (tree-sitter, prettier, black, rustfmt, any wire-format encoder):

1. **Stamp the producing tool's version set into the golden file** (e.g. a `# tool: tree-sitter==0.25.3` header) and have the assertion message self-classify: *"installed=X.Y.Z, golden=A.B.C — environmental, regenerate or pin"* vs. *"versions match, real regression"*.
2. **Minor-lock the dependency** (`~=X.Y.0` not `>=X.Y`) so a minor bump is a deliberate act paired with golden regeneration in the same commit.
3. **On every version bump, grep EVERY golden/pin keyed on that tool's output** (byte offsets, hashes, formatted text) and regenerate them all in the same commit. Fixing only the net that happened to fail leaves silent debt in the sibling nets — they'll surface as unexplained reds whenever someone re-runs them.

Composes with §19 (golden-snapshot identifier normalization) and §8 (contract change → grep ALL assertions over the contract).

## 69. Same-Author Encoders and Synthetic Fixtures Co-Confabulate the Wrong Wire Format

*Source: project-rag L183 (2026-06-08), holodeck L64 (2026-06-08). [universal]*

**When the test fixture and the production code are written from the same wrong mental model, green tests pin the author's model, not the contract.** Two shapes of this failure: (1) round-trip parser tests where the test's encoder helper and the production decoder agree on a wrong wire format and pass trivially; (2) probe/validator tests where synthetic fixtures pin the implementation's wrong understanding of the production artifact's shape.

**Both shapes are *vacuous on the conformance contract* even though every assertion passes.** A passing round-trip test does not prove wire compatibility with an external producer — it proves the encoder and decoder agree, which they trivially do if one engineer wrote both. A passing probe test against an author-written fixture does not prove the probe works on real production data — it proves the fixture and the probe share a mental model.

**Concrete failures:**

- **Wire-format co-confabulation (project-rag, 2026-06-08).** `priming/scip_pb2.py` shipped with off-by-one protobuf field numbers in `_parse_document` / `_parse_occurrence`. The test fixture used a hand-crafted protobuf encoder helper that emitted the SAME wrong field numbers — consistent encode/decode, 8/8 green. The defect only surfaced when the translator was pointed at real `scip-python --output` bytes: every parse returned empty symbol rows.
- **Production-artifact co-confabulation (holodeck, 2026-06-08).** `check_bom_var_consumption` compared `bom_map.get("BOM_UE_VERSION", "")` against `holodeck-bom.yaml`, but `BOM_UE_VERSION` is a *shell variable name* `phase_read_bom` derives at runtime — never a YAML top-level key. Synthetic fixtures wrote `BOM_UE_VERSION: 5.7` as a literal key; probe found it; green. Real BOM uses nested `repos.project_rag.release_tag`; probe always returned BROKEN against any real install for three weeks.

**Rule.** For any parser/serializer/probe/validator whose correctness depends on conformance with an external producer's output shape, the test substrate MUST include at least one fixture sourced from outside the author's mental model:

- **External-producer fixture for wire formats** — a committed binary blob from the real external tool, OR a small generation-script the test runs that invokes the real producer. A round-trip against a hand-written encoder is a smoke test; name it as such and add the external-producer fixture before declaring the parser done.
- **Real-artifact golden snapshot for probe/validator tests** — at least one PASS-path test loads a real production artifact (or a verbatim-captured snapshot of one), not just a synthetic fixture the same author wrote. Synthetic fixtures shape-pin the author's mental model; golden snapshots shape-pin reality.

Sharper than §24 (heavy-boot CLIs warrant unit-shape integration tests — that's about CALL-PATH realism) and §11 (smoke fixtures must clear pre-flight gates — that's about gate-passage); this rule is about *data-shape* realism. Composes with §19 (golden-snapshot identifier normalization) and §1 (spike pass-conditions must match the wire path).

## 70. Fan-Out Lanes Must Propagate Every Filter the Seed Honors; Drop-Fixes Must Assert What Survives

*Source: project-rag L73 (2026-05-31), L136 (2026-05-30). [universal]*

**Two symmetric absence-coverage gaps: (1) a fan-out/lane path added beside a filtered seed silently drops the filter contract; (2) a drop/filter regression test that only asserts the bad thing is gone can't catch over-drop.** Both are "the absence is verified, the presence isn't" — and both go green while the contract is silently broken.

**Fan-out lane filter propagation (project-rag, 2026-05-30).** `project_semantic_search` / `project_rag_blended_query` applied user `chunker_id=` only on the seed project lane; AD-5's later-added default-blend host lanes (`project__lane__*`) each re-filtered to their OWN content class, re-injecting other classes and violating the seed's filter contract — silently tanking NDCG@10 from 0.83 to 0.33 while the JSON verdict stayed `ok`. **Why:** when a parallel/fan-out path is bolted beside an existing one, the seed's filter/invariant contract is easy to honor on the seed and forget on the new lanes; tests written against the seed pass.

**Drop/filter regression over-drop (project-rag, 2026-05-31).** A reject-malformed-node fix's test asserted "no `(`-leading symbol leaks" + a comment that the real sibling was "intentionally NOT recovered" — which masked an over-drop: the real method was fused into the same node and dropped with it. A drop guard whose test only checks the bad thing is gone never the good thing stayed cannot catch over-drop by construction.

**Rule — pair every absence assertion with a presence assertion on the same surface:**

- **Fan-out lanes.** When adding a fan-out lane beside a filtered query, grep every lane-dispatch site for the user-supplied filter args and assert they propagate (or that the lane is explicitly pruned from the filter contract). Add a regression test that a pinned filter yields ONLY the filtered class across the WHOLE fan-out, not just the seed lane. Reinforces enumerate-every-writer (Pre-Dispatch Verification § Investigation Funnel).
- **Drop / filter / dedup fixes.** Pair the negative assertion (junk absent) with a positive assertion (each legitimate neighbor still emitted, by exact identity/range — not just count). A reject fix's net that only counts what's gone never catches over-drop; what survives is half the contract.

Composes with §22 (leakage tests and coverage-floor goldens are complementary lenses — same shape at a different altitude) and §31 (tests must assert positively, not just survive).

## 71. Noisy-Suite Triage: Cumulative-Run, Don't Mass-Edit, Stub the Boundary, Watch Hook Contracts

*Source: holodeck L24 (2026-06-01), L28 (2026-06-01), L30 (2026-06-01); project-rag L175 (2026-06-02). [universal]*

**When a suite is noisy after a landed refactor, four discipline floors apply before any test edit lands:** run the WHOLE tier in one pass (per-cluster green ≠ full-tier green), don't mass-edit on "test rot" framing without per-cluster root-cause, stub the deterministic-subprocess boundary instead of growing timeouts, and make pytest hooks that force outcomes obey pytest's internal contracts.

**(a) Per-cluster green ≠ full-tier green; `--collect-only` is not enough.** Cluster-by-cluster fixes can each go green while the full non-slow tier hides count-assertion regressions, CI parity guards demanding a version-bump, and tests for retired features. *(holodeck, 2026-06-01: retire-layer-c — 6 clusters fixed green; full tier hid 12 failures including 3 stale probe-count constants and a `probe_registry_version` bump the parity guard correctly demanded.)* **Rule:** after any subsystem retirement / large refactor, run the whole tier in one pass before declaring closed; `--collect-only` catches `ImportError` (§56) but not count-assertion fossils (§55) or parity-guard reds. Extends §14 (cumulative-sweep validation).

**(b) "Test rot" is a hypothesis until per-cluster root-cause confirms it.** Mass-editing tests on inherited "test rot" framing buries the real source bugs the gates were catching. *(holodeck, 2026-06-01: a handoff called 77 TS failures "test rot"; per-cluster triage found ~1/3 were real — 11 implemented MCP actions missing from discoverability enums, caught by an enum-handler-sync guard.)* **Rule:** gate-shaped tests (enum sync, count parity, "X is NEW") exist to catch source drift; relaxing them on "test rot" framing hides exactly what they surface. Triage per cluster — separate real source bugs from genuine stale tests — before any mass edit. Composes with §60 (hand-traced refactor-equivalence is hypothesis).

**(c) Stub the deterministic-subprocess boundary; don't grow the timeout.** A test that spawns a real binary to read a deterministic fixture is both flaky and slow — under concurrent load, sporadic timeouts return None, fall back to a default, and the assertion never sees the bad value (12 silent "DID NOT RAISE" false-passes, invisible in isolation). *(holodeck, 2026-06-01: gpu_sidecar's config tests re-exec'd config.py spawning real `machine-local get` ~520× per file; stub `subprocess.run` on the subprocess module BEFORE `exec_module` reading the temp fixture directly cut runtime 219s→83s AND killed the flake.)* **Rule:** patch the external-process seam for tests reading deterministic fixtures; reserve real-subprocess tests for integration tiers. Direct application of §10 (mock at the helper boundary, not the stdlib boundary) to the deterministic-fixture-via-binary case.

**(d) `pytest_runtest_makereport` hooks that force `outcome="skipped"` MUST set `longrepr` to a `(path, lineno, reason)` 3-tuple, never a bare string.** A bare string crashes the WHOLE session with an INTERNALERROR (not just the one test), because pytest's verbose skip-reason path (`_get_raw_skip_reason`) does `assert isinstance(report.longrepr, tuple)`. *(project-rag, 2026-06-02: an addon-absent auto-skip hook set `report.longrepr = "Skipped: ..."`; CI-only failure because the hook fired only addon-absent; green-local / red-CI split.)* **Rule:** when forcing-skip in a makereport hook, build `report.longrepr = (item.location[0], (item.location[1] or 0) + 1, f"Skipped: {reason}")`. Verify with a standalone reproducer under `-v`, since the crash is an INTERNALERROR with no failing-test name to point at. Composes with §25 (`xfail` markers absorb test-infra exceptions silently — same shape: the hook layer eats signal the test layer should surface).
