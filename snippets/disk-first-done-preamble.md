<!-- SCOPE: for EDIT-deliverable dispatches (executor edits code, integrator patches a file) AND
     findings/report/audit agents with scaffold-Bash or a pre-scaffolded sentinel — those agents
     self-persist via Bash-redirect (→ snippets/findings-self-persist-bash.md) and DO need this
     DONE gate. Do NOT append for residual EM-persist cases: (1) runtime-only-fact capture;
     (2) findings agents dispatched with neither scaffold-Bash nor a pre-scaffolded sentinel —
     those return inline and the EM persists on receipt.
     → CLAUDE.md § Scouts and Disk-First Verification.
     EM-side dispatch payload. Append this verbatim to the END of any scout/executor/findings-agent
     prompt whose deliverable is a file on disk. The disk-first DONE gate is a
     load-bearing anti-hallucination guard (~30% Haiku / ~10% Sonnet under load
     hallucinate TEXT-ONLY and dump inline). Pointed-to from CLAUDE.md
     § Scouts and Disk-First Verification. -->

Reply with `DONE: <path>` ONLY after you have confirmed the file exists at the path above (Read or `ls`). If you're about to summarize the deliverable inline, STOP — the coordinator reads from disk, not chat. Inline summary without a written file counts as task failure.
