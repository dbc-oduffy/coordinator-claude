"""engine_bootstrap — the DISPATCH-axis engine-root resolver, split out of cc_invoke.

Purpose: `import cc_invoke` cost 27 modules over a bare site-enabled interpreter
to perform a bootstrap whose job is `os.path.join` plus `open()` on the common
(rung 1.5, pointer-file) path. This SIBLING module under `coordinator/bin/lib/`
carries `_resolve_engine_root` (plus its nested `_delegate_to_gate`) and the
helpers that resolver needs, module-top-import-free except `os`/`sys` — every
other stdlib name it needs (`hashlib`, `importlib.util`, `re`, `subprocess`,
`pathlib.Path`, `typing.cast`) is imported function-local, so a caller that
only reaches rung 1/1.5 (env var / pointer file) never pays for the rest of
the ladder's rarely-exercised rungs (env-var candidate delegation, registry
subprocess read, foreign-tree gate load).

Spec backlink: docs/plans/2026-08-21-the-cli-bootstrap-tax-dies-at-the-interpreter-floor.md § C2.

THE FOUR CONDITIONS THIS MODULE'S SHAPE SATISFIES (see the C2 chunk body for
the full text; restated here because a reader of THIS file, not the plan, is
the one who can break them by editing in isolation):
  (a) this module is a SIBLING under coordinator/bin/lib/, never inside
      coordinator_core — it resolves the engine root, so it cannot itself
      depend on the thing it is locating.
  (b) `_resolve_engine_root` and its nested `_delegate_to_gate` are ONE
      function object, defined here and re-exported from cc_invoke.py by a
      PLAIN NAME ALIAS (`_resolve_claude_klabauter_root = _resolve_engine_root`), never
      wrapped in another function — a wrapper would give the alias a
      DIFFERENT `__globals__`/identity than the real resolver, which is
      exactly the binding this split must not disturb.
  (c) every INTERNAL caller inside cc_invoke.py (route(), _should_pass_repo(),
      require_dispatch_engine_on_path(), resolve_engine_root(), etc.) keeps
      spelling the call `_resolve_claude_klabauter_root()` — a bare name resolved
      against cc_invoke's OWN globals at call time, populated by the `from
      engine_bootstrap import ...` line near the top of that file.
  (d) THE INTERNAL CALLERS STAY IN cc_invoke.py, not here. `require_dispatch_engine_on_path`
      (and every other `*_on_path` wrapper, and `route()`) is deliberately NOT
      moved alongside the resolver: moving it would rebind its bare-name
      lookups against THIS module's globals instead of cc_invoke's, turning
      every `unittest.mock.patch.object(cc_invoke, "_resolve_claude_klabauter_root")` /
      `patch.object(cc_invoke, "_seam_present")` site into a silent no-op —
      no error, the real resolver runs against real machine state. `_seam_present`
      is co-patched with `_resolve_claude_klabauter_root` at ~13 sites and is NOT moved
      here for the same reason, even though it could stand alone.

Negative-spec:
    - Does NOT import coordinator_core, or anything from it, at module top —
      that is the whole point of the split (this module LOCATES coordinator_core,
      so it cannot need it already importable to run).
    - Does NOT duplicate `child_env` or `_settings_home_env` — those stay
      owned by cc_invoke.py (used far beyond this resolver) and are reached here, when
      genuinely needed (the registry-subprocess rung only), via a function-local
      `import cc_invoke`, safe because that rung only fires after a caller has
      already triggered this module's import path, by which point cc_invoke
      itself is either already loaded or loads without issue.
    - Does NOT change rung order, remediation text, or any observable behavior
      of `_resolve_engine_root` relative to its pre-split form in cc_invoke.py.
"""
from __future__ import annotations

import os
import sys

# ---------------------------------------------------------------------------
# Engine-root resolution constants/exceptions — moved alongside the resolver
# that owns them because `_resolve_engine_root`'s bare-name references to
# these bind against THIS module's globals once the function lives here.
# cc_invoke.py imports these back (see its own module-top import block) so
# its OTHER functions (route(), engine_source_root(), _state1_remediation_message(),
# etc.) that also reference them keep resolving through cc_invoke's own
# globals unchanged.
# ---------------------------------------------------------------------------

# Cross-reference: coordinator_core/engine_root.py defines this same literal
# (plan pln-the-ceremony-tail-stops-lying-b58fb3 AC3b). The two rungs sit on
# opposite sides of a declared one-way no-import boundary and cannot share a
# symbol; the constant is duplicated deliberately and each side asserts the literal.
_REGISTRY_READ_TIMEOUT_TOKEN = "machine-local registry read timed out"

_ENGINE_ROOT_NEW_VAR = "COORDINATOR_ENGINE_ROOT"

_MACHINE_LOCAL_READ_TIMEOUT_SECS = 10  # bound on the subprocess.run() call below


class _RegistryReadTimeout(RuntimeError):
    """A machine-local registry subprocess read exceeded its bound.

    Distinct from `is_timeout_error`'s IPC-engine-timeout contract: that predicate
    matches only `_TIMEOUT_MESSAGE_PREFIX`-prefixed messages from the
    cc_invoke()/cc_invoke_bare() transport layer (an engine timeout). This is a
    resolver-rung subprocess timeout — `_machine_local_get` raises nothing wrong
    happened at the engine, only that the registry read itself did not return in
    time. Raised by `_machine_local_get`, caught and re-raised (or absorbed) by
    `_resolve_engine_root`, and threaded through `route()` to
    `_state1_remediation_message` as a named outcome (AC3) — never conflated with
    the IPC-timeout prefix/discriminator above.
    """


_CLAUDE_KLABAUTER_ROOT_REMEDIATION = (
    "cc_invoke: cannot resolve the engine root — repos.claude_klabauter is not set.\n"
    "  The machine-local registry has no 'repos.claude_klabauter' entry on this machine.\n"
    "  Remediate (choose one):\n"
    "    machine-local set repos.claude_klabauter /path/to/claude-klabauter\n"
    "    Re-run /coordinator:install to populate the repos.* registry entries.\n"
    "  Reference: plugins/coordinator/docs/wiki/machine-local-registry.md §4c"
)

# Back-compat alias, same shape as `cc_invoke._resolve_claude_klabauter_root`
# (C17, docs/plans/2026-08-20-an-engine-root-is-not-named-for-the-repo.md): a
# published CLI puts this LIVE (untransformed) module on sys.path but imports
# it under the TRANSFORMED name, since the published tree's own cc_invoke.py
# re-exports `_CLAUDE_KLABAUTER_ROOT_REMEDIATION` as `_CLAUDE_KLABAUTER_ROOT_REMEDIATION`
# post-transform. Exporting both spellings here closes that cross-tree seam
# without touching the mirror.
_CLAUDE_KLABAUTER_ROOT_REMEDIATION = _CLAUDE_KLABAUTER_ROOT_REMEDIATION

# The engine-root module's own basename and entry-point name both carry the
# repo token (`claude_klabauter_root.py` / `coordinator_claude_klabauter_root_with_class`), and the
# publish transform rewrites that token throughout — so the mirror spells them
# `claude_klabauter_root.py` / `coordinator_claude_klabauter_root_with_class`.
# This pattern is deliberately token-FREE, which makes it the one spelling
# that survives the transform byte-identically in both trees. Do not "fix" it
# to name the module directly; that is the defect, not the style.
#
# Compiled lazily inside `_load_foreign_gate_entry_point` (not here at module
# top) — `re` is not on this module's os+sys-only import budget, and this
# pattern is only ever consulted on the rare foreign-tree rung.
_GATE_ENTRY_POINT_PATTERN = r"^def (coordinator_\w+_root_with_class)\s*\("


_MLIR_MODULE = None


def _machine_local_impl_resolver():
    """Lazily import machine_local_impl_resolve, self-locating its own
    sys.path entry so this module stays standalone-invocable regardless of
    whether a caller already inserted coordinator/bin/lib. Cached after first
    call.

    Moved here from cc_invoke.py alongside `_machine_local_get` (its sole
    resolver-ladder caller); `cc_invoke._machine_local_get_in_process` reaches
    this same function via its own `from engine_bootstrap import
    _machine_local_impl_resolver` — one resolver, two callers, unchanged from
    the pre-split shape.
    """
    global _MLIR_MODULE
    if _MLIR_MODULE is None:
        _lib_dir = os.path.dirname(os.path.abspath(__file__))
        if _lib_dir not in sys.path:
            sys.path.insert(0, _lib_dir)
        import machine_local_impl_resolve as _mlir

        _MLIR_MODULE = _mlir
    return _MLIR_MODULE


def _machine_local_get(key: str) -> str | None:
    """Read a machine-local registry key via a direct sys.executable subprocess.

    Native Python replacement for the bash `machine-local` forwarder: invokes
    bin/_machine_local.py (the real reader) directly with the same interpreter
    that loaded this module — no shell, no bash. Mirrors
    gen-claude-klabauter-root-pointer.py::_machine_local_get and
    coordinator_core.engine_root.coordinator_engine_root's own rung-2 lookup.

    Returns the resolved value, or None on any failure (missing impl, non-zero
    exit, empty stdout) — a registry miss is a normal fallback state here, not
    an error; the caller decides whether that's terminal.

    The one exception: a `subprocess.TimeoutExpired` on the registry-read bound
    raises `_RegistryReadTimeout` instead of collapsing to `None`. A busy box
    timing out a subprocess-bounded registry read is not the same fact as the
    key genuinely being absent, and collapsing the two here is what let the
    operator-facing ladder tell a transient reader timeout apart from a broken
    install (see `_resolve_engine_root` / `cc_invoke._state1_remediation_message`).

    Settings-home first (DR-210 Amendment 2026-07-24): resolves via
    machine_local_impl_resolve.machine_local_impl_path(env_override=None) —
    `env_override=None` preserves this function's pre-existing contract of
    never honouring a MACHINE_LOCAL_IMPL test-isolation override (it never
    did before this precedence fix, and gaining that side effect here would be
    an unrelated behavior change).

    `env=` for the spawn is built via a function-local `import cc_invoke` —
    `child_env()` (settings-home propagation) stays owned by cc_invoke.py
    (used far beyond this resolver);
    this is the one rung of the ladder that genuinely needs it, and by the
    time this rung fires cc_invoke has always already started importing this
    module, so the lazy import is never a fresh 27-module tax paid twice.
    """
    impl = _machine_local_impl_resolver().machine_local_impl_path(env_override=None)
    if not os.path.isfile(impl):
        return None
    import subprocess

    import cc_invoke as _cc_invoke

    try:
        result = subprocess.run(
            [sys.executable, impl, "get", key],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=_MACHINE_LOCAL_READ_TIMEOUT_SECS,
            env=_cc_invoke.child_env(),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        raise _RegistryReadTimeout(
            f"{_REGISTRY_READ_TIMEOUT_TOKEN} ({_MACHINE_LOCAL_READ_TIMEOUT_SECS}s bound, "
            f"key={key!r})"
        ) from None
    except OSError:
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.strip()


def _normalised_root(path: str) -> str:
    """Resolve symlinks and case-fold (Windows only) for root COMPARISON and
    for deriving the candidate-unique synthetic-module key below.

    Two spellings of one root must normalise identically; two distinct roots
    must not collide. Used by both `_is_same_tree_as_canonical` (comparison)
    and `_load_foreign_gate_entry_point` (key derivation) so the two never
    disagree about what counts as "the same root".
    """
    resolved = os.path.realpath(path)
    if os.name == "nt":
        resolved = resolved.casefold()
    return resolved


def _is_same_tree_as_canonical(candidate: str) -> bool:
    """True when `candidate` is the SAME root `coordinator_core` is already
    cached from (or nothing is cached yet — no cache to collide with).

    Spec backlink: docs/plans/2026-08-20-an-engine-root-is-not-named-for-the-repo.md § C0.
    This is the disambiguate-by-ROOT check `_delegate_to_gate` uses to decide
    between the ordinary `importlib.import_module` short-circuit (same tree —
    must stay byte-identical to the pre-C0 behaviour) and the foreign-
    candidate file-path load below (genuinely a different root).

    `coordinator_core` not yet in `sys.modules`, or cached with no
    `__file__` (a namespace-package edge case), or an unreadable path along
    the way: treated as "same tree" — there is no cache to collide with, so
    the ordinary import is safe and correct either way.
    """
    canonical = sys.modules.get("coordinator_core")
    if canonical is None:
        return True
    canonical_file = getattr(canonical, "__file__", None)
    if not canonical_file:
        return True
    from pathlib import Path

    try:
        canonical_root = _normalised_root(str(Path(canonical_file).resolve().parents[1]))
        candidate_root = _normalised_root(candidate)
    except OSError:
        return True
    return canonical_root == candidate_root


def _load_foreign_gate_entry_point(candidate: str):
    """Load `candidate`'s engine-root gate entry point BY FILE PATH, under a
    candidate-unique `sys.modules` key — for a candidate proven (by
    `_is_same_tree_as_canonical`) to be a genuinely DIFFERENT root than the
    one `coordinator_core` is already cached from.

    Spec backlink: docs/plans/2026-08-20-an-engine-root-is-not-named-for-the-repo.md § C0.

    LOCATING THE FILE — direct path only. Tries
    `<candidate>/coordinator_core/engine_root.py`, the spelling both this
    tree and the published mirror have converged on (asserted at dispatch
    time in C19's close-out). The shape-scan fallback that once covered the
    pre-convergence / mixed-mirror transition window was retired in C19,
    docs/plans/2026-08-20-an-engine-root-is-not-named-for-the-repo.md.

    KNOWN AND ACCEPTED LIMIT (stated, not silently overclaimed): the loaded
    module still resolves any cross-package import (e.g.
    `from coordinator_core._settings_home import machine_local_dir`) through
    the CACHED `coordinator_core` package (root A), not candidate root B's
    own copy. Harmless today because the only such import is settings-home
    (machine state, not tree state) and `_SHIM_PATH` — the vector that
    actually mattered — derives from this module's own real `__file__`, so it
    is correctly per-root regardless. See `_resolve_engine_root`'s "KNOWN AND
    ACCEPTED LIMIT" docstring note for the caller-facing version of this pin.

    Returns None when `candidate` has no locatable engine-root module (a
    marker-only or broken checkout) — the caller turns that into the same
    RuntimeError it always raised on a same-tree miss.
    """
    module_path = os.path.join(candidate, "coordinator_core", "engine_root.py")
    if not os.path.isfile(module_path):
        return None

    try:
        with open(module_path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return None

    import re

    match = re.search(_GATE_ENTRY_POINT_PATTERN, text, re.MULTILINE)
    if match is None:
        return None
    entry_name = match.group(1)

    import hashlib
    import importlib.util

    digest = hashlib.sha1(_normalised_root(candidate).encode("utf-8")).hexdigest()[:16]
    synthetic_name = f"_cc_engine_root_{digest}"

    spec = importlib.util.spec_from_file_location(synthetic_name, module_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[synthetic_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        # Deliberately broader than ImportError. A candidate whose module
        # matches by path but raises on load (partial checkout, mid-publish
        # state) is a BROKEN candidate, not this loader's problem to
        # re-raise.
        sys.modules.pop(synthetic_name, None)
        return None
    found = getattr(module, entry_name, None)
    if callable(found):
        from typing import cast, Callable, Tuple

        return cast("Callable[[], Tuple[str, str]]", found)
    return None


def _claude_klabauter_root_gate_empty_remediation(candidate: str, *, source: str) -> str:
    """Remediation text for a candidate that imported ``coordinator_core.engine_root``
    but whose gated resolver still returned a falsy root.

    Review: engine-root-slice-2 finding 1 — the un-parameterized
    ``_CLAUDE_KLABAUTER_ROOT_REMEDIATION`` told every rung (env, registry, self-location)
    to run `machine-local set repos.claude_klabauter`, which is only the right
    instruction for Rung 2 (the case that text was written for). A bogus
    `COORDINATOR_ENGINE_ROOT` (Rung 1) or an unimportable/unstamped self-located checkout
    (Rung 3) needs a remedy naming the candidate/source that actually failed,
    not a registry-set instruction unrelated to their problem.
    """
    if source == "machine-local repos.claude_klabauter":
        return _CLAUDE_KLABAUTER_ROOT_REMEDIATION
    # foreign-identity: SUBJECT — remedy names the candidate/checkout the reader must
    # confirm or register (machine-local set repos.claude_klabauter); the name is the fix.
    return (
        f"cc_invoke: cannot resolve the engine root — candidate {candidate!r} (from {source}) "
        "imported coordinator_core.engine_root but the gated ladder returned no root.\n"
        "  Remediate (choose one):\n"
        f"    Confirm {candidate!r} is a genuine, stamped claude-klabauter checkout.\n"
        "    machine-local set repos.claude_klabauter /path/to/claude-klabauter\n"
        "    Re-run /coordinator:install to populate the repos.* registry entries.\n"
        "  Reference: plugins/coordinator/docs/wiki/machine-local-registry.md §4c"
    )


def _walk_up_to_checkout(script_file: str) -> str | None:
    """Walk up from ``script_file`` to the nearest enclosing engine checkout.

    Depth-agnostic sibling of ``cc_invoke.resolve_colocated_claude_klabauter_root``'s fixed
    ``parents[2]`` probe, using the same two-marker test (``coordinator_core/``
    directory AND ``pyproject.toml`` file). The fixed-depth form is correct only
    for scripts at ``coordinator/bin/X.py``; a helper module one level deeper at
    ``coordinator/bin/lib/X.py`` lands on ``coordinator/`` and silently misses.
    Walking removes the depth coupling, so a co-located caller resolves its own
    checkout regardless of where in the tree it sits.

    Returns None when no ancestor probes as a checkout (published/vendored
    outside any engine tree) — callers fall through to the registry ladder.

    Each ancestor's probe is individually guarded against OSError
    (``.is_dir()``/``.is_file()`` can raise on a broken Windows junction, a
    symlink loop, or a permission-denied parent): an unreadable ancestor is
    skipped rather than aborting the whole walk, so one bad link in the chain
    doesn't hide a real checkout further up.
    """
    from pathlib import Path

    try:
        parents = list(Path(script_file).resolve().parents)
    except OSError:
        return None
    for candidate in parents:
        try:
            if (candidate / "coordinator_core").is_dir() and (candidate / "pyproject.toml").is_file():
                return str(candidate)
        except OSError:
            continue
    return None


def _resolve_engine_root(caller_file: str | None = None) -> str:
    """Resolve the engine root natively — no bash subprocess anywhere in the ladder.

    Resolution order (mirrors coordinator_core.engine_root.coordinator_engine_root,
    the native port of coordinator-claude-klabauter-root.sh):
      Rung 1:   COORDINATOR_ENGINE_ROOT already set in environment → CANDIDATE, delegated
                through the single gated ladder (see "DELEGATION" below) rather
                than answered directly.
      Rung 1.5: machine-local pointer files → cheap direct file reads, no
                subprocess spawn (docs/plans/2026-07-14-claude-klabauter-windows-
                portability.md § C1). `.claude-klabauter-root` is consulted
                FIRST and wins outright (DR-326: all engine dispatch goes to the
                published build); `.claude-klabauter-root` answers only on a box with no
                published mirror installed. Both remain a DIRECT return, not a
                delegation — see the "no longer gate-blind in the direction
                that mattered" note below for why that is safe.
      Rung 2:   machine-local registry candidate → delegated, same as Rung 1.
      Rung 3:   terminal self-location (__file__) → CANDIDATE, delegated the
                same way — see "DISPATCH axis" note below.

      DELEGATION (docs/plans/2026-08-19-an-engine-root-is-a-stamped-build.md §
      C6): Rungs 1, 2, and 3 no longer ANSWER the dispatch question themselves.
      Each only supplies a CANDIDATE path capable of importing
      coordinator_core; the nested `_delegate_to_gate()` helper bootstraps that import
      and hands the actual decision to
      ``coordinator_core.engine_root.coordinator_engine_root_with_class()``
      (the DR-132/stamp-gated ladder C5 rewrote) — the single place that
      answers "which engine executes?" for every caller. A candidate that
      cannot import ``coordinator_core.engine_root`` (a marker-only or broken
      checkout) raises, rather than being trusted verbatim.

      DISPATCH axis vs LOCATOR axis: this function answers the DISPATCH
      question ("which engine executes?"), consumed by `route()`/`cc_invoke()`.
      `cc_invoke.resolve_colocated_claude_klabauter_root()` and `cc_invoke.resolve_engine_root()`
      answer a DIFFERENT question — "where is THIS co-located script's own
      tree, for sys.path purposes?" — and deliberately keep their own,
      undelegated rung orderings (self-location-before-env, or
      isdir-gated-env-before-self-location respectively). Do not collapse
      those into this function or vice versa; the two axes are allowed to
      disagree.

      PUBLISHED-ENGINE GATE COVERAGE, stated honestly: only Rungs 1, 2, and 3
      now reach the gate, via delegation. Rung 1.5 (pointer files) is the sole
      remaining direct return — the note below explains why that is not a
      gate-blind hole in practice.

      Rung 1.5 USED to be the live end of that blindness, and was the exact
      defect commit 0fdfb61d6 fixed inside `coordinator_engine_root_with_class()`
      itself — the pointer file pre-empting the DR-132 gate on every installed
      machine. That fix landed in the two-tier wrapper but did NOT reach this
      rung, so on a dual-boot box `cc_invoke` answered the live checkout's own drive-rooted path from
      every cwd, INCLUDING one where the gate itself would have said
      `claude-klabauter` (measured 2026-08-19, all four caller locations). Every
      engine invocation on such a box therefore ran the live working tree, whose
      warm generation token rotates on any commit by any session — the moving
      target DR-326 exists to stop.

      Resolved WITHOUT breaking the constraint that caused it: the published
      pointer is one more plain `open()`, so rung 1.5 still spawns no
      subprocess and still walks no gate — it is no longer gate-blind in the
      direction that mattered, because the answer it gives is the one the gate
      would have given (HARD CONSTRAINT preserved: no new subprocess on rungs
      1/1.5/3).
      Rung 3 (TERMINAL): self-location from THIS module's own ``__file__``,
                via the existing ``_walk_up_to_checkout`` helper — reached only
                when rungs 1, 1.5, and 2 have all missed, immediately before the
                function would otherwise raise. On a stranger's box none of the
                registry/pointer/env rungs resolve, which is why ~24 of the
                published-CLI failures this rung fixes were the single message
                "cc_invoke: cannot resolve the engine root". Its answer is now
                DELEGATED (see "DELEGATION" above) rather than returned
                verbatim — hard constraint 2 (a script run by name must still
                find its own tree) is preserved because self-location still
                supplies the candidate that makes ``coordinator_core`` importable
                at all; only the FINAL answer now comes from the gate.
                LIMITATION, stated honestly: this answers with *cc_invoke.py's
                own* tree, not necessarily the caller's — on a multi-checkout
                box a bare ``_resolve_claude_klabauter_root()`` caller gets cc_invoke's
                tree, which is exactly why this is the TERMINAL rung (reached
                only when the alternative is raising) rather than an earlier
                one. A caller that wants per-caller self-location semantics
                should call ``resolve_engine_root(__file__)`` instead — that is
                not a general recommendation to migrate every caller here, just
                the honest answer for the multi-checkout case this rung cannot
                cover. In the published payload the two trees are the same,
                which is the case this rung targets.

    Returns the resolved absolute path.
    Raises RuntimeError on failure (unresolvable root — including a candidate
    from any delegated rung that cannot import
    ``coordinator_core.engine_root``) — or the RuntimeError subclass
    `_RegistryReadTimeout` specifically when the registry read at Rung 2 timed
    out and self-location (Rung 3) also missed, so a caller wanting to tell the
    two apart can `except _RegistryReadTimeout` before the general
    `except RuntimeError` (see `route()`, which does exactly this).

    C7/C17 routing note (docs/plans/2026-08-19-an-engine-root-is-a-stamped-
    build.md § C7, docs/plans/2026-08-20-an-engine-root-is-not-named-for-the-
    repo.md § C17, docs/reference/engine-vs-locator-resolver-routing.md
    bucket 4-bare-class-blind): this is the class-blind ENGINE-axis resolver
    every bare `_resolve_claude_klabauter_root()` caller reaches, and the PM's naming
    ruling (`resolve_claude_klabauter` should read as "find the source repo", not
    "find the engine") argued for renaming this symbol to say what it
    returns. C17 does the rename: this function's canonical name is now
    `_resolve_engine_root`. `cc_invoke._resolve_claude_klabauter_root` is kept as a
    PLAIN NAME ALIAS to the SAME function object (`_resolve_claude_klabauter_root =
    _resolve_engine_root` in cc_invoke.py), deliberately not a wrapper —
    `_delegate_to_gate`'s own comment above still applies verbatim:
    `inspect.getsource(cc_invoke._resolve_claude_klabauter_root)`-based call-site
    guards elsewhere in this tree, and unittest.mock.patch.object callers
    that intercept `cc_invoke._resolve_claude_klabauter_root` by name, both keep
    working because every bare call site in cc_invoke.py (route(), the other
    rungs, etc.) still spells the call `_resolve_claude_klabauter_root()` — the literal
    identifier a patch/getsource call targets, resolved at call time through
    the alias. Routing bucket-4's ~53 external callers, and cc_invoke's own
    internal call sites, onto the new name directly is left to a later
    chunk; until then both names resolve identically and are interchangeable.
    """
    def _delegate_to_gate(candidate: str, *, source: str) -> str:
        """Bootstrap ``coordinator_core.engine_root`` from ``candidate`` and
        return the gated final answer from ``coordinator_engine_root_with_class()``.

        Nested (not module-level) so every DISPATCH-axis candidate rung below
        (env, registry, self-location) shares exactly ONE delegation body,
        which `inspect.getsource(cc_invoke._resolve_claude_klabauter_root)`-based
        call-site guards elsewhere in this tree see as part of this function's
        own source — each candidate rung now only supplies a path capable of
        importing `coordinator_core`; the actual DR-132/stamp-gated decision
        comes from exactly one place (the ladder C5 rewrote), never answered
        here directly. `source` is folded into the raised message only, on a
        candidate that cannot import `coordinator_core.engine_root` (a
        marker-only or broken checkout) — that candidate is NOT trusted
        verbatim on that failure, unlike the pre-C6 behaviour of Rungs 1 and 3.

        DISAMBIGUATES BY ROOT, NOT BY MODULE NAME (C0,
        docs/plans/2026-08-20-an-engine-root-is-not-named-for-the-repo.md).
        `sys.modules["coordinator_core.<gate-module>"]` is a process-lifetime
        singleton keyed on NAME -- a second call with a different `candidate`
        would silently get served the FIRST call's cached module once both
        trees spell the gate module the same way. `_is_same_tree_as_canonical`
        decides which of two paths this call takes:
          - SAME root as the already-cached `coordinator_core` (or nothing
            cached yet): the ordinary `importlib`-based import below, BYTE-
            IDENTICAL to the pre-C0 behaviour -- this is the load-bearing
            short-circuit, not an optimisation.
          - GENUINELY DIFFERENT root: `_load_foreign_gate_entry_point` loads
            candidate's own gate module by file path under a candidate-unique
            key, so it can never collide with (or be served from) the
            canonical module's cached entry.
        """
        if _is_same_tree_as_canonical(candidate):
            _injected = candidate not in sys.path
            if _injected:
                sys.path.insert(0, candidate)
            try:
                try:
                    from coordinator_core.engine_root import coordinator_engine_root_with_class
                except ImportError as exc:
                    raise RuntimeError(
                        f"cc_invoke: engine-root candidate {candidate!r} (from {source}) is not "
                        f"a valid claude-klabauter checkout — coordinator_core/engine_root.py under it does "
                        f"not define coordinator_engine_root_with_class "
                        f"(import failed: {exc})"
                    ) from exc
                # Published-engine rung: coordinator_engine_root_with_class() runs the
                # DR-132 two-tier gate (published-engine-mirror vs. live-working-tree)
                # instead of the classless coordinator_engine_root(), which always
                # answered live-working-tree. The (root, resolution_class) pair is
                # returned; this rung only needs root — cc_invoke does not branch on
                # the class (that belongs to a future consumer, not this resolution
                # rung: engine.target is a read-site default, never diverted on here).
                resolved, _resolution_class = coordinator_engine_root_with_class()
            finally:
                if _injected:
                    try:
                        sys.path.remove(candidate)
                    except ValueError:
                        pass
        else:
            coordinator_engine_root_with_class = _load_foreign_gate_entry_point(candidate)
            if coordinator_engine_root_with_class is None:
                raise RuntimeError(
                    f"cc_invoke: engine-root candidate {candidate!r} (from {source}) is not "
                    f"a valid claude-klabauter checkout — no coordinator_core/*_root.py under it defines "
                    f"a coordinator_*_root_with_class entry point"
                )
            resolved, _resolution_class = coordinator_engine_root_with_class()
        if not resolved:
            raise RuntimeError(_claude_klabauter_root_gate_empty_remediation(candidate, source=source))
        return resolved

    # Rung 1: already in environment — CANDIDATE only now, delegated through
    # the gate (see docstring's "DELEGATION" note) rather than answered here.
    # C14 closed the dual-read window: the NEW name is the only one that
    # answers here. This is an AC13 bootstrap carve-out site — it cannot import
    # the accessor, because resolving the engine is what it does — so the
    # precedence is duplicated by hand and MUST move in lockstep with
    # coordinator_engine_root_env(). Pinned equal by test; see cc_invoke's own
    # literal duplication note near _ENGINE_ROOT_NEW_VAR/_ENGINE_ROOT_OLD_VAR.
    existing = os.environ.get(_ENGINE_ROOT_NEW_VAR, "")
    if existing:
        return _delegate_to_gate(existing, source=f"{_ENGINE_ROOT_NEW_VAR} environment variable")

    # Rung 1.5 (NEW): cheap direct-file-read pointer, checked ahead of the
    # expensive bash-spawn resolver below. On Windows this avoids spawning a
    # bash subprocess on the per-invoke resolution hot path (fleet-wide
    # hook-latency fix). Plain file read only — never spawns a subprocess.
    # Writer follows reader: the install surface is expected to write
    # <settings-home>/machine-local/.claude-klabauter-root; absence here is a normal
    # fallback state, not an error — falls through to the bash resolver below.
    #
    # Settings-home precedence mirrors _machine_local.py::_settings_home()
    # (Port of: settings-home.sh's _coordinator_settings_home, DoE b644d5a9,
    # 2026-07-22) inline (kept inline here for the same single-file-module
    # reason _machine_local.py documents — no cross-file import hack across
    # the source/install-tree split):
    #   COORDINATOR_SETTINGS_HOME (explicit override) →
    #   ${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings
    #
    # Spec backlink: pln-claude-klabauter-windows-portability-a48fac § C1
    _settings_home = os.environ.get("COORDINATOR_SETTINGS_HOME") or os.path.join(
        os.environ.get("CLAUDE_HOME") or os.path.expanduser("~"),
        ".coordinator-claude-settings",
    )
    _ml_pointer_dir = os.path.join(_settings_home, "machine-local")

    def _read_pointer(name: str) -> str:
        """Plain read of a machine-local pointer file; "" when absent or empty.

        HARD CONSTRAINT (this function's own docstring, rungs 1/1.5/3): no
        subprocess. This stays a bare `open()` for that reason.
        """
        try:
            with open(os.path.join(_ml_pointer_dir, name), "r", encoding="utf-8") as _f:
                return _f.read().strip()
        except OSError:
            return ""

    # DR-326: engine dispatch resolves to the PUBLISHED build, never to the live
    # working tree. The live tree is reachable here only via Rung 1's explicit
    # COORDINATOR_ENGINE_ROOT, which is what "claude-klabauter holds live processes only for testing"
    # means in practice. `.claude-klabauter-root` is written by the same install
    # pass that registers the mirror, so its presence IS the dual-boot signal —
    # and reading it costs one more `open()`, honouring the no-subprocess bound
    # that made this rung gate-blind in the first place.
    _published_pointer_val = _read_pointer(".claude-klabauter-root")
    if _published_pointer_val and os.path.isfile(
        os.path.join(_published_pointer_val, "coordinator_core", "_engine_stamp")
    ):
        return _published_pointer_val

    # Single-tree box (no published mirror installed): the live tree is the only
    # engine there is, and this rung keeps its pre-DR-326 behaviour byte-identical.
    #
    # The `isdir` guard mirrors the intent of the published arm above (C4, AC7;
    # tightened by C3 to a stamp check for that arm -- see below). Without it a
    # bare truthiness check returns whatever the pointer file holds -- a stale
    # path, or a path naming a FILE -- verbatim as the engine root, with no
    # fall-through to Rung 2. That was unreachable in the live tree only
    # because the published arm answers first; in the PUBLISHED MIRROR it is
    # reachable and live, because the publish transform's bare 'claude-klabauter' ->
    # 'claude-klabauter' row rewrote the string literal ".claude-klabauter-root" too,
    # leaving the mirror reading the same pointer file on both arms and unable
    # to fall back at all.
    #
    # This live arm deliberately stays `isdir`, not a stamp check: DR-331
    # makes `compute_client_token` RAISE on a single-tree (unstamped-by-design)
    # box rather than fall back, and `test_rung1_5_pointer_file_no_spawn` pins
    # this arm's isdir-only behaviour. The published arm above admits only a
    # STAMPED root (C3, docs/plans/2026-08-21-the-cli-bootstrap-tax-dies-at-
    # the-interpreter-floor.md § C3) -- `isfile(<root>/coordinator_core/
    # _engine_stamp)` strictly subsumes the prior `isdir` check there, so it
    # was dropped rather than added to.
    _pointer_val = _read_pointer(".claude-klabauter-root")
    if _pointer_val and os.path.isdir(_pointer_val):
        return _pointer_val

    # Rung 2: native bootstrap — locate a candidate root via the machine-local
    # registry (no bash), then delegate to coordinator_core.engine_root itself
    # once it's importable, so the FINAL answer (and any future rung additions
    # to that module) come from the single native oracle, not a re-derivation
    # duplicated here.
    _registry_read_timed_out = False
    try:
        _candidate = _machine_local_get("repos.claude_klabauter")
    except _RegistryReadTimeout:
        _candidate = None
        _registry_read_timed_out = True

    if _candidate and os.path.isdir(_candidate):
        return _delegate_to_gate(_candidate, source="machine-local repos.claude_klabauter")

    # Rung 3 (terminal): self-locate from cc_invoke's OWN __file__ before
    # raising. Reached only when env, pointer, and registry all missed — see
    # the docstring's "Rung 3 (TERMINAL)" note for the limitation this rung
    # knowingly carries. Delegated the same way as every other candidate rung
    # (see docstring's "DELEGATION" note) — hard constraint 2 (a script run by
    # name must still find its own tree) is preserved by self-location still
    # supplying the candidate; only the final answer is no longer verbatim.
    #
    # This module (engine_bootstrap.py) is a sibling of cc_invoke.py, not
    # cc_invoke itself — a bare `__file__` here would answer with THIS file's
    # own location, never cc_invoke's, silently breaking the "cc_invoke's OWN
    # __file__" contract above and every `unittest.mock.patch.object(cc_invoke,
    # "__file__", ...)` test that relies on it. `caller_file` lets a caller
    # thread its own `__file__` through explicitly (e.g. `_resolve_engine_root(
    # __file__)`); when omitted, cc_invoke's already-imported module is looked
    # up by name in `sys.modules` and its CURRENT `__file__` attribute is read
    # at call time (so a patched `__file__` is honoured), falling back to this
    # module's own `__file__` only if cc_invoke has not been imported at all.
    _self_file = caller_file
    if _self_file is None:
        _cc_invoke_mod = sys.modules.get("cc_invoke")
        _self_file = getattr(_cc_invoke_mod, "__file__", None) if _cc_invoke_mod is not None else None
        if _self_file is None:
            _self_file = __file__
    _self_located = _walk_up_to_checkout(_self_file)
    if _self_located:
        return _delegate_to_gate(_self_located, source="self-location (__file__)")

    if _registry_read_timed_out:
        # A transient reader timeout, not a genuinely absent/unregistered
        # checkout — propagate the distinguishable outcome (AC1/AC3)
        # instead of the clone/register text below, which is wrong here.
        raise _RegistryReadTimeout(
            f"{_REGISTRY_READ_TIMEOUT_TOKEN} ({_MACHINE_LOCAL_READ_TIMEOUT_SECS}s bound) "
            "resolving repos.claude_klabauter, and self-location also missed."
        )
    raise RuntimeError(_CLAUDE_KLABAUTER_ROOT_REMEDIATION)
