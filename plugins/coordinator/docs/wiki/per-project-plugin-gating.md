# Per-Project Plugin Gating

> How UE-anchored plugins are enabled only in UE-context sessions, and how new UE projects opt in.

## Design

Four plugins carry UE-specific routing and description weight:

- `holodeck-control@claude-unreal-holodeck`
- `holodeck-docs@claude-unreal-holodeck`
- `holodeck@claude-unreal-holodeck`
- `game-dev@coordinator-claude`

These are **disabled by default** in `~/.claude/settings.json` (the global user settings). Any project that is not a UE project gets a lean session with these plugins absent — approximately 3K always-on description tokens saved per session.

**UE projects opt in via a committed per-project `settings.json`** at `<project>/.claude/settings.json`. Using `settings.json` (committed) rather than `settings.local.json` (gitignored) means multi-machine git checkouts inherit the UE-on state without re-running bootstrap.

The settings hierarchy Claude Code resolves is:
```
userSettings → projectSettings → localSettings → flagSettings → policySettings
```
`projectSettings` fully overrides `userSettings` for matching keys — a project-level `enabledPlugins` block re-enabling the four UE plugins is sufficient.

## Three Ways to Populate the Per-Project Override

### 1. One-shot bootstrap script (recommended for known UE dirs)

Run once per directory; idempotent (re-running on a project that already has the override is a no-op):

```bash
~/.claude/bin/claude-ue-bootstrap.sh /x/DroneSim
~/.claude/bin/claude-ue-bootstrap.sh /x/project-rag
~/.claude/bin/claude-ue-bootstrap.sh /x/claude-unreal-holodeck
~/.claude/bin/claude-ue-bootstrap.sh ~/.claude
```

The script writes `<project>/.claude/settings.json` with the UE override block. If a `settings.json` already exists, it merges using `jq '. * $new'` (right-wins deep merge — existing keys outside `enabledPlugins` are preserved; the four UE plugin keys are set to `true`). Merge path requires `jq`; no-existing-settings fast path is pure shell.

### 2. SessionStart hook auto-bootstrap (for `.uproject`-bearing repos)

`coordinator/hooks/scripts/ue-knowledge-distrust.sh` now detects `.uproject` files and runs the bootstrap script automatically if the per-project `settings.json` is absent or lacks the UE override. The hook fires on every session start.

**First-session friction:** The SessionStart hook fires *after* plugin resolution. A newly-cloned `.uproject` repo therefore loads lean defaults on the **first session** — UE plugins kick in on the **second session** (after the hook has written the override and you close/re-open Claude Code).

**User-facing instruction:** When you clone a new UE repo, the first Claude Code session loads lean defaults — close and re-open to pick up UE plugins. Or run `~/.claude/bin/claude-ue-bootstrap.sh <repo>` before launching Claude Code to get UE plugins on the very first session.

### 3. Explicit override in project's own `.claude/settings.json`

Projects can commit their own `settings.json` with the UE override block to opt in without running the bootstrap script. Useful when the project is already managing its own `.claude/settings.json` for other reasons.

## Respecting Explicit Disables

If a project's `settings.json` explicitly sets any of the four UE plugin keys to `false`, the SessionStart hook skips the bootstrap and emits a warning:

```
UE override SKIPPED — .claude/settings.json explicitly disables UE plugins
To enable UE plugins in this project, run: ~/.claude/bin/claude-ue-bootstrap.sh <cwd>
```

This preserves deliberate disables (e.g., a third-party UE repo where UE plugins are not wanted). The **manual bootstrap script** does NOT check for explicit `false` — if you run it, it overwrites the keys. Own the consequence.

## Drift Verifier

`~/.claude/bin/verify-ue-overrides.sh` walks the four known UE-context dirs and asserts each carries the expected override. Wired into `/workday-complete` Step 1 as a non-blocking check:

```bash
~/.claude/bin/verify-ue-overrides.sh
```

Exits 0 on success; exits 1 with diagnostic output on failure (e.g., someone ran `rm -rf .claude/` in a named UE dir). On failure, re-run the bootstrap for the flagged dir.

## Lean-Session Routing — Sid Unavailability

Sid (`game-dev:staff-game-dev`) is gated to UE-context sessions alongside the `game-dev` plugin. In a lean session, Sid is not available. Patrik's routing note in `coordinator/agents/staff-eng.md` provides conditional guidance: if a UE-context session is available, recommend Sid; otherwise surface to PM with a request to relaunch in a UE-context dir.

## Files Involved

| File | Role |
|------|------|
| `~/.claude/settings.json` | Global default — four UE plugins set to `false` |
| `<project>/.claude/settings.json` | Per-project opt-in — four UE plugins set to `true` |
| `~/.claude/bin/claude-ue-bootstrap.sh` | One-shot script to write/merge the per-project override |
| `~/.claude/bin/verify-ue-overrides.sh` | Drift verifier for known UE-context dirs |
| `coordinator/hooks/scripts/ue-knowledge-distrust.sh` | SessionStart hook — auto-bootstraps on `.uproject` detection |
| `coordinator/commands/workday-complete.md` | Calls `verify-ue-overrides.sh` in Step 1 validate phase |
| `coordinator/agents/staff-eng.md` | Carries lean-session routing note for Sid |

## What Disappeared (vs. the Original Launcher Design)

The original plan explored a launcher-wrapper approach (PowerShell `$PROFILE` function, `settings.lean.json` / `settings.holodeck.json` profile split, concurrent-launch race mitigations). All of that complexity is gone:

- No launcher wrapper in `$PROFILE`
- No profile-split files (no shared global mutation surface)
- No concurrent-launch races (per-project file is written once, read-only thereafter)
- No install-time `$PROFILE` injection questions

The simpler design works because Claude Code's `projectSettings` layer fully overrides `userSettings` for `enabledPlugins` keys.
