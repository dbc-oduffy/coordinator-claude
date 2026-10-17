---
name: new-project
description: Scaffold and onboard a new repo.
version: 1.0.0
allowed-tools: ["Read","Write","Edit","Bash","Grep","Glob","Agent","Skill","AskUserQuestion","TaskCreate","TaskUpdate","TaskGet","TaskList"]
---

# coordinator:new-project

<!-- Purpose: greenfield repo creator. Owns creation + stack scaffolding; DELEGATES coordinator
     onboarding to coordinator:repo-setup — never re-implement the onboarding half. -->

## When to Use

Creating a brand-new repo from any cwd. **`coordinator:repo-setup`** onboards an *existing*
folder; this skill creates the folder, scaffolds source, then delegates onboarding to it.

**Not for:** onboarding an existing repo (`coordinator:repo-setup`), fleet/multi-repo setup
(`coordinator:repo-setup --batch`), monorepo/workspace scaffolds, CI/deploy wiring (out of scope
v1).

## Inputs (promptable, with defaults)

| Input | Flag | Default | Notes |
|-------|------|---------|-------|
| Project name | `--name <n>` | **required** | dir name + `package.json` name; prompt if absent. |
| Parent dir | `--parent <dir>` | none — ask, offering `$HOME/projects` | flag → `COORDINATOR_PROJECTS_ROOT` env → `machine-local get coordinator.projects_root` → ask; always passed to the helper explicitly; created if absent. |
| Stack template | `--template next-app\|empty` | `next-app` | `next-app` = Next/React/TS/Tailwind/Vitest; `empty` = git + onboarding only. |
| Remote | `--remote none\|private\|public` | `none` | opt-in only; never defaults to public, never creates a remote unasked. |

## Flow

**1 — Resolve + validate inputs.** Gather name (ask if absent), parent, template, remote.

**2 — Create + scaffold.** The helper fails loud on an occupied non-empty target dir, `mkdir`s,
`git init`s (`main`), renders the template, seeds `coordinator.local.md` (`project_type` set) and
a minimal `README.md`, and for `next-app` runs the boot smoke (`pnpm install`, `typecheck`,
`test`):

Shape W (rung 0) — ladder and shapes: `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`.

    `& "$env:COORDINATOR_SETTINGS_HOME\bin\new-project-scaffold.exe" --name "<name>" --parent "<parent>" --template "<template>"`

A template that does not boot is a **failed scaffold** — report it, don't work around it.
<!-- engine-gap: field=new_project.scaffold.file_manifest producer=unknown memo=engine-gap-markers-name-a-memo-that-was-never-filed.md -->

**3 — Hand off to a session rooted in the new dir.** A `cd` never persists across Bash calls, so
onboard from a session rooted there: launch `claude -p "/coordinator:repo-setup --non-interactive"`
with the new dir as the process working directory (or the installed launcher, run from that dir),
and say so in the report. Never `cd` and assert; never onboard from the creating session.

**4 — Onboard via `coordinator:repo-setup` (in the rooted session from step 3)** — it produces the
coordinator artifacts (CLAUDE.md, tracker, README index, orientation cache, `state/` skeleton,
git hooks, currency stamp, starter `agent-install-manifest.json`). Never re-implement this half
here (`NEW-PROJECT-REPO-SETUP-BOUNDARY` tripwire). Pass the name and project type as
`--answers` so it asks nothing. A general project gets consumer artefacts only (no
`.project-rag-ignore`, `.github/`, `bin/`, `tasks/`) unless the answers ask for them.

**4.5 — Register in the machine-local registry.** `new-project-scaffold` self-registers the new
dir under `repos.<name>` (kebab→snake-cased) via `machine-local set`; a consumer box touches only
its own registry. Nothing further to run. If `machine-local` exits 127, run `/coordinator:install`
and retry. A durable constellation sibling may also declare the bare key in the committed
`<settings-home>/machine-local/registry.toml` — not for throwaway scaffolds.

**5 — Optional remote (opt-in; never default public).** Only on an explicit `--remote
private|public` choice:

```bash
gh repo create "<name>" --private --source=. --remote=origin --push
```

Substitute `--public` for the public choice. Never create a remote unasked; never default public.

**6 — Scoped first commit** via the engine's scoped-commit helper (explicit `paths`, message
`"<subject>"`) — never `git add -A`/`.`, regardless of hook coverage (the
`BLOCK-BLANKET-GIT-ADD` hook guards only the `~/.claude` meta-repo).

**7 — Report the honest boundary.** The current session does NOT become the new project; it stays
cwd-scoped to where it started. Name what was created, scaffolded, onboarded (say so when step 3
ran headlessly) and pushed, and tell the user to open a Claude session rooted in `<new-dir>`.

Out of scope (v1): fleet creation, monorepo scaffolds, CI/deploy wiring, stack templates beyond
`next-app`/`empty` (add on real need).

## Negative-spec

- Never silently overwrite an occupied dir — fail loud, surface, stop.
- Never default the remote to public; never create any remote without explicit choice.
- Never re-implement `coordinator:repo-setup`'s onboarding half — delegate.
- Never pretend the current session adopts the new project or that a `cd` persists — step 3's rooted-session handoff is the honest one.
- Never blanket-add the first commit — the scoped-commit helper only, self-enforced (not
  hook-backstopped for the new repo).
