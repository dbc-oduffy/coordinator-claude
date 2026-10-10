"""Collaborator detection: identity canonicalization over a mailmap and a bot denylist."""
from __future__ import annotations

import re
import subprocess
from collections.abc import Iterable, Mapping
from pathlib import Path

NOREPLY_SUFFIX = "@users.noreply.github.com"
BOT_SUFFIX = "[bot]"

# Bare two-field grammar only: `<canonical-email> <alias-email>`. Lines carrying a name or
# any other token (the four-field form) do not match and are skipped, never guessed.
_BARE_LINE = re.compile(r"^<([^<>\s]+)>\s+<([^<>\s]+)>$")


def parse_mailmap(path: str | Path) -> Mapping[str, str]:
    """Read a `.mailmap` file into an `{alias_email: canonical_email}` mapping (lowercased).

    Missing or unreadable file yields an empty mapping. Comment, blank, and non-bare-form
    lines are skipped.
    """
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    mapping: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _BARE_LINE.match(line)
        if m:
            mapping[m.group(2).lower()] = m.group(1).lower()
    return mapping


_GIT_LOG_FORMAT = "%x1e%ae%n%(trailers:key=Co-authored-by,valueonly)"
_ANGLE_EMAIL = re.compile(r"<([^<>\s]+)>")


def parse_git_log(output: str) -> list[str]:
    """Extract raw author and `Co-authored-by:` emails from `probe_raw_emails` output."""
    emails: list[str] = []
    for record in output.split("\x1e"):
        lines = record.splitlines()
        if not lines:
            continue
        if lines[0].strip():
            emails.append(lines[0].strip())
        for line in lines[1:]:
            emails.extend(_ANGLE_EMAIL.findall(line))
    return emails


def probe_raw_emails(repo: str | Path) -> list[str]:
    """One `git log` spawn over all history reachable from HEAD; raw author + trailer emails.

    No `--use-mailmap`: it leaves trailer text untouched, so `canonicalize` is the sole mailmap
    owner. Offline; an empty list on a non-repo, unborn HEAD, or missing git.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "log", "HEAD", f"--format={_GIT_LOG_FORMAT}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    return parse_git_log(proc.stdout)


def count_collaborators(repo: str | Path, bot_excludes: Iterable[str] = ()) -> int:
    """Distinct canonical human identities across HEAD's history, mailmap read from the repo."""
    mailmap = parse_mailmap(Path(repo) / ".mailmap")
    return len(canonicalize(probe_raw_emails(repo), mailmap=mailmap, bot_excludes=bot_excludes))


def _is_bot(email: str, excludes: frozenset[str]) -> bool:
    return email.endswith(BOT_SUFFIX) or email.endswith(NOREPLY_SUFFIX) or email in excludes


def canonicalize(
    raw: Iterable[str], *, mailmap: Mapping[str, str], bot_excludes: Iterable[str]
) -> set[str]:
    """Return the distinct canonical human identities among `raw` emails.

    Lowercases, applies `mailmap` (alias -> canonical, single hop), then drops bots. Bot
    status is judged on both the raw spelling and the mapped identity. Pure: no disk, no spawn.
    """
    excludes = frozenset(e.strip().lower() for e in bot_excludes)
    table = {k.strip().lower(): v.strip().lower() for k, v in mailmap.items()}
    out: set[str] = set()
    for item in raw:
        email = item.strip().lower()
        if not email:
            continue
        mapped = table.get(email, email)
        if _is_bot(email, excludes) or _is_bot(mapped, excludes):
            continue
        out.add(mapped)
    return out


class CorruptVerdictError(RuntimeError):
    """The cached verdict exists but is unreadable; distinct from an absent cache."""



def require_readable(previous):
    """Return `previous` unchanged, or raise `CorruptVerdictError` when its source is `corrupt`.

    `refresh` calls this before merging so a corrupt cache fails loudly instead of re-deriving
    as a fresh clone.
    """
    if previous.source == "corrupt":
        raise CorruptVerdictError(
            "state/collaboration-verdict.json exists but fails to parse; "
            "repair or delete it deliberately before refreshing"
        )
    return previous


def merge_verdict(previous, observed, collaboration_mode: str = "auto"):
    """Latch `observed` onto `previous`; both are `collab_gate.Verdict`-shaped.

    `multi` is absorbing: a `multi` previous survives a `solo` observation. Only an explicit
    `collaboration_mode` of `solo` lowers it, and `multi` raises it, each stamped
    `source="override"`. Any other mode value is `auto`. An `unresolved` or `corrupt` previous
    is `solo` and so never lowers an observed `multi`. Pure: no disk, no spawn.
    """
    if collaboration_mode in ("solo", "multi"):
        return type(observed)(
            mode=collaboration_mode,
            source="override",
            author_count=observed.author_count,
            checked_at=observed.checked_at,
        )
    if observed.mode == "solo" and previous.mode == "multi" and previous.source in (
        "detected",
        "override",
    ):
        return previous
    return observed
