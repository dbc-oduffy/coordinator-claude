---
name: new-project
description: "Scaffolds and onboards a new repo (vs. repo-setup's onboard-existing)."
version: 1.0.0
---

# coordinator:new-project

<!-- Purpose: single-invocation greenfield repo creator. Owns creation + stack scaffolding; DELEGATES
     coordinator onboarding to coordinator:repo-setup (the compose boundary — never re-implement the
     onboarding half). The outer wrapper repo-setup is not: repo-setup onboards an existing folder you
     are already inside; this skill creates the folder first, from any cwd, and scaffolds real source. -->

## When to Use

- **Creating a brand-new repo from scratch** (greenfield) — from any cwd, including `~/.claude` or an
  unrelated directory.
- Contrast with **`coordinator:repo-setup`**, which onboards an *existing* folder you are already
  inside. The two are siblings: create-new vs onboard-existing. This skill **delegates the onboarding
  half to `coordinator:repo-setup`** rather than reimplementing it.

**When NOT to use:** onboarding an existing repo → `coordinator:repo-setup`. Fleet/multi-repo setup →
`coordinator:repo-setup --batch`. Monorepo / workspace scaffolds, CI/deploy wiring → out of scope (v1).

## Inputs (promptable, with defaults)

| Input | Flag | Default | Notes |
|-------|------|---------|-------|
| Project name | `--name <n>` | **required** | becomes the dir name + `package.json` name. Prompt if absent. |
| Parent dir | `--parent <dir>` | `$HOME/Code_Projects` | resolution order: flag → `COORDINATOR_PROJECTS_ROOT` env → default. Created if absent. |
| Stack template | `--template next-app\|empty` | `next-app` | `next-app` = Next/React/TS/Tailwind/Vitest shell; `empty` = git + onboarding only. |
| Remote | `--remote none\|private\|public` | `none` | external, opt-in. Never defaults to public; never creates a remote without an explicit choice. |

## Flow

### Phase 1 — Resolve + validate inputs

Gather name (required — ask the user if not supplied), parent, template, remote. The scaffold helper
(Phase 2) **fails loud if the target dir already exists and is non-empty** — never silently scaffold
into an occupied directory; surface the conflict and stop.

### Phase 2 — Create + scaffold (delegate to the scaffold helper)

Run the deterministic creation helper — it resolves the parent, guards against an occupied dir,
`mkdir`s the target, `git init`s with the default branch set to `main`, renders the chosen stack
template (tokens like `{{PROJECT_NAME}}` resolved), seeds `coordinator.local.md` (with `project_type`
pre-set so the downstream onboarding skips its type question) and a minimal `README.md` (H1 = project
name), and — for `next-app` — runs the boot smoke (`pnpm install` + `pnpm typecheck` + `pnpm test`):

<!-- TEMPLATE: adapt the resolved values; --no-smoke only for offline/test runs -->
```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/new-project-scaffold" --name "<name>" --parent "<parent>" --template "<template>"
```

A template that does not boot is a **failed scaffold** — report it, do not work around it.

### Phase 3 — `cd` into the new dir, then assert cwd (required guard)

These instructions run in the **current** Claude session, whose `CLAUDE.md` / `coordinator.local.md`
are **cwd-scoped** to wherever the session started — *not* the new project. The onboarding delegation
(Phase 4) relies on the Bash-tool cwd moving into the new dir so the onboarding skill operates on the
right tree. `cd` in its own Bash call (not a compound `cd &&`), then **assert** before proceeding —
this guard prevents scaffolding the wrong tree (worst case `~/.claude`) if cwd inheritance breaks:

<!-- VERBATIM -->
```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/assert-cwd" "<new-dir-abs>"
```

### Phase 4 — Delegate coordinator onboarding to `coordinator:repo-setup`

Invoke **`coordinator:repo-setup`** against the new dir. It produces the coordinator artifacts
(CLAUDE.md, project tracker, README index, orientation cache, the full `state/` skeleton,
auto-push + commit-msg git hooks, concurrent-EM git hardening, the currency stamp, a
packageability-compliant starter `docs/install/agent-install-manifest.json`). **This skill never
re-implements that onboarding half** — creation + stack scaffolding is this skill's job; coordinator
onboarding belongs wholly to `coordinator:repo-setup`. (Re-doing repo-setup's internal onboarding steps
here — canonical-structure scaffolding, hook installation, currency stamping, git hardening — is the
duplication the compose boundary forbids; see the `NEW-PROJECT-REPO-SETUP-BOUNDARY` tripwire.)

Because Phase 2 seeded `coordinator.local.md` with `project_type`, repo-setup skips its project-type
question; expect **~1-2 ratify-prompts** (project name + initial workstreams). This is the accepted
minimal-friction surface, not a defect.

### Phase 4.5 — Register the new repo in the machine-local registry (cross-repo discovery)

A freshly-created repo is invisible to coordinator cross-repo discovery until its path is registered —
sibling-repo lookups (`machine-local get repos.<name>`, `$REPO_<NAME>`, the `repos.*` Python helper),
the DoE handoff tracker (`render-handoff-tracker.py --all-repos`), and any cross-repo memo relay all
resolve paths through this registry. Skipping it is the gap that leaves a just-created project
unreachable by name from other sessions.

Registration is no longer a separate manual step: the `new-project-scaffold` CLI invoked in
Phase 2 self-registers the new dir's **absolute path** under `repos.<name>` (kebab→snake-cased)
via `machine-local` as part of scaffolding, resolving claude-klabauter's root itself. Nothing further
to run here.

`set` writes the per-machine value to `<settings-home>/machine-local/registry.local.toml`
(gitignored, per-machine; settings home resolved via `~/.coordinator-claude-settings/bin/coordinator-settings-home`
or `COORDINATOR_SETTINGS_HOME` — never hardcode `~/.claude/machine-local`, which does not exist) —
that alone makes `get`/`$REPO_*` resolve; **no commit is required and the path never leaves this
machine.** Each machine registers its own checkout (on clone, re-run the `set` there). If the
`machine-local` binary exits 127 ("command not found" / "resolver not installed" / claude-klabauter
unresolved), run `/coordinator:install` (Phase 3) first to install the coordinator infra, then
retry this step.

**Optional, for a first-class constellation sibling** (a repo other machines should know exists, like
an OSS root paired with coordinator): also declare the bare key in the *committed* schema
`<settings-home>/machine-local/registry.toml` (`"repos.<name>" = ""`). That declaration is a
shared-registry edit — do it only when the project is a durable sibling, not a throwaway scaffold.
The `set` above is the always-on step; the schema declaration is the sometimes-on polish.

### Phase 5 — Optional remote (opt-in; never default public)

The remote defaults to `none`. **Only** when the user explicitly chose `private` or `public`, create
and push the remote — an external, hard-to-reverse action:

<!-- TEMPLATE: only runs on explicit --remote private|public; never on the none default -->
```bash
gh repo create "<name>" --private --source=. --remote=origin --push
```

Substitute `--public` in place of `--private` above when the user explicitly chose the `public`
visibility option.

Never create a remote without an explicit opt-in; never default to `public`.

### Phase 6 — Scoped first commit

Commit the created tree via `ceremony.scoped_git_commit` (claude-klabauter; `paths`, message
`"<subject>"`) — it selects the agree-case vs. private-index form for you, so the new repo's
first commit is scoped exactly like any coordinator commit despite the `BLOCK-BLANKET-GIT-ADD`
hook guarding only the `~/.claude` meta-repo. Never `git add -A` / `git add .` — explicit-path is
coordinator doctrine here regardless of hook coverage. → `docs/wiki/scoped-safety-commits.md § The trailing pathspec is a proxy for scope, valid only while index and worktree agree`.

### Phase 7 — What's next (the honest boundary)

Print a clear close-out. Be truthful about the session boundary: **the current session does NOT become
the new project.** Because `CLAUDE.md` / `coordinator.local.md` are **cwd-scoped** to where this
session started, the new project's project-scoped instructions will not auto-load here. Emit a
paste-able launcher so the user can open a session rooted in (and cwd-scoped to) the new dir:

<!-- TEMPLATE: substitute the new dir -->
```
✓ Created <name> at <new-dir> — scaffolded (<template>), onboarded via repo-setup<, pushed to <remote>>.

This session is still cwd-scoped to where it started — it does NOT become the new project.
To start working in it, open a Claude session rooted there:

    cd <new-dir> && claude
```

## Out of scope (v1)

- Multi-project / fleet creation → `coordinator:repo-setup --batch` (for existing repos).
- Monorepo / workspace scaffolds — single-package only.
- CI / deploy wiring (GitHub Actions, hosting) — creation + local-dev-ready is the bar.
- Speculative stack templates (python, rust, node-lib) — ship `next-app` + `empty`; add others when a
  real need surfaces (instance-#3 rule).

## Negative-spec

- **Never silently overwrite an occupied dir** — the scaffold helper fails loud; surface and stop.
- **Never default the remote to public; never create any remote without an explicit choice.**
- **Never re-implement `coordinator:repo-setup`'s onboarding half** — delegate. Owning creation + stack
  here and onboarding there is the whole point of the compose.
- **Never pretend the current session adopts the new project** — the cwd/CLAUDE.md boundary is real;
  the Phase 7 launcher is the honest handoff.
- **Never use blanket-add for the new project's first commit** — use `ceremony.scoped_git_commit`
  (explicit-path, per coordinator scoped-commit doctrine). The blanket-add hook does not cover the new repo
  (it guards only `~/.claude`); the discipline is self-enforced, not hook-backstopped.
