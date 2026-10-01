"""Fleet posture grant verifier: the bounded half of the P2 authority leg.

Spec backlink: docs/plans/2026-09-11-fleet-control-plane-posture-authority-attention.md (C5);
ruling R2 in docs/research/2026-09-11-fleet-control-plane-design.md.

`verify_grant(path)` returns a `GrantVerdict`. Evaluation order:
  1. tombstone beside the grant (`<grant>.revoked`)  -> `revoked`
  2. `expires_at` (absolute, tz-aware ISO-8601) not after the local clock -> `expired`
  3. the custody seam -> `unverifiable` (no custody answer exists in this repo)

INVARIANT: `granted` is unreachable. No P2 construction scored YES on peer-free
verification (spike verdict), so the custody seam fails closed. `revoked` and `expired`
only remove authority, so they are safe to reach without custody. `tampered` is reserved:
no selected construction can detect tamper, so a tampered file reads `unverifiable`.

Inputs are the grant file, its tombstone, and the local clock. A value a peer session
reported is never an input. Paths use pathlib; replacement uses os.replace; no mode bits.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

GRANTED = "granted"
EXPIRED = "expired"
REVOKED = "revoked"
TAMPERED = "tampered"
UNVERIFIABLE = "unverifiable"

TOMBSTONE_SUFFIX = ".revoked"


@dataclass(frozen=True)
class GrantVerdict:
    verdict: str
    scope: object = None
    reason: str = ""


def tombstone_path(grant_path: Path | str) -> Path:
    p = Path(grant_path)
    return p.with_name(p.name + TOMBSTONE_SUFFIX)


def revoke_grant(grant_path: Path | str) -> Path:
    """Write the tombstone atomically; revocation removes authority only."""
    tomb = tombstone_path(grant_path)
    tmp = tomb.with_name(tomb.name + ".tmp-%d" % os.getpid())
    tmp.write_text(
        json.dumps({"revoked_at": datetime.now(timezone.utc).isoformat()}),
        encoding="utf-8",
    )
    os.replace(tmp, tomb)
    return tomb


def custody_seam(grant: dict, grant_path: Path) -> GrantVerdict:
    """Construction-agnostic custody check. Fails closed: no custody answer exists here.

    A key-custody implementation (engine-resident verify-side pin) replaces this body;
    until then every input is unverifiable.
    """
    return GrantVerdict(UNVERIFIABLE, reason="no custody answer available")


def _parse_expiry(raw: object) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else None


def verify_grant(grant_path: Path | str, now: datetime | None = None) -> GrantVerdict:
    """Return the verdict for the grant file; never raises, never returns `granted`."""
    try:
        path = Path(grant_path)
        if tombstone_path(path).exists():
            return GrantVerdict(REVOKED, reason="tombstone present")
        try:
            grant = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return GrantVerdict(UNVERIFIABLE, reason="grant unreadable: %s" % type(exc).__name__)
        if not isinstance(grant, dict):
            return GrantVerdict(UNVERIFIABLE, reason="grant is not a mapping")
        expiry = _parse_expiry(grant.get("expires_at"))
        if expiry is None:
            return GrantVerdict(UNVERIFIABLE, reason="expires_at absent or malformed")
        clock = now if now is not None else datetime.now(timezone.utc)
        if expiry <= clock:
            return GrantVerdict(EXPIRED, reason="expires_at passed")
        verdict = custody_seam(grant, path)
        if verdict.verdict == GRANTED:
            return GrantVerdict(UNVERIFIABLE, reason="custody seam may not grant")
        return verdict
    except Exception as exc:  # fail closed
        return GrantVerdict(UNVERIFIABLE, reason="verifier error: %s" % type(exc).__name__)
