# coordinator-delegation — the only sanctioned human write path to the
# fleet-delegation grant (`<settings-home>/fleet-delegation.json`,
# `coordinator_core.session.fleet_delegation`). C3 (write_guards) and C4
# (bash_guards) make that file unwritable through Write/Edit and through a
# shell — this CLI, invoked by the human at a terminal, is what C3's guard
# message points at (`coordinator-delegation grant ...`). Without this row
# the capability shipped by C1/C2 has no usable write path at all.
#
# Subcommands (argv[1] selects; remaining argv is this CLI's own flag set —
# it does NOT forward raw argv to `fleet_delegation.write_fleet_delegation`,
# unlike tier-u-grant-cli's `grant_directive` forwarding, because this
# writer's argument shape (designated pid/create_time resolution, the
# lease-to-expires_at conversion) is owned here, not by C2):
#   grant --pid <pid> --classes <c1,c2,...> --lease-hours <N>
#         (--note <text> | --note-file <path>)
#       -> resolves the designated (pid, create_time) pair via a direct
#          psutil probe of --pid, converts --lease-hours into an
#          `expires_at` measured from THIS CALL's wall clock, and rejects
#          a lease over 12h locally (before ever reaching
#          `fleet_delegation.write_fleet_delegation`, so the human sees the
#          rejection immediately rather than after a round trip through the
#          writer's own ceiling check) -> write_fleet_delegation(...)
#          bool->exit. Prints the ceiling sentence verbatim on every call,
#          success or rejection.
#   show                          -> check_fleet_delegation-backed read:
#                                     prints the live grant's fields, or
#                                     "no live grant" when absent (any
#                                     reason: missing, expired, malformed,
#                                     non-human authorship, dead designated
#                                     process — check_fleet_delegation
#                                     itself does not distinguish, and this
#                                     CLI does not either).
#   revoke                        -> hand the grant back: unlink the grant
#                                     file via `fleet_delegation`'s own
#                                     `_grant_file()` location-naming seam
#                                     (mirrors `session.grant.revoke_tier_u_
#                                     grant`'s unlink shape) — never a
#                                     back-dated `granted_at` smuggled past
#                                     the writer's own +/-5min tolerance.
#                                     Idempotent: revoking an absent grant
#                                     is success, not an error. bool->exit.
#
# Exit codes: 0 success, 1 the mapped writer/predicate returned False, 2 a
# usage error (missing/unknown subcommand, missing/malformed flag), 3 a
# transport failure (engine root unresolvable / `coordinator_core` not
# importable — this trampoline's own failure, never silently degraded to
# 0/1). Matches coordinator/bin/tier-u-grant-cli.py's convention.
#
# The ceiling sentence — "this raises the cost of forgery and does not
# prevent it" — is mandatory in this CLI's own output per the plan's
# section (1): a grant read as unforgeable is worse than no grant, because
# every correct refusal it converts into an acceptance then rests on it.
# This is a LAYER, never a boundary: no in-harness guard constrains an
# agent that spawns out of harness (WMI/`schtasks`/service control), and
# this CLI does not claim otherwise anywhere in its own text.
#
# Spec backlink: docs/plans/2026-08-28-the-ask-the-pm-step-gets-an-artifact-to-check.md § chunk C7
from __future__ import annotations
"""coordinator-delegation — see the # comment block above for the RAG-bait
purpose text (the polyglot shebang line above makes THIS triple-quoted
string a silently-discarded expression statement, not the module __doc__ —
same convention as tier-u-grant-cli / session-liveness-cli / session-claim-
cli)."""

import sys
from datetime import datetime, timedelta, timezone

_TRANSPORT_FAIL = 3
_USAGE_FAIL = 2

#: Mandatory in this CLI's own output on every `grant` call — see the
#: header comment block. Never call this a boundary anywhere near it.
CEILING_SENTENCE = "this raises the cost of forgery and does not prevent it"

#: Mirrors `fleet_delegation._MAX_LEASE` — checked here FIRST so a human
#: sees the rejection without a round trip through the writer, and again
#: inside the writer itself (the writer's own check is the one that
#: actually protects a caller that imports `write_fleet_delegation`
#: directly rather than going through this CLI).
_MAX_LEASE_HOURS = 12

_SUBCOMMANDS = "subcommands: grant --pid <pid> --classes <c1,c2,...> --lease-hours <N> (--note <text> | --note-file <path>) | show | revoke"

_HELP_FLAGS = ("--help", "-h", "help")


def _import_module():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    require_dispatch_engine_on_path()
    import coordinator_core.session.fleet_delegation as _mod

    return _mod


def _usage(prog: str) -> int:
    print(f"usage: {prog} <subcommand> <args...>\n{_SUBCOMMANDS}", file=sys.stderr)
    return _USAGE_FAIL


def _bool_to_exit(result: bool) -> int:
    return 0 if result else 1


def _parse_flags(rest: list[str], *, required: tuple[str, ...], optional: tuple[str, ...] = ()) -> dict | None:
    """Minimal `--flag value` parser shared by `grant`. Returns `None` (never
    raises) on any malformed shape — an unknown flag, a dangling flag with
    no value, or a missing required flag — so `main` can uniformly turn
    that into the usage exit code."""
    known = set(required) | set(optional)
    out: dict[str, str] = {}
    i = 0
    while i < len(rest):
        flag = rest[i]
        if flag not in known:
            return None
        if i + 1 >= len(rest):
            return None
        out[flag] = rest[i + 1]
        i += 2
    if any(flag not in out for flag in required):
        return None
    return out


def _resolve_designated(mod, pid_text: str) -> tuple[int, float] | None:
    """Resolve `(pid, create_time)` for `--pid` via a direct `psutil` probe
    — the same identity pair `fleet_delegation.write_fleet_delegation`
    stores verbatim as `designated`. Returns `None` on any failure (bad
    int, psutil absent, no such process) — the caller turns that into a
    usage-shaped rejection printed before the writer is ever called."""
    try:
        pid = int(pid_text)
    except ValueError:
        return None
    from coordinator_core.session.core import _psutil

    ps = _psutil()
    if ps is None:
        return None
    try:
        proc = ps.Process(pid)
        return pid, proc.create_time()
    except Exception:
        return None


def _cmd_grant(mod, rest: list[str]) -> int:
    print(CEILING_SENTENCE)
    flags = _parse_flags(
        rest,
        required=("--pid", "--classes", "--lease-hours"),
        optional=("--note", "--note-file"),
    )
    if flags is None:
        return _usage("coordinator-delegation grant")

    from coordinator_core.argv_fidelity import ArgvFidelityError, refuse_newline_argv, resolve_body

    try:
        refuse_newline_argv(flags.get("--note"), flag_name="--note")
        note = resolve_body(flags.get("--note"), flags.get("--note-file"), flag_name="--note")
    except ArgvFidelityError as exc:
        print(f"coordinator-delegation: {exc}", file=sys.stderr)
        return _usage("coordinator-delegation grant")

    designated = _resolve_designated(mod, flags["--pid"])
    if designated is None:
        print(
            f"coordinator-delegation: --pid {flags['--pid']!r} did not resolve to a live process",
            file=sys.stderr,
        )
        return _USAGE_FAIL
    designated_pid, designated_create_time = designated

    try:
        lease_hours = float(flags["--lease-hours"])
    except ValueError:
        print(
            f"coordinator-delegation: --lease-hours {flags['--lease-hours']!r} is not a number",
            file=sys.stderr,
        )
        return _USAGE_FAIL
    if lease_hours <= 0 or lease_hours > _MAX_LEASE_HOURS:
        print(
            f"coordinator-delegation: --lease-hours must be > 0 and <= {_MAX_LEASE_HOURS} "
            f"(got {lease_hours})",
            file=sys.stderr,
        )
        return _USAGE_FAIL

    classes = [c for c in flags["--classes"].split(",") if c]

    # `NEVER_DELEGABLE` is declared once, in `fleet_delegation.py` (C2), and
    # imported here rather than restated — this early check exists so the
    # human sees the rejection immediately, the same reason the 12h ceiling
    # is checked above before the writer is ever called. The writer's own
    # identical check (module docstring's "Write-time validation") is what
    # actually protects a caller that imports `write_fleet_delegation`
    # directly rather than going through this CLI.
    never_delegable_hit = mod.NEVER_DELEGABLE.intersection(classes)
    if never_delegable_hit:
        print(
            f"coordinator-delegation: class(es) not delegable: {sorted(never_delegable_hit)}",
            file=sys.stderr,
        )
        return _USAGE_FAIL

    now = datetime.now(timezone.utc)
    granted_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    expires_at = (now + timedelta(hours=lease_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")

    ok, reason = mod.write_fleet_delegation(
        designated_pid=designated_pid,
        designated_create_time=designated_create_time,
        classes=classes,
        granted_at=granted_at,
        expires_at=expires_at,
        granted_by="human",
        note=note,
    )
    if not ok:
        print(f"coordinator-delegation: grant rejected: {reason}", file=sys.stderr)
    return _bool_to_exit(ok)


def _cmd_show(mod, rest: list[str]) -> int:
    """Reads the current grant via `check_fleet_delegation` — never the raw
    `read_fleet_delegation` reader — so "no live grant" is printed for the
    SAME reasons the read path's own ABSENT case covers (missing, expired,
    malformed, non-human authorship, dead designated process): `show`
    cannot report a field set the routing predicate itself would treat as
    absent. Probes the record's own first `classes` entry (or, for a
    class-less/absent record, an empty string that can never match) purely
    to reach `check_fleet_delegation`'s liveness/expiry/authorship
    evaluation — every field the record carries applies uniformly, not
    per-class, so which class is probed does not change the outcome."""
    if rest:
        return _usage("coordinator-delegation show")
    record = mod.read_fleet_delegation()
    if record is None:
        print("no live grant")
        return 0
    classes = record.get("classes") or []
    probe_class = classes[0] if classes else ""
    granted, _record = mod.check_fleet_delegation(probe_class)
    if not granted:
        print("no live grant")
        return 0
    print(f"designated: {record.get('designated')}")
    print(f"classes: {record.get('classes')}")
    print(f"granted_at: {record.get('granted_at')}")
    print(f"expires_at: {record.get('expires_at')}")
    print(f"granted_by: {record.get('granted_by')}")
    print(f"note: {record.get('note')}")
    return 0


def _cmd_revoke(mod, rest: list[str]) -> int:
    """Hand the grant back by unlinking it — never by back-dating
    `granted_at` past `write_fleet_delegation`'s own +/-5min tolerance
    (`fleet_delegation._GRANTED_AT_TOLERANCE`) to smuggle an "already
    expired" record past the writer. Routes through `_grant_file()`, the
    module's single location-naming seam (mirrors
    `coordinator_core.session.grant.revoke_tier_u_grant`'s unlink shape,
    out of this CLI's scope to relocate into `fleet_delegation.py` itself).
    Idempotent: revoking an absent grant is success, not an error."""
    if rest:
        return _usage("coordinator-delegation revoke")
    grant_file = mod._grant_file()
    try:
        grant_file.unlink(missing_ok=True)
    except OSError as exc:
        print(f"coordinator-delegation: revoke failed: {exc}", file=sys.stderr)
        return _bool_to_exit(False)
    return _bool_to_exit(True)


def main(argv: list[str]) -> int:
    if not argv:
        return _usage("coordinator-delegation")
    subcmd, rest = argv[0], argv[1:]

    if subcmd in _HELP_FLAGS:
        print(f"usage: coordinator-delegation <subcommand> <args...>\n{_SUBCOMMANDS}")
        return 0

    try:
        mod = _import_module()
    except RuntimeError as exc:
        print(f"coordinator-delegation: engine-root resolution failed: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL
    except ImportError as exc:
        print(
            f"coordinator-delegation: coordinator_core.session.fleet_delegation not importable: {exc}",
            file=sys.stderr,
        )
        return _TRANSPORT_FAIL

    if subcmd == "grant":
        return _cmd_grant(mod, rest)
    if subcmd == "show":
        return _cmd_show(mod, rest)
    if subcmd == "revoke":
        return _cmd_revoke(mod, rest)

    print(f"coordinator-delegation: unknown subcommand {subcmd!r}", file=sys.stderr)
    return _usage("coordinator-delegation")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
