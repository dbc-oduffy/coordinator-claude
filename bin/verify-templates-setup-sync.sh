#!/usr/bin/env bash
# verify-templates-setup-sync.sh — Check byte-identity between live ~/.claude/setup helpers
# and their coordinator/templates/setup/ mirrors. Inspect-only: report drift, exit non-zero.
#
# Usage:
#   verify-templates-setup-sync.sh          Diff each pair; report mismatches; exit non-zero on any mismatch.
#
# There is no --fix. Recovery is manual and template-as-authoritative: templates ship the
# reviewed, plugin-published source; if live drifted, restore it by hand with
#   cp coordinator/templates/setup/<file> ~/.claude/setup/<file>
# (Prior versions of this script offered a live→template --fix path; it was removed —
# no automated caller ever invoked it, and an inspect-only tool cannot silently overwrite
# the plugin's shipped source with an operator's local edits. See F4,
# docs/plans/2026-05-21-generic-percolation-via-coordinator-install.md.)
#
# Pairs verified:
#   ~/.claude/setup/publish.sh                                                          ↔  coordinator/templates/setup/publish.sh
#   ~/.claude/setup/publish_sync.py                                                     ↔  coordinator/templates/setup/publish_sync.py
#   ~/.claude/setup/publish-targets.example.sh                                          ↔  coordinator/templates/setup/publish-targets.example.sh
#   ~/.claude/setup/.percolate-identity.example                                         ↔  coordinator/templates/setup/.percolate-identity.example
#   ~/.claude/setup/percolate-hooks/README.md                                           ↔  coordinator/templates/setup/percolate-hooks/README.md
#   ~/.claude/setup/percolate-hooks/_lib/depersonalize-bin-resolve.sh                   ↔  coordinator/templates/setup/percolate-hooks/_lib/depersonalize-bin-resolve.sh
#   ~/.claude/setup/percolate-hooks/coordinator-claude/post-rsync/10-transform.sh                    ↔  coordinator/templates/setup/percolate-hooks/coordinator-claude/post-rsync/10-transform.sh
#   ~/.claude/setup/percolate-hooks/coordinator-claude-publish-repo-docs/post-rsync/10-transform.sh   ↔  coordinator/templates/setup/percolate-hooks/coordinator-claude-publish-repo-docs/post-rsync/10-transform.sh
#   ~/.claude/setup/percolate-hooks/coordinator-claude-publish-repo-setup/post-rsync/10-transform.sh  ↔  coordinator/templates/setup/percolate-hooks/coordinator-claude-publish-repo-setup/post-rsync/10-transform.sh
#   ~/.claude/setup/percolate-hooks/coordinator-claude-publish-repo-toplevel/post-rsync/10-transform.sh ↔ coordinator/templates/setup/percolate-hooks/coordinator-claude-publish-repo-toplevel/post-rsync/10-transform.sh
#   ~/.claude/setup/percolate-hooks/coordinator-claude-toplevel-wiki/post-rsync/20-transform.sh       ↔  coordinator/templates/setup/percolate-hooks/coordinator-claude-toplevel-wiki/post-rsync/20-transform.sh
#   ~/.claude/setup/percolate-hooks/coordinator-claude-toplevel-install/post-rsync/10-transform.sh    ↔  coordinator/templates/setup/percolate-hooks/coordinator-claude-toplevel-install/post-rsync/10-transform.sh
#
# When neither file in a pair exists yet, the pair is skipped (exit 0 with a message).
# This graceful-no-files behaviour matches the no-consumer pattern in other verify-*-sync.sh
# scripts: the verifier is authored before the files it will eventually verify.
#
# Spec backlink: docs/plans/2026-05-21-generic-percolation-via-coordinator-install.md § Step 3

set -euo pipefail

# Resolve plugin root: from env var, or relative to this script's location.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
    PLUGIN_ROOT="$CLAUDE_PLUGIN_ROOT"
else
    PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

CLAUDE_HOME="${CLAUDE_HOME:-$HOME}/.claude"
TEMPLATES_SETUP="$PLUGIN_ROOT/templates/setup"
LIVE_SETUP="$CLAUDE_HOME/setup"

# No --fix mode: this script is inspect-only. An arg is accepted but not actioned as a
# copy trigger — warn if one is passed so a stale caller doesn't silently no-op.
if [ "${1:-}" != "" ]; then
    echo "WARNING: verify-templates-setup-sync.sh takes no flags (--fix was removed; inspect-only now)." >&2
    echo "         Manual recovery is template-as-authoritative: cp coordinator/templates/setup/<file> ~/.claude/setup/<file>" >&2
fi

# Pairs: "live_name template_name" (relative filenames; both dirs rooted above)
PAIRS=(
    "publish.sh publish.sh"
    "publish_sync.py publish_sync.py"
    "publish-targets.example.sh publish-targets.example.sh"
    ".percolate-identity.example .percolate-identity.example"
    "percolate-hooks/README.md percolate-hooks/README.md"
    "percolate-hooks/_lib/depersonalize-bin-resolve.sh percolate-hooks/_lib/depersonalize-bin-resolve.sh"
    "percolate-hooks/coordinator-claude/post-rsync/10-transform.sh percolate-hooks/coordinator-claude/post-rsync/10-transform.sh"
    "percolate-hooks/coordinator-claude-publish-repo-docs/post-rsync/10-transform.sh percolate-hooks/coordinator-claude-publish-repo-docs/post-rsync/10-transform.sh"
    "percolate-hooks/coordinator-claude-publish-repo-setup/post-rsync/10-transform.sh percolate-hooks/coordinator-claude-publish-repo-setup/post-rsync/10-transform.sh"
    "percolate-hooks/coordinator-claude-publish-repo-toplevel/post-rsync/10-transform.sh percolate-hooks/coordinator-claude-publish-repo-toplevel/post-rsync/10-transform.sh"
    "percolate-hooks/coordinator-claude-toplevel-wiki/post-rsync/20-transform.sh percolate-hooks/coordinator-claude-toplevel-wiki/post-rsync/20-transform.sh"
    "percolate-hooks/coordinator-claude-toplevel-install/post-rsync/10-transform.sh percolate-hooks/coordinator-claude-toplevel-install/post-rsync/10-transform.sh"
)

EXIT_CODE=0
ANY_CHECKED=0

for pair in "${PAIRS[@]}"; do
    live_name="${pair%% *}"
    tmpl_name="${pair##* }"
    live_path="$LIVE_SETUP/$live_name"
    tmpl_path="$TEMPLATES_SETUP/$tmpl_name"

    live_exists=0
    tmpl_exists=0
    [ -f "$live_path" ] && live_exists=1
    [ -f "$tmpl_path" ] && tmpl_exists=1

    if [ "$live_exists" -eq 0 ] && [ "$tmpl_exists" -eq 0 ]; then
        # Neither side exists yet — graceful skip.
        echo "NOT_PRESENT  $live_name (neither live nor template exists yet — Step 1 will create them)"
        continue
    fi

    if [ "$live_exists" -eq 0 ]; then
        echo "LIVE_MISSING $live_name (template exists but live copy absent at $live_path)"
        EXIT_CODE=1
        continue
    fi

    if [ "$tmpl_exists" -eq 0 ]; then
        echo "TMPL_MISSING $live_name (live exists but template absent at $tmpl_path)"
        EXIT_CODE=1
        continue
    fi

    ANY_CHECKED=1

    # Both exist — diff for byte identity.
    if diff -q "$live_path" "$tmpl_path" >/dev/null 2>&1; then
        echo "OK           $live_name"
    else
        echo "MISMATCH     $live_name"
        EXIT_CODE=1
    fi
done

if [ "$ANY_CHECKED" -eq 0 ] && [ "$EXIT_CODE" -eq 0 ]; then
    echo "no files present — nothing to verify (Step 1 will create the live and template copies)"
fi

exit $EXIT_CODE
