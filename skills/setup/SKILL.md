---
name: setup
description: "coordinator-claude install-chain walker (chain step 5 of 5 — DAG root; no upstream deps to walk). Reads the install manifest, observes empty direct_deps, emits the DAG-root terminal banner, and exits 0. Not to be confused with coordinator:install (OSS plugin install of the coordinator package) or coordinator:repo-setup (consumer-project first-time setup of the coordinator integration). Trigger phrases: /coordinator:setup, set up coordinator-claude, run the install chain for coordinator."
allowed-tools: ["Read", "Bash"]
argument-hint: "[--skip-dep-check --accept-missing-deps-risk]"
---

<!-- spec-backlink: archive/specs/2026-06/2026-06-15-coordinator-install-chain-application-phase-b.md § C4 -->

# /coordinator:setup

Chain-walker skill for coordinator-claude (chain position 5 of 5 — DAG root). This skill is the agentic entry-point for the install-chain contract for the coordinator plugin. It reads the install manifest, walks the `direct_deps` list (which is empty for coordinator-claude — it is the DAG root), and emits the DAG-root terminal banner. It does NOT replace `coordinator:install` (the OSS plugin bootstrap for the coordinator package) or `coordinator:repo-setup` (the consumer-project first-time integration setup) — those concerns belong to their respective skills.

**Disambiguation — three coexisting `/coordinator:*` verbs:**

- `/coordinator:setup` — **this skill.** The install-chain walker, required by the agent-install-contract. Reports chain-walk status and verifies the manifest is structurally sound. Invoked by the install-chain DAG walker when a consumer resolves coordinator-claude as a dep.
- `coordinator:install` — installs the coordinator plugin package into a consumer's `~/.claude/` environment. OSS-user-facing bootstrap. Unrelated to the install-chain DAG contract.
- `coordinator:repo-setup` — first-time setup of the coordinator integration into a consumer project repo (generates coordinator scaffolding, sets up hooks, creates initial state files). Consumer-project-facing. Unrelated to the install-chain DAG contract.

These three verbs coexist without collision. The `:setup` verb is the established cross-plugin convention across DR, project-rag, ue-addon, and now coordinator-claude.

**IMPORTANT — `setup_skill` is informational metadata, not the dispatch primitive.** The manifest field `setup_skill: /coordinator:setup` tells humans what to type. Dispatched subagents cannot expand slash commands; this skill uses direct Bash calls instead of subagent dispatch (no deps to walk — no subagent is needed).

---

## Out-of-scope actions for all dispatched agents in this skill

**Destructive-action prohibition (verbatim from `coordinator-tripwires.md` § Destructive-action prohibition):**

DO NOT run `gh pr create`, `gh pr merge`, `git push origin main`, `gh release create`, or any `gh` command that mutates GitHub state beyond pushing the current branch. DO NOT commit to `main` directly. If you find yourself reaching for a merge, STOP and surface the question to the EM in your final reply.

**Additional out-of-scope items specific to this skill:**

- Writing files OUTSIDE `plugins/coordinator/` (this skill owns nothing in the DR, example-game-repo, ue-addon, or project-rag trees)
- Modifying `docs/install/agent-install-manifest.json` at runtime (manifest is a static artifact read by the walker, not mutated by it)
- Touching any example-game-repo tree, ue-addon tree, or project-rag tree (deep-research content is now bundled inside coordinator — its commands/agents/pipelines live under `plugins/coordinator/`, which is this skill's own tree; but this skill must not restructure or rename DR content without a dedicated plan)
- Any `git commit` or `git push` operation

<!-- Spinoff-schema awareness: N/A — this skill does not author handoffs or spinoffs. -->
<!-- Recheck-marker semantics: N/A — this skill is not cadenced; it is invoked on demand. -->

---

## Discovery-surface integration

This skill announces itself via its `description:` frontmatter field. The description contains the trigger phrases and is surfaced by Claude Code's skill discovery. Discovery-surface integration with `/workstream-start` (Step 1 plugin-bootstrap surfacing) is a follow-up item — do NOT edit `/workstream-start` in this chunk.

**Platform-vocabulary collision check:** `:setup` is the established verb across coordinator-claude, example-game-repo, and project-rag-ue-addon. No collision; consistent verb. (deep-research no longer has a separate plugin or `:setup` verb — its content is bundled into coordinator.) The coexistence with `coordinator:install` and `coordinator:repo-setup` is documented above. ✓

---

## Step 1 — Detect layout (flat publish-repo vs. nested working-repo)

Determine whether this skill is running inside the nested working-repo (under `~/.claude/plugins/coordinator/`) or the flat publish-repo (a standalone `coordinator-claude/` checkout).

```bash
# Heuristic mirrors setup.sh layout detection.
# AGENT.md lives at docs/install/AGENT.md relative to the plugin root.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
# Skills live at <plugin-root>/skills/setup/SKILL.md; plugin root is two levels up
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

FLAT_AGENT_MD="${PLUGIN_ROOT}/docs/install/AGENT.md"

if [ -f "${FLAT_AGENT_MD}" ]; then
  LAYOUT="flat"
  REPO_ROOT="${PLUGIN_ROOT}"
else
  # Nested working-repo layout; PLUGIN_ROOT is plugins/coordinator-claude/coordinator
  LAYOUT="nested"
  REPO_ROOT="${PLUGIN_ROOT}"
fi

MANIFEST="${REPO_ROOT}/docs/install/agent-install-manifest.json"
echo "Layout: ${LAYOUT}"
echo "Manifest path: ${MANIFEST}"
```

Report the detected layout. If the manifest does not exist, surface the error with remediation:
`"Manifest not found at ${MANIFEST}. Re-run after the install surface has been committed (plugins/coordinator/docs/install/agent-install-manifest.json)."`

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
- `agent_install_contract_version` — must be 1, 2, or 3 (reject anything outside `{1, 2, 3}` with a remediation message)
- `repo_id` — should be `"coordinator-claude"`
- `direct_deps` — the list to walk (coordinator-claude declares `[]` — empty by design; it is the DAG root)
- `override_flags` — the flag pair names for consent-gate invocations

If the manifest fails JSON parsing, surface the parse error and exit. Do not continue with a corrupt manifest.

---

## Step 3 — Initialise the visited-set (contract § Visited-set protocol)

The visited-set is a disk-resident file used for diamond-DAG and cycle detection across recursive subagent dispatches. Coordinator's visited-set lives at:

```
<settings-home>/coordinator-claude/chain-walk-<session-id>.json
```

where `<settings-home>` = `${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}` (relocated 2026-07-06 off `~/.claude/` — see agent-install-contract.md § Visited-set protocol).

```bash
SESSION_ID="$(python3 -c 'import uuid; print(str(uuid.uuid4()))')"

# Compute settings-home inline — cold-safe, no bin dependency.
# Matches the canonical expression in agent-install-contract.md § Visited-set protocol.
VISITED_DIR="${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/coordinator-claude"
VISITED_FILE="${VISITED_DIR}/chain-walk-${SESSION_ID}.json"

# Stale-cleanup: delete chain-walk-*.json files older than 1 hour
mkdir -p "${VISITED_DIR}"
find "${VISITED_DIR}" -name 'chain-walk-*.json' -mmin +60 -exec rm -f {} + 2>/dev/null || true

# Create the new visited-set file with empty visited array
python3 -c "
import json, sys
data = {'session_id': sys.argv[1], 'started_at': __import__('datetime').datetime.utcnow().isoformat() + 'Z', 'visited': []}
open(sys.argv[2], 'w').write(json.dumps(data, indent=2))
" "${SESSION_ID}" "${VISITED_FILE}"

echo "Session ID: ${SESSION_ID}"
echo "Visited-set: ${VISITED_FILE}"
```

---

## Step 4 — Walk direct_deps AND resolve system prerequisites (DAG-root path)

For coordinator-claude, `direct_deps` is `[]` — the manifest declares no upstream dependencies because coordinator-claude IS the DAG root. As of C3 (2026-06-23), the chain-walk default body also runs the system-prerequisite gate (`_co_run_prereq_gate post-consumer`) so that the DAG-root node reports its own machine-level prerequisites alongside the (empty) dep list.

The walk proceeds as follows:

```bash
# Python is pre-verified (hard exit if absent — the existing hard gate).
# This is the SOLE hard gate on the chain-walk path (post-consumer mode).

# System-prerequisite gate (post-consumer mode).
# Severity demotion applied inside the gate:
#   python     → hard     (unchanged — pre-existing hard gate)
#   gh         → advisory (demoted from hard, no exit-code regression)
#   node       → advisory (demoted from hard, no exit-code regression)
#   git        → advisory (demoted from hard, no exit-code regression)
#   clone_auth → advisory (demoted from semi-hard, no exit-code regression)
#   all others → advisory (already advisory in --preflight; no change)
# Advisory failures emit [WARN] rows to stderr but do NOT block exit 0.
bash scripts/setup.sh       # default body — calls _co_run_prereq_gate post-consumer
```

Because `direct_deps` is empty, the dep-probe loop inside the gate emits zero dep rows. The prereq probe rows (git, python, uv, gh, node, pwsh, ue, clone_auth, longpaths, git_lfs) ARE emitted; advisory failures print WARN but do not change the exit code.

**Override flags** — both flags must be passed TOGETHER to skip dep checking. Since there are no deps, the override flags are accepted but have no effect on the walk outcome. Passing only one of the two override flags still produces an error per contract exit-code 93 semantics (schema-conformance, even though no dep triggers the gate):

```bash
# Override flag validation (schema-conformance — even for empty direct_deps)
HAS_SKIP=0; HAS_RISK=0
for arg in "$@"; do
  [ "$arg" = "--skip-dep-check" ] && HAS_SKIP=1
  [ "$arg" = "--accept-missing-deps-risk" ] && HAS_RISK=1
done

if [ "${HAS_SKIP}" -eq 1 ] && [ "${HAS_RISK}" -eq 0 ]; then
  echo "ERROR (exit 93): Both --skip-dep-check AND --accept-missing-deps-risk must be passed together. Passing only one is not valid." >&2
  exit 93
fi
if [ "${HAS_SKIP}" -eq 0 ] && [ "${HAS_RISK}" -eq 1 ]; then
  echo "ERROR (exit 93): Both --skip-dep-check AND --accept-missing-deps-risk must be passed together. Passing only one is not valid." >&2
  exit 93
fi
```

---

## Step 5 — Terminal report

After walking all deps (the empty list) and resolving system prerequisites, print a structured summary:

```
## /coordinator:setup — chain step 5 of 5

Manifest: plugins/coordinator/docs/install/agent-install-manifest.json
Contract version: 2
Layout: <flat | nested>
Session ID: <uuid>

### System prerequisite gate (post-consumer mode)

| Probe      | Severity | Result | Notes                                      |
|------------|----------|--------|--------------------------------------------|
| python     | hard     | PASS   | Python 3.11+ (the sole hard gate)          |
| gh         | advisory | PASS/WARN | demoted from hard; WARN does not block  |
| node       | advisory | PASS/WARN | demoted from hard; WARN does not block  |
| git        | advisory | PASS/WARN | demoted from hard; WARN does not block  |
| clone_auth | advisory | PASS/WARN | demoted from semi-hard; WARN does not block |
| uv/pwsh/ue/longpaths/git_lfs | advisory | PASS/WARN | advisory, no change |

### Dependency walk

| Dep | Severity | Probe | Action |
|-----|----------|-------|--------|
| (none) | — | — | direct_deps is empty — coordinator-claude is DAG root |

### Result

chain walk complete — coordinator-claude is DAG root

All deps satisfied (no deps declared). coordinator-claude install chain complete.
```

Exit 0 (advisory WARN rows from post-consumer gate do not affect exit code).

---

## Step 6 — Live Claude-Code-integration validation

<!-- spec-backlink: docs/plans/2026-06-24-install-baton-completeness-claude-code-validation.md § C5 -->

This step asserts that the coordinator plugin is **running-in-Claude-Code** — not just present on disk, but active as a live integration. See `docs/wiki/install-surface-completeness.md` § "Running-in-Claude-Code" for the canonical definition of "live integration" that this step validates against.

**What "running-in-Claude-Code" means for coordinator-claude** (no MCP server — three testable surfaces):

1. **Plugin enabled** — coordinator-claude is listed in `settings.json` (or the active enabledPlugins surface) and the entry is not disabled/overridden.
2. **Hooks registered and live** — the hooks this plugin registers (PreToolUse, PostToolUse, etc.) are present at their expected paths on disk and are included in the Claude Code hooks configuration.
3. **Skill discovery preconditions met** — a representative skill file exists, is parseable, and exposes a `description:` field with trigger phrases; the plugin being enabled is a necessary condition for the skill to be reachable by the model. **Note:** skills are model-invoked, not shell-invoked — the assertion here is discovery-preconditions-met, not shell execution. (the Staff Engineer F1: "a representative skill is invocable" was downgraded to discovery-preconditions.)

### Restart-batch up-front

Before running any live probes, collect all **restart-gated** items and emit them as a single consolidated block:

```
restart-batch (emit this block if any restart-gated items are found):
────────────────────────────────────────────────────────────────
The following items require a Claude Code restart to take effect.
Restart Claude Code NOW, then re-validate (re-run /coordinator:setup).
After restart, these items move from restart-gated-expected → live (or
configured-but-broken if they still fail).

  [restart-gated] <item description>
  ...
────────────────────────────────────────────────────────────────
```

Emit the restart-batch block **before** the per-item probe table. An empty restart-batch (no restart-gated items found) is omitted entirely — do not emit an empty block.

### Restart discriminator

Classify each failing probe using the settle-window + restart-occurred axis (defined in `docs/wiki/install-surface-completeness.md` § "Running-in-Claude-Code"):

- **restart-gated-expected** — probe fails AND no load-bearing restart has occurred since the relevant config was written → emit in the restart-batch block above; NOT a hard failure.
- **configured-but-broken** — probe fails AND a restart has already occurred (or settle window has elapsed post-restart) → fail loud (see below).
- **pending-settle** — probe fails within the settle window (e.g. first seconds after a config write) → re-probe once; if still failing after settle, reclassify as restart-gated-expected or configured-but-broken.

### Probe sequence

Run the following probes via Bash:

**Probe 1 — Plugin enabled in settings.json**

```bash
# Locate settings.json (Claude Code user settings — ~/.claude/settings.json is the canonical path)
SETTINGS="${HOME}/.claude/settings.json"
if [ ! -f "${SETTINGS}" ]; then
  echo "[WARN] settings.json not found at ${SETTINGS} — cannot verify plugin enablement" >&2
else
  # Check that coordinator-claude appears in enabledPlugins (or equivalent field)
  python3 -c "
import json, sys
d = json.load(open('${SETTINGS}'))
plugins = d.get('enabledPlugins', d.get('plugins', []))
enabled = any('coordinator' in str(p) for p in plugins)
print('PASS — coordinator plugin found in enabledPlugins' if enabled else 'FAIL — coordinator plugin NOT found in enabledPlugins')
sys.exit(0 if enabled else 1)
"
fi
```

A FAIL here that follows a config-write without a subsequent restart is **restart-gated-expected** — add to the restart-batch block. A FAIL after a restart is **configured-but-broken** — fail loud.

**Probe 2 — Hooks registered and live on disk**

```bash
# Review: code-reviewer — F4: re-derive PLUGIN_ROOT here so this block is self-contained
# when run independently (PLUGIN_ROOT is set in Step 1 but may not be in scope here).
# Skills live at <plugin-root>/skills/setup/SKILL.md; plugin root is two levels up from __this file__.
if [[ -z "${PLUGIN_ROOT:-}" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
  PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
fi

# Hooks live under ~/.claude/hooks/ or at the plugin-root hooks path.
# Check that at least one coordinator-owned hook file exists and is executable.
HOOKS_DIR="${HOME}/.claude/hooks"
PLUGIN_HOOKS_DIR="${PLUGIN_ROOT}/hooks"

# Review: code-reviewer — F6: check for specific coordinator-owned hooks named in
# hooks/hooks.json by path, not a blanket *.sh count (blanket passes vacuously when
# coordinator's hooks are absent but other *.sh files happen to exist).
HOOKS_JSON="${PLUGIN_HOOKS_DIR}/hooks.json"
COORDINATOR_HOOKS_MISSING=()
COORDINATOR_HOOKS_PRESENT=()

# Extract coordinator-owned hook script paths from hooks.json (scripts under hooks/scripts/ or hooks/ directly)
if [ -f "${HOOKS_JSON}" ]; then
  # Pull paths from "command" fields that reference ${CLAUDE_PLUGIN_ROOT}/hooks/
  HOOK_SCRIPTS=$(python3 -c "
import json, re, sys
data = json.load(open(sys.argv[1]))
paths = set()
def walk(obj):
    if isinstance(obj, dict):
        if 'command' in obj:
            m = re.search(r'\\\${CLAUDE_PLUGIN_ROOT}/hooks/(\S+\.sh)', obj['command'])
            if m: paths.add(m.group(1))
        for v in obj.values(): walk(v)
    elif isinstance(obj, list):
        for v in obj: walk(v)
walk(data)
for p in sorted(paths): print(p)
" "${HOOKS_JSON}" 2>/dev/null)
  while IFS= read -r rel_path; do
    [ -z "$rel_path" ] && continue
    full_path="${PLUGIN_HOOKS_DIR}/${rel_path}"
    if [ -f "${full_path}" ]; then
      COORDINATOR_HOOKS_PRESENT+=("${rel_path}")
    else
      COORDINATOR_HOOKS_MISSING+=("${rel_path}")
    fi
  done <<< "${HOOK_SCRIPTS}"
else
  echo "[WARN] hooks.json not found at ${HOOKS_JSON} — cannot verify coordinator-specific hooks" >&2
fi

if [ "${#COORDINATOR_HOOKS_MISSING[@]}" -gt 0 ]; then
  echo "FAIL — coordinator hook(s) named in hooks.json are missing from disk:" >&2
  for h in "${COORDINATOR_HOOKS_MISSING[@]}"; do echo "  missing: ${PLUGIN_HOOKS_DIR}/${h}" >&2; done
  exit 1
elif [ "${#COORDINATOR_HOOKS_PRESENT[@]}" -gt 0 ]; then
  echo "PASS — ${#COORDINATOR_HOOKS_PRESENT[@]} coordinator-owned hook file(s) verified present on disk"
else
  echo "[WARN] No coordinator-owned hook scripts detected in hooks.json" >&2
fi
```

Coordinator-owned hook files absent from disk → **configured-but-broken** (fail loud). Hook files present but not yet loaded by a running Claude Code session → **restart-gated-expected** (emit in restart-batch; advisory WARN).

**Probe 3 — Skill discovery preconditions (representative skill)**

```bash
# Review: code-reviewer — F4: re-derive PLUGIN_ROOT here so this block is self-contained
# when run independently (PLUGIN_ROOT is set in Step 1 but may not be in scope here).
if [[ -z "${PLUGIN_ROOT:-}" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
  PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
fi

# Use this skill itself as the representative: skills/setup/SKILL.md
SKILL_FILE="${PLUGIN_ROOT}/skills/setup/SKILL.md"

if [ ! -f "${SKILL_FILE}" ]; then
  echo "FAIL — representative skill file missing: ${SKILL_FILE}" >&2
  exit 1
fi

# Verify the file is parseable and has a description: field with trigger phrases
python3 -c "
import re, sys
content = open('${SKILL_FILE}').read()
# Extract YAML frontmatter (between first two --- markers)
m = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
if not m:
    print('FAIL — skill file has no YAML frontmatter')
    sys.exit(1)
fm = m.group(1)
desc_match = re.search(r'description:\s*[\"\'](.*?)[\"\']', fm, re.DOTALL)
if not desc_match:
    desc_match = re.search(r'description:\s*(.+)', fm)
if not desc_match:
    print('FAIL — no description: field found in frontmatter')
    sys.exit(1)
desc = desc_match.group(1).strip()
if not desc:
    print('FAIL — description: field is empty')
    sys.exit(1)
# Check for at least one trigger phrase (non-empty description is sufficient)
print(f'PASS — description field present with trigger phrases ({len(desc)} chars)')
sys.exit(0)
"
```

A missing or unparseable skill file is always **configured-but-broken** (fail loud — a skill file cannot be restart-gated, it either exists on disk or it doesn't). The plugin being enabled (Probe 1) is a precondition for the model to reach this skill; an advisory WARN from Probe 1 propagates here.

### Validation summary table

After running all probes, emit a summary table:

```
### Step 6 — Live Claude-Code-integration validation (running-in-Claude-Code)

| Probe | Surface | Result | Classification |
|-------|---------|--------|----------------|
| Plugin enabled | settings.json enabledPlugins | PASS/WARN/FAIL | live / restart-gated-expected / configured-but-broken |
| Hooks live on disk | ~/.claude/hooks/ | PASS/WARN/FAIL | live / restart-gated-expected / configured-but-broken |
| Skill discovery preconditions | skills/setup/SKILL.md | PASS/WARN | live / configured-but-broken |
```

**Exit-code semantics (extends, but is NOT identical to, the Step 4/5 advisory-WARN model — `configured-but-broken` is the exception):**
<!-- Review: code-reviewer — F8: reworded to clarify this step is NOT fully consistent with Steps 4/5; configured-but-broken exits non-zero here, which is an exception to the advisory model -->

- `configured-but-broken` findings → emit `[ERROR]` to stderr and exit non-zero. The install is incomplete; the chain-walk result is NOT valid. **This is the exception to the advisory model — it exits non-zero.**
- `restart-gated-expected` findings → emit as WARN rows in the summary table and in the restart-batch block above; do NOT change the exit code (advisory, per § Post-Consumer Gates).
- All probes PASS → emit the summary table and exit 0 normally.

The advisory-WARN semantics are inherited from Steps 4/5 for `restart-gated-expected` items: WARN rows do not change the exit code. The distinction is: a `restart-gated-expected` item is not a failure — it is an expected transient state that resolves after a restart. A `configured-but-broken` item is a real failure that the operator must fix — and it exits non-zero, unlike the pure-advisory Steps 4/5 model.

---

## Override flags

Both flags from the manifest's `override_flags` section must be passed TOGETHER to skip dep checking:
- `--skip-dep-check` (contract-locked name per § Schema reference)
- `--accept-missing-deps-risk` (coord's repo-specific value for `accept_hallucination_risk`)

Passing only one produces an error and exits (mirrors contract exit-code 93 behavior). Read-only flags (`--help`, `--version`, `--phase-list`, `--last-status`, `--check`) are serviced before any dep-walking and do not trigger the override check.

---

## Negative-spec

<!-- negative-spec: this skill does NOT dispatch subagents. coordinator-claude has no direct_deps; there is nothing to walk recursively. The visited-set is initialised for contract-conformance only. -->
<!-- negative-spec: this skill does NOT replace coordinator:install (OSS plugin install of the coordinator package) or coordinator:repo-setup (consumer-project first-time setup). Three distinct verbs, three distinct concerns — see disambiguation prose above. -->
<!-- negative-spec: this skill does NOT seed install-leg spinoffs into the install-baton rendezvous (`$(coordinator-settings-home)/state/handoffs/`, formerly `~/.claude/state/handoffs/` pre-2026-07-08 relocation). Spinoffs are PM-authorized via /spinoff only. -->
<!-- negative-spec: the visited-set path is <settings-home>/coordinator-claude/chain-walk-*.json where <settings-home> = ${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}. The ~/.claude/ prefix was retired 2026-07-06 (durable-substrate-to-settings-home plan); the settings-home prefix is now canonical per agent-install-contract.md § Visited-set protocol. -->
