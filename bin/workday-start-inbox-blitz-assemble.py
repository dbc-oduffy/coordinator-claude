#!/usr/bin/env python3
# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
workday-start-inbox-blitz-assemble.py -- /workday-start Step 1.45's
count-and-age escalation: a read-only consumer of claude-klabauter's registered
"memo.blitz_buckets" op that renders EITHER a one-line inventory note (below
both trigger legs) OR a full blitz dispatch plan (above either leg).

Why an escalation of an existing step rather than an /inbox-blitz skill
(PM ruling, 2026-07-28): skill-accumulation aversion. The ceremony that
already looks at the inbox every morning is the right place to notice it has
grown; a separate ceremony is one more surface to forget. Do not re-house this.

Why the BRIEFS are generated here rather than described in the ceremony's
prose: three clauses are non-negotiable and each was earned by a concrete
finding in project-rag's 2026-07-28 run --

  1. The fyi sweep is NOT a rubber stamp. The sender labels `fyi` from THEIR
     vantage and cannot know what is load-bearing for the receiver; finding
     mislabels is the entire point. This is what surfaced a break-class
     contract defect in their run.
  2. Supersession must precede classification in the dominant-correspondent
     bucket, or real effort goes into classifying dead asks.
  3. Verification is mandatory. Three of their memos asserted things about
     their tree that had since shipped. A memo saying "your X is broken" is a
     claim to check, not a fact to record.

Prose in a ceremony file is a rule the operator has to remember to carry into
a dispatch brief. Emitting the brief text discharges the rule instead -- the
ceremony pastes what it is handed, and a clause cannot be dropped by an EM
paraphrasing under context pressure.

Output: JSON on stdout (one object), for the ceremony to render. Always exit 0
-- this is advisory orientation, never a gate.

  {"state": "skipped"}         -- claude-klabauter/op unavailable; ceremony renders nothing extra.
  {"state": "inventory", ...}  -- below both legs; plain Step 1.45 inventory stands.
  {"state": "escalate", "trigger": {...}, "summary": {...},
   "dispatches": [{"bucket", "label", "memos": [...], "brief": "<text>"}],
   "supersession_candidates": [...], "plan_weight_note": "<text>",
   "skipped_candidates": <int>}  -- present only when >0; a malformed
   bucket/supersession candidate (missing id/path/newer/older/basis) was
   dropped rather than rendered with a placeholder.

Test seam (test-only): COORDINATOR_INBOX_BLITZ_JSON, when set and non-empty,
supplies the memo.blitz_buckets envelope directly (a `result` key is
unwrapped, an `error` key renders the skipped state, malformed JSON likewise)
-- the real cc_invoke() call is skipped entirely, and the seam is checked
BEFORE CLAUDE_KLABAUTER_ROOT resolution so a test needs no live checkout.

Spec backlink: DoE state/handoffs/2026-07-28-fold-inbox-blitz-into-workday-start-as-a.md;
  DoE cross-repo/inbox/2026-07-28-project-rag-em-inbox-blitz-proven-pattern.md;
  DoE coordinator/commands/workday-start.md Step 1.45.

Negative-spec:
  - Does NOT write, move, or flip any memo's lifecycle state -- memo.blitz_buckets
    is a pure read, and this veneer only renders. The lifecycle flip stays in
    /pickup's memo branch.
  - Does NOT confirm a supersession. Candidates are surfaced as candidates,
    with their basis, for the EM to confirm. Loose matching drops live asks.
  - Does NOT nag when claude-klabauter is absent or the op is unregistered -- matches
    check-deferral-orphan-memo.py's never-nag/never-error posture (structured
    `{"state": "skipped"}` here instead of fully silent, since this script's
    output is a JSON contract the ceremony parses, not free text).
  - Does NOT cut batons or dispatch anything itself. It emits the dispatch
    plan; the ceremony (and the EM) decide.
  - Does NOT emit one baton per plan-weight memo -- `plan_weight_note` carries
    the one-baton-per-SPACE rule, which is concurrency safety on a shared
    worktree, not tidiness.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)


# --------------------------------------------------------------------------
# Dispatch briefs -- the three non-negotiable clauses live HERE, in the text
# actually handed to a dispatched agent, not in ceremony prose.
# --------------------------------------------------------------------------

_VERIFICATION_CLAUSE = """
VERIFICATION IS MANDATORY, NOT OPTIONAL. Every file, symbol, constant, line
number, and commit SHA a memo names gets checked against the CURRENT working
tree before you record anything about it. Put every mismatch in a dedicated
"Stale claims" section of your report. A memo saying "your X is broken" is a
claim to check, not a fact to record -- these memos are days old and assert
things about a tree that has moved. In the run this ceremony is modelled on,
three of thirty memos asserted things that had already shipped; without this
pass the receiving team would have redone work that was already done.
""".strip()

_FYI_BRIEF = """
You are sweeping the `fyi`-tier memos of a cross-repo inbox.

THIS IS NOT A RUBBER STAMP, and reading it as one defeats the dispatch. The
sender labelled each of these `fyi` from THEIR vantage. They cannot know what
is load-bearing on the RECEIVER's side. Finding the mislabels is the entire
value of this pass -- in the run this ceremony is modelled on, one memo
correctly filed `fyi` by its sender collided with a live contract on the
receiver's side and carried a break-class defect.

Read each memo in full -- title, body, cited locus, proposed action -- then
assign exactly one route:

  CLOSE            -- genuinely informational, nothing owed, nothing at risk.
  CLOSE-WITH-NOTE  -- informational, but something worth capturing in-repo
                      before it closes; say what and where.
  ESCALATE         -- load-bearing for us despite the `fyi` label. Say what it
                      collides with and why it is not merely informational.
  SUPERSEDED       -- a later memo from the same sender already resolves it;
                      name that memo.

{verification}

Report: one block per memo -- path, route, one-line rationale, plus the
"Stale claims" section. Do not edit any memo; do not flip any lifecycle field.
""".strip()

_DOMINANT_BRIEF = """
You are triaging the memos from ONE dominant correspondent in a cross-repo
inbox. These are not N independent items -- one correspondent owning half an
inbox is almost always a handful of running threads over several days, with
later memos confirming, correcting, and retracting earlier ones. Treat them
as threads.

Three ORDERED passes. The order is load-bearing:

  PASS 1 -- SUPERSESSION MAP, FIRST. Which memos are already resolved by a
  later one from the same sender? Doing this after classification means real
  effort spent classifying dead asks. Supersession candidates supplied below
  are CANDIDATES: confirm each actually RESOLVES the earlier memo rather than
  merely touching the same topic. Be strict -- loose matching silently drops
  live asks.

  PASS 2 -- THREAD GROUPING. Group the survivors by problem/solution space. A
  sender-declared `space:` value, where present, is a hint you may override,
  not a taxonomy you must obey.

  PASS 3 -- PER-MEMO CLASSIFICATION of the survivors:
    DISPATCH-TO-FIX       -- a defect to repair. Name the defect.
    DISPATCH-TO-IMPLEMENT -- a surface to build. Name the surface.
    PLAN-WEIGHT           -- too big for a dispatch; needs a plan or a baton.
    REPLY-ONLY            -- answerable with a reply; no code change owed.
    SUPERSEDED            -- from pass 1.
  Fix and implement stay split deliberately: both dispatch, but repairing a
  defect and building a surface want different briefs and different
  verification.

{verification}

Report: the supersession map, then the thread groups, then one block per
surviving memo (path, classification, one-line rationale, space), plus the
"Stale claims" section. Do not edit any memo; do not flip any lifecycle field.
""".strip()

_REST_BRIEF = """
You are triaging the remaining memos of a cross-repo inbox -- mixed senders,
no single thread.

For each memo, read it in full, then assign exactly one classification:
    DISPATCH-TO-FIX       -- a defect to repair. Name the defect.
    DISPATCH-TO-IMPLEMENT -- a surface to build. Name the surface.
    PLAN-WEIGHT           -- too big for a dispatch; needs a plan or a baton.
    REPLY-ONLY            -- answerable with a reply; no code change owed.
    SUPERSEDED            -- a later memo already resolves it; name it.
Fix and implement stay split deliberately -- both dispatch, but repairing a
defect and building a surface want different briefs and different verification.

ALSO assign each memo an explicit problem/solution space label. Where the memo
carries a sender-declared `space:` you may adopt or override it; where it does
not, name one. These labels are what the EM groups PLAN-WEIGHT items by.

{verification}

Report: one block per memo -- path, classification, space, one-line rationale
-- plus the "Stale claims" section. Do not edit any memo; do not flip any
lifecycle field.
""".strip()

_BUCKET_SPEC = {
    "fyi": ("fyi-tier sweep", _FYI_BRIEF),
    "dominant": ("dominant-correspondent cluster", _DOMINANT_BRIEF),
    "rest": ("rest (mixed senders)", _REST_BRIEF),
}

_PLAN_WEIGHT_NOTE = (
    "Group PLAN-WEIGHT items by problem/solution space and cut ONE baton per "
    "SPACE, not per memo. The reason is concurrency safety on a shared "
    "worktree, not tidiness: separate batons in one space mean separate EM "
    "sessions editing the same surfaces. Route into an EXISTING open baton "
    "wherever one already covers the space — that is the route-to-baton "
    "default already standing at Step 1.45."
)


def _fetch_result(repo_root: str) -> dict:
    """Return the bare memo.blitz_buckets result dict, or {} on any failure/skip."""
    seam = os.environ.get("COORDINATOR_INBOX_BLITZ_JSON", "")
    if seam:
        try:
            envelope = json.loads(seam)
        except (json.JSONDecodeError, ValueError):
            return {}
        if not isinstance(envelope, dict) or "error" in envelope:
            return {}
        result = envelope.get("result", envelope)
        return result if isinstance(result, dict) else {}

    from cc_invoke import _resolve_claude_klabauter_root, cc_invoke  # noqa: E402

    try:
        claude_klabauter_root = _resolve_claude_klabauter_root()
    except RuntimeError:
        return {}
    if not claude_klabauter_root:
        return {}

    try:
        result = cc_invoke("memo.blitz_buckets", {"dry_run": True}, repo_root)
    except RuntimeError:
        return {}
    return result if isinstance(result, dict) else {}


def _partition(candidates: list) -> tuple[list, dict, list, dict]:
    """Split the op's flat kind-discriminated candidate list into its four parts."""
    buckets, summary, supersessions, trigger = [], {}, [], {}
    for candidate in candidates:
        kind = candidate.get("kind")
        if kind == "bucket":
            buckets.append(candidate)
        elif kind == "bucket_summary":
            summary = candidate
        elif kind == "supersession_candidate":
            supersessions.append(candidate)
        elif kind == "trigger":
            trigger = candidate
    return buckets, summary, supersessions, trigger


def _build_dispatches(buckets: list, supersessions: list) -> tuple[list, int]:
    """One dispatch per NON-EMPTY bucket, each carrying its own finished brief.

    An empty bucket yields no dispatch — a fan-out that spawns an agent to
    report "nothing in my bucket" costs a model call for a fact the counts
    already carry.

    Op-supplied dict fields (`id`/`path` on a bucket candidate, `newer`/
    `older`/`basis` on a supersession candidate) are read defensively —
    matching `_fetch_result`/`_partition`'s style in this same file — because
    a malformed/future-drifted `memo.blitz_buckets` envelope must never turn
    into an uncaught KeyError: the module docstring promises "Always exit 0".
    A memo candidate missing `id` or `path` is SKIPPED rather than rendered
    with a placeholder — a dispatch brief listing a blank memo path is worse
    than one that silently omits it. Returns (dispatches, skipped_count) so
    the caller can surface the count instead of swallowing it.
    """
    dispatches = []
    skipped = 0
    for bucket_name, (label, brief_template) in _BUCKET_SPEC.items():
        raw_memos = [b for b in buckets if b.get("bucket") == bucket_name]
        memos = []
        for m in raw_memos:
            memo_id, memo_path = m.get("id"), m.get("path")
            if not memo_id or not memo_path:
                skipped += 1
                continue
            memos.append(m)
        if not memos:
            continue
        brief = brief_template.format(verification=_VERIFICATION_CLAUSE)
        if bucket_name == "dominant":
            memo_ids = {m["id"] for m in memos}
            relevant = []
            for s in supersessions:
                newer, older, basis = s.get("newer"), s.get("older"), s.get("basis")
                if newer is None or older is None or basis is None:
                    skipped += 1
                    continue
                if newer in memo_ids or older in memo_ids:
                    relevant.append(s)
            if relevant:
                # Review: code-reviewer F2 — fold `advisory` into the rendered
                # basis label so AC4's demotion of `same-sender-same-locus` is
                # observable to the ceremony reading this brief, not merely
                # structurally present in the candidate's own shape.
                rendered = "\n".join(
                    f"  - {s['newer']} may supersede {s['older']} "
                    f"[basis: {s['basis']}"
                    + (", advisory" if s.get("advisory") else "")
                    + "]"
                    + (f" shared loci: {', '.join(s['shared_loci'])}" if s.get("shared_loci") else "")
                    for s in relevant
                )
                brief += f"\n\nSupersession CANDIDATES for pass 1:\n{rendered}"
            else:
                brief += (
                    "\n\nNo supersession candidates were detected mechanically. "
                    "Pass 1 still runs — the detector reads declared "
                    "`supersedes:`, same-sender/same-locus overlap, and "
                    "in-body self-declaration prose, and a thread can still "
                    "supersede itself in a shape none of those three see."
                )
        dispatches.append({
            "bucket": bucket_name,
            "label": label,
            "count": len(memos),
            "memos": [m["path"] for m in memos],
            "brief": brief,
        })
    return dispatches, skipped


def _resolve_repo_root() -> str:
    """CLAUDE_PROJECT_DIR -> `git rev-parse --show-toplevel` -> cwd. Never raises.

    Mirrors the sibling resolution ladder in `advance-tracker-status.py` /
    `append-goal-event.py`: bare `cwd` alone is unreliable from a ceremony
    invoked from a subdirectory or with `CLAUDE_PROJECT_DIR` unset (a manual
    re-run, a test harness, a future non-Claude-Code caller), and a wrong
    root here degrades `memo.blitz_buckets` (common_dir-scoped) to reading
    the wrong repo's inbox -- which renders as `{"state": "skipped"}`,
    indistinguishable from the legitimate claude-klabauter-absent skip. This ladder
    narrows but does not eliminate that ambiguity: a `_fetch_result` failure
    still collapses to the same bare `{}` regardless of cause, and adding a
    cause tag to the skip payload would require plumbing failure reasons
    through `_fetch_result`'s three independent failure paths (seam
    malformed, claude-klabauter unresolvable, op RuntimeError) for a distinction only
    useful during manual debugging -- left alone rather than done cheaply.
    """
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return env
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            # A bounded wait, unlike the sibling ladders this otherwise
            # mirrors: this script's contract is that it never blocks the
            # morning ceremony, and a wedged filesystem (stale network mount,
            # a lock another process is holding) turns an unbounded git call
            # into a hang, which is worse here than any wrong answer — the
            # cwd fallback below is a fine degradation, a stalled ceremony
            # is not.
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        proc = None
    resolved = (proc.stdout or "").strip() if proc else ""
    if proc is not None and proc.returncode == 0 and resolved:
        return resolved
    return os.getcwd()


def main() -> int:
    repo_root = _resolve_repo_root()
    result = _fetch_result(repo_root)
    candidates = result.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        print(json.dumps({"state": "skipped"}))
        return 0

    buckets, summary, supersessions, trigger = _partition(candidates)
    if not trigger:
        print(json.dumps({"state": "skipped"}))
        return 0

    if not trigger.get("fires"):
        print(json.dumps({
            "state": "inventory",
            "trigger": trigger,
            "summary": summary,
        }))
        return 0

    dispatches, skipped_candidates = _build_dispatches(buckets, supersessions)
    payload = {
        "state": "escalate",
        "trigger": trigger,
        "summary": summary,
        "dispatches": dispatches,
        "supersession_candidates": supersessions,
        "plan_weight_note": _PLAN_WEIGHT_NOTE,
    }
    if skipped_candidates:
        payload["skipped_candidates"] = skipped_candidates
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
