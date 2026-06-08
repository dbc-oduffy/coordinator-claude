# Cross-Doctor Routing — Discovery Cascade for Peer-Repo Pointers

**Audience:** doctor / setup / diagnose-style skills that surface peer-repo pointers when an addon or plugin encounters a host-owned failure (peer MCP absent, daemon down, install incomplete).

**Rule (one line):** peer-doctor / peer-install pointer resolution is **cascade-shape**, not constant-shape. Hardcoding a peer path or a GitHub URL alone misses the operator's actual question — "where do I run the peer doctor's setup against source on THIS machine."

---

## The four-rung cascade

When our doctor needs to point an operator at a peer's doctor / setup / repo, resolve via a discovery cascade. Stop at the first hit:

1. **Machine-local registry** — `~/.claude/machine-local/registry.local.toml` `[repos]` keys (e.g. `project_rag`, `project_rag_ue_addon`). If a registered path exists on disk, that is the canonical source clone. `machine-local get repos.<key>` is the reader.
2. **Sibling-relative directory** — `<our-repo>/../<peer-dirname>/`. Convention: peers live alongside in the same parent. If the directory exists and contains the expected marker file (e.g. `pyproject.toml`, `setup.sh`, `.git`), use it.
3. **Grep our own config surfaces** — `~/.claude/CLAUDE.local.md`, our repo's `.mcp.json`, machine-local sentinels. The operator may have a non-canonical path that our config knows about. Stop on first match.
4. **GitHub fallback** — the canonical OSS clone URL (e.g. `gh repo view dbc-oduffy/<peer-name>` or the public clone URL). Right answer when nothing exists locally and the operator needs to clone.

**Each rung returns a pointer to the same operator-facing surface** — typically `(clone_path | None, setup_command, mcp_name, canonical_commands)`. The cascade order is "closest to operator's working state" first.

---

## Why cascade, not constant

A hardcoded peer path is wrong on three axes:

- **Per-machine variance.** `/x/project-rag` on one machine, `~/dev/project-rag` on another, `D:\project-rag` on the third. The registry is per-machine; the cascade reads it.
- **Install state.** Operator may have the peer installed via MCP but no local clone; or a local clone but no MCP wiring; or neither. The cascade discriminates without prompting.
- **Doctor liveness coupling.** If our doctor imports the peer's path constant, the peer's absence from `sys.path` crashes our doctor. The cascade is read-only — failure at one rung falls through to the next.

A constant hides the cascade's first two failure modes silently; the operator gets "follow this path" and then "no such directory" with no remediation.

---

## Implementation shape

The canonical pattern is a single resolver function returning a `PeerPointer` dataclass:

```python
@dataclass(frozen=True)
class PeerPointer:
    slug: str                       # canonical short name ("project_rag", etc.)
    clone_path: Path | None         # local clone if found, else None
    setup_command: list[str]        # argv to invoke their doctor / setup
    mcp_name: str                   # MCP server name (for `claude mcp` calls)
    canonical_commands: dict[str, str]   # "doctor": "...", "setup": "..."
    discovery_rung: int             # 1-4; useful for the operator-facing message

def resolve_peer_repo_pointers(slug: str) -> PeerPointer:
    """Four-rung discovery cascade. Stop at first hit. Never raises;
    a None clone_path with rung==4 is the "operator must clone" signal."""
    ...
```

Per-peer metadata (mcp name, setup command shape, canonical doctor invocation) lives in a registry dict keyed by slug. That registry is the only place new peers get added; the cascade itself is peer-agnostic.

---

## Symmetric pattern across the addon graph

Same cascade applies to:

- holodeck ↔ project-rag (UE-RAG addon)
- project-rag ↔ project-rag-ue-addon (engine corpus)
- coordinator-claude ↔ any plugin's source repo
- Future peers in the graph

The cascade is the primitive; the per-peer dict is the configuration. New peers are one dict entry, not a new code path.

---

## When NOT to use the cascade

- **Reading peer source content** at runtime (e.g. importing peer Python modules). That's a different problem — the cascade resolves *pointers for the operator*, not import paths for our code. For runtime peer code consumption, use `machine-local` registry directly with explicit error if absent.
- **Auto-dispatching a peer doctor.** Cross-doctor coupling breaks fail-open posture — peer failure surfaces as our doctor failure, and the operator's choice of when to act gets bypassed. Surface the pointer via the cascade + a cross-repo memo; the [general PM-as-relay rule](cross-repo-communication.md) applies (no automatic dispatch into the peer's tree, ever).

---

## Source

Pattern formalized 2026-05-21 in addon-doctor-host-routing-pointers-cascade work (project-rag-ue-addon). Canonical implementation: `resolve_peer_repo_pointers()` in the addon's doctor. Lesson promoted from `X:/project-rag-ue-addon/state/lessons.md:356` via `/learn-lessons --mode=central` 2026-05-24.

## Related

- [cross-repo-communication.md](cross-repo-communication.md) — PM-as-relay primitive for cross-repo findings (the no-auto-dispatch rule).
- [machine-local-registry.md](machine-local-registry.md) — Rung 1 source of truth for peer-repo paths.
- [coordinator-doctor.md](coordinator-doctor.md) — general doctor doctrine (probe shapes, fail-open, override-flag hazards).
