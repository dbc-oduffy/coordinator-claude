---
title: "plan_tasks.mutate — coordinator-plane contract for the example-orchestration-hub mutation CLI"
provenance: "docs/plans/2026-07-09-pcli-01-plan-mutation-cli-contract.md § C1"
---

# `plan_tasks.mutate` — the Tier-1 typed writer for the `## Tasks` plan-spine

> Spec backlink: `docs/plans/2026-07-09-pcli-01-plan-mutation-cli-contract.md § Contract pinned by this plan`
> Source of the pinned decisions: `cross-repo/inbox/2026-07-09-example-orchestration-hub-repo-em-pcli-example-orchestration-hub-engines-consult-reply.md`

## What this contract is

`plan_tasks.mutate` is a **example-orchestration-hub-owned engine** (op module, `body_blocks.py` fenced-block
locator, `locked_rmw` wiring — all on example-orchestration-hub's plane, out of scope for this wiki) that
mutates the `## Tasks` machine-parseable plan-spine — the single ` ```yaml plan-tasks ` fenced
block that lives directly under a plan's `## Tasks` heading, schema
`coordinator/schemas/plan-tasks.schema.json` (shipped `475fa53b`). This wiki is the
**coordinator-plane half** of the contract: the verb surface, invocation shape, and
error-envelope semantics that coordinator-side callers author against — frozen here so that
downstream stubs can build in parallel against a stable shape while the example-orchestration-hub engine itself
is still being built.

**Who consumes this contract:**

- **pcli-02** (read-path) — reads spine state the CLI mutates.
- **pcli-04** (Workflow-sidecar emitter) — a future generator over the same spine. Also gated on
  a second, separate DoE contract deliverable — contract-ask #2, a per-task `writes:`/`reads:`
  spine field (per the same consult reply, Q3) — which lives outside this need-1 wiki's scope.
  <!-- Review: code-reviewer — pcli-04 is named as a consumer but the wiki never mentioned the sibling gating contract-ask #2; one-line forward pointer added, full section stays out of scope here. -->
- **pcli-05** (review-integrator scalpel) — re-checks-before-applies against the CLI's
  predictable `MutateAbort` error shape.
- **pcli-07** (DX prose) — documents the CLI for human/agent operators.
- **example-orchestration-hub's engine build** — this wiki is the frozen interface example-orchestration-hub builds the op module
  against; it does not specify example-orchestration-hub internals (see § Suggested mirror shapes, need-not-mandate).

Today, the `## Tasks` spine is mutated **only** by free-form `Edit`/`Write` at the Tier-2 prose
seam (`canonical-artifact-shapes.md` § Warn-Not-Block) — every skill that stamps PM-approval,
defers a row, or adds a task hand-edits YAML by eye: no atomic RMW, no post-mutation schema
validation, no idempotency guard, and a real torn-write hazard under concurrent EM sessions on
the shared `work/*` branch. `plan_tasks.mutate` is the typed answer to that hazard — see
§ Tier posture below for how it coexists with (never replaces) the existing hand-edit path.

## The five verbs

`plan_tasks.mutate` is **one op, multi-verb** — a single entrypoint that dispatches on a
`verb` field in its params. All five verbs operate on the spine block of a single named plan.

| Verb | Form | Semantics |
|---|---|---|
| `stamp` | `stamp --pm-approved <id[,id,...]>` | Set `pm_approved: true` on the named row(s). **Multi-id is ONE atomic `locked_rmw` transaction** — not N separate transactions. The engine validates that all N ids exist *before* mutating any of them; if any id is absent, the whole transaction aborts and no row is touched. This exists specifically to prevent a torn partial-stamp: N separate transactions would reintroduce the exact interleaving hazard the CLI exists to remove. |
| `set` | `set <id> <field> <value>` | Set an arbitrary schema-valid field/value on one row. Post-mutation, the engine re-validates the mutated row against `plan-tasks.schema.json`; an unknown field name or an invalid enum value is a **fail-loud abort** — the mutation does not land, and the caller receives the failure envelope (§ Error-envelope contract). |
| `defer` | `defer <id>` | Set `deferred: true` on the row. Deferral is not approval — a deferred row that later gets ratified still needs its own `stamp --pm-approved` call. `defer` never implies PM sign-off. |
| `undefer` | `undefer <id>` | Set `deferred: false` on the row — the inverse of `defer`. |
| `add-task` | `add-task <yaml-fragment>` | Append a new row to the spine. **Duplicate `id` is a fail-loud error, not a silent no-op** — this mirrors `memo_transition`'s dup-key guard (example-orchestration-hub-repo's existing pattern for rejecting a second write under an already-occupied key rather than quietly treating it as a successful re-application). Enforced via post-mutation validation against the vendored `plan-tasks.schema.json`; the id-collision is what gates the write via `MutateAbort`. |

These five verbs are the **entire** pinned surface for this contract. No verb here implies a
sixth (e.g. `remove-task`) exists or is planned — see § Pinned decisions vs open questions.

## Invocation shape

```
python -m coordinator_core.invoke plan_tasks.mutate '<params-json>' --repo <path>
```

This is **EXPECTED** to ride the generic op-dispatch entrypoint `invoke/__main__.py` — the same
entrypoint `handoff.transition` rides — contingent on the op-registry-op-vs-standalone-script
question resolving toward a registered op (see § Pinned decisions vs open questions, where that
question is GENUINELY OPEN, not settled here). `<params-json>` carries the verb and its
arguments (the exact param-object shape is example-orchestration-hub's internal detail — not pinned by this
contract; callers construct it per the verb table above and consume only the two envelope
shapes below). **Downstream consumers (pcli-02, pcli-04) must not hard-code the
`invoke/__main__.py` invocation path as pinned** until that open question resolves.
<!-- Review: code-reviewer — invocation-shape stated riding invoke/__main__.py as settled fact while § Pinned decisions lists the underlying registry-vs-standalone question as genuinely open; softened + cross-referenced to avoid downstream over-commitment. -->


## Error-envelope contract

**CONFIRMED against example-orchestration-hub's shipped `handoff_transition.py`** (`coordinator_core/ops/handoff_transition.py`, success reply at line 99, failure reply at line 104) — this is not inferred from doctrine, it is read from the sibling repo's source. This envelope shape is **pinned by mirroring** `handoff_transition.py`'s shipped shape, NOT independently confirmed against `plan_tasks.mutate` itself — `plan_tasks.mutate` does not exist yet (see § Call-sites). The envelope has **TWO distinct shapes**, not one uniform shape:
<!-- Review: code-reviewer — a skim-reader of the header could mistake "CONFIRMED" as confirmed against plan_tasks.mutate itself; the confirmation is against handoff_transition.py, mirrored here. -->


**Success:**

```json
{"exit_code": 0, "applied": true, "message": "<human-readable text>"}
```

**Failure:**

```json
{"exit_code": 1, "applied": false, "error": "<human-readable text>"}
```

**The failure shape carries its human-readable text under the `error` key, NOT `message`.**
This is the single most important gotcha in the contract — a caller that reads `message`
unconditionally will get `None`/`KeyError` on every failure path.

**Coordinator callers gate on `exit_code == 0 && applied == true`.** Any non-zero exit is a
hard error the caller must surface, never swallow — read the human-readable text from `error`
on that path, from `message` on the success path. Idempotency and validation aborts
(`MutateAbort` — the unknown-field/invalid-enum abort on `set`, the dup-id abort on
`add-task`, the any-id-absent abort on multi-id `stamp`) all surface as non-zero exits with a
descriptive `error` message. This predictability is load-bearing for pcli-05's
review-integrator scalpel, which re-checks-before-applies against the specific error text
rather than treating every failure as an opaque bail-out.

## Tier posture (LOAD-BEARING)

`plan_tasks.mutate` is a **Tier-1 typed seam that sits ALONGSIDE** the existing Tier-2
warn-only hand-edit path documented in
`coordinator/docs/wiki/canonical-artifact-shapes.md § Warn-Not-Block Enforcement Posture`. It
is an **additional, stricter** writer — never a replacement gate.

**Hand-edits to `## Tasks` remain valid and warn-only.** The Tier-2 `validate-frontmatter-schema.js`
hook still governs free-form `Write`/`Edit`/`MultiEdit` on the spine: default WARN
(`additionalContext`, never `permissionDecision: deny`), the write proceeds, the agent sees the
gripe. `plan_tasks.mutate` does not change that behavior for hand-edits, and it does not
supersede it. **No future EM may treat hand-edits to the spine as blocked or deprecated on the
strength of this CLI existing.** The CLI is a better tool for the specific case of atomic
multi-row mutation under concurrency (stamping, deferring, appending) — it is not a policy
change to the enforcement posture of the artifact. This instantiates
`canonical-artifact-shapes.md`'s two-tier model on a new artifact; it does not introduce a new
posture.

## Contract-ask #1 — schema vendoring + drift-gate (a DoE-owned deliverable)

This is a **concrete DoE deliverable spec**, not a example-orchestration-hub ask. example-orchestration-hub's consult reply pins the
decision: example-orchestration-hub vendors `plan-tasks.schema.json` into its own tree at
`coordinator_core/frontmatter/schemas/plan-tasks.schema.json`, mirroring how
`handoff.schema.json` is already vendored at the same path for `handoff_transition.py`.
Rationale (from the reply): `plan_tasks.mutate` sits on example-orchestration-hub's sub-10ms / zero-spawn hot-path
SLA, so shelling out to DoE's `schema-cli.js` per-invocation is disallowed — vendoring avoids
the cross-process call. **DoE stays the schema's author/owner** — the SSOT copy remains
`coordinator/schemas/plan-tasks.schema.json` in this repo; example-orchestration-hub carries a versioned vendored
copy behind a drift/parity gate, the same model that already keeps `handoff.schema.json` honest.

**The drift-gate mechanism is BOTH legs of `cross-repo-contract-parity.md § Convention B`**
(cited by name — this is a direct instantiation of that convention, not a new one):

1. **Faithfulness leg.** example-orchestration-hub's producer-side parity test asserts the vendored bytes equal
   the pinned DoE snapshot — the same shape as `test_embed_constant_parity` in Convention B's
   worked example: import/read both copies, assert equality, fail red the instant one side
   moves without the other.
2. **Freshness leg — degrades to advisory.** DoE-claude is `source_is_live`
   (`coordinator-claude` over `~/.claude`, no released tag example-orchestration-hub can pin against or
   mechanically detect drift from) — per Convention B, this means the freshness leg cannot run
   mechanically; it degrades to advisory. The compensating control is a **bump-memo
   obligation**: `coordinator/schemas/plan-tasks.schema.json` carries a RAG-bait header note at
   its structural boundary naming example-orchestration-hub as the downstream vendor, and the rule that **any
   breaking change to this schema owes a bump-memo to the example-orchestration-hub EM (PM-relayed)** — the manual
   signal substituting for the freshness test the vendor side cannot run. This is the same
   pattern Convention B documents for every other `source_is_live` producer relationship in
   this system; it is not a bespoke exception invented for this schema.

## Pinned decisions vs open questions

**PINNED — do not re-litigate these** (source: the consult reply):

- `add-task` duplicate-id is a fail-loud error, never a silent no-op.
- Multi-id `stamp` is one atomic `locked_rmw` transaction, never N separate transactions.
- Schema vendoring (example-orchestration-hub vendors `plan-tasks.schema.json`, DoE stays author/owner) — see
  § Contract-ask #1 above.

**RESOLVED — greenfield, on the DoE side** (not a example-orchestration-hub question, decided by grep):
parser-reuse-vs-greenfield for example-orchestration-hub's `body_blocks.py` fenced-block locator. A grep of
`coordinator/bin/lib/*.js` in this repo found **no portable JS body-block parser to port** —
DoE's own frontmatter tooling has nothing that locates a fenced block by heading-then-fence
adjacency in a reusable form. Separately, the consult reply confirms `frontmatter/primitives.py`
on example-orchestration-hub's side is `---`-delimiter-only (`split_frontmatter`/`rebuild` bound the frontmatter
block and treat everything after the closing `---` as opaque body) — there is no existing body
parser to extend either. Net: example-orchestration-hub builds `body_blocks.py` **greenfield**. This is resolved,
not open — it is not carried to example-orchestration-hub as a decision to make.

**GENUINELY OPEN — for example-orchestration-hub to decide, not EM-resolved here:** op-registry-op vs
standalone-script — whether `plan_tasks.mutate` is registered as an op on example-orchestration-hub's existing
op-dispatch registry (the same registry `handoff.transition` lives on) or shipped as a
standalone script outside that registry. This is example-orchestration-hub's internal architecture call; this
contract does not take a position on it, and no EM on the DoE side should silently resolve it.
If it later needs resolving jointly, that is a follow-up consult, not a default assumed here.

## Call-sites (coordinator-side consumers — named and specified, NOT wired)

None of the following are currently wired to `plan_tasks.mutate`. They are named here so
downstream stubs and future EMs know where the CLI attaches once both it and its prerequisites
land — treating any of them as already-integrated is a plan-authoring error.

1. **`execute-plan` Phase 1.6 stamp/derive** — the primary future consumer. Phase 1.6
   (Dispatch Ledger / `## Tasks` spine derivation) today hand-edits the spine to stamp
   PM-approval and derive dispatch rows. Once wired, this becomes the CLI's first real
   call-site. **NOT-YET-WIRED** — gated on BOTH (a) the foundations plan's ledger-derivation
   chunk (pending) and (b) the example-orchestration-hub `plan_tasks.mutate` engine itself (pending, per this
   wiki). Neither prerequisite has shipped as of this writing; do not wire a live invocation
   against this call-site until both land.
2. **A future `stamp --pm-approved` ceremony action.** Any PM-approval ceremony (interactive or
   scripted) that currently asks an EM to hand-edit `pm_approved: true` on one or more rows is a
   candidate to route through `stamp --pm-approved <id[,id,...]>` once the CLI ships, gaining
   the atomic multi-id guarantee for free.
3. **Any skill currently free-form-editing `## Tasks`.** Every skill that today performs an
   `Edit`/`Write` against the spine block (deferral, task addition, field updates) is a latent
   call-site — each such skill is a future candidate for migration to the typed verb that
   matches its current hand-edit, without losing the Tier-2 hand-edit fallback (§ Tier posture).

## Suggested mirror shapes (need-not-mandate)

`handoff_transition.py` (`coordinator_core/ops/handoff_transition.py`) and `locked_write.py`
(`coordinator_core/locked_write.py`) in example-orchestration-hub-repo are the **suggested** shape
`plan_tasks.mutate` extends — the resolve → mutate-closure → post-mutation schema-validate →
`locked_rmw` → error-envelope pipeline, with the vendored-schema gate on the abort path. This
wiki cites them as a mirror, not a requirement: the module paths, class names, and internal
API surface of `body_blocks.py` and the op module are example-orchestration-hub's plane to design. This contract
pins only the verb surface, invocation shape, and error envelope — the "how" inside example-orchestration-hub's
engine is out of scope here.

## Companion doctrine — the shared parser-locate invariant

`coordinator/docs/wiki/writing-plans.md § Machine-Parseable Task Spine` is the DoE-side
companion doctrine to example-orchestration-hub's `body_blocks.py` fenced-block locator — both repos document the
**same parser-locate invariant**: exactly one fenced code block with info-string
` ```yaml plan-tasks ` directly under the `## Tasks` heading; zero blocks or more than one is a
defined error. `writing-plans.md` documents this from the authoring side (how an EM writes a
compliant spine, what `plan-coverage-checker` and the deferred-harvest CLI each do on a
zero/multi-block violation); `body_blocks.py` will enforce the same locate-rule from the
mutation side. Citing both closes the loop between the two documentation surfaces — a reader
who lands on either doc should be pointed at the other.

## Negative-spec

- **Do not** treat this CLI as replacing or deprecating Tier-2 hand-edits — see § Tier posture.
- **Do not** wire the `execute-plan` Phase 1.6 call-site as if its prerequisites have shipped —
  see § Call-sites item 1.
- **Do not** silently resolve op-registry-op-vs-standalone-script as an EM default — see
  § Pinned decisions vs open questions.
- **Do not** read `message` on the failure envelope path — the failure shape's text is under
  `error` (§ Error-envelope contract).
- **Do not** treat `plan_tasks.mutate` as callable — no example-orchestration-hub engine build has landed as of
  this writing; see § Call-sites for wiring prerequisites.
  <!-- Review: code-reviewer — the body repeatedly warns the CLI doesn't exist yet ("NOT-YET-WIRED", etc.); promoting one instance to negative-spec centralizes the warning for a skimming reader. -->
