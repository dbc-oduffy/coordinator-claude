"""Enumerate and classify this repo's live peer sessions (roadmap `gem-01`,
baton `gem-13`).

PURPOSE. This is the Group EM read pass: it lists the other sessions running
against this repo, classifies each with `gem-11`'s `receiver-state.json`
reader where that reader has a verdict, falls back to `claude agents --json`
status plus a bounded transcript-tail read otherwise, and returns a bounded
candidate roster for a human to look at. It is the composition point named in
this stub's own frontmatter -- gem-11's reader meets `claude agents --json`
under one presentation surface.

The reader is preferred per peer; the fallback leg fires only on the
reader's `UNAVAILABLE` verdict. A `PRODUCING` verdict, however it was
reached, is never a candidate; only `PAUSED` (reader) or `PAUSED:turn-ended`
(fallback) is -- the same rule on both legs. See
`docs/decisions/DR-group-em-read-pass-carrier.md` (which carrier this module
reads) and `docs/decisions/DR-group-em-roster-excludes-mid-work-peers.md`
(the candidate-predicate ruling) for the record of how each was decided.

NEGATIVE SPEC -- what this module deliberately does NOT do:

- **No shouldn't-be adjudication.** The output is a read-only candidate list.
  Nothing here judges whether a paused peer "should" have kept moving -- that
  population is unmeasurable by PM ruling (`gem-2026-08-14/OVERVIEW.md` §
  "Declare shouldn't-be, never infer it") and out of scope for this stub.
- **No send, no nudge, no write to any peer's state.** This module only reads
  `claude agents --json`, `gem-11`'s reader, and (bounded) transcript tails.
  Auto-send/nudge is `gem-14`, gated separately.
- **No CPU-delta leg.** Per Resolution 1 clause 4, no CPU-band signal is read
  or used anywhere in this module, gated or otherwise -- the CPU-band
  separation finding is RETRACTED (adjacent bands, 0.01 cpu-s apart).
- **No dependence on `state`/`waitingFor`.** Both fields are background-agent
  -only in the measured corpus (present on 0 of 29 interactive sessions); no
  classification path here reads either key.
- **No caching or batching of the enumeration read.** `fetch_live_agents`
  re-invokes `claude agents --json` on every call; nothing here snapshots
  peers across a presentation.
- **The caller never appears in its own roster.** `enumerate_repo_peers`
  drops the caller's own `sessionId` before classification runs, so the
  caller's own absence can never be reported as a peer event.
- **No whole-transcript reads.** `read_transcript_tail` seeks from the end
  and reads a bounded byte window -- never the full file. Some peer
  transcripts are large and ~20 peer sessions can be live on this machine at
  once; parsing whole transcripts here would not scale.

CLASSIFICATION LADDER (see `## Specification` items 1-4 and AC1/AC3/AC6 in the
gem-13 stub for the source measurements and the binding contract):

- The reader (`gem-11`) is tried first, per peer. Only when it reports
  `UNAVAILABLE` for THIS peer does the fallback leg run at all -- see the
  "per-peer, not repo-global" note on `classify_peer` below.
- `busy` is a strong positive signal on its own: precision 470/472 = 99.58%,
  recall 470/491 = 95.72% over the full capture. Mapped straight to
  `STATE_PRODUCING`, never a candidate -- no transcript read needed. A
  mid-work peer is never presented on this leg, matching the reader leg (see
  `DR-group-em-roster-excludes-mid-work-peers.md`).
- `idle` is NOT a terminal verdict (per AC1, the reader's fallback covers
  "`claude agents --json` + transcript-tail signals" as one combined leg).
  `idle`'s own reliability is genuinely split -- P(quiet | idle), among
  unambiguous outcomes, is 842/863 = 97.57%; over *all* idle transitions
  (unambiguous plus ambiguous-band) it is 842/1192 = 70.6% -- so an `idle`
  peer's transcript tail is read (bounded, see above) to resolve which side
  of that split it is on: `STATE_TURN_ENDED` (the only candidate outcome on
  this leg) if the tail's last recognised marker is a closed turn, or
  `STATE_PRODUCING` (never a candidate) if the
  tail shows live conversational activity despite a stale `idle` status
  (AC1's "status timestamp is unbounded-stale"), or `STATE_UNKNOWN` if the
  tail is empty, unreadable, or carries no line type this module recognises
  -- the line-type vocabulary is open per the stub, and an unrecognised tail
  is `UNKNOWN`, never guessed into a paused-like state (AC6).
- Any other harness status string classifies straight to `STATE_UNKNOWN` --
  first-class and expected, never folded into a paused-like state.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime
from typing import Any, Callable, Mapping, Optional

from coordinator.lib import receiver_state_reader as rsr

#: The peer is actively producing -- either `status == "busy"` directly, or
#: an `idle` peer whose transcript tail shows live conversational activity.
STATE_PRODUCING = "PRODUCING"

#: The peer's last recognised transcript-tail marker is a closed turn. A
#: candidate. Serialized as `state="PAUSED", reason="turn-ended"` on both
#: legs (see `classify_peer`/`classify_transcript_tail`) -- this constant
#: names the internal classification outcome, not the wire shape.
STATE_TURN_ENDED = "PAUSED:turn-ended"

#: The reader-leg spelling of a paused verdict -- kept distinct from
#: `STATE_TURN_ENDED` (the fallback-leg internal spelling) so both legs can
#: be normalised to the same `{state, reason}` shape at serialization time.
STATE_PAUSED = "PAUSED"

#: Neither the reader, nor the status leg, nor the transcript tail could
#: place this peer. First-class and expected -- never a paused-like guess.
STATE_UNKNOWN = "UNKNOWN"

_CLAUDE_AGENTS_CMD = ["claude", "agents", "--json"]

#: Bounded transcript-tail read window (AC-adjacent -- see the "No
#: whole-transcript reads" negative-spec entry above).
TAIL_MAX_LINES = 40
TAIL_MAX_BYTES = 65536

_PATH_SEP_RE = re.compile(r"[/\\:]")


def caller_session_id(env: Optional[Mapping[str, str]] = None) -> Optional[str]:
    """This session's own id, so it can be excluded from its own roster.

    Never resolved from `claude agents --json` itself -- that would require
    guessing which entry is "us" from shape alone. The harness exports it
    directly.
    """
    env = os.environ if env is None else env
    return env.get("CLAUDE_CODE_SESSION_ID")


def fetch_live_agents(
    run: Callable[..., "subprocess.CompletedProcess[str]"] = subprocess.run,
) -> list[dict[str, Any]]:
    """Re-invoke `claude agents --json` fresh. Never cache this list.

    Returns `[]` on any parse or invocation failure -- a read pass with no
    peers to show is a legitimate, quiet outcome, not a raised exception.
    """
    try:
        result = run(
            _CLAUDE_AGENTS_CMD,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []
    try:
        data = json.loads(result.stdout)
    except (ValueError, AttributeError):
        return []
    return data if isinstance(data, list) else []


def _same_repo(cwd: Any, repo_root: str) -> bool:
    if not isinstance(cwd, str) or not cwd:
        return False
    return os.path.normcase(os.path.normpath(cwd)) == os.path.normcase(
        os.path.normpath(repo_root)
    )


def enumerate_repo_peers(
    agents: list[dict[str, Any]],
    repo_root: str,
    exclude_session_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Filter the raw enumeration to this repo's peers, caller excluded.

    `exclude_session_id` is the only mechanism that removes an entry from the
    roster -- there is no "shouldn't be here" inference, only a repo-cwd
    match plus the caller's own exclusion.
    """
    peers = []
    for agent in agents:
        session_id = agent.get("sessionId")
        if exclude_session_id is not None and session_id == exclude_session_id:
            continue
        if not _same_repo(agent.get("cwd"), repo_root):
            continue
        peers.append(agent)
    return peers


def transcript_path_for(session_id: str, cwd: str) -> str:
    """The on-disk transcript path the harness itself writes to for a peer.

    Convention observed under `~/.claude/projects/<encoded-cwd>/<session_id>.jsonl`:
    every path separator and drive-letter colon in `cwd` is replaced with `-`.
    Not a public contract -- if this ever drifts, `read_transcript_tail`
    fails closed (missing file) to `STATE_UNKNOWN`, never a crash.
    """
    projects_root = os.path.join(os.path.expanduser("~"), ".claude", "projects")
    encoded_cwd = _PATH_SEP_RE.sub("-", cwd)
    return os.path.join(projects_root, encoded_cwd, f"{session_id}.jsonl")


def read_transcript_tail(
    path: str,
    max_lines: int = TAIL_MAX_LINES,
    max_bytes: int = TAIL_MAX_BYTES,
) -> list[str]:
    """Read only the trailing `max_bytes` of `path`, bounded to `max_lines`.

    Never reads a whole transcript (see module negative spec). Returns `[]`
    on any I/O failure -- a missing or unreadable transcript is `UNKNOWN`
    upstream, never an exception.
    """
    try:
        size = os.path.getsize(path)
    except OSError:
        return []
    if size <= 0:
        return []
    read_size = min(size, max_bytes)
    try:
        with open(path, "rb") as handle:
            handle.seek(-read_size, os.SEEK_END)
            raw = handle.read()
    except OSError:
        return []
    text = raw.decode("utf-8", errors="ignore")
    lines = [line for line in text.splitlines() if line.strip()]
    return lines[-max_lines:]


def classify_transcript_tail(lines: list[str]) -> str:
    """Resolve a bounded transcript tail to `PRODUCING`, `PAUSED:turn-ended`,
    or `UNKNOWN`.

    The line-type vocabulary is open (the stub's own framing) -- this walks
    the tail newest-first and returns on the first line whose `type` (and,
    for the turn-ended marker, `subtype`) this module recognises, skipping
    unrelated noise line-types (attachments, UI metadata, etc.) in between.
    An unrecognised tail -- empty, unparseable, or containing no recognised
    marker within the bounded window -- is `UNKNOWN`, never guessed into
    `PRODUCING` or `PAUSED:turn-ended`.
    """
    for line in reversed(lines):
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if not isinstance(record, dict):
            continue
        record_type = record.get("type")
        if record_type == "system" and record.get("subtype") == "turn_duration":
            return STATE_TURN_ENDED
        if record_type in ("assistant", "user"):
            return STATE_PRODUCING
    return STATE_UNKNOWN


def classify_fallback_status(
    status: Any,
    tail_lines: Optional[list[str]] = None,
) -> tuple[str, str]:
    """Map a raw harness `status` string (plus, for `idle`, a transcript
    tail) to the fallback ladder's `(state, reason)`.

    Reads `status` and the injected tail only -- never `state`/`waitingFor`
    (background-agent-only, see module docstring) and never a CPU-delta
    (Resolution 1 clause 4).
    """
    if status == "busy":
        return STATE_PRODUCING, "status-busy"
    if status == "idle":
        tail_state = classify_transcript_tail(tail_lines or [])
        if tail_state == STATE_PRODUCING:
            return STATE_PRODUCING, "tail-live-activity"
        if tail_state == STATE_TURN_ENDED:
            return STATE_PAUSED, "tail-turn-duration"
        return STATE_UNKNOWN, "tail-unresolved"
    return STATE_UNKNOWN, "unrecognized-status"


def classify_peer(
    repo_root: str,
    peer: dict[str, Any],
    now: Optional[datetime] = None,
    read_tail: Optional[Callable[[str, str], list[str]]] = None,
) -> dict[str, Any]:
    """One peer in, one verdict out -- the preference check itself.

    Calls `gem-11`'s reader first. Only when that reader reports
    `UNAVAILABLE` for THIS peer (no verdict to give) does this fall back to
    the `claude agents --json` status leg -- deliberately per-peer, not
    gated once on any
    repo-wide carrier-presence check: the carrier tree can exist repo-wide
    while most individual peers still have no record of their own, and must
    still fall through.

    A peer with no `sessionId` at all cannot be keyed against either the
    reader or a transcript, and is `UNKNOWN` rather than reaching either.
    """
    session_id = peer.get("sessionId")
    if not isinstance(session_id, str) or not session_id:
        return {
            "session_id": session_id,
            "source": "fallback",
            "state": STATE_UNKNOWN,
            "reason": "no-session-id",
            "candidate": False,
        }

    reader_verdict = rsr.read_receiver_state(repo_root, session_id, now=now)
    if reader_verdict["verdict"] != rsr.VERDICT_UNAVAILABLE:
        return {
            "session_id": session_id,
            "source": "reader",
            "state": reader_verdict["verdict"],
            "reason": reader_verdict["reason"],
            "candidate": reader_verdict["verdict"] == STATE_PAUSED,
        }

    status = peer.get("status")
    tail_lines: list[str] = []
    if status == "idle":
        cwd = peer.get("cwd") or repo_root
        if read_tail is not None:
            tail_lines = read_tail(session_id, cwd)
        else:
            tail_lines = read_transcript_tail(transcript_path_for(session_id, cwd))

    state, reason = classify_fallback_status(status, tail_lines)

    return {
        "session_id": session_id,
        "source": "fallback",
        "state": state,
        "reason": reason,
        "candidate": state == STATE_PAUSED,
    }


def build_candidate_roster(
    repo_root: str,
    agents: Optional[list[dict[str, Any]]] = None,
    caller_session_id_value: Optional[str] = None,
    now: Optional[datetime] = None,
    run: Callable[..., "subprocess.CompletedProcess[str]"] = subprocess.run,
    read_tail: Optional[Callable[[str, str], list[str]]] = None,
) -> list[dict[str, Any]]:
    """Present the bounded, paused-only candidate population.

    Read-only end to end: enumerates via `fetch_live_agents` (or the injected
    `agents`, for tests), classifies each surviving peer, and returns only
    the verdicts marked `candidate`. `STATE_PRODUCING` and `STATE_UNKNOWN`
    peers are never included here, and never folded into each other -- this
    is a candidate list for a human to adjudicate, not a filtered verdict
    about who "shouldn't" be paused. See
    `docs/decisions/DR-group-em-roster-excludes-mid-work-peers.md` for why a
    mid-work peer is excluded identically on both classification legs.
    """
    if agents is None:
        agents = fetch_live_agents(run=run)
    if caller_session_id_value is None:
        caller_session_id_value = caller_session_id()

    peers = enumerate_repo_peers(agents, repo_root, caller_session_id_value)
    verdicts = [
        classify_peer(repo_root, peer, now=now, read_tail=read_tail) for peer in peers
    ]
    return [verdict for verdict in verdicts if verdict["candidate"]]
