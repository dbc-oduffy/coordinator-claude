---
name: setup
description: "coordinator-claude install-chain walker (chain step 5 of 5 — DAG root; no upstream deps to walk). Reads the install manifest, observes empty direct_deps, emits the DAG-root terminal banner, and exits 0. Not to be confused with coordinator:install (OSS plugin install of the coordinator package) or coordinator:repo-setup (consumer-project first-time setup of the coordinator integration). Trigger phrases: /coordinator:setup, set up coordinator-claude, run the install chain for coordinator."
allowed-tools: ["Read", "Bash"]
argument-hint: "[--skip-dep-check --accept-missing-deps-risk]"
---

<!-- spec-backlink: docs/plans/2026-06-15-coordinator-install-chain-application-phase-b.md § C4 -->

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

- Writing files OUTSIDE `plugins/coordinator/` (this skill owns nothing in the DR, holodeck, ue-addon, or project-rag trees)
- Modifying `docs/install/agent-install-manifest.json` at runtime (manifest is a static artifact read by the walker, not mutated by it)
- Touching `plugins/deep-research/`, any holodeck tree, ue-addon tree, or project-rag tree
- Any `git commit` or `git push` operation

<!-- Spinoff-schema awareness: N/A — this skill does not author handoffs or spinoffs. -->
<!-- Recheck-marker semantics: N/A — this skill is not cadenced; it is invoked on demand. -->

---

## Discovery-surface integration

This skill announces itself via its `description:` frontmatter field. The description contains the trigger phrases and is surfaced by Claude Code's skill discovery. Discovery-surface integration with `/workstream-start` (Step 1 plugin-bootstrap surfacing) is a follow-up item — do NOT edit `/workstream-start` in this chunk.

**Platform-vocabulary collision check:** `:setup` is the established verb across coordinator-claude, holodeck, project-rag-ue-addon, and deep-research-claude. No collision; consistent verb. The coexistence with `coordinator:install` and `coordinator:repo-setup` is documented above. ✓

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
- `agent_install_contract_version` — must be 1 or 2 (reject anything outside `{1, 2}` with a remediation message)
- `repo_id` — should be `"coordinator-claude"`
- `direct_deps` — the list to walk (coordinator-claude declares `[]` — empty by design; it is the DAG root)
- `override_flags` — the flag pair names for consent-gate invocations

If the manifest fails JSON parsing, surface the parse error and exit. Do not continue with a corrupt manifest.

---

## Step 3 — Initialise the visited-set (contract § Visited-set protocol)

The visited-set is a disk-resident file used for diamond-DAG and cycle detection across recursive subagent dispatches. Coordinator's visited-set lives at:

```
~/.claude/coordinator-claude/chain-walk-<session-id>.json
```

```bash
SESSION_ID="$(python3 -c 'import uuid; print(str(uuid.uuid4()))')"

VISITED_DIR="${HOME}/.claude/coordinator-claude"
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

## Step 4 — Walk direct_deps (observe empty list → DAG-root path)

For coordinator-claude, `direct_deps` is `[]` — the manifest declares no upstream dependencies because coordinator-claude IS the DAG root. The walk proceeds as follows:

```bash
# Read direct_deps count from manifest
DEP_COUNT=$(python3 -c "
import json, sys
m = json.load(open(sys.argv[1]))
print(len(m.get('direct_deps', [])))
" "${MANIFEST}")

echo "direct_deps count: ${DEP_COUNT}"

if [ "${DEP_COUNT}" -eq 0 ]; then
  echo "No direct_deps declared — coordinator-claude is the DAG root."
  echo "chain walk complete — coordinator-claude is DAG root"
  exit 0
fi
```

Because `direct_deps` is empty, the loop body never executes and no subagent dispatch is needed. The skill exits 0 at the DAG-root early-exit path above.

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

After walking all deps (the empty list), print a structured summary:

```
## /coordinator:setup — chain step 5 of 5

Manifest: plugins/coordinator/docs/install/agent-install-manifest.json
Contract version: 2
Layout: <flat | nested>
Session ID: <uuid>

### Dependency walk

| Dep | Severity | Probe | Action |
|-----|----------|-------|--------|
| (none) | — | — | direct_deps is empty — coordinator-claude is DAG root |

### Result

chain walk complete — coordinator-claude is DAG root

All deps satisfied (no deps declared). coordinator-claude install chain complete.
```

Exit 0.

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
<!-- negative-spec: this skill does NOT seed install-leg spinoffs into ~/.claude/state/handoffs/. Spinoffs are PM-authorized via /spinoff only. -->
<!-- negative-spec: the visited-set path is ~/.claude/coordinator-claude/chain-walk-*.json (NOT ~/.coordinator-claude/). The ~/.claude/ prefix is canonical per contract § Visited-set protocol. -->
