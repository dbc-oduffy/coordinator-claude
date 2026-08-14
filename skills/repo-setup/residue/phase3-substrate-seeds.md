### Phase 3i. Currency stamp (ALWAYS — idempotent)

Record which `COORDINATOR_SCHEMA_VERSION` this project was onboarded against. Idempotent —
safe to re-run; overwrites only when the schema version has been bumped since the last stamp.

Skip for distribution repos (answer (b) from Phase 1). Apply for working repos ((a) and (c)).

Resolve `CLAUDE_PLUGIN_ROOT` as the coordinator plugin root (e.g. `~/.claude/plugins/coordinator-claude/coordinator`) and the engine-plane root the same way the rest of this skill does (`REPO_CLAUDE_KLABAUTER` / `CLAUDE_KLABAUTER_ROOT` / the machine-local registry pointer; fail loud with remediation if either is unresolved), then invoke `<claude-klabauter-root>/coordinator/lib/coordinator_currency.py write "$(pwd)" <coordinator-plugin-root>` via `python3`.

If the write succeeds: add `docs/coordinator-currency.yaml` to the **Created** list (or **Already Existed** if idempotent no-op). If it fails with a clear error, add a **Needs Attention** warning — the stamp is non-fatal for onboarding but required for the drift probe.

#### 3h. state/orientation_cache.md (if missing)

Authority for this eager seed: the lazy-creation rule in `SKILL.md`'s § Lazy-creation discipline — *"Only scaffold files that have meaningful day-1 content."* PM input from Phase 2 (project name, type, initial workstreams, sibling-repo refs) is *exactly* the meaningful day-1 content that licenses an eager seed. This is the produce-not-prescribe principle (→ `docs/wiki/produce-not-prescribe.md`) applied to the orientation surface: setup has the maximum-possible context for this project, so setup writes the cache rather than punting to `/update-docs` Phase 13 against an empty repo.

Render to `state/orientation_cache.md` with the project context just gathered:

```markdown
# Orientation Cache

## Active workstreams
[WORKSTREAM_LIST — name + 2-3 deliverables each, from Phase 2 PM input]

## Branch
[CURRENT_BRANCH]

## Pinboard
[empty — populated by future workday-start / workstream-start runs]
```

Substitute the bracketed tokens from Phase 1.5 / Phase 2 ratified inputs. Leave `## Pinboard` empty (intentional — populated later). Future `/update-docs` Phase 13 reads this cache and updates it rather than overwriting from scratch.

**The heading set is closed, and the cache verifier enforces it** — a section whose heading is not on the allowlist fails verification, so do not invent one here. Seed only the headings that carry meaningful day-1 content; the generator adds the rest (branch health, recent commits, wiki, atlas, fast test, audits, housekeeping, recheck dates) once there is something real to report.

**Why there is no project-summary or status section:** the cache is a CACHE, not a record. It carries computed pointers to what exists and where — its routing question is *"does this have a truth-expiry?"*, and if yes it is cache and never doctrine. A project-purpose line re-quotes what the repo's own `CLAUDE.md` already told every agent at boot, and counts of handoffs, lessons, or backlog entries are the least useful thing a cache can hold: they expire the moment they are written, they tell an agent nothing it can act on, and a stale count reads as current — which is worse than absent. Seed routes, not answers.

---

### Phase 3j. Extended substrate seeds (ALWAYS — idempotent)

Wire in the four substrate seeds that complete the coordinator machinery for this repo. Each helper is idempotent and fail-loud on ambiguity — safe to re-run; skips cleanly when the artifact already exists or the condition doesn't apply.

Each of the four helpers migrated to the engine plane as a module-main with a `coordinator/lib/` trampoline (see the dated cross-repo memo, Ask 4) — resolve the engine-plane root via the same `_cc_claude_klabauter` seam idiom used elsewhere in this skill (§ 3f.5), then invoke the trampoline as a **subprocess** via `"${COORDINATOR_PYTHON:-python3}" <path>` — every helper is fail-loud and calls `exit` on ambiguity, so `source`-ing would terminate the repo-setup shell (and `setup-rag-decision.py` is `$0`-guarded, so sourcing it bare silently no-ops the decision block); the subprocess form isolates each exit. The target repo root is passed explicitly as `"$(pwd)"` (required by the test-command detector; defaulted to cwd by the others). Run in sequence:

**1. Test-command detection** — detect the stack's test command and write `fast_test_cmd` / `full_test_cmd` into `coordinator.local.md`: `<claude-klabauter-root>/coordinator/lib/setup-detect-test-cmd.py --root "$(pwd)"` via `${COORDINATOR_PYTHON:-python3}` (see the intro paragraph above for the `<claude-klabauter-root>` resolution + fail-loud contract).

Detects `package.json` test scripts, `pyproject.toml`/`pytest.ini`, `Cargo.toml`. Presents candidates for operator confirmation (or accepts `--non-interactive` pre-set). Fails loud when multiple ambiguous candidates are found — never silent-picks. Writes both keys as flat top-level entries in `coordinator.local.md` (the shape `cs_resolve_fast_test_cmd` / `cs_resolve_full_test_cmd` already reads). Skip if both keys are already present. The configured command is invoked only at cadence gates, never on every commit — capped parallelism, commit ≠ trigger.

**2. Health ledger seed** — seed `state/health-ledger.md` from the daily-summary schema: `<claude-klabauter-root>/coordinator/lib/setup-seed-health-ledger.py "$(pwd)"` via `${COORDINATOR_PYTHON:-python3}` (same `<claude-klabauter-root>` resolution as item 1).

Seeds every system row at grade `?` (never fabricates grades). Idempotent — skips if `state/health-ledger.md` already exists. Reference shape: this repo's own `state/health-ledger.md`.

**3. RAG-index decision** — resolve the three-branch RAG-index decision tree and write the outcome into the repo `CLAUDE.md`: `<claude-klabauter-root>/coordinator/lib/setup-rag-decision.py --root "$(pwd)"` via `${COORDINATOR_PYTHON:-python3}` (same `<claude-klabauter-root>` resolution as item 1).

Branch logic (do not write a dead offer for non-UE repos):
- UE repo + project-rag daemon present → offer to index.
- Non-UE repo (any daemon state) → tripwire path (upstream `.uproject`-abstention defect blocks non-UE indexing; cite the memo).
- No daemon → tripwire path.

Tripwire branches write `un-indexed; use Tier-3 (Read/Grep/Glob)` into the repo `CLAUDE.md`.

**4. fnm pin-resolution** — ensure the repo's pinned Node version is installed via machine-level fnm: `<claude-klabauter-root>/coordinator/lib/setup-fnm-pin.py "$(pwd)"` via `${COORDINATOR_PYTHON:-python3}` (same `<claude-klabauter-root>` resolution as item 1).

Acts only when `.node-version` or `.nvmrc` is present; pure no-op when neither exists. When a pin file is found: checks whether the `fnm` binary is installed; if present, runs `fnm install <pinned>` and emits fnm's own shell-init guidance (its `fnm env` output, meant to be eval'd) as PATH guidance for no-version-manager shells; if absent, fails loud: `"fnm not installed — run coordinator:install to install the Node toolchain manager, then re-run repo-setup."` **repo-setup MUST NOT install the fnm binary** — binary install is machine-level only (per `coordinator:install` Phase 3).

Record outcomes in the Phase 4 REPORT under `### Created` or `### Already Existed` as appropriate. Any fail-loud exit from a helper surfaces under `### Needs Attention` with the helper's remediation text verbatim.

**`coordinator:new-project` inherits all four seeds via its Phase-4 delegation to `coordinator:repo-setup` — no re-implementation in `new-project` is needed or permitted.**

### Phase 3k. Packageability-compliant starter agent-install-manifest.json (ALWAYS — idempotent)

Seed `docs/install/agent-install-manifest.json` (shape below) so every repo inherits the
packageability contract at birth, rather than by per-repo goodwill later. **Skip entirely if `docs/install/agent-install-manifest.json` already
exists** — this phase never overwrites a hand-authored or previously-seeded manifest; a repo that
outgrows the starter shape edits the file directly.

Substitute `[REPO_NAME]` with the same project name ratified in Phase 2, and `[SETUP_SKILL]` with
`/coordinator:setup` only when this repo IS coordinator-claude itself — every other repo uses its
own onboarding skill invocation (default `/coordinator:repo-setup` unless the project defines its
own). Create the `docs/install` directory.

```json
{
  "agent_install_contract_version": 3,
  "repo_id": "[REPO_NAME]",
  "setup_skill": "/coordinator:repo-setup",
  "standalone_setup_script": {
    "posix": "scripts/setup.sh",
    "windows": "scripts/setup.ps1",
    "entry_point_contract": {
      "non_interactive_flag": "--i-am-agent",
      "check_only_flag": "--check",
      "deterministic_exit": true
    }
  },
  "direct_deps": [],
  "required_env_vars": [],
  "override_flags": {
    "skip_dep_check": "--skip-dep-check",
    "accept_hallucination_risk": "--accept-missing-deps-risk"
  },
  "tested_platforms": [],
  "configurable_locations": [
    {
      "name": "install_root",
      "discovery": {
        "candidates": [
          "[REPO_NAME_UPPER]_INSTALL_ROOT env var, if set",
          "default: cwd-relative resolution ($(pwd) at setup time)"
        ]
      },
      "default": "$(pwd)",
      "override": {
        "env": "[REPO_NAME_UPPER]_INSTALL_ROOT"
      }
    }
  ],
  "packageability_compliance": {
    "declared": true
  }
}
```

<!-- Negative-spec: the `override` block must use the unified `{flag?, env?}` vocabulary — NOT
     the retired `{mechanism, name}` shape, which the schema's `additionalProperties:false`
     rejects and which fails `validate-install-contract.py` point-6's
     `.override | (.flag // .env)` check. The seed must also include
     `standalone_setup_script.entry_point_contract`, required by point-2 — omitting it leaves a
     manifest that is schema-valid but validator-failing despite
     `packageability_compliance.declared: true`. -->

This is the MINIMAL compliant shape, not a complete one — it declares points 1 (via
`functional_probe`/`remediation` once `direct_deps` gains entries), 4 (`tested_platforms: []` — an
honest "no platform verified yet" claim for a fresh repo, NOT an unbacked `["macos"]`; the field is
derived from `state/platform-outcomes/` records once they exist, and empty is schema-valid), 5
(`packageability_compliance.declared: true`, checked by `validate-install-contract.py` only when a
repo opts in), and 6 (`configurable_locations`, one worked example) at the smallest shape that
passes `validate-install-contract.py`. `direct_deps: []` and `required_env_vars: []` are legitimately
empty for a fresh repo with no upstream deps yet — the packageability checks that key on
non-empty `direct_deps` entries (point 1's per-dep remediation, point 2's `entry_point_contract`)
simply have nothing to check yet. `standalone_setup_script.posix`/`.windows` point at
conventional-but-not-yet-created paths (`scripts/setup.sh`/`.ps1`) — this repo's own onboarding
work creates those scripts; the manifest declares the contract shape ahead of the scripts existing,
consistent with "inherits the contract at birth" rather than "inherits it once someone remembers."
The optional top-level `programmatic_entry_point` field is deliberately omitted from this greenfield
seed because a fresh repo's `scripts/setup.sh` unifies chain-walk and install into one script, so
Point-2 falls back to `standalone_setup_script.entry_point_contract` until (if ever) this repo grows
a separate non-interactive install entry point distinct from its setup script (see
`docs/install/AGENT.md` § Packageability contract for the PREFERRED/FALLBACK precedence rule).

**Point 5 stay-in-shape applies from the first dependency this repo adds onward** — see the
code-reviewer's install-surface coverage lens (`agents/code-reviewer.md § Install-surface coverage
lens`), which fires on any diff adding a dep/prereq/env-var without a paired manifest update in the
same commit.

Record `docs/install/agent-install-manifest.json` under `### Created` in the Phase 4 REPORT (or
`### Already Existed` if the skip-if-present branch fired).

### Phase 3l. Strategic self-description skeleton (ALWAYS — idempotent)

Born-compliant emit-hold, same shape as Phase 3k: a repo is born WITH a conformant,
provenance-marked skeleton `state/strategic/self-description.yaml` (schema:
`coordinator/schemas/strategic-self-description.schema.json`) plus a curation prompt — NOT a hard
onboarding gate that blocks until full vision/OKRs are authored. **Skip entirely if
`state/strategic/self-description.yaml` already exists** — never overwrites a curated instance.

Scaffold via `coordinator:strategic-self-description-refresh`'s skeleton-authoring path (or the
authoring surface named in its SKILL.md) with every field's provenance marked `asserted` or absent
(present-as-null) until a human ratifies. After scaffolding, prompt once:

> Strategic self-description skeleton written to `state/strategic/self-description.yaml` — curate
> vision/lifecycle/CTA now, or leave for the weekly refresh nudge (`/workweek-complete` Step 4i)?

**Fold the same offer into this curation prompt** — do not run a second, separate ask. This reads
like <inferred domain> work — want me to record which inspirations / peers / competitors /
aspirational-targets you have in mind? It goes in the same `state/strategic/self-description.yaml`
skeleton just scaffolded and makes later deliverable planning easier. (Skip freely — it's an offer,
not a gate.) On opt-in, write each named entity into the `competitors[]` array of the
already-scaffolded skeleton (schema: `coordinator/schemas/strategic-self-description.schema.json`)
— `name`, `relationship` (`competitor | peer | aspirational-target | complement | prior-art |
superseded-by | supersedes`), `note`, `provenance: curated`. This is the same self-description
artifact and the same authoring surface referenced above; there is no second marking store.

Record under `### Created` (or `### Already Existed`) in the Phase 4 REPORT. **Presence/staleness is
advisory, not a gate** — an absent or stale instance never blocks onboarding completion; it surfaces
the same way other advisory seeds do (Phase 4 status table note), consistent with the
generated-draft → human-ratify → curated reconciliation model owned by the refresh skill.

### Phase 3m. Guard-regression tripwire tests (ALWAYS — idempotent)

Unlike the Windows console-subprocess and cross-platform-CI tripwires under **Optional Tripwire
Installs** (opt-in, PM-offered — see `residue/tripwire-installs.md`), this seed is **ALWAYS installed, not offered** — the whole
point is that a repo gets this protection automatically at birth, the same way it gets
`fast_test_cmd` or the health ledger in Phase 3j, rather than depending on an operator accepting
an offer. Skip a file individually (idempotent no-op) if it already exists at the destination —
never overwrite a customized copy (an operator may have edited an `EXACT_FILES` allowlist in
place).

**Destination is derived from `fast_test_cmd`, never hardcoded to `tests/guards/` at the repo
root.** Provisioning the files is not the whole job — a guard test that pytest never collects is
indistinguishable from no guard at all (this is exactly the defect the doctrine-plane repo's own copy of this
step shipped with: `tests/guards/` at the repo root while its `fast_test_cmd` was scoped to
`python -m pytest coordinator/tests`, so the guards sat on disk, `ls`-visible, run by nothing —
a regression gate named `test_guard_templates_reachable_by_test_runner` catches a repeat of
exactly that shape, by asserting the guards directory the step creates is actually collected by
the configured runner). Parse the path argument off this repo's own
`fast_test_cmd` line in `coordinator.local.md` (the `<path>` in `python -m pytest <path>` /
`pytest <path>`) and create `<that-path>/guards/` — e.g. `tests/guards/` when `fast_test_cmd` is
scoped to `pytest tests`, `coordinator/tests/guards/` when it is scoped to `pytest
coordinator/tests`. If `fast_test_cmd` has no parseable path argument (a bare `pytest` with no
scope, or a non-pytest test runner), fall back to `tests/guards/` at the repo root — pytest's
default collection root — and note the fallback in the Phase 4 REPORT so the PM can verify
reachability by hand.

Create the resolved `<scope>/guards/` directory if absent, then copy each of these four files
from `<coordinator-plugin-root>/tests/templates/` (resolve `<coordinator-plugin-root>` the same way
the rest of this skill does) into `<scope>/guards/` in the target repo, no-clobber:

- `test_machine_local_state_tracked.py` — flags tracked files that bake in a machine-absolute
  home path (content-scanned, JSON/YAML/dotfile-state only) or match a known kill-switch /
  last-known-good-snapshot filename shape.
- `test_foreign_platform_paths.py` — flags tracked config carrying a path whose syntax belongs
  to a platform other than the one running the test (Windows drive-letter path on a POSIX host,
  or vice versa), a path mixing `\` and `/` separators within one token, or a UNC path on a
  non-Windows host. (Note: matches a single-segment drive-letter path — drive letter, colon,
  backslash, then one directory name, with nothing after it — as well as multi-segment ones;
  an earlier revision of this template's regex missed the
  single-segment shape, which is the exact form a real 2026-07-28 incident hit; fixed the same
  day it was found.)
- `test_registry_toml_machine_paths.py` — conditional on the target repo carrying a tracked file
  named `registry.toml` anywhere (the coordinator machine-local registry convention); a no-op
  (zero findings) elsewhere. When such a file exists, flags any string value shaped like an
  absolute path — a tracked `registry.toml` must declare keys only; the actual per-machine path
  values belong in the gitignored `registry.local.toml` sibling.
- `test_guard_wiring_completeness.py` — conditional on the target repo shipping its own
  `hooks/hooks.json`-shaped surface; a no-op (zero findings) elsewhere. When such a surface
  exists, flags `guard-*` scripts never referenced from hooks.json (directly or via a wrapper
  `.sh` file it invokes), and the silent-skip shape — an existence test guarding a script
  invocation with no `else` branch, so an absent script passes unnoticed — in any `.sh` file
  hooks.json references.

Each template is self-contained (stdlib + `git`, `test_registry_toml_machine_paths.py` also uses
stdlib `tomllib`, Python 3.11+) and runs standalone (`python <scope>/guards/<file>.py`) or under
pytest — no new dependency is introduced. Each template's own docstring documents its detection
heuristic and limits in full; do not duplicate that here.

**Repo-root resolution is automatic — no hop-count surgery.** Each template resolves its
`REPO_ROOT` via the shared `_tripwire_root.resolve_repo_root()`: the `TRIPWIRE_REPO_ROOT` env
override wins outright, otherwise it walks upward from the template's own `__file__` for the
first ancestor containing a `.git` entry — correct at any `<scope>` nesting depth with no per-repo
edit. Copy `_tripwire_root.py` alongside the templates in `<scope>/guards/` — every template
imports it as a same-directory sibling.

**Scope note — "unclassified absolute paths" was considered and deliberately narrowed.** An
earlier draft of this brief asked for a blanket check flagging any absolute path in tracked
config lacking positive proof of portability. That blanket form was not built: a generic
consumer repo can legitimately carry absolute paths with nothing to do with machine identity
(container paths, systemd unit paths, deployment mount points), and flagging all of them would
be exactly the ignored-noise failure mode this effort exists to prevent. The safely-narrow slice
of that risk is covered by the two checks above that target unambiguous shapes (home-directory
paths, and `registry.toml` path values) — see `test_registry_toml_machine_paths.py`'s own
docstring for the full reasoning.

**Why ALWAYS, not offered.** The failure class these tests catch is invisible until it causes an
outage (four bricked sessions on one day) — an opt-in offer is exactly the shape that let the
five guards this incident is named after ship untested-in-practice for weeks. Every check is
designed to prefer silence over a false positive (documented per-check in each template's
docstring), so an ALWAYS install carries negligible noise risk against a repo with none of these
problems.

Record `<scope>/guards/` under `### Created` in the Phase 4 REPORT (or `### Already Existed` if
every target file was already present).

**Verify reachability, don't just assume it.** After copying, confirm the guards are actually
collected by the repo's own `fast_test_cmd` (e.g. run it and check the new `test_*` node ids
appear) rather than trusting the path arithmetic above blindly — this step exists precisely
because that trust broke once already. A companion regression gate named
`test_guard_templates_reachable_by_test_runner`, carried in the coordinator plugin source, catches
a repeat of the "present on disk, run by nothing" shape in the authoring repo's own suite; a target
repo onboarded via this skill does not automatically inherit that gate and should either add an
equivalent check or rely on the reachability confirmation above.

#### 3x. Fleet memo-destination registration

Single-repo `/repo-setup` scaffolds the in-repo `cross-repo/inbox/` CHANNEL (Phase 3e, via the engine-plane `coordinator_core.install.scaffold_structure` CLI), but that channel has no ADDRESS until this repo is also registered as a `repos.<name>` entry in the machine-local registry — per `bin/cross-repo-memo`, a repo becomes an addressable `--to <name>-em` receiver only through that registry entry. Without this step a freshly-onboarded repo is a receiving channel no sibling EM can find. This mirrors `coordinator:install`'s F16 fix (`register-discovered-repos.py`, commit `43182780`) — same registry, same only-if-absent discipline, applied at single-repo onboarding time instead of fleet-discovery time.

**Offer, don't nag.** Default YES for working repos (Phase-1 classification (a) working or (c) both — the tracked-session-artifact case where sibling EMs plausibly need to reach this repo). Default skip (offer still shown, default answer no) for (b) published-artifact repos — a distribution repo is not something a sibling EM addresses directly.

> Register this repo as a fleet memo destination so sibling EMs can `--to <name>-em` it? [Y/n]

On accept, register this repo — only-if-absent, never clobbering an existing `repos.<key>` value — via `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/repo-setup-args-and-register" register-repo`. It derives `<key>` the same way `cross-repo-memo`'s `_receiver_repo_key` (`${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/_machine_local.py`) resolves `--to <name>-em`: lowercase basename, non-alnum runs collapsed to a single `_`, leading/trailing `_` stripped — and prints `repos.<key> already registered — leaving as-is.` or `repos.<key> registered -> <path>`.

Then append a row to `~/.claude/working-repos.yaml` under the `repos:` list, only-if-absent (skip if a row with this `path` already exists), matching the existing row shape:

```yaml
  - path: <absolute path, same OS-native form as sibling rows>
    posix_path: <posix-normalized path>
    purpose: <one-line from README H1/lead paragraph, or the Phase 2 project description if README is absent>
    source: repo-setup
```

On decline: skip both writes and note the decline for Phase 4 (see below).

**Phase 4 REPORT surfacing.** After Phase 3 completes, check whether this repo is now a memo destination (`machine-local has "repos.$_repo_key"`):

- **Registered this run:** add a `### Created` line — `Registered as fleet memo destination: repos.{key} → {path}`.
- **Still NOT a memo destination** (registration declined, skipped, or `machine-local` unavailable): surface LOUDLY under `### Needs Attention`:

  > This repo is not yet a fleet memo destination — sibling EMs cannot `--to <name>-em` it. Run: `machine-local set repos.<name> <path>` and add a working-repos.yaml row. `<name>` = lowercased basename with every non-alnum run collapsed to a single underscore (matching cross-repo-memo's `-em` resolution).
