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

**The route is the op `ceremony.commit_v2`, INVOKED — `coordinator-invoke ceremony.commit_v2
'{...}'`, or the `python3 -m coordinator_core.invoke` spelling of it.** It runs
`coordinator_core.git.commit.commit_paths` underneath, but naming that function is not naming the
route: `block_subagent_commit` reads literal argv and does not unwrap `python -c` payloads, so an
in-process `commit_paths` import is DENIED for a subagent however faithfully it reproduces the
call. Name the invocation, not the function that ends up running.
`run_commit_pipeline` is gone — killed at the process-time bar, not deprecated, so an import of
`coordinator_core.ops.ceremony.commit_pipeline` raises `ModuleNotFoundError`. Its replacement
builds a tree from the explicit paths handed to it rather than reading the index, which is what
makes it incapable of sweeping a peer's staged work.

Parameters: `paths` (repo-relative, list), `message`, `deleted_paths` (list), `prefer_staged`
(list), `repo` (the repo root — **not** `repo_root`; that keyword raises `TypeError`). At least
one of `paths` / `deleted_paths` is required. Always pass `blob_fallback=partial(
hash_worktree_blobs_via_spawn, cwd=<repo root>)` — without it, a path carrying CR bytes under a
`text`/`text=auto`/`eol=` attribute (also LFS clean-filter paths, unresolved `[attr]` macros)
raises `FilterUnsupported` and nothing lands. Which files those are is a property of the repo's
`.gitattributes`, not of the OS: here `* text=auto` with `*.md` unpinned means every markdown
file refuses on a CRLF checkout, while LF-pinned `.py`/`.json`/`.yaml`/`.sh` pass in process.
Pass it unconditionally rather than predicting your pathspec's composition.

**A deletion goes in `deleted_paths`, never in `paths`.** A deleted path passed as `paths` reaches
`commit_paths`' own `read_bytes` and comes back
`cannot read <path>: [Errno 2] No such file or directory` — which reads as the op being unable to
commit deletions at all. It can; the parameter is the whole difference.

**The validation surface did not survive, and never lived here.** The retired op was 2058 lines
with a single call into the pipeline; the other ~2000 were its own `_reject_sweeping_pathspec`,
its stale-index, path-shaped-message and directory-expansion rejections, and the
ledger/declined-paths envelope. None of that moved to the replacement either. **A caller who hands
a sweeping or stale pathspec will not be stopped** — verify the pathspec yourself before calling.

**No gate fires inside a commit any more — deliberately, and it is not a capability loss for
all four.** `run_commit_pipeline` ran four gates immediately before landing: `deletion_block_gate`,
`dirty_tree_gate`, `carry_gate`, `op_scope_coverage_gate`. It was killed at the 500ms brightline
and the replacement runs none of them. That is recorded, not accidental: claude-klabauter
`docs/plans/2026-08-29-the-push-subsystem-leaves-and-then-the-pipeline-can-go.md` § C4, with the
exposure tracked at `state/bug-backlog/2026-08-29-the-commit-v2-route-runs-none-of-the-fou-3e8811d511b7.yaml`.

**Unwired is not absent, and the difference decides what you do about it.** Two of the four keep a
standalone route you can run by hand:

- `deletion_block_gate` — live via `commit_gates.main()`, reached by
  `coordinator/bin/check-workstream-complete-deletion-blocks`. The Step-2.67 Kept/Deleted claim
  check still exists; it just no longer fires automatically inside your commit.
- `carry_gate` — live via `baton_assemble/apply.py`'s `_dispatch_handoff_carry_gate` (over the
  PREDECESSOR's array only) and the standalone `coordinator/bin/handoff-carry-gate` CLI.
- `dirty_tree_gate` — **no caller anywhere.** Nothing imports it, no CLI reaches it, only its own
  tests. `commit_paths` building its tree from explicit paths subsumes part of what it protected,
  which is likely why it went quietly.
- `op_scope_coverage_gate` — in `commit_gates.py`, with no in-commit caller.

So: **verifying the pathspec yourself is the only automatic check on a commit today**, and the two
standalone gates above are opt-in — run them when the commit warrants it. Do not reinstate the
gates inline on your own initiative: they were dropped for measured process cost, and the tracked
proposal is a spike measuring each in-process before choosing a shape. Read the live state off
source rather than this list — `grep -n "_gate(" coordinator_core/ops/ceremony/commit_v2.py
coordinator_core/git/commit.py`, and `commit_gates.py`'s own module docstring, which now opens
with why it has no in-commit caller. A list of gate names here is a pinned constant standing in
for a property (`A-PINNED-CONSTANT-STANDING-IN-FOR-A-PROPERTY`) — which is exactly how the earlier
text came to promise gates that no longer run.


`deletion_block_gate` was the gate built to adjudicate a commit that removes a path, and it no
longer runs on any route — so a deletion is now adjudicated by the caller's own pathspec check
and nothing else. If you invoke a gate in-process for a reason, **say which and why in the commit
message**; a gate is a recorded decision, never a silent consequence of which call you picked.
Pathspec discipline is the whole point on a tree shared with a dozen live peers —
a hand-written `git commit -m <subj> -- <paths>` reads the **worktree** for the named paths and
silently discards your staging, which is the recurring incident this machinery exists to prevent
(tripwire `OFFER-PATHSPEC-DIVERGENCE`).

**So: no hand-rolled equivalent.** If you cannot dispatch, invoke `ceremony.commit_v2` — not
`commit_scoped`, not a reconstruction of its horn-picking, and never a bare `git commit`, which
commits the whole shared index including a peer's staged work.

**Committing by pathspec anyway? Preview with `git diff HEAD -- <paths>`** — the commit re-reads
the worktree *at commit time*, and a peer can write into your path in between. Not
`git diff --cached`: a pathspec commit bypasses the index, so it reads empty for the path at risk
(measured: 7+/7- versus nothing). Knowing the rule does not replace the preview — this exists
because a session told a file held a peer's edits committed it by pathspec minutes later.

A restore of `ceremony.scoped_git_commit` is a live rebuild candidate. If it lands under the same
name, this snippet changes and the citing bodies do not.
