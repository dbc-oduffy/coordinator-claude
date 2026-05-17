# External-Tool Integration Patterns

> Recipes for shelling out to external CLIs/engines from coordinator scripts and agents — exit-code semantics, stdout capture, error mapping.

## Diagnostic recipes

### UE Commandlet `Main` return value reinterpretation

Unreal Engine commandlets that return `-1` from their `Main` function surface to shell wrappers as `0xFFFFFFFF` (4294967295) — the signed `-1` is reinterpreted as an unsigned 32-bit value by the process exit-code path.

**Before assuming SEH or native crash on `exit code 4294967295`, grep the commandlet's stdout for `LogPython: Error:` Traceback.** UE wraps Python `TypeError`-on-exit (and other unhandled Python exceptions) as commandlet exit `-1`, which unsigned-converts to `0xFFFFFFFF`. project-rag's `F-NEW-5` was misclassified as SEH for two release cycles before a `PROJECT_RAG_MODE_B_DEBUG_CAPTURE=1` run surfaced the actual `TypeError: NativizeStructInstance: Cannot nativize 'str' as 'TopLevelAssetPath'` traceback at `tag_references_dump_script.py:54`. The unsigned exit code is a *language-runtime error wrapped by the host*, not a native crash — same shape applies to any subprocess host (UE-Cmd, Node `child_process`, Python `subprocess`, .NET) that wraps a guest interpreter and surfaces an unsigned-converted `-1`.

**Implication for exit-code assertions:** check for BOTH forms when validating a commandlet failure:

```bash
if [[ "$rc" == "-1" || "$rc" == "4294967295" || "$rc" == "0xFFFFFFFF" ]]; then
  echo "commandlet failed (Main returned -1)"
fi
```

PowerShell sees `$LASTEXITCODE = -1` directly (signed); `cmd.exe` and bash see the unsigned form. Cross-shell wrappers must normalize.

### General principle

Exit-code contracts across the C/C++ → shell boundary are signedness-dependent. When wrapping a non-shell binary:

1. Document the binary's documented return values explicitly.
2. Assert against the full set of representations the wrapping shell can observe.
3. Prefer parsing stdout/stderr sentinel lines over exit codes when the binary writes structured output.

## Stateful sessions vs request/response

**Long-lived stateful sessions are not transactional request/response.** When orchestrating PIE, an editor REPL, a notebook kernel, or any long-lived runtime over MCP/RPC, polling-with-timeout is a **symptom of protocol mismatch**, not a fix target. The pattern fires when you reach for a higher timeout because "the call sometimes takes longer" — the actual question is whether the protocol shape itself is wrong for the work it's doing.

Before bumping a sync-timeout in code that drives a stateful session, ask:

- **Should this be an event subscription?** The consumer doesn't actually want "the result of one call" — it wants "notify me when state X reaches value Y." Polling-with-timeout is a busy-wait implementation of an event the protocol should expose directly.
- **Should this be a deferred-response (request-with-correlation-id)?** The work is async by nature. The caller submits, gets a correlation id, polls or subscribes to that id. A single synchronous call with a long timeout collapses the producer's lifecycle into the caller's, losing visibility on partial progress.
- **Should "session" be a first-class concept in the protocol?** If the producer needs to maintain state across calls (open editor, loaded notebook, running game), the protocol needs explicit session handles — not implicit "the same long-running process is on the other end of the wire." Without session identity, timeouts can't distinguish "session crashed and was replaced" from "session is still doing the work."

Symptom shape: timeout bumps that accumulate over months without resolving the underlying flakiness. Fix shape: redesign the protocol seam before iterating timeout values.
