# Pluggy hookspec semantics — parallel-call, not chained

Pluggy's `pm.hook.<name>(...)` call shape is **parallel-call**: every registered hookimpl runs with the *same* input arguments, and the return value is a `list` of each hookimpl's result (in LIFO registration order by default). It is NOT a chained pipeline — the output of one hookimpl does NOT feed the next as input.

## Rule

If you need *transformation* semantics — where each plugin can modify a value before passing it to the next — pluggy does not provide that natively. Use pluggy only to *collect* the participating hookimpls (or callables), then run an explicit reducer (`functools.reduce` or a plain loop) outside the hook call. Designing a hookspec as if its return value mutates the argument for downstream impls is a recurring bug: the second hookimpl sees the *original* input, not the first hookimpl's output, and the "transformation" silently no-ops for every impl after the first.

`firstresult=True` on the hookspec changes this only narrowly — pluggy stops at the first non-`None` return and gives you that single value. It is still parallel-call short-circuit semantics, not chained.

## Code shape contrast

```python
# WRONG — assumes chained semantics
@hookspec
def transform_value(value): ...

result = pm.hook.transform_value(value=x)  # returns LIST of results, each computed from x

# RIGHT — explicit reducer over collected transforms
@hookspec
def get_transformer(): ...

transformers = pm.hook.get_transformer()  # list of callables
result = functools.reduce(lambda acc, fn: fn(acc), transformers, x)
```

## When this applies

Designing any pluggy hookspec whose name reads like a verb-on-the-argument (`transform_*`, `enrich_*`, `filter_*`, `rewrite_*`). Audit the hookspec: if the intent is "each plugin gets to modify X in turn," the hookspec is wrong-shaped — return the transformer, reduce outside.

## Grep ratified cross-repo DRs BEFORE drafting a hookspec

When a hookspec spans repos — producer in repo A, consumer in repo B, addon in repo C — there may already be a ratified spec for the same seam from days or weeks earlier. Drafting fresh and reconciling later is the documented near-miss: prior-art-checker catches the name collision *after* drafting, the planner has already shaped the surface around the now-superseded name, and a rename pass becomes part of the dispatch.

**Concrete failure (project-rag, 2026-05-16):** C7 spec drafted `project_rag_declare_kind_sources` without checking D-5's already-ratified `project_rag_register_corpus_provider` from three days prior (memo lines 823, 879). Both addressed the same seam — registering a corpus provider into the host. Prior-art-checker caught the collision in the review pass; better discipline catches it before any text is written.

**Rule (before drafting):**

1. Grep ratified DRs in the originating repo: `rg "@hookspec.*<seam-shape>" docs/decisions/ archive/specs/`.
2. Grep peer-repo memos for the seam name family: `rg -n '\b(project_rag_|<peer-prefix>_)?<verb-noun>' <peer-repo>/docs/`.
3. Grep the central improvement queue and any open spinoff handoffs for the same surface: `rg -n '<seam-shape>' "$(coordinator_state_root --central)/improvement-queue/" "$(coordinator_state_root --central)/handoffs/"`.
4. If any hit names a ratified seam: cite it in the new spec's "prior art" frontmatter and either *extend* the ratified name (preferred) or document why this is a distinct seam in the same neighborhood (rare).

Cheap pre-flight; expensive to do as integrator-pass rewrite.

## Registering a hookspec: the names-list is necessary but not sufficient — attach it to the `_Hookspecs` wrapper too

Adding a pluggy hookspec to the experimental names-list (`EXPERIMENTAL_HOOKSPEC_NAMES`), `__all__`, and the shim is **not enough** — the staticmethod must also be attached to the `_Hookspecs` wrapper class the plugin manager registers (`core/addon_discovery.py`). Miss the wrapper attachment and `plugin_manager.add_hookspecs(...)` never learns the spec: your own roundtrip test passes (it exercises the shim in isolation), but the host's wrapper-completeness, conformance-harness, and roster tests go red.

**Rule:** a new hookspec is wired only when **all** its registration surfaces agree — names-list AND `__all__` AND shim AND the `_Hookspecs` wrapper attachment. Run the **baseline-diff of the conformance test dir** (`tests/addons/`), not just your own per-chunk roundtrip test, before declaring the spec registered — per-chunk green with a missing wrapper attachment showed 11 new failures (wrapper-completeness, conformance-harness, roster, phase4). Sister to the "Symmetric hookspec/handler wiring" rule in `implementation-standards-by-domain.md` (grep production callers of both halves). (Source: project-rag, 2026-06-25.)

## Related

- `~/.claude/CLAUDE.md` § Implementation Standards — Extensions (detect-then-fail-loud-when-ambiguous)
- `docs/wiki/round-trip-contract-tests.md` — for verifying multi-plugin pipelines end-to-end
- `docs/wiki/cross-repo-citation-conventions.md` — how to cite the ratified DR once you find it
