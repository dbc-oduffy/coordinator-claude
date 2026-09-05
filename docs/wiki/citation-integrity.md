---
last-updated: 2026-08-30
---

# Citation Integrity

This corpus does not cite a sibling page with a markdown link. It cites it with a backticked
bare filename in prose — `` `some-page.md` `` — and that form is invisible to every tool built
to check links, including our own `doc-link-checker` (`doc-link-checker-adds-no-signal-on-
private-repo-absolute-self-urls.md`). A page can be renamed, split into a directory, or retired
to `archive/`, and every prose citation naming its old filename keeps reading as fine — nothing
today notices, because nothing today looks.

**Every count on this page carries the git SHA and wiki-file-count it was measured against.**
A bare number is the exact failure this page documents one layer up — a citation that was
correct when written and silently wrong the moment its target moved, with nothing able to tell
the difference. Don't quote a figure below without its (SHA, file-count) pair.

## The convention, stated

Five extraction grammars exist in this corpus, resolving through three resolution rules — never
one shared code path (`coordinator/lib/citation_graph.py`):

- **Bare basename** (`` `some-page.md` ``) — resolved by basename against
  `coordinator/docs/wiki/`, the tracked wiki corpus. Exactly one match is `live`; more than one
  is `ambiguous`; zero in the wiki set but a match elsewhere in the repo is `cross_surface`
  (below); zero anywhere is `rot`.
- **Cross-surface citation** — a bare basename absent from the wiki tree but present elsewhere in
  the repo (a plan, handoff, lesson, or other tracked state artifact). This is a **live** citation
  into a different tracked surface, not wiki-side rot, and it is out of scope for this page's rot
  ratchet — folding it into `rot` would count a real, resolvable citation as a defect.
- **Pathed** (`` `docs/wiki/some-page.md` ``) — resolved **repo-root-relative**, then against the
  plugin root (`coordinator/`) — never joined against the citing file's own directory. Joining
  against the citing directory was the prototype's inherited bug: this corpus's authors write
  pathed citations relative to the *plugin* root ("Both trees are named 'coordinator-claude';
  they are NOT the same tree" — `CLAUDE.md` § Architecture), so a naive repo-root-only join
  misresolves the overwhelming majority of pathed citations as rot that are in fact live.
- **Markdown link** (`` [text](target.md) ``) — resolved relative to the **citing file's own
  directory**. This is the one form for which that join is correct — it is the only shape this
  category of tool (a link checker) can already see.

- **Wikilink** (`[[some-page]]`, or `[[SOME_PAGE]]`) — a slug with no extension, extracted as its
  own grammar and then resolved as an ordinary `bare_basename` citation (`<slug>.md`, through the
  same basename lookup) after normalizing to lowercase with `_` folded to `-`. Two conventions run
  side by side: a page's own filename slug, and a tripwire page's uppercase GREPPABLE_TOKEN naming
  the same file. A slug carrying no separator at all is not a wikilink — it is TOML
  array-of-tables syntax in a code span — and neither is a double-bracket span containing a space,
  `$`, `"` or `:`, which is bash conditional or POSIX character-class prose.

The first four differ because the corpus's authors use each shape with a different implicit
resolution rule in mind, and collapsing them into one code path — as the pre-C1 prototype did —
silently misclassifies whichever shape doesn't match the one rule chosen. The wikilink grammar is
the exception: its surface form is genuinely distinct (no extension, doubled brackets) but its
resolution is identical to bare-basename at every consumer, so it carries no separate `kind` —
folding it into `bare_basename` avoids a classification axis nothing downstream reads.

The wikilink shape is the one a reader is most likely to under-count: it is invisible to every
link checker AND was invisible to this resolver's own first four grammars, so 53 pages carrying 74
wikilinks read as having no outbound references at all.

## The tell: a clean link-checker run says nothing here

See the companion tripwire,
`docs/wiki/coordinator-tripwires/a-prose-citation-is-invisible-to-every-link-checker.md`. In one line: "I
ran a link checker over the corpus and it came back clean" is true and worthless — a clean
markdown-link-checker run says nothing about the ~4/5 of this corpus's cross-references that
aren't markdown links at all.

## Ground-truthed rot count, and why it isn't a bare threshold

**Measured at 816 wiki files, commit `b96f98fe76106816e2243925c90641ee2fca8dff`** (C1's first
scan; superseded below by C1-repair, kept here because the ground-truth hand-classification below
was performed against this run's 157-item bare-basename rot set):

- Bare-basename citations: 1,458 (after de-duplicating markdown-link labels). Resolved: 701
  `live`, 23 `ambiguous`, 567 `cross_surface`, **157 `rot`**.

**The 157-item bare-basename rot set was read in full, not sampled** (small enough to
hand-classify exhaustively — the plan's own instruction). Split:
- **Genuine rename/retirement rot: 49** — pages whose target moved or was retired without the
  citation updating: `improvement-queue.md` / `bug-backlog.md` / `lessons.md` (converted to
  directories of per-entry YAML), `coordinator-tripwires.md` (converted to a directory),
  `agent-install.md` / `workstream-start.md` / `example-game-repo-install-prereq.md` (moved/retired install
  surfaces), `env-vars.md`, `cross-plugin-whoami-contract.md` (described substantively across four
  citing pages, absent everywhere in the repo).
- **Incidental, not rot: 108** — 20 dated-artifact filenames (plans/handoffs, expected decay), 22
  external-convention mentions that were never wiki pages (`ROADMAP.md`, `CLAUDE.local.md`, etc.),
  66 illustrative/worked-example/cross-repo-target filenames this repo cannot resolve at all.
- **Measured precision (genuine / flagged): 49/157 ≈ 31%.**

**Decision rule, not a bare threshold.** `DR-dead-code-enumeration-declined-on-measured-
precision` killed a comparable gate's signal at ~10% genuine (30/30 ground-truthed at that rate).
31% clears that noise floor by a wide margin — a gate built on the bare-basename rot class would
deny substantially more often on real rename-rot than on noise. That is the honest basis for
building the ratchet at all; a lower measured precision would have been reported as "the report
still ships, the gate does not," per the same precedent.

**Reproducible, not frozen.** The 49/157 split rests on one reader's classification of each
excerpt — a different reasonable reader could move a handful of the 66 "illustrative" items either
way. Treat it as a measurement, recomputable on demand, not settled ground truth. A **seeded
sampler** (`citation_graph.sample_verdicts(verdicts, seed=…, sample_size=…)`) ships as a
test-visible function over the full verdict set for exactly this reason — a 30-sample draw's 95%
CI is roughly ±11pp, too wide to itself decide anything, but wide enough to make any corpus-wide
precision figure independently recheckable rather than believed as a hand-count frozen at one
point in time.

## The root-resolution fix, and what it moved

The pathed-citation class (`` `docs/wiki/some-page.md` ``) was resolved repo-root-only in C1's
first pass, then corrected (commit `66e54f7a3`) to try the plugin root (`coordinator/`) before
the repo root — same commit's `PATHED_RESOLUTION_ROOTS = (PLUGIN_ROOT, REPO_ROOT)`. Measured at
816 wiki files, same tree:

| Class | Before fix | After fix |
|---|---|---|
| pathed `live` | 953 | 1,748 |
| pathed `rot` | 1,797 | 914 |
| pathed `home_relative` (new class, `~`-prefixed) | (counted as rot) | 79 |
| filtered as placeholder (never a citation) | 0 of 9 | 9 |

Rot-class precision on the pathed bucket: **55.8% → 91.2%** genuinely-unresolvable-anywhere,
after the root fix plus reclassifying `~`-home-relative targets (not repo paths at all — a
different fact from "renamed or deleted") and prose-convention placeholders (`…`, `!`, literal
`...`) that were never citations. The pathed rot bucket (914, after fix) was **not** exhaustively
ground-truthed the way the 157 bare-basename items were — it was bucketed by path prefix
(`docs/` 296, `state/` 119, `coordinator/`-prefixed-but-nonexistent 80, `archive/` 70,
`cross-repo/` 64, `_mine/` 44, `plugins/` 33, `tasks/` 32) and spot-verified by hand for two
samples, plus a flagged, unfixed extraction-grammar gap: ~24 of the 914 (≈2.6%) are backticked
shell commands or config values that happen to contain a `.md` token
(`` `git add state/health-ledger.md` ``), not citations at all — a false positive in the
*extraction* grammar, not the resolution rule, left open for a future chunk.

## Standing counts

**Measured live against this checkout at `8884273008a57a06eba593c7d5b4da7e84fcf634`, 819 wiki
files** (`citation_graph.scan_corpus()` — recomputed on every call, never persisted, since a
resolution verdict is a fact about *other* files and goes stale on any change that doesn't touch
the citing file):

| Kind | live | rot | cross_surface | ambiguous | dead_link | home_relative |
|---|---|---|---|---|---|---|
| bare_basename | 572 | 156 | 570 | 23 | — | — |
| pathed | 1,752 | 915 | — | — | — | 79 |
| markdown_link | 897 | — | — | — | 16 | — |

Total extracted citations at this SHA: 4,980. These figures move corpus-to-corpus and commit-to-
commit — re-run `citation_graph.scan_corpus()` for a current number rather than trusting this
table past the SHA it's pinned to.

## Index-coverage figure — a one-time fact, not a standing gate

The wiki directory guide (`DIRECTORY_GUIDE.md`) reached only 177 of 805 pages at the time of the
original audit (`docs/research/2026-08-30-17h00-llm-wiki-doctrine-corpus-workdir/own-side-audit.md`),
drifting from 145 of 203 recorded by the architecture atlas in July. A reader who knows 78% of the
corpus is absent from the guide is better served than one who assumes it's exhaustive — that is
worth stating once, here, and is deliberately **not** a number `check-citation-integrity.py`
recomputes or gates on every run: the guide's rows carry hand-written editorial descriptions,
regenerating it would destroy or fabricate them, and a completeness percentage that only ever
grows worse is not a signal worth a standing check. What the CLI *does* keep as a live gate is
narrower and cheaper: the guide's dead-row count (rows pointing at files that do not exist).

This page's own guide row is, per C7's own dispatch brief, the first case of that dead-row/
completeness gap being closed by an author who could see it while writing the page that names the
gap.

## Orphan counting: all forms, not markdown links alone — a one-time proof, not a standing figure

Counting orphans over markdown links only over-reports the true orphan count by roughly 2x on this
corpus (~80% of cross-references are backticked prose, not links) — the evidentiary measurement
that justified counting orphans over all resolving citation forms (bare basename, pathed, markdown
link) instead of links alone. This was a one-time proof that the all-forms resolver mattered; it is
not recomputed on every run, and `check-citation-integrity.py` does not carry a `links_only`
figure in its default path for that reason.

## When it runs

`/update-docs` Phase 11m, DoE-only. Nothing else invokes it, deliberately: it is a corpus-state
check, not a code test, so it stays out of the test tiers — `test_citation_integrity_cli.py`
asserts the gate contract over synthetic fixtures and never against the live corpus, which ~20
concurrent writers mutate continuously. A tier that goes red because a peer is mid-edit teaches
sessions to ignore it.

**A new violation is looked at, never auto-repaired.** The ratchet's whole value is that it fires
on something a human has not yet classified, and the classification it needs — does this citation
*point*, or merely *mention* — is the one thing no mechanism here can do. Accepting a genuinely
new member into the baseline is legitimate when a detection class is introduced; laundering an
unexamined defect into it is not, and the two are indistinguishable in the file afterwards.

## See also

- `docs/wiki/coordinator-tripwires/a-prose-citation-is-invisible-to-every-link-checker.md` — the tell/
  correction pair.
- `coordinator/lib/citation_graph.py` — the extraction/resolution library these figures are
  computed from.
- `docs/research/2026-08-30-17h00-llm-wiki-doctrine-corpus-workdir/own-side-audit.md` — the
  original 805-file audit this page's figures supersede.
- `docs/plans/2026-08-30-citation-integrity-tier-1.md` — the plan this page and its tripwire were
  dispatched from (chunk C7).
