# Integration Test At the Schema Boundary

**Provenance:** 2026-05-13, `example-game-workbench-repo` — MCP tool registration drift.

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

## Cross-References

- [`round-trip-contract-tests`](./round-trip-contract-tests.md) — sister rule for producer → on-disk-artifact → consumer pipelines. The schema-boundary rule is the RPC/tool analogue of the on-disk contract test.
- [`test-design-discipline`](./test-design-discipline.md) — broader test-shape guidance, including the "green unit tests aren't runtime readiness" line that this rule sharpens for the registration-vs-handler split.
