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

## Cross-references

- [`round-trip-contract-tests.md`](./round-trip-contract-tests.md) — partner-tool integration section: ship the mixed result; workarounds hide the bugs the test was meant to surface.
- [`test-design-discipline.md`](./test-design-discipline.md) — skip-semantics, marker discipline, CI lane composition.
- [`verification-before-completion.md`](./verification-before-completion.md) — "green CI" is not "shipped working" when the green came from skips.
