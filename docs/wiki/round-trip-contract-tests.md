# Round-Trip Contract Tests

**Provenance:** consolidated 2026-05-05 from `tasks/lesson-triage-2026-05-05/SYNTHESIS.md` §B5.

When a pipeline has separate producers and consumers writing/reading the same on-disk artifact, **at least one test must run the real producer feeding the real consumer**. Tests that fabricate the schema inline on each side hide drift indefinitely.

## The Failure Mode

A RAG indexer's lite/clang producers wrote a `symbols` table without `module` / `line_end` / `decl_text` columns; consumers (`cpp_chunker`, `extractor.extract_cpp`, `live.py`) queried those columns. CI passed because every consumer test built its own rich-schema fixture inline. The mismatch only surfaced when a game project ran a clean reindex — the first time the in-tree producers' real DDL met the real consumers' real SQL.

The shape recurs:

- A 2,091-LOC ported producer script's `INSERT` statements were silently rolled back in a worker exception handler because A2 enrichment dropped columns the script still wrote — yielding 0 symbols across every clang TU.
- A FastAPI `.venv` lacking `fastapi`/`uvicorn`/`pip` survived 379 unit tests because tests imported submodules directly; the gap surfaced only when something tried to start the runtime over HTTP.

The common cause: tests prove the parts work in isolation. They don't prove the parts wire together at the seams the runtime actually exercises.

## The Rule

For any producer → on-disk-artifact → consumer pipeline:

1. Write a contract test that runs the **real producer** end-to-end.
2. Open the producer's emitted artifact and assert its schema matches what every consumer queries.
3. Run **≥1 consumer end-to-end** against that producer's output.

Add the test when a new producer or consumer lands. Don't defer to "we'll add it when we hit a bug" — by then the bug has shipped to a downstream consumer.

## Port-Time DDL Floor

When porting a producer script that writes via hardcoded `INSERT`s, the receiving DDL must include every column and every table the script touches — even if no consumer reads them today.

Drop columns ONLY by editing the script's `INSERT`s in the same chunk. Otherwise the column survives the "drop" decision because the script still writes to it, the DDL doesn't have it, and every write rolls back.

The minimalist read-side analysis ("no consumer reads this") is correct in isolation but wrong as a port-time decision. **Port-time DDL = grep the script for every `INSERT` and `CREATE TABLE`. That's the floor.** Schema minimalism comes later, after a consumer actually reads (or fails to read) a column, and always co-edits the writer in the same change.

## HTTP Apps: Smoke-Test the Boot Path

For any FastAPI/uvicorn-shaped service, include at least one smoke test that does:

```python
from <pkg>.app import app
# optionally:
TestClient(app).get("/health")
```

This proves the app at least imports and the boot path is reachable. Tests that exercise registry/lock/lease internals via direct submodule imports can pass while the top-level `from fastapi import ...` in `app.py` would fail (e.g. fastapi missing from the venv). Cheap to add, immediate signal on environment drift.

## Stdio Loops: EOF Is Empty-String, Not None

Python `file.readline()` and similar stdio readers return empty-string `''` to signal EOF, NOT `None`. Round-trip stdio client loops that check `if line is None: break` busy-loop forever on closed pipes — check `if not line: break` (truthiness). Same shape recurs in any language whose stdio API distinguishes "empty line" from "stream closed" by returning a falsy non-`None` sentinel.

## Where the Test Lives

- **Producer-side test directory** if the producer owns the schema authoritatively.
- **Consumer-side test directory** if the consumer's read shape is what's drifting.
- **Either** is fine — the rule is that *one* such test must exist on the contract, not that it must live in a specific place. What's not fine is fabricated-on-each-side fixtures with no integration seam.

## Spike Acceptance: Registration Is Not Initialization

> See `docs/wiki/writing-plans.md` § "Spike Pass-Conditions Must Match the Wire Path" for the plan-authoring corollary.

A spike whose goal is "does X work end-to-end" must verify the **runtime wire path**, not just structural registration. The round-trip failure mode applies to spike ACs just as it applies to contract tests:

- **Registration ≠ initialization.** A module can be registered in a plugin registry while failing to initialize at runtime (missing deps, wrong boot order, missing env bindings).
- **Build success ≠ runtime reachability.** A header that compiles successfully may still be unreachable via the call path the spike claims to verify.

The spike's pass-condition is a contract test in miniature: it must exercise the real producer feeding the real consumer. If the pass-condition can return green while the runtime surface is broken, it is measuring the wrong seam.

## Partner-Tool Integration Tests: Ship the Mixed Result

When running an integration test on a partner team's release (peer-repo dogfood, cross-org API integration, vendor SDK validation), **producer/consumer failures ARE the deliverable**. Workarounds (installing missing tools manually, hand-editing configs, skipping producers, mocking around the broken path) **hide the bugs the test is meant to surface** — and the green-with-workarounds result is structurally worse than the failed run, because it ships false confidence back to the partner.

**The 2026-05-01 project-rag v0.1.1 reindex** left the graph DB essentially empty. Sending the producer ledger + 10 findings A–J back to the partner team was more valuable than a green run that masked broken consumers. The mixed-result data is the contract evidence; manufactured green is fabrication.

**Rule for partner-tool integration runs:**

1. **Ship the mixed-result data.** Don't try to "make it work" by patching around partner bugs.
2. **Capture the failure shape verbatim:** exit codes, stderr, partial outputs, environment state. This is what the partner needs to fix forward.
3. **Refuse the workaround temptation.** "I'll install the missing dep manually and re-run" defeats the test's purpose — the missing dep IS the bug.
4. **Surface as cross-repo finding,** not as in-tree fix unless the partner explicitly hands ownership across.

Same shape applies to cross-team release validation, API integration smoke tests, and peer-repo `/dogfood` runs. The discipline is **don't hide failures, surface them** — companion principle to the round-trip-contract-tests rule that fabricated-on-each-side fixtures lie. A workaround that hides a partner bug is the cross-repo analogue of a parallel fabricated fixture.

## Polyglot Workstreams Need Per-Language Compile+Test Gates

When a workstream spans multiple language runtimes (TS + C++, Python + Rust, Go + JS), the shipping criterion is **per-language** compile + test green, not "the workstream passes." Single-language validation — running only the test runner of the language whose code changed last — is a process bug. The cross-language seam is where the round-trip contract lives, and a one-sided green is no signal about the seam.

**Concrete shape:** a example-game-repo-style workstream that edits TS bridge code AND C++ UE plugin code must (1) compile the TS, (2) compile the C++ via UBT, (3) run the TS unit tests, (4) run the UE editor smoke or equivalent C++ test gate, and (5) round-trip at least one TS→C++→TS message to prove the bridge survived both edits. Skipping any one of these and asserting "the workstream is green" ships a half-validated change.

Per-language gates compose with the round-trip contract test rule above: the round-trip test exercises the seam; the per-language gates prove each side can build at all. Both are required; neither substitutes for the other.

## Golden-Snapshot Identifier Normalization

A golden-snapshot test that inlines file content captures per-install identifiers (40-char hex SHAs, PIDs, install-id UUIDs, floating-point timing) verbatim. Every commit between capture and run breaks the test with a one-character diff even though the assertion the test is *trying* to make is "this file has the expected shape," not "this file contains exactly this SHA."

**Rule:** round-trip contract tests that rely on golden snapshots must run inputs through an identifier normalizer before comparison:
- 40-char hex SHA → `__GIT_SHA__` (regex: `\b[0-9a-f]{40}\b`)
- PID shapes → `__PID__`
- ISO-8601 timestamps → `__TIMESTAMP__`
- UUID4 → `__UUID__`
- Floating-point timing values → `__DURATION__`

Maintain an **excluded-paths list** for log/transient directories that the snapshot should not attempt to compare at all — consume the exclusions at the glob layer, not the per-line layer.

The normalizer itself must be test-covered: feed in real CI outputs and assert that two captures from different installs produce byte-identical normalized output. A snapshot suite without this self-test silently re-introduces flake every time install infrastructure adds a new per-install identifier.

→ Full concrete failure and composition rules: `docs/wiki/test-design-discipline.md` §19.

## Auto-Registration Macros and Framework-Prefix Encoding Drift

Macros that auto-register types by stringifying their names also stringify any framework prefixes attached to the type (e.g. `UCLASS` prefixes, `T`/`F`/`U` naming conventions). A round-trip test that asserts "registered name equals expected string" will fail when the macro-stringified name includes the prefix but the expected string was hand-written without it — or vice versa.

**Rule:** strip or alias both the bare type name *and* the framework-prefixed form in any round-trip assertion over auto-registered names. The encoding drift is only visible at execution time — a shape test that compares compile-time constants against each other will not catch it.

Corollary: when debugging auto-registration round-trip failures, always print the raw stringified name before asserting — the drift is almost always a prefix/suffix encoding difference, not a logic error.

## A False-Passing Gate Is Worse Than No Gate — Reuse the Canonical Parser, Run Against the Real Artifact

*Recurs: L319, example-game-repo-L5. [universal]*

A new gate or parser that consumes a shared config format (machine-local registry, BOM-prefixed file, manifest, on-disk schema) can pass **41 fixture tests and still return a vacuous "all clean exit 0" against the real artifact** — because fixtures don't reproduce the format's accumulated variform reality. A vacuous all-clear gate is the worst outcome: it ships confidence with zero coverage.

**Concrete failure (example-game-repo-L5).** `bin/check-reverse-drift.sh` passed all fixture tests but no-op'd against the real registry — three bugs: unstripped CRLF → installed plugins read as false `[missing]`; `IFS=$'\t'` whitespace-collapse → empty field shifted the next field into the wrong slot; mixed-slash Windows path → `-d` existence check failed. Coordinator's `check-plugin-drift.py` had **already solved all three** (tomllib both-key-shapes, `| tr -d '\r'`, `${path//\\//}`, pipe delimiter) — the new gate hand-rolled a regex/tab variant and re-introduced every bug.

**Rule.** A new consumer of a shared format MUST:
1. **Reuse the canonical sibling parser verbatim** — don't hand-roll a regex/tab/split variant. The canonical parser has absorbed the format's real-world variance (CRLF, both TOML key-shapes, backslash paths, BOM); a fresh re-implementation re-discovers each one as a production bug.
2. **Run once against the REAL artifact** before trusting green fixtures. Fixtures are the floor; the real artifact is the verdict.

This is the parser/gate analogue of the producer→consumer round-trip rule: fabricated-on-each-side fixtures lie, and a re-implemented parser tested only against its own fixtures is testing the re-impl against itself (test-design §16, "real-shell for real-shell semantics").

## Refactoring a Resolution Seam Breaks Tests That Mock the Old Seam — Re-Mock at the New Boundary

*Recurs: L313, example-game-repo-L879. [universal]*

A mock pins the call shape at one boundary. Moving the boundary — routing resolution *upstream* of invocation — makes the old mock match nothing, and a fall-through default branch usually reads as success. The failure is invisible: the test still "passes," wrongly, or passes for the wrong reason.

**Concrete failure (example-game-repo-L879).** A probe-helpers refactor routed `subprocess.run([name, ...])` through a `shutil.which`-first kit, changing `cmd[0]` from the bare name to a resolved abspath. Every test that mocked `subprocess.run` and keyed on `cmd[0] == "node"` / `"tasklist"` / `"machine-local"` **silently fell through to its default branch → false PASS** (an "absent" test saw success). Hit 5 separate test files identically.

**Rule.** When a refactor *moves* a resolution seam, the test mocks must move with it — **re-mock at the new boundary**, don't trust green-on-old-mocks. The regression-net-before-refactor principle (test-design §5) assumes the net is wired to the seam under test; when the refactor moves the seam, the net is now wired to nothing. Greppable trigger: a refactor that changes what a downstream mock keys on (`cmd[0]`, a resolved path, a normalized identifier) → grep every mock of that boundary and verify it still matches the new call shape. Composes with test-design §10 (mock at the helper boundary, not the stdlib boundary) — both are "the mock doesn't intercept what the code actually calls."

## Root-Resolution Is a Round-Trip Contract: Reader and Writer Must Resolve Location Identically

**An idempotency/dedup scan must resolve its target root the SAME way the write seam does — otherwise the "did I already write this?" read looks in the wrong place and silently double-writes.** A dedup read that resolves its scan directory from process cwd (`git rev-parse`) while the write seam honors a test-isolation env override (e.g. `QUEUE_APPEND_OUTPUT_ROOT`) will double-write under any invocation where `cwd != the override root`. Production cwd-coincidence masks the divergence — the two roots happen to agree until an isolated call trips them apart.

**Rule:** the scan must mirror the write seam's OWN root-resolution precedence — env-override first, then git/`DOE_ROOT` fallback — not re-derive location from cwd. Reader and writer resolving location identically is the same round-trip contract as producer and consumer agreeing on schema: a divergence at the *location* seam is as silent as a divergence at the *column* seam, and cwd-coincidence hides it exactly the way inline fixtures hide schema drift.

*Caught by C7 on coordinator-harvest-deferrals.*

## Green Tests ≠ Runtime-Readiness

A green test suite is not proof a change actually works end-to-end — three distinct ways this
lies:

- **Concurrent sweeps silently overwrite edits.** On a shared branch, verify via `git log -p`
  against the actual commit, not chat transcript claims of what was applied.
- **Tool self-health checks lie.** A tool reporting its own "OK" status is not the same evidence
  as a round-trip test exercising the real producer/consumer seam — see the schema-drift and
  boot-path failure modes above.
- **Smoke tests prove dispatch, not useful results.** A smoke test that confirms a call was made
  and returned *something* is not the same claim as "the something was correct" — see § HTTP
  Apps above for the boot-path-only version of this gap.

Never mark complete without proving it works — run tests, check logs, verify agent output
(empty/truncated/format) — the reflex this whole doctrine wiki exists to reinforce.

## Reference Pattern: `coordinator:plan` skill Checklist

When drafting a plan that introduces a new producer or consumer to an existing on-disk-artifact pipeline, the plan must name the round-trip contract test explicitly — not as a follow-up. If it isn't named in the plan, executors won't add it, and CI green will keep lying.
