<!-- Purpose: `--batch` entry-point mechanics — the fleet loop over `~/.claude/working-repos.yaml`.
     Its non-interactive posture is the `add-existing-project` lane's pre-answered behavior. -->

## Batch Mode (--batch)

Fleet-wide non-interactive setup, run by the PM from `~/.claude`.

**Driver:** `lib/bootstrap-orchestrate.py` runs the per-repo loop against this skill in
non-interactive mode.

**Per-repo flow:**

1. Reads `~/.claude/working-repos.yaml`, normalizes paths, filters to repos on disk (repos not on
   disk are counted `not-on-disk` in the summary table and skipped).
2. For each on-disk repo: runs the single-repo phases (1, 1.5, 3, 3g, 4) non-interactively with
   the `add-existing-project` lane's `round_trip_directives[]` and `terminal_offer_defaults[]`
   (`lanes/add-existing-project.yaml`). An existing target artifact is never overwritten or re-asked.

**Idempotency:** a re-run on a fully-bootstrapped fleet (every repo's
`docs/coordinator-currency.yaml` current) exits 0 with "already current" rows and zero writes.

**Hook-respect:** target-repo commit hooks run normally (no `--no-verify`); a hook failure
surfaces the repo as failed and the overall run exits non-zero.

**Summary table** at end of run (status: succeeded, already current, not-on-disk, failed):

| Repo | Status | Notes |
|------|--------|-------|
| `/x/some-repo` | succeeded | currency stamp updated |

Exit 0 if all on-disk repos succeeded or were already current;
non-zero if any failed.

**Per-repo offer invariant.** `lib/detect-onboarding-offer.py` emits plain `/repo-setup`, never
`--batch` and never `--refresh`.
