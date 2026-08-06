"""Tree-wide tripwire against writes to the live machine-local registry.

This tree — like ``coordinator/tests/`` — was adopted into ``testpaths`` in
2026-07 and sits OUTSIDE the reach of ``coordinator_core/conftest.py``'s
``_quarantine_real_home``, so nothing here stops a test (or a subprocess it
spawns with the ambient environment) from writing
``<settings-home>/machine-local/registry.local.toml`` — the fleet's cross-repo
resolution substrate, and a file no tmp_path discipline or dirty-tree gate
watches. The 2026-07-28 incident that motivates this landed in the sibling
tree; the same escape route is open here, and several CLIs exercised from this
tree (``repo-setup``, ``register-coordinator-mirror``, the DoE-root harvest leg)
reach registry writers.

Detection rather than redirection, deliberately: see the long note on the same
fixture in ``coordinator/tests/conftest.py`` for why arming
``MACHINE_LOCAL_REGISTRY_DIR`` tree-wide breaks tests that isolate at the
settings-home rung instead. This fixture changes no environment and no
resolution, so it cannot alter what a correct test observes.

NEGATIVE SPEC
    - Adds NO other fixtures, markers, or hooks. This tree has never had a
      conftest; anything beyond the single guard below silently widens its
      fixture surface.
"""

from __future__ import annotations

import pytest

from coordinator_core.testing.registry_sandbox import fail_on_live_registry_write_fixture

# Shared implementation: see
# ``coordinator_core.testing.registry_sandbox.fail_on_live_registry_write_fixture``
# (Review: code-reviewer, Finding 3, 2026-07-28 — was a byte-identical copy
# duplicated with ``coordinator/tests/conftest.py``; factored into one place).
# No opt-out marker by design: writing live machine config from a test is
# never correct. The remediation the failure names is
# ``coordinator_core.testing.registry_sandbox.sandbox_registry_dir``.
_fail_on_live_registry_write = pytest.fixture(autouse=True)(fail_on_live_registry_write_fixture)
