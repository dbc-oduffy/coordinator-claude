---
segment_id: diff-trigger-and-freeze
surface: diff
class: protected
order: 10
---

**Trigger — `--surface diff`:** EM has a code change ready for review (outgoing): mid-session diff before commit, completed task before next dispatch, branch ready for `/merging-to-main`, PR landing inline. OR a code-review's findings have landed and need processing (incoming).

**`--surface diff`**

**Freeze the diff before dispatching `code-reviewer` — part of the dispatch contract, not an enhancement.** `code-reviewer`'s Bash is allowlist-confined to a single literal absolute `<settings-home>/bin/coordinator-doc-new --type review-findings` command (the dispatching EM resolves the settings home per `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md` — and injects the literal path — the confined reviewer cannot resolve shell expansion itself) (engine guard `coordinator_core.bash_guards.block_reviewer_bash_outside_allowlist`, fail-closed, no escape hatch) — it cannot run `git show`/`git diff`/`git log` and has no way to obtain a diff on its own. Without a frozen diff the reviewer reads current on-disk state, not the change under review.

- Before dispatch, freeze the diff by invoking the engine's `freeze-review-diff` via the settings-home forwarder — never a hand-typed `git diff > file` payload, and never a hand-rolled engine-root resolution ladder:

  `& "$env:COORDINATOR_SETTINGS_HOME\bin\freeze-review-diff.exe" --range "<scope-appropriate-range>" --slice-id "<slice-id>"`
  (shape per `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`; PowerShell shown)

  The CLI writes `state/review-trail/diffs/<slice-id>.diff` and `<slice-id>.head.sha` and prints the resolved `.diff` path on stdout — capture it as `$DIFF_PATH` and fail loud on non-zero exit rather than dispatching the reviewer over an unfrozen diff. `<slice-id>` — the branch slug, plan stem, or chunk id the dispatch is scoped to.

  **You choose the range, the CLI freezes it.** `--range` is required and the tool never defaults it — the division of responsibility is explicit: only the caller knows which range is correct for this dispatch.
  - Session-scoped (workstream-complete Step 2.9, `/handoff`) — resolve via `--session-id`, per Step 2.9's own resolution logic; don't restate the mechanics here, defer to it.
  - Branch- or PR-scoped (standalone branch/PR review, no concurrent peers on the branch) — `origin/main...HEAD` is appropriate.
  - Plan- or chunk-scoped (a dispatch scoped to one plan or one chunk of a larger review) — that plan's/chunk's own commit range.
  - **Never default to `origin/main...HEAD` on a shared `work/*` branch with concurrent sessions** — it sweeps sibling sessions' already-reviewed commits into this review.
- Inject `$DIFF_PATH` into the reviewer's dispatch brief as the primary artifact. The working tree is context only — the frozen diff is what gets reviewed.
- **A `code-reviewer` dispatch without an injected diff path is incomplete, not merely suboptimal.** `workstream-complete` Step 2.9 and `/handoff` both route through this dispatch — the requirement is stated once here and inherited by reference, not restated at each caller.


Pre-flight: diff frozen and `$DIFF_PATH` captured and injected into the brief; reviewer selected (A.2 below) and dispatched per Pattern A/B.
