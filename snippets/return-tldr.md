<!-- canonical source for return-tldr — edit here, then run bin/verify-snippet-sync return-tldr --fix -->
<!-- consumers: fixed list in snippets/registry.toml [snippet.return-tldr] -->
<!-- INJECTED block, not paste-governed: assembled into the dispatched child prompt at dispatch -->
<!-- time via the `contract_blocks:` grammar, keyed by `subagent_type`. Scope: this reaches -->
<!-- standalone Agent dispatch only — inside plan-blitz the `tldr` is carried by the role -->
<!-- schema instead (RETURN_TLDR_SCHEMA in workflows/plan-blitz.mjs), which the harness -->
<!-- enforces with or without `pluginAgentsAvailable`. -->

## Return TLDR

When your dispatch carries a schema, its `tldr` is the only part the EM reads.
Your `tldr` is a verdict, at most 5 decision items of at most 200 characters each with an
anchor, integer counts, and your sidecar path.
Everything else goes in the sidecar: `coordinator/schemas/return-tldr.schema.json`.
