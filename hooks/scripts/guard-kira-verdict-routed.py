"""Stop-hook guard -- hard-stop a close whose Kira (overengineering-reviewer)
verdict was never routed anywhere.

Spec: docs/plans/2026-08-30-kira-verdict-routing-join-key.md (chunk C5).
Dispatch brief: state/dispatch-briefs/2026-08-30-kira-verdict-routing-join-key/C5.md

THE PROBLEM. `/workstream-complete` doctrine is emphatic that Kira fires on
every close, that her findings route through `review-integrator`
unconditionally, and that a `rebuild_recommended: true` verdict routes
instead to an executor carrying a refactor remit -- but none of that was
ever mechanical. C1 gave Kira a terminal-stamp contract (`findings_count`
and the `rebuild_recommended`/`rebuild_rationale`/`rebuild_scope` delta,
lifted to top-level frontmatter); C2/C3 gave review-integrator and the
refactor executor route an `integrated_from` stamp naming the Kira
sidecar(s) they answered; C4 typed all of it in
`review-findings.schema.json`. This module is the first thing that
actually READS those stamps and can hard-stop a close that skipped the
routing they encode. See spec for the full stamp shape -- this guard's
own read set is exactly the five facts named below.

WHY `stop-dispatch.py`, NOT `postuse-stop-family-dispatch.py`. The latter is
registered on PostToolUse and gated by `GuardScopeDescriptor` file-path
matching against `tool_input.file_path` -- a session-level predicate like
this one has no file-path key to match, so an entry there registers cleanly
and then fires zero times, forever (see
`docs/research/spike-verdicts/2026-08-29-six-detectors-onto-stop-family-runner.md`,
verdict `not-viable`, for exactly this enrolment shape already having been
tried once). `stop-dispatch.py` is the single Stop entrypoint: its `main()`
returns 2 if any registered `StopGuard` fires, which IS the hard stop this
guard exists to deliver.

TRIGGER SCOPE -- why this must not fire on every Stop. Every peer blocking
guard already registered in `stop-dispatch.py` (`_pre_manufactured_blocker`,
`_pre_em_report_altitude`) begins its precondition with the same two-leg
check this guard's `main()` repeats: `agent_id` present means this Stop
belongs to a SUBAGENT, not the EM -- including Kira's own Stop, before any
integrator could possibly have run yet -- and `stop_hook_active` means this
is a re-entrant Stop the platform is already replaying, where re-blocking
would spin past `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` rather than deliver a
one-shot-per-turn block. Both legs are the platform contract for any
blocking Stop hook (`claude-code-platform-gotchas.md:790`), not an
implementation detail this module could shortcut.

CONTRACT_EPOCH -- narrow by construction. This guard only ever lists the
CURRENT session's own share dir, so the only sidecar that can be both
pre-contract and visible here is one written by this same session before
the epoch (a session open across the boundary) -- an already-closing
window, not a standing one. `_postdates_epoch` draws that line and fails
toward in-scope on a missing `spawned_at`. Delete `_CONTRACT_EPOCH_ISO`
and `_postdates_epoch` once no session predating 2026-08-30 can still
close.

THE DECISION -- entirely from frontmatter, never from a sidecar body:
  1. No Kira sidecar in the session share dir, but other review activity
     is present -> BLOCK (a close that reviewed something owed Kira a run
     too).
  2. A Kira sidecar carrying `findings_count > 0` with no sibling sidecar
     stamping `integrated_from` naming it -> BLOCK. The owed route is
     named unconditionally in the message (review-integrator, or a
     refactor executor if the verdict recommended a rebuild) -- an
     unanswered ordinary verdict and an unanswered rebuild verdict are
     the same failure: an unrouted Kira sidecar.

A third condition -- blocking a rebuild verdict answered by BOTH an
integrator AND a refactor executor -- was cut (staff-eng review,
2026-08-30): it could only fire when both answering agents had already
stamped `integrated_from` correctly, which is the exact compliance whose
absence is the problem this guard exists to catch; condition 2 already
covers the unanswered case.

NO WARN TIER, NO ENV ESCAPE, NO `--force`. If the guard seems to need an off
switch the design is wrong -- widen the epoch or the detection instead of
adding one.

Contract:
  stdin   -- Stop JSON (session_id, transcript_path, cwd, stop_hook_active, agent_id...)
  stdout  -- a could-not-evaluate advisory breadcrumb on a fail-open path
             only (stdin unreadable, repo root unresolvable, share dir
             unlistable); silent on every clean-pass or BLOCK outcome
  stderr  -- the BLOCK message, only when the guard fires
  exit 2  -- an unrouted (or over-routed) Kira verdict was found this Stop
  exit 0  -- every other path, including every failure path (fail-open)

Graceful degradation: any failure to read stdin, resolve the repo root, or
list/parse the session share directory falls through to a silent exit 0 --
this guard can only ever block on a POSITIVELY-read frontmatter fact, never
on its own inability to read one.
"""
from __future__ import annotations

import json
import os
import sys

# The commit/date C1's terminal-stamp contract lands at -- see the module
# docstring's CONTRACT_EPOCH section. Delete this constant and
# `_postdates_epoch` once no session predating 2026-08-30 can still close.
_CONTRACT_EPOCH_ISO = "2026-08-30T00:00:00Z"

# Pinned against a REAL provisioned sidecar's stamped `agent_type`, not a
# hand-typed literal (review-integrator, 2026-08-30, staff-eng finding 0):
# state/subagent-share/0f81c1a3-9826-441e-9e0a-08e80f92b2fc/
# coordinatoroverengineering-reviewer.a21590e6fcf0df433.md stamps
# `agent_type: coordinator:overengineering-reviewer` -- every real sidecar
# on disk carries the `coordinator:` namespace prefix (16/16 checked). The
# bare form is compared too, in case an unnamespaced provisioner ever
# exists, via `_normalize_agent_type` below.
_KIRA_AGENT_TYPE = "overengineering-reviewer"

# Both machinery roots are read, union-of-filenames, first root wins on a
# duplicate name. The engine's `machinery_paths.machinery_root()` moved from
# `state/` to `.coordinator-local/` on 2026-09-02, so an integrator that
# stamps `integrated_from` in the provisioned directory is invisible to a
# scan of the old literal alone -- the guard then blocks a session that did
# exactly what its own remedy prescribes, which is the one state where
# blocking is wrong. Same reasoning and same retirement condition as
# `guard-review-integrator-sidecar-intake.py`'s dual-root path regex; see
# state/debt-backlog/2026-09-02-retire-dual-root-sidecar-path-regex-
# alternation-c1a9e2b3.yaml for the revert.
_SHARE_ROOTS = (".coordinator-local", "state")


def _repo_root(payload: dict) -> str | None:
    cwd = payload.get("cwd") or os.getcwd()
    if not isinstance(cwd, str):
        return None
    probe = os.path.abspath(cwd)
    while True:
        if os.path.exists(os.path.join(probe, ".git")):
            return probe
        parent = os.path.dirname(probe)
        if parent == probe:
            return None
        probe = parent


def _read_frontmatter(path: str) -> dict:
    """Flat, stdlib-only top-level `key: value` line-scan of the YAML
    frontmatter block, matching `_posture.py`'s / `guard-manufactured-
    blocker.py`'s own line-scan convention -- no YAML dependency.

    Only COLUMN-ZERO keys are read (an indented key, e.g. one nested under
    `divergence:`, is never surfaced as a top-level fact -- the same
    column-zero discipline C1's terminal-stamp contract itself requires of
    the writer). Returns `{}` on any read/shape failure -- a guard that
    cannot prove a fact must never block on it.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return {}
    if not lines or lines[0].strip() != "---":
        return {}
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}

    body = lines[1:end]
    meta: dict = {}
    i = 0
    while i < len(body):
        line = body[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        if line[0].isspace():
            # Indented -- belongs to a nested block (e.g. `divergence:`'s
            # own sub-keys), never a top-level fact. Skip it.
            i += 1
            continue
        if ":" not in line:
            i += 1
            continue
        key, _, rest = line.partition(":")
        key = key.strip()
        rest = rest.strip()
        if "#" in rest:
            rest = rest.split("#", 1)[0].strip()
        if rest.startswith("[") and rest.endswith("]"):
            inner = rest[1:-1]
            meta[key] = [v.strip().strip("'\"") for v in inner.split(",") if v.strip()]
            i += 1
            continue
        if rest in ("", "{}"):
            # Possible block-list continuation (`key:` then `  - item`
            # lines) -- distinct from an empty scalar or an inline `{}`
            # mapping, which `integrated_from` never uses.
            items: list[str] = []
            j = i + 1
            while j < len(body):
                candidate = body[j]
                # Blank and comment lines are skipped here for the same
                # reason the top-level loop skips them: they are YAML
                # nothing. Collecting only on `- ` and stopping otherwise
                # ended the list at the first comment, recording an empty
                # scalar for a key that HAS items -- so a routed verdict
                # read as unrouted and blocked its own close.
                if not candidate.strip() or candidate.lstrip().startswith("#"):
                    j += 1
                    continue
                if not candidate.lstrip().startswith("- "):
                    break
                items.append(candidate.strip()[2:].strip().strip("'\""))
                j += 1
            if items:
                meta[key] = items
                i = j
                continue
            meta[key] = rest
            i += 1
            continue
        meta[key] = rest.strip("'\"")
        i += 1
    return meta


def _postdates_epoch(meta: dict) -> bool:
    """True unless `spawned_at` is present AND strictly precedes
    `_CONTRACT_EPOCH_ISO` -- see the module docstring's CONTRACT_EPOCH
    section for why a MISSING `spawned_at` fails toward in-scope rather
    than toward a free pass."""
    spawned = meta.get("spawned_at")
    if not isinstance(spawned, str) or not spawned:
        return True
    return spawned >= _CONTRACT_EPOCH_ISO


def _to_int(value) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _kira_stem(filename: str) -> str:
    return filename[:-3] if filename.endswith(".md") else filename


def _normalize_agent_type(agent_type) -> str | None:
    """Strip an optional `<namespace>:` prefix (every real sidecar stamps
    `coordinator:overengineering-reviewer`, never the bare form) so the
    comparison in `_is_kira` matches production data. Not a general parser
    -- just the one leading `word:` segment real stamps carry."""
    if not isinstance(agent_type, str) or not agent_type:
        return None
    if ":" in agent_type:
        return agent_type.split(":", 1)[1]
    return agent_type


def _is_kira(filename: str, meta: dict) -> bool:
    """Decided ENTIRELY from the stamped `agent_type` frontmatter field --
    no filename fallback. A sidecar with no `agent_type` is a fact this
    guard cannot prove and must not act on (staff-eng finding 2, 2026-08-30:
    the filename leg was the only path that ever fired on real data, and
    only for `.blocks.md` contract scaffolds that carry no frontmatter at
    all -- see the share-dir listing's `.blocks.md` exclusion below)."""
    return _normalize_agent_type(meta.get("agent_type")) == _KIRA_AGENT_TYPE


def _is_review_activity(filename: str, meta: dict) -> bool:
    """Broader than `_is_kira` -- any OTHER review-shaped sidecar (a
    code-reviewer slice, a staff-eng review, a review-integrator run).
    Used only for BLOCK condition 1 ('reviewed something, but never ran
    Kira')."""
    if "findings_count" in meta:
        return True
    kind = meta.get("kind")
    if kind in ("review-findings", "staff-eng-review"):
        return True
    agent_type = meta.get("agent_type", "")
    if isinstance(agent_type, str) and "review" in agent_type.lower():
        return True
    return "review" in filename.lower()


def _block_condition_1(in_scope: list[tuple[str, dict]]) -> bool:
    kira_present = any(_is_kira(f, m) for f, m in in_scope)
    if kira_present:
        return False
    return any(_is_review_activity(f, m) and not _is_kira(f, m) for f, m in in_scope)


def _find_answers(kira_filename: str, in_scope: list[tuple[str, dict]]) -> list[str]:
    """Return the filenames of sibling sidecars whose `integrated_from`
    names this Kira sidecar.

    Both stamped shapes count. `integrated_from` names ONE sidecar in the
    common case, so the scalar is the likelier thing an agent writes, and
    nothing in the block message asks for a list -- a list-only membership
    test reads on the receiving end as "the routing never happened" and
    invites a re-dispatch of findings that are already discharged
    (claude-klabauter-em FYI, 2026-08-30)."""
    stem = _kira_stem(kira_filename)
    answers: list[str] = []
    for f, m in in_scope:
        if f == kira_filename:
            continue
        integrated = m.get("integrated_from")
        if isinstance(integrated, str):
            integrated = [integrated] if integrated.strip() else []
        if not isinstance(integrated, list):
            continue
        if stem not in integrated and kira_filename not in integrated:
            continue
        answers.append(f)
    return answers


def _unstamped_integrators(in_scope: list[tuple[str, dict]]) -> list[str]:
    """Filenames of sibling sidecars that RAN an integrator but stamped no
    `integrated_from`.

    `integrator_receipt` is spliced into an integrator's own sidecar
    frontmatter by the engine at spawn (`subagent_sandbox/provision_report.
    _splice_integrator_receipt`), so its presence is proof a review-integrator
    actually ran; `integrated_from` is a separate manual Edit the agent makes
    afterwards (`agents/review-integrator.md` § The one write after your
    disposition block). The two come from different writers, so a receipt
    without a stamp spans THREE states this guard cannot tell apart: an
    integrator still in flight (the receipt is spliced at spawn, before the
    agent has read anything), one that finished and skipped only that last
    Edit, and -- to condition 2 -- one that was never dispatched at all.

    All three still BLOCK: the stamp is genuinely absent in every case and the
    guard has no business inventing it. They differ in the REMEDY, and naming
    the wrong one is not cosmetic in either direction. Telling an EM to
    dispatch an integrator that already ran invites a re-dispatch of findings
    already discharged, the exact miss `_find_answers` was widened to avoid;
    telling an EM to hand-stamp one that is still running invites attesting
    dispositions that do not exist yet. The message therefore names the
    in-flight possibility rather than asserting the integrator finished.

    Detected by KEY PRESENCE, not by value. `_read_frontmatter` is a flat
    column-zero line-scan, so a nested block surfaces as its bare key with an
    empty scalar and its sub-keys are skipped -- exactly the shape the engine
    writes. Testing the value for a dict would never match and the branch
    would be dead."""
    return [
        f
        for f, m in in_scope
        if "integrator_receipt" in m and not m.get("integrated_from")
    ]


_BLOCK_HEADER = (
    "[guard] This close carries an unrouted Kira (overengineering-reviewer) "
    "verdict.\n"
)


def _emit_block(reasons: list[str]) -> int:
    sys.stderr.write(_BLOCK_HEADER + "\n".join(reasons) + "\n")
    return 2


def _emit_could_not_evaluate(reason: str) -> None:
    """A fail-OPEN advisory breadcrumb (stdout, exit stays 0) -- fail-open
    on the block itself is correct and stays, but a silent could-not-
    evaluate path is byte-identical to a clean close and therefore
    unfalsifiable in the field (staff-eng finding 4, 2026-08-30)."""
    sys.stdout.write(f"[guard] guard-kira-verdict-routed could not evaluate: {reason}\n")


def main() -> int:
    try:
        raw = sys.stdin.read()
    except Exception:
        _emit_could_not_evaluate("failed to read stdin")
        return 0

    try:
        payload = json.loads(raw) if raw else {}
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        _emit_could_not_evaluate("stdin was not valid JSON")
        return 0

    # Trigger scope, verbatim per the C5 brief and matching
    # `_pre_manufactured_blocker` -- a subagent's own Stop (Kira's included)
    # and a re-entrant Stop replay must never see this guard evaluate at
    # all. This is the platform contract for a blocking Stop hook, not this
    # module's own design choice (claude-code-platform-gotchas.md:790).
    if payload.get("agent_id"):
        return 0
    if payload.get("stop_hook_active"):
        return 0

    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        _emit_could_not_evaluate("no session_id in the Stop payload")
        return 0

    repo_root = _repo_root(payload)
    if repo_root is None:
        _emit_could_not_evaluate("could not resolve repo root from cwd")
        return 0

    share_dirs = [
        os.path.join(repo_root, root, "subagent-share", session_id)
        for root in _SHARE_ROOTS
    ]
    listed: list[tuple[str, str]] = []
    seen: set[str] = set()
    unreadable: list[str] = []
    for share_dir in share_dirs:
        try:
            names = os.listdir(share_dir)
        except OSError:
            unreadable.append(share_dir)
            continue
        for f in sorted(names):
            if not f.endswith(".md") or f.endswith(".blocks.md"):
                continue
            if f in seen:
                continue
            seen.add(f)
            listed.append((f, os.path.join(share_dir, f)))

    if len(unreadable) == len(share_dirs):
        _emit_could_not_evaluate(
            "could not list any share dir: " + ", ".join(unreadable)
        )
        return 0

    entries: list[tuple[str, dict]] = []
    for fname, fpath in listed:
        entries.append((fname, _read_frontmatter(fpath)))

    if not entries:
        return 0

    # CONTRACT_EPOCH scoping applies uniformly across every condition below
    # -- see module docstring. A pre-epoch sidecar is invisible to this
    # guard entirely, not merely exempt from one condition.
    in_scope = [(f, m) for f, m in entries if _postdates_epoch(m)]
    if not in_scope:
        return 0

    reasons: list[str] = []

    # Condition 1: session reviewed something but never ran Kira at all.
    if _block_condition_1(in_scope):
        reasons.append(
            "- Other review activity ran this session, but no Kira "
            "(overengineering-reviewer) sidecar is present. Kira fires on "
            "every close (SKILL.md); dispatch her before closing."
        )

    kira_entries = [(f, m) for f, m in in_scope if _is_kira(f, m)]
    for kira_file, kira_meta in kira_entries:
        findings_count = _to_int(kira_meta.get("findings_count"))
        answers = _find_answers(kira_file, in_scope)

        # Condition 2: a findings-bearing Kira verdict nobody answered. The
        # owed route is named unconditionally -- an unanswered ordinary
        # verdict and an unanswered rebuild verdict are the same failure:
        # an unrouted Kira sidecar (staff-eng review, 2026-08-30).
        if findings_count is not None and findings_count > 0 and not answers:
            ran_but_unstamped = _unstamped_integrators(in_scope)
            if ran_but_unstamped:
                named = ", ".join(sorted(ran_but_unstamped))
                reasons.append(
                    f"- {kira_file} stamps findings_count={findings_count} with no "
                    f"sibling sidecar's integrated_from naming it. An integrator "
                    f"was dispatched ({named} carries an integrator_receipt, "
                    f"which the engine splices AT SPAWN) -- so it is either "
                    f"still in flight or finished having skipped only the "
                    f"stamp -- do NOT re-dispatch it. If it is still running, "
                    f"wait; hand-stamping now would attest dispositions that "
                    f"do not exist yet. Once it has finished, add a top-level "
                    f"`integrated_from: [{_kira_stem(kira_file)}]` to that "
                    f"sidecar's frontmatter at column zero, verify its "
                    f"dispositions are the ones you actually landed, and re-close."
                )
            else:
                reasons.append(
                    f"- {kira_file} stamps findings_count={findings_count} with no "
                    f"sibling sidecar's integrated_from naming it. Owed route: "
                    f"review-integrator, or a refactor executor if the verdict "
                    f"recommended a rebuild."
                )

    if not reasons:
        return 0

    return _emit_block(reasons)


if __name__ == "__main__":
    sys.exit(main())
