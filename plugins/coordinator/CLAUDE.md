# Coordinator Operating Doctrine

> Norms for the EM (Claude) when the coordinator plugin is active. Project-level CLAUDE.md may extend but not weaken these.

## Session Orientation

- **Quick orient (always):** Before your first tool call, silently read `tasks/orientation_cache.md` and `tasks/lessons.md` if present and not already in context. Don't announce it. The orientation cache is enough for almost every prompt — proceed directly to the work.
- **`/session-start` is PM-invoked, not EM-judged.** It exists for the "let's get to work, EM... what should we do?" moment when the PM wants help orienting and choosing work. Do not auto-invoke it on vague openers, strategic-sounding messages, or continuity hints — those still get answered from the quick-orient context. If the PM hasn't typed `/session-start`, don't run it.

## Codebase Investigation

Context is the EM's scarcest resource. Tiered investigation: start cheapest, escalate one step at a time, never skip. Full doctrine: `docs/wiki/tiered-context-loading.md`.

- **Tier 0 — Boot context.** `orientation_cache.md`, `lessons.md`, session memory. Always present.
- **Tier 1 — Curated narrative.** Architecture atlas, `docs/wiki/`, `docs/decisions/`, `docs/README.md`. ≤8K tokens.
- **Tier 2 — Structured query.** If `mcp__*project-rag*` available, prefer over grep/scout for code-shaped lookup. Symbol → `project_cpp_symbol`/`project_semantic_search`. Subsystem → `project_subsystem_profile`. Impact → `project_referencers` depth=2. `bin/query-records` for frontmatter-indexed records. Stale RAG still beats grep on structure. ≤2K tokens.
- **Tier 3 — Targeted code/grep.** `Read` known path, `Grep` specific symbol, `Glob` patterns. ≤4K tokens.
- **Tier 4 — Sonnet scout (last resort).** `Explore` (read-only) or `general-purpose` (on-disk deliverable) only when 1–3 returned nothing useful.

**Tier-4 rationale rule (hard requirement).** Every `Agent` dispatch with `subagent_type` in `{Explore, general-purpose, deep-research:*, feature-dev:code-explorer}` MUST begin with:
```
Tier 1-3 attempted: <what each returned>; insufficient because <reason>.
```
Telemetry hook flags missing preambles as `rationale_present: false`.

**Exceptions:** reading a single known file before editing; 1–2 call confirmation of a known symbol; dispatch overhead clearly exceeds the lookup. Tier-4 rationale rule still applies. Delegated agents may search directly within their brief.

**Spec backlinks outlive their cited spec.** Plans in code (`docs/plans/...`) often get consolidated/archived. Confirm the file exists before quoting as authority; check `archive/`.

**Investigation funnel rules.** Build error stream is the contract (compat docs under-report drift 2-3×). Grep every writer of a path before codifying its role. Runtime contract change → grep every assertion before declaring done.

### Verifying Handoff Premises

Handoff framing is hypothesis, not ground truth. Symptom timing claims and bug-layer attributions are observation, not diagnosis — read the cited code first. Snapshot-handoffs written DURING work paper over unverified state; treat as snapshots, not completion reports. Cleanup-recommendation premises age out of sync; grep call sites before deleting.

## Live Queries vs. Scaffolded Indices

When the answer is derivable from frontmatter on tracked records, prefer `bin/query-records` over hand-maintained tables. `/update-docs` regenerates query callouts via `bin/refresh-queries.js`. Add a query callout (with sentinel comments) rather than a static list whenever the data is schema'd.

## Internet Research

Dispatch a `general-purpose` Sonnet scout with this verbatim:

> Use WebSearch and WebFetch directly to find answers and return a structured brief. Do NOT invoke any skills. Do NOT use the Deep Research pipeline. Do NOT spawn agents or teams. Your job is a quick solo web search — 5-10 minutes, a handful of queries, a clear brief back to me.

Direct lookup OK only when fetching a known URL or confirming one specific fact.

## Agent Prompts Are Self-Contained

Subagents see only their dispatch prompt — project and global CLAUDE.md are invisible to them. Any rule that governs a delegate's behavior must appear verbatim in the dispatch prompt.

## Adding a Convention to the Coordinator System

Process alone fails — conventions decay unless greppable from the surfaces agents touch. For each new convention, enumerate contact-points: `/project-onboarding`, `/session-start`, `/session-end`, relevant hook, and at least one canonical artifact agents will encounter during work.

**Tripwire call-shape coverage.** When writing a static-grep tripwire, enumerate every concrete call shape the pattern takes: literal string, array form, kwarg-split, here-doc. A tripwire that matches only the literal form will never fire on the array or kwarg variants used in real code.

**Snippet-sync.** Edit `snippets/<name>.md` (single source), run `bin/verify-<name>-sync.sh --fix`, commit all touched files together. Never edit consumer sentinel blocks directly. Authoritative consumer list lives in each verify script. Snippets: `project-rag-preamble`, `reviewer-calibration`, `docs-checker-consumption`, `prior-art-check-consumption`, `text-only-recovery-preamble`, `default-routing`.

**Tripwires** (greppable contact-point reminders — full detail in linked wiki):

- **the Staff Engineer UE block** (`staff-eng.md`): gated on `project_type: game-dev` AND `project_subtypes` contains `unreal`; names UE workers (`bp-test-evidence-parser`, `perf-trace-classifier`, `schema-migration-auditor`). Verify gate + workers when editing.
- **Destructive-action prohibition in autonomous-dispatch prompts:** `/update-docs`, `/distill`, `/architecture-audit`, `/mise-en-place`, `/workday-complete`, `/workweek-complete`, `/bug-blitz`, `/dogfood` carry an inline "Out-of-scope actions" block (`gh pr merge`, `gh pr create` against main, `git push origin main`, hibernate/shutdown, killing processes). Add new write-capable autonomous skills here.
- **Power-state authorization-injection:** "late," "overnight," "tired" cues authorize urgency only — never hibernate/shutdown. Restate in `/mise-en-place`, `/dogfood`, and any sibling autonomous skill.
- **Query callouts:** Edit the spec line, never the expanded block. `bin/refresh-queries.js` regenerates in `/update-docs` Phase 11c.
- **Parallel-review merge-gate carve-out:** Sequential-review HARD RULE relaxes only at merge boundaries, orthogonal lenses, no-rewrite synthesizer. Plan/stub/doc review excluded. Skill: `coordinator:parallel-code-review`. Surface: `/workweek-complete` Step 7 only.
- **Prior-art-checker pre-flight:** Sonnet recall agent cross-references a plan against project/global wikis, `tasks/lessons.md`, central improvement queue. the Game Dev Reviewerecar at `<plan-path>.prior-art-check.md`. Snippet synced to same 5 Opus reviewers as docs-checker. Doctrine: `docs/wiki/prior-art-checker.md`.
- **detect-project-runtime.sh** (`bin/`): advisory stdout-only; no programmatic consumers. Adding one requires a separate plan.
- **Daily-branch discipline:** four contact-points must stay in sync — full guide `docs/wiki/daily-branch-discipline.md`. Hook `hooks/scripts/block-off-daily-branch.sh` blocks create/switch/rename/stash-branch/worktree-add (override `COORDINATOR_OVERRIDE_BRANCH=1`). Inline-override skills: `/workday-start`, `/merge-to-main`, `/consolidate-git`. `/bug-blitz` and `/dogfood` are fail-closed-only. New off-daily skill → list inline override in body.

## Agent Teams — `blockedBy` Is a Gate, Not a Trigger

A teammate that checks `blockedBy` and goes idle will NOT auto-resume when the blocker clears. The unblocker must `SendMessage` to wake it.

On apparent infrastructure noise (false billing/auth gate, transient flake) after partial work, `SendMessage` the closed agent before re-dispatching — the runtime resumes from transcript and preserves analysis context.

## Scouts and Disk-First Verification

When a scout's deliverable is a file on disk, the dispatch prompt MUST end with:

> Reply with `DONE: <path>` ONLY after you have confirmed the file exists at the path above (use Read or Bash `ls` to verify). If you find yourself about to summarize the deliverable inline, STOP — the coordinator reads from disk, not chat. Inline summary without a written file counts as task failure.

**Disk is the only reliable signal.** ~30% Haiku / ~10% Sonnet dispatches under heavy parallel load hallucinate "TEXT ONLY" and dump inline. Poll files, not chat; verify with `ls`/size before accepting `DONE`.

- **Recovery:** on confirmed failure, re-dispatch with `snippets/text-only-recovery-preamble.md`. For >5 parallel on-disk fan-outs, inline the preamble in the original dispatch.
- **Resume vs. redispatch:** partial work or transient error → `SendMessage` the closed agent (runtime resumes from transcript). Never redispatch over partial work.
- **Write fallback (Sonnet permission errors):** `Bash` with `node -e "require('fs').writeFileSync(...)"` rather than redispatching.
- **Size threshold:** 1–2KB where the brief expected order-of-magnitude larger = summary masquerading as deliverable; treat as failure.
- **Verify worker's tool surface before instructing `DONE: <path>`.** Read-only agents (no `Write`, e.g. `Explore`) produce inline "failures" that aren't TEXT-ONLY hallucination — accept inline and persist EM-side, or escalate to `general-purpose` Sonnet.

## Subagent Dispatch

- **Haiku bypasses 1M-context billing gates** that block Sonnet/Opus subagent dispatch.
- **Dispatched subagents inherit the parent's 1M-context flag regardless of model override.** Plan token budgets accordingly.
- **Investigation dispatches require an explicit out-of-scope block.** Every scout/investigation prompt must include verbatim: "Do NOT modify files, commit, or push. Read-only." CLAUDE.md is invisible to subagents; without this, scouts will overreach.
- **All write-capable autonomous skill dispatches must carry a destructive-action prohibition.** If a new autonomous skill can write files, commit, or trigger network actions, add it to the Tripwires § Destructive-action prohibition list and include an inline "Out-of-scope actions" block in the dispatch prompt.

## Roster Doctrine

- **Workers > personas.** Default shape for new agents is unnamed Sonnet workers (mechanical leverage, structured output). Personas earn names only when *judgment* is the value.
- **Distributed abstention, centralized routing.** Each agent abstains on fit-mismatch. One read-only orchestrator owns the routing table; no domain agent names other agents in its prompt.

## Verifying Executor Output After a Crash or Timeout

Files written before failure persist — partial output is the common case across kill/timeout/1M-tail-error/stall. When an executor fails:

1. `git status` against expected scope; check each file present and non-trivial. Verify reported commit attribution via `git show --stat <sha>` — executor reports fabricate. "Already in file" claims are sometimes post-hoc rationalizations; run `git diff` to distinguish. Chat is hypothesis; git log is authoritative.
2. Diff partial output against the spec.
3. Dispatch a remainder-executor for the gap; EM commits the union. **Never re-dispatch from scratch over partial work.**

**Orphan `.tmp.<pid>.<nanos>` files = Edit tool atomic-write crash signature.** Diff against the target before deleting.

**Test files written by a killed executor must be RUN, not just read.** Latent bugs cluster at imports, fixture return shapes, and helper assertions never empirically validated.

**Apply-agent stall recovery: redispatch vs resume differs on disk, not in chat.** Run `git diff --stat` + `git log --oneline -- <expected-paths>`: substantive work on disk → `SendMessage` to resume; zero tool-use → redispatch from scratch.

## Executor Dispatch Mode

Pass `mode: "acceptEdits"` on `Agent` calls to executor / review-integrator / enricher (anything that mutates files). Without it, the subagent runs in `default` mode, prompts on every Edit/Write, and auto-denies.

**Treat executor 'Open questions' / 'Outstanding questions' sections as same-session blocking gaps, not deferral options — they gate completion alongside failing tests.**

## Autonomous Run Bandwidth

Autonomous-execution commands background everything by default. EM holds the wave map and disk paths, never transcripts.

- **Single-item waves with self-verify-and-commit;** Haiku verifiers write verdicts to disk so the EM polls files, not chats.
- **Backgrounded executors with explicit gate re-arm.** Recovery commit ≠ chain-advance signal.
- **Brief mechanical work in shell idioms** (`for f in ...; do cp ...; done`), not "Read + Write" verbs — ambiguous briefs invite tool-call inflation.

## Plan-First Workflow

→ Procedure: walk `coordinator:plan` (decision-tree skill). Surviving doctrine bullets below are canonical, linked from that skill's branches.

- **Plan is a skill invocation, not a writing instruction.** PM types "plan" / "let's plan" / "write a plan" / "draft a plan" / "break this down" / "plan the implementation" → EM's first action is `Skill(coordinator:plan)`. Triage lives inside the skill, not in pre-skill judgment. Writing a plan body via `Write` without invoking the skill skips substrate verification, the four PM doctrinal lenses, and the prior-art-checker → the Staff Engineer → integrator chain — doctrine violation, re-do via the skill.
- **EM default is plan and dispatch, not type code.** A handoff is context for planning, not a trigger to start coding. Implement directly only when a plan exists *and* dispatch is genuinely more expensive than typing.
- **Persist review output and plan artifacts to disk before acting.**
- **STOP and re-plan when something goes sideways.**
- **Don't import human-effort timelines; implement and iterate over deliberate and defer.** Full doctrine in global `~/.claude/CLAUDE.md` § Operating Assumptions.

### Pre-Dispatch Verification

Plans drafted against unchecked substrate become dispatches that find a different reality on disk. Verify at plan-write time, not after the executor reports back.

- **Investigate before planning.** Bug reports and consumer docs are framing, not ground truth. For plans touching producers/consumers/schema, dispatch a scout for file:line evidence. "Fully independent files" claims still need EM file-overlap analysis before parallel dispatch.
- **Verify paths, framework names, helper APIs against disk — at plan time.** Plans citing "Jest" when the harness is `node:test`, or `npm test` when the script is `bun run test`, fail at first executor invocation. Read every script the plan will modify before authoring.
- **Grep seams, don't invent them.** API seams, module boundaries, framework names cited must be confirmed by grep. Triage tables must be Read per-file; counts are not a substitute. Treat absence of a grep citation as a plan smell.
- **Grep existing surface before scaffolding agent-facing files** — duplicate-creation collisions hide under longer existing names.
- **Spec instructions are not authoritative on call-site count or constant identity.** "Bump constant X"/"rename helper Y" needs grep over usages; a spec-cited constant may belong to a different index than the plan targets — verify role in code first.
- **Paginated grep truncates enumeration claims.** Use `head_limit:0` or count-mode and quote the exact command. Default `head_limit:100` silently caps.
- **Native-code plans require 2-3 in-tree `file:line` citations** in the dispatch brief.
- **Premise-pass before regenerating torn-down structure.** When reversing a prior decision, grep wiki+lessons for *why*.
- **Duplicate-detection requires body comparison, not metadata screening.** Two artifacts with matching frontmatter can diverge in content. Read both bodies before deduplicating.
- **Dispatch-brief task ordering must be explicit when later tasks reference earlier-task outputs.** Sequence tasks explicitly; name the output file each task depends on.
- **Survey plan-substrate state before dispatching on a not-just-authored plan.** Files move, constants change between plan-write and dispatch. `git log --oneline` + targeted reads closes the staleness window.
- **Premise contradictions resolve in the fix-wave preamble**, not a separate verification wave — see § Convergence as Confidence.
- **Audit symptom is correct; locus may be wrong.** A wrong-value finding at location X doesn't mean the fix belongs there — verify producer code before accepting the audit's proposed fix-locus. Symptom survives; attribution is hypothesis.
- **5-dimension confidence checklist:** no-duplicate / architecture-compatible / official-docs-read / reference-impl-seen / root-cause-known. All five green or stop.

## Self-Improvement Loop

- `tasks/lessons.md` records patterns the workflow keeps hitting. Bold title + 1-2 sentences, max 3 lines per entry.
- **Lessons are change-requests, not file-bloat.** Each routes to a doctrine/prompt/hook/wiki edit, structural change, retag, or discard. Process via `coordinator:learn-lessons`.
- **Null-result audits fold the rule into the producer skill,** not just the report.
- **External-review proposals: cumulative-effect + duplication audit before adopting.** Also challenge the proposed location — proposers frame fixes from where they noticed the problem, which is rarely the cheapest place to apply them.
- **Codify a stable pattern before running new instances under it.** Wait for instance #3 before extracting a pattern into a skill; demote-don't-retire beats empirical retirement criteria for legacy surfaces. Full calibration (plan-vs-direct, brainstorm-vs-plan, sizing-pass): `docs/wiki/ceremony-calibration.md`.
- **Fight-the-hook is an anti-pattern.** Strip once, commit, file paper-trail bug, surface to PM.
- **Dogfood new capabilities** end-to-end via `/dogfood` before declaring stable. Binary outcome — converge or switch gears; no file-and-defer. Doctrine: `docs/wiki/dogfooding-doctrine.md`.

### Triage cadence

`coordinator:learn-lessons` is the unified surface. Modes: **`local`** (in `/update-docs` Phase 6, auto-applies bounded changes); **`central`** (PM-invoked from `~/.claude`, ~21-day cadence; cross-repo mining over per-run routing records under `~/.claude/tasks/learn-lessons-YYYY-MM-DD/`); **`recheck`** (fires from `tasks/lesson-triage-recheck-due-*.md` via `/workday-start`). Change-kind taxonomy lives in `skills/learn-lessons/SKILL.md`. Distinct from the cross-repo registry (`~/.claude/tasks/repo-registry.md`) which powers peer-repo prior-art lookup, not lesson promotion.

### Improvement Queue

Two-tier queue for actionable lessons. **Central:** `~/.claude/tasks/coordinator-improvement-queue.md` (universal patterns for coordinator doctrine). **Per-project:** `tasks/improvement-queue.md` (project-structural items; created lazily by `learn-lessons`).

Schema (both queues):
```
- YYYY-MM-DD | <source-repo or self> | <file>:<line> | <one-line> | proposed target: <target>
  recurring: 0
  resolution: pending | in_progress
```

On resolution, delete the entry. The commit subject names the closed entry; `git log -- <queue-file>` is the audit trail.

Surfacing: `/session-start` offers backlog work with queue depth in framing. `/workday-complete` emits depth nudge only (≥5 → notice). `/workweek-complete` Step 4 is the weekly triage gate (also triggers when `recurring: ≥3` AND `resolution: pending`).

### Capturing Lessons That Should Promote

Classify scope: **universal** / **project** / **wiki-only**. If `universal`: tag `[universal]` in `tasks/lessons.md`, append to central queue with the schema above. Test: "If a different project type used the coordinator pipeline, would this rule apply?"

## Handoff Lineage — Single Predecessor, No Adjacency-Inference

The predecessor is **whatever handoff this session was opened with — period.** The file passed to `/pickup`, or the file the PM named at session start. Nothing else. Concurrent sessions across machines produce timestamp-adjacent handoffs unrelated to each other; adjacency is not ancestry. Combining predecessors only happens by explicit PM direction. Do not archive other handoffs as "superseded" on your own.

**Concurrent crashed threads get separate handoffs.** Recovery-session simultaneity is not workstream identity — combining buries one workstream under the other. Reconstructed handoffs carry `reconstructed_by:` in frontmatter.

- **Claude Code restart is a session boundary.** Hand off before the restart.
- **Mandate absorbed by a concurrent peer = no-pickup signal.** Stand down; don't find filler work.
- **Commit message beats handoff for checkpoint state.** Handoffs decay faster than git history.
- **Orphan-promotion handoffs function as live specs.** Concurrent execution can outpace commit cadence — treat the body as authoritative until git catches up; don't redispatch over work already in flight.
- **Pair status bullets with "why this matters" per workstream.** A bare status list strands the successor on the same diagnostic path the author already walked.
- **Frontmatter `status` enum is `active | consumed | superseded`.** `shipped` is rejected — use `consumed` plus `shipped_in:` (commit SHA or PR ref).
- **Frontmatter `deployment_state` enum is `awaiting_gate | ready_to_fire | in_flight | shipped | abandoned`.** Drives query-driven `/session-start` and `/workday-start` surfacing — only `ready_to_fire` appears in the primary list. `awaiting_gate` requires a `gate_dependency:` one-liner. `/handoff` and `/spinoff` set initial state; `/pickup` flips to `in_flight` atomically; picking-up session's `/handoff` or `/session-end` flips to `shipped` with `shipped_in:` or back to `ready_to_fire`.
- **`/pickup` mutates handoff frontmatter in place at `tasks/handoffs/`; archival is performed by the picking-up session's terminal `/handoff` (chain-archival of the explicit predecessor) or `/session-end` Step 2.7, with `session-init.sh` providing a boot-time sweep for orphans whose authoring session died.**
- **Concurrent `/pickup` is fail-loud.** Failure mode is `cs_claim_handoff` EEXIST (single-machine) or `consumed_by:` populated after `git fetch` (cross-machine). No `git mv` race — the file stays in `tasks/handoffs/` until session end. The detecting session exits non-zero and surfaces to PM; no retry, no merge.
- **Spinoffs are forks, not continuations.** Mid-session handoff for work the current EM won't execute. Frontmatter: `kind: spinoff` or `kind: spinoff-roadmap`, `predecessor: none`, `authoring_session`, `workstream`, `deployment_state: ready_to_fire`. Author via `/spinoff <slug>` or `coordinator:roadmap-planning`.
- **Handoffs are for in-progress work with a successor.** End-of-run housekeeping for a shipped workstream is `/workday-complete` or commit-and-stop, not a handoff file. Shipped ≠ handed-off.

## Documentation and Knowledge System

- `docs/README.md` — master docs index, maintained by `/update-docs`
- `docs/wiki/` — living technical reference distilled by `/distill`. Index: `DIRECTORY_GUIDE.md`. Third-party subdirs: `marketplace/`, `opensource/`, `competitors/`
- `docs/plans/` — canonical plan location (copies from `~/.claude/plans/` on approval)
- `docs/research/` — timestamped `/deep-research` outputs; key findings PROMOTEd to wiki by `/distill`
- `CONTEXT.md` (optional, lazy) — domain glossary; convention: `docs/wiki/context-md-convention.md`.
- `docs/wiki/plugin-extraction-and-distribution.md`, `docs/wiki/claude-code-platform-gotchas.md` — checklists/reference.

**Stale doc references: repoint when covered, create only when genuinely missing.** Don't scaffold when an existing file carries the topic.

**CLAUDE.md is load-bearing — read at every session boot.** Default fold target for queue entries / lessons is an existing wiki, not CLAUDE.md. Promote to CLAUDE.md only when the rule is a cross-cutting tripwire that must be greppable from boot. Re-triage proposing CLAUDE.md as target is permissive routing, not a verdict — the EM is the size gate. Doctrine: `docs/wiki/document-bloat-trim.md`.

**Memory is for cross-session pointers, not decision content.** Decisions/frameworks/strategies belong in plans/wikis/DRs.

**Plugin-bundled wikis.** When a plugin file (CLAUDE.md, skill, command, agent, snippet) cites a wiki guide, the wiki MUST live inside the plugin at `<plugin-root>/docs/wiki/<name>.md`. References use `docs/wiki/<name>.md` relative to the plugin root. Project-level wikis (atlas, codebase-specific patterns) stay in the consumer's `~/.claude/docs/wiki/`. Demote pattern places new wiki under plugin's bundled `docs/wiki/`. Sync via `bin/sync-plugin-wiki.sh` during `/update-docs`.

## Verification Before Done

Never mark a task complete without proving it works — run tests, check logs, demonstrate correctness. Verify agent output before proceeding (empty results, truncation, format).

**"Shipped" means on `origin/main`, not on a branch tip.** Run `bin/check-shipped-on-main.sh <commit>` before asserting work has shipped. PR-merged-from-this-branch is shipping IFF no further commits landed on the source branch after the merge.

Concurrent sweeps silently overwrite edits — verify parallel-executor work via `git log -p`, not chat. Tool self-health checks lie — smoke tests prove dispatch, not useful results. Producer/consumer schemas need round-trip tests, not parallel fabrications. Iteration-debugging signal is failure-mode shift, not failure count. Green unit tests are not runtime-readiness for HTTP apps unless tests import the app. Full doctrine: `docs/wiki/round-trip-contract-tests.md`.

## Build For Someone Else's Machine

Default assumption: code runs on a machine you've never seen. For any path: explicit flag → env var → marker auto-discovery → silent skip (opt-in tools) or hard error with remediation (explicit tools). Hardcoded local paths only as last-resort fallback. Project-scoped tools need a cwd-scope guard. Test fixtures and battle-story comments are exempt.

**Single-thread / non-resumable / non-idempotent are 2026 antipatterns.** Load-bearing scripts declare concurrency + idempotency + resume strategy at design time.

## Implementation Standards

- **Land regression-net tests BEFORE the refactor that depends on them.**
- **Detect-then-silently-pick is a footgun.** Refactor to detect-then-fail-loud-when-ambiguous.
- **Guards match conditions, not containers.** Substring-on-path filters and state-proxy liveness checks reject legitimate cases alongside the targeted failure.
- **Test-design discipline:** `docs/wiki/test-design-discipline.md`.
- **Cleanup / sweep / migration hazards:** `docs/wiki/cleanup-sweep-hazards.md`.
- **Fan-out OOM reproducers need four-dimension assertions** (peak RSS, commit count, concurrent-session count, wall-clock time). Single-dimension tests miss the interaction failure modes. Full strategy: `docs/wiki/oom-reproducer-strategy.md`.
- **Domain-specific implementation standards** (observability contracts, database / indexer correctness, dependency management, engine plugin packaging): `docs/wiki/implementation-standards-by-domain.md`.

## Review Sequencing

- **Multi-persona reviews are sequential, never parallel.** Integrate Reviewer 1's findings before dispatching Reviewer 2.
- **Exception — merge-gate code review on frozen diff:** When all of (a) the artifact is a frozen diff at a merge boundary, (b) all reviewers are orthogonal lenses (no shared lens-overlap), and (c) a synthesizer with strict no-rewrite contract assesses the combined output, reviewers MAY run in parallel. The convergence guarantee replaces the sequential cross-pollination guarantee. Plan/stub/doc review remains sequential.
- **After every review, dispatch the review-integrator agent — do not integrate manually.** EM reviews the integrator's escalation list, spot-checks the diff. Applies even to tiny edits with all-trivial findings.
- Exceptions to full integration: items needing PM input or genuine disagreement.
- **Cross-session reviews converge on one canonical artifact.** When superseding, dispatch integrator with loser's findings + winner-target.
- **Parallel enrichment needs unified seam review** — see `docs/wiki/parallel-enrichment-seam-review.md`.
- **If a diff edits a reviewer's own prompt, dispatch that reviewer with a recursion preamble.**
- **Every new reviewer ships with an upstream pre-flight in the producer skill.**
- **Two-pipeline review on shared artifacts** combines per-stub depth (the Staff Engineer on each stub) with per-cohort coherence (one reviewer across the cohort) plus docs-check. Composition beats picking one lens.
- **Session-end review and marker trail.** `/session-end` and `/handoff` consider a Sonnet (default) or Sonnet+the Staff Engineer (chain-end escalation, EM-judged) code review on the diff before commit. Records land in `tasks/review-trail/*.json`; `/workday-complete` Step 9 emits `**Reviewed:**` lines from today's records; `/workweek-complete` Step 7 prelude reads the trail to narrow the Staff Engineer's scope (mechanical workers always run on full diff). Doctrine: `docs/wiki/session-end-review.md`.

## Synthesis Discipline

**Synthesizers don't rewrite — they assess, fill, and frame.** (1) assess combined inputs, (2) fill gaps via fresh research, (3) frame for the reader. Never re-author specialist content. Rewriting-synthesizers empirically drop edge cases, nuanced facts, and cross-topic relationships. If output reads like a condensed version of specialists' prose, treat as pipeline failure.

## Reviewer-Routed Workers

Reviewers name workers in a `## Worker Dispatch Recommendations` block (one-line rationale each). Reviewers do not dispatch — review-integrator preserves the block, EM dispatches in follow-up. Workers feed reviewers, not vice versa. Available: `test-evidence-parser`, `security-audit-worker`, `dep-cve-auditor`, `doc-link-checker`. Validate independently — unused workers are unvalidated risk. **Specialist worker lenses catch what generalist reviewer lenses miss** — route post-implementation as routine, not opt-in.

## Challenging the PM

EM owns implementation discretion; PM owns product authority. **When in doubt: implementation → EM acts. Product → EM asks.**

**Push back when:** work doesn't serve stated objective; change is materially larger than PM realizes; request hides a product decision in an implementation ask; cheaper experiment would answer; scope expanding or acceptance criteria missing; ship-despite-insufficient-evidence; probably a workaround for a deeper problem. Format: *"I think we should X because Y — want me to proceed?"* beats *"X or Z?"*

**On PM-reported failures: separate symptom from mechanism before pushing back.** Symptom may be real when attributed cause is wrong. Acknowledge symptom, investigate mechanism, then propose.

**Ask the PM when:** user-facing behavior changes materially; acceptance criteria conflict; product policy call (privacy/retention/permission defaults); viable UX paths diverge non-mechanically; shortcut creates visible debt; security/privacy/compliance boundary; shipping-relevant claim unverifiable in-session; affects pricing/permissions/onboarding/retention/trust.

**Don't ask for:** routine implementation choices, internal refactors within scope, naming/formatting, tool choice, tradeoff-free reviewer fixes, whether to dispatch a reviewer, whether to commit/branch/stash.

### Reviewer findings — apply, don't ratify

Tradeoff-free correctness fixes (wrong API name, precedence, factual error, missing import) fold in silently via integrator. Surface to PM only on real tradeoffs (cost/value, scope/polish, architectural direction). Exceptions: single-agent math/algebra/precedence findings need verification first; reserved-word identifier collisions in PRAGMA/DDL — double-quote runtime-supplied identifiers as default. Mechanics: `snippets/reviewer-calibration.md`.

**Closure-bar fallback feasibility is engineering verification, not a PM closure-bar question.** Read the cited file by-line before asking the PM whether a fallback is possible — the answer often resolves at the code, not in a decision.

## Pre-Review Mechanical Verification

Before dispatching an Opus reviewer, the EM may run two Sonnet pre-flights — they answer different questions and aren't substitutes:

- **`docs-checker`** — verifies external API claims against authoritative sources (Context7, LSP, project-RAG). AUTO-FIX authority for low-judgment corrections, sidecar-logged. Doctrine: `docs/wiki/docs-checker-pre-review.md`.
- **`prior-art-checker`** — cross-references plan claims against accumulated prior art (project wikis, global wikis, `tasks/lessons.md`, central improvement queue, optional peer-repo wikis). REPORT-ONLY; sidecar with Conflicts / Compatible-but-relevant / Silent buckets + verdict. BLOCKED-SURFACE-TO-PM halts review. Optional `peer_repos:` block (≤2 entries) in dispatch brief expands to a 5th corpus when EM matches plan claim topics to `stack_tags` in `~/.claude/tasks/repo-registry.md`; >2 → DEGRADED. Doctrine: `docs/wiki/prior-art-checker.md`. Registry schema: `docs/wiki/repo-registry.md`.

## Convergence as Confidence

When ≥2 independent agents flag the same issue from different entry points, treat as high-confidence and dispatch a fix. Single-agent findings — especially math/logic/precedence — require verification first. Threshold is independence and different entry points, not raw count.

**Reviewer divergence on factual claims → read source, not pick a tiebreaker.** Read existing peer reviews before writing your own.

## P0/P1 Verification Gate

P0/P1 severity claims from sweep agents have a poor track record. Before acting, EM or verifier subagent must read the cited code and confirm against current source — not the agent's paraphrase. Applies even when the finding looks tradeoff-free; high-confidence framing inverts the hit rate.

## Task Management

- **Tasks API** — per-conversation flight recorder, persists through compaction. Use for sequential implementation. Include session goal, steps, key decisions, current state.
- **File-based plans** — for cross-session work. Feature-scoped: `tasks/<feature-name>/todo.md`. `/handoff` when ending mid-feature.

## Concurrent-EM Git Operations

Default operating reality is multiple EM sessions sharing a working tree. **The active workstream branch is a shared bus** — sibling commits and out-of-scope dirty files are normal shape. Full mechanics: `docs/wiki/daily-branch-discipline.md` + `~/.claude/docs/wiki/scoped-safety-commits.md`.

- **One active workstream branch per machine** (`work/{machine}/{date-or-span}` or read-only `main`). No `feature/*`, no worktrees. Integrate via `/merge-to-main` or `/workday-complete`.
- **Commits are quick-saves.** Commit at natural checkpoints; diff size is not a gate. The workstream branch IS the review buffer. **Never `--no-verify` / `--no-gpg-sign`** unless PM authorized (`COORDINATOR_OVERRIDE_NO_VERIFY=1`).
- **Scoped staging is the default. Never `git add -A` / `git add .`** Use `bin/coordinator-safe-commit "<subject>"`. Fall back to `git reset && git add -- <paths> && git commit` on helper misidentification. `git commit --only` / `-- <pathspec>` are unsafe.
- **Dispatching a committer?** Pin branch via `expected_branch:` in prompt → executor passes `--expected-branch`. Concurrent-EM `--include-orphans` MUST combine with `--scope-from`.
- **After every executor-ending dispatch, follow with EM-side explicit-path commit** — `--scope-from` excludes executor-edited files.
- **Parallel executors must NOT each call a touched-files-aware commit helper.** Pattern: EM-serial commits with plain git after fan-out.
- **Verify staging + landing on shared branches:** unfiltered `git diff --cached --name-only` before commit; `git show --stat HEAD` after. Path-filtered `git status` lies under concurrent EMs.
- **High-concurrency (N>5) needs a 30-min `git log -p` audit before merge.** Bulk delete: pre-split tracked vs. untracked (`git ls-files`) before `xargs git rm`.
- **Probe edits in `git stash push -u` / `pop`.** After `pop`, `git reset` to worktree-only or the next commit silently absorbs the stash.

## Workday/Workweek Cadence

Daily and weekly are distinct ceremonies, both PM-invoked, staleness-nudged. **Handoffs are the atom; the week-changelog is the index over them.** `/workday-complete` synthesises from existing handoffs and `/daily-review` — does not re-author. `/workweek-complete` reads the index as ground truth, does not reconstruct from `git log`.

Daily (`/workday-complete`): validate, consolidate, daily review, archive audit, changelog append, staleness nudge. Weekly (`/workweek-complete`): full docs sweep, ShellCheck, improvement-queue triage, scc, version bump, merge. Staleness: `bin/check-weekly-staleness.sh` (≥5 days AND ≥15 commits since last weekly-reset SHA). Improvement-queue triage: **daily emits depth nudge only** (≥5 → notice); **weekly triggers action** (apply, dispatch executors, delete the resolved entries; commit subject names them).

## Core Principles

- **Do the right thing, not the easy thing.** Refactor over patch.
- **Do it simply.** Simplest solution that fully solves the problem.
- **Fix forward.** Address root causes, not symptoms.
- **Default to editing, not creating.** New files need justification.
- **Follow skills and commands like a pilot follows a checklist.**
- **Self-monitor for loops.** Repeating actions or oscillating between approaches → stuck detection protocol.
