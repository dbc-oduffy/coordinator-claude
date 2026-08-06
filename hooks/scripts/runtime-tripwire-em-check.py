#!/usr/bin/env python3
"""PostToolUse(*) naked-Python direct port of the former bash EM-side check.

Purpose: Fires in the EM session. Self-throttled 5 min. Reads the EM's
         dispatched-agents.txt, identifies any running subagent past its
         model-specific runtime threshold, and emits an awareness
         additionalContext naming each overrun dispatch.

This is a SELF-CONTAINED naked-Python hook, not a claude-klabauter-op stub: no
Claude-klabauter op exists for this EM-side disk-bookkeeping check (grepped
coordinator_core/hooks + coordinator_core/ops for "dispatched-agents.txt",
"em-check", "wrap-requested" — only track_dispatched_agents.py [the WRITER
of dispatched-agents.txt] and postuse_advisory_dispatch.py [the AGENT-side
port of the former bash advisory hook, an entirely different script that fires
INSIDE the subagent and keeps in-memory-only bark-once state] came back;
neither implements this EM-side disk-sentinel + fire-log + wrap-requested.txt
artifact scan). Per the W5 straggler-port contract: port the logic directly
into a self-contained hook rather than inventing a new claude-klabauter op.

Spec backlink: docs/plans/2026-06-08-runtime-tripwire-background-executors.md § C3b
Wiki: docs/wiki/runtime-tripwire.md

This is the EM-side complement to the former bash advisory hook /
postuse-advisory-dispatch.py's _check_runtime_tripwire_sync (which fires
inside the subagent). Together they give both parties awareness; the agent
owns the wrap judgment, the EM holds authority (trust-but-verify).

Discriminator: if HOOK_INPUT.session_id IS found under any
  .git/coordinator-sessions/.agents/*/em-session-id.txt -> this is a subagent
  session; exit 0 and let the agent-side hook handle it. If NOT found -> this
  is the EM session; proceed.

IMPORTANT -- env-var discriminator is NOT used here: CLAUDE_CODE_SESSION_ID
inherits the dispatching EM's id inside subagents (confirmed:
claude-code-platform-gotchas.md:33-50, probe 2026-05-23). Only
HOOK_INPUT.session_id is the firing session's distinct id and is reliable as
the subagent-vs-EM discriminator.

Contract (mirrors the former bash oracle):
  stdin   -- PostToolUse JSON (session_id, tool_response.agentId, agent_id, ...)
  stdout  -- one hookSpecificOutput JSON envelope when >=1 dispatch is past
             threshold; NOTHING otherwise
  exit 0  -- ALWAYS, unconditionally, on every code path (advisory hook;
             must fail-open -- mirrors the bash oracle's `set -uo pipefail`
             with -e deliberately omitted + explicit `|| true` guards).

Simplification vs the bash oracle (documented, non-decisional): the fire-log
target directory uses an INLINE mirror of coordinator_state_root's Rule 5
(meta-repo check via realpath(git_root) == realpath(<claude-home>) -> claude-klabauter
root /state, else GIT_ROOT/state) rather than shelling out to the full
claude-home/coordinator-claude-klabauter-root resolver chain. This affects only WHERE
the best-effort calibration fire-log TSV row lands, never WHETHER/WHAT a
nudge fires -- the advisory/deny decision surface is byte-faithful.
resolve_subagent_identity is similarly reimplemented as a local pure
function (mirrors the retired bash identity-resolution logic byte-for-byte,
and is IDENTICAL to the one already ported into claude-klabauter's
postuse_advisory_dispatch.py::_resolve_subagent_identity) instead of
shelling out -- pure function, no filesystem I/O, so no fidelity loss.

Escape-hatch env vars (byte-faithful, all honoured exactly as in the bash
oracle):
  RUNTIME_TRIPWIRE_RESTAGE_SECONDS -- re-nudge delay after first fire (300)
  RUNTIME_TRIPWIRE_MAX_TRACK_MIN   -- max-age cap before a dispatch is
                                      considered too stale to track (90)
  RUNTIME_TRIPWIRE_OPUS_MIN        -- Opus/unknown-model threshold (25)
  RUNTIME_TRIPWIRE_SONNET_MIN      -- Sonnet threshold (12)
  RUNTIME_TRIPWIRE_HAIKU_MIN       -- Haiku threshold (10)
  COORDINATOR_SUPPRESS_DISPATCH_RESTATEMENT -- suppresses the
                                      once-per-session DISPATCH-DEFAULT-
                                      RESTATEMENT line below (DR-110;
                                      cadence retired to once-per-session
                                      by DR-123). Unlike the five vars
                                      above, this one is NOT a byte-faithful
                                      mirror of anything in the retired bash
                                      oracle -- the restatement is a
                                      2026-07-28 addition with no bash-era
                                      precedent, so there is no prior escape
                                      hatch this one reproduces.
  COORDINATOR_EM_REPORT_ALTITUDE_OFF -- disables the EM-REPORT-ALTITUDE
                                      surfacer below entirely (no claude-klabauter
                                      round-trip, no advisory text, ever).
                                      Also a 2026-07-30 addition with no
                                      bash-era precedent.

Negative-spec:
  - Does NOT block execution -- PostToolUse is advisory only.
  - Does NOT fire for a subagent-side session (early-exits to the agent-side
    hook's territory) -- see the two-path subagent-detect block below.
  - Does NOT re-nudge more than once per dispatch (bark-once + single
    +RESTAGE_SECONDS re-nudge, then permanent silence for that agentId).
  - Does NOT track a dispatch past MAX_TRACK_MINUTES (stale-dispatch cap).

Windows note: `git rev-parse` calls are wrapped with CREATE_NO_WINDOW to
suppress the console-popup flash, matching the pattern already used by
postuse_advisory_dispatch.py::_check_runtime_tripwire_sync.

AUTO-PUSH-MID-SESSION-DETECT (added 2026-07-20, folded onto this existing
seam rather than a new hook): this hook already fires on the highest-
frequency EM-side cadence available (Stop + UserPromptSubmit + one
PostToolUse matcher; see hooks.json) without a per-tool-call cost, and
already carries the fail-open + additionalContext-advisory plumbing this
detector needs -- so it is extended in place instead of adding a fifth
registration. See `_check_push_failures()` docstring for the full predicate,
cost analysis, and origin incident. Contract addition: stdout may now also
carry a push-failure advisory even when zero dispatched agents are being
tracked (previously this hook emitted nothing at all in that case).

Classification moved off this file (added 2026-08-06): this detector no
longer derives its own verdict from a single `git rev-list` count split into
two prose strings. The rare about-to-emit path now round-trips the engine op
`git.push_failure_verdict` (registered commit `f17ea2f78`), which classifies
the growth into one of five states -- `peer_staged`, `half_applied_merge`,
`simple_lag`, `resolved_since`, `indeterminate` -- and returns the evidence
this file renders each state's sentence from (`_push_failure_verdict`/
`_render_push_failure_verdict`, near `_check_push_failures`). This file is
the renderer; the engine owns the classification and its cross-repo
contract, per the memo trail at `state/memo-outbox/sent/
autopush-advisory-yes-build-the-verdict-op.md`. The engine round-trip is
fail-open: an unresolvable/unimportable/malformed response falls back to
this file's original two-string rendering (`_unpushed_commit_count`) rather
than going silent -- fail-open on the classifier, fail-toward-firing on the
answer.

ZERO-TOOL-USE-DETECT-SURFACE (Stage 2, added 2026-07-25; folded onto this
same UserPromptSubmit-gated seam rather than a new hook registration --
DEC-6, docs/plans/2026-07-25-zero-tool-use-detection.md): UserPromptSubmit
is the cheapest steady-state hot path in the hooks census -- one `python3`
spawn per human prompt. Registering a fresh script there would double that
to two, against coordinator.local.md's standing P0 that a non-default-
interpreter process spawn is a correctness/performance defect on the
Windows-primary fleet, not a cosmetic cost (the windows-tax-evidence spawn
census that ruling cites). The on-point precedent is IN THIS FILE:
`_check_push_failures()` (see its own docstring, above) already folds a
second, unrelated detector into this exact hook for the identical reason --
this part follows that precedent rather than re-deriving the argument.

Host event is UserPromptSubmit, not UserPromptExpansion: UserPromptExpansion
fires only on slash-command/skill expansion (and supports a command-name
matcher), so anchoring here instead would silently miss every ordinary
plain-text PM turn -- do not "optimize" this registration to
UserPromptExpansion later.

Cost ceiling, stated the same explicit way `_check_push_failures()` states
its own: the steady-state (nothing-unsurfaced) path is one small
cursor-file read, then one `os.path.getsize` stat call against Stage 1's
own durable store JSONL -- both unconditional on every `UserPromptSubmit`
fire -- with the claude-klabauter round-trip (no `coordinator_core` import, no
`dispatch_message` call) gated on that comparison's result: only if the
stat shows growth past this session's own surfaced-cursor does anything
past the two cheap local reads run. This matters because the registered timeout
on all three of this script's events is 5 seconds, not the UserPromptSubmit
harness default of 30s (`hooks.json:12,38,79,302` confirm "timeout": 5
identically across this script's entries), and python cold start alone is
~642ms on the reference Windows machine -- an unconditional engine
round-trip on every prompt in every session, most of which dispatch no
subagents at all, would eat into that budget for no reason on the
overwhelmingly common nothing-to-report path.

Integration fix, this pass (landed engine contract diverged from the
pass-3 draft in three ways -- see the three inline `INTEGRATION FIX` marks
below for each): (1) the store/cursor paths below now resolve the git
COMMON dir, not `<git_root>/.git`, via `_resolve_git_common_dir` (a
byte-identical copy of the same helper in
`subagent-zero-tool-use-detect.py` -- keep both in step, see that file's
module docstring); (2) the earlier redundant sibling sentinel this part
used to stat is gone -- it now stats Stage 1's own durable store JSONL
directly, which is the actual append-only signal; (3) the landed
`hooks.subagent_zero_tool_use` op has NO zero-gate (it appends a record for
EVERY verified tool_use_count, healthy agents included), and the landed
surface op returns ALL of this session's `kind == "zero-tool-use"` records
without filtering -- so this part now filters to `tool_use_count == 0`
itself before composing any advisory text (AC1: a missing/non-int count is
treated as NOT a detection, never as zero).

Contract addition: stdout may now also carry a zero-tool-use advisory,
composed alongside the runtime-tripwire nudge and/or the push-failure
advisory in the SAME additionalContext envelope -- never a separate write,
never stderr, never plain stdout. See docs/wiki/coordinator-tripwires.md
§ ZERO-TOOL-USE-DETECT for the full two-stage design and Stage 1
(`hooks/scripts/subagent-zero-tool-use-detect.py`, SubagentStop).

DISPATCH-DEFAULT-RESTATEMENT (added 2026-07-28, DR-110; retired to
once-per-session 2026-08-02, DR-123, docs/decisions/
DR-123-the-per-turn-dispatch-restatement-is-ret.md): folded onto this same
UserPromptSubmit-gated seam for the same reason ZERO-TOOL-USE-DETECT-SURFACE
was -- this hook is already the cheapest steady-state per-human-turn hot path
in the census, and a fresh registration would double that spawn cost.
Originally fired on every UserPromptSubmit at frequency parity with the
harness's own once-per-turn "do not call the Agent tool unless the user
requested it" directive (DR-110); that per-turn cadence also failed (see
`_DISPATCH_DEFAULT_LINE`'s own comment block, above its definition, for the
full history), so it now fires at most once per session, and never on the
session's first UserPromptSubmit.

Contract addition: stdout may now also carry the dispatch-default line on
UserPromptSubmit, composed in the SAME additionalContext envelope as every
other advisory this hook emits -- never a separate write, never stderr --
at most once per session (never on turn one; see `_dispatch_default_restatement`)
unless `COORDINATOR_SUPPRESS_DISPATCH_RESTATEMENT` is set (see the
escape-hatch env var inventory above).

EM-REPORT-ALTITUDE (added 2026-07-30; folded onto this same seam for the
same per-`python3`-spawn-count reason as every addition above -- see
AUTO-PUSH-MID-SESSION-DETECT / ZERO-TOOL-USE-DETECT-SURFACE): measures the
EM's own just-finished PM-facing reply against the word-budget and
lead-with-the-outcome contract in global-doctrine/CLAUDE.md
§ Communication Style, and reports back what the measurement found -- it
does not itself state or restate that contract, only names when a reply
appears to have missed it. Gated hard to `Stop`: a reply is only complete,
and only worth measuring, at the turn's own end -- `UserPromptSubmit` and
`PostToolUse:Agent` fire mid-turn or on an unrelated tool's return, where
there is no finished EM reply to measure yet.

Advisory only, never blocking, deliberately: this hook's whole contract is
additionalContext, never exit 2, and that is worth restating here
specifically. The naive alternative -- block the Stop on a long or
citation-heavy reply and force a rewrite -- hands the EM another turn in
which to write MORE, which is the exact defect this measures; a blocking
channel here would fight its own purpose rather than correct it.

Cost gate: before any claude-klabauter round-trip, a cheap local precondition
(`_em_report_altitude_precondition`) requires that the just-finished
reply's text is actually obtainable -- a non-empty `last_assistant_message`
on the payload, or a `transcript_path` that exists on disk right now.
Neither present means nothing can be measured, so this returns without
resolving claude-klabauter, importing `coordinator_core`, or round-tripping the
engine at all -- same shape as every other cheap-precondition-before-
engine-resolve check in this file (see `_zero_tool_use_local_evidence`).
Deliberately NOT a message-length prefilter, and do not add one later: the
measured corpus that motivated this detector had real citation-density
violations in replies of 10, 16 and 29 words, so a length gate would
silently exempt most of what this exists to catch.

Contract addition: stdout may now also carry an EM-report-altitude
advisory on `Stop`, composed in the SAME additionalContext envelope as
every other advisory this hook emits -- never a separate write, never
stderr. Escape hatch: `COORDINATOR_EM_REPORT_ALTITUDE_OFF` (see the
escape-hatch env var inventory above).

Fires at most once per session (added 2026-07-31): a session-scoped
sentinel (`<git COMMON dir>/coordinator-sessions/<session_id>/
em-report-altitude-nudged`, resolved via `_resolve_git_common_dir` --
portability fix, see that helper's docstring) caps this advisory to a
single emission per session, written only at the point a real message is
returned -- never on
a fail-open/no-advisory-this-time path. Same fix also absorbs this hook
being registered as a Stop hook on two delivery surfaces at once (a
separate, PM-tracked registration defect): the sentinel makes the second
same-Stop invocation a no-op the same way it silences a later Stop.

SUBAGENT-ARRIVAL-CHECK -- STOOD DOWN 2026-07-31 (PM ruling, reversible, not
a deletion). The overrun nudge this section describes no longer fires:
`_SUBAGENT_OVERRUN_TRIPWIRE_ENABLED` (declared above the imports) gates the
whole dispatch-tracking section of `main()` off, and `main()` now returns
early with only the three unrelated advisories (push-failure, zero-tool-
use, EM-report-altitude) still emitting. The prose below describing the
arrival-check design is preserved verbatim as the recoverable record; it
does not describe live behaviour until the constant is flipped back to
`True`. See that constant's own docstring for the measured basis and the
full restore recipe.

SUBAGENT-ARRIVAL-CHECK (added 2026-07-30, restoring what the retired
SUBAGENTSTOP TRIGGER-LOSS branch used to cover; UNKNOWN reclassified from
fire-worthy to suppressing on 2026-07-31 -- see below): every dispatch past
the max-age cap and the per-model runtime threshold used to flow straight
to a nudge below with no check that the agent was still actually running
-- a dispatch that had already returned (arrived) got nudged anyway. This
calls the engine op `hooks.subagent_arrival_check`
(`coordinator_core/hooks/subagent_arrival_check.py`) for exactly the row
about to be nudged, mirroring `_check_zero_tool_use_surface`'s
engine-resolve pattern rather than inventing a new one.

As of 2026-07-31 this oracle nudges ONLY on a confirmed `"running"`; both
`"arrived"` and `"unknown"` suppress. This is a deliberate reversal of the
2026-07-30 "fail toward firing" contract stated above and in
`_check_subagent_arrival`'s own docstring: a subagent transcript is not
durable (measured on this repo at 14 transcript files against 3,083
distinct agentIds in the audit log), so `"unknown"` is the overwhelmingly
common NO-INFORMATION case, not evidence of a live agent. Treating it as
fire-worthy meant this hook fired on essentially every completed dispatch
(diagnosed cross-repo, 2026-07-31; corroborated by `d75402345`'s own commit
message, which measured 681 false fires over 26 days across 6 distinct
agents against a 0.59% genuine stall rate before retiring the mechanism
this replaced). This arrival oracle -- consulted only for a row already
past the max-age cap, per-model threshold, and sentinel-state pre-gate
below -- is the ONLY completion/liveness signal this file consults. There
is deliberately no `agent-audit.jsonl` cross-check here (see the
NOT-A-COMPLETION-LOG note immediately below for why one was tried, and
removed again, on 2026-07-31). DR-047 boundary unchanged: `transcript_path`
and `agent_id` are passed to the op unopened -- this file never opens a
transcript or derives a subagent transcript path itself; that is the
engine's job.

NEAR-INERT-BY-DESIGN, AND TIME-BOXED (stated plainly so no future reader
mistakes silence for health). Because `"unknown"` is the overwhelmingly
common arrival state and `"unknown"` suppresses, this hook's overrun nudge
fires rarely today -- it is closer to off than to accurate. That is the
deliberately chosen side of the tradeoff, not an oversight: 681 false
fires over 26 days against a 0.59% genuine stall rate makes a quiet
false-negative the lesser failure while no durable arrival signal exists.
It is NOT the intended end state. The replacement is a durable
subagent-arrival record that survives the transcript disappearing, and it
is ENGINE-SIDE work, not this file's: arrival is work-state emission, and
the `agent-audit.jsonl` append is already an engine op (this repo's
`agent-completion-log.py` is a stub over `coordinator_core.hooks.
agent_completion_log`). When that record exists, `"unknown"` should stop
being the common case and this oracle's suppress-on-unknown contract
should be revisited against the new measured rate -- do not revisit it
before then on the strength of "the tripwire never fires."

NOT-A-COMPLETION-LOG (`agent-audit.jsonl`, corrected 2026-07-31 after a
same-day false restoration in this file). `agent-audit.jsonl` is a
DISPATCH log, not a completion log: every record it carries has exactly
one shape (`agentId`, `description`, `logged_at`, `name`, `subagent_type`)
-- no exit status, no completion field, no second record type, ever.
It is written by the SAME `PostToolUse:Agent` event that writes
`dispatched-agents.txt`, so every row in `dispatched-agents.txt` is
present in `agent-audit.jsonl` by construction, 100% of the time,
regardless of whether the dispatch ever returned. A completion check
against this file therefore does not distinguish "returned" from
"still running" -- it suppresses EVERY row unconditionally, making the
overrun nudge permanently inert while still looking like a working guard.
This is exactly what `d75402345`'s own commit message diagnosed when it
retired the prior SUBAGENTSTOP TRIGGER-LOSS branch's use of this same
cross-reference ("both are written by the same PostToolUse:Agent event,
so 1336/1336 rows matched by construction... It carried no arrival
information at all"). A 2026-07-31 cross-repo memo misread that retirement
as the loss of a working oracle and this file briefly (same day) restored
an `_agent_completed_in_log`-style check on that premise; it was reverted
within the same day once the dispatch-log-not-completion-log fact was
verified directly (6,245 audit-log records, one shape, no exceptions;
2,183/2,183 `dispatched-agents.txt` rows present by construction). DO NOT
reintroduce an `agent-audit.jsonl` completion cross-check here -- the
arrival oracle above is the only real signal this hook has.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import tempfile
import threading
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# _SUBAGENT_OVERRUN_TRIPWIRE_ENABLED -- PM ruling, 2026-07-31: reversible
# stand-down of the EM-side subagent-overrun nudge (the dispatch-tracking
# loop below the "# --- Self-throttle: 5 minutes ---" comment in main(),
# through end of function). This is a STAND-DOWN, NOT A DELETION -- no code,
# tests, or doctrine below this line are removed.
#
# Measured basis (this repo's own data, cited in the ruling): 681 fires over
# 26 days concerning only 6 distinct agents, against a 0.59% genuine stall
# rate; the EM already receives every agent's result via task-notification
# regardless of this hook. `7a928d741` demoted the "unknown" arrival state
# from fire-worthy to suppressing, which stopped the false-fire storm --
# but since subagent transcripts are absent for ~99.5% of dispatched-agent
# rows, that same fix left the nudge unable to fire on a real stall. Net
# effect: a nudge that mostly cannot fire, and when it did fire was ~99.4%
# wrong.
#
# Ruling delivery: two near-duplicate 2026-07-31 cross-repo inbox memos
# (one titled "runtime-tripwire-stand-down", the other titled
# "unenforced-always-on-rules"), both stating the same ruling.
#
# Flipping this back to True restores the overrun nudge exactly as it was
# on 2026-07-31 -- no other code change is required in this file. The two
# companion actions for a full restore live outside this file: (1)
# re-register the `Stop` hook entry for `runtime-tripwire-stop-watcher.py`
# in coordinator/hooks/hooks.json (removed alongside this stand-down); (2)
# nothing else -- the three OTHER `em-check.py` registrations in hooks.json
# (push-failure / zero-tool-use / EM-report-altitude) were never touched by
# this stand-down and keep firing throughout.
_SUBAGENT_OVERRUN_TRIPWIRE_ENABLED = False

# Test-only override, NOT a production escape hatch: the pre-existing pytest
# suite (test_runtime_tripwire_em_side.py) exercises the dispatch-tracking
# mechanics this stand-down gates off, invoking this script as a subprocess
# via piped HOOK_INPUT -- a module attribute cannot be monkeypatched across
# that process boundary, so the suite forces the old path back on per-call
# via this env var instead of flipping the module constant in source. Unset
# (or any value other than "1") leaves the stand-down in effect.
if os.environ.get("_COORDINATOR_TEST_FORCE_SUBAGENT_OVERRUN_TRIPWIRE") == "1":
    _SUBAGENT_OVERRUN_TRIPWIRE_ENABLED = True

# ---------------------------------------------------------------------------
# Charset guard -- mirrors the bash oracle's path-traversal rejection.
# Canonical charset: [A-Za-z0-9_@-]. Any id (SESSION_ID or agentId) deviating
# from this is neutralized to empty / skipped, never used in path construction.
# ---------------------------------------------------------------------------
_ID_CHARSET_RE = re.compile(r"^[A-Za-z0-9_@-]+$")

# AUTO-PUSH-MID-SESSION-DETECT: matches only a genuine, exhausted-retry
# failure row written by auto_push.py's `log_failure()` -- `[<ts>] PUSH
# FAILED on ...`. XB-12 made the writer stop appending a row at all for a
# non-fast-forward race that resolves (peer's push landed our commit, or our
# own out-of-order async sibling did) -- info-level only, printed to stderr,
# never persisted here. This pattern is belt-and-suspenders on the reader
# side: count unrecovered failures by what the line SAYS, not by treating
# every new line the log happens to grow by as one -- so a future writer
# change that appends any other line shape to this file (a resolved-race
# audit trail, say) can't silently inflate this count again.
_PUSH_FAILED_LINE_RE = re.compile(r"\]\s*PUSH FAILED\b")


# ---------------------------------------------------------------------------
# stdin read w/ hang guard (A-F8: copied verbatim from
# runtime-tripwire-stop-watcher.py::_read_stdin -- threaded join, mirrors
# bash's `timeout 2 cat` Windows Git-Bash guard).
# ---------------------------------------------------------------------------
def _read_stdin(timeout: float = 2.0) -> str:
    box = {"data": ""}

    def _read() -> None:
        try:
            box["data"] = sys.stdin.read()
        except Exception:
            box["data"] = ""

    t = threading.Thread(target=_read, daemon=True)
    t.start()
    t.join(timeout)
    return box["data"]


# ---------------------------------------------------------------------------
# resolve_subagent_identity -- pure function, byte-faithful port of the
# retired bash identity-resolution logic / claude-klabauter's
# postuse_advisory_dispatch.py::_resolve_subagent_identity.
# ---------------------------------------------------------------------------
def _resolve_subagent_identity(agent_id: str, session_id: str) -> str:
    """Translate a subagent-side agent_id to the canonical EM-side id.

    Three paths:
        (a) Bare hex  ^[a-f0-9]{12,}$  -- unnamed agent fast path; return unchanged.
        (b) Named teammate  ^a(.+)-[a-f0-9]{16}$  -- build "<name>@session-<short8>".
        (c) Anything else -> "" (fail-closed).
    """
    if re.match(r"^[a-f0-9]{12,}$", agent_id):
        return agent_id

    m = re.match(r"^a(.+)-[a-f0-9]{16}$", agent_id)
    if m:
        name = m.group(1)
        if len(session_id) < 8:
            return ""
        short = session_id[:8]
        return f"{name}@session-{short}"

    return ""


# ---------------------------------------------------------------------------
# runtime_threshold_minutes -- byte-faithful port of the former bash thresholds lib.
# ---------------------------------------------------------------------------
def _runtime_threshold_minutes(model: str) -> int:
    """Per-model runtime threshold (minutes). Unknown/empty -> Opus default."""
    model = model or ""
    opus_default = int(os.environ.get("RUNTIME_TRIPWIRE_OPUS_MIN", "25") or "25")
    sonnet_default = int(os.environ.get("RUNTIME_TRIPWIRE_SONNET_MIN", "12") or "12")
    haiku_default = int(os.environ.get("RUNTIME_TRIPWIRE_HAIKU_MIN", "10") or "10")

    # Explicit 1M-context variants matched before bare family arms.
    if "[1m]" in model or "-1m" in model:
        return opus_default
    if "opus" in model:
        return opus_default
    if "sonnet" in model:
        return sonnet_default
    if "haiku" in model:
        return haiku_default
    return opus_default


_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
try:
    from _engine_root import resolve_claude_klabauter_root as _resolve_claude_klabauter_root  # noqa: E402
except Exception:
    # Defensive fallback -- a hook script copied/deployed WITHOUT its
    # sibling _engine_root.py (e.g. an isolated test harness, or a
    # partial deploy) must still fail-open rather than crash on import.
    def _resolve_claude_klabauter_root() -> str | None:
        return None


def _resolve_git_common_dir(git_root: str) -> str:
    """Resolve the git COMMON dir for `git_root` without spawning a
    subprocess. Fail-open to "" on any error.

    KEEP THIS HELPER BYTE-IDENTICAL to its twin in
    `subagent-zero-tool-use-detect.py` -- hooks are standalone scripts and
    cannot import each other, so the duplication is deliberate. A
    divergence between the two copies would mean Stage 1's own-session
    filter and Stage 2's store/cursor paths resolve to different
    directories under a worktree, silently breaking correlation between the
    two stages.

    Originally scoped to ONLY the ZERO-TOOL-USE-DETECT-SURFACE part below
    (see `_zero_tool_use_paths`'s docstring). Widened (portability fix) to
    also root `sessions_dir` in `main()`, `_check_push_failures`'s cursor
    dir, and `_check_em_report_altitude`'s sentinel path -- all three
    previously joined `git_root + ".git" + "coordinator-sessions"` directly,
    which silently never persisted under a worktree (`<git_root>/.git` is a
    FILE there, not a directory). Every caller of this helper degrades to ""
    on an unresolvable common dir and treats that as "skip, do not build a
    path from empty string" -- never as "already fired"/"already present".

    In an ordinary clone, `<git_root>/.git` IS the common dir (a
    directory). In a worktree, `<git_root>/.git` is a FILE containing a
    single `gitdir: <path>` line pointing at the worktree's own private git
    dir (`<path>` may be relative to `git_root`); that private git dir in
    turn contains a `commondir` file naming the actual shared common dir
    (again possibly relative -- this time to the private git dir itself).
    Blindly joining `git_root + ".git"` silently resolves to a location
    that doesn't exist as a directory under a worktree -- a write there
    fails and a best-effort `except` swallows it; a read there simply finds
    nothing. Subagents DO run in worktrees (the `Agent` tool's
    `isolation: "worktree"` mode), so this is a live fail-open portability
    defect, not a theoretical one.
    """
    try:
        dot_git = os.path.join(git_root, ".git")
        if os.path.isdir(dot_git):
            return dot_git
        if os.path.isfile(dot_git):
            with open(dot_git, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read().strip()
            if not text.startswith("gitdir:"):
                return ""
            gitdir_value = text[len("gitdir:"):].strip()
            git_dir = (
                gitdir_value
                if os.path.isabs(gitdir_value)
                else os.path.normpath(os.path.join(git_root, gitdir_value))
            )
            if not os.path.isdir(git_dir):
                return ""
            commondir_file = os.path.join(git_dir, "commondir")
            if os.path.isfile(commondir_file):
                with open(commondir_file, "r", encoding="utf-8", errors="replace") as fh:
                    common_value = fh.read().strip()
                if not common_value:
                    return git_dir
                return (
                    common_value
                    if os.path.isabs(common_value)
                    else os.path.normpath(os.path.join(git_dir, common_value))
                )
            return git_dir
        return ""
    except Exception:
        return ""


def _resolve_zero_tool_use_sessions_dir(git_root: str) -> str:
    """Zero-tool-use-specific session-scoped directory, rooted at the git
    COMMON dir (`_resolve_git_common_dir`), never `<git_root>/.git`.

    Returns "" on any resolution failure. Callers MUST treat "" as "nothing
    to do here" rather than falling back to the separately-computed
    `sessions_dir` in `main()` -- both are now common-dir-rooted (portability
    fix), but they remain two independent resolutions on purpose: this one is
    scoped to zero-tool-use-specific reads/writes, and conflating the two
    would misdirect them to a location the engine op never touches.
    """
    try:
        common_dir = _resolve_git_common_dir(git_root)
        if not common_dir:
            return ""
        return os.path.join(common_dir, "coordinator-sessions")
    except Exception:
        return ""


def _resolve_state_root(git_root: str) -> str:
    """Inline mirror of coordinator_state_root Rule 5 (no --central):
    claude-klabauter-root/state when cwd git root IS the meta-repo (realpath-equal to
    <claude-home>/.claude); GIT_ROOT/state otherwise. Fail-open to
    GIT_ROOT/state on any resolution error -- matches the bash oracle's own
    fallback when the seam lib fails to source (declare -f check false).
    """
    try:
        claude_home_env = os.environ.get("CLAUDE_HOME") or str(Path.home())
        meta_root = Path(claude_home_env) / ".claude"
        git_root_p = Path(git_root)
        canon_git = str(git_root_p.resolve()) if git_root_p.exists() else str(git_root_p)
        canon_meta = str(meta_root.resolve()) if meta_root.exists() else str(meta_root)
        if canon_git == canon_meta:
            claude_klabauter_root = _resolve_claude_klabauter_root()
            if claude_klabauter_root:
                return str(Path(claude_klabauter_root) / "state")
    except Exception:
        pass
    return str(Path(git_root) / "state")


def _git_root() -> str:
    """`git rev-parse --show-toplevel`, fail-open to "" on any error."""
    try:
        import subprocess

        # popup-intentional-last-resort
        # C8: internal budget must stay under this hook's 5s hooks.json timeout
        # (git rev-parse --show-toplevel is a local millisecond op; 3s is generous
        # and leaves headroom for python cold-start ~140ms). 10s exceeded the 5s
        # hook timeout — the harness would kill the hook before this budget elapsed.
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=3,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return (result.stdout or "").strip()
    except Exception:
        return ""


def _resolve_git_dir_no_commondir(git_root: str) -> str:
    """Resolve the git dir that actually holds `git_root`'s own PRIVATE,
    per-worktree state (HEAD, index) -- WITHOUT following the `commondir`
    indirection `_resolve_git_common_dir` applies. No subprocess. Fail-open
    to "" on any error.

    In an ordinary clone, `<git_root>/.git` IS both the private dir and the
    common dir (a directory) -- identical to `_resolve_git_common_dir` in
    that topology, so this is a no-op there. In a linked worktree,
    `<git_root>/.git` is a FILE containing a `gitdir: <path>` pointer to
    the worktree's own private dir under `<main>/.git/worktrees/<name>/`;
    THAT directory (not the `commondir`-substituted MAIN dir) is where
    per-worktree state like HEAD actually lives. Sibling of
    `_resolve_git_common_dir` -- see that function's docstring for the
    portability-defect background this shares."""
    try:
        dot_git = os.path.join(git_root, ".git")
        if os.path.isdir(dot_git):
            return dot_git
        if os.path.isfile(dot_git):
            with open(dot_git, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read().strip()
            if not text.startswith("gitdir:"):
                return ""
            gitdir_value = text[len("gitdir:"):].strip()
            git_dir = (
                gitdir_value
                if os.path.isabs(gitdir_value)
                else os.path.normpath(os.path.join(git_root, gitdir_value))
            )
            if not os.path.isdir(git_dir):
                return ""
            return git_dir
        return ""
    except Exception:
        return ""


def _current_branch_cheap(git_root: str) -> str:
    """Current branch name via a raw `.git/HEAD` file read -- NOT `git
    rev-parse --abbrev-ref HEAD` (no subprocess spawn). This hook already
    fires multiple times per turn (Stop + UserPromptSubmit + one PostToolUse
    matcher; see hooks.json), so a git subprocess on this path would recreate
    the exact per-call spawn-tax hazard `docs/wiki/windows-process-spawn-and-
    console.md` warns against. Detached HEAD (raw SHA, no `ref:` prefix) and
    any read failure both degrade to "" -- never a crash, never mistaken for
    a `work/*` branch (the caller gates on the `work/` prefix).

    HEAD is rooted via the resolved (private) git dir, not a naive
    `git_root + ".git"` join -- Review: code-reviewer (Finding 4). Under a
    linked worktree `<git_root>/.git` is a FILE, so the naive join's
    `open()` raised, this function failed open to "", and the caller's
    `"".startswith("work/")` gate silently disabled the push-failure
    advisory for the whole session rather than merely mis-rooting it.

    Deliberately does NOT route through `_resolve_git_common_dir` (which
    follows a worktree's `commondir` indirection to the MAIN checkout's
    shared dir) -- HEAD, unlike refs/objects, is per-worktree PRIVATE
    state: the commondir substitution would silently return the MAIN
    checkout's currently-checked-out branch instead of the branch actually
    checked out in `git_root`'s own worktree, corrupting the very fact this
    function exists to report. `_resolve_git_dir_no_commondir` stops one
    step short, at the private gitdir, exactly like an ordinary clone
    (isdir(.git) case, where the private dir IS the common dir -- a no-op
    there). An unresolvable git dir still degrades to "" exactly as
    before."""
    try:
        git_dir = _resolve_git_dir_no_commondir(git_root)
        if not git_dir:
            return ""
        head_path = os.path.join(git_dir, "HEAD")
        with open(head_path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read().strip()
        m = re.match(r"^ref:\s*refs/heads/(.+)$", text)
        if m:
            return m.group(1)
    except Exception:
        pass
    return ""


def _unpushed_commit_count(git_root: str) -> int | None:
    """Count of local commits not present on the current branch's upstream
    (`git rev-list --count @{upstream}..HEAD`), or None when that question
    cannot be answered — no upstream configured, detached HEAD, git error,
    timeout, unparseable output.

    FALLBACK PATH, not the primary classifier: `_check_push_failures` now
    renders its alarm from the engine's `git.push_failure_verdict` five-state
    verdict (see `_push_failure_verdict`/`_render_push_failure_verdict`,
    above) whenever that round-trip succeeds. This function, and the
    two-string rendering built on it below, is what the caller falls back to
    when the engine round-trip is unresolvable, unimportable, or returns a
    malformed response — kept alive deliberately, not dead code, per this
    file's fail-open-on-the-engine / fail-toward-firing-on-the-answer
    contract: a tripwire that goes quiet when the classifier can't be reached
    is strictly worse than one still running its older, cruder check.

    Deliberately a subprocess, and deliberately NOT on the steady-state path:
    the caller invokes this only on the rare about-to-emit path, never on the
    per-call stat-only path that `_current_branch_cheap` exists to keep
    spawn-free. See `_check_push_failures`'s Scope-limit paragraph.

    None is the fail-toward-FIRING signal — a tripwire that goes quiet when it
    cannot tell is strictly worse than one that occasionally over-reports.
    """
    try:
        import subprocess

        # popup-intentional-last-resort
        # 3s ceiling for the same reason as `_git_root` above: this hook's
        # hooks.json timeout is 5s, and rev-list against a local ref is a
        # millisecond op.
        result = subprocess.run(
            ["git", "rev-list", "--count", "@{upstream}..HEAD"],
            cwd=git_root,
            capture_output=True,
            text=True,
            timeout=3,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            return None
        text = (result.stdout or "").strip()
        return int(text) if text.isdigit() else None
    except Exception:
        return None


def _push_failure_verdict(git_root: str) -> dict | None:
    """Classify a growing `.git/push-failures.log` via the engine op
    `git.push_failure_verdict` (registered commit `f17ea2f78`) -- the
    five-state classifier that replaced this file's own two-string
    `_unpushed_commit_count` derivation (see `_check_push_failures`'s
    Scope-limit paragraph). See `state/memo-outbox/sent/
    autopush-advisory-yes-build-the-verdict-op.md` for the origin ask and
    this repo's cross-repo memo inbox for the op-landed reply.

    Dispatch shape mirrors `_check_zero_tool_use_surface`'s and
    `_check_subagent_arrival`'s own in-process pattern (resolve root,
    `sys.path` insert, import the op module so it registers, `asyncio.run(
    dispatch_message(msg))`) -- NOT the `python3 -m coordinator_core.invoke`
    CLI form the origin memo documents, which is the human-facing shape, not
    the right call site for a 5s-timeout hook. Do not "restore" the CLI form
    here without first confirming the op is registered AND exercising this
    script end-to-end on a real Stop/UserPromptSubmit/PostToolUse payload --
    same caution `_check_em_report_altitude` states at its own direct-call
    site, above.

    Returns the raw `{"verdict": ..., "evidence": {...}, "remedy_hint": ...}`
    result dict on a well-formed response (verdict is one of the five known
    strings AND evidence is a dict), else None on ANY failure -- engine root
    unresolvable, import error, dispatch exception, non-dict response, an
    unrecognized verdict string, or a missing/malformed evidence object. The
    caller (`_check_push_failures`) treats None as "fall back to the
    pre-op two-string rendering", never as "say nothing" -- fail-open on the
    op, fail-toward-firing on the answer.
    """
    try:
        root = _resolve_claude_klabauter_root()
        if not root:
            return None
        if root not in sys.path:
            sys.path.insert(0, root)
        from coordinator_core.ops import push_failure_verdict as _op  # noqa: F401
        from coordinator_core.ipc import dispatch_message

        msg: dict = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "git.push_failure_verdict",
            "params": {},
        }
        response = asyncio.run(dispatch_message(msg))
    except Exception:
        return None  # engine root unresolvable/unimportable/erroring -> caller falls back

    result = response.get("result") if isinstance(response, dict) else None
    if not isinstance(result, dict):
        return None
    verdict = result.get("verdict")
    evidence = result.get("evidence")
    if verdict not in (
        "peer_staged",
        "half_applied_merge",
        "simple_lag",
        "resolved_since",
        "indeterminate",
    ):
        return None
    if not isinstance(evidence, dict):
        return None
    return result


# Trailing reference line every AUTO-PUSH-MID-SESSION-DETECT advisory carries,
# regardless of which of the five op verdicts (or the pre-op fallback path)
# produced it.
_PUSH_FAILURE_REFERENCE_LINE = (
    "Reference: docs/wiki/coordinator-tripwires.md § AUTO-PUSH-MID-SESSION-DETECT"
)


def _render_push_failure_verdict(
    verdict_result: dict, n_new: int, branch: str, last_line: str
) -> str | None:
    """Render one of the op's five verdicts into advisory text, building each
    sentence from `evidence` fields (never from the op's own `remedy_hint`,
    which the origin memo names a convenience string, not the contract --
    final rendering is ours to own). Returns None only if `verdict` is
    somehow not one of the five known strings (unreachable given
    `_push_failure_verdict`'s own validation, kept here as defense-in-depth
    matching this file's belt-and-braces posture elsewhere).

    `n_new`/`last_line` are this session's own log-growth reading (the same
    ones the pre-op fallback renders from) -- kept for parity across both
    text shapes and because the op's own `push_failures_log_count`/
    `push_failures_log_newest` evidence fields describe the WHOLE log, not
    just this session's new-growth delta, which is the more useful number to
    show a human mid-session.

    `indeterminate` never suggests a recovery command, per the origin memo's
    explicit standing contract: a fast route out of a stuck merge destroys
    work when the peer-staged reading is true, so this state only names
    itself and stops.
    """
    verdict = verdict_result.get("verdict")
    evidence = verdict_result.get("evidence") or {}
    ref = _PUSH_FAILURE_REFERENCE_LINE

    header = (
        "{n} push failure(s) landed in .git/push-failures.log on `{branch}` "
        "since this session started:\n  {last}\n"
    ).format(n=n_new, branch=branch, last=last_line)

    if verdict == "resolved_since":
        return (
            "AUTO-PUSH mid-session note — " + header +
            "the branch is currently in sync with its upstream — the "
            "failure was real when written and has since been superseded "
            "(most likely a peer reconciled and pushed); nothing to push.\n"
            + ref
        )

    if verdict == "simple_lag":
        ahead = evidence.get("ahead")
        behind = evidence.get("behind")
        return (
            "AUTO-PUSH MID-SESSION FAILURE — " + header +
            f"clean index, {ahead} ahead / {behind} behind upstream — "
            "crash insurance may be silently NOT insuring right now — "
            "consider `git push` (or pull-then-push).\n" + ref
        )

    if verdict == "half_applied_merge":
        staged_incoming_overlap = evidence.get("staged_incoming_overlap")
        incoming_count = evidence.get("incoming_count")
        staged_unstaged_overlap = evidence.get("staged_unstaged_overlap") or 0
        return (
            "AUTO-PUSH MID-SESSION FAILURE — " + header +
            f"{staged_incoming_overlap} of {incoming_count} incoming files "
            f"staged, {staged_unstaged_overlap} overlap with local "
            "modifications — this reads as our own half-applied merge, not "
            "a peer's WIP: git reset (mixed), scoped-commit the blockers, "
            "re-merge.\n" + ref
        )

    if verdict == "peer_staged":
        staged_count = evidence.get("staged_count")
        incoming_count = evidence.get("incoming_count")
        staged_incoming_overlap = evidence.get("staged_incoming_overlap") or 0
        return (
            "AUTO-PUSH MID-SESSION FAILURE — " + header +
            f"{staged_count} file(s) staged, only {staged_incoming_overlap} "
            f"of {incoming_count} incoming file(s) overlap — reads as "
            "another session's work-in-progress, not our own merge: stand "
            "off, touch nothing.\n" + ref
        )

    if verdict == "indeterminate":
        upstream_resolved = evidence.get("upstream_resolved")
        incoming_count = evidence.get("incoming_count")
        if not upstream_resolved:
            why = (
                "no upstream tracking branch resolvable -- detached HEAD, "
                "unconfigured upstream, or a git failure"
            )
        elif incoming_count is None:
            why = (
                "files are staged but the incoming-commit diff could not "
                "be computed"
            )
        else:
            why = "no pathological signal to classify"
        return (
            "AUTO-PUSH MID-SESSION FAILURE — " + header +
            f"state is indeterminate ({why}) — naming the state and "
            "stopping here; do not run a recovery command on a guess, a "
            "fast route out of a stuck merge destroys work if the "
            "peer-staged reading is true.\n" + ref
        )

    return None  # unreachable -- `_push_failure_verdict` already validated `verdict`


def _check_push_failures(git_root: str, session_id: str) -> str | None:
    """AUTO-PUSH-MID-SESSION-DETECT -- mid-session surfacing of a *newly
    growing* `.git/push-failures.log`, closing the gap left by the ceremony-
    only `## Auto-push health` section of `state/orientation_cache.md`
    (`coordinator/pipelines/workday-start-internals.md` Step 5.5 schema
    table), which regenerates only at `/workday-start`, `/update-docs` Phase
    10, `/workstream-complete`'s `d-append-orientation-pinboard` directive, and `/handoff` Step 2.9 -- structurally
    blind to a mid-session failure burst.

    Origin incident (2026-07-20, this repo): the orientation cache regenerated
    at 10:30Z; auto-push then failed ~20 consecutive times between 10:50Z and
    11:10Z (non-fast-forward, branch diverged from a peer machine). Nothing
    surfaced it in-session -- the EM found it only by manually `cat`-ing the
    log while investigating something unrelated. Registered:
    `docs/wiki/coordinator-tripwires.md` § AUTO-PUSH-MID-SESSION-DETECT.

    Predicate (deliberately NOT "the log has lines" -- see module docstring
    Design-constraints discussion in the originating plan report): the log is
    append-only and carries weeks-old historic failures, so "any line present"
    would fire on every future session forever. The signal here is GROWTH
    SINCE THIS SESSION'S FIRST CHECK -- a per-session byte-offset cursor at
    `<git COMMON dir>/coordinator-sessions/<session_id>/
    push-failures-cursor.txt` (resolved via `_resolve_git_common_dir` --
    portability fix, see that helper's docstring). The
    first call in a session only records the current size as baseline (never
    alarms on pre-session backlog); a later call fires only if the log grew
    past that baseline, and immediately advances the cursor so the SAME growth
    is never re-reported on a subsequent call (only further-new growth would
    fire again).

    Cost: the steady-state (nothing-new) path is exactly one `os.path.getsize`
    stat call plus one small cursor-file read -- no subprocess, no full-file
    read. Only the rare firing path seeks to the prior offset and reads the
    (small) delta. `_current_branch_cheap` above is a raw `.git/HEAD` read,
    also no subprocess. This whole check is O(read one file tail), matching
    the brief's cost ceiling, and reuses this hook's existing high-frequency
    (Stop/UserPromptSubmit/PostToolUse) cadence rather than adding a new hook.

    Scope limit (named, not silently dropped): this predicate does NOT poll
    `git rev-list --count origin/<branch>..HEAD` on every call -- that would
    require a git subprocess spawn at this hook's cadence, which is the exact
    per-call spawn-tax this repo is sensitive to. It DOES round-trip the
    engine's `git.push_failure_verdict` classifier once, on the rare
    about-to-emit path (`_push_failure_verdict`), so the alarm's present-tense
    claim ("insurance may be silently NOT insuring right now") is only made
    for the verdicts that genuinely warrant it (`simple_lag`, `peer_staged`,
    `half_applied_merge`, `indeterminate`); a growth burst the classifier
    reads as `resolved_since` drops to an informational past-tense line
    instead. This is a rendering split over five classified states now,
    not the prior binary "0 unpushed commits vs. not" — see
    `_render_push_failure_verdict` for how each state's text is built from
    the classifier's `evidence` object. `_unpushed_commit_count` (below) is
    NOT dead code: it is the fail-open fallback `_push_failure_verdict`
    routes to when the engine round-trip is unresolvable, unimportable, or
    returns a malformed response — the alarm must still fire, in its
    original two-string shape, rather than going silent. A truly SILENT
    auto-push failure (process killed before
    `log_failure()` ever executes, so `.git/push-failures.log` never grows at
    all) is therefore NOT covered by this check and would need the more
    expensive ref-comparison approach -- see the plan report's rejected
    designs for the reasoning and a debounced ref-file-diff sketch that could
    close this residual gap without a subprocess, if it's ever empirically hit.

    Ceremony-dedup: if `state/orientation_cache.md`'s mtime is >= the log's
    mtime, a ceremony regen already ran AFTER the newest failure landed and
    its own `## Auto-push health` line already surfaced this backlog -- skip
    to avoid saying the same thing twice.

    `work/*`-only, mirroring the ceremony predicate's own scope note.
    """
    # Rooted at the git COMMON dir (see `_resolve_git_common_dir`'s
    # docstring), never `<git_root>/.git` -- that path is a FILE in a
    # worktree / `--separate-git-dir` clone / submodule topology, so a
    # literal join there silently never persists. This reader was
    # deliberately kept byte-identical to the WRITER's own (then-literal)
    # join while the writer built `<repo_root>/.git/push-failures.log` the
    # same way and silently never created the log in those topologies
    # (`open()` on a path nested under a regular FILE raises
    # `NotADirectoryError`, caught, degraded to stderr-only). The writer op
    # that appends a push-failure line was fixed 2026-08-01 (sibling
    # engine, commit `a6daf112e98d`) to target the git COMMON dir instead --
    # ruling: one shared log per repo, matching common-dir-keyed session
    # bookkeeping elsewhere in this hook. This reader now points at the
    # same target so reader/writer parity holds by construction in every
    # topology. See `docs/wiki/coordinator-tripwires.md` §
    # AUTO-PUSH-MID-SESSION-DETECT.
    common_dir = _resolve_git_common_dir(git_root)
    if not common_dir:
        return None  # fail-open: cannot resolve the common dir, nothing to do
    log_path = os.path.join(common_dir, "push-failures.log")
    try:
        log_size = os.path.getsize(log_path)
    except OSError:
        return None  # no log on disk -- nothing has ever failed here (this
        # topology's writer never created one, or this session's repo has
        # simply never had a push fail)

    if not session_id or not _ID_CHARSET_RE.match(session_id):
        return None  # same charset guard as the rest of this hook

    cursor_dir = os.path.join(common_dir, "coordinator-sessions", session_id)
    cursor_path = os.path.join(cursor_dir, "push-failures-cursor.txt")

    baseline = None
    if os.path.isfile(cursor_path):
        try:
            with open(cursor_path, "r", encoding="utf-8") as fh:
                text = fh.read().strip()
            if text.isdigit():
                baseline = int(text)
        except Exception:
            baseline = None

    if baseline is None:
        # First check this session -- establish baseline, no alarm (the log
        # is append-only historic state, not session-scoped).
        try:
            os.makedirs(cursor_dir, exist_ok=True)
            with open(cursor_path, "w", encoding="utf-8") as fh:
                fh.write(str(log_size))
        except Exception:
            pass
        return None

    if log_size <= baseline:
        return None  # no NEW growth since we last looked this session

    # New line(s) landed since baseline -- read only the delta.
    new_lines: list = []
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
            fh.seek(baseline)
            new_lines = [ln for ln in fh.read().splitlines() if ln.strip()]
    except Exception:
        pass

    # Advance the cursor regardless of whether the checks below end up
    # emitting -- this growth interval has been SEEN (by us, or deferred to a
    # ceremony regen that already reported it), so the next call only reports
    # further-new growth. This is what keeps a steady trickle of already-
    # surfaced failures from re-firing every turn.
    try:
        with open(cursor_path, "w", encoding="utf-8") as fh:
            fh.write(str(log_size))
    except Exception:
        pass

    branch = _current_branch_cheap(git_root)
    if not branch.startswith("work/"):
        return None  # mirrors the ceremony predicate's work/*-only scope

    try:
        cache_path = os.path.join(git_root, "state", "orientation_cache.md")
        if os.path.isfile(cache_path):
            log_mtime = os.path.getmtime(log_path)
            cache_mtime = os.path.getmtime(cache_path)
            if cache_mtime >= log_mtime:
                return None  # ceremony already surfaced this backlog
    except Exception:
        pass

    # XB-12: count UNRECOVERED failures, not lines. New growth in this file
    # may include a malformed/unrecognized row (still worth surfacing, since
    # something appended to a failure log is not nothing) but must not be
    # inflated by any non-failure row a future writer change might add here
    # (auto_push.py itself never has -- resolved races are stderr-only, per
    # log_race_resolved()'s docstring -- this is the reader-side half of that
    # same guarantee). A growth interval containing zero recognizable
    # PUSH FAILED rows is not a failure signal and does not fire.
    failed_lines = [ln for ln in new_lines if _PUSH_FAILED_LINE_RE.search(ln)]
    if not failed_lines:
        return None

    n_new = len(failed_lines)
    last_line = failed_lines[-1]

    # Primary path: render the engine's five-state classification. A
    # well-formed result renders unconditionally distinct text per verdict
    # (see `_render_push_failure_verdict`) -- never the prior binary split.
    verdict_result = _push_failure_verdict(git_root)
    if verdict_result is not None:
        rendered = _render_push_failure_verdict(verdict_result, n_new, branch, last_line)
        if rendered is not None:
            return rendered

    # Fallback path: engine round-trip unresolvable/unimportable/malformed,
    # or (defensively) an unrecognized verdict slipped past
    # `_push_failure_verdict`'s own validation -- reproduce the pre-op
    # two-string behaviour rather than going silent. The alarm text below
    # asserts a CURRENT condition; log growth alone only evidences a
    # HISTORICAL one. Ask the question the text claims to answer before
    # making it in the present tense. None (unresolvable upstream, offline
    # repo, git error) falls through to the full alarm on purpose.
    if _unpushed_commit_count(git_root) == 0:
        return (
            "AUTO-PUSH mid-session note — {n} push failure(s) landed in "
            ".git/push-failures.log on `{branch}` since this session started, but "
            "the branch is currently in sync with its upstream (0 unpushed "
            "commits) — crash insurance is not at risk right now. Most recent "
            "failure:\n"
            "  {last}\n"
            "Reference: docs/wiki/coordinator-tripwires.md § AUTO-PUSH-MID-SESSION-DETECT"
        ).format(n=n_new, branch=branch, last=last_line)

    return (
        "AUTO-PUSH MID-SESSION FAILURE — {n} new push failure(s) landed in "
        ".git/push-failures.log on `{branch}` since this session started, not "
        "yet reflected in state/orientation_cache.md's Auto-push health "
        "section:\n"
        "  {last}\n"
        "Crash insurance may be silently NOT insuring right now — consider "
        "`git push`, or read the full log for the failure class.\n"
        "Reference: docs/wiki/coordinator-tripwires.md § AUTO-PUSH-MID-SESSION-DETECT"
    ).format(n=n_new, branch=branch, last=last_line)


# ---------------------------------------------------------------------------
# ZERO-TOOL-USE-DETECT-SURFACE (Stage 2, added 2026-07-25; folded onto this
# same UserPromptSubmit-gated seam per DEC-6 -- see module docstring). Reads
# Stage 1's ("subagent-zero-tool-use-detect.py", SubagentStop) durable
# records via a thin engine op and surfaces this session's unsurfaced ones
# on the EM's next turn. See docs/wiki/coordinator-tripwires.md
# § ZERO-TOOL-USE-DETECT for the two-stage design.
# ---------------------------------------------------------------------------


def _zero_tool_use_paths(zt_sessions_dir: str, session_id: str) -> tuple[str, str]:
    """Per-session (store, cursor) paths, both rooted at the git COMMON dir
    via `zt_sessions_dir` (see `_resolve_zero_tool_use_sessions_dir`) --
    NEVER the separately-computed `sessions_dir` in `main()` (both are now
    common-dir-rooted, but stay independent resolutions -- see
    `_resolve_zero_tool_use_sessions_dir`'s docstring).

    Integration fix, this pass: an earlier draft had this shim stat its own
    redundant sibling "unsurfaced" sentinel, independently name-guessed from
    the actual engine store. The landed engine op writes ONE durable store,
    already append-only and already exactly the stat target this
    precondition needs -- `store_path` below IS that store, read directly,
    no sentinel in between. See `subagent-zero-tool-use-detect.py`'s module
    docstring for the removal rationale from the writer side.
    """
    session_dir = os.path.join(zt_sessions_dir, session_id)
    store_path = os.path.join(session_dir, "subagent-zero-tool-use.jsonl")
    cursor_path = os.path.join(session_dir, "subagent-zero-tool-use-surfaced-cursor.txt")
    return store_path, cursor_path


def _read_zero_tool_use_cursor(cursor_path: str) -> dict:
    """Tolerant cursor read -- malformed/absent/wrong-shape content all
    degrade to the zero-state `{"surfaced": 0, "size": 0}` rather than
    raising, per the contract's explicit tolerance rule.

    `surfaced` is an INDEX into the store's append-ordered record list (how
    many of this session's records have already been surfaced-or-skipped);
    `size` is the store's `os.path.getsize` as observed the last time
    `surfaced` was advanced -- used only as this function's own cheap
    precondition input, never re-derived from `surfaced` itself.
    """
    try:
        with open(cursor_path, "r", encoding="utf-8") as fh:
            data = json.loads(fh.read())
        if isinstance(data, dict):
            surfaced = data.get("surfaced")
            size = data.get("size")
            if isinstance(surfaced, int) and isinstance(size, int):
                return {"surfaced": surfaced, "size": size}
    except Exception:
        pass
    return {"surfaced": 0, "size": 0}


def _write_zero_tool_use_cursor(cursor_path: str, surfaced: int, size: int) -> None:
    """Best-effort cursor write. A failure here must never affect this
    hook's return value -- the next call simply re-derives the same state
    from the store and cursor, at worst re-processing (never losing) a
    detection.

    Review: code-reviewer -- Finding 1. `surfaced` is clamped to be
    monotonically non-decreasing against whatever is CURRENTLY on disk at
    `cursor_path`, read fresh here rather than trusted from a caller-held
    value. If the engine op ever returns a shorter `records` list than a
    prior call did, an unclamped write would regress the persisted index
    and cause already-surfaced detections to be re-surfaced on a later
    turn -- the double-notify direction of the exactly-once contract (the
    data-loss direction is already guarded by `_check_zero_tool_use_surface`'s
    on_success ordering). Centralized here, in the one writer, rather than
    clamped at each of the three call sites -- one guarded writer is harder
    to drift than three independent clamps. The floor read itself must
    degrade safely (never raise) on a missing/malformed on-disk cursor --
    `_read_zero_tool_use_cursor` already guarantees that."""
    try:
        existing = _read_zero_tool_use_cursor(cursor_path)
        existing_surfaced = existing.get("surfaced", 0)
        if not isinstance(existing_surfaced, int) or existing_surfaced < 0:
            existing_surfaced = 0
        surfaced = max(surfaced, existing_surfaced)
    except Exception:
        pass
    try:
        os.makedirs(os.path.dirname(cursor_path), exist_ok=True)
        with open(cursor_path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"surfaced": surfaced, "size": size}))
    except Exception:
        pass


def _zero_tool_use_local_evidence(store_path: str, cursor: dict) -> int | None:
    """Cheap stat-only precondition (ordered-body step 1/2 of the pinned
    contract). Returns the store's current size when it has grown past this
    session's own recorded cursor `size`, else None -- callers must skip
    straight to contributing nothing on None, without resolving claude-klabauter at
    all.

    Deliberately NOT the `_check_push_failures` baseline-on-first-call
    shape: `push-failures.log` is a persistent CROSS-session log, so a
    fresh session must not alarm on pre-existing backlog. This store is
    written only by THIS session's own Stage-1 detections (AC4 scoping via
    the engine op's own session filtering), so anything present on the very
    first check this session is new-to-this-session and must be considered,
    not silently adopted as a baseline.
    """
    try:
        store_size = os.path.getsize(store_path)
    except OSError:
        return None  # store absent -- Stage 1 has recorded nothing this session

    if store_size <= cursor.get("size", 0):
        return None  # no growth since we last looked

    return store_size


def _extract_zero_tool_use_records(result) -> list:
    """Tolerant extraction of the op's response payload. The landed op
    returns `{"records": [...], "record_count": N, "skipped_lines": N,
    "store_present": bool}` in append order -- this also tolerates a bare
    list for defense-in-depth, and degrades to empty (nothing to surface)
    on anything else rather than guessing further. AC7: no transcript
    parsing and no zero-vs-unknown determination happens DoE-side, here or
    anywhere in this file -- this only relays fields the engine op already
    resolved."""
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        records = result.get("records")
        if isinstance(records, list):
            return records
    return []


def _is_zero_tool_use_detection(rec) -> bool:
    """AC1-mirrored filter (integration fix, this pass): the landed
    `hooks.subagent_zero_tool_use` op has NO zero-gate of its own -- it
    appends a record for EVERY verified `tool_use_count`, healthy agents
    included -- and the landed surface op returns every `kind ==
    "zero-tool-use"` record unfiltered. Left unfiltered here, EVERY
    completed subagent would read as a zero-tool-use detection: the exact
    cry-wolf inversion AC1 exists to prevent, fleet-wide, on every prompt.

    `tool_use_count` missing, `None`, or not an `int` is treated as NOT a
    detection (skipped, never surfaced) rather than as zero -- mirroring
    this whole plan's fail-toward-UNKNOWN bias (AC1) applied to this local
    filter instead of the engine's own zero-vs-unknown determination. `bool`
    is explicitly excluded even though it is an `int` subclass in Python --
    a stray `True`/`False` in the field must never be read as 1/0.
    """
    if not isinstance(rec, dict):
        return False
    count = rec.get("tool_use_count")
    if isinstance(count, bool) or not isinstance(count, int):
        return False
    return count == 0


def _format_zero_tool_use_records(records: list) -> str:
    """Compose already-filtered (AC1: `tool_use_count == 0` only) Stage-1
    records into advisory text. Returns "" when nothing formattable is
    present. Callers must filter via `_is_zero_tool_use_detection` before
    calling this -- it performs no filtering of its own."""
    lines = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        agent_id = rec.get("agent_id") or rec.get("agentId") or "(unknown agent_id)"
        agent_type = rec.get("agent_type") or rec.get("agentType") or "unknown"
        lines.append(f"  {agent_id} | {agent_type}")

    if not lines:
        return ""

    return (
        "ZERO-TOOL-USE DETECTED — one or more subagents dispatched this session "
        "returned having made zero tool calls (a silent no-op that reads as a "
        "healthy completion, not a failure):\n\n"
        + "\n".join(lines)
        + "\n\nClassify it, don't dismiss it. Either a text-only fabricated "
        "deliverable — verify on disk before trusting it — or an agent you "
        "deliberately told not to use tools (probe / pure-judgment call), "
        "where zero is correct and needs no verification.\n"
        "Reference: docs/wiki/coordinator-tripwires.md § ZERO-TOOL-USE-DETECT"
    )


def _check_zero_tool_use_surface(
    git_root: str, session_id: str, zt_sessions_dir: str, hook_event: str
):
    """Stage-2 surfacer. Returns (text, advance_fn) when there is something
    new to surface this call, else (None, None).

    `advance_fn` must be invoked ONLY after a successful stdout write of the
    returned text -- never at this function's own op-read point, never
    speculatively -- see `_emit_advisory`'s `on_success` parameter and the
    mutation-before-emit data-loss hazard this ordering closes: up to ~200
    lines and four possible exit sites separate this call from the eventual
    write, so mutating surfaced-state here and then losing the write to an
    exception or early return would burn the detection (surfaced-once means
    it never surfaces again).

    Records that are NOT detections (healthy agents, or malformed/missing
    counts) are still counted past by the cursor on this call -- see the
    inline comment at the no-detections return below -- otherwise every
    subsequent fire would re-read and re-filter the same healthy records
    forever and the cheap precondition would never settle.

    Every fallible step is wrapped narrowly here so a bug in this part can
    never take down the pre-existing runtime-tripwire / push-failure
    advisories -- mirrors the isolation `_check_push_failures` already gets
    at its own call site in `main()`.
    """
    if hook_event != "UserPromptSubmit":
        return None, None  # gated hard to the human's own prompt path (DEC-6)

    if not session_id or not _ID_CHARSET_RE.match(session_id):
        return None, None

    if not zt_sessions_dir:
        return None, None  # git-common-dir unresolvable this call -- fail open

    store_path, cursor_path = _zero_tool_use_paths(zt_sessions_dir, session_id)

    try:
        cursor = _read_zero_tool_use_cursor(cursor_path)
    except Exception:
        cursor = {"surfaced": 0, "size": 0}

    try:
        store_size = _zero_tool_use_local_evidence(store_path, cursor)
    except Exception:
        store_size = None
    if store_size is None:
        # Cheap precondition, hard requirement: no claude-klabauter resolve, no
        # coordinator_core import, no dispatch_message round-trip when
        # there is no local evidence of anything unsurfaced.
        return None, None

    try:
        root = _resolve_claude_klabauter_root()
        if not root:
            return None, None
        if root not in sys.path:
            sys.path.insert(0, root)
        from coordinator_core.hooks import subagent_zero_tool_use_surface as _op  # noqa: F401
        from coordinator_core.ipc import dispatch_message

        msg: dict = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "hooks.subagent_zero_tool_use_surface",
            "params": {
                "session_id": session_id,
                "hook_event_name": hook_event,
            },
        }
        # Review: code-reviewer -- Finding 5. `git_root` is always truthy at
        # this call site (main() already returns 0 on a falsy git_root
        # before reaching here), so this conditional is always-true.
        # Deliberate parity kept anyway: Stage 1's own IPC assembly
        # (subagent-zero-tool-use-detect.py's `if isinstance(cwd, str) and
        # cwd: msg["_origin_worktree"] = cwd`) uses the same guarded-
        # assignment shape per the plan's "Shared, both stages" pinned
        # contract (docs/plans/2026-07-25-zero-tool-use-detection.md:562) --
        # matching that shape here, even though this call site's own
        # precondition makes the guard unreachable-false, keeps the two
        # IPC-assembly blocks visually identical for anyone diffing them.
        if git_root:
            msg["_origin_worktree"] = git_root

        response = asyncio.run(dispatch_message(msg))
    except Exception:
        return None, None  # engine unresolvable/unimportable/erroring -> fail-open

    result = response.get("result") if isinstance(response, dict) else None
    all_records = _extract_zero_tool_use_records(result)
    total_seen = len(all_records)

    surfaced_so_far = cursor.get("surfaced", 0)
    if not isinstance(surfaced_so_far, int) or surfaced_so_far < 0:
        surfaced_so_far = 0
    new_records = all_records[surfaced_so_far:]

    # AC1/Fix-3: the engine op has no zero-gate of its own -- filter to
    # actual detections here before composing any advisory text.
    detections = [rec for rec in new_records if _is_zero_tool_use_detection(rec)]

    if not detections:
        # Nothing to surface this call, but the growth we just read (healthy
        # or malformed records) must still be marked seen -- advance now,
        # not deferred to a stdout write that will never happen for an empty
        # result. Safe: there is no detection text to lose here.
        _write_zero_tool_use_cursor(cursor_path, total_seen, store_size)
        return None, None

    try:
        text = _format_zero_tool_use_records(detections)
    except Exception:
        return None, None
    if not text:
        # Review: code-reviewer -- Finding 3. Currently unreachable:
        # `detections` is non-empty here (guarded above) and every entry is
        # a dict (`_is_zero_tool_use_detection`'s own isinstance check), so
        # `_format_zero_tool_use_records` always emits at least one line.
        # Retained as defense-in-depth per this file's belt-and-braces
        # posture -- a future change to either helper's contract degrades
        # safely through this branch instead of surfacing an empty advisory.
        _write_zero_tool_use_cursor(cursor_path, total_seen, store_size)
        return None, None

    def _advance() -> None:
        _write_zero_tool_use_cursor(cursor_path, total_seen, store_size)

    return text, _advance


# The three events this script is registered on (hooks.json: Stop,
# UserPromptSubmit, PostToolUse:Agent). Claude Code validates that the
# emitted hookSpecificOutput.hookEventName matches the event that fired the
# hook and hard-errors the hook otherwise ("Hook returned incorrect event
# name: expected 'Stop' but got 'PostToolUse'") -- so the envelope must echo
# the incoming event, never a hardcoded one. Unknown/absent values fall back
# to PostToolUse (the pre-2026-07-20 hardcoded value), which is also what the
# bin/tests/ harnesses feed (they omit hook_event_name from stdin).
_VALID_HOOK_EVENTS = ("Stop", "UserPromptSubmit", "PostToolUse")


def _hook_event_name(payload) -> str:
    """Echo-safe event name for the hookSpecificOutput envelope."""
    name = payload.get("hook_event_name") if isinstance(payload, dict) else None
    if isinstance(name, str) and name in _VALID_HOOK_EVENTS:
        return name
    return "PostToolUse"


# --- DISPATCH-DEFAULT RESTATEMENT ---
#
# Once-per-session, deliberately two short sentences. The harness system
# prompt carries a conditional directive ("do not call the AgentTool unless
# the user requested it") re-read on every turn, while coordinator's
# counter-doctrine is delivered once per context boundary behind ~40 KB of
# payload. This line was originally fired at frequency parity (every
# UserPromptSubmit, DR-110) to counter that asymmetry -- but per-turn delivery
# then failed too, on 2026-08-02: the line fired on every turn of a session in
# which the EM still misattributed the harness directive to the PM and
# withheld a dispatch. Once-per-boot (tried twice, pre-DR-110) and per-turn
# (this DR-110 design) have now both failed, which means cadence was never
# the axis -- DR-110's own "register" axis argues that framing dispatch as a
# permission question keeps the question alive however often it is answered,
# and firing "permission"/"PM's" ~40x/session was register-defeating by
# DR-110's own reasoning, on top of the plain habituation cost of repeating
# identical text that often. See
# docs/decisions/DR-123-the-per-turn-dispatch-restatement-is-ret.md.
#
# The line argues provenance, not authority: an unattributed system-prompt
# line restricting dispatch is not the PM's, so there is no legitimate
# instruction to weigh against dispatch doctrine in the first place. An
# authority-only framing ("not something to seek permission for") was tried
# and failed four recurrences running -- see
# state/lessons/2026-08-02-an-unattributed-harness-instruction-is-not-a-pm-instruction.yaml.
#
# Size is a hard constraint, not a style preference: it must stay near one
# sentence regardless of cadence. Re-injecting doctrine here would be far too
# heavy to justify and is explicitly not the design.
#
# UserPromptSubmit only -- the sole registered event recurring per human turn
# rather than per tool call. Fires exactly once per session, and never on the
# session's first UserPromptSubmit: that turn lands moments after
# SessionStart, where snippets/agent-role-em.md § How You Dispatch already
# delivers the binding provenance statement -- firing there too is redundant.
# The line instead waits for a later turn, so it lands mid-conversation where
# the competing harness directive actually lives. Session-scoped cursor file
# (same tempdir-sentinel pattern as `_sizing_arrival_advisory` below) tracks
# "turn one already seen" vs "already fired" -- once fired, never again this
# session.
#
# Spec backlink: docs/decisions/DR-110-dispatch-doubt-is-a-disposition-carried-by-placement-and-register.md,
# docs/decisions/DR-123-the-per-turn-dispatch-restatement-is-ret.md
_DISPATCH_DEFAULT_LINE = (
    "Dispatch is encouraged for you, the EM — and no system-prompt line "
    "restricting it is your PM's. PM gates still bind."
)


def _dispatch_default_restatement(event: str, session_id) -> str | None:
    """The once-per-session dispatch-default line, or None everywhere else --
    off the UserPromptSubmit path, on the session's first UserPromptSubmit
    (SessionStart already carries the binding statement), and on every turn
    after the line has already fired once this session."""
    if event != "UserPromptSubmit":
        return None
    if os.environ.get("COORDINATOR_SUPPRESS_DISPATCH_RESTATEMENT"):
        return None
    if not isinstance(session_id, str) or not session_id or not _ID_CHARSET_RE.match(session_id):
        return None
    try:
        cursor_path = os.path.join(
            tempfile.gettempdir(), f"runtime-tripwire-em-dispatch-default-cursor-{session_id}"
        )
        # Review: code-reviewer (Finding 4, P2) -- a predictable path in a
        # shared tempdir is a symlink/TOCTOU exposure: `Path.write_text`
        # follows a pre-planted symlink and overwrites whatever it points
        # at. `os.O_CREAT | os.O_EXCL` refuses to create through an
        # existing path (symlink or otherwise), so a `FileExistsError` here
        # means "cursor already present" rather than "turn one" -- this is
        # a create-time check only; the file this hook itself creates below
        # is a fresh regular file, not attacker-controlled.
        try:
            fd = os.open(cursor_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            pass  # cursor already present -- not turn one, fall through
        else:
            with os.fdopen(fd, "w") as handle:
                handle.write("turn1")
            return None
        if Path(cursor_path).read_text() == "fired":
            return None
        # First eligible turn (turn two or later) -- fire once, then latch.
        Path(cursor_path).write_text("fired")
        return _DISPATCH_DEFAULT_LINE
    except Exception:
        return None


# --- SIZING-LOBBY ARRIVAL ADVISORY ---
#
# An offer naming the sizing room to a fresh session -- not a gate. Latches
# on a ROUTE ACTUALLY TAKEN, observed mechanically by this hook from payloads
# it already receives (see `_sizing_route_taken`), never on turn one merely
# being spent and never on an agent volunteering a sentinel of its own: an EM
# that reads this line on turn one and takes a fresh ask on turn nine still
# sees it. Until latched, it recurs on a prompt that looks like the start of
# novel engineering work rather than a skill invocation or a bare pointer at
# a file, throttled 5 minutes (see the throttle sentinel in
# `_sizing_arrival_advisory`) so this stays an offer that resurfaces rather
# than a nag repeated on every prompt.
_SIZING_ARRIVAL_LINE = (
    "coordinator:sizing is the first move on a fresh ask -- it reads the size and names the "
    "room. Prior art you turn up yourself is input to its probe, not a reason to route around it."
)

_SIZING_ARRIVAL_IMPERATIVE_WORDS = frozenset(
    {
        "fix",
        "implement",
        "add",
        "remove",
        "refactor",
        "update",
        "change",
        "debug",
        "write",
        "create",
        "delete",
        "modify",
        "rewrite",
        "port",
        "migrate",
        "patch",
        "build",
        "design",
        "investigate",
        "review",
    }
)

_SIZING_ARRIVAL_KNOWN_EXTENSIONS = frozenset(
    {
        "py",
        "js",
        "ts",
        "tsx",
        "jsx",
        "md",
        "json",
        "yaml",
        "yml",
        "sh",
        "toml",
        "txt",
        "cfg",
        "ini",
        "rs",
        "go",
        "java",
        "rb",
        "c",
        "h",
        "cpp",
        "hpp",
    }
)

# A token qualifies as path-shaped only if it contains a path separator, or
# its extension is a known code/doc extension AND the pre-extension stem is
# at least 2 characters. This is deliberately narrower than "one dot plus a
# short alnum suffix" -- that shape also matches "e.g.", "i.e.", "2.5s", and
# "v1.2" after punctuation-stripping, none of which are filepaths.
_SIZING_ARRIVAL_HAS_SEPARATOR_RE = re.compile(r"^[\w.-]+/[\w./-]*$")
_SIZING_ARRIVAL_EXTENSION_RE = re.compile(r"^([\w-]{2,})\.([A-Za-z0-9]{1,6})$")


def _looks_path_shaped(token: str) -> bool:
    """See `_SIZING_ARRIVAL_HAS_SEPARATOR_RE`/`_SIZING_ARRIVAL_EXTENSION_RE`
    docstring above -- a token qualifies only via a path separator, or a
    known extension with a >=2-char stem."""
    if _SIZING_ARRIVAL_HAS_SEPARATOR_RE.match(token):
        return True
    match = _SIZING_ARRIVAL_EXTENSION_RE.match(token)
    if match and match.group(2).lower() in _SIZING_ARRIVAL_KNOWN_EXTENSIONS:
        return True
    return False

# If any of these diagnostic/interrogative words appear in the prompt, the
# prompt is NOT a bare pointer regardless of path tokens -- a bug report or a
# question that happens to name a real file ("coordinator/hooks/foo.py is
# broken", "why does foo/bar.py crash?") is a genuine engineering ask, not a
# "what does this file do" pointer, and must force-fire.
_SIZING_ARRIVAL_FORCE_FIRE_WORDS = frozenset(
    {
        "broken",
        "break",
        "breaks",
        "crash",
        "crashes",
        "crashing",
        "fail",
        "fails",
        "failing",
        "leak",
        "leaks",
        "wedge",
        "wedges",
        "hang",
        "hangs",
        "wrong",
        "bug",
        "slow",
        "why",
        "how",
        "should",
        "can",
        "could",
    }
)


# Review: code-reviewer -- Finding 1. Docstring updated to recurrence-until-
# latched semantics: this predicate now runs on every un-latched
# `UserPromptSubmit`, not only turn one.
def _is_bare_pointer_prompt(stripped_prompt: str) -> bool:
    """True only for a short prompt that is essentially a filepath with
    little or no surrounding imperative (e.g. "what does foo/bar.py do?").
    Deliberately narrow: a filepath appearing inside an imperative ask
    ("fix the retry logic in coordinator/hooks/scripts/foo.py") must NOT
    match -- the word-count ceiling and the imperative-word denylist both
    exist to keep this predicate from over-firing on that shape. The path
    token regex and the force-fire vocabulary are equally deliberately
    narrow, in the opposite direction: a false fire here costs one advisory
    line, but a false suppression is silenced only until the next un-latched
    `UserPromptSubmit` (throttle permitting) -- not permanent for the rest
    of the session -- and silences the feature on exactly the case -- a
    genuine engineering ask -- it exists to catch."""
    words = stripped_prompt.split()
    if not words or len(words) > 6:
        return False
    has_path_token = False
    for word in words:
        trimmed = word.strip("?.,!:;\"'()[]")
        if trimmed.lower() in _SIZING_ARRIVAL_FORCE_FIRE_WORDS:
            return False
        if _looks_path_shaped(trimmed):
            has_path_token = True
        if trimmed.lower() in _SIZING_ARRIVAL_IMPERATIVE_WORDS:
            return False
    return has_path_token


# Skill names that count as "the sizing-lobby route was taken" when observed
# in a `PostToolUse` Skill invocation's `tool_input`. `coordinator:pickup` is
# included alongside `coordinator:sizing` because it is the other room the
# sizing lobby routes into on the same PM-ratified map (see
# `docs/wiki/sizing-lobby.md`) -- either is a route taken, not a bare mention.
_SIZING_ROUTE_SKILL_NAMES = ("coordinator:sizing", "coordinator:pickup")


def _sizing_route_taken(event: str, tool_name, tool_input) -> bool:
    """True only when THIS payload is a mechanical observation -- by the
    hook itself, from fields it already receives on every `PostToolUse`
    call -- of a sizing-lobby route actually being taken. Never inferred
    from an agent volunteering a sentinel of its own (see the module's
    Anti-scope: re-keying the latch to something a skill writes on its own
    reproduces the original defect one level down). Two mechanical shapes
    qualify: (a) a `Skill` invocation naming `coordinator:sizing` or
    `coordinator:pickup`, (b) a write landing under `state/sizings/`. Fails
    closed (False) on any other shape, including malformed/missing
    `tool_input` -- the caller decides what False means, this predicate only
    classifies the payload it was given."""
    if event != "PostToolUse":
        return False
    if not isinstance(tool_name, str) or not tool_name:
        return False
    if tool_name == "Skill":
        if not isinstance(tool_input, dict):
            return False
        # Review: code-reviewer -- Finding 3. Exact match against the field
        # that names the invoked skill -- `skill` for the `Skill` tool
        # (schema `{skill, args}`), `command` for the `SlashCommand` tool --
        # never a substring scan of every `tool_input` value. A substring
        # scan would false-latch on e.g. a future `coordinator:sizing-lite`
        # or free text quoting the skill name. Tolerant fallback: an
        # unexpected shape (missing/non-string `skill`/`command`) degrades
        # to not-latching, the safe direction.
        skill = tool_input.get("skill")
        if isinstance(skill, str) and skill in _SIZING_ROUTE_SKILL_NAMES:
            return True
        command = tool_input.get("command")
        if isinstance(command, str) and command in _SIZING_ROUTE_SKILL_NAMES:
            return True
        return False
    if tool_name in ("Write", "Edit", "MultiEdit"):
        if not isinstance(tool_input, dict):
            return False
        path_val = tool_input.get("file_path") or tool_input.get("path")
        if isinstance(path_val, str) and "state/sizings/" in path_val.replace(os.sep, "/"):
            return True
        return False
    return False


def _sizing_arrival_advisory(
    event: str, prompt, session_id: str, tool_name=None, tool_input=None
) -> str | None:
    """The sizing-lobby offer, latched on a ROUTE ACTUALLY TAKEN rather than
    on turn one merely being spent -- an EM that reads this line on turn one
    and takes a fresh ask on turn nine still sees it (this is the whole
    point: see the module comment above `_SIZING_ARRIVAL_LINE`). The latch
    (tempdir cursor, per-session) is set ONLY by `_sizing_route_taken`
    observing a mechanical signal in the payload this hook already
    receives -- never by an agent volunteering a sentinel of its own. Until
    latched, the offer recurs on a novel-work-shaped `UserPromptSubmit`
    prompt, throttled 5 minutes (separate tempdir sentinel, same pattern as
    the 5-minute self-throttle a few lines below in `main()`) so this stays
    an offer that resurfaces rather than a nag repeated on every prompt."""
    if not isinstance(session_id, str) or not session_id:
        return None
    # Review: code-reviewer -- Finding 3. Defense-in-depth, not the primary
    # boundary: `main()` already neutralizes a non-matching `session_id` to
    # `""` before every call site reachable from it, so this re-check is
    # currently unreachable-false on every live path. Kept because a future
    # caller of this function need not route through `main()`'s
    # neutralization first.
    if not _ID_CHARSET_RE.match(session_id):
        return None

    latch_path = os.path.join(
        tempfile.gettempdir(), f"runtime-tripwire-em-sizing-arrival-latch-{session_id}"
    )
    try:
        if _sizing_route_taken(event, tool_name, tool_input):
            Path(latch_path).touch()
    except Exception:
        # A failure observing/latching the route must never take down the
        # rest of the advisory -- fail-open per module contract.
        pass

    try:
        if os.path.isfile(latch_path):
            return None
    except Exception:
        return None

    if event != "UserPromptSubmit":
        return None

    try:
        throttle_path = os.path.join(
            tempfile.gettempdir(), f"runtime-tripwire-em-sizing-arrival-cursor-{session_id}"
        )
        throttle_seconds = 300
        if os.path.isfile(throttle_path):
            if (time.time() - os.path.getmtime(throttle_path)) < throttle_seconds:
                return None
    except Exception:
        return None

    if not isinstance(prompt, str):
        return None
    stripped = prompt.strip()
    if not stripped:
        return None
    if stripped.startswith("/"):
        return None
    try:
        if _is_bare_pointer_prompt(stripped):
            return None
    except Exception:
        return None

    try:
        # Touch the offer throttle ONLY on an actual fire -- a suppressed
        # prompt (bare pointer, slash-prefixed, empty) must not consume the
        # recurrence budget, matching `main()`'s own "sentinel written only
        # if something fired" convention a few lines below.
        Path(throttle_path).touch()
    except Exception:
        return None

    return _SIZING_ARRIVAL_LINE


def _emit_advisory(
    parts,
    event="PostToolUse",
    on_success=None,
    prompt=None,
    session_id=None,
    tool_name=None,
    tool_input=None,
) -> int:
    """Compose the non-empty entries of `parts` into one hookSpecificOutput
    envelope and write it to stdout. No-op (no stdout write) when every part
    is falsy. Always returns 0 -- this hook is advisory-only and must never
    block Stop/UserPromptSubmit/PostToolUse.

    `on_success`, if given, is called ONLY after the stdout write actually
    succeeds -- never on the empty-parts no-op path, never if the write
    raises. Used by ZERO-TOOL-USE-DETECT-SURFACE to advance its per-session
    surfaced-cursor exactly-once, strictly after the text it gates has
    actually reached stdout (see `_check_zero_tool_use_surface`'s ordering
    requirement). Pre-existing callers pass no `on_success` and are
    unaffected.

    `prompt` and `session_id`, if given, feed the sizing-lobby arrival
    advisory (see `_sizing_arrival_advisory`) -- both default to None, which
    makes that stanza a no-op, so pre-existing callers that have neither in
    scope are unaffected. `tool_name`/`tool_input`, if given, feed the SAME
    stanza's route-taken latch (see `_sizing_route_taken`) -- also default to
    None, under which the latch simply never observes a route this call and
    the stanza falls through to its ordinary prompt-driven behavior."""
    text_parts = [p for p in parts if p]

    # The dispatch-default line and the sizing-arrival offer both ride the
    # SAME envelope as every other advisory this hook emits (module
    # contract: one envelope per fire, never a second write). Prepended so
    # neither can end up behind a variable-length tripwire list, and added
    # after `text_parts` is computed so `had_caller_parts` still reflects
    # only the caller's own content -- that is what keeps `on_success`
    # exactly-once (see its guard below).
    had_caller_parts = bool(text_parts)
    # Review: code-reviewer -- Finding 4. Each prepend below puts its own
    # line in FRONT of everything accumulated so far, so the two prepends
    # below emit in the REVERSE of code order: sizing_arrival ends up ahead
    # of restatement in the final envelope even though restatement is
    # computed and prepended first. This is deliberate (see the comment
    # above) -- called out here so a reader doesn't need to trace the
    # prepend chain to see it.
    restatement = _dispatch_default_restatement(event, session_id)
    if restatement:
        text_parts = [restatement] + text_parts
    try:
        sizing_arrival = _sizing_arrival_advisory(
            event, prompt, session_id, tool_name=tool_name, tool_input=tool_input
        )
    except Exception:
        sizing_arrival = None
    if sizing_arrival:
        text_parts = [sizing_arrival] + text_parts

    if not text_parts:
        return 0
    combined = "\n\n".join(text_parts)
    wrote = False
    try:
        out = {
            "hookSpecificOutput": {
                "hookEventName": event,
                "additionalContext": combined,
            }
        }
        sys.stdout.write(json.dumps(out))
        sys.stdout.write("\n")
        wrote = True
    except Exception:
        pass
    # `had_caller_parts` gate: the dispatch-default line can now trigger a stdout
    # write on a fire where the caller supplied nothing. Without this predicate
    # that write would advance the zero-tool-use surfaced-cursor for text never
    # emitted, silently swallowing the next real detection.
    #
    # Review: code-reviewer -- Finding 1. Currently unreachable as a live
    # protection: `_check_zero_tool_use_surface` never returns a non-None
    # `on_success` (`_advance`) except paired with truthy `text` (every
    # early-return path is `return None, None`), so whenever `on_success is
    # not None` here, `text_parts` already contained that truthy text before
    # the restatement was prepended and `had_caller_parts` is already `True`.
    # Retained as defense-in-depth against a future decoupling of
    # message-content from the advance callback -- mirrors this file's own
    # belt-and-braces posture (see the empty-text branch in
    # `_check_zero_tool_use_surface`, ~line 937).
    if wrote and had_caller_parts and on_success is not None:
        try:
            on_success()
        except Exception:
            pass
    return 0


# ---------------------------------------------------------------------------
# EM-REPORT-ALTITUDE (see module docstring's own section, above, for the
# full design rationale). Round-trips `hooks.em_report_altitude` on Stop
# only, mirroring `_check_zero_tool_use_surface`'s engine-round-trip shape.
# ---------------------------------------------------------------------------


def _em_report_altitude_precondition(payload) -> bool:
    """Cheap local precondition, hard requirement before any claude-klabauter
    round-trip: proceed only when the EM's just-finished reply text is
    actually obtainable somehow -- either inline (`last_assistant_message`)
    or via a transcript file that exists on disk right now
    (`transcript_path`). Neither present means there is nothing to measure,
    so callers must skip straight to contributing nothing, without
    resolving claude-klabauter, importing `coordinator_core`, or round-tripping the
    engine at all.

    Deliberately NOT a message-length prefilter -- do not add one later. In
    the measured corpus that motivated this detector, real citation-density
    violations occurred in replies of 10, 16 and 29 words, well under any
    reasonable length threshold, so gating on length would silently exempt
    most of what this detector exists to catch.
    """
    if not isinstance(payload, dict):
        return False
    msg = payload.get("last_assistant_message")
    if isinstance(msg, str) and msg.strip():
        return True
    tpath = payload.get("transcript_path")
    if isinstance(tpath, str) and tpath:
        try:
            return os.path.isfile(tpath)
        except Exception:
            return False
    return False


def _check_em_report_altitude(payload, git_root: str, hook_event: str, session_id: str = ""):
    """EM-REPORT-ALTITUDE surfacer. Returns the engine's advisory text, or
    None when there is nothing to surface -- including every fail-open path
    below (engine unresolvable/unimportable/erroring, malformed response) and
    the once-per-session cap below.

    Gated hard to `Stop` -- see module docstring for why the other two
    registered events are meaningless for this measurement. Advisory only:
    the caller composes the return value into the same additionalContext
    envelope as every other advisory this hook emits; this function itself
    never writes stdout/stderr and never raises past its own boundary.

    ONCE-PER-SESSION CAP (added 2026-07-31, PM-observed live): a repeat
    "lead with the decision" advisory that re-fires on every long Stop reply
    trains the reader to tune it out, defeating the point of the nudge. This
    is also the fix for the paired duplicate-registration symptom -- this
    hook script is registered as a Stop hook on two delivery surfaces at
    once, so a single logical Stop invokes this function twice; the sentinel
    check below collapses that second same-Stop call to a no-op the same way
    it collapses a later Stop in the same session, without this function
    needing to know or care that the duplicate registration exists.
    Sentinel path mirrors this file's own `_check_push_failures` cursor
    convention and `nudge-multiwave-workflow.py`'s `nudged_sentinel`
    (`<git_root>/.git/coordinator-sessions/<session_id>/<name>`) -- not a
    new pattern. `session_id` is expected pre-validated by `main()` via
    `_ID_CHARSET_RE` before this function is ever called; re-validated here
    too since this function is directly unit-testable outside that call
    path.
    """
    if os.environ.get("COORDINATOR_EM_REPORT_ALTITUDE_OFF"):
        return None

    if hook_event != "Stop":
        return None

    if not _em_report_altitude_precondition(payload):
        return None

    sentinel_path = None
    if isinstance(session_id, str) and session_id and _ID_CHARSET_RE.match(session_id):
        # Rooted at the git COMMON dir (see `_resolve_git_common_dir`'s
        # docstring), never `<git_root>/.git` -- that path is a FILE in a
        # worktree, so the pre-fix join silently never persisted the
        # sentinel and the once-per-session cap re-fired forever. An
        # unresolvable common dir leaves `sentinel_path` None, which the
        # write side below already treats as "no sentinel to claim" --
        # fail-open toward "not yet fired", never "always fired".
        common_dir = _resolve_git_common_dir(git_root)
        if common_dir:
            sentinel_path = os.path.join(
                common_dir, "coordinator-sessions", session_id, "em-report-altitude-nudged"
            )
        # Read-side failure direction: an unreadable/unstat-able sentinel
        # (permission error, transient IO, race) must NOT be treated as
        # "already fired" -- that would permanently suppress the nudge for
        # the rest of the session on a single filesystem hiccup, which is
        # worse than the duplicate-firing bug this cap exists to fix.
        # Degrade toward "not yet fired" (fall through and let the engine
        # round-trip decide), not toward "always fired".
        try:
            if sentinel_path and os.path.isfile(sentinel_path):
                return None
        except Exception:
            pass

    # DIRECT CALL, not an IPC round-trip -- and this is load-bearing, not a
    # style choice. `Stop` does not route through the claude-klabauter IPC daemon, so
    # `hooks.em_report_altitude` is deliberately NOT `@register_op`-registered
    # engine-side; dispatching it as a JSON-RPC method resolves to no handler,
    # the round-trip raises, and this function's own fail-open `except`
    # swallows it -- leaving a detector that is wired, green, and permanently
    # silent. That exact combination was live for one build of this file and
    # produced no error anywhere, which is why it is called out here rather
    # than merely fixed: reading either side alone looks correct. The on-point
    # precedent is the sibling Stop-hook shim
    # (`nudge-harness-directive-dispatch.py`), which imports the engine module
    # and calls `op()` directly for the same reason. Do not "restore" the
    # dispatch_message form without first confirming the op is registered AND
    # exercising this script end-to-end on a real Stop payload.
    #
    # It is also strictly cheaper: no asyncio loop and no daemon dependency on
    # a hook whose registered timeout is 5s.
    try:
        root = _resolve_claude_klabauter_root()
        if not root:
            return None
        if root not in sys.path:
            sys.path.insert(0, root)
        from coordinator_core.hooks import em_report_altitude as _op

        result = _op.op(payload)
    except Exception:
        return None  # engine unresolvable/unimportable/erroring -> fail-open

    # Never trust the engine's return SHAPE, only its intent -- mirrors
    # nudge-harness-directive-dispatch.py's own code-reviewer-annotated
    # tolerance block on exactly this pattern (Findings 1-2 there): a
    # truthy non-dict result, or a missing/non-str/empty "message", both
    # degrade to None here rather than raising or emitting garbage.
    if not isinstance(result, dict):
        return None
    message = result.get("message")
    if not isinstance(message, str) or not message:
        return None

    # Sentinel is written ONLY here, at the point a real non-empty message is
    # in hand and about to be returned -- writing it any earlier (e.g. before
    # the engine round-trip) would burn the session's single allowance on a
    # run where the engine has nothing to surface, and the nudge would then
    # never fire at all this session. Write-side failure direction, deliberately
    # asymmetric: EEXIST on the exclusive create means a peer copy already
    # surfaced this same advisory -> stay silent. Any OTHER error (missing
    # git_root, unwritable .git, read-only filesystem, or the parent-dir
    # `mkdir` failing) must NOT raise and must NOT suppress this emission --
    # the message already in hand is real and still surfaces; at worst the
    # cap fails to stick and a later Stop in the same session re-fires.
    # The claim is an ATOMIC exclusive create, and losing it SUPPRESSES this
    # emission -- both properties are load-bearing. The duplicate Stop
    # registrations run concurrently (measured: two injections stamped at the
    # same millisecond), so the read-side `os.path.isfile` check above races
    # -- both copies observe "not yet fired" before either writes, and a
    # plain `touch()` lets both emit. `O_CREAT | O_EXCL` makes exactly one
    # copy the winner. Do not relax this back to touch()/exist_ok.
    #
    # Review: code-reviewer -- Finding 1. `mkdir(parents=True, exist_ok=True)`
    # is kept OUTSIDE the FileExistsError-catching try below -- it can itself
    # raise FileExistsError when a path component exists but is not a
    # directory (exist_ok only suppresses the "already a directory" case),
    # which sharing one try/except with the exclusive `os.open` would
    # misclassify as "a peer already claimed the sentinel" and wrongly
    # suppress a real, in-hand message. Mirrors the sibling precedent
    # `offer-exploration-tier-dispatch.py:_claim_offer_marker`, which keeps
    # its own `os.makedirs(..., exist_ok=True)` unguarded and wraps only the
    # `os.open(..., O_EXCL, ...)` call in the FileExistsError-catching try.
    if sentinel_path:
        try:
            Path(sentinel_path).parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        try:
            os.close(os.open(sentinel_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644))
        except FileExistsError:
            return None
        except Exception:
            pass

    return message


# ---------------------------------------------------------------------------
# SUBAGENT-ARRIVAL-CHECK (added 2026-07-30, restoring an arrival gate onto
# the runtime-overrun nudge after the former SUBAGENTSTOP TRIGGER-LOSS branch
# was retired from this file -- everything past the max-age cap and
# per-model threshold used to flow straight to a nudge with no check that
# the dispatch was still actually running. Calls the claude-klabauter op
# `hooks.subagent_arrival_check` (coordinator_core/hooks/
# subagent_arrival_check.py) for exactly the dispatch row about to be
# nudged -- never for every row in dispatched-agents.txt -- mirroring
# `_check_zero_tool_use_surface`'s claude-klabauter-resolve pattern (resolve root,
# sys.path insert, import the op module, `asyncio.run(dispatch_message(...))`)
# rather than inventing a new one.
# ---------------------------------------------------------------------------


def _check_subagent_arrival(transcript_path: str, agent_id: str) -> str:
    """Classify one about-to-be-nudged dispatch as "arrived" / "running" /
    "unknown" via the `hooks.subagent_arrival_check` op. Returns "unknown"
    on ANY failure -- unresolvable engine, import error, a malformed/
    non-dict response, or a missing `transcript_path`/`agent_id`.

    As of 2026-07-31 the caller nudges ONLY on a confirmed "running" state;
    both "arrived" and "unknown" suppress. This reverses the 2026-07-30
    "fail toward firing on unknown" contract this docstring previously
    stated -- a subagent transcript proved not durable in practice (14
    transcript files against 3,083 distinct agentIds in the audit log on
    this repo), making "unknown" the overwhelmingly common no-information
    case rather than evidence of a live agent. This is the ONLY completion/
    liveness signal the caller consults -- see this file's module
    docstring, NOT-A-COMPLETION-LOG section, for why `agent-audit.jsonl` is
    NOT also cross-checked (it is a dispatch log, not a completion log; a
    same-day 2026-07-31 attempt to restore such a check was reverted once
    that was verified directly).

    Cost gate: call ONLY for a dispatch that has already cleared the
    max-age cap and the per-model runtime threshold in the caller's loop --
    i.e. one that is actually about to be nudged, never speculatively for
    every tracked row. Same round-trip-affordability reasoning as
    `_check_zero_tool_use_surface`'s own cost gate.

    DR-047 boundary: `transcript_path` (the PARENT session's transcript path,
    straight off the payload) and `agent_id` are passed through to the op
    UNOPENED -- this function must never itself open a transcript or derive
    a subagent transcript path. Path derivation and the file read are the
    engine's job (see subagent_arrival_check.py's own module docstring).

    ID NAMESPACE -- forward the row's id VERBATIM; do not translate it here.
    A named teammate's row in dispatched-agents.txt carries the EM-side
    canonical form `<name>@session-<short8>`, while its transcript on disk is
    `agent-a<name>-<16 hex>.jsonl`. The forward map (`_resolve_subagent_identity`
    above) is lossy -- it drops the 16-hex suffix -- so the reverse needs a
    directory probe, which is path derivation, which is the engine's side of
    DR-047. Translating (or "correcting") the id here is the wrong repair for
    an unknown-state named teammate: the op accepts both namespaces and
    resolves between them itself.
    """
    if not transcript_path or not agent_id:
        return "unknown"
    try:
        root = _resolve_claude_klabauter_root()
        if not root:
            return "unknown"
        if root not in sys.path:
            sys.path.insert(0, root)
        from coordinator_core.hooks import subagent_arrival_check as _op  # noqa: F401
        from coordinator_core.ipc import dispatch_message

        msg: dict = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "hooks.subagent_arrival_check",
            "params": {
                "transcript_path": transcript_path,
                "agent_id": agent_id,
            },
        }
        response = asyncio.run(dispatch_message(msg))
    except Exception:
        return "unknown"  # engine unresolvable/unimportable/erroring -> fail-open

    result = response.get("result") if isinstance(response, dict) else None
    if not isinstance(result, dict):
        return "unknown"
    state = result.get("state")
    if state not in ("arrived", "running", "unknown"):
        return "unknown"
    return state


def main() -> int:
    raw = _read_stdin(2.0)

    try:
        payload = json.loads(raw) if raw else {}
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    hook_event = _hook_event_name(payload)

    session_id = payload.get("session_id") or ""
    if not isinstance(session_id, str):
        session_id = ""

    tool_response = payload.get("tool_response")
    if not isinstance(tool_response, dict):
        tool_response = {}
    tool_response_agent_id = tool_response.get("agentId") or ""
    if not isinstance(tool_response_agent_id, str):
        tool_response_agent_id = ""

    # SIZING-LOBBY ARRIVAL ADVISORY route-latch inputs (see
    # `_sizing_route_taken`) -- extracted here, alongside the pre-existing
    # `tool_response` extraction above, rather than assumed absent from the
    # payload: nothing read `tool_name`/`tool_input` before this stanza
    # needed them.
    tool_name = payload.get("tool_name")
    if not isinstance(tool_name, str):
        tool_name = None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = None

    # Security: reject SESSION_IDs with path-traversal characters before any
    # path construction. Non-empty ids that deviate are neutralized to empty
    # and fall through to the absent-id exit-0 below -- same no-op path.
    if session_id and not _ID_CHARSET_RE.match(session_id):
        session_id = ""

    # Fail-open: no session id means we cannot do anything useful.
    if not session_id:
        return 0

    agent_id = payload.get("agent_id") or ""
    if not isinstance(agent_id, str):
        agent_id = ""

    git_root = _git_root()
    if not git_root:
        return 0

    state_root = _resolve_state_root(git_root)

    # Rooted at the git COMMON dir, never `<git_root>/.git` (see
    # `_resolve_git_common_dir`'s docstring) -- in a worktree that path is a
    # FILE, so the pre-fix `git_root + ".git"` join silently never persisted.
    # Fail-open: an unresolvable common dir degrades `sessions_dir`/
    # `agents_dir` to "" below, and every consumer guards on that emptiness
    # rather than building a path from it.
    common_dir = _resolve_git_common_dir(git_root)
    sessions_dir = os.path.join(common_dir, "coordinator-sessions") if common_dir else ""
    agents_dir = os.path.join(sessions_dir, ".agents") if sessions_dir else ""

    # --- Subagent-detect inverse: primary path (SESSION_ID as an agent dir) ---
    if agents_dir and os.path.isfile(os.path.join(agents_dir, session_id, "em-session-id.txt")):
        return 0

    # --- Resolver-based fallback for named teammates (additive, not replacement) ---
    if agent_id:
        canonical = _resolve_subagent_identity(agent_id, session_id)
        if (
            canonical
            and agents_dir
            and os.path.isfile(os.path.join(agents_dir, canonical, "em-session-id.txt"))
        ):
            return 0

    # Zero-tool-use-specific session dir, rooted at the git COMMON dir
    # (worktree-safe) -- a SEPARATE resolution from `sessions_dir` above,
    # never a repoint of that shared variable (which the pre-existing
    # dispatch-tracking loop, `_check_push_failures`, and the `.agents`
    # lookups above all still use byte-identically). See
    # `_resolve_zero_tool_use_sessions_dir`'s docstring.
    #
    # Review: code-reviewer -- Finding 4. Resolved here, below the two
    # subagent-detect early returns above, not before them -- this
    # git-common-dir walk is wasted work on every Stop fire from inside a
    # subagent's own session, the common case those early returns exist to
    # short-circuit.
    try:
        zero_tool_use_sessions_dir = _resolve_zero_tool_use_sessions_dir(git_root)
    except Exception:
        zero_tool_use_sessions_dir = ""

    # --- AUTO-PUSH-MID-SESSION-DETECT (see _check_push_failures docstring) ---
    # Computed here, once EM-session-ness is confirmed, independently of the
    # runtime-tripwire dispatch-tracking logic below (this repo may have zero
    # dispatched agents this session and still have a mid-session push-failure
    # flood to surface). Wrapped so a bug here can never take down the
    # existing runtime-tripwire advisory -- fail-open per module contract.
    try:
        push_failure_msg = _check_push_failures(git_root, session_id)
    except Exception:
        push_failure_msg = None

    # --- ZERO-TOOL-USE-DETECT-SURFACE (see module docstring + the section
    # immediately above _emit_advisory). Independently wrapped, same as the
    # push-failure block above -- a bug here must never take down either
    # pre-existing advisory. Gated to UserPromptSubmit inside the function
    # itself (checked first, before any stat call), so this costs nothing
    # extra on Stop/PostToolUse:Agent fires. ---
    try:
        zero_tool_use_msg, _zero_tool_use_advance = _check_zero_tool_use_surface(
            git_root, session_id, zero_tool_use_sessions_dir, hook_event
        )
    except Exception:
        zero_tool_use_msg, _zero_tool_use_advance = None, None

    # --- EM-REPORT-ALTITUDE (see module docstring + the section immediately
    # above `main()`). Independently wrapped, same as the two blocks above --
    # a bug here must never take down either pre-existing advisory. Gated to
    # Stop inside the function itself, so this costs nothing extra on
    # UserPromptSubmit/PostToolUse:Agent fires. ---
    try:
        em_report_altitude_msg = _check_em_report_altitude(
            payload, git_root, hook_event, session_id
        )
    except Exception:
        em_report_altitude_msg = None

    # --- Subagent-overrun tripwire stand-down (PM ruling, 2026-07-31; see
    # _SUBAGENT_OVERRUN_TRIPWIRE_ENABLED docstring above imports). When
    # disabled, skip the entire dispatch-tracking / overrun-nudge section
    # below and emit only the three surviving advisories (push-failure,
    # zero-tool-use, EM-report-altitude), matching the shape the existing
    # self-throttle early-return already uses. ---
    if not _SUBAGENT_OVERRUN_TRIPWIRE_ENABLED:
        return _emit_advisory(
            [push_failure_msg, zero_tool_use_msg, em_report_altitude_msg],
            hook_event,
            on_success=_zero_tool_use_advance,
            prompt=payload.get("prompt"),
            session_id=session_id,
            tool_name=tool_name,
            tool_input=tool_input,
        )

    # --- Self-throttle: 5 minutes ---
    tmpdir = tempfile.gettempdir()
    throttle_sentinel = os.path.join(tmpdir, f"runtime-tripwire-em-throttle-{session_id}")
    throttle_seconds = 300

    try:
        if os.path.isfile(throttle_sentinel):
            sentinel_mtime = os.path.getmtime(throttle_sentinel)
            now_f = time.time()
            if (now_f - sentinel_mtime) < throttle_seconds:
                return _emit_advisory(
                    [push_failure_msg, zero_tool_use_msg, em_report_altitude_msg],
                    hook_event,
                    on_success=_zero_tool_use_advance,
                    prompt=payload.get("prompt"),
                    session_id=session_id,
                    tool_name=tool_name,
                    tool_input=tool_input,
                )
    except Exception:
        pass
    # Throttle sentinel is written AFTER the dispatch loop, only if at least
    # one nudge fired this pass -- below-threshold passes do NOT consume the
    # throttle, so the first threshold-crossing fires immediately instead of
    # being delayed up to 5 min. (This throttle governs the runtime-tripwire
    # dispatch nudge only -- the push-failure advisory above is unaffected by
    # it and is emitted above regardless.)

    dispatch_file = (
        os.path.join(sessions_dir, session_id, "dispatched-agents.txt") if sessions_dir else ""
    )
    if not dispatch_file or not os.path.isfile(dispatch_file):
        return _emit_advisory(
            [push_failure_msg, zero_tool_use_msg, em_report_altitude_msg],
            hook_event,
            on_success=_zero_tool_use_advance,
            prompt=payload.get("prompt"),
            session_id=session_id,
            tool_name=tool_name,
            tool_input=tool_input,
        )

    now = int(time.time())
    first_fire_list = ""
    restage_list = ""

    try:
        restage_seconds = int(os.environ.get("RUNTIME_TRIPWIRE_RESTAGE_SECONDS", "300") or "300")
    except ValueError:
        restage_seconds = 300
    try:
        max_track_minutes = int(os.environ.get("RUNTIME_TRIPWIRE_MAX_TRACK_MIN", "90") or "90")
    except ValueError:
        max_track_minutes = 90

    fire_log = os.path.join(state_root, "runtime-tripwire-fire-log.tsv")

    try:
        with open(dispatch_file, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except Exception:
        lines = []

    for raw_line in lines:
        line = raw_line.rstrip("\n").rstrip("\r")
        parts = line.split("\t")
        agent_id_row = parts[0] if len(parts) > 0 else ""
        model = parts[1] if len(parts) > 1 else ""
        subagent_type = parts[2] if len(parts) > 2 else ""
        dispatched_at_str = parts[3] if len(parts) > 3 else ""

        if not agent_id_row:
            continue

        # Security: same charset guard as SESSION_ID, applied to agentId
        # before any path/tempfile construction.
        if not _ID_CHARSET_RE.match(agent_id_row):
            continue

        # Skip-if-returning: the triggering PostToolUse event's own return.
        if tool_response_agent_id and tool_response_agent_id == agent_id_row:
            continue

        # Deliberately NO `agent-audit.jsonl` completion cross-check here --
        # see the module docstring's NOT-A-COMPLETION-LOG section. That file
        # is a dispatch log (written by the same PostToolUse:Agent event as
        # dispatched-agents.txt), not a completion log; every dispatched row
        # is present in it by construction regardless of whether it ever
        # returned, so a membership check against it would suppress every
        # row unconditionally. The arrival oracle below is the only real
        # completion/liveness signal this loop has.

        # Backward-compat: missing/non-numeric dispatched_at -> legacy record.
        if not dispatched_at_str.isdigit():
            continue
        dispatched_at = int(dispatched_at_str)
        if dispatched_at == 0:
            continue

        elapsed_min = (now - dispatched_at) // 60

        # Max-age cap (skip-if-too-old).
        if elapsed_min >= max_track_minutes:
            continue

        threshold_min = _runtime_threshold_minutes(model)
        if elapsed_min < threshold_min:
            continue

        agent_sentinel = os.path.join(tmpdir, f"runtime-tripwire-em-{agent_id_row}")
        restage_sentinel = os.path.join(tmpdir, f"runtime-tripwire-em-restage-{agent_id_row}")

        # SENTINEL-STATE-PRE-GATE: decide whether this row can produce ANY
        # output this call BEFORE paying the arrival-check engine
        # round-trip below -- a permanently-silenced row (both sentinels
        # set) or one still inside its restage wait window produces zero
        # output regardless of arrival state, so neither case should
        # reach the engine at all.
        agent_sentinel_exists = os.path.isfile(agent_sentinel)
        if agent_sentinel_exists:
            if os.path.isfile(restage_sentinel):
                continue  # already re-nudged -> silence
            try:
                first_fire_mtime = os.path.getmtime(agent_sentinel)
            except Exception:
                first_fire_mtime = 0
            since_first = now - int(first_fire_mtime)
            if since_first < restage_seconds:
                continue

        # SUBAGENT-ARRIVAL-CHECK: only called here, past the max-age cap,
        # the per-model threshold, and the sentinel-state pre-gate above --
        # i.e. exactly the row that is about to reach a first-fire or
        # restage decision this call. As of 2026-07-31 this is the ONLY
        # completion/liveness signal consulted: nudge ONLY on a confirmed
        # "running"; both "arrived" and "unknown" suppress. "unknown" is no
        # longer fail-toward-firing here because a subagent transcript is
        # not durable (see the module docstring's SUBAGENT-ARRIVAL-CHECK
        # section for the measured unknown rate) -- and there is
        # deliberately no `agent-audit.jsonl` cross-check to fall back on
        # (see the NOT-A-COMPLETION-LOG section: that file is a dispatch
        # log, not a completion log, and a membership check against it
        # would suppress every row unconditionally).
        transcript_path_val = payload.get("transcript_path")
        if not isinstance(transcript_path_val, str):
            transcript_path_val = ""
        try:
            arrival_state = _check_subagent_arrival(transcript_path_val, agent_id_row)
        except Exception:
            arrival_state = "unknown"
        if arrival_state != "running":
            continue

        try:
            os.makedirs(os.path.dirname(fire_log), exist_ok=True)
        except Exception:
            pass

        if agent_sentinel_exists:
            # First fire already happened and since_first >=
            # restage_seconds (verified in the pre-gate above) -- time
            # for the single re-nudge.
            try:
                Path(restage_sentinel).touch()
            except Exception:
                pass
            restage_list += f"  {agent_id_row} | {model} | {elapsed_min} min\n"
            try:
                with open(fire_log, "a", encoding="utf-8") as fh:
                    fh.write(
                        "%s\t%s\t%s\t%s\t%s\n"
                        % (
                            time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            agent_id_row,
                            model,
                            elapsed_min,
                            "em-side-restage",
                        )
                    )
            except Exception:
                pass
        else:
            try:
                Path(agent_sentinel).touch()
            except Exception:
                pass
            # Write wrap-signal artifact to agent session dir if present --
            # the agent still believed to be running.
            agent_dir = os.path.join(agents_dir, agent_id_row)
            if os.path.isdir(agent_dir):
                try:
                    with open(
                        os.path.join(agent_dir, "wrap-requested.txt"),
                        "w",
                        encoding="utf-8",
                    ) as fh:
                        fh.write(
                            "%s wrap-requested: em-check first-fire at %s min elapsed (%s)\n"
                            % (
                                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                elapsed_min,
                                model,
                            )
                        )
                except Exception:
                    pass
            first_fire_list += f"  {agent_id_row} | {model} | {elapsed_min} min\n"
            try:
                with open(fire_log, "a", encoding="utf-8") as fh:
                    fh.write(
                        "%s\t%s\t%s\t%s\t%s\n"
                        % (
                            time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            agent_id_row,
                            model,
                            elapsed_min,
                            "em-side",
                        )
                    )
            except Exception:
                pass

    # Throttle sentinel -- write only if at least one nudge fired this pass.
    if first_fire_list or restage_list:
        try:
            Path(throttle_sentinel).touch()
        except Exception:
            pass

    # Nothing to report from the runtime-tripwire dispatch tracker -- the
    # push-failure advisory (if any) may still stand alone.
    if not first_fire_list and not restage_list:
        return _emit_advisory(
            [push_failure_msg, zero_tool_use_msg, em_report_altitude_msg],
            hook_event,
            on_success=_zero_tool_use_advance,
            prompt=payload.get("prompt"),
            session_id=session_id,
            tool_name=tool_name,
            tool_input=tool_input,
        )

    # --- Emit awareness additionalContext ---
    nudge = ""

    if first_fire_list:
        nudge = (
            "RUNTIME TRIPWIRE — one or more dispatched agents are past their runtime threshold:\n\n"
            f"{first_fire_list}"
            "\nEach has received its own wrap-shape nudge (agent-side hook). Agent owns the wrap "
            "judgment; you (EM) hold authority (trust-but-verify). If an agent reports continued "
            "progress and you concur on visible disk artifacts, let it finish. Otherwise plan a "
            "successor dispatch or TaskStop."
        )

    if restage_list:
        if nudge:
            nudge += "\n\n"
        nudge += (
            "RUNTIME TRIPWIRE — RE-NUDGE (flagged 5+ minutes ago, still reads as running):\n\n"
            f"{restage_list}"
            "\nReassess explicitly: TaskStop, plan a successor dispatch, or accept the runaway. "
            "After this fire, the hook is silent for these dispatches — the next decision is yours."
        )

    nudge += "\n\nReference: docs/wiki/runtime-tripwire.md"

    return _emit_advisory(
        [nudge, push_failure_msg, zero_tool_use_msg, em_report_altitude_msg],
        hook_event,
        on_success=_zero_tool_use_advance,
        prompt=payload.get("prompt"),
        session_id=session_id,
        tool_name=tool_name,
        tool_input=tool_input,
    )


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Absolute fail-open floor -- an advisory hook must never non-zero-exit
        # or crash the harness on an unforeseen error.
        sys.exit(0)
