"""PostToolUse / PostToolUseFailure on `mcp__project-rag__*`: ABORT banner when project-rag gives no data.

A failed call, or a retrieval call that returned nothing, injects one ABORT `additionalContext`
banner: the agent stops and reports the exact call and output instead of answering from Grep or
memory. Sibling to the in-file rule (tripwire A-PROJECT-RAG-MISS-ON-A-UE-FACT-ABORTS-NEVER-FALLS-BACK).

Exemptions, each silent:
  - MetaHuman wrong-source: a MetaHuman lookup whose `source` is not `unreal_5.8_plugin` is a
    wrong-source error, not an outage; the agent retries with the right source.
  - example-game-repo stand-down: when the example-game-repo-control plugin (or a settings file) already registers
    its own `project_rag_abort_banner` hook, that hook speaks and this one stays silent, so the
    banner never fires twice.
  - Non-retrieval tools (health, staleness, instructions) and non-project-rag tools.

Never blocks; always exits 0; every failure degrades to silence.
"""

from __future__ import annotations

import json
import os
import sys
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
_LIST_KEYS = frozenset({
    "results", "matches", "hits", "items", "symbols", "references", "referencers", "callers",
    "files", "chunks", "documents", "nodes", "edges", "examples", "modules", "rows",
})
_COUNT_KEYS = ("count", "total", "total_count", "result_count", "n_results")

BANNER = (
    "!!! ABORT !!! project-rag returned no data: {tool} {outcome}.\n"
    "Call: {call}\n"
    "Output: {output}\n"
    "STOP THE TASK. For an Unreal Engine fact do NOT fall back to Grep, memory or training data: "
    "open your report with an unmistakable ABORT banner quoting this exact call and its output, "
    "say project-rag is not returning data, and hand it back. For a non-UE lookup, retry once, "
    "then Grep, and report the fallback. (A MetaHuman lookup needs source={source}; a "
    "source=engine miss is a wrong-source error, retry with the right source.)"
)


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
    """The ABORT banner text for this hook payload, or "" when nothing should fire."""
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
        if not _is_empty(response):
            return ""
        output = _response_text(response).strip() or "<empty result>"
        outcome = "returned an EMPTY result"
    if is_metahuman_wrong_source(tool_input, _response_text(output)):
        return ""
    if example_game_repo_banner_registered(payload.get("cwd") or ""):
        return ""
    return BANNER.format(
        tool=tool_name, outcome=outcome, call=f"{tool_name}({_short(tool_input)})",
        output=_short(output if output not in (None, "") else "<no output>"), source=METAHUMAN_SOURCE)


def main(stdin_text: Optional[str] = None) -> int:
    try:
        raw = sys.stdin.read() if stdin_text is None else stdin_text
        payload = json.loads(raw or "null")
        if not isinstance(payload, dict):
            return 0
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
