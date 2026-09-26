# is-session-live / list-stale-claim-handoffs (2026-07-23) are a SEPARATE
# remedy (`_CLAIM_CONFLICT_REMEDY`, a human-facing string). That module, its
# `_check_claim_conflicts` gate, and `_CLAIM_CONFLICT_REMEDY` were all deleted
# docstring BOUNDARY note).
#     carries no extension). Exit code is UNCHANGED (idempotent no-op ->
#       "indeterminate". "live" | "dead" | "indeterminate" are UNCHANGED
#                 1 to distinguish; exit code is UNCHANGED for compat.
#                 _sid_looks_valid) — COULD NOT DETERMINE liveness;
#     Reads the PATH-TOUCH plane (coordinator_core.session.claim_index --
#     a DIFFERENT plane and a DIFFERENT question than
#     `list-claims-by-session` above (which reads the ARTIFACT-CLAIM RECORD
#     the-name.md) is PROVENANCE, not an address ready for SendMessage --
#     (_CLAIM_CONFLICT_REMEDY) -- a blocked EM sent here by that refusal was,
#     exit 1   -> the path's claim-index entry is claim_index.UNANSWERABLE
#                 (claim_index.ABORT_CAUSE_EMPTY_BASE / _CAP_EXCEEDED /
#                 _IO_ERROR, or "unknown" if the lookup result carries none)
# trampoline's own transport failure) exits 3 (_TRANSPORT_FAIL, same
# catches the REQUIRED-arg ``ValueError`` those three claims.py functions
from __future__ import annotations
"""session-claim-cli — see the # comment block above for the RAG-bait purpose
text (the polyglot shebang line above makes THIS triple-quoted string a
silently-discarded expression statement, not the module __doc__ — same
convention as archive-stamp-cli)."""

import os
import sys
from pathlib import Path

_TRANSPORT_FAIL = 3
_NOT_LIVE = 1
_MALFORMED_SID = 4


_CC_INVOKE_MODULE = None


def _cc_invoke():
    """Lazy singleton import of the ``cc_invoke`` module OBJECT itself (not
    just one name out of it) — the dispatch-import chokepoint below
    (``_dispatch_import``) needs ``require_dispatch_module``, and call sites
    that must discriminate a diagnosed stale-mirror failure from a plain
    root-resolution failure need ``StaleEngineImportError`` too. One cached
    import serves both, and every ``_bootstrap_engine``/``_dispatch_import``
    caller in this file, rather than re-doing the ``import lib`` dance each
    time."""
    global _CC_INVOKE_MODULE
    if _CC_INVOKE_MODULE is None:
        import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
        import cc_invoke as _mod

        _CC_INVOKE_MODULE = _mod
    return _CC_INVOKE_MODULE


def _bootstrap_engine():
    """Shared lazy import + engine-root resolution used by every
    ``_import_*`` seam below that does NOT route through
    ``_dispatch_import`` — keeps the ``lib``/``cc_invoke`` imports out of
    module scope without duplicating them six times."""
    return _cc_invoke().require_dispatch_engine_on_path()


def _dispatch_import(dotted_name: str):
    """Chokepoint for every ``coordinator_core.session.<x>`` import this
    CLI's claim-QUERY handlers make against the DISPATCH engine
    (state/bug-backlog/2026-09-01-a-new-engine-module-breaks-fleet-wide-
    claim-queries-until-publish.yaml): resolves the dispatch root exactly as
    ``_bootstrap_engine`` does (``require_dispatch_engine_on_path``,
    unchanged) and then imports ``dotted_name`` through
    ``cc_invoke.require_dispatch_module``, so an ``ImportError`` caused by a
    published mirror lagging source arrives as a diagnosed
    ``StaleEngineImportError`` (cause + "publish the mirror" / "fix the
    import path" remedy) instead of a raw one.

    Not every bare import in this file routes through here.
    ``_import_harness_registry_module`` and ``_import_holder_evidence_module``
    stay on the plain ``_bootstrap_engine`` + bare-import shape deliberately:
    each of their call sites already wraps the call in a broad ``except Exception`` that
    degrades to ``None``/``"unknown"``/a marker (best-effort diagnostics,
    never a verdict), so an ``ImportError`` there was never a raw traceback
    to begin with — there is nothing for the diagnosis to improve, and
    routing them through here would only widen this seam's surface for no
    behaviour change.
    """
    return _cc_invoke().require_dispatch_module(dotted_name)


def _import_module():
    return _dispatch_import("coordinator_core.session.claims")


def _import_liveness_module():
    """Separate seam from ``_import_module`` (claims) so ``is-session-live``
    tests can stub liveness in isolation without touching the claims stub."""
    return _dispatch_import("coordinator_core.session.liveness")


def _import_stale_claims_module():
    """Separate seam from ``_import_module`` (claims) so
    ``list-stale-claim-handoffs`` tests can stub the enumerator in isolation."""
    return _dispatch_import("coordinator_core.session.stale_claims")


def _import_claim_index_module():
    """Separate seam from ``_import_module`` (claims) and
    ``_import_liveness_module`` so ``who-claims-path`` tests can stub the
    PATH-TOUCH plane independently of the artifact-claim store and the
    liveness verdict, mirroring the existing per-functional-area seam
    split above."""
    return _dispatch_import("coordinator_core.session.claim_index")


def _import_harness_registry_module():
    """Separate seam from ``_import_liveness_module`` so ``who-claims-path``'s
    rung-2 name resolution (``harness_registry.lookup(sid)``) can be stubbed
    independently of the live/dead verdict in tests, mirroring the
    per-functional-area seam split above."""
    claude_klabauter_root = _bootstrap_engine()
    import coordinator_core.session.harness_registry as _mod

    return _mod


def _import_holder_evidence_module():
    """Separate seam from ``_import_liveness_module`` so ``is-session-live``'s
    AC7 basis line can be stubbed independently of the live/dead verdict in
    tests, mirroring the claims/liveness/stale_claims seam split above."""
    claude_klabauter_root = _bootstrap_engine()
    import coordinator_core.session.holder_evidence as _mod

    return _mod


def _liveness_basis_for(sid: str, cwd) -> str:
    """AC7/AC8: report the SAME basis ``holder_evidence.liveness_basis``
    already derives, never a second computation. Fail-soft by construction
    (mirrors that module's own contract): any import or lookup failure here
    degrades to ``"unknown"`` rather than raising — the basis line is
    additive output (AC9) and must never take down the live/dead verdict
    this subcommand already resolved before calling this helper."""
    try:
        mod = _import_holder_evidence_module()
        return mod.liveness_basis(sid, cwd)
    except Exception:  # noqa: BLE001 - fail-soft additive output, see docstring
        return "unknown"


_UNNAMED_MARKER = "<unnamed>"

#: Rung 3 split into its two DISTINGUISHABLE outcomes (doe-claude-em,
#: and rc 4 (record found, process gone). `_UNNAMED_MARKER` is retained above
_NO_REGISTRY_RECORD_MARKER = "<no registry record -- not proof the session ended>"
_NAME_UNRESOLVED_MARKER = "<name unresolved: registry lookup failed>"


def _format_claim_age(seconds: float) -> str:
    """"held Nh"/"held Nm", the SAME rendering ``coordinator-safe-commit.py``'s
    ``_holder_context`` already uses for its identical "how stale is this"
    question -- reused verbatim rather than a second phrasing invented here."""
    hours = seconds / 3600.0
    if hours >= 1:
        return f"held {hours:.1f}h"
    return f"held {max(seconds, 0.0) / 60.0:.0f}m"


_KIND_LABELS = {"w": "write", "r": "read"}

_UNKNOWN_KIND_MARKER = "unknown-kind"


def _render_claimant_kind(sid: str, path: str, lookup_result) -> str:
    """Whether this claimant WROTE the path or merely READ it.

    One rung, not three (contrast `_render_claimant_name`): the kind is a
    property of the recorded event and there is nothing live to fall back
    to. Either the claim states it or it does not, and "does not" is
    reported as such rather than guessed -- the guess would be invisible and
    the unknown is not.

    Best-effort, same posture as its name sibling: this column is additive
    display output and must never take down the row's sid/live|dead columns.
    """
    try:
        recorded = getattr(lookup_result, "recorded_kind", None) or {}
        kind = (recorded.get(path) or {}).get(sid)
    except Exception:  # noqa: BLE001 -- an additive column never fails a row
        return _UNKNOWN_KIND_MARKER
    return _KIND_LABELS.get(kind, _UNKNOWN_KIND_MARKER)


def _render_claimant_name(sid: str, path: str, lookup_result) -> str:
    """The three-rung resolution ladder (C2, docs/plans/2026-09-01-the-claim-
    record-carries-the-name.md): (1) the name RECORDED on the claim at write
    time -- survives the writer exiting, re-pointing its session id, or the
    machine restarting; (2) failing that, a LIVE ``harness_registry.
    lookup(sid)`` -- cheap, and correct for a pre-C1 record whose writer
    session is still resident; (3) failing both, one of THREE distinct
    markers -- never an error, and each visually distinct from a bare sid so
    a reader cannot mistake it for one.

    RUNG 3 IS THREE OUTCOMES, NOT ONE. ``_NO_REGISTRY_RECORD_MARKER`` (the
    registry was asked and holds nothing for this sid), ``_NAME_UNRESOLVED_
    MARKER`` (the registry could not be asked -- import failure or a raise
    from ``lookup``), and ``_UNNAMED_MARKER`` (a record resolved and simply
    carries no name, which is what a pre-C1 record from an exited session
    renders as). Collapsing the first two into one marker, as this function
    did until 2026-09-01, made a DEGRADATION indistinguishable from a FACT:
    a caller cannot tell "re-check this against a workstream path" from
    "distrust this column entirely" when both print the same token. The
    split mirrors ``resolve-peer-address.py``'s own rc 3 / rc 4 distinction,
    which doe-claude-em's memo asked be kept intact at this seam.

    RENDERED AS PROVENANCE, NEVER AS AN ADDRESS. Rung 1's name is an
    identity the CLAIMANT claimed for itself at write time, not a live
    resolution performed now -- the whole reason C2 exists is that the sid
    beside it may no longer resolve to anything, and a name inherited from
    the same stale record is not proof it still does either. It is rendered
    with its age (``_format_claim_age``, following ``_holder_context``'s
    "held 33.8h" precedent) and an explicit staleness warning: the name may
    now belong to someone else, and a caller MUST verify liveness/identity
    before sending to it -- this function never claims present-tense
    reachability for a rung-1 answer. Rung 2's name IS a fresh live lookup,
    so it carries no age or staleness qualifier of its own, but it is still
    not a reachability claim: the caller decides, this function only names.

    Best-effort: an import failure, a raise from ``harness_registry.lookup``
    (which per its own docstring never raises, but this stays defensive
    should that contract ever change), or any other exception on the rung-2
    path degrades to rung 3 rather than propagating -- this column is
    additive display output on an already-decided claimant row and must
    never take down the row's ``sid``/``live|dead`` columns.
    """
    name_ladder = _dispatch_import("coordinator_core.session.name_ladder")

    recorded = getattr(lookup_result, "recorded_name", None) or {}
    recorded_name = (recorded.get(path) or {}).get(sid)

    def _lookup(_sid: str):
        return _import_harness_registry_module().lookup(_sid)

    name, rung, reason = name_ladder.resolve_name(recorded_name, sid, _lookup)

    if rung == name_ladder.RUNG_RECORDED:
        edit_ts = getattr(lookup_result, "edit_ts", None) or {}
        ts = (edit_ts.get(path) or {}).get(sid)
        age = ""
        if ts is not None:
            try:
                from datetime import datetime, timezone  # noqa: PLC0415

                now = datetime.now(timezone.utc)
                age = f", {_format_claim_age((now - ts).total_seconds())}"
            except Exception:  # noqa: BLE001 - additive display only
                age = ""
        return (
            f"{name} (recorded name{age} -- provenance only, not a live "
            "address; verify the holder before sending)"
        )
    if rung == name_ladder.RUNG_LIVE_LOOKUP:
        return f"{name} (live harness registry lookup)"
    if reason == name_ladder.REASON_LOOKUP_FAILED:
        return _NAME_UNRESOLVED_MARKER
    if reason == name_ladder.REASON_NO_REGISTRY_RECORD:
        return _NO_REGISTRY_RECORD_MARKER
    return _UNNAMED_MARKER


_SID_ALLOWED_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
)


def _sid_looks_valid(sid: str) -> bool:
    """True iff ``sid`` is a plausible session id worth asking
    ``liveness.session_live`` about — False for empty/whitespace-only, or a
    value containing any character outside the allowlist below.

    ``session_live`` itself already treats an empty sid as not-live (returns
    False, never raises), which is exactly the conflation ``is-session-live``
    must NOT reproduce at the CLI boundary: a bad/absent argument must read as
    "could not determine" (exit 4), never silently fold into "confirmed dead"
    (exit 1) — that fold is precisely the fail-open shape named in this
    subcommand's spec backlink (a session with no matching detector reads as
    if it doesn't exist, rather than as an unanswered question).

    Allowlist, not blocklist (Review: coordinator:code-reviewer, colon/
    drive-letter gap): a blocklist of `/`, `\\`, `..`, NUL rejected a path
    separator and traversal but not a bare drive-letter/colon component
    (e.g. ``"C:evil"``) — on Windows, ``ntpath.join(base, "C:evil")``
    DISCARDS ``base`` entirely and resolves to ``"C:evil"``, a full
    containment escape out of the sessions corpus. A session id is a
    UUID-shaped token (or, for test fixtures, a hyphen/underscore-delimited
    slug like ``"test-session-abc123"``); restricting to
    ``[A-Za-z0-9_-]`` closes that class of escape (colon, reserved device
    names, trailing dot/space, path separators, ``..``, NUL — all excluded
    by construction) without narrower special-casing, and is compatible
    with every sid already live on disk under
    ``.git/coordinator-sessions/``.
    """
    s = sid.strip()
    if not s:
        return False
    return all(ch in _SID_ALLOWED_CHARS for ch in s)


#: load-bearing, not decoration: ``artifact`` is the PATH-TOUCH plane
_SUBCOMMANDS = (
    "subcommands: claim-artifact <class> | release-artifact <class> | "
    "release-or-relinquish <class> | clear-claim-if-dead <class> | "
    "claim-plan | take-over-claim plan | is-session-live | "
    "list-stale-claim-handoffs | list-claims-by-session | who-claims-path\n"
    "  <class>: handoff | memo | plan (basename-keyed claim records), or "
    "'artifact' (path-touch plane — basename is a repo-relative PATH; this "
    "is how a path claim who-claims-path reports is released)\n"
    "  'artifact' is valid on release-artifact and clear-claim-if-dead ONLY. "
    "claim-artifact refuses it: a touch-claim is recorded by touching the "
    "path, never declared ahead of one.\n"
    "  release-or-relinquish <class> <basename> [baton_repo_root]: releases "
    "like release-artifact, and additionally writes a DR-205 relinquishment "
    "marker for a plan claim this process's own identity still recognises.\n"
    "  take-over-claim plan <basename> --justification <text> "
    "[baton_repo_root]: DR-205's fail-loud takeover verb. 'plan' is the ONLY "
    "valid class token here (D2) -- any other value is a usage error, not a "
    "runtime refusal, and calls no claims function."
)

_HELP_FLAGS = ("--help", "-h", "help")


def _usage(prog: str) -> int:
    print(f"usage: {prog} <subcommand> <args...>\n{_SUBCOMMANDS}", file=sys.stderr)
    return 2


def _reject_flag_like_positionals(usage: str, args: list) -> int | None:
    """`2` (via `_usage`) when any of `args` looks like a flag, else `None`.

    Every claim subcommand below takes POSITIONALS only — `<class>
    <basename> [baton_repo_root]`. Without this, a caller reaching for the
    flag spelling every other coordinator CLI uses (`--repo <root>`) has
    `--repo` silently bound as `baton_repo_root` and `<root>` dropped past
    the end: the release targets a directory named `--repo`, finds no claim,
    and `release_artifact` returns its no-op success. EXIT 0, nothing
    released, and a caller that stood down on that believes its claim is
    gone while it still holds it. A wrong repo root must be a usage error,
    never a silent success.

    Negative-spec: this rejects on the `--` shape, NOT against a list of
    known flags — the point is that these subcommands have no flags at all,
    so any `--`-leading token is a caller mistake whatever it spells.
    `claim-plan` owns a real `--for-execution` and filters it itself; it
    does not route through here."""
    for arg in args:
        if isinstance(arg, str) and arg.startswith("--"):
            print(
                f"session-claim-cli: {arg!r} is not a flag on this subcommand — "
                "the repo root is POSITIONAL. Passing it as a flag binds the flag "
                "name itself as the root and releases nothing, at exit 0.",
                file=sys.stderr,
            )
            return _usage(usage)
    return None


def _bool_to_exit(result: bool) -> int:
    return 0 if result else 1


_CLASSED_CLAIM_CLASSES = ("handoff", "memo", "plan")


def _claim_lookup_dir(mod, class_: str, basename: str, baton_repo_root: str):
    """Best-effort resolution of the SAME claim directory
    ``claims.clear_claim_if_dead`` / ``claims.release_artifact`` will inspect,
    so the CLI can tell a caller what was looked up and under which key BEFORE
    the call, when that directory turns out not to exist (AC5). Delegates to
    ``claims.claim_dir_for`` — the same base+claim_dir arithmetic
    ``clear_claim_if_dead`` itself calls — rather than re-deriving it here, so
    this precheck and the library's own resolution cannot drift apart.

    ``mod`` is the already-imported ``claims`` module (the CLI's own
    ``_import_module`` seam) — passed in rather than re-imported so this stays
    a plain arithmetic lookup, not a second import chokepoint.

    Returns ``None`` on ANY resolution failure (bad/absent baton root,
    unresolvable sessions dir, transport failure) — callers MUST treat
    ``None`` as "skip the not-found precheck", never as evidence either way;
    ``claims.clear_claim_if_dead`` itself remains the sole authority on the
    actual outcome.
    """
    try:
        return mod.claim_dir_for(class_, basename, baton_repo_root)
    except Exception:  # noqa: BLE001 - best-effort diagnostic only, see docstring
        return None


def _emit_claim_not_found_note(
    subcmd: str, class_: str, basename: str, claim_dir
) -> None:
    """AC5: the basename convention is part of the trap — the claim key
    carries no ``.md`` while a caller naturally holds a path that does. Name
    what was looked up and under which key, so a wrong basename is
    self-diagnosing rather than silent. The distinction from a refusal is
    already carried by exit 0 vs exit 1 and by the refusal's own distinct
    message; asserting it in prose is a message-register violation (Review:
    staff-eng-review, docs/wiki/guard-messaging.md B1/B2) and is not
    repeated here.

    Serves ``release-artifact`` on the same terms: ``release_artifact``'s
    not-the-holder / claim-absent legs are documented NO-OP SUCCESS, so a
    wrong key there is exit 0 with nothing written and nothing said — the
    same silence this note exists to remove, reached by a different door."""
    note = (
        f"session-claim-cli: {subcmd}: no claim at {claim_dir} "
        f"(class {class_!r} basename {basename!r})"
    )
    if basename.endswith(".md"):
        note += " — claim keys carry no '.md' extension"
    print(note, file=sys.stderr)


def _call_claim_bool(subcmd: str, fn, *args) -> int:
    """Invoke a bool-returning claims.py function and map its result to an
    exit code, catching the ``${1:?}``-style ``ValueError`` its REQUIRED-arg
    guards raise (``class_``/``basename`` empty — see ``claim_artifact`` /
    ``release_artifact`` / ``clear_claim_if_dead``'s own docstrings) and
    reporting it the SAME way ``claim_plan``'s boundary check already does:
    a clean one-line stderr message + exit 1, never a raw Python traceback.

    This is the shared CLI-boundary fix for all three ``claim_artifact``-
    family entry points at once (rather than duplicating a shape guard
    inside each of the three library functions) — the CLI is the one place
    that can hand a caller-supplied EMPTY STRING through as a syntactically
    complete argv (``len(rest) >= 2`` already passed usage validation), so
    it is also the one place a required-arg ``ValueError`` can still reach
    an end user rather than a Python caller who controls its own arguments.
    ``claim-plan`` does not route through this helper — it already returns
    bool on every input (no raise), by its own boundary check.
    """
    try:
        result = fn(*args)
    except ValueError as exc:
        print(f"session-claim-cli: {subcmd}: {exc}", file=sys.stderr)
        return 1
    return _bool_to_exit(result)


def main(argv: list[str]) -> int:
    """Top-level safety net (Review: coordinator:code-reviewer — guard-
    per-callsite structural fragility) around ``_dispatch``.

    The per-callsite ``try/except Exception`` guards below map an engine
    failure at ITS OWN callsite to ``indeterminate``/``_TRANSPORT_FAIL`` —
    but nothing in that shape stops a NEW callsite (a future subcommand, or
    a call added inside an existing arm) from reproducing the original
    exit-1-on-engine-failure defect this file exists to close. This
    function is the backstop, not a replacement: it does not shrink or
    remove any per-callsite handler, it only catches whatever a callsite
    forgot to.

    ``SystemExit`` and ``KeyboardInterrupt`` are NOT ``Exception`` subclasses
    and so pass through unmodified — ``_usage``'s ordinary int-returning
    exit-code path is untouched (it never raises), and an operator-initiated
    Ctrl-C still exits via Python's normal interpreter path rather than
    being folded into ``indeterminate``/exit 3. Only a genuinely unexpected
    exception is remapped here — a real ``dead`` verdict is a return value,
    never an exception, so it can never be caught and converted by this
    guard.
    """
    try:
        return _dispatch(argv)
    except Exception as exc:  # noqa: BLE001 - top-level backstop, see docstring
        print("indeterminate")
        print(
            f"session-claim-cli: unhandled {type(exc).__name__}: {exc} — "
            f"could not determine liveness/claim outcome (exit {_TRANSPORT_FAIL})",
            file=sys.stderr,
        )
        return _TRANSPORT_FAIL


def _dispatch(argv: list[str]) -> int:
    if not argv:
        return _usage("session-claim-cli")
    subcmd, rest = argv[0], argv[1:]

    if subcmd in _HELP_FLAGS:
        print(f"usage: session-claim-cli <subcommand> <args...>\n{_SUBCOMMANDS}")
        return 0

    _CLAIM_SUBCOMMANDS = (
        "claim-artifact", "release-artifact", "release-or-relinquish",
        "clear-claim-if-dead", "claim-plan", "list-claims-by-session",
    )
    if subcmd in _CLAIM_SUBCOMMANDS:
        try:
            mod = _import_module()
        except _cc_invoke().StaleEngineImportError as exc:
            print(f"session-claim-cli: {exc}", file=sys.stderr)
            return _TRANSPORT_FAIL
        except RuntimeError as exc:
            print(f"session-claim-cli: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
            return _TRANSPORT_FAIL
        except ImportError as exc:
            print(f"session-claim-cli: coordinator_core.session.claims not importable: {exc}", file=sys.stderr)
            return _TRANSPORT_FAIL

    if subcmd == "claim-artifact":
        if len(rest) < 2:
            return _usage("session-claim-cli claim-artifact <class> <basename> [baton_repo_root]")
        _flagged = _reject_flag_like_positionals("session-claim-cli claim-artifact <class> <basename> [baton_repo_root]", rest)
        if _flagged is not None:
            return _flagged
        class_, basename = rest[0], rest[1]
        baton_repo_root = rest[2] if len(rest) > 2 else ""
        return _call_claim_bool("claim-artifact", mod.claim_artifact, class_, basename, baton_repo_root)

    if subcmd == "release-artifact":
        if len(rest) < 2:
            return _usage("session-claim-cli release-artifact <class> <basename> [baton_repo_root]")
        _flagged = _reject_flag_like_positionals("session-claim-cli release-artifact <class> <basename> [baton_repo_root]", rest)
        if _flagged is not None:
            return _flagged
        class_, basename = rest[0], rest[1]
        baton_repo_root = rest[2] if len(rest) > 2 else ""
        if class_ in _CLASSED_CLAIM_CLASSES:
            claim_dir = _claim_lookup_dir(mod, class_, basename, baton_repo_root)
            if claim_dir is not None and not claim_dir.is_dir():
                _emit_claim_not_found_note("release-artifact", class_, basename, claim_dir)
        return _call_claim_bool("release-artifact", mod.release_artifact, class_, basename, baton_repo_root)

    if subcmd == "release-or-relinquish":
        if len(rest) < 2:
            return _usage("session-claim-cli release-or-relinquish <class> <basename> [baton_repo_root]")
        _flagged = _reject_flag_like_positionals("session-claim-cli release-or-relinquish <class> <basename> [baton_repo_root]", rest)
        if _flagged is not None:
            return _flagged
        class_, basename = rest[0], rest[1]
        baton_repo_root = rest[2] if len(rest) > 2 else ""
        if class_ in _CLASSED_CLAIM_CLASSES:
            claim_dir = _claim_lookup_dir(mod, class_, basename, baton_repo_root)
            if claim_dir is not None and not claim_dir.is_dir():
                _emit_claim_not_found_note("release-or-relinquish", class_, basename, claim_dir)
        return _call_claim_bool(
            "release-or-relinquish", mod.release_or_relinquish_artifact, class_, basename, baton_repo_root
        )

    if subcmd == "clear-claim-if-dead":
        if len(rest) < 2:
            return _usage("session-claim-cli clear-claim-if-dead <class> <basename> [baton_repo_root]")
        _flagged = _reject_flag_like_positionals("session-claim-cli clear-claim-if-dead <class> <basename> [baton_repo_root]", rest)
        if _flagged is not None:
            return _flagged
        class_, basename = rest[0], rest[1]
        baton_repo_root = rest[2] if len(rest) > 2 else ""
        if class_ in _CLASSED_CLAIM_CLASSES:
            claim_dir = _claim_lookup_dir(mod, class_, basename, baton_repo_root)
            if claim_dir is not None and not claim_dir.is_dir():
                _emit_claim_not_found_note("clear-claim-if-dead", class_, basename, claim_dir)
        return _call_claim_bool("clear-claim-if-dead", mod.clear_claim_if_dead, class_, basename, baton_repo_root)

    if subcmd == "claim-plan":
        if not rest:
            return _usage("session-claim-cli claim-plan <slug> [--for-execution]")
        for_execution = "--for-execution" in rest
        positional = [a for a in rest if a != "--for-execution"]
        if not positional:
            return _usage("session-claim-cli claim-plan <slug> [--for-execution]")
        return _bool_to_exit(mod.claim_plan(positional[0], for_execution=for_execution))

    if subcmd == "take-over-claim":
        _usage_line = (
            "session-claim-cli take-over-claim plan <basename> "
            "--justification <text> [baton_repo_root]"
        )
        if not rest:
            return _usage(_usage_line)
        class_token = rest[0]
        if class_token != "plan":
            print(
                f"session-claim-cli: take-over-claim: only the 'plan' class "
                f"supports takeover (D2) — {class_token!r} is not valid here",
                file=sys.stderr,
            )
            return _usage(_usage_line)

        remaining = rest[1:]
        justification = None
        positionals = []
        i = 0
        while i < len(remaining):
            arg = remaining[i]
            if arg == "--justification":
                if i + 1 >= len(remaining):
                    print(
                        "session-claim-cli: take-over-claim: --justification "
                        "requires a value",
                        file=sys.stderr,
                    )
                    return _usage(_usage_line)
                justification = remaining[i + 1]
                i += 2
                continue
            if isinstance(arg, str) and arg.startswith("--"):
                print(
                    f"session-claim-cli: take-over-claim: unrecognised flag "
                    f"{arg!r}",
                    file=sys.stderr,
                )
                return _usage(_usage_line)
            positionals.append(arg)
            i += 1
        if not positionals:
            return _usage(_usage_line)
        basename = positionals[0]
        baton_repo_root = positionals[1] if len(positionals) > 1 else ""
        if justification is None:
            justification = ""

        try:
            mod = _import_module()
        except _cc_invoke().StaleEngineImportError as exc:
            print(f"session-claim-cli: {exc}", file=sys.stderr)
            return _TRANSPORT_FAIL
        except RuntimeError as exc:
            print(f"session-claim-cli: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
            return _TRANSPORT_FAIL
        except ImportError as exc:
            print(f"session-claim-cli: coordinator_core.session.claims not importable: {exc}", file=sys.stderr)
            return _TRANSPORT_FAIL
        return _call_claim_bool(
            "take-over-claim", mod.take_over_claim, basename, justification, baton_repo_root
        )

    if subcmd == "list-claims-by-session":
        if not rest:
            return _usage("session-claim-cli list-claims-by-session <sid> [cwd]")
        _flagged = _reject_flag_like_positionals(
            "session-claim-cli list-claims-by-session <sid> [cwd]", rest
        )
        if _flagged is not None:
            return _flagged
        sid = rest[0]
        cwd = rest[1] if len(rest) > 1 else None
        for class_, basename in mod.list_claims_by_session(sid, cwd):
            print(f"{class_}\t{basename}")
        return 0

    if subcmd == "is-session-live":
        if not rest:
            return _usage("session-claim-cli is-session-live <SID> [cwd]")
        sid = rest[0]
        cwd = rest[1] if len(rest) > 1 else None
        if not _sid_looks_valid(sid):
            print("indeterminate")
            print(
                f"session-claim-cli: is-session-live: malformed/absent session "
                f"id {sid!r} — could not determine liveness (exit {_MALFORMED_SID}), "
                f"NOT a not-live verdict (exit {_NOT_LIVE})",
                file=sys.stderr,
            )
            return _MALFORMED_SID
        try:
            liveness_mod = _import_liveness_module()
        except _cc_invoke().StaleEngineImportError as exc:
            print(f"session-claim-cli: {exc}", file=sys.stderr)
            return _TRANSPORT_FAIL
        except RuntimeError as exc:
            print(f"session-claim-cli: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
            return _TRANSPORT_FAIL
        except ImportError as exc:
            print(
                f"session-claim-cli: coordinator_core.session.liveness not importable: {exc}",
                file=sys.stderr,
            )
            return _TRANSPORT_FAIL
        try:
            live = liveness_mod.session_live(sid, cwd)
        except Exception as exc:  # noqa: BLE001 - see docstring below
            print("indeterminate")
            print(
                f"session-claim-cli: is-session-live: session_live raised "
                f"{type(exc).__name__}: {exc} — could not determine liveness "
                f"(exit {_TRANSPORT_FAIL}), NOT a not-live verdict (exit {_NOT_LIVE})",
                file=sys.stderr,
            )
            return _TRANSPORT_FAIL
        basis = _liveness_basis_for(sid, cwd)
        if live:
            print("live")
        elif basis == "harness-registry-elsewhere":
            print("live-elsewhere")
        else:
            print("dead")
        print(f"liveness_basis:{basis}")
        return 0 if live else _NOT_LIVE

    if subcmd == "who-claims-path":
        if not rest:
            return _usage("session-claim-cli who-claims-path <path> [cwd]")
        path = rest[0]
        cwd = rest[1] if len(rest) > 1 else None
        try:
            claim_index_mod = _import_claim_index_module()
        except _cc_invoke().StaleEngineImportError as exc:
            print(f"session-claim-cli: {exc}", file=sys.stderr)
            return _TRANSPORT_FAIL
        except RuntimeError as exc:
            print(f"session-claim-cli: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
            return _TRANSPORT_FAIL
        except ImportError as exc:
            print(
                f"session-claim-cli: coordinator_core.session.claim_index not importable: {exc}",
                file=sys.stderr,
            )
            return _TRANSPORT_FAIL
        try:
            liveness_mod = _import_liveness_module()
        except _cc_invoke().StaleEngineImportError as exc:
            print(f"session-claim-cli: {exc}", file=sys.stderr)
            return _TRANSPORT_FAIL
        except RuntimeError as exc:
            print(f"session-claim-cli: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
            return _TRANSPORT_FAIL
        except ImportError as exc:
            print(
                f"session-claim-cli: coordinator_core.session.liveness not importable: {exc}",
                file=sys.stderr,
            )
            return _TRANSPORT_FAIL
        try:
            lookup_result = claim_index_mod.lookup([path], cwd=cwd)
            claimants = lookup_result.get(path, [])
        except Exception as exc:  # noqa: BLE001 - see is-session-live's own guard
            print("indeterminate")
            print(
                f"session-claim-cli: who-claims-path: claim_index.lookup raised "
                f"{type(exc).__name__}: {exc} for {path!r} — could not determine "
                f"claim ownership (exit {_TRANSPORT_FAIL})",
                file=sys.stderr,
            )
            return _TRANSPORT_FAIL
        if claim_index_mod.UNANSWERABLE in claimants:
            abort_cause = getattr(lookup_result, "abort_cause", None) or "unknown"
            print(
                f"session-claim-cli: who-claims-path: claim ownership for {path!r} "
                "could not be determined (claim index rebuild aborted/unresolvable) "
                "-- NOT a verdict that the path is unclaimed",
                file=sys.stderr,
            )
            print(f"session-claim-cli: who-claims-path: abort cause: {abort_cause}", file=sys.stderr)
            return 1
        rows = []
        for sid in claimants:
            try:
                live = liveness_mod.session_live(sid, cwd)
            except Exception as exc:  # noqa: BLE001 - see is-session-live's own guard
                print("indeterminate")
                print(
                    f"session-claim-cli: who-claims-path: session_live raised "
                    f"{type(exc).__name__}: {exc} for claimant {sid!r} — could not "
                    f"determine liveness (exit {_TRANSPORT_FAIL})",
                    file=sys.stderr,
                )
                return _TRANSPORT_FAIL
            name_col = _render_claimant_name(sid, path, lookup_result)
            kind_col = _render_claimant_kind(sid, path, lookup_result)
            rows.append(f"{sid}\t{'live' if live else 'dead'}\t{name_col}\t{kind_col}")
        if not rows:
            # A5/DD4 -- SC-DR-023's own caveat, cited verbatim rather than
            # paraphrased (Review: coordinator:staff-eng -- register is one
            # fact, once): empty output here reports no RECORDED claimant,
            # never that the path was never written.
            print(
                "session-claim-cli: who-claims-path: no claimant recorded -- "
                "no holder is not evidence no one wrote it: a write through "
                "a subprocess or an unrecognised shape records no claim "
                "(SC-DR-023).",
                file=sys.stderr,
            )
        for row in rows:
            print(row)
        return 0

    if subcmd == "list-stale-claim-handoffs":
        repo_root = rest[0] if rest else None
        try:
            stale_mod = _import_stale_claims_module()
        except _cc_invoke().StaleEngineImportError as exc:
            print(f"session-claim-cli: {exc}", file=sys.stderr)
            return _TRANSPORT_FAIL
        except RuntimeError as exc:
            print(f"session-claim-cli: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
            return _TRANSPORT_FAIL
        except ImportError as exc:
            print(
                f"session-claim-cli: coordinator_core.session.stale_claims not importable: {exc}",
                file=sys.stderr,
            )
            return _TRANSPORT_FAIL
        for entry in stale_mod.list_stale_claim_handoffs(repo_root):
            print(f"{entry.path}\t{entry.claimer_sid}")
        return 0

    print(f"session-claim-cli: unknown subcommand {subcmd!r}", file=sys.stderr)
    return _usage("session-claim-cli")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
