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

## Skill Reference

`docs/wiki/test-driven-development.md` should cite items 1, 2, 3, 5, 8, 9, 10, and 11 in its preflight checklist when the planned change crosses a contract or refactors >3 files of similar shape.

## Related

- `docs/wiki/oom-reproducer-strategy.md` — multi-dimension assertions for fan-out OOM reproducers (RSS + commit count + concurrent-session count + wall-clock).
- `docs/wiki/round-trip-contract-tests.md` — producer/consumer schemas need round-trip tests, not parallel fabrications.
