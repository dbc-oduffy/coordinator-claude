# Review signals

`routing.md`'s reviewer `**Signals` prose is the source of truth. `review-signals.json` is its
machine projection — one entry per distinct selection trigger, each pinned to the exact
`routing.md` H3 it projects. A parity test keeps the two equal.

Adding a persona or a new selection trigger means editing **both** `routing.md` and
`review-signals.json` in one commit — the JSON never drifts ahead of or behind the prose.

Scope: the coordinator base `routing.md` table only. A plugin-registered reviewer (game-dev's
The Game Dev Reviewer, whose own `routing.md` fragment carries its own `**Signals` lines and merges into the
composite table at dispatch time) stays prose-matched and is permanently unreachable by signal
id until a plugin-side contract shape exists.
