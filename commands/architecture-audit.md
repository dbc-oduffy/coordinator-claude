---
name: architecture-audit
description: "Rotational arch audit — score systems, audit the top, package spinoffs. Never edits code."
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent"]
argument-hint: [system-name]
---

Read and follow the instructions in ${CLAUDE_PLUGIN_ROOT}/skills/architecture-audit/SKILL.md

<!--
This audit's Haiku→Sonnet pre-digestion (SKILL.md Step 3, >10-file path) dispatches the SAME
Phase-1/1R and Phase-2 templates the rebuilt /architecture-survey uses, sourced from one shared
template file: `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-architecture-survey/agent-prompts.md` — no
separate copy exists here to go stale. Three things that do NOT apply to this audit are
deliberate, not gaps — do not "fix" them:

- **claude-klabauter extraction consumption (`cartography.*` ops replacing agentic Phase-1 inventory)** does
  not apply here: that consume-gate is wired into /architecture-survey's first-run/refresh atlas-
  *construction* pipeline (full-tree extraction), whereas this audit is a narrower re-review of ONE
  system the atlas already describes (SKILL.md Step 2.5 loads the existing atlas page precisely so
  reviewers do NOT re-derive structure). Wiring claude-klabauter's precomputed substrate into this audit's
  pre-digestion is new scope for a future plan, not an omission of this one.

- **Workflow-native dispatch** (single background Workflow owning a multi-phase, multi-system wave
  map) does not apply here either: this audit dispatches exactly ONE system per invocation, a
  single short-lived 3-tier fan-out — not the multi-wave, multi-system problem the Workflow vehicle
  exists to solve. Only if a future change makes this audit batch multiple systems per invocation
  does that become worth revisiting.

- The **H2 anchors** this audit's Sonnet analysis prompt relies on (`## System Narrative` /
  `## Information Flow Diagram` / `## Boundary Catalog` / `## Health Grade` / `## Summary`, under
  "Phase 2: Sonnet System Analysis Prompt (Audit)" in the shared template file above) must
  continue to exist verbatim — renaming any of them silently breaks this audit without touching
  this file, so check here before renaming those headings in the shared template.
-->
