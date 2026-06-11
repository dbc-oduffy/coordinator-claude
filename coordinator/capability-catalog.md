<!-- Maintenance: update when plugins change. Version: 1.3 | Last reviewed: 2026-05-30 -->

# Specialists — Route, Don't Execute

## Why Delegation Is Superior, Not Just Correct

Domain agents aren't a hierarchy — they're a capability gap in your favor. A specialist dispatched for one task has advantages the orchestrator cannot replicate in its own context:
- **Tool access:** typed domain tools with validation, loaded in the agent's context — tools the EM would otherwise have to ToolSearch for one at a time.
- **Loaded knowledge:** pre-baked domain patterns, verification protocols, and operational skills baked into the agent's system prompt.
- **Context efficiency:** fresh Sonnet context dedicated to one task vs. Opus context juggling orchestration state.

Keeping domain tool schemas out of the EM's context window saves tokens better spent on orchestration judgment than tool definitions.

Before using a tool yourself, ask: would a specialist produce better results? The answer is almost always yes for multi-step work.

When a reviewer returns findings, **accept their expertise** — implement ALL items, including P2s, nitpicks, and suggestions to defer. Every finding is an opportunity to meet or exceed their quality bar. The only exceptions: escalate to the PM when findings change scope, or push back if you believe the reviewer is genuinely wrong (state why explicitly).

**the Staff Engineer** — architecture + code review. Use `/review` (plan artifacts) or `/review-code` (code artifacts).
**Enricher/Executor** — codebase research + implementation. Use /enrich-and-review; for executor dispatch follow `docs/wiki/delegate-execution.md`.

**the Data Science Reviewer** — ML, statistics, RAG eval, training. Route: any AI/data pipeline work.

> **UE / holodeck / game-dev capabilities** — when the `game-dev` and `holodeck-control` plugins are active, see `capability-catalog.holodeck.md` (the Game Dev Reviewer, the UE Editor domain agents, ue-docs-researcher, the cinematic / virtual-production agents, and the UE game-dev workers). Not shipped in the OSS coordinator distribution — those agents require the holodeck-control MCP.

**NotebookLM** — break-glass for YouTube/podcasts/audio Claude can't access. Use /notebooklm-research. NOT for normal web research. *(requires deep-research plugin with notebooklm)*

**the Front-End Reviewer** (senior-front-end) — front-end review (tokens, design system, CSS). **the UX Reviewer** — UX flow review (trust, clarity). Use `/review` (plan artifacts) or `/review-code` (code artifacts).

**vp-product** (the VP-Product Reviewer, they/them) — VP of Product with software-engineering instincts. Stress-tests shape choices before they ship: refactor-over-patch advocacy, "have you considered a different shape", and the dumb questions experienced engineers skip. Distinct from the Staff Engineer (code quality) and the Director of Engineering (DoE backstop). Run the VP-Product Reviewer on plans, on completed work before merge, and any time the EM proposes a patch where a refactor would be cheaper long-term. Primary dispatch path: `/staff-session` when VP-of-Product lens is included; otherwise explicit PM ask only — not EM-self-triggered.

**eng-director** (the Director of Engineering) — Director of Engineering. Three modes: (1) **standalone primary reviewer** (default; dispatched directly via `/review`, `/review-code`, or `coordinator:eng-director` for cross-team / cross-repo / generic-substrate reviews — peer of the Staff Engineer in technical rigor, with DoE-altitude authority to set cross-team boundaries the Staff Engineer would hedge on); (2) **backstop reviewer** (chained after the Staff Engineer on High-effort architectural reviews); (3) **staff-session synthesizer** (spawned by `/staff-session`, blocked until debaters complete, resolves contested topics with DoE authority — organizational benefit, customer-serving, velocity-over-time — not by averaging the loudest debaters).

**Agent Teams** — collaborative multi-agent work with messaging and shared task coordination:
- `/staff-session --mode plan` — domain experts debate (the Staff Engineer, the Data Science Reviewer, the Front-End Reviewer, etc.), the Director of Engineering (eng-director) synthesizes with ambition lens. Tier selection and composition: `docs/wiki/staff-sessions.md`.
- `/staff-session --mode review` — same debate structure for critiquing existing artifacts. The Director of Engineering synthesizes findings. Lightweight tier falls through to single-reviewer dispatch via `/review` (plan) or `/review-code` (code).
- `/deep-research:research --mode=web <topic>` — Pipeline A: internet research (scout → specialists → synthesizer) *(requires deep-research plugin)*
- `/deep-research:research --mode=repo <path>` — Pipeline B: repository analysis (scouts → specialists → synthesizer) *(requires deep-research plugin)*
- `/deep-research:research --mode=structured <spec-path>` — Pipeline C: schema-conforming batch research *(requires deep-research plugin)*
- `/notebooklm-research` — Pipeline D: media research via NotebookLM MCP *(requires deep-research plugin with notebooklm)*

When to use teams vs. subagents: teams when agents need to **communicate** (cross-pollinate, resolve contradictions, share discoveries); subagents when tasks are **independent** (no cross-agent value). Teams are fire-and-forget — the EM scopes, spawns, and is freed.

**Merge-gate synthesizers** (invoked by specific ceremonies, not directly by EM):
- **parallel-review-synthesizer** — reads the output of N code-semantics chunk reviewers (`code-reviewer-weekly`) + 3 mechanical workers (security-audit-worker + dep-cve-auditor + test-evidence-parser) and synthesizes a structured BLOCKED/WARN/OK verdict, plus an `arch_tier_candidates` bucket aggregated from chunk reviewers' `escalate_to_architecture` flags. Writes `synthesis.json`; never rewrites finding text; emits verbatim quotes only. Invoked exclusively by `coordinator:parallel-code-review` as part of `/workweek-complete` Step 7 gate.
- **code-reviewer-weekly** — weekly-gate variant of `code-reviewer` (Sonnet, code-semantics lens). Same obsessive standards but writes findings incrementally to a single assigned `$FINDINGS_DIR/chunk-<k>.md` (crash-safe under compaction), and marks architectural findings `escalate_to_architecture: true`. One instance per disjoint file-scope chunk. Dispatched only by `coordinator:parallel-code-review`.

**Pipeline orchestrators** (dispatch via commands, not directly):
- **deep-research-orchestrator** — /deep-research dispatches this (lives in the deep-research plugin). Reads PIPELINE.md, runs Haiku→Sonnet→Opus. *(requires deep-research plugin)*
- **coverage-auditor** — post-synthesis coverage auditor for all deep-research pipelines (A web / B repo / C structured / D notebooklm). Dispatched by the EM as a NON-TEAMMATE Agent after synthesis completes. Reads specialist claim records, cross-references the synthesis, emits a `-coverage-audit.md` sidecar. READ-ONLY on the synthesis output path — never writes it. Answers: (1) did the synthesis carry each specialist claim? (2) what was distilled out, and where can a reader go deeper? Always-on; no size floor; no opt-out. *(requires deep-research plugin)*

**EM-driven pipelines** (command contains full orchestration logic, dispatches leaf agents directly):
- `/bug-sweep` — EM scopes→dispatches Haiku/Sonnet scanners→triages→dispatches Sonnet executors→commits fixes.
- `/architecture-survey` — EM scopes→dispatches Haiku scouts→dispatches Sonnet analysts→dispatches Opus synthesizer→commits atlas.

**Pre-review pre-flight agents** (dispatched before the first Opus reviewer; write sidecars, not reviews):
- **prior-art-checker** — cross-references a plan's claim surface against project wikis, global wikis, `state/lessons.md`, and the central improvement queue. Returns a sidecar with three buckets: Conflicts (plan contradicts prior art), Compatible-but-relevant (plan should cite), and Silent (no signal). Verdict is COMPATIBLE / WARN / BLOCKED-SURFACE-TO-PM / DEGRADED. Invoked inside `coordinator:plan` before the Staff Engineer; never modifies the plan itself.

**Reviewer-routed workers** (dispatched by EM after a reviewer names them in a `## Worker Dispatch Recommendations` block — never dispatched directly by reviewers):
- **test-evidence-parser** — runs a test command (Jest/pytest/cargo/Go/RSpec — auto-detected), classifies each failure as `real / flake / env / timeout / known-skip`, returns structured markdown table. Dispatch when the Staff Engineer flags test failures needing mechanical triage.
- **security-audit-worker** — static security scan of a diff or file set; detects path traversal, validation-vs-rewrite traps, command injection, secret leakage, env-var ingestion; runs semgrep → bandit/gitleaks → grep-heuristics fallback chain. Dispatch when the Staff Engineer flags a security surface in review.
- **dep-cve-auditor** — reads dependency manifests (`package.json`, `requirements.txt`, `Cargo.toml`, `go.mod`, `pyproject.toml`), runs ecosystem audit tools (`npm audit`, `pip-audit`, `cargo audit`, `govulncheck`), classifies CVEs by severity and our actual usage. Dispatch when the Staff Engineer flags a CVE surface, or via `/workweek-complete` Step 4h (change-aware: fires only when a tracked manifest changed in the week).
- **doc-link-checker** — crawls `docs/` (or a specified path), validates internal markdown links (file + anchor existence) and external URLs (HEAD requests, 100-URL cap, 1s rate limit), returns structured broken/redirect/timeout table. Dispatch opportunistically from `/update-docs` or when a reviewer recommends it.
