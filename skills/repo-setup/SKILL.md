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

**Setup is sufficient — downstream skills add-to, never create-from-scratch.** This skill produces the minimum-viable **skeleton** (`state/orientation_cache.md`, `docs/README.md`, `CLAUDE.md`); `/update-docs` and `/workstream-start` add to it.

## Lanes

Every invocation fires exactly one lane — `new-project`, `add-existing-project`, `add-repo` — each
a pre-answered round-trip set: `lanes/CONTRACT.md` (shape), `lanes/<lane>.yaml` (values),
`residue/<lane>.md` (rationale). The op parameter (or the
caller's answer to `p1.repo-classification-ask`) names it. `--batch` is an entry-point mode, not a
fourth lane — it drives the `add-existing-project` answers per repo (`residue/batch-mode.md`).

## Flag contract

- **Default (no flag) — single-repo, `new-project` or `add-existing-project` lane**, from inside one repo's cwd.
- **`--root <path>` (alias `--target <path>`) — single-repo only, optional.** Onboards a sibling repo by path without cd-ing into it; defaults to `$(pwd)`. Orthogonal to `--batch`. Resolution: § Procedure.
- **`--batch` — fleet non-interactive.** See `residue/batch-mode.md`.
- **`--non-interactive` (single repo, valid without `--batch`).** Asks nothing: every judgment point takes the lane's `lanes/<lane>.yaml` value and the unattended-halt set (§ Procedure step 4) returns unresolved to the caller. Name from `coordinator.local.md` or the directory name, type from detection.
- **`--answers <file.json | inline-json>` (single repo).** JSON keyed by lane `step_id` (`p2.ask-project-name`, `p2.ask-project-type`, `p2.ask-workstreams`, ...) overriding that step's lane value; unlisted steps take the lane value. Implies `--non-interactive`; an unknown key fails loud, naming it.
- **`--check-only` is batch-mode-only.** Passed to the default single-repo mode, exit with: `"--check-only is only valid with --batch; for a single repo use --non-interactive or --answers."`

Run from the project's directory (not `~/.claude`) or pass `--root`/`--target`.

## Procedure

**1. Resolve `$_TARGET_ROOT`** (run before everything else). (shape per `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`; PowerShell shown) `& "$env:COORDINATOR_SETTINGS_HOME\bin\repo-setup-args-and-register.exe" resolve-target-root`. It prints the absolute path of an existing directory inside a git repo, else a fail-loud `ERROR: ...` on stderr with exit 1 — mirror that, never silently fall back to cwd. With an explicit `--root`/`--target`, first `cd` to `$_TARGET_ROOT` so every cwd-relative step targets that repo. Absent, it resolves to `$(pwd)`.

**2. Load the firing lane's directives.** Read `lanes/<lane>.yaml` in full: `round_trip_directives[]` supplies every value the procedure would otherwise prompt for, `terminal_offer_defaults[]` every terminal-offer default, `second_phase_deferred[]` the steps left unresolved. Load once, apply throughout.

**3. Run the lane-independent mechanical procedure.** Read `residue/mechanics.md` and execute it in full. Substitute the lane's directive/default values at every judgment point; take no value from a prompt.

**4. UNATTENDED-HALT SET.** `p3j.1-test-cmd-detect`, `p3m.verify-reachability`, `tw.windows-console-verify-run`, `batch.hook-respect` are never pre-answered by any lane (`lanes/CONTRACT.md`) — return them unresolved to the calling agent/PM as mechanics.md surfaces them.

**5. Roster.** Report the lane's `roster_slots[]` verbatim in the Phase 4 output (materializing it is a later ceremony's job).

**5a. Posture overlay.** Read `engagement_posture` from `${CLAUDE_HOME:-$HOME}/.claude/coordinator-identity.yaml`; when set, run `render-posture-overlay <posture> "$_TARGET_ROOT/.claude/em-context.md"` (same call as `commands/install.md`'s engagement-posture step, including its `.gitignore` check). Absent, skip silently; re-running is safe.

**6. Sentinel.** As the final action, write a session-scoped sentinel so `/workstream-start` (if invoked in this same session) prints its one-line setup notice and then runs orientation once: create `state/` if absent, then touch `state/.repo-setup-just-ran`. Single-shot; MUST be gitignored (`residue/mechanics.md`).

## Optional Tripwire Installs

`residue/tripwire-installs.md`; whether an offer fires is the lane's
`terminal_offer_defaults[]` value (`tw.windows-console-offer`). A Perforce workspace registers per `contract/p4-provider-fragment.md` § Registration.

## Notes

- **Embedding-class check.** Where this flow touches project-rag indexing, ask whether the corpus needs `text`-class embedding.
- Any onboarding bug fix needs all three layers to not recur: prevention (fix the install script), reactive repair (`doctor`-style recovery), searchable docs (a troubleshooting row keyed on the literal error text).
- Peer-repo `file:line` citations land in the `state/workstreams/<id>.yaml` entry's `specs[]` or
  `deliverables[].text`, never in `state/orientation_cache.md` (name-only, capped at 10 entries).
