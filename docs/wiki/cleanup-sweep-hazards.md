# Cleanup, Sweep, and Migration Hazards

**Provenance:** consolidated from `tasks/lesson-triage-2026-05-05/SYNTHESIS.md` §B8.

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

A SessionStart hook had a hardcoded fallback `$KnownRoots = @("X:\<project-1>", "E:\dev\ue\Keep_Blank")` for graph.db location when env vars were unset. Worked silently on the author's machine. Would have emitted nothing useful (or worse, misleading freshness reports about the wrong codebase) on every external consumer with a different drive layout. <!-- foreign-path-ok: the hardcoded path IS the anti-pattern being critiqued -->

**Defense pattern** for any path-resolution fallback in shipped tooling:

1. Explicit env var override.
2. Marker-convention discovery walking up from cwd (e.g., `Saved/ProjectRag/graph.db`).
3. Silent skip — **never** a hardcoded path.

Add a cwd-scope guard so the tool refuses to act when the resolved root doesn't contain cwd (prevents acting on the wrong project even when discovery succeeds). Same trap exists for any reflexive "preamble" injected into agent prompts that depends on user-scoped configuration but should be project-scoped.

## 7. Edit-Tool Success Is Not Landing Proof

Edit-tool success return value is NOT proof the change landed — concurrent writers, atomic-write crashes, and `.tmp.<pid>` orphans can leave the target file unchanged despite a success message. On hot files (load-bearing scripts, CLAUDE.md, frequently-edited skills), follow every Edit with `git diff --stat <path>` to confirm.

## 8. Bulk Substitution Self-Corruption

Any bulk find/replace tool that defines its own substitution vocabulary in-file (or in a sibling script) will rewrite *itself* unless its scan path explicitly excludes those vocabulary-carrying files. The tool's identifier strings, replacement templates, and pattern tables become substitution targets — the first run corrupts the table, the second run runs against the corrupted table, and recovery requires `git checkout` against the tool source.

**Concrete failure:** 2026-05-09 publish-sanitization dogfood ran `publish-time-transform-py --fix` (claude-klabauter `coordinator/bin/publish-time-transform-py`) over `/x/coordinator-claude`. The publish-repo's `check-persona-names.py` mirrors the same `PERSONA_NAMES` vocabulary; the bulk-fix rewrote the literal table entries inside that checker, breaking persona detection on the publish side. Recovery via `git checkout` was clean, but the failure mode is silent — exit code 0, files rewritten, only a content audit catches it.

**Defense:** every bulk-substitution tool carries an `EXCLUDED_BASENAMES` (or equivalent) guard listing its own filename AND any sibling file that mirrors its vocabulary. See claude-klabauter `coordinator/bin/publish-time-transform-py` `EXCLUDED_BASENAMES` + basename-pattern guards for the canonical shape. The guard runs ahead of subtree-prefix exclusion (a file under `bin/` shouldn't be skipped wholesale, only the vocabulary-bearing ones).

## 9. Narrow Dependent Surfaces When User-Facing Surface Narrows

When the user-facing surface narrows (deprecated option removed, verb dropped, flag retired), narrow dependent test fixtures and doc examples in the SAME workstream — leaving stale surface references in tests/docs is doctrine-rot that future sessions trip on. The next executor reads the doc example, copies the deprecated form into new code, and the cycle restarts. Surface-narrowing is a multi-file operation: producer + every test asserting it + every doc demonstrating it.

## 10. Cross-Repo Deletion Needs Consumer Audit (Two-Phase, Not One-Shot)

Deleting a module/file/symbol that lives in one repo while consumers live in *another* repo is not a one-shot operation. The producer-side delete completes cleanly in isolation; the consumer side fails at next import/build with no signal travelling back across the repo boundary. Split into **PHASE-1: copy or stub the new location and rewire consumers** → **PHASE-2: delete the old location** with a verifiable gap between phases (consumers green on the new wire-up before producer-side removal).

**Concrete failure pattern (recurring across project-rag ↔ ue-addon ↔ example-game-repo splits):** excision lands in repo A; sibling repos B and C still `import` / `#include` / cite the moved-or-deleted path. Discovery comes from runtime failure days later, not from the delete commit.

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

**Concrete failure (example-sim-repo):** combined purge-cache with a first untested pipeline run; pipeline failed mid-way; consumer cache was empty afterward, breaking a downstream system that had been working off the prior cache.

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
3. Wiki-guide protection: any deletion sweep that reads from a scout report MUST hard-exclude `docs/wiki/`, `CLAUDE.md`, `archive/`, and `state/lessons/` regardless of column origin — these are never legitimate sweep targets and the protection is cheap insurance against parser bugs.

**Scout delete-candidate lists need EM-side grep before `rm` fires (L754, example-game-workbench-repo).** A scout's delete-candidate list is a *recommendation*, not an authorization. Before the `rm` executes, the EM must grep each candidate for live consumer surfaces (imports, `#include`, doc citations, agent-prompt embeddings) across the repo and named siblings — the scout's "unused" verdict is scoped to what it grepped, and it routinely misses cross-file or cross-repo consumers. This is the same hazard family as §11 (grep imports before celebrating an excision); applied to scout-driven sweeps, the grep is the EM's gate, not the scout's.

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

1. Any sweep refactor or cleanup pass should grep `state/bug-backlog/` (and project-equivalents) for paths/symbols it touches, and close matching entries in the same commit.
2. Consumer-side: bug-blitz's pickup phase must verify each entry against current `HEAD` (not against the entry's authoring date) before dispatching a fix — entries that fail to reproduce get deleted, not "investigated."
3. The commit subject names the closed backlog entry; `git log -- state/bug-backlog.md` becomes the audit trail.

## 20. Doctrine Flips: Audit Test Infra AND Write-Sites

When a doctrine flips a *value-class* (preferred Python interpreter, default branch shape, canonical commit helper, env-var polarity), the sweep is two-sided and both sides bite:

1. **Test infra and guards encode the OLD rationale.** Pre-flip assertion shapes (`_check_venv refused presence of a venv`, "no-venv-policy" warnings, fixtures that assert against the rejected state) survive the flip with their *inverted* rationale intact. They keep enforcing the old rule against a codebase now meant to violate it. Grep every assertion site mentioning the flipped value-class before declaring the flip done.

2. **Write-sites that consumed the flipped value as-is silently regress on a secondary property.** Code that happily took `python.exe` instead of system Python (the headline flip) may suddenly produce different *subsystem* (console vs GUI), different `sys.executable`, different bundled-package surface, different launch flags — properties the original write-site never asserted on because it didn't matter under the old polarity. The flip is correct in the headline dimension and wrong in an orthogonal one.

**Concrete failure:** project-rag venv-primary doctrine flip — the producer side moved from system Python to venv `python.exe`. The headline switch landed cleanly, but downstream a Windows hook was launching `python.exe` (console subsystem) where it had been launching `pythonw.exe`-equivalent system Python (GUI-by-shim) — flashing a console window on every fire. The test infra side simultaneously kept an `_check_venv refused presence of a venv` guard that now fired on every legitimate run.

**Defense:** the doctrine-flip plan enumerates (a) every guard/test that mentions the value-class — sweep for inversion; (b) every write-site that consumes the value — sweep for orthogonal-property regression. Both go in the plan body before dispatch, both are verified post-flip, neither is "we'll catch it in CI" territory.

## 21. Producer-Rename Sweep: Test Files Split Into Three Buckets

When renaming a producer symbol (function, class, module), the test-file sweep splits into **three distinct buckets**, not one — and bucket 2 is the silent-failure trap.

1. **Consumer-shape tests** — tests that call the renamed symbol directly. `from <module> import <old_name>` becomes `from <module> import <new_name>`. Greppable, mechanical, low risk; rename or fail loudly at import time.
2. **Patch-target-shape tests** — tests that `@patch('<module>.<old_name>')` or `monkeypatch.setattr('<module>.<old_name>', ...)`. **These fail SILENTLY.** The patch target is a string; the stale string resolves to nothing; the patch decorator no-ops; the test runs against the *real* (renamed) symbol while *believing* it's running against a mock. Often passes for the wrong reason and ratifies the rename as green.
3. **Fixture-shape tests** — tests that build fixture data (dataclass instances, dict literals, mock objects) shaped against the old name's surface. These usually fail loudly when the renamed surface changes shape — but if the rename is name-only and the shape is unchanged, fixtures still resolve and the test passes against stale assumptions.

**Rule:** producer-rename sweeps must grep for all three patterns independently:

```bash
# Bucket 1: consumer
rg -n '\bold_name\b' tests/

# Bucket 2: patch target — string-typed, escapes the AST grep
rg -n "['\"](<module>\.)?old_name['\"]" tests/
rg -n "patch\(['\"].*old_name['\"]" tests/
rg -n "monkeypatch\.setattr\(['\"].*old_name" tests/

# Bucket 3: fixture references (case-by-case; usually class/dataclass names)
rg -n 'OldClassName\(' tests/
```

Bucket 2 is the one that ages out of doctrine. Bucket 1 is muscle memory; bucket 3 fails at the next assertion. Bucket 2 is the silent residue.

Composes with §11 (consumer rewrite — grep imports before celebrating) and §13 (renumber/rename requires multi-pattern reverse-reference scan) — all three are the same family: a rename's blast radius lives in surfaces a literal-name grep misses.

*Provenance: project-rag.* Auditing a producer-rename sweep confirmed that patch-decorator string references (bucket 2) were systematically missed — tests passed as import but asserted nothing. Audit each test file against all three buckets independently before declaring the rename complete.

## 22. Distill Scaffolding-Deletion: Shipped-Status Check Is Not Enough [recurring: 1]

*project-rag.* A tasks directory whose dominant workstream has shipped may still be load-bearing for a separate active workstream. Shipped-status alone does not clear the directory for deletion. Grep for active references before any `rm -rf tasks/<dir>/` — same as §1, but the recurrence signals this check is being skipped in practice.

**Rule:** shipped-status + zero active-reference grep hits = safe to delete. Shipped-status alone = not safe.

## 23. Convention-Paired Scripts Are Unenforced Contracts

*self.* A convention documented in a wiki + a script that "should run alongside it" is not the same as the convention being enforced. If the script is opt-in (manually invoked, named in a procedure step a successor must read), the convention decays the first session the successor forgets the step. Pair the convention with one of: a hook that auto-runs the script at the right tool boundary, a CI/pre-commit gate that fails-loud on the unmet convention, or an audit step in the ceremony skill that owns the surface (`/update-docs`, `/workday-complete`).

**Rule:** when documenting a convention that has a script-shaped enforcer, name the auto-run mechanism in the same edit. If no such mechanism exists, file the gap as an improvement-queue entry rather than declaring the convention shipped.

## 24. Sequential Same-Path Bugs Signal a Pair-Shaped-Refactor Completion Gap

*example-game-workbench-repo.* When a smoke surfaces several sequential bugs along the same code path, suspect ONE refactor's incomplete propagation rather than N independent bugs. Refactors often touch one half of a pair — `.sh`/`.ps1`, producer/consumer, frontend/backend, schema/reader — and the other half slips. A five-bug cascade unblocked one-at-a-time turned out to be two completion gaps: three bugs from a `.ps1` refactor that never propagated to the `.sh` counterpart, plus three from a corpus-layout rollout left behind in downstream readers.

**Rule:** when fixing the first sibling-drift bug, immediately grep the parent refactor's git log + spec backlinks for what else should have moved together; diff the paired surfaces (`.sh` vs `.ps1`, producer vs consumer) for the same file-pair. Treat the cascade as a single workstream's completion-gap, not as independent bugs — fixing them one-by-one as they surface wastes the cascade's shared root.

## 25. Rename Audits Must Drive Entrypoints, Not Just Pattern-Match Strings

*project-rag.* When auditing a rename for completeness, a string-pattern grep of the OLD name can miss usages hidden inside dynamic-loader calls — e.g. `os.path.join(_plugin_root, "scripts")` passed to `spec_from_file_location`. The old directory name lives inside a variable or join expression, not as a bare literal, so the grep fires clean while the loader still resolves the OLD path at runtime. Two compound rules apply:

1. **Grep dynamic-loader call sites** (`importlib.util.spec_from_file_location`, `importlib.import_module`, `__import__`, `exec(open(...))`, Node `require()`, etc.) separately from bare string-literal greps. These call sites accept constructed paths that don't contain the old name as a literal.
2. **Drive the entrypoint, not the module.** A unit test that imports the module directly cannot catch an incorrect path in the loader call. The test must call the CLI / entrypoint / plugin-load surface so the loader actually runs. If the loader resolves a wrong path, a module-direct test will still green because it bypasses the loader entirely.

(Source: project-rag)

**Worked example — a doctrinally-complete rename audit still shipped a broken loader call (L130, project-rag).** A dir-rename audit can satisfy every grep-the-imports checklist item and still ship a broken `spec_from_file_location` call-site, because no test exercised the console-script entrypoint — `cli.py:2517` shipped broken to **v0.7.0**. Module-direct tests are *zero* coverage of the loader path. The audit being "complete" is not the bar; an entrypoint test that drives the console-script loader is. This converges with the addon-side dir-rename lesson (L129) — same rule, two repos, one shipped-broken-to-release data point.

## 26. Impact-Radius Scouts Must Enumerate WRITE-Direction Patterns

*project-rag-ue-addon.* An impact-radius scout grepping for usages of a symbol, env var, or path typically finds READ-direction patterns (`import X`, `$X`, `os.environ["X"]`) but silently misses WRITE-direction patterns: `export X=`, `env[X] = ...`, subprocess env injection (`{"X": ...}`), or config-file writes that set X. A rename or deletion that only audits read-direction leaves a writer that now sets the wrong name, producing a value nobody reads. Defense: for any scan that declares "all usages found," explicitly enumerate write-direction patterns as a second grep pass and include their count in the finding. (Source: project-rag-ue-addon)

## 27. Bug-Class Sweeps Close the Whole CLASS, Not the Construct That Surfaced

A bug almost never affects only the one construct that happened to surface. A portability gap, an embedding gotcha, an unsafe-spawn pattern — each is a *class* with multiple member constructs, and a fix scoped to the single surfaced member is whack-a-mole. The next member regresses the moment a sweep touches it.

**Concrete failure (PS5.1↔PS7 portability, project-rag):** Bug 2 fixed PS5.1 3-arg `Join-Path` across `*.ps1` with a static-lint guard. Days later Chunk B surfaced a PS5.1 parse error from `?.Source` (null-conditional — a *different* PS7-only construct the guard never covered), which a sweep then found in two more scripts (`??`, ternary too). The PS5.1-vs-PS7 incompatibility is one class: `{ 3-arg Join-Path, ?., ?[, ??, ??=, ternary }`. A guard scoped to one member is theater.

Scope: the PS5.1↔PS7 class is project-rag's. Coordinator targets pwsh 7 only, so these constructs need no guard in coordinator-authored `.ps1` — what carries over is the class-enumeration rule below, not this instance.

**Rule:** when fixing a portability / version-gap / pattern bug (PS5.1↔PS7, Python 3.x version drift, C++ standard drift, unsafe-spawn, console-subsystem), **enumerate the construct class** and sweep all of it in one pass; write the guard test against the *class enum*, not the surfaced member (`test_no_ps7_only_operators.py` covering the whole operator set, beside `test_no_three_arg_join_path.py`). The class-wide sweep is cheap relative to N repeat incidents.

Composes with §13/§21 (rename blast-radius across surface shapes) — same family: the fix's scope is the *class of locations/constructs*, not the one instance you can see.

## 28. Enumerated-Site-List Lint Gives False Confidence — Prefer Class-Catching Structural/AST Lint

A regression test that enumerates a fixed list of known bug sites passes green forever while *new* files introducing the same bug class regress silently. The list-based test can only prove that the listed files still reference the helper; it is structurally blind to a brand-new file that reintroduces the bug.

**Concrete failure (console-popup suppression, project-rag):** the F-21 suppression test enumerated a fixed list of "production hot-path" spawn sites. Popups returned anyway — new spawn sites (`paths.py`, `core/probes.py`, doctor probes, dogfood runner) were added to the codebase but never to the list. The test stayed green throughout.

**Rule:** when guarding a bug *class* (not a single site), write a lint that **walks all production source and pattern-matches the bug signature**, with an explicit, documented allowlist for true exceptions. Catch the *literal*, not just the call site, so assigned-then-spawned forms are covered too — e.g. for unsafe-spawn, flag any `list`/`tuple` literal whose first element is `sys.executable` (must be `pythonw_executable()`), which catches `cmd = [...]; run(cmd)` as well as inline `run([sys.executable, ...])`. An AST visitor is the strongest form; a structural `grep` over all source with an allowlist is the cheap form. Either beats an enumerated site list.

Pairs with `pre-dispatch-verification-extras.md` ("if a coverage test exists that enumerates affected sites, run it FIRST as the audit table") — that rule consumes such a class-catching lint; this rule says to *build* one rather than a hand-maintained list.

## 29. Heredoc-Python Embedding Has TWO Independent Silent-Fail Classes — Guard Both Together

Shell that embeds Python via heredoc has two orthogonal silent-fail modes, and a sweep that checks one misses the other:

1. **Shell-as-program body** — `python -c "..."` (a shell command) wrapped as the *body* of `python - <<'PYEOF'` (which expects Python program text). The outer Python parses the shell as program → `SyntaxError` every run.
2. **Bare-name-in-quoted-heredoc** — a bash variable (`PLUGIN_ROOT`) used as a bare Python identifier inside a single-quoted `<<'PYEOF'` heredoc. Bash never expands inside a quoted heredoc → Python `NameError`.

**Concrete failure (project-rag, weekly gate):** six doctor probes were inert at runtime — three in class (a), three in class (b). Both were masked by `# noqa` and probe wrappers that exit 0 in the non-fix path, so a 91-file `CLAUDE_PLUGIN_ROOT` sweep landed clean and the probes silently did nothing for ~2 weeks.

**Rule:** when reviewing or sweeping shell-embedded Python, check BOTH: (a) the heredoc *body* is Python program text, not a shell command; (b) bash variables inside are either an unquoted heredoc or explicitly passed via env — `<<'PYEOF'` (quoted) + a bare uppercase identifier is *always* a bug. Greppable class-wide guard:

```bash
# Class (a): shell command wrapped as heredoc Python body
grep -nE "python -.{0,5}<<'[A-Z_]+'" plugin/**/*.sh
# Class (b): bare uppercase identifiers in a quoted heredoc body
#   (scan body for uppercase names that aren't os/sys/pathlib)
```

The quote-state of the heredoc tag and the contents of the heredoc body are independent failure modes — one guard per class, run together.

## 30. .gitignore Patterns Encode a Naming SHAPE — Shape Drift Silently Un-Ignores

A build-artifact `.gitignore` pattern encodes a directory *naming shape*. When that shape drifts — a rename, a new suffix, a per-band split — the pattern silently stops matching and previously-ignored artifacts (often multi-GB) become committable. The un-ignore is invisible until a `--blanket` commit stages them and (if you're lucky) an oversize-blob guard catches it at push.

**Concrete failure (project-rag-ue-addon):** the per-band split renamed `…engine-vector-store/` → `…engine-vector-store-<band>/`, but `.gitignore` matched only the bare form. 5.5 GB of chroma blobs went untracked-and-not-ignored; a Phase-0 `coordinator-safe-commit --blanket` staged them, and only the oversize-blob pre-commit guard stopped the push.

**Rule:** build-workspace ignore rules need a **suffix-general glob** (`…-vector-store-*/`, not `…-vector-store/`) AND a `git check-ignore`-based regression test that **includes a deliberately-unknown future suffix** — so a future rename fails *red at test time* rather than silently at push time. The oversize-blob guard is the backstop; the `.gitignore` is the intended line and must be tested like one. Canonical shape: `tests/test_gitignore_workspace_coverage.py`.

This is the §27 bug-class principle applied to ignore rules: the *class* is "every name the artifact dir might ever take," and the guard is a glob over the class plus a test that probes an unseen member.

## 31. Stub-Dedup Canonical Is Git Commit Provenance, Not Filename Timestamp

*Source: L366, project-rag-ue-addon.*

When deduplicating stub/draft files, the canonical version is decided by **git commit provenance** (which one carries the authoritative history), not by filename timestamp or mtime — the newer-named file is frequently a divergent draft, not the successor. And the loser is not always pure waste: it can carry draft-only content the canonical never absorbed.

**Rule.** Decide canonical by `git log --follow` provenance, then archive divergent duplicates with `git mv` to `archive/` (a suffix-preserving move) rather than `git rm` — the move preserves draft-only content for later salvage, where `rm` discards it. Composes with §14 (audit duplication by reading bodies, not metadata): the body-read tells you *whether* they diverge; the git-provenance read tells you *which* is canonical.

## 32. Verbatim Code-Extraction / Dedup Must Stay Behavior-Preserving — Pre-Existing Bugs Go to Backlog, Not the Same Commit

*Source: L421, project-rag-ue-addon.*

A code-extraction or dedup refactor (lift a function to a shared helper, collapse two near-identical blocks into one) must move the code **verbatim** — behavior-preserving, byte-for-byte where possible. If the moved code contains a pre-existing bug, the temptation is to "fix it while I'm here." Don't: fixing it in the same commit conflates a behavior-changing edit with a structural move, so a bisect or revert can't separate them and the reviewer can't verify the move was clean.

**Rule.** Extraction/dedup commits change *structure only*. A pre-existing bug found in moved code → file a backlog entry, land the move clean, fix in a separate commit. The regression-net (snapshot/byte-stability test per §5 of `test-design-discipline.md`) verifies the move preserved behavior; a same-commit "fix" defeats that net. Composes with §5 (defend invariants with snapshot tests) — the snapshot only proves a clean move if the move didn't also change behavior.

## 33. Excision Missed-the-Consumer-Rewrite — Grep Imports Before Celebrating

*project-rag-ue-addon Phase 2 convergent finding.*

**When a donor module is excised cleanly from one repo, consumer files that still import it remain broken until a clean checkout tries to run the producer.** The split appears complete (donor is gone, schemas align, tests are green on the donor side) — then a consumer script fails at import time with no signal crossing the repo boundary.

**Rule:** before declaring any excision complete, grep `from <excised>.` and `import <excised>` across the consumer repo. This is the same hazard family as §11 (grep imports before celebrating) but applies at module-excision granularity, not function granularity. Convergent finding from two independent reviewers raises confidence. (project-rag-ue-addon shipped 6 broken `mcp_server.{structural,path_norm,host_resilience}` imports across 3 producer scripts.)

## 34. Directory-Rename Variable-Indirection Sweep

*project-rag-ue-addon (code-reviewer F10).*

**Directory-rename sweeps must grep variable-assignment indirections, not just path literals.** A `scripts/` → `project_rag_ue_addon_scripts/` rename left `SCRIPTS_DIR="$ADDON_ROOT/scripts"` in `build_engine_structural_index.sh`, silently breaking the from-source rebuild — every `$SCRIPTS_DIR/...` invocation 404'd, and `--check` masked it by passing pre-flight.

**Rule:** rename sweeps must grep three pattern shapes independently:
1. Direct literals: `oldname/` in path strings
2. Variable assignments: `<VAR>=.*<oldname>` — catches the indirect case
3. Module paths: `-m <oldpkg>.` — catches Python module references

A sweep that only covers direct literals ships with broken variable-indirected consumers. [universal]

## 35. Source-Migrate Without Test-Migrate Leaves Import-Error Wall

*Source: example-game-workbench-repo L17. [universal]*

Migrating a source module without co-migrating its test suite produces `ImportError` failures at pytest collection time that mask all real test results. The collected-count delta is the falsification: a drop in `pytest --collect-only` count relative to the pre-migration baseline means tests are invisibly broken at import time — not because code regressed, but because the test's imports lag the source.

**Rule.** Co-migrate the regression net in the same commit as the source migration. Run `pytest --collect-only` before and after — a count drop signals import failures. See also: `test-design-discipline.md` §56.

## 36. `git stash pop` After a No-op Push Applies a Stale Unrelated Stash

*Source: project-rag. [universal]*

`git stash push` followed by a push that saves nothing ("No local changes to save") leaves the stash list unchanged — the prior stash entry (from a different context) is the one that gets popped. The pop silently applies unrelated working-tree changes, corrupting the worktree before the next commit.

**Rule.** Never pop blind after a no-op push. To isolate a committed change from HEAD for targeted inspection, use `git checkout <commit>^ -- <path>` directly rather than the stash round-trip. Confirm with `git stash list` before any `git stash pop` to verify what you're about to apply.

## 37. Auditing Pivoted/Abandoned Work — Scan STATE Artifacts, Not Just Code+Spec

*Source: project-rag-ue-addon. [universal]*

When a workstream pivots or is abandoned mid-flight, the code and spec artifacts are the obvious targets for cleanup. But the highest-risk residue lives in **STATE artifacts**: sentinel files, status JSON blobs, partial migration records, half-updated registry entries, and in-progress handoff bodies that reference the abandoned approach. These state artifacts can mislead future sessions into treating abandoned-work state as current operational state.

**Rule.** When auditing a pivoted or abandoned workstream for residue, explicitly scan:
1. `state/handoffs/` and `archive/handoffs/` — any handoff body that describes the abandoned approach as in-flight.
2. `machine-local/` registry entries, sentinel files (`*-sentinel.json`, `addon-health-*`), and status JSONs written by the abandoned path.
3. Any migration helper or partial-apply record that reflects an abandoned schema/path shape.

Code+spec cleanup without state cleanup leaves a sentinel that future sessions read as "install succeeded" for a path that was never completed. Compose with §22 (shipped-status check is not enough) — a state artifact from an abandoned workstream is the same hazard applied to non-code residue.

## 38. Re-Derive Each Parent's Terminal `status:` From Disk Before a Cleanup Deletion Set — Don't Trust the Classifier Manifest

*Source: cross-repo learn-lessons. [universal]*

A distill / cleanup dry-run that classifies plan-scaffolding for deletion emits a manifest labelling each parent plan as `archived` / `shipped` / `draft` / `executing`. That manifest is a **classifier inference**, not the ground-truth frontmatter — and it drifts: a parent plan in `draft` or `executing` state can be mislabelled "archived" by the classifier, and trusting the label deletes scaffolding that three in-flight plans still depend on.

**Concrete failure averted:** a distill dry-run classifier labelled draft/executing parents as "archived." Acting on the manifest would have deleted live scaffolding for 3 in-flight plans. A pre-commit `grep '^status:'` audit over every parent re-derived the real status from disk and caught it — 7 files were `git checkout`-restored before the commit landed.

**Rule.** Before deleting any plan-scaffolding deletion set, **re-derive each parent's live `status:` from the file on disk** (`grep '^status:' <parent-plan>`), not from the classifier's manifest column. **HOLD** any parent whose disk status is non-terminal (`draft` / `executing` / `reviewed`) — only `archived` / `shipped` / `consumed` / `superseded` clears a parent's scaffolding for deletion. Pair this with the active-reference guard (§1 / §22): terminal-status AND zero active-reference grep hits is the conjoint bar; either alone is insufficient. The audit is a pre-commit gate, not a post-hoc link-heal that happens to catch the dangling reference. Composes with §15 (scout delete-candidate lists need EM-side grep before `rm`) and §37 (state artifacts from abandoned work mislead — frontmatter `status:` is itself a state artifact that the classifier can misread).

## 39. `large-producer | grep -q` Under `set -o pipefail` Silently Fails Open

*Source: ~/.claude. [universal]*

`tail -N file | grep -q PAT` on a multi-MB input: `grep -q` matches early and closes the read end of the pipe; `tail` (still writing) receives SIGPIPE (exit 141); `pipefail` propagates that 141 as the pipeline status — so `if tail … | grep -q …` evaluates **FALSE** despite a match. The bug only manifests past the ~64 KB pipe buffer, so small-fixture tests pass and the hazard is invisible in unit testing.

**Concrete failure:** both nudge hooks' skill-suppression branch was dead on every real-sized transcript (>64 KB), causing the `/handoff` nudge to fire 100% of the time — caught only in production.

**Rule.** Read into a variable, match via here-string:
```bash
content=$(tail -N "$file")
if grep -qE "PAT" <<< "$content"; then ...
```
Keep the early-exiting `grep -q` reader out of the pipeline. Test with a real-sized fixture, not a 3-line one.

## 40. Fleet-Wide Worktree EOL Strip Assumes an Autocrlf-Normalized LF Index

*Source: ~/.claude. [universal]*

Bulk CRLF→LF worktree stripping kills the Git-for-Windows autocrlf nag only where the index is already pure LF. A mixed/CRLF index (LFS-heavy or older repo) shows thousands of files "modified" post-strip and needs `git add --renormalize`, not just a strip.

## blanket ruff F401 --fix destroys implicit re-exports and fixture imports

Blanket `ruff --select F401 --fix` is destructive in repos with: (1) implicit re-exports (modules that import then re-export without `__all__`), (2) pytest fixture-argument imports (fixtures injected by name, invisible to static analysis), (3) monkeypatch-target module imports (imports that exist only so the monkeypatch can find the symbol). These are invisible to ruff's static analysis. Apply: never auto-fix F401 blindly in a repo you haven't audited; run `--select F401` in report-only mode first, then apply fixes one-by-one with manual review.

## Post-Extraction Residue Is an Orphan, Not a Conflict

Post-extraction residue (leftover wiring in a consumer after a subsystem is extracted) is an ORPHAN of the old key, not a CONFLICT with the new owner. The consumer's leftover import/reference targets the OLD deleted module; disposition is REMOVE (delete the wiring), not REPOINT (redirect to the new module). Apply: before "fixing" post-extraction residue, verify which module the leftover targets — if it targets the deleted module, remove; if it targets a still-existing module, investigate whether it should repoint.

**Before any fleet-wide strip:** survey per-repo index EOL with `git ls-files --eol` and watch for `i/mixed` or `i/crlf` index attributes. The committed `.gitattributes` `* text=auto eol=lf` is the durable fix (survives a fresh clone under system `autocrlf=true`); a worktree-only strip without an index renormalization is belt-only and may not survive the next checkout.

## §31 Stub-Dedup Canonical Is Git Commit Provenance

When deduplicating stubs across a renamed/relocated tree, the canonical
record is the **earlier git commit provenance**, not the surviving copy in
the new location. A later identical-content stub committed during a
directory-rename pass is the duplicate — even if it is the one that ends up
in the "correct" path. Verify via `git log --follow --diff-filter=A` on each
candidate; the earlier `A`-status commit is canonical. Worked example:
`cli.py:2517 / v0.7.0`.

## §32 Verbatim Code-Extraction / Dedup Must Stay Behavior-Preserving

When extracting a function into a shared module to deduplicate, the
extraction is **verbatim or it is not behavior-preserving** — any
"light tidy-up" during extraction (renamed parameter, default-value
adjustment, exception-type change, log-message wording) silently rewrites
behavior at every old call site. Diff the extracted body byte-for-byte
against the donor; tidy-up is a separate commit, after the extraction is
proven inert.

## Excision-missed-consumer + directory-rename variable-indirection

When a donor module is excised, **grep for `from <excised>.` imports in
consumer code BEFORE celebrating migration** — broken imports stay invisible
until a clean checkout runs the producer. Static `import` lines miss
re-exports and dynamic imports; pair with a `grep -F "<excised>"` sweep.

Directory-rename sweeps must grep **variable-assignment indirections**, not
just path literals. Patterns: `<VAR>=.*<oldname>` (shell + Python),
`-m <oldpkg>.` (module-spec args), `os.path.join(..., "<oldname>", ...)`,
config-key strings (`section = "<oldname>"`). Path-literal grep (`oldname/`)
catches ~70% of sites in practice; the missed 30% explode at runtime, often
hours later under a downstream consumer.

## 41. Defer Scratch Cleanup Until After PM Has Directed Follow-Ons

<!-- spec-backlink: state/lessons.md:52 -->

**Rule:** when a session has downstream consumers likely to fire after the commit (cross-repo memos, plan amendments, doctrine seeds), keep scratch artifacts through Step 4 of `/workstream-complete` — not just through the commit.

The `/bug-sweep` Phase 4 step 5 prescription "clean scratch after commit succeeds" is correct in the narrow sense but too early in practice. Scratch files from the sweep phase (grepped findings, file:line specificity, cross-repo citations) are the source material for downstream follow-ons. If the PM asks "send those memos" or "file those findings" immediately after the commit, and scratch has already been deleted, recovery requires a Sonnet to re-grep and re-verify the same evidence.

**Correct timing:** delete scratch at `/workstream-complete` session close, or on an explicit PM cleanup signal — whichever comes first. Do not delete at commit time when downstream consumers of scratch content are plausibly in flight. The practical test: "has the PM had a turn to direct follow-on actions since the commit?" If no, scratch stays.

**Empirical basis:** bug-sweep Phase 4 step 5 cleaned scratch right after the bug-backlog commit. The PM then asked to send 5 C4 cross-repo memos; the file:line specificity was gone. Recovery cost approximately one Sonnet worth of re-grepping and re-verifying.

**Applies to:** `/bug-sweep` Phase 4, `/distill` Phase E, any sweep that produces cross-repo memo candidates, doctrine seeds, or plan-amendment candidates as scratch artifacts.

## 42. `git checkout HEAD` Discard Resurrects Via Stash Pop and Rides a Working-Tree-Sourced Publish to Prod

*Source: ~/.claude. [universal]*

A `git checkout HEAD -- <path>` "discard" of unwanted working-tree changes is not durable when a stash is in play: a later `git stash pop` re-applies the same changes you thought you discarded, silently resurrecting them in the worktree. The compounding danger is the second leg — a publish/percolate step that copies from the **working tree** (not from a committed ref) then carries the resurrected changes straight to a production target. The discard looked clean, the stash pop reverted the discard, and the working-tree-sourced publish shipped the unwanted content to prod with no commit in between to catch it.

**Defense:**

1. Treat `git checkout HEAD -- <path>` as a *worktree-only* discard — it does NOT remove the same change from any stash entry. If you stashed before discarding, `git stash drop` the entry or `git stash list` + diff before any later pop (composes with §36 and `concurrent-em-hazards.md` H6 — stale-stash diff-before-pop).
2. **Publish/percolate must source from a committed ref, never the live working tree.** A working-tree-sourced publish has no audit gate between worktree state and the prod target; a resurrected discard, a sibling's uncommitted edit, or any dirty state rides through. If a publish tool reads the worktree, commit first and publish from `HEAD` (or have the tool refuse on a dirty tree).

## 43. Append-Only Session-State Files Need a Max-Age Backstop, Not Just Dedup

**Append-only session-state files require a max-age cap sized past the longest legitimate use, not just a deduplication pass.**

A dedup pass removes exact-duplicate lines from an append-only log, but it cannot prune entries that are individually unique yet collectively stale — sessions that started and never completed, tracking records that outlived their owning workstream, or entries whose origin process is long dead. Without a max-age cap, these files grow unboundedly, mislead consumers that scan them for current state, and inflate the runtime context size of skills that read them on startup.

The canonical sizing guideline: the cap must exceed the longest plausible legitimate session, plus a safety margin for clock drift and multi-machine async. `coordinator/hooks/scripts/runtime-tripwire-em-check.py:MAX_TRACK_MINUTES` is the reference example — it defines the max age (in minutes) after which a tracking entry is considered stale and eligible for expiry. Use that constant's reasoning as the template when sizing a cap for a new session-state file. *Source: central-improvement-queue #78.*

## 44. Terminal-Stamp → Immediately-Sweepable Window

*DoE-claude.*

A plan becomes archival-eligible the instant its frontmatter is stamped a terminal status (`implemented` / `superseded` / `abandoned`) — not at the next commit, not at the end of the ceremony that stamped it. Claude-klabauter `coordinator/bin/sweep-terminal-plans.py` fires asynchronously from session-init on *every* session start, and it only reads the plan's on-disk `status:` field; it has no notion of "mid-ceremony" or "close-out review still pending."

**Concrete failure:** `/workstream-complete` stamped a plan `implemented`, its close-out code-review produced findings, and while the review-integrator's plan edits were still sitting uncommitted in the working tree, a concurrent session's session-init fired the sweep and `git mv`'d the plan from `docs/plans/` to `archive/specs/` out from under the in-flight edits. The `wsc_commit` stage then looked for the plan at its pre-sweep path, found nothing, and silently skipped it — the edits survived only because `git mv` happens to carry working-tree content along with the path move, not because anything caught the race.

**Defense:**

1. Any post-stamp edit window — most notably `/workstream-complete` close-out review-integration, which runs *after* the terminal stamp lands — is vulnerable to the async sweep until those edits are committed. Commit promptly; don't leave a stamped-but-uncommitted plan sitting across a session boundary.
2. The sweep's working-tree-dirty guard (added as a DoE-side backstop) is exactly that — a backstop, not a license to leave post-stamp edits dirty. Treat "the guard will catch it" the same as treating a snapshot test as a substitute for correct sequencing: it narrows the blast radius, it doesn't remove the race.
3. Downstream effect to watch for: `wsc_commit`'s staging step may report a mid-ceremony-archived plan as `missing:<path>` when the sweep has already relocated it. This is a known silent-skip failure mode — a cross-repo memo to claude-klabauter is open tracking a fix on that stage's path-resolution. Don't assume `missing:<path>` means the edits were lost; check `archive/specs/` for the plan before treating the skip as data loss.

Composes with §38 (re-derive terminal status from disk before deletion) — same underlying fact, opposite direction: §38 is about trusting stale terminal-status labels for a *deletion* decision; this entry is about a *stamp-then-edit* window racing an automated consumer of that same status field.

## 45. Cross-Repo/Fleet Identity Rename: Classify Every Hit by SHAPE Before Editing

*DoE-claude — provenance: `docs/plans/2026-07-11-example-store-repo-rename-surgery.md` (archived).*

A fleet-wide identity rename (e.g. `delphi-cockpit` → `example-store-repo`) is not a single-shape sed-sweep problem — the same literal token recurs across at least six structurally distinct shapes, and each shape carries an *independent* fix-vs-leave disposition:

1. **Name-ref** (repo/plugin name in prose, config, doc titles) — FIX.
2. **Env-var** (e.g. `DELPHI_COCKPIT_HOME`) — FIX (with care for downstream consumers still reading the old var).
3. **Dated spec/plan filename** (e.g. `2026-06-01-delphi-cockpit-something.md`) — LEAVE; the filename is a point-in-time backlink, not a live identity reference.
4. **Registry-key code-ref** (a string literal that resolves a registry/config key named after the old identity) — FIX only if the key itself is being renamed in lockstep; otherwise LEAVE, or the code-ref silently stops resolving.
5. **Point-in-time state record** (ceremony JSON, historical goals-log entries, snapshot artifacts) — LEAVE; rewriting history to match current identity destroys provenance.
6. **Live-data repo-path segment** (an actual filesystem path a running system reads today) — FIX, but verify no external consumer still writes to the old path first.

A blanket `grep -v archive` acceptance criterion is insufficient and can even contradict its own anti-scope — it does not distinguish shapes 3/5 (which *should* stay untouched, archive or not) from shapes 1/2/4/6 (which need to move). Classify each hit by shape before deciding fix-vs-leave; do not run a single global sed pass across all hits.

This composes with, but is broader than, the rename-blast-radius miss captured in `state/lessons/2026-07-07-rename-blast-radius-needs-both-reference.yaml` (which covers only the narrower colon-namespace-vs-slash-form grep miss) — that lesson is about *finding* every hit; this entry is about *disposing* of each found hit correctly once you have it.

## 46. Premise-Check Dead-vs-Fallback Before Bulk-Deleting "Dead" Scripts

*DoE-claude.*

A handoff "delete N dead X" item is a hypothesis, not a verdict — several classes of script read as "dead" to a shallow grep yet are load-bearing:

- **Guard-DEAD but oracle-LIVE** — never called on the live path, but a parity/golden test *sources* it as the reference oracle. Deleting it breaks the test, not production — and the break may not surface until the test suite next runs.
- **Permanent strangler State-1 fallback** — fires only when the native/engine path is absent (the fail-closed branch). It is dead on the author's machine (engine present) and live on any machine where the engine isn't — deleting it removes the guard on exactly those machines.
- **Shared-test entanglement** — shares a test fixture spanning deletable AND non-deletable members, so it is not isolable without splitting the fixture first.

**Rule.** Before deleting anything a handoff labels "dead" — especially a fail-closed security/parity guard — run a read-only dead-vs-fallback verification: trace the live path, grep every sourcer/caller (tests included), and map any fallback wiring (State-1 / engine-absent branches). Deletion may correctly fold into a larger coupled unit rather than being isolable. Composes with §1/§22 (active-reference grep) and §38 (re-derive status from disk) — same family: a "dead" label is a classifier inference the disk can contradict.

## Skill Checklist Reference

`/distill` and `/update-docs` should reference items 1, 2, and 3 in their dispatch prompts so the agent enforces these checks during sweep operations, not just the EM after the fact. `/bug-blitz` consumers reference item 19 for backlog-currency verification. `/coordinator:plan` Branch B references item 20 when the plan body flips a doctrine value-class. `/coordinator:plan` and `/bug-sweep` reference items 27–30 when the work is a class-scoped sweep — enumerate the construct class, build a class-catching lint (not a site list), and test the guard against an unseen class member. Items 33–34 apply to any cross-repo excision or directory-rename plan — add consumer-grep and variable-indirection grep to the done-criteria. Items 39–40 apply to any shell pipeline using `grep -q` on large inputs or any fleet-wide EOL sweep. Item 41 applies to any sweep that produces downstream-consumer artifacts (memos, doctrine seeds, plan amendments) — keep scratch through PM follow-on opportunity, not just through the commit. Item 42 applies to any `/percolate` / claude-klabauter `coordinator/bin/publish.py` flow and any cleanup that discards changes via `git checkout HEAD --` while a stash is in play — source publishes from a committed ref, never the live worktree.
