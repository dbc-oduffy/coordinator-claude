"""PostToolUse / PostToolUseFailure on `mcp__project-rag__*`: gap banner when project-rag gives no data.

A failed call, or a retrieval call that returned nothing, injects one gap `additionalContext`
banner: the call counts as an attempt, the agent records the exact call and output as a gap and
continues, and the engine alone decides any abort. Every call is also recorded in the rag-call ledger.

Exemptions, each silent except the semantic advisory:
  - MetaHuman wrong-source: a MetaHuman lookup whose `source` is not `unreal_5.8_plugin` is a
    wrong-source error, not an outage; the agent retries with the right source.
  - Semantic-only failure: `project_semantic_search`, or a non-structural call whose output names only
    the embed/semantic band, gets a one-line advisory (use structural lookups, name the semantic gap),
    never the gap banner. A structural tool (symbol, referencers, callers, graph, type hierarchy) always gets the gap banner.
  - example-game-repo stand-down: when the example-game-repo-control plugin (or a settings file) already registers
    its own `project_rag_abort_banner` hook, that hook speaks and this one stays silent, so the
    banner never fires twice.
  - Timeout under load: a structural call whose envelope says `verdict == "timeout"` gets a TIMEOUT UNDER
    LOAD retry-once message (stage, source, retry_after advisory); the same call timing out again
    within ten minutes gets the gap banner. Only `verdict == "warming"` means warming.
  - Non-UE miss: a call that names no engine/unreal/MetaHuman source, repo, tool or type gets a
    retry-then-Grep advisory that reports the gap, never the gap banner. Only a UE/MetaHuman miss gets the gap banner.
  - Non-retrieval tools (health, staleness, instructions) and non-project-rag tools.

Never blocks; always exits 0; every failure degrades to silence.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

_LIB_DIR = Path(__file__).resolve().parents[2] / "lib"

TOOL_PREFIX = "mcp__project-rag__"
EXAMPLE_GAME_REPO_PLUGIN = "example-game-repo-control"
EXAMPLE_GAME_REPO_HOOK_MARKER = "project_rag_abort_banner"
METAHUMAN_SOURCE = "unreal_5.8_plugin"

_NON_RETRIEVAL = frozenset({
    "project_health", "project_staleness_check", "project_rag_instructions",
    "project_rag_status", "project_index_status",
})
SEMANTIC_TOOLS = frozenset({"project_semantic_search"})
_STRUCTURAL_MARKERS = ("symbol", "referencer", "caller", "reference", "type_hierarchy", "graph",
                       "trace", "dependenc", "scip", "lsp")
_SEMANTIC_WORDS = ("embed", "semantic")
_LIST_KEYS = frozenset({
    "results", "matches", "hits", "items", "symbols", "references", "referencers", "callers",
    "files", "chunks", "documents", "nodes", "edges", "examples", "modules", "rows",
})
_COUNT_KEYS = ("count", "total", "total_count", "result_count", "n_results")

BANNER = (
    "PROJECT-RAG GAP: project-rag returned no data: {tool} {outcome}.\n"
    "Call: {call}\n"
    "Output: {output}\n"
    "This call counts as an attempt and does not end your task; the engine alone decides any abort. "
    "Cite this exact call and output in your report as a gap. For an Unreal Engine fact do not answer "
    "from memory or training data: retry once, use another project-rag layer or tool, and mark the "
    "claim UNVERIFIED if none answers. (A MetaHuman lookup needs source={source}; a "
    "source=engine miss is a wrong-source error, retry with the right source.)"
)


ADVISORY = (
    "project-rag semantic search is unavailable: {tool} {outcome} ({output}). This does NOT abort the "
    "task: use the structural lookups (project_symbol, project_referencers, project_symbol_callers, "
    "type hierarchy), Grep for literal text, and name the semantic-search gap in your report."
)


TIMEOUT_BANNER = (
    "TIMEOUT UNDER LOAD: project-rag is up and loaded but {tool} timed out (stage: {stage}; source: {source}). "
    "This is NOT an outage and NOT warming. Back off {wait} and retry this exact call ONCE: "
    "Call: {call}\n"
    "Output: {output}\n"
    "If the retry also times out, cite the call and output in your report as a gap and continue "
    "with another project-rag layer or tool; never answer an Unreal Engine fact from memory or training data."
)
_TIMEOUT_TTL_SECONDS = 600
_TIMEOUT_STATE_FILE = "project-rag-banner-timeouts.json"


def timeout_envelope(output) -> Optional[dict]:
    """The `verdict == "timeout"` envelope inside a tool response or failure text, else None."""
    text = _response_text(output).strip()
    candidates = [text]
    brace = text.find("{")
    if brace > 0:
        candidates.append(text[brace:])
    for cand in candidates:
        try:
            parsed = json.loads(cand)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            if parsed.get("verdict") == "timeout":
                return parsed
            for value in parsed.values():
                if isinstance(value, dict) and value.get("verdict") == "timeout":
                    return value
    return None


def _timeout_key(tool_name: str, tool_input) -> str:
    return f"{tool_name}|{json.dumps(tool_input, sort_keys=True, default=str)}"


def _is_repeat_timeout(key: str) -> bool:
    """Record this timeout; True when the same call already timed out within the TTL (the retry failed).

    Trap: the read-modify-write is not atomic; a concurrent hook can lose an update, which only costs one extra retry message."""
    path = _claude_home() / _TIMEOUT_STATE_FILE
    now = time.time()
    try:
        seen = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(seen, dict):
            seen = {}
    except (OSError, ValueError):
        seen = {}
    seen = {k: t for k, t in seen.items() if isinstance(t, (int, float)) and now - t < _TIMEOUT_TTL_SECONDS}
    repeat = key in seen
    if repeat:
        del seen[key]
    else:
        seen[key] = now
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(seen), encoding="utf-8")
    except OSError:
        return False
    return repeat


def _timeout_text(tool_name: str, tool_input, envelope: dict, output) -> str:
    retry_after = envelope.get("retry_after")
    wait = (f"{retry_after:g} seconds" if isinstance(retry_after, (int, float)) and not isinstance(retry_after, bool)
            and retry_after > 0 else "a few seconds (no retry_after given; it is advisory)")
    source = envelope.get("backpressure_source") or _input_source(tool_input) or "unknown"
    return TIMEOUT_BANNER.format(
        tool=tool_name, stage=envelope.get("stalled_stage") or "unknown", source=source, wait=wait,
        call=f"{tool_name}({_short(tool_input)})", output=_short(output))
MISS_ADVISORY = (
    "project-rag returned no data for a non-Unreal lookup: {tool} {outcome} ({output}). This does NOT "
    "abort the task: retry the call once (pass repo=<the repo's registry key> if it was omitted), "
    "then Grep for literal text, and report the fallback to project-rag as a gap."
)

_UE_WORDS = ("unreal", "metahuman", "engine", "example-game-repo", "ue_addon", "ue-addon")
_UE_TYPE_NAME = re.compile(r"\b[AUFEI][A-Z][a-z]{2,}[A-Za-z]*\b")


def _field(tool_input, *keys) -> str:
    if not isinstance(tool_input, dict):
        return ""
    parts = []
    for key in keys:
        value = tool_input.get(key)
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            parts.extend(v for v in value if isinstance(v, str))
    return " ".join(parts).lower()


def is_ue_miss(short: str, tool_input) -> bool:
    """True when the call targets Unreal Engine or MetaHuman content: an engine tool, a `source` or
    `repo` naming an engine/unreal/example-game-repo band, or a UE-shaped type name in the arguments."""
    if short.startswith("project_engine_"):
        return True
    scope = _field(tool_input, "source", "sources", "repo", "repos")
    if any(w in scope for w in _UE_WORDS):
        return True
    text = _short(tool_input, 4000)
    return "metahuman" in text.lower() or bool(_UE_TYPE_NAME.search(text))


def _is_structural(short: str) -> bool:
    return any(m in short for m in _STRUCTURAL_MARKERS)


def is_semantic_only(short: str, output) -> bool:
    """True when the failing call is semantic-only: the semantic tool itself, or a non-structural tool
    whose output names the embed/semantic band and no structural store."""
    if short in SEMANTIC_TOOLS:
        return True
    if _is_structural(short):
        return False
    text = _response_text(output).lower()
    return any(w in text for w in _SEMANTIC_WORDS) and not any(m in text for m in _STRUCTURAL_MARKERS)


def _short(value, limit: int = 400) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _response_text(response) -> str:
    """Flattened text of a tool response: a string, an MCP `content` list, or a dict."""
    if response is None:
        return ""
    if isinstance(response, str):
        return response
    if isinstance(response, list):
        return "\n".join(_response_text(r) for r in response)
    if isinstance(response, dict):
        if isinstance(response.get("content"), list):
            return "\n".join(_response_text(c) for c in response["content"])
        if isinstance(response.get("text"), str):
            return response["text"]
        return json.dumps(response, ensure_ascii=False, default=str)
    return str(response)


def _empty_value(value) -> bool:
    return value is None or value == "" or value == [] or value == {} or value == 0


def _is_empty(response) -> bool:
    """True when the response carries no retrieval data."""
    if isinstance(response, dict) and response.get("isError"):
        return True
    text = _response_text(response).strip()
    if not text or text in ("null", "[]", "{}"):
        return True
    try:
        parsed = json.loads(text)
    except ValueError:
        return False
    if isinstance(parsed, list):
        return not parsed
    if not isinstance(parsed, dict):
        return False
    if parsed.get("error") and not any(not _empty_value(parsed.get(k)) for k in _LIST_KEYS):
        return True
    lists = [parsed[k] for k in _LIST_KEYS if k in parsed]
    if lists:
        return all(_empty_value(v) for v in lists)
    counts = [parsed[k] for k in _COUNT_KEYS if isinstance(parsed.get(k), int)]
    return bool(counts) and all(c == 0 for c in counts)


def _input_source(tool_input) -> Optional[str]:
    if isinstance(tool_input, dict):
        for key in ("source", "sources"):
            value = tool_input.get(key)
            if isinstance(value, str):
                return value
            if isinstance(value, list) and value and all(isinstance(v, str) for v in value):
                return ",".join(value)
    return None


def is_metahuman_wrong_source(tool_input, response_text: str) -> bool:
    """A MetaHuman lookup made without `source=unreal_5.8_plugin`, or a response pointing at it."""
    source = _input_source(tool_input)
    if source == METAHUMAN_SOURCE:
        return False
    if "metahuman" in _short(tool_input, 4000).lower():
        return True
    return METAHUMAN_SOURCE in response_text


def _claude_home() -> Path:
    config = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(config) if config else Path(os.environ.get("CLAUDE_HOME") or Path.home()) / ".claude"


def _registers_marker(path: Path, require: str = "") -> bool:
    """True when the JSON file at `path` has a hook registration naming the banner script (and, when
    `require` is set, that substring: a settings file may register this coordinator's own copy)."""
    try:
        hooks = json.loads(path.read_text(encoding="utf-8")).get("hooks")
    except (OSError, ValueError, AttributeError):
        return False
    if not isinstance(hooks, dict):
        return False
    for event in ("PostToolUse", "PostToolUseFailure"):
        text = json.dumps(hooks.get(event, []))
        if EXAMPLE_GAME_REPO_HOOK_MARKER in text and require in text:
            return True
    return False


def _example_game_repo_roots() -> list[Path]:
    try:
        if str(_LIB_DIR) not in sys.path:
            sys.path.insert(0, str(_LIB_DIR))
        prs = __import__("plugin_review_signals")
        return [r for r in prs.installed_plugin_roots() if prs.plugin_name(r) == EXAMPLE_GAME_REPO_PLUGIN]
    except Exception:  # noqa: BLE001 -- unresolvable plugin registry reads as "not registered"
        return []


def example_game_repo_banner_registered(cwd: str = "") -> bool:
    """True when example-game-repo's own banner hook is registered: in an installed example-game-repo-control plugin's
    hooks.json, or in a user, project or project-local settings file whose registration names example-game-repo-control."""
    if any(_registers_marker(root / "hooks" / "hooks.json") for root in _example_game_repo_roots()):
        return True
    candidates: list[Path] = []
    home = _claude_home()
    candidates += [home / "settings.json", home / "settings.local.json"]
    start = Path(cwd or os.getcwd())
    for d in (start, *start.parents):
        for name in ("settings.json", "settings.local.json"):
            candidates.append(d / ".claude" / name)
    return any(_registers_marker(p, EXAMPLE_GAME_REPO_PLUGIN) for p in candidates)


def _tool_short(tool_name: str) -> str:
    return tool_name[len(TOOL_PREFIX):] if tool_name.startswith(TOOL_PREFIX) else tool_name


def _is_failure(payload: dict) -> bool:
    """True for a PostToolUseFailure payload (or one carrying `error` with no `tool_response`)."""
    return payload.get("hook_event_name") == "PostToolUseFailure" or (
        "error" in payload and "tool_response" not in payload)


def banner_for(payload: dict) -> str:
    """The gap banner text for this hook payload, or "" when nothing should fire."""
    tool_name = payload.get("tool_name")
    if not isinstance(tool_name, str) or not tool_name.startswith(TOOL_PREFIX):
        return ""
    short = _tool_short(tool_name)
    if short in _NON_RETRIEVAL:
        return ""
    tool_input = payload.get("tool_input")
    if _is_failure(payload):
        output = payload.get("error")
        outcome = "FAILED"
    else:
        response = payload.get("tool_response")
        if not _is_empty(response) and timeout_envelope(response) is None:
            return ""
        output = _response_text(response).strip() or "<empty result>"
        outcome = "returned an EMPTY result"
    if is_metahuman_wrong_source(tool_input, _response_text(output)):
        return ""
    if example_game_repo_banner_registered(payload.get("cwd") or ""):
        return ""
    if is_semantic_only(short, output):
        return ADVISORY.format(
            tool=tool_name, outcome=outcome, output=_short(output if output not in (None, "") else "<no output>"))
    envelope = timeout_envelope(output)
    if envelope is not None and not _is_repeat_timeout(_timeout_key(tool_name, tool_input)):
        return _timeout_text(tool_name, tool_input, envelope, output)
    if not is_ue_miss(short, tool_input):
        return MISS_ADVISORY.format(
            tool=tool_name, outcome=outcome, output=_short(output if output not in (None, "") else "<no output>"))
    return BANNER.format(
        tool=tool_name, outcome=outcome, call=f"{tool_name}({_short(tool_input)})",
        output=_short(output if output not in (None, "") else "<no output>"), source=METAHUMAN_SOURCE)


def ledger_outcome(payload: dict) -> str:
    """`ok` for a successful call that returned data (any success of a non-retrieval tool), else `down`."""
    if _is_failure(payload):
        return "down"
    if _tool_short(str(payload.get("tool_name"))) in _NON_RETRIEVAL:
        return "ok"
    response = payload.get("tool_response")
    return "down" if _is_empty(response) or timeout_envelope(response) is not None else "ok"


def _record_ledger(payload: dict) -> None:
    """Record this project-rag call in the rag-call ledger; the stand-down never silences it. Never raises."""
    try:
        tool_name = payload.get("tool_name")
        if not isinstance(tool_name, str) or not tool_name.startswith(TOOL_PREFIX):
            return
        here = str(Path(__file__).resolve().parent)
        if here not in sys.path:
            sys.path.insert(0, here)
        __import__("_rag_call_ledger").record(payload, ledger_outcome(payload))
    except Exception:  # noqa: BLE001 -- a ledger fault never touches the banner
        return


def main(stdin_text: Optional[str] = None) -> int:
    try:
        raw = sys.stdin.read() if stdin_text is None else stdin_text
        payload = json.loads(raw or "null")
        if not isinstance(payload, dict):
            return 0
        _record_ledger(payload)
        text = banner_for(payload)
        if text:
            event = "PostToolUseFailure" if _is_failure(payload) else "PostToolUse"
            sys.stdout.write(json.dumps(
                {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}},
                separators=(",", ":")))
            sys.stdout.write("\n")
    except Exception:  # noqa: BLE001 -- fail open: a banner that cannot be built is no banner
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
