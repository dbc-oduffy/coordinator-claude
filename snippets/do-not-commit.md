<!-- canonical source for do-not-commit — edit here, then run bin/verify-snippet-sync do-not-commit --fix -->
<!-- consumers: fixed list in snippets/registry.toml [snippet.do-not-commit] -->
<!-- RESIDENT block (F3, fail-open safety finding): pasted into each consumer, sentinel-governed via verify-snippet-sync — NOT injected. -->
<!-- Do-not-commit is one of the two blocks (with guard-encounter-preamble) whose silent absence is dangerous, so it does not ride the dispatch-time injection path where a subprocess failure could omit it. -->

## Do Not Commit

Your role does not include creating git commits. Write your edits and run any required validation, then report back — the EM owns the commit step, committing directly or dispatching `coordinator:git-commit-agent` with an explicit pathspec.

**Per-persona override:** a consumer whose remit structurally excludes commits (e.g. a review persona that only writes a sidecar) may narrow this to a bespoke one-liner instead of pasting the block verbatim — an intentional per-persona omission, not drift from this canonical text.

**Doctrine root:** `coordinator/docs/wiki/scoped-safety-commits.md`
