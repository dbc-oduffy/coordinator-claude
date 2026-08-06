<!-- canonical source for wiki-reconcile-preamble — edit here, then run bin/verify-snippet-sync wiki-reconcile-preamble --fix -->
<!-- consumers: fixed list in snippets/registry.toml [snippet.wiki-reconcile-preamble] -->

## Reconcile Before You Add

Before a doctrine-wiki edit lands here, check whether the target file already states the rule being added. If it does, amend the existing statement in place rather than appending a second one — or, if both genuinely need to coexist, record why in the edit itself. One source drifting into two restatements is the exact failure this rule exists to prevent.

**This is residue, not computed coverage.** The lesson-reconcile assembler computes `candidate_restatements` automatically for the assembler-backed reconcile surfaces. This surface has no assembler to inject into, so the check stays a prose obligation applied by hand, not a computed one.
