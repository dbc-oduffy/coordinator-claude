# Cleanup, Sweep, and Migration Hazards

**Provenance:** consolidated 2026-05-05 from `tasks/lesson-triage-2026-05-05/SYNTHESIS.md` §B8.

Cleanup operations — `/distill`, `/update-docs`, link-heal, scaffolding-deletion, auto-discovery glob configs — are higher-risk than they look. They run across many files at once, often without per-file judgment, and they routinely undo work nobody noticed they were doing. This guide enumerates the recurring failure modes.

## 1. Scaffolding-Deletion Needs Active-Reference Check

Before deleting a scaffolding directory under `tasks/`, grep for references to its files from any *active* canonical spec — not just its own shipped parent plan. A scratch file's parent workstream may have shipped while the same file is load-bearing for a *different*, still-active workstream.

**Concrete failure:** `/distill` deleted `tasks/scratch/2026-04-30-shakedown2-verification.md` because it lived in a "scratch" dir whose dominant content was post-ship review residue. But the still-active `2026-04-30-shakedown-2-response.md` plan referenced it verbatim as canonical evidence for the WS-G workstream verifier. Recovery via `git show <sha>^:<path>` worked, but only because Phase E's link-heal sweep happened to catch the dangling reference.

**Defense:** before any `rm -rf tasks/<dir>/`, run

```bash
grep -rE "tasks/<dir>/" docs/plans/ tasks/<other-dirs>/ CLAUDE.md MEMORY.md
```

and flag any hits in active (non-archived) docs. Only proceed if every hit is in archived/historical content.

## 2. Sed-Based Link-Heal Over-Rewrites Provenance Frontmatter

When sweeping `s|docs/plans/X.md|archive/specs/X.md|g` across a repo, the regex hits both intended Spec backlinks AND provenance frontmatter fields like `original_path: docs/plans/X.md` — where the original location is the *literal* point of the field.

**Concrete failure:** the distill Phase E sed pass rewrote 98 files correctly for `Spec backlink:` comments, but corrupted `original_path:` provenance frontmatter on 9 wiki entries from `docs/plans/` to `archive/specs/` — making the provenance frontmatter self-referential and lying about where the spec originally lived.

**Defense:** anchor the regex to exclude provenance fields:

```bash
sed -E '/^(original_path|originally|pre-archive):/!s|docs/plans/X.md|archive/specs/X.md|g'
```

OR do a post-sweep audit: grep for the *new* path in fields where the *old* path is semantically correct, restore those before committing.

## 3. Stale Doc References — Repoint Before You Create

When a doc-link-checker surfaces N references to M missing pages, **don't** default to "create M pages." For each missing page, ask: does the referenced content actually need its own surface, or is it already covered by existing pages + a canonical section in CLAUDE.md? Repoint when covered; create only when genuinely missing.

**Concrete failure averted:** the bug-backlog had 8 references to 2 missing wiki pages. The naive fix is "create both." But one page's claimed scope was already 100% covered by existing wiki pages + CLAUDE.md — a new page would have duplicated and drifted. The other page's scope was genuinely unmet. The hybrid fix (create one, repoint the other) was right.

**Defense:** before creating a new doc-surface to satisfy stale references, grep the references' descriptors against existing wiki + CLAUDE.md. If existing surfaces already carry that content, repoint instead of creating.

## 4. Auto-Discovery Globs Sweep In Stale Backups

`structural.py:_discover_overlays()` did `glob('structural_*.sqlite3')` after the env-var check; a 12-day-old `structural_index.v3_backup_*.sqlite3` in the canonical directory got auto-attached as `overlay_0`, and the cross-schema dedup query then failed on a missing-column. Cost: 5-min fix once correctly diagnosed vs. a 2-7h env-var hunt against the wrong cause.

**Defense:** any "or auto-discover" config branch needs either:

1. An explicit glob pattern that excludes obvious backup naming: `*backup*`, `*.bak*`, `*-bak*`, `*.partial`.
2. **Or** explicit registration only — no fall-through glob.

Stale backups are the silent footgun in any "env var → fallback to glob" config layer.

## 5. Defend Structural Invariants With Snapshot Tests, Not Commit-Message Discipline

A commit titled `path-sweep + grep gate + allowlist` silently reverted a prior single-source-of-truth refactor by re-adding 7 trimmed lines to a `Build.cs` file. No future reviewer will catch this from commit messages — the title sounds like it's *enforcing* the invariant, not violating it.

**Defense:** for any structural invariant that load-bearing tests/specs depend on, encode it as a snapshot test (allowlist of permitted lines under version control), not as a norm about commit hygiene. The snapshot blocks scope-expanded commits at CI; norms don't.

## 6. Hardcoded Developer-Machine Paths Hurt Every External Consumer

A SessionStart hook had a hardcoded fallback `$KnownRoots = @("X:\<project-1>", "E:\dev\ue\Keep_Blank")` for graph.db location when env vars were unset. Worked silently on the author's machine. Would have emitted nothing useful (or worse, misleading freshness reports about the wrong codebase) on every external consumer with a different drive layout.

**Defense pattern** for any path-resolution fallback in shipped tooling:

1. Explicit env var override.
2. Marker-convention discovery walking up from cwd (e.g., `Saved/ProjectRag/graph.db`).
3. Silent skip — **never** a hardcoded path.

Add a cwd-scope guard so the tool refuses to act when the resolved root doesn't contain cwd (prevents acting on the wrong project even when discovery succeeds). Same trap exists for any reflexive "preamble" injected into agent prompts that depends on user-scoped configuration but should be project-scoped.

## 7. Edit-Tool Success Is Not Landing Proof

Edit-tool success return value is NOT proof the change landed — concurrent writers, atomic-write crashes, and `.tmp.<pid>` orphans can leave the target file unchanged despite a success message. On hot files (load-bearing scripts, CLAUDE.md, frequently-edited skills), follow every Edit with `git diff --stat <path>` to confirm.

## 8. Bulk Substitution Self-Corruption

Any bulk find/replace tool that defines its own substitution vocabulary in-file (or in a sibling script) will rewrite *itself* unless its scan path explicitly excludes those vocabulary-carrying files. The tool's identifier strings, replacement templates, and pattern tables become substitution targets — the first run corrupts the table, the second run runs against the corrupted table, and recovery requires `git checkout` against the tool source.

**Concrete failure:** 2026-05-09 publish-sanitization dogfood ran `depersonalize-for-publish.sh --fix` over `/x/coordinator-claude`. The publish-repo's `check-persona-names.py` mirrors the same `PERSONA_NAMES` vocabulary; the bulk-fix rewrote the literal table entries inside that checker, breaking persona detection on the publish side. Recovery via `git checkout` was clean, but the failure mode is silent — exit code 0, files rewritten, only a content audit catches it.

**Defense:** every bulk-substitution tool carries an `EXCLUDED_BASENAMES` (or equivalent) guard listing its own filename AND any sibling file that mirrors its vocabulary. See `bin/depersonalize-for-publish.sh` `EXCLUDED_BASENAMES` + basename-pattern guards for the canonical shape. The guard runs ahead of subtree-prefix exclusion (a file under `bin/` shouldn't be skipped wholesale, only the vocabulary-bearing ones).

## 9. Narrow Dependent Surfaces When User-Facing Surface Narrows

When the user-facing surface narrows (deprecated option removed, verb dropped, flag retired), narrow dependent test fixtures and doc examples in the SAME workstream — leaving stale surface references in tests/docs is doctrine-rot that future sessions trip on. The next executor reads the doc example, copies the deprecated form into new code, and the cycle restarts. Surface-narrowing is a multi-file operation: producer + every test asserting it + every doc demonstrating it.

## 10. Cross-Repo Deletion Needs Consumer Audit (Two-Phase, Not One-Shot)

Deleting a module/file/symbol that lives in one repo while consumers live in *another* repo is not a one-shot operation. The producer-side delete completes cleanly in isolation; the consumer side fails at next import/build with no signal travelling back across the repo boundary. Split into **PHASE-1: copy or stub the new location and rewire consumers** → **PHASE-2: delete the old location** with a verifiable gap between phases (consumers green on the new wire-up before producer-side removal).

**Concrete failure pattern (recurring across project-rag ↔ ue-addon ↔ holodeck splits):** excision lands in repo A; sibling repos B and C still `import` / `#include` / cite the moved-or-deleted path. Discovery comes from runtime failure days later, not from the delete commit.

**Defense:**

1. Before the delete dispatch, grep consumer repos for the symbol/path. Don't trust "we already migrated callers" claims from the producer-repo session — verify against every named consumer's `HEAD`.
2. Author a cross-repo coordination memo or spinoff handoff naming each consumer repo and the rewire commit that must land first.
3. Phase the work explicitly in the plan: P1 = copy/duplicate to new location + rewire consumers (reversible); P2 = remove old location (irreversible). Never one-shot.
4. After PHASE-2, run a consumer-side smoke or import test to prove the gap closed.

## 11. Excision Missed the Consumer Rewrite — Grep Imports Before Celebrating

A successful excision in the producer repo is not "done" until the consumer-side rewrite has landed AND been exercised. "Removed X, all tests green here" is a partial signal — the green tests are the producer's, and the consumer's import is what breaks. Grep every importer/citer before declaring the excision complete. This is the same hazard family as §10 but applies even within a single repo when consumer surfaces live far from the producer (test fixtures, doc examples, agent prompts, snippets).

**Defense:** the excision plan's done-criteria must include "grep `<deleted-symbol>` returns zero hits across repo + sibling repos, AND every consumer that referenced it has a follow-up commit rewiring it." Symbol-only grep is not enough — also grep prose mentions, doc examples, and agent-prompt embeddings.

## 12. Purge-Cache + First Untested Run Is a Net Regression

`--purge` / `--clean` / `--reset` flags that wipe downstream artifacts BEFORE the producer chain runs are dangerous on first untested runs: if the producer pipeline fails for any reason, nothing rebuilds, and the consumer state ends up *empty* — strictly worse than the pre-purge state. The flag's value (force a clean rebuild) is conditional on the rebuild succeeding; pair them and the failure mode is silent regression.

**Concrete failure (dronesim):** combined purge-cache with a first untested pipeline run; pipeline failed mid-way; consumer cache was empty afterward, breaking a downstream system that had been working off the prior cache.

**Defense:**

1. Run the non-purge variant first to confirm the rebuild path works end-to-end on the current code.
2. Only then run the purge variant.
3. If a script offers a "purge-and-rebuild" combined flag, treat that flag as a two-step sequence (non-destructive rebuild → destructive purge → idempotent rebuild) in your head; don't trust the script to have ordered it safely.

## 13. Renumber/Rename Requires Multi-Pattern Reverse-Reference Scan

When renumbering a published API (or renaming an exported symbol), references live across at least three surface shapes that a single grep pattern won't cover:

1. **User-facing surface:** call sites — easy to grep, easy to remember.
2. **Internal cross-references:** `# See §4`, `as shown in step 7`, parity comments, doc anchors — prose-embedded, not symbol-shaped.
3. **Symbol-level references:** test names, agent-prompt embeddings, snippet sentinels, manifest entries that lift the number into structured frontmatter.

Each shape needs its own grep pattern. A single regex on the literal symbol misses prose-embedded references (#2) and structured-field references (#3) — those decay silently and surface weeks later as broken anchors or stale doctrine quotes.

**Defense:** before the renumber/rename, enumerate the three pattern shapes and run a grep per shape. Treat parity comments as a non-grep-targeted second surface — they will need a wider-net pattern (e.g., the description, not just the symbol).

## 14. Audit Duplication by Reading Bodies, Not Metadata

Metadata-level surveys (title, frontmatter `topic`, scope tag) are a *triage signal*, not a verdict. Two artifacts with matching metadata routinely diverge in content; one carries edge cases or empirical battle-stories the other doesn't. The half-the-list reversal — where the "duplicate" turns out to carry distinct content under the same title — is the empirical norm on these audits.

**Defense:** every dedup or migration candidate gets a body-read before action. Frontmatter is the index; the body is the record. If the body-read shows divergence, the right action is **merge**, not delete-one.

## 15. Path Extraction by Table-Column, Not Regex Over Rationale Text

When a scout produces a recommendation table — `| path | reason | action |` — and a downstream sweep needs to act on the `path` column, extract by column index, not by regex-over-the-rendered-table-text. A loose regex (e.g., `tasks/[a-z-]+/`) will sweep paths the scout *referenced* in the `reason` cell (cited as evidence, not as deletion targets) into the deletion list.

**Defense:**

1. Parse table columns by markdown column index or convert to JSON/YAML before consumption — never regex-extract from the rendered prose.
2. Fail closed: the deletion sweep refuses to act on any path not in a fully-parsed `path` column.
3. Wiki-guide protection: any deletion sweep that reads from a scout report MUST hard-exclude `docs/wiki/`, `CLAUDE.md`, `archive/`, and `tasks/lessons.md` regardless of column origin — these are never legitimate sweep targets and the protection is cheap insurance against parser bugs.

## 16. Auto-Discovery Globs Sweep In Stale Backups (Reprise + Hardening)

§4 covers the SQLite overlay case. The pattern generalises: any "env var unset → fallback to glob" config layer is vulnerable to backup files matching the discovery pattern. Backup-name exclusion is cheap doctrine-bait — add `*backup*`, `*.bak*`, `*-bak*`, `*.partial`, `*.tmp.*`, `*~` to every fallback glob, or require explicit registration with no glob fallback at all.

Also flag during code review: any `glob(...)` call inside a config-discovery code path needs a backup-exclusion comment justifying its absence if missing.

## 17. Inventory All Path-Typed Columns Before Path Normalization

When normalizing one path-typed column in a schema (e.g., absolute → relative, forward-slash → POSIX), inventory **every** path-typed column across **every** table before declaring done. Schemas accrete path columns over time — `source_path`, `dest_path`, `parent_dir`, `original_path` in provenance, `cwd` in audit logs, embedded paths in JSON-blob columns. A one-column normalization that misses sibling columns leaves the schema half-normalized and downstream consumers querying the wrong column get garbage.

**Defense:** before the normalization migration, run a schema-introspection query enumerating every column whose `name` or `type` suggests a path (or whose sample values match path shapes). Migrate or document each. Same rule for JSON-blob columns: probe nested keys for path-shaped values.

## 18. Enumerate Orthogonal Surfaces Before Retargeting Refactor

A retargeting refactor (rename a tool, change a transport, migrate a namespace) often touches two *orthogonal* surfaces — and a grep on one will not catch the other. Tool-name namespace and HTTP transport, for example, are orthogonal: changing the tool name doesn't migrate the transport endpoint, and vice versa. Each lives in different code, different config, different docs.

**Defense:** at plan-write time, enumerate orthogonal surfaces explicitly: tool name, transport/endpoint, config key, agent-prompt mention, doc reference, test fixture. Grep each independently. Treat single-surface-only retargeting plans as a plan smell — ask which orthogonal surface was skipped.

## 19. Bug-Backlog Decays Silently — Sweep Refactors Should Co-Edit It

Refactors that fix or close a bug-backlog entry by side effect (without naming it in the commit subject) leave the entry sitting in the backlog as a phantom — future bug-blitz sweeps re-investigate it, find no symptom, and waste a session on "verify still applies."

**Defense:**

1. Any sweep refactor or cleanup pass should grep `tasks/bug-backlog.md` (and project-equivalents) for paths/symbols it touches, and close matching entries in the same commit.
2. Consumer-side: bug-blitz's pickup phase must verify each entry against current `HEAD` (not against the entry's authoring date) before dispatching a fix — entries that no longer reproduce get deleted, not "investigated."
3. The commit subject names the closed backlog entry; `git log -- tasks/bug-backlog.md` becomes the audit trail.

## 20. Doctrine Flips: Audit Test Infra AND Write-Sites

When a doctrine flips a *value-class* (preferred Python interpreter, default branch shape, canonical commit helper, env-var polarity), the sweep is two-sided and both sides bite:

1. **Test infra and guards encode the OLD rationale.** Pre-flip assertion shapes (`_check_venv refused presence of a venv`, "no-venv-policy" warnings, fixtures that assert against the rejected state) survive the flip with their *inverted* rationale intact. They keep enforcing the old rule against a codebase now meant to violate it. Grep every assertion site mentioning the flipped value-class before declaring the flip done.

2. **Write-sites that consumed the flipped value as-is silently regress on a secondary property.** Code that happily took `python.exe` instead of system Python (the headline flip) may suddenly produce different *subsystem* (console vs GUI), different `sys.executable`, different bundled-package surface, different launch flags — properties the original write-site never asserted on because it didn't matter under the old polarity. The flip is correct in the headline dimension and wrong in an orthogonal one.

**Concrete failure:** 2026-05-14 project-rag venv-primary doctrine flip — the producer side moved from system Python to venv `python.exe`. The headline switch landed cleanly, but downstream a Windows hook was launching `python.exe` (console subsystem) where it had been launching `pythonw.exe`-equivalent system Python (GUI-by-shim) — flashing a console window on every fire. The test infra side simultaneously kept an `_check_venv refused presence of a venv` guard that now fired on every legitimate run.

**Defense:** the doctrine-flip plan enumerates (a) every guard/test that mentions the value-class — sweep for inversion; (b) every write-site that consumes the value — sweep for orthogonal-property regression. Both go in the plan body before dispatch, both are verified post-flip, neither is "we'll catch it in CI" territory.

## Skill Checklist Reference

`/distill` and `/update-docs` should reference items 1, 2, and 3 in their dispatch prompts so the agent enforces these checks during sweep operations, not just the EM after the fact. `/bug-blitz` consumers reference item 19 for backlog-currency verification. `/coordinator:plan` Branch B references item 20 when the plan body flips a doctrine value-class.
