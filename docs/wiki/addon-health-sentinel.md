# Addon Health Sentinel Convention

> Operator-facing visibility for plugin doctor verdicts. Coordinator reads, addons write.

## Problem

Doctor skills (`/project-rag-ue-addon:doctor`, `/holodeck:doctor`, etc.) correctly diagnose addon health when invoked — but nothing surfaces a RED verdict to the operator between invocations. The empirical failure mode (2026-05-19, project-rag-ue-addon): the engine corpus was unreachable from a consumer MCP session for an unknown duration; the doctor would have flagged it RED, but no operator ran it, so a consumer (DroneSim) queried the engine corpus, received a silent fallback to project content, and shipped work against the wrong substrate.

The `setup-doctor-coverage-invariant.md` wiki covers "setup landed but doctor didn't." This convention covers the adjacent gap: "doctor exists, fires correctly, and nobody runs it."

## Contract

### Path

```
~/.claude/plugins/<plugin>/data/doctor-last-run.json
```

`<plugin>` is the plugin directory name (e.g. `project-rag-ue-addon`, `coordinator-claude`). One sentinel per plugin; plugins that ship multiple doctor variants pick one canonical verdict for the sentinel.

### Schema

```json
{
  "ran_at":     "2026-05-19T14:32:08Z",
  "verdict":    "GREEN" | "AMBER" | "RED",
  "red_probes": ["C-16", "C-19"],
  "hint":       "engine_modules_round_trip — A-F-20",
  "plugin":     "project-rag-ue-addon"
}
```

- **`ran_at`** — ISO-8601 UTC timestamp of the run that wrote the sentinel. Required.
- **`verdict`** — overall verdict from the doctor run. Required. Values outside the enum are surfaced as `unknown verdict '<x>'` in workday-start (RED-only callers ignore).
- **`red_probes`** — array of probe identifiers that returned RED (probe IDs are doctor-internal). May be empty when verdict is GREEN/AMBER. Required field; empty array if N/A.
- **`hint`** — one-line operator-actionable description (probe name + remediation tag, error class, etc.). Required (use empty string if nothing useful to say).
- **`plugin`** — plugin name. Optional; derived from the sentinel's path if absent.

Plugins MAY include additional fields; the scanner ignores unknown keys.

### Write discipline

- **Write atomically.** Rename-over (write to `doctor-last-run.json.tmp`, then `mv`) to avoid the scanner reading a half-written file.
- **Write after every run, regardless of verdict.** A successful GREEN run is the signal that the doctor still works; absent or stale sentinels are themselves a workday-start nudge.
- **Never write from a non-doctor context.** This file is the doctor's signed receipt; arbitrary processes writing to it defeat the purpose.

## Consumers

### `/workday-start` (Step 1.9)

Runs `scan-addon-health.sh --red-and-stale`. Surfaces RED verdicts, AMBER verdicts, stale sentinels (>24h since `ran_at`), and missing/malformed sentinels under a `### Addon Health` section in the Morning Briefing. Threshold override: `COORDINATOR_HEALTH_STALE_SEC`.

AMBER is surfaced in workday-start (but not session-start) because sentinel verdicts can age out of sync with substrate before the wall-clock staleness threshold fires — observed 2026-05-21 with `project-rag-ue-addon` (sentinel AMBER at 10:03Z, live re-probe RED at 10:30Z, sentinel still inside the 24h freshness window). Workday-start is already a triage posture, so the noise cost is low; the alternative is silent workday-start under verdict inversion.

### `/session-start` (Lessons section)

Runs `scan-addon-health.sh --red-only`. Surfaces RED verdicts only — stale-but-green is not loud enough to fire on every session. The pre-handoff slot is deliberate: a RED engine corpus must be visible before the EM chooses work, because downstream MCP calls silently fall back without surfacing the failure.

### Remediation

Each notice cites `/`<plugin>`:doctor` as the remediation surface. Doctor skills are agentic remediation — they probe, diagnose, and frequently auto-repair (e.g. install missing assets, refresh corpus indices). The coordinator's role is purely surfacing; the addon owns the fix.

## Why convention-based, not registration-based

Discovery via glob (`~/.claude/plugins/*/data/doctor-last-run.json`) is opt-in by file presence — no `coordinator.local.md` registration step, no drift between "installed plugin" and "registered with coordinator." When a new addon ships, the day it writes its first sentinel is the day coordinator starts surfacing it. This matches the existing pattern for plugin-bundled wiki imports and tool surfaces.

## Scanner

`scan-addon-health.sh` is the single reader. Two modes:

| Mode | Caller | Surfaces |
|------|--------|----------|
| `--red-only` | `/session-start` | RED verdicts only (signal-not-noise) |
| `--red-and-stale` (default) | `/workday-start` | RED, AMBER, stale (>24h), malformed, unknown verdict (triage posture); also: plugins that declare a doctor but have never written a sentinel (absent-sentinel pass); SessionStart hook scripts referenced in `hooks.json` but absent on disk (hook-script existence pass — 2026-05-27) |
| `--check-sentinel-presence` | `/session-start` (alongside `--red-only`) | Bootstrap notice: emits one line when plugins are installed but NO sentinel exists anywhere (fires at most once per install life); silent once any sentinel is written |

Exit code is always 0 — advisory, never gating. Empty output ⇒ no surfaceable findings.

The `--red-and-stale` mode now runs three passes: (1) main sentinel-verdict loop, (2) absent-sentinel detection for plugins with declared doctor commands, (3) SessionStart hook-script existence probe. All passes emit the `[health] <plugin>: <message>` contract. Pass 3 catches the silent-skip failure mode: Claude Code no-ops a missing hook command without error. Authoring guide for hook authors: `docs/wiki/plugin-session-start-hooks.md`.

## Related: drift detection for plugin live installs

If your plugin's live install is a **separate git checkout** (e.g. `~/.claude/plugins/<plugin>/` is a clone of the plugin's source repo rather than the source repo itself), you should also register it for drift detection. The addon-health sentinel surfaces "doctor ran and said RED"; the drift probe surfaces "live checkout is N commits behind source" — orthogonal failure modes.

Registration shape: add `[plugin.mirrors.<plugin>]` to `~/.claude/machine-local/registry.local.toml`. Schema documented in `machine-local-registry.md § plugin.mirrors`. Runtime self-doc: `bash check-plugin-drift.sh --help` enumerates the probe's six drift legs (git-state, venv-pin, venv-pyproject, venv-mapping, venv-shim, working-tree).

Both signals converge under `### Addon Health` in `/workday-start` Step 1.10 — operators see one section, not two.

## Not in scope

- **Aggregate dashboards.** If the addon roster grows past a handful, consider a `/health:check` slash command that aggregates sentinels with more structure. For now, the one-line-per-RED-plugin shape is sufficient.
- **Cross-repo health.** Sentinels are per-machine, per-plugin. Multi-machine fleet health is a future concern.
- **Self-doctoring the doctor.** If a doctor never writes its sentinel, workday-start's stale check fires after 24h — that's the only signal. There is no meta-doctor watching the doctors.
