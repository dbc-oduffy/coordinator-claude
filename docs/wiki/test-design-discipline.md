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

Async timing tests have too many yield-point escape hatches. A test that "blocks the event loop for >N ms" can be defeated by adding a single `await asyncio.sleep(0)` in the middle of a sync block, or by the test environment's clock resolution being too coarse to catch the regression.

**The robust shape is a source-level tripwire:** grep the async-handler code for `time.sleep`, blocking `requests.*` calls, sync `open()` of files above threshold, `subprocess.run` without `asyncio.to_thread`, etc. — fail at static-analysis time, not at flaky test-time.

Empirical timing tests are belt-and-suspenders, not the primary contract. If both exist, the timing test supplements the tripwire; it does not replace it.

**Generalizes:** for any property best stated structurally — no sync call inside async, no allocation in a hot loop, no global state in a pure function — the source-level grep IS the primary regression net. When you find yourself writing a timing-based or sampling-based probe to enforce a structural invariant, stop and ask whether a static grep on the production source would enforce the same invariant deterministically.

*Source: project-rag-ue-addon/tasks/lessons.md:116, 2026-05-16.*

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

## Skill Reference

`docs/wiki/test-driven-development.md` should cite items 1, 2, 3, 5, 8, 9, 10, and 11 in its preflight checklist when the planned change crosses a contract or refactors >3 files of similar shape.

## Related

- `docs/wiki/oom-reproducer-strategy.md` — multi-dimension assertions for fan-out OOM reproducers (RSS + commit count + concurrent-session count + wall-clock).
- `docs/wiki/round-trip-contract-tests.md` — producer/consumer schemas need round-trip tests, not parallel fabrications.
