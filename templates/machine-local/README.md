# Machine-local registry

> Spec backlink: `archive/specs/2026-05/2026-05-19-machine-local-registry.md` §4.4 (Discoverability) and §4 (Design).

This directory is the canonical home for per-machine paths and environment values — Unreal Engine install root, CUDA toolkit path, sibling-repo locations, vendor SDK roots, and any other path that is stable on one machine but differs from machine to machine.

## What this is NOT

- **Not a Claude Code plugin.** Claude Code plugins live under `~/.claude/plugins/` and are loaded by the Claude Code host at startup. This directory is operator-set configuration, not executable plugin code.
- **Not a project-rag addon.** The project-rag host/addon split is a separate concept governing MCP server composition. This registry holds path values the operator sets; it is not an addon and does not interact with the addon lifecycle.
- **Not per-project config.** Values that belong to one specific codebase live in that project's `.claude/` directory. The machine-local registry is for values that span repos and tools — things the operator sets once per machine and every tool reads.

Think of it in the spirit of `~/.gitconfig` — you set it up once per machine, and your tooling reads it from a single well-known location.

---

## Format — TOML

Registry files use TOML. Keys are dotted strings; values are strings (or arrays for the `publish.targets` case). The reader supports two equivalent shapes:

**Quoted flat-key form** (preferred for explicitness — the key name is unambiguous):
```toml
schema = 1

"repos.my_service"             = "/path/to/my-service"
"repos.project_rag"            = "/path/to/project-rag"
"unreal.install_root"          = "/path/to/UnrealEngine"
```

**Natural TOML table form** (convenient for hand-edits with many keys under one namespace):
```toml
schema = 1

[repos]
my_service  = "/path/to/my-service"
project_rag = "/path/to/project-rag"

[unreal]
install_root = "/path/to/UnrealEngine"
```

Both forms produce the same dotted keys (`repos.my_service`, `unreal.install_root`). The reader flattens nested tables at load time via `_flatten_nested`. You may mix both forms in the same file.

**Concern-file namespaces** (`unreal.*`, `cuda.*`) do NOT resolve through the registry's flatten path — they resolve exclusively from their concern file (`unreal.toml` / `unreal.local.toml`) when that concern is listed in the `concerns` array. Keys with a concern prefix in `registry.toml` are ignored (a warning is emitted). See the Concern files section below.

Dotted-namespace keys group related values. The namespace prefix (`repos`, `unreal`, `cuda`) is the first segment. Keys within a namespace are further-dotted as needed.

---

## File roles

| File | Tracked? | Purpose |
|---|---|---|
| `registry.toml` | Yes | Shared baseline: key declarations, schema version, `concerns` list, values stable across all your machines |
| `registry.local.toml` | No (gitignored) | Per-machine path values — different on Machine-a vs. Mac, never committed |
| `registry.toml.example` | Yes | Operator-facing template showing every expected key with comments |
| `registry.local.toml.example` | Yes | Template showing per-machine override shape |
| `<concern>.toml` | Yes | Optional concern-file baseline (only for large surfaces like `unreal`, `cuda`) |
| `<concern>.local.toml` | No (gitignored) | Per-machine overrides for that concern |
| `.gitignore` | Yes | Ignores all `*.local.toml`; tracks everything else |

### `*.example` files

`*.example` files are tracked templates. Copy them to create your live files:

```sh
cp registry.toml.example registry.toml
cp registry.local.toml.example registry.local.toml   # optional: only for multi-machine setups
```

### `*.local.toml` files

Per-machine overrides. The `.local` convention matches `~/.claude/`'s existing practice (`coordinator.local.md`, `settings.local.json`) — `.local` files are gitignored and hold values specific to one machine.

---

## Tracked-vs-local split — worked example (Machine-a + Mac)

The PM operates from Machine-a (Windows, repos under a drive-rooted path) and a Mac (`~/work/...`). One git-tracked `~/.claude` repo is cloned to both machines.

**`registry.toml`** (identical on both machines, committed):
```toml
schema = 1

"repos.my_service"  = ""
"repos.project_rag" = ""
```

**`registry.local.toml` on Machine-a** (gitignored, never committed) — each value is a Windows
drive-rooted path specific to that machine (drive letter, colon, forward slash, then the repo
directory):
```toml
schema = 1

"repos.my_service"  = "<Machine-a's own drive-rooted path>/my-service"
"repos.project_rag" = "<Machine-a's own drive-rooted path>/project-rag"
```

**`registry.local.toml` on Mac** (gitignored, never committed):
```toml
schema = 1

"repos.my_service"  = "~/work/my-service"
"repos.project_rag" = "~/work/project-rag"
```

Same key, different machine-specific values. The `.local` file is gitignored on both machines so there are no merge conflicts. The git-tracked `registry.toml` carries the shared baseline (key declarations, schema) and travels via git pull. Single-machine operators can put all values directly in `registry.toml` and skip the `.local` layer entirely — the split is opt-in.

---

## Git-tracking benefit

`~/.claude/` is intended to be git-tracked (established practice on the PM's primary machines; recommended for OSS operators in coordinator setup material). The registry composes with that: `registry.toml` and concern-file baselines travel via git — key declarations, schema, and cross-machine-stable values are versioned and diffable. Per-machine `.local.toml` files are gitignored and stay local.

This means you get version history on the shared baseline for free, without any machine-specific paths leaking into git.

---

## Concern files

For large surfaces with many keys or version-multiplexed values (multiple Unreal Engine versions, multiple CUDA toolkits), isolate into a concern file — `unreal.toml` / `unreal.local.toml`, `cuda.toml` / `cuda.local.toml`, etc.

List active concerns in `registry.toml`:
```toml
concerns = ["unreal", "cuda"]
```

When a concern is listed, that concern's namespace (`unreal.*`, `cuda.*`) is owned exclusively by the concern file. Do NOT also set `unreal.*` keys in `registry.toml` — the concern file wins, and duplicating them creates confusing silent-shadowing for operators. Put `unreal.*` keys EITHER in the core registry OR in `unreal.toml`, never both.

---

## Reader — `~/.claude/bin/machine-local`

The reader is a shell wrapper at `~/.claude/bin/machine-local` that delegates to a Python implementation (`~/.claude/bin/_machine_local.py`). Python 3.11+ required (uses stdlib `tomllib`).

### Subcommands

```sh
machine-local get <key>                # print value to stdout; exit 1 if missing
machine-local get <key> --default <v>  # print value or default; always exit 0
machine-local has <key>                # exit 0 if present, exit 1 if absent (no output)
machine-local keys                     # list all known keys, one per line
machine-local path                     # print absolute path to the active registry.toml
machine-local set <key> <value>        # write a value to registry.local.toml (preferred over hand-edit)
machine-local set <key> <value> --global   # write to registry.toml (tracked/shared)
machine-local set <key> <value> --dry-run  # print what would be written without changing anything
```

**`set` is the preferred write primitive.** Any EM, executor, or installer that needs to populate a registry value should use `machine-local set` rather than editing the TOML files directly. `set` is atomic (write-to-tmp + rename), idempotent (safe to re-run), and concern-aware (refuses to write keys that belong to a loaded concern file's namespace). Direct hand-edits are fragile — they do not reproduce on reinstall and will not transfer to a new machine automatically.

### Resolution order (most-specific first)

1. `<concern>.local.toml` — per-machine concern overrides
2. `<concern>.toml` — tracked concern baseline
3. `registry.local.toml` — per-machine top-level overrides
4. `registry.toml` — tracked top-level baseline
5. `MACHINE_LOCAL_<UPPER_KEY>` env var — emergency one-off escape (e.g. `MACHINE_LOCAL_UNREAL_INSTALL_ROOT`)
6. `--default` value (if provided)
7. Exit 1 with a one-line error to stderr

The registry is the audited source; env is the escape valve for one-off overrides, not the default channel. Any ambient export in a parent shell, IDE, or `.envrc` would silently outrank deliberate registry values if env ranked higher — it does not.

---

## Doctrine

Full doctrine — when to put a value in machine-local vs. discover at runtime, decay discipline, anti-patterns, and extension path — is in:

```
~/.claude/plugins/coordinator/docs/wiki/machine-local-registry.md
```
