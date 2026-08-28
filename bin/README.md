# coordinator/bin

Purpose: the place someone deciding a new script's shape actually looks,
before they add one — a `coordinator/bin/<name>.py` script here has TWO
consumers, and dropping either shape breaks one of them.

## Two consumers, one script

1. **The assembler**, which imports the module and calls `main()`
   in-process (via `coordinator_core.ceremony_common.cli_dispatch` for the
   `workday_complete`/`workstream_complete`/`workweek_complete` trio, or
   the assembler's own in-process handler for others).
2. **Agents**, who invoke the script by name at a prompt, instructed to do
   so by a skill.

The `argparse` main and the `.cmd` launcher exist for the second consumer
and are REQUIRED — an assembler never touches either, but an agent
invoking the script by name at a prompt does, every time.

Checkable live examples of the second consumer (in the coordinator-claude
skills tree, `DoE-claude/coordinator/skills/`, not this repo):

- `archive-stamp-cli claim-handoff <path>` — `skills/pickup`
- `coordinator-queue-append --schema …` — `skills/bug-sweep`,
  `skills/debt-triage`, `skills/learn-lessons`, `skills/quick-wrap`
- `archive-stamp-cli resolve-memo` — `skills/workstream-start`

An earlier investigation concluded these were vestigial (54 of 54, no
consumer outside the assembler); that reading is REFUTED — the probe
filtered out `.md` files, which is exactly where the second consumer is
recorded. Do not re-derive that error: keep the `argparse` main and the
`.cmd` launcher on every script here.

See `docs/reference/cli-directive-execution-models.md` for the longer
form: both dispatch-table populations, which assemblers are in each, the
absent-producer table, and the measured cost ladder for going from a cold
per-directive spawn to a warm in-process call.
