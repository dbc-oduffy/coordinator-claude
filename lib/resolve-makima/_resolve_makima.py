"""
_resolve_claude_klabauter.py — shared resolve-claude-klabauter-bin ladder, extracted from
``coordinator_core.install.substrate._write_agent_forwarder``'s
formerly-inline-per-forwarder body.

Every emitted bin forwarder used to carry its own copy (~50 lines) of the
registry-then-sentinel resolution ladder that locates
``<claude-klabauter-root>/coordinator/bin/`` and validates it before exec'ing into a
target CLI there. With the forwarder SET now derived from a directory
listing (rather than a hand-maintained ~10-entry tuple — see
``substrate.py``'s ``_derive_agent_helper_names``), that duplication would
have scaled to ~127+ near-identical copies of the same ladder. This module
is installed ONCE (alongside every emitted forwarder, in the same shim
dir — settings-home ``bin/`` and the ``~/.claude/bin`` compat mirror) and
imported by each forwarder's now-trivial ~6-line body.

Contract preserved verbatim from the prior inline body (DoE-claude
``coordinator/snippets/resolve-claude-klabauter-bin.md``, DoE commit ``ad7fb0d1``):
registry-key-then-sentinel resolution rungs, ``coordinator/bin`` composition,
the ``..``-traversal guard, on-disk existence checks for the resolved root
and ``coordinator/bin``, an *executable* sentinel probe (``archive-stamp-cli``),
and distinct fail-loud messages for the two on-disk failure modes (wrong/
incomplete checkout vs. stale/partial migration).

Deliberately does NOT carry the ``_cc_trusted``/``.doe-root`` trust-prefix
dance the prior template never carried either — this seam's trust posture
differs from ``cc-root-source-guard``: ``registry.local.toml`` and
``.claude-klabauter-root`` are per-machine, gitignored, operator-authored config under
the operator's own settings-home, not a harness-supplied value an external
actor can steer. What this module DOES check — because a typo'd or stale
config value is a real, non-adversarial failure mode, not a trust boundary —
is exactly the four checks enumerated above.

Spec backlink:
    DoE-claude coordinator/snippets/resolve-claude-klabauter-bin.md (DoE commit ad7fb0d1)
    docs/plans/2026-07-23-... (M1 — forwarder-ladder extraction + derived set)
    cross-repo/inbox/2026-07-22-claude-central-em-forwarder-template-still-execs-dead-doe-bin.md

Port source: coordinator_core.install.substrate._write_agent_forwarder
"""
from __future__ import annotations

import os
import runpy
import stat
import sys
from pathlib import Path
from typing import List, Optional


class ClaudeKlabauterResolutionError(RuntimeError):
    """A fully-formed, fail-loud message ready to write to stderr verbatim.

    Each raise site below matches one distinct failure mode from the ladder
    (missing config, traversal, missing root, missing coordinator/bin,
    missing/non-executable sentinel) — callers must not collapse these into
    a single generic message; see module docstring.
    """


def _settings_home() -> Path:
    """Resolve the coordinator settings home (mirrors _claude_home.py's
    settings_home() precedence, replicated inline here rather than imported
    — this module must stay import-independent of coordinator_core, since it
    is installed standalone into a bare bin/ directory with no package
    context).

    HOME guard (2026-07-28): the Windows claude-doe.cmd -> `bash -c` launch
    chain is a NON-LOGIN, cmd-spawned shell env that can present with
    COORDINATOR_SETTINGS_HOME/CLAUDE_HOME/HOME all empty. The prior body then
    fell back to os.path.expanduser("~"), which returns a LITERAL "~" when no
    home var is resolvable — silently yielding the garbage relative path
    "~/.coordinator-claude-settings"; the shell-equivalent
    "$HOME/.coordinator-claude-settings" with empty $HOME collapses to
    "/.coordinator-claude-settings", which Windows resolves to the current
    DRIVE ROOT (a stray 0-byte X:\\.coordinator-claude-settings was created that
    way, 2026-07-28). This resolver now (a) consults USERPROFILE so a bare
    cmd.exe session with no HOME still resolves on Windows, and (b) fails loud
    (ClaudeKlabauterResolutionError, caught by exec_cli into a clean stderr message)
    rather than returning a path a downstream writer lands junk at. Empty
    COORDINATOR_SETTINGS_HOME still falls through (unchanged) — a launch env
    that exports it empty must not start failing.
    """
    override = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if override:
        return Path(override)
    home = (
        os.environ.get("CLAUDE_HOME")
        or os.environ.get("HOME")
        or os.environ.get("USERPROFILE")
        or ""
    )
    if not home:
        expanded = os.path.expanduser("~")
        if expanded and expanded != "~":
            home = expanded
    if not home:
        raise ClaudeKlabauterResolutionError(
            "ERROR: cannot resolve the coordinator settings home — none of "
            "COORDINATOR_SETTINGS_HOME, CLAUDE_HOME, HOME, or USERPROFILE is set "
            "and '~' is unexpandable (a non-login shell env). Set CLAUDE_HOME or "
            "HOME to your home directory, or launch from a normal shell\n"
        )
    return Path(home) / ".coordinator-claude-settings"


def _ml_dir() -> Path:
    """Resolve the machine-local registry directory.

    Negative-spec: does NOT validate ``MACHINE_LOCAL_REGISTRY_DIR`` itself —
    by the time this override is read, the operator has already selected
    the file; a guard here would be vacuous (the value has no independent
    "before use" moment to police).
    """
    override = os.environ.get("MACHINE_LOCAL_REGISTRY_DIR")
    return Path(override) if override else (_settings_home() / "machine-local")


def _resolve_claude_klabauter_root(ml_dir: Path) -> str:
    """Resolve the claude-klabauter root path via the registry-then-sentinel
    ladder, validating it before return.

    Rung 1 (preferred): registry.toml (tracked baseline) then
    registry.local.toml (per-machine override, wins on collision) — key
    "repos.claude_klabauter" in either the nested [repos] table or the flat
    quoted-dotted-key form ``machine-local set`` writes. Empty-string is a
    miss, not a hit (never overwrites a value already resolved from the
    other file).

    Rung 2 (fallback): .claude-klabauter-root sentinel — honored when the registry key
    above is absent or the file itself is missing.

    Raises ClaudeKlabauterResolutionError (with a fail-loud, distinct message) when:
      - neither rung resolves anything,
      - the resolved value contains a '..' traversal segment,
      - the resolved value does not exist on disk as a directory.
    """
    claude_klabauter_root = ""
    for fname in ("registry.toml", "registry.local.toml"):
        registry_path = ml_dir / fname
        if not registry_path.is_file():
            continue
        try:
            import tomllib
            with open(registry_path, "rb") as f:
                registry_data = tomllib.load(f)
        except Exception:
            continue
        nested = registry_data.get("repos", {})
        if isinstance(nested, dict):
            v = nested.get("claude_klabauter")
            if isinstance(v, str) and v:
                claude_klabauter_root = v
        flat = registry_data.get("repos.claude_klabauter")
        if isinstance(flat, str) and flat:
            claude_klabauter_root = flat

    if not claude_klabauter_root:
        sentinel_path = ml_dir / ".claude-klabauter-root"
        try:
            with open(sentinel_path, "r", encoding="utf-8") as f:
                claude_klabauter_root = f.read().rstrip("\r\n")
        except OSError:
            claude_klabauter_root = ""

    claude_klabauter_root = claude_klabauter_root.rstrip("\r\n").rstrip("/")

    if not claude_klabauter_root:
        raise ClaudeKlabauterResolutionError(
            "ERROR: cannot resolve claude-klabauter — set it via 'machine-local set "
            f"repos.claude_klabauter <path>' (writes {ml_dir}/registry.local.toml), "
            f"or write the path to {ml_dir}/.claude-klabauter-root\n"
        )

    # Corrupted/typo'd-config guard, not a hostile-input guard — see module
    # docstring for why no harness-facing prefix-allowlist applies here.
    if "/.." in claude_klabauter_root:
        raise ClaudeKlabauterResolutionError(
            f"ERROR: resolved claude-klabauter root '{claude_klabauter_root}' contains a "
            f"'..' traversal segment — refusing; fix {ml_dir}/registry.local.toml "
            f"or {ml_dir}/.claude-klabauter-root\n"
        )

    if not os.path.isdir(claude_klabauter_root):
        raise ClaudeKlabauterResolutionError(
            f"ERROR: resolved claude-klabauter root '{claude_klabauter_root}' does not exist "
            "on disk — re-run 'machine-local set repos.claude_klabauter <path>' or fix "
            f"{ml_dir}/.claude-klabauter-root\n"
        )

    return claude_klabauter_root


def _is_executable(path: str) -> bool:
    """Stdlib-only twin of ``coordinator_core.win_portability.is_executable``
    — POSIX exec-bit inspection, Windows PATHEXT resolvability (a suffixed
    file must carry a PATHEXT suffix; an extensionless one is launchable only
    via a PATHEXT-suffixed sibling, which is what ``CreateProcess`` actually
    execs).

    Negative-spec — this MUST NOT become
    ``from coordinator_core.win_portability import is_executable``, at module
    scope or lazily. This file is installed standalone into the operator's
    ``<settings-home>/bin/`` beside ~334 generated forwarders and runs on a
    bare ``#!/usr/bin/env python3`` with only the stdlib importable: its
    entire job is to FIND claude-klabauter, so it cannot presuppose claude-klabauter is already
    importable. The package import landed here in ``a141074a``'s 40-site
    ``os.access(X_OK)`` -> ``is_executable()`` sweep, which had no way to see
    that this one call site executes outside the package, and it took down
    every bareword CLI on PATH at once — ``ModuleNotFoundError:
    coordinator_core`` before the ladder's first line, including
    ``~/.local/bin/claude-doe``, i.e. launching Claude Code itself.

    A lazy import off the resolved root is not the fix either: it would make
    the sentinel probe demand a FULL, importable checkout, conflating
    "coordinator/bin/ holds a launchable sentinel" (what this ladder rung
    actually asks) with "this tree is an installed Python package". The
    duplication is the deliberate cost of this file's standalone contract —
    keep the two in sync by hand if the Windows semantics change.

    ``os.access(path, os.X_OK)`` is banned repo-wide (see
    ``win_portability``'s own docstring: it degrades to existence-only on
    NTFS) — mode-bit inspection, not that call, is the POSIX branch here."""
    p = Path(path)
    if os.name != "nt":
        try:
            mode = os.stat(p).st_mode
        except OSError:
            return False
        return bool(mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))

    # PATHEXT's own separator is always ';' on Windows — never os.pathsep,
    # which would be ':' under a POSIX host modelling Windows semantics.
    pathext = os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD")
    exts = [e.upper() for e in pathext.split(";") if e.strip()]
    if p.suffix:
        return p.is_file() and p.suffix.upper() in exts
    return any((p.parent / (p.name + ext.lower())).is_file() for ext in exts)


def resolve_claude_klabauter_bin_dir() -> str:
    """Resolve, validate, and return ``<claude-klabauter-root>/coordinator/bin``.

    The coordinator-owned CLIs live at ``<claude-klabauter-root>/coordinator/bin``, NOT
    ``<claude-klabauter-root>/bin`` (that top-level bin/ is a different, unrelated
    claude-klabauter directory with its own entries).

    Probes a specific, load-bearing executable (``archive-stamp-cli``)
    rather than trusting dir-existence alone — a bare directory can exist
    without containing the CLIs a caller needs.

    Raises ClaudeKlabauterResolutionError with a message distinguishing "wrong or
    incomplete checkout" (coordinator/bin/ itself missing) from "stale or
    partial migration" (coordinator/bin/ exists but its sentinel doesn't) —
    these are different failure modes and must not be collapsed into one
    generic message.
    """
    ml_dir = _ml_dir()
    claude_klabauter_root = _resolve_claude_klabauter_root(ml_dir)

    bin_dir = claude_klabauter_root + "/coordinator/bin"
    if not os.path.isdir(bin_dir):
        raise ClaudeKlabauterResolutionError(
            f"ERROR: '{bin_dir}' does not exist — the claude-klabauter clone at '"
            f"{claude_klabauter_root}' has no coordinator/bin/ directory; wrong or incomplete "
            "checkout. Confirm repos.claude_klabauter points at the claude-klabauter repo "
            "root (not a subdirectory)\n"
        )

    sentinel = bin_dir + "/archive-stamp-cli"
    if not _is_executable(sentinel):
        raise ClaudeKlabauterResolutionError(
            f"ERROR: '{sentinel}' is missing or not executable — coordinator/bin "
            f"exists at '{bin_dir}' but its sentinel CLI (archive-stamp-cli, the "
            "sole authorized handoff/memo frontmatter writer) is absent; this is a "
            "stale or partial claude-klabauter migration, not a wrong-path problem. "
            "Re-sync/re-clone claude-klabauter\n"
        )

    return bin_dir


def _run_target_in_process(target_path: str, argv: List[str]) -> int:
    """Run *target_path* (a ``coordinator/bin/`` Python CLI) in-process,
    return its intended exit code.

    Every ``coordinator/bin/`` CLI is a plain ``.py``-shaped module (some
    extensionless, some ``.py``-suffixed — see ``substrate.py``'s
    ``_write_agent_forwarder`` docstring) whose body is either a bare script
    or the ``if __name__ == "__main__": sys.exit(main(sys.argv[1:]))``
    pattern (e.g. ``archive-stamp-cli``). ``runpy.run_path(...,
    run_name="__main__")`` is the portable stdlib primitive that executes a
    plain file path as if it were run as ``__main__`` — no shebang
    interpretation needed (unlike ``os.execv`` on Windows, which goes
    through ``CreateProcess`` and cannot honor ``#!`` lines), no second
    interpreter cold-start, and no module-registry entry required for a
    target this function has no static import path for (targets are
    resolved dynamically by filename, not by package name).

    ``sys.argv`` is swapped for the duration of the call (restored in
    ``finally``) because target scripts read ``sys.argv`` directly (as
    ``archive-stamp-cli`` does) rather than accepting an injected argv
    parameter — this is the in-process equivalent of what ``execv``/
    ``subprocess`` would otherwise set up via the child's own process argv.

    A target that calls ``sys.exit(n)`` raises ``SystemExit(n)`` through
    ``run_path`` exactly as it would run standalone; that is caught here and
    its ``.code`` propagated (``None`` and non-int codes normalize to 0/1
    per Python's own ``sys.exit`` contract, mirrored here rather than
    reinvented). A target that falls off the end without calling
    ``sys.exit`` completes with implicit success (0), matching normal
    process-exit semantics.
    """
    original_argv = sys.argv
    try:
        sys.argv = [target_path] + argv
        runpy.run_path(target_path, run_name="__main__")
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        sys.stderr.write(str(code) + "\n")
        return 1
    finally:
        sys.argv = original_argv
    return 0


def exec_cli(target: str, argv: Optional[List[str]] = None) -> None:
    """Resolve ``<claude-klabauter-root>/coordinator/bin/<target>`` and run it,
    forwarding *argv* (defaults to ``sys.argv[1:]``).

    POSIX: ``os.execv``s into ``sys.executable`` with *target_path* as its
    first argument (``[sys.executable, target_path, *argv]`` — never returns
    on success, replaces the current process image). Interpreter-targeted,
    not shebang-dependent: this runs the target as ``python target_path``
    rather than executing *target_path* itself, so it no longer relies on
    every ``coordinator/bin/`` CLI carrying a ``#!/usr/bin/env python3``
    shebang or its executable bit being set.

    Windows: ``os.execv`` cannot honor a POSIX shebang — ``CreateProcess``
    (which ``os.execv`` goes through on Windows) does not interpret ``#!``
    lines, so a bare extensionless *target_path* fails outright. Windows
    also can't truly replace the current process image the way POSIX
    ``exec`` does. The prior body worked around both problems by resolving
    a second Python interpreter and ``subprocess.run``-ing the target — a
    full interpreter cold-start on every single forwarder call. Every
    ``coordinator/bin/`` target is a Python CLI (naked ``.py``-shaped file,
    with or without a ``.py`` suffix — see ``substrate.py``'s
    ``_write_agent_forwarder`` docstring), so there is no "genuinely
    unimportable target class" requiring a spawn fallback: this process is
    already running Python, so the fix is to run the target **in-process**
    via ``_run_target_in_process`` (``runpy.run_path``) instead of shelling
    out to a second one. This removes the interpreter-resolution failure
    mode entirely — there is no longer a "no Python interpreter found on
    PATH" case, because no second interpreter is ever located or started.

    Negative-spec (POSIX mechanism) — interpreter-targeted ``execv`` was
    chosen over in-process ``runpy.run_path`` (the same primitive the
    Windows leg uses) for the POSIX leg too. Measured on one warm macOS
    box, 12 runs each, both orders, pessimistic reading: status quo
    ``os.execv(target_path, ...)`` 32.6ms; interpreter-targeted execv
    31.3ms; in-process 20.2ms. In-process was rejected despite being
    fastest because it abandons process identity and couples forwarder and
    target process state permanently — specifically, ``runpy.run_path``
    from a forwarder leaves the FORWARDER's directory at ``sys.path[0]``
    rather than the target's, breaking bare sibling imports that
    direct-script invocation handles. Interpreter-targeted execv runs the
    target as ``python target_path``, which CPython treats identically to
    today's shebang-invoked script for ``sys.path[0]``, ``sys.argv[0]``,
    ``__file__``, signal disposition, and traceback shape — this is why the
    POSIX leg does NOT collapse onto ``_run_target_in_process``.

    On a resolution failure, writes the distinct fail-loud message to
    stderr and exits 1 (matching the prior inline body's contract). On a
    missing (or unreadable — see the `os.access(os.R_OK)` pre-check below)
    *target* itself (partial install, mid-refresh tree, or a name-map entry
    pointing at a stale target), exits 127 (POSIX command-not-found
    convention) with a one-line remediation. Non-executable is no longer a
    127 case: the interpreter-targeted POSIX mechanism below runs the
    target as `python target_path`, not target_path directly, so the exec
    bit is never required.
    """
    if argv is None:
        argv = sys.argv[1:]

    try:
        bin_dir = resolve_claude_klabauter_bin_dir()
    except ClaudeKlabauterResolutionError as exc:
        sys.stderr.write(str(exc))
        sys.exit(1)

    target_path = bin_dir + "/" + target

    # Hoisted above the os.name branch (Review: code-reviewer F4 — was
    # byte-for-byte duplicated on both legs). Readability, not executability
    # (Review: code-reviewer F1) — the interpreter-targeted POSIX mechanism
    # below execs `sys.executable`, which always exists and is executable,
    # so `os.execv` itself no longer raises for an unreadable *target*; the
    # failure would otherwise surface only after process replacement, inside
    # the second interpreter's own `open()` of target_path, losing both the
    # 127 contract and the remediation message for exactly the
    # partial-install/mid-refresh scenario this check exists to catch. A
    # target can still change state between this check and the exec below
    # (TOCTOU) — that narrower window is accepted, not closed, and the
    # `except OSError` handler on the POSIX leg remains its backstop.
    if not os.path.isfile(target_path) or not os.access(target_path, os.R_OK):
        sys.stderr.write(
            f"ERROR: coordinator helper '{target_path}' is missing — "
            "re-run coordinator:install to repair the plugin tree\n"
        )
        sys.exit(127)

    if os.name == "nt":
        sys.exit(_run_target_in_process(target_path, argv))

    try:
        os.execv(sys.executable, [sys.executable, target_path, *argv])
    except OSError as exc:
        sys.stderr.write(
            f"ERROR: coordinator helper '{target_path}' is missing or not "
            f"executable ({exc.strerror}) — re-run coordinator:install to "
            "repair the plugin tree\n"
        )
        sys.exit(127)
