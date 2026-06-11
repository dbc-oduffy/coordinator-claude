# Phase 15 — Cross-Repo Registry Refresh

Invoked from `/update-docs` Phase 15 when `pwd` is `~/.claude`. EM-only — Sonnet sub-agent skips.

**Purpose:** Maintain `~/.claude/state/repo-registry.md` — the cross-repo inventory powering peer-repo prior-art lookup. Schema and conventions: [`docs/wiki/repo-registry.md`](../../docs/wiki/repo-registry.md).

## Steps

1. **Decode Claude Code invocation history.** Run `${CLAUDE_PLUGIN_ROOT}/bin/decode-claude-projects-dir.sh`. Output is tab-separated `shortname<TAB>candidate-path<TAB>encoded-dir`. The decoder is heuristic; treat output as candidates, not authoritative paths.

2. **Diff against active registry block.** Read the `<!-- BEGIN repo-registry --> ... <!-- END repo-registry -->` block in `~/.claude/state/repo-registry.md`. For each decoded candidate:
   - **Already in active block (by `shortname`)** → no-op.
   - **Not in active block** → append to `<!-- BEGIN repo-registry-candidates --> ... <!-- END repo-registry-candidates -->` block with `status: needs-pm-review`, `goals: []`, `stack_tags: []`, `relationships: []`, `last_verified: <today>`. Skip if already in candidates block.

3. **Staleness check on existing entries.** For each repo in the active block:
   - Reachability check (`ls "${path}"`). If reachable → update `last_verified: <today>`.
   - If unreachable → flip `status: unreachable` (do NOT delete; repo may be on a disconnected drive).
   - If currently `unreachable` and now reachable → flip back to `active` and log the transition.

4. **Surface counts to PM.** End-of-phase output (count-only):
   - `N candidates surfaced for tagging` (if any new candidates)
   - `M entries marked unreachable` (if any flipped to unreachable this run)
   - `K entries restored to active` (if any flipped back from unreachable)
   - `R entries refreshed last_verified`

5. **Commit.** Include `~/.claude/state/repo-registry.md` in the EM-side Phase 9 commit (explicit-path staging or `coordinator-safe-commit "registry refresh: N candidates, M unreachable"`).

## Failure modes

- Decoder returns zero candidates → log warning, proceed to staleness check.
- Registry file missing → create from template (Schema heading + empty active + empty candidates blocks); log `"Phase 15: registry file created from scratch"`.
- Sentinel block malformed → surface to PM, do NOT auto-repair.

## Out of scope (V1)

Auto-promoting candidates, inferring stack tags from manifest files, pruning dormant entries. PM curates and judges in `/workweek-complete`.
