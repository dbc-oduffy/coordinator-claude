---
segment_id: plan-triage-and-exit
surface: plan
class: protected
order: 7
---

**Plan-surface additions to Branch B's classification rows** (the rows themselves are in the core;
only what is plan-specific is stated here).

- **Artifact-shape tradeoff.** Most plan findings are about *what to build*, not *how it's coded*, so this row carries the bulk of them. On a **refactor-over-patch** signal, surface a refactor proposal: refactor is the default when AI is the implementer, since a critical rewrite is often an afternoon rather than a quarter — *"too big"* means genuinely complex, not merely large. _See `${CLAUDE_PLUGIN_ROOT}/snippets/em-operating-doctrine.md` § How to Decide._
- **Worker dispatch recommendations.** Eligible on plan reviews: `doc-link-checker` (most relevant); `dep-cve-auditor` (if the plan introduces a dependency). `test-evidence-parser` and `security-audit-worker` do NOT fire — they require runtime artifacts; a reviewer naming them on a plan is miscalibration, surface it to PM.

**Prior-Art Mutability and Reviewer Elevation**

**Prior-art mutability and elevation.** Only when the PM authorizes prior-art mutation as an explicit deliverable may the director-elevated reviewer override the prior-art-checker's `update-plan`/`update-prior-art` recommendation; the exact authorization phrase must appear verbatim in the dispatch brief or the integrator escalates the override as ASK. Default: the plan adapts to prior art.

**Review-integration rung.** The moment all reviewer integration is complete, invoke (PowerShell hosts: Shape W) `& "$env:COORDINATOR_SETTINGS_HOME\bin\review-exec-auth-stamp.exe" mark-reviewed <plan-path>`. It flips `draft` → `reviewed` and writes nothing else; no `execution_authorized_*` field, because a reviewed plan is explicitly not an authorized one. `reviewed` records that review integration landed, and nothing more. A non-zero exit is a real refusal to investigate; an at-or-past source is an rc-0 no-op.

**Review exit — proceed and report.** When reviewer integration is complete, report that the plan is reviewed and integrated and PROCEED. Exactly two stops survive: (a) the plan carries candidate scope cuts, and (b) the plan's next act is irreversible and external. A third exception is a new question for the PM, not an EM judgment call.

**The deferral slate rides with the scope-cut stop, argued not listed:** per candidate cut (rows `open` with `case_against`, or already `backlogged`/`wont_do`), the case for, the case against, and the EM's recommendation with confidence — never an ID list. Above n=4 cuts present buckets and a spinoff proposal; a grouping approval goes to the PM as its rows. Candidate-cut rows flip via `plan_tasks.mutate` only AFTER the PM rules.

**Precondition — land every plan-body edit the approval entails before closing any cut row through `plan_tasks.mutate`.** On a plan whose frontmatter carries a `grouping_approvals` key, that means the `do` / `defer` / `ruled_out` grouping block(s) the PM just approved: `status: approved`, the `approver`, `approved_at`, the PM's verbatim `pm_utterance`, and the membership `digest` for that grouping — plus the plan-header `Status:` line and any final integration note. **Never author the `digest` yourself** — it is a mechanical sha256 over the grouping's membership set; a plausible-looking value binds the approval to a cut-set nobody approved. Take it from (POSIX-host form; PowerShell hosts: Shape W, `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`)
`& "$env:COORDINATOR_SETTINGS_HOME\bin\plan-tasks-grouping-digest.exe" --plan <plan-path> --grouping do|defer|ruled_out --cut <id>:<disposition>[,<id>:<disposition>...]` — it prints the digest over the membership the cut-set produces. Pass `--cut` for every row the PM's cut-set is closing (with its target disposition); omitting `--cut` computes over the grouping's CURRENT membership instead, which is the wrong set for a fresh approval — see the precondition above. The tool is read-only; printing a digest is not an approval. If you cannot obtain a computed value, leave the grouping `pending` and say so. (With no `grouping_approvals` key, the equivalent precondition is the legacy per-row `pm_approved:` flips in the `yaml plan-tasks` spine.)
Then `/handoff` (execution handoff) so a fresh session runs `/execute-plan`. Same-session `/execute-plan` is the token-economics carve-out only — narrow, named-reason, never the default. The EM owns the dispatch-gate graph only when executing same-session (carve-out); the default handoff path hands it to the fresh session picking up via `/pickup` → `/execute-plan`.
