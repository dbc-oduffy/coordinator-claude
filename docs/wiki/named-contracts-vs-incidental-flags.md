---
title: Named Contracts vs. Incidental Flags
status: active
kind: doctrine-wiki
created: 2026-05-18
---

# Named Contracts vs. Incidental Flags

> A flag that disables the behavior you want only because of a shared code path is not configuration — it's an exploited implementation detail.

## Lesson Surface

**Origin:** example-game-workbench-repo, 2026-05-13 — coordinator improvement queue.

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

## Related

- → [`implementation-standards-by-domain.md`](./implementation-standards-by-domain.md) — domain-specific guard discipline
- → [`substrate-pin-doctrine.md`](./substrate-pin-doctrine.md) — sibling pattern: name what you actually depend on
