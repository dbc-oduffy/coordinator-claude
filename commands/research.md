---
name: research
description: "Research by value class: scouts, corpus, deep, or spike. EM-fired, never from a subagent."
allowed-tools: ["Agent", "Read", "Write", "Edit", "Bash", "Glob", "Grep", "Workflow"]
argument-hint: "--sizing <path> | --ask \"<question>\" [--target web|repo=PATH|local=PROBE] ... [--split|--combine]"
---

# Research — Single Entry Point

One entry for all research. The EM sizes the research; the engine resolves the value class and
prints one `Workflow` line. Value classes and the tier-to-manifest map:
`coordinator/docs/wiki/skills-corpus/deep-research-pipelines.md`.

| Value class | Run |
|---|---|
| `scouts` | one Sonnet scout per question (up to 8), optional Haiku probes for local targets, one grounding agent; a scratch digest. The default for a bare ask |
| `corpus` | the named-source manifest pipeline (web, repo, structured, NotebookLM), with coverage audit |
| `deep` | the unblock-us diagnostic team (diagnose, decompose, challenge, plus one specialist per source), for an EM stuck delivering something |
| `spike` | a binary verdict on one unproven mechanism: both halves, throwaway probes, a verdict record. Procedure: `coordinator/skills/spike/SKILL.md`. Spike is the research door's verdict class |

## The research door

Sizing is the door for build work (one `coordinator:engine-ask` submission); this command is the
door for research. The EM enters it when the PM says "research" or "spike", when the ask is
multifaceted and likely to break up, or when it is uncharted territory. The EM's sizing is the
authority; neither door gates or refuses the other's arrival. An engine-ask of a research sizing
halts with route `research` and a one-entry `fire` list; the EM runs that one `fire` call unedited
and never re-sizes or re-fires by hand. Research need not end with code, and
every class ends with a committed artifact and trail (Step 4).

`deep` is the unblock team, not "more depth". A comprehension ask ("understand this repo", "survey
this topic") is `corpus` however many targets (`A-SURVEY-IS-CORPUS-NEVER-DEEP`); shallowness is
`--research-depth standard`, never a class change; more thoroughness on a corpus run is `--research-depth deeper|deepest`
or `--research-appetite large`. `research.appetite` moves the class one notch (`small` down,
`large` up), so `deep` at `small` runs corpus and `corpus` at `large` runs deep. Read the emitted
script's meta before firing: a "The EM is stuck delivering something" meta on a comprehension ask
means the class is wrong.

## Arguments

`$ARGUMENTS`:
- `--sizing <path>` — a sizing carrying a `research` block (`value_class`, `appetite`, `sources[]`, `depth`, `targets[]`); resolves to scouts, corpus or deep per the class and appetite
- `--ask "<question>"` — a bare ask; runs `scouts` with no sizing object. Repeatable: every `--ask` is one question
- `--target web|repo=PATH|local=PROBE` — repeatable; binds to the `--ask` before it, and several on one question mix them. `web` is the default; `repo` takes a path (absolute for another checkout); `local` takes an allowlisted probe id
- `--split | --combine` — one scout per question (default), or one scout over all questions

Contract (cap, grammar, probe allowlist, close params): `coordinator/contract/scouts-ask-fragment.md`.

## Sizing the research

The EM sizes the research itself; no sizing-scout is needed to pick a class, but `sizing-assemble`
still requires the build-sizing flags (`--tshirt`, `--intent`, `--no-doc-consumers`,
`--no-ask-conflicts`) beside the research ones; a research sizing takes `--tshirt S` unless the
work says otherwise. A research ask enters
through `coordinator:sizing` (Step 3 flags: `--research-class`, `--research-source`,
`--research-appetite`, `--research-depth`, `--research-target <source>=<ref>`, each target
repeatable) and the sizing is written with `--write state/sizings/<date>-<slug>.yaml`. A pickup
`ask` memo whose ask is research takes the same route: size it, then fire. A sizing carrying
`--research-class` fires `/coordinator:research --sizing <path>` and never enters the plan chain;
its `next_move` names the research fire and `research.close`. Questions go in with
`--research-question "<q>"` (repeatable), written to `research.questions`. `--research-target`
takes an absolute path for a repo outside this checkout (`repo=<absolute path>`); the
concrete-path guard's warning on it is expected. A scouts run over a local clone keeps
`--research-source` at web, since a `repo` source floors scouts to corpus (claude-klabauter
`research_shape` and `_research_contract` `FLOOR_SOURCES`); name the clone with
`--research-target repo=<absolute path>` or a bare `--research --ask` naming it. To change only
the research block, run `sizing-assemble --amend-research <sizing> --research-<flag> <value>`.

**Seed URLs.** A URL the run must ingest goes in with `--research-seed <kind>=<url>` (repeatable),
written to `research.seeds`, never in a `--context` file. Each kind routes to one pipeline and adds
that source to the run:

| kind | pipeline |
|------|----------|
| `video` | notebooklm |
| `repo` | repo |
| `doc` | web |
| `paper` | web |

**Local-only research.** Research over code or material that must never enter a git repo
(vendor-proprietary source, licensed corpora) sets `research.destination: local-only` on the
sizing (`sizing-assemble --research-destination local-only`), or passes `--local-only` to the emit;
a local-only sizing cannot be emitted any other way. Scratch and every durable output then land under
machine-local `research.local_root`, which must sit outside every checkout and must be set on the box
first (`machine-local set research.local_root <dir>`). `research.close` copies them there and commits
no output content; the run's trail record is committed (Step 4).

`research.depth` picks the scout tier: `standard` runs Haiku scouts, `deeper` runs Sonnet scouts
over chunks A–D, and `deepest` adds the relay pass. A large repo (about 1000+ files, or about 150+
files or 1.5 MB per chunk) is sized at `deeper` or `deepest`; Haiku scouts fail silently on it.

## Emit lists and context

`emit-dispatch-workflow --from-sizing <path>` accepts `--list NAME=a,b,c`, `--flag NAME=value`
and `--context <file>` (each repeatable) and `--scratch-dir`. Lists default to what the scope
templates fix (repo `chunks=A,B,C,D` and `haiku_scouts=1,2`, web `topics=a,b,c,d`). NotebookLM
has no default: a `notebooklm` source needs its notebooks, recorded on the sizing with
`--research-target notebooklm=<letter or id>` (one per notebook) or passed as
`--list notebooks=A,B`; `--research-source notebooklm` alone is refused. `--context` takes a real
file path; process substitution (`<(...)`) fails under Git Bash, so write the text to a scratch
file first. A `--flag`
goes to the pipeline that declares it (e.g. `compare=true`). The emit reply lists each segment's
flags and lists, and reports every refusal in one error.

**Fan-out.** A sizing with several independent topic groups (many notebooks or targets) emits
one run per group with `--per-group`, or a subset with `--group <letter>` (repeatable). The reply
is the fan-out plan: groups in priority order, each with its own run id and `Workflow` line. Fire
them in waves; each run closes on its own `research.close`, and the sizing's research block is
held until the last sibling closes. One failing group never stalls the others.

A repo run takes every `repo` target from one sizing: the first is the primary, each further one a
secondary folded into one chunk (`**Secondary:**` in the scope header). A secondary too large to
fold (the scope stage notes `secondary too large to fold`), or a peer of equal weight, is its own
sizing and emit. A requested output path goes in the sizing's exit criterion or a
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
`emit-dispatch-workflow --from-sizing <path>` (the direct path; a sizing that carries a `research`
block can also be fired as one `coordinator:engine-ask` submission `{sizing: <path>}`, and the
engine emits the research run), or `emit-dispatch-workflow --research --ask "<question>"`
for scouts; a multi-question, mixed-target ask is
`emit-dispatch-workflow --research --ask "<q1>" --target web --target repo=coordinator/hooks --ask "<q2>" --target local=<probe-id> --split`.
Fire the one printed `Workflow` line as a background Workflow (`run_in_background: true`).
Never hand-fill a script. Worker briefs (scout, specialist, synth) are composed from the sizing's
frozen intent only; never put baton or `pm_turns` mid-turn instructions into one. On a corpus or deep fire, run `em_watch` (the module `-m coordinator_core.workflow_watch.mailbox_line <box>`, under the interpreter resolved per `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md` § Portability) in the background the same turn; it returns on an escalation: act, then `em_rewatch`. When `sources[]` holds `notebooklm`, the engine prepends the preflight
stage and halts before spend if the NotebookLM MCP is unregistered; its remedy strings are the
exact commands to relay.

## Step 4: On Completion

Every class closes on a committed artifact and trail
(`A-RESEARCH-CLOSES-ON-A-COMMITTED-ARTIFACT-AND-TRAIL`). The trail record is
`docs/research/trail/<run-id>.yaml`: run id, sizing path, class, destination, output count, with
repo-relative paths only.

- **Scouts:** the Workflow returns `{results, next_action}`; run `next_action` (`research.close`,
  `require_grounding`) unedited, as corpus and deep do; the close commits the trail record in the
  same step. The close refuses a run whose grounding
  report grades a claim ungrounded or contradicted or rules a contradiction invented; the refusal
  names the claims to fix or drop before re-closing. Clear a refusal in order: fix or drop the
  claim in the digest, re-ground against the edited digest, then re-run `research.close`. The
  close re-reads `grounding.md`, so a fix alone leaves the stale grade in place, and a resume
  replays grounding from cache on an unchanged prompt; never hand-edit `grounding.md`. The
  re-ground mechanism is in `coordinator/contract/scouts-ask-fragment.md` `## Close`.
- **Corpus and deep:** the Workflow returns `{results, next_action}`; run `next_action`
  (`research.close` with its params) unedited: it archives and commits the outputs together with
  the trail record.
- **Halted run (any class):** a return carrying `halted`, or `segment_halts` with no `next_action`
  (every leg halted), is not closed: relay each `decision_required` remedy and stop. A return with
  a `next_action` whose `params.halted_segments` is set: run `next_action` unedited; the close
  excuses those segments, and the report names them.
- **Spike:** follow `coordinator/skills/spike/SKILL.md`; the committed artifact is the verdict
  record at `docs/research/spike-verdicts/`, and the trail record names it. The engine has no
  spike pipeline, so the EM commits the trail record beside the verdict record by the ordinary
  scoped commit path.
- **Local-only (any class):** the outputs stay under `research.local_root`; `research.close`
  commits only the trail record, with no excerpt of the output content.
- **NotebookLM:** the sweep never deletes notebooks. Once the coverage-audit sidecar exists, if the
  sizing asked for cleanup, read each `{letter}-summary.md`'s `notebook_id` and call `notebook_delete`
  for each, logging failures; otherwise report the preserved notebook names to the PM. The NotebookLM
  pipeline needs the external `notebooklm-mcp-cli` server, an external dependency the plugin does not bundle:
  `coordinator/docs/wiki/mcp-topology/notebooklm-for-your-research.md`.

## Declared Pipelines

A repo's `research_pipelines` (in `coordinator.local.md`) names research that runs only on its
declared spec; a PreToolUse(Agent) guard denies ad-hoc dispatches onto it. Shape: wiki
(`research-pipelines-config`).
