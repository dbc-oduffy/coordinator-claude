# Cloud-session verification — does the coordinator layer actually load?

Run this **inside a cloud session**, once, after `setup.sh` has provisioned the environment. It
answers the one question provisioning cannot: the setup script runs *before* Claude Code launches,
so it can prove the files are on disk and prove nothing about whether Claude Code reads them.

Paste the result back into this file's § Recorded results and commit it. An unrecorded run is a run
nobody after you can rely on.

## What is already settled, and needs no re-probing

- **SessionStart hooks run in cloud.** Vendor-documented: "Claude Code launches and runs your
  SessionStart hooks, as it does at the start of every session, local or cloud." Ordering is setup
  script first, then Claude Code.
- **Your own machine's `~/.claude` does not carry over.** "User-level settings stay on your
  machine." This is about the laptop you launched from — *not* about the VM's own `$HOME/.claude`,
  which `setup.sh` writes and which is as local to the session as any file it clones. Conflating
  those two is the trap; see the tripwire
  `coordinator/docs/wiki/coordinator-tripwires/a-vm-written-home-claude-is-not-your-machines-home-claude.md`.
- **Skills, agent types, engine import, and the env-var block reach the session.** Verified
  2026-09-06 in a real Anthropic-hosted environment: a session booted against `setup.sh` reported,
  from its own context rather than from the script's config, coordinator skills and agent types
  present and loaded, both env-var-block values reached, both clones present, the marketplace
  registered as a directory source, `coordinator_core` importing, and the pointer file written.
  Session ran as root with `HOME=/root`, the same user and home the script ran as.
- **The image's `python3` carries no `EXTERNALLY-MANAGED` marker** (same 2026-09-06 session). The
  engine installer's exit-96 PEP-668 refusal does not fire on this platform.

## What is NOT settled — the gap this file closes

Whether **plugin-declared hooks** (`coordinator/hooks/hooks.json`) fire in a cloud session. The
2026-09-06 verification named skills, agents and the engine; it did not name hooks. That matters
more in cloud than anywhere else, because cloud sessions are the unattended ones: a guard that
silently fails to load has no operator to notice.

There is indirect evidence in both directions and neither is conclusive. `setup.sh` pre-sets
`COORDINATOR_PROBE_CANARY` precisely because a PreToolUse hook would otherwise deny every Bash call
for the session's life — which presumes hooks fire; but that line was written prophylactically, not
after observing a denial.

## The probes

Two probes, in order. The first is the cheap one and settles the class.

### Probe 1 — PreToolUse plugin hooks (one command, unambiguous)

```
find / -name whatever
```

- **DENIED**, with text naming `Guard: runaway-find` → plugin-declared PreToolUse hooks are live.
  The whole plugin hook layer is being read; you are done with probe 1.
- **RUNS** (or errors as an ordinary shell command) → plugin hooks are NOT loading. Stop and record
  that; nothing below is worth running, and the environment is not safe for unattended work.

Chosen because it needs no setup, mutates nothing, and the deny text names the guard by name, so a
positive cannot be confused with an unrelated failure.

### Probe 2 — SessionStart payload delivery

Read your own session's opening context. Did the EM role payload appear — the `## Your Role`
block, and the `assert-em-role` line reporting a peer-session count?

- **Present** → SessionStart plugin hooks fire *and* their stdout reaches context.
- **Absent while probe 1 denied** → hooks fire but the payload is not landing in context. That is a
  different defect from "hooks don't load", and it has local precedent worth reading first: the
  fan-in stdout truncation recorded in `coordinator/hooks/hooks.json`'s `SessionStart[1]._comment`,
  where a payload reached context in 4 of 279 measured sessions while sharing a stdout stream.

## Recorded results

| Date | Environment | Probe 1 (PreToolUse) | Probe 2 (SessionStart payload) | By |
|---|---|---|---|---|
| _unrun_ | Anthropic-hosted | — | — | — |

Until a row here is filled, treat cloud hook coverage as **unknown, not present**. Unknown is the
honest state and it is the one worth acting on: assume a cloud session may be running with no
guards until this table says otherwise.
