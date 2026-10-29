<!-- canonical source for persona-persisting-findings — edit here, then run bin/verify-snippet-sync persona-persisting-findings --fix -->
<!-- consumers: see bin/snippet-registry list-consumers persona-persisting-findings -->

<!-- BEGIN persona-persisting-findings (synced from snippets/persona-persisting-findings.md) -->
## Persisting your findings

Apply every finding in place with Edit, then Edit the file named by the `sidecar_path:` line in your dispatch context to hold your `ReviewOutput` JSON, narrative and a `## Findings Ledger`. Stamp the brief's `run_nonce:` verbatim into the frontmatter; never copy one off disk, and with no `run_nonce:` line omit the key. The ledger is exactly one fenced `json` array under that heading, one row per finding: `{"id": "F1", "file": "<repo-relative path>", "before": "<exact text replaced, empty for an insertion>", "after": "<exact text now on disk, empty for a deletion>"}`; a finding you did not apply adds `"status": "em-rejected", "reason": "..."` (or `"suspended"`) instead of the text pair. Run `review-findings-ledger verify --sidecar <your sidecar>` until it exits 0, then return only `DONE: <sidecar-path> | verdict: <OK|WARN|BLOCKED> | findings: <N>`. With no `sidecar_path:` line, say in your first line that provisioning missed, then return the findings inline
<!-- END persona-persisting-findings -->
