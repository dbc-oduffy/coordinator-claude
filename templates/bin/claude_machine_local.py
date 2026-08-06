"""
claude_machine_local — ergonomic Python API for the machine-local registry.

Spec backlink: docs/plans/2026-05-20-portable-code-substrate.md §5.1
              docs/decisions/DR-072-durable-machine-local-coordinator-state-lives-in-settings-home-not-claude.md
Purpose: make the registry-correct shape shorter than the hardcoded literal so
agents and humans default to portable references. Resolves <settings-home> by
pure path arithmetic (never a filesystem read) and shells out to
<settings-home>/bin/_machine_local.py — never invokes the bare-name
`machine-local` wrapper (forbidden for consumers, see
docs/wiki/machine-local-registry.md §8(a)) and never imports
_machine_local.py in-process (dual-identity hazard, see
docs/wiki/dual-identity-module-hazard.md).

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

# Windows-only: suppress the console window that console-subsystem child
# processes flash when this process has no console to inherit (e.g. spawned by
# an MCP server or a GUI Claude Code host). POSIX: empty dict — CREATE_NO_WINDOW
# is a Windows-only attribute, so the ternary short-circuits before touching it.
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
    # Path.home() (not os.path.expanduser) is the fail-loud rung: it honours
    # USERPROFILE on Windows exactly as expanduser does, but raises
    # RuntimeError instead of silently returning the literal string "~" when
    # every home-resolution env var is unset -- expanduser's silent-degrade
    # is the exact shape that turns an unset shell into a cwd-relative
    # settings-home and writes artifacts at the drive root.
    home = os.environ.get("CLAUDE_HOME") or str(Path.home())
    return os.path.join(home, ".coordinator-claude-settings")


def _reader_invocation() -> list[str]:
    """Compose the invocation for the settings-home machine-local reader.

    Never shells out through the bare-name `machine-local` wrapper — that
    invocation form is forbidden for consumers (docs/wiki/machine-local-registry.md
    §8(a)) and hits a CreateProcess-no-PATHEXT/shebang trap on Windows. Instead,
    compose <settings-home>/bin/_machine_local.py by path arithmetic and invoke
    it explicitly under the running interpreter (sys.executable) — the running
    interpreter is by definition a working Python, so this dodges the trap on
    every OS without a PATH lookup.
    """
    impl = Path(_settings_home()) / "bin" / "_machine_local.py"
    return [sys.executable, str(impl)]


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
        # Review: code-reviewer — F3, invocation[0] is sys.executable (exists
        # by construction), so subprocess.run never raises FileNotFoundError
        # for a missing *script* argument — a missing reader path surfaces as
        # a normal non-zero CompletedProcess, not an exception. Check
        # existence directly rather than relying on an exception shape that
        # can't occur for this case.
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
                f"Fix: run `machine-local dir` (or `coordinator-settings-home`) "
                f"to locate your registry, then set \"{key}\" = \"<path>\" in "
                f"registry.local.toml there."
            )
        if result.returncode == 0 and not value:
            # Key exists but value is empty string (declared-but-unconfigured,
            # e.g. the AC14 case for repos.example-sim-repo before Machine-a population).
            raise AttributeError(
                f"Registry key '{key}' is declared but has no value. "
                f"Fix: run `machine-local dir` (or `coordinator-settings-home`) "
                f"to locate your registry, then set \"{key}\" = \"<path>\" in "
                f"registry.local.toml there."
            )
        # Any other non-zero exit: surface the real error from the reader.
        raise RuntimeError(
            f"machine-local CLI failed (exit {result.returncode}): {stderr}"
        )


repos = _Namespace("repos")
