---
title: Review integration doctrine
created: 2026-05-17
type: doctrine
related:
  - plugins/coordinator/docs/wiki/reviewer-pipeline/prior-art-checker.md
  - plugins/coordinator/docs/wiki/reviewer-pipeline/docs-checker-pre-review.md
---

# Review Integration Doctrine

How a reviewer applies its own findings, and how the engine checks that it did — there is no
separate integrator agent; the reviewer that finds a defect fixes it.

## The reviewer applies every finding, then logs a verifiable record

Apply every finding in place in the reviewed artifact — source, test, plan body, or wiki. Then
write a `## Findings Ledger` section in your own sidecar holding one fenced ` ```json ` array,
with exactly one row per finding in your `ReviewOutput`:

    {"id": "finding-<N>", "file": "<repo-relative/forward-slash>", "before": "<exact text replaced, or empty for an insertion>", "after": "<exact text now present, or empty for a deletion>"}

Then run `review-findings-ledger verify --sidecar <your sidecar>`. Exit 0 is done. Non-zero names
the failing rows: fix and re-run. Never write attribution (`Review:`, finding numbers, reviewer
names) into the reviewed artifact, plans included — the ledger is the attribution record
(`review-attribution-lives-in-the-sidecar-not-the-source.md`).

**Every finding folds, nits included; the sole exemption is believing the finding is wrong, said
out loud and defended** in the ledger row's evidence. Filing a current-workstream defect to a
backlog queue is not closure — a defect blocking work in flight needs fixing, or an explicit
EM-recorded rejection with a reason, never a queue entry that reads as progress while nothing
changes for the workstream it blocks
(`coordinator-tripwires/a-reviewer-applies-every-finding-it-logs.md`).

## Verdicts

`OK`/`WARN`/`BLOCKED`: apply everything. `REJECTED`/`PIVOT` (premise failure): apply nothing, and
log every row as `"status": "suspended"`. `review-findings-ledger verify` accepts `suspended` only
under those two verdicts. Kira's `rebuild_recommended: true`: apply nothing. The EM dispatches an
executor with a refactor remit, and that executor stamps `integrated_from: [<kira stem>]` in its
own run-report — the only remaining writer of `integrated_from`.

## Engine op `review-findings-ledger`

- `verify --sidecar <p>` passes when the ledger row count equals the findings count, and each row
  meets one of three conditions:
  - `applied` with evidence: `after` is present in `file` now, confirmed against a
    `baseline_sha256` recorded per touched file before any edit. A deletion (`after` empty)
    requires `before` non-empty, absent from `file` now, present at baseline. A replacement
    requires `before` present at baseline and absent now, `after` present now. An insertion
    (`before` empty) requires `after` non-empty and not already present at baseline. Every
    comparison is in-process and CRLF-normalised.
  - `em-rejected` with a non-empty `reason`.
  - `suspended`, under a premise verdict.

  On a pass, `verify` stamps `findings_ledger: {rows, applied, em_rejected, suspended,
  verified_at}` in the sidecar frontmatter, and each row gets `verified: true` so a later
  reviewer's edits do not un-verify it.
- `reject --sidecar <p> --finding finding-<N> --reason "<one line>"` restores `before` over
  `after` in `file`, sets `status: em-rejected` plus the reason, and re-stamps. Only the EM may
  run `reject` — a subagent invoking it is denied by a bash guard. When a later reviewer's edit
  has superseded an earlier row's `after`, that later row carries `superseded_by: finding-<earlier-id>`
  instead of leaving it unrelated; `verify` accepts a row carrying `superseded_by` as satisfying
  its own row without re-deriving evidence for the finding it names. No separate adjudication lane
  exists between sequential reviewers on one artifact — the EM reads each reviewer's ledger and
  the `superseded_by` chain directly.
- `targets --add <repo-relative path>...` appends the review target set to
  `<git_root>/.git/coordinator-sessions/<em_session_id>/review-targets.txt`, one repo-relative
  forward-slash path per line, de-duplicated. The EM runs it before dispatching a confined
  reviewer, naming the plan path, a slice's frozen file set, or a diff's file list. A subagent
  invoking `targets` is denied by the same guard as `reject` — it would otherwise widen what a
  confined reviewer may write. Absolute paths and drive letters are refused.

## Reviewer write access reaches the reviewed artifact, and only that

A confined reviewer (`coordinator:code-reviewer`) may write inside its sandbox, which holds its
sidecar, and to any path in the session's registered review targets. Every other path is still
denied, including hooks, guards, and sibling trees — deleting the write-confinement guard outright
would let a confined reviewer edit the very guard that confines it. With no targets registered,
the guard is sandbox-only: the reviewer cannot apply its findings, and `verify` fails visibly
rather than the write landing somewhere unintended. The reviewer Bash allowlist stays — reviewers
edit, they do not execute; `verify` is on that allowlist.

## Same artifact means sequential; disjoint slices mean parallel

Two reviewers editing one artifact would race. A plan's reviewers run in sequence — premise
checker first, each verifying before the next starts. A plan's review-phase wall time is therefore
the sum of its reviewers' durations, not the slowest one alone.

Code review over a diff is different: it runs as one parallel wave, and every reviewer in it —
slice owners, Kira (`coordinator:overengineering-reviewer`), and every named persona — applies
every finding it logs, in place, with an exact-text `Edit`, including a finding outside its own
slice. When an `Edit` misses because another writer moved the text first, re-read and re-apply.
The EM sweeps `verify` over every sidecar once the wave finishes and lands one scoped commit for
the whole wave, never one per slice.

## No integration pass

There is no separate integrator agent and no integrate remit. Every reviewer applies its own
findings as it goes (§ The reviewer applies every finding, above), and there is no second review
round. The one thing that returns to the EM instead of being applied in place is a Kira
`rebuild_recommended: true`, or a `REJECTED`/`PIVOT` premise verdict (§ Verdicts) — everything
else is applied and verified before the review stage ends.

## Pre-flight lens findings are not the reviewer's to fold

The pre-flight lens checkers (`prior-art-checker`, `plan-coverage-checker`, `docs-checker`,
`external-pattern-checker`) write to a structurally different home —
`.coordinator-local/plan-sidecars/<plan-stem>.<lens>.md`, plan-derived rather than session-keyed —
and their findings are never a reviewer's own findings-ledger input, however tradeoff-free they
look. A lens finding that belongs in the plan body is plan-body maintenance: dispatch
`coordinator:enricher`, never fold it under a reviewer's own ledger row.

## Re-verify reviewer premises against artifacts landing after review

Schemas, function signatures, and file layouts can change between when a review runs and when its
findings are applied. Before applying any finding that contains "TBD," "confirm later," "verify
before applying," or a premise about a schema/path/API, read the current state of the referenced
artifact. If the premise fails to hold, drop the finding (not the whole review — just that
finding) and note the drop in the ledger row's evidence.

**Sidecar `<file>.md § <section>` citations need a two-part verification.** Prior-art-checker,
docs-checker, and plan-coverage-checker sidecars routinely cite a wiki by name and section. Before
acting on such a citation, verify both that (a) the cited path exists (check `archive/` for
relocated wikis) and (b) the section's scope actually maps to the deliverable — a citation can
resolve to a real file and a real section that nonetheless addresses a different concern.

## A reviewer recommendation is not authority to deviate from what shipped

Spec authority is the PM's, not a reviewer's. Applying a reviewer's recommendation against
already-shipped code can be reverted by the PM — the reviewer exposed a consideration, but "what
shipped" is the PM's ratified surface until the PM says otherwise.

**A `system-reminder` reporting a file the user or a linter just modified is ground-truth signal —
stop additive cleanup and roll back to match.** That is the strongest available signal of the
desired shape, stronger than any in-flight reviewer finding.

## Single-agent math and precedence findings need verification

A single reviewer flagging a logic error, arithmetic mistake, or operator-precedence bug requires
verification before applying it — the false-positive rate on single-agent findings of this class
is high enough that acting on them without verification introduces regressions. The confidence
threshold is convergence: two or more independent reviewers flagging the same issue from different
entry points. One reviewer with high-confidence framing is not the same as convergence.

## Verify a code-reviewer's absence claims against disk

`coordinator:code-reviewer` runs with Bash confined to the sidecar-scaffold command — it cannot
run `find`/`git`/`ls` to enumerate the tree. Its "no tests exist" / "file absent" findings are
guesses at plausible paths, and false-positive the moment the real file has a different name.
Independently confirm any absence-based finding on disk before treating a `BLOCKED` verdict built
on it as real.

## Reviewer self-persists; the EM reads the returned path — no transcription

`coordinator:code-reviewer` self-persists by default: it writes findings to its pre-provisioned
sidecar at `state/subagent-share/<session>/<provision_key>.md`, edits the `<!-- FINDINGS -->`
sentinel, applies every finding, writes the `## Findings Ledger`, runs `verify`, and returns:

```
DONE: <sidecar-path> | verdict: <OK|WARN|BLOCKED> | findings: <N> | executed: <yes|no>
```

Persona reviewers (the Staff Engineer, the Game Dev Reviewer, the Data Science Reviewer, the Front-End Reviewer, the UX Reviewer, the Director of Engineering) are dual-use (advisory OR sidecar-review)
and follow the same pattern when dispatched for a review: the invoking skill injects the
pre-provisioned sidecar path, and the persona writes its findings and ledger there. No EM
transcription, ever — inline-relayed findings are never a valid handoff format; the ledger's
`verify` step hard-stops loud when the sidecar is a trivial/unfilled scaffold.

## Revertability

A single finding reverts through `reject`. A whole review reverts through the EM's single scoped
commit. Nothing about the record lives in the reviewed artifact.
