---
segment_id: dirty-tree
case: dirty-tree
class: protected
order: 40
---

## Dirty-Tree Case-(c) Disposition

The assembler's `j-dirty-tree-case-c` judgment point surfaces the fact (uncommitted paths) — computed by `coordinator_core.ops.dirty_tree_gate` (`dirty-tree-gate.py`), runnable directly before the terminating commit via (Shape W,
`snippets/resolve-coordinator-bin.md`) `& "$env:COORDINATOR_SETTINGS_HOME\bin\dirty-tree-gate.exe" --terminator handoff`; attribution is yours. Classify every dirty path as (a) yours, (b) a named concurrent owner's, or (c) unattributable — and never terminate with a case-(c) path still dirty and unnamed. For a genuine (c):

1. **Commit with provenance** if the change is coherent and you can attribute it.
2. **Stash with provenance** if it is incoherent or risky to commit — name the stash so the next session can find and adjudicate it.
3. **Explicit "leave it owned by X"** only when you can now name the owner, converting it from case (c) to case (b).

Orphan `.tmp.<pid>.<nanos>` files are a special case (Edit-tool atomic-write crash) — diff against target before deleting; do not stash them blind.

---

## Safe-Commit Auto-Commit

Before hand-classifying the dirty tree above, run the auto-commit mechanism — it does the (a)/(b) attribution AND the commit+push mechanically, leaving only genuine case-(c) paths for your judgment. Run (Shape W, `snippets/resolve-coordinator-bin.md` § The door) `& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-invoke.exe" session.safe_commit_offer '{"cwd":"<repo-root>","session_id":"<this session's id>"}'` — it computes this session's safe pathspec (this session's own touch-list claims, minus anything a live peer session's touch list also claims) and commits+pushes it, then echoes the op's `rendered` field: what landed and why. 

**Pass `session_id` explicitly — the op refuses without it.** Scope is "none", so identity is never taken from the environment, and `cwd` does not supply it either: `cwd` selects which tree is scanned, nothing more. With no explicit `params.session_id` and no carried identity on the wire, the op returns `caller identity could not be established` rather than falling back to the engine process's own environment — that environment belongs to whoever spawned the warm server, so the fallback would commit one session's paths under another's claim. Both params are required in practice: `cwd` for the tree, `session_id` for the identity.

**Payload is one positional JSON string, not `k=v`** — `cwd=<repo> message="<subject>"` does not parse. **Never pass `--repo`**: this op is scope "none" and refuses it (`-32603`). Add `"dry_run": true` to preview; omit it to commit.

**No confirmation step, by explicit PM ruling — do not add one, including behind a flag.** "I get annoyed when I'm asked if there should be a commit or not. y'all are the engineers." Being asked whether to commit was itself the defect. Run it and report the outcome AFTER the fact — never gate the run on an EM/PM yes.

**Grouping: prefer your own judgment over the mechanical default.** Bare invocation (`message` omitted) groups mechanically (by directory, short bounded subject, full path list in the body) — right for an unattended trigger. After deliberate, describable work, author real per-group messages via the `groups` param (an inline list of `{"paths": [...], "message": "..."}` objects, mutually exclusive with `message`) or `message="<subject>"` for one well-described group. Either way, any path you name that ISN'T in the computed safe pathspec is silently dropped — the boundary is computed, never caller-widened.

**A safety net, not the primary path.** Per the PM: "if I have to commit, it's a safety [net] because someone forgot to commit." Keep authoring real commits for real chunks as you go; this exists so nothing is lost when that didn't happen.

**Multi-session overlap on the SAME file is accepted collateral.** No conflict resolution is attempted between two sessions that touched one file — the mechanism exists to stop ONE session's commit from sweeping a peer's UNRELATED work.

**`excluded` paths still need the Dirty-Tree Case-(c) judgment above** — the mechanism narrows what needs attention, it does not replace the classification. `untouched by this session` may still be a genuine case (c); `owned by session <id>` is already case (b).
