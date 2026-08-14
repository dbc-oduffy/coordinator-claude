# session-claim-cli — CLI trampoline over claude-klabauter
# coordinator_core.session.claims (the claim-lock primitives: claim_artifact /
# release_artifact / clear_claim_if_dead / claim_plan). Direct-import variant,
# mirroring coordinator/bin/archive-stamp-cli.py's resolve/import/dispatch/exit
# shape (template-variant #1: a plain in-process function call after
# resolving CLAUDE_KLABAUTER_ROOT, no cc_invoke/IPC hop — these functions are plain
# module functions in claims.py, NOT registered coordinator_core.invoke ops).
#
# is-session-live / list-stale-claim-handoffs (2026-07-23) are a SEPARATE
# exposure of coordinator_core.session.liveness / coordinator_core.session.
# stale_claims. They were built for a sibling repo's bash skill (DoE's
# workstream-complete Step 0 crash-recovery fix, DoE fd5d61ccb) — that
# consumer NO LONGER EXISTS: DoE removed it at ada28dbe5 when their
# workstream-complete converted to the computed-skill shape and session-shape
# became assembler-computed. Verified 2026-08-10: no DoE surface invokes
# is-session-live, and DoE calls this CLI only for claim-plan and
# release-artifact. Do NOT read the exit-code contract below as a foreign
# contract needing cross-repo coordination to change. It still needs to be
# right: who-claims-path shares these arms and is named as an operator
# inspection instrument in coordinator_core/ops/ceremony/scoped_git_commit.py's
# refusal remedy (_CLAIM_CONFLICT_REMEDY, a human-facing string) — grep does
# not support any automated in-repo stdout consumer of this CLI as of
# 2026-08-10 (Review: staff-eng slice-A). scoped_git_commit.py's own commit
# gate decides via direct `coordinator_core.session.claim_index` /
# `coordinator_core.session.liveness` module imports, never by invoking this
# CLI or parsing its stdout. Claude-klabauter owns liveness FACTS only; it does NOT
# decide chain-terminal disposition (see coordinator_core/session/
# stale_claims.py's module docstring BOUNDARY note).
#
# Subcommands (argv[1] selects; remaining argv forwarded to the mapped
# coordinator_core.session function):
#   claim-artifact <class> <basename> [baton_repo_root] -> claims.claim_artifact(...)
#   release-artifact <class> <basename> [baton_repo_root] -> claims.release_artifact(...)
#   clear-claim-if-dead <class> <basename> [baton_repo_root] -> claims.clear_claim_if_dead(...)
#     AC5 (docs/plans/2026-08-13-liveness-stops-conflating-dead-with-
#     elsewhere.md): for the three classed forms (handoff/memo/plan — NOT
#     the artifact/path-touch plane), a target that cannot be found is
#     self-diagnosing rather than silent. Before dispatching, the CLI
#     resolves the SAME claim directory claims.clear_claim_if_dead itself
#     resolves (core.sessions_dir — the identical public path-arithmetic,
#     never a second parser) and, if absent, emits a stderr note naming the
#     class/basename/path looked up and stating plainly this is NOT a
#     refusal, plus a hint when basename ends in ".md" (the claim key
#     carries no extension). Exit code is UNCHANGED (idempotent no-op ->
#     0, same as before) — the note is additive output only, distinct in
#     BOTH output and exit code from a live-holder refusal (which prints
#     "refusing to clear claim ... holder is live" and exits 1).
#   claim-plan <slug> -> claims.claim_plan(slug)
#   list-claims-by-session <sid> [cwd] -> claims.list_claims_by_session(sid, cwd)
#     stdout: one line per match, TAB-delimited "<class>-claims\t<basename>"
#       (e.g. "handoff-claims\thb-1.md") — reads the claim-record store
#       directly (each claim dir's own session_id file), NEVER the
#       claimed_by/consumed_by frontmatter mirror.
#     exit 0   -> enumeration completed (0 or more matches printed) — an
#                 empty result is success, not failure, same contract as
#                 list-stale-claim-handoffs.
#     exit 3   -> transport failure (CLAUDE_KLABAUTER_ROOT unresolvable / ImportError).
#   is-session-live <SID> [cwd] -> liveness.session_live(SID, cwd)
#     stdout line 1: exactly one word — "live" | "live-elsewhere" | "dead" |
#       "indeterminate". "live" | "dead" | "indeterminate" are UNCHANGED
#       position/spelling from before liveness_basis was added (AC9) — an
#       existing caller that parses only this first token/line sees no
#       difference. "live-elsewhere" (Review: staff-eng-review, C1's ripple)
#       is the exit-1 arm's basis carrying "harness-registry-elsewhere": the
#       session has no dir in THIS repo but the harness registry confirms it
#       live in another one — printing "dead" over that basis reproduced
#       this plan's own Problem statement in this CLI.
#     stdout line 2 (live/dead/live-elsewhere verdicts ONLY, i.e. exit 0 or
#       exit 1 below):
#       "liveness_basis:<value>", where <value> is holder_evidence.
#       liveness_basis()'s vocabulary ("harness-registry" | "stable-pid" |
#       "recency-window" | "recency-window-mtime" | "harness-registry-
#       elsewhere" | "unknown") — additive output (AC7/AC8), never emitted
#       on the malformed-SID or transport-failure paths since those carry no
#       decided verdict to attach a basis to. A basis-derivation failure
#       degrades to "unknown" on this line; it never changes the line-1
#       token or the exit code.
#     exit 0   -> live.
#     exit 1   -> NOT live in THIS repo (dead, or live-elsewhere) — see line
#                 1 to distinguish; exit code is UNCHANGED for compat.
#     exit 2   -> usage error (missing SID arg).
#     exit 3   -> transport failure (CLAUDE_KLABAUTER_ROOT unresolvable / ImportError),
#                 OR liveness.session_live itself raised unexpectedly (e.g.
#                 MissingPsutilError propagating past a Layer-1 arm) — reused
#                 rather than a new code (Review: staff-eng-review A): 3
#                 already means "the claude-klabauter engine could not be reached,
#                 never silently degraded", and an uncaught raise here is
#                 exactly that, not a determinate dead verdict. Line 1 prints
#                 "indeterminate" on this path.
#     exit 4   -> malformed/absent SID (empty, whitespace-only, or containing
#                 any character outside the sid allowlist — see
#                 _sid_looks_valid) — COULD NOT DETERMINE liveness;
#                 a bash caller MUST treat this distinctly from exit 1. Reading
#                 an infra/input error as "dead" is exactly the fail-open shape
#                 this exposure exists to close (see the stub's spec backlink).
#   who-claims-path <path> [cwd] -> claim_index.lookup([path], cwd=cwd) +
#     liveness.session_live(sid, cwd) per claimant
#     Reads the PATH-TOUCH plane (coordinator_core.session.claim_index --
#     `T/R <iso8601> <path>` lines in each session's/agent's touched.txt),
#     a DIFFERENT plane and a DIFFERENT question than
#     `list-claims-by-session` above (which reads the ARTIFACT-CLAIM RECORD
#     STORE -- each <class>-claims/<basename>/session_id file). A session
#     can hold zero artifact claims and still have touched a path; the two
#     subcommands legitimately disagree and neither is wrong. This is the
#     ONLY instrument exposing claim_index.lookup() -- previously it had
#     exactly one consumer in the whole repo (scoped_git_commit.py's commit
#     gate) and no CLI, so an EM hit by that gate's refusal had no way to
#     ask "who touched this path, and are they live?" without reading
#     touched.txt files by hand.
#     stdout: one line per claimant, TAB-delimited "<sid>\t<live|dead>".
#     exit 0   -> enumeration completed (0 or more claimant lines printed);
#                 no claimant is empty output + exit 0, same "empty ==
#                 success" convention as list-claims-by-session.
#     exit 1   -> the path's claim-index entry is claim_index.UNANSWERABLE
#                 (an aborted/unresolvable index rebuild) -- printed to
#                 stderr as "could not determine", NEVER read as
#                 "unclaimed" (an unanswerable index entry authorizing a
#                 silent pass-through would repeat the exact fail-open
#                 shape the commit gate itself refuses to allow). A second
#                 stderr line names WHICH of the three abort causes fired
#                 (claim_index.ABORT_CAUSE_EMPTY_BASE / _CAP_EXCEEDED /
#                 _IO_ERROR, or "unknown" if the lookup result carries none)
#                 -- additive only; the refusal sentence above and this exit
#                 code are unchanged (C1/C2, docs/plans/2026-08-11-claim-
#                 index-abort-cause-and-cli-blindness.md).
#     exit 3   -> transport failure (CLAUDE_KLABAUTER_ROOT unresolvable / ImportError),
#                 OR liveness.session_live raised unexpectedly for one of the
#                 claimants (same reused code as is-session-live above).
#   list-stale-claim-handoffs [repo_root] -> stale_claims.list_stale_claim_handoffs(repo_root)
#     stdout: one line per stale entry, TAB-delimited
#       "<absolute handoff path>\t<dead claimer session id>" — TAB chosen
#       because neither a filesystem path nor a session id can contain one.
#       Zero lines + exit 0 means "no stale claims found", not "could not tell".
#     exit 0   -> enumeration completed (0 or more stale entries printed).
#     exit 3   -> transport failure (CLAUDE_KLABAUTER_ROOT unresolvable / ImportError).
#
# Exit codes: the claim-* subcommands' mapped functions return bool, not an
# int exit code (unlike archive-stamp-cli's archive_stamp functions, which
# return ints passed through verbatim) — this CLI maps bool->exit: True->0,
# False->1. A missing/unresolvable CLAUDE_KLABAUTER_ROOT or an ImportError (this
# trampoline's own transport failure) exits 3 (_TRANSPORT_FAIL, same
# dedicated code archive-stamp-cli uses — "the claude-klabauter engine could not be
# reached," never silently degraded to 0). A usage error (missing/unknown
# subcommand, wrong arity) exits 2. claim-artifact / release-artifact /
# clear-claim-if-dead additionally route through ``_call_claim_bool``, which
# catches the REQUIRED-arg ``ValueError`` those three claims.py functions
# raise on an empty ``class``/``basename`` (a syntactically-complete argv
# that still carries an empty string — usage validation above only checks
# arity) and reports it exit 1 with a clean stderr line, never a raw Python
# traceback. claim-plan needs no such wrapping — its own boundary check
# already returns bool on every input.
from __future__ import annotations
"""session-claim-cli — see the # comment block above for the RAG-bait purpose
text (the polyglot shebang line above makes THIS triple-quoted string a
silently-discarded expression statement, not the module __doc__ — same
convention as archive-stamp-cli)."""

import os
import sys
from pathlib import Path

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402

_TRANSPORT_FAIL = 3
_NOT_LIVE = 1
_MALFORMED_SID = 4


def _import_module():
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    import coordinator_core.session.claims as _mod

    return _mod


def _import_liveness_module():
    """Separate seam from ``_import_module`` (claims) so ``is-session-live``
    tests can stub liveness in isolation without touching the claims stub."""
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    import coordinator_core.session.liveness as _mod

    return _mod


def _import_stale_claims_module():
    """Separate seam from ``_import_module`` (claims) so
    ``list-stale-claim-handoffs`` tests can stub the enumerator in isolation."""
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    import coordinator_core.session.stale_claims as _mod

    return _mod


def _import_core_module():
    """Separate seam from ``_import_module`` (claims) so
    ``clear-claim-if-dead``'s not-found precheck (AC5) can be stubbed
    independently in tests, mirroring the per-functional-area seam split
    above. Only reads ``core.sessions_dir`` — the SAME public path-arithmetic
    ``claims.clear_claim_if_dead`` itself calls, never a second liveness
    parser."""
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    import coordinator_core.session.core as _mod

    return _mod


def _import_claim_index_module():
    """Separate seam from ``_import_module`` (claims) and
    ``_import_liveness_module`` so ``who-claims-path`` tests can stub the
    PATH-TOUCH plane independently of the artifact-claim store and the
    liveness verdict, mirroring the existing per-functional-area seam
    split above."""
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    import coordinator_core.session.claim_index as _mod

    return _mod


def _import_holder_evidence_module():
    """Separate seam from ``_import_liveness_module`` so ``is-session-live``'s
    AC7 basis line can be stubbed independently of the live/dead verdict in
    tests, mirroring the claims/liveness/stale_claims seam split above."""
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    import coordinator_core.pickup_assemble.holder_evidence as _mod

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


_SUBCOMMANDS = (
    "subcommands: claim-artifact | release-artifact | clear-claim-if-dead | "
    "claim-plan | is-session-live | list-stale-claim-handoffs | "
    "list-claims-by-session | who-claims-path"
)

_HELP_FLAGS = ("--help", "-h", "help")


def _usage(prog: str) -> int:
    print(f"usage: {prog} <subcommand> <args...>\n{_SUBCOMMANDS}", file=sys.stderr)
    return 2


def _bool_to_exit(result: bool) -> int:
    return 0 if result else 1


# AC5 — clear-claim-if-dead's classed forms (mkdir-based claim-record store,
# NOT the artifact/path-touch plane, which is a different lookup entirely).
_CLASSED_CLAIM_CLASSES = ("handoff", "memo", "plan")


def _clear_claim_lookup_dir(class_: str, basename: str, baton_repo_root: str):
    """Best-effort resolution of the SAME claim directory
    ``claims.clear_claim_if_dead`` will inspect, so the CLI can tell a caller
    what was looked up and under which key BEFORE the call, when that
    directory turns out not to exist (AC5). Mirrors ``clear_claim_if_dead``'s
    own base resolution byte for byte — ``core.sessions_dir`` is the SAME
    public path-arithmetic function that module already calls, so this is
    not a second parser of anything liveness-shaped, just the identical
    directory-join claims.py performs.

    Returns ``None`` on ANY resolution failure (bad/absent baton root,
    unresolvable sessions dir, transport failure) — callers MUST treat
    ``None`` as "skip the not-found precheck", never as evidence either way;
    ``claims.clear_claim_if_dead`` itself remains the sole authority on the
    actual outcome.
    """
    try:
        if baton_repo_root:
            if not (Path(baton_repo_root) / ".git").is_dir():
                return None
            base = str(Path(baton_repo_root) / ".git" / "coordinator-sessions")
        else:
            base = _import_core_module().sessions_dir(None)
        if not base:
            return None
        return Path(base) / f"{class_}-claims" / basename
    except Exception:  # noqa: BLE001 - best-effort diagnostic only, see docstring
        return None


def _emit_clear_claim_not_found_note(class_: str, basename: str, claim_dir) -> None:
    """AC5: the basename convention is part of the trap — the claim key
    carries no ``.md`` while a caller naturally holds a path that does. Name
    what was looked up and under which key, so a wrong basename is
    self-diagnosing rather than silent. The distinction from a refusal is
    already carried by exit 0 vs exit 1 and by the refusal's own distinct
    message; asserting it in prose is a message-register violation (Review:
    staff-eng-review, docs/wiki/guard-messaging.md B1/B2) and is not
    repeated here."""
    note = (
        f"session-claim-cli: clear-claim-if-dead: no claim at {claim_dir} "
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
        "claim-artifact", "release-artifact", "clear-claim-if-dead", "claim-plan",
        "list-claims-by-session",
    )
    if subcmd in _CLAIM_SUBCOMMANDS:
        try:
            mod = _import_module()
        except RuntimeError as exc:
            print(f"session-claim-cli: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
            return _TRANSPORT_FAIL
        except ImportError as exc:
            print(f"session-claim-cli: coordinator_core.session.claims not importable: {exc}", file=sys.stderr)
            return _TRANSPORT_FAIL

    if subcmd == "claim-artifact":
        if len(rest) < 2:
            return _usage("session-claim-cli claim-artifact <class> <basename> [baton_repo_root]")
        class_, basename = rest[0], rest[1]
        baton_repo_root = rest[2] if len(rest) > 2 else ""
        return _call_claim_bool("claim-artifact", mod.claim_artifact, class_, basename, baton_repo_root)

    if subcmd == "release-artifact":
        if len(rest) < 2:
            return _usage("session-claim-cli release-artifact <class> <basename> [baton_repo_root]")
        class_, basename = rest[0], rest[1]
        baton_repo_root = rest[2] if len(rest) > 2 else ""
        return _call_claim_bool("release-artifact", mod.release_artifact, class_, basename, baton_repo_root)

    if subcmd == "clear-claim-if-dead":
        if len(rest) < 2:
            return _usage("session-claim-cli clear-claim-if-dead <class> <basename> [baton_repo_root]")
        class_, basename = rest[0], rest[1]
        baton_repo_root = rest[2] if len(rest) > 2 else ""
        if class_ in _CLASSED_CLAIM_CLASSES:
            claim_dir = _clear_claim_lookup_dir(class_, basename, baton_repo_root)
            if claim_dir is not None and not claim_dir.is_dir():
                _emit_clear_claim_not_found_note(class_, basename, claim_dir)
        return _call_claim_bool("clear-claim-if-dead", mod.clear_claim_if_dead, class_, basename, baton_repo_root)

    if subcmd == "claim-plan":
        if not rest:
            return _usage("session-claim-cli claim-plan <slug>")
        return _bool_to_exit(mod.claim_plan(rest[0]))

    if subcmd == "list-claims-by-session":
        if not rest:
            return _usage("session-claim-cli list-claims-by-session <sid> [cwd]")
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
        # Review: staff-eng-review — a live-elsewhere peer has no session
        # dir in this repo, so `live` is False here (AC1, session_live's
        # boolean is untouched); printing "dead" over that basis reproduces
        # this plan's own Problem statement in this sibling CLI. "dead" is
        # reserved for every OTHER not-live basis.
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
        except RuntimeError as exc:
            print(f"session-claim-cli: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
            return _TRANSPORT_FAIL
        except ImportError as exc:
            print(
                f"session-claim-cli: coordinator_core.session.liveness not importable: {exc}",
                file=sys.stderr,
            )
            return _TRANSPORT_FAIL
        # Review: staff-eng slice-A P1 #1 — this lookup sits on the same arm
        # the commit hardened for session_live below; an unguarded raise here
        # (OSError on the claim store, a JSON/parse error, a partially-
        # importable module) would escape main() and exit 1 via a raw
        # traceback, indistinguishable from a determinate "confirmed dead"-
        # shaped exit on this CLI. Same three-line guard as its sibling.
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
            # C1 (docs/plans/2026-08-11-claim-index-abort-cause-and-cli-
            # blindness.md) adds `abort_cause` alongside `.complete` on the
            # lookup() result -- additive to this refusal line, never a
            # replacement: the "NOT a verdict that the path is unclaimed"
            # sentence below is unchanged verbatim, and the exit code stays 1.
            abort_cause = getattr(lookup_result, "abort_cause", None) or "unknown"
            print(
                f"session-claim-cli: who-claims-path: claim ownership for {path!r} "
                "could not be determined (claim index rebuild aborted/unresolvable) "
                "-- NOT a verdict that the path is unclaimed",
                file=sys.stderr,
            )
            print(f"session-claim-cli: who-claims-path: abort cause: {abort_cause}", file=sys.stderr)
            return 1
        # Review: staff-eng slice-A P1 #2 — collect every claimant's verdict
        # before printing any of them. Printing per-claimant inside the loop
        # meant a raise on claimant k emitted k-1 well-formed "sid\tstate"
        # rows followed by a bare TAB-less "indeterminate" line — a TAB-
        # splitting consumer parses that as a claimant literally named
        # "indeterminate" with an empty state, not an abort marker. Buffering
        # keeps the failure path's stdout exactly ["indeterminate"], matching
        # is-session-live's own single-line failure contract.
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
            rows.append(f"{sid}\t{'live' if live else 'dead'}")
        for row in rows:
            print(row)
        return 0

    if subcmd == "list-stale-claim-handoffs":
        repo_root = rest[0] if rest else None
        try:
            stale_mod = _import_stale_claims_module()
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
