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

## Dependency management

- **Vendor with a mechanical SHA pin, not a doc-only policy.** A pinned SHA is machine-verifiable and survives doc drift; a policy note in a README is not enforceable at build time.
- **Substrate pins belong in `pyproject.toml` / `setup.cfg` / declared manifest, NOT in installer scripts.** Python version, library minimum, CUDA variant, and similar substrate constraints belong in the declared package manifest where every tool (pip, uv, build systems, CI) sees them. Installer-side pins drift from manifest and silently install the wrong substrate when called out-of-band (direct `pip install`, editor-driven venv creation, sibling repo bootstrap).
- **Bash scripts shelling to Python MUST resolve the interpreter via `PYTHON_BIN` env-var or a shared `bin/lib/resolve-python.sh` helper**, not hard-coded `python` or `python3`. Resolution order: explicit `PYTHON_BIN` env → repo-local venv → system. Hard-coded `python` picks up whichever interpreter `$PATH` happens to expose, which on shared machines (Windows + WSL, multi-version dev boxes) is rarely the one the script was authored against.

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

## Cross-cutting design

- **Avoid value-type polymorphism when fixing shape-divergence bugs.** If a function returns `str | list[str]` because callers disagree on shape, and you're fixing a bug caused by that divergence, don't paper over it with an `isinstance` gate — that re-creates the bug class the fix was meant to eliminate. Prefer a canonical-shape representation with explicit conversions at boundaries (e.g. always return `list[str]`, normalize at ingestion). Polymorphic value types are a hidden precondition contract that propagates indefinitely.

- **Override-flag defaults should fail-loud, not legacy-compat.** When adding an opt-in or opt-out flag to behavior that previously had no flag, choose the default whose failure mode is *visible*. Replace-by-default silently drops data; augment-by-default consults one extra source (visible in output). The legible failure is almost always the safer default. Generalizes broadly: API design (additive vs. replacing semantics), feature-flag defaults on new capabilities, config-schema migrations where the old path is now one of N options, override-mode semantics. When in doubt, ask "which default mode would a developer notice immediately if wrong?" — that's the right default.

## Named contracts vs incidental flags

- **A workaround that relies on a flag's incidental name/value** (e.g. piggy-backing on `--legacy-compat` to enable an unrelated behavior) is not a solution — it's debt the next refactor will silently break. Add an explicit named contract (a new flag, a constant, an env var) when the behavior is intentional.

## Shared-layer read/write conflation

- **A shared-layer constructor that is both a read and a write path (e.g. `chromadb.PersistentClient`) should not receive a pattern-match guard at construction time** — that guard blocks legitimate read callers who happen to pass through the shared constructor. Ownership data and caller-inference belong at a WRITE-ONLY seam (the path that actually mutates state), not at the shared constructor that reads and writes share. When adding a guard to prevent unauthorized writes, locate the guard at the point where the write diverges from the read path. (Source: 2026-05-24 project-rag)

## Gate on Discriminating Signal, Not Coarse Aggregate

- **When a downstream consumer needs to distinguish between multiple outcome types, gate it on the discriminating signal, not a coarse aggregate rollup.** An `OVERALL_VERDICT` flag that collapses `[PASS, WARN, SKIP]` → `PASS` and `[FAIL, ERROR]` → `FAIL` loses the WARN and SKIP distinctions that downstream consumers may need to branch on. Callers who only care about pass/fail get a simpler API; callers who need finer discrimination get a broken one. Prefer: emit the full structured result, let each consumer pick the rollup they need. If an aggregate IS needed, compute it from the structured result at the callsite rather than baking it into the producer. (Source: 2026-05-24 project-rag)

## Related

- `coordinator/CLAUDE.md` § Implementation Standards — the cross-cutting flat-bullet rules
- `docs/wiki/test-design-discipline.md`
- `docs/wiki/cleanup-sweep-hazards.md`
- `docs/wiki/oom-reproducer-strategy.md`
- `docs/wiki/document-bloat-trim.md` — extraction doctrine
