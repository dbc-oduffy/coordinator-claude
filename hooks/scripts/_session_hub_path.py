"""Stdlib mirror of the engine's canonical session-hub path.

`hub_for_common(common)` maps a git common dir to the session hub directory:
`<repo>/.coordinator-local/coordinator-sessions` when the common dir is a
`.git` directory, else `<common>/coordinator-sessions`. Never creates a
directory. Parity with `coordinator_core.session_hub_path.hub_for_common` is
pinned by `coordinator/tests/test_session_hub_path_parity.py`.
"""

from pathlib import Path

HUB_NAME = "coordinator-sessions"


def hub_for_common(common: Path) -> Path:
    """Return the session hub path for a git common dir; no I/O."""
    common = Path(common)
    if common.name == ".git":
        return common.parent / ".coordinator-local" / HUB_NAME
    return common / HUB_NAME
