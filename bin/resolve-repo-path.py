# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""resolve-repo-path.py — emit the on-disk path for a registered repo shortname.

Port of: resolve-repo-path.sh (DoE a1a568d2, 2026-07-22) — naked-Python port,
2026-07-19 Windows de-bash campaign, chunk E3-c. Reads the machine-local [repos] registry for machine-portable
cross-repo path resolution.

Contract (unchanged from the bash oracle):
  1. `resolve-repo-path.py <shortname>` maps <shortname> to a registry key via
     s/-/_/g normalization (e.g. project-rag-ue-addon -> repos.project_rag_ue_addon)
     and emits the resolved on-disk path on stdout.
  2. `--wiki` flag makes it emit '<resolved-path>/docs/wiki' instead of the bare path.
     An optional `--docs-wiki <subpath>` flag overrides the appended subpath: when
     <subpath> is RELATIVE, emit '<resolved-path>/<subpath>' instead; when <subpath>
     is ABSOLUTE (leading `/`, or `~`-prefixed — home-relative values are
     machine-specific in intent and treated as absolute for this guarantee), WARN
     to stderr (required, not optional — order-independence guarantee) and fall
     back to the default '<resolved-path>/docs/wiki'.
  3. FAIL-LOUD-SKIP on unknown key: a shortname with NO matching repos.* key (or
     a key that resolves empty) emits NOTHING (empty stdout) and exits 0 — the
     caller SKIPS the unreachable/unregistered peer and reports it; never a silent
     mis-resolution.
  4. OSS-safe: when the machine-local registry is absent/empty entirely, degrade to
     empty + exit 0.
  5. Genuine internal errors (missing shortname argument, unknown flag) exit non-zero
     on stderr — distinct from the "no such key" skip-to-empty/exit-0 path.

Spec backlink: docs/plans/2026-06-19-portability-tracked-per-machine-config.md § C1
Spec backlink: docs/plans/2026-07-19-debash-coordinator-windows.md (Wave E3-c)
Reference impl: bin/learn-lessons-roots.py (same machine-local-derived, skip-absent,
  OSS-degradation pattern).
OSS requirement: works for any coordinator-claude installer with zero registered repos.

claude-central wiki exception (FOLLOW-UP, carried over from the bash oracle):
  As of this writing the machine-local registry exposes NO per-entry wiki-layout
  override key (probed: wiki_layout.*, repos.*.wiki, wiki.*, *.wiki_path — all
  absent), and `repos.claude_central` itself resolves empty on the authoring
  machine. So --wiki emits the default <path>/docs/wiki for every entry; when a
  claude-central entry with a divergent wiki layout is registered, add an
  override lookup here (e.g. `machine-local get wiki_layout.<key>`) before the
  default composition.

Negative-spec: does NOT spawn a shell (subprocess.run with an argv list, never a
  shell string) and does NOT swallow a genuine internal usage error into the
  skip-to-empty/exit-0 path.
"""
from __future__ import annotations

import os
import subprocess
import sys


_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_BOOTSTRAP_DONE = False


def _bootstrap_engine() -> None:
    """Put `_REPO_ROOT` on `sys.path` so the deferred `lib`/`coordinator_core.*`
    imports below resolve. Idempotent; safe to call more than once.

    What moved, and what did NOT: this single-line mutation used to run at
    MODULE scope, which made every import of this file mutate the `sys.path`
    of a warm server ~50 sessions share. The line is preserved exactly; only
    the trigger moved. No name is bound as a global here (every consumer does
    its own local import at its own call site), so there is nothing to
    publish and no `__getattr__` hook is needed.
    """
    global _BOOTSTRAP_DONE
    if _BOOTSTRAP_DONE:
        return
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)
    _BOOTSTRAP_DONE = True


def _machine_local_path_candidates() -> list[str]:
    """Candidate paths for the machine-local CLI, settings-home first
    (DR-210 Amendment 2026-07-24: "resolves nothing through ~/.claude/bin" —
    this rung previously offered the retired compat mirror as its ONLY
    candidate), extension-first on Windows within each base.

    The extensionless `bin/machine-local` path never resolves on Windows —
    there is no bare-name executable there, only a `.cmd` shim — so the
    isfile+X_OK guard below silently never fires and the wiki-layout override
    feature this backs is permanently dead on that platform with no
    diagnostic. Windows `.cmd`-first-per-base handling now lives in
    `machine_local_impl_resolve.windows_cmd_first_candidates()` (review:
    code-reviewer F2 — was hand-rolled here only, so the module's own
    `machine_local_bin_candidates()` silently diverged from this file).
    """
    _bootstrap_engine()
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from machine_local_impl_resolve import (
        claude_home as _mlir_claude_home,
        settings_home as _mlir_settings_home,
        windows_cmd_first_candidates as _mlir_windows_cmd_first_candidates,
    )

    bases = [
        os.path.join(_mlir_settings_home(), "bin", "machine-local"),
        os.path.join(_mlir_claude_home(), "bin", "machine-local"),
    ]
    return _mlir_windows_cmd_first_candidates(bases)


def _resolve_registry_value(key: str) -> str:
    """Call the machine-local CLI directly (its own shebang, no shell). Any
    failure (binary absent, non-zero exit, spawn error) degrades to empty —
    mirrors the bash oracle's `"$MACHINE_LOCAL" get "$KEY" 2>/dev/null || true`.
    A stderr breadcrumb is emitted when NO candidate resolves, so "feature
    silently inert" (the original Windows failure mode) becomes diagnosable
    instead of a silent empty-string skip.
    """
    _bootstrap_engine()
    from coordinator_core.win_portability import is_executable, no_console_creationflags

    ml = ""
    for cand in _machine_local_path_candidates():
        if os.path.isfile(cand) and is_executable(cand):
            ml = cand
            break
    if not ml:
        print(
            "resolve-repo-path.py: machine-local CLI not found "
            f"(tried: {', '.join(_machine_local_path_candidates())}) — "
            "wiki-layout override skipped",
            file=sys.stderr,
        )
        return ""
    try:
        result = subprocess.run(
            [ml, "get", key],
            capture_output=True,
            text=True,
            **no_console_creationflags(),
        )
    except OSError:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _parse_args(argv: list[str]) -> tuple[bool, str, str]:
    """Returns (wiki, docs_wiki, shortname). Raises _UsageError on a genuine
    internal/usage error (distinct from the skip-to-empty/exit-0 path)."""
    wiki = False
    docs_wiki = ""
    shortname = ""
    positional_done = False

    i = 0
    while i < len(argv):
        tok = argv[i]
        if not positional_done and tok == "--":
            positional_done = True
            i += 1
            continue
        if not positional_done and tok == "--wiki":
            wiki = True
            i += 1
            continue
        if not positional_done and tok == "--docs-wiki":
            if i + 1 >= len(argv):
                raise _UsageError("--docs-wiki requires a value")
            val = argv[i + 1]
            # Review parity (F1): reject a flag-like next token so --docs-wiki
            # never silently swallows a real flag (e.g. --wiki) as its value.
            if val.startswith("-"):
                raise _UsageError(
                    f"--docs-wiki requires a value, got flag-like '{val}'"
                )
            docs_wiki = val
            i += 2
            continue
        if not positional_done and tok.startswith("-") and tok != "-":
            raise _UsageError(f"unknown flag: {tok}")
        if shortname:
            raise _UsageError(f"unexpected extra argument: {tok}")
        shortname = tok
        i += 1

    return wiki, docs_wiki, shortname


class _UsageError(Exception):
    pass


def main(argv: list[str]) -> int:
    _bootstrap_engine()
    try:
        wiki, docs_wiki, shortname = _parse_args(argv[1:])
    except _UsageError as exc:
        print(f"resolve-repo-path.py: {exc}", file=sys.stderr)
        return 2

    if not shortname:
        print(
            "resolve-repo-path.py: missing required <shortname> argument",
            file=sys.stderr,
        )
        print(
            "  usage: resolve-repo-path.py [--wiki] [--docs-wiki <subpath>] [--] <shortname>",
            file=sys.stderr,
        )
        return 2

    normalized = shortname.replace("-", "_")
    key = f"repos.{normalized}"
    resolved = _resolve_registry_value(key)

    # FAIL-LOUD-SKIP: no such key (or key resolves empty) -> empty stdout, exit 0.
    if not resolved:
        return 0

    if wiki:
        if docs_wiki:
            if docs_wiki.startswith("/") or docs_wiki.startswith("~"):
                print(
                    f"resolve-repo-path.py: WARNING: docs_wiki value '{docs_wiki}' "
                    "is absolute; falling back to default docs/wiki (relative "
                    "subpath required)",
                    file=sys.stderr,
                )
                print(f"{resolved}/docs/wiki")
            else:
                print(f"{resolved}/{docs_wiki}")
        else:
            print(f"{resolved}/docs/wiki")
    else:
        if docs_wiki:
            print(
                f"resolve-repo-path.py: WARNING: --docs-wiki '{docs_wiki}' "
                "ignored because --wiki was not passed",
                file=sys.stderr,
            )
        print(resolved)

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
