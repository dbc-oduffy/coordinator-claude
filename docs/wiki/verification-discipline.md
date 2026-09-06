# Verification Discipline

Doctrine extending CLAUDE.md § Verification Before Done. Empirical audit beats confident hypothesis, observed-outcome beats inferred-mechanism, and acceptance evidence is satisfied by real artifacts — not prose claims. These rules sit one layer below the boot-context CLAUDE.md tripwires; they apply during diagnosis, fix-validation, and AC-table authoring.

## When this applies

Any workstream that diagnoses a failure, validates a fix, writes an acceptance-criteria table, or produces "evidence" prose for review. Also config-layer authoring where auto-discovery globs decide what gets loaded.

## Rules

### Diagnostic-first

- **Build a cheap N-way diagnostic before fixing any single suspect when ≥2 tools could explain a failure.** Fixing the wrong one wastes more cycles than the diagnostic costs. If subsystem A, B, or C could have produced the symptom, a 10-minute probe that distinguishes them is cheaper than a 2-hour fix to the wrong one.

- **Confident hypothesis is not empirical audit.** When you "know" the bug, run the audit anyway — confident hypotheses are wrong often enough that the audit cost is amortized across the ones it catches. The pattern fails closed: audit cheap → run it; audit expensive → still run it, because the alternative is a confident wrong fix that gets caught two sessions later.

### Evidence quality

- **Distinguish observed-outcome from inferred-mechanism in evidence prose.** Evidence MUST separate `"tests passed"` (observed) from `"because the fix removed the race"` (inferred). Confident inferred-mechanism prose without observed-outcome backing is a wishful-thinking trap — the reader can't tell whether you ran the test or argued the test would pass. Frame as: *observed: X. inferred: Y because Z.*

- **A CI matrix-run artifact satisfies `evidence-committed` acceptance criteria.** Don't require copy-pasted test output in commit messages when CI already preserves the run — linked from PR description or repo CI page is sufficient. Copy-pasted output drifts; the run artifact doesn't.

### Acceptance-criteria authoring

- **`LIKE` / fuzzy-match operators in AC tables mask separator and normalization bugs.** Path-separator drift, NFC vs NFD, trailing whitespace all sneak through. Use exact-string ACs and quote the expected value with explicit delimiters. LIKE is fine as one predicate among several; never as the only predicate. (See also: `test-design-discipline.md` §3.)

### Defensive-hardening calibration

- **Defensive hardening past the primitive means the primitive is at the wrong layer.** When you find yourself wrapping the same call in try/except at three layers, stop adding wrappers — refactor to push the boundary to where the failure is *meaningful*. Three layers of defensive hardening signal a design problem, not a robustness problem.

### Config / auto-discovery

- **Auto-discovery globs MUST exclude backup-file patterns.** `*backup*`, `*.bak*`, `*.orig`, `*.old`, `~` suffixes — stale backups masquerade as live config and silently override the intended set. Either pin explicit paths or extend the exclusion list. (See also: `cleanup-sweep-hazards.md` §4.)

### Sentinel-marker parity tests for enumerated diagnostic surfaces

- **Probe-without-surface = invisible probe.** When a diagnostic command (slash command, agent prompt, human-readable script) enumerates a fixed set of probe phases that map to a code-level array or registry, the enumeration is a **load-bearing surface — not documentation**. The two artifacts drift silently within ~30 minutes of any unsynchronized edit.
- **Wrap the enumeration in sentinel markers** (HTML comments, code-block delimiters, named ranges) and add a CI parity test that asserts set-equality between the enumeration and its sibling source-of-truth registry. The drift costs ~30 minutes of diagnosis when it happens; the parity test costs minutes to author.
- **Same shape applies to sibling-surface capability divergence.** Where two commands/skills expose enumerations that *should* match (probe lists across `doctor` and `setup`, capability tables across orchestrators), the parity test runs across both — divergence is a predictable bug class, not a one-off.

### Git verification

- **When `git commit` reports "no changes added," check `git reflog` before re-staging.** The staged set was empty — but the reason may be that a peer session already committed the work. Re-staging without checking creates duplicate commits or, worse, resurrects content the peer session intentionally dropped.

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

> **Provenance:** consolidated 2026-05-27 from learn-lessons Bucket B (verify-against-disk / claims-are-hypothesis / crash-recovery), the largest recurring bucket (~92 queue + delta items). The single dominant pattern: an artifact that *describes* state (handoff, audit, executor report, reviewed plan, scout brief, `consumed_by`/`claimed_by` claim — DR-084 renamed the field; the on-disk corpus is mixed, check both) is treated as ground truth when it is hypothesis. Primary sources are disk and git; everything else is a claim to be checked.

The unifying rule for this entire section: **every status-describing artifact ages or fabricates — the primary source is code on disk, `git show`, the live interface, not the description.** What follows is the per-shape application.

### Executor and agent reports fabricate — diff is ground truth

Executor reports routinely assert state that the diff contradicts: "already done as an uncommitted edit," "finding implemented" (with a comment claiming so but no code), "file already correct," a re-score from a flag that doesn't exist. Agents hallucinate prior state and downstream success, *especially* when a fix "feels" present.

- **Executor reports are unverified until the claimed paths are diffed against disk.** The diff is ground truth; chat is hypothesis. (Extends CLAUDE.md § Verifying Executor Output.)
- **Verify each load-bearing reviewer-finding by reading the code that claims to satisfy it** — an executor comment "per-sample cc synthesized below" / "finding addressed" is narrative, not implementation. Full review chains do not catch an executor that *says* done and isn't.
- **A reviewed plan can cite a non-existent CLI flag or tool interface.** At execution, grep the literal tool interface (the script's `argparse`, the real command name) — reviewed ≠ substrate-verified. `synthesize_engine_compile_commands.py --project-root` did not exist; the real tool was `synthesize_project_compile_commands.py`.
- **Executor file-size / commit-structure claims need `git show --stat <sha>` (and `git show <sha>:<path>`) verification** — false-narrative commits encode fictional premises; a terminal commit proves a *file was written*, not that ACs were met or review ran.
- **Parallel-executor "green" reports require EM verification before trust (~36% real-pass rate observed).** Do not chain-advance on a self-reported green.
- **Executor "next-failure / pre-existing / unrelated" attribution is hypothesis.** Verify with `git log -G<symbol>` + `git stash` before inheriting the attribution. Touches-X ≠ caused-by-session; `--author` does not isolate work on a shared branch — triage attribution needs git verification, not area-matching.
- **Executor-caught latent spec bugs: adopt in-flight, update the plan body, don't re-spec.** "BLOCKED" can be a misdiagnosis — verify substrate before believing it.

Small, well-diagnosed fixes are often faster to apply EM-direct than to re-dispatch over a confused executor.

### Handoff / audit / roadmap / scout premises are hypothesis

A handoff's diagnosis, an audit's locus, a roadmap stub's AC, a scout's finding, a `consumed_by`/`claimed_by` claim (formerly `consumed_by` only; DR-084) — all describe a state that may have drifted, been mis-attributed, or never been verified.

- **"Broken today" and concrete numeric claims age out within hours.** Before building a fix on a cited failure: `git log --oneline -- <cited-paths>` since the report's date, then re-run on HEAD. Specific numeric claims (latency, scores, counts) re-confirm against HEAD — they are the fastest-decaying.
- **Scout-relayed and mid-chain subagent findings describe run-time state, not chain-terminus state.** Re-verify against HEAD before acting on a flagged-fix sub-report inside a ceremony chain. The audit *symptom* is usually correct; the proposed *locus* is not — read the producer code before accepting it.
- **A pickup-time 30-min spike on the handoff's central artifact can collapse a binary architectural choice to a 30-line patch.** Handoff AC-line citations are hypothesis, not contract — read substrate before drafting. Roadmap-altitude framings are hypothesis; substrate-verify at plan-draft time.
- **Reconcile a handoff slate by deliverable-on-disk, not `consumed_by`/`claimed_by` claim-state (formerly `consumed_by` only; DR-084 — the corpus is mixed, check both fields).** A populated `consumed_by` or `claimed_by` with a uniform `00:00:00Z` timestamp and frontmatter-only commits is the signature of a batch triage sweep, not a live executor — every deliverable can be unstarted. Check whether *deliverable* commits exist past the pickup-mutation commit; treat `consumed_by`/`claimed_by` as "claimed, verify liveness."
- **Roadmap-spinoff ACs authored days earlier can specify already-shipped work, mis-attributed to the wrong layer.** Grep each AC's capability before building. A cohort stub whose siblings "inherit decisions from the anchor" goes stale when the anchor ships via a different plan — correct the sibling inheritance pointers at pickup, don't just close the anchor.
- **Re-baseline a paired A/B measurement when substrate drifted under a stale handoff.** "Resume from the on-disk baseline, no re-run needed" is a same-day assumption that decays the moment any commit touches the corpus/index — a 6-day-old anchor drifted 0.024, which would have injected straight into the lever deltas. Re-run the anchor leg fresh when the handoff is >1 day old or any substrate-touching commit landed.
- **A perf diagnosis taken while zombie processes / subprocess-spawned daemons are contending is contaminated.** `ps` / process-list + a clean re-run BEFORE trusting any "X is slow/broken" number — a reported 1230s collection was actually ~4s under contention from 5 abandoned pytest processes + a daemon commit-leak. A newly-runnable test tier also surfaces pre-existing failures the prior avoidance hid — expect and triage them, don't assume they're your regression.
- **A transient infra state is not a missing capability.** A handoff gate naming an external MCP tool as "blocked" needs connection-confirmation + source-repo check first: "server not connected" ≠ "capability not shipped."
- **A handoff's diagnostic prescriptions decay — verify the named symptom rather than trusting the prescribed fix.** Handoff diagnostics are hypothesis, not procedure. Case: a from-source-rebuild handoff prescribed "If STALL fires it's almost certainly the structural-index-merge lock-wait — check tasks/_locks/ for a stale lock whose pid is dead, clear it." When STALL fired, the lock holder was ALIVE — the actual bug was a parent/child self-deadlock the handoff author had mis-diagnosed. Following the prescription verbatim would have wasted time finding nothing. Rule: re-classify the named symptom against current evidence (e.g. `psutil.pid_exists` on the lock holder) before applying the prescribed fix. Source: project-rag-ue-addon.

### Reconstruction after a crash: work hides in untracked files

A crash boundary is *exactly* where work exists on disk but not in the git index. Reconstruction accounts for **where work landed**, not whether process gates closed.

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

The last is the most dangerous, because a reader who checks is told the answer is yes. An
unasserted invariant is a gap; an asserted-and-false one is a trap.

**Rules.**

1. Before trusting a new gate, plant a defect it must catch and see it go red. Record that you
   did — "shown failing on a planted bad target before I accepted it" is the sentence.
2. A check that passes on a machine where its subject cannot exist must skip with a stated reason,
   never pass. A skip is honest; a green is a lie.
3. A property stated in prose is documentation, not verification. If it must hold, something has
   to execute it — and the artifact that executes it is the discharge, per this repo's own
   discharge test.
4. Reproducing a failing check's own setup confirms its premise; it does not check it. When a
   check fails, ask what its setup fails to establish before concluding the subject is broken.

## Verification Must Not Reuse the Fix's Own Assumption — Use an Independent Oracle

A `sed` substitution that silently missed the backtick-wrapped form, and a follow-up `grep` that used the **same backtick-omitting pattern**, falsely confirmed "none remain" — the stale refs shipped and were caught only by a downstream reviewer. When a verification check shares the substitution/assumption of the thing it verifies, a true-negative is indistinguishable from success.

**Rule.** Verify with an independent oracle: anchor existence, a differently-shaped grep, or a count — never the fix's own pattern. The oracle's query must be structurally independent from the transformation it verifies. (Source: ~/.claude.)

### An end-to-end probe is only end-to-end downstream of where its fixture is built

When the defect is in how an input is **parsed, resolved, or normalized**, any harness that pre-normalizes the fixture is blind to it by construction — the probe exercises zero new code path while reading as the strongest possible evidence.

The 2026-07-31 destructive-`rm` repo-root fix was reported to claude-klabauter as "verified end to end through the real hook, not only the unit function." It was not. At that guard version `rm -rf ~/.Claude` and `rm -rf $HOME/.claude` were both **ALLOWED**; only an absolute path denied. The guard's token loop dropped a raw `~/…` at `if not tgt or not os.path.exists(tgt): continue` (the token is never tilde-expanded) and dropped every `$HOME/…` at the glob/variable filter — so a `deny` was only reachable with an already-absolute target. The probe payload had therefore been expanded before the hook saw it: constructing it in a shell double-quoted string, or via `os.path.expanduser` / `Path.home()` / an f-string, performs exactly the expansion whose absence *was the bug*. The claim was true of the command as intended and false of the bytes on the wire, and it re-ran the leg the unit tests already covered while wearing an end-to-end costume.

**Rule.** Assert on the payload **bytes** before sending — print the JSON and confirm the `~` or `$HOME` literal survived — never on the command you meant to type. Build probe payloads from single-quoted or `json.dumps`'d literals, never a double-quoted shell interpolation or an `expanduser` call. When a fix concerns how a target *spelling* is resolved, the probe corpus must carry every spelling as-typed; a corpus of one absolute path cannot observe a resolution bug. (Caught by claude-klabauter-em; see `docs/wiki/coordinator-tripwires.md § PROBE-PAYLOAD-PRE-NORMALIZED`.)

### Mirroring an idiom copies its latent bugs — audit the source, don't trust mirror-fidelity

A plan instruction to "mirror the existing idiom" is not a correctness guarantee. The reaper's P4 SHA-selection was written by faithfully mirroring `promote-shipped-in-flight-stubs.py`'s `best_ct=-1` / `git show ... || echo 0` idiom — and thereby inherited its fail-OPEN bug (a non-empty all-unresolvable `commits[]` array selects a garbage SHA instead of failing closed). Audit the source idiom for defects *before* copying it, and when a review surfaces a copied bug, queue the source's identical instance too (done: bug-backlog for the promoter).

## Enforcement mechanisms — verify a guard/flag FIRES, not that it superficially exists

A guard, sentinel, gate, or CLI option is only a safety backstop if it actually runs on the actual input. "The mechanism is present" and "the mechanism does its job" are distinct claims — the gap between them ships mislabeled contracts and dead flags, and is caught downstream (by a reviewer) rather than at plan time. Before a plan leans on any enforcement mechanism as a forcing-function, verify it end-to-end against the substrate.

- **Verify a guard/sentinel against the directory the guard actually scans.** A reader-first sentinel (or any guard-file) must be dropped in the exact dir the guard globs — for cockpit emit that is `coordinator-state-root.py --central` (claude-klabauter state), NOT repo-local `state/`. A misplaced sentinel is a *delayed fuse*: masked while a prior sentinel coexists, it fires the moment the prior one is removed (a Gate-A clearing). The AC must be **"the guard actually fires on my file"**, not "a file exists somewhere." (Caught live by the Director of Engineering review on the v2.6.0 cockpit bump.)
- **Wiki-claimed enforcement guards can be phantoms — grep the code before a plan trusts one as a forcing-function.** A plan (and its prior-art check) asserted "`pnpm run emit` mechanically aborts without a `CONTRACT_VERSION` bump" — a hard forcing-function. Verified against `emit-schema.ts`: no such guard existed; the emitter stamps the bundle version *from* the source constant, so they can never disagree, and the wiki described a version-desync guard that was never implemented (doctrine-vs-code drift). A forgotten bump would have silently shipped a mislabeled contract — the exact opposite of the plan's confidence. Rule: when a plan relies on a described guard/gate as its safety backstop, grep the code to confirm the guard exists before trusting it; a wiki description is a claim, not an enforcement. (The guard is now implemented.)
- **Verify a flag/option is HONORED, not merely PARSED.** When a plan's premise rests on an existing CLI/config option, confirming the flag appears in the arg parser is NOT confirming it does anything. `refresh-queries.js` parsed `--files` into `opts.files` but `main()` called `walkMd(root)` unconditionally and never read it — a dead flag with zero working callers. Both pre-flight sidecars (prior-art + coverage) AND the EM confirmed "parsed" and missed "not honored"; only an Opus reviewer reading `main()` caught it. Substrate check for an option must **trace it to the code path that consumes it** (grep the option name in the executor/`main`, not just the parser), or run it and observe the scoped effect.

## Strategic-direction claims verify against the ratifying DR, not a code comment

When a finding hinges on a strategic-direction claim ("X was tried and abandoned", "we rejected approach Y"), verify against the governing decision record / roadmap before letting it steer a recommendation — a code comment about a revert describes a *tactic*, not a *direction*. A scout (and the EM's first draft) read a shim-hooks-revert code comment as a permanent rejection of claude-klabauter Python-hook integration; the PM flagged it. Ground truth was the opposite: DR-042 (superseding DR-148) ratifies Python-resident `coordinator_core` + thin bash veneer, and the revert was a transport-tactic change *within* that direction. The DR is the primary source for direction; a revert comment is not.

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
A claim's source being "trusted doctrine" is not evidence it is correct — a batch of false doctrine claims were each believed until someone actually tested them. Empirical validation beats a trusted-source label; the label describes provenance, not correctness. Apply: when a doctrine claim is about to gate a decision, prefer a cheap direct test over inheriting the claim on authority alone. (Source: `archive/completed/2026-07/2026-07-27-adhoc-d1f514.md`.)

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

Worked instances, all from one deliverable (percolate removal side, 2026-08-26):

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

## Related

- CLAUDE.md § Verification Before Done — boot-context rules (shipped-on-main, concurrent-sweep verify, smoke-test dispatch).
## test baseline run-window overlapping in-flight commit produces transient ImportErrors

A test baseline whose run-window overlaps your own in-flight commit reports transient `ImportError`s, not real failures. The in-progress commit may leave the module in a partially-written state during the baseline run. Sequence the baseline run before your commit series starts, or after it completes cleanly. Apply: if a baseline shows unexpected `ImportError`s, check whether a concurrent commit was in flight during the baseline run before treating the errors as real.

## green local fast-tier is not green CI; rename sweeps must include .github/workflows/

A green local fast-tier is NOT a green CI — the merge gate only counts if it actually executes. Rename and path-change sweeps MUST include `.github/workflows/` YAML files; CI workflow files that reference the old path will fail silently on the next PR. Apply: any `git mv`, module rename, or path-change plan must include a `grep -r <old-name> .github/` step in done-criteria.

## red CI in seconds = billing/quota gate not code failure — triage by duration

A CI job that "fails" in seconds without ever starting is a billing/quota gate, not a test failure. Distinguish by run-duration and annotation: billing/quota failures typically show a flat-line graph with a quota or billing error annotation, not a test-runner traceback. Apply: before chasing a red CI job in code, check the job duration — sub-5-second failure is a quota signal, not a code signal.

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
