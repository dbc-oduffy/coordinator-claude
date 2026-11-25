"""guard-rag-bypass-brief.py -- PreToolUse(Agent) guard: an Agent brief that tells the run to
read project-rag-served corpus files by path instead of calling project-rag draws a loud
warning. Hosted by `preuse-agent-dispatch.py`; no hooks.json entry of its own.

Tripwire token: RAG-BYPASS-BRIEF.

Two bypass shapes, judged per clause of the prompt:
  - SUBSTITUTION: "instead of / rather than / in place of / bypass / skip / avoid" then
    (up to two words) `project-rag`, or a bare "do not use / never call / no need to query"
    `project-rag`.
  - DIRECT READ: a read verb (read, open, cat, browse, grep, scan) with "directly",
    "by path" or "from disk" AND a corpus noun (corpus, corpus-store, `.project-rag`) in the
    same clause.
A negator earlier in the clause ("do not read the corpus directly") suppresses the match: a
brief that forbids the bypass is the rule, not the violation.

Warning only, never a deny: the EM may mean it, and the brief, not the agent, is the
violation. Silent unless a `.project-rag` directory sits at or above the payload cwd. The
revise-note side of the same defect reaches a workflow run through `workflow.revise`, which
never traverses PreToolUse(Agent); that leg belongs to claude-klabauter.

Fail-open: any error, a non-Agent payload, or an unreadable prompt allows silently.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

_WIKI_ANCHOR = (
    "coordinator/docs/wiki/coordinator-tripwires/"
    "code-intelligence-before-grep-is-mandatory.md"
)

_CLAUSE_SPLIT_RE = re.compile(r"[.;!?](?=\s|$)|\n")
_RAG = r"project[- ]rag"

_SUBSTITUTION_RE = re.compile(
    r"(?<![\w-])(?:instead\s+of|rather\s+than|in\s+place\s+of|bypass(?:ing)?|skip(?:ping)?|"
    r"avoid(?:ing)?)\s+(?:[\w`'-]+\s+){0,2}" + _RAG,
    re.IGNORECASE,
)
_ABSTAIN_RE = re.compile(
    r"(?<![\w-])(?:do\s+not|don'?t|never|no\s+need\s+to|shouldn'?t|must\s+not)\s+"
    r"(?:use|call|query|consult|rely\s+on|go\s+through|touch)\s+(?:the\s+)?`?" + _RAG,
    re.IGNORECASE,
)
_READ_VERB_RE = re.compile(
    r"(?<![\w-])(?:read|reads|open|opens|cat|browse|grep|scan|parse)(?![\w-])", re.IGNORECASE
)
_BY_PATH_RE = re.compile(r"(?<![\w-])(?:directly|by\s+path|from\s+disk|straight\s+from)(?![\w-])", re.IGNORECASE)
_CORPUS_RE = re.compile(r"corpus|\.project-rag|project-rag-corpus-store", re.IGNORECASE)
_NEGATOR_RE = re.compile(
    r"(?<![\w-])(?:not|never|don'?t|without|must\s+not|shouldn'?t)(?![\w-])", re.IGNORECASE
)


def _bypass_clause(prompt: str) -> Optional[str]:
    """The first clause of `prompt` that instructs a project-rag bypass, or None."""
    for clause in _CLAUSE_SPLIT_RE.split(prompt):
        sub = _SUBSTITUTION_RE.search(clause)
        if sub and not _NEGATOR_RE.search(clause[: sub.start()]):
            return clause.strip()
        if _ABSTAIN_RE.search(clause):
            return clause.strip()
        verb = _READ_VERB_RE.search(clause)
        if (
            verb
            and _BY_PATH_RE.search(clause)
            and _CORPUS_RE.search(clause)
            and not _NEGATOR_RE.search(clause[: verb.start()])
        ):
            return clause.strip()
    return None


def _warning(clause: str) -> dict:
    from _message_envelope import compose, render

    quoted = clause if len(clause) <= 80 else clause[:77] + "..."
    msg = compose(
        f'RAG-BYPASS-BRIEF: brief says "{quoted}" -- reading project-rag-served files by '
        f"path skips the index the run must consult. Tell it to call project-rag tools first. "
        f"Proceeding.",
        anchor=_WIKI_ANCHOR,
    )
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": render(msg)}}


def _decide(payload: Any) -> Optional[dict]:
    if not isinstance(payload, dict) or payload.get("tool_name") != "Agent":
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    prompt = tool_input.get("prompt")
    if not isinstance(prompt, str) or not prompt:
        return None
    clause = _bypass_clause(prompt)
    if clause is None:
        return None
    from _project_rag_nudge import rag_present

    if not rag_present(payload.get("cwd")):
        return None
    return _warning(clause)


def main() -> int:
    try:
        out = _decide(json.loads(sys.stdin.read()))
        if out:
            sys.stderr.write(out["hookSpecificOutput"]["additionalContext"] + "\n")
            sys.stdout.write(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n")
    except BaseException:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
