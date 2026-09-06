---
title: Doctor Probe Design
status: active
kind: doctrine-wiki
created: 2026-05-27
---

# Doctor Probe Design

> A diagnostic probe is only as trustworthy as its fidelity to the thing it vouches for. A probe must walk the same resolution path as the runtime tool it checks, must fail loud when doctrine and reality diverge, and must report honest status — including an explicit `inconclusive` — rather than collapsing uncertainty into a false pass or false fail. These three properties are facets of one rule: **a probe faithfully mirrors what it vouches for, and reports what it actually saw.**

This wiki consolidates the doctor/probe-design lessons that cut across consumer-claude repos shipping doctors. The shared failure mode is a probe whose verdict the operator *trusts* but that does not actually exercise — or honestly report on — the thing it claims to verify.

## `inconclusive` Is a First-Class Probe Status

*project-rag-ue-addon.* A doctor that can only emit pass or fail is forced to lie when it cannot actually determine the answer. A probe that hits an unreachable substrate, a missing prerequisite, or an environment it wasn't designed for will — under a binary verdict model — either false-pass (silently green on a state it never checked) or false-fail (red on a condition that isn't actually broken). Both destroy operator trust: the first because a green doctor that misses real breakage trains the operator to distrust greens; the second because a doctor that cries wolf trains the operator to ignore reds.

**Rule:** codify `inconclusive` (or `skipped` / `unknown` — pick one vocabulary and hold it) as a first-class probe status alongside pass and fail, across every consumer-claude repo that ships doctors. When a probe cannot reach the state it checks, it emits `inconclusive` with the reason — never a fabricated pass or fail. The operator reads `inconclusive` as "this probe couldn't run, here's why," which is honest signal; a fabricated green or red is noise that erodes the whole doctor's credibility. This is the diagnostic-status analog of `docs/wiki/implementation-standards-by-domain.md` § Cross-cutting standards, "detect-then-fail-loud on ambiguity" — a probe that can't determine the answer must say so, not silently pick.

**Third vocabulary — the data-record analog: an unset field beats a fabricated one.** *claude-klabauter.* The same rule governs structured records, not just probe verdicts. When a record's field (an `evidence:` pointer, a `verified_at`, a `source`) cannot be filled with something that would actually resolve, leave it **unset** rather than writing a value that resolves true unconditionally. A pointer that always resolves is the record-shaped form of a vacuous pass: it satisfies every reader's existence check while vouching for nothing, and it silently devalues every *honestly* filled field beside it. Claude-klabauter's commitments ledger now leaves `evidence:` unset on 13 of 30 records precisely so the other 17 are worth reading. Applies to probe status (`inconclusive`), test outcome (`pytest.skip` over a silent bare `return` — see § Vacuity Is Not a Probe-Only Defect), and record fields alike: **the honest absence is signal; the fabricated presence is noise that costs you the signal elsewhere.**

## Divergence-Sentinel Probes Must Fail Loud, Not Vacuously Pass

*example-game-workbench-repo.* Doctor remediations and the doctrine they enforce drift apart over time — the doctrine moves, the probe's expected-state baseline doesn't. A probe written to detect "config diverges from doctrine" must **fail loud on divergence**, not vacuously pass when its own baseline has gone stale or its check has silently no-op'd. The recurring failure: a sentinel probe whose match condition stops matching (a renamed field, a relocated file, a grep that now returns zero) returns green-because-nothing-matched rather than red-because-the-thing-it-guards-is-gone. A vacuous pass is indistinguishable from a real pass to the operator — and it is exactly the divergence the probe existed to catch.

**Rule:** a divergence-sentinel probe must distinguish "checked and aligned" from "couldn't check" (→ `inconclusive`, above) and must treat "expected marker absent" as a *failure*, not a pass. Anchor the probe on a positive assertion that the guarded state exists and matches, so that disappearance of the guarded surface trips the probe rather than silently satisfying it. Guard against the `set -euo pipefail` + zero-match footgun where a grep-no-match kills the loop and the probe reports success by exiting before it checked anything. (Connects to `pre-dispatch-verification.md` § Surfacing Probes — a probe whose output isn't surfaced is invisible; a probe that vacuously passes is worse than invisible because it actively asserts a falsehood.)

## Vacuity Is Not a Probe-Only Defect — and Doctrine Is Not Where It Gets Fixed

*claude-klabauter → DoE.* This file's vacuity rules are, by claude-klabauter's own read, well-written and complete. They prevented nothing. Claude-klabauter hit six instances of green-while-asserting-nothing in a single working day, and **not one was a doctor probe** — which is exactly why probe doctrine never reached them. The spread is the argument: a lifecycle verb's `last_gate_recheck` stamp recording *that* a sweep ran and nothing about what it found (two batons sat blocked 18 and 22 days on preconditions already satisfied); a ledger record whose own title read "(now satisfied)" beside `status: open` for thirteen days; a pytest oracle whose subject was hidden by a suite-wide `HOME` quarantine, bailing with a bare `return` and reporting **PASS**; a FAIL-LOUD cross-repo reachability sweep that had never once executed; two delete-safety gates whose surface definitions had drifted apart around a shared blind spot; and an install-contract gate emitting an inert `SKIP` on a missed probe path, costing a sibling repo 13 days and an `## External blocker` section in a reviewed plan for a validator that was passing clean throughout.

**Rule: when this class recurs, the remedy is a mechanism, not another paragraph.** Restating the vacuity rule in more places is the exact move our own discharge test rejects (→ `invisible-doctrine.md`: *for every rule, what artifact discharges it? if the answer is "the operator remembers," the work is not finished*). The design property that makes a mechanism work here is that **it makes the cheap move the correct one** — claude-klabauter's `test_no_silent_bail_on_live_root_resolver.py` accepts `pytest.skip` (honest non-assertion) and accepts an explicit in-file marker (the oracle genuinely runs), and rejects only the silent bare `return`. Nobody has to remember the rule; the wrong shape does not ship. DoE's vendored counterpart is `coordinator/tests/test_no_silent_bail_in_test_corpus.py`.

**Three properties any such checker must hold itself to** — the checker is the highest-value place to apply the rules, not an exemption from them:

1. **It cannot pass vacuously itself.** A missing scan root or zero matched files must *raise*. A vacuity checker that passed having scanned nothing is the failure mode in its purest form.
2. **It can be made to fail.** A planted bad-input fixture must be flagged, and counter-fixtures must not be — this file's own authoring assertion #3 (*a probe that PASSes on good input but cannot be made to FAIL on bad input is vacuous*), applied to the checker most of all.
3. **No exclusion list.** A flagged instance is a real defect or a checker bug, never a name to register in a file. Any exemption is an in-file marker an author writes deliberately at the site, where a reader will see it.

Name the blind spots in the checker's own docstring rather than implying them away.

## A Probe Must Walk the Same Resolution Path as the Runtime Tool It Vouches For

*project-rag-ue-addon.* The deepest fidelity failure: a probe that checks a *different code path* than the runtime tool it claims to verify. When a diagnostic probe resolves a path, reads a config field, or parses an output shape **differently** from how the actual runtime tool does it, the probe and the tool disagree — and the probe produces a false-RED (or false-GREEN) because it is vouching for a path the tool never takes. Field-shape divergence between probe and tool is the recurring signature: the probe reads `config.foo` where the tool reads `config.foo.bar`, or the probe shells out with one interpreter while the tool uses another, or the probe parses a flat list where the tool parses a wrapped envelope.

**Rule:** a probe must walk the *same* resolution path as the runtime tool it vouches for — same path-resolution logic, same config-field access, same interpreter context, same output-shape parsing. Where possible, the probe should call the tool's own resolution code rather than re-implementing it (re-implementation is where the divergence creeps in). Where the probe must stand alone, pin it to the tool's exact field-shape and resolution order, and add a test that fails when the two drift. This is the diagnostic-side instance of `pre-dispatch-verification.md` § Consumer Parsers Must Verify Producer's Actual Output Shape and § Gate-Verification Mechanics ("run the probe IN the dispatch's interpreter context") — a probe is a consumer of the tool's runtime contract, and it must read the *actual* shape, not an inferred one.

## The Unifying Principle

All three rules are the same discipline at different layers of the probe:

| Layer | Failure shape | Rule |
|---|---|---|
| **Status vocabulary** | Binary verdict forces a lie when the answer is unknown | `inconclusive` is first-class |
| **Match condition** | Stale/no-op check passes vacuously instead of catching divergence | Divergence sentinels fail loud, anchor on positive assertion |
| **Resolution path** | Probe checks a different path than the tool → vouches for the wrong thing | Probe walks the tool's exact resolution path |

A probe is a *promise* to the operator: "I checked this, and here is what I found." Every one of these failures breaks the promise in a way that is invisible at read time — the operator sees a clean verdict and trusts it. Probe design is therefore trust-preservation engineering: the probe must mirror what it vouches for faithfully, and report what it actually saw honestly, or it is worse than no probe at all (a missing probe prompts caution; a lying probe prompts misplaced confidence).

## Probe Authoring Discipline

> The trio above governs each probe's *fidelity* to the thing it vouches for. This section governs the probe's *internal authoring* — that the name, the verdict, and the required/optional axis are honest at write time. Probes are doctrine, not just code; they need spec-level review before landing.

### Verdict Fields Must Not Multiplex Soft Pressure With Real Degradation

*project-rag.* A `status: degraded` field that fires on both genuine subsystem failure AND soft pre-breach pressure (e.g. RSS at 87% of a stopgap ceiling, watchdog has not aborted, queries still work) is uninterpretable downstream. Callers either treat all `degraded` as hard-stop and refuse valid work (a spike runner refused on a daemon whose only problem was being at 3.065/3.5 GiB), or they learn to ignore `degraded` entirely and miss the real breach. The leading-indicator instinct is correct — surface pre-breach pressure to the watchdog/doctor; the design error is multiplexing it through the same field that names real failure.

**Rule:** split the signal at the source. Reserve the verdict enum (`status` ∈ {ready, degraded, warming}, probe `PASS/WARN/FAIL`, envelope verdicts, ledger statuses) for genuine failure — subsystem unreachable, schema downgrade, addon mismatch, actual ceiling breach. Surface soft pressure as a separate `warnings: [...]` list plus a structured flag on the relevant sub-object (e.g. `rss.pressure: true`). Reasons in a `degraded_reasons`-style list must be load-bearing: if a caller acts on the string, the action must match the severity. Pressure strings in that list train callers to round-trip the ambiguity, and the verdict field becomes noise. Folds with § `inconclusive` Is a First-Class Probe Status — the cure for "binary verdict forces a lie" generalizes to "any verdict enum forces a lie when it carries two severities."

### Required vs Opt-In Keys — AMBER on Optional Absence Is Bad Form

*example-game-workbench-repo (PM-ratified verbatim).* A doctor probe that checks for opt-in capability (vendor toolchains, optional consumer-project paths, feature-flagged integrations) must NOT flip verdict on absence — only load-bearing prerequisites do. The PM ruling, quoted to the wiki because it names the smell directly: *"doctor shouldn't be amber on something that's optional ... it's bad form to have the doctor be flagging non-core absences."* The probe that AMBERs on every optional miss trains the operator to ignore amber entirely — same trust-collapse as the verdict-multiplexing failure above.

**Rule:** any probe that aggregates "N things missing" needs a required/optional split at design time, not bolted on after the first false amber. Implement as two lists (e.g. `_KEYS_REQUIRED` vs `_KEYS_OPTIONAL`); required-misses drive the verdict, optional-misses surface as `data.missing_optional` (advisory only). The authoring test: *"if the operator doesn't use this feature, is the probe still complaining?"* If yes, the probe is over-claiming and the verdict is dishonest. This is the keys-axis instance of the verdict-multiplexing rule above — both come from the same anti-pattern of one verdict signal carrying two severities (real-failure-vs-soft-pressure on one axis; required-vs-optional on the other).

### Name, Implementation, and Parser Must Match What Each Claims

*example-game-workbench-repo (8 witnesses in one session).* The deepest authoring failure: probes, recovery-steps, and sentinel scripts whose **implementation does not do what their name claims**, or whose **parser does not match the producer's actual output**. One session surfaced eight distinct instances on the example-game-repo doctor + install surface — all the same architectural family. The shape recurs because probes are usually reviewed as code-of-N-lines (does it run? does it pass?) rather than as doctrine (does it actually exercise the failure mode it claims?). Witnesses included:

- A recovery `--step` named "shim restoration" that only checked dist freshness.
- A drift-checker whose regex matched `[DRIFT]` while the producing script emitted `[DIVERGE]`.
- A presence-check looking for a sentinel name no producer ever wrote.
- A health probe shelling to `python3` on a platform where the interpreter is unreachable from that shell.
- A skip-list misclassifying a sibling repo against its declared propagation mode.
- An install-idempotency probe checking directory-existence, not content-currency.
- A divergence assertion conflating "stale install" with "hand-edits."
- A bounded-popen-compliance regex catching JS `.exec(` method calls as if they were subprocess calls (6 of 9 "violations" were false positives).

**Rule:** every probe (and every sentinel / recovery-step / check primitive) ships with three authoring assertions verified before landing — (1) the implementation matches the name's claim (does `--step shim-restoration` actually exercise shim restoration?); (2) the parser token matches the producer's literal output (grep the producer for the exact string the parser keys on, don't infer); (3) the smoke-test actually triggers the failure mode the probe is designed to catch (run the probe against a known-bad fixture, not just a known-good one — a probe that PASSes on good input but cannot be made to FAIL on bad input is vacuous). Treat probes as doctrine, not as one-off scripts: spec-level review (a reviewer who reads the producer + the probe + asks "does this match?") catches what code-review-of-the-probe-alone cannot. This is the authoring-time analog of § A Probe Must Walk the Same Resolution Path as the Runtime Tool It Vouches For — that rule says "match the runtime tool's resolution path"; this rule says "match every name, every parser token, every claimed exercise — at the moment you write the probe, not when the operator hits the false verdict."

Folds with § Divergence-Sentinel Probes Must Fail Loud (vacuous-pass is the runtime symptom of a name/impl mismatch authored at design time) and § Diagnostic Remediation Is a Contract (a `recover-step` pointing at a phase it doesn't actually run is exactly the name/impl gap, manifesting as a remediation that doesn't remediate).

## Single-Entry-Point Consolidation Must Stay Addressable

> The three rules above govern a single probe's *internals*. This rule governs the doctor's *surface* — the shape of the entry point all the probes hang off.

**Single-Entry-Point consolidation must pair with selective addressability, or the entry point becomes a hammer.** The Single-Entry-Point doctrine consolidates health behind one verb (no `/fix-X` / `/check-Y` proliferation — health lives in the doctor, period). That instinct is correct and stays. But consolidation has a missing second half: the one verb must stay **aimable**. A consolidated doctor with no way to run a subset fires its *entire* probe battery on every invocation — and the moment some of those probes are expensive (spawn a server, load a model, touch VRAM), the single surface degrades into a warhammer that pays cost the situation never asked for. Consolidation without addressability is the failure mode; the two are not separable.

*Empirical origin (project-rag).* The project-rag host's doctor committed ~43 GiB at boot because a `silent` tool-smoke probe ran all 40 handlers on every invocation; the host froze ~12×. The acute bug was one heavy probe, but the chronic shape was "consolidated surface, no addressability." The fix proved the pattern below on a real surface (host plan `docs/plans/2026-05-27-doctor-scalpel-not-hammer-overhaul.md`, shipped + dogfooded green). This doctrine is seeded from that proven implementation, not a planned one.

### What a good doctor shape is

1. **Triage-first by default.** Bare invocation runs a cheap first-pass (cheap localization checks only), emits a structured read + a recommendation of which cluster/probe to look at, and **stops** — it does not auto-escalate into the heavy probes it recommends. The agent (or operator) aims the next step. A bare invocation that fires everything is the warhammer this doctrine indicts; a doctor whose *default* is fire-everything teaches the anti-pattern by example.
2. **A declarative manifest is the SSOT for probe metadata.** One entry per probe carrying, at minimum: `id`, `cluster` (symptom group), `weight` (resource-semantic: `cheap` / `standard` / `heavy` — NOT latency), `interactivity` (orthogonal to weight), `triage` (in the cheap first-pass?), `symptom_keywords`. The registry / interactivity / inventory surfaces are **derived from or validated against** the manifest, not hand-synced across N files.
3. **Weight and interactivity are orthogonal axes.** Interactivity ("does this probe need a human?") carries no cost information. A `silent` probe can be `heavy`. Conflating them is how an expensive probe ends up running unconditionally. The triage invariant: `triage=true ⟹ weight ∈ {cheap, standard}`, never `heavy`.
4. **A selection grammar makes the one verb aimable** — scalpel / sword / warhammer, parameterized, NOT scattered into new commands: `<doctor> <cluster>` (sword: one cluster), `<doctor> <probe-id>` (scalpel: one probe), `<doctor> <symptom>` (match `symptom_keywords`), `<doctor> --full` (warhammer: the rare explicit "check everything"). Single-Entry-Point is preserved — it is one surface, parameterized, not a proliferation of verbs.
5. **VALIDATE-not-GENERATE at rest.** Derived artifacts are committed; a CI tripwire asserts `regenerate(manifest) == committed` (the test IS the generator in `--check` mode). There is no on-demand generator without a paired drift gate — a stale generated file must fail CI exactly as a hand-sync miss would, but there is now ONE authored source.

### The cargo-cult guard — machinery transfers, motivation does not

The *machinery* (manifest-SSOT, triage-first, selection grammar, VALIDATE-not-GENERATE) is the universal, transferable shape. The *founding motivation* — resource cost — is not universal. A doctor whose probes are all cheap (file reads, CLI smoke, a short-lived subprocess) gains the **addressability** half of this doctrine — aim a subset when debugging — but does **not** need the resource-regression-net (peak-RSS / spawn-count budget tests) an expensive-probe doctor needs. Adopting the resource apparatus for a cheap-probe doctor is cargo-culting a motivation that does not apply.

- **Expensive-probe reference:** the project-rag host doctor (75 probes, several spawn servers / load torch / touch VRAM). Resource-boundedness is its founding goal; it carries the four-dimension RSS regression-net.
- **Cheap-probe reference:** the coordinator doctor (`coordinator-doctor-sentinel.py`, ~13 probes — file reads, machine-local CLI smoke, one live host-gpu-probe subprocess; none `heavy`). It adopts addressability + manifest shape; it does **not** carry the resource-regression-net, because there is no resource problem to bound. Its `weight` field exists for shape parity, not because any probe is expensive.

A consolidated diagnostic surface also stays **probe + addressability only** at this layer — it does not silently grow a diagnose+remediate (mutation) elevation. (The project-rag host bounds this as its WS-R rule: `--fix` adds visibility, never new remediation surface.) Addressability is about *aiming what you read*, not about *expanding what you change*.

### Beyond doctors

The rule generalizes to **any consolidated command or diagnostic surface**: when you collapse N scattered verbs into one (the correct anti-proliferation instinct), pair the consolidation with a selection grammar so the one surface stays aimable. Consolidation that forfeits addressability trades verb-sprawl for a hammer — a different anti-pattern, not a fixed one.

**`--full` must route through the canonical `run_all_probes`, not a re-implemented list-comprehension.** A `--full` branch that builds `probe_results = [fn(ctx) for _, fn in subset]` (a) drops the inter-probe context stashing that `run_all_probes` does (C-0's context feeds downstream probes), and (b) bypasses the `run_all_probes` symbol that renderer/verdict/sentinel tests mock — so mocked fixtures never flow and the tests fail. Rule: the full sweep IS `run_all_probes`; reserve subset-iteration for genuine cluster/probe/symptom selectors. When a refactor adds a new dispatch path that subsumes an existing canonical function, route through the function, don't re-implement its loop. (project-rag-ue-addon doctor-scalpel Chunk 6.) [universal]

**A consolidated verb without a declarative probe manifest is addressability theater.** The manifest (per-probe `id`, `cluster`, `weight`, `triage`, `symptom_keywords`) is what makes the verb aimable — without it, `<doctor> <cluster>` or `<doctor> <probe-id>` has no SSOT to route against, and the selection grammar is hand-waved. Consolidation without addressability degrades into a warhammer; a declarative manifest is the concrete artifact that closes that gap. → `docs/wiki/doctor-probe-design.md` § What a good doctor shape is.

## Warmup Probe Pattern for Environmental Cold-Boot

**A sacrificial first-position probe absorbs environmental cold-boot cost — use separate timeout budgets and a `warmup_absorbed` summary bucket that doesn't pollute the error count.**

When a tool's first invocation in a fresh server session pays a non-deterministic environmental cost (AV scan on process creation, JIT compilation, model load, DNS warmup), a dedicated `d0-warmup` probe at bank position 0 is the cleanest fix. The warmup gets a `--cold-timeout` budget; real probes get `--warm-timeout`. The warmup probe's status — whether `ok`, `tool_error/timeout`, or runner-side `timeout` — does not increment the error count; it lands in a `warmup_absorbed` summary bucket. Empirical proof of self-sufficiency: 0 errors on a Dev Drive with no AV exclusions applied, once the warmup probe absorbed the cold-boot cost.

Generalizes beyond AV cold-boot to any environmental variance in the first-call cost. The pattern is cheap (one extra probe, one extra bucket) and eliminates "my machine is fast, CI is flaky" non-determinism. (project-rag-ue-addon Chunk 6 dogfood.)

## Diagnostic Remediation Is a Contract, Not a Suggestion

*Source: example-game-repo `state/lessons/` (example-game-repo-L161, central-promoted) — DoE-authored mirror.* A probe that says "run X to fix this" must have been verified that X actually fixes it on the current code path. The recurring failure: a remediation pointer that *looks* sensible (the right slash-command, the right script name) but whose target doesn't actually execute the phase the probe is checking — so two doctor runs return identical FAIL with no signal anything has changed. The operator runs the remediation, the probe stays red, and trust collapses.

**Rule:** every probe FAIL has a closed remediation loop. Either (a) the remediation runs a step the probe re-checks on next invocation, (b) the remediation is a `manual:` instruction the probe cannot auto-verify (still acceptable — operator owns the loop), or (c) the remediation is `setup-resolves` on opt-in (the probe declares that running `/setup` clears the failure). Anchor the contract in a test gate that enumerates allowed remediation shapes — a `recover-step` pointing at a setup phase that doesn't run is the bug class to catch. The empirical incident (Probes 9/10 → `/example-game-repo:install`) was exactly this: remediation pointer looked sensible, setup silently skipped the watchdog phase, two consecutive runs returned identical FAIL. Folds with § Divergence-Sentinel Probes Must Fail Loud — a remediation that doesn't actually remediate is a vacuous pass in disguise.

## Silent Env-Var-Gated Phase Skips Break the Remediation Loop

*Source: example-game-repo `state/lessons/` (example-game-repo-L157, central-promoted) — DoE-authored mirror.* When a setup/recovery script consults an env var to decide whether to run a load-bearing phase, the absence path is the trap: an unset env var that defaults to *skip* makes the script silently no-op the phase, the probe stays failing, and the operator sees identical state across runs with no indication the phase was skipped at all. The probe and the script disagree about whether work happened, and the divergence is invisible.

**Rule:** any script gating a load-bearing phase on an env var must (a) **default-on with explicit opt-out**, never default-off with implicit opt-in, and (b) emit a **structured skip event** the diagnostic surface can detect (a log line, a status field, a sentinel file — whatever the surrounding diagnostic layer consumes). The structured skip event is what closes the remediation loop the rule above demands: a probe can now distinguish "phase ran and failed" from "phase silently skipped," and the operator sees the actual cause. Default-on is the design-as-offers stance applied to invisible defaults — make the script's behaviour announce itself, not require the operator to suspect a gating env var exists. Empirical incident: `EXAMPLE_GAME_REPO_WATCHDOG_AUTOSTART` defaulted to skip; `/example-game-repo:install` silently no-op'd the watchdog phase; Probes 9/10 returned identical FAIL across two runs with zero signal anything had changed.

## A Probe Asserting a Retired Invariant Manufactures False RED — Gate/Retire Probes Atomically with Contract Flips

*example-game-workbench-repo.* A doctor probe that still asserts an invariant the codebase has since retired manufactures a **false-positive RED**: the contract moved (a bake-time guarantee became a runtime one, a required field became optional, a path moved), the runtime is correct, but the probe vouches for the *old* contract and fails the operator on a state that is actually healthy. This is the temporal twin of the divergence-sentinel vacuous-pass above — there the probe's check went stale and passed silently; here the probe's *assertion* went stale and fails loudly against the new truth.

**Rule:** retire or re-gate the probe in the **same change** that flips the contract it checks — a bake→runtime move, an enum widening, a required→optional relaxation. A contract flip and its probes are one atomic edit, never two. The recurring failure is shipping the contract change and leaving the probe to be reconciled "later" — between the flip and the reconciliation, every doctor run reads RED on a healthy runtime, and the operator learns to ignore the doctor. Fold with `verification-before-completion.md` § Health probe anchoring (anchor to the canonical artifact) and the premise-pass discipline in `docs/wiki/pre-dispatch-verification.md` (a contract reversal must reconcile code + probe + doctrine-doc in one change).

## Each Doctor Owns Its Own Code-Currency Surface — No Cross-Partition Reads

*project-rag (DoE-seeded from a project-rag-ue-addon → project-rag-em ask).* A **code-currency** probe answers "is the installed CODE behind the latest published release?" — a third currency axis, distinct from corpus/index freshness and from source→live-install propagation drift. The originating temptation: the addon's doctor wanted to know whether the *host* was stale, and the obvious-but-wrong implementation was to have the addon reach across the partition and parse the host's git HEAD / `pyproject.toml` to judge it. That couples the sibling's probe to layout and versioning assumptions that are the host's to change — brittle coupling that breaks silently the moment the host reorganizes, exactly the cross-partition read `cross-doctor-routing.md` warns against (importing a peer's path constant crashes your doctor when the peer moves it).

**Rule:** each repo owns its own code-currency check, surfaced in its **own** doctor — no cross-partition reads of a sibling's git HEAD or version manifest to judge that sibling's staleness. The symmetric shape: host owns host-currency, addon owns addon + corpus currency, consumer owns consumer-currency. Every doctor stays authoritative on its own shape and reaches into none. A code-currency probe is advisory by default — `PASS / WARN / INFO`, exit-0, `interactivity = silent`, no failure-catalog row (it informs, it does not gate) — following the silent-advisory disposition precedent already established by the project-rag host doctor's release-vs-installed steps. When repo A genuinely needs to *surface* repo B's currency, it points the operator at B's doctor via the read-only discovery cascade (`cross-doctor-routing.md`); it does not re-derive B's currency itself. This is the currency-axis instance of the partition-ownership principle that `install-surface-completeness.md` (and its peer `trio-install-surface-coupling.md`) establish for install surfaces: own your surface end-to-end, never reach across the seam to read a sibling's. Working reference: the project-rag host `probe_host_code_currency.py` (gh-release vs installed, advisory) — `docs/plans/2026-06-01-host-code-currency-doctor-probe.md`. [universal]

## First-Party Install-Drift Coverage Is a Doctor Obligation — The Three Reconciliation Axes

*claude-central-EM (DoE ruling on a example-game-workbench-repo consult; PM-extended with the upstream axis). [universal]*

**A repo's own doctor MUST detect that repo's broken / stale / incomplete install conditions first-party. A downstream consumer's chain-triage — or a user hitting a boot-time hard error — discovering the drift *before* the source repo's doctor does is a doctor *coverage bug*, not merely bad luck.** The doctor is the surface whose entire job is install-health; a drift condition that takes the install down while the doctor reads GREEN is the same vacuous-pass failure (§ Divergence-Sentinel Probes Must Fail Loud) raised to the level of a whole *class* of conditions the doctor never probes at all. This coverage-bug tell applies to a repo's own install state — the three axes here; when the drift is a cross-repo CONTRACT mismatch the downstream owns, the downstream finding it first is correct ownership, not a coverage gap — the source doctor probes its own install, not its consumers' expectations of it. The originating evidence (example-game-repo trio, one session): three install-drift conditions across three repos, each first surfaced by a *sibling's* triage or a SessionStart hard error rather than by the first-party doctor.

**The generalizing abstraction — a reconciliation probe.** Every install-drift condition is the same shape: a probe compares a **declared source-of-truth** against the **actually-provisioned state**, and reports drift as a first-party finding. What varies is the *axis* — *which* truth the probe reconciles against (distinct from the three currency axes in § Each Doctor Owns Its Own Code-Currency Surface — axis 3 here is that section’s code-currency axis, surfaced as install drift). These are the three **recurring** axes, not a closed taxonomy — for instance, config/schema-migration drift folds under axis 2 as a required-migration phase:

| Axis | Declared truth | Actual state | Locality | Severity | Maturity in the coordinator |
|---|---|---|---|---|---|
| **1 — version drift** | local source version (`plugin.json .version` / `pyproject`) | installed-artifact version (editable `.dist-info`, on-disk MAPPING) (detected via content-hash, not necessarily a version-string compare) | **local** — all machines | break / stale (RED or AMBER per surface) | **mostly covered** — `check-plugin-drift.py` detects editable-install staleness via pin-path + `pyproject` hash; see `install-surface-completeness.md` § setuptools editable MAPPING |
| **2 — phase reconciliation** | currently-required install phases | completed install phases on this host | **local** — all machines | break / incomplete (RED) | **handled via per-phase self-heal** — phase drift has already fired and the correct resolution was per-phase self-heal (`--setup-only` flag, dist-installer wiring, deprecated `publish-targets.sh` backstop, doctor remediation text); see `install-surface-completeness.md` § Bootstrap gap and § State-Files Written Only by Install Ceremony Never Exist on `source_is_live` Machines for the worked example. Centralized required-vs-completed phase ledger deferred — per-phase self-heal is the proven mitigation for the cases seen so far; build a ledger only if per-phase self-heals stop scaling |
| **3 — upstream-release drift** | latest upstream published release tag (`git ls-remote --tags`) | locally-installed version / SHA | **upstream** — consumer installs only | advisory / nudge (INFO; never a health FAIL) | **covered as a currency check, but NOT yet reachable through the doctor** — `coordinator/bin/release-currency.py` (the SessionStart boot hook that called it has since been removed in the full-kill-keep-fast-orientation SessionStart cutover; the library survives, unwired); see § Boot hook ≠ doctor probe below and § Each Doctor Owns Its Own Code-Currency Surface above |

**Severity is axis-dependent, and must not be collapsed.** Axes 1 and 2 reconcile against *local* truth — the install on *this* machine is broken or stale, so drift is **break-class** (RED/AMBER, gates). Axis 3 reconciles against *upstream* truth — the install is healthy but *behind* — so drift is **advisory** (INFO, exit-0, `interactivity = silent`, no failure-catalog row), per § Each Doctor Owns Its Own Code-Currency Surface and `install-surface-completeness.md` § Post-Consumer Gates Must Be Advisory WARN. Folding "you are behind upstream" into the health verdict cry-wolfs — currency is not integrity.

**Axis 3 is consumer-only by construction, and the gate already exists.** On a source-of-truth machine (anything `propagation_mode = "source_is_live"`, or an authoring clone) local HEAD is *ahead of* the latest published release by construction — you are the thing that cuts the release — so the upstream check would either read "ahead" (meaningless) or false-negative. The correct behavior is **detect source-of-truth and skip the probe entirely**, not tolerate the noise. `release-currency.py` already returns `source_is_live` (silent) on authoring machines — any axis-3 probe inherits this gating for free.

**The network caveat for axis 3.** Axes 1–2 are pure local filesystem reads (work offline, on a plane). Axis 3 needs the network (`git ls-remote --tags`) — so it MUST be opt-in, non-blocking, and degrade to a clean `inconclusive`/silent skip when offline (a doctor that goes RED because GitHub was unreachable is worse than no check; see § `inconclusive` Is a First-Class Probe Status). Its value is also bounded by upstream **release-tagging discipline** — if the publish targets don't reliably cut `v*` tags, `git ls-remote --tags` returns nothing and the probe silently no-ops; a real precondition, not an assumption.

**Boot hook ≠ doctor probe.** Axis 3's coordinator implementation historically lived in a SessionStart *boot hook* (`check-plugin-update-currency`, since removed — see the currency-check note above), not in the *doctor* (`coordinator-doctor-sentinel.py`). For the first-party-coverage obligation to be literally true, an axis the doctrine names as a doctor responsibility should be reachable *through the doctor* — wrap the existing `release_currency_probe` as an advisory, silent, `source_is_live`-gated sentinel probe rather than leaving currency visible only as a transient boot nag. The probe MUST be `triage=false` (cluster/scalpel-callable, excluded from the bare first-pass), `weight=standard`, and degrade to `inconclusive` when offline — so a bare `:doctor` never makes a network call. The boot nag and the doctor probe are complementary surfaces, not substitutes.

This § consolidates rather than replaces: it is the *coverage obligation* that ties together § Each Doctor Owns Its Own Code-Currency Surface (axis 3), `install-surface-completeness.md` § setuptools editable MAPPING (axis 1) and § Doctor surface gaps and the vacuous-pass anti-pattern (the GREEN-while-broken failure this obligation forbids). The three were scattered; this names them as one obligation a doctor is *required* to cover, and marks the "downstream found it first" signal as the coverage-bug tell.

## Manifest Schema — The Eight Verbatim Fields

*project-rag-ue-addon doctor-shape reconciliation.* The cross-repo doctor parity exercise (project-rag host ↔ coordinator ↔ ue-addon ↔ example-game-repo) settled on **eight field names adopted verbatim** across every consumer-claude doctor: `id`, `cluster`, `weight`, `interactivity`, `fix`, `symptom_keywords`, `triage`, `body`. Naming parity is the substrate of routing parity — a `cluster` here, `category` there, `group` somewhere else makes the selection grammar unwriteable across repos.

**Enums and invariants:**

- `weight ∈ {cheap, standard, heavy}` — resource-semantic, NOT latency. A `silent heavy` probe is legitimate; a `heavy` probe in the triage first-pass is not.
- `interactivity ∈ {silent, assert, prompt, prompt-with-cli-override}` — orthogonal to weight.
- `triage = true ⟹ weight ∈ {cheap, standard}` — the triage-first invariant the addressability doctrine depends on (a `heavy` probe in triage is the warhammer-by-default antipattern).
- `fix` = catalog_row_id or the literal string `"none"`.
- **No `order` / `sequence` field** — probe order is the manifest file position (TOML row order). Single source of truth; no parallel ordering substrate to drift.

**Coordinator additive fields.** Coordinator's manifest carries `severity_if_fail` and `remediation` as additive fields — they hold wiki-catalog data the host doctor does not have. Additive (new field names, never re-purposed existing ones) is parity-safe; field-name divergence is not. Sibling doctors adding their own additive fields follow the same rule.

**Probe catalog naming.** Probes live under stable `P-N` identifiers (`P-1`, `P-2`, …) keyed in the manifest by `id`. The catalog is the manifest plus the per-probe implementation; consumers (the `<doctor> <probe-id>` scalpel verb, downstream test fixtures, the remediation contract above) reference probes by `id`, not by manifest position or function name.

*Reference:* `plugins/coordinator/doctor-probes.toml`.

## Corpus Schema Currency — Doctor-Probe + Envelope Shape, Not Identity-on-Disk

*project-rag host ↔ project-rag-ue-addon.* A schema-version currency check between two cooperating plugins is **field-shape parity**, not file-identity matching. The temptation: addon imports the host's `SCHEMA_VERSION` constant, compares to its own, and emits PASS/FAIL on equality. The trap: a per-band line spans schema namespaces (engine-band → engine namespace; project-content-band → graph.db namespace; knowledge/example bands → their own), and no single host constant can express "current vs stale" across all of them. Putting a single host currency value on a per-band line produces a meaningless verdict for the bands in other namespaces.

**Rule:** corpus-schema currency stays at **doctor / query time**, evaluated **per-namespace** — not baked into a per-band startup line, not mirrored as an addon-side constant, not asserted at daemon boot. The doctor probe + envelope shape is what carries the verdict; the on-disk constant identity is not the answer. Per-band startup logs emit shape (`band=<name> corpus_schema_version=<N> min_supported=<M> source=<path>`) without currency verdicts — eager boot-time corpus-open blew the 60s watchdog when previously tried (host evidence). Lazy emission, first-open-per-band, once per process.

Folds with § Each Doctor Owns Its Own Code-Currency Surface — both rules say the same thing at different layers: each side owns its own currency axis (host owns host schema, addon owns addon schema, doctor evaluates at query time), and reaching across to read a sibling's identity to judge currency is the antipattern.

## Probe-Template Author-Time Hazards

*cross-repo rollout of four portable hooks.* Template-authored probes (boilerplate the operator clones into a new doctor) ship hazards that handwritten probes don't — the template author writes once, the hazard fires N times as the template propagates. Three recurring author-time hazards surfaced during the 4-hook rollout:

1. **Hardcoded interpreter shell-out** in template body (`python3` / `bash` / `node`). The hazard is platform variance: `python3` is unreachable from some Windows-Git-Bash shells, `bash` may be 3.2 on stock macOS, and the template's hidden assumption surfaces only when the operator hits the absence. Portable pattern: use the registry / probe-context's resolved interpreter, never an inline literal.
2. **Hardcoded path / drive letter** in the template's "discovery candidate" list. Templates that ship `X:/project-rag` (Machine-a drive) as a discovery seed silently succeed on the author's machine and silently fall through on every other machine. Portable pattern: resolve discovery via `machine-local get <key>` or registry helpers (`$REPO_PROJECT_RAG`), never bare paths. <!-- foreign-path-ok: naming the anti-pattern this rule prohibits -->
3. **Env-var registration discipline missing in `doctor.md`.** A probe that consults `$FOO_AUTOSTART` must (a) document the env var in the doctor's own surface (the slash-command README / skill prose), and (b) be enumerated in a single registry the doctor can list. A probe that reads an undocumented env var is a hidden gating dependency and breaks the remediation-loop contract (the operator can't know what env var to set to clear the FAIL). Folds with § Silent Env-Var-Gated Phase Skips Break the Remediation Loop — that § governs the runtime symptom; this rule governs the author-time prevention.

**Authoring discipline.** Treat the template as the probe's *spec* — it is the surface every clone inherits. The same name-implementation-parser-match discipline (§ Name, Implementation, and Parser Must Match What Each Claims) applies to the template: spec-level review of a template catches what a per-clone code review cannot, because the per-clone review never sees the original template.

## Warmup Probe Pattern — `--full` routing reinforcement

*Reinforcement (ue-addon apply-packet-3).* The warmup-probe pattern composes with the `--full` routing rule: `--full` must route through the canonical `run_all_probes` (warmup included as position-0); a re-implemented list-comprehension that iterates only "real" probes drops the warmup buffer AND drops the inter-probe context stash that the canonical runner threads. Reaffirms the existing rule (`--full` IS `run_all_probes`) — the warmup probe is not exempt from it.

## Cross-Partition Reads — Sibling Layout Hard-Coding Is the Same Antipattern

*Reinforcement (ALL-doctor sweep, post project-rag-host-currency).* Re-confirmed cross-repo: **no doctor reads a sibling repo's layout to make its own verdict.** Sibling probes that hard-code assumptions about another repo's directory structure (`X:/sibling-repo/some/path`) <!-- foreign-path-ok: naming the anti-pattern this rule prohibits --> break silently the moment the sibling reorganizes — exactly the cross-partition coupling § Each Doctor Owns Its Own Code-Currency Surface warns against. The same rule that bans importing a peer's path constant bans hard-coding it.

When repo A genuinely needs to surface repo B's currency, route via the read-only discovery cascade in `cross-doctor-routing.md` (point at B's doctor); when A only needs to know *if* B is reachable, run a presence-check on B's discovery key (`machine-local get repos.<B>`), not a parse of B's git HEAD.

## Regression-Net Probes Must Exercise the User-Facing Invocation Path — Not an Internal Absolute-Path Fallback

A health probe that resolves a tool **absolute-first** (e.g. `$BIN_DIR/<tool>`) and falls back to bare-name only on failure MASKS the bare-name PATH bug it exists to catch. When the probe resolves `machine-local` or `claude-home` via an absolute path and succeeds, it returns PASS even when the bare-name invocation is `command not found` on the user's PATH. The probe's green light proves the absolute path works; it proves nothing about what users and agents actually invoke.

**Empirical origin (machine-c machine-local-bare-invocation-macos).** Doctor probes P-4 and P-10 resolved `machine-local` and `claude-home` via `$BIN_DIR/<tool>` (absolute) first, bare name only as fallback. They PASSed on macOS even when bare invocation was `command not found`, hiding exactly the PATH gap the workstream was fixing. A dedicated P-14 asserting bare-name invocation (`machine-local get`) was added to catch what P-4/P-10 could not.

**Rule.** A regression-net probe must exercise the **user-facing invocation path** — bare name on PATH — not a robust internal fallback. The invariant: the probe must fail under the exact conditions a user or agent would hit failure. An absolute-path-first resolver inside a probe is a green light that proves nothing about what callers actually hit.

The canonical fix: resolve the tool the same way the failing call site resolves it. If users type `machine-local get`, the probe runs `machine-local get`. Any additional absolute-path check is a separate probe with a separate `id`, not a fallback within the user-facing probe.

**Generalizes.** This is the regression-net instance of § A Probe Must Walk the Same Resolution Path as the Runtime Tool It Vouches For — that section governs the probe's resolution logic in general; this rule applies it specifically to the PATH-resolution layer, where the "robust internal fallback" antipattern is endemic in installer-owned tools.

*Pairs with § Probe Authoring Discipline (§ Name, Implementation, and Parser Must Match What Each Claims) — a probe named "bare-name PATH check" that resolves via absolute path first is exactly the name/implementation mismatch that section warns against.*

## Triage Sets Must Include a Functional-Headline Probe Per Critical Surface

Wiring/install/registry coverage alone can return GREEN while a critical capability is completely dead. For every critical surface the doctor covers, at least one **functional-headline probe** — one that calls the actual capability, not just its prerequisites — must be flagged `triage=true`.

**Why:** a probe set covering env vars, install artifacts, and machine-local registry is necessary but never sufficient. If no triage probe actually invokes the capability end-to-end, a user runs bare doctor, sees GREEN, and walks away from a broken system. This is the worst possible outcome: a green doctor that misses real breakage trains the operator to distrust greens.

**Rule:** at probe-set design time, enumerate the critical capabilities the surface exposes. For each, require at least one functional-headline probe (calls the actual capability, verifies an actual response) flagged `triage=true`. Static wiring checks (env vars, paths exist, packages installed) are necessary context but not a substitute. Functional-headline probes must respect the `triage=true ⟹ weight ∈ {cheap, standard}` invariant — a heavy functional probe belongs in its cluster, callable via scalpel/sword selection, not in the default triage first-pass.

**Empirical basis (project-rag-ue-addon):** bare `/project-rag-ue-addon:doctor` verdicted GREEN while engine corpus tools failed with `embed sidecar unavailable: WinError 10061` + Chroma settings-conflict. The 7 triage probes covered env vars, install, and machine-local registry but NO daemon-liveness or engine functional-headline. The probe that would have caught it (`probe_engine_modules_round_trip`) was in the `daemon` cluster with `triage=false`.

*(Source: ue-addon-L24, central-promoted.)*

## Related

- `docs/wiki/cross-doctor-routing.md` — the complementary seam: to *point at* a peer doctor, resolve via a read-only discovery cascade (never import the peer's path constant); the § above establishes that you never reach across to *judge* the peer's currency at all — the peer owns that.
- `docs/wiki/pre-dispatch-verification.md` § Surfacing Probes — probe-without-surface is invisible; § Gate-Verification Mechanics — run the probe in the real interpreter context; § Consumer Parsers Must Verify Producer's Actual Output Shape — read the actual shape, don't infer it.
- `docs/wiki/workstream-complete-review.md` § Dogfood as a structurally distinct review surface — dogfood catches reality errors in operator-environment code (doctors are exactly this class).
- `docs/wiki/implementation-standards-by-domain.md` § Cross-cutting standards — "Detect-then-silently-pick is a footgun. Refactor to detect-then-fail-loud on ambiguity"; `docs/wiki/round-trip-contract-tests.md` — "Tool self-health checks lie; smoke tests prove dispatch, not useful results."
- `docs/wiki/dogfooding-doctrine.md` — binary-outcome rule and smoke-driven fix-through loop for operator-environment code.
- `docs/wiki/step-zero-emitter-contract.md` — the ratified NDJSON probe-line contract (five keys, `status`/`severity` enums, five-escape-in-order sequence, conformance fixture protocol) that consumes the `inconclusive` first-class rule above and extends it to the cross-repo Step Zero probe surface.
