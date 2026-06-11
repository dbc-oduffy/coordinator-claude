# Machine-local Registry

<!-- spec-backlink: docs/plans/2026-05-19-machine-local-registry.md § 5 -->

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
| Proposed `addon-resolvers/<addon>.py` | holodeck (proposal) | Wrong scope dimension (per-addon, not per-machine); dual-identity hazard |
| Distributed env-var sprawl | holodeck | ~9 cross-machine env vars + 5 orthogonal doctor precedence chains |

The registry is the single audited place all of these needed to be. The anti-pattern each represents is still alive; if you see a new `~/.<tool>/config.toml` or a per-repo `TOOL_ROOT=` env var being invented, that is the reinvention detector firing.

## 2. When to Put a Value in Machine-local vs. Discover at Runtime

The discriminator is **stability and source of truth**:

| Value type | Belongs in | Rationale |
|---|---|---|
| Stable per-machine path (sibling repo root, vendor SDK install dir) | `machine-local/registry.toml` or `.local.toml` | Set once by the operator; no live source; persistence is correct |
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

The reader (`machine-local get <key>`) resolves in this order, most-specific-and-most-local first:

```
1. <concern>.local.toml (most specific + per-machine)
2. <concern>.toml (most specific shared)
3. registry.local.toml (per-machine)
4. registry.toml (shared baseline)
5. MACHINE_LOCAL_<KEY> env override (intentional one-off escape — NOT highest precedence; env-vars are ambient, registry is deliberate)
6. --default (if provided)
7. exit 1
```

Layers 1–4 are all `.toml` files and all outrank the env layer. The env layer (5) sits below all `.toml` layers because env-vars in a parent process are *ambient*, not deliberate — any export in a parent shell, IDE launch configuration, `.envrc`, or CI step would silently shadow the operator's registry values if env ranked above them. The registry's authority comes precisely from being the audited, operator-set source. The env var is an emergency one-off escape valve, not the default channel.

**`MACHINE_LOCAL_<KEY>` naming.** The key `repos.claude_unreal_holodeck` maps to env var `MACHINE_LOCAL_REPOS_CLAUDE_UNREAL_HOLODECK` (dots and hyphens become underscores, all uppercase). This is the named successor to the ad-hoc per-repo env-var opt-in pattern — for example, the `HOLODECK_REPO_ROOT=` pattern documented in `docs/wiki/cross-repo-citation-conventions.md § peerless-installs`. That pattern was the right local answer at the time; machine-local unifies all such ad-hoc env vars under one named registry with a documented fallback chain.

**Short shell-out examples:**

```bash
# Resolve a sibling-repo root; fail loud if not set
repo=$(machine-local get repos.claude_unreal_holodeck)

# Resolve with a sibling-relative fallback (belt-and-suspenders pattern)
repo=$(machine-local get repos.claude_unreal_holodeck --default "$(cd "$(dirname "$0")/../claude-unreal-holodeck" && pwd)")
```

Consumers that want the full resolution chain (registry → sibling-relative → error with remediation) compose it themselves using `--default` or by checking the exit code of `machine-local has <key>` before the fallback.

## 4a. `CLAUDE_HOME` — canonical escape hatch for `~/.claude` path resolution

The machine-local registry resolves *values* with a documented precedence chain (§4). The companion question — *where does `~/.claude` itself live?* — has the same shape and is formalized here as cross-repo doctrine so peer plans (project-rag F11, holodeck, deep-research, future Python/TS/Rust consumers) adopt one convention instead of inventing N variants.

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
ml_dir=$(claude-home machine-local)
plugins_dir=$(claude-home plugins)
```

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

**What this unblocks.** Peer plans previously deferred the CLAUDE_HOME pattern as "host-side only, not cross-repo doctrine" (e.g., holodeck's review of project-rag F11). With §4a formalized, `claude-home` installed by coordinator setup, and the JSON I/O primitives shipped alongside, the pattern IS coordinator doctrine with a first-class resolver. Peer repos adopt by shelling out to `claude-home {home|path|dir|machine-local|plugins}` or importing the Python helpers — no precedence chain re-derivation, no duplicate test surface to maintain.

**Out of scope.** `CLAUDE_HOME` resolves *where the directory lives*, not *what is inside it*. Values inside (sibling-repo roots, vendor SDK paths, etc.) continue to resolve through the machine-local registry chain (§4). The two chains are orthogonal and compose cleanly: `CLAUDE_HOME` selects which `~/.claude/machine-local/registry.toml` the reader opens; the reader's own precedence chain then resolves keys within it.

**Bootstrap-lookup vs. contents-resolution — DO NOT conflate.** A peer repo importing the central `_claude_home.py` module hits two distinct $HOME-resolution surfaces with opposite precedence rules. The mistake is using `CLAUDE_HOME` for both; the failure mode is silent test-sandbox bypass of the central path.

| Surface | What it answers | Precedence |
|---|---|---|
| **Bootstrap lookup** | Where does `_claude_home.py` LIVE on disk? | `HOME` → `USERPROFILE` → `Path.home()`. **NOT `CLAUDE_HOME`.** |
| **Contents resolution** | What paths does the module's API return (`~/.claude.json`, `~/.claude/`, etc.)? | Full chain: `CLAUDE_HOME` → `HOME` → `USERPROFILE` → `Path.home()`. |

Why: `/coordinator:install` installs `_claude_home.py` at the operator's REAL `$HOME/.claude/bin/`, never at `CLAUDE_HOME/.claude/bin/`. A test setting `CLAUDE_HOME=/tmp/sandbox` to redirect contents resolution will find no module at `/tmp/sandbox/.claude/bin/`, the import fails, the peer falls back to its inlined copy, and the central path is never exercised under CI. The bug is invisible until production drift between the two copies surfaces.

Reference adoption shape: `coordinator/lib/claude-home/README.md § "Adopting from a peer repo"` carries the canonical Python snippet for the bootstrap-lookup half. Peer repos retiring inlined `_claude_config.py`-shaped modules MUST use the real-`$HOME`-only chain for the bootstrap import and let the central module own the full-precedence chain for everything it returns.

## 5. Relationship to `plugin-extraction-and-distribution.md` and `cross-repo-citation-conventions.md`

These two wikis define the **port-time cleanup contract** for the coordinator install chain: when extracting a plugin or porting vendored code, sweep absolute paths and replace them with sibling-relative references (`../<sibling-repo>/<path>`). That contract is **unchanged by this wiki** — at port time, the consumer does not yet exist to be told about machine-local. Sibling-relative is the correct vocabulary for the extraction step.

What this wiki establishes is the **runtime discovery preference order** for consumers that already exist and need to find a sibling repo or vendor root at execution time:

1. **Machine-local registry first** (`machine-local get repos.<name>`). Works in every case: triangular dependency graphs, multi-drive layouts, deterministic-location requirements, daemon-invoked scripts, vendored scripts invoked from another repo.
2. **Sibling-relative fallback** (`../<sibling-repo>/`). Rough-and-ready resort when machine-local is not populated and the operator's filesystem happens to match the sibling-installs-together convention. Backward compatible.
3. **Error with remediation hint** — point the operator at `~/.claude/machine-local/README.md` and the key they need to set.

This is **belt-and-suspenders, not co-equal**. Registry is the preferred primary because sibling-relative alone fails in four cases: (a) it dictates operator filesystem layout; (b) it cannot represent deterministic locations (vendor binaries on a specific drive); (c) it fails opaquely with no remediation hint; (d) it does not compose with triangular dependency graphs where moving any one vertex breaks every sibling-relative inside the moved repo.

Port-time cleanup uses sibling-relatives because that is still better than absolute paths leaking into shipped code. Runtime discovery prefers machine-local because the operator has a stable location to declare their actual layout. Cross-link: `docs/wiki/plugin-extraction-and-distribution.md § 11`, `docs/wiki/cross-repo-citation-conventions.md § Sibling-layout convention`.

## 5a. Schema-Authorship vs. Value-Writing — Who Owns What

A recurring failure mode (observed across multiple EM sessions, 2026-05) is reading "the coordinator owns the registry" as "EMs other than the coordinator team should not write here," then sidecarring `~/.<tool>/config.toml` to avoid the perceived gate. That is the opposite of the design intent. Two distinct authorities are at play; conflating them is the bug:

- **Schema authorship** (coordinator-team responsibility). The shape of shared keys (`repos.*`, `install.*`, `plugin.mirrors.*`), the resolution order (§4), the reader contract (§7), and the helper surface (`machine-local`, `claude-machine-local.sh/ps1`, the Python module) are coordinator-governed because every consumer depends on them. Changing the reader contract, renaming a shared namespace, or adding a tracked baseline key requires coordinator-team coherence.

- **Value writing** (anyone on the machine). Appending values under existing namespaces, opening a new tool-specific namespace (`mything.*`), or hand-editing per-machine paths in `registry.local.toml` does NOT require coordinator-team sign-off. The reader is schemaless by design — no per-key validation, no declaration step (§7). The registry's whole value proposition is being the convenient shared place that prevents per-tool sidecars from accreting; gatekeeping value-writes would defeat the substrate.

The library/service distinction is useful here: this is a **library**, not a **service**. The coordinator ships the schema and helpers; callers freely write values under the schema. Treating it service-shaped (writes mediated by the coordinator team) is the misread §5b exists to correct.

## 5b. Adding a Value or Namespace — The Cheap Path Is the Default

Four shapes, only one is heavyweight:

1. **Per-machine path that varies across your machines.** Append a key to `registry.local.toml`. No declaration step required. The reader is schemaless; declaring an empty placeholder in tracked `registry.toml` is *optional* and only useful if you want the key shape to be discoverable across machines via git.
2. **New namespace cluster you own** (`mything.*`, `mytool.*`). Just use it. The `concerns` array (§6) gates *concern-file isolation* (whether `mything.*` reads from a separate `mything.toml`), not *namespace existence*. A new namespace under `registry.local.toml` needs zero registration.
3. **Sanctioned auto-writer** (your installer or daemon writes values, not just reads them). Heavier — §6's machine-generated-write-authority criterion applies, with single registered writer, declared sources, loud-fail on collision, and a `[provenance]` table. Worked example on disk: `project_rag.toml`. This is the only path that warrants the heavier criteria; it is heavy because *unsupervised writers* need clobber-discipline, not because *humans/EMs adding values* do. **Concern-file provenance shape:** the `[provenance]` block lives at the concern-file root (not `[provenance.<concern>]`) because the concern name is already the file's namespace; provenance uses per-key sub-tables (e.g., `[provenance.install_root]`) to support multi-writer collision diagnosis when more than one automated writer contributes keys to the same concern file.
4. **Hand-edited cross-machine value** (same on every machine — schema version, a public URL). Append to `registry.toml`. It travels via git.

If you find yourself reading the wiki to figure out whether you "may" add a value — the answer is yes, cases 1, 2, and 4 are the default and need no authorization. Case 3 is the only one with criteria, and the criteria gate *automated writer patterns*, not human authorship.

## 6. Concern-file Convention

Most values belong in the core `registry.toml`. A concern file (`unreal.toml`, `cuda.toml`) is warranted only when a surface meets at least one of:

- More than five keys for that namespace, OR
- Version-multiplexed values (e.g., Unreal 5.4, 5.5, 5.6 each with their own install root), OR
- **Machine-generated write authority** — the file is written by an automated process from declared sources (e.g., `cli.py wire` aggregating each installed addon's `CorpusBand.required_env` declarations), not hand-edited by the operator. Concern-file isolation here is doing different work from the count/version criteria: it separates machine-generated content from operator-edited config so the automated writer's clobber radius can never touch operator-set values, and so the file's `[provenance]` attribution stays co-located with the keys it describes. The criterion gates on the **writer pattern** (registered automated aggregator from declared sources), not on key count or addon presence — a hypothetical addon whose two keys are hand-edited by the operator still belongs in `registry.local.toml`. Worked example: `project_rag.toml` (2 keys, unversioned, but written exclusively by `cli.py wire` from each installed addon's declared sources; loud-fail on cross-addon key collision; `[provenance]` table records addon→key attribution that the predecessor `wiring.env` lost). Hand-editing a `wire`-managed key would be silently clobbered on the next addon install — the operator's leverage is via the source declarations, not the concern file.

When a concern file is listed in `registry.toml`'s `concerns` array, that concern's namespace (`unreal.*`, `cuda.*`) is **resolved exclusively from the concern file**. Keys with that prefix in `registry.toml` are ignored and emit a warning — the concern file wins. Put `unreal.*` keys EITHER in the core registry OR in `unreal.toml`, never both. This is a read-resolution rule (avoids silent shadowing for operators), not an ownership/permission rule — see §5a for the schema-authorship-vs-value-writing distinction.

**Extension path (per the Director of Engineering review, F7).** If a future need for per-repo metadata (kind, role, version, consumer-set) emerges, the extension path is a new concern file (e.g., `repos_meta.toml`), not restructuring the flat `repos.*` namespace. The flat namespace is correct for the current consumer set (sibling-repo roots are strings, not structured objects). YAGNI: add the concern file if and when the need is concrete; this note just records that the extension path exists so a future contributor does not feel forced to restructure the baseline.

**When the "wait for instance #3" rule applies vs. when it doesn't.** Per `docs/wiki/ceremony-calibration.md`, conventions wait for the third instance before being extracted into a shared abstraction — single instances of a pattern are routinely premature to generalize. The machine-local registry itself appears to break that rule (four EM reinventions surfaced in the triggering plan's §1.2). It does not, because the rule's exception is precisely the case it surfaced: the rule prevents premature abstraction when you have *one* instance and might invent a *second* speculatively; it does NOT prevent abstraction when you already have *N≥2* instances and one of them is in active wrong-shape arrangement because the abstraction never existed. The four-reinvention pattern + the wrong-shape `wiring.env`-style accumulation was the empirical signal; the rule held perfectly. Document this distinction when proposing similar substrate-gap-driven extractions.

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

**(c) Adding a value that varies per-project.** Per-project state (project root, project type, enabled plugins, skill overrides) belongs in the project's `.claude/` config, not in machine-local. Machine-local is scoped to the machine, not the project; a value that changes when you switch projects is not per-machine.

**(d) Adding a value that varies per-runtime-invocation.** Values that change with each tool invocation — current binding, active corpus, daemon PID — belong in live MCP introspection. See §2 and `docs/wiki/plugin-identity-and-health-sentinels.md`.

**(e) Adding a value that is universal across machines.** If the value is the same on every machine the operator runs (e.g., a fixed public URL, a schema version constant, a vendor SDK that always installs to the OS-canonical location), commit it to the relevant repo. Git-tracked durability is the right primitive; no operator action needed per machine.

**(f) Putting machine-specific path values in `registry.toml` instead of `registry.local.toml`.** `registry.toml` is git-tracked and travels with the `~/.claude` repo across machines. If you bake `repos.claude_unreal_holodeck = "E:/dev/claude-unreal-holodeck"` into `registry.toml`, that path is wrong on every other machine the operator uses. Machine-specific values go in `registry.local.toml`, which is gitignored. See §9 for the full split rationale and the Striker-and-Mac worked example.

## 9. Tracked Baseline + `.local` Overrides — Why and When

`~/.claude/` is git-trackable, and operators are encouraged to treat it that way (established practice on the PM's machines; documented as a recommendation for OSS adopters in the coordinator setup material). The registry composes with that:

- `registry.toml` (and any `<concern>.toml`) is **tracked** — carries the shared baseline: key declarations, `schema = 1`, the `concerns` list, and values that hold across all of the operator's machines.
- `registry.local.toml` (and `<concern>.local.toml`) is **gitignored** — carries per-machine path values. These are the values that differ across the operator's machines.

This matches the `*.local.*` precedent already established at `~/.claude/`: `CLAUDE.local.md`, `coordinator.local.md`, `settings.local.json`. The `.local` convention is consistent throughout the install tree.

**Worked example — Striker and Mac.** The operator runs from Striker (Windows, repos under `X:/...`) and a Mac on the go (repos under `~/work/...`). One git-tracked `~/.claude` repo lives on both machines. `registry.toml` is identical on both — it declares `repos.coordinator_claude`, `repos.project_rag`, etc. as keys, sets `schema = 1`, lists `concerns`. On Striker, `registry.local.toml` contains:

```toml
"repos.coordinator_claude" = "X:/coordinator-claude"
"repos.project_rag"        = "X:/project-rag"
```

On the Mac, `registry.local.toml` contains:

```toml
"repos.coordinator_claude" = "~/work/coordinator-claude"
"repos.project_rag"        = "~/work/project-rag"
```

Same keys, different machine-specific values, no manual reconciliation, no merge conflicts — `.local.toml` is gitignored on both ends so it never appears in the shared history. Single-machine operators ignore the `.local` layer entirely; it is opt-in by virtue of the file simply not existing unless the operator creates it.

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
| `~/.claude/holodeck/` | claude-unreal-holodeck | install-status.json, install-logs/, setup-state.json; **imminent:** watchdog/status.json, chain-walk-*.json (migrating from `~/.holodeck/`) | Migration in flight 2026-05-19; collapses the dual-namespace split (`~/.holodeck/` + `~/.claude/holodeck/`) into the canonical root. See `claude-unreal-holodeck/state/memos/2026-05-19-doe-question-holodeck-namespace-collapse.md` (grandfathered pre-cutoff memo) |
| `~/.claude/project-rag/` | project-rag host | host runtime state | Existing; predates this doctrine |
| `~/.claude/machine-local/` | coordinator | TOML registry — see §1–10 above | The config substrate, not a project state dir |
| `~/.claude/plugins/<plugin>/data/` | each plugin | addon-owned on-disk state | Plugin-addressed; orthogonal to top-level project dirs |

**Adding a new top-level FS namespace under `~/.claude/<project>/`.** This is the DoE-altitude call: claiming a top-level directory under `~/.claude/` is an FS-namespace claim that other projects might collide with, and the §1.2 critique of `~/.<project>/` accretion is what this row exists to prevent. Register here in the same commit that creates the directory on disk; PM-authorized.

**Distinct from — adding a TOML key or table inside the registry.** Adding a new key in `registry.local.toml`, opening a new dotted namespace (`mything.*`), or even authoring a new concern file under §6 criteria is NOT DoE-altitude. See §5a (authorship vs. value-writing) and §5b (the cheap path for adding values). The FS-namespace gate here is about *new top-level directories on disk*, not about *content inside the registry's existing namespace*.

**Retiring `~/.<project>/` top-level dirs.** When a project still owns a `~/.<project>/` top-level namespace, migrate to `~/.claude/<project>/` and register here. Operator-visible path migration; one release of relocation logic. The `~/.project-rag/wiring.env` retirement (PM-handled, downstream of this registry shipping) is the worked precedent.

## 12. `plugin.mirrors` — Plugin Live-Install Tracking

<!-- spec-backlink: docs/plans/2026-05-21-plugin-source-live-mirror-doctrine.md § Chunk 5 -->

The `plugin.mirrors` table namespace registers plugins whose live install may be a separate git checkout of the plugin's source repo. The drift probe (`check-plugin-drift.sh`) reads these entries to detect when a live install has fallen behind its source.

**Full schema, field reference, and operator examples live in `~/.claude/machine-local/README.md § plugin.mirrors`** — do not duplicate here. The summary below covers only the doctrine decision points.

**No provenance stamp on `plugin.mirrors.<name>` writes (DoE ruling 2026-05-23).** Each `[plugin.mirrors.<name>]` table is repo-namespaced and single-writer — only that plugin's own installer ever writes its table, so the table key already encodes the writer. The `[provenance]` convention (§5b case 3, §6) exists specifically for *multi-writer collision diagnosis* — disambiguating which automated writer set a key several installers can write (e.g. `[provenance.unreal]` on the shared `unreal.install_root`, seeded by more than one installer). It is **not** a universal stamp on every `registry.local.toml` write. A single-writer namespaced table has nothing to disambiguate, so a provenance stamp there is ceremony, not signal. Append-only writers that structurally preserve sibling tables (read → `tomllib`-parse-absent-check → append → atomic `os.replace`) satisfy the preserve-unrelated-tables property by construction and need no provenance. (Triggered by project-rag-em's question on `_register_plugin_mirror.py`.)

### Three modes, three structural shapes

| Mode | When to use | Drift probe behavior |
|---|---|---|
| Default (git-checkout-managed) | Live install is a separate git checkout; source changes must be explicitly propagated via `refresh-plugin-live-install.sh` | Checks git-state (commits-behind) and venv-state (editable pin, MAPPING integrity, console-script shims) |
| `propagation_mode = "source_is_live"` | Live install IS the canonical source (e.g., coordinator — `~/.claude/` is both source and install) | Emits `[n/a] propagation_mode=source_is_live` and skips all checks |
| `propagation_mode = "copy_install"` | Live install is a file-copy produced by a copy-based installer (e.g., the holodeck trio — `holodeck`, `holodeck-control`, `game-dev`); no git remote in the live path | SHA-sentinel drift class: compares `version.txt` (40-char SHA written by the installer) against `git -C <source_path> rev-parse HEAD`; no git fetch, no venv legs |

### `source_is_live` rationale

For the coordinator plugin, edits happen directly inside `~/.claude/`. There is no "source → live" propagation step because source and live are the same directory. Registering this with `propagation_mode = "source_is_live"` communicates the structural distinction to the probe so it does not report false drift. Outward percolation (`install → publish-repo` via `publish.sh`) is a separate concern and unaffected by this entry. See `docs/plans/2026-05-21-plugin-source-live-mirror-doctrine.md § Chunk 5` for the source-direction inversion rationale.

### `propagation_mode = "copy_install"`

<!-- spec-backlink: docs/plans/2026-05-23-copy-install-drift-coverage.md § Chunk 1 -->

For plugins whose live install is produced by a copy-based installer (rather than a git
checkout), set `propagation_mode = "copy_install"`. The canonical example is the
`claude-unreal-holodeck` trio (`holodeck`, `holodeck-control`, `game-dev`), installed via
`scripts/install-plugin.sh` from the holodeck source repo.

**Applicable fields.** `track_ref` and `dist_name` do not apply — no git remote is consulted and no venv editable-install is involved. The fields that apply are:

| Field | Required | Semantics |
|-------|----------|-----------|
| `source_path` | yes | Absolute path to the plugin source repo root (for `git rev-parse HEAD` + locating the installer) |
| `live_path` | yes | Absolute path to the live install directory (for reading `version.txt`) |
| `refresh_cmd` | no | Shell command run from `source_path` to reinstall. If absent, refresh prints the manual path and exits non-zero. |
| `source_subpath` | no | Relative path within `source_path` to the plugin tree (e.g. `plugin/holodeck-control`). Used by the content-equivalence fallback to scope `git ls-tree`. Default: `plugin/<plugin_name>` when absent. |

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

The coordinator does **not** hardcode `install-plugin.sh <plugin> --no-enable`: the holodeck trio
gates standalone component installs behind `HOLODECK_UMBRELLA_INSTALL=1` (a bare component install
is *refused*), reachable only via the component forwarders' `--allow-standalone` passthrough — and
the docs/umbrella component has no forwarder. The correct invocation is installer-internal
knowledge, so it lives in `refresh_cmd` (operator/installer-supplied, same trust level as the paths
the script already executes against). `--no-enable` bypasses `enable_plugin.py` (the `settings.json`
lock). **If no `refresh_cmd` is registered, refresh prints the manual path (`/holodeck:setup` or the
per-component forwarder) and exits non-zero — it never silently no-ops or guesses an invocation.**

**No-sentinel state.** If `version.txt` is absent, the probe emits `[info] no sentinel` and
exits 0 — this is honest degraded state, not drift. The sentinel is only written when
`requires_plugin_source_index: true` is set in the plugin manifest; for plugins without it,
`[info] no sentinel` is the expected output until the holodeck installer is updated (see
the holodeck repo's `cross-repo/2026-05-23-copy-install-drift.md` (holodeck pre-restructure root-level placement; will move to cross-repo/inbox/ on next migration) (asks tracked in `docs/plans/2026-05-23-copy-install-drift-coverage.md`)).

**Known limitation.** SHA-sentinel catches **committed drift only**. Uncommitted source edits
are invisible. Content-diff (the only alternative) is a false-positive machine because the
installer injects BOMs into `.ps1` files, copies the marketplace manifest, and strips
`.mcp.json`. The sentinel is the deliberate tradeoff.

**Registration example** (Striker, holodeck trio):

```bash
machine-local set plugin.mirrors.holodeck-control.propagation_mode copy_install
machine-local set plugin.mirrors.holodeck-control.source_path X:/claude-unreal-holodeck
machine-local set plugin.mirrors.holodeck-control.live_path C:/Users/oduffy/.claude/plugins/claude-unreal-holodeck/holodeck-control
machine-local set plugin.mirrors.holodeck-control.refresh_cmd 'bash scripts/install-control-plugin.sh --allow-standalone --no-enable'
# game-dev: same shape, refresh_cmd → install-game-dev-plugin.sh --allow-standalone --no-enable
# holodeck (docs, no forwarder): refresh_cmd → 'HOLODECK_UMBRELLA_INSTALL=1 bash scripts/install-plugin.sh holodeck --no-enable'
```

For clean-install reproducibility on a fresh machine, installers should self-register these
entries at install time. See the holodeck repo's `cross-repo/2026-05-23-copy-install-drift.md` (holodeck pre-restructure root-level placement; will move to cross-repo/inbox/ on next migration) (asks tracked in `docs/plans/2026-05-23-copy-install-drift-coverage.md`)
for the memo requesting this from the holodeck installer.

### `reverse_drift_cmd` (reverse-drift merge gate)

`refresh_cmd` polices **forward** drift (source newer than live). `reverse_drift_cmd` polices the
opposite direction: a live install hand-edited *after* the last copy, which the forward-SHA probe
cannot see. It is the per-plugin command that digest-compares live against source and exits non-zero
on a hand-edit. Registered per `copy_install` plugin alongside `refresh_cmd`:

```bash
machine-local set plugin.mirrors.holodeck.reverse_drift_cmd 'bash bin/check-reverse-drift.sh'
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
dronesim, geneva-mvp, …) checks only `copy_install` plugins whose `source_path` IS that repo — usually
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
N/A and passes cleanly (exit `0`, empty output). Detection logic itself remains holodeck-owned
(`X:/claude-unreal-holodeck/bin/check-reverse-drift.sh`); the coordinator only routes to it via this field.

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
test -d ~/.claude/machine-local/                          # P-1 — substrate exists
~/.claude/bin/machine-local has schema                    # P-4 — reader works + schema declared
~/.claude/bin/machine-local get repos.coordinator_claude  # P-3 — sample key resolves
```

If any probe fails, coordinator-doctor.md §3 has the remediation steps.

## Related Wikis

- `docs/wiki/plugin-identity-and-health-sentinels.md` — companion doctrine; defines operator-set configuration and the decay-discipline boundary. The 2026-05-19 Scope narrowing amendment is the joint anchor between that wiki and this one.
- `docs/wiki/dual-identity-module-hazard.md` — why the reader contract is shell-out, not import.
- `docs/wiki/plugin-extraction-and-distribution.md` — port-time cleanup contract (§ 11); sibling-layout is unchanged for extraction, machine-local is the runtime preference.
- `docs/wiki/cross-repo-citation-conventions.md` — sibling-layout convention and peerless-installs; `MACHINE_LOCAL_<KEY>` is the named successor to the ad-hoc per-repo env-var opt-in (e.g., `HOLODECK_REPO_ROOT=`).
- `docs/wiki/doe-altitude-and-shared-infra.md` — the PM-facilitated DoE consult methodology that produced the design plan for this registry.
- `docs/wiki/cross-repo-communication.md` — PM-relay reply-memo pattern used when the DoE reply memo (Task 6 of the design plan) was dispatched to the bilateral EMs.
