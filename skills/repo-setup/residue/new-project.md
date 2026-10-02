<!-- Purpose: Judgment resolution for the `new-project` lane (greenfield). Mechanics:
     `mechanics.md`; canonical values: `lanes/new-project.yaml`. -->

# repo-setup — new-project lane

**Basis.** Caller supplies a project name and goal statement; no existing code to read.

**Phase 1.5 is skipped mechanically** (`p15.skip-gate-empty-repo`); `p15.ratification-ask` is
pre-answered `go-cold`. Every `round_trip` point is a caller-supplied or fixed value
(`lanes/new-project.yaml` `round_trip_directives[]`); no PM prompt fires.

**Terminal offers** default per `terminal_offer_defaults[]` — the Windows console-subprocess
tripwire installs by default.

**Roster.** Two ordered slots: `coordinator:goal-setting`, then the roadmap ceremony
(`roster_slots[]`).

**UNATTENDED-HALT SET applies unchanged** (`lanes/CONTRACT.md`).
