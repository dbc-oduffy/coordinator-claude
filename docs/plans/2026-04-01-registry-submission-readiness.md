# Plugin Registry Submission Readiness

> **For Claude:** REQUIRED SUB-SKILL: Use /execute-plan to implement this plan task-by-task.

**Goal:** Close all gaps between our current plugin state and Anthropic official registry submission requirements, cleanly extract deep-research to its own repo, then submit.

**Status:** Tasks 1-9 complete. Task 10 (registry submission) deferred to next session.

**Architecture:** Two-track approach — (1) fix manifest and README gaps across all plugins, (2) cleanly extract deep-research to its own standalone GitHub repo (removed from monorepo entirely). Then submit deep-research standalone and the remaining 6 via git subdirectory. Tasks 1-5 touch deep-research while it's still in the monorepo; Task 8 extracts it.

**Review:** Reviewed by Patrik. 2 major, 4 minor findings applied below.

---

## Task 1: Add `license` field to all 7 plugin.json files

**Files:**
- Modify: `plugins/coordinator/.claude-plugin/plugin.json`
- Modify: `plugins/data-science/.claude-plugin/plugin.json`
- Modify: `plugins/deep-research/.claude-plugin/plugin.json`
- Modify: `plugins/game-dev/.claude-plugin/plugin.json`
- Modify: `plugins/notebooklm/.claude-plugin/plugin.json`
- Modify: `plugins/remember/.claude-plugin/plugin.json`
- Modify: `plugins/web-dev/.claude-plugin/plugin.json`

Add `"license": "MIT"` to every plugin.json. Root repo already has MIT LICENSE file.

**Step 1:** Add the field to each file after the `description` field.

**Step 2:** Commit: `plugin manifests: add MIT license field to all 7 plugins`

---

## Task 2: Fix remember plugin.json — add missing fields

**Files:**
- Modify: `plugins/remember/.claude-plugin/plugin.json`

remember is the only plugin missing `repository` and `keywords`. Add:
```json
"repository": "https://github.com/oduffy-delphi/coordinator-claude",
"keywords": ["session-memory", "claude-code", "temporal-memory", "session-history"]
```

Also add `hooks` declaration since remember has `hooks/hooks.json`:
```json
"hooks": "./hooks/hooks.json"
```

**Step 1:** Add the three fields.

**Step 2:** Commit: `remember plugin.json: add repository, keywords, hooks fields`

---

## Task 3: Declare component paths in all plugin.json files

**Files:** All 7 `plugin.json` files.

The schema supports `commands`, `agents`, `hooks`, `mcpServers` as path declarations. Skills are auto-discovered (no manifest field). Add declarations for components that exist:

| Plugin | `agents` | `commands` | `hooks` | `mcpServers` |
|--------|----------|------------|---------|---------------|
| coordinator | `"./agents"` | `"./commands"` | `"./hooks/hooks.json"` | — |
| data-science | `"./agents"` | — | — | — |
| deep-research | `"./agents"` | `"./commands"` | — | — |
| game-dev | `"./agents"` | — | — | — |
| notebooklm | `"./agents"` | `"./commands"` | — | `"./.mcp.json"` |
| remember | — | — | `"./hooks/hooks.json"` | — |
| web-dev | `"./agents"` | — | — | — |

Note: notebooklm `.mcp.json` confirmed to exist. These supplement auto-discovery, so adding them is declarative/informational — won't break anything.

**Step 1:** Add component path fields to each plugin.json.

**Step 2:** Commit: `plugin manifests: declare component paths (agents, commands, hooks, mcpServers)`

---

## Task 4: Add `homepage` to plugin.json files (6 of 7)

**Files:** All plugin.json files **except** deep-research (its homepage will be set once in Task 8 to point directly to the standalone repo — avoids double-touch churn).

```json
"homepage": "https://github.com/oduffy-delphi/coordinator-claude"
```

**Step 1:** Add to each file (skip deep-research).

**Step 2:** Commit: `plugin manifests: add homepage field`

---

## Task 5: Update coordinator plugin.json description + sync install.sh versions

**Files:**
- Modify: `plugins/coordinator/.claude-plugin/plugin.json`
- Modify: `setup/install.sh`

Two fixes:
1. The coordinator description says "23 workflow skills" — now 24. Fix it.
2. `setup/install.sh` PLUGIN_REGISTRY (line ~22-29) has hardcoded versions that are out of sync with actual plugin.json versions (e.g., coordinator listed as 1.0.0 but is actually 1.1.0, notebooklm listed as 1.0.0 but is 1.1.0). Sync all versions to match their plugin.json files.

**Step 1:** Fix the coordinator description.

**Step 2:** Sync all PLUGIN_REGISTRY versions in install.sh to match plugin.json.

**Step 3:** Commit: `fix: coordinator description skill count + install.sh version sync`

---

## Task 6: Write README.md for deep-research plugin

**Files:**
- Create: `plugins/deep-research/README.md`

Follow the pattern of existing plugin READMEs (coordinator, game-dev). Cover:
- What it does (3 pipelines: A internet, B repo, C structured)
- Prerequisites (Agent Teams experimental flag)
- Agents table (6 agents: repo-scout, repo-specialist, research-scout, research-specialist, research-synthesizer, structured-synthesizer)
- Commands table (4: /deep-research, /research, /structured, /web)
- Pipeline overview (Haiku scouts → Sonnet specialists → Opus sweep)
- Usage examples
- Works standalone or as part of the coordinator system

Write it for a standalone audience — this becomes the repo README after extraction in Task 8.

**Step 1:** Write the README.

**Step 2:** Commit: `deep-research: add plugin README`

---

## Task 7: Write README.md for notebooklm and remember plugins

**Files:**
- Create: `plugins/notebooklm/README.md`
- Create: `plugins/remember/README.md`

Same pattern as Task 6. Shorter — these are simpler plugins.

**notebooklm README:** What it does (YouTube/podcast research via NotebookLM MCP), agents (3), commands (1), MCP dependency, usage.

**remember README:** What it does (automatic session memory), how it works (Haiku summarization, rolling compression), hooks, skill (1: remember), no agents or commands. Cross-platform Node.js.

**Step 1:** Write both READMEs.

**Step 2:** Commit: `notebooklm, remember: add plugin READMEs`

---

## Task 8: Extract deep-research — clean split to standalone repo

**Files in new repo:**
- All contents of `plugins/deep-research/` → repo root
- Copy: root `LICENSE` file
- Copy: `docs/research/2026-03-31-deep-research-pipeline-evidence.md` → `docs/research/`
- Copy: `docs/research/2026-03-21-deep-research-prompt-improvements.md` → `docs/research/`
- Update: `.claude-plugin/plugin.json` — set `repository` and `homepage` to new repo URL

**Files in monorepo (after extraction):**
- Delete: `plugins/deep-research/` entirely (clean split, not dual-homed)
- Modify: `.claude-plugin/marketplace.json` — remove deep-research entry, also remove holodeck-control and holodeck-docs entries (those plugins aren't in this repo and will fail source resolution)
- Modify: `setup/install.sh` — remove deep-research from PLUGIN_REGISTRY, add a comment noting it's now at the standalone repo
- Modify: `README.md` — update deep-research entry in Plugins table to point to standalone repo instead of `plugins/deep-research/`
- Modify: `README.md` — update directory structure (remove deep-research line)
- Modify: `plugins/coordinator/README.md` — update any deep-research cross-references
- Check: `docs/research/2026-03-31-deep-research-pipeline-evidence.md` is referenced by the root README — keep the copy in monorepo since it backs claims about the overall system, not just deep-research

Note: `setup/dev-sync.sh` iterates `plugins/*/` and auto-skips missing directories — no changes needed.

**Step 1:** Create new GitHub repo (PM picks name — suggested: `deep-research-claude`).

**Step 2:** Copy files to new repo, update plugin.json, add LICENSE, add research docs.

**Step 3:** Run `claude plugin validate` in the new repo.

**Step 4:** In monorepo: delete `plugins/deep-research/`, update marketplace.json, install.sh, READMEs.

**Step 5:** Commit in monorepo: `extract deep-research to standalone repo`

**Step 6:** Push both repos.

---

## Task 9: Run `claude plugin validate` on remaining 6 monorepo plugins

**Files:** None modified — validation only.

deep-research was already validated in Task 8 Step 3 in its standalone repo. This task validates the 6 remaining monorepo plugins.

```bash
claude plugin validate plugins/coordinator
claude plugin validate plugins/data-science
claude plugin validate plugins/game-dev
claude plugin validate plugins/notebooklm
claude plugin validate plugins/remember
claude plugin validate plugins/web-dev
```

Fix any validation errors (separate commit per fix if needed).

---

## Task 10: Submit to registry

1. Submit deep-research standalone repo via `claude.ai/settings/plugins/submit`
2. Submit remaining 6 plugins from monorepo via git subdirectory source type
3. Document what we submitted and any response in a session note

This is a manual step — the PM does the form submission, or we do it together.

---

## Verification

- [ ] All 7 plugin.json files have: name, version, description, author, repository, license, keywords, homepage
- [ ] All 7 plugin.json files declare their component paths (agents, commands, hooks where applicable)
- [ ] All 7 plugins have a README.md
- [ ] `claude plugin validate` passes on all 7 (6 monorepo + 1 standalone)
- [ ] deep-research standalone repo exists with LICENSE + research docs
- [ ] `plugins/deep-research/` removed from monorepo (clean split)
- [ ] `.claude-plugin/marketplace.json` updated — deep-research removed, holodeck entries removed
- [ ] `setup/install.sh` — deep-research removed from PLUGIN_REGISTRY, versions synced
- [ ] `setup/dev-sync.sh` — no changes needed (auto-skips missing dirs)
- [ ] Root README.md deep-research entry points to standalone repo
- [ ] Root README.md directory structure updated
- [ ] Research docs referenced by root README still resolve (kept in monorepo)
- [ ] remember plugin.json has repository and keywords fields
