#### 3a. CLAUDE.md (if missing)

Use `templates/CLAUDE.md.template` via the `render-template` forwarder. Construct three substitution values before calling it:

1. **`GLOBAL_EXTENDS_LINE`** — `Extends global \`~/.claude/CLAUDE.md\`.` if that file exists; else `""`.
2. **`PROJECT_TYPE_BLOCK`** — concatenated per-type convention section bodies, one per selected type, blank line between multiple. Each type's body is the literal content of this skill's own `templates/project-type-block.<type>.template` (`game-dev`, `web-dev`, `data-science`). `general` type, and any type without a matching template file: empty string.
3. **Render helper call:**

   ```bash
   "${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/render-template" templates/CLAUDE.md.template -o CLAUDE.md PROJECT_NAME="<derived-name>" PROJECT_TYPE="<type>" SUBTYPES="<comma-separated-list-or-empty>" GLOBAL_EXTENDS_LINE="<line-or-empty>" PROJECT_TYPE_BLOCK="<concatenated-blocks-or-empty>"
   ```

   The forwarder self-resolves its own engine-plane target — no separate root resolution is
   needed at this call site. It substitutes every `{{KEY}}` placeholder and exits non-zero if any
   remain (template/key drift guard). Leave `<!-- Fill in -->` comments as-is; they are prompts
   for the PM.
4. **Runtime conventions population:** populate the rendered `## Runtime conventions` section
   bullets from the Phase 1 marker-scan output — one bullet per detected stack line. If the scan
   reported no known stack markers, replace the placeholder bullets with
   `- <!-- no runtime markers detected; PM to fill -->`. Do not edit other `<!-- Fill in -->`
   placeholders.

Use absolute `$HOME`-anchored paths. Leave `<!-- Fill in -->` comments as-is.

After `render-template.py` returns successfully, set `_PHASE_3A_RENDERED_CLAUDE_MD=true` so Phase 4 item 1 can fire its conditional. (When CLAUDE.md exists before Phase 3a and is left untouched, the flag stays unset and Phase 4 item 1 is suppressed — the intended behavior for bespoke CLAUDE.md.)

#### 3b. — RETIRED

No tracker is scaffolded. Workstreams live in `state/workstreams/` and are queried, never
rendered to a hand-maintained index.

#### 3c. state/lessons/ — SKIP (lazy)

Do NOT create this directory during onboarding — no meaningful day-1 content. Its first per-entry YAML file is created by `coordinator:workstream-complete` on first lesson capture.

#### 3d. docs/README.md (if missing)

Render `templates/README.md.template` via `render-template.py`, substituting `[PROJECT_NAME]` and `[DATE]`.

#### 3d.5. docs/exec-summary.md (if missing)

Generate the per-repo executive summary brief using the coordinator generator — resolve and run it via `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/repo-setup-args-and-register" resolve-exec-summary-generator --run`. It checks the coordinator-plugin-root copy first, falls back to the engine-plane sibling copy (via `REPO_CLAUDE_KLABAUTER`/`CLAUDE_KLABAUTER_ROOT`/the `.claude-klabauter-root` pointer), and degrades gracefully with a stderr warning — `generate-exec-summary.py unresolvable ... exec-summary generation skipped` (exit 1) — rather than aborting the skill when neither copy resolves.

The generator populates the two MANAGED sections from current disk artifacts (identity from README
H1 + lead paragraph; progress from `state/week-changelog/` latest Highlights + `orientation_cache`
Counters + `git log` since last weekly reset, with a git-log fallback when week-changelog is
absent). The two HAND sections (`<!-- BEGIN HAND: special -->`, `<!-- BEGIN HAND: goals -->`) ship
as documented placeholders for PM hand-authoring on first run.

**Idempotency on existing file:** when `docs/exec-summary.md` already exists the generator
re-emits the MANAGED sections from current disk data and copies both HAND sections forward
verbatim. If a HAND fence is malformed or absent the generator exits non-zero, names the file
+ the broken fence, and writes nothing — per detect-then-fail-loud doctrine.

**Backfill (--batch):** `repo-setup --batch` runs Phase 3d.5 across the fleet in no-clobber
mode — the generator's no-clobber create path fires only when `docs/exec-summary.md` is genuinely
absent. Repos that already have the file are skipped cleanly.

**After generation, prompt the PM to hand-author the two HAND sections:**

1. **What makes this project special** (`<!-- BEGIN HAND: special -->`) — the differentiator or
   architectural bet. Seed from the machine-local sibling-repo registry entry for this repo
   (`machine-local get repos.<key>`) if one exists.
2. **Near-term goals** (`<!-- BEGIN HAND: goals -->`) — the 2–4 highest-priority near-term items.
   The generator may pre-fill a commented seed from `week-changelog/HEADER.md` Priorities when
   non-blank.

Record in Phase 4 REPORT: `### Created` if generated this run, `### Already Existed` if the file
was already present and left untouched. Any fail-loud generator exit (malformed HAND fence) surfaces
under `### Needs Attention` with the generator's error text verbatim.

#### 3g. DIRECTORY.md

Do NOT create this file directly — requires source file analysis handled by `/update-docs` Phase 2. Do NOT add a prescription to the Phase 4 REPORT telling the PM to run `/update-docs` — the precondition probe self-gates and will run when DIRECTORY.md analysis is warranted. → `docs/wiki/produce-not-prescribe.md`.
