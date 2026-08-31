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

import hashlib
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
from typing import Any, Dict, Optional, Tuple

__all__ = [
    "DENY_REASON",
    "REFUSED_REASON",
    "UNREACHABLE_REASON",
    "VETOED_ENV_REASON",
    "DIAL_COUNT_PATH_ENV",
    "FIXED_PORT",
    "HEALTH_PATH",
    "DOOR_PROTOCOL_VERSION_KEY",
    "PUBLISHED_DOOR_PROTOCOL_VERSION",
    "HOLDER_NAME",
    "ROUTING_HEADER_NAME",
    "COOKIE_HEADER_NAME",
    "DialCounter",
    "dial_count_path",
    "module_fingerprint",
    "publish_door_discovery",
    "retract_door_discovery",
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

#: Reason text for the third deny this module authors: the override channel was DECLARED and then
#: VETOED (`_env_from_request_headers` found an `httpHookAllowedEnvVars` setting vetoing the
#: registration's own `allowedEnvVars`). Its own branch because it has NOTHING to do with backend
#: reachability and fires against a live, healthy, unskewed backend -- a caller told the backend
#: was unreachable will probe the listener, read the discovery record, and test skew, and every
#: one of those steps is wasted. A deny whose stated cause is false costs more than a silent one,
#: because it is acted upon.
VETOED_ENV_REASON = (
    "http-hook-forwarder: the env override channel was declared but vetoed by an "
    "httpHookAllowedEnvVars setting -- the Bash guard did not run, denying rather than "
    "forwarding an emptied env that every guard would read as 'no override requested'. "
    "The backend is not implicated; do not go looking at it"
)

#: Discovery resolved a backend and it could not be reached -- distinct from `DENY_REASON`'s
#: "nothing resolved at all". A stale record pointing at a dead process denies exactly like an
#: absent one, but the two want different first moves: this one names the address that failed.
UNREACHABLE_REASON = (
    "http-hook-forwarder: discovery named an engine backend but it could not be reached "
    "(refused, timed out, or reset mid-response) -- the Bash guard did not run, denying rather "
    "than permitting a command it never evaluated. The discovery record may be stale"
)

#: Same cap `http_listener.py` applies to its own POST bodies -- a hook event is a small JSON
#: object, and anything larger here is malformed or hostile before it reaches this module's own
#: (tiny) parsing.
MAX_BODY_BYTES = 1 << 20

#: How long the CONNECT leg may take before this module treats the backend as unreachable and
#: denies. Small: the backend is loopback-local and, per the 2026-08-19 spike, sub-millisecond
#: when it is actually up. This bound exists for the down case, not the up one.
_FORWARD_CONNECT_TIMEOUT_SECS = 2.0

#: How long the backend may spend RESPONDING once the socket is established. Deliberately an
#: order of magnitude above the connect bound, and above the engine's own per-op dispatch budget
#: (30 s at the time of writing), because this leg measures guard EXECUTION, not transport.
#:
#: WHY THE TWO LEGS CANNOT SHARE ONE NUMBER. `HTTPConnection(timeout=N)` applies N to the socket
#: for its whole lifetime -- connect, send, AND response read -- so a single small value caps how
#: long the engine may take to *evaluate a guard*, and a `socket.timeout` on that read is an
#: `OSError` that lands in `do_POST`'s unreachable branch. A live backend still legitimately
#: serving an expensive guard (a commit guard's cwd-sensitive git reads plus a delegate spawn, on
#: a large index under fleet load) is then reported as no-backend and the command is denied.
#: Reachability must never be adjudicated on a call the backend is still answering.
#:
#: Sized ABOVE the engine's own budget on purpose: the engine is the component that owns giving
#: up on a slow op, and it already does. This module's job is to not pre-empt that decision.
_FORWARD_READ_TIMEOUT_SECS = 45.0

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

#: THE FIXED-PORT SUCCESSION -- the four literals that let this module keep the seat.
#:
#: `coordinator_core.warm.front_door` binds this same 47623 (it took the value FROM here, per its
#: own module docstring), so a spawned front door takes EADDRINUSE against this process and must
#: then discriminate an ordinary lost election from a foreign squatter. It does that by
#: `probe_existing_holder`: GET `<HEALTH_PATH>` on the bound port, and a 2xx UTF-8 JSON object
#: carrying `DOOR_PROTOCOL_VERSION_KEY` as an int. Anything else -- refused, timed out, non-2xx,
#: malformed, or missing the marker -- is `ForeignHolderError`, which its AC4 branch says must
#: never be read as "no listener" nor as an ordinary defer.
#:
#: The marker is what lets `ensure_front_door` have a useful production caller: without it,
#: registering one would spawn a front-door process per session that can never win the seat --
#: ~30 concurrently on this box -- restoring nothing.
#:
#: THE MARKER IS A CONFORMANCE CLAIM, NOT AN IDENTITY CLAIM. It asserts "this holder speaks the
#: front-door hook transport", never "I am a process running front_door.py". This module is not
#: one and never becomes one; it is a legitimate ordinary-defer holder. The full holder contract
#: -- route, status, body, version, budget, and the `POST /hook` obligation the marker also
#: claims -- is written down at `hook-seam-warm-reach-contract.md` § The fixed-port succession
#: (claude-klabauter `fa736c9dba`), and is pinned engine-side by
#: `coordinator_core/warm/tests/test_front_door_succession_contract.py`.
#:
#: SPELT AS LITERALS, NOT IMPORTED, for the identical reason `COOKIE_HEADER_NAME` below is: this
#: module must keep serving when `coordinator_core` is unimportable, and the health answer in
#: particular must not depend on an engine root resolving -- an engine-gated `/health` would 501
#: on exactly the cold box where the succession has to work. Pinned against the engine's own
#: constants by `test_http_hook_forwarder_health.py`, the same way the cookie header is.
#:
#: DO NOT BUMP `PUBLISHED_DOOR_PROTOCOL_VERSION` TO FORCE A RE-ELECTION. It gates wire shape, and
#: `is_own_door_health_payload` accepts ANY int precisely so a bump is not a fleet restart.
HEALTH_PATH = "/health"
DOOR_PROTOCOL_VERSION_KEY = "door_protocol_version"
PUBLISHED_DOOR_PROTOCOL_VERSION = 1

#: Published beside the marker so a human reading a probe body can tell WHICH conforming holder
#: answered. The contract ignores extra keys, and the engine pins that they stay ignored, so this
#: is safe to carry and strictly better than an anonymous 2xx: the marker says the transport is
#: spoken, this says by whom.
HOLDER_NAME = "doe-http-hook-forwarder"

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
#: Wall-clock ceiling on the bounded wait `_resolve_backend` and `do_POST`'s `OSError` arm
#: spend re-reading discovery before they deny. THREE SECONDS, NOT FIFTEEN, AND THE NUMBER IS
#: ARGUED RATHER THAN INHERITED.
#:
#: The shape is `warm.client`'s, whose ledger is 161/166 served against a 15s deadline, p50 wait
#: 1.30s, p90 3.05s, over a boot whose own `ready_secs` is p50 0.783s / p90 1.189s. That is prior
#: art, not authority: this module runs inside a `PreToolUse` hook on the hot path of every Bash
#: call on the box, and `coordinator.local.md`'s worst-host rule governs here -- the budget is set
#: by the slowest machine any peer is sitting at, and a per-call stall is never "not a hot path".
#: Against that text a 15s hold is not defensible; ~3s recovers 89% of the same population for a
#: fifth of the worst-case stall, which is the trade this repo's own governing text picks.
#:
#: WHY A BOUNDED WAIT IS CHEAPER THAN TODAY'S DENY, on both units. A hard deny costs the caller a
#: full model retry -- more wall clock AND more process time than any wait here. And a thread
#: blocked on `time.sleep` between discovery reads consumes ~0 process time, so this adds no
#: second process-time bar. That is the whole of the process-time claim; it is not a licence to
#: treat wall clock as free, which is why the deadline above is argued down rather than adopted.
_BACKEND_WAIT_DEADLINE_SECS = 3.0

#: Gap between discovery re-reads inside the wait. Small enough that a listener that binds at
#: 0.78s is served at ~0.8s rather than at the next coarse tick.
_BACKEND_WAIT_TICK_SECS = 0.1

#: The three ways a dial that ARRIVED can still fail to reach a backend, counted separately.
#: `received_total - sum(forwarded_by_event)` collapses all three into one number, and that
#: collapse is why the incident this instrument exists for could not diagnose itself: "no record
#: was published", "a record named a backend that refused the connection", and "a record parsed
#: but was version-skewed and never resolved" have different owners and different fixes, and are
#: indistinguishable in a single gap figure. They are also what makes the wait above MEASURABLE
#: rather than merely asserted -- an effect size needs the arm it moved.
DENY_ARM_NO_BACKEND = "no_backend"
DENY_ARM_UNREACHABLE = "unreachable"
DENY_ARM_SKEW = "skew"

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


def module_fingerprint(path: Optional[Path] = None) -> Optional[str]:
    """Content fingerprint of the forwarder module THIS process is running, stamped into the
    dial-count file at bind time so a reader on the box can tell running code from on-disk code.

    THE GAP THIS CLOSES, MEASURED. `sessionstart-ensure-http-forwarder.py` decides the forwarder
    is healthy by whether it can win the fixed-port bind, and a bound port is "trusted as success
    without inspection". That probe cannot see a forwarder serving code that has since been fixed:
    this is a long-lived process, so a module edit is inert until it happens to die. Observed
    2026-08-30 -- `6b136a38d` split the connect and read bounds and the box kept denying at the
    old 2 s whole-socket bound for over an hour under a process bound 20 h earlier, 259/18357
    dials (1.41%) never forwarded, the rate still climbing while the fix sat committed.
    "The operator remembers to restart it" is not an artifact, so the fingerprint is.

    HASHED, NOT MTIME'D. A checkout, a branch switch, or a percolate rewrites mtime without
    changing a byte, and each spurious mismatch costs a real forwarder restart on a box carrying
    dozens of live sessions. Content is the thing that actually decides whether the running
    process differs from disk.

    Reads the module's own file, so it is the code that was LOADED only in the ordinary case
    where the file has not been edited since import. That is exactly the comparison wanted: a
    post-import edit is precisely the stale-code condition this reports.

    Returns `None` rather than raising if the file cannot be read -- an unreadable module must
    never take the forwarder's bind path down, and an absent fingerprint is read by the ensure
    script as "cannot tell", which is its do-not-restart case.
    """
    target = Path(path) if path is not None else Path(__file__).resolve()
    try:
        return hashlib.sha256(target.read_bytes()).hexdigest()[:16]
    except Exception:
        return None


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

      - **``module_fingerprint`` and ``pid`` accompany every count, for a reader that is not
        this process.** The bind probe in ``sessionstart-ensure-http-forwarder.py`` can only ask
        "is the port held", which a forwarder running superseded code answers exactly like a
        healthy one. These two fields are what let that script tell those apart and act: the
        fingerprint says whether the running code is the code on disk, and the pid says what to
        restart if it is not. Stamped at bind, never refreshed -- a value that tracked disk would
        describe the file rather than the process and report every stale forwarder as current.

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
        self._pid = os.getpid()
        self._module_fingerprint = module_fingerprint()
        self._bound_at = _utc_now()
        self._received_total = 0
        self._received_by_event: dict = {}
        self._forwarded_by_event: dict = {}
        self._denied_by_arm: dict = {}
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
            "schema": 3,
            "boot_id": self._boot_id,
            "pid": self._pid,
            "module_fingerprint": self._module_fingerprint,
            "bound_at": self._bound_at,
            "received_total": self._received_total,
            "received_by_event": dict(self._received_by_event),
            "forwarded_by_event": dict(self._forwarded_by_event),
            "denied_by_arm": dict(self._denied_by_arm),
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

    def record_denied(self, arm: str) -> None:
        """The arrival did not reach a backend, and THIS is the arm it died on.

        One of `DENY_ARM_NO_BACKEND` / `DENY_ARM_UNREACHABLE` / `DENY_ARM_SKEW` -- see their
        definitions for why the split is the point. Keyed by arm and NOT by event: the arm is the
        diagnostic axis (whose bug is it), and crossing it with the event name would spread a
        already-small population across a sparse grid nobody can read at a glance.

        NOT DERIVABLE FROM THE OTHER COUNTERS, which is the whole reason it is recorded rather
        than computed. `received_total - sum(forwarded_by_event)` is a single scalar that already
        conflates these three with the arrived-but-unparseable population; no arithmetic over the
        existing fields recovers which arm fired.
        """
        with self._lock:
            self._denied_by_arm[arm] = self._denied_by_arm.get(arm, 0) + 1

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


def _wait_for_discovery(
    supervisor,
    engine_root: Path,
    predicate,
    deadline_secs: float = _BACKEND_WAIT_DEADLINE_SECS,
    tick_secs: float = _BACKEND_WAIT_TICK_SECS,
):
    """Re-read the discovery record until `predicate(record)` accepts one, or the deadline lapses.

    Returns the accepted record, or the last record read (possibly `None`) when the deadline
    lapses -- the caller decides what a rejected record means, exactly as it did before this
    existed. Never raises: `read_discovery` is documented never to raise, and the belt-and-braces
    `except` mirrors the caller's.

    NEGATIVE SPEC -- A TICK RE-READS DISCOVERY AND NOTHING ELSE. No `ensure_listener`, no
    `check_health`, no skew recompute, no spawn. That restraint is the entire basis for calling
    this wait cheap: `ensure_listener` can carry a synchronous `check_health` urlopen (bounded by
    the engine's `HEALTH_CHECK_TIMEOUT_SECS`, 2.0s), a `compute_client_token` hash, and a
    `spawn_detached` interpreter start, so re-entering it per tick would turn a blocked wait into
    a spawn amplifier on the hottest path on the box -- the opposite of the fix, and precisely
    the shape `coordinator.local.md`'s worst-host rule forbids. EXACTLY ONE SPAWN TRIGGER PER
    REQUEST, at ladder entry, from the `ensure_listener` call the caller already makes.

    THE LADDER IS NOT GATED ON A PLATFORM CHECK, and that is a decision rather than an omission.
    The risk a gate would answer is a host where no listener can ever boot, which would convert
    today's fast deny into a universal stall. That cannot arise here, because every call site is
    downstream of four conditions that already establish a bootable transport: the routing header
    resolved to a real clone on disk, the engine root resolved, `coordinator_core` imported, and
    `is_engine_root` passed. A host with no engine returns `None` above this, at no cost. Nor is
    the transport Windows-only: read at `claude-klabauter` branch `candidate`, commit `32d80e15`,
    `warm/http_listener.py` and `warm/supervisor.py` carry no platform guard at all, and
    `warm/election.py` exposes TWO election doors rather than one branching function -- `elect`
    (Windows) at :282 and `elect_unix_socket` (POSIX, holding a real `fcntl.flock` across
    probe/unlink/bind) at :699. Stated precisely because the imprecise form sends a reader hunting
    for a `sys.platform` branch INSIDE `elect`, finding none, and concluding this note is stale.
    "No platform guard in the supervisor" and "the election is Windows-only" are also separate
    facts, and collapsing them is what produced the original Windows-only claim this decision
    declines to act on. A platform check here would deny POSIX callers a wait their transport can
    actually satisfy.
    """
    record = None
    deadline = time.monotonic() + max(0.0, deadline_secs)
    while True:
        try:
            record = supervisor.read_discovery(engine_root)
        except Exception:
            record = None
        if record is not None and predicate(record):
            return record
        if time.monotonic() >= deadline:
            return record
        time.sleep(tick_secs)


def _import_supervisor():
    """The engine's `warm.supervisor` module, or `None` when it cannot be imported.

    A named seam rather than an inline import so the wait paths can be exercised without an
    engine on disk. An unimportable engine is "no backend" like every other resolution failure
    here -- never an exception onto the hot path.
    """
    try:
        from coordinator_core.warm import supervisor as _supervisor

        return _supervisor
    except Exception:
        return None


def _retry_forward_after_wait(    host: str,
    port: int,
    hook_path: str,
    body_to_forward: bytes,
    cookie_value: Optional[str],
) -> Optional[Tuple[int, bytes]]:
    """One bounded wait for a SUCCESSOR listener after a dial was refused, then one re-dial.

    Returns `(status, body)` from the re-dial, or `None` when no successor appeared inside the
    window, when the re-dial refused too, or when anything about the wait could not be set up --
    every one of which leaves the caller on exactly the deny path it was already taking.

    THE PREDICATE IS A PORT CHANGE, NOT A PRESENT RECORD, and the distinction is the whole value.
    The record that produced the refused dial is still on disk and still parses; waiting for
    "a record exists" would return instantly with the same dead port and buy nothing but latency.
    A listener that has actually succeeded the dead one publishes a different port, so port
    inequality is the first moment a re-dial can succeed.

    ONE RE-DIAL, NOT A DIAL LOOP. The wait is on discovery reads (`_wait_for_discovery`'s
    negative spec); the socket is touched exactly once more, after the record changed. Dialling
    per tick would put a connect attempt on every tick of the hottest path on the box.

    NO `ensure_listener` HERE. The caller's `_resolve_backend` already fired the one spawn
    trigger this request gets; a refused dial against a published record is a succession in
    progress, not an absent listener, and re-triggering the spawn would amplify rather than wait.
    """
    engine_root = _resolved_engine_root()
    if not engine_root:
        return None
    _supervisor = _import_supervisor()
    if _supervisor is None:
        return None

    record = _wait_for_discovery(
        _supervisor,
        Path(engine_root),
        lambda rec: isinstance(rec.get("port"), int)
        and not isinstance(rec.get("port"), bool)
        and rec.get("port") > 0
        and rec.get("port") != port,
    )
    if not isinstance(record, dict):
        return None
    new_port = record.get("port")
    if not isinstance(new_port, int) or isinstance(new_port, bool) or new_port <= 0:
        return None
    if new_port == port:
        return None
    try:
        return _forward(host, new_port, hook_path, body_to_forward, cookie_value)
    except OSError:
        return None


def _resolve_backend(
    clone_root_header: Optional[str],
) -> Tuple[Optional[Tuple[str, int, str, Optional[str]]], Optional[str]]:
    """Fresh discovery read for THIS request -- never cached across requests (module docstring).

    `clone_root_header` is the raw `ROUTING_HEADER_NAME` header value off the incoming request
    (or `None`/empty when absent). Per `DR-http-hook-forwarder-fixed-port.md` Decision 1: header
    missing, blank/whitespace (the measured null for an unexpanded placeholder -- it arrives as
    an EMPTY STRING, not verbatim), or present but unresolvable to a real clone all return a
    `None` backend, and that `None` is the caller's DENY signal, same as every other "no backend"
    case below. This is the single most important branch in this module -- see CHUNK B2 brief.

    Returns `(backend, arm)`. `backend` is `(host, port, hook_path, cookie)` for a discovery
    record that names a plausible live listener, or `None` when there is nothing to forward to:
    no routing key, no engine root resolvable, the engine package itself unimportable, no
    discovery record published for the routed clone, or a record missing/malforming the fields a
    forward needs. Every one of those is "no backend", not "backend said no" -- the caller denies
    on a `None` backend, never treats it as a verdict. `arm` is `None` when `backend` resolved,
    and otherwise names which `DENY_ARM_*` the caller should record -- `DENY_ARM_NO_BACKEND` for
    every case above, `DENY_ARM_SKEW` only for the skewed-record case below.
    """
    if not clone_root_header or not clone_root_header.strip():
        return None, DENY_ARM_NO_BACKEND
    clone_root = _normalize_clone_root(clone_root_header)
    if clone_root is None:
        return None, DENY_ARM_NO_BACKEND

    engine_root = _resolved_engine_root()
    if not engine_root:
        return None, DENY_ARM_NO_BACKEND
    try:
        from coordinator_core.warm import cookie as _cookie
        from coordinator_core.warm import http_listener as _http_listener
        from coordinator_core.warm import supervisor as _supervisor
    except Exception:
        return None, DENY_ARM_NO_BACKEND

    try:
        if not _supervisor.is_engine_root(Path(engine_root)):
            return None, DENY_ARM_NO_BACKEND
    except Exception:
        return None, DENY_ARM_NO_BACKEND

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
            #
            # AND THE SPAWN IT TRIGGERS TAKES TIME, so a single re-read behind it asks the
            # question before the answer can exist. `ensure_listener` never waits by contract;
            # the listener it starts is p50 0.783s / p90 1.189s from ready, and a one-shot
            # re-read lands inside that window essentially always. The wait below is what turns
            # "spawned one for the next call" into "served this one" -- ticking on discovery
            # reads alone, per `_wait_for_discovery`'s negative spec.
            try:
                _supervisor.ensure_listener(Path(engine_root))
            except Exception:
                pass
            record = _wait_for_discovery(
                _supervisor, Path(engine_root), lambda rec: not _record_is_skewed(rec, Path(engine_root))
            )

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
            record = _wait_for_discovery(
                _supervisor, Path(engine_root), lambda rec: not _record_is_skewed(rec, Path(engine_root))
            )
            if record is not None and _record_is_skewed(record, Path(engine_root)):
                # COUNTED, BECAUSE IT WAS INVISIBLE. A skewed record that never resolves denied
                # exactly like "no record at all" in the dial file, which is why the original
                # bug row could not diagnose itself. The arm names it; it never changes the
                # verdict.
                return None, DENY_ARM_SKEW
    except Exception:
        # `read_discovery` is documented never to raise; this except is belt-and-braces so an
        # engine-side regression cannot turn "no backend" into an unhandled exception that would
        # otherwise 500 rather than deny.
        return None, DENY_ARM_NO_BACKEND
    if not isinstance(record, dict):
        return None, DENY_ARM_NO_BACKEND

    port = record.get("port")
    if not isinstance(port, int) or isinstance(port, bool) or port <= 0:
        return None, DENY_ARM_NO_BACKEND

    hook_path = record.get("hook_path")
    if not isinstance(hook_path, str) or not hook_path:
        hook_path = "/hook"

    try:
        host = _http_listener.bind_host()
    except Exception:
        return None, DENY_ARM_NO_BACKEND
    if not isinstance(host, str) or not host:
        return None, DENY_ARM_NO_BACKEND

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

    return (host, port, hook_path, cookie_value), None


def _compute_plugin_root(clone_root: Path) -> Optional[Path]:
    """Pick the plugin root under `clone_root`, probing for the `snippets/` ARTIFACT, never for
    bare directory existence.

    Two on-disk shapes, same two `provision_report.resolve_plugin_root`'s own rung 2 probes: a
    dev clone nests plugin content under `coordinator/` (`<clone_root>/coordinator`); a
    marketplace/OSS-mirror clone holds it directly (`<clone_root>`). Checked in that order. A
    bare `is_dir()` probe would return the first candidate that merely EXISTS -- on this fleet's
    dev-clone install that is a real directory holding only `bin`, composing empty contract
    blocks everywhere (see `resolve_plugin_root`'s own docstring). Probing for `snippets/`
    avoids that trap.
    """
    for candidate in (clone_root / "coordinator", clone_root):
        try:
            if (candidate / "snippets").is_dir():
                return candidate
        except OSError:
            continue
    return None


#: The engine's own override-channel header names (`warm/hook_http.py`). Mirrored here as
#: literals rather than imported: this module must stay importable with no `coordinator_core`
#: on the path. A divergence is caught by the DoE-side registration coverage test, which reads
#: the same names out of `hooks.json`.
_ENV_HEADER_PREFIX = "x-coordinator-env-"
_ENV_CHANNEL_HEADER = "x-coordinator-env-channel"
_ENV_CANARY_HEADER = "x-coordinator-env-canary"

#: Exactly `hook_http.FORWARDED_ENV_PREFIXES`. A caller's environment is not forwarded
#: wholesale; only these four prefixes are guard-relevant, and widening this tuple puts
#: unrelated session state on the wire.
_FORWARDED_ENV_PREFIXES = (
    "COORDINATOR_ALLOW_",
    "COORDINATOR_OVERRIDE_",
    "COORDINATOR_PROBE_",
    "COORDINATOR_SCOPE_",
)


def _env_from_request_headers(headers) -> Tuple[Dict[str, str], Optional[str]]:
    """The caller's forwardable environment, read off THIS request's headers.

    WHY THE FORWARDER HAS TO DO THIS AT ALL -- the defect this closes. `_forward` builds a
    fresh header dict (Content-Type, Content-Length, cookie) and sends only that, so EVERY
    inbound `X-Coordinator-Env-*` header dies here. The engine's listener reads the override
    channel off request headers (`supervisor.py`, `hook_http.env_from_headers`), which works
    when the harness dials it directly and cannot work through this hop. Registering the Bash
    matcher as `type: "http"` without this makes every `COORDINATOR_OVERRIDE_*` /
    `COORDINATOR_ALLOW_*` silently inert -- measured, not theorised: with the flip live and 40
    override headers correctly declared, `COORDINATOR_OVERRIDE_NO_VERIFY=1` still denied, while
    the same override in `payload["env"]` allowed.

    Returns `(env, disarm_reason)`, mirroring `hook_http.env_from_headers`. A non-None
    `disarm_reason` means the channel is DECLARED BUT VETOED and the caller must refuse to
    report a verdict rather than forward an empty env -- an emptied override reads to the guard
    as "no override requested", which is the PERMISSIVE direction.

    The channel/canary pair is the mechanism and neither half is optional: the static channel
    header says the registration declares the channel at all (absent means an old-style
    registration -- `({}, None)`, today's behaviour, not a fault); the interpolated canary
    detects an `httpHookAllowedEnvVars` SETTING vetoing the registration's own `allowedEnvVars`,
    which empties every override header and is otherwise indistinguishable from a caller who set
    nothing.
    """
    lowered = {k.lower(): v for k, v in headers.items()}

    if not (lowered.get(_ENV_CHANNEL_HEADER) or "").strip():
        return {}, None

    if not (lowered.get(_ENV_CANARY_HEADER) or "").strip():
        return {}, (
            "override channel declared but the canary header interpolated empty -- an "
            "httpHookAllowedEnvVars setting is vetoing this registration's allowedEnvVars, "
            "so no caller override reached the guard"
        )

    reserved = {_ENV_CHANNEL_HEADER, _ENV_CANARY_HEADER}
    out = {}
    for key, value in lowered.items():
        if not key.startswith(_ENV_HEADER_PREFIX) or key in reserved or value == "":
            continue
        name = key[len(_ENV_HEADER_PREFIX):].upper()
        if any(name.startswith(prefix) for prefix in _FORWARDED_ENV_PREFIXES):
            out[name] = value
    return out, None


def _with_injected_env(body: bytes, env: Dict[str, str]) -> bytes:
    """Put `env` onto `body` so it survives this hop, or hand `body` back unchanged.

    Same shape and the same conservatism as `_with_injected_plugin_root`: the engine's
    `payload_from_event` reads `event["env"]`, and its listener only overwrites that key when
    request headers carried an override channel -- which, through this forwarder, they never do.
    So a body-carried `env` is what reaches the guards.

    Returns `body` untouched when there is nothing to add, when it does not parse as a JSON
    object, or when it already carries an `env` mapping -- this function is a fallback author,
    never an authority over a caller-supplied value.
    """
    if not env:
        return body
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return body
    if not isinstance(parsed, dict) or isinstance(parsed.get("env"), dict):
        return body
    parsed["env"] = env
    try:
        out = json.dumps(parsed).encode("utf-8")
    except (TypeError, ValueError):
        return body
    return body if len(out) > MAX_BODY_BYTES else out


def _with_injected_plugin_root(body: bytes, clone_root_header: Optional[str]) -> bytes:
    """Inject a `plugin_root` this forwarder computed onto `body`, or hand `body` back byte-for-
    byte unchanged when it should not.

    WHY THIS EXISTS. The engine expects `plugin_root` as a body field the FORWARDER computes,
    never the resident engine itself -- the engine's own caller-context fallback reads this
    process's ambient environment, frozen to whichever session booted it, which is exactly the
    per-session hazard this plan exists to close. This function is the caller-side half: it has
    access to the per-request routing header the engine never sees.

    DEGRADE TO TODAY'S BEHAVIOUR, NEVER TO A WRONG VALUE. Every failure mode below returns
    `body` untouched, so a miss here falls through to the engine's existing fallback ladder --
    the current, non-regressed behaviour -- rather than injecting a value that could point the
    governed-surfaces manifest read at the wrong clone:

      - no routing header, or a blank one
      - `body` does not parse as a JSON object
      - `body` already carries a non-empty `plugin_root` -- this function is a fallback author,
        never an authority that overrides a caller-supplied value
      - the header does not normalize to a real clone root (`_normalize_clone_root`)
      - neither on-disk candidate under that clone root carries `snippets/`
      - the re-serialized body would exceed `MAX_BODY_BYTES`

    Reuses the ALREADY-NORMALIZED clone root the same way `_resolve_backend` does; never re-reads
    this process's own `os.environ` for it -- this forwarder is itself a long-lived resident, so
    its environment is no more the caller's than the engine's is.
    """
    if not clone_root_header or not clone_root_header.strip():
        return body
    try:
        obj = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return body
    if not isinstance(obj, dict):
        return body
    existing = obj.get("plugin_root")
    if isinstance(existing, str) and existing.strip():
        return body

    clone_root = _normalize_clone_root(clone_root_header)
    if clone_root is None:
        return body
    plugin_root = _compute_plugin_root(clone_root)
    if plugin_root is None:
        return body

    obj["plugin_root"] = str(plugin_root)
    try:
        new_body = json.dumps(obj).encode("utf-8")
    except (TypeError, ValueError):
        return body
    if len(new_body) > MAX_BODY_BYTES:
        return body
    return new_body


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

    def do_GET(self) -> None:  # noqa: N802
        """The succession health endpoint -- see `HEALTH_PATH` for the whole contract.

        DELIBERATELY THE CHEAPEST HANDLER IN THIS MODULE: a dict literal and a `json.dumps`. It
        resolves no engine root, reads no discovery record, opens no socket, and touches no
        file. Two reasons, both binding. (1) The probe is bounded at `PROBE_TIMEOUT_SECS` (2.0s)
        and a live-but-hung holder costs EVERY prober that full timeout, so anything that can
        block has no business on this path. (2) The marker claims transport conformance, not
        backend reachability -- a holder with a dead backend still speaks the transport, and
        still answers `POST /hook` with this module's own affirmative deny. Health-checking the
        backend here would answer a question the probe never asked and would hand the front door
        a foreign-holder verdict every time the engine was merely down.

        NOT COUNTED AS AN ARRIVAL. `DialCounter` answers "did the HARNESS dial the registration",
        and a front-door election probe is neither the harness nor a hook fire. Filing it would
        inflate `received_total` against a `forwarded_by_event` it can never appear in, and the
        gap between those two numbers is read as the no-backend deny rate.

        404, not 501, on any other path: 501 is the answer that made this module unrecognizable
        in the first place, and a holder that serves a real `/health` should not go on claiming
        the whole verb is unimplemented.
        """
        path = self.path.split("?", 1)[0].split("#", 1)[0]
        if path != HEALTH_PATH:
            self._respond(404, b'{"error":"not found"}')
            return
        payload = {
            DOOR_PROTOCOL_VERSION_KEY: PUBLISHED_DOOR_PROTOCOL_VERSION,
            "holder": HOLDER_NAME,
            "pid": os.getpid(),
        }
        self._respond(200, json.dumps(payload).encode("utf-8"))

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
            backend, deny_arm = _resolve_backend(clone_root_header)
            if backend is None:
                # NO BACKEND -- the module's own affirmative deny, never a passthrough error
                # status.
                if counter is not None:
                    counter.record_denied(deny_arm or DENY_ARM_NO_BACKEND)
                self._respond(200, _deny_body(hook_event_name))
                return

            host, port, hook_path, cookie_value = backend
            hook_path = _apply_registration_op(hook_path, self.path)
            header_env, env_disarm = _env_from_request_headers(self.headers)
            if env_disarm is not None:
                # A DECLARED-BUT-VETOED CHANNEL IS AN UNRUN GUARD, NOT A CLEAN ONE -- the same
                # call the engine's own listener makes. Forwarding with an emptied env would
                # have every guard read "no override requested" and decide in the permissive
                # direction, so refuse the verdict instead.
                self._respond(200, _deny_body(hook_event_name, VETOED_ENV_REASON))
                return
            body_to_forward = _with_injected_plugin_root(body, clone_root_header)
            body_to_forward = _with_injected_env(body_to_forward, header_env)
            try:
                status, resp_body = _forward(host, port, hook_path, body_to_forward, cookie_value)
            except OSError:
                # Discovery named a backend but it could not actually be reached (refused, timed
                # out, reset mid-response, ...) -- still the "no backend" case, not "backend said
                # no". A stale record pointing at a dead process must deny exactly like an absent
                # one -- same decision, different first move, so a different reason string.
                #
                # RETRIED ONCE AGAINST A RE-READ RECORD BEFORE DENYING. A record naming a backend
                # that refuses the connection is the same "not there yet" fact as no record at
                # all: a listener mid-succession has published its port and not yet accepted on
                # it. Waiting for a record whose port CHANGED is the discriminating move -- a
                # re-dial to the identical port would only re-sample the same refusal, so the
                # predicate is port inequality, not mere presence. The deny below is unchanged
                # in every other respect; this only spends the same bounded window the no-record
                # arm spends, and only on a path that was already going to deny.
                retried = _retry_forward_after_wait(
                    host, port, hook_path, body_to_forward, cookie_value
                )
                if retried is None:
                    if counter is not None:
                        counter.record_denied(DENY_ARM_UNREACHABLE)
                    self._respond(200, _deny_body(hook_event_name, UNREACHABLE_REASON))
                    return
                status, resp_body = retried

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
    conn = HTTPConnection(host, port, timeout=_FORWARD_CONNECT_TIMEOUT_SECS)
    try:
        # CONNECT UNDER THE SHORT BOUND, READ UNDER THE LONG ONE. `connect()` is called
        # explicitly rather than left to `request()` so the socket exists before the deadline is
        # widened; re-arming it afterwards is what stops the read leg inheriting the down-case
        # bound (see `_FORWARD_READ_TIMEOUT_SECS`). `conn.sock` is None only if `connect()`
        # raised, which this function deliberately does not catch.
        conn.connect()
        if conn.sock is not None:
            conn.sock.settimeout(_FORWARD_READ_TIMEOUT_SECS)
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


#: The engine root `publish_door_discovery` actually wrote against, captured so the
#: retract cannot re-resolve a different one. `None` means nothing was published, which
#: is also what makes the retract a no-op rather than a guess.
_PUBLISHED_DOOR_ROOT: "Optional[Any]" = None


def publish_door_discovery(port: int) -> bool:
    """Publish the front-door discovery record naming THIS process as the holder of
    `FIXED_PORT`. True iff a record was written.

    WHY A NON-DOOR PUBLISHES THIS. The `/health` marker (see `HEALTH_PATH`) fixed the
    front door's CLASSIFICATION of this process -- a conforming holder is now an ordinary
    `ElectionLost` rather than a `ForeignHolderError`. It did not fix the CHURN.
    `front_door.should_spawn` debounces on this record, and while this forwarder holds
    the seat no door ever wins the election, so none ever writes one: the debounce input
    is never produced, `should_spawn` returns True on every call, and a `SessionStart`
    caller spawns a door per session forever -- ~30 concurrently on this box, each
    existing only to lose. Measured 2026-08-30, before wiring anything. With this record
    present `ensure_front_door` takes branch 1 instead -- live record, protocol version
    satisfied, `probe_existing_holder` sees our marker -- and returns the URL without
    spawning. That is the whole point: the caller becomes a real no-op on a healthy box.

    THROUGH THE ENGINE'S OWN WRITER, never by hand-writing the JSON.
    `front_door.write_discovery` is the sole publisher and stamps `health_path` and
    `door_protocol_version` from the same constants `probe_existing_holder` reads, so the
    two surfaces cannot drift. Confirmed as the sanctioned route by claude-klabauter-em,
    2026-08-30, along with every field below.

    `engine_sha=None` DELIBERATELY. It is `Optional[str]`, no consumer reads it today, and
    this process is not an engine build -- a fabricated sha would be worse than an honest
    null.

    `pid` and `stable_pid_start_epoch` must be OURS, and they are the only inputs to
    `discovery_is_live`: it requires the process to still exist AND its birth instant to
    match, so a recycled pid reads dead. Any other value and the record reads dead on the
    first call and the churn comes straight back.

    THE ROOT IS `current_engine_clone()`, not this module's own resolved engine root, and
    the distinction is load-bearing. `discovery_path` is
    `breadcrumb.svc_dir(root)/warm-front-door.json`, `svc_dir` keys on a sha1 of the
    resolved clone path, and `ensure_front_door` defaults its root to
    `current_engine_clone()`. A record written against any other clone is invisible to
    every real caller and the churn survives, silently.

    NO REFRESH CADENCE, BY CONTRACT. Written once at bind and that is the whole
    obligation: `started_at` feeds only `should_spawn`'s debounce, which branch 1 never
    reaches, so a days-old `started_at` on a live holder is harmless.

    NEVER RAISES, NEVER BLOCKS THE BIND. A box with no importable engine publishes
    nothing -- and needs nothing, since `ensure_front_door` gates on `is_engine_root` and
    returns before it ever reads this file there.
    """
    if port != FIXED_PORT:
        # ONLY THE REAL SEAT IS EVER ADVERTISED. Every test in this repo binds port 0, and
        # a record written from one would name a short-lived test process as the machine's
        # front-door holder -- clobbering the live one on the operator's own box, since
        # `svc_dir` keys on the clone and knows nothing about a test.
        return False
    if not _ensure_engine_on_sys_path():
        return False
    try:
        from coordinator_core.warm import front_door as _front_door

        # THE ENGINE'S OWN HELPER, not a local copy. This module's no-engine-import rule
        # does not reach here: three lines up it imports `front_door` outright, and that
        # is the module already exposing this exact function -- every other writer of this
        # record (`front_door`, `supervisor`, `server`) calls it. A local copy would import
        # `session.core._win_create_time_epoch` instead, trading one engine-private name
        # for another while adding a second thing that can disagree about the value
        # `discovery_is_live` compares against.
        epoch = _front_door._self_stable_pid_start_epoch()
        if epoch is None:
            # Cannot vouch for our own birth instant, so cannot write a record
            # `discovery_is_live` would ever accept. Publishing a zero would advertise a
            # holder that reads dead -- strictly worse than the absent record, which at
            # least fails honestly to the spawn path.
            return False

        root = _front_door.current_engine_clone()
        _front_door.write_discovery(
            port=port,
            pid=os.getpid(),
            stable_pid_start_epoch=epoch,
            engine_sha=None,
            engine_root=root,
        )
        global _PUBLISHED_DOOR_ROOT
        _PUBLISHED_DOOR_ROOT = root
        return True
    except Exception:
        return False


def retract_door_discovery(port: int) -> None:
    """Remove the discovery record iff it still names THIS process.

    THE OTHER HALF, and the one whose absence was measured rather than theorised: an
    out-of-band front door started 2026-08-27 left a record naming its pid for three days
    after the process was gone. Nothing reaps this file -- the litter sweep does not cover
    the name -- so a publisher that does not retract is one that lies to the next reader
    until something happens to overwrite it.

    THE ROOT IS THE ONE PUBLISH CAPTURED, never a fresh `current_engine_clone()`.
    `discovery_path` is `svc_dir(root)/warm-front-door.json` and `svc_dir` keys on a
    sha1 of the resolved clone path, so if that resolution drifts during this
    process's lifetime -- `COORDINATOR_SETTINGS_HOME` or the machine-local registry
    edited under a resident that has been bound for hours -- a re-resolving retract
    would unlink a path this process never wrote and leave its real record behind.
    That is the three-day orphan again, reached through a root that moved instead of
    a process that died.

    `owner_pid` makes it safe under a race: `unlink_discovery` re-reads the record and
    removes the file only if it still names us, so a successor that has already published
    its own is never deleted by a predecessor's slow teardown.

    Never raises: this runs in a `finally` on the way out of `serve_forever`, and a
    teardown that raises would mask whatever actually stopped the server.
    """
    if port != FIXED_PORT:
        return
    if _PUBLISHED_DOOR_ROOT is None:
        return
    if not _ensure_engine_on_sys_path():
        return
    try:
        from coordinator_core.warm import front_door as _front_door

        _front_door.unlink_discovery(_PUBLISHED_DOOR_ROOT, owner_pid=os.getpid())
    except Exception:
        return


def serve_forever(port: int = FIXED_PORT, host: Optional[str] = None) -> None:
    """Bind and serve the forwarder on the current thread until interrupted or killed. Defaults
    to `FIXED_PORT` when the caller does not supply one.

    Lifecycle (start, keep-alive, respawn, teardown) is deliberately NOT this module's job --
    `docs/decisions/DR-http-hook-forwarder-lifecycle.md` assigns that to the process that starts
    this one. This function is the forwarding body such an owner runs; it does not daemonize,
    fork, or manage its own restart.

    It DOES own publishing and retracting the front-door discovery record, and that is not a
    lifecycle exception. The record asserts "this process holds FIXED_PORT right now" -- a fact
    only the process that won the bind can state, and only it can withdraw. Publishing happens
    after `make_server` returns, i.e. after the bind actually succeeded, so a forwarder that lost
    the election never advertises a seat it does not hold. See `publish_door_discovery` for why a
    non-door publishes this at all.
    """
    server = make_server(port, host=host)
    publish_door_discovery(port)
    try:
        server.serve_forever()
    finally:
        retract_door_discovery(port)
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
