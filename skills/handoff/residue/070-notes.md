---
segment_id: notes
case: shared
class: droppable
order: 70
---

## Notes

- Keep it concise. Focus on state that MEMORY.md doesn't capture: in-progress work, blockers, uncommitted changes.
- If the PM provides arguments (e.g., `/handoff focus on auth refactor`), incorporate that context into `## In-Progress Work` and `## Recommended Next Steps`.
- **A Claude Code restart is a session boundary, not a step within a session.** If your workflow needs an MCP-bridge restart, a runtime artifact rebuild, or a `/reload-plugins` between code-edit and verification, run `/handoff` BEFORE the restart, not after.
- **Cross-repo communication is not a handoff use-case.** Route it via the PM as relay or `cross-repo-memo`.
- **Commit shape:** default scoped commit per `snippets/scoped-commit-route.md` — the agree-case vs. private-index form is selected for you from observed state; never `git add -A`/`.`. → `${CLAUDE_PLUGIN_ROOT}/docs/wiki/scoped-safety-commits.md § The trailing pathspec is a proxy for scope, valid only while index and worktree agree`.
- **Archiving is not something this skill body does by hand — the apply path already did it.** `/workday-complete`'s `handoff-housekeeping` directive (`housekeeping.cycle` via `cc_invoke.route_mutation`) archives everything terminal in one batch, and `chain` / `supersede` / `baton-assemble apply`'s `d6` all route through the same op. The old key `handoff.archive_transition` is permanently dead; a call still naming it fails `-32006`, and `session.boot_sweep` dispatches no op at all. So a predecessor this skill wrote a successor for is archived by `d6` at apply time; anything else terminal is swept by the closing session's own `sweep-terminal-handoffs` run, NOT left for the next ceremony — stamp `deployment_state` and a resolvable `shipped_in`, then drain. Do not invent a private archival convention, and do not author a second sweep on the belief none exists. → `${CLAUDE_PLUGIN_ROOT}/docs/wiki/coordinator-tripwires/terminal-batons-are-swept-at-close-not-left-to-the-next-ceremony.md`
