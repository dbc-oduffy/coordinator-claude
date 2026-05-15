# Super-Skill Architecture

> Spec backlink: `docs/plans/2026-05-06-decision-tree-skill-pattern.md`

Decision-tree skills ("super-skills") are the primary shape for coordinator workflow skills. This wiki documents the contract governing their structure, plus the calibration doctrine for when to collapse thin skills into super-skills vs. retain them as standalone units.

## Decision-Tree Skill Contract (7 rules)

1. **The skill is a tree the EM walks at trigger time**, not prose the EM absorbs at boot. Each branch terminates in a single concrete action.
2. **The root is a triage question** whose branches cover all realistic invocation shapes. Unrecognized shapes fall to a "surface to PM" leaf, never to a default action.
3. **Each leaf names exactly one action** (dispatch X, read Y, run Z, ask PM). No compound "and also" leaves.
4. **Branch conditions are observable**, not judgment calls the EM must infer. Wrong-branch misfire produces a recoverable error, not silent misbehavior.
5. **No fallback escape hatches.** A branch that says "if MCP unavailable, fall back to grep" codifies the wrong shape: executors under pressure pick the fallback every time. Convert "missing verb" branches into explicit prerequisite Step 0 checks that fail-loud.
6. **Load-bearing steps must survive demotion verbatim.** When consolidating a standalone skill into a super-skill branch, carry every load-bearing step exactly — "trimmed for brevity" is task failure. Phase-anchored cross-references survive when phase numbers move with the algorithm.
7. **TDD applies.** Ship with a passing pressure scenario (at least one subagent run where the skill was absent and the agent violated the rule, followed by a run where the skill is present and the agent complied).

Related: `docs/wiki/writing-skills.md` for full skill authoring conventions.

## Demote-vs-Retain Calibration

When a skill has grown thin (single caller, mechanical steps, no judgment required), collapse it rather than maintain a standalone file. The fold target depends on the engine shape:

| Engine shape | Fold target | Example |
|---|---|---|
| Single-caller mechanical | Inline in the caller skill | `daily-review` → `/workday-complete` Step 4 |
| Shared procedure, multiple callers | Wiki those callers walk | `review-dispatch` → `docs/wiki/reviewer-pipeline.md` |
| Pure mechanical, no judgment | `bin/` script | `generate-repomap` → `bin/generate-repomap.sh` |
| Judgment-requiring, multi-caller | Retain as super-skill or standalone | `coordinator:plan`, `coordinator:review` |

**the Staff Engineer's "scaffold defaults" caveat.** When the source skill carries audit-and-classify doctrine (e.g. a reviewer skill that adjudicates findings), inline/wiki targets must preserve every load-bearing step verbatim — scaffold defaults can introduce a privacy/leakage regression if the classify step gets dropped. Review the diff against the original after demotion; "the logic is equivalent" is not sufficient.

**Phase-anchored cross-references survive demotion.** When a caller cites `Phase 2.7c` of a now-demoted skill, the caller's reference still resolves if the phase numbers move with the algorithm to the new home. Update callers' citations to point at the new location; don't leave orphan phase references.

**Deprecation-cycle posture by consumer count.** At ≤2 known consumers, migrate in one commit (both consumers visible in `git grep`). General "deprecation cycle" pacing is for surfaces with diffuse external consumers; in-tree surfaces with small N don't need the ceremony.
