---
segment_id: roadmap-routing-and-sequencing
surface: roadmap
class: protected
order: 6
---

**Reviewer tier table — roadmap spine and sprint slice.**

| Situation | Correct tier |
|---|---|
| Roadmap spine, single-domain | One Opus-persona reviewer (auto-detects domain from the routing table) |
| Roadmap spine crossing a repo or team boundary | the Director of Engineering (`eng-director`) — boundary arbitration is their charter, not the generalist's |
| Sprint slice whose flavor names a domain | The domain persona by flavor, then the Staff Engineer only if the domain pass left the architectural layer untouched |
| Sprint slice already covered at spine altitude | Domain reviewer is SKIPPABLE — see the skip contract below. Record the rationale in the roadmap dir; an unrecorded skip is a gap, not a decision |
| Contested spine shape with ≥2 valid decompositions AND PM authorized | `/staff-session` review-mode |
| "Route this to `code-reviewer` instead" | **Not a valid row.** `code-reviewer` is the Sonnet diff reviewer. A roadmap artifact is reviewed by a named Opus persona or not at all. |

**The skip contract — both conditions, never one.** A domain reviewer is skippable at
sprint altitude ONLY when (a) their spine-altitude findings are pinned into the stub ACs
*verbatim*, not paraphrased, AND (b) each stub becomes a downstream `coordinator:plan`
that re-applies the same lens at PLAN altitude. Either condition alone leaves the lens
unapplied at every altitude — the failure this contract exists to refuse. Record the
rationale in the roadmap dir at skip time; a skip reconstructed later is not evidence.

**Altitude rule.** A roadmap review reads the DECOMPOSITION, never the implementation.
Findings about how a stub will be built belong to that stub's own plan review, and a
reviewer who returns them at this altitude has reviewed the wrong artifact — route them
downstream rather than integrating them here. The reciprocal also binds: a plan-altitude
review does not re-litigate which clusters became stubs.

**Sequencing (HARD RULE):**
- Default → sequential. Integrate Reviewer 1's findings via `coordinator:review-integrator`
  BEFORE dispatching Reviewer 2. Roadmap artifacts are never parallelized; the
  merge-gate parallel carve-out is diff-only.
- **Two PM rounds bracket the reviewers, and they are not interchangeable.** Round 1 is
  shape approval and runs BEFORE any reviewer (`status: shape-approved`). Round 2 is final
  approval and carries a diff against the shape-approved body (`status: final-approved`).
  The next phase MUST NOT start without round 2.
- A reviewer dispatched before round 1 reviews a shape the PM has not accepted, and their
  findings are spent on an artifact about to change underneath them.

_See `coordinator/snippets/em-operating-doctrine.md` § How to Dispatch — `/staff-session`
is PM-gated; ask first._
