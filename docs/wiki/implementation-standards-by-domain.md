---
system: implementation-standards-by-domain
last_updated: 2026-05-07
status: active
provenance: extracted from coordinator/CLAUDE.md § Implementation Standards Cluster 3 sub-headings (2026-05-07)
---

# Implementation Standards by Domain

> **The rule.** Domain-specific implementation standards live here. Domain-specific rules
> (observability contracts, database/indexer correctness, dependency management, engine plugin
> packaging) live in this wiki — they're high-value when you hit the failure mode in that domain,
> but pay no cost on every read of a shared always-on file (see § Why this exists below).

## Cross-cutting standards (formerly `coordinator/CLAUDE.md § Implementation Standards`)

<!-- spec backlink: docs/plans/2026-07-27-claude-md-altitude-triage.md C11 — coordinator/CLAUDE.md
     was retired and deleted whole; these three flat bullets from its § Implementation Standards
     had no other verified destination in the corpus at deletion time, so they land here rather
     than being silently dropped. -->

- **OOS framing must be architectural, not appetite-based.** Name the irreversible cost or hard
  constraint. "Not now / follow-up" hedging is incomplete work, not OOS. → `CONTEXT.md`'s
  Appetite-based OOS glossary entry; mechanically enforced by `agents/plan-coverage-checker.md`.
- **Land regression-net tests BEFORE the refactor that depends on them.**
- **Detect-then-silently-pick is a footgun** — refactor to detect-then-fail-loud on ambiguity.
  Guards match conditions, not containers. →
  `docs/wiki/codebase-judgment/detect-then-silently-pick-is-a-footgun-fail-loud-instead.md`.

## Why this exists

<!-- spec backlink: docs/research/spike-verdicts/2026-07-27-plugin-claude-md-delivery.md -->

Coordinator `CLAUDE.md` is **not** read at every session start — see
`coordinator/docs/wiki/claude-md-surfaces.md` § Trap A and
`coordinator/docs/wiki/claude-md-delivery-topology.md` for the fuller account. It loads only in a session whose cwd is
DoE-claude, and only after that session Reads some file under `coordinator/` (ordinary nested-
`CLAUDE.md` lazy loading, unrelated to `--plugin-dir`); it reaches no sibling-repo session at all,
and can evaporate again on `/compact`. Whatever the parent file's load timing turns out to be, the
extraction argument doesn't rest on "always loaded" — it rests on **shared-load economics**:
whenever and wherever the parent loads, its full byte cost lands on every session that triggers
the load, whether or not that session is working in the domain a given standard covers. Domain-
specific standards (observability, DB/indexer, dependency, engine plugin) apply only when working
in that domain — folding them into the shared parent would mean every triggering read pays for
content most of those reads don't need. Promoting them to a wiki keeps the doctrine intact,
greppable when relevant, and out of the shared-load payload — the conclusion survives the
corrected mechanism unchanged; only the false universality claim ("boot path", "95% of sessions")
is retired.

See `docs/wiki/document-bloat-trim.md` for the general extraction rule.

## Observability contracts

- **Log field names are contracts, not labels.** A field must measure exactly one fact, named for that fact. `cuda_available` reporting NVML probe state (not device availability) misled reviewers for an entire release cycle — the name promised a different fact than the value delivered.
- **Silent absence is indistinguishable from success.** Fail-open paths and gate-skipped phases must both emit structured events; default-on-with-opt-out beats default-off-with-opt-in for load-bearing phases.
- **Fail-open paths require a structured "degraded mode" emit.** Fail-open is often the right default (don't hard-block the user when a probe library is missing), but it must be coupled with a queryable signal: `logger.warning("vram_probe degraded — pynvml not installed; gate disabled", extra={"pynvml_importable": False, "vram_gate_active": False})`. The field names must let a log-analytics pass enumerate hosts where the gate is non-functional. A silent fail-open is a silent no-op.
- **Silent env-var-gated skips break diagnostic loops.** When a script consults an env var to decide whether to run a load-bearing phase, the absence path must emit a structured skip event the diagnostic surface can detect — and the default should be *on with explicit opt-out*, not *off with implicit opt-in*. Probes that say "run X to fix this" silently no-op when X's env-gate is unset produce identical FAIL across multiple remediation attempts with no diagnostic signal.
- **Long-running backgrounded scripts need machine-parseable progress.** Any backgrounded long-running script the agent dispatches must emit (a) a status file at a known path (machine-parseable JSON), (b) a heartbeat timestamp updated every N seconds (liveness), and (c) tagged stdout at phase boundaries using a three-tag taxonomy: `PHASE-START:<name>` / `PHASE-END:<name>` / `PHASE-SKIP:<name>:<reason>`. Cat-ing tmp files and grepping the script for `Read-Host` is the diagnostic shape that signals the surface needs structured output. See `docs/wiki/dispatching-parallel-agents.md` § Long-Running Dispatched Process for the full status-file schema.

## Database / indexer correctness

- **Authority follows definition site, not invocation site, in any structural indexer.** Resolving a symbol at the call site produces the wrong canonical when the definition lives elsewhere — index at the definition, resolve outward.
- **When normalizing one path column, inventory ALL path-typed columns across ALL tables before declaring done.** A single-column patch leaves sibling columns broken; LIKE predicates let ACs pass clean while sibling queries silently return wrong data.
- **`INSERT OR REPLACE` + post-COUNT reports table residue, not insert delta.** Take a pre/post diff of row counts (or use `changes()`) when the goal is "how many rows were written this call."
- **Multi-root callers with an unscoped known-set wipe each other.** Scope the known-set query to the call's input boundary; a shared global set causes one caller's inserts to be invisible to a sibling caller's seen-check.
- **Schema CHECK enum widenings need a paired idempotent migration helper, not just a SCHEMA_DDL edit.** DDL-on-create and migration-on-upgrade are asymmetric: editing `SCHEMA_DDL` widens the CHECK constraint only for *freshly created* databases. Already-migrated DBs keep the narrow CHECK and silently reject the new enum value at INSERT time. Every enum widening ships two changes — the DDL edit AND an `ALTER`/rebuild migration helper that runs idempotently on upgrade. Grep for the existing migration-runner before adding the value.
- **Symmetric hookspec/handler wiring: when one half ships, grep for non-test PRODUCTION callers of the symmetric pair.** A hookspec or paired event handler can be defined, tested, and green while the production side that fires it is never wired. Test invocations exercise the spec in isolation — they do not prove the runtime path calls it. After landing one half of a symmetric pair, grep for non-test production call sites of the other half before declaring the wiring complete. (Applies to pluggy hookspecs, event emitters, paired serialize/deserialize.)
- **In-place `UPDATE`-by-derive is a valid post-hoc remediation when the producer omitted a derivable column and source data is preserved — MUST be paired with a durable producer-side fix.** When a pipeline stage writes rows without a column whose value can be derived from other columns already in the row (e.g. a missing `normalized_path` derivable from `raw_path`), an `UPDATE tbl SET col = derive(other_col) WHERE col IS NULL` corrects all existing rows in one idempotent pass. This is correct ONLY when: (a) the source data needed for derivation is still present in the same table, and (b) a producer-side fix ships in the same workstream to prevent future omission. An UPDATE without the producer fix is a one-time patch — the column is empty again after the next pipeline run. Apply: land the UPDATE migration first (so the column is populated for consumers that run immediately), then land the producer fix in the same commit or the next one; document the migration as `idempotent: WHERE col IS NULL` so re-runs are safe. (Source: coordinator-improvement-queue L119.)

- **An insert-only callback invoked under an orchestrator's open write transaction MUST share the orchestrator's connection — a second connection deadlocks.** SQLite is single-writer: if an orchestrator holds an uncommitted write transaction (e.g. a step-b DELETE) and a wired-in `extract_fn` opens its *own* connection to INSERT, the real path raises `database is locked` at the insert. This stays invisible when the only test **mocks** the transaction-holding function — the held connection is never real, so the callback's second connection never collides. Pass the live connection into the callback, and test the callback under a genuinely-held write txn, not a mocked one. (Source: project-rag.)
- **An "atomic swap" built from delete-then-rename has a non-atomic boundary — guard the rename and fail loud, naming the temp.** A collection/table swap that builds into `<canon>__building_<tok>`, then `delete(canon)` + `rename(building → canon)` on success, *reads* as atomic but is two calls. If the delete succeeds and the rename then raises, the canonical is gone AND the freshly-built data sits under a `__building_*` name that the next build's orphan sweep deletes unconditionally — permanent data loss. Wrap the rename so a failure fails loud naming the surviving temp (an operator can recover it), and make the orphan sweep spare a `__building_*` sibling that has no live canonical peer. (Source: project-rag.)

## Structured-config write primitives (TOML / JSON / YAML / ini / frontmatter)

Write primitives that mutate structured-config formats fail in a class the text-search eye misses: the write lands somewhere the *reader* won't look. The unifying discipline is round-trip verification against the reader's resolution logic — see also the schema CHECK enum-widening rule under DB/indexer (DDL-on-create vs migration-on-upgrade is the same write-lands-in-the-wrong-place asymmetry, applied to schema).

- **A write primitive that mutates structured config must round-trip-verify against the READER logic before declaring success.** Text-searching the output for the inserted token proves the bytes are present, not that the reader resolves them. The fix has three layers: (1) correct shape handling on write, (2) post-build re-parse of the emitted file, (3) a reader-equivalent resolve check (load it the way production loads it and assert the value comes back). Zero-test config-mutation codepaths shipped in CLIs are the recurring smell — a mutation path with no round-trip test is unverified by construction.
- **TOML flat keys written after a `[table]` header are table-scoped, not document-root.** Appending `key = value` to the end of a TOML file places it under whatever the last `[table]`/`[[array]]` header was — so a "top-level" key inserted at EOF becomes a member of the final table. Text-search for the key passes (the literal is in the file); the reader's document-root lookup fails (it's nested). For a true top-level key, insert it *before the first `[table]` header*. This is the canonical example of why round-trip-against-reader (above) is non-optional for TOML writers.

## Emitting a file into a directory the tool doesn't exclusively own

- **A tool that writes config into a directory it does not exclusively own must stamp a managed-marker and never clobber an unmarked file.** When a host emits a file (`.clangd`, `.editorconfig`, a settings JSON) into a *consumer workspace root* — a directory the user also authors in — an unconditional atomic write silently destroys hand-authored config. "Emit a config file" reads as a pure write, but the target dir is shared, so the write is really a three-way decision: no file / our file / their file. Stamp every host-emitted file with a marker line, and before writing: absent → write; marker present → overwrite (it's ours); present-but-unmarked → do NOT clobber (back off, warn, or write a sidecar). (Source: project-rag, LSP `.clangd` emitter.)

## Dependency management

- **Dependency-CVE triage reconciles against the committed lockfile resolution, not the shared system env.** A `pyproject.toml`/manifest floor does not bind until the lockfile is regenerated — a vulnerable transitive version can still be the *resolved* one even after the floor is bumped. Triaging against `pip list` / the ambient venv reports whatever happens to be installed on this box, which may be newer (false-clear) or older (false-alarm) than what the lockfile pins for everyone else. Read the committed `uv.lock` / `poetry.lock` / `requirements.txt` resolution, and require a lock-regen step in the same change that bumps the floor.
- **Vendor with a mechanical SHA pin, not a doc-only policy.** A pinned SHA is machine-verifiable and survives doc drift; a policy note in a README is not enforceable at build time.
- **Substrate pins belong in `pyproject.toml` / `setup.cfg` / declared manifest, NOT in installer scripts.** Python version, library minimum, CUDA variant, and similar substrate constraints belong in the declared package manifest where every tool (pip, uv, build systems, CI) sees them. Installer-side pins drift from manifest and silently install the wrong substrate when called out-of-band (direct `pip install`, editor-driven venv creation, sibling repo bootstrap).
- **Bash scripts shelling to Python MUST resolve the interpreter via the `COORDINATOR_PYTHON`/registry/PATH resolution contract**, not hard-coded `python` or `python3` and not (the retired) `lib/resolve-python.sh` helper. Resolution order: explicit `COORDINATOR_PYTHON` env → `machine-local get coordinator.python` (registry pin) → PATH fallback — see `machine-local-registry.md § coordinator.python resolution contract`. Hard-coded `python` picks up whichever interpreter `$PATH` happens to expose, which on shared machines (Windows + WSL, multi-version dev boxes) is rarely the one the script was authored against.
- **An automated manifest edit (version bump, dep floor) via shell must end with a parse gate before the release commit lands.** A `sed`/`grep`/`echo` redirection that touches `pyproject.toml`, `package.json`, or similar can silently inject stray stdout into the file body — the write appears to succeed, the manifest is malformed, but green local state on the authoring disk is not a parse check. Gate: `python -c "import tomllib; tomllib.load(open('pyproject.toml','rb'))"` (or JSON/YAML equivalent) immediately after the edit, before the commit. *project-rag.* The v0.8.0 `/workweek-complete` version bump piped a shell-output line (`0.7.0 line found`) into `pyproject.toml:7`, breaking TOML parse → all pytest/pip/build failed on `origin/main` and shipped that way unnoticed. Belongs in the `/workweek-complete` version-bump step.

## Ship-complete — no degraded-mode evasion

**A long-running orchestrator must be idempotent across completed sub-phases, not just per-shard within a phase.** Every sub-step that produces a durable artifact must guard its execution on absence of that artifact — a 4-line `if [ -f $OUT/$src.sqlite3 ]; then skip; fi` turns O(N × source-time) recovery cost into O(1 × source-time). "Resumable" in handoffs often means per-shard within a source; cross-source resume requires explicit artifact-absence guards. When a step fails at position N, recovery must not re-extract N-1 hours of completed work. (Source: project-rag-ue-addon L83)

These two share a shape: a partial or degraded deliverable presented as if it were the real thing. The OOS test from this wiki's own § Cross-cutting standards ("name the irreversible cost, not the appetite") applies — but these are the specific execution-time forms.

- **Deferred-remediation banners on validators are time bombs — ship the gate plus the cleanup together, or ship the gate advisory-only.** A validator that hard-fails while emitting "TODO: clean up the N pre-existing violations later" is a landmine: the next contributor trips the gate on work they didn't author, and the deferred cleanup never happens. Either land the gate *and* the cleanup of existing violations in the same change (so the gate enforces a clean state from commit one), or land the gate in advisory/WARN mode until the cleanup lands. A blocking gate with a deferred-cleanup banner is incomplete work wearing a completion banner.
- **A degraded demo shape is an evasion, not a substitute.** When the real target proves infeasible at execution time, swapping in a stripped-down "demo" target that technically runs but doesn't exercise the capability is the same incompleteness pattern as the deferred-cleanup banner — it ships a green signal over an unproven feature. Find a real target (the right shape is "what would actually prove this works?") and get PM acknowledgement of the substitution before treating the degraded run as evidence.

## Engine plugin packaging

- **UE plugin distribution mode determines DLL load location.** `AdditionalPluginDirectories` (engine-managed) and project-local plugin paths load from different directories; conflating the two produces inverted directional rules. Verify distribution mode before writing any DLL-path logic.
- **An accessor that would close a UE module build-dependency cycle must be mediated via a shared lower module — grep both `Build.cs` dependency lists before authoring.** A direct back-edge from module A to module B, when B already depends on A, creates a circular dependency the UBT linker will reject at build time. Before adding a new cross-module accessor, grep both modules' `Build.cs` `PublicDependencyModuleNames` and `PrivateDependencyModuleNames` lists to detect existing dependency direction. If A already depends on B (or transitively reaches B), the accessor must live in a shared lower module that neither A nor B depends on — never in A reaching back to B. How to apply: (1) grep the two `Build.cs` files for each module's name in the other's dep list; (2) if a back-edge would form, identify or create a shared module (`Core`, `CoreUObject`, or a project-local `SharedTypes` module) that both A and B can safely depend on; (3) land the accessor there. (Source: coordinator-improvement-queue L128.)

## Shell

- **Python stdout via `read -r` on Windows carries CR; strip it.** Patterns of the shape `read -r VAR1 VAR2 < <(python -c '...print(...)')` on Git Bash silently capture `"VAR\r"` — downstream comparisons like `[[ "$VAR" != "Write" ]]` are unexpectedly true and `bash -x` traces are misleading (the trace shows both operands of `&&` inside `[[ ]]`, making short-circuit look broken when the real defect is the trailing CR). Diagnostic: `echo -n "$VAR" | xxd` to confirm the trailing `0d`. Fix: pipe Python output through `tr -d '\r'` before `read`. Greppable signature for review: `read -r ... < <(... python ...)` without a `tr -d '\r'` somewhere in the chain. `set -uo pipefail` does not catch this.

- **Bash → other-interpreter interpolation is the dominant P1 injection family.** `node -e "$VAR..."`, `python -c "...$VAR..."`, `sed "s/x/$VAR/"`, `pwsh -Command "$VAR..."` are all silently corruptible when `$VAR` contains `'`, `"`, `$`, `&`, `/`, or `\`. Default authoring posture: pass values through argv (`node -e '...' -- "$VAR"`), env vars (`VAR="$value" python -c "...os.environ['VAR']..."`), or a `printf '%s' | sed ...` chain with a pre-pass escape. Every occurrence of `-e "...$"`, `-c "...$"`, or `s/.../$VAR/` in a shell script is a code-review candidate. The pattern looks harmless on controlled input and fails catastrophically on user-supplied or path-derived values containing special chars.

- **`cmd || rc=$?` that logs failure but never `exit $rc` is a doctrine-shaped REQUIRE-mode bug.** When a helper's return-non-zero contract is "only in REQUIRE mode" (`X_REQUIRE_Y=1 → hard-fail; default → warn-and-continue`), the caller's exit propagation is doing *all* the REQUIRE-mode enforcement. `cmd || _rc=$?; status_log fail` captures and clears the failure — the rest of the script proceeds even under `set -euo pipefail` because the `||` swallows the non-zero exit. Bug is invisible in normal runs (rc=0 short-circuits) and invisible in default-mode failures (no non-zero rc returned); only the rare REQUIRE-mode-and-failing path surfaces it, which by definition is a CI-edge case. Two-line fix: `if [[ $_rc -ne 0 ]]; then status_log fail; exit "$_rc"; fi`. Greppable: `rg -n '\|\| [_a-z]+_rc=\$\?' scripts/` then check each match for matching `exit "?\$.*_rc` within ~6 lines. Folds with the "test that passes for the wrong reason is functionally equivalent to no test" pattern.

## Comment provenance and primitive layering

All three rules below share a shape: comments-as-stories don't age well; structured citation does. When in doubt, lift the explanation out of the comment and into a commit message + commit-SHA pointer, or delete the comment entirely.

- **When defensive hardening bloats past the primitive, the primitive is at the wrong layer.** A guard pile that grows comment-per-edge-case ("handle case X", "but watch out for Y", "Z is also valid when …") is the symptom; the cause is that the primitive sits below the layer where those distinctions exist. Refactor up — move the primitive to the layer that has the type, the schema, or the context to express the distinction structurally. Each new guard added in place is debt; the primitive is misplaced. Applies to any embedded-language pattern (shell-in-JSON, SQL-in-JS, regex-in-config) where the host language can't see the embedded structure.

- **Dated bug-fix narrative comments are frozen-in-time stories.** `// 2026-04-09 — fixed crash when foo is null because bar` reads well in the review but ages into a fossil the moment the surrounding code is refactored. The comment ages into pointing at a fix that may not exist, against a bug that may not reproduce, in a code path that may not run. Prefer a commit-SHA citation in the commit message + (when truly needed in-line) a one-line `// see commit <sha> — <subject>` pointer; the SHA stays valid even when the narrative goes stale. Migrations and refactors should not have to update comment prose to remain truthful.

- **"Empirical verification" comments without provenance age into folklore.** A comment that says "tested empirically, this works" or "verified — N is the right limit" with no test file, no dated run-log, no benchmark artifact cited is folklore the moment its author leaves. The next reader has no way to re-verify and no signal whether the claim still holds. Either cite a test/log path (`see tests/perf/foo_test.py::test_n_limit, run 2026-05-12`) or omit the comment and let the test be the documentation. A code comment that asserts an empirical fact without a verifiable pointer back to the verification is worse than no comment — it stops future readers from re-checking.

## Python

- **Module-top unconditional cross-package imports break graceful-fail at port-out boundaries.** A top-level `from sibling_pkg import X` raises at module load time when the sibling package is absent — it fires before any `try/except` in `__init__` paths can catch it. This defeats every lazy-degradation strategy and turns an optional dependency into a hard one. Guard with function-scoped imports (`def foo(): from sibling_pkg import X; ...`) or a sentinel-import pattern (`try: import sibling_pkg as _sp except ImportError: _sp = None`) with lazy-use at call sites. Applies equally to optional C-extension imports (e.g. `pynvml`, `torch`) that should fail gracefully when absent.
- **`importlib` exec_module of a helper re-runs its top-level imports — its dir must be on `sys.path` before exec, or a sibling import fails silently at load.** Loading a module by file path (`importlib.util.spec_from_file_location` → `spec.loader.exec_module`) does NOT add the module's directory to `sys.path`, unlike running `python foo.py` (which prepends the script's dir). So a top-level `import sibling` inside the exec'd helper resolves against whatever `sys.path` already is — and if the helper's own directory isn't on it, a same-dir sibling import raises `ModuleNotFoundError` at exec time. The trap is the asymmetry with `python foo.py`, which is why hand-testing the helper standalone passes while the path-loaded invocation fails. Fix: prepend the helper's directory to `sys.path` before `exec_module`, or restructure to import the helper as a proper package member. (Source: example-game-workbench-repo.)

- **Python `fnmatch`'s `*` crosses `/` — use component-wise matching for path-glob semantics.** `fnmatch.fnmatch(path, "state/reviews/*.md")` MATCHES `state/reviews/<topic>/the Staff Engineer-review.md` because `fnmatch`/`fnmatch.translate` compiles `*` → `.*` (path-blind). A glob meant to bind `*` to a single path segment must use `pathlib.PurePath.match` or a gitignore-style matcher — not `fnmatch`. The failure is silent over-capture (a drift validator pulled 59 nested files into one type and inflated its count), not an error. (Source: project-rag.)
- **A FastMCP-registered callable's signature IS its pydantic arguments model — a `lambda *a, **kw` wrapper surfaces `a` and `kw` as required fields.** FastMCP introspects the registered callable's signature to build the tool's argument schema. A var-args lambda wrapping a handler (e.g. returned from a factory) registers `a` and `kw` as required positional fields, corrupting the wire schema. Any wrapper FastMCP consumes must preserve the original handler's typed signature — a named wrapper with explicit params, or `functools.wraps` plus a real signature, never `lambda *a, **kw`. Only an in-process daemon round-trip surfaces the regression; isolated unit tests of the handler pass. (Source: project-rag-ue-addon.)

## Validator design

- **A membership validator allowlists the valid token SHAPE and checks the allowlist only on shape-matches — never collect-everything-then-reject-non-members.** A validator enforcing "every token must be one of this small enumerated set" has two implementations: (a) match the *shape* of a candidate token (the bracket/sigil/grammar that marks it as in-scope), then check only shape-matches against the allowlist; or (b) collect every token in the file and reject any not in the set. Shape (b) is a denylist in disguise — it grows a false positive for every new convention (a new bracket type, a new comment marker, a new directive) the validator never anticipated, so the validator breaks the moment the surrounding language gains a feature. Allowlist the shape, scope the membership check to shape-matches.
- **Per-write validation hooks validate the delta, not the reconstructed whole file.** A hook firing on each write should check the change being made, not re-scan the entire reconstructed file — re-scanning re-litigates pre-existing content the write didn't touch and turns every edit into a whole-file gate.
- **Overlapping skip-lists answer different questions — run a semantic check before SSOT-consolidating them.** Two skip/exclude/ignore lists that overlap in entries are not automatically duplicates to merge into one source of truth. Ask what question each list answers (e.g. "skip from indexing" vs "skip from linting" vs "skip from the dirty-tree gate") before consolidating — collapsing two lists that share entries but answer different questions silently changes behavior for the entries unique to one list.

## Regex-based code-extraction gates must strip comments before matching

*example-game-workbench-repo.* [universal]

A regex-based code-extraction gate (action-map discovery, enum-member extraction, symbol/declaration scanning) MUST strip comments before matching — a `}`, `*/`, or quoted token inside a comment terminates brace-matches prematurely AND injects phantom captures.

**Empirical case:** an enum-handler-sync gate for `const X_ACTIONS = { KEY: 'value' }` object-literal maps captured `'ubt'|'msbuild'` from a JSDoc type-union doc inside a comment, and a `{ raw, ... }` example in the same comment prematurely closed the non-greedy `([\s\S]*?)\}` brace match — the real `triage_build_log` value after the comment was missed.

**Fix:** strip `/* */` and `//` blocks before extraction — `.replace(/\/\*[\s\S]*?\*\//g,'').replace(/\/\/[^\n]*/g,'')`. Stripping comments is strictly subtractive (can only remove false captures, never add real ones), so it is safe for existing patterns.

**How to apply:** any gate that greps source for definitions (case labels, enum members, action maps, symbol declarations) should strip block and line comments before extracting. Caveat: `//` inside a string literal (URL, regex literal) — assess whether stripping risks a false negative for your specific source shapes. Land the false-positive guard as a regression test (a synthetic-source case proving comment tokens are not captured). Sister to detect-then-fail-loud.

## Layered filtering — keep the cheap gate dumb, let the smart layer judge

**Two-layer defense (cheap upstream gate + LLM/expensive downstream filter): never let the upstream gate grow teeth.** When a pipeline filters in two stages — a cheap mechanical pre-gate (regex, keyword match, schema check) feeding a more expensive judgment layer (an LLM classifier, a semantic filter, a human review) — the correct division of labor is: the upstream gate stays *permissive and dumb* (it drops only the unambiguous junk and passes everything plausible), and the downstream layer makes the discriminating calls. The failure mode is letting the cheap gate accrete judgment logic ("also reject if X, unless Y, but allow Z") to "save" downstream calls — every rule the upstream gate grows is a false-negative the smart layer never gets to see, and the discrimination logic now lives in the layer least equipped to do it.

**Rule.** Express the upstream gate's scope as a **negative-spec block inside the gate module** — enumerate what it is *allowed* to reject and explicitly forbid it from making the judgment calls reserved for the downstream layer. The negative-spec is the structural guard against the gate's incremental teeth-growth: a reviewer (or a future you) adding a discrimination rule to the gate trips against the in-module spec that says "this decision belongs downstream." (Source: example-league-data-repo.)

## Cross-cutting design

- **Avoid value-type polymorphism when fixing shape-divergence bugs.** If a function returns `str | list[str]` because callers disagree on shape, and you're fixing a bug caused by that divergence, don't paper over it with an `isinstance` gate — that re-creates the bug class the fix was meant to eliminate. Prefer a canonical-shape representation with explicit conversions at boundaries (e.g. always return `list[str]`, normalize at ingestion). Polymorphic value types are a hidden precondition contract that propagates indefinitely.

- **Override-flag defaults should fail-loud, not legacy-compat.** When adding an opt-in or opt-out flag to behavior that previously had no flag, choose the default whose failure mode is *visible*. Replace-by-default silently drops data; augment-by-default consults one extra source (visible in output). The legible failure is almost always the safer default. Generalizes broadly: API design (additive vs. replacing semantics), feature-flag defaults on new capabilities, config-schema migrations where the old path is now one of N options, override-mode semantics. When in doubt, ask "which default mode would a developer notice immediately if wrong?" — that's the right default.

## Named contracts vs incidental flags

- **A workaround that relies on a flag's incidental name/value** (e.g. piggy-backing on `--legacy-compat` to enable an unrelated behavior) is not a solution — it's debt the next refactor will silently break. Add an explicit named contract (a new flag, a constant, an env var) when the behavior is intentional.

## Shared-layer read/write conflation

- **A shared-layer constructor that is both a read and a write path (e.g. `chromadb.PersistentClient`) should not receive a pattern-match guard at construction time** — that guard blocks legitimate read callers who happen to pass through the shared constructor. Ownership data and caller-inference belong at a WRITE-ONLY seam (the path that actually mutates state), not at the shared constructor that reads and writes share. When adding a guard to prevent unauthorized writes, locate the guard at the point where the write diverges from the read path. (Source: project-rag)

## Gate on Discriminating Signal, Not Coarse Aggregate

- **A new capability must gate on its own precondition, never inherit the legacy guard of the code it was bolted onto.** The inherited guard silently defeats the new capability's primary use case. When a feature is added to a seeder whose existing job was finding a *source clone*, gating binary-writing on `_has_ue_context` (source present) means a binary-only machine — the universal-floor consumer tier — gets no binaries written. Fix: gate on the new capability's own signal (binaries discovered), let the empty-result no-op preserve the legacy contract naturally, and update the legacy tests to mock the new input empty. **Tell:** when a feature subordinates itself to a pre-existing test to avoid touching it, the gate is wrong. (Source: project-rag-ue-addon L75)

- **When a downstream consumer needs to distinguish between multiple outcome types, gate it on the discriminating signal, not a coarse aggregate rollup.** An `OVERALL_VERDICT` flag that collapses `[PASS, WARN, SKIP]` → `PASS` and `[FAIL, ERROR]` → `FAIL` loses the WARN and SKIP distinctions that downstream consumers may need to branch on. Callers who only care about pass/fail get a simpler API; callers who need finer discrimination get a broken one. Prefer: emit the full structured result, let each consumer pick the rollup they need. If an aggregate IS needed, compute it from the structured result at the callsite rather than baking it into the producer. (Source: project-rag)

- **A capability GUARD that delegates to a LOADER must widen when the loader's capability widens.** A pre-flight fail-loud gate's accept-set must be defined in terms of — or delegated to — what the guarded operation actually accepts. When a downstream capability set changes (a new device, format, or auth mode the loader now handles), the guard that fronts it silently rejects the newly-valid input until its accept-set is re-derived. Grep every guard of a capability whenever that capability widens, and re-derive their accept-sets from the loader; keep the gate's *policy* while widening its *detection* — the two are separable. (Source: project-rag-ue-addon.)

## External-CLI producers

- **A producer that shells out to an external CLI must health-gate the tool and quiet-degrade on its absence/failure — never let a missing or broken external CLI poison the whole run.** When a producer (indexer, extractor, formatter, linter wrapper) depends on an external binary (`git`, `clang`, `ripgrep`, an LLM CLI, a vendor tool), a missing/incompatible/erroring invocation must NOT abort the run or write garbage downstream. Gate at the call boundary: probe the tool once (resolvable on PATH, version compatible), and on failure emit a structured degraded-mode signal (per § Observability contracts: `logger.warning("X unavailable — feature Y disabled", extra={...})`) and continue with the feature cleanly skipped. The anti-pattern is a producer that hard-fails (or silently emits empty/corrupt output) the moment the external CLI is absent, turning an optional capability into a run-killer — and a fail-open that drops the output without any queryable trace. Composes with § Python "module-top unconditional imports break graceful-fail" (same fail-at-boundary discipline, applied to subprocess deps) and § Observability "silent fail-open is a silent no-op." (project-rag.)

## Cross-repo contract discipline

- **An addon/plugin row whose field crosses into a host envelope must use the HOST's palette, not the addon's local enum.** When a sibling/addon produces a structured row the host wraps into its own envelope (e.g. `FailureCatalogRow.runtime_verdict` flowing into the host's result envelope), the field's value space is the *host envelope's* verdict palette — not the addon's richer per-probe outcome enum. Authoring the field against the per-probe enum produces values the host can't place in its envelope. Soft-probe / catalog-row authors must confirm which palette governs a cross-boundary field before populating it; dispatch briefs for new soft-probe authors should name the host palette explicitly.
- **A probe or tool that spawns a sibling's daemon directly inherits NONE of the sibling's lifecycle-manager safety.** Bypassing the sibling's lifecycle manager (its `ensure-server` / supervisor / launcher) to spawn its daemon process directly skips every guard the manager owns — park-on-idle, crash-loop breaker, resource ceilings, single-instance locking. Either route the spawn through the sibling's lifecycle manager, or replicate the manager's guard signals at the spawn site (and accept that the replica drifts from the canonical guards). Direct-spawn is a footgun precisely because it works in the happy path and fails only under the conditions the skipped guards exist to handle.
- **A one-shot resolver cache over addon/sibling-supplied substrate must lazy-re-resolve on `None`, not freeze the first (possibly pre-boot) miss.** When a resolver reads substrate another repo provides (an addon registry, a sibling's config, a hookspec-contributed value) and memoizes the first result, a resolution that happens *before* the addon substrate is wired returns `None` — and a one-shot cache then freezes `None` forever, long after the substrate becomes available. Treat `None`/empty as "not yet resolved" (re-resolve on next access), reserving the cache for a genuinely-resolved value. Boot-order is the trap: the cache is correct in the steady state and wrong only across the wiring boundary. Source: project-rag.

## Safety thresholds — display and early-warning must read the armed value, not recompute it

**An armed safety threshold's display UI and early-warning logic must read the value that is *actually in force*, not independently recompute the same formula.**

When a threshold is computed at arming time and stored (e.g. in config, a registry key, a constants file, or passed as an argument), downstream consumers — the display widget, the approaching-threshold warning, the audit log line — must read the stored armed value. If they recompute it from the same inputs, they drift silently the moment any input changes between arming and display: the armed value stays the same (it was frozen at arm-time) but the display shows a different number. The user sees a mismatch; the early warning fires at the wrong point; an audit log shows a value that was never in effect.

**Rule:** the armed value is the single source of truth from the moment it is armed. All downstream reads must resolve to the same stored value, not to a live recomputation. Treat the stored value as an immutable fact until the next arming cycle. Independent recomputation in display code is a latent drift bug that only surfaces when inputs change mid-operation.

## Gating a per-process decision on a system-wide resource sensor — credit your own reclaimable share first

**When a per-process admission gate compares a *system-wide* resource sensor against a floor, credit back the process's own reclaimable share before comparing — or the gate penalises you for your own reclaimable cache.**

An embed-sidecar VRAM gate compared NVML *system-wide* free VRAM against a floor and 503'd spuriously: NVML counts PyTorch's caching-allocator reserved-but-unused pool as "used" (an `empty_cache()` would hand it back to the driver), so the gate treated the process's OWN reclaimable cache as unavailable. Fix: `effective_free = nvml_free + own_reclaimable` (reserved − allocated) — cross-process usage still counts against you, but your own reclaimable pool does not. Generalizes to any admission gate reading a shared/system-wide sensor (RSS vs own cache, disk-free vs own tempfiles) to decide a per-process action. (Source: project-rag.)

## Refactor-over-patch heuristics

**Structural refactors often close per-symptom bugs as a side-effect — prioritize structural fixes over bug-by-bug patches when a refactor is on the table.**
**Why:** Replacing an N-branch dispatcher with a registry lookup (each handler reading its own payload directly) eliminated an entire class of per-handler empty-default bugs in one move — no targeted per-symptom patch was needed. The same shape recurs whenever a switch/if-else cascade hardcodes shared defaults: the structural fix collapses the bug cluster, the per-symptom patches treat instances.
**How to apply:** before writing a per-symptom patch, ask whether the symptom cluster is rooted in an architectural seam the codebase already needs to fix; when yes, the structural fix is the cheaper path. The test: would the same refactor close ≥3 of the open bugs in that area? If yes, do the refactor.

*Source: example-game-repo `state/lessons/` (example-game-repo-L11, central-promoted).*

## Hardening bloat signals wrong layer

**When defensive hardening bloats past the primitive (5+ quoting or escaping lines inline), the primitive is at the wrong layer — restructure to a dispatch-script or parameterised-query pattern.**
**Why:** A security audit found 7 inherent quoting issues in a 12-line embedded-command block; restructuring to a committed shell script that receives positional args collapsed the issues to standard shell-quoting discipline.
**How to apply:** any time you add a third+ inline guard to make a call safe (quoting, escaping, encoding), stop and ask whether the call site should be a committed artifact the lint/shell pipeline can see.

*Source: example-game-repo `state/lessons/` (example-game-repo-L129, central-promoted).*

## Deprecation cycle by consumer count

**Calibrate deprecation-cycle posture to consumer count — at two consumers, direct ship; deprecation ceremony is for large populations.**
**Why:** Deprecation windows, opt-in flags, and gradual-rollout machinery assume thousands of consumers; at two consumers the same machinery is ceremony that delays a clean fix.
**How to apply:** ask "how many consumers?" before asking "what's the right posture?" At ≤2, update both call sites in the same commit and ship directly.

*Source: example-game-repo `state/lessons/` (example-game-repo-L151, central-promoted).*

## Mirror discipline, not topology

**Mirror a proven pattern's discipline, not its topology — verify the shape fits your substrate before labeling it "same as host".**
**Why:** A "mirrors host" plan label caused an executor to hunt for a phantom manifest→registry generator; the peer's manifest GENERATES its registry artifact, but the consumer's registry holds live callables that are not TOML-serializable — an inverted topology.
**How to apply:** before labeling a design "mirrors X", read X's actual code to confirm the topology (source-of-record direction, generation vs. validation, serializable vs. live) matches your substrate. The transferable part is discipline (committed derived artifact, single source of truth); the topology must be independently confirmed.

*Source: example-game-repo `state/lessons/` (example-game-repo-L211, central-promoted).*

## Reusing a helper "as-is" — existence ≠ fit; verify the SHAPE matches

**Before reusing or promoting an existing helper, verify its traversal / cap / direction / contract matches the new caller's need — not just that it exists and compiles.** Existence ≠ fit. Sister to "Mirror discipline, not topology" above (that one is about pattern *labels*; this is about a concrete helper *function* whose internal shape silently differs).

**Why:** a `tc-2` plan said "promote the `BfsExecReachable`-style exec walk"; review caught that `BfsExecReachable` is a *bidirectional, 50-node-capped* RAG-neighborhood pre-filter — the new caller (an extractor) needed a *forward-only, uncapped, topological* walk. Reusing its body would silently truncate >50-node graphs and break downstream branch reconstruction. The fix: author the walk fresh, borrow only the determinism *pattern*.

**How to apply:** read the helper's actual traversal direction, any caps/limits, and its return/raise contract against what the new call site requires. When a doc or index can't confirm an exact constant value (e.g. a member-constant literal), prefer **in-repo compiling code that already uses it** over an external lookup — shipped code is a stronger witness than a degraded RAG/index. Sister to fix-locus-discrimination and Rule 1 of `peer-port-discipline.md` (the cross-repo analog).

*Source: example-game-repo `state/lessons/` (example-game-repo-L126), central-pulled.*

## Structural-Guard Allowlist Keying — Qualname Over Line Number

**Line-number-keyed allowlists (`path:lineno`) rot on every surrounding edit — key structural-guard allowlists on a stable identifier (enclosing-function qualname) instead.**

Why: a guard keyed on `relpath:lineno` drifts silently when any edit above a call site shifts its line. On a shared concurrent-EM branch, ~10 entries can drift in a single session. A guard that breaks on unrelated edits trains everyone to blindly resync it, eroding the guard's signal entirely.

How to apply: re-key to `relpath::qualname` (with `#N` for same-function multi-calls) — stable across line moves, only changes on a rename/move (exactly when re-review is warranted). In tests, derive the key from AST scope (function/class qualname) in the walker, not from line numbers. Reserve line numbers for human-readable comments only. Prove line-independence: insert a blank line above an entry and confirm the guard stays green. (Source: project-rag L16)

## Local-Derivable Fields — Skip the Accessor

**Prefer local-cheap computation over a shell-out/RPC accessor when the field is locally derivable — the accessor is strictly worse (same answer + a subprocess), worst when called at import time.**

A shared-surface accessor is justified only for fields the consumer CANNOT cheaply compute locally (memory, disk, GPU, hostname). For frozen constants like `sys.platform` or `os.name`, routing through an accessor that shells out adds a cold-cache subprocess at module-import time to retrieve a value identical to the free local call. Generalizes the Staff Engineer's F6 (don't shell out for disk-free — `shutil.disk_usage` is a cheap local stat).

How to apply: before routing a consumer site through an upstream accessor, ask "can I compute this locally for free?" — if yes (frozen constant), use the local form. Reserve the accessor for genuinely remote/expensive fields. (Source: project-rag L22)

## Observability — Armed Threshold Display Must Read, Not Recompute

**An armed safety threshold's display / early-warning path must READ the armed value, not independently recompute it.**

Two independent computations of "the limit" silently diverge: the daemon watchdog arms at `resolve_daemon_cap_bytes()` (24 GiB), but `/health` recomputes via `resolve_ceiling_bytes()` (0.5 × commit-limit = 176 GiB) — so `/health` reports a 176 GiB ceiling that never fires and an "early-warning" at 141 GiB *above* a 24 GiB death: a dead leading indicator. The code's own docstring asserted `soft ≤ hard`; the display path simply never received the armed value.

How to apply: when a guard arms a threshold, stash it (module global / passed param) and have the observability path consume that same value — never let `/health`-style surfacing re-derive the limit from first principles. Composes with the existing § Safety thresholds rule above. (Source: project-rag L112)

## Silent-Swallow `except Exception: pass` Is the Highest-Leverage Bug Pattern

*Source: project-rag-ue-addon. [universal]*

A bare `except Exception: pass` (or `except: pass`) inside a long-running pipeline or orchestrator silently converts real failures into invisible no-ops. The pipeline continues, the caller sees no error, and the bug only surfaces when a downstream consumer discovers missing or corrupt output — often sessions later. The silent-swallow is the highest-leverage single-line bug class in pipelines precisely because it masks every other bug class in the same execution path.

**Rule.** Any sweep for pipeline reliability should prioritize `except.*pass` patterns first. Narrow every bare except to the specific expected error, or log at `warning`/`error` minimum before swallowing. A `pass` in an except block in a long-running producer is a P0 candidate by default. Compose with the § Database/indexer correctness `INSERT OR REPLACE` + post-COUNT rule: both are "appears to succeed, silently fails to write" shapes.

## Selective-Fix at the Orchestrator Seam, Not Per-Cluster

*Source: project-rag. [universal]*

When an N-sibling pattern (e.g. N exception-catch sites, N retry loops, N path-normalizers) has a recurring bug, fixing only the cluster that surfaced leaves the pattern broken everywhere else. The fix belongs at the **orchestrator seam** — the typed exception, the shared helper, the registry entry point — not at individual probe clusters. Per-cluster fixes entrench the pattern as recurring architectural inconsistency: the next cluster regresses the moment a sweep touches it.

**Rule.** Before writing a per-cluster fix, ask whether a seam-level change closes the whole class. A typed exception replacing `except Exception: pass` across the orchestrator loop is the canonical example: one change at the entry seam, all clusters remediated.

## Sentinel and generated-artifact design

### Cross-cluster sentinel anchors must embed a content HASH via a shared token function — not the raw identity string

*example-game-workbench-repo.* [universal]

A cross-cluster sentinel or anchor that must survive human-authored free text must embed a delimiter-safe content HASH via a SHARED token function that BOTH the producer and the consumer call — never the raw identity string.

A sentinel that embeds a free-text identity tuple (e.g. `NodeTitle`, which users can name `Set @@HOLODECK-BODY:foo@@` or include `:` / newlines in) allows field-split corruption or false-sentinel injection when the identity contains delimiter characters. Fix: the sentinel payload is a hex content-token (`[0-9a-f]+`) produced by a single shared `SentinelToken(Id)` function — the free text never reaches the emitted line, only its hash.

**How to apply:** for any generated-artifact marker keyed on an identity that carries user-editable free text, hash the identity through one shared function (not two independent stringifications), anchor matches whole-line prefix-to-EOL (never substring), and add a hostile-input round-trip test (a name containing `:`, newlines, and `@` chars). Sister to detect-then-fail-loud.

### A fail-loud sentinel emitted into source must be a compile-BREAKING token, not a C-comment — the preprocessor strips comments before the parser sees the type position

*example-game-workbench-repo.* [universal]

When a code-generator emits a sentinel into source to signal an unresolved/unmapped case, the sentinel must be a compile-BREAKING token (an invalid identifier that surfaces verbatim in a compiler error), not a C-style comment. The preprocessor strips `/* */` and `//` comments before the compiler sees the type position, so a `/*SENTINEL*/` in a type slot silently vanishes — yielding a typeless declaration with NO mention of the sentinel in the error: the opposite of fail-loud.

**Example:** `ResolveCppType` returning `/*HOLODECK-UNMAPPED:<cat>*/` as a `UPROPERTY` type emits nothing in the compile error. Fix: return `EXAMPLE_GAME_REPO_UNMAPPED_<cat>` (non-identifier chars replaced with `_`), which surfaces verbatim in an "undeclared identifier" error.

**How to apply:** when a sentinel's purpose is to BREAK a downstream compile or parse step, make it a token that survives into the parser's error output (an invalid identifier or a `#error` directive), not a comment or whitespace the toolchain discards before the failure point. Sister to detect-then-fail-loud.

## Generated-artifact freshness gate — existence is necessary but not sufficient

*coordinator; hazard/reference re-anchored.* [universal]

A tool whose runtime correctness depends on a gitignored (or otherwise not-directly-consumed) generated artifact — `dist/`, `build/`, compiled bindings, generated schema files, a vendored/cached copy of a source-of-truth, an out-of-tree deploy of a bin/lib tree — must check **freshness**, not just existence, and fail loud with a remediation when the check comes up stale or ambiguous. The freshness *signal* is mechanism-agnostic — an mtime comparison, a content hash, or a version/contract-version pin all satisfy the requirement — what matters is that *some* signal is checked and that absence or mismatch fails loud rather than silently degrading to "use whatever's there."

**Why:** A fresh checkout/install and an existing working tree diverge in opposite ways. Right after provisioning, existence check passes and freshness holds. After the source changes without a corresponding rebuild/redeploy, existence check still passes but the artifact is stale — the consumer either fails with opaque downstream errors ("unknown entity", "type mismatch") or, worse, silently keeps using the stale copy with no error at all. Existence is necessary but not sufficient.

**Anti-pattern (historical/synthetic — illustrates the shape to avoid, not a live citation).** A presence-only idempotency guard standing in for a freshness check looks like this:
```python
shim = claude_home / "bin" / "resolve-coordinator-clone"
if shim.is_file() and os.access(shim, os.X_OK):
    return 0
```
If an older deploy emitted the shim and its format/content has since changed upstream, this guard is satisfied by the *stale* shim and returns immediately — never re-invoking the refresh logic that would otherwise catch the drift. The lesson: a presence check standing in for a freshness check is the defect, independent of whether any particular instance is live.

`coordinator/hooks/scripts/bootstrap-substrate.py` does not exist — it was the last live instance of this exact anti-pattern before it was deleted as orphaned dead code (PM-authorized delete-vs-keep ruling: the SessionStart hook was orphaned by the full-kill directive and nothing invoked it). The freshness-inventory audit (`state/audits/2026-07-21-generated-artifact-freshness-inventory.md`) confirms the `coordinator/{bin,lib,hooks,skills}` tree carries **no live presence-only hazard instances**. Whether this hazard class warrants a shared runtime primitive (vs. staying a per-site review lens) is ratified in `docs/decisions/DR-078-freshness-gate-per-site-not-runtime-primitive.md` — per-site, not a runtime primitive.

**Reference implementation (gate done right) — claude-klabauter `coordinator/bin/sync-cockpit-contract.py` (formerly `.sh`, lines ~90–113 of the pre-port script).** Vendor-sync staleness check between the canonical `cockpit-contract.schema.json` and a consumer's vendored copy:
```bash
if [[ ! -f "$VENDORED" ]]; then
    echo "DRIFT: vendored schema not found at: $VENDORED" >&2
    exit 1
fi
VENDORED_VERSION="$(jq -r '.version // empty' "$VENDORED")"
...
if [[ "$CANONICAL_VERSION" == "$VENDORED_VERSION" ]]; then
    echo "in sync (v${CANONICAL_VERSION})"; exit 0
else
    echo "DRIFT: canonical v${CANONICAL_VERSION} vs vendored v${VENDORED_VERSION} — re-vendor and regen" >&2
    exit 1
fi
```
The freshness signal here is a **version pin**, not an mtime comparison — and the contrast with the anti-pattern above is the pedagogical point of the pairing: a *missing* vendored copy is treated as `DRIFT` / exit 1, the same hard-fail path as a version mismatch, never a silent skip. Presence alone is never deemed sufficient; the exact inverse of `bootstrap-substrate.py`'s presence-satisfies-everything guard.

**Other live examples showing the range of valid freshness signals** — the mechanism varies, the invariant (some signal checked, mismatch/absence fails loud) doesn't: claude-klabauter `coordinator/bin/check-install-divergence.py:178–196` compares git blob SHAs via `git hash-object --path <relpath>` (content hash, not mtime); claude-klabauter `coordinator/bin/migrate-bug-backlog.py:380–386` compares a dry-run artifact's `os.path.getmtime()` against a `--stale-hours` threshold (classic mtime gate). A third pattern designs the hazard out entirely rather than gating it: claude-klabauter `coordinator/bin/repomap/generate-repomap.py:1209` keys its parse cache as `f"{rel}:{content_hash}"` (`generate-repomap.py:1459`) — staleness is structurally impossible because a changed file simply misses the cache under its old key, no comparison step required.

**How to apply:** (1) identify the freshness signal available for the artifact in question — mtime-vs-source, content hash, or a version/contract-version field are all valid, pick whichever the artifact already carries or can cheaply carry; (2) treat a missing artifact and a stale/mismatched artifact as the same failure class (both fail loud with the regeneration command), never let "present" alone short-circuit past a staleness check; (3) wherever a presence-only idempotency guard stands in for a freshness check, that guard is exactly the anti-pattern this section warns about.

**`bin/lib/validate-cockpit-record.mjs` does not exist** — formerly cited here as a live existence-but-not-freshness gap, it was removed along with the whole cockpit-contract TS/node/Zod toolchain it validated against.

**`bin/emit-cockpit-snapshot.sh` does not exist** — formerly cited here as the reference implementation (the `find src -newer dist` mtime-gate pattern), it was removed along with its cockpit-contract Node/TS toolchain; its Python replacement carries no equivalent freshness gate. Superseded above by `sync-cockpit-contract.sh` as the reference implementation, using a version-pin signal instead of mtime.

## Related

## best-effort try/except with pre-guarded callee catches only real failures — narrow the swallow

A best-effort `try/except` whose only benign failure is already guarded inside the callee only ever catches REAL failures when the swallow fires. Swallowing broadly (bare `except Exception`) masks contract drift. Apply: before writing a try/except, enumerate what the callee's benign cases are and whether they're already handled inside. If yes, narrow the `except` to the specific exception class that represents genuine transient failure; any broader swallow is silently masking bugs.

## Hardening doctrine in one document does not cleanse downstream surfaces

Hardening a rule in a wiki or CLAUDE.md does not automatically cleanse downstream surfaces (agent prompts, skill SKILL.md files, hook scripts, executor briefs) that may still carry the old pattern. Ratification opens a contact-point sweep, not closes it. Apply: after any DR or wiki-hardening commit, enumerate downstream contact-points with `grep -r <old-pattern>` and edit them in lockstep, OR file a tracked cleanse stub in the improvement queue before claiming the hardening is done.

## Closed-Set Frozenset Duplication — Import Canonical, Never Re-Declare

A manually-duplicated closed-set frozenset will drift. When one stale copy is found, grep for ALL copies before fixing. The real fix is to import the canonical definition, not re-declare it at the use site. Apply: any frozenset that defines a closed set (enum-like values, allowed type names) must have exactly one declaration site; all other uses import from that site.

## Chronic-Warning Anti-Pattern — Benign Conditions Must Be Silent

A guard that warns on every run for an expected-benign condition is a defect, not tolerable noise. Chronic warnings train agents and humans to ignore warnings, so when a real drift occurs, it goes unnoticed. The fix is to make the condition conditional on genuine drift (e.g., check if the value actually changed), not to suppress the warning entirely. Apply: any warning that fires on every run without a corresponding user action needed must be made conditional.

## Deletion-Boundary Sentinels Must Match All Top-Level Constructs

"Next top-level construct" sentinel patterns for deletion-range detection must match ALL top-level construct forms: `^(def |class )` alone is insufficient. Also match `^[A-Z_]+\s*[=:]` (module-level assignments and annotated assignments), `^# ---` (section headers), and `^(import |from )` (imports). Missing sentinels cause deletion ranges to over-consume into the next construct. Apply: whenever authoring or reviewing a deletion-boundary sentinel regex, verify it handles all five construct forms.

## Schema `required` Audit — Every Required Field Must Name Its Consumer

**Before adding an entry to a schema's `required` set, name its consumer and what breaks if the field is absent. No answer means demote to optional.**

A "required" field defended only by "the schema says so" is stub-bait: it manufactures conformance debt with no safety return. The symptom is a `required` entry that no reader actually consumes — the chain-walker ignores it, downstream tooling skips it, and conformance is enforced only at schema-validation time against producers who are forced to supply a value that goes nowhere.

**Empirical origin (agent-install-contract).** The install contract made `doctor_skill` REQUIRED, but no reader consumed it (the chain-walker ignored the field; deep-research shipped it pointing at a never-existent `/deep-research:doctor`). Requiring it bought zero safety and forced a do-nothing conformance stub whose bare name collided with Claude Code's native `/doctor`. Reversing the Staff Engineer's F1 (which correctly conformed to the schema-as-written) revealed the defect was the requirement, not the conformance.

**How to apply.** When auditing any contract/config schema — plugin manifests, coordinator schema, frontmatter specs, JSON schemas — for each entry in `required`:

1. Name the consumer (which parser, walker, tool, or CLI reads this field at runtime).
2. Name what breaks if the field is absent (schema validation is not an answer — the question is whether the *runtime* breaks).
3. No concrete answer to (1) or (2) → demote to optional. Keep the property definition so repos that genuinely use the field can still declare it; removing it forces those consumers to break their contract.

The inverse also holds: a property that IS consumed by runtime tooling belongs in `required` even if it feels optional — the `required` set is a machine-readable contract, not a style preference.

*Folds with the § Validator Design rule "a membership validator allowlists the valid token SHAPE" — both warn against validators that enforce a constraint whose safety value hasn't been traced to a runtime consumer.*

- This wiki's own § Cross-cutting standards — the cross-cutting flat-bullet rules (formerly `coordinator/CLAUDE.md` § Implementation Standards)
- `docs/wiki/test-design-discipline.md`
- `docs/wiki/cleanup-sweep-hazards.md`
- `docs/wiki/oom-reproducer-strategy.md`
- `docs/wiki/document-bloat-trim.md` — extraction doctrine
