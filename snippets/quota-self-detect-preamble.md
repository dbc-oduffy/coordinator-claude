<!-- canonical source for quota-self-detect-preamble — edit here, then run bin/verify-snippet-sync quota-self-detect-preamble --fix -->

## Quota-Exhausted Self-Detection

Before returning your response, scan the text you are about to emit for these quota-exhaustion patterns (case-insensitive):

| Pattern | Strength | Fires alone? |
|---|---|---|
| `resets HH:MM` (regex: `resets [0-9][0-9]?:[0-9][0-9]`) | Highly specific | **Yes** |
| `session limit` / `rate limit` / `quota` | Weak | Only if body length < 1024 bytes |

**Corroboration rule:** `resets HH:MM` fires on its own. The weak patterns fire only if the body you are about to return is under 1024 bytes — a short body with one of these terms is almost certainly a quota-error apology, not a work product. Body length means the response text you are constructing, not system context or prompt.

**A match means the runtime hit a quota mid-dispatch.** Do not return the apology text — your task did not complete. Substitute this envelope as your **sole return, no other content**, then exit:

```
QUOTA-EXHAUSTED-DISPATCH: <matched-pattern> | ts=<ISO-8601> | re-dispatch=eligible | original-brief-summary=<≤80-char one-line summary you infer from your dispatch brief>
```

- `<matched-pattern>` — the exact pattern that fired (e.g. `session limit`, `resets 14:30`, `quota`).
- `ts=<ISO-8601>` — current timestamp (e.g. `2026-06-15T14:30:00Z`).
- `re-dispatch=eligible` — leave literal: the failure is transient, not a permanent task failure.
- `original-brief-summary=<…>` — ≤80-char summary of your dispatch brief, the re-dispatch anchor.

No partial work, no apology, no preamble. The EM-side scan treats `QUOTA-EXHAUSTED-DISPATCH:` as a definite quota event.
