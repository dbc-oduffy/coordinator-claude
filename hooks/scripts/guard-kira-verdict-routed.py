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

BOUNDED PICKUP CHAIN. `/coordinator:pickup` continues another session's
review chain, and Kira's sidecar can then sit in the authoring session's
share dir rather than the picking-up session's own -- the picking-up
session's integrator sidecar stamps a correct `integrated_from` naming a
stem `_find_answers` cannot resolve without also looking there, and
condition 1 fires on every close as a false block (memo, confirmed; see
docs/plans/2026-09-09-inbox-blitz-xs-s-bundle-21-fixes.md § C14). The
reach is BOUNDED to exactly the other session-ids named on the ONE
handoff record under `state/handoffs/` whose `consumed_by` or
`claimed_by` contains this Stop's own `session_id` -- resolved from that
record, never from a filesystem scan. No record found, or no other
session-id on it, means the reachable set is empty and this guard behaves
exactly as it does with no chain at all -- the non-pickup case is
byte-identical to prior behaviour. `os.listdir` is still called only on
`<share_root>/subagent-share/<session_id>` paths, one per `(root,
session_id)` pair, now with the session-ids enumerated across the chain
rather than singular; there is no scan of `subagent-share/` itself and no
glob.

CONTRACT_EPOCH -- narrow by construction. The epoch filter applies
identically to every sidecar this guard reaches, whether from the current
session's own share dir or a chain-resolved predecessor's (see BOUNDED
PICKUP CHAIN above): `_postdates_epoch` draws the same line regardless of
which session-id supplied the dir, and still fails toward in-scope on a
missing `spawned_at`. The closing window this epoch exists to retire is
now "a chain whose predecessor session opened before 2026-08-30," not
merely "this session opened before 2026-08-30" -- delete
`_CONTRACT_EPOCH_ISO` and `_postdates_epoch` once no session predating
that date, nor any predecessor reachable through a chain, can still
close.

THE DECISION -- entirely from frontmatter, never from a sidecar body:
  1. No Kira sidecar in the session share dir, but other review activity
     is present -> BLOCK (a close that reviewed something owed Kira a run
     too).
  2. A Kira sidecar carrying `findings_count > 0` with no sibling sidecar
     stamping `integrated_from` naming it, and no `## Integrator
     Dispositions` block recorded on the verdict itself -> BLOCK. That block
     is the routing record when no integrator survived to write a sibling. The owed route is
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
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _block_discharge  # noqa: E402

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


def _block_discharge_cli_path() -> str:
    """Absolute path to `block-discharge.py`, derived from THIS guard's own
    location rather than from the invoking repo.

    A consumer repo that installs coordinator as a plugin has no
    `coordinator/` tree of its own, so the relative
    `coordinator/bin/block-discharge.py` this used to print does not exist
    there -- and the guard's whole instruction is therefore unrunnable in
    exactly the repos the ledger-root fix just taught the CLI to serve.
    Reported independently by `example-cockpit-repo-em` and `example-game-repo-em`.

    This guard file sits at `<plugin-root>/hooks/scripts/`, so the CLI is at
    `<plugin-root>/bin/block-discharge.py`. Falls back to the old relative
    form only if that path is absent, which keeps a partially-deployed tree
    printing something rather than nothing.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.join(os.path.dirname(os.path.dirname(here)), "bin", "block-discharge.py")
    if os.path.isfile(candidate):
        return candidate
    return os.path.join("coordinator", "bin", "block-discharge.py")


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


def _handoff_field_values(meta: dict, key: str) -> list[str]:
    """Normalize `consumed_by`/`claimed_by` to a list of session-id
    strings -- both fields are conventionally a bare scalar, but
    `_read_frontmatter` already parses an inline `[a, b]` or block-list
    shape into a list, and this reads whichever shape is on disk."""
    val = meta.get(key)
    if isinstance(val, list):
        return [v for v in val if isinstance(v, str) and v.strip()]
    if isinstance(val, str) and val.strip():
        return [val.strip()]
    return []


def _pickup_chain_session_ids(repo_root: str, session_id: str) -> list[str]:
    """The other session-ids named on the ONE handoff record under
    `state/handoffs/` whose `consumed_by` or `claimed_by` contains this
    Stop's own `session_id` -- see the module docstring's BOUNDED PICKUP
    CHAIN section. `[]` when no such record exists, or the record names no
    other session-id: the reachable set is bounded to that single record,
    never a directory scan or fanout past it."""
    handoffs_dir = os.path.join(repo_root, "state", "handoffs")
    try:
        names = sorted(os.listdir(handoffs_dir))
    except OSError:
        return []
    for name in names:
        if not name.endswith(".md"):
            continue
        meta = _read_frontmatter(os.path.join(handoffs_dir, name))
        consumed = _handoff_field_values(meta, "consumed_by")
        claimed = _handoff_field_values(meta, "claimed_by")
        if session_id not in consumed and session_id not in claimed:
            continue
        others: list[str] = []
        seen: set[str] = set()
        for sid in consumed + claimed:
            if sid == session_id or sid in seen:
                continue
            seen.add(sid)
            others.append(sid)
        return others
    return []


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


#: The heading `append-integrator-dispositions` writes onto the REVIEWER's own
#: sidecar (`coordinator_core/ops/append_integrator_dispositions.py`).
_DISPOSITIONS_HEADING = "## Integrator Dispositions"


def _body_lines(path: str) -> list[str]:
    """Body lines below the frontmatter block. `[]` on any read failure — a
    guard that cannot read a file must never block on what it did not see."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return []
    if not lines or lines[0].strip() != "---":
        return lines
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return lines[i + 1:]
    return []


def _has_recorded_dispositions(path: str) -> bool:
    """True when this sidecar carries its own `## Integrator Dispositions`
    block with content under it.

    That block IS the routing record when the integrator never ran to write a
    sibling: `append-integrator-dispositions` writes it onto the reviewer's
    sidecar, and stamps `integrated_from` on an integrator run-report only
    when one exists. A fire killed before its integrators land leaves none,
    and then every honest route to a sibling is closed — hand-authoring one is
    refused by `block_hand_authored_sidecar_creation`, and
    `coordinator-doc-new --type run-report` demands a plan and chunk asserting
    an execution that never happened. Reported twice on example-market-data-repo
    (nonces 2f8c15b2, 48e0aed6). The alternative to reading this block is an
    EM stamping a receipt on an agent that never ran, which is the false
    attestation the stamp exists to prevent."""
    lines = _body_lines(path)
    for i, line in enumerate(lines):
        if line.strip() != _DISPOSITIONS_HEADING:
            continue
        for rest in lines[i + 1:]:
            stripped = rest.strip()
            if not stripped or stripped.startswith("<!--"):
                continue
            if stripped.startswith("#"):
                break
            return True
    return False


def _is_untouched_scaffold(path: str) -> bool:
    """True when nothing has been written into this sidecar's body.

    A provisioned scaffold carries headings and nothing under them. Its
    `integrator_receipt` is spliced AT SPAWN, so an integrator killed before it
    read anything is indistinguishable, by frontmatter alone, from one that ran
    and skipped its stamp — and the guard then tells the EM to wait for a
    corpse. Headings and HTML comments are the scaffold; one line of anything
    else means the agent wrote."""
    for line in _body_lines(path):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("<!--"):
            continue
        return False
    return True


def _unstamped_integrators(
    in_scope: list[tuple[str, dict]], paths: dict | None = None
) -> list[str]:
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

    A FOURTH state is excluded rather than blocked: a sidecar whose body is
    still the provisioned scaffold. Its agent was killed before it read
    anything — the receipt was spliced at spawn — so naming it sends the EM to
    wait on a run that will never finish. See `_is_untouched_scaffold`.

    The other three still BLOCK: the stamp is genuinely absent in every case
    and the guard has no business inventing it. They differ in the REMEDY, and naming
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
        if "integrator_receipt" in m
        and not m.get("integrated_from")
        and not (paths and _is_untouched_scaffold(paths.get(f, "")))
    ]


#: How many integrator filenames the message prints before summarising the rest.
#: A session that has run fifty integrators printed fifty names per unrouted
#: verdict, three times over — and a list that long tells the reader nothing
#: about WHICH sidecar to stamp, which is the one thing the remedy needs.
_NAMES_SHOWN = 5


def _name_a_few(names: list[str]) -> str:
    ordered = sorted(names)
    if len(ordered) <= _NAMES_SHOWN:
        return ", ".join(ordered)
    rest = len(ordered) - _NAMES_SHOWN
    return f"{', '.join(ordered[:_NAMES_SHOWN])}, and {rest} more"


def _integrators_that_could_have_received(
    kira_meta: dict, unstamped: list[str], in_scope: list[tuple[str, dict]]
) -> list[str]:
    """Narrow the named integrators to those spawned at or after this review.

    `spawned_at` is engine-written on every sidecar, so an integrator that
    spawned BEFORE the review existed cannot have been given it — naming one
    sends the EM to stamp a sidecar whose agent never saw these findings. The
    filter is skipped whole when either timestamp is missing or unparseable:
    a narrowing that silently drops every candidate would flip the message to
    the "never dispatched" branch and invite a re-dispatch of discharged work,
    which is the more expensive error of the two."""
    reviewed_at = _spawned_at(kira_meta)
    if reviewed_at is None:
        return unstamped
    later = [
        f
        for f in unstamped
        for m in (dict(in_scope).get(f) or {},)
        if (_spawned_at(m) or reviewed_at) >= reviewed_at
    ]
    return later or unstamped


def _spawned_at(meta: dict):
    raw = (meta or {}).get("spawned_at")
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return datetime.fromisoformat(raw.strip().strip("'\""))
    except ValueError:
        return None


#: A journal untouched this long is a run that died, not one still working.
_LIVE_JOURNAL_SECONDS = 2 * 60 * 60


def _live_workflow_runs(transcript_path) -> list[str]:
    """Workflow runs of this session with an agent still in flight.

    A review inside a Workflow fire is unrouted by construction until that fire's integrator
    runs, minutes to an hour later, so condition 2 read every in-flight wave as an unrouted
    verdict and blocked each turn close with a nonce the EM could only discharge as "wait".
    A run is live when its journal holds a `started` agent with no `result`, and the journal
    was written recently: a killed run leaves a started agent forever and must not suppress
    the check forever. The first Stop after the run lands evaluates everything it deferred."""
    if not isinstance(transcript_path, str) or not transcript_path.endswith(".jsonl"):
        return []
    base = os.path.join(transcript_path[: -len(".jsonl")], "subagents", "workflows")
    try:
        runs = os.listdir(base)
    except OSError:
        return []
    live = []
    for run in runs:
        journal = os.path.join(base, run, "journal.jsonl")
        try:
            if time.time() - os.path.getmtime(journal) > _LIVE_JOURNAL_SECONDS:
                continue
            started, finished = set(), set()
            with open(journal, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        rec = json.loads(line)
                    except ValueError:
                        continue
                    if rec.get("type") == "started":
                        started.add(rec.get("agentId"))
                    elif rec.get("type") == "result":
                        finished.add(rec.get("agentId"))
        except OSError:
            continue
        if started - finished:
            live.append(run)
    return sorted(live)


_BLOCK_HEADER = (
    "[guard] This close carries an unrouted Kira (overengineering-reviewer) "
    "verdict.\n"
)


def _emit_block(reasons: list[str], repo_root: str, session_id: str) -> int:
    nonce = _block_discharge.record_fire(
        repo_root, session_id, "guard-kira-verdict-routed", "\n".join(reasons)
    )
    if nonce is not None:
        discharge_note = (
            f"Recorded as {nonce}. When you have acted on this, run:\n"
            f"  python {_block_discharge_cli_path()} record --nonce {nonce} "
            f'--action "<what you did>" --repo-root {repo_root}\n'
        )
    else:
        discharge_note = (
            f"Could not record this fire (write failed) at "
            f"state/block-discharge/{session_id}.jsonl.\n"
            "No nonce to discharge -- this failure is visible in stderr, not "
            "laundered into a clean check.\n"
        )
        sys.stderr.write(
            "[guard] guard-kira-verdict-routed: record_fire write failed, "
            "no nonce minted\n"
        )
    sys.stderr.write(_BLOCK_HEADER + "\n".join(reasons) + "\n" + discharge_note)
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

    chain_session_ids = _pickup_chain_session_ids(repo_root, session_id)
    share_dirs = [
        os.path.join(repo_root, root, "subagent-share", sid)
        for root in _SHARE_ROOTS
        for sid in (session_id, *chain_session_ids)
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
    paths: dict[str, str] = {}
    for fname, fpath in listed:
        entries.append((fname, _read_frontmatter(fpath)))
        paths[fname] = fpath

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
    live_runs = _live_workflow_runs(payload.get("transcript_path"))
    if live_runs and kira_entries:
        sys.stdout.write(
            f"[guard] guard-kira-verdict-routed deferred: workflow run(s) {', '.join(live_runs)} "
            "still in flight; their integrators route these verdicts. Evaluated at the first "
            "Stop after they land.\n"
        )
        kira_entries = []
    for kira_file, kira_meta in kira_entries:
        findings_count = _to_int(kira_meta.get("findings_count"))
        answers = _find_answers(kira_file, in_scope)

        # Condition 2: a findings-bearing Kira verdict nobody answered. The
        # owed route is named unconditionally -- an unanswered ordinary
        # verdict and an unanswered rebuild verdict are the same failure:
        # an unrouted Kira sidecar (staff-eng review, 2026-08-30).
        # A dispositions block recorded on the verdict itself IS an answer.
        if _has_recorded_dispositions(paths.get(kira_file, "")):
            continue

        if findings_count is not None and findings_count > 0 and not answers:
            ran_but_unstamped = _integrators_that_could_have_received(
                kira_meta, _unstamped_integrators(in_scope, paths), in_scope
            )
            if ran_but_unstamped:
                named = _name_a_few(ran_but_unstamped)
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
                    f"recommended a rebuild. Where the wave that would have "
                    f"integrated these findings is dead (a killed fire leaves "
                    f"untouched scaffolds), record the dispositions you landed "
                    f"on {kira_file} itself with append-integrator-dispositions; "
                    f"that block answers this verdict. Never stamp a receipt on "
                    f"an agent that did not run."
                )

    if not reasons:
        return 0

    return _emit_block(reasons, repo_root, session_id)


if __name__ == "__main__":
    sys.exit(main())
