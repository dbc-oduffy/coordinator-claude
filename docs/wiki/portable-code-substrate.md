# Portable Code Substrate

<!-- spec-backlink: archive/specs/2026-05/2026-05-20-portable-code-substrate.md -->
<!-- spec-backlink: archive/specs/2026-05/2026-05-20-eager-agent-calibration.md §5 -->

> See also: substrate-pin-doctrine.md, machine-local-registry.md

**Purpose.** Doctrine and API reference for the three ergonomic helpers that make registry-correct code *shorter* than hardcoded paths. The correctness argument lives in `machine-local-registry.md`; this guide covers the *shape* of the helpers, the shim-import pattern, and what was deliberately left out-of-scope and why.

The substrate problem: even after the machine-local registry ships, an executor writing Python that needs a sibling-repo path reaches for a hardcoded string (19 chars) rather than the registry-correct shape (~90 chars of shell-out). When the wrong path is cheaper to type, agents take the wrong path. The portable-code substrate makes the correct shape the shorter one.

## The Three Helpers

### 1. Python — `claude_machine_local.py` (`~/.claude/bin/`)

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
sys.path.insert(0, os.path.expanduser("~/.claude/bin"))
from claude_machine_local import repos
```

This is the canonical pattern for scripts that cannot assume `~/.claude/bin` is on `PYTHONPATH`. Document it in the module docstring AND in any dispatch prompt that instructs an executor to use the helper.

**Non-negotiable:** `claude_machine_local.py` shells out to `machine-local` via subprocess. It NEVER imports `_machine_local.py` directly — doing so creates the dual-identity failure mode (two module copies with separate state in `sys.modules`). See `docs/wiki/dual-identity-module-hazard.md` and `machine-local-registry.md §8(a)`.

### 2. Shell — `claude-machine-local.sh` (`~/.claude/bin/`)

```bash
source ~/.claude/bin/claude-machine-local.sh
echo "$REPO_PROJECT_RAG/subdir/file.py"
```

**Contract:**
- Source once per session; idempotent (guarded by `CLAUDE_MACHINE_LOCAL_SOURCED`).
- Exports `$REPO_<NAME>` for every declared `repos.*` key.
- Key transformation: `repos.project_rag` → `REPO_PROJECT_RAG` (dots and hyphens → underscores, lowercase → uppercase).
- Keys whose transformed name fails POSIX validation (`^[A-Z_][A-Z0-9_]*$`) are skipped with a stderr warning.
- Restricted to `repos.*` namespace only — concern namespaces with version-multiplexed keys don't map cleanly to flat env vars.

**Naming convention note:** The prefix is singular `REPO_`, not `REPOS_`. This is the shipped convention.

### 3. PowerShell — `claude-machine-local.ps1` (`~/.claude/bin/`)

```powershell
. ~/.claude/bin/claude-machine-local.ps1
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

Production traffic is unaffected (env var arrives unset from outside); the failure mode is invisible until a test sandbox / CI runner pre-sets the var and every nested script silently corrupts it. Any script that resolves AND re-exports a path env var inherits the same hazard — gate the resolve call, don't unconditionally overwrite. (case: example-game-repo 2026-06-09)

## Harness-Injected `plugins/*/bin` Is the Cross-Shell PATH-Substrate

**The real cross-platform PATH guarantee is the Claude Code harness**: it injects each installed plugin's own `bin/` directory (`plugins/<plugin>/bin/`) onto PATH for every tool invocation and hook shell — on Windows, macOS, and Linux alike. This is the substrate a plugin can rely on unconditionally.

**`~/.claude/bin/` is on PATH only on Windows** (the installer writes it via `install-substrate.sh` Step 3b). It is NOT harness-injected on macOS or Linux. Callers using the absolute path `~/.claude/bin/<tool>` work everywhere (the path resolves correctly on POSIX); bare-name invocation of a `~/.claude/bin/` shim from a hook or tool shell fails on macOS/Linux because that directory is not on PATH in those environments.

**Consequence for plugin CLI shims:** a plugin needing bare-name cross-shell reach on POSIX MUST ship its shim (or a thin exec-forwarder) in its **own** `plugins/<plugin>/bin/` directory — not in `~/.claude/bin/`. The harness injects `plugins/<plugin>/bin/` unconditionally; `~/.claude/bin/` is Windows-installer-only.

`~/.claude/bin/` retains two valid roles:
- **Absolute-path callers** — health-check probes that call `~/.claude/bin/machine-local …` explicitly are always correct.
- **Persistence across reinstalls** — the directory is stable user-space; installer-authored files there survive plugin upgrades.

Coordinator's own forwarders in `coordinator/bin/` exemplify the correct pattern: the bare-name shims live in `plugins/coordinator/bin/` (harness-injected), where they forward to the implementations in `~/.claude/bin/` (absolute-path callers only). See `docs/plans/2026-06-18-machine-local-bare-invocation-macos.md` for the worked example.

Empirically: `%APPDATA%\npm` is NOT on PATH for Git Bash or PowerShell on Windows (only cmd.exe via the standard Node installer); `/usr/local/bin` doesn't exist on Windows shells; `npm link` ships a file that satisfies `ls` but fails `which` for the agent's actual shell. The harness-injected plugin bin is the only directory guaranteed for bare-name invocation on all platforms.

**Tenancy contract** for any plugin shipping into its own `plugins/<plugin>/bin/`:
- Namespaced by binary name (e.g. `example-game-repo-control{,.cmd}`) — no collisions across plugins.
- Uninstall removes those exact files — no orphan shims.
- Drift reporting surfaces via the plugin's own doctor probe — not the coordinator's.
- Producer is a ~30-line phase function in the plugin's install path.

<!-- review: code-reviewer slice2-F4 — adds supersession statement per finding -->
This supersedes the prior `~/.claude/bin/`-based tenancy contract (corrected 2026-06-18: `~/.claude/bin/` is Windows-installer-only, not a POSIX PATH guarantee).

The contract is a one-paragraph wiki addition for the consuming plugin; the producer is the install-phase function. Cross-repo doctrine — applies to every plugin authoring a cross-shell CLI shim. (case: example-game-repo 2026-06-09)

<!-- DoE resolved: 2026-06-15 — tenancy contract memo `cross-repo/inbox/2026-06-09-example-game-repo-bin-tenancy-contract.md` actioned 2026-06-09 (status: actioned, fyi-nil); namespaced `example-game-repo-control{,.cmd}`, no coordinator-side conflicts. -->
<!-- Doctrine corrected: 2026-06-18 — harness injects plugins/*/bin/ (cross-platform); ~/.claude/bin/ is Windows-installer-only, not POSIX-PATH. See docs/plans/2026-06-18-machine-local-bare-invocation-macos.md. -->

## Invoke workspace tooling from its package dir — `npx <tool>` from the wrong cwd resolves a decoy

`npx <tool>` run from a directory **without** a local `node_modules`/lockfile does not fail — it silently reaches up the resolution chain to a globally-installed, transiently-cached, or (worst case) an unrelated registry package of the same name, then exits 0. The success is false: the tool that ran is not the workspace's pinned version, or is not the intended package at all (a same-name **decoy**). The exit-0 reads as "worked," so the discrepancy surfaces later as mysterious behavior, not an error.

**Rule:** invoke workspace-scoped tooling from the package directory that owns its lockfile (`cd <pkg> && npx …`, or `npm --prefix <pkg> exec …`, or an absolute path into `<pkg>/node_modules/.bin/`). A bare `npx <tool>` from the repo root or a sibling dir is a footgun whenever the tool is workspace-local. Treat exit-0 from `npx` in a `node_modules`-less cwd as unproven, not confirmed.

**Reporting corollary — reproduce a surprising discrepancy with a controlled probe before reporting it to the PM.** When a tool's output is surprising (a version mismatch, a missing feature, a package that "should" be present behaving wrongly), the first hypothesis is your own invocation context (wrong cwd, decoy resolution, stale cache) — not a real defect. Re-run from the correct package dir / with an absolute path before escalating; a false "X is broken" report sends the PM chasing a bug that is actually a cwd mistake. (Pairs with `docs/wiki/tool-output-flakiness-protocol.md` § don't-infer-from-one-read.) Source: 2026-06-21 (example-game-repo).

## Template Mirrors

All three helpers live at two locations:
- Live install: `~/.claude/bin/{claude_machine_local.py,claude-machine-local.sh,claude-machine-local.ps1}`
- Template mirrors: `coordinator/templates/bin/` (byte-identical)

`verify-templates-bin-sync.sh` diffs live vs. template and should be clean before percolation. Any change to the helpers ships to both locations.

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
| Doctor auto-population of `repos.*` | 3-line manual edit per machine dominated in cost by `coordinator_whoami` operator-identity capture | ≥1 OSS operator reports first-run friction |
| Cross-OS CI gate | Same measurement-validity constraint as hook | Substrate shipped + demos landed + ≥3 portability bugs surfaced post-substrate |

**Do not re-propose these without first checking whether the pickup signal has fired.** They were not deferred for lack of appetite; they were deferred because the measurement surface didn't exist yet.

## Oracle-7 Out-of-Scope Taxonomy

The following hardcoded-path patterns are *not* `repos.*` problems and were explicitly excluded from the portable-code-substrate plan:

| Item | Why OOS | Correct fix |
|---|---|---|
| Hardcoded branch name in `run-phase5-rebisect-inline.ps1` | Branch-name bug, not path bug | `$env:BISECT_BASE_BRANCH ?? "main"` |
| `api_registry_names.json` UE 5.7 install path | Runtime-data file | Resolve via `whoami`-discovered UE root |
| `build-plugin.yml` hardcoded MSVC | GitHub Actions config | Parameterize via workflow input |
| `server.json` placeholder `C:/Users/YourName` | Template placeholder | Substitute at install time or move to `.example` |
| `integration.yml` sibling-checkout | CI workflow | Configurable checkout step or cross-OS CI matrix |

The discriminator: if the wrong thing is a path to a *sibling repo root*, machine-local is the fix. If it is a configuration value, branch name, build parameter, or template placeholder — that is a different problem category.

## Related Wikis

- `machine-local-registry.md` — the schema, resolution order, and authority doctrine; this guide covers only the ergonomic helpers.
- `eager-agent-calibration.md` — design-as-offers doctrine and the full preamble content.
- `dual-identity-module-hazard.md` — why the Python helper shells out rather than importing directly.
