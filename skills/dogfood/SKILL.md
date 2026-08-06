---
name: dogfood
description: "Fix-through loop — invoke a new thing, fix bugs until it works."
triggers:
  - /dogfood
  - dogfood <target>
  - run dogfood
  - smoke test and fix
  - self-dogfood
argument-hint: "<target> [--narrow|--broad|--shakedown]"
---

# /dogfood — Smoke-Driven Fix-Through Super-Skill

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
| `--narrow` | Single smoke surface — one install, one command, one happy-path sequence. "Does it work?" | Tight. | Only when the surface explodes. |
| `--broad` | Multi-surface happy path. End-to-end flow across multiple commands/skills/agents. Auto-handoffs survive compaction. | Larger. | At budget halfway. |
| `--shakedown` | Comprehensive coverage matrix. Every tool/surface/path exercised once with realistic input. Requires a declared matrix (Gate 4). | Largest. | At budget halfway and on PM check-in pause. |

Shakedown is a *kind* of dogfood, not a separate activity. It composes inward: a shakedown of a multi-tool surface is a broad dogfood across each tool's narrow surface with a coverage-matrix overlay.

## Gate 1 — Idempotent Re-Run

The target must be safely re-invocable across iterations. When the target mutates state such that a second invocation diverges from the first for non-bug reasons, fix idempotency first — this is empirical judgment about the target, not something an assembler reader can determine from an artifact. The fix is in-cone: idempotency is a property of the thing being dogfooded, not an external concern.

## Gate 2 — Machine-Parseable Progress

The target must emit tagged stdout, exit codes, or a status file that the EM can diff iteration-to-iteration. Naked-stdout streams are forbidden — write a capture-and-classify wrapper as the first deliverable when the target doesn't already produce machine-parseable output. Whether the existing output actually parses cleanly is an empirical call the EM makes by trying it, not a static check.

## Gate 3 — Framing Audit (Runs First, Every Invocation)

When the dogfood session is opened from a handoff or carries inherited scope language ("smoke verification only," "no scope expansion," "out of scope: refactor"), the EM surfaces the language to PM and forces a decision:

> "This phrase invites file-and-defer when bugs surface. Confirm dogfood fix-through posture, not verification-only."

Hardcoded fix-through is the default. PM can override only with explicit reasoning. This gate runs as the first action of every `/dogfood` invocation, including autonomous runs. Skipping it is not permitted.

## Gate 4 — Coverage Matrix Declared (`--shakedown` only)

PM declares the coverage matrix at invocation — every tool/surface/path to be exercised, with realistic input specified. Matrix is persisted to `tasks/dogfood-<target>-<date>/coverage-matrix.md` at session start and checked off iteration-to-iteration.

**Without a declared matrix, `--shakedown` degrades to `--broad`**, and the EM surfaces the choice to PM before entering the loop. This gate exists because shakedown's value claim ("every surface exercised") is unfalsifiable without a prior declaration of what "every surface" means.

**Before entering the loop: if any of Gates 1-4 fails its precondition** (Gate 4 applies to `--shakedown` only), the first deliverable of the session is to satisfy it, then enter the loop below.

## Loop

Invoke target → observe across every channel → classify each observation (Cone Classification, below) → act → write `pass-<N>-modes.json` → re-invoke → check for convergence, switch-gears, or PM stop.

### Bug-Revealing-Bug Cascade

The bug-revealing-bug cascade is the normal shape. Each fix uncovers the next layer; single-pass "find all bugs" mode is forbidden because the deepest bugs are invisible until shallower ones clear. Expect multiple passes; each pass narrows the remaining surface.

### Cross-Channel Observation (Mandatory)

Observation does not stop at exit code — read every channel:

- Exit code vs stderr severity
- Status-file claim vs downstream consumer behavior
- "Complete" signal vs phase-N failure
- "PASS" status vs warning text on stderr

When a contradiction surfaces across channels (success exit + warning stderr; status file says ready + no readiness probe firing), the fix is **structural** — capture in-process truth at decision time, emit one consistent signal — not patching the lying channel. This bug class is invisible to schema tests; only cross-channel reading catches it.

### Cone Classification — Mandatory Per Finding

Every observation must be explicitly classified before acting, logged in the flight recorder. This is the skill's actual purpose — deciding what's in-scope for a fix-through loop is a judgment call every time, not a lookup:

**In-cone — fix-now (default).** Mechanical fixes (validator gaps, missing fallbacks, false-success exits, off-by-one, missing flag handling, idempotency gaps, the skill/script/pipeline body itself) are in-scope by definition because the dogfood IS the test. The default question is "is there a real reason this isn't fix-now?" not "do I have permission to fix this?" In-cone fix surface includes production code; hooks, scripts, `bin/` helpers; the skill body / agent prompt / pipeline being dogfooded (yes — this is the whole point when dogfooding a new skill); and doctrine/wiki/CLAUDE.md the target depends on, when the smoke trips it.

**Out-of-cone — switch-gears.** The bug requires architectural rework that the plan author should re-do: a fix would reverse a load-bearing structural choice in the thing being dogfooded. Loop ends on PM confirm.

**Surface-and-skip.** Reserved for bugs requiring PM-level product decisions, externalities (PRs, signing, network), or genuinely-not-this-loop scope. The rare exception, not the conservative move. Required structured entry: `{ "category": "pm-product | externality | architectural-rework", "evidence": "<link-or-pointer-to-rationale>" }`, landing in `tasks/dogfood-<target>-<date>/surface-and-skip.md` — never `state/bug-backlog/` (that would blur the boundary with `/bug-blitz`, which works backlog, and undermine dogfood's does-not-file-remainder rule). Silent skips are forbidden.

**Skip-ratio threshold.** Skip-ratio over 40% of the session, or more than two consecutive skips without an interleaved fix-now, means the session has lost fix-through character — surface "is this dogfood the wrong shape?" to PM.

### Per-Iteration Mode Artifact (Mandatory)

After each pass, write `tasks/dogfood-<target>-<date>/pass-<N>-modes.json` — a JSON list of `{component, error-class}` tuples, one per distinct failure mode observed:

```json
[
  { "component": "branch-cut helper", "error-class": "branch-cut-failure" },
  { "component": "coordinator-safe-commit",   "error-class": "scope-overlap-false-positive" }
]
```

Classifying a failure into a tuple is judgment; counting tuples and comparing them to the prior pass is not. `backlog-grind-assemble brief dogfood` reads the current `pass-<N>-modes.json`, against the prior pass where one exists, and returns the tuple count and a stuck flag (same tuples, unchanged, across passes) — that computed pair is the mechanical half of the Switch-Gears signal below; whether to act on it stays an EM proposal, PM confirm.

Each iteration also appends a tee'd log to `tasks/dogfood-<target>-<date>/pass-<N>.log` so iterations are diffable and compaction doesn't lose the trail. TaskList is the cross-iteration flight recorder.

### Commit Doctrine — Tier-Dependent

Parallel executors that each call `coordinator-safe-commit` produce concurrent-commit absorption and scope sweep — non-negotiable.

**`--narrow` (no fanout, single-committer):** the EM commits each fix directly on the daily branch (lessons.md:207; `docs/wiki/scoped-safety-commits.md § Current Doctrine`) via `backlog-grind-assemble apply dogfood`, which emits the `stage_and_commit` directive at `commit-per-item` granularity — one commit per fix, subject naming the fix, smoke evidence (the iteration's stdout/exit/probe transition that proves the fix landed) in the body. Smoke-evidence-in-commit is not optional.

**`--broad` and `--shakedown` (fanout-capable, autonomous):** executors and fix agents are edit-and-report only — no commit, no `coordinator-safe-commit` invocation of their own; helper invocation is forbidden in executor scope under these tiers. The EM serializes at wave gates via `apply dogfood` at `commit-per-wave` granularity — one commit per wave, gathered from DONE reports, subject naming the wave, smoke evidence in the body.

**`--expected-branch`** applies only on `--narrow`-mode executor dispatches that commit. Under `--broad` and `--shakedown`, executors never commit, so the flag is moot.

### Per-Bug Serial Executors, Not Per-File Parallel

Fixes that span languages/files for one bug must ship as one unit; splitting parallelizes the executor at the cost of the semantic guarantee that one bug gets one coherent fix.

## Switch-Gears Protocol

Switch-gears is a judgment call informed by mechanical signals, never automatic.

**Well-grounded signals:**
- **Failure-mode shift / stuck-detection (computed).** `backlog-grind-assemble brief dogfood` reports the tuple count for the latest pass and whether it repeats the prior pass unchanged (§ Per-Iteration Mode Artifact). Roughly 3-4 distinct tuples in one pass, or an unchanged tuple across two passes, means the loop has shifted from "verify a fix" to "discover more bugs," or is stuck.
- **Same seam, different bugs (judgment).** Three or more distinct failures attributable to the same architectural shape decision means the shape is the bug — this is an EM read of the failure pattern, not a count the engine can produce.
- **Skip-ratio threshold breached** (§ Cone Classification).
- **Fix would reverse a load-bearing structural choice** in the thing being dogfooded — an architectural-shape judgment, made by the EM against the specific target, every time.

EM proposes switch-gears with reasoning; PM confirms. On switch-gears the loop ends — the session output is the replan ask, not a converged thing.

## Loop Exit — Three-Criterion Convergence

Loop ends when ALL THREE hold:

1. **Primary goal met** — the original "what does this thing do" succeeds end-to-end on the latest pass.
2. **No new in-cone bugs surfaced in the last iteration.** Out-of-cone surface-and-skip findings don't count against convergence. Auto-detect this and surface "ready to converge?" rather than running forever.
3. **PM signals stop** OR EM proposes converge and PM confirms.

**Alternative exits:**
- **Switch-gears** — EM proposes replan/refactor (signals above), PM confirms. Loop ends; output is the replan ask.
- **PM stop** — PM calls it for any reason; EM emits a status summary listing fixes shipped, surface-and-skip findings, and the open observation that was about to be addressed.

**NOT an exit path:**
- "Budget exhausted, file remainder to backlog." Budget exhaustion is itself a switch-gears signal — surface to PM, don't paper over with a backlog dump.
- "Zero new bugs surfaced this pass" alone — convergence needs criterion 1 (clean happy-path) AND criterion 2 (clean in-cone iteration), not just one quiet pass. Flakes mask a single quiet pass.

**PM is loop terminator, not loop driver.** Once `/dogfood` is authorized, the EM hardcodes autonomous fix-through posture. Mid-loop "should I continue?" prompts are anti-signal — they burn PM context on operational decisions the EM is empowered to make. PM intervenes to stop or to confirm switch-gears, not to re-authorize each pass.

## Flight Recorder Directory

All per-session artifacts land in `tasks/dogfood-<target>-<date>/`:

| File | Contents |
|------|----------|
| `pass-<N>.log` | Tee'd output from each invocation |
| `pass-<N>-modes.json` | Distinct `{component, error-class}` tuples (mandatory) |
| `surface-and-skip.md` | Structured skip entries with category + evidence |
| `coverage-matrix.md` | (`--shakedown` only) Declared matrix + check-off state |

Do NOT route surface-and-skip findings to `state/bug-backlog/`. If PM later decides an item belongs in the backlog, that is a deliberate hand-off, not automatic spillover.

## Autonomous-Mode Compatibility

`/dogfood --broad` and `--shakedown` are write-capable autonomous tiers. Under autonomous operation:

- Gate 3 (Framing Audit) is hardcoded as the first action — cannot be skipped.
- Auto-handoff at budget halfway and on PM check-in pause.
- Commit doctrine mirrors the tier-split (§ Commit Doctrine, above).
- Power-state cues ("late," "overnight," "tired") authorize urgency only — never hibernate or shutdown, never a destructive or externally-visible action outside what the fix itself requires.

## Composition With Existing Surface

| Sibling | Boundary |
|---------|----------|
| `/bug-blitz` | Works `state/bug-backlog/`. `/dogfood` does NOT file remainder there — if `/dogfood` exits via switch-gears, the output is a replan, not a backlog dump. |
| `/bug-sweep` | Searches the repo for latent bugs (repo-driven). `/dogfood` invokes a specific thing (invocation-driven). A sweep finds bugs that exist; a dogfood finds bugs that the new thing causes when used. |
| `coordinator:validate` | Static repo-state pre-flight. Appropriate before the first smoke pass and after the loop ends. Does not substitute for dynamic invocation. |
| `/workstream-complete` | `/dogfood` exit emits a workstream-complete-shaped summary (bugs surfaced + commits shipped + filed skips + verdict), but does not invoke `/workstream-complete`. PM may chain. |
| `/learn-lessons` | Surfaced doctrine drift is filed to `state/lessons/` for `/learn-lessons` triage — out-of-loop, by design. |

## Final Summary

**Report by exception.** Two lines always; everything else appears only when it is *not* clean. This is still an EM→PM reply and still owes the ≤200-word budget — a fixed block of all-clean status lines spends that budget on facts the PM can read off the commit or the flight-recorder, then gets measured as verbosity. Print what needs a reader, not what needs a checkbox.

```markdown
## Dogfood Session Complete

**Target:** <target> (tier: --narrow/--broad/--shakedown)
**Verdict:** <converged: thing works | switch-gears: replan ask | stopped: open observation was X>
```

Then append a line **only** if its condition holds:

| Line | Include only when |
|---|---|
| `**Bugs fixed this session:**` | F ≥ 1 — count plus a one-line characterization of what shipped |
| `**Surface-and-skip:**` | S ≥ 1 — count plus a one-line characterization |

**Negative-spec — these are gone, do not restore them.** `Outcome` is dropped — `Verdict` already states converged/switch-gears/stopped, so a separate Outcome line was a redundant restatement of the same fact. `Passes run` is dropped — a raw iteration count with no PM decision attached; the count is already in the flight-recorder's `pass-<N>.log`/`pass-<N>-modes.json` trail. `Tier` is dropped as its own line — folded into the `Target` line instead, since it's the invocation parameter the PM already declared, not new information. Per-fix commit SHAs and per-item surface-and-skip evidence pointers are dropped from both retained lines — the Stop hook's D2 detector fires on ≥2 file:line citations or absolute paths in an EM→PM reply independently of length, on the doctrine that verification detail belongs in the commit message and the artifact, not the reply; per-fix smoke evidence lives in the commit body (§ Commit Doctrine), and per-item category/evidence lives in `surface-and-skip.md`, which the field label already points to. A future reader must not re-add SHA lists or evidence pointers "for completeness" — that completeness belongs to the commit and the flight-recorder, not the PM reply.
