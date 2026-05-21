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

  Canonical propagation primitive: `bash bin/refresh-plugin-live-install.sh <plugin>` — executes both legs atomically, with pre-flight (clean working tree check) and post-flight (drift probe). Both legs must close together; advancing git HEAD without re-running `uv pip install -e .` leaves the venv leg stale and can cause silent `ImportError`.

- **Live install IS the canonical source (e.g. coordinator-claude — installed over `~/.claude/`):** there is no source → live propagation step. Edits made in `~/.claude/plugins/coordinator-claude/...` take effect immediately. These plugins carry `propagation_mode = "source_is_live"` in `~/.claude/machine-local/registry.local.toml::plugin.mirrors`. The drift probe treats them as structural no-ops; the refresh script skips them.

**Drift detection:** `bash bin/check-plugin-drift.sh` probes both legs (git-state and venv-state) for each registered plugin and surfaces results in `/workday-start` Step 1.10 Addon Health daily.

**`publish.sh` direction:** `publish.sh` runs source → publish-repo (sibling) for cross-machine distribution. It does NOT write back to the live install; the 2026-05-20 ban on publish-repo → live install clobber is preserved. These are orthogonal operations.

Spec: `docs/plans/2026-05-21-plugin-source-live-mirror-doctrine.md`.

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

### 12. Cross-repo port: prefer registration-seam over parallel-surface

When porting a feature from a host repo into a plugin/addon, default to **using the host's registration hookspec or seam** rather than authoring a parallel front-end on the plugin side. A parallel-surface port creates two registration paths the host has to reconcile at runtime and routinely results in one path silently winning while the other looks active. Before authoring a plugin-side surface that mirrors an existing host surface, grep the host's registration corpus (hookspec discovery, pluggy entry points, plugin-manifest readers) and route through the existing seam. (2026-05-16, project-rag-ue-addon.)

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

The meta-repo (`~/.claude/`) authors files with persona display names — the Staff Engineer, the Game Dev Reviewer, the Data Science Reviewer, the Front-End Reviewer, the UX Reviewer, the Director of Engineering, the VP-Product Reviewer — because that's how the human PM thinks of the reviewers. The publish repo (`X:/coordinator-claude` or any open-source consumer mirror) ships nameless: reviewers are referred to by articulated role labels (the Staff Engineer, the Game Dev Reviewer, etc.), with naming offered as an opt-in install step. Personae ≠ names — the doctrine is in `docs/evolution/03-personas-as-ergonomics.md` (publish-repo copy). Without a guard, percolation reintroduces names silently, since the meta-repo source still has them.

Two paired tools enforce the boundary:

- **Publish-repo CI gate.** `.github/scripts/check-persona-names.py` runs as a tracked-files scan auto-discovered by `run-all-checks.py`. Hard-fails any commit/PR where canonical-layer files (`*.md`, `*.sh`, `*.py`; excludes `archive/`, `tasks/`, `experiments/`, `evals/`, `docs/{plans,research,decisions,specs}/`) contain bare persona display names. Suppression: `# noqa: persona-names` inline, or `.github/.persona-names-allowlist` file-based (`filepath:line_number` per line).

- **Meta-repo registered hook.** `setup/percolate-hooks/<target>/post-rsync/10-depersonalize.sh` is a thin wrapper around `bin/depersonalize-for-publish.sh` in `~/.claude/plugins/coordinator/bin/`. The depersonalize binary itself supports `--check` (exit 1 on hits) or `--fix` (in-place rewrite to role labels, with `.bak` backups). The hook receives the destination path as `$1` and the synced-files list via stdin (newline-delimited), then `--fix`es each `*.md`/`*.sh`/`*.py` file. Registered for `coordinator-claude` and `deep-research-claude` (open-source publish targets); deliberately NOT registered for `holodeck` (keeps persona names natively). Only the hook lives meta-repo-local; the binary it calls is shipped with the coordinator plugin and percolates with it. The `--fix` mode handles the common "the X" / "The X" article cases including the "the X" double-article it would otherwise produce.

**`publish.sh` is the authority for percolation — manual `cp` is wrong.** Percolating to `coordinator-claude` (or any registered publish target) means running `bash ~/.claude/setup/publish.sh <target>`, not copying files by hand. Manual `cp` bypasses the depersonalize pipeline, the content-leakage scan, and the `.percolate-ignore` filter — the resulting publish repo may contain persona names, local paths, or excluded files the author didn't intend to ship. The publish-targets list at `setup/publish-targets.sh` is the authority; if a target is missing from it, register it there rather than working around it with ad-hoc copies.

Workflow during percolation:

1. Run `bash ~/.claude/setup/publish.sh <target>` (a.k.a. percolate / push-to-publish-repo) — or `/percolate <target>` for the dry-run-confirm-real-run skill wrapper.
2. `publish.sh` discovers and runs every executable script in `setup/percolate-hooks/<target>/{pre-rsync,post-rsync,pre-ci}/*.sh` in lexical order at the corresponding boundary. The depersonalize hook fires automatically at `post-rsync` for any target with one registered. Failure-semantics: non-zero hook exit aborts the publish; post-rsync abort = destination partially mutated, recovery is to fix the hook and re-run (`--check`/`--fix` is idempotent).
3. CI on the publish repo re-runs `python .github/scripts/check-persona-names.py` on push as the safety net — even if a hook is mis-registered, the gate catches regressions.

To add or modify a hook for a target: place an executable `*.sh` script under `setup/percolate-hooks/<target>/<hook-point>/`. Numeric prefixes (`10-`, `20-`) order execution. Authoring help: see `docs/wiki/percolate-setup.md` (walked by `/percolate` Branch 0 and `/setup` percolation phase) — it scaffolds the hook directories with `.gitkeep`. Registration is convention-based discovery — no manifest required.

Source-side publish-content policy (`.percolate-ignore`) lives at `$SOURCE_DIR/.percolate-ignore` (gitignore-shaped, simplified subset — `**/` not supported). `publish.sh` `sync_mirror` honors it in both copy and delete phases. See `docs/wiki/percolate-setup.md` (walked by `/percolate` Branch 0 and `/setup` percolation phase) for the full audit-and-scaffold procedure, including classification taxonomy and grey-zone handling.

The vocabulary table (also in `docs/customization.md` "Reviewer Roles" of the publish repo): the Staff Engineer → the Staff Engineer; the Director of Engineering → the Director of Engineering; the VP-Product Reviewer → the VP-Product Reviewer; the Game Dev Reviewer → the Game Dev Reviewer; the Front-End Reviewer → the Front-End Reviewer; the UX Reviewer → the UX Reviewer; the Data Science Reviewer → the Data Science Reviewer.

> **Publish-repo follow-up (2026-05-17):** The `the Director of Engineering → the Director of Engineering` mapping replaces the prior `the Director of Engineering → the Ambition Advocate` mapping. The publish repo's `docs/customization.md` "Reviewer Roles" table, any `check-persona-names.py` allow-list, and any personalizer script that maps role labels back to user-chosen names must be updated to match — `the Ambition Advocate` is retired, `the Director of Engineering` is the new canonical role label. Personalizers should let the new user pick any name for the DoE role; the title carries the rank, the name is cosmetic. Previously-published copies of files containing `the Ambition Advocate` will need a search-and-replace at next publish.

## Auxiliary Sync — Publish-Repo Top-Level `docs/wiki/`

**Auxiliary sync — publish-repo top-level `docs/wiki/`.** The publish repo also carries a public-facing wiki at `<publish-repo>/docs/wiki/` (separate from the plugin tree under `<publish-repo>/plugins/coordinator/docs/wiki/`). This auxiliary surface is synced from the plugin's `docs/wiki/` via a second publish-target row (`coordinator-claude-toplevel-wiki`) with `flat-mirror` mode plus a publish-native allowlist. The allowlist lives at `setup/percolate-hooks/coordinator-claude-toplevel-wiki/post-rsync/publish-native-allowlist.txt`; files named there are backed up before rsync and restored after, so publish-native authoring on the public side (including uncommitted edits) survives meta-repo syncs. Verification gate at `30-verify-toplevel-wiki.sh` enforces canary survival, forbidden-shape grep, and rewrite-target sanity.

**Allowlist lives in `setup/percolate-hooks/<target>/post-rsync/` (hook-local) rather than in the publish repo** because (1) the consumer is the meta-repo hook — locality with the consumer beats locality with the protected data; (2) it documents the allowlist mechanism alongside the hook, making the existence of an allowlist visible to anyone reading `percolate-hooks/`; (3) future plugins with publish-native allowlists organize under one tree.

**When to add a file to the allowlist:** the file is authored on the publish-repo side (its git history lives in `/x/coordinator-claude/`), and it is not a copy of any plugin wiki. Today: `task-tier-guidance.md` is the sole entry.

**When NOT to use the allowlist:** if a plugin-side wiki and a publish-side wiki need to converge into one canonical source, move the publish-side authoring back to the plugin and remove from allowlist. The allowlist is for genuinely divergent lifecycles, not for resisting normalization.

Spec backlink: `docs/plans/2026-05-18-publish-repo-toplevel-wiki-sync.md` § Shape decision A*.

## Scan/Substitution Division of Labor

Two tools enforce the publish boundary; they solve different failure modes and are not interchangeable:

- **`depersonalize-for-publish.sh --fix`** (substitution): rewrites known persona names, identity tokens, and dev-tree plugin paths that were deliberately used in the meta-repo. Catches static vocabulary the author knew was persona-named or dev-tree-scoped. Table-driven; must be updated when new identity tokens or path patterns are added.
- **Percolate Step 2c content-leakage scan** (per-publish detection): catches dynamic drift — a path slipping into a wiki body, a peer-repo name embedded in a snippet, a machine name in a code comment. These accumulate through normal authoring between substitution-table updates; no static list can anticipate them.

The substitution hook handles the expected case; the per-publish scan handles the unexpected case. Removing either leaves the corresponding failure class uncaught. Per-publish detection earns its keep on every run because authoring drift precedes substitution-table updates; do not treat the scan as redundant once the hook is in place.

Scan-vs-substitute division of labor: the content scan (regex inventory pass) is for *detection*; the substitute pass is for *correction*. Scan earns its keep on day 1 because it catches new patterns the substitute hasn't been taught — a `WARN:` line in scan output is a signal to extend the substitute, not silenced noise.

When `publish.sh` uses `rsync --delete` to mirror source-to-dest, add `--exclude=<pattern>` for files the dest has already shipped that the source intentionally lacks (e.g. dest's own README, CHANGELOG generated by release tooling). Without excludes, `--delete` strips the dest's local artifacts.

## Path-Rewrite Mechanics at Percolate Time

The substitution pass in `depersonalize-for-publish.sh --fix` handles more than persona names — it also normalizes dev-tree plugin path references into publish-tree form. This collapse happens at `post-rsync` as part of the same hook invocation.

**Dev-tree → publish-tree path form.** In the meta-repo, plugin files are authored under `plugins/coordinator-claude/<plugin>/` (one extra segment for the upstream source repo). The publish tree drops that segment: the canonical install path is `plugins/<plugin>/`. The substitution table rewrites every occurrence of the dev-tree form to the publish-tree form across all percolated `.md`, `.sh`, and `.py` files.

**Two-segment collapse for the central plugin.** The coordinator plugin itself lives at `plugins/coordinator/` in the dev tree. At percolate time this collapses to `plugins/coordinator/` — a two-segment reduction, not one. The substitution table carries this as a separate rule from the general one-segment drop, because the intermediate `coordinator-claude/coordinator` path is the coordinator plugin's dev-side nesting and must not survive into publish artifacts.

**Plugin enumeration — floor plus discovery.** The substitution pass seeds its path-rewrite table from a static floor of five known plugins: `coordinator`, `data-science`, `deep-research`, `game-dev`, `web-dev`. It then discovers additional published plugins by enumerating `$TARGET/plugins/*/` in the destination tree. The static floor is a correctness guarantee for the core set; the enumeration step picks up plugins that were added since the floor was last updated without requiring a table edit.

**Idempotency.** Re-running `--fix` on an already-percolated tree produces no further changes. Path references already in publish-tree form (`plugins/<plugin>/`) do not match the dev-tree patterns, so the substitution is a no-op on a clean destination.

**Post-percolate verification gate.** `10-depersonalize.sh` runs a `--check` pass after `--fix` and asserts zero residual occurrences of `plugins/coordinator-claude` in any `.md` file under the publish tree. A non-zero result aborts the publish with a clear diagnostic. This gate locks the wiki rule to the substrate: if the substitution table falls out of sync with a new dev-tree path pattern, the abort surfaces the gap immediately rather than silently shipping a malformed reference.

## Authoring Discipline — No Local Paths in Percolation-Destined Content

The `depersonalize-for-publish.sh` hook and the percolate Step 2c content scan are **safety nets for inherited content**, not authoring licenses. When writing any doc, skill, or agent file that will be percolated, never hardcode local working-tree paths — even as "doctrine source" citations. Use abstract repo references instead:

- Wrong: `X:/coordinator-claude/docs/wiki/foo.md`
- Right: `docs/wiki/foo.md` (relative to plugin root) or `plugins/coordinator/docs/wiki/foo.md` (from meta-repo root)

Local path leaks survive substitution-table updates (new paths not yet in the regex) and require hand-edits at percolation time. The drift is silent until the per-publish scan catches it. Authoring discipline prevents the class entirely; the hook is the last line of defense, not the first.

Local working-tree paths (`C:/Users/<name>/...`, `/home/<name>/...`) in authored content (skills, agents, wikis) are an authoring-discipline failure, not a depersonalize-substitution failure. The depersonalize hook is defense-in-depth; the primary discipline is: don't write your local path into shared content in the first place. Use `~/.claude/...` or relative paths.

## Versioning Extraction Churn

Removing one optional plugin from a distribution is a MINOR bump, not MAJOR. Semver major implies breaking changes to core API or to every consumer's setup — not "we removed an opt-in surface that was enabled-by-default in our own settings." Reserve MAJOR for the extraction event itself when it changes the install-script contract (path layout moves, MCP server names rename, env-var shape changes that consumers must mirror). Iterative cleanup of the extracted plugin's own surface is MINOR or PATCH.

## Release Notes on Every Merge

At LLM speeds, the human heuristic of "batch small release notes" no longer applies — per-merge release notes are cheap enough that skipping them creates audit gaps with no cost savings. Every merge to main gets a release-notes entry, regardless of size. This discipline is encoded in `/merge-to-main` Step 1.5 and applies equally to `/publish-coord-claude`, `/publish-deep-research`, and any other release or publish skill: write the entry at merge time, not retrospectively.

## Plugin-Bundled Wiki Authoring Direction

Edits to plugin-bundled wikis (`<plugin>/docs/wiki/<name>.md`) belong on the dev-side authoring tree first; `bin/sync-plugin-wiki.sh` mirrors authoring → bundled. Editing the bundled copy directly without the dev-side counterpart gets silently undone the next time the sync script runs. Mirror-sync scripts must detect direction-of-truth asymmetry pre-sync and escalate rather than overwrite. Executor briefs editing bundled wikis should include the dev-side path explicitly.

## Plugin-Bundled Wiki Reference Convention

**Canonical decision (2026-05-06):** Plugin doctrine wikis (wikis cited from plugin files like SKILL.md, CLAUDE.md, agent prompts) MUST live inside the plugin at `<plugin>/docs/wiki/<name>.md`. References use the path **relative to the plugin root**.

**Rationale:** Wikis at `~/.claude/docs/wiki/` resolve only on the authoring machine. Marketplace consumers install the plugin into their `~/.claude/plugins/cache/<marketplace>/<plugin>/<sha>/`. References to `docs/wiki/<name>.md` from plugin files must resolve against the plugin's own directory, not the consumer's home directory (which does not contain the demoted content).

**Convention:**
- Plugin doctrine wikis → `plugins/<plugin>/docs/wiki/<name>.md` (bundled inside plugin)
- Project-level wikis (atlas, codebase-specific patterns) → consumer's `~/.claude/docs/wiki/` (NOT cited from plugin files)
- References in plugin files → `docs/wiki/<name>.md` resolved relative to plugin root

**Sync:** `bin/sync-plugin-wiki.sh` during `/update-docs` (auto-discovers new wiki citations from plugin files and confirms bundled copies exist).

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
