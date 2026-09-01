# archive-stamp-cli — CLI trampoline over claude-klabauter
# coordinator_core.archive_stamp (handoff/memo/plan lifecycle frontmatter
# writes). Direct-import variant (template-variant #1, per
# tasks/2026-07-16-clean-slate-recon/r1-doe-port-template.md § 1): a plain
# in-process function call after resolving the engine root, no cc_invoke/IPC hop.
#
# Direct Python engine boundary (R1 template's variant discriminator) for
# callers in skills/{handoff,pickup,workstream-complete}/SKILL.md.
#
# Subcommands (argv[1] selects; remaining argv forwarded to the mapped
# coordinator_core.archive_stamp function):
#   stamp-shipped-in <handoff_path> [--allow-branch-tip-fallback] [--sha <SHA>]
#       [--kind <ship-commit|successor|scope-derived|no-commit>]
#     (--kind is REQUIRED, keyword-only, on the mapped
#     coordinator_core.archive_stamp.stamp_shipped_in choke point (DR-096) —
#     this CLI defaults it when omitted: "ship-commit" when --sha is supplied,
#     "scope-derived" otherwise, matching the choke point's own default-shaped
#     callers. An explicitly-supplied --kind is validated against the
#     canonical enum, coordinator_core.ops.handoff_stamp._SHIPPED_IN_KIND_ENUM.)
#   ship-handoff <handoff_path> [<SHA>] [--sha <SHA>] [--archive] [--force]
#   claim-handoff <handoff_path>
#     (deprecated alias: consume-handoff — accepted, not advertised; DR-084
#     renamed the verb to match the claimed/claimed_at/claimed_by frontmatter
#     vocabulary this writer has stamped since the cutover)
#   claim-memo-stamp <memo_path>
#   action-memo <memo_path> [disposition-flags...]
#   resolve-memo <memo_path> [disposition-flags...]
#     (memo.transition verb resolve — collapses claim-memo-stamp + action-memo
#     into ONE atomic locked_rmw closure, open->actioned with no in_progress
#     ever visible on disk between the two calls; see
#     coordinator_core/ops/memo_transition.py's _resolve docstring)
#     # Review: overengineering-reviewer -- dropped the -file-sibling sentence
#     # here; the usage rows below and _PROSE_DISPOSITION_FLAGS's comment
#     # already carry it.
#   release-memo-revert <memo_path>
#   stamp-plan-implemented <plan_path>
#   gate-recheck-handoff <handoff_path> <at> [--cleared]
#   close-handoff <handoff_path> --reason <cancelled|displaced|stale>
#   repark-handoff <handoff_path>
#   unclaim-handoff <handoff_path> [note] [--reaped-from <sid>]
#     (deprecated alias: unconsume-handoff — accepted, not advertised)
#     (--reaped-from is the reaper's opt-in provenance signal — see
#     coordinator_core.ops.handoff_transition._unclaim's docstring for the
#     reaped_from_session resolution order it triggers)
#   chain-archive-handoff <handoff_path> [--exclude <path>]...
#   supersede-archive-handoff <handoff_path> --continued-into <successor> [--exclude <path>]...
#     (handoff.archive_transition mode='chain'/'supersede' — see
#     coordinator_core/archive_stamp.py's cs_chain_archive_handoff /
#     cs_supersede_archive_handoff docstrings)
#   repair-archived-shipped-in <handoff_path> --reason <reason> (--sha <SHA> | --unset)
#   repair-archived-deployment-state <handoff_path> --reason <reason> --deployment-state <state>
#       [--continued-into <successor>] [--continued-into-override]
#       [--closed-reason <cancelled|displaced|stale>]
#     (--continued-into-override bypasses the resolution-and-existence check on
#     --continued-into for the genuinely-cannot-verify-locally cases — a
#     successor deleted by a distill sweep and recovered from git history, or
#     a cross-repo continuation this single-repo op cannot resolve. --reason
#     is the audit trail for why the override was needed.)
#     (narrow provenance-repair doors onto archive/handoffs/ — see
#     coordinator_core/archive_stamp.py's cs_repair_archived_shipped_in /
#     cs_repair_archived_deployment_state docstrings. Every other verb above is
#     state/handoffs/-only; these two are the ONLY verbs that reach an
#     already-archived handoff, and only touch the one named field.)
#   correct-handoff-body <handoff_path> --old-string <old> --new-string <new>
#     (handoff.correct_body op veneer — a bounded, authorship-gated body
#     correction for a status:claimed (or legacy status:consumed)
#     state/handoffs/*.md file. --old-string/--new-string are free-form prose,
#     hence flags rather than positionals; scanned order-independently, same
#     idiom as --sha/--exclude above. See
#     coordinator_core/archive_stamp.py's cs_correct_handoff_body docstring.
#     THE AUTHORSHIP GATE IS ANTI-ACCIDENT, NOT ANTI-ADVERSARY (DR-247 § 3):
#     the op's authorship check is a pure caller-controlled environment-
#     variable lookup inside a subprocess the caller itself spawns, so a
#     deliberately-set env var passes the gate unconditionally — this verb
#     must never be read as enforcing "only the author can correct this".
#     The real control is the stamped, auditable correction note the op
#     writes on every applied correction; a spoofed invocation is made
#     visible on disk, not prevented.)
#
# Exit codes: propagates the mapped function's own return value verbatim (see
# coordinator_core/archive_stamp.py module docstring for the per-function
# exit-code contract — cs_stamp_plan_implemented is now a plain 0/1 contract,
# having moved to an in-process plan_status_transition.main() call with no
# node/DoE-root resolution step of its own).
# A missing/unresolvable the engine root (this trampoline's own transport failure,
# distinct from any mapped function's business exit code) exits 3 — the
# dedicated code below, since that failure means "the claude-klabauter engine could not
# be reached," never silently degraded to 0.
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
    "stamp-plan-implemented | gate-recheck-handoff | close-handoff | "
    "repark-handoff | unclaim-handoff | chain-archive-handoff | "
    "supersede-archive-handoff | repair-archived-shipped-in | "
    "repair-archived-deployment-state | correct-handoff-body\n"
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

# Explicit help flags exit 0 on stdout — an unknown/absent subcommand still exits
# 2 on stderr via _usage(). Without this, `archive-stamp-cli --help` reported
# "unknown subcommand '--help'" and the only way to discover the surface was to
# trigger the error fallback (claude-klabauter-em memo, 2026-07-20).
_HELP_FLAGS = ("--help", "-h", "help")

# Per-subcommand help. Without this, `archive-stamp-cli ship-handoff --help`
# fell through to the subcommand's own parser, which took "--help" as the
# positional handoff_path and reported `handoff_path escapes state/handoffs/:
# '--help'` — so the surface's own flags were discoverable only by failing
# into the remediation text twice (project-rag-em memo, 2026-07-28).
#
# The bareword "help" is deliberately NOT accepted in this position:
# `action-memo` forwards its tail to the engine verbatim, and a disposition
# flag or value is free to be any string.
_SUBCOMMAND_HELP_FLAGS = ("--help", "-h")

# Single source of truth for the accepted-but-unadvertised deprecated verb
# names (DR-084 rename, commit 92c902051): alias -> canonical verb. `main()`
# below derives its dispatch conditions from this mapping rather than
# hardcoding the alias tuples, so a future rename/retirement changes exactly
# one place. Kept out of `_SUBCOMMANDS` deliberately — see that NOTE text —
# but still given `_SUBCOMMAND_USAGE` rows so `<alias> --help` answers
# directly instead of falling through to the positional-arg parser.
_DEPRECATED_ALIASES = {
    "consume-handoff": "claim-handoff",
    "unconsume-handoff": "unclaim-handoff",
}

_SUBCOMMAND_USAGE = {
    "stamp-shipped-in": (
        "archive-stamp-cli stamp-shipped-in <handoff_path> "
        "[--allow-branch-tip-fallback] [--sha <SHA>] [--kind <kind>]"
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
        "  NOTE — same prose file siblings as action-memo."
    ),
    "release-memo-revert": "archive-stamp-cli release-memo-revert <memo_path>",
    "stamp-plan-implemented": "archive-stamp-cli stamp-plan-implemented <plan_path>",
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
# `--`, so an unrecognized flag there is not distinguishable from the text.
# Their usage lines already document that collision; strictness would change
# documented behaviour rather than restore it, so they stay exempt.
_FREE_TEXT_POSITIONAL_VERBS = frozenset({"unclaim-handoff", "unconsume-handoff"})

# An OPEN FLAG TAIL: a bracketed placeholder ending in `...` that is not itself a
# literal flag, e.g. `[disposition-flags...]`. It means the verb forwards its tail
# to the engine verbatim and its flag vocabulary is the ENGINE's, not this file's,
# so `_SUBCOMMAND_USAGE` cannot enumerate it and this guard has nothing to check
# against. Deliberately does NOT match `[--exclude <path>]...` — a REPEATABLE
# LITERAL flag, which is declared, enumerable, and stays guarded.
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
    # No help-flag union: `main()` early-returns on every help form before calling
    # this, so a help flag can never reach here. Unioning them in pinned a branch
    # nothing exercises (Kira, 2026-08-31).
    known = set(_FLAG_RE.findall(usage))
    i = 0
    while i < len(rest):
        tok = rest[i]
        if tok in known:
            i += 2  # skip this flag's value; a value may itself look like a flag
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


# --- Prose transport: the `.cmd` forwarder is lossy, so prose gets a file leg ---
#
# `%*` in a generated `.cmd` launcher is an UN-RE-QUOTED expansion, and cmd.exe
# truncates its whole command line at the first LF during its own parse. A
# multi-line `--new-string` therefore reaches this process holding only line 1,
# with no signal anywhere: example-cockpit-repo-em measured
# `archive-stamp-cli.cmd correct-handoff-body --old-string <one line>
# --new-string <20 lines>` exiting 0, printing "applied body correction", and
# writing line 1 glued onto the text it was meant to replace
# (`cross-repo/archive/2026-08-21-example-cockpit-repo-em-cmd-wrapper-eats-argv-and-
# wsc-tail-exit-3-hides-a-landed-commit.md` § 1). The corrupted file was
# committed and reported as done.
#
# REMEDY CHOSEN DELIBERATELY, NOT DEFAULTED. The other candidate was enrolling
# this entrypoint in `gen-launcher-shim.py::_RAW_CMDLINE_ENTRYPOINTS` /
# `substrate.py::_RAW_CMDLINE_TARGETS` -- the `%CMDCMDLINE%` capture-and-recover
# mechanism. Rejected on three measured grounds, all already written down
# elsewhere in this tree:
#   1. Recovery cannot work for this payload shape. `docs/wiki/windows-first-
#      class.md` § "Quote-and-space-bearing payloads" records the measurement:
#      PowerShell never distinguished literal-payload quotes from batch-syntax
#      quotes on the way in, so recovering argv from the raw command line is
#      genuinely ambiguous once a value contains a space -- widening the raw-
#      cmdline set "would recover the unspaced case and silently mis-recover
#      the spaced one". A body correction is prose; spaces are certain.
#   2. Enrolment is not free, and this is a hot-path CLI. Every invocation of an
#      enrolled target pays a per-invocation capture file (mkdir + write + read
#      + unlink). `archive-stamp-cli` runs on every pickup claim and every
#      close; the 50-70-concurrent-session load norm makes that cost fleet-wide,
#      paid by every verb to protect four.
#   3. The membership rule beside `_RAW_CMDLINE_ENTRYPOINTS` already routes this
#      case away from itself, in its own words: "when a payload is prose rather
#      than a rev, prefer the `--<flag>-file <path>` sibling
#      `docs/wiki/windows-first-class.md` rules for, which removes the exposure
#      instead of recovering from it."
#
# So: a `--<flag>-file <path>` sibling for every prose-bearing flag, plus a hard
# refusal (never a silent truncation) when the inline form carries a newline.
# The seam is `coordinator_core.argv_fidelity`, shared with the three CLIs
# already on this pattern -- not a fourth local shape.
#
# NOT COVERED HERE, deliberately: a SINGLE-LINE prose value containing a quote
# or a space is still corrupted by `%*`, and no refusal in this file can see it
# (the damage is done before this process's first line runs). The file leg is
# the escape; `docs/wiki/windows-first-class.md` is the ruling. The newline
# refusal closes the silent-truncation half -- the half measured destroying a
# committed artifact.


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


# The prose-bearing disposition flags of `action-memo`/`resolve-memo`. Their
# values are free text a reviewer writes by hand, so they carry the same
# `%*`-truncation and quote-mangling exposure `_resolve_prose` exists for, and
# this file's own header block already names the remedy for every prose-bearing
# flag: a `--<flag>-file <path>` sibling. These three were the flags that
# remedy had not reached (project-rag-em, 2026-08-31).
#
# NOT A MULTI-LINE CHANNEL. `memo_transition._validate_disposition` refuses a
# note containing a newline or a carriage return, and that refusal stays:
# `serialize_yaml_scalar` emits an inline YAML scalar, and its negative-spec
# says so. A multi-line file is therefore still refused, by the engine,
# loudly. What the file leg buys is LOSSLESS transport of a single-line note
# carrying a quote or a space, which
# the `.cmd` forwarder corrupts with nothing observable at any layer above it.
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

    # Before path validation, and before the engine import — a help request
    # must be answerable even where the engine root does not resolve.
    if subcmd in _SUBCOMMAND_USAGE and any(t in _SUBCOMMAND_HELP_FLAGS for t in rest):
        print(f"usage: {_SUBCOMMAND_USAGE[subcmd]}")
        return 0

    # After the help early-returns (a help request must still answer), before the
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
        # Review: code-reviewer — scan for --allow-branch-tip-fallback the same way
        # --sha is scanned below (order-independent), rather than matching only the
        # fixed 2nd positional slot. The prior positional-only match silently dropped
        # the fallback flag when --sha preceded it (`stamp-shipped-in <path> --sha
        # <sha> --allow-branch-tip-fallback`) — a detect-then-silently-drop footgun.
        # --sha is a claude-klabauter-added capability (commit 3103ea3e) with no bash oracle
        # equivalent (coordinator-archive-stamp.sh, retired 2026-07-19 BIG_PORT); both
        # flags are now scanned independently of position/order.
        allow_fallback = "--allow-branch-tip-fallback" in rest[1:]
        sha = None
        if "--sha" in rest[1:]:
            idx = rest.index("--sha")
            if idx + 1 >= len(rest):
                return _usage_line(_SUBCOMMAND_USAGE["stamp-shipped-in"])
            sha = rest[idx + 1]
        # DR-096 made `kind` REQUIRED and keyword-only on stamp_shipped_in with no
        # default (coordinator_core/archive_stamp.py:452) — this trampoline was
        # never updated to supply it, so every invocation raised TypeError. --kind
        # is scanned order-independently, same idiom as --sha/--allow-branch-tip-
        # fallback above. When omitted, derive it from --sha presence exactly as
        # the choke point's own docstring describes for its two default-shaped
        # callers: a caller-supplied sha means "I have a specific commit in hand"
        # (kind="ship-commit"; this is what reap-orphaned-in-flight-handoffs.py
        # does), and no sha means the self-derivation path (kind="scope-derived").
        kind = None
        if "--kind" in rest[1:]:
            idx = rest.index("--kind")
            if idx + 1 >= len(rest):
                return _usage_line(_SUBCOMMAND_USAGE["stamp-shipped-in"])
            kind = rest[idx + 1]
        if kind is None:
            # Mirror stamp_shipped_in's own override-presence normalization
            # (coordinator_core/archive_stamp.py:589 —
            # `override = sha.strip() if sha else None`) rather than bare `sha`
            # truthiness: a whitespace-only --sha must derive the same default
            # kind as an absent --sha, or the CLI picks "ship-commit" while the
            # engine strips it to "" and rejects the call as an unsupported
            # kind/sha combination.
            kind = "ship-commit" if (sha and sha.strip()) else "scope-derived"
        else:
            # Canonical enum, imported not redefined — a second copy here is
            # exactly the fork DR-096 exists to close (see
            # coordinator_core/archive_stamp.py's own "imported not redefined"
            # note on this same enum, ~line 471).
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
        # Review: code-reviewer (P0) — chunk C0 changed stamp_shipped_in's
        # return type from a bare int to a StampOutcome envelope; returning
        # the envelope itself here meant sys.exit(main(...)) received a
        # non-int and exited 1 unconditionally. `.exit_code` mirrors the
        # migration already done at every other call site.
        return mod.stamp_shipped_in(
            rest[0], kind=kind, allow_branch_tip_fallback=allow_fallback, sha=sha
        ).exit_code

    if subcmd == "ship-handoff":
        if not rest:
            return _usage_line(_SUBCOMMAND_USAGE["ship-handoff"])
        # Order-independent flag/positional scan, mirroring the
        # stamp-shipped-in --sha convention above (both flags scanned
        # independently of position/order — see the Review comment on that
        # block for why a fixed-slot positional match is a footgun).
        #
        # Deliberately a SEPARATE verb from stamp-shipped-in: stamp-shipped-in
        # must not flip state or archive (that would bypass the live-children
        # guard) — cs_ship_handoff composes handoff.archive_transition so the
        # guard stays intact.
        #
        # Review: code-reviewer (incident 2026-07-22) — the prior parser took
        # ONLY `rest[1:2] == ["--archive"]` and had NO sha-forwarding path at
        # all: a caller passing a positional sha (`ship-handoff <path> <sha>`)
        # or `--sha <sha>` had it silently swallowed, even though
        # cs_ship_handoff/handoff.archive_transition already accept and thread
        # a caller-supplied sha. A bare positional sha is accepted here (not
        # just --sha) because that is the ergonomic form the fleet was already
        # calling — silently dropping it is what caused the incident.
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

        # Fail loud rather than silently pick one — a caller who passes both
        # a positional sha and a conflicting --sha almost certainly has a bug,
        # and picking either value silently could stamp the wrong provenance.
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
        # consume-handoff retained as a deprecated alias — DoE-claude has ~5
        # live doc/skill references to it that this change does not own.
        if not rest:
            return _usage(f"archive-stamp-cli {subcmd} <handoff_path>")
        return mod.cs_claim_handoff(rest[0])

    if subcmd == "claim-memo-stamp":
        if not rest:
            return _usage("archive-stamp-cli claim-memo-stamp <memo_path>")
        return mod.cs_claim_memo_stamp(rest[0])

    if subcmd in ("action-memo", "resolve-memo"):
        if not rest:
            return _usage(_SUBCOMMAND_USAGE[subcmd])
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

    if subcmd == "gate-recheck-handoff":
        if len(rest) < 2:
            return _usage("archive-stamp-cli gate-recheck-handoff <handoff_path> <at> [--cleared]")
        cleared = "--cleared" in rest[2:]
        return mod.cs_gate_recheck_handoff(rest[0], rest[1], cleared=cleared)

    if subcmd == "close-handoff":
        if not rest:
            return _usage_line(_SUBCOMMAND_USAGE["close-handoff"])
        # Order-independent --reason scan, mirroring the --sha convention on
        # stamp-shipped-in/ship-handoff above. --reason is REQUIRED (not
        # optional like --sha) — a close-handoff call with no reason must
        # refuse before reaching the engine, never silently write a partial
        # terminal (mod.cs_close_handoff's own enum validation is the second,
        # authoritative gate; this is the CLI-layer "did the operator supply
        # one at all" check).
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
        # unconsume-handoff retained as a deprecated alias (mirrors
        # claim-handoff/consume-handoff above).
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
            # Review: code-reviewer — a repeated --reaped-from left the second
            # occurrence in `tail` after the first was stripped, so `note`
            # silently became the literal string "--reaped-from" and the
            # second sid was dropped with no error at all. Hard-reject a
            # repeat at parse time instead, mirroring the missing-value
            # check just above.
            if "--reaped-from" in tail:
                return _usage(
                    f"archive-stamp-cli {subcmd} <handoff_path> [note] [--reaped-from <sid>]"
                    " — --reaped-from may only be given once"
                )
        # --note-file: the lossless leg for a note the .cmd forwarder would
        # truncate, and simultaneously the escape for the collision the usage
        # line documents (a note whose own text begins with `--` cannot be
        # passed positionally). Stripped here, BEFORE the leftover-flag guard
        # below, which would otherwise refuse it as a corrupted note.
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

        # The same silent-corruption class the --reaped-from repeat fix above
        # closed, generalized: ANY unrecognized `--flag` left in the tail
        # became the note verbatim, and any further positional was dropped
        # without a word. `unclaim-handoff <path> --note "<text>"` — a
        # plausible mistyping of a positional-note CLI — therefore exited 0
        # having written `park_note: '--note'` into the baton's frontmatter
        # and thrown the real text away. A note is load-bearing substrate;
        # writing a flag name into it is worse than refusing.
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
        # Refused, never truncated: a multi-line positional note arriving
        # through the .cmd forwarder has ALREADY lost every line after the
        # first, so the refusal only fires on a host where it survived --
        # which is exactly where refusing it and naming --note-file keeps the
        # two platforms writing the same frontmatter. That refusal, the mutual
        # exclusion, and the file read are the same seam every other prose flag
        # in this file uses; the note being positional changes where the value
        # comes from, nothing about what is owed to it.
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

        # `allow_empty` differs between the two, and the difference is this
        # verb's semantics, not an oversight: an empty --old-string matches
        # nothing and is a caller error, while an empty --new-string is how a
        # correction DELETES the matched region. This verb accepted an empty
        # replacement before it gained a file sibling; refusing it now would be
        # a behaviour regression smuggled in on a transport fix.
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
