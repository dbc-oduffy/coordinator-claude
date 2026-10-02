<!-- Purpose: Judgment resolution for the `add-existing-project` lane (a repo built without
     coordinator). Mechanics: `mechanics.md`; canonical values: `lanes/add-existing-project.yaml`. -->

# repo-setup — add-existing-project lane

**Basis.** Existing code repo, no coordinator setup, classification `working`.

**Ratification accepts Phase 1.5's synthesis unattended.** `p15.ratification-ask` resolves
`ratify`; the proposed name, type and workstreams are trusted without a round-trip. When the
proposal differs from the Phase 1 `detected_type`, the proposal wins.

**Terminal offers with residual judgment:**

- **`p3f.untrack-scratch-offer`** — never auto-runs `git rm --cached`; declines and reports
  `Needs Attention`.
- **`p3f5.custom-hook-skip`** — installs the standard hook, but DEFERS (skip + `Needs Attention`)
  when a custom auto-push hook is already present.

**Roster.** One slot: `lanes/add-existing-project.yaml` `roster_slots[]`.

**UNATTENDED-HALT SET applies unchanged** (`lanes/CONTRACT.md`).
