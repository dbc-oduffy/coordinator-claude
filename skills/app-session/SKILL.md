---
name: app-session
description: "Census/launch/teardown/validate for a repo's declared app."
version: 1.0.0
allowed-tools: ["Read", "Bash"]
---

# App Session

Stateful lifecycle around a repo-declared app: four named verbs, keyed by target, backed by
per-repo config in `coordinator.local.md`'s `app_session` mapping.

<!-- TEMPLATE: illustrative config shape, not a literal value to invoke -->
```yaml
app_session:
  desktop:
    runtime: electron
    command: pnpm dev
```

Each key is a **target name**; its value carries a `runtime` discriminator (`electron | command |
server | ...`) plus runtime-specific fields. An unrecognised or absent `runtime` degrades to a
plain argv command (electron resolution mechanics: wiki).

## Verbs

One binary, four verbs, routing to the engine's `app_session.census` / `.launch` / `.teardown` /
`.validate` ops; each prints that op's result object verbatim as JSON.

- **census** -- whether a target is running, and (where the resolver supports it) its process/port.
  Read-only. `--key` is optional -- omitted, it lists every persisted handle in the repo.

  Invoke through the `.exe` launcher by absolute path via the PowerShell call operator (Shape W).
  Ladder and shapes: `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`.

  `& "$env:COORDINATOR_SETTINGS_HOME\bin\app-session.exe" census --key <target>`

  `& "$env:COORDINATOR_SETTINGS_HOME\bin\app-session.exe" census`

- **launch** -- starts a target per its config and records it so `census` / `teardown` can find
  it. Launch errors propagate loudly.

  `& "$env:COORDINATOR_SETTINGS_HOME\bin\app-session.exe" launch --key <target>`

- **teardown** -- stops a launched target and clears its state. Matches the specific command line
  it launched, never a blanket kill, because concurrent sessions share these runtimes (wiki).

  `& "$env:COORDINATOR_SETTINGS_HOME\bin\app-session.exe" teardown --key <target>`

- **validate** -- builds, launches, sweeps the declared routes at 1440 and 390 px, screenshots,
  reports, tears down. `--variant`, `--out`, `--wait`. Exit 0 ok, 4 defects, 5 `ok:false` or
  `--wait` lapsed. The result carries the report and screenshots paths. Order of use: validate
  (EM), then the persona UX review (staff-ux) on the screenshots, then the PM. The browser is a
  one-time operator install, never auto-installed; a stage `browser` result carries the install
  command. Config keys and guard rationale: `coordinator/docs/wiki/skills-corpus/app-session-seam.md`.

  `& "$env:COORDINATOR_SETTINGS_HOME\bin\app-session.exe" validate --key <target>`

`--repo-root <path>` is accepted on every verb, defaulting to the git toplevel. Exit 0 covers a
real result and a structured "not configured" one; 2 is a usage error; 3 a transport/op failure.
`launch` without a later `teardown` leaves state behind.

## No config, no effect

A repo declaring no `app_session` keys is not an error: every verb is a silent no-op returning
`{"ok": true, "configured": false, ...}`, exit 0. There is no environment-variable override rung --
an env-settable spawn target is a worse blast radius than an env-settable test command. Targets
resolve via `cs_read_local_md_mapping` (`coordinator_core/resolve_validation_cmd.py`), which
returns `None` for an absent or malformed target.

## Relationship to the platform's `run` skill

`app-session` is the stateful lifecycle complementing the built-in one-shot `run` skill; it is not
named `run*` because `run` is a taken platform primitive.
