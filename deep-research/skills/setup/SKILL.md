---
name: setup
description: "deep-research-claude install-chain walker (chain step 4 of 5). Walk the direct_deps declared in docs/install/agent-install-manifest.json, probe coordinator-claude (soft dep), dispatch the chain-walker subagent, and report. Trigger phrases: /deep-research:setup, set up deep-research, run the install chain for deep-research."
allowed-tools: ["Read", "Bash", "Agent"]
argument-hint: "[--skip-dep-check --accept-missing-deps-risk]"
---

<!-- spec-backlink: docs/plans/2026-06-15-deep-research-install-chain-application-phase-b.md § C4 -->

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

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT}"
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
- `agent_install_contract_version` — must be 1 or 2 (reject anything outside `{1, 2}` with a remediation message)
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
# Generate a session UUID (stdlib only — no python -c uuid fallback needed; date+$$ is sufficient for uniqueness)
SESSION_ID="$(python -c 'import uuid; print(str(uuid.uuid4()))')"

VISITED_DIR="${HOME}/.claude/deep-research-claude"
VISITED_FILE="${VISITED_DIR}/chain-walk-${SESSION_ID}.json"

# Stale-cleanup: delete chain-walk-*.json files older than 1 hour
mkdir -p "${VISITED_DIR}"
find "${VISITED_DIR}" -name 'chain-walk-*.json' -mmin +60 -delete 2>/dev/null || true

# Create the new visited-set file with empty visited array
python -c "
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
python -c "
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

The manifest declares `functional_probe: {kind: "file_exists", path: "plugins/coordinator/CLAUDE.md"}` for this dep.

In the flat publish-repo: the probe path resolves relative to the coordinator sibling repo root.
In the nested working-repo: the probe path resolves relative to the repo root (which contains `plugins/coordinator/CLAUDE.md`).

```bash
# Probe result
if [ -f "${SIBLING_PATH}/plugins/coordinator/CLAUDE.md" ] || \
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
python -c "
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

## Step 6 — Terminal report

After walking all deps, print a structured summary:

```
## /deep-research:setup — chain step 4 of 5

Manifest: plugins/deep-research/docs/install/agent-install-manifest.json
Contract version: 2
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

If the walk completed without halting, run `/deep-research:install --check-only` to verify the plugin-local prerequisites (Agent Teams env var, pipeline availability) are also satisfied, and include the result in the terminal report.

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
