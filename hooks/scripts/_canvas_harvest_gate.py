"""Disk-state check for claude.ai artifact citations: a cited canvas needs a complete,
cited, fresh harvest record. Contract: coordinator/docs/wiki/schema-and-validation-contracts/canvas-harvest-record.md.

Stdlib only; reads local files and calls nothing over the network. Both legs import it:
`check(text, repo_root)` is the write leg, `check(text, repo_root, session_id=...)` the dispatch leg.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import NamedTuple, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import _message_envelope  # noqa: E402

WIKI_ANCHOR = "coordinator/docs/wiki/schema-and-validation-contracts/canvas-harvest-record.md"
SCHEMA_ID = "canvas-harvest-record/1"

_URL_RE = re.compile(r"claude\.ai/artifact/([A-Za-z0-9_-]+)")
_RECORD_PATH_RE = re.compile(r"(?:[\w.\-]+[/\\])*harvest[/\\]harvest\.json")
_SETTLED_HEADING = "## Thread-settled behaviour"
_ITEM_RE = re.compile(r"^\s*[-*]\s+(.*)$")
_TAG_RE = re.compile(r"^\[(?:thread:([^\]\s]+)|(no-threads))\]")


class Refusal(NamedTuple):
    url: str
    code: str
    message: str


def artifact_urls(text: str) -> list:
    """Every concrete artifact URL in `text`, in order; the `<id>` placeholder never matches."""
    return [m.group(0) for m in _URL_RE.finditer(text)]


def new_citations(before: str, after: str) -> list:
    """Each URL occurring more often in `after` than in `before`, once, in first-seen order."""
    return list(Counter(artifact_urls(after)) - Counter(artifact_urls(before)))


_REHARVEST = "Re-harvest through the engine op."

# code -> (what the text did, remedy)
_REASONS = {
    "record-not-cited": (
        "cites a canvas but names no record for it",
        "Harvest the canvas and cite its harvest/harvest.json path in this text.",
    ),
    "no-harvest-record": (
        "names a harvest record that does not exist",
        "Harvest the canvas through the engine op.",
    ),
    "record-unparseable": (
        "names a harvest record that is unparseable or incomplete",
        _REHARVEST,
    ),
    "canvas-unreadable": (
        "cites a canvas the probe could not read",
        "Republish from the committed files under the current login, or drop the URL "
        "and cite the committed source.",
    ),
    "drift-unchecked": (
        "cites a canvas owned by another login; the committed record is admitted with "
        "version and comment drift unchecked",
        "Swap back to that login and re-probe to check drift.",
    ),
    "frames-or-threads-missing": (
        "names a record with a missing or altered frame or thread file",
        _REHARVEST,
    ),
    "settled-empty": (
        "names a record whose SETTLED.md has no entries",
        "Settle the threads in SETTLED.md.",
    ),
    "settled-uncited": (
        "names a record whose SETTLED.md has an uncited entry",
        "Cite a real thread id for every SETTLED.md entry.",
    ),
    "probe-missing": (
        "names a record with no probe from this session",
        "Re-probe the canvas in this session.",
    ),
    "version-missing": ("names a record with no artifact version", _REHARVEST),
    "version-mismatch": (
        "names a record whose canvas version moved since harvest",
        _REHARVEST,
    ),
    "comment-drift": (
        "names a record whose comment threads moved since harvest",
        "Re-harvest, then update SETTLED.md.",
    ),
}


class Advisory(NamedTuple):
    url: str
    code: str
    message: str


def _message(code: str, detail: str) -> str:
    what, remedy = _REASONS[code]
    prose = f"Canvas {code}: {what}{detail}. {remedy}"
    if len(prose) > _message_envelope.CEILING:
        prose = prose[: _message_envelope.CEILING - 3].rstrip() + "..."
    return _message_envelope.render(_message_envelope.compose(prose, anchor=WIKI_ANCHOR))


def _refusal(url: str, code: str, detail: str = "") -> Refusal:
    return Refusal(url, code, _message(code, detail))


def _is_account(value) -> bool:
    return isinstance(value, str) and bool(value)


def _parse_time(value) -> datetime:
    """Timezone-aware datetime from a `Z` or offset ISO-8601 string; ValueError otherwise."""
    if not isinstance(value, str):
        raise ValueError("time is not a string")
    parsed = datetime.fromisoformat(value.strip())
    if parsed.tzinfo is None:
        raise ValueError("time carries no timezone")
    return parsed


def _validate(record) -> bool:
    """True when `record` carries every required field other than the versions, times parsed."""
    try:
        if record["schema"] != SCHEMA_ID:
            return False
        artifact, harvest = record["artifact"], record["harvest"]
        for key in ("url", "id", "title", "type"):
            if not isinstance(artifact[key], str):
                return False
        _parse_time(harvest["harvested_at"])
        latest = harvest["latest_comment_at"]
        if latest is not None:
            _parse_time(latest)
        if not isinstance(harvest["thread_ids"], list):
            return False
        if not all(isinstance(t, str) for t in harvest["thread_ids"]):
            return False
        frames = harvest["frames"]
        if not isinstance(frames, list):
            return False
        for frame in frames:
            if not isinstance(frame["path"], str) or not isinstance(frame["sha256"], str):
                return False
        if harvest.get("account") is not None and not isinstance(harvest["account"], str):
            return False
        probe = record.get("probe")
        if probe is not None:
            if probe.get("account") is not None and not isinstance(probe["account"], str):
                return False
            if not isinstance(probe.get("record_committed", False), bool):
                return False
            _parse_time(probe["probed_at"])
            if not isinstance(probe["session_id"], str) or not isinstance(probe["readable"], bool):
                return False
            if probe["unreadable_reason"] is not None and not isinstance(
                probe["unreadable_reason"], str
            ):
                return False
            if not isinstance(probe["thread_ids"], list) or not all(
                isinstance(t, str) for t in probe["thread_ids"]
            ):
                return False
            if probe["latest_comment_at"] is not None:
                _parse_time(probe["latest_comment_at"])
    except (KeyError, TypeError, ValueError, AttributeError):
        return False
    return True


def _resolve(repo_root: Path, cited: str) -> Optional[Path]:
    """The cited repo-relative path under `repo_root`, or None when it escapes the root."""
    root = Path(repo_root).resolve()
    target = (root / cited.replace("\\", "/")).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return None
    return target


def _select_record(text: str, repo_root: Path, artifact_id: str):
    """(record_path, record) for the candidate carrying `artifact_id`, else (None, code)."""
    saw_missing = saw_unparseable = False
    for cited in dict.fromkeys(m.group(0) for m in _RECORD_PATH_RE.finditer(text)):
        path = _resolve(repo_root, cited)
        if path is None or not path.is_file():
            saw_missing = True
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            saw_unparseable = True
            continue
        if not isinstance(record, dict):
            saw_unparseable = True
            continue
        artifact = record.get("artifact")
        if isinstance(artifact, dict) and artifact.get("id") == artifact_id:
            return path, record
    if saw_missing:
        return None, "no-harvest-record"
    if saw_unparseable:
        return None, "record-unparseable"
    return None, "record-not-cited"


def _frames_or_threads_ok(record_dir: Path, harvest: dict) -> bool:
    frames_dir = (record_dir / "frames").resolve()
    for frame in harvest["frames"]:
        target = (frames_dir / frame["path"].replace("\\", "/")).resolve()
        try:
            target.relative_to(frames_dir)
        except ValueError:
            return False
        if not target.is_file():
            return False
        try:
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
        except OSError:
            return False
        if digest != frame["sha256"]:
            return False
    for thread_id in harvest["thread_ids"]:
        if not thread_id or "/" in thread_id or "\\" in thread_id or thread_id in (".", ".."):
            return False
        if not (record_dir / "threads" / f"{thread_id}.json").is_file():
            return False
    return True


def _settled_items(record_dir: Path) -> Optional[list]:
    """List-item texts in SETTLED.md's section; None when the file or section is absent."""
    try:
        lines = (record_dir / "SETTLED.md").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    items: list = []
    in_section = in_fence = False
    found = False
    for line in lines:
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if line.startswith("## "):
            in_section = line.strip() == _SETTLED_HEADING
            found = found or in_section
            continue
        if in_section:
            match = _ITEM_RE.match(line)
            if match:
                items.append(match.group(1).strip())
    return items if found else None


def _settled_code(record_dir: Path, thread_ids: list) -> Optional[str]:
    items = _settled_items(record_dir)
    if not items:
        return "settled-empty"
    members = set(thread_ids)
    for item in items:
        tag = _TAG_RE.match(item)
        if tag is None:
            return "settled-uncited"
        if tag.group(2):
            if thread_ids:
                return "settled-uncited"
        elif tag.group(1) not in members:
            return "settled-uncited"
    return None


def _same_time(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return _parse_time(a) == _parse_time(b)


def _judge(url: str, text: str, repo_root: Path, session_id: Optional[str]):
    """A `Refusal`, an `Advisory` (admitted, drift unchecked), or None (admitted)."""
    artifact_id = url.rsplit("/", 1)[1]
    path, selected = _select_record(text, repo_root, artifact_id)
    if path is None:
        return _refusal(url, selected)
    record = selected
    if not _validate(record):
        return _refusal(url, "record-unparseable")
    harvest, probe = record["harvest"], record.get("probe")
    dispatch = session_id is not None

    owner = harvest.get("account")
    unchecked = False
    if probe is not None and probe["readable"] is False:
        reason = probe.get("unreadable_reason") or "unknown"
        other = (
            reason == "other-account"
            and _is_account(owner)
            and _is_account(probe.get("account"))
            and owner != probe["account"]
        )
        if not (other and probe.get("record_committed") is True):
            detail = f" ({reason})"
            if _is_account(owner):
                detail += f"; harvested under {owner}, swap back to that login and re-probe"
                if other:
                    detail += " and commit the record"
            return _refusal(url, "canvas-unreadable", detail)
        unchecked = True
    if not _frames_or_threads_ok(path.parent, harvest):
        return _refusal(url, "frames-or-threads-missing")
    settled = _settled_code(path.parent, harvest["thread_ids"])
    if settled:
        return _refusal(url, settled)
    if dispatch and (probe is None or probe["session_id"] != session_id):
        return _refusal(url, "probe-missing")

    harvest_version = harvest.get("version")
    if not isinstance(harvest_version, str) or not harvest_version:
        return _refusal(url, "version-missing")
    if unchecked:
        return Advisory(url, "drift-unchecked", _message("drift-unchecked", f" (owner {owner})"))
    if dispatch:
        probe_version = probe.get("version")
        if not isinstance(probe_version, str) or not probe_version:
            return _refusal(url, "version-missing")
        if probe_version != harvest_version:
            return _refusal(url, "version-mismatch")
        if sorted(probe["thread_ids"]) != sorted(harvest["thread_ids"]) or not _same_time(
            probe["latest_comment_at"], harvest["latest_comment_at"]
        ):
            return _refusal(url, "comment-drift")
    return None


def judge(text: str, repo_root, *, session_id: Optional[str] = None) -> tuple:
    """(refusals, advisories) over each cited artifact URL, first reason in table order.

    An advisory is an admit: the canvas is owned by another login and drift is unchecked.
    `session_id=None` is the write leg: dispatch-only codes and the probe side of
    `version-missing` are skipped."""
    root = Path(repo_root)
    refusals: list = []
    advisories: list = []
    for url in dict.fromkeys(artifact_urls(text)):
        verdict = _judge(url, text, root, session_id)
        if isinstance(verdict, Refusal):
            refusals.append(verdict)
        elif verdict is not None:
            advisories.append(verdict)
    return refusals, advisories


def check(text: str, repo_root, *, session_id: Optional[str] = None) -> list:
    """The refusals of `judge`; the write leg's entry point."""
    return judge(text, repo_root, session_id=session_id)[0]
