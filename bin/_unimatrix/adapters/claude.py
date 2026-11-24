"""Claude Code host adapter for Unimatrix."""
import os
from pathlib import Path

from _unimatrix.paths import sessions_dir


def own_session(env=None) -> str | None:
    """Native Claude session id from CLAUDE_SESSION_ID / CLAUDE_CODE_SESSION_ID, else None."""
    environ = os.environ if env is None else env
    return environ.get("CLAUDE_SESSION_ID") or environ.get("CLAUDE_CODE_SESSION_ID") or None


class ClaudeAdapter:
    vendor = "claude"

    def own_session(self, env=None) -> str | None:
        return own_session(env)

    def discover_peers(self, **kwargs) -> list[dict]:
        return []  # Claude sessions register directly in ~/.claude/sessions

    async def deliver(self, peer: dict, text: str, **kwargs) -> str:
        raise NotImplementedError("Claude delivery uses native session sockets via roster/relay")

    def owned_endpoints(self, state_root=None) -> set[str]:
        return set()


__all__ = ["ClaudeAdapter", "own_session", "sessions_dir"]
