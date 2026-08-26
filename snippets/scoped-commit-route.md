# Scoped commit route

> Cited by path from skill and command bodies wherever a ceremony step commits. One rule, one
> place to change it — the route below has already moved once and will move again.

**Commit exactly the paths you own, never a sweep.** `git add -A`, `git add .`, `git add -u`, and
`git commit -a` are forbidden at every ceremony seam, in every posture, with no override. That
rule is invariant; only the mechanism underneath it changes.

## The route

**Dispatch `git-commit-agent` with an explicit pathspec.** It is the one dispatchable committer,
it verifies the pathspec before staging, and it already carries both legs of the current mechanism
split — you do not reproduce that logic in a skill body. Hand it the enumerated paths and the
subject; it refuses an unbounded or missing pathspec rather than guessing.

## Why the mechanism is not named here

`ceremony.scoped_git_commit` is **retired** — the op, its trampoline, and its tests are deleted in
the engine repo's relocation ledger. The `scoped-git-commit` launchers survive under the
settings-home `bin/` and are dead: they point at helpers deleted from the engine tree and fail with
a helper-missing error (exit 127 on every host measured), **not** the `-32006` the kill-switch
contract prescribes. A caller written against that contract handles the wrong failure shape. Never
route a ceremony commit through those launchers.

**The staging property survives; the validation surface did not.**
`coordinator_core.ops.ceremony.commit_pipeline.run_commit_pipeline` is intact and is the route. But
the retired op was not a thin wrapper over it — it was 2058 lines with a single call into the
pipeline, and the other ~2000 were its own: `_reject_sweeping_pathspec`,
`_reject_stale_index_paths`, `_reject_path_shaped_message`, `_expand_directory_pathspecs`,
`_classify_uncommitted`, and the ledger/declined-paths envelope. None of that moved. **A caller who
hands the pipeline a sweeping or stale pathspec will not be stopped** — verify the pathspec
yourself before calling, and anyone rebuilding the op as a wrapper over the pipeline silently drops
all of it. The pipeline
is the route — its own docstring is "Run the full stage -> gate -> commit -> [push] critical
section". It calls `git_native.commit_scoped`, which chooses between the agree-case pathspec form
and a private-index commit by reading observed index/worktree state, **and** it runs the commit
gates — at time of writing five: `branch_gate`, `dirty_tree_gate`, `deletion_block_gate`,
`carry_gate`, `op_scope_coverage_gate`.

**Read them off source rather than trusting that list** — it is prose, and prose rots the way
the op names above rotted. The gates are the `*_gate(` calls in `run_commit_pipeline`'s own
body, in the engine at `coordinator_core/ops/ceremony/commit_pipeline.py`; that body is the
count, and this paragraph is not.


Calling `commit_scoped` directly gets you the staging safety and **silently skips all five**. The
failure is quiet and shaped like success, so it will not announce itself: a commit that removes a
path bypasses `deletion_block_gate`, the gate built to adjudicate exactly that. If you have a
named reason to call `commit_scoped` anyway, invoke the gates you need in-process and **say which
you skipped and why in the commit message** — a skipped gate is a recorded decision, never a
silent consequence of picking the cheaper call. That choice is the whole point on a tree shared with a dozen live peers —
a hand-written `git commit -m <subj> -- <paths>` reads the **worktree** for the named paths and
silently discards your staging, which is the recurring incident this machinery exists to prevent
(tripwire `OFFER-PATHSPEC-DIVERGENCE`).

**So: no hand-rolled equivalent.** If you cannot dispatch, call `run_commit_pipeline` — not
`commit_scoped`, not a reconstruction of its horn-picking, and never a bare `git commit`, which
commits the whole shared index including a peer's staged work.

A restore of `ceremony.scoped_git_commit` is a live rebuild candidate. If it lands under the same
name, this snippet changes and the citing bodies do not.
