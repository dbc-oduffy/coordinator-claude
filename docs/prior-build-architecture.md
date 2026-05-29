# Prior Build Architecture — Monolithic Holodeck (pre-split)

> **Status:** Superseded (replaced by the three-repo triad — see `new-build-architecture.md`).
> **Era:** Through early May 2026.
> **Scope:** How UE engine knowledge + RAG retrieval were built, shipped, and served *before* the host/addon/consumer split.

---

## 1. One-sentence summary

A **single repository** (`claude-unreal-holodeck`) that bundled everything — the Unreal Engine documentation corpus, the vector store, and a self-contained MCP server — so that the RAG index shipped *inside* the consumer project rather than being produced and distributed independently.

---

## 2. Shape of the system

```
claude-unreal-holodeck/              (one repo = everything)
├── vector_store/                    ← the corpus, committed/bundled IN the repo
│   ├── chroma.sqlite3               (~375 MB — embedded UE-docs vectors)
│   ├── <uuid>/                      (Chroma collection segment dir)
│   ├── bm25_cache_ue_docs.pkl       (~166 MB — lexical/BM25 index)
│   ├── doc_texts.sqlite3            (~247 MB — raw chunk text store)
│   ├── chunk_index_state.json       (~9 MB — indexing fingerprint/state)
│   └── ue-mcp-server.pid            (PID of the standalone MCP server)
└── (UE project + holodeck editor-control tooling)
```

Everything a query needed lived in one tree: the embeddings, the lexical cache, the source text, the indexing state, and the server process that served them.

---

## 3. Components & responsibilities

| Component | Responsibility |
|-----------|----------------|
| **`vector_store/` (bundled corpus)** | The entire UE-docs knowledge base — Chroma vectors + BM25 cache + raw doc text — physically present in the consumer repo. |
| **`ue-mcp-server` (standalone)** | A self-contained MCP server that loaded `vector_store/` and answered retrieval queries. Tracked its own process via `vector_store/ue-mcp-server.pid`. |
| **Indexing scripts (in-repo)** | Built/refreshed the bundled `vector_store/` in place; `chunk_index_state.json` recorded the fingerprint of what had been indexed. |

There was **no separation** between the retrieval engine, the engine-knowledge corpus, and the project being worked on — all three concerns were fused into one repo and one server.

---

## 4. How a build/install worked (old model)

1. Clone/obtain the holodeck repo — which **already contained** the multi-hundred-MB `vector_store/`.
2. Start the bundled `ue-mcp-server`, which loaded the in-repo Chroma + BM25 store directly.
3. Query against the single embedded collection.

There was no separate "download the corpus" step and no separate runtime to install — the corpus *was* the repo, and the server *was* part of it.

---

## 5. Why this was replaced

The monolithic design had structural problems that the triad split (see the new-architecture doc) was designed to fix:

- **Corpus bloat in the consumer repo.** ~800 MB of binary index artifacts (`chroma.sqlite3` 375 MB + `bm25_cache` 166 MB + `doc_texts` 247 MB) lived inside the project repo — heavy to clone, version, and update.
- **No independent corpus distribution.** Refreshing UE engine knowledge meant re-building artifacts inside the consumer repo; the corpus couldn't be produced once and consumed by many projects.
- **No reuse across projects.** Every UE project that wanted engine RAG would have to carry its own copy of the corpus and its own server.
- **Coupled lifecycles.** The retrieval engine, the engine corpus, and the project code all versioned together — a change to one forced churn in the others.
- **Schema lock-in.** The embedded store's schema was tied to whatever version shipped in the repo; there was no host "minimum schema" gate to reject an incompatible corpus (the new model adds `MIN_SUPPORTED_SCHEMA`).

---

## 6. Migration residue observed during the clean install

During the 2026-05-27 → 05-29 clean install, the old store was still present on disk in the holodeck repo (`vector_store/chroma.sqlite3` 375 MB, dated April 24; `ue-mcp-server.pid` referencing a **stale, non-running** PID). The PM decision was to **ignore the old bundled store and download a fresh engine corpus** from the addon's GitHub Releases instead — i.e. treat the monolithic artifacts as legacy leftover, not migrate them. (See friction-log entry **E14**.) The old store was potentially schema-incompatible with the rewritten host (the new host enforces a minimum corpus schema version).

---

## 7. Contrast with the new model (one line)

Old: **one repo holds the engine + corpus + server, all fused.**
New: **three repos — a generic host runtime, an engine-knowledge addon that publishes the corpus to GitHub Releases, and a thin consumer project — each versioned and distributed independently.** See `new-build-architecture.md`.
