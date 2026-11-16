---
name: new-project
description: Scaffold and onboard a new repo.
version: 1.0.0
allowed-tools: ["Read","Write","Edit","Bash","Grep","Glob","Agent","Skill","AskUserQuestion","TaskCreate","TaskUpdate","TaskGet","TaskList"]
---

# coordinator:new-project

## When to Use

Creating a brand-new repo from any cwd: this skill creates the folder, scaffolds source, then
delegates onboarding to `coordinator:repo-setup`.

**Not for:** onboarding an existing repo (`coordinator:repo-setup`), fleet setup
(`coordinator:repo-setup --batch`), monorepo scaffolds, CI/deploy wiring.

## Inputs (promptable, with defaults)

| Input | Flag | Default | Notes |
|-------|------|---------|-------|
| Project name | `--name <n>` | **required** | dir name + `package.json` name; prompt if absent. |
| Parent dir | `--parent <dir>` | none — ask, offering `$HOME/projects` | flag → `COORDINATOR_PROJECTS_ROOT` env → `machine-local get coordinator.projects_root` → ask; passed to the helper explicitly. |
| Stack template | `--template next-app\|empty` | **none — infer or ask** | `next-app` (Next/React/TS/Tailwind/Vitest) only for a web app; `empty` (git + onboarding only) for any non-web ask, said aloud. Ambiguous → ask; never fall through to `next-app`. |
| Remote | `--remote none\|private\|public` | `none` | opt-in only. |
| Like | `--like <sibling-repo>` | none | a registered sibling (`machine-local get repos.<key>`) whose `CLAUDE.md` conventions and `pyproject.toml` shape seed step 4. |

## Flow

**1 — Resolve + validate inputs.** Gather name, parent, template, remote.

**2 — Create + scaffold.** The helper fails loud on an occupied non-empty target dir, `mkdir`s,
`git init`s (`main`), renders the template, seeds `coordinator.local.md` (`project_type` set) and
a minimal `README.md`, and for `next-app` runs the boot smoke (`pnpm install`, `typecheck`,
`test`). Shape per host: `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md` (POSIX: Shape A or
B, bare launcher `new-project-scaffold`; PowerShell: Shape W, guard line first, launcher plus `.exe`).
Flags on every host: `--name "<name>" --parent "<parent>" --template "<template>"`.

A template that does not boot is a **failed scaffold** — report it, don't work around it.
**3 — Onboard the new dir by path.** A `cd` never persists across Bash calls: from the creating
session, run `/coordinator:repo-setup --root "<new-dir>" --answers '{"project_name":...,"project_type":...,"project_subtypes":[...]}'`,
which calls the engine's `repo.setup` op (`EVERY-PROJECT-CARRIES-A-METRIC-REGISTER`, hooks, `state/` and the
rest are the op's; never re-implement them, `NEW-PROJECT-REPO-SETUP-BOUNDARY`). A bare
`claude -p "/coordinator:repo-setup ..."` rooted in the new dir is not a route: that fresh headless
session lacks the plugin and write permission, replies "isn't installed", and exits 0. **Ran-check:**
a success exit proves nothing; confirm `CLAUDE.md`, the tracker and `state/` exist in `<new-dir>`,
else report onboarding failed. Surface the verdict's `open` and `needs_attention` items in step 7.
This run is the only onboarding writer and finishes before step 7.

**4 — `--like`.** The op takes no `like` key. Read the sibling's `CLAUDE.md` and `pyproject.toml` before
step 3: carry its project type and subtypes into `--answers`, and after step 3 add its conventions to the
new `CLAUDE.md` as a "Conventions from `<sibling>`" section citing the sibling by name; a sibling-specific
fact is not copied.

**4.5 — Registry.** `new-project-scaffold` self-registers the new dir under `repos.<name>`
(kebab→snake-cased) via `machine-local set`; nothing further to run. If `machine-local` exits 127, run
`/coordinator:install` and retry.

**5 — Optional remote (opt-in; never default public).** Only on `--remote private|public`:

```bash
gh repo create "<name>" --private --source=. --remote=origin --push
```

Substitute `--public` for the public choice. Never default public; never create a remote unasked.

**6 — Scoped first commit** by the route in `${CLAUDE_PLUGIN_ROOT}/snippets/scoped-commit-route.md`
(`git-commit-agent` with the enumerated `paths` and `"<subject>"`; underneath,
`coordinator-invoke ceremony.commit_v2 '{"paths":[...],"message":"<subject>"}' --repo "<new-dir>"`
per the step-2 ladder) — never `git add -A`/`.`; no hook backstops the new repo.

**7 — Report the honest boundary.** The current session does NOT become the new project. Name what
was created, scaffolded, onboarded (with the ran-check result) and pushed, then tell the user to open
a Claude session rooted in `<new-dir>` for work.

## Negative-spec

- Close residue becomes ignore rules, not commits: the scaffolded ignore block (from `repo-setup`'s
  `gitignore.project.template`) carries the `gitignore_candidates` rule
  (`CLOSE-RESIDUE-IS-COMMITTED-OR-GITIGNORED` tripwire).
- Never silently overwrite an occupied dir — fail loud, stop.
- Never trust a headless `repo-setup` exit 0 — verify its artifacts exist.
