---
name: research
description: "Research by value class: scouts, corpus, or deep. EM-fired, never from a subagent."
allowed-tools: ["Agent", "Read", "Write", "Edit", "Bash", "Glob", "Grep", "Workflow"]
argument-hint: "--sizing <path> | --ask \"<question>\""
---

# Research — Single Entry Point

One entry for all research. The EM sizes the research; the engine resolves the value class and
prints one `Workflow` line. Value classes and the tier-to-manifest map:
`coordinator/docs/wiki/skills-corpus/deep-research-pipelines.md`.

| Value class | Run |
|---|---|
| `scouts` | 1-2 Sonnet agents; a scratch digest. The default for a bare ask |
| `corpus` | the named-source manifest pipeline (web, repo, structured, NotebookLM), with coverage audit |
| `deep` | the unblock-us diagnostic team (diagnose, decompose, challenge, plus one specialist per source), for an EM stuck delivering something |

`deep` is the unblock team, not "more depth". A comprehension ask ("understand this repo", "survey
this topic") is `corpus`; more thoroughness on a corpus run is `--research-depth deeper|deepest`
or `--research-appetite large`. `research.appetite` moves the class one notch (`small` down,
`large` up), so `deep` at `small` runs corpus and `corpus` at `large` runs deep. Read the emitted
script's meta before firing: a "The EM is stuck delivering something" meta on a comprehension ask
means the class is wrong.

## Arguments

`$ARGUMENTS`:
- `--sizing <path>` — a sizing carrying a `research` block (`value_class`, `appetite`, `sources[]`, `depth`, `targets[]`); resolves to scouts, corpus or deep per the class and appetite
- `--ask "<question>"` — a bare ask; runs `scouts` with no sizing object

## Sizing the research

The EM sizes the research itself; no sizing-scout is needed to pick a class. A research ask enters
through `coordinator:sizing` (Step 3 flags: `--research-class`, `--research-source`,
`--research-appetite`, `--research-depth`, `--research-target <source>=<ref>`, each target
repeatable) and the sizing is written with `--write state/sizings/<date>-<slug>.yaml`. A pickup
`ask` memo whose ask is research takes the same route: size it, then fire. A sizing carrying
`--research-class` fires `/coordinator:research --sizing <path>` and never enters the plan chain;
its `next_move` names the research fire and `research.close`. Questions go in with
`--research-question "<q>"` (repeatable), written to `research.questions`. `--research-target`
takes an absolute path for a repo outside this checkout (`repo=<absolute path>`); the
concrete-path guard's warning on it is expected. To change only the research block, run
`sizing-assemble --amend-research <sizing> --research-<flag> <value>`.

**Local-only research.** Research over code or material that must never enter a git repo
(vendor-proprietary source, licensed corpora) sets `research.destination: local-only` on the
sizing (`sizing-assemble --research-destination local-only`), or passes `--local-only` to the emit;
a local-only sizing cannot be emitted any other way. Scratch and every durable output then land under
machine-local `research.local_root`, which must sit outside every checkout and must be set on the box
first (`machine-local set research.local_root <dir>`). `research.close` copies them there and commits
nothing.

`research.depth` picks the scout tier: `standard` runs Haiku scouts, `deeper` runs Sonnet scouts
over chunks A–D, and `deepest` adds the relay pass. A large repo (about 1000+ files, or about 150+
files or 1.5 MB per chunk) is sized at `deeper` or `deepest`; Haiku scouts fail silently on it.

## Emit lists and context

`emit-dispatch-workflow --from-sizing <path>` accepts `--list NAME=a,b,c`, `--flag NAME=value`
and `--context <file>` (each repeatable) and `--scratch-dir`. Lists default to what the scope
templates fix (repo `chunks=A,B,C,D` and `haiku_scouts=1,2`, web `topics=a,b,c,d`); a `--flag`
goes to the pipeline that declares it (e.g. `compare=true`). The emit reply lists each segment's
flags and lists, and reports every refusal in one error.

A repo run studies one repo: the scope stage reads the first `repo` target, so a multi-repo ask is
one sizing and one emit per repo. A requested output path goes in the sizing's exit criterion or a
`--context` file; the scope stage honours it. `research.close` refuses secret-shaped outputs
(reported as file:line and pattern, never the value) and returns stray `docs/research/` files
written outside the destination as `strays`.

## Chatty Workflow

Every run is ONE background `Workflow` the EM fires; the EM is then freed and completion is the
Workflow's task notification. Workers never `SendMessage` each other or the EM: peer exchange goes
through mailbox files (`{workdir}/mail/<role>.jsonl`). A break-class finding the EM must act on
before the run ends goes to `{workdir}/mail/_em.jsonl` as `{"from","escalate":true,"text"}`;
everything else reaches the EM through the overseer's return value. Doctrine: `coordinator/docs/wiki/dispatching-parallel-agents/chatty-workflows.md`.

## Step 1: Run Identity

Run ID format `YYYY-MM-DD-HHhMM`. Shared run workdir: `docs/research/{run-id}-{topic-slug}-workdir`,
bound as `{scratch-dir}`.

## Step 2: Structured Create Mode

When the work is a structured run and no spec exists yet, write the spec first: the `create`
sub-mode in `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/structured-driver.md` Step 0. This is the
one EM-authored step; scoping, prior-art and coverage are manifest stages.

## Step 3: Fire

Resolve the engine CLI per `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`, then run
`emit-dispatch-workflow --from-sizing <path>`, or `emit-dispatch-workflow --research --ask "<question>"`
for scouts. Fire the one printed `Workflow` line as a background Workflow (`run_in_background: true`).
Never hand-fill a script. On a corpus or deep fire, arm `Monitor` on the emit reply's `em_watch`
command in the same turn (`ToolSearch select:Monitor` first: it is a deferred tool); each line it prints is a member escalation to act on now. When `sources[]` holds `notebooklm`, the engine prepends the preflight
stage and halts before spend if the NotebookLM MCP is unregistered; its remedy strings are the
exact commands to relay.

## Step 4: On Completion

- **Scouts:** read the digest in scratch. Commit nothing.
- **Corpus and deep:** the Workflow returns `{results, next_action}`; run `next_action`
  (`research.close` with its params) unedited: it archives and commits the outputs.
- **NotebookLM:** the sweep never deletes notebooks. Once the coverage-audit sidecar exists, if the
  sizing asked for cleanup, read each `{letter}-summary.md`'s `notebook_id` and call `notebook_delete`
  for each, logging failures; otherwise report the preserved notebook names to the PM. The NotebookLM
  pipeline needs the external `notebooklm-mcp-cli` server, an external dependency the plugin does not bundle:
  `coordinator/docs/wiki/mcp-topology/notebooklm-for-your-research.md`.

## Declared Pipelines

A repo's `research_pipelines` (in `coordinator.local.md`) names research that runs only on its
declared spec; a PreToolUse(Agent) guard denies ad-hoc dispatches onto it. Shape: wiki
(`research-pipelines-config`).
