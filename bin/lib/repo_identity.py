"""coordinator/bin/lib/repo_identity.py -- the ONE checked repo-root
resolver for the `coordinator/bin` script family.

Spec backlink: pln-one-checked-resolver-for-the-c-035d59
§ C1.

Public signature (this is the contract every other chunk in the plan,
C2-C7, is authored against -- do not change without re-authoring them):

    resolve_checked_repo_root(explicit_root: str | None = None) -> tuple[str | None, dict]

Callers MUST branch on the returned dict's `"verdict"` field, never treat
the returned root as trustworthy on its own. Verdict vocabulary:
  - `"MATCH"`      -- the harness anchor is contained within the resolved
                      root. Safe to proceed.
  - `"MISMATCH"`   -- positive evidence the harness anchor is a DIFFERENT
                      real repo. Disposition (refuse vs warn-and-proceed)
                      is entirely the CALL SITE's decision (AC2, AC10) --
                      this module never refuses on its own.
  - `"UNRESOLVED"` -- the check could not run (no sid, no registry record,
                      failed trust check, failed plausibility band, or no
                      git root found at all). Per DR-277
                      (docs/decisions/DR-277-guards-are-advisory-by-default-two-named.md)
                      and this plan's Anti-scope, UNRESOLVED must NEVER be
                      hardened into a refusal anywhere downstream.
  - `"EXPLICIT"`   -- an explicit root was supplied by the caller. Nothing
                      was resolved or gated (AC3): an explicit root is a
                      statement of caller intent that never touched cwd,
                      so it is returned as-is with an informational
                      verdict rather than run through the gate at all.

This module intentionally imports NOTHING beyond the `cc_invoke` engine
bootstrap (see the sys.path shim below, copied verbatim in shape from
`coordinator/bin/wsc-coverage-gate-runner.py`'s own bootstrap) plus the two
engine seams it composes over. It is NOT added to `cli_shared.py`:
verified on disk (before it was deleted in C2), `cli_shared.current_repo_root()`
had exactly one caller (`resolve_from_repo`, same file) and none of the ~30
class-A migration targets imported `cli_shared` at all -- see the plan's C1
body for the full refutation. That fan-in premise is what the argument rests
on, not the function's continued existence: C2 deleted `current_repo_root()`
outright once every call site it fed was repointed onto this module, so the
function no longer exists, but the reason this module was kept separate from
`cli_shared.py` still holds. `cli_shared.py` also declares itself call-site plumbing, not
engine-owned business logic, which a gate composed directly over
`coordinator_core.pickup_assemble` is not obviously.

Composition:
  1. Resolve the root via `coordinator_core.git.repo_root.show_toplevel` --
     memoized and NON-SPAWNING (it walks for a `.git` entry, spawning only
     when the walk finds nothing). Never a fresh
     `subprocess.run(["git", "rev-parse", ...])` -- eliminating those
     spawns across the ~24 near-verbatim copies this plan replaces is half
     its value (see the plan's "second defect this closes, for free").
  2. Gate via `coordinator_core.pickup_assemble.compute_repo_identity_gate(
     repo_root, sid)`. `sid` is read directly from
     `$CLAUDE_CODE_SESSION_ID` -- none of the ~25 CLIs this plan migrates
     has a `sid` the way the predecessor's engine-side callers (via
     `compute_session_shape_gate`) did. When the env var is absent (or
     empty), the verdict degrades to UNRESOLVED (AC1's fail-open bias) --
     this module never passes `sid=None` into the gate and trusts
     whatever it returns; it short-circuits to UNRESOLVED itself so the
     `sessionId == sid` equality leg and the `(resolved_root, sid)` memo
     key are never degenerately keyed on `None`.
  3. Never refuses (AC2): no `raise`, no `sys.exit`, on any verdict.
     Returns BOTH the resolved root and the verdict dict; disposition is
     entirely the call site's decision -- exactly where the predecessor
     plan placed it.

Memoization -- WHAT and WHY, not just WHAT:

Only `MATCH` and `MISMATCH` are memoized, process-lifetime, keyed on
`(resolved_root, sid)`. `UNRESOLVED` is NEVER memoized.

Why a process-lifetime memo is safe here: these are spawn-per-call CLI
processes (DR-215 -- no resident daemon), so "process lifetime" is one
dispatch, and both key components (`resolved_root`, `sid`) are stable
within that one dispatch -- `show_toplevel`'s own module docstring
(`coordinator_core/git/repo_root.py`) makes the identical argument for
its own cwd-keyed memo, and this module's memo follows the same shape for
the same reason.

Why UNRESOLVED is never memoized: `coordinator_core/git/repo_root.py`'s
own module docstring carries an explicit negative-spec -- a failed
resolution is never memoized there, because "not found" is the absence of
an identity at this moment, not the identity itself, and can flip to
present later in the same process (e.g. a registry record write races a
gate read). The identical reasoning applies to UNRESOLVED here: a missing
registry record, a failed trust check, or a plausibility-band miss is not
evidence the repo identity check can never succeed in this process --
caching it would poison every subsequent call at this `(resolved_root,
sid)` key for the rest of the process, exactly the bug `repo_root.py`'s
own negative-spec exists to prevent. `clear_repo_identity_memo()` is
shipped alongside, mirroring `repo_root.py::clear_memo()`, primarily for
this module's own test surface (every test in
`coordinator/bin/tests/test_checked_repo_resolver.py` calls it in
`setUp` -- without it, two tests sharing a `(resolved_root, sid)` pair
against different on-disk registries would be served the first test's
cached verdict, silently passing AC7's wrong-repo assertion while
asserting nothing).

DR-277's fourth structural rule, addressed directly (a reader WILL
pattern-match this memo against it): DR-277
(`docs/decisions/DR-277-guards-are-advisory-by-default-two-named.md`)
states "a one-time approval must never become a standing grant for a
repeated cost. Any gate whose harm scales with invocation count -- CPU,
RAM, network egress, spend, rate limits -- needs a per-invocation check,
and no amount of upstream ratification substitutes for it." That rule
targets harm that SCALES WITH INVOCATION COUNT -- a resource-exhaustion
class of risk. It does not conflict here: this memo's two key components,
`resolved_root` and `sid`, are BOTH INVARIANT within a single process (a
CLI's cwd-derived git root and its harness session id cannot change
mid-dispatch), so there is no repeated COST being amortized away by the
memo -- only a repeated RECOMPUTATION of an answer that cannot change
mid-process being skipped. DR-277's rule is about a cost whose harm grows
with how many times you pay it; this memo is about an answer that cannot
become a different answer no matter how many times you ask, which is a
different shape entirely.

This memo shape is established in-fleet, not novel: the in-fleet memo-shape
wiki page under `docs/wiki/` (its ownership-boundary doc, line 254) names
process-scope memoization as the primary design (not incidental) for
exactly this "resolve once per process"
pattern, and `docs/plans/2026-08-07-n-plus-one-git-spawn-class-and-
amplification-gate.md:692` already ships a `(sha_range, session_id)`-keyed
memo of the same shape.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BIN_DIR = os.path.dirname(_SCRIPT_DIR)

if _BIN_DIR not in sys.path:
    sys.path.insert(0, _BIN_DIR)

from cc_invoke import require_engine_on_path  # noqa: E402

_ENGINE_ROOT = require_engine_on_path(__file__)

from coordinator_core.git.repo_root import show_toplevel as _show_toplevel  # noqa: E402

_VERDICT_MATCH = "MATCH"
_VERDICT_MISMATCH = "MISMATCH"
_VERDICT_UNRESOLVED = "UNRESOLVED"
_VERDICT_EXPLICIT = "EXPLICIT"

#: `(resolved_root, sid)` -> full verdict dict. MATCH/MISMATCH only -- see
#: module docstring's "Memoization" section for why UNRESOLVED is excluded.
_verdict_memo: Dict[Tuple[str, str], Dict[str, Any]] = {}


def clear_repo_identity_memo() -> None:
    """Drop every memoized MATCH/MISMATCH verdict. Mirrors
    `coordinator_core.git.repo_root.clear_memo()`. Not called automatically
    in production -- exists for the rare caller that needs a fresh
    resolution, and is MANDATORY in this module's own test suite (every
    test calls this in `setUp`; see module docstring)."""
    _verdict_memo.clear()


def _unresolved(resolved_root: Optional[str], sid: Optional[str], detail: str) -> Dict[str, Any]:
    return {
        "verdict": _VERDICT_UNRESOLVED,
        "session_root": None,
        "resolved_root": resolved_root,
        "sid": sid,
        "message": f"repo-identity (checked resolver): {detail}",
    }


def resolve_checked_repo_root(
    explicit_root: Optional[str] = None,
) -> Tuple[Optional[str], Dict[str, Any]]:
    """The ONE checked resolver -- see module docstring for the full
    contract. NEVER refuses (AC2): always returns, never raises, never
    calls `sys.exit`. Disposition on any verdict, including MISMATCH, is
    entirely the caller's decision.
    """
    if explicit_root is not None:
        # AC3: an explicit root is caller intent that never touched cwd --
        # resolve nothing, gate nothing into a refusal.
        return explicit_root, {
            "verdict": _VERDICT_EXPLICIT,
            "session_root": None,
            "resolved_root": explicit_root,
            "sid": None,
            "message": f"repo-identity (checked resolver): explicit root supplied ({explicit_root}), not gated",
        }

    resolved_root = _show_toplevel()
    if resolved_root is None:
        # No git root at all -- nothing to gate.
        return None, _unresolved(None, None, "no git root resolved from cwd")

    sid = os.environ.get("CLAUDE_CODE_SESSION_ID") or None
    if not sid:
        # AC1's fail-open bias: do not pass sid=None into the gate and
        # trust its return -- short-circuit to UNRESOLVED here so the
        # `sessionId == sid` equality leg and the `(resolved_root, sid)`
        # memo key are never degenerately keyed on `None`.
        return resolved_root, _unresolved(resolved_root, None, "no $CLAUDE_CODE_SESSION_ID in environment")

    memo_key = (resolved_root, sid)
    cached = _verdict_memo.get(memo_key)
    if cached is not None:
        return resolved_root, cached

    # Imported at call time, not module scope: `coordinator_core.pickup_assemble`
    # costs ~360ms to import and this module is plumbing for ~25 CLIs, most of
    # which never reach the gate (no $CLAUDE_CODE_SESSION_ID, or a memo hit
    # above returns first). Module-scope it was also an import-chain the fake
    # engine trees in facade tests cannot satisfy, failing them on a symbol
    # unrelated to what they assert.
    from coordinator_core.pickup_assemble import compute_repo_identity_gate

    verdict = compute_repo_identity_gate(Path(resolved_root), sid)

    if verdict.get("verdict") in (_VERDICT_MATCH, _VERDICT_MISMATCH):
        _verdict_memo[memo_key] = verdict

    return resolved_root, verdict
