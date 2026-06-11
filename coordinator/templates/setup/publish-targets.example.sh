#!/bin/bash
# publish-targets.example.sh — Example target registry for publish.sh (percolation / push-to-publish-repo)
#
# Copy this file to publish-targets.sh and adjust paths for your machine.
# publish-targets.sh is gitignored (machine-specific paths).
#
# NOTE: This file is the legacy fallback. The preferred source for
# publish.sh's target list is the machine-local registry key `publish.targets`
# (see ~/.claude/machine-local/README.md and the registry.toml.example
# alongside it). When `publish.targets` is set there, publish-targets.sh is
# ignored; this file remains supported for back-compat.
#
# ---------------------------------------------------------------------------
# Tuple format
# ---------------------------------------------------------------------------
# Each TARGETS entry is a pipe-separated tuple. Two shapes are supported:
#
#   Legacy 4-field:   "name|mode|source|path"
#   Extended 5-field: "name|mode|source|path|native_slugs"
#
#   name:         identifier used in CLI (bash publish.sh <name>)
#   mode:         "mirror" (copy + delete per plugin), "flat-mirror"
#                 (copy + delete at top level, no subdirs), or "manifest"
#                 (selective copy driven by publish-manifest.txt)
#   source:       absolute path to the source plugin directory
#   path:         absolute path to the target's plugin directory
#   native_slugs: (optional, 5-field only) comma-separated list of
#                 marketplace slugs that are EXPECTED in this target's
#                 content. The personal-data audit treats these as
#                 expected matches instead of REVIEW hits. Use for
#                 publish targets whose published content naturally
#                 mentions another marketplace identity (e.g. a target
#                 that ships a marketplace-flavored plugin where the
#                 marketplace slug is part of the public identity).
#
# ---------------------------------------------------------------------------
# Per-operator identity tokens — .percolate-identity
# ---------------------------------------------------------------------------
# publish.sh's personal-data audit pulls operator-specific tokens (your name,
# org slug, working-branch prefix, machine codename) from
# ~/.claude/setup/.percolate-identity, which is also gitignored. Copy
# .percolate-identity.example to .percolate-identity and populate it before
# running publish.sh against your downstream repos. See the example file for
# field documentation.
#
# Without a .percolate-identity, publish.sh's audit still catches generic
# leakage (your $HOME path, the drive letter your install lives on) but does
# not know your name or org slug.
# ---------------------------------------------------------------------------

TARGETS=(
  # 4-field shape (no per-target native-slug allowlist):
  "coordinator-claude|mirror|/path/to/source/plugins/coordinator-claude|/path/to/coordinator-claude/plugins"
  "deep-research-claude|manifest|/path/to/source/plugins/coordinator-claude/deep-research|/path/to/deep-research-claude"

  # 5-field shape (with native_slugs — comma-separated marketplace slugs
  # expected to appear in this target's content):
  "example-target|manifest|/path/to/source/plugins/example-plugin|/path/to/example-publish-repo|your-marketplace-slug"

  # publish-repo content targets (flat-mirror, no native_slugs):
  # flat-mirror at publish repo root pulls top-level files from dist/publish-repo-toplevel/;
  # flat-mirror at publish repo's setup/ subdir pulls scripts from dist/publish-repo-setup/;
  # flat-mirror at publish repo's docs/ subdir pulls top-level docs from dist/publish-repo-docs/.
  # All rely on sync_flat_mirror's iterdir-based file scan (publish_sync.py:207-251) —
  # directories at the dest are protected; only top-level files participate. The docs/ target
  # carries a substantial .percolate-ignore (large for a single-file target): it controls only the files Claude Central authors
  # (today: agent-install.md) and protects every other top-level docs/*.md from delete-not-in-source.
  # "coordinator-claude-publish-repo-toplevel|flat-mirror|/path/to/plugins/coordinator/dist/publish-repo-toplevel|/path/to/coordinator-claude"
  # "coordinator-claude-publish-repo-setup|flat-mirror|/path/to/plugins/coordinator/dist/publish-repo-setup|/path/to/coordinator-claude/setup"
  # "coordinator-claude-publish-repo-docs|flat-mirror|/path/to/plugins/coordinator/dist/publish-repo-docs|/path/to/coordinator-claude/docs"
)
