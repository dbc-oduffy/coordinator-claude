"""Base interface for Unimatrix host adapters.

Each host (Claude, Codex, Agy, Grok) implements discovery, delivery, own-session identification,
and owned-endpoint enumeration behind one stdlib-only contract.
"""
from typing import Protocol, runtime_checkable


@runtime_checkable
class HostAdapter(Protocol):
    vendor: str

    def own_session(self, env=None) -> str | None:
        """Native session id of the calling shell, or None."""
        ...

    def discover_peers(self, **kwargs) -> list[dict]:
        """Return live peer rows [{name, vendor, target, ...}]."""
        ...

    async def deliver(self, peer: dict, text: str, **kwargs) -> str:
        """Deliver one turn to `peer` and return its reply text."""
        ...

    def owned_endpoints(self, state_root=None) -> set[str]:
        """Return local socket/pipe paths owned by live processes of this host."""
        ...
