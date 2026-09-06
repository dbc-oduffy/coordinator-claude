---
title: Emission Conformance Contract
status: active
kind: doctrine-wiki
created: 2026-07-04
spec-backlink: docs/plans/2026-07-04-doe-emission-conformance-fixture.md
---

# Emission Conformance Contract

> Normative shared contract for the DoE-hosted emission-conformance fixture. Coordinator keeps the
> fixture current on HEAD; claude-klabauter DR-210's strangler drift-check (strang-02) and any other consumer
> conform against it. This doc codifies the three contract decisions (CD-1/CD-2/CD-3) the fixture
> answers — fixture path, version semantics + freshness protocol, and emitter reachability — plus the
> shared provenance-normalization oracle (AC5-PROVENANCE) that makes the conformance compare
> deterministic across stateful emitter output.

<!-- spec-backlink: docs/plans/2026-07-04-doe-emission-conformance-fixture.md § CD-1/CD-2/CD-3 -->
<!-- ratification: cross-repo/archive/2026-07-04-claude-klabauter-strangler-emission-fixture-and-fallback.md -->

---

## Purpose

The coordinator cockpit-contract tc3 emitter (claude-klabauter's Python `artifact.emit`, the sole
production emitter as of claude-klabauter DR-208/DR-210 — `coordinator/bin/emit-cockpit-snapshot.py` is now a
fail-loud facade stub, see § Reachability Contract) and `append-goal-event.py` produce structured
NDJSON cockpit records covering every entity class (handoff-summary, backlog-item-summary,
review-trail, routine-signal, completion-rollup, goal). The **contract SSOT stays DoE-side**; each
consumer repo owns its language-specific validator.

This doc is the shared normative surface every consumer validator conforms against. It answers
three questions strang-02 needs resolved before it can build:

1. **Where is the fixture** and how does its schema version travel with it? (CD-1)
2. **How does a consumer know the fixture is current** without going blind to DoE-HEAD drift? (CD-2)
3. **Is the emission path reachable** through and after the W4.2 plugin-source cutover, and what
   happens when the claude-klabauter control plane is absent? (CD-3)

This fixture is **instance #2** of the Step Zero NDJSON conformance pattern
(`coordinator/docs/wiki/step-zero-emitter-contract.md`): same five-part shape (fixture + generator
+ drift-runner + contract-doc + ratifying-memo). It differs on the **determinism axis**: the
step-zero emitter is a pure function (zero runtime-varying fields; byte-equality is a complete
oracle). The cockpit emitter is stateful — it stamps wall-clock, host, git SHA, and a hardcoded
`REPO_NAME` into every record. The conformance oracle is therefore **NORMALIZE-then-compare, not
raw byte-compare** (see § AC5-PROVENANCE). The generator belongs at claude-klabauter's `coordinator/bin/`
(a plugin-load PATH surface) rather than `tests/fixtures/` — intentional per the CD-1
schema-package version-lock rationale. DoE's own `coordinator/bin/` holds no executables and is
not a candidate home.

---

## The Fixture as Single Normative Authority (CD-1)

`coordinator/cockpit-contract/conformance/emission-conformance.json` is the **single normative
authority** for the emission contract. It lives inside the contract SSOT package
(`coordinator/cockpit-contract/`, alongside `schema/`, `fixtures/`, `dist/`). This placement
version-locks the fixture to the schema in the same package: a schema bump and a fixture regen
ride the same commit, making staleness detectable rather than silently divergent.

**The generator is claude-klabauter's `coordinator_core.contract.cockpit_schema.emit_conformance_fixture`**,
beside `emit_schema`. `regen-cockpit-schema.py` emits `schema/` only and produces no fixture — do
not follow it looking for one. The generator **migrates** the committed fixture rather than
synthesizing a new one: its real records carry across, newly-required fields are synthesized
per-field and checked against their own subschema before use, and fields the schema dropped are
removed. It refuses to write a body that does not validate. Regeneration is idempotent — a second
run over its own output is byte-identical, so a regen diff is readable.

Hand-edits to `emission-conformance.json` are forbidden — a hand-patched fixture is one no
generator can reproduce. Changes go through the generator, a reviewed diff, and a
`contract_version` bump on intentional contract change.

**`contract_version` and `min_supported_contract_version` are fixture METADATA, not envelope
fields.** `snapshot-envelope.schema.json` declares neither and is `additionalProperties: false`,
so **validating the whole document against that schema is the wrong measurement** — it reports an
`additionalProperties` failure for the two metadata keys and nothing else. Strip both keys, then
validate the remaining envelope. The generator does exactly this, and so must any drift-runner or
consumer check.

`min_supported_contract_version` is **DoE-owned, hand-maintained, and preserved verbatim** across
every regen. It is never derived and never set equal to `contract_version`: the two differing is
what keeps claude-klabauter's `doe_drift` version-band gate meaningful. A fixture carrying no
`min_supported_contract_version` is refused by the generator, not guessed at.

The fixture is a round-trip instance, **not full entity coverage**. Six of its twenty entity
sections carry records — `coordinator_roots`, `branches`, `handoffs`, `review_trail`,
`routine_signals`, `goals_current`; the rest are present-and-empty, so the schema keys are
exercised but those entity bodies are not. Read it as a conformance instance over the emitter's
census-and-work-state core, and do not cite it as evidence that an unpopulated entity class
round-trips. → `docs/wiki/round-trip-contract-tests.md` for the round-trip fixture discipline.

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
reader-first** by construction: claude-klabauter is behind the instant DoE bumps HEAD. Any consumer would
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
changes. It is a **precise, non-over-firing signal** — claude-klabauter does not get a re-vendor nudge on
unrelated DoE commits.

**DoE-surface commitment (AC8):** discharging this commitment is a two-part seam. The LOCAL
advance — claude-klabauter `coordinator/bin/regen-cockpit-schema.py --advance-ref` — MUST move
this tag on every intentional contract change, and by deliberate invariant never pushes it. The
ORIGIN PUSH that makes the moved tag visible to a consumer's `git ls-remote` fires from
Claude-klabauter's post-commit auto-push hook (`coordinator_core/hooks/auto_push.py`,
`_maybe_publish_cockpit_contract`), which runs this repo's own
`.github/scripts/publish_cockpit_contract.py` after a successful push that touched
`coordinator/cockpit-contract/schema/**`, and advances and pushes both the moving
`cockpit-contract-release` ref and the immutable per-version alias tag. There is no separate
manual publish-now path — the outage remediation is re-running the script directly
(`EXPLAIN_ONLY=1` for a dry run). Both halves are required — a local-only advance discharges
nothing for a fleet consumer polling the origin:

```bash
_cc_claude_klabauter="$REPO_CLAUDE_KLABAUTER"
[ -n "$_cc_claude_klabauter" ] || _cc_claude_klabauter="$CLAUDE_KLABAUTER_ROOT"
python "$_cc_claude_klabauter/coordinator/bin/regen-cockpit-schema.py" --advance-ref
# internally: git tag -f cockpit-contract-release (local only, skipped if the
# regen produced no change under coordinator/cockpit-contract/schema/)
```

**On Windows, `--advance-ref` cannot complete — advance and push in one step with the publish
script instead:**

```bash
EXPLAIN_ONLY=1 python3 .github/scripts/publish_cockpit_contract.py  # dry run: decision + reason
python3 .github/scripts/publish_cockpit_contract.py                 # advance + push both refs
```

`--advance-ref` re-runs the regen unconditionally before its refuse-if-dirty check, and the
emitter writes with the platform's newline, so a Windows regen rewrites all 31 schema files CRLF,
the dirty check trips, and every re-run reproduces the same dirt. The publish script reads
committed state and never regenerates, so it is unaffected. Committed bytes are never at risk
either way — `coordinator/cockpit-contract/.gitattributes` pins `*.json eol=lf`. Root cause and
fix are claude-klabauter-side (`regen-cockpit-schema.py`); see `coordinator/cockpit-contract/DECISIONS.md`
D45 §3.

The origin push is designed to fire from claude-klabauter's post-commit auto-push hook, not a
GitHub Action — the retired `.github/workflows/publish-cockpit-contract-release.yml` was deleted
2026-07-29 and does not exist. GitHub Actions is not banned fleet-wide, but the operative rule is
fleet-wide and cost-driven: any use of GitHub Actions anywhere in the fleet requires PM permission
*before* it is used, because GH Actions minutes are billed and burn budget fast.

**Do not assume the hook fired.** On 2026-08-11 the 3.11.0 bundle commit (`081bdd2cf`) pushed
cleanly and neither tag moved on origin; the manual script run published both. Check
`git ls-remote --tags origin 'cockpit-contract*'` after any schema push, and run the publish
script if the refs did not move — a stale origin ref is what blocks every fleet consumer polling
it, and it fails silently.

`--advance-ref` is opt-in and never the default — a bare drift-check run (no flag) must not
touch the tag, or it would spuriously advance the release ref on every no-op invocation (an AC8
violation in its own right).

**Why a dedicated regression guard exists (context, greppable so this is not re-learned the hard
way):** the tag-advance is collateral to `regen-cockpit-schema.py` regenerating the schema — an
entrypoint with no tag awareness silently drifts the tag behind the schema version with nothing
catching it. A static regression guard for that entrypoint lives at claude-klabauter's
`coordinator/bin/tests/test-cockpit-contract-release-tag.js`
(fast tier, `node --test` glob) — it greps the entrypoint for the `--advance-ref`
wiring and the `cockpit-contract-release` tag name, and asserts `git push` never appears in it,
so a regression on the push-free local-advance invariant fails the fast tier immediately instead
of drifting silently for months. DoE's own side of the guard is a Python test module,
`coordinator/tests/test_cockpit_contract_publish_seam.py`, covering the origin-push half of the
seam.

### Consumer freshness probe

Claude-klabauter's freshness probe:

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

**Both DoE (generator + drift-runner) and claude-klabauter (validator) apply this normalization before
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

### Freezing the emitter's inputs (generator/drift-runner technique)

Provenance normalization (above) makes runtime-varying *output* fields deterministic; it does not by
itself make the emitter's *inputs* deterministic. The cockpit emitter reads live state — `query-records`,
sub-scripts, and `git` — so to produce a byte-reproducible golden the generator (and any consumer's
drift-runner producing fresh output for the compare) must also **freeze the input side**:

- **Redirect the emitter at a fixture `.claude-root`** — set `CLAUDE_HOME` and `CLAUDE_KLABAUTER_ROOT` at a fixed
  fixture tree, so `query-records` and the sub-scripts read a frozen corpus rather than live session state.
- **Init a deterministic git repo** inside the fixture: fixed `user.name`/`user.email`, pinned
  `GIT_AUTHOR_DATE`/`GIT_COMMITTER_DATE`, and a commit message carrying the tokens the emitter greps for
  fresh signals (e.g. update-docs / bug-sweep markers) so the emitted records are populated, not empty.
- **Then** apply § AC5-PROVENANCE scrubbing to the output, since the frozen git repo still stamps a real
  (fixture) SHA/branch/timestamp into each record.

Input-freeze and output-scrub are complementary, not substitutes: the frozen `.claude-root` makes the
record *structure* reproducible; the provenance scrub makes the residual runtime *stamps* reproducible.
Both are required for a stateful emitter's golden. (Source: emission-conformance fixture;
reusable for the memo-emission graduation fixture.)

---

## Reachability Contract (CD-3)

### State-1 now fails loud — no bash-emitter fallback (claude-klabauter DR-208/DR-210)

**As of claude-klabauter DR-208 (tri-plane relocation) and claude-klabauter DR-210 (strangler facade, strang-01 C2),
Claude-klabauter `coordinator/bin/emit-cockpit-snapshot.py` retains no working emitter body.** The
original bash implementation was ported to claude-klabauter's Python `artifact.emit`, which is now the
**sole production cockpit emitter**. The bash script is a facade router with a three-state model:

- **State 1 (claude-klabauter seam absent on disk)** — `legacy_emit` **fails loud**: "cockpit emission
  requires the claude-klabauter control plane, not present in this distribution." No snapshot is written.
  This is a capability boundary, not a degraded-but-functional fallback — the prior cold-shell
  PATH-reachability framing below (State-1 target = a populated bash-emitted snapshot) does not
  hold. A consumer that reaches State 1 gets nothing, and must treat that as "cockpit emission
  unavailable in this environment," not as data to conform against.
- **State 2 (seam present, daemon idle-shut)** — the C1 client lazy-launches the daemon, then RPCs
  into `artifact.emit`. This is the normal production path.
- **State 3 (seam present, post-spawn unreachable)** — hard transport error, fail loud.

Consumers conforming against this contract MUST target claude-klabauter's `artifact.emit` output (State 2)
as the live-producer surface. The bash script's continued presence at `coordinator/bin/` is a
routing facade only (zero caller repoints, per claude-klabauter DR-210 AC8) — it is not an independent emitter
implementation and must not be treated as one for conformance purposes.

**`emit-cadence.py` shares this same State-1 fail-loud shape.** The per-repo cadence-trigger
facade (claude-klabauter `coordinator/bin/emit-cadence.py`, § New claude-klabauter composite op below) is a
second thin Python trampoline (2026-07-19 Windows de-bash campaign, W1b — routes natively via
`cc_invoke.route_mutation`, no bash in the middle), structurally analogous to
Claude-klabauter `coordinator/bin/emit-cockpit-snapshot.py` and `append-goal-event.py`: when the claude-klabauter seam is absent on disk,
its `legacy_cadence` fallback
**fails loud** (exit 1) with "cockpit emission cadence requires the claude-klabauter control plane, which is
not present in this distribution. No emission fired." — not a degraded-but-functional fallback,
same as `legacy_emit` above. When the seam is present, it routes to claude-klabauter's `emit.cadence`
composite op (State 2); a post-spawn transport failure is State 3, hard error. The one
behavioral difference: `emit-cadence.py` is gated by `COORDINATOR_EMISSION_CADENCE_LIVE`
(default OFF) checked *before* the three-state probe — absent an explicit on value the gate
short-circuits to a benign exit-0 skip without ever reaching State 1/2/3, so a gate-off consumer
sees "cadence skipped," not a State-1 failure.

### Plugin-load PATH surfaces (warm session)

Claude-klabauter `coordinator/bin/emit-cockpit-snapshot.py` and `append-goal-event.py` are **plugin-load-PATH
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

### Live per-repo cadence trigger — `emit-cadence.py` (DR-047, emission-cadence-trigger-rewire)

A LIVE per-repo cadence trigger now exists: claude-klabauter `coordinator/bin/emit-cadence.py`
fires claude-klabauter's `emit.cadence` composite op. It is called from the three `-complete` ceremonies —
`/workstream-complete` (`skills/workstream-complete/SKILL.md`), `/workday-complete`
(`commands/workday-complete.md`), and `/workweek-complete` (`commands/workweek-complete.md`) —
after each ceremony's work-landing steps complete, so the emitted snapshot reflects *completed*
work, not in-flight state. This is the cadence half of the DR-047 transport-seam split: DoE owns
WHEN emission fires (the cadence trigger, at these three call sites); claude-klabauter owns WHAT the op does
internally (backlog.record → artifact.emit ordering — see § New claude-klabauter composite op below).

`emit-cadence.py` is gate-flagged by `COORDINATOR_EMISSION_CADENCE_LIVE` — **default OFF**. Only an
explicit on value (`1`, `true`, `on`, case-insensitive) enables cadence emission; unset or any
other value leaves it OFF, so all three ceremony-close triggers benign-skip and
`state/cockpit-emission.json` does not advance. When OFF, the script logs once to stderr and exits
0 — a skip that never wedges or errors the calling ceremony. Each call site treats a non-zero exit
from `emit-cadence.py` as non-fatal to the ceremony (`|| echo "note: emission cadence skipped..."`).

A halted repo's frozen `state/cockpit-emission.json` sits beside a `state/cockpit-emission.HALTED.md`
marker naming the last captured `emitted_at`, so the stale file cannot be read as a current fleet
snapshot. `artifact.emit` remains available on demand; only the automatic trigger is off.

**This trigger is new as of the emission-cadence-trigger-rewire plan** — no live call
site invoking a cadence-triggering emitter from any `-complete` ceremony existed before this plan
landed. Any framing that predates it (e.g. a claim that `artifact.emit` was already "triggered at
/workstream-complete via `emit-cockpit-snapshot.py`") describes a state that did not exist on disk
at the time it was written and must not be read as historical fact — claude-klabauter `coordinator/bin/emit-cockpit-snapshot.py` is
the State-1/2/3 facade for `artifact.emit` itself (see above), not a cadence trigger, and it was
never wired into a `-complete` ceremony's call graph.

### New claude-klabauter composite op — `emit.cadence`

<!-- PROVENANCE: run 2026-08-06-14h38, source nugget c4-017 -->
`emit.cadence` is a new claude-klabauter composite op (landed alongside this facade) that runs
**`backlog.record` THEN `artifact.emit`**, in that order, as a claude-klabauter-internal invariant. It sits
conceptually alongside `artifact.emit` in this contract: `artifact.emit` is the leaf cockpit
emission op (§ Purpose, § Reachability Contract above); `emit.cadence` is the composite the
per-repo cadence trigger calls, which performs a backlog record THEN delegates to `artifact.emit`
aggregation as its second step. Consumers conforming against this contract's emission output should
be aware that a cadence-triggered emission is the composite's `artifact.emit` leg, not a
freestanding call — the ordering (backlog.record first) is claude-klabauter-internal and not independently
observable from the DoE side of the transport seam.

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

## Producer Contract — Repo Identity and `coordinator_root_path`

> The remaining two AC14 producer-contract details — backlog/goal per-repo sharding, and
> born-compliant emit-hold sentinel onboarding — live in `state-placement-law.md` § Fleet Producer
> Contract.

Every emission carries a single **top-level** `coordinator_root_path` field:

- **Value:** the emitting repo's root path, as a per-emission, machine-local location fact. It MAY
  be null — the field is always present in a conformant emission, but its value is not guaranteed
  and is never load-bearing for identity.
- **Placement:** top-level, sibling of `emitted_by_machine` — **emission-uniform**, not a
  per-provenance-row field. One value per emission, not one per row.
- **Consumer keying:** consumers key logical repo identity on **`(owner, repo)`** alone.
  `coordinator_root_path` is demoted OUT of the identity key — it is a non-key, per-emission,
  machine-local location fact carried alongside the key, not part of it. Consumers MUST NOT derive
  `coordinator_root_path` themselves from a per-row field; when they consume the top-level value at
  all, it is for location display/diagnostics, never for joining or deduplicating repo identity.

**The machine axis is orthogonal to repo identity.** The same repo checked out on N machines is
**one logical identity, not N.** `coordinator_root_path` varies per checkout — `C:\Users\alice\repo` <!-- foreign-path-ok: illustrating the per-machine path variance this contract exists to normalize -->
and `/home/bob/repo` and `X:\DoE-claude` can all be the same logical repo observed from different <!-- foreign-path-ok: illustrating the per-machine path variance this contract exists to normalize -->
machines — so keying identity on it fragments one repo into as many rows as it has checkouts. Where
a consumer genuinely needs per-machine differentiation (e.g. "which machine last emitted this"),
that comes from `emitted_by_machine` / `coordinator.machine_slug` — never from the root path.
Conflating the machine axis with the identity axis is exactly what produced the cross-machine
identity drift this contract now forecloses.

**This ratifies existing consumer behavior; it is not a consumer-facing break.** Per
`docs/decisions/DR-022-cockpit-contract-canonical-repo-owner-form.md:28`, cockpit and rag already
join on a machine-blind `lower(owner)/lower(repo)` key in practice — the path-in-key design this
section previously described had already produced a live double-count defect at cockpit ingest.
The producer contract is catching up to shipped consumer behavior, not changing it.

**Legacy per-row literals are uninformative.** Some on-disk provenance rows carry a legacy
`coordinator_root_path: "."` literal — a relative, per-row artifact of an earlier emission shape.
That per-row literal is not the top-level value and does not carry the emitting repo's actual
root path; consumers MUST resolve `coordinator_root_path` (where they consume it at all) from the
top-level field described above, not from any legacy per-row occurrence.

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

- `coordinator/cockpit-contract/conformance/emission-conformance.json` — the normative
  emission instance (CD-1), tracking the current contract version and validating clean against
  `schema/snapshot-envelope.schema.json` once its two metadata keys are stripped. Claude-klabauter's
  `coordinator_core.ops.emit.doe_drift` resolves it by path from this clone, so it is never free
  to delete — a missing oracle is worse than a stale one, and the cost lands on claude-klabauter.
- `coordinator/docs/wiki/step-zero-emitter-contract.md` — instance #1 of this pattern (Step Zero NDJSON); the emission-conformance fixture is instance #2, mirroring its five-part structure with the added provenance-normalization oracle.
- `docs/wiki/round-trip-contract-tests.md` — round-trip fixture discipline and golden-snapshot normalization.
- `docs/wiki/schema-version-gate.md` — two-axis version gate semantics and reader-first bump ordering.
- `docs/wiki/machine-local-registry.md` — `repos.doe_claude` registry resolution.
- `docs/wiki/portable-code-substrate.md` — plugin-load PATH-injection mechanics.
- `docs/wiki/cross-platform-shell-portability.md` — cross-platform shell portability (plugin-load PATH context).
- `docs/wiki/state-placement-law.md` § Fleet Producer Contract — per-repo emission, live-remote horizon, Tier A/B observation model this Consumer-Tolerance Ledger and producer-contract details are symmetric with.
- `docs/plans/2026-07-07-cockpit-owner-string-not-enum.md` — the peer reshape plan that lands the `owner` validated-string end-state described above.
- claude-klabauter `coordinator/bin/emit-cadence.py` — live per-repo cadence-trigger facade for claude-klabauter's `emit.cadence` composite op; fires from the three `-complete` ceremonies (§ Reachability Contract).
- `docs/plans/2026-07-11-emission-cadence-trigger-rewire.md` — the plan that lands the `emit-cadence.py` cadence trigger and `emit.cadence` composite op.

---

## Ratification

This contract was ratified via the accepted memo
`cross-repo/archive/2026-07-04-claude-klabauter-strangler-emission-fixture-and-fallback.md` (topic:
`strang-emission-fixture-answers`). The fixture path, version semantics, freshness protocol,
resolution contract, provenance-normalization oracle, and reachability contract codified here are
the definitive answers to the four sharp contract elements that memo raised.

The plan that commissioned this fixture and contract doc is
`docs/plans/2026-07-04-doe-emission-conformance-fixture.md`.
