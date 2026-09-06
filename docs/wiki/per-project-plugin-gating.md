# Per-Project Plugin Gating

> How UE-anchored plugins are enabled only in UE-context sessions, and how new UE projects opt in.

## Design

Four plugins carry UE-specific routing and description weight:

- `example-game-repo-control@example-game-workbench-repo`
- `example-game-repo-docs@example-game-workbench-repo`
- `example-game-repo@example-game-workbench-repo`
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
python3 $REPO_CLAUDE_KLABAUTER/coordinator/bin/claude-ue-bootstrap.py /path/to/<your-game-repo>
```

The script writes `<project>/.claude/settings.json` with the UE override block. If a `settings.json` already exists, it merges via a right-wins deep update of `enabledPlugins` (existing keys outside `enabledPlugins` are preserved; the four UE plugin keys are set to `true`) using Python's stdlib `json` module — no external `jq`/`node` dependency (naked-Python port, Windows de-bash campaign, chunk I-d).

### 2. SessionStart hook auto-bootstrap (for `.uproject`-bearing repos) — DISABLED

**Status: disabled.** Per PM directive (full-kill-keep-fast-orientation, see `hooks.json`'s `SessionStart` `_comment`), all boot-time guardrail/reminder/detector SessionStart hooks — including this one — were removed from `hooks.json`; only the orientation RAM-cache injector remains. The dead `coordinator/hooks/scripts/ue-knowledge-distrust.sh` file itself was removed. A naked-Python port, `coordinator/hooks/scripts/ue-knowledge-distrust.py`, exists (delegates to claude-klabauter `coordinator_core.hooks.ue_knowledge_distrust.run`) but is not wired into `hooks.json`. The auto-bootstrap behavior described below does not currently fire — use the manual bootstrap in step 1 instead.

Formerly: `ue-knowledge-distrust.sh` detected `.uproject` files and ran the bootstrap script automatically if the per-project `settings.json` was absent or lacked the UE override. The hook fired on every session start.

**Rationale, kept for context:** when the hook fired (pre-2026-07-15), the SessionStart hook ran *after* plugin resolution, so a newly-cloned `.uproject` repo loaded lean defaults on the **first session** — UE plugins kicked in on the **second session**, once the hook had written the override and you closed/re-opened Claude Code. The auto-bootstrap does not run today (see the DISABLED status above): closing and re-opening alone does not write the override — it just repeats the same lean-default session indefinitely.

**User-facing instruction (current):** When you clone a new UE repo, run `python3 $REPO_CLAUDE_KLABAUTER/coordinator/bin/claude-ue-bootstrap.py <repo>` (step 1, above) before launching Claude Code — this is now the only way to get UE plugins, including on the very first session. Closing and re-opening Claude Code without running the bootstrap script will not enable UE plugins.

### 3. Explicit override in project's own `.claude/settings.json`

Projects can commit their own `settings.json` with the UE override block to opt in without running the bootstrap script. Useful when the project is already managing its own `.claude/settings.json` for other reasons.

## Respecting Explicit Disables

If a project's `settings.json` explicitly sets any of the four UE plugin keys to `false`, the SessionStart hook skips the bootstrap and emits a warning:

```
UE override SKIPPED — .claude/settings.json explicitly disables UE plugins
To enable UE plugins in this project, run: python3 $REPO_CLAUDE_KLABAUTER/coordinator/bin/claude-ue-bootstrap.py <cwd>
```

This preserves deliberate disables (e.g., a third-party UE repo where UE plugins are not wanted). The **manual bootstrap script** does NOT check for explicit `false` — if you run it, it overwrites the keys. Own the consequence.

## Drift Verifier

A drift verifier — wired into `/workday-complete` Step 1 as a non-blocking check — walks the set of UE-context dirs and asserts each carries the expected override keys in `.claude/settings.json`. Exits 0 on success; exits 1 with diagnostic output on failure (e.g., someone ran `rm -rf .claude/` in a registered UE dir). On failure, re-run the bootstrap for the flagged dir.

The reference verifier and bootstrap helper are not shipped with this plugin (they're wired to the source author's local layout). Consumers who want this behavior implement their own thin script: a JSON read of `enabledPlugins` per dir, comparing against the four UE plugin keys above, plus the `game-dev@coordinator-claude` opt-in for game-dev sessions.

## Lean-Session Routing — the Game Dev Reviewer Unavailability

The Game Dev Reviewer (`game-dev:staff-game-dev`) is gated to UE-context sessions alongside the `game-dev` plugin. In a lean session, the Game Dev Reviewer is not available. The Staff Engineer's routing note in `coordinator/agents/staff-eng.md` provides conditional guidance: if a UE-context session is available, recommend the Game Dev Reviewer; otherwise surface to PM with a request to relaunch in a UE-context dir.

## Files Involved

| File | Role |
|------|------|
| `~/.claude/settings.json` | Global default — four UE plugins set to `false` |
| `<project>/.claude/settings.json` | Per-project opt-in — four UE plugins set to `true` |
| claude-klabauter `coordinator/bin/claude-ue-bootstrap.py` | _(reference helper, not shipped)_ — one-shot script to write/merge the per-project override |
| claude-klabauter `coordinator/bin/verify-ue-overrides.py` | _(reference helper, not shipped)_ — drift verifier for UE-context dirs |
| `coordinator/hooks/scripts/ue-knowledge-distrust.py` | Unwired naked-Python port of the former SessionStart auto-bootstrap hook (disabled; `.sh` ancestor removed) |
| claude-klabauter `coordinator/bin/probe-cwd-project-rag-relevance.py` | Workstream-start probe — emits gift-shape project-RAG importance signal for any project-RAG-bound cwd; UE enrichment layer added when UE detected. Generic cross-stack (UE, TS, Python, meta-repo). Distinct job from the (currently unwired) UE-knowledge-gap warning. |
| `coordinator/commands/workday-complete.md` | _(not auto-invoked)_ — manual diagnostic; run via claude-klabauter `coordinator/bin/verify-ue-overrides.py` when you suspect peer-repo drift |
| `coordinator/agents/staff-eng.md` | Carries lean-session routing note for the Game Dev Reviewer |

## verify-ue-overrides.py — Manual Diagnostic Only

`verify-ue-overrides.py` is a personal-machine config diagnostic: it walks a hardcoded list of peer directories (stored in `NAMED_DIRS` within the script, e.g. `/x/example-sim-repo`, `/x/project-rag`, `~/.claude`) and asserts each carries the expected `enabledPlugins` keys. Because the peer paths are specific to the source author's local layout, the script is not shipped with this plugin and is never auto-invoked by any ceremony. Per `docs/plans/2026-05-08-coordinator-claude-publish-sanitization.md` PM-D3, wiring it into automated sequences on consumer machines would produce false failures wherever the hardcoded peer dirs don't exist. Run it manually when you suspect drift on your own machine; do not add it to any ceremony hook or workstream-start nudge.

---

## What Disappeared (vs. the Original Launcher Design)

The original plan explored a launcher-wrapper approach (PowerShell `$PROFILE` function, `settings.lean.json` / `settings.example-game-repo.json` profile split, concurrent-launch race mitigations). All of that complexity is gone:

- No launcher wrapper in `$PROFILE`
- No profile-split files (no shared global mutation surface)
- No concurrent-launch races (per-project file is written once, read-only thereafter)
- No install-time `$PROFILE` injection questions

The simpler design works because Claude Code's `projectSettings` layer fully overrides `userSettings` for `enabledPlugins` keys.
