---
title: Repo Setup — CLAUDE.md Render Procedure
status: active
kind: procedure-wiki
created: 2026-05-30
---

# Repo Setup — CLAUDE.md Render Procedure

**Purpose:** Full procedure for constructing substitution values and calling `render-template.py` when generating a project's `CLAUDE.md` during `/repo-setup` Phase 3a. Referenced from `skills/repo-setup/SKILL.md § 3a`.

---

## Substitution Construction

`templates/CLAUDE.md.template` contains ONLY literal `{{KEY}}` substitutions — no conditionals. Construct all values before calling the helper.

### 1. `GLOBAL_EXTENDS_LINE`

- If `~/.claude/CLAUDE.md` exists: set to `Extends global \`~/.claude/CLAUDE.md\`.`
- If no global CLAUDE.md exists: set to empty string `""`

### 2. `PROJECT_TYPE_BLOCK`

Concatenate block bodies for each selected type (in selection order); blank line between multiple blocks.

**`game-dev` block:**
```
## Unreal Engine Conventions

- **Engine version:** UE5.x (specify)
- **Build command:** <!-- e.g., UnrealBuildTool invocation -->
- **Cook command:** <!-- platform-specific cook -->
- **Blueprint vs C++:** <!-- project policy on when to use each -->
- **Naming conventions:** <!-- UE naming standards: A_ for assets, BP_ for blueprints, etc. -->
- **Key modules:** <!-- list primary C++ modules -->
```

**`web-dev` block:**
```
## Web Development

- **Framework:** <!-- e.g., Next.js, React, Vue, Svelte -->
- **Dev server:** <!-- e.g., npm run dev, port -->
- **Component conventions:** <!-- file structure, naming, styling approach -->
- **State management:** <!-- e.g., Zustand, Redux, signals -->
- **CSS approach:** <!-- e.g., Tailwind, CSS Modules, styled-components -->
- **Key routes/pages:** <!-- list primary routes -->
```

**`data-science` block:**
```
## Data Science Conventions

- **Notebook conventions:** <!-- naming, cell organization, output clearing policy -->
- **Data pipelines:** <!-- tools, orchestration, storage locations -->
- **Model versioning:** <!-- MLflow, DVC, manual, etc. -->
- **Environment management:** <!-- conda, venv, poetry -->
- **Key datasets:** <!-- list primary data sources -->
```

**`general` type:** no block body — `PROJECT_TYPE_BLOCK` is empty string `""`.

**Multi-type projects** (e.g., `game-dev` + `data-science`): concatenate both block bodies with a blank line between them.

## 3. Render Helper Call

```bash
# render-template.py migrated to claude-klabauter (coordinator bin/lib -> claude-klabauter, commit b644d5a9).
# POSIX-host form (this is the cc-root-source-guard.md SSOT preamble, not a coordinator-CLI
# invocation); a PowerShell host resolves the trusted root by its own PowerShell-native path.
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/machine-local/.doe-root" 2>/dev/null || cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/machine-local/.doe-root" 2>/dev/null || true)"
if [ -z "$_cc_doe" ]; then
  _cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
fi
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }

_cc_claude_klabauter="${REPO_CLAUDE_KLABAUTER:-${COORDINATOR_ENGINE_ROOT:-}}"
if [ -z "$_cc_claude_klabauter" ]; then
  _cc_claude_klabauter="$(python3 "$_cc_root/hooks/scripts/_engine_root.py" 2>/dev/null)"
fi
if [ -z "$_cc_claude_klabauter" ] || [ ! -d "$_cc_claude_klabauter" ]; then
  echo "ERROR: claude-klabauter root unresolved (checked REPO_CLAUDE_KLABAUTER, CLAUDE_KLABAUTER_ROOT, and the coordinator settings-home registry/pointer via _engine_root.py) — set REPO_CLAUDE_KLABAUTER, or run: machine-local set repos.claude_klabauter <path>" >&2
  exit 1
fi

python "$_cc_claude_klabauter/coordinator/bin/render-template.py" \
  "$_cc_root/skills/repo-setup/templates/CLAUDE.md.template" \
  -o CLAUDE.md \
  PROJECT_NAME="<derived-name>" \
  PROJECT_TYPE="<type>" \
  SUBTYPES="<comma-separated-list-or-empty>" \
  GLOBAL_EXTENDS_LINE="<line-or-empty>" \
  PROJECT_TYPE_BLOCK="<concatenated-blocks-or-empty>"
```

The helper substitutes all `{{KEY}}` placeholders, exits non-zero if any remain (template/key drift guard). The render helper and template resolve from the coordinator plugin root (`$_cc_root`, settings-resolved via `CLAUDE_PLUGIN_ROOT`/`.doe-root`, trust-guarded above) and the claude-klabauter root (`$_cc_claude_klabauter`, settings-resolved via `REPO_CLAUDE_KLABAUTER`/`CLAUDE_KLABAUTER_ROOT`/`_engine_root.py`) — relative paths are wrong because they resolve against the project root, not the plugin directory, but the fix is these resolved variables, never a hardcoded `$HOME`-anchored literal. Leave `<!-- Fill in -->` comments as-is; they are prompts for the PM.

## 4. Runtime Conventions Section

Populate the `## Runtime conventions` section bullets from the Phase 1 marker-scan output — one bullet per detected stack line. If the script reported "no known stack markers", replace the placeholder bullets with `- <!-- no runtime markers detected; PM to fill -->`. Do not edit other `<!-- Fill in -->` placeholders.
