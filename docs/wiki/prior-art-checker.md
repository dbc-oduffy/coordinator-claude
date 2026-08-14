---
title: prior-art-checker pre-review doctrine
created: 2026-05-06
type: doctrine
---

# prior-art-checker Pre-Review Doctrine

## What is prior-art-checker?

prior-art-checker is a Sonnet-tier agent that cross-references a plan artifact against the coordinator's accumulated prior art before the artifact reaches an Opus reviewer. It reads the plan, enumerates its claim surface, then searches its corpus inventory — project wikis (`docs/wiki/` recursively, including subdirectories `marketplace/`, `opensource/`, `competitors/`, and `codebase-judgment/`), global wikis (the Claude Code meta-repo's `docs/wiki/`), the coordinator doctrine wiki, decision records, `state/lessons/` (per-entry YAML, not a flat file), skill definitions, and the central improvement queue — and reports each claim as **Conflict**, **Compatible-but-relevant**, or **Silent**.

The output is a sidecar at the plan-derivable `state/plan-sidecars/<plan-stem>.prior-art-check.md` home (D0). The agent makes no judgments and applies no fixes; it surfaces matches with verbatim quotes for the EM to disposition.

The result: Opus reviewers receive a plan that has already been cross-referenced against captured wisdom and can focus their attention on architecture and approach instead of re-deriving lessons we have already learned.

## Why this exists — the capture-recall loop

The coordinator system captures lessons via `state/lessons/` (per-entry YAML) → `learn-lessons` → `docs/wiki/` and the central improvement queue. **Capture is mature; recall was broken.**

Wikis sat in `docs/wiki/` without being part of any EM's default context. The EM rarely read them at plan time. Lessons promoted to wikis silently decayed because nothing in the workflow reached for them. The fix was not more wikis — it was a process loop that consults them automatically.

prior-art-checker is the recall side of the loop. Without it, captured wikis are storage; with it, captured wikis become live doctrine that shapes plans before they ship.

## What counts as "prior art"

Two kinds, both equally in scope:

1. **Doctrine** — rules about how things should be done. Project-agnostic patterns, conventions, anti-patterns. Examples: `test-design-discipline.md`, `cleanup-sweep-hazards.md`, `round-trip-contract-tests.md`.
2. **Institutional memory** — project-specific history. What we tried, what broke, why we made the call we did. Examples: `daily-branch-discipline.md` (born of a real incident), `scoped-safety-commits.md` (born of audit-trail corruption).

Both are equally important. A plan can be doctrinally fine and still violate a project-specific decision; a plan can be project-fine and still violate doctrine. The agent checks both corpora every run.

## Role in the review pipeline

**The prior-art-checker is a recall pre-flight, not a reviewer.** It does not participate in the sequential-review HARD RULE — it runs once before any reviewer is dispatched and its output is consumed by all downstream reviewers. Running it does not satisfy the "sequential" requirement; it sits upstream of the reviewer sequence entirely.

## When does it run? — EM Decision Rules

| Artifact type | Default | EM discretion |
|---|---|---|
| **Plan documents** (`docs/plans/*.md`, the meta-repo's `plans/*.md`) | **Run by default.** | Skip only when the plan is a single-file mechanical bug-fix with no architectural decision. |
| **Enriched stubs with architectural decisions** | Run when chunks introduce a new pattern, new agent, new convention, or modify cross-cutting doctrine. | Skip for stubs that are mechanical execution of a previously-checked plan. |
| **Code review (no plan artifact)** | Skip. | Run when a PR/diff lacks a plan but introduces a new pattern worth checking against doctrine. |
| **Pure prose** (lessons, postmortems, retros, strategy memos) | Skip. | None — no claim surface to cross-reference. |
| **Trivial single-file edits** | Skip. | None — overhead exceeds the benefit. |

**Special case — premise reversals.** When a plan reverses a prior decision (regenerates torn-down structure, re-introduces a pattern we previously removed), ALWAYS run the prior-art-checker. This is exactly the case where prior art most matters; per the coordinator's "Premise-pass before regenerating torn-down structure" rule, the prior-art-checker is the mechanical implementation of that premise pass.

**Special case — destructive surfaces.** Any plan touching destructive code (`rm -rf`, delete, truncate, drop-table, unlink of consumer-durable data) ALWAYS runs the prior-art-checker AND the coverage pre-flights — the "single-file mechanical bug-fix" skip does NOT apply when the fix touches a destructive path. The mechanism is a *partial-read false-clear*: clearing a hazard ("no over-broad `rm -rf` here") from a partial function read is not a clear at all. *Canonical:* at pickup a "no over-broad `rm -rf`" premise was cleared after reading `uninstall_remove_substrate()` only to line 632; the prior-art-checker read the FULL function and caught a live shipped `rm -rf $sh` at line 641 that would have deleted consumer durable data. Never assert absence of a hazard from a partial function read — the checker's whole-function read is exactly what earns its cost on destructive surfaces.

**Skip is silent.** No flag needed, no justification required. EM judgment.

## Output format

```markdown
## Prior-Art Verification

**Plan:** <path>
**Verdict:** COMPATIBLE | WARN | BLOCKED-SURFACE-TO-PM | DEGRADED
**Claims checked:** N
**Conflicts:** X | **Compatible-but-relevant:** Y | **Silent:** Z

### Conflicts (plan contradicts prior art)
[verbatim quotes from prior art with EM-action suggestions]

### Compatible-but-relevant (plan should cite or align)
[verbatim quotes with citation suggestions]

### Silent areas (no prior art found)
[bulleted list of uncovered claims]
```

The verdict is advisory. The agent never auto-blocks; only the EM/PM may halt a review.

## Prior-art mutability — director-tier reviewer override path

Prior art is not immutable doctrine. When a PM-authorized director-tier reviewer (the Director of Engineering, or the Staff Engineer elevated by PM brief) finds that a captured wiki/lesson is outdated, vague, or wrong, they have explicit authority to override the prior-art-checker's conflict finding and direct the integrator to update the prior art rather than the plan. The integrator records the override decision and edits the wiki/lesson/queue as a first-class deliverable of the review pass — same commit, same review trail.

**When the override applies:**

- The plan deliberately reverses a captured pattern the project has since outgrown.
- The wiki entry was captured from a one-off incident and overstated as universal.
- The lesson was captured before a structural change that made it inapplicable.

**Required brief framing.** The dispatching EM MUST surface the override authority verbatim in the director-tier reviewer's brief — e.g. *"You may direct the integrator to update prior art (wiki/lesson/queue) rather than the plan when the captured pattern is itself the problem. Cite the wiki entry and reason in your finding."* Without the verbatim elevation, the reviewer defaults to plan-side correction per the standard direction-of-correction enum (`update-plan` / `update-prior-art` / `both` / `override-and-document` / `PM-input-needed`).

**Companion doctrine:** the reviewer-pipeline doctrine's section on reviewer elevation past charter — for the mechanics of PM-authorized reviewer elevation generally.

## Verdict semantics

- **COMPATIBLE** — zero conflicts; compatible-but-relevant items are informational only. Proceed to Opus reviewer dispatch.
- **WARN** — one or more conflicts surfaced. EM (with reviewer + integrator help) picks a direction-of-correction per conflict before dispatching the Opus reviewer: `update-plan`, `update-prior-art`, `both`, `override-and-document`, or `PM-input-needed`. "WARN" does not mean "plan is wrong" — it means "two surfaces disagree; pick which to update." See § Bidirectional resolution.
- **BLOCKED-SURFACE-TO-PM** — one or more conflicts contradict load-bearing doctrine (scoped-safety-commits, daily-branch-discipline, round-trip-contract-tests, sequential-review HARD RULE, etc.) OR contradict explicit institutional memory recording a past incident. EM **must** escalate to PM before continuing. Do not dispatch the Opus reviewer until the conflict is resolved or PM authorizes override.
- **DEGRADED** — the agent ran with materially incomplete coverage. Emitted when: (a) Phase 1 capped at 30 claims and the plan has significantly more, (b) Stuck Detection fired ≥1 time, (c) a corpus was unreadable, or (d) estimated token cost exceeded 50K. Treat DEGRADED as no signal — review the plan fully against prior art as if no pre-flight ran. DEGRADED does not block; it flags unreliable coverage.

## Hard prohibitions — prior-art-checker must NOT

- Edit the plan inline. The agent writes exactly one file: the sidecar.
- Edit any wiki, lesson, or queue file (read-only against the corpus). Wiki/registry/lessons amendments arising from a Conflict are landed by the review-integrator after the EM picks a direction — not by the prior-art-checker itself.
- Apply auto-fixes of any kind. Recall is judgmental — even compatible-but-relevant findings could be wrong, and conflict resolutions need EM/PM input.
- Fabricate prior art. If a claim is silent, the agent says so. Inventing citations is worse than reporting a gap.
- WebSearch for general guidance. The agent checks **our** prior art, not the open internet's.
- Auto-block a plan. Only the EM/PM may halt a review.

## Distinction from docs-checker

The two pre-flights answer different questions:

| | docs-checker | prior-art-checker |
|---|---|---|
| **Question** | Are these external API claims factually correct? | Have we already established something relevant about this? |
| **Corpus** | Context7, LSP, project-RAG, cppreference | Project wikis, global wikis, `state/lessons/`, central improvement queue |
| **Output** | Per-claim verification table (VERIFIED / UNVERIFIED / INCORRECT) | Three-bucket sidecar (Conflict / Compatible-but-relevant / Silent) |
| **Authority** | AUTO-FIX allowlist for tradeoff-free corrections | REPORT-ONLY — EM dispositions all findings |
| **Surface** | reviewer pipeline Phase 2.7 | reviewer pipeline Phase 2.7b |

They are not substitutes; they can both run on the same artifact.

## Sidecar format note

Sidecars use `kind:` rather than `type:` in their frontmatter to distinguish machine-emitted artifacts from authored docs. docs-checker sidecars should adopt the same convention when they are next revised (not in scope for this commit — surfaced as a follow-up).

## Distribution

The reviewer-side consumption block is synced via `verify-snippet-sync prior-art-check-consumption --fix` (an engine-resident script) from `plugins/coordinator/snippets/prior-art-check-consumption.md` to all Opus reviewer prompts:

- `plugins/coordinator/agents/staff-eng.md` (the Staff Engineer)
- `plugins/coordinator/agents/eng-director.md` (the Director of Engineering)
- a game-dev sibling repo's `game-dev/agents/staff-game-dev.md` (the Game Dev Reviewer — resolved via a machine-local sibling-repo registry key; skipped when that repo is absent locally; `game-dev` is not part of the OSS `coordinator-claude` distribution)
- `plugins/coordinator/agents/staff-data-sci.md` (the Data Science Reviewer)
- `plugins/coordinator/agents/senior-front-end.md` (the Front-End Reviewer)
- `<plugin-consumer>/game-dev/agents/staff-game-dev.md` (optional domain-plugin the Game Dev Reviewer variant)

The sync verifier is auto-discovered by `/update-docs` Phase 11b.

## Prior art is current best-state, not eternal law

Wikis, lessons, and registries record what we believed at last write-time. They are the corpus a new plan should align with *by default* — but they are not immutable. A plan that contradicts prior art may be the plan capitulating to the wiki, OR it may be the wiki needing revision because the plan is the corrective. Treating every conflict as "plan must yield" turns the prior-art-checker into a freeze mechanism; treating every conflict as "wiki is stale" turns it into noise. Neither is right.

The discipline: every Conflict is a **direction-of-correction question**, answered by the EM with reviewer + integrator input. The candidate directions (defined in the agent prompt) are `update-plan`, `update-prior-art`, `both`, `override-and-document`, and `PM-input-needed`. The sidecar surfaces the conflict and may offer a lean; the call is the EM's.

## Bidirectional resolution — who applies which edit

Once the EM has picked a direction per Conflict, edits land via the integrator chain after the Opus reviewer's normal pass:

| Direction | What lands | Where |
|---|---|---|
| `update-plan` | Plan amendment folding prior art in | The plan artifact |
| `update-prior-art` | Wiki/registry/lessons amendment | The cited prior-art file(s) |
| `both` | Plan amendment + prior-art amendment | Both surfaces, in one integration pass |
| `override-and-document` | One-line entry in plan's "Considered alternatives" citing prior-art quote and override rationale | The plan artifact |
| `PM-input-needed` | No edit until PM decides; then one of the above | Per PM direction |

The review-integrator agent has explicit authority to land prior-art-side edits when the EM's dispatch prompt names the direction per conflict. See `agents/review-integrator.md` § Prior-Art Conflict Resolution.

**Precedence when reviewer disagrees with EM's pre-dispatch direction.** The EM names a direction per conflict in the integrator dispatch prompt. If the Opus reviewer's findings recommend a different direction (e.g., EM pre-selected `update-plan`; reviewer's architectural read says `update-prior-art`), the integrator escalates as ASK — does NOT silently apply either direction. The EM resolves the conflict before the integration commit. The EM's dispatch-prompt direction does not auto-override a contrary reviewer recommendation; this is the structural protection against the EM short-circuiting the review's directional input.

## False-positive arbitration — feedback loop on wiki quality

The prior-art-checker is mechanical, not judgmental. It can over-match (false-flag a phrasing difference as a conflict) and under-match (miss a doctrine that applies but uses different keywords). The bidirectional resolution table above is the per-instance fix. The longer-running quality loop:

- **Repeated false-positives signal wiki revision.** When the same wiki entry produces multiple bogus conflicts across plans, that is a feedback signal — the wiki is outdated, vague, or wrong. Surface as a candidate for wiki revision (or land an `update-prior-art` direction the next time it fires). The prior-art-checker thus becomes a quality loop on the wiki corpus, not a freeze on it.
- **Repeated `update-prior-art` outcomes against the same entry** are the strong signal — two plans correcting the same wiki within a quarter means the entry is stale, not just badly phrased. Promote to a wiki-revision task at next `/workweek-complete`.

**Sidecar preservation.** Prior sidecars are never overwritten — on re-run the agent renames the existing sidecar to `state/plan-sidecars/<plan-stem>.prior-art-check.<UTC-mtime>.md` before writing the new one. This means the arbitration history (what the first run flagged, what changed in the second run) is always available as an archived sidecar alongside the current one. The feedback-loop in rule 2 above depends on this archive existing. `state/plan-sidecars/` is an unreaped-by-design archive class (Z1) precisely because this feedback loop depends on the history surviving.

**Operational hook:** during `/workweek-complete` Step 4 (improvement-queue triage), the EM scans recent `state/plan-sidecars/*.prior-art-check*.md` sidecars for Conflicts dispositioned as `override-and-document`, `update-prior-art`, or `both`, and flags wikis cited ≥3 times across those dispositions as candidates for revision. Repeated `update-prior-art` against the same wiki is the strongest signal — two plans correcting the same entry within a quarter means the entry is structurally stale, not just occasionally wrong. The in-flight bidirectional resolution handles individual conflicts at plan time; the weekly pass exists for cross-plan pattern detection that in-flight resolution cannot see. This is judgment-based, not automated — but the responsibility lives in weekly cadence so it doesn't drift.

## EM Disposition Prose Against a Conflict Needs Substrate Grep

**When the EM writes disposition prose against a prior-art-checker Conflict — especially a non-existence claim ("no typed X exists in this codebase") — that prose is a hypothesis until substrate-grepped, not authoritative framing.**

The prior-art-checker surfaces a Conflict; the EM responds with a disposition direction (e.g. `update-prior-art` with rationale "we don't have X"). If the rationale rests on a non-existence claim, it must be substrate-grepped before landing in the integration commit — the same no-fabrication discipline that applies to plan body assertions applies here. A disposition that convincingly argues "we have no typed Y" without a grep citation is fabrication with more prose around it.

**How to apply:** before writing an `update-prior-art` or `override-and-document` disposition that relies on a non-existence or existence claim about your codebase, run `grep -rn "<claimed identifier>" src/ tests/ plugins/ commands/` and quote a file:line result (or the zero-result) in the disposition. The sidecar body carries the rationale; the rationale is only load-bearing when it's grounded.

Companion to this wiki's § Bidirectional resolution.

## Audit-side closure must cross-check pre-existing test signal

When an audit triage proposes closing a candidate as "out of scope" or "covered elsewhere," cross-check against pre-existing test failures on that candidate before closing. Convergent signal (audit says skip + existing test already red on the same surface) beats a unilateral audit-side contract-boundary assumption. The audit is reasoning forward from claim surface; the failing test is reasoning backward from observed behavior. When they disagree, the test wins until the audit explains the failure.

**Rule:** before dispositioning a prior-art match as `update-prior-art` or `override-and-document` on a candidate cited as "broken anyway," run the cited test on HEAD. A failing test that the audit was about to dismiss is the audit's blind spot, not noise.

## Tree-sitter ERROR-byte coverage interpretation

A "Tree-sitter ERROR-byte coverage %" figure cited in a plan or audit is meaningless without locus-vs-consumer-query context. ERROR bytes in regions never touched by the consumer's queries cost zero; ERROR bytes inside a query's target subtree are total failures. Coverage % aggregates both into one number, hiding the only distinction that matters.

**Rule:** when prior art cites a tree-sitter ERROR-byte percentage as evidence, demand the breakdown by consumer-query locus. "97% non-ERROR" is admissible only with "and the 3% does not overlap any of queries X, Y, Z." Without the locus split, treat the coverage figure as unverified.

## Sibling-Spinoff Pre-Commit Gate

**Plan-time spurious-spinoff drift caught by prior-art-checker is the highest-ROI pre-flight.** When a plan-writer assumes downstream infrastructure doesn't exist and authors a sibling spinoff for it, prior-art-checker's scout-artifact cross-reference catches the drift before the spinoff ships to disk.

Any sibling-spinoff handoff authored by a plan-writer MUST go through prior-art-checker before being committed — the spinoff substrate may already exist in the peer repo. The checker should search for the proposed hookspec name, dataclass name, and boot-block pattern across the peer-repo corpus (`peer_repos:` field in the checker brief).

*Canonical:* A plan-writer authored a spinoff for a sibling repo's addon-registration hookspec, dataclass, and boot-iteration block. All three already existed in that repo's substrate, documented in its own wiki. Prior-art-checker surfaced this from a handful of scout artifacts within minutes; the spinoff was revoked, and the deliverable collapsed into a ~10-line hook implementation.

**Operational trigger:** In `coordinator:plan` Branch C, when a chunk authors or commits a spinoff handoff, fire prior-art-checker with `peer_repos:` populated with the spinoff's target repo before the chunk is committed to disk.

## Roadmap Stub-Minting Must Reconcile Against Shipped and In-Flight Same-Repo Work

The Sibling-Spinoff gate above catches *peer-repo* substrate that already exists. The same drift recurs one altitude in — a roadmap OVERVIEW or an audit defect-slate mints stubs for work THIS repo has already shipped or is landing concurrently. Prior-art-checker catches both at plan time; without it, the corrections surface as PM-facing premise reversals mid-execution.

- **Reconcile OVERVIEWs against shipped hooks/schemas before minting stubs.** A roadmap OVERVIEW authored without grepping for the hooks, guards, and schemas it proposes to build mints stubs that duplicate live infrastructure. *Canonical:* a stub asked to (a) build an executor plan-file write-deny and (b) generalize a reviewer hook — but the deny already shipped in the engine's write-guards, and the target sidecar was already a typed producer-backed schema. Three PM-facing premise corrections (deny already shipped / sidecar already typed / extend-in-place) all resulted — each caught by prior-art-checker at plan time, not stub time.

- **Cross-ref concurrently-executing plans on the same file scope.** *[universal]* When roadmap-planning turns an audit's findings into spinoff stubs, grep in-flight and recently-landed plans touching the same file scope FIRST, so already-delivered items are not re-packaged as pending work. *Canonical:* a stub was packaged from a prep-audit defect slate, but a parallel plan had already executed the entire slate before the stub was authored — pickup reconcile found every acceptance criterion delivered on disk. Liveness is git + disk, never a sibling plan's frontmatter `status`.

## Cost target

Aim for under 10K tokens per plan check. The corpus is bounded (project wikis across all `docs/wiki/` subdirectories — currently ~57 files including `codebase-judgment/` entries — plus global wikis, lessons, and queue). RAG-over-wikis is a phase-2 optimization; for now, full-text reads of relevant entries is the contract.

## Cross-repo capability lens

`prior-art-checker`'s three within-repo buckets (wikis, lessons, queue) answer
"have we already established something relevant?" for a single repo's own
history. They have no cross-repo reflex: a plan proposing to build structured
infrastructure — a store, a query surface, an index, an embed-pipeline — gets
zero signal that a sibling repo already ships exactly that as a platform
capability. **The 4th plan-mode bucket, "Platform capability — consume, don't
rebuild,"** closes that gap. It is plan-mode only; it does not appear in the
research-mode "Existing corpus" 4th bucket (see § What is prior-art-checker?
above) and is excluded from the reviewer-side consumption block's
research-mode negative-spec — the two "4th buckets" are different modes and
must not be conflated.

**The receipt this bucket exists to prevent.** A consumer-side repo built a full
parallel multi-query, multi-loader workstate store duplicating a sibling
repo's workstate store — same relational model, a re-implemented claims
ledger, its own supersession logic — while the sibling repo had offered the
equivalent capability as a host surface across multiple transports for
months. The consumer is now mid-cutover onto the sibling's store, with every
loader mapped 1:1 onto the sibling's API. A plan-time capability lens would
have surfaced "consume the sibling's workstate store" before the parallel
stack was ever built.

### Constraint 1 — offer-shape, never a bare violation flag

Every emitted entry LEADS with the alternative: `"<host_repo> offers
<capability_label>; consume via <consume_seam>"` — never a bare "you are
duplicating X." This is the same offers-not-nags discipline that governs all
agent-facing tooling design (global `CLAUDE.md § Implementation Standards —
Extensions`, where `superpowers` is named the canonical anti-pattern of
mistrust-shape tooling that nags without offering the better path). Because
the substrate is an authored manifest (see below), `consume_seam` is always a
real, structured seam the offering repo vouches for — never a degraded
"consume via (unconfirmed)."

### Constraint 2 — mechanical polarity, `host_repo == plan_repo` suppression

The bucket's match logic keys on an explicit construction-vs-production
predicate: it fires only when the plan's claim proposes a NEW
schema/store/surface/index/embed-pipeline, never when the claim is an
append/write against a NAMED EXISTING seam (this is what keeps the bucket
silent on the pure-*producer* repo shape — one that
into an existing sibling store). Matching is domain-aware (capability
identity, not coarse `capability_class` alone), so a same-class-
different-domain construction does not false-fire.

Polarity itself is a MECHANICAL field comparison, not inference:
`host_repo == plan_repo` suppresses the offer outright — the plan's own repo
is the host, so there is no consume-from-sibling direction to offer. Genuine
peer overlap (a different sibling also hosts the same capability, no clean
consumer/host asymmetry) renders as `peer-overlap — coordinate`, a distinct
classification from a directional consume offer. The plan's repo is always
CONSUMER by construction (it is the one proposing to build); the sibling is
always HOST; the offer only ever points consumer → host.

### The authored per-repo manifest substrate

`prior-art-checker`'s tool list is `["Read", "Bash", "Write", "WebSearch",
"ToolSearch", "TaskUpdate", "TaskList", "TaskGet"]`
(`agents/prior-art-checker.md:7`) — `Bash` is present (this harness build
has no `Grep`/`Glob`; `Bash` is how the agent still gets `grep`/`find`), but
no MCP. The checker is a local-file reader; it cannot call the live fleet
surfaces a sibling might expose (an MCP tool, a `--json` CLI, an HTTP
endpoint). The capability data must therefore arrive as an on-disk artifact
the checker can `Read`.

The substrate is a two-tier authored pipeline, not a live query:

1. **Each platform repo EMITS its own authored capability manifest**, rooted
   at its own `state/` — a per-repo, decentralized declaration of the
   capabilities it offers siblings (`capability_id`, `capability_class`,
   `capability_label`, a real `consume_seam`, `maturity`, `provenance`,
   `host_repo`).
2. **The engine AGGREGATES the N per-repo manifests into a persisted fleet-
   capability index** as an engine op (engine-tier read-aggregation is
   engine-owned; the doctrine-authoring repo authors the two contract schemas
   and the cross-repo asks, not the aggregation machinery in any language).
3. **The review SKILL resolves the persisted index via the engine's
   op-invocation seam**, applies the read-time TTL staleness rule (below),
   and passes the index path to the checker in the dispatch brief as
   `fleet_capability_index:` — the checker reads it as a plain file, exactly
   like its other three corpora.

### Read-derived projection, not a consolidation-point SPOF

A persisted *central* fleet index looks, at first glance, like exactly the
shape the fleet's producer-contract doctrine flags: per-repo, decentralized
emission with no single consolidation point — a consolidation point makes
one producer a fleet-wide single point of failure. The distinction that
keeps this substrate on the sanctioned side is **emit-into (banned) vs.
derive-from (sanctioned)**: no repo ever emits its capability rows *into* the
fleet index — each repo remains the sole authoritative emitter of its own
manifest, decentralized emission untouched. The engine's persisted index is a
read-derived projection (a materialized cache) over those N per-repo
manifests, the same read-side aggregation pattern already sanctioned
elsewhere in the fleet's strategic-self-description standard. If the index
is stale, absent, or lost, it is rebuildable from the always-authoritative
per-repo manifests — no repo's visibility depends on being co-located with
it, and no per-repo declaration is destroyed by the index's loss.

### Why Tier-2 authored, not Tier-1 heuristic extraction

An earlier draft of this mechanism had the engine *heuristically extract*
capabilities from each sibling's strategic self-description record
`version_highlights[]` plus a keyword grep of `docs/wiki` for store/query/
index terms. The Staff Engineer's review and an empirical scout read of a sibling repo's
real substrate killed that approach on its own motivating exemplar: (1) that
repo has no `self-description.yaml` — its strategic profile is a live
claim-store projection, and `strategic_self_description` is not even
registered on its own instance; there is nothing for a highlights extractor
to read. (2) that repo IS a store/query/index engine, so the generic keyword
grep matches the great majority of its wiki — pure noise, and its README is
silent on the capability. The Tier-1 heuristic would therefore NOT have
surfaced that repo's workstate store — the exact rebuild-case the lens
exists to catch. The authored manifest (Tier-2) resolves this by
construction: the repo that owns the capability declares it, with a real
seam it vouches for, so there is no extraction step to fail.

### Read-time TTL staleness

A persisted index whose engine refresh cadence has lapsed ages invisibly —
rebuildability protects against loss, not staleness. The SKILL applies a
read-time downgrade rule: past the index's declared `ttl`/refresh cadence,
every entry's `maturity` is downgraded to `stale`/`unverified` before the
index is handed to the checker, so offers self-weaken as the index ages
rather than asserting a capability a sibling has since moved or deprecated
as `live`. A capability whose seam has never been self-verified reachable is
`unverified` by default (never `live`), and manifest entries with
`provenance: generated | asserted` fail closed harder than `curated` ones.

### Report-then-relay action

The bucket's action is REPORT-only, never a cross-repo write of its own: the
sidecar directs the EM to route a `cross-repo-memo` and hand the PM the
receiver path for relay — the same draft-then-surface-to-PM discipline every
cross-repo ask in this system follows. Any engine op reading a sibling's
authored manifest is read-only against that sibling's tree — "ship
what makes sense for OUR install surface; teach how OTHERS handle theirs —
never code both sides from our repo"). The lens itself never auto-blocks and
never mutates the plan — inheriting the checker's existing report-only
invariant verbatim.
