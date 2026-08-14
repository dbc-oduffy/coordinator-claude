#### 3e. Directories

Only create directories with real day-1 content or referenced by files being written in this phase:
create `docs` (for `README.md` in 3d), and the ephemeral,
git-ignored `scratch/subagent-sandbox` (deliberately outside `canonical-structure.yaml`, which
would otherwise scaffold README.md/.gitkeep sentinels only to have them immediately git-ignored —
its git-tracked twin, `state/subagent-share/`, IS in `canonical-structure.yaml` and is scaffolded
by the invocation below).

**Scaffold contract-bearing directories and the full `state/` skeleton** by invoking the engine-plane `coordinator_core.install.scaffold_structure` CLI. This is idempotent — safe to re-run; never clobbers existing content. Resolve the engine-plane root the same way the rest of this skill does (`REPO_CLAUDE_KLABAUTER` / `CLAUDE_KLABAUTER_ROOT` / the machine-local registry pointer), then invoke `python3 -m coordinator_core.install.scaffold_structure --manifest-root <coordinator-plugin-root>` from that root with `CLAUDE_KLABAUTER_ROOT` exported and `PYTHONPATH` including it (`--root` defaults to the current git repo root when omitted, so no explicit `--root` is needed when run from the target repo). Skip with a stderr note — `canonical structure scaffold skipped — engine-plane not resolvable` — when the engine-plane root doesn't resolve.

Reads `canonical-structure.yaml` (source of truth for the skeleton). For each `creation: eager` entry: any entry with a non-null `readme:` gets a `README.md` (contract-bearing dirs like `cross-repo/inbox/`, or a seeded signal-bearing dir like `state/handoffs/`); `gitkeep: true` dirs get a `.gitkeep` sentinel (full `state/` subdir skeleton + `tasks/`). Idempotent — `.gitkeep` skips dirs containing real files.

**Most tracker files are NOT pre-created** (`state/lessons/` entries, etc.) — they are written lazily by their owning skills on first use (see the lazy-creation audit table in `SKILL.md`). Pre-creating empty tracker files trains agents to ignore the directory; empty scaffolding has zero signal value. **Exception — `state/orientation_cache.md`** is now eagerly seeded by Phase 3h
(`residue/phase3-substrate-seeds.md`): PM has just ratified project name, type, and workstreams in Phase 2, so meaningful day-1 content exists. See `docs/wiki/produce-not-prescribe.md` for the underlying principle.

#### 3f. .gitignore handling

Ensure `.gitignore` contains the canonical block:

```
# Machine-specific Claude settings (do not commit)
.claude/settings.local.json

# Scratch — transient agent output, investigation notes, workstream byproduct.
# `scratch/` matches at any depth (top-level scratch/, tasks/scratch/, etc.)
scratch/
tasks/_*.log

# Per-session transient markers (produce-not-prescribe sentinel — consumed by /workstream-start)
state/.repo-setup-*

# Ceremony/coverage per-run transients — receipts, gate results, last-phase caches written
# by the wsc ceremony op every /workstream-complete run. Tracking them re-dirties the tree and
# wedges the dirty-tree gate on the op's OWN regenerated output (self-transient loop).
state/ceremony/*.json
state/coverage/*.json
```

Procedure:

1. **If `.gitignore` doesn't exist:** Create it with the canonical block above.
2. **If `.gitignore` exists but is missing any of the canonical rules:** Append only the missing rules under a single comment header (`# Coordinator universal — scratch + machine-local settings`).
3. **If all canonical rules are present:** Skip silently.
4. **If the ceremony/coverage transients are already TRACKED** (`git ls-files state/ceremony/*.json state/coverage/*.json` non-empty): after adding the ignore rules, `git rm --cached` them — a tracked-then-ignored transient still wedges the dirty-tree gate until untracked.

**Warning checks:**

- If `.gitignore` ignores all of `.claude/` (`.claude/` or `.claude/*`), warn: only `.claude/settings.local.json` needs ignoring.
- If tracked content exists under `scratch/` or `tasks/_*.log`, surface count and offer `git rm --cached -r` cleanup (confirm with PM first — don't auto-untrack).

#### 3f.5. Auto-push post-commit hook

Delegate to the canonical idempotent self-heal helper — it handles install (hook absent), repair (hook present but not routed), and exec-bit fix (hook present but `chmod -x`) in one place: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-ensure-post-commit-hook"`.

Idempotent and near-zero cost when already installed (one stat + one grep). A repo that pre-dated the doctrine, had its `.git/hooks/` wiped, or was cloned without `/repo-setup` ever being run is self-healed by re-running `/repo-setup`, not by session boot alone.

Skip if a custom auto-push hook already exists and the PM has signed off on it.

#### 3f.5.6. Session-Id trailer prepare-commit-msg hook

Delegate to the same idempotent self-heal pattern as 3f.5 — installs the `prepare-commit-msg` hook that injects a `Session-Id: <id>` git trailer on every commit (resolution-order, env-only: `CLAUDE_SESSION_ID` → `CLAUDE_CODE_SESSION_ID`). The trailer is the substrate `~/.claude/plugins/coordinator/bin/review-brightline-gate.py --session-id` filters on so the brightline gate fires on this session's commits, not the whole shared-branch diff: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-ensure-prepare-commit-msg-hook"`.

Idempotent; silent no-op when no session-id resolves (legitimate non-coordinator commits stay unaffected). Self-healing runs by re-invoking `/repo-setup`, not via a session-boot hook.

#### 3f.7. Concurrent-EM git config hardening

Harden this repo's git config against two concurrent-EM Git-for-Windows failure modes — `gc.autoDetach false` so git's auto-maintenance runs synchronously instead of detaching into a background process that can orphan the index lock, and `core.checkStat minimal` so the index comparison ignores the NTFS-unstable `ctime/ino/dev` fields that cause a phantom-dirty tree under concurrent index rewrites — via `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-configure-git"`.

Idempotent — safe to re-run; a no-op if already hardened.

#### 3f.5.5. Meta-repo pre-commit exec-bit gate (conditional)

Install via `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/install-meta-repo-precommit-hook" "$HOME/.claude"`.

Idempotent. Pass `"$HOME/.claude"` explicitly so the install is cwd-independent — without the arg the installer derives the repo root from cwd, which is the consumer *project* repo during `/repo-setup`, so the gate would silently never land in the meta-repo. The helper still internally gates on `canon(repo-root) == canon($HOME/.claude)` — installs the pre-commit gate only in the meta-repo itself, no-ops in consumer repos. If an existing `pre-commit` hook is present without the gate marker, the installer appends the invocation instead of clobbering it.

**Why this is conditional.** The helper scans `~/.claude/plugins/*` for exec-bit drift on `.sh` files — a meta-repo concern. Consumer-repo commits don't touch that tree; installing the hook in a consumer repo would fire the helper on every commit only to have it immediately exit 0. The `/workday-complete` Step 5 gate remains the meta-repo's end-of-day backstop; this hook is the earlier-cadence catch.

**Override:** `COORDINATOR_OVERRIDE_PRECOMMIT_EXEC_BIT=1 git commit ...` bypasses the gate for emergency commits.

#### 3f.6. VS Code read-only guard for generated trackers

Mark generated tracker renders read-only in VS Code (and forks that
honor `files.readonlyInclude`) so a human does not accidentally hand-edit a file
the renderer overwrites. This is the editor-side complement to the agent-side
guard (the `preuse-bash-dispatch.py` PreToolUse(Bash) dispatcher's tracker-edit
guard, which ships with the plugin and needs no per-project setup). Idempotent — merges the glob into
`.vscode/settings.json` without clobbering existing settings, via `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/ensure-vscode-readonly" --root "$(pwd)"`.

The helper skips loudly if `jq` is absent or `.vscode/settings.json` is JSONC
(comments/trailing commas) — in that case the report should note the key to
add by hand for whichever generated artifacts the repo carries.
(The tracker globs this note used to list are retired along with the trackers
themselves.) Offer-shaped, not a hard lock: a
user can still override per-file via VS Code's "Set Active Editor Writeable".
