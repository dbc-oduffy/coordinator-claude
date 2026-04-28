# Bug Sweep — Pattern Library and Reference Tables

Detail companion to `commands/bug-sweep.md`. Pattern catalog, cost profile, and failure-mode matrix.

## Bug Patterns — Universal (all languages)

- `TODO`, `FIXME`, `HACK`, `XXX`, `BUG` comments — potential deferred bugs
- Empty catch/except blocks — swallowed errors
- Unreachable code after return/throw/raise

## Bug Patterns — Python

- Bare `except:` without exception type
- `except Exception as e: pass` — swallowed
- Mutable default arguments (`def f(x=[])`)
- `is` comparison with literals (should be `==`)
- Missing `await` on async calls

## Bug Patterns — JavaScript/TypeScript

- Unhandled promise rejections (`.then()` without `.catch()`)
- Missing `key` prop in React lists

## Bug Patterns — C++/Unreal

- Raw `new` without matching `delete` (memory leak)
- Missing `nullptr` checks after `Cast<>()` or `FindObject()`
- `UPROPERTY()` missing on UObject pointers (GC won't track them)
- Missing `Super::` calls in overridden lifecycle functions

## Code Smells & Structural Patterns (ALWAYS ON)

Code smells are bugs waiting to happen. Fix them alongside functional bugs:

- `== null` vs `=== null` (JS/TS)
- `var` vs `let`/`const` (JS/TS)
- `any` type assertions hiding real types (TS)
- Functions >200 lines (any language)
- Duplicated code blocks (3+ near-identical sites)
- `FString` concatenation in hot loops (C++/UE)
- Mid-file imports, unused imports, dead parameters
- Confusing function names that don't match behavior
- In-place mutation of shared data without documentation
- Double-checked locking with subtle correctness issues

## Cost Profile

| Scenario | Sonnet Agents | Executors | Wall-Clock |
|----------|---------------|-----------|------------|
| Small repo, 3 systems | 4 (3 search + 1 test) | 2-3 | ~15-25 min |
| Medium repo, 6 systems | 7 (6 search + 1 test) | 3-5 | ~25-40 min |
| Large repo, 8+ systems | 9+ | 4-6 | ~35-50 min |

**`DOCS_VERIFY` overhead:** Track C adds 1 docs-checker agent per chunk (parallel with A2). Phase 3.5 adds 1 docs-checker post-fix pass. Total: +N+1 Sonnet agents, +5-10 min wall-clock. Worth it for compiled/framework-heavy stacks (UE, Unity, C#, C++, etc.) where "compiles" does not imply "as documented" and API hallucinations are the highest-risk false-confidence failure mode.

## Failure Modes

| Failure | Prevention |
|---------|------------|
| False positive flood | Phase 2 triage with explicit "false positive" category. |
| Fix introduces regression | Post-fix test suite run; revert and defer if new failures. |
| Sonnet over-reports low-confidence issues | Verify and either fix or drop — LOW confidence is not a reason to backlog; it's a reason to verify. |
| Coordinator skips code smells as "informational" | Smells are always fixable. Agents must use P0/P1/P2 only — no P3/info/defer. Coordinator must fix all P2s, not just P0/P1. |
| Pattern library misses project-specific bugs | Phase 0 reads `tasks/lessons.md` for known gotchas. |
| Executor fix uses hallucinated API | Phase 3.5 docs-checker catches it before commit; reverted finding goes to backlog. |
| holodeck-docs server unavailable during Track C | Docs-checker marks claims UNVERIFIED, sweep continues; report notes degraded API verification. |
| Test suite doesn't exist | Report the gap, sweep code-only. |
| Executor fix conflicts across files | Group fixes by file/system. |
| Executor agent failure | Re-dispatch once. Second failure → move finding to backlog with `fix-blocked: agent failure`. Keep scratch files for manual review. |
