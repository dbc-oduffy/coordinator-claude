# depersonalize-identity.sh — per-operator identity-rewrite pairs for
# publish-time-transform.sh.
#
# Copy this file to `depersonalize-identity.sh` (no `.example` suffix) in the
# same directory and edit with your own values. The sibling script will source
# it automatically if present.
#
# See ~/.claude/plugins/coordinator-claude/coordinator/docs/wiki/percolate-setup.md
#
# GitHub org-slug rewrites: private-org/repo → public-org/repo (or whatever
# rewrite shape your workflow needs). Entries declared here are appended to the
# script's NAME_TO_ROLE + ORDERED_KEYS at script-load time.
#
# Format:
#   - Declare entries in the OPERATOR_NAME_TO_ROLE associative array.
#   - List the keys (in desired iteration order — longest/most-specific first
#     if any key is a substring of another) in OPERATOR_ORDERED_KEYS.

declare -A OPERATOR_NAME_TO_ROLE=(
    # ["private-org/repo-name"]="public-org/repo-name"
    # ["acme-internal/foo"]="acme-public/foo"
)

OPERATOR_ORDERED_KEYS=(
    # "private-org/repo-name"
    # "acme-internal/foo"
)
