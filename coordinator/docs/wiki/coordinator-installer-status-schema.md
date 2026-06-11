---
title: Coordinator installer — status report row schema
created: 2026-05-19
kind: wiki
spec_backlink_arch: "2026-05-19-coordinator-installer-redesign.md § D4 (lives in meta-repo docs/plans/; not bundled with the plugin)"
spec_backlink_impl: "2026-05-19-coordinator-installer-redesign-implementation.md § C4 (lives in meta-repo docs/plans/; not bundled with the plugin)"
---

# Coordinator installer — status report row schema

Purpose: document the stable producer-side contract for `/coordinator:install`'s status-report
table so that holodeck-callable wrappers (and any other consumer that parses the rendered
output) can pin against a known enumeration. Column names and value strings are
**append-only** across coordinator versions — see § Stability contract below.

---

## Column set

The status table has exactly two columns:

| Column header (literal) | Role |
|-------------------------|------|
| `Check` | Identifies the check by a short, stable identifier string (left column) |
| `Status` | Reports the result of that check using the value vocabulary below (right column) |

Consumers match rows with: `<identifier> .* <status-value>` (regex on the rendered Markdown
table line).

---

## Check identifiers

Every row that `/coordinator:install` currently emits, plus the three new rows introduced
by the installer redesign (marked **new**):

| Identifier | Display label in table | What it checks |
|---|---|---|
| `git_repo` | Git repository | Whether the current directory is inside a git repo (`git rev-parse --is-inside-work-tree`) |
| `agent_teams_env` | Agent Teams env var | Whether `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` is set |
| `scc` | Code stats (scc) | Whether the `scc` binary is on `$PATH` (optional capability) |
| `deep_research` | Deep research plugin | Whether the deep-research plugin is registered (optional capability) |
| `notebooklm` | NotebookLM (Pipeline D) | Whether the notebooklm MCP server is reachable (optional capability) |
| `global_claude_md_import` | Global CLAUDE.md import | Whether the project `CLAUDE.md` imports `~/.claude/CLAUDE.md` |
| `meta_repo_doctrine` | Meta-repo CLAUDE.local.md | Whether `~/.claude/CLAUDE.local.md` exists and is non-empty |
| `claude_git_tracking` | `~/.claude` git tracking | Whether `~/.claude` is a tracked git repo |
| `coordinator_local_md` | coordinator.local.md | Whether a `coordinator.local.md` exists in the project root |
| `percolation` | Percolation | Percolation target count and configuration state (`n/a` if not a percolation source) |
| `project_scaffolding` | Project scaffolding | Directive to run `/repo-setup` — always a fixed prose value, not a computed status |
| `operator_identity` | Operator identity | **new** — Whether `~/.claude/coordinator-identity.yaml` exists with a parseable `version: 1` + `operator_name` field |
| `non_interactive_contract` | Non-interactive contract | **new** — Under `--non-interactive`, each prompt site's annotation (`skip-with-note` / `default-with-warning` / `fail-loud`); surfaces which defaults were applied |
| `render_template_helper` | Render-template helper | **new** — Whether `render-template.sh` is present and executable in the coordinator plugin directory |
| `persona_customization` | Persona customization | Whether persona names were customized or kept at defaults under this run |
| `coordinator_whoami` | `coordinator_whoami` package | Whether the `coordinator_whoami` Python package is importable in the active env, and if not, what `/coordinator:install` Phase 3 Step 6 did about it |

**Total: 16 rows** (11 pre-redesign + 3 new + 1 persona-customization row + 1 coordinator-whoami row).

<!-- Review: code-reviewer — persona_customization row was emitted by setup.md C3 but missing from this table -->

---

## Status value vocabulary

The `Status` column uses only values from this enumeration. Any value not in this list is a
bug in the producer.

| Value | Semantics |
|---|---|
| `ready` | The check passed — the component is present, configured, and functional. |
| `missing` | The check failed because an expected file, binary, or configuration item does not exist. |
| `not_configured` | The component exists but is incomplete or has no usable configuration (e.g. env var present but empty, file exists but required fields absent). |
| `not_a_repo` | Specific to `git_repo`: the current directory is not inside any git repository. |
| `skipped (non-interactive default)` | Under `--non-interactive`, a prompt site with a `default-with-warning` annotation was reached; the documented default was applied without prompting. The value is the literal string `skipped (non-interactive default)`, including the parenthetical. |
| `failed` | The check ran but produced an error (e.g. a command exited non-zero for an unexpected reason, or a file was unparseable). |
| `not_applicable` | The check does not apply to this installation context (e.g. `percolation` on a repo that is not a percolation source). |
| `would write` | Under `--check-only`, indicates what would be created without the flag. Used for `operator_identity`, `meta_repo_doctrine`, and similar rows that write files. Not emitted in normal (mutating) mode. |
| `not_invoked` | For `non_interactive_contract`: the `--non-interactive` flag was not passed; the row is informational (no prompt-fallback behavior occurred). |
| `applied (skipped: N, defaulted: M, failed: 0)` | For `non_interactive_contract`: the `--non-interactive` flag was active; the parenthetical is a per-site outcome summary — `skipped` is the count of `skip-with-note` callsites, `defaulted` is the count of `default-with-warning` callsites, `failed` is the count of `fail-loud` callsites that fired. |

<!-- Review: code-reviewer — C3 setup.md emits would_write, not_invoked, and applied(...) compound token; these were missing from the vocabulary table -->

---

## Stability contract

The schema above is **append-only** across coordinator versions:

- **Adding a new identifier row is allowed** at any time without a version bump. Consumers that
  don't know the new identifier simply won't match it — acceptable degradation.
- **Renaming an existing identifier is a breaking change.** Old consumers will stop matching
  the renamed row. Requires a coordinator major version bump and a migration note.
- **Removing an existing identifier is a breaking change** by the same logic.
- **Adding a new Status value is allowed** without a version bump; consumers that pin against
  only the documented subset are unaffected.
- **Renaming or removing an existing Status value is a breaking change.** Any consumer pinning
  that value will silently misfire. Requires a version bump.

The coordinator plugin does not currently carry a formal semver contract, but the convention is:
breaking schema changes increment the first component of the plugin version in `package.json`
(or equivalent manifest). Non-breaking additions are patch-level.

---

## Consumer guidance

Holodeck wrappers (`scripts/holodeck_setup.sh`, `scripts/holodeck_setup.ps1`) and any other
caller that parses the status table should:

1. **Match by identifier + value:** use a regex of the form `\|\s*<identifier>\s*\|.*\|\s*<status-value>\s*\|`
   (or an equivalent grep on the rendered output line).
2. **Pin only against documented values.** Any value not in the vocabulary above is unstable
   and may change without notice. If you observe an undocumented value, file a bug against
   this wiki.
3. **Treat unknown identifiers as informational.** A row your parser doesn't recognise is a
   new check added after your consumer was written — log it, don't error.
4. **`skipped (non-interactive default)` is a compound token.** Match it as a literal string
   (including the parenthetical) rather than splitting on whitespace.
5. **`not_applicable` is not a failure.** Do not gate install success on a `ready` value for
   optional checks (`scc`, `deep_research`, `notebooklm`, `percolation`).
6. **`applied (skipped: N, defaulted: M, failed: 0)` is a compound token for `non_interactive_contract`.**
   Match it with a regex that tolerates varying numeric values, e.g. `applied \(skipped: \d+, defaulted: \d+, failed: \d+\)`.
   A `failed` count greater than 0 indicates at least one `fail-loud` callsite fired — treat this as an install error.
   Analogous to the `skipped (non-interactive default)` guidance in item 4: match the whole parenthetical as a unit.

---

## Provenance

- Architecture decision: `docs/plans/2026-05-19-coordinator-installer-redesign.md` § D4 (per-callsite annotation contract; `--non-interactive` controls only `AskUserQuestion` fallback; `--check-only` is a strict superset)
- Implementation chunk: `docs/plans/2026-05-19-coordinator-installer-redesign-implementation.md` § C4
- Producer code: `commands/setup.md` § 4. Status Report
