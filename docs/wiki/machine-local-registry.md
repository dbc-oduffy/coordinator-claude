# Machine-local Registry

<!-- spec-backlink: archive/specs/2026-05/2026-05-19-machine-local-registry.md § 5 -->

This wiki is the **substrate doctrine** — what belongs in the registry, how the reader resolves values, what does NOT belong. For **operator-facing health verification** of the registry (is my install populated correctly? what to do when probes fail?), see the companion wiki: [`coordinator-doctor.md`](coordinator-doctor.md). Together these wikis form the doctrine-vs-operator-guide pair for the machine-local substrate.

**Purpose.** Durable doctrine for the per-machine registry at `~/.claude/machine-local/`. Covers what belongs there, what does not, how the reader resolves values, anti-patterns, and how this substrate composes with the rest of the coordinator install chain.

## 1. Purpose and Disambiguation

The machine-local registry is **operator-set, machine-specific configuration** — the system administrator's `~/.gitconfig` is the right mental model. The operator sets values once per machine; tooling reads them deterministically. It is not:

- A **Claude Code plugin** (`~/.claude/plugins/` is the plugin directory; the registry lives at `~/.claude/machine-local/` deliberately outside that namespace).
- A **project-rag addon** — the host/addon split governs corpus content and MCP tooling. The registry is orthogonal to that architecture.
- An **MCP server** — nothing in the registry changes at runtime; it is not queried via a running server process. Runtime-queryable state belongs in MCP introspection (see §2).

The scope is: stable per-machine paths and environment roots that any tool, language, or repo needs to find — sibling-repo roots, vendor SDK roots (Unreal install, CUDA toolkit), and other per-machine invariants. The empirical origin is four independent EM teams each inventing the same primitive for inter-repo discovery, none aware of the others; §1 of the design plan documents all four cases.

**What this replaces — the four independent reinventions (plan §1.2):**

| Prior approach | Location | Why it fell short |
|---|---|---|
| `setup/publish-targets.sh` | coordinator meta-repo | Shell-only, single-purpose; unknown to any other tool |
| `~/.project-rag/wiring.env` | project-rag | Shell-sourceable env assignments; `.env` format breaks non-shell consumers; per-project namespace doesn't scale |
| Proposed `addon-resolvers/<addon>.py` | example-game-repo (proposal) | Wrong scope dimension (per-addon, not per-machine); dual-identity hazard |
| Distributed env-var sprawl | example-game-repo | ~9 cross-machine env vars + 5 orthogonal doctor precedence chains |

The registry is the single audited place all of these needed to be. The anti-pattern each represents is still alive; if you see a new `~/.<tool>/config.toml` or a per-repo `TOOL_ROOT=` env var being invented, that is the reinvention detector firing.

## 2. When to Put a Value in Machine-local vs. Discover at Runtime

The discriminator is **stability and source of truth**:

| Value type | Belongs in | Rationale |
|---|---|---|
| Stable per-machine path (sibling repo root, vendor SDK install dir) | `machine-local/registry.local.toml` | Set once by the operator; no live source; persistence is correct. Machine-specific paths go in `.local.toml`, never tracked `registry.toml` — see §8(f)/§9 |
| Runtime state (which corpus is currently bound, daemon PID, active consumer-project path) | Live MCP introspection | Changes with each invocation; a stale file would be a receipt, not an answer |
| Per-project state (project root, project type, skill overrides) | Project `.claude/` config | Varies per project, not per machine |
| Universal constant (same on every machine, not sensitive) | The relevant repo, committed | Git-tracked durability is the right primitive; no operator action needed |
| Sibling-repo path needed by a dispatcher CLI | `machine-local/registry.local.toml` | Cross-repo memo dispatcher resolves receiver paths at runtime; registry is the only cross-machine-stable source (PM-endorsed 2026-05-21) |
| Per-invocation override (CI one-off, test harness path) | `MACHINE_LOCAL_<KEY>` env var | The intentional escape hatch — see §4 resolution order |

Per `docs/wiki/plugin-identity-and-health-sentinels.md`: live = MCP truth (current = answer); persistent = receipt (stale = signal). Machine-local values sit on the "persistent, operator-audited" side. They change when the operator reorganizes their machine, not when a tool runs. If you find yourself wanting to write to machine-local from an MCP server or a script, stop — see anti-patterns §7(b).

## 3. Relationship to `plugin-identity-and-health-sentinels.md`

The two wikis are companion doctrines. `plugin-identity-and-health-sentinels.md` defines what operator-set configuration is and why it sits outside the decay-discipline that governs plugin receipts and MCP introspection. The **2026-05-19 Scope narrowing amendment** to that wiki explicitly names machine-local registry values as operator-set configuration — stable, no live source, persistence is intentional and correct, not a decay signal.

Machine-local is where that wiki's "operator-set configuration" concept lives on disk. If you are deciding whether something belongs in machine-local or in an MCP introspection call, read `plugin-identity-and-health-sentinels.md § Scope` (amended 2026-05-19) for the full decay-discipline framing.

## 4. Resolution Order

> **Doctrine-seed (2026-06-30, from project-rag-em — resolution-behavior SSOT).** The durable
> cross-machine **`repos.*` sibling-repo resolution-behavior** axis — the 4-rung ladder (explicit
> flag/env → tracked OS-keyed search-roots + marker autodiscovery → tracked exceptions table →
> `registry.local.toml` fallback), the identity-marker convention, and the fail-loud seam — is
> specified by project-rag's `docs/wiki/cross-machine-path-resolution-contract.md` (SSOT for that
> axis, per /shape-ratified DoE delegation). The reconciliation has landed (2026-06-30) — §4c and
> §5a now reflect the split. Key-namespace SCHEMA, the reader contract (§7), and the helper surface
> remain coordinator-owned.

The reader (`machine-local get <key>`) resolves in this order, most-specific-and-most-local first:

```
1. <concern>.local.toml (most specific + per-machine)
2. <concern>.toml (most specific shared)
3. registry.local.toml (per-machine)
4. registry.toml (shared baseline)
5. MACHINE_LOCAL_<KEY> env override (intentional one-off escape — NOT highest precedence; env-vars are ambient, registry is deliberate)
6. --default (if provided)
7. exit 1 (clean absence — operational failures exit 2; see §4.1)
```

Layers 1–4 are all `.toml` files and all outrank the env layer. The env layer (5) sits below all `.toml` layers because env-vars in a parent process are *ambient*, not deliberate — any export in a parent shell, IDE launch configuration, `.envrc`, or CI step would silently shadow the operator's registry values if env ranked above them. The registry's authority comes precisely from being the audited, operator-set source. The env var is an emergency one-off escape valve, not the default channel.

**`MACHINE_LOCAL_<KEY>` naming.** The key `repos.example_game_workbench_repo` maps to env var `MACHINE_LOCAL_REPOS_EXAMPLE_GAME_WORKBENCH_REPO` (dots and hyphens become underscores, all uppercase). This is the named successor to the ad-hoc per-repo env-var opt-in pattern — for example, the `EXAMPLE_GAME_REPO_ROOT=` pattern documented in `docs/wiki/cross-repo-citation-conventions.md § peerless-installs`. That pattern was the right local answer at the time; machine-local unifies all such ad-hoc env vars under one named registry with a documented fallback chain.

**Short shell-out examples:**

```bash
# Resolve a sibling-repo root; fail loud if not set
repo=$(machine-local get repos.example_game_workbench_repo)

# Resolve with a sibling-relative fallback (belt-and-suspenders pattern)
repo=$(machine-local get repos.example_game_workbench_repo --default "$(cd "$(dirname "$0")/../example-game-workbench-repo" && pwd)")
```

Consumers that want the full resolution chain (registry → sibling-relative → error with remediation) compose it themselves using `--default` or by checking the exit code of `machine-local has <key>` before the fallback.

### 4.1 Read-path exit-code contract — absence is not failure

A consumer that swallows any non-zero (`val=$(machine-local get X 2>/dev/null) || val=$fallback`) must be able to tell a **cleanly-absent key** from a reader that **could not produce an answer at all** — otherwise an operational failure silently masquerades as absence and the fallback fires when it should have fail-loud. The `get`/`has` read path therefore uses three exit codes:

| rc | meaning | when |
| --- | --- | --- |
| `0` | success | value found (`get`) / key present (`has`) |
| `1` | clean absence | `get`: key not found; `has`: key not set — the normal fall-back signal |
| `2` | operational failure | reader could not answer: Python < 3.11 version guard, malformed TOML |

A consumer that genuinely wants "use fallback on absence but fail-loud on a broken reader" branches on `2`:

```bash
val=$(machine-local get repos.foo); rc=$?
case $rc in
  0) : ;;                                  # got it
  1) val=$fallback ;;                       # cleanly absent — fall back
  *) echo "machine-local reader failed (rc=$rc)" >&2; exit "$rc" ;;  # operational — fail loud
esac
```

This contract is the fix for the 2026-06-24 daemon read-path bug: an MCP daemon launched under a stripped `PATH=/usr/bin:/bin` ran the wrapper against macOS system Python 3.9, tripping the version guard. Pre-fix that exited `1`, indistinguishable from "key absent," so the daemon degraded to `None` instead of failing loud. The write commands (`set` / `array-*`) have no "absent" concept and keep the simpler `0` = success / non-zero = refused-or-failed convention.

**Wrapper interpreter resolution.** The `machine-local` shell wrapper does **not** blindly take the first `python3` on `PATH` — under a stripped PATH that can be a guard-failing system Python. It probes candidates (`python3.14`…`python3.11`, then the generics) and execs the first that satisfies the `>=3.11` guard, self-healing for any caller whose PATH carries a good interpreter even when it isn't first. When the only reachable interpreter is older than 3.11 (nothing the wrapper can fix), it still execs it so the impl emits its actionable guard message and the operational `2`. Defense-in-depth with the contract above; cross-repo memo `2026-06-24-daemon-machine-local-readpath-rootcause-correction.md`.

## 4a. `CLAUDE_HOME` — canonical escape hatch for `~/.claude` path resolution

The machine-local registry resolves *values* with a documented precedence chain (§4). The companion question — *where does `~/.claude` itself live?* — has the same shape and is formalized here as cross-repo doctrine so peer plans (project-rag F11, example-game-repo, deep-research, future Python/TS/Rust consumers) adopt one convention instead of inventing N variants.

**Filesystem layout — `.claude.json` and `.claude/` are siblings under `$HOME`, not nested.** Reads matter here:

```
$HOME/
  .claude.json        <-- Claude Code's config (a single JSON file)
  .claude/            <-- Claude Central directory (this wiki's subject)
    machine-local/
    plugins/
    bin/
```

`CLAUDE_HOME` is a **`$HOME` substitute**, not a `.claude/` substitute. Setting `CLAUDE_HOME=/tmp/sandbox` redirects `.claude.json` to `/tmp/sandbox/.claude.json` and the entire `.claude/` install to `/tmp/sandbox/.claude/`. This matches `plugins/project-rag/scripts/_claude_config.py`'s long-standing semantics; the coordinator-side resolver was authored to be coherent with it.

**Resolution order for the `$HOME` analog.** Any tool that reads or writes `~/.claude.json` or anything inside `~/.claude/` MUST resolve the base directory in this order, most-specific first:

```
1. CLAUDE_HOME   — $HOME substitute (test sandboxes, CI runners, alt installs)
2. HOME          — POSIX-canonical (Linux/macOS/git-bash/MSYS/WSL)
3. USERPROFILE   — Windows-canonical fallback (native cmd.exe / PowerShell without HOME)
4. Path.home()   — language-stdlib last resort (Python `pathlib.Path.home()`, Node `os.homedir()`, etc.)
5. exit 1        — refuse to guess; emit remediation pointing here
```

From the resolved `$HOME` analog, the four downstream paths derive trivially: `<home>/.claude.json`, `<home>/.claude/`, `<home>/.claude/machine-local/`, `<home>/.claude/plugins/`.

**Why `CLAUDE_HOME` ranks above `HOME`.** Unlike `MACHINE_LOCAL_<KEY>` env vars (which rank *below* the registry because the registry is the deliberate audited source — §4), `CLAUDE_HOME` ranks *above* `HOME` because it answers a different question: not "what is this value" but "where does the entire Claude install live for this invocation". Test sandboxes, CI runners, scratch installs, and per-user-on-shared-machine setups all need to point the resolution at an alternate root without polluting the operator's real `$HOME`. There is no "registry of registries" to consult above it; `CLAUDE_HOME` *is* the deliberate audited override at this layer.

**Canonical resolver — `claude-home`.** Installed by `/coordinator:install` Phase 3 Step 3 alongside `machine-local`. Same shape: shell shim → Python module → Windows `.cmd`. Source-of-truth at `coordinator/lib/claude-home/` (load-bearing module: README + tests + artifacts co-located); install destination `~/.claude/bin/`. The `lib/<module>/` location is deliberate — it signals "cross-repo contract surface, do not customize" rather than "template scaffolding the operator may modify." Use from any coordinator-installed environment:

```bash
# Resolve the $HOME analog (CLAUDE_HOME if set, else $HOME)
home=$(claude-home home)

# Resolve the ~/.claude.json path
config_path=$(claude-home path)

# Resolve the ~/.claude directory itself
claude_dir=$(claude-home dir)

# Resolve sub-locations directly (avoids dirname/basename gymnastics)
ml_dir=$(claude-home machine-local)   # DELEGATES to 'machine-local dir' (settings-home seam) — see §4e
plugins_dir=$(claude-home plugins)
```

**`claude-home machine-local` delegation note (2026-07-06).** Post-relocation, `claude-home machine-local` is a **working delegation alias** — it exec-forwards to the `machine-local dir` subcommand (settings-home seam, §4e) rather than returning `<claude-dir>/machine-local` directly. This keeps existing `claude-home machine-local` callers working through the compat window. It is NOT removed in this plan; removal is gated on the 5 consumer confirmations, same as the phase-2 compat tail. `claude-home dir` continues to return the genuine `~/.claude` directory.

Python callers can import the module instead of shelling out (it sits at `~/.claude/bin/_claude_home.py` after install):

```python
import os
import sys
from pathlib import Path

# Resolve the bin/ location using the same precedence as the module itself.
# CLAUDE_HOME wins over HOME; do NOT use Path.home() unconditionally because it
# ignores CLAUDE_HOME and risks importing the wrong copy under test sandboxes.
_base = Path(os.environ.get("CLAUDE_HOME") or os.environ.get("HOME") or Path.home())
sys.path.insert(0, str(_base / ".claude" / "bin"))

from _claude_home import (
    claude_home_dir, claude_config_path, machine_local_dir,
    read_config, write_config,
)
```

The shell-out form is preferred for cross-language portability AND avoids the dual-identity hazard (§8(a)) — if anything else also imports `_claude_home` via a different `sys.path` insertion, two module copies live in `sys.modules` with separate state. The import form is fine for Python-only callers that want to avoid subprocess startup cost (~50ms cold-start on Windows) AND are confident they are the only importer in their process.

**Generic JSON I/O surface.** `_claude_home.py` ships the two generic primitives any install script touching `~/.claude.json` needs: `read_config()` (BOM-tolerant, returns `{}` for absent files, enriches `JSONDecodeError` with the file path) and `write_config()` (atomic tempfile + `os.replace`, creates parent dir, cleans up tmp files on failure). Higher-level shape-specific helpers — e.g., "update a single `mcpServers` entry under global vs `projects.<root>.mcpServers`" — stay with their consumer; those carry policy decisions (key-collision rules, project-key normalization) that don't generalize.

**Cross-repo alignment — coordinator is canonical.** `claude-home` (path resolver) plus the JSON I/O primitives ship with `/coordinator:install`. Peer repos that previously inlined a CLAUDE_HOME precedence chain (notably `plugins/project-rag/scripts/_claude_config.py`) should consume this surface and retire their local copies; the only thing that stays peer-side is the *shape-specific* layer (e.g., project-rag's `update_mcp_entry()`). Test coverage lives at `coordinator/tests/test_claude_home.py` (stdlib-only `unittest`, 16 tests, no pytest dep).

**What this unblocks.** Peer plans previously deferred the CLAUDE_HOME pattern as "host-side only, not cross-repo doctrine" (e.g., example-game-repo's review of project-rag F11). With §4a formalized, `claude-home` installed by coordinator setup, and the JSON I/O primitives shipped alongside, the pattern IS coordinator doctrine with a first-class resolver. Peer repos adopt by shelling out to `claude-home {home|path|dir|machine-local|plugins}` or importing the Python helpers — no precedence chain re-derivation, no duplicate test surface to maintain.

**Out of scope.** `CLAUDE_HOME` resolves *where the directory lives*, not *what is inside it*. Values inside (sibling-repo roots, vendor SDK paths, etc.) continue to resolve through the machine-local registry chain (§4). The two chains are orthogonal and compose cleanly: `CLAUDE_HOME` selects which `~/.claude/machine-local/registry.toml` the reader opens; the reader's own precedence chain then resolves keys within it.

**Bootstrap-lookup vs. contents-resolution — DO NOT conflate.** A peer repo importing the central `_claude_home.py` module hits two distinct $HOME-resolution surfaces with opposite precedence rules. The mistake is using `CLAUDE_HOME` for both; the failure mode is silent test-sandbox bypass of the central path.

| Surface | What it answers | Precedence |
|---|---|---|
| **Bootstrap lookup** | Where does `_claude_home.py` LIVE on disk? | `HOME` → `USERPROFILE` → `Path.home()`. **NOT `CLAUDE_HOME`.** |
| **Contents resolution** | What paths does the module's API return (`~/.claude.json`, `~/.claude/`, etc.)? | Full chain: `CLAUDE_HOME` → `HOME` → `USERPROFILE` → `Path.home()`. |

Why: `/coordinator:install` installs `_claude_home.py` at the operator's REAL `$HOME/.claude/bin/`, never at `CLAUDE_HOME/.claude/bin/`. A test setting `CLAUDE_HOME=/tmp/sandbox` to redirect contents resolution will find no module at `/tmp/sandbox/.claude/bin/`, the import fails, the peer falls back to its inlined copy, and the central path is never exercised under CI. The bug is invisible until production drift between the two copies surfaces.

Reference adoption shape: `coordinator/lib/claude-home/README.md § "Adopting from a peer repo"` carries the canonical Python snippet for the bootstrap-lookup half. Peer repos retiring inlined `_claude_config.py`-shaped modules MUST use the real-`$HOME`-only chain for the bootstrap import and let the central module own the full-precedence chain for everything it returns.

## 4b. Env-var resolver idempotency — gate re-resolution on `[[ -z ]]`

**Env-var resolvers that derive a canonical path and export it MUST gate re-resolution on `[[ -z "${VAR:-}" ]]` to prevent double-resolution in child processes.**

When a resolver script runs (e.g. `source ~/.claude/bin/claude-machine-local.sh`), it exports variables such as `$REPO_PROJECT_RAG` into the shell environment. A child process that sources the same script — or a grandchild that sources it again through a nested hook — will re-run the resolver against the same registry, potentially overwriting a `MACHINE_LOCAL_<KEY>` env override that a parent process deliberately set, or recomputing a path that was already correctly set. The guard pattern:

```bash
[[ -z "${REPO_PROJECT_RAG:-}" ]] && REPO_PROJECT_RAG=$(machine-local get repos.project_rag)
export REPO_PROJECT_RAG
```

applies to every exported variable the resolver emits. The `:-` default ensures an already-set empty string is treated as unset (intentional override to blank is a separate edge case). *Source: 2026-06-09 central-improvement-queue #76.*

## 4c. `repos.*` sibling-discovery ladder — SSOT pointer

<!-- spec-backlink: project-rag/docs/wiki/cross-machine-path-resolution-contract.md (SSOT) -->

The generic key-resolution order above (§4, rungs 1–7) governs ALL keys in the registry. For the specific question of *how a `repos.<slug>` value is discovered across machines*, a four-rung behavior ladder governs the resolution and is owned by project-rag as SSOT:

**SSOT:** `project-rag/docs/wiki/cross-machine-path-resolution-contract.md`

The four rungs in summary: **(1)** an explicit `REPO_<SLUG>` env-var or CLI flag overrides everything; **(2)** a tracked `search-roots.toml` lists OS-keyed parent directories and the scanner autodiscovers repos via `.claude-plugin/marketplace.json` identity markers — this is the primary rung for convention-installed repos (derive-not-store, no absolute paths stored); **(3)** a small tracked `path-exceptions.toml` maps OS-keyed slug → parent-path overrides for genuinely off-convention repos that cannot appear under any standard search-root; **(4)** `registry.local.toml`'s `repos.<slug>` key is the last-resort fallback for off-convention repos not discoverable under any search-root or path-exception (rung 2/3) — the documented, supported escape hatch named in the contract's remediation string. Do NOT re-specify the rung mechanics here — the SSOT contract is the authoritative source; a second copy would drift.

Coordinator retains ownership of: the key-namespace SCHEMA (what `repos.*` keys exist and mean), the generic key-resolution order (§4), the reader contract (§7), write-authority (§5a/§5b), and the helper surface (`machine-local` CLI, tri-language wrappers). The resolution-*behavior* axis (rung order, marker convention, fail-loud seam, `search-roots.toml` format) is project-rag-contract-governed.

## 4e. Settings Home — `~/.coordinator-claude-settings` and the Registry-Dir Seam

<!-- spec-backlink: docs/plans/2026-07-06-durable-substrate-to-settings-home.md § Design -->

The machine-local registry and coordinator durable substrate (`bin/` resolver family, `coordinator-whoami/`, `.coordinator-venv/`, `settings-manifest.md`) live in a **settings home** that is a deliberate sibling to `~/.claude` — clone-independent and immune to user edits of the `coordinator-claude` plugin clone. (`setup/` stays at `~/.claude/setup/` — intentionally NOT migrated; see `migrate-substrate-to-settings-home.sh`.) Full registry-dir precedence ladder (most-specific wins):

```
MACHINE_LOCAL_REGISTRY_DIR             (rung-1: direct registry-dir override; bypasses home
                                         resolution entirely — test isolation / explicit dir path;
                                         ~16 test files + 4 production readers depend on this)
  else COORDINATOR_SETTINGS_HOME/machine-local
                                        (rung-2: home root override; sandboxes/CI/XDG users)
  else ${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings/machine-local
```

**Settings home itself** (used for any sub-path other than the registry dir):

```
COORDINATOR_SETTINGS_HOME              (explicit home root override — document prominently)
  else ${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings
```

**`COORDINATOR_SETTINGS_HOME` is the sanctioned escape hatch** for operators who want XDG (`~/.config/...`) or other placement. `XDG_CONFIG_HOME` is intentionally NOT auto-honored — auto-XDG would break `CLAUDE_HOME`-based sandbox isolation and decouple the settings home from the sibling-to-`~/.claude` semantics.

**Linux/XDG users:** set `COORDINATOR_SETTINGS_HOME=~/.config/coordinator-claude` if you prefer XDG placement. Sandboxes and CI runners set `COORDINATOR_SETTINGS_HOME` to redirect the entire settings home to a temp dir (same mechanism as `CLAUDE_HOME` for `~/.claude`).

**`MACHINE_LOCAL_REGISTRY_DIR` is rung-1** — it bypasses home resolution entirely and targets the registry directory directly. It is NOT part of the key-resolution order (§4, rungs 1–7); it is a separate, earlier-resolving override at the *dir-location* level. This distinction matters for test isolation: ~16 test files and 4 production readers (`list-reverse-drift-cmds.sh`, `check-plugin-drift.sh`, `detect-hardware.sh`, `refresh-plugin-live-install.sh`) set `MACHINE_LOCAL_REGISTRY_DIR` to a sandbox path to run against a test registry without touching the operator's real registry.

**Fail-loud on divergent-realpath-both-homes:** if both `~/.claude/machine-local` AND `<settings-home>/machine-local` exist and their `realpath` values differ, the seam fails loud with a remediation pointing at the one-time migration (`migrate-substrate-to-settings-home.sh`). A compat symlink at `~/.claude/machine-local` whose `realpath` equals `<settings-home>/machine-local` is NOT a second divergent home and does NOT trigger fail-loud.

**Seam is location-only.** `coordinator-settings-home` (shell) and `settings_home()` (Python, `_settings_home.py`) return the home path and stop — they do not read registry contents.

**`~/.claude` compat window (transitional, phase-2 gated).** During the transition from `~/.claude`-resident substrate, `~/.claude/machine-local` is a realpath-symlink to `<settings-home>/machine-local`. Consumers that read the old absolute path continue to resolve the relocated content unchanged. The symlink is removed only at the single phase-2 gated tail, once all 5 consumers confirm migration. See `docs/plans/2026-07-06-durable-substrate-to-settings-home.md § Transitional compat window`.

**`machine-local dir` subcommand.** Returns `<settings-home>/machine-local` as an absolute path — the sanctioned dir-resolution primitive for concern-file readers that need to construct a path to a specific concern file (e.g. `project_rag.local.toml`):

```bash
# Resolve the machine-local directory itself (not the registry.toml file — use 'path' for that):
ml_dir=$(machine-local dir)

# Construct a concern-file path without hardcoding ~/.claude/machine-local:
project_rag_toml=$(machine-local dir)/project_rag.local.toml
```

`machine-local path` continues to return the absolute path to `registry.toml` (the file, not the directory). `machine-local dir` is the NEW subcommand for directory-path resolution; it is the concrete primitive consumers need to migrate hardcoded `~/.claude/machine-local/…` dir reads.

**`<settings-home>/bin/<name>` composition is a stable consumer contract.** The `bin/` resolver family (`machine-local`, `_machine_local.py`, `claude-home`, `_claude_home.py`, and siblings) lives at `<settings-home>/bin/`. A consumer that needs the **absolute path to an impl** — rather than invoking the bare-name wrapper — may compose `<settings-home>/bin/<name>` by resolving `<settings-home>` via the ladder above and joining `bin/<name>`. This is a blessed surface: the `bin/` layout is stable across the compat window and after the phase-2 gated tail.

**Windows: resolve by path arithmetic, never by invoking the wrapper.** On Windows the bare-name `machine-local` entry is a `.cmd`/shebang wrapper that hits a `CreateProcess`-no-`PATHEXT` / shebang trap when invoked from hidden-window install children. Consumers with such sites (e.g. example-game-repo's ~8 PS1 install sites) MUST NOT invoke the wrapper to bootstrap; instead resolve `<settings-home>` by **pure path arithmetic** in their own resolver (the ladder above — `MACHINE_LOCAL_REGISTRY_DIR` > `COORDINATOR_SETTINGS_HOME` > `${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings`), compose `<settings-home>/bin/_machine_local.py`, and invoke `python <that path> get <key>`. Arithmetic resolution executes no wrapper, so it dodges the trap entirely.

**Pin the composed path to the CLI; never read `registry.toml` to resolve it.** The arithmetic resolver is a *fallback that must not drift* from the canonical `coordinator-settings-home` CLI. Pin it with a parity/drift test comparing the arithmetic result against the CLI output, and resolve using arithmetic only — never open `registry.toml` to compute a path. This is the shape project-rag adopted for its impl-path sites. A `machine-local impl-path` wrapper subcommand would NOT solve the Windows problem — invoking it hits the same wrapper trap the `.py` pin exists to dodge; arithmetic composition of `<settings-home>/bin/<name>` is the seam.

<!-- spec-backlink: docs/plans/2026-07-06-durable-substrate-to-settings-home.md § Transitional compat window; surfaced by the example-game-repo-em settings-home residuals consult (Windows shape-iii gap), 2026-07-07 -->

## 4d. `.claude.json` `projects` map — EM last-resort repo-discovery hint (advisory)

The registry chains above (§4/§4c) resolve a **known** repo slug to a path. A different question — *which repos of note even exist on this machine?* — is normally answered by the curated sources (the `repos.*` namespace, `working-repos.yaml`, the sibling-repo enumeration in `~/.claude/CLAUDE.local.md`). When those are absent, thin, or you are in doubt, `~/.claude.json`'s top-level `projects` map is a **fallback hint an EM/DoE may consult** — Claude Code auto-maintains it as the set of directories it has been invoked in, so it needs no coordinator upkeep.

Treat hits as **candidates to confirm, never registry entries**. The map is a lossy proxy for "repos of note" in both directions:

- **False positives (noise):** it records every cwd ever used — junk one-off folders, scratch dirs, and subdirectories deep inside a repo, none of which are projects. Confirm a hit is a repo root (`.git` present) and is significant before acting on it.
- **False negatives (gaps):** a repo worked in only via `gh` / subagents / dispatch — never as a Claude Code cwd — will not appear at all. Several sibling repos on non-primary machines are exactly this shape (see `CLAUDE.local.md`). Absence from the map is **not** evidence a repo doesn't exist.

Because of both, `.claude.json` is a discovery *hint*, not a source of truth: it never overrides the curated registry, and it is per-machine and Anthropic-owned (undocumented, unversioned schema) — read it opportunistically, do not build tooling that depends on its shape. Resolve its path via `claude-home path` (§4a), not a hardcoded `~/.claude.json`. New repos worthy of a registry entry surface rarely enough that this stays a doctrinal pointer, not a system.

## 5. Relationship to `plugin-extraction-and-distribution.md` and `cross-repo-citation-conventions.md`

These two wikis define the **port-time cleanup contract** for the coordinator install chain: when extracting a plugin or porting vendored code, sweep absolute paths and replace them with sibling-relative references (`../<sibling-repo>/<path>`). That contract is **unchanged by this wiki** — at port time, the consumer does not yet exist to be told about machine-local. Sibling-relative is the correct vocabulary for the extraction step.

What this wiki establishes is context for the **runtime `repos.<slug>` discovery order** for consumers that already exist. As of 2026-06-30, that order defers to the 4-rung ladder in §4c (SSOT: `project-rag/docs/wiki/cross-machine-path-resolution-contract.md`); the prior numbered preference order (registry first → sibling-relative fallback → error) is superseded. The blind `../<sibling-repo>/` walk is **no longer a runtime rung** — marker-autodiscovery (§4c rung 2) replaced it. The "operator hasn't populated the registry" case is now served by autodiscovery with no sibling-layout compliance required.

The four failure modes that motivated this change remain valid doctrine — and explain WHY the walk is not the runtime mechanism: (a) it dictates operator filesystem layout; (b) it cannot represent deterministic locations (vendor binaries on a specific drive); (c) it fails opaquely with no remediation hint; (d) it does not compose with triangular dependency graphs where moving any one vertex breaks every sibling-relative inside the moved repo.

Port-time cleanup uses sibling-relatives because that is still better than absolute paths leaking into shipped code. Runtime `repos.<slug>` discovery follows the §4c ladder. Cross-link: `docs/wiki/plugin-extraction-and-distribution.md § 11`, `docs/wiki/cross-repo-citation-conventions.md § Sibling-layout convention`.

## 5a. Schema-Authorship vs. Value-Writing — Who Owns What

A recurring failure mode (observed across multiple EM sessions, 2026-05) is reading "the coordinator owns the registry" as "EMs other than the coordinator team should not write here," then sidecarring `~/.<tool>/config.toml` to avoid the perceived gate. That is the opposite of the design intent. Two distinct authorities are at play; conflating them is the bug:

- **Schema authorship** (coordinator-team responsibility). The shape of shared keys (`repos.*`, `install.*`, `plugin.mirrors.*`), the generic key-resolution order (§4), the reader contract (§7), and the helper surface (`machine-local`, `claude-machine-local.sh/ps1`, the Python module) are coordinator-governed because every consumer depends on them. Changing the reader contract, renaming a shared namespace, or adding a tracked baseline key requires coordinator-team coherence. **Exception — `repos.*` sibling-resolution-BEHAVIOR:** the rung order, marker-autodiscovery convention, and fail-loud seam for `repos.<slug>` discovery across machines are governed by project-rag's contract SSOT (`project-rag/docs/wiki/cross-machine-path-resolution-contract.md`); see §4c. The coordinator's schema and helper surface implement that behavior contract — they do not set the policy.

- **Value writing** (anyone on the machine). Appending values under existing namespaces, opening a new tool-specific namespace (`mything.*`), or hand-editing per-machine paths in `registry.local.toml` does NOT require coordinator-team sign-off. The reader is schemaless by design — no per-key validation, no declaration step (§7). The registry's whole value proposition is being the convenient shared place that prevents per-tool sidecars from accreting; gatekeeping value-writes would defeat the substrate.

The library/service distinction is useful here: this is a **library**, not a **service**. The coordinator ships the schema and helpers; callers freely write values under the schema. Treating it service-shaped (writes mediated by the coordinator team) is the misread §5b exists to correct.

## 5b. Adding a Value or Namespace — The Cheap Path Is the Default

Four shapes, only one is heavyweight:

1. **Per-machine path that varies across your machines.** Append a key to `registry.local.toml`. No declaration step required. The reader is schemaless; declaring an empty placeholder in tracked `registry.toml` is *optional* and only useful if you want the key shape to be discoverable across machines via git.
2. **New namespace cluster you own** (`mything.*`, `mytool.*`). Just use it. The `concerns` array (§6) gates *concern-file isolation* (whether `mything.*` reads from a separate `mything.toml`), not *namespace existence*. A new namespace under `registry.local.toml` needs zero registration.
3. **Sanctioned auto-writer** (your installer or daemon writes values, not just reads them). Heavier — §6's machine-generated-write-authority criterion applies, with single registered writer, declared sources, loud-fail on collision, and a `[provenance]` table. Worked example: project-rag's `wire` writes `[env]`/`[provenance]` to the **untracked** `project_rag.local.toml` — those values are machine-specific corpus paths, so by §9 they belong in the `.local` layer, not the tracked baseline. The tracked `project_rag.toml` carries only the operator-stable `[addons]` registration (enabled-flags, set by setup Phase 7D — not a per-machine path). This is the only path that warrants the heavier criteria; it is heavy because *unsupervised writers* need clobber-discipline, not because *humans/EMs adding values* do. **Concern-file provenance shape:** the `[provenance]` block lives at the concern-file root (not `[provenance.<concern>]`) because the concern name is already the file's namespace; provenance uses per-key sub-tables (e.g., `[provenance.install_root]`) to support multi-writer collision diagnosis when more than one automated writer contributes keys to the same concern file.
4. **Hand-edited cross-machine value** (same on every machine — schema version, a public URL). Append to `registry.toml`. It travels via git.

If you find yourself reading the wiki to figure out whether you "may" add a value — the answer is yes, cases 1, 2, and 4 are the default and need no authorization. Case 3 is the only one with criteria, and the criteria gate *automated writer patterns*, not human authorship.

**Writing a single concern key from the CLI — `machine-local set --concern`.** The bare `machine-local set <key> <value>` writer refuses namespaced keys (a `unreal.*` write is redirected to the concern file that owns the namespace). To set one concern key without hand-editing the TOML (which loses atomicity + provenance) or invoking a concern-owner's full seeder, use:

```bash
machine-local set --concern unreal unreal.samples_root /path/to/samples
```

It resolves `<name>.local.toml`, validates the key is under the `<name>.` namespace (rejecting cross-concern writes), does an atomic read-merge-write that preserves every other key/table, writes the key under the self-named `[<name>]` table (the form the reader's self-named-table elision expects — §4), and stamps `[provenance.<bare_key>]` (`written_by = 'machine-local'`, `source = 'cli:--concern'`). If `<name>` is not yet in the `concerns` array it writes anyway but emits a note that the value will not resolve via `get` until the concern is registered (§6). This is the general-purpose CLI counterpart to a concern-owner's bespoke seeder (e.g. the addon's `_seed_unreal_keys.py --set`), which remains valid as a seeder-local shortcut. Spec: cross-repo memo `2026-06-23-machine-local-concern-set-writer.md`.

## 5c.1. `repos.*` — Working Repos Only

As of 2026-06-30 (registry-publish-vs-working-targets plan), the `repos.*` namespace serves **one purpose**: sibling-repo discovery for scripts and agents (§5). Publish-target mirror paths have been separated into the distinct `publish.mirrors.*` namespace (§5c.2).

**Prior to 2026-06-30,** `repos.*` served a second role — resolving DEST roots for `publish.sh` targets via `repo:<dest_key>` portable rows. Those rows now use the `publish-mirror:<key>` sigil and resolve via `machine-local get publish.mirrors.<key>.path` exclusively (see §5c.2). The old `repos.coordinator_claude` and `repos.deep_research_claude` keys have been removed from `repos.*` and reborn as `publish.mirrors.coordinator_claude` / `publish.mirrors.deep_research_claude`.

The shared publish topology (which targets exist and what they publish) is committed to `setup/publish-targets.portable` and travels via git. Only the per-machine mirror DEST path stays in gitignored `registry.local.toml` — now under `[publish.mirrors.*]` tables. Provisioning a new machine:

```bash
machine-local set publish.mirrors.coordinator_claude.path   /abs/path/to/coordinator-claude
machine-local set publish.mirrors.deep_research_claude.path /abs/path/to/deep-research-claude
```

After that, `publish.sh` reads the portable topology from `setup/publish-targets.portable` and resolves all DEST roots from the registry — zero hand-authored absolute rows.

**Bootstrap precondition.** The `machine-local set` remediation shown above (and emitted by `publish.sh` on an unset key) presupposes the `machine-local` CLI is on PATH and `machine-local/` already exists. On a truly fresh OSS install neither may hold — the failure mode is "command not found", not a registry miss. This is exactly why the legacy `setup/publish-targets.sh` fallback is deliberately retained and not retired: it gives fresh-install operators a working path before the machine-local substrate is bootstrapped.

## 5c.2. `publish.mirrors.*` — Publish-Target Mirror Destinations

The `publish.mirrors.*` namespace holds outward-only OSS distribution destinations — repos the coordinator team *pushes to* and must *never* treat as source or working trees.

### Two-class taxonomy

| Class | Namespace | Purpose | How to resolve |
|---|---|---|---|
| Working repos | `repos.*` | Sibling-repo roots used by scripts, agents, and tooling | `machine-local get repos.<name>` |
| Publish-target mirrors | `publish.mirrors.*` | OSS mirror DEST roots — outward push only, never working trees | `machine-local get publish.mirrors.<key>.path` |

**Why distinct namespaces, not a class attribute on `repos.*`?** Distinct namespaces make the publish→working-repo clobber guard structural: `publish.sh` reads only the mirror namespace, so it can never accidentally resolve a working repo as a publish destination. The clobber risk is documented at `plugin-extraction-and-distribution.md:87` and `live-install-drift-audit.md:21`.

### Schema shape

Each publish mirror is a nested TOML table split across tracked `registry.toml` (owner + same-on-every-machine values) and gitignored `registry.local.toml` (per-machine absolute path):

```toml
# registry.toml (TRACKED — declarations + shared values)
[publish.mirrors.coordinator_claude]
owner = "claude-central-em"

[publish.mirrors.deep_research_claude]
owner  = "claude-central-em"
aliases = ["deep-research", "deep-research-em"]   # legacy shortnames — not derivable from key

# registry.local.toml (GITIGNORED — per-machine absolute paths)
[publish.mirrors.coordinator_claude]
path = "/abs/path/to/coordinator-claude"

[publish.mirrors.deep_research_claude]
path = "/abs/path/to/deep-research-claude"
```

### `publish-mirror:` sigil in `setup/publish-targets.portable`

Portable rows use `publish-mirror:<key>` in field 3. The resolver (`setup/lib/resolve-publish-target.sh`) routes that sigil exclusively through `machine-local get publish.mirrors.<key>.path` — no `repos.*` read occurs in that branch. The legacy `repo:` branch is retained for backward-compat, but any residual `repo:coordinator_claude` / `repo:deep_research_claude` row rc1-fails after the migration because those `repos.*` keys no longer exist.

### Migrating an existing machine

Run the idempotent migration subcommand once:

```bash
machine-local migrate-publish-mirrors
```

This moves `repos.coordinator_claude` / `repos.deep_research_claude` values (and the legacy `repos.deep_research` alias) into `[publish.mirrors.*].path` tables, removes the old `repos.*` keys, and rewrites `repo:<mirror>` rows in any machine-local `publish.targets` registry array. Re-run is a no-op once migrated. For legacy `publish-targets.sh` fallback files the subcommand emits loud operator-remediation instead of editing the gitignored file automatically.

### Namespace-stability invariant (F6)

`publish` MUST remain a **registry namespace** (keys in `registry.toml` / `registry.local.toml`) and must NOT be promoted to a concern file. If `publish` is ever added to the `concerns` array, `_clean_registry` (`_machine_local.py:234-244`) will silently drop every `publish.mirrors.*` and `publish.targets` registry entry with no error. Any proposal to add a `publish.toml` concern file must be treated as a breaking change to this architecture and requires an explicit decision record.

### Distinct from `plugin.mirrors.*`

`plugin.mirrors.*` is the live-install source→live propagation namespace (example-game-repo-control, coordinator-claude, etc.) — a separate concept entirely. Do not confuse the two:

| Namespace | Purpose | Reference |
|---|---|---|
| `plugin.mirrors.*` | Live-install drift tracking (source→live propagation mode + paths) | §12 |
| `publish.mirrors.*` | OSS publish-target DEST roots (outward push, never live-install) | this section |

### `$REPO_COORDINATOR_CLAUDE` / `$REPO_DEEP_RESEARCH_CLAUDE` env exports

The `claude-machine-local.sh` shell helper exports `$REPO_<NAME>` for every `repos.*` key. Since `repos.coordinator_claude` and `repos.deep_research_claude` are no longer in `repos.*` (they were publish DEST keys, never dev-tooling source paths; no active consumers of those env exports exist), `$REPO_COORDINATOR_CLAUDE` and `$REPO_DEEP_RESEARCH_CLAUDE` intentionally disappear from the helper's export set. Where the publish DEST path is needed, use `machine-local get publish.mirrors.coordinator_claude.path` / `machine-local get publish.mirrors.deep_research_claude.path` directly.

## 5c. Coordinator-owned Keys — Reference

Keys authored by coordinator infrastructure (not user-set). These are registered in tracked `registry.toml` as empty-value declarations; per-machine values are written to `registry.local.toml` by the named script.

| Key | Writer | Consumer | Meaning |
|---|---|---|---|
| `coordinator.python` | `bin/ensure-coordinator-venv.sh` | `lib/resolve-python.sh` | Absolute path to the coordinator venv's Python interpreter on this machine (e.g. `~/.coordinator-claude-settings/.coordinator-venv/bin/python`). Written when the coordinator venv at `~/.coordinator-claude-settings/.coordinator-venv/` is created or rebuilt. Never hand-edit — let `ensure-coordinator-venv.sh` set it. Pre-relocation (before 2026-07-06): this was `~/.claude/.coordinator-venv/bin/python`; if you see the old path in your registry, re-run `/coordinator:install` Phase 3 to rebuild the venv at the settings home. |
| `coordinator.machine_slug` | `coordinator:install` (eager seed); `/workday-start` Step 0 (lazy self-heal) | `lib/coordinator-daily-branch.sh` (`cs_compute_machine`) | The canonical machine token used in daily branch names (`work/{machine}/{date}`). Classification: `idempotent-regeneratable` — seeded from `cs_compute_machine_live` (hostname-derived) at a known-good moment; re-seeded by `/workday-start` on any pre-seed install. Drift vs. live hostname is surfaced by `/workday-start` Step 0 (detect-then-fail-loud, not silent overwrite). Never inherit from an existing branch name or substrate label — see `docs/wiki/daily-branch-discipline.md § Machine-token derivation`. |
| `coordinator.contributor_slug` | `coordinator:install` (silent absent-only eager seed); `/workday-start` Step 0 (lazy self-heal) | `lib/coordinator-daily-branch.sh` (`cs_compute_contributor` / `cs_compute_contributor_live`) | The canonical human-contributor token — the `{human}` identity axis, structurally mirroring `coordinator.machine_slug`'s `{machine}` axis. **Resolver precedence (four-tier, most-specific first):** (1) `$COORDINATOR_CONTRIBUTOR` env escape valve (persisting it is discouraged — it silently masks registry-key drift detection, exactly like `$COORDINATOR_MACHINE`, see §4 above); (2) `coordinator.contributor_slug` registry key (canonical); (3) sanitized git `user.email` local-part (seed source only); (4) `"unknown"`. **Charset:** resolved slugs MUST match `^[a-z0-9][a-z0-9-]*$` — enforced by the same bash port of the `_memo_filename` sanitize idiom used elsewhere (`cross-repo-memo:868-870`: lowercase → collapse non-`[a-z0-9-]` runs to a single dash → collapse consecutive dashes → strip leading/trailing dashes). **Fleet-unique onboarding note:** slugs must be unique across the collaborator fleet; uniqueness is operator-set and drift-surfaced (not enforced structurally) — collision likelihood is LOW per the ratified risk table (`tasks/multi-collaborator-support/D0-ownership-model-RATIFIED.md`), and a collision surfaces via `/workday-start` Step 0's detect-then-fail-loud drift comparator, never a silent pick. **Seed-source demotion / PII note:** git `user.email` is a seed source ONLY — it is PII-bearing (drops the `@domain` half before sanitizing, local-part only) and is never promoted to the canonical key; the registry value, once seeded or operator-set, is authoritative and `user.email` is not re-consulted except as the live/drift comparator. Classification: `idempotent-regeneratable` — seeded from `cs_compute_contributor_live` at a known-good moment (silent, absent-only, never a canonical overwrite); re-derivable with no state loss. **Caveat vs. `machine_slug`:** unlike `machine_slug` (purely hostname-derived, re-derives to the *same* value on every clean re-seed), `contributor_slug`'s seed source is git `user.email`, which can change over the contributor's lifetime — regeneration after key loss recovers the value as of the *current* seed-time email, not necessarily the value that was lost, if the operator's email changed between loss and re-seed. See `docs/plans/2026-07-08-mcollab-01-contributor-slug.md § Design` for the full resolver/seed lifecycle. |

**`coordinator.python` resolution contract.** `lib/resolve-python.sh` resolves the coordinator Python in this order: (1) `COORDINATOR_PYTHON` env var (test override), (2) `machine-local get coordinator.python` (registry pin), (3) existing PATH Python as a fallback. A stale or broken pin (the path in the registry no longer resolves to a working interpreter) fails loud with a remediation pointing at `bin/ensure-coordinator-venv.sh`. This key is the successor to the bare-`python3` assumption that broke when the coordinator migrated `coordinator_whoami` into its own venv (`~/.claude/.coordinator-venv/`) to avoid PEP-668 blocks and system-Python-bump-induced import failures. See `docs/wiki/install-surface-completeness.md § whoami venv pin (2026-06-20)`.

**Consumer recipe — use `coordinator_whoami` from a sibling/consumer venv via SUBPROCESS, never a bare import (D2-26).** A consumer repo's own venv interpreter (e.g. `project-rag/.venv/bin/python`) **cannot** `import coordinator_whoami` — the package lives only in the coordinator venv (`~/.claude/.coordinator-venv/`), and the 2026-06-20 whoami-durable workstream *deliberately* made the bare in-process import fail-loud rather than silently resolve a wrong interpreter. This is by design, not a gap. The sanctioned consumer pattern is to **resolve the coordinator interpreter and invoke `coordinator_whoami` as a subprocess**:

```bash
# Shell consumer (preferred — one resolution seam):
COORD_PY="${COORDINATOR_PYTHON:-$(machine-local get coordinator.python)}"
[ -x "$COORD_PY" ] || { echo "coordinator venv not provisioned — run /coordinator:install Phase 3 Step 6" >&2; exit 1; }
"$COORD_PY" -m coordinator_whoami <args>
```

```python
# Python consumer — resolve, then subprocess; do NOT `import coordinator_whoami`:
import os, subprocess
coord_py = os.environ.get("COORDINATOR_PYTHON") or subprocess.check_output(
    ["machine-local", "get", "coordinator.python"], text=True).strip()
subprocess.run([coord_py, "-m", "coordinator_whoami", *args], check=True)
```

Resolution precedence is the `coordinator.python` contract above (`COORDINATOR_PYTHON` env → registry pin → fail-loud). All coordinator-internal probes already follow this seam (`coordinator-doctor.md §5`); a consumer simply reuses it. Do NOT install `coordinator_whoami` into the consumer venv (duplicate-install drift) and do NOT add a `sys.path` shim (couples the consumer to the coordinator venv's internal layout).

## 6. Concern-file Convention

Most values belong in the core `registry.toml`. A concern file (`unreal.toml`, `cuda.toml`) is warranted only when a surface meets at least one of:

- More than five keys for that namespace, OR
- Version-multiplexed values (e.g., Unreal 5.4, 5.5, 5.6 each with their own install root), OR
- **Machine-generated write authority** — the file is written by an automated process from declared sources (e.g., `cli.py wire` aggregating each installed addon's `CorpusBand.required_env` declarations), not hand-edited by the operator. Concern-file isolation here is doing different work from the count/version criteria: it separates machine-generated content from operator-edited config so the automated writer's clobber radius can never touch operator-set values, and so the file's `[provenance]` attribution stays co-located with the keys it describes. The criterion gates on the **writer pattern** (registered automated aggregator from declared sources), not on key count or addon presence — a hypothetical addon whose two keys are hand-edited by the operator still belongs in `registry.local.toml`. Worked example: project-rag's `wire` aggregator. Its machine-specific `[env]`/`[provenance]` output (written exclusively from each installed addon's declared sources; loud-fail on cross-addon key collision; `[provenance]` records addon→key attribution that the predecessor `wiring.env` lost) lands in the **untracked** `project_rag.local.toml` — per §9, the corpus paths differ per machine, so they belong in the `.local` layer. The tracked `project_rag.toml` carries only the operator-stable `[addons]` registration (setup Phase 7D). Hand-editing a `wire`-managed key would be silently clobbered on the next addon install — the operator's leverage is via the source declarations, not the concern file.

When a concern file is listed in `registry.toml`'s `concerns` array, that concern's namespace (`unreal.*`, `cuda.*`) is **resolved exclusively from the concern file**. Keys with that prefix in `registry.toml` are ignored and emit a warning — the concern file wins. Put `unreal.*` keys EITHER in the core registry OR in `unreal.toml`, never both. This is a read-resolution rule (avoids silent shadowing for operators), not an ownership/permission rule — see §5a for the schema-authorship-vs-value-writing distinction.

**Registered concern files — reference.**

| Concern name | Tracked baseline | Per-machine values file | Writer | Key namespace | Justification (§6 criterion met) |
|---|---|---|---|---|---|
| `unreal` | `unreal.toml` | `unreal.local.toml` | project-rag-ue-addon + example-game-repo installers (multi-writer) | `unreal.*` | Version-multiplexed values (5.3–5.7 install roots) + machine-generated write authority (multi-writer requires `[provenance]` stamping per §12) |
| `project_rag` | `project_rag.toml` | `project_rag.local.toml` | `cli.py wire` aggregator | `env.*` (machine corpus paths) | Machine-generated write authority — single registered aggregator from declared addon sources; loud-fail on cross-addon key collision; `[provenance]` records addon→key attribution |
| `hardware` | `hardware.toml` | `hardware.local.toml` | `lib/detect-hardware.sh` (called by `lib/install-substrate.sh` on install; single writer) | `hardware.*` | Machine-generated write authority — the install-time hardware audit writes `hardware.cores`, `hardware.ram_gb`, and optionally `hardware.gpu`/`hardware.vram_gb` from declared system sources; values differ per machine (not operator-editable); idempotent re-audit on re-run. Added by the 2026-06-23 setup-time-substrate-completeness plan. |

**`hardware` concern — shape and lifecycle.** The concern follows the same two-file split as `unreal`:

- **Tracked `hardware.toml` schema baseline** — copy-if-not-exist at install time (same `install-substrate.sh` logic as the `unreal.toml` baseline at lines 96-98). Contains the key declarations for the concern namespace; no machine-specific values. Travels via git so the key shape is discoverable across machines.
- **Gitignored `hardware.local.toml` machine values** — written (and upserted on re-run) by `lib/detect-hardware.sh` via `machine-local set --concern hardware hardware.cores <n>` etc. (the `--concern` writer from the 2026-06-23 machine-local-concern-set-writer plan, commit `210fa58a`). Values are regeneratability class `idempotent-regeneratable` (§13) — lost values are recovered by re-running `lib/install-substrate.sh` or the OSS `setup/install.sh --setup-only`.
- **Concern registration** — `registry.toml`'s `concerns` array includes `"hardware"` so that `machine-local get hardware.*` resolves from `hardware.local.toml` rather than falling through to the core registry. The install-substrate.sh migration step (AC10) performs a TOML-aware upsert to add `"hardware"` to the `concerns` array on existing installs where the entry is absent.
- **Doctor probe** — the hardware-absence probe registered in `bin/doctor-probes.toml` detects missing `hardware.cores`/`hardware.ram_gb` and emits population-aware remediation: "run coordinator:install Phase 3" for coordinator-install users; "re-run setup/install.sh" for OSS users. See `coordinator-doctor.md` for the probe narrative.

**Writing concern-namespace keys via the CLI — `machine-local set --concern`.** The bare `machine-local set <key> <value>` writer REFUSES concern-namespace keys (the concern file owns the namespace; a bare `set unreal.x` redirects to the concern owner). To set an individual concern scalar without hand-editing the TOML or running a concern owner's full seeder, use the explicit opt-in:

```bash
machine-local set --concern unreal unreal.samples_root /x/LyraStarterGame
```

The writer resolves `<name>.local.toml`, validates the key is under the `<name>.` namespace (rejects cross-concern pollution; rejects mixed-case keys fail-loud), performs an atomic read-merge-write that preserves every co-writer key/table **with its scalar type intact** (the DR-CONTRACT-001 witness integer `unreal.emit_shape_version` round-trips as an int, not a string — see §12), and stamps `[provenance.<bare_key>]` with `written_by = machine-local`, `source = cli:--concern`. This is purely additive: bare `set` still refuses concern keys (the negative-spec is preserved; `--concern` is the explicit carve-out). A concern owner's own seeder (e.g. project-rag-ue-addon's `_seed_unreal_keys.py --set`) remains valid as a seeder-local shortcut. Spec: cross-repo memo `2026-06-23-machine-local-concern-set-writer.md`; `docs/plans/2026-06-23-machine-local-concern-set-writer.md`.

**Extension path (per the Director of Engineering review, F7).** If a future need for per-repo metadata (kind, role, version, consumer-set) emerges, the extension path is a new concern file (e.g., `repos_meta.toml`), not restructuring the flat `repos.*` namespace. The flat namespace is correct for the current consumer set (sibling-repo roots are strings, not structured objects). YAGNI: add the concern file if and when the need is concrete; this note just records that the extension path exists so a future contributor does not feel forced to restructure the baseline.

**When the "wait for instance #3" rule applies vs. when it doesn't.** Per `docs/wiki/ceremony-calibration.md`, conventions wait for the third instance before being extracted into a shared abstraction — single instances of a pattern are routinely premature to generalize. The machine-local registry itself appears to break that rule (four EM reinventions surfaced in the triggering plan's §1.2). It does not, because the rule's exception is precisely the case it surfaced: the rule prevents premature abstraction when you have *one* instance and might invent a *second* speculatively; it does NOT prevent abstraction when you already have *N≥2* instances and one of them is in active wrong-shape arrangement because the abstraction never existed. The four-reinvention pattern + the wrong-shape `wiring.env`-style accumulation was the empirical signal; the rule held perfectly. Document this distinction when proposing similar substrate-gap-driven extractions.

**Concern loader — two operational notes.**

- **`schema` is a per-file meta-key, not a queryable value.** Every concern file carries `schema = 1` at its root to declare the file-format version. The reader's `_flatten_concern` helper intentionally skips this key — `machine-local get unreal.schema` (or `<any-concern>.schema`) always returns not-found, regardless of what is written in the file. This is by design, not a loader failure. Do not file bugs when `<concern>.schema` resolves not-found.

- **A missing concern emits a fail-loud warning (not silent not-found).** If a concern is listed in `registry.toml`'s `concerns=[...]` array but neither `<concern>.toml` nor `<concern>.local.toml` can be loaded (files absent, unreadable, or empty), the reader emits a stderr warning of the form `machine-local: warning: concern '<name>' is registered in concerns=[...] but neither '<name>.toml' nor '<name>.local.toml' could be loaded ... Refresh the install or remove it from concerns.` The concern's keys resolve not-found as before, but the misconfiguration is no longer silent. This is the correct failure mode per coordinator doctrine: detect-then-fail-loud, never detect-then-silently-ignore.

## 7. Reader Contract — Intentionally Minimal

The reader (`machine-local`) returns string values. No nested types. No per-key schemas. No built-in validation beyond TOML parse and schema version check.

This is a deliberate choice: the substrate is a flat string-typed key/value store. If your consumer needs structured values (a list of targets, a typed enum), parse the string in your consumer. The reader stays small so every language and script environment can call it without ceremony.

The reader is **read-only**. It never writes, never caches to disk, never mutates the registry. Write authority belongs to the operator, always.

## Ergonomic helpers

Two thin wrappers over `machine-local` make the registry-correct shape shorter than the hardcoded literal. Both shell out to the reader CLI — they do NOT import `_machine_local.py` directly (per §8(a) and `docs/wiki/dual-identity-module-hazard.md`).

**Python** — `~/.claude/bin/claude_machine_local.py`:

```python
from claude_machine_local import repos
config_path = repos.project_rag / "subdir/file.toml"
```

Missing keys raise `AttributeError` with a remediation message. Process-local memoization amortizes the ~50ms shell-out cost.

**Shell** — source once per session:

```sh
source ~/.claude/bin/claude-machine-local.sh
echo "$REPO_PROJECT_RAG/subdir/file.py"
```

Exports `$REPO_<NAME>` for every declared `repos.*` key (note: prefix is singular `REPO_`, not `REPOS_`). Hyphens in keys are normalized to underscores; identifiers that fail POSIX validation are skipped with a stderr warning.

> **Naming note.** The export prefix is singular `REPO_` (not `REPOS_`). This is the shipped convention; the original plan spec used `REPOS_` but the final implementation settled on `REPO_`. Hyphens and dots in key names are both normalized to underscores — `repos.project-rag` exports as `REPO_PROJECT_RAG`.

**PowerShell** — dot-source:

```powershell
. ~/.claude/bin/claude-machine-local.ps1
"$($env:REPO_PROJECT_RAG)/subdir/file.py"
```

Same contract; OS-detects between `machine-local.cmd` (Windows) and the bash wrapper elsewhere.

Templates at `~/.claude/plugins/coordinator/templates/bin/` are byte-identical mirrors of these — they publish to consumer projects via `setup/publish.sh` alongside the reader.

## 8. Anti-patterns

**(a) Importing the registry as a Python module by absolute path.** Do not do `importlib.util.spec_from_file_location("machine_local", "/path/to/_machine_local.py")` or equivalents. Python-importable resolvers reintroduce the dual-identity failure mode: importing the same `.py` file under two different module identities yields two copies in `sys.modules` with separate state. Read `docs/wiki/dual-identity-module-hazard.md` before proposing a Python-importable `machine_local` package. The correct reader contract is shell-out: `machine-local get <key>`.

**(b) Writing to machine-local from an MCP server or daemon.** The writer is the operator, always — for `registry.toml`, `registry.local.toml`, and any concern file whose lifecycle is operator-edit. An MCP server or background daemon that writes to those files is acting outside its authority. The explicit carve-out is concern files that satisfy §6's machine-generated-write-authority criterion: those have a single registered writer (e.g., `cli.py wire`) that IS the authority for that file, declared sources, and well-defined clobber semantics. The anti-pattern is unauthorized writes to operator-edited config; sanctioned writes by a registered writer to its own concern file are §6 by construction. If your tool needs to persist runtime-discovered state and you do NOT have §6's writer-pattern shape, write it somewhere under the relevant plugin's data directory instead.

The `machine-local set --concern` CLI writer (§6) is NOT an exception to this rule — it is the operator's own hands at the CLI, the same authority that hand-edits the file, just atomic and provenance-stamping. The writer-is-the-operator invariant holds; an MCP server or daemon shelling out to `set --concern` to persist runtime state would still be the §8(b) anti-pattern (the operator is not in the loop).

**(c) Adding a value that varies per-project.** Per-project state (project root, project type, enabled plugins, skill overrides) belongs in the project's `.claude/` config, not in machine-local. Machine-local is scoped to the machine, not the project; a value that changes when you switch projects is not per-machine.

**(d) Adding a value that varies per-runtime-invocation.** Values that change with each tool invocation — current binding, active corpus, daemon PID — belong in live MCP introspection. See §2 and `docs/wiki/plugin-identity-and-health-sentinels.md`.

**(e) Adding a value that is universal across machines.** If the value is the same on every machine the operator runs (e.g., a fixed public URL, a schema version constant, a vendor SDK that always installs to the OS-canonical location), commit it to the relevant repo. Git-tracked durability is the right primitive; no operator action needed per machine.

**(f) Putting machine-specific path values in `registry.toml` instead of `registry.local.toml`.** `registry.toml` is git-tracked and travels with the `~/.claude` repo across machines. If you bake `repos.example_game_workbench_repo = "E:/dev/example-game-workbench-repo"` into `registry.toml`, that path is wrong on every other machine the operator uses. Machine-specific values go in `registry.local.toml`, which is gitignored. See §9 for the full split rationale and the Striker-and-Mac worked example.

## 9. Tracked Baseline + `.local` Overrides — Why and When

`~/.claude/` is git-trackable, and operators are encouraged to treat it that way (established practice on the PM's machines; documented as a recommendation for OSS adopters in the coordinator setup material). The registry composes with that:

- `registry.toml` (and any `<concern>.toml`) is **tracked** — carries the shared baseline: key declarations, `schema = 1`, the `concerns` list, and values that hold across all of the operator's machines.
- `registry.local.toml` (and `<concern>.local.toml`) is **gitignored** — carries per-machine path values. These are the values that differ across the operator's machines.

This matches the `*.local.*` precedent already established at `~/.claude/`: `CLAUDE.local.md`, `coordinator.local.md`, `settings.local.json`. The `.local` convention is consistent throughout the install tree.

**Worked example — Striker and Mac.** The operator runs from Striker (Windows, repos under `X:/...`) and a Mac on the go (repos under `~/work/...`). One git-tracked `~/.claude` repo lives on both machines. `registry.toml` is identical on both — it declares `repos.project_rag`, `repos.example-sim-repo`, etc. as keys, sets `schema = 1`, lists `concerns`. On Striker, `registry.local.toml` contains:

```toml
"repos.project_rag" = "X:/project-rag"
"repos.example-sim-repo"    = "E:/dev/example-sim-repo"

[publish.mirrors.coordinator_claude]
path = "X:/coordinator-claude"

[publish.mirrors.deep_research_claude]
path = "X:/deep-research-claude"
```

On the Mac, `registry.local.toml` contains:

```toml
"repos.project_rag" = "~/work/project-rag"

[publish.mirrors.coordinator_claude]
path = "~/work/coordinator-claude"
```

Same keys, different machine-specific values, no manual reconciliation, no merge conflicts — `.local.toml` is gitignored on both ends so it never appears in the shared history. Single-machine operators ignore the `.local` layer entirely; it is opt-in by virtue of the file simply not existing unless the operator creates it. Note that publish mirror paths follow the same `.local.toml` convention but live under `[publish.mirrors.*]` nested tables (§5c.2) rather than flat `repos.*` keys.

## 10. When NOT to Use `.local`

`.local` is specifically for values that **differ across the operator's machines** — that is the discriminator. If a value is the same on every machine the operator runs, it belongs in `registry.toml` and inherits git-tracked durability for free. Misusing `.local` for stable cross-machine values loses the version-history benefit and forces manual synchronization.

Examples of values that should NOT go in `.local`:

- A vendor SDK that always installs to the OS-canonical location (e.g., `C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v12.4` when all machines run the same Windows CUDA version) — commit to `registry.toml`.
- A publish target URL that is the same on every machine — commit to `registry.toml`.
- A schema version or well-known constant — commit to the relevant repo, not the registry at all.

The test: *"If I cloned `~/.claude` to a second machine right now, would this value be wrong there?"* If yes, `.local.toml`. If no, `registry.toml`.

## 11. Per-project State Directories Under `~/.claude/` — Inventory

Machine-local handles operator-set config (key-value, TOML, reader-mediated). The orthogonal substrate is **per-project state directories** under `~/.claude/<project>/` — bespoke paths each project owns for runtime artifacts (PID files, lockfiles, status JSON, install logs, sentinels) that aren't shaped like key-value config. Two substrates, one canonical root.

**Doctrine (2026-05-19, DoE):** The §1.2 namespace-scalability critique of `~/.project-rag/` (per the DoE reply memo, `~/.claude/cross-repo/archive/2026-05-19-machine-local-doe-reply.md` — grandfathered pre-cutoff memo) is content-agnostic. State directories do NOT get a top-level carve-out — `~/.<project>/` is the anti-pattern whether the contents are config or state. State lives under `~/.claude/<project>/` alongside the project's other claude-home artifacts. XDG's `STATE_HOME` vs `CONFIG_HOME` split informs sub-path naming inside the namespace, not separate top-level dirs.

**Registered namespaces:**

| Namespace | Owner | Contents | Notes |
|---|---|---|---|
| `~/.coordinator-claude-settings/` | coordinator | **Settings home** — durable coordinator substrate: `machine-local/` (TOML registry), `bin/` (resolver family), `coordinator-whoami/`, `.coordinator-venv/`, `settings-manifest.md` (`setup/` stays at `~/.claude/setup/` — intentionally NOT migrated; see `migrate-substrate-to-settings-home.sh`) | New top-level FS namespace registered 2026-07-06 (durable-substrate-to-settings-home plan). Sibling to `~/.claude`. Redirectable via `COORDINATOR_SETTINGS_HOME` env var; sandbox-safe via `CLAUDE_HOME`. See §4e for the full resolution ladder. |
| `~/.claude/example-game-repo/` | example-game-workbench-repo | install-status.json, install-logs/, setup-state.json; **imminent:** watchdog/status.json, chain-walk-*.json (migrating from `~/.example-game-repo/`) | Migration in flight 2026-05-19; collapses the dual-namespace split (`~/.example-game-repo/` + `~/.claude/example-game-repo/`) into the canonical root. See `example-game-workbench-repo/state/memos/2026-05-19-doe-question-example-game-repo-namespace-collapse.md` (grandfathered pre-cutoff memo) |
| `~/.claude/project-rag/` | project-rag host | host runtime state | Existing; predates this doctrine |
| `~/.claude/machine-local/` | coordinator | **Transitional compat symlink only** — realpath-symlink → `~/.coordinator-claude-settings/machine-local/`. Retained for consumers that read the old absolute path; removed at phase-2 gated tail. **Actual content lives at `~/.coordinator-claude-settings/machine-local/`.** | DoE-altitude: claiming this top-level dir is unchanged; it is now a symlink pointer. |
| `~/.claude/plugins/<plugin>/data/` | each plugin | addon-owned on-disk state | Plugin-addressed; orthogonal to top-level project dirs |
| `~/.claude/.coordinator-venv/` | coordinator-claude | **RELOCATED** to `~/.coordinator-claude-settings/.coordinator-venv/` (2026-07-06). This path is the legacy location; the actual venv now lives in the settings home. `coordinator.python` registry key points to the new location. | Legacy path removed after venv rebuild confirms healthy. If you see this path, run `/coordinator:install` Phase 3 to rebuild at the settings home. |

**Adding a new top-level FS namespace under `~/.claude/<project>/`.** This is the DoE-altitude call: claiming a top-level directory under `~/.claude/` is an FS-namespace claim that other projects might collide with, and the §1.2 critique of `~/.<project>/` accretion is what this row exists to prevent. Register here in the same commit that creates the directory on disk; PM-authorized.

**Distinct from — adding a TOML key or table inside the registry.** Adding a new key in `registry.local.toml`, opening a new dotted namespace (`mything.*`), or even authoring a new concern file under §6 criteria is NOT DoE-altitude. See §5a (authorship vs. value-writing) and §5b (the cheap path for adding values). The FS-namespace gate here is about *new top-level directories on disk*, not about *content inside the registry's existing namespace*.

**Retiring `~/.<project>/` top-level dirs.** When a project still owns a `~/.<project>/` top-level namespace, migrate to `~/.claude/<project>/` and register here. Operator-visible path migration; one release of relocation logic. The `~/.project-rag/wiring.env` retirement (PM-handled, downstream of this registry shipping) is the worked precedent.

## 12. `plugin.mirrors` — Plugin Live-Install Tracking

<!-- spec-backlink: docs/wiki/plugin-extraction-and-distribution.md:87 (publish.sh direction + 2026-05-20 clobber ban); docs/wiki/live-install-drift-audit.md:21 (drift audit doctrine) -->

The `plugin.mirrors` table namespace registers plugins whose live install may be a separate git checkout of the plugin's source repo. The drift probe (`check-plugin-drift.sh`) reads these entries to detect when a live install has fallen behind its source.

**Full schema, field reference, and operator examples live in `~/.claude/machine-local/README.md § plugin.mirrors`** — do not duplicate here. The summary below covers only the doctrine decision points.

**No provenance stamp on `plugin.mirrors.<name>` writes (DoE ruling 2026-05-23).** Each `[plugin.mirrors.<name>]` table is repo-namespaced and single-writer — only that plugin's own installer ever writes its table, so the table key already encodes the writer. The `[provenance]` convention (§5b case 3, §6) exists specifically for *multi-writer collision diagnosis* — disambiguating which automated writer set a key several installers can write (e.g. `[provenance.unreal]` on the shared `unreal.install_root`, seeded by more than one installer). It is **not** a universal stamp on every `registry.local.toml` write. A single-writer namespaced table has nothing to disambiguate, so a provenance stamp there is ceremony, not signal. Append-only writers that structurally preserve sibling tables (read → `tomllib`-parse-absent-check → append → atomic `os.replace`) satisfy the preserve-unrelated-tables property by construction and need no provenance. (Triggered by project-rag-em's question on `_register_plugin_mirror.py`.)

**Scope of this ruling — single-writer tables only.** This "no provenance stamp" ruling applies narrowly to **single-writer repo-namespaced tables like `plugin.mirrors.*`**, where the table key already encodes the sole writer. It does **NOT** exempt **multi-writer concern files** (§5b case 3 / §6): those genuinely have several writers contributing keys to one file (`unreal.local.toml` is co-written by project-rag-ue-addon and example-game-workbench-repo per its ownership map), so per-key `[provenance.<key>]` IS the collision-diagnosis signal and is required, not ceremony. The `machine-local set --concern` CLI writer (a third writer of concern keys) stamps `[provenance.<bare_key>]` for exactly this reason. (Clarified 2026-06-23 — the boundary case of a NEW writer joining an existing multi-writer concern file was unaddressed; prior-art-check on the concern-set-writer plan surfaced the gap.)

### Three modes, three structural shapes

| Mode | When to use | Drift probe behavior |
|---|---|---|
| Default (git-checkout-managed) | Live install is a separate git checkout; source changes must be explicitly propagated via `refresh-plugin-live-install.sh` | Checks git-state (commits-behind) and venv-state (editable pin, MAPPING integrity, console-script shims) |
| `propagation_mode = "source_is_live"` | Live install IS the canonical source (e.g., coordinator — both `source_path` and `live_path` point at the same directory; post-2026-07-04 cutover this is the DoE clone `<DoE>/coordinator/` resolved via `--plugin-dir`, not `~/.claude/`) | Emits `[n/a] propagation_mode=source_is_live` and skips all checks |
| `propagation_mode = "copy_install"` | Live install is a file-copy produced by a copy-based installer (e.g., the example-game-repo trio — `example-game-repo`, `example-game-repo-control`, `game-dev`); no git remote in the live path | SHA-sentinel drift class: compares `version.txt` (40-char SHA written by the installer) against `git -C <source_path> rev-parse HEAD`; no git fetch, no venv legs |

### `source_is_live` rationale

For the coordinator plugin, there is no "source → live" propagation step because `source_path` and `live_path` both resolve to the same directory. Registering this with `propagation_mode = "source_is_live"` communicates the structural distinction to the probe so it does not report false drift. **Post-2026-07-04 cutover:** coordinator's `source_is_live` directory is the DoE clone (`<DoE>/coordinator/`), resolved live via `--plugin-dir`; the registry entry's `source_path` and `live_path` both point there. Pre-cutover, this was `~/.claude/plugins/coordinator/` — edits in `~/.claude/` took effect immediately. Outward percolation (`install → publish-repo` via `publish.sh`) is a separate concern and unaffected by this entry. For the publish-direction contract (source → publish-repo, never write-back) and the 2026-05-20 ban on publish-repo → live-install clobber that motivates `source_is_live`, see `plugin-extraction-and-distribution.md:87` and `live-install-drift-audit.md:21`.

### `propagation_mode = "copy_install"`

<!-- spec-backlink: archive/specs/2026-05/2026-05-23-copy-install-drift-coverage.md § Chunk 1 -->

For plugins whose live install is produced by a copy-based installer (rather than a git
checkout), set `propagation_mode = "copy_install"`. The canonical example is the
`example-game-workbench-repo` trio (`example-game-repo`, `example-game-repo-control`, `game-dev`), installed via
`scripts/install-plugin.sh` from the example-game-repo source repo.

**Applicable fields.** `track_ref` and `dist_name` do not apply — no git remote is consulted and no venv editable-install is involved. The fields that apply are:

| Field | Required | Semantics |
|-------|----------|-----------|
| `source_path` | yes | Absolute path to the plugin source repo root (for `git rev-parse HEAD` + locating the installer) |
| `live_path` | yes | Absolute path to the live install directory (for reading `version.txt`) |
| `refresh_cmd` | no | Shell command run from `source_path` to reinstall. If absent, refresh prints the manual path and exits non-zero. |
| `source_subpath` | no | Relative path within `source_path` to the plugin tree (e.g. `plugin/example-game-repo-control`). Used by the content-equivalence fallback to scope `git ls-tree`. Default: `plugin/<plugin_name>` when absent. |

**SHA-sentinel drift class.** This is a distinct third drift class alongside git-state drift
and venv-state drift. The installer writes a 40-char source HEAD SHA to
`<live_path>/version.txt` at copy time. The probe detects drift by comparing:

```
version.txt  (live install at copy time)
    vs.
git -C <source_path> rev-parse HEAD  (currently-checked-out source HEAD — no fetch)
```

Using the local HEAD (not `origin/main`) avoids constant false-positive drift: these plugins
develop on `work/*` branches ahead of main.

**Refresh action.** `refresh-plugin-live-install.sh <plugin>` on a `copy_install` entry runs the
registry-supplied `refresh_cmd` from `source_path`, with a snapshot + REPLACE-semantics rollback
on failure. The git-state and venv-state legs are skipped entirely.

```bash
( cd <source_path> && bash -c "<refresh_cmd>" )    # e.g. bash scripts/install-control-plugin.sh --allow-standalone --no-enable
```

The coordinator does **not** hardcode `install-plugin.sh <plugin> --no-enable`: the example-game-repo trio
gates standalone component installs behind `EXAMPLE_GAME_REPO_UMBRELLA_INSTALL=1` (a bare component install
is *refused*), reachable only via the component forwarders' `--allow-standalone` passthrough — and
the docs/umbrella component has no forwarder. The correct invocation is installer-internal
knowledge, so it lives in `refresh_cmd` (operator/installer-supplied, same trust level as the paths
the script already executes against). `--no-enable` bypasses `enable_plugin.py` (the `settings.json`
lock). **If no `refresh_cmd` is registered, refresh prints the manual path (`/example-game-repo:install` or the
per-component forwarder) and exits non-zero — it never silently no-ops or guesses an invocation.**

**No-sentinel state.** If `version.txt` is absent, the probe emits `[info] no sentinel` and
exits 0 — this is honest degraded state, not drift. The sentinel is only written when
`requires_plugin_source_index: true` is set in the plugin manifest; for plugins without it,
`[info] no sentinel` is the expected output until the example-game-repo installer is updated (see
the example-game-repo repo's `cross-repo/2026-05-23-copy-install-drift.md` (example-game-repo pre-restructure root-level placement; will move to cross-repo/inbox/ on next migration) (asks tracked in `docs/plans/2026-05-23-copy-install-drift-coverage.md`)).

**Known limitation.** SHA-sentinel catches **committed drift only**. Uncommitted source edits
are invisible. Content-diff (the only alternative) is a false-positive machine because the
installer injects BOMs into `.ps1` files, copies the marketplace manifest, and strips
`.mcp.json`. The sentinel is the deliberate tradeoff.

**Registration example** (Striker, example-game-repo trio):

```bash
machine-local set plugin.mirrors.example-game-repo-control.propagation_mode copy_install
machine-local set plugin.mirrors.example-game-repo-control.source_path X:/example-game-workbench-repo
machine-local set plugin.mirrors.example-game-repo-control.live_path "$HOME/.claude/plugins/example-game-workbench-repo/example-game-repo-control"
machine-local set plugin.mirrors.example-game-repo-control.refresh_cmd 'bash scripts/install-control-plugin.sh --allow-standalone --no-enable'
# game-dev: same shape, refresh_cmd → install-game-dev-plugin.sh --allow-standalone --no-enable
# example-game-repo (docs, no forwarder): refresh_cmd → 'EXAMPLE_GAME_REPO_UMBRELLA_INSTALL=1 bash scripts/install-plugin.sh example-game-repo --no-enable'
```

For clean-install reproducibility on a fresh machine, installers should self-register these
entries at install time. See the example-game-repo repo's `cross-repo/2026-05-23-copy-install-drift.md` (example-game-repo pre-restructure root-level placement; will move to cross-repo/inbox/ on next migration) (asks tracked in `docs/plans/2026-05-23-copy-install-drift-coverage.md`)
for the memo requesting this from the example-game-repo installer.

### `reverse_drift_cmd` (reverse-drift merge gate)

`refresh_cmd` polices **forward** drift (source newer than live). `reverse_drift_cmd` polices the
opposite direction: a live install hand-edited *after* the last copy, which the forward-SHA probe
cannot see. It is the per-plugin command that digest-compares live against source and exits non-zero
on a hand-edit. Registered per `copy_install` plugin alongside `refresh_cmd`:

```bash
machine-local set plugin.mirrors.example-game-repo.reverse_drift_cmd 'bash bin/check-reverse-drift.sh'
```

**Invocation contract.** `/workweek-complete` Step 4g discovers registered commands via
`list-reverse-drift-cmds.sh` (which reads this registry from any cwd), then runs each from its
`source_path` — the same `( cd <source_path> && bash -c "<reverse_drift_cmd>" )` idiom as `refresh_cmd`.
Because the value is shell-evaluated once by `bash -c`, operators **MUST single-quote** the value in
`registry.local.toml` (the registration example above does). The reader is referenced by its
authoritative absolute path in Step 4g; a cwd-relative path would silently no-op when
`/workweek-complete` runs from the meta-repo cwd — the exact bug DR-146 fixed.

**Per-repo scoping (`--scope-repo`).** Step 4g passes the releasing repo's root
(`git rev-parse --show-toplevel`) as `--scope-repo`, so the gate is scoped to that repo, **not**
machine-global. The **meta-repo** (`${HOME}/.claude`, the coordinator home) is the explicit check-all
case — releasing it covers every `copy_install` plugin on the machine. Any **consumer repo** (project-rag,
example-sim-repo, example-repo, …) checks only `copy_install` plugins whose `source_path` IS that repo — usually
none, so a clean no-op. This prevents a consumer-repo release from gating on a *sibling* plugin's
live-install drift, which would violate the dependency-direction invariant (a host must never be forced
to sync with a consumer's state). Path forms are normalized before comparison (Windows `X:/` vs MSYS
`/x/` vs `$HOME`-derived `/c/`), so the meta-repo and `source_path` matches survive cross-platform path
representations. Omitting `--scope-repo` (direct callers, tests) retains the legacy emit-all behavior.
The scope filter runs **before** the `copy_install`-seen counter, so a consumer repo that legitimately
sources none of the registered plugins exits `0` (clean), not `3` (misconfig).

**Distinct from `refresh_cmd` on rollback.** `refresh_cmd` runs inside `refresh-plugin-live-install.sh`,
which wraps it with snapshot + REPLACE-semantics rollback (it *mutates* the live install). `reverse_drift_cmd`
is a **detection-only read** — it never mutates anything, so it is invoked bare in a loop with no
snapshot/rollback wrapper. Do not route `reverse_drift_cmd` through `refresh-plugin-live-install.sh`.
See the `refresh_cmd` contract above (`docs/wiki/machine-local-registry.md`, "Refresh action").

**Fail-loud, never silent.** The reader exits `3` when `copy_install` plugins are registered but none
carry a `reverse_drift_cmd` (the gate would be structurally blind) — Step 4g turns that into a blocking
failure with a registration hint. When no `copy_install` plugins exist at all, the gate is genuinely
N/A and passes cleanly (exit `0`, empty output). Detection logic itself remains example-game-repo-owned
(`X:/example-game-workbench-repo/bin/check-reverse-drift.sh`); the coordinator only routes to it via this field.

### `track_ref` lifecycle

**`track_ref` lifecycle.** Register against `origin/main` by default. Pin to a workbranch (e.g. `origin/work/<machine>/<date>`) only during active rollout, and flip back to `origin/main` at merge — otherwise the drift probe goes silent (when the workbranch is deleted post-merge) or errors. Plugin authors with separate-checkout-style live installs (project-rag, project-rag-ue-addon, future plugins) should set this field as part of registration; the drift probe (`check-plugin-drift.sh`) reads it.

### Idempotent registration

`/coordinator:install` Phase 3 Step 5 writes the `[plugin.mirrors.coordinator-claude]` entry to `registry.local.toml` on first run. Re-running `/setup` is idempotent — it checks for the section header before appending. Values set here follow the `registry.local.toml` gitignore convention (§9): the structural shape is declared in `registry.toml`; the machine-specific `live_path` goes in `registry.local.toml`.

### TOML flat-key table-scoping gotcha

Flat keys appended *after* a `[table]` header are scoped to that table, not the document root. `tomllib.loads()` (what the `machine-local` reader uses) scopes them correctly — so a key written after `[plugin.mirrors.coordinator-claude]` resolves as `plugin.mirrors.coordinator-claude."unreal.install_root"`, NOT as a top-level `unreal.install_root`. A naïve append to the end of the file lands the key inside whatever table happens to be last.

**Insert flat quoted keys BEFORE the first `[table]` header** (e.g. via a `_first_table_header_line()` helper); `[header]`-shaped blocks like `[provenance.unreal]` go at the end since they open their own table. **Verify by reader lookup, not text-search:** `machine-local get unreal.install_root` confirms the key resolves at the intended scope — a text-grep of the file passes even when the reader lookup fails because the key is mis-scoped.

## Verifying Registry Health

These are the coordinator-doctor.md §3 probes P-1 through P-4. Paste them in a shell for a quick sanity check; consult [`coordinator-doctor.md`](coordinator-doctor.md) for the full structured diagnostic experience (including remediation steps for each failure mode).

```bash
# Quick verify (paste in shell):
test -d "$(machine-local dir)"                          # P-1 — settings-home machine-local exists
machine-local has schema                                # P-4 — reader works + schema declared
machine-local get repos.project_rag                     # P-3 — sample working-repo key resolves
```

**Settings-home path form (post-relocation):** `machine-local dir` resolves the current settings-home `machine-local/` directory (§4e). The legacy absolute-path probes (`~/.claude/bin/machine-local …`) continue to work during the transitional compat window because `~/.claude/bin/machine-local` is a retained-and-repointed forwarder that execs the settings-home resolver.

Note: the P-3 probe previously used `repos.coordinator_claude`, which is no longer a `repos.*` key (it moved to `publish.mirrors.coordinator_claude.path` as of 2026-06-30). The sample probe above uses `repos.project_rag` as a stable working-repo key. See `coordinator-doctor.md` for the full probe narrative and current remediation steps.

Bare `machine-local …` invocation works on POSIX because a forwarder shim ships in the harness-injected coordinator bin for both `machine-local` and `claude-home` (`plugins/coordinator/bin/{machine-local,claude-home}`) — see `docs/plans/2026-06-18-machine-local-bare-invocation-macos.md`; during the compat window, `~/.claude/bin/machine-local` also works as a retained-and-repointed compat forwarder.
<!-- review: code-reviewer slice2-F3 — extended to name both resolvers; workstream shipped forwarders for machine-local AND claude-home -->

If any probe fails, coordinator-doctor.md §3 has the remediation steps.

## Untracking a machine-specific value from a shared tracked file — multi-consumer + co-writer sweep

Moving a machine-specific value OUT of a shared tracked file and INTO the `.local` layer (or a per-machine registry key) is not a one-line edit — it is a **multi-consumer + co-writer sweep**. Before the move:

1. **Grep all readers** of the value across every consumer (tools, scripts, hooks, sibling repos) — each must resolve from the new location or carry a fallback.
2. **Grep all writers / co-writers** — any installer, daemon, or ceremony that *writes* the old location must be repointed too, or it silently re-introduces the machine-specific value into the tracked file on its next run.
3. **Check install order for clobber** — if a later install step rewrites the tracked file, the untrack is undone; sequence the writers so the `.local` move is durable.
4. **Merging-reader transparency** — a reader that merges the tracked baseline with `.local` overrides must surface which layer won, so a stale tracked value can't silently shadow the per-machine one.

(Source: 2026-06-17, project-rag.) Composes with §9 (tracked baseline + `.local` overrides) and `install-surface-completeness.md § settings.json portability` (the same tracked-union + local-override shape for harness-managed config).

## Browser-spawned interpreter runtimes — embed `sys.executable`, not a bare name

**Browser-spawned interpreted runtimes (Chrome/Chromium native-messaging hosts, and any browser-launched interpreter) must embed `sys.executable` in the launcher — the browser strips PATH, so a `python3`-on-PATH shim silently fails to launch.**

The native-host manifest's `path` field (the launch command) must be an absolute interpreter path captured via `sys.executable` at install time. A bare `python3` that resolves correctly in a normal shell session resolves to nothing inside a browser-spawned child because browsers do not inherit the user's shell PATH. Apply to any process launched by a browser extension or native-messaging registration; the rule is not Chrome-specific — any sandboxed launcher that strips PATH has the same shape.

How to apply: at install time, write the manifest's interpreter field as `sys.executable` (Python), the `node` binary resolved via an absolute `which`/`command -v` probe, or the result of `shutil.which` filtered for WindowsApps stubs (see § Python resolver above). Never hard-code `/usr/bin/python3` (absent on many macOS), `python3` (PATH-relative, fails in stripped env), or `python` (absent on modern Linux/macOS). Validate post-install by launching the host directly from its registered manifest path, not from your shell.

*Empirical origin: queue 2026-06-08, example-league-data-repo — native-messaging host manifest used bare `python3`; Chrome spawned it with a stripped PATH, process failed to start silently. Same class as the python3-on-Windows WindowsApps-stub failure (§ Python resolver); the fix shape is identical: absolute path captured at install time.*

## 13. Regeneratability Classification

<!-- spec-backlink: archive/specs/2026-06/2026-06-22-invariant-verification-observers.md § C1 (Flag 3) -->

Every coordinator-owned registry key is classified by its **regeneratability** — the answer to: *if this value is lost (e.g., a fresh-machine clone, a crash, or a gitignored file not restored), can it be recovered without losing work?*

### Three-value enum

| Value | Definition |
|---|---|
| `idempotent-regeneratable` | The value can be re-derived by running an idempotent script or installer step with no human input and no state loss. Example: `coordinator.python` is rewritten by `bin/ensure-coordinator-venv.sh`. |
| `session-accumulated-must-survive-crash` | The value is set by the operator or an install step and cannot be regenerated from code alone — it encodes the operator's machine layout. Loss requires the operator to re-enter the path manually on each machine. |
| `ephemeral` | The value is transient or can be ignored on loss; it is not needed for correct operation after a restart. |

### Canonical home — `[regeneratability]` TOML table

Classification lives in a real `[regeneratability]` TOML section in `registry.toml` (tracked). This is the **machine-readable form** consumed by `bin/check-machine-local-regeneratability.sh`. Do NOT use inline `# regeneratability:` comments — `tomllib` discards comments on load and they cannot be surfaced by the `machine-local` CLI.

```toml
[regeneratability]
"coordinator.python"       = "idempotent-regeneratable"
"repos.project_rag"        = "idempotent-regeneratable"
"publish.targets"          = "ephemeral"
```
<!-- Review: code-reviewer Slice-C — F1: repos.* reclassified to idempotent-regeneratable (rung-2 autodiscovery); F2: publish.targets reconciled to ephemeral to match registry.toml:172-173. -->

See `templates/machine-local/registry.toml.example` § `[regeneratability]` for the full classification table with all coordinator-owned keys.

### Classification of all coordinator-owned keys

| Key | Regeneratability | Rationale |
|---|---|---|
| `coordinator.python` | `idempotent-regeneratable` | Rewritten by `bin/ensure-coordinator-venv.sh` whenever the coordinator venv is rebuilt. See §5c. |
| `plugin.mirrors.*` | `idempotent-regeneratable` | Mirror registrations are written by each plugin's installer; re-running the installer restores them. |
| `publish.targets` | `ephemeral` | Absent until explicitly configured; falls through to `setup/publish-targets.portable` when unset. Publish DEST roots resolve via `publish.mirrors.*.path`, not `repos.*`. |
| `publish.mirrors.coordinator_claude.path` | `session-accumulated-must-survive-crash` | Per-machine path set by the operator; no installer re-derives it. Resolves the coordinator-claude publish DEST root for the portable topology. Provision: `machine-local set publish.mirrors.coordinator_claude.path /abs/path`. |
| `publish.mirrors.deep_research_claude.path` | `session-accumulated-must-survive-crash` | Per-machine path set by the operator; no installer re-derives it. Resolves the deep-research-claude publish DEST root for the portable topology. Provision: `machine-local set publish.mirrors.deep_research_claude.path /abs/path`. |
| `repos.example-sim-repo` | `idempotent-regeneratable` | Derived at runtime by rung-2 marker autodiscovery via `search-roots.toml` for convention-installed repos; rung-4 `registry.local.toml` is the fallback for off-convention repos. |
| `repos.project_rag` | `idempotent-regeneratable` | Derived at runtime by rung-2 marker autodiscovery via `search-roots.toml` for convention-installed repos; rung-4 `registry.local.toml` is the fallback for off-convention repos. |
| `repos.project_rag_ue_addon` | `idempotent-regeneratable` | Derived at runtime by rung-2 marker autodiscovery via `search-roots.toml` for convention-installed repos; rung-4 `registry.local.toml` is the fallback for off-convention repos. |
| `repos.example_game_workbench_repo` | `idempotent-regeneratable` | Derived at runtime by rung-2 marker autodiscovery via `search-roots.toml` for convention-installed repos; rung-4 `registry.local.toml` is the fallback for off-convention repos. |
| `repos.example_repo` | `idempotent-regeneratable` | Derived at runtime by rung-2 marker autodiscovery via `search-roots.toml` for convention-installed repos; rung-4 `registry.local.toml` is the fallback for off-convention repos. |
| `repos.example_stats_repo` | `idempotent-regeneratable` | Derived at runtime by rung-2 marker autodiscovery via `search-roots.toml` for convention-installed repos; rung-4 `registry.local.toml` is the fallback for off-convention repos. |
| `repos.example_league_data_repo` | `idempotent-regeneratable` | Derived at runtime by rung-2 marker autodiscovery via `search-roots.toml` for convention-installed repos; rung-4 `registry.local.toml` is the fallback for off-convention repos. |
| `repos.experiments` | `idempotent-regeneratable` | Derived at runtime by rung-2 marker autodiscovery via `search-roots.toml` for convention-installed repos; rung-4 `registry.local.toml` is the fallback for off-convention repos. |
| `repos.example_cockpit_repo` | `idempotent-regeneratable` | Derived at runtime by rung-2 marker autodiscovery via `search-roots.toml` for convention-installed repos; rung-4 `registry.local.toml` is the fallback for off-convention repos. |
| `repos.example-os-repo` | `idempotent-regeneratable` | Derived at runtime by rung-2 marker autodiscovery via `search-roots.toml` for convention-installed repos; rung-4 `registry.local.toml` is the fallback for off-convention repos. |
| `test.xdist_workers` | `idempotent-regeneratable` | Fast-tier pytest-xdist worker cap; computed count passed as `-n <N>` at invocation. Default formula: `max(1, floor(cores*0.5))`. Per-repo convention key — no coordinator infrastructure writes this; repos read it at invocation to cap parallelism on shared concurrent-EM boxes. → `docs/wiki/test-design-discipline.md § Posture: Proportional Test-Running`. |

### `repos.*` regeneratability — common case vs. rung-4 fallback

`repos.*` working-repo paths are `idempotent-regeneratable` for convention-installed repos: rung-2 marker autodiscovery derives the path at runtime from `search-roots.toml` — no absolute path stored in `registry.local.toml`. Off-convention repos that are not discoverable under any search-root or path-exception fall through to the rung-4 `registry.local.toml` fallback (`session-accumulated-must-survive-crash`), requiring manual `machine-local set repos.<slug>` entry per machine. `publish.mirrors.*.path` mirror values are always `session-accumulated-must-survive-crash` — there is no autodiscovery mechanism for publish-target DEST roots. They live in `registry.local.toml` (gitignored per §9).

**The 4-rung ladder (§4c, SSOT: `project-rag/docs/wiki/cross-machine-path-resolution-contract.md`) closes the common-case Bootstrap gap for convention-installed repos.** Rung 2 (marker autodiscovery) derives `repos.<slug>` at runtime from the tracked `search-roots.toml` and the repo's `.claude-plugin/marketplace.json` identity marker — no absolute path is stored in `registry.local.toml`. A fresh-machine clone of `~/.claude` with a correctly configured `search-roots.toml` resolves all convention-installed repos through rung 2 without any manual `machine-local set` invocation.

Manual `machine-local set repos.<slug> /abs/path` (rung 4) is the last-resort fallback for repos that are genuinely off-convention (not discoverable under any `search-roots.toml` entry) and also absent from the tracked exceptions table (`path-exceptions.toml`, rung 3). This is the uncommon case, not the default.

For publish mirror paths, `machine-local set publish.mirrors.<key>.path /abs/path` remains a manual step — there is no autodiscovery mechanism for publish-target DEST roots.

The Bootstrap gap for *off-convention repos* (those requiring an operator-supplied absolute rung-4 path) remains open. A generative installer that interactively configures `search-roots.toml` for new operators is the longer-term fix — tracked in `docs/wiki/install-surface-completeness.md` § Bootstrap gap.

The regeneratability check (`bin/check-machine-local-regeneratability.sh`, Step 2.95 sub-check) flags `session-accumulated-must-survive-crash` keys without a tracked baseline declaration. The remediation it offers:

```bash
machine-local set --global "<key>" ""   # adds tracked baseline declaration
# then document the manual population step in your machine's setup notes
```

## 14. New-machine landing sequence

When `~/.claude` is git-cloned onto a fresh machine, the machine-local substrate does not exist, the coordinator venv is absent, and per-machine state (`settings.local.json`, `known_marketplaces.json`, `registry.local.toml`, `.coordinator-venv/`) has not been regenerated. This section documents the end-to-end landing sequence.

### Step 1 — Clone

```bash
git clone <your-~/.claude-remote> ~/.claude
```

Nothing else exists yet. The machine-local registry directory, the coordinator venv, and all gitignored per-machine files are absent by design (§9).

### Step 2 — Run `bin/first-run.sh`

```bash
bash bin/first-run.sh          # interactive, preview-then-confirm
bash bin/first-run.sh --plan   # dry-run: print what would happen, no mutation
```

`bin/first-run.sh` is the **plugin-independent first-run entrypoint** that solves the bootstrap paradox: `/coordinator:install` is itself an unregistered plugin on a fresh clone — it cannot load before the coordinator plugin is registered. Similarly, `scripts/setup.sh` hard-exits on bash < 4 and stock macOS ships bash 3.2. `bin/first-run.sh` is a thin wrapper at the meta-repo root that locates and execs `plugins/coordinator/scripts/first-run.sh`; callers always invoke it as `bash bin/first-run.sh` from `~/.claude` regardless of how the repo was cloned.

**What first-run.sh does:**

1. **Toolchain detection.** Probes for bash ≥ 4.3, Homebrew, Python, Node, uv, and git-lfs. Reports gaps.
2. **Preview-then-confirm.** Prints a summary of what it will install; the operator confirms before any mutation. `--plan` exits at this point.
3. **Homebrew + bash ≥ 4.3.** Offers to install Homebrew if absent; installs bash ≥ 4.3 via Homebrew on macOS. Re-execs itself under the newly installed bash so the rest of the script runs with bash-4 features available.
4. **Python, Node, uv, git-lfs.** Offers each missing toolchain component; installs on confirmation.
5. **Machine-local registry seed.** Creates `machine-local/` and seeds it with `registry.toml` defaults so the `machine-local` CLI works.
6. **Per-machine state regeneration.** Runs in order:
   - `lib/install-substrate.sh` — lays down `machine-local/`, installs `bin/` resolver shims (`machine-local`, `claude-home`).
   - `bin/ensure-coordinator-venv.sh` — creates the coordinator venv at `~/.claude/.coordinator-venv/` and writes the `coordinator.python` registry key (§5c).
   - `bin/platform-localize.sh` — generates platform-specific state (`settings.local.json`, `known_marketplaces.json`).
7. **`git lfs install`.** Installs git-lfs hooks into this clone.

After `first-run.sh` completes, the machine-local substrate is populated and all regeneratable state (§13) has been re-derived.

### Step 3 — One `/reload-plugins` in Claude Code (NOT a full restart)

Open Claude Code (or the already-running session) and run:

```
/reload-plugins
```

This activates the freshly-cloned coordinator plugin for the current session. A full Claude Code restart is **not** required for plugin activation alone. There is a one-reload lag that is inherent to Claude Code's plugin lifecycle: a `SessionStart` hook fires when the session opens, before any plugins are registered — it cannot register into the already-running session. `/reload-plugins` is the correct repair, not a workaround.

After the reload, run `/coordinator:install` for the full install sequence (operator-identity capture, MCP wiring, skill registration, etc.).

### Why this regenerates rather than tracks

Per-machine state (`settings.local.json`, `known_marketplaces.json`, `registry.local.toml`, `.coordinator-venv/`) is **gitignored by design** (§9). These files contain machine-specific paths, platform-specific config, and environment-derived values that are wrong on every other machine. The correct fix for new-machine landing is **reliable regeneration on arrival** (the sequence above) plus a **machine-path guard** (values resolved through `machine-local get <key>` rather than hardcoded) — NOT tracking machine state in git. Tracking machine-specific values into git is the §8(f) and §9 anti-pattern; the §13 `session-accumulated-must-survive-crash` classification documents the one class of value (operator-set `repos.*` paths) that genuinely requires manual re-entry per machine.

**PERCOLATION NOTE:** `bin/first-run.sh` and its canonical implementation (`scripts/first-run.sh`) ship to the OSS coordinator-claude publish repo via `setup/publish.sh`. OSS users hit the same bootstrap paradox on a fresh clone and the same script solves it.

## 15. Operator-Identity Surface Completeness Sweep

<!-- spec-backlink: coordinator/templates/settings-manifest.md § Device-Singular vs. OSS-Canonical Discriminator -->
<!-- PM directive: 2026-07-07 — enumerate all on-device operator-identity surfaces and their disposition -->

This section is a **provably complete enumeration** of on-device operator-identity surfaces and their disposition against the device-singular vs. OSS-canonical discriminator (see `coordinator/templates/settings-manifest.md § Device-Singular vs. OSS-Canonical Discriminator`). Its job is to ensure no operator-identity surface is silently left hardcoded in committed source.

**Discriminator reminder.** Device-singular operator identity (values unique to one operator/device) → `registry.local.toml`, operator-set, fail-loud-on-unset. OSS-canonical project constants (values identical for every operator) → committed source; moving them breaks publish.

| Surface | Current location | Disposition | Notes |
|---|---|---|---|
| OwnerNamespace GitHub orgs | `owner-namespaces.ts` (deleted; formerly committed source) | **RETIRED — owner is now a validated string; no namespace enum, no registry key.** | Superseded 2026-07-07 (cockpit-contract DECISIONS D-new, supersedes D12): `owner` was reshaped from a closed enum to a validated string (`z.string().min(1)`), eliminating the namespace-enum seam entirely — `owner-namespaces.ts`, `test/owner-seam.test.ts`, and `test/owner-emit-example.sh` were deleted. There is no owner-namespace set to configure, so `cockpit.owner_namespaces` was removed from `machine-local` rather than relocated. |
| Meta-repo slug | `.claude-prime` sentinel / `emit-cockpit-snapshot.sh` (hardcoded) | **MOVED → `cockpit.meta_repo_slug`** (this workstream) | Device-singular: the operator's `owner/repo` meta-repo slug differs per operator. Committed source personalized the OSS artifact. Now resolved via `machine-local get cockpit.meta_repo_slug` with cold-safe fail-loud. |
| `COORDINATOR_PUBLISH_OWNER` / `dbc-oduffy/coordinator-claude` publish destination | Committed source | **STAYS in committed source** | OSS-canonical project constant: the canonical publish destination for the coordinator-claude OSS repo is the same for every operator running the official coordinator. Moving it to `registry.local.toml` would break publish for fresh-install operators who haven't set the key. This is NOT device-singular. |
| `working-repos.yaml` (`$ROOT/working-repos.yaml`, consumed by `emit-cockpit-snapshot.sh:~1438`) | On-disk UNTRACKED config file listing the operator's fleet repo slugs | **CANDIDATE for settings-home relocation — FOLLOW-UP** | The fleet-owner identity is DERIVED via slug-split, not hardcoded. The file itself is already untracked, so it does not personalize committed source in the same way as the MOVED surfaces above. However, its placement outside the settings home (`~/.coordinator-claude-settings/`) is inconsistent with the on-device substrate doctrine (§4e). Relocation to `<settings-home>/working-repos.yaml` or representation as a `cockpit.*` registry key is a candidate follow-up, but is NOT this workstream's live case. Listed here so the sweep is provably complete rather than silently partial. |

**Sweep completeness claim.** As of 2026-07-07, the four rows above cover all known operator-identity surfaces in the cockpit emission path. Any new surface discovered must be added here in the same commit that reclassifies it — the table is the audit artifact.

## Related Wikis

- `docs/wiki/plugin-identity-and-health-sentinels.md` — companion doctrine; defines operator-set configuration and the decay-discipline boundary. The 2026-05-19 Scope narrowing amendment is the joint anchor between that wiki and this one.
- `docs/wiki/dual-identity-module-hazard.md` — why the reader contract is shell-out, not import.
- `docs/wiki/plugin-extraction-and-distribution.md` — port-time cleanup contract (§ 11); sibling-layout is unchanged for extraction, machine-local is the runtime preference.
- `docs/wiki/cross-repo-citation-conventions.md` — sibling-layout convention and peerless-installs; `MACHINE_LOCAL_<KEY>` is the named successor to the ad-hoc per-repo env-var opt-in (e.g., `EXAMPLE_GAME_REPO_ROOT=`).
- `docs/wiki/doe-altitude-and-shared-infra.md` — the PM-facilitated DoE consult methodology that produced the design plan for this registry.
- `docs/wiki/cross-repo-communication.md` — PM-relay reply-memo pattern used when the DoE reply memo (Task 6 of the design plan) was dispatched to the bilateral EMs.
