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
- **Markdown link** (`[text]` followed by `(target.md)`) — resolved relative to the **citing file's own
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

## Verify the mechanism a claim is relied on for, not the adjacent signal it arrived with

A citation or a capability claim can be **true and still not support what it is used for.**
Falsity fails a grep or a test; a true-but-misapplied claim passes every check you'd think to run,
because the thing you verify is not the thing you are relying on. It compounds with silent
fail-open behaviour: the citation verifies clean, and the defect it causes announces nothing.

- **Verify a capability by the mechanism that consumes it, never by an adjacent signal.** A module
  file present and correct in a published mirror is not "the op is available" — an op resolves
  through a registry (`@register_op` / `_REGISTRY`), not by file presence, and file presence is
  precisely the signal that reads true while the op is dead. A docstring describing a code path is
  evidence about intent, not about behaviour — read the code, not the docstring, for anything you
  will build against. When one citation is doing double duty for two different claims in one
  sentence, split it; the second claim is the one nobody checked.
- **A citation entering a document from a relay — a baton's AC, a subagent's report, a peer's
  message, a pre-flight's finding, an earlier plan — is unverified until *this* session opens the
  cited file itself.** Not the citing document, the cited one. Re-reading your own draft cannot
  catch a bad citation: it checks that the prose is coherent and the number supports the claim it
  sits next to, and a fabricated decision-record number or an inverted statistic passes both of
  those — the falsifying information is not in the document being reread, it is only in the source.
  A false citation even arguing for the right conclusion is worse, not better: correctness of the
  conclusion is not evidence for correctness of the evidence. "It came from a pre-flight whose job
  is checking citations" is not a discharge either — a pre-flight is a relay like any other, and can
  catch one citation error while introducing a second in the same run. Cheapest sufficient act: open
  the cited file and read the line — for a decision record, its title and `## Decision`; for a
  statistic, the sentence it was extracted from. For a class of error the author structurally cannot
  see from inside their own document, add a reader (a dispatched pre-flight, a peer opening the same
  source independently) — being more careful is the response that feels proportionate and does
  nothing, because carelessness was never the mechanism.
- **A subagent's own working journal is not the artifact, and is not preserved.** When a workflow's
  per-agent findings are richer than the synthesis it writes to disk, citing the raw journal
  (`subagents/workflows/<run>/journal.jsonl` and its like) instead of the written report cites
  something that will not exist for the next reader. One baton quoted a prior audit's journal-only
  verdict and told its EM to test the hypothesis; the executing session found only a narrower null
  result in the actual artifact and had to report "there was no prior ruling to overturn." Cite what
  the artifact says, not what you recall an agent finding along the way — if a journal-only finding
  matters, promote it into the artifact first.
- **A handoff's cached description of another artifact's mutable state is not evidence, no matter
  how specific it reads.** A frontmatter field that caches "plan X's status is draft, never
  authorized" is a snapshot, and it goes stale the moment that plan moves — nothing re-reads it. One
  pickup drafted a full duplicate plan for work that was already PM-authorized and shipping, because
  it trusted a handoff's cached `first_draft_plan_status` field instead of opening the live plan.
  Worse, a false "the prior holder is dead" verdict (`dead-holder` on a claim lock means the lock was
  *takeable*, not that the holder actually stopped working) removed the suspicion that would have
  prompted re-checking anything else — two agreeing-but-wrong signals read as corroboration. Re-read
  the live artifact a baton names (`status:`, `execution_authorized_by`) before planning against it,
  never the handoff's prose description of it; on a shared branch, a recent commit against the scope
  path is a cheaper and more honest liveness check than trusting a stale reclaim record.
- **Your own artifacts are not evidence about a sibling's state, and neither is an elegant
  mechanism you constructed to explain one.** Enumerating your own store, inferring a sibling's
  sweep behavior from a locally-absent directory, or building a plausible causal chain ("title
  resolved to no entity, so it fell back to X, so field Y is null") and citing that chain as fact
  are all the same error: a conclusion that feels checked because its parts are individually real.
  Confirmed repeatedly in one fleet within a single day, each time caught only because a peer forced
  the actual query to be run rather than the inference to be trusted. If you can run the query,
  run it before citing the inference.
- **On a question the project is actively governing, read the newest ratified record first, not
  the one that reads most authoritative.** A `docs/decisions/DR-NNN` looks like the settled answer,
  but a later roadmap gate or resolutions file routinely narrows or supersedes it, and citing the DR
  alone gets the ruling backwards. Enumerate candidate governing records by date before reading any
  of them; when two ratified records appear to conflict, stop and date them rather than picking the
  one that fits your current hypothesis; and verify the *scope* a quoted sentence was written to
  serve, not just that the sentence exists — a reviewer's citations being real does not make the
  generalization built on them sound.
- **A guard or test whose scope is narrower than the rule it cites in its own comment reads as
  enforcement and lets the defect recur.** A guard born from one audit finding, written against the
  example that prompted it while the comment beside it states the rule at full breadth, protects
  only the corner it was born in — and every future reader has a stated rule and a green check with
  no reason to doubt either. When a defect class recurs and a guard for it already exists, the first
  question is the guard's actual scope, not why someone missed the rule; the recurrence is evidence
  about the guard. Never trust a guard you have not watched fail — remove one covered case, confirm
  it fires, then restore.
- **A premise-check a tool prompts for only after the send is too late to help.** A cross-repo memo
  tool that reminds you to verify a claim against the sibling's HEAD in its *post-send* output has
  already delivered the memo before the check runs. One memo asserted a sibling hadn't yet vendored
  a schema field and the break was therefore latent; checking their tree after sending showed the
  opposite — the break was live and silently discarding data, and the correction had to chase the
  memo out the door. The dangerous direction is not "went stale," it's "was wrong in a way that
  reversed severity" — the memo told the sibling to relax about something urgent. Run the premise
  check while drafting, against the sibling's actual tree, and cite `file:line` from *their* repo in
  the memo body so the premise is falsifiable by the reader, not after you've already sent it. (One
  guard in this fleet denies a read-only `git -C <peer-repo> merge-base ... && ...` compound as a
  foreign-repo write even though nothing in it mutates — if verifying a peer's HEAD this way is
  blocked, don't reshape the command to evade the guard; verify the load-bearing claim some other
  read-only way and say so.)

## Line numbers and SHAs are a coordinate system your own writes are entitled to invalidate

A `file:line` pin decays even when nobody else touches the file — and it decays *worse* when a
line-pinned citation looks precise, because precision is exactly what stops the next reader from
rechecking it. Several distinct decay paths, all landing on the same rule:

- **Your own plan's later chunk invalidates a citation your earlier chunk verified correctly.** A
  citation can be verified at draft time, re-verified by a reviewer, and still ship wrong, because
  a *different, independently-scoped* chunk in the same plan inserted lines above the cited
  coordinate before the plan finished. Chunk-independence analysis (disjoint write-targets, no
  gate between them) correctly finds no conflict between the chunks' *edits* while missing the
  conflict between one chunk's *edit* and another's *citation* — the two are different
  relationships and only one is normally checked. Before citing `file:line`, ask whether *any*
  chunk in this plan writes that file; if one does, anchor on something the edit cannot move (a
  field name, a symbol, a heading, a unique string) and keep the line number only as a demoted,
  dated secondary note.
- **A precedent citation that was never true is not caught by re-reading your own prose.** A plan
  citing "exactly as `file:439-440` does" reads as verified and gets trusted downstream even when
  no such precedent exists at that location — caught, in one case, only because a reviewer went
  and opened the cited file. The false claim propagated plan → dispatch brief → shipped docstring
  before that happened. Prefer symbol-name citations over line numbers, which drift silently as a
  file grows; when a reviewer reports a citation is false, correct it at the plan, not only at the
  code, or the next session copies the same wrong pin forward.
- **A per-commit slice diff (built by concatenating commits, the correct remedy for
  peer-contamination in a range diff) replays intermediate states that never exist at HEAD.** Code
  added and removed within the same commit set reads as a `+` line in the review artifact and is
  gone by the time anyone reads it live — and line citations taken from that artifact are
  diff-relative, so a finding can cite `file:1055-1071` against a file that is 860 lines long.
  Treat any citation taken from a synthetic diff artifact as needing re-resolution against the
  real file, not as already-resolved.
- **A version ceiling pinned against a sibling's release train rots by design, for the same
  reason a bare line number does: it encodes a fact about a moving target as if it were fixed.**
  Pin a floor, not a ceiling, when the sibling practices additive versioning — a ceiling rejects
  identically on additive and breaking bumps and cannot tell them apart, converting a routine
  release into your outage. The same session that found this also found the sharper corollary:
  bare cross-repo `file:line` citations in decision records rot within days as the sibling's file
  grows, for the identical reason — pin the SHA or the stable symbol, not the line.
- **A SHA you verified yourself, minutes ago, can stop existing.** `git cat-file` reporting a
  commit and `git show` returning its content is real verification — and a history-rewriting
  sweep on the *cited* repo can orphan that exact object within the hour, surviving only as a
  different hash with byte-identical content. Nothing in either tree announces the change. A
  reviewer flagging the dead hash is not necessarily wrong just because your own evidence was
  direct — your evidence can simply be stale. Where the target repo is one you don't control,
  pin what you can re-derive (content, a stable symbol) over what a maintenance sweep can silently
  retire (a specific commit hash).

## A claim verified once does not stay verified — and a number needs its construction to travel with it

Verification has no shelf life marked on it. A plan, memo, or handoff states a fact about disk in
the present tense — "X ships nothing," "the door is unreachable," "the contract cannot hold this
field" — and every one of those can be true when written and silently false by the time a
successor document repeats it, because nothing marks *when* it was checked and nothing re-checks
it. A verified claim and an unverified one are typographically identical once written down; the
reader inherits the confidence without inheriting the check. Two cheap fixes: (1) stamp the
verification — "verified `<ref>` against `<repo>` disk `<date>`" — so a reader can see a claim is
weeks old and re-check it, which they cannot do from bare prose; (2) treat a **negative** claim
("X does not exist," "Y ships nothing") as higher-risk than a positive one and state its method —
a negative derived from a token grep is a claim about those tokens, not about the capability, and
should say so.

A related but distinct trap: a number measured on synthetic data is evidence only for the
question its construction was built to answer, and stripping the construction lets the number
read as a finding about real data instead. A cross-seed stability figure measured on a
deliberately low-separation synthetic mixture, cited bare two hops later, was read as a claim
about real-corpus structure and written into a frozen public docstring as a determinism-scope
claim — a claim the number never supported once separated from the parameters that produced it.
When a synthetic measurement is cited outside the record that generated it — a plan decision row,
a cross-repo memo, a docstring — carry the generator identity and its key parameters, or carry
the word "synthetic" plus a pointer to the record that has them. A number cited bare is a number
that will eventually be read as an observation.

## A mechanism whose failure state is indistinguishable from its working state is not a mechanism

Ask of every guard, marker, vocabulary, or citation check on this page: **what would I observe if
this were broken?** If the answer is "exactly what I observe now," it is not enforcement, it is a
description of enforcement, and it will read as working forever. This page's own tools are not
exempt — `citation_graph.scan_corpus()` and the ratchet below only count what their grammars
extract, and a class the grammar doesn't recognize fails exactly this way: silently, indefinitely,
and looking like zero rot rather than like a gap.

Two concrete tells worth watching for, both distinct from ordinary staleness: an **operator-set
marker whose absence is read as "nothing changed"** actively mismarks rather than merely omitting
— a sibling repo's `hash_basis_changed` field defaults to "basis did not change" when nobody sets
it, so a silent derivation change is not left unmarked, it is actively misrecorded as a clean
delta; and a **consumer that silently strips unknown fields** keeps both sides' tests green while
the data never arrives — a `.strict()` schema that discards an unrecognized key and keeps the row
is functionally identical, from the outside, to the field never having been sent. Neither failure
produces a red test, a stack trace, or a log line. The tell is asymmetry between how cheap the
claim was to write and how impossible it is to falsify from outside — that combination is what
lets these accumulate, because nothing pushes back. When you write a claim (in a docstring, a
comment, a marker's absence), name the observation that would contradict it; if you can't, the
claim is decoration and should be deleted rather than softened. Prefer a loud failure to a
plausible default whenever the plausible answer could be wrong.

## Citations into lifecycle-swept directories rot by construction

Some directories aren't storage, they're a lifecycle: a file's presence *there* is a state, and a
working mechanism moves it out from under any citation the moment that state changes. Three
tracked cases in this fleet: `fleet.archive_completed_plans` relocates a plan to
`archive/specs/YYYY-MM/` the moment its status flips terminal, often mid-session right after
`/execute-plan` stamps it; `cross-repo/inbox/` moves an actioned memo to `cross-repo/archive/`;
and `state/memo-outbox/` moves a draft to `sent/`. A citation written as `docs/plans/<slug>.md` or
`cross-repo/inbox/<name>.md` is correct only until the sweep runs, then permanently wrong — and
the rot is generated by the sweep doing its job, not by anyone's carelessness. One repo's
doc-link sweep found this the dominant citation-defect class on disk: 34 unique memo paths dead
across roughly 80 citation sites in 25+ files, several already self-flagged inline by authors who
noticed the symptom repeatedly without anyone naming the cause.

The failure has teeth beyond a dead link: a citation into an actioned-but-real memo reads as
**absent**, and an absent citation reads as a **fabricated** one — a reviewer once flagged an
acceptance criterion as overclaiming because its supporting memo "does not exist on disk" and
recommended reverting settled work, when the memo was real and simply archived.

**Rule:** for a durable backlink in code or docs, cite the stable artifact — a decision record
(`docs/decisions/DR-NNN`), not a plan path that will archive out from under it. For a memo, cite
its filename (basenames are unique and stable across the whole lifecycle) or its title plus
from/created, never a live `inbox/`/`outbox/` path — add a parenthetical noting inbox items
relocate to archive once processed if the reader needs the hint. **Do not "fix" a rotted
lifecycle citation by repointing it at the current `archive/` location** — that is correct only
until the next sweep and reproduces the same defect one hop later. Distinguish this from a path
that never existed in this checkout at all (a memo delivered receiver-side only) — that looks
identical to a grep miss but is a different failure and must not be "fixed" by pointing at
archive either. (A related tooling gap in the same family: `cross-repo-memo`'s `--in-reply-to` is
single-valued, so one reply answering two inbound memos leaves the second one permanently
re-flagged as unreplied by every future pickup scan — not a citation defect itself, but the same
shape of a mechanism that cannot represent a real, already-resolved link.)

## The tell: a clean link-checker run says nothing here

See the companion tripwire,
`docs/wiki/coordinator-tripwires/a-prose-citation-is-invisible-to-every-link-checker.md`. In one line: "I
ran a link checker over the corpus and it came back clean" is true and worthless — a clean
markdown-link-checker run says nothing about the ~4/5 of this corpus's cross-references that
aren't markdown links at all.

## Ground-truthed rot count, and why it isn't a bare threshold

**Measured at 816 wiki files** (C1's first
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
first pass, then corrected to try the plugin root (`coordinator/`) before
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

**Measured live against this checkout, 819 wiki
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
  dispatched from (chunk C7).
