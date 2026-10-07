"""Fleet-scoped posture artifact: sanctioned writer plus per-session reader.

Spec backlink: docs/plans/2026-09-11-fleet-control-plane-posture-authority-attention.md (C4);
rulings R1, R3, R4, R8 in docs/research/2026-09-11-fleet-control-plane-design.md.

The artifact is one host-local JSON file at `fleet-posture.json` in `coordinator_temp_root("_fleet")`
(grants beside it as `fleet-grant-<id>.json`; reads fall back to the bare-Temp legacy location;
never a literal `/tmp`: a Windows-native Python misses every file the bash side sees).
Fields: schema, posture, scope (repo-root basenames or `all-on-host`), expires_at,
grant_id, optional channel_holder.

INVARIANT (R3): `resolve_posture` reads posture only through `_fleet_grant.verify_grant`.
No code path treats raw artifact presence as posture; absent, malformed, expired,
out-of-scope, or unverified all resolve to not-applying. Today the verifier never returns
`granted`, so nothing applies in production.

`human_channel` returns data (`holder` / `non-holder` / `unknown`); `unknown` routes as
`non-holder`. The caller acts on the route; this module never opens a modal.

Writes use os.replace and no POSIX mode bits. `fleet-posture.py` is not protected from agent
invocation (R4): the grant verifier is the sole trust anchor.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _fleet_grant  # noqa: E402
from _coordinator_temp import coordinator_temp_root  # noqa: E402

SCHEMA_VERSION = 1
POSTURES = frozenset({"autonomous", "mise-en-place"})
ALL_ON_HOST = "all-on-host"
ARTIFACT_NAME = "fleet-posture.json"

HOLDER = "holder"
NON_HOLDER = "non-holder"
UNKNOWN = "unknown"

ROUTE_TEXT_TURN_ASK = "text-turn-ask"
ROUTE_DECIDE_AND_REPORT = "decide-and-report"

_GRANT_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


@dataclass(frozen=True)
class PostureResolution:
    applies: bool
    posture: str | None = None
    reason: str = ""
    grant_verdict: str = ""


FLEET_SLUG = "_fleet"
SENTINEL_PREFIX = "autonomous-run-"


def fleet_dir() -> Path:
    """Host-scoped sentinel directory `<gettempdir()>/coordinator/_fleet` (created)."""
    return coordinator_temp_root(FLEET_SLUG)


def legacy_dir() -> Path:
    """Bare-Temp location read during the dual-read window; only a legacy grant's tombstone is written here."""
    return Path(tempfile.gettempdir())


def artifact_path() -> Path:
    return fleet_dir() / ARTIFACT_NAME


def _check_grant_id(grant_id: str) -> None:
    if not isinstance(grant_id, str) or not _GRANT_ID_RE.match(grant_id) or grant_id.startswith("."):
        raise ValueError("grant_id must match [A-Za-z0-9._-]{1,128} and not start with '.'")


def grant_path(grant_id: str) -> Path:
    """Grant file the verifier confirms for `grant_id`; raises ValueError on an unsafe id.

    Returns the new location unless only a legacy bare-Temp grant exists.
    """
    _check_grant_id(grant_id)
    name = "fleet-grant-%s.json" % grant_id
    new = fleet_dir() / name
    legacy = legacy_dir() / name
    if not new.exists() and legacy.exists():
        return legacy
    return new


def sentinel_candidates(session_id: str) -> list[Path]:
    """Autonomous sentinel locations for a session: new first, then bare Temp."""
    name = SENTINEL_PREFIX + session_id
    return [fleet_dir() / name, legacy_dir() / name]


def _atomic_write_json(path: Path, payload: dict) -> None:
    tmp = path.with_name(path.name + ".tmp-%d" % os.getpid())
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def write_posture(
    posture: str,
    scope: list[str] | str,
    expires_at: datetime,
    grant_id: str,
    channel_holder: str | None = None,
) -> Path:
    """Write the artifact atomically; raises ValueError on a malformed contract."""
    if posture not in POSTURES:
        raise ValueError("posture must be one of %s" % sorted(POSTURES))
    if scope != ALL_ON_HOST:
        if not isinstance(scope, list) or not scope or not all(isinstance(s, str) and s for s in scope):
            raise ValueError("scope must be %r or a non-empty list of repo-root basenames" % ALL_ON_HOST)
    if expires_at.tzinfo is None:
        raise ValueError("expires_at must be timezone-aware")
    grant_path(grant_id)
    payload: dict = {
        "schema": SCHEMA_VERSION,
        "posture": posture,
        "scope": scope,
        "expires_at": expires_at.astimezone(timezone.utc).isoformat(),
        "grant_id": grant_id,
    }
    if channel_holder:
        payload["channel_holder"] = channel_holder
    path = artifact_path()
    _atomic_write_json(path, payload)
    return path


def clear_posture() -> bool:
    """Remove the artifact; True when one was removed."""
    removed = False
    for path in (artifact_path(), legacy_dir() / ARTIFACT_NAME):
        try:
            path.unlink()
            removed = True
        except FileNotFoundError:
            pass
    return removed


def revoke_posture_grant() -> Path | None:
    """Write the tombstone for the artifact's grant; None when no readable artifact names one."""
    art = _read_artifact()
    if art is None:
        return None
    try:
        return _fleet_grant.revoke_grant(grant_path(art["grant_id"]))
    except (KeyError, ValueError):
        return None


def _read_artifact() -> dict | None:
    path = artifact_path()
    if not path.exists():
        path = legacy_dir() / ARTIFACT_NAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _session_repo_basename(cwd: str | os.PathLike | None) -> str | None:
    start = Path(cwd) if cwd else Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    try:
        start = start.resolve()
    except OSError:
        return None
    for cand in (start, *start.parents):
        if (cand / ".git").exists():
            return cand.name
    return start.name or None


def _in_scope(scope: object, cwd: str | os.PathLike | None) -> bool:
    if scope == ALL_ON_HOST:
        return True
    if not isinstance(scope, list) or not scope:
        return False
    return _session_repo_basename(cwd) in scope


def resolve_posture(
    session_id: str | None = None,
    cwd: str | os.PathLike | None = None,
    now: datetime | None = None,
) -> PostureResolution:
    """Does a fleet posture apply to this session; never raises, fails to not-applying."""
    try:
        art = _read_artifact()
        if art is None:
            return PostureResolution(False, reason="no readable artifact")
        if art.get("schema") != SCHEMA_VERSION:
            return PostureResolution(False, reason="unknown schema")
        posture = art.get("posture")
        if posture not in POSTURES:
            return PostureResolution(False, reason="malformed posture")
        if "scope" not in art:
            return PostureResolution(False, reason="malformed: scope absent")
        expiry = _fleet_grant._parse_expiry(art.get("expires_at"))
        if expiry is None:
            return PostureResolution(False, reason="malformed: expires_at")
        clock = now if now is not None else datetime.now(timezone.utc)
        if expiry <= clock:
            return PostureResolution(False, reason="expired")
        if not _in_scope(art["scope"], cwd):
            return PostureResolution(False, reason="out of scope")
        verdict = _fleet_grant.verify_grant(grant_path(art.get("grant_id")), now=clock)
        if verdict.verdict != _fleet_grant.GRANTED:
            return PostureResolution(False, reason="grant not granted", grant_verdict=verdict.verdict)
        return PostureResolution(True, posture=posture, reason="granted", grant_verdict=verdict.verdict)
    except Exception as exc:  # fail closed
        return PostureResolution(False, reason="reader error: %s" % type(exc).__name__)


def human_channel(
    session_id: str | None,
    cwd: str | os.PathLike | None = None,
    now: datetime | None = None,
) -> str:
    """`holder`, `non-holder`, or `unknown`; only a verified, applying posture can answer."""
    res = resolve_posture(session_id, cwd, now)
    if not res.applies:
        return UNKNOWN
    art = _read_artifact() or {}
    holder = art.get("channel_holder")
    if session_id and holder and holder == session_id:
        return HOLDER
    return NON_HOLDER


def ask_route(
    session_id: str | None,
    cwd: str | os.PathLike | None = None,
    now: datetime | None = None,
) -> str:
    """Route for a gate that says "ask the PM", returned as data; never a modal.

    `holder` asks via a text turn. `non-holder` and `unknown` decide-and-report.
    """
    if human_channel(session_id, cwd, now) == HOLDER:
        return ROUTE_TEXT_TURN_ASK
    return ROUTE_DECIDE_AND_REPORT
