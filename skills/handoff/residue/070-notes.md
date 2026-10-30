---
segment_id: notes
case: shared
class: droppable
order: 70
---

## Notes

- Keep it concise: in-progress work, blockers, uncommitted changes — not what MEMORY.md holds.
- PM arguments (e.g., `/handoff focus on auth refactor`) go into `## In-Progress Work` and `## Recommended Next Steps`.
- **A Claude Code restart is a session boundary.** An MCP-bridge restart, runtime rebuild, or `/reload-plugins` between edit and verification means `/handoff` BEFORE it.
- **Cross-repo communication is not a handoff use-case.** Route it via the PM as relay or `cross-repo-memo`.
- **Commit shape:** scoped commit per `snippets/scoped-commit-route.md`; never `git add -A`/`.`.
- **Archiving is not done by hand.** `d6` archives the predecessor at apply time (`housekeeping.cycle` via `cc_invoke.route_mutation`); anything else terminal is swept by the closing session's `sweep-terminal-handoffs` run — stamp `deployment_state` and a resolvable `shipped_in`, then drain. `handoff.archive_transition` is permanently dead (`-32006`).
