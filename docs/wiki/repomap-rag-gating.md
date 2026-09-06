---
name: repomap-rag-gating
status: active
spec_backlink: archive/specs/2026-05/2026-05-09-skill-consolidation-pass.md
---

# Repomap RAG-Gating Contract

**Purpose:** Define the three-tier behavior contract that governs when `generate-repomap.py`
is invoked. Every caller (update-docs, enrich-and-review, project-orientation hook) gates via
`check-rag-state.py` before invoking the generator. This wiki is the single source of truth
for the gating doctrine; callers reference it rather than embedding the logic inline.

Spec backlink: `archive/specs/2026-05/2026-05-09-skill-consolidation-pass.md § T2`

---

## Canonical output path

The generator writes to **`<project>/.claude/repomap.md`** when `--output` is unspecified (`generate-repomap.py` resolves the `None` default to this path; the file is gitignored/regenerable, co-located with `.claude/repomap-cache/`). All callers and consumers — including the `project-orientation.py` staleness banner — read this path. Do **not** place it under `state/`: that directory is tracked session substrate, and a gitignored regenerated artifact does not belong there.

---

## Why Gating Exists

Reindexing a large project-RAG takes 5–30 minutes; repomap generation takes seconds. When RAG
is fresh, repomap is redundant overhead — callers should skip it and rely on `mcp__*project-rag*`
tools for structural lookups. When RAG is stale or absent, repomap is a fast, valuable
orientation artifact that costs almost nothing to regenerate.

The gating contract balances these costs across three states.

---

## Three-Tier Behavior Table

| RAG State | `check-rag-state.py` output | Action | Notes |
|-----------|----------------------------|--------|-------|
| **RAG absent** | `absent` | **Generate unconditionally.** | Repomap is the primary structural orientation artifact. |
| **RAG present + stale or uninitialized** | `stale` or `unknown` | **Generate as fallback stopgap.** Note in run report: "Generated as RAG-fallback — RAG is present but stale." | EM chooses repomap-vs-reindex per session based on time budget. |
| **RAG present + fresh** | `fresh` | **Skip generation.** Report: "Repomap skipped — project-RAG is present and fresh. Use `mcp__*project-rag*` tools for structural lookups." | Exit cleanly — this is the happy path in RAG-enabled sessions. |

**`unknown` maps to the stale branch** — conservative fallback. Generating when uncertain is
cheaper than silently omitting orientation data.

---

## Caller Pattern

Every caller follows this exact sequence. Do not embed variant logic — gate uniformly.

> **Variable convention:** `${CLAUDE_PLUGIN_ROOT}` is the variable Claude Code injects into command and skill bodies; `PLUGIN_ROOT` is internal to individual shell scripts that compute it from their own location. Callers resolve it through the guarded `$_cc_root` form (guard doctrine: CLAUDE-PLUGIN-ROOT-SOURCE-GUARD, `coordinator/docs/wiki/coordinator-tripwires/draft-plan-aging.md`, Variant A fail-loud) before executing anything under it — never dereference `${CLAUDE_PLUGIN_ROOT}` directly in an executable invocation.

```bash
# 0. Resolve + validate the trusted root (guard doctrine: CLAUDE-PLUGIN-ROOT-SOURCE-GUARD, coordinator/docs/wiki/coordinator-tripwires/draft-plan-aging.md)
# POSIX-host form; a PowerShell host resolves the trusted root by its own PowerShell-native path.
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/machine-local/.doe-root" 2>/dev/null || cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/machine-local/.doe-root" 2>/dev/null || true)"
if [ -z "$_cc_doe" ]; then
  _cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
fi
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }

# 0b. Resolve the claude-klabauter root — check-rag-state.py / generate-repomap.py migrated there
# (coordinator bin/lib -> claude-klabauter, commit b644d5a9).
_cc_claude_klabauter="${REPO_CLAUDE_KLABAUTER:-${COORDINATOR_ENGINE_ROOT:-}}"
if [ -z "$_cc_claude_klabauter" ]; then
  _cc_claude_klabauter="$(python3 "$_cc_root/hooks/scripts/_engine_root.py" 2>/dev/null)"
fi
if [ -z "$_cc_claude_klabauter" ] || [ ! -d "$_cc_claude_klabauter" ]; then
  echo "ERROR: claude-klabauter root unresolved (checked REPO_CLAUDE_KLABAUTER, CLAUDE_KLABAUTER_ROOT, and the coordinator settings-home registry/pointer via _engine_root.py) — set REPO_CLAUDE_KLABAUTER, or run: machine-local set repos.claude_klabauter <path>" >&2
  exit 1
fi

# 1. Detect RAG state
RAG_STATE=$(python "$_cc_claude_klabauter/coordinator/bin/check-rag-state.py" 2>/dev/null || echo "unknown")

# 2. Gate on state
case "$RAG_STATE" in
  fresh)
    echo "Repomap skipped — project-RAG is present and fresh."
    ;;
  absent|stale|unknown)
    # Generate (stale/unknown → note it as RAG-fallback if RAG_STATE != absent)
    python "$_cc_claude_klabauter/coordinator/bin/generate-repomap.py"
    if [ "$RAG_STATE" != "absent" ]; then
      echo "Note: Repomap generated as RAG-fallback (RAG state: ${RAG_STATE})."
    fi
    ;;
esac
```

### Hook-context callers (project-orientation.py)

Hook scripts run at session open and must NOT block it. Wrap the entire gate-and-generate
block in a guard that exits 0 on any failure:

```bash
(
  # Advisory-hook resolve (Variant B, fail-open — SSOT: coordinator/snippets/cc-root-source-guard.md).
  # Never hard-exits; a hook must not terminate the hook chain on an untrusted/unresolved root.
  # POSIX-host form; a PowerShell host resolves the trusted root by its own PowerShell-native path.
  _cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/machine-local/.doe-root" 2>/dev/null || cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
  _cc_doe="$(cat "${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/machine-local/.doe-root" 2>/dev/null || true)"
  if [ -z "$_cc_doe" ]; then
    _cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
  fi
  _cc_doe="${_cc_doe%/}"
  _cc_trusted=0
  case "$_cc_root" in
    "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
  esac
  [ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
  case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac
  [ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1
  [ "$_cc_trusted" = 1 ] || { [ -n "$_cc_root" ] && [ -d "$_cc_root" ] && echo "[coordinator] WARNING: '$_cc_root' outside trusted prefix — hook degraded" >&2; _cc_root=''; }

  # Resolve the claude-klabauter root — fail-open (never hard-exit; a hook must not
  # terminate the hook chain), but DO emit a diagnostic on failure rather than
  # silently swallowing it (P1 fix — the prior `2>/dev/null || true` shape gave
  # zero signal when the gate silently no-op'd on a stale/unresolvable claude-klabauter root).
  _cc_claude_klabauter=""
  if [ -n "$_cc_root" ]; then
    _cc_claude_klabauter="${REPO_CLAUDE_KLABAUTER:-${COORDINATOR_ENGINE_ROOT:-}}"
    if [ -z "$_cc_claude_klabauter" ]; then
      _cc_claude_klabauter="$(python3 "$_cc_root/hooks/scripts/_engine_root.py" 2>/dev/null)"
    fi
    if [ -z "$_cc_claude_klabauter" ] || [ ! -d "$_cc_claude_klabauter" ]; then
      echo "[coordinator] WARNING: claude-klabauter root unresolved — repomap-rag-gating hook degraded (checked REPO_CLAUDE_KLABAUTER, CLAUDE_KLABAUTER_ROOT, and the coordinator settings-home registry/pointer via _engine_root.py)" >&2
      _cc_claude_klabauter=""
    fi
  fi

  RAG_STATE=$([ -n "$_cc_claude_klabauter" ] && python "$_cc_claude_klabauter/coordinator/bin/check-rag-state.py" 2>/dev/null || echo "unknown")
  case "$RAG_STATE" in
    fresh) ;;
    *)
      if [ -n "$_cc_claude_klabauter" ]; then
        python "$_cc_claude_klabauter/coordinator/bin/generate-repomap.py" 2>&1 >/dev/null | while IFS= read -r _line; do
          echo "[coordinator] WARNING: generate-repomap.py: $_line" >&2
        done
      fi
      ;;
  esac
) || true
```

---

## Determining RAG Freshness

`check-rag-state.py` probes two bash-readable signals in order:

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
it appends an audit log entry to `state/repomap-audit.log`:

```
<ISO-date> | rag_state=<state> | generated=yes | unique_value=<yes|no|unknown>
```

After two consecutive `no` entries, `/update-docs` surfaces a retirement recommendation.
The generator script itself does not audit — auditing is an `/update-docs` concern.

---

## RAG-State Detection Sync Note

The detection logic in `check-rag-state.py` and the marker written by
`hooks/project-rag-detect.*` (W1 hook) must stay in sync. If you change the marker
file path or content format in one, update the other. The marker file path is
`tasks/.rag-state` relative to the plugin root (or overridden by
`CLAUDE_RAG_STATE_FILE` env var).
