<!-- Purpose: The lane-independent mechanical core of repo-setup — detection, rendering, scaffolding,
     hooks, substrate seeds, report shape, and tripwire installs that run the same way whichever lane
     fired. Lane-varying judgment lives in `lanes/*.yaml`. -->

# repo-setup mechanics — lane-independent

## Detection (Phase 1 basis)

**`coordinator.local.md` project-type short-circuit.** If present, read `project_type`,
`project_subtypes`, `cross_platform`. Emit a one-line confirmation naming the source. If
`project_type` differs from the marker-scan `detected_type`, emit a one-line PM-authoritative
challenge (informational, never a re-ask): *file value wins, correct `coordinator.local.md` and
re-run if wrong.* Legacy values (`unreal`, `meta`, bare `web`) get a one-line migration-hint
warning — never auto-rewritten.

**Runtime marker scan.** Run (Shape W, `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`)
`& "$env:COORDINATOR_SETTINGS_HOME\bin\detect-project-runtime.exe"`. Advisory only — warn and
continue, never abort onboarding, if the forwarder or its engine-plane target is unresolvable.
Output is advisory stdout; no skill/agent/hook reads it programmatically.

**Derived type from markers**, priority order:
- `*.uplugin`/`*.uproject` → `game-dev` / `[unreal]`
- `package.json` + a JS framework config → `web-dev`
- `requirements.txt`/`pyproject.toml`, no UE markers → `data-science`
- `Cargo.toml`, `go.mod`, or none of the above → `general`

## Rendering and scaffolding

**Machine profile.** Every step marked *author box only* is skipped without comment on a
consumer box (`machine-local get coordinator.machine_profile` prints `consumer`, or prints nothing
and no `repos.*` path holds a `.coordinator-dev-repo` file).

**CLAUDE.md** (if missing): create it once with the Write tool (never a Bash redirect, never an
overwrite of an existing file) from `render-template templates/CLAUDE.md.template` with
`PROJECT_NAME`, `PROJECT_TYPE`, `SUBTYPES`, `GLOBAL_EXTENDS_LINE` (present iff `~/.claude/CLAUDE.md`
exists), `PROJECT_TYPE_BLOCK` (concatenated `templates/project-type-block.<type>.template` bodies;
empty for `general` or an unmatched type). Populate `## Runtime conventions` bullets from the
marker-scan output (or a single "no runtime markers detected; PM to fill" placeholder). Set
`_PHASE_3A_RENDERED_CLAUDE_MD=true` on success so the Phase 4 fill-in reminder fires only when this
run rendered the template.

**docs/README.md** (if missing): `render-template templates/README.md.template`, substituting
`[PROJECT_NAME]`/`[DATE]`.

**docs/exec-summary.md** (if missing): run
`repo-setup-args-and-register resolve-exec-summary-generator --run` (Shape W). When the generator is
unresolvable (it ships with the author toolchain), skip and list `docs/exec-summary.md` under
`### Needs Attention` with that reason — a skip is never silent. It regenerates the two MANAGED
sections (identity, progress) on every run and copies the two HAND sections (`special`, `goals`)
forward verbatim; a malformed/absent HAND fence fails loud, writes nothing, names the file.
`--batch` runs this in no-clobber mode fleet-wide.

**DIRECTORY.md**: never created here — `/update-docs` Phase 2 owns it.

**Directories.** On a consumer box create only `docs/`, `docs/plans/`, `state/handoffs/` and the
gitignored `scratch/subagent-sandbox/` directly, and do not run the manifest scaffolder: the
consumer artefact set has no `.project-rag-ignore`, `.github/`, `bin/` or `tasks/` unless a lane
answer or the PM asks for one. On an author box create only `docs` (for README.md) and the
gitignored `scratch/subagent-sandbox` directly; everything else scaffolds via the engine-plane
`coordinator_core.install.scaffold_structure` CLI (`--manifest-root <coordinator-plugin-root>`,
`--root` defaults to cwd), idempotent, reading `canonical-structure.yaml`. Skip with a stderr note
if the engine-plane root doesn't resolve. Tracker-shaped files are lazy, written by their owning
skill on first use — except `state/orientation_cache.md` (below).

**`.gitignore`.** Source the block from `templates/gitignore.project.template` (never the
settings-home `dotgitignore.tmpl`). Ensure the canonical block (`.coordinator-local/`,
settings.local.json, scratch/, per-session sentinels, the doctrine-edit approval sentinel (honoured
by mtime, so a committed copy re-arms on every checkout), ceremony/coverage transients, the group-EM
watch trio — `state/group-em-watch.json`, `state/group-em-watch-parked.json`,
`state/group-em-watch-spool.jsonl` — the engine-provenance ledger
`state/engine-provenance-counts.jsonl`, `state/housekeeping-liveness.json`, `state/orientation_cache.md`, the emitted workflow scripts
`state/**/fire-*.mjs` and `state/**/*.mjs.emitted.json`,
`.project-rag-corpus-artifacts/` and `.project-rag-corpus-store/`) is present — create if
absent, append only the missing lines under one header if partially present, skip silently if
complete. If ceremony/coverage transients, any of the watch trio, the ledger, the orientation cache, or `state/housekeeping-liveness.json` are already
tracked (emitted `fire-*.mjs` / `*.mjs.emitted.json` included), `git rm --cached` them after adding the ignore rule — never `git rm`. Warn if `.claude/`
(not just `settings.local.json`) is blanket-ignored, if tracked content exists under
`scratch/`/`tasks/_*.log` (offer, don't auto-`git rm --cached`), or if the project-rag corpus paths
are already tracked (break-class finding, not a nit).

**Pre-commit corpus-artifact guard**: install `${CLAUDE_PLUGIN_ROOT:?coordinator plugin root unset — run this from a plugin command/skill, or substitute an absolute path}/bin/pre_commit_corpus_artifact_guard.py`
as `.git/hooks/pre-commit` in the same pass: `cp` it byte-for-byte, `chmod +x`, and confirm
`head -1 .git/hooks/pre-commit` prints `#!/usr/bin/env python3` — a hook without the shebang runs
under `sh` and fails every commit with `import: command not found`.

**Post-commit auto-push hook**: `coordinator-ensure-hooks-fleet` (Shape W) — idempotent
install/repair/exec-bit self-heal. Skip if a custom hook exists with PM sign-off (the
`add-existing-project` lane's `p3f5.custom-hook-skip` policy).

**Session-Id trailer hook**: `coordinator-ensure-prepare-commit-msg-hook` (Shape W) — same
self-heal pattern; silent no-op when no session-id env var resolves.

**Git config hardening**: `coordinator-configure-git` (Shape W) —
`gc.auto 0` + `core.checkStat minimal` + `maintenance.strategy incremental` +
`maintenance.auto false` + `maintenance.prefetch.enabled false`. Idempotent, cwd-only.

**Meta-repo pre-commit exec-bit gate** (*author box only*, and only when the repo being onboarded
is the meta-repo itself): run `install-meta-repo-precommit-hook <meta-root>` (Shape W) solely when
`canon(<repo-root>) == canon($HOME/.claude)`. Any other repo skips the step; it never
writes into `~/.claude/.git` and never creates `~/.claude/working-repos.yaml`.
Override: `COORDINATOR_OVERRIDE_PRECOMMIT_EXEC_BIT=1`.

**VS Code read-only guard**: `ensure-vscode-readonly --root <repo-root>` (Shape W) — merges the
read-only glob into `.vscode/settings.json`. Skips loudly (report the key to add by hand) if `jq`
is absent or the settings file is JSONC.

## Substrate seeds (ALWAYS, idempotent — no lane varies these)

**Currency stamp**: `<claude-klabauter-root>/coordinator/lib/coordinator_currency.py write "$(pwd)"
<coordinator-plugin-root>`. Skip for `published-artifact` classification. Failure is a
Needs-Attention warning, non-fatal.

**`state/orientation_cache.md`** (if missing; gitignored, session-start rewrites it): render with `## Active workstreams` (name + 2-3
deliverables from ratified Phase 2 input), `## Branch`, empty `## Pinboard`. The heading set is
closed and verifier-enforced — never invent a heading; no project-summary/status section.

**Extended substrate seeds** (Shape W trampolines, run as subprocesses — each is fail-loud): `setup-detect-test-cmd.py --root` (writes `fast_test_cmd`/`full_test_cmd`, never silent-picks an ambiguous candidate); `setup-seed-health-ledger.py` (every row `?`); `setup-rag-decision.py --root` (*author box only* — UE + daemon present → offer to index, else `un-indexed; use Tier-3` in CLAUDE.md; a consumer box skips it and writes no RAG text); `setup-fnm-pin.py` (only when `.node-version`/`.nvmrc` present; never installs `fnm`). `coordinator:new-project` inherits all four.

**Agent-install-manifest.json seed** (if absent, never overwritten): minimal schema-compliant shape — `agent_install_contract_version: 3`, `repo_id`, `setup_skill`, `standalone_setup_script` with `entry_point_contract`, empty `direct_deps`/`required_env_vars`/`tested_platforms`, one `configurable_locations` example, `packageability_compliance.declared: true`; `[REPO_NAME]` from the ratified Phase 2 name.

**Strategic self-description skeleton** (if absent): scaffold
`state/strategic/self-description.yaml` with every field provenance `asserted` or null. The
curate-now-or-defer choice is the `p3l.curation-prompt` terminal offer; the write is unconditional.

**Guard-regression tripwire tests** (ALWAYS, idempotent, never offered). Destination is
`<that-path>/guards/`, derived from the repo's own `fast_test_cmd` path argument, never hardcoded.
Runs only where `<coordinator-plugin-root>/tests/templates/` exists; where it does not (a
published install), skip the seed and report one `### Needs Attention` line naming the missing
directory. Copy, no-clobber, every ALWAYS template from that directory:
`test_machine_local_state_tracked.py`, `test_foreign_platform_paths.py`,
`test_registry_toml_machine_paths.py` (conditional on a tracked `registry.toml`),
`test_guard_wiring_completeness.py` (conditional on a `hooks/hooks.json` surface),
`test_every_test_tree_is_collected.py`, `test_no_absolute_path_literals.py`,
`test_gitattributes_line_ending_coverage.py`. Each resolves its own repo root via
`_tripwire_root.resolve_repo_root()` (copy that sibling alongside). Afterwards verify the guards
are collected by the repo's own `fast_test_cmd`.

**Widened spawn tripwire — `.py`/`.ps1`, ALWAYS, not offered; same `tests/templates/` condition.**
Copy `test_no_bare_python_spawn.py` + `spawn_detect.py` (verbatim, stdlib-only) + the `no_console_creationflags()` helper (`_win_portability.py` for hooks, `win_portability.py` for lib/bin) into `<scope>/guards/`; set `SCOPE_SUBDIR` and extend `spawn_detect.DEFAULT_EXCLUDE` with the repo's ephemera dirname (a vendored tree by path). Exemptions key on a stable marker (`# guard-allow: <rule-id> <rationale>`, `# popup-intentional-last-resort`, or `spawn_exemption_register.yaml` + monotonic `RATCHET_MAX`), never `file:line`.

**Fleet memo-destination registration — mechanical half (*author box only*).** On accept (lane- or
PM-answered), only-if-absent register via `repo-setup-args-and-register register-repo` (Shape W;
derives `<key>` the same way `cross-repo-memo`'s `_receiver_repo_key` does), and stop: nothing
writes `~/.claude/working-repos.yaml`. Report `### Created` on success; surface
`### Needs Attention` loudly (with the manual remediation command) when the repo is still not a
memo destination after this run for any reason — declined, skipped, or `machine-local` unavailable.

## Optional tripwire installs — mechanical half

**Windows console-subprocess tripwire** (`.sh`-only). Copy
`tests/templates/test_no_bare_console_subprocess.py` to `tests/test_no_bare_console_subprocess.py`,
customize `PREFIXES`/`EXACT_FILES`, verify with `python tests/test_no_bare_console_subprocess.py`
(bare `python`, no `python3` alias on Windows). Two suppression markers, honoured identically:
`# popup-intentional-last-resort`, `# popup-safe-env-suppressed`. Retired form
`# noqa: bare-subprocess-windows` is NOT honoured. Whether to offer it is lane/PM judgment.

## Phase 4 report — mechanical shape

**Declared exemption from the ≤200-word EM→PM budget** (global `CLAUDE.md § Communication Style`):
do not shorten this once-per-repo walkthrough to satisfy the word-budget hook. The template's first
and last lines are the marker pair that declares the exemption (`em-pm-comms-instrumentation.md`
§ The ceremony-mandated marker).

`### Already Existed (untouched)` prints only when non-empty. `### Created` and `### Needs Attention` always
print. `### Recent Roadmap` is count-always — render `(none)` on a fresh repo.

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

`### What's next` carries the fixed operator walkthrough: `~/.claude` is the surface the operator
evolves; the plugin **source** lives in the doctrine-plane clone, resolved live via `--plugin-dir`;
restart (or `/reload-plugins`) to pick up mid-session doctrine-plane edits. The CLAUDE.md fill-in
reminder fires only when `_PHASE_3A_RENDERED_CLAUDE_MD=true`. `machine-local get repos.*` failure:
no registry dir → `/coordinator:install` Phase 3; registry present, no keys →
`machine-local set repos.<name> <path>` per sibling; command not found → re-run
`/coordinator:install` Phase 3.

Rationale and history: `coordinator/docs/wiki/install-playbook-rationale/repo-setup-residue.md`
§ repo-setup mechanics rationale.
