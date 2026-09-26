"""UserPromptExpansion auto-fire hook for Group EM entry (naked Python, no bash).

Purpose: when a session types `/group-em`, this hook fires ahead of
`UserPromptSubmit`, runs the entry op (`coordinator/bin/group-em-enter.py`),
and injects the assembled result as `additionalContext` — so the Group EM is
already claimed and the roster and digest already built by the time the
session's own turn begins. Without it, `SKILL.md` can only *tell* the reading
session to run a command, which is the discharge-test failure the entry op was
built to close: a skill body is a document, and a mode nobody fires is a mode
assembled from memory.

This is the fourth `UserPromptExpansion` auto-fire in this directory and
follows `pickup-autofire.py` / `mise-autofire.py` exactly — same bare-verb
normalization, same fail-open discipline, same envelope. It is not new
infrastructure.

Contract (mirrors the sibling hooks in this directory):
  stdin   -- UserPromptExpansion JSON (command_name, command_args, cwd,
             session_id, prompt_id, ...)
  stdout  -- one `hookSpecificOutput` JSON envelope with `additionalContext`
             when a `group-em` verb was matched and entry produced a result;
             NOTHING otherwise (silent pass)
  exit 0  -- always. Never a blocking gate on the session's own prompt.

THE ENTRY OP MUTATES, AND THAT IS THE POINT. Unlike a brief-computing hook,
this one claims the Group EM nomination as a side effect. That is exactly what
`/group-em` invocation means — the skill is PM-gated at the point a human types
it, so firing on the typed verb inherits that gate rather than inventing one.
It fires on nothing else: no `Stop` trigger, no timer, no other command. Wiring
it to anything but the typed verb would re-derive the stood-down watcher that
`SKILL.md` § Anti-scope forbids.

SESSION ID IS PROPAGATED, NEVER AMBIENT. The payload carries the originating
`session_id`; it is passed explicitly via `--session-id`. The entry op would
otherwise read `CLAUDE_SESSION_ID` from this hook process's environment, which
is not reliably the invoking session's under concurrency — and a Group EM claimed
under the wrong id is worse than no claim, because it looks correct.

A REFUSAL IS REPORTED, NEVER SWALLOWED. Exit 5 (a live incumbent), exit 6 (an
engine that returned a digest under a refused standing) and exit 7 (unreachable
engine, no silent fallback) each produce their own `additionalContext` naming
what happened. A hook that fired, was refused, and said nothing would leave the
session believing it holds a Group EM it does not.

NEGATIVE SPEC — what this hook deliberately does NOT do:

- **Never passes `--supersede`.** Taking the role from a live peer is
  direction-class and belongs to a human. The hook reports the refusal and the
  incumbent; it never resolves it.
- **Never passes `--local`.** The engine path is the default and an
  unreachable engine refuses. A hook silently selecting the divergent
  in-tree ladder is precisely the fallback the CLI exists to refuse.
- **Never sends to a peer.** It assembles. `gate1`/`gate2` stay unresolved and
  the injected text says so; every send remains an explicit per-send act.
- **Never blocks.** Any failure — unreadable stdin, unresolvable CLI, timeout,
  malformed output — degrades to silence and exit 0.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_GROUP_EM_COMMAND_NAMES = {"group-em"}
_ENTER_TIMEOUT_SECONDS = 30
_CONTEXT_BUDGET_CHARS = 10_000

# Windows console-subprocess discipline: `python.exe` is a CONSOLE-subsystem
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_PM_CALL_DEFAULT = "resolving this is the PM's call"


def _normalize_command_name(name: str | None) -> str:
    if not isinstance(name, str):
        return ""
    return name.lstrip("/").rsplit(":", 1)[-1]


sys.path.insert(0, str(Path(__file__).resolve().parent))
import _watch_module  # noqa: E402

render_watch_line = _watch_module.render_watch_line


def resolve_enter_cli() -> Path | None:
    candidate = Path(__file__).resolve().parents[2] / "bin" / "group-em-enter.py"
    return candidate if candidate.is_file() else None


def _run_enter(script: Path, repo_root: str, session_id: str):
    argv = [
        sys.executable,
        str(script),
        "--repo",
        repo_root,
        "--session-id",
        session_id,
        "--json",
    ]
    try:
        return subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=_ENTER_TIMEOUT_SECONDS,
            creationflags=_NO_WINDOW,
        )
    except Exception:  # noqa: BLE001
        return None


def render_additional_context(payload: dict, exit_code: int, stderr: str) -> str:
    if exit_code in (6, 7):
        detail = (stderr or "").strip().splitlines()
        reason = detail[-1] if detail else "no detail reported"
        head = "engine refused" if exit_code == 7 else "stale engine payload refused"
        return (
            f"## Group EM entry: NOT ENTERED ({head})\n\n"
            f"{reason}\n\n"
            "The Group EM was NOT claimed and no roster or digest exists. Do not act as this "
            "repo's Group EM until entry succeeds."
        )

    standing = (payload or {}).get("standing") or {}
    if not standing.get("claimed"):
        message = standing.get("message") or "nomination refused"
        pm_call = standing.get("needs_pm_decision") or _PM_CALL_DEFAULT
        return (
            "## Group EM entry: REFUSED\n\n"
            f"{message}\n\n"
            f"{pm_call}\n\n"
            "No roster or digest was built. Entry is last-writer-wins and vacates any incumbent "
            "before re-entering, so a refusal that reaches here is NOT a standing-ownership "
            "problem -- do not reach for an override. Something else refused."
        )

    roster = payload.get("roster") or []
    digest = payload.get("digest") or {}
    entries = digest.get("entries") or []
    suppressed = digest.get("suppressed") or []
    candidates = sum(1 for peer in roster if peer.get("candidate"))

    # `roster` IS NOT THE PEER POPULATION -- it is `build_candidate_roster`'s output
    considered = payload.get("roster_considered")
    if isinstance(considered, int) and not isinstance(considered, bool):
        roster_line = (
            f"Roster: {len(roster)} of {considered} peer(s) considered, "
            f"{candidates} candidate(s)"
        )
    else:
        roster_line = (
            f"Roster: {len(roster)} shortlisted, {candidates} candidate(s) — "
            f"ENUMERATED COUNT UNAVAILABLE (`roster_considered` absent from the payload), so "
            f"this says nothing about how many peers exist"
        )

    lines = [
        "## Group EM entry: ACTIVE",
        "",
        f"Group EM: {standing.get('message') or 'claimed'}",
        roster_line,
    ]
    if standing.get("displaced_holder"):
        lines.append(
            f"DISPLACED: {standing['displaced_holder']} — "
            + (
                "still running and does not know yet. Tell it, this turn: it holds no standing and "
                "must not act as Group EM. This send is owed, not offered."
                if standing.get("displaced_holder_live")
                else "not running; nobody to tell."
            )
        )
    for peer in roster[:10]:
        mark = "*" if peer.get("candidate") else " "
        lines.append(
            f"  {mark} {peer.get('session_id')}  {peer.get('state')} ({peer.get('reason')})"
        )
    if len(roster) > 10:
        lines.append(f"  ... and {len(roster) - 10} more")

    lines.append(f"Digest: {len(entries)} offerable, {len(suppressed)} suppressed")
    for entry in entries[:10]:
        lines.append(f"  - {entry.get('session_id')}  {entry.get('trigger')}")

    unrecorded = digest.get("unrecorded") or []
    if unrecorded:
        lines.append(
            f"  ! cooldown UNARMED for {len(unrecorded)} peer(s) -- their throttle did not write"
        )

    intake = payload.get("intake") or {}
    if intake.get("rejected"):
        # A rejected intake row is a PRODUCER defect, and the whole reason the
        lines.append(
            f"  ! obligations-inbound: {intake['rejected']} malformed row(s) quarantined to "
            ".coordinator-local/subagent-share/<sid>/obligations-inbound.rejected.jsonl -- producer bug"
        )
    if intake.get("deferred"):
        lines.append(
            f"  ! obligations-inbound: {intake['deferred']} session(s) deferred; their rows fold "
            "on the next tick"
        )

    baseline = payload.get("baseline") or {}
    if baseline and not baseline.get("first_tick"):
        lines.append(
            f"Baseline: +{len(baseline.get('spawned') or [])} spawned, "
            f"-{len(baseline.get('exited') or [])} exited, "
            f"~{len(baseline.get('changed') or [])} changed"
        )

    gate_line = (
        "GATES UNRESOLVED. `gate1`/`gate2` are unset and nothing here resolves them. "
        "Declare both in prose per send, and never loop over `entries` sending."
    )
    arm_line = (
        "ARM BOTH CLOCKS, NOW, AS YOUR FIRST ACT: `CronCreate` a ~23-minute recurring "
        "re-entry (off the :00/:30 marks) AND hold a `Monitor` poller over the session "
        "registry. Both are session-scoped; no hook arms them for you."
    )
    lines += ["", arm_line, "", gate_line]

    text = "\n".join(lines)
    if len(text) > _CONTEXT_BUDGET_CHARS:
        tail = f"{arm_line}\n\n{gate_line}"
        keep = max(0, _CONTEXT_BUDGET_CHARS - len(tail) - 24)
        text = text[:keep] + "\n... (truncated)\n\n" + tail
    return text


def main() -> int:
    try:
        raw = sys.stdin.read()
    except Exception:  # noqa: BLE001
        return 0

    try:
        payload = json.loads(raw) if raw else {}
        if not isinstance(payload, dict):
            payload = {}
    except Exception:  # noqa: BLE001
        payload = {}

    if _normalize_command_name(payload.get("command_name")) not in _GROUP_EM_COMMAND_NAMES:
        return 0

    cwd = payload.get("cwd")
    repo_root = cwd if isinstance(cwd, str) and cwd else os.getcwd()
    watch_line = render_watch_line(repo_root)

    def _emit(context: str | None) -> int:
        if not context:
            return 0
        try:
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "UserPromptExpansion",
                            "additionalContext": context,
                        }
                    }
                )
            )
        except OSError:
            pass
        return 0

    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return _emit(watch_line)

    script = resolve_enter_cli()
    if script is None:
        return _emit(watch_line)

    result = _run_enter(script, repo_root, session_id)
    if result is None:
        return _emit(watch_line)

    try:
        entered = json.loads(result.stdout) if result.stdout.strip() else {}
        if not isinstance(entered, dict):
            entered = {}
    except Exception:  # noqa: BLE001
        entered = {}

    if not entered and result.returncode not in (6, 7):
        return _emit(watch_line)

    context = render_additional_context(entered, result.returncode, result.stderr or "")
    if watch_line and context:
        context = f"{watch_line}\n\n{context}"
    elif watch_line and not context:
        context = watch_line
    return _emit(context)


if __name__ == "__main__":
    sys.exit(main())
