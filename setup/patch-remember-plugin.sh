#!/bin/bash
# patch-remember-plugin.sh — Apply Windows compatibility fixes to the remember plugin
#
# The remember plugin (claude-plugins-official) assumes Unix paths and a
# layout where the plugin lives at $PROJECT/.claude/remember/. On Windows
# with a plugin cache install, two things break:
#
# 1. Path resolution: scripts use ../../.. to find PROJECT_DIR, which gives
#    the wrong path in the plugin cache layout.
# 2. Session slug: `tr '/' '-'` produces wrong slugs on Windows (Git Bash).
#    Claude Code uses a different algorithm: replace all non-alphanumeric,
#    non-dash chars with dashes, from the Windows-style path.
#
# This script patches the installed plugin in-place. Re-run after plugin updates.

set -euo pipefail

PLUGIN_DIR="${1:-$HOME/.claude/plugins/cache/claude-plugins-official/remember/0.1.0}"

if [ ! -d "$PLUGIN_DIR" ]; then
    echo "ERROR: Plugin not found at $PLUGIN_DIR"
    exit 1
fi

echo "Patching remember plugin at: $PLUGIN_DIR"

# --- 1. Create config.json if missing ---
if [ ! -f "$PLUGIN_DIR/config.json" ]; then
    cat > "$PLUGIN_DIR/config.json" << 'CONF'
{
  "data_dir": ".remember",
  "cooldowns": {
    "save_seconds": 120,
    "ndc_seconds": 3600
  },
  "thresholds": {
    "min_human_messages": 3,
    "delta_lines_trigger": 50
  },
  "features": {
    "ndc_compression": true,
    "recovery": true
  },
  "debug": false,
  "timezone": "Europe/Dublin"
}
CONF
    echo "  Created config.json"
fi

# --- 2. Patch log.sh: config/hooks paths + project_slug function ---
LOG_SH="$PLUGIN_DIR/scripts/log.sh"
if ! grep -q 'project_slug' "$LOG_SH" 2>/dev/null; then
    # Fix REMEMBER_CONFIG path
    sed -i 's|REMEMBER_CONFIG="${PROJECT_DIR:-.}/.claude/remember/config.json"|REMEMBER_CONFIG="${CLAUDE_PLUGIN_ROOT:-${PROJECT_DIR:-.}/.claude/remember}/config.json"|' "$LOG_SH"
    # Fix REMEMBER_HOOKS_DIR path
    sed -i 's|REMEMBER_HOOKS_DIR="${PROJECT_DIR:-.}/.claude/remember/hooks.d"|REMEMBER_HOOKS_DIR="${CLAUDE_PLUGIN_ROOT:-${PROJECT_DIR:-.}/.claude/remember}/hooks.d"|' "$LOG_SH"
    # Add project_slug function before the dispatch function
    sed -i '/^REMEMBER_TZ=\$(config/a\
\
# Compute the Claude Code project slug for session JSONL directories.\
project_slug() {\
    local path="$1"\
    if command -v cygpath >/dev/null 2>\&1; then\
        path=$(cygpath -w "$path" 2>/dev/null || echo "$path")\
    fi\
    echo "$path" | sed '"'"'s/[^a-zA-Z0-9-]/-/g'"'"'\
}' "$LOG_SH"
    echo "  Patched log.sh"
else
    echo "  log.sh already patched"
fi

# --- 3. Patch save-session.sh ---
SAVE_SH="$PLUGIN_DIR/scripts/save-session.sh"
# Fix PROJECT_DIR + PIPELINE_DIR
sed -i 's|^PROJECT_DIR="\$(cd "\$(dirname "\$0")/\.\./\.\./\.\." && pwd)"|PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../../.." \&\& pwd)}"|' "$SAVE_SH"
sed -i 's|^PIPELINE_DIR="${PROJECT_DIR}/.claude/remember"|PIPELINE_DIR="${CLAUDE_PLUGIN_ROOT:-${PROJECT_DIR}/.claude/remember}"|' "$SAVE_SH"
# Fix session slug
sed -i "s|echo \"\$PROJECT_DIR\" | tr '/' '-'|project_slug \"\$PROJECT_DIR\"|" "$SAVE_SH"
echo "  Patched save-session.sh"

# --- 4. Patch run-consolidation.sh ---
CONSOL_SH="$PLUGIN_DIR/scripts/run-consolidation.sh"
sed -i 's|^PROJECT_DIR="\$(cd "\$(dirname "\$0")/\.\./\.\./\.\." && pwd)"|PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../../.." \&\& pwd)}"|' "$CONSOL_SH"
sed -i 's|^PIPELINE_DIR="${PROJECT_DIR}/.claude/remember"|PIPELINE_DIR="${CLAUDE_PLUGIN_ROOT:-${PROJECT_DIR}/.claude/remember}"|' "$CONSOL_SH"
echo "  Patched run-consolidation.sh"

# --- 5. Patch post-tool-hook.sh ---
POST_SH="$PLUGIN_DIR/scripts/post-tool-hook.sh"
sed -i "s|echo \"\$PROJECT\" | tr '/' '-'|project_slug \"\$PROJECT\"|" "$POST_SH"
echo "  Patched post-tool-hook.sh"

# --- 6. Patch session-start-hook.sh ---
START_SH="$PLUGIN_DIR/scripts/session-start-hook.sh"
sed -i "s|echo \"\$PROJECT\" | tr '/' '-'|project_slug \"\$PROJECT\"|" "$START_SH"
echo "  Patched session-start-hook.sh"

# --- 7. Patch pipeline/extract.py ---
EXTRACT_PY="$PLUGIN_DIR/pipeline/extract.py"
if ! grep -q '_project_slug' "$EXTRACT_PY" 2>/dev/null; then
    python3 -c "
import re

with open('$EXTRACT_PY', 'r') as f:
    content = f.read()

# Replace the _session_dir function with one that includes _project_slug
old = '''def _session_dir(project_dir: str) -> str:
    \"\"\"Convert a project directory path to its Claude sessions directory.\"\"\"
    return os.path.expanduser(
        \"~/.claude/projects/\" + project_dir.replace(\"/\", \"-\")
    )'''

new = '''def _project_slug(project_dir: str) -> str:
    \"\"\"Convert a project path to Claude Code's session directory slug.\"\"\"
    import re as _re
    import shutil
    path = project_dir
    if shutil.which(\"cygpath\"):
        import subprocess
        try:
            path = subprocess.check_output(
                [\"cygpath\", \"-w\", path], text=True
            ).strip()
        except Exception:
            pass
    return _re.sub(r\"[^a-zA-Z0-9-]\", \"-\", path)


def _session_dir(project_dir: str) -> str:
    \"\"\"Convert a project directory path to its Claude sessions directory.\"\"\"
    return os.path.expanduser(
        \"~/.claude/projects/\" + _project_slug(project_dir)
    )'''

content = content.replace(old, new)

with open('$EXTRACT_PY', 'w') as f:
    f.write(content)
"
    echo "  Patched extract.py"
else
    echo "  extract.py already patched"
fi

echo ""
echo "Done. Test with: CLAUDE_PROJECT_DIR=\$PWD CLAUDE_PLUGIN_ROOT=$PLUGIN_DIR bash $PLUGIN_DIR/scripts/save-session.sh --dry"
