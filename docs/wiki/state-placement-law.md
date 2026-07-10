---
title: "State placement law — where session-authored artifacts live"
created: 2026-07-03
status: active
spec_backlink: docs/plans/2026-07-03-stop-the-rot-example-orchestration-hub-state-home-placement.md § AC7
---

# State Placement Law — Where Session-Authored Artifacts Live

> **Purpose (spec backlink: `docs/plans/2026-07-03-stop-the-rot-example-orchestration-hub-state-home-placement.md § AC7`).**
> Durable rule for where every session-authored artifact lands after the example-orchestration-hub state-home
> migration. This wiki is the SSOT for artifact-authoring surfaces (`coordinator-doc-new`,
> `/handoff`, `/plan`, hooks, CLI tools) to resolve their write-target. Never hardcode
> `~/.claude/state` as a central-state write target — route through the seam.

---

## Why This Exists — The Stop-the-Rot Rationale

Before this migration, `~/.claude` conflated three distinct concerns: the Claude Code harness
home, the plugin source tree (OSS-published), and the coordinator's executing working data
(`state/`, `docs/{plans,research,problems}`). Every new session layered more work-state into
`~/.claude`, compounding structural rot. The fix: **relocate working data to the example-orchestration-hub sibling
repo** and route every artifact-authoring surface through a resolver seam, so future pickups
automatically land in the right place.

The durable value: separation of concerns (harness home ≠ working data home), a regression guard
against permission-trip recurrence, and enabling the engine-absorbs-shell trajectory.

---

## Taxonomy — What Goes Where

| Artifact class | Post-migration home | Notes |
|---|---|---|
| **Central/global state** (`state/lessons/`, `state/trackers/`, `state/queues/`, `state/ledgers/`, `state/memos/`, `state/scratch/`, `state/debt-backlog/`, `state/bug-backlog/`, `state/improvement-queue/`, `state/lessons-outbox/`) | **example-orchestration-hub — unconditionally** | Central state for all coordinator-installed repos. `EXAMPLE_ORCHESTRATION_HUB_ROOT` is the root; `$(coordinator_state_root --central)/` is the write target. *Mechanism lag: the subject-classification seam rewire is pending the doe-authoring-repo spinoff — `coordinator_state_root --central` routes here unconditionally until that spinoff lands (see INTERIM note in § Plan Homes).* |
| **Per-repo work state** (`state/` under a sibling project). Includes session-scoped `state/handoffs/`, `state/orientation_cache.md`, `state/review-trail/`, `state/week-changelog/`, `state/audits/`, `state/recovery/` — resolved via `coordinator_state_root` (no flag), which for the meta-repo still redirects to example-orchestration-hub but for a sibling stays local. | **Unchanged for siblings** — `$GIT_ROOT/state/` | example-os-repo, project-rag, example-game-repo, etc. all keep writing their own `state/`. Only when `$GIT_ROOT` IS the meta-repo (`~/.claude`) does per-repo state redirect to example-orchestration-hub. **Exception — install-baton rendezvous:** the shared `state/handoffs/` rendezvous that a downstream repo's installer seeds an install/orient `kind: spinoff` baton into is NOT this per-repo `$GIT_ROOT/state/` and NOT row-36 central example-orchestration-hub state — it is machine-shared install substrate at `$(coordinator-settings-home)/state/handoffs/`, distinct from both. See the dedicated **Install-baton rendezvous** row below. |
| **Install-baton rendezvous** (shared install/orient batons — `kind: spinoff` batons carrying `install_chain_order:` or an orient-leg discriminator, seeded by a conforming repo's installer or coordinator's own onboarding flow) | **`$(coordinator-settings-home)/state/handoffs/`** — machine-shared, per-machine install substrate | Distinct from per-repo `state/handoffs/` (row above — session-scoped, `$GIT_ROOT`-resolved) and from central example-orchestration-hub state (row above — meta-repo session state). Mints the same `<settings-home>` root prefix as the C9 (`docs/plans/2026-07-06-durable-substrate-to-settings-home.md`) `<settings-home>/<repo-id>/` install-status-ledger / chain-walk-visited-set precedent — both are per-machine install substrate, a plane distinct from example-orchestration-hub's meta-repo session state — but the rendezvous is NOT scoped under `<settings-home>/<repo-id>/` (it is machine-shared, not per-repo-id). See `agent-install-contract.md` § The rendezvous and § Relocation boundary. Compat: legacy `~/.claude/state/handoffs/` read as fallback during the transition window. |
| **Meta-repo operational docs**: top-level `~/.claude/docs/{plans,research,problems}/` whose deliverable does NOT edit the plugin source tree | **example-orchestration-hub** | Physically moved at migration (not auto-resolved); new artifacts authored via seam-routed surfaces land in example-orchestration-hub. **Carve-out:** a plan whose `scope:` edits `plugins/coordinator/**` is a *plugin-development* plan and stays in the plugin tree — see § Plan Homes below. |
| **Plugin source** (`bin/`, `lib/`, `hooks/`, `skills/`, `agents/`) | **DoE clone — `coordinator/` tree, resolved live via `--plugin-dir`** | Current tooling shape: coordinator plugin source is resolved live from the external DoE clone (`$REPO_DOE_CLAUDE/coordinator/`) via Claude Code `--plugin-dir`; the `~/.claude/plugins/coordinator-claude/` marketplace copy is retired/vestigial. OSS publish (`publish.sh`) sources from the allowlisted plugin subpath inside the DoE clone (DoE→OSS percolation). |
| **Wikis** (`docs/wiki/`) | **DoE clone — `coordinator/docs/wiki/`, resolved live via `--plugin-dir`** | Same coordinator tree as plugin source (`$REPO_DOE_CLAUDE/coordinator/docs/wiki/`); OSS-published Tier-1 orientation surface — moves would break publish + session boot. |
| **Decisions** (`docs/decisions/`) | **`~/.claude/docs/decisions/` — unchanged** | Tier-1 orientation; stays in meta-repo. |
| **`archive/`** | **example-orchestration-hub** | Session-init archives `state/handoffs → archive/handoffs` within the state-repo; example-orchestration-hub holds `archive/` alongside `state/`. |

**Summary rule:** working data moves to example-orchestration-hub; the coordinator plugin source is DoE-resident (resolved live via `--plugin-dir`); other doctrine surfaces (decisions, settings, harness config) remain in `~/.claude`.

> **`docs/wiki/` is source-only — the naming-collision trap.** The DoE-claude clone is the coordinator doctrine source of truth; `~/.claude` is the live-install and post-cutover carries exactly one coordinator-owned artifact (`.doe-root` — see `coordinator-installer-shape.md`). Both trees are named "coordinator-claude"; they are not the same tree. A bare `coordinator/docs/wiki/<name>.md` citation resolves against the DoE clone only — grepping it under `~/.claude` finds nothing, and that absence is NOT evidence the doctrine doesn't exist. Cross-repo citations must repo-qualify to avoid a false stand-down — see `cross-repo-citation-conventions.md § When to qualify`.

> **Negative-spec (soft-seam, DR-210):** The authoritative-mutation subset — terminal work-state write + lifecycle stamp (e.g. `cross-repo-memo`'s emit-and-stamp op) — is a strangler candidate that may later relocate to example-orchestration-hub ops without violating this placement law.

---

## Residency Is Not Ownership

A plan, DR, or doc living in example-orchestration-hub records only that **example-orchestration-hub is coordinator's central
working-data store** — it makes NO claim about who *owns* or *executes* the work. Ownership is
set by the tri-plane boundary (`example-orchestration-hub-repo/docs/decisions/2026-07-03-tri-plane-ownership-boundary.md`):
*meaning* (artifact-shape-contract + skills) → coordinator-claude; *emission-write engine* → example-orchestration-hub;
*durable store* → rag. A plan states its own ownership in its ownership-boundary table; **never
infer ownership from the file's on-disk location.** (2026-07-04: a plan editing 100%
coordinator-plugin surfaces sat in `example-orchestration-hub/docs/plans/` and read as "example-orchestration-hub's work" — it is not.
The file is *stored* there; the work is coordinator's.)

**Fallback for artifacts lacking an ownership-boundary table** (archive/, queues, review-trail,
lessons, and most legacy backfill): ownership follows the **same subject-matter axis** — is the
artifact ABOUT engine internals (coordinator_core, pcore, resident-service) or ABOUT doctrine
(skills, hooks, ceremonies, install surfaces)? The axis that decides *home* also decides *ownership*
for un-tabled artifacts. Location remains non-authoritative; subject-matter is the inference key.

## Plan Homes — Two Locations, One Discriminator

> *Supersedes stop-the-rot § AC7's plans-slice for plugin-development plans. The § Why This Exists
> "working data moves to example-orchestration-hub" summary rule now applies only to the operational/engine-subject slice.*

> **INTERIM (2026-07-04) — pending the DoE authoring repo.** The `~/.claude` plugin-tree destination
> below is the home *only because* the correct end-state — a dedicated **DoE authoring repo** — does
> not exist yet. The ratified direction is the **subject-matter axis**: *engine-subject* working-data
> (`coordinator_core/**`, pcore, install-chain node, MCP/resident-service research) → example-orchestration-hub;
> *all doctrine-subject* working-data (plans/handoffs/lessons/review-trail/queues/archive *about*
> skills, hooks, agents, ceremonies, install surfaces) → the DoE plane. **Scoped claim — two tiers:**
> (1) **Manually-placed** doctrine artifacts (plans/research/problems routed by the EM/human using
> the discriminator below) stop routing to example-orchestration-hub NOW — they land in the plugin tree per the rule below.
> (2) **Seam-routed central-state classes** (`state/lessons/`, queues, review-trail via
> `coordinator_state_root --central`) STILL route to example-orchestration-hub — Taxonomy row-1's unconditional routing
> above remains mechanically accurate for those classes until the spinoff rewires the seam.
> When the DoE repo lands (spinoff in flight;
> consult `cross-repo/inbox/2026-07-04-example-orchestration-hub-over-migration-artifact-home.md`), this destination moves
> from the plugin tree to the DoE repo and the rule generalizes past plans to every working-data class.
> The durable half — **§ Residency Is Not Ownership** above — holds regardless of where the files land.
> Full diagnosis: `example-orchestration-hub-repo:docs/research/2026-07-04-example-orchestration-hub-over-migration-artifact-home-split.md`.

`docs/plans/` (and `docs/research/`, `docs/problems/`) resolves to **two** homes, not one. The
discriminator is a single question: **is this artifact's deliverable ABOUT coordinator doctrine?**
That means: does it edit coordinator plugin source (`plugins/coordinator/**`) OR
any meta-repo doctrine surface (`CLAUDE.md`, `CLAUDE.local.md`, `docs/decisions/`, `docs/wiki/`)?

A `scope:` entry under `plugins/coordinator/**` is a sufficient fast-path YES —
but the definition is **subject-matter, not tree-location**. A plan whose deliverable edits `CLAUDE.md`
or `docs/decisions/` is doctrine-plane even if its `scope:` never names the plugin tree.

| Answer | Home | Rationale |
|---|---|---|
| **Yes — plugin-development plan** (deliverable modifies coordinator plugin source: skills, `bin/`, `lib/`, `hooks/`, `agents/`, `cockpit-contract/`, `artifact-shape-contract/`, `docs/wiki/`) | **`coordinator/docs/plans/`** in the DoE clone (resolved live via `--plugin-dir`) | It IS the plugin's development history; it travels with the plugin source (now DoE-resident — see § Taxonomy) and is NOT subject to the example-orchestration-hub migration. (exec-summary, the fleet-contract-landing plan, + ~115 others.) |
| **No — meta-repo operational plan** (fleet coordination, meta-repo infra; nothing under `plugins/`) | **example-orchestration-hub** (`$(coordinator_state_root --central)`-resident `docs/plans/`) | Genuine meta-repo working data; the migration target. The now-empty `~/.claude/docs/plans/` is this class. |

**Cross-cutting plans (edits BOTH doctrine and engine surfaces):** the plane that OWNS the changed
contract or doctrine wins. Contracts and artifact-shape definitions live in coordinator per the
tri-plane DR (`example-orchestration-hub-repo:docs/decisions/2026-07-03-tri-plane-ownership-boundary.md § Vendored-Pin
Consumer`). A predominantly-engine plan that only incidentally touches a doctrine surface (e.g., one
hook file) stays engine-plane; a plan that *defines* a contract or skill stays doctrine-plane even if
it names engine emit operations.

**This is the rule the exec-summary relocation established (PM-ratified 2026-07-03):** exec-summary's
plan was pulled *out* of example-orchestration-hub *into* the plugin tree precisely because its deliverable is plugin
skills/hooks. Apply the same test to every plan — location follows *what the plan edits*, not which
session happened to author it.

**`docs/research/` and `docs/problems/` — no `scope:` field fallback:** research and problem artifacts
routinely carry no `scope:` list, so the discriminator's mechanical grep test cannot run on them.
Apply subject-matter judgment instead: is this artifact ABOUT **engine internals** (`coordinator_core`,
pcore, MCP/resident-service, install-chain node) → example-orchestration-hub; or ABOUT **doctrine** (skills, hooks,
agents, ceremonies, install surfaces, the coordinator plugin) → doctrine-plane (plugin tree INTERIM,
DoE repo when it lands)?

---

## Resolver Seam — The Single Write-Target Authority

Two primitives form the seam. Every state-writing surface routes through one of them — never
open-codes a path.

### `EXAMPLE_ORCHESTRATION_HUB_ROOT`

The example-orchestration-hub repo root. Resolution chain (outer only — inner four-rung autodiscovery is
encapsulated inside `machine-local get`):

1. `$EXAMPLE_ORCHESTRATION_HUB_ROOT` env var if already set (gated by `[[ -z "${EXAMPLE_ORCHESTRATION_HUB_ROOT:-}" ]]` per
   `machine-local-registry.md §4b`).
2. `machine-local get repos.example_orchestration_hub_repo` — the registry lookup; internally runs the §4c
   four-rung discovery ladder (explicit flag → OS-keyed search-roots + marker autodiscovery →
   tracked exceptions → `.local.toml` fallback). Do NOT re-implement the inner rungs as outer
   steps; `machine-local-registry.md §4c` is the SSOT.
3. Hard-error + remediation message if both are unresolvable.

### `REPO_DOE_CLAUDE`

The DoE-claude authoring-repo root — the *doctrine plane*, sibling to `EXAMPLE_ORCHESTRATION_HUB_ROOT` (the *engine
plane*). Resolver primitive `coordinator_doe_root` (`lib/coordinator-doe-root.sh`), same outer chain
shape as `EXAMPLE_ORCHESTRATION_HUB_ROOT`: `$REPO_DOE_CLAUDE` env → `machine-local get repos.doe_claude` → hard-error +
remediation. Callers in the central write loop wrap it and degrade (WARN + skip); the primitive
itself fails loud. Introduced by the DoE-authoring-repo seam rewire (W2.1).

### `coordinator_artifact_subject <path>`

Subject-matter classifier (`lib/coordinator-artifact-subject.sh`, W2.2) — the routing key for
subject-aware placement. Prints one token: `engine` | `doctrine` | `cross-cutting`. Exit 0 for a
confident engine/doctrine call; **exit 2 + stderr for cross-cutting** (detect-then-fail-loud — a
genuinely two-plane artifact never auto-routes; it surfaces for an explicit human decision). Discriminates
on *subject*, not tree location: e.g. a example-orchestration-hub install *script* → `engine`, the coordinator install
*skill* → `doctrine`.

### `coordinator_state_root [--central] [--subject <engine|doctrine>] [--artifact <path>]`

The single seam for resolving the state-root directory. Encodes the full taxonomy, now subject-aware:

- `coordinator_state_root --central` (no subject/artifact) → `$(coordinator_example_orchestration_hub_root)/state` unconditionally
  (**backward-compat default — unchanged**; every existing `--central` caller still routes to example-orchestration-hub).
- `coordinator_state_root --central --subject doctrine` (or `--artifact <doctrine-path>`) →
  `$(coordinator_doe_root)/state` — doctrine-subject central state routes to the DoE plane. Fail-loud
  (no silent fallback to example-orchestration-hub) when `REPO_DOE_CLAUDE` is unresolvable; central-loop callers catch
  and WARN+skip.
- `coordinator_state_root --central --subject engine` (or `--artifact <engine-path>`) →
  `$(coordinator_example_orchestration_hub_root)/state`.
- `coordinator_state_root --central --artifact <cross-cutting-path>` → **fail-loud (exit 2)**; never
  auto-routes a two-plane artifact.
- `coordinator_state_root` (no flag) → `$(coordinator_example_orchestration_hub_root)/state` if the current git root IS the meta-repo
  (`~/.claude`); otherwise `$GIT_ROOT/state` (sibling repos keep their own state).

The meta-repo discriminator (`coordinator_is_meta_repo`) canonicalizes both sides (realpath before
comparison) and fails loud on an empty or unresolvable git root — never silently defaults.

> **Sequencing note (2026-07-04) — capability landed, live caller-switch pending.** The subject-aware
> routing above is the *mechanism* (W2.1–W2.3-shell, landed + tested). No central-loop caller passes
> `--subject`/`--artifact` yet, so doctrine central writes still land in example-orchestration-hub until the switch. The
> live flip is deliberately sequenced **after** the W3 migration populates the DoE plane and the DoE
> clone is fleet-wide — switching callers before then would WARN+skip (silently drop) doctrine writes
> on any machine without DoE cloned. The two named central-loop CLIs (`coordinator-lesson-promote`,
> `coordinator-queue-append`) are **Python with their own MAKIMA resolution** — they do not call this
> shell seam, so routing their doctrine writes to DoE needs a Python-side subject-router (post-W3).

**Central write target for any central-state artifact:**
```
$(coordinator_state_root --central)/<artifact-path>
```

**Per-repo write target (meta-repo or sibling):**
```
$(coordinator_state_root)/<artifact-path>
```

---

## Rule for Artifact-Authoring Surfaces

Any surface that writes a session artifact MUST resolve its write-target through the seam.
The anti-pattern is hardcoding the path:

```sh
# WRONG — hardcodes the meta-repo as state home
echo "$data" > ~/.claude/state/improvement-queue/"$id".yaml

# CORRECT — routes through the seam
CENTRAL_ROOT=$(coordinator_state_root --central)
echo "$data" > "$CENTRAL_ROOT/improvement-queue/$id.yaml"
```

This applies to:
- `coordinator-doc-new` (handoff, plan, cross-repo-memo scaffolders)
- `/handoff`, `/plan`, `/workday-complete`, `/workstream-complete` skills
- `coordinator-lesson-promote`, `coordinator-queue-append`
- The `plan-persistence-check.sh` PostToolUse hook (harness-native plan mode ExitPlanMode writes)
- Any new artifact-authoring surface added post-migration

**Graceful degradation:** central-loop entry points (`coordinator-lesson-promote`,
`coordinator-queue-append --schema improvement-queue`) MUST NOT propagate a hard-error when
`EXAMPLE_ORCHESTRATION_HUB_ROOT` is unresolvable on an un-migrated install. They emit a WARN + remediation message
and skip the central write with exit 0. The low-level `EXAMPLE_ORCHESTRATION_HUB_ROOT` resolver may hard-error; its
callers in the central loop must catch and degrade gracefully.

---

## Surfaces That Deliberately Stay in `~/.claude`

<!-- update-prior-art rewrite (2026-07-06): machine-local/, coordinator-whoami/, .coordinator-venv/, and bin/ have RELOCATED to ~/.coordinator-claude-settings/. Only .doe-root remains as the single coordinator-owned ~/.claude residual. PM-ratified 2026-07-06. Spec: docs/plans/2026-07-06-durable-substrate-to-settings-home.md -->

These surfaces are NOT subject to the placement law:
- Plugin source: `bin/`, `lib/`, `hooks/`, `skills/`, `agents/` — **DoE-resident** (resolved live via `--plugin-dir` from the DoE clone; NOT a `~/.claude`-resident surface in the current tooling shape — see § Taxonomy).
- Plugin-development plans/research: `coordinator/docs/{plans,research,problems}/` in the DoE clone — plans whose deliverable edits the plugin source (see § Plan Homes). NOT the meta-repo top-level `~/.claude/docs/plans/`, which moved to example-orchestration-hub.
- Wikis: `docs/wiki/` (both coordinator plugin and meta-repo)
- Decisions: `docs/decisions/`
- Settings and config: `settings.json`, `.mcp.json`, `CLAUDE.md`, `CLAUDE.local.md`
- `docs/README.md` (meta-repo master index — stays; updated to point cross-repo to example-orchestration-hub-resident plans)
- **`.doe-root`** — the ONLY intentional coordinator-owned `~/.claude` residual: a read-only one-line bootstrap pointer written by `install-substrate.sh` and read by `resolve-coordinator-clone.sh` rung-1 on cold-start. PM-ratified 2026-07-06. Everything else coordinator previously parked in `~/.claude` has relocated — see below.

**Surfaces that RELOCATED to the coordinator settings home (`~/.coordinator-claude-settings/`) — 2026-07-06:**

The plan `docs/plans/2026-07-06-durable-substrate-to-settings-home.md` moved the full coordinator durable substrate out of `~/.claude` to make it clone-mutation-independent. The precise home location:

```
COORDINATOR_SETTINGS_HOME env var   (XDG / sandbox override — see machine-local-registry.md §4e)
  else ${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings
```

Relocated surfaces:

| Surface | Old `~/.claude/…` location | New `~/.coordinator-claude-settings/…` location | Transitional compat |
|---|---|---|---|
| `machine-local/` | `~/.claude/machine-local/` | `~/.coordinator-claude-settings/machine-local/` | `~/.claude/machine-local` is a realpath-symlink to the settings home; consumers that read via the old path continue to resolve through it. Removed at phase-2 gated tail (all 5 consumers confirmed). |
| `coordinator-whoami/` | `~/.claude/coordinator-whoami/` | `~/.coordinator-claude-settings/coordinator-whoami/` | Copied by `install-substrate.sh` (C10a); resolved at runtime via `coordinator.whoami_src` registry seam set by the same install run. |
| `.coordinator-venv/` | `~/.claude/.coordinator-venv/` | `~/.coordinator-claude-settings/.coordinator-venv/` | Rebuilt (never copied) by `install-substrate.sh` (C10a) via `bin/ensure-coordinator-venv.sh`; legacy venv removed only after rebuild + health probe both confirm healthy. |
| `bin/` resolver family | `~/.claude/bin/machine-local` etc. | `~/.coordinator-claude-settings/bin/` | `~/.claude/bin/machine-local` and siblings are **retained-and-repointed compat forwarders** (exec the settings-home resolver). Removed at phase-2 gated tail. |
| `settings-manifest.md` | `~/.claude/settings-manifest.md` | `~/.coordinator-claude-settings/settings-manifest.md` | None needed. |

**`setup/` is NOT in this table — it never relocated.** `setup/` is intentionally excluded from the settings-home migration: nothing reads `setup/` from the settings home at runtime (coordinator continues to read `~/.claude/setup/`), and the percolation step in `install-substrate.sh` writes the canonical copy there. Migrating it would create two diverging locations that the fail-loud divergent-file guard then blocks on every re-run. See `coordinator/lib/migrate-substrate-to-settings-home.sh` header.

**The transitional compat window is a first-class design primitive, not a footnote.** Coordinator cuts over first and deletes last. The compat layer (symlink + retained forwarders) is removed only at the single gated tail in phase-2, triggered when all 5 consumers (example-game-repo, project-rag, project-rag-ue-addon, cockpit, example-orchestration-hub) confirm they have migrated off the legacy surfaces. Until that gate, `~/.claude/machine-local` and `~/.claude/bin/machine-local` remain functional.

Moving the session-boot and harness surfaces listed above (wikis, decisions, settings, config) breaks
orientation or the harness config contract. Plugin source is DoE-resident — `publish.sh` now sources
from the allowlisted plugin subpath inside the DoE clone (DoE→OSS percolation), so plugin-source
location is no longer a constraint on the items above.

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
code-level `topology.md § AC-1` reclassification is example-orchestration-hub's own artifact, folded into this
contract via the return memo referenced above.

### Brittleness triad — reject all three (same anti-pattern)

(a) a single consolidation location; (b) local-file-only aggregation used as the *permanent,
fleet-wide* mechanism; (c) manual or stale snapshot upload. All three collapse per-repo emission
back onto one point of failure — the shape differs, the defect is identical. None may stand as
the fleet's source of truth.

### Tier A / Tier B observation model

- **Tier A — instrumented repos** (run coordinator + example-orchestration-hub): owe rich Tier-A emission — the full
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

- **`--subject`/sibling routing** (`coordinator/lib/coordinator-state-root.sh` Rules 1–5) — the
  subject-aware `coordinator_state_root` resolution documented in § Resolver Seam above.
- **Strangler PWD `repo_root` resolution** (`coordinator/lib/strangler-facade.sh`) — resolves
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
cockpit. A new repo that stands up coordinator + example-orchestration-hub inherits per-repo emission automatically
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

---

## Cross-References

- `machine-local-registry.md` — `EXAMPLE_ORCHESTRATION_HUB_ROOT` resolution and the §4b/§4c ladder that `machine-local get` encapsulates
- `coordinator-tripwires.md` — tripwires that enforce placement law at the hook layer
- `docs/plans/2026-07-03-stop-the-rot-example-orchestration-hub-state-home-placement.md` — full plan: resolver seam (C1/C2), scripted repoint (C3/C4), migration (C6), placement law (C10)
- `emission-conformance-contract.md` — the Consumer-Tolerance Ledger this contract's producer-side obligations are symmetric with
- `example-cockpit-repo/docs/decisions/2026-07-07-cockpit-live-remote-per-repo-observation-model.md` — canonical consumer-side record for § Fleet Producer Contract
