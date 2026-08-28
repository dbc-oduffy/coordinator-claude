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
its stale-index, path-shaped-message and directory-expansion
rejections, and the ledger/declined-paths envelope. None of that moved. **A caller who
hands the pipeline a sweeping or stale pathspec will not be stopped** — verify the pathspec
yourself before calling, and anyone rebuilding the op as a wrapper over the pipeline silently drops
all of it. The pipeline
is the route — its own docstring is "Run the full stage -> gate -> commit -> [push] critical
section". It calls `git_native.commit_scoped`, which chooses between the agree-case pathspec form
and a private-index commit by reading observed index/worktree state, **and** it runs the commit gates.

**Read the gates off source, never off prose** — they are the `*_gate(` calls in
`run_commit_pipeline`'s own body, in the engine at
`coordinator_core/ops/ceremony/commit_pipeline.py`. A list here would be a pinned constant
standing in for a property: right the day written, silent the day a gate is added
(`A-PINNED-CONSTANT-STANDING-IN-FOR-A-PROPERTY`).


Calling `commit_scoped` directly gets you the staging safety and **silently skips every one**. The
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

**Committing by pathspec anyway? Preview with `git diff HEAD -- <paths>`** — the commit re-reads
the worktree *at commit time*, and a peer can write into your path in between. Not
`git diff --cached`: a pathspec commit bypasses the index, so it reads empty for the path at risk
(measured: 7+/7- versus nothing). Knowing the rule does not replace the preview — this exists
because a session told a file held a peer's edits committed it by pathspec minutes later.

A restore of `ceremony.scoped_git_commit` is a live rebuild candidate. If it lands under the same
name, this snippet changes and the citing bodies do not.
