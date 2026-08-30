---
name: cruft-sweep
description: "Scan for reclaimable scratch and orphans; apply only if confirmed."
allowed-tools: ["Read", "Bash", "Glob", "Grep", "Agent", "AskUserQuestion"]
argument-hint: "[--dry-run|--apply] [--class harness|scratch|orphans|empty-dirs|all]"
---

# Cruft Sweep — Layer 2 Skill

Consume the JSONL wire output of `bin/cruft-sweep` to surface `confirm-needed` findings and
parent-folder orphans for PM review. Present reclaim opportunities in offer-shape — never
violation framing. Apply only after explicit confirmation. Class definitions, disposition set,
wire contract, and guard-rail rationale: wiki.

**Destructive-action prohibition.** This skill dispatches read-only scouts only. The sole write
path is `bin/cruft-sweep --apply` after explicit `AskUserQuestion` confirmation.

**Hardcoded refusals (regardless of what the JSONL says):** never auto-prune a path containing a
`.git/` boundary; never expand the parent-folder scan beyond this machine's registry-resolved dev
roots; never treat git-untracked as sufficient for cruft; never auto-prune a session UUID cited as
`predecessor:` in an active handoff.

---

## Steps

### Step 0 — Surface last sweep staleness

Report the last sweep date and staleness to the PM as one line: _"Last sweep: YYYY-MM-DD (N days
ago)."_ <!-- engine-gap: field=cruft_sweep.last_sweep_staleness producer=unknown memo=2026-08-14-doe-claude-em-three-cut-obligations-from-the-corpus-grind.md -->

### Step 1 — Run Layer 1 dry-run and parse JSONL

Shape W (`${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`):

`& "$env:COORDINATOR_SETTINGS_HOME\bin\cruft-sweep.exe" --dry-run --json --class all`

Parse the JSONL stdout by `disposition`: `auto-prune` — summary count only; `confirm-needed` —
surface via `AskUserQuestion` (Step 3); `skip` — informational, don't surface unless asked;
`duplicate-of-scratch` — never a finding, never counted (wiki: dedup mechanism); `prune-failed` —
surface in Step 5, don't fold into the removed count. Total reclaimable MB = `auto-prune` +
`confirm-needed` only.

### Step 2 — Scout parent-altitude orphans (Class 3 registry-diff)

For `class == "orphans"` + `disposition == "skip"` records, dispatch a read-only `Explore` agent:

```
Agent(
  subagent_type: "Explore",
  description: "Cruft-sweep Class 3 parent-altitude registry-diff scan",
  prompt: """
    Do NOT modify files, commit, or push. Read-only.

    Enumerate top-level children of these resolved dev roots: {{RESOLVED_DEV_ROOTS}}. For each:
    1. Check whether its name appears among the `machine-local keys` sibling-repo registry.
    2. If NOT in the registry AND NOT matching the Layer 1 auto-prune conjoint gate
       (name match + fingerprint match), include it.

    Reply with a JSON list of {path, name, mtime_iso, evidence} per candidate.
  """
)
```

Resolve dev roots via `machine-local` (`registry.local.toml` first, `registry.toml` fallback);
test each with `[[ -d "$root" ]]`. No dev root on this machine → skip Class 3 and log one line:
`Class 3 parent-orphan scan skipped — no dev roots present on this machine.`

### Step 3 — Present confirm-needed items via offer-shape AskUserQuestion

> _"Reclaim N MB by pruning `<path>` (`<evidence>`, mtime `<mtime>`)? [y/N/inspect]"_

Batch related items from the same class into one question where practical. Never ask about
`auto-prune` items.

### Step 4 — Apply after confirmation

Shape W: `& "$env:COORDINATOR_SETTINGS_HOME\bin\cruft-sweep.exe" --apply --class <selected>`

Pass `--parent-root` overrides for confirmed Class 3 items outside the default roots. The script
appends to the central cruft-sweep log on apply — no separate log write from this skill.

### Step 5 — Report

Summarise all four classes swept (an omitted class reads as a silent under-report), items removed,
MB reclaimed, items deferred. Report `empty-dirs` by item count only — its reclaim bytes are 0 by
construction. Report `prune-failed` records explicitly, never folded into removed.

---

## Out-of-scope

Do NOT attempt: cleanup of `~/.claude/plugins/cache/` (harness owns); `git clean -fd` worktree
cleanup; auto-deletion of orphan markdown at parent altitude (always confirm-needed); re-walking
what Layer 1 already auto-prunes.

## Negative-spec

- Does NOT re-walk the filesystem — consumes `cruft-sweep --dry-run --json` only.
- Does NOT dispatch parallel scouts — sequential; each candidate is judgment-bearing.
- Does NOT write outside the central cruft-sweep log (script-owned via `--apply`).
- Does NOT auto-prune on the PM's behalf — every deletion needs explicit confirmation or Layer 1
  auto-prune eligibility.
