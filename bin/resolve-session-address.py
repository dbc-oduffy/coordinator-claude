from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

_BOOTSTRAP_DONE = False


def _bootstrap_engine() -> None:
    """Put `_REPO_ROOT` on `sys.path` so `main`'s deferred
    `coordinator_core.session.reachability` import resolves. Idempotent.

    What moved, and what did NOT: this single-line mutation used to run at
    MODULE scope, which made every import of this file mutate the `sys.path`
    of a warm server ~50 sessions share. The line is preserved exactly; only
    the trigger moved. No name is bound as a global here, so there is
    nothing to publish and no `__getattr__` hook is needed.
    """
    global _BOOTSTRAP_DONE
    if _BOOTSTRAP_DONE:
        return
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    _BOOTSTRAP_DONE = True

# fails-open shape DR084-SINGLE-ACCESSOR exists to catch is a MIXED corpus: a
_CLAIM_KEYS = ("claimed_by", "held_by", "authoring_session", "origin_session")


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


_SID_SHAPE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


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

    _bootstrap_engine()
    from coordinator_core.session import reachability

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
        if not _SID_SHAPE.match(sid):
            print(
                f"resolve-session-address: {sid} is not a session id — this "
                f"resolves an id to a name, not a name to an address. Read the "
                f"id off the artifact's claimed_by, or pass the artifact path.",
                file=sys.stderr,
            )
            return 2

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
            print(
                f"{sid}{origin}\n  -> not reachable from here "
                f"(no live harness-registry record, or a different working tree)",
                file=sys.stderr,
            )
    return 0 if address else 1


if __name__ == "__main__":
    raise SystemExit(main())
