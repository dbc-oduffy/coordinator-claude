#!/usr/bin/env python3
"""Never-fail client for the Klabauter host-hook shim (Codex and agy PreToolUse guard).

guard() imports coordinator_core.host_hooks.shim from the engine root into this interpreter and runs
shim.run(host, stdin) on a daemon thread joined at one wall, so import, the warm-socket dial, the shim's
engine-free backstop and telemetry are all bounded and no second interpreter starts. Any miss (no engine
root, import failure, timeout, empty or invalid answer, or a Codex object that is neither {} nor the exact
nested PreToolUse deny) answers the host's open answer with state "degraded". agy never answers a bare ask there:
it classifies the command in-process against the irreversible-class denies (backstop.degrade_match, no spawn) and
answers a deny naming the cause on a match, else an allow whose reason says the guard was down.
A Codex bare {} is state "neutral-unknown": the shim cannot yet tell a real neutral verdict from a warm miss
or caught error. Only a verified deny (or valid agy answer) is "engine"; "degraded" and "neutral-unknown"
never satisfy an enforcement check. A cold or unreachable warm engine is answered by the shim itself and
recorded in warm/degrade.jsonl, not in this module's log.

Every degrade appends one record {ts, host, cause, budget_secs, cpu_secs} to degrade_log_path(); cpu_secs is the
process CPU the guard spent. An import_error or run_error record also carries exc_type and, for a missing module,
exc_module. A write failure never alters the answer. The log is append-only and unrotated; the
A7 reader owns truncation.

CLI: unimatrix-host-guard.py --host codex|agy|grok [--engine-root PATH]
  stdin: one hook payload. stdout: exactly one JSON line. stderr: `state`. Exit 0 always.
"""
import contextlib
import io
import json
import os
import sys
import threading
import time
from pathlib import Path

NEUTRAL = {"agy": {"decision": "allow"}, "codex": {}, "grok": {}}
NEUTRAL_UNKNOWN = "neutral-unknown"
DEFAULT_BUDGET_SECS = 0.5
DEGRADE_LOG_NAME = "host-guard-degrades.jsonl"
CLASSIFY_WALL_SECS = 0.25


def _neutral(host):
    return dict(NEUTRAL.get(host, {}))


def _place_engine_root(engine_root):
    lib = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
    if lib not in sys.path:
        sys.path.insert(0, lib)
    from cc_invoke import place_engine_root_on_path

    place_engine_root_on_path(str(engine_root))


def _load_shim(engine_root):
    """Import coordinator_core.host_hooks.shim with engine_root first on sys.path. Test seam."""
    _place_engine_root(engine_root)
    from coordinator_core.host_hooks import shim
    return shim


def _load_backstop(engine_root):
    """(backstop module, agy adapter) from engine_root when it is a directory, else from sys.path. Test seam."""
    if engine_root and Path(engine_root).is_dir():
        _place_engine_root(engine_root)
    from coordinator_core.host_hooks import backstop
    from coordinator_core.host_hooks.agy_adapter import AgyAdapter
    return backstop, AgyAdapter()


CODEX_DENY_KEYS = {"hookEventName", "permissionDecision", "permissionDecisionReason"}


def _is_codex_deny(obj):
    """True only for the exact nested PreToolUse deny: {"hookSpecificOutput": {event, "deny", reason}}."""
    if not isinstance(obj, dict) or set(obj) != {"hookSpecificOutput"}:
        return False
    inner = obj["hookSpecificOutput"]
    return (isinstance(inner, dict) and set(inner) == CODEX_DENY_KEYS
            and inner["hookEventName"] == "PreToolUse" and inner["permissionDecision"] == "deny"
            and isinstance(inner["permissionDecisionReason"], str))


CODEX_ADVISORY_KEYS = {"hookEventName", "permissionDecision", "additionalContext"}


def _is_codex_advisory(obj):
    """True for the nested PreToolUse advisory {event[, allow|ask], non-empty additionalContext}; never a deny."""
    if not isinstance(obj, dict) or set(obj) != {"hookSpecificOutput"}:
        return False
    inner = obj["hookSpecificOutput"]
    return (isinstance(inner, dict) and {"hookEventName", "additionalContext"} <= set(inner)
            and set(inner) <= CODEX_ADVISORY_KEYS and inner["hookEventName"] == "PreToolUse"
            and inner.get("permissionDecision", "allow") in ("allow", "ask")
            and isinstance(inner["additionalContext"], str) and bool(inner["additionalContext"]))


GROK_PERMISSION_DECISIONS = ("allow", "deny", "ask")
GROK_INNER_KEYS = CODEX_DENY_KEYS | {"additionalContext"}


def _is_grok_decision(obj):
    """True for {} or the nested PreToolUse answer {"hookSpecificOutput": {event, decision[, reason][, additionalContext]}}."""
    if obj == {}:
        return True
    if not isinstance(obj, dict) or set(obj) != {"hookSpecificOutput"}:
        return False
    inner = obj["hookSpecificOutput"]
    return (isinstance(inner, dict) and {"hookEventName", "permissionDecision"} <= set(inner)
            and set(inner) <= GROK_INNER_KEYS and inner["hookEventName"] == "PreToolUse"
            and inner["permissionDecision"] in GROK_PERMISSION_DECISIONS
            and isinstance(inner.get("permissionDecisionReason", ""), str)
            and isinstance(inner.get("additionalContext", ""), str))


def _valid_answer(host, obj):
    if not isinstance(obj, dict):
        return False
    if host == "agy":
        return obj.get("decision") in ("deny", "ask", "allow")
    if host == "grok":
        return _is_grok_decision(obj)
    return obj == {} or _is_codex_deny(obj) or _is_codex_advisory(obj)


def _parse_single_object(text):
    """The one JSON object in `text`, or None for empty, partial, invalid or multi-value text."""
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def degrade_log_path():
    """<settings home>/host-hooks/host-guard-degrades.jsonl; COORDINATOR_SETTINGS_HOME overrides the home."""
    env = os.environ.get("COORDINATOR_SETTINGS_HOME")
    home = Path(env) if env else Path.home() / ".coordinator-claude-settings"
    return home / "host-hooks" / DEGRADE_LOG_NAME


def _exc_detail(exc):
    """{exc_type, exc_module?} naming a caught exception; exc_module is ModuleNotFoundError.name when present."""
    detail = {"exc_type": type(exc).__name__}
    name = exc.name if isinstance(exc, ImportError) else None
    if isinstance(name, str) and name:
        detail["exc_module"] = name
    return detail


def _record_degrade(host, cause, budget_secs, cpu_secs, verdict=None, unchecked=None, detail=None):
    """Append one JSON line naming why the guard degraded; never raises."""
    try:
        path = degrade_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        rec = {"ts": round(time.time(), 3), "host": host, "cause": cause, "budget_secs": budget_secs,
               "cpu_secs": cpu_secs}
        if detail:
            rec.update(detail)
        if verdict:
            rec["verdict"] = verdict
        if unchecked:
            rec["unchecked"] = unchecked
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
    except Exception:
        pass


def _classify_irreversible(stdin_text, engine_root):
    """(deny reason, None) for an irreversible-class command; (None, None) for any other; (None, why) when it
    could not be classified. In-process and spawn-free, bounded by CLASSIFY_WALL_SECS."""
    box = {}

    def work():
        try:
            payload = _parse_single_object(stdin_text or "")
            if not isinstance(payload, dict):
                box["unchecked"] = "no_payload"
                return
            backstop, adapter = _load_backstop(engine_root)
            verdict = backstop.degrade_match(adapter.adapt_event(payload))
            box["deny"] = (verdict.get("reason") or "irreversible command") if verdict else None
        except Exception:
            box["unchecked"] = "classifier_unavailable"

    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    worker.join(CLASSIFY_WALL_SECS)
    if worker.is_alive():
        return None, "classifier_timeout"
    return box.get("deny"), box.get("unchecked")


def _degrade(host, cause, budget_secs, cpu_secs=None, stdin_text=None, engine_root=None, detail=None):
    """Record the degrade and answer open. agy classifies the command against the irreversible-class denies:
    a match is a deny naming the cause, anything else an allow whose reason says the guard was down; never a bare ask."""
    if host != "agy":
        _record_degrade(host, cause, budget_secs, cpu_secs, detail=detail)
        return _neutral(host), "degraded"
    deny, unchecked = _classify_irreversible(stdin_text, engine_root)
    if deny:
        _record_degrade(host, cause, budget_secs, cpu_secs, verdict="deny", detail=detail)
        return {"decision": "deny",
                "reason": "Klabauter guard unavailable (%s); irreversible-class command denied: %s" % (cause, deny)}, "degraded"
    _record_degrade(host, cause, budget_secs, cpu_secs, verdict="allow", unchecked=unchecked, detail=detail)
    note = ("irreversible-class check also unavailable (%s)" % unchecked) if unchecked else \
        "no irreversible-class match; every other guard is off"
    return {"decision": "allow",
            "reason": "WARNING: Klabauter guard DEGRADED (%s); %s; proceeding open" % (cause, note)}, "degraded"


def _run_shim(host, stdin_text, engine_root, box):
    try:
        shim = _load_shim(engine_root)
    except Exception as exc:
        box["cause"] = "import_error"
        box["detail"] = _exc_detail(exc)
        return
    try:
        take = getattr(shim, "take_pending_nag", None)
        if take:
            take()
        box["answer"] = shim.run(host, stdin_text)
        if take:
            box["nag"] = take()
            box["shim"] = shim
    except Exception as exc:
        box["cause"] = "run_error"
        box["detail"] = _exc_detail(exc)


def guard(host, stdin_text, engine_root, budget_secs=DEFAULT_BUDGET_SECS, pending=None):
    """Return (answer, state): "engine" for a Codex nested deny or a valid agy answer; "neutral-unknown" for a
    Codex bare {} (the shim emits it for a real neutral verdict, a warm miss and a caught internal error alike);
    else "degraded" with the host's neutral answer. Only "engine" may count as governance evidence.

    `pending`, a list, receives (shim, nag) when the shim finished in time and merged a DIY nag; a timeout,
    degrade or neutral substitution leaves it empty, and `main` stamps the nag window only after writing."""
    if host not in NEUTRAL:
        return {}, "degraded"

    def degrade(cause, cpu_secs=None, detail=None):
        return _degrade(host, cause, budget_secs, cpu_secs, stdin_text, engine_root, detail)

    if not engine_root or not Path(engine_root).is_dir():
        return degrade("no_engine_root")
    if not isinstance(_parse_single_object(stdin_text or ""), dict):
        return degrade("bad_stdin")
    cpu0 = time.process_time()
    box = {}
    worker = threading.Thread(target=_run_shim, args=(host, stdin_text, engine_root, box), daemon=True)
    try:
        worker.start()
        worker.join(budget_secs)
        cpu_secs = round(time.process_time() - cpu0, 4)
        if worker.is_alive():
            return degrade("timeout", cpu_secs)
        if "cause" in box:
            return degrade(box["cause"], cpu_secs, box.get("detail"))
        answer = box.get("answer")
        if not _valid_answer(host, answer):
            return degrade("invalid_answer", cpu_secs)
        if pending is not None and box.get("nag"):
            pending[:] = [(box["shim"], box["nag"])]
        if host == "codex" and (answer == {} or _is_codex_advisory(answer)):
            return answer, NEUTRAL_UNKNOWN
        if host == "grok" and answer.get("hookSpecificOutput", {}).get("permissionDecision") != "deny":
            return answer, NEUTRAL_UNKNOWN
        # Trap: a non-deny agy answer is never forwarded as an ask (agy -p auto-approves it); it becomes an
        # allow that keeps the advisory reason and never counts as governance.
        if host == "agy" and answer["decision"] != "deny":
            reason = answer.get("reason")
            if isinstance(reason, str) and reason:
                return {"decision": "allow", "reason": reason}, NEUTRAL_UNKNOWN
            return _neutral(host), NEUTRAL_UNKNOWN
        return answer, "engine"
    except Exception as exc:
        return degrade("run_error", None, _exc_detail(exc))


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
    pending = []
    stdin_text, engine_root = "", _argv_value(argv, "--engine-root")
    try:
        try:
            stdin_text = sys.stdin.read()
        except Exception:
            stdin_text = ""
        # Trap: the in-process shim and engine print notices on stderr; the contract is `state` alone.
        with contextlib.redirect_stderr(io.StringIO()):
            answer, state = guard(host, stdin_text, engine_root, pending=pending)
    except Exception:
        try:
            answer, state = _degrade(host, "run_error", DEFAULT_BUDGET_SECS, None, stdin_text, engine_root)
        except Exception:
            answer, state = _neutral(host), "degraded"
    sys.stdout.write(json.dumps(answer) + "\n")
    sys.stdout.flush()
    if pending:
        try:
            shim, nag = pending[0]
            shim.mark_if_delivered(nag, answer)
        except Exception:
            pass
    sys.stderr.write(state + "\n")
    return 0


if __name__ == "__main__":
    if any(_a in ("-h", "--help") for _a in sys.argv[1:]):
        print("usage: unimatrix-host-guard [-h]\nunimatrix host guard hook body; reads hook JSON on stdin, emits JSON")
        raise SystemExit(0)
    sys.exit(main())
