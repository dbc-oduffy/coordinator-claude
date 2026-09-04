---
description: "Reverses the coordinator install — full removal or revert to marketplace."
allowed-tools: ["Read", "Bash"]
argument-hint: "[--keep-marketplace] [--purge-operator-config [--force]] [--dry-run]"
---

# Coordinator Uninstall

Reverses the out-of-repo surfaces `/coordinator:install`'s maximalist shape wrote. **Do NOT
hand-run the old snapshot-rollback runbook** for anything this command covers.

## Backing script

No settings-home forwarder for this script — resolve the engine root with the ratified resolver.
Never hand-roll a precedence chain here: a second copy of the ladder is a second thing to drift.

```
"${COORDINATOR_PYTHON:-python3}" "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/_engine_root.py"
```

- PowerShell hosts: `& $env:COORDINATOR_PYTHON "$env:CLAUDE_PLUGIN_ROOT\hooks\scripts\_engine_root.py"`
  (`python3` when unset).

It prints the resolved root on stdout and owns the whole ladder: the live-tree env overrides
first (the manual test-and-execute carve-out), then the published engine mirror — which is the
ordinary answer on a healthy box. **The engine root is the published mirror, not an authoring
checkout**; an authoring tree moves under concurrent sessions, so resolving against one makes the
engine a moving target.

Empty output: stop, report "engine root unresolved" — never guess a path. (The resolver
prints an empty line on a total miss rather than failing, so empty output IS the miss
signal; do not wait for a non-zero exit it does not produce.)

Python interpreter: `COORDINATOR_PYTHON` env override, else `python3`.

Invoke (PowerShell): `& $env:COORDINATOR_PYTHON "<resolved-engine-root>\coordinator\bin\coordinator-uninstall.py" [OPTIONS]`
(`python3` when unset).

Every leg is idempotent and fail-loud on ambiguity.

## The judgment half

This command is the mechanical half. Weighing an unexpected surface, when to stop, and the rule
that uncertainty routes to **reported-and-untouched** (never a guessed reversal) lives at:

```
${CLAUDE_PLUGIN_ROOT}/docs/wiki/uninstall-agentic-judgment.md
```

Read it whenever a run turns up a surface nothing below covers.

## End-states

**Default is full-remove.**

| End-state | Invocation | Result |
|---|---|---|
| **Full-remove** (default) | `coordinator-uninstall.py` | `check-install-singularity.py` resolves "no coordinator tree resolved". Bare `claude` does not resolve coordinator at all. |
| **Revert-to-marketplace** | `coordinator-uninstall.py --keep-marketplace` | Re-registers the flat `~/.claude/plugins/coordinator-claude` marketplace plugin, clears `live_path`. `check-install-singularity.py` resolves the single flat tree, CHECK 5 tri-file contract satisfied. |

## Flags

| Flag | Effect |
|---|---|
| *(none)* | Full-remove. |
| `--keep-marketplace` | Revert-to-marketplace: re-registers the flat tree, clears `live_path`, removes `.doe-root`. |
| `--purge-operator-config` | Also purges `coordinator-identity.yaml` / `working-repos.yaml` (not touched by default). Fails loud on a hand-edited file unless combined with `--force`. |
| `--force` | Required alongside `--purge-operator-config` to remove a hand-edited file. No effect alone. |
| `--dry-run` | Prints the ordered leg plan for THIS machine — zero writes, zero registry clears. Run this first. |
| `-h`, `--help` | Usage, exit 0. |

## What gets reversed

`--dry-run` lists the current surfaces this command reverses and how. Per-surface rationale: wiki.

Roughly nineteen further install surfaces have no landed removal leg yet — every entry below is a
specification for work not yet done, written present-tense to describe the intended contract, not
current behaviour. Until each leg ships, treat it as a manual-cleanup checklist item. Disposition
set: `REVERSE`, `DELIBERATELY-NOT-REVERSED`, `CANNOT-REVERSE-SAFELY`. Rationale for each: wiki
(`uninstall-reversal-rationale`).

<!-- engine-gap: field=uninstall.item_disposition producer=unknown memo=2026-08-27-claude-klabauter-em-doe-unmarked-obligations-and-four-lost-markers.md -->

11. **Windows Defender process exclusions** — CANNOT-REVERSE-SAFELY. Roll back manually, elevated,
    per resolved toolchain path: `Remove-MpPreference -ExclusionProcess "<path>"` for each of
    `bash.exe`, `git.exe`, `sh.exe`, `python.exe`, `pythonw.exe` that was excluded (no-op if never
    excluded).
12. **`~/.ssh/config` rewrite + global SSH commit signing** — REVERSE. If the file pre-existed:
    restore from the PID-suffixed backup (`config.coordinator-bak.<pid>`, located by glob — fail
    loud if missing, never reconstruct). If it did not pre-exist: delete the installer-created
    file. Then `git config --global --unset` the signing keys the installer set (`gpg.format`,
    `user.signingkey`, `commit.gpgsign`, `tag.gpgsign`, `gpg.ssh.program`,
    `gpg.ssh.allowedSignersFile`), each only if unchanged since install, and strip the appended
    line from `~/.config/git/allowed_signers`.
13. **`origin` remote SSH flip** — DELIBERATELY-NOT-REVERSED. Manual:
    `git remote set-url origin <original-https-url>`.
14. **Git-config hardening** — REVERSE. Unset the machine-wide keys — `core.checkStat` and the
    Windows-only `help.format`/`web.browser`/`browser.noop.cmd` triple (as a unit — never
    partial) — each only when unchanged since install. `gc.auto`, `maintenance.strategy`/
    `maintenance.auto`, and `maintenance.prefetch.enabled` are NOT global-unset here: per the
    2026-08-07 per-key scope ruling, these are per-repo keys, each reached through the Phase 3
    git-perf-config fleet sweep across every registered worktree, never through a `--global`
    line.
15. **Global `git lfs install --skip-repo` filters** — DELIBERATELY-NOT-REVERSED. Config-only (never
    touched repo hooks — Phase 1's git-LFS step never runs a repo-level `git lfs install`, only this
    global-config form). No manual command offered; `git lfs uninstall` is the operator's own call.
16. **Shell-init-guard seam** — REVERSE. Locate the sentinel-guarded resource-cap rc block, strip
    it; fail loud on a hand-modified block.
17. **Operator `~/.claude` git-hook gate regions** — REVERSE, across `pre-commit`, `post-merge`,
    `post-checkout`.
18. **`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` env key** — CANNOT-REVERSE-SAFELY. Manual, only if
    certain nothing else needs it: delete the `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` entry from
    `~/.claude/settings.json`'s `env` block.
19. **`settings.local.json` sibling-plugin seeds** — DELIBERATELY-NOT-REVERSED. Manual per key: set
    the specific `<plugin>@<marketplace>` entry to `false` under `~/.claude/settings.local.json`'s
    `enabledPlugins` block.
20. **`~/.claude/CLAUDE.md` personal-layer seed** — DELIBERATELY-NOT-REVERSED. No manual command
    offered.
21. **`coordinator-setup-state.yaml` receipt** — REVERSE via
    `coordinator-setup-state clear setup_concluded`, or delete the file if it holds no other
    milestones.
22. **Discovered-repo `repos.*` entries** — DELIBERATELY-NOT-REVERSED. Not swept by any flag:
    `repos.*` is general-purpose sibling-repo addressing infra, useful independent of
    coordinator, and other tooling may already depend on entries seeded here.
23. **Four project-repo writes** — REVERSE, driven by a new install-time record
    (`coordinator.installed_repos`). Interactive: offers removal of `.claude/em-context.md`, the
    `.gitignore` append (only if byte-identical), `coordinator.local.md`, the currency stamp.
    `--non-interactive`: reports, does not touch.
24. **Git Bash fast-profile block** (Windows) — CANNOT-REVERSE-SAFELY from here: the block lives in
    Git-for-Windows' own `/etc/profile`, inside the install root, so removing it needs elevation.
    Roll back manually from an elevated terminal:
    `python "<plugin-root>\templates\bin\install-git-bash-fast-profile.py" --uninstall` — it strips
    the block and round-trips the file to byte-identical stock (no-op if never installed).
25. **Engine-side install state** — REVERSE, driven by the control-plane engine's own uninstall
    door — not a leg this script drives itself. Confirm the engine-side door ran (or run it) as
    part of a full reversal; this repo's script covers only the doctrine-plane surfaces above.
26. **`~/.local/bin` PATH block** — REVERSE. `install-substrate.py` Step 3e appends a
    sentinel-guarded block putting `~/.local/bin` on PATH for the standalone `claude` CLI. Strip
    the sentinel-guarded region from the interactive rc; fail loud on a hand-modified block, and
    leave `~/.local/bin` itself and anything in it alone — the directory is the operator's, not
    coordinator's.
27. **Machine and contributor slugs** — REVERSE. Clear `coordinator.machine_slug` and
    `coordinator.contributor_slug` from the machine-local registry, each only if unchanged
    since install.
28. **Step Zero environment normalization** — CANNOT-REVERSE-SAFELY. `normalize-env.py` installs
    toolchains (uv, Python) and sets global `git config core.longpaths` that the operator's other
    work may now depend on; nothing here removes them. It writes TWO backup shapes and
    `normalize-env.py --restore <backup-file>` treats them differently: the `.bash_profile.coordinator-backup.<ts>`
    leg is copied back automatically, while the `.coordinator-env-backup.<ts>` PATH/pymanager leg
    only PRINTS the commands to run in your parent shell — you still execute those by hand.
    Both backup paths are printed at install time.
29. **`check-gitignore-template-drift` appended rules** — DELIBERATELY-NOT-REVERSED. Report-only
    by default; only mutates behind explicit `--apply` (appends missing `.gitignore` rules verbatim
    from the template) and never runs `git rm --cached` itself. An appended ignore rule is not
    something uninstall retracts.
30. **`${CLAUDE_HOME:-$HOME}/.claude/agents/navi.md` role file** — REVERSE, on the DEFAULT
    full-remove path (not gated behind `--purge-operator-config`): the file carries zero operator
    content and is inert without the plugin. Byte-compare against the shipped
    `templates/agents/navi.md` (no substitutions, so a plain compare — same precedent as
    `_uninstall_purge_operator_config`'s use for `coordinator-identity.yaml` / `CLAUDE.local.md`).
    Identical: unlink. Differs, or the shipped template cannot be read: `cannot-reverse-safely` —
    report and leave, with a manual removal command in the message, never a silent skip.
    Report-and-leave does not fail the leg; an `OSError` on the unlink does. The compare depends
    on this leg running while the shipped template is still readable — see `uninstall_legs.py`
    for the actual leg order, not restated here. No `WriteSurfaceEntry`, no receipt entry: that
    manifest describes what INSTALL writes, and this leg only reverses another plane's install —
    a consumer of that manifest, never a producer, so it stays out of the denominator.

## Uninstall boundary

Blanket-with-provenance: deletes only coordinator-authored artifacts under `<settings-home>/`,
never the root via a blanket sweep. Full detail: wiki.

## Verification after running

Resolve the engine root per § Backing script, then invoke (PowerShell):
`& $env:COORDINATOR_PYTHON "<resolved-engine-root>\coordinator\lib\check-install-singularity.py"`
(`python3` in place of `$env:COORDINATOR_PYTHON` when unset; POSIX hosts:
`"${COORDINATOR_PYTHON:-python3}" "<resolved-engine-root>/coordinator/lib/check-install-singularity.py"`).

- **Full-remove:** exits 0, "no coordinator tree resolved".
- **Revert-to-marketplace:** exits 0, single canonical tree at `~/.claude/plugins/coordinator-claude`.

Also check `coordinator/lib/resolve-coordinator-clone.py --for-content` / `--for-git-ops`:
full-remove → both fail-loud; revert-to-marketplace → both resolve to the flat tree.

## Running-in-Claude-Code validation

Requires a restart before validating (`settings.json` and plugin wiring are boot-time reads). A
pre-restart `✘` is expected — only a post-restart failure is real. Restart once, then re-run
§ Verification after running.

## See also

- `coordinator/commands/install.md` — the forward install this reverses, kept in lockstep with it.
  A new surface added there gets a matching removal step here in the same change.
