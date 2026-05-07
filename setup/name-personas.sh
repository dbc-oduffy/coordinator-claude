#!/usr/bin/env bash
# name-personas.sh — Bind user-chosen names to role-distinct reviewer personae.
#
# The publish repo ships nameless: reviewers are referred to by articulated role
# labels ("the Staff Engineer", "the Game Dev Reviewer", etc.). Some installers
# find names easier to think with. This one-shot binding script substitutes the
# articulated role-label sentinels in installed-copy prose for user-supplied names.
#
# This is NOT a renaming utility — it is a naming utility, run once per role.
# To switch from one chosen name to another, re-clone the install or edit the
# files manually; this script is not idempotent across multiple runs.
#
# What gets touched:
#   - Articulated role-label sentinel (e.g., "the Staff Engineer") in prose,
#     in any *.md or *.sh file under plugins/, plus docs/customization.md.
#   - YAML frontmatter is skipped.
#
# What is NOT touched:
#   - Agent filenames (staff-eng.md, staff-game-dev.md, etc.) — infrastructure.
#   - YAML name: fields — infrastructure.
#   - subagent_type: dispatch keys (coordinator:staff-eng, etc.) — infrastructure.
#   - Unarticulated forms like "a staff engineer" in generic prose — collision-safe.
#
# Usage: name-personas.sh [--dry-run] ROLE NAME [ROLE NAME ...]
# Example:
#   name-personas.sh "the Staff Engineer" "Patrik" "the Game Dev Reviewer" "Sid"

set -euo pipefail

# bash 4.0+ required (associative arrays). macOS default bash is 3.2 — error
# clearly with install guidance.
if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: this script requires bash 4.0 or later (associative arrays)." >&2
  echo "  Detected: bash ${BASH_VERSION}" >&2
  echo "  macOS users: install a newer bash via 'brew install bash' and re-run with" >&2
  echo "  /opt/homebrew/bin/bash $(basename "$0") ..." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Known roles (articulated form — the leading article is the sentinel that
# distinguishes role references from generic prose like "a staff engineer
# with exacting standards"). Slug column is reference only; not modified.
#
# Articulated role label    | Subagent slug                  | Plugin
# the Staff Engineer        | coordinator:staff-eng          | coordinator
# the Ambition Advocate     | coordinator:ambition-advocate  | coordinator
# the VP-Product Reviewer   | coordinator:vp-product         | coordinator
# the Game Dev Reviewer     | game-dev:staff-game-dev        | game-dev
# the Front-End Reviewer    | web-dev:senior-front-end       | web-dev
# the UX Reviewer           | web-dev:staff-ux               | web-dev
# the Data Science Reviewer | data-science:staff-data-sci    | data-science
# ---------------------------------------------------------------------------
KNOWN_ROLES=(
  "the Staff Engineer"
  "the Ambition Advocate"
  "the VP-Product Reviewer"
  "the Game Dev Reviewer"
  "the Front-End Reviewer"
  "the UX Reviewer"
  "the Data Science Reviewer"
)

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGINS_DIR="$REPO_ROOT/plugins"

# ---------------------------------------------------------------------------
# Slug derivation: lowercase + strip combining diacritics. Preserved from
# rename-personas.sh in case downstream tooling wants to inspect a slug
# derived from the user's chosen name (e.g., for an optional display_name:
# frontmatter field). Not used for canonical substitution.
# ---------------------------------------------------------------------------
to_slug() {
  printf '%s' "$1" | perl -CS -MUnicode::Normalize -ne '
    print lc(NFC(NFD($_) =~ s/\p{M}//gr))
  '
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=true
  shift
fi

if (( $# % 2 != 0 )); then
  echo "Error: arguments after [--dry-run] must be ROLE NAME pairs." >&2
  echo "Usage: $(basename "$0") [--dry-run] ROLE NAME [ROLE NAME ...]" >&2
  echo "Example: $(basename "$0") \"the Staff Engineer\" \"Patrik\" \"the Game Dev Reviewer\" \"Sid\"" >&2
  exit 1
fi

if (( $# == 0 )); then
  echo "Error: no ROLE NAME pairs provided." >&2
  echo "Known roles:" >&2
  for r in "${KNOWN_ROLES[@]}"; do echo "  $r" >&2; done
  exit 1
fi

declare -a ROLES=()
declare -a NAMES=()
declare -a NEW_SLUGS=()
while (( $# > 0 )); do
  role="$1"; name="$2"; shift 2
  ROLES+=("$role")
  NAMES+=("$name")
  NEW_SLUGS+=("$(to_slug "$name")")
  # Validate: ROLE must be a known articulated role label
  known=false
  for r in "${KNOWN_ROLES[@]}"; do
    [[ "$r" == "$role" ]] && known=true && break
  done
  if ! $known; then
    echo "Error: '$role' is not a known role label." >&2
    echo "Use one of:" >&2
    for r in "${KNOWN_ROLES[@]}"; do echo "  $r" >&2; done
    exit 1
  fi
done

# Show binding plan. Each ROLE expands into two substitution targets — the
# lowercase ("the Staff Engineer", mid-sentence) and capitalized ("The Staff
# Engineer", sentence-initial) forms. Both map to the same NAME.
declare -a SUB_OLDS=()
declare -a SUB_NEWS=()
for i in "${!ROLES[@]}"; do
  role="${ROLES[$i]}"
  name="${NAMES[$i]}"
  SUB_OLDS+=("$role")
  SUB_NEWS+=("$name")
  if [[ "${role:0:4}" == "the " ]]; then
    SUB_OLDS+=("The ${role:4}")
    SUB_NEWS+=("$name")
  fi
done

echo "Naming plan:"
for i in "${!ROLES[@]}"; do
  echo "  ${ROLES[$i]} → ${NAMES[$i]} (slug: ${NEW_SLUGS[$i]})"
done
echo "  (sentence-initial capitalization handled automatically: 'The Staff Engineer' as well as 'the Staff Engineer')"
echo ""

# ---------------------------------------------------------------------------
# Collect target files (canonical layer: plugins + docs/customization.md)
# ---------------------------------------------------------------------------
FILES=()
while IFS= read -r -d '' f; do
  FILES+=("$f")
done < <(find "$PLUGINS_DIR" \( -name "*.md" -o -name "*.sh" \) -print0)
[[ -f "$REPO_ROOT/docs/customization.md" ]] && FILES+=("$REPO_ROOT/docs/customization.md")

# ---------------------------------------------------------------------------
# Collision audit (per plan F4): warn the user if unarticulated forms of the
# role labels appear in body prose. The articulated form is the locked
# sentinel — unarticulated occurrences will not be substituted, which is
# usually correct ("a staff engineer with exacting standards" should not be
# renamed). This advisory tells the user what's intentionally being skipped.
# ---------------------------------------------------------------------------
for i in "${!ROLES[@]}"; do
  role="${ROLES[$i]}"
  if [[ "${role:0:4}" != "the " ]]; then
    continue
  fi
  unarticulated="${role:4}"
  found_files=()
  for file in "${FILES[@]}"; do
    if perl -0777 -ne "
      my \$body;
      if (/\A---\r?\n.*?\r?\n---\r?\n(.*)/s) { \$body = \$1; }
      else { \$body = \$_; }
      exit 1 unless \$body =~ /\b\Q$unarticulated\E\b/;
    " "$file" 2>/dev/null; then
      found_files+=("$file")
    fi
  done
  if (( ${#found_files[@]} > 0 )); then
    echo "Note: '$unarticulated' (unarticulated form of '$role') appears in ${#found_files[@]} file(s)."
    echo "  These will NOT be substituted — only the articulated form is replaced."
    echo "  This is usually correct (generic prose like 'a staff engineer' should not be renamed)."
    echo ""
  fi
done

# ---------------------------------------------------------------------------
# Frontmatter-safe replacement (carried from rename-personas.sh).
# ---------------------------------------------------------------------------
replace_in_prose() {
  local old="$1" new="$2" file="$3"
  perl -0777 -i.bak -pe "
    if (/\A---\r?\n(.*?\r?\n)---\r?\n(.*)/s) {
      my (\$fm, \$body) = (\$1, \$2);
      \$body =~ s/\Q$old\E/$new/g;
      \$_ = \"---\\n\$fm---\\n\$body\";
    } else {
      s/\Q$old\E/$new/g;
    }
  " "$file"
}

count_prose_matches() {
  local old="$1" file="$2"
  perl -0777 -ne "
    my \$count = 0;
    if (/\A---\r?\n(.*?\r?\n)---\r?\n(.*)/s) {
      my \$body = \$2;
      \$count++ while \$body =~ /\Q$old\E/g;
    } else {
      \$count++ while /\Q$old\E/g;
    }
    print \$count;
  " "$file"
}

# ---------------------------------------------------------------------------
# Dry-run: report counts, no modifications
# ---------------------------------------------------------------------------
if $DRY_RUN; then
  echo "Dry-run mode — no files will be modified."
  echo ""
  for i in "${!SUB_OLDS[@]}"; do
    old="${SUB_OLDS[$i]}"; new="${SUB_NEWS[$i]}"
    total_replacements=0; total_files=0
    for file in "${FILES[@]}"; do
      count="$(count_prose_matches "$old" "$file")"
      if (( count > 0 )); then
        echo "  [${old} → ${new}] $file: $count match(es)"
        (( total_replacements += count )) || true
        (( total_files += 1 )) || true
      fi
    done
    echo "  ${old} → ${new}: $total_replacements replacement(s) across $total_files file(s)"
    echo ""
  done
  exit 0
fi

# ---------------------------------------------------------------------------
# Live run: apply substitutions and report
# ---------------------------------------------------------------------------
declare -A PAIR_REPLACEMENTS=()
declare -A PAIR_FILES=()
for i in "${!SUB_OLDS[@]}"; do
  PAIR_REPLACEMENTS["${SUB_OLDS[$i]}"]=0
  PAIR_FILES["${SUB_OLDS[$i]}"]=0
done

total_files_modified=0

for file in "${FILES[@]}"; do
  file_modified=false
  for i in "${!SUB_OLDS[@]}"; do
    old="${SUB_OLDS[$i]}"; new="${SUB_NEWS[$i]}"
    count="$(count_prose_matches "$old" "$file")"
    if (( count > 0 )); then
      replace_in_prose "$old" "$new" "$file"
      PAIR_REPLACEMENTS["$old"]=$(( PAIR_REPLACEMENTS["$old"] + count ))
      PAIR_FILES["$old"]=$(( PAIR_FILES["$old"] + 1 ))
      file_modified=true
    fi
  done
  if $file_modified; then
    (( total_files_modified += 1 )) || true
  fi
done

echo "Persona names bound:"
for i in "${!SUB_OLDS[@]}"; do
  old="${SUB_OLDS[$i]}"; new="${SUB_NEWS[$i]}"
  echo "  ${old} → ${new}: ${PAIR_REPLACEMENTS[$old]} substitutions across ${PAIR_FILES[$old]} files"
done
echo ""
echo "Total files modified: $total_files_modified"
echo ""
echo "Infrastructure unchanged: agent filenames (staff-eng.md, etc.), YAML name: fields,"
echo "and subagent_type dispatch keys are role-based and not affected by naming."
