# Round-Trip Contract Tests

**Provenance:** consolidated 2026-05-05 from `tasks/lesson-triage-2026-05-05/SYNTHESIS.md` §B5.

When a pipeline has separate producers and consumers writing/reading the same on-disk artifact, **at least one test must run the real producer feeding the real consumer**. Tests that fabricate the schema inline on each side hide drift indefinitely.

## The Failure Mode

A RAG indexer's lite/clang producers wrote a `symbols` table without `module` / `line_end` / `decl_text` columns; consumers (`cpp_chunker`, `extractor.extract_cpp`, `live.py`) queried those columns. CI passed because every consumer test built its own rich-schema fixture inline. The mismatch only surfaced when a game project ran a clean reindex — the first time the in-tree producers' real DDL met the real consumers' real SQL.

The shape recurs:

- A 2,091-LOC ported producer script's `INSERT` statements were silently rolled back in a worker exception handler because A2 enrichment dropped columns the script still wrote — yielding 0 symbols across every clang TU.
- A FastAPI `.venv` lacking `fastapi`/`uvicorn`/`pip` survived 379 unit tests because tests imported submodules directly; the gap surfaced only when something tried to start the runtime over HTTP.

The common cause: tests prove the parts work in isolation. They don't prove the parts wire together at the seams the runtime actually exercises.

## The Rule

For any producer → on-disk-artifact → consumer pipeline:

1. Write a contract test that runs the **real producer** end-to-end.
2. Open the producer's emitted artifact and assert its schema matches what every consumer queries.
3. Run **≥1 consumer end-to-end** against that producer's output.

Add the test when a new producer or consumer lands. Don't defer to "we'll add it when we hit a bug" — by then the bug has shipped to a downstream consumer.

## Port-Time DDL Floor

When porting a producer script that writes via hardcoded `INSERT`s, the receiving DDL must include every column and every table the script touches — even if no consumer reads them today.

Drop columns ONLY by editing the script's `INSERT`s in the same chunk. Otherwise the column survives the "drop" decision because the script still writes to it, the DDL doesn't have it, and every write rolls back.

The minimalist read-side analysis ("no consumer reads this") is correct in isolation but wrong as a port-time decision. **Port-time DDL = grep the script for every `INSERT` and `CREATE TABLE`. That's the floor.** Schema minimalism comes later, after a consumer actually reads (or fails to read) a column, and always co-edits the writer in the same change.

## HTTP Apps: Smoke-Test the Boot Path

For any FastAPI/uvicorn-shaped service, include at least one smoke test that does:

```python
from <pkg>.app import app
# optionally:
TestClient(app).get("/health")
```

This proves the app at least imports and the boot path is reachable. Tests that exercise registry/lock/lease internals via direct submodule imports can pass while the top-level `from fastapi import ...` in `app.py` would fail (e.g. fastapi missing from the venv). Cheap to add, immediate signal on environment drift.

## Where the Test Lives

- **Producer-side test directory** if the producer owns the schema authoritatively.
- **Consumer-side test directory** if the consumer's read shape is what's drifting.
- **Either** is fine — the rule is that *one* such test must exist on the contract, not that it must live in a specific place. What's not fine is fabricated-on-each-side fixtures with no integration seam.

## Spike Acceptance: Registration Is Not Initialization

> See `docs/wiki/writing-plans.md` § "Spike Pass-Conditions Must Match the Wire Path" for the plan-authoring corollary.

A spike whose goal is "does X work end-to-end" must verify the **runtime wire path**, not just structural registration. The round-trip failure mode applies to spike ACs just as it applies to contract tests:

- **Registration ≠ initialization.** A module can be registered in a plugin registry while failing to initialize at runtime (missing deps, wrong boot order, missing env bindings).
- **Build success ≠ runtime reachability.** A header that compiles successfully may still be unreachable via the call path the spike claims to verify.

The spike's pass-condition is a contract test in miniature: it must exercise the real producer feeding the real consumer. If the pass-condition can return green while the runtime surface is broken, it is measuring the wrong seam.

## Reference Pattern: `writing-plans` Skill Checklist

When drafting a plan that introduces a new producer or consumer to an existing on-disk-artifact pipeline, the plan must name the round-trip contract test explicitly — not as a follow-up. If it isn't named in the plan, executors won't add it, and CI green will keep lying.
