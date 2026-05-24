---
title: Coordinator Doctor
created: 2026-05-20
author: claude-central-em
status: current
---

<!-- spec-backlink: docs/plans/2026-05-20-coordinator-doctor-wiki.md § Chunk 1 -->

# Coordinator Doctor

**Purpose.** This wiki is the operator-facing health-verification surface for the two pieces of coordinator substrate that downstream plugins depend on: the `~/.claude/machine-local/` registry and the `coordinator_whoami` package. It enumerates eleven runnable probes (P-1 through P-11, plus P-7a), defines severity vocabulary for probe results, and establishes the citation contract that downstream plugin doctors (holodeck, project-rag, project-rag-ue-addon) MUST follow when probing coordinator-owned substrate.

**What this wiki is not.** It is not a slash skill — a `/coordinator:doctor` command would be bloat for a non-interactive verification surface. It is not a runtime validator or a programmatic API. It does not duplicate the substrate doctrines: for `machine-local/` resolution order, see [`machine-local-registry.md`](machine-local-registry.md); for the whoami envelope schema, see [`cross-plugin-whoami-contract.md`](cross-plugin-whoami-contract.md).

**Cadence path — sentinel-writer primitive.** The wiki's "no slash skill" decision stands. To close the gap where coordinator-claude's substrate health was invisible to the daily addon-health sweep, the non-skill primitive `bin/coordinator-doctor-sentinel.sh` fires P-1..P-12 on cadence (from `/workday-start` Step 1.10, ahead of `scan-addon-health.sh`) and writes `~/.claude/plugins/coordinator-claude/data/doctor-last-run.json` in the sentinel schema documented in [`addon-health-sentinel.md`](addon-health-sentinel.md). Operators retain the inline-invocation path of §3 below; the script is the same probes, batched and serialized. See §7 for the script's contract.

**Adding a probe?** A new probe is a P-N entry in §3 of *this wiki* + a firing wire-up in `bin/coordinator-doctor-sentinel.sh` — there is no `coordinator/commands/doctor.md` to edit (the "no slash skill" decision above). Dispatch briefs for probe-wiring or coordinator-substrate audits should name this wiki path explicitly: an agent told to "check `coordinator/commands/` for a doctor" finds nothing and mis-wires the probe into a downstream project-doctor instead. Project-doctors are runtime consumers that cite P-N back to this authority surface.

---

> **Found a broken probe, or a fix that isn't in here? Patch it and send it back.** This substrate leans on agents because a script-only install was whack-a-mole across machines — and your machine is where the remaining rough edges surface. Hotwire whatever you need to get healthy, then send the fix upstream: open a PR, file an issue, or paste a rough note. Don't polish it — the *what / how / why* of your fix is what we generalize from, and it beats a one-line bug report. The agent diagnosing this with you can draft the writeup. See [CONTRIBUTING.md](https://github.com/dbc-oduffy/coordinator-claude/blob/main/CONTRIBUTING.md).

---

## Audience Routing

Three readers land here for different reasons:

**(a) Operator with a config failure.** You hit a "machine-local key not found" or "coordinator_whoami import error" and want a one-line answer. Go directly to the probe catalog §3 — run P-1 through P-4 for registry failures, P-5 through P-7 for whoami failures. If probes surface a missing substrate, see §6 (Bootstrap from cold-start).

**(b) Agent invoked from a downstream doctor.** You are running a holodeck or project-rag doctor and need to verify coordinator substrate as a prerequisite. Read §5 (Citation contract) first — it defines whether you should delegate to this wiki's probe or augment with your own. Do not reinvent the probe; cite P-N and surface the verdict.

**(c) Author of a new downstream doctor.** You are writing a plugin doctor that touches machine-local keys or coordinator_whoami introspection. Read §5 in full before authoring. The citation contract is binding — two shapes are defined, a third path is explicitly closed.

---

## Probe Catalog

Each probe has a single-line invocation. All `machine-local` invocations use the `bin/machine-local` CLI from the coordinator install. All `python -m coordinator_whoami.*` invocations assume `coordinator_whoami` is installed in the active Python environment (verified by P-5).

Severity values are from the vocabulary defined in §4.

**Portability note (Windows / Git Bash).** `python3` is the canonical Linux/macOS interpreter name. On Windows + Git Bash, the Python Launcher is the canonical entry; substitute `py -3` for `python3` in every command below. Operators on Windows may want to alias once: `alias python3='py -3'`. The `python3` references in the table are otherwise portable.

| ID | What it checks | Command | Pass interpretation | Fail interpretation | Severity if fail | Remediation |
|---|---|---|---|---|---|---|
| **P-1** | `~/.claude/machine-local/` directory exists | `test -d ~/.claude/machine-local && echo healthy \|\| echo error` | `healthy` | Directory absent — substrate was never bootstrapped | `error` | Run `/coordinator:setup` Phase 3 (§6) |
| **P-2** | `registry.toml` parses and declares `schema = 1` | `python3 -c "import tomllib,pathlib; d=tomllib.loads(pathlib.Path('~/.claude/machine-local/registry.toml').expanduser().read_text()); assert d.get('schema')==1"` | Exits 0 | File missing, unparseable TOML, or wrong schema version | `error` | Re-run Phase 3; check for manual edits that broke TOML structure |
| **P-3** | At least one key under `repos.*` is populated in `registry.local.toml` | `machine-local keys \| grep -q '^repos\.' && echo healthy \|\| echo degraded` | `healthy` — at least one repo path declared | `degraded` — fresh install or operator never seeded machine-specific paths | `degraded` | Run `machine-local set repos.<name> <path>` for each sibling repo (see [`machine-local-registry.md`](machine-local-registry.md) §9 for the `.local.toml` discipline) |
| **P-4** | `bin/machine-local` CLI shell-out works (smoke test) | `machine-local keys >/dev/null && echo healthy \|\| echo error` | `healthy` — CLI runs and registry is parseable | CLI not on PATH, `bin/` not linked, or registry.toml unparseable — setup incomplete | `error` | Run Phase 3; verify `~/.claude/bin/` is on PATH; verify `~/.claude/machine-local/registry.toml` exists and parses |
| **P-5** | `coordinator_whoami` package is importable | `python3 -c "import coordinator_whoami; print('healthy')"` | `healthy` | ImportError — package not installed or Python env mismatch | `error` | Run `/coordinator:setup` (Phase 3 Step 6) — this is the primary remediation; re-running Phase 3 installs `coordinator_whoami` idempotently. Fallback: `pip install -e ~/.claude/plugins/coordinator/whoami/` |
| **P-6** | Live `coordinator_whoami.project_rag` returns a v1-conformant envelope | `python3 -m coordinator_whoami.project_rag --human \| head -5` | Output contains `contract_version: 1` | JSON parse error, missing required fields, or non-zero exit | `error` | Check P-5 first; then inspect `~/.claude/machine-local/registry.toml` for missing keys the probe requires; see [`cross-plugin-whoami-contract.md`](cross-plugin-whoami-contract.md) §Validation |
| **P-7** | `~/.claude.json` mcpServers entries for installed plugins are present and well-formed (**configuration-presence probe — not binding health**) | `python3 -c "import json,pathlib; cfg=json.loads(pathlib.Path('~/.claude.json').read_text()); assert 'mcpServers' in cfg and len(cfg['mcpServers'])>0; print('healthy')"` | `healthy` — config entry exists and is parseable JSON | Config entry absent, malformed JSON, or `mcpServers` key missing | `degraded` | Re-run plugin install to write the mcpServers entry; verify `~/.claude.json` is writable. **For live binding state, see P-6** — P-7 confirms the config exists, not that the binding is active. |
| **P-7a** | `~/.claude.json` mcpServers entries are reachable (reachability-augmentation of P-7 — configuration presence is P-7's job; this probe adds transport-layer checks) | EM-native: read the deferred-tools registry at session-start (`/workday-start` Step 1.10.5) to detect tools that appear in `mcpServers` config but are absent from the live session tool surface. A standalone shell probe (`bin/probe-mcp-registration.sh`) is planned but not yet implemented — the EM-native Step 1.10.5 probe covers this gap. | All servers emit `registered presumed` or tools appear in session surface | Any server appears in config but absent from live tool surface | `degraded` (advisory; never gating) | Check the named server's transport: for stdio servers, verify command exists on PATH; for HTTP servers, verify the server process is running. Run `/workday-start` to trigger Step 1.10.5 visibility. |
| **P-8** | Sentinel presence: at least one `doctor-last-run.json` exists across installed plugins | `ls ~/.claude/plugins/*/data/doctor-last-run.json 2>/dev/null \| head -1 \| grep -q . && echo healthy \|\| echo degraded` | `healthy` — at least one doctor has been run | `degraded` — no plugin doctor has ever been run on this machine | `degraded` | Run each installed plugin's doctor once to bootstrap the sentinel; see [`addon-health-sentinel.md`](addon-health-sentinel.md) for the sentinel schema |
| **P-9** | UE override paths resolve against registry-declared roots | `bash ~/.claude/bin/verify-ue-overrides.sh` | Exits 0 with no remediation output | Non-zero exit or remediation message emitted | `degraded` or `error` (per script output) | Follow the remediation hint from the script, which will point to the relevant machine-local key (typically `repos.claude_unreal_holodeck`); re-run after setting the key |
| **P-10** | `bin/claude-home` path resolver smoke (added 2026-05-21 for resolver-family symmetry with P-4) | `~/.claude/bin/claude-home plugins` | Prints an absolute path to an existing directory | Command missing, prints empty, or path doesn't resolve to a directory | `error` | Re-run `/coordinator:setup` Phase 3; verify `~/.claude/bin/` is on PATH and the `claude-home` script + `_claude_home.py` are present |
| **P-11** | `coordinator/templates/setup/` matches live `~/.claude/setup/` (no drift) | `bash ~/.claude/plugins/coordinator/bin/verify-templates-setup-sync.sh >/dev/null && echo healthy \|\| echo degraded` | `healthy` — templates and live install are byte-identical | `degraded` — operator customized `~/.claude/setup/publish.sh` (or sibling) AND template ships a different version; bugfixes in the template will not reach this operator until manually re-synced | `degraded` | Inspect drift with `bash ~/.claude/plugins/coordinator/bin/verify-templates-setup-sync.sh` (no flags). To accept the operator's local edits as canonical: re-run with `--fix` (copies live → template). To accept the template as canonical: `cp coordinator/templates/setup/<file> ~/.claude/setup/<file>` for each drifted file. |
| **P-12** | Canonical document structure present — eager dirs from `canonical-structure.yaml` exist at `~/.claude` and their `README.md` files are intact | `bash ~/.claude/plugins/coordinator/bin/scaffold-canonical-structure.sh --root ~/.claude --dry-run \| grep -q "skip (exists)" && echo healthy \|\| echo degraded` | `healthy` — all eager directories and their READMEs are present | `degraded` — one or more eager dirs (e.g. `cross-repo/`) or READMEs are missing; the scaffold has not been run or a directory was manually deleted | `degraded` | Run `bash ~/.claude/plugins/coordinator/bin/scaffold-canonical-structure.sh --root ~/.claude` to restore the canonical structure; or re-run `/coordinator:setup` (Phase 3 Step 7). |

**Note on P-7 vs P-6.** P-7 is a *configuration-presence* probe: it verifies that the mcpServers entry exists and is well-formed JSON. It does NOT verify that the MCP server process is running, that the binding resolves, or that tool calls succeed. For binding health — "is this plugin's binding working?" — the answer comes from the live whoami call in P-6. Treating P-7 as a binding-health probe is the consumer-leak shape this wiki exists to close.

**Note on P-7a.** P-7a is the **reachability-augmentation** of P-7, per the THIRD-PATH-CLOSED citation contract defined in §5. P-7 confirms the mcpServers configuration entry is present and well-formed. P-7a confirms the configured server is actually reachable: for stdio servers, that the configured command exists on PATH; for HTTP servers, that the endpoint responds (3s timeout). Neither P-7 nor P-7a proves tool registration is active in a running session — that is `/workday-start` Step 1.10.5's job. Step 1.10.5 is the current implementation of P-7a: it reads the deferred-tools registry from session context and compares it against the `mcpServers` config, writing a sentinel at `~/.claude/plugins/coordinator-claude/data/mcp-registration-last-check.json`. A standalone shell probe (`bin/probe-mcp-registration.sh`) is planned but not yet implemented; `probe-cwd-project-rag-relevance.sh` reads the Step 1.10.5 sentinel to determine MCP health for the current cwd.

### P-11 — Templates/setup drift detection

<!-- spec-backlink: docs/plans/2026-05-21-generic-percolation-via-coordinator-install.md § Step 3 + Step 8 -->

P-11 covers the source-of-truth substrate the coordinator plugin ships for `/coordinator:setup` and the generic percolator: `coordinator/templates/setup/publish.sh`, `publish_sync.py`, and `publish-targets.example.sh`. The live install at `~/.claude/setup/` is materialized from these templates by `install-substrate.sh`. **Drift** here means the bytes on disk in `~/.claude/setup/` no longer match the templates the plugin ships — typically because the operator hand-edited the live file, or because a plugin update bumped the template without re-running the installer. Either way, the next `/coordinator:setup` or installer run would produce a result the templates declare but the operator does not have.

**Recovery direction is opinionated.** `verify-templates-setup-sync.sh --fix` copies **live → template** — it treats the operator's working copy as authoritative and updates the template to match. This is the same discipline `verify-templates-bin-sync.sh` carries, and it matches the contract the templates exist under: templates are mirrors of an installer-managed live tree, not the other way around. To go the other direction (template-as-authoritative, e.g. accepting a plugin bugfix), the operator runs `cp coordinator/templates/setup/<file> ~/.claude/setup/<file>` by hand, deliberately overwriting their local edits. There is no `--fix-reverse` flag; that asymmetry is intentional.

**Why `degraded` and not `error`.** Operator-customized `publish.sh` is intentional behavior the doctrine accepts — operators legitimately tune their publish targets, retry logic, or commit messages for their environment. Drift is informational ("bugfixes in the template will not reach this operator until manually re-synced"), not a failure mode that blocks coordinator function. `error` severity is reserved for substrate that, when broken, prevents downstream plugins from working at all (P-1, P-2, P-4, P-5, P-6, P-10). P-11 is in the same severity family as P-3 (machine-local repos populated) and P-7 (mcpServers config presence) — surface to operator, do not block.

---

## Severity Vocabulary

This wiki uses a four-state probe-result vocabulary: `{healthy, degraded, error, inconclusive}`.

**Relationship to `cross-plugin-whoami-contract.md`.** The whoami contract defines a *closed* `status.state` enum: `{"healthy", "degraded", "error"}`. That enum is enforced by the envelope validator — a response with `status.state = "inconclusive"` would be rejected as non-conformant. The doctor-wiki vocabulary is a *separate* surface used in operator-facing prose and probe tables, never inside a whoami envelope. The first three states intentionally match the contract's so that a probe verdict lines up with a `status.state` when you are reporting results in a table; `inconclusive` is added for the case where a probe cannot determine pass or fail (e.g., a dependency tool is absent and the probe cannot execute).

**Three-way "degraded" disambiguation.** The term `degraded` appears in three distinct vocabularies in this system, with different semantics:

- **Doctor-probe result** (this wiki): the probe ran and surfaced a non-fatal problem. The substrate is partially functional. Operator action recommended but not blocking.
- **`status.state` in the whoami envelope** ([`cross-plugin-whoami-contract.md`](cross-plugin-whoami-contract.md) §`status` object): the plugin reported that its health is degraded — some dependency is missing or tool calls may succeed with reduced capability.
- **`binding.kind` in the whoami envelope** ([`cross-plugin-whoami-contract.md`](cross-plugin-whoami-contract.md) §`binding` object): the plugin's primary resource is only partially resolved.

All three reuse the word deliberately (the probe-result vocabulary aligns with the contract's so probe tables read cleanly), but they are non-interchangeable. A doctor probe returning `degraded` does not imply the whoami envelope will carry `status.state = "degraded"` — the probe may have found a configuration gap that does not affect the live binding reported by the daemon.

**`inconclusive`** is doctor-wiki-only. It is the correct probe verdict when the probe cannot run at all (command not found, required dependency absent). It must never flow into a whoami envelope `status.state`.

---

## Citation Contract for Downstream Doctors

Plugin doctors (holodeck, project-rag, project-rag-ue-addon) that probe coordinator-owned substrate — the machine-local registry, the `coordinator_whoami` package, or mcpServers classification — MUST use one of two citation shapes:

**(a) Delegation.** The downstream doctor's probe says "for diagnostic procedure, see coordinator-doctor.md P-N" and surfaces this wiki's verdict verbatim. Use this when the downstream doctor has no additional context to add — it is asking the same question this wiki's probe answers.

Example citation string:
```
Probe C-N delegates to coordinator-doctor P-3. Run: machine-local list | grep -q '^repos\.' && echo healthy || echo degraded
See coordinator-doctor.md P-3 for full pass/fail interpretation and remediation.
```

**(b) Augmentation.** The downstream doctor runs its own check that depends on coordinator substrate, and cites P-N as the prerequisite. Use this when the downstream doctor's probe builds on a coordinator-substrate result (e.g., "given P-3 is healthy, verify that `repos.claude_unreal_holodeck` resolves to a directory containing a `.uproject` file").

Example citation string:
```
Prerequisite: coordinator-doctor P-3 (machine-local repos populated). This probe extends P-3:
given P-3 healthy, verify repos.claude_unreal_holodeck resolves to a valid .uproject root.
```

**THIRD-PATH-CLOSED.** There is no third path. Downstream doctors probing coordinator-owned substrate (machine-local registry, `coordinator_whoami`, mcpServers classification) MUST use citation shape (a) or (b). Reinventing a probe against coordinator substrate without one of these citation shapes is a doctrine violation, surfaceable to PM. Ad-hoc invention is out-of-contract; the citation shapes exist precisely to close that failure mode.

> *Cross-team directive (holodeck, project-rag, project-rag-ue-addon): any doctor.md surfacing probes against coordinator-owned substrate — machine-local registry, coordinator_whoami, mcpServers classification — MUST use citation shape (a) delegation or (b) augmentation. Reinventing a probe against our substrate is the failure mode this wiki exists to close; ad-hoc invention is out-of-contract.*

**Binding-health probes MUST cite P-6, not P-7.** When a downstream doctor is classifying binding health ("is this plugin's binding working?"), it MUST cite P-6 (live whoami call), not P-7 (config-presence file check) — even when P-7 is sufficient for a pure config-audit purpose. File presence does not equal runtime correctness. This applies whether the doctor delegates (a) or augments (b).

> *Cross-team directive (holodeck, project-rag, project-rag-ue-addon): when probing "is this plugin's binding healthy?" the answer comes from live whoami (P-6), not file-read mcpServers classification (P-7). Treating P-7 as a binding-health probe is consumer-leak shape — file presence ≠ runtime correctness.*

**Live-call requirement for whoami-dependent probes.** Per [`plugin-identity-and-health-sentinels.md`](plugin-identity-and-health-sentinels.md) (live = MCP truth; persistent = receipt) and the live-not-receipt invariant in [`cross-plugin-whoami-contract.md`](cross-plugin-whoami-contract.md), any downstream doctor reusing P-7 or any whoami-dependent probe MUST call the live MCP `*_whoami` tool — never read a persisted snapshot from `~/.claude/<plugin>/install-profile.json` or equivalent. Persisted whoami snapshots are operator-facing receipts, not diagnostic truth; consulting a stale snapshot turns "stale = signal" into "stale = active lie." This requirement applies to both delegation (a) and augmentation (b) citation shapes.

---

## Bootstrap from Cold-Start

If P-1, P-2, or P-4 fail because the substrate does not exist yet, the operator has not run Phase 3 of `/coordinator:setup`. Phase 3 lays down:

- `~/.claude/machine-local/` directory
- `bin/machine-local` CLI shim
- `registry.toml` (tracked baseline with `schema = 1`)
- `registry.local.toml` (gitignored machine-specific overrides)
- A README and `.gitignore` for the directory

Run `/coordinator:setup` and follow the Phase 3 interactive prompts to seed the four baseline keys (`repos.coordinator_claude`, `repos.project_rag`, `repos.claude_unreal_holodeck`, and `publish.targets`). After Phase 3 completes, re-run P-1 through P-4 to confirm.

For P-5 failures (package not importable), the package ships at `plugins/coordinator/whoami/` and installs via `pip install -e <path>`. Phase 3 Step 6 installs `coordinator_whoami` for fresh installs; if it regressed, re-run Phase 3 or install manually.

---

## Sentinel-Writer Primitive

**Script.** `bin/coordinator-doctor-sentinel.sh` (in the coordinator-claude plugin tree). Fires P-1..P-12 in batch, classifies each result, and writes a sentinel at `~/.claude/plugins/coordinator-claude/data/doctor-last-run.json` for [`scan-addon-health.sh`](addon-health-sentinel.md) to consume.

**Why a script and not a slash skill.** The §1 framing ("not a slash skill") remains the design. A slash skill would imply an interactive flow with EM choice points; the cadence path is the opposite — fire the probes, write the receipt, move on. The script is a thin glue layer over the same probes operators run inline.

**Verdict synthesis.**

- Any probe with severity `error` failing → `RED`
- No errors, but one or more `degraded` failing → `AMBER`
- All probes pass → `GREEN`
- Probes that cannot execute (missing dependency tool) → `AMBER` with explanatory note in `hint`

**Sentinel schema** (mirrors `addon-health-sentinel.md`, plus an `amber_probes` field for machine-readable AMBER triage — `scan-addon-health.sh` ignores unknown fields, so the extension is additive-safe):

```json
{
  "ran_at":       "<ISO-8601 UTC, Z-suffix>",
  "verdict":      "GREEN" | "AMBER" | "RED",
  "red_probes":   ["P-1", "P-5", ...],
  "amber_probes": ["P-3", "P-9", ...],
  "hint":         "<one-line per failing probe, joined with ' | '>",
  "plugin":       "coordinator-claude"
}
```

**Severity rule for missing dependencies.** Probes for OPTIONAL tools whose dependency is absent (e.g. P-9 `verify-ue-overrides.sh` on a non-UE workstation) are silently skipped — not surfaced. Probes for REQUIRED INFRASTRUCTURE whose binary is missing (P-4 `machine-local` CLI, P-10 `claude-home` resolver) are RED — their absence means `/coordinator:setup` Phase 3 regressed and downstream plugins will fail.

**Where it fires.**

- `/workday-start` Step 1.10 — runs the script ahead of `scan-addon-health.sh` so the freshly-written sentinel is picked up the same run.
- Direct operator invocation — `bash ~/.claude/plugins/coordinator/bin/coordinator-doctor-sentinel.sh` any time. Silent on GREEN; brief AMBER/RED stdout for direct visibility.

**Citation contract carryover.** Downstream plugin doctors that need to verify coordinator substrate MUST still follow §5 — delegate to P-N or augment P-N, never reinvent. The sentinel-writer is the *batch-execution* path for our own scheduled probing; it does not change the contract for cross-plugin citations.

**Environment honored.** `CLAUDE_HOME` (test sandboxes / CI), `COORDINATOR_PYTHON` (explicit interpreter override), `COORDINATOR_PLUGINS_ROOT` (alternate plugin root for testing).

---

## Cross-References

- [`machine-local-registry.md`](machine-local-registry.md) — substrate doctrine: what belongs in the registry, resolution order, anti-patterns, tracked-baseline + `.local` discipline. For health verification, see P-1 through P-4 above; do not consult this wiki for "is my registry healthy?" — that is what P-1 through P-4 answer.
- [`cross-plugin-whoami-contract.md`](cross-plugin-whoami-contract.md) — envelope schema, binding/status field semantics, validation, and reference implementation. For operator-facing health verification using `coordinator_whoami`, use P-5 through P-7 above.
- [`addon-health-sentinel.md`](addon-health-sentinel.md) — decay-discipline convention: doctor writes receipts (stale = signal), scanner is the no-side-effects bridge. P-8 above surfaces sentinel absence as the operator-facing gap this convention addresses.
- [`plugin-identity-and-health-sentinels.md`](plugin-identity-and-health-sentinels.md) — companion doctrine defining the live/persistent split that underlies the P-6-not-P-7 rule in §5.
- [`coordinator-installer-shape.md`](coordinator-installer-shape.md) — three-audience installer contract; Phase 3 referenced in §6 above.
- [`coordinator-installer-status-schema.md`](coordinator-installer-status-schema.md) — status-report table schema for `/coordinator:setup`; referenced when reading Phase 3 output.
- [`live-install-drift-audit.md`](live-install-drift-audit.md) — two-leg drift probe and refresh primitives; used when P-11 surfaces template/live-install drift as systematic.
- `bin/probe-mcp-registration.sh` — planned P-7a standalone shell probe (not yet implemented as of 2026-05-21; `/workday-start` Step 1.10.5 EM-native probe covers this gap); writes `~/.claude/plugins/coordinator-claude/data/mcp-probe-last-run.json` when implemented.
