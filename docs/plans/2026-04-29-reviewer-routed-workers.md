# Plan — Reviewer-Routed Workers (no new personas)

**Date:** 2026-04-29
**Branch:** work/striker/2026-04-29
**Status:** DRAFT — awaiting PM approval before Phase 1
**Plan author:** EM (Claude)
**Predecessor:** holodeck-side draft [`X:/claude-unreal-holodeck/docs/plans/2026-04-29-personas-workers-expansion.md`](file:///X:/claude-unreal-holodeck/docs/plans/2026-04-29-personas-workers-expansion.md) — this plan supersedes it for coord-claude; the holodeck team can layer UE-specific workers on top after this lands.

## 1. Context

The holodeck-side draft proposed three new Opus personas (Sam / Kira / Lee), 10–12 workers, a `/review-dispatch` classifier rewrite, and multi-human shared-state infrastructure — ~15–18 new dispatchable surfaces, a 30–40% roster expansion. Reviewing it from the coordinator angle (generic SE, not game-dev) and against our prior judgment that CCGS-scale rosters are performative overkill, the plan is too large.

The principle this plan rests on:

- **Personas are for distinct judgment styles that are hard to invoke as prompt addenda.** Threat-modeling, test-pyramid reasoning, release coordination — Opus-level judgment can absorb these as lenses, surfaced by the EM when the workers below produce evidence. Most of our infra exists to *help the EM make better decisions*, not to substitute additional decision-makers.
- **Workers are for mechanical leverage with structured output.** Tight tool surface, no opinions. The `ue-blueprint-worker` shape we already use.
- **Named reviewers (Patrik / Sid / Camelia / Palí / Fru) become the routing intelligence for workers.** The EM stays the dispatcher — we don't change the no-direct-spawn rule — but reviewers, who are already reading the artifact, name the workers the EM should dispatch next. Same shape as today's Patrik→Palí escalation; we generalize the targets to include workers, not only sibling personas.
- **Release mechanics belong to the EM, gated by `/merge-to-main`.** Same as a real eng team where the dev cutting the release writes the notes. No coordinator persona needed.

Net effect: zero new personas, four new Sonnet workers, one new reviewer-prompt section, and one extension to `/merge-to-main`. My routing surface is unchanged.

## 2. What ships

### 2.1 Four Sonnet workers (coord-claude, always shipped)

All live in `~/.claude/plugins/coordinator-claude/coordinator/agents/`. Sonnet model. Tight tool surfaces, structured output, no architectural opinions.

| Worker | Requested by | Job | Tool surface |
|---|---|---|---|
| `test-evidence-parser` | Patrik / Sid (named in their findings) | Run a test command, parse output, classify failures (real / flake / env / timeout / known-skip), return structured table | Bash, Read |
| `security-audit-worker` | Patrik | Scan diff for path traversal, validation-vs-rewrite traps, command injection, secret leakage, env-var ingestion. Structured findings table with severity + line refs. | Read, Grep, Glob, Bash (restricted to read-only invocations of security scanners: semgrep, bandit, gitleaks, trufflehog, and equivalents) |
| `dep-cve-auditor` | Patrik / EM (periodic + on-demand) | Run `npm audit` / `pip-audit` / equivalent for languages present in repo, normalize CVE output, classify severity vs. our actual usage | Bash, Read |
| `doc-link-checker` | EM (opportunistic; called from `/update-docs`) | Crawl `docs/`, validate internal markdown links + external URLs. Sleep 1s between external HEAD checks; cap at 100 external URLs per dispatch (split into multiple dispatches if more). Return broken set. | Bash, Read, WebFetch |

Each worker spec includes:
- Structured-output contract (JSON or table-shaped markdown with explicit columns)
- Disk-write requirement matching CLAUDE.md "Scouts That Produce File Output" — DONE-after-write
- **Per-worker failure-mode enumeration:** each spec must list ≥3 specific failure modes the worker will encounter (e.g. for `test-evidence-parser`: flaky output that varies between runs, missing test framework, test command exits non-zero with no parseable output) and the structured-output shape returned in each case (not a generic exception). Generic "handle errors" is insufficient.
- 3–4 dispatch examples in the agent frontmatter

### 2.2 Reviewer protocol — "name the worker"

Patrik, Sid, and Camelia get a new section in their system prompts (Palí and Fru can grow it later if/when relevant workers exist for their domains):

> **Worker Dispatch Recommendations**
>
> If during review you identify a surface beyond your direct lens that warrants mechanical analysis — test evidence, security audit, dep CVE posture, link integrity — end your findings with a `## Worker Dispatch Recommendations` block naming the worker(s) the EM should dispatch and the specific scope. Do not attempt to dispatch directly. Surface to the EM with a one-line rationale per recommendation.
>
> Available workers: `test-evidence-parser`, `security-audit-worker`, `dep-cve-auditor`, `doc-link-checker`. Recommend a worker only when its mechanical analysis would add evidence your direct findings don't already cover. Do not recommend redundantly.

The review-integrator brief grows a matching paragraph:

> If the reviewer's findings include a `## Worker Dispatch Recommendations` block, preserve it verbatim in your integration report. Do not act on it — surface to the EM after applying the reviewer's primary findings.

### 2.3 `/merge-to-main` release-readiness gate

The command grows a checklist phase before the actual merge:

1. **User-visible changes summarized?** EM drafts; if the diff is large enough to warrant it (>50 commits or >2k lines changed), dispatch `changelog-drafter` worker (added in Phase 2 — see below). Otherwise EM writes inline.
2. **Schema / version bumps flagged?** EM scans for version sidecars, manifest bumps, `package.json` / `pyproject.toml` version changes.
3. **Install / setup scripts touched?** If yes, run them in a sandbox before merge. Phase 2 adds `install-script-sandbox` worker; until then, EM runs manually or flags as gap.
4. **CHANGELOG / release-notes section updated where applicable?** EM checks; warns if missing for repos that have one.
5. **Patrik review of the release artifact?** Required if ANY of: (a) public API additions detected (e.g. by api-surface-diff if/when added, otherwise EM grep), (b) version sidecar / manifest version bumped, (c) install or setup script touched in the diff, (d) >50 commits since last release tag, (e) CHANGELOG entries marked breaking. Otherwise EM judgment.

Phase 1 ships the checklist with EM-manual handling for steps 1 and 3. Phase 2 adds the optional workers when the next release exercises the command.

## 3. What this plan explicitly does not ship

- **No `Sam` / `Kira` / `Lee` personas.** Threat-modeling discipline and test-pyramid judgment are absorbed by the EM and Patrik when worker output surfaces evidence to consider. Release coordination belongs to `/merge-to-main`.
- **No `/review-dispatch` classifier rewrite.** Current EM-picks-reviewer flow is fine. Reviewer-routed workers add specialist coverage *downstream* of reviewer judgment, not upstream of it.
- **No multi-human `team-state.json` infrastructure.** Speculative for users we don't have. The scoped-safety-commits work plus `coordinator-safe-commit` already cover the only multi-EM problem we've actually hit. Revisit when a real multi-human consumer surfaces.
- **No multi-human workers** (`branch-state-auditor`, `code-owner-mapper`, `pr-conformance-checker`, `release-train-sequencer`). Same reason.
- **No `api-surface-diff` worker.** When we need a public-API surface diff, we can grep-and-LSP it in-session. Build when used three times by hand in a quarter.
- **No skills (`ac-extractor`, `scope-creep-auditor`, `convergence-tagger`).** The first two are absorbed by reviewers naming the appropriate worker. Convergence-tagging is already an EM-judgment doctrine in CLAUDE.md ("Convergence as Confidence") — adding a skill doesn't strengthen it.

If any of these gaps prove costly in practice, we add the specific missing piece — not the whole roster.

## 4. Phasing

### Phase 1 — Four workers + reviewer protocol (1 session)

**Scope:**
- Write four worker specs in `~/.claude/plugins/coordinator-claude/coordinator/agents/`:
  - `test-evidence-parser.md`
  - `security-audit-worker.md`
  - `dep-cve-auditor.md`
  - `doc-link-checker.md`
- Update Patrik, Sid, Camelia system prompts with the `## Worker Dispatch Recommendations` section
- Update `review-integrator` agent brief with the matching preserve-and-surface paragraph
- Brief addition: enumerate the four workers in `coordinator/CLAUDE.md` under a small new section ("Reviewer-Routed Workers") so the convention is greppable from the surfaces agents touch (per CLAUDE.md "Adding a Convention to the Coordinator System")

**Validation:**
- Replay a recent security-touched commit (e.g. one of the path-security port-sweep findings from 2026-04-26) through Patrik. Confirm Patrik names `security-audit-worker`, EM dispatches, and worker produces useful structured output.
- Replay a recent test-touched commit through Patrik or Sid. Confirm `test-evidence-parser` gets named and returns a useful failure classification table.
- Run `dep-cve-auditor` once standalone against `plugins/coordinator-claude/` and `plugins/claude-unreal-holodeck/` to seed a baseline.

**Delta-vs-baseline acceptance criterion** (per Patrik's review): for each replay, compare worker output against the original review's findings. Acceptance requires the worker either (a) surfaces an issue not in the original review, (b) confirms an issue with stronger mechanical evidence than the reviewer had, or (c) cleanly rules out a class of concern the reviewer flagged speculatively. If three replays produce none of (a)/(b)/(c), reconsider that worker before percolating to publish.

**Rollback:** Four agent files + three system-prompt edits + one CLAUDE.md edit. All clean reverts. Personas don't cascade.

### Phase 2 — `/merge-to-main` release-readiness gate + optional workers (1 session, opportunistic)

**Scope:**
- Extend `/merge-to-main` with the five-step checklist phase
- Add `changelog-drafter` worker (Sonnet, structured output by category)
- Add `install-script-sandbox` worker (Sonnet, sandboxed shell, idempotency check)
- Both workers invoked from `/merge-to-main` on demand based on diff size / files touched

**Trigger:** Next time we cut a non-trivial release (plugin republish, schema bump, install-script change). Don't build speculatively.

**Validation:** Run the extended `/merge-to-main` on the actual next release. Adjust thresholds (e.g. "diff large enough to warrant changelog-drafter") based on what actually fires usefully.

**Rollback:** Command edits + two new agent files. Symmetric to Phase 1.

## 5. Percolation to publish repos

The four workers and reviewer-prompt edits live in `~/.claude/plugins/coordinator-claude/`. The publish flow already syncs this to the coord-claude publish repo. Sequence:

1. Land Phase 1 here (`~/.claude/`) on `work/striker/2026-04-29`.
2. Validate against recent commits as above.
3. `/merge-to-main` here.
4. Run the existing publish-pipeline to push to the coord-claude publish repo.
5. Notify the holodeck team that the reviewer-routed-workers convention is live; they can layer UE-specific workers (`perf-trace-classifier`, `bp-test-evidence-parser`, `schema-migration-auditor`) on top using the same reviewer-routing pattern, in their own plan.

Phase 2 percolates the same way after the first release exercises it.

## 6. Acceptance criteria

- [ ] Four worker specs exist in coord-claude with structured-output contracts and DONE-after-write protocol
- [ ] Patrik / Sid / Camelia system prompts include the `Worker Dispatch Recommendations` section
- [ ] `review-integrator` agent preserves and surfaces worker recommendations
- [ ] `coordinator/CLAUDE.md` has a "Reviewer-Routed Workers" section enumerating the four workers and the protocol
- [ ] Phase 1 validation: at least one recent commit replayed through Patrik produces a worker recommendation that fires usefully
- [ ] Phase 2 (when triggered): `/merge-to-main` checklist runs on next release without disrupting flow
- [ ] No new persona files in `agents/` for Sam / Kira / Lee — confirmed absent

## 7. Open questions

### 7.1 Worker output: JSON vs. structured markdown

Workers produce structured output the EM and reviewers consume. JSON is parseable but harder for reviewers to read inline; structured markdown tables are reviewer-friendly but require parsing if a downstream tool wants the data. Recommendation: structured markdown with explicit columns, since the primary consumers are humans (PM, EM) and Opus reviewers — not parsers. Defer JSON variant until something needs to parse it.

### 7.2 `security-audit-worker` scope vs. dep-cve-auditor

Two workers in security-adjacent territory. Boundary: `security-audit-worker` reads code (path traversal, validation traps, injection, secrets in source); `dep-cve-auditor` reads dependency manifests (`package.json`, `requirements.txt`). No overlap, but document clearly in both specs to prevent drift.

### 7.3 Periodic dispatch for `dep-cve-auditor`

Should `dep-cve-auditor` run periodically or only on Patrik recommendation? Recommendation: both. Use the existing scheduled-recheck pattern — first run drops a `tasks/cve-recheck-due-YYYY-MM-DD.md` marker dated +7 days; `/workday-start` already globs `tasks/*-recheck-due-*.md` (per Step 1.6) and surfaces due rechecks to the EM. This keeps the cadence discoverable, skippable, and out of the daily-flow tax. Patrik can also name the worker on dependency-touching diffs as usual.

### 7.4 Cross-plugin edit for Sid's prompt

Sid lives in the holodeck plugin (`~/.claude/plugins/claude-unreal-holodeck/game-dev/agents/staff-game-dev.md`), but the worker-dispatch protocol section is mechanical (~5 lines, identical wording to Patrik's section minus references to UE-specific workers, which the holodeck team will add later). Phase 1 includes this cross-plugin edit so Sid's reviewer dispatches produce worker recommendations from day one — without it, dispatching Sid as a reviewer on UE work would be a silent capability gap. The holodeck team can layer their UE-specific workers on top in a follow-up plan; the protocol section itself ships now.

## 8. Estimated effort

| Phase | Sessions | Surface area | Risk |
|---|---|---|---|
| 1 — Four workers + reviewer protocol | 1 | 4 agent files + 2 system-prompt edits + 1 CLAUDE.md edit + 1 review-integrator edit | Low |
| 2 — `/merge-to-main` checklist + 2 release workers | 1 (opportunistic, on next release) | 1 command edit + 2 agent files | Low |
| **Total** | **2** | **~10 files** | **Low** |

Compare original plan: 9–14 sessions, 15–18 new agents, one phase rated High risk.

## 9. Cross-references

- Predecessor draft (holodeck side): `X:/claude-unreal-holodeck/docs/plans/2026-04-29-personas-workers-expansion.md`
- Existing reviewer pattern (Patrik→Palí escalation): `~/.claude/plugins/coordinator-claude/coordinator/agents/staff-eng.md`
- Worker shape reference: `~/.claude/plugins/claude-unreal-holodeck/game-dev/agents/ue-blueprint-worker.md`
- Coordinator doctrine on convention propagation: `~/.claude/plugins/coordinator-claude/coordinator/CLAUDE.md` § "Adding a Convention to the Coordinator System"
- Disk-first verification protocol: `~/.claude/plugins/coordinator-claude/coordinator/CLAUDE.md` § "Verifying Scout Deliverables"

---

**Approval needed from PM before Phase 1 dispatch:**

1. Worker roster (the four named in §2.1) — add, drop, rename
2. Reviewer protocol wording (§2.2) — voice and constraints
3. `/merge-to-main` checklist shape (§2.3) — five steps, EM-driven, optional workers
4. Phase 1 starts next session
