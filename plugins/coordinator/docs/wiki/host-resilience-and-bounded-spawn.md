---
title: Host resilience and bounded subprocess spawn
purpose: Doctrine for project-rag's three-layer OOM defense — kernel ceilings, argv capture at every spawn, and embed_sidecar self-bounding. Doctrine outlives any individual incident; every future spawn-site review touches this page.
audience: EM, executors editing any file under core/, embed_sidecar/, priming/, indexer/, scripts/ that may add a subprocess.Popen or subprocess.run callsite
last_distilled: 2026-05-14
provenance:
  - archived_spec: archive/specs/2026-05-05-belt-and-suspenders-oom-prevention.md
    original_path: docs/plans/2026-05-05-belt-and-suspenders-oom-prevention.md
    last_verbose_sha: e12fd3f4ab4e15af309ec25e469c00b2304f91f8
    distilled: 2026-05-06
distilled_from:
  - archive/specs/2026-05-07-bounded-popen-convergence.md
  - docs/plans/2026-05-13-tc-2-long-lived-subprocess-hookspec.md
  - tasks/install-chain-readiness/2026-05-08-readiness-confirmation.md
---

<!-- Imported from X:/project-rag at SHA d376cb01 on 2026-05-19. Inherited substrate; canonical lineage now in Claude Central. Origin: project-rag/docs/... — see CLAUDE.local.md "Sibling repos" for layout. -->

# Host resilience and bounded subprocess spawn

> Three-layer defense against runaway resource consumption from any project-rag spawn site (embed_sidecar, Mode B headless UE, clang structural index, install/update pip subprocesses). Companion to the holodeck `host-resource-resilience` plan; project-rag is the consumer, holodeck is the canonical author.

## The three layers

| Layer | Mechanism | Where it lives | What it catches |
|---|---|---|---|
| **1. Kernel ceiling** | `bounded_popen` wraps every long-lived `subprocess.Popen` with a Windows Job Object (`mem_max_bytes`) or POSIX `setrlimit`. Kernel terminates on breach. | `core/host_resilience.py` (vendored from holodeck) | Process committing virtual memory faster than user-space pollers can react. The "217 GB in 30 s" failure mode. |
| **2. Argv capture at spawn** | Every `bounded_popen` call logs full argv (including resolved interpreter abs-path) at INFO before Popen returns. | `core/embed_client.py:_spawn_sidecar`, `priming/producer_runner.py` Mode B, `priming/producers/structural_index_clang.py`, `embed_sidecar/app.py` torch self-test | Names the next OOM event in `Saved/ProjectRag/embed_sidecar.<pid>.log` or producer-runner log — closes the static-analysis-can't-find-it gap. |
| **3. Sidecar self-bound** | `embed_sidecar/app.py` lifespan starts a psutil RSS sampler; on `EMBED_SIDECAR_MAX_RSS_GIB` breach, sets `_self_bound_exit_reason` and raises SIGTERM → graceful drain → exit 75. | `embed_sidecar/app.py`, `embed_sidecar/config.py` | Sidecar invoked outside `bounded_popen` (debug starter scripts, manual launch) still has a ceiling. Defense-in-depth. |

## Vendoring contract — single canonical authoring source

`core/host_resilience.py` is **vendored from holodeck's `mcp_server/host_resilience/bounded_spawn.py` + `_win32_jobobj.py`**, collapsed into one file with a header citing the upstream commit SHA at vendor time. project-rag is a consumer; authoring stays in holodeck.

**Drift enforcement (mechanical, not doctrinal):**

- Header: `# Vendored from claude-unreal-holodeck/mcp_server/host_resilience/ — single canonical authoring source. Pull updates from there; do not fork.` + `# Vendored from holodeck @ <sha>`.
- `tests/host_resilience/test_vendored_helper_is_current.py`: reads recorded SHA from header, resolves canonical upstream files' current SHA via `git -C X:/claude-unreal-holodeck log -1 --format=%H -- mcp_server/host_resilience/bounded_spawn.py mcp_server/host_resilience/_win32_jobobj.py`, fails when they differ.
- Decorated `@pytest.mark.xfail(condition=not Path("X:/claude-unreal-holodeck").exists(), reason="holodeck not present on this machine")` — xfail-on-CI, PASS-required on dev machine.

**Why vendor and not probe-chain or path-on-disk import:** cross-repo coupling direction matters. Holodeck is the platform; project-rag is one of N tenants. Coupling project-rag's runtime to holodeck install presence is the wrong direction. Probe-chain has the same problem and is brittler. Vendoring is cheap (~150 LOC) and drift is greppable.

## Argv-capture-at-every-spawn rule + ALLOW_LIST policy

**The rule:** every `subprocess.Popen` and long-lived `subprocess.run` call site in `core/`, `embed_sidecar/`, `priming/`, `project_rag_mcp/`, `indexer/`, `scripts/` is either (a) routed through `bounded_popen` (which logs argv), or (b) on the explicit ALLOW_LIST in `tests/host_resilience/test_spawn_helper_coverage.py` with a one-line `accepted-risk-with-reason` rationale, or (c) a test failure.

**Enforcement:** AST coverage test resolves import aliases and matches both `subprocess.Popen` and `subprocess.run` (both are long-lived spawn surfaces; the test must catch either form). Run as part of `tests/host_resilience/`.

**ALLOW_LIST seed (short-lived call sites that don't need bounding):**

| Site | Rationale |
|---|---|
| `scripts/_update_runner.py:81` | Update verb pip subprocess; transient runtime; redirected to log |
| `scripts/install_project_rag_plugin.py:865` | Installer pip subprocess; transient; redirected |
| `scripts/staleness_survey.py:149/168` | Read-only inventory probe |
| `scripts/extract_structural_index.py:1092` | Wraps clang invocation; bounded at clang spawn site instead |
| `embed_sidecar/app.py:484` | Torch self-test, `subprocess.run(timeout=90)`; kill-on-timeout already enforced; argv logged at INFO before call |
| `priming/producer_runner.py:805` (UnrealEditor-Cmd.exe) | Mode B headless UE; mid-cook kill is destructive; matches holodeck's accepted-risk-with-reason; argv logged |

**Adding a new long-lived spawn site:** route through `bounded_popen` with a generous-but-real ceiling (8 GiB for clang-class processes; `EMBED_SIDECAR_MAX_RSS_GIB` for sidecar-class). Ship the wiring + the AST test pass in the same commit. Do NOT add to ALLOW_LIST without `accepted-risk-with-reason` documented on the same line.

## Why argv-capture is load-bearing

The 217 GB recurring `python3.13.exe` event sits in a regime where static analysis is exhausted. Five candidate hypotheses survived; static analysis cannot distinguish them. **Two lines of code per spawn site** (`logger.info("spawn <name>: argv=%s mem_max_bytes=%d", argv, mem_max_bytes)`) name the offender on the next event — file:line, interpreter abs-path, full argument list, working directory if relevant. The argv line is the contract for "the next OOM event names itself in the log."

## Embed sidecar self-bound — the 75 exit code

`embed_sidecar/app.py` lifespan starts an asyncio task that polls `psutil.Process().memory_info().rss` every `EMBED_SIDECAR_RSS_POLL_SECONDS` (default 10). On RSS > `EMBED_SIDECAR_MAX_RSS_GIB` (default 16):

1. Log reason: `self-bound RSS ceiling exceeded: %.2f GiB > %.2f GiB; graceful self-exit`.
2. Set module-level `_self_bound_exit_reason` flag.
3. `signal.raise_signal(signal.SIGTERM)` → uvicorn's existing graceful-drain path → lifespan-teardown.
4. Lifespan teardown reads `_self_bound_exit_reason` and exits with code **75** instead of default 0.

**Why 75 (not 1, not 0)?** It distinguishes self-bound from kernel-bound at post-mortem time. The kernel-bound exit signal is `STATUS_QUOTA_EXCEEDED` (0xC0000044) on Windows or SIGKILL on POSIX. Exit 75 means "I noticed I was approaching the ceiling and exited gracefully"; the kernel exit means "the kernel terminated me." Different evidence trails; different next-step diagnostics.

**Why `signal.raise_signal(SIGTERM)` and not `sys.exit(75)` directly?** `sys.exit` from an asyncio task is unreliable — `SystemExit` is swallowed by the asyncio event loop. The signal-and-graceful-drain pattern matches `_idle_watchdog_tick` at `app.py:365` and is the established lifecycle hook.

**Configuration:**

- `EMBED_SIDECAR_MAX_RSS_GIB` (default 16) — chosen permissive; well above CodeRankEmbed's working set.
- `EMBED_SIDECAR_RSS_POLL_SECONDS` (default 10).
- Per-poll instrumentation: `logger.info("embed batch peak RSS: %.2f GiB", peak_rss_gib)` so future telemetry can validate the 16 GiB ceiling.

## BREAKAWAY_OK upstream gap (open, tracked)

Win10/11 supports nested Job Objects at the OS level, but `AssignProcessToJobObject` returns `ERROR_ACCESS_DENIED` when the parent process is itself in a job that lacks `JOB_OBJECT_LIMIT_BREAKAWAY_OK` and the child is not launched with `CREATE_BREAKAWAY_FROM_JOB`. This affects:

- GitHub Actions Windows runners (jobbed)
- Windows Sandbox
- Potentially Windows Terminal (ConPTY) under some sandbox policies

**Holodeck's helper does NOT currently probe `BREAKAWAY_OK` on the parent job.** This is an upstream gap. project-rag is a consumer, not an author — the gap is filed against the holodeck plan; the SHA-pin test catches when the upstream fix lands and triggers a re-vendor.

The project-rag dev machine is not jobbed at the parent level (typical interactive shell), so W2 ships with this gap accepted. Surface this in CI failures and reviews of new spawn sites that might run inside a CI sandbox.

## Tripwires for editing this surface

- **Adding a `subprocess.Popen` or long-lived `subprocess.run` call** in `core/`, `embed_sidecar/`, `priming/`, `project_rag_mcp/`, `indexer/`, `scripts/`: the AST coverage test (`tests/host_resilience/test_spawn_helper_coverage.py`) will fail. Either route through `bounded_popen` or add to ALLOW_LIST with rationale.
- **Editing `core/host_resilience.py`**: STOP. The file is vendored. Either pull from holodeck (re-vendor) or file the change against the holodeck plan and let it flow back. Do NOT fork.
- **Touching `embed_sidecar/app.py` lifespan**: respect the `_self_bound_exit_reason` + signal-raise pattern; don't replace with `sys.exit` from inside the asyncio task.
- **Adding a `*_MIB` / `*_GB` / `*_GIB` constant** in any audited package: the AC-4 declaration-multiplier audit (`tests/host_resilience/test_no_unit_mismatch_in_size_constants.py`) will fail if `value × unit_multiplier` exceeds `2 × total_system_memory`. The audit catches declaration mismatches; interpretation mismatches (a `*_MIB` constant correctly declared but consumed at a call site as bytes) require AC-3 argv evidence on the next event.

## Cross-repo migration recipe — current state

> **Audit summary (2026-05-07, WS-1 of multi-rag-coexistence-prep):** the multi-rag-coexistence research corpus axis-4 §H proposed inverting the canonical authoring direction of `bounded_popen` (project-rag → holodeck). That proposal was empirically wrong. The vendoring contract documented above already runs the *correct* direction (holodeck → project-rag), and convergence is structurally satisfied today. No new convergence work is required; corpus axis-4 §H has been corrected (see `docs/research/2026-05-07-multi-rag-staff-session/bounded-popen-cross-repo-handoff.md`).

**Vendoring direction (canonical, do not invert):**

```
holodeck/mcp_server/host_resilience/{__init__,bounded_spawn,_win32_jobobj,_linux_cgroup,_macos_rlimit}.py
        │
        │  (vendor by SHA-pinned copy; ~150 LOC collapsed into one file)
        ▼
project-rag/core/host_resilience.py
```

**Current vendored state (verified 2026-05-07):**

| Field | Value |
|---|---|
| Vendored SHA in `core/host_resilience.py` header (line 19) | `3ae429e597a8ef225ec397015ac946605bdae1b7` |
| Holodeck HEAD SHA touching the canonical files | `3ae429e597a8ef225ec397015ac946605bdae1b7` |
| Drift | **None.** SHA matches — vendored copy is current. |
| `tests/host_resilience/test_vendored_helper_is_current.py` | PASS (1 passed, 1.29 s) on dev machine 2026-05-07 |

**Call-site inventory (verified 2026-05-07 by `grep -rn "bounded_popen\|bounded_spawn"` on each repo root):**

*project-rag* — 3 production call sites + tests:

| Location | Purpose |
|---|---|
| `core/embed_client.py:437` (`_spawn_sidecar`) | Embed sidecar launch — primary high-RSS spawn |
| `priming/producers/structural_index_clang.py:638` | clang structural-index extractor (8 GiB ceiling) |
| `core/host_resilience.py:116` (definition) | Public entry point (vendored from holodeck) |

(Plus AST-coverage test, SHA-pin test, smoke test, embed-sidecar bounded-spawn test, and three `test_embed_sidecar_client.py` fakes — non-production.)

*holodeck* — 1 production call site + module internals:

| Location | Purpose |
|---|---|
| `mcp_server/server_lifecycle.py:505` | gpu_sidecar / aux-process launch from MCP server lifespan |
| `mcp_server/host_resilience/bounded_spawn.py:71` | Public entry point (canonical authoring source) |
| `mcp_server/host_resilience/__init__.py:1` | Public re-export |
| `mcp_server/host_resilience/{_linux_cgroup,_macos_rlimit}.py` | Platform impls importing `BoundedPopen`/`SpawnPolicyViolation` |

**Why this direction (not the inverse corpus axis-4 §H proposed):**

1. **Coupling-direction matters.** Holodeck is the platform; project-rag is one of N tenants. Inverting (project-rag-canonical, holodeck-consumer) would tie the holodeck MCP server's runtime spawn behavior to whichever project-rag install happens to be on disk. Wrong direction.
2. **Author surface > consumer surface.** Holodeck has the broader spawn-call vocabulary (gpu_sidecar, future aux processes); project-rag is currently 3 sites. The richer caller-surface drives the API.
3. **The drift-detection test runs on the consumer side already.** `test_vendored_helper_is_current.py` reads the SHA from the vendored header, queries holodeck's git log, and fails on mismatch. It is xfail-on-CI (holodeck not present) and PASS-required on dev machines. This is the convergence enforcement; nothing else needs building.

**When holodeck's `bounded_spawn.py` changes:**

1. Holodeck commits land normally.
2. On project-rag dev machines, `test_vendored_helper_is_current.py` starts failing (recorded SHA != HEAD SHA).
3. Re-vendor on the project-rag side: collapse the 5 holodeck source files into `core/host_resilience.py`, update the `# Vendored from holodeck @ <sha>` line to the new HEAD, run smoke + AST-coverage tests, commit.

No two-way sync, no probe-chain, no path-on-disk import. The vendored-copy + SHA-pin pattern is the entire migration recipe.

## Long-lived subprocess hookspec (tc-2, 2026-05-13)

The tc-2 work added `project_rag_register_long_lived_subprocess` as the 7th addon hookspec. The host harness (`core.long_lived_runtime._boot_subprocess`) now owns the lifecycle for ALL long-lived daemon-style subprocesses via this hookspec:

- `bounded_popen` wrapping with memory-ceiling enforcement
- Single-instance PID lock under `<data_dir>/<spec.id>.pid` (`O_EXCL`)
- Asyncio idle-offload and process-exit watchdog (thresholds from `AddonLongLivedSubprocessSpec`)
- Doctor probe registration via `spec.doctor_probe_step_id`
- Tenant-registry write under `~/.claude/process-tenants/` (or `~/.claude/gpu-tenants/` per `spec.tenant_kind`)

**Migration impact:** the embed sidecar's spawn mechanism moved from `core/embed_client.py:_spawn_sidecar` (deleted in WS-8) to `core.long_lived_runtime._boot_subprocess`. Observable behavior is unchanged (same port, PID file, timeouts). Tests that previously patched `core.embed_client.bounded_popen` must now patch `core.long_lived_runtime.bounded_popen`.

The embed sidecar dogfoods this seam via `BUILTIN_EMBED_SIDECAR_SPEC` in `embed_sidecar/builtin_spec.py` — registered by the host directly, no addon required for built-in subprocesses.

**Addons wanting a GPU sidecar or LSP server:** return an `AddonLongLivedSubprocessSpec` from `project_rag_register_long_lived_subprocess`. The host harness handles all lifecycle mechanics; the addon supplies `argv_builder`, `env_extras`, memory ceilings, idle/exit timeouts, health URL, and doctor probe step ID. See `core/addon_protocol.py` for the full field spec.

> Distilled from: `docs/plans/2026-05-13-tc-2-long-lived-subprocess-hookspec.md` §WS-1, §WS-8; `docs/wiki/addon-protocol.md` §project_rag_register_long_lived_subprocess

## Tenant registry — `~/.claude/process-tenants/`

Every long-lived subprocess registered through the hookspec writes a tenant file to `~/.claude/process-tenants/<spec.id>.json`. This is the canonical location for cross-process process-presence assertions.

GPU-consuming tenants additionally write to `~/.claude/gpu-tenants/` (the legacy location, maintained for backward compat with holodeck's peer-offload protocol). Both paths are written atomically and read by the VRAM coordination code.

**Tenant file schema (v1):**

```json
{
  "pid": 12345,
  "started_at": "2026-05-14T10:00:00Z",
  "spec_id": "embed_sidecar",
  "health_url": "http://127.0.0.1:43841/health",
  "tenant_kind": "gpu"
}
```

**GC policy:** stale entries (PID not running) are removed lazily on next tenant-registry read. No dedicated GC daemon.

> Distilled from: `docs/plans/2026-05-13-tc-2-long-lived-subprocess-hookspec.md` §WS-5 tenant-registry

## Cross-repo SHA-pin policy (DR-DIST-cross-repo-sha-pin)

The vendoring contract for `core/host_resilience.py` (sourced from holodeck) extends to all cross-repo vendored helpers:

1. **SHA pin must reference `origin/main`** (not `work/*` or `feature/*` branches). Pinning a work branch that later rebases or gets abandoned silently invalidates the vendor record without a test failure.
2. **Vendor-with-mechanical-SHA-pin beats doc-only policy.** A sentence in CLAUDE.md saying "keep in sync" has no enforcement; a test that reads the SHA from the file header and checks it against the upstream git log catches drift automatically.
3. **Update sequence:** holodeck commits on its file → `test_vendored_helper_is_current.py` starts failing on dev machines → re-vendor (`collapse 5 files → 1`, update `# Vendored from holodeck @ <sha>`) → commit with both files in the same PR.

The SHA-pin policy originated in `archive/specs/2026-05-07-bounded-popen-convergence.md` (WS-1 direction audit, 2026-05-07) and was confirmed as the canonical direction (holodeck → project-rag) after the multi-rag-coexistence research corpus axis-4 §H proposed the inverse and was found empirically wrong.

> Distilled from: `archive/specs/2026-05-07-bounded-popen-convergence.md` (DR-DIST-cross-repo-sha-pin)

## Cross-references

- Holodeck peer plan (now archived): `X:/claude-unreal-holodeck/archive/specs/2026-05-05-host-resource-resilience.md` (was: `docs/plans/2026-05-05-host-resource-resilience.md`)
- Cross-repo bug filing: `X:/claude-unreal-holodeck/archive/bugs/2026-05-05-cross-repo-217gb-virtual-memory-recurring.md`
- project-rag archived spec: `archive/specs/2026-05-05-belt-and-suspenders-oom-prevention.md`
- Companion VRAM-coexistence wiki: `docs/wiki/cross-process-vram-coexistence.md`
- Doctor surface: `commands/doctor.md` Step 1.7 (watchdog status read)
- Long-lived subprocess hookspec: `docs/wiki/addon-protocol.md` §project_rag_register_long_lived_subprocess
