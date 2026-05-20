#!/usr/bin/env bash
# depersonalize-for-publish.sh — scan or rewrite files to normalize meta-repo
# content for publish: strip persona display names, rewrite dev-tree plugin
# paths to publish-tree form, substitute identity vocabulary.
#
# Use case: percolating files from the meta-repo (`~/.claude/`) to the publish
# repo (`X:/coordinator-claude` or any open-source consumer mirror). Persona
# names and PM-identity strings live in the meta-repo where they were authored;
# the publish repo's canonical layer must ship nameless. Dev-tree plugin paths
# (`plugins/coordinator-claude/<plugin>/`) must be rewritten to publish-tree
# form (`plugins/<plugin>/`) because the `coordinator-claude/` middle segment is
# stripped at percolate time. This script is the meta-repo-side pre-percolation
# gate that pairs with `.github/scripts/check-persona-names.py` in the publish
# repo.
#
# Spec backlink: docs/plans/2026-05-18-publish-time-path-rewriting.md
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
#   Patrik                        → the Staff Engineer
#   Zolí                          → the Director of Engineering
#   YK                            → the VP-Product Reviewer
#   Sid                           → the Game Dev Reviewer
#   Palí                          → the Front-End Reviewer
#   Fru                           → the UX Reviewer
#   Camelia                       → the Data Science Reviewer
#
# Identity vocabulary (PM name forms and private org slugs):
#   Dónal O'Duffy & Claude        → the Coordinator Authors
#   Donal O'Duffy & Claude        → the Coordinator Authors  (ASCII variant)
#   Donal + Claude                → the Coordinator Authors
#   Dónal                         → the PM  (defensive — stray first-name use)
#   oduffy-delphi/coordinator-claude   → dbc-oduffy/coordinator-claude
#   oduffy-delphi/deep-research-claude → dbc-oduffy/deep-research-claude
#
# Path mapping (dev-tree → publish-tree):
#   plugins/coordinator-claude/coordinator/ → plugins/coordinator/  (two-segment collapse, applied first)
#   plugins/coordinator-claude/data-science/ → plugins/data-science/
#   plugins/coordinator-claude/deep-research/ → plugins/deep-research/
#   plugins/coordinator-claude/game-dev/ → plugins/game-dev/
#   plugins/coordinator-claude/web-dev/ → plugins/web-dev/
#   plugins/coordinator-claude/<discovered>/ → plugins/<discovered>/  (additional plugins found under $TARGET/plugins/)
#
# --fix limitations:
#   - Substitution is a literal find/replace per name; no awareness of
#     possessives (Patrik's → the Staff Engineer's still works correctly
#     because only the name token is replaced).
#   - Sentence-initial capitalization handled (Patrik / "The Staff Engineer"
#     and lowercase mid-sentence both substitute to the same target).
#   - Historical attribution shorthand like "Patrik R1 F11" becomes
#     "the Staff Engineer R1 F11" — readable but verbose. Reviewer prefers
#     "Staff Engineer R1 F11" (drop article in attribution shorthand) — that's
#     a hand-edit after --fix if you want the tightest form.
#   - Identity substitutions are applied longest-first (compound forms before
#     bare first-name) to avoid partial matches turning "Dónal O'Duffy & Claude"
#     into "the PM O'Duffy & Claude".
#   - Path rewrites run BEFORE persona substitution (structural-first).
#
# Exit codes:
#   0 — clean (--check) or rewrite applied (--fix)
#   1 — hits found (--check) or rewrite error (--fix)
#   2 — usage error
#   3 — state/environment fault (self-corruption detected — restore from source)

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: depersonalize-for-publish.sh --check PATH
       depersonalize-for-publish.sh --fix PATH

  --check  Scan PATH (file or dir); print file:line:hit; exit 1 if any persona
           names, identity strings, or dev-tree plugin paths found. Default mode
           if --check / --fix omitted.
  --fix    Rewrite files in-place, substituting persona names and identity strings
           for role labels and canonical public identifiers, and rewriting dev-tree
           plugin paths to publish-tree form.
           Backups written to <file>.bak before rewrite.
           Path rewrite runs BEFORE persona substitution (structural-first).

Surface: tracked-or-not *.md, *.sh, *.py, *.json files. Excluded subtree prefixes:
  archive/, tasks/, experiments/, evals/, docs/{plans,research,decisions,specs}/.

Path-mapping table (static floor — always applied):
  plugins/coordinator-claude/coordinator/ → plugins/coordinator/
  plugins/coordinator-claude/data-science/ → plugins/data-science/
  plugins/coordinator-claude/deep-research/ → plugins/deep-research/
  plugins/coordinator-claude/game-dev/ → plugins/game-dev/
  plugins/coordinator-claude/web-dev/ → plugins/web-dev/
  plugins/coordinator-claude/<discovered>/ → plugins/<discovered>/  (additional plugins found at $TARGET/plugins/)

Persona vocabulary table:
  Patrik   → the Staff Engineer
  Zolí     → the Director of Engineering
  YK       → the VP-Product Reviewer
  Sid      → the Game Dev Reviewer
  Palí     → the Front-End Reviewer
  Fru      → the UX Reviewer
  Camelia  → the Data Science Reviewer

Identity vocabulary table:
  Dónal O'Duffy & Claude             → the Coordinator Authors
  Donal O'Duffy & Claude             → the Coordinator Authors
  Donal + Claude                     → the Coordinator Authors
  Dónal                              → the PM
  oduffy-delphi/coordinator-claude   → dbc-oduffy/coordinator-claude
  oduffy-delphi/deep-research-claude → dbc-oduffy/deep-research-claude
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
# ORDER MATTERS for fix: compound forms (e.g. "Dónal O'Duffy & Claude") must
# be listed before their substrings (e.g. "Dónal") to prevent partial-match
# clobbering. ORDERED_KEYS enforces this sequence at fix time.
declare -A NAME_TO_ROLE=(
  # Persona names (must match the publish-repo check-persona-names.py pattern)
  ["Patrik"]="the Staff Engineer"
  ["Zolí"]="the Director of Engineering"
  ["YK"]="the VP-Product Reviewer"
  ["Sid"]="the Game Dev Reviewer"
  ["Palí"]="the Front-End Reviewer"
  ["Fru"]="the UX Reviewer"
  ["Camelia"]="the Data Science Reviewer"
  # Identity vocabulary — PM name forms (compound before bare)
  ["Dónal O'Duffy & Claude"]="the Coordinator Authors"
  ["Donal O'Duffy & Claude"]="the Coordinator Authors"
  ["Donal + Claude"]="the Coordinator Authors"
  ["Dónal"]="the PM"
  # Identity vocabulary — private org slugs
  ["oduffy-delphi/coordinator-claude"]="dbc-oduffy/coordinator-claude"
  ["oduffy-delphi/deep-research-claude"]="dbc-oduffy/deep-research-claude"
)

# Fix-application order: compound identity forms before their substrings,
# then persona names. Assoc array iteration order is undefined in bash, so we
# maintain an explicit ordered list here.
ORDERED_KEYS=(
  "Dónal O'Duffy & Claude"
  "Donal O'Duffy & Claude"
  "Donal + Claude"
  "Dónal"
  "oduffy-delphi/coordinator-claude"
  "oduffy-delphi/deep-research-claude"
  "Patrik"
  "Zolí"
  "YK"
  "Sid"
  "Palí"
  "Fru"
  "Camelia"
)

# Self-protection: if this script's own ORDERED_KEYS look already-substituted
# (every key starts with "the " or "dbc-"), a past run depersonalized our own
# substitution map. Subsequent --fix sweeps would be no-ops and silently lie
# about it. Refuse to run; instruct the operator to restore from source.
# Tripped previously: dest's depersonalize.sh had ORDERED_KEYS = ("the Coordinator
# Authors", "the Staff Engineer", ...) — repaired 2026-05-17 by copying source.
self_corrupted=true
for k in "${ORDERED_KEYS[@]}"; do
  if [[ "$k" != "the "* && "$k" != "dbc-"* ]]; then
    self_corrupted=false
    break
  fi
done
if [[ "$self_corrupted" == "true" ]]; then
  echo "depersonalize-for-publish: FATAL — ORDERED_KEYS look already-substituted." >&2
  echo "  This script's substitution map has been corrupted by a past depersonalize run." >&2
  echo "  Restore from the meta-repo source:" >&2
  echo "    cp \$HOME/.claude/plugins/coordinator-claude/coordinator/bin/depersonalize-for-publish.sh \\" >&2
  echo "       \$(realpath \"\$0\")" >&2
  # Review: code-reviewer — exit 2 is usage error; self-corruption is a state/environment fault.
  exit 3
fi

# ---------------------------------------------------------------------------
# Path-rewrite static seed — the floor applied regardless of discovery results.
# Order: longest/most-specific first (coordinator two-segment collapse before
# bare plugin-name mappings). SOURCE patterns contain "plugins/coordinator-claude/"
# which is the canonical dev-tree prefix; DEST patterns are publish-tree form.
#
# Self-validation guard (parallel to ORDERED_KEYS guard above): if every source
# in the static seed already starts with "plugins/" and does NOT contain
# "coordinator-claude", the map has been replaced by publish-form keys — this
# script was already depersonalized and its path-rewrite map is now wrong.
# Refuse to run; instruct restore from source.
# ---------------------------------------------------------------------------
PATH_REWRITE_SOURCES=(
  "plugins/coordinator-claude/coordinator/"
  "plugins/coordinator-claude/data-science/"
  "plugins/coordinator-claude/deep-research/"
  "plugins/coordinator-claude/game-dev/"
  "plugins/coordinator-claude/web-dev/"
)
PATH_REWRITE_DESTS=(
  "plugins/coordinator/"
  "plugins/data-science/"
  "plugins/deep-research/"
  "plugins/game-dev/"
  "plugins/web-dev/"
)

# Self-validation guard for the path-rewrite seed.
path_map_corrupted=true
for src in "${PATH_REWRITE_SOURCES[@]}"; do
  if [[ "$src" == "plugins/coordinator-claude/"* ]]; then
    path_map_corrupted=false
    break
  fi
done
if [[ "$path_map_corrupted" == "true" ]]; then
  echo "depersonalize-for-publish: FATAL — PATH_REWRITE_SOURCES look already-substituted." >&2
  echo "  The path-rewrite seed no longer contains 'coordinator-claude' in any source pattern." >&2
  echo "  This script's path-rewrite map has been corrupted by a past depersonalize run." >&2
  echo "  Restore from the meta-repo source:" >&2
  echo "    cp \$HOME/.claude/plugins/coordinator-claude/coordinator/bin/depersonalize-for-publish.sh \\" >&2
  echo "       \$(realpath \"\$0\")" >&2
  # Review: code-reviewer — exit 2 is usage error; self-corruption is a state/environment fault.
  exit 3
fi

# Sentence-initial capitalization: "Patrik flagged..." at sentence start would
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

# ---------------------------------------------------------------------------
# Discovery: if TARGET is a directory with a plugins/ subdirectory, enumerate
# plugins not already in the static seed and append to the rewrite arrays.
# If plugins/ exists but is empty, emit a non-fatal warning and proceed with
# the static 5 floor only.
# ---------------------------------------------------------------------------
# Build a set of already-seeded plugin names for fast membership test.
declare -A _SEEDED_PLUGINS=(
  ["coordinator"]=1
  ["data-science"]=1
  ["deep-research"]=1
  ["game-dev"]=1
  ["web-dev"]=1
)

if [[ -d "$TARGET" && -d "$TARGET/plugins" ]]; then
  # Review: code-reviewer — old discovered_count counted ALL dirs including the 5 seeded ones,
  # so WARNING only fired when plugins/ was completely empty — never when only the floor existed.
  # Renamed to new_plugin_count and incremented only inside the non-seeded guard so the WARNING
  # fires when no plugins beyond the static floor were found, which is the meaningful signal.
  new_plugin_count=0
  while IFS= read -r -d '' plugin_dir; do
    plugin_name="$(basename "$plugin_dir")"
    if [[ -z "${_SEEDED_PLUGINS[$plugin_name]+_}" ]]; then
      new_plugin_count=$((new_plugin_count + 1))
      PATH_REWRITE_SOURCES+=("plugins/coordinator-claude/${plugin_name}/")
      PATH_REWRITE_DESTS+=("plugins/${plugin_name}/")
    fi
  done < <(find "$TARGET/plugins" -mindepth 1 -maxdepth 1 -type d -print0)
  if (( new_plugin_count == 0 )); then
    echo "depersonalize-for-publish: WARNING — $TARGET/plugins/ exists but no plugins beyond the static floor were discovered; only the 5 floor mappings will be applied." >&2
  fi
fi

# ---------------------------------------------------------------------------
# rewrite_plugin_paths: apply PATH_REWRITE_SOURCES → PATH_REWRITE_DESTS across
# FILES. Uses perl env-var injection (matching the existing slash-bearing-key
# pattern below) to handle '/' in source and dest patterns without delimiter
# conflicts. Returns the count of files modified.
# ---------------------------------------------------------------------------
rewrite_plugin_paths() {
  local path_fixed=0
  local n="${#PATH_REWRITE_SOURCES[@]}"
  for f in "${FILES[@]}"; do
    # Quick check: does this file contain any dev-tree plugin path prefix?
    if ! grep -qF "plugins/coordinator-claude/" "$f" 2>/dev/null; then continue; fi
    for (( i=0; i<n; i++ )); do
      local src="${PATH_REWRITE_SOURCES[$i]}"
      local dst="${PATH_REWRITE_DESTS[$i]}"
      # Pass src/dst via env vars to avoid delimiter conflicts with '/' in the
      # pattern. Use quotemeta on the source to escape regex metacharacters.
      DEPERSONALIZE_PATH_SRC="$src" DEPERSONALIZE_PATH_DST="$dst" \
        perl -CS -i -pe '
          my $s = $ENV{DEPERSONALIZE_PATH_SRC};
          # Escape ASCII regex metacharacters for literal matching.
          # Review: code-reviewer — [ and ] omitted; unescaped [ causes fatal perl parse error
          # if any future source key contains a bracket. Add both to the escape set.
          $s =~ s/([.+*?^\${}()|[\]])/\\$1/g;
          s/$s/$ENV{DEPERSONALIZE_PATH_DST}/g;
        ' "$f"
    done
    path_fixed=$((path_fixed + 1))
  done
  echo "$path_fixed"
}

# Build a grep alternation pattern from all substitution keys.
# Identity tokens with slashes or special chars are matched as literals (no \b
# needed — slash is already a natural boundary). Persona names use \b word
# boundary. The pattern is a single alternation so one grep pass catches all.
# Also includes the dev-tree plugin path prefix for --check mode detection.
PATTERN="(plugins/coordinator-claude/"
for i in "${!ORDERED_KEYS[@]}"; do
  PATTERN+="|"
  # Escape regex metacharacters in the key for literal matching.
  # Review: code-reviewer — the previous sed apostrophe workaround produced ['] in the ERE
  # (a single-char class) rather than a bare apostrophe, making debug output confusing.
  # Switch to perl env-var injection to produce a literal apostrophe in PATTERN.
  escaped_key=$(DEPERSONALIZE_ESC_KEY="${ORDERED_KEYS[$i]}" perl -e '
    my $k = $ENV{DEPERSONALIZE_ESC_KEY};
    $k =~ s/([.+*?^\${}()|[\]\\])/\\$1/g;
    print $k;
  ')
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
    echo "depersonalize-for-publish: $hits file(s) carry persona names, identity strings, or dev-tree plugin paths."
    echo "  Run with --fix to rewrite, or hand-edit using the vocabulary table:"
    for name in "${ORDERED_KEYS[@]}"; do
      printf "    %-40s → %s\n" "$name" "${NAME_TO_ROLE[$name]}"
    done
    echo "  Path mappings (static floor):"
    for (( i=0; i<${#PATH_REWRITE_SOURCES[@]}; i++ )); do
      printf "    %-50s → %s\n" "${PATH_REWRITE_SOURCES[$i]}" "${PATH_REWRITE_DESTS[$i]}"
    done
    exit 1
  fi

  echo "depersonalize-for-publish: clean (${#FILES[@]} file(s) scanned)."
  exit 0
fi

# --fix mode
# Path rewrite runs BEFORE persona substitution — structural transforms first,
# naming transforms second. This matches the script's existing compound-before-
# substring ordering precedent and ensures a path like
# "plugins/coordinator-claude/coordinator/agents/Patrik.md" is rewritten to
# "plugins/coordinator/agents/the Staff Engineer.md" in the correct order.
path_fixed_count="$(rewrite_plugin_paths)"
if (( path_fixed_count > 0 )); then
  echo "path-rewrote: $path_fixed_count file(s) (dev-tree plugin paths → publish-tree form)"
fi

fixed=0
for f in "${FILES[@]}"; do
  # Quick check first; skip files with no hits.
  # Review: code-reviewer — grep -qP is PCRE-only; macOS BSD grep lacks -P and silently passes,
  # making --fix a no-op on macOS. Use -qE to match the check-mode grep at line 395.
  if ! grep -qE "$PATTERN" "$f" 2>/dev/null; then continue; fi

  cp -p "$f" "${f}.bak"
  for name in "${ORDERED_KEYS[@]}"; do
    role="${NAME_TO_ROLE[$name]}"
    # Use perl for in-place edit with literal-quote support (handles diacritics,
    # slashes in org slugs, and single quotes in names). Key and role are passed
    # via env vars to avoid delimiter conflicts (e.g. "dbc-oduffy/coordinator-claude"
    # contains "/" which would terminate a s/…/…/g literal delimiter) and
    # single-quote escaping issues in "Dónal O'Duffy & Claude".
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
        # Review: code-reviewer — [ and ] omitted; unescaped [ causes fatal perl parse error
        # if any future identity key contains a bracket. Add both to the escape set.
        $k =~ s/([.+*?^\${}()|[\]])/\\$1/g;
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
  # 1. "The the X" / "the the X" → collapse to a single article. Fires when the
  #    input had "The Patrik" (capitalized article, sentence-initial) and the
  #    role substitution introduced its own "the".
  # 2. Sentence-initial lowercase "the X" after substitution should be "The X" —
  #    detect by ". the Staff Engineer" (period-space-the-Cap), "! the X",
  #    "? the X", and the file-/line-start position. We only handle the
  #    period-space and start-of-line cases; mid-paragraph fixes stay literal.
  perl -CS -i -pe '
    s/\b(?:[Tt]he) (the) /\1 /g;                                  # The the X / the the X → the X
    s/^the (Staff Engineer|Director of Engineering|VP-Product Reviewer|Game Dev Reviewer|Front-End Reviewer|UX Reviewer|Data Science Reviewer)\b/The \1/g;  # line-start
    s/(\. |\? |\! )the (Staff Engineer|Director of Engineering|VP-Product Reviewer|Game Dev Reviewer|Front-End Reviewer|UX Reviewer|Data Science Reviewer)\b/\1The \2/g;  # sentence-initial
  ' "$f"
  fixed=$((fixed + 1))
  echo "rewrote: $f (backup: ${f}.bak)"
done

if (( fixed == 0 && path_fixed_count == 0 )); then
  echo "depersonalize-for-publish: no files needed rewriting."
elif (( fixed == 0 )); then
  echo ""
  echo "depersonalize-for-publish: path rewrites applied to $path_fixed_count file(s); no persona/identity substitutions needed."
else
  echo ""
  echo "depersonalize-for-publish: rewrote $fixed file(s) (persona/identity). Review diffs:"
  echo "  for f in ${TARGET}/**/*.bak; do diff \"\$f\" \"\${f%.bak}\"; done"
  echo "  (or use git diff if files are tracked)"
fi
exit 0
