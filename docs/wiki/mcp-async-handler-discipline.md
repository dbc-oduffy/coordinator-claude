---
system: mcp-async-handler-discipline
last_updated: 2026-05-18
status: living
provenance: coordinator improvement queue 2026-05-16 (project-rag-ue-addon)
---

# MCP Async Handler Discipline

> **The rule.** Blocking I/O inside an `async def` MCP handler MUST be wrapped in `asyncio.to_thread(fn, *args)` or replaced with a native async variant. Sync calls inside async handlers block the event loop; under stdio framer pressure this surfaces as "stale frame discarded" errors and client disconnects — not as a perf regression you can defer.

## Lesson surface

2026-05-16, project-rag-ue-addon. Sync `Path.read_text()` and `subprocess.run()` calls inline in two `async def` tool handlers. Under concurrent client load, the event loop stopped servicing the stdio framer mid-frame; client saw stale frames, retried, disconnected. Empirical event-loop-blocking probes did not flag it — async timing tests have too many yield-point escape hatches that mask real blocking when the offending call is fast in the single-client case.

## Failure shape

```python
# WRONG — sync I/O inside an async handler blocks the event loop
@server.tool()
async def read_symbol(path: str) -> str:
    return Path(path).read_text()              # blocks
    # or: subprocess.run([...], capture_output=True)
    # or: requests.get(url).text
    # or: sqlite3.connect(db).execute(...).fetchall()

# RIGHT — push the sync call to a worker thread
@server.tool()
async def read_symbol(path: str) -> str:
    return await asyncio.to_thread(Path(path).read_text)
    # or use a native-async client (httpx.AsyncClient, aiosqlite, asyncio.create_subprocess_exec)
```

Logs show `stale frame discarded` or client-side `MCP server disconnected` under load. Single-client smoke tests pass — the bug surfaces only when concurrent requests or large payloads pin the loop long enough that the stdio reader misses a frame boundary.

## Rule

Any blocking I/O inside an `async def` MCP handler — file reads, subprocess waits, `requests`, sync DB drivers, `time.sleep`, sync `socket` calls — MUST be either:

1. Wrapped in `asyncio.to_thread(fn, *args, **kwargs)`, or
2. Replaced with a native async equivalent (`httpx.AsyncClient`, `aiosqlite`, `asyncio.create_subprocess_exec`, `aiofiles`).

"I'll fix the perf later" is not an option. The default failure mode is correctness, not throughput — the framer is stateful and a missed frame breaks the session, not just slows it.

## Detection — source-level grep, not runtime probes

Async timing tests have too many yield-point escape hatches to be a reliable regression net. Use a source-level grep over every MCP server module:

```bash
# Find sync-call shapes inside async def handlers
rg -n --multiline -U \
  'async def \w+[^}]*?(\.read_text\(|\.write_text\(|subprocess\.run\(|requests\.(get|post|put|delete)\(|time\.sleep\(|sqlite3\.connect\()' \
  src/
```

Every hit is either a wrapped `asyncio.to_thread(...)` (verify ±3 lines) or a real bug. Run in CI on every PR touching `async def` handlers. Cheap, deterministic, survives refactors — empirical event-loop probes do not.

## Cross-references

- [`implementation-standards-by-domain.md`](./implementation-standards-by-domain.md) — sibling domain-specific standards (observability, DB/indexer, deps, packaging)
- [`verification-before-completion.md`](./verification-before-completion.md) — green unit tests aren't runtime-readiness when tests don't exercise the framer under load
