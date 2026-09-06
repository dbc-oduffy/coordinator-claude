# Integration Test At the Schema Boundary

**Provenance:** `example-game-workbench-repo` — MCP tool registration drift.

For any tool/RPC/endpoint where **registration** and **handler** are separate code paths, the integration test must exercise the wire end-to-end. Unit tests against the handler alone bypass the seam where the bug lives.

## The Failure Shape

MCP tool registration has two orthogonal surfaces:

1. **Registration / published schema** — the tool name, input shape, and description advertised to the client.
2. **Handler routing** — the server-side dispatch from incoming request to the function that does the work.

Both can be green individually while the wire is broken. The client sends a request matching schema V1; the server routes to handler V2; the request errors silently or succeeds with wrong semantics. A unit test that imports the handler and calls it with hand-built inputs proves the handler works in isolation — nothing about whether *that handler* is what the client actually reaches.

The shape generalises to any advertise-then-dispatch split: gRPC service registration vs. method impl, OpenAPI spec vs. route handler, plugin manifest vs. callback.

## The Rule

For any tool/RPC/endpoint with separate registration and handler surfaces, **at least one test must**:

1. Serialize a request matching the **published schema** (as the client would see it).
2. Dispatch it through the **real registration/routing layer** (no test-only shortcut wiring).
3. Hit the **real handler**.
4. Deserialize the response and assert on it.

The integration test sits at the **schema boundary**, not the handler boundary. If the test imports the handler directly, it has skipped the seam it was supposed to cover. Add when a new tool/endpoint lands — defer and a downstream consumer hits the bug first.

## Where This Surfaces

- **MCP tool servers** — `@tool` registration vs. handler dispatch table drift.
- **gRPC / Connect** — generated stub registration vs. method impl signature drift.
- **OpenAPI / FastAPI / Express** — route decorator path/method vs. handler param shape.
- **Plugin manifests** — declared command name vs. exported callback.
- **Message bus consumers** — topic subscription vs. consumer schema-version expectation.

Diagnostic when something breaks: client-side error mentions a field the server log never sees, or handler logs an arg shape the client claims it never sent. Both sides "look right" because each was tested against its own fabricated counterpart.

## YAML Implicit Typing Is a Schema-Boundary Trap — Quote Scalars or the Loader Types Them Before the Validator Sees a String

A distinct advertise-vs-parse seam lives between a YAML frontmatter loader and a JSON-Schema validator. **PyYAML (YAML 1.1 implicit typing) coerces unquoted scalars before the schema ever sees them** — an ISO date `created: 2026-06-26` becomes a `datetime.date`, an all-digit run `commits: [44605404]` becomes an `int`, `version: 1.0` becomes a `float`, `enabled: yes` becomes a `bool`. A JSON-Schema field declared `{type: string, format: date}` then fails on EVERY artifact with `"... is not of type 'string'"`, because the loader typed the value out of `str` before validation ran.

**Rule:** when validating YAML frontmatter against a string-typed JSON Schema, either (a) quote the scalar in the source (`created: "2026-06-26"`), (b) load with a loader/typing discipline that preserves strings for the affected keys, or (c) coerce known-string fields back to `str` between load and validate. This is the same registration-vs-handler shape as the rest of this wiki: the producer (the YAML author) and the consumer (the JSON-Schema validator) disagree about the type at the boundary, and each looks right in isolation. Test it end-to-end — load a real frontmatter block through the real loader and run the real schema — never assert the schema against a hand-built Python dict where the strings are already strings (that fabricates the counterpart and hides the coercion).

*Source: 2026-06, frontmatter-schema validation.*

## The In-Repo Validator Is a Keyword Subset — an Unimplemented Keyword Silently Under-Validates at the Write-Time Hook

A third advertise-vs-enforce seam lives between a JSON Schema and the **in-repo validator that the write-time hook actually runs**. `coordinator/bin/lib/schema.js` implements only a *subset* of JSON Schema keywords. When a schema reaches for a keyword `schema.js` doesn't handle, the constraint is not enforced — it is silently *skipped*, and the instance PASSES. Concretely: `strategic-self-description.schema.json` used `oneOf`+`const` to build the DEC-5 CTA security boundary; `schema.js` had no `oneOf`/`const` handling, so the frontmatter hook (`validate-frontmatter-schema.js`, which validates via `schema.js`) PASSED a malformed-CTA instance that an external `jsonschema` `Draft202012Validator` correctly REJECTED. The security boundary was unenforced on write — a false green.

**Rule:** an external-validator PASS is *not* evidence the in-repo hook enforces the same constraint. The producer here is the schema author (reaching for an expressive keyword); the consumer is the runtime hook's cut-down validator — and they disagree about which keywords are load-bearing. When a schema uses any keyword beyond the primitive `type`/`required`/`properties` core — `oneOf`, `allOf`, `anyOf`, `const`, `if/then`, `pattern`, `format`, `additionalProperties` — confirm `schema.js` implements it before trusting the write-time hook to enforce it; otherwise the boundary must be enforced by a code check, not by the schema alone. Test end-to-end through the **real hook's validator**, never against an external validator that implements a richer keyword set than the one the hook actually runs.

*Source: strategic-self-description schema.*

## Handoff/Spinoff Lineage Is a Write-Time Schema Boundary — Reachability and Scope Must Be Validated Where the Baton Is Written, Not Discovered Later

The handoff/spinoff continuity backbone has the same advertise-vs-enforce shape as a schema
validator: a handoff/spinoff document *declares* a lineage pointer (predecessor, origin,
`shipped_in`), and the continuity graph *consumes* that pointer later to reconstruct history.
If the write-time check only validates document shape (fields present, types correct) and not
**lineage reachability**, a document can pass validation while pointing at a target that never
existed or has since gone out of scope — a false green identical in kind to a schema that
validates syntax but not semantics.

**Rule:** validate lineage reachability **at write time**, git-history-aware, across both
`state/` and `archive/` locations (a handoff can reference either), and across the batch-sweep
path as well as the single-write path — not just the common case. Two enforcement postures:

- **Deny-always** for a target that is provably never-existed (no commit ever created it) — this
  is a hard reject, not a warning.
- **Carve-out** for legitimate foreign-baton references (same-repo-only) — a lineage pointer
  crossing repo boundaries is out of scope for this reachability check and must not be silently
  accepted as if it were validated.

A lineage/continuity-graph corruption discovered sessions later, once other work has built on
the bad pointer, is strictly more expensive to unwind than a write-time rejection. Treat lineage
reachability as load-bearing as the document schema itself, and test it end-to-end against the
real write-time hook — not a hand-built graph where the reachable/unreachable cases are already
known-good.

### Scoping-Keyword Holes Are the Same Failure Shape, One Level Down

Even with reachability enforced, a narrower version of the same gap can persist in the
**scoping keywords** that qualify a lineage pointer: `shipped_in`, `origin_*` fields, and
pattern-keyword scoping used to bound which lineage entries a given handoff is allowed to claim.
If the write-time validator checks that these fields are *present and well-typed* but not that
their *values are consistent with the declared scope*, a document can silently absorb lineage
that belongs to a different scope — the corruption is smaller in surface area than a fully
unreachable target, but identical in mechanism: the schema/consumer boundary trusts a value the
producer was never actually constrained to get right. Close scoping-keyword holes with the same
discipline as the primitive type/required checks — don't treat "the keyword exists" as a proxy
for "the keyword's value is in scope."

*Source: coordinator handoff/spinoff continuity hardening.*

## Cross-References

- [`round-trip-contract-tests`](./round-trip-contract-tests.md) — sister rule for producer → on-disk-artifact → consumer pipelines. The schema-boundary rule is the RPC/tool analogue of the on-disk contract test.
- [`test-design-discipline`](./test-design-discipline.md) — broader test-shape guidance, including the "green unit tests aren't runtime readiness" line that this rule sharpens for the registration-vs-handler split.
