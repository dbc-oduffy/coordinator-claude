#!/usr/bin/env bash
# setup-templates-manifest.sh — single source of truth for the ~/.claude/setup/
# percolation file list.
#
# Sourced (never executed) by:
#   - lib/install-substrate.sh        (coordinator /setup Phase 3, Step 3d)
#   - dist/publish-repo-setup/install.sh :: deliver_setup_templates()
#
# Both consumers copy these files from <plugin>/coordinator/templates/setup/
# into ~/.claude/setup/. Edit this list HERE and nowhere else; the parity test
# tests/install/test_setup_templates_manifest_sync.py fails the build if any
# consumer reintroduces a divergent inline copy.
#
# Spec backlink: archive/specs/2026-05-27-cqcs-cluster7-lib-consolidation.md
#
# Negative spec: do NOT add machine-local/, bin/ resolver, or claude-home
# files here — those have their own delivery loops in install-substrate.sh
# (Steps 2, 3) and are deliberately out of this manifest's scope.

# Top-level files copied flat into ~/.claude/setup/.
SETUP_TEMPLATE_FILES=(
  publish.sh
  publish_sync.py
  publish-targets.example.sh
  .percolate-identity.example
)

# Subset of SETUP_TEMPLATE_FILES that must be marked executable at the destination.
# WHY only publish.sh, despite all four sources being +x on disk (and publish_sync.py
# + the .example files carrying shebangs): only publish.sh is invoked DIRECTLY at the
# destination. publish_sync.py is called as `python publish_sync.py` by publish.sh
# (never executed directly), and the .example files are copy-templates that are sourced
# or copied, not run. So despite their source +x bits and shebangs, only publish.sh is a
# directly-invoked entrypoint and only it needs the exec flag delivered. Do NOT "fix" this
# by adding publish_sync.py — the delivered-permission surface is deliberately narrower
# than the source-permission surface.
SETUP_TEMPLATE_EXEC_FILES=(
  publish.sh
)

# Files copied into the ~/.claude/setup/percolate-hooks/ subdirectory.
# (Separate array — different destination shape, never executable.)
SETUP_TEMPLATE_HOOK_FILES=(
  percolate-hooks/README.md
)
