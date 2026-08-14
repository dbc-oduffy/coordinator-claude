---
description: "Reverses the coordinator install — full removal or revert to marketplace."
allowed-tools: ["Read", "Bash"]
argument-hint: "[--keep-marketplace] [--purge-operator-config [--force]] [--dry-run]"
---

# Coordinator Uninstall

Reverses the out-of-repo surfaces `/coordinator:install`'s maximalist shape wrote. **Do NOT
hand-run the old snapshot-rollback runbook** for anything this command covers.

## Backing script

No settings-home forwarder for this script — resolve the engine root yourself: `CLAUDE_KLABAUTER_ROOT` env
override, then `REPO_CLAUDE_KLABAUTER` env override, then
`"${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/bin/machine-local" get repos.claude_klabauter`.
None resolving to an existing directory: stop, report "engine root unresolved — set
REPO_CLAUDE_KLABAUTER, or run: `machine-local set repos.claude_klabauter <path>`".

Invoke: `"${COORDINATOR_PYTHON:-python3}" "<resolved-engine-root>/coordinator/bin/coordinator-uninstall.py" [OPTIONS]`.

Every leg is idempotent and fail-loud on ambiguity.

## The judgment half

This command is the mechanical half. Weighing an unexpected surface, when to stop, and the rule
that uncertainty routes to **reported-and-untouched** (never a guessed reversal) lives at:

```
<resolved-engine-root>/docs/wiki/uninstall-agentic-judgment.md
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

<!-- Review: code-reviewer bad07211 — items 11-24 dropped disposition/manual-command detail is a
disposition deletion, not a legitimate wiki relocation; restored from pre-cut history
(a0d82baf5^:coordinator/commands/uninstall.md). Only surrounding rationale stays in wiki. -->

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
14. **Git-config hardening** — REVERSE. Unset `core.checkStat`, `gc.autoDetach`, and the
    Windows-only `help.format`/`web.browser`/`browser.noop.cmd` triple (as a unit — never
    partial), each only when unchanged since install.
15. **Global `git lfs install` filters** — DELIBERATELY-NOT-REVERSED. No manual command offered;
    `git lfs uninstall` is the operator's own call.
16. **Shell-init-guard seam** — REVERSE. Locate the sentinel-guarded resource-cap rc block, strip
    it; fail loud on a hand-modified block.
17. **Operator `~/.claude` git-hook gate regions** — REVERSE, across `pre-commit`, `post-merge`,
    `post-checkout`.
18. **`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` env key** — CANNOT-REVERSE-SAFELY. Manual, only if
    certain nothing else needs it: delete the `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` entry from
    `~/.claude/settings.json`'s `env` block.
19. **`settings.local.json` sibling-plugin seeds** — DELIBERATELY-NOT-REVERSED. Manual per key: set
    the specific `<plugin>@<marketplace>` entry to `false` in `~/.claude/settings.local.json`.
20. **`~/.claude/CLAUDE.md` personal-layer seed** — DELIBERATELY-NOT-REVERSED. No manual command
    offered.
21. **`scaffold_structure` doc-structure output** — DELIBERATELY-NOT-REVERSED. No manual command
    offered.
22. **`coordinator-setup-state.yaml` receipt** — REVERSE via
    `coordinator-setup-state clear setup_concluded`, or delete the file if it holds no other
    milestones.
23. **Discovered-repo `repos.*` entries** — DELIBERATELY-NOT-REVERSED. Not swept by any flag.
24. **Four project-repo writes** — REVERSE, driven by a new install-time record
    (`coordinator.installed_repos`). Interactive: offers removal of `.claude/em-context.md`, the
    `.gitignore` append (only if byte-identical), `coordinator.local.md`, the currency stamp.
    `--non-interactive`: reports, does not touch.

## Uninstall boundary

Blanket-with-provenance: deletes only coordinator-authored artifacts under `<settings-home>/`,
never the root via a blanket sweep. Full detail: wiki.

## Verification after running

Resolve the engine root per § Backing script, then invoke:
`"${COORDINATOR_PYTHON:-python3}" "<resolved-engine-root>/coordinator/lib/check-install-singularity.py"`.

- **Full-remove:** exits 0, "no coordinator tree resolved".
- **Revert-to-marketplace:** exits 0, single canonical tree at `~/.claude/plugins/coordinator-claude`.

Also check `coordinator/lib/resolve-coordinator-clone.py --for-content` / `--for-git-ops`:
full-remove → both fail-loud; revert-to-marketplace → both resolve to the flat tree.

## Running-in-Claude-Code validation

Requires a restart before validating (`settings.json` and plugin wiring are boot-time reads). A
pre-restart `✘` is expected — only a post-restart failure is real. Restart once, then re-run
§ Verification after running.

## See also

- `coordinator/commands/install.md` — the forward install this reverses. A new surface added
  there gets a matching removal step here in the same change.
