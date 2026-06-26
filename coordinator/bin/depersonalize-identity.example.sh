# depersonalize-identity.sh — per-operator identity-rewrite pairs for
# publish-time-transform.sh.
#
# Copy this file to `depersonalize-identity.sh` (no `.example` suffix) in the
# same directory and edit with your own values. The sibling script will source
# it automatically if present.
#
# See ~/.claude/plugins/coordinator-claude/coordinator/docs/wiki/percolate-setup.md
#
# Entries declared here are appended to the script's NAME_TO_ROLE + ORDERED_KEYS
# at script-load time.
#
# THREE CLASSES of operator-private token require substitution entries here:
#
#   1. Private company org / GitHub org slug → public-facing name
#      Any private org that appears in file paths, comments, or import strings
#      must be rewritten to a neutral synthetic value before OSS publish.
#
#   2. Private repo / project codename → synthetic OSS-safe placeholder
#      Internal project codenames that appear in docstrings or comments must
#      be rewritten so the OSS publish tree contains no disclosure.
#
#   3. Machine slugs → role-name (machine-a / machine-b / …)
#      Machine hostnames that appear in docstrings (e.g., branch examples,
#      machine-local path examples) must be rewritten before OSS publish.
#      Use a consistent convention: first machine = machine-a, second = machine-b, etc.
#
# Format:
#   - Declare entries in the OPERATOR_NAME_TO_ROLE associative array.
#   - List the keys in OPERATOR_ORDERED_KEYS in LONGEST-FIRST order so a key
#     that is a substring of another is iterated AFTER the longer key
#     (prevents partial clobbering mid-pass).

declare -A OPERATOR_NAME_TO_ROLE=(
    # Class 1 — private company org → public-facing name
    # ["acme-internal"]="acme-public"

    # Class 2 — private repo/project codename → synthetic placeholder
    # ["secret-project"]="example-repo"

    # Class 3 — machine slugs → role-name convention
    # ["myhost"]="machine-x"
    # ["myother-host"]="machine-y"
)

OPERATOR_ORDERED_KEYS=(
    # Longest/most-specific keys first — see note above.
    # "acme-internal"
    # "secret-project"
    # "myother-host"
    # "myhost"
)
