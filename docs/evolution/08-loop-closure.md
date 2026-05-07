# 08 — Loop-closure

> Recording isn't learning. Capture without a consumer is decoration. The case for this system isn't a brainwave; it's the rigor that falls out of running an EM-PM pairing seriously.

## Recording is easy. Learning is hard.

A lot of agent infrastructure invests heavily in *recording* what happened. Session memories, activity rolls, rolling daily/weekly summaries, lightweight memory plugins. The pitch is always some version of "your agent will remember." It's appealing. It's also mostly the easy half of the problem.

We had better work-tracking than recording-focused plugins offer before any of that landed: handoffs as the atom of session continuity, commit-as-habit (auto-push on every workstream commit, daily-branch discipline), structured plan documents on disk. Plans, handoffs, and `git log -p` are higher-fidelity records of what a session actually did than any agent-summarized memory file. We tried memory-recording add-ons — including a `remember` plugin that summarized session activity into rolling daily/weekly files — and removed them. They duplicated the work the handoff/commit/plan pipeline already did, at worse fidelity, and added their own staleness and Windows-path-quirk failure modes. More hassle than they were worth.

The hard half of the problem isn't capture. It's making the captured material *change a future decision*. That's where lessons.md belonged, and where it spent most of its life failing.

## The lessons.md fraud-of-promise

`tasks/lessons.md` came from inspiration. Other agent systems pitched some version of "the agent will never make the same mistake twice" via a lessons file. The framing was seductive. We adopted it.

The promise didn't hold water. Dumping observations into an ever-growing file doesn't mean the lessons are *learned*. A learned lesson is one that changes a future decision. An entry in lessons.md only changes a future decision if some downstream process reads it and acts on it. Without that, the file is a write-only buffer with a friendly name.

For a long stretch we used lessons.md as two malformed substitutes:

- **As short-term memory.** A session would dump its observations and the next session would skim them, hoping something stuck. The hope was usually wrong. Lessons aged out of context faster than they aged out of relevance.
- **As a forced session-start reading habit.** Read lessons before starting work. The reading happened; the *relevance* didn't. The EM read entries that could be about anything, hoping today's work happened to overlap with what last week's work captured. It rarely did, and even when it did, the reader was the wrong person at the wrong time — orientation phase, not planning phase.

Neither posture felt right. We knew it. We kept iterating on `lessons-trim` — consolidating overlap, pruning dead entries, retagging — knowing we were making a flawed system less bad rather than fixing the frame. The frame was the problem. Trim doesn't fix a write-only buffer; it just makes the buffer smaller.

## /distill built wikis. Wikis weren't enough either.

Meanwhile the `/distill` pipeline was running. It extracted plans, handoffs, and research outputs into evergreen wiki pages — `docs/wiki/` — and a parallel decision-records directory. Real value: structured artifacts replaced sprawling work-in-progress directories, and the wiki was searchable.

Wikis were useful as **grep bait**. The EM searches for a term, finds a wiki, reads the wiki, has the context. We invest in this deliberately — it's why naming, frontmatter, and structural cross-references matter. The architecture.md piece on "grep bait" is the same idea.

But two gaps:

- **Wikis biased toward what was chosen and why.** A wiki page for a shipped pattern records the cleaned-up retrospective: *here is the convention, here is the rationale*. That's load-bearing. What it under-captured was the *scar tissue* — the days we spent failing to get something to work, the patterns we now know to avoid because we tried and they bit us. Hard-won lessons live in `tasks/lessons.md` more than in `docs/wiki/`. The two surfaces weren't talking.
- **Wikis weren't getting involved in planning.** The grep-when-curious surface is different from the read-before-deciding surface. A planner who didn't know a wiki existed wouldn't find it. Wikis recorded; they didn't interject.

The 2026-05-04 holodeck `.uplugin Modules` incident made this concrete. A plan was written, reviewed by the Staff Engineer (`coordinator:staff-eng`), approved. The plan reintroduced a pattern that `tasks/lessons.md` had explicitly forbidden five days earlier. Nobody read lessons.md before drafting. Nobody read lessons.md inside the Staff Engineer's review. The lesson lived on disk, current and correct, and zero downstream consumers were listening.

That was the moment the frame broke for good. Capture wasn't the problem. Routing was.

## v2.0.0: organize, then inject

The v2.0.0 reframe is two moves: **organize the material**, *and* **inject it into the processes where decisions get made**. The two moves together turn passive scar tissue into an active input. Either one alone fails — organized material with no injection point is a tidy graveyard; injection without organization is noise.

Four named consumers shipped, each closing a previously-orphaned loop:

**`/learn-lessons` — lessons as routed change-requests.** Replaces `lessons-trim`. Three modes: local (auto-fires inside `/update-docs` Phase 6, applies bounded changes in-session), central (PM-invoked from `~/.claude` at ~21-day cadence, mines lessons across all repos and promotes universal patterns to the central improvement queue), recheck (picks up deferred items from `tasks/lesson-triage-recheck-due-*.md`). The reframe: a lesson worth keeping is a *change-request* — for a doctrine paragraph, a hook, a tripwire, a wiki promotion, a queue entry. Twelve change-kinds, named targets. Lessons are no longer file-bloat; they're inputs to a routing decision.

**prior-art-checker — wikis + lessons read before plan review.** A Sonnet recall agent dispatched as a pre-flight to Opus review. Reads the plan, enumerates its claim surface, cross-references project wikis + global wikis + `tasks/lessons.md` + the central improvement queue. Writes a sidecar with three buckets: Conflicts (BLOCKED → halt the pipeline, surface to PM), Compatible-but-relevant (the Staff Engineer gets prior-art context for the review), Silent (no prior art, proceed normally). Doctrine: `plugins/coordinator/docs/wiki/prior-art-checker.md`. Born directly from the holodeck `.uplugin` incident — the lesson that lived on disk and contradicted the plan five days later.

**`/bug-blitz` — autonomous bug-backlog grinder.** Walks `tasks/bug-backlog.md` top-to-bottom, verifies each entry still applies (handoff-premise rot is real — old bugs are often already fixed or no-longer-reproducible), fixes small items in parallel waves, spins big items off to handoffs. The hard-won detail: parallel executors must NOT each call a touched-files-aware commit helper — that produces sibling-sweep absorption, empirical from the 2026-05-06 sweep. Corrected pattern is **EM-serial commits at wave gates** with plain git, after the fan-out completes.

**`/dogfood` — binary-outcome smoke loop.** New capability shipped → invoke it end-to-end → if it works, declare stable; if it breaks, fix and try again. The doctrine bullet that makes it work: **converge or switch gears, no defer**. A `/dogfood` session ending with "we'll fix the rest next time" is a `/dogfood` failure. File-and-defer is the failure mode the loop exists to prevent.

| Surface | Consumer | Where it fires |
|---------|----------|----------------|
| `tasks/lessons.md` | `/learn-lessons` (local) | `/update-docs` Phase 6 |
| Central improvement queue | `/learn-lessons` (central) | PM-invoked, ~21-day cadence |
| Wikis + lessons + queue | prior-art-checker | `/review-dispatch` Phase 2.7b, before Opus review |
| `tasks/bug-backlog.md` | `/bug-blitz` | PM-invoked; surfaced in `/session-start`, `/workday-start` |
| New capabilities | `/dogfood` | EM-invoked after first ship |

Each consumer is the answer to "who reads this?" Without that named answer, the surface is decoration.

## Active use of scar tissue

The thing this gets us, summed up: the system actively reads its own scar tissue at the moments where the scar tissue is load-bearing. Wikis are no longer just grep bait; they're a planning input via prior-art-checker. Lessons are no longer a write-only buffer; they're routed change-requests. The bug backlog is no longer a graveyard; it's a queue with a named consumer.

That phrase is worth holding onto. Most agent systems either don't capture, or capture without consumption. Capturing without consumption produces the comforting sensation of learning while not actually learning. *Active use of scar tissue* is the thing that distinguishes "we wrote it down" from "we let it change a decision."

A side-effect worth naming: over time, the accumulated wikis + lessons + decision records + this evolution series is hard-won knowledge about agentic engineering that's hard to find elsewhere. The published research is mostly about model capabilities; the operational scar tissue of running long-horizon agent work is mostly trapped in private notes. Even as training data, that material is load-bearing — it covers questions a model can't answer well from public corpora because the corpora don't have it.

## Why this lands

None of the four loops is a brainwave. They're each obvious in retrospect. So why is this the v2.0.0 thesis chapter?

Because the rigor is distinctive in the space, and the rigor isn't an accident. Most agent infrastructure trends toward "make the agent smarter and trust it more." This system trends toward "make the *process* tighter." That's a different bet. It comes organically from being structured as an **EM-PM pairing**.

When you're running a real engineering team, the loop-closure question surfaces on its own. *Why is the bug backlog growing? Why didn't the planner know about that lesson? Why are we re-litigating a decision the staff session already made?* A PM running an EM asks those questions because that's what PMs do. Adopt that pairing structure inside an agent system and the same questions surface, with the same forcing function. The discipline isn't imported from theory; it falls out of taking the role split seriously.

The case for this system isn't that any single piece is novel. It's that the role split forces the boring-but-load-bearing process work to actually get done. Loop-closure is the v2.0.0 instance of that. Plenty more is downstream.

## What hasn't changed

Capture surfaces are unchanged. Lessons still go in `tasks/lessons.md`. Bugs still go in `tasks/bug-backlog.md`. Wikis still get written by `/distill`. Plans still land in `docs/plans/` and archive when consolidated.

The change is downstream: every capture surface now has a named consumer that fires at a known cadence on a known surface. Loop-closure isn't a feature. It's a posture. The posture says: *if you can't name the consumer, don't capture the list.*
