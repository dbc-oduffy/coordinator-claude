# Plugin Extraction and Distribution

When extracting a plugin from its source repo into a standalone distributable, "it works on my machine" is not the bar. External consumers run from a clean profile, on different OSes, with different drive layouts, against fresh `~/.claude.json` state. The extraction is incomplete until each of the surfaces below is verified.

## The 10-Item Checklist

### 1. Source-repo cleanup

Sweep the source repo for orphan plugin trees, install scripts, local configs, and stale tool-name references that survive the extraction. The plugin's old in-repo location often leaves debris that misleads future readers and breaks reproducibility. Brand-bound names (`EXAMPLE_GAME_REPO_*`, `EXAMPLE_SIM_REPO_*`) and the old plugin tree itself must both go — extraction is incomplete until orphans + brand-bound names are gone.

The four surfaces that must mop up together at extraction time: (a) the in-source-repo plugin tree, (b) install scripts that register the old layout, (c) `marketplace.json` entries pointing at the old location, and (d) per-user `~/.claude.json` `mcpServers` and `enabledPlugins` registrations. Skip any one and the next external consumer hits dead entries the author's machine does not notice.

### 2. Plugin generalization — `${CLAUDE_PLUGIN_ROOT}`, not hardcoded paths

The plugin's own commands, hooks, and skills must resolve their install dir via `${CLAUDE_PLUGIN_ROOT}`, never via hardcoded sibling-repo paths. Hardcoded paths embed the author's machine layout into the shipped artifact and break on every external consumer.

### 3. Env/config rename to neutral names (with deprecation fallback)

Brand-bound env vars, paths, and config keys (`EXAMPLE_GAME_REPO_*`, `EXAMPLE_SIM_REPO_*`, etc.) get renamed to neutral names. Keep a deprecation fallback that reads the old name and emits a one-line warning so existing consumers don't break overnight.

### 4. Runtime detachment — sever venv dependency on source repo

If the plugin's MCP server runs from a source tree (`pip install -e <source-path>`), document this explicitly. The runtime version is the checked-out branch HEAD, **not** what `pip show <pkg>` reports — which is often a separately-installed wheel. Conflating the two leads to "install v0.2.3" being a near-no-op when the consumer's MCP entry already points at source-path. Surface the source-path-vs-wheel distinction in install docs.

A source-path MCP registration (`command: python`, `args: [-m, server]`, `cwd: <source-tree>`) makes every subsequent `install vN` invocation a near-no-op for that consumer — the runtime version is whatever the source checkout currently points at. Installer should detect a pre-existing source-path registration and either (a) refuse to re-register over it without `--force`, or (b) print a loud notice that "install v0.5.3" will not change runtime behavior until the consumer's checkout is updated.

### 5. Doc sync

Update READMEs, install instructions, and any cross-repo references that pointed at the old location. Stale doc references → repoint to existing surfaces when content is already covered; create new pages only when genuinely missing (don't default to "create the missing doc" for every broken link).

### 6. Marketplace.json + per-user `~/.claude.json` mcpServers cleanup

Easy to forget: the per-user `~/.claude.json` `mcpServers` registration AND the marketplace.json entry both auto-register the now-deleted server file. Both need to be cleaned up at extraction time, otherwise `claude mcp list` carries dead entries until the next user notices and asks.

### 7. Enablement scope must match the capability's scope

Plugin enablement (`enabledPlugins["<name>@<marketplace>"]`) defaults to `<project>/.claude/settings.local.json`. It belongs in `~/.claude/settings.json` only when the capability is genuinely machine-wide — coordinator itself, or a plugin fronting a globally-installed server (an npm-global LSP). The marketplace and install record stay user-global either way, but a project-scoped install record uses `scope:"project"` with `projectPath` so a second project on the same machine appends a separate record rather than overwriting the first. Enablement granularity must match MCP-server registration granularity; the two surfaces drift apart silently when one is per-project and the other is user-global.

Writing a **project-scoped** plugin's enablement to `~/.claude/settings.json` surfaces its slash commands in every project on the machine — not just the one that opted in. Mirrors the same wrong-shape failure as writing MCP server args to top-level `mcpServers` instead of `projects[<root>].mcpServers`. The cost compounds: every situational MCP plugin enabled user-global contributes its deferred-tool surface and instruction blocks to *every* session open regardless of whether the project actually uses it. A machine-wide capability pays no such tax — its surface is wanted in every session by construction, which is why the scope test is the capability's reach, not a blanket per-project rule.

`~/.claude/settings.json` has **multiple independent writers across the fleet** — coordinator's installer (`dist/publish-repo-setup/install.sh`) and project-rag's fleet-LSP provisioner (`lib/provision_fleet_lsp.py`, Section J4) both read/modify/write it, with no interlock. Their key namespaces are disjoint (`@coordinator-claude` vs `@claude-plugins-official`), so nothing clobbers today; a genuinely concurrent run would drop one side's merge. Installs are operator-driven and serial — keep them that way rather than adding locking.

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

  Canonical propagation primitive: `refresh-plugin-live-install.py <plugin>` — executes both legs atomically, with pre-flight (clean working tree check) and post-flight (drift probe). Both legs must close together; advancing git HEAD without re-running `uv pip install -e .` leaves the venv leg stale and can cause silent `ImportError`.

- **Live install IS the canonical source:** there is no source → live propagation step because source and live point at the same directory. These plugins carry `propagation_mode = "source_is_live"` in `~/.claude/machine-local/registry.local.toml::plugin.mirrors`, where both `source_path` and `live_path` resolve to that directory. The drift probe treats them as structural no-ops; the refresh script skips them. **Coordinator-specific note (post-2026-07-04 cutover):** the coordinator plugin's `source_is_live` directory is now the DoE clone (`<DoE>/coordinator/`), resolved live via `--plugin-dir` — NOT `~/.claude/plugins/coordinator-claude/`. The OSS distribution (`coordinator-claude`) is a separate snapshot repo that receives publishes; it is not the live source. Pre-cutover, `~/.claude/plugins/coordinator-claude/` was the `source_is_live` path.

  **`source_is_live` rename mechanic.** When renaming a file or directory inside a `source_is_live` plugin (i.e. a plugin where `source_path` and `live_path` both point at the same directory — the canonical source), the git index at both the canonical side and the consumer side must be updated together. The correct sequence:

  ```bash
  # 1. At the canonical (<DoE>/coordinator or equivalent) side:
  git mv old/path new/path

  # 2. At the consumer (~/.claude) side, mirror the index across the symlink:
  git add old/path new/path
  ```

  A plain `git mv` at the canonical side updates only that repo's index. The `~/.claude/` tree (the `source_is_live` consumer) sees the rename as a worktree change but not as a staged rename — a subsequent `git status` will show `deleted: old/path` + `untracked: new/path` unless `git add old/path new/path` is run in the consumer tree to mirror the index. Omitting the consumer `git add` step produces a commit where the delete and add are unrelated to each other (no rename detection), misleading `git log --follow` and diff tools that rely on rename tracking. *Source: central-improvement-queue #99.*

**Drift detection:** `python check-plugin-drift.py` probes both legs (git-state and venv-state) for each registered plugin and surfaces results in `/workday-start` Step 1.10 Addon Health daily.

**`publish.py` direction:** `publish.py` runs source → publish-repo (sibling) for cross-machine distribution. It does NOT write back to the live install; the ban on publish-repo → live install clobber is preserved. These are orthogonal operations.

Spec: `docs/plans/2026-05-21-plugin-source-live-mirror-doctrine.md`.

#### `propagation_mode = "editable_sibling_venv"` — addon editable-installed into a sibling host's venv

<!-- spec-backlink: archive/specs/2026-05/2026-05-30-editable-sibling-venv-propagation-mode.md § Chunk 5 -->
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

**`track_ref` contract divergence — omitting is a footgun.** The default-mode behaviour (`track_ref` absent → parsers default to `"origin/main"`) does NOT apply safely here. `refresh-plugin-live-install.py`'s `_read_registry` calls `entry.get("track_ref", "origin/main")`, so an absent `track_ref` resolves to the literal string `"origin/main"`. In `editable_sibling_venv` mode this would trigger the git-state leg and run `git fetch && checkout origin/main` against the addon's working tree — clobbering in-flight branch work on a dev machine. (`bin/lib/read_mirrors.py` — the naked-Python port of the former `bin/lib/read-mirrors.sh` — preserves the same default for any future direct caller, but as of 2026-07-21 has zero live callers; both parsers this paragraph originally cited have migrated to claude-klabauter's `coordinator_core.plugin_health.drift` / `coordinator_core.ops.list_reverse_drift_cmds`, neither of which sources this file.)

- **Dev posture:** `track_ref = "live"` — explicit sentinel meaning "addon source is a live working tree; skip the git leg; run venv-state only."
- **Consumer posture:** `track_ref = "origin/main"` — full two-leg (git-state advances the addon checkout, venv-state repairs the editable install).

**Do NOT omit `track_ref` in either entry.** The parser default-to-`"origin/main"` makes a missing field dangerous in this mode. Cross-reference: `machine-local-registry.md` § `track_ref` lifecycle.

**Registry entry shape — exact TOML blocks.**

Dev posture (venv-only refresh; git-state is the live working tree):

```toml
[plugin.mirrors.project-rag-ue-addon]
# editable_sibling_venv: addon source (own git repo) editable-installed into the
# project-rag HOST venv. On THIS dev machine the addon source X:/project-rag-ue-addon  <!-- foreign-path-ok: illustrative worked-example registry-config comment, not a live path assertion -->
# is a live working tree — do NOT run the git leg against it.
# track_ref = "live" is the EXPLICIT sentinel — do NOT omit it.
# Both parsers default an absent track_ref to "origin/main", which would trigger
# git fetch && checkout origin/main and clobber the dev working tree.
propagation_mode = "editable_sibling_venv"
source_path = "X:/project-rag-ue-addon"  # foreign-path-ok: illustrative worked-example registry-config value, not a live path assertion
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

> Before any `machine-local set` command can succeed, the `machine-local/` directory must exist. Neither `setup/install.sh` nor claude-klabauter `coordinator/bin/publish.py` creates it. This is a known coordinator-side gap — see `install-surface-completeness.md` § Bootstrap gap. **A fresh-machine bootstrap MUST include the directory-creation step.**

Full sequence for a dev machine (venv-only posture):

```bash
# Step 1 — create the registry directory if it does not exist (NOT created by any installer)
mkdir -p ~/.claude/machine-local/

# Step 2 — register the addon entry (dev posture — track_ref=live skips the git leg)
machine-local set plugin.mirrors.project-rag-ue-addon.propagation_mode editable_sibling_venv
machine-local set plugin.mirrors.project-rag-ue-addon.source_path "X:/project-rag-ue-addon"  # foreign-path-ok: illustrative worked-example registry-config value, not a live path assertion
machine-local set plugin.mirrors.project-rag-ue-addon.live_path "/c/Users/<you>/.claude/plugins/project-rag"
machine-local set plugin.mirrors.project-rag-ue-addon.dist_name project_rag_ue_addon
machine-local set plugin.mirrors.project-rag-ue-addon.track_ref live

# Alternatively — append the TOML block directly to registry.local.toml
# (uses the block form, which is safe to append at end-of-file per the TOML scoping rules
# in machine-local-registry.md § TOML flat-key table-scoping gotcha)
cat >> ~/.claude/machine-local/registry.local.toml << 'EOF'

[plugin.mirrors.project-rag-ue-addon]
propagation_mode = "editable_sibling_venv"
source_path = "X:/project-rag-ue-addon"  # foreign-path-ok: illustrative worked-example registry-config value, not a live path assertion
live_path = "/c/Users/<you>/.claude/plugins/project-rag"
dist_name = "project_rag_ue_addon"
track_ref = "live"
EOF

# Step 3 — verify by reader lookup (do NOT rely on text-search alone)
machine-local get plugin.mirrors.project-rag-ue-addon.propagation_mode
# Expected: editable_sibling_venv
```

For a consumer machine (full two-leg), substitute `track_ref = "origin/main"` and set `source_path` / `live_path` to the consumer's actual checkout paths.

**`NOT_REGISTERED` failure — cross-link.** If `refresh-plugin-live-install.py project-rag-ue-addon` or `check-plugin-drift.py project-rag-ue-addon` exits with `NOT_REGISTERED` (exit 5), it means no `[plugin.mirrors.project-rag-ue-addon]` entry exists in the registry. Follow the bootstrap steps above. This section closes the tracked coordinator-side gap noted in `install-surface-completeness.md` § Three recurring failure shapes, shape 2 — the "Known coordinator-side gap" tracking exactly this `NOT_REGISTERED` pattern for addons editable-installed into a sibling's venv.

**example-game-repo-owned plugins — one-way install-only, explicitly NOT in OSS coordinator-claude.** Plugins whose value is entirely contingent on the example-game-repo/UE-addon infrastructure (e.g. `game-dev`) flow example-game-repo-repo → example-game-repo install, one direction only. Nothing flows them outward to the `coordinator-claude` OSS publish target or any other distribution target. No bidirectional back-prop or merge script is maintained; that asymmetry is structural — it would reintroduce the multi-master state the 2026-05-20 publish→live clobber ban closed.

The adjudicating rule for packaging calls: **coordinator ships a coherent operating system for our colleagues, not generic personae as a contribution to the OSS community.** Domain content whose value requires infrastructure the OSS user does not have belongs to the specialized distribution, not the naked OSS coordinator-claude publish.

**`plugins/example-game-workbench-repo/` remains git-tracked in `~/.claude/`.** git-tracking on `~/.claude/` is the mechanism by which the entire setup is portable across devices. Gitignoring example-game-repo plugin files would defeat the meta-repo's portability purpose. Refresh discipline for the example-game-repo plugin is tracked explicitly via the workday-start drift probe (`check-plugin-drift.py` Step 1.10 Addon Health). The git-tracking decision is structural, not a per-session choice — do not add the example-game-repo plugin directory to `.gitignore`. The UE-specialization-migrates-OUT polarity principle that governs *why* example-game-repo owns this content is documented in `docs/wiki/peer-repo-polarity.md`. The `game-dev` retirement is the canonical precedent; see `archive/specs/2026-05-26-retire-game-dev-from-oss.md`.

### 10. Plugin hooks belong in `hooks/hooks.json`, not user-scope `settings.json`

A SessionStart/PreToolUse/etc. hook registered in `~/.claude/settings.json` works on the author's machine but doesn't follow the plugin to marketplace consumers — install lays down the script but never registers the event. Always ship `hooks/hooks.json` alongside the script in the plugin tree so install auto-wires it. User-scope settings is for non-plugin overrides only. Treat this as a portability check at extraction time: grep `~/.claude/settings.json` for any hook entry whose script lives under the plugin tree, and migrate it to the plugin's `hooks/hooks.json` before shipping.

**`--plugin-dir` delivery exception.** ONLY when the plugin is delivered via `--plugin-dir` (which disables plugin-declared hook auto-wire, observed behavior; issue ref #38699 — approximate, spot-check before OSS publish), generate `settings.json` hooks from `hooks.json` as a machine-local delivery artifact; marketplace/OSS consumers keep `hooks.json` as SSOT with the normal auto-wire. (DoE-internal research record: `coordinator/docs/wiki/external-plugin-live-resolution.md` § 10. Adoption — External/OSS Consumers: the `settings.json` hook-registration approach documented inline above is the workaround.)

### 11. Port-time absolute-path sweep + sibling-layout convention

> **Runtime `repos.*` discovery.** Sibling-relative replacement is the contract for port-time cleanup (this section's scope: extraction-time absolute-path sweep, where the consumer doesn't yet exist to be told about anything else). At **runtime**, `repos.<slug>` discovery is governed by the 4-rung ladder in `machine-local-registry.md` §4c (SSOT: `project-rag/docs/wiki/cross-machine-path-resolution-contract.md`); the blind `../<sibling-repo>/` walk is **not a runtime rung** — marker-autodiscovery (§4c rung 2) covers that case instead. See `machine-local-registry.md`.

Incomplete migrations leak absolute paths (`C:/Users/.../source-repo/...`, `~/work/src/...`) into the vendored code, hooks, and config. <!-- foreign-path-ok: the hardcoded path IS the anti-pattern being critiqued --> Symbol parity passes; runtime breaks on every consumer machine. **At extraction time, sweep absolute repo prefixes across the carved-out tree** and replace with sibling-layout relative references (`../<sibling-repo>/<path>`) where cross-repo references are unavoidable. Document the sibling-layout convention in the plugin's CLAUDE.md so `../sibling/...` is a contract — not an implementation detail downstream consumers have to reverse-engineer.

Grep recipe for the sweep:

```bash
grep -rn "C:[\\/]" <new-plugin-tree>
grep -rn "$HOME/.*[/]src[/]" <new-plugin-tree>
grep -rn "/Users/.*/" <new-plugin-tree>  # abs-path-ok: grep pattern demonstrating what to search for, not a location claim
```

(project-rag-ue-addon.)

#### Runtime preference order vs. port-time cleanup

Port-time cleanup (the topic of this section) and runtime discovery are **different sub-problems** with different answers. Port-time cleanup replaces absolute paths with sibling-relatives at extraction time because the consumer doesn't exist yet to be told about any other mechanism. Runtime discovery, however, happens on an operator's live machine — and sibling-layout-alone is insufficient for the general case.

**The four failure modes of sibling-layout at runtime:**

1. **It dictates operator filesystem layout.** Every sibling repo must live under one common parent folder. Operators with established conventions (separate drives for engine source vs. tooling, network shares, multi-machine sync setups) cannot comply without restructuring their environment to match the convention.
2. **It cannot represent deterministic locations.** Some things — vendored binaries, large indices, GPU sidecars — genuinely need a fixed absolute path on a specific drive. Sibling-relatives have no way to express "this lives at `E:/UE-content/` regardless of where the repo is cloned." <!-- foreign-path-ok: illustrative example of a deterministic-location need, not an asserted install location -->
3. **It silently breaks discovery for downstream consumers.** A repo that uses `../sibling-repo/x` works when cloned into the expected parent, fails opaquely when cloned anywhere else. The failure mode is "file not found" with no remediation hint that the convention was violated.
4. **It does not compose with triangular dependency graphs.** A sibling-relative inside `example-game-workbench-repo` pointing at `../project-rag-ue-addon/x` assumes both repos share a parent. The moment one triangle vertex moves to a different drive or directory, every sibling-relative pointing at it breaks — not just the path that was moved.

**Runtime `repos.<slug>` discovery — governed by the §4c ladder.**

The runtime discovery order defers to the 4-rung ladder in `machine-local-registry.md` §4c (SSOT: `project-rag/docs/wiki/cross-machine-path-resolution-contract.md`). The blind `../<sibling-repo>/<path>` walk is not a runtime rung — marker-autodiscovery (§4c rung 2) is the runtime rung. The "operator hasn't populated the registry" case is served by autodiscovery; the original "no forced cutover" intent is satisfied, not overridden.

Port-time cleanup still uses sibling-relatives as its replacement vocabulary — the extraction-time MUST rule stays, because at that moment the consumer doesn't yet exist. Runtime consumers follow the §4c ladder.

Cross-references: `machine-local-registry.md` (registry doctrine and schema); `cross-repo-citation-conventions.md § Sibling-layout convention` (port-time MUST rule + runtime preference-order supersession).

### Portable publish topology + provisioning a new machine

The shared publish-target topology (which targets exist, what each publishes) is committed to `setup/publish-targets.portable` using the portable row format:

```
name|mode|publish-mirror:<key>|source_subdir|dest_subdir[|native_slugs]
```

Field 3 starts with `"publish-mirror:"` so no absolute paths appear in the tracked file. The resolver derives the DEST root from `machine-local get publish.mirrors.<key>.path` (e.g. `publish.mirrors.coordinator_claude.path`, `publish.mirrors.deep_research_claude.path`). The SOURCE root is the meta-repo (script-derived); `source_subdir` is meta-repo-relative. An empty `dest_subdir` means the publish-repo root.

**Provisioning a new machine** requires only two registry writes — the tracked `.portable` file does the rest:

```bash
machine-local set publish.mirrors.coordinator_claude.path /path/to/coordinator-claude
machine-local set publish.mirrors.deep_research_claude.path /path/to/deep-research-claude
```

After that, `publish.py` reads the topology from `setup/publish-targets.portable` and resolves all DEST roots automatically. Zero hand-authored rows needed in `setup/publish-targets.portable` or the registry.

### 11a. Publish-time content transforms ride the publish-time-transform surface — extend, don't sibling

When a new class of publish-time content transformation is needed (a new persona-name mapping, a new path-rewrite rule, a new identity-token substitution), **extend the existing `publish-time-transform-py` substitution table — do not author a sibling transform tool.** (The bash `publish-time-transform.sh` this surface was ported from is retired; `publish-time-transform-py` in claude-klabauter `coordinator/bin/` is the current CLI.) The publish-time-transform hook is already the registered `post-rsync` transform surface for every publish target; a second sibling tool means two surfaces that must both fire in the right order, two places to register, and a silent gap when one is updated and the other isn't. The substitution table is table-driven precisely so new transforms are table edits, not new tools. (Scan-vs-substitute is the one legitimate two-tool split — see § Scan/Substitution Division of Labor — because detection and correction are genuinely different jobs; a *second corrector* is not.) The script was renamed from a path-decay-mismatched name (see `docs/plans/2026-05-28-publish-surface-hygiene.md`); its job had already grown beyond depersonalization, and the rename reflects that.

### 12. Cross-repo port: prefer registration-seam over parallel-surface

When porting a feature from a host repo into a plugin/addon, default to **using the host's registration hookspec or seam** rather than authoring a parallel front-end on the plugin side. A parallel-surface port creates two registration paths the host has to reconcile at runtime and routinely results in one path silently winning while the other looks active. Before authoring a plugin-side surface that mirrors an existing host surface, grep the host's registration corpus (hookspec discovery, pluggy entry points, plugin-manifest readers) and route through the existing seam. (project-rag-ue-addon.)

### 13. Bootstrap script — a plugin's own `setup` cannot bootstrap itself into Claude Code

A plugin's own `/<plugin>:setup` skill **cannot register the plugin into Claude Code** — the setup skill only runs *after* the plugin is already enabled, so it cannot be the thing that enables it. This is a chicken-and-egg gap: a fresh-clone user has the plugin's files on disk but no `known_marketplaces.json` / `enabledPlugins` entry, so `/<plugin>:setup` is unreachable.

**Every plugin needs a standalone `bin/register-claude-plugin.{py,sh,ps1}` script** (per-platform variants) that:

- Registers the marketplace and enables the plugin **from the user's actual clone path** (not a hardcoded author path).
- Seeds **both** `extraKnownMarketplaces` in `~/.claude/settings.json` AND the `~/.claude/plugins/known_marketplaces.json` cache, so `/reload-plugins` activates the plugin without requiring a cold Claude Code restart.
- Is invoked from the README **before** the `/<plugin>:setup` line — the README order is `clone → run register-claude-plugin → /reload-plugins → /<plugin>:setup`.
- Is **also called early from `scripts/setup.{sh,ps1}`** as a self-heal step, so a user who runs the setup script directly (skipping the README's register step) still gets registered rather than hitting the unreachable-skill gap.

This is distinct from checklist item 8 (installer registers enablement, not just MCP wiring): item 8 is about the shell *installer* touching the three enablement files; this is about the *bootstrap-from-clone* path where no installer has run yet and the plugin must register itself from wherever the user cloned it. (project-rag-ue-addon.)

## Removing One Plugin From a Shared Marketplace Clone — Excise Per-Plugin, Never `rm` the Tree

A Claude Code marketplace directory (e.g. `plugins/coordinator-claude/`) hosts *multiple* plugins as subdirs and is git-tracked in the meta-repo. Sibling plugins have no resolution path other than this shared clone, so "remove the plugin tree" never means `rm -rf` the marketplace — that breaks every sibling at once. The correct excision is three scoped edits:

- `git rm` the ONE plugin subdir,
- drop that plugin's entry from `marketplace.json`,
- drop its `enabledPlugins["<name>@<marketplace>"]` key.

The whole-tree `rm` is the trap precisely because it *looks* like "remove the plugin" — the shared-clone structure makes the blast radius invisible until a sibling silently fails to load. (Removal-side analog of item 9's disable-≠-uninstall two-surface discipline.)

## Plugin Relocation Cutover — Sweep Every Path-Registration Surface, Not Just `settings.json`

When a plugin's live source *moves* (e.g. into a `--plugin-dir` clone), far more than `settings.json` points at the old bin path. Git hooks (`post-commit`, `prepare-commit-msg`) AND their installer templates AND the publish source AND every registry seam still resolve the old location and break on removal. Item 1's four extraction surfaces are the floor; a *relocation* additionally touches:

- committed git hooks in every repo that installed them,
- the hook *installer templates* that regenerate those hooks,
- the publish/percolate source paths,
- registry seams (`plugin.mirrors`, `repos.*`) that record the old root.

Enumerate and repoint all of them, then **verify a real commit fires clean in every affected repo** before declaring the move complete — a hook resolving a stale bin path fails only when git actually invokes it, not when you grep the config.

## Dry-Run Is Not Hook-Invoking — a Clean Dry-Run Is Not Clean-Publish Evidence

Percolate machinery built for one plugin layout breaks silently under another, and the dry-run will not tell you. The 2026-07 flat-repo (v3) cutover surfaced this: the then-live `publish.sh` still assumed the old nested `plugins/coordinator/` layout and resolved `COORDINATOR_BIN` to a stale `plugins/` path — so `install-sentinel-write` was never found (`version.txt` never written) and `check-version-consistency.py` was silently skipped. The **dry-run looked clean because the publish driver does not invoke post-rsync hooks on `--dry-run`** — only the real percolate runs them (still true of `publish.py`, its Python successor).

Rule: after any layout/path cutover to the publish pipeline, a clean dry-run is advisory only. Confirm with a **real percolate plus an empirical `grep`/`comm` of the published tree against the prior release** — the dry-run cannot witness hook-dependent output (sentinels, version stamps, verification gates) it never fired.

## Cross-plugin contract — coordinator never parses peer-plugin config

When coordinator skills need data from a plugin (project root, transport URL, capability registry), the contract surface is **`invoke + read exit code + read stdout`** — pass through the plugin's CLI or daemon. Reaching into `~/.claude.json` from coordinator-side code to reconstruct args a plugin CLI could resolve itself is cross-plugin contract leakage and breaks the next time the plugin migrates transport (e.g. stdio → HTTP, as project-rag did).

The 2026-05-21 dogfood failure surfaced one instance: `/workday-start` Step 3.6 parsed `mcpServers.project-rag.args[-1]` to extract `--project-root` and crashed with `KeyError` after project-rag's HTTP-shape entry has no `args` array. The fix was not "guard `args[-1]` with a `type == 'stdio'` check" — the fix was to stop parsing project-rag's config entirely and let `project-rag-cli staleness-survey` resolve its own root via env (`PROJECT_RAG_PROJECT_ROOT`) or cwd-walk. See `docs/plans/2026-05-21-coordinator-side-dogfood-followup.md` for the worked example.

The rule generalizes:
- **Pass env vars or cwd to influence resolution.** `PROJECT_RAG_PROJECT_ROOT="$(pwd)" project-rag-cli ...` is the right shape.
- **Do not parse the plugin's MCP entry shape from coordinator.** If you need state the plugin's CLI/daemon doesn't expose, ask the plugin author to add an endpoint (e.g. project-rag's planned `/state` endpoint) — don't reverse-engineer it from the registration.
- **Plugin CLIs own their own resolution chain.** If a CLI doesn't yet resolve its own root, that's an upstream improvement; document it as a plugin-author ask, not a coordinator hack.

This applies symmetrically: plugins should not parse coordinator's internal files (orientation cache, queue files) — same contract, opposite direction.

## Test From a Clean Profile

The single highest-leverage validation: run the install script from a profile that has never used Claude Code before. Anything that "just worked" on the author's machine from prior manual setup will fail loudly. This catches gaps 1, 6, 8, 9, and 10 in one pass.

## Atlas Drift After Extraction

When a plugin moves to a standalone repo, the consumer-side architecture atlas, file-index paths, and MCP-tool prefixes go stale silently — greppable-by-old-name is not the same as broken-by-old-name. Old paths still resolve in cache, old tool prefixes still appear in agent-prompt examples, and nothing surfaces the drift until a new contributor reads the atlas and gets pointed at a path that does not exist.

Plugin-extraction PRs need an explicit atlas-sweep step before merge: grep the consumer repo for the old plugin path, the old MCP tool prefix, and the old marketplace name; update or repoint each hit; verify the architecture atlas's plugin section reflects the new layout. Treat this as part of the extraction PR itself, not a follow-up — the cost of doing it later is ambiguous "is this stale or current?" reads from every downstream consumer until someone audits.

## CRLF/LF Verification on Percolation

Percolation from a Unix-authored source repo to a Windows consumer (or vice versa) silently swaps line endings under the wrong git config, producing whole-file diffs that read as no-op edits but change every line of every file. "Agent reported clean" is not enough — a clean diff under `core.autocrlf=true` may hide the entire reformatted file. Establish `.gitattributes` rules early.

**Per-file diff, not aggregate "no changes," is what catches CRLF/LF drift.** CRLF/LF differences on Windows can produce a clean-looking percolation summary that doesn't match upstream at the file level — the line-ending swap touches every byte but registers as zero semantic changes under some diff modes. An aggregate "no changes" report from the percolation agent is advisory only.

## Persona-Name Guard on Percolation

The meta-repo (`~/.claude/`) authors files with persona display names — the Staff Engineer, the Game Dev Reviewer, the Data Science Reviewer, the Front-End Reviewer, the UX Reviewer, the Director of Engineering, the VP-Product Reviewer — because that's how the human PM thinks of the reviewers. The publish repo (`coordinator-claude`, or any open-source consumer mirror) ships nameless: reviewers are referred to by articulated role labels (the Staff Engineer, the Game Dev Reviewer, etc.), with naming offered as an opt-in install step. Personae ≠ names — the doctrine is in `docs/evolution/03-personas-as-ergonomics.md` (publish-repo copy). Without a guard, percolation reintroduces names silently, since the meta-repo source still has them.

Two paired tools enforce the boundary:

- **Publish-repo CI gate.** `.github/scripts/check-persona-names.py` runs as a tracked-files scan auto-discovered by `run-all-checks.py`. Hard-fails any commit/PR where canonical-layer files (`*.md`, `*.sh`, `*.py`; excludes `archive/`, `tasks/`, `experiments/`, `evals/`, `docs/{plans,research,decisions,specs}/`) contain bare persona display names. Suppression: `# noqa: persona-names` inline, or `.github/.persona-names-allowlist` file-based (`filepath:line_number` per line).

- **Meta-repo registered hook.** `setup/percolate-hooks/<target>/post-rsync/10-transform.sh` is a thin wrapper around `publish-time-transform-py` (the naked-Python successor to the retired `publish-time-transform.sh`) in claude-klabauter `coordinator/bin/`. The depersonalize CLI itself supports `--check` (exit 1 on hits) or `--fix` (in-place rewrite to role labels, with `.bak` backups). The hook receives the destination path as `$1` and the synced-files list via stdin (newline-delimited), then `--fix`es each `*.md`/`*.sh`/`*.py` file. Registered for `coordinator-claude` and `deep-research-claude` (open-source publish targets); deliberately NOT registered for `example-game-repo` (keeps persona names natively). Only the hook lives meta-repo-local; the CLI it calls is shipped with the coordinator plugin and percolates with it. The `--fix` mode handles the common "the X" / "The X" article cases including the "the X" double-article it would otherwise produce.

**`publish.py` is the authority for percolation — manual `cp` is wrong.** Percolating to `coordinator-claude` (or any registered publish target) means running `python coordinator/bin/publish.py <target>` (claude-klabauter `coordinator/bin/publish.py`), not copying files by hand. Manual `cp` bypasses the depersonalize pipeline, the content-leakage scan, and the `.percolate-ignore` filter — the resulting publish repo may contain persona names, local paths, or excluded files the author didn't intend to ship. The publish-targets list at `setup/publish-targets.portable` is the authority; if a target is missing from it, register it there rather than working around it with ad-hoc copies.

> **Double-prefix trap — source layout ≠ target layout; never re-append the plugin subpath.** The recurring failure behind hand-built paths is conflating the *source-side* layout with the *target-side* layout. Source side, the coordinator plugin lives at `~/.claude/plugins/coordinator/...`; publish side, it lives at `X:/coordinator-claude/plugins/coordinator/...` — **`plugins/coordinator/`, not `plugins/coordinator/`.** A hand-built `cp` that takes the publish-repo root `X:/coordinator-claude` and appends the *source* relative path produces the doubled `X:/coordinator-claude/plugins/coordinator/...` (stale entries of exactly this shape were found frozen in `.claude/settings.local.json` and removed). <!-- foreign-path-ok: worked example of the double-prefix bug shape, not an asserted install location --> The same trap bites runtime tooling: the `coordinator-claude` registry mirror's `live_path` (`~/.claude/plugins/coordinator-claude/coordinator`) is **already the full coordinator root** under `propagation_mode = "source_is_live"` — any consumer that treats it as `~/.claude` and re-appends `plugins/coordinator-claude/coordinator` doubles it (symptom: `Get-ChildItem ...coordinator\plugins\coordinator-claude\coordinator` cannot-find-path). Rule: `live_path` is the root, not a base to join onto; and the only correct way to reach a target path is to let `publish.py` map source→target — never hand-construct it.

Workflow during percolation:

1. Run `python "$CLAUDE_KLABAUTER_ROOT/coordinator/bin/publish.py" <target>` (a.k.a. percolate / push-to-publish-repo — `publish.py` migrated to claude-klabauter in commit `b644d5a9`, resolved via `CLAUDE_KLABAUTER_ROOT`) — or `/percolate <target>` for the dry-run-confirm-real-run skill wrapper.
2. `publish.py` discovers and runs every executable script in `setup/percolate-hooks/<target>/{pre-rsync,post-rsync,pre-ci}/*.sh` in lexical order at the corresponding boundary. The depersonalize hook fires automatically at `post-rsync` for any target with one registered. Failure-semantics: non-zero hook exit aborts the publish; post-rsync abort = destination partially mutated, recovery is to fix the hook and re-run (`--check`/`--fix` is idempotent).
3. CI on the publish repo re-runs `python .github/scripts/check-persona-names.py` on push as the safety net — even if a hook is mis-registered, the gate catches regressions.

To add or modify a hook for a target: place an executable `*.sh` script under `setup/percolate-hooks/<target>/<hook-point>/`. Numeric prefixes (`10-`, `20-`) order execution. Authoring help: see `docs/wiki/percolate-setup.md` (walked by `/percolate` Branch 0 and `/setup` percolation phase) — it scaffolds the hook directories with `.gitkeep`. Registration is convention-based discovery — no manifest required.

Source-side publish-content policy (`.percolate-ignore`) lives at `$SOURCE_DIR/.percolate-ignore` (gitignore-shaped, simplified subset — `**/` not supported). `publish_sync.py`'s `sync_mirror` honors it in both copy and delete phases. Details below.

**`.percolate-ignore` policy details:**

- **Location:** source plugin root (e.g. `~/.claude/plugins/coordinator-claude/.percolate-ignore`), one per `SOURCE_DIR` in `publish-targets.portable`, parallel to `.gitignore`. Source-keyed, not target-keyed — authoring agents must see the policy from their cwd; a target-keyed file makes the policy invisible to authoring-time scrutiny.
- **Format:** gitignore-shaped lines. Simplified-subset semantics — `**/` is NOT supported. Supported: plain `dir/` (prefix-anchored), `*.ext` (basename match), explicit paths. Blank lines and `#`-comments ignored.
- **Default scaffold body:** `_archived/`, `scratch/`, `*.bak`, `*.tmp`.
- **Integration:** `sync_mirror` reads once per source plugin at top of sync; `is_ignored()` helper applies in both copy and delete phases. The inline `_archived/` skip (ported from the retired bash `publish.sh`'s equivalent lines) is retained in `publish_sync.py` as defense-in-depth alongside `.percolate-ignore`.
- **Coverage drift detection:** `/percolate` Step 2 surfaces files newer than `.percolate-ignore` mtime — a signal the policy may not have been reviewed since those files were added.
- **Surface B coupling:** Surface B (mirror+depersonalize oscillation) may redesign `sync_mirror`; the inline `_archived/` skip must be re-evaluated alongside that work. `cp -p` / `rsync -t` preserve mtime through any staging dance; naive `cp` resets mtime and makes every source file appear "newer than policy" on next dry-run.

See `docs/wiki/percolate-setup.md` (walked by `/percolate` Branch 0 and `/setup` percolation phase) for the full audit-and-scaffold procedure, including classification taxonomy and grey-zone handling.

The vocabulary table (also in `docs/customization.md` "Reviewer Roles" of the publish repo): the Staff Engineer → the Staff Engineer; the Director of Engineering → the Director of Engineering; the VP-Product Reviewer → the VP-Product Reviewer; the Game Dev Reviewer → the Game Dev Reviewer; the Front-End Reviewer → the Front-End Reviewer; the UX Reviewer → the UX Reviewer; the Data Science Reviewer → the Data Science Reviewer.

### Hook Registry Architecture

The hook registry is conventional-discovery, no manifest required. Key mechanics:

- **Hook-point directory:** `setup/percolate-hooks/<target-name>/{pre-rsync,post-rsync,pre-ci}/`. Pre-rsync receives `$1=source_dir $2=target_dir`; post-rsync receives `$1=target_dir` and synced-files list via stdin; pre-ci receives `$1=target_dir`.
- **Ordering:** lexical sort; numeric prefixes (`10-foo.sh`, `20-bar.sh`) order execution. Scripts invoked via `bash "$hook"` (not sourced — isolation). Executable bit NOT required.
- **Empty-glob safety:** MUST use `shopt -s nullglob` scoped in subshell OR `[[ -e "$hook" ]] || continue` guard. Raw `*.sh` glob with no files expands literally under bash.
- **Failure semantics:** non-zero hook exit aborts publish (`set -euo pipefail`). Post-rsync abort = destination partially mutated. Recovery: fix the hook and re-run `/percolate` — depersonalize is idempotent.
- **Out-of-percolation guard:** `setup/percolate-hooks/` lives at meta-repo root, OUTSIDE every `SOURCE_DIR`. Runtime guard MUST assert `$hooks_dir` is not a subpath of `$SOURCE_DIR`.
- **Hook discovery logging:** even in non-dry-run, emit one line per hook-point: `"  <hook-point> hooks: <comma-sep-names or '(none)'>"`.
- **Depersonalize hook is a thin wrapper** calling `publish-time-transform-py` (successor to the retired `publish-time-transform.sh`). Registered as `post-rsync/10-transform.sh` for `coordinator-claude` and `deep-research-claude`; deliberately absent for `example-game-repo`. Only the hook lives meta-repo-local; the CLI it calls ships with the coordinator plugin and percolates with it.

### /percolate Skill — Step Sequence and Gates

The `/percolate` skill wraps `publish.py` with a structured confirmation gate. The seven steps are:

1. **Pre-flight:** verify target name exists in `setup/publish-targets.portable`. If not, list registered targets and exit non-zero.
2. **Dry-run:** `python "$CLAUDE_KLABAUTER_ROOT/coordinator/bin/publish.py" --dry-run <target>`. Capture stdout + exit code. Compute coverage-drift panel: `find "$source_dir" -type f -newer "$source_dir/.percolate-ignore" 2>/dev/null | head -20` (surface if non-empty; shows files changed since policy was last reviewed).
3. **PM confirmation gate:** fires iff a deletion is present, OR dry-run touches ≥10 files, OR dry-run touches sensitive paths (`CLAUDE.md`, `settings.json`, `hooks/`, `agents/`). If dry-run reports zero changes: skip gate AND real run, but still run CI smoke (Step 5).
4. **Real run:** `python "$CLAUDE_KLABAUTER_ROOT/coordinator/bin/publish.py" <target>`. Surface any `WARNING: REVIEW` lines from Phase 4 verbatim.
5. **Optional CI smoke:** if target repo has `.github/scripts/run-all-checks.py`, run it from repo root. Skip silently if missing. Call `run-all-checks.py`, not `check-persona-names.py` directly.
6. **Unified summary** (4 lines): dry-run exit / real-run exit or "skipped (no-op)" / CI-check exit or "n/a" / overall verdict. `PASS` = all exits 0 AND no Phase 4 REVIEW lines; `PASS-WITH-WARNINGS` = all exits 0 AND REVIEW lines present; `FAIL` = any non-zero exit.
7. **Stop on first failure:** print failing step's stderr + one-line manual-recovery hint.

The skill does NOT call `publish-time-transform-py` directly, does NOT modify `publish.py`/`publish-targets.portable`, does NOT commit/push publish-repo results. All triggers (percolate, push to publish repo, publish to `<target>`, sync meta to publish) map to this skill.

**Dogfood discipline:** a clean-tree no-op pass does NOT satisfy convergence. The acceptance-test sequence must include: (1) clean no-op, (2) trivial-edit happy path, (3) sensitive-path edit forcing confirmation, (4) bad-target name (Step 1 exit), (5) missing source-dir (Step 7 failure), (6) CI smoke on clean target, (7) verify summary line counts in all cases.

**Cygwin/fork-exhaustion note:** `publish.py` is a single Python process and does not fork per-line, so a fork-heavy grep/sed driver's Cygwin-shell wedge failure mode (`"fork: retry: Resource temporarily unavailable"` on large dry-run output) does not apply to it.

> **`the Director of Engineering → the Director of Engineering` is the canonical role-label mapping.** The publish repo's `docs/customization.md` "Reviewer Roles" table, any `check-persona-names.py` allow-list, and any personalizer script that maps role labels back to user-chosen names must match it. Personalizers should let the new user pick any name for the DoE role; the title carries the rank, the name is cosmetic.

## Auxiliary Sync — Publish-Repo Top-Level `docs/wiki/`

**Auxiliary sync — publish-repo top-level `docs/wiki/`.** The publish repo also carries a public-facing wiki at `<publish-repo>/docs/wiki/` (separate from the plugin tree under `<publish-repo>/plugins/coordinator/docs/wiki/`). This auxiliary surface is synced from the plugin's `docs/wiki/` via a second publish-target row (`coordinator-claude-toplevel-wiki`) with `flat-mirror` mode plus a publish-native allowlist. The allowlist lives at `setup/percolate-hooks/coordinator-claude-toplevel-wiki/post-rsync/publish-native-allowlist.txt`; files named there are backed up before rsync and restored after, so publish-native authoring on the public side (including uncommitted edits) survives meta-repo syncs. A verification gate enforces canary survival, forbidden-shape grep, and rewrite-target sanity.

**Allowlist lives in `setup/percolate-hooks/<target>/post-rsync/` (hook-local) rather than in the publish repo** because (1) the consumer is the meta-repo hook — locality with the consumer beats locality with the protected data; (2) it documents the allowlist mechanism alongside the hook, making the existence of an allowlist visible to anyone reading `percolate-hooks/`; (3) future plugins with publish-native allowlists organize under one tree.

**When to add a file to the allowlist:** the file is authored on the publish-repo side (its git history lives in `/x/coordinator-claude/`), and it is not a copy of any plugin wiki. Today: `task-tier-guidance.md` is the sole entry.

**When NOT to use the allowlist:** if a plugin-side wiki and a publish-side wiki need to converge into one canonical source, move the publish-side authoring back to the plugin and remove from allowlist. The allowlist is for genuinely divergent lifecycles, not for resisting normalization.

Spec backlink: `archive/specs/2026-05/2026-05-18-publish-repo-toplevel-wiki-sync.md` § Shape decision A*.

### `dist/publish-repo-docs/` corner and bidirectional `.percolate-ignore`

A further authoring source (in addition to those listed in `### Publish-Repo Content Authoring`) handles publish-repo-owned top-level `docs/*.md` files that are not driven by the plugin tree. `coordinator/dist/publish-repo-docs/` controls publish-repo-owned top-level docs not driven by the plugin tree (today: `evidence.md`, `safety.md`, `README-meta.md`). A bidirectional `.percolate-ignore` inside this source dir protects every other top-level publish-repo `docs/*.md` from the flat-mirror delete-not-in-source pass — preventing the sync from removing docs whose lifecycle lives in the publish repo. A `maxdepth-1` depersonalize post-rsync hook is scoped to never touch `docs/wiki/` or other targets' subdirs.

### Publish-Repo Content Authoring (setup scripts and top-level docs)

**The publish repo is a percolation target, not a source of truth.** All publish-repo content is authored in Claude Central (`~/.claude/`) and percolated outward via `python coordinator/bin/publish.py` (claude-klabauter `coordinator/bin/publish.py`). Editing the publish repo directly is always wrong — it bypasses the planning, review, and doctrine pipeline that governs the rest of the coordinator system.

The four authoring flows:

- `plugins/*` ← `~/.claude/plugins/coordinator-claude/` (existing `coordinator-claude` mirror target)
- `docs/wiki/*` ← `…/coordinator/docs/wiki/` (existing `coordinator-claude-toplevel-wiki` flat-mirror target — the established precedent for this section)
- `setup/*.sh` ← `…/coordinator/dist/publish-repo-setup/` (new `coordinator-claude-publish-repo-setup` flat-mirror target)
- top-level docs (`coordinator-claude` mirror) ← `…/coordinator/dist/publish-repo-toplevel/` (`coordinator-claude-publish-repo-toplevel` flat-mirror target)

**Why this matters.** Direct publish-repo edits drift silently across sessions: they accumulate as orphan branches, rot when the next percolation run overwrites them, and compound without any doctrine trail. The 2026-05-21 audit (cross-repo memo at `archive/cross-repo/`) found three orphan setup scripts and eight orphan top-level docs that had been edited in the publish repo over multiple sessions; the back-percolation work documented in `docs/plans/2026-05-21-back-percolate-publish-repo-orphans.md` is the corrective.

**Flat-namespace note.** The `dist/publish-repo-*` naming is a flat namespace. Future siblings (e.g. `dist/publish-repo-workflows/` if `.github/workflows/` ever back-percolates) are parallel entries, not nested under any current member. Nesting under an `oss-distribution/` umbrella is intentionally declined: the coordinator system has multiple publish repos (`coordinator-claude` and `deep-research-claude`), and the explicit publish-repo prefix is clearer than a presumed-singular umbrella.

**Recovery — when a publish-repo edit happens anyway:**

1. Copy the edited file from the publish repo back into the appropriate `coordinator/dist/publish-repo-*/` source directory. Manual `cp` is correct here — back-percolation is the genuine exception to "publish.py is the authority," which governs the source → publish-repo direction only.
2. Commit in Claude Central with a `back-percolate:` subject prefix.
3. Re-run `python "$CLAUDE_KLABAUTER_ROOT/coordinator/bin/publish.py" <target>` to verify the source-of-truth now drives the publish-repo state.
4. Surface the incident in `state/lessons/` if the edit was substantive, so the doctrine compounds.

**Per-target `.percolate-ignore`.** Publish-repo-owned infra files (e.g. `.gitignore`, `.python-version`, `version.txt`, `subagent-sandbox-policy.yaml`) are protected via `dist/publish-repo-toplevel/.percolate-ignore`. These files remain owned by the publish repo by design; back-percolating them is a separate, per-file decision, not an automatic consequence of this doctrine.

The publish repo's own root `CLAUDE.md` is **not** on that list (`docs/plans/2026-07-27-doctrine-envelope-allocation.md` § C8, commit `389b0a225`, following the allowlist admission of `templates/CLAUDE.md.tmpl` in `463718687`): the mirror copy was a stale third fork of `templates/CLAUDE.md.tmpl`, and the ruling is remove-do-not-regenerate — the percolate engine has no render or placeholder-fill capability, so re-homing it in `dist/` would only trade one hand-maintained copy for another. The flat-mirror Phase-2 sweep deletes it. Do not restore it from mirror history during an incident; that reverses a decision rather than recovering from one.

**Mirror-native CI harnesses go in `dist/mirror-native/<target>/`, not in the publish repo.** A `.github/` that exists only in the publish repo cannot be reconstructed if that repo is ever rebuilt, and takes the end-of-run identity gate's own checker with it when it goes — found the hard way. Ship it via an `inject` entry (never a publish row: inject runs *after* the content-transform sweep, so a persona-name checker's deliberately-literal vocabulary is not rewritten into placeholders, which would leave it reporting green over a dirty tree), and put that entry on the row whose `dest_subdir` is empty, or it lands in a subdirectory invisible to GitHub.

## Scan/Substitution Division of Labor

Two tools enforce the publish boundary; they solve different failure modes and are not interchangeable:

- **`publish-time-transform-py --fix`** (substitution): rewrites known persona names, identity tokens, and dev-tree plugin paths that were deliberately used in the meta-repo. Catches static vocabulary the author knew was persona-named or dev-tree-scoped. Table-driven; must be updated when new identity tokens or path patterns are added.
- **Percolate Step 2c content-leakage scan** (per-publish detection): catches dynamic drift — a path slipping into a wiki body, a peer-repo name embedded in a snippet, a machine name in a code comment. These accumulate through normal authoring between substitution-table updates; no static list can anticipate them.

The substitution hook handles the expected case; the per-publish scan handles the unexpected case. Removing either leaves the corresponding failure class uncaught. Per-publish detection earns its keep on every run because authoring drift precedes substitution-table updates; do not treat the scan as redundant once the hook is in place.

Scan-vs-substitute division of labor: the content scan (regex inventory pass) is for *detection*; the substitute pass is for *correction*. Scan earns its keep on day 1 because it catches new patterns the substitute hasn't been taught — a `WARN:` line in scan output is a signal to extend the substitute, not silenced noise.

When `publish.py` mirrors source-to-dest (via `rsync --delete` semantics reimplemented in `publish_sync.py`), add `--exclude=<pattern>` for files the dest has already shipped that the source intentionally lacks (e.g. dest's own README, CHANGELOG generated by release tooling). Without excludes, delete-mirroring strips the dest's local artifacts.

**Path-rewrite enumeration.** The static floor of five plugins for path rewriting is: `coordinator`, `data-science`, `deep-research`, `game-dev`, `web-dev`. `example-game-repo-control` and `example-game-repo-docs` are NOT in the publish tree. The discovery step enumerates `$TARGET/plugins/*/` to pick up plugins added since the floor was last updated. The self-validation guard: if static path-mapping seed patterns start with `plugins/` and don't contain `coordinator-claude`, the substitution has already run — fail loud with restore-from-source instructions.

**Path-rewrite order within depersonalize.** Path rewrite runs BEFORE persona substitution (structural normalization first, naming second).

**Post-percolate verification gate.** After `--fix`, `10-transform.sh` greps for residual `plugins/coordinator-claude` in `.md` files under the publish tree (excluding `archive/`, `tasks/`, `docs/plans/`, `docs/research/`, `docs/decisions/`, `docs/specs/`). Any hit → exit non-zero.

**The live CLI is `publish-time-transform-py`** (claude-klabauter `coordinator/bin/`), carrying forward the substitution-table contract described below. Hook callers use the `N-transform.sh` naming convention. **Each hook hardcodes the consumer-script name ~10× across fallback resolution paths, error messages, and SYNC-WITH comments — it is not single-seam.** Any future rename of the consumer script requires a full grep-and-substitute per hook, not a one-line edit.

## Path-Rewrite Mechanics at Percolate Time

The substitution pass in `publish-time-transform-py --fix` handles more than persona names — it also normalizes dev-tree plugin path references into publish-tree form. This collapse happens at `post-rsync` as part of the same hook invocation.

**Dev-tree → publish-tree path form.** In the meta-repo, plugin files are authored under `plugins/coordinator-claude/<plugin>/` (one extra segment for the upstream source repo). The publish tree drops that segment: the canonical install path is `plugins/<plugin>/`. The substitution table rewrites every occurrence of the dev-tree form to the publish-tree form across all percolated `.md`, `.sh`, and `.py` files.

**Two-segment collapse for the central plugin.** The coordinator plugin itself lives at `plugins/coordinator/` in the dev tree. At percolate time this collapses to `plugins/coordinator/` — a two-segment reduction, not one. The substitution table carries this as a separate rule from the general one-segment drop, because the intermediate `coordinator-claude/coordinator` path is the coordinator plugin's dev-side nesting and must not survive into publish artifacts.

**Plugin enumeration — floor plus discovery.** The substitution pass seeds its path-rewrite table from a static floor of five known plugins: `coordinator`, `data-science`, `deep-research`, `game-dev`, `web-dev`. It then discovers additional published plugins by enumerating `$TARGET/plugins/*/` in the destination tree. The static floor is a correctness guarantee for the core set; the enumeration step picks up plugins that were added since the floor was last updated without requiring a table edit.

**Idempotency.** Re-running `--fix` on an already-percolated tree produces no further changes. Path references already in publish-tree form (`plugins/<plugin>/`) do not match the dev-tree patterns, so the substitution is a no-op on a clean destination.

**Post-percolate verification gate.** `10-transform.sh` runs a `--check` pass after `--fix` and asserts zero residual occurrences of `plugins/coordinator-claude` in any `.md` file under the publish tree. A non-zero result aborts the publish with a clear diagnostic. This gate locks the wiki rule to the substrate: if the substitution table falls out of sync with a new dev-tree path pattern, the abort surfaces the gap immediately rather than silently shipping a malformed reference.

## Authoring Discipline — No Local Paths in Percolation-Destined Content

The `publish-time-transform-py` hook and the percolate Step 2c content scan are **safety nets for inherited content**, not authoring licenses. When writing any doc, skill, or agent file that will be percolated, never hardcode local working-tree paths — even as "doctrine source" citations. Use abstract repo references instead:

- Wrong: `X:/coordinator-claude/docs/wiki/foo.md` <!-- foreign-path-ok: the hardcoded path IS the anti-pattern being critiqued -->
- Right: `docs/wiki/foo.md` (relative to plugin root) or `plugins/coordinator/docs/wiki/foo.md` (from meta-repo root)

Local path leaks survive substitution-table updates (new paths not yet in the regex) and require hand-edits at percolation time. The drift is silent until the per-publish scan catches it. Authoring discipline prevents the class entirely; the hook is the last line of defense, not the first.

Local working-tree paths (`C:/Users/<name>/...`, `/home/<name>/...`) in authored content (skills, agents, wikis) are an authoring-discipline failure, not a depersonalize-substitution failure. <!-- foreign-path-ok: the hardcoded path IS the anti-pattern being critiqued --> The depersonalize hook is defense-in-depth; the primary discipline is: don't write your local path into shared content in the first place. Use `~/.claude/...` or relative paths.

## Versioning Extraction Churn

Removing one optional plugin from a distribution is a MINOR bump, not MAJOR. Semver major implies breaking changes to core API or to every consumer's setup — not "we removed an opt-in surface that was enabled-by-default in our own settings." Reserve MAJOR for the extraction event itself when it changes the install-script contract (path layout moves, MCP server names rename, env-var shape changes that consumers must mirror). Iterative cleanup of the extracted plugin's own surface is MINOR or PATCH.

## Release Notes on Every Merge

At LLM speeds, the human heuristic of "batch small release notes" does not apply — per-merge release notes are cheap enough that skipping them creates audit gaps with no cost savings. Every merge to main gets a release-notes entry, regardless of size. This discipline is encoded in `/merging-to-main` Step 1.5 and applies equally to `/publish-coord-claude`, `/publish-deep-research`, and any other release or publish skill: write the entry at merge time, not retrospectively.

## Plugin-Bundled Wiki Authoring Direction

Plugin doctrine wikis live ONLY at `<plugin>/docs/wiki/<name>.md` — the bundled copy IS the canonical source. There is no dev-side mirror at `~/.claude/docs/wiki/` for plugin-doctrine wikis. Editing the bundled copy directly is the correct and only authoring verb; any dev-side file at that path is a write-direction trap.

**Why single-tree?** Practice evidence: after 9 days of the original dual-tree model, 5 wikis existed only in the bundled tree; 2 same-day drift instances occurred; the dual-tree invariant fails under concurrent authoring because executors read from bundled and write back. Maintaining a two-tree invariant at authoring frequency costs more than it saves.

`sync-plugin-wiki.py` semantics: if `~/.claude/docs/wiki/<name>.md` EXISTS → exit 5 (dev-side mirror of plugin-doctrine wiki — delete to restore single-tree invariant). If only bundled exists: OK. If neither exists: WARN.

The `PreToolUse` guard (claude-klabauter `write_guards/block_dev_side_mirror_wiki.py`) blocks Write/Edit/NotebookEdit to `~/.claude/docs/wiki/<name>.md` when `~/.claude/plugins/*/docs/wiki/<name>.md` exists — the DoE-side `block-dev-side-mirror-wiki.sh` shell equivalent was dead/unwired and removed (engine-tier port already superseded it). Override: `COORDINATOR_OVERRIDE_WIKI_MIRROR=1`.

## Plugin-Bundled Wiki Reference Convention

Plugin doctrine wikis (wikis cited from plugin files like SKILL.md, CLAUDE.md, agent prompts) MUST live inside the plugin at `<plugin>/docs/wiki/<name>.md`. References use the path **relative to the plugin root**.

**Rationale:** Wikis at `~/.claude/docs/wiki/` resolve only on the authoring machine. Marketplace consumers install the plugin into their `~/.claude/plugins/cache/<marketplace>/<plugin>/<sha>/`. References to `docs/wiki/<name>.md` from plugin files must resolve against the plugin's own directory, not the consumer's home directory (which does not contain the demoted content).

**Convention:**
- Plugin doctrine wikis → `plugins/<plugin>/docs/wiki/<name>.md` (bundled inside plugin)
- Project-level wikis (atlas, codebase-specific patterns) → consumer's `~/.claude/docs/wiki/` (NOT cited from plugin files)
- References in plugin files → `docs/wiki/<name>.md` resolved relative to plugin root

**Sync:** `sync-plugin-wiki.py` during `/update-docs` (auto-discovers new wiki citations from plugin files and confirms bundled copies exist).

Source: `archive/specs/2026-05-06-wiki-bundling-for-marketplace-consumers.md`.

## Five-Axis Extraction Checklist — Resource-Path Walk

When extracting a plugin that loads its own assets at runtime (templates, data files, snippets, JSON manifests), the path-resolution code is the highest-risk surface. Pre-extraction the plugin sat next to its consumers and could rely on relative paths from the source-repo root; post-extraction it ships into `~/.claude/plugins/cache/<marketplace>/<plugin>/<sha>/` and those relative paths now resolve to whatever happens to be next to the consumer's cwd.

Five resource-loading axes must be audited at extraction time:

1. **`__file__`-relative reads.** All `Path(__file__).parent / "data" / ...` and `os.path.dirname(__file__)` lookups must resolve inside the plugin tree. Grep `__file__` and inspect each. The translation rule: `Path(__file__).parents[N] / "subdir"` where N is whatever climbs to the plugin root, never beyond.
2. **CWD-relative reads.** Any `open("data/...")`, `Path("config.json").read_text()` is a bug — drop or convert to `__file__`-relative.
3. **Env-var-rooted reads.** `${CLAUDE_PLUGIN_ROOT}` is the supported anchor; anything else (`${EXAMPLE_GAME_REPO_HOME}`, `${PROJECT_RAG_ROOT}`) is a leak.
4. **Sibling-repo reads.** A pre-extraction plugin often peeked at `../<other-plugin>/data/*`. Post-extraction the sibling tree is on a different filesystem path or absent entirely. Grep `..` in path joins.
5. **Hardcoded absolute reads.** `/Users/<name>/...`, `C:\Users\<name>\...`, `X:\<vendor>\...` — never survive consumer install. The depersonalize hook does NOT cover these; authoring discipline does. <!-- foreign-path-ok: the hardcoded path IS the anti-pattern being critiqued -->

The grep pass is mechanical: `rg -n '__file__|os\.path\.dirname|Path\(__file__\)|CLAUDE_PLUGIN_ROOT|\.\./|/Users/|C:[\\/]Users'` across the extracted plugin. Each hit needs a one-line audit before merge.

## Manifest Scan Includes Authoring-Time Outputs by Default

A plugin's release manifest (or percolate `.percolate-ignore`) typically does a recursive walk of the plugin tree to enumerate shipped files. Without explicit excludes, the walk pulls in `tasks/`, `archive/`, `.last-cleanup`, scratch dirs, and `.tmp.*` orphan files from Edit-tool crashes — i.e. the author's working state ships into the consumer cache. Defense: anchor the manifest scan to a deliberate include list (`commands/`, `skills/`, `agents/`, `hooks/`, `docs/wiki/`, `bin/`) rather than "everything under root minus a few excludes." The exclude approach is forever-incomplete; the include approach is auditable.

## Marketplace Source-Path Registrations

When a marketplace entry's `source` field points at a local development tree (`file:///X:/coordinator-claude` or `git+file://...`) rather than a published URL/tag, every consumer install pulls whatever HEAD that tree happens to be at — not a versioned artifact. <!-- foreign-path-ok: illustrative example of a misconfigured source field, not an asserted install location --> The marketplace JSON looks correct, `claude plugin install` succeeds, but version-pinning is structurally impossible. Audit `~/.claude/plugins/known_marketplaces.json` and any `marketplace.json` for `file://` / source-tree `source` fields before shipping. For real distribution, the `source` must resolve to a published location (GitHub release, tagged ref, or wheel URL) consumers cannot mutate locally.

## LSP-Style Plugins Without `plugin.json`

Some plugins distributed alongside language servers (or as LSP extensions of the host) ship without a `plugin.json` manifest because the host launches them via a separate config layer. Claude Code's plugin system requires `plugin.json` at the plugin tree root for enablement to take effect — its absence makes `enabledPlugins["<name>@<marketplace>"]` a silent no-op. When extracting an LSP-adjacent surface as a Claude Code plugin, generate `plugin.json` even if the LSP host doesn't need one. Symptom: install reports success, marketplace shows the plugin, but `claude /` lists none of its slash commands.

## Competing Plugins in Overlapping Domains

When two plugins both expose game-dev (or any overlapping-domain) routing — for instance a `game-dev@coordinator-claude` and a stack-specific `example-game-repo-control@example-game-workbench-repo` — their description-token surfaces and slash-command names collide silently. Both load, both contribute deferred-tool prefaces, and the EM picks whichever description matches first. Defense: gate domain-overlapping plugins via per-project enablement (`docs/wiki/per-project-plugin-gating.md`), so only one set is active in any given project context. Same-marketplace plugins compete the same way — overlap is a function of description, not provenance.

**When competing plugins define the same agents or personas, keep them in sync.** If two plugins both define (for example) `staff-game-dev` (the Game Dev Reviewer), whichever marketplace loads later wins — the losing copy's tool surface is what the EM actually gets. When patching one copy, diff the other: divergence between the two manifests as silent tool-availability regressions (e.g. `Write` permission present in one but absent from the other). Per-project enablement (above) is the structural fix; cross-plugin diff discipline is the safety net while both copies coexist.

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
- **Plugin hooks belong in `hooks/hooks.json`, NOT user-scope `settings.json`.** Hooks in user settings break marketplace distribution. **Exception: `--plugin-dir` delivery** — when delivered via `--plugin-dir` (which disables plugin-declared hook auto-wire, #38699, observed behavior), generate `settings.json` hooks from `hooks.json` as a machine-local delivery artifact; marketplace/OSS consumers keep `hooks.json` as SSOT with the normal auto-wire.
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

## Publish-content policy is explicit (.percolate-ignore + depersonalize-hook), not implicit

Two surfaces gate what reaches a publish repo: `.percolate-ignore` (path-keyed exclusion from rsync) and the depersonalize-hook (post-rsync content transform). Treat both as agent-aware policy, not implementation detail.

- **`.percolate-ignore` is source-keyed.** Glob patterns name source paths the publish-sync should skip. **`publish.py` is outward-only** (source → publish-repo, never the reverse — the publish→live clobber ban).
- **depersonalize-hook fires automatically inside `publish.py`** — not opt-in, not "run if you remember". Two readers in the OSS docs framed it as a manual step and were both wrong. README/agent-install must describe the hook as part of the pipeline, not an optional pass.
- **Hook gaps to know:** `decode-claude-projects-dir.py` historically hardcoded the operator username (`oduffy`) as a special-case; portable shape uses the registry helper. The simplified glob-style patterns in the hook do not match arbitrary regex — pattern additions require testing against the leak-inventory baseline before merge.

The publish pipeline has hooks; they fire; treat them as the contract.

## Publish-repo CI debt — broken-link and persona-leak floors

Two recurring publish-repo failure shapes:

1. **Broken wiki links** in the published subset — links targeting wikis that exist in source but are `.percolate-ignore`'d out of the publish payload. Floor: doc-link-checker run against the published tree, not just the source tree.
2. **Persona-name backstop leaks** — `routing.md` and capability-catalog references to the Game Dev Reviewer, the Staff Engineer, the Data Science Reviewer, etc. survive the depersonalize-hook because they sit in code-comment-style contexts the simplified pattern doesn't match. Floor: explicit allow/deny list in the hook config, audited at publish time.

These are gate failures, not nag-worthy nits. Pre-merge to publish-repo should run both checks.

## Dogfood verification before switch-gears

When a dogfood pass uncovers a publish-pipeline finding ("wikis leaking to publish repo"), verify the substrate before declaring switch-gears. Case: an EM Pass-1 read 3 wikis as proof of a leak class without checking whether the rest of the corpus shared the pattern. Subsequent audit of all 37 wikis showed only 2 wikis were actually private-config (per-project-plugin-gating, example-game-repo-for-your-ue-project) — the other 35 were either clean or sanitizable.

Rule: a publish-pipeline finding scoped at "leak class" needs corpus-wide enumeration before the switch-gears verdict, not a sample of three.

## .percolate-ignore leak-inventory baseline

The percolate pipeline's known concrete leak is `coordinator/lib/__pycache__/`. The corpus inventory currently shows 24 of 37 coordinator wikis clean (load-bearing by inbound-reference count), 13 wikis carrying project-specific scar-tissue (repo names, machine names, battle-story tags), and only 2 of those unsalvageable as OSS-published content.

Baseline implication: `.percolate-ignore` is the small surface — the depersonalize-hook + sanitization-before-publish carries most of the load. Adding paths to `.percolate-ignore` is the last resort, not the default fix.

## Wiki triage at publish time — rewrite-with-placeholders vs .percolate-ignore

Decision tree for a wiki that fails the OSS-publish polarity check:

| Failure shape | Default fix | When to escalate to `.percolate-ignore` |
|---|---|---|
| Project-specific repo names embedded (`example-game-repo`, `example-sim-repo`) | Sanitize via depersonalize-hook (placeholder substitution) | Content is structurally project-private (≥50% private config) |
| Machine-name leaks (`machine-a`, `oduffy`) | Sanitize via depersonalize-hook | Never — always sanitize |
| example-game-repo/UE-specialized content that depends on example-game-repo-control MCP | Extract example-game-repo-specialized siblings (peer-repo-polarity polarity-OUT principle) | Always — UE specialization migrates out of OSS coordinator-claude per peer-repo-polarity |

The `per-project-plugin-gating.md` case (2026-05/06) was the canonical ~50% private-config wiki: example-game-repo-control, example-game-repo-docs, example-sim-repo, example-game-workbench-repo names hardcoded. Resolution: REWRITE (replace concrete names with placeholders) OR EXCLUDE and inline generic gating doctrine into the consumer hook's header comment.

## OSS-docs ground-truth drift — stale command names in README/agent-install/capability-catalog

The OSS-published docs drift independently of the underlying skill/command surface — a slash command renamed or retired in source carries old-name references in:

- the OSS top-level README (capability listings),
- `coordinator/README.md` (sub-component intro),
- `INSTALL.md` (agent-install.md's absorbed successor),
- and the capability-catalog itself when phantom commands persist (the `/fan-out` skill removal left several catalog rows pointing at a non-existent surface).

Closure: every command-surface rename/retire dispatches a doc-link-checker pass against the publish subset, not just the source tree (this is the same floor as the broken-link section above, but for command names rather than wiki links). Routing this through `reviewer-routed-workers` `doc-link-checker` per-plan default is the cheap fix.

The deep-research plugin authentication callout is the canonical bug-shape: install docs said `nlm login` when the actual mechanism is the in-MCP `setup_auth` tool — a wrong-API-name regression the docs-checker pre-flight would have caught.

## depersonalize-hook fires automatically (publish.py, not opt-in)

`publish.py` runs the depersonalize-hook unconditionally on every publish-cycle. The OSS-docs 2026-05-30 audit found two instances of README/agent-install prose framing the hook as a manual step ("run depersonalize before publishing"). Both are wrong and were corrected.

Reader contract: the user/OSS-operator never calls the hook directly. Documenting it as an automatic in-pipeline pass — with the failure mode being "hook ran but missed a pattern" rather than "did the user remember to run it" — is the correct framing.

## depersonalize-hook gaps — hardcoded operator name + simplified-pattern limits

Two structural hazards in the hook to be aware of when extending:

1. **Hardcoded operator-name special-cases.** `decode-claude-projects-dir.py` carried a hardcoded `oduffy` username path for handling the encoded `~/.claude/projects/C--Users-example-operator--claude/` directory. Portable shape resolves operator name from `~/.claude/machine-local/registry.local.toml` (operator identity), not from a baked-in literal.
2. **Pattern surface is glob-simplified, not regex.** The hook's simplified-pattern matcher misses code-comment-style persona references (e.g. `// authored by the Game Dev Reviewer` survives a `the Game Dev Reviewer` token-match). Pattern additions need real testing against the leak-inventory baseline, not eyeballed regex confidence.

## Reverse-drift gate — per-repo scoping via --scope-repo

`/workweek-complete` Step 4g runs a reverse-drift gate to surface any content present in a publish-repo that is missing or stale in source. The gate is scoped per-repo via a `--scope-repo` flag (commit `bf7842ea`) — meta-repo invocations check all registered publish-targets; consumer-repo invocations check only their own source path. Path forms normalize across `the checkout root` (Windows-native), `/x/` (Git-Bash), and `/c/` (WSL/Cygwin).

The gate is structurally inert from `~/.claude` cwd unless a per-plugin command tells it what to scope. The registry shape is identical to `plugin.mirrors.<name>.refresh_cmd` — sibling field `reverse_drift_cmd` registers the per-plugin invocation; Step 4g iterates registered plugins. This generalizes naturally to future `copy_install` plugins.


## Reverse-drift gate surfaced pre-existing game-dev live-install drift

The reverse-drift gate fix didn't just close the scoping gap — it also surfaced pre-existing game-dev live-install drift that the gate's prior structural inertness had been masking. The fix-the-gate / find-the-existing-drift pairing is the normal shape: gate hardening exposes accumulated debt, not just the change under review.

Operationally: after any gate hardening, expect a one-time backlog spike. The game-dev case routed through normal /update-docs cycle, not as an emergency fix.

## Refresh harness test coverage — integration suite for refresh-plugin-live-install.py

The `refresh-plugin-live-install.py` script is covered by an integration harness (per `b1g-037`/`b1g-038`) that exercises the propagation legs (git-state, venv-state) against synthetic plugin layouts. The harness is a hard requirement for changes to the script — the venv leg is exercised end-to-end via `uv pip install -e .` and the test fails loud on missing `uv`. Smoke / unit tests against the script alone are not sufficient; the integration harness is the gate.

## Publish-repo history scrub — force-push reconciliation

`git filter-repo` + force-push is the tool for reconciling the `coordinator-claude` publish repo (`origin/main`) when leaked personal-data or machine-private paths have landed in a publish cycle ahead of `.percolate-ignore` and the depersonalize-hook's current floors.

Operational invariant: a force-push to a publish-repo main is a one-time tool, not a routine remediation — the gates (`.percolate-ignore`, depersonalize-hook, doc-link-checker against publish subset) should make this unnecessary going forward. If the gates fail twice on the same leak class, harden the gate; don't repeat the scrub.

## install.sh leak inventory pre-scrub

The 2026-05-30 audit found leaked files reaching public main via the OSS `install.sh` path — a class of leak orthogonal to `.percolate-ignore` (the script itself referenced paths/identifiers that the rsync boundary couldn't catch). The install-time scripts are part of the publish payload and require the same content-policy floor as the wiki/skill corpus: depersonalize-hook coverage + manual review before any change that touches `install.sh` or `lib/bootstrap-repo.py`.

## propagation_mode = "editable_sibling_venv" — addon editable-installed into a sibling host's venv

Full propagation-leg contract (git-state leg conditioned on `track_ref`, venv-state leg, registry entry shapes, dev-vs-consumer posture) is documented once, above in this file, under `#### propagation_mode = "editable_sibling_venv" — addon editable-installed into a sibling host's venv` — see that section for the leg table and both TOML examples. Do not re-derive the git-state behavior from memory: it is **not** an unconditional `git fetch && git checkout <track_ref>` — the dev posture (`track_ref = "live"`) skips that leg entirely to avoid clobbering a live working tree.

`refresh-plugin-live-install.py` handles editable-into-sibling-venv plugins as an idempotent path (the `uv` requirement above applies): re-running the refresh primitive is a no-op when both legs are current, and only writes when a leg is genuinely stale.

Host-consumer dependency invariant (per b4g-049): the host plugin and the addon share a release-process coupling — bumping the host's published version requires the addon's editable install to be re-verified against the updated `pyproject.toml`, and bumping the addon requires the host's drift probe to re-run. The release ceremonies coordinate this via the per-plugin `refresh_cmd` registry entries.

## Coordinator Install-Root Resolver — Public Contract Surface

<!-- spec-backlink: docs/plans/2026-06-23-coordinator-install-surface-dogfood-hardening.md § C2a -->

`lib/resolve-coordinator-clone.py` is the **single source of truth** for locating the coordinator plugin's install root. Peer repos (`project-rag`, `ue-addon`, `example-game-repo`) and coordinator-owned scripts that need to locate coordinator content or git history MUST bind here rather than each vendoring their own cache-glob fallback or flat-layout hardcode.

### Two resolution modes

**`--for-git-ops`** — returns the `.git`-backed clone. Use this for drift probes, `git log`, `refresh-plugin-live-install.py`, and any operation that reads git history.

Precedence:
1. `COORDINATOR_CLONE` env var (non-empty; must point to a dir with `.git/`)
2. `plugin.mirrors.coordinator-claude.live_path` from `~/.claude/machine-local/registry.local.toml`
3. Flat layout `~/.claude/plugins/coordinator-claude/coordinator` — only if it has `.git/`
4. **Fail-loud** — prints a remediation message and exits non-zero

**`--for-content`** — returns the highest-precedence readable payload dir. Use this for loading libs, agents, snippets, templates, `query-records.js`, and any coordinator content file.

Precedence:
1. `CLAUDE_PLUGIN_ROOT` env var (harness/install-script injection; test-sandbox wins)
2. `COORDINATOR_ROOT` env var (explicit content-root override)
3. Registry `live_path` — the registered clone is authoritative for content when it exists; dev-loop edits in the clone stay live
4. Newest versioned-cache glob: `~/.claude/plugins/cache/coordinator-claude/coordinator/*/` (safe: pure-bash per-component numeric-compare loop so 2.10.0 > 2.9.0; NO `sort -rV`/`realpath`/`grep -P` — a lexicographic `sort -r` would wrongly rank 2.9.0 above 2.10.0)
5. Flat layout: `~/.claude/plugins/coordinator-claude/coordinator`
6. **Fail-loud**

### CLI entrypoint (public contract)

```bash
# Resolve for git operations:
python3 lib/resolve-coordinator-clone.py --clone-root      # legacy alias: --for-git-ops

# Resolve for content (libs, agents, snippets):
python3 lib/resolve-coordinator-clone.py --content-root    # legacy alias: --for-content
```

The resolver is CLI-only: it prints the resolved path to stdout and exits non-zero
with a fail-loud remediation message on stderr if nothing resolves. There is no
importable function for the full precedence ladder (see "Python bridge" below for
the partial env+flat subset that IS importable).

### Sourced mode — retired

The bash-era resolver (`resolve-coordinator-clone.sh`) supported being `source`d
(not executed) into a caller's shell, setting `COORDINATOR_CLONE` and
`COORDINATOR_CONTENT_ROOT` as caller-scope variables — the pattern the 13 in-tree
integration sites used via a `BASH_SOURCE`-relative `../lib` hop. That `.sh` file
was retired in the de-bash campaign (DR-079) and replaced by
`resolve-coordinator-clone.py`, which is invoked as a **subprocess**, never sourced
— there is no caller-scope-variable mode in the Python successor. Per the file's
own docstring, sourced mode had no callers left post-port: the two in-tree bash
sourcers (`bin/cruft-sweep.sh`, `bin/check-mcp-versions.sh`) were repointed to
invoke the CLI directly in the same commit that ported this file. A caller that
needs the resolved path in its own scope captures the subprocess's stdout —
`subprocess.run([sys.executable, "lib/resolve-coordinator-clone.py", "--content-root"], capture_output=True, text=True).stdout`
in Python, or `$(python3 lib/resolve-coordinator-clone.py --content-root)` in a
shell caller — rather than sourcing anything.

<!-- Review: the Staff Engineer F8 — replaced circular `source "${CLAUDE_PLUGIN_ROOT}/lib/..."` example
with the BASH_SOURCE-relative discovery the real integration sites used at the time. That
discovery pattern (and the sourced mode it demonstrated) is itself retired above — kept here
only as provenance for the earlier review round. -->

### Out-of-tree entry shim — `<settings-home>/bin/resolve-coordinator-clone`

`resolve-coordinator-clone` is a member of the settings-home `bin/` resolver family per
`coordinator-installer-shape.md`, not `~/.claude/bin/` (no installer mints content there — Gate 6,
`docs/plans/2026-07-24-coordinator-owns-zero-claude-bin.md`). The fixed path below reflects that
home; the section's deeper mechanism detail (the exact anchor rung and the SessionStart-hook
trigger) describes `install-substrate.py` — engine-subject, claude-klabauter — and is left
unverified from here rather than guessed.

The retired `BASH_SOURCE`-relative pattern above worked only for a caller **inside the
coordinator tree** (the 13 in-tree integration sites). An **out-of-tree consumer** (`project-rag`,
`project-rag-ue-addon`, `example-game-repo`) cannot use it: it is not inside the tree, so before it can
run the resolver it must first *find the resolver file itself* — and the resolver lives inside the
very clone it resolves (the chicken-and-egg). Hand-rolling a find-the-resolver locator in each
consumer re-vendors the exact cache-glob/flat precedence the resolver was built to centralize
(three near-identical copies that drift).

The fix is a coordinator-owned **fixed-path entry shim**, a sibling to `<settings-home>/bin/machine-local`:

```bash
# Out-of-tree consumers call ONE fixed path — zero find-the-file bootstrap:
COORDINATOR_CONTENT="$(<settings-home>/bin/resolve-coordinator-clone --content-root)"
COORDINATOR_CLONE="$(<settings-home>/bin/resolve-coordinator-clone --clone-root)"
```

The shim (`templates/bin/resolve-coordinator-clone`, seeded onto every consumer's
`<settings-home>/bin/` by `lib/install-substrate.py`) is a naked Python script — the bash shim it
replaced (de-bash campaign) used to locate and `exec bash` against a
`resolve-coordinator-clone.sh` trampoline; that trampoline is gone, and this shim now locates
`lib/resolve-coordinator-clone.py` directly and re-execs the current Python interpreter against
it (`os.execv(sys.executable, [sys.executable, str(lib), *argv])`), passing all args through. It
is **position-independent**: it does NOT read its own file location to find the resolver (that
would relocate the consumer's chicken-and-egg). It anchors on the fixed
`${CLAUDE_HOME:-$HOME}/.claude` home — `CLAUDE_HOME` is a `$HOME` substitute, so the `.claude`
suffix is appended OUTSIDE the default (the form `${CLAUDE_HOME:-$HOME/.claude}` is wrong: it breaks
the `CLAUDE_HOME=/tmp/sb` sandbox/CI redirect, which must resolve `/tmp/sb/.claude/`). It walks a
minimal find-the-resolver ladder (env `CLAUDE_PLUGIN_ROOT`/`COORDINATOR_ROOT`/`COORDINATOR_CLONE` →
`.doe-root` pointer → flat layout → newest versioned cache → fail-loud), then hands off to the
located resolver, which still owns ALL content/git-ops precedence — the shim only finds the file.
Because it is position-independent, the live (`bin/`) and template (`templates/bin/`) copies are
byte-identical — enforced by `verify-templates-bin-sync.py`.

Marketplace-plugin installs drop the plugin tree under `~/.claude/plugins/coordinator-claude/` but
never run `install-substrate.py`, so the settings-home `bin/` surface would otherwise be absent on
first boot. A SessionStart `startup` hook closes that gap:
on any boot where `<settings-home>/bin/resolve-coordinator-clone` is missing it runs
`install-substrate.py --setup-only` to lay the full substrate down, then stays silent once the shim
exists (shim-presence is the idempotency guard). The result is that the out-of-tree contract surface
is present after **any** install method — `coordinator:install`, the OSS installer, or a bare
marketplace drop — without operator intervention.

**Binding rule (negative-spec — read before adding a new consumer):** out-of-tree peers
(`project-rag`, `project-rag-ue-addon`, `example-game-workbench-repo`, and every future adopter) **MUST**
call this fixed-path shim and **MUST NOT** hand-roll a find-the-lib locator, copy the shim's ladder,
or re-vendor any cache-glob/flat precedence. The shim's find-the-lib ladder is the ONE sanctioned copy
of that bootstrap. Rationale: two siblings independently derived divergent locator precedences
(`env → registry → newest-cache → flat` vs. `flat → newest-cache`) before the shim centralized them;
a third hand-rolled variant is exactly what this rule prevents. A new consumer that finds itself
writing locate-the-lib logic has taken a wrong turn — bind to the shim instead.

**Contract stability:** the fixed path, the `--for-content`/`--for-git-ops` flags, and the
`CLAUDE_PLUGIN_ROOT`/`COORDINATOR_ROOT`/`COORDINATOR_CLONE` env names are **append-only**. Removing
or renaming any is a breaking change requiring a coordinated cross-repo memo wave to
project-rag / project-rag-ue-addon / example-game-workbench-repo — never a silent edit.

### Python bridge

`coordinator_root()` in `lib/claude-home/_claude_home.py` provides a Python-importable subset covering the env-var tiers (CLAUDE_PLUGIN_ROOT, COORDINATOR_ROOT, flat layout). The registry and versioned-cache tiers require the CLI. CLI: `claude-home coordinator-root`.

**Note:** `coordinator_root()` covers only env+flat tiers — prefer the CLI (`python3 lib/resolve-coordinator-clone.py --content-root`) on cache-only installs where the registry/versioned-cache path is needed.

### Env-var override names

| Env var | Tier | Role |
|---|---|---|
| `CLAUDE_PLUGIN_ROOT` | `--for-content` tier 1 | Harness/test sandbox injection; beats all other content tiers |
| `COORDINATOR_ROOT` | `--for-content` tier 2 | Explicit content-root override |
| `COORDINATOR_CLONE` | `--for-git-ops` tier 1 | Explicit git-clone override; must point to a `.git`-bearing dir |

### Resolver invocation is subprocess-only, no trusted-root guard needed

The resolver and its callers are Python. A caller invokes the resolver as a subprocess and reads its stdout — there is no `source`-step caller-scope injection to guard against, so no trusted-root sourcing guard is needed.

```bash
# git-ops sites (need .git history):
COORDINATOR_CLONE="$(python3 lib/resolve-coordinator-clone.py --clone-root)"

# content sites (libs, scripts, agents) — no trusted-root guard needed;
# subprocess invocation never injects code into the caller's own scope:
COORDINATOR_CONTENT_ROOT="$(python3 lib/resolve-coordinator-clone.py --content-root)"
# then use $COORDINATOR_CONTENT_ROOT/lib/... etc.
```

A Python caller in-tree imports `subprocess` directly rather than shelling out through a wrapper script; the `python3 lib/resolve-coordinator-clone.py` invocation above is the shell-caller shape.

## Renaming Files Across a `source_is_live` Symlink Boundary

<!-- spec-backlink: state/lessons.md:38 (2026-06-15) -->

When a plugin is in `propagation_mode = "source_is_live"` (e.g. `coordinator-claude` installed over `~/.claude/`), file content may be tracked by two separate git repos simultaneously — the canonical source repo and the meta-repo that git-tracks the symlinked tree. A `git mv` in the meta-repo moves the index entry without touching the underlying filesystem path (the symlink target owns that), which leaves file content at the old path in the canonical repo while the meta-repo's index points to the new name.

**Correct rename sequence for a file behind a `source_is_live` symlink:**

1. **Canonical side first** — `git -C <canonical-repo-path> mv old/path new/path && git -C <canonical-repo-path> commit -m "..."`. This performs the actual filesystem rename.
2. **Meta-repo index mirror** — in the meta-repo, `git add old/path new/path` (the deleted path and the created path). Git detects this as a rename (`R100`) without needing `git mv`, because the filesystem change already happened via step 1.
3. **Commit both repos.** The meta-repo commit captures the index-mirror of what the canonical repo already did on disk.

**Why `git mv` in the meta-repo alone fails:** it moves the meta-repo index entry but issues no filesystem call to the symlink target. The canonical repo still has the file at the old path; the live install reflects the canonical repo's filesystem. Result: the meta-repo index and the canonical repo filesystem are desynchronized — the file appears renamed in `git status` on the meta-repo side but is absent at the new path at runtime.

**Empirical basis:** `~/.claude/plugins/example-game-workbench-repo/example-game-repo/` is a symlink to `/x/example-game-workbench-repo/plugin/example-game-repo/`. A rename attempted via `git mv` in `~/.claude` moved only the meta-repo index entry, leaving content desynced. The correct path was confirmed: canonical `git mv` first, then meta-repo `git add old new`.

**Rule:** when renaming a tracked file behind a `source_is_live` symlink, the filesystem rename belongs to the canonical repo. The meta-repo's role is index-mirroring only — `git add <old> <new>`, never `git mv`.
