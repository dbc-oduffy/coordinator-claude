<!-- canonical source for quota-self-detect-preamble — edit here, then run bin/verify-snippet-sync quota-self-detect-preamble --fix -->

## Quota-Exhausted Self-Detection

Before returning your response, scan the text you are about to emit for these quota-exhaustion patterns (case-insensitive):

| Pattern | Strength | Fires alone? |
|---|---|---|
| `resets HH:MM` (regex: `resets [0-9][0-9]?:[0-9][0-9]`) | Highly specific | **Yes** |
| `session limit` / `rate limit` / `quota` | Weak | Only if body length < 1024 bytes |

**Corroboration rule:** `resets HH:MM` fires on its own. The weak patterns fire only if the total body you are about to return is under 1024 bytes — a short body containing one of these terms is almost certainly a quota-error apology, not a real work product. Body length means the text of the response you are constructing, not system context or prompt.

**If you find yourself about to return text matching these patterns, the runtime hit a quota mid-dispatch.** Do NOT return the apology text — your task did not complete, and returning it as if it were a work product misleads the dispatching EM. Substitute the following envelope as your **sole return, no other content**, then exit:

```
QUOTA-EXHAUSTED-DISPATCH: <matched-pattern> | ts=<ISO-8601> | re-dispatch=eligible | original-brief-summary=<≤80-char one-line summary you infer from your dispatch brief>
```

- `<matched-pattern>` — the exact pattern that fired (e.g. `session limit`, `resets 14:30`, `quota`).
- `ts=<ISO-8601>` — current timestamp (e.g. `2026-06-15T14:30:00Z`). Lets the EM order multiple quota events and infer retry timing.
- `re-dispatch=eligible` — leave literal. Signals the failure is transient and re-dispatchable after quota resets, not a permanent task failure.
- `original-brief-summary=<…>` — ≤80-char summary of what you were asked to do, inferred from your dispatch brief. A re-dispatch anchor when the original brief is large.

No partial work, no apology, no preamble — the envelope is a clean machine-readable signal. The EM-side scan recognises `QUOTA-EXHAUSTED-DISPATCH:` as a definite quota event and handles retry or escalation.
