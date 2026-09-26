
from __future__ import annotations

SETUP_TEMPLATE_FILES: list[str] = [
    "publish_sync.py",
    ".percolate-identity.example",
]

# Subset of SETUP_TEMPLATE_FILES that must be marked executable at the destination.
# publish.sh (the former sole entry here, invoked DIRECTLY at the destination) was
# current SETUP_TEMPLATE_FILES entry needs the exec flag delivered — do NOT re-add
SETUP_TEMPLATE_EXEC_FILES: list[str] = []

SETUP_TEMPLATE_HOOK_FILES: list[str] = [
    "percolate-hooks/README.md",
    "percolate-hooks/percolate-store.yaml",
    "percolate-hooks/coordinator-claude/pre-ci/.gitkeep",
    "percolate-hooks/coordinator-claude/pre-rsync/.gitkeep",
    "percolate-hooks/coordinator-claude-toplevel-wiki/post-rsync/publish-native-allowlist.txt",
]
