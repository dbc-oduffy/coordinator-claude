# percolate-hooks/

Percolate behavior is declared, not scripted. `percolate-store.yaml` (this
directory) is the **authoritative behavioral spec**: per target under its
`targets:` map, it declares a `hooks:` list (which named transform phases to
run — e.g. `path-rewrite`, `substitute`, `depersonalize`, `inject`, `guard`),
plus `inject:` and `guards:` entries with their own parameters. Read its own
header comment first.

`publish.py` (engine-repo-resident, resolved via `CLAUDE_KLABAUTER_ROOT`) reads
`percolate-store.yaml` and dispatches the declared phases in-process against
the engine repo's `coordinator_core.percolate` engine (`dispatch_percolate_pre_rsync` /
`_post_rsync` / `_inject` / `_pre_ci`). There is no per-target shell script to
write or discover — the engine is fully declarative.

The `<target>/{pre-rsync,post-rsync,pre-ci}/` subdirectory tree under this
directory (`coordinator-claude/`, `coordinator-claude-toplevel-wiki/`,
`deep-research-claude/`) is vestigial scaffolding — only `.gitkeep`
placeholders (plus one surviving non-script data file,
`publish-native-allowlist.txt`) remain under it. Do not add `.sh` hook
scripts here expecting them to be discovered — nothing reads this tree for
executable content; the engine reads only `percolate-store.yaml`.

## Adding percolate behavior for your own target

1. Register the target (in `publish.targets`, the machine-local registry,
   settings-home-resolved —
   `${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/machine-local/registry.local.toml`,
   falling back to the tracked `registry.toml`).
2. Add a `targets: <your-target>:` entry to `percolate-store.yaml`, naming the
   `hooks:` phases you need and any `inject:`/`guards:` parameters. See the
   `coordinator-claude` entry in that file for a worked example, and its own
   header comment for the schema this validates against
   (`coordinator_core/frontmatter/schemas/percolate-store.schema.json` in
   the engine repo).
3. Dry-run first:
   ```bash
   python "$CLAUDE_KLABAUTER_ROOT/coordinator/bin/publish.py" <your-target> --dry-run
   ```
   (`--dry-run` skips engine-phase dispatch entirely — the engine has no
   non-mutating preview mode.)

## What's shipped today

Every target's behavior lives as declarative entries in
`percolate-store.yaml`'s `targets:` map — see that file for the current
`coordinator-claude` / `coordinator-claude-toplevel-wiki` /
`coordinator-claude-toplevel-install` target definitions (`hooks:`,
`inject:`, `guards:` per target). Patterns are reusable across targets;
specifics (org slugs, allowlist contents, target names) are not.

- **Depersonalize / path-rewrite / substitute** — the `depersonalize`,
  `path-rewrite`, and `substitute` hook phases in `percolate-store.yaml`'s
  `base:` section, driven by the `depersonalize`/`basename_rename` tables
  there. Org-slug pairs remain operator-specific (`~/.claude/setup/
  .percolate-identity`); the pattern is reusable.
- **Inject** — the `inject:` entry under the `coordinator-claude` target in
  `percolate-store.yaml`, for OSS-only skill injection.
- **Guard** — `guards:` entries under the relevant target (e.g.
  `extensionless-shebang-absent`, `no-residual-pattern` kinds), enforcing
  OSS-leak and doctrine-only invariants at the engine level.
- **Toplevel-wiki backup/restore/verify** — the `coordinator-claude-toplevel-wiki`
  target's own `hooks:`/`guards:` entries.

## See also

- `percolate-store.yaml` (this directory) — the authoritative behavioral spec;
  read its own header comment first.
- `publish.py` (engine-repo-resident, `$CLAUDE_KLABAUTER_ROOT/coordinator/bin/publish.py`) — the driver that dispatches these phases.
- `~/.claude/plugins/coordinator/docs/wiki/percolate-setup.md` — full percolation setup procedure (target registration, identity config, first-run walkthrough).
- `~/.claude/plugins/coordinator/docs/wiki/post-sync-hook-doctrine.md` — canonical statement of the touched-list-scoped mutation constraint this mechanism's predecessor was built around; still relevant background for anyone writing a new declarative `hooks:` phase.

## Out of scope (for this README)

- Registering a target in `publish.targets` — see `percolate-setup.md`.
- `publish.py`'s own internals (`$CLAUDE_KLABAUTER_ROOT/coordinator/bin/publish.py`) — see the script's header documentation.
- Identity configuration (`.percolate-identity`) — see the example file in `~/.claude/setup/.percolate-identity.example`.
