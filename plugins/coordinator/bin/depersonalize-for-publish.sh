#!/usr/bin/env bash
# depersonalize-for-publish.sh — scan or rewrite files to strip persona display
# names (the Staff Engineer, the Game Dev Reviewer, the Data Science Reviewer, Palí, the UX Reviewer, Zolí, the VP-Product Reviewer) and identity vocabulary
# (PM name forms, private GitHub org slugs) in favor of role labels and
# canonical public identifiers.
#
# Use case: percolating files from the meta-repo (`~/.claude/`) to the publish
# repo (`X:/coordinator-claude` or any open-source consumer mirror). Persona
# names and PM-identity strings live in the meta-repo where they were authored;
# the publish repo's canonical layer must ship nameless. This script is the
# meta-repo-side pre-percolation gate that pairs with
# `.github/scripts/check-persona-names.py` in the publish repo.
#
# Modes:
#   --check  PATH    scan files; print file:line:hit; exit 1 if any hit (default)
#   --fix    PATH    rewrite files in-place, substituting names per the
#                    vocabulary table below. Make a backup at PATH.bak first.
#
# PATH may be a single file or a directory (recursively walked for *.md, *.sh,
# *.py, *.json — same surface as the publish-repo check). Excluded: `archive/`,
# `tasks/`, `experiments/`, `evals/`, `docs/{plans,research,decisions,specs}/`.
#
# Vocabulary (matching docs/customization.md "Reviewer Roles" table):
#   the Staff Engineer                        → the Staff Engineer
#   Zolí                          → the Ambition Advocate
#   the VP-Product Reviewer                            → the VP-Product Reviewer
#   the Game Dev Reviewer                           → the Game Dev Reviewer
#   Palí                          → the Front-End Reviewer
#   the UX Reviewer                           → the UX Reviewer
#   the Data Science Reviewer                       → the Data Science Reviewer
#
# Identity vocabulary (PM name forms and private org slugs):
#   the Coordinator Authors        → the Coordinator Authors
#   the Coordinator Authors        → the Coordinator Authors  (ASCII variant)
#   the Coordinator Authors                → the Coordinator Authors
#   the PM                         → the PM  (defensive — stray first-name use)
#   dbc-oduffy/coordinator-claude   → dbc-oduffy/coordinator-claude
#   dbc-oduffy/deep-research-claude → dbc-oduffy/deep-research-claude
#
# --fix limitations:
#   - Substitution is a literal find/replace per name; no awareness of
#     possessives (the Staff Engineer's → the Staff Engineer's still works correctly
#     because only the name token is replaced).
#   - Sentence-initial capitalization handled (the Staff Engineer / "The Staff Engineer"
#     and lowercase mid-sentence both substitute to the same target).
#   - Historical attribution shorthand like "the Staff Engineer R1 F11" becomes
#     "the Staff Engineer R1 F11" — readable but verbose. Reviewer prefers
#     "Staff Engineer R1 F11" (drop article in attribution shorthand) — that's
#     a hand-edit after --fix if you want the tightest form.
#   - Identity substitutions are applied longest-first (compound forms before
#     bare first-name) to avoid partial matches turning "the Coordinator Authors"
#     into "the PM O'Duffy & Claude".
#
# Exit codes:
#   0 — clean (--check) or rewrite applied (--fix)
#   1 — hits found (--check) or rewrite error (--fix)
#   2 — usage error

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: depersonalize-for-publish.sh --check PATH
       depersonalize-for-publish.sh --fix PATH

  --check  Scan PATH (file or dir); print file:line:hit; exit 1 if any persona
           names or identity strings found. Default mode if --check / --fix omitted.
  --fix    Rewrite files in-place, substituting persona names and identity strings
           for role labels and canonical public identifiers.
           Backups written to <file>.bak before rewrite.

Surface: tracked-or-not *.md, *.sh, *.py, *.json files. Excluded subtree prefixes:
  archive/, tasks/, experiments/, evals/, docs/{plans,research,decisions,specs}/.

Persona vocabulary table:
  the Staff Engineer   → the Staff Engineer
  Zolí     → the Ambition Advocate
  the VP-Product Reviewer       → the VP-Product Reviewer
  the Game Dev Reviewer      → the Game Dev Reviewer
  Palí     → the Front-End Reviewer
  the UX Reviewer      → the UX Reviewer
  the Data Science Reviewer  → the Data Science Reviewer

Identity vocabulary table:
  the Coordinator Authors             → the Coordinator Authors
  the Coordinator Authors             → the Coordinator Authors
  the Coordinator Authors                     → the Coordinator Authors
  the PM                              → the PM
  dbc-oduffy/coordinator-claude   → dbc-oduffy/coordinator-claude
  dbc-oduffy/deep-research-claude → dbc-oduffy/deep-research-claude
EOF
}

if (( $# == 0 )); then
  usage >&2
  exit 2
fi

MODE="check"
TARGET=""
while (( $# > 0 )); do
  case "$1" in
    --check) MODE="check"; shift ;;
    --fix)   MODE="fix"; shift ;;
    -h|--help) usage; exit 0 ;;
    *)
      if [[ -z "$TARGET" ]]; then
        TARGET="$1"; shift
      else
        echo "Error: unexpected argument '$1'" >&2
        usage >&2
        exit 2
      fi
      ;;
  esac
done

if [[ -z "$TARGET" ]]; then
  echo "Error: PATH argument required." >&2
  usage >&2
  exit 2
fi

if [[ ! -e "$TARGET" ]]; then
  echo "Error: '$TARGET' does not exist." >&2
  exit 2
fi

# Substitution table — maps every token that must not appear in the publish tree
# to its canonical replacement. Persona names and identity vocabulary are both
# expressed here; the check pattern and fix loop are both derived from this
# single source of truth.
#
# ORDER MATTERS for fix: compound forms (e.g. "the Coordinator Authors") must
# be listed before their substrings (e.g. "the PM") to prevent partial-match
# clobbering. ORDERED_KEYS enforces this sequence at fix time.
declare -A NAME_TO_ROLE=(
  # Persona names (must match the publish-repo check-persona-names.py pattern)
  ["the Staff Engineer"]="the Staff Engineer"
  ["Zolí"]="the Ambition Advocate"
  ["the VP-Product Reviewer"]="the VP-Product Reviewer"
  ["the Game Dev Reviewer"]="the Game Dev Reviewer"
  ["Palí"]="the Front-End Reviewer"
  ["the UX Reviewer"]="the UX Reviewer"
  ["the Data Science Reviewer"]="the Data Science Reviewer"
  # Identity vocabulary — PM name forms (compound before bare)
  ["the Coordinator Authors"]="the Coordinator Authors"
  ["the Coordinator Authors"]="the Coordinator Authors"
  ["the Coordinator Authors"]="the Coordinator Authors"
  ["the PM"]="the PM"
  # Identity vocabulary — private org slugs
  ["dbc-oduffy/coordinator-claude"]="dbc-oduffy/coordinator-claude"
  ["dbc-oduffy/deep-research-claude"]="dbc-oduffy/deep-research-claude"
)

# Fix-application order: compound identity forms before their substrings,
# then persona names. Assoc array iteration order is undefined in bash, so we
# maintain an explicit ordered list here.
ORDERED_KEYS=(
  "the Coordinator Authors"
  "the Coordinator Authors"
  "the Coordinator Authors"
  "the PM"
  "dbc-oduffy/coordinator-claude"
  "dbc-oduffy/deep-research-claude"
  "the Staff Engineer"
  "Zolí"
  "the VP-Product Reviewer"
  "the Game Dev Reviewer"
  "Palí"
  "the UX Reviewer"
  "the Data Science Reviewer"
)

# Sentence-initial capitalization: "the Staff Engineer flagged..." at sentence start would
# substitute fine to "the Staff Engineer flagged..." (lowercase t), which is
# grammatically odd. We cannot detect sentence position reliably without an
# NLP pass; treat the literal substitution as authoritative and let the user
# correct sentence-initial cases by hand if they care. The publish-repo check
# treats both "the X" and "The X" as canonical, so consumers downstream are
# tolerant of either form.

EXCLUDED_PREFIXES=(
  "archive/" "tasks/" "experiments/" "evals/"
  "docs/plans/" "docs/research/" "docs/decisions/" "docs/specs/"
)

# Self-corruption guard: any file whose own content IS the substitution
# vocabulary (this script and the publish-repo's checker that mirrors the
# table) must be skipped, regardless of where it sits in the tree. Without
# this guard, --fix on a tree containing either rewrites the literal table
# entries themselves and breaks both tools. Discovered the hard way during
# 2026-05-09 publish-sanitization dogfood (bulk-fix on /x/coordinator-claude
# corrupted the publish-repo's check-persona-names.py PERSONA_NAMES list).
EXCLUDED_BASENAMES=( "depersonalize-for-publish.sh" "check-persona-names.py" )

is_excluded() {
  local rel="$1"
  local base; base="$(basename "$rel")"
  for b in "${EXCLUDED_BASENAMES[@]}"; do
    [[ "$base" == "$b" ]] && return 0
  done
  case "$base" in *check-persona*|*depersonalize*) return 0 ;; esac
  for pfx in "${EXCLUDED_PREFIXES[@]}"; do
    if [[ "$rel" == "$pfx"* ]]; then return 0; fi
  done
  return 1
}

# Build the list of candidate files.
declare -a FILES=()
if [[ -f "$TARGET" ]]; then
  FILES+=("$TARGET")
else
  while IFS= read -r -d '' f; do
    # Compute relative path from TARGET for exclusion check.
    rel="${f#"$TARGET"/}"
    if is_excluded "$rel"; then continue; fi
    FILES+=("$f")
  done < <(find "$TARGET" -type f \( -name '*.md' -o -name '*.sh' -o -name '*.py' -o -name '*.json' \) -print0)
fi

# Build a grep alternation pattern from all substitution keys.
# Identity tokens with slashes or special chars are matched as literals (no \b
# needed — slash is already a natural boundary). Persona names use \b word
# boundary. The pattern is a single alternation so one grep pass catches all.
PATTERN="("
for i in "${!ORDERED_KEYS[@]}"; do
  if (( i > 0 )); then PATTERN+="|"; fi
  # Escape regex metacharacters in the key for literal matching.
  escaped_key=$(printf '%s' "${ORDERED_KEYS[$i]}" | sed 's/[.+*?^${}()|[\]\\]/\\&/g; s/'"'"'/['"'"']/g')
  PATTERN+="${escaped_key}"
done
PATTERN+=")"

if [[ "$MODE" == "check" ]]; then
  hits=0
  for f in "${FILES[@]}"; do
    # grep -nE gives POSIX extended regex; -H prepends filename. (Was -P, but
    # macOS BSD grep lacks -P, which made --check silently pass. PATTERN is
    # built from literal-escaped keys joined by | — pure ERE, no PCRE features
    # required.)
    if grep -nHE "$PATTERN" "$f" 2>/dev/null; then
      hits=$((hits + 1))
    fi
  done

  if (( hits > 0 )); then
    echo ""
    echo "depersonalize-for-publish: $hits file(s) carry persona names or identity strings."
    echo "  Run with --fix to rewrite, or hand-edit using the vocabulary table:"
    for name in "${ORDERED_KEYS[@]}"; do
      printf "    %-40s → %s\n" "$name" "${NAME_TO_ROLE[$name]}"
    done
    exit 1
  fi

  echo "depersonalize-for-publish: clean (${#FILES[@]} file(s) scanned)."
  exit 0
fi

# --fix mode
fixed=0
for f in "${FILES[@]}"; do
  # Quick check first; skip files with no hits.
  if ! grep -qP "$PATTERN" "$f" 2>/dev/null; then continue; fi

  cp -p "$f" "${f}.bak"
  for name in "${ORDERED_KEYS[@]}"; do
    role="${NAME_TO_ROLE[$name]}"
    # Use perl for in-place edit with literal-quote support (handles diacritics,
    # slashes in org slugs, and single quotes in names). Key and role are passed
    # via env vars to avoid delimiter conflicts (e.g. "dbc-oduffy/coordinator-claude"
    # contains "/" which would terminate a s/…/…/g literal delimiter) and
    # single-quote escaping issues in "the Coordinator Authors".
    # Three substitution branches:
    #   1. Slash-bearing keys (org slugs): plain s// — slash is a natural boundary.
    #   2. Non-ASCII keys (diacritic names like Palí, Zolí): plain s// without \b.
    #      quotemeta() escapes non-ASCII chars (e.g. í → \í), breaking the match
    #      under -CS; and Perl's \b treats non-ASCII letters as non-\w, so the
    #      word-boundary anchor also fails at the diacritic position. Diacritic
    #      names are not substrings of any ASCII word, so \b guards are unnecessary.
    #   3. ASCII keys: \b...\b word boundaries so short tokens ("fru", "sid") do
    #      not match inside unrelated words ("fruit", "aside"). Only ASCII
    #      metacharacters are escaped (not non-ASCII chars) to keep the pattern valid.
    DEPERSONALIZE_KEY="${name}" DEPERSONALIZE_ROLE="${role}" \
      perl -CS -i -pe '
        my $k = $ENV{DEPERSONALIZE_KEY};
        # Escape only ASCII regex metacharacters (not non-ASCII, which quotemeta
        # would over-escape and break under -CS Unicode mode).
        $k =~ s/([.+*?^\${}()|])/\\$1/g;
        if ($ENV{DEPERSONALIZE_KEY} =~ m{/}) {
          s/$k/$ENV{DEPERSONALIZE_ROLE}/g;
        } elsif ($ENV{DEPERSONALIZE_KEY} =~ /[^\x00-\x7F]/) {
          s/$k/$ENV{DEPERSONALIZE_ROLE}/g;
        } else {
          s/\b$k\b/$ENV{DEPERSONALIZE_ROLE}/g;
        }
      ' "$f"
  done
  # Post-pass cleanups:
  # 1. "the X" / "the X" → collapse to a single article. Fires when the
  #    input had "the Staff Engineer" (capitalized article, sentence-initial) and the
  #    role substitution introduced its own "the".
  # 2. Sentence-initial lowercase "the X" after substitution should be "The X" —
  #    detect by ". The Staff Engineer" (period-space-the-Cap), "! the X",
  #    "? the X", and the file-/line-start position. We only handle the
  #    period-space and start-of-line cases; mid-paragraph fixes stay literal.
  perl -CS -i -pe '
    s/\b(?:[Tt]he) (the) /\1 /g;                                  # the X / the X → the X
    s/^the (Staff Engineer|Ambition Advocate|VP-Product Reviewer|Game Dev Reviewer|Front-End Reviewer|UX Reviewer|Data Science Reviewer)\b/The \1/g;  # line-start
    s/(\. |\? |\! )the (Staff Engineer|Ambition Advocate|VP-Product Reviewer|Game Dev Reviewer|Front-End Reviewer|UX Reviewer|Data Science Reviewer)\b/\1The \2/g;  # sentence-initial
  ' "$f"
  fixed=$((fixed + 1))
  echo "rewrote: $f (backup: ${f}.bak)"
done

if (( fixed == 0 )); then
  echo "depersonalize-for-publish: no files needed rewriting."
else
  echo ""
  echo "depersonalize-for-publish: rewrote $fixed file(s). Review diffs:"
  echo "  for f in ${TARGET}/**/*.bak; do diff \"\$f\" \"\${f%.bak}\"; done"
  echo "  (or use git diff if files are tracked)"
fi
exit 0
