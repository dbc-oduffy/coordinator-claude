<!-- canonical source for disk-first-protocol — edit here, then run bin/verify-snippet-sync disk-first-protocol --fix -->
<!-- consumers: fixed list in snippets/registry.toml [snippet.disk-first-protocol] -->
<!-- INJECTED block, not paste-governed: assembled into the dispatched child prompt at dispatch -->
<!-- time via the `contract_blocks:` grammar (subagent-sandbox-policy.yaml), keyed by -->
<!-- `subagent_type`. Consumed by the G5 deep-research-pipeline family (repo-scout, -->
<!-- repo-specialist, research-scout, research-specialist, research-worker, research-sweep, -->
<!-- research-synthesizer, structured-synthesizer, notebooklm-research-scout) — the agents whose -->
<!-- deliverable is an incrementally-written file on disk, dispatched as Agent-Teams teammates -->
<!-- under parallel-fanout load. Not pasted by verify-snippet-sync. -->
<!-- -->
<!-- Distinct from, and additive to, the three already-resident blocks these agents carry -->
<!-- (text-only-recovery-preamble, guard-encounter-preamble, subagent-sandbox-preamble): those -->
<!-- cover recovery framing, guard-denial handling, and sandbox-path provisioning respectively. -->
<!-- This block covers the mechanical write-and-verify discipline layered on top — the early-write -->
<!-- probe and the after-every-write growth check — generalized from the repo-scout/repo-specialist -->
<!-- "Specifically… First action… After every file…" epilogue into one injected block shared by the -->
<!-- whole family, rather than a copy pasted separately per agent. -->

## Disk-First Early-Write Verification

Your deliverable is a file (or files) on disk, at the path(s) named in your dispatch prompt — not
your final chat reply. Inline analysis blocks, prose summaries, or a reply that dumps the content
instead of writing it count as **task failure**. The dispatcher, downstream specialist, or
synthesizer reads your output from disk, never from your reply.

**First action — early-write probe.** Before you do any substantive reading, searching, or
analysis, call `Write` once for EACH output path in your dispatch prompt with a short header stub
naming the deliverable and your spawn timestamp, e.g.:

```
# <Deliverable>: <chunk/topic identifier>

_Spawned at {SPAWN_TIMESTAMP}. Entries appended below as work proceeds._
```

This is mandatory, not optional. It (a) confirms your output paths are writable, (b) breaks any
"Write is forbidden" misframing before it can take hold, and (c) gives the dispatcher an early
disk signal that you are alive and on-protocol. After the probes succeed, proceed with your normal
work loop, appending to the file(s) incrementally rather than holding everything until the end.

**Verify every write landed.** After each append — or, for a single-shot deliverable, after your
one write — confirm the file actually grew: `Bash ls -la {path}` or a quick `Read` is cheap
insurance. If a `Write` appears to silently no-op, retry — do NOT switch to inline output as a
substitute.

**Doctrine root:** `coordinator/snippets/em-operating-doctrine.md § Extensions to coordinator defaults ▸ Fan-out dispatch extras ¶ "Scouts: disk-first"`
