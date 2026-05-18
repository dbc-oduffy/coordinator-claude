---
title: Coordinator tripwires — registry
type: doctrine
status: living
provenance: extracted from coordinator/CLAUDE.md § Adding a Convention 2026-05-18
---

# Coordinator Tripwires — Registry

> Registered tripwires: hooks, agent-prompt rules, and override env vars. When adding a new tripwire, register it here AND update the relevant agent prompt / hook / skill in the same commit. CLAUDE.md keeps a one-line pointer; the catalogue lives here.

## Snippet-sync

Edit `snippets/<name>.md` (single source), run `bin/verify-<name>-sync.sh --fix`, commit all touched files together. Never edit consumer sentinel blocks.

Current snippets: `project-rag-preamble`, `reviewer-calibration`, `docs-checker-consumption`, `prior-art-check-consumption`, `plan-coverage-check-consumption`, `text-only-recovery-preamble`, `default-routing`.

Snippet-sync flow for `plan-coverage-check-consumption`: edit `snippets/plan-coverage-check-consumption.md` → run `bin/verify-plan-coverage-sync.sh --fix` → commit all touched files together. Consumer sentinel: `<!-- BEGIN plan-coverage-check-consumption (synced from snippets/plan-coverage-check-consumption.md) -->` / `<!-- END plan-coverage-check-consumption -->`. Consumers: `agents/staff-eng.md` (the Staff Engineer), `../game-dev/agents/staff-game-dev.md` (the Game Dev Reviewer), `../data-science/agents/staff-data-sci.md` (the Data Science Reviewer), `../web-dev/agents/senior-front-end.md` (the Front-End Reviewer), `agents/eng-director.md` (the Director of Engineering).

## Tripwire registry

- **the Staff Engineer UE block** (`staff-eng.md`): gated on `project_type: game-dev` AND `project_subtypes` contains `unreal`; names UE workers (`bp-test-evidence-parser`, `perf-trace-classifier`, `schema-migration-auditor`).

- **Destructive-action prohibition in autonomous-dispatch prompts:** `/update-docs`, `/distill`, `/architecture-audit`, `/mise-en-place`, `/workday-complete`, `/workweek-complete`, `/bug-blitz`, `/dogfood` carry inline "Out-of-scope actions" block (`gh pr merge`, `gh pr create` against main, `git push origin main`, hibernate/shutdown, killing processes). Add new write-capable autonomous skills here.

- **Power-state authorization-injection:** "late," "overnight," "tired" cues authorize urgency only — never hibernate/shutdown. Restate in `/mise-en-place`, `/dogfood`, siblings.

- **Query callouts:** Edit the spec line, never the expanded block. `bin/refresh-queries.js` regenerates in `/update-docs` Phase 11c.

- **Parallel-review merge-gate carve-out:** Sequential-review HARD RULE relaxes only at merge boundaries, orthogonal lenses, no-rewrite synthesizer. Skill: `coordinator:parallel-code-review`. Surface: `/workweek-complete` Step 7 only.

- **Prior-art-checker pre-flight:** Sonnet recall agent cross-references plan vs. project/global wikis, lessons, central queue. Sidecar at `<plan-path>.prior-art-check.md`. → `docs/wiki/prior-art-checker.md`.

- **detect-project-runtime.sh** (`bin/`): advisory stdout-only; no programmatic consumers.

- **Daily-branch discipline:** → `docs/wiki/daily-branch-discipline.md`. Hook `block-off-daily-branch.sh` blocks create/switch/rename/stash-branch/worktree-add (override `COORDINATOR_OVERRIDE_BRANCH=1`). Inline-override: `/workday-start`, `/merge-to-main`, `/consolidate-git`. `/bug-blitz` and `/dogfood` fail-closed-only.

- **Wiki-mirror block:** `block-dev-side-mirror-wiki.sh` blocks writes to `~/.claude/docs/wiki/<name>.md` when bundled copy exists. Override: `COORDINATOR_OVERRIDE_WIKI_MIRROR=1`. Write plugin-doctrine wikis to bundled path directly.

- **Unauthorized-handoff block:** `block-unauthorized-handoff.sh` blocks `Write` creating a new file in `tasks/handoffs/` or `tasks/spinoffs/` unless transcript shows recent `/handoff`, `/session-end`, or `/spinoff` invocation. Edits to existing files always allowed (covers `/pickup` mutation, review-marker writes). Override: `COORDINATOR_HANDOFF_AUTHORIZED=1` (rare-use). Cross-repo messaging is NOT a use-case — see `docs/wiki/cross-repo-communication.md`.

- **Improvement-queue nudge:** `nudge-improvement-queue-write.sh` blocks `Write`/`Edit`/`MultiEdit` appending a new `- YYYY-MM-DD` entry to any `*improvement-queue.md` and surfaces the four laziness-trap questions (fix-now? PM-call? lazy? scope-decision?). Skipped silently during `/learn-lessons`, `/workweek-complete`, `/workday-complete`, `/distill`, `/session-end`, `/update-docs`, `/bug-blitz`, `/mise-en-place`. Pruning/reformat edits also pass (entry-line count check). Override: `COORDINATOR_QUEUE_PUNT="<one-sentence reason>"` — trivial values ("1", "ok", <12 chars) rejected; the friction IS the typed reason.

- **Persona-at-Sonnet block:** dispatching `coordinator:staff-eng` (or any domain persona) with `model: "sonnet"` override is a doctrine violation. Sonnet code review → `coordinator:code-reviewer`. No hook enforces this yet; the rule is greppable from `CLAUDE.md` + `skills/review-code/SKILL.md` + `skills/session-end/SKILL.md` + `agents/code-reviewer.md`.

- **Swappable-sink-check (SWAPPABLE-SINK-CHECK):** [universal] When a producer-side change ships a swappable-sink / dependency-injection seam (a parameter that accepts a callable/module to be swapped in at boot), verify the corresponding wire-up call exists at the boot or entry-point surface BEFORE stamping the feature shipped. Synthesis-shape tests pass either way; only a wire-level dogfood surfaces inert sinks. Contact-points: `/session-end` (verify wire-up present for any new sink introduced this session), `/merge-to-main` (grep for unconsumed sinks — sinks introduced since last merge that lack a boot-time wire-up call). Greppable token: `SWAPPABLE-SINK-CHECK`. Origin: `project-rag-ue-addon/tasks/lessons.md` L63 — round-7 root cause K-1.

- **Cross-repo-halves-check (CROSS-REPO-HALVES-CHECK):** [universal] When a cross-repo feature requires both an addon-side registration AND a host-side call-site (e.g. hookimpl + `pm.hook.*()` boot call), both halves must be present in shipped commits on each repo's main branch before the feature is stamped shipped. Shipping one half alone leaves the feature inert and produces regress loops across dogfood rounds. Contact-points: `/handoff` (enumerate cross-repo halves in-flight; note which repo still owes its commit), `/workday-complete` (for each feature stamped shipped today, verify peer-repo half landed via `git -C <peer-repo> log --grep=<feature-token> --oneline` or `bin/check-shipped-on-main.sh`). Greppable token: `CROSS-REPO-HALVES-CHECK`. Origin: `project-rag-ue-addon/tasks/lessons.md` L971 — round-7 root cause K-1 (second lens).

- **Cross-repo-import check (CROSS-REPO-IMPORT-CHECK):** [universal, triad-specific] The triad-roles doctrine (`project-rag-ue-addon/docs/wiki/triad-roles-doctrine.md`) requires composition between `claude-unreal-holodeck` and `project-rag-ue-addon` to happen at the MCP / query surface in `project-rag`, never via in-process coupling. Enforced by grep: `from project_rag_ue_addon` or `import project_rag_ue_addon` appearing under `claude-unreal-holodeck/` source, or `from claude_unreal_holodeck` / `import claude_unreal_holodeck` appearing under `project-rag-ue-addon/` source, is a doctrine violation — the work needs re-partition (one side owns it cleanly, the other consumes via the on-disk envelope). Contact-points: `/merge-to-main` (pre-merge grep at the touching repo's root), `/session-end` (post-work grep on the diff scope). Greppable token: `CROSS-REPO-IMPORT-CHECK`. Origin: `project-rag-ue-addon/docs/wiki/triad-roles-doctrine.md` §"Composition across the seam" — Zolí pass-2 ratification 2026-05-18 of holodeck-EM-proposed refinement #1.

- **Blanket-commit destructive-shape gate:** `bin/coordinator-safe-commit` `do_blanket` fires `_blanket_check_destructive_shape` after `git add -A` and before `git commit`. Fails (or warns) when ≥3 files in the staged set have deletion-heavy diffs (≥10 lines deleted AND deletions > insertions) AND the commit subject lacks a word-boundary-anchored reference token (`handoff`, `spinoff`, `learn-lessons`, `update-docs`, `session-end`, `distill`, `PR #N`, `#N`, `plan/`, `plan #`, `lessons.md`, `queue.md`, `review-trail`, `workday-{start,complete}`, `workweek-{start,complete}`). Soft-warn through 2026-06-01 then promotes to fail-loud. Override: `COORDINATOR_OVERRIDE_BLANKET_SHAPE=1` (silence the gate entirely — emergency only). Strict mode: `COORDINATOR_BLANKET_SHAPE_STRICT=1` (fail-loud immediately, skipping the soft-warn window — useful in CI). Origin: queue entry 2026-05-16 (project-rag, blanket-commit shape-check tripwire) — catches the 572a548b-class regression where unauthorized substrate changes ride a blanket sweep commit without paper trail.

## Tripwire call-shape coverage

Static-grep tripwires must enumerate every call shape: literal string, array form, kwarg-split, here-doc. A tripwire that grep-matches one shape and misses the others fires asymmetrically and erodes trust in the gate.

## Related

- `~/.claude/CLAUDE.md` § Adding a Convention to the Coordinator System — boot-time pointer
- `docs/wiki/document-bloat-trim.md` — why this wiki exists separately from CLAUDE.md
- `docs/wiki/hook-best-practices.md` — JSON deny shape, friction-as-warning, model-version gating
