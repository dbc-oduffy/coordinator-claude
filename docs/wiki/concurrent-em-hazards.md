# Concurrent-EM Hazards

**System:** coordinator
**Last Updated:** 2026-05-27 (created — bucket-A learn-lessons consolidation)
**Siblings:** [`scoped-safety-commits.md`](./scoped-safety-commits.md) (commit *content* — which files/hunks), [`daily-branch-discipline.md`](./daily-branch-discipline.md) (commit *location* — which branch), [`cross-repo-communication.md`](./cross-repo-communication.md) (cross-repo + same-repo session coordination).

---

## What this page is

The canonical narrative on the failure class that arises when **multiple EM (Claude Code) sessions share one working tree on one shared workstream branch**. The two sibling wikis own the *enforcement surfaces* (the commit helper, the branch hook). This page owns the *hazard catalog* — the symptom-indexed list of ways a shared tree bites you, the recovery procedures when it already has, and the read-side hygiene that keeps two sessions from clobbering each other.

This is one of the highest-recurrence lesson clusters in the system (≈40 distinct queue entries folded here). The recurrence is the evidence: these hazards re-fire faster than documentation reaches the EM at the moment of the `git` call. **Internalize the catalog; do not expect to look it up mid-incident.**

## The model — a shared bus, not a workspace

The active workstream branch is a **shared bus for every concurrent EM session on the machine**, plus the working tree and index those sessions all mutate. Three facts follow, and almost every hazard below is a corollary of one of them:

1. **The index is shared, last-writer-wins.** Anything you stage sits in the same index a sibling's `git add` / `git commit` / `--blanket` sweep can absorb. Staging is not a private act.
2. **The working tree is shared, last-writer-wins.** An uncommitted edit (` M`, `??`) you hold is overwritten the instant a sibling commits or checks out the same path. Holding an edit uncommitted is a bet that no sibling touches it first.
3. **A same-machine registry peer is addressable, narrowly.** Proven there only — never cross-machine, registry-absent, or a peer's internal state (`status` unverifiable; no trustworthy signal exists yet — see `cross-repo-communication.md` § sync-vs-async gate). Default coordination stays committed artifacts; a live peer is a verified exception. **Cite a peer by its `sessionId`; resolve the display name at the moment you send, never before.** The registry name is `nameSource: derived` — the harness mints it, neither repo owns it, it is unique in neither direction, and it is recycled to a later session once its holder exits. It addresses a process for as long as you hold it and identifies nobody afterwards (`docs/wiki/coordinator-tripwires/a-session-id-is-an-identity-not-an-address.md`).

Sibling commits, sibling dirty files, and a branch that advanced since you oriented are **normal**, not contamination. The discipline is to commit your own work narrowly and immediately, verify what actually landed, and never assume a clean tree.

---

## Hazard Catalog

Indexed by the symptom you'll actually see. Each entry: the trap, why it happens, the rule.

### H1 — `git add` absorbs a sibling's uncommitted edits (commit-content contamination)

**Symptom.** Your commit subject says one workstream; `git show --stat` lists files you never touched.

**Trap.** Any `git add` that names a *directory* (`git add tasks/ docs/`), an *untracked dir* (`git add -- <dir>` recurses into every file under it, including a sibling's 29K-line `diff.patch` or a 423MB sqlite blob), or a *whole shared file* a sibling also edited, stages content that isn't yours. `Edit`-replace-all followed by `git add -- <file>` is blanket-staging by another name — it stages every on-disk hunk, not just yours (one incident absorbed ~290 LOC of a sibling's probe additions). Path-scoped `git add` protects against *cross-file* contamination but not *cross-hunk* contamination within a contested file.

**Rule.**
- Never `git add -A` / `git add .` / `git add <dir>` on a shared branch (~/.claude/CLAUDE.md § Concurrent-EM Git Operations).
- Stage explicit files: `git add -- <file1> <file2>`.
- For a file a sibling also holds dirty, stage by hunk: `git add -p -- <file>` (SC-DR-010, [`scoped-safety-commits.md`](./scoped-safety-commits.md)).
- **`git diff --cached --name-only` before every commit** — read the FULL staged set, not your mental model of it. This single check pre-empts H1, H2, and H10. It is load-bearing, not ceremony.

### H2 — A "no stray staged" check that prints but doesn't halt is theater

**Symptom.** A pre-commit guard echoes the offending foreign path, then the commit runs anyway and re-attributes the sibling's work.

**Trap.** The `grep … || echo "stray!"` shape detects but does not gate. Under concurrent EMs a detect-without-halt check is worse than none — it produces a false sense of safety and a contaminated commit. H2 applies to any *non-blanket* commit guard that detects foreign paths but proceeds anyway.

**Rule.** Gate the commit on the check's exit code (non-zero → unstage with `git rm --cached -- <foreign>` or abort), or stage by explicit file list so the stray never enters the index.

**`git rm --cached` on a tracked path needs the phantom-guard override.** This clone's
`pre-commit` guard refuses a commit deleting a path still in HEAD **and** on disk; a deliberate
`git rm --cached` is byte-identical to that phantom in `git status`, so the guard stops both rather
than invent a distinction the data does not support. Named here, not left to the block message,
because you reach for this mid-incident and a recovery step that fails when you need it is the
advice-unreachable-from-the-triggering-state shape:

    COORDINATOR_OVERRIDE_PHANTOM_STAGED_DELETION=1 git commit -- <paths>

**Never carry it to the `git rm --cached` steps below.** Those untrack **not-in-HEAD** artifacts,
which leave no staged row at all, so the guard cannot fire. The override is per-commit, not
per-path: setting it there disarms **every** path in that commit, re-arming the phantom inside the
incident you are recovering from.

For `--blanket` sweep ceremonies, the blanket path subtracts live-sibling-claimed paths (Foreign set) before staging and unstages them via `git reset HEAD --`. → [`scoped-safety-commits.md`](./scoped-safety-commits.md) § "Carve-Outs and Why" for the blanket-path subtract mechanism.

### H3 — Commit without trailing `-- <pathspec>` is unsafe even after a clean scoped `git add`

**Symptom.** `git commit -m "..."` (no pathspec) lands a sibling's staged files under your subject; or returns *"no changes added to commit"* when you know you just staged work (a sibling commit swept the index between your `add` and `commit`).

**Trap.** Splitting `add` and `commit` across two Bash tool calls opens a window for a sibling's `git add -A` / `--blanket` to mutate the index. Path-scoped `git add` does not scope the *commit*.

**Rule.** Treat stage+commit as one atomic gesture, computed rather than hand-classified: call `ceremony.commit_v2` (claude-klabauter, `coordinator_core/git/commit.py` :: `commit_paths`) with `repo` (the repo root — the keyword is `repo`, not `repo_root`), `paths`, `message` (and `deleted_paths` for anything being removed) — it builds the commit's tree from the paths you name rather than reading the shared index, so a peer's staged work cannot ride along and there is no horn to classify. `ceremony.scoped_git_commit` and `run_commit_pipeline` are both deleted; so are the commit gates they ran, which makes verifying your own pathspec the only check left. If a commit returns "no changes added," the work is likely in the reflog under a sibling's SHA — probe before retrying (see R4). Full mechanism + rationale in [`scoped-safety-commits.md`](./scoped-safety-commits.md) § "Atomic stage+commit gesture" and § SC-DR-015.

**Same-invocation `add`+`commit` is not the protection — the trailing pathspec on `commit` is.** `git add -- <paths> && git commit -m "…"` with no pathspec on the `commit` half still takes the whole shared index, even though the `add` half looks scoped — atomicity of the two calls in one invocation was never the mechanism that protects you. Write the pathspec on `commit` every single time, with no exception for "I just added exactly these" or "it's all one command." When a mix of tracked and untracked files forces a `git add`, write the full pathspec twice: `git add -- $P && git commit -m "…" -- $P`. Tell: if the commit's file count exceeds the number of paths you named, stop and read `git show --stat` before doing anything else.

**The inbound mirror image: anything you stage is available for any peer's next pathspec-less `git commit` to claim.** H1 above covers you absorbing a sibling's uncommitted work; the reverse is just as live and far less intuitive. Content you stage and then leave staged while doing further work can be swept into a CONCURRENT session's plain `git commit`, landing under an unrelated subject line — and your own later commit then finds an empty index and silently no-ops. The content is correct on disk, but attribution and traceback are lost. If a commit reports nothing staged when you believe you staged something, do not read that as "already committed" — run `git log --oneline -3` and find whose commit took it. History-rewriting to un-mix afterwards is worse than the smear on a branch peers are still committing to; report it honestly instead.

**A directory pathspec on a shared-queue dir is pure downside, even when it feels obviously yours.** Lifecycle dirs (`state/memo-outbox/`, `state/handoffs/`, other queue dirs) are the worst offenders: a CLI can add and remove files there on other sessions' behalf between your own calls, so naming the directory in `git add`/`git commit` can contribute zero of your own files while still sweeping in a peer's deletion or addition under your subject. Enumerate files explicitly, even when there are several and the directory feels obviously "mine."

### H4 — A sibling's workstream-complete / blanket sweep absorbs your in-flight edits

**Symptom.** Your uncommitted edits ship inside a sibling's commit; that commit's subject doesn't describe your work. Or your staged handoff `git mv` is reverted by the same sweep.

**Trap.** While you hold an edit uncommitted, a concurrent `/workstream-complete` or `--blanket` sweep stages and commits whatever is dirty in the tree — including your work. This is the inverse of H1 (you're the victim, not the polluter), and it is structurally undefendable from your side once the edit is dirty and unguarded.

**Partial prevention.** The `--blanket` path subtracts live-sibling-claimed paths before staging: paths tracked in your session's `touched.txt` are excluded (unstaged via `git reset HEAD --`) and left in your tree. This means *tracked* in-flight edits are protected from blanket absorption. **Untracked edits (files you modified via Bash, files you haven't yet touched via Edit/Write, or new files not yet `git add`ed) remain at risk** — the mtime-based heuristic may not have recorded them in your `touched.txt`, so they won't appear in the sibling's Foreign exclusion set. The rule below is still the primary defence. (Setting `COORDINATOR_BLANKET_ACCEPT_FOREIGN=1` skips the subtract — see scoped-safety-commits.md § Carve-Outs and Why for when this is legitimate.) → [`scoped-safety-commits.md`](./scoped-safety-commits.md) § "Carve-Outs and Why" for the subtract mechanism; § "Stage Bug-Sweep Fix Edits" for the symmetric treatment.

**Rule.** **Commit shared / hot files explicitly and regularly, on your own authority — never batch them for workstream-complete, and never ask permission to commit.** For known shared buses (`state/lessons/`, `state/improvement-queue/`, shared registration/index files), `git add -- <file> && git commit -m "..." -- <file>` at the next coherent boundary after the edit (agree-case form — see H3's disagree-case caveat if you staged a partial hunk). The window between edit and commit is the attack surface; keep it short.

**A commit is a savepoint for a discrete chunk of work** — something worth logging, safeguarding, tracking, and unwinding atomically if it turns out wrong. That definition sets the cadence: commit when you have such a chunk, which on a hot shared file is usually within a minute or two of the edit anyway. It is not a per-edit trigger. A commit per `Edit` call is its own defect — it destroys the atomic-revert property (the chunk is now scattered across N commits) and every one of those commits takes `.git/index.lock`, turning one session into a lock-contention source for every peer on the tree (H31).

**"Commit often" and "don't ask to commit" are two rules, and only the second is absolute.** Committing is EM remit — never a permission question, never a thing to surface. Cadence is a judgment call the EM owns and should make thoughtfully; the wrong answers are holding everything for workstream-complete and firing a commit per keystroke, and there is a wide correct range between them.

### H5 — Committing a shared registration/index file ships a HEAD that imports untracked modules

**Symptom.** `git add -- __init__.py` (the hookimpl list, plugin registry, module index) sweeps in concurrent sessions' uncommitted registrations whose target modules are still `??` untracked. HEAD now imports modules absent from git — a latent broken-clean-install, masked on the author's disk and (if the loader graceful-fails on ImportError) silently non-registering on a clean checkout.

**Trap.** This is H1 specialized to registration files, with a second-order failure: the absorbed edits introduce `import` statements whose targets you never committed.

**Rule.** Before committing any shared registration/index/`__init__` file under concurrent EMs:
1. `git diff --cached --name-only` — see the full absorbed set (H1 baseline).
2. For every new `import` / `from … import` the commit introduces, confirm the target module is `git ls-files`-tracked. An import of an untracked sibling module is a HEAD-break, not a harmless extra.

If you find absorbed registrations, the fix-forward is to commit the referenced impls+tests too (if complete and green on disk), turning the latent break into a real landing — not to revert the registration. (project-rag-ue-addon tc-34: commit `526ba4705` imported four nonexistent-in-git chunker modules this way.) → cross-link: [`scoped-safety-commits.md`](./scoped-safety-commits.md) H1 staging rules.

### H6 — Blind `git stash pop` reverts committed fixes (the stale-stash trap)

**Symptom.** A crash-day, pickup, or concurrent-session stash looks like unsaved work; popping it reverts fixes that already shipped as committed work.

**Trap.** A stash diff is relative to the stash's *parent*, not HEAD. After HEAD advances (the session continued and committed equivalents through normal flow, or a sibling committed them), the stash's "additions" become *reversions*. The stashed content can be the same bytes as what was committed — but relative to HEAD, applying the stash undoes the commit. A blind pop silently rolls back later commits.

**Rule.** Before popping any stash older than the branch tip, diff each stashed blob against HEAD per file:

```bash
git rev-parse stash@{0}:<f>   # vs  git rev-parse HEAD:<f>   → SAME = redundant, skip
git diff HEAD:<f> stash@{0}:<f>   # on the differs: a hunk that REVERTS a later commit = stale
```

Rescue only genuinely-unique content (e.g. an uncommitted lesson), then `git stash drop` — never blind-pop. (project-rag: `stash@{0}` base `22ad8f53` would have reverted an OOM prereq, a paths-lint routing fix, and an ndcg dedup.) Pairs with CLAUDE.md "Probe edits in git stash push -u / pop." Distinct from H7 (wrong-owner stash trap).

### H7 — Bare `git stash pop` pops a *sibling's* stash (the wrong-owner trap)

**Symptom.** A bare `git stash pop` dumps unrelated content + merge conflicts (e.g. a `DU` on a 423MB `chroma.sqlite3`, a `UU` on `.workday-start-marker`) into your tree.

**Trap.** `stash@{0}` is a single global ref shared across all sessions in the tree — it is NOT scoped to your session. Worse: `git stash push -- <path>` that prints *"No local changes to save"* is a **NO-OP** (often because a sibling already *committed* your edit), so your subsequent bare `pop` reaches past empty and pops the sibling's `stash@{0}`.

**Rule.**
- Before relying on a stash to isolate a change, confirm it's an uncommitted working-tree delta: `git --no-optional-locks status --short <path>` non-empty. Under concurrent EMs your edit may already be committed, making the push a no-op. (A manual-read `git status`/`git diff` takes `.git/index.lock` and contributes to fleet-wide lock contention; `--no-optional-locks` avoids it and must sit between `git` and the subcommand — `git status --no-optional-locks` hard-fails. `git diff --cached` and `git ls-files -m` don't need the flag. This flag belongs on a genuine recovery/forensic read like this one — a step that only fires once you're already isolating a specific stash. A routine "before every commit" git-read mandate doesn't earn the flag; it gets cut outright, because a diligent EM reads the tree without being told to.)
- **NEVER `git stash pop` without `git stash list` confirming `stash@{0}` is yours** (branch + subject match). Always stash with a message: `git stash push -u -m "<subject>"`.
- For "does my additive change cause failure X?" — reason it out. A purely-additive change (new module + one registration) cannot affect unrelated tests; don't stash-dance on a shared tree to find out.
- Recovery if you popped a sibling's stash: `git stash show --name-status stash@{0}` to scope, restore only those paths (`git rm --cached` for not-in-HEAD workspace artifacts, `git checkout HEAD -- <f>` for tracked), leave the stash for its owner.

**If a whole-tree stash happens anyway, snapshot before any pop attempt.** The safer default is never to reach for a stash at all — the question a stash is usually reached for ("is this failure pre-existing, or did my change cause it?") is often answerable by reading which files the failing check actually opens, not by mutating the shared tree; ask "can I answer this without touching the tree?" first. But if a whole-tree stash has already landed (yours or a sibling's), immediately snapshot `git stash show -p` to scratchpad before any pop attempt — that snapshot is the only lossless recovery path if the pop then collides with a sibling's re-applied work.

**`git stash push -- <own paths>` is not automatically the safe scoped alternative it looks like.** A scoped push dies entirely — creating no stash at all — if any named pathspec is untracked (`error: pathspec '…' did not match any file(s) known to git` — needs `-u`), and the output reads like a partial success while the tracked paths you did name are left untouched. The reflexive `git stash pop` that follows then pops `stash@{0}` — which under that failure mode is a PEER's stash, not an empty one. Before any pop, check the top entry's base commit in `git stash list` (`WIP on <branch>: <sha> <subject>`); if that sha is not your current HEAD, the stash is not yours.

**GitHub Desktop stashes the whole tree by itself, no agent involved**, sweeping every session's uncommitted work at once. The harness surfaces the resulting missing files as an innocuous "file was modified, either by the user or by a linter" note rather than naming a stash — do not trust that note; check disk. The tell is a `!!GitHub_Desktop<<branch>>` entry in `git stash list`. Recover with `git checkout stash@{0} -- <only your paths>`, never `pop` — a GitHub Desktop stash holds several sessions' work at once, and popping it dumps all of it into your tree.

**Subagents reach for `git stash` unprompted, and the EM-lock does not block it.** A dispatched executor can stash mid-sync to get a clean baseline and then die on a quota limit with its work parked in the stash and the on-disk files reverted. Put an explicit "no git stash — the tree is shared with live sessions" line in every executor/integrator dispatch brief, and on any agent death, check `git stash list` for an orphaned entry before assuming the work is simply lost.

### H8 — `--amend` / `rebase` / `checkout --detach` collide with concurrent work

**Symptom.** A history-rewriting op on a shared dirty-tree branch aborts (dirty tree), reverts a sibling's tracked files, or collides with a concurrent amend.

**Trap.** `git rebase` aborts on a dirty tree; `checkout --detach` reverts tracked files; `--amend` races a sibling amend. All three touch the working tree or index a sibling is using.

**An armed auto-push hook is a fourth, independent way `--amend` collides, and it fires even with no sibling in sight.** A pre-amend check that feels sufficient — "is HEAD still the commit I just made?" — only rules out a *peer* having committed on top; it says nothing about whether the commit has already been *published*, and on a branch with an auto-push post-commit hook it usually has, within seconds. Amending a published commit makes local history diverge from the remote (non-fast-forward), and every subsequent auto-push then fails silently into `.git/push-failures.log`, with crash-insurance off until someone notices. Before amending, check `git rev-list origin/<branch>..HEAD` (or `git fetch && git --no-optional-locks status`) to confirm the commit is unpushed — local HEAD alone does not answer this. If it is already on the remote, do not amend and do not force-push (a peer may hold it); land a follow-up commit instead, or if the amend already happened, `git merge origin/<branch>` to reconcile — content-free and safe when the amend only changed the commit message. Better still, get the commit subject right the first time: a frontmatter-mutation guard that fires *after* the commit is often what prompts the amend in the first place, and satisfying it pre-emptively avoids the whole trap.

**Rule.**
- **Prefer new commits over `--amend` on a shared bus.** Quick-saves are cheap; rewriting shared history is not.
- To **reword a commit buried under concurrent commits** on a shared dirty-tree branch, use pure plumbing — never `rebase`/`checkout`:
  1. Rebuild the target: `git commit-tree <tree> -p <parent> -F msg` (reuse each child's exact `^{tree}`, rewritten parents, preserved author/committer ident+date).
  2. Replay children reusing their trees.
  3. **GATE on `final^{tree} == old_tip^{tree}`** before swinging the ref.
  4. `git push --force-with-lease=<branch>:<old-origin-sha>` so a racing push aborts safely.
  5. Abort if any commit in range is a merge (single-parent reuse is unsafe).

  Plumbing never touches the working tree or index, so the sibling's WIP is safe. → also in [`daily-branch-discipline.md`](./daily-branch-discipline.md).

### H9 — `git mv` / rename hazards on a shared branch

**Symptom.** A staged forward-rename survives a worktree-looks-correct revert; or a rename commit lands without its content edit; or a rename leaves an orphaned staged deletion.

**Trap.** Three distinct rename traps:
- A `git mv` revert does NOT undo a staged forward-rename — `find`/worktree appearing correct ≠ index clean. `git ls-tree HEAD` is authoritative.
- `git mv src dst` then `Edit dst` then `git commit -- dst` lands the rename without the content change (the staged rename is content-identical to src). Correct order: `git mv` → `Edit dst` → `git add -- dst` → `git commit -- dst`.
- `git mv A B && git commit -- B` leaves A's staged deletion orphaned. Pathspec must enumerate both sides: `git commit -- A B`.

**Rule.** On a shared branch, fuse a directory-rehome (`git mv` + edits + `git add` + `git commit`) into **one Bash call** — separate-call windows let a concurrent session revert between steps. Enumerate both rename sides in the commit pathspec. Detailed treatment in [`scoped-safety-commits.md`](./scoped-safety-commits.md) §§ "`git mv` + Edit ordering" and "Rename pathspec must include both sides".

### H10 — Path-filtered `git status` lies; verify what actually landed

**Symptom.** `git status -- <your-paths>` shows a clean expected scope, but the commit carried foreign files.

**Trap.** A path filter hides exactly the foreign files the index actually carries. Under concurrency the filter is a blindfold.

**Rule.** Bracket every commit on a shared branch with unfiltered audits:
- **Before:** `git diff --cached --name-only` (full staged set).
- **After:** `git show --stat HEAD` (confirm the file list matches intent).
- **After high-concurrency fan-out (N>5):** `git log -p --since="<dispatch-start>"` audit before merge — look for diffs exceeding their subject's scope and ghost commits with no clear attribution.
- **Verify your commit landed with `git log -N | grep <subject>`, never `git log -1`.** On a shared branch, `git log -1` may show a sibling's commit; grep recent log for your own subject line to confirm your commit actually landed.

### H11 — `git checkout --ours` and mtime pitfalls

**Symptom.** Downstream mtime-based pre-flights misfire after a conflict resolution; or conflict markers persist after `--ours`.

**Trap.**
- `git checkout --ours <path>` updates the worktree mtime even when content matches HEAD — mtime-based detectors (the commit-helper's mtime fallback included) then misclassify the file as freshly-edited.
- `git checkout --ours <path>` resolves the `AA` index stage but does NOT refresh the worktree from stage 2 — conflict markers can persist in the file.

**Rule.** After `git checkout --ours <path>`, follow with `git checkout HEAD -- <path>` and **verify the file content** (grep for conflict markers `<<<<<<<`) before staging. Be aware mtime-based scope tooling may misfire on `--ours`-touched files; prefer explicit `git add -- <path>` over mtime fallback in conflict-recovery flows.

### H12 — Sibling-session coordination is via committed memo, never their dirty file

**Symptom.** A fix needs a 2-line change in a file a sibling holds dirty (` M`). Editing it or `git commit -- <file>` sweeps the sibling's uncommitted work (H4). `SendMessage` doesn't reach them.

**Trap.** Touching a sibling's dirty file is the H1/H4 collision either way — a live read confirms existence, not that they'll commit on request.

**Rule.** **Split at the concurrency seam.** Commit the clean part of your fix; write a dated `archive/YYYY-MM-DD-<topic>.md` memo. Also: a `consumed`/`claimed` (formerly `consumed`; DR-084) status or an `in_flight` handoff stamp is a collision signal — grep the shared branch (`consumed_by`/`claimed_by`) before building on a handoff that shows this status. with the exact atomic change + file links; leave their dirty file untouched. The receiving session reads the memo and lands it. Distinct from a cross-repo memo (PM-relay, different repo) and from Agent Teams `SendMessage` (same team context). → [`cross-repo-communication.md`](./cross-repo-communication.md) § same-repo concurrent sessions. If you discover >100 LOC of unstaged changes in a shared file you didn't edit, check the registry first, else treat it as activity — edit unrelated files only, resume after they commit ([`scoped-safety-commits.md`](./scoped-safety-commits.md) § "Large unstaged diff in shared files").

### H13 — Scope process-kills to your own invocation, not the runtime class

**Symptom.** Killing "all pytest processes" (or any runtime-class kill) catches a concurrent EM's unrelated run, the embed sidecar, or the MCP daemon.

**Trap.** The Python/pytest/node runtime is shared across concurrent sessions and long-lived services. A class-level `Stop-Process -Name python` / `pkill -f pytest` is indiscriminate.

**Rule.** Match on the specific command line (your test paths/flags) before killing — `Win32_Process.CommandLine` filtering on Windows, `pgrep -f "<your-exact-args>"` on POSIX. Never blanket-kill a runtime shared with concurrent sessions or daemons.

### H14 — Concurrent `/workweek-complete` or `filter-repo` flips/resets your tree

**Symptom.** A concurrent `/workweek-complete` flips the working tree to `main` mid-session, landing your commits on `main`. A concurrent `git filter-repo` resets working-tree state across all sibling sessions.

**Trap.** These are tree-global operations a sibling can run while you're mid-flight; they're not scoped to one session.

**Rule.** **Commit narrative drafts and WIP BEFORE any review/merge/history-rewrite ceremony you know a sibling might run.** After such a ceremony, verify your branch is still your branch (`git branch --show-current`) and your commits didn't land on `main` (`check-shipped-on-main.py` / `git log main`). If your commits landed on `main` via a sibling's flip, surface to PM — do not improvise a fix on `main` (read-only-main doctrine).

---

## Recovery Procedures

When a hazard already fired. **Disk and reflog are authoritative; chat and your memory of what you staged are not.**

### R1 — Abandoned `git stash pop` (UU/DU/UD stages, no MERGE_HEAD)

Diagnosis: index shows `UU`/`DU`/`UD` stages but there is no `MERGE_HEAD` → an abandoned `git stash pop`, not a merge. Recovery requires **stage-by-stage decisions, not auto-commit**:
- `git stash show --name-status stash@{0}` to scope what the pop tried to apply.
- Per path: `git checkout HEAD -- <tracked>` to discard the stash's version, or `git rm --cached <not-in-HEAD-artifact>` for workspace junk.
- Verify no conflict markers remain before staging anything.
- Do NOT `git commit` your way out — you'll bake the half-applied stash into history.

### R2 — Staging one hunk from a concurrent-EM-entangled file

Content-verify the extracted patch before committing: grep for your own marker AND assert the peer's content is absent. Then a broad bleed-grep across the staged set before commit. `git add -p -- <file>` is the staging primitive (H1).

### R3 — Phantom test failures from a sibling's uncommitted working-tree diffs

Before classifying a failure's scope, a 30-second verification: `git stash push -u -m "phantom-check"` your local changes, re-run, `git stash pop`. If the failure vanishes with your changes stashed, it's a sibling's dirty-tree artifact, not your regression. (Confirm `stash@{0}` is yours per H7.)

### R4 — "no changes added to commit" / swept index — reflog probe

```bash
git reflog --date=iso | head -20    # find the foreign commit's parent
git stash list                      # check for auto-stashed state
git fsck --lost-found               # last-resort dangling-blob recovery
git show --stat <foreign-sha>       # did a sibling commit absorb your files?
```

Identify the sibling commit; if it absorbed your files they're now in HEAD under the wrong subject — resolution (cherry-pick / reword via H8 plumbing / revert+redo) is a PM call. Do NOT blindly retry `add && commit` — that repeats the race. Full sequence in [`scoped-safety-commits.md`](./scoped-safety-commits.md) § "no changes added to commit".

---

## Detecting Concurrent Work at Pickup / Plan-Time

A peer session co-driving your workstream is invisible until you look. Two read-side checks before treating branch state as yours:

- **At pickup.** If the workstream branch shows commits since your orientation point you didn't author, suspect a parallel EM session. Run `git log --since=<handoff-date> --oneline` and `ls archive/ cross-repo/` to surface sibling commits and dropped memos. (Folds into `/pickup` concurrent-EM detection.)
- **Before launching a plan pipeline.** Survey `git log --oneline` on the workstream for concurrent work — a peer may be co-driving the same plan. Grep for sibling plans before reverting "out-of-scope drift" as contamination (it may be a sibling's legitimate in-flight work). (Folds into `/workstream-start` / `/workday-start` concurrent-workstream surfacing.)
- **Peer detection via remotes covers OTHER machines only.** `git branch --branches` is structurally wrong for detecting concurrent EMs; off-machine, `origin/work/{peer}/*` remains the only visibility — `git for-each-ref refs/remotes/origin/work/`. Same-machine: see fact #3 above.
- **Before authoring overlapping code fixes**, a concurrent-EM peer `git log` check on the target paths — a sibling may have already fixed it — **and verify the peer's landed change is *correct*, not merely present.** A shared-branch commit can be a landed *half*-fix (e.g. one that arg-wired an invocation but kept a buggy `grep|sed` extraction); bare commit-existence is not proof of correctness — read the peer's actual diff before building on the same seam. → [`daily-branch-discipline.md`](./daily-branch-discipline.md).
- **Recent peer commits on your exact plan surface = the peer may be running their OWN review pipeline — stand down before launching a parallel one.** When reconcile shows another session committed to the exact plan surface within the last ~15-30 min, treat it as a positive-liveness signal that the peer may be mid review+integrate. Do NOT launch a parallel code-review / integrator; grep the peer's `git log` for review/fix commits and check for an in-flight `state/review-trail/` sidecar first, then reconcile against their output and salvage only genuinely-unique findings. `cs_claim_plan` does NOT gate a peer's *inline* (same-session, uncommitted) work — the claim is no protection here (a live read only confirms existence).
- **Uncommitted edits on your plan's cited seams = a peer already executing the same plan.** The pickup collision check (`source_memo` / today-dated-plan) catches a duplicate *plan file*, but not a peer that picked up the same handoff, wrote the same plan, and is mid-execution with **uncommitted** C1/C2 edits in the shared tree. `cs_claim_plan` (gates `execute-plan` Phase 1.5 and `workstream-complete`) fails loud at the claim boundary when a second live session drives the same plan — but uncommitted work on the plan's cited seams is the earlier tell, visible before the full prior-art → reviewer → integrator pipeline burns the run getting to that gate.

---

## Cross-platform / tooling gotchas under concurrency

- **CRLF `autocrlf` silently drops files from commits** despite `git add` succeeding (Windows). Verify staged-count vs committed-count post-commit. → `claude-code-platform-gotchas.md`.
- **Cross-shell line-count comparison is NOT a drift oracle.** `wc -l` (Git-Bash) and `Measure-Object -Line` (PowerShell) disagree on the *same* file because of CRLF and final-newline handling — bash counts `\n` terminators, PowerShell counts lines including a non-terminated last line. A line-count delta between two shells is a measurement artifact, not evidence a sibling edited the file. **Use `git --no-optional-locks status` + `git log -- <file>` as the only drift oracle, and stay in ONE shell for any given measurement.** → composes with H10 (path-filtered `git status` lies) — both are "the measurement you reached for is lying about concurrent state."
- **Multi-line commit messages via the Bash tool** must use a heredoc or `git commit -F <file>`, not PowerShell `@'…'@` here-string syntax — the here-string leaks a stray `@` into the subject. → `claude-code-platform-gotchas.md`.
- **Pre-commit hooks must stream large staged diffs** (`mktemp` + `grep`), not capture `git diff --cached` into a bash variable — multi-hundred-MB staged-deletion diffs OOM the shell. → `coordinator/docs/wiki/coordinator-tripwires/` hook-authoring.
- **GitHub force-merge requires bypassing BOTH rulesets AND classic branch protection** — they are independent gates.

---

### H15 — Concurrent `/update-docs` silently pre-populates archive and orientation entries

**Symptom.** You reach `/workstream-complete` to write an archive entry or update the orientation cache, only to find the entries are already there — or worse, you write a duplicate.

**Trap.** A sibling session running `/update-docs` while you were working may have swept your commit hashes into `archive/completed/`, the orientation cache, and the project tracker. Nothing prompts them to tell you; the surfaces look clean until you diff.

**Rule.** Before adding any archive/orientation entry at workstream-complete, grep `archive/completed/` for your commit hashes and check the orientation cache's `git_head_at_generation` field. If your work is already indexed, skip the entry — do not add a duplicate. Duplicates cause merge friction and wasted edits on shared branches.


### H16 — Shared-file edits under concurrent EMs get clobbered at workstream-complete

**Symptom.** Edits to `state/lessons/` or `state/improvement-queue/` accumulated during a session vanish when a concurrent session commits its own version before your workstream-complete commit.

**Trap.** `state/lessons/` and similar shared buses are last-writer-wins on the working tree. A staged `git mv` or pending edit held for the batched workstream-complete commit is overwritten the moment a sibling's commit/checkout touches the same path (H4). Two lessons appended mid-session can be silently lost.

**Rule.** When editing a known shared file during a multi-session window, commit it at the next coherent boundary — `git add -- <file> && git commit -m "..." -- <file>` (agree-case form — see H3's disagree-case caveat if you staged a partial hunk) — rather than holding it for the batched workstream-complete commit. Regular, unasked, narrow commits; the unit is a discrete revertible chunk, not an edit (H4 § "A commit is a savepoint").

### H17 — Line-number-keyed allow-lists drift silently under concurrent editing

**Symptom.** A `file:line`-keyed exemption registry (e.g., a spawn-audit allow-list) suddenly shows false violations after a session's edits shift line numbers.

**Trap.** Any registry keyed by line number is O(edits) fragile and breakage is invisible until the gate runs. On a shared concurrent-EM branch, multiple sessions' edits compound the drift across sessions. Prior "Line drifted" triage comments in such files are evidence of this failure pattern repeating.

**Rule.** Reconcile via the test's own collectors (e.g., `_collect_hits` + stale-key diff), not truncated pytest output. Longer-term, such registries should key on a stable marker (function signature, symbol name), not line number. When taking over a `file:line`-keyed registry, treat any pre-existing drift comments as a structural warning — the registry design will fail again.

### H18 — Workstream-complete housekeeping artifacts are exposed to concurrent tree resets

**Symptom.** Mid-`/workstream-complete`, a concurrent crash-recovery session runs a working-tree reset that wipes this session's uncommitted lessons, plan edits, orientation updates, and untracked completion-log entries.

**Trap.** The branch is a shared bus; other sessions run destructive git ops (checkout, clean) without coordination. Committed work survives; uncommitted working-tree state has no protection.

**Rule.** During `/workstream-complete`, commit housekeeping artifacts as they become coherent rather than batching all edits then committing once at the end. Untracked deliverables (completion entries, review trail JSON) are especially exposed to `git clean` by a sibling's crash recovery. Workstream-complete is not the moment to accumulate — it is the moment to commit narrow and unasked. Group the artifacts that belong together into one commit; a commit per file here buys nothing and costs lock cycles (H4 § "A commit is a savepoint"). **Structural enforcement:** the commit-narrow-and-unasked rule is backed by claude-klabauter `coordinator_core.bash_guards.dispatch_checks.check_destructive_git_clean` (BLOCK-DESTRUCTIVE-GIT-CLEAN), a PreToolUse guard that DENIES a `git clean` which would remove untracked load-bearing deliverables — see `coordinator/docs/wiki/coordinator-tripwires/`.

### H19 — A just-authored plan's cited seam can drift mid-execution when a concurrent session refactors shared infra

**Symptom.** An executor finds the function, file, or call-site it was directed to modify has moved — extracted into a shared lib or renamed — between plan-write and execution.

**Trap.** The plan-substrate-staleness rule ("survey before dispatching") has a concurrent-session corollary: even same-session-authored plans can drift when a sibling EM refactors shared infra in parallel. The plan's seam was accurate at write time; the disk is different at execution time.

**Rule.** When an executor finds its cited seam has moved into shared/out-of-scope territory, the correct response is an in-scope adaptation that preserves behaviour — NOT silently widening scope to absorb the drift (Branch D violation). Flag the deviation in the return so the EM records it. If the seam moved into a shared library that is genuinely out-of-scope, compute the new field or behaviour via an inline alternative, deliver identical observable behaviour, and report the deviation explicitly.


### H20 — Editing Build-Input Source During an In-Flight Long-Running Build

**Symptom.** A source file edit lands mid-build; the build picks up partial state (some translation units see the new code, some see the old), producing a build artifact that is neither the pre-edit nor the post-edit executable — silent correctness corruption that passes compilation.

**Trap.** On a shared concurrent-EM tree, a long-running build (UBT, Cmake, tsc `--watch`, gradle) reads source files incrementally. An edit to a header or a widely-included module that lands mid-build is incorporated into only the translation units compiled after the edit — the earlier units already compiled against the old version. The resulting artifact is a chimera.

**Rule.** Before editing a file that is a build input on a shared tree — especially widely-included headers, generated files, or source files in an active hot-loop — check for an in-flight long-running build: `ps aux | grep -E "(UBT|cmake|tsc|gradle)"` (or equivalent). If one is running, either wait for it to finish and re-trigger, or make the edit and force a full rebuild. A partial-input build is worse than a clean rebuild: it produces an artifact that looks healthy but is not.

### H21 — Orphaned `.git/index.lock` survives commits under concurrent-EM (Git-for-Windows)

**Symptom.** A `.git/index.lock` file (~the size of a full index copy) outlives the `git` process that created it; subsequent commits from *other* processes succeed via fresh lock cycles, but a later commit in the *same* worktree fails with `fatal: Unable to create '.../.git/index.lock': File exists.` A `.git/objects/maintenance.lock` is often co-present.

**Trap — this is NOT coordinator code.** `coordinator-auto-push` only runs `git push` (never touches the index); `coordinator-safe-commit`'s session lock is `.overlap-gate.lock` (PID-stamped, self-reaping), never `index.lock`, and it commits via plain foreground git. The real mechanism is a Windows file-sharing artifact: a foreground `git add`/`git commit` writes a full index copy to `index.lock`, then the final `rename(index.lock → index)`/unlink fails with a sharing violation because another process holds a handle on `index` — a concurrent session's `git`, antivirus/Defender, the search indexer, or **git's own *detached* auto-maintenance child** (`gc.autoDetach` defaults true; the co-present `maintenance.lock` is its fingerprint). The commit's objects+ref are already durable, so the commit "succeeds" while the orphan lock survives. `index.lock` carries no holder PID, so liveness cannot be read from the lock itself.

**Rule — three-leg fix, all shipping to every coordinator install:**
1. **Production-elimination:** `gc.auto 0` (set by `coordinator-configure-git`, asserted per-repo at `/repo-setup` § 3f.5 and `coordinator/commands/install.md` — per-repo by design per the per-key scope ruling recorded below, not globalized). No auto-gc at all — neither a detached child to orphan the lock nor a foreground repack a killed session can abandon half-written. `coordinator-configure-git` is a Python trampoline onto `coordinator_core.ops` in claude-klabauter.

   Ending auto-gc ends automatic repacking too, so two legs replace it:
   - **Repacking:** a ceremony-triggered `git maintenance run --task=<...>` call (`maintenance.strategy=incremental`, `maintenance.auto=false`, `maintenance.prefetch.enabled=false` — set directly, never via `git maintenance register`/`start`; the prefetch key matters because a schedule cascades across every tier, so no tier choice escapes a network-fetching prefetch task once one runs — see `coordinator/docs/wiki/coordinator-tripwires/git-maintenance-runs-at-ceremonies-never-on-a-scheduler.md`) at six DoE-owned ceremony commands: hourly-shaped `commit-graph` at `update-docs`/`distill`, daily `incremental-repack` at `workday-start`/`workday-complete`, weekly (superset, also runs daily+hourly) at `workweek-start`/`workweek-complete`. Advisory — a non-zero exit is reported and the ceremony continues. `incremental-repack` at a ceremony is still a foreground child of a killable session and can still leave a `.tmp` body — the class is bounded by the pack reaper below, not ended by this config.
   - **Weekly prune, and it runs FIRST:** the weekly-tier call also runs `git prune --expire=<age>` (never `git gc --prune=<age>` — that form is a 10,068 ms / 9-proc call, and reads as the obvious choice but is the wrong one) to drop unreachable objects, which `gc.auto 0` would otherwise let accumulate forever under the incremental strategy. **Sequence the prune BEFORE the `--schedule=weekly` call, never after.** Weekly runs `loose-objects`, which packs loose objects without regard to reachability, and `git prune` only ever removes *loose* ones — so a prune sequenced after the packer finds nothing left to remove and the garbage is now permanent. Measured on git 2.55.0.windows.5: an unreachable blob written with `hash-object -w` survives `git prune --expire=now` after a weekly run (it has been moved into `objects/pack/loose-<sha>.pack`, where `git cat-file -e` still finds it); with the prune sequenced first, the same blob is gone and the weekly run has nothing to pack. Prune-after-weekly is not a slower cleanup, it is no cleanup. This prune leg is bound by the same defer-on-index-lock predicate as the reapers below — under a held index, both `git prune` and `git gc --prune=now` return rc=128, so a supervised run must not assume a free index.

2. **Self-heal — `coordinator-reap-stale-locks`, in claude-klabauter's tree** (`coordinator/bin/coordinator-reap-stale-locks.{py,cmd,ps1}`, not local to DoE-claude). Removes an orphaned `index.lock`/`next-index-*.lock`/`maintenance.lock` ONLY when both aged (≥120s; maintenance ≥600s) AND stable across a re-sample (no active writer), as a pre-op self-heal inside `coordinator-safe-commit` (fail-open). **Locks only — it never reaps pack bodies.** It is the commit pre-flight, called in-process by `coordinator_core/lock_preflight.py`, and its stability gate is a serial `time.sleep` per candidate; a glob over `objects/pack` there would pay one 2s window per orphan (~10s for five) on the hottest path in the repo, and would falsify the module's own Purpose/closed-lock-set/bash-parity/`GENERATES = []` contracts and its rc-2 "a live commit may be in progress" signal.

   Manual recovery: `tasklist`/`pgrep` to confirm no live git, then `rm -f .git/index.lock .git/next-index-*.lock .git/objects/maintenance.lock`.

3. **Pack reaping — `sweep_orphan_packs()` in claude-klabauter's `coordinator_core/ops/git_maintenance.py`**, beside the maintenance door that is its only caller (an earlier draft put it in a sibling `reap_orphan_packs.py`; a review removed the third module, since the argument against extending `reap_stale_locks` was never an argument for a new file). It reuses the age-and-stability gate's *semantics* by importing that module's sampling primitives and env-knob readers, and deliberately does NOT call `stale_and_stable` itself: that function's sample/wait/re-sample cycle is per-call and therefore per-file, so N orphans would cost N windows — the exact cost the batching exists to avoid. `reap_stale_locks.py` is untouched, contract and all. Reaps orphaned `.tmp-<pid>-pack-*.pack` bodies left by a killed foreground repack, a class `git gc` never reaps (a planted 30-day-old `.tmp-99999-pack-deadbeef.pack` survives `git gc --prune=now` unchanged on git 2.55.0.windows.5) — a net-new cleanup, not a replacement for one `gc.auto 0` removed. It runs on the **weekly tier of the `git.maintenance` op**, beside the `git prune`, so both garbage classes sit behind one ceremony entrypoint; with `gc.auto 0` the producer of orphan packs is gone, so weekly is amply timely. It samples the whole candidate set once, waits ONE stability window, re-samples, unlinks — never a window per file.


### H22 — Phantom-dirty index under concurrent-EM (Git-for-Windows + NTFS)

**Symptom.** `git status` reports a large set of tracked files as modified that have no real content change; `git update-index --refresh` (even `--really-refresh`) does not clear them, and the racy-entry count can *grow* mid-refresh (e.g. 3181→3183) as other sessions touch the index.

**Trap.** Git-for-Windows writes nanosecond mtimes into `.git/index`, but NTFS reports them back at coarser precision, so on every stat the recorded and observed mtimes differ and the entry is flagged "racy." The default `core.checkStat` also compares `ctime/ino/dev`, which are likewise unstable across the NTFS round-trip. Concurrent EM sessions continuously rewriting the shared `.git/index` re-arm the racy flag faster than any single refresh can clear it — a refresh-clobber loop that no amount of `--refresh` escapes.

**Rule.** `core.checkStat minimal` — compares only `mtime+size` (both stable across the NTFS round-trip), dropping the unstable fields. Set by `coordinator-configure-git` alongside the H21 keys, so it self-heals per-repo via `/repo-setup` § 3f.5 and `coordinator/commands/install.md`. Unlike `gc.auto 0` (which we keep per-repo), `core.checkStat minimal` is benign and content-neutral on every platform and the phantom-dirty pattern affects *any* repo on Git-for-Windows + NTFS, so `/setup` **also** sets it as the machine-wide default (`git config --global core.checkStat minimal`) — covering every current and future repo, coordinator-managed or not. Manual one-off: `git config --global core.checkStat minimal`. **Does not cure H23** — that phantom is a *size* mismatch, which even `minimal` compares.

### H23 — EOL phantom-dirty index: stale line-ending blob size flags content-equal files (Git-for-Windows)

**Symptom.** `git status` perpetually flags files as ` M` that `git diff` and `git diff --cached` both report as having nothing to commit. Forensics on one file: HEAD blob and index blob are byte-identical (e.g. both 41313 B, LF), but the recorded stat size differs from the worktree (e.g. worktree 42218 B, CRLF) — or the mirror image (worktree LF 5115 B, index CRLF 5218 B, HEAD LF). The count can run into the thousands and grow as siblings commit. `core.checkStat minimal` does **not** fix it (size is compared even by `minimal`); `git update-index --refresh` does **not** fix it (the size genuinely differs).

**Trap.** This is a *pending line-ending renormalization that lives only in the index*. `git diff`/`git diff --cached` renormalize-then-hash, so they correctly see the content as equal and report empty. But `git status` uses the recorded blob *size* as a stat shortcut, and the EOL round-trip changes the size — so the file is flagged forever. The naïve fix `git add --renormalize .` is **forbidden under concurrent-EM**: it re-stages every modified file's *current* worktree content, absorbing siblings' live uncommitted edits into the next commit and clobbering a sibling's mid-commit staged blob (the exact absorption hazard the doctrine bans).

**Rule — `coordinator-renormalize-index`.** Because each phantom's content already renormalizes-equal to the index/HEAD, a plain `git add <path>` refreshes only the stat-cache and stages **nothing committable** — no commit needed. The tool refreshes ONLY the phantom set, computed as `(git ls-files -m) MINUS (git diff --name-only) MINUS deleted-in-worktree` = stat-modified minus real worktree-vs-index content diffs minus deletions. This excludes every genuine worktree edit AND any path a sibling has staged (index≠HEAD with a differing worktree). **Residual race (honest scope, not "by construction impossible"):** the set is a snapshot and the `git add` fires later, so a sibling overwriting a phantom path in that window could be staged; we shrink the window to near-zero by re-confirming against a fresh `git diff` immediately before staging, and the worst case is bounded — the sweep only ever `git add`s, never commits, so an absorbed edit sits merely *staged* (visible, recoverable) and is caught downstream by `coordinator-safe-commit`'s touched-files filter before it can enter a commit. **Safe on a live shared tree at any time.** Hardening: a real `git diff` *failure* (not empty) aborts loudly rather than treating all paths as phantoms; deleted-in-worktree paths are excluded (a `git add` there would stage a deletion); `--ignore-errors` keeps one poison path from sinking the batch; and the write is deferred if a live `index.lock` is present (no added contention vs § H21). Requires bash 4+ (associative arrays) — `#!/usr/bin/env bash` prefers a modern bash, and it no-ops cleanly on older shells (e.g. macOS stock /bin/bash 3.2), where the NTFS phantom does not arise anyway. It is invokable on demand and used in test coverage; the former SessionStart-hook caller (`session-init.sh`) is gone as part of the hook full-kill (see `coordinator/hooks/hooks.json` and `coordinator/hooks/scripts/project-orientation.py:9-16`), so `coordinator-renormalize-index` currently has no automatic per-session caller — it is manual/test-only. The session terminators' (`/workstream-complete`, `/handoff`, `/workday-complete`, and `quick-wrap` — see `ceremony-calibration.md` § Session terminators) dirty-tree gates only carry a one-line *recognition* clause treating a content-equal ` M` file as benign (never a case-(c) orphan) as a backstop for phantoms that appear mid-session. `--check` reports the phantom count without writing the index. `coordinator-renormalize-index` is now a Python trampoline onto `coordinator_core.ops` in claude-klabauter. The heavier repo-wide cure — `git add --renormalize . && commit` — fixes it for *all* clones at once but must run on a quiet tree (no live sibling edits); prevention is a consistent `.gitattributes` (`* text=auto`) so the index never re-acquires an EOL-stale blob.

### H24 — Concurrent sweep deletes uncommitted executor output between DONE and EM-commit

**Symptom.** An executor replies `DONE` citing files it wrote and tested (`.pyc` cached in `__pycache__/`), but when the EM runs `git status` to commit, the source files are missing from disk — and `git log --all --diff-filter=D -- <path>` returns nothing (they never entered git).

**Trap.** The EM-serial-commit-after-wave doctrine has a vulnerable window between executor `DONE` and EM commit. New uncommitted files are dirty-tree state with no git protection; a concurrent EM running a registry/age-driven sweep (claude-klabauter `coordinator/bin/cruft-sweep`, test-tree cleanup, `/distill`) can classify them as old scratch and delete them. Disk-write + local test-pass + `DONE` is not durability — the bytes can vanish before they're committed.

**Rule.** Two-leg fix. **Recovery shape:** when an executor's `DONE` cites a file the EM can't find on disk, issue a *recovery dispatch with a commit-on-write override* — the brief explicitly lifts the no-commit rule for this single chunk and instructs the executor to `git add -- <path> && git commit -m "..." -- <path>` immediately after Write+verify (agree-case form; see H3's disagree-case caveat). Note "files swept" in the prompt so the executor doesn't try to recover from a phantom prior state. Do NOT re-dispatch the original brief blind. **Long-fix:** shorten the EM-side commit cadence on heavily-concurrent days — commit executor output as `DONE`s arrive, not after the whole wave. An executor's returned file set is the natural unit: one commit per `DONE`, not one per file it touched, and not one for the wave.

### H25 — Concurrent sibling `git stash push -u` absorbs in-flight executor edits across the fan-out

**Symptom.** Mid-fan-out (N parallel write-capable executors), a sibling session runs `git stash push -u` to clear their tree for a probe. The working tree empties atomically; executors that continued writing after the stash see disjointed state. Executors that completed after the stash report `DONE` truthfully against the live tree at edit time but their pre-stash edits are gone. Post-stash audit shows ~70% file-landing rate against the report.

**Trap.** `git stash push -u` is destructive to the working tree, not coordinative — there is no per-session affinity, all dirty files leave the tree in one atomic op. Concurrent sessions sharing a branch share a single stash-collision surface; sibling executor edits are absorbed into the stashing session's `stash@{0}` and silently dropped on the next `git stash drop`. Compounds with H7 (wrong-owner stash) and with Sonnet TEXT-ONLY hallucination at fan-out scale >5 (the reports trust the moment-of-edit return, not the post-stash disk state).

**Rule.** Three legs. **(1) Prevent:** on a shared branch with active executors, NEVER bare `git stash push -u` — scope to your own workstream with `git stash push -u -- <explicit-paths>`. **(2) Verify:** after ANY parallel fan-out of write-capable executors, EM verifies actual on-disk state via `grep -lr <expected-token> <scope>/ | wc -l` against reported counts BEFORE accepting `DONE`. Disk is the only signal that counts. **Recovery shape:** on suspicious count-vs-claim mismatch, `git fsck --unreachable --no-reflogs` surfaces the dropped stash commit (still in the object DB after `git stash drop`); recover via `git diff <stash>^1 <stash> -- <file-list> | git apply --reject`. Prefer plain `git apply --reject` over `git apply --3way` — the 3way variant reports "Applied cleanly" but may silently no-op against certain index states. Companion guardrail: hard-cap parallel write-capable fan-out at 5 (Sonnet TEXT-ONLY rate spikes above that scale).

**Enumerating stash shapes — `save` is `push` under a deprecated name.** Any rule, guard, or review checklist that enumerates which `git stash` subcommands sweep the working tree must count `save` as a sweeper. It is the pre-2.16 spelling of `push` with an identical sweep; being deprecated changes nothing about what it does. The plausible-and-wrong grouping is `save` alongside `create`/`store` — those two genuinely do not touch the tree, and `save` reads like it belongs with them. Anyone writing the next such enumeration will reach for the same grouping, so state the sweep set positively — `push`, `save`, and bare `git stash` — rather than by exclusion.

### H26 — Auto-push post-commit hook missing locally + GitHub email-privacy reject (silent crash-insurance failure)

**Symptom.** A full work-day of commits on `work/{machine}/{date}` lives only on disk — `git log origin/work/{machine}/{date}` is empty or many commits behind local HEAD. On manual `git push`, GitHub may also refuse with `remote rejected … push declined due to email privacy restrictions`. Discovered at `/workstream-complete` → Verify Remote step, after the crash-insurance window has already closed.

**Trap — two independent failures on the same crash-insurance promise.**

1. **Layer A — installer drift.** The coordinator auto-push doctrine is *"every commit on `work/*` and `feature/*` branches pushes via a `.git/hooks/post-commit` hook."* That hook is a per-repo file written by the install/setup chain — not by `git config`, not tracked in the repo. A new repo, a freshly-cloned working copy, a `rm -rf .git/hooks/` recovery, or a `/repo-setup` run that skipped or silently failed the hook-install step all leave the repo with NO post-commit hook. Commits accumulate locally, the EM sees `git status` clean and `git log --oneline` healthy, and assumes pushed — there is no per-commit signal that auto-push didn't run. This is a per-repo, per-clone failure: machine-a can be hook-clean while example-game-repo on the same machine is hookless.

2. **Layer B — email-privacy reject.** Even with the hook installed and firing, `git push` rejects with `push declined due to email privacy restrictions` when the repo's `user.email` is the operator's public address but the GitHub account has "Keep my email address private" enabled. The hook's exit code is non-zero but the *commit* succeeded — local HEAD advances, the push silently fails, the EM sees no warning until the workstream-complete verify step.

Both layers fail silently along the same surface (no per-commit failure signal, no SessionStart probe before this audit shipped). One workday on Machine-a accumulated ~15 commits before the gap surfaced.

**Rule — two-layer fix; both ship on every coordinator install.**

- **Layer A — installer idempotency.** `/setup` and `/repo-setup` § 3f install `.git/hooks/post-commit` from `coordinator-auto-push` (per-repo, since `.git/hooks/` is per-clone). The installer is idempotent (re-running overwrites the file with current content; checksum/version sentinel decides whether to re-install). The former per-session re-assertion via `session-init.sh` is gone as part of the hook full-kill (`coordinator/hooks/hooks.json` has no `session-init` entry; see `coordinator/hooks/scripts/project-orientation.py:9-16`) — same fate as the `session-init.sh`-driven assertion of `coordinator-configure-git` / `coordinator-reap-stale-locks` (H21) / `coordinator-renormalize-index` (H23) above. Current callers: `coordinator-configure-git` from `coordinator/commands/install.md` and `coordinator/skills/repo-setup/SKILL.md`; `coordinator-reap-stale-locks` from `coordinator-safe-commit`'s pre-op self-heal (fail-open); `coordinator-renormalize-index` manual/test-only. A clobbered or cloned-without repo now self-heals only at `/repo-setup`/`/setup` re-run or `/workstream-complete`, not at every session start.
- **Layer B — email format that bypasses email-privacy.** Set `user.email` to the GitHub no-reply format (`<id>+<username>@users.noreply.github.com`) or document the alternative (turn off email-privacy in GitHub settings). The no-reply form is preferred because it composes with PMs who want the privacy default. `coordinator-configure-git` (per-repo) and `/setup` (global) assert this — surfaced to the operator at `/setup` with the remediation inline, not buried in `Verify Remote`.

**Why this is a concurrent-EM hazard, not just an install hazard.** Each concurrent EM session running on a shared workstream branch *individually* depends on the post-commit hook for crash-insurance. A hook gap on one machine while peers push normally produces a *partial* `origin/work/...` history — sibling commits land remotely, your local commits do not — and the asymmetry is invisible until a `/pickup` from another machine fetches the partial branch and proceeds against missing context. Composes with H14 (a concurrent `/workweek-complete` flips your tree mid-session): if Layer A is broken and your commits never reached origin, the workweek-complete sibling has no way to absorb them. The crash-insurance promise is per-session, per-repo, per-clone — assert it as such.


### H31 — Fan-out executors running git-stash/tsc/pop round-trips contend for `.git/index.lock` on a shared tree

**Symptom.** During a high-fan-out wave (N ≥ ~10 parallel write-capable executors), intermittent `failed to write commit object` / `fatal: Unable to create '.git/index.lock': File exists` errors appear on EM commits. Executors report clean tsc output, but the EM's per-file commits fail transiently.

**Trap.** When each executor runs a `git stash push` / `tsc --noEmit` / `git stash pop` round-trip to isolate pre-existing errors, all stash operations write `.git/index.lock` — one per executor, potentially concurrent with EM commits. At fan-out ~27, the lock acquisition from every executor's stash overlaps the EM's commit lock windows, producing intermittent collision.

**Rule.** Do NOT brief fan-out executors to use `git stash` / `pop` as a pre-existing-error isolation technique on a shared tree. Instead:

- Compute the pre-existing-error baseline WITHOUT stash: capture a committed baseline error count (e.g. `tsc --noEmit 2>&1 | wc -l`) before dispatch, and brief executors to compare against that baseline number — no stash needed.
- If a stash round-trip is unavoidable, brief executors to scope to their own paths only (`git stash push -u -- <explicit-paths>` per H25) and expect transient lock collisions; retry-after-seconds is acceptable for a single executor.
- Under high fan-out, the EM should expect transient `index.lock` failures from executor stash contention; retry the EM commit (the lock clears in seconds). Do NOT treat these as real failures requiring executor redispatch.

*Composes with H21 (orphaned index.lock from gc.autoDetach) and H25 (sibling stash absorbs executor edits). The root cause is distinct: H21 is a Windows gc artifact; H25 is a `push -u` absorbing peer edits; H31 is a fan-out-scale lock-contention surge from stash-round-trip tsc probes.*

---

## Triage discipline under concurrent EMs

### "Out of frame" / "concurrent-session contamination" is not a disposition — diagnose first, then route

The cheap reflex when a fast-suite failure looks unrelated to current work is to dismiss it as "concurrent-session noise / out of scope." This is the failure mode this rule exists to suppress. Read the failure message before classifying: a "concurrent CUDA OOM" may be a sibling workstream's own contract test catching a real VRAM leak in their uncommitted code — a real finding that needs surfacing, not dismissing. An "RSS-bound flake" with a self-documented `@pytest.mark.slow` xdist TODO is a backlog entry, not noise. **Route:** read the failure → name the workstream owner → write a finding (or cross-session memo per H12) for them. Dismissal is the reflex; routing is the discipline. Composes with H10 (path-filtered `git status` lies) and R3 (phantom failures from sibling dirty-tree) — those tell you *whether* the failure is yours; this tells you what to do once you know it isn't.

### Full-suite spins during concurrent EM activity are unstable signal — quiet re-spin before dispatching a fix

The shared work branch is a shared bus by design; xdist + many workers + concurrent EM commits amplifies every transient. Treating any single full-suite spin as authoritative is the failure mode — a 10m26s run with 3 failures can be a mid-update commit caught by a test oracle (concurrent class-name-metadata workstream commit landed mid-spin), an embedder subprocess timeout under GPU contention from a sibling A/B harness, and a sqlite WAL cleanup race under heavy I/O — none of which is a real test bug. **Discipline.** Before treating a full-suite failure as actionable: (a) re-run in isolation to check it's not a real bug; (b) `git log --since=<spin-start>` for concurrent EM commits touching the failing surface; (c) if both are clean, re-spin under quieter conditions before dispatching a fix. **Flake budget.** Under concurrent activity, ~1-2 failures per 4800 tests is the load-noise floor — treat 1-3 unrelated failures as noise unless they reproduce on a quiet re-spin. The structural enabler is a fast quiet re-spin (~1 minute) so re-runs stay cheap. Composes with R3 (single-failure phantom-check) — this is the multi-failure full-suite generalization.

### A picked-up memo that routes to a plan — reply is the task; do not auto-continue into the plan's execution

Actioning an inbound `ask` memo means *replying* to it (status, seam contract, disposition) — NOT sliding into executing the plan it references. When the memo says "please deliver C6-amend 2b," the reply is the deliverable; the memo told you the work exists, not that it's yours to drive. Auto-continuing into the referenced plan's execution risks colliding with a LIVE concurrent session already on it: in the documented case a sibling session had committed the plan amendment minutes after the memo and was reworking a test in the shared tree, and the memo-picker's "just keep going" into C4 + un-gate collided head-on. **Rule.** After replying to a plan-routing memo, run the § Detecting Concurrent Work at Pickup / Plan-Time check before touching that plan's execution.

---

## See also

## verify HEAD before pausing release or spinoff on broken-today claim

Before pausing a release or authoring a spinoff based on a "broken today" claim, run `git log --oneline -- <cited-paths>` for concurrent-session work on that exact surface FIRST. Broken-today claims age in hours under concurrent EMs; the fix may have already landed. Apply: verify-before-act, not verify-after; never pause a release ceremony or open a spinoff stub on a broken-today premise without a HEAD check.

## concurrent rename + scoped commit can land delete-half without add-half

Concurrent rename plus your scoped commit can land the delete-half without the add-half, silently. When a sibling EM runs `git mv old-path new-path` concurrently, your explicit-path `git add -- old-path` will stage the deletion (because old-path is gone) but NOT stage the add (because new-path is a different path). Result: committed tree is missing the file. Apply: after a scoped commit on a shared branch, `git show --stat HEAD` to verify the expected add landed, not just the delete.

## H15 — Orientation-cache "in-flight concurrent" flag must be verified against live branch before building

Before planning or executing a ticket the orientation cache flags as "in flight under a concurrent session," grep the live branch for that ticket's commits FIRST. The in-flight flag is a STOP-and-check signal — parallel duplicate work is the failure mode. Apply: `git log --oneline --grep="<ticket-id>" origin/<branch>` before starting any work flagged as concurrent-in-flight.

## stash-pop conflict silently rolls back disk state in multi-agent sessions

Multi-agent stash-pop conflicts silently roll back disk state — the final reviewer reads a stale tree. In multi-agent sessions where multiple sessions may stash independently, stash-pop conflicts abort silently (no error message on stdout), leaving the file as it was before the pop. Use a WIP commit instead of `git stash` in multi-agent contexts. Apply: in any concurrent-EM session, replace `git stash push` / `git stash pop` with `git commit -m "wip: <context>"` / `git reset HEAD~1`.

## consumed/claimed or in_flight handoff means concurrent session already owns it

A `consumed` or `claimed` (formerly `consumed`; DR-084) status, or an `in_flight` handoff frontmatter deployment_state, means a concurrent session already owns it. The `consumed_at`/`consumed_by` stamp — or its DR-084 successor `claimed_at`/`claimed_by` (the on-disk corpus is mixed; read both) — is a collision signal; grep the shared branch and decisions dir before building on a handoff that shows this status. Apply: `git fetch && git log --oneline -- state/handoffs/<file>` before picking up any handoff; if `consumed_by` OR `claimed_by` is populated, stand down and surface to PM.

## Gate failure during long ceremony may be stale code — re-run before treating as real

A gate failure during a long ceremony (workweek-complete, parallel fan-out) may be stale checked-out code that a concurrent EM is actively fixing. Re-run the gate after sibling commits land before treating it as a real failure. Also: capture shared-file appends (week-changelog, orientation-cache) via commit message or a scoped append, not full-file Write, when a sibling may be doing full-file Writes concurrently.

## Peer-session convergence can rescind a PM gate-override mid-plan

**A PM gate-override granted to one session can be rescinded mid-plan when a peer session converges on a different settled architecture on the same shared question.** A spinoff sitting `awaiting_gate` can be overridden by the PM ("worth covering, not parked") while a peer session is independently shipping work that *resolves the same architectural choice differently* — when that peer's commit lands, the override evaporates and the spinoff returns to `awaiting_gate`. The planning + reviewer dispatch + sidecars between override and rescind are not wasted (they're substrate for the gate-fire pickup), but the pipeline churn is real: revert frontmatter, write a successor handoff, mark plan deferred, re-dispatch integrator on the deferred plan.

**How to apply.** At handoff pickup on a shared-decision workstream, check peer-session activity *before* claiming: `git log --oneline --all --since=<handoff-write-date> -- <peer-workstream-paths>` and `ls tasks/<peer-workstream>/`. When a PM directive crosses a peer-session decision boundary, surface the peer activity to the PM explicitly ("the peer is running X right now — plan in parallel or wait?") rather than taking the override at face value. On a rescind: preserve the planning substrate (mark plan `status: deferred`, fold reviewer findings anyway so it's gate-fire-ready, write a successor handoff, chain-archive at workstream-complete). Do NOT delete the plan or sidecars; do NOT in-place mutate a `consumed-handoff-frozen` handoff — the frozen-handoff doctrine exists exactly because rescinds are the case where in-place mutation feels right and is wrong.

- [`scoped-safety-commits.md`](./scoped-safety-commits.md) — the commit-content enforcement surface (`coordinator-safe-commit`, touch-tracker, hunk-scoping, the full atomic-gesture / blanket-race / reflog-probe treatments). This page is the symptom catalog; that page is the machinery.
- [`daily-branch-discipline.md`](./daily-branch-discipline.md) — the commit-location enforcement surface (branch-shape hook, shared-bus framing, plumbing-reword).
- [`cross-repo-communication.md`](./cross-repo-communication.md) — same-repo and cross-repo session coordination via memos.
- ~/.claude/CLAUDE.md § Concurrent-EM Git Operations — the boot-loaded doctrine summary.
- `pretooluse-deny-contract.md` — JSON deny mechanics for the enforcement hooks.

### H27 — Pre-commit hook child processes inherit `GIT_INDEX_FILE` — `cwd` does NOT override it

**Symptom.** A test that runs `git add` against a tmp repo passes fine when run directly. When the same test is invoked from inside a `git commit` pre-commit hook, the commit itself fails with `error: invalid object … for '<path>'` at the internal tree-write step — AFTER the hook returns 0 and all test assertions pass.

**Trap.** When git fires a pre-commit hook, it sets `GIT_INDEX_FILE` (and potentially `GIT_DIR`, `GIT_WORK_TREE`, `GIT_OBJECT_DIRECTORY`, `GIT_ALTERNATE_OBJECT_DIRECTORIES`) in the hook's environment pointing at the real repo's commit machinery. Any child process spawned inside the hook — including `execSync('git add .', { cwd: tmpDir })` — **inherits** the parent's git env vars. The `cwd: tmpDir` option redirects the working directory but does NOT scrub the inherited `GIT_INDEX_FILE`. Result: `git add` in the tmp repo stages the tmp repo's files into the *real* repo's index. When git then runs `git write-tree` to finalize the commit, the staged blobs reference objects that don't exist in the real object DB, producing `error: invalid object` and a hard abort. `git write-tree` from a standalone shell works fine — only commits-with-hooks exhibit the failure, making the root cause hard to see.

**Rule.** Any test that runs `git` against a tmp repo from inside a hook context MUST scrub `GIT_INDEX_FILE`, `GIT_DIR`, `GIT_WORK_TREE`, `GIT_OBJECT_DIRECTORY`, and `GIT_ALTERNATE_OBJECT_DIRECTORIES` from the env it passes to `execSync`/`spawn`. Canonical scrub recipe:

```js
const { GIT_INDEX_FILE, GIT_DIR, GIT_WORK_TREE,
        GIT_OBJECT_DIRECTORY, GIT_ALTERNATE_OBJECT_DIRECTORIES,
        ...cleanEnv } = process.env;
execSync('git add .', { cwd: tmpDir, env: cleanEnv });
```

For shell-based hooks, use `env -u GIT_INDEX_FILE -u GIT_DIR -u GIT_WORK_TREE git add .` before any git operation in the tmp directory. The invariant: a tmp-repo git operation must receive ONLY the variables appropriate to the tmp repo's own git context — never the ambient hook env.

*Composes with the cross-platform portability rule: any hook-spawned subprocess inheriting an unintended env var is platform-portable only if the scrub is portable. Use the `env` object / `--unset` form, not bash-only variable tricks.*

### H28 — Concurrent-EM HEAD race on a hot sibling repo — coordinate a pause window, don't tight-loop retry

**Symptom.** A `git` op against a hot sibling repo (or the shared branch) keeps losing a HEAD race — every retry collides with another session committing/advancing the ref, and a tight retry loop never converges.

**Trap.** Tight-loop retrying a HEAD-mutating op against a ref that a concurrent session is actively advancing is a livelock, not a transient — the retry window and the sibling's commit cadence overlap indefinitely. Even where the sibling is a same-machine, registry-visible peer reachable via direct message (`cross-repo-communication.md` § "Then, the sync-vs-async gate"), a tight retry loop is the wrong moment to negotiate a pause live — interrupting a session mid-burst to ask it to back off costs more than it saves, and the loop itself out-paces any round trip.

**Rule.** Do NOT tight-loop retry a HEAD race. Either (a) coordinate a pause window — commit your own work narrowly, write a memo (H12), and let the sibling's burst finish before re-attempting — or (b) branch off the contested ref so your op lands on a private base and reconciles later. The fix is to *stop contending*, not to contend faster.

### H29 — Shared-branch sibling-reconciliation must find the PARITY GAP, not just duplicates

**Symptom.** After a concurrent same-workstream session ran in parallel, you reconcile by deduplicating overlapping work — and miss that the sibling *also* left a gap: work it was expected to do that neither session landed.

**Trap.** Reconciliation reflexively looks for *over*-production (two sessions did the same thing — visible as duplicates). The harder failure is *under*-production: a concurrent session co-driving the same workstream split the work implicitly, and a slice fell between the two sessions with neither owning it. Duplicates are loud; the parity gap is silent.

**Rule.** When reconciling a workstream a concurrent same-workstream session co-drove, audit in BOTH directions: dedup the overlap AND diff the union of both sessions' output against the workstream's intended scope to surface the slice neither session landed. `git log --oneline <session-start>..HEAD` from both sessions' start points + the plan/handoff scope is the parity oracle — not just a duplicate-row grep. Composes with § "Detecting Concurrent Work at Pickup / Plan-Time" (find the peer first) and H15 (the in-flight flag is a stop-and-check).

### H30 — Union-commit on a shared hot file when hunk-isolation is unavailable

**Symptom.** Your fix needs a change in a shared hot file a sibling EM also has uncommitted changes in, and `git add -p` cannot cleanly isolate your hunks from theirs (interleaved edits, overlapping regions).

**Trap.** This is the H1/H4/H12 collision at its hardest: you can't stage only your hunks, you can't reach the sibling to ask them to commit first, and holding your edit uncommitted exposes it to a blanket sweep. The clean splits (H12 memo, `git add -p`) have run out.

**Rule.** When hunk-isolation is genuinely unavailable on a contested hot file, **commit the union** of both sessions' changes with a **dual-credit** commit (name both workstreams / both EM sessions in the body) AND **PM-relay** — surface to the PM that a union-commit landed foreign hunks under a shared subject so the sibling EM is informed. Then **scope your own review to exclude the foreign hunks** — review only your changes, not the sibling's, since you cannot vouch for work you didn't author. The union-commit is the last-resort when the concurrency seam can't be split (H12); the dual-credit + PM-relay + scoped-review trio is what keeps it auditable rather than a silent re-attribution.

### H32 — A concurrent session adding a hard-dependency to a shared install/setup helper breaks sibling workstreams' test fixtures

**Symptom.** Contract tests owned by a *different* in-flight workstream start failing — their fixtures bail before reaching the assertion — even though production and your own tests are green.

**Trap.** A shared setup/install helper (`_pr_write_setup_state`, a receipt writer, a state-stamper) gains a new hard prerequisite: one session edits it to resolve a dependency (e.g. a coordinator-clone path via `<settings-home>/bin/resolve-coordinator-clone`) and `return 1` if unresolved — placed *before* the helper's core write. Production is fine because the dependency resolves there. But a sibling workstream's test fixtures build a synthetic environment (`fake_home`) that has no shim for the new dependency, so the helper now bails before stamping the state the sibling's tests assert on. The break is invisible to the editing session — it surfaces only in the peer's suite.

**Rule.** Before adding a hard prerequisite to a shared setup/install helper, grep every caller AND every test fixture that exercises it — a new early-`return 1` guard is a contract change on all of them. Prefer a soft-degrade (skip the enrichment, still perform the core write) over a hard bail, or gate the new prerequisite behind a flag the fixtures can satisfy. Composes with H16/H18 (shared-file edits under concurrency) — here the shared surface is a *helper contract*, not a file's staged hunks.

### H33 — Editing a live PreToolUse Bash-matcher hook mid-fan-out aborts every concurrent agent's Bash tool

**Symptom.** Every concurrent agent/reviewer's `Bash` tool calls start failing at the PreToolUse boundary simultaneously — fleet-wide, not scoped to the session that's editing anything — with an error like `line 479: unexpected EOF while looking for matching...`. The failure has no connection in the failing sessions' own recent actions; it looks like the harness itself broke.

**Mechanism.** The Claude Code harness `exec`s each hook fresh from disk on every matching tool call — there is no cached/compiled hook process. A multi-`Edit` sequence against a hook script that is *live* (registered in `hooks.json` and currently matching in-flight tool calls) leaves each intermediate on-disk state briefly the *actual enforcement code* for every concurrent session, not just the editor's own. If any intermediate state is syntactically broken (e.g. an Edit lands between adding an opening heredoc/brace and its matching close), the very next `Bash` call from ANY session — including ones with no relation to the edit — execs the broken script and fails at the PreToolUse gate.

**Blast-radius scope.** Any hook registered under a PreToolUse matcher that includes `Bash` is fleet-blast-radius. As of this writing (verify via `grep -oE '"matcher": "[^"]*Bash[^"]*"' coordinator/hooks/hooks.json` and cross-reference the hook script paths in the same block), the live hooks are `session-heartbeat.py` and `preuse-bash-dispatch.py` — the latter dispatches into claude-klabauter `coordinator_core.bash_guards.*` (including the `block-illegal-filename.sh` and `block-reviewer-bash-outside-allowlist.sh` logic; the DoE-side bash equivalents do not exist). This list is a static grep fact against `hooks.json`, not a fixed enumeration — re-derive it before relying on it, since hook registration changes over time.

**Rule.**
1. **Prefer editing these hooks only on a quiescent tree** — no live fan-out with concurrent agents whose Bash tool depends on the hook staying syntactically valid throughout the edit.
2. **When unavoidable, never multi-`Edit` the live path.** Stage the edit on a scratch copy, `bash -n`-validate the scratch copy, and land via a single atomic `mv` (same-filesystem rename is atomic — there is no window where the live path is a half-written file). Use claude-klabauter `coordinator/bin/edit-live-hook.py` (stage → edit → validate → atomic-swap helper) rather than hand-rolling this pattern.

Composes with H20 (build-input edit mid-build) — same root shape (a consumer reads a file incrementally/repeatedly while a producer edits it in place), different consumer (harness `exec` of a hook vs. an incremental compiler) and different failure mode (fleet-wide Bash-tool abort vs. a chimera build artifact). See also `docs/wiki/hook-best-practices.md` for hook authoring conventions generally.

---

## Ceremony-engine hazards under concurrent EMs (claude-klabauter `wsc_resolve` / `wsc_commit`)

The claude-klabauter-owned `/workstream-complete` ceremony ops (`ceremony.wsc_resolve` → `ceremony.wsc_commit`) were built against a single-session tree; several of their steps read whole-tree or time-window state that is wrong on a shared `work/*` branch. Claude-klabauter owns the ceremony engine, DoE owns the contract — the durable fixes below route to claude-klabauter via cross-repo memo; the per-incident recovery is the EM's.

### H34 — claude-klabauter `wsc_commit` dirty-tree gate wedges on concurrent-EM peer files

**Symptom.** `wsc_commit` refuses to stage / exits non-zero (observed exit 3) because the tree carries unattributable files — 99 from concurrent sessions in one case — even though your own explicit `wsc_paths` staging is clean. The op's *archival* phase (handoff archive, claim release) may still run, leaving the ceremony half-done.

**Trap.** `wsc_commit` runs its dirty-tree gate over the WHOLE working tree, not the session-attributable subset. On a shared branch, an unattributable-peer-files tree is the ROUTINE state, so the gate's commit phase is effectively unusable under concurrency — the gate condition IS the normal condition.

**Rule.** Don't fight the gate. Finish the gate-blocked tail manually with explicit-path commits (concurrent-EM-safe by design): `coordinator-complete-entry.py` for the completion entry, the handoff shipped-stamp, then `git add -- <wsc_paths> && git commit -- <wsc_paths>` (agree-case form; see H3's disagree-case caveat). Also raise `CC_INVOKE_TIMEOUT_SECS` — the `cc_invoke` default 10s is too short for `wsc_commit`'s commit+push tail. The proper fix is claude-klabauter's: scope the dirty-tree gate to session-attributable paths, or make it advisory when explicit `wsc_paths` staging succeeds.

### H35 — claude-klabauter `wsc_resolve` / `wsc_commit` mis-attributes a CONCURRENT session's consumed handoff

**Symptom.** `wsc_commit` HALTs at `handoff.archive_transition:stamp_only failed_critical 'consumed_by != current sid'` (symptom signature carried over from the pre-native-cutover era — formerly `coordinator-handoff-archive.sh:stamp-only failed_critical …`), or silently stamps a SIBLING workstream's `in_flight` handoff `shipped` — even though the commit / push / claim-release / completion-entry all succeeded (top-level `exit_code=1` masks a mostly-successful ceremony).

**Trap.** `wsc_resolve`'s disposition detection is a time-window heuristic, not `consumed_by`/`claimed_by`-keyed. On a shared branch it (a) mis-classifies a single-session memo-pickup (zero handoffs consumed) as `chain-terminal` and selects a handoff `consumed_by`/`claimed_by` a DIFFERENT sid as predecessor, or (b) returns `disposition=chain-terminal` with `consumed_handoff=null`, and `wsc_commit` Step 2.7 falls back to stamping the most-recent `in_flight` handoff — which under concurrency is a sibling's. Either path is a cross-session substrate write.

**Rule.** Before phase-2, verify `wsc_resolve`'s `consumed_handoff_path` against the grep-confirmed `consumed_by:<your-sid>` (or its DR-084 successor `claimed_by:<your-sid>` — the on-disk corpus is mixed; grep both) handoff. Do NOT blind-re-run — it deterministically re-fails on the foreign handoff. Recovery: hand-correct `resolved_state`'s `consumed_handoff_path` (step_0 / 2.6.5a / 2.7) to your own `consumed_by`/`claimed_by`-verified handoff, then re-invoke (idempotent); or finish the archival bookkeeping manually with explicit-path commits, leaving peer handoffs untouched. Claude-klabauter-side fix (landed — the write path stamps `claimed_by`/`claimed_at`, formerly `consumed_by`/`consumed_at`): Step 2.7 must match the claim-holder against the current sid and never stamp a handoff whose claim-holder differs; `wsc_resolve` must populate `consumed_handoff` whenever it sets `disposition=chain-terminal` and filter chain-terminal candidates by current sid.

### H36 — Shared unscoped tempfile collides with a concurrent EM running the same ceremony

**Symptom.** A two-phase op driven across separate Bash calls (e.g. `wsc_resolve` → `wsc_commit`) reads back the WRONG state: `wsc_resolve` reported single-session, but the saved file later shows `chain-terminal` with a foreign `consumed_handoff` — and the commit then fails trying to archive a handoff you never consumed.

**Trap.** A shared tempfile name like `$TMPDIR/wsc_resolve_out.json` is a single global path, not session-scoped. A concurrent EM running the SAME ceremony in the shared tree clobbers it between your two Bash calls, so you feed the PEER's resolved_state (their chain-terminal, their consumed_handoff) into your commit. Same shared-global-ref hazard as the stash traps (H7), applied to intermediate op state.

**Rule.** Scope every cross-call temp path by session id — `$TMPDIR/wsc-$SID-resolve.json` — or, better, pipe the resolve output directly into the commit invoke in ONE bash block so no intermediate file exists to collide. (Also observed: `wsc_commit` is not cleanly idempotent after a partial failure — `cs_archive` re-runs as exit 1 'already archived' and each retry lands another ceremony commit; flag to the op owner.)

### H37 — Workstream-complete auto-scoping over-scopes on a shared branch (raw commit range + Session-Id grep)

**Symptom.** The review partition and auto-sourced `diff_loc` / `sha_range` balloon far past what you actually shipped — one case reported `diff_loc` 968 against ~10 authored lines — over-mandating the code-review partition.

**Trap.** Two independent over-scoping sources on a shared concurrent-EM branch:
- The B-wave brightline (`diff_loc`, `slice_count`, `partition_boundaries` from `wsc_resolve`) is derived from the raw `HEAD~N..HEAD` commit range, which folds in unrelated sibling commits.
- `git log --grep 'Session-Id: <sid>'` matches commits that merely *reference* your sid in their body (handoff / pickup cross-refs), not only commits your session authored.

**Rule.** Scope the code-review slices to the workstream's OWN file set — `git diff <base>..HEAD -- <workstream-files>` — and treat `slice_count` as an upper bound to right-size, not a floor. Verify authorship on the tip commits (`%B` trailer) and use the explicit `review_trail` override scoped to your own commits rather than the sid-grep auto-source. Composes with H10 (path-filtered `git status` lies) — both are "the auto-scoping oracle over-counts under concurrency."

---

### H38 — The reaper can release a LIVE executing session's in-flight handoff (stale heartbeat)

**Symptom.** `reap-orphaned-in-flight-handoffs.py` re-parks an execution handoff to `ready_to_fire` with 'holder dead, executed nothing' while that session is actively executing and committing the plan.

**Trap.** The reaper's liveness check (`live_session_ids(cwd)`) omitted the live session because its heartbeat was stale / unregistered at reap-time — a long backgrounded Workflow wave can outrun the heartbeat's freshness window. The reaper then reads the live handoff as an orphan and dispatches `archive-stamp-cli`'s `unconsume-handoff` verb, releasing its claim (`status: active`, `deployment_state: ready_to_fire`, `claimed_by`/`claimed_at` stripped — DR-084's rename from `consumed_by`/`consumed_at` has landed on the write path; the on-disk corpus is mixed, so a dual-read fallback to the legacy names still applies — a `park_note:` recording the release), exposing the workstream to duplicate pickup.

**Rule.** This is a break-class liveness-detection gap, not paranoia. The reaper does not flip a mis-detected orphan to `abandoned` — a released claim is recoverable (the handoff and its work are not destroyed; the same session can simply re-consume it) — but the exposure to a duplicate picker-upper starting a second execution of the same handoff is unchanged. In the observed case no duplicate execution occurred ONLY because the plan-execution claim (`cs_claim_plan`) stayed held AND a git-log-by-chunk-id reconcile would have stood down a picker-upper — defense-in-depth (plan-claim + reconcile) is load-bearing, not belt-and-suspenders. Do not rely on the reaper's orphan verdict alone; the real fix is ensuring Claude Code sessions maintain a fresh-enough `live_session_ids(cwd)` heartbeat during long backgrounded Workflow waves. Composes with the CLAUDE.md `RAW-PID-LIVENESS` rule (liveness is `session_live`/`live_session_ids`/`claim_holder_live` only, never a stored pid; the bash names `cs_live_session_ids`/`cs_claim_holder_live` are retired).

### H39 — A benign concurrent fleet-automation commit relocates your plan/doc — not corruption

**Symptom.** During `/execute-plan` Phase 4, moments after you stamp a plan `status: implemented`, a `BASE..HEAD` diff shows the plan as a large deletion at `docs/plans/<plan>.md` and `ls` reports 'no such file'.

**Trap.** Stamping `status: implemented` makes the plan terminal; a concurrent fleet-automation commit then moves it to `archive/specs/YYYY-MM/` — a legitimate, expected relocation that reads as data loss from your side of the tree. Do not attribute the move to a named op without checking that op has a live occasioned call site: `fleet.archive_completed_plans` was killed and rebuilt and currently has none, so it is not what moved your plan.

**Rule.** Before treating a post-stamp missing-plan as corruption, check `archive/specs/` for the relocated file. This is benign auto-archival — the same "concurrent automation touched your surface, not contamination" shape as H15 (concurrent `/update-docs` pre-populates archive / orientation entries). Disk and `git log --follow -- <path>` are authoritative; a bare deletion in a scoped diff is not proof of loss.

### H40 — A shared non-git advisory-state file raced by concurrent hook fires is the wrong shape — use a per-session cursor

**Symptom.** A hook on a high-frequency event (`Stop`, `UserPromptSubmit`, `PostToolUse`) needs to surface a durable, backlog-bearing signal exactly once. A single shared state file (a "surfaced" flag, a last-seen marker) written by that hook is exposed to the same concurrent-EM race as any other shared-tree mutable state — two sessions' hook invocations can interleave reads and writes of the one file, so one session's fire clears or advances state a sibling session hasn't seen surfaced yet, or both fire redundantly on the same backlog.

**Trap.** This is not a hypothetical — this repo has now hit the shape twice. `_check_push_failures()` (`runtime-tripwire-em-check.py`) needed exactly-once surfacing of newly-grown `.git/push-failures.log` content across every `Stop`/`UserPromptSubmit`/`PostToolUse` fire in a session; the zero-tool-use subagent detector's Stage-2 surfacer needed the same exactly-once guarantee for its own durable detection records. A shared engine-side or single-file "surfaced" flag would need locking, an atomicity ask, or a cross-session protocol to be race-free under concurrent EMs — exactly the coordination cost this repo's shared-tree model exists to avoid paying per-feature.

**Rule.** The standing answer is **per-session state placement, not a shared mutable flag**: a byte-offset cursor (or equivalent sentinel) at a session-scoped path — `.git/coordinator-sessions/<session_id>/<name>-cursor.txt` — read and advanced only by that session's own hook invocations. Two concurrent sessions each own their own cursor file, so there is nothing to coordinate: no locking, no atomicity ask, no cross-session protocol, because the two sessions never touch the same file. This is the same shared-bus-vs-private-state principle as H36 (scope cross-call tempfiles by session id), applied to advisory-surfacing state rather than intermediate ceremony-op output. Full pattern shape, worked-example citation, and the load-bearing "advance the cursor only after emission, never at read time" ordering rule: `docs/wiki/hook-best-practices.md` § Exactly-once advisory surfacing.

### H41 — A stash cache accumulates unnoticed because nothing ever looks at `git stash list`

**Symptom.** A `git stash list` run for an unrelated reason returns entries weeks old holding thousands of lines of several sessions' in-flight work. Nobody knew the pile existed; no session reported losing anything, because the loss is invisible from every side — the stasher's tree looked clean, and the swept sessions' edits simply were not there next time anyone looked.

**Trap.** H6 (stale-pop) and H7 (wrong-owner) are both hazards of *acting on a stash you have already found*. Neither covers the case where nobody looks. `git stash list` is not on any routine path: no ceremony reads it, no status surface reports it, and a stash is invisible to `git status`, so a swept tree reads as clean. That makes accumulation the failure mode with no natural discovery event — the fleet found two such caches (19 entries, ~20,900 patch lines between them) purely by accident, one after three weeks. Time-to-detection matters more here than for H6/H7 because recoverability decays: the further HEAD advances past a stash's parent, the harder its content is to reconcile against what has since shipped.

**Rule.** Detection is now mechanical rather than remembered — that is the part worth recording. `/workday-start` Step 1.92 runs claude-klabauter's read-only `stale-stashes` counter each morning and surfaces any entry past the age threshold (default 7 days). It is advisory and never gates; it only guarantees the pile stops being invisible. The forward action on a surfaced entry is inspect-and-recover under H6/H7 discipline, never a drop — a stale entry may hold a sibling's only copy of real work. Do not treat the guards that closed the creation paths as making this redundant: they stop new caches, they do not surface existing ones, and a hand-run stash remains legitimate and untracked.

### H42 — Reverting a hunk to *disown* it (not to scope a commit) destroys a peer's uncommitted work

**Symptom.** A dispatched agent's diff contains files outside its brief. The EM runs `git checkout -- <those paths>` to undo the out-of-scope change and tells the agent off for it. The agent's denial turns out to be correct — a concurrent session was working that exact surface, and its uncommitted edits are now gone.

**Trap — three doors, one impulse, and only one of them has a pathspec answer.** The impulse is *"make this not-mine."* It reaches the working tree by at least three routes:

1. **Scoping a commit.** Answered by an explicit pathspec: scoping a commit never requires mutating the working tree.
2. **Disowning an edit you did not authorise.** *Not* answered by a pathspec — there is no commit involved. This is the door that has actually fired.
3. **Tidying a tree before a test run.** Same shape, same loss.

Two compounding factors make door 2 feel justified at the moment it fires:

- **A working-tree edit that appeared during your agent's run is not evidence your agent made it.** On a shared tree with active peers, "changed while my dispatch ran" is not attribution at all. Check for concurrent sessions on that surface before assigning authorship — and treat a specific, checkable denial from the agent as better evidence than any timestamp.
- **`git blame` on an *uncommitted* line carries zero authorship information.** It stamps `Not Committed Yet` with **the clock at the moment you run blame** — reading that back as "when the agent wrote it" is reading your own wristwatch and calling it a fingerprint. Never cite blame output on an uncommitted line as provenance.

Note the guard does not cover this door: `BLOCK-DESTRUCTIVE-GIT-REVERT` matches only whole-tree forms (`git checkout .`, `git restore .`, `git reset --hard`, unscoped `stash -u`). A *scoped* `git checkout -- <path>` is explicitly out of its match set, by design, so an operator can revert their own file. Door 2 is exactly a scoped checkout — prose is the only thing standing there.

**Rule.** **Never revert a hunk you did not write.** If a diff contains work outside the brief, the move is to **report it and stop** — never to revert it. On a shared tree you frequently cannot tell whose it is, and being wrong destroys work that lives in no commit, no stash, and no reflog. If it genuinely must come out of the way, `git stash push -- <path>` with a provenance message, never `git checkout --`. See H12 for the peer-detected case and H7 for stash-ownership discipline.

### H43 — Parking a load-bearing edit uncommitted in a *peer's* tree is not custody

**Symptom.** You land a fix in a sibling repo and deliberately leave it uncommitted — committing it isn't yours to do, and reverting it would re-expose a live vulnerability, because the peer's hook imports their working tree in-process and so the dirty edit *is* the live guard. Later it turns up at their `HEAD` as `auto-commit: N file(s) rescued at session stop (session <id>, <dir>)` — committed by a session that had no idea what it was committing.

**Trap.** The reasoning that keeps the edit uncommitted is sound about why not to *revert* and says nothing about who else can *commit*. A peer tree runs its own Stop-event auto-commit sweep (`scoped-safety-commits.md § 3b`): an unattended committer with **no confirmation gate of any kind**, grouping dirty files mechanically by directory under a generic safety-net message. A dirty file with no `touched.txt` record falls through `compute_scope()`'s **mtime fallback** and silently joins whichever session stops first. That § documents the mechanism as a same-repo concurrency hazard; nothing there says the sweep will equally adopt a change a *sibling* repo's EM parked on purpose.

For a security-guard change the cost is not the content — that survives intact — it is that an unreviewed guard edit reaches `HEAD` under a message carrying none of the incident context, destroying the audit trail that the change was ever reviewed. The edit was never one `git checkout --` from being lost; it was one Stop hook from being committed by a stranger.

**Rule.** Treat "uncommitted in a peer tree" as a state with an owner you do not control, never as a hold, and **never rely on dirtiness as a review gate**. If the edit must stay live, say so in the memo *and* tell the peer EM directly if live in the registry, so their sweep does not adopt it blind — or ask them to commit it deliberately with real provenance. If a rescue commit does capture it, say so in the thread rather than letting the generic message stand as the record. Same failure class as H4 and H24, one repo boundary out.

### H44 — Break-class fix-by-default meets a live peer's path claim, and the owner cannot be reached

**Symptom.** A break-class defect has a small, verified fix, and every file it touches is claimed by
a live peer session. Flag-severity doctrine says fix it by default; shared-tree doctrine says the
path is not yours. Attempts to reach the owner go nowhere — no registry name for the claiming UUID,
no reply, or they are mid-operation. Both rules are right and neither yields, so the disposition
gets improvised under pressure: take the path anyway, or drop the fix on the floor.

**Trap.** The two failure shapes are not symmetric, and neither is what it looks like from inside.
Taking the path reads as decisive; it is a silent write into work that lives in no commit, and the
peer discovers it as corruption of their own change. Dropping the fix reads as respectful; it
discards verification that has already been paid for, and the next owner of that file rediscovers
the defect from zero. A third improvisation — escalating to the PM as *"peer won't answer, what do
I do?"* — is the forbidden shape twice over: it is a break-class item sent up as a question, and it
makes the record contingent on someone else's next move.

**Rule — revert clean, land the described patch, report partial.**

1. **Do not take the path.** Ownership on a shared tree is unconditional; there is no break-class
   override. A tree a dozen sessions write to only works because the rule has no exceptions worth
   arguing at 200 lines of context.
2. **Attempt to reach the owner**, and stop attempting when it does not work. There is no time
   threshold and deliberately so — a threshold is a countdown to claiming someone's file, which is
   worse than the problem it solves.
3. **Revert your own hunks out of their files** and leave them as you found them. Yours only:
   H42 still binds every other line in the file.
4. **Land the change in a surface you own** — the property that matters, not a named file: a
   surface you can write at will (`state/bug-backlog/`, `state/debt-backlog/`,
   `state/improvement-queue/`, a spine row, a commit), carrying the **diff**, the **verification you
   actually ran**, and the **reason it is unapplied**. Not "surfaced to the PM", not an owner field
   no queue schema has, not a spinoff you proposed — anything contingent on another session's next
   move is a gamble, not a record. Same standard the memo-pickup doctrine applies to open items.
5. **Report it as partial, never as done.** A tested fix degraded into a described fix is a real
   loss, not a wash. Naming the residual is what stops the disposition becoming a way to look
   finished while shipping nothing.

The disposition preserves the work rather than the credit: the next owner of that file inherits a
verified patch and a reason, instead of a rediscovery. Reported by `example-game-repo-em` 2026-09-01 after
hitting it on a routine two-line MCP-registry fix. See H42 for the revert discipline, H43 for the
peer-tree custody case, and `docs/wiki/coordinator-tripwires/a-blocking-path-claim-with-no-reachable-owner-still-has-a-disposition.md`.
