# Portable Code Substrate

<!-- spec-backlink: archive/specs/2026-05/2026-05-20-portable-code-substrate.md -->
<!-- spec-backlink: archive/specs/2026-05/2026-05-20-eager-agent-calibration.md §5 -->

> See also: substrate-pin-doctrine.md, machine-local-registry.md

**Purpose.** Doctrine and API reference for the three ergonomic helpers that make registry-correct code *shorter* than hardcoded paths. The correctness argument lives in `machine-local-registry.md`; this guide covers the *shape* of the helpers, the shim-import pattern, and what was deliberately left out-of-scope and why.

The substrate problem: even after the machine-local registry ships, an executor writing Python that needs a sibling-repo path reaches for a hardcoded string (19 chars) rather than the registry-correct shape (~90 chars of shell-out). When the wrong path is cheaper to type, agents take the wrong path. The portable-code substrate makes the correct shape the shorter one.

## The Three Helpers

### 1. Python — `claude_machine_local.py` (`<settings-home>/bin/`)

```python
from claude_machine_local import repos

# Resolve a sibling-repo root as a pathlib.Path
config = repos.project_rag / "subdir/file.toml"
```

**API contract:**
- `repos.<key>` resolves `repos.<key>` from the registry and returns a `pathlib.Path`.
- Missing key raises `AttributeError` (not `KeyError`) — Python protocol; `hasattr`/`getattr(default)` work correctly.
- Dunder/underscore-prefixed names are guarded — `repos.__foo__` never resolves a registry key.
- Process-local memoization: first call triggers a subprocess; subsequent calls return the cached `Path`. Exceptions are never cached — a missing/broken reader on first call remains retryable.

**Shim-import pattern** (for scripts without `sys.path` control):

```python
import sys, os
settings_home = os.environ.get(
    "COORDINATOR_SETTINGS_HOME",
    os.path.join(os.environ.get("CLAUDE_HOME", os.path.expanduser("~")), ".coordinator-claude-settings"),
)
sys.path.insert(0, os.path.join(settings_home, "bin"))
from claude_machine_local import repos
```

This is the canonical pattern for scripts that cannot assume `<settings-home>/bin` is on `PYTHONPATH`. `<settings-home>` resolves per the ladder `${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}` — see `machine-local-registry.md § 4e` for the full resolution-order doctrine; this doc doesn't restate it. Document the shim-import pattern in the module docstring AND in any dispatch prompt that instructs an executor to use the helper.

**Non-negotiable:** `claude_machine_local.py` shells out to `machine-local` via subprocess. It NEVER imports `_machine_local.py` directly — doing so creates the dual-identity failure mode (two module copies with separate state in `sys.modules`). See `docs/wiki/dual-identity-module-hazard.md` and `machine-local-registry.md §8(a)`.

### 2. Shell (POSIX hosts) — `claude-machine-local.sh` (`<settings-home>/bin/`)

`<settings-home>` resolves via `COORDINATOR_SETTINGS_HOME`, else `CLAUDE_HOME`-or-`HOME`-rooted `.coordinator-claude-settings` (the same ladder as Helper 1); PowerShell hosts use Helper 3 below instead.

```bash
source "<settings-home>/bin/claude-machine-local.sh"
echo "$REPO_PROJECT_RAG/subdir/file.py"
```

**Contract:**
- Source once per session; idempotent (guarded by `CLAUDE_MACHINE_LOCAL_SOURCED`).
- Exports `$REPO_<NAME>` for every declared `repos.*` key.
- Key transformation: `repos.project_rag` → `REPO_PROJECT_RAG` (dots and hyphens → underscores, lowercase → uppercase).
- Keys whose transformed name fails POSIX validation (`^[A-Z_][A-Z0-9_]*$`) are skipped with a stderr warning.
- Restricted to `repos.*` namespace only — concern namespaces with version-multiplexed keys don't map cleanly to flat env vars.

**Naming convention note:** The prefix is singular `REPO_`, not `REPOS_`. This is the shipped convention.

### 3. PowerShell — `claude-machine-local.ps1` (`<settings-home>/bin/`)

```powershell
$SettingsHome = if ($env:COORDINATOR_SETTINGS_HOME) { $env:COORDINATOR_SETTINGS_HOME } elseif ($env:CLAUDE_HOME) { Join-Path $env:CLAUDE_HOME ".coordinator-claude-settings" } else { Join-Path $HOME ".coordinator-claude-settings" }
. (Join-Path $SettingsHome "bin/claude-machine-local.ps1")
"$($env:REPO_PROJECT_RAG)/subdir/file.py"
```

Same contract as the shell helper; `$IsWindows` detection handles reader path differences between `machine-local.cmd` (Windows) and the bash wrapper (Linux/macOS/WSL).

## Env-Var Resolver Re-Entry Discipline

**Production env-var resolvers MUST gate re-resolution on `[[ -z "${VAR:-}" ]]`** — accept upstream values unchanged. The resolver's job is "produce canonical path"; re-running it on an already-canonical path is doctrinally a no-op, but implementations that unconditionally re-derive (e.g. by appending `.claude`) double-resolve into `.../.claude/.claude` when a child process inherits the already-resolved value from a parent that also called the resolver.

```bash
# Right — re-entrant
: "${CLAUDE_HOME:=$(claude-home dir)}"

# Wrong — double-resolves under child-process inheritance
CLAUDE_HOME=$(claude-home dir)
export CLAUDE_HOME
```

Production traffic is unaffected (env var arrives unset from outside); the failure mode is invisible until a test sandbox / CI runner pre-sets the var and every nested script silently corrupts it. Any script that resolves AND re-exports a path env var inherits the same hazard — gate the resolve call, don't unconditionally overwrite. (case: example-game-repo)

## Harness-Injected `plugins/*/bin` Is the Cross-Shell PATH-Substrate

**The real cross-platform PATH guarantee is the Claude Code harness**: it injects each installed plugin's own `bin/` directory (`plugins/<plugin>/bin/`) onto PATH for every tool invocation and hook shell — on Windows, macOS, and Linux alike. This is the substrate a plugin can rely on unconditionally.

**`~/.claude/bin/` is PATH-registered on no platform.** The installer registers `<settings-home>/bin` (`bin_dst`) on the Windows user PATH (`install-substrate.py`'s `_windows_health_steps`); `compat_bin_dst` occurs zero times in that PATH-registration path, and there is no POSIX-side registration either. It is NOT harness-injected on any platform. Bare-name invocation of a `~/.claude/bin/` shim from a hook or tool shell fails everywhere, not only on macOS/Linux, because that directory is on PATH nowhere.

**Consequence for plugin CLI shims:** a plugin needing bare-name cross-shell reach MUST ship its shim (or a thin exec-forwarder) in its **own** `plugins/<plugin>/bin/` directory — not in `~/.claude/bin/`. The harness injects `plugins/<plugin>/bin/` unconditionally; `~/.claude/bin/` gets no bare-name reach on any platform.

`~/.claude/bin/` retains two valid roles:
- **Absolute-path callers** — health-check probes that call an installer-authored `~/.claude/bin/<tool>` path explicitly are always correct, for whichever plugin still mints a forwarder there. Coordinator mints none (see below): a probe should not reference `~/.claude/bin/machine-local` — no forwarder exists at that path.
- **Persistence across reinstalls** — the directory is stable user-space; installer-authored files there survive plugin upgrades.

**Coordinator's own `coordinator/bin/` is not a worked example of this pattern — it tracks zero files** (verify: `git ls-files coordinator/bin | wc -l` → `0`). The harness still injects that directory; it is simply empty, so bare-name resolution for coordinator's own scripts, and for the settings-home CLI family (`~/.coordinator-claude-settings/bin/`, 300+ generated forwarders including `machine-local`/`cross-repo-memo`), is broken on POSIX — that directory is not harness-injected and not on PATH on macOS/Linux. A fix generalizing the installer's login-profile PATH block to also cover settings-home/bin has been requested from claude-klabauter by memo and has not yet landed. Until it lands, invoke the settings-home CLI family per the precedence ladder in `coordinator/snippets/resolve-coordinator-bin.md` — rung 0 / Shape W on a PowerShell host, the explicit `${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/<cli>` path on a POSIX host — this remains correct regardless of the underlying fix's status.

**Distinct from where the resolver family lives.** The PATH-injection claims above are about *bare-name invocability* on POSIX shells — a separate concern from *where the three helpers are installed*. Per DR-072, the `claude_machine_local.py` / `claude-machine-local.sh` / `claude-machine-local.ps1` resolver family's canonical home is `<settings-home>/bin/`, not `~/.claude/bin/`; see `machine-local-registry.md § 4e` for the settings-home ladder. Don't conflate "is this on PATH" with "where does the resolver family live" — a caller with the absolute `<settings-home>/bin/…` path works everywhere regardless of PATH.

**`~/.claude/bin/` PATH-shim tenancy is OUTSIDE DR-072's vacate mandate.** DR-072's mandate is over durable machine-local *state* (root pointers, registries, per-machine installer-seeded values) — the axis is durability, not executability. An installer-authored PATH shim is a regenerable artifact whose absence self-resolves from a re-install, which is precisely the disposable-artifact shape DR-072 permits under `~/.claude` (DR-072 § "Decision rule for authors"). It is therefore **not** a DR-072 finding, and a repo that is reset-safe for durable state while still writing an executable here has no DR-072 hole. This is a fleet-wide exemption — every repo shipping a CLI shim inherits it.

**Coordinator itself declines the exemption for its own forwarders (owns-zero).** The exemption above is a *permission* (a regenerable shim in `~/.claude/bin/` does not *violate* DR-072), not a mandate to keep one. Coordinator mints zero content into `~/.claude/bin/` and resolves nothing through it, consolidating its forwarder set onto the single durable settings-home home (`<settings-home>/bin/`, DR-071/072) — the `~/.claude/bin/` copy would otherwise be a byte-identical redundant mirror of settings-home, and `~/.claude/bin/` is the reset-*fragile* surface. The installer registers **settings-home\bin** (`bin_dst`) on the Windows user PATH (`install-substrate.py` Step 3b / `_windows_health_steps`), **not** `~/.claude/bin/` (`compat_bin_dst` is never PATH-registered) — settings-home is already the Windows bare-name home, so owns-zero relocates nothing there; it only stops minting redundant `.cmd` twins into a non-PATH directory. **Scope: this is coordinator declining a permitted option for its own minted content — NOT a fleet-wide vacate mandate.** The fleet-wide exemption is unchanged; any repo may still ship a regenerable shim there under the ruling above.

**The exemption is narrow, and it is not a licence to ship shims here.** DR-072 silence does not make `~/.claude/bin/` the right home for a plugin CLI shim — the tenancy correction above already governs that, on a separate axis: `~/.claude/bin/` is PATH-registered on no platform, so a shim written there yields **no bare-name reach anywhere**, not merely on macOS or Linux. A plugin shipping `~/.claude/bin/<tool>{,.cmd}` for cross-shell invocability is DR-072-clean and *still* wrong under this file — its POSIX users get a file that satisfies `ls` and fails `which`. Route such shims to `plugins/<plugin>/bin/` per § Consequence for plugin CLI shims.

Empirically: `%APPDATA%\npm` is NOT on PATH for Git Bash or PowerShell on Windows (only cmd.exe via the standard Node installer); `/usr/local/bin` doesn't exist on Windows shells; `npm link` ships a file that satisfies `ls` but fails `which` for the agent's actual shell. The harness-injected plugin bin is the only directory guaranteed for bare-name invocation on all platforms.

**Tenancy contract** for any plugin shipping into its own `plugins/<plugin>/bin/`:
- Namespaced by binary name (e.g. `example-game-repo-control{,.cmd}`) — no collisions across plugins.
- Uninstall removes those exact files — no orphan shims.
- Drift reporting surfaces via the plugin's own doctor probe — not the coordinator's.
- Producer is a ~30-line phase function in the plugin's install path.

`~/.claude/bin/` is PATH-registered on no platform — the tenancy contract above governs bare-name reach instead.

The contract is a one-paragraph wiki addition for the consuming plugin; the producer is the install-phase function. Cross-repo doctrine — applies to every plugin authoring a cross-shell CLI shim. (case: example-game-repo)

<!-- DoE resolved: 2026-06-15 — tenancy contract memo `cross-repo/inbox/2026-06-09-example-game-repo-bin-tenancy-contract.md` actioned 2026-06-09 (status: actioned, fyi-nil); namespaced `example-game-repo-control{,.cmd}`, no coordinator-side conflicts. -->
<!-- Harness injects plugins/*/bin/ (cross-platform); ~/.claude/bin/ is PATH-registered on no platform. See docs/plans/2026-06-18-machine-local-bare-invocation-macos.md. -->

## Invoke workspace tooling from its package dir — `npx <tool>` from the wrong cwd resolves a decoy

`npx <tool>` run from a directory **without** a local `node_modules`/lockfile does not fail — it silently reaches up the resolution chain to a globally-installed, transiently-cached, or (worst case) an unrelated registry package of the same name, then exits 0. The success is false: the tool that ran is not the workspace's pinned version, or is not the intended package at all (a same-name **decoy**). The exit-0 reads as "worked," so the discrepancy surfaces later as mysterious behavior, not an error.

**Rule:** invoke workspace-scoped tooling from the package directory that owns its lockfile (`cd <pkg> && npx …`, or `npm --prefix <pkg> exec …`, or an absolute path into `<pkg>/node_modules/.bin/`). A bare `npx <tool>` from the repo root or a sibling dir is a footgun whenever the tool is workspace-local. Treat exit-0 from `npx` in a `node_modules`-less cwd as unproven, not confirmed.

**Reporting corollary — reproduce a surprising discrepancy with a controlled probe before reporting it to the PM.** When a tool's output is surprising (a version mismatch, a missing feature, a package that "should" be present behaving wrongly), the first hypothesis is your own invocation context (wrong cwd, decoy resolution, stale cache) — not a real defect. Re-run from the correct package dir / with an absolute path before escalating; a false "X is broken" report sends the PM chasing a bug that is actually a cwd mistake. (Pairs with `docs/wiki/tool-output-flakiness-protocol.md` § don't-infer-from-one-read.) Source: example-game-repo.

## Template Mirrors

Canonical live install per DR-072 is `<settings-home>/bin/{claude_machine_local.py,claude-machine-local.sh,claude-machine-local.ps1}`. The installer mints these three helpers there only — the prior `~/.claude/bin/` compat mirror (the Step 3c-compat producer and its `compat_bin_dst` mkdir) is retired (Gate 6, `docs/plans/2026-07-24-coordinator-owns-zero-claude-bin.md`); a fresh install mints nothing into `~/.claude/bin/`.

All three helpers live at two locations:
- Live install: `<settings-home>/bin/{claude_machine_local.py,claude-machine-local.sh,claude-machine-local.ps1}`
- Template mirrors: `coordinator/templates/bin/` (byte-identical)

The byte-identity gate between them is engine-subject — `coordinator_core/ops/verify_templates_bin_sync.py`, in `claude-klabauter`, not this repo. It resolves the live side through `<settings-home>/bin/`, with `~/.claude/bin/` retained only as a migration-window fallback taken when the settings-home bin directory doesn't exist as a directory at all. Any change to the helpers ships to both locations.

## The Meta-Ask Preamble — Making Registry-Correct the Easy Path

Executors default to hardcoded paths not because they are lazy, but because the wrong shape is shorter. The intervention class is **redirection** — make the right shape the path of least resistance. Two mechanisms in concert:

1. **Executor meta-ask preamble** (`coordinator/snippets/meta-ask-preamble.md`, synced into `agents/executor.md`). Appears in every executor prompt. Content: "What 'working' means on this stack — working on all machines, not just this one" + registry-correct shape examples for Python, Shell, PowerShell.

2. **This substrate** — the helpers make the correct shape shorter than hardcoded strings once the operator knows they exist.

The preamble addresses the discoverability problem; the substrate addresses the ergonomics problem. Both are required; either alone is insufficient.

**Design-as-offers principle.** The preamble leads with the better alternative ("did you mean `repos.project_rag`?"), not the violation. Offer-shape — assume willing collaboration; mistrust-shape (warn/block/nag without alternative) fights eagerness rather than redirecting it. See `docs/wiki/eager-agent-calibration.md`.

## Out-of-Scope Items — Explicit Deferrals with Pickup Signals

The following were evaluated and deliberately excluded from the initial substrate ship. Each carries an explicit pickup signal:

| Item | Why deferred | Pickup signal |
|---|---|---|
| PostToolUse hook detecting hardcoded paths | Evidence asymmetry: hook value only measurable after substrate-alone effectiveness observed; shipping both confounds the measurement | ≥3 new authored offenders over 30-day window post-substrate |
| Sweep CLI (portability audit on demand) | No concrete consumer surface yet | A ceremony (e.g. `/workweek-complete`) wants a portability summary |
| Doctor auto-population of `repos.*` | 3-line manual edit per machine dominated in cost by operator-identity capture (formerly `coordinator_whoami`'s job; retired, `archive/specs/2026-08-23-retire-coordinator-whoami-entirely.md`) | ≥1 OSS operator reports first-run friction |
| Cross-OS CI gate | Same measurement-validity constraint as hook | Substrate shipped + demos landed + ≥3 portability bugs surfaced post-substrate |

**Do not re-propose these without first checking whether the pickup signal has fired.** They were not deferred for lack of appetite; they were deferred because the measurement surface didn't exist yet.

## Oracle-7 Out-of-Scope Taxonomy

The following hardcoded-path patterns are *not* `repos.*` problems and were explicitly excluded from the portable-code-substrate plan:

| Item | Why OOS | Correct fix |
|---|---|---|
| Hardcoded branch name in `run-phase5-rebisect-inline.ps1` | Branch-name bug, not path bug | `$env:BISECT_BASE_BRANCH ?? "main"` |
| `api_registry_names.json` UE 5.7 install path | Runtime-data file | Resolve via `whoami`-discovered UE root |
| `build-plugin.yml` hardcoded MSVC | GitHub Actions config | Parameterize via workflow input |
| `server.json` placeholder `C:/Users/YourName` | Template placeholder | Substitute at install time or move to `.example` <!-- foreign-path-ok: template placeholder text, not an asserted location --> |
| `integration.yml` sibling-checkout | CI workflow | Configurable checkout step or cross-OS CI matrix |

The discriminator: if the wrong thing is a path to a *sibling repo root*, machine-local is the fix. If it is a configuration value, branch name, build parameter, or template placeholder — that is a different problem category.

## Durable-path literals are the smell; the resolution seam is the fix — introduce it early

A **durable location** — config home, identity dir, install-chain contract path — written as a
frozen absolute literal (`~/.claude/...`) at every read/write site is the smell; the eventual
relocation is the interest payment. Because the literal is copied to N sites, any future move
becomes an N-site migration **plus** a fleet-wide contract change **plus** a consumer round-trip,
instead of a one-line change to a single seam's return value. Merely swapping literal A for
literal B during a relocation re-arms the trap for the next move.

This is distinct from the `repos.*` sibling-repo problem above (that resolves *peer-repo roots*);
durable-location literals resolve *this install's own config/identity/contract homes*. Fix the
**class**, not the instance:

1. **Code** resolves durable locations through ONE seam — a helper, or a cold-safe inline env
   expression like `${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}`
   on a POSIX host (rung 0 / Shape W in `coordinator/snippets/resolve-coordinator-bin.md` on a
   PowerShell host) — never a frozen absolute literal duplicated per site.
2. **Docs / contracts** describe the RESOLUTION RULE, not a frozen path. A contract that mandates
   a specific literal is itself a migration site — and one a reads-only census cannot even see
   (the claude-klabauter visited-set gap was exactly a contract-mandated literal invisible to the audit).
3. **A lint/guard** treats a NEW hardcoded durable-path literal as the defect and **offers** the
   seam (design-as-offers — see § The Meta-Ask Preamble above and `eager-agent-calibration.md`,
   not a bare nag).

**Introduce the seam early** — at the first durable read/write site, not at relocation time.
Empirical: the 2026-07-06 durable-substrate-to-settings-home move was an ~18-reader migration +
an agent-install-contract change + a 5-consumer memo round *precisely because* the durable paths
were hardcoded rather than seam-resolved. (case: durable-substrate-to-settings-home)

## Related Wikis

- `machine-local-registry.md` — the schema, resolution order, and authority doctrine; this guide covers only the ergonomic helpers.
- `eager-agent-calibration.md` — design-as-offers doctrine and the full preamble content.
- `dual-identity-module-hazard.md` — why the Python helper shells out rather than importing directly.
