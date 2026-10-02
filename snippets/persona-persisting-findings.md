<!-- canonical source for persona-persisting-findings — edit here, then run bin/verify-snippet-sync persona-persisting-findings --fix -->
<!-- consumers: see bin/snippet-registry list-consumers persona-persisting-findings -->

<!-- BEGIN persona-persisting-findings (synced from snippets/persona-persisting-findings.md) -->
## Persisting your findings (the easy path)

Your deliverable is a **file on disk**, not inline text — the harness blocks the `Write` tool on report files. Which mechanism applies depends on the deliverable:

- **Plan/design document** — persist to its `docs/plans/...` path from your brief via a **Bash shell redirect** as your final action, then return only a pointer line. Full procedure: `snippets/findings-self-persist-bash.md`.
- **Apply every finding in place, nits included, then write the ledger** — a finding worth naming is worth making; never leave one as a suggestion. Use **Edit** on the reviewed artifact itself to land every finding, then use **Edit** on the file named by the `sidecar_path: <path>` line in your dispatch context (the brief may repeat it) to write your full `ReviewOutput` JSON + narrative plus a `## Findings Ledger` block there as your final action, then return only a pointer line (`DONE: <sidecar-path> | verdict: <OK|WARN|BLOCKED> | findings: <N>`). That line is either an ordinary offer or, after "Sidecar provisioning missed", a sentinel scaffold: edit that file in both cases, and say in your findings that provisioning missed when it did; for a named teammate, follow the miss notice in your dispatch context. The sidecar's ledger is the record the engine's `review-findings-ledger verify` checks: a repo-convention review file (`docs/reviews/…` and the like) may be written *as well*, never *instead*. Only a context carrying no `sidecar_path:` line may return inline, and never quietly: say plainly, in your first line, that provisioning missed and no sidecar path was supplied, then return the findings inline — a named dispatch's return text may never reach the dispatcher, so an unflagged return vanishes silently. The Bash-redirect recipe below is for the plan/design case, not this one. Edit your existing sidecar, never a Bash redirect: that hook fails closed on governed filenames quoted in prose (`Write` on a sidecar you have already read is equivalent).

Short version (plan/design path only — a plan/design target typically does not exist yet, so a redirect creates it; a review-findings sidecar already exists, so use Edit above instead):
1. Choose the target path — a plan/design goes to its `docs/plans/...` path from your brief.
2. Write the full content there via a Bash redirect (`python3 -c "import pathlib; pathlib.Path('<target>').write_text(..., encoding='utf-8')"` for content with quotes/backticks; `printf ... > <target>` for simple content).
3. `ls -l <target>` to confirm it is non-empty.
4. Return only a pointer line (e.g. `DONE: <path> | verdict: <...>`), not the body.

You have Read/Write/Edit/Bash and there is no tool-confinement in your way — you are trusted to review and return. The EM reads your applied edits and your findings ledger from the file, not from chat.
<!-- END persona-persisting-findings -->
