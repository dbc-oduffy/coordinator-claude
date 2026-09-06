---
title: Setup Reference Detail
created: 2026-05-30
author: claude-central-em
status: active
---

<!-- spec-backlink: coordinator/commands/install.md -->

# Setup Reference Detail

Extended reference content extracted from `commands/install.md` to keep that spec under the 500-line ceiling. All rules and values here are normative — the spec points here by reference.

---

## Phase 3 Step 3 — Registry Seed Prompt (full interactive script)

**Skip entirely** if either `~/.claude/machine-local/registry.toml` or `registry.local.toml` already exists (idempotency).

Under `--non-interactive`: skip; emit status row `machine_local_seed: skipped (non-interactive; copy .example files to seed manually)`.

Under interactive, ask once via `AskUserQuestion`:

> Would you like to seed the registry with three `repos.*` working-repo keys (project-rag, project-rag-ue-addon, example-game-workbench-repo) and the coordinator-claude publish-mirror path? Key declarations go to `registry.toml` (shared, tracked); per-machine path values to `registry.local.toml` (gitignored). Single-machine operators may put everything in `registry.toml`. [Y/n]

**On Y:** Ask for each key's path value inline (blank = skip). Then write via script:

1. Write `registry.toml` with key declarations (empty-string values + `schema = 1`) using a plain atomic write — these are shared declarations, not machine-specific.
2. For each non-blank path value, write to `registry.local.toml` via `machine-local set`:

```bash
machine-local set publish.mirrors.coordinator_claude.path "${PATH_VALUE}"
machine-local set repos.project_rag            "${PATH_VALUE}"
machine-local set repos.project_rag_ue_addon   "${PATH_VALUE}"
machine-local set repos.example_game_workbench_repo "${PATH_VALUE}"
```

**Do NOT write paths to `registry.local.toml` by hand-editing or heredoc.** `machine-local set` is atomic, idempotent, and sets the example for every future script that needs to populate the registry.

3. After the `repos.*` seeds, seed the machine slug (absent-only — never overwrites an existing value):

```bash
# Seed coordinator.machine_slug from hostname if not already set.
# cs_compute_machine_live is natively imported from coordinator_core.machine_resolver
# (env→hostname, no registry read) — de-bash campaign, unit "daily-branch"
# (coordinator-daily-branch.sh is retired).
# This is the deliberate canonical seed — hostname at a known-good install moment.
if ! machine-local has coordinator.machine_slug 2>/dev/null; then
  _cc_machine_py="python3"; command -v python3 >/dev/null 2>&1 || _cc_machine_py="python"
  _slug="$("$_cc_machine_py" -c '
import sys
sys.path.insert(0, "'"${CLAUDE_PLUGIN_ROOT}"'/hooks/scripts")
from _engine_root import resolve_claude_klabauter_root
mr = resolve_claude_klabauter_root()
if mr not in sys.path:
    sys.path.insert(0, mr)
from coordinator_core.machine_resolver import compute_machine_live
print(compute_machine_live())
')"
  machine-local set coordinator.machine_slug "${_slug}"
fi
```

Idempotent: re-running install does not overwrite an existing `coordinator.machine_slug`. The value is seeded from `cs_compute_machine_live` (hostname-derived, never from a transient `$COORDINATOR_MACHINE` env override) so the canonical identity persists rather than a session-scoped override. The key is classified `idempotent-regeneratable` in `registry.toml` — `/workday-start` Step 0 self-heals any install where this step was skipped.

4. Also after the `repos.*` seeds, seed the contributor slug (absent-only — never overwrites an existing value):

```bash
# Seed coordinator.contributor_slug from git user.email if not already set.
# cs_compute_contributor_live is natively imported from coordinator_core.machine_resolver
# (env→user.email, no registry read) — de-bash campaign, unit "daily-branch"
# (coordinator-daily-branch.sh is retired).
# This is the deliberate canonical seed — sanitized user.email at a known-good install moment.
if ! machine-local has coordinator.contributor_slug 2>/dev/null; then
  _cc_machine_py="python3"; command -v python3 >/dev/null 2>&1 || _cc_machine_py="python"
  _slug="$("$_cc_machine_py" -c '
import sys
sys.path.insert(0, "'"${CLAUDE_PLUGIN_ROOT}"'/hooks/scripts")
from _engine_root import resolve_claude_klabauter_root
mr = resolve_claude_klabauter_root()
if mr not in sys.path:
    sys.path.insert(0, mr)
from coordinator_core.machine_resolver import compute_contributor_live
print(compute_contributor_live())
')"
  machine-local set coordinator.contributor_slug "${_slug}"
fi
```

Idempotent: re-running install does not overwrite an existing `coordinator.contributor_slug`. The value is seeded from `cs_compute_contributor_live` (sanitized git `user.email` local-part, never from a transient `$COORDINATOR_CONTRIBUTOR` env override) so the canonical identity persists rather than a session-scoped override. The key is classified `idempotent-regeneratable` in `registry.toml` — `/workday-start` Step 0 self-heals any install where this step was skipped.

**On N:** leave both `coordinator.machine_slug` and `coordinator.contributor_slug` absent.

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
| PowerShell 7+ (pwsh)        | ... (`ready (<ver> at <path>)` / `installed (<ver>)` / `declined` / `not_found (would offer)` / `not_found (install: <doc-url>)` / `not_found (install offer suppressed — non-interactive)`) |
| Windows Terminal            | ... (n/a non-Windows / `ready` / `installed` / `declined` / `not_found (would offer)` / `not_found (install via Microsoft Store or https://aka.ms/terminal)`) |
| Deep research plugin        | ... (`ready` / `installed` / `not_found (install declined)` / `not_found (install failed: <reason>)` / `not_found (would offer install)` / `not_found (install offer suppressed — non-interactive)`) |
| NotebookLM (Pipeline D)     | ... (optional) |
| Global CLAUDE.md import     | ... |
| Operator identity           | ... (`ready` / `would write` / `failed (...)`) |
| Working repos               | ... (`ready (N from tier A\|B\|C)` / `defaulted to empty`) |
| Meta-repo the (now-removed) meta-repo local-doctrine file   | ... |
| Machine-local directory     | ... (`ready` / `created` / `FATAL`) |
| Machine-local tracked files | ... (`ready (4/4)` / `partial (N/4: <missing>)` / `customized (<file> preserved)` / `FATAL`) |
| bin/ resolvers              | ... (`ready (7/7)` / `partial (N/7: <missing>)` / `FATAL`) |
| Windows PATH + Python shims | ... (n/a non-Windows / `ready` / `PATH-added, restart shells` / `WARNING: <stub\|alias\|no-python>`) |
| Registry seed (machine_slug + contributor_slug) | ... (`seeded (Y)` / `declined (N)` / `skipped (non-interactive)` / `pre-existing`) |
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
| Project scaffolding         | Run `/repo-setup` — it owns lazy directory creation, lessons file, and tracker |

### Available commands

- `/workstream-start` — Orient session, load context, choose work
- `/workstream-complete` — Wrap up, capture lessons
- `/handoff` — Save state for next session
- `/review` (plans) / `/review-code` (diffs) — review skills with inline routing; shared phases in `docs/wiki/reviewer-pipeline.md`
- `/update-docs` — Refresh project documentation, maintain docs/README.md index
- `/distill` — Extract knowledge from session artifacts into wiki guides
- `/repo-setup` — Full project scaffolding (CLAUDE.md, tracker, docs/README.md, wiki structure)
- `/repo-setup --batch` — Scaffold coordinator support into all discovered working repos (fleet-level setup; default `/repo-setup` is single-repo deep mode)
- `/percolate` — Publish to a registered target; first-run setup walks `docs/wiki/percolate-setup.md` automatically
```
