---
name: app-session
description: "Census/launch/teardown for a repo's declared app."
version: 1.0.0
allowed-tools: ["Read", "Bash"]
---

# App Session

Stateful lifecycle around a repo-declared app: three named verbs, keyed by target, backed by
per-repo config declared in `coordinator.local.md`'s `app_session` mapping.

<!-- TEMPLATE: illustrative config shape, not a literal value to invoke -->
```yaml
app_session:
  desktop:
    runtime: electron
    command: pnpm dev
```

Each key under `app_session` is a **target name** (`desktop` above); its value is an object
carrying a `runtime` discriminator (`electron | command | server | ...`) plus runtime-specific
fields. An unrecognised or absent `runtime` degrades to a plain argv command with no resolution
step -- the electron-specific resolution mechanics are out of this skill's scope (wiki).

## Verbs

Each verb dispatches through the `app-session` trampoline, one binary three verbs, which routes
to the control-plane engine's `app_session.census` / `app_session.launch` / `app_session.teardown`
ops and prints that op's own result object verbatim as JSON.

- **census** -- reports the current state of a target: whether it is running, and (where the
  runtime resolver supports it) which process/port it occupies. Read-only; makes no state
  change. `--key` is optional -- omitted, it lists every persisted handle in the repo.

  Invoke through the `.exe` launcher by absolute path via the PowerShell call operator (Shape W).
  Ladder and shapes: `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`.

  `& "$env:COORDINATOR_SETTINGS_HOME\bin\app-session.exe" census --key <target>`

  `& "$env:COORDINATOR_SETTINGS_HOME\bin\app-session.exe" census`

- **launch** -- starts a target per its `app_session` config and records that it is running, so a
  later `census` or `teardown` call can find it. Fails loudly on a launch error -- this verb's
  failures propagate rather than being swallowed.

  `& "$env:COORDINATOR_SETTINGS_HOME\bin\app-session.exe" launch --key <target>`

- **teardown** -- stops a previously launched target and clears its recorded state. Matches the
  specific command line it launched rather than a blanket process kill, because this machine
  routinely runs concurrent sessions against the same runtimes (wiki).

  `& "$env:COORDINATOR_SETTINGS_HOME\bin\app-session.exe" teardown --key <target>`

`<target>` is the `app_session` mapping key (`desktop` above). `--repo-root <path>` is accepted on
every verb but normally omitted -- it defaults to the git toplevel. Exit code 0 covers both a real
result and a structured "not configured" one (see § No config, no effect); 2 is a usage error; 3
is a transport/op failure.

`launch` without a later `teardown` leaves state behind for `census` and `teardown` to find.

## Config resolution

Each op resolves its target via `cs_read_local_md_mapping(repo_root, key) -> dict`
(`coordinator_core/resolve_validation_cmd.py`), not `cs_read_local_md_key`, which cannot read the
nested per-target mapping. It returns a bare `dict` for a present, well-formed target and `None`
for an absent or malformed one; callers turn `None` into the structured "not configured" result
below rather than raising.

## No config, no effect

A repo declaring no `app_session` keys is not an error: every verb degrades to a silent no-op,
because `app_session` is opt-in, unlike `fast_test_cmd`, which fails loud at a cadence gate
(`validate/SKILL.md`). The ops return `{"ok": true, "configured": false, ...}`, exit 0.

`app_session` carries no environment-variable override rung: the configured value spawns a
process, and an env-settable spawn target is a worse blast radius than an env-settable test
command. Resolution reads only `coordinator.local.md`.

## Relationship to the platform's `run` skill

`app-session` complements the built-in `run` skill (one-shot "start it and look at it"): it is the
stateful census/launch/teardown lifecycle with per-repo config, and is not named `run*` because
`run` is a taken platform primitive. Registration with `run` is unconfirmed.
