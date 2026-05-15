---
name: repomap-rag-gating
status: canonical
spec_backlink: docs/plans/2026-05-09-skill-consolidation-pass.md
---

# Repomap RAG-Gating Contract

**Purpose:** Define the three-tier behavior contract that governs when `bin/generate-repomap.sh`
is invoked. Every caller (update-docs, enrich-and-review, project-orientation hook) gates via
`bin/check-rag-state.sh` before invoking the generator. This wiki is the single source of truth
for the gating doctrine; callers reference it rather than embedding the logic inline.

Spec backlink: `docs/plans/2026-05-09-skill-consolidation-pass.md § T2`

---

## Why Gating Exists

Reindexing a large project-RAG takes 5–30 minutes; repomap generation takes seconds. When RAG
is fresh, repomap is redundant overhead — callers should skip it and rely on `mcp__*project-rag*`
tools for structural lookups. When RAG is stale or absent, repomap is a fast, valuable
orientation artifact that costs almost nothing to regenerate.

The gating contract balances these costs across three states.

---

## Three-Tier Behavior Table

| RAG State | `check-rag-state.sh` output | Action | Notes |
|-----------|----------------------------|--------|-------|
| **RAG absent** | `absent` | **Generate unconditionally.** | Repomap is the primary structural orientation artifact. |
| **RAG present + stale or uninitialized** | `stale` or `unknown` | **Generate as fallback stopgap.** Note in run report: "Generated as RAG-fallback — RAG is present but stale." | EM chooses repomap-vs-reindex per session based on time budget. |
| **RAG present + fresh** | `fresh` | **Skip generation.** Report: "Repomap skipped — project-RAG is present and fresh. Use `mcp__*project-rag*` tools for structural lookups." | Exit cleanly — this is the happy path in RAG-enabled sessions. |

**`unknown` maps to the stale branch** — conservative fallback. Generating when uncertain is
cheaper than silently omitting orientation data.

---

## Caller Pattern

Every caller follows this exact sequence. Do not embed variant logic — gate uniformly.

> **Variable convention:** `${CLAUDE_PLUGIN_ROOT}` is the variable Claude Code injects into command and skill bodies; `PLUGIN_ROOT` is internal to individual shell scripts that compute it from their own location. Use `${CLAUDE_PLUGIN_ROOT}/coordinator` in caller bodies.

```bash
# 1. Detect RAG state
RAG_STATE=$(bash "${CLAUDE_PLUGIN_ROOT}/coordinator/bin/check-rag-state.sh" 2>/dev/null || echo "unknown")

# 2. Gate on state
case "$RAG_STATE" in
  fresh)
    echo "Repomap skipped — project-RAG is present and fresh."
    ;;
  absent|stale|unknown)
    # Generate (stale/unknown → note it as RAG-fallback if RAG_STATE != absent)
    bash "${CLAUDE_PLUGIN_ROOT}/coordinator/bin/generate-repomap.sh"
    if [ "$RAG_STATE" != "absent" ]; then
      echo "Note: Repomap generated as RAG-fallback (RAG state: ${RAG_STATE})."
    fi
    ;;
esac
```

### Hook-context callers (project-orientation.sh)

Hook scripts run at session boot and must NOT block it. Wrap the entire gate-and-generate
block in a guard that exits 0 on any failure:

```bash
(
  RAG_STATE=$(bash "${CLAUDE_PLUGIN_ROOT}/coordinator/bin/check-rag-state.sh" 2>/dev/null || echo "unknown")
  case "$RAG_STATE" in
    fresh) ;;
    *) bash "${CLAUDE_PLUGIN_ROOT}/coordinator/bin/generate-repomap.sh" 2>/dev/null || true ;;
  esac
) || true
```

---

## Determining RAG Freshness

`bin/check-rag-state.sh` probes two bash-readable signals in order:

1. **`RAG_STATE` env var** — injectable in tests and by the W1 session-init hook.
2. **`tasks/.rag-state` marker file** — written by `hooks/project-rag-detect.*` (W1 hook)
   at session start. Content is one of `absent | stale | fresh`.

If neither signal is present, the script prints `unknown` and exits non-zero.

**Rationale for marker-file approach:** MCP tool availability cannot be probed from bash.
The W1 hook (which runs in agent context where MCP is visible) writes the marker; subsequent
bash scripts read it. This separates detection (agent-side, once) from consumption (bash,
multiple callers).

---

## Audit Log (update-docs Phase 10b)

When `/update-docs` generates repomap as a RAG-fallback (`RAG_STATE` is `stale` or `unknown`),
it appends an audit log entry to `tasks/repomap-audit.log`:

```
<ISO-date> | rag_state=<state> | generated=yes | unique_value=<yes|no|unknown>
```

After two consecutive `no` entries, `/update-docs` surfaces a retirement recommendation.
The generator script itself does not audit — auditing is an `/update-docs` concern.

---

## RAG-State Detection Sync Note

The detection logic in `bin/check-rag-state.sh` and the marker written by
`hooks/project-rag-detect.*` (W1 hook) must stay in sync. If you change the marker
file path or content format in one, update the other. The marker file path is
`tasks/.rag-state` relative to the plugin root (or overridden by
`CLAUDE_RAG_STATE_FILE` env var).
