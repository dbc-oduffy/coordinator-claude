---
title: "State placement law — where session-authored artifacts live"
created: 2026-07-03
status: active
spec_backlink: docs/plans/2026-07-03-stop-the-rot-claude-klabauter-state-home-placement.md § AC7
---

# State Placement Law — Where Session-Authored Artifacts Live

> **Purpose (spec backlink: `docs/plans/2026-07-03-stop-the-rot-claude-klabauter-state-home-placement.md § AC7`).**
> Durable rule for where every session-authored artifact lands after the claude-klabauter state-home
> migration. This wiki is the SSOT for artifact-authoring surfaces (`coordinator-doc-new`,
> `/handoff`, `/plan`, hooks, CLI tools) to resolve their write-target. Never hardcode
> `~/.claude/state` as a central-state write target — route through the seam.

---

## Why This Exists — The Stop-the-Rot Rationale

Before this migration, `~/.claude` conflated three distinct concerns: the Claude Code harness
home, the plugin source tree (OSS-published), and the coordinator's executing working data
(`state/`, `docs/{plans,research,problems}`). Every new session layered more work-state into
`~/.claude`, compounding structural rot. The fix: **relocate working data to the claude-klabauter sibling
repo** and route every artifact-authoring surface through a resolver seam, so future pickups
automatically land in the right place.

The durable value: separation of concerns (harness home ≠ working data home), a regression guard
against permission-trip recurrence, and enabling the engine-absorbs-shell trajectory.

---

## Taxonomy — What Goes Where

| Artifact class | Post-migration home | Notes |
|---|---|---|
| **Central/global state** (`state/lessons/`, `state/trackers/`, `state/queues/`, `state/ledgers/`, `state/memos/`, `state/scratch/`, `state/debt-backlog/`, `state/bug-backlog/`, `state/improvement-queue/`, `state/lessons-outbox/`) | **claude-klabauter — unconditionally** | Central state for all coordinator-installed repos. `CLAUDE_KLABAUTER_ROOT` is the root; `coordinator-state-root.py --central`'s output is the write target. *Mechanism lag: the subject-classification seam rewire is pending the doe-authoring-repo spinoff — `coordinator-state-root.py --central` routes here unconditionally until that spinoff lands (see § Plan Homes).* |
| **Per-repo work state** (`state/` under a sibling project). Includes session-scoped `state/handoffs/`, `state/orientation_cache.md`, `state/review-trail/`, `state/week-changelog/`, `state/audits/`, `state/recovery/` — resolved via `coordinator-state-root.py` (no flag), which for the meta-repo still redirects to claude-klabauter but for a sibling stays local. | **Unchanged for siblings** — `$GIT_ROOT/state/` | example-os-repo, project-rag, example-game-repo, etc. all keep writing their own `state/`. Only when `$GIT_ROOT` IS the meta-repo (`~/.claude`) does per-repo state redirect to claude-klabauter. **Exception — install-baton rendezvous:** the shared `state/handoffs/` rendezvous that a downstream repo's installer seeds an install/orient `kind: spinoff` baton into is NOT this per-repo `$GIT_ROOT/state/` and NOT row-36 central claude-klabauter state — it is machine-shared install substrate at `$(coordinator-settings-home)/state/handoffs/`, distinct from both. See the dedicated **Install-baton rendezvous** row below. **Distill-reap exception — `state/review-trail/` (historical; superseded home is `state/subagent-share/`, see below):** `state/review-trail/findings/*.md` sidecars carrying a `## Integrator Dispositions` block (already integrated into a plan by the review-integrator) ARE reaped by `/distill`'s targeted `bin/reap-integrated-review-findings.py` (`PIPELINE.md` § Phase 5 step 10) — a surgical, named, post-integration reap of one artifact class, distinct from a `/distill` directory purge, and history-preserving (`git rm`, not `rm -rf`). **Disjoint complement — claude-klabauter-owned, marker-ABSENT-and-aged:** the never-integrated tail — `state/review-trail/findings/*.md` sidecars that are marker-absent AND aged >14d — is reaped by claude-klabauter's `fleet.reap_unintegrated_findings` op (sanctioned by claude-klabauter DR-218, run on claude-klabauter's `session.boot_sweep` cadence at session-init + `/workday-start`), NOT by `/distill`. Age is filename-derived only (checkout-invariant — a fresh clone's recent mtimes never disable it — via a three-tier date cascade, fail-closed-to-keep on a genuinely date-less name), the delete is history-preserving (`git rm`, never `-f`, so a concurrently-modified sidecar fails closed and is retained), and each candidate gets an act-time terminality re-verify so a sidecar that gains the `## Integrator Dispositions` marker between scan and reap is skipped. Two disjoint reapers over one artifact class: leg (a) reaps marker-PRESENT (DoE-owned, `/distill`); leg (b) reaps marker-ABSENT-and-aged (claude-klabauter-owned, boot_sweep) — no overlap, nothing double-reaped. **`state/review-trail/` is a closed corpus** — nothing writes it; the live home for every provisioned sidecar is `state/subagent-share/` (DR-091, row below). The two reap legs above govern what is already there. |
| **Per-repo work state — `state/subagent-share/`** (provisioned subagent run-report sidecars: review findings, staff-eng-review, and general run-reports) | **Unchanged for siblings — `$GIT_ROOT/state/subagent-share/<session>/<provision_key>.md`** (per-repo, same resolver as the row above) | DR-091's one home for every provisioned subagent sidecar — see `docs/decisions/DR-091-agent-citizenship-identity-typed-sidecar-contract.md`. **Not provisioned here:** the plan-pipeline sidecar-emitters — prior-art-check, plan-coverage-check, docs-check (and, when it fires, external-pattern) — do not provision here; their OUTPUT home is the plan-derivable `state/plan-sidecars/<plan-stem>.<lens>.md` (see the **Per-repo work state — `state/plan-sidecars/`** row below), because their path is derivable from the plan itself rather than session-keyed. Reaped by `bin/reap-stale-subagent-sidecars.py` (claude-klabauter-resident; shipped by `docs/plans/2026-07-24-reviewer-sidecar-provisioning-reconciliation.md` chunk C7) under the general delete-by-convention reap rule (see § Delete-by-Convention Reap Doctrine below): ephemeral scaffolding whose durable content has already folded into a consuming artifact (the review-integrator's Disposition block, an executor's doc-handoff contract, etc.) is deletable, gated on session liveness AND/OR an age floor — never `status:` alone. Wired into `/distill` Phase 5, `/update-docs`' sweep, a `/workweek-complete` cron step, and on-demand invocation. |
| **Per-repo work state — `state/plan-sidecars/`** (plan-pipeline lens sidecars: prior-art-check, plan-coverage-check, docs-check, and — when it fires — external-pattern) | **`$GIT_ROOT/state/plan-sidecars/<plan-stem>.<lens>.md`** (per-repo, plan-derivable — claude-klabauter's `provision_report` is the single path-deriving surface, D0/Z2) | **UNREAPED BY DESIGN** — not swept by `bin/reap-stale-subagent-sidecars.py` or any age/liveness-gated reaper, and deliberately NOT widened into that reaper's scope (the Director of Engineering Z1, rejecting the alternative of folding this class into row above). Rationale: these sidecars ARE the prior-art-checker / plan-coverage-checker false-positive-arbitration feedback-loop archive (`coordinator/agents/prior-art-checker.md:316`, "Never delete a prior sidecar") — a second run of the same lens against the same plan must find the first run's verdict at the same plan-derived path (rename-on-existing, never delete). Deleting them on an age/liveness floor would destroy exactly the cross-run continuity the feedback loop depends on. See D0's Reap-disposition paragraph in `docs/plans/2026-07-24-g2-plan-pipeline-sidecar-contract.md` for the full rejection-of-alternative reasoning. |
| **Install-baton rendezvous** (shared install/orient batons — `kind: spinoff` batons carrying `install_chain_order:` or an orient-leg discriminator, seeded by a conforming repo's installer or coordinator's own onboarding flow) | **`$(coordinator-settings-home)/state/handoffs/`** — machine-shared, per-machine install substrate | Distinct from per-repo `state/handoffs/` (row above — session-scoped, `$GIT_ROOT`-resolved) and from central claude-klabauter state (row above — meta-repo session state). Mints the same `<settings-home>` root prefix as the C9 (`docs/plans/2026-07-06-durable-substrate-to-settings-home.md`) `<settings-home>/<repo-id>/` install-status-ledger / chain-walk-visited-set precedent — both are per-machine install substrate, a plane distinct from claude-klabauter's meta-repo session state — but the rendezvous is NOT scoped under `<settings-home>/<repo-id>/` (it is machine-shared, not per-repo-id). See `agent-install-contract.md` § The rendezvous and § Relocation boundary. Compat: legacy `~/.claude/state/handoffs/` read as fallback during the transition window. |
| **Meta-repo operational docs**: top-level `~/.claude/docs/{plans,research,problems}/` whose deliverable does NOT edit the plugin source tree | **claude-klabauter** | Physically moved at migration (not auto-resolved); new artifacts authored via seam-routed surfaces land in claude-klabauter. Doctrine-subject plans land in the DoE clone's single `docs/plans/` — see § Plan Homes below. |
| **Plugin source** (`bin/`, `lib/`, `hooks/`, `skills/`, `agents/`) | **DoE clone — `coordinator/` tree, resolved live via `--plugin-dir`** | Current tooling shape: coordinator plugin source is resolved live from the external DoE clone (`$REPO_DOE_CLAUDE/coordinator/`) via Claude Code `--plugin-dir`; the `~/.claude/plugins/coordinator-claude/` marketplace copy is retired/vestigial. OSS publish (claude-klabauter `coordinator/bin/publish.py`) sources from the allowlisted plugin subpath inside the DoE clone (DoE→OSS percolation). |
| **Wikis** (`docs/wiki/`) | **DoE clone — `coordinator/docs/wiki/`, resolved live via `--plugin-dir`** | Same coordinator tree as plugin source (`$REPO_DOE_CLAUDE/coordinator/docs/wiki/`); OSS-published Tier-1 orientation surface — moves would break publish + session boot. |
| **Decisions** (`docs/decisions/`) | **DoE clone — `$REPO_DOE_CLAUDE/docs/decisions/`** | Tier-1 orientation. `~/.claude` has no `docs/` path in any commit reachable from this clone's fetched refs, and none untracked in the pre-incident config snapshot; the corpus was seeded into the DoE clone (`b683e4e49`) and is still written there (`a7235ccf8`). DR-083 makes DoE the SSOT for DR-identifier allocation, so the write target and the numbering authority are the same tree. Note the corpus is dual-indexed — some records are date-named files carrying an internal `id: DR-NNN`, so a filename-only scan shows phantom gaps (see `naming-discipline.md`). |
| **`archive/`** | **claude-klabauter** | Session-init archives `state/handoffs → archive/handoffs` within the state-repo; claude-klabauter holds `archive/` alongside `state/`. |
| **Strategic self-description** (`state/strategic/self-description.yaml`) | **Unchanged for siblings — `$GIT_ROOT/state/strategic/`** (per-repo, same resolver as row "Per-repo work state") | New artifact class under § Fleet Producer Contract, NOT a new topology — per-repo-emitted, harvested read-side, never consolidated. See § Fleet Producer Contract → Artifact class — strategic self-description below and `strategic-self-description-standard.md`. |
| **File-based cross-session plans** (`tasks/<feature-name>/todo.md`) | **Unchanged for siblings — `$GIT_ROOT/tasks/<feature-name>/todo.md`** (per-repo, feature-scoped) | Not `state/` — this is `tasks/` ephemera (see § Taxonomy above for the `state/` vs `tasks/` split), aggressively swept by `/distill` and `/update-docs`. `/handoff` when ending a session mid-feature rather than leaving the todo file as the sole record. |

**Summary rule:** working data moves to claude-klabauter; the coordinator plugin source is DoE-resident (resolved live via `--plugin-dir`); decisions moved to the DoE clone (see the Decisions row above); other doctrine surfaces (settings, harness config) remain in `~/.claude`.
<!-- Review: code-reviewer — this sentence still listed decisions among the ~/.claude-resident surfaces, contradicting the corrected row eight lines above -->


> **`docs/wiki/` is source-only — the naming-collision trap.** The DoE-claude clone is the coordinator doctrine source of truth; `~/.claude` is the live-install and post-cutover carries no durable coordinator-owned artifact — the one residual, `.doe-root`, is a disposable regenerated mirror of the settings-home anchor (see `coordinator-installer-shape.md`). Both trees are named "coordinator-claude"; they are not the same tree. A bare `coordinator/docs/wiki/<name>.md` citation resolves against the DoE clone only — grepping it under `~/.claude` finds nothing, and that absence is NOT evidence the doctrine doesn't exist. Cross-repo citations must repo-qualify to avoid a false stand-down — see `cross-repo-citation-conventions.md § When to qualify`.

> **Negative-spec (soft-seam, claude-klabauter DR-210):** The authoritative-mutation subset — terminal work-state write + lifecycle stamp (e.g. `cross-repo-memo`'s emit-and-stamp op) — is a strangler candidate that may later relocate to claude-klabauter ops without violating this placement law.

---

## Delete-by-Convention Reap Doctrine

> Spec backlink: `docs/plans/2026-07-24-reviewer-sidecar-provisioning-reconciliation.md` § C7 (the `state/subagent-share/` reaper that generalized this rule out of the review-findings-specific reap precedent).

**General rule — applies to every ephemeral-scaffolding sidecar type, not just review findings.** A session-authored artifact is *ephemeral scaffolding* when its durable value is a fold: the artifact exists only to shepherd content into a longer-lived consuming artifact (a plan's `## Integrator Dispositions` block, an executor's doc-handoff contract, a queue entry, a wiki edit), and once that fold has happened the scaffolding itself carries no residual information the consuming artifact doesn't already have. Ephemeral scaffolding is **deletable once folded** — this is delete-by-convention: the convention (the artifact's typed shape + its consumer's contract) is what licenses the delete, not a per-instance judgment call.

**The gate is never `status:` alone.** A reaper for this class must condition deletion on session liveness AND/OR an age floor (or both), never bare completion status — a `status: complete` sidecar whose requesting session is still live, or that hasn't cleared the age floor, is preserved regardless of status. This mirrors the two legacy `state/review-trail/findings/` reap legs (marker-present / DoE-owned; marker-absent-and-aged / claude-klabauter-owned) and is now the steady-state rule for every `state/subagent-share/` sidecar type (review findings, staff-eng-review, general run-reports — **not** the plan-pipeline lens sidecars, which live at `state/plan-sidecars/` and are UNREAPED-BY-DESIGN, see that row above) via `bin/reap-stale-subagent-sidecars.py` (claude-klabauter-resident; see the `state/subagent-share/` row above).

**Why this is a named op, not an ad-hoc `/distill` purge.** A directory-purge sweep can't distinguish "folded and safe to delete" from "never folded, still load-bearing" — that's exactly the failure mode a naive `status:`-only sweep hits, reaping a sidecar an in-flight concurrent session is still writing to. Pinned in **DoE-claude** by `coordinator/tests/test_distill_subagent_share_sweep.py` (`test_gate_is_liveness_or_age_not_status_alone`) — a DoE path, not a claude-klabauter one, and the only pin this clause has. Delete-by-convention reaping is surgical and typed, scoped to one artifact class at a time — the same shape as `bin/reap-integrated-review-findings.py`.

**The fold premise requires a consumer that CONTAINS the content, not one that CITES the path.** A `state/bug-backlog/*.yaml` provenance field or archived plan naming a `state/subagent-share/<session-id>/` UUID is a pointer, not a fold; reaping its target leaves the citation dangling, and no liveness-or-age gate detects it — a cited dir looks most reapable exactly when its session is long dead. Census citations before deleting this class (~38% of on-disk dirs are cited here): `coordinator-tripwires/a-cited-sidecar-is-not-folded-scaffolding.md`.

<!-- Review: review-integrator/overengineering-reviewer — the tracked-corpus exposition duplicated
     coordinator-tripwires/a-cited-sidecar-is-not-folded-scaffolding.md § "Why the tracked corpus
     is load-bearing here" verbatim-in-substance; kept the rule sentence, cut the argument to the
     one home that already carries it. -->

**`state/subagent-share/` stays git-tracked; untracking it is a reap-gate change, not a storage
decision** — see `coordinator-tripwires/a-cited-sidecar-is-not-folded-scaffolding.md` for why. The
per-session `*.jsonl` accumulators are records of events, not work product — mined across sessions
as a ranking oracle, regenerable at no price. Machine-home literals are a sanitizer's job, never a
reason to untrack; `unresolved_cross_path` scans `.py` only and never reaches a `.md`/`.jsonl`
sidecar.

**Relationship to `scratch-lifecycle.md`.** That wiki governs *skill-emitted working-notes scratch* (a skill's own scratch dir, self-cleaned by the emitting skill at the end of its own run — Pattern A/B). This section governs *provisioned subagent sidecars* (a cross-session artifact type with its own typed reaper, gated on liveness/age rather than emitting-skill self-clean). Both share the same underlying principle — content that has already folded into a durable artifact is noise once shipped — but the mechanism differs: scratch-lifecycle is same-skill self-clean; delete-by-convention reap is a standalone, cadence-wired op over a cross-session artifact class. See `scratch-lifecycle.md` for the self-clean shape.

---

## Residency Is Not Ownership

A plan, DR, or doc living in claude-klabauter records only that **claude-klabauter is coordinator's central
working-data store** — it makes NO claim about who *owns* or *executes* the work. Ownership is
set by the tri-plane boundary (DoE's `docs/decisions/DR-047-doe-claude-klabauter-boundary-redraw-contract-vs-e.md`,
governing authority, with the custody-vs-projection framing supplied by
`claude-klabauter/docs/decisions/DR-236-state-is-disk-truth-workstate-store-is-pro.md`):
*meaning* (artifact-shape-contract + skills) → coordinator-claude; *emission-write engine + custody
of its own disk-truth bytes* → claude-klabauter; *query/retrieval capability over a derived, re-projectable
projection of that disk-truth* → rag. A plan states its own ownership in its ownership-boundary table; **never
infer ownership from the file's on-disk location.** (2026-07-04: a plan editing 100%
coordinator-plugin surfaces sat in `claude-klabauter/docs/plans/` and read as "claude-klabauter's work" — it is not.
The file is *stored* there; the work is coordinator's.)

**Fallback for artifacts lacking an ownership-boundary table** (archive/, queues, review-trail,
lessons, and most legacy backfill): ownership follows the **same subject-matter axis** — is the
artifact ABOUT engine internals (coordinator_core, pcore, resident-service) or ABOUT doctrine
(skills, hooks, ceremonies, install surfaces)? The axis that decides *home* also decides *ownership*
for un-tabled artifacts. Location remains non-authoritative; subject-matter is the inference key.

## Plan Homes — One Location

> *Supersedes stop-the-rot § AC7's plans-slice and the two-home discriminator that stood here.*

**`docs/plans/` is the one plans home. There is no second one, and no discriminator to apply.**
The same holds for `docs/research/` and `docs/problems/`. Every repo in the fleet resolves the
path the same way: `$GIT_ROOT/docs/plans/`. The only thing that varies is which repo root, which
the existing state-root chain already answers.

`coordinator/canonical-structure.yaml` carries exactly one plans row and is the machine-readable
statement of this rule; no `plans_dir:`/`plan_home:`/`plans_root:` YAML/JSON config key exists
anywhere, because the path is a constant rather than a configured value.

**Retired: the plugin-tree second home (`coordinator/docs/plans/`).** That directory does not
exist, and naming its absence is the operative part — a reader who only sees the "plans about the
plugin should travel with the plugin source" reasoning would re-create the split as an
improvement. Do not. **Residency is not ownership** (§ above) carries the intuition the split was reaching
for — a doctrine-subject plan is doctrine-plane work no matter which directory holds the file.

---

## Resolver Seam — The Single Write-Target Authority

Two primitives form the seam. Every state-writing surface routes through one of them — never
open-codes a path.

### `COORDINATOR_ENGINE_ROOT`

The engine root. Resolution chain (outer only — inner four-rung autodiscovery is
encapsulated inside `machine-local get`):

1. `$COORDINATOR_ENGINE_ROOT` env var if already set (gated by
   `[[ -z "${COORDINATOR_ENGINE_ROOT:-}" ]]` per `machine-local-registry.md §4b`). The retired
   `CLAUDE_KLABAUTER_ROOT` spelling is not a fallback rung here or anywhere else.
2. `machine-local get repos.claude_klabauter` — the registry lookup; internally runs the §4c
   four-rung discovery ladder (explicit flag → OS-keyed search-roots + marker autodiscovery →
   tracked exceptions → `.local.toml` fallback). Do NOT re-implement the inner rungs as outer
   steps; `machine-local-registry.md §4c` is the SSOT.
3. Hard-error + remediation message if both are unresolvable.

### `REPO_DOE_CLAUDE`

The DoE-claude authoring-repo root — the *doctrine plane*, sibling to `CLAUDE_KLABAUTER_ROOT` (the *engine
plane*). Resolver primitive `coordinator_doe_root` (claude-klabauter-native — `coordinator_core/ops/coordinator_doe_root.py`; there is NO `lib/coordinator-doe-root.sh` and never was, so do not reach for a sourced shell form. Reached in practice through `lib/coordinator-state-root.py --central --subject doctrine`, which routes to the DoE plane), same outer chain
shape as `CLAUDE_KLABAUTER_ROOT`: `$REPO_DOE_CLAUDE` env → `machine-local get repos.doe_claude` → hard-error +
remediation. Callers in the central write loop wrap it and degrade (WARN + skip); the primitive
itself fails loud. Introduced by the DoE-authoring-repo seam rewire (W2.1).

### `coordinator_artifact_subject <path>`

Subject-matter classifier (claude-klabauter `coordinator/lib/coordinator-artifact-subject.py`, W2.2) — the routing key for
subject-aware placement. Prints one token: `engine` | `doctrine` | `cross-cutting`. Exit 0 for a
confident engine/doctrine call; **exit 2 + stderr for cross-cutting** (detect-then-fail-loud — a
genuinely two-plane artifact never auto-routes; it surfaces for an explicit human decision). Discriminates
on *subject*, not tree location: e.g. a claude-klabauter install *script* → `engine`, the coordinator install
*skill* → `doctrine`.

### `coordinator_state_root [--central] [--subject <engine|doctrine>] [--artifact <path>]`

The single seam for resolving the state-root directory. **Python-native** — the retired bash
oracle (`coordinator-state-root.sh`) was deleted by the de-bash campaign; invoke
via claude-klabauter `coordinator/lib/coordinator-state-root.py` (or import `coordinator_state_root` from it,
now itself migrated to claude-klabauter — commit b644d5a9), never as a sourced shell function. Encodes the
full taxonomy, now subject-aware:

- `coordinator-state-root.py --central` (no subject/artifact) → `$(coordinator_claude_klabauter_root)/state` unconditionally
  (**backward-compat default — unchanged**; every existing `--central` caller still routes to claude-klabauter).
- `coordinator-state-root.py --central --subject doctrine` (or `--artifact <doctrine-path>`) →
  `$(coordinator_doe_root)/state` — doctrine-subject central state routes to the DoE plane. Fail-loud
  (no silent fallback to claude-klabauter) when `REPO_DOE_CLAUDE` is unresolvable; central-loop callers catch
  and WARN+skip.
- `coordinator-state-root.py --central --subject engine` (or `--artifact <engine-path>`) →
  `$(coordinator_claude_klabauter_root)/state`.
- `coordinator-state-root.py --central --artifact <cross-cutting-path>` → **fail-loud (exit 2)**; never
  auto-routes a two-plane artifact.
- `coordinator-state-root.py` (no flag) → `$(coordinator_claude_klabauter_root)/state` if the current git root IS the meta-repo
  (`~/.claude`); otherwise `$GIT_ROOT/state` (sibling repos keep their own state).

The meta-repo discriminator (`coordinator_is_meta_repo`) canonicalizes both sides (realpath before
comparison) and fails loud on an empty or unresolvable git root — never silently defaults.

> **Sequencing note — capability landed, live caller-switch pending.** The subject-aware
> routing above is the *mechanism* (W2.1–W2.3-shell, landed + tested). No central-loop caller passes
> `--subject`/`--artifact` yet, so doctrine central writes still land in claude-klabauter until the switch. The
> live flip is deliberately sequenced **after** the W3 migration populates the DoE plane and the DoE
> clone is fleet-wide — switching callers before then would WARN+skip (silently drop) doctrine writes
> on any machine without DoE cloned. The two named central-loop CLIs (`coordinator-lesson-promote`,
> `coordinator-queue-append`) are **Python with their own CLAUDE-KLABAUTER resolution** — they do not call this
> shell seam, so routing their doctrine writes to DoE needs a Python-side subject-router (post-W3).

**Central write target for any central-state artifact** (`coordinator-state-root.py` is
Claude-klabauter-resident post-b644d5a9; resolve `$REPO_CLAUDE_KLABAUTER` first):
```
$(python3 "$REPO_CLAUDE_KLABAUTER/coordinator/lib/coordinator-state-root.py" --central)/<artifact-path>
```

**Per-repo write target (meta-repo or sibling):**
```
$(python3 "$REPO_CLAUDE_KLABAUTER/coordinator/lib/coordinator-state-root.py")/<artifact-path>
```

---

## Rule for Artifact-Authoring Surfaces

Any surface that writes a session artifact MUST resolve its write-target through the seam.
The anti-pattern is hardcoding the path:

```sh
# WRONG — hardcodes the meta-repo as state home
echo "$data" > ~/.claude/state/improvement-queue/"$id".yaml

# CORRECT — routes through the seam (coordinator-state-root.py is claude-klabauter-resident post-b644d5a9)
CENTRAL_ROOT=$(python3 "$REPO_CLAUDE_KLABAUTER/coordinator/lib/coordinator-state-root.py" --central)
echo "$data" > "$CENTRAL_ROOT/improvement-queue/$id.yaml"
```

This applies to:
- claude-klabauter `coordinator-doc-new` (handoff, plan, cross-repo-memo scaffolders)
- `/handoff`, `/plan`, `/workday-complete`, `/workstream-complete` skills
- claude-klabauter `coordinator-lesson-promote`, `coordinator-queue-append`
- The `plan-persistence-check.py` PostToolUse hook (harness-native plan mode ExitPlanMode writes)
- Any new artifact-authoring surface added post-migration

**Graceful degradation:** central-loop entry points (claude-klabauter `coordinator-lesson-promote`,
`coordinator-queue-append --schema improvement-queue`) MUST NOT propagate a hard-error when
`CLAUDE_KLABAUTER_ROOT` is unresolvable on an un-migrated install. They emit a WARN + remediation message
and skip the central write with exit 0. The low-level `CLAUDE_KLABAUTER_ROOT` resolver may hard-error; its
callers in the central loop must catch and degrade gracefully.

---

## Surfaces That Deliberately Stay in `~/.claude`

> **DR-072 — durable machine-local state does not belong in `~/.claude`.** Before parking a
> new durable, per-machine value under `~/.claude` (a config file, a cache, a registry entry),
> read `docs/decisions/DR-072-durable-machine-local-coordinator-state-lives-in-settings-home-not-claude.md`
> and `docs/decisions/DR-071-durable-coordinator-root-anchor-settings-home-registry-doe-root-demoted-to-cache.md`.
> `~/.claude` is resettable/synced ground; the durable home is settings-home
> (`coordinator/templates/bin/coordinator-settings-home` — `_coordinator_settings_home()`), registry mechanics in
> `machine-local-registry.md`. This is the doctrine-decays-unless-greppable cross-ref that stops
> the recurrence DR-071/DR-072 fixed.

### Shared-Rendezvous Paths

A rendezvous path's *value* is inter-repo agreement on its literal string — processes in different
repos must resolve byte-identical directories to find each other. Moving one unilaterally fails
**silently**: the odd tenant out sees no peers and races them into OOM. Move only by coordinated
cross-repo flip through an env-var rung. DR-072 classifies these SHARED-RENDEZVOUS.

Live case: `<settings-home>/gpu-tenants/`, reached via `_default_registry_dir()` in both
`example-game-workbench-repo/gpu_sidecar/peers.py` and `project-rag/embed_sidecar/peers.py` — each
resolving settings-home itself, never importing a shared constant. The two repos are asymmetric on
the legacy leg, not a symmetric pair to copy: `project-rag/embed_sidecar/peers.py` retired its
`~/.claude/gpu-tenants/` union-read (2026-08-15; `_union_registry_dirs()` is now single-element),
while `example-game-workbench-repo/gpu_sidecar/peers.py` still defines `_legacy_registry_dir()` (`:190`)
and union-reads it in `_read_registry_dirs()` (`:286`, appended at `:310`). Neither repo writes the
legacy path, but a pre-flip entry left there is visible to example-game-repo and invisible to project-rag —
the one-sided-rendezvous hazard this class exists to name.

<!-- machine-local/, .coordinator-venv/, and bin/ live under ~/.coordinator-claude-settings/. .doe-root remains under ~/.claude only as a disposable regenerated mirror; the durable anchor is the settings-home registry key repos.doe_claude (DR-071/DR-072). Spec: docs/plans/2026-07-06-durable-substrate-to-settings-home.md -->

These surfaces are NOT subject to the placement law:
- Plugin source: `bin/`, `lib/`, `hooks/`, `skills/`, `agents/` — **DoE-resident** (resolved live via `--plugin-dir` from the DoE clone; NOT a `~/.claude`-resident surface in the current tooling shape — see § Taxonomy).
- Plans/research/problems: `docs/{plans,research,problems}/` in the DoE clone — the one home, whatever the deliverable edits (see § Plan Homes). NOT the meta-repo top-level `~/.claude/docs/plans/`, which moved to claude-klabauter.
- Wikis: `docs/wiki/` (both coordinator plugin and meta-repo)
- Decisions: `docs/decisions/`
- Settings and config: `settings.json`, `.mcp.json`, `CLAUDE.md`, the (now-removed) `the (now-removed) meta-repo local-doctrine file`
- `docs/README.md` (meta-repo master index — stays; updated to point cross-repo to claude-klabauter-resident plans)
- **`.doe-root`** — **a disposable, non-authoritative mirror under `~/.claude` (DR-071/DR-072).** The durable, authoritative coordinator-root anchor is now the settings-home machine-local registry (`~/.coordinator-claude-settings/machine-local/registry.local.toml`, key `repos.doe_claude`), mirroring the sibling `.claude-klabauter-root` shape — see `docs/decisions/DR-071-durable-coordinator-root-anchor-settings-home-registry-doe-root-demoted-to-cache.md`. `~/.claude/.doe-root` remains as a regenerated, untracked cache (never a committed per-machine value); it is downstream of the registry, not the source of truth. → `docs/decisions/DR-072-durable-machine-local-coordinator-state-lives-in-settings-home-not-claude.md`; claude-klabauter `coordinator/bin/coordinator-settings-home` (the settings-home resolution seam).
- **`~/.claude/setup/`** — coordinator-written, coordinator-read, authoritative, durable, and
  deliberately RETAINED under `~/.claude` (DR-072 RETAINED-UNDER-CLAUDE): nothing reads `setup/` from settings-home at runtime,
  and migrating it would create two diverging copies the fail-loud divergent-file guard then
  blocks. Cited on all three converging authorities, not one — a single-source citation once
  produced a wiki-vs-wiki disagreement: `agent-install-contract.md:795-804`, this file's own
  Relocated-surfaces note at `:294` below, and `machine-local-registry.md:249` and `:746`.

**Net effect: `~/.claude` carries no *unintentional* durable coordinator-owned residual** — the
intentional ones are enumerated above (`setup/` chief among them), each retained on a named
authority, and DR-072 is what classifies them as such.

**Surfaces that RELOCATED to the coordinator settings home (`~/.coordinator-claude-settings/`):**

The plan `docs/plans/2026-07-06-durable-substrate-to-settings-home.md` moved the full coordinator durable substrate out of `~/.claude` to make it clone-mutation-independent. The precise home location:

```
COORDINATOR_SETTINGS_HOME env var   (XDG / sandbox override — see machine-local-registry.md §4e)
  else ${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings
```

Relocated surfaces:

| Surface | Old `~/.claude/…` location | New `~/.coordinator-claude-settings/…` location | Transitional compat |
|---|---|---|---|
| `machine-local/` | `~/.claude/machine-local/` | `~/.coordinator-claude-settings/machine-local/` | `~/.claude/machine-local` is a realpath-symlink to the settings home; consumers that read via the old path continue to resolve through it. Removed at phase-2 gated tail (all 5 consumers confirmed). |
| `.coordinator-venv/` | `~/.claude/.coordinator-venv/` | `~/.coordinator-claude-settings/.coordinator-venv/` | Rebuilt (never copied) by `install-substrate.py` (C10a) via the native venv builder (`coordinator_core.install.ensure_venv`, claude-klabauter-resident); legacy venv removed only after rebuild + health probe both confirm healthy. |
| `bin/` resolver family | `~/.claude/bin/machine-local` etc. | `~/.coordinator-claude-settings/bin/` | **Phase-2 gated tail: cleared** (owns-zero retirement, `docs/plans/2026-07-24-coordinator-owns-zero-claude-bin.md`, Gate 6) — the compat-mirror producer (`substrate.py`'s Step 3c-compat) is deleted; a fresh install writes forwarders to settings-home ONLY, minting nothing into `~/.claude/bin`. Coordinator does not *write* to that path. Pre-existing installs still have real files under `~/.claude/bin` until an uninstall/reinstall sweeps them (leg #7, individually, never `rm -rf`) — a fresh install resolves through settings-home only, but pre-existing installs may still fall back to `~/.claude/bin` as a last-resort read until swept (Gate 1's `bare_forwarder.py` settings-home-first rung and Gate 3's soft-fallback rungs deliberately retain that fallback by design, AC2/AC4). |
| `settings-manifest.md` | `~/.claude/settings-manifest.md` | `~/.coordinator-claude-settings/settings-manifest.md` | None needed. |

**`setup/` is NOT in this table — it never relocated.** `setup/` is intentionally excluded from the settings-home migration: nothing reads `setup/` from the settings home at runtime (coordinator continues to read `~/.claude/setup/`), and the percolation step in `install-substrate.py` writes the canonical copy there. Migrating it would create two diverging locations that the fail-loud divergent-file guard then blocks on every re-run.

**The transitional compat window is a first-class design primitive, not a footnote.** Coordinator cuts over first and deletes last. The compat layer (symlink + retained forwarders) is removed only at the single gated tail in phase-2, triggered when all 5 consumers (example-game-repo, project-rag, project-rag-ue-addon, cockpit, claude-klabauter) confirm they have migrated off the legacy surfaces. `~/.claude/machine-local` remains gated open — its own phase-2 tail is a separate, still-pending decision, untouched by the `bin/` retirement below. The `bin/` family's gate is cleared (see the table row above): all 5 consumers are confirmed and repointed settings-home-first, and `~/.claude/bin/machine-local` is not functional on a fresh install (the compat forwarder is not minted).

Moving the session-boot and harness surfaces listed above (wikis, decisions, settings, config) breaks
orientation or the harness config contract. Plugin source is DoE-resident — claude-klabauter `coordinator/bin/publish.py` now sources
from the allowlisted plugin subpath inside the DoE clone (DoE→OSS percolation), so plugin-source
location is not a constraint on the items above.

---

## Fleet Producer Contract — Per-Repo Emission, Live-Remote Horizon, Tier A/B Observation

> **Purpose.** State-placement law governs where an artifact lives on disk *within* a repo. This
> section governs the orthogonal question: how a repo's work-state is *emitted* to the fleet-wide
> observation surface (cockpit). Same "no single consolidation point" instinct as the rest of this
> wiki, applied one layer up — from within-repo taxonomy to across-repo topology.
>
> Consumer-side canonical record: `example-cockpit-repo/docs/decisions/2026-07-07-cockpit-live-remote-per-repo-observation-model.md`.
> This section is the producer-side doctrine that record's "collaborating-repos contract" obligates.

### The three coupled producer requirements

Breaking any one of these breaks the premise — they are coupled, not independently satisfiable:

1. **Per-repo, decentralized emission.** Each repo emits its own work-state rooted at its own
   `state/`. There is no single consolidation point. A consolidation point makes one producer a
   fleet-wide single point of failure, and it blinds observation of every repo that is not
   co-located with that consolidation point.
2. **Live + remotely readable (HORIZON, not now).** Each repo *publishes* its per-repo state to a
   shared live sink (Firestore, per cockpit's Firebase direction), keyed per repo, read remotely
   and continuously — not local files read off disk, not a manually-refreshed snapshot.
3. **Aggregate keyed per repo.** The SOURCE of the fleet-wide view must be per-repo; consumers
   aggregate on the read side. A per-repo source with read-side aggregation is what makes a
   non-co-located repo observable at all.

### `service topology ⊥ emission topology`

A single global multiplexing **service** (one daemon ingesting a fleet's worth of emission — this
is correct and desired) does **not** imply a single central **emission** source. Service topology
and emission topology are orthogonal axes; collapsing them onto one another is the exact defect
this contract exists to prevent. **The meta-repo (`~/.claude`) is NOT the fleet root.** This
principle is the doctrine-of-record here — there is no competing DoE decision-record; the
code-level `topology.md § AC-1` reclassification is claude-klabauter's own artifact, folded into this
contract via the return memo referenced above.

### Brittleness triad — reject all three (same anti-pattern)

(a) a single consolidation location; (b) local-file-only aggregation used as the *permanent,
fleet-wide* mechanism; (c) manual or stale snapshot upload. All three collapse per-repo emission
back onto one point of failure — the shape differs, the defect is identical. None may stand as
the fleet's source of truth.

### Tier A / Tier B observation model

- **Tier A — instrumented repos** (run coordinator + claude-klabauter): owe rich Tier-A emission — the full
  handoff/goal/rollup/lineage/review-trail/backlog ingest this contract's own repos already emit.
- **Tier B — uninstrumented repos**: no rich emission ingest, but never nothing — GitHub census
  (branches, PRs, commits, ahead/behind) is the degraded-but-real floor every feature falls back
  to when Tier-A emission is unavailable.

Every feature built against fleet observation degrades gracefully to Tier B rather than assuming
Tier-A emission exists universally.

### Time-calibration — shape is binding now, transport is forward-compatible horizon

**Do not over-build.** The per-repo emission **shape and keying** (requirements 1 and 3 above) are
binding **now** — build every new emission surface forward-compatibly against them. The **live-remote
publish transport** (requirement 2 — the Firestore/live-sink leg) feeds the **SOONER** cloud
observatory / information-plane horizon (cockpit's own framing: "SOONER, on the cards") — it is
**not** the ~6–12-month **cloud action ops** horizon (running agentic sessions in the cloud), which
is a wholly different and harder problem this contract does not touch. Do not tag the publish
transport with the 6–12-month estimate; that label belongs exclusively to cloud action ops.

Near-term **local** per-repo emission ingest (a repo's own `state/` read directly, on the same
machine, by an instrumented consumer) is **Tier-A-local** and correct today — it is a legitimate
stepping stone, not an instance of the forbidden brittleness triad, precisely because the source
stays per-repo even though the read is still local.

**Producers do NOT need to build Firestore/live-sink publishing today.** This contract states the
shape as binding and the transport as a forward-compatible horizon — it is not an instruction to
implement live-remote publishing in this session or this plan.

### Verified-current mechanism and the Ask A#3 seam record

The per-repo emission this contract requires is not aspirational — it is already the verified
mechanism on disk, via two seams:

- **`--subject`/sibling routing** (claude-klabauter `coordinator/lib/coordinator-state-root.py`, a CLI trampoline
  over claude-klabauter's `coordinator_core.state_root.coordinator_state_root`, Rules 1–5) — the
  subject-aware `coordinator_state_root` resolution documented in § Resolver Seam above.
- **Strangler PWD `repo_root` resolution** (the strangler-facade seam) — resolves
  `repo_root` from `$PWD` via `git -C "$PWD" rev-parse --show-toplevel`, which is already per-repo
  by construction: whichever repo the shell is sitting in is the repo that gets resolved.

**Ask A#3 record — frame accurately, not flatly "false."** Ask A#3 claimed "the seam returns empty
and falls back to `~/.claude/state`." That claim is **false on the DoE *shell* seam when sourced**
— a sourced invocation resolves per-repo correctly, as designed. It is, however, **true on
direct-exec** (invoking the script with no exec entrypoint, rather than sourcing it) — the seam
does return empty in that mode and a caller could fall through to a stale default. This is a real,
DoE-owned latent robustness bug, tracked at low priority. State both halves precisely: a reader
must not conclude per-repo emission is unshipped work (it is shipped and verified), and must not
dismiss the direct-exec gap as non-existent (it is real, just narrow).

### Born-compliant-by-default

Future instrumented producers are **born compliant**: per-repo emission is the default at the
producer-side emission convention, not a bilateral negotiation between each new producer and
Cockpit. A new repo that stands up coordinator + claude-klabauter inherits per-repo emission automatically
— it does not need to separately agree terms with cockpit before its emission is fleet-observable.
The norm lives here, at the producer-side convention, precisely so that negotiation never needs to
happen again per-repo.

### Cockpit, framed precisely

**Cockpit *is* a local application** — the local system of action: a desktop cockpit,
harness-for-a-harness wrapping Claude Code, authoring and resolving work, not merely watching it.
**Cockpit *has* a hosted web observation plane** — the cloud information surface that renders the
fleet from anywhere. Local = action, cloud = information. **"Cockpit is a web app" is a category
error** — do not write or repeat that framing. Canonical consumer-side record:
`example-cockpit-repo/docs/decisions/2026-07-07-cockpit-live-remote-per-repo-observation-model.md`.

### Backlog and goal shape — sharded, not consolidated

Backlog and goal emission are **per-repo SHARDED, not consolidated**: each repo emits only its own
shard (its own backlog items, its own goal state), never a fleet-wide roll-up. Consumers aggregate
those shards read-side. State this explicitly so the consolidated-census anti-pattern — one repo's
emission accidentally becoming the fleet's backlog-of-record — cannot recur.

### Born-compliant onboarding — the emit-hold sentinel

A new producer onboarding into per-repo emission does so **with the emit-hold sentinel already in
place**: onboarding places the initial `cockpit-revendor-pending-<ver>` sentinel automatically, and
the producer does **not** emit *unheld* until its consumers have confirmed ingest. This is the
producer-side analog of the consumer-side register-before-reliance obligation in
`emission-conformance-contract.md`'s Consumer-Tolerance Ledger: just as a consumer must register
its tolerance before the fleet can rely on non-holding for it, a producer must hold before it emits
unheld, so the two sides of the contract close symmetrically.

### Artifact class — strategic self-description

> **This is an EXTENSION of the contract above, not a new invariant.** Same three coupled producer
> requirements, same Tier A/B degradation, same time-calibration — applied to a new artifact class.
> Full standard: `strategic-self-description-standard.md`. Schema:
> `coordinator/schemas/strategic-self-description.schema.json`.
> Spec backlink: `docs/plans/2026-07-11-strategic-self-description-standard.md § DEC-1`.

A repo's strategic self-description — mission, lifecycle phase, positioning, call-to-action — is a
**new artifact class under this same Fleet Producer Contract**, not a new topology:

- **Path: `state/strategic/self-description.yaml` (per-repo).** Rooted at each repo's own `state/`,
  same as every other class this contract governs — see Taxonomy row "Per-repo work state" above.
  Curated (human-authored) provenance does NOT make it a `docs/` artifact; the Fleet Producer
  Contract's emission-surface rule applies regardless of how much of the content is hand-ratified
  vs. machine-derived.
- **Per-repo-emitted, harvested read-side, never consolidated.** Requirement 1 (no single
  consolidation point) applies exactly as written above: each repo emits its own
  `state/strategic/self-description.yaml`; consumers (cockpit's Strategic board first) aggregate N
  per-repo paths read-side. No fleet-wide file ever authors or lands strategic content for another
  repo — the same brittleness triad this contract rejects elsewhere applies here unchanged.
- **Tier A/B graceful degradation.** A Tier-A repo (coordinator + claude-klabauter) emits the full artifact
  with per-field provenance; a Tier-B repo has no self-description to harvest at all — that is the
  expected degraded floor (§ Tier A / Tier B observation model), not an error state for a consumer
  to special-case.
- **Shape-binding-now, transport-horizon** (§ Time-calibration, unchanged). The artifact's shape and
  per-repo keying are binding today; live-remote publish of this artifact rides the same
  Firestore/live-sink horizon as every other emission class here — building that transport is
  explicitly out of scope for the producer/schema work that defines this class.

Provenance model (curated/generated/asserted), CTA validate-or-degrade shape, and the
generated-draft → human-ratify → curated reconciliation seam are documented in full in
`strategic-self-description-standard.md` — this section states only the placement + topology facts
that fall under the Fleet Producer Contract proper.

---

## Cross-References

- `machine-local-registry.md` — `CLAUDE_KLABAUTER_ROOT` resolution and the §4b/§4c ladder that `machine-local get` encapsulates
- `coordinator/docs/wiki/coordinator-tripwires/` — tripwires that enforce placement law at the hook layer
- `docs/plans/2026-07-03-stop-the-rot-claude-klabauter-state-home-placement.md` — full plan: resolver seam (C1/C2), scripted repoint (C3/C4), migration (C6), placement law (C10)
- `emission-conformance-contract.md` — the Consumer-Tolerance Ledger this contract's producer-side obligations are symmetric with
- `example-cockpit-repo/docs/decisions/2026-07-07-cockpit-live-remote-per-repo-observation-model.md` — canonical consumer-side record for § Fleet Producer Contract
