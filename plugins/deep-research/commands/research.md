---
description: "PM-GATED — only invoke when the PM explicitly asks for deep research; if the EM thinks it's warranted, ask first. NEVER invoke from a subagent. Run a deep research pipeline on a topic across internet sources (Pipeline A), a repository (Pipeline B), or structured research with schema-conforming output (Pipeline C). Use for studying codebases, building knowledge bases, evaluating libraries, or investigating multi-source technical topics with verified findings. For batch structured research campaigns, use /structured-research instead."
allowed-tools: ["Read", "Bash"]
argument-hint: "'repo' <repo-path> [--compare <project-path>] | 'web' <topic> | 'structured' <spec-path> [subject-key]"
---

# Deep Research — Router

This command routes to the appropriate pipeline-specific driver.

## Step 1: Parse Arguments

`$ARGUMENTS` determines the pipeline:

- **`web <topic>`** — Pipeline A (internet research, Agent Teams)
- **`repo <path> [--compare <path>]`** — Pipeline B (repo research, Agent Teams)
- **`structured <spec-path> [subject-key]`** — Pipeline C (structured research, Agent Teams)
- **Auto-detect:** if the first argument is a path that exists on disk → repo; otherwise → web

## Step 2: Route

Use the Skill tool to invoke the appropriate sub-command, passing through all arguments:

- **Pipeline A:** `skill: "deep-research:web", args: "<remaining arguments>"`
- **Pipeline B:** `skill: "deep-research:repo", args: "<remaining arguments>"`
- **Pipeline C:** `skill: "deep-research:structured", args: "<remaining arguments>"`

That's it. The driver handles everything from here.
