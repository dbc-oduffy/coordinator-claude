<!-- RAG-bait: diagnosing an MCP/LLM tool that rejects every call with a "<field> is required" /
     "regardless of format" error — distinguishing a schema-declaration gap from a handler bug.
     Negative-spec: this is NOT about async-handler blocking (see mcp-async-handler-discipline.md)
     nor about runtime instructions= self-declaration (see project-rag-mcp-self-declaration.md). -->

# Tool Schema-Gap Debugging — "`<field>` is required regardless of format"

When an MCP (or any LLM-facing) tool rejects **every** call with `"<field> is required"` — and the caller has tried the field in every plausible shape (string, object, nested, omitted) and still gets the same rejection — the bug is almost never in the handler body. It is a **schema-declaration gap**: the tool's input schema does not declare the field the way the runtime validates it, so the validation layer rejects the call before the handler ever runs.

## The diagnostic tell

The user phrase **"regardless of format"** (or "no matter how I pass it", "I've tried everything") is the signal. It means the caller has already varied the *value shape* and the error is invariant — which rules out a value-parsing bug in the handler and points at the *schema contract* one layer up. A handler bug would change behavior as the input shape changes; a schema-validation rejection does not.

## Where to look

1. **The declared input schema**, not the handler. For FastMCP / JSON-schema-backed tools: is the field in `properties`? Is it listed in `required` when it should be optional (or vice-versa)? Is the type a mismatch (`object` declared, `string` sent)?
2. **Schema-vs-handler drift.** The handler may read `params["foo"]` while the schema declares `bar` — the validator enforces the schema name, so a correctly-shaped call for the *handler* fails the *schema*.
3. **Wrapper/decorator introspection.** A `lambda`/partial wrapper or a decorator that re-derives the schema from a signature can drop or rename fields silently — the registered schema diverges from what the handler expects.

## Rule

Treat an invariant `"<field> is required"` across input shapes as a **contract bug at the schema boundary**, not a handler bug — fix the schema declaration (add the field, correct its `required`/type, or align the name with the handler), then re-test. Reaching for handler-side input-coercion first is the wasted-cycle anti-pattern this tell exists to short-circuit.

## Cross-references

- `mcp-async-handler-discipline.md` — a different MCP-author failure (sync I/O blocking the event loop).
- `project-rag-mcp-self-declaration.md` — runtime `instructions=` / self-declaration doctrine.

Source: 2026-06-02 (example-game-workbench-repo).
