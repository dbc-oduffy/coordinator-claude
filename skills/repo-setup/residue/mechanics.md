<!-- Purpose: The lane-independent mechanical core of repo-setup — detection, rendering, scaffolding,
     hooks, substrate seeds, report shape, and tripwire installs that run the SAME WAY regardless
     of which lane (`lanes/new-project.yaml`, `lanes/add-existing-project.yaml`,
     `lanes/add-repo.yaml`) fired. Re-cut from the phase-keyed originals: a phase number is a
     table of contents, not a situation split, so this file keys on "runs regardless of lane"
     instead. Lane-varying judgment (which round_trip point resolves to which value, which
     terminal offer defaults to what) lives in the three lane files, not here — narrated
     ask-and-wait prose is stripped; see each lane file for the pre-answered values. -->

# repo-setup mechanics — lane-independent

## Detection (Phase 1 basis)

**`coordinator.local.md` project-type short-circuit.** If present, read `project_type`,
`project_subtypes`, `cross_platform`. Emit a one-line confirmation naming the source. If
`project_type` differs from the marker-scan `detected_type`, emit a one-line PM-authoritative
challenge (informational, never a re-ask): *file value wins, correct `coordinator.local.md` and
re-run if wrong.* Legacy values (`unreal`, `meta`, bare `web`) get a one-line migration-hint
warning — never auto-rewritten.

**Runtime marker scan.** Run (Shape W, `snippets/resolve-coordinator-bin.md`)
`& "$env:COORDINATOR_SETTINGS_HOME\bin\detect-project-runtime.cmd"`. Advisory only — warn and
continue, never abort onboarding, if the forwarder or its engine-plane target is unresolvable.
Output is advisory stdout; no skill/agent/hook reads it programmatically.

**Derived type from markers**, priority order:
- `*.uplugin`/`*.uproject` → `game-dev` / `[unreal]`
- `package.json` + a JS framework config → `web-dev`
- `requirements.txt`/`pyproject.toml`, no UE markers → `data-science`
- `Cargo.toml`, `go.mod`, or none of the above → `general`

**Cross-platform inference signal.** Two signals, either sufficient: (a) a
`.github/workflows/*.yml` `os:` matrix with 2+ OS entries; (b) `*.sh` in `bin/` AND a Windows-
operator marker in `coordinator.local.md`. Record `_CROSS_PLATFORM_INFERRED` +
`_CROSS_PLATFORM_SIGNAL` (human-readable) when either fires — **never auto-write
`cross_platform: true`**; the lane's `tw.ci-inference-prompt` pre-answer (or, absent a lane, a
live prompt) decides whether to act on the signal. Suppress the signal (`_CROSS_PLATFORM_INFERRED`
stays false) when `templates/ci/cross-platform-matrix.snippet.yml` already exists — the repo has
already adopted the discipline.

## Rendering and scaffolding

**CLAUDE.md** (if missing): `render-template templates/CLAUDE.md.template` with
`PROJECT_NAME`, `PROJECT_TYPE`, `SUBTYPES`, `GLOBAL_EXTENDS_LINE` (present iff `~/.claude/CLAUDE.md`
exists), `PROJECT_TYPE_BLOCK` (concatenated `templates/project-type-block.<type>.template` bodies;
empty for `general` or an unmatched type). Populate `## Runtime conventions` bullets from the
marker-scan output (or a single "no runtime markers detected; PM to fill" placeholder). Set
`_PHASE_3A_RENDERED_CLAUDE_MD=true` on success so the Phase 4 fill-in reminder fires only when this
run rendered the template, never for a bespoke CLAUDE.md.

**docs/README.md** (if missing): `render-template templates/README.md.template`, substituting
`[PROJECT_NAME]`/`[DATE]`.

**docs/exec-summary.md** (if missing): run
`repo-setup-args-and-register resolve-exec-summary-generator --run` (Shape W). Degrades to a
stderr warning and skip, never an abort, when the generator is unresolvable. Regenerates the two
MANAGED sections (identity, progress) from current disk state on every run, including re-runs
against an existing file; copies the two HAND sections (`special`, `goals`) forward verbatim. A
malformed/absent HAND fence fails loud, writes nothing, names the file. `--batch` runs this in
no-clobber mode fleet-wide.

**DIRECTORY.md**: never created directly here — `/update-docs` Phase 2 owns it, self-gated.

**Directories.** Create only `docs` (for README.md) and the gitignored `scratch/subagent-sandbox`
directly; everything else scaffolds via the engine-plane
`coordinator_core.install.scaffold_structure` CLI (`--manifest-root <coordinator-plugin-root>`,
`--root` defaults to cwd), idempotent, reading `canonical-structure.yaml`. Skip with a stderr note
if the engine-plane root doesn't resolve. Most tracker-shaped files are NOT pre-created — lazy,
written by their owning skill on first use — except `state/orientation_cache.md` (below), which
has real day-1 content once Phase 2 answers exist.

**`.gitignore`.** Ensure the canonical block (settings.local.json, scratch/, per-session
sentinels, ceremony/coverage transients, `.project-rag-corpus-artifacts/` and
`.project-rag-corpus-store/`) is present — create if
absent, append only the missing lines under one header if partially present, skip silently if
complete. If ceremony/coverage transients are already tracked, `git rm --cached` them after adding
the ignore rule. Warn if `.claude/` (not just `settings.local.json`) is blanket-ignored, if tracked
content exists under `scratch/`/`tasks/_*.log` (offer, don't auto-`git rm --cached`), or if the
project-rag corpus paths are already tracked (break-class finding, not a nit — ~230MB in history).

**Post-commit auto-push hook**: `coordinator-ensure-post-commit-hook` (Shape W) — idempotent
install/repair/exec-bit self-heal in one call. Skip if a custom hook exists with PM sign-off
(judgment; see the `add-existing-project` lane's `p3f5.custom-hook-skip` policy).

**Session-Id trailer hook**: `coordinator-ensure-prepare-commit-msg-hook` (Shape W) — same
self-heal pattern; silent no-op when no session-id env var resolves.

**Git config hardening**: `coordinator-configure-git` (Shape W) —
`gc.autoDetach false` + `core.checkStat minimal`. Idempotent.

**Meta-repo pre-commit exec-bit gate** (conditional): `install-meta-repo-precommit-hook <meta-root>`
(Shape W), meta-repo root passed explicitly (`~/.claude`) so the install is cwd-independent. The
helper itself gates on `canon(repo-root) == canon($HOME/.claude)` — no-ops in every consumer repo.
Override: `COORDINATOR_OVERRIDE_PRECOMMIT_EXEC_BIT=1`.

**VS Code read-only guard**: `ensure-vscode-readonly --root <repo-root>` (Shape W) — merges the
read-only glob into `.vscode/settings.json`. Skips loudly (report the key to add by hand) if `jq`
is absent or the settings file is JSONC.

## Substrate seeds (ALWAYS, idempotent — no lane varies these)

**Currency stamp**: `<claude-klabauter-root>/coordinator/lib/coordinator_currency.py write "$(pwd)"
<coordinator-plugin-root>`. Skip for `published-artifact` classification; apply otherwise. Failure
is a Needs-Attention warning, non-fatal to onboarding.

**`state/orientation_cache.md`** (if missing): render with `## Active workstreams` (name + 2-3
deliverables from ratified Phase 2 input), `## Branch`, empty `## Pinboard`. The heading set is
closed and verifier-enforced — never invent a heading. No project-summary/status section: the
cache is a cache, not a record (routing question: "does this have a truth-expiry?").

**Extended substrate seeds** (Shape W trampolines, resolved via the shared engine-plane root
idiom, run as subprocesses — each is fail-loud/`exit`-on-ambiguity so `source`-ing would kill the
shell): test-command detection (`setup-detect-test-cmd.py --root`, writes `fast_test_cmd`/
`full_test_cmd`, fails loud on ambiguous candidates, never silent-picks); health-ledger seed
(`setup-seed-health-ledger.py`, every row `?`, never fabricates a grade); RAG-index decision
(`setup-rag-decision.py --root` — UE + daemon present → offer to index; everything else → tripwire
path, `un-indexed; use Tier-3` written to CLAUDE.md); fnm pin-resolution (`setup-fnm-pin.py` — acts
only when `.node-version`/`.nvmrc` present; fails loud if `fnm` itself isn't installed, never
installs the binary — that's `coordinator:install` Phase 3's job). `coordinator:new-project`
inherits all four via delegation; no re-implementation there.

**Agent-install-manifest.json seed** (ALWAYS if absent, never overwritten if present): minimal
compliant shape per the schema — `agent_install_contract_version: 3`, `repo_id`, `setup_skill`,
`standalone_setup_script` with `entry_point_contract`, empty `direct_deps`/`required_env_vars`/
`tested_platforms`, one `configurable_locations` example, `packageability_compliance.declared:
true`. Substitute `[REPO_NAME]` from the ratified Phase 2 name.

**Strategic self-description skeleton** (ALWAYS if absent): scaffold
`state/strategic/self-description.yaml` with every field provenance `asserted` or null. This is a
terminal offer (`p3l.curation-prompt`) for the immediate curate-now-or-defer choice — see the
per-lane policy default; the skeleton write itself is unconditional.

**Guard-regression tripwire tests** (ALWAYS, idempotent, never offered — the class of failure is
invisible until it causes an outage). Destination is derived from the repo's own `fast_test_cmd`
path argument (`<that-path>/guards/`), never hardcoded to `tests/guards/` — a guard pytest never
collects is no guard at all. Copy, no-clobber, every ALWAYS template from
`<coordinator-plugin-root>/tests/templates/`: `test_machine_local_state_tracked.py`,
`test_foreign_platform_paths.py`, `test_registry_toml_machine_paths.py` (conditional on a tracked
`registry.toml`), `test_guard_wiring_completeness.py` (conditional on a `hooks/hooks.json`
surface), `test_every_test_tree_is_collected.py`, `test_no_absolute_path_literals.py`,
`test_gitattributes_line_ending_coverage.py`. Each resolves its own repo root via
`_tripwire_root.resolve_repo_root()` (copy that sibling alongside). After copying, verify the
guards are actually collected by the repo's own `fast_test_cmd` — don't trust the path derivation
blindly.

`test_every_test_tree_is_collected.py` is what makes that verification standing rather than
one-shot: it reads the repo's own `fast_test_cmd`/`full_test_cmd`/`ceremony_test_cmds[].
collection_roots` live out of `coordinator.local.md` and fails on any test module on disk that
no tier collects — the tree added six months after setup, not just the guards seeded here. It
skips clean where a repo has no `coordinator.local.md` or declares no roots, so it is safe to
seed unconditionally.

**Widened spawn tripwire — `.py`/`.ps1`, ALWAYS, not offered.** Closes the gap the `.sh`-only
console-subprocess tripwire (below, offered) leaves for repos without `coordinator_core`. Copy
`test_no_bare_python_spawn.py` + `spawn_detect.py` (verbatim vendored copy, stdlib-only) + the
`no_console_creationflags()` helper (`_win_portability.py` for hooks, `win_portability.py` for
lib/bin) into `<scope>/guards/` (same derivation as the guard-regression seed). Adjust the repo-
root hop count via the template's `SCOPE_SUBDIR` constant; extend `spawn_detect.DEFAULT_EXCLUDE`
with the repo's own ephemera dirname — never add a bare `dist`-shaped exclude by dirname alone,
name a genuinely-vendored tree by path. Two exemption mechanisms, keyed on a stable marker never
`file:line`: inline `# guard-allow: <rule-id> <rationale>` (scanned across the full call span), or
the central `spawn_exemption_register.yaml` + monotonic `RATCHET_MAX` for tiering a bulk legacy
tree (`frozen_relpaths` makes a newly-authored file structurally ineligible). `# popup-intentional-
last-resort` is honoured identically to `guard-allow` for last-resort cases.

**Fleet memo-destination registration — mechanical half.** On accept (lane- or PM-answered), only-
if-absent register via `repo-setup-args-and-register register-repo` (Shape W; derives `<key>` the
same way `cross-repo-memo`'s `_receiver_repo_key` does), then append a row to
`~/.claude/working-repos.yaml`, only-if-absent by `path`. Report `### Created` on success; surface
`### Needs Attention` loudly (with the manual remediation command) when the repo is still not a
memo destination after this run for any reason — declined, skipped, or `machine-local` unavailable.

## Optional tripwire installs — mechanical half

**Windows console-subprocess tripwire** (`.sh`-only). Copy
`tests/templates/test_no_bare_console_subprocess.py` to `tests/test_no_bare_console_subprocess.py`,
customize `PREFIXES`/`EXACT_FILES`, verify with `python tests/test_no_bare_console_subprocess.py`
(bare `python`, no `python3` alias on Windows). Two suppression markers, honoured identically:
`# popup-intentional-last-resort` (popup accepted), `# popup-safe-env-suppressed` (suppressed by
env-var means). Retired form `# noqa: bare-subprocess-windows` is NOT honoured. Whether to offer
this tripwire at all is lane/PM judgment (Windows-operator repo signal); the install steps
themselves don't vary by lane.

**Cross-platform CI reference** — language-aware install once offered/declared:
Python repos (`data-science` type or `pyproject.toml`/`requirements.txt`/`pytest.ini` present):
auto-copy `templates/ci/cross-platform-matrix.snippet.yml` to `templates/ci/`, note in Needs
Attention to adapt marker names for the project's own hardware-gated tests. Non-Python repos: never
copy the pytest snippet — surface the wiki + snippet as a worked example to adapt instead. Whether
the offer fires (declared vs inferred-and-confirmed) is lane/PM judgment; the copy behavior itself
does not vary by lane.

## Phase 4 report — mechanical shape

**Declared exemption from the ≤200-word EM→PM budget** (global `CLAUDE.md § Communication Style`):
this is a once-per-repo onboarding walkthrough, not a recurring status report — do not shorten it
to satisfy the word-budget advisory hook.

Report-by-exception on `### Already Existed (untouched)` — print only when non-empty.
`### Created` and `### Needs Attention` always print. `### Recent Roadmap` is count-always — render
`(none)` explicitly on a fresh repo rather than omitting the heading.

Template:

```
## Onboarding Complete — [Project Name]

### Created
### Already Existed (untouched)
### Needs Attention
### Recent Roadmap (last 90d, top-10 by size)
### What's next
```

`### What's next` carries the fixed operator walkthrough: `~/.claude` is the surface the operator
evolves (git-tracked, holds config/lessons/working-data); the plugin **source** lives in the
doctrine-plane clone, resolved live via `--plugin-dir` — launch with `claude-doe`, not bare
`claude`; restart (or `/reload-plugins` if available) to pick up mid-session doctrine-plane edits.
CLAUDE.md fill-in reminder fires only when `_PHASE_3A_RENDERED_CLAUDE_MD=true`. Cross-platform CI
availability note when relevant. `machine-local get repos.*` failure: no registry dir →
`/coordinator:install` Phase 3; registry present, no keys → `machine-local set repos.<name> <path>`
per sibling; command itself not found → re-run `/coordinator:install` Phase 3 (bare-name reach is
the `coordinator/bin` forwarder, not a PATH edit).

## Fate of the seven prior segments

- `phase1-detection-details.md` — mechanical detection retained above; the PM-ask/branch prose it
  carried (Phase 2 question skip, cross-platform prompt firing) is now pre-answered per lane —
  see the three lane files.
- `phase3-core-docs.md` — rendering mechanics retained above verbatim in substance (3a/3d/3d.5/3g).
  Of its three retired-tracker references: the retired-3b tracker note and
  `p1.healthcheck-shortcircuit`'s tracker-format branch are deleted outright, carried nowhere;
  `p4.scout-citation-check`'s peer-repo scout `file:line` citation requirement is re-homed onto
  `state/workstreams/<id>.yaml` (`specs[]` / `deliverables[].text`), stated in `SKILL.md` § Notes.
- `phase3-infra-hooks.md` — retained above verbatim in substance (3e/3f/3f.5/3f.5.5/3f.5.6/3f.6).
- `phase3-substrate-seeds.md` — mechanical scaffold/seed procedure retained above; the terminal-
  offer prompt text and PM-authoritative-branch prose (curation prompt, hand-section prompt,
  custom-hook-skip judgment, memo-destination offer wording) move to the three lane files as
  policy defaults.
- `phase4-report-template.md` — retained above verbatim in substance.
- `tripwire-installs.md` — mechanical install-step content retained above; the offer-firing
  judgment (when to ask, what the inference prompt says) moves to the lane files.
- `batch-mode.md` — retained as its own file (`residue/batch-mode.md`) since `--batch` is an
  entry-point mode, not one of the three lanes; its Phase-2-substitution description now cites the
  `add-existing-project` lane's pre-answers instead of re-describing them ad hoc.
