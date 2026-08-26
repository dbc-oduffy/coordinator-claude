<!-- Purpose: Judgment resolution for the `add-existing-project` lane (a repo built without
     coordinator: real code, README, commit history for Phase 1.5 to synthesize from). Mutually-
     exclusive sibling of `new-project.md` and `add-repo.md`. Lane-independent mechanical
     procedure lives in `mechanics.md`; canonical pre-answered values live in
     `lanes/add-existing-project.yaml` — this file states rationale, not a second data copy. -->

# repo-setup — add-existing-project lane

**Basis.** Existing code repo, no coordinator setup present, classification answer `working`
(the "add repo" thin door — see `add-repo.md` — is the lane for registration-only,
`published-artifact` classification instead).

**Ratification accepts Phase 1.5's synthesis unattended.** `p15.ratification-ask` resolves
`ratify`: the Phase 1.5 substrate read (README, CLAUDE.md, lessons, recent handoffs, sibling
`stack_tags`) produces a proposed project name, type, and workstream set, and this lane trusts that
proposal without a confirmation round-trip — see `lanes/add-existing-project.yaml`
`round_trip_directives[]` for the full derivation chain (name/type/workstreams all read
"suppressed by the ratify answer above").

**Reconciliation on conflict.** When the Phase 1.5 proposal differs from the Phase 1 marker-scan
`detected_type`, the proposal wins — the reconciled value is what gets ratified, not a re-ask.

**Every `round_trip` point is pre-answered** per `lanes/add-existing-project.yaml`; the
`tw.ci-inference-prompt` answer is conditional on whether `tw.ci-eligibility-resolve`'s inferred
signal actually fired (never auto-`yes` absent a fired signal).

**Terminal offers with genuine residual judgment** (see `lanes/add-existing-project.yaml`
`terminal_offer_defaults[]` for every value; two carry judgment this lane cannot manufacture a
policy for):

- **`p3f.untrack-scratch-offer`** — never auto-runs `git rm --cached`; this lane declines and
  reports `Needs Attention` rather than guessing PM intent on tracked scratch content.
- **`p3f5.custom-hook-skip`** — installs the standard hook by default, but DEFERS (skip + report
  `Needs Attention`) when a custom auto-push hook is already present, rather than either
  overwriting it or fabricating a sign-off this lane cannot obtain unattended. The sign-off itself
  is the judgment the census names; a policy default cannot manufacture one.

**Roster.** One slot, contents settled by the brownfield-onboarding-roster panel output — this
lane names the slot shape only; see `lanes/add-existing-project.yaml` `roster_slots[]`.

**UNATTENDED-HALT SET applies unchanged** — `p3j.1-test-cmd-detect`, `p3m.verify-reachability`,
`tw.windows-console-verify-run`, `batch.hook-respect` are never pre-answered by this lane, same as
every other lane; see `lanes/CONTRACT.md`.
