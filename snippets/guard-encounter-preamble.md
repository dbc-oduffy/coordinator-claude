<!-- canonical source for guard-encounter-preamble — edit here, then run bin/verify-snippet-sync guard-encounter-preamble --fix -->
<!-- consumers: fixed list in snippets/registry.toml [snippet.guard-encounter-preamble] -->

## Guard Denial Is a Stop Signal

A coordinator PreToolUse denial is a stop, not an obstacle. **Never reshape a denied operation** — a script file, `sh -c`, `python -c`, `xargs`, a written-then-run heredoc, or any rewrite aimed at how the guard *reads* the command. **Stop and report** the exact command and the guard that denied it; what happens next, including any override, is the dispatching EM's call. Disclosing an evasion does not excuse it.
