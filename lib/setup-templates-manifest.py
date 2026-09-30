
from __future__ import annotations

SETUP_TEMPLATE_FILES: list[str] = [
    "publish_sync.py",
    ".percolate-identity.example",
]

# Subset of SETUP_TEMPLATE_FILES that must be marked executable at the destination.
#
# publish.sh (the former sole entry here, invoked DIRECTLY at the destination) was
# retired in the percolate bash->Python port (chunk C-W4a,
# docs/plans/2026-07-21-percolate-python-port.md) — the entrypoint is now
# coordinator/bin/publish.py, resolved live from the plugin source tree via
# --plugin-dir (this repo's source_is_live convention), not copied into
# ~/.claude/setup/. publish_sync.py remains here but is never executed directly
# (called as `python publish_sync.py` by the retired publish.sh's successor tooling);
# the .example files are copy-templates that are sourced or copied, not run. No
# current SETUP_TEMPLATE_FILES entry needs the exec flag delivered — do NOT re-add
# publish.sh or widen this list without re-establishing a directly-invoked
# destination entrypoint first.
SETUP_TEMPLATE_EXEC_FILES: list[str] = []

SETUP_TEMPLATE_HOOK_FILES: list[str] = [
    "percolate-hooks/README.md",
    "percolate-hooks/percolate-store.yaml",
    "percolate-hooks/coordinator-claude/pre-ci/.gitkeep",
    "percolate-hooks/coordinator-claude/pre-rsync/.gitkeep",
    "percolate-hooks/coordinator-claude-toplevel-wiki/post-rsync/publish-native-allowlist.txt",
]
