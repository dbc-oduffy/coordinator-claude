---
description: Setup or maintenance of coordinator scaffolding in repos. Default: deep first-time setup of one repo (interactive). --batch: idempotent fleet pass over working-repos.yaml. Consolidated 2026-06-08 from /project-onboarding + /bootstrap-repos.
allowed-tools: ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "AskUserQuestion"]
argument-hint: "[--batch [--check-only] [--non-interactive]]"
---

# /repo-setup — Coordinator Repo Setup

<!-- spec-backlink: docs/plans/2026-06-08-repo-setup-consolidation.md (consolidation); docs/plans/2026-05-29-it-just-works-agentic-install-currency.md § Chunk 4 (batch-mode currency); docs/plans/2026-05-30-onboarding-install-redesign.md (superseded "three surfaces" architecture) -->

Single surface for two modes of coordinator scaffold setup:

- **Default (no flag) — single-repo interactive.** Deep first-time setup of one repo. Run from inside the target repo's cwd. Dispatches `Skill(coordinator:repo-setup)` which walks Phase 1 (detect) → Phase 1.5 (substrate) → Phase 2 (ask PM 3 questions) → Phase 3 (generate CLAUDE.md / tracker / docs/README.md / hooks / VS Code guard / currency stamp) → Phase 4 (report).
- **`--batch` — fleet non-interactive.** Reads `~/.claude/working-repos.yaml` and runs the single-repo flow over every repo on disk without prompting. PM-position: invoked from `~/.claude` cwd, not from inside a target repo.

## Flag contract

- `--batch` — opt-in to fleet mode. Without it, the command runs single-repo from cwd.
- `--check-only` — dry-run; reports per-repo action list without writes. **Batch-mode-only.**
- `--non-interactive` — skip all `AskUserQuestion` prompts; apply Phase-2 substituted defaults from detected stack + substrate. **Batch-mode-only.**

**Detect-then-fail-loud rejection (AC12 binding):** If `--check-only` or `--non-interactive` is passed without `--batch`, exit with:

> `--check-only and --non-interactive are only valid with --batch; for non-interactive single-repo setup, set coordinator.local.md first and re-run /repo-setup.`

Do NOT silently pick a meaning for an ambiguous flag combination. Per `docs/wiki/coordinator-tripwires.md` § Detect-then-fail-loud.

## Dispatch — single-repo (default)

When no flag is passed, dispatch the skill:

```
Skill(coordinator:repo-setup)
```

The skill walks its documented phases. See `skills/repo-setup/SKILL.md` for the full flow.

## Dispatch — batch (`--batch`)

When `--batch` is passed:

1. **Precondition:** `~/.claude/working-repos.yaml` must exist (produced by `/setup` Phase 2 Step 4). If missing, exit with: `"working-repos.yaml not found. Run /setup first."`
2. **Delegate to the orchestrator:**
   ```bash
   # Strip --batch before forwarding: the orchestrator is already in batch mode by virtue of this dispatch branch; --batch is the command-level mode flag, not an orchestrator flag.
   _fwd_args="${ARGUMENTS:-}"
   _fwd_args="${_fwd_args//--batch/}"
   _fwd_args="$(echo "$_fwd_args" | xargs)"
   bash "${CLAUDE_PLUGIN_ROOT}/lib/bootstrap-orchestrate.sh" ${_fwd_args:-}
   ```
   The orchestrator iterates `working-repos.yaml`, normalizes paths, filters to on-disk repos, dispatches `Skill(coordinator:repo-setup)` non-interactively per repo, stamps coordinator currency, and emits the summary table.

3. **Hook-respect contract:** Per-repo commits run with the target repo's hooks (no `--no-verify`). A hook failure surfaces the repo as failed in the summary; overall exit non-zero.

4. **Idempotency:** A re-run on a fully-bootstrapped fleet emits per-repo "already current" rows and produces zero writes — the currency stamp short-circuits work.

## Summary table

After processing, the command emits:

```
=== /repo-setup --batch summary ===

  Succeeded:   N
  Failed:      N
  Skipped:     N   (non-git repos under --non-interactive)
  Not on disk: N

  Setup OK:
    OK  /path/to/repo-1

  Failed:
    XX  /path/to/repo-4

  /repo-setup --batch complete.
  Revert any setup commit: git -C <repo> revert HEAD
```

Exit codes: 0 on full success; 3 on any per-repo failure; non-zero with remediation on flag-rejection or precondition failure.

## Out-of-Scope

This command does NOT:
- Discover repos (delegates to `~/.claude/working-repos.yaml` — produced by `/setup`).
- Modify `~/.claude/working-repos.yaml` or any Wave-1 library file.
- Author handoffs, spinoffs, or session artifacts.
- Commit into `~/.claude` or any coordinator-managed repo (target-repo commits are made BY the per-repo setup, NOT by this command directly).
- Bypass target-repo commit hooks.

## Destructive-Action Prohibition

This command MUST NOT run `git reset`, `git rm`, `git push --force`, or any destructive git operation. All mutations are reversible: `git -C <repo> revert HEAD` in the target repo undoes the per-repo setup commit.

## Consolidation history

Replaces both `/project-onboarding` (single-repo deep) and `/bootstrap-repos` (fleet batch). See `docs/plans/2026-06-08-repo-setup-consolidation.md` for the consolidation rationale and the breaking-change CHANGELOG entry in `dist/publish-repo-toplevel/CHANGELOG.md`.
