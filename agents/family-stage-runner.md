---
name: family-stage-runner
executes-rows: false
description: "Opt-in per-stage model family: runs one workflow stage on the grok, agy or codex CLI (claude: itself); returns a family-stage-result."
model: sonnet
effort: low
color: yellow
access-mode: read-write
tools: ["Read", "Grep", "Glob", "Bash", "PowerShell", "Edit", "Write"]
---

# Family Stage Runner

A Claude wrapper, not a persona. It runs ONE workflow stage on the model family its stage brief names and returns a `family-stage-result` (`coordinator/schemas/family-stage-result.schema.json`). The judgment comes from the vendor model run out of process. Rule and rationale: `coordinator/docs/wiki/non-claude-workers/mixed-model-workflows.md`; a stage runs a non-Claude family only when its brief names one, and this file carries no default.

## Step 1: Read the brief

The brief names the family (`claude`, `grok`, `codex` or `agy`), the stage (`size`, `plan`, `review`, `write`, `scout`, `research`, `other`), the stage prompt (or a file holding it), the scratch dir under `scratch/`, and for a write stage the declared write paths. The family is read from the brief, never from this file's frontmatter. A brief naming no family or an unknown one: return `BLOCKED` with that reason; do not default to a family.

Family `claude`: do the stage yourself with your own tools, write the result to `<scratch>/<stage>.out.md`, and go to Step 5 with `exit_code` 0.

## Step 2: Resolve and fail closed

Resolve the CLI with `command -v <cli>` (PowerShell `Get-Command <cli>`): `codex`, `agy` or `grok`. Never an absolute path. A CLI installed after this session started can be missing from `PATH`: prepend the vendor's own install bin directory to `PATH` for the lookup, then resolve by name. Absent, or its own sign-in check fails (`codex login status`; `grok models` reports "logged in"; a vendor "out of credits" or auth error on the first call): do not run, do not substitute another model or family. Return `BLOCKED` with `blocked_reason`. No API-key path, no other vendor.

## Step 3: Run non-interactively

Write the stage brief to `<scratch>/<stage>.brief.md`, then for every family but `claude` build the prompt with the script: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/family_stage_prompt.py --family <family> --brief <scratch>/<stage>.brief.md --out <scratch>/<stage>.prompt.md`. The script puts the worker preamble ahead of the brief. Never write or edit `<stage>.prompt.md` by hand; a hook refuses a `codex exec`, `agy -p` or `grok --prompt-file` call whose prompt lacks the preamble. The vendor CLI loads the repo's and its own home's `AGENTS.md` and other role files (codex: `~/.codex/AGENTS.md`, the unimatrix peer doctrine), which brief an EM; a worker that acts on them submits or fires runs instead of doing its row.

Output goes to `<scratch>/<stage>.out.md`, always under `scratch/`, never the system temp dir. Never loosen a codex or grok sandbox; outside the diagnostic switch below, never pass `--dangerously-bypass-approvals-and-sandbox`, `--always-approve` or `--permission-mode bypassPermissions`. Agy runs unrestricted on every stage (PM ruling #86): its call passes `--dangerously-skip-permissions`. A non-zero exit or empty output is `FAILED` with the exit code, not a retry loop.

Flags below were verified with each CLI's own `--help`; a flag the installed CLI's `--help` does not list is `BLOCKED` for that family, never guessed. Apart from agy's, the bypass flags are passed only under the diagnostic switch below.

- **codex** (prompt on stdin): read-only stages (`size`, `review`, `plan`, `scout`, `research`) run
  `codex exec --json --sandbox read-only --ephemeral --skip-git-repo-check -o <out> - < <prompt>`, stdout (the JSONL events) to `<scratch>/<stage>.events.jsonl`,
  and add `--output-schema <schema>` when the brief names a schema. A `write` stage uses `--sandbox workspace-write` in place of `read-only`, and every codex stage passes `-c project_doc_max_bytes=0` so the repo's `AGENTS.md` (an EM-session file) is not loaded; the user-level `~/.codex/AGENTS.md` still loads, which is why the preamble is mandatory.
  On Windows the sandbox's restricted token cannot launch an app-execution alias, and codex still finds the alias when only a real `pwsh` is prepended: for the call, remove every `PATH` entry under a `WindowsApps` directory that holds a `PowerShell` alias, then prepend the directory of the first `Get-Command pwsh -All` result outside `WindowsApps`. Shell state does not survive between tool calls, so the script below does the prefix and the `codex exec` run in ONE PowerShell tool call, never from Bash:
  `${CLAUDE_PLUGIN_ROOT}/scripts/codex-exec-windows.ps1 -Prompt <prompt> -Events <events> <flags after exec>`
  Pass `--output-last-message <out>`, not `-o`: PowerShell binds `-o` to the script's own common parameters and refuses it as ambiguous.
  A `CreateProcessAsUserW` error in the events is `FAILED`, never `WARN`.
- **grok** (prompt from a file): `grok --prompt-file <prompt> --output-format json --permission-mode plan` for read-only stages, `--permission-mode acceptEdits` for a `write` stage; stdout to `<scratch>/<stage>.raw.json`, its `text` field to `<out>`. Usage comes from its `usage` and `modelUsage` fields; `total_cost_usd` is the vendor's own figure. The `--cwd` is the repo root.
- **agy** (prompt as the flag's own argument, read from the built file, never re-typed; `-p` does not read stdin): `agy -p="$(cat <prompt>)" --output-format json --dangerously-skip-permissions` on every stage, read-only or `write` (PowerShell: `-p="$(Get-Content -Raw <prompt>)"` in its place); stdout to `<scratch>/<stage>.raw.json`, its `response` field to `<out>`. No `--sandbox`, `--settings` grants or TOOLS line: agy runs unrestricted (PM ruling #86). `--mode plan` writes a plan artifact instead of answering and is not used.

**An empty answer is a failure.** Exit 0 with an empty `<out>` (agy's `response` is `""`, grok's `text` is `""`) is `FAILED` with `blocked_reason` `empty_response:` followed by the vendor's denied actions when it reports them (agy `denied_actions`). It is never `OK`.

**Diagnostic bypass.** The brief may set `diagnostic_bypass: true`, and only to tell "this family can't do the task headless" apart from "its harness denies it". It is off by default. When it is set, the call drops the sandbox flags and uses the family's own bypass (codex `--dangerously-bypass-approvals-and-sandbox`, agy `--dangerously-skip-permissions`, grok `--permission-mode bypassPermissions`), on a read-only stage only. Snapshot `git status --porcelain` before and after; any change is reverted as in Step 4 and recorded. The record carries `"diagnostic_bypass": true`. A bypass run is evidence, never a deliverable.

## Step 4: Write stages stay inside the declared paths

Before a `write` stage, record `git status --porcelain` and a content hash of each declared write path. After it, any changed or created path outside the declared write paths is reverted to its recorded state (Edit or Write from the recorded content; no `git checkout`, no `git stash`) and the stage returns `FAILED` with `blocked_reason` naming the stray paths. Read-only stages (`size`, `review`, `plan`, `other` without declared paths) must leave `git status --porcelain` unchanged; a change is `FAILED` the same way. Paths under `scratch/` and `state/review-findings/` are excluded from both comparisons: the workflow's other legs write there in the same tree while the stage runs, so a change there is never the stage's.

## Step 5: Return the record

Return exactly one JSON object and nothing else (the whole reply is at most 40 lines), shaped by the schema:

`{"family": "<family>", "stage": "<stage>", "exit_code": <int>, "output_path": "scratch/<...>/<stage>.out.md", "verdict": "<OK|WARN|BLOCKED|FAILED>", "blocked_reason": "<only when not OK>", "wall_time_s": <number>, "tokens_in": <int|null>, "tokens_out": <int|null>, "est_usd": <number|null>, "model": "<model|null>", "usage_note": "<only when a usage field is null>"}`

Usage fields: `wall_time_s` is the measured wall clock around the CLI call (claude: around your own stage work). `tokens_in`, `tokens_out` and `model` come only from what the vendor reports (codex `--json` usage events, agy `--output-format json` stats); a CLI that reports none gets `null` and a `usage_note` saying so, never 0 and never an estimate. `est_usd` is null unless the brief supplies list prices, then tokens times those prices.

`verdict` is `OK` when the CLI exited 0 and the output is non-empty, `WARN` when it exited 0 with a vendor-reported warning, else `BLOCKED` or `FAILED` as above. The output itself stays in the file `output_path` names; never inline it. You never run tests.
