---
title: Substrate-Pin Doctrine
status: active
kind: doctrine-wiki
created: 2026-05-18
---

# Substrate-Pin Doctrine

> Both index/source AND version must be locked — index-only or version-only pins fail silently under alternate resolvers.

## Overview

A substrate-pin (the specific version of a dependency AND the registry it came from) needs defense-in-depth. `uv` honors `[tool.uv.sources]`, but a stray `pip install` or sibling tool ignores it and resolves against PyPI's mirror, silently downgrading to a CPU wheel when the project requires CUDA — or substituting a different ABI build. The pin is only as strong as its weakest reachable resolver.

## The Failure Mode

**Observed at project-rag:** six silent torch downgrades from CUDA to CPU wheels in seven days.

`[tool.uv.sources]` pinned torch to the CUDA-12 index. Despite this, torch silently downgraded to PyPI's CPU wheel repeatedly because:

- A `pip install -e .` call (CI helper) bypassed uv-sources entirely.
- A `pip install -U <unrelated>` triggered re-resolution and pulled the CPU wheel.
- A constraints file from a sibling repo lacked the local-version suffix.

Each downgrade silently broke embedding tests — no exception, no loud failure, just CPU-speed runtime where GPU was expected. The fix that finally held: PEP 440 local-version pin (`torch==2.4.0+cu124`). After this change, bare `pip install torch` fails with "no matching distribution" instead of silently substituting.

## The Doctrine

**A substrate pin must specify BOTH index AND version.** Use all applicable layers for substrate-sensitive deps:

### Layer 1 — PEP 440 Local-Version Pin (strongest)

```toml
# pyproject.toml
dependencies = [
    "torch==2.4.0+cu124",
]
```

Makes any resolver that cannot find the exact local-version fail-loud rather than silently substitute. This is the only layer that catches `pip install -U` re-resolution.

### Layer 2 — `[tool.uv.sources]`

```toml
# pyproject.toml
[tool.uv.sources]
torch = { index = "pytorch-cuda" }

[[tool.uv.index]]
name = "pytorch-cuda"
url = "https://download.pytorch.org/whl/cu124"
explicit = true
```

Covers uv-native callers. Fails open against `pip` and sibling tools — necessary but not sufficient.

### Layer 3 — `constraints.txt` with Explicit Index URL

```text
# constraints.txt
--index-url https://download.pytorch.org/whl/cu124
torch==2.4.0+cu124
```

Covers `pip` callers when passed via `pip install -c constraints.txt`. Only effective if the index URL is in the same constraints file — omitting it lets pip use its default resolver and ignore the version's local suffix as unresolvable.

### Layer 4 — Lockfile

```bash
uv lock   # generates uv.lock
```

`uv.lock`, `requirements.lock`, `poetry.lock` — covers reproducible installs. Fails open against `pip install -U` when invoked without the lockfile.

### Defense-in-Depth Pyramid

```
fail-loud for any resolver  →  PEP 440 local-version pin  (==X.Y.Z+local)
default resolver coverage   →  [tool.uv.sources] + constraints.txt
reproducible installs       →  lockfile (uv.lock / poetry.lock)
```

Use ALL three levels for substrate-sensitive deps. No single layer is sufficient.

## Detection

Find substrate pins that lack a local-version suffix (should return empty for substrate-sensitive deps):

```bash
grep -E '^[a-zA-Z_-]+ ?==[0-9]+\.[0-9]+\.[0-9]+ *$' \
    pyproject.toml requirements*.txt constraints*.txt
```

A non-empty result for a CUDA wheel or ABI-sensitive binary dep is a misconfiguration — the pin will fail silently under alternate resolvers.

## Auditing a Suspect Environment

```bash
# Verify which torch variant is actually installed
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
# Expected on CUDA install: 2.4.0+cu124 True
# CPU downgrade signature: 2.4.0 False  (no local-version suffix)

# Confirm the installed wheel's index of origin
pip show torch | grep -i location
uv pip show torch
```

## Scope — When This Applies

This is overkill for ordinary deps. Apply substrate-pin doctrine to:

| Category | Examples | Risk |
|---|---|---|
| CUDA / ROCm wheels | torch, torchvision, cupy | CPU substitute is PyPI default; high probability of silent downgrade |
| ABI-sensitive binaries | numpy, scipy with non-default BLAS | Wrong BLAS backend silently degrades performance or produces wrong results |
| Vendored hashes | Any dep with `--hash=` in constraints | Already pinned by hash; document explicitly if skipping local-version layer |

Do NOT apply to pure-Python deps, optional extras, or dev tools — the overhead exceeds the risk.

## Anti-Patterns

- **Index-only pin** (`[tool.uv.sources]` without local-version): uv-native callers are covered; any `pip` call silently downgrades.
- **Version-only pin** (`torch==2.4.0` without `+cu124`): PyPI resolves to the CPU wheel because local-version suffix is absent.
- **Constraints file without `--index-url`**: `pip install -c constraints.txt torch==2.4.0+cu124` fails with "no matching distribution" against PyPI — the local-version suffix blocks the substitution but the index isn't provided either. Both must appear together.
- **`pip install -U` in CI without lockfile gate**: re-resolution bypasses all source pins; lockfile check should gate this.

## Related

- → `docs/wiki/implementation-standards-by-domain.md` § Python
- → project-rag wiki: `cpu-torch-install-trap.md` (site-specific install history)
