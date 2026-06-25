---
name: setup
description: "deep-research-claude install-chain walker (chain step 4 of 5). Walk the direct_deps declared in docs/install/agent-install-manifest.json, probe coordinator-claude (soft dep), dispatch the chain-walker subagent, and report. Trigger phrases: /deep-research:setup, set up deep-research, run the install chain for deep-research."
allowed-tools: ["Read", "Bash", "Agent"]
argument-hint: "[--skip-dep-check --accept-missing-deps-risk]"
---

<!-- spec-backlink: archive/specs/2026-06/2026-06-15-deep-research-install-chain-application-phase-b.md § C4 -->

# /deep-research:setup

Chain-walker skill for deep-research-claude (chain position 4 of 5). This skill is the agentic entry-point for the install-chain contract. It walks `direct_deps` declared in the install manifest, checks each dep via functional probe, and dispatches the chain-walker subagent to handle recursive install of soft deps. It does NOT replace `/deep-research:install` (the plugin-local bootstrap for Agent Teams, NotebookLM auth, etc.) — those concerns belong to that skill.

**IMPORTANT — `setup_skill` is informational metadata, not the dispatch primitive.** The manifest field `setup_skill: /deep-research:setup` tells humans what to type. Dispatched subagents cannot expand slash commands; this skill uses direct Bash + Agent calls instead.

---

## Out-of-scope actions for all dispatched agents in this skill

**Destructive-action prohibition (verbatim from `coordinator-tripwires.md` § Destructive-action prohibition):**

DO NOT run `gh pr create`, `gh pr merge`, `git push origin main`, `gh release create`, or any `gh` command that mutates GitHub state beyond pushing the current branch. DO NOT commit to `main` directly. If you find yourself reaching for a merge, STOP and surface the question to the EM in your final reply.

**Additional out-of-scope items specific to this skill:**

- Writing files OUTSIDE `plugins/deep-research/` (this skill owns nothing in coordinator's tree)
- Modifying `docs/install/agent-install-manifest.json` (manifest is a static artifact read by the walker, not mutated by it)
- Touching `plugins/coordinator/CLAUDE.md` or any coordinator-plugin tree file
- Any `git commit` or `git push` operation
- Writing to `~/.claude/state/handoffs/` — DR does NOT seed install-leg spinoffs; coordinator seeds `deep-research`'s spinoff from `plugins/coordinator/templates/handoffs/install-deep-research.md` (contract § Install-spinoff layer / two roles; plan NG5)

<!-- Spinoff-schema awareness: N/A — this skill does not author handoffs or spinoffs. -->
<!-- Recheck-marker semantics: N/A — this skill is not cadenced; it is invoked on demand. -->

---

## Discovery-surface integration

This skill announces itself via its `description:` frontmatter field. No separate `/workstream-start` hook integration is required — the description line contains the trigger phrases and is surfaced by Claude Code's skill discovery. If the project's `/workstream-start` mentions install-chain setup (Step 1 plugin-bootstrap surfacing), the description field is the hook point.

**Platform-vocabulary collision check:** `:setup` is the established verb across coordinator-claude, holodeck, project-rag-ue-addon, and now deep-research-claude. No collision; consistent verb. ✓

---

## Step 1 — Detect layout (flat publish-repo vs. nested working-repo)

Determine whether this skill is running inside the nested working-repo (under `~/.claude/plugins/deep-research/`) or the flat publish-repo (a standalone `deep-research-claude/` checkout).

```bash
# Heuristic mirrors setup.sh layout detection.
# Flat publish-repo: docs/install/AGENT.md exists directly under CLAUDE_PLUGIN_ROOT/../
# Nested working-repo: CLAUDE_PLUGIN_ROOT is plugins/coordinator-claude/deep-research

# Review: code-reviewer — F5: add CLAUDE_PLUGIN_ROOT fallback guard; BASH_SOURCE fallback
# for OSS install layouts where CLAUDE_PLUGIN_ROOT may not be set.
if [[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
  PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT}"
else
  # Derive from BASH_SOURCE: skills/setup/SKILL.md → two levels up = plugin root
  _SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
  PLUGIN_ROOT="$(cd "${_SCRIPT_DIR}/../.." && pwd)"
  if [[ ! -d "${PLUGIN_ROOT}" ]]; then
    echo "ERROR: CLAUDE_PLUGIN_ROOT is unset and cannot derive plugin root from BASH_SOURCE — set CLAUDE_PLUGIN_ROOT before running" >&2
    exit 1
  fi
fi

FLAT_AGENT_MD="${PLUGIN_ROOT}/docs/install/AGENT.md"

if [ -f "${FLAT_AGENT_MD}" ]; then
  LAYOUT="flat"
  REPO_ROOT="${PLUGIN_ROOT}"
else
  # Nested layout — repo root is two levels up (coordinator-claude root)
  LAYOUT="nested"
  # In the working-repo the manifest lives at the same relative path from PLUGIN_ROOT
  REPO_ROOT="${PLUGIN_ROOT}"
fi

MANIFEST="${REPO_ROOT}/docs/install/agent-install-manifest.json"
echo "Layout: ${LAYOUT}"
echo "Manifest path: ${MANIFEST}"
```

Report the detected layout. If the manifest does not exist, surface the error with remediation: "Manifest not found at `${MANIFEST}`. Re-run after the install surface has been committed (`plugins/deep-research/docs/install/agent-install-manifest.json`)."

---

## Step 2 — Read the install manifest

```bash
if [ ! -f "${MANIFEST}" ]; then
  echo "ERROR: manifest not found at ${MANIFEST}" >&2
  exit 1
fi
cat "${MANIFEST}"
```

Parse the manifest to extract:
- `agent_install_contract_version` — must be 1, 2, or 3 (reject anything outside `{1, 2, 3}` with a remediation message). DR reads coordinator's manifest during chain-walk; coordinator ships v3 as of the 2026-06-23 cutover.
- `repo_id` — should be `"deep-research-claude"`
- `direct_deps` — the list to walk (DR declares one: `coordinator-claude`, severity `soft`)
- `override_flags` — the flag pair names for consent-gate invocations

If the manifest fails JSON parsing, surface the parse error and exit. Do not continue with a corrupt manifest.

---

## Step 3 — Initialise the visited-set (contract § Visited-set protocol)

The visited-set is a disk-resident file used for diamond-DAG and cycle detection across recursive subagent dispatches. DR's visited-set lives at:

```
~/.claude/deep-research-claude/chain-walk-<session-id>.json
```

<!-- the Staff Engineer Finding 4 (plan §7 C3 + §9): visited-set path is ~/.claude/deep-research-claude/ NOT ~/.deep-research-claude/ -->

```bash
# python3-first interpreter resolution — `python` is absent on modern macOS / many
# Linux (only python3); `python3` is absent on Windows/pyenv (only python).
PY="$(command -v python3 || command -v python)"; [ -n "$PY" ] || { echo "no python3/python on PATH" >&2; exit 1; }

# Generate a session UUID
SESSION_ID="$("$PY" -c 'import uuid; print(str(uuid.uuid4()))')"

VISITED_DIR="${HOME}/.claude/deep-research-claude"
VISITED_FILE="${VISITED_DIR}/chain-walk-${SESSION_ID}.json"

# Stale-cleanup: delete chain-walk-*.json files older than 1 hour
mkdir -p "${VISITED_DIR}"
find "${VISITED_DIR}" -name 'chain-walk-*.json' -mmin +60 -delete 2>/dev/null || true

# Create the new visited-set file with empty visited array
"$PY" -c "
import json, sys
data = {'session_id': sys.argv[1], 'started_at': __import__('datetime').datetime.utcnow().isoformat() + 'Z', 'visited': []}
open(sys.argv[2], 'w').write(json.dumps(data, indent=2))
" "${SESSION_ID}" "${VISITED_FILE}"

echo "Session ID: ${SESSION_ID}"
echo "Visited-set: ${VISITED_FILE}"
```

---

## Step 4 — Walk direct_deps

For each dep in `direct_deps` (DR declares one: `coordinator-claude`, severity `soft`):

### 4a. Read the visited-set and skip if already claimed

```bash
PY="$(command -v python3 || command -v python)"; [ -n "$PY" ] || { echo "no python3/python on PATH" >&2; exit 1; }
"$PY" -c "
import json, sys
data = json.load(open(sys.argv[1]))
print('already_visited' if sys.argv[2] in data['visited'] else 'proceed')
" "${VISITED_FILE}" "<dep-id>"
```

If `already_visited`, log "already walking `<dep-id>`, skipping" and continue to the next dep.

### 4b. Run implicit sibling-presence check

Check whether `../<sibling_dir_name>` exists relative to the consumer repo's parent directory. The manifest declares `sibling_dir_name: "coordinator-claude"` for this dep.

```bash
# Resolve sibling path
REPO_PARENT="$(dirname "${REPO_ROOT}")"
SIBLING_PATH="${REPO_PARENT}/coordinator-claude"
```

For the **flat publish-repo** layout, `REPO_PARENT` is the directory that also contains the `deep-research-claude/` checkout; sibling check looks for a `coordinator-claude/` at the same level.

For the **nested working-repo** layout, `REPO_PARENT` is `plugins/coordinator-claude/`; sibling path resolves to `plugins/coordinator/` — the coordinator plugin sub-tree. The functional probe for DR's coord dep checks for `plugins/coordinator/CLAUDE.md`, which exists in the working-repo. The presence check should accommodate this: if the standard sibling path does not exist, also check `${PLUGIN_ROOT}/../coordinator/` (nested layout adaptation).

### 4c. Run the functional probe

The manifest declares `functional_probe: {kind: "file_exists", path: "coordinator/CLAUDE.md"}` for this dep.

In the flat publish-repo: the probe path resolves relative to the coordinator sibling repo root.
In the nested working-repo: the probe path resolves relative to the repo root (which contains `plugins/coordinator/CLAUDE.md`).

```bash
# Probe result
if [ -f "${SIBLING_PATH}/coordinator/CLAUDE.md" ] || \
   [ -f "${REPO_ROOT}/../coordinator/CLAUDE.md" ]; then
  PROBE_STATUS="present"
else
  PROBE_STATUS="missing"
fi
echo "Probe status for coordinator-claude: ${PROBE_STATUS}"
```

### 4d. Handle severity = soft

Per contract § Severity semantics, a **soft** dep that is missing triggers: warn loudly, offer to walk the dep chain and install, proceed if declined.

**Dep present (probe passes):**
```
coordinator-claude: present — continuing.
```

**Dep missing (probe fails):**
```
WARNING — soft dep missing: coordinator-claude

coordinator-claude is recommended but not required. Without it, certain
context-sharing features between the coordinator and deep-research pipelines
will not be available (the coordinator surfaces /deep-research:install at
/workstream-start; DR reports back to coordinator's session state).

To install coordinator-claude now, clone and set up:
  git clone https://github.com/dbc-oduffy/coordinator-claude <sibling-path>
  # then run /coordinator:setup

To proceed without coordinator-claude, respond: proceed
```

If the user declines to install the dep (or if `--skip-dep-check` + `--accept-missing-deps-risk` are both present in `$ARGUMENTS`), proceed with a one-line acknowledgment: "Proceeding without coordinator-claude (soft dep, user accepted)."

If only ONE of the two override flags is present, exit with remediation (mirrors contract exit-code 93): "Both `--skip-dep-check` AND `--accept-missing-deps-risk` must be passed together to override the dep check. Passing only one is not valid."

---

## Step 5 — Dispatch the chain-walker subagent for present deps

When a dep is present (probe passes), atomically append its ID to the visited-set before dispatching:

```bash
PY="$(command -v python3 || command -v python)"; [ -n "$PY" ] || { echo "no python3/python on PATH" >&2; exit 1; }
"$PY" -c "
import json, os, sys
p = sys.argv[1]
d = json.load(open(p))
d['visited'].append(sys.argv[2])
json.dump(d, open(p, 'w'), indent=2)
" "${VISITED_FILE}" "<dep-id>"
```

Then dispatch a chain-walker subagent using the prompt template at:
```
scripts/lib/chain_walker_subagent_prompt.txt
```

Template substitution variables (per contract § Constructed-prompt template):

| Variable | Value |
|---|---|
| `$UPSTREAM_ID` | `coordinator-claude` |
| `$SIBLING_PATH` | Resolved absolute path of the sibling repo |
| `$SESSION_ID` | The UUID generated in Step 3 |
| `$CONSUMER_INSTALL_ARGS` | Space-joined `consumer_install_args` from DR's manifest DirectDep entry (empty for coordinator-claude: `""`) |

The dispatched subagent:
1. Reads the visited-set at `~/.claude/deep-research-claude/chain-walk-${SESSION_ID}.json`
2. Checks for the upstream dep before cloning
3. Appends to the visited-set before recursing
4. Composes the v2 invocation per contract § Walker composition: `$CONSUMER_INSTALL_ARGS --i-am-agent <upstream-override-flag-1> <upstream-override-flag-2>`
5. Recurses for the upstream's own `direct_deps`

**Out-of-scope for dispatched subagents:** DO NOT modify files, commit, or push. Read-only probe — the chain-walker's job is to READ upstream manifests and recursively walk deps, not to install or mutate state in other repos.

### Exit-code handling

| Exit code | Classification | Action |
|---|---|---|
| 0 | success | Log "coordinator-claude: walk complete" and continue |
| 11 / 12 | **actionable-stop** (gh unauthenticated / uv missing) | Surface remediation and halt walk |
| 92 / 93 | **invocation bug** | Surface as internal walker error — the composition logic regressed |
| other non-zero | generic failure | Report last 20 lines of output; halt or continue per severity |

---

## Step 6 — Terminal report with live Claude-Code-integration validation

<!-- spec-backlink: docs/plans/2026-06-24-install-baton-completeness-claude-code-validation.md § C6 -->

After walking all deps, print a structured summary followed by an explicit **running-in-Claude-Code** validation assert. The distinction between install-surface-completeness and running-in-Claude-Code is defined in `coordinator/docs/wiki/install-surface-completeness.md § Running-in-Claude-Code`; this step operationalises it for deep-research-claude.

```
## /deep-research:setup — chain step 4 of 5

Manifest: plugins/deep-research/docs/install/agent-install-manifest.json
Contract version: <agent_install_contract_version from the walked manifest>
Layout: <flat | nested>
Session ID: <uuid>

### Dependency walk

| Dep | Severity | Probe | Action |
|-----|----------|-------|--------|
| coordinator-claude | soft | <present / missing> | <walked / skipped / user-accepted-absent> |

### Result

<All deps satisfied — deep-research-claude install chain complete.>
OR
<Soft dep(s) absent but user accepted — proceeding.>
OR
<Walk halted: <reason>>
```

### 6a — Plugin-local prerequisite check (`--check-only`)

If the walk completed without halting, run `/deep-research:install --check-only` to verify the plugin-local prerequisites (Agent Teams env var, pipeline availability) are also satisfied, and include the result in the terminal report.

### 6b — Live Claude-Code-integration validation

This section performs the running-in-Claude-Code validation for deep-research-claude. Work through the three axes in order: **restart-batch items first** (see 6b-i), then live assertions (6b-ii, 6b-iii).

Classification follows `coordinator/docs/wiki/install-surface-completeness.md § Discriminator`:
- **restart-gated-expected** — ✘ after the settle window but no load-bearing restart has occurred since config-write → surface in the restart-batch block; do NOT count as failure.
- **configured-but-broken** — ✘ after the settle window AND after the load-bearing restart → **fail loud** (emit a ✘ FAIL line and abort the "complete" verdict).

#### 6b-i — restart-batch (emit up front, before any live assertions)

Before running any live checks, collect ALL items that are `restart-gated-expected` and emit them as ONE consolidated block:

```
### restart-batch — restart required before re-validating

The following deep-research-claude items require ONE Claude Code restart:

  [ ] <item-1 description>
  [ ] <item-2 description>
  ...

→ Restart Claude Code now, then re-run /deep-research:setup to re-validate.
   (These are restart-gated-expected, not configured-but-broken — see
    coordinator/docs/wiki/install-surface-completeness.md § Running-in-Claude-Code)
```

If no restart-gated items exist, omit this block entirely.

#### 6b-ii — Agent Teams env var

Check whether the `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` env var is set and live in the current Claude Code session environment:

```bash
if [ "${CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS}" = "1" ]; then
  echo "AGENT_TEAMS_STATUS=live"
else
  echo "AGENT_TEAMS_STATUS=absent_or_unset"
fi
```

Classification:
- **Present (`= "1"`)** → ✓ Agent Teams live.
- **Absent / unset** — determine the restart-occurred status (did a restart occur after writing `settings.json`?). See `coordinator/docs/wiki/install-surface-completeness.md § Restart discriminator` for the settle-window + restart-occurred axis used to classify restart-gated-expected vs. configured-but-broken.
  <!-- Review: code-reviewer — F12: added cross-ref to wiki § Restart discriminator -->
  - If no restart has occurred since `settings.json` was written → **restart-gated-expected**: add to the restart-batch block above; do NOT fail.
  - If a restart has already occurred and the var is still absent → **configured-but-broken**: emit `✘ FAIL: CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS not set after restart. All deep-research pipelines will fail. Remediation: add "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" under the "env" key in settings.json, then restart.`

#### 6b-iii — DR skill discovery preconditions

<!-- negative-spec: do NOT attempt to shell-invoke a skill to test it — skill invocability is model-driven, not bash-testable (the Staff Engineer F1, plan § Anti-scope). Discovery preconditions only. -->

For each DR skill file under `skills/` (at minimum: `setup/SKILL.md`, `research/SKILL.md`, `install/SKILL.md`), assert the three discovery preconditions:

1. **File parses** — the SKILL.md file exists and is readable (non-zero byte file).
2. **`description:` trigger phrases present** — the frontmatter `description:` field is non-empty and contains at least one trigger phrase (a human-readable phrase that Claude Code can match to invoke the skill).
3. **Plugin enabled** — the deep-research plugin appears in `settings.json` `enabledPlugins` (or equivalent enablement surface for the current layout).

```bash
PY="$(command -v python3 || command -v python)"; [ -n "$PY" ] || { echo "no python3/python on PATH" >&2; exit 1; }

SKILLS_DIR="${PLUGIN_ROOT}/skills"
SETTINGS_JSON="${HOME}/.claude/settings.json"

echo "=== DR skill discovery preconditions ==="

# Precondition 3 (plugin enabled) — check once, applies to all skills
PLUGIN_ENABLED="false"
if [ -f "${SETTINGS_JSON}" ]; then
  ENABLED=$("$PY" -c "
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    plugins = d.get('enabledPlugins', [])
    # Accept full path or basename match for deep-research
    print('true' if any('deep-research' in str(p) for p in plugins) else 'false')
except Exception as e:
    print('error:' + str(e))
" "${SETTINGS_JSON}")
  PLUGIN_ENABLED="${ENABLED}"
fi

if [ "${PLUGIN_ENABLED}" = "true" ]; then
  echo "  plugin-enabled: ✓"
elif [ "${PLUGIN_ENABLED}" = "false" ]; then
  # Not enabled: restart-gated if no restart has occurred, configured-but-broken otherwise
  echo "  plugin-enabled: ✘ (deep-research not in enabledPlugins — see restart-batch if pre-restart, else configured-but-broken)"
else
  echo "  plugin-enabled: ✘ ERROR reading settings.json: ${PLUGIN_ENABLED}"
fi

# Preconditions 1 + 2: per-skill file-parse and description-field check
for SKILL_DIR in "${SKILLS_DIR}"/*/; do
  SKILL_FILE="${SKILL_DIR}SKILL.md"
  SKILL_NAME="$(basename "${SKILL_DIR}")"
  if [ ! -s "${SKILL_FILE}" ]; then
    echo "  ${SKILL_NAME}: ✘ FAIL (configured-but-broken) — SKILL.md missing or empty at ${SKILL_FILE}"
    continue
  fi
  # Extract description: field from YAML frontmatter (between first --- pair)
  DESC=$("$PY" -c "
import sys, re
content = open(sys.argv[1]).read()
m = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
if not m:
    print('')
    sys.exit(0)
fm = m.group(1)
# Review: code-reviewer — F5: match coordinator:setup Probe 3's regex — handle both
# single-quoted and double-quoted description: values (SKILL.md files use both forms).
desc_match = re.search(r'description:\s*[\"\'](.*?)[\"\']', fm, re.DOTALL)
if not desc_match:
    desc_match = re.search(r'description:\s*(.+)', fm)
if desc_match:
    print(desc_match.group(1).strip())
else:
    print('')
" "${SKILL_FILE}")
  if [ -z "${DESC}" ]; then
    echo "  ${SKILL_NAME}: ✘ FAIL (configured-but-broken) — no description: trigger phrase in frontmatter of ${SKILL_FILE}"
  else
    echo "  ${SKILL_NAME}: ✓ (description trigger present)"
  fi
done
```

Any skill whose `description:` field is missing or empty is **configured-but-broken** — it cannot be discovered by Claude Code and is therefore not running-in-Claude-Code, regardless of whether the file is present on disk. Emit a ✘ FAIL for each such skill.

A plugin-enabled status of `false` after a restart is **configured-but-broken** (add to the manifest, restart). A plugin-enabled status of `false` with no prior restart is **restart-gated-expected** (add to the restart-batch block in 6b-i).

### 6c — Consolidated running-in-Claude-Code verdict

After running all checks in 6b, emit one of:

```
### deep-research-claude: running-in-Claude-Code status

✓ All live checks passed — deep-research-claude is validated running-in-Claude-Code.
```

or, if there are restart-gated items but no configured-but-broken failures:

```
### deep-research-claude: running-in-Claude-Code status

⚠ RESTART REQUIRED — see restart-batch block above. Re-validate after restart.
  (No configured-but-broken failures detected; items above are restart-gated-expected.)
```

or, if any configured-but-broken failure was detected:

```
### deep-research-claude: running-in-Claude-Code status

✘ FAIL — configured-but-broken items detected (see ✘ FAIL lines above).
  install-surface-completeness ≠ running-in-Claude-Code for this installation.
  Fix the above items before treating deep-research-claude as operational.
```

The verdict must always be one of these three shapes — no silent-pass on partial checks (vacuous-pass anti-pattern, `coordinator/docs/wiki/install-surface-completeness.md § Vacuous-pass anti-pattern`).

---

## Override flags

Both flags from the manifest's `override_flags` section must be passed TOGETHER to skip dep checking:
- `--skip-dep-check` (contract-locked name per § Schema reference)
- `--accept-missing-deps-risk` (DR's repo-specific value for `accept_hallucination_risk`)

Passing only one produces an error and exits (mirrors contract exit-code 93 behavior). Read-only flags (`--help`, `--version`, `--phase-list`, `--last-status`, `--check`) are serviced before any dep-walking and do not trigger the override check.

---

## Negative-spec

<!-- negative-spec: this skill does NOT seed install-leg spinoffs into ~/.claude/state/handoffs/. Coordinator seeds DR's spinoff from its own template. Writing to state/handoffs/ from this skill would violate contract § Install-spinoff layer / The two roles and plan NG5. -->
<!-- negative-spec: this skill does NOT replace /deep-research:install. The plugin-local bootstrap (Agent Teams, NotebookLM auth, pipeline availability) is /deep-research:install's domain; /deep-research:setup is chain-walking only. -->
<!-- negative-spec: the visited-set path is ~/.claude/deep-research-claude/chain-walk-*.json (NOT ~/.deep-research-claude/). The ~/.claude/ prefix is canonical per contract § Visited-set protocol. -->
