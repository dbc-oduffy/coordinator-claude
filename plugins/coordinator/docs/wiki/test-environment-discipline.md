---
title: Test Environment Discipline
status: active
kind: doctrine-wiki
created: 2026-05-18
---

# Test Environment Discipline

Two recurrent foot-guns from project-rag (2026-05-16) that violate the hermetic-test contract in subtle ways. Both look like "making tests simpler" but actually hide real failure modes.

## Overview

A "hermetic test" assumes the test process can fully control its dependencies and environment. Two foot-guns recur:

1. `sys.executable` ≠ project's pinned interpreter when tests are launched from a wrapper or IDE; the test resolves to whichever python invoked pytest.
2. Pinning an environment variable to a degraded state ("force CPU embedding") is treating tests as a probe of "does my code still run when GPU is unavailable" — that is a separate test, not the default-hermetic one.

Neither pattern is caught by "tests pass." Both produce green CI that silently misses production-shape regressions.

---

## 1. Resolve to the pinned venv python, not `sys.executable`

**Symptom.** Tests pass under `uv run pytest` but fail under `pytest` invoked directly; or pass on the EM's machine but fail in a sibling EM's session with a different default interpreter. Root cause: tests that spawn subprocesses with `sys.executable` get whatever python launched pytest — which may be the system python if pytest was installed there, not the venv python.

**Why this matters.** When a test spawns a subprocess (e.g. to test a CLI entrypoint, a worker process, or a serialization round-trip), the subprocess must use the same interpreter and installed packages as the test suite. `sys.executable` does not guarantee this. The venv path is deterministic; `sys.executable` is ambient.

**Fix.** Resolve the venv python explicitly at test-module or conftest scope:

```python
import os
import pathlib

# Adjust `parents[N]` to reach the project root from this file's location.
VENV_PY = (
    pathlib.Path(__file__).parents[N]
    / ".venv"
    / ("Scripts" if os.name == "nt" else "bin")
    / ("python.exe" if os.name == "nt" else "python")
)
assert VENV_PY.exists(), f"venv interpreter missing: {VENV_PY}"
```

Or via a pytest fixture that asserts `sys.executable` matches the expected venv path, skipping with explanation if the project root cannot be located:

```python
import pytest, pathlib, sys

@pytest.fixture(autouse=True)
def assert_venv_python(pytestconfig):
    venv_py = pytestconfig.rootpath / ".venv" / "bin" / "python"
    if not venv_py.exists():
        pytest.skip("venv interpreter not found — skipping env-contract assertion")
    assert pathlib.Path(sys.executable).resolve() == venv_py.resolve(), (
        f"Test launched with wrong interpreter.\n"
        f"  expected: {venv_py}\n"
        f"  got:      {sys.executable}\n"
        f"Run via `uv run pytest` or activate the project venv first."
    )
```

Either way, the test articulates its environmental contract rather than silently inheriting an ambient one.

**Anti-pattern to avoid.**

```python
# BAD — inherits ambient interpreter; breaks under wrapper launchers and CI matrix mismatches
subprocess.run([sys.executable, "my_worker.py", ...])
```

---

## 2. Failure-state pin ≠ hermetic-test pragma

**Symptom.** `PROJECT_RAG_EMBED_DEVICE=cpu` set unconditionally in `conftest.py` "to make tests deterministic." This configures the system in a degraded state (CPU embedding); tests do not exercise the GPU-enabled code path that production uses. Bugs in GPU-specific paths surface only at deploy time.

**Why this matters.** "Hermetic" means the test does not depend on external state outside the test's control. A GPU is part of the test machine's contract if the production system uses one. Forcing CPU does not achieve hermeticity — it just hides GPU regressions behind a permanently green signal.

**Fix.** Distinguish two test categories explicitly:

- **Production-shape tests** — run with the default device the deployed system uses (GPU if available). These are the canonical regression net. No device override in conftest.
- **Degraded-mode tests** — run with `EMBED_DEVICE=cpu`, marked `@pytest.mark.cpu_only` (or equivalent). These verify the fallback path and are additive, not substitutes.

```python
# conftest.py — correct pattern
import pytest

def pytest_configure(config):
    config.addinivalue_line(
        "markers", "cpu_only: test exercises the CPU-only (degraded) code path"
    )

@pytest.fixture
def cpu_embed_env(monkeypatch):
    """Use explicitly in degraded-mode tests; do NOT set globally."""
    monkeypatch.setenv("PROJECT_RAG_EMBED_DEVICE", "cpu")
```

```python
# test_embed_fallback.py — degraded-mode test
@pytest.mark.cpu_only
def test_embed_works_on_cpu(cpu_embed_env):
    ...
```

The production-shape suite runs without `cpu_embed_env`. Degraded-mode tests run in both matrices; production-shape tests require the GPU matrix.

---

## 3. CI matrix contract

If CI runs a CPU-only matrix and a GPU matrix, the test suite SHOULD assert the shape:

- Production-shape tests: GPU matrix (required), CPU matrix (skip-with-explanation acceptable, silent-passing is not).
- Degraded-mode tests: both matrices.

A skip-with-explanation is a contract signal — "this test requires GPU and was not run." A silent pass in the CPU matrix because the env-var was forced to CPU is a contract violation.

---

## Detection

```bash
# Tests that pin device/env-var without scoping to a marked fixture
grep -rn 'EMBED_DEVICE\|TORCH_DEVICE\|CUDA_VISIBLE_DEVICES' tests/ | grep -v '@pytest.mark'

# Tests that resolve sys.executable for subprocesses
grep -rn 'sys\.executable' tests/
```

Both patterns are legitimate in narrow contexts (a `cpu_only`-marked test, or a test that intentionally probes interpreter identity). The grep surfaces candidates for review; the rule is scope annotation, not prohibition.

---

## Related

- `docs/wiki/test-design-discipline.md` — broader test discipline (fixture hygiene, assertion granularity, round-trip contract tests)
- `docs/wiki/substrate-pin-doctrine.md` — CPU-vs-GPU wheel-pin enforcement at install time; paired concern with the device-pin foot-gun above
