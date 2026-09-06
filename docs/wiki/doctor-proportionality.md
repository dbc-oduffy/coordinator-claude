<!-- RAG-bait: doctor proportionality, when does a component earn a doctor skill vs scripts, delegation bloat, probe theater, doctor-vs-scripts decision rule, health-verification proportionality -->
<!-- distilled: run 2026-07-19-synth; sources: archive/specs/2026-05/2026-05-27-doctor-shape-doe-alignment.md, 2026-05-19-cross-plugin-whoami-contract.md -->

# Doctor Proportionality

**Purpose.** A citable rule for deciding *how much* health-verification machinery a component earns: a doctor **skill**, a doctor **wiki**, or just **fail-loud scripts** (+ optionally one host-contributed probe). It exists so the wiki-vs-skill-vs-scripts choice is made by rule rather than per-repo instinct — the instinct default over-builds (every component grows a `/doctor` skill) and the over-build is pure cost: a command that points at another command, or a probe-set that tells the operator nothing the failing script already did.

**What this is not.** Not a replacement for [`coordinator-doctor.md`](coordinator-doctor.md) (the coordinator-substrate health surface + citation contract) or [`doctor-probe-design.md`](doctor-probe-design.md) (how to design a probe once you've decided you need one). This wiki is upstream of both: it decides *whether* a component warrants a doctor at all, and in what form.

## The rule

**A doctor SKILL earns its place only when a component has genuine *aggregate* doctor surface — many independent failure modes an operator/agent must triage *across*.** Everything thinner gets fail-loud idempotent scripts + (optionally) a single failure-catalog probe contributed to the HOST / coordinator doctor. It does **not** get its own skill.

The discriminator is **aggregate triage surface**, not component importance. An important component with one failure mode does not earn a skill; a modest component with a dozen independent, cross-cutting failure modes might.

## Two anti-patterns the rule names

1. **Delegation bloat.** A doctor skill whose probes mostly re-surface another doctor's verdicts (e.g. a downstream doctor that mostly re-runs coordinator wiki-doctor probes per the citation contract) is a command that exists to point at another command. The citation contract is satisfied by a **one-line pointer**, not a whole skill. → `coordinator-doctor.md` §5 (citation contract, THIRD-PATH-CLOSED).

2. **Probe theater on thin components.** For a thin component, a probe-set adds no information the failing setup script didn't already give: *if the scripts don't work, they don't work, and no probe-set will help.* Honest verification for thin things = **idempotent fail-loud scripts** (bad post-condition → specific non-zero exit + remediation) + at most one host-contributed failure-catalog probe.

Both anti-patterns share a root: treating "has a `/doctor`" as a maturity signal rather than a response to real aggregate triage surface.

## The spectrum (form by surface)

| Form | When | Example |
| --- | --- | --- |
| **Wiki-form doctor** | Shared substrate other components cite; a runnable probe catalog + citation contract, but not an interactive flow. | **coordinator-claude** — `coordinator-doctor.md` (machine-local substrate, cited by downstream doctors). |
| **Skill-form doctor** | Genuine aggregate surface: multiple planes, live bindings (MCP), fleet-consumer contract drift — an operator must *triage across* many independent failure modes. | **cockpit** — multiple planes, live MCP bindings, fleet-consumer contract drift. Warrants a real branching skill; should lean in. |
| **Scripts + one host probe** | Thin component: few failure modes, each caught by its own setup script's post-condition. | **example-market-data-repo** — thin producer addon: fail-loud scripts + one failure-catalog probe (`MI-F-1`) contributed to the host. Deliberately **no** doctor skill. |
| **Collapse candidate** | A skill that on inspection is delegation bloat or probe theater — collapse to scripts + host probe. | **claude-klabauter** — collapsed: retired its `/claude-klabauter:doctor` plugin skill to scripts + host probe (`bin/claude-klabauter-doctor-probe.py`), per claude-klabauter's `docs/plans/2026-07-20-retire-claude-klabauter-plugin-surface.md`. |

*(The cockpit/claude-klabauter/example-market-data-repo classifications are illustrative of the rule; the actual collapse/invest decisions belong to those repos' EMs responding to their own copies of the originating memo — this wiki authors only the central citable principle.)*

## Decision procedure

To classify a component:

1. **Count independent failure modes an operator must triage across** (not "is this component important?"). Independent = a distinct root cause with a distinct remediation, not a re-surface of another doctor's verdict.
2. **≥ several independent, cross-cutting modes → skill-form.** The operator needs a branching triage surface. Design its probes per `doctor-probe-design.md` (triage-first default, `--full` as explicit warhammer).
3. **Shared substrate others cite, but not interactive → wiki-form.** A probe catalog + citation contract (the `coordinator-doctor.md` shape). A downstream doctor cites `P-N` rather than reinventing the probe.
4. **Few modes, each caught by a setup script's post-condition → scripts + one host probe.** Make the scripts idempotent and fail-loud (bad post-condition → specific non-zero + remediation). Contribute at most one failure-catalog probe to the host/coordinator doctor. Do **not** author a skill.
5. **If an existing doctor skill fails 1–2 → collapse it** to the appropriate thinner form; the skill is delegation bloat or probe theater.

## The cargo-cult guard: machinery vs. founding motivation

<!-- src: plan12-015 -->

Two of the components on the spectrum above are named as **references**, not just examples — and the distinction matters more than it looks: **coordinator-claude** (the cheap-probe reference) and the **project-rag host doctor** (the expensive-probe reference, `mcp__*project-rag*`'s own health surface, the proving ground this doctrine was seeded from — see § Origins below).

The reason both are named explicitly: this wiki's *machinery* — manifest-as-SSOT, triage-first default, the cluster/probe/symptom selection grammar, VALIDATE-not-GENERATE — is universal and travels to any doctor regardless of probe cost. The *founding motivation* for some of that machinery (resource cost — project-rag's probes are individually expensive, so triage-first exists to avoid firing the whole battery on every invocation) is **not** universal. A cheap-probe doctor (coordinator's own — probes are near-free) that adopts the full resource-conservation apparatus because "that's what a real doctor looks like" is cargo-culting: copying the ceremony without the cost that justified it.

Practical read: when standing up a new doctor, ask *why* each piece of machinery exists in the reference implementation before importing it. If the reason was "probes are expensive," and yours aren't, the machinery may still be worth keeping for addressability (see the rule above) — but keep it because you decided it earns its place, not because the reference had it.

## Origins

<!-- src: plan12-013, plan09-009 -->

This doctrine was not planned top-down — it was **seeded from a proven implementation**. The project-rag host doctor overhaul (`archive/specs/2026-05/2026-05-27-doctor-shape-doe-alignment.md`) is the proving ground: single-entry-point consolidation + selective addressability + manifest-as-SSOT were built and shipped there first, then generalized into this wiki's citable rule. A second seeding pass (example-market-data-repo-em's `doctor-proportionality-doctrine-candidate` memo) added the thin-component classification (scripts + one host probe, collapse candidates) from a different empirical angle. Both seedings are evidence-first, not spec-first — consistent with this repo's general doctrine-from-implementation posture.

**Layering note.** Where a doctor's defining contract lives matters as much as its form. When coordinator-claude inherited the whoami/machine-local substrate (`archive/specs/2026-05/2026-05-19-cross-plugin-whoami-contract.md` — the wiki page this cited has since been retired along with the package itself), the ratified call was that coordinator-claude — not a cross-plugin layer sitting above it — is the correct primitive layer for the doctor that checks that substrate: a doctor at a higher layer would inherit the writer-boundary doctrine without owning the substrate that defines "conformant." The general form of this: **the doctor for a contract lives at the layer that ships the contract**, not at a layer that merely consumes it.

## Cross-links

- [`coordinator-doctor.md`](coordinator-doctor.md) — the wiki-form exemplar + the citation contract that makes downstream delegation a one-liner (the anti-delegation-bloat mechanism). Its §"What this wiki is not" is this rule applied to itself: a non-interactive verification surface is a wiki, not a skill.
- [`doctor-probe-design.md`](doctor-probe-design.md) — once you've decided a component needs probes, how to design them (triage-first, selective addressability).
- [`guard-proportionality.md`](guard-proportionality.md) — the sibling rule on the refusal side: how much blocking machinery a fact earns (necessity / duration / outlet), and the standing-guard antipattern it names.
- Single-Entry-Point consolidation + selective addressability (coordinator `CLAUDE.md` § Implementation Standards) — the same discipline one altitude down: one health surface AND aimable.

<!-- seeded 2026-07-08 from example-market-data-repo-em doctor-proportionality-doctrine-candidate memo; ratified at DoE altitude -->
