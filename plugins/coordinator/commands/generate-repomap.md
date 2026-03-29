---
description: Generate a ranked repository map for LLM context injection
allowed-tools: ["Bash", "Read"]
argument-hint: "[--budget N] [--project-root PATH] [--profile PROFILE]"
---

# Generate Repository Map

Generate a structural map of the current repository, ranked by git activity, fitted to a token budget. Output goes to `tasks/repomap.md` in the project root.

## Instructions

### Running the Generator

**Default invocation** (no arguments):
```bash
python3 .github/scripts/generate-repomap.py \
  --project-root "${PROJECT_ROOT:-.}" \
  --budget 4000 \
  --profile balanced
```

**With user arguments:** If `$ARGUMENTS` is provided, pass the entire argument string to the script. The script handles its own defaults for any flags not specified:
```bash
python3 .github/scripts/generate-repomap.py $ARGUMENTS
```

User arguments always take full precedence — do not merge individual flags with defaults.

After generation, briefly report:
- Number of files included vs total
- Approximate token count
- Output path

The map is cached — subsequent runs only re-parse changed files.

### Task-Scoped Maps

For generating maps focused on specific task areas:

```bash
python3 .github/scripts/generate-repomap.py \
  --project-root /path/to/project \
  --task "Implement the camera follow system for the drone actor" \
  --focus-files "Source/DroneSim/Camera/CameraFollowComponent.cpp,Source/DroneSim/Drone/DroneActor.h"
```

- `--task`: Natural language description of the current task. Path-like tokens in the description are matched against project files.
- `--focus-files`: Comma-separated list of file paths (relative to project root) to boost. These files and their graph neighbors get priority.
- When either flag is used, output defaults to `tasks/repomap-task.md` instead of `tasks/repomap.md`.
- Task-scoped maps are awareness-based — the coordinator decides when to generate them, not every dispatch.

### Error Handling

If the script fails:
1. **Python not found:** Check that `python3` is on PATH. On Windows, `python` may be the correct command — try both.
2. **Script not found:** Verify `.github/scripts/generate-repomap.py` exists. If running from a different machine, the path may differ.
3. **Non-zero exit code:** Report the script's stderr output to the user. Common causes: missing dependencies (run `pip install -r .github/scripts/requirements-repomap.txt`), permission errors on the cache file, or invalid `--project-root` path.
4. **No output generated:** Check that the project root contains trackable files (not an empty directory).
