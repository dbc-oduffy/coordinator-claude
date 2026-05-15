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

Agents at runtime read from `~/.claude/plugins/<name>/` (the installed copy), NOT from the meta-repo source tree. When debugging an agent's behavior, verify against the installed copy; source edits don't take effect until `bin/publish.sh` (or the equivalent percolation step) propagates them. A "fixed it in source" claim with no propagation step is a no-op for the running agent.

### 10. Plugin hooks belong in `hooks/hooks.json`, not user-scope `settings.json`

A SessionStart/PreToolUse/etc. hook registered in `~/.claude/settings.json` works on the author's machine but doesn't follow the plugin to marketplace consumers — install lays down the script but never registers the event. Always ship `hooks/hooks.json` alongside the script in the plugin tree so install auto-wires it. User-scope settings is for non-plugin overrides only. Treat this as a portability check at extraction time: grep `~/.claude/settings.json` for any hook entry whose script lives under the plugin tree, and migrate it to the plugin's `hooks/hooks.json` before shipping.

## Test From a Clean Profile

The single highest-leverage validation: run the install script from a profile that has never used Claude Code before. Anything that "just worked" on the author's machine from prior manual setup will fail loudly. This catches gaps 1, 6, 8, 9, and 10 in one pass.

## Atlas Drift After Extraction

When a plugin moves to a standalone repo, the consumer-side architecture atlas, file-index paths, and MCP-tool prefixes go stale silently — greppable-by-old-name is not the same as broken-by-old-name. Old paths still resolve in cache, old tool prefixes still appear in agent-prompt examples, and nothing surfaces the drift until a new contributor reads the atlas and gets pointed at a path that no longer exists.

Plugin-extraction PRs need an explicit atlas-sweep step before merge: grep the consumer repo for the old plugin path, the old MCP tool prefix, and the old marketplace name; update or repoint each hit; verify the architecture atlas's plugin section reflects the new layout. Treat this as part of the extraction PR itself, not a follow-up — the cost of doing it later is ambiguous "is this stale or current?" reads from every downstream consumer until someone audits.

## CRLF/LF Verification on Percolation

Percolation from a Unix-authored source repo to a Windows consumer (or vice versa) silently swaps line endings under the wrong git config, producing whole-file diffs that read as no-op edits but change every line of every file. "Agent reported clean" is not enough — verify percolation by per-file diff with `git diff --stat` and a spot-check on a handful of files; a clean diff under `core.autocrlf=true` may hide the entire reformatted file. Establish `.gitattributes` rules early, and run a verification pass after every cross-platform percolation.

## Persona-Name Guard on Percolation

The meta-repo (`~/.claude/`) authors files with persona display names — the Staff Engineer, the Game Dev Reviewer, the Data Science Reviewer, Palí, the UX Reviewer, Zolí, the VP-Product Reviewer — because that's how the human PM thinks of the reviewers. The publish repo (`X:/coordinator-claude` or any open-source consumer mirror) ships nameless: reviewers are referred to by articulated role labels (the Staff Engineer, the Game Dev Reviewer, etc.), with naming offered as an opt-in install step. Personae ≠ names — the doctrine is in `docs/evolution/03-personas-as-ergonomics.md` (publish-repo copy). Without a guard, percolation reintroduces names silently, since the meta-repo source still has them.

Two paired tools enforce the boundary:

- **Publish-repo CI gate.** `.github/scripts/check-persona-names.py` runs as a tracked-files scan auto-discovered by `run-all-checks.py`. Hard-fails any commit/PR where canonical-layer files (`*.md`, `*.sh`, `*.py`; excludes `archive/`, `tasks/`, `experiments/`, `evals/`, `docs/{plans,research,decisions,specs}/`) contain bare persona display names. Suppression: `# noqa: persona-names` inline, or `.github/.persona-names-allowlist` file-based (`filepath:line_number` per line).

- **Meta-repo registered hook.** `setup/percolate-hooks/<target>/post-rsync/10-depersonalize.sh` is a thin wrapper around `bin/depersonalize-for-publish.sh` in `~/.claude/plugins/coordinator-claude/coordinator/bin/`. The depersonalize binary itself supports `--check` (exit 1 on hits) or `--fix` (in-place rewrite to role labels, with `.bak` backups). The hook receives the destination path as `$1` and the synced-files list via stdin (newline-delimited), then `--fix`es each `*.md`/`*.sh`/`*.py` file. Registered for `coordinator-claude` and `deep-research-claude` (open-source publish targets); deliberately NOT registered for `holodeck` (keeps persona names natively). Only the hook lives meta-repo-local; the binary it calls is shipped with the coordinator plugin and percolates with it. The `--fix` mode handles the common "the X" / "The X" article cases including the "the X" double-article it would otherwise produce.

Workflow during percolation:

1. Run `bash ~/.claude/setup/publish.sh <target>` (a.k.a. percolate / push-to-publish-repo) — or `/percolate <target>` for the dry-run-confirm-real-run skill wrapper.
2. `publish.sh` discovers and runs every executable script in `setup/percolate-hooks/<target>/{pre-rsync,post-rsync,pre-ci}/*.sh` in lexical order at the corresponding boundary. The depersonalize hook fires automatically at `post-rsync` for any target with one registered. Failure-semantics: non-zero hook exit aborts the publish; post-rsync abort = destination partially mutated, recovery is to fix the hook and re-run (`--check`/`--fix` is idempotent).
3. CI on the publish repo re-runs `python .github/scripts/check-persona-names.py` on push as the safety net — even if a hook is mis-registered, the gate catches regressions.

To add or modify a hook for a target: place an executable `*.sh` script under `setup/percolate-hooks/<target>/<hook-point>/`. Numeric prefixes (`10-`, `20-`) order execution. Authoring help: see `docs/wiki/percolate-setup.md` (walked by `/percolate` Branch 0 and `/setup` percolation phase) — it scaffolds the hook directories with `.gitkeep`. Registration is convention-based discovery — no manifest required.

Source-side publish-content policy (`.percolate-ignore`) lives at `$SOURCE_DIR/.percolate-ignore` (gitignore-shaped, simplified subset — `**/` not supported). `publish.sh` `sync_mirror` honors it in both copy and delete phases. See `docs/wiki/percolate-setup.md` (walked by `/percolate` Branch 0 and `/setup` percolation phase) for the full audit-and-scaffold procedure, including classification taxonomy and grey-zone handling.

The vocabulary table (also in `docs/customization.md` "Reviewer Roles" of the publish repo): the Staff Engineer → the Staff Engineer; Zolí → the Ambition Advocate; the VP-Product Reviewer → the VP-Product Reviewer; the Game Dev Reviewer → the Game Dev Reviewer; Palí → the Front-End Reviewer; the UX Reviewer → the UX Reviewer; the Data Science Reviewer → the Data Science Reviewer.

## Scan/Substitution Division of Labor

Two tools enforce the publish boundary; they solve different failure modes and are not interchangeable:

- **`depersonalize-for-publish.sh --fix`** (substitution): rewrites known persona names and identity tokens that were deliberately used in the meta-repo. Catches static vocabulary the author knew was persona-named. Table-driven; must be updated when new identity tokens are added.
- **Percolate Step 2c content-leakage scan** (per-publish detection): catches dynamic drift — a path slipping into a wiki body, a peer-repo name embedded in a snippet, a machine name in a code comment. These accumulate through normal authoring between substitution-table updates; no static list can anticipate them.

The substitution hook handles the expected case; the per-publish scan handles the unexpected case. Removing either leaves the corresponding failure class uncaught. Per-publish detection earns its keep on every run because authoring drift precedes substitution-table updates; do not treat the scan as redundant once the hook is in place.

Scan-vs-substitute division of labor: the content scan (regex inventory pass) is for *detection*; the substitute pass is for *correction*. Scan earns its keep on day 1 because it catches new patterns the substitute hasn't been taught — a `WARN:` line in scan output is a signal to extend the substitute, not silenced noise.

When `publish.sh` uses `rsync --delete` to mirror source-to-dest, add `--exclude=<pattern>` for files the dest has already shipped that the source intentionally lacks (e.g. dest's own README, CHANGELOG generated by release tooling). Without excludes, `--delete` strips the dest's local artifacts.

## Authoring Discipline — No Local Paths in Percolation-Destined Content

The `depersonalize-for-publish.sh` hook and the percolate Step 2c content scan are **safety nets for inherited content**, not authoring licenses. When writing any doc, skill, or agent file that will be percolated, never hardcode local working-tree paths — even as "doctrine source" citations. Use abstract repo references instead:

- Wrong: `X:/coordinator-claude/docs/wiki/foo.md`
- Right: `docs/wiki/foo.md` (relative to plugin root) or `plugins/coordinator-claude/coordinator/docs/wiki/foo.md` (from meta-repo root)

Local path leaks survive substitution-table updates (new paths not yet in the regex) and require hand-edits at percolation time. The drift is silent until the per-publish scan catches it. Authoring discipline prevents the class entirely; the hook is the last line of defense, not the first.

Local working-tree paths (`C:/Users/<name>/...`, `/home/<name>/...`) in authored content (skills, agents, wikis) are an authoring-discipline failure, not a depersonalize-substitution failure. The depersonalize hook is defense-in-depth; the primary discipline is: don't write your local path into shared content in the first place. Use `~/.claude/...` or relative paths.

## Versioning Extraction Churn

Removing one optional plugin from a distribution is a MINOR bump, not MAJOR. Semver major implies breaking changes to core API or to every consumer's setup — not "we removed an opt-in surface that was enabled-by-default in our own settings." Reserve MAJOR for the extraction event itself when it changes the install-script contract (path layout moves, MCP server names rename, env-var shape changes that consumers must mirror). Iterative cleanup of the extracted plugin's own surface is MINOR or PATCH.

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

## GitHub Org Rename Breaks `claude plugin update`

When a plugin's GitHub org/repo is renamed (`old-org/plugin` → `new-org/plugin`), GitHub auto-redirects `git clone` but `claude plugin update <plugin>` may still hit the cached old URL in `known_marketplaces.json` and silently fail (or worse, succeed against a stale fork that took over the old name). Defense: at rename time, push a final commit to the old repo whose README says "moved to <new>"; update `known_marketplaces.json` `source` URL across all consumers via a one-shot migration note; mention in the release notes that consumers must re-run `claude plugin marketplace remove/add` to pick up the new URL.
