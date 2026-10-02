---
segment_id: dirty-tree
case: dirty-tree
class: protected
order: 40
---

## Dirty-Tree Case-(c) Disposition

The assembler's `j-dirty-tree-case-c` judgment point surfaces the fact (uncommitted paths) — computed by `coordinator_core.ops.dirty_tree_gate` (`dirty-tree-gate.py`), runnable directly before the terminating commit via (Shape W,
`${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`) `& "$env:COORDINATOR_SETTINGS_HOME\bin\dirty-tree-gate.exe" --terminator handoff`; attribution is yours. Classify every dirty path as (a) yours, (b) a named concurrent owner's, or (c) unattributable — and never terminate with a case-(c) path still dirty and unnamed. For a genuine (c):

1. **Commit with provenance** if the change is coherent and you can attribute it.
2. **Stash with provenance** if it is incoherent or risky to commit — name the stash so the next session can find and adjudicate it.
3. **Explicit "leave it owned by X"** only when you can now name the owner, converting it from case (c) to case (b).

Orphan `.tmp.<pid>.<nanos>` files (Edit-tool atomic-write crash): diff against target before deleting; never stash blind.

---

## Safe-Commit Auto-Commit

Before hand-classifying the dirty tree above, run the auto-commit mechanism — it does the (a)/(b) attribution AND the commit+push mechanically, leaving only genuine case-(c) paths for your judgment. Run (Shape W, `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md` § The door) `& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-invoke.exe" session.safe_commit_offer '{"cwd":"<repo-root>","session_id":"<this session's id>"}'` — it computes this session's safe pathspec (own touch-list claims minus any a live peer also claims), commits+pushes it, and echoes `rendered`.

**Pass `session_id` explicitly — the op refuses without it** (`caller identity could not be established`): identity is never taken from the environment, and `cwd` only selects the tree scanned.

**Payload is one positional JSON string, not `k=v`. Never pass `--repo`** (scope "none"; refused `-32603`). Add `"dry_run": true` to preview; omit it to commit.

**No confirmation step, by explicit PM ruling — do not add one, including behind a flag.** Run it and report the outcome AFTER the fact — never gate the run on an EM/PM yes.

**Grouping: prefer your own judgment over the mechanical default.** Bare invocation (`message` omitted) groups mechanically by directory. After deliberate, describable work, author per-group messages via the `groups` param (an inline list of `{"paths": [...], "message": "..."}` objects, mutually exclusive with `message`) or `message="<subject>"` for one group. Any path you name that ISN'T in the computed safe pathspec is silently dropped.

**A safety net, not the primary path.** Keep authoring real commits for real chunks as you go. Two sessions touching the SAME file is accepted collateral — no conflict resolution is attempted.

**`excluded` paths still need the Case-(c) judgment above:** `untouched by this session` may still be a genuine case (c); `owned by session <id>` is already case (b).
