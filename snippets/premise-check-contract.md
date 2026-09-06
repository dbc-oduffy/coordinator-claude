<!-- canonical source for premise-check-contract — edit here, then run bin/verify-snippet-sync premise-check-contract --fix -->
<!-- consumers: see bin/snippet-registry list-consumers premise-check-contract -->

<!-- BEGIN premise-check-contract (synced from snippets/premise-check-contract.md) -->
## Premise Check Contract

A premise check asks one question, in five classes, over a plan's cited paths, symbols, refs and
in-repo behaviour claims: **does this plan's premise actually hold against the tree right now?**
It is written to be INLINED into a dispatch brief, never dispatched as its own agent — the
`PLUGIN_AGENTS` default-off constraint means an `agentType` the harness cannot resolve silently
degrades to a generic agent wearing the role's label, which reuses the persona and loses the
check. Whatever consumes this text must inline it directly.

**Classes 1 and 2 — paths and symbols (mechanical).** For every cited in-repo path: does it
exist? For every cited `file:line` / `file:symbol` claim: does the symbol exist in that file? This
is the same check plan-coverage-checker's Lens 3 already runs (`ls`-check cited paths,
`Read`-verify cited claims, grep backtick-quoted in-repo constants) — it is not re-derived here.

**Tolerance rule, carried over verbatim, do not recalibrate:** same-file line-number drift alone
(same file, same symbol, shifted line number) is tolerated and is NOT a finding; a missing file or
an absent symbol is a real finding.

**Class 3 — refs (mechanical, new).** A cited branch, commit or tag is checked with
`git branch -r` / `git rev-parse --verify`. A peer-repo ref MUST be cited `<repo>@<ref>` — a bare
"verified against HEAD" cannot distinguish `main` from someone's unmerged branch, and the failure
is silent in both directions. See tripwire `VERIFIED-AGAINST-HEAD-DOES-NOT-NAME-A-BRANCH`.

**Class 5 — semantics (judgment, new).** A claim that code EXISTS is not a claim it BEHAVES as
described. This class fires on either of two conditions:

1. The repo carries a surface that FORBIDS the plan's assumption — a wiki page that says so, or a
   sanctioned resolver that raises instead of defaulting.
2. Defect vocabulary (wrong, broken, fails, silently, unsafely) appears in the plan's description
   of in-repo behaviour — the cheaper, second firing condition.

On either trigger, open the cited symbol and compare its actual behaviour against the plan's claim
before trusting it — a substrate pre-flight verifies existence, not described behaviour, so a
claim that code EXISTS is never treated as a claim it BEHAVES as described. Where NEITHER surface
fires, class 5 degrades to reviewer judgment and the verdict must say so plainly rather than
guessing — this asymmetry is why the pass reports and does not refuse.

**Class 5 is PROVISIONAL.** Classes 1-3 generalize from a measured corpus; class 5's second firing
condition (defect vocabulary) generalizes from ONE incident (2026-07-27: a plan claimed a model
resolver's default was defective when it was in fact a PM-ratified asymmetry, caught only because
a defect-vocabulary trigger like this one would have flagged it for a symbol read). That is
enough to ship it as an acceptance criterion and not enough to call the trigger calibrated. The
owner of the standing blitz-conversion re-measurement effort re-checks the trigger against a
class-5 firing log (every class-5 finding, with whether the subsequent symbol read confirmed or
refuted the plan's claim) before the PROVISIONAL mark comes off. Until then, a class-5 finding
carries the same weight as any other finding — only the TRIGGER is under review, not the finding's
validity.

**Mechanical vs. judgment split, carried over verbatim.** Classes 1, 2 and 3 are mechanical:
existence either holds or does not. Class 5 is judgment: it requires reading a symbol's actual
behaviour and comparing it to a claim. A verdict that mixes the two without labeling which is
which loses the distinction that lets a reader gauge rework altitude at a glance.

**Reporting, never refusing.** State plainly, in every verdict, which class(es) were checked and
what was found — name the check in words (path, symbol, ref, semantic, instrument), never a bare
class number: a number alone reads as more precise than the taxonomy underneath it actually is.
**A premise check never claims plan correctness.** It catches a class of false premise; a plan
whose every citation resolves against the tree can still be wrong. This pass reports what it
checked and what it found; it does not ratify the plan, and it does not refuse to report a partial
or degraded result — a class-5 miss with no forbidding surface and no defect vocabulary is
reported as "class 5 not applicable, degrades to reviewer judgment," not withheld.
<!-- END premise-check-contract -->
