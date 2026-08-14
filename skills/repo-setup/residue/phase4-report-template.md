**Declared exemption from the ≤200-word EM→PM budget (global `CLAUDE.md § Communication Style`).** This
phase's walkthrough prose below (the `~/.claude` surface explanation, `claude-doe` launch
instructions, "Fill in CLAUDE.md", the cross-platform CI note, and § Verify the coordinator
binding) invokes that budget's own escape hatch — *"the content is a document."* It was reviewed
and deliberately exempted during the 2026-07-31 report-by-exception sweep: recurrence is the
discriminator, and this is a first-run onboarding walkthrough read once per repo by an operator
who has no other source for it, not a recurring status report printed at every ceremony close
(contrast `coordinator/skills/workstream-complete/SKILL.md § Final Summary`, which the same sweep
converted to report-by-exception because *that* block prints on every close). **Do not shorten
the walkthrough prose to satisfy the word budget** — a future editor sweeping this repo for the
fixed-block anti-pattern should leave Phase 4's walkthrough alone; cutting it would strand a
first-time user with no other source for this content. The word-budget Stop-hook advisory that
measures EM→PM output length may still fire here — expected, not a defect to fix by shortening,
since that hook is non-blocking and advisory by construction.

If Phase 1.5 dispatched peer-repo scouts, ensure the tracker's workstream blocks include `file:line` citations from the scout reports.

**`coordinator_whoami` status row.** Emit a one-line status row based on `whoami_status` from Phase 1 (vocabulary: `coordinator_whoami: ready | installed | would-install | failed`). Route by value: `ready` → `### Already Existed`; `installed` → `### Created`; `would-install` or `failed` → `### Needs Attention` (include `pip_stderr` for `failed`).

**Report-by-exception on `### Already Existed`.** `### Created` and `### Needs Attention` always
print — the first is the receipt for what this run actually did, the second is the actionable
list. `### Already Existed (untouched)` is a list of things that did nothing; print it only when
non-empty, following the `| Line | Include only when |` shape from
`coordinator/skills/workstream-complete/SKILL.md § Final Summary`:

| Line | Include only when |
|---|---|
| `### Already Existed (untouched)` | at least one file/dir was already present and left untouched this run |

`### Recent Roadmap (last 90d, top-10 by size)` stays **count-always** — do not fold it into the
table above. Its zero-row `(none)` render is documented load-bearing behavior
(§ Phase 1.5 above, "count-always, so `(none)` is expected and rendered explicitly on new repos,
never omitted") — an explicit "found nothing yet" signal for a fresh repo, not the same shape as
an omitted list of no-ops.

Present what was done:

```
## Onboarding Complete — [Project Name]

### Created
- [list each file/directory created]

### Already Existed (untouched)
- [list each file that was skipped — omit this whole heading if nothing was already present]

### Needs Attention
- [any warnings — .gitignore issues, incomplete CLAUDE.md sections to fill in]

### Recent Roadmap (last 90d, top-10 by size)
_(Results from Phase 1.5 roadmap orientation query — one bullet per row. Render "(none)" when the query returns zero rows. Heading always present — count-always per orientation-surfacing-doctrine.)_

### What's next

Setup left this repo with `state/orientation_cache.md`, `docs/README.md`, and `CLAUDE.md` — minimum-viable versions of all coordinator artifacts. The standard coordinator skills (`/update-docs`, `/workstream-start`, `/workday-start`, `/workstream-complete`) will keep these in sync as the project accumulates work — invoke them when there's something to maintain. Both `/update-docs` and `/workstream-start` self-gate on fresh substrate and will emit a one-liner rather than running an empty pipeline (→ `docs/wiki/produce-not-prescribe.md` for the underlying principle).

Two things worth flagging before you dive in:

0. **Your `~/.claude` is the surface you evolve** — it is a git-tracked repo holding your config, lessons, and working-data. Customize it (CLAUDE.md, lessons, wiki), commit, and push. The coordinator **plugin source** lives in the doctrine-plane clone (`repos.doe_claude`), resolved live via `--plugin-dir`. Launch with `claude-doe` (not bare `claude`) as the persistent launch surface — the wrapper regenerates the settings.json hook block and execs `claude --plugin-dir <doe_clone>/coordinator` on every invocation, so skills, agents, and hooks always resolve from the doctrine-plane clone. Direct-editing the doctrine-plane clone's coordinator source IS the intended editable-install workflow; those edits take effect at next Claude Code boot for both skills/agents and hooks — restart `claude-doe` to pick them up. If a mid-session plugin-reload command (`/reload-plugins`) is available in your Claude Code build it may pick up skills/agents edits immediately without a full restart, otherwise a restart is required. SessionStart hooks are boot-only regardless — they do not fire on mid-session settings.json edits.

1. **Fill in CLAUDE.md** *(only if Phase 3a rendered the template this session — skip if CLAUDE.md was authored bespoke)* — the `<!-- Fill in -->` sections need project-specific details. Skip silently if `_PHASE_3A_RENDERED_CLAUDE_MD=true` was not set.

2. **Cross-platform CI reference available** — if this repo targets multiple OSes, a 3-OS matrix snippet and honest-measurement marker conventions are available at `templates/ci/cross-platform-matrix.snippet.yml`; the principle lives at `docs/wiki/cross-platform-ci-discipline.md`. Declare `cross_platform: true` in `coordinator.local.md` and re-run `/repo-setup` to trigger the language-aware install offer.

To verify the install: `python3 -m coordinator_whoami.project_rag`.

To start your first workstream now, just describe what you want to do — the EM has full context from the setup conversation.

### Verify the coordinator binding

Run the envelope-branch check below to verify the coordinator sees this project correctly: `python3 -m coordinator_whoami.project_rag` (POSIX/macOS) or `py -3 -m coordinator_whoami.project_rag` (Windows Git Bash/PowerShell). Output is compact JSON by default — no `--json` flag needed; pipe through `python -m json.tool` for pretty-print.

   Parse `binding.kind` and `binding.target` from the JSON envelope (`cross-plugin-whoami-contract.md §Operator wiring`):

   - **`binding.kind == "bound"` AND `binding.target` matches cwd:** emit `Coordinator binding healthy: project-rag is bound to <binding.target>.`
   - **`binding.kind == "bound"` AND `binding.target` does NOT match cwd:** emit a mismatch block:
     ```
     Binding mismatch:
       envelope binding.target : <binding.target>
       expected (cwd)          : <cwd>
     Run /project-rag:setup to re-register this project root.
     ```
   - **`binding.kind == "unbound"`:** emit:
     `project-rag is not bound to this project. Run /project-rag:setup to register this project root.`
   - **Import fails (`ModuleNotFoundError`) OR the command exits non-zero:** emit:
     `coordinator_whoami is not installed. Run /coordinator:install to install the introspection package.`

**If `machine-local get repos.*` fails** — the machine-local registry is not yet bootstrapped for this project. Work the three failure shapes in order:

   - **No registry directory.** The substrate was never bootstrapped — run `/coordinator:install` Phase 3.
   - **Registry present but no `repos.*` keys.** Expected on a fresh install; nobody has seeded the machine-specific sibling paths yet. Declare one per sibling repo with `machine-local set repos.<name> <path>`. Machine-specific values belong in the `.local.toml` layer, never in a tracked file.
   - **The `machine-local` command itself is not found.** Setup is incomplete rather than misconfigured — re-run `/coordinator:install` Phase 3. On macOS and Linux, `~/.claude/bin` is deliberately NOT on PATH; bare-name reach comes from the `coordinator/bin` forwarder that Phase 3 installs, so a missing bare name means a missing forwarder, not a PATH edit you should make by hand.

### Documentation System
The documentation index is live at `docs/README.md`. Subdirectories are created lazily as artifacts accumulate:
- **`docs/wiki/`** — created by `/distill` when first guide is extracted
- **`docs/plans/`** — created when first plan is written in plan mode
- **`docs/research/`** — created by `coordinator:research` on first run
- `/update-docs` maintains docs/README.md; `/distill` creates wiki guides from session artifacts
```
