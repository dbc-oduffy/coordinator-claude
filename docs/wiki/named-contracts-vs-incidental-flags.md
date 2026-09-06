---
title: Named Contracts vs. Incidental Flags
status: active
kind: doctrine-wiki
created: 2026-05-18
---

# Named Contracts vs. Incidental Flags

> A flag that disables the behavior you want only because of a shared code path is not configuration — it's an exploited implementation detail.

## Lesson Surface

A workaround set a flag whose name and documented purpose were unrelated to the behavior being suppressed. It worked because purpose-A's branch and behavior-B's branch shared a code path. The next maintainer rewired that path while preserving the documented contract, and the workaround silently broke.

## The Failure Shape

- A subsystem exposes `bDisableEditorTickPreview` — documented as "skip preview ticks in PIE."
- Behavior B (unrelated AI perception update) happens to live in the same `if (!bDisableEditorTickPreview)` branch by accident of loop layout.
- A workaround sets the flag true to silence B in a test fixture.
- A later refactor splits B into its own conditional. The flag still honors its documented contract (A preserved). Fixture now spams events again. No build break, no test failure. Silent regression.

The flag was never a contract for behavior B. It was a temporal coincidence that two behaviors lived under one predicate.

## The Rule

**When a flag's name and documented purpose are unrelated to the behavior you want to control, you are exploiting an implementation detail, not configuring.** Two valid fixes:

1. **Find the named contract that actually expresses the behavior.** Grep the emitter and its guards — there is often a properly-named flag, CVar, or feature gate one layer deeper.
2. **Restructure so the behavior has a named contract.** Extract a new predicate, wire it through, pin to the new name. The cost of adding it is paid once; incidental-flag failures recur every refactor.

"It works because B happens to live in the same branch as A" is not a stable invariant. The docstring is what the maintainer promises; shared-branch coincidence is what they don't.

## How to Find the Right Contract

- Grep the behavior's emitter (log line, event broadcast, side effect). Inspect guards on the call site and on every caller up the stack — the right name often already exists.
- Read the flag's docstring. If it says nothing about behavior B, the flag is not a contract for B — full stop.
- If no named contract exists, propose one in the plan and ship the new predicate alongside the workaround in the same commit.
- Anti-pattern: a comment "we set this flag to suppress B." It becomes orphan documentation the moment the path is refactored — grep for "B" won't hit the flag.

## The Same Trap at the CLI↔Native-Op Seam

The flag trap generalizes. Anywhere you consume a *signal* as if it were the *contract*, the same silent regression waits — and the seam where a bash CLI wraps a native op is dense with them (empirical cluster: engine-migration strangler work).

- **The process exit code is not the op's result contract.** A native op signals errors via its structured result (`{exit_code: 1}` OR a top-level `{error}` under the JSON-RPC `result` key); the CLI *process* still exits 0. A bash wrapper checking `$?` (via `|| return $?` or bare) is reading the incidental process signal, not the named contract — it silently succeeds on failure and corrupts lifecycle state. Fix: a mutation-aware route helper that captures stdout and returns non-zero on a present-and-nonzero `.exit_code` OR a truthy top-level `.error`, passing stdout through for output-consuming callers. **Not** a blanket `exit_code → process-exit` map: `exit_code` is overloaded — verdict ops (e.g. `handoff.has_live_children`) return nonzero as a *normal answer*.
- **Result shape is per-op — do not generalize one op's shape to another.** Guard/query ops return `{exit_code, …}`; writer ops (`queue.append`, `promote`) return `{out_path, …}` or `{skipped, reason}` with **no** `exit_code`. Checking `result.get('exit_code')` on a writer op always sees absent→0 and reads a *skipped write* as success. Verify each op's real return shape against source before writing verdict logic — the shared-shape assumption is the same false invariant as the shared-branch coincidence above.
- **Load-bearing mutations must fail loud on rejection; advisory ops may warn-and-continue.** A strangler call site (`coordinator-handoff-archive.sh --supersede`, now routed through a direct `handoff.archive_transition` mode `supersede` call via `cc_invoke.route_mutation`) invoked a native mutation whose `_resolve_path` deliberately rejects post-`git-mv` paths (mutation verbs are live-only). The op returned non-zero, but the call site printed `WARNING … exited N` and fell through to `exit 0` — so `deployment_state: abandoned` was **silently never set** on native-live machines. Discriminator: advisory/paper-trail ops (`stamp_shipped_in`, an auxiliary session-record) may legitimately warn-and-continue; a load-bearing lifecycle mutation (`status`/`deployment_state`) must fail loud so the caller never commits a half-mutated artifact. **Test axis:** a strangler/parity test that only exercises the legacy fallback gives false parity confidence — assert the FINAL on-disk state, not just exit code + file-moved.
- **A mutation op that cannot confirm its own write must never exit 0.** This is the bullet above turned inward: there, the *caller* threw away a rejection the op correctly reported. Here the op reports nothing to throw away — it attempts a write, never establishes that the write landed, and returns success anyway. The caller has no defect to fix, because the only signal it receives is a truthful-looking zero. The three shapes it arrives in: the op swallows a transport failure and returns 0 on the reasoning that some later sweep will backstop it (false whenever the engine *is* the sweep); the op's write is a no-op because a guard silently declined it, and "nothing raised" is read as "it worked"; or the op aggregates N sub-directives and reports the batch landed without checking each one's exit. **Rule:** success is a claim about the artifact's post-state, not about the absence of an exception — an op that mutates must read back what it wrote, or must return non-zero. **Not** an argument for making every op verbose or for treating exit 0 as suspect: a *verdict* op returning 0 is answering a question, and an *advisory* op may still warn-and-continue. The rule binds ops that claim to have changed something.

  Doctrine altitude is earned by independent re-derivation, not by severity — three sightings in three surfaces, by two repos: `archive-stamp-cli supersede-archive-handoff` and `handoff-archive-transition supersede` exiting 0 having rewritten nothing (DoE-claude → claude-klabauter, `cross-repo/archive/2026-07-24-doe-claude-em-engine-timeout-swallowed-exit0.md`); the same op again as a silent no-op with the hand-edit fallback blocked by a tripwire whose remediation menu omitted the needed disposition (`state/bug-backlog/2026-07-25-archive-stamp-cli-supersede-archive-hand-0d24cefc847e.yaml`); and `workday_complete.apply` listing seven nonzero-exit directives under `landed` with the `failed` bucket empty, while the skill instructed the EM to trust that report (example-market-data-repo-em → claude-klabauter). The third is the one that shows why this is a contract rule rather than a bug class: a truthful-looking report is worse than a crash, because the doctrine downstream of it tells a reader to believe it. The consequence at the far end was a consumer repo's `state/handoffs/` degrading into a folder its EM had stopped trusting — 46 of 48 batons never reaching a terminal state, because each op that should have moved one had already reported that it did.

- **Preserve the consumer's existing fail-loud across a routing change.** When routing N inline readers through a wrapper that *newly* returns empty-under-ambiguity, the wrapper's empty return **is** the fix — brief the executor to keep each consumer's existing fail-loud handling (exit codes, error paths) intact. Degrading the downstream to silent-continue fights the plan's own detect-then-fail-loud doctrine and deletes test-locked behavior (a first pass deleted safe-commit priority-4 and review-trail exit-3 on an "absent >> blocked" brief; each script's own suite caught it). Run every touched script's suite before committing a routing change.
- **A partial inverse in a name-mapping filter silently drops.** A sibling-exclusion filter compared one schema-name against `_queryTypeToSchemaName(type)`, but the inverse mapped only `completion` — so `bug`/`debt`/`improvement` were silently excluded fleet-wide. When a compare-filter uses a name mapping, the inverse MUST be complete — audit it against the full forward map, not just the one documented exception. A partial map is an exploited coincidence, not a contract.

## Related

- → [`implementation-standards-by-domain.md`](./implementation-standards-by-domain.md) — domain-specific guard discipline
- → [`substrate-pin-doctrine.md`](./substrate-pin-doctrine.md) — sibling pattern: name what you actually depend on
