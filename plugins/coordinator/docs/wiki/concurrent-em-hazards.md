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
3. **Sibling sessions are NOT addressable.** `SendMessage` reaches Agent Teams teammates only — not a sibling Claude Code session sharing the tree. You cannot ask the other session to pause. Coordination is through committed artifacts (git, a memo file), never through a channel.

Sibling commits, sibling dirty files, and a branch that advanced since you oriented are **normal**, not contamination. The discipline is to commit your own work narrowly and immediately, verify what actually landed, and never assume a clean tree.

---

## Hazard Catalog

Indexed by the symptom you'll actually see. Each entry: the trap, why it happens, the rule.

### H1 — `git add` absorbs a sibling's uncommitted edits (commit-content contamination)

**Symptom.** Your commit subject says one workstream; `git show --stat` lists files you never touched.

**Trap.** Any `git add` that names a *directory* (`git add tasks/ docs/`), an *untracked dir* (`git add -- <dir>` recurses into every file under it, including a sibling's 29K-line `diff.patch` or a 423MB sqlite blob), or a *whole shared file* a sibling also edited, stages content that isn't yours. `Edit`-replace-all followed by `git add -- <file>` is blanket-staging by another name — it stages every on-disk hunk, not just yours (one incident absorbed ~290 LOC of a sibling's probe additions). Path-scoped `git add` protects against *cross-file* contamination but not *cross-hunk* contamination within a contested file.

**Rule.**
- Never `git add -A` / `git add .` / `git add <dir>` on a shared branch (CLAUDE.md § Concurrent-EM Git Operations).
- Stage explicit files: `git add -- <file1> <file2>`.
- For a file a sibling also holds dirty, stage by hunk: `git add -p -- <file>` (SC-DR-010, [`scoped-safety-commits.md`](./scoped-safety-commits.md)).
- **`git diff --cached --name-only` before every commit** — read the FULL staged set, not your mental model of it. This single check pre-empts H1, H2, and H10. It is load-bearing, not ceremony.

### H2 — A "no stray staged" check that prints but doesn't halt is theater

**Symptom.** A pre-commit guard echoes the offending foreign path, then the commit runs anyway and re-attributes the sibling's work.

**Trap.** The `grep … || echo "stray!"` shape detects but does not gate. Under concurrent EMs a detect-without-halt check is worse than none — it produces a false sense of safety and a contaminated commit.

**Rule.** Gate the commit on the check's exit code (non-zero → unstage with `git rm --cached -- <foreign>` or abort), or stage by explicit file list so the stray never enters the index. A detect-then-silently-proceed guard is the same anti-pattern as detect-then-silently-pick (CLAUDE.md § Implementation Standards). Recovery when it already shipped: `git rm --cached -- <foreign-path>` and re-commit.

### H3 — Commit without trailing `-- <pathspec>` is unsafe even after a clean scoped `git add`

**Symptom.** `git commit -m "..."` (no pathspec) lands a sibling's staged files under your subject; or returns *"no changes added to commit"* when you know you just staged work (a sibling commit swept the index between your `add` and `commit`).

**Trap.** Splitting `add` and `commit` across two Bash tool calls opens a window for a sibling's `git add -A` / `--blanket` to mutate the index. Path-scoped `git add` does not scope the *commit*.

**Rule.** Treat stage+commit as one atomic gesture in a single Bash call, and always pass the trailing pathspec:

```bash
git add -- <paths> && git commit -m "<subject>" -- <paths>
```

The trailing `-- <paths>` on `git commit` is non-negotiable — it scopes the commit by pathspec regardless of what else landed in the index. If a commit returns "no changes added," the work is likely in the reflog under a sibling's SHA — probe before retrying (see R4). Full treatment in [`scoped-safety-commits.md`](./scoped-safety-commits.md) § "Atomic stage+commit gesture".

### H4 — A sibling's workstream-complete / blanket sweep absorbs your in-flight edits

**Symptom.** Your uncommitted edits ship inside a sibling's commit; that commit's subject doesn't describe your work. Or your staged handoff `git mv` is reverted by the same sweep.

**Trap.** While you hold an edit uncommitted, a concurrent `/workstream-complete`, `/workday-complete`, or `--blanket` sweep stages and commits whatever is dirty in the tree — including your work. This is the inverse of H1 (you're the victim, not the polluter), and it is structurally undefendable from your side once the edit is dirty and unguarded.

**Rule.** **Commit shared / hot files explicitly and immediately after the edit — never batch them for workstream-complete.** For known shared buses (`tasks/lessons.md`, `tasks/improvement-queue.md`, shared registration/index files), `git add -- <file> && git commit -m "..." -- <file>` the moment the edit is complete. The window between edit and commit is the entire attack surface; close it to near-zero.

### H5 — Committing a shared registration/index file ships a HEAD that imports untracked modules

**Symptom.** `git add -- __init__.py` (the hookimpl list, plugin registry, module index) sweeps in concurrent sessions' uncommitted registrations whose target modules are still `??` untracked. HEAD now imports modules absent from git — a latent broken-clean-install, masked on the author's disk and (if the loader graceful-fails on ImportError) silently non-registering on a clean checkout.

**Trap.** This is H1 specialized to registration files, with a second-order failure: the absorbed edits introduce `import` statements whose targets you never committed.

**Rule.** Before committing any shared registration/index/`__init__` file under concurrent EMs:
1. `git diff --cached --name-only` — see the full absorbed set (H1 baseline).
2. For every new `import` / `from … import` the commit introduces, confirm the target module is `git ls-files`-tracked. An import of an untracked sibling module is a HEAD-break, not a harmless extra.

If you find absorbed registrations, the fix-forward is to commit the referenced impls+tests too (if complete and green on disk), turning the latent break into a real landing — not to revert the registration. (project-rag-ue-addon tc-34, 2026-05-26: commit `526ba4705` imported four nonexistent-in-git chunker modules this way.) → cross-link: [`scoped-safety-commits.md`](./scoped-safety-commits.md) H1 staging rules.

### H6 — Blind `git stash pop` reverts committed fixes (the stale-stash trap)

**Symptom.** A crash-day, pickup, or concurrent-session stash looks like unsaved work; popping it reverts fixes that already shipped as committed work.

**Trap.** A stash diff is relative to the stash's *parent*, not HEAD. After HEAD advances (the session continued and committed equivalents through normal flow, or a sibling committed them), the stash's "additions" become *reversions*. The stashed content can be the same bytes as what was committed — but relative to HEAD, applying the stash undoes the commit. A blind pop silently rolls back later commits.

**Rule.** Before popping any stash older than the branch tip, diff each stashed blob against HEAD per file:

```bash
git rev-parse stash@{0}:<f>   # vs  git rev-parse HEAD:<f>   → SAME = redundant, skip
git diff HEAD:<f> stash@{0}:<f>   # on the differs: a hunk that REVERTS a later commit = stale
```

Rescue only genuinely-unique content (e.g. an uncommitted lesson), then `git stash drop` — never blind-pop. (project-rag 2026-05-27: `stash@{0}` base `22ad8f53` would have reverted an OOM prereq, a paths-lint routing fix, and an ndcg dedup.) Pairs with CLAUDE.md "Probe edits in git stash push -u / pop." Distinct from H7 (wrong-owner stash trap).

### H7 — Bare `git stash pop` pops a *sibling's* stash (the wrong-owner trap)

**Symptom.** A bare `git stash pop` dumps unrelated content + merge conflicts (e.g. a `DU` on a 423MB `chroma.sqlite3`, a `UU` on `.workday-start-marker`) into your tree.

**Trap.** `stash@{0}` is a single global ref shared across all sessions in the tree — it is NOT scoped to your session. Worse: `git stash push -- <path>` that prints *"No local changes to save"* is a **NO-OP** (often because a sibling already *committed* your edit), so your subsequent bare `pop` reaches past empty and pops the sibling's `stash@{0}`.

**Rule.**
- Before relying on a stash to isolate a change, confirm it's an uncommitted working-tree delta: `git status --short <path>` non-empty. Under concurrent EMs your edit may already be committed, making the push a no-op.
- **NEVER `git stash pop` without `git stash list` confirming `stash@{0}` is yours** (branch + subject match). Always stash with a message: `git stash push -u -m "<subject>"`.
- For "does my additive change cause failure X?" — reason it out. A purely-additive change (new module + one registration) cannot affect unrelated tests; don't stash-dance on a shared tree to find out.
- Recovery if you popped a sibling's stash: `git stash show --name-status stash@{0}` to scope, restore only those paths (`git rm --cached` for not-in-HEAD workspace artifacts, `git checkout HEAD -- <f>` for tracked), leave the stash for its owner.

### H8 — `--amend` / `rebase` / `checkout --detach` collide with concurrent work

**Symptom.** A history-rewriting op on a shared dirty-tree branch aborts (dirty tree), reverts a sibling's tracked files, or collides with a concurrent amend.

**Trap.** `git rebase` aborts on a dirty tree; `checkout --detach` reverts tracked files; `--amend` races a sibling amend. All three touch the working tree or index a sibling is using.

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

### H11 — `git checkout --ours` and mtime pitfalls

**Symptom.** Downstream mtime-based pre-flights misfire after a conflict resolution; or conflict markers persist after `--ours`.

**Trap.**
- `git checkout --ours <path>` updates the worktree mtime even when content matches HEAD — mtime-based detectors (the commit-helper's mtime fallback included) then misclassify the file as freshly-edited.
- `git checkout --ours <path>` resolves the `AA` index stage but does NOT refresh the worktree from stage 2 — conflict markers can persist in the file.

**Rule.** After `git checkout --ours <path>`, follow with `git checkout HEAD -- <path>` and **verify the file content** (grep for conflict markers `<<<<<<<`) before staging. Be aware mtime-based scope tooling may misfire on `--ours`-touched files; prefer explicit `git add -- <path>` over mtime fallback in conflict-recovery flows.

### H12 — Sibling-session coordination is via committed memo, never their dirty file

**Symptom.** A fix needs a 2-line change in a file a sibling holds dirty (` M`). Editing it or `git commit -- <file>` sweeps the sibling's uncommitted work (H4). `SendMessage` doesn't reach them.

**Trap.** Same-repo sibling sessions are not addressable. Touching their dirty file is the H1/H4 collision; you have no channel to ask them to commit first.

**Rule.** **Split at the concurrency seam.** Commit the clean part of your fix; write a dated `archive/YYYY-MM-DD-<topic>.md` memo with the exact atomic change + file links; leave their dirty file untouched. The receiving session reads the memo and lands it. Distinct from a cross-repo memo (PM-relay, different repo) and from Agent Teams `SendMessage` (same team context). → [`cross-repo-communication.md`](./cross-repo-communication.md) § same-repo concurrent sessions. If you discover >100 LOC of unstaged changes in a shared file you didn't edit, an active peer is on that surface — surface to PM, edit unrelated files only, resume after they commit ([`scoped-safety-commits.md`](./scoped-safety-commits.md) § "Large unstaged diff in shared files").

### H13 — Scope process-kills to your own invocation, not the runtime class

**Symptom.** Killing "all pytest processes" (or any runtime-class kill) catches a concurrent EM's unrelated run, the embed sidecar, or the MCP daemon.

**Trap.** The Python/pytest/node runtime is shared across concurrent sessions and long-lived services. A class-level `Stop-Process -Name python` / `pkill -f pytest` is indiscriminate.

**Rule.** Match on the specific command line (your test paths/flags) before killing — `Win32_Process.CommandLine` filtering on Windows, `pgrep -f "<your-exact-args>"` on POSIX. Never blanket-kill a runtime shared with concurrent sessions or daemons.

### H14 — Concurrent `/workweek-complete` or `filter-repo` flips/resets your tree

**Symptom.** A concurrent `/workweek-complete` flips the working tree to `main` mid-session, landing your commits on `main`. A concurrent `git filter-repo` resets working-tree state across all sibling sessions.

**Trap.** These are tree-global operations a sibling can run while you're mid-flight; they're not scoped to one session.

**Rule.** **Commit narrative drafts and WIP BEFORE any review/merge/history-rewrite ceremony you know a sibling might run.** After such a ceremony, verify your branch is still your branch (`git branch --show-current`) and your commits didn't land on `main` (`check-shipped-on-main.sh` / `git log main`). If your commits landed on `main` via a sibling's flip, surface to PM — do not improvise a fix on `main` (read-only-main doctrine).

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
- **Peer detection uses remotes, not `--branches`.** `git branch --branches` is structurally wrong for detecting concurrent EMs — peers are visible only via `origin/work/{peer}/*` remote refs. Use `git for-each-ref refs/remotes/origin/work/` to enumerate peer machines' active branches.
- **Before authoring overlapping code fixes**, a concurrent-EM peer `git log` check on the target paths — a sibling may have already fixed it. → [`daily-branch-discipline.md`](./daily-branch-discipline.md).

---

## Cross-platform / tooling gotchas under concurrency

- **CRLF `autocrlf` silently drops files from commits** despite `git add` succeeding (Windows). Verify staged-count vs committed-count post-commit. → `claude-code-platform-gotchas.md`.
- **Cross-shell line-count comparison is NOT a drift oracle.** `wc -l` (Git-Bash) and `Measure-Object -Line` (PowerShell) disagree on the *same* file because of CRLF and final-newline handling — bash counts `\n` terminators, PowerShell counts lines including a non-terminated last line. A line-count delta between two shells is a measurement artifact, not evidence a sibling edited the file. (2026-05-29: a 9-vs-18 line discrepancy on one `lessons.md` was misread as a concurrent-EM edit mid-strip and drove an over-revert of two strips that had actually succeeded; `git` proved neither file was touched that day.) **Use `git status` + `git log -- <file>` as the only drift oracle, and stay in ONE shell for any given measurement.** → composes with H10 (path-filtered `git status` lies) — both are "the measurement you reached for is lying about concurrent state." (Source: meta-repo, 2026-05-29.)
- **Multi-line commit messages via the Bash tool** must use a heredoc or `git commit -F <file>`, not PowerShell `@'…'@` here-string syntax — the here-string leaks a stray `@` into the subject. → `claude-code-platform-gotchas.md`.
- **Pre-commit hooks must stream large staged diffs** (`mktemp` + `grep`), not capture `git diff --cached` into a bash variable — multi-hundred-MB staged-deletion diffs OOM the shell. → `coordinator-tripwires.md` hook-authoring.
- **GitHub force-merge requires bypassing BOTH rulesets AND classic branch protection** — they are independent gates.

---

### H15 — Concurrent `/update-docs` silently pre-populates archive and orientation entries

**Symptom.** You reach `/workstream-complete` to write an archive entry or update the orientation cache, only to find the entries are already there — or worse, you write a duplicate.

**Trap.** A sibling session running `/update-docs` while you were working may have swept your commit hashes into `archive/completed/`, the orientation cache, and the project tracker. The sibling cannot tell you; the surfaces look clean until you diff.

**Rule.** Before adding any archive/orientation entry at workstream-complete, grep `archive/completed/` for your commit hashes and check the orientation cache's `git_head_at_generation` field. If your work is already indexed, skip the entry — do not add a duplicate. Duplicates cause merge friction and wasted edits on shared branches.

*Source: holodeck `tasks/lessons.md` (holodeck-L37, central-promoted 2026-05-28).*

### H16 — Shared-file edits under concurrent EMs get clobbered at workstream-complete

**Symptom.** Edits to `tasks/lessons.md` or `tasks/improvement-queue.md` accumulated during a session vanish when a concurrent session commits its own version before your workstream-complete commit.

**Trap.** `tasks/lessons.md` and similar shared buses are last-writer-wins on the working tree. A staged `git mv` or pending edit held for the batched workstream-complete commit is overwritten the moment a sibling's commit/checkout touches the same path (H4). Two lessons appended mid-session can be silently lost.

**Rule.** When editing a known shared file during a multi-session window, commit it immediately after the edit — `git add -- <file> && git commit -m "..." -- <file>` — rather than holding it for the batched workstream-complete commit. The window between edit and commit is the entire attack surface; close it to near-zero.

### H17 — Line-number-keyed allow-lists drift silently under concurrent editing

**Symptom.** A `file:line`-keyed exemption registry (e.g., a spawn-audit allow-list) suddenly shows false violations after a session's edits shift line numbers.

**Trap.** Any registry keyed by line number is O(edits) fragile and breakage is invisible until the gate runs. On a shared concurrent-EM branch, multiple sessions' edits compound the drift across sessions. Prior "Line drifted" triage comments in such files are evidence of this failure pattern repeating.

**Rule.** Reconcile via the test's own collectors (e.g., `_collect_hits` + stale-key diff), not truncated pytest output. Longer-term, such registries should key on a stable marker (function signature, symbol name), not line number. When taking over a `file:line`-keyed registry, treat any pre-existing drift comments as a structural warning — the registry design will fail again.

### H18 — Workstream-complete housekeeping artifacts are exposed to concurrent tree resets

**Symptom.** Mid-`/workstream-complete`, a concurrent crash-recovery session runs a working-tree reset that wipes this session's uncommitted lessons, plan edits, orientation updates, and untracked completion-log entries.

**Trap.** The branch is a shared bus; other sessions run destructive git ops (checkout, clean) without coordination. Committed work survives; uncommitted working-tree state has no protection.

**Rule.** During `/workstream-complete`, commit each housekeeping artifact promptly rather than batching all edits then committing once at the end. Untracked deliverables (completion entries, review trail JSON) are especially exposed to `git clean` by a sibling's crash recovery. Workstream-complete is not the moment to accumulate — it is the moment to commit fast and narrow.

### H19 — A just-authored plan's cited seam can drift mid-execution when a concurrent session refactors shared infra

**Symptom.** An executor finds the function, file, or call-site it was directed to modify has moved — extracted into a shared lib or renamed — between plan-write and execution.

**Trap.** The plan-substrate-staleness rule ("survey before dispatching") has a concurrent-session corollary: even same-session-authored plans can drift when a sibling EM refactors shared infra in parallel. The plan's seam was accurate at write time; the disk is different at execution time.

**Rule.** When an executor finds its cited seam has moved into shared/out-of-scope territory, the correct response is an in-scope adaptation that preserves behaviour — NOT silently widening scope to absorb the drift (Branch D violation). Flag the deviation in the return so the EM records it. If the seam moved into a shared library that is genuinely out-of-scope, compute the new field or behaviour via an inline alternative, deliver identical observable behaviour, and report the deviation explicitly.

*Source: meta-repo `tasks/lessons.md` (central-promoted 2026-05-29).*

### H20 — Editing Build-Input Source During an In-Flight Long-Running Build

**Symptom.** A source file edit lands mid-build; the build picks up partial state (some translation units see the new code, some see the old), producing a build artifact that is neither the pre-edit nor the post-edit executable — silent correctness corruption that passes compilation.

**Trap.** On a shared concurrent-EM tree, a long-running build (UBT, Cmake, tsc `--watch`, gradle) reads source files incrementally. An edit to a header or a widely-included module that lands mid-build is incorporated into only the translation units compiled after the edit — the earlier units already compiled against the old version. The resulting artifact is a chimera.

**Rule.** Before editing a file that is a build input on a shared tree — especially widely-included headers, generated files, or source files in an active hot-loop — check for an in-flight long-running build: `ps aux | grep -E "(UBT|cmake|tsc|gradle)"` (or equivalent). If one is running, either wait for it to finish and re-trigger, or make the edit and force a full rebuild. A partial-input build is worse than a clean rebuild: it produces an artifact that looks healthy but is not. (Source: project-rag-ue-addon, 2026-05-29.)

### H21 — Orphaned `.git/index.lock` survives commits under concurrent-EM (Git-for-Windows)

**Symptom.** A `.git/index.lock` file (~the size of a full index copy) outlives the `git` process that created it; subsequent commits from *other* processes succeed via fresh lock cycles, but a later commit in the *same* worktree fails with `fatal: Unable to create '.../.git/index.lock': File exists.` A `.git/objects/maintenance.lock` is often co-present. (Source: holodeck consult memo, 2026-05-30, `cross-repo/inbox/2026-05-30-index-lock-leak-concurrent-em.md`.)

**Trap — this is NOT coordinator code.** `coordinator-auto-push` only runs `git push` (never touches the index); `coordinator-safe-commit`'s session lock is `.overlap-gate.lock` (PID-stamped, self-reaping), never `index.lock`, and it commits via plain foreground git. The real mechanism is a Windows file-sharing artifact: a foreground `git add`/`git commit` writes a full index copy to `index.lock`, then the final `rename(index.lock → index)`/unlink fails with a sharing violation because another process holds a handle on `index` — a concurrent session's `git`, antivirus/Defender, the search indexer, or **git's own *detached* auto-maintenance child** (`gc.autoDetach` defaults true; the co-present `maintenance.lock` is its fingerprint). The commit's objects+ref are already durable, so the commit "succeeds" while the orphan lock survives. `index.lock` carries no holder PID, so liveness cannot be read from the lock itself.

**Rule — two-leg fix, both ship to every coordinator install:**
1. **Production-reduction:** `gc.autoDetach false` (set by `coordinator-configure-git`, asserted per-repo at `/setup`, `/project-onboarding` § 3f.5, and every coordinator session start via `session-init.sh` — kept per-repo by design, not globalized, to avoid changing auto-gc behavior in non-coordinator repos). Auto-gc then runs synchronously and releases its handles before the triggering command returns — no detached child to orphan the lock. Keeps automatic repacking (unlike the heavier `gc.auto 0`).
2. **Self-heal:** `coordinator-reap-stale-locks` removes an orphaned `index.lock`/`next-index-*.lock`/`maintenance.lock` ONLY when it is both aged (≥120s; maintenance ≥600s) AND stable across a re-sample (no active writer) — never a fresh/in-flight lock. Runs as a pre-flight in `coordinator-safe-commit` and at every session start, so worktrees auto-recover instead of needing manual `rm -f`. Manual recovery: `tasklist`/`pgrep` to confirm no live git, then `rm -f .git/index.lock .git/next-index-*.lock .git/objects/maintenance.lock`.

### H22 — Phantom-dirty index under concurrent-EM (Git-for-Windows + NTFS)

**Symptom.** `git status` reports a large set of tracked files as modified that have no real content change; `git update-index --refresh` (even `--really-refresh`) does not clear them, and the racy-entry count can *grow* mid-refresh (e.g. 3181→3183) as other sessions touch the index. (Source: striker concurrent-EM observation, 2026-06-01.)

**Trap.** Git-for-Windows writes nanosecond mtimes into `.git/index`, but NTFS reports them back at coarser precision, so on every stat the recorded and observed mtimes differ and the entry is flagged "racy." The default `core.checkStat` also compares `ctime/ino/dev`, which are likewise unstable across the NTFS round-trip. Concurrent EM sessions continuously rewriting the shared `.git/index` re-arm the racy flag faster than any single refresh can clear it — a refresh-clobber loop that no amount of `--refresh` escapes.

**Rule.** `core.checkStat minimal` — compares only `mtime+size` (both stable across the NTFS round-trip), dropping the unstable fields. Set by `coordinator-configure-git` alongside `gc.autoDetach false`, so it self-heals per-repo via `/project-onboarding` § 3f.5 and every coordinator session start (`session-init.sh`). Unlike `gc.autoDetach` (which we keep per-repo), `core.checkStat minimal` is benign and content-neutral on every platform and the phantom-dirty pattern affects *any* repo on Git-for-Windows + NTFS, so `/setup` **also** sets it as the machine-wide default (`git config --global core.checkStat minimal`) — covering every current and future repo, coordinator-managed or not. Manual one-off: `git config --global core.checkStat minimal`. **Does not cure H23** — that phantom is a *size* mismatch, which even `minimal` compares.

### H23 — EOL phantom-dirty index: stale line-ending blob size flags content-equal files (Git-for-Windows)

**Symptom.** `git status` perpetually flags files as ` M` that `git diff` and `git diff --cached` both report as having nothing to commit. Forensics on one file: HEAD blob and index blob are byte-identical (e.g. both 41313 B, LF), but the recorded stat size differs from the worktree (e.g. worktree 42218 B, CRLF) — or the mirror image (worktree LF 5115 B, index CRLF 5218 B, HEAD LF). The count can run into the thousands and grow as siblings commit. `core.checkStat minimal` does **not** fix it (size is compared even by `minimal`); `git update-index --refresh` does **not** fix it (the size genuinely differs). (Source: striker + holodeck concurrent-EM observation, 2026-06-01.)

**Trap.** This is a *pending line-ending renormalization that lives only in the index*. `git diff`/`git diff --cached` renormalize-then-hash, so they correctly see the content as equal and report empty. But `git status` uses the recorded blob *size* as a stat shortcut, and the EOL round-trip changes the size — so the file is flagged forever. The naïve fix `git add --renormalize .` is **forbidden under concurrent-EM**: it re-stages every modified file's *current* worktree content, absorbing siblings' live uncommitted edits into the next commit and clobbering a sibling's mid-commit staged blob (the exact absorption hazard the doctrine bans).

**Rule — `coordinator-renormalize-index`.** Because each phantom's content already renormalizes-equal to the index/HEAD, a plain `git add <path>` refreshes only the stat-cache and stages **nothing committable** — no commit needed. The tool refreshes ONLY the phantom set, computed as `(git ls-files -m) MINUS (git diff --name-only) MINUS deleted-in-worktree` = stat-modified minus real worktree-vs-index content diffs minus deletions. This excludes every genuine worktree edit AND any path a sibling has staged (index≠HEAD with a differing worktree). **Residual race (honest scope, not "by construction impossible"):** the set is a snapshot and the `git add` fires later, so a sibling overwriting a phantom path in that window could be staged; we shrink the window to near-zero by re-confirming against a fresh `git diff` immediately before staging, and the worst case is bounded — the sweep only ever `git add`s, never commits, so an absorbed edit sits merely *staged* (visible, recoverable) and is caught downstream by `coordinator-safe-commit`'s touched-files filter before it can enter a commit. **Safe on a live shared tree at any time.** Hardening: a real `git diff` *failure* (not empty) aborts loudly rather than treating all paths as phantoms; deleted-in-worktree paths are excluded (a `git add` there would stage a deletion); `--ignore-errors` keeps one poison path from sinking the batch; and the write is deferred if a live `index.lock` is present (no added contention vs § H21). Requires bash 4+ (associative arrays) — `#!/usr/bin/env bash` prefers a modern bash, and it no-ops cleanly on older shells (e.g. macOS stock /bin/bash 3.2), where the NTFS phantom does not arise anyway. It is packaged as a **silent, idempotent SessionStart hook**: `session-init.sh` runs it at every session start in every repo, alongside `coordinator-reap-stale-locks` and `coordinator-configure-git` — a no-op (no index write) when the tree is clean, so it adds no noise. This is preferred over per-ceremony prose steps (which depend on an agent executing them and fire on the wrong cadence); the session terminators' dirty-tree gates only carry a one-line *recognition* clause treating a content-equal ` M` file as benign (never a case-(c) orphan) as a backstop for phantoms that appear mid-session. Also invokable on demand; `--check` reports the phantom count without writing the index. The heavier repo-wide cure — `git add --renormalize . && commit` — fixes it for *all* clones at once but must run on a quiet tree (no live sibling edits); prevention is a consistent `.gitattributes` (`* text=auto`) so the index never re-acquires an EOL-stale blob.

## See also

- [`scoped-safety-commits.md`](./scoped-safety-commits.md) — the commit-content enforcement surface (`coordinator-safe-commit`, touch-tracker, hunk-scoping, the full atomic-gesture / blanket-race / reflog-probe treatments). This page is the symptom catalog; that page is the machinery.
- [`daily-branch-discipline.md`](./daily-branch-discipline.md) — the commit-location enforcement surface (branch-shape hook, shared-bus framing, plumbing-reword).
- [`cross-repo-communication.md`](./cross-repo-communication.md) — same-repo and cross-repo session coordination via memos.
- CLAUDE.md § Concurrent-EM Git Operations — the boot-loaded doctrine summary.
- [`pretooluse-deny-contract.md`](../pretooluse-deny-contract.md) — JSON deny mechanics for the enforcement hooks.
