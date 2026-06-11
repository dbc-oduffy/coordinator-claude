"""
claude_machine_local — ergonomic Python API for the machine-local registry.

Spec backlink: docs/plans/2026-05-20-portable-code-substrate.md §5.1
Purpose: make the registry-correct shape shorter than the hardcoded literal so
agents and humans default to portable references. Shells out to ~/.claude/bin/
machine-local — never imports _machine_local.py (dual-identity hazard, see
docs/wiki/dual-identity-module-hazard.md and machine-local-registry.md §8(a)).

Public API:
    from claude_machine_local import repos
    project_rag_root = repos.project_rag           # pathlib.Path
    config_path = repos.project_rag / "config.toml"

    # Bootstrap shim for scripts that don't control sys.path at process start:
    import sys, os
    sys.path.insert(0, os.path.expanduser("~/.claude/bin"))
    from claude_machine_local import repos

Missing keys raise AttributeError with a remediation message. Never returns
None; never returns a hardcoded fallback.
"""
import os
import subprocess
from pathlib import Path

# Windows-only: suppress the console window that console-subsystem child
# processes flash when this process has no console to inherit (e.g. spawned by
# an MCP server or a GUI Claude Code host). POSIX: empty dict — CREATE_NO_WINDOW
# is a Windows-only attribute, so the ternary short-circuits before touching it.
_NO_CONSOLE_WINDOW = (
    {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
)


def _reader_invocation() -> list[str]:
    """Discover the right invocation for bin/machine-local on this OS."""
    bin_dir = Path.home() / ".claude" / "bin"
    if os.name == "nt":
        cmd = bin_dir / "machine-local.cmd"
        return [str(cmd)] if cmd.exists() else [str(bin_dir / "machine-local")]
    return [str(bin_dir / "machine-local")]


class _Namespace:
    """Lazy attribute resolver against a dotted-prefix registry namespace.

    Process-local memoization: first resolve per key triggers a subprocess
    call; subsequent accesses return the cached Path. Cache is process-local
    only (not persisted) — registry changes during a long-lived process
    require process restart, matching the reader's existing semantics.

    Negative-spec: exceptions are never cached — a missing or broken reader
    on first call must remain retryable after the operator fixes the issue.
    """

    def __init__(self, prefix: str) -> None:
        self._prefix = prefix
        self._cache: dict[str, Path] = {}

    def __getattr__(self, name: str) -> Path:
        if name.startswith("_"):
            # Dunder/underscore guard: hasattr / getattr-default / debugger
            # introspection must work without consulting the registry.
            raise AttributeError(name)
        if name in self._cache:
            return self._cache[name]
        key = f"{self._prefix}.{name}"
        invocation = _reader_invocation()
        try:
            result = subprocess.run(
                invocation + ["get", key],
                capture_output=True, text=True, check=False,
                **_NO_CONSOLE_WINDOW,
            )
        except FileNotFoundError:
            raise RuntimeError(
                f"machine-local reader not found at {invocation[0]}; "
                f"install coordinator-claude to populate ~/.claude/bin/"
            )
        value = result.stdout.strip()
        if result.returncode == 0 and value:
            # Happy path: key is set and non-empty. Cache successful resolutions
            # only — never cache exceptions (a missing/broken reader on first
            # call should remain retryable after the operator fixes the issue).
            path = Path(value).expanduser()
            self._cache[name] = path
            return path
        stderr = result.stderr.strip()
        if result.returncode == 1 and "not found" in stderr:
            # Key is genuinely absent from the registry.
            raise AttributeError(
                f"Registry key '{key}' is unset. "
                f"Fix: edit ~/.claude/machine-local/registry.local.toml "
                f"and set \"{key}\" = \"<path>\"."
            )
        if result.returncode == 0 and not value:
            # Key exists but value is empty string (declared-but-unconfigured,
            # e.g. the AC14 case for repos.dronesim before Striker population).
            raise AttributeError(
                f"Registry key '{key}' is declared but has no value. "
                f"Fix: set \"{key}\" = \"<path>\" in "
                f"~/.claude/machine-local/registry.local.toml."
            )
        # Any other non-zero exit: surface the real error from the reader.
        raise RuntimeError(
            f"machine-local CLI failed (exit {result.returncode}): {stderr}"
        )


repos = _Namespace("repos")
