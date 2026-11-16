"""Ordered address-list resolver for a far box, run only after its primary name has failed.

A box's machine-local list (`unimatrix.addresses.<box>`) names the IPs a Wi-Fi band hop can move it to.
An address is accepted only when ssh verifies the box's own host key under `HostKeyAlias=<box>` with
`StrictHostKeyChecking=yes`: an address held by a different machine is `not-this-box`, never the box.
No address, MAC or fingerprint lives in code; every value is read through the injected `read_key`.
Dials at a verified address build their channel with the ORIGINAL box id, never a key re-derived from the IP.
"""
from __future__ import annotations

import ipaddress
import socket
import subprocess
import sys

ADDRESSES_KEY = "unimatrix.addresses.{box}"
HOSTKEY_KEY = "unimatrix.hostkey.{box}"
MAX_ADDRESSES = 8
NOT_THIS_BOX = "not-this-box"
UNREACHABLE = "unreachable"
OK = "ok"
_MISMATCH_MARKERS = ("REMOTE HOST IDENTIFICATION HAS CHANGED", "Host key verification failed")


def box_addresses(box, read_key):
    """The box's ordered address list: comma-separated IP literals, order kept, duplicates and invalid tokens dropped, at most 8."""
    raw = read_key(ADDRESSES_KEY.format(box=box)) or ""
    out = []
    for token in str(raw).split(","):
        tok = token.strip()
        if tok.startswith("[") and tok.endswith("]"):
            tok = tok[1:-1]
        try:
            ipaddress.ip_address(tok.split("%", 1)[0])
        except ValueError:
            continue
        if tok not in out:
            out.append(tok)
        if len(out) == MAX_ADDRESSES:
            break
    return out


def pinned_hostkey(box, read_key):
    """The box's out-of-band host-key fingerprint (`SHA256:...`) from machine-local config, or None."""
    raw = read_key(HOSTKEY_KEY.format(box=box))
    raw = str(raw).strip() if raw else ""
    return raw or None


def target_for(user, address):
    """`user@address` (bracketed for IPv6 is not needed by ssh; the bare literal is used)."""
    return f"{user}@{address}" if user else address


def verify_argv(box, target, key=None):
    """One ssh probe argv: HostKeyAlias=<box>, strict host-key checking (never accept-new), 3s connect.

    The command is `roster`: far keys are relay keys whose forced command refuses anything else (`hostname`, `true`)."""
    argv = ["ssh"]
    if key:
        argv += ["-i", key, "-o", "IdentitiesOnly=yes"]
    argv += ["-o", "BatchMode=yes", "-o", f"HostKeyAlias={box}", "-o", "StrictHostKeyChecking=yes",
             "-o", "ConnectTimeout=3", target, "roster"]
    return argv


def classify(returncode, stderr):
    """(status, detail) for one ssh probe: a host-key refusal is `not-this-box`; rc 0 is `ok`; anything else `unreachable`."""
    text = stderr.decode("utf-8", "replace") if isinstance(stderr, (bytes, bytearray)) else str(stderr or "")
    if any(m in text for m in _MISMATCH_MARKERS):
        return NOT_THIS_BOX, "host key does not match the pinned key for this box"
    if returncode == 0:
        return OK, ""
    last = next((ln.strip() for ln in reversed(text.splitlines()) if ln.strip()), f"ssh exit {returncode}")
    return UNREACHABLE, last


def make_verify(box, key=None, *, run=subprocess.run, timeout=8):
    """A `verify(target) -> (status, detail)` that spawns one strict ssh probe for `box`."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0

    def verify(target):
        try:
            p = run(verify_argv(box, target, key), capture_output=True, timeout=timeout, creationflags=flags)
        except Exception as ex:
            return UNREACHABLE, f"{type(ex).__name__}: {ex}"
        return classify(p.returncode, p.stderr)

    return verify


def tcp_connect(address, port=22, timeout=1.0):
    """TCP pre-filter: True when `address:port` accepts a connection within `timeout` seconds. No process spawn."""
    try:
        with socket.create_connection((address.split("%", 1)[0], port), timeout=timeout):
            return True
    except OSError:
        return False


def first_answering(box, user, addresses, *, connect, verify):
    """(address | None, [(address, reason)]): the first listed address that passes `connect` and whose `verify` says ok.

    `verify(target)` returns (status, detail) as `classify` does. An address that fails `connect` is skipped
    as unreachable without a spawn; a host-key refusal is reported `not-this-box` and never chosen. An empty
    list returns (None, [])."""
    skipped = []
    for address in addresses:
        if not connect(address):
            skipped.append((address, UNREACHABLE))
            continue
        status, detail = verify(target_for(user, address))
        if status == OK:
            return address, skipped
        skipped.append((address, NOT_THIS_BOX if status == NOT_THIS_BOX else (detail or UNREACHABLE)))
    return None, skipped
