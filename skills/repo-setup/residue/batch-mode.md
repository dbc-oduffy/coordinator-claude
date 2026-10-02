<!-- Purpose: `--batch` entry-point mechanics — the fleet loop over `~/.claude/working-repos.yaml`.
     Its non-interactive posture is the `add-existing-project` lane's pre-answered behavior. -->

## Batch Mode (--batch)

Fleet-wide non-interactive setup, run by the PM from `~/.claude`.

**Driver:** `lib/bootstrap-orchestrate.py` runs the per-repo loop against this skill in
non-interactive mode.

**Per-repo flow:**

1. Reads `~/.claude/working-repos.yaml`, normalizes paths, filters to repos on disk (repos not on
   disk are counted `not-on-disk` in the summary table and skipped).
2. For each on-disk repo: dispatches the single-repo phases (Phase 1, 1.5, 3, 3g, 4)
   non-interactively with the `add-existing-project` lane's `round_trip_directives[]` and
   `terminal_offer_defaults[]` (`lanes/add-existing-project.yaml`). An existing target artifact
   (e.g. `CLAUDE.md`) is never overwritten or re-asked.

**Idempotency:** a re-run on a fully-bootstrapped fleet (all repos have
`docs/coordinator-currency.yaml` matching current schema) exits 0 with per-repo "already current"
rows and zero writes; the currency stamp short-circuits Phase 3/3g.

**Hook-respect:** target-repo commit hooks run normally (no `--no-verify`); a hook failure
surfaces the repo as failed and the overall run exits non-zero.

**Summary table** printed at end of run (columns: repo path / status / notes):

| Repo | Status | Notes |
|------|--------|-------|
| `/x/some-repo` | succeeded | currency stamp updated |
| `/x/other-repo` | already current | 0 writes |
| `/x/missing-repo` | not-on-disk | skipped |
| `/x/hook-fail-repo` | failed | post-commit hook exited non-zero |

Overall exit code: 0 if all on-disk repos succeeded or were already current; non-zero if any
failed.

**Per-repo offer invariant.** `lib/detect-onboarding-offer.py` emits plain `/repo-setup`, never
`--batch` and never `--refresh`.
