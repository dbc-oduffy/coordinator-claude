# The `docs/exec-summary.md` artifact

A coordinator-mandated, per-repo **executive summary** — a one-screen "why this project
matters" brief. It gives the cockpit fleet board (and cross-repo DoE orientation) a predictable,
uniform "give a shit" pitch for every repo, collecting four facets that otherwise live scattered
across READMEs, `CLAUDE.local.md` sibling lines, and `state/week-changelog/`.

Spec backlink: `docs/plans/2026-07-03-exec-summary-per-repo-brief.md` (the Director of Engineering-reviewed).

## Shape

Canonical path **`docs/exec-summary.md`** (parallels `docs/project-tracker.md`, under `docs/`
where cockpit's artifact fetch already looks). Four sections, two fill modes:

| Section | Fill mode | Source / disposition |
| --- | --- | --- |
| What this project is | **MANAGED** | README H1 + lead paragraph → CLAUDE.md first line → `basename` (identity derivation reused from orientation-cache) |
| What makes it special | **HAND** | No reliable disk source; author once, preserved verbatim on regen. Seed from the `CLAUDE.local.md` sibling-repo differentiator line. |
| Near-term goals | **HAND** | `week-changelog/HEADER.md` Priorities is blank fleet-wide; hand-authored, generator may pre-fill a commented seed only. |
| Progress | **MANAGED** | `state/week-changelog/` latest Highlights + `orientation_cache` Counters + `git log` since last weekly reset (git-log fallback where week-changelog absent). |

Each section body is wrapped in HTML-comment fences — `<!-- BEGIN MANAGED: <name> -->` /
`<!-- END MANAGED: <name> -->` and the `HAND` equivalents (fence names: `identity`, `special`,
`goals`, `progress`). This generalises the `regenerate-orientation-cache.sh` pinboard-preservation
pattern (re-emit derived slots, copy hand slots forward verbatim) to a four-section fence grammar.

## Frontmatter — the cockpit light-read contract (D1)

```yaml
kind: exec-summary
repo: <name>
project: <title>
generated: <ISO-8601>
generator: bin/generate-exec-summary.sh
```

This is the **entire** ingestion contract for the light path: a stable `kind` + path is all
cockpit's frontmatter reader (`src/lib/fleet/` + `src/lib/connector/content.ts` `readArtifact`)
needs to find, class, and render it. **No Zod entity, no `CONTRACT_VERSION`, no envelope array.**

## Generator

`bin/generate-exec-summary.sh` (regenerate-orientation-cache-shaped):

- Resolves git-root; re-emits frontmatter + the two MANAGED blocks from disk-derived data.
- For every HAND block, copies current on-disk content forward **verbatim**.
- `--check` prints the regenerated file to stdout without writing.
- No-clobber create-with-placeholder for a genuinely-new (absent) file only.
- **Fail-loud (detect-then-fail-loud doctrine):** if a HAND fence pair is absent or malformed on
  an existing file, the generator exits non-zero, names the file + broken fence, and writes
  nothing — it never regenerates over an unparseable HAND region.

Freshness is surfaced by an mtime staleness banner in `hooks/scripts/project-orientation.sh`
(24h / 168h thresholds, mirroring the repomap block; kill-switch `COORDINATOR_EXECSUMMARY_STATUS_OFF`)
and refreshed weekly at `/workweek-start`. Registration lives in `canonical-structure.yaml`
(eager file entry) and `repo-setup` SKILL Phase 3d.5 (created on new repos; `--batch` backfills the
fleet, no-clobber).

## Deliberately outside the schema registry

`kind: exec-summary` has **no `schemas/` entry by design.** It is a light render-path artifact:
no typed cockpit-contract entity, no emission-envelope participation, no `CONTRACT_VERSION`. It is a
plain committed markdown doc that cockpit reads directly. Registering it as a typed entity is a
**future, gated decision — not a hygiene fix.**

## Why the typed-entity route is deferred (correct end-state, sequenced)

The typed `exec-summary` cockpit entity is the correct end-state (it aligns with the standing
"contract richness serves cockpit" fleet directive), but it is **sequenced after the
deliverable-spine `2.4.0` cockpit bump clears**, for two reasons:

1. **DR-203 single-owner serialization.** The `2026-07-03-fleet-deliverable-spine` /
   `fleet-contract-landing` work single-owns `cockpit-contract` + `emit-cockpit-snapshot.sh` and
   drives the reader-first `CONTRACT_VERSION 2.4.0` bump. A second concurrent entity + bump is
   exactly the double-bump DR-203's serialization exists to prevent. The light path has **zero
   file-overlap** with that landing.
2. **Unblocks now.** Cockpit can read and render per-repo markdown directly; the light path ships
   exec-summary content fleet-wide without waiting for the spine to clear.

A future plan adds the typed entity + emitter projection + reader-first handshake **after** the
spine `2.4.0` bump lands — never as a concurrent second bump. Synergy note: once the spine lands,
exec-summary frontmatter MAY later carry `deliverable_id` / `initiative` for board-side grouping.

## Percolation status

**Held pending example-orchestration-hub** (see the `percolation-held-pending-example-orchestration-hub` memory entry). This artifact —
template, generator, `canonical-structure.yaml` entry, skill/hook edits — lands in live `~/.claude`
and internal sibling live-installs, but does **not** reach the OSS `coordinator-claude` publish
until the example-orchestration-hub percolation hold lifts. There is no OSS-publish step for this artifact yet.
