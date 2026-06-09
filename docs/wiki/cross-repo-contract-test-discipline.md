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
   - **Pin line endings with an explicit `<path> text eol=lf` `.gitattributes` line — never rely on `* text=auto`.** A file whose whole purpose is byte-stability across repos will silently diverge under `autocrlf` if one repo has `* text=auto` (normalizes to CRLF on Windows checkout) and the sibling has no `text=auto` (stores raw LF). git only *warns* ("LF will be replaced by CRLF") — it never errors — so the drift is invisible. Pin `eol=lf` explicitly on every byte-equal fixture **and** on any text file a shell parses (a stray `\r` breaks shell-read manifests). Confirm with `git ls-files --eol <path>` showing `w/lf`. *(Canonical: 2026-05-26 — copying holodeck's shell-parsed `cross-repo-sync.manifest`; the `.manifest` extension fell only under `* text=auto` while holodeck (no `text=auto`) stored it LF, so the two copies would diverge on the next `autocrlf` checkout.)*
2. **Each repo's helper test reads the SAME fixture bytes** and asserts byte-equal output. Either serializer drifting from the contract fails loudly in that repo's CI, not via fluttering production files.
3. **A shape change forces simultaneous PRs in both repos** — because the fixture bytes change, both byte-equal assertions break until both helpers are updated and the fixture is re-pinned in both. That coupling is the point.
4. **Cross-repo fixture edits route via the `cross-repo-memo` CLI**, never direct writes to the sibling's surface — the memo carries the new fixture SHA so the partner re-pins. (See [`cross-repo-communication.md`](./cross-repo-communication.md).)
5. **Surface cross-copy drift as a startup notice.** The per-repo byte-equal test catches a serializer drifting from *its own* fixture copy; it does NOT catch the two fixture *copies* diverging when one repo updates its copy and the partner's is left stale. Close that seam with a daily byte-compare check — a `bin/check-fixture-sync.sh` (manifest-driven; sibling repo resolved from the machine-local registry, not a hardcoded `../sibling` path; skip-not-flag when the sibling isn't on this machine) wired into `/workday-start` via the `[ -x bin/check-fixture-sync.sh ]` guard. Advisory, never gating. Reference implementation: holodeck `bin/check-fixture-sync.sh` + `tests/fixtures/cross-repo-sync.manifest`.

### Anti-patterns

- **Matching specs instead of a shared fixture.** Two prose specs, or two test suites with hand-authored "equivalent" cases, drift silently. This is the cross-repo-writer analogue of `round-trip-contract-tests.md`'s "fabricated-on-each-side fixtures lie."
- **Documenting the contract in a memo or wiki only.** A memo is a snapshot; it does not fail when a serializer drifts. The executable fixture is the contract; the memo announces a fixture change.
- **Asserting structural/semantic equality instead of byte equality.** Co-writers alternate on the same file; semantic-equal-but-byte-different output produces the fluttering-content symptom. Assert bytes.

## Roadmap-Stub Schemas Are Speculative Until Grounded — Two Specs Agreeing Is Not Corroboration

**Provenance:** 2026-05-26 (project-rag-ue-addon tc-26; ragaddon delta L414/L322).

A schema written into a roadmap stub, spinoff AC, or planning doc is **speculative until grounded against the real on-disk schema in the owning repo.** Before ratifying such a schema into a cross-repo contract — or dispatching an executor against it — grep the actual table/record shape on the owning repo's disk.

### Failure shape

A sibling EM asked to pin an edge-record schema; the receiving repo's own roadmap stub *agreed* with the proposal. But both had invented a 6-field `cross_layer_edges` shape (`target_band`, `resolution_confidence`, …) that matched **neither** the real host-owned table (`source_layer` / `target_layer` / `confidence` / `confidence_tier`, no `CHECK` on `edge_type` since v11) **nor the ownership boundary** (the table is frozen / core-owned; addons add edge *types* via hookspec, not *columns*).

**Two independently-authored specs agreeing is not corroboration when both are speculative — it can be shared fiction.** Convergence between your stub and a peer's ask is only evidence if at least one was grounded against disk. The "convergence as confidence" heuristic (≥2 independent agents) requires *independent grounding*, not two paraphrases of the same un-checked assumption.

### Rule

1. **Grep the real schema on the owning repo's disk** before using a stub schema as the basis for a cross-repo answer or an executor dispatch — DDL, migration files, the live table.
2. **Confirm the ownership boundary**, not just the field list. A frozen/core-owned table extended via hookspec (addons add *types*, not *columns*) is a different contract than "add fields here."
3. **Treat stub schemas authored days earlier as obsolete-until-proven-live.** Roadmap stubs authored before a migration describe a world that may no longer exist; re-ground at pickup. → CLAUDE.md § Pre-Dispatch Verification (no-fabrication on cited fields); `cross-repo-handshake-doctrine.md` (the contract-as-hypothesis handshake).

This extends the cross-repo-contract-is-hypothesis rule (`cross-repo-communication.md`) to the **our-own-stub** entry point: the hypothesis to distrust is not only the *inbound* memo's framing but also *your own* prior planning artifact's schema.

## Field-Ownership Check Before Treating Absence as Defect

**A reviewer "missing field" finding can invert once you check field ownership — grep who computes and who consumes a field across the seam before adding a producer-side emit.**

Absence of a *consumer-owned* field at the producer is often correct, not a gap; the producer emitting it is the redundant anti-pattern that may be silently overwritten. Before treating an absent field across a cross-repo seam as a defect:

1. Grep the consumer side for who *computes* the field (e.g., `indexer/embed.py` overwriting a producer value with its own hash).
2. Grep the producer side for any existing emit of the same field.
3. If the consumer computes it unconditionally at index time, the producer should NOT emit it — omission is correct.

Sibling to the cross-repo-contract-is-hypothesis rule in `cross-repo-communication.md`, applied to review-finding direction.

## Seam Transform Ownership and Idempotency

**A format or identity transform on a cross-component seam must pin which side owns the transform AND must be idempotent — otherwise it green-tests on both sides and fails only at integration.**

If both producer and consumer apply the same transform (e.g., dot-to-underscore token normalization), the result is double-applied corruption. If neither applies it, the key is unaddressable. The failure is invisible until integration because each side's unit tests pass against their own convention.

**Rule:** ONE side owns the transform; that ownership decision is pinned explicitly in the plan, the cross-repo memo, and an idempotency test before integration. The transform implementation must tolerate already-transformed input (`replace('.', '_')` on an already-underscore token is a no-op). The contract must state which caller-shape the producing side accepts ("you pass dotted, I own the token shape").

Anti-pattern: two independent implementations of the same normalization step with no contract pinning which one wins.

## Schema-Extension Seams: Version Handshake + Boundary-Crossing Parity Test

**Provenance:** 2026-05-28, project-rag-ue-addon — **two independent architecture audits the same day** converged on this class from different entry points (doctor-command-surface audit, DSR-2026-05-27-3; addon-pluggy audit, the "silent-subtraction family"). Convergence-as-confidence: a confirmed structural theme, not a one-off.

The paired-writer rule above covers **symmetric co-writers** (two repos emitting the *same* artifact). This section covers the **asymmetric extension** shape: an **addon extends a host's schema** — adding addon-only optional fields atop a row/record/manifest shape the host owns. This is the default shape of any host/addon plugin architecture (→ `authoring-an-addon.md`, `host-vs-addons.md`, `addon-protocol.md`).

### Failure shape

The addon builds a rigorous *internal* contract (declarative SSOT, parity-tested within its own repo) and then **bolts it onto the host contract with no version handshake and no test that crosses the repo boundary.** Two concrete instances, same week, same repo:

- **Doctor probe manifest.** The addon's `doctor-probes.toml` adds `tier`/`depth` axes to the host's probe-row shape. Neither side carries a `manifest_schema_version`. The addon's seam test asserts `schema_version == 1` against a **local constant** — it never imports the host's authoritative version constant. A host-side schema evolution trips no addon test; an addon drift trips no host test. The contract is unenforced in **both** directions while reading green.
- **Pluggy hookimpl surface.** Addon couples to host internals (hookimpl signatures, private host symbols, `host_state`) with no cross-repo compat guard — a host evolution can make addon capability silently vanish with only a `log.warning`.

The within-repo SSOT can be airtight while the *between-repo* contract has zero enforcement. The internal rigor masks the external gap — green internal tests read as "the contract is tested."

### Rule

For any seam where an addon extends a host-owned schema:

1. **A version field crosses the seam.** The host's schema shape carries a `manifest_schema_version` (or named constant); the addon mirrors and asserts it. No version field = no way to detect the host moved on. (This is the schema-shaped instance of the self-documenting-sentinel rule in [`cross-repo-handshake-doctrine.md`](./cross-repo-handshake-doctrine.md) — the version *is* the staleness check.)
2. **The parity test imports the host's constant — it does not assert a local literal.** A test asserting `== 1` against an in-repo copy is the same green-by-skip / fabricated-counterpart failure named at the top of this page: it passes when nothing crossed the boundary. The host **owns** the constant; it must expose a stable importable name; the addon's test imports and compares it.
3. **Both halves fail loud on drift.** Host-side reciprocal test (host manifest version == host constant) + addon-side parity test (addon assertion imports host constant). A shape change then forces simultaneous attention on both sides — the coupling is the point, as with the byte-equal fixture above.
4. **Confirm the ownership boundary, not just the field list** (→ the roadmap-stub rule above): an addon extends the host schema with addon-only *fields/types via the documented extension surface* (hookspec, optional columns the host tolerates), never by editing the host's frozen shape. The host owns the version; the addon owns its extension.
5. **The cross-repo half routes via `cross-repo-memo` + PM relay**, never a direct edit to the host's schema/TOML/constant. The addon adds its own version field and rewrites its own test unilaterally; the host-owned constant and reciprocal test are the host EM's landing.

### Anti-patterns

- **Local-constant assertion masquerading as a cross-repo guard.** `assert payload["schema_version"] == 1` against an in-repo literal — never imports the host. Decorative.
- **No version field at all on an extended schema.** "It's just optional fields" — until the host's required shape shifts under the addon and nothing fails.
- **Trusting internal SSOT rigor to cover the external seam.** A within-repo parity test (regenerate == committed) is necessary but says nothing about host alignment.

## Verbatim-on-Contract Lift Discipline — Flag Bugs Bidirectionally, Don't Patch Unilaterally

**When a cross-repo lift is verbatim-on-contract, findings split by origin: source-bugs flag back via memo, lift-bugs fix here. Never patch unilaterally and move on.**

If the code being lifted verbatim has a real bug (e.g., a counting error in `_classify_two_way` where `counts.unchanged` is inflated), that bug exists in the source repo too. The temptation is to fix our copy and consider it done. This is wrong: it silently erodes the "verbatim" framing — the next lift finds diverged code, can't trust the verbatim contract, and either re-derives the divergence or re-introduces the bug.

**How to apply:**

1. **Sort findings by origin** at review time: *exists verbatim in source* vs. *introduced by the lift itself*.
2. **Source-bugs:** fix in our copy AND send a `cross-repo-memo` to the source-repo EM naming the bug and fix. The contract surfaces (exit codes, JSON schema, CLI flags) are the things that must stay aligned; internal logic is implementation that EITHER side can fix first, but BOTH should land it.
3. **Lift-bugs:** fix here only — these don't exist upstream.
4. **Re-lift if the source EM confirms their fix** — bringing both sides back to a shared verbatim baseline.

**The unifying principle:** a verbatim lift is a contract — deviating from it silently, in either direction, turns a single source of truth into two diverging implementations that nobody can compare reliably. The memo is the mechanism that keeps the contract alive across time.

*Source: 2026-05-28 install-divergence lift; code-reviewer (F1) surfaced a counting bug verbatim in both repos; flagged via cross-repo-memo rather than patching unilaterally.*

## version constants symbolic — parity test is the structural drift defense

Version constants are symbolic — pinning a version integer is not the same as defending against drift. The load-bearing tripwire is a parity test that asserts the constant matches reality at test time (e.g., `assert SCHEMA_VERSION == get_live_schema_version()`). Don't call drift defended after pinning a constant without a parity test that cross-checks it against the actual runtime state.

## Cross-references

- [`cross-repo-communication.md`](./cross-repo-communication.md) — memo framing (fix-locus, fix-shape, field ownership) is hypothesis; the inbound-memo analogue of the our-own-stub rule above.
- [`round-trip-contract-tests.md`](./round-trip-contract-tests.md) — partner-tool integration section: ship the mixed result; workarounds hide the bugs the test was meant to surface. §"Where the Test Lives" (fabricated-on-each-side fixtures lie) is the producer/consumer analogue of the paired-writer rule above.
- [`test-design-discipline.md`](./test-design-discipline.md) — skip-semantics, marker discipline, CI lane composition.
- [`verification-before-completion.md`](./verification-before-completion.md) — "green CI" is not "shipped working" when the green came from skips.
