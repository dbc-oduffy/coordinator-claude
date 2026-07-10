<!-- RAG-bait: doctor proportionality, when does a component earn a doctor skill vs scripts, delegation bloat, probe theater, doctor-vs-scripts decision rule, health-verification proportionality -->

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
| **Wiki-form doctor** | Shared substrate other components cite; a runnable probe catalog + citation contract, but not an interactive flow. | **coordinator-claude** — `coordinator-doctor.md` (machine-local + whoami substrate, cited by downstream doctors). |
| **Skill-form doctor** | Genuine aggregate surface: multiple planes, live bindings (MCP), fleet-consumer contract drift — an operator must *triage across* many independent failure modes. | **cockpit** — multiple planes, live MCP bindings, fleet-consumer contract drift. Warrants a real branching skill; should lean in. |
| **Scripts + one host probe** | Thin component: few failure modes, each caught by its own setup script's post-condition. | **example-market-data-repo** — thin producer addon: fail-loud scripts + one failure-catalog probe (`MI-F-1`) contributed to the host. Deliberately **no** doctor skill. |
| **Collapse candidate** | A skill that on inspection is delegation bloat or probe theater — collapse to scripts + host probe. | **example-orchestration-hub** — thin; a `/example-orchestration-hub:doctor` that looks like probe theater is a collapse candidate. |

*(The cockpit/example-orchestration-hub/example-market-data-repo classifications are illustrative of the rule; the actual collapse/invest decisions belong to those repos' EMs responding to their own copies of the originating memo — this wiki authors only the central citable principle.)*

## Decision procedure

To classify a component:

1. **Count independent failure modes an operator must triage across** (not "is this component important?"). Independent = a distinct root cause with a distinct remediation, not a re-surface of another doctor's verdict.
2. **≥ several independent, cross-cutting modes → skill-form.** The operator needs a branching triage surface. Design its probes per `doctor-probe-design.md` (triage-first default, `--full` as explicit warhammer).
3. **Shared substrate others cite, but not interactive → wiki-form.** A probe catalog + citation contract (the `coordinator-doctor.md` shape). A downstream doctor cites `P-N` rather than reinventing the probe.
4. **Few modes, each caught by a setup script's post-condition → scripts + one host probe.** Make the scripts idempotent and fail-loud (bad post-condition → specific non-zero + remediation). Contribute at most one failure-catalog probe to the host/coordinator doctor. Do **not** author a skill.
5. **If an existing doctor skill fails 1–2 → collapse it** to the appropriate thinner form; the skill is delegation bloat or probe theater.

## Cross-links

- [`coordinator-doctor.md`](coordinator-doctor.md) — the wiki-form exemplar + the citation contract that makes downstream delegation a one-liner (the anti-delegation-bloat mechanism). Its §"What this wiki is not" is this rule applied to itself: a non-interactive verification surface is a wiki, not a skill.
- [`doctor-probe-design.md`](doctor-probe-design.md) — once you've decided a component needs probes, how to design them (triage-first, selective addressability).
- Single-Entry-Point consolidation + selective addressability (coordinator `CLAUDE.md` § Implementation Standards) — the same discipline one altitude down: one health surface AND aimable.

<!-- seeded 2026-07-08 from example-market-data-repo-em doctor-proportionality-doctrine-candidate memo; ratified at DoE altitude -->
