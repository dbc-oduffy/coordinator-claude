"""
setup-templates-manifest.py — single source of truth for the ~/.claude/setup/
percolation file list.

Imported (never executed) by:
  - coordinator/dist/publish-repo-setup/install.sh :: deliver_setup_templates()
    (a Python polyglot trampoline despite its .sh name — bash-to-Python port,
    2026-07-17)

The consumer copies these files from <plugin>/coordinator/templates/setup/
into ~/.claude/setup/. Edit this list HERE and nowhere else; the parity test
coordinator/tests/install/test_setup_templates_manifest_sync.py fails the
build if any consumer reintroduces a divergent inline copy.

Spec backlink: archive/specs/2026-05-27-cqcs-cluster7-lib-consolidation.md

Negative spec: do NOT add machine-local/, bin/ resolver, or claude-home
files here — those have their own delivery loops in install-substrate
(Steps 2, 3) and are deliberately out of this manifest's scope.
"""

from __future__ import annotations

# Files copied into ~/.claude/setup/, preserving any subpath given here.
# NOT flat — nested entries (lib/*.sh) are permitted and consumers MUST create
# the destination parent dir before copying.
SETUP_TEMPLATE_FILES: list[str] = [
    "publish_sync.py",
    ".percolate-identity.example",
]
# publish-targets.example.sh was removed here and deleted from disk (2026-07-22
# bash-kill campaign) — it was inert documentation-by-example, never sourced or
# executed; coordinator/lib/percolate/targets.py:158 reads a user's own
# publish-targets.sh by regex-extracting the bash TARGETS=( ... ) array as text,
# never running it. The expected shape now lives as a comment next to that
# parser instead of in a dead shell file nobody executes.
# test-publish-allowlist-builder.sh was removed here (review: code-reviewer — the
# function it tested, _build_allowlisted_source, no longer exists in bash; it was
# ported to coordinator/lib/percolate/allowlist.py's build_allowlisted_source,
# which already has pytest coverage under coordinator/tests/. The template
# hard-depended on the retired publish.sh and failed on every fresh install.

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

# Files copied into the ~/.claude/setup/percolate-hooks/ subdirectory.
# (Separate list — different destination shape, never executable.)
SETUP_TEMPLATE_HOOK_FILES: list[str] = [
    "percolate-hooks/README.md",
    "percolate-hooks/percolate-store.yaml",
    "percolate-hooks/coordinator-claude/pre-ci/.gitkeep",
    "percolate-hooks/coordinator-claude/pre-rsync/.gitkeep",
    "percolate-hooks/coordinator-claude-toplevel-wiki/post-rsync/publish-native-allowlist.txt",
]
