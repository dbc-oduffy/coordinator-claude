"""Codex host adapter for Unimatrix."""
import os


def own_session(env=None) -> str | None:
    """Native Codex thread id from CODEX_THREAD_ID, else None."""
    environ = os.environ if env is None else env
    return environ.get("CODEX_THREAD_ID") or None


class CodexAdapter:
    vendor = "codex"

    def own_session(self, env=None) -> str | None:
        return own_session(env)

    def discover_peers(self, **kwargs) -> list[dict]:
        return []

    async def deliver(self, peer: dict, text: str, **kwargs) -> str:
        raise NotImplementedError("Use unimatrix-peer-codex.codex_turn for Codex delivery")

    def owned_endpoints(self, state_root=None) -> set[str]:
        return set()


__all__ = ["CodexAdapter", "own_session"]
