# Cross-Repo Contract Test Discipline

**Provenance:** 2026-05-14 from `project-rag` central improvement queue (PR-W1c contract-test green-by-skip incident).

A contract test that `skip`s when its prerequisite is absent is a no-op in every CI lane that lacks the prerequisite. The test only earns its keep when **≥1 CI matrix entry has the prerequisite installed AND the test runs (not skips) in that lane**. Without that lane, the test is decorative — green-by-skip is indistinguishable from green-by-pass.

## Failure Shape

`project-rag` PR-W1c shipped `test_phase4_addon_install_contract` to assert the addon registered the expected `hookimpl` ID-set after install. The test skipped when the addon package wasn't importable from the test venv — which was every CI lane. It "passed" green for 6 days while the addon's `mcp_server*` packaging was silently broken. The break only surfaced when a human ran verification on a hand-built venv with the addon actually installed.

Compounding antipattern: the addon's loader wrapped `hookimpl` registration in fail-soft `try/except ImportError`. The contract test's only assertion was "registration didn't raise" — which silently became "registration was skipped" and still returned green. Install-validation must assert the **exact registered ID-set**, not the absence of an exception.

## Rule

For any prerequisite-gated contract test:

1. **Name the prerequisite** in a marker or skip reason — e.g. `@pytest.mark.requires_addon("mcp_server")`.
2. **Declare a CI matrix lane** that installs it. Lane defined alongside the test, same PR.
3. **In that lane, skipping is failure.** Assert the test is collected as `passed`, not `skipped`. CI reports skipped-where-required as red.
4. **Assert the positive contract.** Compare registered ID-set against expected ID-set; never gate on `try/except` silence.

A contract test without a matrix entry that runs it green is epistemically equivalent to a deleted test.

## Anti-patterns

- **Skip-as-pass.** `pytest.skip()` on missing prerequisite with no lane that installs it.
- **Fail-soft `ImportError` in the producer.** Install-time registration that catches `ImportError` and proceeds — turns missing install into silent partial install. Let it raise.
- **Asserting "didn't raise" instead of "registered exactly this set."** Negative assertions pass when nothing ran.
- **Single-lane CI on cross-repo integration.** Partner artifact prerequisites need `with-partner` and `without-partner` lanes.

## Paired Cross-Repo Writers: Pin a Shared Byte-Equal Fixture

**Provenance:** 2026-05-21 `unreal.*` concern-file migration; convention named 2026-05-26 (holodeck `cross-repo-helper-fixture` spinoff).

The discipline above covers prerequisite-gated tests. This section covers a distinct shape: **two repos that each independently WRITE the same artifact** — symmetric co-writers, not producer/consumer. Examples: two install helpers that both read-merge-write the same per-machine config file; structural-schema constant mirrors; any pair of memo-channel or install-contract writers that must emit identical output.

### Failure shape

`holodeck` (`scripts/lib/write_unreal_concern.py`) and `project-rag-ue-addon` (`_seed_unreal_keys.py`) both co-write `~/.claude/machine-local/unreal.local.toml` via read-merge-write. The initial cross-repo design kept them in parity by **matching prose spec + matching test cases authored on each side**. That is empirically inadequate: two test suites in two repos decay independently under refactor pressure. One side adds a sort-keys pass, the other doesn't, the serialized output drifts — and the symptom is **fluttering file content on every setup alternation, not a clean test failure**. Prose-spec parity decays at refactor velocity, and nothing fails loud.

### Rule

The contract surface between paired cross-repo writers must be **an artifact both repos test against — not a memo, not a shared wiki page, not matching-but-separate fixtures.**

1. **Pin one byte-equal fixture**, committed byte-identical in both repos — e.g. `tests/fixtures/<helper>_contract.json`, a list of `{inputs, expected_output_bytes}` tuples (base64 the bytes so the assertion is exact, including trailing newlines and quote style).
2. **Each repo's helper test reads the SAME fixture bytes** and asserts byte-equal output. Either serializer drifting from the contract fails loudly in that repo's CI, not via fluttering production files.
3. **A shape change forces simultaneous PRs in both repos** — because the fixture bytes change, both byte-equal assertions break until both helpers are updated and the fixture is re-pinned in both. That coupling is the point.
4. **Cross-repo fixture edits route via the `cross-repo-memo` CLI**, never direct writes to the sibling's surface — the memo carries the new fixture SHA so the partner re-pins. (See [`cross-repo-communication.md`](./cross-repo-communication.md).)
5. **Surface cross-copy drift as a startup notice.** The per-repo byte-equal test catches a serializer drifting from *its own* fixture copy; it does NOT catch the two fixture *copies* diverging when one repo updates its copy and the partner's is left stale. Close that seam with a daily byte-compare check — a `bin/check-fixture-sync.sh` (manifest-driven; sibling repo resolved from the machine-local registry, not a hardcoded `../sibling` path; skip-not-flag when the sibling isn't on this machine) wired into `/workday-start` via the `[ -x bin/check-fixture-sync.sh ]` guard. Advisory, never gating. Reference implementation: holodeck `bin/check-fixture-sync.sh` + `tests/fixtures/cross-repo-sync.manifest`.

### Anti-patterns

- **Matching specs instead of a shared fixture.** Two prose specs, or two test suites with hand-authored "equivalent" cases, drift silently. This is the cross-repo-writer analogue of `round-trip-contract-tests.md`'s "fabricated-on-each-side fixtures lie."
- **Documenting the contract in a memo or wiki only.** A memo is a snapshot; it does not fail when a serializer drifts. The executable fixture is the contract; the memo announces a fixture change.
- **Asserting structural/semantic equality instead of byte equality.** Co-writers alternate on the same file; semantic-equal-but-byte-different output produces the fluttering-content symptom. Assert bytes.

## Cross-references

- [`round-trip-contract-tests.md`](./round-trip-contract-tests.md) — partner-tool integration section: ship the mixed result; workarounds hide the bugs the test was meant to surface. §"Where the Test Lives" (fabricated-on-each-side fixtures lie) is the producer/consumer analogue of the paired-writer rule above.
- [`test-design-discipline.md`](./test-design-discipline.md) — skip-semantics, marker discipline, CI lane composition.
- [`verification-before-completion.md`](./verification-before-completion.md) — "green CI" is not "shipped working" when the green came from skips.
