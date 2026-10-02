<!-- canonical source for enriched-artifact-review-contract — edit here; injected at dispatch via contract_blocks: in subagent-sandbox-policy.yaml -->
<!-- consumers: fixed list in snippets/registry.toml [snippet.enriched-artifact-review-contract] -->

## Reviewing an Enriched Artifact

Applies only to an enriched plan or stub, never a code review. It carries facts an enricher pinned (paths, signatures, insertion points, counts). Review both axes: the plan, and those facts.

- **Re-verify each asserted fact at source.** A file you did not open is an unreviewed fact.
- **A wrong enrichment fact is `major` minimum, `correctness`** — the executor types against it.
- **Diff-scoping does not apply here**: there is no diff, and scope is every enriched stub named.

Verified facts are not verified behaviour; say which you checked in Coverage.
