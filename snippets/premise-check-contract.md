<!-- canonical source for premise-check-contract — edit here, then run bin/verify-snippet-sync premise-check-contract --fix -->
<!-- consumers: see bin/snippet-registry list-consumers premise-check-contract -->

<!-- BEGIN premise-check-contract (synced from snippets/premise-check-contract.md) -->
## Premise Check Contract — Classes 1-3 (Mechanical)

A premise check asks one question, over a plan's cited paths, symbols and refs:
**does this plan's premise actually hold against the tree right now?** (Its
sibling snippet, `instrument-can-report-red.md`, asks the companion question for a falsifier
itself: is its verdict wired to its exit path?) The judgment half — class 5, semantics — is a
separate block, `premise-check-class-5-semantics.md`, delivered only to consumers that enact it.
It is written to be INLINED into a dispatch brief, never dispatched as its own agent — the
`PLUGIN_AGENTS` default-off constraint means an `agentType` the harness cannot resolve silently
degrades to a generic agent wearing the role's label, which reuses the persona and loses the
check. Whatever consumes this text must inline it directly.

**Classes 1 and 2 — paths and symbols (mechanical).** For every cited in-repo path: does it
exist? For every cited `file:line` / `file:symbol` claim: does the symbol exist in that file? This
is the same check plan-coverage-checker's Lens 3 already runs (`ls`-check cited paths,
`Read`-verify cited claims, grep backtick-quoted in-repo constants) — it is not re-derived here.

**Why `ls`/`Read`/`grep` and not the symbol-graph tools.** `project_referencers` and
`project_symbol_callers` would answer classes 1 and 2 more precisely, and they are deliberately not
used: this text is INLINED into a dispatch brief inside a workflow, and an MCP tool surface is not
guaranteed to be present for the agent that receives it — a check that silently degrades when a tool
is missing is worse than one built from primitives that are always there. The project-rag index is
also a projection that can lag the tree (1494 commits behind at the time this shipped), and a premise
check that reads a stale projection would report the tree as it was, which is the exact failure it
exists to catch. Existing checker agents ARE reused: this contract carries plan-coverage-checker's
Lens 3 calibration over verbatim rather than re-deriving it, and Lens 3 consumes this same text.

**Tolerance rule, carried over verbatim, do not recalibrate:** same-file line-number drift alone
(same file, same symbol, shifted line number) is tolerated and is NOT a finding; a missing file or
an absent symbol is a real finding.

**AN ABSENCE IS EVIDENCE ONLY IF THE INSTRUMENT COULD HAVE SEEN PRESENCE.** `find`, `ls`,
`test -f` and a failed Read answer the worktree of this box. Before recording an absence the plan
rests on, name what would have made the thing visible and check THAT: a sparse cone hides tracked
paths (`git ls-files`), a blobless clone hides contents (`git show HEAD:<path>`), `.gitignore`
hides build output whose build target is tracked (`git check-ignore -v`, then find the build), and
a registry on another machine hides a whole repo (say UNDECIDABLE-HERE and name the host). Record
the command you actually ran. Re-running the author's `find` endorses the author's blind spot:
two parties running one wrong instrument agree with each other. Tripwire:
`AN-ABSENCE-IS-EVIDENCE-ONLY-IF-THE-INSTRUMENT-COULD-HAVE-SEEN-PRESENCE`.

**Class 3 — refs (mechanical, new).** A cited branch, commit or tag is checked with
`git branch -r` / `git rev-parse --verify`. A peer-repo ref MUST be cited `<repo>@<ref>` — a bare
"verified against HEAD" cannot distinguish `main` from someone's unmerged branch, and the failure
is silent in both directions. See tripwire `VERIFIED-AGAINST-HEAD-DOES-NOT-NAME-A-BRANCH`.

**Reporting, never refusing.** State plainly, in every verdict, which class(es) were checked and
what was found — name the check in words (path, symbol, ref, instrument), never a bare
class number: a number alone reads as more precise than the taxonomy underneath it actually is.
**A premise check never claims plan correctness.** It catches a class of false premise; a plan
whose every citation resolves against the tree can still be wrong. This pass reports what it
checked and what it found; it does not ratify the plan, and it does not refuse to report a partial
or degraded result.
<!-- END premise-check-contract -->
