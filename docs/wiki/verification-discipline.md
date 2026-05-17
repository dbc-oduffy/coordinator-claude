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

## Related

- CLAUDE.md § Verification Before Done — boot-context rules (shipped-on-main, concurrent-sweep verify, smoke-test dispatch).
- `cleanup-sweep-hazards.md` — sweep operations, auto-discovery globs, scaffolding-deletion checks.
- `test-design-discipline.md` — AC table predicates, regression nets, contract-change grep, vacuous-pass risks.
- `round-trip-contract-tests.md` — producer/consumer schema verification.
