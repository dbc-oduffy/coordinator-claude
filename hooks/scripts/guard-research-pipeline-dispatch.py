"""guard-research-pipeline-dispatch.py -- PreToolUse(Agent) guard: an ad-hoc Agent
dispatch that does the work of a repo-declared research pipeline is denied and
routed to Pipeline C (`/research --mode=structured`).

Tripwire token: RESEARCH-PIPELINE-DISPATCH-GUARD. Hosted by `preuse-agent-dispatch.py`.

Config: `research_pipelines` in the session repo's `coordinator.local.md` frontmatter
(schema: coordinator/schemas/coordinator-local-md.schema.json). Read through the
engine's `tier-last-run._load_local_doctrine` -- the one frontmatter reader, never
re-parsed here.

Deny when the dispatch prompt names a declared `output_paths` entry (glob tail
stripped), that entry's basename directory as a whole path segment, or a
`subjects_hint` keyword as a whole word, AND `subagent_type` is not one of
Pipeline C's own agent types.

Silent allow on everything else: not Agent, nested call (payload carries
`agent_id`), no `coordinator.local.md` or no `research_pipelines` text in it,
unreadable engine reader or config, malformed entries, no match. Workflow
`agent()` dispatch never traverses PreToolUse(Agent), so Pipeline C's own
Workflow fan-out needs no carve-out.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from _message_envelope import compose, render  # noqa: E402

_WIKI_ANCHOR = (
    "coordinator/docs/wiki/coordinator-tripwires/"
    "research-pipeline-dispatch-guard.md"
)

PIPELINE_C_AGENTS = frozenset({
    "research-scout",
    "research-specialist",
    "research-synthesizer",
    "structured-synthesizer",
    "coverage-auditor",
    "research-worker",
    "notebooklm-research-scout",
    "research-sweep",
    "repo-scout",
    "repo-specialist",
    "prior-art-checker",
})

_GLOB_CHARS = "*?[{"


def _agent_name(raw: object) -> str:
    if not isinstance(raw, str):
        return ""
    raw = raw.strip()
    prefix, sep, name = raw.partition(":")
    if sep:
        return name if prefix == "coordinator" else raw
    return raw


def _whole(token: str) -> "re.Pattern[str]":
    return re.compile(r"(?<![\w-])" + re.escape(token) + r"(?![\w-])", re.IGNORECASE)


def _dir_of(path: str) -> str:
    """The glob-free directory prefix of a repo-relative path or glob."""
    cut = len(path)
    for ch in _GLOB_CHARS:
        i = path.find(ch)
        if i != -1:
            cut = min(cut, i)
    head = path[:cut].replace("\\", "/")
    if cut < len(path) and not head.endswith("/"):
        head = head.rpartition("/")[0]
    return head.strip("/")


def _match(entry: dict, prompt: str) -> Optional[str]:
    """What the prompt names from this pipeline entry, or None."""
    low = prompt.replace("\\", "/").lower()
    paths = entry.get("output_paths")
    for raw in paths if isinstance(paths, list) else []:
        if not isinstance(raw, str):
            continue
        d = _dir_of(raw.strip())
        if not d:
            continue
        if d.lower() in low:
            return f"output path `{d}`"
        base = d.rpartition("/")[2]
        if base and _whole(base).search(prompt):
            return f"output directory `{base}`"
    hints = entry.get("subjects_hint")
    for kw in hints if isinstance(hints, list) else []:
        if isinstance(kw, str) and kw.strip() and _whole(kw.strip()).search(prompt):
            return f"subject keyword `{kw.strip()}`"
    return None


def _session_root(payload: dict) -> Optional[Path]:
    from _git_root_walk import git_root_walk

    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd:
        root = git_root_walk(cwd)
        if root:
            return Path(root)
    import _engine_root

    return _engine_root._session_repo_root()


def _pipelines(root: Path) -> list:
    local_md = root / "coordinator.local.md"
    try:
        if "research_pipelines" not in local_md.read_text(encoding="utf-8"):
            return []
    except OSError:
        return []
    import _engine_root

    script = _engine_root.resolve_engine_bin_script("tier-last-run.py")
    if script is None:
        return []
    spec = importlib.util.spec_from_file_location("_tier_last_run_rpg", script)
    if spec is None or spec.loader is None:
        return []
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    found = mod._load_local_doctrine(root).get("research_pipelines")
    return found if isinstance(found, list) else []


def _deny(entry: dict, matched: str) -> dict:
    name = entry.get("name") if isinstance(entry.get("name"), str) else "unnamed"
    spec = entry.get("spec") if isinstance(entry.get("spec"), str) else "<spec>"
    msg = compose(
        f"run `/research --mode=structured` with spec `{spec}` (pipeline `{name}`; "
        f"prompt names {matched}): ad-hoc agents skip its schema file, spec score and "
        f"coverage audit.",
        anchor=_WIKI_ANCHOR,
    )
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": render(msg),
        }
    }


def _decide(payload: Any) -> Optional[dict]:
    if not isinstance(payload, dict) or payload.get("tool_name") != "Agent":
        return None
    if "agent_id" in payload:
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    prompt = tool_input.get("prompt")
    if not isinstance(prompt, str) or not prompt:
        return None
    if _agent_name(tool_input.get("subagent_type")) in PIPELINE_C_AGENTS:
        return None
    root = _session_root(payload)
    if root is None:
        return None
    for entry in _pipelines(root):
        if not isinstance(entry, dict):
            continue
        matched = _match(entry, prompt)
        if matched:
            return _deny(entry, matched)
    return None


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
        out = _decide(payload)
    except BaseException:
        return 0
    if out:
        sys.stdout.write(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
