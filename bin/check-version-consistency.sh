#!/usr/bin/env bash
# check-version-consistency.sh — assert the coordinator-claude version surfaces agree.
#
# Purpose (RAG-bait): the coordinator-claude release has FOUR independent version
# surfaces — the plugin manifest, the marketplace catalog manifest, the CHANGELOG,
# and the git tag. They drifted apart historically (plugin.json 2.7.1 / marketplace
# 2.1.1 / CHANGELOG 2.8.1 on 2026-06-22) because the cut ceremony only stamped the
# CHANGELOG and nothing asserted cross-surface agreement. This gate is that
# assertion. It is the mechanical enforcer of docs/wiki/versioning-convention.md.
#
# Invariant (steady-state, holds BETWEEN releases too):
#   plugin.json .version
#     == marketplace.json .metadata.version
#     == latest *released* CHANGELOG `## [X.Y.Z]` section (Unreleased is skipped)
#   [advisory, with --check-tag] == latest `v*` git tag
#
# SSOT is plugin.json's version — every other surface tracks it. See the
# convention doc for which number ships and how a bump moves all surfaces together.
#
# Layout-agnostic: resolves every path RELATIVE TO marketplace.json, so it runs
# unchanged in the meta-repo source layout (plugins/coordinator-claude/...) and in
# the flat OSS publish-repo layout (repo root). Auto-discovers the bundle root.
#
# Usage:
#   check-version-consistency.sh [--root <dir>] [--check-tag] [--quiet]
#   --root <dir>   bundle root containing .claude-plugin/marketplace.json
#                  (default: auto-discover from cwd / git root)
#   --check-tag    additionally compare the latest v* git tag (advisory: a
#                  mismatch WARNs, does not fail — source_is_live repos never tag)
#   --quiet        suppress the OK line (failures always print)
#
# Exit: 0 = all surfaces agree; 1 = mismatch (or a required surface missing/unparseable).
#
# Portability: bash >=4 + BSD/GNU coreutils (DR-148). No jq — versions are
# extracted with portable sed, matching check_marketplace_version_regression in
# setup/lib/percolate-gate.sh.

set -uo pipefail

CHECK_TAG=0
QUIET=0
ROOT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root) ROOT="${2:-}"; shift 2 ;;
    --check-tag) CHECK_TAG=1; shift ;;
    --quiet) QUIET=1; shift ;;
    -h|--help) sed -n '2,33p' "$0"; exit 0 ;;
    *) echo "check-version-consistency: unknown arg '$1'" >&2; exit 2 ;;
  esac
done

fail() { echo "check-version-consistency: $*" >&2; exit 1; }

# --- Locate the bundle root (the dir whose .claude-plugin/marketplace.json governs). ---
discover_root() {
  # 1. Explicit --root.
  if [[ -n "$ROOT" ]]; then
    [[ -f "$ROOT/.claude-plugin/marketplace.json" ]] || fail "no .claude-plugin/marketplace.json under --root '$ROOT'"
    printf '%s\n' "$ROOT"; return 0
  fi
  # 2. Flat publish-repo layout: marketplace.json at git root.
  local git_root
  git_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
  if [[ -n "$git_root" && -f "$git_root/.claude-plugin/marketplace.json" ]]; then
    printf '%s\n' "$git_root"; return 0
  fi
  # 3. Meta-repo source layout: the bundle lives under plugins/coordinator-claude/.
  if [[ -n "$git_root" && -f "$git_root/plugins/coordinator-claude/.claude-plugin/marketplace.json" ]]; then
    printf '%s\n' "$git_root/plugins/coordinator-claude"; return 0
  fi
  # 4. cwd fallback — require BOTH anchor files so an unrelated dir that merely
  #    contains a marketplace.json can't be mistaken for the coordinator bundle
  #    (code-reviewer F3).
  if [[ -f ".claude-plugin/marketplace.json" && -f "coordinator/.claude-plugin/plugin.json" ]]; then
    printf '%s\n' "$PWD"; return 0
  fi
  fail "could not locate .claude-plugin/marketplace.json (pass --root)"
}

BUNDLE_ROOT="$(discover_root)"
MARKETPLACE="$BUNDLE_ROOT/.claude-plugin/marketplace.json"
# plugin.json sits beside marketplace.json in the flat publish/source layout
# (v3), or one level down under coordinator/ in the older nested meta-repo
# layout. Prefer the flat sibling; fall back to the nested path.
if [[ -f "$BUNDLE_ROOT/.claude-plugin/plugin.json" ]]; then
  PLUGIN_JSON="$BUNDLE_ROOT/.claude-plugin/plugin.json"
else
  PLUGIN_JSON="$BUNDLE_ROOT/coordinator/.claude-plugin/plugin.json"
fi

# CHANGELOG lives at the bundle root in the flat publish layout, under
# dist/publish-repo-toplevel/ in the flat v3 source layout, or under
# coordinator/dist/publish-repo-toplevel/ in the older nested meta-repo layout.
CHANGELOG=""
if [[ -f "$BUNDLE_ROOT/CHANGELOG.md" ]]; then
  CHANGELOG="$BUNDLE_ROOT/CHANGELOG.md"
elif [[ -f "$BUNDLE_ROOT/dist/publish-repo-toplevel/CHANGELOG.md" ]]; then
  CHANGELOG="$BUNDLE_ROOT/dist/publish-repo-toplevel/CHANGELOG.md"
elif [[ -f "$BUNDLE_ROOT/coordinator/dist/publish-repo-toplevel/CHANGELOG.md" ]]; then
  CHANGELOG="$BUNDLE_ROOT/coordinator/dist/publish-repo-toplevel/CHANGELOG.md"
else
  fail "no CHANGELOG.md found (looked at bundle root, dist/publish-repo-toplevel/, and coordinator/dist/publish-repo-toplevel/)"
fi

[[ -f "$PLUGIN_JSON" ]] || fail "missing plugin manifest: $PLUGIN_JSON"

# --- Extract each surface's version (portable, no jq). ---
# First "version": "X.Y.Z" in the given file. plugin.json has exactly one.
extract_json_version() { sed -n 's/[[:space:]]*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$1" | head -1; }

PLUGIN_VER="$(extract_json_version "$PLUGIN_JSON")"
[[ -n "$PLUGIN_VER" ]] || fail "could not parse version from $PLUGIN_JSON"

# marketplace.json: the metadata.version specifically — NOT a plugin entry's.
# Plugin entries today carry no "version" key, but rather than bank on that
# schema invariant forever (code-reviewer F1), scope the match to the metadata
# object by deleting everything from the "plugins": array onward before
# extracting. This stays correct if a plugin entry ever gains a version field.
MARKET_VER="$(sed '/^[[:space:]]*"plugins"[[:space:]]*:/,$d' "$MARKETPLACE" | extract_json_version /dev/stdin)"
[[ -n "$MARKET_VER" ]] || fail "could not parse metadata.version from $MARKETPLACE (no \"version\" key before the \"plugins\" array)"

# CHANGELOG: first `## [X.Y.Z]` header that is NOT [Unreleased].
CHANGELOG_VER="$(sed -n 's/^## \[\([0-9][0-9.]*\)\].*/\1/p' "$CHANGELOG" | head -1)"
[[ -n "$CHANGELOG_VER" ]] || fail "no released '## [X.Y.Z]' section found in $CHANGELOG"

# --- The invariant. ---
MISMATCH=0
if [[ "$PLUGIN_VER" != "$MARKET_VER" ]]; then MISMATCH=1; fi
if [[ "$PLUGIN_VER" != "$CHANGELOG_VER" ]]; then MISMATCH=1; fi

if [[ "$MISMATCH" -eq 1 ]]; then
  {
    echo "check-version-consistency: VERSION SURFACES DISAGREE"
    echo "  plugin.json      : $PLUGIN_VER   ($PLUGIN_JSON)"
    echo "  marketplace.json : $MARKET_VER   ($MARKETPLACE)"
    echo "  CHANGELOG (latest): $CHANGELOG_VER   ($CHANGELOG)"
    echo ""
    echo "  SSOT is plugin.json. Bump every surface together — see"
    echo "  docs/wiki/versioning-convention.md. At a release cut, stamping"
    echo "  CHANGELOG [Unreleased] -> [X.Y.Z] MUST also set plugin.json and"
    echo "  marketplace.json metadata.version to X.Y.Z in the same commit."
  } >&2
  exit 1
fi

# --- Advisory git-tag check (opt-in; never fails the gate). ---
if [[ "$CHECK_TAG" -eq 1 ]]; then
  # --sort=-v:refname requires git >=2.0; 2>/dev/null silently skips on older
  # installs (advisory path — acceptable, no gate failure). (code-reviewer F5)
  LATEST_TAG="$(git -C "$BUNDLE_ROOT" tag --list 'v*' --sort=-v:refname 2>/dev/null | head -1)"
  if [[ -n "$LATEST_TAG" ]]; then
    TAG_VER="${LATEST_TAG#v}"
    if [[ "$TAG_VER" != "$PLUGIN_VER" ]]; then
      echo "check-version-consistency: NOTE — latest git tag $LATEST_TAG != plugin.json $PLUGIN_VER (advisory; expected if this release is not yet tagged)" >&2
    fi
  fi
fi

[[ "$QUIET" -eq 1 ]] || echo "check-version-consistency: OK — all surfaces at $PLUGIN_VER"
exit 0
