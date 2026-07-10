# DoE Altitude and Shared-Infra Consults

> Methodology for cross-repo doctrine and shared-infra boundary questions. PM-facilitated multi-EM consult chain with the DoE Claude in `~/.claude` and project-EM Claudes in sibling repos. Evidence base at time of writing: 1 instance (2026-05-19 whoami-sentinel consult). Treat the shape as provisional — validate on next case before locking.

## When DoE altitude is the right intervention

The DoE Claude (working in the `~/.claude` meta-repo) has structural visibility into all sibling repos, ownership of the coordinator plugin and global CLAUDE.md, and authority to shape cross-repo doctrine. Most engineering work does NOT need DoE involvement — project-EMs settle their own implementation, dispatch their own reviewers, ship their own work. The DoE steps in only when the question has *radius* beyond a single project.

Routing signals — DoE-altitude question when ≥1 of:

- **Shared infra is in play.** Multiple plugins/repos consume the same artifact (sentinel file, MCP tool, hookimpl chain, schema version). The boundary question affects every consumer, not just the one raising it.
- **Cross-project writer-boundaries.** "Who owns this file?" / "Should MCP write to plugin-local dirs?" / "Does this field belong on the host or the addon?" — questions where the answer changes which repo's EM owns the followup.
- **Doctrine evolution.** Adding/changing a rule in global CLAUDE.md, the coordinator plugin, or a wiki that ≥2 repos cite. Project-level wiki changes stay project-level; cross-cutting wiki changes route through DoE.
- **Multi-EM disagreement.** Two project-EMs reach incompatible conclusions on a shared interface. Neither has standing to settle for the other. DoE arbitrates.
- **PM-initiated shared-infra ask.** PM raises a question that touches multiple repos and would force the project-EM to speculate about siblings they can't see.

When NONE of these apply, the project-EM owns it. DoE doesn't review project-internal code, doesn't pick implementation details, doesn't dispatch project-level reviewers. The altitude is doctrinal and structural, not tactical.

**Applied at the roadmap-planning review gates.** When a roadmap *sets cross-repo or cross-team boundaries* (a sibling-consumed contract/interface, ≥2-repo `scope:`, a non-trivial `peer-team-asks` ask, or a cross-repo coordination/ownership/version-cutover COORDINATOR-RESOLUTION), the **primary rigor reviewer** at `coordinator:roadmap-planning` Step 1.5.5 (OVERVIEW) and Step 2.8 (stub set) is **the Director of Engineering (`coordinator:eng-director`), not the Staff Engineer** — drawing the cross-repo boundary is DoE-altitude authority an EM-altitude reviewer structurally lacks. The Staff Engineer may still run as the second/backstop reviewer. See `skills/roadmap-planning/SKILL.md` § "Primary rigor-reviewer selection by altitude".

## What `~/.claude` is — three delivery directions for any item under it

`~/.claude/` is itself a git checkout (remote `dbc-oduffy/.claude-prime`, a private dotfiles repo) — not a loose pile of operator-local files. Any audit of `~/.claude` substrate that asks "is there a writer for this file?" is asking the wrong question: every tracked item already has a delivery owner. The right question for any item under `~/.claude/` is **which of three delivery directions owns it:**

1. **Coordinator-plugin percolation** — ships outward to consumer repos / OSS via `setup/publish.sh`. (Plugin source under `plugins/coordinator-claude/`, bundled wikis, agent prompts, hooks.)
2. **Claude Prime dotfiles publication** — shipped via `git push` to the private dotfiles remote. (CONTEXT.md, top-level `agents/`, `docs/`, machine-agnostic config.)
3. **Operator-local-by-design** — gitignored, never shipped. (`machine-local/`, session transcripts, per-machine secrets.)

Before classifying anything under `~/.claude/` as an orphan, `cd ~/.claude && git remote -v` + `git ls-files <path>`. The migration question for a candidate is usually "should this move from direction (2) to direction (1)?" — i.e. ship via the coordinator installer rather than a Claude Prime clone — not "does this have a writer?" *(Canonical mis-frame: a 2026-05-21 surface-coverage audit classified tracked Prime files as ORPHAN-RISK, costing ~2h of wrong-shape work before the geometry was corrected.)*

## The consult-chain methodology

PM-facilitated, not EM-initiated. A project-EM observing a shared-infra question surfaces it; the PM relays to the DoE; the DoE pre-commits a position; the PM relays back to the relevant project-EM(s) for pushback or concurrence. The DoE synthesizes the final shape.

**Why PM-facilitated and not direct EM-to-EM:** project-EM Claudes don't share session context. The PM is the only persistent voice across sessions. Direct EM-to-EM messages would lose context on each hop; PM relay preserves intent and lets the human gate any cross-repo doctrine that escapes.

### Phases

1. **Surface.** A project-EM identifies a shared-infra question and notes it (memo, handoff, inline ask). Marker: the question's resolution would force the EM to speculate about a sibling repo or to set a precedent the EM doesn't have standing to set alone.

2. **PM relay to DoE.** PM hands the question to the DoE Claude in `~/.claude`. Include the originating EM's framing — DoE should see what the EM said, not a paraphrase.

3. **DoE pre-commits a position.** Before consulting other EMs, the DoE states a clear technical position with reasoning. *"I think we should X because Y"* beats *"X or Z, what do you think?"* The pre-commit gives the consulted EMs something specific to push back on, which converges faster than open-ended debate.

4. **PM relay to project-EM(s).** PM forwards the DoE position to the relevant project-EM(s) — host EM, addon EM, etc. Each EM answers the questions only they can answer (their tool contracts, their incident history, their writer-set policy).

5. **DoE synthesizes.** DoE reads replies, identifies which questions are now settled, which remain open, and what the doctrine shape should be. Credits voices: which leg of the doctrine came from which EM. Provenance attribution matters more for shared-infra than for single-plugin doctrine — future readers need to see this was multi-voice consensus, not DoE fiat, or the doctrine reads like top-down imposition and gets quietly worked around.

6. **Codify.** If the shape is stable, DoE writes (or updates) the wiki / coordinator doctrine / global CLAUDE.md. Memos themselves are not preserved long-term — the wiki is the durable artifact. Cite the originating consult date so future readers can find context via `git log` if needed.

### Convergence properties

- **Pre-committing a position narrows the search space.** Without it, each consulted EM speculates broadly and the DoE has to reconcile divergent framings. With it, each EM either concurs or surfaces a specific gap.
- **Asymmetric authority converges faster than symmetric debate.** The DoE has standing to settle questions the EMs don't; trying to reach consensus across peers without an arbiter is the slow path.
- **Provenance crediting closes the loop.** Naming which EM contributed which leg makes the doctrine feel earned by the consult rather than imposed afterward.

## Canonical worked example: the whoami-sentinel consult (2026-05-19)

**Question raised:** example-game-repo-control EM, while shipping the addon health sentinel (`doctor-last-run.json`), flagged a separable-but-related shape — should plugins also ship a `whoami.json` for identity surfacing (consumer project, daemon PID, schema version, build SHA)?

**Why this needed DoE altitude:** the proposal touched three repos (example-game-workbench-repo, project-rag host, project-rag-ue-addon), the writer-boundary question ("can MCP servers write plugin-local data dirs?") had no single-EM answer, and the resolution would set a precedent for every future plugin sentinel.

**Consult chain shape:**
- example-game-repo EM surfaced the proposal with a recommendation (defer until incident).
- DoE pre-committed: defer on principle (*identity is runtime state with a live source; don't persist what you can query*), not on incident-absence.
- project-rag host EM concurred, sharpened the writer-boundary articulation (**"doctor writes, scanner reads, MCP answers live"**), and surfaced the inversion failure mode that made it load-bearing (a fresh MCP restart silently overwriting a doctor RED with a green-on-paper "I just started up").
- DoE synthesized the underlying decay-discipline principle (persistent = receipt semantics where stale = signal; live = truth semantics where current = answer; scanner = no-side-effects bridge) that ties the three legs together.
- project-rag-ue-addon EM consulted last, with most questions pre-answered — kept the consult lean.

**Outcome:** doctrine codified at `docs/wiki/plugin-identity-and-health-sentinels.md`. Decision shape: **receipt-on-disk, identity-via-MCP, deliberate non-merger.** Revisit only on a concrete incident the three-surface layout couldn't catch.

**What made it work:**
- Pre-committed DoE position gave EMs something specific to push back on.
- Each EM answered only questions they had standing to answer.
- Provenance attribution credited example-game-repo (problem identification + receipt-stale-as-signal property), host (writer-boundary articulation + inversion failure mode), and DoE (decay-discipline framing).
- Memos were the working medium; the wiki is the durable artifact.

## What NOT to do

- **Don't escalate within-project decisions to DoE.** If the question doesn't have radius to ≥2 repos, the project-EM owns it. DoE involvement on tactical project work is altitude-violation in the other direction.
- **Don't bypass the PM relay for direct EM-to-EM messaging on doctrine.** SendMessage between project-EM agents in a single session is fine for collaborative work *within* a consult phase; the cross-phase relay belongs to the PM so the human can gate doctrine that escapes.
- **Don't preserve the working memos as durable artifacts.** They served the consult; the wiki is what future readers find. Memo proliferation is its own anti-pattern.
- **Don't codify single-instance shapes as fixed doctrine.** This wiki itself is single-instance — the methodology is provisional until validated on a second case.

## Surface for prior-art-checker

When a plan touches shared infrastructure (sentinel files, MCP tools consumed across plugins, hookimpl chains, cross-repo schemas), the prior-art-checker should surface this wiki as **Compatible-but-relevant** — not because the plan will conflict, but because the methodology for *how to decide* such questions is the prior art, even when the specific decision is new.

Trigger keywords for cross-reference: shared infra, plugin-local data dir, sentinel file, MCP writer boundary, cross-plugin scanner, decay model, receipt-vs-status, host-vs-addon ownership, writer set, who-writes-what.

## Evidence base and revisit cadence

- **Instance 1:** 2026-05-19 whoami-sentinel consult (this wiki's worked example).
- **Instance 2:** 2026-05-19 cross-plugin whoami contract consult (this wiki + `cross-plugin-whoami-contract.md`). Shape: pre-committed DoE position ("host-owned, wait for #3") was corrected mid-consult by PM-surfaced empirical evidence (instance #2 already exists in wrong-shape arrangement → revised to coordinator-owned). Validates the methodology while also exercising the "DoE pre-commits, then revises on EM/PM evidence" sub-pattern. Methodology held; addition: pre-committed DoE positions are themselves revisable on empirical evidence, not just on EM/PM objections.
- **Promote to coordinator doctrine when stable.** Three consistent instances → the methodology graduates from "wiki-documented pattern" to "coordinator skill or CLAUDE.md section". Until then, this wiki is the canonical reference and the global CLAUDE.md carries only the single-line pointer.
