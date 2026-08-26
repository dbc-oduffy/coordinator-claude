<!-- Purpose: Judgment resolution for the `add-repo` lane (the thin door: registration-only, no
     full onboarding). Mutually-exclusive sibling of `new-project.md` and
     `add-existing-project.md`. Canonical pre-answered values live in `lanes/add-repo.yaml`. -->

# repo-setup — add-repo lane

**Basis.** Register a repo as an addressable fleet peer without running full onboarding.
`p1.repo-classification-ask` resolves `published-artifact (b)`, which halts the flow at
`p1.classification-branch-b-stop` before Phase 1.5/2/3 ever run — the material difference from
`add-existing-project.md`, which resolves `(a) working` and runs the full spine. The two lanes are
deliberately NOT collapsed: they differ on the classification answer and on the
`p3x.memo-destination-offer` default below.

**Every other `round_trip` point and terminal offer is declared "not reached"** for AC-completeness
only — the classification halt means none of them fire under this lane's own answer; see
`lanes/add-repo.yaml` for the full per-point declaration.

**The one reachable terminal offer differs from `add-existing-project`'s default.**
`p3x.memo-destination-offer` resolves `no` here (vs. `yes` for working repos) — a thin-door
registration is not yet a fully addressable fleet peer, so the default doesn't push it toward one.

**Roster.** Empty — the thin door registers only, no follow-on onboarding roster; see
`lanes/add-repo.yaml` `roster_slots: []`.
