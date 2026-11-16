"""Tier-1 project-rag nudge text, Grep/Glob hint text, and the `.project-rag` presence gate.

Stdlib-only leaf imported by the SessionStart/SubagentStart nudge and the Grep|Glob hint shim.
Every output is silent-by-construction when the repo carries no `.project-rag` directory.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

NUDGE_BYTE_BUDGET = 600
HINT_BYTE_BUDGET = 300

_RAG_INDEX_DIR = ".project-rag"
_BRIEF, _DEF, _HOVER, _OUTLINE, _SYM = _TIER1_TOOLS = (
    "project_symbol_brief",
    "project_lsp_definition",
    "project_lsp_hover",
    "project_code_outline",
    "project_symbol",
)

TIER1_SELECT = "select:" + ",".join("mcp__project-rag__" + t for t in _TIER1_TOOLS)


def nudge_text() -> str:
    """One short tag-free paragraph naming the tier-1 tools; at most NUDGE_BYTE_BUDGET bytes."""
    return (
        f'project-rag indexes this repo; use before Grep/Glob for symbols. Load ToolSearch("{TIER1_SELECT}"). '
        f'{_BRIEF}(symbol_name="X", lsp=true) first; {_DEF}(file=, line=, name=) or {_HOVER}; '
        f'{_OUTLINE}(file=); {_SYM}(symbol_name="X"). repo= optional.'
    )


def hint_text(symbol: str) -> str:
    """The Grep/Glob redirect hint for `symbol`; at most HINT_BYTE_BUDGET bytes."""
    return (
        f"`{str(symbol)[:60]}`: {_BRIEF}(symbol_name=..., lsp=true) or {_SYM}(symbol_name=...) "
        f"beats Grep; {_OUTLINE}(file=) for a file. Grep stays right for literal text."
    )


def rag_present(cwd: Any) -> bool:
    """True only when a `.project-rag` directory sits at or above cwd, stopping at the git root or home.

    Any failure returns False so callers stay silent when project-rag is absent.
    """
    if not isinstance(cwd, str) or not cwd:
        return False
    try:
        here = Path(cwd)
        home = Path.home()
        for d in (here, *here.parents):
            if d == home:
                return False
            if (d / _RAG_INDEX_DIR).is_dir():
                return True
            if (d / ".git").exists():
                return False
    except Exception:
        return False
    return False
