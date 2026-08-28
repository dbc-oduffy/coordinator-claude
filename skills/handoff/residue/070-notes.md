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
- **Commit shape:** default scoped commit per `snippets/scoped-commit-route.md` — the agree-case vs. private-index form is selected for you from observed state; never `git add -A`/`.`. → `docs/wiki/scoped-safety-commits.md § The trailing pathspec is a proxy for scope, valid only while index and worktree agree`.
- **Archiving is not something this skill does — and right now nothing else does it either.** The boot sweep (`fleet.archive_completed_handoffs`) and `/update-docs` Phase 8 close the loop on a clean chain by dispatching `handoff.archive_transition` via `cc_invoke.route_mutation`. **That op is permanently suspended**, so those sweeps no-op and every direct route to it — `chain`, `supersede`, `baton-assemble apply`'s `d6` — fails `-32006`. Expect claimed predecessors to accumulate un-archived until a replacement exists; that backlog is a known state, not evidence you did the handoff wrong. Hand-stamp the flip per § Supersession — Genuine Dead-End above, and do not invent a private archival convention to fill the gap.
