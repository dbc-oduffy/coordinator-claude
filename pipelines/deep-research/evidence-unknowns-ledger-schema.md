# Evidence and unknowns ledger schema

**Status: FROZEN.** This document defines no record shape of its own: it is a mapping of the
epistemic fields a deep-research claim carries beside its `confidence` enum onto the project-rag
unknown-revision v1 contract. The contract owns the names and vocabularies, the coordinator maps its
claim concepts onto them, and the ledger writer's owner (the `rea-ask-1` peer) owns what is emitted.
Validator: `fixtures/validate-code-comparison-record.py` (checks in
`fixtures/.validate-code-comparison-record-checker.py`).

## Sources and ownership

- The contract: `project-rag:contracts/unknown-revision/v1/schema.json` and `vectors.json`, at
  project-rag `1fd7164e7c`. It owns the field set, digest canonicalisation, chain rule and closed
  vocabularies. A disagreement between this document and the contract is fixed toward the contract.
- The vendored copy: `fixtures/unknown-revision-v1-vectors.json` is copied from the contract's
  `vectors.json` at `1fd7164e7c` (the source of the copy; byte identity is not enforced here). Its
  `canonical_json` strings and digests are the parity oracle for `valid`, `observed_at_variants` and
  `chains`; the `refusal` vector is consumed here only as a canonicalisation check, and the import
  refusal itself belongs to the writer (rea-ask-1).
- `rea-ask-9`: the route that produced the mapping. The reply says the epistemology-engine owner
  owns the shape. The coordinator keeps its claim fields (`confidence` stays its own) and maps the
  epistemic concepts onto the contract's names.
- `rea-ask-1`: the scripted evidence writer and its choke point. The reply confirms the writer's
  owner owns record emission, canonical import and the choke point, and emits the ask 9 shape.
- Names and values below are never edited here without the owning decision.

## Writer wording

"Script is the only writer" is a conditional design claim, never a present fact: until ask 1's op
lands, the pipeline's `*-claims.json` stays agent-written. Assert no only-writer guarantee.

## Mapping table

Every name in the Field column is the contract's (`schema.json` at `1fd7164e7c`), reached through
the ask 9 reply.

| Claim concept | Field | Values | Attribution |
|---|---|---|---|
| Source standing (what kind of source backs the claim) | `source_authority` | `shipped-artifact`, `controlled-replay`, `historical-reference`, `external-service`, `analyst-inference` | contract `source_authority` enum. Never `authority`: the owner reserves that word for a principal's domain authority. |
| Observation kind (how the fact was obtained) | `epistemic_mode` | `observed`, `derived`, `inferred` | contract `epistemic_mode` enum. Derived from the owner's provenance (raw, parsed: observed; rolled_up, computed: derived; synthesized: inferred). |
| Coverage-unknown marker | `coverage` | `complete`, `partial`, `unknown` | contract `coverage` enum. `unknown` means not looked at, never "looked and found nothing". |
| What the marker is about | `coverage_scope` | `claim`, `section`, `output` | contract `coverage_scope` enum. |
| Unknown record, contiguous revisions | `unknown_revisions[]`: `unknown_id`, `revision` (int >= 1), `previous_revision_digest` (null iff revision 1), `question`, `coverage`, `coverage_scope`, `epistemic_mode`, `source_authority`, `observed_at` | as above | contract `UnknownRevision` (`schema.json`; digest rule in `vectors.json` `canonicalisation`). `revision`, `previous_revision_digest` and `revision_digest` are the chain; the digest is `sha256:<hex>` over the sorted-key compact UTF-8 JSON of the nine fields as emitted (`observed_at` is not normalised). |
| Agent belief in an observation | `confidence` | `HIGH`, `MEDIUM`, `LOW` | The coordinator's own, unchanged (`code-comparison-record-schema.md` rule 5). Not mapped. |

All epistemic fields are siblings of `confidence`, additive, and optional on an existing record.
`epistemic_mode` never reuses the name `confidence`, and its `inferred` value is distinct from the
`analyst-inference` value of `source_authority`: one says how a fact was obtained, the other what
kind of source stands behind it. Tripwire: `A-SIBLING-FIELDS-NEVER-REUSE-CONFIDENCE`.

## Validator rules

- A record carrying any of `source_authority`, `epistemic_mode`, `coverage`, `coverage_scope`,
  `unknown_revisions` must carry both `coverage` and `coverage_scope`.
- Each carried vocabulary field takes a value from its closed set; a top-level `authority` is rejected.
- Each `unknown_revisions` entry has exactly the nine keys, a timezone-aware `observed_at`, and
  revision 1 carries no `previous_revision_digest`.
- Per `unknown_id`, revisions are contiguous from 1 and each `previous_revision_digest` equals the
  recomputed digest of the revision before it; a tampered, reordered or gapped chain fails.
- The `confidence` enum check is unchanged.

## The four Contested questions

**1. Sibling fields or replacing `confidence`?** Sibling fields. `confidence` is an agent-emitted
enum (`HIGH | MEDIUM | LOW`) that live deep-research runs and `test_code_comparison_record_shape.py`
read; replacing it breaks both for no gain, because it rates the agent's belief in an observation
while the new fields rate provenance and completeness.

**2. Where do unknowns live?** A separate ledger beside the claims file, not inside
`*-claims.json`: unknowns are revised under a digest chain, and a chained record cannot sit in a
file the specialist rewrites wholesale each pass without losing contiguity; a separate ledger also
lets the scripted writer own it alone. The ledger is a sequence of `unknown_revisions` entries; the
validator checks that sequence where a record carries it.

**3. What does the coverage marker attach to?** The claim as the finest level (`coverage_scope:
claim`), rolled up to a synthesis section (`section`) or a whole specialist output (`output`). A
claim-level marker is the only form that stops one claim implying completeness; the roll-ups let
the degraded mode record a skipped stage as unknown. The marker is required whenever any epistemic
field is present.

**4. How is "script is the only writer" worded before ask 1 lands?** As the conditional claim in
Writer wording above, never a present fact.
