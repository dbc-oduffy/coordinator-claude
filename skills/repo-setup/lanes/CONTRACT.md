---
purpose: >
  Types the three repo-setup lane files (`new-project.yaml`, `add-existing-project.yaml`,
  `add-repo.yaml`) so a caller — human or button — can fire `repo-setup-assemble` unattended
  with every `round_trip` judgment point pre-answered.
census_backlink: "state/plan-sidecars/2026-08-20-repo-setup-computed-form.census-steps.md"
contract_version: "1.0.0"
---

# repo-setup lane contract

## What a lane is, and is not

A lane is a **pre-answered round-trip set**, not a preset. Presetting only the easy judgment
points and leaving a `round_trip` point to be prompted diverges silently from the interactive
path in exactly the cases nobody tests — see the tripwire
`coordinator/docs/wiki/coordinator-tripwires/a-lane-is-not-a-preset.md` (C8). Every lane file in
this directory MUST answer all six `round_trip` census rows, land each as a tier-1 `directives[]`
entry (never a tier-2 `judgment_points[]` entry carrying only a `recommendation` — an unattended
consumer halts on any `judgment_points` entry regardless of a recommendation), and declare a
policy default for every terminal offer not on the second-phase deferral list.

## The three lanes

| Lane | File | Basis |
|---|---|---|
| **new-project** | `new-project.yaml` | Greenfield. No existing code. Caller supplies name + goal statement; classification answer is `working`. |
| **add-existing-project** | `add-existing-project.yaml` | A repo built without coordinator. Classification answer is `working`; Phase 1.5 substrate synthesis is accepted (`ratify`) without a confirmation round-trip. |
| **add-repo** | `add-repo.yaml` | The thin door. Classification answer is `published-artifact` (b), which `p1.classification-branch-b-stop` halts on — Phase 1.5/2/3 are not reached. Registers the repo and stops. |

Each lane file declares a pre-answered value for every `round_trip` row, differing from every
other lane in at least one value (an identical pair collapses per plan anti-scope; verified here —
`add-repo` differs from `add-existing-project` on `p1.repo-classification-ask`,
`p3x.memo-destination-offer`, and every round_trip point downstream of the classification halt).

## The six `round_trip` judgment points (AC2)

Per the census (`round_trip_shape`), these six select which downstream mechanical steps run at
all and MUST be pre-answered as tier-1 `directives[]` in every lane file:

1. `p1.repo-classification-ask` — working / published-artifact / both. Gates whether Phase 2 runs
   at all.
2. `p15.ratification-ask` — ratify / correct / go-cold. Gates which Phase 2 questions are still
   owed.
3. `p2.ask-project-name`
4. `p2.ask-project-type`
5. `p2.ask-workstreams`
6. `tw.ci-inference-prompt` — yes / no / not now. A yes writes `cross_platform: true` and unlocks
   the CI offer.

## Terminal offers requiring a lane policy default

The census's terminal (non-`round_trip`) JUDGMENT/MIXED-judgment-half rows number 17. Nine of
those are the AGENT-WORK STEPS below, deferred to the second phase — not policy-defaulted by a
lane. The remaining **eight** are terminal offers a lane MUST still declare a policy default for,
since a lane that leaves them unaddressed cannot fire unattended:

- `p15.propose-workstreams`
- `p3d5.hand-section-prompt`
- `p3f.untrack-scratch-offer`
- `p3f5.custom-hook-skip`
- `p3l.curation-prompt`
- `p3x.memo-destination-offer`
- `tw.windows-console-offer`
- `tw.ci-offer`

## Nine agent-work steps deferred to the second phase

These carry a genuine semantic read (README prose synthesis, per-site tagging, a per-repo
tree-shape call) that no policy default can safely stand in for. A lane names them as deferred,
not pre-answered — the second phase (out of this plan's scope; the roster names skills that cover
some of this ground, C3) is where they resolve, with a human or a scout dispatch in the loop:

`p15.substrate-read`, `p15.propose-project-type`, `p15.peer-repo-candidate-extraction`,
`tw.spawn-gate-exclude-set`, `tw.spawn-gate-ratchet-init`, `tw.spawn-gate-run-and-burndown`,
`p15.peer-scout-dispatch-offer`, `tw.windows-console-allowlist-customize`,
`tw.windows-console-suppression-tagging`.

## UNATTENDED-HALT SET (AC2b)

Four census steps run a command string or hook sourced from the target repo. Under a
button-spawned, no-human consumer these become tier-1 directives executed against
attacker-influenceable content with full agent-Bash blast radius, so
probe-confirmation is JUDGMENT and an autonomous consumer halts rather than executing it. Every lane in this
directory MUST leave these four **unresolved and returned** to the calling agent (the same
disposition shape as AC4's `repair`/`update`), never pre-answered as tier-1:

- `p3j.1-test-cmd-detect` — detects a test command the target repo defines.
- `p3m.verify-reachability` — RUNS the detected/configured test command.
- `tw.windows-console-verify-run` — runs a copied test from the target repo.
- `batch.hook-respect` — runs the target repo's own git hooks with no `--no-verify`.

A lane file that pre-answers any of these four, at any tier, is a contract defect (see C6's seam
test).

## Id-joinability hedge (AC11, § Assumption this plan is drafted against)

The lane contract pre-answers by census `step_id`; the engine op (`repo-setup-assemble`)
resolves by `judgment_points[].id`. No corpus rule equates the two identifiers today (C1 asks the
engine side to state the basis). Each lane file's `round_trip_directives[]` and
`terminal_offer_defaults[]` entries therefore carry BOTH:

- `step_id` — the census identifier, stable and joinable against
  `state/plan-sidecars/2026-08-20-repo-setup-computed-form.census-steps.md`.
- `engine_judgment_point_id` — placeholder, `null` until the engine side's answer to C1 fixes the
  resolution shape. A later contract shape-change is then a mechanical remap of this one field,
  not a re-authoring of the lane files.

A `round_trip_directives[].value` reading `"not reached (...)"` is a recognized sentinel, not a
typed answer — it marks a directive inert because the lane's classification halts before that
point is ever evaluated (`add-repo.yaml`'s post-classification-halt entries). A mechanical
consumer joining `value` across lane files treats any string matching this prefix as "inert,
no answer to join," never as the point's real pre-answered value.

## Roster slots — an ordering convention, not `orient_after:`

A lane names its second-phase roster as an ordered list of `ready_to_fire` **slots**, reusing the
bare baton shape `kind: spinoff` + `deployment_state: ready_to_fire` + `pickup_ready: true` +
`scope:` (generic `ready_to_fire` triage
via `/workday-start`). This chunk writes no baton, handoff, or spinoff — `roster_slots:` is data
naming the primitive, not an instance of it.

`orient_after:`'s value domain is scoped to a sibling install leg's `repo:` id or the sentinel
`leaf` — it carries no same-repo roster-sequencing meaning, and
is explicitly NOT reused here (plan anti-scope). Instead, ordering is:

Enforced by `coordinator/tests/test_repo_setup_assemble_delivery_seam.py` —
`test_every_lane_roster_is_contiguously_slotted_and_self_consistent`. The convention is not prose:
a gap, a repeat, or a `pickup_ready_condition` disagreeing with its slot fails there.

- Each `roster_slots[]` entry carries an integer `slot` (1-based), fixing fire order within THIS
  lane's roster only.
- `pickup_ready_condition` is `"immediate"` for `slot: 1`, or `"after: <N>"` for `slot: N+1` and
  above.
- At roster materialization time (a later chunk's job, out of this plan's scope — C2 names the
  slot shape, C3 fills brownfield's contents), the batons the roster names are written
  `pickup_ready: true` only for the lowest-numbered slot whose predecessors are archived; every
  higher slot's baton starts `pickup_ready: false`. This is ordinary baton data
  (`pickup_ready` plus the slot number recorded in the baton's own body), never a widened
  `orient_after:`.
- Greenfield's terminal slot names `coordinator:goal-setting` plus the roadmap ceremony as it
  stands at execution time (§ Cross-plan coordination in the plan body — the ceremony's
  post-split shape is a live sibling plan's concern, not pinned here). Brownfield's roster is
  seeded by C3's panel output, not authored in this chunk.

## Completeness verdict (AC3)

The verdict includes registry state. A repo carrying the full directory shape but no
`repos.<key>` entry in the machine-local registry resolves `incomplete`, never `onboarded` — no
sibling EM can address a repo the registry does not name, so the directory shape alone does not
make it onboarded. Only a fully-registered verdict lets a consuming product suppress its onboard
button.

`~/.claude/working-repos.yaml` is not a verdict input. It is `--batch`'s input candidate list, not
a completion ledger, and a repo onboarded via `--root` or interactively legitimately never appears
in it. A lane may touch it as a side effect of the run it drove; that side effect stays out of the
verdict.

Engine-side to implement (C1), like AC4 below.

## Already-onboarded no-op (AC4)

Every lane, run against an already-onboarded repo, exits 0 with an `already-onboarded` verdict.
A genuine conflict (our systems evolve) surfaces as a `repair` or `update` disposition in the
returned object — never a failure, never a prompt. This is the engine's contract to implement
(C1); the lane files below name no special-case behavior for it, since the verdict precedes lane
dispatch.
