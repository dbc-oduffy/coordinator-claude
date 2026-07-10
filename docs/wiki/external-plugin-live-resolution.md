# External-directory live plugin resolution (Claude Code)

> Durable record of the DoE "maximalist" spike: can the coordinator plugin's **source** live in an
> external repo (DoE-claude) and resolve **live** (in-place editable), letting `~/.claude` become a
> thin pointer? Spinoff `2026-07-04_143347_doe-maximalist-external-plugin-resolution-retry`,
> retrying after W0 FAILed the directory-marketplace path.

## TL;DR

- **Directory-source *marketplace* install → byte-copies plugin content to `~/.claude/plugins/cache/`.**
  Not live. This is the W0 path; do not retry it as the primary mechanism.
- **The maximalist shape is CONFIRMED for skills — via `--plugin-dir`, the official editable-install
  mechanism** (the `pip install -e` equivalent). External source, live in-place, resolved at runtime
  from the external dir. Runtime confirmed 2026-07-04 (fresh boot with `claude --plugin-dir
  ~/X/_doe-spike/doe-spike-plugin`): the `doe-spike-echo` skill loaded with base dir
  `~/X/_doe-spike/...` and **zero cache/registry footprint** — live-external, not byte-copied.
- **BUT plugin-declared hooks do NOT fire under `--plugin-dir`, even on a fresh boot.** The spike's
  SessionStart hook never wrote its log on a clean first-boot relaunch (not the "hooks may need
  restart" caveat — this WAS the restart). This is bug **#38699**: `--plugin-dir` registers skills
  live but does not wire up plugin-declared hooks. This is the real cost line for adopting
  `--plugin-dir` as the coordinator delivery mechanism — coordinator leans heavily on SessionStart /
  PreToolUse hooks.
- **W0's directory-marketplace failure is a known Claude Code bug (#51806):** `claude plugin
  marketplace add` writes `settings.json → extraKnownMarketplaces`, but the running harness reads its
  active registry from `~/.claude/plugins/known_marketplaces.json`. The two are **not synced**. W0
  wrote the wrong store → `Marketplace 'doe-spike' not found`.

## Disk-truth (this machine, ground-truth verified 2026-07-04)

- **Active marketplace registry = `~/.claude/plugins/known_marketplaces.json`** (NOT settings.json).
  `settings.json extraKnownMarketplaces` is a seed/hint surface only (holds just
  `claude-plugins-official` here).
- Registry schema: `git` source → `installLocation` = a clone under
  `~/.claude/plugins/marketplaces/<name>/`; `directory` source → `installLocation` = the source path
  **directly** (coordinator-claude, example-game-workbench-repo, oduffy-custom all point at their source dir).
- `installed_plugins.json` records `coordinator@coordinator-claude` installPath =
  `cache/coordinator-claude/coordinator/3.0.0` — **but that dir does not exist**, while coordinator is
  live this session. The stale cache path is vestigial; coordinator resolves from its directory source.
  (Consistent with the global doctrine that coordinator-claude is `source_is_live` and
  `refresh-plugin-live-install.sh` is a no-op for it. **Pre-cutover snapshot:** `source_is_live` was
  over `~/.claude/plugins/coordinator-claude/`. **Post-cutover (Phase 1, this session):** `source_is_live`
  is over the DoE clone `<DoE>/coordinator/`, resolved live via `--plugin-dir`; registry
  `plugin.mirrors.coordinator-claude` `source_path`/`live_path` both point there — see
  § Adoption — W4.2 cutover below.)

## Documented behavior (3 independent doc scouts, sourced)

| # | Mechanism | Live-external? | Persist across restart? | Notes / sources |
|---|-----------|----------------|--------------------------|-----------------|
| 1 | **Symlink** into `~/.claude/plugins/` | ❌ documented dead end | — | Outside-plugin symlinks are **skipped for security** (plugins-reference). Do not test. |
| 2 | **Directory-source marketplace** | ❌ byte-copies to cache | ✅ | Also has a broken refresh (#72616: cached marketplace.json not re-copied on update). This is the W0 path. |
| 3 | **Git-URL marketplace** at DoE-claude | ❌ byte-copies to cache | ✅ | Moves source-of-record out of `~/.claude` but keeps a publish→push→`marketplace update`→reinstall loop. Per the Director of Engineering F9, relocates the round-trip; does not deliver live in-place edit. |
| 4 | **`--plugin-dir <external-repo>`** | ✅ **official** | ⚠️ per-launch flag | The documented dev/editable install. `CLAUDE_PLUGIN_ROOT` = the external dir. `/reload-plugins` hot-reloads skills/agents/hooks/MCP without restart (skills reliably; hooks may need restart). Local `--plugin-dir` plugin takes precedence over a same-named marketplace plugin. |
| 5 | **`@skills-dir`** (`~/.claude/skills/<name>/`) | ✅ in-place | ✅ auto-loads | Skills-only, discovered in place (not copied); SKILL.md edits immediate. Path must be under `~/.claude/skills/` (local, not an external repo checkout) → doesn't satisfy "source lives in external repo". |
| 6 | **Direct `enabledPlugins` path in settings.json** | ❌ not supported | — | `enabledPlugins` accepts only `name@marketplace`; no arbitrary-directory registration. |

Known harness bugs touching this area: **#51806** (settings/known_marketplaces desync — the W0 root
cause), **#72616 / #61954** (directory-marketplace refresh stale), **#56678** (skills/CLAUDE.md revert
to cached), **#38699** (`CLAUDE_PLUGIN_ROOT` inconsistent between hooks and agent env for local plugins).

## Disposition

- **Symlink (mechanism 1): FAIL** — documented; no runtime test spent.
- **Two-store investigation (mechanism 3 of spinoff): SOLVED** — registry is `known_marketplaces.json`;
  W0 wrote `settings.json`; this is bug #51806. Directory + git-URL marketplaces both byte-copy → do
  not deliver live in-place edit.
- **`--plugin-dir` (NEW candidate, not in original spike): PASS for skills/agents, FAIL for hooks —
  runtime-confirmed 2026-07-04.** This is the officially-supported path to the maximalist shape and
  closes the Director of Engineering F9's self-modification gap for skills/agents (source lives externally, resolved live
  in-place, coordinator can edit its own live-resolving source). **Costs:** (1) launch must always
  pass the flag (wrapper/alias); (2) **plugin-declared hooks do not fire** (#38699) — a coordinator
  delivered purely via `--plugin-dir` would lose its SessionStart/PreToolUse hook surface. Any
  maximalist adoption (W4/W5/W6.4) must solve the hook leg separately (e.g. hooks registered via
  `settings.json` rather than plugin-declared, or a hybrid where hooks stay in `~/.claude`).

## Runtime confirmation test — EXECUTED 2026-07-04 (fresh boot with `--plugin-dir`)

Spike rig was at `~/X/_doe-spike/doe-spike-plugin` (skill `doe-spike-echo` + plugin-declared
SessionStart hook `echo-root.sh` appending to `~/X/_doe-spike/hook-fire.log`). **Rig torn down after
this run** (`rm -rf ~/X/_doe-spike`) — throwaway; verdict captured here.

**Test A (executed):** booted fresh with `claude --plugin-dir ~/X/_doe-spike/doe-spike-plugin`. **Split
result:**
- **Skill leg — PASS.** `doe-spike-echo` loaded; skill base dir resolved to the EXTERNAL path
  `~/X/_doe-spike/doe-spike-plugin/skills/doe-spike-echo`, with **no cache copy** and **no
  registry/settings entry** anywhere. Live-external resolution confirmed.
- **Hook leg — FAIL.** `hook-fire.log` was never created — the plugin-declared SessionStart hook did
  not fire on a clean first boot. `--plugin-dir` registers skills but not plugin-declared hooks
  (#38699). Note: the log-on-disk probe was the wrong signal for a same-boot verdict; the skill's own
  base-dir resolution is the reliable runtime tell.

**Test B (not run):** `known_marketplaces.json` directory-entry persistence angle — superseded. Test A
already gives the live-external answer for the maximalist shape; the persistence question folds into
the W4/W5 adoption decision (launch-flag vs registry), not a separate spike.

## Hook-delivery — SOLVED via settings.json external-abs-path (runtime-proven 2026-07-04)

The `--plugin-dir` FAIL leaves plugin-declared hooks dead (#38699). This is the workaround, and it
is **runtime-proven at boot**, not just same-session:

- **Mechanism: hooks registered in `~/.claude/settings.json` with an EXTERNAL absolute-path command.**
  Not plugin-declared, not env-var-interpolated — a baked absolute path (e.g.
  `bash /Users/example-operator/X/DoE-claude/coordinator/hooks/foo.sh`). Scripts live external in DoE-claude,
  live-editable; they self-resolve their libs via `BASH_SOURCE` first, so `CLAUDE_PLUGIN_ROOT` being
  unset does not matter.
- **Runtime matrix (throwaway probe rig, 4 registrations across settings.json + settings.local.json,
  logged to `fire.log`):**

  | Source | Event | Fires at boot? | Fires mid-session? |
  |--------|-------|----------------|--------------------|
  | `settings.json` | SessionStart | ✅ **yes** (3 post-clear boot lines) | — |
  | `settings.json` | PostToolUse:Bash | — | ✅ yes (every Bash call) |
  | `settings.local.json` | SessionStart | ❌ **never** | — |
  | `settings.local.json` | PostToolUse:Bash | ❌ **never** | — |

- **Key findings:**
  1. **`settings.json` SessionStart external-abs-path hook FIRES at boot** — this is the leg the 14
     coordinator SessionStart hooks ride on. Bypasses the whole #38699/#24529 CPR bug family (CPR was
     `<unset>` in every fire; self-resolution via `BASH_SOURCE` is the correct mechanism).
  2. **`settings.local.json` is NOT a user-level hook-merge source** — zero fires across all boots and
     mid-session. Do not register coordinator hooks there.
  3. **`settings.json` hot-reloads hooks** (mid-session edit takes effect without restart).
- **Adoption shape (still PM-gated, W4/W5/W6.4):** a GENERATOR emits settings.json's hook block from
  coordinator's `hooks/hooks.json`, rewriting `${CLAUDE_PLUGIN_ROOT}` → registry-resolved absolute
  path into DoE-claude; a LAUNCH WRAPPER regenerates-then-`exec claude --plugin-dir` (double duty:
  self-heals settings.json clobber #22659/#28966/#28847, and restores the `--plugin-dir` property).
- **This retires the named blocker** in § Disposition: `--plugin-dir`'s hook FAIL is no longer a
  hard stop — hooks are delivered via settings.json external-abs-path, skills/agents via
  `--plugin-dir`. The two legs compose.

## Anti-scope confirmed

- Directory-source marketplace path is FAILed on live-in-place (byte-copy); not retried as primary.
- Filesystem evidence ≠ runtime truth (W0 lesson) — resolved: the `--plugin-dir` skill-leg PASS is now
  runtime-confirmed (skill base dir external, zero cache). The hook-fire.log probe itself proved a
  weaker signal than the skill's base-dir resolution for a same-boot verdict.
- Maximalist shape (W4/W5/W6.4 in parent plan) is PM-gated — not auto-adopted on the skill-leg PASS,
  and now carries a NAMED blocker: the hook leg (#38699) must be solved before coordinator can be
  delivered purely via `--plugin-dir`.

## Adoption — W4.2 cutover (executed 2026-07-04, additive phase)

> **Superseded rollback mechanism (2026-07-08): use `coordinator/commands/uninstall.md` /
> `coordinator/bin/coordinator-uninstall.sh` instead of hand-running the runbooks below.** The
> runbooks in this section were the only reverse available at cutover time — hand-run, one-machine,
> one-window, and dependent on a dated snapshot tarball that expires. `coordinator-uninstall.sh` is
> the tested, first-class, snapshot-independent replacement: it reconstructs the full reverse (all
> ten out-of-repo surfaces, both a full-remove and a revert-to-marketplace end-state) from first
> principles on any machine, gated by regression tests rather than manual care. The runbooks below
> are retained as the **historical record** of the original Phase 1/Phase 2 cutover mechanics —
> useful for understanding *why* each surface exists, not as an operative rollback procedure. Do not
> hand-run them for a rollback going forward; invoke `coordinator-uninstall.sh` (or
> `/coordinator:uninstall`) instead. See `docs/plans/2026-07-08-coordinator-uninstall.md`.

The maximalist cutover was fired in two phases to keep the live daily-driver reversible until a fresh
boot proves DoE resolution. **Phase 1 (this record) is additive** — the running session's substrate is
never removed; the destructive removal is Phase 2, deferred to the post-relaunch session.

**Boundary decision (PM, 2026-07-04): doctrine → DoE; machine-critical infra stays in `~/.claude`.**
`~/.claude` is the only guaranteed-to-exist repo and Anthropic's write-guards protect it, so
session-identity/machine-state infra is deliberately NOT moved:

| Surface | Home | Rationale |
|---|---|---|
| Live-editable doctrine (`bin/ lib/ hooks/ skills/ agents/ commands/ docs/`) | DoE clone `coordinator/` | The point of maximalist — live in-place edit via `--plugin-dir`. |
| `registry.local.toml` (machine-local state) | `~/.claude/machine-local/` | Inherently per-machine; never moved. |
| `.coordinator-venv` (Python interpreter running whoami) | `~/.claude/.coordinator-venv/` | Registry-pinned (`coordinator.python`); path-sensitive. |
| **whoami package source** (`coordinator_whoami`) | **`~/.claude`** (stays) | Session-identity plumbing, not doctrine; identity must not depend on the DoE clone existing. |

**Phase 1 actions taken (additive, committed on `work/delphipro/2026-07-04`):**
1. Snapshot: `~/.claude-cutover-backup/2026-07-04-w4.2-cutover/{plugins.tar.gz,settings.json}` (rollback net).
2. Relocated git-tracked coordinator source (1482 files, `git archive HEAD:<subdir>` prefix-stripped, +3 untracked bin scripts carried) → `<DoE>/coordinator/`, EXCLUDING `whoami/`. Built artifacts (`.venv`, `node_modules`, `dist`, `__pycache__`) NOT copied — they self-heal at DoE (`ensure-coordinator-venv.sh` for the venv; npm for cockpit-contract).
3. Registry: `plugin.mirrors.coordinator-claude` = `source_is_live`, `source_path`/`live_path` → `<DoE>/coordinator` (no-op drift/refresh semantics, recognized by `check-plugin-drift.sh`/`refresh-plugin-live-install.sh`).
4. `settings.json` hooks regenerated via `gen-settings-hooks.sh` → 32 coordinator hooks now DoE-absolute; 2 harness-native hooks preserved; non-hook keys byte-identical; idempotent.
5. `~/.claude/plugins/coordinator-claude/` tree LEFT IN PLACE (removal is Phase 2). `--plugin-dir` takes precedence over the vestigial marketplace entry, so a relaunched `claude-doe` cleanly resolves from DoE.

**Rollback runbook (Phase 1 — before relaunch, trivial since nothing destructive ran):**
1. `cp ~/.claude-cutover-backup/2026-07-04-w4.2-cutover/settings.json ~/.claude/settings.json` (restore hooks).
2. `rm -rf <DoE>/coordinator` + drop the DoE commit.
3. Remove the registry keys: `machine-local` unset `plugin.mirrors.coordinator-claude.*`.
4. Launch stays bare `claude` (Phase 1 never changed the launch command).

**Full rollback runbook (post-Phase-2, once the `~/.claude` tree is removed):** additionally (1) restore
`~/.claude/plugins/coordinator-claude` from `plugins.tar.gz`; (2) revert the launch command from
`claude-doe` to bare `claude` (remove wrapper alias / PATH shim).

**Phase 2 — remaining, deferred to the post-relaunch session (after DoE resolution is confirmed live):**
1. Relocate whoami source from `~/.claude/plugins/coordinator/whoami` → a stable
   `~/.claude` home (e.g. `~/.claude/coordinator-whoami/`); add registry seam `coordinator.whoami_src`;
   edit `ensure-coordinator-venv.sh` `WHOAMI_PKG` resolution to registry-seam-with-`${plugin_root}/whoami`-fallback
   (preserves OSS-install behavior); re-run to re-point the editable install; verify `import coordinator_whoami`.
2. `git rm` the `~/.claude/plugins/coordinator-claude` tree + remove the marketplace / `enabledPlugins`
   entry → achieves the W4.1s singularity end-state (`~/.claude/plugins/coordinator-claude` absent).
3. Then W5 (percolation DoE→OSS) and W6.4 (placement-law spots) unblock.

**Verification owed (PM relaunch):** boot via `claude-doe`; confirm coordinator skills/agents resolve
from `<DoE>/coordinator` (skill base dir external, zero `~/.claude/plugins/coordinator-claude` in
resolution) and settings.json SessionStart hooks fire at boot from DoE-absolute paths.

## Resolution-altitude model: COLD vs WARM

> **Source:** Design decision ratified PM 2026-07-04 (`docs/plans/2026-07-04-coordinator-maximalist-install-shape.md`
> § Design decisions). One source of truth (the machine-local registry), two read-paths.

Post-cutover, artifacts that need the coordinator root fall into two altitude classes depending on when
and how they run. The split is not two competing mechanisms — the pointer is a **projected cache** of
the registry value; the registry remains the single source of truth.

### COLD-read artifacts

**Context:** a fresh terminal (coordinator `bin/` dirs not yet on PATH), EM-run inline bash inside a
skill/command markdown file, or any surface where `machine-local` is unavailable.

> **Why COLD-read must be zero-tool-dependency (2026-07-04):** a cold terminal (opened outside a
> coordinator session) starts with zero coordinator bins on PATH — Claude Code injects coordinator bin
> dirs onto PATH at plugin-load time, not via shell profile. This creates a chicken-and-egg trap
> post-cutover: the launch shim cannot call `machine-local` to resolve the DoE root, because
> `machine-local` itself now lives inside the DoE clone it would need to locate. This is why the install
> step must project the registry value into a cold-readable bootstrap artifact (the `.doe-root` pointer
> file) rather than relying on any tool-mediated resolution for the first cold read.

**Resolution mechanism:** `cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root"` — zero tool dependency. The
`claude()` shim (`~/.claude/shell/claude-doe-shim.sh`) and the inline fallbacks in the 10
skill/command markdown files use this path. The fail-loud idiom is load-bearing — never use the bare
`${CLAUDE_PLUGIN_ROOT:-$(cat …/.doe-root)/coordinator}` form, which silently expands to the literal
`/coordinator` when the pointer file is absent:

```sh
_doe_root="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)"
if [ -z "$_doe_root" ] || [ ! -d "$_doe_root/coordinator" ]; then
  echo "ERROR: ~/.claude/.doe-root missing/invalid — re-run coordinator:install" >&2
  return 1 2>/dev/null || exit 1
fi
_coordinator_root="${CLAUDE_PLUGIN_ROOT:-${_doe_root}/coordinator}"
```

### WARM-generated / warm-run artifacts

**Context:** git hooks generated at install or session-init time (where `machine-local` is on PATH);
`resolve-coordinator-clone.sh` consumers running inside a coordinator session.

**Resolution mechanism:** read the registry directly via `machine-local get repos.doe_claude`. The
hook generators (`coordinator-ensure-post-commit-hook`, `coordinator-ensure-prepare-commit-msg-hook`,
`gen-settings-hooks.sh`) bake the registry-resolved path into the hook body at generate-time — the
**warm half** of the coherent split. See `8be19f9` ("hooks: installers resolve coordinator bin from
registry — fixes stale-path clobber post-cutover") for the canonical warm-surface implementation.

### The pointer is a projection of the registry — coherence assertion

`gen-doe-root-pointer.sh` writes `~/.claude/.doe-root` = the DoE repo root (projected from
`repos.doe_claude`). The pointer is a **bootstrap cache**, not a second source of truth. It is
(re)generated at install time and self-healed at boot: the SessionStart hook calls
`gen-doe-root-pointer.sh` if the pointer is absent but the registry is set, so a `git pull` without
re-running the installer does not leave migrated inline sites fail-louding on pointer-miss.

**Coherence assertion (verified at install):**
`"$(cat ~/.claude/.doe-root)/coordinator"` == `plugin.mirrors.coordinator-claude.source_path`

## Resolution seam: `resolve-coordinator-clone.sh` pointer tier

`coordinator/lib/resolve-coordinator-clone.sh` is the **sanctioned resolution seam** for the
coordinator root — downstream repos (project-rag, example-game-repo, deep-research) bind it instead of
inlining their own fallback. Its header precedence docblock enumerates every tier in order.

Post-W4.2 the resolver gained a `~/.claude/.doe-root` **pointer tier** (added by
`docs/plans/2026-07-04-coordinator-maximalist-install-shape.md` C3). This tier sits **above** the
flat-layout tier and **below** the registry tier. Critically, the two resolver modes resolve to
**different directories** under maximalist — they were the same directory in the old flat-clone model
and this divergence is now explicit in the resolver's header docblock:

| Mode | Pointer tier resolves to | Gate condition |
|------|--------------------------|----------------|
| `--for-content` | `<doe-root>/coordinator` | `-d <doe-root>/coordinator` |
| `--for-git-ops` | `<doe-root>` (repo root) | `-d <doe-root>/.git` |

`--for-git-ops` returns the repo root, not the `coordinator/` subdir, because `coordinator/.git` is
absent under maximalist — a tier returning `<doe-root>/coordinator` fails the `.git` gate and would
fall through to fail-loud. Both pointer-tier variants read the pointer via `cat` (no `machine-local`
dependency), so they are cold-capable even though they live inside the otherwise-warm resolver.

Effective precedence chain for each mode after W4.2:

```
--for-content:  CLAUDE_PLUGIN_ROOT → COORDINATOR_ROOT → registry live_path → cache
                → .doe-root pointer (→ <root>/coordinator) → flat-layout → fail-loud

--for-git-ops:  COORDINATOR_ROOT → CLAUDE_PLUGIN_ROOT (git-ops-incompatible, gated)
                → registry source_path → cache → .doe-root pointer (→ <root>)
                → flat-layout → fail-loud
```

## Install/uninstall surface symmetry — canonical cross-links

The maximalist install and the coordinator-uninstall spinoff share a surface list that must be kept in
lockstep. If you add an out-of-repo surface to the install, update the uninstall in the same commit.

**Install surface — `coordinator/commands/install.md` (DoE repo):**
Steps 3.5a–3.5c and the Phase 7 status table enumerate every out-of-repo surface the installer
writes: registry keys (`repos.doe_claude`), the `~/.claude/.doe-root` pointer, the owned shim file
(`~/.claude/shell/claude-doe-shim.sh`), the one marked `source` line in the interactive rc,
settings.json hook block, and the DoE clone itself. The installer is the canonical listing of what
exists out-of-repo; the uninstall is its inverse.

**Uninstall surface — `coordinator/commands/uninstall.md` + `coordinator/bin/coordinator-uninstall.sh`:**
<!-- Review: code-reviewer (F1) — repointed from the superseded handoff
     (`state/handoffs/2026-07-04_195849_coordinator-uninstall.md`, status: consumed) now that
     the command/script pair has shipped and is the canonical uninstall surface. -->
The "What gets reversed" surface list reverses the install. Surface #6 (`.doe-root` pointer) and the
reshaped surface #4 (owned shim file + marked rc source line + legacy `~/.bashrc` block) were added
in lockstep by C4 of the maximalist-install plan. The uninstall also strips the legacy
`# --- coordinator maximalist launch ---` `claude()` block from `~/.bashrc` even though the install
only migration-notes it (not silently rewrites it) — the uninstall surface list is a superset on that
point by design. (Originally captured in `state/handoffs/2026-07-04_195849_coordinator-uninstall.md`,
now fully absorbed into the shipped command/script pair — `status: consumed` in that handoff's
frontmatter.)

The install uses `$SHELL`-detection to target the correct interactive rc for the `source` line; the
uninstall uses the same detection to strip it. If you override with `COORDINATOR_SHIM_RC`, the
uninstall must receive the same override to strip the correct file.

## Gotchas — Concurrent-EM hazard: second-copy mis-hook-load

Post-cutover, `~/.claude/plugins/coordinator-claude/` (loaded by a plain `claude` launch) and the DoE
clone (loaded via `--plugin-dir`) are **byte-independent copies**. A fix landed in one is invisible to
a session running the other — there is no shared-state assumption between them once they diverge.

Concretely observed 2026-07-04: a 12-hook `mcp_tool`→command revert landed in the `~/.claude` copy,
but running sessions were loading DoE via `--plugin-dir` (confirmed via `ps -eo` showing the actual
launch args), so the fix appeared to have no effect — the noise it was meant to suppress kept firing
because the *running* session never read the patched copy.

**Diagnostic:** when a fix "doesn't seem to take," don't assume the fix is wrong — first `ps` the
running session to read its actual `--plugin-dir` argument, then check *that* copy for the fix, not
the one you edited.
