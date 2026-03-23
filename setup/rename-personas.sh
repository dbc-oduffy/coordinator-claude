#!/usr/bin/env bash
# rename-personas.sh — Renames persona display names AND invocation slugs
# across plugin prose files. Skips YAML frontmatter and filenames.
# Safe for multi-byte names (Zolí, Palí).
#
# For each OLD → NEW pair, the script replaces:
#   1. Display name in prose (e.g., "Patrik" → "Alex")
#   2. Invocation slug (e.g., "patrik" → "alex" in --members, mapping tables,
#      position filenames, active_reviewers lists)
#
# Slugs are auto-derived: lowercase + strip accents (Zolí → zoli, Palí → pali).
# Agent filenames and name: frontmatter fields (staff-eng, staff-game-dev, etc.)
# are infrastructure — they are NOT touched by this script.
#
# Usage: rename-personas.sh [--dry-run] OLD NEW [OLD NEW ...]
# Example: rename-personas.sh Patrik "Alex" Zolí "Jordan"

set -euo pipefail

# ---------------------------------------------------------------------------
# Persona registry
# Display Name | Slug    | Plugin        | Agent File
# Patrik       | patrik  | coordinator   | agents/staff-eng.md
# Zolí         | zoli    | coordinator   | agents/ambition-advocate.md
# Sid          | sid     | game-dev      | agents/staff-game-dev.md
# Palí         | pali    | web-dev       | agents/senior-front-end.md
# Fru          | fru     | web-dev       | agents/staff-ux.md
# Camelia      | camelia | data-science  | agents/staff-data-sci.md
# ---------------------------------------------------------------------------
KNOWN_PERSONAS=("Patrik" "Zolí" "Sid" "Palí" "Fru" "Camelia")

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGINS_DIR="$REPO_ROOT/plugins"

# ---------------------------------------------------------------------------
# Slug derivation: lowercase + strip combining diacritics.
# Zolí → zoli, Palí → pali, Patrik → patrik
# Uses perl for portable Unicode normalization (NFD → strip \p{M} → NFC).
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
  echo "Error: arguments after [--dry-run] must be OLD NEW pairs." >&2
  echo "Usage: $(basename "$0") [--dry-run] OLD NEW [OLD NEW ...]" >&2
  exit 1
fi

if (( $# == 0 )); then
  echo "Error: no OLD NEW pairs provided." >&2
  exit 1
fi

declare -a OLDS=()
declare -a NEWS=()
declare -a OLD_SLUGS=()
declare -a NEW_SLUGS=()
while (( $# > 0 )); do
  old="$1"; new="$2"; shift 2
  OLDS+=("$old")
  NEWS+=("$new")
  OLD_SLUGS+=("$(to_slug "$old")")
  NEW_SLUGS+=("$(to_slug "$new")")
  # Warn if OLD is not a known persona
  known=false
  for p in "${KNOWN_PERSONAS[@]}"; do
    [[ "$p" == "$old" ]] && known=true && break
  done
  if ! $known; then
    echo "Warning: '$old' is not a known persona name (proceeding anyway)." >&2
  fi
done

# Show slug derivations
echo "Rename plan:"
for i in "${!OLDS[@]}"; do
  echo "  Display: ${OLDS[$i]} → ${NEWS[$i]}"
  echo "  Slug:    ${OLD_SLUGS[$i]} → ${NEW_SLUGS[$i]}"
done
echo ""

# ---------------------------------------------------------------------------
# Frontmatter-safe replacement using perl with full Unicode support.
# Rewrites the file in-place; only touches the body, not the YAML frontmatter.
# Handles both LF and CRLF line endings (common on Windows/Git Bash).
# ---------------------------------------------------------------------------
replace_in_prose() {
  local old="$1" new="$2" file="$3"
  # -0777 slurps whole file; -i -pe enables in-place edit with implicit $_ loop.
  # No -CSD: byte-mode matching is correct here — shell expands $old as UTF-8 bytes,
  # and file bytes are also UTF-8. -CSD causes mismatch with multi-byte characters.
  perl -0777 -i -pe "
    if (/\A---\r?\n(.*?\r?\n)---\r?\n(.*)/s) {
      my (\$fm, \$body) = (\$1, \$2);
      \$body =~ s/\Q$old\E/$new/g;
      \$_ = \"---\\n\$fm---\\n\$body\";
    } else {
      s/\Q$old\E/$new/g;
    }
  " "$file"
}

# Count prose occurrences (respecting frontmatter) without modifying the file.
count_prose_matches() {
  local old="$1" file="$2"
  # -0777 slurps whole file; -ne enables implicit $_ loop required for slurping.
  # No -CSD: same rationale as replace_in_prose.
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
# Collect target files
# ---------------------------------------------------------------------------
mapfile -d '' FILES < <(find "$PLUGINS_DIR" \( -name "*.md" -o -name "*.sh" \) -print0)
# Also include docs/customization.md if it exists
[[ -f "$REPO_ROOT/docs/customization.md" ]] && FILES+=("$REPO_ROOT/docs/customization.md")

# ---------------------------------------------------------------------------
# Build replacement pairs: display names + slugs (skip if slug == display)
# ---------------------------------------------------------------------------
declare -a ALL_OLDS=()
declare -a ALL_NEWS=()
for i in "${!OLDS[@]}"; do
  ALL_OLDS+=("${OLDS[$i]}")
  ALL_NEWS+=("${NEWS[$i]}")
  # Add slug pair only if it differs from the display name pair
  if [[ "${OLD_SLUGS[$i]}" != "${OLDS[$i]}" ]] || [[ "${NEW_SLUGS[$i]}" != "${NEWS[$i]}" ]]; then
    ALL_OLDS+=("${OLD_SLUGS[$i]}")
    ALL_NEWS+=("${NEW_SLUGS[$i]}")
  fi
done

# ---------------------------------------------------------------------------
# Dry-run: report counts, no modifications
# ---------------------------------------------------------------------------
if $DRY_RUN; then
  echo "Dry-run mode — no files will be modified."
  echo ""
  for i in "${!ALL_OLDS[@]}"; do
    old="${ALL_OLDS[$i]}"; new="${ALL_NEWS[$i]}"
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
# Live run: apply replacements and report summary
# ---------------------------------------------------------------------------
declare -A PAIR_REPLACEMENTS=()
declare -A PAIR_FILES=()
for i in "${!ALL_OLDS[@]}"; do
  PAIR_REPLACEMENTS["${ALL_OLDS[$i]}"]=0
  PAIR_FILES["${ALL_OLDS[$i]}"]=0
done

total_files_modified=0

for file in "${FILES[@]}"; do
  file_modified=false
  for i in "${!ALL_OLDS[@]}"; do
    old="${ALL_OLDS[$i]}"; new="${ALL_NEWS[$i]}"
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

echo "Persona renames applied:"
for i in "${!ALL_OLDS[@]}"; do
  old="${ALL_OLDS[$i]}"; new="${ALL_NEWS[$i]}"
  echo "  ${old} → ${new}: ${PAIR_REPLACEMENTS[$old]} replacements across ${PAIR_FILES[$old]} files"
done
echo ""
echo "Total files modified: $total_files_modified"
echo ""
echo "Infrastructure unchanged: agent filenames (staff-eng.md, etc.), name: fields,"
echo "and subagent_type keys are role-based and not affected by persona renames."
