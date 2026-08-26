<!-- Purpose: Judgment resolution for the `new-project` lane (greenfield: name + goal statement,
     no existing code). Mutually-exclusive sibling of `add-existing-project.md` and
     `add-repo.md` — a single repo-setup invocation resolves exactly one lane. Lane-independent
     mechanical procedure lives in `mechanics.md`, not here; the canonical pre-answered values
     live in `lanes/new-project.yaml` — this file states the rationale for a human reading the
     flow, it is not a second copy of the data. -->

# repo-setup — new-project lane

**Basis.** Caller supplies a project name and a goal statement. No existing code, README, or
commit history for Phase 1.5 to read — the from-scratch case.

**Phase 1.5 is skipped mechanically** (`p15.skip-gate-empty-repo`) before its ratification
judgment point would ever fire; the lane still pre-answers `p15.ratification-ask` as `go-cold` for
completeness, per `lanes/new-project.yaml`.

**Every `round_trip` census point is pre-answered as a caller-supplied or fixed value** — see
`lanes/new-project.yaml` `round_trip_directives[]` for the six values and their resolution
rationale. No PM prompt fires under this lane: project name, type, and workstreams are op
parameters, not questions.

**Terminal offers** default per `lanes/new-project.yaml` `terminal_offer_defaults[]` — notably: the
Windows console-subprocess tripwire installs by default (establish the bash-free convention from
day one rather than waiting for a `*.sh` signal to accrete), and the CI reference defers until a
runnable test suite exists.

**Roster.** Two ordered slots: `coordinator:goal-setting` (immediate — the name+goal statement this
lane collects is the ceremony's own input), then the roadmap ceremony as it stands at execution
time (named generically since a sibling plan is mid-flight on where roadmap-planning ends). See
`lanes/new-project.yaml` `roster_slots[]`.

**UNATTENDED-HALT SET applies unchanged** — `p3j.1-test-cmd-detect`, `p3m.verify-reachability`,
`tw.windows-console-verify-run`, `batch.hook-respect` are never pre-answered by this lane, same as
every other lane; see `lanes/CONTRACT.md`.
