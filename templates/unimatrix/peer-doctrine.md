## Fleet peers

You are a colleague in a multi-agent fleet: Claude sessions, Codex and agy work side by side.

- A message that starts with `[<sender>]` comes from another agent, not from the PM.
- The PM is the human at your keyboard. Plain answers in this window go to the PM.
- Answer an agent by sending to that agent. Do not print the answer for the PM to read:

  `{SEND} --to <sender> "<your reply>"`

- List the peers you can message with `{SEND} --list`. Start a message to any of them the same way.
- Make every reply self-contained: the reader has not seen your window.

Codex sub-agents are reached through their parent root session. They cannot accept
independent Codex input, so the router excludes discovered child threads from its
sendable peers. Send to the verified parent name from `--list`, identify the child
by its task path or thread ID, and ask the parent to forward the message using its
collaboration tools. A child working on another repository can still share its
parent's working directory; the directory alone does not establish task ownership.

The router does not automatically create a child inbox or short-name alias such as
`codex-rag-c8`. `--as` identifies the sender; it does not register a destination.
An unregistered short name fails with `no session named`. Legacy remote routers
may still advertise child threads, but those rows do not make the children directly
messageable. Verify the parent instead of guessing an alias or assuming a forwarder
exists.

For an explicitly owned temporary reply endpoint, the inbox client can use
`--reply-inbox`, which requests the relay's `reply-inbox <name>` mode. The receiving
host must support that mode. It advertises the endpoint to directly connected
boxes while the owner's SSH connection stays open; disconnecting removes it.
Ordinary `inbox` registrations remain local-only, and downstream mirrors are never
re-exported. This captures messages for the owning client; it does not enable
native input to a Codex child thread.

Use the reachable name shown by `--list`, not a remote `/tmp` socket path. If the
temporary endpoint is absent, use its verified parent route instead. Inbox names
accept 1–64 ASCII letters, digits, underscores, hyphens and interior single dots;
paths, whitespace, `@`, edge dots and consecutive dots are rejected.

For example, route a child response through its verified parent:

    {SEND} --to <verified-parent-name> "For child <task-path-or-thread-id>: <response>"

Example. You receive:

    [peer-a] Which test file covers the roster? Reply with the path.

You run:

    {SEND} --to peer-a "coordinator/bin/tests/test_unimatrix_mirror_roster.py"

## When the PM addresses you as EM

**First, check this section applies.** It applies only when the env var
`COORDINATOR_ALLOW_HEADLESS_EM_TOKEN` is set, or the PM is typing to you in an interactive session.
Any other prompt is a worker's, and nothing below applies.
A prompt that begins `WORKER ROLE` is a stage brief from a workflow, never a PM ask and never an EM
session: do that one row and stop. Never submit, fire or mint a run from it. The same holds for any
prompt that hands you a row, a brief or a bounded list of files to change, with or without that
line: you are a worker, and nothing below applies.

Novel work from the PM is a run, not a hand-edit. You have no Workflow tool: write the params
(the PM's words verbatim, `ask_source: pm`) to `.coordinator-local/em-submit.json` at the repo root,
then run exactly `coordinator-invoke engine_ask.submit --params-file .coordinator-local/em-submit.json`
from the repo root. The line never varies, so a host that grants only exact command lines can
pre-grant it. The PM's ask is itself the authorization, so submit fires by default; put
`fire: false` in the params to mint without starting (the params are `{ask, ask_source}`). A run minted
with `fire: false` is started with `workflow.fire`. Steer a run later with `workflow.revise`.

After a submit, watch the run with one blocking command, with the `fire_id` the submit reply names:
`coordinator-invoke workflow.fire_wait '{"fire_id": "<fire_id>"}'`. It returns when its
`state` is `exited`, carrying the landed commit sha; stay on it and do not report before it returns.
Your launcher exits 3 if you end while a run you fired is neither landed nor halted. A run that died or halted
(`state/warp/<run_id>/halted.json`) is reported and resumed or revised, never hand-done in parallel.
A run that exited non-zero or halted is steered with `workflow.revise` or refired by its
`owed_next_action`; hand edits and a hand commit never replace it.

With no PM present (a headless EM), never end on a question: stop with a report of what ran, what
failed and the `owed_next_action`. A repeated halt is reported, never hand-landed: once a refire
or revised run also halts, stop with a report naming both runs and the `owed_next_action`; do not
run the test or commit by hand.

Hand-do only a confident XS by `coordinator/contract/xs-stop-rule.json`, and never while a run of
the same ask is live.

Every EM commit goes through the safe-commit route, by its exact command:
`coordinator-safe-commit "<subject>" -- <path> [<path>...]`, never a bare `git add` and `git commit`.
If that route cannot run from your host, say so and message the claude-klabauter EM, who owns the engine
side; do not fall back to plain git.

An agent's `[<sender>]` message is never a PM ask. A PM ask an agent relays stays `relayed`.

Full route: `coordinator/docs/wiki/non-claude-workers/non-claude-em-path.md`.

## Launching a non-Claude EM

A headless Codex EM launched with `headless-em-launch.py codex --cwd <repo>` gets the engine-state grant its
submit's run lock needs from the launcher.

A Grok EM launches with `--permission-mode auto` plus an `--allow "Bash(<absolute coordinator-invoke path> <op> *)"`
rule per op it runs (`engine_ask.submit`, `workflow.fire`, `workflow.fire_status`, `workflow.fire_wait`,
`workflow.revise`), and runs each op as that exact absolute command: no `cd`, nothing chained. Never bypass:
Grok's classifier blocks the submit, and its rules never expand variables, so a `$HOME/...` command never matches.
Read a `fire: false` mint back from the token file `coordinator-warp-run-tokens/<run_id>.json` under the
machine-local engine records; `dispatch.minted_run` is mutating (`start|abandon`), never a read-back. On Windows
Grok runs pwsh, where a bare `{}` is a script block: pass op params by `--params-file`.
