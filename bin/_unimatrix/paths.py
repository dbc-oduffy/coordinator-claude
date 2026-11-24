"""Canonical paths, box identity, and safe-alias helpers for Unimatrix.

Stdlib-only and inert on import.
"""
import ipaddress
import os
import re
import socket
from pathlib import Path

_SAFE_ALIAS_RE = None


def settings_home() -> Path:
    """Authoritative coordinator settings root ($COORDINATOR_SETTINGS_HOME, else ~/.coordinator-claude-settings)."""
    env = os.environ.get("COORDINATOR_SETTINGS_HOME")
    return Path(env) if env else Path.home() / ".coordinator-claude-settings"


def state_dir(home=None) -> Path:
    """Unimatrix state directory under settings_home()."""
    return Path(home if home is not None else settings_home()) / "unimatrix"


def sessions_dir() -> Path:
    """Claude Code session registry directory (~/.claude/sessions)."""
    return Path.home() / ".claude" / "sessions"


def safe_alias(name) -> bool:
    """True when `name` is a valid 1..64 ASCII peer/inbox alias without path traversal or double dots."""
    global _SAFE_ALIAS_RE
    if _SAFE_ALIAS_RE is None:
        _SAFE_ALIAS_RE = re.compile(r"[A-Za-z0-9_-](?:[A-Za-z0-9_.-]*[A-Za-z0-9_-])?")
    return (isinstance(name, str) and 1 <= len(name) <= 64 and ".." not in name
            and _SAFE_ALIAS_RE.fullmatch(name) is not None)


def is_ip_literal(host) -> bool:
    """True for an IPv4 or IPv6 literal (bracketed or zone-suffixed forms included)."""
    h = str(host).strip()
    if h.startswith("[") and h.endswith("]"):
        h = h[1:-1]
    try:
        ipaddress.ip_address(h.split("%", 1)[0])
        return True
    except ValueError:
        return False


def box_id(raw, ip_hosts=None) -> str:
    """The one box normaliser: drop any `user@`, keep the first dot label, drop a trailing `-lan`, lowercase.

    An IP literal has no host label: it maps through `ip_hosts` (ip -> member host name) to that
    host's label, and stays whole, never its first octet, when unmapped.
    """
    host = str(raw).rpartition("@")[2]
    if is_ip_literal(host):
        host = (ip_hosts or {}).get(host.strip("[]").lower(), host)
        if is_ip_literal(host):
            return host.strip("[]").lower()
    label = host.partition(".")[0].lower()
    return label[:-4] if label.endswith("-lan") else label


def local_box() -> str:
    """This box's id: box_id of the hostname."""
    return box_id(socket.gethostname())
