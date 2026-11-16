---
name: repo-setup
description: First-time setup for an existing repo, single or --batch.
version: 2.0.0
allowed-tools: ["Read","Write","Edit","Bash","Grep","Glob","Agent","Skill","AskUserQuestion","TaskCreate","TaskUpdate","TaskGet","TaskList"]
---

# Repo Setup

## When to Use

- First work in a project repository, or `/update-docs` reports `tracker_missing`.
- **Creating a NEW repo from scratch**? → `coordinator:new-project` (scaffolds a stack, delegates onboarding back here).

**The engine repo is a hard prerequisite** — resolved via `CLAUDE_KLABAUTER_ROOT` / the machine-local
`repos.claude_klabauter` registry entry — and must resolve before this skill's fences will run.

**Setup is sufficient — downstream skills add-to, never create-from-scratch.** It produces the minimum-viable skeleton (`state/orientation_cache.md`, `docs/README.md`, `CLAUDE.md`); `/update-docs` and `/workstream-start` add to it.

## Lanes

Every invocation fires exactly one lane — `new-project`, `add-existing-project`, `add-repo` — each
a pre-answered round-trip set: `lanes/CONTRACT.md` (shape), `lanes/<lane>.yaml` (values),
`residue/<lane>.md` (rationale). The op parameter (or the caller's `p1.repo-classification-ask` answer) names it. `--batch` is an entry-point mode, not a
fourth lane — it drives the `add-existing-project` answers per repo (`residue/batch-mode.md`).

**Lane rule.** A repo with no code to read (no commits, or only an H1-only README) fires `new-project`, which skips Phase 1.5 (`p15.skip-gate-empty-repo`); a repo with commits or code fires `add-existing-project`.

## Flag contract

- **Default (no flag) — single-repo, `new-project` or `add-existing-project` lane**, from inside one repo's cwd.
- **`--root <path>` (alias `--target <path>`) — single-repo only, optional.** Onboards a sibling repo by path without cd-ing into it; defaults to `$(pwd)`. Orthogonal to `--batch`. Resolution: § Procedure.
- **`--batch` — fleet non-interactive.** See `residue/batch-mode.md`.
- **`--non-interactive` (single repo, valid without `--batch`).** Asks nothing: every judgment point takes the lane's `lanes/<lane>.yaml` value and the unattended-halt set (§ Procedure step 4) returns unresolved to the caller. Name from `coordinator.local.md` or the directory name, type from detection.
- **`--answers <file.json | inline-json>` (single repo).** JSON passed through to the op (step 3); a key overrides that step's lane value, unlisted steps take the lane value. Implies `--non-interactive`. The op owns the key set and folds aliases.
- **`--check-only` is batch-mode-only.** Passed to the default single-repo mode, exit with: `"--check-only is only valid with --batch; for a single repo use --non-interactive or --answers."`

Run from the project's directory (not `~/.claude`) or pass `--root`/`--target`.

## Procedure

**1. Resolve `$_TARGET_ROOT`** (run before everything else). (shape per `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`; PowerShell shown) `& "$env:COORDINATOR_SETTINGS_HOME\bin\repo-setup-args-and-register.exe" resolve-target-root`. It prints the absolute path of an existing directory inside a git repo, else `ERROR: ...` on stderr with exit 1 — mirror that, never fall back to cwd. With an explicit `--root`/`--target`, first `cd` to `$_TARGET_ROOT`. Absent, it resolves to `$(pwd)`.

**2. Load the firing lane's directives.** Read `lanes/<lane>.yaml` in full: `round_trip_directives[]` supplies every value the procedure would otherwise prompt for, `terminal_offer_defaults[]` every terminal-offer default, `second_phase_deferred[]` the steps left unresolved. Load once, apply throughout.

**3. Run the `repo.setup` op.** `coordinator-invoke repo.setup '{"root":"<$_TARGET_ROOT>","answers":{...}}'` (launcher shape per the step-1 snippet; `answers` = step-2 values merged with `--answers`, keys `project_name`, `project_type`, `project_subtypes`, `workstreams`, `description`, `cross_platform`, `register_repo`). The op is create-if-absent and asks nothing. Verdict `{created, already_existed, open, needs_attention}`: report `created` and `already_existed`, and return every `open` item (it carries its manual command) and every `needs_attention` item to the caller unresolved. Read `residue/mechanics.md` only for a step an `open` item names; take no value from a prompt. The op scaffolds `state/metrics/<register_id>/register.jsonl` and the `structured_records` stanza (`EVERY-PROJECT-CARRIES-A-METRIC-REGISTER`, `coordinator/docs/wiki/planning/metric-register.md`).

**4. UNATTENDED-HALT SET.** `p3j.1-test-cmd-detect`, `p3m.verify-reachability`, `tw.windows-console-verify-run`, `batch.hook-respect` are never pre-answered by any lane (`lanes/CONTRACT.md`) — return them unresolved to the caller as the op's `open` items.

**5. Roster.** Report the lane's `roster_slots[]` verbatim in the Phase 4 output (materializing it is a later ceremony's job).

**5a. Posture overlay.** Read `engagement_posture` from `${CLAUDE_HOME:-$HOME}/.claude/coordinator-identity.yaml`; when set, run `render-posture-overlay <posture> "$_TARGET_ROOT/.claude/em-context.md"` (same call as `commands/install.md`'s engagement-posture step, including its `.gitignore` check). Absent, skip silently; re-running is safe.

**5b. LSP index scope.** Copy `templates/pyrightconfig.json.template` to `$_TARGET_ROOT/pyrightconfig.json` only when none exists and `pyproject.toml` has no `[tool.pyright]`; copy `templates/clangd.template` to `$_TARGET_ROOT/.clangd` only when none exists or the existing one carries the `coordinator-managed` marker line, never over an unmarked file (warn instead). Tsconfig is project-owned: report that each `tsconfig.json` `exclude` needs `scratch`, `data`, `exports` and `node_modules`, and edit none.

**6. Sentinel.** As the final action, write a session-scoped sentinel so `/workstream-start` (if invoked in this same session) prints its one-line setup notice and then runs orientation once: create `state/` if absent, then touch `state/.repo-setup-just-ran`. Single-shot; MUST be gitignored (`residue/mechanics.md`).

## Optional Tripwire Installs

`residue/tripwire-installs.md`; the lane's `terminal_offer_defaults[]` (`tw.windows-console-offer`) decides whether an offer fires. A Perforce workspace registers per `contract/p4-provider-fragment.md` § Registration.

## Notes

- **Embedding-class check.** Where this flow touches project-rag indexing, ask whether the corpus needs `text`-class embedding.
- Any onboarding bug fix needs all three layers to not recur: prevention (the install script), reactive repair (`doctor`-style), a troubleshooting row keyed on the literal error text.
- Peer-repo `file:line` citations go in the workstream entry's `specs[]`/`deliverables[].text`, never `state/orientation_cache.md`.
