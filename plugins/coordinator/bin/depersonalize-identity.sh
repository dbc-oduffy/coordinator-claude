# depersonalize-identity.sh — per-operator identity-rewrite pairs for
# depersonalize-for-publish.sh. Sourced automatically if present in the same
# directory as the script.
#
# Authored 2026-05-21: PM's existing org-slug rewrites carried over from the
# static NAME_TO_ROLE + ORDERED_KEYS tables (regression-net for percolation).
# See `depersonalize-identity.example.sh` for shape documentation.

declare -A OPERATOR_NAME_TO_ROLE=(
    ["oduffy-delphi/coordinator-claude"]="dbc-oduffy/coordinator-claude"
    ["oduffy-delphi/deep-research-claude"]="dbc-oduffy/deep-research-claude"
)

OPERATOR_ORDERED_KEYS=(
    "oduffy-delphi/coordinator-claude"
    "oduffy-delphi/deep-research-claude"
)
