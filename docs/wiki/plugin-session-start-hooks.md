# Plugin SessionStart Hook Authoring Guide

> Spec backlink: `archive/specs/2026-05-27-cqcs-cluster6-infra-tooling.md` § Entry B
> Purpose: Authoring rules for plugin SessionStart hooks — three rules that prevent the silent-skip failure mode detected by `scan-addon-health.py --red-and-stale`.
> These are the **`SessionStart` platform hooks that constitute the SessionStart hook path** — distinct from the `/workstream-start` *skill*. This guide is about authoring that platform hook.

## The silent-skip failure mode

Claude Code executes SessionStart hooks declared in a plugin's `hooks/hooks.json`. When a declared hook command references a script that doesn't exist on disk, Claude Code silently no-ops the command — no error surfaces, no log entry, no indication the hook didn't fire. A botched plugin install that leaves a missing hook script is therefore invisible until the operator notices the expected session-boot behavior never fires.

`scan-addon-health.py --red-and-stale` (Third pass) catches this by:
1. Parsing `hooks.json` for each installed plugin.
2. Resolving the script path declared in each SessionStart command against the plugin's directory.
3. Emitting a `[health] <plugin>: SessionStart hook references missing script '...'` line for any that are absent.

This fires under `--red-and-stale` (workday-start triage posture) — signal-not-noise gating matches the existing absent-sentinel second pass.

## Rule 1 — Use `${CLAUDE_PLUGIN_ROOT}`, never `cwd`

SessionStart hooks fire with an **unpredictable working directory**. The only stable anchor is `${CLAUDE_PLUGIN_ROOT}`, which Claude Code resolves to the plugin's install directory at hook invocation time.

**Correct (coordinator's own hook shape — canonical example):**

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/session-init.sh"
          }
        ]
      }
    ]
  }
}
```

**Incorrect — will break on any machine where `cwd` differs:**
```json
"command": "bash ./hooks/scripts/session-init.sh"
"command": "bash ~/.claude/plugins/myplugin/hooks/scripts/session-init.sh"
```

The health probe resolves `${CLAUDE_PLUGIN_ROOT}` to the plugin directory and checks existence there. A hardcoded absolute path or cwd-relative reference produces a false-negative (probe sees the script missing because it's looking in the wrong place) or a true-positive miss (hardcoded path works only on the author's machine).

## Rule 2 — Ship per-platform interpreter variants

**Windows Git Bash ships `python` (Python 3.x), not `python3`.** Linux/macOS typically ship `python3` but may lack `python`. A hook that calls `python3` directly fails silently on Windows Git Bash; one that calls `python` may fail on strict Linux/macOS installs.

Options (pick one):

### Option A — Self-detecting interpreter in the script body

Write the hook script to resolve the interpreter at runtime, matching the pattern at `scan-addon-health.py` lines 74-89:

```bash
#!/usr/bin/env bash
PY="${COORDINATOR_PYTHON:-}"
if [[ -z "$PY" ]]; then
    if command -v python3 >/dev/null 2>&1; then
        PY=python3
    elif command -v python >/dev/null 2>&1; then
        PY=python
    else
        echo "[plugin-name] session-init: no python3/python on PATH — skipping." >&2
        # Write a sentinel so the health probe can distinguish 'skipped on purpose'
        # from 'silently broken'. See Rule 3.
        exit 0
    fi
fi
"$PY" -c "..."
```

`COORDINATOR_PYTHON` is the operator override; honour it for consistency with the rest of the coordinator toolchain.

### Option B — Ship both `.sh` and `.ps1` variants

Declare both in `hooks.json` and gate per platform:

```json
"command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/session-init.sh"
```

For Windows PowerShell sessions (if your plugin targets them), add a `.ps1` variant. The coordinator's own hooks ship as `.sh`-only because Git Bash is the supported shell on Windows; extend this only when you have a genuine PowerShell target.

### Option C — Node-based hooks

If the hook logic is JavaScript, `node ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/session-init.js` avoids the Python-on-Windows issue entirely. `node` is present on any machine running Claude Code (it ships with the Claude Code app).

## Rule 3 — Write a sentinel on deliberate skip

If a hook deliberately no-ops — for example because a required resource isn't available in this project context, or because a gate condition is false — **write a sentinel or log line rather than exiting silently**. This lets the health scanner distinguish "skipped on purpose" from "silently broken."

**Pattern:**

```bash
#!/usr/bin/env bash
# session-init.sh — runs at SessionStart for myplugin.
# If the required resource is absent, logs the skip and exits 0.

REQUIRED_RESOURCE="${MY_PLUGIN_RESOURCE:-}"
if [[ -z "$REQUIRED_RESOURCE" || ! -f "$REQUIRED_RESOURCE" ]]; then
    # Log the skip so workday-start can see it.
    echo "[myplugin] session-init: MY_PLUGIN_RESOURCE not set or absent — hook skipped intentionally." >&2
    # Optionally write a lightweight sentinel so the probe can detect the skipped state.
    mkdir -p "${HOME}/.claude/plugins/myplugin/data"
    echo '{"skipped_at":"'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'","reason":"MY_PLUGIN_RESOURCE absent"}' \
        > "${HOME}/.claude/plugins/myplugin/data/session-init-last-run.json"
    exit 0
fi
# ... normal hook body ...
```

A completely silent `exit 0` is indistinguishable from a missing script (both produce no output). The operator should be able to confirm "this hook ran and chose to skip" without enabling debug-level logging.

## Rule 4 — Runtime shell guards do NOT belong in a SessionStart hook

A SessionStart hook runs in **its own process**; its `env`, `shopt`, and `ulimit` settings do **not** propagate to the Claude Code Bash-tool invoking shell, which is separately resolved. A runtime shell guard (`ulimit -f`, `shopt -s …`) placed in a SessionStart hook therefore silently does nothing to the shell the agent's Bash calls actually run in — a textbook `present-in-config != live-in-invoking-shell` install-surface gap.

Runtime shell guards must be sourced from the rc the Bash tool actually reads — **verified empirically as the NON-LOGIN interactive `~/.bashrc`, not `~/.bash_profile`.** Two disciplines make this reliable:

1. **Confirm the delivery target by probing which rc the tool shell reflects** — don't assume; have the Bash tool echo a marker sourced from a candidate rc and see whether it appears.
2. **Dogfood the guard in a fresh shell** — a guard "present in the rc" is not a guard "live in the invoking shell" until a fresh Bash-tool invocation observes it in effect.

This is the SessionStart-hook corollary of Rule 3's silent-skip theme: a hook that *looks* like it hardens the runtime can be a complete no-op on the surface it was meant to protect.

## Cross-references

- `scan-addon-health.py` — Third pass (SessionStart hook-script existence probe). Run manually: `COORDINATOR_PLUGINS_ROOT=~/.claude/plugins scan-addon-health.py --red-and-stale`
- `docs/wiki/addon-health-sentinel.md` § Scanner — Scanner mode table; this probe rides the existing `--red-and-stale` surface.
- `hooks/hooks.json` — Coordinator's own hook declarations; canonical example of the `${CLAUDE_PLUGIN_ROOT}/hooks/scripts/<name>.sh` command shape.
- `archive/specs/2026-05-27-cqcs-cluster6-infra-tooling.md` § Entry B — Full rationale and design notes for the probe.
