---
name: skill-lint
description: Structurally validate skill files against coordinator conventions
argument-hint: "[skill-path|'all']"
user-invocable: true
allowed-tools: ["Read", "Grep", "Glob"]
---

# Skill Lint — Structural Validation

Validate skill files for structural compliance with coordinator plugin conventions. Runs 7 automated checks against one or all skills. Adapted from CCGS Skill Testing Framework static linter.

## Instructions

### Input

`$ARGUMENTS` is either:
- A path to a specific SKILL.md file
- `all` — scan every skill across all enabled plugins

### Phase 1: Discovery

If `$ARGUMENTS` is `all`:
1. Glob for `**/SKILL.md` under `~/.claude/plugins/*/`
2. Also glob for `**/SKILL.md` under any project-local `.claude/plugins/` if present
3. Collect all paths into a skill manifest

If `$ARGUMENTS` is a specific path:
1. Verify the file exists
2. Manifest = [that one file]

### Phase 2: Run 7 Structural Checks

For each skill file in the manifest, run ALL checks and collect findings:

**Check 1: frontmatter-present**
- File must start with `---` YAML frontmatter block
- Frontmatter must contain at minimum a `description` field
- FAIL if no frontmatter or missing description

**Check 2: description-quality**
- `description` must be a single sentence (no newlines)
- Must be under 200 characters
- Should start with an action verb ("Run", "Create", "Validate", "Check") or "Use when"
- WARN if description doesn't follow conventions, FAIL if missing or over 200 chars

**Check 3: no-orphan-skills**
- The SKILL.md must be inside a directory under a plugin's `skills/` or `commands/` folder
- Path pattern: `*/skills/*/SKILL.md` or `*/commands/*.md`
- WARN if the skill appears to be orphaned (not under a recognized plugin structure)

**Check 4: section-structure**
- Must contain at least one top-level heading (`# ...`)
- Must contain an Instructions, Overview, or Phase section
- WARN if minimal structure

**Check 5: no-unresolved-markers**
- Scan for: TODO, FIXME, PLACEHOLDER, TBD, [UNKNOWN], XXX
- WARN for each occurrence found (with line number)

**Check 6: size-bounds**
- WARN if file is under 20 lines (likely a stub)
- WARN if file is over 500 lines (consider splitting)

**Check 7: cross-references-valid**
- Find any `coordinator:skill-name` or backtick-quoted skill references
- Verify each referenced skill directory exists under the coordinator plugin
- WARN for unresolvable references

**Check 8: no-inline-context-dispatch**

Prevents dispatch-prompt templates from re-transmitting context the specialist could have read from disk (the Aura anti-pattern).

Scan for these violation markers in dispatch-prompt templates and `Agent(...)` call blocks:
- "Here is the context:" or "Here is the relevant context:" — spec summary being passed inline
- "Previous context:" or "Earlier context:" — earlier conversation re-transmitted
- "The plan is as follows:" followed by >200 characters of inline plan text — plan not persisted to disk
- Fenced code blocks with >500 characters inside a dispatch prompt template where a file path could substitute
- `previous_context`, `context_summary`, `relevant_data` as parameter names in Agent dispatch calls

**Whitelist (NOT violations — these are reference payload or ephemeral dispatches):**
- Strings matching `/Game/[A-Za-z0-9/_\.]+` (UE asset paths) — reference payload
- `objectPath`, `blueprintPath`, `assetPath`, `actorId`, `actorLabel` parameter names — editor state references
- Single-action dispatches with ≤3 planned tool calls — ephemeral, no spec to persist
- `stub_path`, `plan_path`, `file_path`, `spec_path` parameter names — on-disk spec pointers
- Arrays of path strings, even if >500 tokens — references-as-payload, not context re-transmission

FAIL if a dispatch-prompt template contains violation markers outside the whitelist patterns.
WARN if a dispatch-prompt template passes >2000 characters of inline text that lacks a `path` parameter pointing at a corresponding on-disk file.

### Phase 3: Report

For each finding, output:
```
[PASS|WARN|FAIL] check-name: message (file:line)
```

End with summary:
```
Skill lint complete: N skills checked, N passed all checks, N warnings, N failures
```
