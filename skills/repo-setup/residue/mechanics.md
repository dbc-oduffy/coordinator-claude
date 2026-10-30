<!-- Purpose: The lane-independent mechanical core of repo-setup — detection, rendering, scaffolding,
     hooks, substrate seeds, report shape, and tripwire installs that run the same way whichever lane
     fired. Lane-varying judgment lives in `lanes/*.yaml`. -->

# repo-setup mechanics — lane-independent

## Detection (Phase 1 basis)

**`coordinator.local.md` short-circuit.** If present, read `project_type`, `project_subtypes`,
`cross_platform` and confirm in one line naming the source. A `project_type` differing from the
marker-scan `detected_type` gets a one-line note (never a re-ask): file value wins. Legacy values
(`unreal`, `meta`, bare `web`) get a one-line migration hint, never auto-rewritten.

**Runtime marker scan** (Shape W, `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`):
`& "$env:COORDINATOR_SETTINGS_HOME\bin\detect-project-runtime.exe"`. Advisory only — warn and
continue if the forwarder or its engine-plane target is unresolvable; no skill/agent/hook reads it programmatically.

**Derived type from markers**, priority order:
- `*.uplugin`/`*.uproject` → `game-dev` / `[unreal]`
- `package.json` + a JS framework config → `web-dev`
- `requirements.txt`/`pyproject.toml`, no UE markers → `data-science`
- `Cargo.toml`, `go.mod`, or none of the above → `general`

## Rendering and scaffolding

**Machine profile.** Steps marked *author box only* are skipped without comment on a consumer box
(`machine-local get coordinator.machine_profile` is `consumer`, or empty with no `.coordinator-dev-repo` under any `repos.*` path).

**CLAUDE.md** (if missing): create once with the Write tool (never a Bash redirect or overwrite)
from `render-template templates/CLAUDE.md.template` with `PROJECT_NAME`, `PROJECT_TYPE`,
`SUBTYPES`, `GLOBAL_EXTENDS_LINE` (iff `~/.claude/CLAUDE.md` exists), `PROJECT_TYPE_BLOCK`
(concatenated `templates/project-type-block.<type>.template` bodies; empty for `general`).
Populate `## Runtime conventions` from the marker scan (or a
"no runtime markers detected; PM to fill" placeholder). Set `_PHASE_3A_RENDERED_CLAUDE_MD=true` on success.

**docs/README.md** (if missing): `render-template templates/README.md.template`, substituting
`[PROJECT_NAME]`/`[DATE]`.

**docs/exec-summary.md** (if missing): run
`repo-setup-args-and-register resolve-exec-summary-generator --run` (Shape W). Generator
unresolvable: skip, list it under `### Needs Attention` with that reason. HAND sections (`special`,
`goals`) copy forward verbatim; a malformed/absent HAND fence fails loud and writes nothing. `--batch` runs it no-clobber.

**DIRECTORY.md**: never created here (`/update-docs` owns it).

**Directories.** Consumer box: create only `docs/`, `docs/plans/`, `state/handoffs/` and the
gitignored `scratch/subagent-sandbox/`; no manifest scaffolder (no `.project-rag-ignore`,
`.github/`, `bin/` or `tasks/` unless a lane answer or the PM asks). Author box: create only `docs`
and `scratch/subagent-sandbox`; the rest scaffolds via the engine-plane
`coordinator_core.install.scaffold_structure` CLI (`--manifest-root <coordinator-plugin-root>`,
`--root` defaults to cwd), idempotent; skip with a stderr note if the engine-plane root doesn't
resolve. Tracker-shaped files are lazy — except `state/orientation_cache.md`.

**`.gitignore`.** Source the block from `templates/gitignore.project.template` (never the
settings-home `dotgitignore.tmpl`). Ensure the canonical block (`.coordinator-local/`,
settings.local.json, scratch/, per-session sentinels, the doctrine-edit approval sentinel,
ceremony/coverage transients, `state/group-em-watch.json`, `state/group-em-watch-parked.json`,
`state/group-em-watch-spool.jsonl`, `state/engine-provenance-counts.jsonl`,
`state/housekeeping-liveness.json`, `state/orientation_cache.md`,
`state/**/fire-*.mjs`, `state/**/*.mjs.emitted.json`, `Intermediate/`, root-anchored `/scratch_*`,
`.project-rag-corpus-artifacts/`, `.project-rag-corpus-store/`) is present — create if absent, append only missing lines under one header. Any already tracked: `git rm --cached` after adding the rule, never
`git rm`. Warn if `.claude/` is blanket-ignored, if content is tracked under
`scratch/`/`tasks/_*.log` (offer, don't auto-`git rm --cached`), or if the project-rag corpus paths (`.project-rag-corpus-artifacts/`, `.project-rag-corpus-store/`) are tracked (break-class).
Warn on a lockfile from a package manager other than the repo's own (`packageManager` field, else the tracked
lockfile); offer to delete or ignore it, never auto-remove. A generated cache is ignored or committed by its
producer, never hand-committed churn.

**Pre-commit corpus-artifact guard**: `cp` `${CLAUDE_PLUGIN_ROOT:?coordinator plugin root unset}/bin/pre_commit_corpus_artifact_guard.py`
byte-for-byte to `.git/hooks/pre-commit`, `chmod +x`, confirm `head -1 .git/hooks/pre-commit`
prints `#!/usr/bin/env python3`.

**Post-commit auto-push hook**: `coordinator-ensure-hooks-fleet` (Shape W), idempotent. Skip if a
custom hook exists with PM sign-off (`p3f5.custom-hook-skip`).

**Session-Id trailer hook**: `coordinator-ensure-prepare-commit-msg-hook` (Shape W); no-op without a session-id env var.

**Git config hardening**: `coordinator-configure-git` (Shape W) — sets `gc.auto 0`,
`core.checkStat minimal`, `maintenance.strategy incremental`, `maintenance.auto false`,
`maintenance.prefetch.enabled false`. Idempotent, cwd-only.

**Meta-repo pre-commit exec-bit gate** (*author box only*): run `install-meta-repo-precommit-hook <meta-root>` (Shape W) solely when
`canon(<repo-root>) == canon($HOME/.claude)`; any other repo skips it. Override: `COORDINATOR_OVERRIDE_PRECOMMIT_EXEC_BIT=1`.

**VS Code read-only guard**: `ensure-vscode-readonly --root <repo-root>` (Shape W); skips loudly
(report the key) if `jq` is absent or the file is JSONC.

## Substrate seeds (ALWAYS, idempotent — no lane varies these)

**Currency stamp**: `<claude-klabauter-root>/coordinator/lib/coordinator_currency.py write "$(pwd)"
<coordinator-plugin-root>`. Skip for `published-artifact`; failure is a non-fatal Needs-Attention warning.

**`state/orientation_cache.md`** (if missing; gitignored): `## Active workstreams` (name + 2-3
deliverables from ratified Phase 2 input), `## Branch`, empty `## Pinboard`. The heading set is closed (verifier-enforced).

**Extended substrate seeds** (Shape W trampolines, fail-loud): `setup-detect-test-cmd.py --root` (writes `fast_test_cmd`/`full_test_cmd`, never silent-picks an ambiguous candidate); `setup-seed-health-ledger.py` (every row `?`); `setup-rag-decision.py --root` (*author box only* — UE + daemon present → offer to index, else `un-indexed; use Tier-3` in CLAUDE.md; a consumer box writes no RAG text); `setup-fnm-pin.py` (only with `.node-version`/`.nvmrc`; never installs `fnm`). `coordinator:new-project` inherits all four.

**Agent-install-manifest.json seed** (if absent, never overwritten): minimal schema-compliant
(`agent_install_contract_version: 3`, `packageability_compliance.declared: true`); `[REPO_NAME]` from the Phase 2 name.

**Strategic self-description skeleton** (if absent): `state/strategic/self-description.yaml`, unconditional.

**Guard-regression tripwire tests** (ALWAYS, never offered). Destination `<that-path>/guards/`,
from the repo's `fast_test_cmd` path argument. Only where `<coordinator-plugin-root>/tests/templates/`
exists; else skip with one `### Needs Attention` line naming it. Copy no-clobber: `test_machine_local_state_tracked.py`,
`test_foreign_platform_paths.py`, `test_registry_toml_machine_paths.py` (iff a tracked
`registry.toml`), `test_guard_wiring_completeness.py` (iff a `hooks/hooks.json`),
`test_every_test_tree_is_collected.py`, `test_no_absolute_path_literals.py`,
`test_gitattributes_line_ending_coverage.py`, plus the `_tripwire_root.resolve_repo_root()` sibling
they resolve their root through. Then verify the repo's `fast_test_cmd` collects them.

**Widened spawn tripwire — `.py`/`.ps1`, ALWAYS, not offered; same `tests/templates/` condition.**
Copy `test_no_bare_python_spawn.py` + `spawn_detect.py` (verbatim, stdlib-only) + the `no_console_creationflags()` helper (`_win_portability.py` for hooks, `win_portability.py` for lib/bin) into `<scope>/guards/`; set `SCOPE_SUBDIR`, extend `spawn_detect.DEFAULT_EXCLUDE` with the repo's ephemera dirname. Exemptions key on a stable marker (`# guard-allow: <rule-id> <rationale>`), never `file:line`.

**Fleet memo-destination registration — mechanical half (*author box only*).** On accept (lane- or
PM-answered), register only-if-absent via `repo-setup-args-and-register register-repo` (Shape W;
derives `<key>` the same way `cross-repo-memo`'s `_receiver_repo_key` does); nothing writes `~/.claude/working-repos.yaml`. `### Created` on success; else `### Needs Attention` with the
manual command when declined, skipped, or `machine-local` unavailable.

Optional tripwire installs: `residue/tripwire-installs.md`.

## Phase 4 report — mechanical shape

**Declared exemption from the ≤200-word EM→PM budget**: do not shorten this walkthrough. The template's first and last lines are the marker pair.

`### Already Existed (untouched)` prints only when non-empty. `### Created` and `### Needs Attention` always
print. `### Recent Roadmap` renders `(none)` on a fresh repo.

Template:

```
<!-- ceremony-mandated:start -->
## Onboarding Complete — [Project Name]

### Created
### Already Existed (untouched)
### Needs Attention
### Recent Roadmap (last 90d, top-10 by size)
### What's next
<!-- ceremony-mandated:end -->
```

`### What's next` carries the fixed operator walkthrough: the plugin **source** lives in the doctrine-plane clone (live via `--plugin-dir`); restart
(or `/reload-plugins`) to pick up mid-session edits. The CLAUDE.md fill-in reminder fires only when
`_PHASE_3A_RENDERED_CLAUDE_MD=true`. `machine-local get repos.*` failure: no registry dir →
`/coordinator:install` Phase 3; registry present, no keys → `machine-local set repos.<name> <path>`
per sibling; command not found → re-run `/coordinator:install` Phase 3.

Background: `coordinator/docs/wiki/install-playbook-rationale/repo-setup-residue.md`.
