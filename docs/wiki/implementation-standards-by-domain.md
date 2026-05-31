---
system: implementation-standards-by-domain
last_updated: 2026-05-07
status: living
provenance: extracted from coordinator/CLAUDE.md § Implementation Standards Cluster 3 sub-headings (2026-05-07)
---

# Implementation Standards by Domain

> **The rule.** Domain-specific implementation standards live here. The flat-bullet rules in coordinator/CLAUDE.md § Implementation Standards cover cross-cutting standards every session should grep on boot. Domain-specific rules (observability contracts, database/indexer correctness, dependency management, engine plugin packaging) live in this wiki — they're high-value when you hit the failure mode in that domain, but pay no boot tax.

## Why this exists

Coordinator CLAUDE.md is read at every session boot. Domain-specific standards (observability, DB/indexer, dependency, engine plugin) apply only when working in that domain — the other 95% of sessions don't need them in context. Promoting them to a wiki keeps the doctrine intact, greppable when relevant, and out of the boot path.

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

## Structured-config write primitives (TOML / JSON / YAML / ini / frontmatter)

Write primitives that mutate structured-config formats fail in a class the text-search eye misses: the write lands somewhere the *reader* won't look. The unifying discipline is round-trip verification against the reader's resolution logic — see also the schema CHECK enum-widening rule under DB/indexer (DDL-on-create vs migration-on-upgrade is the same write-lands-in-the-wrong-place asymmetry, applied to schema).

- **A write primitive that mutates structured config must round-trip-verify against the READER logic before declaring success.** Text-searching the output for the inserted token proves the bytes are present, not that the reader resolves them. The fix has three layers: (1) correct shape handling on write, (2) post-build re-parse of the emitted file, (3) a reader-equivalent resolve check (load it the way production loads it and assert the value comes back). Zero-test config-mutation codepaths shipped in CLIs are the recurring smell — a mutation path with no round-trip test is unverified by construction.
- **TOML flat keys written after a `[table]` header are table-scoped, not document-root.** Appending `key = value` to the end of a TOML file places it under whatever the last `[table]`/`[[array]]` header was — so a "top-level" key inserted at EOF becomes a member of the final table. Text-search for the key passes (the literal is in the file); the reader's document-root lookup fails (it's nested). For a true top-level key, insert it *before the first `[table]` header*. This is the canonical example of why round-trip-against-reader (above) is non-optional for TOML writers.

## Dependency management

- **Dependency-CVE triage reconciles against the committed lockfile resolution, not the shared system env.** A `pyproject.toml`/manifest floor does not bind until the lockfile is regenerated — a vulnerable transitive version can still be the *resolved* one even after the floor is bumped. Triaging against `pip list` / the ambient venv reports whatever happens to be installed on this box, which may be newer (false-clear) or older (false-alarm) than what the lockfile pins for everyone else. Read the committed `uv.lock` / `poetry.lock` / `requirements.txt` resolution, and require a lock-regen step in the same change that bumps the floor.
- **Vendor with a mechanical SHA pin, not a doc-only policy.** A pinned SHA is machine-verifiable and survives doc drift; a policy note in a README is not enforceable at build time.
- **Substrate pins belong in `pyproject.toml` / `setup.cfg` / declared manifest, NOT in installer scripts.** Python version, library minimum, CUDA variant, and similar substrate constraints belong in the declared package manifest where every tool (pip, uv, build systems, CI) sees them. Installer-side pins drift from manifest and silently install the wrong substrate when called out-of-band (direct `pip install`, editor-driven venv creation, sibling repo bootstrap).
- **Bash scripts shelling to Python MUST resolve the interpreter via `PYTHON_BIN` env-var or a shared `bin/lib/resolve-python.sh` helper**, not hard-coded `python` or `python3`. Resolution order: explicit `PYTHON_BIN` env → repo-local venv → system. Hard-coded `python` picks up whichever interpreter `$PATH` happens to expose, which on shared machines (Windows + WSL, multi-version dev boxes) is rarely the one the script was authored against.
- **An automated manifest edit (version bump, dep floor) via shell must end with a parse gate before the release commit lands.** A `sed`/`grep`/`echo` redirection that touches `pyproject.toml`, `package.json`, or similar can silently inject stray stdout into the file body — the write appears to succeed, the manifest is malformed, but green local state on the authoring disk is not a parse check. Gate: `python -c "import tomllib; tomllib.load(open('pyproject.toml','rb'))"` (or JSON/YAML equivalent) immediately after the edit, before the commit. *2026-05-26, project-rag.* The v0.8.0 `/workweek-complete` version bump piped a shell-output line (`0.7.0 line found`) into `pyproject.toml:7`, breaking TOML parse → all pytest/pip/build failed on `origin/main` and shipped that way unnoticed. Belongs in the `/workweek-complete` version-bump step.

## Ship-complete — no degraded-mode evasion

**A long-running orchestrator must be idempotent across completed sub-phases, not just per-shard within a phase.** Every sub-step that produces a durable artifact must guard its execution on absence of that artifact — a 4-line `if [ -f $OUT/$src.sqlite3 ]; then skip; fi` turns O(N × source-time) recovery cost into O(1 × source-time). "Resumable" in handoffs often means per-shard within a source; cross-source resume requires explicit artifact-absence guards. When a step fails at position N, recovery must not re-extract N-1 hours of completed work. (Source: project-rag-ue-addon L83)

These two share a shape: a partial or degraded deliverable presented as if it were the real thing. The OOS test from coordinator/CLAUDE.md § Implementation Standards ("name the irreversible cost, not the appetite") applies — but these are the specific execution-time forms.

- **Deferred-remediation banners on validators are time bombs — ship the gate plus the cleanup together, or ship the gate advisory-only.** A validator that hard-fails while emitting "TODO: clean up the N pre-existing violations later" is a landmine: the next contributor trips the gate on work they didn't author, and the deferred cleanup never happens. Either land the gate *and* the cleanup of existing violations in the same change (so the gate enforces a clean state from commit one), or land the gate in advisory/WARN mode until the cleanup lands. A blocking gate with a deferred-cleanup banner is incomplete work wearing a completion banner.
- **A degraded demo shape is an evasion, not a substitute.** When the real target proves infeasible at execution time, swapping in a stripped-down "demo" target that technically runs but doesn't exercise the capability is the same incompleteness pattern as the deferred-cleanup banner — it ships a green signal over an unproven feature. Find a real target (the right shape is "what would actually prove this works?") and get PM acknowledgement of the substitution before treating the degraded run as evidence.

## Engine plugin packaging

- **UE plugin distribution mode determines DLL load location.** `AdditionalPluginDirectories` (engine-managed) and project-local plugin paths load from different directories; conflating the two produces inverted directional rules. Verify distribution mode before writing any DLL-path logic.

## Shell

- **Python stdout via `read -r` on Windows carries CR; strip it.** Patterns of the shape `read -r VAR1 VAR2 < <(python -c '...print(...)')` on Git Bash silently capture `"VAR\r"` — downstream comparisons like `[[ "$VAR" != "Write" ]]` are unexpectedly true and `bash -x` traces are misleading (the trace shows both operands of `&&` inside `[[ ]]`, making short-circuit look broken when the real defect is the trailing CR). Diagnostic: `echo -n "$VAR" | xxd` to confirm the trailing `0d`. Fix: pipe Python output through `tr -d '\r'` before `read`. Greppable signature for review: `read -r ... < <(... python ...)` without a `tr -d '\r'` somewhere in the chain. `set -uo pipefail` does not catch this.

- **Bash → other-interpreter interpolation is the dominant P1 injection family.** `node -e "$VAR..."`, `python -c "...$VAR..."`, `sed "s/x/$VAR/"`, `pwsh -Command "$VAR..."` are all silently corruptible when `$VAR` contains `'`, `"`, `$`, `&`, `/`, or `\`. Default authoring posture: pass values through argv (`node -e '...' -- "$VAR"`), env vars (`VAR="$value" python -c "...os.environ['VAR']..."`), or a `printf '%s' | sed ...` chain with a pre-pass escape. Every occurrence of `-e "...$"`, `-c "...$"`, or `s/.../$VAR/` in a shell script is a code-review candidate. The pattern looks harmless on controlled input and fails catastrophically on user-supplied or path-derived values containing special chars.

- **`cmd || rc=$?` that logs failure but never `exit $rc` is a doctrine-shaped REQUIRE-mode bug.** When a helper's return-non-zero contract is "only in REQUIRE mode" (`X_REQUIRE_Y=1 → hard-fail; default → warn-and-continue`), the caller's exit propagation is doing *all* the REQUIRE-mode enforcement. `cmd || _rc=$?; status_log fail` captures and clears the failure — the rest of the script proceeds even under `set -euo pipefail` because the `||` swallows the non-zero exit. Bug is invisible in normal runs (rc=0 short-circuits) and invisible in default-mode failures (no non-zero rc returned); only the rare REQUIRE-mode-and-failing path surfaces it, which by definition is a CI-edge case. Two-line fix: `if [[ $_rc -ne 0 ]]; then status_log fail; exit "$_rc"; fi`. Greppable: `rg -n '\|\| [_a-z]+_rc=\$\?' scripts/` then check each match for matching `exit "?\$.*_rc` within ~6 lines. Folds with the "test that passes for the wrong reason is functionally equivalent to no test" pattern.

## Comment provenance and primitive layering

All three rules below share a shape: comments-as-stories don't age well; structured citation does. When in doubt, lift the explanation out of the comment and into a commit message + commit-SHA pointer, or delete the comment entirely.

- **When defensive hardening bloats past the primitive, the primitive is at the wrong layer.** A guard pile that grows comment-per-edge-case ("handle case X", "but watch out for Y", "Z is also valid when …") is the symptom; the cause is that the primitive sits below the layer where those distinctions exist. Refactor up — move the primitive to the layer that has the type, the schema, or the context to express the distinction structurally. Each new guard added in place is debt; the primitive is misplaced. Applies to any embedded-language pattern (shell-in-JSON, SQL-in-JS, regex-in-config) where the host language can't see the embedded structure.

- **Dated bug-fix narrative comments are frozen-in-time stories.** `// 2026-04-09 — fixed crash when foo is null because bar` reads well in the review but ages into a fossil the moment the surrounding code is refactored. The comment now points at a fix that no longer exists, against a bug that no longer reproduces, in a code path that no longer runs. Prefer a commit-SHA citation in the commit message + (when truly needed in-line) a one-line `// see commit <sha> — <subject>` pointer; the SHA stays valid even when the narrative goes stale. Migrations and refactors should not have to update comment prose to remain truthful.

- **"Empirical verification" comments without provenance age into folklore.** A comment that says "tested empirically, this works" or "verified — N is the right limit" with no test file, no dated run-log, no benchmark artifact cited is folklore the moment its author leaves. The next reader has no way to re-verify and no signal whether the claim still holds. Either cite a test/log path (`see tests/perf/foo_test.py::test_n_limit, run 2026-05-12`) or omit the comment and let the test be the documentation. A code comment that asserts an empirical fact without a verifiable pointer back to the verification is worse than no comment — it stops future readers from re-checking.

## Python

- **Module-top unconditional cross-package imports break graceful-fail at port-out boundaries.** A top-level `from sibling_pkg import X` raises at module load time when the sibling package is absent — it fires before any `try/except` in `__init__` paths can catch it. This defeats every lazy-degradation strategy and turns an optional dependency into a hard one. Guard with function-scoped imports (`def foo(): from sibling_pkg import X; ...`) or a sentinel-import pattern (`try: import sibling_pkg as _sp except ImportError: _sp = None`) with lazy-use at call sites. Applies equally to optional C-extension imports (e.g. `pynvml`, `torch`) that should fail gracefully when absent.

## Validator design

- **A membership validator allowlists the valid token SHAPE and checks the allowlist only on shape-matches — never collect-everything-then-reject-non-members.** A validator enforcing "every token must be one of this small enumerated set" has two implementations: (a) match the *shape* of a candidate token (the bracket/sigil/grammar that marks it as in-scope), then check only shape-matches against the allowlist; or (b) collect every token in the file and reject any not in the set. Shape (b) is a denylist in disguise — it grows a false positive for every new convention (a new bracket type, a new comment marker, a new directive) the validator never anticipated, so the validator breaks the moment the surrounding language gains a feature. Allowlist the shape, scope the membership check to shape-matches.
- **Per-write validation hooks validate the delta, not the reconstructed whole file.** A hook firing on each write should check the change being made, not re-scan the entire reconstructed file — re-scanning re-litigates pre-existing content the write didn't touch and turns every edit into a whole-file gate.
- **Overlapping skip-lists answer different questions — run a semantic check before SSOT-consolidating them.** Two skip/exclude/ignore lists that overlap in entries are not automatically duplicates to merge into one source of truth. Ask what question each list answers (e.g. "skip from indexing" vs "skip from linting" vs "skip from the dirty-tree gate") before consolidating — collapsing two lists that share entries but answer different questions silently changes behavior for the entries unique to one list.

## Cross-cutting design

- **Avoid value-type polymorphism when fixing shape-divergence bugs.** If a function returns `str | list[str]` because callers disagree on shape, and you're fixing a bug caused by that divergence, don't paper over it with an `isinstance` gate — that re-creates the bug class the fix was meant to eliminate. Prefer a canonical-shape representation with explicit conversions at boundaries (e.g. always return `list[str]`, normalize at ingestion). Polymorphic value types are a hidden precondition contract that propagates indefinitely.

- **Override-flag defaults should fail-loud, not legacy-compat.** When adding an opt-in or opt-out flag to behavior that previously had no flag, choose the default whose failure mode is *visible*. Replace-by-default silently drops data; augment-by-default consults one extra source (visible in output). The legible failure is almost always the safer default. Generalizes broadly: API design (additive vs. replacing semantics), feature-flag defaults on new capabilities, config-schema migrations where the old path is now one of N options, override-mode semantics. When in doubt, ask "which default mode would a developer notice immediately if wrong?" — that's the right default.

## Named contracts vs incidental flags

- **A workaround that relies on a flag's incidental name/value** (e.g. piggy-backing on `--legacy-compat` to enable an unrelated behavior) is not a solution — it's debt the next refactor will silently break. Add an explicit named contract (a new flag, a constant, an env var) when the behavior is intentional.

## Shared-layer read/write conflation

- **A shared-layer constructor that is both a read and a write path (e.g. `chromadb.PersistentClient`) should not receive a pattern-match guard at construction time** — that guard blocks legitimate read callers who happen to pass through the shared constructor. Ownership data and caller-inference belong at a WRITE-ONLY seam (the path that actually mutates state), not at the shared constructor that reads and writes share. When adding a guard to prevent unauthorized writes, locate the guard at the point where the write diverges from the read path. (Source: 2026-05-24 project-rag)

## Gate on Discriminating Signal, Not Coarse Aggregate

- **A new capability must gate on its own precondition, never inherit the legacy guard of the code it was bolted onto.** The inherited guard silently defeats the new capability's primary use case. When a feature is added to a seeder whose existing job was finding a *source clone*, gating binary-writing on `_has_ue_context` (source present) means a binary-only machine — the universal-floor consumer tier — gets no binaries written. Fix: gate on the new capability's own signal (binaries discovered), let the empty-result no-op preserve the legacy contract naturally, and update the legacy tests to mock the new input empty. **Tell:** when a feature subordinates itself to a pre-existing test to avoid touching it, the gate is wrong. (Source: project-rag-ue-addon L75)

- **When a downstream consumer needs to distinguish between multiple outcome types, gate it on the discriminating signal, not a coarse aggregate rollup.** An `OVERALL_VERDICT` flag that collapses `[PASS, WARN, SKIP]` → `PASS` and `[FAIL, ERROR]` → `FAIL` loses the WARN and SKIP distinctions that downstream consumers may need to branch on. Callers who only care about pass/fail get a simpler API; callers who need finer discrimination get a broken one. Prefer: emit the full structured result, let each consumer pick the rollup they need. If an aggregate IS needed, compute it from the structured result at the callsite rather than baking it into the producer. (Source: 2026-05-24 project-rag)

## External-CLI producers

- **A producer that shells out to an external CLI must health-gate the tool and quiet-degrade on its absence/failure — never let a missing or broken external CLI poison the whole run.** When a producer (indexer, extractor, formatter, linter wrapper) depends on an external binary (`git`, `clang`, `ripgrep`, an LLM CLI, a vendor tool), a missing/incompatible/erroring invocation must NOT abort the run or write garbage downstream. Gate at the call boundary: probe the tool once (resolvable on PATH, version compatible), and on failure emit a structured degraded-mode signal (per § Observability contracts: `logger.warning("X unavailable — feature Y disabled", extra={...})`) and continue with the feature cleanly skipped. The anti-pattern is a producer that hard-fails (or silently emits empty/corrupt output) the moment the external CLI is absent, turning an optional capability into a run-killer — and a fail-open that drops the output without any queryable trace. Composes with § Python "module-top unconditional imports break graceful-fail" (same fail-at-boundary discipline, applied to subprocess deps) and § Observability "silent fail-open is a silent no-op." (2026-05-29, project-rag.)

## Cross-repo contract discipline

- **An addon/plugin row whose field crosses into a host envelope must use the HOST's palette, not the addon's local enum.** When a sibling/addon produces a structured row the host wraps into its own envelope (e.g. `FailureCatalogRow.runtime_verdict` flowing into the host's result envelope), the field's value space is the *host envelope's* verdict palette — not the addon's richer per-probe outcome enum. Authoring the field against the per-probe enum produces values the host can't place in its envelope. Soft-probe / catalog-row authors must confirm which palette governs a cross-boundary field before populating it; dispatch briefs for new soft-probe authors should name the host palette explicitly.
- **A probe or tool that spawns a sibling's daemon directly inherits NONE of the sibling's lifecycle-manager safety.** Bypassing the sibling's lifecycle manager (its `ensure-server` / supervisor / launcher) to spawn its daemon process directly skips every guard the manager owns — park-on-idle, crash-loop breaker, resource ceilings, single-instance locking. Either route the spawn through the sibling's lifecycle manager, or replicate the manager's guard signals at the spawn site (and accept that the replica drifts from the canonical guards). Direct-spawn is a footgun precisely because it works in the happy path and fails only under the conditions the skipped guards exist to handle.
- **A one-shot resolver cache over addon/sibling-supplied substrate must lazy-re-resolve on `None`, not freeze the first (possibly pre-boot) miss.** When a resolver reads substrate another repo provides (an addon registry, a sibling's config, a hookspec-contributed value) and memoizes the first result, a resolution that happens *before* the addon substrate is wired returns `None` — and a one-shot cache then freezes `None` forever, long after the substrate becomes available. Treat `None`/empty as "not yet resolved" (re-resolve on next access), reserving the cache for a genuinely-resolved value. Boot-order is the trap: the cache is correct in the steady state and wrong only across the wiring boundary. Source: 2026-05-19 project-rag.

## Safety thresholds — display and early-warning must read the armed value, not recompute it

**An armed safety threshold's display UI and early-warning logic must read the value that is *actually in force*, not independently recompute the same formula.**

When a threshold is computed at arming time and stored (e.g. in config, a registry key, a constants file, or passed as an argument), downstream consumers — the display widget, the approaching-threshold warning, the audit log line — must read the stored armed value. If they recompute it from the same inputs, they drift silently the moment any input changes between arming and display: the armed value stays the same (it was frozen at arm-time) but the display shows a different number. The user sees a mismatch; the early warning fires at the wrong point; an audit log shows a value that was never in effect.

**Rule:** the armed value is the single source of truth from the moment it is armed. All downstream reads must resolve to the same stored value, not to a live recomputation. Treat the stored value as an immutable fact until the next arming cycle. Independent recomputation in display code is a latent drift bug that only surfaces when inputs change mid-operation.

## Refactor-over-patch heuristics

**Structural refactors often close per-symptom bugs as a side-effect — prioritize structural fixes over bug-by-bug patches when a refactor is on the table.**
**Why:** Replacing an N-branch dispatcher with a registry lookup (each handler reading its own payload directly) eliminated an entire class of per-handler empty-default bugs in one move — no targeted per-symptom patch was needed. The same shape recurs whenever a switch/if-else cascade hardcodes shared defaults: the structural fix collapses the bug cluster, the per-symptom patches treat instances.
**How to apply:** before writing a per-symptom patch, ask whether the symptom cluster is rooted in an architectural seam the codebase already needs to fix; when yes, the structural fix is the cheaper path. The test: would the same refactor close ≥3 of the open bugs in that area? If yes, do the refactor.

*Source: holodeck `tasks/lessons.md` (holodeck-L11, central-promoted 2026-05-28).*

## Hardening bloat signals wrong layer

**When defensive hardening bloats past the primitive (5+ quoting or escaping lines inline), the primitive is at the wrong layer — restructure to a dispatch-script or parameterised-query pattern.**
**Why:** A security audit found 7 inherent quoting issues in a 12-line embedded-command block; restructuring to a committed shell script that receives positional args collapsed the issues to standard shell-quoting discipline.
**How to apply:** any time you add a third+ inline guard to make a call safe (quoting, escaping, encoding), stop and ask whether the call site should be a committed artifact the lint/shell pipeline can see.

*Source: holodeck `tasks/lessons.md` (holodeck-L129, central-promoted 2026-05-28).*

## Deprecation cycle by consumer count

**Calibrate deprecation-cycle posture to consumer count — at two consumers, direct ship; deprecation ceremony is for large populations.**
**Why:** Deprecation windows, opt-in flags, and gradual-rollout machinery assume thousands of consumers; at two consumers the same machinery is ceremony that delays a clean fix.
**How to apply:** ask "how many consumers?" before asking "what's the right posture?" At ≤2, update both call sites in the same commit and ship directly.

*Source: holodeck `tasks/lessons.md` (holodeck-L151, central-promoted 2026-05-28).*

## Mirror discipline, not topology

**Mirror a proven pattern's discipline, not its topology — verify the shape fits your substrate before labeling it "same as host".**
**Why:** A "mirrors host" plan label caused an executor to hunt for a phantom manifest→registry generator; the peer's manifest GENERATES its registry artifact, but the consumer's registry holds live callables that are not TOML-serializable — an inverted topology.
**How to apply:** before labeling a design "mirrors X", read X's actual code to confirm the topology (source-of-record direction, generation vs. validation, serializable vs. live) matches your substrate. The transferable part is discipline (committed derived artifact, single source of truth); the topology must be independently confirmed.

*Source: holodeck `tasks/lessons.md` (holodeck-L211, central-promoted 2026-05-28).*

## Structural-Guard Allowlist Keying — Qualname Over Line Number

**Line-number-keyed allowlists (`path:lineno`) rot on every surrounding edit — key structural-guard allowlists on a stable identifier (enclosing-function qualname) instead.**

Why: a guard keyed on `relpath:lineno` drifts silently when any edit above a call site shifts its line. On a shared concurrent-EM branch, ~10 entries can drift in a single session. A guard that breaks on unrelated edits trains everyone to blindly resync it, eroding the guard's signal entirely.

How to apply: re-key to `relpath::qualname` (with `#N` for same-function multi-calls) — stable across line moves, only changes on a rename/move (exactly when re-review is warranted). In tests, derive the key from AST scope (function/class qualname) in the walker, not from line numbers. Reserve line numbers for human-readable comments only. Prove line-independence: insert a blank line above an entry and confirm the guard stays green. (Source: project-rag L16)

## Local-Derivable Fields — Skip the Accessor

**Prefer local-cheap computation over a shell-out/RPC accessor when the field is locally derivable — the accessor is strictly worse (same answer + a subprocess), worst when called at import time.**

A shared-surface accessor is justified only for fields the consumer CANNOT cheaply compute locally (memory, disk, GPU, hostname). For frozen constants like `sys.platform` or `os.name`, routing through an accessor that shells out adds a cold-cache subprocess at module-import time to retrieve a value identical to the free local call. Generalizes Patrik's F6 (don't shell out for disk-free — `shutil.disk_usage` is a cheap local stat).

How to apply: before routing a consumer site through an upstream accessor, ask "can I compute this locally for free?" — if yes (frozen constant), use the local form. Reserve the accessor for genuinely remote/expensive fields. (Source: project-rag L22)

## Observability — Armed Threshold Display Must Read, Not Recompute

**An armed safety threshold's display / early-warning path must READ the armed value, not independently recompute it.**

Two independent computations of "the limit" silently diverge: the daemon watchdog arms at `resolve_daemon_cap_bytes()` (24 GiB), but `/health` recomputes via `resolve_ceiling_bytes()` (0.5 × commit-limit = 176 GiB) — so `/health` reports a 176 GiB ceiling that never fires and an "early-warning" at 141 GiB *above* a 24 GiB death: a dead leading indicator. The code's own docstring asserted `soft ≤ hard`; the display path simply never received the armed value.

How to apply: when a guard arms a threshold, stash it (module global / passed param) and have the observability path consume that same value — never let `/health`-style surfacing re-derive the limit from first principles. Composes with the existing § Safety thresholds rule above. (Source: project-rag L112)

## Silent-Swallow `except Exception: pass` Is the Highest-Leverage Bug Pattern

*Source: project-rag-ue-addon, 2026-05-28. [universal]*

A bare `except Exception: pass` (or `except: pass`) inside a long-running pipeline or orchestrator silently converts real failures into invisible no-ops. The pipeline continues, the caller sees no error, and the bug only surfaces when a downstream consumer discovers missing or corrupt output — often sessions later. The silent-swallow is the highest-leverage single-line bug class in pipelines precisely because it masks every other bug class in the same execution path.

**Rule.** Any sweep for pipeline reliability should prioritize `except.*pass` patterns first. Narrow every bare except to the specific expected error, or log at `warning`/`error` minimum before swallowing. A `pass` in an except block in a long-running producer is a P0 candidate by default. Compose with the § Database/indexer correctness `INSERT OR REPLACE` + post-COUNT rule: both are "appears to succeed, silently fails to write" shapes.

## Selective-Fix at the Orchestrator Seam, Not Per-Cluster

*Source: project-rag, 2026-05-29. [universal]*

When an N-sibling pattern (e.g. N exception-catch sites, N retry loops, N path-normalizers) has a recurring bug, fixing only the cluster that surfaced leaves the pattern broken everywhere else. The fix belongs at the **orchestrator seam** — the typed exception, the shared helper, the registry entry point — not at individual probe clusters. Per-cluster fixes entrench the pattern as recurring architectural inconsistency: the next cluster regresses the moment a sweep touches it.

**Rule.** Before writing a per-cluster fix, ask whether a seam-level change closes the whole class. A typed exception replacing `except Exception: pass` across the orchestrator loop is the canonical example: one change at the entry seam, all clusters remediated.

## Related

- `coordinator/CLAUDE.md` § Implementation Standards — the cross-cutting flat-bullet rules
- `docs/wiki/test-design-discipline.md`
- `docs/wiki/cleanup-sweep-hazards.md`
- `docs/wiki/oom-reproducer-strategy.md`
- `docs/wiki/document-bloat-trim.md` — extraction doctrine
