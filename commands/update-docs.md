---
name: update-docs
description: "Sync all documentation artifacts to the current codebase state."
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent"]
argument-hint: "[--no-distill]"
---

# Update Documentation — Repo-Wide Maintenance

Repo-wide doc maintenance, any prior agent's changes. `--no-distill` skips Phase 13.

**Split:** Phases 1–11d dispatch UNNAMED to a Sonnet doc-maintenance agent (`model: "sonnet"`;
named breaks report delivery) and stop at 11d — subagents can't dispatch subagents. EM runs
Phase 0, 9's commit, 12, 11f/11g/11h/11h2/11i/11j, 13–15, and all escalations. Sonnet agent
out-of-scope: `gh pr create/merge`, `git push origin main`, any commit to `main` — surface a
merge urge to the EM instead.

Unless a row below says otherwise: **non-zero exit → surface path+error to PM, don't auto-fix,
don't abort. Zero/nothing found → no Phase 14 line.** All CLIs run via
`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/<name>"`. Rationale,
worked examples, and incident write-ups for any row: wiki.

### Pre-flight

`update-docs-probes fresh-scaffold-probe` (3-axis AND, false-negative-NEVER). Exit 0: relay the
printed no-op message verbatim, stop. Exit 1: continue.

### Phases (Sonnet-dispatched unless marked EM)

| # | Action |
|---|---|
| 0 | Branch guard off `main`. `coordinator-safe-commit --blanket "pre-docs quick-save"`. Push is Phase 9. |
| 1–2b | Follow, in order: `${CLAUDE_PLUGIN_ROOT}/pipelines/update-docs/detect-current-state.md`, `source-index-maintenance.md`, `docs-readme-maintenance.md`. |
| 3 | Update plan-doc status markers, completion dates, deviations. |
| 4 | Memory is a pointer index (PM decisions, behavioral feedback, cross-repo/project pointers only) — size-guard-capped, drained at every closure ceremony. Lessons → `/learn-lessons`. |
| 5 | Retired, no-op — placeholder keeps numbering stable. |
| 6 | `/learn-lessons --mode=local`. |
| 7 | CLAUDE.md — rare, only on a real architecture/rule/build-system change. |
| 8 | Follow `pipelines/update-docs/handoff-archival.md`. |
| 8b | Follow `pipelines/update-docs/artifact-pruning.md`. `git rm` is EM-scope — inventory only, EM stages it into Phase 9. |
| 9 (EM) | `coordinator-safe-commit --blanket "docs maintenance"`; verify `git log origin/$(git branch --show-current)..HEAD`, push if needed; warn PM on push failure. Sonnet agent MUST NOT run this. |
| 9b | `update-docs-probes repomap-gate` — resolves RAG tiering itself, prints the Phase 14 note. |
| 10 | If `state/orientation_cache.md` exists: `regenerate-orientation-cache --invoker update-docs`. Never hand-author/patch it. No cache: skip. |
| 10b | Only if RAG present and repomap ran as fallback: append `state/repomap-audit.log`. Two consecutive "no" entries → suggest retirement to PM, no auto-action. |
| 11 | Follow `pipelines/update-docs/atlas-integrity-check.md`. Also surface any RAG-staleness banner and >90-day `last_mapped` drift (informational). |
| 11b | Retired, no-op — placeholder keeps numbering stable. |
| 11g | `sync-plugin-wiki`. Exit 5: dev-side mirror at `~/.claude/docs/wiki/` — resolve before proceeding. |
| 11c | `refresh-queries`. Changed files fold into the Phase 9 commit. |
| 11d | `lint-frontmatter --json`. `ok:false`: top 3 schemas + up to 5 files in Phase 14. Escalate at ≥2 consecutive non-zero runs. Native seam: `schema.validate` op. |
| 12 (EM) | Resolve scope (`plugins/` if present at repo root, else invoking repo's own doc surface). Pre-count `[text](url)` links in `{skills,agents,commands}/*.md`; below a low per-file threshold, skip and report. Else dispatch `doc-link-checker` (scope + file filter only — it follows its own agent file's Output Contract/DONE-After-Write Protocol) via its auto-provisioned sidecar. Never halts. |
| 11f (EM) | `verify-parallel-review-lens-orthogonality`. Non-zero: lens-domain collision — rename/drop the reviewer, don't auto-fix. |
| 11h (EM) | `verify-skill-anchor-links`. Exit 1: dead anchors, don't auto-fix. Exit 2: **could not check** (broken/missing manifest) — report as missing coverage, never a finding; absent manifest is exit 0/1, not 2. |
| 11h2 (EM) | `verify-coverage --sweep-root "$(pwd)"`. **Non-zero HALTS `/update-docs`** — retarget, add a rationale to `REF_ALLOWLIST` in the engine repo's `verify_coverage.py`, or create the artifact. |
| 11i (EM) | `update-docs-probes queue-prune-sweep`. Pruned: fold into the commit, report the count. |
| 11j (EM) | `reap-stale-subagent-sidecars` — reaps on session liveness AND an age floor AND a status carve-out, never `status:` alone. Reaped: `git rm` into the commit, report the count. |
| 11k (EM) | Follow `pipelines/update-docs/claudemeta-manifest-cadence.md`. DoE-specific, no-op elsewhere. |
| 13 (EM) | Skip on `--no-distill`. `update-docs-probes distill-threshold` (fires ≥50 artifacts, OR >14 days stale, OR no log + ≥20). Exit 1: announce to PM, chain `/distill` via Skill tool. |
| 14 (EM) | Report, below. |
| 15 (EM, `~/.claude` only) | Elsewhere: "Phase 15: skipped — not running from ~/.claude." Else follow `pipelines/update-docs/cross-repo-registry-refresh.md`. |

**tasks/ vs state/ (Phases 8b, 13):** `state/` never archived/pruned/deleted except the named
ops above (11i, 11j, 10). `tasks/` is the aggressive target — dated reports/topic dirs, loose
scratch, `status: superseded`/`archived` frontmatter; UUID flight-recorder dirs are
Tasks-API-managed, untouched. `state/scratch/<managed-namespace>/` is exempt. Thresholds: wiki.

### Phase 14: Report

Report by exception — the ≤200-word budget buys a reader's attention, not a checklist.

```
## Documentation Update Summary

**Synced:** [N] doc(s) updated (indexes, plans, memory, lessons, CLAUDE.md, handoffs, artifact pruning, completion archive, repomap, preamble/callout sync) — see commit for detail
**Pushed:** yes (branch) / no (reason)
```

Append a line only if its condition holds:

| Line | Include only when |
|---|---|
| `**Plugin Doc-Link Health:**` | broken link(s) or a skipped-cap notice — omit when clean |
| `**Architecture Atlas:**` | drift, staleness banner, or quarterly drift note fired — omit when clean |
| `**Frontmatter Schema Drift:**` | N ≥ 1 violations, or the sweep errored — omit at 0 |
| `**Distillation:**` | threshold fired and `/distill` was chained — omit when "not needed" |
| `**Cross-Repo Registry:**` | unreachable candidate(s), or skipped (cwd-gated out) — omit when clean |
| `**claudemeta Manifest:**` | regenerated on drift — omit when `--check` was clean or the generator is absent |

Every other phase's count/file-list is never its own line — the commit already carries it, and
its absence is not evidence the phase was skipped. Do not re-add "for completeness" (why: wiki).
