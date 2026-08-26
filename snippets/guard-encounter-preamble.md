<!-- canonical source for guard-encounter-preamble — edit here, then run bin/verify-snippet-sync guard-encounter-preamble --fix -->
<!-- consumers: fixed list in snippets/registry.toml [snippet.guard-encounter-preamble] -->

## Guard Denial Is a Stop Signal

A coordinator PreToolUse guard denying your tool call is a stop signal, not an obstacle to route around.

**Forbidden:** reshaping a denied operation so it parses differently — a script file, `sh -c '...'`, `python -c '...'`, `xargs`, a heredoc written then executed, or any other rewrite aimed at how the guard *reads* the command rather than what the command *does*. If the guard denies the operation stated plainly, it denies the operation.

**Required:** stop, and report the exact command you attempted and the guard that denied it. Do not substitute a different approach of your own once you have been denied. What happens next is the dispatching EM's call, never yours.
