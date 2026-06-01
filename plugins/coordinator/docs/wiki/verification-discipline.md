# Verification Discipline

**Provenance:** consolidated 2026-05-14 from `tasks/queue-triage-2026-05-14/wave-manifest.md` Wave E2. Source entries: E55, E56, E61, E65, E85, E91, E92, E132.

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

*Source: holodeck `tasks/lessons.md` (holodeck-L149, central-promoted 2026-05-28).*

## Verifier Paraphrase Is Still Paraphrase — P0/P1 Gate Recurses Into Phase 2

*Source: project-rag tasks/lessons.md:102, 2026-05-29. [universal]*

A fix-executor that reads the source code directly can find that a verifier's "production risk" was phantom — the cited code was already fixed, or the risk was mis-stated in the verifier's summary. **Verifier paraphrase is still paraphrase.** The P0/P1 verification gate (CLAUDE.md § P0/P1 Verification Gate: read the cited code, confirm against current source) applies recursively: when a Phase 1 verifier returns a P0/P1 finding, the EM or a Phase 2 reader must still read the cited code line-by-line before dispatching a fix. A verifier that summarizes a finding in confident terms provides *another layer of paraphrase*, not primary source confirmation.

**Concrete failure shape:** Phase 1 verifier returns "CRITICAL — production risk at `foo.py:142`." Phase 2 fix-executor reads `foo.py:142` and finds the risk condition is absent or already guarded. The verifier's "production risk" was based on an outdated reading or a misread branch. High-confidence framing in a Phase 1 report inverts the hit rate — treat it as a pointer to read, not as a finding to act on.

## Crash recovery: artifact-survey-first across peer repos

- **Re-extraction as crash recovery is process theater when versioned artifacts already exist.** Before re-running an expensive producer (extractor, indexer, generator) on crash recovery, survey every peer repo in the cohort for already-shipped versioned artifacts. The three-repo split case: producer crashed mid-run, EM reflex was to re-run the extraction — but two sibling repos already carried fresh artifacts from the prior successful pass. Cost of survey is one `ls` per repo + a freshness grep; cost of unnecessary re-run is hours of producer time plus the chance of a worse output. Generalizes to any post-crash decision where "re-run the producer" is one option: artifact-survey-first across the full cohort, then decide.

## Premises Are Hypothesis — Verify Against Disk, Not Prose

> **Provenance:** consolidated 2026-05-27 from learn-lessons Bucket B (verify-against-disk / claims-are-hypothesis / crash-recovery), the largest recurring bucket (~92 queue + delta items). The single dominant pattern: an artifact that *describes* state (handoff, audit, executor report, reviewed plan, scout brief, `consumed_by` claim) is treated as ground truth when it is hypothesis. Primary sources are disk and git; everything else is a claim to be checked.

The unifying rule for this entire section: **every status-describing artifact ages or fabricates. Read the primary source — code on disk, `git show`, `git status -uall`, the live interface — before acting on the description.** What follows is the per-shape application.

### Executor and agent reports fabricate — diff is ground truth

Executor reports routinely assert state that the diff contradicts: "already done as an uncommitted edit," "finding implemented" (with a comment claiming so but no code), "file already correct," a re-score from a flag that doesn't exist. Agents hallucinate prior state and downstream success, *especially* when a fix "feels" present.

- **After any executor edit, `git diff` / `git status` the claimed paths and re-run the cited tests yourself before committing.** The diff is ground truth; chat is hypothesis. (Extends CLAUDE.md § Verifying Executor Output.)
- **Verify each load-bearing reviewer-finding by reading the code that claims to satisfy it** — an executor comment "per-sample cc synthesized below" / "finding addressed" is narrative, not implementation. Full review chains do not catch an executor that *says* done and isn't.
- **A reviewed plan can cite a non-existent CLI flag or tool interface.** At execution, grep the literal tool interface (the script's `argparse`, the real command name) — reviewed ≠ substrate-verified. `synthesize_engine_compile_commands.py --project-root` did not exist; the real tool was `synthesize_project_compile_commands.py`.
- **Executor file-size / commit-structure claims need `git show --stat <sha>` (and `git show <sha>:<path>`) verification** — false-narrative commits encode fictional premises; a terminal commit proves a *file was written*, not that ACs were met or review ran.
- **Parallel-executor "green" reports require EM verification before trust (~36% real-pass rate observed).** Do not chain-advance on a self-reported green.
- **Executor "next-failure / pre-existing / unrelated" attribution is hypothesis.** Verify with `git log -G<symbol>` + `git stash` before inheriting the attribution. Touches-X ≠ caused-by-session; `--author` does not isolate work on a shared branch — triage attribution needs git verification, not area-matching.
- **Executor-caught latent spec bugs: adopt in-flight, update the plan body, don't re-spec.** "BLOCKED" can be a misdiagnosis — verify substrate before believing it.

Small, well-diagnosed fixes are often faster to apply EM-direct than to re-dispatch over a confused executor.

### Handoff / audit / roadmap / scout premises are hypothesis

A handoff's diagnosis, an audit's locus, a roadmap stub's AC, a scout's finding, a `consumed_by` claim — all describe a state that may have drifted, been mis-attributed, or never been verified.

- **"Broken today" and concrete numeric claims age out within hours.** Before building a fix on a cited failure: `git log --oneline -- <cited-paths>` since the report's date, then re-run on HEAD. Specific numeric claims (latency, scores, counts) re-confirm against HEAD — they are the fastest-decaying.
- **Scout-relayed and mid-chain subagent findings describe run-time state, not chain-terminus state.** Re-verify against HEAD before acting on a flagged-fix sub-report inside a ceremony chain. The audit *symptom* is usually correct; the proposed *locus* is not — read the producer code before accepting it.
- **A pickup-time 30-min spike on the handoff's central artifact can collapse a binary architectural choice to a 30-line patch.** Handoff AC-line citations are hypothesis, not contract — read substrate before drafting. Roadmap-altitude framings are hypothesis; substrate-verify at plan-draft time.
- **Reconcile a handoff slate by deliverable-on-disk, not `consumed_by` claim-state.** A populated `consumed_by` with a uniform `00:00:00Z` timestamp and frontmatter-only commits is the signature of a batch triage sweep, not a live executor — every deliverable can be unstarted. Check whether *deliverable* commits exist past the pickup-mutation commit; treat `consumed_by` as "claimed, verify liveness."
- **Roadmap-spinoff ACs authored days earlier can specify already-shipped work, mis-attributed to the wrong layer.** Grep each AC's capability before building. A cohort stub whose siblings "inherit decisions from the anchor" goes stale when the anchor ships via a different plan — correct the sibling inheritance pointers at pickup, don't just close the anchor.
- **Re-baseline a paired A/B measurement when substrate drifted under a stale handoff.** "Resume from the on-disk baseline, no re-run needed" is a same-day assumption that decays the moment any commit touches the corpus/index — a 6-day-old anchor drifted 0.024, which would have injected straight into the lever deltas. Re-run the anchor leg fresh when the handoff is >1 day old or any substrate-touching commit landed.
- **A perf diagnosis taken while zombie processes / subprocess-spawned daemons are contending is contaminated.** `ps` / process-list + a clean re-run BEFORE trusting any "X is slow/broken" number — a reported 1230s collection was actually ~4s under contention from 5 abandoned pytest processes + a daemon commit-leak. A newly-runnable test tier also surfaces pre-existing failures the prior avoidance hid — expect and triage them, don't assume they're your regression.
- **A transient infra state is not a missing capability.** A handoff gate naming an external MCP tool as "blocked" needs connection-confirmation + source-repo check first: "server not connected" ≠ "capability not shipped."
- **A handoff's diagnostic prescriptions decay — verify the named symptom rather than trusting the prescribed fix.** Handoff diagnostics are hypothesis, not procedure. 2026-05-28 from-source-rebuild: the handoff prescribed "If STALL fires it's almost certainly the structural-index-merge lock-wait — check tasks/_locks/ for a stale lock whose pid is dead, clear it." When STALL fired, the lock holder was ALIVE — the actual bug was a parent/child self-deadlock the handoff author had mis-diagnosed. Following the prescription verbatim would have wasted time finding nothing. Rule: re-classify the named symptom against current evidence (e.g. `psutil.pid_exists` on the lock holder) before applying the prescribed fix. Source: 2026-05-28 project-rag-ue-addon.

### Reconstruction after a crash: work hides in untracked files

A crash boundary is *exactly* where work exists on disk but not in the git index. Reconstruction accounts for **where work landed**, not whether process gates closed.

- **A "zero implementation" forensic claim built on `git grep` / `git log` is tracked-only** — it cannot see a crashed session's uncommitted work. Run `git status -uall` + disk `ls` of the expected scope BEFORE accepting a "nothing was built" premise. Crashed sessions routinely leave substantial untracked implementation; dispatched executors then "find the files already present." A recovery handoff's "zero implementation" conclusion is tracked-only by construction — the recovery author used `git grep`, which is blind to everything the crashed session left unindexed. Source: 2026-05-27 project-rag-ue-addon (tc-12 pickup).
- **A dense burst of `workstream-complete quick-save` / `pickup` commits in minutes is a crash signature, not clean closure.** A terminal commit proves a file was written — not that ACs were met, code was reviewed, or `/workstream-complete` ran. After a crash, treat a single scout's reconstruction as HYPOTHESIS, then verify per-thread from primary sources (code on disk, `git show`, `tasks/review-trail/*.json`, completion records, handoff frontmatter), and **dispatch real code review at any "complete" thread whose review-trail record is absent** (2 of 7 "shipped-clean" threads had no review and no completion record in the observed case).
- **Run a second gate-keyed pass after any crash recovery** — the first pass establishes what landed; the second checks each thread's process gates (review-trail + completion-record presence) independently.
- **Predecessor-session background executors can finish mid-pickup** — emitting results inline and writing to disk *after* the picking-up EM has committed. At pickup, reconcile against late-arriving disk writes, not just the pre-pickup commit set. Pickup-reconcile catches pre-pickup commits, not during-investigation ones; peer EMs can close your workstream out from under you.
- **Review-trail coverage audits must glob `archive/review-trail/**`,** not just the live dir — `/workweek-complete` relocates records on weekly reset, so a live-dir-only audit under-reports coverage.

## Verification Must Not Reuse the Fix's Own Assumption — Use an Independent Oracle

A `sed` substitution that silently missed the backtick-wrapped form, and a follow-up `grep` that used the **same backtick-omitting pattern**, falsely confirmed "none remain" — the stale refs shipped and were caught only by a downstream reviewer. When a verification check shares the substitution/assumption of the thing it verifies, a true-negative is indistinguishable from success.

**Rule.** Verify with an independent oracle: anchor existence, a differently-shaped grep, or a count — never the fix's own pattern. The oracle's query must be structurally independent from the transformation it verifies. (Source: ~/.claude, 2026-05-30.)

## Related

- CLAUDE.md § Verification Before Done — boot-context rules (shipped-on-main, concurrent-sweep verify, smoke-test dispatch).
- CLAUDE.md § Verifying Handoff Premises, § Verifying Executor Output After a Crash or Timeout — boot-context tripwires this section expands.
- `verification-before-completion.md` § Runtime Readiness vs. Green Tests — the daemon/editable-install/e2e-symptom half of this bucket.
- `cleanup-sweep-hazards.md` — sweep operations, auto-discovery globs, scaffolding-deletion checks.
- `test-design-discipline.md` — AC table predicates, regression nets, contract-change grep, vacuous-pass risks.
- `round-trip-contract-tests.md` — producer/consumer schema verification.
