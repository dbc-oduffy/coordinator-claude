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
- **Commit shape:** default scoped commit via `ceremony.scoped_git_commit` (engine-repo; `paths`, `message`) — it selects the agree-case vs. private-index form for you; never `git add -A`/`.`. → `docs/wiki/scoped-safety-commits.md § The trailing pathspec is a proxy for scope, valid only while index and worktree agree`.
- **Archiving is automatic, not something this skill does.** The boot sweep (`fleet.archive_completed_handoffs`) and `/update-docs` Phase 8 close the loop on a clean chain by dispatching `handoff.archive_transition` via `cc_invoke.route_mutation`. The same op is reachable directly (seam-absent fallback for the ordinary chain-archival path) through `python3 "${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/handoff-archive-transition" chain "<predecessor-path>" --exclude "$HANDOFF_FILE"`. For a manual supersession park (a dead predecessor with a named successor), use the `supersede` verb per § Supersession — Genuine Dead-End above, never `chain`.
