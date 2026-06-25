---
name: dogfood
description: "Smoke-driven fix-through loop — invoke a newly-built thing (skill, script, pipeline, install process) and fix bugs until it works or gets replanned. Binary outcome only: converge or switch gears."
description-budget: 250
triggers:
  - /dogfood
  - dogfood <target>
  - run dogfood
  - smoke test and fix
  - self-dogfood
argument-hint: "<target> [--narrow|--broad|--shakedown]"
---

# /dogfood — Smoke-Driven Fix-Through Super-Skill

<!-- spec backlink: archive/specs/2026-05/2026-05-07-dogfood-super-skill.md -->

Invoke a newly-built thing and exercise it until it works or gets replanned. **Dogfooding is binary — either fix it through or switch gears.** There is no third path: "log to backlog and keep going" is file-and-defer wearing a dogfood costume.

Distinct from siblings:
- **`/bug-blitz`** works a known backlog.
- **`/bug-sweep`** searches the repo for bugs.
- **`/dogfood`** invokes a new thing and exercises it until it works or gets replanned.

**Announce at start:** "Running `/dogfood <target>` — smoke-driven fix-through loop. Binary outcome: converge or switch gears."

## Activation — When to Invoke vs Not

**Invoke `/dogfood` when:**
- A new skill, command, script, or pipeline has been built and needs real-use validation.
- An install/setup process is new or significantly changed.
- A prior shakedown or smoke run revealed bugs that were deferred — now it's time to fix through.
- The PM explicitly authorizes a dogfood pass on a specific target.

**Do NOT invoke `/dogfood` when:**
- The target is already well-exercised in production — use `/bug-blitz` for known backlog items.
- You want to search the repo for latent bugs — use `/bug-sweep`.
- You want static pre-flight checks on repo state — use `coordinator:validate`.

**Self-dogfood-first default.** When the target is a thing built in repo X, the canonical first invocation is `/dogfood` *in repo X*. Cross-repo dogfood is a deliberate follow-up after self-dogfood converges, not a substitute. When invoked with a target that lives in a different repo, the first action is to surface: *"Self-dogfood-first default — confirm a self-dogfood pass was attempted in the producing repo before proceeding to cross-repo validation."* Require PM acknowledgment to continue.

## Three-Tier Gate

PM declares tier at invocation (`/dogfood <target> [--narrow|--broad|--shakedown]`). Default: `--narrow`.

| Tier | Scope | Budget | Mid-loop PM check |
|------|-------|--------|-------------------|
| `--narrow` | Single smoke surface — one install, one command, one happy-path sequence. "Does it work?" | Tight. | Only if surface explodes. |
| `--broad` | Multi-surface happy path. End-to-end flow across multiple commands/skills/agents. Auto-handoffs survive compaction. | Larger. | At budget halfway. |
| `--shakedown` | Comprehensive coverage matrix. Every tool/surface/path exercised once with realistic input. Requires declared matrix (see Pre-Flight Gate #4). | Largest. | At budget halfway and on PM check-in pause. |

Shakedown is a *kind* of dogfood, not a separate activity. It composes inward: a shakedown of a multi-tool surface is a broad dogfood across each tool's narrow surface with a coverage-matrix overlay.

## Pre-Flight Gates

Before entering the loop, four preconditions must hold (Gate 4 applies to `--shakedown` only). If any gate fails, the **first deliverable of the dogfood session is to satisfy the precondition**, then enter the loop.

### Gate 1 — Idempotent Re-Run

The target must be safely re-invocable across iterations. If the target mutates state in a way that makes pass 2 differ from pass 1 for non-bug reasons, fix idempotency first. The fix is in-cone: idempotency is a property of the thing being dogfooded, not an external concern.

### Gate 2 — Machine-Parseable Progress

The target must emit tagged stdout, exit codes, or a status file that the EM can diff iteration-to-iteration. Naked-stdout streams are forbidden — write a capture-and-classify wrapper as the first deliverable if the target doesn't already produce machine-parseable output.

### Gate 3 — Framing Audit (Hardcoded — Runs First, Every Invocation)

If the dogfood session is opened from a handoff or carries inherited scope language ("smoke verification only," "no scope expansion," "out of scope: refactor"), the EM **surfaces the language to PM and forces disambiguation:**

> "This phrase invites file-and-defer when bugs surface. Confirm dogfood fix-through posture, not verification-only."

Hardcoded fix-through is the default. PM can override only with explicit reasoning. This gate runs as the **first action of every `/dogfood` invocation**, including autonomous runs. Skipping it is not permitted.

### Gate 4 — Coverage Matrix Declared (`--shakedown` only)

PM declares the coverage matrix at invocation — every tool/surface/path to be exercised, with realistic input specified. Matrix is persisted to `tasks/dogfood-<target>-<date>/coverage-matrix.md` at session start and checked off iteration-to-iteration.

**Without a declared matrix, `--shakedown` degrades to `--broad`** and the EM surfaces the choice to PM before entering the loop. This gate exists because shakedown's value claim ("every surface exercised") is unfalsifiable without a prior declaration of what "every surface" means.

## Out-of-Scope Actions (Autonomous-Run Prohibition)

Out of scope for this run, no exceptions: `gh pr merge`, `gh pr create` against main, `git push origin main`, hibernate / shutdown / power-off, killing other processes, `--no-verify` / `--no-gpg-sign`. Do not propose; do not request authorization mid-run. Power-state cues ("late," "overnight," "tired") authorize urgency only — never hibernate or shutdown.

## Daily-Branch Discipline

**`/dogfood` is fail-closed-only** — it does NOT set `COORDINATOR_OVERRIDE_BRANCH=1` and does not run off the active workstream branch under any circumstance. No override mode. If the daily-branch hook blocks an operation, halt and surface to PM. Do not fight the hook.

## Loop

```
[Gate 3 — Framing audit. Always first.]

invoke target
  → observe (capture stdout/stderr/exit, file diffs, hook fires, cross-channel consistency)
  → for each observation, classify explicitly into ONE of:
      (a) in-cone, fix-now    → fix it on this branch, this session
      (b) out-of-cone, switch-gears → stop loop; surface to PM with replan ask
      (c) surface-and-skip    → genuinely out of scope (PM-product call,
                                externality, architectural rework). Surface
                                in flight-recorder; do NOT silently drop.
                                Defer is the rare exception, not the default.
      Silent skips are forbidden. Logging to a generic backlog is forbidden.
  → write pass-<N>-modes.json (mandatory — see below)
  → re-invoke target
  → loop check (see Loop Exit)
```

### Bug-Revealing-Bug Cascade

The bug-revealing-bug cascade is the normal shape. Each fix uncovers the next layer; single-pass "find all bugs" mode is forbidden because the deepest bugs are invisible until shallower ones clear. Expect multiple passes; each pass narrows the remaining surface.

### Cross-Channel Observation (Mandatory)

The observe step does not stop at exit code. Cross-channel observation is explicitly required:

- Exit code vs stderr severity
- Status-file claim vs downstream consumer behavior
- "Complete" signal vs phase-N failure
- "PASS" status vs warning text on stderr

When a contradiction surfaces across channels (success exit + warning stderr; status file says ready + no readiness probe firing), the fix is **structural** — capture in-process truth at decision time, emit one consistent signal — not patching the lying channel. This bug class is invisible to schema tests; only cross-channel reading catches it.

### Cone Classification — Mandatory Per Finding

Every observation must be explicitly classified before acting. Log each classification in the flight-recorder.

**In-cone — fix-now (default).** Mechanical fixes (validator gaps, missing fallbacks, false-success exits, off-by-one, missing flag handling, idempotency gaps, the skill/script/pipeline body itself) are in-scope by definition because the dogfood IS the test. The default question is "is there a real reason this isn't fix-now?" not "do I have permission to fix this?"

In-cone fix surface includes:
- Production code
- Hooks, scripts, `bin/` helpers
- The skill body / agent prompt / pipeline being dogfooded — **yes** (this is the whole point when dogfooding a new skill)
- Doctrine / wiki / CLAUDE.md the dogfood target depends on — yes, if the smoke trips it

**Out-of-cone — switch-gears.** When the bug requires architectural rework that the plan author should re-do. A fix would require reversing a load-bearing structural choice in the thing being dogfooded. Loop ends on PM confirm.

**Surface-and-skip.** Reserved for: bugs requiring PM-level product decisions, externalities (PRs, signing, network), or genuinely-not-this-loop scope. **Surface-and-skip is the rare exception, not the conservative move.**

Required structured entry format per skip:
```json
{ "category": "pm-product | externality | architectural-rework", "evidence": "<link-or-pointer-to-rationale>" }
```

Entries land in `tasks/dogfood-<target>-<date>/surface-and-skip.md`, NOT in `state/bug-backlog.md`. Routing surface-and-skip into the bug-backlog blurs the boundary with `/bug-blitz` (which works backlog) and undermines the "dogfood does not file remainder" rule.

**Skip-ratio threshold:** if skip-ratio exceeds **40% over the session**, OR **>2 consecutive skips occur without an interleaved fix-now**, the EM surfaces "is this dogfood the wrong shape?" to PM. These thresholds signal the session has lost fix-through character and should be re-evaluated against switch-gears.

### Per-Iteration Mode Artifact (Mandatory)

After each pass, the EM writes `tasks/dogfood-<target>-<date>/pass-<N>-modes.json` — a JSON list of `{component, error-class}` tuples, one per distinct failure mode observed. Example:

```json
[
  { "component": "block-off-daily-branch.sh", "error-class": "exit-code-mismatch" },
  { "component": "coordinator-safe-commit",   "error-class": "scope-overlap-false-positive" }
]
```

This file is the **mechanical switch-gears signal**:
- **≥3–4 distinct `{component, error-class}` tuples in a single pass** → switch-gears is warranted.
- **Same tuple appears unchanged from the prior pass** → loop is stuck; propose switch-gears.

EM no longer needs to judge subjectively — the JSON is the signal.

Each iteration also appends a tee'd log to `tasks/dogfood-<target>-<date>/pass-<N>.log` so iterations are diffable and compaction doesn't lose the trail. TaskList is the cross-iteration flight recorder.

### Commit Doctrine — Tier-Dependent

**Non-negotiable; learned from `/bug-blitz` Phase 3 remediation.** Parallel executors that each call `coordinator-safe-commit` produce concurrent-commit absorption and scope sweep.

**`--narrow` (no fanout, single-committer):** EM commits each fix directly via plain git on the daily branch (SC-DR-008, lessons.md:207) — `git add -- <explicit paths> && git commit -m "<subject>" -- <explicit paths>`. Each commit carries empirical smoke evidence in the message body — the iteration's stdout/exit/probe transition that proves the fix landed. Smoke-evidence-in-commit is not optional.

**`--broad` and `--shakedown` (fanout-capable, autonomous):** Executors and fix agents are **edit-and-report only — no commit, no `coordinator-safe-commit` invocation**. The EM serializes commits at wave gates using a single fused Bash call:
```bash
git reset && git add -- <explicit paths from DONE> && git commit -m "<subject>"
```
Helper invocation is forbidden in executor scope under these tiers. Each commit carries smoke evidence in the body.

**`--expected-branch`** applies only on `--narrow`-mode executor dispatches that commit. Under `--broad` and `--shakedown`, executors never commit, so the flag is moot.

### Per-Bug Serial Executors, Not Per-File Parallel

Fixes that span languages/files for one bug must ship as one unit; splitting parallelizes the executor at the cost of semantic guarantee.

## Switch-Gears Protocol

Switch-gears is a judgment call informed by mechanical signals.

**Well-grounded signals:**
- **Failure-mode shift threshold.** `pass-<N>-modes.json` contains ≥3–4 distinct `{component, error-class}` tuples. The loop has transitioned from "verify a fix" to "discover more bugs."
- **Same seam, different bugs.** ≥3 distinct failures attributable to the same architectural shape decision means the shape is the bug.
- **Stuck-detection.** Pass N+1 surfaces the same failure mode (same component, same error class) as pass N unchanged.
- **Skip-ratio threshold breached.** >40% session or >2 consecutive skips — the session may be the wrong shape.
- **Fix would reverse a load-bearing structural choice** in the thing being dogfooded.

EM proposes switch-gears with reasoning; PM confirms. On switch-gears the loop ends — the dogfood session output is the replan ask, not a converged thing.

## Loop Exit — Three-Criterion Convergence

Loop ends when ALL THREE of:

1. **Primary goal met** — the original "what does this thing do" succeeds end-to-end on the latest pass.
2. **No new in-cone bugs surfaced in the last iteration.** Out-of-cone surface-and-skip findings don't count against convergence. Auto-detect this and surface "ready to converge?" rather than running forever.
3. **PM signals stop** OR EM proposes converge and PM confirms.

**Alternative exits:**

- **Switch-gears** — EM proposes replan/refactor (signals above), PM confirms. Loop ends; output is the replan ask.
- **PM stop** — PM calls it for any reason; EM emits a status summary listing fixes shipped, surface-and-skip findings, and the open observation that was about to be addressed.

**NOT an exit path:**
- "Budget exhausted, file remainder to backlog." Budget exhaustion is itself a switch-gears signal — surface to PM, don't paper over with a backlog dump.
- "Zero new bugs surfaced this pass" alone — convergence requires criterion 1 (clean happy-path) AND criterion 2 (clean in-cone iteration), not just one quiet pass. Flakes mask single-pass quiet.

**PM is loop terminator, not loop driver.** Once `/dogfood` is authorized, the EM hardcodes autonomous fix-through posture. Mid-loop "should I continue?" prompts are anti-signal — they burn PM context on operational decisions the EM is empowered to make. PM intervenes to stop or to confirm switch-gears, not to re-authorize each pass.

## Flight Recorder Directory

All per-session artifacts land in `tasks/dogfood-<target>-<date>/`:

| File | Contents |
|------|----------|
| `pass-<N>.log` | Tee'd output from each invocation |
| `pass-<N>-modes.json` | Distinct `{component, error-class}` tuples (mandatory) |
| `surface-and-skip.md` | Structured skip entries with category+evidence |
| `coverage-matrix.md` | (`--shakedown` only) Declared matrix + check-off state |

Do NOT route surface-and-skip findings to `state/bug-backlog.md`. If PM later decides any item belongs in the backlog, that is a deliberate hand-off, not automatic spillover.

## Autonomous-Mode Compatibility

`/dogfood --broad` and `--shakedown` are write-capable autonomous tiers. Under autonomous operation:

- **Framing audit (Gate 3) is hardcoded as the first action** — cannot be skipped in autonomous mode.
- Auto-handoff at budget halfway and on PM check-in pause.
- **Daily-branch discipline preserved** — no override; if the daily is blocked the loop halts and surfaces to PM.
- **Commit doctrine mirrors the tier-split** (see Loop § Commit Doctrine above).
- **Destructive-action prohibition applies in full** (see Out-of-Scope Actions above).
- Power-state cues ("late," "overnight," "tired") authorize urgency only — **never** hibernate or shutdown.

## Composition With Existing Surface

| Sibling | Boundary |
|---------|----------|
| `/bug-blitz` | Works `state/bug-backlog.md`. `/dogfood` does NOT file remainder there — if `/dogfood` exits via switch-gears, the output is a replan, not a backlog dump. |
| `/bug-sweep` | Searches the repo for latent bugs (repo-driven). `/dogfood` invokes a specific thing (invocation-driven). A sweep finds bugs that exist; a dogfood finds bugs that the new thing causes when used. |
| `coordinator:validate` | Static repo-state pre-flight. Appropriate before the first smoke pass and after the loop ends. Does not substitute for dynamic invocation. |
| `/workstream-complete` | `/dogfood` exit emits a workstream-complete-shaped summary (bugs surfaced + commits shipped + filed skips + verdict), but does not invoke `/workstream-complete`. PM may chain. |
| `/learn-lessons` | Surfaced doctrine drift is filed to `state/lessons.md` for `/learn-lessons` triage — out-of-loop, by design. |

## Final Status Report Format

```markdown
## Dogfood Session Complete

**Target:** <target> | **Tier:** --narrow/--broad/--shakedown
**Outcome:** converged | switch-gears | pm-stopped

**Passes run:** N
**Bugs fixed this session:** F items
- [list with commit SHAs and one-line smoke evidence per fix]

**Surface-and-skip (in session flight-recorder):** S items
- [list with category + evidence pointer]

**Verdict:** <converged: thing works | switch-gears: replan ask | stopped: open observation was X>
```
