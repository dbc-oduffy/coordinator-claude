---
segment_id: batch-mode
class: protected
order: 4
situation: batch
---
<!-- Purpose: `--batch` entry-point mechanics — the fleet loop over `~/.claude/working-repos.yaml`.
     Its non-interactive posture is the `add-existing-project` lane's pre-answered behavior. -->

## Batch Mode (--batch)

Fleet-wide non-interactive setup, run by the PM from `~/.claude`.

**Driver:** `lib/bootstrap-orchestrate.py` loops per repo against this skill, non-interactive.

**Per-repo flow:**

1. Read `~/.claude/working-repos.yaml`, normalize paths, filter to repos on disk (repos not on
   disk are counted `not-on-disk` in the summary table and skipped).
2. Per on-disk repo: run the single-repo phases (1, 1.5, 3, 3g, 4) with the `add-existing-project`
   lane's `round_trip_directives[]` and `terminal_offer_defaults[]`. An existing target artifact is never overwritten or re-asked.

**Idempotency:** a re-run on a fully-bootstrapped fleet (every repo's
`docs/coordinator-currency.yaml` current) exits 0 with "already current" rows and zero writes.

**Hook-respect:** target-repo commit hooks run normally (no `--no-verify`); a hook failure
marks the repo failed and the run exits non-zero.

**Summary table** (status: succeeded, already current, not-on-disk, failed); exit 0 unless a repo failed:

| Repo | Status | Notes |
|------|--------|-------|
| `/x/some-repo` | succeeded | currency stamp updated |

`lib/detect-onboarding-offer.py` emits plain `/repo-setup`, never `--batch` or `--refresh`.
