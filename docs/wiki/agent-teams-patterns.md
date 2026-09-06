---
title: Agent Teams patterns
created: 2026-05-17
type: doctrine
related:
  - plugins/coordinator/docs/wiki/dispatching-parallel-agents.md
  - plugins/coordinator/docs/wiki/staff-sessions.md
---

# Agent Teams Patterns

Structural patterns for the Agent Teams API — the 7-teammate limit, pipeline composition, and the `blockedBy` gate.

> **As of Claude Code v2.1.178, teams form implicitly on first teammate spawn — there is no `TeamCreate`/`TeamDelete` tool; `team_name` on the Agent tool is accepted but ignored. Source: https://code.claude.com/docs/en/agent-teams.md**

## 7-teammate hard limit

Agent Teams cap at 7 concurrent teammates per team. Spawning an 8th teammate (via the `Agent` tool) does not error loudly — the dispatch silently blocks, the teammate never starts, and the pipeline stalls waiting for output that never arrives.

Design pipelines with the limit in mind. A stage with 6 specialists plus 1 synthesizer is fine; 7 specialists plus a synthesizer exceeds the cap.

## Phased spawning for pipelines longer than 7 stages

When a pipeline requires more than 7 stages, phase the spawning: dispatch the first phase as a normal subagent (not a team member), and have it spawn the next phase once early stages complete. The 7-limit is per-team, not per-session — a session can host multiple sequential teams.

Pattern for a 10-stage pipeline:

1. EM dispatches Phase-1 subagent (stages 1–4, no team needed).
2. Phase-1 subagent completes; writes output to disk.
3. The phase-1 subagent spawns the phase-2 teammates via the `Agent` tool once early stages complete (no `TeamCreate` call); teams are session-scoped and form implicitly. Phase-2 reads Phase-1 output from disk.

The gate between phases is a disk write + EM coordination step. Do not attempt cross-team `blockedBy` wiring — teams are isolated; `blockedBy` task IDs only route within the same team.

## blockedBy is a gate, not a trigger

→ `coordinator/snippets/em-operating-doctrine.md` § How to Dispatch, "Agent Teams" — "A teammate blocked on `blockedBy` will not auto-resume — `SendMessage` to wake it."

A teammate that enters idle state on a `blockedBy` dependency will NOT auto-resume when the dependency resolves. The unblocking teammate must explicitly `SendMessage` to the waiting teammate to wake it. Missing this step causes silent pipeline hangs — all teammates look healthy (no error) but downstream stages never run.

The remediation when a pipeline appears stalled: check whether any teammate is in a `blockedBy`-idle state, identify which upstream task just completed without sending a wake message, and `SendMessage` the idle teammate manually.

## Cross-machine concurrent pickup is fail-loud

When two machines simultaneously attempt `/pickup` on the same handoff, the fail-loud signal is `consumed_by:` — or its DR-084 successor `claimed_by:` (write path not yet cut over, corpus mixed on disk; check both) — populated in the handoff's frontmatter after `git fetch`. Do not redispatch over partial work — `SendMessage` the existing agent to resume from transcript. Redispatch over partial work produces two agents writing to the same output paths, which silently corrupts the deliverable.

**`claimed_by` is a session id, and messaging addresses a peer name — resolve the one to the other, don't infer it.** A computed claim decision already carries `send_message_address` on its `competing_claim[]` entry; use that field and never re-derive one. With no claim decision to consult — a sid read off a commit trailer, a queue entry, or a plan body — run `python3 coordinator/bin/resolve-peer-address.py <session-id>`, which prints the peer name and distinguishes *no record* (exit 3) from *record found, process dead* (exit 4). It reads `~/.claude/sessions/<pid>.json` (one record per live session, carrying `name`, `pid`, `cwd`, `status`), the same join `claude-klabauter`'s `coordinator_core/session/reachability.py` :: `resolve_advisory_address` wraps on the engine plane.

**Resolve at point of use, and expect empties that are not deaths.** A session id churns inside a single session's lifetime — a resume or `/clear` mints a new `sessionId` while the name and pid persist — so a `claimed_by` stamped earlier can resolve to nothing while its author is still running under the same name. An empty resolution is therefore not evidence the holder is gone; check the registry for a live row on the same workstream before concluding anything. Check `--near <workstream-path>` for a live row on the same tree before concluding anything. When that really does come back empty, stand down and write what the holder needs into the artifact it is working from — never guess a name from roster start times, and never fall back to the redispatch this section forbids.

→ `coordinator/skills/handoff/SKILL.md` § Handoff Lineage — no adjacency-inference — for the concurrent-pickup contract.

## MCP Tool Names May Differ Between Parent and Teammate Sessions

Deferred tool names in Agent Teams teammates can vary from what the parent session sees. A tool that appears as `mcp__notebooklm-mcp__*` (the current external NotebookLM server) in the parent may arrive under a different prefix variant inside a teammate's session — historically seen variants for this same tool include the bare `mcp__notebooklm__*` form and the now-retired vendored `mcp__plugin_notebooklm_notebooklm__*` prefix. Hardcoding a single name pattern in the teammate prompt produces silent "tool not found" failures.

**Rule:** always use graduated ToolSearch in teammate prompts — `select:<exact-name>` first, then keyword `+prefix` fallback, then graceful failure with a diagnostic message. Never embed a naked `mcp__*` name as a constant in a teammate brief without a fallback resolution step.

## Synthesizer position: blocked by all specialists, reads from disk

The synthesizer task should be blocked by every specialist task. Once unblocked, the synthesizer reads specialist outputs directly from disk — no consolidator intermediate, no EM forwarding of chat transcripts. This keeps the synthesizer's input surface deterministic and avoids the "synthesizer receives a paraphrase" failure mode.

When wiring the synthesizer's dispatch prompt, name the exact disk paths where specialist outputs land. The synthesizer reads those paths on startup and treats them as authoritative. Chat transcripts from specialist sessions are not reliable inputs — they can be truncated, reordered, or paraphrased by the runtime.

→ `coordinator/agents/parallel-review-synthesizer.md` and `coordinator/agents/research-synthesizer.md` for the no-rewrite contract, enforced directly in each synthesizer's prompt.

## Don't advertise tools the runtime doesn't expose

<!-- provenance: run 2026-08-06-14h38, nugget c7-055 -->

`code-reviewer` and 25 other agent prompts advertised `Grep`/`Glob` as available tools, but neither is exposed to the EM or subagent runtime — the actual content-search/file-location path is `grep`/`find` via Bash (see the Explore/RAG preamble conventions). The root cause was doctrine text that told every agent author to reach for `Grep`/`Glob` by name; agent prompts inherited the wrong tool names from that shared doctrine rather than from the actual exposed toolset.

Both the doctrine and the 26 agent prompts were corrected in the same pass, with a regression test added to keep an agent prompt from re-advertising a non-exposed tool name. When authoring or reviewing an agent prompt, verify tool names against what the runtime actually exposes, not against habit or older doctrine text.
