# Workday-Start — Internals Reference

Detail companion to `commands/workday-start.md`. Step numbers refer to that command.

## Step 0 — Branch Setup (full procedure)

Ensure all work today happens on a proper work branch and consolidate any lingering open branches from previous days.

1. **Determine today's work branch name:**
   - Machine name: `hostname`, lowercased.
   - Today's branch: `work/{machine}/{YYYY-MM-DD}`

2. **If already on today's work branch:** skip to Step 1.

3. **Find open (unmerged) work branches owned by this user**:
   ```bash
   git branch --list "work/{machine}/*" --no-merged main
   ```
   Use the same `{machine}` from step 1 — scopes consolidation to this user/machine. Collaborators' `work/{their-machine}/*` branches are never touched. Exclude today's branch from the result list.

4. **Create or checkout today's branch:**
   - New: `git checkout -b work/{machine}/{YYYY-MM-DD}`
   - Existing: `git checkout work/{machine}/{YYYY-MM-DD}`
   - Name collides with an already-merged branch: `work/{machine}/{YYYY-MM-DD}-2`

5. **Consolidate open branches** — for each branch from step 3:
   ```bash
   git merge {branch-name} --no-ff -m "consolidate {branch-name} into today's work branch"
   ```
   - Clean merge: continue.
   - Conflict: **stop immediately.** `git merge --abort`. Report: _"Merge conflict consolidating {branch-name} — manual resolution required. Continuing workday-start without consolidating this branch."_ Do not attempt automatic resolution.
   - After all merges: old branches remain as refs (do not delete — PM may want to inspect).

6. **Push today's branch to establish remote tracking:**
   ```bash
   git push -u origin work/{machine}/{YYYY-MM-DD}
   ```

7. **Report:**
   - Consolidated: _"On branch {today-branch}. Consolidated N open branches: {list}."_
   - Nothing to consolidate: _"On branch {today-branch}. No open work branches to consolidate."_
   - Conflicts blocked consolidation: flag clearly.

**Why this matters:** without daily consolidation, sessions pile up unmerged work branches indefinitely. The daily consolidation keeps branch history clean and surfaces accumulated divergence early — before it becomes a merge nightmare.

## Step 1 — Handoff reconciliation (rationale + procedure)

**Why surface-only:** handoffs are archived only when consumed (`/pickup` marks them) or when the PM explicitly directs archival. An old handoff that nobody picked up is a signal that work was deferred — not that the handoff is stale. workday-start surfaces the state; the PM decides what to do.

**Why cross-reference completed archive:** handoffs describe *intended* next steps. The completed archive records *outcomes*. A handoff can remain active even after the work it describes has shipped — especially when a different session completed the work without consuming the handoff. The cross-reference catches this, but the PM confirms before archival.

**Why git-reconcile pending items:** the completed archive records sessions that ran `/workday-complete` or `/update-docs` — it is not exhaustive. Executor sessions that commit and exit without ceremony never land in the archive. The git log is authoritative; the archive is a secondary cross-check. Both checks together cover failure modes the other misses.

### Reconciliation procedure (per handoff, before reporting items as actionable)

a. **Git log check:** extract handoff date from filename/header. Run:
   ```bash
   git log --oneline --since="<handoff-date>" --all
   ```
   Scan commit subjects for key nouns from each pending item. A subject clearly matching an item is strong evidence it shipped.

b. **Plan/stub status check:** for any pending item that references a plan/stub file (`docs/plans/*.md`, `tasks/*/stub.md`, `tasks/*/todo.md`), Read the file's `**Status:**` field. A stub the handoff calls "pending" but whose own status reads `Shipped`, `Completed`, or `Execution complete` is closed.

c. **Drop confirmed-closed items.** Verified-closed items do NOT surface as today's work. Note in the report as _"verified-closed since handoff"_ so the PM sees the reconciliation was done.

**Empirical baseline:** expect 30–60% of inherited items to be already closed. Skipping means the Morning Briefing recommends ghost work.

**Partial-completion claims** (DroneSim T1.2 pattern): before surfacing handoff items described as "stalled", "unfinished", or "partial", verify against `git log --oneline --all -- <relevant paths>`, the `archive/completed/` log, and live artifact state. The handoff's status is a hypothesis, not ground truth.

## Step 5.5 — Orientation Cache Content Derivation

Generate `tasks/orientation_cache.md` — a compact summary for the SessionStart hook to inject in subsequent sessions instead of raw repomap/DIRECTORY content.

1. **Key Documentation:** if `docs/README.md` exists, include a `## Key Documentation` section:
   ```
   ## Key Documentation
   - **Master docs index:** [`docs/README.md`](../docs/README.md) — wikis, research, specs, plans, reference
   - **Wiki guides:** [`docs/guides/`](../docs/guides/) — [N] living guides with embedded decision records
   - **Research outputs:** [`docs/research/`](../docs/research/) — [N] timestamped research files
   - **Plans:** [`docs/plans/`](../docs/plans/) — [N] implementation and design plans
   ```
   Count files in each directory. Reference `docs/guides/DIRECTORY_GUIDE.md` if present. If `docs/README.md` is absent: _"No docs/README.md — run `/update-docs` or `/project-onboarding` to create one."_

2. **Structure:** read `tasks/repomap.md`, extract top 15 by rank. Note total file count.

3. **Navigation:** read `DIRECTORY.md` or `docs/DIRECTORY.md`, summarize at directory level (name + file count + purpose).

4. **Code Statistics:** `scc --no-complexity --no-cocomo --no-duplicates --sort code` if available — total LOC + top 5 languages. Skip silently if scc not installed (`~/bin/scc` is the conventional Windows install path).

5. **Health Snapshot:** compact version of Morning Briefing health data.

6. **Doc Inventory:** checklist of standard docs (from Step 2).

7. **Staleness markers:** repomap age, last update-docs run (from Step 2).

8. **Yesterday's Strategic Review:** glob `archive/daily-summaries/YYYY-MM-DD.md`, take most recent. If it has a `## Strategic Review` section, extract a 3-5 line excerpt for a `## Yesterday` section. Skip silently if no daily summaries exist.

**Frontmatter:** `generated_by`, `generated_at` (ISO 8601), `git_head_at_generation` (current HEAD short hash).

**Target: 40-60 lines.** Replaces ~300 lines of raw hook injection for subsequent sessions.

**If `tasks/` directory doesn't exist:** skip. Not all repos use `tasks/`.
