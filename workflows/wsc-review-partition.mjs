/*
 * wsc-review-partition — background-Workflow encoding of `/workstream-complete`'s partitioned
 * review: N reviewer phases, N 1:1 integrator phases, pipelined per slice with no barrier
 * between a slice's own two phases.
 *
 * Spec backlink: docs/plans/2026-08-18-fire-the-review-partition-as-a-workflow.md, chunk C2.
 * This script is the fired dispatch vehicle the plan's Problem section argues for — it closes
 * the vehicle objection (`review-dispatch-vehicle-choice` in
 * coordinator/skills/workstream-complete/SKILL.md) by consuming a pre-provisioned catering
 * payload rather than relying on the `Agent`-tool `PreToolUse` hook, which never fires on a
 * Workflow-spawned dispatch. Sibling to `review-wave.mjs` in this same directory, following its
 * header conventions (module docstring with spec backlink, explicit args contract,
 * negative-spec block, a worked invocation example) — see that file's own docstring for the
 * shape this one repeats.
 *
 * Negative-spec: this script COMPOSES PROMPTS ONLY. It resolves nothing, provisions nothing,
 * and freezes nothing — every path and every prose block it uses arrives pre-built in `args`.
 * It is NOT a fork of `review-wave.mjs` (that script encodes a different gate, the
 * `/workweek-complete` merge review of chunk reviewers + mechanical specialists + a
 * synthesizer); this script is a sibling encoding a different contract, the 1:1
 * reviewer-then-integrator close review. It does NOT collapse the 1:1 integrator into a
 * union-integrator, does NOT give a reviewer phase a `schema:` (a review phase returns the
 * `DONE: <path> | verdict | findings: N` pointer string and persists to its own sidecar;
 * `review-integrator`'s intake hard-stops on inline findings), and does NOT declare a
 * `depends_on: C1` edge on its own plan row — the coupling to the composer that builds this
 * script's `args` is a pinned interface asserted by each chunk's own test, not a spine gate.
 *
 * args contract — the exact key set below, no other top-level or per-role key:
 *   {
 *     slices: [
 *       {
 *         id: string,             // slice id, e.g. "slice-1" — used to keep a slice's own
 *                                   // reviewer and integrator dispatches grouped together and
 *                                   // to keep N concurrent same-type dispatches distinguishable
 *         diffPath: string,       // the frozen diff path for this slice
 *         shaRange: string,       // the range that diff was frozen from; the reviewer attests it
 *                                   // into its sidecar's `reviewed_range`, which IS the binding --
 *                                   // review_trail.write was gravestoned at K-060, so there is no
 *                                   // trail record and no `trailRecord` key
 *         reviewer: {
 *           sidecarPath: string,  // pre-provisioned run-report sidecar for this slice's reviewer
 *           contractBlocks: string, // fully assembled catering prose (resolved role framing +
 *                                     // contract-block content), appended verbatim
 *         },
 *         integrator: {
 *           sidecarPath: string,  // pre-provisioned run-report sidecar for this slice's integrator
 *           contractBlocks: string, // fully assembled catering prose for the integrator phase
 *         },
 *       },
 *     ],
 *   }
 *
 * Invocation:
 *   Workflow({
 *     scriptPath: "coordinator/workflows/wsc-review-partition.mjs",
 *     args: {
 *       slices: [
 *         {
 *           id: "slice-1",
 *           diffPath: "state/review-trail/diffs/wsc-20260818-slice-1.diff",
 *           reviewer: {
 *             sidecarPath: "state/subagent-share/<session-id>/wsc-20260818.slice-1.reviewer.md",
 *             contractBlocks: "...assembled prose...",
 *           },
 *           integrator: {
 *             sidecarPath: "state/subagent-share/<session-id>/wsc-20260818.slice-1.integrator.md",
 *             contractBlocks: "...assembled prose...",
 *           },
 *         },
 *       ],
 *     },
 *   })
 *
 * Returns: one result object per slice — { id, integratorResult } — `integratorResult` is the
 * integrator dispatch's own returned text (`pipeline()` returns only each item's final-stage
 * result; the reviewer stage's `DONE: ...` pointer is threaded into the integrator prompt as
 * `prevResult` rather than surfaced separately in the return value).
 */

export const meta = {
  name: 'wsc-review-partition',
  description: 'Partitioned close review — N reviewer dispatches, N 1:1 integrator dispatches, each slice pipelined with no barrier between its own two phases.',
  phases: [
    { title: 'Review', detail: 'A coordinator:code-reviewer instance per slice, reading that slice\'s frozen diff and persisting findings to its own pre-provisioned sidecar.' },
    { title: 'Integrate', detail: 'A coordinator:review-integrator instance per slice, applying or explicitly rejecting that slice\'s reviewer findings — 1:1 with the reviewer above, starting the moment that slice\'s review finishes rather than waiting on every slice\'s review.' },
    { title: 'Trail', detail: "One review-trail write per commit in that slice's range, run while the firing session is still alive — the only window in which its reviewer dispatch is attestable." },
  ],
}

// Order pinned by C2's own spec: dispatch framing, the frozen diff path, a literal
// `sidecar_path:` marker on its own newline-preceded line (the exact marker
// coordinator/agents/code-reviewer.md keys off), then contractBlocks appended verbatim.
function reviewerPrompt(slice) {
  return [
    'You are the coordinator:code-reviewer instance dispatched as part of a wsc-review-partition Workflow.',
    'Assigned slice: ' + slice.id,
    'Frozen diff path (read this in full before any working-tree reading): ' + slice.diffPath,
    'Sha range this diff was frozen from: ' + slice.shaRange,
    '',
    'Before you finish, write that range into your sidecar frontmatter as `reviewed_range` --',
    'a list with that one entry. You are the only party permitted to write that field: not the',
    'EM, not a closing session, not a successor. review_trail.write admits a trail record only',
    'against a range attested here, so a sidecar that omits it produces a review that can never',
    'be recorded, no matter who tries later or how.',
    '',
    'sidecar_path: ' + slice.reviewer.sidecarPath,
    '',
    slice.reviewer.contractBlocks,
  ].join('\n')
}

// Same marker convention as the reviewer prompt above; carries the reviewer's own return text
// (its `DONE: ...` pointer) so the integrator knows where the review dispatch above landed
// before it opens the sidecar itself.
function integratorPrompt(slice, reviewerReturn) {
  return [
    'You are the coordinator:review-integrator instance dispatched as part of a wsc-review-partition Workflow.',
    'Assigned slice: ' + slice.id,
    'Reviewer findings sidecar for this slice (read findings from here, never inline): ' + slice.reviewer.sidecarPath,
    'That reviewer dispatch returned: ' + (reviewerReturn || '(no return text)'),
    'Target artifact — the frozen diff this slice reviewed: ' + slice.diffPath,
    '',
    'sidecar_path: ' + slice.integrator.sidecarPath,
    '',
    'YOUR DELIVERABLE IS THE SIDECAR ABOVE, NOT THIS REPLY. Write your per-finding',
    'disposition table — applied / explicitly rejected with reasoning — into that file',
    'BEFORE you return, and reply only with a short pointer to it. A disposition that',
    'exists solely in your return text is not recorded: the return value is discarded',
    'once the wave completes, and the close reads the sidecar. Measured: a fired wave',
    'where every integrator reported a complete triage inline and left its sidecar as',
    'the blank starter template reads on disk as zero findings integrated, which is',
    'indistinguishable from the integrator never having run.',
    '',
    'Applied or explicitly rejected are the two dispositions that discharge a finding.',
    'Deferred and escalated do not — if you use them, name in the sidecar who owns the',
    'item and what unblocks it, or you have moved the finding rather than dispositioned it.',
    '',
    slice.integrator.contractBlocks,
  ].join('\n')
}

const parsedArgs = (typeof args === 'string') ? JSON.parse(args) : args
if (!parsedArgs || typeof parsedArgs !== 'object') {
  // A caller whose composer step died hands us null. Unguarded, that surfaces
  // as a null dereference on the next line and reads as a defect in the review
  // partition -- when in fact the partition never ran. Name it instead.
  throw new Error(
    'wsc-review-partition received no args object (got ' + String(parsedArgs) + '). ' +
    'The caller composes this payload with coordinator/bin/compose-review-wave.py; ' +
    'a null here means that step failed, not that the partition failed.'
  )
}
const slices = Array.isArray(parsedArgs.slices) ? parsedArgs.slices : JSON.parse(parsedArgs.slices)

// Reviewer stage: NO schema — a review dispatch returns the DONE pointer string and persists
// its findings body to disk; review-integrator's intake hard-stops on inline findings, so an
// inline-return mechanism here would be actively harmful, not merely redundant.
async function reviewStage(prevResult, slice, index) {
  return await agent(reviewerPrompt(slice), {
    agentType: 'coordinator:code-reviewer',
    model: 'sonnet',
    phase: 'slice:' + slice.id,
    label: 'reviewer:' + slice.id,
  })
}

// Integrator stage: 1:1 with the reviewer stage above, receiving the same slice as
// `originalItem` — pipeline hands each stage exactly one item, so this is structurally a
// one-reviewer-to-one-integrator dispatch, never a union across slices.
async function integrateStage(prevResult, slice, index) {
  return await agent(integratorPrompt(slice, prevResult), {
    agentType: 'coordinator:review-integrator',
    model: 'sonnet',
    phase: 'slice:' + slice.id,
    label: 'integrator:' + slice.id,
  })
}

// NEGATIVE SPEC -- there is no trail stage, and adding one back is a regression.
// `review_trail.write` and `coordinator-write-review-trail` are a K-060 gravestone
// (DR-372/DR-374). The replacement is the `review_receipt:` block the dispatched reviewer
// stamps into its own sidecar, which `gates.review_receipt` reads: dispatching the reviewer
// IS recording the review, and nobody writes a trail record. The op id still dials, so a
// re-added stage would not fail loudly -- it would collect refusals and report them as an
// unrecordable partition.

// pipeline(), not parallel() barriers: a slice's integrator dispatch starts the moment
// that slice's reviewer dispatch finishes, so a fast slice never idles behind the slowest
// reviewer, and there is no cross-slice context an integrator needs before starting. The
// trail stage rides the same per-slice chain for the same reason.
const sliceResults = await pipeline(slices, reviewStage, integrateStage)

log('wsc-review-partition complete: slices=' + slices.length)

// pipeline() returns results index-stable to its input `slices` array, not in
// completion order, even though each slice's stages run independently and can
// finish out of order -- so `sliceResults[index]` below always lines up with
// `slices[index]`. pipeline() surfaces only each item's FINAL stage, which is
// the integrator; its own deliverable is its sidecar on disk, which is where
// the close reads it from and always was.
return slices.map((slice, index) => ({
  id: slice.id,
  integrateResult: sliceResults[index],
}))
