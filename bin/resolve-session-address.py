#!/usr/bin/env python3
"""resolve-session-address.py — turn a session id into something you can message.

Purpose: coordinator artifacts record ownership as a raw session UUID
(`claimed_by` on a handoff, plan, sizing or memo), but every messaging surface
addresses by NAME. Nothing bridged the two for an arbitrary id, so an EM holding
a `claimed_by` had no supported way to reach that holder and would either guess a
name off `ListAgents` or conclude the session was dead. Both failure modes are
real and were observed 2026-08-25: a live holder was twice misread as dead
because `.git/coordinator-sessions/<sid>/meta.json` records the pid at CLAIM
time, which goes stale while the session keeps working.

This is a thin CLI over `coordinator_core.session.reachability
.resolve_advisory_address` — the resolution logic, the duplicate-name ref
widening, and the not-reachable reasons all live there and are NOT duplicated
here. `pickup_assemble` already calls it for the picked-up artifact's own holder;
this exposes the same answer for any id an EM happens to be holding.

Negative-spec:
  - Does NOT decide liveness from `meta.json`'s pid. The harness registry
    (`~/.claude/sessions/<pid>.json`) is the authority; a coordinator-side pid is
    a claim-time snapshot, not a liveness signal.
  - Does NOT message anyone. Resolution only — the caller decides whether to
    write, and an address is not consent to interrupt.
  - Does NOT guess. An unresolvable id prints the reachability layer's own
    reason and exits 1 rather than emitting a plausible-looking name.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from coordinator_core.session import reachability  # noqa: E402

# `claimed_by` is DR-084's new vocabulary, renamed from `consumed_by`. The
# fails-open shape DR084-SINGLE-ACCESSOR exists to catch is a MIXED corpus: a
# new-vocabulary-only scan silently skipping artifacts still carrying the old
# key. Measured 2026-08-26 across every `state/**` and `cross-repo/**` markdown
# frontmatter block: ZERO artifacts carry `consumed_by` as a field (the 211
# textual hits are prose in audits and handoff bodies). The corpus has fully
# cut over, so there is nothing for a dual read to find, and adding the dead key
# here would make the guard green by widening a scan over a vocabulary no
# artifact uses -- satisfying the check rather than the property it stands for.
# Re-open this if a `consumed_by`-writing producer ever lands.
_CLAIM_KEYS = ("claimed_by", "held_by", "authoring_session", "origin_session")  # dr084: corpus fully cut over, measured 2026-08-26 -- no mixed-vocabulary read to make


def _sid_from_artifact(path: Path) -> tuple[str | None, str | None]:
    """Return (session_id, which_key) read from an artifact's frontmatter.

    Deliberately a line scan rather than a YAML parse: this runs against
    half-written and hand-edited artifacts, and a parse error here would deny an
    answer the scan can still give. First key in `_CLAIM_KEYS` order wins.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise SystemExit(f"resolve-session-address: cannot read {path}: {exc}")
    found: dict[str, str] = {}
    for line in text.splitlines()[:200]:
        stripped = line.strip()
        for key in _CLAIM_KEYS:
            if stripped.startswith(f"{key}:"):
                value = stripped.split(":", 1)[1].strip().strip("'\"")
                if value and value not in ("null", "none", "~"):
                    found.setdefault(key, value)
    for key in _CLAIM_KEYS:
        if key in found:
            return found[key], key
    return None, None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="resolve-session-address",
        description="Resolve a session id (or an artifact's claimed_by) to a "
                    "messageable address.",
    )
    parser.add_argument(
        "target",
        help="A session UUID, or a path to an artifact whose frontmatter carries "
             "one (claimed_by / held_by / authoring_session / origin_session).",
    )
    parser.add_argument("--json", action="store_true", help="Emit a JSON object.")
    args = parser.parse_args(argv)

    source_key = None
    candidate = Path(args.target)
    if candidate.exists() and candidate.is_file():
        sid, source_key = _sid_from_artifact(candidate)
        if not sid:
            print(
                f"resolve-session-address: {candidate} carries no session id in "
                f"{'/'.join(_CLAIM_KEYS)} — nothing to resolve",
                file=sys.stderr,
            )
            return 1
    else:
        sid = args.target.strip()

    address = reachability.resolve_advisory_address(sid)

    payload = {
        "session_id": sid,
        "address": address or "",
        "reachable": bool(address),
        "read_from": str(candidate) if source_key else None,
        "read_key": source_key,
    }

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        origin = f" (from {source_key} in {candidate})" if source_key else ""
        if address:
            print(f"{sid}{origin}\n  -> {address}")
        else:
            # The reachability layer returns "" for every not-reachable case and
            # keeps the reason internal; say so plainly rather than inventing one.
            print(
                f"{sid}{origin}\n  -> not reachable from here "
                f"(no live harness-registry record, or a different working tree)",
                file=sys.stderr,
            )
    return 0 if address else 1


if __name__ == "__main__":
    raise SystemExit(main())
