"""Never-fail client for the Klabauter host-hook shim (Codex and agy PreToolUse guard).

guard() runs `python -m coordinator_core.host_hooks.shim --host <host>` in a killable child under one
outer wall, so import, engine dial, the shim's engine-free backstop and telemetry are all bounded. Any
miss (no engine root, launch or import failure, timeout, non-zero exit, empty, partial, invalid or
multi-object stdout, or a Codex object that is neither {} nor the exact nested PreToolUse deny) answers the
host's neutral fallback with state "degraded". A Codex bare {} is state "neutral-unknown": the shim cannot
yet tell a real neutral verdict from a warm miss or caught error. Only a verified deny (or valid agy
answer) is "engine"; "degraded" and "neutral-unknown" never satisfy an enforcement check.
The timeout bounds communicate(), not Popen setup; a timed-out child's kill-and-reap adds up to 2s.

CLI: unimatrix-host-guard.py --host codex|agy [--engine-root PATH]
  stdin: one hook payload. stdout: exactly one JSON line. stderr: `state`. Exit 0 always.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

NEUTRAL = {"agy": {"decision": "ask"}, "codex": {}}
NEUTRAL_UNKNOWN = "neutral-unknown"
DEFAULT_BUDGET_SECS = 0.5
SHIM_MODULE = "coordinator_core.host_hooks.shim"


def _neutral(host):
    return dict(NEUTRAL.get(host, {}))


def _no_console_flags():
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


CODEX_DENY_KEYS = {"hookEventName", "permissionDecision", "permissionDecisionReason"}


def _is_codex_deny(obj):
    """True only for the exact nested PreToolUse deny: {"hookSpecificOutput": {event, "deny", reason}}."""
    if not isinstance(obj, dict) or set(obj) != {"hookSpecificOutput"}:
        return False
    inner = obj["hookSpecificOutput"]
    return (isinstance(inner, dict) and set(inner) == CODEX_DENY_KEYS
            and inner["hookEventName"] == "PreToolUse" and inner["permissionDecision"] == "deny"
            and isinstance(inner["permissionDecisionReason"], str))


def _valid_answer(host, obj):
    if not isinstance(obj, dict):
        return False
    if host == "agy":
        return obj.get("decision") in ("deny", "ask", "allow")
    return obj == {} or _is_codex_deny(obj)


def _parse_single_object(text):
    """The one JSON object in `text`, or None for empty, partial, invalid or multi-value text."""
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def guard(host, stdin_text, engine_root, budget_secs=DEFAULT_BUDGET_SECS):
    """Return (answer, state): "engine" for a Codex nested deny or a valid agy answer; "neutral-unknown" for a
    Codex bare {} (the shim emits it for a real neutral verdict, a warm miss and a caught internal error alike);
    else "degraded" with the host's neutral answer. Only "engine" may count as governance evidence."""
    if host not in NEUTRAL:
        return {}, "degraded"
    degraded = (_neutral(host), "degraded")
    if not engine_root or not Path(engine_root).is_dir():
        return degraded
    if not isinstance(_parse_single_object(stdin_text or ""), dict):
        return degraded
    env = dict(os.environ)
    prior = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(engine_root) + (os.pathsep + prior if prior else "")
    proc = None
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", SHIM_MODULE, "--host", host],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=env, cwd=str(engine_root), creationflags=_no_console_flags(),
        )
        try:
            out, _ = proc.communicate(stdin_text.encode("utf-8"), timeout=budget_secs)
        except subprocess.TimeoutExpired:
            return degraded
        if proc.returncode != 0:
            return degraded
        answer = _parse_single_object(out.decode("utf-8", "replace"))
        if not _valid_answer(host, answer):
            return degraded
        if host == "codex" and answer == {}:
            return answer, NEUTRAL_UNKNOWN
        # Trap: the warm engine answers a neutral agy command with "allow"; the guard's contract is
        # never-allow, so anything but a deny becomes the ask fallback and never counts as governance.
        if host == "agy" and answer["decision"] != "deny":
            return _neutral(host), NEUTRAL_UNKNOWN
        return answer, "engine"
    except Exception:
        return degraded
    finally:
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass
            try:
                proc.communicate(timeout=2)
            except Exception:
                pass


def _argv_value(argv, flag):
    if flag in argv:
        i = argv.index(flag)
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


def main(argv=None):
    """Print one JSON line on stdout and the state on stderr; exit 0 whatever happens."""
    argv = list(sys.argv[1:] if argv is None else argv)
    host = _argv_value(argv, "--host") or ""
    answer, state = _neutral(host), "degraded"
    try:
        try:
            stdin_text = sys.stdin.read()
        except Exception:
            stdin_text = ""
        answer, state = guard(host, stdin_text, _argv_value(argv, "--engine-root"))
    except Exception:
        answer, state = _neutral(host), "degraded"
    sys.stdout.write(json.dumps(answer) + "\n")
    sys.stdout.flush()
    sys.stderr.write(state + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
