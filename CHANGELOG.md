# Changelog

All notable changes to coordinator-claude are documented here.

## [4.0.0] — 2026-08-06

**v4.0.0 does things no earlier version of coordinator-claude could do.** It is not a port of the same
system into a different language. The capability set and the efficiency are both a long way past 3.x,
and they came from the same move: coordination that used to be prose a model had to notice, retain, and
apply is now code that runs whether or not anyone remembered it — and once it is code, it can fire on
its own, at the moment it is needed, and leave a fact behind. The bash→Python migration and the engine
split described below are *how* this was built. They are not what changed.

~2,115 commits landed since v3.0.0 with nothing public in between; this release closes that gap in one
bump rather than several silent ones.

### The doctrine half now acts on its own

This is where the new capability lives: **87 hook scripts, entirely Python, no shell at all, wired into
42 registered entries across nine harness events.** Earlier versions used hooks almost exclusively to
*forbid* things. These ones run work.

- **A skill can fire itself off what you typed.** Resuming no longer depends on the model noticing it
  should invoke `/pickup`. A prompt-expansion trigger computes the entire pickup routing — dirty-tree
  scope, branch state, claim state, whether a live peer is already holding the same baton, closure
  evidence for every pending item — and hands the session one resolved decision object before it has
  read a single file. `/mise-en-place` fires the same way.
- **Silently dropped work is caught mechanically.** A dispatched agent that returns having used no
  tools is *detected* at subagent-stop rather than believed. An agent that finished without delivering
  its report is caught at dispatch. Every dispatch is logged and tracked as it happens.
- **Turn-end checks nobody would reliably run by hand.** An ask that skipped the sizing gate, a harness
  directive that was never dispatched, an executor past its time ceiling — each is a stop-hook check
  against live state instead of a rule someone has to remember.
- **Context pressure stops costing work.** A pre-compaction trigger writes session state to disk before
  the window collapses, rather than relying on a handoff being written in time.
- **Boot self-heals.** Orientation is recomputed at session start, clobbered settings are repaired,
  foreign-platform paths are detected, and the hook layer probes its own generation for staleness.
- **Dispatch is shaped at the moment of dispatch** — agent tier offered cheapest-first by *measured*
  startup cost, background-by-default enforced, unmodeled agents in a workflow blocked, and native plan
  output persisted as a real artifact instead of left ephemeral.

### Skills compute their own routing — "super-skills" are retired

v2.0.0's headline was the **decision-tree super-skill**: a prose tree inside `SKILL.md` that the model
walks branch by branch at trigger time. It beat narrative prose, and it is now retired from the top of
the ladder. A **computed skill** replaces it: a read-only engine call computes the whole routing over
disk, git and frontmatter state and returns one JSON decision object, sorting every branch into
do-for-you, recommend-for-you, or your-call. The skill body keeps only the judgment.

`pickup` is the worked case and its numbers are the argument: **`pickup/SKILL.md` went from 728 lines to
173, with zero command fences left in it.** The model's job went from re-deriving ~45 mechanical
branches by hand on every invocation to resolving the ~17 that genuinely need judgment. Nothing was
lost in the cut — the 45 branches still happen. They are computed now, in one place, with tests under
them.

The decision-tree shape survives where it is still the right answer: judgment-dense, low-frequency
skills like plan triage and review disposition, where routing depends on product context no assembler
can observe. What is gone is treating a prose tree as the answer for a high-frequency skill whose
branches were mechanical all along.

### Prose was never free

An instruction reaches a model by one of four routes: harness mandate (the config files every spawned
agent reads on boot), invocation (skills and slash commands), injection (hooks), or the prompt itself.
Only the last is under a human's control at the moment it matters. The other three are prose the model
must notice and *choose* to apply — and every one of them is read on boot whether or not it is used, so
a more robust governing architecture becomes a more expensive one to run. Prose also cannot be unit
tested, and it drifts by copying: the same paragraph in forty agent bodies is forty implementations
that have already diverged.

The governing test is *for every rule, what artifact discharges it?* — and "the operator remembers" is
not an answer. Rules with exactly one correct answer became operations. Roughly half of this system's
governing prose has been deleted on that basis, and the results got better rather than worse, because
what remained was almost entirely judgment — which is what large models are actually good at reading.

Measured in this release: agent bodies cut **~31.5% fleet-wide** with a size ratchet underneath so they
cannot creep back; guard and advisory messages capped at runtime rather than by authorial restraint;
per-command startup overhead down again, with redundant file-write hook processing folded from **eight
passes to two**; and ~166 engine operations behind all of it, each held to a per-invocation budget
measured against a real subprocess.

### Why the engine ships as its own repository

coordinator-claude used to be one thing: a plugin full of prompt text. It is now two, and the second is
not a plugin at all. The doctrine — skills, agents, commands, hooks, personas, wikis — stayed here. The
executing half became `coordinator_core`, shipped from
[`claude-klabauter`](https://github.com/dbc-oduffy/claude-klabauter).

**A harness config directory is a guarded surface.** An agent accumulating resident executing code
inside its own instruction directory is exactly the shape that trips vendor safety guards — and it did,
repeatedly. Moving the executing half into a separate, installable, versioned Python package stops that
class of alarm at the source. It also decouples two things that never wanted the same release cadence:
an engine change now ships without a doctrine change and vice versa, instead of either requiring a
coordinated multi-repo commit. Doctrine changes when we learn something about how the work should go —
often, and on the strength of an argument. The engine changes when a mechanism is wrong — less often,
and on the strength of a failing test. Those want different gates.

**Portability was the other forcing function.** Shell on the hot path is not portable. Agent tooling is
optimised for POSIX and trained to reach for bash, which on Windows means a cold `bash.exe` per
invocation on the commit path — process storms severe enough to make scaled agentic work unusable — or a
silent no-op where no bash exists at all, which is a coordination system that has quietly stopped
coordinating. Windows is now first-class alongside macOS and Linux; new automation is naked Python
3.11+.

The long-form argument for the split, including what it costs, is
[`docs/wiki/manifesto.md`](docs/wiki/manifesto.md).

### What this costs, stated plainly

None of the above is free, and the bill is itemised rather than buried.

- **A doctrine-only install is a smaller thing than v3 was.** Roughly 20 `block-*` safety hooks were
  deleted from this repo and their successors live in the engine. An installer who skips the engine has
  no destructive-`rm` guard, no destructive-git guard, no `--no-verify` block, and no subagent
  write-sandbox confinement. That is a real reduction in shipped safety surface, not a cosmetic one.
- **Two repos means a dependency, a version seam, and an install story** with more steps than "add the
  marketplace."
- **This breaks existing installs, thoroughly.** The entire executable surface was renamed, two
  skills/agents were retired, and the handoff lifecycle vocabulary changed shape. Hence a major bump on
  the honest reading of semver rather than the flattering one.

### Upgrading from v2.7.0

v2.7.0 was the last **published** release — the 2.7.x/2.8.x/2.9.x/3.x entries below were
changelogged but never publicly tagged, so if you are on a released version you are coming from
v2.7.0 and everything in that span reaches you at once. Four things need action:

1. **Reinstall the plugin — there is only one now.** v3.0.0 collapsed five marketplace plugins
   (`coordinator`, `web-dev`, `data-science`, `deep-research`, `notebooklm`) into a single
   `coordinator` plugin with a flat repository layout. The separate marketplace entries are retired;
   their agents and skills ship inside `coordinator`. This is a change to *what you install*, not
   just a version bump — remove the old plugin set.
2. **Install the engine.** `coordinator_core` is a hard prerequisite for most mutating operations,
   and it is a separate install from
   [`claude-klabauter`](https://github.com/dbc-oduffy/claude-klabauter) (Apache-2.0 with a Commons
   Clause rider). Install coordinator-claude first, then the engine. Without it you keep the
   judgment flows — plan review, persona review, reasoning about a diff — and lose the durable
   work-state machine plus the guards listed under Breaking changes.
3. **Update the vocabulary.** The lifecycle commands were renamed and their deprecation aliases have
   since been removed:

   | v2.7.0 verb | v4.0.0 verb |
   |---|---|
   | `/session-start` | `/workstream-start` |
   | `/session-end` | `/workstream-complete` |
   | `/coordinator:setup` (scaffold a repo) | `/coordinator:repo-setup` |
   | `/project-onboarding` | `/repo-setup` |
   | `/bootstrap-repos` | `/repo-setup --batch` |
   | `Skill(coordinator:review-code)` | `Skill(coordinator:review --surface diff)` |

   `/coordinator:setup` still exists but now unambiguously means the install-chain walker.
   `/review-code` as a slash command still resolves via a redirect shim.
4. **Re-point anything that reads coordinator records or script paths.** The record contract moved
   to schema epoch 2 (`coordinator-schema-version` v1 → v2) with restandardized artifact shapes, and
   the handoff lifecycle enum changed twice across the span — the v4.0.0 shape is
   `status: open | claimed`. Any script, doc, or tool that names a `.sh` file or a
   `coordinator/bin/<name>` path is stale; that surface is gone from this repo.

### Breaking changes

**The `bin/`/`lib`/`hooks` executable surface was renamed wholesale — nothing that referenced a script by path survives.** Across the migration, roughly 360 files under `coordinator/bin/`, `coordinator/lib/`, and `coordinator/hooks/scripts/` were converted from bash (`.sh`) to Python (`.py`), and the majority of that executable surface relocated out of this repo entirely into the `coordinator_core` execution engine. This repo's own `coordinator/bin/` now tracks zero files. Any doc, script, or downstream tool that names a `.sh` path, or a `coordinator/bin/<name>` location, is stale.

| Old shape | New shape |
|---|---|
| `coordinator/bin/<name>.sh` | ported to `coordinator_core` (Python), not present in this repo |
| `coordinator/hooks/scripts/<name>.sh` | `coordinator/hooks/scripts/<name>.py` (where a hook survives) or retired (see below) |
| `sh`/`python` polyglot trampoline shim | deleted outright — the carve-out was rejected (amends the 3.1.0 entry; see below) |

**~20 `block-*` safety hooks were deleted, and no successor ships in this repo today.** Removed: `block-destructive-rm`, `block-destructive-git-orphan`, `block-destructive-git-clean`, `block-destructive-git-revert`, `block-blanket-git-add`, `block-no-verify`, `block-subagent-destructive-action`, `block-subagent-plan-body-write`, `block-subagent-plan-body-bash-write`, `block-subagent-archive-write`, `block-consumed-handoff-edit`, `block-tracker-edit`, `block-completion-monolith-write`, `block-reviewer-bash-outside-allowlist`, `block-runaway-find`, `block-bin-polyglot-break`, `block-dev-side-mirror-wiki`, `block-off-daily-branch`, among others. Their logic was ported to `coordinator_core.write_guards`, which ships in the separate companion repository (see below). **An installer running only this repository has none of these guarantees**: no destructive-`rm` guard, no destructive-git guard, no `--no-verify` block, no subagent write-sandbox confinement. Installing the engine repository restores them. This is a real, not cosmetic, reduction in shipped safety surface for a doctrine-only install — stated loudly rather than softened.

**`coordinator:review-code` is retired; use `coordinator:review --surface diff`.** The two skills shared duplicated triage scaffolding and one review pipeline; `review` is now the single implementation for both the `plan` and `diff` surfaces.

| Old verb | New verb |
|---|---|
| `Skill(coordinator:review-code)` | `Skill(coordinator:review --surface diff)` |
| `/review-code` (slash command) | still resolves — `commands/review-code.md` is a redirect shim, not deleted |

**The `code-architect` agent is removed.** Nothing in the tree — no skill, no command, no pipeline — ever dispatched it; it existed only as an entry in rosters and registries. No migration: there was no live caller to redirect.

**Handoff lifecycle vocabulary overhauled.** The prior enum conflated "used up" with "still being carried" and had no expressible terminal state for a handoff whose work continued into a successor.

| Old field/value | New field/value |
|---|---|
| `status: active \| consumed` | `status: open \| claimed` |
| `consumed_at` / `consumed_by` | `claimed_at` / `claimed_by` |
| `deployment_state: abandoned` | `deployment_state: continued \| closed` (`closed` carries a `closed_reason`: `cancelled \| displaced \| stale`) |

Existing `state/handoffs/` records are migrated; `handoff-archived.schema.json` still reads the legacy `active`/`consumed`/`abandoned` values for old archived records (read-tolerant, not a live target).

### The engine dependency in detail

32 of this plugin's 36 skills touch engine-installed surface — `coordinator_core`, the Python execution engine that produces work-state artifacts and drives session control (`/pickup`, `/handoff`, `/workstream-complete`, `/execute-plan`, among others). Both halves of that count are reproducible from the tree: 32 is the count of skills invoking *any* CLI, hook, or op the engine installs; 11 is the narrower count that name `coordinator_core` in their own body. coordinator-claude declares a hard dependency on that engine, and it ships from a **separate companion repository, [`claude-klabauter`](https://github.com/dbc-oduffy/claude-klabauter), released alongside this version**. Installing only this repository gets you the doctrine and the machinery it drives; those 32 skills additionally need the engine repository on the machine-local registry. The split is deliberate and the two layers version independently — it is a boundary, not a gap.
>
> **Correction, 2026-08-06:** "released alongside this version" was true-as-intended at the time this entry was written but has not held up: `claude-klabauter`'s publish is **not yet live** (zero commits pushed as of this correction). Until it goes live, the engine is available on request from the maintainer, the same access model already used for `project-rag`. Nothing else in this entry changes — the boundary and the hard dependency both stand.
>
> **Correction, 2026-08-07:** the publish is now live. [`claude-klabauter`](https://github.com/dbc-oduffy/claude-klabauter) is public (Apache-2.0 + Commons Clause), so the original "released alongside this version" claim now holds and the access-on-request workaround in the 2026-08-06 correction is withdrawn. Install it from that repository; no request to the maintainer is needed. Both corrections are kept in place rather than deleted, so the record shows what was true when.

### Highlights

- **DR-047/DR-059/DR-060 bash→`coordinator_core` engine migration completed.** The Zod/TS cockpit-contract emitter is retired; `coordinator_core`'s pydantic emitter is canonical. The doctrine repo retains governance of the frozen artifact contract; the engine owns execution.
- **Weekly-goal (OKR) loop closed.** Weekly priorities are first-class `period=week` goal artifacts, wired into orientation and cockpit-contract wire fields.
- **Artifact-shape and record-family hardening continues** on top of the v3.0.0 tc-0 → tc-4 fleet-substrate: widened handoff/decision schemas, a portability-gates spec + conformance bar turning two ad hoc scripts into a fleet contract, and a corpus-wide sweep closing a machine-absolute-path leak class.
- **Cross-repo commit-grant retirement (DR-127).** The former standing commit grant into the engine repo is retired outright, not superseded quietly — every cross-repo write now routes through the `cross-repo-memo` CLI + relay, with per-session assent required for any cross-repo commit.
- **Subagent Bash confinement narrowed to two classes (DR-125)**, replacing the broader write-sandbox mechanism that DR-058 retired in 3.1.0.
- **Sizing lobby.** Novel work now enters through a dedicated `coordinator:sizing` gate before routing to plan/shape/roadmap/dispatch, closing a class of underweighted asks that skipped straight to implementation.
- **Fabricated or stale planning inputs are now caught earlier.** An automated check confirms where a plan's stated justification actually came from before planning proceeds, and separate automated detection flags stale or unverified documentation before it ships.
- **A prompt-injection-style loophole is closed.** Text arriving inside tool output is now documented, and enforced, as never trusted as a command — closing a proposal that would have let certain marked messages in tool output be treated as instructions.
- **The published package now always regenerates correctly from source.** The published coordinator-claude package is rebuilt from a clean slate on every publish, closing a gap where the published copy could quietly drift from what was actually shipped.
- **Continued Mac/Linux/Windows portability hardening.** Assumptions that only hold on Mac/Linux are now banned in code, not just doctrine.

### Notable

- Orientation cache made fresh-by-construction (self-heals at boot instead of relying on four separate human-invoked ceremonies) and untracked fleet-wide.
- Runtime tripwire and the fast-tier test-exit path both had unscoped/false-positive defects closed.
- Console-popup nag (DR-054) and the old subagent write-sandbox confinement (DR-058) — both already retired in 3.1.0 — stay retired; DR-125 is their narrower replacement.
- The install target is retired as a percolate source (DR-122): it is a destination only, never a publish origin.
- A POSIX-only-execution-assumption ban landed in code, not just doctrine.
- Ceremony summaries moved to report-by-exception.
- Reviewer feedback now identifies reviewers by stable role name instead of a hardcoded persona name, fixing a real bug where renaming or removing a reviewer agent would have silently produced meaningless output.
- Fast test runs now require an explicit per-session permission grant before they can fire, closing a gap where the fast test tier could be triggered far more often than intended.
- A durable priority ledger now lets stated priorities persist across sessions instead of being re-derived from scratch each time.
- Beyond `pickup` (see "Skills compute their own routing" above), the computed shape also reached a new task-sizing entry point and a safer step-by-step migration primitive.
- Slow imports were removed from the code path that runs on every terminal command.

### Other

- ~20 `block-*` hook test suites retired alongside their hooks (see Breaking changes); `check-shipped-on-main`-style reachability checks folded into the engine repo's parity suite.
- `/mise-en-place` gained an explicit definition of completion, decoupled from `/autonomous`'s posture.
- `dep-cve-auditor`, `plan-coverage-checker` Lens 4, and several one-off machine-specific hardcoded paths removed in favor of `machine-local` registry lookups.
- Roadmap stub codes re-prefixed to globally-unique `<slug>-N`; `tc_id` renamed to `stub_id` end-to-end.
- Goal targets can now be pulled in from an external source in addition to being set directly.
- A macOS-specific gap in cross-platform install reliability was closed, along with a safety check meant to catch this kind of regression that had never actually been working.

### Amendment to the 3.1.0 entry (2026-08-03)

The 3.1.0 theme line claimed "script invocation is preserved via sh/python polyglot trampolines." That claim is **false as of 4.0.0** — the polyglot-trampoline carve-out was reconsidered and rejected; the trampolines were deleted as part of the de-bash campaign above. The 3.1.0 entry below is annotated in place rather than silently rewritten; this is the correction, not a retraction of the fact that the claim was true when 3.1.0 shipped.

---

**The entries below were changelogged but never publicly released.** v2.7.0 is the last published
release; v2.7.1 through v3.1.0 were tagged internally only. They are kept, compressed to theme and
breaking changes, because they are part of the upgrade path from v2.7.0 rather than history anyone
received. Full detail for each lives in the release-notes archive named in its entry.

## [3.1.0] — 2026-07-19

> Theme: **infrastructure & engine migration** — the bash→`coordinator_core` Python migration (DR-047/DR-059) and the contract-vs-engine ownership split (DR-060), alongside the new weekly-goal (OKR) system. **Amended 2026-08-03:** the original theme line's claim that "script invocation is preserved via sh/python polyglot trampolines" is no longer true — the 4.0.0 de-bash campaign rejected that carve-out and deleted the polyglot trampolines outright. See the 4.0.0 amendment above.

No consumer-facing breaking changes at the time 3.1.0 shipped: the vendored artifact-shape contract stayed additive. The doctrine-side Zod/TS cockpit-contract emitter was retired in favour of `coordinator_core`'s pydantic emitter (76 files), the plan→execute baton was first-classed as a typed `handoff_phase` schema, and `cross-repo-memo send` was repointed onto the engine's `memo.send` op. DR-054's console-popup nag and DR-058's subagent write-sandbox confinement were retired here.

Full per-entry detail with source links: `archive/release-notes/2026-07-19-v3.1.0.md`.

## [3.0.1] — 2026-07-13

Patch release — OSS percolate hardening (an internal-codename scrub, `.git/` exclusion in the leak scanner). No breaking changes.

## [3.0.0] — 2026-06-27

> Theme: **re-architecture of the document-infrastructure / artifact-shape contracts for standardization and queryability** — the largest structural shift since the move to super-skills. The coordinator's entire artifact surface (handoffs, queues, lessons, completions, audit records, review trail, week-changelog) was given uniform, machine-addressable shapes, so the whole substrate became uniformly queryable. Second theme: a large install-surface and macOS cross-platform-portability hardening cohort from clean-target dogfooding.

### Breaking changes

**Distribution consolidated from five plugins to a single `coordinator` plugin.** The v2 marketplace shipped `coordinator`, `web-dev`, `data-science`, `deep-research`, and `notebooklm` as separate plugins; v3 folds them into one `coordinator` plugin with a flat repository layout (`source: .` at the repo root). The front-end, data-science, and research agents and skills now ship inside `coordinator`. Upgrading consumers install the single plugin — the separate marketplace entries are retired. **This is the change a v2.7.0 upgrader is most likely to miss**; see the 4.0.0 upgrade section above.

**`coordinator-schema-version` bumped v1 → v2.** The install contract and all central-owned record readers move to schema epoch 2. Consumers of coordinator record contracts must account for the v2 shapes.

**`superseded` retired as a handoff status value.** Supersession became `status: consumed` + `deployment_state: abandoned` (+ `predecessor`/`supersedes:` lineage). Superseded again by the 4.0.0 vocabulary — a v2.7.0 upgrader should target the 4.0.0 shape directly.

**Artifact shapes restandardized across the record family.** Plans, decisions, sidecars, queues, lessons, audit records, atlas files, and week-changelog dailies gained canonical machine-addressable shapes; the artifact-shape-contract emits versioned schemas (v1.1 → v1.5, including a deliverable-type-schema taxonomy with kind-aware `matchSchema`). Downstream consumers re-vendoring these shapes should target the v1.5 contract.

Full per-entry detail with source links: `archive/release-notes/2026-06-27-v3.0.0.md`.

## [2.9.0] — 2026-06-24

> Theme: **native-CLI install migration + install-suite hardening, from a week of clean-target dogfooding.** Cuts over to the native `claude plugin` CLI as the primary install path; the harvest of stress-testing `coordinator:install`, `repo-setup`, the install-chain walker, and the publish/percolate path against fresh machines. Most entries close a gap that only appears on a machine you've never seen. Also added: `/coordinator:new-project`, a three-state Claude-home install classifier, a durable coordinator venv pin, declared `system_prerequisites` (manifest contract v3), and Windows console-flash suppression.

### Breaking changes

**`/coordinator:setup` is now the install-chain walker only — repo scaffolding moves to `/coordinator:repo-setup`.** The scaffolding command was a redundant wrapper over `/coordinator:repo-setup` (which already does single-repo *and* `--batch` fleet via the same orchestrator) and collided with the ecosystem-wide `/<repo>:setup` install-chain-walker convention.

| Old verb | New verb |
|---|---|
| `/coordinator:setup` (scaffold a repo) | `/coordinator:repo-setup` |
| `/coordinator:setup --batch` (fleet) | `/coordinator:repo-setup --batch` |

**`/project-onboarding` and `/bootstrap-repos` consolidated into a single `/repo-setup` command.**

| Old verb | New verb |
|---|---|
| `/project-onboarding` | `/repo-setup` |
| `/bootstrap-repos` | `/repo-setup --batch` |

Rationale: new-project setup is infrequent enough that muscle-memory cost is low, and a single surface eliminates the "which verb do I invoke when" decision the prior dual-surface architecture imposed on every setup site.

## [2.8.1] — 2026-06-01

Patch release — weekly-close residual: install-surface exec-bit fix (168 hook/bin scripts were committed non-executable, so on fresh Mac/Linux clones they silently never ran), an acceptance-oracle `sh:`/`bash:` typed prefix, review-trail `scope_kind`, and weekly-gate test hardening.

### Breaking changes

**The `/session-start` and `/session-end` deprecation aliases are removed.** The transition stubs shipped in 2.8.0 are gone after a single release cycle. Use `/workstream-start` and `/workstream-complete`. (Temporal "session start/end" prose and the `SessionStart`/`SessionEnd` platform hooks are unaffected — only the slash-command aliases were removed.)

**`reviewed_at_session_end` handoff frontmatter key renamed to `reviewed_at_workstream_complete`.** 2.8.0 deliberately kept the old name for record back-compat; that constraint turned out to be empty — the field is write-only and no handoff record, live or archived, ever carried it. No record migration was needed.

## [2.8.0] — 2026-06-01

> Theme: **lifecycle skill renames and nomenclature correction**, plus `cross-repo-memo --list-receivers` and the install-contract orientation-supersession layer. The `{session}-start` / `{session}-end` skill names shadowed the `SessionStart` / `SessionEnd` platform hook identifiers, creating a three-way collision (skill slash-command, platform hook key, temporal phrase). The rename breaks it: platform hooks keep `SessionStart`/`SessionEnd`; temporal "session start/end" prose stays free English; the invoked skills become `workstream-*`.

### Breaking changes

**`/session-start` → `/workstream-start` and `/session-end` → `/workstream-complete`.** Deprecation aliases shipped here and were removed in 2.8.1 (above), so from v2.7.0 the net effect is a hard rename.

```diff
- /session-start
+ /workstream-start

- /session-end
+ /workstream-complete
```

The mutual-exclusion doctrine (`/handoff` vs. `/workstream-complete`) is unchanged — just the command name.

## [2.7.1] — 2026-06-01

Patch release — the 2026-06-01 weekly-close ceremony fixes: weekly validation gate unblocked (capability-catalog union read, nested-git plugin-dir skip), `block-no-verify.sh` made CRLF-robust after a transient working-tree CRLF crashed the hook and denied all Bash mid-session, and `workweek-trail-scope.sh` hardened against non-diff `sha_range` records and git-argument injection. No breaking changes.

## [2.7.0] — 2026-05-31

The last publicly released version before 4.0.0. A large batch of session-lifecycle, hook, and skill work, plus the previously-undocumented 2.6.0 safety hook folded in. Headlines: EM-environment and boundary-guard hooks, a generated-tracker system, the cross-repo memo `--kind` lifecycle, the fan-out demotion, and assorted reviewer/skill hardening.

### Added

- **EM-environment & boundary-guard hooks** — effort/model self-check baked into the three start ceremonies and the `/plan` entry point; a nudge that catches the probe-spray loop at the boundary; a `git -C`-over-`cd` redirect; `block-destructive-rm` to guard uncommitted-work loss; `guard-settings-integrity` to auto-recover a clobbered `settings.json`.
- **`block-destructive-git-orphan` safety hook** (originally 2.6.0) — blocks destructive git operations that would orphan commits; pairs with the tool-output-flakiness floors.
- **Generated-tracker system** — schema fields, `query-records` memo type + renderer, producer templates emitting category+summary, lifecycle wire-ins, and edit-resistance for generated trackers.
- **Cross-repo memo `--kind {ask,consult,fyi}`** — a validated kind enum, `/pickup` form-classification fork, and surfacing priority by kind.
- **New skills** — `coordinator:systematic-debugging` (single-issue root-cause discipline) and `/coordinator-update` (OSS self-update).
- **`editable_sibling_venv` propagation mode** — drift-check support for addons editable-installed into a sibling host venv.

### Changed

- **Fan-out demoted from a skill to a methodology** — it collided with native Claude Code vocabulary; `fan-out-dispatch.sh` plus the dispatching-parallel-agents wiki are now the surface. Concurrency uses an organic ramp instead of a hard 6–8 cap.
- **`block-unauthorized-handoff`** reworked from a hard block into a warn-not-block nudge.
- **`bug-blitz`** now runs the full test suite every run and treats failing tests as first-class fix items.
- **`/workweek-complete` version bump** deferred to the consumer's `versioning-convention.md`.

### Fixed

- Tool-output-flakiness stop-at-floors (re-run-solo discipline, destructive-git/rm floors); session-end reviewer routing (named reviewers for plans/arch, not code output); install-portability sweep (bash-4 / BSD-GNU / python3 gotchas across the install surface); drift-check path corrections; assorted hook and skill repairs.

---

## Earlier releases

Every entry for **v2.5.1 and older** — v2.5.1, v2.2.0, v2.1.0, v2.0.0, and the whole 1.x line back
to the initial public release — has been moved verbatim to
[`docs/wiki/changelog-history.md`](docs/wiki/changelog-history.md), including the corrections and
amendments attached to those entries. It is kept for provenance; nothing there is part of the
upgrade path from v2.7.0.
