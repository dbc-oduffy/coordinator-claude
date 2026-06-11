<!-- Imported from X:/project-rag at SHA d376cb01 on 2026-05-19. Inherited substrate; canonical lineage now in Claude Central. Origin: project-rag/docs/... — see CLAUDE.local.md "Sibling repos" for layout. -->

# Published API Surface

Spec backlink: archive/specs/2026-05-09-three-way-repo-coordination.md §PR-T1

This document defines what is **stable** (importable by plugin consumers) versus
**internal** (in-tree only, subject to change without notice).

---

## Stable surface — `project_rag.embed`

Plugin consumers (e.g. `project-rag-ue-addon`, `claude-unreal-holodeck`) MUST
import from `project_rag.embed`. This module is a thin re-export layer; it
contains no logic.

```python
from project_rag.embed import (
    EmbedClient,
    EmbedSidecarUnavailable,
    EmbedSidecarVRAMExhausted,
    EmbedSidecarBusy,
    EmbedSidecarWarming,
    EMBED_MODEL_NAME,
    EMBED_MODEL_REVISION,
)
```

### `EmbedClient`

Sidecar-routed HTTP client for the embed sidecar process (port 43841).
Constructor requires `project_root=` (or `PROJECT_RAG_PROJECT_ROOT` env var).

```python
with EmbedClient(project_root="/path/to/project") as client:
    embedding = client.encode_query("my query")
    health    = client.health()
```

**Plugin consumers MUST use the sidecar path.** In-process model loading
(`core.embed.get_embed_model`) bypasses VRAM coordination and is documented
as not-for-plugins (see DR-2 in `CLAUDE.md`).

### Typed errors

| Exception | When raised |
|---|---|
| `EmbedSidecarUnavailable` | Connection failure after 3 respawn attempts |
| `EmbedSidecarVRAMExhausted` | HTTP 503 with `verdict="vram_unavailable"` after retries |
| `EmbedSidecarBusy` | HTTP 503 with `sidecar_verdict="busy"` after 2 retries |
| `EmbedSidecarWarming` | HTTP 503 with `sidecar_verdict="warming"` (no retries) |

### Model identity constants

| Constant | Value | Description |
|---|---|---|
| `EMBED_MODEL_NAME` | `"nomic-ai/CodeRankEmbed"` | HuggingFace model path |
| `EMBED_MODEL_REVISION` | `"3c4b608"` | Audited commit pin (single source of truth) |

These constants match the sidecar's pinned model. A consumer can compare
`EMBED_MODEL_NAME` / `EMBED_MODEL_REVISION` against a running sidecar's
`client.health()["model_name"]` / `["model_revision"]` to detect version drift.

---

## Stable surface — `project_rag.chunk_limits`

Plugin consumers (e.g. `project-rag-ue-addon`, future Python/TS/Rust producers) MUST
import from `project_rag.chunk_limits`. This module is a thin re-export layer; it
contains no logic.

```python
from project_rag.chunk_limits import (
    MAX_CHUNK_CHARS,
    MAX_CHUNK_TOKENS,
    is_oversized,
)
```

### `MAX_CHUNK_CHARS`

Maximum conformant chunk length in characters (`1800`). Char-primary: bytes-on-disk
is the seam's canonical quantity, token counts are corpus-specific.

### `MAX_CHUNK_TOKENS`

Derived token ceiling (`MAX_CHUNK_CHARS // 4 = 450`). The 4-chars-per-token
heuristic is a single derivation point; non-UE corpora that need a different ratio
pass a custom `is_oversized` callable to `write_chunk` rather than re-deriving
this constant.

### `is_oversized`

Strict-greater char predicate: `len(text) > max_chars`. Default `max_chars=MAX_CHUNK_CHARS`.
Per-corpus producers pass a corpus-specific predicate to
`write_chunk(..., is_oversized=...)` (Python tiktoken, TS real tokenizer, etc.)
without touching this default.

---

## Internal surfaces — do NOT import from plugins

| Module | What it contains | Why internal |
|---|---|---|
| `core.embed_client` | `EmbedClient` implementation, typed errors | Implementation module; stable contract lives in `project_rag.embed` |
| `core.embed` | In-process model loader (`get_embed_model`), BM25 tokenizer, batch utilities, `EMBED_MODEL_NAME` / `EMBED_MODEL_REVISION` | In-process loader bypasses sidecar VRAM coordination; not safe for plugins |
| `core.chunk_limits` | `MAX_CHUNK_CHARS`, `MAX_CHUNK_TOKENS`, `is_oversized` | Implementation module; stable contract lives in `project_rag.chunk_limits` |

In-tree code (MCP server, indexer, semantic search) continues to import from
`core.embed_client` directly — the re-export is purely for plugin consumers.

---

## Shadow guard

`tests/test_published_embed_api.py` includes a path-anchored assertion:

```python
Path(importlib.metadata.distribution('project-rag').locate_file('project_rag/embed.py')).resolve()
```

This assertion fails loudly if a foreign PyPI distribution named `project-rag`
shadows the local install. If you see this failure:

1. `pip show project-rag` — check `Location:` vs. this repo root.
2. `pip uninstall project-rag` — remove the foreign package.
3. `pip install -e .` — reinstall from source.

---

## PyPI name status

As of 2026-05-09: `https://pypi.org/pypi/project-rag/json` returns HTTP 404 —
the name `project-rag` is not registered on PyPI. The shadow guard test is
therefore currently only a guard against accidental local installs of a
same-named package via pip. OSS publish timeline: deferred to the addon
carve-out OSS-publish phase (see `docs/ROADMAP.md §"Post-refactor direction"`).
