# percolate-liveops-preflight — CLI trampoline over claude-klabauter
# coordinator_core.session.{liveness,peer_roster} and
# coordinator_core.machine_resolver, answering the operator's actual
# question before a percolation/publish run: "will this affect any live
# ops?" A REPORT, not a gate — see the module docstring below for the full
# rationale and the negative-spec this deliberately does not violate.
#
# Subcommands (argv[0]; no argv means "run"):
#   run | (no args)        -> census every repo the machine-local registry
#                              knows about (`repos.*`), list each repo's
#                              live sessions (`coordinator_core.session.
#                              liveness`), classify each as affected/
#                              unaffected by resolving whether that repo's
#                              path IS the engine's own resolved source tree
#                              (`_resolve_claude_klabauter.py::_resolve_claude_klabauter_root` --
#                              the same structural check the resolver's own
#                              gate makes; unaffected -- resolves its own
#                              tree by construction) or falls through to the
#                              published engine (affected), and emit a
#                              plain-text report plus the verdict line
#                              "affects N of M live sessions."
#
# Exit codes: 0 on a successful report (REGARDLESS of the N/M verdict --
# this is a report, never a gate; see NEGATIVE SPEC below). 3
# (_TRANSPORT_FAIL) when the engine root cannot be resolved or the wrapped
# coordinator_core.session modules are not importable -- "the engine could
# not be reached," same convention as session-liveness-cli /
# session-reachability-cli. A usage error (unknown subcommand) exits 2.
#
# Spec backlink: docs/plans/2026-08-15-klabauter-release-channels.md, chunk
# C11.
"""percolate-liveops-preflight — answers "will this percolation affect any
live ops?" as a REPORT, not a gate (PM, 2026-08-15, reproduced verbatim in
the plan chunk this ships against): "we do percolation and publishing
basically by ourselves, when the rest of the box is quiet, so we don't
fuck up ongoing things ... that can be something that I remember as a
human, but we can include it in preflight for the percolate skill."

WHAT IT DOES: for every repo the machine-local registry knows about
(`repos.*`), lists that repo's currently-live coordinator sessions
(`coordinator_core.session.liveness.active_sessions` /
`live_session_ids`), and classifies each live session as AFFECTED or
UNAFFECTED by a claude-klabauter engine percolation/publish:

  - UNAFFECTED: the session's repo IS the engine's own resolved source tree
    (same structural check `_resolve_claude_klabauter.py::resolve_claude_klabauter_root_with_class`
    makes, 2026-08-18 C4 -- not per-repo `engine.working_repos.*` membership,
    retired as the discriminant) -- it resolves ITS OWN tree, not the
    published mirror, so a mirror publish cannot touch what that session
    sees, by construction.
  - AFFECTED: every other repo with a live session -- it falls through to
    the published engine, so a publish changes what that session's next
    engine-touching op resolves.

Where a session is addressable (`coordinator_core.session.peer_roster`,
same read surface `session-reachability-cli` wraps), its address is
printed alongside it, so the operator can ask before publishing rather
than guess -- the PM's second half of the same point ("we have a nice new
census tool for seeing which Claude sessions are alive, and talk to
them").

NEGATIVE SPEC (hard boundary, not a detail): this is NOT a quiescence
threshold and NEVER exits non-zero on a nonzero verdict. This box averages
50-70 active LLMs (CLAUDE.md's machine-load-norm) -- a zero-peers gate
would never pass here and would train reflexive overriding, a nag rather
than a guard. The tool leads with the answer and lets the operator act on
it. "affects 0 of N" is a CORRECT, unremarkable output on a machine where
every registered repo happens to be engine-working today -- not a bug in
this tool, and deliberately not special-cased to read as more interesting
than it is.

Zero-spawn is NOT required (operator-invoked, not the boot path) -- this
does spawn `git rev-parse` per candidate repo (session hub resolution),
same as any other `coordinator_core.session.liveness` caller.

Wiring this into `coordinator:percolate`'s skill preflight is a
sibling-repo edit (skills are discovery-resolved surfaces owned by that
repo, out of scope here) -- this chunk ships the runnable and its contract
only.
"""
# Review: coordinatorcode-reviewer-eb287fb6 — `from __future__ import
# annotations` was placed before this docstring, demoting the string to a
# dead expression statement that never became `__doc__`. Moved below the
# docstring so it registers.
from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root, require_dispatch_engine_on_path  # noqa: E402

# Same seam `resolve_claude_klabauter_root_with_class()` uses to determine the ONE
# engine source tree (C4, 2026-08-18) — imported directly rather than
# re-deriving the discriminant against `engine.working_repos.*` a second
# time (the exact duplication C4 exists to kill; see that module's
# `_is_claude_klabauter_source_tree` docstring for why a structural comparison
# replaced the retired per-repo exemption family).
_RESOLVE_CLAUDE_KLABAUTER_LIB_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "lib", "resolve-claude-klabauter"
)
if _RESOLVE_CLAUDE_KLABAUTER_LIB_DIR not in sys.path:
    sys.path.insert(0, _RESOLVE_CLAUDE_KLABAUTER_LIB_DIR)
from _resolve_claude_klabauter import (  # noqa: E402
    ClaudeKlabauterResolutionError,
    _ml_dir as _claude_klabauter_ml_dir,
    _resolve_claude_klabauter_root as _resolve_claude_klabauter_source_root,
)

_TRANSPORT_FAIL = 3

_HELP_FLAGS = ("--help", "-h", "help")
_SUBCOMMANDS = "subcommands: run (default when no args)"


def _import_modules():
    claude_klabauter_root = require_dispatch_engine_on_path()
    import coordinator_core.session.liveness as liveness_mod
    import coordinator_core.session.peer_roster as peer_roster_mod
    import coordinator_core.machine_resolver as machine_resolver_mod

    return liveness_mod, peer_roster_mod, machine_resolver_mod


def _usage(prog: str) -> int:
    print(f"usage: {prog} [run]\n{_SUBCOMMANDS}", file=sys.stderr)
    return 2


def _normalize_path(path: str) -> str:
    """Same containment-safe normalization `peer_roster._normalize_path`
    uses (realpath + normpath + normcase) — comparing a registry-declared
    repo path against another registry-declared repo path needs the exact
    same cross-platform-correct treatment that module already applies to
    cwd-vs-repo_root; not re-derived, mirrored for the same reason (Windows
    is first-class, path casing/symlinks must not silently misclassify a
    working-tree repo as a mirror consumer or vice versa)."""
    return os.path.normcase(os.path.normpath(os.path.realpath(path)))


def _load_registry_prefix(machine_resolver_mod, prefix: str) -> "dict[str, str]":
    """Merge `registry.toml` (tracked baseline) then `registry.local.toml`
    (per-machine, wins on collision — same precedence order
    `machine_resolver.registry_get` documents) and return every key under
    `prefix` with the prefix stripped, value as a plain string. Reads both
    files directly via the module's own `load_flat_registry_file` (no
    second TOML parser, no `machine-local` subprocess — same
    reset-survival rationale `registry_get`'s docstring gives)."""
    reg_dir = machine_resolver_mod.registry_dir()
    merged: "dict[str, str]" = {}
    for fname in ("registry.toml", "registry.local.toml"):
        flat = machine_resolver_mod.load_flat_registry_file(reg_dir / fname)
        for key, val in flat.items():
            if not key.startswith(prefix):
                continue
            if val is None or str(val) == "":
                continue
            merged[key[len(prefix):]] = str(val)
    return merged


def _repo_display_name(name: str, path: str) -> str:
    return f"{name} ({path})"


def _build_id_to_address(peer_roster_mod, repo_path: str) -> "dict[str, str]":
    """Best-effort session-id -> address map for one repo, via
    `peer_roster.build_roster` (the same read surface
    `session-reachability-cli peer-roster` wraps). Never raises out to the
    caller -- a roster read failure degrades to "no addresses known for
    this repo" (an addressing gap, not a reason to fail the whole report)."""
    try:
        rows = peer_roster_mod.build_roster(repo_path, raise_on_failure=False)
    except Exception:
        return {}
    out: "dict[str, str]" = {}
    for row in rows:
        if row.address:
            out[row.session_id] = row.address
    return out


def _run(liveness_mod, peer_roster_mod, machine_resolver_mod) -> int:
    repos = _load_registry_prefix(machine_resolver_mod, "repos.")

    # The ONE path that IS the engine's own live source tree — same
    # structural comparison `_resolve_claude_klabauter.py::_is_claude_klabauter_source_tree`
    # makes, not a scan over `engine.working_repos.*` (C4 retired that as
    # the resolution-class discriminant; the key survives elsewhere as a
    # pure locator, but is no longer this question's input). `None` means
    # undeterminable (no live source tree resolves on this box at all) --
    # every repo then classifies AFFECTED, since nothing resolves the live
    # tree for anyone to be unaffected via.
    try:
        source_tree_path = _normalize_path(
            _resolve_claude_klabauter_source_root(_claude_klabauter_ml_dir())
        )
    except ClaudeKlabauterResolutionError:
        source_tree_path = None

    # Always consider the repo this preflight is invoked from, even if it
    # has no `repos.*` registry entry of its own (a fresh/unregistered
    # checkout should not silently vanish from its own census).
    here = os.getcwd()
    candidates: "dict[str, str]" = dict(repos)
    candidates.setdefault("_this_repo", here)

    # `repos.*` is a many-names-per-path registry (aliases, legacy keys,
    # and the always-added "_this_repo" entry can all name the SAME
    # on-disk path -- e.g. `repos.claude_klabauter` and `_this_repo` here).
    # Census by physical repo, once each -- counting the same live session
    # twice under two aliases would silently inflate both N and M in the
    # verdict line. Preferred name is the FIRST (sorted) REAL registry
    # alias naming that path; the synthetic "_this_repo" placeholder wins
    # only when it is the sole name for that path, so the operator-facing
    # report shows a real registered repo name over the placeholder
    # whenever one exists.
    # Review: coordinatorcode-reviewer-eb287fb6 -- sorting "_this_repo"
    # (leading '_') ahead of lowercase alias names displaced a real
    # registry alias in the report; fixed to prefer real aliases.
    groups: "dict[str, list[str]]" = {}
    for name in candidates:
        norm = _normalize_path(candidates[name])
        groups.setdefault(norm, []).append(name)
    by_path: "dict[str, str]" = {}
    for norm, names in groups.items():
        real_names = sorted(n for n in names if n != "_this_repo")
        by_path[norm] = real_names[0] if real_names else "_this_repo"
    deduped = {name: candidates[name] for norm, name in by_path.items()}

    total_live = 0
    total_affected = 0
    report_lines: "list[str]" = []

    for name in sorted(deduped):
        path = deduped[name]
        if not os.path.isdir(path):
            continue
        live_ids = sorted(liveness_mod.live_session_ids(cwd=path))
        if not live_ids:
            continue
        lines_by_id = {}
        for line in liveness_mod.active_sessions(cwd=path):
            sid = line.split(None, 1)[0] if line else ""
            if sid in live_ids:
                lines_by_id[sid] = line

        is_working = source_tree_path is not None and _normalize_path(path) == source_tree_path
        affected_here = not is_working
        id_to_address = _build_id_to_address(peer_roster_mod, path)

        engine_state = "engine-working (unaffected)" if is_working else "published-engine (AFFECTED)"
        report_lines.append(f"{_repo_display_name(name, path)} -- {engine_state}")
        for sid in live_ids:
            total_live += 1
            if affected_here:
                total_affected += 1
            address = id_to_address.get(sid)
            addr_text = f"address={address}" if address else "address=not addressable"
            detail = lines_by_id.get(sid, sid)
            marker = "AFFECTED" if affected_here else "unaffected"
            report_lines.append(f"  [{marker}] {detail}  {addr_text}")

    if not report_lines:
        report_lines.append("(no live sessions found in any registered repo)")

    print("\n".join(report_lines))
    print(f"verdict: affects {total_affected} of {total_live} live sessions.")
    return 0


def main(argv: list[str]) -> int:
    subcmd = argv[0] if argv else "run"

    if subcmd in _HELP_FLAGS:
        print(f"usage: percolate-liveops-preflight [run]\n{_SUBCOMMANDS}")
        return 0

    if subcmd != "run":
        return _usage("percolate-liveops-preflight")

    try:
        liveness_mod, peer_roster_mod, machine_resolver_mod = _import_modules()
    except RuntimeError as exc:
        print(f"percolate-liveops-preflight: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL
    except ImportError as exc:
        print(f"percolate-liveops-preflight: coordinator_core.session modules not importable: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL

    return _run(liveness_mod, peer_roster_mod, machine_resolver_mod)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
