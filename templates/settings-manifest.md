# Settings Manifest — Machine-Specific Configuration

> Companion to `settings.json`. Read this at orient time to understand what's
> portable, what's machine-specific, and what gates each setting.
>
> **Executable truth for marketplace-sibling enablement and registration
> lives in `bin/seed-marketplace-enabledplugins.py`**, run once per install by
> `coordinator:install` — not a SessionStart hook. `bin/platform-localize.sh`
> (the prior SessionStart-hook-based generator) was de-wired 2026-07-15 and no
> longer runs; do not treat it as executable truth for anything on this page.
> This manifest is the human/EM-readable context around the seeder.

## Architecture

```
settings.json          (tracked)    — union of what ALL machines need
settings.local.json    (gitignored) — per-machine overrides, auto-generated
known_marketplaces.json (gitignored) — CC plugin discovery cache (bug #51806)
registry.local.toml    (gitignored) — per-machine repo paths and values
```

`settings.local.json` takes precedence over `settings.json` (Claude Code
Local > User scope). `bin/seed-marketplace-enabledplugins.py` generates the
marketplace-sibling `enabledPlugins` and marketplace-registration entries in
it at `coordinator:install` time, from what's actually checked out on this
machine (registry-driven, manifest-derived — see § Marketplace Registration
below). It merges-never-clobbers: an existing entry in either `settings.json`
or `settings.local.json` always wins over the seeded default.

## Plugin Infrastructure Requirements

Each plugin below requires specific infrastructure to be useful, gated on
whether a `machine-local/registry.local.toml` key is populated. **This gating
is currently a documented convention, not an automated one** — the
SessionStart hook that used to read the registry key and disable the plugin
in `settings.local.json` (`bin/platform-localize.sh`) was de-wired
2026-07-15 and no automated replacement exists yet. Until one ships, adding a
row to the table below is bookkeeping only; enable/disable the plugin by hand
in `settings.local.json`.

| Plugin | Marketplace | Registry Key | Infrastructure |
|--------|-------------|-------------|----------------|
| *(none by default)* | | | |

The coordinator's core plugins (coordinator, deep-research, web-dev,
data-science) are universally available — they live under `~/.claude/plugins/`
and have no external infrastructure dependency.

**To add a gated plugin:** see § Adding a New Gated Plugin below for the
step-by-step instructions.

## Marketplace Registration

Directory-source marketplaces require absolute paths that differ per machine.
`bin/seed-marketplace-enabledplugins.py`, run at `coordinator:install` time,
enumerates present marketplace siblings (registry-driven, manifest-derived —
same enumeration as § Plugin Infrastructure Requirements' `enabledPlugins`
seeding above) and, for each, discovers the marketplace directory (the
directory containing `.claude-plugin/`, root or nested) and writes correct
absolute paths to:
- `settings.local.json` → `extraKnownMarketplaces` (the documented mechanism)
- `~/.claude/plugins/known_marketplaces.json` (the file CC actually reads — bug #51806)

Both writes are merge-never-clobber: an existing entry for a marketplace name
wins over the seeded default, and the seeder is idempotent (safe to re-run on
every `coordinator:install`).

## Environment Variables

| Variable | In `settings.json` | Purpose | Machine-specific? |
|----------|--------------------|---------|--------------------|
| `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` | `"1"` | Agent Teams + deep-research | No — all machines |
| `CLAUDE_CODE_ENABLE_TODO_TOOLS` | `"1"` | Makes Task* tools available to a main session on models that don't get them by default (v2.1.233+) | No — all machines |
| `CLAUDE_CODE_USE_POWERSHELL_TOOL` | `"1"` on a Windows host under a no-Bash directive; unset elsewhere | Pin the PowerShell tool's availability instead of inheriting a progressive rollout | **Yes** — see the warning below. Never blanket-set `"0"` |
| `COORDINATOR_PROBE_CANARY` | `"1"` | Gives the http override-channel canary a presence guarantee on **every** entry point, so an empty canary header means a veto and nothing else | No — all machines |
| `CLAUDE_HOME` | *(not in settings.json)* | Override the **home directory** the `.claude` root hangs off — resolvers join it with `.claude` themselves, so it is a `$HOME` override, not a path to `.claude` | Yes — every resolver in this tree honors it. Default: `$HOME`, giving `$HOME/.claude` |

**These values are checked, not trusted.** `bin/check-settings-env.py` asserts this table's values
against the live `settings.json` — key *presence* is not the check, because a key at the wrong value
gates a tool out of every session on the box while reading as configured. It grades the **effective**
value across both files: `settings.local.json` is Local scope and outranks `settings.json`, so a var
set in both is decided by the local file, and a wrong value inherited from there is reported against
that file rather than repaired in the user one. It runs at
`coordinator:install` (with `--apply`) and is safe to run at a cadence: report-only by default,
zero-spawn, and it never auto-writes a machine-specific row. Adding a `CLAUDE_CODE_*` row here
without adding it to that script's `_SPEC` fails `tests/test_settings_env_manifest_parity.py`, in
both directions.

> **`CLAUDE_CODE_USE_POWERSHELL_TOOL` is machine-specific and `"0"` is not a safe default.** This
> row previously prescribed `"0"` everywhere as a flash suppressant, described as safe on all
> hosts. On a Windows host whose operator works under a standing no-Bash-tool directive, `"0"` can
> remove the *only* command-issuing tool — an outage, not a cosmetic setting. Do not restore a
> blanket value here. → `docs/decisions/DR-143-...md` (supersedes DR-113 clause 1 on exactly this).
>
> It is a **native Claude Code variable**, not a coordinator one — nothing in this repo or
> the engine repo reads it; the harness does, from `settings.json`. That is why it lives here and
> not in the machine-local registry: a value the harness reads has to be where the harness looks.
> The rollout is progressive on Windows-with-Git-Bash, so an *unset* value is nondeterministic
> across Claude Code updates — pinning is about removing that silent flip, not about picking a side.
>
> **Do not reach for per-hook `"shell": "powershell"` as a spawn-cost win — it is measured slower.**
> The mechanism is real (a hook spawns its shell directly, so the override works regardless of this
> variable), and that is exactly what makes it a tempting wrong turn. `docs/research/2026-07-14-windows-first-class-coordinator/00-EMPIRICAL-spawn-benchmark.md`
> measures `pwsh -NoProfile` cold-start at **231.8ms** median against `bash -c :` at **17.6ms** —
> pwsh costs ~13× more to start before it spawns anything. Current worst case (`bash → python`,
> MSYS-mediated) measures 261.9ms; the pwsh equivalent lands ~265ms. A wash.
> `SYNTHESIS-strategy.md` § 5 already carries this as non-goal #1: *"Do not rewrite hooks in
> PowerShell — measured slower than what exists."*
>
> Note which document wins and why: `06-claude-code-windows-optimization.md` recommends the swap on
> correct mechanism (no MSYS fork-tax under pwsh) but never weighed pwsh's own interpreter
> cold-start. `00-EMPIRICAL-*` is the later measurement and supersedes it. A mechanism argument
> that never met a stopwatch is not evidence.

> **`COORDINATOR_PROBE_CANARY` belongs to the hook registration, not to a launcher.** The http
> override channel carries two discriminators: a static `X-Coordinator-Env-Channel` literal that
> survives an `httpHookAllowedEnvVars` veto, and an interpolated `X-Coordinator-Env-Canary` that a
> veto empties. The pair only separates *vetoed* from *undeclared* while the canary variable is
> actually set — an allowlisted canary nothing exports interpolates empty on every fire and reads,
> from inside the forwarder, as a permanent veto. That is not a degradation: it denies the Bash
> tool for the whole life of the session, citing a setting the box does not have, and every
> documented recovery runs through the tool it just took away.
>
> The launchers (`claude-doe.py`, `claude-doe-launcher.{cmd,ps1}.tmpl`) each `setdefault` it, which
> covers a launcher-started session on any OS and covers nothing else. A bare `claude` — a
> container, a CI runner, an OSS install, Claude Code on the web — has no launcher at all. Setting
> it here gives the canary the same lifecycle as the `hooks.json` registration that depends on it,
> on every entry point and every platform. Veto semantics are unchanged: a veto still empties the
> header, because it empties the interpolation and not the variable.

## Adding a New Machine

1. Clone / sync `~/.claude` via git
2. Create `machine-local/registry.local.toml` — populate repo paths for
   repos present on this machine (empty string for absent repos)
3. Run `coordinator:install` — `bin/seed-marketplace-enabledplugins.py` runs
   as an install step (not a SessionStart hook) and:
   - Seeds `enabledPlugins["<plugin>@<marketplace>"] = true` in
     `settings.local.json` for each present marketplace sibling
   - Writes matching `extraKnownMarketplaces` entries in `settings.local.json`
     and entries in `known_marketplaces.json`
4. Restart Claude Code (env vars + plugin enablements read at boot)

## Device-Singular vs. OSS-Canonical Discriminator

<!-- spec-backlink: coordinator/docs/wiki/depersonalize-doctrine.md §Discriminator -->
<!-- canonical on-device store; see depersonalize-doctrine.md §Discriminator -->

**`~/.coordinator-claude-settings` is the canonical on-device store** for anything stored on a device in a singular space. Device-singular values are set on-device via the machine-local registry (`registry.local.toml`), never hardcoded in committed source.

### The Discriminator

Two classes of coordinator configuration have superficially similar shapes but fundamentally different ownership:

| Class | Examples | Where it belongs | Why |
|---|---|---|---|
| **Device-singular operator identity** — values unique to one operator/device | The meta-repo slug (`cockpit.meta_repo_slug`) | `registry.local.toml` (operator-set, gitignored) | These values differ per operator/device; hardcoding them in committed source would personalize what must be a portable, impersonal artifact. Unset → fail loud with remediation. |
| **OSS-canonical project constants** — values identical for every operator | The canonical OSS publish destination `dbc-oduffy/coordinator-claude`, `COORDINATOR_PUBLISH_OWNER` | Committed source | These are project constants, not device-singular. Every operator running the coordinator gets the same value. Moving them to `registry.local.toml` would break publish for fresh-install operators who haven't set the key. |

**Cross-reference:** `coordinator/docs/wiki/depersonalize-doctrine.md §Discriminator` for the load-bearing-vocabulary-vs-operator-identity distinction. The OSS-canonical vs. device-singular split is the same discriminator; the terminology maps 1:1.

### Cockpit Registry Keys

A `registry.local.toml` key governs cockpit emission. It is operator-set; unset ⇒ cockpit emit fails loud with a remediation pointing at this section.

| Key | Purpose | Consumer | Provision |
|---|---|---|---|
| `cockpit.meta_repo_slug` | The operator meta-repo `owner/repo` slug (e.g. `"myowner/my-meta-repo"`). Feeds `COCKPIT_META_REPO_SLUG`. | the engine repo's `coordinator/bin/emit-cockpit-snapshot.py`, cockpit emit-path | `machine-local set cockpit.meta_repo_slug "owner/slug"` |

**Why these are device-singular.** The operator's GitHub org membership and their choice of meta-repo slug are properties of the operator's identity on their device — they cannot be committed to the coordinator's OSS source without personalizing that source. Every operator running the coordinator will have different values; the registry is the correct store (§ Device-Singular vs. OSS-Canonical Discriminator, §4e of `machine-local-registry.md`).

**Cold-safe resolver contract.** Both keys are resolved through the emit-path cold-safe resolver: if the key is unset (missing from `registry.local.toml`), the resolver exits non-zero with a remediation message that names the `machine-local set` command to run. There is no silent fallback — cockpit emission requires the operator's identity.

## Adding a New Gated Plugin

Two distinct mechanisms cover a new marketplace-sibling plugin — don't
conflate them.

**Marketplace-sibling enablement + registration is automatic — no manual
step needed.** `bin/seed-marketplace-enabledplugins.py` derives the plugin's
`<plugin>@<marketplace>` key(s) from the sibling's own
`.claude-plugin/marketplace.json` manifest and seeds it (`true`) into
`settings.local.json`, plus the marketplace's `extraKnownMarketplaces` /
`known_marketplaces.json` registration (§ Marketplace Registration above), at
`coordinator:install` time — for any marketplace sibling checked out on this
machine. No coordinator self-entry is ever seeded, and nothing is written to
the committed `settings.json`.

**When a plugin ALSO depends on machine-specific infrastructure** (beyond
being present/absent — e.g. a registry-key-gated external dependency),
gating is currently a documented convention only (§ Plugin Infrastructure
Requirements above — no automated enable/disable exists since
`platform-localize.sh` was de-wired 2026-07-15):

1. Add a key declaration (empty string) to `machine-local/registry.toml` (tracked). Per-machine values go in `registry.local.toml` via `machine-local set <key> <path>`
2. Add a row to this manifest's Infrastructure Requirements table
3. On machines that have the infrastructure: `machine-local set <key> <path>`
4. On machines that don't: leave the key empty and, until an automated gate ships, disable the plugin by hand in `settings.local.json`
