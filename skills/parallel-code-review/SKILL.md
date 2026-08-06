---
name: parallel-code-review
description: "Weekly pre-merge code-review gate — chunk reviewers, one verdict. /workweek-complete only."
argument-hint: "[--force] [--gate-mode strict|advisory]"
version: 2.0.0
---

# Parallel Code Review

## Overview

I'm using coordinator:parallel-code-review for the /workweek-complete pre-merge code-review gate.

This skill snapshots the week's diff against `origin/main`, dispatches **N Sonnet `code-reviewer-weekly` instances over disjoint file-scope chunks of the narrowed code-semantics scope** plus **3 mechanical specialist workers** (security, deps, tests) over the full diff, all in parallel, synthesizes their findings into a structured verdict, and halts or proceeds accordingly before release notes are drafted. It is the enforcement surface for the parallel-review merge-gate carve-out pinned in `coordinator/snippets/em-operating-doctrine.md` § How to Review What Came Back.

**the Staff Engineer is NOT in this gate.** The mechanical gate (N Sonnets + 3 specialists → synthesizer verdict) is the only hard block. The Staff Engineer runs a separate architecture-altitude pass (Layer 2, post-gate, advisory) — see `/workweek-complete` Step 7.5. The doctrinal reason: named reviewers (personas) add no value on en-masse diff-sweep coverage — that is exactly the mechanical-worker domain — and everything in the week's diff already had `/workstream-complete` code review, so this gate is insurance, not a first look. Opus-tier judgment (the Staff Engineer) is reserved for architecture over the changelog digest + escalated candidates + the integration-seam set.

---

## Wrong-Context Refusal

**This skill is invoked exclusively from coordinator:/workweek-complete.** If you are reading this skill from any other context — `/workday-complete`, `/merge-to-main`, `/bug-sweep`, ad-hoc invocation — STOP. Do not proceed. Surface the misroute to the PM.

Daily wrap and per-merge surfaces have their own (lighter) review patterns. Running 4 parallel reviewers outside the weekly cadence is order-of-magnitude wrong. The sequential-review HARD RULE in `coordinator/snippets/em-operating-doctrine.md` § How to Review What Came Back applies to all other surfaces; this skill's carve-out is exclusively for the weekly gate at a frozen merge-boundary diff.

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
| test-evidence-parser (`agents/test-evidence-parser.md`) | test-runtime | Reads an EM-captured raw test-output file (it does not run the test command itself — no Bash on its tool surface), classifies failures (real / flake / env / timeout / known-skip). |

**Scope partitions (runtime, not in this static table):** the N `chunk-<k>` reviewers within the code-semantics lens. They are built seam-first (see Snapshot → Chunking) and asserted disjoint-by-file-scope at dispatch time via the chunk-manifest, NOT here.

**Orthogonality vs. partition — two assertions:**
- `verify-parallel-review-lens-orthogonality.py` (no args, static, `/update-docs` Phase 11) asserts no two **lens domains** collide in the table above and each named agent file exists. The code-semantics lens appears ONCE here (as a class), so it does not self-collide.
- `verify-parallel-review-lens-orthogonality.py --chunk-manifest $FINDINGS_DIR/chunk-manifest.tsv` (runtime, pre-dispatch) asserts the N chunk **partitions are disjoint by file-scope** — no file appears in two chunks.

**Adding a 5th orthogonal lens requires editing this table AND `verify-parallel-review-lens-orthogonality.py`.** Agent files are NOT the source of truth for the manifest — this skill owns it.

---

## Gating Rules

**Rule 1 wins over Rule 2; Rule 2 wins over Rule 3; Rule 3 wins over default.**

Run `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/parallel-review-gate-decision" gate --range "origin/main...HEAD" [--force]` — a naked-Python, self-locating, read-only assembler that computes Rules 1-4 over `git diff --shortstat`/`--name-only` (previously reader-performed `grep -E` comparisons) and prints the canonical 8-key decision envelope. Branch on `decisions.gate.action`:

- **`skip_gate` (Rule 1: skip-all-tiny-or-internal, or Rule 3: skip-entire-gate-on-plan-only):** log `decisions.gate.reason` (the envelope names which rule fired) and exit 0. Rule 1 fires on <10 changed lines OR all changed files matching `^(tasks/|tmp/|archive/|\.claude/scheduled_tasks)` — **`docs/wiki/` is intentionally NOT in this filter**, wiki edits remain eligible for security-audit-worker (gitleaks may catch leaked secrets in code samples). Rule 3 fires on every changed file matching `^docs/plans/` — plan-only diffs are handled at authoring time via `/review`, not at the weekly boundary.

- **`skip_code_semantics` (Rule 2: skip-code-semantics-on-doc-only):** every changed file matches `\.(md|rst|txt)$` and none matches `\.(py|js|ts|sh|c|cpp|h|hpp|rs|go|java|cs)$`. Set `SKIP_CODE_SEMANTICS=1`. Dispatch zero `code-reviewer-weekly` chunks; run the 3 mechanical specialist workers only. **Write the class-level skip sentinel** so the synthesizer distinguishes intended-zero from dispatch-failure — write `skipped: doc-only\n` as the sole content of `$FINDINGS_DIR/code_semantics_skip.sentinel` (`printf 'skipped: doc-only\n' > "$FINDINGS_DIR/code_semantics_skip.sentinel"` — kept inline; a single-line, non-branching write earns no named op). Doc-only weeks are possible but rare at weekly cadence.

- **`bypass` (Rule 4, `--force` escape):** `$ARGUMENTS` contained `--force`. Log `decisions.gate.reason` and exit 0.

- **`run_default`:** N code-semantics chunks + 3 specialists run — the typical week.

`gate`'s `judgment_points` is always `[]` — Rules 1-4 are fully mechanical and auto-fire; no EM call is paused on this step.

- **Rule 5 (narrow-or-skip-on-already-reviewed-span — EM-judgment, not auto-fired):** when the span under review is a large catch-up (a multi-week span, or any span where the `staff_eng_seam_files` count balloons because many workstreams touched overlapping files — cockpit's first weekly in ~2.5 weeks produced 1970 commits / 2960 seam files) AND the span's commits are dominated by review-trail verdicts (every workstream already carries a `code-reviewer` / `wsc-auto-adjudication` verdict from `/workstream-complete` time), the chunk gate re-reviews already-verdicted code with **strictly less** context than the reviews already on record — the original reviews ran WITH the plan doc, chunk briefs, and acceptance criteria in the reviewer's window; the weekly chunk-reviewer sees a raw file slice with none of that. It is not merely redundant, it is a weaker review at higher token cost.

  Run `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/parallel-review-gate-decision" rule5-inputs --scope-shas-file <scope-shas> --seam-files-file <seam-files> --review-trail-dir state/review-trail` to compute Rule 5's INPUTS only — `unreviewed_set`, `seam_shas`, `commit_count`, `seam_file_count`, per-workstream review-trail coverage — surfaced under `preflight.rule5_inputs` plus one `jp_rule5_skip_vs_narrow` entry in `judgment_points` (dispositions `narrow`/`skip`, no `recommendation` field — the constructor used cannot smuggle a verdict). **The assembler never decides skip-vs-narrow — that call stays here, in the skill body.** Given those inputs the EM MAY either:
  - **(a) skip the chunk gate**, recording the gate verdict as `incrementally-reviewed` with the week's `state/review-trail/*.json` records named as the evidence trail; or
  - **(b) narrow the chunk gate to the genuinely un-reviewed subset** — the `unreviewed_set`, leaving seam-only-reviewed commits out. The scope shard's `staff_eng` set is `unreviewed_set ∪ seam_shas`; narrowing means dropping the seam-only contribution.

  Unlike Rules 1–4 this does not auto-fire from a `git diff` predicate — the trigger is *disproportionality on an already-reviewed span*, which the mechanical rules can't cleanly threshold, so it is a deliberate EM call (cockpit PM + EM concurred on their span). Record the chosen path and the evidence trail in the gate verdict line. Rules 1–4 still take precedence when they fire.

### Worked examples — weekly-cadence reality

| Rule | Sample diff | Expected gate behavior |
|---|---|---|
| Rule 1 | 4 changed lines in `tasks/some-task/todo.md` | SKIPPED (rule 1 — diff <10 lines or internal-only paths) |
| Rule 2 | `docs/wiki/tiered-context-loading.md` only (no code files) | SKIP_CODE_SEMANTICS=1 — 3 mechanical specialists run; zero chunks; skip sentinel written |
| Rule 3 | `docs/plans/<any-plan>.md` only | SKIPPED (rule 3 — plan-only diff) |
| Rule 4 | Any diff with `--force` | BYPASSED via --force |
| Rule 5 | 1970-commit catch-up span, 2960 seam files, every workstream already `code-reviewer`-verdicted | EM-judgment: skip → `incrementally-reviewed` (trail records as evidence), OR narrow to the un-reviewed subset |
| Default | 500-2000 changed lines, mixed `.ts` + `.md` + `.sh` | N code-semantics chunks + 3 specialists run — **this is the typical week** |

At weekly cadence (`/workweek-complete`), the typical week has 500-2000 changed lines mixed code+docs+plans — none of Rules 1-3 fire and the default (N chunk reviewers + 3 specialists) is the common path. The skip rules exist for completeness, not as the dominant cadence.

---

## Pre-Flight Orthogonality Assertion

Before dispatch, assert that agent files exist and no two lens domains collide (static manifest check). Run `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/parallel-review-orthogonality-guard" guard` — a thin, self-resolving wrapper over the sibling `verify-parallel-review-lens-orthogonality.py` CLI (no cross-repo root resolution needed; the two CLIs live side by side in claude-klabauter's `coordinator/bin/`). It runs the static form, echoes the wrapped CLI's own stdout/stderr, and on a non-zero exit prints `Lens-orthogonality assertion failed; refusing to dispatch.` before exiting 1.

If this fails: do NOT proceed with the parallel dispatch. Surface the failure to the PM — it means either an agent file has gone missing or the manifest table above has been edited to introduce a domain collision.

After chunking (below) and before dispatching the chunk reviewers, assert the N chunk partitions are disjoint by file-scope. Run `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/parallel-review-orthogonality-guard" guard --chunk-manifest "$FINDINGS_DIR/chunk-manifest.tsv"` — same wrapper, runtime chunk-disjointness form. On a non-zero exit it prints `Chunk partitions are not disjoint by file-scope; refusing to dispatch.` before exiting 1.

A file appearing in two chunks means two chunk reviewers would review the same file — breaking the disjoint-partition property the synthesizer's convergence logic depends on. Re-chunk before dispatching.

---

## Snapshot

Freeze the diff and current HEAD before dispatching any reviewers. This is the "frozen diff at merge boundary" guarantee from the carve-out's condition (a).

Run `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/parallel-review-orthogonality-guard" snapshot --range "origin/main...HEAD"` — it computes the UTC timestamp, creates `state/review-findings/<TS>/`, and invokes the sibling `freeze-review-diff.py` CLI to freeze the diff and `head.sha` under `state/review-trail/diffs/`. It prints a single JSON object to stdout: `{"findings_dir": ..., "weekly_slice_id": ..., "diff_path": ..., "head_sha_path": ...}`. Capture these four fields as `$FINDINGS_DIR`, `$WEEKLY_SLICE_ID`, `$DIFF_PATH`, and `$HEAD_SHA_PATH` for the remainder of this skill.

`freeze-review-diff.py` writes the frozen diff + `head.sha` under `state/review-trail/diffs/${WEEKLY_SLICE_ID}.{diff,head.sha}`. `head.sha` records the HEAD at snapshot time. `$DIFF_PATH` and `$HEAD_SHA_PATH` are the only copies of these files — reviewers and the synthesizer read them directly from `state/review-trail/diffs/`, not from `$FINDINGS_DIR`. The synthesizer compares `$HEAD_SHA_PATH` against current HEAD at synthesis time; if the branch has advanced (head drift), it emits `verdict: WARN` with `head_drift: true` per Risk 8 in the plan.

### Test-Output Capture — Tier-U, EM-only

The frozen diff above feeds the code-semantics chunk reviewers, security-audit-worker, and dep-cve-auditor. test-evidence-parser reads a fourth frozen input instead of the diff: an EM-captured raw test-output file — it carries no Bash on its tool surface and never runs the suite itself (`agents/test-evidence-parser.md`).

**This is a Tier-U (full-suite) invocation, and it is the EM's to run.** `/workweek-complete` is one of the three ceremonies that hold the *implicit* Tier-U grant — the EM does not ask before running the full suite here. That implicit grant is the only reason this step skips a PM ask; a skill invoked outside a ceremony holding its own such grant must not copy this pattern without one. The grant itself is written by `/workweek-complete` Step 0.9, before this skill is ever reached.

**Consult the grant before firing — do not rely on the ceremony having reached this step as proof enough.** Run `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/tier-u-grant-cli" check`. Exit 0 means granted — proceed. Exit 1 (ungranted) halts this step regardless of what the ceremony transcript above implies: a token absent or malformed reads as ungranted, never granted (fail-closed — see the grant schema's provenance note). On a halt, do not fabricate a fallback run — surface the ungranted state to the PM and skip Test-Output Capture for this invocation (test-evidence-parser dispatch is already skipped whenever no `$TEST_OUTPUT_PATH` exists, so this degrades the same way an unconfigured resolver does).

Resolve the full-tier command via the single-owner resolver CLI — the same one `/validate` resolves `--fast` from and `/bug-blitz` Phase 0.7 resolves `--full` from, reused here rather than reinvented. Run the installed forwarder `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-resolve-validation-cmd" --full`, capturing its stdout as `$TEST_CMD` and its exit code as `$RESOLVER_EXIT`. The forwarder self-resolves the CLI's home repo, so no separate root resolution is needed here and a future relocation of the CLI cannot break this step. Set `TEST_OUTPUT_PATH="state/review-trail/diffs/${WEEKLY_SLICE_ID}.test.log"`.

Run `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/parallel-review-gate-decision" resolver-branch --resolver-exit "$RESOLVER_EXIT" --test-cmd "$TEST_CMD"` — the same assembler as Gating Rules above, replacing the reader-resolved branch table with its own decision object. Branch on `decisions.resolver_branch.action`: **`run_full`** — full suite resolved, run `$TEST_CMD`; **`run_fast_fallback`** — fast-tier fallback (no `full_test_cmd` configured), run it anyway and note the narrower coverage honestly in the eventual verdict, same as `/bug-blitz`'s `suite_state: fast-fallback`; **`skip`** — unconfigured, do not fabricate a command — skip running the suite this week. On `run_full` or `run_fast_fallback`, run `decisions.resolver_branch.test_cmd` directly via `Bash`, redirecting stdout and stderr to `$TEST_OUTPUT_PATH`.

**Pre-scaffold `$FINDINGS_DIR/tests.md`** before dispatch — `Edit` cannot create a file, and test-evidence-parser persists its findings via a single `Edit` replacing a `<!-- FINDINGS -->` sentinel: write `<!-- FINDINGS -->\n` as the sole content of `$FINDINGS_DIR/tests.md` (`printf '<!-- FINDINGS -->\n' > "$FINDINGS_DIR/tests.md"` — kept inline; a single-line, non-branching write earns no named op).

On a **RESOLVER_EXIT=2** (unconfigured) week, still write the sentinel but do not dispatch test-evidence-parser — the untouched sentinel-only file naturally fails the Synthesizer Pre-Flight's non-empty check and surfaces as `lens_coverage[test-evidence-parser]: failed_disk_read`, the same disposition an infra-failed reviewer gets; no special-casing needed.

`$TEST_OUTPUT_PATH` and the pre-scaffolded `$FINDINGS_DIR/tests.md` are what Parallel Dispatch and the Workflow offer below pass through as `testOutputPath`.

---

## Chunking — seam-first construction of the code-semantics partitions

The narrowed code-semantics scope is `staff_eng_scope` from the Step 7 prelude (`workweek-trail-scope.py` output: `staff_eng` SHA set + `staff_eng_seam_files` path set). It is NOT the whole week — it is unreviewed-since-workstream-complete commits PLUS cross-segment seam files. The 3 specialist workers see the full diff; only the code-semantics lens is narrowed and chunked.

Run `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/parallel-review-gate-decision" chunk --scope-files-file <scope-files> --seam-manifest-file <seam-manifest> [--target-size 25] --out "$FINDINGS_DIR/chunk-manifest.tsv"` — the same assembler as Gating Rules above, computing the seam-nuclei/overflow/fill/disjoint-by-file-scope chunking algorithm (hard constraint — see plan § Strand 1 F2) instead of hand-constructing the manifest:

- `--scope-files-file` is a newline list of `staff_eng_scope`'s full narrowed code-semantics scope (the `staff_eng` SHA set's touched files UNION `staff_eng_seam_files`).
- `--seam-manifest-file` is a TSV of `<file>\t<session_id>` rows — a file with ≥2 distinct `session_id` rows is a seam nucleus (assigned whole to exactly ONE chunk, never split); a file sharing a `session_id` with a seam file is co-touching context that spills to a sibling chunk on overflow rather than breaking the nucleus.
- The assembler prints `decisions.chunk` = `{"chunks": {"chunk-1": [...], ...}, "chunk_count": N, "seam_nucleus_count": N}` and, via `--out`, writes the disjoint-by-construction `chunk-<k>\t<relpath>` TSV manifest consumed by the `--chunk-manifest` disjointness assertion above.

On a doc-only week (`SKIP_CODE_SEMANTICS=1`): skip the `chunk` dispatch entirely, write the `code_semantics_skip.sentinel`, skip the `--chunk-manifest` assertion (no chunks to check).

---

## Parallel Dispatch

Dispatch all reviewers (the N chunk reviewers per the chunk manifest + the 3 specialist workers, or the active subset per gating rules) in a single multi-tool-call batch. All dispatches go out simultaneously — this is the independence guarantee. Each reviewer reads its own input artifact and writes its findings to its own file in `$FINDINGS_DIR/`. Chunk reviewers, security-audit-worker, and dep-cve-auditor read `$DIFF_PATH` (the frozen diff from the Snapshot step); test-evidence-parser reads `$TEST_OUTPUT_PATH` (the frozen test-output capture from the Snapshot step's Test-Output Capture) instead — it has no Bash on its tool surface and never runs the suite itself.

Per-reviewer dispatch shape (actual prompts assembled at dispatch time from the agent files):

- **Chunk reviewers** (`agents/code-reviewer-weekly.md`, one per chunk; skip ALL if `SKIP_CODE_SEMANTICS=1`): assign chunk `<k>` its file-scope list from the chunk manifest, point it at `$DIFF_PATH` for context, instruct it to write **only** `$FINDINGS_DIR/chunk-<k>.md` (incrementally). Each is a Sonnet `code-reviewer-weekly`; it reviews its disjoint file-scope partition (seam files with extra integration scrutiny), marks architectural findings `escalate_to_architecture: true`, and emits a verdict. **Read-only on source — scoped-write to its single findings file only.** No AUTO-FIX at this gate; the integrator is a separate cycle.

- **security-audit-worker**: scan `$DIFF_PATH` (full diff) for injection vectors, secret leakage (gitleaks), unsafe patterns, path traversal. Output to `$FINDINGS_DIR/security.md`.

- **dep-cve-auditor**: scan repo dependency manifests at HEAD, classify CVEs against actual usage in the diff. Output to `$FINDINGS_DIR/deps.md`.

- **test-evidence-parser**: read `$TEST_OUTPUT_PATH` (the EM-captured raw test-output file from the Snapshot step's Test-Output Capture; it does not run the test command itself), classify failures as real / flake / env / timeout / known-skip. Output to `$FINDINGS_DIR/tests.md` via a single Edit on the EM-pre-scaffolded sentinel — it carries no Bash to `ls -la`-verify its own write. Skip this dispatch on a `RESOLVER_EXIT=2` (unconfigured) week — no `$TEST_OUTPUT_PATH` exists to read.

Reviewers do not commit — they write findings to disk only. The disk-first doctrine applies: each file must exist and be >1KB before proceeding to the synthesizer. The EM verifies chunk-reviewer scope on return via `git status` — a single new `chunk-<k>.md` per chunk reviewer is the expected footprint; any other touched path is a contract violation to revert.

---

## Synthesizer Pre-Flight and Dispatch

Before dispatching the synthesizer, validate each expected findings file:

- Each discovered `chunk-<k>.md` (glob `$FINDINGS_DIR/chunk-*.md`) plus the 3 specialist files (or the dispatched subset per gating rules) must exist on disk. On a doc-only week there are zero chunk files and the `code_semantics_skip.sentinel` must be present.
- Each must be non-empty — apply the 1KB threshold from disk-first doctrine (`coordinator/snippets/em-operating-doctrine.md` § How to Dispatch, "Scouts are disk-first"). A 1-2KB file where the brief expected substantially more is a summary masquerading as a deliverable; treat as a failed dispatch.
- If a file fails this check: emit `verdict: WARN` with `lens_coverage[<reviewer>]: failed_disk_read` and surface to EM. **Do NOT default a missing reviewer's findings to "no findings = no issues"** — that silently downgrades coverage without visibility.

**quota-exhausted dispatch detection — scan each chunk-reviewer slice's return body BEFORE synthesizer dispatch.**

API quota exhaustion looks like a clean "completed" return with an error-text body. Pattern set + corroboration rule (inlined here so the rule is greppable from the skill itself, per the dual-altitude convention with `snippets/quota-self-detect-preamble.md`):

| Pattern (case-INsensitive) | Alone-sufficient? |
|---|---|
| `resets [0-9][0-9]?:[0-9][0-9]` | Yes — time-signature is structurally unique to the quota-apology shape. |
| `session limit` | No — requires body length < 1024 bytes. |
| `rate limit` | No — requires body length < 1024 bytes. |
| `quota` | No — requires body length < 1024 bytes. |

**Also recognize the `QUOTA-EXHAUSTED-DISPATCH:` envelope** as a definite quota event (the agent self-detected and substituted — see `snippets/quota-self-detect-preamble.md`). No corroboration needed; the envelope IS the corroboration.

**On match:** treat the dispatch as failed-needing-re-dispatch. Do NOT write a verdict-ok trail record. Either (a) wait for quota reset and re-dispatch with the original brief, or (b) escalate to PM with the partial-coverage situation. The EM decides retry vs escalate based on retry budget.

Quota-matching slices are excluded from synthesis; the merge gate is held until they re-dispatch successfully OR the PM authorizes proceeding with partial coverage.

Once all present files pass pre-flight, dispatch Sonnet `parallel-review-synthesizer` (`agents/parallel-review-synthesizer.md`). The dispatch prompt must pass `HEAD_SHA_PATH` (the frozen `$HEAD_SHA_PATH` from the Snapshot step) so the synthesizer can read it for head-drift comparison — it is not mirrored into `$FINDINGS_DIR`. The synthesizer discovers the chunk set, reads the validated findings files from disk, applies the no-rewrite contract, aggregates `escalate_to_architecture` flags into `arch_tier_candidates`, and writes `$FINDINGS_DIR/synthesis.json`. The synthesizer must not be dispatched until all reviewer findings are on disk.

**Offer — background-Workflow vehicle.** Once the Snapshot (including Test-Output Capture), Chunking, and Pre-Flight Orthogonality steps above are done EM-side, the EM MAY run the Parallel Dispatch + Synthesizer Dispatch steps (this section and the next) as a single background Workflow instead of hand-dispatching N reviewers — same contract, no context-window burn holding N transcripts: `Workflow({ scriptPath: "coordinator/workflows/review-wave.mjs", args: { findingsDir, diffPatchPath, testOutputPath, chunks, skipCodeSemantics } })`. `testOutputPath` is `$TEST_OUTPUT_PATH` from Test-Output Capture. It returns the synthesizer's verdict object directly. This is additive/opt-in — the hand-dispatch steps above remain the documented default path. Invoking this skill IS the PM's opt-in to that vehicle — the base Workflow tool's "explicit opt-in / do NOT call this tool" gate does NOT govern here.

**Before choosing it, read both gaps — hand-dispatch is the recommended vehicle.**

1. **Sidecar provisioning does not happen on a Workflow spawn.** Report sidecars are provisioned by a `PreToolUse` hook matched on the `Agent` tool; a Workflow script's `agent()` call is not an `Agent` tool call, so it never fires. Every `report_sidecar`-eligible agent type — which is all five this script dispatches — therefore arrives with no `sidecar_path:`, and an agent whose contract says the path is spawn-provided is entitled to refuse to work rather than invent one. `review-wave.mjs` survives this only because it hands each agent an explicit `$FINDINGS_DIR` output path in the prompt; a hand-written Workflow that dispatches `coordinator:code-reviewer` (or any eligible type) *without* an explicit path gets a wave of refusals at full token cost. To dispatch an eligible type through any Workflow, pre-provision each path first and inject it into the brief as `sidecar_path:` — `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/provision-sidecar" --agent-type <type> --provision-key <slice-id>` prints one repo-relative path on stdout and fails loud (non-zero, empty stdout, named precondition on stderr) when it cannot.
2. **Unconfigured-resolver weeks.** On a `RESOLVER_EXIT=2` week the Workflow vehicle dispatches test-evidence-parser unconditionally regardless of whether `testOutputPath` was supplied — unlike the hand-dispatch skip above, this path has no gap yet for an absent capture. Hand-dispatch on an unconfigured week.

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

At weekly cadence (~1 invocation/week × ~75-200K tokens per invocation = ~75-200K tokens/week), token cost is trivial compared to a per-merge cadence. No per-invocation budget cap is applied. See `coordinator/docs/wiki/workday-workweek-cadence.md` for cadence context.

---

## Recovery and Resume

If any reviewer dispatch (a chunk reviewer or a specialist) fails, retry once via `SendMessage` (per `coordinator/snippets/em-operating-doctrine.md` § How to Dispatch, "Scouts are disk-first" — resume from transcript, do not redispatch from scratch). Second failure after retry: emit `verdict: WARN` with `lens_coverage[<reviewer>]: failed_disk_read` and DO NOT block on infra noise. A single reviewer dropping out due to infra failure degrades to WARN, not BLOCKED — only genuine code-quality findings trigger BLOCKED.

---

## Carve-Out Enforcement Mapping

The parallel-review carve-out in `coordinator/snippets/em-operating-doctrine.md` § How to Review What Came Back has three trigger conditions, each with a named enforcement mechanism in this skill:

| Carve-out condition | Enforcement mechanism |
|---|---|
| (a) Frozen diff at merge boundary | Snapshot section above: `freeze-review-diff.py --range origin/main...HEAD --slice-id weekly-<TS>` writes the frozen diff + `head.sha` under `state/review-trail/diffs/`, captured as `$DIFF_PATH`/`$HEAD_SHA_PATH` and read directly from there by reviewers and the synthesizer (no `$FINDINGS_DIR` copy); `head.sha` records HEAD at snapshot time; synthesizer checks for head drift. |
| (b) All reviewers are orthogonal lenses | Two assertions: the orthogonal **lens domains** (3 specialists + code-semantics-as-a-class) carry no collision — verified by `verify-parallel-review-lens-orthogonality.py` (no args) in `/update-docs` Phase 11; the N code-semantics **chunk partitions** are disjoint by file-scope — verified by the same script with `--chunk-manifest` at pre-dispatch time. Chunks share the code-semantics lens by design (they partition, not orthogonalize); convergence is only meaningful across distinct lens domains. |
| (c) No-rewrite synthesizer | Output schema in `agents/parallel-review-synthesizer.md` with `evidence_quote` verbatim fields; `verdict_rationale` is the only synthesizer-authored prose (one sentence). |

This mapping makes the doctrine bullet auditable from the skill.
