<!-- canonical source for instrument-can-report-red — edit here, then run bin/verify-snippet-sync instrument-can-report-red --fix -->
<!-- consumers: see bin/snippet-registry list-consumers instrument-can-report-red -->

<!-- BEGIN instrument-can-report-red (synced from snippets/instrument-can-report-red.md) -->
## Can This Instrument Report Red?

One check, over any falsifier, gate, or verification instrument: **is the instrument's verdict
wired to its exit path, or only computed?**

The tell, stated without reference to what a given falsifier is *for*: a verdict variable is
computed somewhere in the instrument, but the code path that decides pass/fail — the exit code,
the return value, the raised exception — does not read it. An instrument that cannot fail this way
cannot report red under any input, which makes every green result from it unfalsifiable rather
than earned.

Trace it concretely: find where the verdict is computed, then find every path out of the
instrument (return statements, `sys.exit` calls, thrown exceptions, a CI step's exit code) and
confirm at least one of them branches on that verdict. A verdict computed and then logged, stored,
or discarded without ever gating an exit path fails this check regardless of how sound the
computation itself is.

Two sightings motivate this as a standing check, not a one-off: `inst-07` injects a token into its
own fixture and reports green regardless of the injection outcome; example-game-repo's release-gates
falsifier computes a shim verdict it never feeds into its exit code. Both are the same tell — a
computed-but-unwired verdict — not two different defects.
<!-- END instrument-can-report-red -->
