# Context-Pressure Measurement

**System:** context-pressure. **Implementation:** the engine repo's
`coordinator_core/hooks/postuse_advisory_dispatch.py` (`_check_context_pressure_sync`) and
`coordinator_core/session/context_usage_sidecar.py`. **Producer:** this repo's
`coordinator/bin/statusline.py`. This wiki documents that code; it does not own it.

## The product is the warning, not the record

A `/handoff` carries **curated state forward** — the EM chooses what survives. Compaction is
**lossy summarisation the EM does not control**. The mechanism's entire value is firing **before**
compaction, while the option the venue actually offers still exists. A warning after the fact is
not a lesser version of the same product; it is a different, much weaker one.

**Which option that is depends on the venue.** On an attended host it is the curated handoff. On a
cloud box a successor costs a new container, a fresh clone and re-provisioning, so **compaction is
the continuation primitive and the handoff is the expensive path** — the pre-emptible act there is
the commit and the baton, not a handoff. The engine selects this with no configuration
(`compaction_warnings`' environment rung); the band table below states both terminals. Ruled in the
cloud-is-a-venue decision record; tripwire
`A-HANDOFF-NAG-ASSUMES-A-SUCCESSOR-THAT-IS-CHEAP-TO-REACH`.

That is why `PostCompact` is not a detection point. The **PreCompact sentinel bridge**
(`context_pressure_precompact.py`) exists only for the residual case: it records that compaction
happened, and the next PostToolUse surfaces it once, guarded by a ≥15%-shrink check so a
compaction that didn't meaningfully shrink the transcript doesn't fire a spurious notice. That
bridge is a consolation record for a missed pre-emption, not a second detection mechanism.

## Two bands, and nothing else

Bands are **token runway back from the session's own compaction cut**, never percentages of a
window. The cut is `effective_auto_compact_window − 33,000`, resolved per session.

| Reading | Behaviour |
|---|---|
| no usable reading | **silence** |
| more than 100,000 tokens of runway | **silence** |
| ≤ 100,000 tokens of runway | INFORMATIONAL — checkpoint state to disk at the next natural boundary; do not stop |
| ≤ 70,000 tokens of runway, attended host | HANDOFF NOW — run it before compaction takes the choice away |
| ≤ 70,000 tokens of runway, cloud box | INFORMATIONAL — bring the task spine current, then commit and checkpoint the baton; continue the run |

Each band barks once per session, behind a 5-minute throttle. Crossing straight into the red band
suppresses the orange text. **The red band's two rows are one signal with two terminals, never an
off switch** — no venue, mode or fleet value removes the warning; only the recommended act changes.
The orange band is identical everywhere.

**Nothing fires above 100,000 tokens of runway.** This is a floor, not a default: a check added
to this path that emits in the quiet band violates it however quietly it is worded, and however
good its reason. The
operator's continuous read-out is the terminal status line, which costs no attention to ignore;
the advisory channel interrupts an EM mid-work on every tool call and is reserved for the two
moments a decision is actually due.

**The band is runway back from the cut, not a fraction of a window.** Claude Code auto-compacts
at `window − 33,000` tokens, where `window` is `CLAUDE_CODE_AUTO_COMPACT_WINDOW` when set — it
takes precedence over `/autocompact`, `--autocompact`, and the `autoCompactWindow` setting — else
the model's own. (The 33,000 is `min(maxOutputTokens, 20000) + 13000`; no tier this runs on has
been observed below 20,000, and the implementation carries the sum, not the terms.) A band
expressed as a percentage moves whenever the window moves; a runway does not.

**The denominator trap: one cut, two reported percentages.** An attended host's statusline reports
occupancy against the MODEL window, the cloud web client against the AUTO-COMPACT window — the
same cut, rendered as 47% and as 93%. Tripwire:
`A-CONTEXT-PERCENTAGE-WITHOUT-ITS-DENOMINATOR`.

## Where the number comes from

Two sources, sidecar preferred. The harness hands the **statusline command's stdin** an
authoritative `context_window` block (`used_percentage`, `context_window_size`, and a
`current_usage` token breakdown). **No hook event payload carries any of it** — a hook cannot ask
how full the window is. So `coordinator/bin/statusline.py` publishes that block to a per-session
sidecar at `$COORDINATOR_SETTINGS_HOME/state/context-window/<session-id>.json`, keyed
`captured_at`, and the advisory reads it back verbatim: a measurement, not an estimate, and it
carries its own denominator with it.

Where no sidecar exists, a bounded transcript-tail read is the fallback: a 256 KiB tail of the
transcript, deduped by `message.id`, rejecting streaming placeholders — 1.6 ms, zero spawn. Both
sources report occupancy against whichever window produced them; neither is a byte-per-token
proxy, a `count_tokens` call, or a default-window guess. A reading that is absent, unparseable,
non-numeric, NaN, infinite, or negative is **no reading**, never zero.

That path and record shape are a **cross-plane contract**: this repo holds them stable, the engine repo
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
