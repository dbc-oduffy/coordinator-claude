"""
coordinator.hooks.http_hook_forwarder -- the fixed-port front door Claude Code's `type: "http"`
hook registration dials, forwarding each POST to whatever ephemeral port the engine's own
`port=0` warm-http listener currently publishes.

WHY THIS EXISTS. A static `hooks.json` `type: "http"` entry can only carry a URL known before
session boot, but the engine's real listener binds `port=0` on purpose -- two engines on one box
must not collide on a hardcoded number (`coordinator_core/warm/http_listener.py:187`). This
module is the stable, fixed-port thing the harness actually dials; it moves bytes and resolves a
port, nothing more.
`docs/plans/2026-08-25-route-the-bash-guard-onto-the-native-htt.md`'s "mechanism question"
section names this shape 3, selected over a boot-time registration rewrite (shape 2, refused --
reinstates the class `fail_open_launcher.py` exists to prevent) and a bare fixed engine port
(shape 1, discards `port=0`'s anti-collision rationale wholesale).

WHAT THIS MODULE DOES NOT DO. It holds no guard *policy* and never authors an allow -- every
allow it relays is a verdict the engine's own `_serve_line` actually returned. It does not decide
who binds the fixed port first, how a machine-wide binder election resolves, or how a fired hook
is routed to the correct engine clone on a multi-clone box -- those are
`docs/decisions/DR-http-hook-forwarder-fixed-port.md`'s Decisions 1 and 3, consumed by whichever
lifecycle owner (C0b) starts this process; this module is the forwarding body they start, not
the supervision around it. It mints no `_engine_token` and forwards none: the backend's own
supervisor self-stamps that token from `skew.compute_client_token` before invoking `_serve_line`
(`supervisor.py:567`, `_ServerContext._compute_engine_token`), because `hooks.json`'s `type:
"http"` caller has no notion of the token and sends none -- inventing a second scheme here would
be exactly the auth duplication `http_listener.py`'s module docstring forbids.

NEGATIVE SPEC -- properties that are deliberately asymmetric with `http_listener.py`, and why a
future edit must not "fix" the asymmetry by copy-paste:

  - **Exclusive bind, not `SO_REUSEADDR`.** `http_listener._Server` sets
    `allow_reuse_address = True` (http_listener.py:180) because the engine's own listener binds
    an ephemeral port nobody else contends for. This forwarder binds a FIXED, well-known port
    that anything on the box could attempt to bind too. Two `SO_REUSEADDR` sockets both bind the
    same fixed port on this host, silently, both succeeding, with indeterminate delivery --
    measured, not theorised (`DR-http-hook-forwarder-fixed-port.md` Decision 4). This class binds
    with `allow_reuse_address = False` and additionally asserts `SO_EXCLUSIVEADDRUSE` where the
    platform has it (Windows), so a losing second bind attempt fails loudly rather than silently
    coexisting. The DR names the machine-wide binder election as the portable floor across every
    OS; this module's exclusivity is a hardening layer on top of that, not a substitute for it.
  - **Re-reads discovery on every fire, never caches the backend port.** LOAD-BEARING, not
    hygiene -- the listener is ephemeral by design and its port changes across generations, and
    the discovery record is REWRITTEN on every token rotation (five in one 213-minute observation
    window). A forwarder that resolved the backend port once at startup would be stale from the
    first respawn while still answering the harness -- looking healthy while pointing at nothing.
    The record-rewrite window this property has to survive (`read_discovery` landing mid-rewrite)
    is closed as of the engine plane's `dcf4f83a1`; an older engine clone reintroduces it beneath a
    forwarder that looks correct. Every request calls `supervisor.read_discovery()` fresh.
  - **Dials the `127.0.0.1` literal, never `localhost`.** Dialling the name costs ~2s per call on
    this host (IPv6-first dual-stack resolution racing an IPv4-only listener). The literal comes
    from `http_listener.bind_host()` -- one place decides it so no caller here re-derives it.
  - **Distinguishes "no backend" from "backend said no," and DENIES on the first.** This is the
    load-bearing property. Reporting unreachability truthfully is NOT the fix: the harness fails
    open on a genuinely unreachable http hook endpoint (2026-08-19 spike, arm C), so a forwarder
    that merely answers truthfully about a dead backend still terminates in a permitted Bash call
    -- the forwarder is the only component of ours left in the path once the registration is
    `type: "http"`, and a down backend cannot author its own refusal. So an unreachable or
    undiscoverable backend gets an AFFIRMATIVE `permissionDecision: deny` whose reason names the
    guard as not having run (this is AC1c). Confirmed at the harness level, not just at this
    module's own response shape, by
    `docs/research/2026-08-25-forwarder-deny-on-dead-backend.md` (C0a): a forwarder-shaped
    process that itself failed to reach its backend and only then emitted this deny shape blocked
    a real, live Bash tool call. Every OTHER response -- any status/body the backend itself
    returned, allow included -- is relayed verbatim; this module makes exactly one permission
    decision of its own.

Reference: `hookSpecificOutput.permissionDecision: "deny"` is the documented and measured block
channel for a `type: "http"` hook response
(`docs/research/spike-verdicts/2026-08-19-http-hook-transport.md`), not invented here.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
import uuid
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional, Tuple

__all__ = [
    "DENY_REASON",
    "REFUSED_REASON",
    "DIAL_COUNT_PATH_ENV",
    "FIXED_PORT",
    "ROUTING_HEADER_NAME",
    "COOKIE_HEADER_NAME",
    "DialCounter",
    "dial_count_path",
    "make_server",
    "serve_forever",
    "main",
]

#: Reason text placed on the one permission decision this module authors itself. Named so a
#: consumer reading a transcript can tell "the forwarder denied because its backend was
#: unreachable" apart from "the engine's own guard denied the command" -- the two must never be
#: mistaken for each other; the caller-facing text says which happened.
DENY_REASON = (
    "http-hook-forwarder: no live engine backend reachable -- the Bash guard did not run, "
    "denying rather than permitting a command it never evaluated"
)

#: Reason text for the OTHER case this module must author a decision for: a backend that was
#: reached and answered, but answered with a transport-level refusal rather than a verdict.
#:
#: WHY THIS IS A DENY AND NOT A RELAY, MEASURED. Relaying the raw status was this module's
#: original behaviour and it is a guard-bypass hole: the harness FAILS OPEN on a non-2xx from a
#: hook, and on `PreToolUse` it does so SILENTLY -- nothing surfaces in the tool result at all.
#: Measured 2026-08-27 with a receiver answering every POST with a bare 401 registered as
#: `PreToolUse`: the harness dialled, took the 401, and ran the tool anyway
#: (`docs/research/evidence/2026-08-27-transport-error-fail-open/`). A transport error is NOT a
#: verdict, and this module must never hand the harness one where a verdict was required.
#: DIAGNOSTIC LIMIT, worth knowing before this text is trusted as a diagnosis. `cookie.read`
#: collapses "no cookie exists" and "the cookie exists and could not be read" to `None` by
#: design -- the engine keeps `CookieUnreadableError` for the boot paths that must NOT collapse
#: them. So this module cannot distinguish an ungated backend from a gated one whose credential
#: it failed to read, and under a deny storm those have entirely different diagnoses. Reading
#: the cookie a second way to tell them apart is deliberately NOT done here: it would add a
#: failure path to the hot path of every Bash call on the box to improve a log line.
REFUSED_REASON = (
    "http-hook-forwarder: engine backend refused the request -- the Bash guard did not run, "
    "denying rather than permitting a command it never evaluated"
)

#: Same cap `http_listener.py` applies to its own POST bodies -- a hook event is a small JSON
#: object, and anything larger here is malformed or hostile before it reaches this module's own
#: (tiny) parsing.
MAX_BODY_BYTES = 1 << 20

#: How long a forward attempt may take before this module treats the backend as unreachable and
#: denies. Small: the backend is loopback-local and, per the 2026-08-19 spike, sub-millisecond
#: when it is actually up. This bound exists for the down case, not the up one.
_FORWARD_TIMEOUT_SECS = 2.0

#: The one fixed, machine-global loopback port this module ever binds or dials -- named here so
#: exactly one place in the tree commits the number (module docstring, "WHAT THIS MODULE DOES
#: NOT DO"; `DR-http-hook-forwarder-fixed-port.md` Decision 3 assigns *ownership* of the port,
#: not its value). It carries no clone identity -- routing rides the `COORDINATOR_CLONE_ROOT`
#: header per that DR's Decision 1 -- so one number serves every clone on the box.
#:
#: Checked against, before picking 47623:
#:   - IANA registered ports (0-49151, both the "well known" 0-1023 and "user/registered"
#:     1024-49151 ranges as of the IANA Service Name and Transport Protocol Port Number
#:     Registry) -- 47623 is unassigned in that registry.
#:   - Windows' default dynamic/ephemeral client port range, `49152-65535`
#:     (`netsh int ipv4 show dynamicport tcp`, Windows default since Vista) -- 47623 sits below
#:     that range, so the OS will never hand it out to an outbound client socket and collide
#:     with this module's own listener.
#:   - Common dev-tool defaults in this environment (Node/Vite 5173, common debug ports
#:     8000/8080/9000-series, Postgres 5432, Redis 6379, etc.) -- no overlap.
FIXED_PORT = 47623

#: HTTP header the `type: "http"` registration carries `${COORDINATOR_CLONE_ROOT}` on, per
#: `DR-http-hook-forwarder-fixed-port.md` Decision 1's routing key. The DR names the env var but
#: leaves the on-the-wire header name unstated (the registration flip is itself deferred --
#: `coordinator/hooks/hooks.json`'s own `_comment` on the folded Bash entry -- so no header has
#: been exercised end-to-end yet). Chosen here as a single module constant so the registration
#: chunk cites this name rather than inventing its own: `X-Coordinator-Clone-Root`.
ROUTING_HEADER_NAME = "X-Coordinator-Clone-Root"

#: Credential header the warm listener's cookie gate requires on every forwarded request
#: (`coordinator_core/warm/cookie.py` `COOKIE_HEADER`; enforced in `supervisor.py`
#: `_cookie_is_valid`, before routing, fail-closed).
#:
#: NOT the door key, and the two are routinely conflated. `X-Coordinator-Door-Key` is env-sourced
#: (`COORDINATOR_DOOR_KEY`, `door_credential.py`) and interpolates into a `type: "http"`
#: registration; THIS one is file-sourced per engine root and the harness cannot interpolate it,
#: which is why it is attached here at forward time rather than by the registration. A third
#: axis, the skew token, is neither -- it self-stamps and refuses with 409, not 401.
#:
#: Spelt as a literal rather than imported from the engine so this module keeps forwarding when
#: `coordinator_core` is unimportable; the value is pinned against the engine by
#: `test_http_hook_forwarder_cookie.py`.
COOKIE_HEADER_NAME = "X-Coordinator-Cookie"

#: Env var overriding where the dial counter is persisted. Exists for tests and for a second
#: forwarder deliberately run off to one side; a deployment never sets it.
DIAL_COUNT_PATH_ENV = "COORDINATOR_FORWARDER_DIAL_COUNT_PATH"

#: How many recent arrivals the counter keeps alongside the totals. A bare integer is
#: uninterpretable while a sweep varies one registration field at a time -- the tail is what says
#: WHICH variation dialled. Small: this is a breadcrumb, not a log.
_DIAL_RING_SIZE = 20

#: Bounded ladder for the counter's atomic replace. CPython's ``open()`` does not request
#: ``FILE_SHARE_DELETE``, so on Windows a replace of a file any reader currently holds open fails
#: with ``PermissionError`` (WinError 5) rather than blocking. Measured against one polling
#: reader, 2474 of 4000 single-attempt replaces failed that way; every one was swallowed by
#: ``persist``'s never-raise contract and lost the arrival it carried. The cap keeps a contended
#: write shorter than the response it already trails, and POSIX never enters the ladder at all.
_REPLACE_RETRY_ATTEMPTS = 50
_REPLACE_RETRY_SLEEP_SECONDS = 0.002


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def dial_count_path() -> Path:
    """Absolute path of the dial-count file.

    Machine-global, like the port -- one forwarder serves every clone on the box, so a per-clone
    location would split one process's counts across N files. Resolves through ``CLAUDE_HOME``
    and then ``Path.home()/".claude"``, the ladder every other coordinator hook uses.
    """
    override = os.environ.get(DIAL_COUNT_PATH_ENV)
    if override and override.strip():
        return Path(override.strip())
    base = os.environ.get("CLAUDE_HOME") or str(Path.home())
    return Path(base) / ".claude" / "http-hook-forwarder-dial-count.json"


class DialCounter:
    """Receiver-side count of inbound requests, answering "did the harness dial?" -- including,
    and especially, when the answer is *none*.

    NEGATIVE SPEC -- the properties below are the whole point of this class, and an edit that
    drops any one of them returns it to being an instrument that cannot report the fact it exists
    to report. ``AN-UNDIALED-HOOK-IS-NOT-A-PASSING-GUARD`` in the tripwire registry is the
    incident this discharges: a ``type: "http"`` registration was silently inert, and nothing on
    the box could say so, because a guard that never fires and a guard that fires and allows are
    the same observable.

      - **Read off disk, never over the wire.** No endpoint exposes this count. A read that is
        itself a request perturbs the number by exactly the amount that makes zero unreadable,
        and conflates the instrument with the thing being measured.

      - **The file is created at bind time with the counts already at zero.** This is what makes
        ZERO discriminating. Three states must read differently: file ABSENT (no forwarder ever
        bound -- says nothing about dialling); ``received_total: 0`` beside a ``bound_at``
        (a forwarder has been up since that moment and *nothing dialled it*); and a nonzero
        count. Persisting on first request instead would collapse the first two into identical
        bytes, rebuilding the original bug inside the instrument.

      - **Counted before parsing, not after routing.** ``received_total`` increments at the top
        of ``do_POST``, ahead of the Content-Length check and any body read, so "dialled but sent
        a shape we rejected" stays distinct from "never dialled". ``received_by_event`` is keyed
        after the body parses; ``received_total`` minus the sum over ``received_by_event`` is
        precisely the arrived-but-unparseable population.

      - **``boot_id`` accompanies every count.** Counts are monotonic within one process lifetime
        only. A reader compares ``(boot_id, count)`` pairs, so a restart reads as a new series
        rather than as a decrement.

      - **Persisted off the latency path.** ``record_*`` mutates memory; the file is rewritten
        after the response has been sent. This process sits on the hot path of every Bash call on
        the box.

      - **Whole-file atomic rewrite, no reader lock.** Written to a temp sibling and
        ``os.replace``d, so a concurrent read sees either the previous complete file or the next
        one, never a torn one. On Windows the replace is itself what the reader contends with --
        see ``_REPLACE_RETRY_ATTEMPTS``.
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = Path(path) if path is not None else dial_count_path()
        self._lock = threading.Lock()
        self._boot_id = "{0}-{1}".format(os.getpid(), uuid.uuid4().hex[:12])
        self._bound_at = _utc_now()
        self._received_total = 0
        self._received_by_event: dict = {}
        self._forwarded_by_event: dict = {}
        self._last_received_at: Optional[str] = None
        self._recent: list = []

    @property
    def path(self) -> Path:
        return self._path

    @property
    def boot_id(self) -> str:
        return self._boot_id

    def snapshot(self) -> dict:
        with self._lock:
            return self._snapshot_locked()

    def _snapshot_locked(self) -> dict:
        return {
            "schema": 1,
            "boot_id": self._boot_id,
            "bound_at": self._bound_at,
            "received_total": self._received_total,
            "received_by_event": dict(self._received_by_event),
            "forwarded_by_event": dict(self._forwarded_by_event),
            "last_received_at": self._last_received_at,
            "recent": list(self._recent),
        }

    def record_arrival(self) -> str:
        """One request reached ``do_POST``. Called before anything about it is validated.

        RETURNS ITS OWN ARRIVAL TIMESTAMP, and the caller must carry it to `record_event`. The
        two calls take the lock separately -- they have to, since the body is parsed between
        them -- so `_last_received_at` is shared mutable state that a second request can
        overwrite in the gap. Reading it back in `record_event` stamped one request's ring entry
        with another request's arrival time under concurrency. The ring is what says WHICH
        variation dialled during a sweep, and a sweep is a concurrent population by construction,
        so a misattributed timestamp there is a wrong answer to the question this file exists to
        answer.
        """
        at = _utc_now()
        with self._lock:
            self._received_total += 1
            self._last_received_at = at
        return at

    def record_event(self, hook_event_name: Optional[str], at: Optional[str] = None) -> None:
        """The arrival's body parsed and named this event.

        `at` is the timestamp `record_arrival` returned for THIS request -- see why there.
        """
        key = hook_event_name or "<unnamed>"
        stamped = at or _utc_now()
        with self._lock:
            self._received_by_event[key] = self._received_by_event.get(key, 0) + 1
            self._recent.append({"at": stamped, "event": key})
            if len(self._recent) > _DIAL_RING_SIZE:
                del self._recent[: len(self._recent) - _DIAL_RING_SIZE]

    def record_forwarded(self, hook_event_name: Optional[str]) -> None:
        """The arrival reached a live backend, as opposed to being denied for want of one."""
        key = hook_event_name or "<unnamed>"
        with self._lock:
            self._forwarded_by_event[key] = self._forwarded_by_event.get(key, 0) + 1

    def persist(self) -> None:
        """Rewrite the file atomically.

        THE LOCK IS HELD ACROSS THE WRITE, not merely across the snapshot, and that is a
        correctness requirement rather than tidiness. This is a `ThreadingHTTPServer`: two
        handlers persist concurrently. Snapshot under the lock and write outside it, and the
        orderings interleave -- thread A snapshots at 1, thread B snapshots at 2, B writes, then
        A writes -- and the file settles at 1 **permanently**, with an arrival correctly counted
        in memory now absent from the only surface anyone reads. A counter that loses arrivals
        under concurrency cannot be trusted to report a zero, which is the one thing it exists to
        do. Serializing the writes costs nothing that matters: `persist` is called only after the
        response has already been sent.

        Each write carries the whole snapshot rather than a delta, so a write that loses a race
        is corrected by the next one instead of compounding.

        Never raises: a counter able to take the forwarder down would be a worse defect than the
        one it measures.
        """
        try:
            with self._lock:
                payload = json.dumps(self._snapshot_locked(), indent=2, sort_keys=True)
                self._path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self._path.with_name("{0}.{1}.tmp".format(self._path.name, self._boot_id))
                with open(tmp, "w", encoding="utf-8") as handle:
                    handle.write(payload + "\n")
                self._replace_with_retry(tmp)
        except Exception:
            return

    def _replace_with_retry(self, tmp: Path) -> None:
        """``os.replace(tmp, self._path)``, retried while a reader still owns the destination.

        WHY THIS IS NOT DEFENSIVE PADDING. On Windows a replace of a file that any reader holds
        open fails outright -- see ``_REPLACE_RETRY_ATTEMPTS`` for the mechanism and the measured
        failure rate. Every such failure was swallowed by ``persist``'s never-raise contract, so
        the arrival stayed correct in memory and vanished from the only surface anyone reads: the
        counter under-reported by an amount set by how hard someone was reading it. A counter that
        loses arrivals when observed cannot be trusted to report a zero, which is the one thing it
        exists to do.

        THE READER CANNOT BE FIXED INSTEAD, and that is why the cost lands here. Reading this file
        off disk, with no endpoint and no perturbation of the count, is the counter's stated
        contract; the sweep does exactly that; and the writer cannot enumerate its readers. So the
        writer absorbs the contention.

        Bounded, never unbounded. Exhausting the cap re-raises into ``persist``'s handler, which is
        the pre-existing lost-write outcome -- no worse than before, and never a raise reaching the
        caller. Called with the lock HELD, which is what serializes this ladder against other
        handlers' persists; the cap is therefore also the bound on how long a contended write can
        hold up the next one, and every persist behind it has already sent its response.
        """
        for attempt in range(_REPLACE_RETRY_ATTEMPTS):
            try:
                os.replace(tmp, self._path)
                return
            except PermissionError:
                if attempt == _REPLACE_RETRY_ATTEMPTS - 1:
                    raise
                time.sleep(_REPLACE_RETRY_SLEEP_SECONDS)


# `_engine_root.py` lives one directory down from this module (`coordinator/hooks/scripts/`),
# the same seam every other coordinator/hooks/*.py hook resolves the sibling engine checkout
# through -- see that module's own docstring for why a single shared seam replaced 22 copies of
# the same ladder.
_SCRIPTS_DIR = str(Path(__file__).resolve().parent / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

try:
    from _engine_root import (  # noqa: E402
        resolve_claude_klabauter_root_with_provenance as _resolve_engine,
    )
except Exception:
    # Defensive fallback, matching every other coordinator/hooks/*.py consumer of this seam:
    # a deploy missing its sibling _engine_root.py must still fail open (deny, on this module's
    # own terms -- "no engine root" is exactly the no-backend case) rather than crash on import.
    def _resolve_engine() -> "Tuple[Optional[str], str, str]":
        return None, "unresolved", "none"


_engine_root_lock = threading.Lock()
_engine_root_cache: Optional[str] = None


def _ensure_engine_on_sys_path() -> bool:
    """Resolve the sibling engine checkout onto `sys.path`, once, caching the resolved root.

    Only the `sys.path` insertion is cached -- never the discovery record or the backend port,
    which this module re-reads on every request (see module docstring). Re-running the engine
    resolution ladder on every fire would spend real work (registry reads) for no benefit, since
    the answer to "where is the coordinator_core checkout" does not change mid-session the way
    the discovery record does.
    """
    global _engine_root_cache
    with _engine_root_lock:
        if _engine_root_cache is not None:
            return True
        root, _resolution_class, _provenance = _resolve_engine()
        if not root:
            return False
        if root not in sys.path:
            sys.path.insert(0, root)
        _engine_root_cache = root
        return True


def _resolved_engine_root() -> Optional[str]:
    """The engine root the resolution ladder answered with, or `None` if it answered nothing.

    DISCOVERY IS KEYED ON THE ENGINE ROOT, NEVER ON THE ROUTED CLONE. `supervisor.read_discovery`
    takes a *stamped engine build* (`is_engine_root`); a doctrine-repo clone is not one and never
    becomes one, so passing the routing key's value straight through returns `None` for every
    clone on every request -- an unconditional deny that no unit test catches, because the deny
    path is exactly what the tests assert. The routing key's job is to say WHICH CLONE IS ASKING
    (the deny gate above), not to name the backend's location.
    """
    if not _ensure_engine_on_sys_path():
        return None
    return _engine_root_cache


def _parse_hook_event_name(body: bytes) -> Optional[str]:
    """The one parse. `None` means the body carried no usable `hook_event_name`.

    Its two callers differ ONLY in what they do with that `None`, and that difference is
    load-bearing (see `_counted_event_name`). The parsing itself is shared so a future change to
    the body shape has one place to land rather than two to keep in step. Never raises.
    """
    try:
        obj = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if isinstance(obj, dict):
        name = obj.get("hook_event_name")
        if isinstance(name, str) and name.strip():
            return name
    return None


def _extract_hook_event_name(body: bytes) -> str:
    """The event name for the DENY this module may author, defaulting to `PreToolUse` -- a
    refusal has to name some event, and that is the only one this plan wires over http."""
    return _parse_hook_event_name(body) or "PreToolUse"


def _counted_event_name(body: bytes) -> Optional[str]:
    """The event name as ACTUALLY PRESENT on the wire, or `None` when the body did not carry one.

    Deliberately NOT `_extract_hook_event_name`, and the difference is load-bearing. That
    function defaults an unparsable body to `"PreToolUse"`, which is right for the deny it
    shapes -- a refusal has to name some event. It is wrong for counting: it would file an
    arrived-but-garbage request as an ordinary PreToolUse and erase the very distinction the
    counter exists to draw. `DialCounter`'s negative spec keeps "dialled but sent a shape we
    rejected" separate from "dialled normally", and that separation dies if this defaults.
    """
    return _parse_hook_event_name(body)


def _record_is_skewed(record: "dict", root: Path) -> bool:
    """True when `record` names a listener whose engine has since been republished.

    A skewed listener is ALIVE and answers `GET /health` 200 -- health never traverses
    `_serve_line`, so it never reaches the version check. Only the fire itself discovers the
    skew, by which time `_serve_line` has answered ENGINE_SKEW (-32002) and the guard has NOT
    run. Classifying at the read is what lets this be a no-backend case instead of a verdict.

    Resolved by name at call time, public alias preferred, private name as fallback. Both are
    present in the published mirror today. THE FALLBACK IS NOT VESTIGIAL AND MUST NOT BE
    COLLAPSED INTO A HARD CALL. Hooks and the engine are provisioned by separate layers, so a
    clone can resolve an engine older than this one -- version skew between those two halves is
    the very condition this function detects. A hard `record_is_skewed(...)` would raise
    `AttributeError` on such an engine, the enclosing handler would read that as "no backend",
    and every Bash call on that machine would DENY until someone noticed. Degrading to
    not-skewed is strictly better: an engine too old to answer the question cannot be one that
    republished under a running listener in the sense this guards against, and a hook must
    never brick a Bash call over a predicate it could not find.
    """
    mod = _sup_mod()
    fn = getattr(mod, "record_is_skewed", None) or getattr(mod, "_record_is_skewed", None)
    if fn is None:
        return False
    try:
        return bool(fn(record, root))
    except Exception:
        return False


def _sup_mod() -> "Any":
    from coordinator_core.warm import supervisor as _supervisor

    return _supervisor


def _deny_body(hook_event_name: str, reason: str = DENY_REASON) -> bytes:
    """The permission decisions this module authors -- see module docstring's "no backend"
    property. Shape matches the measured block channel
    (`docs/research/spike-verdicts/2026-08-19-http-hook-transport.md`).

    TWO REASONS, ONE SHAPE. `DENY_REASON` (the default) says the backend was never reached;
    `REFUSED_REASON` says it was reached and refused. Both are this module's own decision and
    neither is the engine guard's verdict -- the distinction exists so a transcript reader can
    tell which happened, exactly as `DENY_REASON`'s own note requires."""
    payload = {
        "hookSpecificOutput": {
            "hookEventName": hook_event_name,
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    return json.dumps(payload).encode("utf-8")


def _extract_cwd(body: bytes) -> Optional[str]:
    """Second identity source for the routing key, read off the hook payload's own `cwd`.

    WHY THIS EXISTS, and why it is not a weakening of Decision 1's deny-on-absent. The routing
    key rides an HTTP header the `type: "http"` registration expands from
    `${COORDINATOR_CLONE_ROOT}`, which the launchers export. A session started BEFORE that export
    existed carries no such variable, so the header expands to the empty string -- the measured
    null -- and every Bash call in that session would be denied by a guard that is working
    exactly as designed. On a box running dozens of long-lived sessions that is not a transition
    cost, it is an outage, and it would have made the registration flip un-landable until every
    session on the machine had cycled.

    `cwd` is the same provenance as the rest of the payload: harness-authored, arriving on the
    same channel as `tool_input`, not attacker-supplied and not read from the environment of the
    process being guarded. It answers the same question the header answers -- WHICH CLONE IS
    ASKING -- so it is a fallback identity, never a fallback POLICY.

    NEGATIVE SPEC. This does not introduce an allow-on-absent path. When neither the header nor
    `cwd` resolves to a real clone, `_resolve_backend` still returns `None` and the caller still
    denies. The deny gate is unchanged; only the number of ways a legitimate caller can identify
    itself has gone from one to two.
    """
    try:
        obj = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(obj, dict):
        return None
    cwd = obj.get("cwd")
    if not isinstance(cwd, str) or not cwd.strip():
        return None
    return cwd


def _normalize_clone_root(raw: str) -> Optional[Path]:
    """Resolve the `ROUTING_HEADER_NAME` header value to a clone root `Path`, or `None` when it
    does not name a real clone -- never a prefix match, never a best-effort pick (see module
    docstring / CHUNK B2 brief).

    Chunk B's two Windows launchers (`claude-doe-launcher.cmd.tmpl`, `.ps1.tmpl`) export the
    **repo root** (the doctrine repo's own clone directory), not the plan C1 body's "resolved
    coordinator dir" (`<repo root>/coordinator`) -- verified by reading the templates as they
    stand on disk, not the plan text. The POSIX leg exports from a different site,
    and the distinction matters to anyone reasoning about who arrives header-less.
    `claude-doe-shim.sh.tmpl` itself exports NOTHING and must not -- it resolves no plugin dir,
    and DR-087 forbids promoting its `.doe-root` pointer to rung-1 authority (negative-spec
    pinned in `test_launcher_templates_export_clone_root.py`). It delegates instead, terminating
    in `claude-doe`, and the engine's `coordinator/bin/claude-doe.py:650` does the
    `setdefault` ABOVE its `os.name == "nt"` branch, so it runs on every platform. A
    shim-launched POSIX session therefore DOES carry the header, and `_extract_cwd` is its
    second identity source rather than its only one.

    The population that genuinely rests on `_extract_cwd` alone is narrower than "POSIX": a
    session that bypasses `claude-doe` entirely -- a hand-run `claude --plugin-dir`, which
    `INSTALL.md` documents as supported. This resolver accepts
    either shape without favouring one: a header value whose final path segment is literally
    `coordinator` is treated as `<repo root>/coordinator` and folded back to its parent (the repo
    root), since both name the same clone unambiguously. This is a structural check on the
    value's own last segment, never a substring/prefix match against anything else.

    The resolved path must actually exist and be a directory -- a value that resolves to nothing
    on disk is "resolves to no clone", the DR's explicit deny case, not a best-effort forward.
    """
    value = raw.strip()
    if not value:
        return None
    try:
        candidate = Path(value)
    except (TypeError, ValueError):
        return None
    if candidate.name == "coordinator":
        candidate = candidate.parent
    try:
        if not candidate.is_dir():
            return None
    except OSError:
        return None
    return candidate


def _resolve_backend(
    clone_root_header: Optional[str],
) -> Optional[Tuple[str, int, str, Optional[str]]]:
    """Fresh discovery read for THIS request -- never cached across requests (module docstring).

    `clone_root_header` is the raw `ROUTING_HEADER_NAME` header value off the incoming request
    (or `None`/empty when absent). Per `DR-http-hook-forwarder-fixed-port.md` Decision 1: header
    missing, blank/whitespace (the measured null for an unexpanded placeholder -- it arrives as
    an EMPTY STRING, not verbatim), or present but unresolvable to a real clone all return `None`
    here, and `None` is the caller's DENY signal, same as every other "no backend" case below.
    This is the single most important branch in this module -- see CHUNK B2 brief.

    Returns `(host, port, hook_path, cookie)` for a discovery record that names a plausible
    live listener, or `None` when there is nothing to forward to: no routing key, no engine root
    resolvable, the engine package itself unimportable, no discovery record published for the
    routed clone, or a record missing/malforming the fields a forward needs. Every one of those
    is "no backend", not "backend said no" -- the caller denies on `None`, never treats it as a
    verdict.
    """
    if not clone_root_header or not clone_root_header.strip():
        return None
    clone_root = _normalize_clone_root(clone_root_header)
    if clone_root is None:
        return None

    engine_root = _resolved_engine_root()
    if not engine_root:
        return None
    try:
        from coordinator_core.warm import cookie as _cookie
        from coordinator_core.warm import http_listener as _http_listener
        from coordinator_core.warm import supervisor as _supervisor
    except Exception:
        return None

    try:
        if not _supervisor.is_engine_root(Path(engine_root)):
            return None
    except Exception:
        return None

    try:
        record = _supervisor.read_discovery(Path(engine_root))
        if record is None:
            # NO BACKEND IS A TRIGGER, NOT JUST A VERDICT. `ensure_listener` is the engine's own
            # autostart entry: it NEVER WAITS (its docstring mirrors `warm.client`'s "no client
            # ever waits for a server to boot"), returns `None` this call, and best-effort spawns
            # one for the next. Without it, a single engine republish is a PERMANENT box-wide
            # outage rather than one cold call: the republish rotates `engine_sha`, the skew check
            # correctly evicts the stale record, and nothing on any production path writes a new
            # one -- measured live, `634b886a` -> `68851d47`, listener gone, every later read
            # `None`. Denying every Bash call on the machine until a human intervenes is not the
            # failure mode this guard is for.
            #
            # ORDERED AFTER THE READ, DELIBERATELY. `ensure_listener` health-checks and may spawn;
            # calling it ahead of the read spends that on EVERY fire, on the hot path of every
            # Bash call on the box -- measured at +26ms to p50, which is real money against a
            # budget whose whole purpose is removing 271ms. The happy path must cost one discovery
            # read and nothing else.
            try:
                _supervisor.ensure_listener(Path(engine_root))
            except Exception:
                pass
            record = _supervisor.read_discovery(Path(engine_root))

        # SKEW IS THE SAME FACT AS ABSENCE, arriving as a record that parses. `read_discovery`
        # does no version check, so a skewed record is not `None` and would sail past the branch
        # above; the listener is alive, so the caller's `OSError` deny arm never fires either.
        # Forwarding it buys ONE UNGUARDED BASH CALL PER REPUBLISH -- the guard does not run, the
        # relay hands the harness a -32002 the model reads as "the guard errored out", and
        # nothing denies. Handled HERE rather than on the relay path so the module's contract
        # holds unchanged: it still authors no permission decision about a VERDICT, because a
        # skewed listener never produces one.
        if record is not None and _record_is_skewed(record, Path(engine_root)):
            try:
                _supervisor.ensure_listener(Path(engine_root))
            except Exception:
                pass
            record = _supervisor.read_discovery(Path(engine_root))
            if record is not None and _record_is_skewed(record, Path(engine_root)):
                return None
    except Exception:
        # `read_discovery` is documented never to raise; this except is belt-and-braces so an
        # engine-side regression cannot turn "no backend" into an unhandled exception that would
        # otherwise 500 rather than deny.
        return None
    if not isinstance(record, dict):
        return None

    port = record.get("port")
    if not isinstance(port, int) or isinstance(port, bool) or port <= 0:
        return None

    hook_path = record.get("hook_path")
    if not isinstance(hook_path, str) or not hook_path:
        hook_path = "/hook"

    try:
        host = _http_listener.bind_host()
    except Exception:
        return None
    if not isinstance(host, str) or not host:
        return None

    # BEST-EFFORT, AND DELIBERATELY NOT A DENY ON ABSENCE. The listener's cookie gate
    # (`supervisor.py` `_cookie_is_valid`) refuses an uncredentialed caller with a bare 401, so
    # this header is required against any gated backend. But denying HERE when the cookie cannot
    # be read would invent a new box-wide outage of exactly the shape the `ensure_listener`
    # comment above exists to prevent -- one unreadable file and every Bash call on the machine
    # denies, including against a backend that never wanted a cookie.
    #
    # The non-2xx mapping in `do_POST` is what makes that safe to skip: send the credential when
    # we have it, and if the backend refuses for want of it, the refusal becomes an affirmative
    # deny anyway. Fail-closed is preserved without stranding a backend that never wanted a
    # cookie.
    #
    # STATE THE GUARANTEE NARROWLY. A GATED backend plus an unreadable cookie still denies
    # box-wide -- correctly, the guard did not run -- just by way of the 401 rather than a local
    # branch. What best-effort buys is only the ungated case. Said plainly for the one reader
    # this comment has: someone debugging a total deny storm, seeing `REFUSED_REASON` on every
    # call, who must NOT rule the cookie out on the strength of the sentence above.
    #
    # `cookie.read` is documented never to raise and to return `None` for missing/unreadable;
    # the `except` is belt-and-braces against an engine-side regression, matching how every
    # other engine call in this function is wrapped.
    try:
        cookie_value = _cookie.read(Path(engine_root))
    except Exception:
        cookie_value = None

    return host, port, hook_path, cookie_value


def _drain(rfile: Any, length: int) -> None:
    """Discard `length` bytes without buffering them all in memory -- mirrors
    `http_listener._Handler.do_POST`'s own oversized-body handling, and for the same reason:
    responding before the client has finished sending surfaces as a connection reset rather than
    the refusal this module means to send."""
    remaining = max(0, length)
    while remaining:
        chunk = rfile.read(min(remaining, 65536))
        if not chunk:
            break
        remaining -= len(chunk)


class _ForwarderHandler(BaseHTTPRequestHandler):
    """One request: read the body, resolve today's backend, forward or deny.

    Holds no guard policy of its own -- see module docstring. `log_message` is silenced for the
    same reason `http_listener._Handler` silences it: this is a resident process on the hot path
    of every Bash call on the box, and per-request stderr from it is noise at that volume.
    """

    server_version = "coordinator-http-hook-forwarder"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    def _respond(self, status: int, body: bytes, content_type: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    @property
    def _counter(self) -> "Optional[DialCounter]":
        return getattr(self.server, "dial_counter", None)

    def do_POST(self) -> None:  # noqa: N802
        # ARRIVAL IS COUNTED HERE, ahead of every validation below, so a request the harness did
        # send but this module could not parse is never filed under "the harness never dialled".
        # See `DialCounter`'s negative spec.
        counter = self._counter
        arrived_at = counter.record_arrival() if counter is not None else None
        try:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                self._respond(400, b'{"error":"bad content-length"}')
                return
            if length < 0 or length > MAX_BODY_BYTES:
                _drain(self.rfile, length)
                self._respond(413, b'{"error":"body too large"}')
                return

            body = self.rfile.read(length) if length else b""
            hook_event_name = _extract_hook_event_name(body)
            counted_event_name = _counted_event_name(body)
            if counter is not None:
                counter.record_event(counted_event_name, at=arrived_at)
                # PERSISTED HERE: after the arrival is classified, before anything that can
                # block. Everything above this line is a header read and a JSON parse -- cheap
                # and incapable of hanging. Everything BELOW resolves discovery and forwards over
                # a socket, which on a busy engine takes seconds and can be killed part-way.
                #
                # Leaving persistence to the handler's `finally` alone put both facts behind that
                # slow work, so an arrival already correct in memory stayed invisible on disk for
                # seconds and read, to any reader, as a no-dial -- the exact false negative this
                # counter exists to prevent, measured as a 5s timeout in its own suite. One write
                # here makes "the harness dialled, and it was this event" durable independently
                # of whether the rest of the handler ever completes.
                #
                # COST, MEASURED -- it stays. This executes on every Bash call on this box, ahead
                # of the verdict, which is the placement deliberately rejected for the
                # end-of-handler persist, so it owed a number rather than an argument. n=400,
                # warm, on Windows with ~32 live sessions contending for the same disk:
                # **median 0.70 ms, p90 0.94 ms, p99 1.30 ms, max 1.57 ms** on a ~1.3 KB payload.
                # Against DR-344's 50 ms budget that is ~1.4% at the median, and against the
                # measured 45.1 ms warm round trip it is ~1.5% -- noise, in a workstream whose
                # target is removing 271 ms. Kept unconditional on that evidence; an env-gate
                # would buy a rounding error and cost the durability above on every real fire.
                # Re-measure if the payload stops being small: the ring is bounded at
                # _DIAL_RING_SIZE precisely so this write cannot grow without someone choosing it.
                counter.persist()

            clone_root_header = self.headers.get(ROUTING_HEADER_NAME)
            if not clone_root_header or not clone_root_header.strip():
                clone_root_header = _extract_cwd(body)
            backend = _resolve_backend(clone_root_header)
            if backend is None:
                # NO BACKEND -- the module's own affirmative deny, never a passthrough error
                # status.
                self._respond(200, _deny_body(hook_event_name))
                return

            host, port, hook_path, cookie_value = backend
            hook_path = _apply_registration_op(hook_path, self.path)
            try:
                status, resp_body = _forward(host, port, hook_path, body, cookie_value)
            except OSError:
                # Discovery named a backend but it could not actually be reached (refused, timed
                # out, reset mid-response, ...) -- still the "no backend" case, not "backend said
                # no". A stale record pointing at a dead process must deny exactly like an absent
                # one.
                self._respond(200, _deny_body(hook_event_name))
                return

            if counter is not None:
                # COUNTED ON EVERY ANSWER, including the refusals below. This records that the
                # dial reached a backend, which it did; whether that backend produced a verdict
                # is the next branch's question, not this counter's.
                counter.record_forwarded(counted_event_name)

            if not (200 <= status < 300):
                # A TRANSPORT ERROR IS NOT A VERDICT -- and the harness FAILS OPEN on one,
                # silently on `PreToolUse` (see `REFUSED_REASON`). Relaying the raw status here
                # was this module's original behaviour and it is a guard-bypass hole: the guard
                # did not run, and the harness would run the command anyway with nothing
                # surfaced.
                #
                # MAPPED AS A CLASS, NOT PER-STATUS, DELIBERATELY. Today's live instance is the
                # listener's 401 cookie gate, but a per-status fix closes one instance and
                # leaves the shape for the next backend failure nobody enumerated. Every
                # non-2xx lands on the same affirmative deny the unreachable-backend path
                # already emits, so the module's contract -- an unevaluated guard DENIES -- holds
                # for the whole class at once.
                #
                # 2xx ONLY IS THE WHOLE TEST. A verdict rides a 200 body; nothing else here is
                # one. Note this deliberately catches the listener's own 409 skew refusal too:
                # `_resolve_backend` already screens skewed records, and a 409 arriving anyway
                # means the guard did not run, which is a deny for the same reason.
                self._respond(200, _deny_body(hook_event_name, REFUSED_REASON))
                return

            # BACKEND SAID SOMETHING -- relayed verbatim, allow included. This module authors no
            # permission decision on this path; whatever `_serve_line` returned is what the
            # harness sees.
            self._respond(status, resp_body)
        finally:
            # PERSISTED AFTER THE RESPONSE, on every exit path including the early returns above.
            # Off the latency path of a hook that fires on every Bash call, and unconditional so
            # a rejected arrival still lands on disk as an arrival.
            if counter is not None:
                counter.persist()


def _apply_registration_op(backend_hook_path: str, incoming_path: Optional[str]) -> str:
    """Carry the per-registration op from the INCOMING url onto the backend path.

    WHY THIS EXISTS, MEASURED 2026-08-27. Until this function, nothing in this module read
    `self.path` at all -- the string does not otherwise appear in the file. Every `type: "http"`
    registration, whatever url it declared, was posted to the backend's generic `hook_path` from
    the discovery record (`/hook`), where the listener routes on `hook_event_name` instead. So a
    registration written as `.../hook/hooks.agent_postuse_dispatch` reached a real backend and was
    dispatched BY EVENT, and `PostToolUse` has no event-level dispatch -- the listener answers
    "no dispatch for PostToolUse, the hook did not run". That is not a hypothesis about the
    2026-08-26 outage; it is the same answer, reproduced by hand at the live listener.

    THE BACKEND ALREADY SUPPORTS THE ROUTING; ONLY THIS SIDE WAS MISSING. Probed directly against
    the live listener on the discovery record's own port, one payload, three paths:

      /hook                                  -> "no dispatch for PostToolUse"      (event routing)
      /hook/hooks.agent_postuse_dispatch     -> engine error -32602                (REACHED the op)
      /hook/hooks.context_pressure_precompact-> 200, clean                         (REACHED and ran)

    An op-level error is proof of arrival AT THE OP: an unrouted event returns the "no dispatch"
    sentence instead, never an engine error code. So per-registration URL routing works end to
    end the moment this side stops discarding the path.

    NEGATIVE SPEC -- a bare or unrecognized path must change NOTHING. The op segment is taken only
    when the incoming path has one and it looks like an op (`<namespace>.<name>`); anything else
    falls through to the discovery record's own `hook_path` untouched. That keeps every existing
    registration, and the hand probes above that post to a bare `/hook`, on exactly the behaviour
    they have today. This function never invents a segment the caller did not send.
    """
    if not incoming_path:
        return backend_hook_path
    op = incoming_path.split("?", 1)[0].split("#", 1)[0].rstrip("/").rsplit("/", 1)[-1]
    if not op or "." not in op:
        return backend_hook_path
    return backend_hook_path.rstrip("/") + "/" + op


def _forward(
    host: str, port: int, hook_path: str, body: bytes, cookie_value: Optional[str] = None
) -> Tuple[int, bytes]:
    """POST `body` to the resolved backend and return its raw `(status, body)`.

    Any failure to connect, send, or read a complete response raises (`OSError` and its
    subclasses, `socket.timeout`/`TimeoutError`, `http.client` transport errors) rather than
    being swallowed here -- the caller (`_ForwarderHandler.do_POST`) is the one place that
    decides a raised exception means "no backend", so this function must not itself convert a
    transport failure into a response of any kind.
    """
    headers = {"Content-Type": "application/json", "Content-Length": str(len(body))}
    if cookie_value:
        # The listener's `_cookie_is_valid` refuses anything but EXACTLY ONE of these headers --
        # zero is uncredentialed, two or more reads as smuggling -- so this assignment must stay
        # a set, never an append onto a header that might already be present.
        headers[COOKIE_HEADER_NAME] = cookie_value
    conn = HTTPConnection(host, port, timeout=_FORWARD_TIMEOUT_SECS)
    try:
        conn.request("POST", hook_path, body=body, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        return resp.status, data
    finally:
        conn.close()


class _ExclusiveServer(ThreadingHTTPServer):
    """Threading server that claims its fixed port EXCLUSIVELY -- see module docstring.

    `allow_reuse_address = False` is the explicit opposite of `http_listener._Server`'s
    `allow_reuse_address = True` (http_listener.py:180); that default exists there because the
    engine's listener binds an ephemeral port nobody else contends for, and it must NOT be
    inherited here by copy-paste, because this class binds a fixed port anything on the box
    could attempt to bind too.
    """

    daemon_threads = True
    allow_reuse_address = False

    #: Set by `make_server` immediately after bind. Declared here so the attribute is part of the
    #: class rather than grafted on, and so a handler reaching it through `self.server` is
    #: reading a documented member.
    dial_counter: "Optional[DialCounter]" = None

    def server_bind(self) -> None:
        # SO_EXCLUSIVEADDRUSE only exists on Windows. Where it is absent (POSIX), the machine-
        # wide binder election named in DR-http-hook-forwarder-fixed-port.md Decision 4 is the
        # portable floor this class's exclusivity is a hardening layer on top of, not a
        # substitute for -- POSIX's own SO_REUSEADDR semantics (permits rebinding a TIME_WAIT
        # socket; does not grant first-bind-wins exclusivity) do not give this class an
        # equivalent kernel-level guarantee to assert here.
        exclusive_flag = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
        if exclusive_flag is not None:
            self.socket.setsockopt(socket.SOL_SOCKET, exclusive_flag, 1)
        super().server_bind()


def make_server(port: int = FIXED_PORT, host: Optional[str] = None) -> _ExclusiveServer:
    """Build (bind) the forwarder server on `port` (defaults to `FIXED_PORT`), but do not start
    serving it.

    `host` defaults to `http_listener.bind_host()` when the engine is resolvable at construction
    time, and to the `127.0.0.1` literal otherwise -- so this module still binds correctly, on
    the correct address, even when called before the sibling engine checkout is reachable (the
    forwarder itself does not need the engine to bind; only per-request forwarding does). A bind
    failure (port already exclusively held, e.g. by a prior winner of the binder election, or by
    a foreign process) raises `OSError` to the caller -- per
    `DR-http-hook-forwarder-fixed-port.md` Decision 4, that is a supervisor-level "not my port"
    signal, not a condition this module papers over by retrying a different port or degrading
    silently.
    """
    if host is None:
        if _ensure_engine_on_sys_path():
            try:
                from coordinator_core.warm import http_listener as _http_listener

                host = _http_listener.bind_host()
            except Exception:
                host = "127.0.0.1"
        else:
            host = "127.0.0.1"
    server = _ExclusiveServer((host, port), _ForwarderHandler)
    # BOUND, THEREFORE COUNTED FROM ZERO. Written here rather than on first request so "no file"
    # and "a file reading zero" stay different facts -- the first says no forwarder ever bound,
    # the second says one has been up since `bound_at` and nothing has dialled it. Collapsing
    # them is the failure this counter exists to end.
    server.dial_counter = DialCounter()
    server.dial_counter.persist()
    return server


def serve_forever(port: int = FIXED_PORT, host: Optional[str] = None) -> None:
    """Bind and serve the forwarder on the current thread until interrupted or killed. Defaults
    to `FIXED_PORT` when the caller does not supply one.

    Lifecycle (start, keep-alive, respawn, teardown) is deliberately NOT this module's job --
    `docs/decisions/DR-http-hook-forwarder-lifecycle.md` assigns that to the process that starts
    this one. This function is the forwarding body such an owner runs; it does not daemonize,
    fork, or manage its own restart.
    """
    server = make_server(port, host=host)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def main(argv: Optional[list] = None) -> int:
    """CLI entry point: `python -m coordinator.hooks.http_hook_forwarder [port]`.

    `port` is optional and defaults to `FIXED_PORT` -- the single module-level constant this
    plan commits (see its definition above). An explicit argument is still honoured, for tests
    and any caller that deliberately wants a different port (e.g. a non-colliding port in a
    test harness), but the lifecycle owner named in
    `docs/decisions/DR-http-hook-forwarder-lifecycle.md` need not pass one.
    """
    args = sys.argv[1:] if argv is None else argv
    if not args:
        serve_forever()
        return 0
    try:
        port = int(args[0])
    except ValueError:
        print(f"invalid port: {args[0]!r}", file=sys.stderr)
        return 2
    serve_forever(port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
