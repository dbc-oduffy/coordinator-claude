"""
claude_machine_local — ergonomic Python API for the machine-local registry.

Spec backlink: docs/plans/2026-05-20-portable-code-substrate.md §5.1
              docs/decisions/DR-072-durable-machine-local-coordinator-state-lives-in-settings-home-not-claude.md
Purpose: make the registry-correct shape shorter than the hardcoded literal so
agents and humans default to portable references. Resolves <settings-home> by
pure path arithmetic (never a filesystem read) and shells out to
<settings-home>/bin/_machine_local.py — never invokes the bare-name
`machine-local` wrapper (forbidden for consumers, see
docs/wiki/hook-best-practices/machine-local-registry.md §8(a)) and never imports
_machine_local.py in-process (dual-identity hazard, see
docs/wiki/skills-corpus/dual-identity-module-hazard.md).

Public API:
    from claude_machine_local import repos
    project_rag_root = repos.project_rag           # pathlib.Path
    config_path = repos.project_rag / "config.toml"

    # Bootstrap shim for scripts that don't control sys.path at process start:
    import sys, os
    sys.path.insert(0, os.path.expanduser("~/.coordinator-claude-settings/bin"))
    from claude_machine_local import repos

Missing keys raise AttributeError with a remediation message. Never returns
None; never returns a hardcoded fallback.
"""

import os
import subprocess
import sys
from pathlib import Path

# an MCP server or a GUI Claude Code host). POSIX: empty dict — CREATE_NO_WINDOW
_NO_CONSOLE_WINDOW = (
    {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
)


def _settings_home() -> str:
    """Return the coordinator settings-home root path.

    Inline mirror of the canonical seam at
    coordinator/templates/bin/_machine_local.py::_settings_home — same
    two-rung precedence ladder, duplicated here rather than imported because
    consumers must never import _machine_local.py in-process (dual-identity
    hazard: two module copies with separate state in sys.modules).

    Precedence (most-specific first):
      1. COORDINATOR_SETTINGS_HOME — explicit override.
      2. ${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings — default.

    Negative-spec: pure path arithmetic — never reads a file to resolve this.
    """
    override = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if override:
        return override
    # USERPROFILE on Windows exactly as expanduser does, but raises
    home = os.environ.get("CLAUDE_HOME") or str(Path.home())
    return os.path.join(home, ".coordinator-claude-settings")


def _reader_invocation() -> list[str]:
    impl = Path(_settings_home()) / "bin" / "_machine_local.py"
    return [sys.executable, str(impl)]


class _Namespace:

    def __init__(self, prefix: str) -> None:
        self._prefix = prefix
        self._cache: dict[str, Path] = {}

    def __getattr__(self, name: str) -> Path:
        if name.startswith("_"):
            raise AttributeError(name)
        if name in self._cache:
            return self._cache[name]
        key = f"{self._prefix}.{name}"
        invocation = _reader_invocation()
        impl_path = invocation[-1]
        if not os.path.isfile(impl_path):
            raise RuntimeError(
                f"machine-local reader not found at {impl_path}; "
                f"install coordinator-claude to populate <settings-home>/bin/ "
                f"(run `machine-local dir` or `coordinator-settings-home` to "
                f"locate your settings home)"
            )
        result = subprocess.run(
            invocation + ["get", key],
            capture_output=True, text=True, check=False,
            **_NO_CONSOLE_WINDOW,
        )
        value = result.stdout.strip()
        if result.returncode == 0 and value:
            path = Path(value).expanduser()
            self._cache[name] = path
            return path
        stderr = result.stderr.strip()
        if result.returncode == 1 and "not found" in stderr:
            raise AttributeError(
                f"Registry key '{key}' is unset. "
                f"Fix: run `machine-local dir` (or `coordinator-settings-home`) "
                f"to locate your registry, then set \"{key}\" = \"<path>\" in "
                f"registry.local.toml there."
            )
        if result.returncode == 0 and not value:
            raise AttributeError(
                f"Registry key '{key}' is declared but has no value. "
                f"Fix: run `machine-local dir` (or `coordinator-settings-home`) "
                f"to locate your registry, then set \"{key}\" = \"<path>\" in "
                f"registry.local.toml there."
            )
        raise RuntimeError(
            f"machine-local CLI failed (exit {result.returncode}): {stderr}"
        )


repos = _Namespace("repos")
