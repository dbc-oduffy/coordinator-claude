# Dual-Identity Module Hazard

> A Python module that can be launched as `__main__` AND imported by canonical name is loaded *twice* in `sys.modules` — once as `__main__`, once as `<package>.<name>`. The two copies share no state: globals declared at module top reset to their declaration defaults on the second import.

*Lesson surface: 2026-05-16, project-rag — addon `engine_*` tools returned `missing_index` for weeks because `mcp/project_rag_server.py` was loaded as `__main__` (the entry point) while the addon late-bound the same module via its canonical path, getting a fresh copy with mutable state reset.*

## Failure shape

```python
# mcp/project_rag_server.py
_INDEX = None   # boot-time mutable state

def boot():
    global _INDEX
    _INDEX = load_index()   # populates state in THIS instance

if __name__ == "__main__":
    boot()
    serve()
```

Then somewhere downstream:

```python
# addon/engine_tools.py
from mcp.project_rag_server import _INDEX   # imports FRESH copy
# _INDEX is None here — the boot() in __main__ touched a different instance
```

`sys.modules` now contains two entries: `__main__` (the launched version with `_INDEX` populated) and `mcp.project_rag_server` (a fresh import with `_INDEX = None`). Both believe they are the canonical module. Neither is wrong; both are real.

## Detection

Symptoms that should trigger a dual-identity audit:

- A module reports correctly-populated state when interrogated from its own entry point, but consumers see the empty/default state.
- A boot-time `print` or `log` line fires twice with different process semantics (once as `__main__`, once as canonical) — easy to miss because the second fire often happens long after the first.
- "It works in the smoke test (which uses the canonical import) but not in production (which launches as `__main__`)." Or the inverse.

`python -c "import sys; print([m for m in sys.modules if 'project_rag_server' in m])"` from inside the process surfaces the two identities directly.

## Rule

**Mutable state that needs to be readable by canonical-name importers must not live in a module that can be `__main__`.** Extract the state to a sibling module that has no entry-point identity:

```python
# mcp/_state.py — never __main__
INDEX = None

def boot():
    global INDEX
    INDEX = load_index()
```

```python
# mcp/project_rag_server.py — the entry point
from mcp import _state

if __name__ == "__main__":
    _state.boot()
    serve()
```

`mcp._state` can only ever be imported by canonical name; the dual-identity hazard cannot reach it. The entry-point module is reduced to a thin launcher with no globals worth caring about.

## Where this surfaces in this codebase

- Long-running MCP servers that are *both* launched (`python -m mcp.server`) AND imported by plugin / addon code via canonical path.
- Daemon-style background processes that expose introspection endpoints — the endpoint code reads `_STATE` via canonical import; the boot path populates `_STATE` via `__main__`.
- Test harnesses that import the production entry-point module to read its globals while the production process is also running.

## Cross-references

- [`writing-plans.md`](./writing-plans.md) § Substrate-Verification — add this hazard check to the plan-time substrate audit for any plan that ships mutable module-level state.
- [`pre-dispatch-verification.md`](./pre-dispatch-verification.md) — grep the writer set and reader set for any boot-time global before declaring the writer's call sites complete.
