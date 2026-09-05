# Context-Pressure Measurement

**System:** context-pressure. **Implementation:** `claude-klabauter`'s
`coordinator_core/hooks/postuse_advisory_dispatch.py` (`_check_context_pressure_sync`) and
`coordinator_core/session/context_usage_sidecar.py`. **Producer:** this repo's
`coordinator/bin/statusline.py`. This wiki documents that code; it does not own it.

## The product is the warning, not the record

A `/handoff` carries **curated state forward** — the EM chooses what survives. Compaction is
**lossy summarisation the EM does not control**. The mechanism's entire value is firing **before**
compaction, while the curated-state option still exists. A warning after the fact is not a lesser
version of the same product; it is a different, much weaker one.

That is why `PostCompact` is not a detection point. The **PreCompact sentinel bridge**
(`context_pressure_precompact.py`) exists only for the residual case: it records that compaction
happened, and the next PostToolUse surfaces it once, guarded by a ≥15%-shrink check so a
compaction that didn't meaningfully shrink the transcript doesn't fire a spurious notice. That
bridge is a consolation record for a missed pre-emption, not a second detection mechanism.

## Two bands, and nothing else

| Reading | Behaviour |
|---|---|
| no usable reading | **silence** |
| < 40% | **silence** |
| ≥ 40% | INFORMATIONAL — checkpoint state to disk at the next natural boundary; do not stop |
| ≥ 43% | HANDOFF NOW — run it before compaction takes the choice away |

Each band barks once per session, behind a 5-minute throttle. Crossing straight into the red band
suppresses the orange text.

**Nothing fires below 40%.** This is a floor, not a default: a check added to this path that
emits under 40 violates it however quietly it is worded, and however good its reason. The
operator's continuous read-out is the terminal status line, which costs no attention to ignore;
the advisory channel interrupts an EM mid-work on every tool call and is reserved for the two
moments a decision is actually due.

**43, because the band has to land ahead of the cut with runway to spare.** Anthropic
auto-compacts the 1M tier at a fixed ~500K tokens, decoupled from window size, so a 50% trigger on
a 1M window coincides *exactly* with the cut — firing the warning with the event it exists to
pre-empt. Auto-compaction has been observed firing at 47 in practice, so a band level with or two
points under that observation warns too late to act on: a handoff needs room to compose, not a
notification that one is no longer possible. 43 buys that room. Do not
re-derive the bands from that ceiling constant: they are set percentages, and deriving them would
silently move them if Anthropic moves the ceiling.

## Where the number comes from

The harness hands the **statusline command's stdin** an authoritative `context_window` block
(`used_percentage`, `context_window_size`, and a `current_usage` token breakdown). **No hook
event payload carries any of it** — a hook cannot ask how full the window is. So
`coordinator/bin/statusline.py` publishes that block to a per-session sidecar at
`$COORDINATOR_SETTINGS_HOME/state/context-window/<session-id>.json`, keyed `captured_at`, and the
advisory reads it back.

`used_percentage` is used verbatim. It is a measurement, not an estimate — no byte-per-token
proxy, no transcript tail scan, no `count_tokens` call, no default window, and no percentage
computed from any of them. A reading that is absent, unparseable, non-numeric, NaN, infinite, or
negative is **no reading**, never zero.

That path and record shape are a **cross-plane contract**: this repo holds them stable, claude-klabauter
reads them. Renaming either breaks the advisory silently — see
`docs/wiki/coordinator-tripwires/producer-and-consumer-each-resolve-their-own-path.md`.

## Coverage

Interactive sessions are measured. **Headless sessions are not, by design** — no statusline
renders there, so no sidecar exists, and they get silence rather than a notice about it.

## The wall-clock runtime tripwire is a different mechanism, and it is off

`_check_runtime_tripwire_sync` fires on **elapsed minutes**, not occupancy, and emits wrap-shape
text ("stop starting new work… write a successor-handoff stub; return"). It is opt-in
(`COORDINATOR_RUNTIME_TRIPWIRE=1`) and off by default: on a spawn-taxed machine its minutes buy
little work, so it prescribed handoffs at 15-20% of window, on the same advisory channel as the
text above and indistinguishable from it by the agent receiving it. No minute value makes elapsed
time a proxy for occupancy, which is why it is gated rather than re-tuned. Do not re-arm it
fleet-wide without re-deriving it against a context reading.
