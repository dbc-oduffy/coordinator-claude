---
description: Bootstrap coordinator scaffolding into all discovered working repos. Agent-led (the agent drives all repos) or hands-on (per-repo selection). Safe to re-run.
allowed-tools: ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "AskUserQuestion"]
argument-hint: "[--check-only] [--non-interactive]"
---

# /bootstrap-repos — Coordinator Bootstrap

<!-- spec-backlink: docs/plans/2026-05-29-it-just-works-agentic-install-currency.md § Chunk 4 -->

Bootstrap coordinator scaffolding into your working repos. Reads the repo list from
`~/.claude/working-repos.yaml` (produced by `/setup` Phase 2 Step 4) and applies the
Wave-1 `lib/bootstrap-repo.sh` primitive to each selected repo.

If `$ARGUMENTS` contains `--check-only`, produce the per-repo action list and exit without
writing anything.

If `$ARGUMENTS` contains `--non-interactive`, skip all `AskUserQuestion` prompts, applying
the non-interactive fallback documented in **§ Non-Interactive Contract** below.

---

## Precondition

`~/.claude/working-repos.yaml` must exist. If it is absent, this command cannot proceed:

```bash
test -f ~/.claude/working-repos.yaml && echo "ready" || echo "missing"
```

If missing, direct the user to run `/setup` first (or `/coordinator:setup`) — it discovers
and records the working-repos list at Phase 2 Step 4. Under `--non-interactive`, exit non-zero
with a remediation message (no prompt possible).

---

## Step 1 — Parse working-repos.yaml

Read `~/.claude/working-repos.yaml` and extract the `repos:` block (not `out_of_tree:`).
Normalize each path to a POSIX form for existence checks (Windows `X:\foo` → `/x/foo`).
Filter to repos that exist on disk; collect absent repos separately (they may simply not be
checked out on this machine — not an error).

If no repos exist on disk, fail with a clear message.

---

## Step 2 — Surface the execution-dial offer

This is the guided install decision point. You participate in the shape; the agent moves fast
on mechanism. Present two dial settings:

**Agent-led** — the agent bootstraps all discovered repos in partnership; you approve the lot.
**Hands-on** — walk each repo as an individual offer; you decide which repos get bootstrapped.

```
=== /bootstrap-repos — Coordinator Bootstrap ===

  Repos discovered in ~/.claude/working-repos.yaml (N on disk):
    - /path/to/repo-1
    - /path/to/repo-2
    ...

  How would you like to proceed?

  [Agent-led]  Bootstrap all repos above (recommended — safe to re-run, fully reversible)
  [Hands-on]   Choose repos one by one

  Choice [A/H, default A]:
```

Under hands-on, present each repo as a yes/no offer:
```
  Bootstrap '/path/to/repo-1'? [Y/n]
```

<!-- D4 annotation (mode choice): default-with-warning — non-interactive defaults to agent-led. -->

**Under `--non-interactive`:** auto-select agent-led (bootstrap all repos on disk); emit a
one-line note: `--non-interactive — selecting agent-led path (bootstrap all N repo(s)).`

---

## Step 3 — Bootstrap each selected repo

For each selected repo, invoke the existing Wave-1 primitive:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/lib/bootstrap-repo.sh" \
    --root "<repo_path>" \
    --non-interactive
```

**Hook-respect contract:** neither `bootstrap-repo.sh` nor this orchestration helper passes
`--no-verify`. Every commit landed into a target repo — the `chore(coordinator): bootstrap`
commit and the `chore(coordinator): record currency stamp` commit — runs that repo's hooks
exactly as the user would. If a hook fails:

- `bootstrap-repo.sh` exits non-zero; its stderr (including hook output) is surfaced in full.
- This command records the repo as failed, surfaces the per-repo failure in the summary table,
  and exits non-zero.
- The operator must resolve the hook failure (fix the hook or commit the hook-mandated
  changes) and re-run `/bootstrap-repos`.

**Under `--check-only`:** pass `--dry-run` to `bootstrap-repo.sh`; write nothing; collect
and print the per-repo action list.

---

## Step 4 — Stamp coordinator currency

After each successful bootstrap, stamp the currency record and commit it:

```bash
source "${CLAUDE_PLUGIN_ROOT}/lib/coordinator-currency.sh"
coordinator_currency_write "<repo_path>" "${CLAUDE_PLUGIN_ROOT}"
# Stage and commit the stamp so the working tree stays clean for subsequent runs.
# No --no-verify: the target repo's hooks must run, matching the hook-respect contract.
git -C "<repo_path>" add -- docs/coordinator-currency.yaml
git -C "<repo_path>" commit -m "chore(coordinator): record currency stamp"
```

This records which `COORDINATOR_SCHEMA_VERSION` the repo was bootstrapped against.
The commit keeps the working tree clean — without it, a subsequent `/bootstrap-repos` run
would see `docs/coordinator-currency.yaml` as an untracked file and `bootstrap-repo.sh`
would refuse with a dirty-tree error, breaking idempotency.

The write is idempotent — if the stamp already exists at the current version, no file
change is made and no commit is needed.

Skip under `--check-only`.

---

## Step 5 — Summary table

After processing all selected repos, emit a summary:

```
=== /bootstrap-repos summary ===

  Succeeded:   N
  Failed:      N
  Skipped:     N   (non-git repos under --non-interactive)
  Not on disk: N

  Bootstrapped:
    OK  /path/to/repo-1
    OK  /path/to/repo-2

  Skipped:
    --  /path/to/repo-3  (not a git repo — run interactively to be offered git init)

  Failed:
    XX  /path/to/repo-4

  /bootstrap-repos complete.
  Revert any bootstrap commit: git -C <repo> revert HEAD
```

If any repos failed, exit non-zero (exit code 3) with a note directing the operator to
check the per-repo output above. Exit 0 when all selected repos succeeded (or were skipped
because they are not git repos yet).

---

## Non-Interactive Contract

<!-- spec-backlink: coordinator-installer-shape.md § 4 (D4 non-interactive contract) -->

| Step | Prompt site | Annotation | Fallback |
|------|------------|------------|---------|
| Precondition | working-repos.yaml absent | `fail-loud` | Exit non-zero with remediation: run `/setup` first. |
| Step 2 | Agent-led vs hands-on dial | `default-with-warning` | Auto-select agent-led; emit one-line note. |

`--check-only` is a strict superset of `--non-interactive` — no mutations regardless of
interactivity mode. Combining both is supported and behaves identically to `--check-only` alone.

---

## Implementation Note

The agentic paddling beneath this command is encapsulated in
`lib/bootstrap-orchestrate.sh`. The command may invoke it directly:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/lib/bootstrap-orchestrate.sh" \
    ${ARGUMENTS:-}
```

Or implement the steps inline above. The helper and this command share the same contract.

---

## Out-of-Scope

This command does NOT:

- Discover repos (delegates to `~/.claude/working-repos.yaml` — produced by `/setup`).
- Modify `~/.claude/working-repos.yaml` or any Wave-1 library file.
- Author handoffs, spinoffs, or session artifacts.
- Commit into `~/.claude` or any coordinator-managed repo.
- Run git operations against the coordinator meta-repo itself.
- Bypass target-repo commit hooks (see § Hook-respect contract above).

---

## Idempotency

Safe to re-run. `bootstrap-repo.sh` + scaffold are idempotent; the currency stamp write
is idempotent. An agent-led re-run on a fully-bootstrapped set of repos is a no-op —
`bootstrap-repo.sh` emits `"nothing to commit (scaffold was already up to date)"` for
each repo and exits 0.

---

## Destructive-Action Prohibition

This command MUST NOT run `git reset`, `git rm`, `git push --force`, or any destructive
git operation. All mutations are reversible: `git -C <repo> revert HEAD` in the target repo
undoes the bootstrap commit completely.
