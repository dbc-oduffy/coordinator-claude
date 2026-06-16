<!-- canonical source for quota-self-detect-preamble — edit here, then run verify-quota-self-detect-sync.sh --fix -->

## Quota-Exhausted Self-Detection

Before returning your response, scan the text you are about to emit for the following quota-exhaustion patterns (case-insensitive):

| Pattern | Strength | Fires alone? |
|---|---|---|
| `resets HH:MM` (regex: `resets [0-9][0-9]?:[0-9][0-9]`) | Highly specific | **Yes** — match alone fires. |
| `session limit` | Weak | Only if body length < 1024 bytes. |
| `rate limit` | Weak | Only if body length < 1024 bytes. |
| `quota` | Weak | Only if body length < 1024 bytes. |

**Corroboration rule:** `resets HH:MM` fires on its own. Weak patterns (`session limit`, `rate limit`, `quota`) only fire if the total body you are about to return is under 1024 bytes — a short body containing one of these terms is almost certainly a quota-error apology, not a real work product. Body length here means the text of the response you are constructing — the content you intend to return as your final answer, not including any system context or prompt.

**If you find yourself about to return text matching these patterns, the runtime hit a quota mid-dispatch.** Do NOT return the apology text. Your task did not complete and returning the apology text as if it were a work product misleads the dispatching EM. Instead, substitute the following envelope as your **sole return**, then exit:

```
QUOTA-EXHAUSTED-DISPATCH: <matched-pattern> | ts=<ISO-8601> | re-dispatch=eligible | original-brief-summary=<≤80-char one-line summary you infer from your dispatch brief>
```

Field guidance:
- `<matched-pattern>` — the exact pattern that fired (e.g. `session limit`, `resets 14:30`, `quota`).
- `ts=<ISO-8601>` — the current timestamp in ISO-8601 format (e.g. `2026-06-15T14:30:00Z`). Lets the EM order multiple quota events and infer retry timing.
- `re-dispatch=eligible` — leave this literal. It signals the EM that this failure is transient and the task can be re-dispatched after quota resets (as opposed to a permanent task failure).
- `original-brief-summary=<…>` — a ≤80-character one-line summary of what you were asked to do, inferred from your dispatch brief. Serves as a re-dispatch anchor when the original brief is large.

**Do not include any other content** — no partial work, no apology, no preamble. The envelope is a clean machine-readable signal. The EM-side scan recognises `QUOTA-EXHAUSTED-DISPATCH:` as a definite quota event and will handle retry or escalation.

**Spec backlink:** `plugins/coordinator/snippets/quota-self-detect-preamble.md`
**Doctrine root:** `plugins/coordinator/docs/wiki/tool-output-flakiness-protocol.md § API quota exhaustion`
