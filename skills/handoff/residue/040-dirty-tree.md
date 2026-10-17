---
segment_id: dirty-tree
case: dirty-tree
class: protected
order: 40
---

## Dirty-Tree Case-(c) Disposition

The assembler's `j-dirty-tree-case-c` judgment point surfaces uncommitted paths (`coordinator_core.ops.dirty_tree_gate`, `dirty-tree-gate.py`), runnable before the terminating commit via (Shape W,
`${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`) `& "$env:COORDINATOR_SETTINGS_HOME\bin\dirty-tree-gate.exe" --terminator handoff`; attribution is yours. Classify every dirty path as (a) yours, (b) a named concurrent owner's, or (c) unattributable — and never terminate with a case-(c) path still dirty and unnamed. For a genuine (c):

1. **Commit with provenance** if the change is coherent and you can attribute it.
2. **Stash with provenance** if it is incoherent or risky to commit — name the stash so the next session can find and adjudicate it.
3. **Explicit "leave it owned by X"** only when you can now name the owner, converting it from case (c) to case (b).

Orphan `.tmp.<pid>.<nanos>` files (Edit-tool atomic-write crash): diff against target before deleting; never stash blind.

---

## Safe-Commit Auto-Commit

Before hand-classifying, run the auto-commit mechanism — it does the (a)/(b) attribution and commit+push, leaving only case-(c) paths for you. Run (Shape W, `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md` § The door) `& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-invoke.exe" session.safe_commit_offer '{"cwd":"<repo-root>","session_id":"<this session's id>"}'` — it computes this session's safe pathspec (own touch-list claims minus any a live peer also claims), commits+pushes it, and echoes `rendered`.

**Pass `session_id` explicitly — the op refuses without it**; `cwd` only selects the tree scanned. **Payload is one positional JSON string, not `k=v`. Never pass `--repo`** (refused `-32603`). Add `"dry_run": true` to preview.

**No confirmation step, by explicit PM ruling — do not add one, including behind a flag.** Run it and report the outcome AFTER the fact.

**Grouping: prefer your own judgment over the mechanical default** (bare invocation groups by directory). Author per-group messages via `groups` (a list of `{"paths": [...], "message": "..."}`, exclusive with `message`) or `message="<subject>"` for one group. A path you name outside the computed safe pathspec is silently dropped.

**A safety net, not the primary path.** Keep authoring real commits for real chunks. Two sessions touching the SAME file is accepted collateral; no conflict resolution is attempted.

**`excluded` paths still need the Case-(c) judgment above:** `untouched by this session` may still be case (c); `owned by session <id>` is case (b).
