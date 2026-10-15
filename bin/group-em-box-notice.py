"""group-em-box-notice — compute the box-wide Group EM notice and its exact recipients.

The Group EM standing is box-wide: every live named session on the box, in any repo, is told once
when a holder takes the role and once when it ends. A hook has no transport to a peer session
(`SendMessage` is a model tool), so this module makes the notice mechanical up to the send: it
enumerates the recipients, renders the one message text, and records the introductions. The holder
discharges the sends it prints.

`--kind entered`  recipients, text, and introduction rows in the holder's send log. A peer already
                  introduced by this holder is not listed again (re-entry is a refresh).
`--kind ended`    stands the nomination down (holder-matched) and prints the no-Group-EM notice for
                  every live named session. Run it as the last act before the holder's session ends.

The text asks nothing (no question mark) and states that no reply is wanted — the § Owed
introductions content rules in `skills/group-em/SKILL.md`. The introduction row is a send-log row
type `_cooldown_remaining` never reads: `intro_key` / `introduced_at`, no `offer_key`.

NEGATIVE SPEC: never sends, never passes `--supersede`, writes only the holder's own send log and
(for `ended`) the nomination records through the engine's `nomination.stand_down`.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

_BIN_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _BIN_DIR.parent / "skills" / "group-em"

try:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    require_dispatch_engine_on_path()
except (ImportError, RuntimeError):
    pass  # engine already importable (tests, installed layout); a real miss fails below

from coordinator_core.group_em import nomination  # noqa: E402
from coordinator_core.group_em.box_notice import (  # noqa: E402,F401
    NOTICE_ENDED,
    NOTICE_ENTERED,
    box_recipients,
    render_notice,
)


def _load_by_path(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def fetch_live_agents() -> Optional[list[dict[str, Any]]]:
    """Fresh `claude agents --json`; `None` on any failure (an empty box is `[]`, a failed read is
    not the same fact). Not `read_pass.fetch_live_agents`: that
    module imports the engine's receiver-state reader at load, which a hook or bare CLI cannot
    always resolve, and this notice needs only the enumeration."""
    try:
        out = subprocess.run(
            ["claude", "agents", "--json"], capture_output=True, text=True, check=False, timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout
        data = json.loads(out)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return data if isinstance(data, list) else None


def _same_session(a: Any, b: Any) -> bool:
    return isinstance(a, str) and a == b


def holder_identity(agents: list[dict[str, Any]], session_id: str) -> dict[str, Optional[str]]:
    """The holder's own SendMessage name, read from the live enumeration by session id."""
    for agent in agents:
        if isinstance(agent, dict) and _same_session(agent.get("sessionId"), session_id):
            name = agent.get("name")
            return {"sessionId": session_id, "name": name if isinstance(name, str) and name else None}
    return {"sessionId": session_id, "name": None}


def _introduced(send_pass, repo_root: str, holder_sid: str) -> set[str]:
    return {
        r.get("intro_key")
        for r in send_pass.read_send_log(repo_root, holder_sid)
        if r.get("kind") == "introduction" and isinstance(r.get("intro_key"), str)
    }


def _record_introduction(send_pass, repo_root: str, holder_sid: str, peer_sid: str) -> bool:
    path = send_pass.send_log_path(repo_root, holder_sid)
    row = json.dumps(
        {
            "kind": "introduction",
            "intro_key": send_pass.offer_key(holder_sid, peer_sid),
            "introduced_at": time.time(),
        },
        sort_keys=True,
    )
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(row + "\n")
    except OSError:
        return False
    return True


def build_notice(
    kind: str,
    repo_root: str,
    session_id: str,
    *,
    agents: Optional[list[dict[str, Any]]] = None,
    skip_session_ids: frozenset = frozenset(),
    record: bool = True,
) -> dict[str, Any]:
    """Recipients and text for `kind`. `entered` filters peers already introduced and records the
    ones it returns; `ended` returns everyone and records nothing."""
    send_pass = _load_by_path("_gem_box_send_pass", _SKILL_DIR / "send_pass.py")
    if agents is None:
        agents = fetch_live_agents()
    if agents is None:
        # Unknown, not empty: telling nobody would read as "nobody to tell".
        holder: dict[str, Optional[str]] = {"sessionId": session_id, "name": None}
        return {
            "kind": kind,
            "holder": holder,
            "message": render_notice(kind, holder),
            "recipients": [],
            "unrecorded": [],
            "agents_unknown": True,
        }
    holder = holder_identity(agents, session_id)
    recipients = box_recipients(agents, session_id, skip_session_ids)
    unrecorded: list[str] = []
    if kind == NOTICE_ENTERED:
        done = _introduced(send_pass, repo_root, session_id)
        recipients = [
            r for r in recipients if send_pass.offer_key(session_id, r["sessionId"]) not in done
        ]
        if record:
            for r in recipients:
                if not _record_introduction(send_pass, repo_root, session_id, r["sessionId"]):
                    unrecorded.append(r["sessionId"])
    return {
        "kind": kind,
        "holder": holder,
        "message": render_notice(kind, holder),
        "recipients": recipients,
        "unrecorded": unrecorded,
    }


def render_sends_block(notice: dict[str, Any]) -> str:
    """The exact sends owed, as prose lines for an `additionalContext` or a terminal."""
    if notice.get("agents_unknown"):
        return (
            f"BOX NOTICE UNKNOWN ({notice['kind']}): `claude agents --json` failed, so the live "
            "sessions could not be enumerated and nothing was recorded. Re-run this command."
        )
    recipients = notice["recipients"]
    if not recipients:
        return "BOX NOTICE: no live named session to tell."
    lines = [
        f"BOX NOTICE OWED ({notice['kind']}): SendMessage this text to each of "
        f"{len(recipients)} live session(s), this turn. It is informational, interrupts nothing, "
        "and exempt from § Send pass's gates.",
        f"  text: {notice['message']}",
        "  to: " + ", ".join(f"{r['name']} ({r['sessionId'][:8]})" for r in recipients),
    ]
    if notice.get("unrecorded"):
        lines.append(
            f"  ! introduction row UNWRITTEN for {len(notice['unrecorded'])} peer(s); "
            "a re-entry will list them again"
        )
    return "\n".join(lines)


def stand_down_holder(repo_root: str, session_id: str) -> dict[str, Any]:
    # Exit codes are the stable stand-down contract (5: not the holder).
    result = nomination.stand_down(repo_root, session_id)
    return {"ok": result.ok, "exit_code": result.exit_code, "message": result.message}


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="group-em-box-notice",
        description="Compute the box-wide Group EM notice and its recipients. Never sends.",
    )
    parser.add_argument("--kind", required=True, choices=(NOTICE_ENTERED, NOTICE_ENDED))
    parser.add_argument("--repo", help="repo root of the standing; default cwd")
    parser.add_argument("--session-id", help="the holder; default $CLAUDE_CODE_SESSION_ID")
    parser.add_argument("--no-record", action="store_true", help="entered: do not write intro rows")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    repo_root = args.repo or os.getcwd()
    session_id = args.session_id or os.environ.get("CLAUDE_CODE_SESSION_ID") or os.environ.get("CLAUDE_SESSION_ID")
    if not session_id:
        print("group-em-box-notice: no session id (pass --session-id)", file=sys.stderr)
        return 2

    notice = build_notice(
        args.kind, repo_root, session_id, record=not args.no_record
    )
    code = 0
    if args.kind == NOTICE_ENDED:
        notice["stand_down"] = stand_down_holder(repo_root, session_id)
        # Exit 5 (not the holder): announcing an ending that did not happen is worse than
        # silence, so the recipient list is emptied.
        if notice["stand_down"]["exit_code"] == 5:
            notice["recipients"] = []
            code = 5
    if notice.get("agents_unknown") and code == 0:
        code = 3
    if args.json:
        print(json.dumps(notice, indent=2))
    else:
        print(render_sends_block(notice))
        if "stand_down" in notice:
            print(f"stand-down: {notice['stand_down']['message']}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
