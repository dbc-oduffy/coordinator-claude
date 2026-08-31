"""Reading a session's touched-file record, for the hooks that consume it.

PURPOSE. The engine cut over from `touched.txt` to `touch-record.jsonl`, and
two hooks kept opening the old name -- returning "no touches", which at their
call sites is indistinguishable from a session that touched nothing. This
module is the one reader, so a third consumer inherits the cutover rather
than repeating the miss.

SHARED, NOT DUPLICATED, DELIBERATELY. Per-hook independence (DR-047/DR-118)
governs hooks that merely resemble each other; it does not cover a helper
whose copies must agree to be CORRECT. These must: `_touch_lines` places every
new-file row before every legacy row regardless of which was written more
recently, and a caller reading list position as recency is wrong against it.
A rule that has to hold in two places at once has one home.

ORDERING. `_touch_lines` is new-file-first, which is a SOURCE order and not a
recency order. A caller asking "is X anywhere in this session's touches"
(`any()`) is unaffected. A caller taking the last match must instead ask the
new file alone and fall back to legacy only when the new file has nothing --
see `_newest_touched_sizing_path`.
"""

from __future__ import annotations

import json
import os


def _touch_path(line: str):
    line = line.strip()
    if not line:
        return None
    parts = line.split()
    if len(parts) >= 3 and parts[0] in ("T", "R"):
        return parts[-1]
    return line


def _touch_record_jsonl_paths(session_dir: str) -> list[str]:
    """Return repo-relative paths from `touch-record.jsonl`, append order
    (oldest first). Split out of `_touch_lines` so a caller that must
    reason about which FILE a match came from -- see
    `_newest_touched_sizing_path` -- can query the new-file source alone
    without re-deriving this parse."""
    paths: list[str] = []
    try:
        with open(
            os.path.join(session_dir, "touch-record.jsonl"),
            "r",
            encoding="utf-8",
            errors="replace",
        ) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                if not isinstance(row, dict):
                    continue
                rel = row.get("path")
                if isinstance(rel, str) and rel:
                    paths.append(rel)
    except OSError:
        pass
    return paths


def _touched_txt_paths(session_dir: str) -> list[str]:
    """Return repo-relative paths from the legacy `touched.txt`, append
    order (oldest first). Sibling split of `_touch_record_jsonl_paths` --
    see that function's docstring."""
    paths: list[str] = []
    try:
        with open(
            os.path.join(session_dir, "touched.txt"), "r", encoding="utf-8", errors="replace"
        ) as fh:
            for raw_line in fh:
                rel = _touch_path(raw_line)
                if rel:
                    paths.append(rel)
    except OSError:
        pass
    return paths


def _touch_lines(git_dir: str, session_id: str) -> list[str]:
    """Return this session's touched repo-relative paths, new-file matches
    before legacy-file matches.

    THE ENGINE WRITES `touch-record.jsonl`, NOT `touched.txt`. The cutover
    landed engine-side and left this reader pointed at a filename nothing
    writes any more, so it opened nothing and returned "no touches" -- which
    is byte-identical, at this call site, to a session that genuinely touched
    nothing. An always-False precondition, the failure shape
    `an-always-false-precondition-looks-exactly-like-a-quiet-predicate`
    names: no error, no gap, no marker. Measured on this tree: 0 sessions
    with `touched.txt`, 10 with `touch-record.jsonl`.

    Both files are read, new first, and the results concatenated -- a session
    that predates the cutover keeps its history, and a reader deployed
    against an older engine keeps working. Each is independently optional;
    neither being present is a legitimate quiet answer.

    ORDERING CAVEAT -- this list is NOT globally chronological. Within each
    file, rows are append order (oldest first); across files, EVERY new-file
    row is placed before EVERY legacy-file row regardless of which was
    actually written more recently. A caller that only cares "is X anywhere
    in this session's touches" (e.g. `_sizing_exemption_applies`'s `any()`)
    is unaffected. A caller that treats list position as recency -- "last
    match wins" -- is NOT: use `_newest_touched_sizing_path` (or the same
    per-source-then-fallback pattern), never `_touch_lines` directly, for
    that purpose.

    Row shape (`touch-record.jsonl`): one JSON object per line carrying at
    least `{"verb": "T", "path": "<repo-relative>"}`. Unparseable lines and
    rows with no `path` are skipped -- a malformed row degrades this to
    fewer touches, never to a crash on an edit-path hook.
    """
    session_dir = os.path.join(git_dir, "coordinator-sessions", session_id)
    return _touch_record_jsonl_paths(session_dir) + _touched_txt_paths(session_dir)
