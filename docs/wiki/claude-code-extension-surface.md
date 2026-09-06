---
title: Claude Code Extension Surface
status: active
kind: doctrine-wiki
created: 2026-07-27
---

# Claude Code Extension Surface

> What Claude Code 2.1.220 exposes to a plugin, and how much of it coordinator actually uses.
> Spine is used-vs-unused: the gap is the actionable content, not the schema recap.

<!-- spec-backlink: state/reference/anthropic-docs/_verify-harness-capabilities.md -->
<!-- spec-backlink: state/reference/anthropic-docs/_mine/claude-code-product.md -->

Sources: `state/reference/anthropic-docs/claude-code/{hooks,sub-agents,plugins-reference,
plugin-marketplaces,skills,output-styles,statusline,model-config,interactive-mode,
cli-reference}.md`, plus mining sidecars `_mine/{claude-code-product,cli-scripting,
prompting-skills}.md` and the verification pass `_verify-harness-capabilities.md`. Installed
harness: **2.1.220**, newer than every `min-version` gate cited below — nothing here is
aspirational for us.

## Reality filter — read before the tables

`--output-format`, `--json-schema`, `--bare`, `--permission-mode`, `--max-budget-usd` and the rest
of § CLI scripting are flags on the standalone `claude` **binary**, invoked as a subprocess. They
are not fields on the in-session `Agent`/`Task` dispatch tool — verified against the full 14-field
subagent-frontmatter table (§ 2 below), none of which is CLI-output-shaped. Coordinator's dominant
architecture — Sonnet/Haiku workers dispatched via `Agent`, returning `DONE: <path> | ...`
sidecar-pointer text — is **structurally unreachable** by that whole flag family. The one place
this repo shells out `claude --print` at all is the six-item contract at
`coordinator/docs/claude-cli-subprocess-contract.md`, and even its executable call sites migrated
to `claude-klabauter` (commit `b644d5a9`) — this repo tracks zero `coordinator/bin/` files. Treat
every CLI flag below as "useful if we ever build a subprocess-shaped tool," not as something a
dispatched agent can reach today.

## 1. Hook events — 8 of 30 registered

`hooks.md` documents 30 distinct hook events. `coordinator/hooks/hooks.json` registers **8**
(verified by reading the file directly, not any stale count elsewhere in the doc corpus).

> **Reachability column.** "Registered? no" says nothing about whether an event
> *could* be used. A quarantined empirical spike probed every unregistered event against installed
> 2.1.220 and recorded fires / does-not-fire / inconclusive with observed payloads. Full verdicts,
> method, and the two false negatives caught mid-spike:
> `state/reference/anthropic-docs/_hook-frontmatter-reachability.md`. Verdicts below are observed,
> not documentation restatements; `—` means registered-already or not probed.

| Event | What fires it | Registered? | Reachable? (probed) | Script(s) |
|---|---|---|---|---|
| `SessionStart` | session begins/resumes (`startup\|resume\|clear\|compact\|fork`) | **YES** | — | `project-orientation.py --lightweight` (sync, orientation inject); `sweep-boot.py` (async; engine-root resolution + forwarder self-heal only — its archival sweep was killed and it now dispatches no op) |
| `Setup` | `--init` / `--init-only` / `--maintenance` (undocumented — absent from `--help`, present and parser-accepted since at least 2.1.220) | no | **undetermined** — NOT "does not fire". The old flags-absent basis is refuted (2.1.226 re-probe). Three live-fire attempts all failed, but a known-good `SessionStart` control failed under the identical `--init-only` invocation, so the negative is uninterpretable. Untested lead: `Setup` hooks may be plugin-manifest-sourced, not `settings.json`-sourced | — |
| `UserPromptSubmit` | user submits a prompt, pre-processing | **YES** | — | `runtime-tripwire-em-check.py` (L1 idle-EM awareness) |
| `UserPromptExpansion` | a typed slash-command expands into a prompt | **YES** | — | `pickup-autofire.py` (pickup-assemble brief, auto-fires on `coast==clear`) |
| `PreToolUse` | before a tool call executes; can allow/deny/modify | **YES** | — | 10+ matcher-scoped scripts — `preuse-bash-dispatch.py`, `block-dispatch-suite-invocation.py`, `enforce-agent-dispatch-mode.py`, `nudge-multiwave-workflow.py`, `block-workflow-unmodeled-agent.py`, `validate-frontmatter-schema.py`, `check-claude-md-size.py`, `nudge-em-code-dispatch.py`, `preuse-write-dispatch.py`, `block-home-dir-memo-delivery.py`, `suggest-sonnet-research.py`, `nudge-autonomous-askuserquestion.py`, `session-heartbeat.py` |
| `PermissionRequest` | permission dialog appears | no | **does not fire** on the headless auto-mode rule-deny path, under a *confirmed* denial; interactive/TTY path untested | — |
| `PermissionDenied` | auto-mode classifier denies a call | no | **does not fire** — same run/evidence as `PermissionRequest`; denial surfaced only via `permission_denials` + `tool_response` | — could back the "permission policy generalization" item already claimed in `state/handoffs/2026-07-27-structural-policy-enforcement.md` |
| `PostToolUse` | after a tool call succeeds; can modify result | **YES** | — | `session-heartbeat.py`, `track-touched-files.py`, `nudge-initiative-goals-ladder.py`, `plan-persistence-check.py`, `agent-completion-log.py`, `track-dispatched-agents.py`, `runtime-tripwire-em-check.py`, `postuse-advisory-dispatch.py` (unauthorized-handoff nudge folded in) |
| `PostToolUseFailure` | after a tool call fails | no | **fires, bounded** — hard failures with a top-level `error` key (Bash non-zero exit incl. 127, Read-missing) fire; `<tool_use_error>` *content* in a successful result (Edit-mismatch) does not. `tool_input` carries the failing command | could inject the known cross-repo-memo-forwarder-not-on-PATH remediation (`CLAUDE.md`) as `additionalContext` instead of relying on the EM remembering the doc |
| `PostToolBatch` | after a parallel-tool batch resolves | no | **fires** — once per batch, payload `tool_calls[]` enumerates every member with its own `tool_name`/`tool_input`/`tool_response` | — |
| `Stop` | Claude finishes responding | **YES** | — | `runtime-tripwire-em-check.py` (idle check), `runtime-tripwire-stop-watcher.py` (async, `asyncRewake`, 1800s) |
| `StopFailure` | turn ends on API error | no | inconclusive — no reproducible trigger | — |
| `SubagentStart` | subagent spawned | no | **fires** — carries `agent_id` (stable join key vs `SubagentStop`) + `agent_type`; fires before the subagent's own tool calls | would pair with the `SubagentStop` detector below to distinguish "never started" from "started and hung" |
| `SubagentStop` | subagent finishes | **YES** | — | `subagent-zero-tool-use-detect.py` (counts `tool_use` blocks via a claude-klabauter op) |
| `Notification` | Claude Code sends a notification | no | inconclusive — no notification-emitting condition reachable headlessly | — |
| `MessageDisplay` | assistant message text streams | no | **fires** — once per message chunk, `final: true` on the last | — |
| `ConfigChange` | a config file changes mid-session | no | **fires** on a tool-caused write to `.claude/settings.local.json` (`source: local_settings`). Untested: out-of-band edits, `settings.json`, user-tier files | could self-defend the hook stack itself — nothing today notices a mid-session `hooks.json` edit or `disableAllHooks: true` |
| `InstructionsLoaded` | `CLAUDE.md`/`.claude/rules/*.md` loads | no | **fires** — once per file, `load_reason` distinguishes `session_start` from `nested_traversal`; carries `file_path` + `memory_type`. **Requires `--setting-sources` ≥ `project` to observe** | could convert the manually-spiked "does `--plugin-dir` deliver `coordinator/CLAUDE.md`" fact (`docs/research/spike-verdicts/2026-07-27-plugin-claude-md-delivery.md`) into a live per-session assertion |
| `FileChanged` | a watched file changes on disk | no | **does not fire** — no watch-registration mechanism reachable from a settings-registered hook; 4 attempts across in-session writes and external out-of-band edits | — |
| `CwdChanged` | working directory changes | no | **fires** — payload carries **both** `old_cwd` and `new_cwd`. Triggered by an ordinary Bash `cd` (the Bash tool's cwd persists) | could inject a cross-repo-write-discipline reminder when cwd crosses into `claude-klabauter` |
| `WorktreeCreate` | worktree created; hook must return path | no | **fires — and the hook *owns* creation.** Harness does not run `git worktree add`; it trusts the directory the hook prints as its **last stdout line** (plain text, not JSON). Returning nothing fails session startup <!-- spec-backlink: run 2026-08-06-14h38, nugget c8-040 --> | could validate/derive the `work/{machine}/{date}` / `feature/{name}` naming convention at creation instead of by review — but see reachability note: enforcing means owning the git mechanics |
| `WorktreeRemove` | worktree removed | no | inconclusive — no CLI/subcommand trigger found; `ExitWorktree` tool untested. **Highest-value untested lead**: `EnterWorktree`/`ExitWorktree` appear as first-class in-session tool names in the harness's own tool list, likely a materially more relevant trigger than the `-w` CLI flag probed here — see `_hook-frontmatter-reachability.md § Highest-value follow-up` | — |
| `PreCompact` | before context compaction | **YES** | — | `context-pressure-precompact.py` |
| `PostCompact` | after compaction completes | no | inconclusive — not reachable in a short headless run | **real gap** — we infer compaction happened from a `PreCompact` byte-size sentinel rather than confirming completion or reacting post-hoc |
| `Elicitation` | MCP server requests user input mid-call | no | inconclusive — no trigger available | — |
| `ElicitationResult` | after user responds to elicitation | no | inconclusive — no trigger available | — |
| `SessionEnd` | session terminates | no | **fires** — once at end of every session; carries `reason` (only normal-completion observed) | — |
| `TeammateIdle` | Agent Teams teammate about to idle | no | inconclusive — a headless one-shot never builds standing-teammate infrastructure | Agent Teams is PM-gated + low-frequency here; premature |
| `TaskCreated` | task created via `TaskCreate` | no | **fires — but dependency-blind.** Payload is only `task_id`/`task_subject`/`task_description`; no `blockedBy` even when the task was genuinely created blocked (verified harness-side via `TaskList`) | could give the `blockedBy`-is-a-gate rule (`~/.claude/CLAUDE.md § Agent Teams`) a structural backstop instead of an honor system — **but requires a separate task-state read**, not the payload |
| `TaskCompleted` | task marked completed | no | **fires** — identical key set to `TaskCreated`; no status-transition metadata | same, on completion — blocks completion when a declared `blockedBy` dependency isn't itself done |

**Matcher support** is per-event in the docs, but **not enforced by the harness.**
`hooks.md § Matcher Support by Event` lists `UserPromptSubmit`, `PostToolBatch`, `CwdChanged`,
`TeammateIdle`, `TaskCreated`, `TaskCompleted` as taking none. Empirically, the
harness **accepts a matcher key on all of them and fires anyway**. On `CwdChanged` this was pinned
down precisely: a matcher chosen so it *cannot match anything*
(`"this-string-can-never-match-anything-zzz"`) still fired — so the matcher is **never evaluated**
for these events, rather than coincidentally matching.

Two consequences, and the second is the trap. A matcher-bearing registration is inert, not broken,
so it never explains a hook that fails to fire. But it also provides **zero filtering** — a hook on
one of these events fires on *every* occurrence and must narrow in-script. Writing a matcher there
and assuming it scopes anything is the mistake to avoid.

**Handler types beyond `command`:** `http`, `mcp_tool`, `prompt`, `agent` (`hooks.md` §§ 2–5). We
use only `type: "command"` (python3 script spawn) across every entry in `hooks.json` — the other
three shapes are undocumented-by-use here, not verified as reachable or unreachable, just unused.

## 2. Subagent frontmatter fields — 3 of 14 optional fields in use

31 agent files under `coordinator/agents/`. `sub-agents.md` documents `name` and `description` as
required, plus 14 optional fields. Adoption (grep-verified):

| Field | Used by | What it does | Note |
|---|---|---|---|
| `tools` | 31/31 | positive allowlist of tools the agent may call | universal; every agent declares one explicitly |
| `model` | 31/31 | `sonnet`/`opus`/`haiku`/`fable`/full ID/`inherit` | universal; every agent pins a model — see `subagents-sonnet-unless-pm-approves-opus` lesson |
| `color` | 30/31 | display color in task list/transcript | cosmetic only |
| `disallowedTools` | 0/31 | denylist layered over inherited tools | zero use — **probed 2026-07-27: BINDS.** Applied before tool-list resolution, so the tool is absent from the toolset entirely rather than present-but-denied. See § Discharge candidates |
| `permissionMode` | 0/31 | `default`/`acceptEdits`/`auto`/`dontAsk`/`bypassPermissions`/`plan`/`manual` | ignored for plugin subagents per the doc — likely why unused |
| `maxTurns` | 0/31 | hard turn cap before the subagent stops | no runaway-subagent incident in the corpus that would have needed it |
| `skills` | 0/31 | preloads full skill **content** (not just description) at startup | **probed 2026-07-27: BINDS.** Agent recited an unguessable token from the skill body with zero tool calls. Precondition: the skill name must be resolvable from the session's `--setting-sources`. See § Discharge candidates |
| `mcpServers` | 0/31 | grants MCP servers not in the parent session; ADD-only, no restriction semantics (§ 3 below) | — |
| `hooks` (frontmatter) | 0/31 | `PreToolUse`/`PostToolUse`/`Stop` scoped to just this agent | **probed 2026-07-27: SILENTLY IGNORED from an `agents/*.md` file** — binds only via `--agents` JSON. This is the mechanism coordinator uses, so the discharge candidate below is blocked as designed. See § Discharge candidates |
| `memory` | 0/31 | `user`/`project`/`local` — persistent cross-session agent memory dir | **probed 2026-07-27: BINDS, incl. genuine cross-session recall.** Creates and populates `.claude/agent-memory/<agent>/` (`MEMORY.md` + memory files); a separate fresh process recalled the canary. See § Discharge candidates |
| `background` | 0/31 | force background-task execution | harness default (v2.1.198+) already runs subagents backgrounded unless Claude chooses otherwise |
| `effort` | 0/31 | `low`/`medium`/`high`/`xhigh`/`max`, overrides session effort | **notable gap** — the Claude API docs specifically recommend `low` for subagent-shaped work, and every one of our 31 agents is exactly that shape; we set it nowhere |
| `isolation` | 0/31, **blocked by policy** | `worktree` — auto-sandboxed git worktree for one risky dispatch | the harness offers this field, but per-agent git worktrees are structurally banned fleet-wide — they degrade badly on Windows (the primary machine and audience) and don't scale to a concurrent agentic fleet; reaching for `isolation: "worktree"` requires explicit PM permission via the EM, it is never a default choice. Also distinct from fan-out wave shape (never worktree-per-item, per `fanout-shape-scoped-parallel-not-sequential-not-worktree` lesson) — this field is a single-agent sandbox, not a wave pattern |
| `initialPrompt` | 0/31 | auto-submitted first turn for a **main-session** agent via `--agent` | N/A to subagent dispatch — this field only matters when an agent def is loaded as the whole session's persona, which we don't do |

**`access-mode` (32/33 agent files) is not a documented `sub-agents.md` field** — it's a
coordinator-invented convention (`read-only` / `read-write`) layered on top, enforced by our own
tooling/doctrine, not by the harness. Don't confuse it with a real frontmatter contract field when
reading an agent definition.

**`mcpServers` semantics, precisely** (`_verify-harness-capabilities.md § 3`): it is additive
provisioning, never a restriction. An inline `mcpServers` entry gives the subagent servers the
*parent doesn't have at all* (and keeps their tool descriptions out of the parent's context); a
string-reference entry shares the parent's existing connection. There is no "only these servers"
mode. If the goal is restricting a subagent to a named subset of MCP tools, that's
`tools`/`disallowedTools` with `mcp__<server>__*` patterns — `mcpServers` cannot substitute for
graduated `ToolSearch` disclosure-scoping, which solves a different problem (progressive context
cost, not grant scope).

### Discharge candidates worth naming (not yet built)

- **~~`hooks` on the read-only reviewer family~~ (code-reviewer, prior-art-checker,
  plan-coverage-checker, doc-link-checker) — BLOCKED AS DESIGNED, probed 2026-07-27.** The idea
  stands: a `PreToolUse` hook denying `Write|Edit` scoped to just that agent would be a second,
  independent enforcement layer under "reviewer never writes", where today only the `tools:`
  allowlist enforces it and a future edit could loosen that unnoticed. But the mechanism does not
  work from an `agents/*.md` file — the `hooks` key is silently dropped (verified twice
  independently; the same frontmatter's `tools:` registers fine, so it is not a parse or discovery
  failure). It binds only via `--agents` JSON provisioning. Adopting this means moving the reviewer
  family off agent-files, which is a far larger change than this bullet implies. Re-verify on any
  harness bump — `sub-agents.md` documents the file-based path as working, so this may be a
  version-specific defect.
- **`skills` preload** on doctrine-heavy dispatches (e.g. `review-integrator.md`): forces the full
  doctrine content into the subagent's start-of-context rather than trusting it to `Read` a pointer
  path — the design-as-offers principle applied to the dispatch layer, at the real cost of eating
  token budget on every dispatch regardless of job size.
- **`memory: project`** as a scoped pilot on one review persona (e.g. code-reviewer), to let it
  accumulate "seen this class of finding before" notes across sessions the way the EM's own
  MEMORY.md already does — not a blanket rollout, adoption depends on the agent being told to
  consult/update it.
- **`disallowedTools`** for the small number of intentionally-broad-access agents (executor and
  similar) — converts them from a hand-maintained allowlist that silently misses new harness tools
  to an auto-inheriting one. Wrong move for narrow-purpose read-only agents, where a positive
  allowlist is the correct security posture, not debt.

## 3. Settings — scope table only; full key reference not archived

`state/reference/anthropic-docs/claude-code/settings.md` is a 26-line **stub**, truncated after
the scope table — the actual settings-key reference was never captured. Don't treat its absence
here as "nothing to know"; it's an archive gap, flagged for a future harvest pass. What the stub
does confirm: four scopes — **Managed** (server/plist/registry, org-wide), **User** (`~/.claude/`),
**Project** (`.claude/`, committed), **Local** (`.claude/settings.local.json`, gitignored). On this
machine, `~/.claude/settings.json` carries an empty `hooks` object — all coordinator hook
registration lives in the plugin's own `coordinator/hooks/hooks.json`, not in settings.

## 4. Plugin manifest and marketplace — coordinator uses the minimal shape

`plugin.json` is optional; component dirs auto-discover by default location
(`skills/`, `commands/`, `agents/`, `hooks/`). Full manifest schema
(`plugins-reference.md § Complete schema`) supports `displayName`, `version`, `description`,
`author`, `homepage`, `repository`, `license`, `keywords`, `skills`, `commands`, `agents`,
`workflows`, `hooks`, `mcpServers`, `outputStyles`, `lspServers`,
`experimental.{themes,monitors}`, `userConfig`, `channels`, `dependencies`, `defaultEnabled`.

Coordinator's actual `coordinator/.claude-plugin/plugin.json` sets only `name`, `version`,
`description`, `author`, `repository`, `keywords` — no custom component paths, no `mcpServers`, no
`lspServers`, no `experimental` block, no `userConfig`, no `channels`, no `dependencies`,
`defaultEnabled` unset (defaults `true`). All components resolve via the default-location scan.
The one non-default component in use is `workflows/review-wave.mjs` — one canned ceremony ships as
a native plugin `Workflow` script; the rest of multi-wave orchestration is ad-hoc
EM-authored `Workflow` invocation (`workflow-orchestration.md`). Whether more ceremonies should
graduate to canned `workflows/*.mjs` is an open PM-altitude question, not a mining finding.

`claude plugin validate --strict` treats unrecognized/misspelled manifest fields as errors instead
of warnings — worth running once on any manifest edit, since a typo'd field name otherwise loads
silently.

Marketplace schema (`plugin-marketplaces.md`) governs the separate OSS-publish
`coordinator-claude` marketplace entry — out of scope for this wiki; see
`coordinator/docs/wiki/percolate-setup.md` for that path.

## 5. Skills frontmatter — 4 of 17 documented fields in use

35 `SKILL.md` files under `coordinator/skills/`. `skills.md § Frontmatter reference` documents 17
fields beyond the always-required-in-practice `name`/`description`. Adoption:

| Field | Used by | Note |
|---|---|---|
| `name` | 35/35 | — |
| `description` | 35/35 | — |
| `argument-hint` | 22/35 | autocomplete hint, e.g. `[issue-number]` |
| `user-invocable` | 1/35 | hides a skill from the `/` menu when `false` |
| `disable-model-invocation` | 0/35 | prevents auto-loading; also blocks `skills:` preload into subagents (§ 2) and scheduled-task firing |
| `allowed-tools` | 0/35 | pre-approves tools for the invoking turn only, clears on next message |
| `disallowed-tools` | 0/35 | strips tools for the invoking turn only |
| `model` / `effort` | 0/35 | per-invocation override, reverts next turn |
| `context: fork` / `agent` / `background` | 0/35 | runs the skill in a forked subagent context |
| `hooks` | 0/35 | skill-scoped lifecycle hooks |
| `paths` | 0/35 | glob-gated auto-activation — **already spun off**, see `docs/plans/2026-07-27-doctrine-envelope-allocation.md` line 770 (path-scoped `.claude/rules/` conversion), not re-proposed here |
| `arguments` / `when_to_use` / `shell` | 0/35 | named-arg substitution / extra trigger context / PowerShell inline blocks |

The command-name resolution rules (`skills.md § How a skill gets its command name`) matter for
plugin skills specifically: in a plugin `skills/` subdirectory, frontmatter `name` sets the last
segment of the invoked command, namespaced by the plugin (`coordinator:plan`, not bare `/plan`,
unless nothing else claims the bare name).

## 6. Output styles, statusline, model config

- **Output style** (`output-styles.md`): a style file inserts instructions directly into the
  system prompt — a structurally different binding layer than a `CLAUDE.md` instruction the model
  must recall and re-apply every turn. Not in use here. Worth naming: `~/.claude/CLAUDE.md
  § Communication Style` opens by admitting "'Concise' as an adjective has repeatedly failed to
  bind" — that sentence is itself evidence the current prose-only enforcement isn't holding, and an
  output style is the one documented mechanism purpose-built to fix exactly that failure mode. Not
  yet built; would need to verify it doesn't fight `keep-coding-instructions: true` semantics and
  survives across `/clear`/new-session boundaries (the doc says it applies only after those).
- **`subagentStatusLine`** (`statusline.md § Subagent status lines`, v2.1.205+/v2.1.214+-gated
  fields, both below our installed 2.1.220): a custom row per visible subagent fed `id`, `name`,
  `status`, `model`, `effort`, `contextWindowSize`, `tokenCount`. Not in use — today, fan-out wave
  progress is invisible until a `PostToolUse`/`Agent`-matcher hook fires (`agent-completion-log.py`,
  `track-dispatched-agents.py`), i.e. only after each subagent finishes, not live.
- **Model config** (`model-config.md`): `fallbackModel` / `--fallback-model` (up to 3, tried in
  order on overload) — zero adoption, reliability lever not a doctrine one; a PM infra-preference
  call (accept a cheaper/faster silent substitute on overload), not proposed here.

## 7. CLI scripting flags — real, but off the reachable path (see § Reality filter)

`cli-reference.md` documents ~50 flags. The ones with actual teeth for a scripting/CI use case:
`--output-format {text,json,stream-json}`, `--json-schema '<schema>'` (validated structured output
in a `structured_output` field; invalid schema fails loud, fixed v2.1.205), `--bare` (skip
auto-discovery for faster cold start), `--print`/`-p`, `--max-turns` (print-mode only),
`--include-hook-events`. All require a `claude` **subprocess** invocation — none are reachable from
in-session `Agent`/`Task` dispatch. `--max-budget-usd` caps a whole `claude` process and doesn't
map onto in-session dispatch either, for the same reason. The one live use of this surface in this
repo is `coordinator/docs/claude-cli-subprocess-contract.md`'s six-item contract (`--output-format
json` for `total_cost_usd`/`usage.*` telemetry) — its `--json-schema` gap for structured
deliverables (vs. text-parsed `result`) is a named-but-unbuilt discharge candidate, and its
executable call sites now live in `claude-klabauter` (commit `b644d5a9`), not here.

## What's confirmed absent, not just unused

- **No programmatic/hook-accessible surface for `/usage` or `/usage-credits` token/cost data.**
  Neither is documented anywhere in `costs.md`, `hooks.md`, or the (stub) `settings.md`. `PreToolUse`
  /`PostToolUse` hook input carries tool name/input, never cost figures; `SessionStart` input
  carries `model` but not usage. Our context-pressure hook's byte-size-sentinel approach exists
  because there is no better documented alternative. OpenTelemetry is the one real programmatic
  cost/usage channel that exists at all, but its metric schema isn't archived anywhere in this
  corpus — flagged UNKNOWN, not guessed at.
- **`context-window.md`** is a web-only interactive visualization, not a runtime API — don't expect
  a hook or CLI surface for it.
