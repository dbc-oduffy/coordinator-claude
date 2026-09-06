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

<!-- Imported from X:/project-rag at SHA d376cb01. Inherited substrate; canonical lineage now in Claude Central. Origin: project-rag/docs/... — sibling-repo layout doctrine now lives in this repo's own wiki (the meta-repo local-doctrine file this once pointed at is retired). --> <!-- foreign-path-ok: import provenance, quoting the machine-specific path as it stood at import time, not a live location assertion -->

# Host resilience and bounded subprocess spawn

> Three-layer defense against runaway resource consumption from any project-rag spawn site (embed_sidecar, Mode B headless UE, clang structural index, install/update pip subprocesses). Companion to the example-game-repo `host-resource-resilience` plan; project-rag is the consumer, example-game-repo is the canonical author.

## The three layers

| Layer | Mechanism | Where it lives | What it catches |
|---|---|---|---|
| **1. Kernel ceiling** | `bounded_popen` wraps every long-lived `subprocess.Popen` with a Windows Job Object (`mem_max_bytes`) or POSIX `setrlimit`. Kernel terminates on breach. | `core/host_resilience.py` (fleet SSOT) | Process committing virtual memory faster than user-space pollers can react. The "217 GB in 30 s" failure mode. |
| **2. Argv capture at spawn** | Every `bounded_popen` call logs full argv (including resolved interpreter abs-path) at INFO before Popen returns. | `core/embed_client.py:_spawn_sidecar`, `priming/producer_runner.py` Mode B, `priming/producers/structural_index_clang.py`, `embed_sidecar/app.py` torch self-test | Names the next OOM event in `Saved/ProjectRag/embed_sidecar.<pid>.log` or producer-runner log — closes the static-analysis-can't-find-it gap. |
| **3. Sidecar self-bound** | `embed_sidecar/app.py` lifespan starts a psutil RSS sampler; on `EMBED_SIDECAR_MAX_RSS_GIB` breach, sets `_self_bound_exit_reason` and raises SIGTERM → graceful drain → exit 75. | `embed_sidecar/app.py`, `embed_sidecar/config.py` | Sidecar invoked outside `bounded_popen` (debug starter scripts, manual launch) still has a ceiling. Defense-in-depth. |

## SSOT contract — `project-rag/core/host_resilience.py`

**project-rag is the single source of truth for `bounded_popen`; example-game-repo is the consumer.** `example-game-workbench-repo/mcp_server/host_resilience/__init__.py` is a re-export shim over it — the four platform-impl files it once owned are upstream-deleted. The shim raises `ImportError` naming project-rag when project-rag is not pip-installed, so a broken deployment fails loudly.

**Drift enforcement (mechanical, not doctrinal):** `project-rag/tests/host_resilience/test_vendored_helper_is_current.py` asserts the file (a) declares itself canonical in its header and (b) imports nothing from example-game-repo/`mcp_server` — a consumer-direction import would re-invert the dependency. Platform-independent by construction: no hardcoded sibling checkout path, so it is PASS-required everywhere rather than a no-op on machines without the other repo.

**Why one authored copy and not a probe-chain or path-on-disk import:** a probe-chain couples each repo's runtime to the other's install presence, in whichever direction it runs. One authored module plus a package dependency keeps the coupling declared and greppable.

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
| `priming/producer_runner.py:805` (UnrealEditor-Cmd.exe) | Mode B headless UE; mid-cook kill is destructive; matches example-game-repo's accepted-risk-with-reason; argv logged |

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

**example-game-repo's helper does NOT currently probe `BREAKAWAY_OK` on the parent job.** This is an upstream gap. project-rag is a consumer, not an author — the gap is filed against the example-game-repo plan; the SHA-pin test catches when the upstream fix lands and triggers a re-vendor.

The project-rag dev machine is not jobbed at the parent level (typical interactive shell), so W2 ships with this gap accepted. Surface this in CI failures and reviews of new spawn sites that might run inside a CI sandbox.

## Tripwires for editing this surface

- **Adding a `subprocess.Popen` or long-lived `subprocess.run` call** in `core/`, `embed_sidecar/`, `priming/`, `project_rag_mcp/`, `indexer/`, `scripts/`: the AST coverage test (`tests/host_resilience/test_spawn_helper_coverage.py`) will fail. Either route through `bounded_popen` or add to ALLOW_LIST with rationale.
- **Editing `core/host_resilience.py`**: it is the fleet's canonical `bounded_popen`, consumed by example-game-repo through a shim. Author here, and treat a signature change as a cross-repo change. Do NOT fork a second copy anywhere.
- **Touching `embed_sidecar/app.py` lifespan**: respect the `_self_bound_exit_reason` + signal-raise pattern; don't replace with `sys.exit` from inside the asyncio task.
- **Adding a `*_MIB` / `*_GB` / `*_GIB` constant** in any audited package: the AC-4 declaration-multiplier audit (`tests/host_resilience/test_no_unit_mismatch_in_size_constants.py`) will fail if `value × unit_multiplier` exceeds `2 × total_system_memory`. The audit catches declaration mismatches; interpretation mismatches (a `*_MIB` constant correctly declared but consumed at a call site as bytes) require AC-3 argv evidence on the next event.

## Call sites

*project-rag* — `core/embed_client.py` (embed sidecar), `priming/producers/structural_index_clang.py` (clang extractor, 8 GiB ceiling), plus the definition in `core/host_resilience.py`. *example-game-repo* — `mcp_server/server_lifecycle.py` (gpu_sidecar / aux-process launch from the MCP server lifespan), through the shim.

**Coupling direction, do not invert.** Prose elsewhere in the fleet still describes example-game-repo as the authoring side with project-rag vendoring by SHA pin; that description is stale, and acting on it means attempting to re-vendor from four files example-game-repo does not have. The direction is fixed by the package dependency, project-rag → example-game-repo — not by which repo has the richer caller surface.

## Long-lived subprocess hookspec (tc-2)

The tc-2 work added `project_rag_register_long_lived_subprocess` as the 7th addon hookspec. The host harness (`core.long_lived_runtime._boot_subprocess`) now owns the lifecycle for ALL long-lived daemon-style subprocesses via this hookspec:

- `bounded_popen` wrapping with memory-ceiling enforcement
- Single-instance PID lock under `<data_dir>/<spec.id>.pid` (`O_EXCL`)
- Asyncio idle-offload and process-exit watchdog (thresholds from `AddonLongLivedSubprocessSpec`)
- Doctor probe registration via `spec.doctor_probe_step_id`
- Tenant-registry write under `<data-home>/process-tenants/` (or `<settings-home>/gpu-tenants/` per `spec.tenant_kind`)

**Migration impact:** the embed sidecar's spawn mechanism moved from `core/embed_client.py:_spawn_sidecar` (deleted in WS-8) to `core.long_lived_runtime._boot_subprocess`. Observable behavior is unchanged (same port, PID file, timeouts). Tests that previously patched `core.embed_client.bounded_popen` must now patch `core.long_lived_runtime.bounded_popen`.

The embed sidecar dogfoods this seam via `BUILTIN_EMBED_SIDECAR_SPEC` in `embed_sidecar/builtin_spec.py` — registered by the host directly, no addon required for built-in subprocesses.

**Addons wanting a GPU sidecar or LSP server:** return an `AddonLongLivedSubprocessSpec` from `project_rag_register_long_lived_subprocess`. The host harness handles all lifecycle mechanics; the addon supplies `argv_builder`, `env_extras`, memory ceilings, idle/exit timeouts, health URL, and doctor probe step ID. See `core/addon_protocol.py` for the full field spec.

> Distilled from: `docs/plans/2026-05-13-tc-2-long-lived-subprocess-hookspec.md` §WS-1, §WS-8; `docs/wiki/addon-protocol.md` §project_rag_register_long_lived_subprocess

## Tenant registry — `<data-home>/process-tenants/`

Every long-lived subprocess registered through the hookspec writes `<data-home>/process-tenants/<port>.json` — the canonical place for cross-process process-presence assertions. `<data-home>` is project-rag's durable-data plane (`core/machine_local_reader.data_home()`), overridable by `CLAUDE_PROCESS_TENANTS_DIR`. **Nothing writes `~/.claude/process-tenants/`**: read-only legacy, union-read and GC'd by `list_tenants()` so pre-migration entries drain instead of going invisible. Implementer: `project-rag/core/process_tenants.py`.

GPU tenants are a **separate registry with a different schema**, not a second write of this one: `<settings-home>/gpu-tenants/<port>.json` (`project-rag/embed_sidecar/peers.py`, `example-game-workbench-repo/gpu_sidecar/peers.py`), carrying the VRAM `lease` block. That one is a cross-repo rendezvous — its literal string is the two-repo contract, so it moves only by coordinated union-read flip. `~/.claude/gpu-tenants/` is likewise read-only legacy.

**Tenant file schema:**

```json
{
  "name": "ls_host",
  "port": 43841,
  "pid": 12345,
  "kind": "cpu_ram",
  "extra": {}
}
```

`extra` is opaque addon-supplied metadata (subprocess id, health URL) — unenforced at this layer.

**GC policy:** stale entries are removed lazily on next tenant-registry read — PID not running, or older than `PROCESS_TENANTS_STALE_AGE_S` (default 3600s, defending against PID recycling). No dedicated GC daemon.

> Verified at `project-rag/core/process_tenants.py` (`_registry_dir`, `register_tenant`, `_legacy_registry_dir`). Origin: `docs/plans/2026-05-13-tc-2-long-lived-subprocess-hookspec.md` §WS-5 tenant-registry.

## Cross-repo SHA-pin policy (DR-DIST-cross-repo-sha-pin)

For any helper genuinely vendored across repos (`core/host_resilience.py` is authored, not vendored — see § SSOT contract):

1. **SHA pin must reference `origin/main`**, never `work/*` or `feature/*`. A pinned work branch that later rebases or is abandoned invalidates the vendor record without failing a test.
2. **Vendor-with-mechanical-SHA-pin beats doc-only policy.** "Keep in sync" in a CLAUDE.md has no enforcement; a test reading the SHA from the file header and checking it against the upstream git log catches drift automatically.

> Distilled from: `archive/specs/2026-05-07-bounded-popen-convergence.md` (DR-DIST-cross-repo-sha-pin)

## Cross-references

- example-game-repo peer plan (now archived): `example-game-workbench-repo` repo, `archive/specs/2026-05-05-host-resource-resilience.md` (was: `docs/plans/2026-05-05-host-resource-resilience.md`; resolve the repo root via `repos.example_game_workbench_repo`)
## startup-only guard does not cover mid-life resource failure

A startup-only guard (a flag set at load time that says "resource is available") does not cover mid-life failure of the same resource. If the resource fails after startup, the guard reports it as available until the next restart. Health probes must reflect functional state (liveness), not just load-time availability. Apply: any health flag set once at import/startup must be backed by a periodic re-check or replaced with a functional probe that queries the resource directly.

## Windows asyncio ProactorEventLoop CPython #93821 — use SelectorEventLoop for HTTP daemons

Windows asyncio `ProactorEventLoop` carries CPython bug #93821 — long-running HTTP daemons using ProactorEventLoop can zombify after network transients. Use `asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())` at daemon start for any HTTP server that must survive multi-hour sessions. Apply: grep `asyncio` daemon entry points for Windows; add `WindowsSelectorEventLoopPolicy` guard at start.

## PID-file-holder liveness != accept-loop liveness — zombie discriminator grace window

Hook zombie discriminator: PID-file-holder liveness (process is alive) does not equal accept-loop liveness (socket is accepting connections). A process can be alive but wedged before `bind()`/`accept()` — it holds the PID file but cannot serve requests. Add a grace window (e.g., 5s) after PID-file presence is confirmed before asserting accept-loop availability, and perform a socket-connect probe, not just a process-alive check.

## three lifecycle topologies — _boot_subprocess vs ensure-script vs outer-process supervisor

Per-project Windows daemons need a per-user outer-process supervisor (e.g., a coordinator `ensure-<daemon>` script launched by `SessionStart`), NOT a Windows service AND NOT the in-process `_boot_subprocess` harness. Three distinct topologies: (1) `_boot_subprocess` — inline child managed by the caller process, dies when caller dies; (2) `ensure-script` — idempotent launch script, suitable for short-lived services; (3) outer-process supervisor — started by SessionStart hook, independent lifetime, correct for per-project HTTP daemons.

- Cross-repo bug filing: `example-game-workbench-repo` repo, `archive/bugs/2026-05-05-cross-repo-217gb-virtual-memory-recurring.md` (resolve the repo root via `repos.example_game_workbench_repo`)
- project-rag archived spec: `archive/specs/2026-05-05-belt-and-suspenders-oom-prevention.md`
- Companion VRAM-coexistence wiki: `docs/wiki/cross-process-vram-coexistence.md`
- Doctor surface: `coordinator/docs/wiki/coordinator-doctor.md` Step 1.7 (watchdog status read)
- Long-lived subprocess hookspec: `docs/wiki/addon-protocol.md` §project_rag_register_long_lived_subprocess
