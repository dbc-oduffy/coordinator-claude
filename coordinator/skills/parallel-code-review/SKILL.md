---
name: parallel-code-review
description: Pre-merge weekly code-review gate — N code-semantics chunk reviewers (Sonnet) + 3 mechanical specialist workers + no-rewrite synthesizer (BLOCKED/WARN/OK). The Staff Engineer runs a separate post-gate architecture pass, not the gate itself. Invoked only from /workweek-complete.
description-budget: 350
argument-hint: "[--force] [--gate-mode strict|advisory]"
version: 2.0.0
---

<!-- Spec backlink: docs/plans/2026-05-06-parallel-code-review-weekly-gate.md Phase 3 -->
<!-- Spec backlink: docs/plans/2026-05-23-weekly-gate-restructure-and-arch-survey-audit-rename.md § Strand 1 -->

# Parallel Code Review

## Overview

I'm using coordinator:parallel-code-review for the /workweek-complete pre-merge code-review gate.

This skill snapshots the week's diff against `origin/main`, dispatches **N Sonnet `code-reviewer-weekly` instances over disjoint file-scope chunks of the narrowed code-semantics scope** plus **3 mechanical specialist workers** (security, deps, tests) over the full diff, all in parallel, synthesizes their findings into a structured verdict, and halts or proceeds accordingly before release notes are drafted. It is the enforcement surface for the parallel-review merge-gate carve-out pinned in `coordinator/CLAUDE.md` § Review Sequencing.

**the Staff Engineer is NOT in this gate.** The mechanical gate (N Sonnets + 3 specialists → synthesizer verdict) is the only hard block. The Staff Engineer runs a separate architecture-altitude pass (Layer 2, post-gate, advisory) — see `/workweek-complete` Step 7.5. The doctrinal reason: named reviewers (personas) add no value on en-masse diff-sweep coverage — that is exactly the mechanical-worker domain — and everything in the week's diff already had `/workstream-complete` code review, so this gate is insurance, not a first look. Opus-tier judgment (the Staff Engineer) is reserved for architecture over the changelog digest + escalated candidates + the integration-seam set. See plan `docs/plans/2026-05-23-weekly-gate-restructure-and-arch-survey-audit-rename.md` § Why.

---

## Wrong-Context Refusal

**This skill is invoked exclusively from coordinator:/workweek-complete.** If you are reading this skill from any other context — `/workday-complete`, `/merge-to-main`, `/bug-sweep`, ad-hoc invocation — STOP. Do not proceed. Surface the misroute to the PM.

Daily wrap and per-merge surfaces have their own (lighter) review patterns. Running 4 parallel reviewers outside the weekly cadence is order-of-magnitude wrong. The sequential-review HARD RULE in `coordinator/CLAUDE.md` § Review Sequencing applies to all other surfaces; this skill's carve-out is exclusively for the weekly gate at a frozen merge-boundary diff.

(There is no runnable bash check here. The refusal is a narrative instruction the EM honours when reading the skill. The frontmatter `description` field reinforces this for any automated router.)

---

## Lens-Domain Manifest

The gate has two distinct structural axes. **Orthogonal lenses** are independent in domain — no two share a lens domain, which is the property that makes convergent findings meaningful. **Scope partitions** are the N chunks WITHIN the code-semantics lens — they share a lens domain but are disjoint by file-scope, so they are not orthogonal to each other; they partition.

**Orthogonal lenses (one row per domain):**

| Lens (agent) | Lens domain | Rationale |
|---|---|---|
| code-semantics chunk reviewers (`agents/code-reviewer-weekly.md`) | code-semantics | N Sonnet `code-reviewer-weekly` instances, each scoped to a disjoint file-scope chunk of the narrowed scope. Read code semantically — correctness, architecture, naming, error handling, SOLID. As a **class** this is one orthogonal lens; the N instances partition it by file-scope. |
| security-audit-worker (`agents/security-audit-worker.md`) | pattern-scan | Runs semgrep/bandit/gitleaks/trufflehog over the full diff; pattern-matches injection, traversal, secret leakage. |
| dep-cve-auditor (`agents/dep-cve-auditor.md`) | dep-tree | Runs language-appropriate CVE audit over the full diff; classifies vs. actual usage. |
| test-evidence-parser (`agents/test-evidence-parser.md`) | test-runtime | Runs the test command, classifies failures (real / flake / env / timeout / known-skip). |

**Scope partitions (runtime, not in this static table):** the N `chunk-<k>` reviewers within the code-semantics lens. They are built seam-first (see Snapshot → Chunking) and asserted disjoint-by-file-scope at dispatch time via the chunk-manifest, NOT here.

**Orthogonality vs. partition — two assertions:**
- `verify-parallel-review-lens-orthogonality.sh` (no args, static, `/update-docs` Phase 11) asserts no two **lens domains** collide in the table above and each named agent file exists. The code-semantics lens appears ONCE here (as a class), so it does not self-collide.
- `verify-parallel-review-lens-orthogonality.sh --chunk-manifest $FINDINGS_DIR/chunk-manifest.tsv` (runtime, pre-dispatch) asserts the N chunk **partitions are disjoint by file-scope** — no file appears in two chunks.

**Adding a 5th orthogonal lens requires editing this table AND `verify-parallel-review-lens-orthogonality.sh`.** Agent files are NOT the source of truth for the manifest — this skill owns it. See plan `docs/plans/2026-05-06-parallel-code-review-weekly-gate.md` Phase 3.5 and `docs/plans/2026-05-23-weekly-gate-restructure-and-arch-survey-audit-rename.md` § Strand 1c.

---

## Gating Rules

**Rule 1 wins over Rule 2; Rule 2 wins over Rule 3; Rule 3 wins over default. Rules are evaluated with `grep -E` for consistency.**

- **Rule 1 (skip-all-tiny-or-internal):** if `git diff --shortstat origin/main...HEAD` shows fewer than 10 changed lines OR all changed files match `^(tasks/|tmp/|archive/|\.claude/scheduled_tasks)`, log `Code-review gate: SKIPPED (rule 1 — diff <10 lines or internal-only paths).` and exit 0. **Note: `docs/wiki/` is intentionally NOT in this filter** — wiki edits remain eligible for security-audit-worker (gitleaks may catch leaked secrets in code samples). A week with <10 lines changed is implausible at weekly cadence; this rule exists for completeness.

- **Rule 2 (skip-code-semantics-on-doc-only):** if every changed file matches `\.(md|rst|txt)$` AND no file matches `\.(py|js|ts|sh|c|cpp|h|hpp|rs|go|java|cs)$`, set `SKIP_CODE_SEMANTICS=1`. Dispatch zero `code-reviewer-weekly` chunks; run the 3 mechanical specialist workers only. **Write the class-level skip sentinel** so the synthesizer distinguishes intended-zero from dispatch-failure:
  ```bash
  printf 'skipped: doc-only\n' > "$FINDINGS_DIR/code_semantics_skip.sentinel"
  ```
  Doc-only weeks are possible but rare at weekly cadence.

- **Rule 3 (skip-entire-gate-on-plan-only):** if every changed file matches `^docs/plans/`, log `Code-review gate: SKIPPED (rule 3 — plan-only diff; staff-eng review on plans goes through /review).` and exit 0. Plan-only diffs are handled at authoring time via `/review`, not at the weekly boundary.

- **Rule 4 (`--force` escape):** if `$ARGUMENTS` contains `--force`, log `Code-review gate: BYPASSED via --force.` and exit 0.

### Worked examples — weekly-cadence reality

| Rule | Sample diff | Expected gate behavior |
|---|---|---|
| Rule 1 | 4 changed lines in `tasks/some-task/todo.md` | SKIPPED (rule 1 — diff <10 lines or internal-only paths) |
| Rule 2 | `docs/wiki/tiered-context-loading.md` only (no code files) | SKIP_CODE_SEMANTICS=1 — 3 mechanical specialists run; zero chunks; skip sentinel written |
| Rule 3 | `docs/plans/2026-05-06-foo.md` only | SKIPPED (rule 3 — plan-only diff) |
| Rule 4 | Any diff with `--force` | BYPASSED via --force |
| Default | 500-2000 changed lines, mixed `.ts` + `.md` + `.sh` | N code-semantics chunks + 3 specialists run — **this is the typical week** |

At weekly cadence (`/workweek-complete`), the typical week has 500-2000 changed lines mixed code+docs+plans — none of Rules 1-3 fire and the default (N chunk reviewers + 3 specialists) is the common path. The skip rules exist for completeness, not as the dominant cadence.

---

## Pre-Flight Orthogonality Assertion

Before dispatch, assert that agent files exist and no two lens domains collide (static manifest check):

```bash
~/.claude/plugins/coordinator/bin/verify-parallel-review-lens-orthogonality.sh || {
  echo "Lens-orthogonality assertion failed; refusing to dispatch."
  exit 1
}
```

If this fails: do NOT proceed with the parallel dispatch. Surface the failure to the PM — it means either an agent file has gone missing or the manifest table above has been edited to introduce a domain collision.

After chunking (below) and before dispatching the chunk reviewers, assert the N chunk partitions are disjoint by file-scope:

```bash
~/.claude/plugins/coordinator/bin/verify-parallel-review-lens-orthogonality.sh \
  --chunk-manifest "$FINDINGS_DIR/chunk-manifest.tsv" || {
  echo "Chunk partitions are not disjoint by file-scope; refusing to dispatch."
  exit 1
}
```

A file appearing in two chunks means two chunk reviewers would review the same file — breaking the disjoint-partition property the synthesizer's convergence logic depends on. Re-chunk before dispatching.

---

## Snapshot

Freeze the diff and current HEAD before dispatching any reviewers. This is the "frozen diff at merge boundary" guarantee from the carve-out's condition (a).

```bash
TS=$(date -u +%Y%m%dT%H%M%SZ)
FINDINGS_DIR="state/review-findings/$TS"
mkdir -p "$FINDINGS_DIR"
git diff origin/main...HEAD > "$FINDINGS_DIR/diff.patch"
git rev-parse HEAD > "$FINDINGS_DIR/head.sha"
```

`head.sha` records the HEAD at snapshot time. The synthesizer compares against current HEAD at synthesis time; if the branch has advanced (head drift), it emits `verdict: WARN` with `head_drift: true` per Risk 8 in the plan.

---

## Chunking — seam-first construction of the code-semantics partitions

The narrowed code-semantics scope is `patrik_scope` from the Step 7 prelude (`workweek-trail-scope.sh` output: `patrik` SHA set + `patrik_seam_files` path set). It is NOT the whole week — it is unreviewed-since-workstream-complete commits PLUS cross-segment seam files. The 3 specialist workers see the full diff; only the code-semantics lens is narrowed and chunked.

Build the N chunks **seam-first** (hard constraint — `coordinator/CLAUDE.md` lineage and plan § Strand 1 F2):

1. **Seam nuclei first.** Each `cross_segment_seam` file (a file touched by ≥2 distinct sessions this week) plus the union of hunks each contributing session touched (the minimal both-sides context) forms an **atomic nucleus**. Assign each nucleus whole to exactly ONE chunk. The minimal both-sides set (seam file + contributing-session hunks) MUST stay intact in a single chunk — non-negotiable. Two chunks never split a seam file.
2. **Overflow rule.** If a nucleus exceeds the size target, the seam file and its minimal two-session diff context stay whole in one chunk; only NON-seam co-touching files spill to a sibling chunk.
3. **Fill with remaining narrowed-scope files.** Group the rest by coherent surface (subsystem / directory), target ≤ ~25 files or one coherent subsystem per chunk.
4. **Disjoint by file-scope.** No file appears in two chunks. This is asserted mechanically by the `--chunk-manifest` check above.

Write the chunk manifest as a TSV — one `chunk-<k>\t<relpath>` line per file, used by the disjointness assertion:

```bash
# Example shape; the EM constructs the actual mapping per the rules above.
# $FINDINGS_DIR/chunk-manifest.tsv
#   chunk-1<TAB>path/to/seam_file.ts
#   chunk-1<TAB>path/to/contributing_a.ts
#   chunk-2<TAB>path/to/other_subsystem.ts
```

On a doc-only week (`SKIP_CODE_SEMANTICS=1`): write zero chunks, write the `code_semantics_skip.sentinel`, skip the `--chunk-manifest` assertion (no chunks to check).

---

## Parallel Dispatch

Dispatch all reviewers (the N chunk reviewers per the chunk manifest + the 3 specialist workers, or the active subset per gating rules) in a single multi-tool-call batch. All dispatches go out simultaneously — this is the independence guarantee. Each reviewer reads `$FINDINGS_DIR/diff.patch` and writes its findings to its own file in `$FINDINGS_DIR/`.

Per-reviewer dispatch shape (actual prompts assembled at dispatch time from the agent files):

- **Chunk reviewers** (`agents/code-reviewer-weekly.md`, one per chunk; skip ALL if `SKIP_CODE_SEMANTICS=1`): assign chunk `<k>` its file-scope list from the chunk manifest, point it at `$FINDINGS_DIR/diff.patch` for context, instruct it to write **only** `$FINDINGS_DIR/chunk-<k>.md` (incrementally). Each is a Sonnet `code-reviewer-weekly`; it reviews its disjoint file-scope partition (seam files with extra integration scrutiny), marks architectural findings `escalate_to_architecture: true`, and emits a verdict. **Read-only on source — scoped-write to its single findings file only.** No AUTO-FIX at this gate; the integrator is a separate cycle.

- **security-audit-worker**: scan `$FINDINGS_DIR/diff.patch` (full diff) for injection vectors, secret leakage (gitleaks), unsafe patterns, path traversal. Output to `$FINDINGS_DIR/security.md`.

- **dep-cve-auditor**: scan repo dependency manifests at HEAD, classify CVEs against actual usage in the diff. Output to `$FINDINGS_DIR/deps.md`.

- **test-evidence-parser**: run the project test command, collect output, classify failures as real / flake / env / timeout / known-skip. Output to `$FINDINGS_DIR/tests.md`.

Each dispatcher prompt must include `expected_branch: <current-branch>`. Reviewers do not commit — they write findings to disk only. The disk-first doctrine applies: each file must exist and be >1KB before proceeding to the synthesizer. The EM verifies chunk-reviewer scope on return via `git status` — a single new `chunk-<k>.md` per chunk reviewer is the expected footprint; any other touched path is a contract violation to revert.

---

## Synthesizer Pre-Flight and Dispatch

Before dispatching the synthesizer, validate each expected findings file:

- Each discovered `chunk-<k>.md` (glob `$FINDINGS_DIR/chunk-*.md`) plus the 3 specialist files (or the dispatched subset per gating rules) must exist on disk. On a doc-only week there are zero chunk files and the `code_semantics_skip.sentinel` must be present.
- Each must be non-empty — apply the 1KB threshold from disk-first doctrine (`coordinator/CLAUDE.md` § Scouts and Disk-First Verification). A 1-2KB file where the brief expected substantially more is a summary masquerading as a deliverable; treat as a failed dispatch.
- If a file fails this check: emit `verdict: WARN` with `lens_coverage[<reviewer>]: failed_disk_read` and surface to EM. **Do NOT default a missing reviewer's findings to "no findings = no issues"** — that silently downgrades coverage without visibility.

**quota-exhausted dispatch detection — scan each chunk-reviewer slice's return body BEFORE synthesizer dispatch.**

The doctrine root is `docs/wiki/tool-output-flakiness-protocol.md § API quota exhaustion looks like a clean "completed" return with error-text body`. Pattern set + corroboration rule (inlined here so the rule is greppable from the skill itself, per the dual-altitude convention with `snippets/quota-self-detect-preamble.md`):

| Pattern (case-INsensitive) | Alone-sufficient? |
|---|---|
| `resets [0-9][0-9]?:[0-9][0-9]` | Yes — time-signature is structurally unique to the quota-apology shape. |
| `session limit` | No — requires body length < 1024 bytes. |
| `rate limit` | No — requires body length < 1024 bytes. |
| `quota` | No — requires body length < 1024 bytes. |

**Also recognize the `QUOTA-EXHAUSTED-DISPATCH:` envelope** as a definite quota event (the agent self-detected and substituted — see `snippets/quota-self-detect-preamble.md`). No corroboration needed; the envelope IS the corroboration.

**On match:** treat the dispatch as failed-needing-re-dispatch. Do NOT write a verdict-ok trail record. Either (a) wait for quota reset and re-dispatch with the original brief, or (b) escalate to PM with the partial-coverage situation. The EM decides retry vs escalate based on retry budget. → `docs/wiki/tool-output-flakiness-protocol.md § API quota exhaustion`.

Quota-matching slices are excluded from synthesis; the merge gate is held until they re-dispatch successfully OR the PM authorizes proceeding with partial coverage.

Once all present files pass pre-flight, dispatch Sonnet `parallel-review-synthesizer` (`agents/parallel-review-synthesizer.md`). It discovers the chunk set, reads the validated findings files from disk, applies the no-rewrite contract, aggregates `escalate_to_architecture` flags into `arch_tier_candidates`, and writes `$FINDINGS_DIR/synthesis.json`. The synthesizer must not be dispatched until all reviewer findings are on disk.

---

## Verdict Emission

Read `$FINDINGS_DIR/synthesis.json`. Format the one-line verdict for the release-notes draft (Step 9 of /workweek-complete) and eventual PR body:

```markdown
**Code-review gate:** [BLOCKED|WARN|OK] — convergent: N — code-semantics: <N chunks, P0/P1/P2/nit counts> — arch-tier candidates: <count> — security: <count> — deps: <count> — tests: <pass/fail/flake>
```

`arch-tier candidates: <count>` is the size of `arch_tier_candidates` — it feeds the Staff Engineer's Layer-2 pass (Step 7.5), not the gate verdict. Return this string plus the findings-dir path on stdout for the calling command to consume.

---

## Gate Behavior

### BLOCKED

Exit non-zero. `/workweek-complete` halts before Step 9 (Release Notes) and before Step 11 (`/merge-to-main`). Surface the verdict line and path to `$FINDINGS_DIR/synthesis.json` to the PM.

Resolution: fix the flagged issue and re-run the skill, or pass `--force` to bypass. Do NOT proceed to release notes or merge while BLOCKED without explicit PM direction.

Triggered by: any P0/P1 from a code-semantics chunk reviewer OR any HIGH-severity finding from security-audit-worker OR any unfixed CVE ≥ HIGH from dep-cve-auditor OR any real (non-flake) test failure. A non-empty `arch_tier_candidates` bucket does NOT trigger BLOCKED — it feeds the Staff Engineer's advisory Layer-2 pass.

### WARN

Exit 0. Include the verdict line in the release-notes draft (Step 9) and carry it into the eventual PR body via `/merge-to-main`'s normal release-notes pickup.

Triggered by: no BLOCKED triggers AND any P2/nit from a code-semantics chunk reviewer OR MEDIUM/LOW security finding OR MEDIUM CVE OR `convergent_findings` count ≥ 1 OR any `lens_coverage` entry `failed_disk_read` OR head drift.

### OK

Exit 0. Verdict line still goes into the release-notes draft for the record; no warning block in the release notes. Proceed silently.

---

## Cost Discipline

At weekly cadence (~1 invocation/week × ~75-200K tokens per invocation = ~75-200K tokens/week), token cost is trivial compared to a per-merge cadence. No per-invocation budget cap is applied. See `coordinator/CLAUDE.md` § Workday/Workweek Cadence for cadence context. Token-budget tripwire was Gate-1 Finding-3 conditional on per-merge cadence; at weekly cadence it is no longer load-bearing (PM direction 2026-05-06).

---

## Recovery and Resume

If any reviewer dispatch (a chunk reviewer or a specialist) fails, retry once via `SendMessage` (per `coordinator/CLAUDE.md` § Scouts and Disk-First Verification — resume from transcript, do not redispatch from scratch). Second failure after retry: emit `verdict: WARN` with `lens_coverage[<reviewer>]: failed_disk_read` and DO NOT block on infra noise. A single reviewer dropping out due to infra failure degrades to WARN, not BLOCKED — only genuine code-quality findings trigger BLOCKED.

---

## Carve-Out Enforcement Mapping

The parallel-review carve-out in `coordinator/CLAUDE.md` § Review Sequencing has three trigger conditions, each with a named enforcement mechanism in this skill:

| Carve-out condition | Enforcement mechanism |
|---|---|
| (a) Frozen diff at merge boundary | Snapshot section above: `git diff origin/main...HEAD > diff.patch`; `head.sha` records HEAD at snapshot time; synthesizer checks for head drift. |
| (b) All reviewers are orthogonal lenses | Two assertions: the orthogonal **lens domains** (3 specialists + code-semantics-as-a-class) carry no collision — verified by `verify-parallel-review-lens-orthogonality.sh` (no args) in `/update-docs` Phase 11; the N code-semantics **chunk partitions** are disjoint by file-scope — verified by the same script with `--chunk-manifest` at pre-dispatch time. Chunks share the code-semantics lens by design (they partition, not orthogonalize); convergence is only meaningful across distinct lens domains. |
| (c) No-rewrite synthesizer | Output schema in `agents/parallel-review-synthesizer.md` with `evidence_quote` verbatim fields; `verdict_rationale` is the only synthesizer-authored prose (one sentence). |

This mapping makes the doctrine bullet auditable from the skill — per plan `docs/plans/2026-05-06-parallel-code-review-weekly-gate.md` Phase 4A (the Staff Engineer R1 F10).
