---
description: Reverse the coordinator maximalist install — full-remove (default) or revert-to-marketplace. Tested, snapshot-independent, idempotent.
allowed-tools: ["Read", "Bash"]
argument-hint: "[--keep-marketplace] [--purge-operator-config [--force]] [--dry-run]"
---

# Coordinator Uninstall

<!-- spec-backlink: docs/plans/2026-07-08-coordinator-uninstall.md -->

Reverses the out-of-repo surfaces written by `/coordinator:install`'s maximalist shape — the
symmetric counterpart to `install.md`. Where install lays down a shell launch shim, a generated
settings.json hook block, machine-local registry keys, a whoami copy + venv, a `.doe-root`
pointer, `~/.claude/bin/` resolver forwarders, and the `~/.coordinator-claude-settings/`
settings-home tree, this command reverses all of it — tested, idempotent, and **not** dependent on
any dated snapshot tarball. See `docs/plans/2026-07-08-coordinator-uninstall.md § Authoritative
surface list` for the full #1–#10 surface-to-removal-method mapping this command implements.

**Do NOT hand-run the old snapshot-rollback runbook**
(`coordinator/docs/wiki/external-plugin-live-resolution.md § Adoption — W4.2 cutover`) for
anything this command now covers — that runbook is one-machine, one-window, and expires with its
snapshot; this command reconstructs the reverse from first principles on any machine.

## Backing script

```bash
bash "${CLAUDE_PLUGIN_ROOT}/bin/coordinator-uninstall.sh" [OPTIONS]
```

All filesystem/registry targets are resolved from environment overrides — `${CLAUDE_HOME:-$HOME}`,
`${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}`,
`${MACHINE_LOCAL_REGISTRY_DIR}` — never a hardcoded real-user path. Each leg is idempotent
(re-running is a no-op) and **fail-loud on ambiguity** — a leg that cannot determine what to remove
stops with a remediation message rather than guessing.

## End-states — full-remove (default) vs. revert-to-marketplace

**PM-ratified semantics (2026-07-08): the default is full-remove.** Bare `coordinator-uninstall.sh`
removes coordinator entirely. Revert-to-marketplace is the secondary, opt-in option.

| End-state | Invocation | Result |
|---|---|---|
| **Full-remove (default)** | `coordinator-uninstall.sh` | Every surface #1–#10 reversed. Plugin wiring cleared (source at `<DoE>/coordinator` left intact — this is an uninstall of the *install*, not a deletion of the DoE repo). `check-install-singularity.sh` resolves "no coordinator tree resolved". `~/.local/bin/claude-doe` wrapper and all shim/shell surfaces removed — bare `claude` no longer resolves coordinator at all. |
| **Revert-to-marketplace** | `coordinator-uninstall.sh --keep-marketplace` | Re-registers the flat `~/.claude/plugins/coordinator-claude` marketplace plugin and clears `live_path` (so `check-install-singularity.sh` CHECK 4 does not see two trees). Bare `claude` works via the normal marketplace-plugin path, zero shim. `check-install-singularity.sh` resolves the single flat tree, with `settings.json` / `settings.local.json` / `known_marketplaces.json` agreeing on the flat path (CHECK 5 tri-file contract). |

Both end-states reverse the shell-shim/wrapper family (#4a/#4b/#4c/#10) and the settings.json
generated hook block (#2) — a maximalist install's launch surface has no purpose once the plugin
is no longer resolved via `--plugin-dir`.

## Flags

| Flag | Effect |
|---|---|
| *(none)* | Full-remove (default). Reverses every surface #1–#10; leaves no coordinator tree resolvable. |
| `--keep-marketplace` | Revert-to-marketplace instead of full-remove: re-registers the flat `~/.claude/plugins/coordinator-claude` tree and clears `live_path`. <!-- Review: code-reviewer (F3) — inlined the script's own usage() disposition so a reader doesn't need to open the plan's surface table for #5/#7. --> Machine-local dir and `~/.claude/bin` forwarders are preserved (other surfaces may still depend on them post-revert); `.doe-root` is REMOVED (it is a resolution-shadowing pointer that would otherwise outrank the re-registered flat tree and defeat the revert). See the plan's surface table for the full #5/#7 accounting. |
| `--purge-operator-config` | Also purge surface #9 (`coordinator-identity.yaml`, `working-repos.yaml`, `CLAUDE.local.md`) — **not removed by default.** Conservative preserve-by-default: a bare uninstall never touches operator identity. Fails loud on a hand-edited file (re-render + byte-compare) unless combined with `--force`. |
| `--force` | Fail-safe override for `--purge-operator-config` — required to remove a file that differs from its fresh re-render (possibly hand-edited). Has no effect without `--purge-operator-config`. |
| `--dry-run` | Prints the ordered leg plan and performs **zero filesystem writes and zero registry-key clears** — every mutating call is skipped entirely, not run in some "preview" mode. Byte-identical `$HOME` before/after. |
| `-h`, `--help` | Show usage and exit 0. |

The operator-config boundary (`--purge-operator-config`) is a conservative default deliberately —
full-remove is already the default end-state, so a bare `uninstall` hits
`~/.claude/{coordinator-identity.yaml,working-repos.yaml,CLAUDE.local.md}` on every run if it were
not gated; nuking operator identity by default on a routine uninstall would be surprising. See plan
§ Decisions flagged for review / PM #1.

## What gets reversed

Full surface-to-removal-method table: `docs/plans/2026-07-08-coordinator-uninstall.md §
Authoritative surface list` (also mirrored, disk-verified, in `tasks/coordinator-uninstall/surface-map.md`).
Summary:

1. **Plugin wiring** — mirror registry keys (full-remove: cleared; revert: flat plugin re-registered, `live_path` cleared).
2. **`settings.json` generated hook block** — inverse-strip via the shared identity key (`coordinator/lib/settings-hook-identity.sh`), preserving any non-generated hooks (e.g. `portability-guard-hook`, `touch-session-sentinel.sh`).
3. **Machine-local registry** — coordinator keys cleared (`plugin.mirrors.coordinator-claude.*`, `coordinator.python`, `coordinator.whoami_src`, `repos.doe_claude`); full-remove also drops the settings-home `machine-local/` dir + compat symlink (see item 8's boundary note — not a whole-tree drop).
4. **Shell launch shim** — (a) owned shim file, (b) `$SHELL`-detected rc source line, (c) legacy `~/.bashrc` block — all removed; fails loud on a hand-modified block.
5. **whoami + venv** — settings-home dirs + compat symlink removed (full-remove); revert-to-marketplace disposition per plan § Decisions flagged #2.
6. **`.doe-root` pointer** — removed (full-remove); not needed once the plugin isn't resolved via the pointer tier.
7. **`~/.claude/bin/` forwarders** — coordinator-owned names removed individually — **never** a blanket `rm -rf ~/.claude/bin/` (the directory holds harness-native and other-plugin entries).
8. **Settings-home tree** (`~/.coordinator-claude-settings/`) — **provenance-scoped, NOT a blanket `rm -rf`** (full-remove only): removes only the coordinator-authored allowlist under the tree (`machine-local/`, `bin/`, `settings-manifest.md`, `coordinator-whoami/`, `.coordinator-venv/`, `state/handoffs`), then `rmdir`'s the tree root ONLY if it is now empty. See § Uninstall boundary below.
9. **Operator config** — preserved by default; `--purge-operator-config` opt-in (see Flags above).
10. **`claude-doe` wrapper** (`${CLAUDE_HOME:-$HOME}/.local/bin/claude-doe`) — removed in both end-states; marketplace-plugin operation uses bare `claude`, not the wrapper.

## Uninstall boundary

Coordinator uninstall follows **blanket-with-provenance**: it deletes only coordinator-authored
artifacts under `<settings-home>/` (the allowlist enumerated in item 8 above), never the
`<settings-home>` root itself via a blanket sweep. Any `<settings-home>/<repo-id>/` durable-data
subtree owned by a consumer (e.g. example-cockpit-repo's shipped `store.db`, project-rag's future
plane data) is preserved by default — it is not on the coordinator's own allowlist, so it survives
full-remove untouched, and `<settings-home>` itself is left in place (not `rmdir`'d) as long as any
such subtree remains. Full contract: `agent-install-contract.md § Uninstall boundary`.

A consumer MAY additionally register an **optional per-`<repo-id>` keepset** to protect
coordinator-adjacent paths it wants preserved beyond the blanket default — this is a narrowing on
top of blanket-with-provenance, not the primary mechanism: the blanket default already protects an
**unregistered** consumer's durable data, so no consumer is required to register anything for its
`<settings-home>/<repo-id>/` subtree to survive uninstall.

## Verification after running

```bash
bash "${CLAUDE_PLUGIN_ROOT}/lib/check-install-singularity.sh"
```

- **Full-remove:** exits 0, "no coordinator tree resolved (fresh install or all paths absent)".
- **Revert-to-marketplace:** exits 0, single canonical tree at `~/.claude/plugins/coordinator-claude`, with the tri-file contract (CHECK 5) satisfied — `settings.json`, `settings.local.json`, and `known_marketplaces.json` all agreeing on the flat path.

Also check resolver-mode behavior (`resolve-coordinator-clone.sh --for-content` / `--for-git-ops`):
full-remove → both fail-loud (no stale-cache fallthrough); revert-to-marketplace → both resolve to
the flat tree.

## Running-in-Claude-Code validation (required, not just script-green)

<!-- AC11: docs/plans/2026-07-08-coordinator-uninstall.md -->
<!-- Review: code-reviewer (F2) — added an explicit AC11 marker so this section is greppable
     back to its acceptance criterion without opening the plan. -->

Per `coordinator/docs/wiki/install-surface-completeness.md § Running-in-Claude-Code` (plugin-root
wiki — this section has no repo-root copy; per `cross-repo-citation-conventions.md § When to
qualify`), a green script run is
**not** the same as a validated live boot. **The uninstall is itself a restart-requiring
operation** — it rewrites `settings.json`, removes the shim/wrapper launch surface, and flips
plugin wiring, all of which Claude Code only re-reads at boot. Per the **Restart-batch doctrine**
("order restart-needs first, emit once"), treat the whole uninstall as ONE consolidated
restart-need, not a sequence of ad-hoc reboots — run the uninstall, restart once, then validate.

After the single restart, apply the **four-class discriminator** (live/validated, pending-settle,
restart-gated-expected, configured-but-broken) rather than treating any pre-restart `✘` as a
failure:

- **Full-remove:** a fresh boot must resolve **cleanly-absent** — no coordinator plugin, no skills,
  no hooks firing. A pre-restart session still showing coordinator behavior is expected
  (restart-gated-expected, not yet a verdict); it becomes **configured-but-broken** only if
  coordinator behavior persists in a genuinely fresh boot *after* the restart.
- **Revert-to-marketplace:** a fresh boot must resolve the **flat plugin** — coordinator skills and
  hooks working exactly as they did pre-maximalist-cutover, loaded from
  `~/.claude/plugins/coordinator-claude`, not from the DoE clone. Same discriminator: don't call it
  broken until it's `✘` post-restart.

This manual boot validation is spinoff-gated — it requires a live fresh Claude Code boot the
uninstall script cannot perform on its own, so it is the final step after the script and
`check-install-singularity.sh` both report green.

## See also

- `coordinator/commands/install.md` — the forward install this reverses. Surface list kept in
  lockstep per `coordinator/docs/wiki/external-plugin-live-resolution.md § Install/uninstall surface
  symmetry — canonical cross-links`.
- `coordinator/docs/wiki/external-plugin-live-resolution.md § Adoption — W4.2 cutover` — historical
  hand-run snapshot-rollback runbook, retained for the pre-2026-07-08 window it covers; this command
  is the tested, snapshot-independent replacement for anything within its scope.
- `docs/plans/2026-07-08-coordinator-uninstall.md` — full plan, acceptance criteria, and chunk
  breakdown for this capability.
