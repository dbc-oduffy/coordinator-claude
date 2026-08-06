---
description: "PM-GATED, never from a subagent. Deep research — web, repo, or structured."
allowed-tools: ["Agent", "Read", "Write", "Edit", "Bash", "Glob", "Grep", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet", "SendMessage"]
argument-hint: "--mode={web,repo,structured} <args> [--deepest]"
---

# Deep Research — Unified Entry Point

This is the single entry point for all deep-research pipelines. Route by `--mode`.

## Arguments

`$ARGUMENTS`:
- `--mode=web <topic>` — Pipeline A (internet research, Agent Teams)
- `--mode=repo <path> [--compare <path>] [--survey] [--deeper] [--deepest]` — Pipeline B (repo research, Agent Teams)
- `--mode=structured <spec-path> [subject-key]` — Pipeline C (structured research, Agent Teams); use `create` sub-mode to build a new spec (see below)

**Auto-detect (legacy):** if `--mode` is absent, the first argument is used:
- path that exists on disk → `--mode=repo`
- **repo-target candidate** — if NOT an existing local path, check for a repo-target signal. The argument is a repo-target candidate when it matches one of:
  - `https://github.com/<owner>/<repo>` or `git@github.com:<owner>/<repo>` URL
  - bare `<owner>/<repo>` (single slash, no spaces, not a real local path)
  - a bare name resolvable via `machine-local get repos.<name>`

  **Pattern-match is NECESSARY BUT NOT SUFFICIENT.** A bare `owner/repo` shape also matches ordinary web topics ("AI/ML safety", "CI/CD pipelines", "client/server architecture"). Route to `--mode=repo` ONLY when the candidate **successfully resolves** to an on-disk clone via this resolution order:
  1. `machine-local get repos.<name>` — try, in order, `repos.<repo-name>`, `repos.<repo_name>` (hyphens underscored — most registry keys normalize this way, though a few keep literal hyphens), and `repos.<owner>/<repo>`. Confirm the exact key with `machine-local keys | grep '^repos\.'` before concluding non-resolution.
  2. `~/Documents/Code_Reference/<name>`
  3. shallow `git clone --depth=1` — **opt-in last resort only; NEVER automatic on a bare-topic match**

  On non-resolution with no shallow-clone opt-in: **fall back to `--mode=web`** (safe default, NOT an error). Emit a one-line note: *"target matches repo shape but did not resolve to a local clone → falling back to web mode; use `--mode=repo <path>` to force, or opt in to shallow clone."*

- otherwise → `--mode=web`

`--mode=web` explicitly overrides auto-detection in all cases.

> Note: the web pipeline caps at 5 topics — this IS the ≤5 concurrent web-tool caller ceiling; exceeding it self-throttles with a 429 error indistinguishable from a platform gate. For a larger research need, `/spinoff` the question set into chunks across sessions (each running this skill under the cap) rather than authoring an over-cap custom harness.

## Agent Teams Note

Agent Teams form implicitly when the first teammate is spawned (requires `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`). There is no `TeamCreate` tool to check for and no restart gate. (Optional preflight: confirm `SendMessage` + `TaskCreate` are present.)

## Step 1: Parse Arguments

Parse `--mode` from `$ARGUMENTS`. If absent, apply auto-detect. Extract remaining arguments to pass through to the driver.

For `--mode=structured`, check whether remaining arguments start with `create` — if so, run Create Mode (see driver file Step 0) before the normal dispatch.

*Next: Step 0 (Run Identity) — numbered 0 but executes after Step 1.*

## Step 0: Run Identity

> **Execution order:** This step runs after Step 1 (Parse Arguments) — it uses the parsed mode and topic/subject. It is numbered "Step 0" to indicate it is a universal pre-flight that executes before mode-specific routing (Step 2). Run Step 1 first, then Step 0, then Step 0.5, then Step 2.

1. Generate run ID: `YYYY-MM-DD-HHhMM` (current timestamp — matches driver run-id format exactly)
2. Extract topic/subject from the parsed arguments:
   - `--mode=web`: the `<topic>` argument
   - `--mode=repo`: the repo name (basename of `<repo-path>`)
   - `--mode=structured`: the `<subject-key>` argument
3. Generate topic slug from the extracted topic/subject (e.g., `novel-claude-code-implementations`, `onnxruntime`, `acme-corp`)
4. Create the shared run workdir at `docs/research/{run-id}-{topic-slug}-workdir`.
5. Bind `{scratch-dir}` = `docs/research/{run-id}-{topic-slug}-workdir` as a session-level token. This value is available to Step 0.5 and is forwarded to the driver — the driver's Step 1 accept-if-passed clause uses it and skips its own workdir creation.

## Step 0.5: Prior-Art Pre-Flight

**Always-on for all modes (web / repo / structured). Advisory / REPORT-ONLY — never blocking, never aborting.**

**Cost note:** Bounded pre-flight targeting ≤10K tokens — dispatched before fan-out and outside the team-size ceiling.

Dispatch `prior-art-checker` as a **non-teammate Agent** in research mode:

```
Agent(
  subagent_type: "coordinator:prior-art-checker",
  prompt: <inline>
mode: research
research_question: {parsed topic/subject from Step 1}
scratch_dir: {scratch-dir}
peer_repos: {from registry or research question context — omit if not applicable}
</inline>
)
```

When the pre-flight returns:
1. Read the sidecar at `{scratch-dir}/prior-art-check.md` (the research-mode sidecar path the agent writes — see `coordinator/agents/prior-art-checker.md` § Sidecar path (research mode)).
2. Pay particular attention to the **4th bucket ("Existing corpus")**: if a same-subject corpus is found, surface it to the operator before spawning the research team:
   > "Prior-art pre-flight found an existing corpus on this subject at `{path}`. Options: (1) read the existing corpus and refine the question, (2) proceed with fresh research, (3) abort. Which?"
3. If no same-subject corpus is found, proceed silently to Step 2.
4. **Sidecar absent:** if the sidecar does not exist at `{scratch-dir}/prior-art-check.md` after the pre-flight returns, log: *"prior-art pre-flight sidecar not found — proceeding without"* and proceed to Step 2. The pre-flight is advisory; an absent sidecar is non-blocking.

**Graceful-skip clause:** if `prior-art-checker` cannot be resolved (e.g., deep-research-claude installed standalone without coordinator-claude), log:
> "prior-art pre-flight skipped: prior-art-checker not installed"
and proceed directly to Step 2 — do not error, do not abort.

## Step 2: Route to Driver

Read the appropriate driver file and follow its steps, passing through all remaining arguments:

- **`--mode=web`:** Read `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/web-driver.md` and follow all steps exactly
- **`--mode=repo`:** Read `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/repo-driver.md` and follow all steps exactly
- **`--mode=structured`:** Read `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/structured-driver.md` and follow all steps exactly

The driver handles everything from here — team creation, spawn, completion, archival.

## Post-Synthesis: Coverage Auditor (all pipelines)

After the synthesis is complete and before the run concludes, the EM dispatches the **coverage auditor** (`agents/coverage-auditor.md`) as a **non-teammate Agent**. This is always-on across all four pipelines — no size floor, no opt-out.

The coverage auditor answers: *"Did the synthesis carry the research?"* It emits a `-coverage-audit.md` sidecar. It never writes the synthesis output path.

**Depth→relay mapping by pipeline** (governs whether a fidelity relay also runs, in addition to the auditor):

| Pipeline | Coverage Auditor | Fidelity Relay | Relay trigger |
|---|---|---|---|
| A (web) | Always-on | Yes — Team-1 internal sweep phase, before the synthesizer marks its task complete | Gap-report / deepening-threshold signal |
| B (repo) | Always-on | Yes — Team-1 internal sweep phase | `--deepest` flag only |
| C (structured) | Reduced (drop-annotation check against `synthesis-annotations.md`) | OOS — no prose synthesis to distort; CONTESTED pre-empts | N/A |
| D (notebooklm) | Always-on (**documented divergence:** D auditor additionally carries notebooklm MCP tools + cleanup-deferred ordering; degrades to claims-only if MCP unavailable) | OOS — no depth tier; structurally cannot gate | N/A — revisit if D gains depth concept |

**Pipeline D boundaries** (documented divergence from the unified auditor):
- D auditor carries notebooklm MCP tools (`notebook_query` at minimum) with graduated bootstrap (exact names → keyword fallback → graceful-skip); degrades to `{letter}-claims.json`-only with explicit sidecar note if MCP unavailable.
- D notebook cleanup (`--cleanup`) is deferred until AFTER the D auditor completes — notebook deletion must not run before the sidecar is written. Wire at `coordinator/commands/notebooklm-research.md` Step 6: run auditor first, then delete notebooks.
- Relay is OOS for D until D gains a depth concept (architectural boundary, not an appetite call).

See `agents/coverage-auditor.md` for the full auditor spec (input universe, sidecar format, MCP bootstrap, D-specific divergences).
