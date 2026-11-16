"""Shared wording for a failed `git fetch`: git's last stderr line, the remote URL, and
an ssh-agent remediation. Pure text; callers run git themselves and only on the failure path.

Callers: refresh-plugin-live-install.py (git-leg, editable_sibling_venv) and
coordinator/lib/percolate/dest_refresh.py. The remediation never names a slash command and
never offers moving the key to disk or `IdentityAgent none` as the default fix.
"""

from __future__ import annotations

import re

DEFAULT_FALLBACK = "git fetch failed"

_SSH_AGENT_OR_AUTH_FAILURE = re.compile(
    r"agent refused operation"
    r"|sign_and_send_pubkey"
    r"|permission denied \(publickey"
    r"|could not open a connection to your authentication agent"
    r"|error connecting to agent",
    re.IGNORECASE,
)


def last_line(text: str | None, fallback: str = DEFAULT_FALLBACK) -> str:
    """Last non-blank line of `text`, stripped; `fallback` when there is none."""
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return lines[-1] if lines else fallback


def is_ssh_agent_failure(stderr: str | None) -> bool:
    """True when `stderr` shows an ssh agent or public-key auth failure."""
    return bool(_SSH_AGENT_OR_AUTH_FAILURE.search(stderr or ""))


def ssh_remediation(stderr: str | None) -> str:
    """Runnable remediation for an ssh agent/auth failure in `stderr`; "" for any other failure."""
    if not is_ssh_agent_failure(stderr):
        return ""
    return (
        "Unlock or approve your SSH agent (e.g. unlock 1Password and approve the SSH key "
        "request), confirm with `ssh-add -l`, then re-run. "
        "Only for a box whose key deliberately lives on disk instead of an agent: set "
        "IdentityFile with IdentitiesOnly yes for the host in ~/.ssh/config."
    )


def fetch_failure_detail(stderr: str | None, url: str | None, fallback: str = DEFAULT_FALLBACK) -> str:
    """One line naming git's last stderr line and the remote URL the fetch tried."""
    return "{0} (remote: {1})".format(last_line(stderr, fallback), (url or "").strip() or "unknown")
