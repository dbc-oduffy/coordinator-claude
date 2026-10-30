---
segment_id: plan-triage-and-exit
surface: plan
class: protected
order: 7
---

**Plan-surface additions to Branch B's classification rows.**

- **Artifact-shape tradeoff.** On a **refactor-over-patch** signal, surface a refactor proposal: refactor is the default when AI is the implementer — *"too big"* means genuinely complex, not merely large. _See `${CLAUDE_PLUGIN_ROOT}/snippets/em-operating-doctrine.md` § How to Decide._
- **Worker dispatch recommendations.** Eligible on plan reviews: `doc-link-checker`. `security-audit-worker` does NOT fire (needs runtime artifacts); a reviewer naming it on a plan is miscalibrated — surface to PM.

**Prior-art mutability and elevation.** Only a PM-authorized prior-art mutation deliverable lets the director-elevated reviewer override the prior-art-checker's `update-plan`/`update-prior-art` recommendation; the authorization phrase must appear verbatim in the dispatch brief or the integrator escalates it as ASK. Default: the plan adapts to prior art.

**Review-integration rung.** The moment all reviewer integration is complete, invoke (PowerShell hosts: Shape W) `& "$env:COORDINATOR_SETTINGS_HOME\bin\review-exec-auth-stamp.exe" mark-reviewed <plan-path>`. It flips `draft` → `reviewed` and writes nothing else (no `execution_authorized_*` field). A non-zero exit is a real refusal to investigate; an at-or-past source is an rc-0 no-op.

**Review exit — proceed and report.** When reviewer integration is complete, report that the plan is reviewed and integrated and PROCEED. Exactly two stops survive: (a) the plan carries candidate scope cuts, (b) the plan's next act is irreversible and external. Any third is a new question for the PM.

**The deferral slate rides with the scope-cut stop, argued not listed:** per candidate cut, the case for, the case against, and the EM's recommendation with confidence — never an ID list. Above n=4 cuts present buckets and a spinoff proposal; a grouping approval goes to the PM as its rows. Cut rows flip via `plan_tasks.mutate` only AFTER the PM rules.

**Precondition — land every plan-body edit the approval entails before closing any cut row through `plan_tasks.mutate`.** With a `grouping_approvals` frontmatter key: the approved `do` / `defer` / `ruled_out` grouping block(s) (`status: approved`, `approver`, `approved_at`, the PM's verbatim `pm_utterance`, membership `digest`), the plan-header `Status:` line and any final integration note. **Never author the `digest` yourself**; take it from (PowerShell hosts: Shape W, `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`)
`& "$env:COORDINATOR_SETTINGS_HOME\bin\plan-tasks-grouping-digest.exe" --plan <plan-path> --grouping do|defer|ruled_out --cut <id>:<disposition>[,<id>:<disposition>...]` — pass `--cut` for every row the PM's cut-set is closing (omitting it computes over the CURRENT membership, the wrong set). Printing a digest is not an approval; if you cannot obtain a computed value, leave the grouping `pending` and say so. (With no `grouping_approvals` key, the precondition is the legacy per-row `pm_approved:` flips in the `yaml plan-tasks` spine.)
Then `/handoff` (execution handoff) so a fresh session runs `/execute-plan` via `/pickup`. Same-session `/execute-plan` is the token-economics carve-out only — narrow, named-reason, never the default.
