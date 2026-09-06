# Computed skills — the assembler contract

> A **computed skill** is a fourth-generation coordinator skill: instead of a prose
> decision-tree the EM walks by hand (the super-skill shape) or a prose tree plus
> extracted one-liner helpers the EM still sequences (the ASIC shape), a single
> read-only claude-klabauter CLI computes the whole routing over disk/git/frontmatter state and
> returns it as one JSON decision object. The EM's job collapses to resolving the
> judgment residue the object surfaces — it stops re-deriving mechanical branches by
> hand on every invocation. This wiki is the CONTRACT the assembler CLI is built
> against: the decision-object schema, the invocation protocol, the exit-code
> semantics, and the classification of `pickup`'s branch inventory that the contract
> must compute versus surface as judgment. The implementation (`pickup-assemble` in
> `claude-klabauter`) is built to this document, not the other way around.
>
> **Read `docs/wiki/invisible-doctrine.md` first.** This page is the CONTRACT — the schema,
> the protocol, the classification. That page is the AMBITION the contract exists to serve,
> and a conversion can satisfy every clause here while missing it entirely. In particular the
> discharge test ("for every rule, what artifact discharges it?") is what tells you whether a
> converted surface actually removed the need to know something, or merely reworded it.
>
> Spec backlink: `docs/plans/2026-07-23-computed-skills-pickup-beachhead.md` (chunk A1).
> Generalization target named there: `workstream-complete` and the rest of the skill
> frontage, once this POC converges — see § Generalizing this pattern below.
> Amendment spec backlink: `docs/plans/2026-07-23-computed-skills-bz-pickup-rebuild.md`
> (chunk C4) — the `apply` mutating half, the three-tier model, and the arrival-legibility
> surface all land here from that plan.

## Vocabulary — where this sits in the skill-generation lineage

| Generation | Branching lives in | EM's job |
|---|---|---|
| Narrative skill | prose principles | absorb and apply |
| Decision-tree super-skill | a prose tree in `SKILL.md` | walk the tree |
| ASIC helper-extraction | prose tree + extracted `bin/wsc-*` helpers | walk the tree, invoke each helper |
| **Computed skill** (this contract) | a claude-klabauter assembler CLI computes the routing | resolve the judgment residue |

The decision-tree shape is not deprecated — it remains correct for judgment-dense,
low-frequency skills. A computed skill is the right shape only for a high-frequency
skill whose branch inventory skews heavily mechanical, as `pickup`'s does.

<!-- spec-backlink: run 2026-08-06-14h38, nugget c6-023 -->
## Beachhead outcome — `pickup` as the first computed skill

`pickup` is the beachhead conversion this contract was built against and validated
by. The read-only claude-klabauter assembler computes the mechanical routing; `pickup/SKILL.md`
itself carries judgment only — no command fences, no branch prose the assembler
already resolved. The line-count delta is the headline evidence the conversion
discharged its own goal rather than merely reorganizing prose: `pickup/SKILL.md` went
from 728 lines to 173 (zero command fences remaining). In census terms, this is the
same shift the MECHANICAL/JUDGMENT split above documents in full: the EM's job
collapsed from re-deriving ~45 branches by hand on every invocation to resolving the
~17 that genuinely need judgment (§ JUDGMENT checklist).

A5 (cockpit launch-path confirmation) was deferred at this point in the beachhead
plan, not resolved — a later pass confirms cockpit's launch path before that chunk
closes; nothing in this wiki should be read as asserting A5 landed.

## The three-tier model

A computed skill's output sorts every branch it computes into exactly one of three
tiers. The compute/apply split (§ below) is how tier 1 executes; it is not itself the
model — `judgment_points[].recommendation` is the tier the contract's first draft was
missing, and its absence collapsed tiers 2 and 3 into one shape that could not
distinguish "here is my best answer" from "I have nothing to offer."

| Tier | Shape | EM's job |
|---|---|---|
| 1 — **do-for-you** | `directives[]` entry | Execute (or let `apply` execute) without re-deriving the branch. |
| 2 — **recommend-for-you** | `judgment_points[]` entry carrying `recommendation: {disposition, rationale}` | Decide, informed by an offer it may disagree with. The recommendation is never authoritative and never auto-actionable — see § "No automated consumer derives a disposition from a recommendation" below. |
| 3 — **your-call** | `judgment_points[]` entry carrying `recommendation: null` with a `reason` | Decide with no offer in hand — the engine states plainly that it has nothing to narrow the choice with, rather than manufacturing a recommendation to fill the field. |

**Constructed, not remembered.** A `judgment_points` entry is built through a
constructor whose `recommendation` parameter is required, with no default — omitting a
tier decision at authoring time is a `TypeError`, not a missed review item. Tier-3
entries call the same constructor with an explicit `null` and a `reason`
(`insufficient-evidence`); a genuinely recommendation-forbidden judgment point (below)
goes through a **distinct constructor that carries no `recommendation` parameter for
its caller to fill at all** — it hardcodes `recommendation: null, reason:
recommendation-forbidden` itself, so the forbidden case is structurally unreachable by
a caller rather than merely discouraged by a permissive default. Note the schema does
not carry a `confidence`
token alongside `recommendation` — a rationale is checkable; a confidence score is not,
and § "No automated consumer derives" below already forbids the one consumer that
would act on it, so there is nothing for the field to buy.

**The recommendation-forbidden security class.** Some judgment points must never carry
tier 2 at all — the completeness-probe confirmation gate (§ MECHANICAL checklist,
Probe-confirmation) is the corpus's sharpest instance. The general discriminator is
not a curated list of gates that happen to feel sensitive: **can the thing being
recommended about influence the recommendation?** Any judgment point whose evidence is
sourced from content the engine did not itself compute — a probe command lifted
verbatim from a shared branch's frontmatter, a memo or handoff body quoted into
`evidence` — belongs to this class, because a recommendation computed over
attacker-influenceable evidence is itself attacker-influenceable. Every entry in this
class uses the no-recommendation constructor; none carries `recommendation` at all,
not even `null`.

**No automated consumer derives a disposition from a recommendation.** A
`recommendation` is an EM-facing offer, not machine-actionable output. An autonomous
no-human consumer — the button-spawned session named in § The two-phase-stateless
protocol — treats a recommendation-bearing judgment point identically to a bare one:
it halts and leaves the point unresolved. Introducing an engine-authored
`recommendation` into every judgment point would make auto-resolution look sanctioned
unless this is stated as a general contract rule rather than a property of the one
gate (the completeness probe) it was first observed on.

**Tier promotion is a normal edit, not a schema re-litigation.** When a judgment
point's rationale becomes fully mechanical — the engine can reach the same answer with
zero remaining semantic judgment — it promotes from tier 2 (or 3) to tier 1 and stops
being a question at all. `claim_grant` (§ below) is the worked example: "is someone
else holding this?" is a `directives`-tier fact the engine computes and returns, not a
question the EM answers by hand-rolling a grep. A future author
moving a judgment point up a tier is applying this contract, not amending it.

This vocabulary is the doctrinal parent of `docs/wiki/eager-agent-calibration.md` §
Offer-Shape vs. Friction-as-Warning applied to a machine-computed surface rather than
a prose one: lead with the better alternative, never block or nag without one — tier 2
is that lead, tier 3 is candor about not having one, and tier 1 is the friction
removed entirely.

## The compute/apply split — how tier 1 executes

A computed skill's CLI carries two entrypoints over the same schema:

- **`brief <path>`** — pure, read-only, idempotent. Computes and returns the whole
  decision object; never mutates. Safe to fire unbidden, because it changes nothing.
- **`apply <path>`** — mutating. Recomputes the brief in-process, executes every
  execution-ready `directives[]` entry in dependency order, halts at the first
  unresolved `judgment_points` entry, and reports what it did.

Read-only is not incidental to `brief` — it is what makes firing `apply` on an
explicit verdict safe: compute stays pure *because* it fires unbidden; apply mutates
*because* it fires only once the tier-1 answer is in hand. A computed skill that
returns `directives[]` with no paired mutating half leaves the EM to retype exactly
the tier-1 work the split exists to remove — the split is the pattern every computed
skill's do-for-you tier executes through, not a pickup-local convenience.

### What bounds a mutating apply half

Concentrating every mutation an EM used to retype by hand behind one entrypoint is a
real cost, not a free win. It is bounded by four structural properties, not by
assurance that the code is careful:

1. **No new mutation capability.** Apply concentrates *invocation*, not
   *implementation* — every mutation stays in its own already-hardened, separately
   tested primitive (the CLIs named in § Consumes manifest); apply composes them. The
   reachable blast radius is exactly the union of the CLIs the contract already names
   as directives.
2. **A closed dispatch table, not a tautology.** Because apply recomputes the brief in
   the same process, "the brief computed it" is true of whatever apply does — that
   alone is a promise, not an enforcement mechanism. The enforceable version: a
   `directives[].cli` value is a string; apply resolves it through a literal, closed
   name→callable dict and fails loud on any unrecognized value — never a `getattr`,
   never an importlib resolution, never a subprocess, never a shell. No value derived
   from `directives[].cli` or `directives[].args` may reach a subprocess argv. The
   resolved artifact/basename path is asserted in-repo before any mutation.
3. **It halts at judgment and never overrides a denial.** The gates that stop a human
   stop apply identically; an auto-fired apply has strictly *fewer* powers than the EM
   (no override).
4. **The inverse is first-class.** A `drop` subcommand returns the artifact to its
   pre-claim state, so the concentrated surface is also a reversible one.

Every computed skill's apply half inherits this bound. It is what makes concentrating
mutation behind one entrypoint a *paid-for* cost rather than a merely conceded one —
without it, a mutating half is a promise resting on the author's care, which does not
survive a twelfth author who never read the reasoning.

## The decision-object JSON schema

`pickup-assemble brief <artifact-path> [--decisions <json>]` returns exactly
one JSON object with the eight top-level keys normatively enumerated in
§ Decision-Object Schema-of-Record below (`artifact`, `preflight`, `gates`,
`directives`, `judgment_points`, `decisions`, `narration`, `next_move`):

```json
{
  "artifact": {
    "path": "state/handoffs/2026-07-23-example.md",
    "classification": "handoff",
    "frontmatter": {},
    "resolution": null
  },
  "preflight": {
    "dirty_paths": [],
    "staleness": { "branch": "work/machine/2026-07-23", "days": 2 },
    "closure_signals": []
  },
  "gates": {
    "claim": { "fetch_state": "not_performed", "holder": null },
    "addressee": { "exit_code": 0 },
    "branch": { "action": "resume" },
    "aging_verdict": "ok"
  },
  "directives": [
    {
      "id": "d1",
      "cli": "archive-stamp-cli",
      "args": ["consume-handoff", "state/handoffs/2026-07-23-example.md"],
      "depends_on": null,
      "already_satisfied": false
    }
  ],
  "judgment_points": [
    {
      "id": "j1",
      "question": "Any peer live on this handoff/plan? Stand down?",
      "evidence": "gates.liveness_signal",
      "dispositions": [
        { "value": "proceed", "resolves": ["d1"] },
        { "value": "stand-down-and-surface", "resolves": [] }
      ],
      "round_trip": "terminal",
      "revalidate_at_dispatch": false,
      "recommendation": {
        "disposition": "proceed",
        "rationale": "no live holder found on this artifact or its lineage"
      }
    }
  ],
  "decisions": {},
  "narration": "Ran ahead of you: brief computed, baton claimed.",
  "next_move": null
}
```

The tier-3 (your-call) shape carries `"recommendation": null` alongside a sibling
`"reason": "insufficient-evidence"` field naming why no offer was made (§ The
three-tier model). A recommendation-forbidden judgment point (the completeness-probe
gate) uses `"reason": "recommendation-forbidden"` in the same shape — the
no-recommendation constructor hardcodes both, so the `null` is structural, not an
authorial choice made under pressure.

### Typed field schema

Required-ness, type, and enum per field — the normative shape; the illustrative block
above is one concrete instance of it.

| Field | Type | Required | Notes |
|---|---|---|---|
| `artifact.path` | string | yes | Resolved artifact path (post archive-fallback, if applicable). |
| `artifact.classification` | enum: `handoff \| memo \| spinoff \| archived \| ambiguous` | yes | |
| `artifact.frontmatter` | object | yes | Full parsed frontmatter; empty object if none. |
| `artifact.resolution` | object \| null | no | Present only on the archive-fallback path — `{status, archive_path, terminal_fields}`. |
| `preflight.*` | object (sub-schema per key) | yes (object present; individual sub-keys conditional on branch — memo vs. handoff) | Evidence only, never a verdict. |
| `gates.*` | object (sub-schema per key) | yes (object present; individual sub-keys conditional on branch) | Deterministic facts only; a semantic sub-field belongs in `judgment_points`, not here. |
| `directives[].id` | string | yes | Unique within the response. |
| `directives[].cli` | string | yes | Names an existing atomic CLI entrypoint verbatim. |
| `directives[].args` | array of string | yes | Fully resolved; may embed a value sourced from a `judgment_points` disposition. |
| `directives[].depends_on` | `null` \| string (a `judgment_points.id`) \| array of string (`judgment_points.id`) | yes | `null` = unconditional, executes as soon as reached. A single string = gated on that one judgment point. An array = gated on **all** of the named judgment points (AND-semantics) — not execution-ready until every entry in the list has been dispositioned. |
| `directives[].already_satisfied` | boolean | yes | `true` = assembler detected the effect already happened; EM does not re-run it. |
| `judgment_points[].id` | string | yes | Unique within the response. |
| `judgment_points[].question` | string | yes | One-sentence framing of the decision. |
| `judgment_points[].evidence` | pointer (string, dotted path into `preflight`/`gates`) or inline object | yes | Cited by pointer, not duplicated, where the shape is already scalar/list. |
| `judgment_points[].dispositions` | array of `{value: string, resolves: string[]}` | yes | Each `value` is a concrete choice; `resolves` names the `directives[].id` values that choice unblocks. |
| `judgment_points[].round_trip` | enum: `terminal \| round_trip` | yes | See § Round-trip classification. |
| `judgment_points[].revalidate_at_dispatch` | boolean | yes (default `false`) | `true` = this entry's evidence is freshness-sensitive; the EM/consumer MUST recompute the verdict live at dispatch time (fresh fetch + re-read), never trust the brief-time value. See § Round-trip classification. |
| `judgment_points[].recommendation` | object `{disposition: string, rationale: string}` \| `null` | yes | Tier 2 (object) or tier 3 (`null`) per § The three-tier model. Built through a required-parameter constructor — never authored as a bare dict lacking the key. No `confidence` sub-field; a rationale is checkable, a confidence score is not. |
| `judgment_points[].reason` | enum: `insufficient-evidence \| recommendation-forbidden` | conditional — required when `recommendation` is `null`, absent otherwise | Names why no tier-2 offer was made. `recommendation-forbidden` is emitted only by the no-recommendation constructor (§ The three-tier model), never chosen by a caller. |
| `narration` | string | yes | Top-level, non-empty. **Generated** from the executed-directive log, never author-composed, length-capped. Structurally incapable of narrating a pending recommendation — see § Arrival legibility. |
| `next_move` | string \| null | conditional — required (non-empty) on every non-`clear` `gates.coast.verdict`; may be `null` on `clear` | Top-level, explicitly **not** length-capped. See § Arrival legibility and the rendering-priority list under degraded payloads. |
| `decisions` | object | yes | Top-level. The round-tripped `--decisions` input, echoed verbatim on every branch — the disposition-resume/audit surface a caller's own `apply` re-reads back from the emitted decision object (Function 6). Empty object when no `--decisions` was supplied. |
| `gates.claim_grant` | object `{verdict, reason, holder, holder_live, claim_age_minutes, drop_invocation}` (plus `override_invocation` + `recommendation` on `denied`) | yes | `verdict` ∈ `granted \| granted-with-warning \| denied`. Pickup-specific — § Template-scope partition. |
| `gates.coast` | object `{verdict, notes[], blocked_by[]}` | yes | `verdict` ∈ `clear \| blocked`. Reports what the EM is holding; never gates the claim (that is `claim_grant`'s job). Sub-key of the existing `gates` object — no sixth top-level key (AC8). Pickup-specific. |
| `preflight.tree_quiescence` | object `{verdict, repos: [{repo, dirty[], unparseable_scope_entries[]}]}` | yes | `verdict` ∈ `quiet \| dirty`. Real `git status --porcelain` intersection per repo in `scope:`, not a scope echo; a prose `scope:` entry surfaces in `unparseable_scope_entries`, never silently counted as dirty. Pickup-specific. |
| `gates.competing_claim` | object `{verdict, candidates: [{path, claimed_by, holder_live, disposition}]}` | yes | `verdict` ∈ `none \| stale-only \| live-peer`. Distinct from `claim_grant`: `claim_grant` reads this artifact's own claim record; `competing_claim` scans sibling artifacts in the same workstream. Pickup-specific. |
| `gates.execution_stamp_match` | object `{verdict, stamped_sha, computed_sha, stamp_commit, delta_class, next_move}` | conditional — present only on an artifact carrying a `## Plan to Execute` pointer or an `execution_authorized_sha` | `verdict` ∈ `match \| stale-bookkeeping \| stale-substantive \| unstampable`. Emitted, not aspirational — § MECHANICAL checklist names its computation locus. Pickup-specific instantiation; the tier-split worked example it demonstrates (§ The three-tier model) generalizes. |

**The list form of `depends_on`.** Two `judgment_points` entries can independently
fire and both claim to gate the same directive — e.g. an `awaiting_gate` handoff
whose gate has its own dedicated judgment call, and a live-peer liveness signal that
fires independently on the same directive. Neither entry alone tells the whole story,
so `depends_on` carries both ids and the directive is not execution-ready until each
has been dispositioned:

```json
"directives": [
  {
    "id": "d2",
    "cli": "archive-stamp-cli",
    "args": ["consume-handoff", "state/handoffs/2026-07-23-example.md"],
    "depends_on": ["jgate", "j1"],
    "already_satisfied": false
  }
]
```

### `artifact`

The classified artifact: its resolved path, its full parsed frontmatter, and its
`classification` (`handoff | memo | spinoff | archived | ambiguous`). On the
archive-fallback path (artifact absent at the passed path but found in one of the
three archive dirs), `artifact.resolution` carries `{status: "archived", archive_path,
terminal_fields}` instead of live frontmatter — this is read-only, terminal-state
data, never a directive to act on it. On a multi-hit `find` (the same basename swept
into more than one archive dir), `archive_path` becomes `archive_paths: [...]` naming
every candidate — detect-then-fail-loud, never first-wins.

### `preflight`

Everything the engine gathered by reading disk/git state, scoped to the workstream:
dirty paths (from the handoff's `scope:` block), the branch-action needed (resume vs.
create vs. already-current), branch staleness in days, the reconcile evidence bundles
(candidate closing commits, closure signals per pending item, deliverable-scope
evidence, premise-check results, stealth-skip flags, prereq re-verification results),
and — on the memo path — the premise-verification bundle (locus grep, fetch+scan,
archive sweep, sibling-inbox dedup sweep, absence-claim scan). `preflight` is *evidence
for judgment_points to cite*, not itself a set of verdicts.

### `gates`

Boolean/enum gate states the engine can compute deterministically: claim state
(fetched, `claimed_by`/`consumed_by` idempotency result, live-claim holder), addressee
state (self/to resolution + exit code from the addressee-guard CLI), branch state
(on-main vs. resumable vs. stale), and aging state (the `handoff-gate-aging` 0/1/2
verdict). A gate is a fact the EM can trust without re-deriving; it is never itself a
place where the EM's semantic judgment is required — if a would-be gate needs
semantics, it belongs in `judgment_points`, not `gates` (this is exactly the MIXED
discriminator, applied at the schema level).

`gates.claim.fetch_state` is `not_performed` on every `pickup-assemble` emission — the
engine is read-only per AC3 and never fetches, so `not_performed` is the only value
this producer can ever return. `ok` is a reserved value for a future fetch-capable
producer; a reader diffing real output against the contract should expect
`not_performed`, not treat its presence as a bug.

### `directives`

An ordered list of tier-1, do-for-you actions (§ The three-tier model), each naming an
existing atomic CLI verbatim — never a fenced command payload. `directives` is
executed by the same CLI's mutating `apply` half (§ The compute/apply split), not by
the compute half that returns them: `brief` stays read-only and computes the whole
ordered list; `apply` walks it and executes each entry through a closed dispatch table
(§ What bounds a mutating apply half). Each directive entry carries: `id`,
`cli` (the entrypoint name, e.g. `archive-stamp-cli`), `args` (fully resolved,
including any values sourced from a resolved `judgment_points` disposition),
`depends_on` (`null` if unconditional, a single `judgment_points` id if gated on
one entry, or an array of `judgment_points` ids if gated on more than one — a
directive that two independently-firing judgment points can each claim to resolve
takes the array form, and every named entry must be dispositioned before the
directive is execution-ready), and `already_satisfied` (true if the assembler
detects the directive's effect already happened — e.g. a peer already claimed —
so the EM does not re-run it).

### `judgment_points`

An ordered list of EM decisions. Each entry: `id`, `question` (the decision framed in
one sentence), `evidence` (the pre-gathered `preflight`/`gates` data relevant to this
call, cited by pointer not duplicated), `dispositions` (an enumerated list of the
concrete choices, each carrying the exact `directives` entries — by `id` — that choice
resolves), `round_trip` (`terminal` or `round_trip` — see § Round-trip
classification below), `revalidate_at_dispatch` (boolean, default `false` — `true`
marks a freshness-sensitive entry the EM must recompute live at dispatch time, never
trust the brief-time value; see § Round-trip classification), and `recommendation`
(the tier-2/tier-3 discriminator — an object offer or `null` with a `reason`; see §
The three-tier model). **Every entry is an offer, not a verdict** — see § Candor is
the design principle.

## The two-phase-stateless protocol, resolved to single-shot

The plan's Architecture section named two candidate control-flow shapes and routed the
choice here. This section pins it (the Director of Engineering F1 obligation) and states the outcome that
falls out of the round-trip classification (§ below): **the contract is single-shot.**

**(a) Control flow.** `brief` does not halt at the first unresolved `judgment_points`
entry. It returns the *whole* ordered routing in one call — mechanical directives the
EM can execute immediately as it walks the list, with `judgment_points` entries
interleaved at their position, each carrying its dispositions' fully pre-resolved
directive templates. This is the shape the named downstream consumer requires: a
button-spawned session with no human mid-loop must be able to act on the brief cold,
and a halt-at-first-unresolved-point shape would leave that session stuck on the first
judgment call with nothing else to do.

**(b) When the EM executes mutating directives.** As the EM walks the ordered
`directives`/`judgment_points` list: execute an unconditional directive
(`depends_on: null`) as soon as it is reached. On reaching a `judgment_points` entry,
decide using the attached evidence, then execute the specific `directives` entries
that disposition names — this executes *without* re-invoking `brief`, because every
disposition's directive template (including CLI args that vary by choice, e.g.
`gate-recheck-handoff … --cleared` vs. the no-flag form) is already fully resolved in
the returned object. A directive is execution-ready only once every judgment point
named in its `depends_on` has been dispositioned — for the common single-gate case
that's the one entry named by the string form; where `depends_on` is a list (two
independently-firing judgment points both claiming to gate the same directive), the
EM must resolve **all** of them, not just the first one reached, before executing.
No downstream mechanical branch in `pickup`'s inventory needs a second call to
compute its shape from a judgment resolution — see § Round-trip classification.

**(c) What `--decisions` accumulates.** `--decisions` is a cumulative, monotonic
resolution map: `{judgment_point_id: {disposition, resolved_at, note?}}`. It is
**not required for the primary flow** (single-shot handles it), but it is retained for
two secondary uses: (1) **crash-resume** — a session that crashed mid-walk can re-invoke
`brief --decisions <accumulated-map>` and get a recomputed routing that reflects
already-resolved points without re-asking the EM to re-decide them; (2) **audit** — the
returned object echoes back the resolution map it was given, so a cold-started
button-spawned session (or a PM inspecting the transcript later) can see what was
decided and why, even without chat history. A key once present in the map is never
removed by a later call — only added to.

**(d) AC3 idempotency, restated precisely.** *Same disk snapshot AND same `--decisions`
payload → byte-identical `brief` output, and the call mutates nothing.* A disk-state
change that occurs *because* the EM executed a directive between two `brief` calls is
not a violation of this property — it changes the "same disk snapshot" precondition,
so the two calls are not comparable under the guarantee in the first place. The
guarantee is about the assembler's own determinism and read-only-ness, not about the
world staying still around it.

## Round-trip classification (the Director of Engineering F2) — the finding that collapses two-phase to single-shot

Every `judgment_points` entry in `pickup`'s inventory was classified `terminal` or
`round_trip`:

- **`terminal`** — the EM decides and acts; nothing *mechanical* downstream
  re-consumes the specific resolution to compute a *new* shape it couldn't already
  express. This covers the large majority: the 3.4b/c commit-match-and-drop calls,
  the M3 `ask`/`proposal` dispositions (each disposition's CLI call and flags are
  fully known in advance — `accepted`/`declined`/`partial` each map to a fixed
  `cs_action_memo` template), the `scoped_to` reach-beyond challenge (feeds a return
  memo, not a recomputed mechanical step), the ceremony-calibration and route-to-baton
  calls (feed a dispatch choice, not a further assembler-computed field), and the
  `distill_fate` ratification-escalation call (the CLI args for `ratification` vs.
  `commitment` vs. `ephemeral` are all enumerable in advance per disposition).
- **`round_trip`** — none found on the *shape* dimension. Every downstream mechanical
  directive in `pickup`'s inventory can be fully expressed as one of a small enumerated
  set of templates keyed by the judgment disposition itself, rather than requiring the
  assembler to *recompute new disk/git evidence* in light of the EM's choice.

**Outcome, shape dimension (per the decision rule the plan pins, not a resolution this
document makes unilaterally): the round-trip set is empty on directive shape. The POC
ships the single-shot brief-with-evidence shape and the two-phase protocol described
architecturally is not exercised in practice** — `--decisions` remains in the CLI
surface for crash-resume and audit (§ above), but no `pickup` invocation requires a
second `brief` call to compute a new directive shape from a judgment resolution.

**A second, orthogonal dimension: freshness, not shape.** Shape-round-trip-empty does
not mean every judgment point's evidence stays valid from brief-compute time through
dispatch time. The positive-liveness three-signal predicate — surfaced as the "Any peer
live on this handoff/plan? Stand down?" judgment point, and re-run verbatim at the
memo-branch's mandatory pre-dispatch reconcile — is evaluated once at brief-compute time
but its correctness is time-sensitive: a peer can claim-and-push *between* the brief
call and the EM's dispatch of the resolved directives, and the brief-time verdict goes
stale without the directive *shape* ever changing. This is a **freshness round-trip**,
not a data round-trip: the schema does not need a second `brief` call or a new field
shape, but the EM/consumer MUST recompute the verdict *live* at dispatch time (fresh
`git fetch` + re-read) rather than trust the value the brief returned. The
`judgment_points[].revalidate_at_dispatch` field (§ The decision-object JSON schema)
is the schema's answer to this: `true` on the positive-liveness stand-down judgment
point (both the Step 3.4h handoff-branch instance — its directives fire immediately
after the same brief call resolves it, sharing the identical freshness-gap property —
and the M3 ask-Accept pre-dispatch-reconcile instance, which is the same three-signal
predicate re-run mandatorily immediately before dispatch), `false` elsewhere.

**Outcome, freshness dimension — AC8 waiver, adjusted.** Because the shape-round-trip
set is empty, the dogfood corpus does **not** need an artifact forcing ≥2 *sequentially
dependent judgment points recomputing new directive shape* — the ≥6-artifact
behavioral-parity corpus (AC8's base requirement) remains sufficient for that dimension.
But the corpus MUST separately include at least one artifact that exercises a
`revalidate_at_dispatch: true` judgment point end-to-end (brief-time evidence, then a
disk-state change before dispatch, then the live re-check catching the staleness) — the
shape waiver does not extend to the freshness dimension, and skipping it would leave
the pre-dispatch reconcile contractually unverified.

**A disposition is not reusable across a `revalidate_at_dispatch` recompute — as a
general rule, not a `claim_grant` special case.** Apply recomputes the brief in-process
before mutating, and a stale disposition in hand for *any* `revalidate_at_dispatch:
true` entry — not only the peer-liveness one this contract names by example — must be
discarded if the recompute's verdict changed, and apply must halt rather than act on
it. Hand-picking this behaviour for one judgment point and leaving the general rule
implicit is the shape that misses the next one: an EM dispositions a *different*
revalidating judgment point against brief-time evidence, then invokes apply; apply
recomputes and the verdict has moved, but nothing says the stale disposition should be
discarded unless the rule is stated for every entry carrying the field, not derived
per-instance.

## Exit-code contract — locally scoped to this CLI

`pickup-assemble` defines its own exit-code contract. **This is not inherited from a
house convention** — the corpus has no single exit-code scheme
(`handoff-has-live-children.py` uses a distinct 3-outcome scheme of its own;
`docs/wiki/named-contracts-vs-incidental-flags.md` warns against generalizing one op's
shape onto another). AC4 requires this be stated as this CLI's own contract, not a
claim of inheritance.

| Code | Meaning |
|---|---|
| `0` | OK — a decision object was computed and returned. |
| `1` | Business failure — artifact unreadable/absent-and-not-archived, claim held by a live peer, addressee mismatch without override. |
| `2` | Usage error — malformed arguments, malformed `--decisions` JSON. |
| `3` | Transport failure — claude-klabauter root unresolvable, `coordinator_core` import failure. Distinguishable from a business failure without parsing stderr — a caller (hook or EM) that sees `3` knows the *engine* is unreachable, not that the artifact itself is a problem. |

**A decision object is emitted on every exit, including non-zero — never a bare exit
code with no object.** Exit `1` collapses three semantically distinct business failures
into one code, but the caller is never left to parse stderr to tell them apart: the
returned object on a `1` exit carries the specific failing gate (`gates.claim.holder`
for a live-peer claim, `gates.addressee` for an addressee mismatch, `artifact.resolution`
for unreadable/absent-and-not-archived) plus that gate's full offer text. The addressee
mismatch case is the sharpest instance — `gates.addressee` on a `1` exit carries the
complete M-addr stop-with-offer message verbatim (*"addressed to `<to-em>`; this
session's repo resolves to `<self-em>` — surface to the PM for relay, or confirm the
addressing is wrong"*) and a `cross_seat_override` field naming
`COORDINATOR_OVERRIDE_MEMO_ADDRESSEE` as the override path — both the candor of the
offer and the override affordance survive into the object rather than being flattened
away by the bare exit code.

### Exit-code contract for a mutating half (candidate-general-as-a-pattern)

The brief-side contract above covers `brief` only. A computed skill's mutating
`apply`/`drop` half defines its **own** exit-code instance — the pattern generalizes;
the specific codes below are pickup's own, not inherited verbatim by a future
computed skill's mutating half.

| Code | Meaning |
|---|---|
| `0` | Applied-clean — every execution-ready directive ran, commit landed. |
| `1` | Halted-at-judgment — zero further mutation beyond already-satisfied skips; ≥1 unresolved `judgment_points` entry remains. |
| `2` | Claim-denied — zero mutation; `claim_grant.verdict == denied`. |
| `3` | Transport-failure — unchanged brief-side meaning: artifact unreadable/crash, zero guaranteed mutation. |
| `4` | **Partial-mutation** — ≥1 directive succeeded, a subsequent directive then failed. Apply reports exactly which directives landed and which did not, so a follow-up `drop` acts on a known state. |

`4` is the state most likely to strand an EM with no memory of how it got there: an
auto-fired apply fails open identically to `3` on this code — a partial-mutation state
is never silently retried unattended — and the returned `next_move` instructs running
`drop` before retrying. `drop` itself is unconditional and relies on the idempotency
of the primitives it composes (a no-op release on a not-yet-claimed artifact, a no-op
unconsume on a not-yet-consumed handoff) rather than inspecting partial-apply state —
a half-applied artifact still returns cleanly to its pre-claim state regardless of
which directives actually landed.

## Candor is the design principle, not a nicety

Every `judgment_points` entry — whether native to the ~17 or reclassified out of the
~19 MIXED set — must read as an offer, never a verdict. The evidence attached is
framed as *"here are the 3 of 47 commits that plausibly close pending items — you
decide,"* never *"closed."* An entry that reads as settled is a defect, caught at the
A7 dogfood pass. This is what keeps the assembler on the correct side of the
predecessor plan's ruling that invocation-judgment stays with the EM: the engine
narrows the search space; it does not decide for the EM.

## Arrival legibility — the returned message is a designed surface

An EM invoking a computed skill arrives with no memory of ever having done this
before, and auto-fire sharpens that: machinery can run before the session has any
context for why. The failure mode is not a wrong verdict — it is a *correct* verdict
that arrives as unexplained machinery, or a refusal with no way forward against a
standing instruction the EM has no way to resolve on its own. Every computed skill
that auto-fires or returns a decision object inherits the three rules below; they are
contract doctrine, not a pickup-local nicety.

1. **Narrate what already happened, before showing any evidence — in one terse line.**
   `narration` (§ Typed field schema) is the required, non-empty field for this.
   Calibrate against what the EM already holds by the time this line lands — global
   `CLAUDE.md`, the skill's own prose, and the fact that it typed the command — and
   carry only the delta: that something already ran, and where that leaves it.
   Explaining the ceremony, reassuring, or touring the decision object is a tutorial
   written for a reader who does not need it (`invisible-doctrine.md` § The reader).

   **Register separation is structural, not an authoring convention.** `narration` is
   past tense and factual — checkable against the executed-directive log. A
   `recommendation` is future tense and contestable. Rendering both in one voice to a
   reader with no history to weigh them against lets the second borrow the first's
   authority, and terseness makes this *worse*: a dense, past-tense declarative sitting
   above a recommendation reads as *more* authoritative, not less. The mitigation is
   structural rather than a rule to remember: `narration` is **generated** from the
   executed-directive log, never from `judgment_points`, so it is incapable of
   narrating a pending recommendation — there is no authoring step at which to feel
   pressure to blur the two.

2. **No surface may terminate in a refusal.** Every denial, hold, or transport failure
   carries its next move — the override invocation, the drop invocation, the person to
   align with, or the one thing to check — in `next_move` (§ Typed field schema),
   non-empty on every non-`clear` verdict and explicitly not length-capped (a denial
   reason and its next move can be as long as they need to be). *"Denied"* is a dead
   end; *"held by a live peer — stand down, or override with `<exact command>` if you
   and the PM judge otherwise"* is a fork the EM can act on.

   **Degradation must not silently drop the next move.** When a hook's injected
   payload is over budget, it degrades per a rendering priority list — `narration →
   verdict → next-move → pointer → evidence`, truncated from the tail — never to a
   bare verdict-plus-pointer that drops `next_move`. A degraded payload that terminates
   in an unexplained verdict is the same forbidden shape arriving through the back
   door, so the priority list is what keeps `next_move` present in every degraded
   rendering, not only the full-size one.

3. **One voice across every surface that speaks — structural first, tested second.**
   The skill's own prose, the CLI's returned messages, and any hook-injected context
   must not contradict each other. An amnesiac reader cannot arbitrate between two
   surfaces that disagree — it has no history to break the tie, so it either stalls or
   picks arbitrarily. Two moves, in order of strength: **(a) structural** — a skill's
   prose carries no invocation strings at all (not even a drop affordance — it states
   *that* the affordance exists, never *how* to invoke it), so one surface cannot
   disagree with itself and drift becomes unrepresentable rather than merely
   detectable; **(b) mechanical** — a contract↔emission conformance test parses this
   wiki's § Typed field schema (required keys, enum domains) and asserts it against a
   real emitted decision object, catching the semantic contradictions a string-match
   test sails past ("prose says stop-with-offer, engine emits a bare exit"). Test
   surface: `coordinator/tests/test_pickup_contract_emission_conformance.py`.

**This axis is orthogonal to command-count.** A brief that costs the EM zero commands
and arrives as an unexplained wall of resolved JSON has traded one failure for
another — it discharged the mechanics and left the orientation on the operator.

## Lineage-aware liveness — a handover is not contention

Every liveness-bearing verdict a computed skill returns — a competing-claim scan, a
raw liveness signal, a claim-grant's holder check — must resolve a **live holder's
relationship to the artifact** before calling that holder a peer. A live session that
authored the artifact, or that holds or consumed the artifact named in this artifact's
`predecessor` / `additional_predecessors` / `forked_from` lineage fields, resolves to
**`handover`** — narrated as *"the session that handed this to you is still open;
that's a clean handover, not contention"* — and never forces a hold verdict. Only a
live holder with **no** lineage relationship to the artifact resolves to `live-peer`.

This is the commonest shape in the corpus, not an edge case: every plan-then-execute
split produces exactly this configuration — a predecessor session, still open,
handing a baton to a successor. Skipping the lineage check does not fail loud; it
fails silently, because a false hold is indistinguishable from a correct one at the
surface, and the EM has no way to tell "someone else is genuinely contending for this"
from "the session that gave me this baton hasn't closed its terminal yet." Lineage is
resolved from frontmatter the engine already parses to classify the artifact — no new
evidence source is required to apply this rule.

## MECHANICAL checklist (AC5) — each census branch mapped to a computed field

Derived from this plan's Problem-section inventory and from `pickup/SKILL.md`'s own
structure — not a second independent enumeration. Grouped by pipeline stage; each row
names the branch, its `SKILL.md` locus, and the decision-object field it computes into.

> **The `Locus` column names pre-rewrite pickup step-IDs as stable branch identifiers, not live section anchors.** The assembler computes at this branch granularity — one field per branch — which is finer than the rewritten skill's prose spine (that rebuild collapsed the old `Step 1.1`…`Step 5.5` numbering into three flat handoff steps plus a Memo Branch). A `Locus` value here is therefore the identity of the branch the field computes, not a heading you will find verbatim in the current `pickup/SKILL.md`. This granularity is deliberate and load-bearing: it is the contract `pickup-assemble` was built against, so it is preserved rather than flattened to the coarser new headings.

**Handoff branch — Steps 1–3, Step 5, Step 5.5:**

| Branch | Locus | Computed field |
|---|---|---|
| Dirty-tree scope extraction + commit | Step 1.1 | `preflight.dirty_paths`, `directives[]` (scoped `git add`/`commit`) |
| Branch resume/create | Step 1.2 | `gates.branch` |
| Branch-staleness age computation (fixed threshold, fixed message) | Step 1.3 | `preflight.staleness` |
| Archive-fallback: path-exists → `find` in 3 archive dirs → terminal-frontmatter read | Step 1.5 | `artifact.resolution` |
| Classification table: path + frontmatter shape → Handoff/Memo/Spinoff/Ambiguous | Step 1.5 | `artifact.classification` |
| Zero/one/multiple handoff enumeration (no-`$ARGUMENTS` path) | Step 2 | `artifact.candidates[]` |
| While-You-Were-Away: glob week-changelog, filter after handoff date, cap at 10 | Step 2.5 | `preflight.away_summary[]` |
| Referenced-file extraction from named handoff sections | Step 3.1 | `preflight.referenced_files[]` |
| Lessons enumeration | Step 3.2 | `preflight.lessons[]` |
| Branch-checkout-if-differs | Step 3.3 | `gates.branch` (target) |
| Git-log-since-date candidate scan | Step 3.4a | `preflight.candidate_closures[]` (evidence, not verdict) |
| Plan/stub closure-signal extraction (chunk-id commit scan, `Status:` read, wave-map read) | Step 3.4b | `preflight.closure_signals[]` |
| Deliverable-scope-paths glob + `ls` + git-log cross-check | Step 3.4b(iii) | `preflight.deliverable_evidence[]` |
| `handoff-gate-aging` 14d/7d threshold verdict (already a CLI) | Step 3.4d | `gates.aging_verdict` |
| Premise checks: `ls`/`Read` cited paths, `cat-file -e` + `branch --contains` SHAs, glob scope pathspecs | Step 3.4e | `preflight.premise_checks[]` |
| `execution_authorized_sha` recompute (`hash-object`) + compare | Step 3.4e | `gates.execution_stamp_match` — **emitted**, on any artifact carrying a `## Plan to Execute` pointer or an `execution_authorized_sha` (directly or on the plan it points at); `verdict` ∈ `match \| stale-bookkeeping \| stale-substantive \| unstampable` (§ Typed field schema). This branch is the contract's worked example of a tier split within one computed field: `stale-bookkeeping` promotes to a tier-1 re-stamp `directives[]` entry, while `stale-substantive` stays a tier-3 `judgment_points[]` entry (`recommendation: null`, `reason: insufficient-evidence`) — the engine reads the diff's shape, the EM reads the diff's meaning, the engine never adjudicates scope. `unstampable` names a stamped hash that reproduces at no revision including its own stamp commit — a mis-computed stamp, not a body edit, distinguishable because the body hash is invariant across the range; it carries a re-stamp `directives[]` entry, never a stale-plan report. |
| Stealth-skip pattern match on `shipped_in:` value shape | Step 3.4f | `preflight.stealth_skip_flags[]` |
| Prereq-table command re-run | Step 3.4g | `preflight.prereq_reverify[]` |
| Positive-liveness three-signal predicate (active handoff / `claim_holder_live` / recent chunk-id commit) — deterministic OR (signal *computation* only) | Step 3.4h | `gates.liveness_signal`; fire → surfaces the "Any peer live…? Stand down?" `judgment_points` entry (§ JUDGMENT checklist) — the resolve-or-stand-down call itself is JUDGMENT, not a mechanical auto-directive (see the note below the table) |
| Baton-repo resolution (tilde-normalize, `rev-parse --show-toplevel`, `--show-prefix`) | Step 5 (repo resolve) | `artifact.baton_repo`, `artifact.baton_relpath` |
| Pre-mutation gate 1: fetch + re-read | Step 5 gate 1 | `gates.claim.fetch_state` |
| Pre-mutation gate 2: `claimed_by`/`consumed_by` dual-read idempotency | Step 5 gate 2 | `gates.claim.holder` |
| Pre-mutation gate 3: atomic claim | Step 5 gate 3 | `directives[]` (`session-claim-cli claim-artifact`) |
| Pre-mutation gate 4: `pickup_ready` absence warning (fixed message) | Step 5 gate 4 | `gates.pickup_ready_warning` |
| Frontmatter mutation | Step 5 | `directives[]` (`archive-stamp-cli consume-handoff`) |
| Scoped commit | Step 5 | `directives[]` |
| Roadmap-callout refresh: extract `roadmap_id`, allowlist-guard, conditional call | Step 5 | `directives[]` (conditional) |
| Completeness-item parse (per item, via `parse-completeness-item`) | Step 5.5a | `preflight.completeness_items[]` |
| Restart-gated hoist/partition (fixed ordering rule) | Step 5.5b | `preflight.completeness_batches` |
| `TaskCreate` + disk-mirror `init` | Step 5.5c | `directives[]` |
| Probe three-state discriminator (pending-settle / restart-gated-expected / configured-but-broken — rule-based per `install-surface-completeness.md`), applied AFTER a probe has been confirmed and run | Step 5.5d | `preflight.probe_classification[]` |
| `spike-before-plan` / T3 token+heuristic detection | Notes/Step 6 | `gates.routing_signal` |

**Memo branch — M-addr through M4:**

| Branch | Locus | Computed field |
|---|---|---|
| M-addr addressee guard (CLI exit-code branch, fixed message templates) | M-addr | `gates.addressee` |
| M-pre branch guard (mirrors Step 1.2) | M-pre | `gates.branch` |
| M0 short-circuit on `status: actioned` (read terminal fields, STOP) | M0 | `artifact.terminal_state` |
| M1 read-before-act ordering (sequencing constraint, not a data field) | M1 | *(sequencing rule enforced by directive ordering, no field)* |
| M2 premise checks: locus grep, fetch+scan, archive sweep, absence-claim `branch -a`/`log --all` scan | M2 | `preflight.premise_checks[]` (memo variant) |
| M2 sender-absence-claim contradiction check (fixed rule: any hit surfaces contradiction) | M2 | `preflight.absence_claim_flags[]` |
| M2.5 claim gate: fetch+reread, `picked_up_by` idempotency incl. `clear-claim-if-dead`, atomic claim | M2.5 | `gates.claim` (memo variant) |
| M3 `kind`-enum resolution (absent → `ask` default; present-unrecognized → `ask` + warn; pinned-enum match) | M3 | `artifact.kind_resolved` |
| `scoped_to` declared-seam field extraction (artifact/version-or-sha/seam) | M3 | `preflight.scoped_to.declared_seam` |
| `distill_fate` default-mapping table (disposition type → `ephemeral`/`commitment`/`ratification` default) | M3 | attached as evidence on the owning `judgment_points` entry |
| Routed-plan reconcile: positive-liveness three-signal predicate (same predicate as Step 3.4h — signal *computation* only) | M0/M2.5/M3-Accept | `gates.routed_plan_liveness`; fire → surfaces the same stand-down `judgment_points` entry, not an auto-directive |
| M4 flip-in-place + release-claim-on-terminal (fixed sequencing) | M4 | `directives[]` (`session-claim-cli release-artifact`) |

That is ~44 rows against the plan's `~45` census figure — within the census's own
stated approximation; W0's re-verified count against the D1-landed file is the oracle,
and any material drift there amends this table, not the other way around.

**One coherent model for positive-liveness, stated once.** The three-signal predicate
appears at two loci (Step 3.4h and the memo branch's Routed-plan reconcile) because
`pickup` evaluates it in two contexts, not because it is split across MECHANICAL and
JUDGMENT. In both loci the split is identical: the engine COMPUTES the signal
(mechanical evidence — `gates.liveness_signal` / `gates.routed_plan_liveness`), and
"given a firing signal, proceed or stand down" is a single JUDGMENT entry (the "Any
peer live on this handoff/plan? Stand down?" row in § JUDGMENT checklist) that the
downstream claim/consume directives `depends_on`. A firing signal never auto-directs a
stand-down — it surfaces the judgment point; the EM's PM-confirmed resolution is what
unblocks (or continues to block) the dependent directives. This predicate is not a
branch counted twice against the census; it is one JUDGMENT branch computed from two
mechanical evidence sources.

**Probe-confirmation is JUDGMENT, not a `gates` boolean — this is a security gate, not
a bookkeeping one.** `pickup/SKILL.md` Step 3 (Completeness Checklist and Dispatch) is explicit: a `[probe: …]` value is
UNTRUSTED input — attacker-influenceable via the `completeness_checklist:` field on a
shared `work/*` branch — with full agent-Bash blast radius (credential exfiltration,
cross-repo mutation, file deletion) if auto-executed. "Explicit operator confirmation is
the SOLE gate." The probe *classification* three-state discriminator (the table row
above, applied only after a probe has already been confirmed and run) is genuinely
MECHANICAL — the assembler surfaces it as `preflight.probe_classification[]`. The
run/no-run *confirmation* itself is NOT: it is the "Run untrusted completeness probe
`<cmd>`?" `judgment_points` entry (§ JUDGMENT checklist), whose disposition is the ONLY
thing that resolves the probe-run directive's `depends_on`. **An autonomous no-human
consumer (the button-spawned session named in § two-phase-stateless) MUST leave this
judgment point unresolved when no human is present to confirm — the probe stays unrun,
its task stays open — never auto-satisfy it.** Classifying this gate MECHANICAL would
defeat its entire purpose in exactly the autonomous-consumer scenario this contract is
built for; JUDGMENT with mandatory non-auto-resolution is the only classification that
preserves the security property the gate exists to enforce.

## MIXED reclassification (AC5b) — the first sub-task, blocking the rest of A1

**Discriminator (single, mechanical): can the engine reach a correct answer with ZERO
semantic judgment?** Yes → MECHANICAL (folded into the checklist above). No → the
engine's narrowing becomes pre-gathered evidence on a `judgment_points` entry
(JUDGMENT). Zero branches remain "MIXED" in this contract.

**Census corrections applied (the Staff Engineer F15–F17, inputs to this reclassification — not a
substitute for W0's re-count):**

| Branch | Was | Reclassified | Rationale |
|---|---|---|---|
| Step 1.5 archive-fallback | MIXED | **MECHANICAL** | Path-exists check → `find` across 3 fixed archive dirs → read a fixed set of terminal frontmatter keys. No semantic step; the "found vs. not found" branch and the terminal-field read are both deterministic. On a multi-hit `find` (same basename swept into more than one archive dir), the assembler must detect-then-fail-loud — `artifact.resolution` surfaces ALL candidate paths rather than silently taking the first — never first-wins. |
| Step 2.5 While-You-Were-Away | MIXED | **MECHANICAL** | Glob a fixed directory, filter by date comparison, cap at a fixed number. No semantic step. |
| M-addr addressee guard | MIXED | **MECHANICAL** | A CLI exit-code branch (0/1/3/4) with fixed message templates per code. The comparison itself is path-based (`realpath` of resolved repo roots via the CLI), not a semantic judgment. |
| `scoped_to` reach-beyond challenge | MIXED | **JUDGMENT** | "Does the ask reach beyond the declared seam" requires understanding intent, not just comparing declared-seam fields to memo-body text. The engine surfaces the declared seam and the body's apparent targets as evidence; whether that constitutes over-reach is semantic. Held explicitly as a JUDGMENT entry — do not force to MECHANICAL. |

**Remaining MIXED-flavored branches audited in this pass** (the census's `~19` figure
is a count from the fence-state-machine methodology, not a published itemized roster;
these are the additional branches this read of `pickup/SKILL.md` found carrying the
MIXED flavor — engine can narrow, final call is semantic):

| Branch | Locus | Reclassified to | Rationale |
|---|---|---|---|
| Commit-subject "clearly matches" a pending item | Step 3.4a/b | **JUDGMENT** | Semantic match between a commit subject and a prose-described pending item. Engine narrows to a candidate commit list (`preflight.candidate_closures`); EM decides which, if any, close the item. |
| "Drop confirmed-closed items" verdict | Step 3.4c | **JUDGMENT** | Weighs the mechanical evidence bundle (closure signals + deliverable evidence + candidate commits) into a keep-or-drop call per pending item. The bundle is fully mechanical; the weighing is not. |
| Gate-source re-read: "has this gate actually cleared" | Step 3.4d | **JUDGMENT** | The `SKILL.md` text states this explicitly: "Whether the gate has cleared is the EM's judgment call from the Read above — not mechanized." The engine surfaces the gate path's content as evidence; it does not parse gate-clearance semantics. |
| Execution-authorized-SHA diff: bookkeeping vs. substantive | Step 3.4e | **JUDGMENT** | The plan's own taxonomy (ratification-line-only, `Status:` line, typo/formatting → bookkeeping; new task-spine row, changed target, altered AC → substantive) is mechanically pattern-matchable for the *named* categories, so the engine pre-classifies and attaches the diff plus its best-guess category as evidence — but "anything unclassifiable defaults [to substantive]" is an open-ended catch-all requiring semantic judgment on novel diff shapes. JUDGMENT with strong mechanical narrowing. |
| Route-to-baton scope-coverage check | M3 Accept | **JUDGMENT** | "An active baton whose scope covers this ask" needs semantic comparison between the ask's content and a baton's declared scope description, not just pathspec overlap. Engine surfaces candidate open/claimed handoffs as evidence. |
| Ceremony-calibration: mechanical-direct vs. escalate-to-plan | M3 Accept / `proposal` Adopt | **JUDGMENT** | "Novel decision", "instance #1 of a pattern with downstream occupancy", "vague enough to need shaping" are semantic magnitude calls the `ceremony-calibration.md` decider requires; not reducible to a fixed rule. |
| `fyi` impact-assessment routing (nil / plan-invalidated / surgical-fix / product-decision / ambiguous) | M3 `fyi` | **JUDGMENT** | Assessing memo content against active plans and in-flight workstreams for material impact is semantic; the engine surfaces the plan/workstream list as evidence. |
| Sibling-commitment-capture trigger recognition | Shared procedure (called from `fyi`/`ask` Accept/`proposal` Adopt) | **JUDGMENT** | Explicit in `SKILL.md`: "Capture is an agent JUDGMENT at pickup-action-time — there is no mechanical field that forces this." |
| `distill_fate` escalation to `ratification` | M3 (all dispositions) | **JUDGMENT** | Whether a specific disposition "settles ownership or a seam PERMANENTLY" vs. merely realizes bounded work is a semantic call about the disposition's actual weight. The engine attaches the default mapping (accept→commitment, decline→ephemeral, etc.) as evidence; the escalation override is the EM's. |
| Sibling-dedup "same-topic" match | M2 | **JUDGMENT** | Determining that a sibling-repo memo hit is genuinely the *same* topic (not merely a grep coincidence) before treating it as resolving evidence is semantic. Engine narrows via topic-noun grep across the sibling's inbox/archive. |
| M3 `proposal` Adopt/Decline/Negotiate | M3 `proposal` | **JUDGMENT** | "Fits this repo's current direction" is the core adjudication the `proposal` disposition exists to make; irreducibly semantic. |
| Dispatch routing: EM-inline vs. dispatch-executor | Step 6 / M3 Accept "perform the work" | **JUDGMENT** | The `agent-dispatch-economics.md` § When-to-EM-Inline checklist is conjunctive and requires judging whether *all* criteria hold in context, not a fixed boolean the engine can decide standalone. |

That accounts for the full ~19-branch MIXED set this pass identified plus the
4 named corrections (some branches above appear in both tables where the plan's
correction and this pass's independent read converged on the same locus — no
double-counting against the census, since the corrections are a subset of the audit,
not additive to it). **Zero branches remain "MIXED" in this contract.** No branch in
this audit resisted forcing to one side or the other — there is no BLOCKED finding to
surface to the PM from this pass. A1r (the review gate) re-verifies this table against
`pickup/SKILL.md`'s post-D1 content before A2 builds against it.

## JUDGMENT checklist (AC6) — every entry an offer, never a verdict

The native ~17 plus every MIXED branch reclassified to JUDGMENT above collapse into
one list, because they share one contract shape: a `judgment_points` entry with
`question`, `evidence` (pointer into `preflight`/`gates`), `dispositions[]` (each
naming its resolved `directives`), and `round_trip: terminal` (see § Round-trip
classification — none in this inventory are `round_trip`).

| Judgment point | Evidence surfaced | Dispositions | `revalidate_at_dispatch` |
|---|---|---|---|
| Does this commit close this pending item? | Candidate commit list (subject, SHA, date) per item | keep-open \| close \| close-with-note | `false` |
| Overall keep/drop verdict per pending item | Closure signals + deliverable evidence + candidate commits, bundled | drop-from-queue \| retain-in-queue | `false` |
| Has this `awaiting_gate` handoff's gate actually cleared? | Gate-path content (Read result) | cleared → `--cleared` gate-recheck \| not-cleared → stamp-only | `false` |
| Is this `execution_authorized_sha` mismatch bookkeeping or substantive? | Diff `stamp-commit..HEAD -- <plan-path>`, pre-tagged bookkeeping/substantive/unclassified | bookkeeping → re-stamp+proceed \| substantive/unclassified → surface to PM | `false` |
| Any peer live on this handoff/plan? Stand down? | Three-signal positive-liveness predicate result | proceed \| stand-down-and-surface | **`true`** — evaluated once at brief-compute time (Step 3.4h) but re-run live immediately before dispatch (memo branch: M3 ask-Accept's mandatory pre-dispatch reconcile, § Round-trip classification); never trust the brief-time value at dispatch time |
| Is this memo an over-reach on its declared `scoped_to` seam? | Declared seam fields vs. apparent ask targets | in-scope \| challenge-via-return-memo | `false` |
| Does an active baton's scope cover this `ask`? | Candidate open/claimed handoffs + their scope text | route-to-baton \| adjudicate-standalone | `false` |
| Mechanical-direct or escalate to a plan? | Named-signal checklist (novel/instance-1/vague) evidence | mechanical-direct \| escalate-coordinator:plan | `false` |
| `fyi` impact: nil / invalidated / surgical-fix / product-decision / ambiguous | Active-plan list, in-flight workstream list | ack-nil \| re-plan \| surgical-fix \| surface-to-PM \| investigate-further | `false` |
| Does this action owe a sibling-commitment watch-ledger entry? | Memo body text (forward-looking commitment language) | write-entry \| no-entry | `false` |
| Should `distill_fate` escalate to `ratification`? | Default mapping for the chosen disposition | accept-default \| escalate-to-ratification (+`in_repo_capture`) | `false` |
| Is this sibling-inbox hit genuinely the same topic? | Topic-noun grep hits across sibling `cross-repo/{inbox,archive}/` | same-topic-resolves-issue \| coincidental-no-action | `false` |
| `ask`: Accept / Decline / Surface-to-PM | Full memo body, M2 premise-check bundle | accept-mechanical-direct \| accept-escalate-to-plan \| decline \| surface-to-PM | `false` — the Accept disposition itself is not freshness-sensitive; the *positive-liveness* judgment point it triggers a mandatory re-run of (pre-dispatch reconcile) is the row above |
| `proposal`: Adopt / Decline / Negotiate | Full memo body, this repo's current direction (named plans/wikis) | adopt \| decline \| negotiate | `false` |
| Inline this fix, or dispatch an executor? | `agent-dispatch-economics.md` checklist evidence (size, novelty, context) | em-inline \| dispatch-executor | `false` |
| Run untrusted completeness probe `<cmd>`? | Probe command string, verbatim, from a `completeness_checklist:` on a shared `work/*` branch — treat as untrusted | confirm-and-run \| skip-and-validate-manually | `false` |

Every row's `dispositions` are pre-resolved directive templates, not open text — the
EM picks one, and the corresponding `directives` entries execute. No entry is silently
auto-decided; AC6's bar is enforced by construction, not by convention.

## Consumes manifest (the Director of Engineering F3, AC16) — orchestrates, does not reimplement

`pickup-assemble` MUST consume the following existing `coordinator_core` capabilities
— in-process import for read-only computation, or as a named returned `directives`
entry for anything mutating. It reimplements none of them:

| Capability | Consumed as |
|---|---|
| `coordinator_core.session.liveness` (`session_live`, `live_session_ids`, `claim_holder_live`) | in-process import — powers `gates.liveness_signal` / `gates.routed_plan_liveness` |
| `handoff-gate-aging` | in-process import (or subprocess of the existing CLI) — powers `gates.aging_verdict` |
| `archive-stamp-cli` (`consume-handoff`, `gate-recheck-handoff`, `claim-memo-stamp`, `action-memo`, `unconsume-handoff`, `release-memo-revert`) | returned `directives` entries — the assembler names the call, never runs it |
| `session-claim-cli` (`claim-artifact`, `clear-claim-if-dead`, `release-artifact`) | returned `directives` entries |
| `coordinator-queue-append` | returned `directives` entry (conditional, on sibling-commitment-capture trigger) |
| `cross-repo-memo --check-addressee` | in-process import or subprocess — powers `gates.addressee` |
| `refresh-roadmap-callout` | returned `directives` entry (conditional) |
| `parse-completeness-item` | in-process import — powers `preflight.completeness_items[]` |
| `coordinator-tasks-mirror` (`init`, `update`) | returned `directives` entry (conditional, on `completeness_checklist` presence) |

**`preflight.dirty_paths` scope-block extraction.** The assembler consumes
the shared, parameterized `coordinator_core.ops.extract_scope_paths._extract_scope_paths(text,
key=...)` for both list-shaped frontmatter keys (`scope:` *and* `completeness_checklist:`)
rather than hand-rolling either — the uniform block-parser this rule requires.
`coordinator_core/ops/dirty_tree_gate.py` consumes the same shared parameterized extractor.
No caller of this manifest hand-rolls a block-scan the shared extractor already provides.

The assembler is a **surface** — one entrypoint the EM invokes instead of walking the
M-addr→…→M3 ordering by hand — over **composed internals** that consume these named
modules. It is not a new computation engine; A2's build must not introduce logic that
duplicates what any of the above already exports. AC16's verification is a direct diff
against this table: every new function in `coordinator_core.pickup_assemble` either
calls one of these, or is glue code assembling their outputs into the schema above.

**`TaskCreate` itself is a harness tool, not a `coordinator_core` capability — the
assembler cannot call it in-process.** The completeness-checklist path (Step 5.5c) emits
directives the EM runs (`coordinator-tasks-mirror init`/`update` naming the disk mirror,
plus the harness-native `TaskCreate` calls the EM performs directly), not in-process
assembler calls; the manifest row above covers the disk-mirror half only.

## Template-scope partition (the Director of Engineering F5) — what generalizes, what's pickup-specific

| Contract element | Scope |
|---|---|
| The eight-key schema shape (`artifact`/`preflight`/`gates`/`directives`/`judgment_points`/`decisions`), plus the top-level `narration`/`next_move` fields — § Decision-Object Schema-of-Record | **Candidate-general** — every computed skill returns this shape |
| The three-tier model (do-for-you / recommend-for-you / your-call) and the compute/apply split it executes through | **Candidate-general** — the reusable pattern every computed skill's mutating half is built against |
| The judgment-point constructor contract (required `recommendation` parameter; a distinct no-parameter constructor for recommendation-forbidden gates) | **Candidate-general** — every computed skill authors judgment points against this constructor contract |
| The closed dispatch table + no-subprocess + in-repo-path bound on a mutating `apply` half (§ What bounds a mutating apply half) | **Candidate-general** — every computed skill's apply half is bound by the same four structural properties |
| The general `revalidate_at_dispatch` disposition-reuse rule (a disposition is not reusable across a recompute, for *any* entry carrying the field) | **Candidate-general** — not a `claim_grant` special case |
| "No automated consumer derives a disposition from a `recommendation`" | **Candidate-general** — a design constraint on every computed skill's decision object, not a pickup convention |
| The lineage-aware liveness rule (a live holder related to the artifact via authorship or predecessor lineage resolves `handover`, not `live-peer`) | **Candidate-general** — every computed skill that reads liveness inherits this |
| The `brief [--decisions]` two-subcommand surface, incl. the single-shot-by-default / `--decisions` for crash-resume-and-audit pattern | **Candidate-general** — the round-trip finding may differ per target skill, but the protocol shape (single call unless a genuine round-trip exists) generalizes |
| The 0/1/2/3 brief-side exit-code contract, and the separate 0/1/2/3/4 mutating-half exit-code enumeration (§ Exit-code contract for a mutating half) — each locally defined, not inherited | **Candidate-general as a pattern** — each computed skill defines its own instance; the codes' meanings are not shared verbatim across skills |
| The MECHANICAL/JUDGMENT discriminator ("can the engine reach a correct answer with zero semantic judgment") | **Candidate-general** — this is the reusable audit procedure, not pickup-specific content |
| The candor principle (offer, never verdict) | **Candidate-general** — a design constraint on every computed skill, not a pickup convention |
| The step-level extraction unit (a step that only sequences is as extractable as one that branches; the skill names an op, it never narrates a procedure) | **Candidate-general** — a design constraint on every computed skill, not a pickup convention |
| Arrival legibility (narrate-before-evidence with register separation, no surface terminates in a refusal, one voice across every surface that speaks) | **Candidate-general** — every computed skill that auto-fires or returns a decision object inherits these three rules |
| `pickup`'s specific `gates` set (claim/addressee/branch/aging) | **Pickup-specific** — a different skill's gate set reflects its own preconditions |
| `claim_grant`, `coast`, `CLAIM_STALE_AFTER`, and the claim-grant truth table | **Pickup-specific** — claim semantics answer questions specific to claiming a baton; a skill that claims nothing should not inherit a claim gate or a settling window |
| `tree_quiescence` and `competing_claim` | **Pickup-specific** — `pickup`'s own coverage-gap fields, not a general schema requirement |
| The memo/handoff bimodal classification and the two parallel branch structures it produces | **Pickup-specific** — `workstream-complete` and other frontage targets are not bimodal in this way |
| The specific `directives` CLI catalogue (archive-stamp-cli verbs, session-claim-cli, etc.) | **Pickup-specific instantiation** of a general pattern (name existing atomic CLIs as directives) — the *pattern* generalizes, the specific CLI names do not |
| `gates.execution_stamp_match`'s specific verdict enum and computation | **Pickup-specific instantiation**; the tier-split it demonstrates (stale-bookkeeping promotes to a directive, stale-substantive stays a tier-3 judgment point) is the **candidate-general** worked example of the three-tier model |
| `pickup`'s specific `judgment_points` inventory (the table above) | **Pickup-specific** — content, not shape |

## Generalizing this pattern (AC14) — the procedure `workstream-complete` follows

A future computed-skill conversion (named next: `workstream-complete`, which already
carries the ASIC helper-extraction — see § Vocabulary) follows this procedure without
re-deriving the shape from scratch:

1. **Census every mechanical step, not only every decision branch.** Walk the target
   skill's prose tree and classify every step MECHANICAL, JUDGMENT, or (provisionally)
   MIXED, using the same fence-state-machine-or-equivalent methodology this plan's
   Problem section used. A step with zero branches is still in scope: an ordered pair
   of mutations the EM merely sequences ("stage these paths, then commit them"), a
   `[placeholder]` the EM resolves by inference, or a restated invariant ("never
   `git add -A`") are each pure functions of disk/git/frontmatter and become a
   `directives[]` entry exactly as a branching step would. The unit of extraction is
   the mechanical step, not the mechanical branch (DR-090; see
   `docs/wiki/coordinator-tripwires/draft-plan-aging.md § SKILL-NARRATES-PROCEDURE`). The census itself
   is a schema'd artifact, not a hand-rolled table: it validates against
   `coordinator/schemas/census-document.schema.json` and lives at
   `state/plan-sidecars/<plan-or-skill-stem>.census-steps.md`, one per conversion.
2. **No MIXED row may remain unsplit.** This is the MIXED concession's actual term:
   claude-klabauter's row schema persists MIXED as a container of two half-steps, so the
   invariant is `MIXED ⇒ both mechanical_part and judgment_part present` — exactly its
   own `allOf` conditional, not a looser "mostly split" reading. A row that resists
   splitting is a BLOCKED finding surfaced to the PM, not a re-parked middle bucket.
3. **Sort every step into one of the three tiers** (§ The three-tier model), not just
   into MECHANICAL/JUDGMENT. A MECHANICAL step is tier 1 (`directives[]`). A JUDGMENT
   step needing an offer becomes a tier-2 `judgment_points[]` entry carrying
   `recommendation`; a JUDGMENT step the engine genuinely cannot narrow — including any
   recommendation-forbidden step, built through the no-recommendation constructor —
   becomes tier 3. This is a finer sort than a binary MECHANICAL/JUDGMENT pass and is
   where the schema's `recommendation` field actually gets populated correctly.
4. **Instantiate the general schema.** Reuse the five-key shape and the top-level
   `narration`/`next_move` fields verbatim (§ Template-scope partition, candidate-general
   rows). Populate `gates` and `judgment_points` with the target skill's own content —
   do not import `pickup`'s specific gate set or judgment inventory. Build the mutating
   half against the same closed-dispatch-table bound (§ What bounds a mutating apply
   half) and its own exit-code enumeration (§ Exit-code contract for a mutating half) —
   do not reuse pickup's specific codes verbatim.
5. **Classify round-trip vs. terminal per judgment point,** and let that finding
   determine single-shot vs. genuine two-phase for *that* skill — do not assume
   `pickup`'s empty-round-trip-set finding transfers; a different skill's judgment
   points may genuinely gate downstream mechanical recomputation. The general
   `revalidate_at_dispatch` disposition-reuse rule (§ Round-trip classification)
   applies to every entry so marked, not only the ones this target skill happens to
   share with `pickup`.
6. **Write the consumes manifest** before building — name every existing
   `coordinator_core` capability and atomic CLI the assembler orchestrates, and hold
   the build to reimplementing none of them (mirrors AC16). Pair it with a
   contract↔emission conformance test (§ Arrival legibility, rule 3) parsing this
   skill's own § Typed field schema against a real emission — a per-field row for
   every field the skill introduces, never a catch-all `gates.*`/`preflight.*` row,
   or the test passes blind.
7. **Rebuild the retained skill prose to evergreen — and push, not pull (realizations #5
   and #6).** Not merely thinned: the axis-2/axis-3 bar (de-changelog, consolidate)
   applies to every frontage conversion (per the frontage-rollout remit this plan
   mirrors). But thinning is not the bar — the bar is that **the skill body branches on
   nothing the engine resolved.** Grep the rebuilt body for classification/branch-selection
   vocabulary (`if <classification>`, "if memo", "branch on", "if a peer is live") and
   expect it empty; deterministic if/else is code in a markdown fence one abstraction up
   (`invisible-doctrine.md` § "The adventure"). What survives is the irreducible
   non-branching action core plus genuine universals; the classification-appropriate
   adventure is *injected at fire time*, keyed on the material, never a section the
   operator navigates to. Line-count of the skill body is a real success criterion. Name
   every retained/deleted/relocated block's fate explicitly — an orphaned block forces the
   next pass. Apply arrival legibility (§ above) to whatever the skill still emits.
8. **Exercise the delivery seam end-to-end (realization #5) — do not assert it.** "The
   assembler returns the object" ≠ "the operator receives the adventure." Trace the wire
   and exercise it under a realistic full payload: confirm (a) the consuming surface no
   longer duplicates logic the compute layer resolved, and (b) the hook/caller actually
   reaches and invokes the mutation layer — not a CLI verb that doesn't exist yet (the
   silent fail-open trap that cost `/pickup` a second pass). The resolved guidance must
   render in the operator's hands as a protected segment (§ Arrival legibility, the
   degraded-payload priority list) — never a first-dropped JSON evidence tail. A green
   unit test on the compute layer and a correct-looking hook are each necessary and
   NEITHER is sufficient; the check is whether the wire is live, verified by running it.
9. **Dogfood before declaring stable,** with a corpus sized to the round-trip finding
   from step 5 (AC8's rule: non-trivial round-trip set → corpus must force ≥2
   sequential dependent judgment points; empty/trivial set → ordinary behavioral-parity
   corpus suffices).

Steps 1–2 and 6 are audit work a Sonnet-tier pass can do against the target skill and
this wiki alone; step 7 needs the same evergreen-rewrite discipline
(`docs/wiki/rag-bait-conventions.md`, `no-ruling-dates-in-skill-surfaces`) applied here.

### Legacy census gap — recorded, not migrated

`state/plan-sidecars/2026-07-26-workstream-complete-computed-frontage.census-steps.md` (the
92-row `workstream-complete` census used above) predates `census-document.schema.json` and does
not validate against it. Recorded here so a census author reads the gap before assuming that file
is a conforming example; it is not migrated. Missing: the entire envelope — no YAML frontmatter at
all, so none of `schema_version`/`skill`/`source_path`/`source_sha`/`unit`/`taken_at`/
`round_trip_shape`/`rows` exist on disk. Its `## Table` rows carry no `step_id` field (the `Step`
column is a locus label, not a stable id) and their `Classification` values fail the row schema's
enum: the file's `DIRECTIVE`/`JUDGMENT`/`MIXED-SPLIT` vocabulary (plus ad hoc values like
`BLOCKED` and `Not a step (...)`) has no member in common with claude-klabauter's closed
`MECHANICAL | JUDGMENT | MIXED` set — `DIRECTIVE` and `MECHANICAL` name the same concept under
different words, and `MIXED-SPLIT` is expressed as two separate table rows (a mechanical-half row
and a judgment-half row) rather than one `MIXED` row carrying both `mechanical_part` and
`judgment_part`, which the row schema requires together on a single row.

## Multi-module compute layer — the layout convention past ~1500 lines (F6/F7, `workstream_complete`)

`pickup`, the nearest precedent, stays a single `__init__.py`. `workstream_complete`
(convert #2) is the tree's first compute layer to split: ~35 new directives and ~20
judgment points cannot land in one file without serializing every executor on a shared
write target, so the module divides into domain-cohesive submodules —
`directives_lessons_plan.py`, `directives_completion.py`, `directives_memo_lifecycle.py`,
`directives_session_hygiene.py`, `directives_review.py`, `directives_commit_tail.py`,
`judgments.py` — with `__init__.py` retained as the assembly + CLI seam
(`docs/plans/2026-07-26-workstream-complete-computed-frontage.md` D-4). This is the
convention the next large conversion inherits deliberately, not by imitation:

- **Split on domain seam, not on step-number adjacency.** A cut is legitimate when it
  groups steps a solo author would plausibly co-locate once the module got large —
  lessons/plan, completion, review, commit/tail, judgments were each cohesive on this
  basis. A cut driven by steps merely sitting next to each other in the deleted ordinal
  spine is not cohesion — adjacency in a spine this conversion's whole thesis says was
  never the real structure doesn't survive as a module boundary either. `workstream_complete`
  caught exactly this: an initial `directives_scratch_memo.py` bundled memo lifecycle,
  scratch self-clean, the orientation pinboard, machine-local regeneratability, and the
  completeness-checklist WARN gate into one file because their step numbers happened to be
  adjacent; splitting it into `directives_memo_lifecycle.py` and
  `directives_session_hygiene.py` along the actual concern boundary was the fix.
- **Every submodule's docstring names the convention explicitly** — that it is one part of
  a multi-module assembler, and which sibling modules complete the set. A reader landing
  on one submodule cold must be able to tell it is not the whole compute layer without
  grepping the directory.
- **`__init__.py` stays the sole assembly + CLI seam.** Submodules export directives and
  judgment constructors; only `__init__.py` assembles the envelope and exposes the CLI
  entrypoint — a submodule importing another submodule's assembly logic (rather than the
  other way around) is the tell that the split picked the wrong seam.
- **The decision to split is a size-and-fan-out call, not a fixed line count.** The trigger
  here was "this makes seven parallel executors possible instead of one serializing
  grind" (§ Adding a Convention framing, `~/.claude/CLAUDE.md` fan-out doctrine) — reach
  for the same split once a compute layer's directive/judgment count would otherwise force
  one write target across an entire wave.

## Family-scoped factoring vs. the cross-family runner (F1/F2/D-1, `workstream_complete`)

Two axes look similar and are not: a **cross-family runner** (`coordinator_core.contract.apply_base`,
4 unrelated consumers — pickup, baton, merge, consolidate) and a **family-scoped factor**
(`coordinator_core/ceremony_common/`, shared only among `X_complete` ceremony-close
assemblers — `workday_complete`, `workweek_complete`, and now `workstream_complete`). The
rule the next `X-complete` converter inherits:

- **Share the family-scoped factor.** `workday_complete` and `workweek_complete` already
  import `build_ceremony_close_tail` from `ceremony_common.tail` rather than hand-deriving
  it; `workstream_complete` extended the same module with `ceremony_common/apply_halt.py`
  (the `_directive_gate_open`/`_disposition_resolves_directive` halt-trio, factored out of
  two byte-identical hand copies, plus the shared exit-code ladder) and repointed both
  existing consumers onto it. A third ceremony-close assembler joining `ceremony_common` is
  conforming to an existing family factoring surface, not inventing a new dependency.
- **Abstain from the cross-family runner by name.** Do not import or extend `apply_base.py`
  from an `X_complete` assembler — that consolidation is a different owner's baton (DR-092
  AC-5), and joining it as an ad-hoc 5th consumer creates migration debt on someone else's
  future reshaping of it. Author the family's own standalone `apply.py` (own exit-code
  enum via `extend_exit_codes`, own closed dispatch table) and state the abstention as an
  explicit negative-spec docstring line, paired with the positive counterpart naming what
  *is* composed instead (the `ceremony_common` halt-trio).
- **The discriminator is "does more than one sibling in the same close-ceremony family
  already share this," not raw instance count.** A third similar-shaped module does not by
  itself justify folding into the cross-family runner — the trigger for that fold is
  understood divergence against the runner's owner's own axes, not count=2 or count=3
  (`docs/plans/2026-07-24-canonical-resolution-engine.md` AC-5).

## Decision-Object Schema-of-Record (DR-047)

DoE owns the decision-object schema-of-record; claude-klabauter owns the engine that emits and
validates against it. Per DR-047's split (DoE owns contract, claude-klabauter owns engine), the
canonical shape of the 8-key envelope described throughout this wiki is now codified as
a standalone JSON Schema (draft 2020-12) at `schemas/decision-object.schema.json` — not
re-derived informally from prose each time a new computed skill or validator is
authored. Claude-klabauter's `coordinator_core` decision-object validators (`envelope.py` for the
top-level envelope, `judgment.py` for `judgment_points[]` shape) conform to this schema;
they do not define their own competing notion of the shape.

Only the **candidate-general** elements from § Template-scope partition above are
codified as required schema shape: the 8-key envelope, the `directive` and
`judgment_point` item sub-shapes, and the `subagent_sidecar` container. Per-skill
instance content — `pickup`'s specific `gates` set (`claim_grant`, `coast`,
`tree_quiescence`, `competing_claim`), its specific `directives` CLI catalogue, and its
specific `judgment_points` inventory — is deliberately left permissive
(`additionalProperties: true`) in the schema rather than baked in as required fields;
those are a per-skill instantiation of the general pattern, not part of the schema
itself.

The 8 top-level keys:

| Key | Shape | Purpose |
|---|---|---|
| `artifact` | object | The classified artifact this decision object was computed against — resolved path, parsed frontmatter, classification; archive-fallback carries terminal `resolution` data instead of live frontmatter. |
| `preflight` | object | Evidence gathered from disk/git state, scoped to the workstream — evidence *for* `judgment_points` to cite, never itself a verdict. |
| `gates` | object | MECHANICAL-tier facts the engine computed deterministically — trustworthy without re-derivation; a gate needing semantics belongs in `judgment_points` instead. |
| `directives` | array of `directive` | Do-for-you tier: ready-or-blocked mechanical actions, each naming an existing atomic CLI (never an inline command payload). |
| `judgment_points` | array of `judgment_point` | Your-call tier: open questions the engine cannot resolve mechanically, each with dispositions, evidence, and (except untrusted-gate points) a recommendation. |
| `decisions` | object | Free-form map of dispositions already resolved for this artifact (e.g. from a prior `--decisions` round-trip). |
| `narration` | string | One-voice, narrate-before-evidence summary of the computation (arrival legibility) — never terminates in a refusal. |
| `next_move` | string | The single next action the consumer should take given the current directive/judgment-point state. |

The schema also pins the two judgment-point constructor contracts as a nullability
distinction on `recommendation`: `build_judgment_point(...)` requires a non-null
`recommendation`; `build_untrusted_gate_judgment_point(...)` takes no `recommendation`
parameter at all, so the key is always present, value `null`, by construction for
untrusted-gate judgment points — offer-forbidden by design, per the candor principle
(offer, never verdict; no automated consumer derives a disposition from a
recommendation).

A `subagent_sidecar` `$defs` sub-schema models the agent-side instance of the same
envelope idea — the decision-object container seen from a dispatched subagent's input
end (its run-report sidecar frontmatter). Beyond ordinary dispatch frontmatter, it
requires `completion_status` (a durable, queryable "task done" marker backlinking the
existing `query-completions` records surface — not a new store), `divergence_from_plan`
(`{diverged, summary, detail}` — executor-authored prose defending any deviation;
untrusted narrative, never re-read as a directive), and `tell_the_EM` (a freeform
exit-interview channel).

See `schemas/decision-object.schema.json` for the full machine-checkable definition.

## Canonical Resolution Engine — the shared contract library

<!-- PROVENANCE: run 2026-08-06-14h38, nuggets c7-008, c7-010 -->

This session shipped the first shared library two computed-skill front-ends *compose*, and the
architecture is worth naming precisely because the easy version of "share code between the two
front-ends" is a trap this session deliberately did not fall into.

**Shared CONTRACT, not shared COMPUTE.** A library both front-ends compose (types, validators,
constructors, a thin facade) is sound; a god-assembler both route control-flow *through* is the
FOLD-INTO-CALLER trap — it re-centralizes the per-domain routing that belongs inside each
assembler, and the first domain divergence forces either a caller-side special case or a
speculative parameter neither domain asked for. The per-domain routing decision — which gates to
check, which directives to emit, which judgment points to raise — stays inside each assembler.
What's shared is the *shape* those decisions must conform to, not the decision logic itself.

**Two tiers + one discipline.**

- **Tier-A — the resolution facade** (`claude-klabauter`'s `coordinator_core/resolution/facade.py`):
  the compute-only entrypoint both front-ends call to resolve a target artifact/session/root down
  to a typed result, before either front-end starts assembling its own decision object.
- **Tier-B — the declarative contract library** (`coordinator_core/contract/decision_object/`):
  the 8-key envelope (§ Decision-Object Schema-of-Record above), the `_emit()` chokepoint every
  decision object flows through on its way out, and the two judgment-point constructors
  (`build_judgment_point` / `build_untrusted_gate_judgment_point`) that pin the
  recommendation-nullability distinction at construction time rather than leaving it to
  per-caller discipline.
- **Consumer discipline** — the shared shape only holds if every caller actually uses it. That
  discipline is the DR-090 per-baton checklist
  (`coordinator/docs/wiki/computed-skills-conversion-checklist.md`, authored this session) plus
  the anti-rebound inline-mechanism budget gate: a converted skill that re-accretes a mechanical
  step inline is rebound, and the checklist is what catches it before merge rather than three
  conversions later.

**Two-method guard boundary is security-load-bearing, and the discriminator is PROVENANCE of the
root, not the operation being performed.** `resolve_operator_config()` is corruption-checked
only — it reads operator-authored config, which can be malformed but is not attacker-steerable,
so a schema/parse check is the right and only check. `guard_plugin_root(root, *, mode)` is
trust-guarded only, and it delegates to the shipped `coordinator_trusted_root_guard` rather than
reimplementing trust logic locally — there is exactly one trust implementation in the system,
never a second one grown alongside a new call site. Collapsing these into one `validate_root()`
would either over-check operator config (rejecting legitimate operator variance as if it were an
attack) or under-check a plugin root (treating trust as a formatting concern) — the two failure
modes are not symmetric, so the function boundary encodes a real distinction, not a stylistic
one.

**Schema-of-record ownership (DR-047) restated for this session's build.** DoE owns
`schemas/decision-object.schema.json` (authored this session, § Decision-Object Schema-of-Record
above); the claude-klabauter-side `contract/decision_object` validators conform to it rather than defining
a competing notion of the envelope shape.

**The divergence-understood extraction trigger — and why the Tier-B apply-side runner was NOT
factored this session.** Convert #2 (`workstream_complete`) landed **compute-only** — it has no
in-package apply/dispatch half; its directives are dispatched by the ceremony/EM, not by an
in-package runner. That leaves only `pickup` exercising an apply-side runner, so n=1 for the
thing a "universal" Tier-B apply runner would need to generalize over. Per AC-5 / Risk R-2,
factoring `apply_base.py` from a single real instance would codify pickup's specific shape as
the invariant — precisely the "1 built + 9 paper designs codifies the wrong invariant" failure
this campaign exists to avoid. Convert #2's compute-only outcome IS the divergence signal (a
weak fit against B9's candidate-general list): the apply-side runner is not yet proven
candidate-general, so it does not get extracted on the strength of one witness.

**W2-B2 (the apply-side runner factoring) is therefore a scheduled deferral, not an abandonment**
— Risk R-6's named mitigation, with an explicit trigger rather than a vague "later": **a second
assembler that genuinely exercises an apply/dispatch half.** Until that second witness exists,
the plan's own defer branch is the one to follow, and it was followed this session — B3 (the
agent-side sidecar, below) was built ahead of any Tier-B runner factoring, exactly as the plan's
priority ordering specified. AC-5 is satisfied by the act of NOT factoring, not despite it; the
trigger condition itself is recorded in DR-092 rather than left to institutional memory, so the
next assembler that lands can check the decision record instead of re-deriving the reasoning.
<!-- distill:2026-08-06-14h38 src:c7-009 -->

**claude-klabauter DR-215 stays retired for this surface.** The ≤60 ms per-brief budget this session's facade and
contract library hit is met by lazy-import plus in-process git, not a resident daemon; a
`<10 ms` target is an explicitly-deferred stretch goal that would require re-litigating claude-klabauter DR-215's
daemon-retirement, not something either tier was built to hit this session.

**Agent-side sidecar — the same envelope shape, read from the input end.** The
`subagent_sidecar` container (§ Decision-Object Schema-of-Record above) is not a separate
invention; it's a shape-guarded instance of the same decision-object idea, seen from where a
dispatched agent reads it rather than where an assembler emits it. The engine provisions an
*empty* sidecar file as a write TARGET — never a write CAPABILITY the agent previously lacked —
and injects the sidecar path plus the agent's citizenship metadata into the dispatch. Confinement
stays structural and upstream of the sidecar itself, the same shape as `code-reviewer`'s
command-allowlist: the scaffolder that provisions the sidecar never widens what tools the
dispatched agent may call: only the intake surface it can write to changes.

<!-- distill:2026-08-06-14h38 src:c7-010 -->
**Dogfood converged: canonical paths are cheaper than the ceremony they replace.** Both
`pickup` and `workstream_complete` — the two converts this session exercised through the
Tier-A facade and Tier-B contract library above — confirmed their canonical (computed-skill)
path is genuinely cheaper in practice than the ad-hoc ceremony it replaces, not merely
equivalent to it. This is the outcome the per-baton conversion checklist and anti-rebound
budget gate (§ above, "Consumer discipline") exist to protect: a conversion that lands the
new shape but leaves the old ceremony cheaper (or no cheaper) at the point of use is the
failure mode those gates catch before merge.

Spec backlink: `docs/decisions/DR-092-canonical-resolution-engine.md`;
`docs/plans/2026-07-24-canonical-resolution-engine.md`.

## Multi-baton `/pickup` — one hook, N==1 and N>1 uniformly

<!-- distill:2026-08-06-14h38 source:c7-013 -->
> Spec backlink: `2026-07-24-multibaton-pickup-and-args-prose-7167e1.md`.

Earlier `/pickup` hook prose assumed a single-baton shape. The hook now decodes
**both** the single-baton and multi-baton wire shapes into one normalized
`list[dict]` before doing anything else — there is no separate N==1 code path
that diverges from N>1; N==1 is just the one-element case of the same list.

**Correctness fix folded in: resolve off `artifact.path`, not the requested
path.** Each baton in the list is applied off its **resolved** `artifact.path`
— the path the assembler actually classified and computed evidence against —
never the raw path the caller passed in. This matters specifically on the
archive-fallback branch (§ `artifact` above): when a requested path is absent
but found via the three-archive-dir `find` sweep, `artifact.path` is the
*resolved* location, and a baton applied against the pre-resolution path would
silently miss the archived artifact's real state. Prior single-baton code that
happened to reuse the caller-supplied path worked by coincidence when no
archive-fallback was in play; the multi-baton rewrite makes resolving off
`artifact.path` the uniform rule for every baton in the list, closing that gap
generally rather than special-casing the archive branch.

**Rendering: one verdict/next-move pair per baton, budget-capped as a set.**
The hook renders exactly one verdict line and one `next_move` (§ Arrival
legibility) per baton, and the whole rendered block — not any single baton's
share of it — is held under the existing 10K injected-context budget. An
EM-facing ` -- <prose>` suffix that earlier baton-argument shapes carried is
stripped before rendering: that free-text tail is caller-composed prose, not
engine-computed evidence, and belongs to the same class of untrusted,
non-computed content the recommendation-forbidden discriminator (§ The
three-tier model) already excludes from influencing engine-authored output.

**Pinned by a negative-spec docstring naming the claude-klabauter contract.** The
decode/normalize step carries a negative-spec docstring stating explicitly
what it does *not* do — it does not special-case N==1, and it does not accept
the stripped EM-facing suffix as engine-authored text — pinned against the
`claude-klabauter` contract this hook is a client of, per
`docs/wiki/rag-bait-conventions.md` § negative-spec blocks.

## `session-reachability-cli` / `artifact_owner` — what may be cited, and what it answers

<!-- distill-run: 2026-08-14; C1 epistemic-premise gate. Measured, not inferred. -->
**Doctrine may not cite a bare `session-reachability-cli` command line as resolving on a
fresh install.** Name the capability instead. The CLI landed in `claude-klabauter` at
`2b8a3bdb606d` but is absent from that repo's `docs/install/bin-inventory.json` — the
tracked baseline gating which oracles get forwarders written into
`$COORDINATOR_SETTINGS_HOME/bin` — so a fresh-install reader typing the bareword gets
`command not found`. The whole derive/write chain lives in claude-klabauter; this repo has no local
trigger. Neighbouring `session-liveness-cli` resolves precisely because it *has* an
inventory entry. **Owed by claude-klabauter, not doable here:** the inventory entry plus a re-run of
the install/substrate write step. Recheck disk before trusting it is still absent.

**`artifact_owner` subsumes one of the three `pickup/SKILL.md:189-193` liveness
heuristics, not all three.** Exercised live on a claimed DoE plan and on an absolute
cross-repo claude-klabauter handoff path; both resolved, returning per-owner
`reachable`/`not_reachable` rather than failing on the cross-repo pointer:

```
$ python3 coordinator/bin/session-reachability-cli.py artifact-owner <plan-or-handoff-path>
{"artifact_path": "...", "owners": [{"session_id": "0269582a-…",
 "source_field": "agent_sessions", "outcome": "reachable",
 "address": "doe-claude-ee [5950ee]", "claim_live": null, "claim_stage": null}],
 "file_error": null}
```

It answers **"a live claim resolving true"** — extracting `claimed_by` /
`agent_sessions` / `authoring_session` owners and each one's reachability. It does not
compute **"an active reference"** or **"a very recent chunk-commit with no closure"**:
neither is an owner-extraction question, and `resolve_artifact_owner` is scoped by its own
docstring to owner-id extraction plus reachability. `claim_live`/`claim_stage` populate
only for the `claim_dir` source field. So the other two heuristics stay standing — folding
all three into one `artifact_owner` call would claim more than the op does.

## Gotchas — auto-fire validation and the skill-tool invocation trap

<!-- distill-run: 2026-08-06-14h38; nugget: c7-001 -->
**Per-session hook-reload semantics can produce a false negative on `UserPromptExpansion`
auto-fire.** When validating that `/coordinator:pickup`'s AC1 auto-fire path fires on the
production path, a hook-reload boundary tied to session lifetime (not to the hook file's own
edit timestamp) caused an earlier validation pass to read as a failure when the underlying
wiring was correct — the stale reading came from testing against a session that had not
picked up the current hook definition, not from a real regression. Re-test AC1-style
auto-fire claims in a fresh session before trusting a negative result.

**Invoking a skill via the Skill tool does NOT fire `UserPromptExpansion`.** The
`UserPromptExpansion` hook is keyed to the literal user-typed prompt path, not to any
downstream tool invocation that happens to route through the same skill body. A dispatched
or programmatic Skill-tool call bypasses the hook entirely — this is not a bug to work
around but the reason `pickup`'s fallback invocation must go through `pickup/SKILL.md`
directly (its prose entrypoint) rather than assuming Skill-tool dispatch will trigger the
same auto-fire machinery as a typed `/coordinator:pickup` prompt.

Spec backlink: `2026-07-23-computed-skills-bz-pickup-rebuild-e9a989.md`.
