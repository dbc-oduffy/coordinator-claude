---
kind: wiki
title: Dogfooding Doctrine — Fix-Through Validation of New Capabilities
status: active
created: 2026-05-07
last_updated: 2026-05-07
sources:
  - coordinator/skills/dogfood/SKILL.md
  - coordinator/docs/wiki/dogfooding-doctrine.md § Cross-References (formerly coordinator/CLAUDE.md § Self-Improvement Loop; relocated here 2026-07-27)
tags: [dogfood, validation, fix-through, lesson-capture]
---

# Dogfooding Doctrine

> Spec backlink: this file's own `§ Cross-References` — "Dogfood new capabilities end-to-end via
> `/dogfood` before declaring stable." (Formerly `coordinator/CLAUDE.md` § Self-Improvement Loop;
> relocated here as part of that file's retirement — see § Cross-References below for
> the full provenance note.)
<!-- Review: coordinator:code-reviewer — Finding 8: this backlink quoted CLAUDE.md prose deleted
     by the 2026-07-27 relocation; repointed self-referentially to this file's own § Cross-References,
     which already carries the full provenance story. -->

Dogfooding is the discipline of invoking a newly-built capability end-to-end and fixing everything that breaks before declaring the pattern stable. It occupies a specific and load-bearing position in the improvement loop: between lesson capture and stable-pattern declaration. Skip it and the lesson remains a hypothesis; complete it and the capability is proven at the surface that matters.

---

## 1. Why Dogfooding Is the First Validation Pass

The improvement loop in this system runs: **observe a recurring pattern → capture a lesson → distill into doctrine → build the capability** (skill, script, pipeline, hook). At that point, the capability exists as text. It has not been invoked. The lesson that motivated it has not been falsified.

Dogfooding is the step that converts "we wrote a thing" into "the thing works." It runs *before* the pattern is declared stable because stability is a runtime property, not a text property. A skill body that looks correct in review and fails in use is not a stable pattern — it is a draft that happened to survive review.

The alternative — declaring stability at merge time and finding bugs in production — is more expensive: the next session inherits a broken capability, the lesson that validated it is wrong, and the fix has to be rediscovered rather than being in-session and in-cone.

Running at the source-of-truth surface (the actual invocation, not a simulation of it) beats reasoning about correctness from the spec for the same reason real integration tests beat unit tests that mock every dependency: the real surface is where the unexpected failure modes live.

---

## 2. What "Fix-Through" Means

Dogfooding is **binary**: either the capability converges (works end-to-end) or the session switches gears (surfaces a replan ask to PM). There is no third outcome.

The forbidden middle ground is **file-and-defer**: the dogfood run surfaces a bug, the bug gets logged to `state/bug-backlog/` or a note in the handoff, and the session moves on. This pattern means:

- The capability has not been proven. The lesson it was meant to validate remains a hypothesis.
- The bug is now disconnected from the context in which it was found. Future sessions that pick it up from the backlog have lost the reproduction environment and the fix-cone.
- The "dogfood" was actually a discovery run wearing a dogfood costume. Discovery is useful; calling it dogfood misrepresents the validation status of the capability.

Fix-through means: every in-cone bug found during the run is fixed in the same session, on the same branch, before the loop exits. The run does not end until the capability works or the session explicitly switches gears with PM confirmation.

**Surface-and-skip is the narrow exception**, not the conservative move. Skipping is structurally correct only for: bugs requiring a PM-level product decision, external dependencies, or architectural rework that the plan author needs to redo. Skip ratio above 40% in a session signals the dogfood has lost fix-through character and should be re-evaluated.

---

## 3. The Convergence Signal

A dogfood run needs a **concrete, machine-readable signal** that proves the capability worked end-to-end. Without one, the run is a vibes-check: the EM observed some output, formed an impression, and called it done. That is not a proof.

Acceptable convergence signals:

- **Exit code 0 on the primary happy path** — with cross-channel consistency (exit code matches stderr severity, status file matches probe behavior).
- **Probe status mtime advancing** — a readiness probe whose status file updates to a known-good state proves downstream consumers will see the result.
- **Log line transition** — a tagged stdout line whose value changes from a failure-class to a success-class across iterations (e.g., `Probe 9: FAIL → PASS`).
- **Per-iteration modes.json going empty** — the `/dogfood` skill's mandatory `pass-<N>-modes.json` artifact converges to zero `{component, error-class}` tuples when no in-cone bugs remain.

The convergence signal must be declared before entering the loop (Gate 2 of the `/dogfood` skill). If the target doesn't emit machine-parseable output, the first deliverable is a wrapper that produces it — not skipping the gate.

---

## 4. When to Switch Gears

Switching gears is correct when convergence is unattainable in-session without reversing a load-bearing structural choice. Signals that warrant it (from the `/dogfood` skill's switch-gears criteria):

- `pass-<N>-modes.json` contains ≥3–4 distinct `{component, error-class}` tuples — the loop has shifted from "verify a fix" to "discover more bugs," which is a different activity.
- The same `{component, error-class}` tuple appears unchanged from pass N to pass N+1 — the loop is stuck.
- The fix cone requires reversing an architectural decision the plan author made intentionally.
- Skip ratio exceeds 40% of findings in the session.

On switch-gears, the EM proposes to PM with the mechanical signal as evidence, gets confirmation, and ends the loop. The session output is the replan ask — a precise description of what shape the rework needs to take. It is not a backlog dump and not a handoff with "investigate X" as the next step.

Grinding past the switch-gears threshold because the budget still permits more iterations is the failure mode. Budget exhaustion is itself a switch-gears signal; it does not authorize filing the remainder to the backlog.

Acceptance criteria that require PM-eyeballs verification ("PM confirms the rendered output looks right") are legitimate autonomous-mode stop conditions — the autonomous run pauses, surfaces the artifact, and waits. This is not a "work item" to defer; it's a structural gate in the dogfood loop.

---

## 5. What Dogfooding Is NOT

Dogfooding is **not**:

- **Unit tests** — unit tests validate components in isolation with controlled inputs. Dogfooding exercises the complete capability at its actual invocation surface with realistic inputs.
- **Type checks or lint** — static analysis catches textual errors; dogfooding catches runtime behavior.
- **A smoke that exits 0 without exercising the new path** — if the smoke doesn't trigger the code that was added, it didn't prove anything about the addition. An exit-0 smoke on a path that wasn't exercised is not a convergence signal; it's a false positive.
- **A discovery run** — discovery (surfacing what exists or what's broken) is a precursor to dogfooding, not a synonym. Dogfooding begins after the capability exists and runs until it works or gets replanned.

The `/dogfood` skill is distinct from `/bug-blitz` (works a known backlog) and `/bug-sweep` (searches the repo for latent bugs). Dogfooding is invocation-driven; it finds bugs the new thing causes when used, not bugs that were already there.

---

## 6. Recent Example — 2026-05-07 Agentic Install Hardening

The agentic-install-hardening dogfood smoke is the canonical example of fix-through behavior.

Three real bugs surfaced and shipped in the same session:

- **W6 (`e35c6551`):** `install_status_writer` did not accept `status=skip` via `phase_end`. This caused phases that legitimately produced no work to emit no signal, leaving the watchdog and probe consumers without confirmation that the phase ran. Fixed forward.
- **W7 (`ab951c2a`):** Watchdog autostart relied solely on Task Scheduler, which is unavailable on locked-down user profiles. The fix added a Startup-shortcut fallback and added unconditional immediate-launch at install time, closing a race window where the watchdog was not running between install and the first scheduler trigger.
- **W8 (`f7f6c552`):** Setup honesty — phase status accuracy and summary truth-telling. The setup script reported phases as complete when their observable output (status file, probe state) hadn't confirmed it.

The convergence signal was concrete: **Probe 9 status mtime advanced from FAIL to PASS in 0.9 seconds** after W7 landed. That transition was the observable that proved the capability worked end-to-end.

Universal lesson captured from this run: **"Dogfood means fix-through, not file-and-defer."** No bug from this run was deferred to `state/bug-backlog/`. All three were fixed in the same session, on the same branch, with smoke evidence in the commit message.

Canonical archived plan: `archive/specs/2026-05-06-agentic-install-hardening.md`.

---

## 7. E2E Gate Timing — Schedule as Early as the Producer Can Compile

End-to-end execution gates catch real bugs that unit tests + structural verification miss. The Stream-J β.5 dogfood surfaced **five distinct bugs in one session**, all in code that had passed unit tests + structural review + docs-check:

1. A spec-cited API function that did not exist in the target engine version (docs-check Gate A blind spot).
2. A C++ namespace-shadow bug (no test exercised the multi-item header path).
3. An MSYS path-translation bug in the wrapper script (`--dry-run` skipped the node handoff that triggered it).
4. `/tmp` manifest paths handed to `node.exe` (same dry-run blind spot).
5. A C++ batch-output overwrite-per-iteration bug (explicit TODO-confessed in code; reviewer didn't catch it).

Each caught **only when the actual end-to-end flow ran** — the producer was actually invoked, the rebuilt plugin actually loaded, the multi-item commandlet actually iterated. Several were one-line fixes with high cost-to-find ratios. Without the e2e gate, they'd have shipped and surfaced at next-consumer's first attempt.

**Rule:** when a plan has an end-to-end execution gate (`/dogfood`, integration smoke against real runtime, β.5-style "rebuild + run capture script live"), **schedule it as soon as the producer-side artifacts can plausibly compile and invoke** — don't wait until everything looks structurally clean. The structural-clean state is precisely when latent integration bugs hide best: skeleton stubs, structural reviews, and docs-checks each verify a specific surface; none substitute for "actually run the thing end-to-end."

**Multi-stage plan corollary.** For a plan with α / β / β.5 / γ / δ / ε waves, β.5 (the e2e gate) is **more valuable than δ (the consumer-side test) for catching producer-side bugs** — schedule the e2e gate as early as the producer can compile, even with a partial-AC fixture form. The full integration test downstream is for the consumer surface; the early e2e gate is for the producer surface, and the producer surface is the bug-rich one.

## 8. Sacrificial Warmup Probe for Environmental Cold-Boot

When running a tool-test suite against a freshly-spawned MCP server (or any process subject to first-fork JIT, lazy imports, or startup-state initialization), **include a sacrificial first call whose result is intentionally discarded**. The first-position probe is not graded — it exists solely to absorb cold-boot artifacts that would otherwise pollute the first real measurement.

Without the warmup probe, a test suite that grades the first call conflates two distinct failure modes: "the capability is broken" vs. "the process was still warming up." The distinction matters because the remediation is different: a broken capability needs a fix; a warmup artifact needs a re-run after the process is warm, or a formal warmup step in the test setup.

Pattern (project-rag-ue-addon): emit probe call → discard result → emit a summary-bucket classifier that distinguishes `cold_boot_warm` from `real_failure` before entering the graded run. The classifier is the signal; the discarded probe is the enabling infrastructure. Apply to any test harness that spins up a server fresh for each suite run.

## 9. Dogfood as a Distinct Review Surface

Dogfood is structurally distinct from plan-review and post-implementation code-review — not a substitute for either, and not subsumed by either.

- **Plan-review** catches architecture defects against a written body.
- **Code-review** catches diff-level defects against a frozen change.
- **Dogfood** catches runtime defects against the operator's live environment.

The three lenses find progressively different defect classes. A clean plan-review and a clean code-review do NOT constitute a passed dogfood. The defects each surface are different in kind, not in severity.

**Empirical evidence (pynvml probe):** A multi-interpretation pynvml probe shipped through three review cycles, plan-review, and code-review with zero findings. Dogfood found a probe-startup crash on the first real-environment run. No static review surface could have caught it — the failure was a runtime-environment interaction invisible to the review lens.

**Rule:** Any code that runs against the operator's live environment — doctor probes, installer scripts, MCP servers, CLI helpers, hook scripts — MUST pass a dogfood pass before declaring done. The dogfood gate is not optional after review; it is structurally additive to review.

**Dogfood-as-review-floor vs. dogfood-as-feature-validation.** These are distinct framings. Even when a feature works as designed (correct behavior for happy-path inputs), the dogfood pass catches runtime-environment defects that no static review can reach: wrong process start-up order, unavailable system resource, environment-specific import failure, cold-boot timing bug. The review-floor framing applies to ALL operator-facing code, not just new features under design validation.

---

## 10. Dogfood Timing for Runbook / Command-Surface Edits — Pre-Review, Not Just Post-Review

§9 establishes dogfood as a review-floor that runs before declaring done. For one class of artifact — **runbook / command-surface `.md` edits** (install/doctor runbooks, CLI-invocation docs, anything an agent executes by walking a command graph) — the dogfood pass is most valuable *before* the named-reviewer dispatch, not after.

Review lenses cover *what the artifact says*; dogfood covers *what happens when an agent walks the artifact's command graph in a real environment*. The leaf-trigger workstream made the distinction concrete: the Director of Engineering (DoE-altitude), code-reviewer (Sonnet, post-integration), plan-coverage, and prior-art pre-flights ALL approved. A dogfood pass then caught two operational bugs no lens surfaced: (i) the runbook probed a `--help` surface that didn't exist (the host ships a direct python script, intentionally not a console-script); (ii) a `python3` literal that fails on Windows Git-Bash where only `python` is on PATH. Both are invisible to a reviewer reading partition / gate-matrix correctness; they only surface when an agent executes the command graph in a real shell.

**Rule:** for runbook `.md` edits to install/doctor command surfaces, slot a dogfood pass BETWEEN Wave 1 (drafting) and named-reviewer dispatch. Cheap shape: spawn a Sonnet agent with the runbook, have it execute the read-paths (chain-presence reads, CLI probes, env-var resolution) against the local environment and report exit codes + stderr — no full live-install needed. This catches the "the runbook says X but X doesn't work on this OS" class before the named reviewer's time is spent on architecture. Review caught the architecture bug; dogfood caught the operational bugs — complementary, not substitutional.

---

## 11. Dogfood the Template Surface, Not the Inner Script

**Dogfood the command/invocation TEMPLATE, not just the underlying script — the wiring between them is exactly where the template-only bug hides.**

A `--narrow` dogfood that ran `probe_triage.py` with a literal path passed cleanly — but the `doctor.md` template used an undefined `${REPO_ROOT}` variable; only the parallel code-review caught the broken keystone path. The inner script worked; the template that users actually invoke was broken.

**How to apply:** dogfood the actual invocation surface (the command, skill, or template a user or agent triggers), not the inner script in isolation. "The script works when I call it directly" is not evidence the wired invocation surface works. Source: project-rag. [universal]

## 12. Consumer-Posture Bypass Discipline — Evidence Continuation, Not Bug-Fixing

When dogfood runs against an upstream capability from a downstream consumer posture (e.g., a sibling repo exercising a freshly-cut producer release), the EM is operating under a **consumer-only contract**: the producer's install path, CLI, and sidecars are themselves under test. Source-tree edits to the producer dependency are not in-scope; they would silently launder a bug-find into a working session and destroy the very evidence the dogfood exists to collect.

The operative rule: **bypasses (move-aside, kill-process, retry-without-flag) are allowed only to enable continued evidence collection, never to fix the bug.** Local patches to the producer dependency tree are forbidden. If a teammate's in-tree fix appears on disk mid-session, surface it as a finding (the producer just shipped a silent partial fix) rather than silently riding on it — the report is the deliverable, and silent use of an unannounced fix corrupts the report.

Three concrete shapes from the example-sim-repo shakedown against project-rag v0.5.x, each a deliberate refusal to fix forward in-session:

- **"Manually `pip install -e` instead of fixing the broken update script."** The broken update path IS the bug being characterized; rerouting around it via direct pip-install preserves the failure evidence and lets the run continue. Fixing the update script in this session would erase the finding.
- **"Bypass the canary by moving the baseline JSON aside, not by patching cli.py."** The bypass is a filesystem mv that the producer cannot mistake for a code fix; cli.py stays unmodified, the canary stays falsifiable on the next clean run.
- **"Do NOT apply Mode A bypass to populate the BP tables."** When the bug surfaces as "the table is empty," the empty graph state IS the evidence. Populating it via a workaround invalidates downstream observations about why it was empty.

**Why this lives in dogfood doctrine, not in producer testing doctrine.** A producer-side dogfood (project-rag self-dogfood) and a consumer-side dogfood (example-sim-repo against project-rag) catch different bug classes — and run under different fix-authority rules. Consumer-side runs that mutate the producer source tree are not dogfood; they are a producer patch wearing a dogfood costume. The contract that distinguishes the two is the source-tree boundary, and it is the EM's job to hold it.

**When the bypass discipline ends.** If the producer-side fix can be authored *in this session under producer authority* (the run started as a self-dogfood, or PM authorizes a posture switch to producer-side), the discipline relaxes and §2 fix-through applies. The boundary is authority, not appetite.

Source: example-sim-repo → project-rag v0.5.x shakedown (`tasks/dogfood-prior-art/example-sim-repo-shakedown-report.md` § 3). [universal]

## 13. Bug-Revealing-Bug Cascade — N-Iteration Is the Normal Shape

A dogfood pass that surfaces *one* bug, fixes it, and exits is rare. The structurally common shape is a **cascade**: each fix unblocks the next layer of execution, which surfaces the next bug, which was previously masked by the first failure.

The agentic-install-hardening run (the canonical fix-through example from §6) ran this exact shape:
W3.3 fix → W5 probe expansion (40+ legacy remediations) → W6 status-writer fix → W7 watchdog fix → Probe 9 FAIL→PASS.
Three distinct bugs in strict sequence, each invisible until its predecessor cleared.

**Why this matters for loop design.** A single-pass "find all the bugs" framing guarantees the deepest bugs stay hidden, because the first failure short-circuits the execution path before the second failure's site is even reached. Static analysis cannot substitute: the masked failures are by construction not reachable until the earlier failures clear at runtime. The only way to surface the cascade is to fix in-iteration and re-run.

**Operative rule.** The `/dogfood` skill's pass-N modes.json artifact is built around this premise: each iteration is a fresh observation, and convergence is judged by whether the *next* iteration adds nothing new — not by whether the *first* iteration was clean. Operators who treat the first non-empty modes.json as a session-completion signal (file the contents, exit) are running discovery, not dogfood (see §5).

**Where this interacts with switch-gears (§4).** A cascade does NOT trigger switch-gears merely by being multi-iteration. The switch-gears signal is *un-changed* modes.json from pass N to pass N+1, or ≥3–4 distinct concurrent tuples — i.e., the cascade has stalled or fanned out beyond a single fix-cone. A healthy cascade looks like the agentic-install run: one new mode per iteration, converging to empty. An unhealthy cascade looks like four orthogonal modes co-present in one pass. Read the modes.json shape, not just the count.

Source: agentic-install dogfood (`tasks/dogfood-prior-art/example-game-repo-insights-report.md` § 2–4). [universal]

## 14. Agent-Facing Tooling Must Activate in Its Own Dev Repo

**Agent-facing tooling we ship MUST work in our own dev repo — guards that exclude the shipping repo are wrong by construction.**

When the plugin ships an LSP, MCP, slash-command, or hook for the agent, that tooling must activate IN THE ADDON'S OWN CHECKOUT — not only on a downstream consumer with a canonical project file at root. The addon repo carries the same shape of code the tool exists to serve and the agent reads/edits it daily; refusing to activate here breaks the dogfood loop.

**Activation guard discipline:** when designing workspace/scope detection, list every place the tooling should activate; the shipping repo is always on the list. Acceptable widenings: detect any `Source/<Module>/*.Build.cs`, detect any `*.uproject` anywhere in tree, detect UE-specific macros in headers (UCLASS/UFUNCTION/UE_API). Default-on with no guard beats default-off when in doubt — false-attach is silent noise; false-non-attach kills the dogfood loop.

**Sister rule — consumer-facing infra is for consumers:** the "must work in our dev repo" principle does NOT apply when a piece of tooling exists to serve downstream users (LSP for consumer UE projects, MCP servers for consumer agents). In that case, the activation/attach rules should match what THE CONSUMER would have on disk, not what we happen to have in our addon repo. False-attach to our own dev repo for consumer-posture tooling solves the wrong problem and may make verification look successful while the real consumer flow is unverified.

Convergence with install-surface completeness doctrine: "works on a fresh-machine clean-install" must include "works in the shipping repo on this machine."

*Source: ue-addon (ue-aware-lsp restart-test pickup; PM correction before writing a `.uproject`-at-workspace-root activation guard).* [universal]

## 15. Agent-Facing Deliverable Verification Is the EM's Job, Not the PM's

**Agent-facing tooling deliverables are FOR THE AGENT — verification is "does it work for me in this session", not "PM opens X to confirm".**

When the deliverable targets the agent's own runtime (LSP, MCP tool, slash command, hook), the closing test is the EM's to run — invoke the tool, spawn the server, exchange the protocol, observe the result. Punting verification to the PM when the PM is sitting in the same session is a failure mode.

**How to apply:** any handoff/closing note for agent-facing tooling ends with an EM-side acceptance check, not a PM-side one. If the only test is "user opens X and looks at Y", the closing is incomplete — design an agent-side probe instead (LSP-tool invocation, MCP echo, slash-command response capture). The PM's role is product decisions, not QA-clicker.

*Source: ue-addon (PM correction twice: "Claude, I'm not going to open the .uproject — this is for you"; "CC is already open, why would I need to open CC").* [universal]

## 16. Dogfood by Invoking — Doc-Comment "Exempt" Does Not Prove the Dispatch Gate Honors It

**Dogfood a just-shipped discovery/query tool by actually INVOKING it before declaring awareness work done — a handler's documented "connection-exempt" doc-comment does NOT prove the dispatch gate honors it.**

After shipping search_tools awareness (SessionStart banner + agent frontmatter + orchestrator framing), a dogfood audit agent calling `search_tools` hit "Unreal Engine not connected" on every call: the `tool-registry.ts` top-level connection gate never exempted it, despite the handler being documented connection-exempt and reading only the static catalog — so the feature was broken for its PRIMARY use (pre-connection / headless discovery).

**How to apply:**
1. Before planning a new test/SSOT/coverage-invariant, grep for an existing one — prior-art-checker is the mechanism.
2. A "connection-exempt" / "bypasses X" doc-comment on a handler does not prove the DISPATCH path exempts it — verify the actual gate.
3. Dogfood by invoking the shipped tool end-to-end, not just wiring awareness prose to it.

Sister to §9 (Dogfood as a Distinct Review Surface) and "existence ≠ fit".

*Source: example-game-repo (search_tools dispatch-gate not honoring handler's connection-exempt doc).* [universal]

## 17. A Dogfood Harness Exercising a Config-Mutating Tool Must Isolate the Config ROOT — Isolating Only Its Input Is Insufficient

A dogfood/test harness that exercises a config-mutating tool (`--dry-run`, `--preview`, self-heal, a settings regenerator) MUST isolate the config **ROOT** — point `HOME`/`CLAUDE_HOME`/the tool's config-root at a sandbox — AND assert the live file is **byte-unchanged** after the run. Isolating only the tool's *input* (pointing its source at a sandbox) is not enough: if the tool writes to the live target, the harness silently infects the live config.

This has a producer-side twin the harness cannot compensate for: **any `--dry-run`/preview/self-heal mode that regenerates a config file MUST write to a temp (`mktemp`, trap-cleaned) and never mutate the live target.** A dry-run that regenerates against the live file before branching into its dry-run path has already done the damage by the time it decides not to.

**Empirical basis.** A launch wrapper's `--dry-run` ran its `settings.json` regenerator against the live `~/.claude/settings.json` *before* the dry-run branch; a dogfood harness that pointed the wrapper's source at a sandbox but did NOT isolate its write target baked 32 sandbox hook paths into the live config. When the sandbox was `rm`'d, every event's hooks fired against a deleted path — a live "infection" spraying errors across SessionStart/Stop/PostToolUse/PreToolUse. Two independent fixes were required: temp-write in the tool, config-root isolation + byte-unchanged assertion in the harness. [universal]

## 18. Dogfood a Doctrine Rewrite With a Fresh COLD Read, Not the Author

§10 dogfoods runbook/command-surface `.md` edits by having an agent *walk the command graph*. A sibling case: when a workstream **retires a mechanical artifact and relocates its discipline onto prose doctrine** (a ledger, a checklist, a script replaced by "the wiki now says to do X"), dogfood the rewrite with a **fresh agent reading the rewritten doctrine COLD** — as if executing it, with no memory of the prior mechanical form. The author's confirmation bias fills gaps the cold reader cannot, so the author re-reading their own rewrite reliably misses the ambiguities a first-time executor hits.

**Empirical basis.** A ledger-retirement dogfood — relocating the ledger's enforcement onto prose — had a fresh cold reader surface a real DEC-1a serial-chain-of-single-chunk-dispatches gap that the EM's own execution had already silently hit; it closed with one clarifying sentence. The author had not noticed it because they carried the retired artifact's discipline in their head. [universal]

## Cross-References

- **`/dogfood` skill** — `coordinator/skills/dogfood/SKILL.md` — the full operational procedure: three-tier gate (narrow/broad/shakedown), pre-flight gates (idempotency, machine-parseable progress, framing audit, coverage matrix), loop mechanics, switch-gears protocol, convergence criteria, commit doctrine, flight recorder directory structure.
- **Doctrine rule.** Dogfood new capabilities end-to-end via `/dogfood` before declaring stable. Binary outcome — converge or switch gears; no file-and-defer. (Formerly stated in `coordinator/CLAUDE.md` § Self-Improvement Loop; relocated here as part of that file's retirement — see `docs/plans/2026-07-27-doctrine-delivery-by-audience-and-hook.md` C3.)
- **`/learn-lessons` skill** — `coordinator/skills/learn-lessons/SKILL.md` — the upstream step; surfaces patterns that need dogfooding before they can be declared stable.
