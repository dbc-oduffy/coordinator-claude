---
purpose: >
  Types the three repo-setup lane files (`new-project.yaml`, `add-existing-project.yaml`,
  `add-repo.yaml`) so a caller — human or button — can fire `repo-setup-assemble` unattended
  with every `round_trip` judgment point pre-answered.
contract_version: "1.0.0"
---

# repo-setup lane contract

## What a lane is, and is not

A lane is a **pre-answered round-trip set**, not a preset
(`coordinator/docs/wiki/coordinator-tripwires/a-lane-is-not-a-preset.md`). Every lane file MUST
answer all five `round_trip` census rows as tier-1 `directives[]` entries (never tier-2
`judgment_points[]`, which an unattended consumer halts on) and declare a policy default for
every terminal offer not on the deferral list. Each lane differs from every other in at least one `round_trip` value (an identical pair collapses).

## The three lanes

| Lane | File | Basis |
|---|---|---|
| **new-project** | `new-project.yaml` | Greenfield. Caller supplies name + goal statement; classification answer is `working`. |
| **add-existing-project** | `add-existing-project.yaml` | A repo built without coordinator. Classification `working`; Phase 1.5 synthesis accepted (`ratify`) without a round-trip. |
| **add-repo** | `add-repo.yaml` | The thin door. Classification `published-artifact` (b), which `p1.classification-branch-b-stop` halts on — Phase 1.5/2/3 are not reached. Registers the repo and stops. |

## The five `round_trip` judgment points (AC2)

These MUST be pre-answered as tier-1 `directives[]` in every lane file:

1. `p1.repo-classification-ask` — working / published-artifact / both. Gates whether Phase 2 runs.
2. `p15.ratification-ask` — ratify / correct / go-cold. Gates which Phase 2 questions are owed.
3. `p2.ask-project-name`
4. `p2.ask-project-type`
5. `p2.ask-workstreams`

## Terminal offers requiring a lane policy default

Seven terminal offers a lane MUST declare a policy default for:

- `p15.propose-workstreams`
- `p3d5.hand-section-prompt`
- `p3f.untrack-scratch-offer`
- `p3f5.custom-hook-skip`
- `p3l.curation-prompt`
- `p3x.memo-destination-offer`
- `tw.windows-console-offer`

## Nine agent-work steps deferred to the second phase

A lane names these as deferred, not pre-answered:

`p15.substrate-read`, `p15.propose-project-type`, `p15.peer-repo-candidate-extraction`,
`tw.spawn-gate-exclude-set`, `tw.spawn-gate-ratchet-init`, `tw.spawn-gate-run-and-burndown`,
`p15.peer-scout-dispatch-offer`, `tw.windows-console-allowlist-customize`,
`tw.windows-console-suppression-tagging`.

## UNATTENDED-HALT SET (AC2b)

Four census steps run a command or hook sourced from the target repo. Every lane MUST leave
these four **unresolved and returned** to the calling agent, never pre-answered at any tier:

- `p3j.1-test-cmd-detect` — detects a test command the target repo defines.
- `p3m.verify-reachability` — RUNS the detected/configured test command.
- `tw.windows-console-verify-run` — runs a copied test from the target repo.
- `batch.hook-respect` — runs the target repo's own git hooks with no `--no-verify`.

## Id-joinability hedge (AC11)

The contract pre-answers by census `step_id`; the engine op resolves by `judgment_points[].id`.
Each lane's `round_trip_directives[]` and `terminal_offer_defaults[]` entries carry BOTH `step_id`
and `engine_judgment_point_id` (`null` until the engine side fixes the resolution shape).

A `round_trip_directives[].value` reading `"not reached (...)"` is an inert sentinel (the lane's
classification halts first): a consumer joining `value` across lanes treats it as no answer.

## Roster slots — an ordering convention, not `orient_after:`

A lane names its second-phase roster as ordered `ready_to_fire` **slots** (bare baton shape
`kind: spinoff` + `deployment_state: ready_to_fire` + `pickup_ready: true` + `scope:`);
`roster_slots:` is data, this contract writes no baton. `orient_after:` is NOT reused.

Enforced by `coordinator/tests/test_repo_setup_assemble_delivery_seam.py` —
`test_every_lane_roster_is_contiguously_slotted_and_self_consistent`: a gap, a repeat, or a
`pickup_ready_condition` disagreeing with its slot fails there.

- Each `roster_slots[]` entry carries an integer `slot` (1-based), fixing fire order within THIS
  lane's roster only.
- `pickup_ready_condition` is `"immediate"` for `slot: 1`, or `"after: <N>"` for `slot: N+1` and
  above.
- Greenfield's terminal slot names `coordinator:goal-setting` plus the roadmap ceremony.
- At materialization, only the lowest-numbered slot whose predecessors are archived gets
  `pickup_ready: true`; higher slots start `false`.

## Completeness verdict (AC3)

A repo with the full directory shape but no `repos.<key>` entry in the machine-local registry
resolves `incomplete`, never `onboarded`. `~/.claude/working-repos.yaml` is not a verdict input
(it is `--batch`'s candidate list). Only a fully-registered verdict lets a consuming product suppress its onboard button. Engine-side (C1).

## Already-onboarded no-op (AC4)

Every lane, run against an already-onboarded repo, exits 0 with an `already-onboarded` verdict; a
genuine conflict surfaces as a `repair` or `update` disposition, never a failure or prompt. Engine-side (C1).
