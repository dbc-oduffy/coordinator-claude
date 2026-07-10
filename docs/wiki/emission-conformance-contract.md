---
title: Emission Conformance Contract
status: active
kind: doctrine-wiki
created: 2026-07-04
spec-backlink: docs/plans/2026-07-04-doe-emission-conformance-fixture.md
---

# Emission Conformance Contract

> Normative shared contract for the DoE-hosted emission-conformance fixture. Coordinator keeps the
> fixture current on HEAD; example-orchestration-hub's DR-210 strangler drift-check (strang-02) and any other consumer
> conform against it. This doc codifies the three contract decisions (CD-1/CD-2/CD-3) the fixture
> answers — fixture path, version semantics + freshness protocol, and emitter reachability — plus the
> shared provenance-normalization oracle (AC5-PROVENANCE) that makes the conformance compare
> deterministic across stateful emitter output.

<!-- spec-backlink: docs/plans/2026-07-04-doe-emission-conformance-fixture.md § CD-1/CD-2/CD-3 -->
<!-- ratification: cross-repo/archive/2026-07-04-example-orchestration-hub-strangler-emission-fixture-and-fallback.md -->

---

## Purpose

The coordinator cockpit-contract tc3 emitter (example-orchestration-hub's Python `artifact.emit`, the sole
production emitter as of DR-208/DR-210 — `coordinator/bin/emit-cockpit-snapshot.sh` is now a
fail-loud facade stub, see § Reachability Contract) and `append-goal-event.sh` produce structured
NDJSON cockpit records covering every entity class (handoff-summary, backlog-item-summary,
review-trail, routine-signal, completion-rollup, goal). The **contract SSOT stays DoE-side**; each
consumer repo owns its language-specific validator.

This doc is the shared normative surface every consumer validator conforms against. It answers
three questions strang-02 needs resolved before it can build:

1. **Where is the fixture** and how does its schema version travel with it? (CD-1)
2. **How does a consumer know the fixture is current** without going blind to DoE-HEAD drift? (CD-2)
3. **Is the emission path reachable** through and after the W4.2 plugin-source cutover, and what
   happens when the example-orchestration-hub control plane is absent? (CD-3)

This fixture is **instance #2** of the Step Zero NDJSON conformance pattern
(`coordinator/docs/wiki/step-zero-emitter-contract.md`): same five-part shape (fixture + generator
+ drift-runner + contract-doc + ratifying-memo). It differs on the **determinism axis**: the
step-zero emitter is a pure function (zero runtime-varying fields; byte-equality is a complete
oracle). The cockpit emitter is stateful — it stamps wall-clock, host, git SHA, and a hardcoded
`REPO_NAME` into every record. The conformance oracle is therefore **NORMALIZE-then-compare, not
raw byte-compare** (see § AC5-PROVENANCE). The generator is also placed at `coordinator/bin/`
(a plugin-load PATH surface) rather than `tests/fixtures/` — intentional per the CD-1
schema-package version-lock rationale.

---

## The Fixture as Single Normative Authority (CD-1)

`coordinator/cockpit-contract/conformance/emission-conformance.json` is the **single normative
authority** for the emission contract. It lives inside the contract SSOT package
(`coordinator/cockpit-contract/`, alongside `schema/`, `fixtures/`, `dist/`). This placement
version-locks the fixture to the schema in the same package: a schema bump and a fixture regen
ride the same commit, making staleness detectable rather than silently divergent.

The generator (`coordinator/bin/gen-emission-conformance.sh`) is the only sanctioned path to
authoring the fixture. Hand-edits to `emission-conformance.json` are forbidden — changes go
through the generator, a reviewed diff, and a `contract_version` bump on intentional contract
change.

The fixture is a **round-trip over full C2 entity coverage**: handoff-summary, backlog-item-summary,
review-trail, routine-signal, completion-rollup, goal — every entity class the emitter produces.
→ `docs/wiki/round-trip-contract-tests.md` for the round-trip fixture discipline.

---

## Version Semantics and Versioning Policy (CD-2)

### Two-field version stamp

The fixture body carries two top-level version fields:

| Field | Source | Meaning |
|---|---|---|
| `contract_version` | Schema `version` field in `coordinator/cockpit-contract/schema/cockpit-contract.schema.json` | The current HEAD contract version at fixture-generation time. |
| `min_supported_contract_version` | DoE-maintained trailing floor | The oldest pinned version a consumer may hold without a re-vendor demand. |

Both fields are strings in SemVer form (e.g. `"2.5.0"`).

**Two-axis note** (`docs/wiki/schema-version-gate.md`): `contract_version` tracks the
**contract/schema version** (the shape of emitted records), not a data-format or fixture-format
version. Consumers key their staleness compare on `contract_version` — not on the fixture file's
own byte identity or a sha of the fixture blob.

### Gate semantics — MIN_SUPPORTED band, not equality-fail-loud

The staleness gate is:

```
pinned_version >= min_supported_contract_version   →  PASS (re-vendor advisory only)
pinned_version  < min_supported_contract_version   →  FAIL LOUD (re-vendor required)
```

**Equality-fail-loud (`pinned != contract_version`) is architecturally incompatible with
reader-first** by construction: example-orchestration-hub is behind the instant DoE bumps HEAD. Any consumer would
fail continuously and uselessly. The MIN_SUPPORTED band is the machine-consumable mechanism for
this — it gives consumers a re-vendor window before the gate trips. → `docs/wiki/schema-version-gate.md`
§ Two-axis version gate and § Reader-first bump ordering.

### Versioning policy — re-vendor window discipline

During a re-vendor window:

1. DoE advances `contract_version` (and advances the dedicated freshness ref — see § Dedicated-Ref
   Freshness Protocol below) in the same commit that regenerates the fixture.
2. DoE leaves `min_supported_contract_version` **trailing** — it does NOT move on the same commit
   as `contract_version`.
3. DoE MUST announce a re-vendor window to consumers before raising `min_supported_contract_version`.
4. Only after the window closes (consumers have had time to re-vendor) does DoE raise
   `min_supported_contract_version` to match `contract_version`.

**DoE MUST NOT raise `min_supported_contract_version` without a named re-vendor window and
sufficient advance notice.** Raising it silently would trip the gate on a still-current consumer
pin without warning.

---

## Dedicated-Ref Freshness Protocol (CD-2 / AC8)

### Why a pure local-clone read is insufficient

A consumer that reads the fixture body from its local DoE clone only — without a freshness signal
— may compare against a stale contract if the local clone is behind origin. This is the blindness
`§ EM-Response-2a` in the accepted memo forbade: byte-identical against an out-of-date fixture
reads as PASS when the contract has already advanced.

### Why `git ls-remote` cannot read `contract_version` directly

`git ls-remote` returns a **ref SHA** (the commit or tag object SHA the ref points at), not blob
contents. "Comparing `contract_version` via ls-remote" is not achievable — `contract_version` is a
string inside the JSON blob. A ref SHA tells you whether the tip has moved; it cannot tell you
what the blob says.

### The dedicated ref: `cockpit-contract-release`

DoE publishes a **dedicated lightweight moving tag** on this repo:

```
refs/tags/cockpit-contract-release
```

This tag is advanced ONLY when `emission-conformance.json` or `coordinator/cockpit-contract/schema/`
changes. It is a **precise, non-over-firing signal** — example-orchestration-hub does not get a re-vendor nudge on
unrelated DoE commits.

**DoE-surface commitment (AC8):** the gen/regen workflow (`gen-emission-conformance.sh`) MUST
advance this tag on every intentional contract change:

```bash
git tag -f cockpit-contract-release
# (origin push rides /merge-to-main — not during pre-merge work/ branch execution)
```

### Consumer freshness probe

example-orchestration-hub's freshness probe:

```bash
git ls-remote <doe_origin> refs/tags/cockpit-contract-release
```

Records the SHA at which its vendored pin was cut. Fails loud on SHA mismatch (the tag has
advanced since the pin was cut — re-vendor is needed). This is a bounded single-ref probe — one
ref, no full fetch, no fixture-body network read. It does NOT reintroduce network cost into the
hot path.

**Net contract: local clone read for the fixture body; single-ref `ls-remote` of
`cockpit-contract-release` for the freshness signal.**

---

## Resolution Contract (CD-2)

Consumers resolve the DoE clone and read the fixture via two legs:

| Leg | Mechanism | Network? |
|---|---|---|
| **Fixture body** | Registry `repos.doe_claude` → local sibling clone → `HEAD:coordinator/cockpit-contract/conformance/emission-conformance.json` | No — direct file read from local clone |
| **Freshness signal** | `git ls-remote <origin> refs/tags/cockpit-contract-release` | Yes — single-ref, bounded |

Registry resolution: `docs/wiki/machine-local-registry.md` documents the `repos.doe_claude` key
and the resolution mechanics.

The freshness probe is the ONLY network leg. Reading the fixture body is always a local file read
— fast, offline-capable, no credentials.

---

## AC5-PROVENANCE — Provenance Normalization (Shared Cross-Repo Oracle)

### Why normalization is required

Unlike the Step Zero emitter (a pure function), the cockpit emitter stamps runtime-varying
provenance into every record. A frozen input corpus makes the record structure deterministic but
does NOT make these fields deterministic. Raw byte-compare would fail on every fresh emitter run
regardless of contract correctness.

The conformance oracle is therefore: **NORMALIZE both sides to fixed sentinels, then compare.**

**Both DoE (generator + drift-runner) and example-orchestration-hub (validator) apply this normalization before
comparing.** This section is the cross-repo shared oracle definition — not a generator-internal
detail.

### Paths scrubbed to fixed sentinels

Both sides scrub the following JSON paths to the sentinel values shown before comparing:

| JSON path | Sentinel value | Source in emitter |
|---|---|---|
| `provenance.observed_at` | `"1970-01-01T00:00:00Z"` | `date -u` call, lines ~120–122 |
| `provenance.ref.sha` | `"0000000000000000000000000000000000000000"` | `git rev-parse HEAD`, lines ~120–122 |
| `provenance.ref.branch` | `"__NORMALIZED__"` | `git rev-parse --abbrev-ref HEAD`, lines ~120–122 |
| `provenance.repo` | `"__NORMALIZED__"` | Registry-resolved repo name, lines ~120–122 |
| `observed_at` (top-level) | `"1970-01-01T00:00:00Z"` | `date -u` top-level stamp |
| `computed_as_of` (top-level) | `"1970-01-01T00:00:00Z"` | `date -u` top-level stamp |
| `REPO_NAME` (hardcoded string) | `"__NORMALIZED__"` | Hardcoded at emitter line ~122 |

### Sentinel value conventions

- **Epoch zero (`"1970-01-01T00:00:00Z"`)** for all timestamp fields — unambiguous, zero, not a
  real wall-clock value on any conformant machine.
- **Zero SHA (`"0000000000000000000000000000000000000000"`)** for git commit SHA fields — the
  git null object SHA; unambiguous as a sentinel.
- **`"__NORMALIZED__"`** for string identifier fields (branch, repo, `REPO_NAME`) — visibly
  artificial, cannot collide with a real branch name or repo path.

### Normalization scope

The normalizer MUST scrub **all seven paths above** and MUST NOT scrub any other fields. Scrubbing
additional fields would mask real drift; scrubbing fewer would produce non-deterministic output and
spurious failures. Both sides apply the same normalizer in the same order.

→ `docs/wiki/round-trip-contract-tests.md` § Golden-Snapshot Identifier Normalization for the
general discipline.

---

## Reachability Contract (CD-3)

### State-1 now fails loud — no bash-emitter fallback (DR-208/DR-210)

**As of DR-208 (tri-plane relocation) and DR-210 (strangler facade, strang-01 C2),
`coordinator/bin/emit-cockpit-snapshot.sh` no longer retains a working emitter body.** The
original bash implementation was ported to example-orchestration-hub's Python `artifact.emit`, which is now the
**sole production cockpit emitter**. The bash script is a facade router with a three-state model:

- **State 1 (example-orchestration-hub seam absent on disk)** — `legacy_emit` **fails loud**: "cockpit emission
  requires the example-orchestration-hub control plane, not present in this distribution." No snapshot is written.
  This is a capability boundary, not a degraded-but-functional fallback — the prior cold-shell
  PATH-reachability framing below (State-1 target = a populated bash-emitted snapshot) no longer
  holds. A consumer that reaches State 1 gets nothing, and must treat that as "cockpit emission
  unavailable in this environment," not as data to conform against.
- **State 2 (seam present, daemon idle-shut)** — the C1 client lazy-launches the daemon, then RPCs
  into `artifact.emit`. This is the normal production path.
- **State 3 (seam present, post-spawn unreachable)** — hard transport error, fail loud.

Consumers conforming against this contract MUST target example-orchestration-hub's `artifact.emit` output (State 2)
as the live-producer surface. The bash script's continued presence at `coordinator/bin/` is a
routing facade only (zero caller repoints, per DR-210 AC8) — it is not an independent emitter
implementation and must not be treated as one for conformance purposes.

### Plugin-load PATH surfaces (warm session)

`coordinator/bin/emit-cockpit-snapshot.sh` and `append-goal-event.sh` are **plugin-load-PATH
surfaces**: Claude Code injects the coordinator plugin's `bin/` directory onto PATH at plugin-load
(`coordinator/.claude-plugin/plugin.json`). They are **NOT cold-terminal-PATH surfaces** — they
have never been on a cold PATH, before or after W4.2. This PATH-injection fact still governs
*invocation* reachability (whether the facade script itself can be called by name); it does not
change the State-1 fail-loud behavior above once invoked.

→ `docs/wiki/portable-code-substrate.md` and `docs/wiki/cross-platform-shell-portability.md` for
the plugin-load PATH-injection mechanics.
→ `docs/plans/2026-07-04-coordinator-maximalist-install-shape.md` § P0 for W4.2 PATH-injection
specifics. (**Note: this plan was in DRAFT status at the time this contract was authored; confirm
§ P0 details against current plan state before building against them.**)

**W4.2 relocates the plugin source** (`~/.claude/plugins/coordinator-claude/coordinator` →
`<DoE>/coordinator`, via `claude --plugin-dir <DoE>/coordinator`), **not the `bin/` layout**. The
facade script remains at `coordinator/bin/` relative to the plugin root. Claude Code continues to
PATH-inject it at plugin-load post-cutover. Warm-session resolution: unaffected through and
after W4.2.

### Cold-shell resolution (outside a coordinator session)

If any consumer ever runs in a **cold shell** — outside a coordinator session, before plugin-load
has happened — the facade script is NOT on PATH and was never on PATH. Cold reachability MUST
resolve the emitter by absolute path.

**Two valid cold-resolution paths:**

1. **Direct file read of the machine-local registry** at `$HOME/.claude/machine-local/<registryfile>`.
   Read the file directly as a file — `$HOME/.claude/machine-local/` is a PATH-independent,
   stable, well-known absolute location. → `docs/wiki/machine-local-registry.md`.

2. **`.doe-root` sentinel** at a known absolute path (if the W4.2 install stamps one).

**NEVER use `machine-local get repos.doe_claude` as a CLI call in a cold shell.** The
`machine-local` CLI is itself a coordinator bin — it is only on PATH at plugin-load. In a cold
shell it is not reachable. This is verbatim the maximalist-P0 bootstrap hazard:
`docs/plans/2026-07-04-coordinator-maximalist-install-shape.md` § P0. A cold-shell consumer that
calls the CLI will fail with "command not found" on the very binary it needs to locate DoE.

This constraint applies today and after W4.2 cutover alike — W4.2 does not change the
plugin-load PATH-injection boundary.

---

## Re-implementer Protocol

For a consumer building a conformance validator against this fixture:

1. **Resolve the DoE clone** via the `repos.doe_claude` key in the machine-local registry (direct
   file read — see § Resolution Contract).
2. **Read the fixture body** from the local clone HEAD at
   `coordinator/cockpit-contract/conformance/emission-conformance.json`. No network required.
3. **Probe freshness** via `git ls-remote <doe_origin> refs/tags/cockpit-contract-release`.
   Record the SHA at pin-cut time. Fail loud if the tag SHA has advanced since the pin was cut.
4. **Check the MIN_SUPPORTED gate**: fail loud if your pinned `contract_version` <
   `min_supported_contract_version` in the fixture body.
5. **Run your emitter** against a controlled input corpus to produce fresh emission output.
6. **Normalize both sides** (fresh output AND fixture) per § AC5-PROVENANCE — scrub all seven
   paths to the specified sentinels before comparing.
7. **Compare normalized outputs.** Fail non-zero on any divergence. A conformance check that
   exits 0 on normalized divergence is a false-pass.

**Do NOT vendor the fixture into your repo.** Vendoring is correct for a stable ratified contract
(see `step-zero-emitter-contract.md` § Re-implementer — conform against the fixture), but for
a HEAD-tracking drift-check it induces the § EM-Response-2a blindness this whole contract exists
to prevent. Pull the fixture from the local DoE clone at check-time.

---

## Consumer-Tolerance Ledger

> One row per registered cockpit-emission consumer, its structural tolerance, its version-envelope
> tolerance, and the date that tolerance was last confirmed. This section is the **single canonical
> home** for the ledger — obligations (a)–(c) below exist so "declared, not assumed" cannot silently
> rot as the consumer set changes.

### Ledger

| Consumer | Structural tolerance | Version-envelope tolerance | As-of |
|---|---|---|---|
| **cockpit** | Ignores unknown top-level arrays — ingest reads only known entity keys. | Major 2, ANY minor, NO floor. Accepts higher AND lower same-major minor, warn-and-proceed; only a MAJOR mismatch or malformed record throws. Contributes NO minor-floor to the fleet envelope. | 2026-07-07 |
| **rag** | Replayable quarantine of unknown top-level arrays — records to `malformed_ingest`, no data loss. Stronger than silent-ignore. | Major-gate AND same-major minor-floor: `INGEST_SCHEMA_FLOOR = 2.3.0`. This floor is rag's alone. | 2026-07-07 |

### Net binding fleet envelope

**Major 2, minor ≥ 2.3.0 — binding because of rag's floor ALONE.** cockpit imposes no floor; it
contributes nothing to the binding envelope beyond the major-version gate. A future change to the
consumer set (a new consumer registering, an existing consumer relaxing or tightening its floor)
must **re-derive** the net binding envelope from the ledger rows above — never assume cockpit's
row contributes a floor just because it is listed here.

### Ledger obligations

The ledger holds only as long as these three obligations are honored:

(a) **Single canonical home.** This `## Consumer-Tolerance Ledger` section in this file is the
    ONLY place the fleet's consumer-tolerance state is recorded. A tolerance claim made anywhere
    else (a plan, a memo, a comment) is not authoritative until it is folded in here.

(b) **New consumer registers before reliance.** A new cockpit-emission consumer MUST register its
    declared structural and version-envelope tolerance in this ledger BEFORE the fleet may rely on
    that consumer's non-holding behavior. An unregistered consumer is treated as **non-tolerant
    (bilateral)** by default — the fleet does not assume graceful degradation from a consumer that
    has not stated its tolerance here.

(c) **Existing consumer announces tolerance change.** If cockpit or rag ever changes its declared
    tolerance (tightens or relaxes its floor, changes its structural handling of unknown fields),
    that consumer MUST announce the change via memo to producers/DoE so this ledger — and the net
    binding envelope derived from it — is re-derived, not left stale.

---

## Producer Contract — Authoritative `coordinator_root_path`

> The remaining two AC14 producer-contract details — backlog/goal per-repo sharding, and
> born-compliant emit-hold sentinel onboarding — live in `state-placement-law.md` § Fleet Producer
> Contract.

Every emission carries a single **top-level authoritative** `coordinator_root_path` field:

- **Value:** the emitting repo's root path.
- **Placement:** top-level, sibling of `emitted_by_machine` — **emission-uniform**, not a
  per-provenance-row field. One authoritative value per emission, not one per row.
- **Consumer keying:** consumers key on `(owner, repo, coordinator_root_path)` using this
  top-level authoritative value, rather than deriving `coordinator_root_path` themselves from a
  per-row field.

**Legacy per-row literals are uninformative.** Some on-disk provenance rows carry a legacy
`coordinator_root_path: "."` literal — a relative, per-row artifact of an earlier emission shape.
That per-row literal is not the authoritative value and does not carry the emitting repo's actual
root path; consumers MUST resolve `coordinator_root_path` from the top-level field described above,
not from any legacy per-row occurrence.

### `owner` — a validated string, not a closed enum

End-state: `owner` is a **validated string**, not a closed enum — D11 parity with the existing
`machine` / `MachineSlug` field (`z.string().min(1)`, a light format guard: reject empty, whitespace-only,
or leading-slash values). This admits `local/<basename>` (a repo that resolves on disk but has no
git remote) without needing a dedicated sentinel value — the validated-string shape already covers
it. **This is a description of the end-state, not a change landed by this doc.** The contract change
itself is authored and landed by the peer reshape plan
`docs/plans/2026-07-07-cockpit-owner-string-not-enum.md` — do not re-author that change here.

---

## Related

- `coordinator/cockpit-contract/conformance/emission-conformance.json` — normative fixture.
- `coordinator/bin/gen-emission-conformance.sh` — generator (the only sanctioned path to authoring the fixture).
- `coordinator/tests/test_emission_conformance.sh` — DoE-side drift regression guard.
- `coordinator/docs/wiki/step-zero-emitter-contract.md` — instance #1 of this pattern (Step Zero NDJSON); the emission-conformance fixture is instance #2, mirroring its five-part structure with the added provenance-normalization oracle.
- `docs/wiki/round-trip-contract-tests.md` — round-trip fixture discipline and golden-snapshot normalization.
- `docs/wiki/schema-version-gate.md` — two-axis version gate semantics and reader-first bump ordering.
- `docs/wiki/machine-local-registry.md` — `repos.doe_claude` registry resolution.
- `docs/wiki/portable-code-substrate.md` — plugin-load PATH-injection mechanics.
- `docs/wiki/cross-platform-shell-portability.md` — cross-platform shell portability (plugin-load PATH context).
- `docs/wiki/state-placement-law.md` § Fleet Producer Contract — per-repo emission, live-remote horizon, Tier A/B observation model this Consumer-Tolerance Ledger and producer-contract details are symmetric with.
- `docs/plans/2026-07-07-cockpit-owner-string-not-enum.md` — the peer reshape plan that lands the `owner` validated-string end-state described above.

---

## Ratification

This contract was ratified via the accepted memo
`cross-repo/archive/2026-07-04-example-orchestration-hub-strangler-emission-fixture-and-fallback.md` (topic:
`strang-emission-fixture-answers`). The fixture path, version semantics, freshness protocol,
resolution contract, provenance-normalization oracle, and reachability contract codified here are
the definitive answers to the four sharp contract elements that memo raised.

The plan that commissioned this fixture and contract doc is
`docs/plans/2026-07-04-doe-emission-conformance-fixture.md`.
