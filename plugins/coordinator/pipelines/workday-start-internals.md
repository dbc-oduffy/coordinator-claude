# Workday-Start — Internals Reference

Detail companion to `commands/workday-start.md`. Step numbers refer to that command.

## Step 0 — Branch Setup (full procedure)

Spec backlink: `docs/plans/2026-05-07-daily-branch-doctrine-rethink.md` Phase 3.

The goal is to ensure the active workstream branch reconciles with `origin/main` daily — not to create a new branch every day. The active workstream may be either:

- **Canonical** — `work/{machine}/{date-or-span}` (e.g. `work/striker/2026-05-06to07`). Span form is the normal shape when work runs across midnight.
- **Named long-lived workstream** — `migration/...`, `release/...`, `feature/...`, etc., authorized at create-time via the inline `COORDINATOR_OVERRIDE_BRANCH=1`. Once it exists with commits ahead of main, workday-start treats it as a legitimate workstream bus.

The hook polices branch *shape* at create-time, not branch *date* at workday-start. Daily ritual is **reconcile with origin/main**, applicable to both branch types. One active workstream branch per machine, kept current with main, until it's ready to merge.

**Lib sourcing (run once at the top of the script context):**
```bash
LIB_PATH="${HOME}/.claude/plugins/coordinator/lib/coordinator-daily-branch.sh"
[[ -f "$LIB_PATH" ]] && source "$LIB_PATH"
```

### Step 0.1 — Sync main

Run `sync-main.sh` first; abort if it exits non-zero. Never create or rename branches from stale main.

### Step 0.2 — Determine machine and today's date

```bash
MACHINE=$(cs_compute_machine)   # always lowercase (the Staff Engineer F11; lib Phase 1)
TODAY=$(date +%Y-%m-%d)
CURRENT=$(git branch --show-current)
```

`MACHINE` is used in every branch name constructed below. Because `cs_compute_machine` lowercases its output unconditionally, new branches are always `work/<machine>/...` regardless of `$COMPUTERNAME` case.

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

**Check 3 — On main / detached / empty branch (runs third):**
If `$CURRENT == "main"` OR HEAD is detached OR `$CURRENT` is non-main with zero commits ahead of `origin/main` → create a fresh canonical workstream branch:
```bash
COORDINATOR_OVERRIDE_BRANCH=1 \
COORDINATOR_OVERRIDE_BRANCH_REASON="workday-start step 0 create workstream branch" \
git checkout -b "work/${MACHINE}/${TODAY}"

git push -u origin "work/${MACHINE}/${TODAY}"
```
Name collision with an already-merged branch: append `-2`. Then proceed to **Step 0.4.5 (reconcile)** and **Step 0.5 (consolidation)**.

**Why "empty branch" qualifies for fresh-cut:** a non-main branch with zero commits ahead is structurally indistinguishable from `main` for workstream purposes — it's an empty container, not work-in-progress. Cutting fresh from main is fine; nothing is being abandoned.

**Check 3.5 — Named long-lived workstream (runs between 3 and 4):**
If `$CURRENT` is non-main, `cs_parse_branch_span "$CURRENT"` returns non-zero (not `work/{machine}/...`), AND `git rev-list --count origin/main..HEAD` > 0 → this is an active named workstream bus (e.g. `migration/from-holodeck-...`, `release/v2.0`). Skip the rename procedure (which is `work/{machine}/...`-specific). Proceed directly to **Step 0.4.5 (reconcile)**, then **Step 0.5 (consolidation)** with this branch as base.

**Why not force a fresh daily here:** creating `work/{machine}/{today}` off main and abandoning the named workstream branch would strand potentially weeks of work on an inactive ref. The PM authorized this branch at create-time via the inline override; daily reconciliation keeps it current with main without forking.

**Consolidation scope for named workstreams:** Step 0.5 (merge open `work/{machine}/...` siblings into the active branch) is **skipped** when the active branch is a named long-lived workstream. The named bus is deliberately scoped (e.g. a migration, a release); folding generic daily work into it cross-pollutes the workstream history. Sibling `work/{machine}/...` branches stay where they are until their own session consolidates them, or until they're explicitly merged via `/consolidate-git`.

**Check 4 — Midnight-rename (runs last):**
Condition: `cs_should_prompt_rename "$CURRENT" "$TODAY" "$LAST_EPOCH"` returns 0. This means the current branch is a valid `work/{machine}/...` branch with recent commits that does not yet cover today.

Run the rename procedure below silently (no prompt — engineering housekeeping, not a product call). Emit a one-line notice in the Morning Briefing:
```
Renamed $OLD → $NEW (crossed midnight)
```
PM can revert via `git branch -m` if they object.

### Step 0.4 — Rename procedure (the Staff Engineer F5 — atomic, reversible)

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

  # Rename complete — update tracking to the new remote branch.
  # Surface (don't swallow) failures: --set-upstream-to should succeed because
  # the atomic push above already published origin/${NEW}; unexpected failure
  # is worth a visible warning rather than a silent || true.
  if ! git branch --set-upstream-to="origin/${NEW}" "$NEW" 2>/dev/null; then
    echo "WARN: could not set upstream to origin/${NEW}; check remote tracking manually."
  fi
fi
```

**Override rationale:** `git branch -m` and `git push --atomic` are both hook-blocked ops when the target name is being mutated. The inline `COORDINATOR_OVERRIDE_BRANCH=1` is required on each of the three git commands (rename, push, rollback). Never export this variable — set it inline per command.

### Step 0.4.5 — Reconcile with origin/main (daily ritual)

Applies to any non-main active branch — canonical `work/{machine}/...` or named long-lived workstream. Runs after the precedence switch resolves and after any rename, before consolidation.

```bash
git fetch origin main
CURRENT=$(git branch --show-current)

if git merge-base --is-ancestor origin/main HEAD; then
  # Already includes origin/main — nothing to do.
  :
elif COORDINATOR_OVERRIDE_BRANCH=1 \
     COORDINATOR_OVERRIDE_BRANCH_REASON="workday-start step 0 reconcile origin/main (ff)" \
     git merge --ff-only origin/main 2>/dev/null; then
  echo "Fast-forwarded $CURRENT to include origin/main."
else
  if COORDINATOR_OVERRIDE_BRANCH=1 \
     COORDINATOR_OVERRIDE_BRANCH_REASON="workday-start step 0 reconcile origin/main (merge)" \
     git merge --no-ff origin/main \
       -m "reconcile origin/main into $CURRENT (workday-start)"; then
    echo "Merged origin/main into $CURRENT."
  else
    git merge --abort
    echo "Reconcile conflict with origin/main — surface via A/B/C Branch Reconciliation Decision."
    # Do not proceed to Step 0.5; PM resolves first.
    exit 1
  fi
fi
```

**Why this replaces "cut a fresh daily off main":** other contributors push to `origin/main` independently. The active workstream branch needs that work folded in daily to stay mergeable — abandoning the branch and cutting a fresh one off main would lose the in-progress workstream. Conflicts on reconcile use the same A/B/C decision flow as consolidation conflicts (`commands/workday-start.md` § Step 0 conflict handling).

**Override rationale:** `git merge origin/main` does not mutate a branch ref, but the hook surface includes `git merge` in some shells (compound parsing). Inline override is cheap insurance; remove if hook coverage analysis confirms it's not needed.

### Step 0.5 — Consolidate open branches

Find open (unmerged) work branches for this machine. Use a case-insensitive glob (the legacy uppercase transition period is over but mixed-case strays still appear from manual branch creates):
```bash
# shopt is bash-only; case-fold the listing portably with grep -i over a wider glob
git branch --list "work/*" --no-merged main | grep -i "^[* ]*work/${MACHINE}/"
```

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
git push -u origin "$(~/.claude/plugins/coordinator/bin/coordinator-current-branch)"
```

Report:
- _"On branch {active-branch}. Consolidated N open branches: {list}."_
- _"On branch {active-branch}. No open work branches to consolidate."_
- _"Renamed {old} → {new} to reflect midnight span."_ (if rename occurred)
- Conflicts blocked consolidation: flag clearly.

**Why this matters:** without consolidation, sessions pile up unmerged work branches indefinitely. The span-aware rename keeps the active branch name accurate without splitting the workstream history across a date boundary.

## Step 1 — Handoff reconciliation (rationale + procedure)

**Why filter to `ready_to_fire` for the primary actionable list, with `awaiting_gate` always surfaced as its own subsection (doctrine reversal 2026-05-08, revised 2026-05-15):** the prior "surface everything" policy presumed the EM grep-walks every handoff to assess readiness — exactly the agentic-grep `deployment_state` is designed to obviate. Sub-second queryability for the actionable list requires a clear filter. The original 2026-05-08 revision hid `awaiting_gate` behind a 14-day staleness gate; empirical use (2026-05-15) showed this buried gated work the PM needed for cross-workstream planning — clear-gate, retarget, or pick-up-early decisions never reached the briefing. Revised behavior: `awaiting_gate` items always surface as a "Gated handoffs" subsection (count + list when present), with a >6-day flag for items where the gate may be stuck. Six days ≈ one working week — long enough to filter normal in-flight gates, short enough to catch ossification. **Archive policy unchanged:** handoffs are archived only via `/pickup` (the atomic archival event), supersession (chain-aware pass), or PM direction — never automatically based on age. Spec backlink: `docs/plans/2026-05-08-roadmap-skill-and-handoff-lifecycle.md` § Phase 3b.

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

**Partial-completion claims:** before surfacing handoff items described as "stalled", "unfinished", or "partial", verify against `git log --oneline --all -- <relevant paths>`, the `archive/completed/` log, and live artifact state. The handoff's status is a hypothesis, not ground truth.

## Step 5.5 — Orientation Cache Content Derivation

Generate `tasks/orientation_cache.md` — a compact, schema-conformant summary the SessionStart hook injects at every boot. **This step does not author the cache directly.** It invokes the shared regeneration routine:

```bash
bash plugins/coordinator/bin/regenerate-orientation-cache.sh --invoker workday-start
```

The routine is the single source-of-truth derivation. This section documents the **canonical schema** that the routine produces and the verifier (`bin/verify-orientation-cache-sync.sh`) enforces. Drift from this schema is a verifier failure at `/update-docs` Phase 11b.

**Why a schema, not prose:** four writers (`/workday-start`, `/update-docs`, `/session-end`, `/handoff`) historically patched the cache with free-form sections, and there was no owner for subtraction. The cache accreted prior-session narrative ("publish-repo-topology-sync just shipped...", "the Staff Engineer R1 (9 findings folded)...", "AC7 dogfood waived by PM") that poisoned every subsequent boot. The schema below is the structural fix: every section is either (a) static template, (b) sentinel-regenerated from disk, or (c) absent. No free-form prose anywhere. See `docs/plans/2026-05-18-orientation-cache-authoring-discipline.md` for the full motivating audit.

### Canonical schema

| Section | Shape | Source-of-truth | Tier |
|---|---|---|---|
| Frontmatter | `generated_by: <slug>` (single word — no parentheticals, no "patched by"), `generated_at: <ISO-8601>`, `git_head_at_generation: <short-sha>` | writer + `git rev-parse` | both |
| `## Project` | 1 line, project name + 1-sentence purpose | static (CLAUDE.md identity line if present, else config) | ceremony |
| `## Trust caveats` | ≤5 lines of `- <one-line caveat>`; **omit section entirely if no detector fires** | filesystem detectors (NOT config). MVP: any `*.uproject` anywhere in repo → UE caveat starting `Unreal Engine project detected (<path>) — do NOT trust your training data on UE5 APIs/classes/Blueprint semantics; verify every claim via mcp__project-rag__* tools or dispatch game-dev:staff-game-dev (the Game Dev Reviewer). This applies to your delegates — restate it in every UE dispatch brief.` Additional framework detectors (Unity, RN, etc.) added as those projects materialise. | ceremony (static — content changes only when the routine ships a new detector) |
| `## Counters` | Lines of the form `- **<label>:** <integer>`; **omit lines where value is 0** | derived from disk: handoffs ready_to_fire, spinoffs ready_to_fire, gated handoffs, bug-backlog depth, local improvement queue depth | ceremony |
| `## Active workstreams` | Name-only list, one per line, max 10 entries; names only — no progress prose, no parenthetical state | `tasks/project-tracker.md` or equivalent | ceremony |
| `## Rechecks due ≤7 days` | One line per recheck marker due within 7 days; **omit section entirely if empty** | glob `tasks/*-recheck-due-*.md`, filter by date in filename | ceremony |
| `## Branch` | 1 line: `<branch> — <ahead>/<behind> vs origin/main`. No narrative. | `git rev-parse` + `git rev-list --count` | ceremony |
| `## Pinboard` | exactly 0 or 1 line of `- <ISO-date> <writer-slug>: <one-line note>`; **omit section entirely if empty**. One-slot only — second mid-session write overwrites the first, never appends. | mid-session writers append-or-overwrite; cleared by every ceremony regen | mid-session |

### Writer tiers

**Ceremony writers** (`/workday-start` Step 5.5, `/update-docs` Phase 10) own full regeneration. Every section is re-derived from source-of-truth. The pinboard is cleared. Out-of-schema sections present in the file are discarded. **This is where bloat dies.**

**Mid-session writers** (`/session-end` Step 2.8, `/handoff` Step 2.9) may ONLY mutate `## Pinboard`, and only by writing exactly one line. No other section. No body edits. Pinboard content rule: write a line only when next session boot MUST see this and it would otherwise be lost (e.g., a transient surface gotcha discovered this session; a critical blocker context for the picker-upper of a handoff). If you find yourself wanting to write more, that's a wiki edit or a handoff body — escalate to PM. The pinboard is automatically cleared at the next ceremony regen.

### Hard limits (verifier-enforced)

- File length ≤35 lines.
- `## Trust caveats`: ≤5 lines.
- `## Active workstreams`: ≤10 lines.
- `## Pinboard`: ≤1 line.
- Counter lines must match `^- \*\*[A-Za-z][A-Za-z0-9 /\-]*:\*\* [0-9]+(\.|$)` — integer terminated. Prose continuation ("— cleared by bug-blitz", "— 4 concurrent-EM additions") is a verifier failure.
- Workstream lines must match `^[0-9]+\. [A-Za-z][^\n]{0,80}$` — name only.
- Pinboard line must match `^- [0-9]{4}-[0-9]{2}-[0-9]{2} [a-z0-9-]+: [^\n]{1,120}$`.
- `generated_by` value must be a single slug — no parenthetical annotation.
- If `*.uproject` is present in the repo, `## Trust caveats` MUST be present and its first line MUST contain `Unreal Engine project detected` (detector-regression guard).

**If `tasks/` directory doesn't exist:** skip cache generation. Not all repos use `tasks/`.
