"""coordinator_whoami/session/probes.py — git + filesystem probes for the session adopter.

Three probes for daemon-independent orientation health:

  git_state        — branch, dirty flag, ahead/behind origin/main counts.
  orientation_cache — presence and staleness of state/orientation_cache.md
                     (compares stored git_head_at_generation vs live HEAD).
  handoff_counts   — ready_to_fire / awaiting_gate counts via bin/query-records.

All three degrade gracefully: partial data or None on errors, never crash.
The orientation_cache verdict is LIVE at query time — never persisted.

Spec backlink: archive/specs/2026-05-27-whoami-session-spine-refactor.md § C2
"""
from __future__ import annotations

import json  # review: F5 — explicit top-level import; replaces __import__("json") inline (reviewer: code-reviewer, nit)
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

# Windows-only: suppress the console window that console-subsystem child
# processes (git, node, ...) flash when this process has no console to inherit
# (e.g. spawned by an MCP server or a GUI Claude Code host). POSIX: empty dict —
# CREATE_NO_WINDOW is a Windows-only attribute, so the ternary short-circuits.
_NO_CONSOLE_WINDOW = (
    {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_git(args: list[str], cwd: Path | None = None) -> tuple[str, int]:
    """Run a git subcommand; return (stdout.strip(), returncode). Never raises."""
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            cwd=str(cwd) if cwd else None,
            timeout=10,
            **_NO_CONSOLE_WINDOW,
        )
        return result.stdout.strip(), result.returncode
    except Exception:
        return "", -1


def git_root() -> Path | None:
    """Return the git repo root for cwd, or None if not in a git repo."""
    # review: F4 — made public (was _git_root); envelope.py is an in-package
    # caller with standing to use this, and private cross-module calls are
    # an API boundary smell (reviewer: code-reviewer, P2)
    out, rc = _run_git(["rev-parse", "--show-toplevel"])
    if rc == 0 and out:
        return Path(out)
    return None


# ---------------------------------------------------------------------------
# git_state probe
# ---------------------------------------------------------------------------

def probe_git_state() -> dict[str, Any]:
    """Return branch, dirty flag, and ahead/behind counts vs origin/main.

    Degrade gracefully: unknown values set to None on git errors.
    ahead/behind are computed via 'git rev-list --count' against origin/main;
    if origin/main is unreachable (no remote, no fetch), both default to None.
    """
    result: dict[str, Any] = {
        "branch": None,
        "dirty": None,
        "ahead": None,
        "behind": None,
    }

    # Branch name
    branch_out, rc = _run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    if rc == 0 and branch_out:
        result["branch"] = branch_out
    else:
        # Could not determine branch (detached HEAD or no repo)
        return result

    # Dirty flag — any uncommitted changes (staged or unstaged)
    status_out, rc = _run_git(["status", "--porcelain"])
    if rc == 0:
        result["dirty"] = bool(status_out)
    # If rc != 0, leave dirty=None (git unavailable for status)

    # ahead/behind relative to origin/main
    ahead_out, rc_ahead = _run_git(["rev-list", "--count", "origin/main..HEAD"])
    behind_out, rc_behind = _run_git(["rev-list", "--count", "HEAD..origin/main"])
    if rc_ahead == 0 and ahead_out.isdigit():
        result["ahead"] = int(ahead_out)
    if rc_behind == 0 and behind_out.isdigit():
        result["behind"] = int(behind_out)

    return result


# ---------------------------------------------------------------------------
# orientation_cache probe
# ---------------------------------------------------------------------------

def _read_frontmatter_field(path: Path, field: str) -> str | None:
    """Extract a scalar frontmatter field value from a YAML-fenced markdown file.

    Reads only up to the closing '---' delimiter; never loads the full file body.
    Returns None if the field is absent or the file has no valid frontmatter.
    """
    try:
        # review: F13 — removed dead `in_frontmatter = False`; never read in its False state (reviewer: code-reviewer, nit)
        with path.open(encoding="utf-8") as fh:
            for i, line in enumerate(fh):
                stripped = line.strip()
                if i == 0:
                    if stripped == "---":
                        in_frontmatter = True
                    else:
                        return None
                    continue
                if stripped == "---":
                    break  # end of frontmatter
                if stripped.startswith(f"{field}:"):
                    value = stripped[len(f"{field}:"):].strip().strip('"').strip("'")
                    return value if value else None
    except OSError:
        return None
    return None


def _current_git_head() -> str | None:
    """Return the current git HEAD SHA (full), or None."""
    out, rc = _run_git(["rev-parse", "HEAD"])
    if rc == 0 and out:
        return out
    return None


def probe_orientation_cache() -> dict[str, Any]:
    """Report orientation cache presence and HEAD-staleness.

    Reads state/orientation_cache.md frontmatter field 'git_head_at_generation'
    and compares to the current git HEAD. Verdict is computed live at call time —
    never persisted.

    Returns:
        present: bool — whether state/orientation_cache.md exists
        stale:   bool | None — True if stored HEAD != live HEAD; None if
                 present=False or HEAD unavailable
        stored_head: str | None — the frontmatter value
        live_head:   str | None — current git HEAD SHA
    """
    result: dict[str, Any] = {
        "present": False,
        "stale": None,
        "stored_head": None,
        "live_head": None,
    }

    # Locate the repo root first; fall back to HOME/.claude if not in a git repo
    root = git_root()
    if root is None:
        # Try $HOME/.claude as a fallback (coordinator is typically installed there)
        home = Path(os.environ.get("HOME", os.environ.get("USERPROFILE", "")))
        root = home / ".claude" if home else None

    if root is None:
        return result

    cache_path = root / "state" / "orientation_cache.md"
    result["present"] = cache_path.exists()
    if not result["present"]:
        return result

    stored_head = _read_frontmatter_field(cache_path, "git_head_at_generation")
    result["stored_head"] = stored_head

    live_head = _current_git_head()
    result["live_head"] = live_head

    if stored_head is not None and live_head is not None:
        # Normalize before comparing: the cache may store a short SHA
        # (e.g. "36a7a3d4"), a branch name, or a tag — none of which equals the
        # full `rev-parse HEAD` by naive string compare, so a naive `!=` reports
        # stale=True even for a fresh cache. Resolve the stored value to a full
        # commit SHA via `git rev-parse <stored>^{commit}`; compare full-to-full.
        # Fall back to prefix match (short stored vs full live) then exact compare
        # if the stored value is not resolvable on this machine (e.g. rebased away).
        resolved, rc = _run_git(["rev-parse", "--verify", "--quiet", f"{stored_head}^{{commit}}"])
        if rc == 0 and resolved:
            result["stale"] = resolved != live_head
        else:
            result["stale"] = not (
                live_head.startswith(stored_head) or stored_head == live_head
            )
    # else stale stays None (insufficient data)

    return result


# ---------------------------------------------------------------------------
# handoff_counts probe
# ---------------------------------------------------------------------------

def _resolve_query_records_path() -> Path | None:
    """Resolve the absolute path to query-records.js.

    Uses $HOME/.claude/plugins/coordinator/bin/query-records.js
    — mirrors the absolute-path resolution used elsewhere for this hook family.
    Returns None if the file does not exist.
    """
    # review: F11 — honor CLAUDE_HOME env var before hardcoded ~/.claude fallback,
    # mirrors sentinel pattern `CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"` (reviewer: code-reviewer, P2)
    # USERPROFILE rung: HOME is a POSIX convention -- native Windows shells
    # (PowerShell, cmd.exe) set USERPROFILE instead, so a HOME-only fallback
    # silently resolves home to "" there. Single boolop chain (not a
    # separately-resolved `home` variable) so CLAUDE_HOME/HOME/USERPROFILE
    # precedence is textually visible in one line.
    home_str = os.environ.get("CLAUDE_HOME") or os.environ.get("HOME") or os.environ.get("USERPROFILE") or ""
    if not home_str:
        return None
    base = Path(home_str) / ".claude"
    candidate = base / "plugins" / "coordinator-claude" / "coordinator" / "bin" / "query-records.js"
    return candidate if candidate.exists() else None


def _query_records_count(qr_path: Path, record_type: str, where: str, root: str | None) -> int | None:
    """Invoke node query-records.js and count returned JSON records.

    Returns an integer count, or None on any invocation / parse error.
    """
    cmd = ["node", str(qr_path), "--type", record_type, "--where", where, "--format", "json"]
    if root:
        cmd.extend(["--root", root])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15, **_NO_CONSOLE_WINDOW)
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        if isinstance(data, list):
            return len(data)
    except Exception:
        pass
    return None


def probe_handoff_counts() -> dict[str, Any]:
    """Return ready_to_fire and awaiting_gate handoff counts.

    Invokes bin/query-records.js via node at an absolute path
    (NOT cwd-relative).
    Degrades to null counts on any error (node absent, qr script absent,
    no state/handoffs directory, parse failure).
    """
    result: dict[str, Any] = {
        "ready_to_fire": None,
        "awaiting_gate": None,
    }

    qr_path = _resolve_query_records_path()
    if qr_path is None:
        return result

    # Verify node is available
    try:
        subprocess.run(["node", "--version"], capture_output=True, timeout=5, **_NO_CONSOLE_WINDOW)
    except Exception:
        return result

    root = git_root()
    root_str = str(root) if root else None

    result["ready_to_fire"] = _query_records_count(
        qr_path, "handoff", "deployment_state=ready_to_fire", root_str
    )
    result["awaiting_gate"] = _query_records_count(
        qr_path, "handoff", "deployment_state=awaiting_gate", root_str
    )

    return result
