## Batch Mode (--batch)

Batch mode runs fleet-wide setup non-interactively. Intended for PM use from `~/.claude` against all repos in the fleet.

**Driver:** delegates to `lib/bootstrap-orchestrate.py` for the per-repo loop (repointed to drive this consolidated skill in non-interactive mode — see C3a commit).

**Per-repo flow:**

1. Reads `~/.claude/working-repos.yaml`, normalizes paths, filters to repos on disk (repos not on disk are counted as `not-on-disk` in the summary table and skipped).
2. For each on-disk repo: dispatches the single-repo phases (Phase 1, 1.5, 3, 3g, 4) in non-interactive mode.
3. **SKIPS Phase 2 cold-asks.** Cold-asks are substituted by detected defaults from Phase 1's marker scan + Phase 1.5 substrate profile. When the target artifact already exists (e.g. `CLAUDE.md` present), lazy-creation discipline applies — no overwrite, no re-ask.

**Idempotency:** a re-run on a fully-bootstrapped fleet (all repos have `docs/coordinator-currency.yaml` matching current schema) exits 0 with per-repo "already current" rows and zero writes. The currency stamp is the load-bearing idempotency primitive — already-current stamps short-circuit Phase 3/3g for that repo.

**Hook-respect:** target-repo commit hooks run normally (no `--no-verify`); a hook failure surfaces the repo as failed and the overall run exits non-zero.

**Summary table** printed at end of run (columns: repo path / status / writes):

| Repo | Status | Notes |
|------|--------|-------|
| `/x/some-repo` | succeeded | currency stamp updated |
| `/x/other-repo` | already current | 0 writes |
| `/x/missing-repo` | not-on-disk | skipped |
| `/x/hook-fail-repo` | failed | post-commit hook exited non-zero |

Overall exit code: 0 if all on-disk repos succeeded or were already current; non-zero if any failed.

AC4, AC6, AC10 bind this section. AC9 binds the lib/detect-onboarding-offer.py emitting `/repo-setup` (single-repo form, no flags) — never `/repo-setup --batch` in the per-repo offer (batch mode is PM-from-~/.claude, not per-repo), and never with a `--refresh` flag (the command is idempotent; re-running `/repo-setup` on a stale repo re-stamps currency).
