Part of [`PIPELINE.md`](PIPELINE.md); phases still run in its strict sequence.

## Clustering Interstitial (Coordinator or Haiku)

After all Phase 1.5 verdicts are PASS (or batches are marked FAIL/SKIP), regroup nuggets from input-batch grouping to output-topic grouping.

**For ≤100 nuggets:** Coordinator reads all Phase 1 scratch files and builds the clustering table directly (mechanical, not wasteful at this scale).

**For >100 nuggets:** Dispatch a single Haiku clustering agent using the **Clustering: Haiku Clustering Prompt** from `agent-prompts/clustering.md`. The agent produces a mapping of `{system_tag → [nugget_ids_with_batch_references]}`. Coordinator validates the mapping before proceeding.

**Output:** topic dispatch table mapping each guide topic to its source nuggets across all batches. This table drives Phase 2 dispatch.

---

## Consolidation (Coordinator, mechanical — pure function, no dispatch)

Runs between Clustering and Phase 2/Wave 2, over the clustering table's raw cluster set —
**after** curation (§ above) has already run on invocation A's tag census and every surviving
tag has cleared the engine repo's `distill.curate_clusters` verdict. That ordering is why consolidation is
now a single unconditional rule rather than a shrapnel-triage pass: curation decided per-tag,
upstream of clustering, whether a tag deserves a home at all, so by the time a cluster reaches
consolidation the question "does this shit deserve a home" is already answered — consolidation
only decides *which* home.

**Homed / homeless partition.** Partition the raw cluster set by whether `wikiSlugs[slugify(cluster.topicKey)]`
resolves to an existing file (exact slug match, or a `findFuzzyWikiHome` hit):
- **homed** — slug matches an existing wiki file → passes through UNCHANGED; merges into that guide at Phase 2.
- **homeless** — no existing home → **unconditionally becomes a NEW file.** No coarsening, no
  folding, no cap, no misc bucket: every surviving homeless cluster earns its own file, because
  curation already ruled it a real topic before it ever reached clustering.

**The coarsen/fold/cap/misc-bucket mechanics that used to sit here are retired**, not merely
disused — `MISC_MAX_NUGGET_SHARE`, `MIN_SHARED_SEGMENTS`, the segment-prefix trie
(`buildSegmentTrie`/`longestSharedPrefixKey`), `consolidateClusters()` Steps 2-5, and the
`misc-harvest-<RUN_ID>` emission are all deleted from `distill-harvest.workflow.js`, not merely
unreferenced. They existed to triage the homeless bucket *after the fact*, deciding per-cluster
whether a run's inevitable shrapnel earned its own file or got folded into a shared dump. That
triage now happens upstream, per-tag, before clustering — so there is no post-hoc shrapnel left
to triage, and the code that used to do it is gone.

**`SINGLETON_FLOOR` and `NEW_FILE_CAP` are DELETED OUTRIGHT, not held (chunk C4b, commit
`3e99e52c3`).** They are not defined anywhere in `distill-harvest.workflow.js` and are not
pending re-wiring — the two open questions that used to hold them unwired (does curation's `keep`
verdict weight per-tag nugget volume; what does a cold-start drop-rate census show) are both
answered, per `cross-repo/inbox/2026-08-06-claude-klabauter-em-curate-clusters-four-answers-volume-
is-weighted-but-not-a-floor.md`. The minting policy they used to encode now lives in exactly one
place — the engine repo's `distill.curate_clusters` gate — parameterized by `recommended_keep_threshold`,
a value returned alongside `tag_counts` from invocation A and derived below.

**Volume IS weighted, but not by a floor we hold — by a threshold WE pass.** The curation gate
compares `keep_threshold` against a cluster **FAMILY's** total nugget count, summed across every
tag folded into that family, not any single tag's count — two count-1 siblings clear a threshold
neither would clear alone. The drop test is `family_total < keep_threshold`. **At the gate's
default of 2 this drops only 1-nugget families — a 2-nugget cluster is KEPT.** The retired floor's
stated job ("a 1-2-nugget cluster doesn't earn its own new file") is thus only PARTLY discharged
at threshold 2, not fully — record that gap honestly rather than smoothing it over.

**Why the threshold lives on our side.** We emit **1 for cold-start** (empty wiki tree, or fewer
than 150 carry-forward nuggets) and **2 for mature**, derived from the engine repo's own measured drop
rates (mean of 20 seeds over its 433-nugget/249-tag census, deterministically subsampled to
simulate first runs of increasing size):

| N nuggets | thr=2 | thr=1 |
|---:|---:|---:|
| 20 | 71.2% | 12.0% |
| 60 | 44.4% | 8.7% |
| 150 | 27.4% | 8.8% |
| 433 (full) | 17.1% | 8.1% |

We deliberately do NOT emit 3. This is now a **decided tradeoff with a measured price**, not an
open gap awaiting a number. Threshold 3 has been measured (their reproducer, same seeds 0..19,
deterministic, full 433-nugget corpus):

| threshold | keep | normalize | merge | drop | tag-drop | nugget-drop |
|---|---|---|---|---|---|---|
| 3 | 38 | 2 | 124 | 85 | 34.1% | 23.1% |
| 2 (default) | 51 | 2 | 132 | 64 | 25.7% | 17.1% |
| 1 | 86 | 6 | 132 | 25 | 10.0% | 8.1% |

Cold-start (mean of 20 seeds, N=20 nuggets): threshold 3 drops **94.2%** of the corpus, against
71.2% at 2 and 12.0% at 1. Adopting full floor semantics on a mature corpus costs about six points
of nugget loss (23.1% vs 17.1% at 2) — that cost is harvested knowledge discarded permanently.
What it buys is suppressing some 2-nugget wiki files, which are cheap, visible, and mergeable
later. Trading recall for tidiness is the wrong direction for a knowledge harvest, so the retired
floor's 2-nugget-suppression job stays deliberately undone: we stay at 2. Floor semantics want a
high threshold; cold-start survival wants a low one; it is a single knob, so it cannot be a fixed
constant anywhere — it is derived per run from corpus maturity, a fact this repo owns and the
gate cannot see. The policy still lives in exactly one place (their gate); we only parameterize
it.

**Mechanism, not tidying.** `drop_summary.by_cause` makes the 2→3 delta legible: the entire delta is
`below-threshold` (60 / 39 / 0 at thresholds 3 / 2 / 1), while `bare-no-sibling` stays FLAT at 25
across all three thresholds — structural, threshold-invariant, moving the knob changes nothing
about it. The extra drops at 3 are not junk being cleaned up; they are real small topics, which is
exactly why the ruling above goes the way it does.

**Corroboration, not a dependency.** Their gate now auto-derives `keep_threshold` when the caller
omits it; we always pass ours in, so their auto-derivation never fires for us. On their mature
corpus it resolves to 2 — the same value our derivation picks, from a different fact. Two
agreeing heuristics corroborate each other; neither proves the other correct.

**A prediction this plan made, and measurement refuted.** The plan's original worry was that the
gate's structural bare-token rule would savage a cold-start corpus. It does not, and the same
census settles it: at `keep_threshold=1` the drop rate is FLAT — 8-12% across a 20x range of
corpus size, no cold-start blow-up. The structural rule is corpus-size-invariant because it never
consults corpus size; the cold-start degeneration is entirely `keep_threshold`, not the bare-token
rule (71.2% at threshold 2 on a 20-nugget run vs. 17.1% on the full corpus). This is the engine repo's
measurement on its own corpus, with its own caveat attached: a single corpus, and a materially
different tag-naming convention could move the ~10% floor.

**Count-conservation invariant, and where drops actually happen now.** No nugget is ever dropped
by *consolidation* — every input nugget lands in exactly one output cluster (`homed ∪ new`). This
is still an assertable invariant (total nugget count in equals total nugget count out), asserted
by the workflow at consolidation time, and it is still true. But it is now the wrong place to
look for where nuggets get dropped: consolidation drops nothing, full stop. **Curation, upstream
of clustering, is where drops happen** — a tag whose verdict resolves to `drop` is deliberately
excluded before its nuggets ever reach a cluster, and every drop is recorded by tag, nugget, and
reason, then surfaced in the `drop_summary` structure returned from invocation B (verdict counts,
homing-override count, dropped-nugget count and share of the pre-curation corpus, and the top-10
dropped tags by nugget volume with their reasons). A `WARNING` log line fires when the dropped
share exceeds `DROP_SHARE_WARNING_THRESHOLD` (0.25, a first guess — the engine repo's cold-start census has
since landed, see the threshold derivation above, and does not by itself argue for moving this
number) — a visibility tripwire, not a gate; it never halts a run or suppresses output.

**Verdict payload contract (confirmed, chunk C3c, commit `810ffe46d`).** One verdict entry per
RAW input tag, always. `merge_target` is the destination slug a tag folds INTO — populated ONLY
on `merge`, never null there, and null on keep/normalize/drop. `canonical_slug` is the tag's OWN
normalized slug, not a destination. `reason` is non-empty on every drop, naming which of three
paths fired: placeholder / bare-token-with-no-compound-sibling / family-total-below-threshold. The
drop set is a FILTER over the verdict list (`verdict === 'drop'`), never a separate top-level
`dropped:` key — that key does not exist and is not coming. Clustering keys `keep` on
`canonical_slug` (falling back to the raw tag), `normalize` on `canonical_slug`, `merge` on
`merge_target`; a tag absent from the map, a merge with no `merge_target`, a normalize with no
`canonical_slug`, or an unknown verdict each stop the run rather than inventing a bucket.
**Landed (chunk C3c-successor, commit `67b7061f6`) — code against it.** Per-verdict `drop_cause`,
an enum of `placeholder` / `bare-no-sibling` / `below-threshold`, `null` on non-drops. Plus a
`by_cause` count block nested under `drop_summary`, and top-level result fields `threshold_applied`,
`threshold_auto`, and `nugget_drop_share`. Our drop logging keys on the enum now, not on parsing the
`reason` prose string. The
pinned verdict payload this contract is measured against is a committed test fixture under
`coordinator/pipelines/artifact-distillation/tests/`, asserting the three contract properties
above plus the flat-`bare-no-sibling`-at-25 invariant — the contract is test-enforced, not only
described here.

**Log line:** the Workflow emits a one-line summary at this step —
`consolidation: <rawCount> raw -> <homedCount> homed + <newCount> new (no-misc: curation already
decided upstream which tags survive, per plan chunk C4)` — so a run's homed-vs-new ratio is
visible in the run log without reading scratch files. There is no misc term in this line because
there is no misc bucket left to report.

**Output:** the consolidated cluster set (homed clusters unchanged + every homeless cluster
promoted to `new`) replaces the raw clustering-table output as Phase 2/Wave 2's input. Phase 2's
`synthBriefFor`-equivalent honors a cluster's consolidation-assigned target path when present,
else falls back to the disk-resolved `wikiSlugs` target from § Phase 0 step 3.
