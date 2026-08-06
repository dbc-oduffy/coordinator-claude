<!-- Not vestigial: reviewer/persona agents no longer use this mechanism (they Edit a
     pre-provisioned state/subagent-share/<session-id>/<provision_key>.md path instead). This
     snippet's one remaining live role is the general findings-deliverable EM-persist fallback
     for a no-Bash / Write-blocked findings agent (any agent, not just reviewers) that cannot
     self-persist and is handed a pre-scaffolded sentinel to Edit. -->

<!-- WHEN TO USE: self-scaffolding findings-agents whose deliverable is a
     structured findings sidecar confined to state/review-trail/findings/ -- i.e., agents that
     scaffold their own sidecar path (via coordinator-doc-new) and inject their entire findings
     body via a single Edit on the sentinel line. NOT reviewer/persona agents proper -- those are
     auto-provisioned a state/subagent-share/<session-id>/<provision_key>.md sidecar at spawn and
     are routed through snippets/persona-persisting-findings.md instead (see the "Not vestigial"
     note above). For worker/scout/auditor agents that produce a freeform report file, see
     findings-self-persist-bash.md instead. -->

<!--
  Purpose: scaffold-then-Edit pattern for findings-agents that must persist their
  deliverable to a sidecar on disk instead of returning inline. The Claude Code harness BLOCKS
  subagent report-file Writes; this mechanism sidesteps the block by Editing a pre-scaffolded
  confined file rather than Writing a fresh one.
  Negative-spec (Mode A only): there is no EM-injected sidecar path; the agent ALWAYS scaffolds
  its own sidecar in state/review-trail/findings/ via coordinator-doc-new. Mode B (claim-marker
  ceremony + agent-id .allow files) is retired. Confinement is state/review-trail/findings/ only.
-->

## HARD RULE: Scaffold first (if needed), read everything, Edit last

Your deliverable is a **sidecar file on disk**, not inline text. Persist it via a single Edit
as your final action. The harness blocks subagent `Write` calls on report files; `Edit` on a
pre-existing scaffolded file is the blessed sidestep.

**Three-phase action sequence -- no exceptions:**

1. **SCAFFOLD** your own sidecar:
   Run `coordinator-doc-new --type review-findings --slice <id> --scope <comma-paths>` and
   capture the path it prints. The file lands at `state/review-trail/findings/<slice>.md`
   with a `<!-- FINDINGS -->` sentinel already in place. This is your only permitted Bash call
   (confined by an engine-side guard that allowlists this exact command and hard-denies
   everything else). The EM never pre-scaffolds this
   file; you always scaffold it yourself so "where you were told to write" and "where
   confinement allows" are the same directory.

2. **READ AND REASON** across the full artifact under review. Use Read, Grep, Glob freely.
   Do not Edit during this phase.

3. **SINGLE EDIT -- LAST**: Replace the `<!-- FINDINGS -->` sentinel with your complete findings
   body. This is the final tool call. No partial Edits, no draft Edits, no second Edit.
   The sentinel is a one-shot injection point; two Edits corrupt the replacement.

**Why Edit sidesteps the harness block:** `Edit` operates on a pre-existing confined file, not
a fresh path -- the harness permits it. `Write` would create a new file and is blocked.
`Edit` also cannot create a file; if the scaffold step is skipped and the file is absent,
Edit fails loudly -- the correct failure mode.

**Do not fall back to a Bash heredoc/redirect for this Edit, even when Bash is available to
you.** A Bash payload that persists findings quoting a governed doctrine surface's filename in
its own prose (e.g. a finding *about* `coordinator/snippets/em-operating-doctrine.md`) can be
denied by `guard-doctrine-surface-bash-write.py` as a false positive: that hook cannot tell "a
governed filename appears as prose inside the content you are writing" from "a governed
filename is the write's actual destination", and fails closed on the ambiguity by design. Edit
on your pre-provisioned sidecar sidesteps this entirely -- it targets your real destination file
directly and never goes through that hook's Bash-command classification. If you ever find
yourself reaching for a Bash heredoc to persist a findings sidecar that already exists, that is
the wrong tool for this job; use Edit instead. (This is the self-scaffolding-findings-agent copy of
this guidance — `snippets/persona-persisting-findings.md` carries a parallel copy for the
reviewer/persona-agent audience that this file's header says no longer uses this mechanism.)

**Discipline (not a guard):** the Edit write-sandbox confinement was
removed — nothing structurally blocks an Edit outside `state/review-trail/findings/` anymore. You
MUST still write ONLY your sidecar there; editing any other path is a contract violation. Your Bash
remains allowlist-confined by that same engine-side guard, so a stray edit cannot be
committed — it stays in the working tree for the EM's `git diff`.

**Output contract -- return a pointer line only:**

```
DONE: <sidecar-path> | verdict: <OK|WARN|BLOCKED> | findings: <N>
```

Do not return your findings body inline. The EM reads findings from the sidecar on disk.

<!-- See also: findings-self-persist-bash.md (Bash-redirect persistence for worker/scout/auditor agents) -->
