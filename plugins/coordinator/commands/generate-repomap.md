---
description: Generate a ranked repository map for LLM context injection
allowed-tools: ["Bash", "Read"]
argument-hint: "[--budget N] [--project-root PATH] [--profile PROFILE]"
---

# Generate Repository Map

Generate a structural map of the current repository, ranked by git activity, fitted to a token budget. Output goes to `.claude/repomap.md` in the project root (this is where the SessionStart staleness hook looks).

## Instructions

### Locating the Generator

The generator script is shared across projects. Resolve its path in this order:

1. **Global install:** `~/.claude/.github/scripts/generate-repomap.py` (preferred — installed once, serves all projects)
2. **Project-local:** `.github/scripts/generate-repomap.py` (legacy; may exist in older projects)

Pick whichever exists. If neither exists, report the error and stop.

### Running the Generator

**Default invocation** (no arguments):
```bash
GENERATOR="$HOME/.claude/.github/scripts/generate-repomap.py"
[ -f "$GENERATOR" ] || GENERATOR=".github/scripts/generate-repomap.py"
python3 "$GENERATOR" \
  --project-root "${PROJECT_ROOT:-.}" \
  --budget 4000 \
  --profile balanced
```

**With user arguments:** If `$ARGUMENTS` is provided, pass the entire argument string to the script. The script handles its own defaults for any flags not specified:
```bash
python3 "$GENERATOR" $ARGUMENTS
```

User arguments always take full precedence — do not merge individual flags with defaults.

After generation, briefly report:
- Number of files included vs total
- Approximate token count
- Output path (`.claude/repomap.md` by default)

The map is cached — subsequent runs only re-parse changed files.

### Task-Scoped Maps

For generating maps focused on specific task areas:

```bash
python3 "$GENERATOR" \
  --project-root /path/to/project \
  --task "Implement the camera follow system for the drone actor" \
  --focus-files "Source/DroneSim/Camera/CameraFollowComponent.cpp,Source/DroneSim/Drone/DroneActor.h"
```

- `--task`: Natural language description of the current task. Path-like tokens in the description are matched against project files.
- `--focus-files`: Comma-separated list of file paths (relative to project root) to boost. These files and their graph neighbors get priority.
- When either flag is used, output defaults to `.claude/repomap-task.md` instead of `.claude/repomap.md`.
- Task-scoped maps are awareness-based — the coordinator decides when to generate them, not every dispatch.

### Error Handling

If the script fails:
1. **Python not found:** Check that `python3` is on PATH. On Windows, `python` may be the correct command — try both.
2. **Script not found at either path:** The generator lives at `~/.claude/.github/scripts/generate-repomap.py` (global) or `.github/scripts/generate-repomap.py` (project-local legacy). If neither exists, the user's `~/.claude` config is incomplete — point them at `scripts/setup-ue-repomap.{sh,ps1}` (if present) or the coordinator-claude repo install docs.
3. **Non-zero exit code:** Report the script's stderr output to the user. Common causes: missing dependencies (run `pip install -r ~/.claude/.github/scripts/requirements-repomap.txt`), permission errors on the cache file, or invalid `--project-root` path.
4. **No output generated:** Check that the project root contains trackable files (not an empty directory).
