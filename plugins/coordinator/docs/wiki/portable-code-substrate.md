# Portable Code Substrate

<!-- spec-backlink: docs/plans/2026-05-20-portable-code-substrate.md -->
<!-- spec-backlink: docs/plans/2026-05-20-eager-agent-calibration.md §5 -->

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

**Non-negotiable:** `claude_machine_local.py` shells out to `bin/machine-local` via subprocess. It NEVER imports `_machine_local.py` directly — doing so creates the dual-identity failure mode (two module copies with separate state in `sys.modules`). See `docs/wiki/dual-identity-module-hazard.md` and `machine-local-registry.md §8(a)`.

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

## Template Mirrors

All three helpers live at two locations:
- Live install: `~/.claude/bin/{claude_machine_local.py,claude-machine-local.sh,claude-machine-local.ps1}`
- Template mirrors: `coordinator/templates/bin/` (byte-identical)

`bin/verify-templates-bin-sync.sh` diffs live vs. template and should be clean before percolation. Any change to the helpers ships to both locations.

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
