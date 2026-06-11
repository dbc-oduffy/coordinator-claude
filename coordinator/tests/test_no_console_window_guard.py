"""
test_no_console_window_guard.py — regression net for the Windows console-popup fix.

Spec backlink: cross-repo/archive/2026-05-30-windows-popup-child-process-hypothesis.md
Purpose: Every console-subsystem subprocess spawn in coordinator production code
         must pass the Windows console-suppression guard, so a child process that
         runs with no console to inherit (MCP server / GUI Claude Code host /
         scheduled task) does not flash a focus-stealing window. The guard is the
         module-local `_NO_CONSOLE_WINDOW` dict (POSIX-empty, Windows
         `{"creationflags": CREATE_NO_WINDOW}`) splatted into the call, or an
         explicit `creationflags=` keyword.

Negative-spec: this test does NOT execute any spawn — it parses source with `ast`
               so it is formatting-robust and stays green on POSIX CI where the
               guard is an intentional no-op.

Detection limits (forbidden-by-convention in covered files, hence not handled):
  - `from subprocess import run` + bare `run(...)` — bare-name call form. Covered
    files use `import subprocess` + `subprocess.run`; a bare-name spawn would be
    invisible here. The aliased-module form (`import subprocess as sp` → `sp.run`)
    IS resolved below via the module's import bindings.
  - A console guard splatted under a name other than `_NO_CONSOLE_WINDOW`. The
    `creationflags=` explicit-keyword form is accepted; a differently-named spread
    dict is not, and would be flagged (false-positive). The CONSOLE-FLASH-GUARD-PY
    tripwire enforces the `_NO_CONSOLE_WINDOW` naming so this stays a non-issue.

A new unguarded `subprocess.run`/`Popen` in any listed file fails this test. When
adding a genuinely console-less spawn (no window possible), splat
`**_NO_CONSOLE_WINDOW` anyway — it is a no-op there and keeps the invariant total.
"""

import ast
import os

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PLUGIN_ROOT = os.path.normpath(os.path.join(_HERE, ".."))

# Production files that spawn child processes. The installed root copy
# ~/.claude/bin/claude_machine_local.py is the render of templates/bin/... below,
# so covering the template covers the installed copy.
_TARGET_FILES = [
    "whoami/coordinator_whoami/host_probes.py",
    "whoami/coordinator_whoami/session/probes.py",
    "lib/coordinator_session.py",
    "bin/check-install-divergence.py",
    "templates/bin/claude_machine_local.py",
]

_SPAWN_ATTRS = {"run", "Popen", "call", "check_call", "check_output"}


def _read(relpath: str) -> str:
    path = os.path.join(_PLUGIN_ROOT, relpath)
    assert os.path.isfile(path), f"target file moved or renamed: {relpath}"
    with open(path, encoding="utf-8") as f:
        return f.read()


def _subprocess_bound_names(tree: ast.Module) -> set[str]:
    """Names the `subprocess` module is bound to (handles `import subprocess as X`)."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "subprocess":
                    names.add(alias.asname or "subprocess")
    return names


def _is_subprocess_spawn(node: ast.Call, bound_names: set[str]) -> bool:
    """True if node is <subprocess-alias>.<run|Popen|call|check_call|check_output>(...)."""
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr in _SPAWN_ATTRS
        and isinstance(func.value, ast.Name)
        and func.value.id in bound_names
    )


def _is_guarded(node: ast.Call) -> bool:
    """True if the call carries the console guard (splatted dict or explicit kw)."""
    for kw in node.keywords:
        # Explicit `creationflags=...`
        if kw.arg == "creationflags":
            return True
        # `**_NO_CONSOLE_WINDOW`
        if kw.arg is None and isinstance(kw.value, ast.Name) and kw.value.id == "_NO_CONSOLE_WINDOW":
            return True
    return False


@pytest.mark.parametrize("relpath", _TARGET_FILES)
def test_every_subprocess_spawn_has_console_guard(relpath):
    tree = ast.parse(_read(relpath), filename=relpath)
    bound_names = _subprocess_bound_names(tree)
    assert bound_names, f"{relpath} does not `import subprocess` — target list is stale"

    unguarded = [
        f"{relpath}:{node.lineno}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _is_subprocess_spawn(node, bound_names) and not _is_guarded(node)
    ]
    assert not unguarded, (
        "Unguarded subprocess spawn(s) — add `**_NO_CONSOLE_WINDOW` to suppress "
        "Windows console pop-ups:\n  " + "\n  ".join(unguarded)
    )


@pytest.mark.parametrize("relpath", _TARGET_FILES)
def test_guard_constant_is_defined(relpath):
    """Each target file must define _NO_CONSOLE_WINDOW so the splat resolves at runtime.

    AST-based (not string-match) so a `_NO_CONSOLE_WINDOW` mentioned only in a
    comment/docstring does not satisfy the check — the actual assignment must exist.
    """
    tree = ast.parse(_read(relpath), filename=relpath)
    defined = any(
        isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "_NO_CONSOLE_WINDOW" for t in node.targets)
        for node in ast.walk(tree)
    )
    assert defined, f"{relpath} references the guard but does not assign _NO_CONSOLE_WINDOW"
