---
name: workday-start
description: Morning orientation — triage handoffs, surface staleness, align priorities
allowed-tools: ["Read", "Write", "Grep", "Glob", "Bash", "Agent"]
argument-hint: "[optional day focus]"
---

# Workday Start — Morning Orientation

Prepare the day's workstream-start calls to be maximally efficient. Ensure context is fresh, priorities are clear, and any overnight health findings are surfaced.

**Announce at start:** "I'm running workday-start to prepare the day's context."

## Step -1: Session Reaper

Run the session reaper before any other work to bound stale-session accumulation. Capture stdout to a log file; do not echo reaped-session lines into the Morning Briefing.

```bash
REAP_LOG=$(~/.claude/plugins/coordinator/bin/coordinator-reap-sessions 2>/dev/null)
if [[ -n "$REAP_LOG" ]]; then
  mkdir -p ~/.claude/logs
  printf '%s  %s\n' "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" "$REAP_LOG" >> ~/.claude/logs/coordinator-reap.log
fi
```

Non-zero exit (lib not found) → continue; the reaper is hygiene, not a gate.

## Step -0.5: EM Environment Check

Before load-bearing work, confirm the EM is on the right model and effort:

- **Effort** — you cannot observe this yourself (it shows only in the CLI startup banner, never in your system prompt). Run the safety script and relay any banner it prints in the Morning Briefing; silent output means clean (`medium` effort), so say nothing:
  ```bash
  bash ~/.claude/plugins/coordinator/bin/check-em-environment.sh
  ```
- **Model** — your system prompt names your model. If it is not Opus, WARN the PM (`⚠ MODEL DRIFT — not Opus; toggle via /model`) and recommend switching before proceeding. (The script also reads the transcript model as a backstop.)

## Step 0: Branch Setup

Ensure work happens on an active workstream branch and reconcile with `origin/main` daily. Active workstream may be canonical (`work/{machine}/{date-or-span}`) **or** a PM-authorized long-lived bus (`migration/...`, `release/...`, `feature/...`). Daily ritual is **reconcile with origin/main**, not rotation.

**Precedence switch** (evaluate in order; stop at first match): (1) stale-commit (>2 days) → A/B/C Branch Reconciliation flow; (2) already-in-span → silent exit; (3) on main/detached/empty → create `work/{machine}/{today}`; (4) named long-lived bus → skip rename, proceed to reconcile; (5) midnight-rename → atomic rename + one-line briefing notice.

Every off-daily ref operation requires `COORDINATOR_OVERRIDE_BRANCH=1 COORDINATOR_OVERRIDE_BRANCH_REASON="workday-start step 0 <action>"`.

**Run the canonical Step 0 script — do not transcribe the procedure inline:**

```bash
bash ~/.claude/plugins/coordinator/bin/workday-start-step0.sh
```

The script encapsulates sync-main, the precedence switch (Checks 1–4 + 3.5), the rename procedure (Step 0.4), and the reconcile flow (Step 0.4.5).

**Stdout shape:** one line on IN-SPAN; two lines on FRESH-CUT / NAMED-WORKSTREAM / RENAMED (precedence status + reconcile status: `ALREADY-CURRENT`, `RECONCILED-FF`, or `RECONCILED-MERGE`). Surface both in the Morning Briefing.

Exit codes: `0` success; `2` `STALE-NEEDS-ABC` → invoke A/B/C flow below; `3` `RECONCILE-CONFLICT` → PM resolves; `1` unexpected error → halt.

**Step 0 is not EM-skippable on judgment.** "Reconcile not rotate" governs whether to *abandon* the branch (no), not whether to *rename* the suffix at midnight (yes, via Check 4). Legitimate skips: only the precedence outcomes the script reports (`IN-SPAN`, `NAMED-WORKSTREAM`, `FRESH-CUT`). Any other path MUST execute the rename when Check 4 fires; Step 0.45 catches silent skips. Full rationale: `pipelines/workday-start-internals.md` § Step 0.

### Step 0.45: Post-Step-0 Span Assertion

After the precedence switch resolves, verify the active branch's name covers today. Catches EM judgment-skips, rename failures, and silent fall-throughs.

```bash
source ~/.claude/plugins/coordinator/lib/coordinator-daily-branch.sh
CURRENT=$(git branch --show-current)
TODAY=$(date +%Y-%m-%d)
SPAN_ASSERT_FAIL=
SPAN_ASSERT_MSG=

if cs_parse_branch_span "$CURRENT" > /dev/null 2>&1; then
  END_DATE=$(cs_parse_branch_span "$CURRENT" | awk '{print $2}')
  if [[ "$END_DATE" != "$TODAY" ]]; then
    SPAN_ASSERT_FAIL=1
    EXPECTED="work/$(cs_compute_machine)/$(cs_format_span_suffix "$(cs_parse_branch_span "$CURRENT" | awk '{print $1}')" "$TODAY")"
    SPAN_ASSERT_MSG="Active branch \`$CURRENT\` does not cover today ($TODAY) — end=$END_DATE, expected rename to \`$EXPECTED\`. Step 0 Check 4 did not fire. The library helpers work; the rename was skipped at the command level. Re-run \`/workday-start\` Step 0 manually or rename inline."
  fi
fi
```

- **If `$SPAN_ASSERT_FAIL` is set:** surface `$SPAN_ASSERT_MSG` as a top-line `### Branch Span Mismatch` block (above `### Context Freshness`). Do NOT auto-rename — assertion is a tripwire, not a retry.
- **If branch does not parse as `work/{machine}/...`** (named long-lived, `main`, or other authorized shape): skip silently — Check 3.5 covered it.
- **If the branch parses and end-DD == today:** skip silently.

Rationale (2026-05-18 drift): "reconcile not rotate" forbids *abandoning* the branch, not skipping the midnight rename.

### Step 0 conflict handling — Branch Reconciliation Decision

When `git merge --no-ff` hits a conflict, abort and produce a **Branch Reconciliation Decision** block naming each conflicting branch.

**Interactive (TTY):** Hard-block until PM chooses:
- **A — Consolidate now:** run `/consolidate-git`; resume after.
- **B — Defer:** write `tasks/.deferred-branches.md` entry: `{branch} | reason: {reason} | re-check: {today+7d} | deferred-by: workday-start {today}`. Surfaced next morning if re-check date passed.
- **C — Archive (abandon):** rename `archive/{machine}/{today}/{branch}` locally; push; delete old ref.

**Non-interactive (no TTY):** Auto-defer with `reason=auto-deferred, awaiting PM` and `re-check={today}`; emit note in Morning Briefing. Next interactive run forces A/B/C.

## Step 0.5: Orphan Branch Sweep

Run `orphan-branch-sweep.sh --format text --severity-min warning`. For each line returned:

- **CRITICAL** entries → surface in the Morning Briefing under a `### Orphan Sweep` section. Include the branch name, the merged PR number, and the count of post-merge commits. Recommend: _"Investigate before opening new work — these commits may be orphaned. Salvage via PR or consolidate into today's branch."_
- **WARNING** entries → surface as a heads-up in the same section. Recommend: _"Open a PR or consolidate before the branch goes stale."_
- **No output** → skip silently (do not emit "no orphans found" — noise).

Append the rendered section to the Morning Briefing template in Step 5 (after `### Alignment Check`, before `### Priority Suggestions`).

## Step 0.6: Agent Worktree Sweep

Claude Code 2.1.x auto-creates per-dispatch worktrees under `<repo>/.claude/worktrees/agent-<hash>/` that accumulate. Doctrine forbids worktrees as parallelism (→ `docs/wiki/dispatching-parallel-agents.md` § Worktree vs. Same-Worktree); any on disk is unintended residue. Run sweep in `--reap` mode:

```bash
~/.claude/plugins/coordinator/bin/agent-worktree-sweep.sh --reap --format text
```

Per-worktree disposition: `empty-clean` → removed silently. `commits-clean` → cherry-picked onto active branch (carries `COORDINATOR_OVERRIDE_BRANCH=1`), then removed (conflict aborts pick, leaves worktree intact, exit 3). `dirty-benign` (allowlist: `.claude/settings.local.json`, `.last-cleanup`) → `git worktree remove --force` — Claude Code permission auto-add residue; main worktree is authoritative. `dirty` (outside allowlist, or commits-ahead-AND-dirty) → left alone; EM triages.

**Surface `### Agent Worktrees`** only when something other than empty-clean/benign-discard happened. Format: `[N] swept ([K] clean, [B] benign, [S] salvaged, [D] dirty retained, [F] salvage-conflict)` + per-path triage notes. **Do not** emit "dirty retained" under "probably benign" — if benign by allowlist, the script removed it; outside, the EM triages. (Step 0.6 not 0.5: orphan-branch-sweep matches `work/*`/`feature/*`; agent worktrees use ephemeral `worktree-agent-*` branches invisible to that pass.)

## Step 0.7: Consumed-Marker Frontmatter Sync

Belt-and-suspenders against handoff-frontmatter drift: EMs sometimes mark work shipped with `<!-- consumed: YYYY-MM-DD -->` body markers but forget to flip `status:`/`deployment_state:` in frontmatter, leaving unflipped records in `ready_to_fire` queries.

```bash
node ~/.claude/plugins/coordinator/bin/normalize-consumed-frontmatter.js
```

Idempotent; one-line no-drift notice to stderr when nothing changes. Each change names file + field flips; recurring drift across days is a doctrine signal (consider `coordinator:learn-lessons`). Scans handoffs + plans + decisions + reviews. Strips `gate_dependency:` on flipped records; preserves terminal states (`superseded`, `abandoned`).

## Step 0.8: Stale-Executing Plan Nudge

*Lesson 2026-05-16, project-rag — session-init orphan-sweep archives handoffs without running workstream-end ceremony.* When `session-init.sh` silently archives an orphaned handoff, the driving plan in `docs/plans/` stays `status: executing` forever. This step catches that — plans whose handoff was silently archived, or where code landed without the EM flipping the plan to `implemented`.

```bash
# Advisory: list plans with status:executing untouched >3 days (git mtime).
for plan in docs/plans/*.md; do
  [[ -f "$plan" ]] || continue
  awk '/^---$/{n++; next} n==1' "$plan" 2>/dev/null | grep -qE '^status:[[:space:]]*executing' || continue
  last_commit=$(git log -1 --format=%ct -- "$plan" 2>/dev/null)
  [[ -z "$last_commit" ]] && continue
  age_days=$(( ($(date +%s) - last_commit) / 86400 ))
  [[ "$age_days" -gt 3 ]] && echo "  - $plan (status: executing, untouched ${age_days}d)"
done
```

Advisory only — never blocks. Recurring entries across runs are the doctrine signal. Triage: flip to `status:implemented`, `status:abandoned`, or pick back up.

**Also read `tasks/orphan-sweep-notes.md` if present** — `session-init.sh` appends a line per orphan-archive event. Surface alongside the stale-executing list, then rotate (preserve 4-line header):

```bash
if [[ -f tasks/orphan-sweep-notes.md ]] && [[ $(wc -l < tasks/orphan-sweep-notes.md) -gt 4 ]]; then
  echo "Orphan handoffs archived by session-init since last workday-start:"
  tail -n +5 tasks/orphan-sweep-notes.md
  head -n 4 tasks/orphan-sweep-notes.md > tasks/orphan-sweep-notes.md.new && mv tasks/orphan-sweep-notes.md.new tasks/orphan-sweep-notes.md
fi
```

Non-empty on days when concurrent sessions died mid-pickup overnight.

## Step 1: Handoff Triage

Query-driven, not grep-driven. Two `bin/query-records` calls — sub-second by construction.

### Step 1.1: Actionable-now handoffs

```bash
"$HOME/.claude/plugins/coordinator/bin/query-records.sh" --type handoff \
  --where "deployment_state=ready_to_fire AND status=active" \
  --sort "-created" --format markdown-list
```

Routing on `kind:` (spinoffs cluster separately):

- **`kind: spinoff` and `kind: spinoff-roadmap`** — both are pickup-able forks. List together in a "Spinoffs awaiting pickup" subsection. `spinoff-roadmap` rows additionally cluster by `roadmap_id:` (group all stubs from a single roadmap-planning run) — surface roadmap heading + stub count, not raw rows, when `roadmap_id` is non-empty and the count > 3.
- **`kind: session-handoff`** (or absent) and **`kind: recovery`** — list together in a "Continuation handoffs" subsection. Recovery rows get a `(recovery)` suffix so the PM can see at a glance which continuations came from a crashed/killed prior session.

### Step 1.2: Gated handoffs (always surface count; flag stale subset)

Two queries — first lists everything `awaiting_gate`, second flags the stale subset:

```bash
"$HOME/.claude/plugins/coordinator/bin/query-records.sh" --type handoff \
  --where "deployment_state=awaiting_gate AND status=active" \
  --sort "-created" --format markdown-list

"$HOME/.claude/plugins/coordinator/bin/query-records.sh" --type handoff \
  --where "deployment_state=awaiting_gate AND status=active" \
  --older-than 6d --format markdown-list
```

- **If any `awaiting_gate` exist:** surface the full list as a "Gated handoffs" subsection (titles + gate_dependency, not bodies). Morning briefing is the right surface for cross-workstream gate awareness — silently filtering them buries actionable triage decisions (clear gate, retarget, pick up early).
- **If any are >6 days old (≈ one working week):** additionally flag _"{M} handoffs awaiting_gate >6 days — gate may be stuck; consider triage, PM clear-gate, or close out."_
- **If none exist:** skip silently.

### Step 1.3: Reconcile pending items against git (MANDATORY before declaring any item actionable)

Per-handoff in `ready_to_fire`: (a) `git log --oneline --since="<handoff-date>" --all` and scan subjects for matching items; (b) Read referenced plan/stub `**Status:**` fields; (c) drop confirmed-closed items, note as "verified-closed since handoff". Empirical baseline: 30–60% of inherited items are already closed. **Full procedure:** `pipelines/workday-start-internals.md` § Step 1.

### Step 1.4: Cross-reference against completed archive (sanity check)

Query the completed archive for recent entries:
```bash
"$HOME/.claude/plugins/coordinator/bin/query-completions.sh" --where "created>=$(date -d '30 days ago' +%Y-%m-%d)" --sort "created" --format json
```

**Legacy fallback:** if `query-completions` returns empty AND `archive/completed/legacy/YYYY-MM.md` exists, read the legacy monolith for this reconciliation check only (read-only; no writes to the legacy path).

For each `ready_to_fire` handoff, check whether the work it describes appears as completed in the query results — match on workstream names, feature names, commit hashes, or distinctive keywords. If a match is found, flag it: _"Handoff [file] describes [work] — archive/completed shows this shipped on [date] (commit: [hash]). Likely already done — pick up to confirm and archive, or close out?"_

### Step 1.5: Report

_"{N} actionable handoffs ({K} continuations, {S} spinoffs incl. {R} roadmap stubs in {G} groups). {G} awaiting_gate (of which {M} >6 days) [if any]. {X} items verified-closed by git reconciliation."_ Omit any clause whose count is zero.

### Step 1.48: Refresh DoE handoff-tracker aggregate

`state/doe-handoff-tracker.md` is the cross-repo DoE roll-up of every reachable sibling repo's handoffs/spinoffs/memos. Unlike the per-repo `state/handoff-tracker.md` (refreshed by `/workstream-complete` and `/handoff` inside each repo), no per-repo ceremony reaches across the DoE — so without a daily render hook the aggregate goes stale silently. Run it here unconditionally; the script is a pure render (idempotent, ~100ms) and silently skips repos not present on this machine:

```bash
node ~/.claude/plugins/coordinator/bin/render-handoff-tracker.js --all-repos 2>&1 | tail -3
```

No surfacing required — the file's freshness is the signal. Errors (machine-local CLI missing, no roots configured) → one-line note in the Morning Briefing under `### Handoffs` ("DoE tracker refresh skipped: <reason>"); do not block.

## Step 1.45: Outstanding Cross-Repo Memos

Run `bash ~/.claude/plugins/coordinator/bin/workday-start-cross-repo-memo-surface.sh`. Non-empty → surface verbatim under `#### Outstanding cross-repo memos (DoE attention):`. Empty → skip. Details: `pipelines/workday-start-internals.md § Step 1.45`.

Run `bash ~/.claude/plugins/coordinator/bin/workday-start-cross-repo-memo-outbox-surface.sh`. Non-empty → surface verbatim under `#### Outbox drafts awaiting send (DoE attention):`. Empty → skip. Details: `pipelines/workday-start-internals.md § Step 1.46`.

## Step 1.55: Recent Roadmap Orientation

Surface last quarter's top-10 roadmap completions by size — grounding the day in recent delivery context. Per `docs/wiki/orientation-surfacing-doctrine.md` count-always pattern: heading renders regardless of row count.

```bash
"$HOME/.claude/plugins/coordinator/bin/query-records.sh" --type completion --since "90d" --where "nature=roadmap" \
  --sort "-loe.tshirt" --limit 10 --format markdown-list
```

Render under `#### Recent roadmap (last 90d, top-10 by size)` inside `### Handoffs` (Step 5). One bullet per row; `(none)` when zero rows (expected on new/un-migrated repos). `query-completions.sh` with equivalent flags is also accepted.

## Step 1.6: Coordinator-Improvement Queue Check

Read `~/.claude/state/coordinator-improvement-queue.md` (if it exists). Count `- ` lines in `## Active queue`; note the oldest date and any entries carrying `[recurring: ≥3]` on the main line (DR-056 amended 2026-05-17 — main-line-only schema).

Also read `state/improvement-queue.md` (if present in current repo). Count its `## Active queue` entries.

Surface in the Morning Briefing when notable: central ≥ 5 entries, oldest >14 days, any `[recurring: ≥3]`, or local ≥ 1. EM advocates based on depth — judgment, not a threshold trigger. Skip silently when both queues are empty or absent.

## Step 1.65: Bug Backlog Depth Check

Read `state/bug-backlog.md` (if it exists). Count P1+P2 data rows (stop before `## Resolved`; exclude headers and separators). Surface in the Morning Briefing when ≥ 10: moderate (10–19) → `/bug-blitz` suggestion; heavy (≥ 20) → stronger nudge. Skip silently if absent or <10.

## Step 1.7: Scheduled Rechecks

Glob `tasks/cookbook-recheck-due-*.md`, `state/inspiration-recheck-due-*.md`, `state/lesson-triage-recheck-due-*.md`, and `tasks/recheck-due-*.md`. Each filename ends in `-YYYY-MM-DD.md`. For each:
- **today ≥ due date** → surface in Priority Suggestions: _"Scheduled recheck due: `<filename>` (due {YYYY-MM-DD}). Procedure inside the file."_
- **due within 7 days** → heads-up: _"Scheduled recheck upcoming: `<filename>` (due {YYYY-MM-DD}, in {N} days)."_
- **Otherwise** → skip silently.

No marker files → skip silently. Do not auto-execute — PM-actioned, not auto-dispatched.

## Step 1.75: Central Learn-Lessons Volume Trigger

Run `central-run-due.sh` (relative to the coordinator plugin root). It counts `[universal]`
entries accrued across the configured roots since the last **COMPLETE** central run and compares to
`central_volume_threshold` (config, default 150). This is the *volume* companion to the date-based
recheck marker (Step 1.7): a fixed cadence under-runs in busy weeks, when the sibling `lessons.md`
boot-surface floor balloons fastest.

- **Prints a `CENTRAL_RUN_DUE` line** (over threshold): surface in Priority Suggestions —
  _"Central learn-lessons due (volume): {N} universals accrued since {date}. Consider `/learn-lessons` central."_
  with the per-repo breakdown.
- **Stderr-only / nothing on stdout** (below threshold, or no COMPLETE sentinel yet — informational stderr on first run): nothing for Priority Suggestions; skip silently.

Read-only and PM-actioned — never auto-dispatch a central run. On a machine without the sibling roots,
unreachable roots are skipped silently (the date-based marker in Step 1.7 still covers the cadence floor).

## Step 1.8: Project-RAG Preamble Drift Check

Run `verify-preamble-sync.sh` (relative to the coordinator plugin root, typically `~/.claude/plugins/coordinator/bin/verify-preamble-sync.sh`).

- **No consumers found** (exit 0): skip silently.
- **All consumers OK** (exit 0, all `OK`): skip silently.
- **Any MISMATCH or MISSING_END** (exit non-zero): surface under **Preamble Drift**: _"project-rag-preamble drift in [N] consumer(s): [list files]. Run `verify-preamble-sync.sh --fix` to repair, then commit all touched files together."_

**Do NOT auto-fix** — investigate which consumer drifted and why; a drift may need to be merged back into the canonical snippet rather than overwritten.

## Step 1.9: Auto-Push Failure Surface

Silent `coordinator-auto-push` failures (Windows case-mismatched branch refs, expired credentials, SSH agent unreachable) accumulate in `.git/push-failures.log` until the next manual push — surfaced here each morning.

```bash
LOG=".git/push-failures.log"
if [[ -s "$LOG" ]]; then
  TOTAL=$(wc -l < "$LOG" | tr -d ' ')
  RECENT_24H=$(awk -v cutoff="$(date -d '24 hours ago' -Iseconds 2>/dev/null || date -v-1d -Iseconds 2>/dev/null)" \
    '$0 >= "[" cutoff' "$LOG" | wc -l | tr -d ' ')
  LAST_LINE=$(tail -1 "$LOG")
fi
```

**Surface `### Auto-Push Health`** when `RECENT_24H ≥ 1` OR `TOTAL ≥ 5`:
```
### Auto-Push Health
- [N] failures in last 24h (total log: [M] lines). Most recent: [LAST_LINE].
- Investigate before opening new work — push failures keep firing on every commit until the credential/branch-case/agent issue is resolved.
- Cleanup after fix: `> .git/push-failures.log` (truncate; do not delete — helper appends in-place).
```
**If `RECENT_24H == 0` AND `TOTAL < 5`:** skip silently.

## Step 1.91: Local-Only Work-Branch Surface

Complement to Step 1.9. Step 1.9 surfaces failures that the auto-push hook *captured* into `.git/push-failures.log`; this step catches the silent failure mode where the hook never ran at all (uninstalled, non-executable, routed elsewhere) — in which case `.git/push-failures.log` would never be created and Step 1.9 would report all-green even though commits are stranding on local disk.

Spec backlink: `state/handoffs/2026-06-11_145955_auto-push-silent-failure-email-privacy.md`. The 2026-06-11 instance stranded ~15 commits across multiple sessions for an entire day before being noticed at `/workstream-complete`.

```bash
CUR_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
LOCAL_ONLY_AHEAD=0
LOCAL_ONLY_NOORIGIN=0
if [[ "$CUR_BRANCH" == work/* || "$CUR_BRANCH" == feature/* ]]; then
  git fetch --quiet origin "$CUR_BRANCH" 2>/dev/null
  if git rev-parse --verify --quiet "refs/remotes/origin/$CUR_BRANCH" >/dev/null 2>&1; then
    LOCAL_ONLY_AHEAD=$(git rev-list --count "origin/$CUR_BRANCH..HEAD" 2>/dev/null || echo 0)
  else
    # Branch doesn't exist on origin at all — every commit is local-only.
    LOCAL_ONLY_NOORIGIN=$(git rev-list --count HEAD 2>/dev/null || echo 0)
  fi
fi
```

**Surface `### Local-Only Branch Warning`** when `LOCAL_ONLY_AHEAD ≥ 1` OR `LOCAL_ONLY_NOORIGIN ≥ 1`:
```
### Local-Only Branch Warning
- Branch `<CUR_BRANCH>` has [N] commits not on origin (or does not exist on origin at all).
- Auto-push has either not fired or has been failing silently; `.git/push-failures.log` is [present|absent].
- Verify `.git/hooks/post-commit` is present-AND-executable-AND-routed-to-coordinator-auto-push (session-init self-heals this on next boot, but the day's accumulated commits stay stranded until pushed).
- Recover with `git push origin <CUR_BRANCH>`; if the remote rejects on email-privacy (GH007), set `git config user.email '<id>+<user>@users.noreply.github.com'` and make any benign commit before retrying.
```
**Otherwise:** skip silently.

## Step 1.10: Addon Health Sentinels

**First**, heal canonical-structure drift at `~/.claude` before the doctor fires. The scaffold is idempotent and additive-only (`mkdir -p` + `.gitkeep`; never overwrites READMEs or existing content). Running it here turns manifest-extension drift into a self-healing event instead of a recurring P-12 AMBER nag across every repo's daily health snapshot:

```bash
bash ~/.claude/plugins/coordinator/bin/scaffold-canonical-structure.sh --root "$HOME/.claude"
```

Silent on no-op (already-scaffolded). Brief on creation (new dirs introduced by manifest evolution). Always safe to re-run. P-12 stays as the detector for *actual* brokenness (scaffold script error, manifest unreadable) — not for "manifest grew and your install hasn't caught up." See `docs/wiki/install-surface-completeness.md`.

**Then**, refresh the coordinator-claude sentinel:

```bash
bash ~/.claude/plugins/coordinator/bin/coordinator-doctor-sentinel.sh --full
```

Fires all probes (`docs/wiki/coordinator-doctor.md`) and writes `~/.claude/plugins/coordinator-claude/data/doctor-last-run.json`. Silent on GREEN, brief on AMBER/RED. Always exits 0 — advisory only. (`--full` is required: bare invocation now defaults to `--triage` which does not write the sentinel.)

Plugins that ship a doctor skill write a sentinel at `~/.claude/plugins/<plugin>/data/doctor-last-run.json`. Run `scan-addon-health.sh --red-and-stale`; on non-empty output, render under `### Addon Health` (between `### Auto-Push Health` and `### Priority Suggestions`); on empty, omit. Schema + EM dispatch flow: `docs/wiki/addon-health-sentinel.md`. The scan now also includes a SessionStart hook-script existence pass (2026-05-27): missing hook scripts referenced in `hooks/hooks.json` surface as `[health]` lines here. Authoring guide: `docs/wiki/plugin-session-start-hooks.md`.

Additionally, run `check-plugin-drift.sh` to probe git-state and venv-state drift for registered plugin live installs. On non-empty output (exit 1), append into the same `### Addon Health` section:
<!-- [ok-via-git-propagation] lines exit 0 and are intentionally silent here — the state is benign (live content matches source; sentinel will advance on next install). Operators who want to inspect sentinel state run the probe directly. See docs/plans/2026-05-28-forward-drift-probe-content-equivalence.md § Chunk 3. -->
```
Plugin propagation: <summary e.g. "project-rag 22 commits behind, venv ok" or "all clean">
```
No `plugin.mirrors` entries → omit silently. `source_is_live` entries (e.g. coordinator) surface as "n/a-by-design" and are not counted as drift.

Spec backlink: `docs/plans/2026-05-21-plugin-source-live-mirror-doctrine.md § Chunk 1`

## Step 1.10.4: Onboarding Currency Offer (cwd repo)

Run the onboarding currency detector against the cwd repo:

```bash
bash ~/.claude/plugins/coordinator/lib/detect-onboarding-offer.sh
```

- **Non-empty output** → append the line verbatim into the `### Addon Health` section (alongside other health findings). The line is offer-shaped — surface it as a PM-facing suggestion, not a warning.
- **Empty output** → silent (repo is current, not a git repo, distribution repo, or already dismissed).

The detector respects the dismissal sentinel (`<repo>/.git/coordinator-onboarding-dismissed`) — once dismissed it never fires again for that repo. The offer text tells the PM how to dismiss.

Spec backlink: `docs/plans/2026-05-29-it-just-works-agentic-install-currency.md § Chunk 3`

## Step 1.10.5: MCP Tool Registration

For each entry in `~/.claude.json mcpServers` (top-level AND `projects.<active-cwd>.mcpServers`), confirm tools registered in this session by scanning the deferred-tools registry in `<system-reminder>` for `mcp__<server-name>__`.

1. Read `~/.claude.json` (top-level + per-project `mcpServers`).
2. Per configured server: skip if `enabled: false` or if the per-project block key ≠ active cwd. Otherwise count `mcp__<server-name>__` matches in session context.
3. **0 matches** → emit under `### MCP Tool Registration`: `- <server>: 0 tools registered. Configured at <transport>:<url-or-stdio-cmd>. Investigate with /<server>:doctor.`
4. **>0 matches** → silent.

**Sentinel:** atomically write `~/.claude/plugins/coordinator-claude/data/mcp-registration-last-check.json` (`.tmp` + `mv`) with: `ran_at`, `verdict` (`RED`/`GREEN`), `checked_servers[]` (`name`, `tool_count`, `transport`, `configured_at`), `red_servers[]`. Feeds `scan-addon-health.sh`.

**Render:** when section has content, place between `### Addon Health` and `### Priority Suggestions`; otherwise omit heading. Auto-remediation is out of scope — surfacing only.

## Step 1.10.6: Cross-Repo Paired-Fixture Sync (conditional)

Repos with paired cross-repo writers ship a `bin/check-fixture-sync.sh` that byte-compares declared fixtures against sibling-repo copies (see `docs/wiki/cross-repo-contract-test-discipline.md` § "Paired Cross-Repo Writers"). Catches the two fixture copies silently diverging when one repo updates and the partner's is left stale.

```bash
[ -x bin/check-fixture-sync.sh ] && bin/check-fixture-sync.sh 2>&1
```

(`2>&1` required: drift → stdout, config errors → stderr.)

- **Exit 0, no output** → in sync or sibling not on machine → skip silently.
- **Exit 1 (drift)** → surface `FIXTURE DRIFT:` lines verbatim under `### Cross-Repo Fixture Sync`. Re-pin both copies byte-identical via `cross-repo-memo` (never a direct sibling edit).
- **Exit 2 (config error)** → surface stderr verbatim; `tests/fixtures/cross-repo-sync.manifest` has a missing local fixture path.

Advisory only — never blocks.

## Step 1.10.7: Exec-Bit Drift Probe (meta-repo only)

Daily detect-only probe for shebanged files in the meta-repo whose git index mode is `100644` instead of `100755`. The pre-commit hook (`coordinator-precommit-exec-bit-check`) auto-fixes drift at commit time, so steady-state findings here mean files that drifted out-of-band: `--no-verify` commits, external pushes, or hook-bypass paths.

```bash
# `realpath` is GNU-only and absent on stock macOS — use the same canon idiom
# as coordinator-precommit-exec-bit-check (cd && pwd -P).
_canon(){ (cd "$1" 2>/dev/null && pwd -P) || echo "$1"; }
[ "$(_canon "$PWD")" = "$(_canon "$HOME/.claude")" ] && \
  bash ~/.claude/plugins/coordinator/bin/check-all-shebanged-exec-bits.sh 2>&1
```

- **Exit 0, no output** → in sync → skip silently.
- **Exit 1 (drift)** → surface stderr verbatim under `### Exec-Bit Drift` (between `### Addon Health` and `### Priority Suggestions`). Fix path printed by the probe.
- **Exit 2 (probe infra)** → silent (node/test missing — not a daily-noise condition).
- **Outside meta-repo** → probe skipped silently (no consumer-repo drift to guard against).

Spec backlink: `state/handoffs/2026-06-15_114014_exec-bit-drift-recurring-on-windows-git-bash.md`.

## Step 1.11: Cruft Sweep Advisory

Surface filesystem-cruft reclaim opportunities when they cross threshold. Layer 1 floor only — Layer 2 (`/cruft-sweep`) is PM-actioned.

```bash
bash ~/.claude/plugins/coordinator/bin/cruft-sweep.sh --class all --dry-run --quiet
```

Surface one-line `Cruft sweep candidates: <N reclaimable>, last sweep <YYYY-MM-DD>` in the Morning Briefing when EITHER:
- Reclaimable size > 1 GB (read from the dry-run grand-total banner on stderr), OR
- Staleness > 14d (read the most recent row timestamp from `~/.claude/state/cruft-sweep-log.md` using `tail -1 ~/.claude/state/cruft-sweep-log.md | awk -F'|' '{gsub(/ /, "", $2); print $2}'`; if the file does not exist, treat as stale). <!-- Review: Slice C reviewer F5 — use row-parse not file mtime; log is pipe-delimited, field 2 is the timestamp -->

PM-actioned only — DO NOT auto-invoke `/cruft-sweep` or `cruft-sweep.sh --apply` from this advisory. The apply pass runs automatically in `/workday-complete` Step 1.5; an out-of-session scheduler (cron / Windows Task Scheduler) is optional additional layering for days when Claude Code is not opened, per `docs/wiki/cruft-sweep-cadence.md` § Cadence.

Silent when below both thresholds.

## Step 2: Doc Freshness

1. Find last update-docs run: `git log --oneline --grep="update-docs\|workday-complete" --since="7 days ago" -1`
2. Find commits since: `git log --oneline <last-update-docs-commit>..HEAD`
3. **Commits exist:** Flag: _"Docs are stale — [N] commits since last update-docs. Recommend `/update-docs` before feature work."_ Do NOT dispatch automatically — it commits files and would race with the working tree.
4. **No commits since:** "Docs are current."

## Step 3: Test Staleness

1. Detect test framework (same as bug-sweep Phase 0).
2. If tests exist: find most recent test-related commit/CI run; find code changes since. **If code changed:** Flag: _"Tests haven't been run since [N] commits ago. Recommend running test suite."_ Don't run automatically — PM decides.
3. No tests → skip silently.

## Step 3.5: Bug Sweep Staleness

Check if a bug sweep should be suggested — based on **code churn since last sweep**, not just calendar time:

1. Read `state/bug-backlog.md` header for `Last sweep:` date and `Commit at sweep:` hash. Header format (written by `/bug-sweep`): `> Last sweep: YYYY-MM-DD | Commit at sweep: [short hash] | Open: N items (P0: X, P1: Y, P2: Z)`
2. If no backlog exists: count source files (`find . \( -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.cpp" -o -name "*.h" -o -name "*.cs" -o -name "*.go" -o -name "*.rs" \) | grep -v node_modules | grep -v __pycache__ | wc -l`). If >50: _"No bug sweep has ever run ([N] source files). Recommend running bug-sweep."_ If <50, skip silently.
3. If backlog exists: count commits since anchor (`git rev-list --count <sweep-commit>..HEAD`).
4. **Suggest sweep if:** >50 commits AND >7 days since last sweep (churn + time floor prevents sprint-mode nagging), OR >14 days AND >20 commits (moderate churn + time). Message: _"Bug sweep last ran [date] ([N] commits ago). Recommend running bug-sweep before new feature work."_
5. Otherwise: "Bug sweep is current ([N] commits since last sweep)."

## Step 3.6: Project-RAG Staleness (conditional)

**Skip silently** if `ToolSearch` finds no `mcp__project-rag__*` tool — same gate pattern as `workstream-start.md`. Coordinator does not depend on project-rag; it only adapts when present.

When present:

1. Invoke the staleness survey directly via `project-rag-cli`. Coordinator does NOT parse `~/.claude.json` to extract project-rag's internal state — the CLI resolves its own project root via env (`PROJECT_RAG_PROJECT_ROOT` / legacy `HOLODECK_PROJECT_ROOT`) or cwd-walk. Set the env var to the active project root and invoke:

   ```bash
   PROJECT_RAG_PROJECT_ROOT="$(pwd)" project-rag-cli staleness-survey --json
   ```

   If `project-rag-cli` is not on PATH, fall back to:

   ```bash
   PROJECT_RAG_PROJECT_ROOT="$(pwd)" python -m project_rag.cli staleness-survey --json
   ```

2. Parse the JSON. If `verdict == "current"`, emit nothing. Otherwise inline the rendered output into the Morning Briefing under a new **Project-RAG** line (template below).

**Doctrine — no parsing peer-plugin config from coordinator.** Contract: `invoke + read exit code + read stdout`. Reaching into `~/.claude.json` is cross-plugin leakage that breaks on transport migration. See `docs/wiki/plugin-extraction-and-distribution.md` § Cross-plugin contract.

**Flag-only — never auto-run.** A reindex can race with an open editor. PM invokes manually after `/workday-start` completes.

## Step 4: Priority Alignment

```bash
bash ~/.claude/plugins/coordinator/bin/whats-next.sh
```

Emits: improvement-queue head (top 5), `docs/project-tracker.md` Ready/Executing rows, open handoffs. Use as-is for § Priority Suggestions; do not reconstruct from prose.

**Reconcile active work against completed archive:** `"$HOME/.claude/plugins/coordinator/bin/query-completions.sh" --where "created>=$(date -d '30 days ago' +%Y-%m-%d)" --sort "created" --format json` (fallback: `archive/completed/legacy/YYYY-MM.md` if query empty). Cross-reference tracker Ready/Executing items and open handoffs:
- **Match found** → Flag: _"Tracker shows [workstream] as [status], but archive/completed records it shipped on [date]."_
- Fuzzy match on names/descriptions — when unsure, flag as "possible match — verify" rather than auto-resolving.
- Report mismatches under **Alignment Check** in the Morning Briefing.

## Step 5: Morning Briefing

Present a concise morning report:

```markdown
## Good Morning — Workday Start

**Date:** YYYY-MM-DD
**Branch:** [current branch]

### Branch Span Mismatch
_(Omit this section entirely unless Step 0.45's `$SPAN_ASSERT_FAIL` was set. When present, render `$SPAN_ASSERT_MSG` verbatim — this is the loudest tripwire in the briefing and PM should see it first.)_

### Context Freshness
- Handoffs: [N] actionable for today, [M] stale (flagged for /update-docs archival)
- Docs: [current / stale — N commits since last update-docs]
- Tests: [current / N commits since last run — suggest running]
- Health: last daily check [today/N days ago], last weekly audit [N days ago]
- Atlas: [N systems mapped, M stale >90 days / no atlas]
- Bug backlog: [N open (P0: X, P1: Y) / empty / no backlog]
- Bug sweep: [current (N commits since) / suggest sweep (N commits since last)]
- Project-RAG: [{verdict} — {age}, {code_commits} commits / {asset_changes} assets / verdict source: {recommendation_command}] _(omit this line if verdict is `current`)_
- Tools: [missing optional tools, if any — see below]

### Tool Availability
Check PATH for `scc` (also `~/bin/scc`) and `shellcheck`. Surface install hint for each missing tool (`winget install BenBoyter.scc` / `winget install koalaman.shellcheck`). When both present: _"Tools: scc + shellcheck available."_ Only nag when missing.

**Fan-out tooling:** `fan-out-dispatch.sh` (compiler — overlap pass + scoped prompts); follow the fan-out methodology (`docs/wiki/dispatching-parallel-agents.md` § Executing a Fan-Out Wave) to dispatch the compiled wave and hold the EM-serial commit (not a skill — no `/fan-out` command). Use for any multi-chunk parallel or serial dispatch instead of hand-authoring executor prompts.

### Handoffs
- **Continuation:** [N active, M aging, K likely-consumed]
- **Spinoffs awaiting pickup:** [list each: filename — title — age — workstream]
  _(Omit this bullet if no spinoffs exist.)_
- **Stale spinoffs (≥14 days):** [list each with a one-line nudge]
  _(Omit this bullet if no stale spinoffs exist.)_
- **Tracker:** durable snapshot at `state/handoff-tracker.md` (refreshed by `/workstream-complete` and `/handoff`; ad-hoc: `node ~/.claude/plugins/coordinator/bin/render-handoff-tracker.js`). **DoE aggregate `state/doe-handoff-tracker.md` is refreshed daily by `/workday-start` Step 1.48** (`--all-repos`); ad-hoc: same command with `--all-repos`.

#### Recent roadmap (last 90d, top-10 by size)
_(Results from Step 1.55 query — one bullet per row. Render "(none)" when the query returns zero rows. Heading always present — count-always per orientation-surfacing-doctrine.)_

### Alignment Check
- [N mismatches found between active trackers and completed archive / all aligned]
- [List each mismatch: "Tracker: X is Executing — Archive: shipped YYYY-MM-DD"]
- [List each handoff flagged as likely completed]

### Orphan Sweep / Agent Worktrees / Auto-Push Health / Addon Health
Each section omitted unless its step (0.5 / 0.6 / 1.9 / 1.10) produced surfaceable findings; render only the non-empty rows from that step's structured output.

### Priority Suggestions
Pull from the active state: bugs (top severity first), stale sweep, stale tests, stale atlas, tracker Ready rows, deep debt backlog. Order by urgency, not by template.

### What should today's focus be?
[Surface tracker Ready items, handoff action items, and PM-facing options]
```

**Set marker:** Write `state/.workday-start-marker` with today's date (single line). Workstream-start checks this one file.

## Step 5.5: Write Orientation Cache

Generate `state/orientation_cache.md` — a compact 40-60 line summary the SessionStart hook injects instead of raw repomap/DIRECTORY content. Skip if `tasks/` doesn't exist. Health Snapshot includes a Step-1 mirrored split: one line for continuation handoffs, a separate line for spinoffs (omitted if N=0).

**Full content derivation per section:** see `pipelines/workday-start-internals.md` § Step 5.5.

## What This Does NOT Do

Run bug-sweep / daily-code-health / deep-architecture-survey / update-docs (dedicated invocations). Merge to main (use `/merge-to-main`). Choose work (`/workstream-start`'s Engage section).

## Relationship & Concurrent Safety

`workday-start` runs once/day; `/workstream-start` runs per-session and skips redundant checks when the marker is fresh. `/workday-complete` is the evening counterpart. `/update-docs` and `/bug-sweep` are recommended (not dispatched) when state warrants. Read-only for all tracking files; writes only `state/.workday-start-marker`. Failure mode to avoid: acting on stale handoff items a concurrent session shipped — Step 1.3's git reconciliation is the prevention.

If `$ARGUMENTS` is provided, include as a focus hint: _"Requested focus: {arguments}"_
