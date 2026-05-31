---
title: Live-Install Drift Audit
created: 2026-05-21
author: claude-central-em
status: current
---

<!-- spec-backlink: plugins/project-rag/docs/plans/2026-05-21-plugin-source-live-mirror-doctrine.md § Chunk 2 (sibling repo) -->
<!-- extended-by: docs/plans/2026-05-23-copy-install-drift-coverage.md § Chunk 3 -->

# Live-Install Drift Audit

**Purpose.** Operator-facing reference for the canonical plugin live-install drift detection and remediation primitives. These primitives catch deployment-time skew — when the live install of a plugin diverges from its source — a failure mode orthogonal to the addon-health sentinel (which surfaces doctor-run verdicts).

---

## Problem Statement

The coordinator uses a publisher-mirroring model: plugins are authored in `~/.claude/` and published outward to OSS sibling repos (e.g. `coordinator-claude`) via `setup/publish.sh`. Per-machine live installs are separate git checkouts managed independently.

The 2026-ban on publish-repo → live-install clobber (per `feedback_no_publish_sh_overwrites_live_install.md`) means propagation is **never automatic**. An operator must explicitly run a refresh after publishing. Three failure modes emerge from this design:

- **Git-state drift.** The live checkout is N commits behind the source tree. The operator's live install is running stale code.
- **Venv-state drift.** The editable-install MAPPING in the live checkout's `.venv/` is stale relative to the plugin's `pyproject.toml`. The runtime resolves against an outdated package shape even when the source files are current.
- **Copy-install drift (SHA-sentinel).** The live install was produced by a copy-based installer and the source has advanced past the SHA recorded in `version.txt` at copy time. There is no git remote in the live path; only the sentinel reveals the gap.

All three failure modes are silent without an active probe.

---

## Configuring a refresh-managed install — verbs, not hand-edits

The drift failure modes above have a doctrine corollary for *how operators configure* a refresh-managed plugin: **configure through the provided verbs; never hand-edit the wiring or the source.** Because a background refresh periodically runs `git checkout <track_ref>` against the live directory, source-tree edits in a refresh-managed checkout (a) do nothing useful — configuration lives in the registry, env, and per-project wiring, not the source tree — and (b) get silently reverted on the next refresh.

This is the refresh-managed analogue of coordinator's own *source-is-live* rule ("edit `~/.claude`, not a clone" — see `getting-started.md` Movement 2). In both cases the true mental model is identical: **you are configuring an infra tool, not maintaining a fork.**

The provided verbs vary by plugin — e.g. `machine-local set <key> <val>` for registry keys; a plugin's `setup` / `wire` command for env knobs and per-project MCP wiring. Each plugin documents its own configuration-surface table; the universal rule is that hand-editing the refresh-managed checkout is the anti-pattern. Genuine per-project live files (sentinels, `coordinator.local.md` `project_type`) are the documented exceptions — editing those in place IS the correct verb.

<!-- Cross-team origin: project-rag-em, 2026-05-23 cross-repo consult (configure-not-edit framing); folded into coordinator doctrine by DoE. -->

**Per-project plugin gating.** When two plugins expose overlapping domain routing (e.g. `game-dev@coordinator-claude` and `holodeck-control@claude-unreal-holodeck`), enable only one per project via per-project `enabledPlugins`. See `docs/wiki/plugin-extraction-and-distribution.md § Competing Plugins in Overlapping Domains` and `docs/wiki/per-project-plugin-gating.md` for the gating mechanism.

---

## Canonical Primitives

These primitives are documented here for operator reference. Do NOT re-implement them — the scripts ship as part of the coordinator plugin.

### `check-plugin-drift.sh`

Read-only probe. Six drift legs for Default (git-checkout-managed) mode; SHA-sentinel for copy_install mode:

**Default (git-checkout-managed) legs:**

| Leg | What it checks |
|-----|----------------|
| `git-state` | Live checkout commit vs source tree commit on `track_ref` |
| `venv-pin` | `.python-version` match between source and live checkout |
| `venv-pyproject` | `pyproject.toml` mtime/hash delta between source and live |
| `venv-mapping` | Editable-install MAPPING up-to-date (no stale `.pth` or `__editable__` artifact) |
| `venv-shim` | Shim scripts present and pointing at the correct interpreter |
| `working-tree` | No uncommitted local changes in the live checkout |

**copy_install SHA-sentinel leg:**

| Output | Meaning | Exit |
|--------|---------|------|
| `[ok] <plugin>: copy_install — sentinel matches source HEAD (<sha:12>)` | Live install is current | 0 |
| `[ok-via-git-propagation] <plugin>: copy_install — live content matches source HEAD (<sha:12>); sentinel at <sha:12> (lagging — will refresh on next install)` | Sentinel lags source HEAD, but live content is byte-equal with source HEAD — content arrived via `git pull`; sentinel will advance on next local install run | 0 |
| `[drift] copy_install: <plugin> — sentinel <sha:12> ≠ source HEAD <sha:12> AND content differs: <file list>` | Sentinel lags source HEAD AND live content differs from source HEAD; live install is genuinely stale | 1 |
| `[warn] <plugin>: copy_install — sentinel mismatch and source_subpath '<path>' not found; cannot run content-equivalence check` | Sentinel lags, `source_subpath` unconfigured or missing on disk; probe cannot determine drift | 0 |
| `[warn] <plugin>: copy_install — could not enumerate source tracked files (git ls-tree failed): <err>` | Sentinel lags, `git ls-tree` failed on source repo; probe cannot determine drift | 0 |
| `[warn] <plugin>: copy_install — git ls-tree returned empty for source_subpath '<path>'; cannot run content-equivalence check` | Sentinel lags, `source_subpath` exists on disk but has no tracked files in source HEAD; probe cannot determine drift | 0 |
| `[info] <plugin>: copy_install — no version.txt sentinel (installer did not write one; see holodeck memo)` | Honest degraded state; no sentinel yet; see Known Limitation #1 | 0 |
| `[warn] <plugin>: version.txt malformed (len=N) — refresh to rewrite sentinel` | Sentinel exists but is not a valid 40-char hex SHA; does NOT count as drift | 0 |

Exit 0 = clean or informational; exit 1 = drift detected. Surfaced daily via `/workday-start` Step 1.10 Addon Health (exit-0 states, including `[ok-via-git-propagation]`, are intentionally silent there — see comment at that step). Run `bash check-plugin-drift.sh --help` for the full probe description and per-leg remediation hints.

**Dual-channel propagation model.** For `copy_install` plugins that are also git-tracked in the live install directory (e.g. the holodeck trio — see DR-137), live install content can advance through two independent channels: (1) a local install run — advances both file content and the `version.txt` sentinel atomically; or (2) a `git pull` from a peer machine that ran install at a later source HEAD — advances file content only, leaving the sentinel at the prior install's SHA. After a `git pull`, the live content may already match the current source HEAD while the sentinel still reflects "last local install." The forward probe now distinguishes these two states: `[ok-via-git-propagation]` for the git-pull case (exit 0, benign); `[drift]` only when content also differs (exit 1, genuinely stale). This distinction was not possible under the original sentinel-only probe. Predecessor that documented the WHAT (sentinel catches committed drift only): `archive/specs/2026-05-23-copy-install-drift-coverage.md § Known Limitations #1`; this paragraph adds the WHY (dual-channel).

**Why `[warn]` (malformed sentinel) exits 0, not 1 (deliberate, not an oversight).** A malformed
`version.txt` is a *corruption* signal, not a *behind-source* signal — exit-1 would conflate it with
genuine drift in the aggregate Addon-Health roll-up and could noise a transient/partial write into a
red gate. The actionable surface is the printed `[warn]` line (operator re-runs refresh to rewrite the
sentinel); the exit code stays 0 so a corrupt sentinel on one plugin doesn't mask or fake drift state
for others. `[info]` (no sentinel) and `[warn]` (malformed sentinel) are both "can't compare yet,
here's why" states — distinct from `[drift]` ("compared, and live is behind").

### `refresh-plugin-live-install.sh <plugin>`

**Default (git-checkout-managed) mode:** Atomic two-leg refresh:

- **Git-state leg:** `git fetch && git checkout <track_ref>` in the live checkout directory.
- **Venv-state leg:** `uv pip install -e .` against the live checkout's `.venv/` when `pyproject.toml` has changed or the MAPPING is stale.

**copy_install mode:** Single-action refresh via the registry-supplied `refresh_cmd`:

- Runs `refresh_cmd` from `source_path` (e.g. `bash scripts/install-control-plugin.sh --allow-standalone --no-enable`), with a snapshot + REPLACE-semantics rollback on failure. Git-state and venv-state legs are skipped entirely.
- The coordinator does **not** hardcode the install invocation: the holodeck trio refuses bare standalone component installs (`HOLODECK_UMBRELLA_INSTALL=1` gate), reachable only via the forwarders' `--allow-standalone` passthrough (and the docs component has no forwarder). The correct command is installer-internal knowledge, so it lives in `refresh_cmd`. `--no-enable` bypasses `enable_plugin.py` (the `settings.json` lock).
- **No `refresh_cmd` registered → refresh prints the manual path (`/holodeck:setup` or the per-component forwarder) and exits non-zero.** It never guesses an invocation or silently no-ops.

Takes `<plugin>` name from the `plugin.mirrors.*` registry in `~/.claude/machine-local/registry.local.toml`. **Default (non-interactive) atomic path: idempotent and resumable** — re-running converges to the same fully-refreshed state. The `--interactive` partial path (2026-05-27) is the one deliberate non-idempotent escape hatch: HEAD is left behind when any file is skipped, producing a MIXED live-install state. The convergence step is a subsequent plain `refresh-plugin-live-install.sh <plugin>` (non-interactive), which re-applies the full atomic checkout and restores the idempotency invariant. **Never auto-applied** — operator runs it after `check-plugin-drift.sh` flags drift.

### `[plugin.mirrors.<plugin>]` in `~/.claude/machine-local/registry.local.toml`

Registration surface. Three modes:

| Mode | `propagation_mode` value | Drift probe behavior |
|------|--------------------------|----------------------|
| Default (git-checkout-managed) | `""` (empty / absent) | Six-leg git + venv check |
| `source_is_live` | `"source_is_live"` | Structural no-op; `[n/a]` |
| `copy_install` | `"copy_install"` | SHA-sentinel comparison; no git/venv legs |

**Schema fields for copy_install:**

| Field | Semantics |
|-------|-----------|
| `source_path` | Absolute path to the plugin source repo root (for `git rev-parse HEAD` + locating the installer) |
| `live_path` | Absolute path to the live install directory (for reading `version.txt`) |
| `refresh_cmd` | Shell command run from `source_path` to reinstall the plugin. If absent, refresh prints the manual path and exits non-zero — it never guesses. |
| `source_subpath` | Relative path within `source_path` to the plugin tree. Default: `plugin/<plugin_name>` when absent. Used by the content-equivalence fallback to enumerate tracked source files for blob-SHA comparison. |

**Why `refresh_cmd` and not a direct `install-plugin.sh` call.** The holodeck trio refuses bare standalone component installs via the `HOLODECK_UMBRELLA_INSTALL=1` gate; the correct command is installer-internal knowledge. A registry-supplied `refresh_cmd` keeps the coordinator generic and routes around umbrella gates without coordinator knowing about them. Dogfood-proven: both refresh-success and refresh-failure paths verified in a live round-trip (2026-05-23).

**No `refresh_cmd` registered → refresh prints the manual path (`/holodeck:setup` or the per-component forwarder) and exits non-zero.** Never guesses or silently no-ops.

`track_ref` and `dist_name` do not apply to `copy_install` entries.

`propagation_mode = "source_is_live"` applies to self-install plugins (coordinator-claude itself, installed over `~/.claude/`). `check-plugin-drift.sh` treats these as structural no-ops — there is no separate live checkout to diverge.

Run `machine-local keys | grep plugin.mirrors` to enumerate registered plugins on the current machine.

---

## `copy_install` Mode — Mechanism and Rationale

The `copy_install` propagation mode covers plugins installed by a file-copy installer rather
than a git checkout. The canonical example is the `claude-unreal-holodeck` trio (`holodeck`,
`holodeck-control`, `game-dev`), installed via `scripts/install-plugin.sh` from the holodeck
source repo.

### SHA-sentinel — why not content-diff?

The installer writes a 40-char source HEAD SHA to `<live_path>/version.txt` at copy time.
The probe compares this sentinel to `git -C <source_path> rev-parse HEAD`. No network fetch —
the local HEAD is the comparison target, since these plugins develop on `work/*` branches ahead
of `origin/main`.

Content-diff (comparing live files to source files) would be a false-positive machine: the
installer injects UTF-8 BOMs into every `.ps1`, copies in the marketplace manifest, and strips
`.mcp.json` — so `live ≠ source` by construction even when perfectly current. The sentinel
sidesteps all of it.

**Refinement — sentinel-gated content-equivalence fallback is valid (2026-05-28).** The rejection above applies to content-diff as the *primary* mechanism: running it unconditionally against every plugin, including those whose live tree was produced by the installer (with BOM injection, manifest copy, and `.mcp.json` strip applied), would generate false positives. A *sentinel-gated* content-equivalence fallback — fired only when `sentinel != source HEAD`, using blob-SHA comparison of the SOURCE tracked set — is a different operation and does not reintroduce that surface. Specifically: when `sentinel != HEAD`, the fallback can only be running against a tree where the installer either (a) did not run (content arrived via `git pull` — verbatim source bytes, no BOM, no manifest, no strip) or (b) ran at an older HEAD and source has since advanced. In case (a), blob SHAs match source and the probe correctly emits `[ok-via-git-propagation]` (exit 0). In case (b), SHAs differ and the probe correctly emits `[drift]` (exit 1). The SHA-sentinel remains the primary mechanism; the content-equivalence check is a secondary fallback that narrows the `[drift]` verdict to cases of genuine content divergence. **Honesty caveat:** for a future plugin that ships installer-transform-affected files (`.ps1` with BOM injection, `.mcp.json` that gets stripped), a stale-install scenario (case b) would compare a transformed live tree against pristine source bytes — the SHAs would differ, and `[drift]` would be the correct verdict, but the diff output would mention transform-affected files alongside genuine content changes. Correct attribution in that case requires transform-aware handling; this is a documented follow-up. No current plugin (`holodeck`, `holodeck-control`, `game-dev`) ships `.ps1` or `.mcp.json` inside its plugin tree, so this caveat is presently moot. The sentinel-gated fallback eliminates false-positives for git-propagated trees; it does not claim airtightness for all future plugin shapes. Spec: `docs/plans/2026-05-28-forward-drift-probe-content-equivalence.md § Prior-art reconciliation`.

### Known Limitations

1. **SHA-sentinel catches committed drift only.** Uncommitted source edits are invisible:
   `version.txt` records the committed HEAD, so if source has uncommitted changes that haven't
   been copied to the live install, the probe will show `[ok]` even though the live install
   lags behind. Acceptable: the 3-day-drift incident (2026-05-20 → 2026-05-23) was committed
   drift, and content-diff is the only way to catch uncommitted drift — and it is a
   false-positive machine. Documented here; not deferred by appetite.

2. **`holodeck` and `game-dev` report `[info] no sentinel`** until the holodeck installer
   is updated to write `version.txt` unconditionally (currently gated on
   `requires_plugin_source_index: true` in the plugin manifest, set only for
   `holodeck-control`). See the holodeck repo's `cross-repo/inbox/2026-05-23-copy-install-drift.md` (memo requesting the fix) (asks tracked in `docs/plans/2026-05-23-copy-install-drift-coverage.md`)
   for the memo requesting the fix. This is honest degraded state — the prior coverage was
   zero; `[info]` is progress, not silence.

3. **Clean-install reproducibility** depends on the holodeck installer self-registering
   `plugin.mirrors` entries at install time. Until that lands, a fresh machine requires a
   manual `machine-local set` pass. The cross-repo memo is the close for this gap.

4. **`rm -rf` restore guard.** The post-flight restore guard is hardened to check that `LIVE_PATH` is a resolved-physical-path under `$PLUGINS_DIR` (not a self-compare). This matters because `refresh_cmd` is operator-controlled registry content — the trust model was confirmed: `refresh_cmd` adds no privilege-escalation beyond the ability to write the registry.

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

- `docs/plans/2026-05-21-plugin-source-live-mirror-doctrine.md` — implementation spec and rationale for Default + source_is_live modes
- `docs/plans/2026-05-23-copy-install-drift-coverage.md` — implementation spec for copy_install mode
- `docs/wiki/machine-local-registry.md § plugin.mirrors` — registry schema and value-writing discipline; § 12 copy_install subsection
- `docs/wiki/addon-health-sentinel.md` — health sentinel convention; design contrast documented above
- `docs/wiki/plugin-identity-and-health-sentinels.md` — scanner-is-reader-never-writer rule
- the holodeck repo's `cross-repo/inbox/2026-05-23-copy-install-drift.md` (memo requesting the fix) (asks tracked in `docs/plans/2026-05-23-copy-install-drift-coverage.md`) — cross-repo memo requesting version.txt ungating + installer self-registration
- Global CLAUDE.md § Plugin live-install propagation — managed-refresh model
