# Human-Facing Doc Freshness — Staleness + Content Verification

A doc-health gate over the small set of human-facing entry-point documents a repo carries
(README, INSTALL, CONTEXT, CONTRIBUTING-class files) — the surfaces a new reader or a fresh
clone actually opens first, which sit outside every other doc-maintenance mechanism this
plugin runs. `/update-docs` sweeps working substrate on a short cadence and is explicitly
the wrong cadence for this doc class (it fires far too often for prose that is meant to
change on the order of weeks-to-months, not per-session). Nothing else in the ceremony
stack watches these files at all.

The gate ships two distinct signals through one mechanism: **staleness** (has this doc
moved recently, by genuine authorship) and **content verification** (is what this doc
currently claims still true). They answer different questions, are computed by different
code, and are described separately below before the section that explains why they still
share one gate.

## Staleness — why two thresholds joined by AND, not one

A single threshold in either dimension fails in an obvious, opposite way:

- **Commits-only** fires on a quiet repo the moment enough *other* work has piled up,
  even if the doc itself hasn't changed in a way that matters — a repo that goes quiet for
  a stretch and then has one busy week nags on volume alone.
- **Days-only** fires on the calendar regardless of velocity — a fast-moving repo's
  human-facing docs get flagged every few days even when nothing about them is actually
  wrong, training the reader to tune the nag out.

Requiring **both** a commits floor and a days floor — `stale = commits_since >= C AND
days_since >= D` — means a quiet repo doesn't nag on the calendar alone, and a busy repo
doesn't nag on volume alone. Each threshold is the other's backstop.

### Defaults and the velocity assumption they encode

The shipped fleet defaults are **`C = 8000` commits and `D = 21` days**, both overridable
per repo (see below). Neither number is arbitrary; both encode an explicit judgment about
how often a human-facing entry-point document *should* turn over.

The calibration method: walk the real commit history of a repo's own README/INSTALL/
CONTEXT-class files, classify every touch as **authored** (a real content edit) or a
**sweep drive-by** (a mechanical repoint riding inside a much larger unrelated commit —
see the content-modifying filter below), and check where a candidate threshold would have
fired. A commits-only threshold low enough to ever fire at all fires on *every* doc *every
week* at a repo moving at real development velocity — exactly the nag failure this design
exists to avoid. The chosen thresholds are the point past which the true authored-touch
cadence for this doc class (weeks-to-months, not days) stops competing with routine
development churn for the trigger.

At a repo moving at a sustained few-hundred-commits-per-day pace, `C = 8000` corresponds
to roughly a month — proportionate to a doc class meant to stay high-level and change
infrequently. A slower-moving repo reaches the same commit count over a much longer
calendar span; `D = 21` is the paired floor that becomes binding in that case (see the
portability section below). This is the asymmetry the AND is there to provide: at high
velocity the commits leg binds first and the days leg is the backstop; at low velocity the
relationship inverts.

### Honest limitation — this cannot be backtest-validated on a young repo

A commits threshold can be *falsified* by history — replay a candidate value against real
touches and if it fires every week, it's too low, and that's a genuine empirical result.
It cannot be *confirmed* the same way on a repo whose total commit count is smaller than
the threshold itself: there is no window in that repo's own history long enough to have
ever crossed it, so no backtest run can show the threshold firing correctly. A default set
this way is chosen on judgment about the right turnover cadence for the doc class, not on
a fired-correctly-in-backtest result — a legitimate basis for a default, but a different
kind of evidence than the falsification case above, and doctrine describing this design
should not claim backtest support it does not have. One further consequence worth naming:
a content-modifying filter that correctly discounts mechanical sweep touches (below)
lengthens the apparent staleness interval relative to a naive git-log read, so a naive
reading of "time since last touch" over-estimates freshness before the filter, not after.

### Portability caveat and per-repo override

`C = 8000` is sized to one fleet's actual commit velocity. The same absolute number means
a wildly different calendar span at a different velocity — weeks at a high-throughput repo,
well over a year at a low-throughput one. It is therefore shipped as a **fleet default**,
not a universal constant, with per-repo override as a first-class part of the design, not
an afterthought: a repo declares its own commits/days thresholds (and its own doc registry)
in its local configuration, following the same override convention every other
repo-tunable threshold in this plugin uses.

**Below roughly 380 commits per day sustained (the point at which 8000 commits and 21 days
land on the same calendar date), the days floor binds before the commits floor does, and
the commits leg goes effectively inert.** This is by design, not misconfiguration: a
slower-moving repo should be governed by the calendar rather than by a commit count it may
take a very long time to reach at all. A repo whose commit count never reaches its
configured `C` at all simply falls through to the `D` floor alone — read that as "this
repo's human-facing docs are governed by elapsed time," not as "the detector is broken."
Confirm your repo's actual velocity and set both thresholds deliberately rather than
importing the shipped defaults unexamined; a repo far slower than the reference fleet
should very likely lower `C` substantially so the commits leg does meaningful work at all.

### Content-modifying discrimination — a touch is not the same as an edit

Naive `git log` on a path resets its clock on *any* commit that touches the file, including
commits that never actually change anything a reader would notice: whitespace-only diffs,
link-only edits, and — the failure mode that matters most in practice — **sweep
drive-bys**, where a large mechanical commit (a repo-wide rename, a path repoint, a
formatting pass) happens to touch the doc as one of dozens or hundreds of files, changing
only a line or two of it without anyone having read the doc's actual content.

Two filters, both required, discount a touch from resetting the freshness clock:

1. Whitespace-only or link-only diffs are excluded outright.
2. A commit is treated as a sweep drive-by — and excluded — when it touches an unusually
   large number of files overall while changing only a small number of lines in *this*
   document specifically. The files-touched floor and the lines-changed ceiling are fixed
   fleet-wide constants, not currently exposed as a per-repo override — adjusting either
   means changing the value in code, unlike the `C`/`D` staleness thresholds above.

   The shipped lines-changed ceiling was chosen by replaying real commit history and
   plotting where genuine drive-by touches and genuine authored touches actually land on
   the lines-changed axis, rather than by guessing a round number. The two classes did not
   land close together: every drive-by touch changed a small handful of lines in the
   document, and every authored touch that also crossed the files-touched floor changed a
   visibly larger number — a clean, wide gap with no real touches falling in between. When a
   calibration replay produces a gap like that, the exact threshold value stops mattering
   much: **any value inside the gap classifies every observed case correctly**, so the
   shipped default is set at the gap's midpoint — as far as possible from either class,
   rather than pinned to whichever edge happened to be observed. This is a stronger and more
   honestly-stated form of "robust" than claiming the predicate was validated at several
   specific threshold settings: what was actually validated is the *separation* between the
   two classes, and any setting inside that separation inherits the same correctness. A
   repo replaying its own history to retune this constant should look for the same shape —
   a gap between the two classes — rather than assuming the shipped number transfers as-is.

Without this filter, a doc can look freshly touched purely because it was mechanically
swept, while nobody actually read or revised its content in years — the exact inversion a
staleness measure exists to prevent.

## Why staleness provably cannot reach a fresh-but-wrong document

Staleness measures *recency of touch*. It cannot measure *correctness of content* — a
document edited an hour ago can cite a path, command, or fact that stopped being true the
moment a later, unrelated commit moved or deleted what it pointed at. A doc that was
correct when last authored, then silently orphaned by drift elsewhere in the tree, reads
as maximally fresh by every staleness measure while being actively wrong. No tuning of
`C` or `D` can close this gap — driving either threshold down far enough to catch a
same-day breakage makes the gate fire on essentially every doc every week, trading a real
signal for constant noise. This is a structural property of a recency measure, not a
calibration shortfall.

**Content verification is the separate, distinct mechanism that reaches this class.** It
asks a different question entirely: not "when was this last touched" but "does what this
document currently asserts still resolve against the tree." It is authored as its own op,
with its own tests and its own verdict, deliberately not folded into the staleness
computation — the two remain separable findings under one gate (see below), not one
measure wearing two hats.

## Content verification — scope and the negative surface that makes it trustworthy

v1 content verification checks a narrow, mechanically-checkable slice of what a
human-facing doc asserts: does a repo-relative path cited inside a fenced command block
still exist; does an inline code-span token that looks like a repo-relative path (contains
a directory separator) still exist; does a relative markdown link's target file (and
anchor, if given) still exist. All three are structural existence checks against the
working tree — no natural-language understanding, no semantic judgment.

**The negative surface is load-bearing, not optional polish.** A bare existence check over
every path-shaped token in a real README or INSTALL doc produces false positives at scale:
a citation to a sibling repo's file, a slash-command name, a URL, a glob pattern, or an
environment-variable-prefixed path all look exactly like a broken repo-relative path to a
naive matcher, and are lexically indistinguishable from a genuinely broken citation without
deliberate handling. Three pieces close that gap, and all three are required for the
mechanism to produce a trustworthy signal rather than noise the reader learns to skim past:

1. **An exclusion set applied before resolution** — a token is not treated as a path
   citation at all if it looks like a slash-command, contains a URL scheme or bare domain,
   contains a glob metacharacter or placeholder shape, or is prefixed with an
   environment-variable or home-directory marker.
2. **Cross-repo resolution** — a token that does not resolve against the current tree is
   re-checked against the sibling repo roots this repo declares before being reported as
   missing. A token that resolves in a sibling root is a correct cross-repo citation, not a
   defect, and must be reported as such rather than as an absence.
3. **A repo-wide ignore list** for the small residue of genuinely-correct citations that
   remain unresolvable by the two mechanical steps above (a doc referencing something
   outside any declared root, for instance). This is what lets a first real run be driven
   to a clean baseline, so every subsequent finding is a real defect rather than accumulated
   noise. The list is flat and applies uniformly to every registered doc — v1 does not scope
   an ignore entry to a single document, so a token added to silence one doc's false
   positive also silences that same token everywhere else it appears. Known v1 limitation,
   not an oversight: a future per-doc scoping would tighten this without changing the
   underlying clean-baseline guarantee.

Without all three, the exact failure this mechanism exists to catch is indistinguishable
from a wall of false positives, and a gate that cries wolf gets ignored — which defeats
the entire point of adding it.

### Historical replay — proof the mechanism catches the incident it was built for, without inventing new false positives

A synthetic test fixture reproducing "a human-facing doc cites a path a later commit
emptied" proves the matching logic works, but a self-authored fixture cannot fail — it
proves the regex fires on something, not that the mechanism solves the real incident that
motivated it. The stronger proof is a **historical replay**: check out the doc and the
tree exactly as they stood at the commit where the real incident happened, and run content
verification against that historical state.

Replayed this way, the result holds **both directions**: the positive half confirms the
mechanism flags the exact path that was, in historical fact, absent at that commit and
cited by the doc anyway — the true incident, not a stand-in for it. The negative half
confirms the same replay does **not** flag the correct-but-cross-repo citations present in
that same historical tree — proving the negative surface above is doing real work, not
merely permitting the positive case to pass by coincidence. Proving both halves together is
what distinguishes "the matcher fires on something" from "the mechanism solves the
motivating incident without manufacturing new noise."

### Deliberately out of v1 scope

Three classes of check are recorded here as **deliberately excluded from v1**, not silently
omitted: prose claims a doc makes about its own subject matter (asserting something is true
without citing a checkable token), re-derivation of counts a doc states inline (a doc
asserting a specific file or line count that would require recomputing the count to check),
and diffing a doc's content against a separately-maintained canonical description of the
same subject matter elsewhere in the repo. All three are judgment-shaped or materially more
expensive than the mechanical, unambiguously-falsifiable subset v1 ships; they are a
plausible extension, not an oversight.

## Why one gate carries two signal types, and why judgment points are per-doc, not per-finding

Staleness and content verification are surfaced together as **one doc-health gate with two
signal types**, each finding carrying its own reason, rather than as two separate ceremony
steps to reconcile. A document can be fresh-but-wrong (recently touched, but citing
something no longer true) or stale-but-still-accurate (untouched for a long stretch, but
everything it says still holds) — collapsing the two into a single "needs attention"
flag would erase a distinction the reader actually needs; keeping them as two full separate
ceremony batteries would double the surfaces to reconcile for no benefit. One gate, two
labeled reasons, is the right granularity.

**The mechanism reuses an existing primitive rather than inventing a third disposition
class.** An advisory verdict-array entry (never blocking) carries the evidence — for
staleness: commits-since, days-since, last-touch identity, and the areas of the repo that
changed in that window; for verification: the specific citation, its location, and why it
failed — into the ceremony's render. Separately, a `judgment_points[]` entry gates a
follow-on directive: the directive cannot proceed until an explicit, human-recorded
disposition is set, and no disposition is ever auto-picked. This is a complete,
code-enforced implementation of "mandatory but non-blocking" using two primitives that
already exist for other gates in the same ceremony — it needed no new class, because the
distinction the earlier design reached for (advisory vs. hard-blocking) was never the axis
that mattered; the axis that matters is halts-the-ceremony vs. requires-an-explicit-
disposition-before-a-later-step-can-proceed, and that axis was already fully served.

**Judgment-point cardinality is bound to the doc, not to the finding.** Staleness findings
are naturally bounded — a repo's human-facing doc registry is a handful of files, so one
judgment point per stale doc stays small. Content-verification findings are not bounded the
same way: a single document can carry dozens of path-shaped citations, and giving each
citation its own judgment point would reproduce, on an unbounded set, the exact "just
force through it" muscle-memory failure this design exists to prevent — a human facing
dozens of individually-gated micro-decisions learns to wave them through rather than read
them. The fix is to keep cardinality at the document, not the citation: exactly one
judgment point per document that carries *any* verification finding, with the full finding
list attached to that single entry as evidence. A human disposes of the document once,
informed by everything wrong with it, rather than clicking through each citation
individually. Both signal types share the same per-doc judgment point without either being
flattened into the other, because the underlying array already supports one entry per item
with an attached evidence payload — heterogeneous evidence through one shape, not two
parallel gates.

## Why "staleness" cannot be built as a days-only measure, and why this is git-derived rather than mtime-derived

Two adjacent design choices are worth stating explicitly, because both are instances of a
general pattern that recurs across this plugin wherever something needs to be checked for
freshness or drift.

**A single days-since-last-touch measure is not enough on its own.** A sibling rotational
architecture-audit staleness gate in this same ceremony stack uses exactly that shape — a
pure days-since-last-audit clock, with no second signal — and it is the right design *for
that gate*, because the audit it triggers is itself calendar-paced and doesn't need a
volume signal. This gate's target is different:
human-facing doc freshness needs to resist both a quiet-repo calendar nag and a busy-repo
volume nag simultaneously, which is exactly the case the AND-of-two-thresholds design above
exists to cover. The two designs are not in tension — each is the right shape for what it
watches.

**Freshness here is derived from commit history, never from filesystem modification time.**
This design deliberately follows the same reasoning a sibling drift-detection mechanism in
this plugin applies elsewhere: it hashes content rather than trusting mtime or mere
presence, because modification time is a well-known false-negative-prone proxy for "has
this actually changed" — a fresh checkout or a fresh clone resets every file's mtime to the
checkout moment regardless of when its content was actually last authored, so an
mtime-based staleness check that works within one long-lived working copy silently stops
working the moment anyone re-clones or re-checks-out the repo. Deriving `commits_since` and
`days_since` from git commit history rather than from the filesystem avoids that failure
class by construction, in the same family as that sibling mechanism's own
content-over-mtime choice: prefer the content-derived signal, because the timestamp proxy
is checkout-sensitive and the content-derived one is not.

**Content verification is a distinct mechanism from generic reference-integrity checking,
not an extension of it.** A separate reference-integrity checker elsewhere in the
engineering ops layer already does a structurally similar job for a different artifact
class — asserting that plan-internal backlinks aren't dangling, rather than that
human-facing document citations resolve. Content verification here is a separate mechanism
rather than a broadened version of that check, for two reasons: the target artifact class
is different (README/INSTALL/CONTEXT-style prose, not plan-to-plan backlinks), and the
negative-surface requirement above — the exclusion set, cross-repo resolution, and per-doc
ignore list — has no equivalent need in the plan-backlink case, where every valid target
lives inside the same repo the checker already knows how to enumerate. A human-facing doc
routinely cites paths that are correct but live in a sibling repo, which a plan backlink
structurally cannot do; that asymmetry is why this is a new, purpose-built mechanism rather
than a generalization of the existing one.

## Reused primitive: `judgment_points[]`

The per-doc gating mechanism described above (one judgment point per document, never
auto-resolved, evidence attached rather than duplicated) is not a bespoke invention for
this gate — it is a direct consumer of a `judgment_points[]` primitive shared across this
plugin's ceremony machinery: an advisory verdict-array entry carries the evidence for a
finding, and a paired `judgment_points[]` entry names a question, cites that evidence by
pointer, and enumerates the concrete dispositions available — gating a follow-on step until
an explicit, human-recorded disposition is set, with no automated consumer ever deriving a
disposition from a recommendation. This gate applies that shared shape exactly as it is
used everywhere else it appears.

## A staged-decision precedent worth knowing about

A different artifact class elsewhere in this plugin — a decision deliberately staged
inside a plan or spec document pending later ratification, rather than a document whose
freshness is measured passively — uses the same underlying shape this gate does: a fixed
default threshold, overridable per instance, checked automatically at a ceremony gate
rather than relying on someone remembering to come back to it. The artifact class differs
entirely (a staged decision vs. a document's own freshness), but the design shape — default
threshold, explicit override, mechanical check at a known cadence point, never silently
auto-resolved — recurs, and recognizing the pattern is useful the next time a similar
"someone has to remember to come back to this" class of gap turns up.
