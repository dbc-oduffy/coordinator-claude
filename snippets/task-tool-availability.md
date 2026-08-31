<!-- canonical source for task-tool-availability — edit here, then run bin/verify-snippet-sync task-tool-availability --fix -->
<!-- consumers: fixed list in snippets/registry.toml [snippet.task-tool-availability] -->

`TaskCreate` absent from this session's surface (`ToolSearch("select:TaskCreate")` returns nothing)
→ fall back to `coordinator-tasks-mirror` for the same flight-recorder role; do not assume either
state without checking. When Task* is unavailable, dispatch the phases in order, waiting on each
completion notification — that is the ordering a `blockedBy` chain would otherwise express.
