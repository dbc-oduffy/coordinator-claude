# Workday-Start — Internals Reference

Detail companion to `commands/workday-start.md`. Step numbers refer to that command.

## Step 0 — Branch Setup (full procedure)

Spec backlink: `docs/plans/2026-05-07-daily-branch-doctrine-rethink.md` Phase 3.

The goal is to ensure today is within the active workstream branch's span — not to create a new branch every day. A span-form branch (`work/striker/2026-05-06to07`) is the normal shape when work runs across midnight. The hook polices branch *shape*, not branch *date*; `cs_is_allowed_branch` is the policy oracle.

**Lib sourcing (run once at the top of the script context):**
```bash
LIB_PATH="${HOME}/.claude/plugins/coordinator-claude/coordinator/lib/coordinator-daily-branch.sh"
[[ -f "$LIB_PATH" ]] && source "$LIB_PATH"
```

### Step 0.1 — Sync main

Run `sync-main.sh` first; abort if it exits non-zero. Never create or rename branches from stale main.

### Step 0.2 — Determine machine and today's date

```bash
MACHINE=$(cs_compute_machine)   # always lowercase (Staff Engineer F11; lib Phase 1)
TODAY=$(date +%Y-%m-%d)
CURRENT=$(git branch --show-current)
```

`MACHINE` is used in every branch name constructed below. Because `cs_compute_machine` lowercases its output unconditionally, new branches are always `work/striker/...` regardless of `$COMPUTERNAME` case.

### Step 0.3 — Precedence switch (evaluate in order; stop at first match)

**Check 1 — Stale-commit guard (runs first):**
```bash
LAST_EPOCH=$(git log -1 --format="%ct" 2>/dev/null || echo 0)
NOW_EPOCH=$(date +%s)
AGE_DAYS=$(( (NOW_EPOCH - LAST_EPOCH) / 86400 ))
```
If `$AGE_DAYS > 2` AND `$CURRENT` matches `work/*/...` → jump to **Step 0.5 (consolidation)** using `$CURRENT` as the base. Do NOT rename; surface to PM via the A/B/C Branch Reconciliation Decision (see `commands/workday-start.md` § Step 0 conflict handling). Rationale: a stale span branch whose end-suffix happens to equal today is still dead work warranting triage, not a silent continue.

**Check 2 — Already-in-span (runs second):**
```bash
LAST_EPOCH=$(git log -1 --format="%ct" 2>/dev/null || echo 0)
cs_should_prompt_rename "$CURRENT" "$TODAY" "$LAST_EPOCH"
SHOULD_PROMPT=$?
```
If `$SHOULD_PROMPT` is **1** and the branch is a valid `work/{machine}/...` form → exit Step 0 silently. Today is already within the branch's span. Proceed to Step 1.

**Check 3 — On main / no workstream branch (runs third):**
If `$CURRENT == "main"` or `cs_parse_branch_span "$CURRENT"` returns non-zero (branch is not a valid daily/span form) → create a fresh workstream branch:
```bash
COORDINATOR_OVERRIDE_BRANCH=1 \
COORDINATOR_OVERRIDE_BRANCH_REASON="workday-start step 0 create workstream branch" \
git checkout -b "work/${MACHINE}/${TODAY}"

git push -u origin "work/${MACHINE}/${TODAY}"
```
Name collision with an already-merged branch: append `-2`. Then proceed to **Step 0.5 (consolidation)**.

**Check 4 — Midnight-rename (runs last):**
Condition: `cs_should_prompt_rename "$CURRENT" "$TODAY" "$LAST_EPOCH"` returns 0. This means the current branch is a valid `work/{machine}/...` branch with recent commits that does not yet cover today.

Run the rename procedure below silently (no prompt — engineering housekeeping, not a product call). Emit a one-line notice in the Morning Briefing:
```
Renamed $OLD → $NEW (crossed midnight)
```
PM can revert via `git branch -m` if they object.

### Step 0.4 — Rename procedure (Staff Engineer F5 — atomic, reversible)

```bash
OLD=$(git branch --show-current)
START_DATE=$(cs_parse_branch_span "$OLD" | awk '{print $1}')
NEW="work/${MACHINE}/$(cs_format_span_suffix "$START_DATE" "$TODAY")"

# Concurrent-rename race guard (plan Risk #3):
# Another session on this machine may have already renamed while we prompted.
# Re-read the current branch name and bail if it already ends in today's DD.
CURRENT_RECHECK=$(git branch --show-current)
TODAY_DD=$(date +%d)
if [[ "$CURRENT_RECHECK" == *"to${TODAY_DD}" ]]; then
  echo "Branch already renamed by another session — nothing to do."
  # Continue with CURRENT_RECHECK as the active branch; skip to Step 0.5.
else
  # Step a: local rename (cheap, reversible)
  COORDINATOR_OVERRIDE_BRANCH=1 \
  COORDINATOR_OVERRIDE_BRANCH_REASON="workday-start step 0 rename across midnight" \
  git branch -m "$OLD" "$NEW"

  # Step b: atomic remote rename
  # git push --atomic sends two refspecs in one transport round-trip:
  #   ${NEW}:${NEW}  — create the new remote ref
  #   :${OLD}        — delete the old remote ref
  # Both succeed or both fail (requires git ≥2.4, GA since 2015).
  if ! COORDINATOR_OVERRIDE_BRANCH=1 \
       COORDINATOR_OVERRIDE_BRANCH_REASON="workday-start step 0 atomic rename push" \
       git push --atomic origin "${NEW}:${NEW}" ":${OLD}"; then

    # Step b failed — roll back local rename so local and remote stay consistent
    COORDINATOR_OVERRIDE_BRANCH=1 \
    COORDINATOR_OVERRIDE_BRANCH_REASON="workday-start step 0 rename rollback after atomic push failure" \
    git branch -m "$NEW" "$OLD"

    echo "ERROR: remote rename rejected; local rolled back to $OLD. Manual recovery may be needed."
    echo "Hint: check remote ref-update hooks or push permissions."
    exit 1
  fi

  # Rename complete — update tracking to the new remote branch
  git branch --set-upstream-to="origin/${NEW}" "$NEW" 2>/dev/null || true
fi
```

**Override rationale:** `git branch -m` and `git push --atomic` are both hook-blocked ops when the target name is being mutated. The inline `COORDINATOR_OVERRIDE_BRANCH=1` is required on each of the three git commands (rename, push, rollback). Never export this variable — set it inline per command.

### Step 0.5 — Consolidate open branches

Find open (unmerged) work branches for this machine:
```bash
git branch --list "work/${MACHINE}/*" --no-merged main
```
(Also check `work/$(echo "$MACHINE" | tr '[:lower:]' '[:upper:]')/*` for legacy uppercase branches during the transition period.)

Exclude the current active branch from the result list. For each remaining branch:
```bash
COORDINATOR_OVERRIDE_BRANCH=1 \
COORDINATOR_OVERRIDE_BRANCH_REASON="workday-start step 0 consolidate {branch-name}" \
git merge {branch-name} --no-ff -m "consolidate {branch-name} into active workstream branch"
```

- **Clean merge:** continue to next branch.
- **Conflict:** `git merge --abort` immediately. Report: _"Merge conflict consolidating {branch-name} — manual resolution required."_ Do not attempt automatic resolution. Surface to PM via the A/B/C Branch Reconciliation Decision.
- After all merges: old branches remain as refs (do not delete — PM may want to inspect).

### Step 0.6 — Push and report

```bash
git push -u origin "$(~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-current-branch)"
```

Report:
- _"On branch {active-branch}. Consolidated N open branches: {list}."_
- _"On branch {active-branch}. No open work branches to consolidate."_
- _"Renamed {old} → {new} to reflect midnight span."_ (if rename occurred)
- Conflicts blocked consolidation: flag clearly.

**Why this matters:** without consolidation, sessions pile up unmerged work branches indefinitely. The span-aware rename keeps the active branch name accurate without splitting the workstream history across a date boundary.

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
