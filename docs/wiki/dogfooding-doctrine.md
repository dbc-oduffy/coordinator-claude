---
kind: wiki
title: Dogfooding Doctrine — Fix-Through Validation of New Capabilities
status: active
created: 2026-05-07
last_updated: 2026-05-07
sources:
  - coordinator/skills/dogfood/SKILL.md
  - coordinator/CLAUDE.md § Self-Improvement Loop
tags: [dogfood, validation, fix-through, lesson-capture]
---

# Dogfooding Doctrine

> Spec backlink: `coordinator/CLAUDE.md` § Self-Improvement Loop — "Dogfooding new capabilities is the loop's first validation pass."

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

The forbidden middle ground is **file-and-defer**: the dogfood run surfaces a bug, the bug gets logged to `tasks/bug-backlog.md` or a note in the handoff, and the session moves on. This pattern means:

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

The 2026-05-07 agentic-install-hardening dogfood smoke is the canonical example of fix-through behavior.

Three real bugs surfaced and shipped in the same session:

- **W6 (`e35c6551`):** `install_status_writer` did not accept `status=skip` via `phase_end`. This caused phases that legitimately produced no work to emit no signal, leaving the watchdog and probe consumers without confirmation that the phase ran. Fixed forward.
- **W7 (`ab951c2a`):** Watchdog autostart relied solely on Task Scheduler, which is unavailable on locked-down user profiles. The fix added a Startup-shortcut fallback and added unconditional immediate-launch at install time, closing a race window where the watchdog was not running between install and the first scheduler trigger.
- **W8 (`f7f6c552`):** Setup honesty — phase status accuracy and summary truth-telling. The setup script reported phases as complete when their observable output (status file, probe state) hadn't confirmed it.

The convergence signal was concrete: **Probe 9 status mtime advanced from FAIL to PASS in 0.9 seconds** after W7 landed. That transition was the observable that proved the capability worked end-to-end.

Universal lesson captured from this run: **"Dogfood means fix-through, not file-and-defer."** No bug from this run was deferred to `tasks/bug-backlog.md`. All three were fixed in the same session, on the same branch, with smoke evidence in the commit message.

Canonical archived plan: `archive/specs/2026-05-06-agentic-install-hardening.md`.

---

## 7. E2E Gate Timing — Schedule as Early as the Producer Can Compile

End-to-end execution gates catch real bugs that unit tests + structural verification miss. The 2026-05-13 Stream-J β.5 dogfood surfaced **five distinct bugs in one session**, all in code that had passed unit tests + structural review + docs-check:

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

Pattern (2026-05-16 project-rag-ue-addon): emit probe call → discard result → emit a summary-bucket classifier that distinguishes `cold_boot_warm` from `real_failure` before entering the graded run. The classifier is the signal; the discarded probe is the enabling infrastructure. Apply to any test harness that spins up a server fresh for each suite run.

## 9. Dogfood as a Distinct Review Surface

Dogfood is structurally distinct from plan-review and post-implementation code-review — not a substitute for either, and not subsumed by either.

- **Plan-review** catches architecture defects against a written body.
- **Code-review** catches diff-level defects against a frozen change.
- **Dogfood** catches runtime defects against the operator's live environment.

The three lenses find progressively different defect classes. A clean plan-review and a clean code-review do NOT constitute a passed dogfood. The defects each surface are different in kind, not in severity.

**Empirical evidence (2026-05-18 pynvml probe):** A multi-interpretation pynvml probe shipped through three review cycles, plan-review, and code-review with zero findings. Dogfood found a probe-startup crash on the first real-environment run. No static review surface could have caught it — the failure was a runtime-environment interaction invisible to the review lens.

**Rule:** Any code that runs against the operator's live environment — doctor probes, installer scripts, MCP servers, CLI helpers, hook scripts — MUST pass a dogfood pass before declaring done. The dogfood gate is not optional after review; it is structurally additive to review.

**Dogfood-as-review-floor vs. dogfood-as-feature-validation.** These are distinct framings. Even when a feature works as designed (correct behavior for happy-path inputs), the dogfood pass catches runtime-environment defects that no static review can reach: wrong process start-up order, unavailable system resource, environment-specific import failure, cold-boot timing bug. The review-floor framing applies to ALL operator-facing code, not just new features under design validation.

---

## 10. Dogfood Timing for Runbook / Command-Surface Edits — Pre-Review, Not Just Post-Review

§9 establishes dogfood as a review-floor that runs before declaring done. For one class of artifact — **runbook / command-surface `.md` edits** (install/doctor runbooks, CLI-invocation docs, anything an agent executes by walking a command graph) — the dogfood pass is most valuable *before* the named-reviewer dispatch, not after.

Review lenses cover *what the artifact says*; dogfood covers *what happens when an agent walks the artifact's command graph in a real environment*. The 2026-05-23 leaf-trigger workstream made the distinction concrete: Zolí (DoE-altitude), code-reviewer (Sonnet, post-integration), plan-coverage, and prior-art pre-flights ALL approved. A dogfood pass then caught two operational bugs no lens surfaced: (i) the runbook probed a `--help` surface that didn't exist (the host ships a direct python script, intentionally not a console-script); (ii) a `python3` literal that fails on Windows Git-Bash where only `python` is on PATH. Both are invisible to a reviewer reading partition / gate-matrix correctness; they only surface when an agent executes the command graph in a real shell.

**Rule:** for runbook `.md` edits to install/doctor command surfaces, slot a dogfood pass BETWEEN Wave 1 (drafting) and named-reviewer dispatch. Cheap shape: spawn a Sonnet agent with the runbook, have it execute the read-paths (chain-presence reads, CLI probes, env-var resolution) against the local environment and report exit codes + stderr — no full live-install needed. This catches the "the runbook says X but X doesn't work on this OS" class before the named reviewer's time is spent on architecture. Review caught the architecture bug; dogfood caught the operational bugs — complementary, not substitutional.

---

## 11. Dogfood the Template Surface, Not the Inner Script

**Dogfood the command/invocation TEMPLATE, not just the underlying script — the wiring between them is exactly where the template-only bug hides.**

A `--narrow` dogfood that ran `probe_triage.py` with a literal path passed cleanly — but the `doctor.md` template used an undefined `${REPO_ROOT}` variable; only the parallel code-review caught the broken keystone path. The inner script worked; the template that users actually invoke was broken.

**How to apply:** dogfood the actual invocation surface (the command, skill, or template a user or agent triggers), not the inner script in isolation. "The script works when I call it directly" is not evidence the wired invocation surface works. Source: 2026-05-27 project-rag. [universal]

## Cross-References

- **`/dogfood` skill** — `coordinator/skills/dogfood/SKILL.md` — the full operational procedure: three-tier gate (narrow/broad/shakedown), pre-flight gates (idempotency, machine-parseable progress, framing audit, coverage matrix), loop mechanics, switch-gears protocol, convergence criteria, commit doctrine, flight recorder directory structure.
- **Doctrine cite** — `coordinator/CLAUDE.md` § Self-Improvement Loop, line 169: *"Dogfooding new capabilities is the loop's first validation pass. Before a lesson-captured pattern is declared stable, the thing it produced should be exercised end-to-end via `/dogfood`. Binary outcome — converge or switch gears; no file-and-defer."*
- **`/learn-lessons` skill** — `coordinator/skills/learn-lessons/SKILL.md` — the upstream step; surfaces patterns that need dogfooding before they can be declared stable.
