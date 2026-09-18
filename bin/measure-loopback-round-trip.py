"""
coordinator.bin.measure-loopback-round-trip -- committed probe for the local HTTP round-trip term
in the hook-routing budget.

Ported from DoE-claude `coordinator/bin/measure-loopback-round-trip.py` (W3-C1,
`docs/plans/2026-09-18-doe-holds-no-scripts.md`) -- mechanical move, no behavioural change. No
path resolution at all (§ Path resolution): the module never touches `__file__`, spawns nothing,
and only opens an in-process loopback HTTP server.

Purpose: the round-trip cost of a fired hook talking to a local listener has no structural
signature (no module, no file open, no spawn), so `measure-hook-class-cost.py`'s instrument cannot
see it and it has to be measured directly. This module is that measurement, committed rather than
scratch.

Negative spec -- why this file exists at all rather than a throwaway listener in a session
scratchpad: the first measurement of this term WAS a throwaway. It produced a bimodal 14-17ms band,
which was published to a peer repo as `windows_timer_quantum_floor` (~15.6ms/call, read as the
15.625ms Windows system timer quantum). Claude-klabauter-em refuted it off the published distribution
alone -- 33 of 200 samples were sub-millisecond on the same box and the same fresh-connection shape,
which no real 15ms floor can produce -- and their named-pipe control agreed. Re-measurement here
found zero of 800 samples in that band. The original harness was gone by then, so its actual defect
can never be identified. A peer-facing number whose harness is not committed is a number that
outlives the ability to reproduce it. Do not move this back to a scratchpad.

Findings this probe pins, both on Windows (`docs/research/2026-08-19-hook-class-route-budget.md`):
  - the round trip on the `127.0.0.1` literal is sub-millisecond (median ~0.2ms), across raw-socket
    and urllib clients, Nagle-on and TCP_NODELAY, listener in-process and out-of-process;
  - dialing the NAME `localhost` costs ~2s/call against an IPv4-bound listener -- dual-stack
    resolution trying ::1 and waiting out the TCP SYN retry. Clients must dial the literal.

Reported as a full distribution with explicit buckets, never a mean: a mean over a bimodal sample
describes nothing that happens, which is how the retracted figure survived as long as it did.

Usage:
    python coordinator/bin/measure-loopback-round-trip.py            # all arms
    python coordinator/bin/measure-loopback-round-trip.py --n 500
    python coordinator/bin/measure-loopback-round-trip.py --skip-localhost
"""
from __future__ import annotations

import argparse
import http.server
import json
import socket
import statistics
import threading
import time
import urllib.request
from typing import List

PROBE_BODY = b'{"hook_event_name": "PreToolUse", "tool_input": {"command": "echo probe"}}'
PROBE_RESPONSE = b'{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}'


BUCKETS = ("<1ms", "1-5ms", "5-14ms", "14-17ms", ">17ms")
LOCALHOST_ARM_N = 50
"""The localhost arm is capped independently: at ~2s/call it dominates wall-clock, and 50 samples
already separate it from the literal by four orders of magnitude."""


def _bucket(ms: float) -> str:
    if ms < 1:
        return "<1ms"
    if ms < 5:
        return "1-5ms"
    if ms < 14:
        return "5-14ms"
    if ms <= 17:
        return "14-17ms"
    return ">17ms"


def _make_handler(disable_nagle: bool) -> type:
    class ProbeHandler(http.server.BaseHTTPRequestHandler):
        disable_nagle_algorithm = disable_nagle
        protocol_version = "HTTP/1.0"

        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(PROBE_RESPONSE)))
            self.end_headers()
            self.wfile.write(PROBE_RESPONSE)

        def log_message(self, format: str, *args: object) -> None:
            pass

    return ProbeHandler


def raw_socket_arm(host: str, port: int, n: int, nodelay: bool) -> tuple:
    """Fresh connection per call -- the shape a fired hook actually uses.

    The success comparison happens OUTSIDE the timed window: chunks are collected into a
    list in-loop (never `+=` concatenation, which is itself in-window work) and joined only
    after the clock has already stopped, then compared against `PROBE_RESPONSE`. A call whose
    response does not carry the probe's own success token is not a slow sample -- it is not a
    sample, and is counted as a failure instead of timed.
    """
    request = (
        b"POST / HTTP/1.0\r\nHost: " + host.encode() + b"\r\n"
        b"Content-Type: application/json\r\n"
        b"Content-Length: " + str(len(PROBE_BODY)).encode() + b"\r\n\r\n" + PROBE_BODY
    )
    samples: List[float] = []
    failures = 0
    for _ in range(n):
        sock = socket.socket()
        if nodelay:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        started = time.perf_counter()
        sock.connect((host, port))
        sock.sendall(request)
        chunks: List[bytes] = []
        while True:
            buf = sock.recv(65536)
            if not buf:
                break
            chunks.append(buf)
        elapsed_ms = (time.perf_counter() - started) * 1000
        sock.close()
        body = b"".join(chunks)
        if body.endswith(PROBE_RESPONSE):
            samples.append(elapsed_ms)
        else:
            failures += 1
    return samples, failures


def urllib_arm(host: str, port: int, n: int) -> tuple:
    """`response.read()` already materializes the body inside the timed window, so only the
    `PROBE_RESPONSE` assertion is added here, after the read and outside the window -- same
    admissibility rule as `raw_socket_arm`'s post-join compare."""
    url = f"http://{host}:{port}/"
    samples: List[float] = []
    failures = 0
    for _ in range(n):
        request = urllib.request.Request(
            url, data=PROBE_BODY, headers={"Content-Type": "application/json"}
        )
        started = time.perf_counter()
        with urllib.request.urlopen(request) as response:
            body = response.read()
        elapsed_ms = (time.perf_counter() - started) * 1000
        if body == PROBE_RESPONSE:
            samples.append(elapsed_ms)
        else:
            failures += 1
    return samples, failures


def report(label: str, samples: List[float], failures: int = 0) -> dict:
    """Refuses rather than printing when any call in this arm failed to return the probe's
    own `PROBE_RESPONSE` success token -- a sample from a failed call is not a slow sample,
    it must never reach the median. The refusal names how many calls failed."""
    if failures:
        total = len(samples) + failures
        raise RuntimeError(
            f"[{label}] refusing to report: {failures}/{total} calls did not return "
            "PROBE_RESPONSE -- not admissible as latency"
        )
    ordered = sorted(samples)
    n = len(ordered)
    counts = {name: 0 for name in BUCKETS}
    for value in ordered:
        counts[_bucket(value)] += 1
    print(
        f"[{label}] n={n} min {ordered[0]:.3f} median {statistics.median(ordered):.3f} "
        f"p90 {ordered[int(0.9 * n)]:.3f} max {ordered[-1]:.3f}",
        flush=True,
    )
    print("   " + "  ".join(f"{name}: {counts[name]}" for name in BUCKETS), flush=True)
    return {"label": label, "n": n, "buckets": counts}


def _serve(disable_nagle: bool) -> tuple:
    server = http.server.HTTPServer(("127.0.0.1", 0), _make_handler(disable_nagle))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_address[1]


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=200, help="samples per fast arm")
    parser.add_argument(
        "--skip-localhost",
        action="store_true",
        help="skip the ~2s/call name-resolution arm",
    )
    args = parser.parse_args(argv)

    results = []
    for disable_nagle in (False, True):
        server, port = _serve(disable_nagle)
        arm = "TCP_NODELAY" if disable_nagle else "Nagle-on"
        try:
            raw_samples, raw_failures = raw_socket_arm("127.0.0.1", port, args.n, disable_nagle)
            results.append(report(f"raw 127.0.0.1 {arm}", raw_samples, raw_failures))
            urllib_samples, urllib_failures = urllib_arm("127.0.0.1", port, args.n)
            results.append(report(f"urllib 127.0.0.1 {arm}", urllib_samples, urllib_failures))
            if not args.skip_localhost and not disable_nagle:
                loc_samples, loc_failures = urllib_arm("localhost", port, LOCALHOST_ARM_N)
                results.append(report("urllib localhost (name)", loc_samples, loc_failures))
        finally:
            server.shutdown()

    in_band = sum(r["buckets"]["14-17ms"] for r in results)
    total = sum(r["n"] for r in results)
    print(f"\n14-17ms band: {in_band}/{total} samples.", flush=True)
    if in_band:
        print(
            "Non-zero in-band count -- this is the shape of the retracted "
            "`windows_timer_quantum_floor`. Identify the harness defect BEFORE publishing "
            "the figure to a peer repo; see this module's negative spec.",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
