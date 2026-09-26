#     (--kind is REQUIRED, keyword-only, on the mapped
#     canonical enum, coordinator_core.ops.handoff_stamp._SHIPPED_IN_KIND_ENUM.)
#     # here; the usage rows below and _PROSE_DISPOSITION_FLAGS's comment
#     REQUIRED: a missing --by is a usage error at this CLI layer, and the
#     THE AUTHORSHIP GATE IS ANTI-ACCIDENT, NOT ANTI-ADVERSARY (DR-247 § 3):
from __future__ import annotations
"""archive-stamp-cli — see the # comment block above for the RAG-bait purpose
text (the polyglot shebang line above makes THIS triple-quoted string a
silently-discarded expression statement, not the module __doc__ — see
tasks/2026-07-16-clean-slate-recon/PORTER-BRIEF-ADDENDUM.md § 1)."""

import os
import re
import sys

_TRANSPORT_FAIL = 3


def _import_module():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    import coordinator_core.archive_stamp as _mod

    return _mod


_SUBCOMMANDS = (
    "subcommands: stamp-shipped-in | ship-handoff | claim-handoff | "
    "claim-memo-stamp | action-memo | resolve-memo | release-memo-revert | "
    "stamp-plan-implemented | stamp-plan-superseded | gate-recheck-handoff | close-handoff | "
    "repark-handoff | unclaim-handoff | chain-archive-handoff | "
    "supersede-archive-handoff | repair-archived-shipped-in | "
    "repair-archived-deployment-state | correct-handoff-body\n"
    "\n"
    "NOTE — close-handoff <path> --reason <cancelled|displaced|stale> is the live "
    "door for retiring a dead baton (handoff.transition verb 'close'). It stamps "
    "deployment_state: closed, closed_reason, and pickup_ready: false. cancelled = "
    "deliberate stop; displaced = replaced with NO lineage edge; stale = overtaken "
    "by events. A successor WITH a lineage edge is supersede-archive-handoff "
    "--continued-into, which is 'continued', not 'closed'.\n"
    "\n"
    "NOTE — consume-handoff / unconsume-handoff are accepted as deprecated "
    "aliases of claim-handoff / unclaim-handoff (not advertised above).\n"
    "\n"
    "NOTE — chain-archive-handoff / supersede-archive-handoff (archiving: wraps "
    "handoff.archive_transition, which moves/archives the file in addition to "
    "stamping it) — see this file's top comment block for the full distinction.\n"
    "\n"
    "NOTE — repair-archived-shipped-in / repair-archived-deployment-state are the "
    "ONLY verbs that reach an already-archived handoff (archive/handoffs/); every "
    "other verb above is state/handoffs/-only. See this file's top comment block.\n"
    "\n"
    "NOTE — correct-handoff-body's authorship gate is ANTI-ACCIDENT, NOT "
    "ANTI-ADVERSARY (DR-247 § 3): a caller-controlled session-id env var passed "
    "into a caller-spawned subprocess is not a security boundary; the real "
    "control is the stamped, auditable correction note the op writes on every "
    "applied correction. See this file's top comment block."
)

_HELP_FLAGS = ("--help", "-h", "help")

_SUBCOMMAND_HELP_FLAGS = ("--help", "-h")

# one place. Kept out of `_SUBCOMMANDS` deliberately — see that NOTE text —
# but still given `_SUBCOMMAND_USAGE` rows so `<alias> --help` answers
_DEPRECATED_ALIASES = {
    "consume-handoff": "claim-handoff",
    "unconsume-handoff": "unclaim-handoff",
}

_SUBCOMMAND_USAGE = {
    "stamp-shipped-in": (
        "archive-stamp-cli stamp-shipped-in <handoff_path> "
        "[--allow-branch-tip-fallback] [--sha <SHA>] [--kind <kind>] [--force]"
    ),
    "ship-handoff": (
        "archive-stamp-cli ship-handoff <handoff_path> [<SHA>] "
        "[--sha <SHA>] [--archive] [--force]"
    ),
    "claim-handoff": "archive-stamp-cli claim-handoff <handoff_path>",
    # Deprecated alias — retained-for-compat, not advertised in _SUBCOMMANDS.
    "consume-handoff": "archive-stamp-cli consume-handoff <handoff_path>",
    "claim-memo-stamp": "archive-stamp-cli claim-memo-stamp <memo_path>",
    "action-memo": (
        "archive-stamp-cli action-memo <memo_path> [disposition-flags...]\n"
        "  NOTE — the prose-bearing disposition flags each take a lossless\n"
        "  file sibling: --decision-note-file / --actioned-note-file /\n"
        "  --supersede-note-file <path>. The remaining flags are the ENGINE's\n"
        "  (coordinator_core/archive_stamp.py :: _DISPOSITION_FLAGS); this\n"
        "  file forwards its tail verbatim and does not restate them."
    ),
    "resolve-memo": (
        "archive-stamp-cli resolve-memo <memo_path> [disposition-flags...]\n"
        "  NOTE — same prose file siblings as action-memo.\n"
        "  disposition-flags (engine's, coordinator_core/archive_stamp.py ::\n"
        "  _DISPOSITION_FLAGS/_DISPOSITION_BOOL_FLAGS): --decision <value>,\n"
        "  --decision-note <text>, --realized-by <value>, --actioned-note <text>,\n"
        "  --distill-fate <value>, --in-repo-capture <value>,\n"
        "  --superseded-by <memo_path>, --supersede-note <text>,\n"
        "  --supersede-realized-by <value>, --supersede-at <ISO-date>,\n"
        "  --correct-realization (no value). --superseded-by is mutually exclusive\n"
        "  with --decision/--actioned-note — alternative terminal shapes, not\n"
        "  combinable."
    ),
    "release-memo-revert": "archive-stamp-cli release-memo-revert <memo_path>",
    "stamp-plan-implemented": "archive-stamp-cli stamp-plan-implemented <plan_path>",
    "stamp-plan-superseded": (
        "archive-stamp-cli stamp-plan-superseded <plan_path> --by <successor>"
    ),
    "gate-recheck-handoff": (
        "archive-stamp-cli gate-recheck-handoff <handoff_path> <at> [--cleared]"
    ),
    "close-handoff": (
        "archive-stamp-cli close-handoff <handoff_path> "
        "--reason <cancelled|displaced|stale>"
    ),
    "repark-handoff": "archive-stamp-cli repark-handoff <handoff_path>",
    "unclaim-handoff": (
        "archive-stamp-cli unclaim-handoff <handoff_path> [note] [--note-file <path>] "
        "[--reaped-from <sid>]\n"
        "  NOTE — [note] and --reaped-from share one token stream with no `--`\n"
        "  separator: a note whose literal text is the string \"--reaped-from\"\n"
        "  cannot be passed positionally (it is parsed as the flag and, absent a\n"
        "  following value, rejected as a usage error). This is a pre-existing\n"
        "  collision in the CLI's flag/positional grammar, not specific to this\n"
        "  flag."
    ),
    # Deprecated alias — retained-for-compat, not advertised in _SUBCOMMANDS.
    "unconsume-handoff": (
        "archive-stamp-cli unconsume-handoff <handoff_path> [note] [--note-file <path>] "
        "[--reaped-from <sid>]\n"
        "  NOTE — [note] and --reaped-from share one token stream with no `--`\n"
        "  separator: a note whose literal text is the string \"--reaped-from\"\n"
        "  cannot be passed positionally (it is parsed as the flag and, absent a\n"
        "  following value, rejected as a usage error). This is a pre-existing\n"
        "  collision in the CLI's flag/positional grammar, not specific to this\n"
        "  flag."
    ),
    "chain-archive-handoff": (
        "archive-stamp-cli chain-archive-handoff <handoff_path> [--exclude <path>]..."
    ),
    "supersede-archive-handoff": (
        "archive-stamp-cli supersede-archive-handoff <handoff_path> "
        "--continued-into <successor> [--exclude <path>]..."
    ),
    "repair-archived-shipped-in": (
        "archive-stamp-cli repair-archived-shipped-in <handoff_path> "
        "(--reason <reason> | --reason-file <path>) (--sha <SHA> | --unset)"
    ),
    "repair-archived-deployment-state": (
        "archive-stamp-cli repair-archived-deployment-state <handoff_path> "
        "(--reason <reason> | --reason-file <path>) --deployment-state <state> "
        "[--continued-into <successor>] [--continued-into-override] "
        "[--closed-reason <cancelled|displaced|stale>]"
    ),
    "correct-handoff-body": (
        "archive-stamp-cli correct-handoff-body <handoff_path> "
        "(--old-string <old> | --old-string-file <path>) "
        "(--new-string <new> | --new-string-file <path>)\n"
        "  PROSE TRAVELS AS A FILE ON WINDOWS: the .cmd forwarder truncates a "
        "multi-line inline value at the first newline, silently. A newline-bearing "
        "--old-string/--new-string is REFUSED here and names its -file sibling; a "
        "single-line value containing a quote or a space is corrupted before this "
        "process starts and cannot be detected -- prefer the -file form for prose. "
        "See docs/wiki/windows-first-class.md.\n"
        "  THE AUTHORSHIP GATE IS ANTI-ACCIDENT, NOT ANTI-ADVERSARY (DR-247 § 3): "
        "authorship is a caller-controlled env-var lookup inside a caller-spawned "
        "subprocess, not an enforced access-control boundary; the real control is "
        "the stamped, auditable correction note the op writes on every applied "
        "correction."
    ),
}


def _usage(prog: str) -> int:
    print(f"usage: {prog} <subcommand> <args...>\n{_SUBCOMMANDS}", file=sys.stderr)
    return 2


def _usage_line(usage: str) -> int:
    """Print a complete per-subcommand usage line verbatim and refuse (exit 2).

    Distinct from ``_usage``, which takes a PROGRAM name and appends the
    top-level ``<subcommand> <args...>`` synopsis plus the whole subcommand
    list. Handing ``_usage`` an already-complete usage line produced
    ``usage: archive-stamp-cli ship-handoff <handoff_path> ... <subcommand>
    <args...>`` followed by every other verb — the noise that made the ship
    path discoverable only by failing into it (project-rag-em memo,
    2026-07-28).
    """
    print(f"usage: {usage}", file=sys.stderr)
    return 2


def _scan_repeatable_flag(tail: list[str], flag: str) -> tuple[list[str] | None, str | None]:
    """Order-independent scan for a repeatable `--flag value` pair (e.g. --exclude,
    which handoff.archive_transition accepts as a list). Returns (values, error) —
    values is None (not an error, just absent) when the flag never appears; error is
    a message string when a trailing flag has no value. Mirrors the order-independent
    flag scan already used for --sha/--allow-branch-tip-fallback above."""
    values: list[str] = []
    i = 0
    while i < len(tail):
        if tail[i] == flag:
            if i + 1 >= len(tail):
                return None, f"{flag} requires a value"
            values.append(tail[i + 1])
            i += 2
        else:
            i += 1
    return (values or None), None


_FLAG_RE = re.compile(r"--[a-z][a-z0-9-]*")

# Verbs taking a FREE-TEXT positional whose value can legitimately begin with
_FREE_TEXT_POSITIONAL_VERBS = frozenset({"unclaim-handoff", "unconsume-handoff"})

# so `_SUBCOMMAND_USAGE` cannot enumerate it and this guard has nothing to check
# against. Deliberately does NOT match `[--exclude <path>]...` — a REPEATABLE
_OPEN_FLAG_TAIL_RE = re.compile(r"\[[a-z][a-z0-9-]*\.\.\.\]")


def _reject_unknown_flags(subcmd: str, rest: list[str]) -> int | None:
    """Refuse a `--`-prefixed token this verb's own usage line does not declare.

    Every verb here hand-slices `argv` and reads the positionals it wants
    (`rest[0]`, `rest[1]`, an order-independent scan for its own flags); nothing
    ever looked at what was left over. So `repark-handoff <path> --gate-note "..."`
    reparked the handoff, discarded the note, and exited 0 — the caller is told
    the write succeeded, and the part they cared about is gone. That is the
    failure this refuses: a silent partial write reported as a full one, not a
    typo-catcher.

    THE ACCEPTED SET IS DERIVED FROM `_SUBCOMMAND_USAGE`, NEVER HAND-LISTED. That
    table is already the declared contract, and a second copy of it here would go
    stale the first time a verb gained a flag — the same defect shape as a
    hand-copied module list. A flag that works but is undocumented is a
    documentation bug this correctly surfaces.

    VALUES ARE NOT FLAGS: the token after a recognized flag is skipped, so
    `--reason --weird` passes `--weird` through as the reason rather than
    refusing it. Only tokens in flag POSITION are checked.

    AN OPEN FLAG TAIL DECLINES RATHER THAN REFUSES. `action-memo` and
    `resolve-memo` declare `[disposition-flags...]` and forward their tail to
    the engine verbatim, so their vocabulary lives in the engine and this
    table cannot enumerate it. The first version of this guard derived an
    EMPTY `known` set for them and therefore refused every documented
    disposition flag with exit 2, making the whole memo-disposition surface
    unreachable through this CLI until a caller resorted to invoking
    `cs_action_memo` directly (project-rag-df, 2026-08-31). This file's own
    `_SUBCOMMAND_HELP_FLAGS` comment already stated the rule -- "forwards its
    tail to the engine verbatim, and a disposition flag or value is free to be
    any string" -- and the guard was written past it.

    NOT FIXED BY FAILING OPEN ON AN EMPTY `known` SET, which was the obvious
    shape and is wrong: a verb that legitimately takes NO flags (`claim-handoff
    <path>`) also derives an empty set, and there refusing an undeclared flag
    is precisely the silent-partial-write this guard exists for. The
    discriminator is the usage line's SHAPE, not the size of the set it
    yields. Same polarity lesson as
    `state/lessons/2026-08-31-a-fail-safe-direction-is-only-safe-for-o.yaml`:
    this gate REFUSES, so its uncertain direction must be to decline.
    """
    if subcmd in _FREE_TEXT_POSITIONAL_VERBS:
        return None
    usage = _SUBCOMMAND_USAGE.get(subcmd)
    if usage is None:
        return None
    if _OPEN_FLAG_TAIL_RE.search(usage):
        return None
    known = set(_FLAG_RE.findall(usage))
    i = 0
    while i < len(rest):
        tok = rest[i]
        if tok in known:
            i += 2
            continue
        if tok.startswith("--"):
            print(
                f"archive-stamp-cli: {subcmd}: unrecognized option {tok}\n"
                f"usage: {usage}",
                file=sys.stderr,
            )
            return 2
        i += 1
    return None


# `%*` in a generated `.cmd` launcher is an UN-RE-QUOTED expansion, and cmd.exe
# REMEDY CHOSEN DELIBERATELY, NOT DEFAULTED. The other candidate was enrolling
# this entrypoint in `gen-launcher-shim.py::_RAW_CMDLINE_ENTRYPOINTS` /
# `substrate.py::_RAW_CMDLINE_TARGETS` -- the `%CMDCMDLINE%` capture-and-recover
#   3. The membership rule beside `_RAW_CMDLINE_ENTRYPOINTS` already routes this
# NOT COVERED HERE, deliberately: a SINGLE-LINE prose value containing a quote


def _scan_flag_value(tail: list[str], flag: str) -> str | None:
    """Order-independent scan for `flag <value>`, mirroring the --sha idiom used
    throughout this file. Returns None when the flag is absent OR trails with no
    value; every caller here already refuses on a missing required value."""
    if flag not in tail:
        return None
    idx = tail.index(flag)
    if idx + 1 >= len(tail):
        return None
    return tail[idx + 1]


def _resolve_prose(
    tail: list[str],
    flag: str,
    *,
    allow_empty: bool = False,
) -> tuple[str | None, str | None]:
    """Resolve `flag` from its inline form or its `<flag>-file` sibling.

    Returns `(value, error_message)` -- exactly one is non-None, except when the
    flag is absent in BOTH forms, which yields `(None, None)` so the caller
    emits its own verb-specific "required" refusal and usage line unchanged.

    Delegates to `coordinator_core.argv_fidelity` (imported lazily: this file
    must answer `--help` and a usage error without a resolvable CLAUDE_KLABAUTER_ROOT, so
    nothing engine-side may be imported at module scope). `refuse_newline_argv`
    runs FIRST -- a newline-bearing inline value is refused on its own terms,
    naming the file sibling, rather than surfacing as some downstream mutual-
    exclusion or empty-value error.
    """
    return _resolve_prose_pair(
        _scan_flag_value(tail, flag),
        _scan_flag_value(tail, f"{flag}-file"),
        flag,
        allow_empty=allow_empty,
    )


def _resolve_prose_pair(
    inline: str | None,
    from_file: str | None,
    flag: str,
    *,
    allow_empty: bool = False,
) -> tuple[str | None, str | None]:
    """The half of `_resolve_prose` that does not assume a `--flag <value>` scan.

    Split out for `unclaim-handoff`, whose note is POSITIONAL: its inline value
    cannot be scanned by flag name -- that verb hard-refuses a leftover `--note`
    precisely so the note is never mistaken for one -- but everything downstream
    of the scan is identical (newline refusal, mutual exclusion, file read,
    hollow-record refusal) and must not be re-rolled per verb. Callers that have
    a flag to scan use `_resolve_prose`; this exists for the shape that has not.
    """
    from coordinator_core.argv_fidelity import (
        ArgvFidelityError,
        refuse_newline_argv,
        resolve_body,
    )

    if inline is None and from_file is None:
        return None, None
    try:
        refuse_newline_argv(inline, flag_name=flag)
        return resolve_body(
            inline, from_file, flag_name=flag, allow_empty=allow_empty
        ), None
    except ArgvFidelityError as exc:
        return None, f"archive-stamp-cli: {flag}: {exc}"


# NOT A MULTI-LINE CHANNEL. `memo_transition._validate_disposition` refuses a
# loudly. What the file leg buys is LOSSLESS transport of a single-line note
_PROSE_DISPOSITION_FLAGS = ("--decision-note", "--actioned-note", "--supersede-note")


def _resolve_disposition_prose(
    tail: list[str],
) -> tuple[list[str] | None, str | None]:
    """Normalise each `--<note>-file <path>` in a disposition tail to its inline form.

    Returns `(rewritten_tail, None)` or `(None, error_message)`. The rewrite is
    what lets `action-memo`/`resolve-memo` keep forwarding their tail to the
    engine VERBATIM: no `-file` token ever reaches the op, the engine's flag
    vocabulary is unchanged, and `_DISPOSITION_FLAGS` stays the single
    declaration of what a disposition accepts. Resolved flags are re-appended
    at the tail's end -- `_parse_disposition_args` is order-independent.

    THE WALK IS A TRUE MIRROR of `_parse_disposition_args`, not just of its
    three prose flags: `_DISPOSITION_FLAGS` and `_DISPOSITION_BOOL_FLAGS` are
    imported LAZILY (this file must answer `--help` and a usage error without
    a resolvable engine root -- same reason `_resolve_prose_pair` imports
    `coordinator_core.argv_fidelity` inside its own body, not at module
    scope), and every token in the tail is classified against that full
    vocabulary before it is treated as free-standing. Without this, any of
    the engine's OTHER 2-token flags (`--decision`, `--realized-by`,
    `--superseded-by`, ...) walked one token at a time here let its own value
    -- or a missing-value slot -- land on a prose flag's name and get
    misread as the START of a fresh pair, silently rewriting the tail this
    function hands back (P1, code-reviewer a5c86ae1f7c7c0a12, Finding 1). A
    bool flag consumes one token; a non-prose `_DISPOSITION_FLAGS` member
    consumes two and both are appended VERBATIM -- its value is never
    inspected, only counted -- so a value that happens to equal a prose flag
    name stays that flag's value on both sides of the seam, exactly as
    `_parse_disposition_args` sees it.
    """
    from coordinator_core.archive_stamp import _DISPOSITION_BOOL_FLAGS, _DISPOSITION_FLAGS

    _FILE = "-file"
    out: list[str] = []
    seen: dict[str, list[str | None]] = {}
    i = 0
    while i < len(tail):
        tok = tail[i]
        base, slot = None, 0
        if tok in _PROSE_DISPOSITION_FLAGS:
            base = tok
        elif tok.endswith(_FILE) and tok[: -len(_FILE)] in _PROSE_DISPOSITION_FLAGS:
            base, slot = tok[: -len(_FILE)], 1
        if base is not None:
            if i + 1 >= len(tail):
                return None, f"archive-stamp-cli: {tok} requires a value"
            pair = seen.setdefault(base, [None, None])
            if pair[slot] is not None:
                return None, f"archive-stamp-cli: {tok} may only be given once"
            pair[slot] = tail[i + 1]
            i += 2
            continue
        if tok in _DISPOSITION_BOOL_FLAGS:
            out.append(tok)
            i += 1
            continue
        if tok in _DISPOSITION_FLAGS and i + 1 < len(tail):
            out.append(tok)
            out.append(tail[i + 1])
            i += 2
            continue
        out.append(tok)
        i += 1

    for base, (inline, from_file) in seen.items():
        value, err = _resolve_prose_pair(inline, from_file, base)
        if err is not None:
            return None, err
        if value is not None:
            out += [base, value]
    return out, None


def main(argv: list[str]) -> int:
    if not argv:
        return _usage("archive-stamp-cli")
    subcmd, rest = argv[0], argv[1:]

    if subcmd in _HELP_FLAGS:
        print(f"usage: archive-stamp-cli <subcommand> <args...>\n{_SUBCOMMANDS}")
        return 0

    if subcmd in _SUBCOMMAND_USAGE and any(t in _SUBCOMMAND_HELP_FLAGS for t in rest):
        print(f"usage: {_SUBCOMMAND_USAGE[subcmd]}")
        return 0

    # engine import (a usage error must not need a resolvable CLAUDE_KLABAUTER_ROOT).
    _bad_flag = _reject_unknown_flags(subcmd, rest)
    if _bad_flag is not None:
        return _bad_flag

    try:
        mod = _import_module()
    except RuntimeError as exc:
        print(f"archive-stamp-cli: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL
    except ImportError as exc:
        print(f"archive-stamp-cli: coordinator_core.archive_stamp not importable: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL

    if subcmd == "stamp-shipped-in":
        if not rest:
            return _usage_line(_SUBCOMMAND_USAGE["stamp-shipped-in"])
        # equivalent (coordinator-archive-stamp.sh, retired 2026-07-19 BIG_PORT); both
        allow_fallback = "--allow-branch-tip-fallback" in rest[1:]
        sha = None
        if "--sha" in rest[1:]:
            idx = rest.index("--sha")
            if idx + 1 >= len(rest):
                return _usage_line(_SUBCOMMAND_USAGE["stamp-shipped-in"])
            sha = rest[idx + 1]
        # DR-096 made `kind` REQUIRED and keyword-only on stamp_shipped_in with no
        kind = None
        if "--kind" in rest[1:]:
            idx = rest.index("--kind")
            if idx + 1 >= len(rest):
                return _usage_line(_SUBCOMMAND_USAGE["stamp-shipped-in"])
            kind = rest[idx + 1]
        if kind is None:
            kind = "ship-commit" if (sha and sha.strip()) else "scope-derived"
        else:
            try:
                from coordinator_core.ops.handoff_stamp import (
                    _SHIPPED_IN_KIND_ENUM,
                )
            except ImportError as exc:
                print(
                    "archive-stamp-cli: coordinator_core.ops.handoff_stamp not "
                    f"importable: {exc}",
                    file=sys.stderr,
                )
                return _TRANSPORT_FAIL
            if kind not in _SHIPPED_IN_KIND_ENUM:
                print(
                    f"archive-stamp-cli stamp-shipped-in: unknown --kind {kind!r} "
                    f"— must be one of {sorted(_SHIPPED_IN_KIND_ENUM)}",
                    file=sys.stderr,
                )
                return _usage_line(_SUBCOMMAND_USAGE["stamp-shipped-in"])
        return mod.stamp_shipped_in(
            rest[0],
            kind=kind,
            allow_branch_tip_fallback=allow_fallback,
            sha=sha,
            force="--force" in rest[1:],
        ).exit_code

    if subcmd == "ship-handoff":
        if not rest:
            return _usage_line(_SUBCOMMAND_USAGE["ship-handoff"])
        # Deliberately a SEPARATE verb from stamp-shipped-in: stamp-shipped-in
        handoff_path = rest[0]
        tail = rest[1:]
        archive = False
        force = False
        sha_flag: str | None = None
        positional_sha: str | None = None
        i = 0
        while i < len(tail):
            tok = tail[i]
            if tok == "--archive":
                archive = True
                i += 1
            elif tok == "--force":
                force = True
                i += 1
            elif tok == "--sha":
                if i + 1 >= len(tail):
                    return _usage_line(_SUBCOMMAND_USAGE["ship-handoff"])
                sha_flag = tail[i + 1]
                i += 2
            else:
                if positional_sha is not None:
                    print(
                        f"archive-stamp-cli: ship-handoff: unrecognized argument {tok!r}",
                        file=sys.stderr,
                    )
                    return 2
                positional_sha = tok
                i += 1

        if (
            positional_sha is not None
            and sha_flag is not None
            and positional_sha != sha_flag
        ):
            print(
                "archive-stamp-cli: ship-handoff: conflicting sha values — "
                f"positional {positional_sha!r} vs --sha {sha_flag!r}",
                file=sys.stderr,
            )
            return 2

        sha = sha_flag if sha_flag is not None else positional_sha
        return mod.cs_ship_handoff(handoff_path, archive=archive, sha=sha, force=force)

    if subcmd == "claim-handoff" or _DEPRECATED_ALIASES.get(subcmd) == "claim-handoff":
        if not rest:
            return _usage(f"archive-stamp-cli {subcmd} <handoff_path>")
        handoff_path = rest[0]
        result = mod.cs_claim_handoff(handoff_path, return_result=True)
        rc = int(result.get("exit_code", 1))
        if rc == 0:
            sid = mod.resolve_current_session_id()
            print(f"archive-stamp-cli: claimed {handoff_path} (claimed_by {sid})")
            writes = result.get("writes") or {}
            failed = [field for field, landed in writes.items() if not landed]
            if failed:
                print(
                    "archive-stamp-cli: WARNING — best-effort write(s) did not land: "
                    + ", ".join(sorted(failed))
                )
        return rc

    if subcmd == "claim-memo-stamp":
        if not rest:
            return _usage("archive-stamp-cli claim-memo-stamp <memo_path>")
        return mod.cs_claim_memo_stamp(rest[0])

    if subcmd in ("action-memo", "resolve-memo"):
        if not rest:
            return _usage(_SUBCOMMAND_USAGE[subcmd])
        extras: list[str] = []
        for token in rest[1:]:
            if token.startswith("-"):
                break
            extras.append(token)
        if extras:
            print(
                f"archive-stamp-cli {subcmd}: takes ONE memo, and "
                f"{', '.join(repr(t) for t in extras)} would be silently ignored "
                "— re-run once per memo",
                file=sys.stderr,
            )
            return 2
        disposition, err = _resolve_disposition_prose(rest[1:])
        if err is not None:
            print(err, file=sys.stderr)
            return 2
        fn = mod.cs_action_memo if subcmd == "action-memo" else mod.cs_resolve_memo
        return fn(rest[0], *disposition)

    if subcmd == "release-memo-revert":
        if not rest:
            return _usage("archive-stamp-cli release-memo-revert <memo_path>")
        return mod.cs_release_memo_revert(rest[0])

    if subcmd == "stamp-plan-implemented":
        if not rest:
            return _usage("archive-stamp-cli stamp-plan-implemented <plan_path>")
        return mod.cs_stamp_plan_implemented(rest[0])

    if subcmd == "stamp-plan-superseded":
        if not rest:
            return _usage_line(_SUBCOMMAND_USAGE["stamp-plan-superseded"])
        plan_path, tail = rest[0], rest[1:]
        by = _scan_flag_value(tail, "--by")
        if not by:
            print(
                "archive-stamp-cli: stamp-plan-superseded: --by <successor> "
                "is required",
                file=sys.stderr,
            )
            return 2
        return mod.cs_stamp_plan_superseded(plan_path, by)

    if subcmd == "gate-recheck-handoff":
        if len(rest) < 2:
            return _usage("archive-stamp-cli gate-recheck-handoff <handoff_path> <at> [--cleared]")
        cleared = "--cleared" in rest[2:]
        return mod.cs_gate_recheck_handoff(rest[0], rest[1], cleared=cleared)

    if subcmd == "close-handoff":
        if not rest:
            return _usage_line(_SUBCOMMAND_USAGE["close-handoff"])
        # stamp-shipped-in/ship-handoff above. --reason is REQUIRED (not
        handoff_path, tail = rest[0], rest[1:]
        reason: str | None = None
        if "--reason" in tail:
            idx = tail.index("--reason")
            if idx + 1 >= len(tail):
                return _usage_line(_SUBCOMMAND_USAGE["close-handoff"])
            reason = tail[idx + 1]
        if not reason:
            print(
                "archive-stamp-cli: close-handoff: --reason "
                "<cancelled|displaced|stale> is required",
                file=sys.stderr,
            )
            return 2
        return mod.cs_close_handoff(handoff_path, reason)

    if subcmd == "repark-handoff":
        if not rest:
            return _usage("archive-stamp-cli repark-handoff <handoff_path>")
        return mod.cs_repark_handoff(rest[0])

    if subcmd == "unclaim-handoff" or _DEPRECATED_ALIASES.get(subcmd) == "unclaim-handoff":
        if not rest:
            return _usage(f"archive-stamp-cli {subcmd} <handoff_path> [note] [--reaped-from <sid>]")
        handoff_path, tail = rest[0], rest[1:]
        reaped_from = None
        if "--reaped-from" in tail:
            idx = tail.index("--reaped-from")
            if idx + 1 >= len(tail):
                return _usage(
                    f"archive-stamp-cli {subcmd} <handoff_path> [note] [--reaped-from <sid>]"
                )
            reaped_from = tail[idx + 1]
            tail = tail[:idx] + tail[idx + 2 :]
            if "--reaped-from" in tail:
                return _usage(
                    f"archive-stamp-cli {subcmd} <handoff_path> [note] [--reaped-from <sid>]"
                    " — --reaped-from may only be given once"
                )
        note_from_file: str | None = None
        if "--note-file" in tail:
            idx = tail.index("--note-file")
            if idx + 1 >= len(tail):
                return _usage_line(_SUBCOMMAND_USAGE[subcmd])
            note_from_file = tail[idx + 1]
            tail = tail[:idx] + tail[idx + 2:]
            if "--note-file" in tail:
                return _usage(
                    f"archive-stamp-cli {subcmd} <handoff_path> [note] "
                    "[--note-file <path>] [--reaped-from <sid>]"
                    " -- --note-file may only be given once"
                )

        flagged = [token for token in tail if token.startswith("--")]
        if flagged:
            return _usage(
                f"archive-stamp-cli {subcmd} <handoff_path> [note] [--reaped-from <sid>]"
                f" — unrecognized flag(s) {flagged!r}; the note is POSITIONAL"
                " (a note whose own text begins with '--' cannot be passed here)"
            )
        if len(tail) > 1:
            return _usage(
                f"archive-stamp-cli {subcmd} <handoff_path> [note] [--reaped-from <sid>]"
                f" — {len(tail)} positional notes given; quote the note as ONE argument"
            )
        note, note_err = _resolve_prose_pair(
            tail[0] if tail else None, note_from_file, "--note"
        )
        if note_err:
            print(note_err, file=sys.stderr)
            return 2
        return mod.cs_unclaim_handoff(handoff_path, note, reaped_from)

    if subcmd == "chain-archive-handoff":
        if not rest:
            return _usage_line(_SUBCOMMAND_USAGE["chain-archive-handoff"])
        handoff_path, tail = rest[0], rest[1:]
        exclude, err = _scan_repeatable_flag(tail, "--exclude")
        if err:
            print(f"archive-stamp-cli: chain-archive-handoff: {err}", file=sys.stderr)
            return 2
        return mod.cs_chain_archive_handoff(handoff_path, exclude=exclude)

    if subcmd == "supersede-archive-handoff":
        if not rest:
            return _usage_line(_SUBCOMMAND_USAGE["supersede-archive-handoff"])
        handoff_path, tail = rest[0], rest[1:]
        exclude, err = _scan_repeatable_flag(tail, "--exclude")
        if err:
            print(f"archive-stamp-cli: supersede-archive-handoff: {err}", file=sys.stderr)
            return 2
        continued_into = None
        if "--continued-into" in tail:
            idx = tail.index("--continued-into")
            if idx + 1 >= len(tail):
                return _usage_line(_SUBCOMMAND_USAGE["supersede-archive-handoff"])
            continued_into = tail[idx + 1]
        if not continued_into:
            print(
                "archive-stamp-cli: supersede-archive-handoff: --continued-into "
                "<successor> is required",
                file=sys.stderr,
            )
            return 2
        return mod.cs_supersede_archive_handoff(handoff_path, continued_into, exclude=exclude)

    if subcmd == "repair-archived-shipped-in":
        if not rest:
            return _usage_line(_SUBCOMMAND_USAGE["repair-archived-shipped-in"])
        handoff_path, tail = rest[0], rest[1:]
        reason, reason_err = _resolve_prose(tail, "--reason")
        if reason_err:
            print(reason_err, file=sys.stderr)
            return 2
        if not reason:
            print(
                "archive-stamp-cli: repair-archived-shipped-in: --reason <reason> "
                "(or --reason-file <path>) is required",
                file=sys.stderr,
            )
            return 2
        sha = None
        if "--sha" in tail:
            idx = tail.index("--sha")
            if idx + 1 >= len(tail):
                return _usage_line(_SUBCOMMAND_USAGE["repair-archived-shipped-in"])
            sha = tail[idx + 1]
        unset = "--unset" in tail
        if bool(sha) == bool(unset):
            print(
                "archive-stamp-cli: repair-archived-shipped-in: exactly one of "
                "--sha <SHA> or --unset is required",
                file=sys.stderr,
            )
            return 2
        return mod.cs_repair_archived_shipped_in(handoff_path, reason, sha=sha, unset=unset)

    if subcmd == "repair-archived-deployment-state":
        if not rest:
            return _usage_line(_SUBCOMMAND_USAGE["repair-archived-deployment-state"])
        handoff_path, tail = rest[0], rest[1:]

        reason, reason_err = _resolve_prose(tail, "--reason")
        if reason_err:
            print(reason_err, file=sys.stderr)
            return 2
        if not reason:
            print(
                "archive-stamp-cli: repair-archived-deployment-state: "
                "--reason <reason> (or --reason-file <path>) is required",
                file=sys.stderr,
            )
            return 2
        deployment_state = _scan_flag_value(tail, "--deployment-state")
        if not deployment_state:
            print(
                "archive-stamp-cli: repair-archived-deployment-state: "
                "--deployment-state <state> is required",
                file=sys.stderr,
            )
            return 2
        continued_into = _scan_flag_value(tail, "--continued-into")
        continued_into_override = "--continued-into-override" in tail
        closed_reason = _scan_flag_value(tail, "--closed-reason")
        return mod.cs_repair_archived_deployment_state(
            handoff_path,
            reason,
            deployment_state,
            continued_into=continued_into,
            continued_into_override=continued_into_override,
            closed_reason=closed_reason,
        )

    if subcmd == "correct-handoff-body":
        if not rest:
            return _usage_line(_SUBCOMMAND_USAGE["correct-handoff-body"])
        handoff_path, tail = rest[0], rest[1:]

        old_string, err = _resolve_prose(tail, "--old-string")
        if err:
            print(err, file=sys.stderr)
            return 2
        if old_string is None:
            print(
                "archive-stamp-cli: correct-handoff-body: --old-string <old> "
                "(or --old-string-file <path>) is required",
                file=sys.stderr,
            )
            return 2
        new_string, err = _resolve_prose(tail, "--new-string", allow_empty=True)
        if err:
            print(err, file=sys.stderr)
            return 2
        if new_string is None:
            print(
                "archive-stamp-cli: correct-handoff-body: --new-string <new> "
                "(or --new-string-file <path>) is required",
                file=sys.stderr,
            )
            return 2
        return mod.cs_correct_handoff_body(handoff_path, old_string, new_string)

    print(f"archive-stamp-cli: unknown subcommand {subcmd!r}", file=sys.stderr)
    return _usage("archive-stamp-cli")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
