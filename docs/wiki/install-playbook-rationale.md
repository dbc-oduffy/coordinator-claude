# Install Playbook — Rationale, Worked Examples, Failure-Mode Detail

> Companion to `INSTALL.md`. That file keeps the command, its expected output, and at most one
> line of why; this page carries the mechanism detail that would otherwise bloat the playbook.
> Cross-referenced by heading name from `INSTALL.md`.
<!-- Review: review-integrator (overengineering-reviewer finding 5) — deletion-default pass. Kept
the SSH clone behaviour, gitCommitSha snapshot pinning, and the percolation provisioning table;
cut failure-mode essays duplicating what INSTALL.md already states inline. -->

## Step 1d — SSH clone and snapshot pinning

The repo is public, but this step still needs a working git credential — it clones over SSH.
`claude plugin marketplace add owner/repo` resolves the shorthand to `git@github.com:owner/repo.git`
and prints `Cloning via SSH:` as it does so. That is Claude Code's behaviour, not a coordinator
setting, and the requirements table's `gh auth login` does **not** satisfy it — `gh auth status` on
an HTTPS-configured box reports `Git operations protocol: https` and there may be no `~/.ssh/id_*`
at all. If this step fails with `git@github.com: Permission denied (publickey)`, add an SSH key to
the GitHub account, or clone over HTTPS and register the local directory as the marketplace source
instead — noting the live-edit and portability caveats below.

A directory source does NOT give you live edits — verify this before relying on it.
`claude plugin install` copies the plugin into
`~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/` and pins `installed_plugins.json`'s
`gitCommitSha` to the commit present at install time, for a directory source exactly as for a git
one. The running plugin is that **snapshot**, not your working tree: uncommitted edits are
invisible, and committed ones are too until you reinstall. On an actively committed clone the gap
opens within minutes, silently. Check it yourself:

```bash
diff -r ~/.claude/plugins/cache/coordinator-claude/coordinator/*/ <clone>/coordinator/
```

## One-shot alternative (`coordinator-install`) — caveat detail

**This path requires an already-resolvable engine root — it is not a cold bootstrap.** Confirm
resolution first with `python3 coordinator/hooks/scripts/_engine_root.py` — empty output means
take the CLI steps and reach the engine at Step 4 instead.

**`--check-only` does not verify the install.** It forwards to the engine installer's `--check`,
which reports only that the script is present and executable. It returns green on a box where the
real invocation then fails.

Full execution proof on Windows is tracked in this repo's dogfood log rather than re-run per doc
edit — see `docs/plans/2026-08-07-windows-pc-install-repair-and-dogfood-log.md`, a doctrine-repo
authoring-repo working-data doc with no OSS-mirror counterpart.

## Step 1e — engine-root export, and the retired token

If `machine-local` does not exist yet, that is expected on a cold box — it is deposited by
Phase 3, which has not run. Export the engine root instead and Phase 3 will pick it up:

```bash
export COORDINATOR_ENGINE_ROOT="$(dirname <coordinator-clone>)/claude-klabauter"
```

`COORDINATOR_ENGINE_ROOT` is the top rung of the engine-root ladder and the one bootstrap remedy
that works before anything is installed. The durable equivalent, which survives a new shell, is a
pointer file at `~/.coordinator-claude-settings/machine-local/.claude-klabauter-live-root`
containing the path. `CLAUDE_KLABAUTER_ROOT` is retired and unhonoured — setting it produces an
error naming `COORDINATOR_ENGINE_ROOT` as the replacement.

## DoE-only: `claude-doe` — when the shim earns its keep

The shim is about *live* resolution, not about whether coordinator loads at all. `claude-doe`
passes `--plugin-dir` at the clone, so edits here take effect on the next session with no
reinstall; a plain `claude` session loads the pinned snapshot instead. The two are additive, not
exclusive — a `claude-doe` session that also has the plugin installed gets one deduplicated
command set, not a double load. The gap between them is measurable:

```bash
claude -p "count skills starting with coordinator:"                       # snapshot
claude --plugin-dir <clone>/coordinator -p "count skills starting with coordinator:"   # live
```

On the box this was written from, that read 51 vs 53 — the snapshot was four commits behind. If
Step 1d has NOT run, a plain `claude` session is silently coordinator-less — nothing announces it,
and it is easy to mistake for a doctrine bug rather than a launcher problem.

## Step 4 — why the ordering is not the obvious one

**Known braid defect, not a design.** The clone has to come first because `/coordinator:install`'s
own Phase 3 bootstraps coordinator's substrate from a script that lives *in the engine repo*
(`$ENGINE_ROOT/coordinator/lib/install-substrate.py`) — an ordering that installs
coordinator-claude before the engine clone exists fails on the first command with an unset root.
`/coordinator:install` and `/coordinator:setup` are not aliases: Phase 3 of `/coordinator:install`
deposits the `machine-local` resolver the engine installer's dependency check needs; running
`/coordinator:setup` expecting it to install the substrate gets a fail-loud "engine not satisfied"
with no explanation.

## Percolation surface — full detail

Percolation (`python "$(python3 coordinator/hooks/scripts/_engine_root.py)/coordinator/bin/publish.py"`
— this driver migrated to the engine repo in commit `b644d5a9`, resolved via the engine-root seam,
not this repo — driven by `/percolate`) resolves its runtime root (`PERCOLATE_ROOT`) via a
four-rung chain — see `coordinator/docs/wiki/percolate-setup.md § PERCOLATE_ROOT Resolution` for
the full mechanism. A fresh-machine install produces a *working* percolation surface only if all
three pieces below are in place; the installer delivers the first, the operator must provision the
second and third by hand.

| Piece | Delivered by | Location |
|---|---|---|
| Machine-agnostic topology (`publish-targets.portable`) | Installer — tracked in the repo, clones with it | `setup/publish-targets.portable` (repo root — this tracked copy is itself the authoritative source; no `coordinator/templates/setup/` mirror of it exists on disk) |
| Per-operator secrets (`.percolate-identity`, real machine codenames) | **Operator, by hand** — never installer-generated | `setup/.percolate-identity` at this repo's root, gitignored — `publish.py` sources it from its own directory, so this is the copy that's actually read in repo-local mode |
| Per-machine state (`percolate-state/*.lastsync`) | `publish.py` creates it on first run — no installer step | `setup/percolate-state/`, gitignored, machine-local |

**Provisioning `.percolate-identity` on a new machine:** copy
`coordinator/templates/setup/.percolate-identity.example` to `setup/.percolate-identity` at the
repo root and populate `PERSONAL_REVIEW_PATTERNS` with this machine's real codenames. This is the
one percolation step no installer phase performs for you — it requires knowledge (which machine
names are private) that only the operator has. **Do not** provision this at
`~/.coordinator-claude-settings/.percolate-identity` expecting it to be picked up here — that path
belongs to the older shared-install (`~/.claude`-rooted) topology and is a separate file; see the
wiki's § Per-operator identity for the distinction and for why a
`~/.coordinator-claude-settings/setup/` tree is a retired orphan, not a live surface.

**Verifying the surface is complete:** run
`python "$(python3 coordinator/hooks/scripts/_engine_root.py)/coordinator/bin/publish.py" --dry-run coordinator-claude`
from the repo root and confirm the output includes both an `Allowlist enforcement:` line and a
`Restricted source:` line, and does **not** print a `machine-slug detection net is DOWN` warning.
The warning firing means `.percolate-identity` is either absent or has an empty
`PERSONAL_REVIEW_PATTERNS` — go back to the provisioning step above. A dry-run that instead reports
the version-consistency gate as "not found" is not a clean install either — it means
`check-version-consistency.py` (also claude-klabauter-resident, same
`$(python3 coordinator/hooks/scripts/_engine_root.py)/coordinator/bin/`) didn't resolve, and
publishing would proceed with that surface unchecked.

**Why rung 2 (repo-local resolution) needs a root-level `setup/`:** this repo's plugin root is the
`coordinator/` subdirectory, not the repo root, so a bare clone with no root `setup/` falls through
repo-local resolution and silently resolves against `~/.claude` instead — see the wiki's §
one-level-offset trap. The maximalist installer keeps the repo-root `setup/` tree in sync with
`coordinator/templates/setup/`; if you hand-roll a clone without running the installer, copy that
template to the repo root before expecting `/percolate` to work locally.
</content>
