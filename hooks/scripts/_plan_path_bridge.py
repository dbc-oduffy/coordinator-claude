"""_plan_path_bridge -- carries a plan-derivable dispatch's `plan_path` from
PreToolUse(Agent), the only event that sees the child's prompt, to
SubagentStart, the only event that caters it.

Purpose: `provision_report._provision`'s plan-derivable leg fires for the G2
lens emitters ONLY when the spawn payload carries a non-empty `plan_path`;
absent it, those dispatches fall through to the session-keyed
`state/subagent-share/` home and their `state/plan-sidecars/<plan-stem>.<lens>.md`
sidecar never exists. `plan_path` is extracted from the child's prompt, and a
`SubagentStart` payload carries no prompt at all (`agent_id`, `agent_type`,
`cwd`, `session_id`, `transcript_path`, `prompt_id` -- nothing else). The two
events share `session_id`, so the extraction happens on the PreToolUse side and
lands here; the SubagentStart shim reads it back before relaying the catering op.

Newest-matching-wins, never pop. The plan-derivable path is deterministic and
its provisioning is idempotent-on-collision, so a duplicate read costs nothing
while a lost pop would cost a whole sidecar -- there is no read-modify-write
here and therefore no race between two concurrent hook processes. A second
dispatch of the same lens against a different plan writes its own newer row
before its own SubagentStart fires, so newest-wins is correct rather than
merely convenient.

Fail-open at every leg: an unresolvable root, an unwritable queue, a malformed
row, or an absent file all degrade to "no plan_path" -- the same fall-through
that exists without this module, never a blocked spawn.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path, PureWindowsPath
from typing import Optional

#: Queue leaf under `state/subagent-share/<session_id>/`, sibling of the
#: telemetry `*.jsonl` rows already written there.
QUEUE_LEAF = "plan-path-queue.jsonl"

#: Rows older than this are ignored on read -- a PreToolUse fire whose spawn
#: was denied leaves a row nothing ever consumes.
_ROW_TTL_SECONDS = 3600

#: Rewrite cap; the file is truncated to its newest rows on every append.
_MAX_ROWS = 64

#: The subagent_types whose sidecar home is plan-derivable. Mirrors
#: `coordinator_core.subagent_sandbox.provision_report._PLAN_DERIVABLE_LENS`'s
#: key set -- the engine owns the lens SUFFIXES and the path formula; this
#: plane only needs to know which dispatches are worth extracting a plan path
#: for. Pinned against that engine key set by
#: coordinator/tests/test_sidecar_family_resolution.py.
PLAN_DERIVABLE_TYPES = frozenset(
    {
        "coordinator:prior-art-checker",
        "coordinator:plan-coverage-checker",
        "coordinator:external-pattern-checker",
        "coordinator:docs-checker",
        "coordinator:plan-reviewer",
    }
)

# Both separators, per tripwire `GUARD-PATH-REGEX-SEPARATOR-BLINDNESS`: a
# Windows brief cites `docs\plans\<stem>.md`, which a forward-slash-only prefix
# literal never matches, and this detector's failure on a miss is SILENT -- no
# plan_path is recorded and the G2 sidecar chain simply does not form. The
# leading `/`/`\` in the boundary class admits an absolute filesystem path but
# also matches a URL path separator; that ambiguity is resolved post-match in
# `extract_plan_path` by rejecting a candidate whose whitespace-delimited token
# prefix contains "://" (scheme-agnostic, not a literal http(s) check).
_PLAN_PATH_RE = re.compile(
    r"(?:^|[\s(\[\"'`/\\])"
    r"((?:docs[/\\]plans[/\\]|~[/\\]\.claude[/\\]plans[/\\])[^\s()\[\]\"'`,;:]+\.md)"
)

_PREFIX_RE = re.compile(r"(docs[/\\]plans[/\\]|~[/\\]\.claude[/\\]plans[/\\])")


def extract_plan_path(prompt: str) -> Optional[str]:
    """First genuine `docs/plans/*.md` (or `~/.claude/plans/*.md`) citation in
    `prompt`, normalized to the repo-relative forward-slash spelling downstream
    `Path(plan_path).stem` assumes. `None` when the prompt cites none.

    Separator normalization is split rather than applied wholesale: the matched
    PREFIX's separators are provably separators (this module's own regex matched
    them as its separator class), while a literal backslash in the filename
    REMAINDER is a legal character on POSIX and is left alone there.
    """
    if not prompt:
        return None
    for match in _PLAN_PATH_RE.finditer(prompt):
        start = match.start(1)
        token_start = start
        while token_start > 0 and not prompt[token_start - 1].isspace():
            token_start -= 1
        if "://" in prompt[token_start:start]:
            continue
        matched = match.group(1)
        prefix_match = _PREFIX_RE.match(matched)
        if not prefix_match:
            return matched
        boundary = prefix_match.end()
        prefix = PureWindowsPath(matched[:boundary]).as_posix() + "/"
        remainder = matched[boundary:]
        if sys.platform.startswith("win"):
            remainder = PureWindowsPath(remainder).as_posix()
        return prefix + remainder
    return None


def _repo_root(cwd: Optional[str]) -> Optional[Path]:
    """Zero-spawn parent walk for a `.git` entry from `cwd` (a directory in an
    ordinary clone, a FILE in a linked worktree). `None` when unresolvable --
    same contract as `_git_root_walk.git_root_walk`, which cannot be reused
    here because it walks from the process cwd rather than a supplied start."""
    try:
        start = Path(cwd).resolve() if cwd else Path.cwd().resolve()
        for candidate in (start, *start.parents):
            if (candidate / ".git").exists():
                return candidate
    except Exception:
        pass
    return None


def _queue_path(session_id: str, cwd: Optional[str]) -> Optional[Path]:
    root = _repo_root(cwd)
    if root is None or not session_id:
        return None
    # session_id is a harness-minted uuid; reject anything separator-shaped
    # rather than letting a crafted value escape subagent-share/.
    if not re.fullmatch(r"[A-Za-z0-9._-]+", session_id) or session_id in {".", ".."}:
        return None
    return root / "state" / "subagent-share" / session_id / QUEUE_LEAF


def record_plan_path(
    session_id: str, subagent_type: str, plan_path: str, cwd: Optional[str]
) -> bool:
    """Append one `(subagent_type, plan_path)` row for `session_id`. Returns
    whether the row landed; every failure leg returns False and writes nothing."""
    if subagent_type not in PLAN_DERIVABLE_TYPES or not plan_path:
        return False
    path = _queue_path(session_id, cwd)
    if path is None:
        return False
    row = {
        "subagent_type": subagent_type,
        "plan_path": plan_path,
        "ts": int(time.time()),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = _read_rows(path)
        existing.append(row)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            for entry in existing[-_MAX_ROWS:]:
                handle.write(json.dumps(entry) + "\n")
    except Exception:
        return False
    return True


def _read_rows(path: Path) -> list:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []
    rows = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except Exception:
            continue
        if isinstance(entry, dict):
            rows.append(entry)
    return rows


def read_plan_path(
    session_id: str, subagent_type: str, cwd: Optional[str]
) -> Optional[str]:
    """Newest live `plan_path` recorded for `subagent_type` in `session_id`, or
    `None`. Non-consuming by design (module docstring) -- the caller may read
    the same row twice and the resulting provisioning is idempotent."""
    if subagent_type not in PLAN_DERIVABLE_TYPES:
        return None
    path = _queue_path(session_id, cwd)
    if path is None:
        return None
    now = int(time.time())
    for entry in reversed(_read_rows(path)):
        if entry.get("subagent_type") != subagent_type:
            continue
        ts = entry.get("ts")
        if not isinstance(ts, int) or now - ts > _ROW_TTL_SECONDS:
            continue
        plan_path = entry.get("plan_path")
        if isinstance(plan_path, str) and plan_path:
            return plan_path
    return None
