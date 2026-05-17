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

## Comment provenance and primitive layering

All three rules below share a shape: comments-as-stories don't age well; structured citation does. When in doubt, lift the explanation out of the comment and into a commit message + commit-SHA pointer, or delete the comment entirely.

- **When defensive hardening bloats past the primitive, the primitive is at the wrong layer.** A guard pile that grows comment-per-edge-case ("handle case X", "but watch out for Y", "Z is also valid when …") is the symptom; the cause is that the primitive sits below the layer where those distinctions exist. Refactor up — move the primitive to the layer that has the type, the schema, or the context to express the distinction structurally. Each new guard added in place is debt; the primitive is misplaced. Applies to any embedded-language pattern (shell-in-JSON, SQL-in-JS, regex-in-config) where the host language can't see the embedded structure.

- **Dated bug-fix narrative comments are frozen-in-time stories.** `// 2026-04-09 — fixed crash when foo is null because bar` reads well in the review but ages into a fossil the moment the surrounding code is refactored. The comment now points at a fix that no longer exists, against a bug that no longer reproduces, in a code path that no longer runs. Prefer a commit-SHA citation in the commit message + (when truly needed in-line) a one-line `// see commit <sha> — <subject>` pointer; the SHA stays valid even when the narrative goes stale. Migrations and refactors should not have to update comment prose to remain truthful.

- **"Empirical verification" comments without provenance age into folklore.** A comment that says "tested empirically, this works" or "verified — N is the right limit" with no test file, no dated run-log, no benchmark artifact cited is folklore the moment its author leaves. The next reader has no way to re-verify and no signal whether the claim still holds. Either cite a test/log path (`see tests/perf/foo_test.py::test_n_limit, run 2026-05-12`) or omit the comment and let the test be the documentation. A code comment that asserts an empirical fact without a verifiable pointer back to the verification is worse than no comment — it stops future readers from re-checking.

## Named contracts vs incidental flags

- **A workaround that relies on a flag's incidental name/value** (e.g. piggy-backing on `--legacy-compat` to enable an unrelated behavior) is not a solution — it's debt the next refactor will silently break. Add an explicit named contract (a new flag, a constant, an env var) when the behavior is intentional.

## Related

- `coordinator/CLAUDE.md` § Implementation Standards — the cross-cutting flat-bullet rules
- `docs/wiki/test-design-discipline.md`
- `docs/wiki/cleanup-sweep-hazards.md`
- `docs/wiki/oom-reproducer-strategy.md`
- `docs/wiki/document-bloat-trim.md` — extraction doctrine
