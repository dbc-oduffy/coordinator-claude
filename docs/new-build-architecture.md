# New Build Architecture — The Host / Addon / Consumer Triad

> **Status:** Current (replaces the monolithic holodeck — see `prior-build-architecture.md`).
> **Era:** May 2026 onward (three-repo carve-out).
> **Scope:** How UE engine knowledge + RAG retrieval are built, published, distributed, installed, and served in the post-split design.
> **Verified facts** below (record counts, versions, ports) were observed directly during the 2026-05-27 → 05-29 clean install; see `install_friction_log.md`.

---

## 1. One-sentence summary

Three independently-versioned repos: a **generic, content-agnostic host runtime** (`project-rag`) that serves retrieval over an MCP daemon; an **engine-knowledge addon** (`project-rag-ue-addon`) that *produces and publishes* the Unreal Engine corpus to GitHub Releases and registers UE-specific tools/config into the host; and a thin **consumer project** (`claude-unreal-holodeck`) that gets indexed and consumes both.

---

## 2. The three repos

| Repo | Role | Versioned/shipped as |
|------|------|----------------------|
| **`project-rag`** | **Host runtime.** Generic code-RAG engine + MCP daemon. Knows nothing about Unreal specifically. | Python package (host venv at `C:\Delphi\project-rag\.venv`). Daemon = HTTP MCP on `127.0.0.1:8767`. |
| **`project-rag-ue-addon`** | **Engine-knowledge addon.** Produces the UE corpus, publishes it to GitHub Releases, and registers `required_env` + UE-specific MCP tools into the host via a plugin protocol. | `project-rag-ue-addon==0.4.0` (editable-installed into the host venv). Corpus shipped as GitHub Release assets. |
| **`claude-unreal-holodeck`** | **Consumer project.** The UE project that gets indexed; also hosts the live-editor MCP servers (holodeck-control, etc.). | The project repo itself; registered as a project root with the host. |

The defining move vs. the old model: **the retrieval engine, the engine corpus, and the project are now three separate concerns with three separate lifecycles.**

---

## 3. The host runtime (`project-rag`)

- **MCP daemon.** Entry point `project_rag_mcp/project_rag_server.py`, served over **HTTP (FastMCP streamable-http) on `127.0.0.1:8767`** (defaults in `project_rag_mcp/http_config.py`, overridable via `PROJECT_RAG_HTTP_HOST`/`PROJECT_RAG_HTTP_PORT`). Registered in `~/.claude.json` as `{"type":"http","url":"http://127.0.0.1:8767/mcp"}`. Claude Code *connects* to this URL — it does not spawn the daemon. Health probe: `GET /health` → `{"status":"ready","subsystems":{"boot_complete":true}}`.
- **Retrieval layers.** (1) raw content retrieval (`project_file`, `project_symbol`), (2) structural graph-SQL over a graph DB (`project_referencers`, `project_dependencies`, `project_trace`), (3) semantic embedding search over Chroma (`project_semantic_search`, `project_rag_blended_query`).
- **Embed sidecar.** A separate process (FastAPI, port **43841**) hosts the embedding model and auto-starts on first embed request — decoupled from the daemon so model load doesn't block the server.
- **GPU.** Uses CUDA torch when available — verified `torch 2.12.0+cu130` on an RTX 5070 Ti this install.
- **Config — `~/.claude/machine-local/project_rag.toml`.** Read at daemon boot. Two relevant blocks:
  - `[bin]` — host-declared (absolute path to `project-rag-cli`).
  - `[env]` — **addon-declared**, written by `project-rag-cli wire`; loaded into the daemon's environment at boot. For the UE addon this is `PROJECT_RAG_ENGINE_VECTOR_STORE` (path to the canonical engine Chroma) and `PROJECT_RAG_STRUCTURAL_INDEX` (path to the engine structural-index DB).
- **Addon protocol.** Addons register via a plugin manager; they contribute MCP tools, content classes, and `required_env` declarations that the host aggregates.

---

## 4. The engine addon (`project-rag-ue-addon`)

The addon owns the **engine content class**: it scrapes/chunks/embeds UE engine knowledge, packages it, and publishes it. The consumer side then downloads and merges it.

### 4.1 Corpus layout — single-store (AD-8 / DR-CORPUS-COLLECTIONS-001)

The corpus is published as **per-band archives** but consumed as **one canonical collection per (engine, version)** — named **`chroma_unreal_5.7`**. The bands are an intermediate packaging shape; on the consumer they are *merged* into the single store.

- **13 release archives** for UE 5.7 (`.tar.zst`), ~2.9 GB total:
  - **12 vector-store bands:** `blueprint`, `community`, `configs`, `editor`, `knowledge`, `lyra`, `official_docs`, `plugin`, `python_api`, `runtime`, `samples`, `shaders`.
  - **1 structural index:** `engine-structural` (a Clang/LSP symbol+edge database — `structural_index_ue5.7.sqlite3`).
- **Corpus identity** is an opaque string `release_tag|corpus_version|schema_version`, e.g. `corpus-v0.3.0-ue5.7|0.3.0|4`. `corpus_version` (semver `0.3.0`) is **decoupled** from the UE version (only in the `-ue5.7` tag suffix). `schema_version` is an integer (currently **4**) gated against the host's `MIN_SUPPORTED_SCHEMA`.

### 4.2 Producer pipeline (addon side)

```
scrape/chunk/embed UE content   →  per-band Chroma collections + structural index
        ↓ package_engine_archive.py        (12 band tarballs + structural + corpus_manifest.json)
        ↓ publish-engine-corpus.sh         (uploads to GitHub Releases: corpus-v0.3.0-ue5.7)
GitHub Releases  (release assets + outer manifest-<ue>.json + .sha256)
```

### 4.3 Consumer pipeline (download → merge → wire → load)

```
download-engine-corpus.ps1
  ├─ reads outer manifest (assets map: filename → sha256)
  ├─ per band/structural: download_corpus.py (host lib)
  │     gh release download → stream-hash (sha256 verify) → schema-gate → _atomic_replace (extract .tar.zst)
  │     extracts to: data/corpus-v0.3.0-ue5.7-engine-vector-store-<band>/chroma-<band>/
  │              and data/corpus-v0.3.0-ue5.7-engine-structural/engine-structural/
  └─ merge_per_band_chroma_into_canonical.py
        copies all 12 bands' records (content-hash IDs, idempotent) into ONE collection:
        data/corpus-v0.3.0-ue5.7-engine-vector-store/engine-vector-store/chroma/  →  chroma_unreal_5.7
                                                                          (VERIFIED: 542,331 records)

project-rag-cli wire
  └─ aggregates addon required_env → writes [env] in ~/.claude/machine-local/project_rag.toml
        PROJECT_RAG_ENGINE_VECTOR_STORE = .../engine-vector-store/.../chroma/
        PROJECT_RAG_STRUCTURAL_INDEX    = .../engine-structural/engine-structural/

daemon restart (ensure-project-rag-server.ps1)
  └─ reads [env] at boot → loads the engine collection
        engine_domain_status → engine_queryable: true
```

`.tar.zst` archives require the **`zstandard`** Python module in the host venv — a mandatory-but-previously-undeclared dependency whose absence silently broke the merge during this install (friction-log **E22**).

---

## 5. The consumer (`claude-unreal-holodeck`)

- Registered with the host as a **project root** (`--project-root C:/Delphi/claude-unreal-holodeck`); the host indexes the project's own code into a per-project graph DB + Chroma collection (`/project-rag:index`). *(Not yet primed as of this install — graph.db empty.)*
- Separately hosts the **live-editor MCP servers** (e.g. `holodeck-control` — actor/blueprint/lighting/animation/material/viewport tooling). These are orthogonal to the RAG host but live in the same consumer repo.
- A normal query (`project_rag_blended_query`) can **blend** project hits with engine-corpus hits — the headline benefit of the split: ask "how does my drone controller extend `UCharacterMovementComponent`?" and get project + engine results fused.

---

## 6. Install flow & gates (new model)

The host installer (`project_rag_scripts/install-project-rag-plugin.ps1`, requires **PowerShell 7**) and the addon setup (`project_rag_ue_addon_scripts/setup.ps1`, phased 0–7) enforce:

| Gate / phase | Purpose |
|--------------|---------|
| **Gate A** | `coordinator_whoami` importable by the install venv — an environment/consent probe package supplied by `dbc-oduffy/coordinator-claude`. Must be installed into the *install venv*, not just any interpreter. |
| **Gate B** | machine-local registry present (`~/.claude/machine-local/registry.toml`) — declares repo paths consumed by the host + addon. |
| **torch-CUDA** | selects CUDA wheels for the GPU (`fix-torch-cuda.ps1`). |
| **MCP registration** | writes the HTTP server entry into `~/.claude.json` (an HTTP-migration step moves it to top-level `mcpServers`). **Requires a Claude Code restart** to surface the `project_*` tools. |
| **Addon install** | `pip install -e .` (addon) + `-e ../project-rag` (host) into the venv; seeds the addon registry. |
| **Corpus download + wire** | the §4.3 pipeline. |

Windows note: several steps need `PYTHONUTF8=1` (the `~/.claude.json` merge and even `project-rag-cli --help` crash on cp1252 otherwise — friction-log **E19/E23**).

---

## 7. Why this design (vs. the monolith)

| Old (monolith) | New (triad) |
|----------------|-------------|
| Corpus bundled inside the consumer repo (~800 MB of binaries). | Corpus published once to GitHub Releases; downloaded on demand. |
| One server fused with one corpus and one project. | Generic host serves *any* project; addon supplies *any* engine corpus; consumer is thin. |
| No cross-project reuse. | One published corpus serves N projects. |
| Coupled lifecycles. | Three independent versions (host pkg, `corpus-vX-ueY`, project). |
| No schema gate. | Host enforces `MIN_SUPPORTED_SCHEMA`; corpus carries `schema_version`. |
| One in-repo collection. | Single canonical store per (engine,version), merged from bands, blendable with project hits. |

---

## 8. Known gap at time of writing (2026-05-29)

The engine corpus is **loaded and `engine_queryable: true` at the daemon level**, but `project_rag_blended_query` cannot yet reach engine hits: the generic "engine" band leg is **not registered in the addon band catalog** against the merged single-store collection (the per-band names like `unreal_5.7_runtime` exist; the generic leg name does not map). This is the last gap before engine RAG is reachable through a normal blended query. See friction-log **E24**.
