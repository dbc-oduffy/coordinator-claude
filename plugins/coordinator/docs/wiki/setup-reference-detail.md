---
title: Setup Reference Detail
created: 2026-05-30
author: claude-central-em
status: current
---

<!-- spec-backlink: coordinator/commands/setup.md -->

# Setup Reference Detail

Extended reference content extracted from `commands/setup.md` to keep that spec under the 500-line ceiling. All rules and values here are normative — the spec points here by reference.

---

## Phase 3 Step 3 — Registry Seed Prompt (full interactive script)

**Skip entirely** if either `~/.claude/machine-local/registry.toml` or `registry.local.toml` already exists (idempotency).

Under `--non-interactive`: skip; emit status row `machine_local_seed: skipped (non-interactive; copy .example files to seed manually)`.

Under interactive, ask once via `AskUserQuestion`:

> Would you like to seed the registry with the four most common `repos.*` keys (coordinator, project-rag, project-rag-ue-addon, claude-unreal-holodeck)? Key declarations go to `registry.toml` (shared, tracked); per-machine path values to `registry.local.toml` (gitignored). Single-machine operators may put everything in `registry.toml`. [Y/n]

**On Y:** Ask for each key's path value inline (blank = skip). Then write via script:

1. Write `registry.toml` with key declarations (empty-string values + `schema = 1`) using a plain atomic write — these are shared declarations, not machine-specific.
2. For each non-blank path value, write to `registry.local.toml` via `machine-local set`:

```bash
machine-local set repos.coordinator_claude     "${PATH_VALUE}"
machine-local set repos.project_rag            "${PATH_VALUE}"
machine-local set repos.project_rag_ue_addon   "${PATH_VALUE}"
machine-local set repos.claude_unreal_holodeck "${PATH_VALUE}"
```

**Do NOT write paths to `registry.local.toml` by hand-editing or heredoc.** `machine-local set` is atomic, idempotent, and sets the example for every future script that needs to populate the registry.

**On N:** leave both absent.

---

## Phase 7 — Status Table and Available Commands

Present this summary table after Step 0 records the setup-concluded receipt:

```
## Coordinator Setup

| Check                       | Status |
|-----------------------------|--------|
| Git repository              | ... |
| Agent Teams env var         | ... |
| Code stats (scc)            | ... (optional) |
| Deep research plugin        | ... (`ready` / `installed` / `not_found (install declined)` / `not_found (install failed: <reason>)` / `not_found (would offer install)` / `not_found (install offer suppressed — non-interactive)`) |
| NotebookLM (Pipeline D)     | ... (optional) |
| Global CLAUDE.md import     | ... |
| Operator identity           | ... (`ready` / `would write` / `failed (...)`) |
| Working repos               | ... (`ready (N from tier A\|B\|C)` / `defaulted to empty`) |
| Meta-repo CLAUDE.local.md   | ... |
| Machine-local directory     | ... (`ready` / `created` / `FATAL`) |
| Machine-local tracked files | ... (`ready (4/4)` / `partial (N/4: <missing>)` / `customized (<file> preserved)` / `FATAL`) |
| bin/ resolvers              | ... (`ready (7/7)` / `partial (N/7: <missing>)` / `FATAL`) |
| Windows PATH + Python shims | ... (n/a non-Windows / `ready` / `PATH-added, restart shells` / `WARNING: <stub\|alias\|no-python>`) |
| Registry seed               | ... (`seeded (Y)` / `declined (N)` / `skipped (non-interactive)` / `pre-existing`) |
| Coordinator plugin.mirrors  | ... (`ready` / `would write` / `skipped (--check-only)`) |
| Canonical structure         | ... (`ready` / `would scaffold` / `failed`) |
| Fan-out threshold           | ... (`written (N)` / `pre-existing` / `would write (N)`) |
| Setup-state receipt         | ... (`recorded` / `pre-existing` / `would record`) |
| Currency stamp              | ... (`written (vN)` / `current (vN)` / `unstamped(legacy)` / `failed — <reason>`) |
| `~/.claude` git tracking    | ... |
| coordinator.local.md        | ... |
| Percolation                 | ... (n/a if not a percolation source) |
| Non-interactive contract    | ... (`not_invoked` / `applied (skipped: N, defaulted: M, failed: 0)`) |
| Render template helper      | ... (`ready` / `missing`) |
| Bootstrap offer             | ... (`offered (N repos)` / `suppressed (--non-interactive\|--check-only)`) |
| Project scaffolding         | Run `/project-onboarding` — it owns lazy directory creation, lessons file, and tracker |

### Available commands

- `/workstream-start` — Orient session, load context, choose work
- `/workstream-complete` — Wrap up, capture lessons
- `/handoff` — Save state for next session
- `/review` (plans) / `/review-code` (diffs) — review skills with inline routing; shared phases in `docs/wiki/reviewer-pipeline.md`
- `/update-docs` — Refresh project documentation, maintain docs/README.md index
- `/distill` — Extract knowledge from session artifacts into wiki guides
- `/project-onboarding` — Full project scaffolding (CLAUDE.md, tracker, docs/README.md, wiki structure)
- `/bootstrap-repos` — Scaffold coordinator support into all discovered working repos (express all-at-once or per-repo selection)
- `/percolate` — Publish to a registered target; first-run setup walks `docs/wiki/percolate-setup.md` automatically
```
