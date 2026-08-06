---
description: "Reverses the coordinator install — full removal or revert to marketplace."
allowed-tools: ["Read", "Bash"]
argument-hint: "[--keep-marketplace] [--purge-operator-config [--force]] [--dry-run]"
---

# Coordinator Uninstall

Reverses the out-of-repo surfaces written by `/coordinator:install`'s maximalist shape — the
symmetric counterpart to `install.md`. Where install lays down a shell launch shim, a generated
settings.json hook block, machine-local registry keys, a whoami copy + venv, a `.doe-root`
pointer, `~/.claude/bin/` resolver forwarders, and the `~/.coordinator-claude-settings/`
settings-home tree, this command reverses all of it — tested, idempotent, and **not** dependent on
any dated snapshot tarball. See § What gets reversed below for the full #1–#10
surface-to-removal-method mapping this command implements.

**Do NOT hand-run the old snapshot-rollback runbook** for
anything this command now covers — that runbook is one-machine, one-window, and expires with its
snapshot; this command reconstructs the reverse from first principles on any machine.

## Backing script

`coordinator-uninstall.py` has no settings-home forwarder (it is a rarely-invoked, high-blast-radius
operation deliberately kept off the `${COORDINATOR_SETTINGS_HOME}/bin/` forwarder set), so
this command resolves the `claude-klabauter` root directly rather than through a forwarder. Resolution
order: `CLAUDE_KLABAUTER_ROOT` env override, then `REPO_CLAUDE_KLABAUTER` env override, then the settings-home
machine-local registry via
`"${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/bin/machine-local" get repos.claude_klabauter`
— the same registry key `install.md`'s own Step Zero preflight already requires to resolve before
install can run, so this lookup is safe to assume succeeds on any machine coordinator was installed
on. If none of the three resolve to an existing directory, stop and report: "claude-klabauter root
unresolved (checked CLAUDE_KLABAUTER_ROOT, REPO_CLAUDE_KLABAUTER, and the settings-home machine-local registry)
— set REPO_CLAUDE_KLABAUTER, or run: `machine-local set repos.claude_klabauter <path>`".

Once resolved, invoke:
`"${COORDINATOR_PYTHON:-python3}" "<resolved-claude-klabauter-root>/coordinator/bin/coordinator-uninstall.py" [OPTIONS]`.

All filesystem/registry targets are resolved from environment overrides — `${CLAUDE_HOME:-$HOME}`,
`${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}`,
`${MACHINE_LOCAL_REGISTRY_DIR}` — never a hardcoded real-user path. Each leg is idempotent
(re-running is a no-op) and **fail-loud on ambiguity** — a leg that cannot determine what to remove
stops with a remediation message rather than guessing.

## The judgment half — read before deciding a surface you did not expect

This command is the mechanical half. The agentic half — how to weigh a surface, when to stop, and
the rule that uncertainty routes to **reported-and-untouched** rather than to a guessed reversal —
lives engine-side, not here. Resolve the engine root exactly as § Backing script above does, then
read:

```
<resolved-claude-klabauter-root>/docs/wiki/uninstall-agentic-judgment.md
```

Read it when a run turns up a surface no disposition below covers.

It is deliberately prose and deliberately does **not** enumerate surfaces: the facts are mechanized
in the write-surface manifest (`write_surface.emit_manifest`), and a page that re-listed them would
be a third transcribed copy of a source-of-truth — the same copy-drift defect item 17 was. A test on
the engine side derives a recognizer per declared kind from the manifest and asserts the page
matches none of them, so it cannot silently become that copy. **Do not mirror its content here.**

## End-states — full-remove (default) vs. revert-to-marketplace

**The default is full-remove.** Bare `coordinator-uninstall.py`
removes coordinator entirely. Revert-to-marketplace is the secondary, opt-in option.

| End-state | Invocation | Result |
|---|---|---|
| **Full-remove (default)** | `coordinator-uninstall.py` | Every surface #1–#10 reversed. Plugin wiring cleared (source at `<DoE>/coordinator` left intact — this is an uninstall of the *install*, not a deletion of the DoE repo). `check-install-singularity.py` resolves "no coordinator tree resolved". `~/.local/bin/claude-doe` wrapper and all shim/shell surfaces removed — bare `claude` no longer resolves coordinator at all. |
| **Revert-to-marketplace** | `coordinator-uninstall.py --keep-marketplace` | Re-registers the flat `~/.claude/plugins/coordinator-claude` marketplace plugin and clears `live_path` (so `check-install-singularity.py` CHECK 4 does not see two trees). Bare `claude` works via the normal marketplace-plugin path, zero shim. `check-install-singularity.py` resolves the single flat tree, with `settings.json` / `settings.local.json` / `known_marketplaces.json` agreeing on the flat path (CHECK 5 tri-file contract). |

Both end-states reverse the shell-shim/wrapper family (#4a/#4b/#4c/#10) and the settings.json
generated hook block (#2) — a maximalist install's launch surface has no purpose once the plugin
is no longer resolved via `--plugin-dir`.

## Flags

| Flag | Effect |
|---|---|
| *(none)* | Full-remove (default). Reverses every surface #1–#10; leaves no coordinator tree resolvable. |
| `--keep-marketplace` | Revert-to-marketplace instead of full-remove: re-registers the flat `~/.claude/plugins/coordinator-claude` tree and clears `live_path`. Machine-local dir and `~/.claude/bin` forwarders are preserved (other surfaces may still depend on them post-revert); `.doe-root` is REMOVED (it is a resolution-shadowing pointer that would otherwise outrank the re-registered flat tree and defeat the revert). See the plan's surface table for the full #5/#7 accounting. |
| `--purge-operator-config` | Also purge surface #9 (`coordinator-identity.yaml`, `working-repos.yaml`) — **not removed by default.** Conservative preserve-by-default: a bare uninstall never touches operator identity. Fails loud on a hand-edited file (re-render + byte-compare) unless combined with `--force`. |
| `--force` | Fail-safe override for `--purge-operator-config` — required to remove a file that differs from its fresh re-render (possibly hand-edited). Has no effect without `--purge-operator-config`. |
| `--dry-run` | Prints the ordered leg plan and performs **zero filesystem writes and zero registry-key clears** — every mutating call is skipped entirely, not run in some "preview" mode. Byte-identical `$HOME` before/after. |
| `-h`, `--help` | Show usage and exit 0. |

The operator-config boundary (`--purge-operator-config`) is a conservative default deliberately —
full-remove is already the default end-state, so a bare `uninstall` hits
`~/.claude/{coordinator-identity.yaml,working-repos.yaml}` on every run if it were
not gated; nuking operator identity by default on a routine uninstall would be surprising. See plan
§ Decisions flagged for review / PM #1.

## What gets reversed

Full surface-to-removal-method table:

1. **Plugin wiring** — mirror registry keys (full-remove: cleared; revert: flat plugin re-registered, `live_path` cleared). **Revert-to-marketplace's re-registration of `~/.claude/plugins/coordinator-claude` is NOT a reversal of any install write** — install.md § "3.5d — Thin `~/.claude/plugins/` shape (design note — no mutation)" states that tree is *never* written under the maximalist shape ("Anti-pattern ... runtime-proven FAIL"). Revert-to-marketplace instead deliberately constructs the pre-maximalist marketplace shape as an alternate, independently-valid end-state; it is documented here as its own end-state (§ End-states table above), not folded into the "reverses what install wrote" framing.
2. **`settings.json` generated hook block** — inverse-strip via the shared identity key (`coordinator/lib/settings_hook_identity.py`, now resolved from the claude-klabauter root per the canonical `_cc_claude_klabauter` seam — ported from the `.sh` original and migrated out of this repo), preserving any non-generated hooks (e.g. `portability-guard-hook`, `touch-session-sentinel.sh`).
3. **Machine-local registry** — coordinator keys cleared (`plugin.mirrors.coordinator-claude.*`, `coordinator.python`, `coordinator.whoami_src`, `repos.doe_claude`, `coordinator.machine_slug`, `coordinator.contributor_slug`); full-remove also drops the settings-home `machine-local/` dir + compat symlink (see item 8's boundary note — not a whole-tree drop). `coordinator.whoami_src` is set by `install-substrate.py` (install.md § "Step 1 — Run install-substrate helper") without being named there by key — this item is the citation for it on the uninstall side; the key is swept regardless as part of the same machine-local clear.
4. **Shell launch shim** — (a) owned shim file, (b) `$SHELL`-detected rc source line, (c) legacy `~/.bashrc` block — all removed; fails loud on a hand-modified block.
5. **whoami + venv** — settings-home dirs + compat symlink removed (full-remove); revert-to-marketplace disposition per plan § Decisions flagged #2.
6. **`.doe-root` pointer** — removed (full-remove); not needed once the plugin isn't resolved via the pointer tier.
7. **`~/.claude/bin/` forwarders** — coordinator-owned names removed individually — **never** a blanket `rm -rf ~/.claude/bin/` (the directory holds harness-native and other-plugin entries).
8. **Settings-home tree** (`~/.coordinator-claude-settings/`) — **provenance-scoped, NOT a blanket `rm -rf`** (full-remove only): removes only the coordinator-authored allowlist under the tree (`machine-local/`, `bin/`, `settings-manifest.md`, `coordinator-whoami/`, `.coordinator-venv/`, `state/handoffs`), then `rmdir`'s the tree root ONLY if it is now empty. See § Uninstall boundary below. `state/handoffs` is a **runtime** surface (written by ongoing coordinator operation, not by `install.md`) — it is swept here because it lives under the same coordinator-owned settings-home allowlist, not because it reverses an install write; do not read this item as evidence of an install.md counterpart.
9. **Operator config** — preserved by default; `--purge-operator-config` opt-in (see Flags above).
10. **`claude-doe` wrapper** (`${CLAUDE_HOME:-$HOME}/.local/bin/claude-doe`) — removed in both end-states; marketplace-plugin operation uses bare `claude`, not the wrapper.
### Removal invariant — a chosen position, not table stakes

Every `REVERSE` disposition below is bound by one rule: **verify before removing, fail loud rather
than reconstruct, never touch what the operator has edited.** State it as the deliberate position
it is. Surveyed comparators — nvm, rustup, conda — all strip sentinel blocks on bare pattern match
with no tamper check, and none has a disambiguation convention for accumulated backups; we are
stricter than the market, not catching up to it. The cautionary case is oh-my-zsh, whose
uninstaller restores a pre-install snapshot unconditionally with no edited-since check
(ohmyzsh#13156 — an open bug where a user lost years of config to exactly that shape).

For the same reason `--dry-run` is **standard, not optional** on this command (the shape conda
ships as `--reverse --dry-run`): a preview of the ordered leg plan is the cheapest protection
against a reversal doing more than the operator expected. See § Flags.

> **Items 11-24 are SPECIFIED, NOT YET IMPLEMENTED. Read this before trusting any `REVERSE`
> disposition below.**
>
> Surfaces 1-10 describe what `/coordinator:uninstall` does today. Surfaces 11-24 supplement that
> list: install writes roughly nineteen out-of-repo surfaces this table did not previously account
> for — the `#1-#10` list was a removal-leg list, not a write-surface list, so nothing forced it to
> be a superset.
>
> The removal legs for the `REVERSE` items below **do not exist yet**. Verified at the time of
> writing: the engine's uninstall entrypoint and its install-legs module carry no handling for the
> recorded-repo list, `~/.ssh/config`, the signing-key config, the Defender exclusions, or the
> per-repo posture overlay. That implementing code is engine-resident, so it is not this repo's to
> land.
>
> Every `REVERSE` entry below is therefore a **specification for work not yet done**, written in
> the present tense because it describes the intended contract — not a description of current
> behaviour. Until those legs ship, treat items 11-24 as a manual-cleanup checklist. A reader who
> uninstalls today gets surfaces 1-10 reversed and nothing below this line.
>
> Stating this rather than letting the present tense imply otherwise is deliberate: a document
> that claims reversals it does not perform is the same defect the published `docs/safety.md`
> carried until it was corrected the same day, and putting it here instead of there would have
> moved the problem, not fixed it.
>
> **Uninstall is an explicitly best-effort courtesy, not a guaranteed reversal** — the agentic half
> of the story lives on a wiki page rather than in this command. The engine side enforces a
> three-value disposition set — `reversed`, `deliberately-not-reversed` (carrying a reason), and
> `cannot-reverse-safely` (carrying the manual command) — in
> `coordinator_core/install/uninstall_legs.py`, where a disposition outside the set cannot be
> constructed and `assert_total_coverage()` sums the three buckets against the record count. Items
> 11-24's `REVERSE` / `DELIBERATELY-NOT-REVERSED` / `CANNOT-REVERSE-SAFELY` map onto it directly.
> Coverage is quantified over a machine's install *receipt* — what that machine actually got — not
> over the write-surface manifest emitted by `write_surface.emit_manifest`, which describes what a
> writer *can* write and is unsatisfiable on any real machine. **That denominator is not yet
> available on any machine:** the receipt's shape and derivation exist engine-side
> (`coordinator_core/install/receipt.py`), but no writer emits one — the call-site is unowned and
> tracked engine-side as `state/debt-backlog/2026-08-06-install-receipt-has-no-emission-call-site.yaml`.
> Until that leg lands, the coverage property is stated, not checkable, and this repo's consuming
> test enforces declaration-against-leg-text only rather than approximating receipt coverage.

11. **Windows Defender process exclusions** (install.md Step 1c) — **CANNOT-REVERSE-SAFELY.** Install itself declines to auto-reverse this (elevated, machine-wide security policy); uninstall does not attempt it either. Roll back manually, per resolved toolchain path, elevated: `Remove-MpPreference -ExclusionProcess "<path>"` for each of `bash.exe`, `git.exe`, `sh.exe`, `python.exe`, `pythonw.exe` that was excluded — a no-op, not an error, on a path that was never excluded.
12. **`~/.ssh/config` rewrite + global SSH commit signing** (`coordinator/scripts/setup-github-auth-1password.py`, engine-resident; install.md § "GitHub Auth via 1Password (optional opt-in)") — **REVERSE.** Two branches on `~/.ssh/config`, discriminated by whether the file existed pre-install: (a) **it existed** — restore from the pre-edit backup, which is PID-suffixed (`config.coordinator-bak.<pid>`) and must be located by glob, not by name; exactly one accumulates, because a second install short-circuits on the marker rather than re-backing-up. Fail loud if that backup is missing — never reconstruct. (b) **it did not exist** — absence of a backup is the *expected* state, not a failure; the correct reverse is removing the file the installer created. Without this branch the leg fires its fail-loud on the normal fresh-machine path. Once the installer writes a matching END marker alongside its `# Added by coordinator setup-github-auth-1password` BEGIN marker (see item 16, same ask), prefer a precise block splice over whole-file restore; until then only whole-file restore is available. Global signing config set by the same helper — `gpg.format`, `user.signingkey`, `commit.gpgsign`, `tag.gpgsign`, `gpg.ssh.program`, `gpg.ssh.allowedSignersFile`, and the line the helper appended to `~/.config/git/allowed_signers` — is unset via `git config --global --unset` (the allowed-signers line stripped in place), each only when the current value still matches what the installer would have set (skip with a note otherwise — an operator may have since re-keyed).
13. **`origin` remote SSH flip** (same helper) — **DELIBERATELY-NOT-REVERSED.** Flipping `origin` back to HTTPS post-hoc risks breaking a remote the operator has since relied on over SSH (new commits, new auth flow) — the installer's own `git ls-remote` verification before keeping the change has no symmetric un-verification step. Manual reversal: `git remote set-url origin <original-https-url>`.
14. **Git-config hardening settings** (install.md § "1a.1. Git-config hardening (concurrent-EM lock safety)") — **REVERSE.** The authoritative surface list is the writer's own `_SETTINGS` tuple (engine `coordinator_core/ops/configure_git.py`), imported rather than hardcoded here — today `core.checkStat=minimal` (machine-wide) and `gc.autoDetach=false` (per-repo). Each is unset only when the current value still matches what the installer set (skip with a note otherwise).
15. **Global `git lfs install` filters** (install.md § "1a.3. Git-LFS enablement (idempotent, harmless — proactive coverage)") — **DELIBERATELY-NOT-REVERSED.** Act-not-gate, benign, and other LFS-tracked repos the operator clones after uninstalling coordinator may now depend on the global filter being present; removing it risks silently reverting those repos to pointer-only checkouts. No manual command is offered — running `git lfs uninstall` is the operator's own call if they're certain nothing else needs it.
16. **Shell-init-guard seam** (install.md § "3.5b.1 — Install interactive-shell resource-cap guard (idempotent, graceful-absent)") — **REVERSE.** Scoped to this seam alone: the PATH guard families — `CLAUDE_CLI_PATH` and `SETTINGS_HOME_BIN` — are not distinct from the `#4` shim family, they *are* it, and are already stripped today by `uninstall_legs.uninstall_remove_shim` (`wrapper_onto_path.py` itself writes no rc block — its `on_path` is advisory-only). What remains is the resource-cap guard's sentinel-guarded rc block: locate by sentinel, strip the exact block, fail loud on a hand-modified block. Precise stripping today depends on treating the body line `unset _cc_fsize_guard` as a de-facto end marker; the installer is to write an explicit END marker instead (same ask as item 12).
The `~/.local/bin/claude-doe` file itself is **not** part of this item — it is a file deletion with none of the sentinel machinery, and it is already covered, and already implemented, as item #10.
17. **Operator `~/.claude` git-hook gate regions** (install.md § "1a.2. Operator `~/.claude` git-hook gates (conditional)") — **REVERSE.** Key on the live `# --- Gate: <label> (<marker>) ---` regions the installer actually writes, across **all three** hook files it touches — `pre-commit` (sending side) plus `post-merge` and `post-checkout` (receiving side); the installer no longer writes a `coordinator-precommit-exec-bit-check` marker, so do not key on it. Reuse the installer's own `_find_gate_region` / `_find_all_gate_markers` / `_remove_orphaned_gate_regions` and its present/current/stale classification rather than re-implementing the locate-and-splice: a region classified current is removed; one hand-edited since is left in place with a note; a hook file left with no coordinator regions is deleted only if it holds nothing else. The marker set is read from the installer's registry, never copied into a second list here.
18. **`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` env key** (install.md § "1b. Agent Teams env var") — **CANNOT-REVERSE-SAFELY.** No coordinator-owned marker distinguishes "seeded by this install and untouched" from "operator now relies on Agent Teams directly" — `#2`'s hook-identity inverse-strip has no equivalent for a bare env key. Not auto-removed. Manual reversal, only if you're sure nothing else needs it: delete the `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` entry from `~/.claude/settings.json`'s `env` block.
19. **`settings.local.json` `enabledPlugins` sibling-plugin seeds** (install.md § "3.5c-2 — Seed marketplace-sibling enabledPlugins (idempotent)") — **DELIBERATELY-NOT-REVERSED.** Same provenance problem as #18: a seeded `true` may since be genuinely relied on by the operator. Manual reversal per key, if desired: set the specific `<plugin>@<marketplace>` entry to `false` in `~/.claude/settings.local.json`.
20. **`~/.claude/CLAUDE.md` personal-layer seed** (install.md § "Personal-layer doctrine seed (`~/.claude/CLAUDE.md`)") — **DELIBERATELY-NOT-REVERSED.** This file is explicitly never-clobber at install time specifically because it is expected to accumulate hand-authored doctrine; blind removal at uninstall time risks destroying an operator's customized global file. Not offered even under `--purge-operator-config` — that flag covers `coordinator-identity.yaml`/`working-repos.yaml`, files coordinator alone owns, not this operator-editable one.
21. **`scaffold_structure` canonical doc-structure output** (`coordinator_core.install.scaffold_structure`, install.md § "Step 7 — Scaffold canonical document structure (idempotent)") — **DELIBERATELY-NOT-REVERSED.** `cross-repo/` and sibling scaffolded dirs accumulate real operator artifacts (memos, archives) over time that are not coordinator's to delete.
22. **`coordinator-setup-state.yaml` `setup_concluded` receipt** (install.md § "Step 0 — Record setup-concluded receipt (idempotent)") — **REVERSE.** Removed via `coordinator-setup-state clear setup_concluded` (or the file deleted outright if it holds no other milestones). `clear` is a **new** subcommand — the CLI ships `{record, check, status, auto-record-if-source-is-live}` today and returns 2 on `clear`; it is added engine-side as part of this leg, not assumed present.
23. **Discovered-repo `repos.*` registry entries** (`register-discovered-repos.py`, install.md § "Step 3 — Optional seed prompt (declinable, interactive only)") — **DELIBERATELY-NOT-REVERSED.** `repos.*` is general-purpose sibling-repo addressing infrastructure other tooling (`cross-repo-memo`, `machine-local`) may depend on independent of coordinator; blind clearing risks breaking that other tooling. Not swept by any flag.
24. **Four project-repo writes** (`.claude/em-context.md`, `.gitignore` append, `coordinator.local.md`, the currency stamp — install.md § "Step 3b-5 — Materialize the overlay pre-restart" / same step's `.gitignore` append / § "Phase 5 — Project-local" § "coordinator.local.md" / § "Currency stamp (idempotent)") — **REVERSE, driven by a new install-time record.** Install now appends the invocation repo's root path to the machine-local list key `coordinator.installed_repos` (see install.md's Step 3b-6 below) the first time any of these four writes fires for that repo. Uninstall reads that list and, for each recorded repo still present on disk, offers (interactive) or reports (`--non-interactive`: lists the repos and the exact per-repo cleanup, does not touch them) removal of: the `.claude/em-context.md` overlay, the two-line `.gitignore` append (only if byte-identical to what the installer wrote), `coordinator.local.md`, and the currency stamp. A repo no longer present on disk is reported and skipped, not treated as an error. This is the chosen design over the two alternatives considered: a `--repo <path>` flag (rejected — puts the burden on the operator to remember every repo a maximalist install ever touched, with no self-discovery, and silently misses any they forget) and pure hand-documentation with no recording (rejected — leaves the cleanup undiscoverable, which is the exact gap this P1 exists to close for a security-relevant surface class).

## Uninstall boundary

Coordinator uninstall follows **blanket-with-provenance**: it deletes only coordinator-authored
artifacts under `<settings-home>/` (the allowlist enumerated in item 8 above), never the
`<settings-home>` root itself via a blanket sweep. Any `<settings-home>/<repo-id>/` durable-data
subtree owned by a consumer (e.g. Example-cockpit-repo's shipped `store.db`, project-rag's future
plane data) is preserved by default — it is not on the coordinator's own allowlist, so it survives
full-remove untouched, and `<settings-home>` itself is left in place (not `rmdir`'d) as long as any
such subtree remains.

A consumer MAY additionally register an **optional per-`<repo-id>` keepset** to protect
coordinator-adjacent paths it wants preserved beyond the blanket default — this is a narrowing on
top of blanket-with-provenance, not the primary mechanism: the blanket default already protects an
**unregistered** consumer's durable data, so no consumer is required to register anything for its
`<settings-home>/<repo-id>/` subtree to survive uninstall.

## Verification after running

Resolve `claude-klabauter`'s root the same way as § Backing script above (`CLAUDE_KLABAUTER_ROOT` env override,
then `REPO_CLAUDE_KLABAUTER` env override, then
`"${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/bin/machine-local" get repos.claude_klabauter`),
then invoke:
`"${COORDINATOR_PYTHON:-python3}" "<resolved-claude-klabauter-root>/coordinator/lib/check-install-singularity.py"`.

- **Full-remove:** exits 0, "no coordinator tree resolved (fresh install or all paths absent)".
- **Revert-to-marketplace:** exits 0, single canonical tree at `~/.claude/plugins/coordinator-claude`, with the tri-file contract (CHECK 5) satisfied — `settings.json`, `settings.local.json`, and `known_marketplaces.json` all agreeing on the flat path.

Also check resolver-mode behavior (claude-klabauter `coordinator/lib/resolve-coordinator-clone.py --for-content` / `--for-git-ops`):
full-remove → both fail-loud (no stale-cache fallthrough); revert-to-marketplace → both resolve to
the flat tree.

## Running-in-Claude-Code validation (required, not just script-green)

A green script run is
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
`check-install-singularity.py` both report green.

## See also

- `coordinator/commands/install.md` — the forward install this reverses. The surface list is kept
  in lockstep between the two commands — a new surface added there gets a matching removal step
  here in the same change.
