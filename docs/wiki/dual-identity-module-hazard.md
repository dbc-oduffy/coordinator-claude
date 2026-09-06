# Dual-Identity Module Hazard

> A Python module that can be launched as `__main__` AND imported by canonical name is loaded *twice* in `sys.modules` — once as `__main__`, once as `<package>.<name>`. The two copies share no state: globals declared at module top reset to their declaration defaults on the second import.

*Lesson surface: project-rag — addon `engine_*` tools returned `missing_index` for weeks because `mcp/project_rag_server.py` was loaded as `__main__` (the entry point) while the addon late-bound the same module via its canonical path, getting a fresh copy with mutable state reset.*

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

## Bare-namespace top-level packages collide across sibling repos

*project-rag + project-rag-ue-addon.* A related `sys.modules` collision arises when two sibling repos each ship a **bare-namespace top-level package** with the same generic name — `scripts/`, `utils/`, `lib/`, `tests/` — and both get imported into one process (e.g. an addon imported into a host, or a shared test runner that loads both trees). Python keys `sys.modules` on the import name, not the on-disk path, so `import scripts.foo` from repo A and `import scripts.bar` from repo B both register under the single `scripts` package entry. Whichever repo imports first wins the namespace; the second repo's `scripts.*` submodules either shadow or fail to resolve, depending on import order — a non-deterministic, order-dependent failure.

**Defensive eviction is a workaround, not a fix.** Popping the colliding entry out of `sys.modules` before the second import (or manipulating `sys.path` ordering) papers over the symptom but leaves the latent collision for the next caller and the next import order. The structural fix is a **bilateral rename**: give each repo's top-level package a repo-unique name (`projectrag_scripts/`, `addon_scripts/`) so the namespaces never share a key. Generic bare-namespace package names are the root cause; only renaming removes it.

## Dual plugin-source-tree identity — verify the loaded copy, not the assumed-canonical one

*DoE-claude.* The `sys.modules` double-load above has a filesystem-level cousin: **two on-disk copies of the same plugin, each reached by a different launch path.** After the W4.2 cutover relocated the coordinator plugin source → `DoE-claude/coordinator/` (loaded via `--plugin-dir`), `~/.claude` retained an independent copy loaded by a plain `claude` invocation. A config/hook fix edited into one copy silently misses the other — the fix "lands" but nothing that runs loads it.

**Detection.** When a hooks/config fix looks restart-gated but the behavior (e.g. shim-not-connected noise) *persists in a genuinely fresh session*, do NOT re-open the diagnosis — first confirm which tree the session actually loads:

```bash
ps -eo pid,command | grep claude   # read the REAL --plugin-dir the session runs
```

Verify your edit against the **loaded** copy, not the assumed-canonical one. Two live copies of one plugin is the latent hazard; a fix to one silently misses the other — the same "both believe they are canonical, neither is wrong" shape as the `sys.modules` case above, one altitude up (source tree, not module object).

## Cross-references

- [`writing-plans.md`](./writing-plans.md) § Substrate-Verification — add this hazard check to the plan-time substrate audit for any plan that ships mutable module-level state.
- [`pre-dispatch-verification.md`](./pre-dispatch-verification.md) — grep the writer set and reader set for any boot-time global before declaring the writer's call sites complete.
