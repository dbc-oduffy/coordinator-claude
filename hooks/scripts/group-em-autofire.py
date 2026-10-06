"""UserPromptExpansion auto-fire hook for Group EM entry (naked Python, no bash).

Purpose: when a session types `/group-em`, this hook fires ahead of
`UserPromptSubmit`, runs the entry op (`coordinator/bin/group-em-enter.py`),
and injects the assembled result as `additionalContext` — so the Group EM is
already claimed and the roster and digest already built by the time the
session's own turn begins. Without it, `SKILL.md` can only *tell* the reading
session to run a command, which is the discharge-test failure the entry op was
built to close: a skill body is a document, and a mode nobody fires is a mode
assembled from memory.

This hook follows `pickup-autofire.py` / `mise-autofire.py` — same bare-verb
normalization, same fail-open discipline, same envelope. It runs the entry CLI by
path, in-process through `_engine_forward`, never as a child process.

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

import io
import json
import os
import sys
from pathlib import Path

_GROUP_EM_COMMAND_NAMES = {"group-em"}
_CONTEXT_BUDGET_CHARS = 10_000

_PM_CALL_DEFAULT = "resolving this is the PM's call"


def _normalize_command_name(name: str | None) -> str:
    """Normalize a raw `command_name` to its bare verb. Identical shape to
    `pickup-autofire.py::_normalize_command_name` -- strips any `<namespace>:` prefix by taking
    the segment after the LAST `:`, so both `"coordinator:group-em"` and a bare typed verb
    normalize to the same string. Also strips a leading `/` -- a literally-typed slash-command
    value is otherwise a distinct string from the same bare verb and would silently miss the
    membership test below."""
    if not isinstance(name, str):
        return ""
    return name.lstrip("/").rsplit(":", 1)[-1]


# _resolve_watch_module/render_watch_line live in the shared _watch_module.py beside the other
# _-prefixed modules in this directory; see that module's docstring for why the per-hook-
# independence posture does not cover this case.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _watch_module  # noqa: E402

render_watch_line = _watch_module.render_watch_line


def resolve_enter_cli() -> Path | None:
    """Locate `group-em-enter.py` from this hook's own position in the plugin tree. Resolved
    from `__file__`, never cwd: the hook fires from whatever directory the invoking session
    happens to be in, and `--plugin-dir` can root this tree anywhere."""
    candidate = Path(__file__).resolve().parents[2] / "bin" / "group-em-enter.py"
    return candidate if candidate.is_file() else None


def _load_box_notice():
    """`bin/group-em-box-notice.py`, loaded by path from this hook's own tree; None when absent."""
    path = Path(__file__).resolve().parents[2] / "bin" / "group-em-box-notice.py"
    if not path.is_file():
        return None
    import importlib.util

    spec = importlib.util.spec_from_file_location("_gem_autofire_box_notice", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fleet_repo_roots() -> list[str]:
    """Fleet repos from the machine-local registry (`repos.*`), never from live sessions: a repo
    with no EM still has an inbox. De-duplicated by normalised path (the registry carries aliases
    for one checkout) and kept only when it is a git repo carrying `state/cross-repo/inbox`."""
    import tomllib

    import _engine_root

    reg_dir = _engine_root._settings_home_registry_dir()
    paths: dict[str, str] = {}
    for name in ("registry.toml", "registry.local.toml"):  # local overrides the tracked baseline
        try:
            with (reg_dir / name).open("rb") as fh:
                data = tomllib.load(fh)
        except (OSError, tomllib.TOMLDecodeError):
            continue
        for key, value in _engine_root._flatten_registry(data).items():
            if key.startswith("repos.") and isinstance(value, str) and value:
                paths[key] = value
    roots: dict[str, str] = {}
    for value in paths.values():
        root = Path(value)
        if (root / ".git").exists() and (root / "state" / "cross-repo" / "inbox").is_dir():
            roots.setdefault(os.path.normcase(os.path.normpath(value)), str(root).replace("\\", "/"))
    return sorted(roots.values())


def render_fleet_workflow(plugin_root: Path, repos: list[str], holder: dict) -> str:
    """The exact `Workflow` invocation that grinds every fleet inbox to zero."""
    script = (plugin_root / "workflows" / "fleet-inbox-blitz.mjs").as_posix()
    args = {"repos": repos, "gem": {"sessionId": holder.get("sessionId"), "name": holder.get("name")}}
    return (
        "FLEET INBOX GRIND, FIRE NOW: cross-repo memos are enabled on this box, and entering the "
        "Group EM role is the request. Fire this saved workflow as your first act, unattended; "
        "do not hand-author a variant (`A-GROUP-EM-HAND-AUTHORING-THE-INBOX-WORKFLOW`). "
        "Commit authority in every listed repo is inherent to the role.\n"
        f"  Workflow({{scriptPath: {json.dumps(script)}, args: {json.dumps(args)}}})"
    )


def _box_blocks(repo_root: str, session_id: str, payload: dict) -> list[str]:
    """The box-wide additions to the entry context: the owed notice sends, and the fleet inbox
    workflow invocation when cross-repo memos are enabled. Fail-open per block."""
    blocks: list[str] = []
    notice_mod = None
    try:
        notice_mod = _load_box_notice()
        if notice_mod is not None:
            away = frozenset(
                p.get("session_id")
                for p in (payload.get("roster") or [])
                if str(p.get("state") or "").startswith("PAUSED:away")
            )
            notice = notice_mod.build_notice(
                "entered", repo_root, session_id, skip_session_ids=away
            )
            blocks.append(notice_mod.render_sends_block(notice))
            holder = notice["holder"]
        else:
            holder = {"sessionId": session_id, "name": None}
    except Exception:  # noqa: BLE001
        holder = {"sessionId": session_id, "name": None}
    try:
        import _machine_profile

        if _machine_profile.feature_enabled("cross_repo_memos"):
            repos = fleet_repo_roots()
            if repos:
                blocks.append(
                    render_fleet_workflow(Path(__file__).resolve().parents[2], repos, holder)
                )
    except Exception:  # noqa: BLE001
        pass
    return blocks


class _EnterResult:
    def __init__(self, returncode: int, stdout: str, stderr: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _run_enter(script: Path, repo_root: str, session_id: str):
    """Run the entry CLI in-process through the engine forwarder with stdout/stderr captured.
    Rewrites `sys.path`, `sys.argv` and both std streams for the duration; all four are
    restored in `finally`. Returns None when the forward raises."""
    argv = [str(script), "--repo", repo_root, "--session-id", session_id, "--json"]
    saved_path = list(sys.path)
    saved_argv = list(sys.argv)
    saved_out, saved_err = sys.stdout, sys.stderr
    out, err = io.StringIO(), io.StringIO()
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "bin" / "lib"))
        from _engine_forward import forward

        sys.argv = argv
        sys.stdout, sys.stderr = out, err
        code = forward(str(script))
        return _EnterResult(code, out.getvalue(), err.getvalue())
    except Exception:  # noqa: BLE001
        return None
    finally:
        sys.stdout, sys.stderr = saved_out, saved_err
        sys.argv = saved_argv
        sys.path[:] = saved_path


def render_additional_context(
    payload: dict, exit_code: int, stderr: str, box_blocks: list[str] | None = None
) -> str:
    """Render the injected turn context. A refusal renders as loudly as a success -- see the
    module docstring's refusal clause. Truncated from the tail to stay inside the budget; the
    standing verdict and the gate reminder are never dropped, because a session that loses the
    Group EM line believes it holds one, and a session that loses the gate line is the one the
    send gate exists to stop."""
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
    # (candidate | unclassifiable | contradicted), a numerator whose denominator the engine
    # reports separately as `roster_considered` (see `coordinator_core/ops/group_em_enter.py`'s
    # module docstring, which says so in capitals). Rendering `len(roster)` as "peer(s)" told
    # the holder a busy repo was nearly empty, and `0 of 11` and `0 of 0` -- looked-and-found-
    # nothing versus never-enumerated -- collapsed into the same line. Both were chased as
    # separate bugs across three repos on 2026-09-02 before the render was found.
    considered = payload.get("roster_considered")
    if isinstance(considered, int) and not isinstance(considered, bool):
        roster_line = (
            f"Roster: {len(roster)} of {considered} peer(s) considered, "
            f"{candidates} candidate(s)"
        )
    else:
        # Never fabricate the denominator, and never print a bare count in its place -- that is
        # the exact ambiguity this branch exists to avoid. Say the denominator is missing.
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
        # The one message this mode owes rather than offers. A displaced holder that is still
        # running believes it is this repo's Group EM and will act on that; the ordinary send
        # gates ask whether an interrupt is worth its cost to the receiver, and a peer acting
        # under a role it no longer holds is the case where the answer is not in doubt.
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
        # fold refuses to skip malformed lines quietly. Surfacing the count at
        # entry is what turns the quarantine file into something someone reads.
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
    # No hook can arm the watch itself -- a Monitor is a model tool. A Monitor dies at the harness's
    # 30-minute cap, so the arming ask carries the re-arm duty. Whether arming happened is reported
    # by the watch verdict, never acted on here.
    arm_line = (
        "ARM THE WATCH, NOW, AS YOUR FIRST ACT: run the watch trampoline under a `Monitor` from "
        "this conversation, and re-arm it on each expiry notice -- a `Monitor` dies at the "
        "harness's 30-minute cap, so it does not run for the session. Wakes are events (watch "
        "lines, peer SendMessages, notify_when_idle); arm no cron tick."
    )
    # Box blocks are owed sends and a workflow fire: obligations, so they ride the tail.
    tail = "\n\n".join([*(box_blocks or []), arm_line, gate_line])
    head = "\n".join(lines)
    text = head + "\n\n" + tail
    if len(text) > _CONTEXT_BUDGET_CHARS:
        # Truncation drops roster rows, never the tail: a session that loses the gate line is
        # the one the send gate exists to stop, and a session that loses the arm line stops
        # watching without noticing. Both are obligations, not listings.
        keep = max(0, _CONTEXT_BUDGET_CHARS - len(tail) - 24)
        text = head[:keep] + "\n... (truncated)\n\n" + tail
    return text


def compute_context(stdin_text: str) -> str | None:
    """The `additionalContext` text for a UserPromptExpansion payload; None for a silent pass."""
    try:
        payload = json.loads(stdin_text) if stdin_text else {}
        if not isinstance(payload, dict):
            payload = {}
    except Exception:  # noqa: BLE001
        payload = {}

    if _normalize_command_name(payload.get("command_name")) not in _GROUP_EM_COMMAND_NAMES:
        return None  # not a group-em invocation -- silent pass

    cwd = payload.get("cwd")
    repo_root = cwd if isinstance(cwd, str) and cwd else os.getcwd()
    # Read independently of everything below, so an unreachable engine cannot silence it.
    # Computed only once the command is confirmed as a group-em invocation, so an unrelated
    # command still stays silent.
    watch_line = render_watch_line(repo_root)

    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return watch_line or None  # no id to claim under; still report the watch verdict

    script = resolve_enter_cli()
    if script is None:
        return watch_line or None  # transport failure -- CLI unresolvable, fail open

    result = _run_enter(script, repo_root, session_id)
    if result is None:
        return watch_line or None  # forward raised -- fail open

    try:
        entered = json.loads(result.stdout) if result.stdout.strip() else {}
        if not isinstance(entered, dict):
            entered = {}
    except Exception:  # noqa: BLE001
        entered = {}

    if not entered and result.returncode not in (6, 7):
        return watch_line or None  # nothing else to report -- still fail open on the watch line

    boxes: list[str] = []
    if result.returncode == 0 and (entered.get("standing") or {}).get("claimed"):
        boxes = _box_blocks(repo_root, session_id, entered)
    context = render_additional_context(entered, result.returncode, result.stderr or "", boxes)
    if watch_line and context:
        context = f"{watch_line}\n\n{context}"
    elif watch_line and not context:
        context = watch_line
    return context or None


def main() -> int:
    try:
        raw = sys.stdin.read()
    except Exception:  # noqa: BLE001
        return 0  # fail-open -- stdin unreadable
    context = compute_context(raw)
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


if __name__ == "__main__":
    sys.exit(main())
