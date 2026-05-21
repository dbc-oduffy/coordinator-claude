---
title: Live-Install Drift Audit
created: 2026-05-21
author: claude-central-em
status: current
---

<!-- spec-backlink: plugins/project-rag/docs/plans/2026-05-21-plugin-source-live-mirror-doctrine.md § Chunk 2 (sibling repo) -->

# Live-Install Drift Audit

**Purpose.** Operator-facing reference for the canonical plugin live-install drift detection and remediation primitives. These primitives catch deployment-time skew — when the live install of a plugin diverges from its source — a failure mode orthogonal to the addon-health sentinel (which surfaces doctor-run verdicts).

---

## Problem Statement

The coordinator uses a publisher-mirroring model: plugins are authored in `~/.claude/` and published outward to OSS sibling repos (e.g. `coordinator-claude`) via `setup/publish.sh`. Per-machine live installs are separate git checkouts managed independently.

The 2026-ban on publish-repo → live-install clobber (per `feedback_no_publish_sh_overwrites_live_install.md`) means propagation is **never automatic**. An operator must explicitly run a refresh after publishing. Two failure modes emerge from this design:

- **Git-state drift.** The live checkout is N commits behind the source tree. The operator's live install is running stale code.
- **Venv-state drift.** The editable-install MAPPING in the live checkout's `.venv/` is stale relative to the plugin's `pyproject.toml`. The runtime resolves against an outdated package shape even when the source files are current.

Both failure modes are silent without an active probe.

---

## Canonical Primitives

These primitives are documented here for operator reference. Do NOT re-implement them — the scripts ship as part of the coordinator plugin.

### `bin/check-plugin-drift.sh`

Read-only probe. Six drift legs:

| Leg | What it checks |
|-----|----------------|
| `git-state` | Live checkout commit vs source tree commit on `track_ref` |
| `venv-pin` | `.python-version` match between source and live checkout |
| `venv-pyproject` | `pyproject.toml` mtime/hash delta between source and live |
| `venv-mapping` | Editable-install MAPPING up-to-date (no stale `.pth` or `__editable__` artifact) |
| `venv-shim` | Shim scripts present and pointing at the correct interpreter |
| `working-tree` | No uncommitted local changes in the live checkout |

Exit 0 = clean; exit 1 = drift detected. Surfaced daily via `/workday-start` Step 1.10 Addon Health. Run `bash bin/check-plugin-drift.sh --help` for the full probe description and per-leg remediation hints.

### `bin/refresh-plugin-live-install.sh <plugin>`

Atomic two-leg refresh:

- **Git-state leg:** `git fetch && git checkout <track_ref>` in the live checkout directory.
- **Venv-state leg:** `uv pip install -e .` against the live checkout's `.venv/` when `pyproject.toml` has changed or the MAPPING is stale.

Takes `<plugin>` name from the `plugin.mirrors.*` registry in `~/.claude/machine-local/registry.local.toml`. Idempotent and resumable. **Never auto-applied** — operator runs it after `check-plugin-drift.sh` flags drift. Exits non-zero if the pre-flight working-tree check in the live checkout fails (uncommitted local changes would be clobbered by the git-state leg).

### `[plugin.mirrors.<plugin>]` in `~/.claude/machine-local/registry.local.toml`

Registration surface. Schema fields:

| Field | Semantics |
|-------|-----------|
| `source_path` | Absolute path to the plugin source tree (the authored copy) |
| `live_path` | Absolute path to the plugin live install (separate git checkout) |
| `track_ref` | Branch or tag the live checkout should track (e.g. `main`) |
| `propagation_mode` | `"managed"` (default) or `"source_is_live"` (see below) |

`propagation_mode = "source_is_live"` applies to self-install plugins (coordinator-claude itself, installed over `~/.claude/`). `check-plugin-drift.sh` treats these as structural no-ops — there is no separate live checkout to diverge.

Run `bin/machine-local keys | grep plugin.mirrors` to enumerate registered plugins on the current machine.

---

## Why `plugin.mirrors.*` Over a Per-Plugin Manifest Field

Two alternatives were considered and rejected:

1. **Per-plugin manifest field** (e.g. `live_path:` in `plugin.json`). MCP-only entries (e.g. `project-rag`) have no `plugin.json`. A manifest field would require either inventing a new schema for these plugins or maintaining two registration surfaces.

2. **Blanket glob discovery** (`~/.claude/plugins/*/` as the live-install root). False positives. Marketplace plugins without a source tree have no sensible `source_path`; treating them as drift candidates produces noise and may drive incorrect refresh attempts.

The `plugin.mirrors.*` shape in `registry.local.toml` is opt-in, co-located with other machine-local values, and uses the same reader infrastructure as everything else in the registry. Single source of truth per machine.

---

## Design Contrast: Addon-Health Sentinel

The sentinel wiki (`addon-health-sentinel.md`) chose **glob-discovery over manifest registration** for health verdicts. That tradeoff is correct for its domain: every plugin that ships a doctor writes a sentinel, and false positives don't apply (a sentinel either exists or doesn't; its existence is a signal, not a noise source).

Drift audit makes the **opposite tradeoff** — explicit `plugin.mirrors.*` registration — because false positives WOULD apply. A marketplace plugin with no source tree has no sensible drift state; blanket-by-glob would surface it as "drift unknown" on every probe run, training operators to ignore the output.

Both choices are deliberate. They reflect the asymmetry between the two failure modes:

- **Health sentinel:** presence-or-absence of a file is already meaningful. Glob discovery is safe.
- **Drift audit:** source-to-live comparison requires both ends to be known and valid. Explicit registration is safer.

---

## Why R-9(b): `check-plugin-drift.sh` at Deployment Time, Source-Side Tripwires at Authoring Time

Project-RAG's source-side tripwires catch in-repo authoring errors — a wrong import path, a missing module declaration, a schema field that drifted from the spec. These fire at the source level.

`check-plugin-drift.sh` catches **deployment-time skew** — the live checkout is stale, or the venv hasn't been refreshed since `pyproject.toml` changed. It fires at the runtime level.

These are orthogonal failure modes at different capture points. Running both is not redundant; it covers the full gap between "the source is correct" and "the live install reflects the source."

---

## Spec Backlink

This wiki documents the primitives shipped by: `docs/plans/2026-05-21-plugin-source-live-mirror-doctrine.md`

The plan contains the implementation rationale and dispatch decomposition. This wiki is the operator-facing reference.

---

## Cross-References

- `docs/plans/2026-05-21-plugin-source-live-mirror-doctrine.md` — implementation spec and rationale
- `docs/wiki/machine-local-registry.md § plugin.mirrors` — registry schema and value-writing discipline
- `docs/wiki/addon-health-sentinel.md` — health sentinel convention; design contrast documented above
- `docs/wiki/plugin-identity-and-health-sentinels.md` — scanner-is-reader-never-writer rule
- Global CLAUDE.md § Plugin live-install propagation — managed-refresh model
