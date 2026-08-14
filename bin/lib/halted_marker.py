"""halted_marker — the repo-local `state/cockpit-emission.HALTED.md` writer.

Purpose: `state/cockpit-emission.json` carries no in-band signal that it stopped
advancing (the in-artifact halt field is blocked behind DoE's
`additionalProperties: false` envelope schema gate), so a co-located filesystem
marker carries the signal instead. This module owns that marker's content and its
write/refresh/remove operations for every writer in `coordinator/bin/`.

Two writers, deliberately:

- `emit-cadence.py` — writes/refreshes on each benign gate-off skip, removes when
  the gate is ON. The cadence-side lifecycle (DR-287).
- `emit-cockpit-snapshot.py` — refreshes after a successful on-demand emission to
  the canonical path. Without this the heading keeps reading "do not read as
  current" over a just-emitted artifact, and the stamped `emitted_at` lags the
  bytes beside it until the next ceremony close happens to re-sync. On-demand
  emission is the standing offer made to example-cockpit-repo and project-rag under
  DR-287; that offer is what turns the lag from theoretical into a thing a
  consumer's pre-`store:build` bridge would actually hit.

Negative-spec: nothing here raises past its own boundary. Every operation is
best-effort and contained — a marker failure must never turn a ceremony skip, or
a live emission, into a failure.

Spec backlink: docs/decisions/DR-287-emit-cadence-halted-pending-consumer-pur.md
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_HALT_DATE = "2026-08-10"
_HALT_REASON = (
    "PM ruling (DR-287): `emit.cadence` was firing 24-46x/day fleet-wide with "
    "~64% timeout rate and no downstream consumer required per-ceremony freshness."
)
_DR_POINTER = "docs/decisions/DR-287-emit-cadence-halted-pending-consumer-pur.md (claude-klabauter)"
_REENABLE_VAR = "COORDINATOR_EMISSION_CADENCE_LIVE=1"
_EMITTED_AT_RE = re.compile(r'"emitted_at"\s*:\s*"([^"]*)"')
MARKER_READ_HEAD_BYTES = 4096


def extract_emitted_at(artifact_path: Path) -> str | None:
    """Cheaply pull `emitted_at` out of a (possibly ~23MB) cockpit-emission.json
    without reading it whole — `emitted_at` sits in the top-level envelope, well
    within the first few KB, so a bounded head-read + regex suffices."""
    try:
        with open(artifact_path, "rb") as f:
            head_bytes = f.read(MARKER_READ_HEAD_BYTES)
    except OSError:
        return None
    head = head_bytes.decode("utf-8", errors="replace")
    match = _EMITTED_AT_RE.search(head)
    return match.group(1) if match else None


def build_halted_marker_content(emitted_at: str | None) -> str:
    emitted_line = (
        emitted_at
        if emitted_at
        else "unknown (state/cockpit-emission.json absent or unreadable at write time)"
    )
    return (
        "# state/cockpit-emission.json is HALTED — do not read as current\n\n"
        f"**Halted:** {_HALT_DATE}, {_HALT_REASON}\n\n"
        f"**Re-enable:** set `{_REENABLE_VAR}` in the environment the ceremony "
        "directives run under.\n\n"
        f"**Reference:** {_DR_POINTER}\n\n"
        "**Local artifact `emitted_at` at halt-marker-write time:** "
        f"`{emitted_line}`\n\n"
        "**On-demand emission does not clear this marker, it re-stamps it.** "
        "`coordinator/bin/emit-cockpit-snapshot.py` refreshes the line above "
        "after a successful emission to the canonical path, so the stamp tracks "
        "the bytes beside it. The heading still holds: the artifact is not "
        "advancing on a cadence, it advanced because somebody asked.\n\n"
        "**Scope note:** this marker is repo-local, self-stamped by "
        "`coordinator/bin/emit-cadence.py` on each benign gate-off skip in "
        "*this* repo only — it is written/refreshed here and does NOT travel "
        "with a `git show <sha>:state/cockpit-emission.json` blob (a checked-out "
        "historical commit will not carry this file's sibling marker). This is "
        "exactly the limitation that motivated requesting an in-artifact halt "
        "field, which is blocked behind DoE's `additionalProperties: false` "
        "envelope schema gate; until that lands, this filesystem marker is the "
        "weaker signal.\n"
    )


def sync_halted_marker(repo_root: str) -> None:
    """Ensure `<repo_root>/state/cockpit-emission.HALTED.md` exists and is
    accurate. No-op if `state/` doesn't exist (never creates it), no-op if the
    marker already holds the correct content (no mtime churn on a shared tree),
    and swallows every error — a failure here degrades silently, it never
    propagates."""
    try:
        state_dir = Path(repo_root) / "state"
        if not state_dir.is_dir():
            return
        marker_path = state_dir / "cockpit-emission.HALTED.md"
        artifact_path = state_dir / "cockpit-emission.json"
        emitted_at = extract_emitted_at(artifact_path) if artifact_path.is_file() else None
        content = build_halted_marker_content(emitted_at)
        if marker_path.is_file():
            try:
                if marker_path.read_text(encoding="utf-8") == content:
                    return
            except OSError:
                pass
        tmp_path = marker_path.with_name(marker_path.name + f".tmp-{os.getpid()}")
        try:
            tmp_path.write_text(content, encoding="utf-8")
            os.replace(tmp_path, marker_path)
        finally:
            # os.replace consumed tmp_path on success; a survivor means the
            # swap failed, and an uncleaned one becomes untracked litter in
            # state/ that trips the next session's dirty-tree gate.
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
    except Exception:
        return


def remove_halted_marker(repo_root: str) -> None:
    """Delete a stale `state/cockpit-emission.HALTED.md` when the gate is ON —
    a marker beside a live artifact is the same lie in the other direction.
    Swallows every error; never propagates."""
    try:
        marker_path = Path(repo_root) / "state" / "cockpit-emission.HALTED.md"
        if marker_path.is_file():
            marker_path.unlink()
    except Exception:
        return
