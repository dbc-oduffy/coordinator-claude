# The DR Corpus: Where Decisions Live and How They're Edited

Conventions for authoring and maintaining `DR-*` decision records — read this before writing a
new one or editing an existing one. This is the durable home for these conventions, on a
surface a decision author hits while authoring, not buried inside one record among 200+.

## The two-directory split is intentional

- `docs/decisions/` — **repo-plane.** Decisions about this repo's own working data, doctrine
  working-data, and cross-repo boundary arbitration. Not shipped anywhere.
- `coordinator/docs/decisions/` — **plugin-plane.** Decisions about the coordinator plugin
  itself, and these ship to the OSS `coordinator-claude` mirror alongside the rest of
  `coordinator/`.

The split is not an accident of history to be flattened — it tracks which plane a decision
governs, the same discriminator that governs every other file placement in this repo (see
project `CLAUDE.md` § Place in the fleet).

## Edit in place, or mint a new DR — the rule is reversal, not change

**A non-reversing change is an in-place edit** of the record, stamped with `edited:` in its
frontmatter. No `## Amendment`, `## Supersession`, or `## Correction` sections: the record states
the ruling as it stands.

**A full reversal mints a new DR**, and the old record is deleted via
`fleet.delete_superseded_decisions`. `status: superseded` is a transient pre-delete state, never a
resting state; every record in the corpus is live. The rule itself lives in
`coordinator/docs/wiki/dr-supersession-rule.md`.

## Citation integrity — check-decision-citations

`coordinator/bin/check-decision-citations.py` verifies that every cited `DR-nnn` and `SC-DR-nnn`
id resolves to a record somewhere in the fleet.

- **CLI.** No flags: delta check against the committed baseline. `--emit-baseline`: rewrite
  the committed baseline file.
- **Exit codes.** 0 = clean (`decision citations: clean`), or baseline absent (one stderr line,
  skipped). 1 = new dangling id; one line per id with its citing files. 2 = could not check
  (`git grep` failed), or emit refused.
- **Live-token rule.** One `git grep` over tracked `.md/.json/.sh/.py/.yaml/.js` files. A token is
  live when it is outside a fenced code block, its file is outside `archive/`, `tasks/`,
  `.structural-index/`, `.coordinator-local/`, and it is not a reserved placeholder id (the all-zero and all-nine
  ids, with or without the `SC-` prefix). Namespaced ids (`DR-PV1-nnn`) never match.
- **Resolution keys.** Filename prefix or frontmatter `id:` in `docs/decisions/` or
  `coordinator/docs/decisions/`; an id whose record was deleted from either directory in git
  history; the same in any sibling registry repo's `docs/decisions/` (absent
  siblings are skipped); `SC-DR` ids resolve against `concurrent-em-git-operations/scoped-safety-commits.md`.
- **Baseline shape.** A header naming the generating command and the resolved sibling registry
  keys (never paths); `## Dangling` (id, citing-file count, first citing file; the only gated
  part); `## Bare cross-repo inventory` (ids resolving only in a sibling, with key and count).
  Re-emit on an unchanged tree is byte-identical. Emit refuses (exit 2, file untouched) when a
  sibling key named in the existing header fails to resolve.
- **Fire response.** Fix the citation, or route a genuinely lost record to the recovery plan.
  Never run `--emit-baseline` to silence a fire.


## Negative spec

- Not a place to restate the substance of a specific ruling — that lives in the ruling's own
  record.
- Not a changelog of who edited what when — git history carries that; this page states the
  standing convention, present tense.
