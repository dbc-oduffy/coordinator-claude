<!-- canonical source for guard-encounter-preamble — edit here, then run bin/verify-snippet-sync guard-encounter-preamble --fix -->
<!-- consumers: fixed list in snippets/registry.toml [snippet.guard-encounter-preamble] -->

## Guard Denial Is a Stop Signal

A coordinator PreToolUse denial is a stop, not an obstacle. **Follow a remedy the denial itself names** (e.g. "use a script file", a named CLI): that is compliance, not evasion. **Never reshape a denied operation on your own initiative** — a script file, `sh -c`, `python -c`, `xargs`, a written-then-run heredoc, or any rewrite aimed at how the guard *reads* the command. Otherwise **stop and report** the exact command and the guard that denied it; what happens next, including any override, is the dispatching EM's call. Disclosing an evasion does not excuse it. A denial naming no next move is a tool bug: report it to the guard's owner.
