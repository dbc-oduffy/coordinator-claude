#!/usr/bin/env python3
"""PostToolUse(*) naked-Python direct port of the former bash EM-side check.

Purpose: Fires in the EM session. Emits an awareness additionalContext for
         push-failure, hooks.json-staleness, zero-tool-use, and
         session-baton-mint conditions. The former subagent-overrun
         dispatch-tracking nudge (dispatched-agents.txt scan +
         model-specific runtime threshold) was stood down 2026-07-31 and
         excised entirely -- see the SUBAGENT-ARRIVAL-CHECK note below.

This is a SELF-CONTAINED naked-Python hook, not an engine-op stub: no
engine-repo op exists for this EM-side disk-bookkeeping check (grepped
coordinator_core/hooks + coordinator_core/ops for "dispatched-agents.txt",
"em-check", "wrap-requested" — only track_dispatched_agents.py [the WRITER
of dispatched-agents.txt] and postuse_advisory_dispatch.py [the AGENT-side
port of the former bash advisory hook, an entirely different script that fires
INSIDE the subagent and keeps in-memory-only bark-once state] came back;
neither implements this EM-side disk-sentinel + fire-log + wrap-requested.txt
artifact scan). Per the W5 straggler-port contract: port the logic directly
into a self-contained hook rather than inventing a new engine-repo op.

Spec backlink: docs/plans/2026-06-08-runtime-tripwire-background-executors.md § C3b
Wiki: docs/wiki/hook-best-practices/runtime-tripwire.md

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
  stdin   -- PostToolUse JSON (session_id, agent_id, ...)
  stdout  -- one hookSpecificOutput JSON envelope when >=1 dispatch is past
             threshold; NOTHING otherwise
  exit 0  -- ALWAYS, unconditionally, on every code path (advisory hook;
             must fail-open -- mirrors the bash oracle's `set -uo pipefail`
             with -e deliberately omitted + explicit `|| true` guards).

Simplification vs the bash oracle (documented, non-decisional): the fire-log
target directory uses an INLINE mirror of coordinator_state_root's Rule 5
(meta-repo check via realpath(git_root) == realpath(<claude-home>) -> the engine repo's
root /state, else GIT_ROOT/state) rather than shelling out to the full
claude-home/coordinator-claude-klabauter-root resolver chain. This affects only WHERE
the best-effort calibration fire-log TSV row lands, never WHETHER/WHAT a
nudge fires -- the advisory/deny decision surface is byte-faithful.
resolve_subagent_identity is similarly reimplemented as a local pure
function (mirrors the retired bash identity-resolution logic byte-for-byte,
and is IDENTICAL to the one already ported into the engine repo's
postuse_advisory_dispatch.py::_resolve_subagent_identity) instead of
shelling out -- pure function, no filesystem I/O, so no fidelity loss.

Negative-spec:
  - Does NOT block execution -- PostToolUse is advisory only.
  - Does NOT fire for a subagent-side session (early-exits to the agent-side
    hook's territory) -- see the two-path subagent-detect block below.
  - Does NOT track subagent dispatch overrun any more -- see the
    SUBAGENT-ARRIVAL-CHECK note below for the excised mechanism and its
    former `RUNTIME_TRIPWIRE_*` escape-hatch env vars.

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
fire -- with the engine-repo round-trip (no `coordinator_core` import, no
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
never stderr, never plain stdout. See docs/wiki/coordinator-tripwires/
§ ZERO-TOOL-USE-DETECT for the full two-stage design and Stage 1
(`hooks/scripts/subagent-zero-tool-use-detect.py`, SubagentStop).

SUBAGENT-ARRIVAL-CHECK -- REMOVED (PM ruling 2026-07-31 stood it down;
excised entirely on the finding that the gate had been `False` since, per
the overengineering review that also removed the ~620 lines of
dispatch-tracking/arrival-check structure it gated). The EM-side overrun
nudge, its dispatch-tracking loop in `main()`, `_check_subagent_arrival`,
and the four `RUNTIME_TRIPWIRE_*` env vars that only that machinery read
are gone. Restore is deferred to engine-side work (a durable
subagent-arrival record) that does not exist yet -- see the removal
commit message for the full restore recipe salvaged from the excised
`_SUBAGENT_OVERRUN_TRIPWIRE_ENABLED` constant's own comment. This file now
emits only the push-failure, hooks.json-staleness, zero-tool-use, and
session-baton-mint advisories.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import threading
from pathlib import Path

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
try:
    # Fail-open: a deploy missing its sibling _git_common_dir.py must still fail
    # open (empty common dir -> callers skip) rather than crash on import.
    from _git_common_dir import resolve_git_common_dir as _resolve_git_common_dir  # noqa: E402
except Exception:
    def _resolve_git_common_dir(git_root: str) -> str:
        return ""
try:
    # Fail-open: a deploy missing its sibling _session_hub.py must still fail
    # open to the pre-gate behaviour, not crash on import.
    from _session_hub import ensure_session_dir as _ensure_session_dir  # noqa: E402
except Exception:
    def _ensure_session_dir(session_dir: str, session_id: object) -> bool:
        try:
            os.makedirs(session_dir, exist_ok=True)
        except OSError:
            return False
        return True

# ---------------------------------------------------------------------------
# Charset guard -- mirrors the bash oracle's path-traversal rejection.
# Canonical charset: [A-Za-z0-9_@-]. Any id (SESSION_ID or agentId) deviating
# from this is neutralized to empty / skipped, never used in path construction.
# ---------------------------------------------------------------------------
_ID_CHARSET_RE = re.compile(r"^[A-Za-z0-9_@-]+$")

# ---------------------------------------------------------------------------
# Session-hub creation gate. `_ID_CHARSET_RE` above is a path-traversal guard
# and nothing more -- it admits `hookperf-3ee8b3f4a1d1`, `probe`, `test-sid`
# and every other synthetic id a benchmark or probe hands a hook. This hook's
# two per-session cursors used to create `<git common dir>/
# coordinator-sessions/<id>/` unconditionally, so any invocation driven with a
# made-up session id materialised a hub directory that no registrar ever
# claimed and no reaper will ever collect. 176 such directories accumulated in
# this repo's hub, none carrying `meta.json` -- the creator here is not the
# thing that writes session metadata, which is why they are indistinguishable
# from litter by inspection.
#
# The shape gate, its uuid4 rationale, and the reason an existence gate is the
# wrong instrument all live in `_session_hub`, which the other hub-directory
# creators in this tree share. This hook keeps its own named wrapper because
# both call sites read as cursor writes, not directory creation.
# ---------------------------------------------------------------------------


def _atomic_write_text(path: str, text: str) -> None:
    """Write via a sibling temp file and os.replace so a concurrent reader never sees a torn cursor."""
    tmp = "%s.tmp-%d" % (path, os.getpid())
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _ensure_session_cursor_dir(cursor_dir: str, session_id: str) -> bool:
    """Create this session's hub directory for a per-session cursor write.
    Returns True when `cursor_dir` exists and is safe to write a cursor into,
    False when the caller must skip its cursor write entirely -- the callers'
    baseline writes are fail-open paths, so a refusal is a silent no-op, never
    a broken tool call."""
    return _ensure_session_dir(cursor_dir, session_id)


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


def _resolve_subagent_identity(agent_id: str, session_id: str) -> str:
    """Translate a subagent-side agent_id to the canonical EM-side id. Three
    paths: (a) bare hex -- unnamed agent fast path, return unchanged; (b)
    named teammate -- build "<name>@session-<short8>"; (c) anything else ->
    "" (fail-closed)."""
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


try:
    from _engine_root import (  # noqa: E402
        resolve_claude_klabauter_root as _resolve_claude_klabauter_root,
        arm_lazy_ops as _arm_lazy_ops,
        warn_on_engine_import_divergence as _warn_engine_divergence,
    )
except Exception:
    def _resolve_claude_klabauter_root() -> str | None:
        return None

    def _arm_lazy_ops() -> None:
        return None

    def _warn_engine_divergence(where: str) -> str:
        return "unresolved"
try:
    from _message_envelope import resolve_wiki_citation  # noqa: E402
except Exception:
    def resolve_wiki_citation(text: str) -> str:
        return text

# Armed once at module import, not just at the mint call site below --
# `_arm_lazy_ops()` sets an in-process `sys` attribute read by
# `coordinator_core.ops.__init__` at PACKAGE-INIT time, so whichever of this
# file's engine-importing legs runs first (push-failure verdict, zero-tool-use
# surface, subagent-arrival check, or the session-baton mint) decides the mode
# for the rest of the process -- arming only inside `_mint_session_baton` left
# the other three legs racing it eager. `arm_lazy_ops()` never raises (see its
# own docstring) and costs nothing beyond the attribute set -- no engine
# import, no env var, no leak to child processes. Do not delete this as
# "redundant" with the call inside `_mint_session_baton`: that call stays as
# the leg's own documentation of intent, but THIS is the one that actually
# wins the race on every prompt.
_arm_lazy_ops()


def _fail_open(fn, *args, default=None):
    """Run one detector, yielding `default` on any exception. Every advisory
    leg in `main()` is independently wrapped so a bug in one can never take
    down another. Catches `Exception`, NOT `BaseException` -- a
    KeyboardInterrupt or SystemExit must still terminate the hook rather than
    be swallowed. Do not add logging on the failure path: this runs on every
    session event across every live session, and a detector that fails on
    every fire would write a stderr line every time."""
    try:
        return fn(*args)
    except Exception:
        return default


def _resolve_zero_tool_use_sessions_dir(git_root: str) -> str:
    """Zero-tool-use-specific session-scoped directory, rooted at the git
    common dir. Returns "" on any resolution failure -- callers must treat ""
    as "nothing to do here" rather than falling back to the
    separately-computed `sessions_dir` in `main()`. Both are common-dir-rooted
    but stay two independent resolutions on purpose: conflating them would
    misdirect this one to a location the engine op never touches."""
    try:
        common_dir = _resolve_git_common_dir(git_root)
        if not common_dir:
            return ""
        return os.path.join(common_dir, "coordinator-sessions")
    except Exception:
        return ""


def _git_root() -> str:
    """Nearest ancestor of cwd holding `.git`, else "" (fail-open). No subprocess leg."""
    try:
        start = Path.cwd().resolve()
        for candidate in (start, *start.parents):
            if (candidate / ".git").exists():
                return str(candidate)
    except Exception:
        pass
    return ""


def _resolve_git_dir_no_commondir(git_root: str) -> str:
    """Resolve the git dir that actually holds `git_root`'s own private,
    per-worktree state (HEAD, index) -- without following the `commondir`
    indirection `_resolve_git_common_dir` applies. No subprocess; fail-open to
    "" on any error. In an ordinary clone this is a no-op (the private dir IS
    the common dir); in a linked worktree, `<git_root>/.git` is a FILE
    pointing at the worktree's own private dir under
    `<main>/.git/worktrees/<name>/`, which is where per-worktree state like
    HEAD actually lives."""
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
    """Current branch name via a raw `.git/HEAD` file read -- not a git
    subprocess. This hook fires multiple times per turn, so a spawn here would
    recreate the per-call spawn-tax hazard. Detached HEAD and any read failure
    both degrade to "" -- never a crash, never mistaken for a `work/*` branch.
    HEAD is rooted via the resolved private git dir
    (`_resolve_git_dir_no_commondir`), not a naive `git_root + ".git"` join --
    under a linked worktree that join would open a FILE and fail closed,
    silently disabling the push-failure advisory for the whole session.
    Deliberately does not route through `_resolve_git_common_dir`, since HEAD
    is per-worktree private state, unlike refs/objects -- the commondir
    substitution would report the MAIN checkout's branch instead of this
    worktree's own."""
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


def _configured_day_branch_cheap(git_root: str) -> str:
    """`coordinator.dayBranch` off `.git/config` via a raw file read -- the
    same zero-spawn posture as `_current_branch_cheap`. "" on any read failure
    or absent key."""
    try:
        common_dir = _resolve_git_common_dir(git_root)
        if not common_dir:
            return ""
        with open(
            os.path.join(common_dir, "config"), "r", encoding="utf-8", errors="replace"
        ) as fh:
            text = fh.read()
        m = re.search(
            r"(?im)^\s*\[coordinator\]\s*$.*?^\s*dayBranch\s*=\s*(\S+)\s*$", text, re.DOTALL
        )
        return m.group(1) if m else ""
    except Exception:
        return ""


def _unpushed_commit_count(git_root: str, session_id: str | None = None) -> int | None:
    """Count of local commits not present on the current branch's upstream,
    RESCOPED (DR-190 § 40, 2026-09-02) to this session's own commits only —
    or None when that question cannot be answered — no upstream configured,
    detached HEAD, git error, timeout, unparseable output.

    DR-190 § 40: the prior branch-wide count (`git rev-list --count
    @{upstream}..HEAD`) is correct as measured but wrong as addressed — on a
    shared `work/*` branch with ~35 concurrent sessions the count is rarely
    zero, so the second-person escalation this feeds ("your crash insurance
    may not be insuring") reached sessions whose own work was fully insured
    (six escalations observed in one session, zero involving uninsured work
    by that session). Discriminate via the `Session-Id:` trailer every
    coordinator-produced commit carries (`agents/git-commit-agent.md` § Check
    the `Session-Id` trailer) rather than the raw ahead-count: a commit with
    no trailer, or a foreign session's trailer, does not belong to THIS
    session's insurance question. `session_id=None` (caller has none to
    offer) falls back to the prior branch-wide count — a session that cannot
    name itself cannot be excluded from its own alarm.

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
    if session_id:
        session_count = _own_session_unpushed_commit_count(git_root, session_id)
        if session_count is not None:
            return session_count
    try:
        import subprocess

        # popup-intentional-last-resort
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


def _own_session_unpushed_commit_count(git_root: str, session_id: str) -> int | None:
    """Count of `@{upstream}..HEAD` commits carrying THIS session's own
    `Session-Id:` trailer -- the rescope `_unpushed_commit_count` applies when
    it has a session id to filter by. Returns None on any failure so the
    caller falls back to the branch-wide count -- fail-toward-firing, never
    fail-silent."""
    try:
        import subprocess

        # popup-intentional-last-resort -- same 3s ceiling as
        # `_unpushed_commit_count`'s own subprocess.
        result = subprocess.run(
            [
                "git",
                "log",
                "@{upstream}..HEAD",
                "--format=%(trailers:key=Session-Id,valueonly)",
            ],
            cwd=git_root,
            capture_output=True,
            text=True,
            timeout=3,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            return None
        lines = (result.stdout or "").splitlines()
        return sum(1 for line in lines if line.strip() == session_id)
    except Exception:
        return None


def _push_failure_verdict(git_root: str) -> tuple[dict | None, str | None]:
    """Classify a growing `.git/push-failures.log` via the engine op
    `git.push_failure_verdict` (registered commit `f17ea2f78`) -- the
    five-state classifier that replaced this file's own two-string
    `_unpushed_commit_count` derivation (see `_check_push_failures`'s
    Scope-limit paragraph). See `state/memo-outbox/sent/
    autopush-advisory-yes-build-the-verdict-op.md` for the origin ask and
    this repo's cross-repo memo inbox for the op-landed reply.

    Dispatch shape mirrors `_check_zero_tool_use_surface`'s own in-process
    pattern (resolve root,
    `sys.path` insert, import the op module so it registers,
    `dispatch_from_hook(...)` -- DR-118's named hook-dispatch seam, above the
    `dispatch_message` telemetry wrapper) -- NOT the `python3 -m
    coordinator_core.invoke` CLI form the origin memo documents, which is the
    human-facing shape, not the right call site for a 5s-timeout hook. Do not
    "restore" the CLI form here without first confirming the op is
    registered AND exercising this script end-to-end on a real
    Stop/UserPromptSubmit/PostToolUse payload.

    Returns `(result, degrade_reason)`. On a well-formed response the first
    element is the raw `{"verdict": ..., "evidence": {...}, "remedy_hint":
    ...}` dict and the second is None. On ANY failure the first element is
    None -- engine root unresolvable, import error, dispatch exception,
    non-dict response, an unrecognized verdict string, or a missing/malformed
    evidence object -- and the second names WHICH condition:

      `"contract"`     -- the op rejected our envelope (JSON-RPC -32602,
                          invalid params: a missing or malformed routing key).
                          This is a bug in THIS call site, not a sick engine,
                          and it never fixes itself.
      `"unreachable"`  -- engine root unresolvable, unimportable, or the
                          dispatch raised anything else. Environmental.
      `"malformed"`    -- the op answered, but not in the shape the contract
                          promises.

    The caller (`_check_push_failures`) treats a None result as "fall back to
    the pre-op two-string rendering", never as "say nothing" -- fail-open on
    the op, fail-toward-firing on the answer. `degrade_reason` does not change
    THAT: it only decides whether the fallback text also says the classifier
    was called wrongly. Distinguishing the two is the whole point --
    `origin_worktree` was dropped from this very call for a year and the
    silent fallback is what hid it, so a routing-contract violation is
    reported on its first firing rather than looking like a quiet outage.
    """
    try:
        root = _resolve_claude_klabauter_root()
        if not root:
            return None, "unreachable"
        from _engine_root import place_engine_root_on_path as _place_engine_root_on_path
        _place_engine_root_on_path(root)
        from coordinator_core.ops import push_failure_verdict as _op  # noqa: F401
        from coordinator_core.ipc import HookDispatchError, dispatch_from_hook
    except Exception:
        return None, "unreachable"

    try:
        result = dispatch_from_hook(
            "git.push_failure_verdict", {}, origin_worktree=git_root
        )
    except HookDispatchError as exc:
        return None, ("contract" if getattr(exc, "code", None) == -32602 else "unreachable")
    except Exception:
        return None, "unreachable"

    if not isinstance(result, dict):
        return None, "malformed"
    verdict = result.get("verdict")
    evidence = result.get("evidence")
    if verdict not in (
        "peer_staged",
        "half_applied_merge",
        "simple_lag",
        "resolved_since",
        "indeterminate",
    ):
        return None, "malformed"
    if not isinstance(evidence, dict):
        return None, "malformed"
    return result, None


# Trailing reference line every AUTO-PUSH-MID-SESSION-DETECT advisory carries,
# regardless of which of the five op verdicts (or the pre-op fallback path)
# produced it.
_PUSH_FAILURE_REFERENCE_LINE = (
    resolve_wiki_citation("Reference: docs/wiki/coordinator-tripwires/tripwire-registry/auto-push-mid-session-detector-auto-push-mid-session-detect.md")
)


def _render_push_failure_verdict(
    verdict_result: dict, n_new: int, branch: str, last_line: str
) -> str | None:
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
        if behind:
            return (
                "AUTO-PUSH MID-SESSION FAILURE — " + header +
                f"clean index, {ahead} ahead / {behind} behind upstream — the "
                "branch has DIVERGED. Whether any of the unpushed commits are "
                "YOURS is not something this check knows: on a shared day-branch "
                "they are often entirely a peer's, in which case your own work is "
                "already pushed. Confirm before acting — `git merge-base "
                "--is-ancestor <your-sha> @{u}` per commit you care about. Do NOT "
                "retry a bare `git push`; it is what just failed, and it will keep "
                "failing while the branch is behind. A merge/rebase here rewrites "
                "or overwrites commits that may be a live peer's.\n" + ref
            )
        return (
            "AUTO-PUSH MID-SESSION FAILURE — " + header +
            f"clean index, {ahead} ahead / 0 behind upstream — the branch is "
            "strictly ahead, so `git push` should fast-forward cleanly. Whether "
            "the unpushed commits are yours or a peer's, pushing insures them "
            "all.\n" + ref
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

    return None


# ---------------------------------------------------------------------------
# PLUGIN-HOOKS-JSON-RESTART-GATED (added 2026-08-07) -- detects when THIS
# session's own hook registrations are stale relative to
# `coordinator/hooks/hooks.json` on disk. Established by a three-probe
# control sweep (`state/audits/2026-08-07-bx17-piece3-observed-block-
# discharge.md` § Finding 1): the plugin's own `hooks.json` is snapshotted
# at session boot -- a matcher edit landing after boot is NOT live in that
# session, while the same matcher loaded from `.claude/settings.local.json`
# takes effect on the next tool call. Nothing detected this before now: a
# session that edits `hooks.json`, probes its own guard, and sees no block
# reads that as "the guard is broken" when the only thing wrong is that its
# own snapshot predates the edit -- a false-bug-filing engine already
# measured to have burned real time on the BX-17 campaign.
#
# Idiom deliberately mirrors `_check_push_failures` above rather than
# inventing a second one: a per-session cursor file at
# `<git COMMON dir>/coordinator-sessions/<session_id>/hooks-json-boot-hash.txt`
# (rooted via `_resolve_git_common_dir`, worktree-safe -- see that helper's
# docstring). First check this session records the current on-disk content
# hash as baseline and never alarms (this session's OWN boot snapshot is,
# by definition, not stale relative to itself). A later check compares the
# current hash against that baseline; a mismatch means `hooks.json` changed
# since this session's registrations were captured, so this session's own
# guard observations are invalid until restart. The cursor advances on
# alarm (mirrors `_check_push_failures`' cursor-advance-on-report contract)
# so the SAME edit is never re-reported -- only further-new changes fire
# again.
#
# Cost: content hash (sha256), not mtime -- mtime is unreliable across the
# ~11 peer sessions sharing this tree (a peer's unrelated checkout/rebase
# can bump mtime without changing content, and vice versa across
# filesystems). No subprocess: a single `open().read()` + hashlib digest
# against a small (few-KB) JSON file, run at this hook's existing
# Stop/UserPromptSubmit/PostToolUse cadence -- no new hook registration, no
# per-call spawn added.
#
# Fail-open, never a crash: an unresolvable common dir, unreadable
# hooks.json, or an unwritable cursor file on the baseline-establishing
# write all degrade to None (silent no-op). The alarm-path cursor-advance
# write is separate: if IT fails, the already-built alert text is still
# returned (never dropped), which is the safer failure -- but it means an
# unwritable cursor there causes the same alarm to re-fire on the next
# call instead of degrading to None, not a false alarm but a repeating one.
# ---------------------------------------------------------------------------

_HOOKS_JSON_STALE_REFERENCE_LINE = (
    resolve_wiki_citation("Reference: docs/wiki/coordinator-tripwires/related.md")
)


def _hooks_json_path(git_root: str) -> str:
    """Path to the plugin's own hooks.json, relative to the repo root."""
    return os.path.join(git_root, "coordinator", "hooks", "hooks.json")


def _hash_file_sha256(path: str) -> str | None:
    """sha256 hex digest of `path`'s contents, or None on any read failure --
    fail-open, never raises."""
    try:
        import hashlib

        h = hashlib.sha256()
        with open(path, "rb") as fh:
            h.update(fh.read())
        return h.hexdigest()
    except Exception:
        return None


def _check_hooks_json_staleness(git_root: str, session_id: str, common_dir: str) -> str | None:
    """PLUGIN-HOOKS-JSON-RESTART-GATED detector -- see the module-level
    comment block above this function for the full design rationale.

    Returns advisory text naming the restart-gated trap when
    `coordinator/hooks/hooks.json`'s content hash has changed since this
    session's own first check (its boot-time baseline); None on the
    first-check-records-baseline path, on an unchanged hash, and on the
    fail-open paths that precede any hash comparison (unresolvable common
    dir, invalid session_id, unreadable hooks.json, or an unwritable cursor
    file on the baseline-establishing write). On the alarm path, an
    unwritable cursor does NOT degrade to None -- the alert text is still
    returned (the safer failure), it just means the same alarm re-fires on
    the next call instead of being absorbed.
    """
    if not common_dir:
        return None

    if not session_id or not _ID_CHARSET_RE.match(session_id):
        return None

    current_hash = _hash_file_sha256(_hooks_json_path(git_root))
    if current_hash is None:
        return None

    cursor_dir = os.path.join(common_dir, "coordinator-sessions", session_id)
    cursor_path = os.path.join(cursor_dir, "hooks-json-boot-hash.txt")

    baseline = None
    if os.path.isfile(cursor_path):
        try:
            with open(cursor_path, "r", encoding="utf-8") as fh:
                text = fh.read().strip()
            baseline = text or None
        except Exception:
            baseline = None

    if baseline is None:
        if not _ensure_session_cursor_dir(cursor_dir, session_id):
            return None
        try:
            _atomic_write_text(cursor_path, current_hash)
        except Exception:
            pass
        return None

    if current_hash == baseline:
        return None

    try:
        _atomic_write_text(cursor_path, current_hash)
    except Exception:
        pass

    return (
        "PLUGIN-HOOKS-JSON-RESTART-GATED — coordinator/hooks/hooks.json changed on disk "
        "since this session booted. This session's own hook registrations are a SNAPSHOT "
        "taken at boot: a matcher edit landing after boot is NOT live in this session "
        "(the same matcher loaded from .claude/settings.local.json IS live, no restart "
        "needed — this trap is specific to the plugin's own hooks.json). Any guard "
        "observation this session makes about a changed matcher — e.g. \"I edited the "
        "guard and it still doesn't block\" — is INVALID until a fresh session starts: "
        "restart before trusting it, or a working guard reads as inert and gets "
        "\"fixed\" twice.\n" + _HOOKS_JSON_STALE_REFERENCE_LINE
    )


def _branch_has_no_upstream_and_no_commits(git_root: str, branch: str) -> bool:
    """True when `branch` has no tracking upstream and no commit beyond the
    commit it was cut from -- a push failure there has nothing to lose.

    Reads `.git` files only (no subprocess): no `branch.<name>.remote` in
    config, and the branch ref equals the ref of the branch it was cut from
    (recorded by the first reflog line, `branch: Created from <ref>`), or the
    reflog holds a single entry. Any uncertainty returns False.
    """
    try:
        common = _resolve_git_common_dir(git_root)
        if not common:
            return False
        cfg = os.path.join(common, "config")
        with open(cfg, "r", encoding="utf-8", errors="replace") as fh:
            if f'[branch "{branch}"]' in fh.read():
                return False
        log = os.path.join(common, "logs", "refs", "heads", *branch.split("/"))
        with open(log, "r", encoding="utf-8", errors="replace") as fh:
            entries = [ln for ln in fh.read().splitlines() if ln.strip()]
        return len(entries) == 1 and "branch: Created from" in entries[0]
    except Exception:
        return False


def _check_push_failures(git_root: str, session_id: str):
    """AUTO-PUSH-MID-SESSION-DETECT -- mid-session surfacing of a *newly
    growing* `.git/push-failures.log`, closing the gap left by the ceremony-
    only `## Auto-push health` section of `state/orientation_cache.md`
    (`coordinator/pipelines/workday-start-internals.md` Step 5.5 schema
    table), which regenerates only at `/workday-start`, `/update-docs` Phase
    10, `/workstream-complete`'s `d-append-orientation-pinboard` directive, and `/handoff` Step 2.9 -- structurally
    blind to a mid-session failure burst.

    Returns `(text, advance_fn)`, mirroring `_check_zero_tool_use_surface`'s
    contract: `advance_fn` must be invoked ONLY after a successful stdout
    write of `text` -- never at this function's own read point, never
    speculatively (see `_emit_advisory`'s `on_success` parameter). The cursor
    is advanced immediately, inline, on every path that returns `(None, None)`
    -- there is no alarm text to lose there. It is deferred to `advance_fn`
    only on the path that returns real alarm text, closing the same
    data-loss hazard `_check_zero_tool_use_surface` closes: a process killed
    between this call and the eventual `_emit_advisory` write (a real risk on
    this file's own `_push_failure_verdict` leg -- ~445ms process/~4.3s wall
    against the hot-path timeout) would otherwise have already burned the
    cursor, permanently losing the announcement.

    Origin incident (2026-07-20, this repo): the orientation cache regenerated
    at 10:30Z; auto-push then failed ~20 consecutive times between 10:50Z and
    11:10Z (non-fast-forward, branch diverged from a peer machine). Nothing
    surfaced it in-session -- the EM found it only by manually `cat`-ing the
    log while investigating something unrelated. Registered:
    `docs/wiki/coordinator-tripwires/tripwire-registry/auto-push-mid-session-detector-auto-push-mid-session-detect.md`.

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
    close this residual gap without a subprocess. This is no longer
    hypothetical: the engine repo's cadence-decline admission predicate
    (`docs/plans/2026-08-31-the-cadence-declines-the-push-it-cannot-finish.md`)
    declines a push before any process spawns for a repo whose recent cost
    exceeds its budget, and a decline deliberately writes no `PUSH FAILED`
    row -- so "log never grows" becomes the STEADY-STATE outcome for the
    median repo, not a rare edge case. Fleet-wide guarantee: NO -- this check
    only sees `.git/push-failures.log` under THIS session's own `git_root`
    (via `_resolve_git_common_dir`), so it covers exactly the repos this hook
    is registered in and says nothing about a sibling repo's push health. The
    now-steady-state silent-decline class above is covered on the engine repo's own
    side instead (`coordinator_core/orientation/regenerate_cache.py ::
    emit_auto_push_health`'s declined-repo class), per that team's own memo
    -- this function is deliberately NOT being widened to compensate.

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
    # topology. See `docs/wiki/coordinator-tripwires/` §
    # AUTO-PUSH-MID-SESSION-DETECT.
    common_dir = _resolve_git_common_dir(git_root)
    if not common_dir:
        return None, None
    log_path = os.path.join(common_dir, "push-failures.log")
    try:
        log_size = os.path.getsize(log_path)
    except OSError:
        return None, None

    if not session_id or not _ID_CHARSET_RE.match(session_id):
        return None, None

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
        if not _ensure_session_cursor_dir(cursor_dir, session_id):
            return None, None
        try:
            _atomic_write_text(cursor_path, str(log_size))
        except Exception:
            pass
        return None, None

    if log_size <= baseline:
        return None, None

    new_lines: list = []
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
            fh.seek(baseline)
            new_lines = [ln for ln in fh.read().splitlines() if ln.strip()]
    except Exception:
        pass

    def _advance_cursor() -> None:
        try:
            _atomic_write_text(cursor_path, str(log_size))
        except Exception:
            pass

    branch = _current_branch_cheap(git_root)
    designated = _configured_day_branch_cheap(git_root)
    if not (branch.startswith("work/") or (designated and branch == designated)):
        _advance_cursor()
        return None, None

    if _branch_has_no_upstream_and_no_commits(git_root, branch):
        _advance_cursor()
        return None, None

    try:
        cache_path = os.path.join(git_root, "state", "orientation_cache.md")
        if os.path.isfile(cache_path):
            log_mtime = os.path.getmtime(log_path)
            cache_mtime = os.path.getmtime(cache_path)
            if cache_mtime >= log_mtime:
                _advance_cursor()
                return None, None
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
        _advance_cursor()
        return None, None

    n_new = len(failed_lines)
    last_line = failed_lines[-1]

    verdict_result, degrade_reason = _push_failure_verdict(git_root)
    if verdict_result is not None:
        rendered = _render_push_failure_verdict(verdict_result, n_new, branch, last_line)
        if rendered is not None:
            return rendered, _advance_cursor

    # Fallback path: engine round-trip unresolvable/unimportable/malformed,
    # or (defensively) an unrecognized verdict slipped past
    # `_push_failure_verdict`'s own validation -- reproduce the pre-op
    # two-string behaviour rather than going silent. The alarm text below
    # asserts a CURRENT condition; log growth alone only evidences a
    # HISTORICAL one. Ask the question the text claims to answer before
    # making it in the present tense. None (unresolvable upstream, offline
    # repo, git error) falls through to the full alarm on purpose.
    #
    # A `"contract"` degrade is not an outage and must not read as one: the op
    # answered that OUR envelope was wrong (-32602). That is a defect in this
    # file, invisible for as long as the fallback looks identical to a sick
    # engine -- which is exactly how a dropped `origin_worktree` kwarg survived
    # here undetected. Name it in the text so the next dropped field is caught
    # on its first firing, not by a peer repo reading our source.
    contract_note = (
        "\n(The five-state classifier did not run: `git.push_failure_verdict` "
        "rejected this hook's envelope as invalid params (JSON-RPC -32602). "
        "That is a routing-contract bug in `_push_failure_verdict`, not an "
        "unreachable engine — the text above is the cruder pre-classifier "
        "fallback and will keep firing until the call site is fixed.)\n"
        if degrade_reason == "contract"
        else ""
    )

    if _unpushed_commit_count(git_root, session_id) == 0:
        text = (
            "AUTO-PUSH mid-session note — {n} push failure(s) landed in "
            ".git/push-failures.log on `{branch}` since this session started, but "
            "the branch is currently in sync with its upstream (0 unpushed "
            "commits) — crash insurance is not at risk right now. Most recent "
            "failure:\n"
            "  {last}\n"
        ).format(
            n=n_new, branch=branch, last=last_line
        ) + contract_note + resolve_wiki_citation(
            "Reference: docs/wiki/coordinator-tripwires/tripwire-registry/auto-push-mid-session-detector-auto-push-mid-session-detect.md"
        )
        return text, _advance_cursor

    text = (
        "AUTO-PUSH MID-SESSION FAILURE — {n} new push failure(s) landed in "
        ".git/push-failures.log on `{branch}` since this session started, not "
        "yet reflected in state/orientation_cache.md's Auto-push health "
        "section:\n"
        "  {last}\n"
        "Crash insurance may be silently NOT insuring right now — consider "
        "`git push`, or read the full log for the failure class.\n"
    ).format(
        n=n_new, branch=branch, last=last_line
    ) + contract_note + resolve_wiki_citation(
        "Reference: docs/wiki/coordinator-tripwires/tripwire-registry/auto-push-mid-session-detector-auto-push-mid-session-detect.md"
    )
    return text, _advance_cursor


# ---------------------------------------------------------------------------
# ZERO-TOOL-USE-DETECT-SURFACE (Stage 2, added 2026-07-25; folded onto this
# same UserPromptSubmit-gated seam per DEC-6 -- see module docstring). Reads
# Stage 1's ("subagent-zero-tool-use-detect.py", SubagentStop) durable
# records via a thin engine op and surfaces this session's unsurfaced ones
# on the EM's next turn. See docs/wiki/coordinator-tripwires/
# § ZERO-TOOL-USE-DETECT for the two-stage design.
# ---------------------------------------------------------------------------


def _zero_tool_use_paths(zt_sessions_dir: str, session_id: str) -> tuple[str, str]:
    session_dir = os.path.join(zt_sessions_dir, session_id)
    store_path = os.path.join(session_dir, "subagent-zero-tool-use.jsonl")
    cursor_path = os.path.join(session_dir, "subagent-zero-tool-use-surfaced-cursor.txt")
    return store_path, cursor_path


def _read_zero_tool_use_cursor(cursor_path: str) -> dict:
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

    `surfaced` is clamped to be
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
        _atomic_write_text(cursor_path, json.dumps({"surfaced": surfaced, "size": size}))
    except Exception:
        pass


def _zero_tool_use_local_evidence(store_path: str, cursor: dict) -> int | None:
    try:
        store_size = os.path.getsize(store_path)
    except OSError:
        return None

    if store_size <= cursor.get("size", 0):
        return None

    return store_size


def _extract_zero_tool_use_records(result) -> list:
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        records = result.get("records")
        if isinstance(records, list):
            return records
    return []


def _is_zero_tool_use_detection(rec) -> bool:
    if not isinstance(rec, dict):
        return False
    count = rec.get("tool_use_count")
    if isinstance(count, bool) or not isinstance(count, int):
        return False
    return count == 0


def _format_zero_tool_use_records(records: list) -> str:
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
        + resolve_wiki_citation("Reference: docs/wiki/coordinator-tripwires/tripwire-registry/zero-tool-use-subagent-detector-zero-tool-use-detect.md")
    )


def _check_zero_tool_use_surface(
    git_root: str, session_id: str, zt_sessions_dir: str, hook_event: str
):
    if hook_event != "UserPromptSubmit":
        return None, None

    if not session_id or not _ID_CHARSET_RE.match(session_id):
        return None, None

    if not zt_sessions_dir:
        return None, None

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
        return None, None

    try:
        root = _resolve_claude_klabauter_root()
        if not root:
            return None, None
        from _engine_root import place_engine_root_on_path as _place_engine_root_on_path
        _place_engine_root_on_path(root)
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
        if git_root:
            msg["_origin_worktree"] = git_root

        response = asyncio.run(dispatch_message(msg))
    except Exception:
        return None, None

    result = response.get("result") if isinstance(response, dict) else None
    all_records = _extract_zero_tool_use_records(result)
    total_seen = len(all_records)

    surfaced_so_far = cursor.get("surfaced", 0)
    if not isinstance(surfaced_so_far, int) or surfaced_so_far < 0:
        surfaced_so_far = 0
    new_records = all_records[surfaced_so_far:]

    detections = [rec for rec in new_records if _is_zero_tool_use_detection(rec)]

    if not detections:
        _write_zero_tool_use_cursor(cursor_path, total_seen, store_size)
        return None, None

    try:
        text = _format_zero_tool_use_records(detections)
    except Exception:
        return None, None
    if not text:
        _write_zero_tool_use_cursor(cursor_path, total_seen, store_size)
        return None, None

    def _advance() -> None:
        _write_zero_tool_use_cursor(cursor_path, total_seen, store_size)

    return text, _advance


# ---------------------------------------------------------------------------
# SESSION-BATON-MINT (added 2026-08-19, folded onto this existing
# UserPromptSubmit-gated seam per the same no-second-registration constraint
# ZERO-TOOL-USE-DETECT-SURFACE above already follows -- AC5,
# `_hook_spawn_budget.py` pins `UserPromptSubmit: 1`.
#
# Spec backlink: docs/plans/2026-08-19-promoted-baton-born-status-and-mint-hook.md § C4
# Spike verdict: docs/research/spike-verdicts/2026-08-19-session-baton-mint-from-userpromptsubmit.md
#
# Captures a session's FIRST prompt into the engine's lazy session-baton
# record via the `session_baton.mint` op, so a later `session_baton.promote`
# ceremony has a record to promote. mint only needs the session's FIRST
# prompt, so every prompt after it has nothing to do -- but UserPromptSubmit
# has no matcher support, so this leg short-circuits itself rather than
# being registered narrowly. Gate: one small JSON read of the session's own
# `baton.json` (rooted at the git COMMON dir, the same `sessions_dir` main()
# already resolves for the dispatch-tracking loop below), checked against the
# FIELD the leg cares about, never mere file existence -- an existence-only
# gate here would return immediately off a `baton.json` a pickup session's
# adoption writer already created, and silently never capture a prompt for
# the rest of that session (history and the specific finding: spike verdict
# above, "Finding 0"). Absent record, or present with `first_prompt is None`
# and no `adopted_artifacts` -> pays the mint cost. Present with
# `adopted_artifacts` set -> return immediately, no matter what
# `first_prompt` says: a pickup session's identity is already named by the
# handoff it adopted, and capturing the pickup invocation itself would
# overwrite that with junk (PM ruling, same review -- see spike verdict).
# Present with `first_prompt` already captured and no `adopted_artifacts` ->
# return immediately: no op call, no `coordinator_core` import, no
# read-modify-write (AC7, AC10 -- see spike verdict for AC7's superseded
# "one stat" wording; the field it protects is unchanged). The op's own
# idempotence
# (`session_baton_mint.py`'s `existing.get("first_prompt") is None` guard)
# stays the correctness backstop for the race where two prompts land together
# or the read lies (AC9) -- this gate is an optimization layered on top of
# it, never a substitute for it. Cost ceiling cited from
# `docs/wiki/hook-best-practices.md:279,287` rather than re-derived.
#
# Entry path is pinned by the spike verdict above, not a design choice
# reopened here: `_engine_root.arm_lazy_ops()` sets the in-process
# `sys._coordinator_core_lazy_ops` attribute -- NEVER the
# `COORDINATOR_CORE_LAZY_OPS` env var, which leaks to every child spawned
# without an explicit `env=` -- BEFORE importing
# `coordinator_core.ops.session_baton_mint`, then its `_handler` is called
# DIRECTLY, with `first_prompt` preservation intact, never routed through
# `coordinator_core.ipc.dispatch_message` -- its registry-miss fallback
# force-imports the whole op surface, reproducing the cold-import cost this
# entry path exists to avoid (measured numbers: spike verdict above). Do not
# "simplify" to that shape. Lazy mode leaves `ipc._REGISTRY` unpopulated;
# harmless here since only this one op module is ever imported in this leg.
#
# Calling `store.merge_baton(...)` directly is FORBIDDEN even though it
# measures ~3 ms cheaper: it silently overwrites `first_prompt` on every
# call (`_UNSET` sentinel semantics -- an explicitly-passed value always
# wins), which is exactly the guarantee `_handler`'s own
# `existing.get("first_prompt") is None` check exists to protect. See the
# spike verdict's "the trap in the cheap path."
#
# Fails open on every path -- this hook's UserPromptSubmit registration
# BLOCKS the user; a raise here rejects the prompt outright. Contributes at
# most one line to the additionalContext envelope, and only where the baton
# demonstrably exists on disk (a confirmed mint, or an observed adoption) --
# never on a short-circuit that did neither. Every step is wrapped so a bug
# here can never take down the pre-existing advisories in main().
# ---------------------------------------------------------------------------

_PROMPT_CAPTURE_CAP = 8192
_PROMPT_TRUNCATION_MARKER = "...[truncated]"

_BATON_ADOPTED_ANNOUNCED_SUFFIX = ".adopted-announced"

# Mint is the opposite event from adoption: `minted_artifacts` (dedup-extended
# by the engine, same semantics as `adopted_artifacts`) names handoffs the
# ENGINE created for this session unasked, never something the operator
# chose. It can grow more than once in a session, so a bare once-per-session
# flag (as `_BATON_ADOPTED_ANNOUNCED_SUFFIX` uses) would silently swallow a
# second mint -- this marker instead holds the newline-delimited set of
# artifact paths already announced, so each call can announce only the
# paths not yet in that set.
_BATON_MINTED_ANNOUNCED_SUFFIX = ".minted-announced"


def _baton_advisory_text(baton_path: str, git_root: str) -> str:
    try:
        display_path = os.path.relpath(baton_path, git_root)
    except Exception:
        display_path = baton_path
    display_path = display_path.replace(os.sep, "/")
    prefix = ".git/coordinator-sessions/"
    if display_path.startswith(prefix):
        display_path = "…/" + display_path[len(prefix):]
    return f"WORK JOURNAL — {display_path} — your durable work journal, script-managed"


def _turn_log_clause(turn_log_name: str) -> str:
    return f"; PM prompts saved beside it in {turn_log_name} land in your next sizing"


_HARNESS_WRAPPER_PREFIXES = ("<task-notification>", "<cross-session-message")
_SYSTEM_REMINDER_ONLY_RE = re.compile(
    r"(?:\s*<system-reminder>.*?</system-reminder>)+\s*", re.DOTALL
)


def _is_harness_injected_prompt(prompt: str) -> bool:
    """True when the whole prompt is a harness wrapper rather than human words.
    A human prompt that merely quotes a wrapper mid-text is not matched."""
    body = prompt.strip()
    if body.startswith(_HARNESS_WRAPPER_PREFIXES):
        return True
    return _SYSTEM_REMINDER_ONLY_RE.fullmatch(body) is not None


def _append_pm_turn(
    git_root: str, session_id: str, sessions_dir: str, hook_event: str, prompt,
    baton_msg,
):
    """Appends a human PM prompt to the engine's per-session turn log (after
    the mint, so turn 0 is the first prompt) and returns `baton_msg`, with the
    work-journal line extended to name the log only when the append succeeded.
    Silent no-op on import failure, `ok: false`, or any error."""
    if hook_event != "UserPromptSubmit" or not sessions_dir:
        return baton_msg
    if not session_id or not _ID_CHARSET_RE.match(session_id):
        return baton_msg
    if not isinstance(prompt, str) or not prompt.strip():
        return baton_msg
    if _is_harness_injected_prompt(prompt):
        return baton_msg
    try:
        root = _resolve_claude_klabauter_root()
        if not root:
            return baton_msg
        from _engine_root import place_engine_root_on_path as _place_engine_root_on_path
        _place_engine_root_on_path(root)
        _arm_lazy_ops()
        from coordinator_core.ops.baton_pm_turns import append_turn

        result = append_turn(prompt, session_id=session_id, cwd=git_root)
        if not (isinstance(result, dict) and result.get("ok") is True):
            return baton_msg
        log_path = result.get("log_path")
        if (
            not isinstance(log_path, str)
            or not baton_msg
            or not baton_msg.startswith("WORK JOURNAL — ")
        ):
            return baton_msg
        first, sep, rest = baton_msg.partition("\n")
        return first + _turn_log_clause(os.path.basename(log_path)) + sep + rest
    except Exception:
        return baton_msg


def _minted_advisory_text(artifact_path: str, git_root: str) -> str:
    try:
        display_path = os.path.relpath(artifact_path, git_root)
    except Exception:
        display_path = artifact_path
    display_path = display_path.replace(os.sep, "/")
    return (
        f"HANDOFF MINTED — {display_path} — created for this session by "
        "the engine, not picked up."
    )


def _handoff_mint_advisory(minted_artifacts, baton_path: str, git_root: str):
    """Returns `(text, commit_fn)` for every path in `minted_artifacts` not
    yet announced, or `(None, None)` if there is nothing new. `commit_fn`
    records the announcement and must run only after a successful emit; a
    symlink at the marker refuses the announcement before emit. Reads a
    sibling marker file
    (`_BATON_MINTED_ANNOUNCED_SUFFIX`) holding the newline-delimited set of
    paths already announced -- unlike the adopted marker, this one carries
    content because a mint can recur mid-session and each path needs its own
    once-only signal, not a session-wide one.

    Never touches the marker at all when `minted_artifacts` is falsy --
    the caller's truthiness gate is what keeps a settled session (no mints)
    at the pre-existing zero-extra-IO cost profile. An unreadable/corrupt
    marker fails open to "announce nothing" rather than "announce
    everything" -- treating it as empty would re-announce every already-seen
    path as a storm on the next call.
    """
    if not isinstance(minted_artifacts, list) or not minted_artifacts:
        return None, None

    marker_path = baton_path + _BATON_MINTED_ANNOUNCED_SUFFIX
    try:
        with open(marker_path, "r", encoding="utf-8") as fh:
            announced = {line.strip() for line in fh if line.strip()}
    except FileNotFoundError:
        announced = set()
    except Exception:
        return None, None

    new_paths = []
    seen = set()
    for p in minted_artifacts:
        if isinstance(p, str) and p not in announced and p not in seen:
            new_paths.append(p)
            seen.add(p)
    if not new_paths:
        return None, None

    try:
        if os.path.islink(marker_path):
            return None, None
    except Exception:
        return None, None

    def _commit() -> None:
        if not _symlink_safe_marker(marker_path):
            return
        with open(marker_path, "a", encoding="utf-8") as fh:
            for p in new_paths:
                fh.write(p + "\n")

    return "\n".join(_minted_advisory_text(p, git_root) for p in new_paths), _commit


def _combine_baton_advisories(baton_line, mint_block) -> str | None:
    parts = [p for p in (baton_line, mint_block) if p]
    if not parts:
        return None
    return "\n".join(parts)


def _mint_session_baton(
    git_root: str, session_id: str, sessions_dir: str, hook_event: str, prompt
):
    """Returns `(text, advance_fn)` on every path. `advance_fn` runs the
    announced-marker writes (minted, adopted) and must be called only after
    a successful emit."""
    if hook_event != "UserPromptSubmit":
        return None, None

    if not sessions_dir:
        return None, None

    if not session_id or not _ID_CHARSET_RE.match(session_id):
        return None, None

    baton_path = os.path.join(sessions_dir, session_id, "baton.json")

    try:
        with open(baton_path, "r", encoding="utf-8") as fh:
            record = json.load(fh)
    except FileNotFoundError:
        record = None
    except Exception:
        return None, None

    if record is not None and not isinstance(record, dict):
        return None, None

    mint_advisory, mint_commit = (
        _handoff_mint_advisory(record.get("minted_artifacts"), baton_path, git_root)
        if isinstance(record, dict)
        else (None, None)
    )
    commits = [mint_commit] if mint_commit is not None else []

    def _advance() -> None:
        for fn in commits:
            try:
                fn()
            except Exception:
                pass

    if isinstance(record, dict):
        if record.get("adopted_artifacts"):
            # settled: identity already named by the adopted handoff -- no
            # mint, but the baton is real and this session now owns it.
            # Announce once, gated on the sibling marker (see
            # `_BATON_ADOPTED_ANNOUNCED_SUFFIX` above), not on this branch
            # being reached -- every later prompt of the same session hits
            # this same branch and must stay silent.
            announced_marker = baton_path + _BATON_ADOPTED_ANNOUNCED_SUFFIX
            if os.path.isfile(announced_marker):
                return mint_advisory, _advance
            try:
                if os.path.islink(announced_marker):
                    return mint_advisory, _advance
            except Exception:
                return mint_advisory, _advance
            commits.append(lambda: _symlink_safe_marker(announced_marker))
            return (
                _combine_baton_advisories(
                    _baton_advisory_text(baton_path, git_root), mint_advisory
                ),
                _advance,
            )
        if record.get("first_prompt") is not None:
            return mint_advisory, _advance

    try:
        root = _resolve_claude_klabauter_root()
        if not root:
            return mint_advisory, _advance
        from _engine_root import place_engine_root_on_path as _place_engine_root_on_path
        _place_engine_root_on_path(root)

        _arm_lazy_ops()
        from coordinator_core.ops.session_baton_mint import _handler

        _warn_engine_divergence("session-baton-mint")

        params: dict = {"session_id": session_id, "cwd": git_root}
        if isinstance(prompt, str):
            if len(prompt) > _PROMPT_CAPTURE_CAP:
                params["prompt"] = (
                    prompt[:_PROMPT_CAPTURE_CAP] + _PROMPT_TRUNCATION_MARKER
                )
            else:
                params["prompt"] = prompt
        result = _handler(params)

        if isinstance(result, dict):
            engine_baton_path = result.get("baton_path")
            if isinstance(engine_baton_path, str) and os.path.normcase(
                engine_baton_path
            ) != os.path.normcase(baton_path):
                # foreign-identity: SUBJECT — the two disagreeing baton paths ARE
                # the anomaly report.
                print(
                    "session-baton-mint: path divergence -- "
                    f"hook={baton_path!r} engine={engine_baton_path!r}",
                    file=sys.stderr,
                )
            exit_code = result.get("exit_code")
            if exit_code not in (0, None):
                print(
                    f"session-baton-mint: op returned exit_code={exit_code!r} "
                    f"error={result.get('error')!r}",
                    file=sys.stderr,
                )
                return mint_advisory, _advance
            if not os.path.isfile(baton_path):
                return mint_advisory, _advance
            return (
                _combine_baton_advisories(
                    _baton_advisory_text(baton_path, git_root), mint_advisory
                ),
                _advance,
            )
        return mint_advisory, _advance
    except Exception:
        return mint_advisory, _advance


_VALID_HOOK_EVENTS = ("Stop", "UserPromptSubmit", "PostToolUse")


def _hook_event_name(payload) -> str:
    name = payload.get("hook_event_name") if isinstance(payload, dict) else None
    if isinstance(name, str) and name in _VALID_HOOK_EVENTS:
        return name
    return "PostToolUse"


# --- SYMLINK-SAFE MARKER CREATE/TOUCH ---
#
# Bug: state/bug-backlog/2026-08-07-o-creat-o-excl-follows-a-dangling-symlin-13c1e12b3ccc.yaml.
# POSIX `open(O_CREAT | O_EXCL)` already refuses a symlinked leaf outright --
# EEXIST fires whether the link is dangling or resolves, per POSIX open(2).
# Windows does NOT: `os.open(path, O_CREAT | O_EXCL)` on a DANGLING symlink
# follows it and creates the FILE THE LINK POINTS AT, succeeding with no
# exception -- so every predictable-tempdir marker in this module was
# reachable for attacker-chosen-path file creation by a local actor who
# pre-plants a dangling symlink at the marker's known name before the
# session starts. `O_NOFOLLOW` does not exist on Windows, so the fix cannot
# be a flag; it is a post-open identity check that costs nothing on POSIX
# (it can only ever agree there).
def _symlink_safe_marker(path: str) -> bool:
    """Create-or-refresh an empty marker file at `path` without ever
    resolving a symlink planted at that name. Returns True if `path` now
    names a verified-non-symlink regular file the caller may treat as its
    own marker; False if `path` is (or was, at open time) a symlink and must
    not be used or refreshed.

    Windows exposure this closes: `os.open(path, O_CREAT|O_EXCL)` against a
    DANGLING symlink follows it and silently creates its target -- the fd
    then refers to that target, not to `path`. Two layers close it:

    1. A PRE-open `os.path.islink` check -- this is what stops the target
       from ever being created at all for the common case (a symlink
       planted before this call runs), since a post-open check alone
       cannot undo a create that already happened.
    2. A post-open `os.fstat(fd)` vs `os.lstat(path)` identity check, for
       the narrower race a symlink planted in the gap between check 1 and
       the `os.open` call would leave -- lstat inspects the leaf without
       following it, fstat inspects what the open actually produced, and
       the two can only disagree when `path` names a symlink. A mismatch
       means the open followed a link anyway; we close the fd without
       writing to or using it and report False.

    Residual window: only the gap between the two checks above -- a
    symlink planted in THAT window still gets an empty file created at its
    target as an unavoidable side effect of the OS's own O_CREAT semantics
    completing before we can inspect it (no portable, race-free way to
    recover the resolved path after the fact without risking a second
    TOCTOU chasing a moving target). What both layers together guarantee is
    the actual guarantee this bug asked for: our own marker content is
    never written through a link, and the caller's marker state is never
    advanced as though the real path had been claimed -- `path` itself
    stays a dangling symlink forever after a detected hijack, so every
    later call sees the same `False` and the feature this marker gates
    degrades to permanently-not-firing for that session rather than
    writing attacker-influenced content anywhere.

    The already-exists branch (a second call refreshing an existing
    marker's mtime, e.g. a throttle) has a separate, much tighter residual:
    `os.path.islink` and `os.utime` are two syscalls, not one, so a symlink
    swapped in between them is a real but sub-millisecond local race, and at
    worst causes an mtime bump on a file that already existed -- never a
    creation, never content.
    """
    try:
        if os.path.islink(path):
            print(f"symlink-safe-marker: hijack detected at {path!r} (pre-open)", file=sys.stderr)
            return False
    except OSError:
        return False
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            if os.path.islink(path):
                print(f"symlink-safe-marker: hijack detected at {path!r} (exists-branch)", file=sys.stderr)
                return False
        except OSError:
            return False
        try:
            os.utime(path, None)
        except OSError:
            pass
        return True
    else:
        try:
            if not _fd_matches_lstat(fd, path):
                print(f"symlink-safe-marker: hijack detected at {path!r} (post-open race)", file=sys.stderr)
                return False
        finally:
            os.close(fd)
        return True


def _fd_matches_lstat(fd: int, path: str) -> bool:
    """True iff `fd` (just returned by an `O_CREAT`-flagged `os.open(path,
    ...)`) actually refers to `path` itself rather than to whatever a
    symlink planted at `path` resolved to. See `_symlink_safe_marker` for
    why this identity check, rather than a pre-open `O_NOFOLLOW`-style flag,
    is the fix: `os.lstat(path)` inspects the leaf without following it,
    `os.fstat(fd)` inspects what the open actually produced, and the two
    can only disagree (different `(st_dev, st_ino)`) when `path` names a
    symlink -- POSIX `O_EXCL` never reaches this function with fd open
    through a symlink at all (EEXIST fires first), so this is a no-op
    confirmation there and the real check only on platforms that follow a
    dangling link. `fd` is left open either way -- caller's responsibility
    to close it.
    """
    try:
        fd_stat = os.fstat(fd)
        link_stat = os.lstat(path)
    except OSError:
        return False
    return (link_stat.st_dev, link_stat.st_ino) == (fd_stat.st_dev, fd_stat.st_ino)


def _emit_advisory(
    parts,
    event="PostToolUse",
    on_success=None,
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
    unaffected."""
    text_parts = [p for p in parts if p]

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
    if wrote and on_success is not None:
        try:
            on_success()
        except Exception:
            pass
    return 0


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

    # Security: reject SESSION_IDs with path-traversal characters before any
    # path construction. Non-empty ids that deviate are neutralized to empty
    # and fall through to the absent-id exit-0 below -- same no-op path.
    if session_id and not _ID_CHARSET_RE.match(session_id):
        session_id = ""

    if not session_id:
        return 0

    agent_id = payload.get("agent_id") or ""
    if not isinstance(agent_id, str):
        agent_id = ""

    git_root = _git_root()
    if not git_root:
        return 0

    common_dir = _resolve_git_common_dir(git_root)
    sessions_dir = os.path.join(common_dir, "coordinator-sessions") if common_dir else ""
    agents_dir = os.path.join(sessions_dir, ".agents") if sessions_dir else ""

    # --- Subagent-detect inverse: primary path (SESSION_ID as an agent dir) ---
    if agents_dir and os.path.isfile(os.path.join(agents_dir, session_id, "em-session-id.txt")):
        return 0

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
    # Resolved here, below the two
    # subagent-detect early returns above, not before them -- this
    # git-common-dir walk is wasted work on every Stop fire from inside a
    # subagent's own session, the common case those early returns exist to
    # short-circuit.
    zero_tool_use_sessions_dir = _fail_open(
        _resolve_zero_tool_use_sessions_dir, git_root, default=""
    )

    # --- AUTO-PUSH-MID-SESSION-DETECT (see _check_push_failures docstring) ---
    # Computed here, once EM-session-ness is confirmed, independently of the
    # runtime-tripwire dispatch-tracking logic below (this repo may have zero
    # dispatched agents this session and still have a mid-session push-failure
    # flood to surface). Wrapped so a bug here can never take down the
    # existing runtime-tripwire advisory -- fail-open per module contract.
    push_failure_msg, _push_failure_advance = _fail_open(
        _check_push_failures, git_root, session_id, default=(None, None)
    )

    # --- PLUGIN-HOOKS-JSON-RESTART-GATED (see _check_hooks_json_staleness
    # docstring + the module-level comment block above that function).
    # Independently wrapped, same as the push-failure block above -- a bug
    # here must never take down any other advisory. Not gated to a single
    # hook_event: this session's registrations can be stale relative to a
    # matcher edit regardless of which of Stop/UserPromptSubmit/PostToolUse
    # fired, and the read is cheap (one file hash, no subprocess). ---
    hooks_json_stale_msg = _fail_open(
        _check_hooks_json_staleness, git_root, session_id, common_dir
    )

    # --- ZERO-TOOL-USE-DETECT-SURFACE (see module docstring + the section
    # immediately above _emit_advisory). Independently wrapped, same as the
    # push-failure block above -- a bug here must never take down either
    # pre-existing advisory. Gated to UserPromptSubmit inside the function
    # itself (checked first, before any stat call), so this costs nothing
    # extra on Stop/PostToolUse:Agent fires. ---
    zero_tool_use_msg, _zero_tool_use_advance = _fail_open(
        _check_zero_tool_use_surface,
        git_root,
        session_id,
        zero_tool_use_sessions_dir,
        hook_event,
        default=(None, None),
    )

    # --- SESSION-BATON-MINT (see module comment block above
    # _mint_session_baton). Independently wrapped, same as the checks above --
    # a bug here must never take down any other advisory, and must never
    # reject the prompt. Steady-state cost is exactly one os.path.isfile stat
    # (AC7); only this session's first UserPromptSubmit pays the mint cost.
    # Contributes at most one line to _emit_advisory, and only on the call
    # where the baton newly demonstrably exists (confirmed mint, or observed
    # adoption) -- see `_mint_session_baton`'s docstring. ---
    # --- REPLY-CAP-ESCAPE-FOLD-IN (C3, see block above _check_reply_cap_
    # escape). Independently wrapped, same as the checks above -- a bug here
    baton_msg, _baton_advance = _fail_open(
        _mint_session_baton,
        git_root,
        session_id,
        sessions_dir,
        hook_event,
        payload.get("prompt"),
        default=(None, None),
    )

    # --- PM-TURN-LOG: every human prompt, after the mint so turn 0 exists. ---
    baton_msg = _fail_open(
        _append_pm_turn,
        git_root,
        session_id,
        sessions_dir,
        hook_event,
        payload.get("prompt"),
        baton_msg,
        default=baton_msg,
    )

    # --- Subagent-overrun tripwire: REMOVED (PM ruling 2026-07-31 stood it
    # down; excised on the finding the gate had been False since -- see the
    # module docstring's SUBAGENT-ARRIVAL-CHECK note for the restore
    # pointer). Only the surviving advisories emit now. ---
    def _on_success() -> None:
        if _push_failure_advance is not None:
            try:
                _push_failure_advance()
            except Exception:
                pass
        if _zero_tool_use_advance is not None:
            try:
                _zero_tool_use_advance()
            except Exception:
                pass
        if _baton_advance is not None:
            try:
                _baton_advance()
            except Exception:
                pass

    return _emit_advisory(
        [baton_msg, push_failure_msg, hooks_json_stale_msg, zero_tool_use_msg],
        hook_event,
        on_success=_on_success,
    )


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
