<!-- Purpose: Judgment resolution for the `add-repo` lane (thin door: registration-only).
     Canonical values: `lanes/add-repo.yaml`. -->

# repo-setup — add-repo lane

**Basis.** Register a repo as a fleet peer without full onboarding.
`p1.repo-classification-ask` resolves `published-artifact (b)`, halting at
`p1.classification-branch-b-stop` before Phase 1.5/2/3. Every other `round_trip` point and
terminal offer is "not reached" (see `lanes/add-repo.yaml`).

**`p3x.memo-destination-offer` resolves `no`** (`yes` for working repos).

**Roster.** Empty.
