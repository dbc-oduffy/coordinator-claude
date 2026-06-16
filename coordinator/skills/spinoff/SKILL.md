---
name: spinoff
description: PM-GATED. Fork a mid-session topic into its own pickup-able handoff (a spinoff). Never EM-initiated.
allowed-tools: ["Read", "Write", "Bash", "Grep", "Glob"]
argument-hint: "<slug> [optional one-line title]"
---

# Spinoff — Fork a Workstream Into Its Own Handoff

A **spinoff** is a handoff written mid-session by the current EM, addressed to a *future* picking-up EM, describing a workstream the current session does NOT intend to execute. Synonyms used in older artifacts: "orphan-promotion handoff," "ersatz-handoff." `spinoff` is the canonical term.

## Step 0 — PM-authorization gate (hard requirement)

**Spinoffs require explicit PM authorization. The EM never initiates a spinoff on its own judgment.** If the PM has not typed `/spinoff`, named the skill, or explicitly said "spinoff this" / "make a spinoff for X" / one of the trigger phrases below for *this specific topic*, STOP. Do not write a spinoff file.

Topic drift counts: an earlier "spinoff that auth thing" does NOT authorize a later spinoff of "the migration cleanup." Each spinoff is its own authorization.

**Paraphrase is not authorization.** A statement of *eventual intent* — "another session will do this," "we should spin that off sometime," "that's really its own workstream," "someone should pick that up" — is the EM observing that a spinoff *might* be warranted. It is NOT the PM invoking the spinoff primitive. The authorizing speech act is the literal trigger: `/spinoff`, the skill name, or one of the trigger phrases below, directed at *this specific topic now*. When you find yourself inferring authorization from intent-shaped prose rather than a literal trigger, STOP and surface the candidate (one-line proposal, below) — do not promote your read of the PM's intent into a write.

If the EM identifies a candidate workstream that *would* warrant a spinoff but the PM has not authorized one, surface it as a one-line proposal — "Candidate spinoff: <slug> — <one-line topic>. Authorize?" — and wait. Do not proceed past Step 0 until the PM says yes.

Autonomous skills that previously auto-spinoffed (e.g. `/bug-blitz` Phase 2.1) MUST surface the candidate list and obtain PM authorization before writing any spinoff file. The skill body following Step 0 only runs after authorization.

**When to use this vs. its neighbors:**

- Use `/handoff` when ending the *current* session's *current* work — predecessor links to whatever you're continuing.
- Use `/spinoff` mid-session when a topic comes up that deserves its own session and you don't want to context-switch into it now. The current session keeps its own work; the fork lives at `state/handoffs/` for someone else (or future-you) to pick up.
- Use the improvement queue (one-line entry) for half-formed ideas. A spinoff is the same level of detail as a real handoff: load-bearing context, references, acceptance criteria, anti-scope.

## Trigger phrases

"spinoff", "make a spinoff for X", "ersatz handoff", "orphan handoff", "fork off this workstream", "make a handoff for someone else", "carve out X into its own pickup", "split this off as a spinoff."

## Workflow

### Step 1: Capture the slug and title

The PM gives you `$ARGUMENTS` of shape `<slug> [optional title]`. The slug becomes part of the filename; the title is the H1 of the handoff body. If only a slug was provided, ask the PM for a one-line title before writing.

### Step 2: Author the body

**Do NOT add interactive AskUserQuestion ceremony.** The EM (you) writes the body from current session context. The PM has just told you what the spinoff covers; you have everything you need. A skill that auto-fills the body from heuristics will produce shallow spinoffs the picking-up EM can't act on.

Path: `state/handoffs/{YYYY-MM-DD}_{HHMMSS}_{slug}.md`

Frontmatter (all fields literal — do not paraphrase keys):

```yaml
---
title: <one-line title>
created: <YYYY-MM-DD>
branch: <current branch — git symbolic-ref>
status: active
kind: spinoff                       # or spinoff-roadmap (Phase 5 roadmap stubs only;
                                    # see skills/roadmap-planning for that path)
predecessor: none
authoring_session: <one-line description of the session that wrote this>
workstream: <slug>
category: <roadmap|infra|bug|docs|research|refactor>
                                    # category ∈ {roadmap|infra|bug|docs|research|refactor};
                                    # summary ≤120 chars, one-line tl;dr
summary: "<one-line tl;dr>"        # ≤120 chars. Required on handoffs created ≥ 2026-05-29.
deployment_state: ready_to_fire     # default — spinoffs are authored to be picked up cold.
                                    # Override to awaiting_gate ONLY if the spinoff depends
                                    # on another spinoff/handoff shipping first; in that
                                    # case set gate_dependency: <other-handoff-filename>.
pickup_ready: true                  # DEFAULT ON for spinoffs — positive pickup-authorized
                                    # signal. Absence triggers a non-blocking warning at
                                    # /pickup time. Spinoffs are orphan-promotions by design
                                    # and are always explicitly authorized for pickup.
scope:
  - <pathspec 1>
  - <pathspec 2>
---
```

`status: active` (ready for pickup). `pickup_ready: true` always — positive pickup-authorized signal; absence triggers a non-blocking warning at `/pickup`. `predecessor: none` always — spinoffs have no continuity ancestor. `authoring_session` replaces the predecessor link as the audit trail back to origin. `workstream` lets `/workday-start` and `/pickup` group related forks. `deployment_state: ready_to_fire` makes the spinoff visible to query-driven `/workstream-start` and `/workday-start` surfaces.

Body sections (adapted from the regular handoff template):

- `# <title>` (H1 mirrors frontmatter title)
- Opening paragraph: one sentence on **why this exists as its own session** — what triggered the fork, why it deserves separation from the current work.
- `## What this covers` — origin context. Plain English on the topic, who's affected, what surface is in play.
- `## Reference materials (read first)` — file paths the picking-up EM will need, each with a one-line "what's in it" annotation. Include any session-context artifacts (plan paths, scout outputs) that aren't obvious from a fresh `git log`.
- `## Specification` — the actual work spec. Be concrete enough that a context-less EM can act.
- `## Acceptance criteria` — checklist a picking-up EM gates completion against.
- `## Recommended next steps for the picking-up EM` — 3-7 numbered, each verifiable.
- `## Anti-scope` — failure modes a context-less EM might hit. Negative scope.
- (Optional) `## Out of scope` — adjacent work explicitly NOT included.

**Related-chain discovery (optional, run while authoring the body).** Before writing `## Reference materials`, query for completion records in the same chain so the picking-up EM has concrete prior-work context:

```bash
"$HOME/.claude/plugins/coordinator/bin/query-records.sh" --type completion --where "chain~<topic-slug>"
```

Replace `<topic-slug>` with the spinoff's `workstream` slug. If the query returns matches, surface the most relevant entries as a `### Prior completed work in this chain` subsection under `## Reference materials` — one line per entry with its date and summary. This is optional: if the query returns zero rows, omit the subsection (no zero-row rendering required here; the absence is informative). The `predecessor: none` frontmatter rule is unchanged — body-level citation of related chains is orientation aid only, not lineage.

End the file with a single-line HTML comment marker for greppability:

```html
<!-- spinoff: <YYYY-MM-DD> by current EM during <authoring_session> -->
```

### Step 3: Mark in the source session

Append one line to your session task tracker (or session memory if no tracker exists) noting:

```
spinoff written: <path> — do NOT pick this up in current session.
```

This prevents the current EM from accidentally absorbing the work back into the active session.

### Step 4: Commit

Plain-git scoped commit — do NOT use coordinator-safe-commit here (SC-DR-008, lessons.md:43, lessons.md:207). Extract scope paths from handoff frontmatter; the handoff file itself is always included since it was just written.

```bash
HANDOFF=<handoff-path>
# Extract scope paths from YAML frontmatter (  - <path> lines under scope: key)
SCOPE=$(awk '/^scope:/{found=1; next} found && /^  - /{print substr($0, 5)} found && /^[a-z]/{exit}' "$HANDOFF")
if [ -z "$SCOPE" ]; then
  echo "FAIL: handoff frontmatter scope: block missing or empty — cannot enumerate paths" >&2
  exit 1
fi
# Include the handoff file itself alongside the declared scope
git add -- $SCOPE "$HANDOFF" && git commit -m "chore(spinoff): <slug> [authored mid-session]" -- $SCOPE "$HANDOFF"
```

The auto-push hook handles propagation.

*(The block below is the universal mandatory-commit-shape reminder; for spinoff Step 4 specifically, the plain-git form above is the expected path — coordinator-safe-commit is for handoff-scoped sessions, not spinoff-write.)*

<!-- mandatory-commit-shape -->
**Mandatory commit shape (concurrent-EM safe).** Plain explicit-path git is the default per SC-DR-008; the helper is reserved for sweep ceremonies + the executor's branch-pin path. Use ONE of:

```bash
# Default — explicit-path commit (SC-DR-008 baseline):
git add -- <paths> && git commit -m "<subject>" -- <paths>

# OR, for handoff-scoped sessions, the helper (defaults to em-only as of 2026-06-15):
coordinator-safe-commit --scope-from <handoff> "<subject>"
```

Plain-git is listed first deliberately — the helper is the carve-out, not the primary path. **Never `git add -A` / `git add .` / `git add --all`** — the `block-blanket-git-add.sh` PreToolUse hook enforces this; see `docs/wiki/coordinator-tripwires.md § BLOCK-BLANKET-GIT-ADD` and `docs/wiki/scoped-safety-commits.md § SC-DR-014`.

### Step 5: Surface to PM

Print one line:

```
Spinoff written: <path> — workstream: <slug>. Pick up with /pickup <filename> from any session.
```

Then return to the work the current session was doing **before** the fork. A spinoff is a fork, not a context switch.

## Anti-scope

- **`reviewed_at_workstream_complete:` does NOT apply to spinoffs.** Spinoffs are forks authored mid-session, not continuations of a session's own work — the workstream-complete review marker tracks what the *current* EM reviewed before handing off a workstream they were executing. A spinoff has no executed diff to review; it is a brief for someone else's future session. Do not add `reviewed_at_workstream_complete:` to spinoff frontmatter. (Field is defined in `schemas/handoff.yaml` as optional for the handoff kind but semantically meaningless on `kind: spinoff` and `kind: spinoff-roadmap`.)
- **Don't bake content generation into this skill.** No heuristic templates that fill `## Specification` from the slug. The body is the value — the skill provides the shape, the EM provides the content.
- **Don't auto-delete or auto-merge spinoffs that get picked up.** Spinoffs follow the standard handoff lifecycle on consumption: `/pickup` mutates frontmatter in place, then the picking-up session's `/handoff` (chain-archival) or `/workstream-complete` Step 2.7 moves the file to `archive/handoffs/`. The `<!-- consumed: -->` marker is deprecated — do not write it.
- **Don't extend `kind:` to other values speculatively.** Three values are now authorized — `session-handoff`, `spinoff`, `spinoff-roadmap`. The third (`spinoff-roadmap`) was added 2026-05-08 after the recurring-shape threshold was met: the project-rag cross-deep-dive-synthesis episode (see `archive/specs/2026-05-08-roadmap-planning-skill-brief.md` § "Weaknesses and gaps #2") was instance #3 of stubs ending up *adjacent to* spinoffs rather than *as* spinoffs. Further extension still requires a documented recurring shape, not speculation.
- **Don't replace `/handoff` with `/spinoff`.** They serve different needs. The writer-of-spinoff still ends their own session with `/handoff`.
- **Don't migrate prior orphan-promotion handoffs.** Their lifecycle is over; renaming retroactively is churn. New spinoffs use the `kind:` field; old ones stay as-is.

## See also

- `docs/wiki/cross-repo-communication.md` — decision tree for handoff vs spinoff vs cross-repo messaging; codifies PM-as-relay as the cross-repo primitive (NOT a spinoff to the other repo).
- `commands/handoff.md` — end-of-session continuation handoffs.
- `commands/pickup.md` — picking up a handoff (recognizes `kind: spinoff` and emits a banner).
- `CLAUDE.md` § "Handoff Lineage — Single Predecessor, No Adjacency-Inference" — doctrine on why `predecessor: none` is correct for spinoffs.
- `schemas/handoff.yaml` — frontmatter schema enumerating allowed `kind:` values.
