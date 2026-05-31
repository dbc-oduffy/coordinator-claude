# Plugin Extraction and Distribution

**Provenance:** consolidated 2026-05-05 from `tasks/lesson-triage-2026-05-05/SYNTHESIS.md` §B4, refactored 2026-05-07 to absorb the post-shipping plugin-extraction queue cluster (atlas drift, versioning, CRLF/LF, source-path runtime pinning, four-surface mop-up).

When extracting a plugin from its source repo into a standalone distributable, "it works on my machine" is not the bar. External consumers run from a clean profile, on different OSes, with different drive layouts, against fresh `~/.claude.json` state. The extraction is incomplete until each of the surfaces below is verified.

## The 10-Item Checklist

### 1. Source-repo cleanup

Sweep the source repo for orphan plugin trees, install scripts, local configs, and stale tool-name references that survive the extraction. The plugin's old in-repo location often leaves debris that misleads future readers and breaks reproducibility. Brand-bound names (`HOLODECK_*`, `DRONESIM_*`) and the old plugin tree itself must both go — extraction is incomplete until orphans + brand-bound names are gone.

The four surfaces that must mop up together at extraction time: (a) the in-source-repo plugin tree, (b) install scripts that register the old layout, (c) `marketplace.json` entries pointing at the old location, and (d) per-user `~/.claude.json` `mcpServers` and `enabledPlugins` registrations. Skip any one and the next external consumer hits dead entries the author's machine no longer notices.

### 2. Plugin generalization — `${CLAUDE_PLUGIN_ROOT}`, not hardcoded paths

The plugin's own commands, hooks, and skills must resolve their install dir via `${CLAUDE_PLUGIN_ROOT}`, never via hardcoded sibling-repo paths. Hardcoded paths embed the author's machine layout into the shipped artifact and break on every external consumer.

### 3. Env/config rename to neutral names (with deprecation fallback)

Brand-bound env vars, paths, and config keys (`HOLODECK_*`, `DRONESIM_*`, etc.) get renamed to neutral names. Keep a deprecation fallback that reads the old name and emits a one-line warning so existing consumers don't break overnight.

### 4. Runtime detachment — sever venv dependency on source repo

If the plugin's MCP server runs from a source tree (`pip install -e <source-path>`), document this explicitly. The runtime version is the checked-out branch HEAD, **not** what `pip show <pkg>` reports — which is often a separately-installed wheel. Conflating the two leads to "install v0.2.3" being a near-no-op when the consumer's MCP entry already points at source-path. Surface the source-path-vs-wheel distinction in install docs.

A source-path MCP registration (`command: python`, `args: [-m, server]`, `cwd: <source-tree>`) makes every subsequent `install vN` invocation a near-no-op for that consumer — the runtime version is whatever the source checkout currently points at. Installer should detect a pre-existing source-path registration and either (a) refuse to re-register over it without `--force`, or (b) print a loud notice that "install v0.5.3" will not change runtime behavior until the consumer's checkout is updated.

### 5. Doc sync

Update READMEs, install instructions, and any cross-repo references that pointed at the old location. Stale doc references → repoint to existing surfaces when content is already covered; create new pages only when genuinely missing (don't default to "create the missing doc" for every broken link).

### 6. Marketplace.json + per-user `~/.claude.json` mcpServers cleanup

Easy to forget: the per-user `~/.claude.json` `mcpServers` registration AND the marketplace.json entry both auto-register the now-deleted server file. Both need to be cleaned up at extraction time, otherwise `claude mcp list` carries dead entries until the next user notices and asks.

### 7. Plugin enablement is **per-project**, not user-global

Plugin enablement (`enabledPlugins["<name>@<marketplace>"]`) belongs in `<project>/.claude/settings.local.json`, not `~/.claude/settings.json`. The marketplace and install record stay user-global, but the install record uses `scope:"project"` with `projectPath` so a second project on the same machine appends a separate record rather than overwriting the first. Enablement granularity must match MCP-server registration granularity; the two surfaces drift apart silently when one is per-project and the other is user-global.

Writing enablement to `~/.claude/settings.json` surfaces the plugin's slash commands in every project on the machine — not just the one that opted in. Mirrors the same wrong-shape failure as writing MCP server args to top-level `mcpServers` instead of `projects[<root>].mcpServers`. The cost compounds: every situational MCP plugin enabled user-global contributes its deferred-tool surface and instruction blocks to *every* session boot regardless of whether the project actually uses it.

### 8. Plugin installers must register enablement, not just MCP wiring

A Claude Code plugin distributed via shell installer must touch **three** files for slash commands and agents to surface:

- `~/.claude/settings.json` (or `<project>/.claude/settings.local.json`) — `enabledPlugins`
- `~/.claude/plugins/known_marketplaces.json`
- `~/.claude/plugins/installed_plugins.json`

Registering only the MCP server in `~/.claude.json` is necessary but not sufficient. Test installs from a profile that has never run `/plugin install` to catch this — installs that happen to work on the author's profile rely on a one-time manual `/plugin install` long forgotten.

### 9. Plugin disable ≠ uninstall

Setting `enabledPlugins.foo: false` leaves the cache intact (`~/.claude/plugins/cache/<marketplace>/<plugin>/`) and a re-enable instantly resurrects the plugin. For a true uninstall when `claude plugin uninstall` reports "not found in installed plugins" (cache-only loads), `rm -rf` the cache dir AND delete the `enabledPlugins` key from every project's settings.json.

Generalized: disabling a plugin/hook (toggling `enabled: false`) is NOT uninstalling — the on-disk artifacts remain and can be re-enabled silently by stale config layers (settings cascades, project overrides, marketplace caches). Uninstall = `enabled: false` + remove artifacts from disk + grep for cached references in every settings layer. The same pattern applies to hooks, MCP servers, and any toggle-gated artifact: removal is a two-surface operation, not a flag flip.

### Installed-vs-source plugin staleness — agents read from `~/.claude/plugins/`

Agents at runtime read from `~/.claude/plugins/<name>/` (the installed copy), NOT from the meta-repo source tree. When debugging an agent's behavior, verify against the installed copy. A "fixed it in source" claim with no propagation step is a no-op for the running agent.

**Propagation model depends on how the live install was created.** Two modes:

- **Separate git checkout (e.g. `project-rag`):** the live install at `~/.claude/plugins/<name>/` is its own git checkout with its own `.venv/`. Source changes require both legs to propagate:
  1. **Git-state leg:** which HEAD is checked out in the live install. Stale when the live checkout's HEAD lags the source branch.
  2. **Venv-state leg:** whether the editable install's `direct_url.json` resolves to the live checkout path, the MAPPING dict in `__editable___*_finder.py` reflects the current package layout, and console-script shims exist. Stale when `pyproject.toml` changed or a package directory was renamed without a re-install.

  Canonical propagation primitive: `bash refresh-plugin-live-install.sh <plugin>` — executes both legs atomically, with pre-flight (clean working tree check) and post-flight (drift probe). Both legs must close together; advancing git HEAD without re-running `uv pip install -e .` leaves the venv leg stale and can cause silent `ImportError`.

- **Live install IS the canonical source (e.g. coordinator-claude — installed over `~/.claude/`):** there is no source → live propagation step. Edits made in `~/.claude/plugins/coordinator-claude/...` take effect immediately. These plugins carry `propagation_mode = "source_is_live"` in `~/.claude/machine-local/registry.local.toml::plugin.mirrors`. The drift probe treats them as structural no-ops; the refresh script skips them.

**Drift detection:** `bash check-plugin-drift.sh` probes both legs (git-state and venv-state) for each registered plugin and surfaces results in `/workday-start` Step 1.10 Addon Health daily.

**`publish.sh` direction:** `publish.sh` runs source → publish-repo (sibling) for cross-machine distribution. It does NOT write back to the live install; the 2026-05-20 ban on publish-repo → live install clobber is preserved. These are orthogonal operations.

Spec: `docs/plans/2026-05-21-plugin-source-live-mirror-doctrine.md`.

#### `propagation_mode = "editable_sibling_venv"` — addon editable-installed into a sibling host's venv

<!-- spec-backlink: docs/plans/2026-05-30-editable-sibling-venv-propagation-mode.md § Chunk 5 -->
<!-- closes: install-surface-completeness.md § Three recurring failure shapes, shape 2 — "Known coordinator-side gap" -->

**When it applies.** An addon (e.g. `project-rag-ue-addon`) whose editable install lives in a *sibling* plugin's venv (e.g. `project-rag`'s `.venv`), while the addon's own git checkout is a separate repo. The addon's `dist-info` is inside the host's venv; the addon's source tree is an independent checkout with its own git history. Neither existing mode covers this: default mode and `source_is_live` both assume `source_path` and `live_path` point at the same plugin; `copy_install` has no venv leg at all.

**`editable_sibling_venv` is the first mode to decouple `source_path` from `live_path`.** In this mode the two fields point at *two different plugins*, not two locations of the same plugin. Field co-anchoring (source_path and live_path both pointing at the same plugin's install relationship) holds for modes 1–3 (`default` / `source_is_live` / `copy_install`) only. Authoritative field table: `machine-local-registry.md` § `plugin.mirrors` — Three modes.

**Decoupled-leg semantics.** The two propagation legs diverge:

| Leg | Path | Notes |
| --- | --- | --- |
| **git-state** | `source_path` — the addon's own git checkout | Fetches/checks-out the addon repo (skipped when `track_ref = "live"`) |
| **venv-state** | `live_path/.venv` — the host plugin's venv | Probes `dist-info`, editable pin, MAPPING, shims for `dist_name` |
| Expected editable-pin root | `source_path` | The install pins to the addon repo, NOT the host; checks must assert pin→`source_path` |
| Re-install command | `uv pip install -e <source_path> --python <live_path/.venv python>` | Installs the *addon source* into the *host venv* |
| MCP restart sentinel | `live_path/data/doctor-last-run.json` | Keyed on the host (the running MCP server), not the addon |

**`track_ref` contract divergence — omitting is a footgun.** The default-mode behaviour (`track_ref` absent → parsers default to `"origin/main"`) does NOT apply safely here. Both parsers (`bin/lib/read-mirrors.sh:83` and `refresh-plugin-live-install.sh`'s `_read_registry:233`) call `entry.get("track_ref", "origin/main")`, so an absent `track_ref` resolves to the literal string `"origin/main"`. In `editable_sibling_venv` mode this would trigger the git-state leg and run `git fetch && checkout origin/main` against the addon's working tree — clobbering in-flight branch work on a dev machine.

- **Dev posture:** `track_ref = "live"` — explicit sentinel meaning "addon source is a live working tree; skip the git leg; run venv-state only."
- **Consumer posture:** `track_ref = "origin/main"` — full two-leg (git-state advances the addon checkout, venv-state repairs the editable install).

**Do NOT omit `track_ref` in either entry.** The parser default-to-`"origin/main"` makes a missing field dangerous in this mode. Cross-reference: `machine-local-registry.md` § `track_ref` lifecycle.

**Registry entry shape — exact TOML blocks.**

Dev posture (venv-only refresh; git-state is the live working tree):

```toml
[plugin.mirrors.project-rag-ue-addon]
# editable_sibling_venv: addon source (own git repo) editable-installed into the
# project-rag HOST venv. On THIS dev machine the addon source X:/project-rag-ue-addon
# is a live working tree — do NOT run the git leg against it.
# track_ref = "live" is the EXPLICIT sentinel — do NOT omit it.
# Both parsers default an absent track_ref to "origin/main", which would trigger
# git fetch && checkout origin/main and clobber the dev working tree.
propagation_mode = "editable_sibling_venv"
source_path = "X:/project-rag-ue-addon"
live_path = "/c/Users/<you>/.claude/plugins/project-rag"  # replace <you> with your username
dist_name = "project_rag_ue_addon"
track_ref = "live"
```

Consumer posture (full two-leg; addon checkout tracks `origin/main`):

```toml
[plugin.mirrors.project-rag-ue-addon]
# editable_sibling_venv: addon source editable-installed into the project-rag HOST venv.
# Full two-leg: git-state advances the addon checkout; venv-state repairs the editable install.
propagation_mode = "editable_sibling_venv"
source_path = "/path/to/project-rag-ue-addon"
live_path = "/path/to/.claude/plugins/project-rag"
dist_name = "project_rag_ue_addon"
track_ref = "origin/main"
```

Note on `dist_name`: use `"project_rag_ue_addon"` (underscore, not hyphen). While `plugin_name.replace("-","_")` coincidentally produces the same string, the explicit value is safer against silent drift if naming conventions change.

**Consumer-path coverage caveat.** The two-leg consumer path (`track_ref = "origin/main"`, full git-state + venv-state) was verified by **code inspection only** — no consumer-machine integration test was run in this session. Future operators should treat the consumer two-leg path as unverified until an integration test is run against a fresh consumer machine.

**Fresh-machine bootstrap — complete step sequence.**

> Before any `machine-local set` command can succeed, the `machine-local/` directory must exist. Neither `setup/install.sh` nor `setup/publish.sh` creates it. This is a known coordinator-side gap — see `install-surface-completeness.md` § Bootstrap gap. **A fresh-machine bootstrap MUST include the directory-creation step.**

Full sequence for a dev machine (venv-only posture):

```bash
# Step 1 — create the registry directory if it does not exist (NOT created by any installer)
mkdir -p ~/.claude/machine-local/

# Step 2 — register the addon entry (dev posture — track_ref=live skips the git leg)
machine-local set plugin.mirrors.project-rag-ue-addon.propagation_mode editable_sibling_venv
machine-local set plugin.mirrors.project-rag-ue-addon.source_path "X:/project-rag-ue-addon"
machine-local set plugin.mirrors.project-rag-ue-addon.live_path "/c/Users/<you>/.claude/plugins/project-rag"
machine-local set plugin.mirrors.project-rag-ue-addon.dist_name project_rag_ue_addon
machine-local set plugin.mirrors.project-rag-ue-addon.track_ref live

# Alternatively — append the TOML block directly to registry.local.toml
# (uses the block form, which is safe to append at end-of-file per the TOML scoping rules
# in machine-local-registry.md § TOML flat-key table-scoping gotcha)
cat >> ~/.claude/machine-local/registry.local.toml << 'EOF'

[plugin.mirrors.project-rag-ue-addon]
propagation_mode = "editable_sibling_venv"
source_path = "X:/project-rag-ue-addon"
live_path = "/c/Users/<you>/.claude/plugins/project-rag"
dist_name = "project_rag_ue_addon"
track_ref = "live"
EOF

# Step 3 — verify by reader lookup (do NOT rely on text-search alone)
machine-local get plugin.mirrors.project-rag-ue-addon.propagation_mode
# Expected: editable_sibling_venv
```

For a consumer machine (full two-leg), substitute `track_ref = "origin/main"` and set `source_path` / `live_path` to the consumer's actual checkout paths.

**`NOT_REGISTERED` failure — cross-link.** If `refresh-plugin-live-install.sh project-rag-ue-addon` or `check-plugin-drift.sh project-rag-ue-addon` exits with `NOT_REGISTERED` (exit 5), it means no `[plugin.mirrors.project-rag-ue-addon]` entry exists in the registry. Follow the bootstrap steps above. This section closes the tracked coordinator-side gap noted in `install-surface-completeness.md` § Three recurring failure shapes, shape 2 — the "Known coordinator-side gap" tracking exactly this `NOT_REGISTERED` pattern for addons editable-installed into a sibling's venv.

**Holodeck-owned plugins — one-way install-only, explicitly NOT in OSS coordinator-claude.** Plugins whose value is entirely contingent on the holodeck/UE-addon infrastructure (e.g. `game-dev`) flow holodeck-repo → holodeck install, one direction only. Nothing flows them outward to `X:/coordinator-claude` or any OSS distribution target. No bidirectional back-prop or merge script is maintained; that asymmetry is structural — it would reintroduce the multi-master state the 2026-05-20 publish→live clobber ban closed.

The adjudicating rule for packaging calls: **coordinator ships a coherent operating system for our colleagues, not generic personae as a contribution to the OSS community.** Domain content whose value requires infrastructure the OSS user does not have belongs to the specialized distribution, not the naked OSS coordinator-claude publish.

**`plugins/claude-unreal-holodeck/` remains git-tracked in `~/.claude/`.** git-tracking on `~/.claude/` is the mechanism by which the entire setup is portable across devices. Gitignoring holodeck plugin files would defeat the meta-repo's portability purpose. Refresh discipline for the holodeck plugin is tracked explicitly via the workday-start drift probe (`check-plugin-drift.sh` Step 1.10 Addon Health). The git-tracking decision is structural, not a per-session choice — do not add the holodeck plugin directory to `.gitignore`. The UE-specialization-migrates-OUT polarity principle that governs *why* holodeck owns this content is documented in `docs/wiki/peer-repo-polarity.md`. The `game-dev` retirement (2026-05-26) is the canonical precedent; see `archive/specs/2026-05-26-retire-game-dev-from-oss.md`.

### 10. Plugin hooks belong in `hooks/hooks.json`, not user-scope `settings.json`

A SessionStart/PreToolUse/etc. hook registered in `~/.claude/settings.json` works on the author's machine but doesn't follow the plugin to marketplace consumers — install lays down the script but never registers the event. Always ship `hooks/hooks.json` alongside the script in the plugin tree so install auto-wires it. User-scope settings is for non-plugin overrides only. Treat this as a portability check at extraction time: grep `~/.claude/settings.json` for any hook entry whose script lives under the plugin tree, and migrate it to the plugin's `hooks/hooks.json` before shipping.

### 11. Port-time absolute-path sweep + sibling-layout convention

> **2026-05-19 amendment — runtime preference order.** Sibling-relative replacement remains the contract for port-time cleanup (this section's scope: extraction-time absolute-path sweep, where the consumer doesn't yet exist to be told about anything else). At **runtime**, however, consumers should prefer the machine-local registry (`machine-local get repos.<name>`) as the primary discovery mechanism, with sibling-relative as the rough-and-ready fallback for the simple sibling-installs-together case. The registry is more reliable across the cases sibling-layout cannot serve (triangular dependencies, multi-drive layouts, deterministic-location requirements, scripts that can't assume their CWD). See `machine-local-registry.md`. **Belt-and-suspenders, NOT co-equal:** registry preferred because not every consumer can run on sibling convention.

Incomplete migrations leak absolute paths (`C:/Users/.../source-repo/...`, `~/work/src/...`) into the vendored code, hooks, and config. Symbol parity passes; runtime breaks on every consumer machine. **At extraction time, sweep absolute repo prefixes across the carved-out tree** and replace with sibling-layout relative references (`../<sibling-repo>/<path>`) where cross-repo references are unavoidable. Document the sibling-layout convention in the plugin's CLAUDE.md so `../sibling/...` is a contract — not an implementation detail downstream consumers have to reverse-engineer.

Grep recipe for the sweep:

```bash
grep -rn "C:[\\/]" <new-plugin-tree>
grep -rn "$HOME/.*[/]src[/]" <new-plugin-tree>
grep -rn "/Users/.*/" <new-plugin-tree>
```

(2026-05-16, project-rag-ue-addon.)

#### Runtime preference order vs. port-time cleanup

Port-time cleanup (the topic of this section) and runtime discovery are **different sub-problems** with different answers. Port-time cleanup replaces absolute paths with sibling-relatives at extraction time because the consumer doesn't exist yet to be told about any other mechanism. Runtime discovery, however, happens on an operator's live machine — and sibling-layout-alone is insufficient for the general case.

**The four failure modes of sibling-layout at runtime:**

1. **It dictates operator filesystem layout.** Every sibling repo must live under one common parent folder. Operators with established conventions (separate drives for engine source vs. tooling, network shares, multi-machine sync setups) cannot comply without restructuring their environment to match the convention.
2. **It cannot represent deterministic locations.** Some things — vendored binaries, large indices, GPU sidecars — genuinely need a fixed absolute path on a specific drive. Sibling-relatives have no way to express "this lives at `E:/UE-content/` regardless of where the repo is cloned."
3. **It silently breaks discovery for downstream consumers.** A repo that uses `../sibling-repo/x` works when cloned into the expected parent, fails opaquely when cloned anywhere else. The failure mode is "file not found" with no remediation hint that the convention was violated.
4. **It does not compose with triangular dependency graphs.** A sibling-relative inside `claude-unreal-holodeck` pointing at `../project-rag-ue-addon/x` assumes both repos share a parent. The moment one triangle vertex moves to a different drive or directory, every sibling-relative pointing at it breaks — not just the path that was moved.

**The preferred runtime discovery order:**

1. **Machine-local registry first** — `machine-local get repos.<name>`. Works in every case: triangular graphs, multi-drive layouts, deterministic-location requirements, scripts invoked from a daemon with no sibling-relative anchor, scripts vendored into one repo but invoked from another.
2. **Sibling-relative fallback** — `../<sibling-repo>/<path>`. The rough-and-ready resort when the registry hasn't been populated yet AND the operator's filesystem layout happens to match the sibling-installs-together convention. Preserves backward compatibility for existing consumers.
3. **Error with remediation hint** — point the operator at `~/.claude/machine-local/README.md` and the specific key they need to set. Never fail silently.

The two are belt-and-suspenders: registry is more reliable (no layout assumptions, works everywhere), sibling-relative is the fallback that keeps existing consumers working until they migrate. Port-time cleanup still uses sibling-relatives as its replacement vocabulary — the extraction-time MUST rule stays, because at that moment the consumer doesn't yet exist. Runtime consumers prefer the registry.

Cross-references: `machine-local-registry.md` (registry doctrine and schema); `cross-repo-citation-conventions.md § Sibling-layout convention` (port-time MUST rule + runtime preference-order amendment).

### 11a. Publish-time content transforms ride the publish-time-transform surface — extend, don't sibling

When a new class of publish-time content transformation is needed (a new persona-name mapping, a new path-rewrite rule, a new identity-token substitution), **extend the existing `publish-time-transform.sh` substitution table — do not author a sibling transform tool.** The publish-time-transform hook is already the registered `post-rsync` transform surface for every publish target; a second sibling tool means two surfaces that must both fire in the right order, two places to register, and a silent gap when one is updated and the other isn't. The substitution table is table-driven precisely so new transforms are table edits, not new tools. (Scan-vs-substitute is the one legitimate two-tool split — see § Scan/Substitution Division of Labor — because detection and correction are genuinely different jobs; a *second corrector* is not.) The script was renamed 2026-05-28 from a path-decay-mismatched name (see `docs/plans/2026-05-28-publish-surface-hygiene.md`); its job had already grown beyond depersonalization, and the rename reflects that.

### 12. Cross-repo port: prefer registration-seam over parallel-surface

When porting a feature from a host repo into a plugin/addon, default to **using the host's registration hookspec or seam** rather than authoring a parallel front-end on the plugin side. A parallel-surface port creates two registration paths the host has to reconcile at runtime and routinely results in one path silently winning while the other looks active. Before authoring a plugin-side surface that mirrors an existing host surface, grep the host's registration corpus (hookspec discovery, pluggy entry points, plugin-manifest readers) and route through the existing seam. (2026-05-16, project-rag-ue-addon.)

### 13. Bootstrap script — a plugin's own `setup` cannot bootstrap itself into Claude Code

A plugin's own `/<plugin>:setup` skill **cannot register the plugin into Claude Code** — the setup skill only runs *after* the plugin is already enabled, so it cannot be the thing that enables it. This is a chicken-and-egg gap: a fresh-clone user has the plugin's files on disk but no `known_marketplaces.json` / `enabledPlugins` entry, so `/<plugin>:setup` is unreachable.

**Every plugin needs a standalone `bin/register-claude-plugin.{py,sh,ps1}` script** (per-platform variants) that:

- Registers the marketplace and enables the plugin **from the user's actual clone path** (not a hardcoded author path).
- Seeds **both** `extraKnownMarketplaces` in `~/.claude/settings.json` AND the `~/.claude/plugins/known_marketplaces.json` cache, so `/reload-plugins` activates the plugin without requiring a cold Claude Code restart.
- Is invoked from the README **before** the `/<plugin>:setup` line — the README order is `clone → run register-claude-plugin → /reload-plugins → /<plugin>:setup`.
- Is **also called early from `scripts/setup.{sh,ps1}`** as a self-heal step, so a user who runs the setup script directly (skipping the README's register step) still gets registered rather than hitting the unreachable-skill gap.

This is distinct from checklist item 8 (installer registers enablement, not just MCP wiring): item 8 is about the shell *installer* touching the three enablement files; this is about the *bootstrap-from-clone* path where no installer has run yet and the plugin must register itself from wherever the user cloned it. (2026-05-18, project-rag-ue-addon.)

## Cross-plugin contract — coordinator never parses peer-plugin config

When coordinator skills need data from a plugin (project root, transport URL, capability registry), the contract surface is **`invoke + read exit code + read stdout`** — pass through the plugin's CLI or daemon. Reaching into `~/.claude.json` from coordinator-side code to reconstruct args a plugin CLI could resolve itself is cross-plugin contract leakage and breaks the next time the plugin migrates transport (e.g. stdio → HTTP, as project-rag did 2026-05-13).

The 2026-05-21 dogfood failure surfaced one instance: `/workday-start` Step 3.6 parsed `mcpServers.project-rag.args[-1]` to extract `--project-root` and crashed with `KeyError` after project-rag's HTTP-shape entry has no `args` array. The fix was not "guard `args[-1]` with a `type == 'stdio'` check" — the fix was to stop parsing project-rag's config entirely and let `project-rag-cli staleness-survey` resolve its own root via env (`PROJECT_RAG_PROJECT_ROOT`) or cwd-walk. See `docs/plans/2026-05-21-coordinator-side-dogfood-followup.md` for the worked example.

The rule generalizes:
- **Pass env vars or cwd to influence resolution.** `PROJECT_RAG_PROJECT_ROOT="$(pwd)" project-rag-cli ...` is the right shape.
- **Do not parse the plugin's MCP entry shape from coordinator.** If you need state the plugin's CLI/daemon doesn't expose, ask the plugin author to add an endpoint (e.g. project-rag's planned `/state` endpoint) — don't reverse-engineer it from the registration.
- **Plugin CLIs own their own resolution chain.** If a CLI doesn't yet resolve its own root, that's an upstream improvement; document it as a plugin-author ask, not a coordinator hack.

This applies symmetrically: plugins should not parse coordinator's internal files (orientation cache, queue files) — same contract, opposite direction.

## Test From a Clean Profile

The single highest-leverage validation: run the install script from a profile that has never used Claude Code before. Anything that "just worked" on the author's machine from prior manual setup will fail loudly. This catches gaps 1, 6, 8, 9, and 10 in one pass.

## Atlas Drift After Extraction

When a plugin moves to a standalone repo, the consumer-side architecture atlas, file-index paths, and MCP-tool prefixes go stale silently — greppable-by-old-name is not the same as broken-by-old-name. Old paths still resolve in cache, old tool prefixes still appear in agent-prompt examples, and nothing surfaces the drift until a new contributor reads the atlas and gets pointed at a path that no longer exists.

Plugin-extraction PRs need an explicit atlas-sweep step before merge: grep the consumer repo for the old plugin path, the old MCP tool prefix, and the old marketplace name; update or repoint each hit; verify the architecture atlas's plugin section reflects the new layout. Treat this as part of the extraction PR itself, not a follow-up — the cost of doing it later is ambiguous "is this stale or current?" reads from every downstream consumer until someone audits.

## CRLF/LF Verification on Percolation

Percolation from a Unix-authored source repo to a Windows consumer (or vice versa) silently swaps line endings under the wrong git config, producing whole-file diffs that read as no-op edits but change every line of every file. "Agent reported clean" is not enough — verify percolation by per-file diff with `git diff --stat` and a spot-check on a handful of files; a clean diff under `core.autocrlf=true` may hide the entire reformatted file. Establish `.gitattributes` rules early, and run a verification pass after every cross-platform percolation.

**Contract: per-file `git diff --stat`, not aggregate "no changes."** CRLF/LF differences on Windows can produce a clean-looking percolation summary that doesn't match upstream at the file level — the line-ending swap touches every byte but registers as zero semantic changes under some diff modes. Per-file `git diff --stat` is the verification contract; an aggregate "no changes" report from the percolation agent is advisory only.

## Persona-Name Guard on Percolation

The meta-repo (`~/.claude/`) authors files with persona display names — Patrik, Sid, Camelia, Palí, Fru, Zolí, YK — because that's how the human PM thinks of the reviewers. The publish repo (`X:/coordinator-claude` or any open-source consumer mirror) ships nameless: reviewers are referred to by articulated role labels (the Staff Engineer, the Game Dev Reviewer, etc.), with naming offered as an opt-in install step. Personae ≠ names — the doctrine is in `docs/evolution/03-personas-as-ergonomics.md` (publish-repo copy). Without a guard, percolation reintroduces names silently, since the meta-repo source still has them.

Two paired tools enforce the boundary:

- **Publish-repo CI gate.** `.github/scripts/check-persona-names.py` runs as a tracked-files scan auto-discovered by `run-all-checks.py`. Hard-fails any commit/PR where canonical-layer files (`*.md`, `*.sh`, `*.py`; excludes `archive/`, `tasks/`, `experiments/`, `evals/`, `docs/{plans,research,decisions,specs}/`) contain bare persona display names. Suppression: `# noqa: persona-names` inline, or `.github/.persona-names-allowlist` file-based (`filepath:line_number` per line).

- **Meta-repo registered hook.** `setup/percolate-hooks/<target>/post-rsync/10-transform.sh` is a thin wrapper around `publish-time-transform.sh` in `~/.claude/plugins/coordinator-claude/coordinator/bin/`. The depersonalize binary itself supports `--check` (exit 1 on hits) or `--fix` (in-place rewrite to role labels, with `.bak` backups). The hook receives the destination path as `$1` and the synced-files list via stdin (newline-delimited), then `--fix`es each `*.md`/`*.sh`/`*.py` file. Registered for `coordinator-claude` and `deep-research-claude` (open-source publish targets); deliberately NOT registered for `holodeck` (keeps persona names natively). Only the hook lives meta-repo-local; the binary it calls is shipped with the coordinator plugin and percolates with it. The `--fix` mode handles the common "the X" / "The X" article cases including the "The the X" double-article it would otherwise produce.

**`publish.sh` is the authority for percolation — manual `cp` is wrong.** Percolating to `coordinator-claude` (or any registered publish target) means running `bash ~/.claude/setup/publish.sh <target>`, not copying files by hand. Manual `cp` bypasses the depersonalize pipeline, the content-leakage scan, and the `.percolate-ignore` filter — the resulting publish repo may contain persona names, local paths, or excluded files the author didn't intend to ship. The publish-targets list at `setup/publish-targets.sh` is the authority; if a target is missing from it, register it there rather than working around it with ad-hoc copies.

> **Double-prefix trap — source layout ≠ target layout; never re-append the plugin subpath (2026-05-28).** The recurring failure behind hand-built paths is conflating the *source-side* layout with the *target-side* layout. Source side, the coordinator plugin lives at `~/.claude/plugins/coordinator-claude/coordinator/...`; publish side, it lives at `X:/coordinator-claude/plugins/coordinator/...` — **`plugins/coordinator/`, not `plugins/coordinator-claude/coordinator/`.** A hand-built `cp` that takes the publish-repo root `X:/coordinator-claude` and appends the *source* relative path produces the doubled `X:/coordinator-claude/plugins/coordinator-claude/coordinator/...` (two stale entries of exactly this shape were found frozen in `.claude/settings.local.json` and removed 2026-05-28). The same trap bites runtime tooling: the `coordinator-claude` registry mirror's `live_path` (`~/.claude/plugins/coordinator-claude/coordinator`) is **already the full coordinator root** under `propagation_mode = "source_is_live"` — any consumer that treats it as `~/.claude` and re-appends `plugins/coordinator-claude/coordinator` doubles it (symptom: `Get-ChildItem ...coordinator\plugins\coordinator-claude\coordinator` cannot-find-path). Rule: `live_path` is the root, not a base to join onto; and the only correct way to reach a target path is to let `publish.sh` map source→target — never hand-construct it.

Workflow during percolation:

1. Run `bash ~/.claude/setup/publish.sh <target>` (a.k.a. percolate / push-to-publish-repo) — or `/percolate <target>` for the dry-run-confirm-real-run skill wrapper.
2. `publish.sh` discovers and runs every executable script in `setup/percolate-hooks/<target>/{pre-rsync,post-rsync,pre-ci}/*.sh` in lexical order at the corresponding boundary. The depersonalize hook fires automatically at `post-rsync` for any target with one registered. Failure-semantics: non-zero hook exit aborts the publish; post-rsync abort = destination partially mutated, recovery is to fix the hook and re-run (`--check`/`--fix` is idempotent).
3. CI on the publish repo re-runs `python .github/scripts/check-persona-names.py` on push as the safety net — even if a hook is mis-registered, the gate catches regressions.

To add or modify a hook for a target: place an executable `*.sh` script under `setup/percolate-hooks/<target>/<hook-point>/`. Numeric prefixes (`10-`, `20-`) order execution. Authoring help: see `docs/wiki/percolate-setup.md` (walked by `/percolate` Branch 0 and `/setup` percolation phase) — it scaffolds the hook directories with `.gitkeep`. Registration is convention-based discovery — no manifest required.

Source-side publish-content policy (`.percolate-ignore`) lives at `$SOURCE_DIR/.percolate-ignore` (gitignore-shaped, simplified subset — `**/` not supported). `publish.sh` `sync_mirror` honors it in both copy and delete phases. Details below.

**`.percolate-ignore` policy details:**

- **Location:** source plugin root (e.g. `~/.claude/plugins/coordinator-claude/.percolate-ignore`), one per `SOURCE_DIR` in `publish-targets.sh`, parallel to `.gitignore`. Source-keyed, not target-keyed — authoring agents must see the policy from their cwd; a target-keyed file makes the policy invisible to authoring-time scrutiny.
- **Format:** gitignore-shaped lines. Simplified-subset semantics — `**/` is NOT supported under bash `[[ ]]` matching. Supported: plain `dir/` (prefix-anchored), `*.ext` (basename match), explicit paths. Blank lines and `#`-comments ignored.
- **Default scaffold body:** `_archived/`, `scratch/`, `*.bak`, `*.tmp`.
- **Integration:** `sync_mirror` reads once per source plugin at top of sync; `is_ignored()` helper applies in both copy and delete phases. The inline `_archived/` skip at publish.sh:150 and :192 is retained as defense-in-depth alongside `.percolate-ignore`.
- **Coverage drift detection:** `/percolate` Step 2 surfaces files newer than `.percolate-ignore` mtime — a signal the policy may not have been reviewed since those files were added.
- **Surface B coupling:** Surface B (mirror+depersonalize oscillation) may redesign `sync_mirror`; the inline `_archived/` skip must be re-evaluated alongside that work. `cp -p` / `rsync -t` preserve mtime through any staging dance; naive `cp` resets mtime and makes every source file appear "newer than policy" on next dry-run.

See `docs/wiki/percolate-setup.md` (walked by `/percolate` Branch 0 and `/setup` percolation phase) for the full audit-and-scaffold procedure, including classification taxonomy and grey-zone handling.

The vocabulary table (also in `docs/customization.md` "Reviewer Roles" of the publish repo): Patrik → the Staff Engineer; Zolí → the Director of Engineering; YK → the VP-Product Reviewer; Sid → the Game Dev Reviewer; Palí → the Front-End Reviewer; Fru → the UX Reviewer; Camelia → the Data Science Reviewer.

### Hook Registry Architecture

The hook registry is conventional-discovery, no manifest required. Key mechanics:

- **Hook-point directory:** `setup/percolate-hooks/<target-name>/{pre-rsync,post-rsync,pre-ci}/`. Pre-rsync receives `$1=source_dir $2=target_dir`; post-rsync receives `$1=target_dir` and synced-files list via stdin; pre-ci receives `$1=target_dir`.
- **Ordering:** lexical sort; numeric prefixes (`10-foo.sh`, `20-bar.sh`) order execution. Scripts invoked via `bash "$hook"` (not sourced — isolation). Executable bit NOT required.
- **Empty-glob safety:** MUST use `shopt -s nullglob` scoped in subshell OR `[[ -e "$hook" ]] || continue` guard. Raw `*.sh` glob with no files expands literally under bash.
- **Failure semantics:** non-zero hook exit aborts publish (`set -euo pipefail`). Post-rsync abort = destination partially mutated. Recovery: fix the hook and re-run `/percolate` — depersonalize is idempotent.
- **Out-of-percolation guard:** `setup/percolate-hooks/` lives at meta-repo root, OUTSIDE every `SOURCE_DIR`. Runtime guard MUST assert `$hooks_dir` is not a subpath of `$SOURCE_DIR`.
- **Hook discovery logging:** even in non-dry-run, emit one line per hook-point: `"  <hook-point> hooks: <comma-sep-names or '(none)'>"`.
- **Depersonalize hook is a thin wrapper** calling `publish-time-transform.sh`. Registered as `post-rsync/10-transform.sh` for `coordinator-claude` and `deep-research-claude`; deliberately absent for `holodeck`. Only the hook lives meta-repo-local; the binary it calls ships with the coordinator plugin and percolates with it.

### /percolate Skill — Step Sequence and Gates

The `/percolate` skill wraps `publish.sh` with a structured confirmation gate. The seven steps are:

1. **Pre-flight:** verify target name exists in `setup/publish-targets.sh`. If not, list registered targets and exit non-zero.
2. **Dry-run:** `bash ~/.claude/setup/publish.sh --dry-run <target>`. Capture stdout + exit code. Compute coverage-drift panel: `find "$source_dir" -type f -newer "$source_dir/.percolate-ignore" 2>/dev/null | head -20` (surface if non-empty; shows files changed since policy was last reviewed).
3. **PM confirmation gate:** fires iff a deletion is present, OR dry-run touches ≥10 files, OR dry-run touches sensitive paths (`CLAUDE.md`, `settings.json`, `hooks/`, `agents/`). If dry-run reports zero changes: skip gate AND real run, but still run CI smoke (Step 5).
4. **Real run:** `bash ~/.claude/setup/publish.sh <target>`. Surface any `WARNING: REVIEW` lines from Phase 4 verbatim.
5. **Optional CI smoke:** if target repo has `.github/scripts/run-all-checks.py`, run it from repo root. Skip silently if missing. Call `run-all-checks.py`, not `check-persona-names.py` directly.
6. **Unified summary** (4 lines): dry-run exit / real-run exit or "skipped (no-op)" / CI-check exit or "n/a" / overall verdict. `PASS` = all exits 0 AND no Phase 4 REVIEW lines; `PASS-WITH-WARNINGS` = all exits 0 AND REVIEW lines present; `FAIL` = any non-zero exit.
7. **Stop on first failure:** print failing step's stderr + one-line manual-recovery hint.

The skill does NOT call `publish-time-transform.sh` directly, does NOT modify `publish.sh`/`publish-targets.sh`, does NOT commit/push publish-repo results. All triggers (percolate, push to publish repo, publish to `<target>`, sync meta to publish) map to this skill.

**Dogfood discipline:** a clean-tree no-op pass does NOT satisfy convergence. The acceptance-test sequence must include: (1) clean no-op, (2) trivial-edit happy path, (3) sensitive-path edit forcing confirmation, (4) bad-target name (Step 1 exit), (5) missing source-dir (Step 7 failure), (6) CI smoke on clean target, (7) verify summary line counts in all cases.

**Cygwin/fork-exhaustion note:** `publish.sh` is fork-heavy (grep/sed loops over large trees). If a dry-run dies at ~9 KB output with "fork: retry: Resource temporarily unavailable" the shell session is wedged — restart the session, do not re-invoke. Script timeouts: 20s maximum for percolation scripts. Re-invoking on a wedged shell produces zero-byte output files.

> **Publish-repo follow-up (2026-05-17):** The `Zolí → the Director of Engineering` mapping replaces the prior `Zolí → the Ambition Advocate` mapping. The publish repo's `docs/customization.md` "Reviewer Roles" table, any `check-persona-names.py` allow-list, and any personalizer script that maps role labels back to user-chosen names must be updated to match — `the Ambition Advocate` is retired, `the Director of Engineering` is the new canonical role label. Personalizers should let the new user pick any name for the DoE role; the title carries the rank, the name is cosmetic. Previously-published copies of files containing `the Ambition Advocate` will need a search-and-replace at next publish.

## Auxiliary Sync — Publish-Repo Top-Level `docs/wiki/`

**Auxiliary sync — publish-repo top-level `docs/wiki/`.** The publish repo also carries a public-facing wiki at `<publish-repo>/docs/wiki/` (separate from the plugin tree under `<publish-repo>/plugins/coordinator/docs/wiki/`). This auxiliary surface is synced from the plugin's `docs/wiki/` via a second publish-target row (`coordinator-claude-toplevel-wiki`) with `flat-mirror` mode plus a publish-native allowlist. The allowlist lives at `setup/percolate-hooks/coordinator-claude-toplevel-wiki/post-rsync/publish-native-allowlist.txt`; files named there are backed up before rsync and restored after, so publish-native authoring on the public side (including uncommitted edits) survives meta-repo syncs. Verification gate at `30-verify-toplevel-wiki.sh` enforces canary survival, forbidden-shape grep, and rewrite-target sanity.

**Allowlist lives in `setup/percolate-hooks/<target>/post-rsync/` (hook-local) rather than in the publish repo** because (1) the consumer is the meta-repo hook — locality with the consumer beats locality with the protected data; (2) it documents the allowlist mechanism alongside the hook, making the existence of an allowlist visible to anyone reading `percolate-hooks/`; (3) future plugins with publish-native allowlists organize under one tree.

**When to add a file to the allowlist:** the file is authored on the publish-repo side (its git history lives in `/x/coordinator-claude/`), and it is not a copy of any plugin wiki. Today: `task-tier-guidance.md` is the sole entry.

**When NOT to use the allowlist:** if a plugin-side wiki and a publish-side wiki need to converge into one canonical source, move the publish-side authoring back to the plugin and remove from allowlist. The allowlist is for genuinely divergent lifecycles, not for resisting normalization.

Spec backlink: `docs/plans/2026-05-18-publish-repo-toplevel-wiki-sync.md` § Shape decision A*.

### `dist/publish-repo-docs/` corner and bidirectional `.percolate-ignore`

A fourth authoring source (in addition to the three listed in `## Publish-Repo Content Authoring`) handles publish-repo-owned top-level `docs/*.md` files that are not driven by the plugin tree. `coordinator/dist/publish-repo-docs/` controls only `agent-install.md` (with a "if you had to patch to install, send it back" section). A bidirectional `.percolate-ignore` inside this source dir protects every other top-level publish-repo `docs/*.md` from the flat-mirror delete-not-in-source pass — preventing the sync from removing docs whose lifecycle lives in the publish repo. A `maxdepth-1` depersonalize post-rsync hook is scoped to never touch `docs/wiki/` or other targets' subdirs.

### Publish-Repo Content Authoring (setup scripts and top-level docs)

**The publish repo is a percolation target, not a source of truth.** All publish-repo content is authored in Claude Central (`~/.claude/`) and percolated outward via `setup/publish.sh`. Editing the publish repo directly is always wrong — it bypasses the planning, review, and doctrine pipeline that governs the rest of the coordinator system.

The four authoring flows:

- `plugins/*` ← `~/.claude/plugins/coordinator-claude/` (existing `coordinator-claude` mirror target)
- `docs/wiki/*` ← `…/coordinator/docs/wiki/` (existing `coordinator-claude-toplevel-wiki` flat-mirror target — the established precedent for this section)
- `setup/*.sh` ← `…/coordinator/dist/publish-repo-setup/` (new `coordinator-claude-publish-repo-setup` flat-mirror target)
- top-level docs ← `…/coordinator/dist/publish-repo-toplevel/` (new `coordinator-claude-publish-repo-toplevel` flat-mirror target)

**Why this matters.** Direct publish-repo edits drift silently across sessions: they accumulate as orphan branches, rot when the next percolation run overwrites them, and compound without any doctrine trail. The 2026-05-21 audit (cross-repo memo at `archive/cross-repo/`) found three orphan setup scripts and eight orphan top-level docs that had been edited in the publish repo over multiple sessions; the back-percolation work documented in `docs/plans/2026-05-21-back-percolate-publish-repo-orphans.md` is the corrective.

**Flat-namespace note.** The `dist/publish-repo-*` naming is a flat namespace. Future siblings (e.g. `dist/publish-repo-workflows/` if `.github/workflows/` ever back-percolates) are parallel entries, not nested under any current member. Nesting under an `oss-distribution/` umbrella is intentionally declined: the coordinator system has multiple publish repos (`coordinator-claude` and `deep-research-claude`), and the explicit publish-repo prefix is clearer than a presumed-singular umbrella.

**Recovery — when a publish-repo edit happens anyway:**

1. Copy the edited file from the publish repo back into the appropriate `coordinator/dist/publish-repo-*/` source directory. Manual `cp` is correct here — back-percolation is the genuine exception to "publish.sh is the authority," which governs the source → publish-repo direction only.
2. Commit in Claude Central with a `back-percolate:` subject prefix.
3. Re-run `bash setup/publish.sh <target>` to verify the source-of-truth now drives the publish-repo state.
4. Surface the incident in `tasks/lessons.md` if the edit was substantive, so the doctrine compounds.

**Per-target `.percolate-ignore`.** Publish-repo-owned infra files (e.g. `.gitignore`, `.python-version`, the publish repo's own `CLAUDE.md`) are protected via `dist/publish-repo-toplevel/.percolate-ignore`. These files remain owned by the publish repo by design; back-percolating them is a separate, per-file decision, not an automatic consequence of this doctrine.

## Scan/Substitution Division of Labor

Two tools enforce the publish boundary; they solve different failure modes and are not interchangeable:

- **`publish-time-transform.sh --fix`** (substitution): rewrites known persona names, identity tokens, and dev-tree plugin paths that were deliberately used in the meta-repo. Catches static vocabulary the author knew was persona-named or dev-tree-scoped. Table-driven; must be updated when new identity tokens or path patterns are added.
- **Percolate Step 2c content-leakage scan** (per-publish detection): catches dynamic drift — a path slipping into a wiki body, a peer-repo name embedded in a snippet, a machine name in a code comment. These accumulate through normal authoring between substitution-table updates; no static list can anticipate them.

The substitution hook handles the expected case; the per-publish scan handles the unexpected case. Removing either leaves the corresponding failure class uncaught. Per-publish detection earns its keep on every run because authoring drift precedes substitution-table updates; do not treat the scan as redundant once the hook is in place.

Scan-vs-substitute division of labor: the content scan (regex inventory pass) is for *detection*; the substitute pass is for *correction*. Scan earns its keep on day 1 because it catches new patterns the substitute hasn't been taught — a `WARN:` line in scan output is a signal to extend the substitute, not silenced noise.

When `publish.sh` uses `rsync --delete` to mirror source-to-dest, add `--exclude=<pattern>` for files the dest has already shipped that the source intentionally lacks (e.g. dest's own README, CHANGELOG generated by release tooling). Without excludes, `--delete` strips the dest's local artifacts.

**Path-rewrite enumeration.** The static floor of five plugins for path rewriting is: `coordinator`, `data-science`, `deep-research`, `game-dev`, `web-dev`. `holodeck-control` and `holodeck-docs` are NOT in the publish tree. The discovery step enumerates `$TARGET/plugins/*/` to pick up plugins added since the floor was last updated. The self-validation guard: if static path-mapping seed patterns start with `plugins/` and don't contain `coordinator-claude`, the substitution has already run — fail loud with restore-from-source instructions.

**Path-rewrite order within depersonalize.** Path rewrite runs BEFORE persona substitution (structural normalization first, naming second).

**Post-percolate verification gate.** After `--fix`, `10-transform.sh` greps for residual `plugins/coordinator-claude` in `.md` files under the publish tree (excluding `archive/`, `tasks/`, `docs/plans/`, `docs/research/`, `docs/decisions/`, `docs/specs/`). Any hit → exit non-zero.

**Renamed 2026-05-28.** `publish-time-transform.sh` was renamed from a path-decay-mismatched name (see `docs/plans/2026-05-28-publish-surface-hygiene.md`; `git log -- bin/` carries the literal predecessor); the rename closed the naming debt introduced by the path-rewrite addition in `docs/plans/2026-05-18-publish-time-path-rewriting.zoli-review.md`. Hook callers were also renamed from `N-depersonalize.sh` to `N-transform.sh` for consistency. NOTE: an earlier draft of this note claimed the hooks were single-seam (one variable making the rename one line per hook) — that was wrong. Each hook hardcodes the consumer-script name ~10× across fallback resolution paths, error messages, and SYNC-WITH comments; a full grep-and-substitute per hook was required (per Patrik Finding #1 on the rename plan).

## Path-Rewrite Mechanics at Percolate Time

The substitution pass in `publish-time-transform.sh --fix` handles more than persona names — it also normalizes dev-tree plugin path references into publish-tree form. This collapse happens at `post-rsync` as part of the same hook invocation.

**Dev-tree → publish-tree path form.** In the meta-repo, plugin files are authored under `plugins/coordinator-claude/<plugin>/` (one extra segment for the upstream source repo). The publish tree drops that segment: the canonical install path is `plugins/<plugin>/`. The substitution table rewrites every occurrence of the dev-tree form to the publish-tree form across all percolated `.md`, `.sh`, and `.py` files.

**Two-segment collapse for the central plugin.** The coordinator plugin itself lives at `plugins/coordinator-claude/coordinator/` in the dev tree. At percolate time this collapses to `plugins/coordinator/` — a two-segment reduction, not one. The substitution table carries this as a separate rule from the general one-segment drop, because the intermediate `coordinator-claude/coordinator` path is the coordinator plugin's dev-side nesting and must not survive into publish artifacts.

**Plugin enumeration — floor plus discovery.** The substitution pass seeds its path-rewrite table from a static floor of five known plugins: `coordinator`, `data-science`, `deep-research`, `game-dev`, `web-dev`. It then discovers additional published plugins by enumerating `$TARGET/plugins/*/` in the destination tree. The static floor is a correctness guarantee for the core set; the enumeration step picks up plugins that were added since the floor was last updated without requiring a table edit.

**Idempotency.** Re-running `--fix` on an already-percolated tree produces no further changes. Path references already in publish-tree form (`plugins/<plugin>/`) do not match the dev-tree patterns, so the substitution is a no-op on a clean destination.

**Post-percolate verification gate.** `10-transform.sh` runs a `--check` pass after `--fix` and asserts zero residual occurrences of `plugins/coordinator-claude` in any `.md` file under the publish tree. A non-zero result aborts the publish with a clear diagnostic. This gate locks the wiki rule to the substrate: if the substitution table falls out of sync with a new dev-tree path pattern, the abort surfaces the gap immediately rather than silently shipping a malformed reference.

## Authoring Discipline — No Local Paths in Percolation-Destined Content

The `publish-time-transform.sh` hook and the percolate Step 2c content scan are **safety nets for inherited content**, not authoring licenses. When writing any doc, skill, or agent file that will be percolated, never hardcode local working-tree paths — even as "doctrine source" citations. Use abstract repo references instead:

- Wrong: `X:/coordinator-claude/docs/wiki/foo.md`
- Right: `docs/wiki/foo.md` (relative to plugin root) or `plugins/coordinator-claude/coordinator/docs/wiki/foo.md` (from meta-repo root)

Local path leaks survive substitution-table updates (new paths not yet in the regex) and require hand-edits at percolation time. The drift is silent until the per-publish scan catches it. Authoring discipline prevents the class entirely; the hook is the last line of defense, not the first.

Local working-tree paths (`C:/Users/<name>/...`, `/home/<name>/...`) in authored content (skills, agents, wikis) are an authoring-discipline failure, not a depersonalize-substitution failure. The depersonalize hook is defense-in-depth; the primary discipline is: don't write your local path into shared content in the first place. Use `~/.claude/...` or relative paths.

## Versioning Extraction Churn

Removing one optional plugin from a distribution is a MINOR bump, not MAJOR. Semver major implies breaking changes to core API or to every consumer's setup — not "we removed an opt-in surface that was enabled-by-default in our own settings." Reserve MAJOR for the extraction event itself when it changes the install-script contract (path layout moves, MCP server names rename, env-var shape changes that consumers must mirror). Iterative cleanup of the extracted plugin's own surface is MINOR or PATCH.

## Release Notes on Every Merge

At LLM speeds, the human heuristic of "batch small release notes" no longer applies — per-merge release notes are cheap enough that skipping them creates audit gaps with no cost savings. Every merge to main gets a release-notes entry, regardless of size. This discipline is encoded in `/merge-to-main` Step 1.5 and applies equally to `/publish-coord-claude`, `/publish-deep-research`, and any other release or publish skill: write the entry at merge time, not retrospectively.

## Plugin-Bundled Wiki Authoring Direction

Plugin doctrine wikis live ONLY at `<plugin>/docs/wiki/<name>.md` — the bundled copy IS the canonical source. There is no dev-side mirror at `~/.claude/docs/wiki/` for plugin-doctrine wikis. Editing the bundled copy directly is the correct and only authoring verb; any dev-side file at that path is a write-direction trap.

**Why single-tree?** Practice evidence: after 9 days of the original dual-tree model, 5 wikis existed only in the bundled tree; 2 same-day drift instances occurred; the dual-tree invariant fails under concurrent authoring because executors read from bundled and write back. Maintaining a two-tree invariant at authoring frequency costs more than it saves.

`sync-plugin-wiki.sh` semantics: if `~/.claude/docs/wiki/<name>.md` EXISTS → exit 5 (dev-side mirror of plugin-doctrine wiki — delete to restore single-tree invariant). If only bundled exists: OK. If neither exists: WARN.

The `PreToolUse` hook `block-dev-side-mirror-wiki.sh` blocks Write/Edit/NotebookEdit to `~/.claude/docs/wiki/<name>.md` when `~/.claude/plugins/*/docs/wiki/<name>.md` exists. Override: `COORDINATOR_OVERRIDE_WIKI_MIRROR=1`.

## Plugin-Bundled Wiki Reference Convention

**Canonical decision (2026-05-06):** Plugin doctrine wikis (wikis cited from plugin files like SKILL.md, CLAUDE.md, agent prompts) MUST live inside the plugin at `<plugin>/docs/wiki/<name>.md`. References use the path **relative to the plugin root**.

**Rationale:** Wikis at `~/.claude/docs/wiki/` resolve only on the authoring machine. Marketplace consumers install the plugin into their `~/.claude/plugins/cache/<marketplace>/<plugin>/<sha>/`. References to `docs/wiki/<name>.md` from plugin files must resolve against the plugin's own directory, not the consumer's home directory (which does not contain the demoted content).

**Convention:**
- Plugin doctrine wikis → `plugins/<plugin>/docs/wiki/<name>.md` (bundled inside plugin)
- Project-level wikis (atlas, codebase-specific patterns) → consumer's `~/.claude/docs/wiki/` (NOT cited from plugin files)
- References in plugin files → `docs/wiki/<name>.md` resolved relative to plugin root

**Sync:** `sync-plugin-wiki.sh` during `/update-docs` (auto-discovers new wiki citations from plugin files and confirms bundled copies exist).

Source: `archive/specs/2026-05-06-wiki-bundling-for-marketplace-consumers.md`.

## Five-Axis Extraction Checklist — Resource-Path Walk

When extracting a plugin that loads its own assets at runtime (templates, data files, snippets, JSON manifests), the path-resolution code is the highest-risk surface. Pre-extraction the plugin sat next to its consumers and could rely on relative paths from the source-repo root; post-extraction it ships into `~/.claude/plugins/cache/<marketplace>/<plugin>/<sha>/` and those relative paths now resolve to whatever happens to be next to the consumer's cwd.

Five resource-loading axes must be audited at extraction time:

1. **`__file__`-relative reads.** All `Path(__file__).parent / "data" / ...` and `os.path.dirname(__file__)` lookups must resolve inside the plugin tree. Grep `__file__` and inspect each. The translation rule: `Path(__file__).parents[N] / "subdir"` where N is whatever climbs to the plugin root, never beyond.
2. **CWD-relative reads.** Any `open("data/...")`, `Path("config.json").read_text()` is a bug — drop or convert to `__file__`-relative.
3. **Env-var-rooted reads.** `${CLAUDE_PLUGIN_ROOT}` is the supported anchor; anything else (`${HOLODECK_HOME}`, `${PROJECT_RAG_ROOT}`) is a leak.
4. **Sibling-repo reads.** A pre-extraction plugin often peeked at `../<other-plugin>/data/*`. Post-extraction the sibling tree is on a different filesystem path or absent entirely. Grep `..` in path joins.
5. **Hardcoded absolute reads.** `/Users/<name>/...`, `C:\Users\<name>\...`, `X:\<vendor>\...` — never survive consumer install. The depersonalize hook does NOT cover these; authoring discipline does.

The grep pass is mechanical: `rg -n '__file__|os\.path\.dirname|Path\(__file__\)|CLAUDE_PLUGIN_ROOT|\.\./|/Users/|C:[\\/]Users'` across the extracted plugin. Each hit needs a one-line audit before merge.

## Manifest Scan Includes Authoring-Time Outputs by Default

A plugin's release manifest (or percolate `.percolate-ignore`) typically does a recursive walk of the plugin tree to enumerate shipped files. Without explicit excludes, the walk pulls in `tasks/`, `archive/`, `.last-cleanup`, scratch dirs, and `.tmp.*` orphan files from Edit-tool crashes — i.e. the author's working state ships into the consumer cache. Defense: anchor the manifest scan to a deliberate include list (`commands/`, `skills/`, `agents/`, `hooks/`, `docs/wiki/`, `bin/`) rather than "everything under root minus a few excludes." The exclude approach is forever-incomplete; the include approach is auditable.

## Marketplace Source-Path Registrations

When a marketplace entry's `source` field points at a local development tree (`file:///X:/coordinator-claude` or `git+file://...`) rather than a published URL/tag, every consumer install pulls whatever HEAD that tree happens to be at — not a versioned artifact. The marketplace JSON looks correct, `claude plugin install` succeeds, but version-pinning is structurally impossible. Audit `~/.claude/plugins/known_marketplaces.json` and any `marketplace.json` for `file://` / source-tree `source` fields before shipping. For real distribution, the `source` must resolve to a published location (GitHub release, tagged ref, or wheel URL) consumers cannot mutate locally.

## LSP-Style Plugins Without `plugin.json`

Some plugins distributed alongside language servers (or as LSP extensions of the host) ship without a `plugin.json` manifest because the host launches them via a separate config layer. Claude Code's plugin system requires `plugin.json` at the plugin tree root for enablement to take effect — its absence makes `enabledPlugins["<name>@<marketplace>"]` a silent no-op. When extracting an LSP-adjacent surface as a Claude Code plugin, generate `plugin.json` even if the LSP host doesn't need one. Symptom: install reports success, marketplace shows the plugin, but `claude /` lists none of its slash commands.

## Competing Plugins in Overlapping Domains

When two plugins both expose game-dev (or any overlapping-domain) routing — for instance a `game-dev@coordinator-claude` and a stack-specific `holodeck-control@claude-unreal-holodeck` — their description-token surfaces and slash-command names collide silently. Both load, both contribute deferred-tool prefaces, and the EM picks whichever description matches first. Defense: gate domain-overlapping plugins via per-project enablement (`docs/wiki/per-project-plugin-gating.md`), so only one set is active in any given project context. Same-marketplace plugins compete the same way — overlap is a function of description, not provenance.

**When competing plugins define the same agents or personas, keep them in sync.** If two plugins both define (for example) `staff-game-dev` (Sid), whichever marketplace loads later wins — the losing copy's tool surface is what the EM actually gets. When patching one copy, diff the other: divergence between the two manifests as silent tool-availability regressions (e.g. `Write` permission present in one but absent from the other). Per-project enablement (above) is the structural fix; cross-plugin diff discipline is the safety net while both copies coexist.

## Module-Top Unconditional Cross-Package Imports Break Graceful-Fail

Re-export shims at port-out boundaries that do `from sister_pkg import X` at module top crash hosts that don't have the sister package installed — even when the host never invokes the re-exported symbol. Lazy-only smoke checks (`if __name__ == "__main__": import sister_pkg`) miss it because the failure fires on `from shim import anything`, before the lazy guard runs.

**Pattern for every port-out shim:** wrap the module-top cross-package import in `try / except ImportError`, expose a sentinel (`HAS_SISTER = True/False`) and a clear error from the re-exported callable when called without the sister installed:

```python
try:
    from sister_pkg import _impl
    HAS_SISTER = True
except ImportError:
    HAS_SISTER = False
    _impl = None

def public_symbol(*args, **kwargs):
    if not HAS_SISTER:
        raise RuntimeError(
            "public_symbol requires sister_pkg; not installed in this host"
        )
    return _impl(*args, **kwargs)
```

Pair with a **host-only-import smoke test in CI**: a test that imports the shim package against a synthetic environment where the sister is *not* installed, and asserts no `ImportError` at import time (only at call time). Without that test, the bug only surfaces on a consumer host the author never tested against.

## GitHub Org Rename Breaks `claude plugin update`

When a plugin's GitHub org/repo is renamed (`old-org/plugin` → `new-org/plugin`), GitHub auto-redirects `git clone` but `claude plugin update <plugin>` may still hit the cached old URL in `known_marketplaces.json` and silently fail (or worse, succeed against a stale fork that took over the old name). Defense: at rename time, push a final commit to the old repo whose README says "moved to <new>"; update `known_marketplaces.json` `source` URL across all consumers via a one-shot migration note; mention in the release notes that consumers must re-run `claude plugin marketplace remove/add` to pick up the new URL.

**Unexpected 404s from `gh` calls: check for org rename before blaming the handle.** When a sub-repo's remote `gh` CLI calls return 404 unexpectedly, verify whether the GitHub org has been renamed before assuming the stored handle is wrong. Org renames redirect on the web UI but break the REST API — `gh repo view old-org/plugin` fails while the browser silently forwards. Stale-handle diagnosis: `gh api repos/old-org/plugin` vs `gh api repos/new-org/plugin`; update `known_marketplaces.json` and local git remote after confirming.

## Operational Gotchas — 2026-05-17 Batch

- **Plugin disable ≠ uninstall.** Disabling a plugin in `settings.json` doesn't remove the cache; both the cache entry and the settings flag need clearing.
- **`installed_plugins.json` is managed.** Hand edits get reverted by the plugin system. Use `claude plugin` commands.
- **MCP scope precedence: Local > Project > User > Plugin.** User-scope MCP entries silently override plugin `.mcp.json` of the same name. Fix: `claude mcp remove <name> --scope user`.
- **Plugin hooks belong in `hooks/hooks.json`, NOT user-scope `settings.json`.** Hooks in user settings break marketplace distribution.
- **Pure-LSP plugins don't need `.claude-plugin/plugin.json`.** A pure-LSP plugin is configured via `mcp` settings or LSP host config — it does not participate in the Claude Code plugin enablement system. Adding a `plugin.json` shim creates a phantom entry in `installed_plugins.json` that decays into orphan state when the LSP plugin is uninstalled via its own tooling. Contrast with LSP-*adjacent* Claude Code plugins (see `## LSP-Style Plugins Without plugin.json` above), which do need `plugin.json` because they integrate with the Claude Code plugin lifecycle.
- **`claude plugin update` defaults to user scope.** When running `claude plugin update <name>` from inside a project directory, the command updates the user-scope installation, not the project-scope one — the default does not infer scope from cwd. If the plugin was installed at project scope (e.g. `claude plugin install <name> --scope project`), pass `--scope project` explicitly on update or the user-scope version is bumped while the project-scope copy stays stale.

## Parity Audit: Host→Plugin Direct-Import Grep

**Plugin migration parity audits must grep host→plugin direct imports as a separate check.** When extracting a subsystem from a host repo into its own plugin, the migration is incomplete until you've grepped the host's source tree for any direct imports, direct path references, or direct symbol usage of the now-plugin code.

Wiki-level redirection and routing-layer wrapping are NOT sufficient — the host can still reach past the wrapper through a direct import that the registration seam doesn't intercept. Audit shape:

1. Enumerate the plugin's exported symbol set.
2. Grep each symbol across the host tree (exclude the wrapper file itself).
3. Each hit is a residual coupling to fix before declaring migration parity.

This check is symmetric for cross-repo plugins: the host-side consumer tree must be grepped for direct references to the plugin's internal symbols, not just the public seam.

**Do this BEFORE declaring migration parity.** Deferring to "we'll catch it in CI" is how host→plugin direct imports survive months undetected — the wrapper intercepts runtime routing but direct imports bypass both the wrapper and any registration seam entirely.
