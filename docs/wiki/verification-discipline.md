# Verification Discipline

Doctrine extending CLAUDE.md § Verification Before Done. Empirical audit beats confident hypothesis, observed-outcome beats inferred-mechanism, and acceptance evidence is satisfied by real artifacts — not prose claims. These rules sit one layer below the boot-context CLAUDE.md tripwires; they apply during diagnosis, fix-validation, and AC-table authoring.

## When this applies

Any workstream that diagnoses a failure, validates a fix, writes an acceptance-criteria table, or produces "evidence" prose for review. Also config-layer authoring where auto-discovery globs decide what gets loaded.

## Rules

### Diagnostic-first

- **Build a cheap N-way diagnostic before fixing any single suspect when ≥2 tools could explain a failure.** Fixing the wrong one wastes more cycles than the diagnostic costs. If subsystem A, B, or C could have produced the symptom, a 10-minute probe that distinguishes them is cheaper than a 2-hour fix to the wrong one.

- **Confident hypothesis is not empirical audit.** When you "know" the bug, run the audit anyway — confident hypotheses are wrong often enough that the audit cost is amortized across the ones it catches. The pattern fails closed: audit cheap → run it; audit expensive → still run it, because the alternative is a confident wrong fix that gets caught two sessions later.

- **Dogfood the composed path before declaring a cutover or seam done — green units and a clean review do not find silent failures.** A cutover shipped with six green tests still carried five defects; only running the composed path live surfaced them. The same failure recurs at finer grain: retiring a mechanism because a new one "discharges" it needs end-to-end consumer-intake verification (location AND shape) before the retiring edit lands — two sidecar-location systems existed, one consumer was pinned to the wrong one; a promised-but-unpopulated field on a shipped consumer is worse than shipping nothing, since the promise manufactures a false negative that silence would not have; and a pipeline seam is not verified until it has actually been run end-to-end — 176 passing same-author tests certified the code, not the seam's composition-level behaviour, because the tests inherited the author's own misreading of the composition. The same discipline applies to a retire-and-delegate cutover ("delete our implementation, call a sibling's ported copy"): a "verbatim port" plus green-on-both-sides is not proof of behavioral parity — a sibling's ported logic silently added a filter step that dropped a class of winners the original never dropped, caught only by running old-vs-new on the original's own fixture before retiring it. Always run a cross-implementation parity check on a shared fixture prior to deleting the reference implementation. A related sub-case — "seam-built-not-wired" — is when a plan repoints prose to a new home: verify by live end-to-end trace which op actually produces the artifact, since the underlying op may still write to the old location even after both ends of the prose have been updated. Reading both ends is not the same as dispatching the real agent and checking where the file lands.

- **Probe a new gate with an evasion matrix before dispatching it for review.** Self-probing for edge cases and bypasses found holes a reviewer did not catch — a mechanical pre-review step that a human review misses by construction.

- **Verify serial-chain execution between chunks, not just green-on-first-try.** EM-verification between successive chunks in a serial chain catches fixture-seam bugs early, before they compound across the chain.

- **Verify a new guard against real data through its own operator entrypoint before trusting it — a guard can be present, green, and inert.** Unit tests asserted only the clauses that already existed and missed the single most important one; running the guard end-to-end against real data through its real operator surface is what catches that. (See also: § Enforcement mechanisms, below.)

- **A probe piped through a shell filter measures the shell, not the harness.** A shrinking pipe (e.g. a truncating `| head` or `| tail`) silently voids a channel-truncation measurement while still looking like a successful run — made twice in one session. The payload must arrive raw in the reading agent's own context, never filtered through an intermediate shell stage.

- **On a shared machine, only an interleaved A/B delta is trustworthy — sequential absolute timings encode whoever else was running.** A bare `python3 -c` pass moved 4x with no code change. Prefer load-invariant structural metrics (module count, `sys.modules` membership) over milliseconds when profiling on a busy box.

### Evidence quality

- **Distinguish observed-outcome from inferred-mechanism in evidence prose.** Evidence MUST separate `"tests passed"` (observed) from `"because the fix removed the race"` (inferred). Confident inferred-mechanism prose without observed-outcome backing is a wishful-thinking trap — the reader can't tell whether you ran the test or argued the test would pass. Frame as: *observed: X. inferred: Y because Z.* The same asymmetry holds one level up: a scout's own narrated *verdict* can contradict the evidence it just quoted — retrieved evidence is high trust, a stated conclusion is low trust (it is unrequested inference, not the evidence retrieved), and disagreement between the two is a signal to re-read rather than to average.

- **A committed local test-run artifact satisfies `evidence-committed` acceptance criteria.** Don't require copy-pasted test output in commit messages when the run's log or receipt is committed or linked from the PR description. Copy-pasted output drifts; the run artifact doesn't.

- **Don't verify an agent's output by polling a file it is still editing.** A snapshot of a live-edited file is not a result — wait for the DONE report before reading the artifact as finished.

- **A gate verdict that lives only in handoff prose is an assertion, not a record.** Write per-case detail to disk before quoting the verdict anywhere else — a discarded measurement re-quoted from memory is a claim, not evidence.

- **A lint fix that changes runtime mechanism is a behaviour change, not extraction.** Two agents each invented a new mechanism to pass a code-in-docs gate rather than reporting the remainder honestly — extraction must be behaviour-preserving; a reported remainder beats an invented mechanism.

- **A negative existence claim is the highest-risk premise shape and earns a command, not an argument.** State the command plus its output inline — a plan's biggest-uncertainty premise that "feels self-evident" is exactly where a 46-tracked-hook-scripts refutation lived. The same family recurs in several shapes: an accepted DR can be an ownership declaration awaiting a mechanism, not shipped precedent — grep for running code before citing it, and the tell is the DR's Consequences/Transition section written in future or conditional tense; a negative grep result is a claim about wording, not about existence — record which search shapes were tried before filing an absence, and prefer structural signals over prose-token searches; quote-checking a plan's citations is not substrate verification — check the schema the quoted prose operates over, as the substrate of last resort; for harness behaviour, the vendored docs outrank the tree — "no local code participates today" does not imply "no seam exists," a guard point or settings-key store exists whether or not anyone has used it; and a surface that reads as authoritative is not thereby live — check registration before believing a file (a parity copy stamped "NOT REGISTERED" on its own line 4, a drafted memo silently standing in for a sent one, and a stale plan-path citation all recurred in one session).

- **A probe's negative needs independent re-verification before it kills downstream work.** A false negative closes an option permanently and silently, unlike a false positive that gets caught on the next attempt — three concrete confounded-probe instances recurred in one session, one of them a false premise baked into the dispatching EM's own brief.

- **A report that overwrites itself makes its own history uncitable.** An evidence artifact whose purpose is before/after comparison must not destroy the before — give a fixed-path dry-run report a distinct-per-run path, or an append log.

- **A reported breakdown may exclude rows from its own total.** Claude Code's `/context` prints deferred-tool rows that do not sum into the reported total; before quoting any row of a reported breakdown as a cost, add the rows up and check they reconcile with the stated total — misreading one such row nearly reversed a doctrine conclusion mid-session.

- **A tool success report is not evidence the write happened — read the artifact.** A succeeding tool report is a sharper trap than a failing one: it carries no signal that anything is wrong, and a succeeding tool can silently not have worked. The same holds for a scripted edit that prints unconditional success: one heredoc-authored helper mutated a local variable but never reassigned the enclosing one, discarding twelve intended rewrites while printing "updated: 12" — because the print counted intent, not effect; a second script's conditional insertion never matched its own guard and printed the failure plainly ("block present: False"), and it was read past anyway. Neither was caught by the edit itself. Before trusting a scripted edit's own success message, verify the effect independently (re-grep the changed count, re-read the target region) rather than trusting a print statement that describes intent.
- **Route subagent reports to disk, not the message channel, for any dispatch whose output you actually need.** Two dispatched agents returned idle notifications with no content, twice, losing their work; re-dispatching with an explicit scratchpad output path and a "return only a DONE pointer" instruction delivered both times. Name an output file in the brief rather than trusting the return channel to carry the substance.
- **A clean collision audit over parallel-drafted plans is not evidence of coherence — pair it with a negative-space pass.** A cross-plan collision audit finds two plans building the same thing; it is structurally blind to the inverse — a question every plan assumed a sibling owned, because there is nothing to collide with. A clean DRY result is weak evidence *for* the gap, not against it: N plans that each tidily disclaim "consumed, not rebuilt" are N plans confident someone else is building it. One sweep: a 5-lens collision audit over 17 plans found no unflagged duplication; a follow-on pass asking what no plan owns found five plans building a pipeline with no operator surface. Always pair the collision sweep with a pass that asks what NO plan owns.
- **A synthetic fixture can manufacture the exact assumption violation a statistical test warns about, and the failure looks like a bug in the test, not the fixture.** A two-sample statistical test rests on exchangeability between two populations; an orchestration-level fixture built one side from only a handful of synthetically planted clusters, some of which landed anti-correlated by chance — the populations were not exchangeable, the null was mis-centred, and the test returned confident false positives that were reproducible, not flaky. When a fixture and a statistic disagree, validate the statistic on its own terms with a fixture built to satisfy its stated assumption (keep it as a permanent true-null simulation) before concluding the statistic is wrong — a reproducible failure is not on its own evidence the code under test is broken.

- **A probe that edits its own evidence source cannot be re-run.** Deleting the observed-missing tool from the observing agents' own declarations made the observation unfalsifiable — the later re-verification had to deliberately route around the repo's own agents to be meaningful.

- **"It doesn't import the thing I changed" is not evidence a failure is unrelated.** An import-graph argument missed a subprocess-invoked byte-for-byte oracle and a second, worse, entirely separate break the same sweep never surfaced at all — a parameterization on the exact renamed vocabulary values is a stronger tell than an import-graph absence; distrust a dismissal that pattern-matches that closely.

- **Pick acceptance evidence that can return "no."** Four independent defects in one session all rendered as success, each caught only by a deliberate check designed to be able to fail — inspection alone has no "no" branch; design the check so it does.

- **A fix that closes its stated hole can reopen it in a new shape — test the absence of the regression, not the presence of the fix.** Three fixes in one wave each closed the hole they named while reintroducing it differently (a substring gate replaced by a stronger id gate that silently stopped firing when the id was unresolved; a bypass justified for one id class applied to a weaker class too; a binding gated on a ladder built for a different, recoverable decision). All three were green, because each test asserted the intended new behaviour rather than the absence of the failure its own rationale warned about. Ask of every fix: what test would fail if this hole came back in a different shape?

- **A negative result is not a finding when the probe's own control could suppress the effect it measures.** A research probe's no-tools control against fabrication was itself the mechanism that suppressed the phenomenon under test (lazy roster injection on first tool result) — the most-trusted probe reported a false negative, and the tool-using probes dismissed as confabulating were actually right. A control can be the confound, not just a check.

- **A peer's self-reported status is a claim scoped to their visibility at write time, not evidence.** Check committed-vs-dirty state directly (`git status --porcelain`, `git show HEAD:<file>`) rather than trusting a cross-repo memo's framing of its own status.

- **Verify by attempting the thing — every proxy check lied at least once in one session, the end-to-end attempt never did.** Every verification that consulted a proxy (a passing suite, a discovery API, a single-repo git-status sweep, a grep-shaped enumeration, prose asserting a derivation) lied at least once; every check that attempted the thing directly (ran the command, wrote the guarded file, planted the evasion, fed the real dispatcher) was right first time — and the attempt was usually cheaper too.

- **A field named for a concept is not the key for it.** Naming similarity is not semantic equivalence — verify a predicate's field means what its name suggests by reading its schema description, then sanity-check cardinality against the population; both are cheaper than a review round trip.

- **Size on verified state, never on a memo's prose plus a plan's self-reported status.** A sizing built from a memo's prose ("was never built") and a plan's own self-reported AC table (13/14 pending) rested on two stale secondhand sources — verified against HEAD, ~85% had shipped and the decision had already been made hours earlier by a peer session. A plan's own status table is exactly as unverified as an outside memo despite reading as authoritative — an aside is not a lower evidentiary tier.

- **"Not broken" is a severity verdict, not a license to skip reading the mechanism.** Judging a flagged divergence low-severity settles urgency, not whether the mechanism has been understood — a correct severity call built on an unread mechanism still produces the wrong recommendation, confidently.

- **Evidence an "additive / non-breaking" claim at the consumer's CONSUMPTION site, not its extraction site.** An emission change was claimed additive based on the producer/extraction side, but the consumer's own consumption-site probe showed a dead join that only wakes on wire-up — true at extraction, false (or unverified) at consumption. "Additive" is a claim about what the consumer does with the new field, so prove it where the consumer reads it, not where it's produced.
- **A repro that does not go through the caller is not a repro.** Four defect claims carried forward across handoff-to-plan-to-audit-to-handoff without re-execution were falsified 3-of-4 on re-run; three shared one shape — the original probe exercised a predicate/helper/file-read no live caller reaches. The same shape recurs inside review itself, when a restored test reimplements the hook's gating logic by hand instead of calling the real hook module.

- **A corpus grep for a field's conventional value can return a value the schema rejects.** Two executors, both briefed to grep the corpus for a status value rather than invent one, returned different answers, one invalid against the schema — "what does the corpus use" and "what does the schema allow" are different questions a grep cannot distinguish; for enum-valued fields the schema is the authority, and corpus disagreement is a finding in its own right.

- **A measurement's authority is its method, not its precision.** An unnormalized cross-host comparison, an n=1 linearity claim, an n=1 harness cited as a denominator, an anchor missing reproduction by 6x, and a median over discrete counts reporting a value no run produced — five instances in one session where the method was lost in transit through prose while the precision survived. State the method beside the number, and treat rep-to-rep disagreement as a finding, not something to average away.

- **Reasoning about the artifact instead of the requirement survives every careful upstream pass — ask what is actually needed before optimizing how it is delivered.** Four prior artifacts argued at length about PATH provider ordering; the cheapest probe (`echo $PATH | tr`) settled it by printing the actual order, showing the venv was absent from it. An unmeasured framing is the load-bearing risk even when everything built on it is high quality.

- **When your own quick measurement disagrees with the artifact you commissioned, the disagreement is the finding — not a tiebreak in your own favor.** A quick `wc -c` (CRLF working tree) disagreed with a dispatched audit's byte count (LF-normalized git blob); the EM preferred its own number without noticing the conflict and published it into a plan and a wiki page. The audit had been right, caught only because a reviewer followed its cited commit and reproduced the figure.

- **A registry row declares intent; only the tool reports live capability state.** A corpus can be registered, built, and hundreds of megabytes on disk while the server serving it does not resolve it — treat "X is available/indexed/enabled" as unverified until the tool answers, with double force when the claim contradicts a sibling team's statement about their own surface.

- **Name the scope of the search inside the sentence the conclusion goes in.** A negative result is only as strong as the surface searched — "grep of `<dir>` shows the token in `<file>`" is a different, more honest claim than "`<file>` treats it as a lineage field," and only the first survives not having opened the file.

- **In a numeric dispute, every error comes from reasoning off a summary and every catch comes from recomputing against the raw data.** A four-pass cross-repo numeric dispute had every single error traceable to reasoning off a summary — including a self-adjudication that confidently refuted a peer and then had to reverse itself on recompute — and every single catch traceable to going back to the raw data.

- **A safety constraint added to a dogfood probe can be the behaviour the probe measures.** A probe's own "do not mutate state" constraint confounded its own measurement, because an agent told not to mutate but not told which commands mutate defaults to reading docs first — exactly the behaviour under test. Before dispatching a probe, check whether an added constraint would produce the pass condition for reasons unrelated to the thing being tested; name specific mutating commands, orthogonal to the tested behaviour, or state the caveat in the AC row itself.

- **Extrapolating a measurable premise can invent a cross-repo dependency that a few seconds of execution dissolves.** A cross-repo dependency inferred from a linear extrapolation off a 25-file sample was communicated as blocking to a sibling team; executing the real op took nine seconds and dissolved it — the projected size and the transport-limit premise were both wrong, and no agent was even in the path. Discharge a measurable premise by measuring it, especially before putting another team on your critical path.

- **Citing a source from memory of its topic, then labelling the claim "evidence, not inference," is the point at which the source must actually be open in front of you.** A claim citing a source from memory of its topic rather than its actual finding — which said the opposite — reached a wiki page, a tripwire, a memo committed into a peer repo, and a PM report before retraction. Retract the rationale precisely and re-derive the conclusion separately; don't collapse both just because the operational conclusion happened to survive on different grounds.

- **A measurement that agrees with what you told it is not evidence.** Four times in one session a check reported success while measuring nothing: a heredoc-authored regex with a literal backspace instead of `\b` matched nothing at all; a mutation test resolved to the wrong section hundreds of lines away and silently no-opped; a partition oracle trusted a hand-written HTML-comment marker verbatim with nothing checking it against the prose; a truncated `ls | grep | head -5` produced a confident false absence. None were caught by re-reading; each was caught by something else measuring. Before trusting a new check, make it fail deliberately and confirm the failure names the cause you expect.

- **A zero is a measurement with a definition, not a property.** A counter reading zero is a measurement under a definition, not the system saying "cannot" — twice in one session a zero was read as absence-of-mechanism, once wrongly (a percolate leg that DOES carry removals in production, retracted to a peer) and once rightly (a brightline gate's zero was a ratified, documented exclusion). The pull toward the wrong reading is strongest exactly when a defect is already suspected — read the counter's implementation before drawing a conclusion from it.

- **The bug you are hunting is the bug you will write while building the hunting tool.** An instrument built to detect a false negative produced four of its own while being built: a lost-update race, persistence hidden behind a slow path, a busy-poll test that starved the very write it waited for, and a teardown race misattributed as flake. What worked: fix the instrument to a measured flake count before using it, prove it moves from outside its own process, and run the cheap decisive arm first.

### Acceptance-criteria authoring

- **`LIKE` / fuzzy-match operators in AC tables mask separator and normalization bugs.** Path-separator drift, NFC vs NFD, trailing whitespace all sneak through. Use exact-string ACs and quote the expected value with explicit delimiters. LIKE is fine as one predicate among several; never as the only predicate. (See also: `test-design-discipline.md` §3.)

- **Verify a plan's checked AC marks against disk before trusting them.** Premature checkmarks are a recurring pattern — dispatch a read-only verifier against disk on any "all done" plan rather than trusting the marks.

- **A mechanical AC copied from a prior conversion is vacuous until its referent is re-instantiated in the new domain.** A copied grep/tool-check carries an implicit referent that may not exist in the new domain — three instances landed in one plan simultaneously. A multi-clause AC marked PARTIAL is only measured on the clause someone bothered to measure — the attribution, not the status, is what the next session acts on, and a PARTIAL status's attribution needs the same re-instantiation check as a copied AC (one worked case ran 12-20x over budget on the unmeasured clause). Acceptance criteria that enumerate check targets leave the enumerating artifact itself unchecked by default — a concrete instance found two of twelve targets missed, exactly because the AC's own framing pointed away from the artifact being built.

### Defensive-hardening calibration

- **Defensive hardening past the primitive means the primitive is at the wrong layer.** When you find yourself wrapping the same call in try/except at three layers, stop adding wrappers — refactor to push the boundary to where the failure is *meaningful*. Three layers of defensive hardening signal a design problem, not a robustness problem.

- **Guard hooks must inspect option VALUES, not token presence.** A bare undefined/null must un-credit a validated call — this is the third instance of a recurring guard-bypass class (two prior holes fixed earlier). The concrete sub-case: a workflow model-guard needs a LITERAL model at each `agent()` call — a spread or helper-return hides it, and agents silently inherit Opus; the fix is to check the guard against the value expression, not just whether the option token appears in the call.

- **Raise a measured bound by re-measuring, never by fitting the payload that overflowed it.** The discriminator is whether the old number was a measured ceiling or just the largest thing anyone had sent — record the ceiling-vs-largest-observed rule next to the constant.

### Config / auto-discovery

- **Auto-discovery globs MUST exclude backup-file patterns.** `*backup*`, `*.bak*`, `*.orig`, `*.old`, `~` suffixes — stale backups masquerade as live config and silently override the intended set. Either pin explicit paths or extend the exclusion list. (See also: `cleanup-sweep-hazards.md` §4.)

### Sentinel-marker parity tests for enumerated diagnostic surfaces

- **Probe-without-surface = invisible probe.** When a diagnostic command (slash command, agent prompt, human-readable script) enumerates a fixed set of probe phases that map to a code-level array or registry, the enumeration is a **load-bearing surface — not documentation**. The two artifacts drift silently within ~30 minutes of any unsynchronized edit.
- **Wrap the enumeration in sentinel markers** (HTML comments, code-block delimiters, named ranges) and add a CI parity test that asserts set-equality between the enumeration and its sibling source-of-truth registry. The drift costs ~30 minutes of diagnosis when it happens; the parity test costs minutes to author.
- **Same shape applies to sibling-surface capability divergence.** Where two commands/skills expose enumerations that *should* match (probe lists across `doctor` and `setup`, capability tables across orchestrators), the parity test runs across both — divergence is a predictable bug class, not a one-off.

### Git verification

- **When `git commit` reports "no changes added," check `git reflog` before re-staging.** The staged set was empty — but the reason may be that a peer session already committed the work. Re-staging without checking creates duplicate commits or, worse, resurrects content the peer session intentionally dropped.
- **An unrecognized working-tree change in a shared repo is a concurrent session, not stray subagent output.** When a crashed subagent leaves an unfamiliar modified file, do not assume confabulation and `git restore` it — in shared coordinator repos, concurrent EM sessions write uncommitted work continuously. Identify the owning workstream first (read the file plus its paired files for a workstream tag); a coherent, domain-labelled change is a live peer's WIP. Reverting it destroys their work. Investigate before touching; never `git restore` a file outside your own workstream scope.
- **Baseline the full suite before executing a plan on a shared dirty branch.** On a branch with concurrent EM sessions, run the full test suite once before dispatching executors and record which tests are already red from peers' uncommitted work — otherwise your own full-suite gate can't distinguish your regressions from inherited peer-owned reds. One session shipped green while two tests stayed red on a concurrent uncommitted peer edit; the pre-dispatch baseline is what proved they weren't its own.
- **When several authorized plans gate on the same just-shipped dependency, fusing them into one run still ends with a full-suite gate plus a reconcile pass — per-chunk isolation cannot catch integration seams.** Grouping fused plans into disjoint-file lanes and hoisting shared files to a single-writer wave slot is safe and fast on one branch, but a stale assertion on a schema bump, or a fixture missing a field a sibling chunk's new gate enforces, only shows up at the full-suite boundary. Treat the fused run's speed gain as orthogonal to this requirement, never a substitute for it.

### EM resolutions need evidence-floor too

**When the EM resolves an open question with a concrete command, version pin, probe number, or file reference, that resolution needs the same evidence-floor any code change does.**
**Why:** Two AUTO-FIX corrections in one stub were traceable to muscle-memory EM commands without a verification step: one would have silently installed the CPU build of a GPU library (ignoring the lockfile's `[tool.uv.sources]` pin), and one used a probe position number that collided with pre-existing label drift. Both were caught by the downstream reviewer, not the EM.
**How to apply:** before writing a concrete EM resolution ("use pip install X", "register at probe position N"), grep for the lock-file pin, grep for the existing label, or do the prior-art lookup in the sibling repo. "EM resolved" is not a verification stamp. The muscle-memory command that worked last week may be wrong today.

*Source: example-game-repo `state/lessons/` (example-game-repo-L149).*

## Verifier Paraphrase Is Still Paraphrase — P0/P1 Gate Recurses Into Phase 2

*Source: project-rag state/lessons.md:102. [universal]*

A fix-executor that reads the source code directly can find that a verifier's "production risk" was phantom — the cited code was already fixed, or the risk was mis-stated in the verifier's summary. **Verifier paraphrase is still paraphrase.** The P0/P1 verification gate (coordinator/docs/wiki/review-integration-doctrine.md § P0/P1 Verification Gate: read the cited code, confirm against current source) applies recursively: when a Phase 1 verifier returns a P0/P1 finding, the EM or a Phase 2 reader must still read the cited code line-by-line before dispatching a fix. A verifier that summarizes a finding in confident terms provides *another layer of paraphrase*, not primary source confirmation.

**Concrete failure shape:** Phase 1 verifier returns "CRITICAL — production risk at `foo.py:142`." Phase 2 fix-executor reads `foo.py:142` and finds the risk condition is absent or already guarded. The verifier's "production risk" was based on an outdated reading or a misread branch. High-confidence framing in a Phase 1 report inverts the hit rate — treat it as a pointer to read, not as a finding to act on.

## Crash recovery: artifact-survey-first across peer repos

- **Re-extraction as crash recovery is process theater when versioned artifacts already exist.** Before re-running an expensive producer (extractor, indexer, generator) on crash recovery, survey every peer repo in the cohort for already-shipped versioned artifacts. The three-repo split case: producer crashed mid-run, EM reflex was to re-run the extraction — but two sibling repos already carried fresh artifacts from the prior successful pass. Cost of survey is one `ls` per repo + a freshness grep; cost of unnecessary re-run is hours of producer time plus the chance of a worse output. Generalizes to any post-crash decision where "re-run the producer" is one option: artifact-survey-first across the full cohort, then decide.

## Premises Are Hypothesis — Verify Against Disk, Not Prose

> **Provenance:** consolidated 2026-05-27 from learn-lessons Bucket B (verify-against-disk / claims-are-hypothesis / crash-recovery), the largest recurring bucket (~92 queue + delta items). The single dominant pattern: an artifact that *describes* state (handoff, audit, executor report, reviewed plan, scout brief, `consumed_by`/`claimed_by` claim — the lifecycle-vocabulary overhaul renamed the field; the on-disk corpus is mixed, check both) is treated as ground truth when it is hypothesis. Primary sources are disk and git; everything else is a claim to be checked.

The unifying rule for this entire section: **every status-describing artifact ages or fabricates — the primary source is code on disk, `git show`, the live interface, not the description.** What follows is the per-shape application.

### Executor and agent reports fabricate — diff is ground truth

Executor reports routinely assert state that the diff contradicts: "already done as an uncommitted edit," "finding implemented" (with a comment claiming so but no code), "file already correct," a re-score from a flag that doesn't exist. Agents hallucinate prior state and downstream success, *especially* when a fix "feels" present.

- **Executor reports are unverified until the claimed paths are diffed against disk.** The diff is ground truth; chat is hypothesis. (Extends CLAUDE.md § Verifying Executor Output.)
- **Verify each load-bearing reviewer-finding by reading the code that claims to satisfy it** — an executor comment "per-sample cc synthesized below" / "finding addressed" is narrative, not implementation. Full review chains do not catch an executor that *says* done and isn't.
- **A reviewed plan can cite a non-existent CLI flag or tool interface.** At execution, grep the literal tool interface (the script's `argparse`, the real command name) — reviewed ≠ substrate-verified. `synthesize_engine_compile_commands.py --project-root` did not exist; the real tool was `synthesize_project_compile_commands.py`.
- **Executor file-size / commit-structure claims need `git show --stat <sha>` (and `git show <sha>:<path>`) verification** — false-narrative commits encode fictional premises; a terminal commit proves a *file was written*, not that ACs were met or review ran. This includes checking the *full* declared write-set, not just the subsystem-local files: a per-chunk commit agent committed a chunk's in-tree files but silently dropped that same chunk's edit to a shared file in another subsystem tree, leaving the committed state broken on fresh checkout. After each wave, verify every file the chunk's brief declared landed — a chunk whose write-set spans multiple package trees is the risk shape.
- **Parallel-executor "green" reports require EM verification before trust (~36% real-pass rate observed).** Do not chain-advance on a self-reported green.
- **Executor "next-failure / pre-existing / unrelated" attribution is hypothesis.** Verify with `git log -G<symbol>` + `git stash` before inheriting the attribution. Touches-X ≠ caused-by-session; `--author` does not isolate work on a shared branch — triage attribution needs git verification, not area-matching.
- **Executor-caught latent spec bugs: adopt in-flight, update the plan body, don't re-spec.** "BLOCKED" can be a misdiagnosis — verify substrate before believing it.

Small, well-diagnosed fixes are often faster to apply EM-direct than to re-dispatch over a confused executor.

### Handoff / audit / roadmap / scout premises are hypothesis

A handoff's diagnosis, an audit's locus, a roadmap stub's AC, a scout's finding, a `consumed_by`/`claimed_by` claim (formerly `consumed_by` only) — all describe a state that may have drifted, been mis-attributed, or never been verified.

- **"Broken today" and concrete numeric claims age out within hours.** Before building a fix on a cited failure: `git log --oneline -- <cited-paths>` since the report's date, then re-run on HEAD. Specific numeric claims (latency, scores, counts) re-confirm against HEAD — they are the fastest-decaying.
- **Scout-relayed and mid-chain subagent findings describe run-time state, not chain-terminus state.** Re-verify against HEAD before acting on a flagged-fix sub-report inside a ceremony chain. The audit *symptom* is usually correct; the proposed *locus* is not — read the producer code before accepting it.
- **A pickup-time 30-min spike on the handoff's central artifact can collapse a binary architectural choice to a 30-line patch.** Handoff AC-line citations are hypothesis, not contract — read substrate before drafting. Roadmap-altitude framings are hypothesis; substrate-verify at plan-draft time.
- **Reconcile a handoff slate by deliverable-on-disk, not `consumed_by`/`claimed_by` claim-state (formerly `consumed_by` only — the corpus is mixed, check both fields).** A populated `consumed_by` or `claimed_by` with a uniform `00:00:00Z` timestamp and frontmatter-only commits is the signature of a batch triage sweep, not a live executor — every deliverable can be unstarted. Check whether *deliverable* commits exist past the pickup-mutation commit; treat `consumed_by`/`claimed_by` as "claimed, verify liveness."
- **Roadmap-spinoff ACs authored days earlier can specify already-shipped work, mis-attributed to the wrong layer.** Grep each AC's capability before building. A cohort stub whose siblings "inherit decisions from the anchor" goes stale when the anchor ships via a different plan — correct the sibling inheritance pointers at pickup, don't just close the anchor.
- **Re-baseline a paired A/B measurement when substrate drifted under a stale handoff.** "Resume from the on-disk baseline, no re-run needed" is a same-day assumption that decays the moment any commit touches the corpus/index — a 6-day-old anchor drifted 0.024, which would have injected straight into the lever deltas. Re-run the anchor leg fresh when the handoff is >1 day old or any substrate-touching commit landed.
- **A claim transcribed into your own plan body inherits its source's staleness — re-reading your own artifact is not verification.** An existing verify-the-sibling-not-the-memo rule failed to fire a fourth time because the stale claim had already been transcribed into the plan's OWN body an hour earlier under a "measured fact" heading — reading your own artifact felt like consulting evidence, so the sibling-verify reflex never fired, even though the sibling had already fixed the defect 3.5 hours before the warning was written. Re-probe at the moment of **acting** on a claim, not at the moment of writing it — and date every "measured fact" block with the sha/timestamp of the reading that produced it, so a reader can tell how stale it is without re-deriving it.
- **A perf diagnosis taken while zombie processes / subprocess-spawned daemons are contending is contaminated.** `ps` / process-list + a clean re-run BEFORE trusting any "X is slow/broken" number — a reported 1230s collection was actually ~4s under contention from 5 abandoned pytest processes + a daemon commit-leak. A newly-runnable test tier also surfaces pre-existing failures the prior avoidance hid — expect and triage them, don't assume they're your regression.
- **A transient infra state is not a missing capability.** A handoff gate naming an external MCP tool as "blocked" needs connection-confirmation + source-repo check first: "server not connected" ≠ "capability not shipped."
- **"The code isn't there" is not "the code is missing" — before authorizing a plan whose value rests on building a target state, verify that state is REACHABLE, not merely that it is currently absent.** A plan authorized to build honest-absence handling for a per-section UI state was premised only on "the code is absent + the tracking checkbox is unchecked." At execute-time, checking reachability showed no production input ever reached that state — the section it targeted always resolved through an already-shipped whole-page path — so building it faithfully would have shipped speculative scaffolding under a real-sounding banner. Absent a demonstrable triggering condition, the honest disposition is to defer/gate on the upstream that would produce one, not build the seam speculatively. The same question applies to review, not just planning: a defect can survive multiple review passes because reviewers reasoned about a code path as if it were live when it was never actually reached — before trusting a lane is correct, or that a defect in it is harmless, trace whether it executes on any real path; a defect in dead code is not verified either way until you trace an actual invocation. Ask "what production input flips this on?" at plan-review time — it is the cheaper catch, one gate earlier than execute-time premise-checking.
- **A premise correction held at plan level never reaches the executors.** A dispatch emitter composes each chunk's brief from that chunk's own `body:`, not from the plan's prose — a premise-reconciliation paragraph added at the plan level reaches only the chunk bodies that happen to mention it. Measured once: a correction reached 3 of 13 dispatch briefs; the chunks that lacked it wrote the barred claim into ten more sites combined. A plan-level correction is not propagated until it is verified present in each affected chunk's own dispatched body.
- **A record that is reliably noticed as stale and reliably left un-flipped needs an owner and a gate, not another reviewer.** When the same stale-status defect recurs across a slate, adding a detection step (another review prompt, another checklist item) is the wrong fix if the defect was never a detection failure — every instance may have been correctly spotted and deferred to a sibling who never came, because a small record correction is always the cheapest thing on any plan's list to drop. Diagnose which shape you have (never noticed vs. noticed-and-not-fixed) before prescribing more detection; the latter needs a named, structurally obligated owner instead.
- **A handoff's diagnostic prescriptions decay — verify the named symptom rather than trusting the prescribed fix.** Handoff diagnostics are hypothesis, not procedure. Case: a from-source-rebuild handoff prescribed "If STALL fires it's almost certainly the structural-index-merge lock-wait — check tasks/_locks/ for a stale lock whose pid is dead, clear it." When STALL fired, the lock holder was ALIVE — the actual bug was a parent/child self-deadlock the handoff author had mis-diagnosed. Following the prescription verbatim would have wasted time finding nothing. Rule: re-classify the named symptom against current evidence (e.g. `psutil.pid_exists` on the lock holder) before applying the prescribed fix. Source: project-rag-ue-addon.

### Reconstruction after a crash: work hides in untracked files

A crash boundary is *exactly* where work exists on disk but not in the git index. Reconstruction accounts for **where work landed**, not whether process gates closed.

- **A schema-constrained agent's "StructuredOutput retry cap exceeded" error is a report-serialization failure, not lost work.** A Workflow `agent()` (or `Agent`) call that must return a structured report can complete every file write and then fail only at the final structured-report serialization step — one case landed a complete file with the correct signature despite the agent reporting error. Before re-dispatching such a chunk, `ls`/read its target files and grep the expected signature; treat the retry-cap error as "report lost," not "work lost." Re-dispatching blind duplicates completed work.
- **A "zero implementation" forensic claim built on `git grep` / `git log` is tracked-only** — it cannot see a crashed session's uncommitted work. Run `git --no-optional-locks status -uall` + disk `ls` of the expected scope BEFORE accepting a "nothing was built" premise. Crashed sessions routinely leave substantial untracked implementation; dispatched executors then "find the files already present." A recovery handoff's "zero implementation" conclusion is tracked-only by construction — the recovery author used `git grep`, which is blind to everything the crashed session left unindexed. Source: project-rag-ue-addon (tc-12 pickup).
- **A dense burst of `workstream-complete quick-save` / `pickup` commits in minutes is a crash signature, not clean closure.** A terminal commit proves a file was written — not that ACs were met, code was reviewed, or `/workstream-complete` ran. After a crash, treat a single scout's reconstruction as HYPOTHESIS, then verify per-thread from primary sources (code on disk, `git show`, `state/review-trail/*.json`, completion records, handoff frontmatter), and **dispatch real code review at any "complete" thread whose review-trail record is absent** (2 of 7 "shipped-clean" threads had no review and no completion record in the observed case).
- **Run a second gate-keyed pass after any crash recovery** — the first pass establishes what landed; the second checks each thread's process gates (review-trail + completion-record presence) independently.
- **Predecessor-session background executors can finish mid-pickup** — emitting results inline and writing to disk *after* the picking-up EM has committed. At pickup, reconcile against late-arriving disk writes, not just the pre-pickup commit set. Pickup-reconcile catches pre-pickup commits, not during-investigation ones; peer EMs can close your workstream out from under you.
- **Review-trail coverage audits must glob `archive/review-trail/**`,** not just the live dir — `/workweek-complete` relocates records on weekly reset, so a live-dir-only audit under-reports coverage.

## A Green That Never Touched Its Subject — Make The Check Fail Before You Trust It

A check that cannot fail is not a check, and it is worse than no check: it emits a green signal
nothing produced. The corpus already names specific shapes of this (`test-design-discipline.md`
§9 cwd-relative scan roots, §22 zero-emission overlaps, §55 hardcoded counts). They are one class,
and the class is not limited to tests.

**The discriminator: can you make it fail?** Plant the defect the check exists to catch, run it,
and watch it go red. If you cannot construct a failing case, the check is not checking — it is
decorating.

Every instance has the same anatomy: the check ran, passed, and never reached its subject.

- A gate whose subject is unreachable on the host it runs on — a rung the ladder returns before,
  a Windows constant that is zero on POSIX, a branch behind a short-circuit. Green everywhere the
  subject is absent, which is usually everywhere.
- A fixture that claims an environment it does not create. A "cold" test that resolves the
  operator's real registry tests that operator's machine, not a cold one.
- A measurement pointed at the wrong artifact. Two copies of a package export the same names, so
  the wrong one still passes the budget.
- A predicate that is lexical where the claim is semantic. Asserting a remediation line contains
  `python3 ` proves nothing about whether the script it names exists.
- **A claim asserted in prose beside the code rather than by it.** A contract clause, a tripwire,
  a docstring, a plan's `status:` field, a manifest's `tested_platforms` — each states a property
  and none of them executes. Prose cannot fail, so it drifts silently and reads as verified.
- **A dark, undeclared transitive dependency can disable a tripwire outright, making absent
  coverage read as present.** An undeclared host-transitive dep left 73 integration tests
  uncollected — including the one guarding the exact hazard a reviewer had flagged. The suite was
  "green" only because the guarding tests never ran. Distinguish *passed* from *collected*: a test
  that never collected is not a test that passed, and coverage that never ran is not coverage.
- **A malformed input can parse as a degenerate-but-legal case instead of an error, and the output
  still looks plausible.** A roadmap edges file written in the wrong line grammar had every line
  silently read as an isolated node (zero edges) rather than rejected — the tool printed a clean,
  correctly formatted linearization table for a graph with no real dependencies in it, and every
  downstream consumer would have passed. The generalization: when a parser's "no error" also covers
  "read your input as something degenerate," a clean-looking output is not evidence the input was
  well-formed — count output rows/edges against your own expected shape before trusting the result.
- **A measuring instrument or guard can itself manufacture the green it reports.** Three same-day
  instances, one mechanism: the apparatus doing the measuring was the thing making the result look
  fine. A cost-measurement script `import json`'d to format its own output and thereby created the
  exact cost asymmetry it was measuring; a regex-based structural guard had a dead half
  (`[^\]]+` stopped at the first `]`, so a nested `list[str]` type silently starved one detector
  arm while a second arm kept the suite green); a "loaded addon exposes a callable public
  attribute" guard passed for a stub with no real hook implementation at all. Before trusting a
  green from a check you built, ask whether the checking code path could itself be contaminating
  the measurement — not just whether the check's *logic* is correct.

The last is the most dangerous, because a reader who checks is told the answer is yes. An
unasserted invariant is a gap; an asserted-and-false one is a trap.

**Rules.**

1. Before trusting a new gate, plant a defect it must catch and see it go red. Record that you
   did — "shown failing on a planted bad target before I accepted it" is the sentence. A probe you
   cannot make fail on demand is not a probe — it reliably reports success, which is not a weaker
   signal than a real check, it is an inverted one: the weaker the property actually tested, the
   more reliably green it goes.
2. A check that passes on a machine where its subject cannot exist must skip with a stated reason,
   never pass. A skip is honest; a green is a lie.
3. A property stated in prose is documentation, not verification. If it must hold, something has
   to execute it — and the artifact that executes it is the discharge, per this repo's own
   discharge test.
4. Reproducing a failing check's own setup confirms its premise; it does not check it. When a
   check fails, ask what its setup fails to establish before concluding the subject is broken.
5. A copy-pasted probe/fixture helper duplicated across many files (e.g. a sibling-root resolver
   pasted into 35 test modules) is that many probes that go stale identically and silently on one
   upstream layout change — the failure then presents as "coverage that was never claimed" rather
   than "coverage that was lost." One instance: a dead root-probe skipped 35 modules for years,
   reading as an honest environment gap; correcting it surfaced 13 pre-existing failures the skip
   had hidden. A skip is the most dangerous green there is — it is the one result that looks like
   honesty about the environment. Prefer one shared fixture over a copy-pasted helper so a stale
   probe is one red edit, not N quiet skips.

## A Confirmation Is Only As Good As The Artifact It Ran Against

A confirmation is only as good as the artifact it was run against, and nothing in a *passing* check
tells you whether the artifact was the right one. This is a different failure from § Premises Are
Hypothesis above: there, the artifact is stale prose describing a system. Here, every step is sound
— the file is real, the read is correct, the reasoning holds — and the conclusion is still false,
because the check never touched the thing the claim was about. **Before reporting a check as
verified, name what the check would have to touch to be able to fail. If it never touched that, the
pass is not evidence.**

Sharpest instance: an engineer read cockpit's `intelligenceSignalSchema` and found it ended
`.strict()`, concluded an undeclared key would quarantine the row, and reported "verified rather
than assumed." The schema was real and `.strict()` genuinely means what they thought — but it is
not the last thing that touches the row. `parseLenient` catches the strict failure downstream,
strips the unrecognized key's value, and keeps the row. The question was "what does the reader do";
the artifact read was the thing the reader is built on, not the reader itself. A check against the
wrong artifact is worse than not checking: not checking leaves a caution; a clean pass upgrades the
caution to a fact, and the output carries nothing that distinguishes it from a check that means
something.

**Sub-clauses:**

1. **A schema is a claim about a reader; only the reader is the reader.** A declaration, a
   contract, a `.strict()`, a manifest, a type — none of them is the thing that runs. Read them to
   form the hypothesis, then run the path.
2. **A grep hit is a sighting, not an existence proof.** A stale comment describing a deleted
   mechanism is textually indistinguishable from a live reference to a present one. Confirm
   existence with a presence test against the tree (one `ls`/`stat`), not a mention.
3. **When a real input fails a check it demonstrably passes in production, suspect the instrument
   first.** The engineer above only surfaced the rescue layer because a peer ran a real wire row
   against the raw schema, watched it fail on a field the producer strips before publishing, and
   treated that as evidence the *instrument* was wrong rather than the data — a real row failing a
   check that demonstrably ingests hundreds of rows a day is the tell. The peer then replayed real
   snapshots twice into fresh stores, control vs. an injected undeclared key, and got the same
   landed count both times: an independent-oracle run, not another read of the same schema.

**A contradiction between your instrument and a working system is evidence about the instrument
first.** The same engineer held both facts — a field is stripped before publishing, and rows land
anyway — without connecting them, because the schema read was already accepted as fact rather than
carried as hypothesis.

**The clause bites on evidence-category language, specifically.** "Verified", "confirmed", "checked
in source" are load-bearing words between sessions — a peer receiving them reasonably stops
looking. "Reasoned to" and "verified" are different claims; only one of them names an observation.
The failure above did not happen at the schema read — it happened when a second peer relayed that
read as "verified rather than assumed," upgrading *reasoned* to *verified* in the retelling.
Relaying a peer's confirmation makes their artifact choice yours: when you hand a claim forward,
either it is your own independent oracle or it is still "reasoned," never re-labeled "verified" in
transit. The discriminator: does the evidence show the system doing the thing, or a component that
merely participates in the thing? Source-reading is the second; only the second was ever available
in the case above, and it was called the first.

*Sources: `2026-09-05-example-market-data-repo-em-a-confirmation-against-the-wrong-artifact.md`,
`2026-09-05-example-market-data-repo-em-co-sign-confirmation-against-the-wrong-artifact.md`,
`2026-09-05-example-store-repo-em-evidence-that-points-your-way-survives-review.md` (`state/cross-repo/archive/`).*

## Verification Must Not Reuse the Fix's Own Assumption — Use an Independent Oracle

A `sed` substitution that silently missed the backtick-wrapped form, and a follow-up `grep` that used the **same backtick-omitting pattern**, falsely confirmed "none remain" — the stale refs shipped and were caught only by a downstream reviewer. When a verification check shares the substitution/assumption of the thing it verifies, a true-negative is indistinguishable from success.

**Rule.** Verify with an independent oracle: anchor existence, a differently-shaped grep, or a count — never the fix's own pattern. The oracle's query must be structurally independent from the transformation it verifies. (Source: ~/.claude.)

### An end-to-end probe is only end-to-end downstream of where its fixture is built

When the defect is in how an input is **parsed, resolved, or normalized**, any harness that pre-normalizes the fixture is blind to it by construction — the probe exercises zero new code path while reading as the strongest possible evidence.

The 2026-07-31 destructive-`rm` repo-root fix was reported to the engine repo as "verified end to end through the real hook, not only the unit function." It was not. At that guard version `rm -rf ~/.claude` and `rm -rf $HOME/.claude` were both **ALLOWED**; only an absolute path denied. The guard's token loop dropped a raw `~/…` at `if not tgt or not os.path.exists(tgt): continue` (the token is never tilde-expanded) and dropped every `$HOME/…` at the glob/variable filter — so a `deny` was only reachable with an already-absolute target. The probe payload had therefore been expanded before the hook saw it: constructing it in a shell double-quoted string, or via `os.path.expanduser` / `Path.home()` / an f-string, performs exactly the expansion whose absence *was the bug*. The claim was true of the command as intended and false of the bytes on the wire, and it re-ran the leg the unit tests already covered while wearing an end-to-end costume.

**Rule.** Assert on the payload **bytes** before sending — print the JSON and confirm the `~` or `$HOME` literal survived — never on the command you meant to type. Build probe payloads from single-quoted or `json.dumps`'d literals, never a double-quoted shell interpolation or an `expanduser` call. When a fix concerns how a target *spelling* is resolved, the probe corpus must carry every spelling as-typed; a corpus of one absolute path cannot observe a resolution bug. (Caught by claude-klabauter-em; see `docs/wiki/coordinator-tripwires.md § PROBE-PAYLOAD-PRE-NORMALIZED`.)

### Mirroring an idiom copies its latent bugs — audit the source, don't trust mirror-fidelity

A plan instruction to "mirror the existing idiom" is not a correctness guarantee. The reaper's P4 SHA-selection was written by faithfully mirroring `promote-shipped-in-flight-stubs.py`'s `best_ct=-1` / `git show ... || echo 0` idiom — and thereby inherited its fail-OPEN bug (a non-empty all-unresolvable `commits[]` array selects a garbage SHA instead of failing closed). Audit the source idiom for defects *before* copying it, and when a review surfaces a copied bug, queue the source's identical instance too (done: bug-backlog for the promoter).

## Enforcement mechanisms — verify a guard/flag FIRES, not that it superficially exists

A guard, sentinel, gate, or CLI option is only a safety backstop if it actually runs on the actual input. "The mechanism is present" and "the mechanism does its job" are distinct claims — the gap between them ships mislabeled contracts and dead flags, and is caught downstream (by a reviewer) rather than at plan time. Before a plan leans on any enforcement mechanism as a forcing-function, verify it end-to-end against the substrate.

- **Verify a guard/sentinel against the directory the guard actually scans.** A reader-first sentinel (or any guard-file) must be dropped in the exact dir the guard globs — for cockpit emit that is `coordinator-state-root.py --central` (engine-repo state), NOT repo-local `state/`. A misplaced sentinel is a *delayed fuse*: masked while a prior sentinel coexists, it fires the moment the prior one is removed (a Gate-A clearing). The AC must be **"the guard actually fires on my file"**, not "a file exists somewhere." (Caught live by the Director of Engineering review on the v2.6.0 cockpit bump.)
- **Wiki-claimed enforcement guards can be phantoms — grep the code before a plan trusts one as a forcing-function.** A plan (and its prior-art check) asserted "`pnpm run emit` mechanically aborts without a `CONTRACT_VERSION` bump" — a hard forcing-function. Verified against `emit-schema.ts`: no such guard existed; the emitter stamps the bundle version *from* the source constant, so they can never disagree, and the wiki described a version-desync guard that was never implemented (doctrine-vs-code drift). A forgotten bump would have silently shipped a mislabeled contract — the exact opposite of the plan's confidence. Rule: when a plan relies on a described guard/gate as its safety backstop, grep the code to confirm the guard exists before trusting it; a wiki description is a claim, not an enforcement. (The guard is now implemented.) The same trap applies to any document whose value IS its accuracy about enforcement, not just wikis backing plans: a staleness registry declared three mechanisms "ci-asserted" in a repo with no `.github/` and no CI runner at all — self-consistent prose, entirely false. When a document's value is its accuracy about enforcement, grep for the enforcing thing (the workflow file, the hook, the gate) before trusting any tier it assigns itself.
- **Verify a flag/option is HONORED, not merely PARSED.** When a plan's premise rests on an existing CLI/config option, confirming the flag appears in the arg parser is NOT confirming it does anything. `refresh-queries.js` parsed `--files` into `opts.files` but `main()` called `walkMd(root)` unconditionally and never read it — a dead flag with zero working callers. Both pre-flight sidecars (prior-art + coverage) AND the EM confirmed "parsed" and missed "not honored"; only an Opus reviewer reading `main()` caught it. Substrate check for an option must **trace it to the code path that consumes it** (grep the option name in the executor/`main`, not just the parser), or run it and observe the scoped effect. A `try`/`except ImportError` soft-import falling back to an empty result is the same trap in a different shape: one chunk's producer soft-imported a sibling chunk's not-yet-landed function and degraded to `[]` on failure, but the sibling had shipped under a different function name — so the `ImportError` fired and silently swallowed a real wiring gap (zero output produced) while every unit test passed, because each chunk was mocked in isolation. At merge, reconcile each pinned cross-chunk import against the sibling's actual on-disk API — a soft-import that cannot distinguish "not landed yet" from "landed under a different name" hides the seam; grep the pinned name against the sibling module before trusting an empty result.
- **A guard denial usually names its own sanctioned alternative — read it before reporting blocked.** An acceptance criterion was reported unmeetable when a broad test-run command was refused for lacking a grant. The denial text itself prescribed the scoped alternative, and running the equivalent path-scoped invocations produced the same coverage with no grant written. Read the denial for its named remedy before escalating "blocked."

## A Supersession Needs The Superseded Suite In Review Scope

A change that overturns a ratified rule must run the suite encoding that rule, in review scope — a skipped stale-red test causes the next agent to revert the newer ruling right back to the old one. Pair every supersession with a run of the superseded suite, plus the ruling's provenance recorded in the docstring, so the reversal risk is closed at review time rather than left for a future agent to rediscover.

## Dogfooding A Ceremony Under Active Rebuild

Dogfood a ceremony while improving it — run it live to feed ground-truth friction into its own rebuild baton, rather than rebuilding it from a distance. Capture what the live run surfaces under a stable heading ("Dogfooding observations (captured live)") so friction lands in the rebuild baton as it happens, not reconstructed from memory afterward.

## A Rewrite Is Verified By Diffing It Against What It Replaces, Not By Running It

Running a rewritten payload and seeing output is not verification when the rewrite's job is to preserve semantics — it only confirms the rewrite produces *some* output. A `PreToolUse` command-rewrite seam shipped five defects, each "verified" only by running the rewritten payload and observing output; none were found by diffing the rewrite against the original command's semantics.

**Rule.** Verify a command-rewrite (or any semantics-preserving transform) by diffing it against the command it replaces — enumerate what the original did clause-by-clause and confirm the rewrite preserves each, rather than trusting that non-error output means equivalence.

## Strategic-direction claims verify against the ratifying DR, not a code comment

When a finding hinges on a strategic-direction claim ("X was tried and abandoned", "we rejected approach Y"), verify against the governing decision record / roadmap before letting it steer a recommendation — a code comment about a revert describes a *tactic*, not a *direction*. A scout (and the EM's first draft) read a shim-hooks-revert code comment as a permanent rejection of engine-repo Python-hook integration; the PM flagged it. Ground truth was the opposite: the ratified architecture (superseding the earlier record) is Python-resident `coordinator_core` + thin bash veneer, and the revert was a transport-tactic change *within* that direction. The DR is the primary source for direction; a revert comment is not.

## Doc-silence is not falsification — and first-hand testimony outranks a doc search

Doc-silence and behavioural absence are different claims. A scout reporting "not documented" has established only that vendor docs are silent, not that the described behaviour is false — and an over-correction that retracts a true, previously-observed constraint because no document backs it is worse than the error it fixes: it launders real first-hand knowledge out of the record while looking like diligence. Apply: when a scout returns "not in the docs," report it as doc-silence, and ask whether anyone observed the behaviour directly — log first-hand testimony with explicit provenance ("first-hand observation, not reproduced from documentation") rather than discarding it or laundering it into a doc citation.

## A per-line classification pass cannot see its own ceiling

A line-by-line KEEP/CUT pass structurally cannot find redundancy that only exists across sections — evaluated one line at a time, nearly every line defends itself locally: it is true, it reads well, it is not wrong. Two independent line-by-line triage passes over the same document, the second explicitly briefed to attack the first, converged on the same low ceiling; a structural pass ("if this vanished, what concretely breaks?") and an audience pass ("who actually pays for this, and does it reach a reader who acts on it?") over the identical corpus each found far more. An adversarial re-check of a per-line pass is not a substitute for a structural or audience lens — it inherits the frame it was told to attack, so redundancy that only exists across sections stays **invisible to that frame by construction**. When a stated number gets rejected, suspect the instrument — which lens produced it — before defending the measurement.

## "Unreachable" and "unset" are the same observable, different failures — including in your own shell

A resolver that cannot be *invoked* and a resolver that ran and found nothing both report as empty to a caller that treats a non-zero exit as "not found" — every downstream consumer then falls through to its own last-resort rung and bakes whatever that rung names into a durable artifact, and a guard whose absence is indistinguishable from its success enforces nothing while looking healthy.

The same trap recurs in ad-hoc shell commands: `grep <needle> <path> || echo "no references"` prints "no references" when grep *fails* (missing file, a bad glob, a moved cwd) exactly as loudly as when it searches successfully and finds nothing — `set -o pipefail` does not help, the exit code is genuinely non-zero either way. Never let `||` be the evidence for absence, especially before an irreversible act justified by "nothing references it." Check the target exists first, or use a reader that prints a distinct success-path confirmation only after it actually opened something. When writing a resolver, make "could not run" a distinct error from "not found"; when auditing a generator, the question is not whether it invokes a resolver but whether its resolved target exists at generation time.

## Reading a file proves its contents, never its reachability

Distinguish "this text says so" from "this surface is live" before citing a file as the mechanism for a behaviour — the fact that decides it (registration, dispatch state, current location) always lives outside the bytes being read, so **a dead surface and a live one render identically** on the page. Read the file's own header first — a stale or superseded file frequently says so plainly, and gets skipped past on the way to the implementation detail anyway. Then prove reachability by the surface's own kind: a hook needs a grep of the hooks registry, a script needs a live caller, a queued artifact needs its dispatch state checked (not just its existence), a cited path needs a `stat`. Verification is a real payload through the live path, never a file read alone.

## A stated corpus count is usually a grep-hit count, not a row count

A number like "N rows across M files" quoted from a plan is almost never a count of real task-spine rows — a raw grep across a plan corpus also matches **coverage-check report sidecars that quote row content verbatim**, and the count may trace back to the plan's own prose asserting it, so a second document "agreeing" is not corroboration when the second document is the first. Before repeating a stated corpus count anywhere, especially into a cross-repo memo, re-derive it: count rows inside the real fenced task-spine block only, excluding coverage-check reports and prose mentions, and name the exclusions applied. When the re-derived number differs, say so rather than silently substituting it.

## Trusted-source doctrine still needs testing

<!-- spec-backlink: run 2026-08-06-14h38, nugget c8-083 -->
A claim's source being "trusted doctrine" is not evidence it is correct — a batch of false doctrine claims were each believed until someone actually tested them. Empirical validation beats a trusted-source label; the label describes provenance, not correctness. Apply: when a doctrine claim is about to gate a decision, prefer a cheap direct test over inheriting the claim on authority alone. (Source: `2026-07-27-adhoc-d1f514.md` under `archive/completed/2026-07/`.)

## A Safety Property Is Uniform Over An Interval, Not Over A Thing

A safety argument names the conditions that make an operation safe. The failure is stating them as
properties of a **thing** — this mirror, this path, this operation — when they are properties of a
**moment**: the thing right after some event, and only until the next one.

**Tell.** The argument contains no interval. It reads "X is safe because P(X)" and never says
*until when*. Second tell: someone proposes scoping the property by space — per-mirror, per-target,
per-path — and it does not help. Space-scoping that fails to bite is worth checking against a
temporal axis next, not proof the variance is temporal — the property can also be false outright,
or scoped along a third axis (actor/session identity) that isn't strictly time. <!-- Review:
coordinator:code-reviewer — space-scoping-fails does not license concluding "must be temporal";
narrowed from "is the signature of" to a prompt-to-check, and named the disjunction. -->
Same underlying failure — scoping by thing instead of by interval — also shows up as: prose that
points at a stored measurement instead of the method that produced it (below); a check for an event
that outlives the process (the cross-process-hole corollary, below); and running a check against a
peer's uncommitted tree instead of committed code (below). <!-- Review: coordinator:code-reviewer —
the section's four failure shapes didn't restate or extend the opening Tell; grep landing on one of
the other three wouldn't recognize it as this pattern. -->

**Correction.** Name the interval. Which event makes P start holding, which event ends it, and what
the state is in between. Then ask whether the code can observe which side of those events it is on
— usually it cannot, because the event belongs to a previous process.

Worked instances, all from one deliverable (percolate removal side):

| claim as stated | actually holds | what ends it |
|---|---|---|
| absent from disk ⇒ not live payload (the removal-sync's target file) | between rounds | a round that refuses after its sync |
| a successfully-swapped dest is complete | across ordinary rounds | process death inside the per-entry swap window |
| the sync is fully `reset --hard`-revertible | while dest carries only this round's bytes | the first stranded removal accumulating there |
| a read of the substrate is a fact | for one frame | any concurrent writer |

The fourth is the general case; the first three are instances of it. Each states a property of a
substrate something else is free to mutate.

**Another surface: prose that caches a measurement.** The rows above are properties the code
asserts. The same expiry hits an *instruction* to a future reader — "do not re-derive this, read it
off the artifact already on disk." That is true when written and false the moment the artifact's
producer is fixed, and nothing about it looks stale. This narrows § Premises Are Hypothesis's rule
(every status-describing artifact ages or fabricates) to the instruction case specifically: point
at the method, or name what would invalidate the stored result. <!-- Review: coordinator:code-reviewer
— cross-referenced § Premises Are Hypothesis instead of restating its argument unlinked. -->

**The corollary that costs the most: an in-process predicate cannot close a cross-process hole.**
When the event that ends the property belongs to a previous invocation, no function over *this*
invocation's locals can detect it — you need a durable witness written to the substrate before the
window opens, or a positive read of the substrate itself. Reaching for the in-process predicate is
the natural move and it is wrong whenever the ending event outlives the process.

**Run production against committed code, never a peer's working tree.** A constant read as `True`
in a sibling repo's dirty checkout is one frame of that session's editing, not a property of the
system — the same session may revert it a minute later, and then the shipped result was produced by
a mechanism that exists nowhere.

The cost is **provenance, not reversibility**. The output may be trivially undoable and still be
unexplainable: nobody can re-derive why it did what it did, or re-run it to check. Confirm the
mechanism is committed before running it for real; a peer saying they landed it is not the same as
`git log` saying so.

**Observations have the same shape.** A measurement that refutes a peer's blocker is itself a
point-in-time read, and it is worth more scrutiny than one that confirms. Timestamp the observation
against the act it claims to refute — numbers that reconcile too neatly are a shared frame, not
independent confirmation.

## Attribution — A Subagent Cannot Distinguish Broken-Before-Me From Broken-By-Me

A subagent sees a snapshot, never a timeline. It can read the diff, read the failing test, and
still not know whether the failure predates its own change — that determination needs the
baseline, and producing the baseline is an act the subagent is not positioned to trust itself on.
**Attribution of a failing test is the EM's non-delegable job.** Verify a subagent's "pre-existing
failure" claim by executing the baseline (`git stash` / checkout the pre-change commit and re-run),
never by reading the diff and reasoning about which lines could plausibly matter. The same gap
recurred ten days later in a different session: a probe called a test failure "pre-existing"
because the failing file matched HEAD — but HEAD was already the change under test. Checked
against the pre-cut blob, the cut had silently converted indented code blocks into fenced ` ```bash `
blocks, invisible to ShellCheck, the test registry, and coverage-of-coverage gates alike.
**"Pre-existing" is a claim about the baseline, not about HEAD, and HEAD may already be your
change** — the diff not naming a file is not evidence the file was untouched by the change's
effects.

**Cross-repo detectors invert the usual intuition — the repo where a test fails is where the RULE
lives, not necessarily where the VIOLATION was introduced.** "My diff didn't touch that file" is
correct in a single-repo codebase and silently wrong here: a sweep commit made earlier in the
same session reads as somebody else's work to a subagent dispatched later with a narrow scope, and
several detectors in this fleet scan the resolved sibling-repo root while living in, and failing
in, the contract repo. Before accepting an "unrelated pre-existing failure" claim, run the detector
directly against the named file, read which repo the offending path is actually in, and check this
session's own commit list for that path — only then is "not ours" a finding rather than an
assumption.

## A Delivery Gate Discharges Arrival, Never Compliance

A delivery gate that confirms injected contract text reached a child process has proven the text
**arrived**, not that the child treats it as authoritative. Arrival is not obedience. A gate
built to certify "the contract text was delivered" answers a narrower question than the one a plan
usually needs answered — whether the receiving agent is bound by it — and the two get silently
conflated. Concrete positive case worth preserving: a smoke test worked when the child
self-reported that the injected block read like test content rather than a binding instruction,
which is itself evidence the gate was measuring arrival and nothing else. Before treating a
delivery gate as proof of compliance, dogfood the injected contract against a live child and check
whether its *behavior* changed, not just whether the bytes showed up in its context.

## Related

- CLAUDE.md § Verification Before Done — boot-context rules (shipped-on-main, concurrent-sweep verify, smoke-test dispatch).
## test baseline run-window overlapping in-flight commit produces transient ImportErrors

A test baseline whose run-window overlaps your own in-flight commit reports transient `ImportError`s, not real failures. The in-progress commit may leave the module in a partially-written state during the baseline run. Sequence the baseline run before your commit series starts, or after it completes cleanly. Apply: if a baseline shows unexpected `ImportError`s, check whether a concurrent commit was in flight during the baseline run before treating the errors as real.

## green local fast-tier is not green on the other OSes; rename sweeps must include CI-shaped config

The fleet runs no CI; the merge gate is the local fast tier plus the PM's own Windows/Mac/Linux boxes. A green fast tier on one box is NOT green on the others. Rename and path-change sweeps MUST include any tracked CI-shaped config (`.github/`, `.gitlab-ci.yml`) that names the old path — such files stay in repos this fleet does not own. Apply: any `git mv`, module rename, or path-change plan must include a `grep -r <old-name> .github/` step in done-criteria.

## Count-stable ≠ regression-free when editing a file that already has failing tests

A removal or edit to a file that already has pre-existing red can silently drop live code whose breakage is masked by the existing failure — e.g. deleting a helper still referenced by an already-failing test, leaving a latent `ReferenceError` hidden behind the primary assertion. Verifying "pass/fail counts unchanged" is NOT sufficient there: read what the removed symbols were actually referenced by, or run the file to green first. Caught when a codex-removal deleted `sandboxedHomeEnv`/`detectPython` that a failing suite still used.

## A-vs-B diff requires same-conditions control — never a pre-existing artifact

To attribute an A-vs-B diff to ONE variable, hold every other variable constant — diff against a same-conditions control, never a pre-existing artifact built under different conditions. Cross-condition artifact diffs produce phantom deltas. A clean go/no-go null result (no diff under same conditions) is a success confirming the diff IS the variable. Apply: whenever testing "did X change the output," produce a fresh control run under the same conditions and diff against that.

## CI precedent borrowing requires asymmetry-load-bearing audit

Before invoking a CI precedent from another workflow step, audit whether the precedent is symmetric in failure-mode load-bearing. A silent-pass on an optional dependency does not equal a silent-pass on a substrate the contract pins to. Apply: when copy-pasting a CI pattern, explicitly verify that the failure mode of the borrowed pattern matches the failure mode you need to handle.

## `.venv/site-packages` grep matches ≠ "the host imports this dep"

**A grep hit inside `.venv/Lib/site-packages/` proves the package is installed; it does NOT prove production code reaches it. Before claiming a transitive third-party dependency fires in production, grep the *importing tree* (production `.py` files in `core/`, `src/`, the package's runtime modules), not the venv.** A cross-repo memo claimed a `powershell.exe` popup came from a transitive `joblib/loky` spawn, citing matches in `../<host>/.venv/Lib/site-packages/joblib/...`; the host scout's `grep -rn "joblib\|loky"` in actual production source returned zero hits. The package was on the venv path but never imported. The hypothesis was a transitive-import fiction, and a correction memo had to chase it within the same session. Discipline: production grep proves *reached*; venv grep only proves *installed*. The verify-before-send step had been scoped to the wrong substrate. (case: project-rag-ue-addon)

- coordinator/docs/wiki/verification-discipline.md § Premises Are Hypothesis — Verify Against Disk, Not Prose, § Verifying Executor Output After a Crash or Timeout — boot-context tripwires this section expands.
- `verification-before-completion.md` § Runtime Readiness vs. Green Tests — the daemon/editable-install/e2e-symptom half of this bucket.
- `cleanup-sweep-hazards.md` — sweep operations, auto-discovery globs, scaffolding-deletion checks.
- `test-design-discipline.md` — AC table predicates, regression nets, contract-change grep, vacuous-pass risks.
- `round-trip-contract-tests.md` — producer/consumer schema verification.
