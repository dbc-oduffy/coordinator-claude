**Project type short-circuit:** Check if `coordinator.local.md` exists at the repo root.

If it exists, read it and capture `project_type`, `project_subtypes`, and `cross_platform` (all optional). Record `_CROSS_PLATFORM_DECLARED=true` when `cross_platform: true` is present. Emit a one-line confirmation:

> Project type: {type}{ +subtypes: [{subtypes}] if any}. From coordinator.local.md — skipping Phase 2 question 2.

If `coordinator.local.md`'s `project_type` differs from the `detected_type` derived from the marker scan, append this one-line challenge immediately after the confirmation (PM remains authoritative — this is informational only, not a re-ask):

> *`coordinator.local.md` says `{type}` but detected stack is mostly `{detected_type}` — keeping the file value (PM authoritative). If wrong, edit `coordinator.local.md` and re-run.*

If `coordinator.local.md` is missing, proceed to Phase 2 question 2 (cold-ask) as normal.

Also check for legacy values in the file: if `project_type` is `unreal`, `meta`, or bare `web`, emit a one-line warning with the migration hint (e.g. `unreal` → `project_type: game-dev` + `project_subtypes: [unreal]`). Do not auto-rewrite.

**`cross_platform` inference (when absent from `coordinator.local.md` or when `coordinator.local.md` does not exist):** Run the cross-platform inference signal check and store results for the "Optional Tripwire Installs" offer later in this run. Two signals, either is sufficient:

- **(a)** A `.github/workflows/*.yml` file carries an `os:` matrix with multiple entries (more than one OS value present — e.g. `ubuntu-latest` plus `macos-latest` and/or `windows-latest`).
- **(b)** `*.sh` files exist in `bin/` AND a Windows-operator marker is present in `coordinator.local.md` (e.g. `project_type` or a custom field that implies Windows as a primary development environment).

If either fires, set `_CROSS_PLATFORM_INFERRED=true` and record `_CROSS_PLATFORM_SIGNAL` as a human-readable description of which signal fired (e.g. `"detected: OS matrix with 3 entries in .github/workflows/ci.yml"`). **Do NOT auto-write `cross_platform: true`** — the correct shape is detect-then-ask; the offer prompt fires in "Optional Tripwire Installs." Detect-then-silently-pick is a footgun: an incorrect auto-enable installs a pytest CI snippet into a TypeScript repo.

**Negative check — suppress duplicate install offer:** Before setting `_CROSS_PLATFORM_INFERRED=true`, check whether `templates/ci/cross-platform-matrix.snippet.yml` already exists in the repo (or a consumer copy at an equivalent path). If signal (a) fires AND the snippet file is already present, the repo has already adopted the CI discipline — suppress the install offer and emit a one-line note instead:

> _CI reference already installed (`templates/ci/cross-platform-matrix.snippet.yml` present) — skipping cross-platform install offer._

Set `_CROSS_PLATFORM_INFERRED=false` (or leave unset) in this case. The signal correctly fired; the action it normally triggers is already done. This prevents the offer from self-firing on the meta-repo itself (which dogfoods the matrix as of C6) and on any consumer repo that has already copied the snippet.

**Runtime marker scan:** Run `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/detect-project-runtime"` — the marker scan is advisory, so warn and continue (do not abort onboarding) if the forwarder or its engine-plane target is unresolvable: `⚠ detect-project-runtime not found — skipping advisory runtime detection (coordinator plugin install may be incomplete, or the engine-plane root unresolved). PM's answer to Phase 2 question 2 remains authoritative.`

Capture the output. Show to PM in Phase 2 above question 2 as `_(detected stack: <one-line summary>)_`. PM's answer is authoritative; detection is sanity-check only. Output is advisory stdout — no skill/agent/hook reads it programmatically; adding a consumer requires a separate plan.

**Derived type from markers:** Once the marker scan returns, derive a `detected_type` (and `detected_subtypes` if applicable) using these rules, in priority order:

- `*.uplugin` or `*.uproject` present → `detected_type: game-dev`, `detected_subtypes: [unreal]`
- `package.json` + any of `next.config.js`, `vite.config.*`, `nuxt.config.*`, `svelte.config.*`, `remix.config.*` present → `detected_type: web-dev`
- `requirements.txt` or `pyproject.toml` present (and no UE markers) → `detected_type: data-science`
- `Cargo.toml`, `go.mod`, or none of the above → `detected_type: general`

Capture these as part of the Phase 1 profile. If `coordinator.local.md` already exists and its `project_type` differs from `detected_type`, emit a one-line challenge inline in the Phase 1 report (see **Project type short-circuit** block above for the exact wording).

**coordinator_whoami availability (install-surface-completeness):**

The Phase 4 binding probe (`python3 -m coordinator_whoami.project_rag`) requires the `coordinator_whoami` package. On a fresh machine where this is the first onboarded repo, the package is not yet installed. Probe and install idempotently — owning the binding-probe contract this skill advertises rather than punting to a separate meta-package command — via `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/repo-setup-args-and-register" whoami-status` (add `--check-only` when batch mode's `CHECK_ONLY=1` is active). It never exits non-zero (matching the original never-block contract) and prints `whoami_status: <ready|installed|would-install|failed>` to stdout, plus a following `pip_stderr: ...` line when the status is `failed`.

Record `coordinator_whoami: <whoami_status>` in the Phase 4 status table.

- **`ready`:** package was already importable — no mutation.
- **`installed`:** `pip install -e` succeeded; binding probe will work in Phase 4.
- **`would-install`:** `--check-only` is set; package missing; no mutation. Reported in status table.
- **`failed`:** pip itself errored (no Python, no pip, or pip exit non-zero). Do NOT halt the skill — Phase 4's existing `ModuleNotFoundError` fallback (`Run /coordinator:install to install the introspection package.`) remains the last-resort signal. Log pip stderr (captured in `pip_stderr`) to the status table notes.

Idempotent: re-running the skill on an already-bootstrapped repo short-circuits at the `import` probe with no pip invocation.
