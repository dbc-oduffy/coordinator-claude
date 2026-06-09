# Pre-Dispatch Verification — Extras

**System:** coordinator
**Provenance:** consolidated 2026-05-14 from `state/coordinator-improvement-queue.md` triage (E24, E131, E136, E161).

Extensions to [`pre-dispatch-verification.md`](pre-dispatch-verification.md) for specific failure modes the parent wiki doesn't carry — predicate-claim verification against schema, write-seam grep (not just read-seam), numeric-constant transcription, and mechanical enumeration as the source-of-truth for audit tables. Companion to `coordinator/CLAUDE.md` § Pre-Dispatch Verification; keep the parent for headline rules, this file for the long tail.

---

## When this applies

These rules fire at plan-write time, alongside the parent wiki's premise-pass discipline. They cover four failure modes the parent doesn't enumerate: claim-shaped predicates that cite schema fields, grep coverage that stops at read seams and forgets writes, numeric constants transcribed from memory instead of from the asserting test, and hand-built audit tables that miss what an existing AST/grep coverage script already enumerates.

---

## Rules

- **Predicate claims citing schema fields MUST grep the schema definition before plan-write.** When a plan asserts a condition like "when `frontmatter.deployment_state == awaiting_gate`," confirm the field exists in the frontmatter validator, JSON schema, or dataclass before the executor depends on it. Fabricated field references are a recurring plan-stage failure — the predicate reads correctly, the executor wires up against a field that was renamed or never existed.

- **Numeric constants quoted into a dispatch brief MUST be verified against the asserting test or contract.** Timeouts, thresholds, RSS limits, retry counts, descendant counts, cutoff values — grep them out of the test or contract that enforces them, not memory. Citing `TIMEOUT=30` when the contract is `TIMEOUT=60` gets faithfully transcribed into a dispatch that the executor then implements correctly against the wrong number. The fix is upstream of the executor, not in review.

- **Pre-dispatch grep-seams discipline extends to WRITE seams, not just read seams.** If a headless handler writes to a collection — asset registry, content folder, data table, frontmatter sidecar — grep where the engine's blessed write path lands and mirror that placement. Off-path writes silently degrade: the data is there, but the engine's discovery path doesn't reach it, so consumers behave as if the write never happened. Read-seam coverage at plan time is not sufficient when the plan introduces writes.

- **If a coverage test exists that enumerates affected sites, run it FIRST and use its output as the audit table.** AST visitors, grep-coverage scripts, schema-coverage tools, snippet-sync verifiers — any mechanical enumerator that already covers the surface is the single source of truth. Hand-built audit tables miss what mechanical enumeration finds (longer identifiers, kwarg-split call shapes, here-doc variants, dynamic dispatch). Treat the coverage tool's output as the table; the plan body cites and quotes it rather than re-enumerating from memory or grep.

---

## Additional recipes (2026-05-14 central /learn-lessons grind)

- **Verify-then-fix is the executor protocol when the brief cites a classifier/audit substrate.** Substrate audits (classifiers, sweep agents, structural-index scans, P0/P1 finders) report file:line claims as hypothesis, not ground truth. Executor briefs against this substrate must instruct: "Read the cited site first; confirm the symptom is present in current source; THEN apply the fix." Without this preamble, executor faithfully patches a location the substrate misclassified — and the real symptom survives. Pairs with the P0/P1 Verification Gate in CLAUDE.md but extends it from EM-side to executor-side.

- **Pre-resolved substrate values still need `ls` defense-in-depth at executor time.** When a reviewer or prior wave hands the executor a resolved path / constant / SHA / branch name in the brief, the executor must `ls` / `git rev-parse` / `grep` the value against current disk before consuming. Pre-resolution is hypothesis frozen at an earlier moment; concurrent EMs and intervening commits invalidate freezes silently. Belt-and-braces over substrate trust.

- **Increment-by-N beats absolute baselines in stubs and dispatch briefs.** Periodic baselines (commit counts, row totals, version numbers, file-count snapshots) drift between plan-write and dispatch. When the assertion is "the value will be X at executor time," prefer "the value will be (current + N)" — read-current-then-add survives wall-clock drift; absolute-baseline-match breaks the first time another session lands an unrelated commit. Tell executors to read-current rather than match-spec for any monotonically-changing baseline.

- **Verify recorder column labels and table schemas before trusting them as audit sources.** When a recorder / metric pipeline / row-count export names a count under a column label, the column label is a claim about schema, not a verification of it. Same applies to runtime FK auto-detection: necessary but not sufficient — auto-detection on one table doesn't prove the FK shape holds on sibling tables. Grep the actual schema (DDL, dataclass, JSON schema, sqlite `PRAGMA table_info`) per affected table before plan-write cites the column / FK as load-bearing.

- **Enriching a spike: backward-search for prior probes before reasoning forward from API gates.** When enriching a spike, before walking the engine's reference docs to derive what the probe should look like, grep the repo for prior probes that touched this surface — sibling tests, archived plans, lessons.md entries, queue resolutions. Forward-from-API-gates reasoning produces "designed" probes that bypass the cheaper signal: someone already characterised this surface and the answer is in-tree. Backward-search first; forward-derive only if the backward pass is genuinely empty.

- **EM resolutions need the same evidence-floor as code changes.** When closing an open question, marking a queue entry resolved, or ratifying a reviewer's recommendation, the EM must cite the same `grep` / `Read` / `git log` evidence a code change would require. "Resolved — substrate confirmed" without a file:line citation or a pyproject/config snippet is no different from a fabricated commit attribution: hypothesis frozen as decision. The evidence-floor is symmetric across implementer roles and orchestrator roles.

- **Enricher STOP gates catch plan-level errors before executors hit them.** When a plan targets an external surface (third-party API, sibling-repo contract, plugin manifest, MCP tool name), the enrichment phase MUST run a source-verification STOP gate before the plan ships to dispatch: read the external surface's current shape, compare to plan's cited shape, halt the plan if they diverge. Plan-level errors that get past enrichment cost an executor wave and a re-plan; STOP-gate at enrichment-time costs one read.

---

## Smoke-Test Executor Deliverables Under Edge-Case Inputs Before EM Commit

**An executor returning green tests only certifies the authored test cases — not uncovered input shapes.**

When an executor reports N/N tests green, those tests cover what was written, not what can happen. A real bug can sit in an uncovered input shape (e.g., a `--date-prefix` filter with zero matches erroring on a missing tempfile despite all N happy-path cases passing). EM-commit time is the last cheap moment to exercise a deliverable.

**How to apply:** after an executor returns, run 1-2 real-world invocations with edge-case inputs (zero-match queries, missing optional args, empty datasets) before committing. Take 60 seconds; a bug found here costs a follow-up queue entry if deferred. Treat as a closing gate at EM-commit time, not a reviewer's job.

*Source: 2026-05-28 sweep; `--date-prefix` filter errored on zero-match despite 7/7 green.*

---

## Related

## Old cross-repo handoff — re-verify failure modes before grinding the original investigation

Old cross-repo handoffs age. Re-verify the failure modes against the current sibling substrate before grinding the original investigation. Re-repro is cheap (a few test runs); grinding a stale spec is expensive (hours of work that may not apply). Apply: for any handoff older than a day, run `git log --oneline -- <cited-paths>` on the sibling before accepting the handoff's failure-mode description.

## Roadmap stub authored against old substrate — premise-check against sibling DRs

A roadmap stub authored against old substrate can rest on a false premise a sibling ticket already corrected. Before executing a stub, check sibling DRs + the live branch — not just the stub's own disk state. Stubs inherit-don't-regenerate extends across repos; sibling DRs can retire a stub's premise before it's executed. Apply: for any roadmap stub older than a few days, run `bin/query-records --kind decision` on the sibling repo before treating the stub's premise as current.

## gh release list != git tag -l when checking a version surface

`gh release list` and `git tag -l` are disjoint namespaces — a tag that isn't a GitHub Release won't appear in `gh release list`, and a draft release won't appear in `git tag -l`. Before asserting a versioning surface is missing, query both plus `git ls-remote --tags`. Apply: any "is version X published?" check must query all three surfaces.

- [`pre-dispatch-verification.md`](pre-dispatch-verification.md) — parent doctrine
- `coordinator/CLAUDE.md` § Pre-Dispatch Verification — canonical bullet list
- [`tiered-context-loading.md`](tiered-context-loading.md) — what to read before dispatching
- [`prior-art-checker.md`](prior-art-checker.md) — automated pre-flight against accumulated prior art
