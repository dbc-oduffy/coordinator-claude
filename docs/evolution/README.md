# Evolution

> The fingerprints on this project. Why it looks the way it does, what failed before we got here, and what we tried that didn't work.

Most software projects describe what they *are*. This series describes how this one *became* what it is. Public artifacts and the README explain the current state; this series is for readers who want to know whether the design has been pressure-tested or just declared.

It's also a credibility ledger. If you're evaluating whether to adopt this plugin, the strongest signal isn't a feature list — it's a documented record of negative results we ran on ourselves and choices we declined despite their plausibility. Aesthetic decisions look the same as load-bearing ones from the outside; this series sorts them.

## The chapters

1. **[Origin](01-origin.md).** What problem this started solving, what the first version looked like, what failed early.
2. **[Handoffs over compaction](02-handoffs-over-compaction.md).** Why we stopped trusting automatic summarization and built a structured baton-passing model instead. Frames the [research doc](../research/2026-03-21-handoff-artifacts-vs-compaction.md).
3. **[Personas as ergonomics](03-personas-as-ergonomics.md).** The honest version of the persona story: detailed reviewer profiles didn't improve recall and increased false positives. Calibration blocks, not character depth, are what actually work. Frames the [persona experiment](../research/2026-03-26-persona-experiment-results.md).
4. **[Investigation funnel](04-investigation-funnel.md).** Why we built tiered context loading and stopped reaching for Sonnet scouts as the default investigation tool.
5. **[Failure modes](05-failure-modes.md).** A taxonomy of how AI engineering work goes wrong, with detection signals and recovery moves. The thing this project gets paid in is operational scar tissue.
6. **[What we rejected](06-what-we-rejected.md).** Choices we declined — including from external review — and the reasoning. Taste, not just enthusiasm.

## Voice

These read like war stories, not engineering changelogs. That's deliberate. Engineering changelogs decay into "we did X, then Y" and fail to transmit the *why*. War stories carry the why because they carry the failure that prompted the change. If a chapter feels too clinical, it has probably drifted from purpose.

## How this series gets updated

Chapters get added when a non-trivial design decision lands and we want to mark *why*. Existing chapters get amended when a later result changes the picture (e.g., the personas chapter would be amended if a future experiment found a regime where character depth *did* improve recall — that hasn't happened yet, but we'd say so).

Don't update chapters to remove embarrassing details. The embarrassment is the point.
