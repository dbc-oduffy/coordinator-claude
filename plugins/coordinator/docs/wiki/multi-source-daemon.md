---
title: Multi-source daemon
status: shipped
shipped_in_wave: multi-source-daemon-and-source-kwarg
spec: docs/plans/2026-05-16-multi-source-daemon-and-source-kwarg.md
---

<!-- Imported from X:/project-rag at SHA d376cb01 on 2026-05-19. Inherited substrate; canonical lineage now in Claude Central. Origin: project-rag/docs/... — see CLAUDE.local.md "Sibling repos" for layout. -->

<!-- Spec backlink: docs/plans/2026-05-16-multi-source-daemon-and-source-kwarg.md -->

# Multi-source daemon

> **See also:** [`docs/wiki/source-kwarg-routing.md`](source-kwarg-routing.md) — consumer-facing contract for the `source=` kwarg, routing-failure verdicts, and band naming convention. This file covers daemon internals.

The multi-source daemon is the architecture by which a single project-rag MCP server running on a developer machine serves multiple indexed repositories concurrently, automatically routing each Claude Code session to the right per-project index based on the session's working directory.

## 1. Why this exists

Before this architecture, the daemon was effectively single-project: agents had to pass a `project_root` parameter explicitly to identify which codebase they were querying, or rely on the boot-time global set when the server launched. This worked when one agent ran in one repo, but broke down the moment a developer had Claude Code sessions open across several repositories simultaneously.

The multi-source daemon eliminates the explicit parameter burden for the common case. One daemon process runs per machine, maintaining a host-wide registry of all indexed projects. When an agent calls any retrieval tool without specifying a `source=`, the daemon resolves the caller's project automatically: it inspects the TCP connection's peer process, reads that process's current working directory, and looks up the corresponding registry entry. The EM can still name a source explicitly (`source="project-rag-ue-addon"`) for intentional cross-repo queries. The design follows the PM's stated principle: "the default can be that the queries come with a var that matches their parent folder / github repo name, and they'd have to act to replace it with something else."

**What did not change:** the HTTP-shared-daemon topology (`127.0.0.1:8767`, one `~/.claude.json` entry) is unchanged. Per-project storage partitioning (each project's `Saved/ProjectRag/` with its own `graph.db` and Chroma collections) is unchanged. The new layer is discovery and routing — the substrate was already multi-project capable.

## 2. Source registry (`~/.project-rag/projects.json`)

The host-wide source registry is a JSON file at `~/.project-rag/projects.json`. It records every project root that has been indexed by this installation of project-rag.

### Schema

```json
{
  "version": 1,
  "sources": [
    {
      "name": "project-rag",
      "path": "/home/user/project-rag",
      "kind": "python",
      "engine_version": null,
      "last_indexed": "2026-05-16T14:30:00+00:00"
    },
    {
      "name": "project-rag-ue-addon",
      "path": "/home/user/project-rag-ue-addon",
      "kind": "unreal",
      "engine_version": null,
      "last_indexed": "2026-05-16T13:00:00+00:00"
    }
  ]
}
```

The `version: 1` envelope guards against schema evolution. A reader that finds any other value will sidecar the corrupt file and start fresh (see §2.1 below).

### Existing occupants of `~/.project-rag/`

This directory was already in use before the registry shipped. The following files co-exist there and must not be disturbed:

- `chain-walk-<session-id>.json` — chain-walker visited-set per session
- `setup-state.json` — install state written by the Wave 2' installer
- `project.json` — project-type override consumed by `core/project_type.py`

The registry appends `projects.json` and `projects.json.lock` to this directory. No other writes occur.

### 2.1 Read-inside-lock / write-inside-lock contract

Every mutating call to `SourceRegistry.register()` acquires an exclusive OS-level file lock on `projects.json.lock`, then performs read → merge → write entirely inside the critical section. The sequence is:

1. Acquire file lock (`core/_file_lock.py:file_lock`).
2. Re-read `projects.json` from disk (may have been updated by a concurrent session since the lock was requested).
3. Merge the new entry.
4. Atomically rewrite the file via `.tmp` → `os.replace`.
5. Release lock.

Corruption detection also runs inside the same critical section: if the JSON is invalid or the schema version is unrecognised, the bad file is moved to a timestamped sidecar (`~/.project-rag/projects.corrupt.<unix-ts>.json`) and a fresh registry is written before the lock is released. This prevents two concurrent readers both seeing corruption from each deciding independently to write a fresh registry and clobbering each other.

Read-only operations (`resolve_by_path`, `list_sources`, `path_for`) do **not** acquire the lock. They observe a consistent snapshot because the registry file is always replaced via `os.replace`, which is atomic at the filesystem level — partial writes are never visible.

Implementation: `core/source_registry.py`.

## 3. SourceEntry shape and name canonicalisation

Each registry entry is represented as a `SourceEntry` frozen dataclass (`core/source_entry.py`):

```python
@dataclass(frozen=True)
class SourceEntry:
    name: str               # canonical source name (parent folder by default)
    path: Path              # absolute, resolved project root
    kind: str               # from core.project_type.detect() at register time
    engine_version: str | None = None   # reserved; populated by addon hookimpls
    last_indexed: datetime | None = None
```

### Name canonicalisation

The `name` field defaults to the parent folder name of the project root — for example, a project at `/home/user/project-rag` gets the name `project-rag`. This mirrors how repository names appear in most tooling.

**Collision rule (v1 — first-wins):** if two projects share the same parent folder name (e.g., `~/work/foo` and `~/scratch/foo`), the registry keeps the first registered path and logs a warning when a second registration attempts to claim the same name with a different path. Hash-suffix disambiguation (`project-rag-a1b2`) is deferred to a follow-up if/when collisions are encountered in practice.

Re-registering the same `(name, path)` pair is idempotent: it updates `last_indexed` and returns `False` (not newly added).

## 4. CwdResolverMiddleware

`project_rag_mcp/middleware/cwd_resolver.py` implements an ASGI middleware that resolves the caller's project source on every HTTP request before the tool handler fires.

### ASGI stack ordering

```
CwdResolverMiddleware(
    JSONErrorMiddleware(
        streamable_http_app
    )
)
```

`CwdResolverMiddleware` runs first. It populates `_PROJECT_CONTEXT_VAR` before handing control to the inner stack, so every tool handler that calls `current_project_context()` sees the per-request value, not a boot-time global.

### Resolution logic (cache miss path)

On a cache miss, the middleware resolves in two steps:

**Step 1 — psutil network-connections walk.** `psutil.net_connections(kind='tcp')` is called to find the connection whose peer port matches the caller and whose local port matches the daemon. The matching connection's PID is passed to `psutil.Process(pid).cwd()` to read the process's working directory. That directory is resolved against the source registry via `SourceRegistry.resolve_by_path(cwd)`.

```python
# Simplified resolution sketch
conns = psutil.net_connections(kind="tcp")
for conn in conns:
    if conn.laddr.port == peer_port and conn.raddr.port == daemon_port:
        cwd = psutil.Process(conn.pid).cwd()
        return registry.resolve_by_path(Path(cwd))
```

**Step 2 — by-PID marker fallback.** If the psutil walk returns nothing (permission denied, no matching connection, transient race), the middleware reads the by-PID marker files written by the SessionStart hook (see §6). If a marker for the connection's PID exists and is fresh, the `cwd` field is resolved against the registry.

### Session cache

Resolved entries are cached in a process-level `OrderedDict` LRU to avoid paying the full psutil walk cost on every tool call within the same session:

| Cache key | Condition |
|---|---|
| `Mcp-Session-Id` header value | When the header is present (stateless-HTTP sessions) |
| `(peer_host, peer_port)` tuple | When the header is absent (admin endpoints, hook POSTs) |

Cap: 64 entries. TTL: 1 hour. Eviction sweeps on access. Because the MCP server runs in a single asyncio event loop thread, no mutex is required on the cache data structure.

### ContextVar reset (per-request isolation)

The middleware sets `_PROJECT_CONTEXT_VAR` with a token, awaits the inner app, and resets the token in a `try/finally` block. This guarantees per-request isolation even when requests run concurrently on the asyncio loop:

```python
token = _PROJECT_CONTEXT_VAR.set(project_ctx)
try:
    await self.app(scope, receive, send)
finally:
    _PROJECT_CONTEXT_VAR.reset(token)
```

## 5. Boot-race contract (the Staff Engineer Finding 2)

**This section documents a hard architectural contract. Do not relax the retry bound without an architectural review.**

The SessionStart hook (§6) and the middleware's first-request resolution (§4) are concurrent processes with no happens-before guarantee. A Claude Code session may dispatch its first tool call before the hook has finished writing the by-PID marker. In the same window, psutil may not yet see a stable connection entry if the TCP handshake is still in progress.

The specified resolution is **one bounded retry**:

1. The middleware attempts psutil walk + marker file read.
2. If both return no match, the middleware sleeps the `boot_race_sleep_s` duration (default 100 ms, configurable via the constructor arg).
3. The middleware re-walks psutil and re-reads the marker directory.
4. If still unresolved, the middleware returns `verdict="no_source_resolved"` with a hint listing registered sources.

<!-- Review: Sonnet session-end F9 — "100 ms" → "default 100 ms, configurable via boot_race_sleep_s" -->
The retry is bounded to exactly one attempt (default 100 ms sleep, configurable via `boot_race_sleep_s`). This is not a polling loop. Future maintainers must not expand this to multiple retries, exponential backoff, or any form of blocking wait — the 100 ms default is the maximum latency acceptable for a first-call resolution penalty, and the correct response to persistent non-resolution is the `no_source_resolved` verdict with a helpful hint, not indefinite waiting.

The boot-race retry is implemented in `CwdResolverMiddleware.__call__` in `project_rag_mcp/middleware/cwd_resolver.py`.

## 6. SessionStart hook by-PID marker (C5)

The SessionStart hook writes a JSON marker file under `~/.project-rag/sessions/by-pid/` at session boot. This marker serves as the fallback channel when psutil cwd-resolution fails or is unavailable.

### Marker file shape

```json
{
  "cwd": "/home/user/project-rag",
  "machine": "striker-dev",
  "timestamp": 1747392000
}
```

The file is named `<cc_pid>.json`, where `cc_pid` is the PID of the Claude Code process that started the session. Writes use an atomic `.tmp` → rename pattern so partial writes are never visible to the middleware reader.

### Shell implementations

**Bash (`plugin/hooks/scripts/ensure-server.sh`):** resolves the Claude Code parent PID via `$PPID` and writes the marker using Python's `core.session_marker.write_marker()` helper (to keep the JSON serialisation in one place).

**PowerShell (`plugin/hooks/scripts/ensure-server.ps1`):** resolves the parent PID via `(Get-Process -Id $PID).Parent.Id`.

### Janitor sweep

`bin/sessions-janitor.sh` and `bin/sessions-janitor.ps1` sweep marker files whose mtime is older than one hour. The sweep is also accessible programmatically via `core.session_marker.sweep_markers(max_age_seconds=3600)`. The daemon may invoke the sweep opportunistically on boot to avoid stale-marker accumulation.

Markers older than five minutes are ignored by `CwdResolverMiddleware._resolve_from_marker` as a boot-fresh heuristic (stale markers from previous sessions should not accidentally bind a new session's resolution).

## 7. `@logged_retrieval` resolution precedence (E-RUNTIME, 4-step)

Every retrieval tool body resolves its project context through a single 4-step precedence chain in `@logged_retrieval` (`project_rag_mcp/audit.py`). The env-var fallback rung was removed in E-RUNTIME (AD-RT-1, 2026-05-17) — `PROJECT_RAG_DEFAULT_PROJECT_ROOT` is no longer consulted by tool bodies.

| Priority | Source | How |
|---|---|---|
| 1 | Explicit `source` kwarg | `SourceRegistry().entry_for(source)` → `ProjectContext` v2 (source_name, engine_version, project_kind) |
| 2 | Middleware-set ContextVar | `current_project_context()` already populated by CwdResolverMiddleware |
| 3 | Legacy `project_root` kwarg | Used as a bare path (backward-compat; source_name/engine_version/project_kind = None) |
| 4 | None resolved | Returns `(None, False)` → caller emits `verdict="no_source_resolved"` |

**`PROJECT_RAG_DEFAULT_PROJECT_ROOT` env var (post-E-RUNTIME role):** this env var continues to exist as a daemon-launch convenience for `--project-root` defaulting in `project_rag_server.py` boot, but it is never consulted by the tool-body resolver chain. Setting it does not rescue an unresolved tool call.

**No silent fallback.** If the chain exhausts all priorities without a resolved source, the tool returns `no_source_resolved` with a hint — it does not silently pick a "primary" source or the last-used source. Fail-loud is the contract.

**`engine_runtime` → `unreal_5.7_runtime` rename note:** the canonical source name for the UE 5.7 engine corpus changed from `engine_runtime` to `unreal_5.7_runtime` in the E-NAMED-BANDS naming convention (E-RUNTIME phase, 2026-05-17). Any stored source kwarg using `engine_runtime` will return `input_invalid` until updated.

Spec backlink: docs/plans/2026-05-17-engine-rag-runtime.md §AD-RT-1

## 8. Source kwarg agent UX

Every retrieval tool accepts an optional `source` kwarg:

```python
# Default: use the middleware-resolved source for this session
result = project_cpp_symbol(symbol="DGFlightController")

# Explicit: override to a named source for cross-repo queries
result = project_cpp_symbol(symbol="DGFlightController", source="project-rag-ue-addon")
```

**Default behaviour (source=None):** the `@logged_retrieval` decorator resolves the source from the middleware-set ContextVar. The caller does not need to think about which repo they are in — the daemon already knows.

**Explicit override (source="<name>"):** useful when an EM needs to reach into a different indexed repository. The name must match a registered source exactly (case-sensitive). An unknown source name fails loud with `verdict="input_invalid"` and a hint listing valid names — there is no silent fallback to a default.

**No list form.** The old `sources=["project","engine"]` list-form parameter is deleted as of the C4 sweep (PM directive 2026-05-16: "kill backwards compat, let's make this clean"). There is one `source` (singular, optional string), not a filter list.

## 9. `project_whoami` and `project_list_sources`

Two meta-tools in `project_rag_mcp/tools/whoami.py` give agents a self-discovery surface without requiring external context injection.

### `project_whoami`

Returns the caller's resolved source identity and the full registered-source roster:

```json
{
  "verdict": "ok",
  "data": {
    "source": "project-rag",
    "project_kind": "python",
    "engine_version": null,
    "registered_sources": [
      {"name": "project-rag", "kind": "python", "last_indexed": "2026-05-16T14:30:00+00:00"},
      {"name": "project-rag-ue-addon", "kind": "unreal", "last_indexed": "2026-05-16T13:00:00+00:00"}
    ],
    "addon_sources_available": []
  },
  "hint": null,
  "provenance": {"indices": ["source_registry"], "phase": null}
}
```

`engine_version` and `addon_sources_available` are reserved fields: they are populated by addon hookimpls in later waves (C7 / W5). Both tools carry `domain=[]` — no project-type gating — so they are callable from any session regardless of whether the project is Python, Unreal, or anything else.

### `project_list_sources`

A thin convenience wrapper over `SourceRegistry().list_sources()`. Broken out as a separate tool for agent discoverability: agents grepping the tool roster for `list` can find it immediately without parsing the richer `project_whoami` response.

**Neither tool ever returns a non-OK verdict.** An empty registry is descriptive, not an error. Resolution failure (no source for caller) surfaces `source: null` in the data payload, not a non-OK verdict.

## 10. Addon hookspec — `project_rag_register_corpus_provider` (C7) + v8 band-naming convention

C7 authors the project-rag side of the D-5 hookspec from the ue-addon cross-repo coordination memo. The addon authors the hookimpl in its W5 PR wave once C7 lands.

**v8 update (2026-05-17, E-NAMED-BANDS):** `CorpusBand` extended with five fields; boot-time aggregation centralized in `source_registry.aggregate_at_boot()`. See §v8 additions below.

### Hookspec (shipped in C7, extended in v8)

```python
def project_rag_register_corpus_provider() -> list[CorpusBand]:
    """Return corpus bands this addon makes available to the host.

    Each band declares a named set of (source, authority) pairs that the
    host's source-routing and blended-query layers can dispatch to.
    """
```

### `CorpusBand` shape (v8 — ADDON_PROTOCOL_VERSION = 8)

```python
CorpusBand = {
    # v1-v7 fields (with v8 default changes for authority_pairs and default_weight)
    "band_name": str,                           # Addressable source name (see naming convention below)
    "authority_pairs": list[tuple[str, str]],   # (source_name, authority) pairs; default=[]
    "default_weight": float,                    # blended-query default weight; default=1.0
    "applicable_kinds": list[str] | None,       # None=universal; []= bug-shape; ["unreal"]=UE-only
    # v8 new fields (all defaulted)
    "engine_version": str | None,               # AD-14. Required for engine-kinded bands.
    "chunk_filter": dict | None,                # AD-8. Flat {key: value} filter applied as Chroma where.
    "required_env": dict[str, str] | None,      # AD-13. Env-var declarations probed at boot.
    "corpus_sha256": str | None,                # INERT. Carry-along provenance.
    "corpus_root": str | None,                  # AD-15. Parent dir of chroma data; host appends sub-path.
}
```

### Band naming convention (AD-9, v8)

**Engine-tied bands** (applicable_kinds non-None): `[engine-name]_[engine-version]_[band]`
- Examples: `"unreal_5.7_runtime"`, `"unreal_5.7_editor"`, `"unreal_5.5_plugin"`
- Reserved namespaces: `"unreal_*"`, `"unity_*"`, `"godot_*"`

**Universal bands** (applicable_kinds=None): `[content-form]` or `[content-form]_[topic]`
- Examples: `"coordinator_knowledge"`, `"template_example_band"`
- Reserved: `"coordinator_knowledge"`, `"template_example_band"`

Host does not parse band_name structure; names are opaque routing keys. Uniqueness is enforced at boot across all installed addons — duplicate band_name raises `AddonProtocolViolation`.

### Cross-version isolation (Z-5)

Engine-kinded bands (applicable_kinds non-None) MUST declare `engine_version`. The default-blend filter (AD-5) includes an engine-kinded band in a session's default blend ONLY IF `band.engine_version == session.engine_version`. This prevents UE 5.5 corpora from auto-blending into UE 5.7 sessions (confidently-wrong-answer class Z-5).

Universal bands (applicable_kinds=None) are exempt from engine_version filtering — they serve all sessions by design (AD-10).

### How the host uses registered bands (v8)

- Source validation: `source_registry.band_for(name)` replaces `_VALID_SOURCES` frozenset check.
- `project_whoami` populates `addon_sources_available` from `source_registry.all_bands()` (boot-aggregated, not per-call discovery).
- Default blend: `default_blend_bands(ctx)` in `project_rag_mcp/tools/semantic.py` applies AD-5 + AD-10 + Z-5.
- P-9: `source_registry.CORPUS_KNOWN_GOOD_PAIRS` derived at boot from union of all `band.authority_pairs`.

### OQ-4 disposition trace

The multi-source-daemon plan initially drafted a different hookspec (`project_rag_declare_kind_sources`) that turned out to be a duplicate of the already-ratified D-5 design. OQ-4 was closed 2026-05-16 with Option A: C7 honors D-5 and authors `project_rag_register_corpus_provider` with the extended `CorpusBand.applicable_kinds` field. Full trace: `docs/plans/2026-05-16-multi-source-daemon-and-source-kwarg.hookspec-alignment-proposal.md`.

## 11. Cross-platform substrate

| Platform | Status | Notes |
|---|---|---|
| Windows | Verified empirically | Spike confirmed `scope['client']`, `Mcp-Session-Id`, `psutil.net_connections`, and `Process.cwd()` all work cleanly on Windows without permission errors. psutil 7.2.2 declared in `pyproject.toml`. |
| Linux (POSIX) | Expected to work | `/proc/<pid>/cwd` is psutil's backend on Linux. Untested in automated tests; works in common developer setups. May be blocked under restricted containers (Docker default profile, snap-confined Claude Code) — follow-up validation deferred. |
| macOS | Unverified — possible architectural gap | `psutil.Process.cwd()` may require Full Disk Access for cross-uid introspection. Same-user same-uid usually works without it. If macOS requires a fundamentally different resolution channel (XPC-based introspection), the `CwdResolverMiddleware` will need a platform branch — this is not treated as a test-coverage gap but as a potential architectural divergence. Mac validation is a follow-up workstream. |

The bash SessionStart hook variant works on Linux and macOS. The PowerShell variant covers Windows. `Path.home()` resolves the user home directory cross-platform.

## 11. CI / headless flow (`--non-interactive`)

E-HEADLESS (docs/plans/2026-05-17-engine-rag-headless.md) ships a non-interactive surface for CI runners and agentic callers that cannot complete a TTY-based setup flow.

### `--non-interactive` on `cli.py reindex`

```bash
python cli.py reindex --non-interactive --project-root /workspace/myproject --kind unreal
```

- **Requires** both `--project-root <path>` AND `--kind <kind>` — both must be present or both must be supplied via env vars.
- **Implies `--strict`** — exits non-zero on any producer/consumer partial failure.
- **Suppresses** all interactive prompts; replaces them with assert-or-fail-loud.
- **Runs** post-reindex doctor verification automatically; exits non-zero on NOT GREEN.
- **Detect-and-cross-check** — after validating `--kind`, runs `core.project_type.detect()` on `--project-root` and fails loud if they disagree (prevents silent mis-indexing on shared CI runners). Override with `--kind-force` when genuinely needed.

### Env-var alternates

Agents that cannot inject argv (e.g., some MCP launchers) set three env vars instead:

| Env var | Equivalent CLI arg | Notes |
|---|---|---|
| `PROJECT_RAG_NON_INTERACTIVE` | `--non-interactive` | Only `"1"` is truthy — `"true"`, `"yes"`, `"on"` are all falsy (single-token canonical form) |
| `PROJECT_RAG_KIND` | `--kind <K>` | Must be a member of `core/project_type.py:PROJECT_TYPES` |
| `PROJECT_RAG_PROJECT_ROOT` | `--project-root <path>` | Must be an absolute existing-directory path |

**CLI wins over env vars.** If `--non-interactive` is passed AND `PROJECT_RAG_NON_INTERACTIVE=0` is set, non-interactive mode is ON (CLI flag wins). This follows the `make` / `cargo` / `pytest` convention.

### `--non-interactive` on `scripts/project_rag_setup.{sh,ps1}`

`--non-interactive` on the setup scripts bundles three behaviors:

1. Suppresses all interactive prompts (`read -p` / `Read-Host`).
2. Implies `--i-am-agent` (suppress agent-mode confirmation prompt).
3. Implies `--skip-dep-check` (dep-check failures exit non-zero immediately).

Phase 4 (source registration) requires explicit `--project-root` and `--kind` under `--non-interactive`; fail-loud if either is missing (same F-12 message as `cli.py`).

The existing `--i-am-agent` and `--skip-dep-check` flags remain for back-compat — callers that pass them individually continue to work.

### `PROJECT_RAG_REGISTRY_PATH` (test isolation)

When set, overrides `_DEFAULT_REGISTRY_PATH` in `core/source_registry.py` (normally `~/.project-rag/projects.json`). Test-only: subprocess tests (T-31, T-32, T-35) set this to a `tmp_path`-scoped path to isolate registry writes from developer machines. Production callers never set it.

### Failure catalog row F-12

Non-interactive invocation without both `--project-root` and `--kind` emits:

```
❌ --non-interactive requires both --project-root and --kind (or both PROJECT_RAG_PROJECT_ROOT and PROJECT_RAG_KIND env vars). Got: project_root=<X>, kind=<None>.
```

F-12 is a CLI gate, not a doctor probe (`doctor_probe: null`). It fires before any indexer work begins.

### Doctor probe interactivity (`plugin/commands/doctor-probe-interactivity.txt`)

Sibling file to `doctor-probe-registry.txt`. Maps each probe to an interactivity class:

| Class | Behavior under `--non-interactive` |
|---|---|
| `silent` | Runs normally |
| `assert` | Runs; failure exits non-zero with catalog-sourced message |
| `prompt` | Skipped; catalog row `doctor_failed` provides headless hint |
| `prompt-with-cli-override` | Auto-accepts when override flag present (e.g., `--reinstall-addons`); skipped otherwise |

Default for unclassified probes: `assert` (fail-loud, not skip-silently).

## 12. What is intentionally out of scope

These are deliberate exclusions, not deferred improvements. Do not reintroduce them without a new PM-authorised plan.

- **Multi-retry polling on boot race.** The boot-race contract (§5) specifies exactly one retry (default 100 ms, configurable via `boot_race_sleep_s`). No polling loop, no exponential backoff.
- **Engine-version routing in core.** Core does not know about Unreal Engine versions. Engine-version → band-name mapping lives in the ue-addon hookimpl. Core sees opaque band names.
- **Backwards-compatible `sources=` list-form.** The old `sources=["project","engine"]` enum-based parameter is deleted in C4. PM directive 2026-05-16: "kill backwards compat, let's make this clean." One pass, clean break.
- **Polyglot source-resolution (multiple kinds per source).** A source has one `kind` string in v1. If a project legitimately has multiple primary languages (e.g., Python + C++ host), `kind` stores `detect()`'s priority-ordered winner. The `frozenset[str]` multi-kind shape is the v2 path if/when needed.
- **Silent fallback to a default source.** When the caller's cwd is not in the registry, the response is `no_source_resolved` with a hint. No "pick the primary" or "pick the last-used" fallback exists by design.
- **Filter-then-discard approach.** The daemon dispatches directly to the named source's index — it does not retrieve from all sources and filter. PM rejected filtering: "let's not waste resources by just filtering results when we can be smarter."
- **Cross-repo access-control or permissions.** Any registered source is reachable by any session by name. Source routing is about noise and resource efficiency, not isolation.

## 13. Operational reference

### File locations

| Path | Purpose |
|---|---|
| `~/.project-rag/projects.json` | Host-wide source registry |
| `~/.project-rag/projects.json.lock` | File-lock sentinel (never edit manually) |
| `~/.project-rag/projects.corrupt.<ts>.json` | Corrupt-registry sidecar (informational) |
| `~/.project-rag/sessions/by-pid/<pid>.json` | Per-session marker written by SessionStart hook |

### CLI / operational commands

| Command | Purpose |
|---|---|
| `/project-rag:index` | Full or incremental reindex; auto-registers the source on completion (C2) |
| `bin/sessions-janitor.sh` / `.ps1` | Manual sweep of stale by-PID markers |
| `project_whoami()` MCP tool | Inspect caller's resolved source + full registry |
| `project_list_sources()` MCP tool | Enumerate all registered sources |

### Doctor probes

The `/project-rag:doctor` command (`plugin/commands/doctor.md`) is the canonical health and remediation surface. Registry-related failures will surface as probe failures there. As of this writing, specific registry probes are under active development; check `commands/doctor-probe-registry.txt` for the current probe inventory.

## 11. Engine-only mode (`--require-uproject=auto|true|false`)

<!-- Spec backlink: docs/plans/2026-05-18-host-side-install-surface-from-addon-relay.md §H-1 -->

The `--require-uproject` flag decouples uproject presence from addon loading. Prior behaviour coupled them: `require_uproject=not _no_addons` in `project_rag_server.py:1050`.

| Value | Behaviour |
|-------|-----------|
| `auto` (default) | Scans for `.uproject`; falls back to `true` when `--project-root` unset |
| `true` | Legacy UE behaviour — .uproject required |
| `false` | Engine-only mode: project-* tools return `no_source_resolved` with enriched hint; engine-RAG tools function normally |

**Engine-only mode:** addons load regardless of `.uproject` presence. `--require-uproject=false` is independent of `--no-addons`. A valid use case: connect an addon-registered engine corpus source from a non-UE project directory.

**See also:** `docs/wiki/host-vs-addons.md §Engine-only mode`, `docs/wiki/engine-rag-runtime-contract.md §Engine-only mode`

---

## 12. `source=None` isolation hazard

<!-- Spec backlink: docs/plans/2026-05-17-engine-rag-cross-repo.md -->

When an EM connects to the project-rag MCP server from a cwd that does not match the intended project, `source=None` resolves to the caller cwd-derived project, returning wrong corpus results silently.

**Rule:** sessions querying the self-hosted project-rag index must launch from `X:/project-rag` or set `source="project-rag"` explicitly. This lesson is replicated to both repos' memory dirs.

Z-BAR adjudications (Z-BAR-1, Z-BAR-2, Z-BAR-3) carry concrete resolution shapes so neither EM relitigates.

---

## 13. Headless / CI consumer flow (E-HEADLESS, shipped V1)

<!-- Spec backlink: docs/plans/2026-05-17-engine-rag-headless.md -->

**No v1/v2 split** (PM mandate, 2026-05-17 staff session). The headless flow ships in V1 alongside the interactive flow.

Single command pattern:
```
python cli.py reindex --non-interactive --project-root /workspace/myproject --kind unreal
```
Exits non-zero on unrecoverable failure with catalog-sourced error line on stderr. Every interactive probe is either skipped (if it would prompt) or replaced by a fail-loud assert (if the answer must be present). Same `~/.project-rag/projects.json` entry, same band registry, same doctor verification.

---

## 14. Spec trail

- **Primary plan:** `docs/plans/2026-05-16-multi-source-daemon-and-source-kwarg.md`
- **OQ-4 closure (hookspec alignment):** `docs/plans/2026-05-16-multi-source-daemon-and-source-kwarg.hookspec-alignment-proposal.md`
- **the Staff Engineer review:** `docs/plans/2026-05-16-multi-source-daemon-and-source-kwarg.patrik-review.md`
- **Cross-repo memo (ue-addon side, D-5):** `X:/project-rag-ue-addon/docs/plans/2026-05-13-ue-authority-shift-coordination-memo.md § D-5`
- **Superseded predecessor:** `docs/plans/2026-05-16-cross-repo-mcp-registration-shape.md`
- **MCP shared-server migration (HTTP topology):** `docs/wiki/mcp-shared-server-migration.md`
- **Addon hookspec doctrine:** `docs/wiki/addon-hookspec-shape.md`
