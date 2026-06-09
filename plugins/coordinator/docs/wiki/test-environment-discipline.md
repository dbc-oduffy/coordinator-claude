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

## 4. Autouse HOME-Isolation Fixtures Are Inherited by Spawned Subprocesses

*Source: L20, test-design §32. project-rag, 2026-05-24.*

A pytest autouse fixture that redirects `HOME` (or its Windows equivalent `USERPROFILE`) to a tmp directory — to isolate per-test config — is **inherited by any subprocess** the test spawns via `subprocess.run` / `Popen`. If that subprocess calls `os.environ.copy()` (the common pattern), it carries the hijacked HOME and silently uses the wrong root. The in-process path is correct, so the test **appears to pass** while the subprocess operates against substrate that doesn't exist.

This is the same class as §1 (`sys.executable` ambient-inheritance): the test's environmental contract leaks into children it does not control.

**Fix.** Add a `@pytest.mark.real_home` escape-hatch marker and have the autouse fixture skip the HOME redirect for tests whose subject explicitly spans a subprocess boundary into real `~/.claude/bin` substrate:

```python
@pytest.fixture(autouse=True)
def _isolate_home(request, monkeypatch, tmp_path):
    if request.node.get_closest_marker("real_home"):
        return  # subprocess needs the real HOME substrate
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
```

**Module-import-time capture corollary (L199).** If a module captures an env var at *import time* (`_ROOT = os.environ["HOME"]` at module scope), a per-test autouse `monkeypatch.setenv` runs too late — the value is already bound. The autouse fixture must ALSO `monkeypatch.setattr` the captured module attribute, not just the env var. Greppable smell: module-level `os.environ[...]` / `os.getenv(...)` assignments outside a function body.

## 5. Native-Backed Stores (Chroma / SQLite / LMDB) Segfault In-Process Under Concurrent Writes — Isolate Reads in a Subprocess

*Recurs: ragaddon-L8, ragaddon-L427. Consolidated 2026-05-27. [universal]*

A test that opens a large native-backed store **in-process** while another session holds the write lock races into a native access violation (Windows `0xC0000005` in chromadb's Rust layer) that **aborts the entire pytest process with a raw stack dump**. A native crash cannot be caught with `try/except` — the interpreter is gone before any Python handler runs. On a multi-session machine (e.g. ~15 concurrent EM sessions, RAM-saturated) this is not rare; it is the expected outcome.

**Concrete failures.**
- *ragaddon-L8:* `test_corpus_chunks_carry_provenance_module` opened the 3.6GB `chroma.sqlite3` directly while the corpus-extraction session was mid-write — native access violation, raw stack dump, pytest aborted.
- *ragaddon-L427:* the fix commit subprocess-isolated the ONE test that fired but left `test_embedding_model_parity.py:87` doing the identical unguarded open — a still-live landmine for the next full `pytest tests/`. **A point-fix on the test that happened to crash is not a fix.**

**Rule.**
1. **Isolate the entire class of live-store reads in a subprocess** (e.g. `tests/_read_corpus_provenance.py`), not one test at a time. The parent interprets a crash returncode as an actionable fail — "store written concurrently (dev) or corrupt (CI)" — never as a segfault that takes the suite down.
2. **Grep every test for the open primitives** (`PersistentClient`, `_evs_dir`, `resolve_addon_data_root`, raw `sqlite3.connect` on the canonical store path) and route all of them through the subprocess reader. The discriminator is "reads a large native-backed store on a multi-session machine," not "the test that crashed today."
3. **Pair with a heavy-workstream lock** serializing pytest against pipeline/embedding writes, and cap concurrent sessions.

This composes with the round-trip subprocess interpreter rule (§1): the subprocess must use the pinned venv python, and its crash returncode is the contract signal.

## 6. Concurrent-Shared-Tree Edits Produce Fake Assertion Failures on HEAD-Correct Constants

*Source: ragaddon-L8 (second failure mode). 2026-05-27.*

On a machine where multiple sessions share one working tree, a test can read a source file **mid-edit** — transiently in a partial state — and assert against a constant that HEAD already defines correctly. The failure is a concurrency artifact, not a defect.

**Concrete failure.** A run reported a *fake* "invalid 'blueprint' value" assertion: the shared tree had `provenance_module.py` transiently in a 4-value `_VALID_MODULES` state during a concurrent edit, even though HEAD already had all 14 values (committed days earlier).

**Rule.** Treat a transient assertion failure on a shared-tree-derived constant as **suspect until re-verified against `git show HEAD:<file>`**. Don't triage it as a code defect or "fix" the constant. This is the runtime mechanics behind test-design §38 (stale-bytecode flake) — same root (shared/transient on-disk state), different surface (live edit vs. stale `.pyc`).

## 7. Clean-Shell Smoke After Every Production-Artifact Commit

*Source: L214, L177. 2026-05-27.*

Fixture-substitution test isolation can mask production-state drift: a fixture that swaps a real implementation in "at test time" makes the test green while the **on-disk artifact under test IS the stub** (test-design §33). Likewise, symmetric hookspec wiring can have test invocations that exercise a code path no production caller reaches — test green, production wire-path dead (composes with test-design §20/§21).

**Rule.** After committing a production artifact (a hookspec wiring, a config-format consumer, an installed script, a plugin registration), run a **smoke from a clean shell** — fresh process, no test fixtures, no path hacks — that drives the real entry point. Grep for *non-test production callers* of any symmetric pair you ship: test invocations don't prove production wiring. The clean-shell smoke is the analogue of round-trip's "real producer feeding real consumer" at the install boundary.

## 8. Partner-Tool Integration Tests: Ship the Mixed-Result Data, Don't Try to Make It Green

*Source: DroneSim `state/lessons.md` (L12, central-promoted 2026-05-29). [universal]*

When running an integration test against a partner team's or upstream tool's release, **producer/consumer failures are the deliverable** — they are the reason the test run exists. Workarounds that make the test appear to pass (installing a missing tool on the fly, editing a config to skip a failing producer, commenting out broken consumers) hide the exact bugs the test was designed to surface.

**Rule.** When a partner-tool integration run produces a mixed result — some producers/consumers pass, others fail — ship the full producer ledger and findings back to the partner team unmodified. A green run achieved by masking failures is less valuable than a partial-green run that names every failing seam precisely. Concrete failure mode: the 2026-05-01 project-rag v0.1.1 reindex left `graph.db` essentially empty; suppressing the producer errors to reach a "clean" run would have hidden the root cause entirely.

**How to apply.** Write integration test runs to output a machine-readable ledger (pass/fail per producer/consumer, with error summaries). Deliver the ledger even — especially — when it is mixed. The partner team needs the signal, not a polished green dashboard.

## 9. Don't Combine "Purge Cache" with "First Untested Run"

*Source: DroneSim `state/lessons.md` (L14, central-promoted 2026-05-29). [universal]*

A clean-state flag that wipes downstream artifacts (vector store, collection, derived data cache, build intermediates) **before** a producer/consumer chain has been verified to rebuild correctly turns any pipeline failure into a net regression: the previously-working state is gone, and the new state was never proven. This is the test-environment analog of the "don't destroy your backup before the restore is verified" principle.

**Rule.** When using a `--purge`, `--clean`, or equivalent flag on a pipeline whose rebuild path is unproven in the current environment, run WITHOUT the flag first to verify the full rebuild succeeds end-to-end. Only purge after a non-purge run has produced a known-good rebuilt state. Concrete failure mode: the 2026-05-01 project-rag reindex used `--purge` to match handoff framing of "start from a clean state"; consumer schema-mismatch failures meant nothing rebuilt the vector store, dropping `semantic_search` and `blended_query` from working to broken — a net regression even though prior state was usable.

**Exception.** Purge is safe before a first-ever run (no prior state to lose) or when you have an independent backup of the prior state that can be restored on failure.

## 10. Large Red Residual After a Week of Landed Refactors Is Stale-Test Debt — Triage Before Fixing

*Source: cross-repo learn-lessons, 2026-05-30. [universal]*

When a long-lived shared branch suddenly shows a large red residual (100+ failing tests) after a week of landed refactors, the instinct is to read it as the current session's live work breaking. It usually isn't. Most of those reds are **stale-test debt from refactors that already shipped** — stale `mock.patch` targets, deleted-module import paths, removed-kwarg fixtures and goldens — not regressions the active workstream introduced. The reds inherit the branch's age the same way a gate-created "pre-existing failure" does (test-design §26): the refactor landed, the test's assumptions lagged, and the failure sat there.

**Sampling two reds and extrapolating mislabels the whole bucket.** Two stale-patch-target reds make the residual look like "concurrent session broke everything"; two genuine-bug reds make it look "all live work." Neither sample is representative of a heterogeneous residual.

**Rule.** Before fixing a large red residual on a refactor-heavy shared branch, **triage by attribution, not by sampling.** Dispatch read-only triage workers to classify *each* red into a bucket — `{stale-patch-target / stale-path / stale-fixture / hygiene-gap / concurrent-active / genuine-bug}` — with a fix-locus and a `safe-now` flag per entry. Then fix only the safe slice and commit per-wave; surface `genuine-bug` and `concurrent-active` separately rather than folding them into the bulk sweep. *Empirical anchor (2026-05-30):* a "97 concurrent reds" first impression triaged to ~91 fixable stale-debt entries + 6 not-ours — the bulk was landed-refactor lag, not the concurrent session's live work. Composes with test-design §26 ("pre-existing failure" is provisional — a recently-landed refactor can have created it), §43 (collection errors + slow-marking mask large populations — fix collection first, then attribute), and §56 (source-migrate without test-migrate leaves an import wall — a major stale-path source).

## scope="session" autouse fixture bleeds global state into every later file

A `scope="session"` autouse fixture that mutates global state (`sys.modules`, `os.environ`) restores only at session END — it bleeds into every later file in the session. A later test then trips on the leaked state. Use `scope="module"` for global-state mutators. Also: a test driving real lifespan must pin ALL env knobs via monkeypatch, not inherit ambient state. Apply: audit `scope="session"` fixtures that mutate global state and downgrade to `scope="module"`.

## repro Windows daemon spawn bugs under production parent context (nohup/detached) not foreground bash

Test-environment console does not equal production-environment console for child-process spawn flags. A Windows daemon bug that only manifests in production (hidden console, no stdin) may not reproduce in a foreground bash test. Always repro Windows daemon spawn bugs under production parent context: use `nohup`, `START /B`, or a fully-detached spawn wrapper to replicate the real launch conditions. Apply: any Windows daemon spawn-flag bug investigation must include a repro under production parent context before concluding the fix works.

## Related

- `docs/wiki/test-design-discipline.md` — broader test discipline (fixture hygiene, assertion granularity, round-trip contract tests); §32–33 (HOME-isolation, fixture-substitution), §38 (stale-bytecode flake), §44 (bound every run)
- `docs/wiki/round-trip-contract-tests.md` — producer/consumer seam tests; native-store subprocess reads use the pinned venv interpreter (§1)
- `docs/wiki/substrate-pin-doctrine.md` — CPU-vs-GPU wheel-pin enforcement at install time; paired concern with the device-pin foot-gun above
