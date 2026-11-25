"""Tier-1 project-rag nudge text, Grep/Glob hint, deny and degraded text, the code-question agent set, and the `.project-rag` presence gate.

Stdlib-only leaf imported by the SessionStart/SubagentStart nudge and the Grep|Glob hint shim.
Every output is silent-by-construction when the repo carries no `.project-rag` directory.
The ToolSearch select string also names every tool an applicable research-rules layer declares; no
layer, or any failure reading one, leaves it at the tier-1 set.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from typing import Any

NUDGE_BYTE_BUDGET = 600
HINT_BYTE_BUDGET = 300

_RAG_INDEX_DIR = ".project-rag"
_GIT = ".git"
_GREP = "Grep is for prose/literal strings that are not identifiers."
_BRIEF, _DEF, _HOVER, _OUTLINE, _SYM = _TIER1_TOOLS = (
    "project_symbol_brief",
    "project_lsp_definition",
    "project_lsp_hover",
    "project_code_outline",
    "project_symbol",
)

_TIER1_NAMES = ["mcp__project-rag__" + t for t in _TIER1_TOOLS]


def _select(names: list[str]) -> str:
    return "select:" + ",".join(names)


TIER1_SELECT = _select(_TIER1_NAMES)


def _layer_tools(cwd: Any) -> list[str]:
    """Tools the installed research-rules layers declare for the repo holding `cwd`; [] on any failure."""
    try:
        root = Path(cwd)
        for d in (root, *root.parents):
            if (d / _GIT).exists():
                root = d
                break
        src = Path(__file__).resolve().parents[2] / "pipelines/deep-research/research_rules_layer.py"
        spec = importlib.util.spec_from_file_location(src.stem, src)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return [t for t in mod.required_tools(root) if isinstance(t, str)]
    except Exception:
        return []


def select_string(cwd: Any = None) -> str:
    """The ToolSearch select string: the tier-1 tools plus every tool the applicable layer declares."""
    names = list(_TIER1_NAMES)
    names += [t for t in _layer_tools(cwd or Path.cwd()) if t not in names]
    return _select(names)


def nudge_text(cwd: Any = None) -> str:
    """One short tag-free paragraph naming the tier-1 tools.

    At most NUDGE_BYTE_BUDGET bytes when no layer applies; a layer's declared tool names are added
    verbatim, never truncated.
    """
    return (
        f'Use project-rag before Grep/Glob for symbols. ToolSearch("{select_string(cwd)}"). '
        f'{_BRIEF}(symbol_name="X", lsp=true) first; {_DEF}(file=, line=, name=) or {_HOVER}; '
        f'{_OUTLINE}(file=); {_SYM}(symbol_name="X"). {_GREP}'
    )


def hint_text(symbol: str) -> str:
    """The Grep/Glob redirect hint for `symbol`; at most HINT_BYTE_BUDGET bytes."""
    return f"`{str(symbol)[:60]}`: {_BRIEF} or {_SYM} beats Grep; {_OUTLINE}(file=) for a file. {_GREP}"


CODE_QUESTION_AGENTS = frozenset({
    "sizing-scout", "prior-art-checker", "premise-checker", "plan-author", "enricher",
    "repo-specialist", "research-specialist", "code-reviewer", "staff-eng", "coverage-auditor",
    "research-scout", "research-synthesizer", "structured-synthesizer",
})


def is_code_question_agent(agent_type: Any) -> bool:
    """True for a CODE_QUESTION_AGENTS member or any `*-reviewer`, with or without a `coordinator:` prefix."""
    if not isinstance(agent_type, str):
        return False
    name = agent_type.strip().rsplit(":", 1)[-1]
    return name in CODE_QUESTION_AGENTS or (name.endswith("-reviewer") and len(name) > len("-reviewer"))


def deny_text(symbol: str, cwd: Any = None) -> str:
    """The Grep refusal for `symbol`: names the ToolSearch select string and the lookup tools to call first."""
    return (
        f"[guard] RAG-FIRST-GUARD: `{str(symbol)[:60]}` is a code symbol; make one project-rag call before Grep. "
        f'ToolSearch("{select_string(cwd)}"), then {_BRIEF}(symbol_name="X", lsp=true) or {_SYM}(symbol_name="X"). '
        f"One attempted call, even a failed one, lifts this refusal. {_GREP}"
    )


def degraded_text() -> str:
    """The loud warning carried by a Grep allowed because the recorded project-rag outcome is a failure."""
    return (
        "DEGRADED: project-rag is down; Grep is allowed as the fallback. "
        "Say in your report that this answer rests on grep, not the index."
    )


NAG_EVERY = 5
_NAG_MAX_KEYS = 500
_CODE_INTEL_HINTS = (
    "serena", "lsp", "scip", "tree-sitter", "treesitter", "ctags", "sourcegraph",
    "ast-grep", "code-index", "codebase", "code-graph", "repomix",
)


def _home() -> Path:
    return Path.home()


def _mcp_names(doc: Any) -> list[str]:
    servers = doc.get("mcpServers") if isinstance(doc, dict) else None
    return [k for k in servers if isinstance(k, str)] if isinstance(servers, dict) else []


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _install_names(cwd: Any = None) -> list[str]:
    """Every MCP server and enabled-plugin name this install exposes to `cwd`; [] on any failure."""
    try:
        home = _home()
        names: list[str] = []
        root = Path(cwd) if isinstance(cwd, (str, Path)) and str(cwd) else None
        if root is not None:
            for d in (root, *root.parents):
                if (d / ".mcp.json").is_file():
                    names += _mcp_names(_read_json(d / ".mcp.json"))
                if (d / _GIT).exists():
                    break
        user = _read_json(home / ".claude.json")
        names += _mcp_names(user)
        projects = user.get("projects") if isinstance(user, dict) else None
        if root is not None and isinstance(projects, dict):
            for key, val in projects.items():
                if isinstance(key, str) and Path(key) in (root, *root.parents):
                    names += _mcp_names(val)
        plugins = (_read_json(home / ".claude" / "settings.json") or {}).get("enabledPlugins")
        if isinstance(plugins, dict):
            names += [k.split("@")[0] for k, v in plugins.items() if v and isinstance(k, str)]
        return names
    except Exception:
        return []


def installed_code_intel_tools(cwd: Any = None) -> list[str]:
    """Names of non-project-rag code-intelligence MCP servers and plugins this install enables; [] on any failure.

    Reads the repo `.mcp.json`, `~/.claude.json` (global and per-project servers) and the
    `enabledPlugins` of `~/.claude/settings.json`; a name counts only when it matches a known
    code-intelligence family.
    """
    out: list[str] = []
    for n in _install_names(cwd):
        low = n.lower()
        if "project-rag" in low or "project_rag" in low or n in out:
            continue
        if any(h in low for h in _CODE_INTEL_HINTS):
            out.append(n)
    return out


def contract_path() -> Path:
    """The tier contract the engine also imports."""
    return Path(__file__).resolve().parents[2] / "contract" / "project-rag-gated-roles.json"


def _contract() -> dict:
    doc = _read_json(contract_path())
    return doc if isinstance(doc, dict) else {}


def _provider(cwd: Any = None) -> dict | None:
    """The first contract provider entry whose `detect` names match an installed MCP server or plugin."""
    providers = _contract().get("providers")
    if not isinstance(providers, list):
        return None
    names = [n.lower() for n in _install_names(cwd)]
    for p in providers:
        detect = p.get("detect") if isinstance(p, dict) else None
        if isinstance(detect, list) and any(
            isinstance(d, str) and d.lower() in n for d in detect for n in names
        ):
            return p
    return None


def tier(cwd: Any = None) -> str:
    """"none" without project-rag, "ue" when a registered provider is installed beside it, else "rag"."""
    if not rag_present(cwd):
        return "none"
    p = _provider(cwd)
    return "ue" if p and p.get("tier") == "ue" else "rag"


def nag_every(cwd: Any = None) -> int:
    """The Grep|Glob nag period for the tier of `cwd`: the contract's `nag_every[tier]` when a positive int, else NAG_EVERY."""
    table = _contract().get("nag_every")
    n = table.get(tier(cwd)) if isinstance(table, dict) else None
    return n if isinstance(n, int) and not isinstance(n, bool) and n > 0 else NAG_EVERY


_RAG_DUTY = (
    "THE ENGINE ABORTS THE RUN IF YOU MAKE ZERO PROJECT-RAG CALL ATTEMPTS. A FAILED CALL STILL COUNTS AS AN "
    "ATTEMPT AND IS NEVER A REASON TO ABORT; REPORT IT AS A GAP AND CONTINUE. CALLING IT ONCE AND NO MORE "
    "DRAWS NAGS, NEVER AN ABORT."
)


def _provider_duty(p: dict) -> str:
    """The provider's own duty text with its `ue_cadence` numbers filled in; "" when absent or malformed."""
    cad = p.get("ue_cadence")
    text = p.get("duty_text")
    if not (isinstance(text, str) and isinstance(cad, dict)):
        return ""
    w, m = cad.get("window_tool_calls"), cad.get("min_rag_calls")
    if not all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in (w, m)):
        return ""
    return text.replace("{window_tool_calls}", str(w)).replace("{min_rag_calls}", str(m))


def duty_text(cwd: Any = None) -> str:
    """The ALL-CAPS tier duty block stating the run's abort rule up front; "" at tier none.

    Tier rag is generic; tier ue is the installed provider's registered text, numbers read from the contract.
    """
    t = tier(cwd)
    if t == "none":
        return ""
    if t == "ue":
        return _provider_duty(_provider(cwd) or {}) or _RAG_DUTY
    return _RAG_DUTY


def push_text(cwd: Any, agent_type: Any = None) -> str:
    """The SubagentStart code-intelligence push; "" when nothing applies.

    project-rag installed: its nudge, led for a code-question agent by an ALL-CAPS MUST and the tier's
    abort rule. Not installed: a code-question agent is pointed at the detected code-intelligence tools,
    or told nothing.
    """
    code_agent = is_code_question_agent(agent_type)
    if rag_present(cwd):
        if not code_agent:
            return nudge_text(cwd)
        return (
            "CODE INTELLIGENCE FIRST: PROJECT-RAG IS INSTALLED. YOU MUST CALL ITS TOOLS BEFORE ANY GREP, GLOB "
            "OR FILE-BY-FILE READ FOR A CODE QUESTION, AND KEEP CALLING THEM. "
            + duty_text(cwd) + " " + nudge_text(cwd)
        )
    if not code_agent:
        return ""
    tools = installed_code_intel_tools(cwd)
    if not tools:
        return ""
    return (
        "CODE INTELLIGENCE FIRST: BEFORE ANY GREP, GLOB OR FILE-BY-FILE READ FOR A CODE QUESTION, YOU MUST "
        f"USE THE CODE-INTELLIGENCE TOOLS THIS INSTALL PROVIDES: {', '.join(tools)}. "
        "GREP IS FOR LITERAL TEXT ONLY."
    )


def nag_text(symbol: str) -> str:
    """The periodic reminder carried by a Grep|Glob from an agent that already called project-rag."""
    return (
        f"CODE INTELLIGENCE FIRST: `{str(symbol)[:60]}` IS A CODE SYMBOL; KEEP USING PROJECT-RAG "
        f"({_BRIEF}, {_SYM}, {_OUTLINE}) INSTEAD OF GREP. {_GREP}"
    )


def bump_search_count(session_id: str, agent_id: Any, path: Path | None = None) -> int:
    """Increment and return the symbol-search count for (session_id, agent_id); 0 on any failure.

    The counter lives beside the call ledger, in the same machine-local settings home.
    """
    try:
        if path is None:
            import _rag_call_ledger

            path = _rag_call_ledger.ledger_path().with_name("rag-search-counts.json")
        counts = _read_json(path)
        counts = counts if isinstance(counts, dict) else {}
        key = f"{session_id}|{agent_id}"
        n = int(counts.pop(key, 0)) + 1
        counts[key] = n
        while len(counts) > _NAG_MAX_KEYS:
            counts.pop(next(iter(counts)))
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(counts), encoding="utf-8")
        os.replace(tmp, path)
        return n
    except Exception:
        return 0


def rag_present(cwd: Any) -> bool:
    """True only when a `.project-rag` directory sits at or above cwd, stopping at the git root or home.

    Any failure returns False so callers stay silent when project-rag is absent.
    """
    if not isinstance(cwd, (str, os.PathLike)) or not str(cwd):
        return False
    try:
        here = Path(cwd)
        home = Path.home()
        for d in (here, *here.parents):
            if d == home:
                return False
            if (d / _RAG_INDEX_DIR).is_dir():
                return True
            if (d / _GIT).exists():
                return False
    except Exception:
        return False
    return False
