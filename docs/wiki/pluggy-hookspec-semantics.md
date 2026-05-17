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

## Related

- `~/.claude/CLAUDE.md` § Implementation Standards — Extensions (detect-then-fail-loud-when-ambiguous)
- `docs/wiki/round-trip-contract-tests.md` — for verifying multi-plugin pipelines end-to-end
