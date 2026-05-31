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

*2026-05-18, project-rag-ue-addon.* A doctor that can only emit pass or fail is forced to lie when it cannot actually determine the answer. A probe that hits an unreachable substrate, a missing prerequisite, or an environment it wasn't designed for will — under a binary verdict model — either false-pass (silently green on a state it never checked) or false-fail (red on a condition that isn't actually broken). Both destroy operator trust: the first because a green doctor that misses real breakage trains the operator to distrust greens; the second because a doctor that cries wolf trains the operator to ignore reds.

**Rule:** codify `inconclusive` (or `skipped` / `unknown` — pick one vocabulary and hold it) as a first-class probe status alongside pass and fail, across every consumer-claude repo that ships doctors. When a probe cannot reach the state it checks, it emits `inconclusive` with the reason — never a fabricated pass or fail. The operator reads `inconclusive` as "this probe couldn't run, here's why," which is honest signal; a fabricated green or red is noise that erodes the whole doctor's credibility. This is the diagnostic-status analog of `coordinator/CLAUDE.md` § Implementation Standards "detect-then-fail-loud on ambiguity" — a probe that can't determine the answer must say so, not silently pick.

## Divergence-Sentinel Probes Must Fail Loud, Not Vacuously Pass

*2026-05-20, claude-unreal-holodeck.* Doctor remediations and the doctrine they enforce drift apart over time — the doctrine moves, the probe's expected-state baseline doesn't. A probe written to detect "config diverges from doctrine" must **fail loud on divergence**, not vacuously pass when its own baseline has gone stale or its check has silently no-op'd. The recurring failure: a sentinel probe whose match condition stops matching (a renamed field, a relocated file, a grep that now returns zero) returns green-because-nothing-matched rather than red-because-the-thing-it-guards-is-gone. A vacuous pass is indistinguishable from a real pass to the operator — and it is exactly the divergence the probe existed to catch.

**Rule:** a divergence-sentinel probe must distinguish "checked and aligned" from "couldn't check" (→ `inconclusive`, above) and must treat "expected marker absent" as a *failure*, not a pass. Anchor the probe on a positive assertion that the guarded state exists and matches, so that disappearance of the guarded surface trips the probe rather than silently satisfying it. Guard against the `set -euo pipefail` + zero-match footgun where a grep-no-match kills the loop and the probe reports success by exiting before it checked anything. (Connects to `pre-dispatch-verification.md` § Surfacing Probes — a probe whose output isn't surfaced is invisible; a probe that vacuously passes is worse than invisible because it actively asserts a falsehood.)

## A Probe Must Walk the Same Resolution Path as the Runtime Tool It Vouches For

*2026-05-20, project-rag-ue-addon.* The deepest fidelity failure: a probe that checks a *different code path* than the runtime tool it claims to verify. When a diagnostic probe resolves a path, reads a config field, or parses an output shape **differently** from how the actual runtime tool does it, the probe and the tool disagree — and the probe produces a false-RED (or false-GREEN) because it is vouching for a path the tool never takes. Field-shape divergence between probe and tool is the recurring signature: the probe reads `config.foo` where the tool reads `config.foo.bar`, or the probe shells out with one interpreter while the tool uses another, or the probe parses a flat list where the tool parses a wrapped envelope.

**Rule:** a probe must walk the *same* resolution path as the runtime tool it vouches for — same path-resolution logic, same config-field access, same interpreter context, same output-shape parsing. Where possible, the probe should call the tool's own resolution code rather than re-implementing it (re-implementation is where the divergence creeps in). Where the probe must stand alone, pin it to the tool's exact field-shape and resolution order, and add a test that fails when the two drift. This is the diagnostic-side instance of `pre-dispatch-verification.md` § Consumer Parsers Must Verify Producer's Actual Output Shape and § Gate-Verification Mechanics ("run the probe IN the dispatch's interpreter context") — a probe is a consumer of the tool's runtime contract, and it must read the *actual* shape, not an inferred one.

## The Unifying Principle

All three rules are the same discipline at different layers of the probe:

| Layer | Failure shape | Rule |
|---|---|---|
| **Status vocabulary** | Binary verdict forces a lie when the answer is unknown | `inconclusive` is first-class |
| **Match condition** | Stale/no-op check passes vacuously instead of catching divergence | Divergence sentinels fail loud, anchor on positive assertion |
| **Resolution path** | Probe checks a different path than the tool → vouches for the wrong thing | Probe walks the tool's exact resolution path |

A probe is a *promise* to the operator: "I checked this, and here is what I found." Every one of these failures breaks the promise in a way that is invisible at read time — the operator sees a clean verdict and trusts it. Probe design is therefore trust-preservation engineering: the probe must mirror what it vouches for faithfully, and report what it actually saw honestly, or it is worse than no probe at all (a missing probe prompts caution; a lying probe prompts misplaced confidence).

## Single-Entry-Point Consolidation Must Stay Addressable

> The three rules above govern a single probe's *internals*. This rule governs the doctor's *surface* — the shape of the entry point all the probes hang off.

**Single-Entry-Point consolidation must pair with selective addressability, or the entry point becomes a hammer.** The Single-Entry-Point doctrine consolidates health behind one verb (no `/fix-X` / `/check-Y` proliferation — health lives in the doctor, period). That instinct is correct and stays. But consolidation has a missing second half: the one verb must stay **aimable**. A consolidated doctor with no way to run a subset fires its *entire* probe battery on every invocation — and the moment some of those probes are expensive (spawn a server, load a model, touch VRAM), the single surface degrades into a warhammer that pays cost the situation never asked for. Consolidation without addressability is the failure mode; the two are not separable.

*Empirical origin (2026-05-27, project-rag).* The project-rag host's doctor committed ~43 GiB at boot because a `silent` tool-smoke probe ran all 40 handlers on every invocation; the host froze ~12×. The acute bug was one heavy probe, but the chronic shape was "consolidated surface, no addressability." The fix proved the pattern below on a real surface (host plan `docs/plans/2026-05-27-doctor-scalpel-not-hammer-overhaul.md`, shipped + dogfooded green). This doctrine is seeded from that proven implementation, not a planned one.

### What a good doctor shape is

1. **Triage-first by default.** Bare invocation runs a cheap first-pass (cheap localization checks only), emits a structured read + a recommendation of which cluster/probe to look at, and **stops** — it does not auto-escalate into the heavy probes it recommends. The agent (or operator) aims the next step. A bare invocation that fires everything is the warhammer this doctrine indicts; a doctor whose *default* is fire-everything teaches the anti-pattern by example.
2. **A declarative manifest is the SSOT for probe metadata.** One entry per probe carrying, at minimum: `id`, `cluster` (symptom group), `weight` (resource-semantic: `cheap` / `standard` / `heavy` — NOT latency), `interactivity` (orthogonal to weight), `triage` (in the cheap first-pass?), `symptom_keywords`. The registry / interactivity / inventory surfaces are **derived from or validated against** the manifest, not hand-synced across N files.
3. **Weight and interactivity are orthogonal axes.** Interactivity ("does this probe need a human?") carries no cost information. A `silent` probe can be `heavy`. Conflating them is how an expensive probe ends up running unconditionally. The triage invariant: `triage=true ⟹ weight ∈ {cheap, standard}`, never `heavy`.
4. **A selection grammar makes the one verb aimable** — scalpel / sword / warhammer, parameterized, NOT scattered into new commands: `<doctor> <cluster>` (sword: one cluster), `<doctor> <probe-id>` (scalpel: one probe), `<doctor> <symptom>` (match `symptom_keywords`), `<doctor> --full` (warhammer: the rare explicit "check everything"). Single-Entry-Point is preserved — it is one surface, parameterized, not a proliferation of verbs.
5. **VALIDATE-not-GENERATE at rest.** Derived artifacts are committed; a CI tripwire asserts `regenerate(manifest) == committed` (the test IS the generator in `--check` mode). There is no on-demand generator without a paired drift gate — a stale generated file must fail CI exactly as a hand-sync miss would, but there is now ONE authored source.

### The cargo-cult guard — machinery transfers, motivation does not

The *machinery* (manifest-SSOT, triage-first, selection grammar, VALIDATE-not-GENERATE) is the universal, transferable shape. The *founding motivation* — resource cost — is not universal. A doctor whose probes are all cheap (file reads, CLI smoke, a short-lived subprocess) gains the **addressability** half of this doctrine — aim a subset when debugging — but does **not** need the resource-regression-net (peak-RSS / spawn-count budget tests) an expensive-probe doctor needs. Adopting the resource apparatus for a cheap-probe doctor is cargo-culting a motivation that does not apply.

- **Expensive-probe reference:** the project-rag host doctor (75 probes, several spawn servers / load torch / touch VRAM). Resource-boundedness is its founding goal; it carries the four-dimension RSS regression-net.
- **Cheap-probe reference:** the coordinator doctor (`coordinator-doctor-sentinel.sh`, ~13 probes — file reads, machine-local CLI smoke, one live-whoami subprocess; none `heavy`). It adopts addressability + manifest shape; it does **not** carry the resource-regression-net, because there is no resource problem to bound. Its `weight` field exists for shape parity, not because any probe is expensive.

A consolidated diagnostic surface also stays **probe + addressability only** at this layer — it does not silently grow a diagnose+remediate (mutation) elevation. (The project-rag host bounds this as its WS-R rule: `--fix` adds visibility, never new remediation surface.) Addressability is about *aiming what you read*, not about *expanding what you change*.

### Beyond doctors

The rule generalizes to **any consolidated command or diagnostic surface**: when you collapse N scattered verbs into one (the correct anti-proliferation instinct), pair the consolidation with a selection grammar so the one surface stays aimable. Consolidation that forfeits addressability trades verb-sprawl for a hammer — a different anti-pattern, not a fixed one.

**`--full` must route through the canonical `run_all_probes`, not a re-implemented list-comprehension.** A `--full` branch that builds `probe_results = [fn(ctx) for _, fn in subset]` (a) drops the inter-probe context stashing that `run_all_probes` does (C-0's context feeds downstream probes), and (b) bypasses the `run_all_probes` symbol that renderer/verdict/sentinel tests mock — so mocked fixtures never flow and the tests fail. Rule: the full sweep IS `run_all_probes`; reserve subset-iteration for genuine cluster/probe/symptom selectors. When a refactor adds a new dispatch path that subsumes an existing canonical function, route through the function, don't re-implement its loop. (2026-05-27, project-rag-ue-addon doctor-scalpel Chunk 6.) [universal]

**A consolidated verb without a declarative probe manifest is addressability theater.** The manifest (per-probe `id`, `cluster`, `weight`, `triage`, `symptom_keywords`) is what makes the verb aimable — without it, `<doctor> <cluster>` or `<doctor> <probe-id>` has no SSOT to route against, and the selection grammar is hand-waved. Consolidation without addressability degrades into a warhammer; a declarative manifest is the concrete artifact that closes that gap. → `docs/wiki/doctor-probe-design.md` § What a good doctor shape is.

## Warmup Probe Pattern for Environmental Cold-Boot

**A sacrificial first-position probe absorbs environmental cold-boot cost — use separate timeout budgets and a `warmup_absorbed` summary bucket that doesn't pollute the error count.**

When a tool's first invocation in a fresh server session pays a non-deterministic environmental cost (AV scan on process creation, JIT compilation, model load, DNS warmup), a dedicated `d0-warmup` probe at bank position 0 is the cleanest fix. The warmup gets a `--cold-timeout` budget; real probes get `--warm-timeout`. The warmup probe's status — whether `ok`, `tool_error/timeout`, or runner-side `timeout` — does not increment the error count; it lands in a `warmup_absorbed` summary bucket. Empirical proof of self-sufficiency: 0 errors on a Dev Drive with no AV exclusions applied, once the warmup probe absorbed the cold-boot cost.

Generalizes beyond AV cold-boot to any environmental variance in the first-call cost. The pattern is cheap (one extra probe, one extra bucket) and eliminates "my machine is fast, CI is flaky" non-determinism. (2026-05-27, project-rag-ue-addon Chunk 6 dogfood.)

## Diagnostic Remediation Is a Contract, Not a Suggestion

*Source: holodeck `tasks/lessons.md` (holodeck-L161, central-promoted 2026-05-28) — DoE-authored mirror.* A probe that says "run X to fix this" must have been verified that X actually fixes it on the current code path. The recurring failure: a remediation pointer that *looks* sensible (the right slash-command, the right script name) but whose target doesn't actually execute the phase the probe is checking — so two doctor runs return identical FAIL with no signal anything has changed. The operator runs the remediation, the probe stays red, and trust collapses.

**Rule:** every probe FAIL has a closed remediation loop. Either (a) the remediation runs a step the probe re-checks on next invocation, (b) the remediation is a `manual:` instruction the probe cannot auto-verify (still acceptable — operator owns the loop), or (c) the remediation is `setup-resolves` on opt-in (the probe declares that running `/setup` clears the failure). Anchor the contract in a test gate that enumerates allowed remediation shapes — a `recover-step` pointing at a setup phase that doesn't run is the bug class to catch. The empirical incident (Probes 9/10 → `/holodeck:setup`) was exactly this: remediation pointer looked sensible, setup silently skipped the watchdog phase, two consecutive runs returned identical FAIL. Folds with § Divergence-Sentinel Probes Must Fail Loud — a remediation that doesn't actually remediate is a vacuous pass in disguise.

## Silent Env-Var-Gated Phase Skips Break the Remediation Loop

*Source: holodeck `tasks/lessons.md` (holodeck-L157, central-promoted 2026-05-28) — DoE-authored mirror.* When a setup/recovery script consults an env var to decide whether to run a load-bearing phase, the absence path is the trap: an unset env var that defaults to *skip* makes the script silently no-op the phase, the probe stays failing, and the operator sees identical state across runs with no indication the phase was skipped at all. The probe and the script disagree about whether work happened, and the divergence is invisible.

**Rule:** any script gating a load-bearing phase on an env var must (a) **default-on with explicit opt-out**, never default-off with implicit opt-in, and (b) emit a **structured skip event** the diagnostic surface can detect (a log line, a status field, a sentinel file — whatever the surrounding diagnostic layer consumes). The structured skip event is what closes the remediation loop the rule above demands: a probe can now distinguish "phase ran and failed" from "phase silently skipped," and the operator sees the actual cause. Default-on is the design-as-offers stance applied to invisible defaults — make the script's behaviour announce itself, not require the operator to suspect a gating env var exists. Empirical incident: `HOLODECK_WATCHDOG_AUTOSTART` defaulted to skip; `/holodeck:setup` silently no-op'd the watchdog phase; Probes 9/10 returned identical FAIL across two runs with zero signal anything had changed.

## A Probe Asserting a Retired Invariant Manufactures False RED — Gate/Retire Probes Atomically with Contract Flips

*2026-05-30, claude-unreal-holodeck.* A doctor probe that still asserts an invariant the codebase has since retired manufactures a **false-positive RED**: the contract moved (a bake-time guarantee became a runtime one, a required field became optional, a path moved), the runtime is correct, but the probe vouches for the *old* contract and fails the operator on a state that is actually healthy. This is the temporal twin of the divergence-sentinel vacuous-pass above — there the probe's check went stale and passed silently; here the probe's *assertion* went stale and fails loudly against the new truth.

**Rule:** retire or re-gate the probe in the **same change** that flips the contract it checks — a bake→runtime move, an enum widening, a required→optional relaxation. A contract flip and its probes are one atomic edit, never two. The recurring failure is shipping the contract change and leaving the probe to be reconciled "later" — between the flip and the reconciliation, every doctor run reads RED on a healthy runtime, and the operator learns to ignore the doctor. Fold with `verification-before-completion.md` § Health probe anchoring (anchor to the canonical artifact) and the premise-pass discipline in `coordinator/CLAUDE.md` § Pre-Dispatch Verification (a contract reversal must reconcile code + probe + doctrine-doc in one change).

## Related

- `docs/wiki/pre-dispatch-verification.md` § Surfacing Probes — probe-without-surface is invisible; § Gate-Verification Mechanics — run the probe in the real interpreter context; § Consumer Parsers Must Verify Producer's Actual Output Shape — read the actual shape, don't infer it.
- `docs/wiki/session-end-review.md` § Dogfood as a structurally distinct review surface — dogfood catches reality errors in operator-environment code (doctors are exactly this class).
- `coordinator/CLAUDE.md` § Implementation Standards — "Detect-then-silently-pick is a footgun. Refactor to detect-then-fail-loud on ambiguity"; § Verification Before Done — "Tool self-health checks lie; smoke tests prove dispatch, not useful results."
- `docs/wiki/dogfooding-doctrine.md` — binary-outcome rule and smoke-driven fix-through loop for operator-environment code.
