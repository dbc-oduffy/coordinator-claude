---
name: new-project
description: "Scaffolds and onboards a new repo (vs. repo-setup's onboard-existing)."
version: 1.0.0
---

# coordinator:new-project

<!-- Purpose: greenfield repo creator. Owns creation + stack scaffolding; DELEGATES coordinator
     onboarding to coordinator:repo-setup — never re-implement the onboarding half. -->

## When to Use

Creating a brand-new repo from scratch, from any cwd. Contrast with **`coordinator:repo-setup`**,
which onboards an *existing* folder you are already inside — this skill creates the folder first
and scaffolds real source, then delegates onboarding to repo-setup.

**Not for:** onboarding an existing repo (`coordinator:repo-setup`), fleet/multi-repo setup
(`coordinator:repo-setup --batch`), monorepo/workspace scaffolds, CI/deploy wiring (out of scope
v1).

## Inputs (promptable, with defaults)

| Input | Flag | Default | Notes |
|-------|------|---------|-------|
| Project name | `--name <n>` | **required** | dir name + `package.json` name; prompt if absent. |
| Parent dir | `--parent <dir>` | `$HOME/Code_Projects` | flag → `COORDINATOR_PROJECTS_ROOT` env → default; created if absent. |
| Stack template | `--template next-app\|empty` | `next-app` | `next-app` = Next/React/TS/Tailwind/Vitest; `empty` = git + onboarding only. |
| Remote | `--remote none\|private\|public` | `none` | opt-in only; never defaults to public, never creates a remote unasked. |

## Flow

**1 — Resolve + validate inputs.** Gather name (ask if absent), parent, template, remote.

**2 — Create + scaffold.** The helper resolves the parent, fails loud on an occupied non-empty
target dir, `mkdir`s, `git init`s (`main` default branch), renders the template
(`{{PROJECT_NAME}}` tokens), seeds `coordinator.local.md` (with `project_type` pre-set) and a
minimal `README.md`, and for `next-app` runs the boot smoke (`pnpm install` + `pnpm typecheck` +
`pnpm test`):

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/new-project-scaffold" --name "<name>" --parent "<parent>" --template "<template>"
```

A template that does not boot is a **failed scaffold** — report it, don't work around it.
<!-- engine-gap: field=new_project.scaffold.file_manifest producer=unknown memo=2026-08-14-doe-claude-em-three-cut-obligations-from-the-corpus-grind.md -->

**3 — `cd` into the new dir, assert cwd.** This session's `CLAUDE.md`/`coordinator.local.md` are
cwd-scoped to where it started, not the new project — Phase 4's onboarding needs the Bash-tool
cwd moved first. `cd` in its own Bash call (never a compound `cd &&`), then assert:

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/assert-cwd" "<new-dir-abs>"
```

**4 — Delegate onboarding to `coordinator:repo-setup`** against the new dir — it produces the
coordinator artifacts (CLAUDE.md, tracker, README index, orientation cache, `state/` skeleton,
git hooks, currency stamp, starter `agent-install-manifest.json`). Never re-implement this half
here (`NEW-PROJECT-REPO-SETUP-BOUNDARY` tripwire). Phase 2's `project_type` seed means repo-setup
skips its type question — expect ~1-2 ratify-prompts (name + initial workstreams).

**4.5 — Register in the machine-local registry.** `new-project-scaffold` self-registers the new
dir's absolute path under `repos.<name>` (kebab→snake-cased) via `machine-local set` as part of
scaffolding — required for cross-repo discovery (`machine-local get repos.<name>`, `$REPO_<NAME>`,
the handoff tracker's `--all-repos`, cross-repo memo relay). Nothing further to run; each machine
re-registers on clone. If `machine-local` exits 127 (not installed), run `/coordinator:install`
first, then retry. Optional, for a durable constellation sibling other machines should know
exists: also declare the bare key in the *committed* `<settings-home>/machine-local/registry.toml`
— a shared-registry edit, not for throwaway scaffolds.

**5 — Optional remote (opt-in; never default public).** Only on an explicit `--remote
private|public` choice:

```bash
gh repo create "<name>" --private --source=. --remote=origin --push
```

Substitute `--public` for the public choice. Never create a remote unasked; never default public.

**6 — Scoped first commit** via the engine's scoped-commit helper (explicit `paths`, message
`"<subject>"`) — never `git add -A`/`.`, regardless of hook coverage (the
`BLOCK-BLANKET-GIT-ADD` hook guards only the `~/.claude` meta-repo). Detail: wiki.

**7 — Report the honest boundary.** The current session does NOT become the new project — its
`CLAUDE.md`/`coordinator.local.md` stay cwd-scoped to where it started. Emit a paste-able
launcher:

```
✓ Created <name> at <new-dir> — scaffolded (<template>), onboarded via repo-setup<, pushed to <remote>>.

This session is still cwd-scoped to where it started — it does NOT become the new project.
To start working in it, open a Claude session rooted there:

    cd <new-dir> && claude
```

## Out of scope (v1)

Multi-project/fleet creation (`repo-setup --batch`), monorepo/workspace scaffolds, CI/deploy
wiring, speculative stack templates beyond `next-app`/`empty` (add on real need — instance-#3
rule).

## Negative-spec

- Never silently overwrite an occupied dir — fail loud, surface, stop.
- Never default the remote to public; never create any remote without explicit choice.
- Never re-implement `coordinator:repo-setup`'s onboarding half — delegate.
- Never pretend the current session adopts the new project — Phase 7's launcher is the honest
  handoff.
- Never blanket-add the first commit — the scoped-commit helper only, self-enforced (not
  hook-backstopped for the new repo).
