#!/usr/bin/env bash
# publish-time-transform.sh — scan or rewrite files to normalize meta-repo
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
# *.py, *.json, *.ts, *.toml, *.js, *.mjs, *.ps1, PLUS extensionless files whose
# first line is a `#!` shebang — same surface as the publish-repo check). Excluded:
# `archive/`, `tasks/`, `experiments/`, `evals/`, `docs/{plans,research,decisions,specs}/`.
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
# Lowercase-slug and compound forms (C8, 2026-07-09 hardening): the table above is
# TitleCase/diacritic prose only, case-sensitive and \b-bounded — lowercase slugs
# (patrik, fru, pali, zoli, camelia, yk) used as functional identifiers (schema
# enums, YAML/JSON field values, filename-glob suffixes) and CamelCase-glued
# compounds (FruFinding) slipped through both the \b anchor (defeats glued
# compounds — no boundary between "Fru" and "Finding") and the case-sensitivity
# (defeats lowercase forms entirely). Lowercase keys map to the SAME role as their
# prose form. 'sid' is DELIBERATELY EXCLUDED — see LOWERCASE_SLUG_KEYS comment
# below. Known functional occurrences (schema `reviewer` enums, field values) are
# held rather than blanket-rewritten — see DEPERSONALIZE_PROTECT below.
#
# Identity vocabulary (PM name forms and private org slugs):
#   Dónal O'Duffy & Claude        → the Coordinator Authors
#   Donal O'Duffy & Claude        → the Coordinator Authors  (ASCII variant)
#   Donal + Claude                → the Coordinator Authors
#   Dónal                         → the PM  (defensive — stray first-name use)
#
# Per-operator org-slug rewrites (private-org → public-org) are loaded from an
# optional sibling file `depersonalize-identity.sh` (see
# `depersonalize-identity.example.sh` for the shape). Without that file, no
# org-slug rewrites are applied.
#
# Codename vocabulary: loaded at runtime from the sibling codename-provenance-seed.sh
# (committed; .percolate-ignore'd; absent on OSS installs → no-op). See that file for the table.
#
# Path mapping (dev-tree → publish-tree):
#   plugins/coordinator-claude/coordinator/ → plugins/coordinator/  (two-segment collapse, applied first)
#   plugins/coordinator-claude/data-science/ → plugins/data-science/
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
#   4 — environment prerequisite unmet (bash < 4) — distinct from code 1 so a
#       --check caller does not misread a version abort as "hits found"

set -euo pipefail

if (( BASH_VERSINFO[0] < 4 )); then
    echo "ERROR: publish-time-transform.sh requires bash 4.0 or later (associative arrays)." >&2
    echo "       Detected: bash ${BASH_VERSION:-unknown}" >&2
    echo "  macOS ships bash 3.2 as /bin/bash. Install a current bash and put it first on PATH:" >&2
    echo "      brew install bash" >&2
    echo '      export PATH="$(brew --prefix)/bin:$PATH"   # add to ~/.zshrc or ~/.bashrc' >&2
    exit 4
fi

usage() {
  cat <<'EOF'
Usage: publish-time-transform.sh --check PATH
       publish-time-transform.sh --fix [--keep-bak] PATH

  --check     Scan PATH (file or dir); print file:line:hit; exit 1 if any persona
              names, identity strings, or dev-tree plugin paths found. Default mode
              if --check / --fix omitted.
  --fix       Rewrite files in-place, substituting persona names and identity strings
              for role labels and canonical public identifiers, and rewriting dev-tree
              plugin paths to publish-tree form.
              Backups written to <file>.bak before rewrite; cleaned up on exit by
              default (see --keep-bak).
              Path rewrite runs BEFORE persona substitution (structural-first).
  --keep-bak  Preserve .bak files for manual recovery (default: clean up after
              rewrite). Use when running outside the publish hook flow.

Surface: tracked-or-not *.md, *.sh, *.py, *.json, *.ts, *.toml, *.js, *.mjs, *.ps1 files.
  Excluded subtree prefixes: archive/, tasks/, experiments/, evals/,
  docs/{plans,research,decisions,specs}/.

Path-mapping table (static floor — always applied):
  plugins/coordinator-claude/coordinator/ → plugins/coordinator/
  plugins/coordinator-claude/data-science/ → plugins/data-science/
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

Per-operator org-slug rewrites are loaded from an optional sibling file
`depersonalize-identity.sh` (see `depersonalize-identity.example.sh` for the
shape). Without that file, no org-slug rewrites are applied.

Codename vocabulary: loaded at runtime from the sibling codename-provenance-seed.sh
(committed; .percolate-ignore'd; absent on OSS installs → no-op). See that file for the table.

Exit codes:
  0  clean (--check) or rewrite applied (--fix)
  1  hits found (--check) or rewrite error (--fix)
  2  usage error
  3  state/environment fault (self-corruption detected — restore from source)
  4  environment prerequisite unmet (bash < 4) — distinct from code 1 so a
     --check caller does not misread a version abort as "hits found"
EOF
}

if (( $# == 0 )); then
  usage >&2
  exit 2
fi

MODE="check"
KEEP_BAK=false
TARGET=""
while (( $# > 0 )); do
  case "$1" in
    --check)    MODE="check"; shift ;;
    --fix)      MODE="fix"; shift ;;
    --keep-bak) KEEP_BAK=true; shift ;;
    -h|--help)  usage; exit 0 ;;
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
  # Persona names (must match the publish-repo check-persona-names.py pattern).
  # Persona depersonalization is intentional for OSS distribution: the reviewer-
  # role framing carries the value; persona names are private vocabulary.
  ["Patrik"]="the Staff Engineer"
  ["Zolí"]="the Director of Engineering"
  ["Zoli"]="the Director of Engineering"
  ["YK"]="the VP-Product Reviewer"
  ["Sid"]="the Game Dev Reviewer"
  ["Palí"]="the Front-End Reviewer"
  ["Pali"]="the Front-End Reviewer"
  ["Fru"]="the UX Reviewer"
  ["Camelia"]="the Data Science Reviewer"
  # --- Lowercase-slug forms (C8, 2026-07-09) — same role as prose form above.
  # 'sid' is intentionally OMITTED here: it collides catastrophically with the
  # pervasive "session_id" abbreviation used as a bare variable/flag name
  # throughout the coordinator shell/JS surface (`local sid=`, `--sid`, `<sid>`,
  # `em_sid`, `stub_sid`, etc — hundreds of occurrences). A blanket \b-bounded
  # 'sid' key would misfire on any of those. Held for hand review; not
  # auto-rewritten. See LOWERCASE_SLUG_KEYS below (also excludes 'sid').
  ["patrik"]="the Staff Engineer"
  ["fru"]="the UX Reviewer"
  ["pali"]="the Front-End Reviewer"
  ["zoli"]="the Director of Engineering"
  ["camelia"]="the Data Science Reviewer"
  ["yk"]="the VP-Product Reviewer"
  # --- Compound glued forms (no separator, defeats \b entirely). Exact-string
  # literal keys, same convention as codename-provenance-seed.sh's D5 underscore-
  # glued entries. Extend this list as new compounds are discovered (grep the
  # guard's output, add the exact key — do not attempt a general prefix regex).
  ["FruFinding"]="UXReviewerFinding"
  # NOTE: PM-name forms ("Dónal", "Dónal O'Duffy & Claude", etc.) are intentionally
  # NOT depersonalized — the PM is the author of this OSS project (repo lives at
  # github.com/dbc-oduffy/coordinator-claude) and merits attribution in LICENSE,
  # marketplace owner.name, README, and other attribution surfaces. The prior rule
  # produced broken attributions like "Copyright (c) 2026 the PM O'Duffy" in
  # LICENSE and stripped owner.name from marketplace.json, which is the inverse
  # of what an OSS publish target should do.
  # Per-operator org-slug rewrites are merged in below from
  # `depersonalize-identity.sh` (sibling file, optional).
)

# Fix-application order: persona names only. (PM-name forms removed — see
# NAME_TO_ROLE comment above.) Assoc array iteration order is undefined in
# bash, so we maintain an explicit ordered list here.
ORDERED_KEYS=(
  # Compound/glued forms FIRST (longest-match-first — see D3/D4 precedent in
  # codename-provenance-seed.sh). FruFinding must precede "Fru"/"fru": \b would
  # not have caught the glue anyway (no boundary between "Fru" and "Finding"),
  # but ordering is preserved for consistency with the established convention.
  "FruFinding"
  "Patrik"
  "Zolí"
  "Zoli"
  "YK"
  "Sid"
  "Palí"
  "Pali"
  "Fru"
  "Camelia"
  # Lowercase-slug forms (C8) — 'sid' deliberately absent, see NAME_TO_ROLE comment.
  "patrik"
  "fru"
  "pali"
  "zoli"
  "camelia"
  "yk"
)

# LOWERCASE_SLUG_KEYS: the subset of ORDERED_KEYS requiring the DEPERSONALIZE_PROTECT
# functional-hold guard at --fix time (see the --fix loop below). These are the
# lowercase persona slugs that also appear as PARSED values in shipped surfaces —
# JSON schema `reviewer` enums (schemas/review.schema.json,
# artifact-shape-contract/artifact-shape-contract.schema.json), agent-definition
# `"reviewer": "<slug>"` JSON examples (6 files: staff-eng.md, staff-ux.md,
# eng-director.md, vp-product.md, senior-front-end.md, staff-data-sci.md), and
# JSON/JS object-key literals (lib/workweek-trail-scope.sh's `"patrik": patrik_shas`
# shape). Blanket-rewriting these would desync the enum from its consumers (real
# `reviewer: patrik` frontmatter would no longer validate) — that consistent,
# cross-file rewrite is out of scope for a mechanical substitution pass, so these
# specific occurrences are HELD (skipped) rather than silently corrupted. FruFinding
# is a compound literal, not in this set — no reviewer-field collision risk.
LOWERCASE_SLUG_KEYS=( "patrik" "fru" "pali" "zoli" "camelia" "yk" )
is_lowercase_slug_key() {
  local k="$1" x
  for x in "${LOWERCASE_SLUG_KEYS[@]}"; do
    [[ "$k" == "$x" ]] && return 0
  done
  return 1
}

# Self-protection: if this script's own ORDERED_KEYS look already-substituted
# (every key starts with "the " or "dbc-"), a past run depersonalized our own
# substitution map. Subsequent --fix sweeps would be no-ops and silently lie
# about it. Refuse to run; instruct the operator to restore from source.
# Tripped previously: dest's depersonalize.sh had ORDERED_KEYS = ("the Coordinator
# Authors", "the Staff Engineer", ...) — repaired 2026-05-17 by copying source.
self_corrupted=true
for k in "${ORDERED_KEYS[@]}"; do
  # "the " and "dbc-" are the canonical already-substituted prefixes for persona
  # and org-slug keys respectively. This guard is a whole-map detector: it
  # short-circuits to self_corrupted=false on the first non-prefixed key (e.g.
  # "Patrik"). Codename corruption (a separate failure mode) is not detectable
  # here while persona keys remain intact; the guard does not attempt it.
  if [[ "$k" != "the "* && "$k" != "dbc-"* ]]; then
    self_corrupted=false
    break
  fi
done
if [[ "$self_corrupted" == "true" ]]; then
  echo "publish-time-transform: FATAL — ORDERED_KEYS look already-substituted." >&2
  echo "  This script's substitution map has been corrupted by a past depersonalize run." >&2
  echo "  Restore from the meta-repo source (either candidate path, whichever exists):" >&2
  echo "    cp \$HOME/.claude/plugins/coordinator-claude/coordinator/bin/publish-time-transform.sh \\" >&2
  echo "       \$(realpath \"\$0\")" >&2
  echo "    # or, if running from the DoE-claude source clone directly:" >&2
  echo "    cp <path-to-DoE-claude>/coordinator/bin/publish-time-transform.sh \\" >&2
  echo "       \$(realpath \"\$0\")" >&2
  # Review: code-reviewer — exit 2 is usage error; self-corruption is a state/environment fault.
  exit 3
fi

# ---------------------------------------------------------------------------
# Per-operator identity overrides. Sourced from a sibling `depersonalize-identity.sh`
# if present. The override file declares `OPERATOR_NAME_TO_ROLE` (assoc array)
# and `OPERATOR_ORDERED_KEYS` (indexed array); we merge them into the main
# tables here. Without the file, no org-slug rewrites fire — the static tables
# above contain only role/identity vocabulary that ships with the coordinator
# plugin itself. See `depersonalize-identity.example.sh` for the shape.
# ---------------------------------------------------------------------------
_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_OP_IDENTITY="${_SCRIPT_DIR}/depersonalize-identity.sh"
if [[ -f "$_OP_IDENTITY" ]]; then
  # shellcheck source=/dev/null
  source "$_OP_IDENTITY"
  # Note: ${VAR[@]+set} (not ${VAR+set}) is required for assoc/indexed arrays;
  # bare ${VAR+set} probes index 0, which is unset for sparse/string-keyed arrays.
  # shellcheck disable=SC2199  # intentional: ${VAR[@]+set} probes whole-array set-ness for sparse/string-keyed maps
  if [[ -n "${OPERATOR_NAME_TO_ROLE[@]+set}" ]]; then
    for _k in "${!OPERATOR_NAME_TO_ROLE[@]}"; do
      NAME_TO_ROLE["$_k"]="${OPERATOR_NAME_TO_ROLE[$_k]}"
    done
  fi
  # shellcheck disable=SC2199  # same rationale as above
  if [[ -n "${OPERATOR_ORDERED_KEYS[@]+set}" ]] && (( ${#OPERATOR_ORDERED_KEYS[@]} > 0 )); then
    ORDERED_KEYS+=("${OPERATOR_ORDERED_KEYS[@]}")
  fi
fi

# ---------------------------------------------------------------------------
# Built-in codename provenance seed. Sourced from a sibling
# `codename-provenance-seed.sh` if present. The seed declares
# `CODENAME_TO_PLACEHOLDER` (assoc array) and `CODENAME_ORDERED_KEYS` (indexed
# array, longest-match-first with case variants as separate keys per D3/D4); we
# merge them into the main tables here. This file is committed but
# `.percolate-ignore`'d — the OSS publish tree never receives it, so the OSS
# transform sources an absent file, producing no-op identical to a fresh
# operator with no depersonalize-identity.sh. Codenames thus flow into the
# same PATTERN (--check) and fix loop (--fix) machinery as personas.
# See Decision D2: docs/plans/2026-06-27-genericize-provenance-sweeper.md
# ---------------------------------------------------------------------------
_CODENAME_SEED="${_SCRIPT_DIR}/codename-provenance-seed.sh"
declare -A STEM_TO_PLACEHOLDER=()
STEM_KEYS=()
if [[ -f "$_CODENAME_SEED" ]]; then
  # shellcheck source=/dev/null
  source "$_CODENAME_SEED"
  # Note: ${VAR[@]+set} (not ${VAR+set}) is required for assoc/indexed arrays;
  # bare ${VAR+set} probes index 0, which is unset for sparse/string-keyed arrays.
  # shellcheck disable=SC2199  # intentional: ${VAR[@]+set} probes whole-array set-ness for sparse/string-keyed maps
  if [[ -n "${CODENAME_TO_PLACEHOLDER[@]+set}" ]]; then
    for _k in "${!CODENAME_TO_PLACEHOLDER[@]}"; do
      NAME_TO_ROLE["$_k"]="${CODENAME_TO_PLACEHOLDER[$_k]}"
    done
  fi
  # shellcheck disable=SC2199  # same rationale as above
  if [[ -n "${CODENAME_ORDERED_KEYS[@]+set}" ]] && (( ${#CODENAME_ORDERED_KEYS[@]} > 0 )); then
    ORDERED_KEYS+=("${CODENAME_ORDERED_KEYS[@]}")
  fi
  # D7 (2026-07-10, v3 go-live privacy audit): CODENAME_STEM_MAP/CODENAME_STEM_KEYS —
  # boundary-free codename-stem rewrite pass, separate from the exact-key ORDERED_KEYS
  # loop (see codename-provenance-seed.sh's own D7 header comment for the full
  # rationale). Merged into STEM_TO_PLACEHOLDER/STEM_KEYS here; applied by
  # apply_stem_rewrites() in the --fix loop, AFTER the exact-key substitution pass.
  # shellcheck disable=SC2199
  if [[ -n "${CODENAME_STEM_MAP[@]+set}" ]]; then
    for _k in "${!CODENAME_STEM_MAP[@]}"; do
      STEM_TO_PLACEHOLDER["$_k"]="${CODENAME_STEM_MAP[$_k]}"
    done
  fi
  # shellcheck disable=SC2199
  if [[ -n "${CODENAME_STEM_KEYS[@]+set}" ]] && (( ${#CODENAME_STEM_KEYS[@]} > 0 )); then
    STEM_KEYS+=("${CODENAME_STEM_KEYS[@]}")
  fi
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
  "plugins/coordinator-claude/game-dev/"
  "plugins/coordinator-claude/web-dev/"
  "plugins/coordinator-claude/deep-research/"
)
PATH_REWRITE_DESTS=(
  "plugins/coordinator/"
  "plugins/data-science/"
  "plugins/game-dev/"
  "plugins/web-dev/"
  "plugins/deep-research/"
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
  echo "publish-time-transform: FATAL — PATH_REWRITE_SOURCES look already-substituted." >&2
  echo "  The path-rewrite seed no longer contains 'coordinator-claude' in any source pattern." >&2
  echo "  This script's path-rewrite map has been corrupted by a past depersonalize run." >&2
  echo "  Restore from the meta-repo source (either candidate path, whichever exists):" >&2
  echo "    cp \$HOME/.claude/plugins/coordinator-claude/coordinator/bin/publish-time-transform.sh \\" >&2
  echo "       \$(realpath \"\$0\")" >&2
  echo "    # or, if running from the DoE-claude source clone directly:" >&2
  echo "    cp <path-to-DoE-claude>/coordinator/bin/publish-time-transform.sh \\" >&2
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
EXCLUDED_BASENAMES=( "publish-time-transform.sh" "check-persona-names.py" )

is_excluded() {
  local rel="$1"
  local base; base="$(basename "$rel")"
  for b in "${EXCLUDED_BASENAMES[@]}"; do
    [[ "$base" == "$b" ]] && return 0
  done
  case "$base" in *check-persona*|*depersonalize*|*codename-provenance*) return 0 ;; esac
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
  done < <(find "$TARGET" -type f \( -name '*.md' -o -name '*.sh' -o -name '*.py' -o -name '*.json' -o -name '*.ts' -o -name '*.toml' -o -name '*.js' -o -name '*.mjs' -o -name '*.ps1' \) -print0)

  # Extensionless shebang scripts (audit A6 leak vector): a file with no
  # matched extension above whose first line begins with `#!` is still a
  # script and can carry the same leak surface (persona names, org slugs,
  # codenames). The name-glob pass above only catches known extensions;
  # extensionless executables (e.g. a `bin/` script with no `.sh` suffix)
  # were previously silently skipped. Detect via first-line `#!` sniff,
  # restricted to files whose basename has NO dot (so we don't re-scan
  # files the name-glob pass already caught, and don't false-positive on
  # e.g. `README` or binary blobs with an unrelated extension).
  while IFS= read -r -d '' f; do
    base="$(basename "$f")"
    case "$base" in *.*) continue ;; esac  # has an extension — already handled above, skip
    rel="${f#"$TARGET"/}"
    if is_excluded "$rel"; then continue; fi
    if head -n1 "$f" 2>/dev/null | grep -q '^#!'; then
      FILES+=("$f")
    fi
  done < <(find "$TARGET" -type f -print0)
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
  ["game-dev"]=1
  ["web-dev"]=1
  ["deep-research"]=1
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
    echo "publish-time-transform: WARNING — $TARGET/plugins/ exists but no plugins beyond the static floor were discovered; only the 5 floor mappings will be applied." >&2
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

# ---------------------------------------------------------------------------
# apply_stem_rewrites (D7, 2026-07-10 v3 go-live privacy audit): case-insensitive
# rewrite of codename stems, CONSTRAINED to identifier-glued contexts only (see
# codename-provenance-seed.sh's D7 header for full rationale). Runs AFTER the
# exact-key ORDERED_KEYS loop for a given file, so any occurrence already
# resolved by an exact compound key (e.g. "MAKIMA_ROOT_RESOLVED") is already
# gone from the buffer before this pass runs its case-insensitive match on
# "makima" — no double-substitution risk from the two passes disagreeing on a
# shared substring, since exact-key matches always disappear first.
#
# Glued-only scope (Review: code-reviewer Finding 1, 2026-07-10): this pass exists
# ONLY to catch identifier-GLUED forms that the \b-bounded exact-key pass misses
# (makima_root, makimaRoot, MAKIMA_PRESENT_OK — underscore/camelCase adjacency
# defeats \b, see D5 note in codename-provenance-seed.sh). It must NOT match a
# bare, whitespace/punctuation-bounded standalone occurrence of the stem (e.g.
# ordinary prose "the crew used the holodeck for training") — "holodeck" is a
# real Star Trek term and this doctrine's own conventions explicitly invite
# Star Trek prose (~/.claude/CLAUDE.md § Communication Style); an unconstrained
# substring match would silently corrupt legitimate franchise-term prose into a
# nonsense placeholder. Standalone occurrences are already handled by the
# \b-bounded exact-key pass above, which does not fire on the bare human-readable
# term (no exact key for it) — so a standalone "holodeck" is intentionally left
# untouched by BOTH passes; only the private per-repo compound forms are keyed.
# The match below therefore requires the matched stem span to be immediately
# adjacent (no separator) to a word character on at least one side — a
# lookbehind/lookahead on `[A-Za-z0-9_]`, not a `\b` (which would defeat the
# glued case this pass exists to catch in the first place).
#
# Case-preservation rule: the replacement casing mirrors the matched stem's
# casing style, not the surrounding file's style —
#   ALL-CAPS stem   (MAKIMA)  -> ALL-CAPS placeholder   (EXAMPLE_ORCHESTRATION_HUB)
#   Title-Case stem (Makima)  -> Title-Case placeholder (ExampleOrchestrationHub)
#   lowercase stem  (makima)  -> lowercase placeholder  (example_orchestration_hub)
# Any OTHER casing (e.g. truly mixed-case "MaKiMa") falls through to the
# lowercase placeholder form — named explicitly here (Review: code-reviewer
# Finding 2) so the fallback is stated, not implicit; still removes the
# codename, just loses case fidelity for the rare mixed-case spelling.
# This keeps `MAKIMA_PRESENT_OK` -> `EXAMPLE_ORCHESTRATION_HUB_PRESENT_OK`,
# `_MakimaUnresolvable` -> `_ExampleOrchestrationHubUnresolvable`, and
# `makima_root`/`makimaRoot` -> `example_orchestration_hub_root`/
# `exampleOrchestrationHubRoot` (Perl's \U...\E / \u lowercase-first fallthrough
# naturally yields the correct camelCase continuation because only the matched
# stem span is re-cased — surrounding "Root"/"root" is untouched by the s///).
# ---------------------------------------------------------------------------
apply_stem_rewrites() {
  local f="$1"
  local stem placeholder
  for stem in "${STEM_KEYS[@]}"; do
    placeholder="${STEM_TO_PLACEHOLDER[$stem]}"
    # Quick pre-check (case-insensitive) before paying the perl invocation cost.
    if ! grep -qiF "$stem" "$f" 2>/dev/null; then continue; fi
    DEPERSONALIZE_STEM="$stem" DEPERSONALIZE_STEM_PLACEHOLDER="$placeholder" \
      perl -CS -i -pe '
        my $stem = $ENV{DEPERSONALIZE_STEM};
        my $repl_lower = $ENV{DEPERSONALIZE_STEM_PLACEHOLDER};
        my $repl_upper = uc($repl_lower);
        my $repl_title = $repl_lower;
        $repl_title =~ s/(^|_)([a-z])/$1 . uc($2)/ge;
        $repl_title =~ s/_//g;
        # Glued-only: require a word char immediately adjacent on at least one
        # side (lookbehind OR lookahead), not a bare \b — this is what catches
        # makima_root/makimaRoot/MAKIMA_PRESENT_OK while leaving a standalone
        # whitespace/punctuation-bounded "holodeck" untouched (Finding 1).
        s/(?:(?<=[A-Za-z0-9_])(\Q$stem\E)|(\Q$stem\E)(?=[A-Za-z0-9_]))/
          my $m = defined($1) ? $1 : $2;
          if ($m eq uc($m)) { $repl_upper }
          elsif ($m eq ucfirst(lc($m))) { $repl_title }
          else { $repl_lower }
        /gie;
      ' "$f"
  done
}

# ---------------------------------------------------------------------------
# rename_codename_basenames (D6/form-c, 2026-07-10 v3 go-live privacy audit):
# renames the codename-bearing FILE BASENAMES enumerated in
# CODENAME_BASENAME_RENAMES. Hand-listed here as a second table alongside the
# same four pairs' exact keys in CODENAME_TO_PLACEHOLDER (codename-provenance-
# seed.sh) — NOT derived programmatically (Review: code-reviewer Finding 5,
# 2026-07-10: a clean bash derivation from "exact keys ending in a known
# extension" would require reliably distinguishing basename-rename keys from
# other extension-suffixed exact keys in that same map with no existing marker
# to key off, which risks silently over-selecting; the two tables are kept
# hand-synced instead). Single-source-of-truth caveat: if a fifth codename-
# bearing file is ever added, update BOTH this array AND its
# CODENAME_TO_PLACEHOLDER exact-key counterpart in codename-provenance-seed.sh —
# they intentionally mirror each other and must stay in lockstep by hand.
# Populated from codename-provenance-seed.sh's exact keys that end in a known
# file extension — .sh/.md/etc. Content substitution (apply_stem_rewrites + the
# exact-key loop) has already run over FILES by the time this is called, so
# in-file textual references to the OLD basename have already been rewritten to
# the NEW basename via the exact CODENAME_ORDERED_KEYS entries for those
# basenames (see codename-provenance-seed.sh D6). This function performs the
# actual `git mv`-equivalent filesystem rename. Returns the count of files
# renamed.
# ---------------------------------------------------------------------------
CODENAME_BASENAME_RENAMES=(
  "coordinator-makima-root.sh:coordinator-example-orchestration-hub-root.sh"
  "migrate-state-to-makima.sh:migrate-state-to-example-orchestration-hub.sh"
  "check-makima-doctor-sentinel.sh:check-example-orchestration-hub-doctor-sentinel.sh"
  "makima-4th-class-ref-manifest.md:example-orchestration-hub-4th-class-ref-manifest.md"
)
rename_codename_basenames() {
  local target="$1"
  local renamed=0
  local entry old_base new_base
  for entry in "${CODENAME_BASENAME_RENAMES[@]}"; do
    old_base="${entry%%:*}"
    new_base="${entry##*:}"
    while IFS= read -r -d '' old_path; do
      new_path="$(dirname "$old_path")/${new_base}"
      if [[ -e "$new_path" ]]; then
        echo "publish-time-transform: WARNING — rename target already exists, skipping: $new_path" >&2
        continue
      fi
      mv "$old_path" "$new_path"
      # Progress line goes to stderr — stdout is reserved for the final numeric
      # count (caller captures stdout via command substitution). Emitting the
      # progress line to stdout would corrupt the count into a multi-line string.
      echo "renamed: $old_path -> $new_path" >&2
      # Rename-manifest seam (2026-07-10): when the caller (publish.sh) sets
      # PUBLISH_RENAME_MANIFEST, record old->new pairs so the caller can
      # reconcile its own AUDIT_FILES list — otherwise the Phase 4 personal-data
      # audit scans the now-nonexistent old path (false ENOENT scan failure) and
      # never scans the new path (audit coverage gap). No-op when unset.
      if [[ -n "${PUBLISH_RENAME_MANIFEST:-}" ]]; then
        printf '%s\t%s\n' "$old_path" "$new_path" >> "$PUBLISH_RENAME_MANIFEST"
      fi
      renamed=$((renamed + 1))
    done < <(find "$target" -type f -name "$old_base" -print0 2>/dev/null)
  done
  # Review: code-reviewer Finding 4 (2026-07-10) — cheap post-rename verification:
  # the old comment's "textual references already rewritten" claim is a point-in-
  # time audit assertion, not a structural guarantee (a fresh file added later
  # could reference the old basename via a form the exact-key pass doesn't cover —
  # string concatenation, a glob, basename comparison). Non-fatal: re-grep the
  # tree for each old basename and warn to stderr if any textual reference
  # survives. Not fatal because --fix has already run; this converts a silent
  # dangling-reference risk into a visible publish-time warning.
  local old_base_check hit_count self_basename
  self_basename="$(basename "${BASH_SOURCE[0]}")"
  for entry in "${CODENAME_BASENAME_RENAMES[@]}"; do
    old_base_check="${entry%%:*}"
    # Exclude this transform script's own published copy from the scan: its
    # CODENAME_BASENAME_RENAMES array (above) legitimately carries the old
    # basenames as map DATA (the rename table itself), not as a live/dangling
    # reference — without this exclusion every publish false-positives on its
    # own source (code-reviewer Finding 4 follow-up, 2026-07-10).
    #
    # Review: code-reviewer Finding 4 (2026-07-10), re-verified by review-integrator:
    # the exclusion is basename-shaped (matches ANY file named publish-time-transform.sh
    # in $target, not just this script's specific self-copy) and was flagged as broader
    # than the stated self-copy-only intent. Narrowing was considered and rejected: this
    # script runs from the SOURCE tree (coordinator/bin/), never from $target, and
    # coordinator/.percolate-ignore root-anchor-excludes /bin/ (and /hooks/, /lib/) from
    # every registered publish target as of v3split-02 (commit 1f0f0351, 2026-07-09) —
    # publish_sync.py's ignore.matches() gate filters at copy-time, so no publish target
    # can ever place a copy of this script under $target. Narrowing to the running
    # script's resolved absolute path would therefore match nothing in $target and
    # silently re-expose the exact false-positive this exclusion exists to prevent, the
    # moment /bin/ percolation policy changes again. Keeping the basename form is the
    # correct choice today: the false-negative risk it accepts (a hypothetical second,
    # unrelated publish-time-transform.sh elsewhere in $target) is not currently
    # reachable, while a path-anchored form is a silent no-op under the current
    # percolate-ignore policy. Revisit if /bin/ (or this script specifically) is ever
    # re-admitted to a publish target.
    hit_count="$(grep -rlF "$old_base_check" "$target" 2>/dev/null | grep -vF "/${self_basename}" | wc -l | tr -d ' ')"
    if [[ "$hit_count" != "0" ]]; then
      echo "publish-time-transform: WARNING — old basename '$old_base_check' still referenced in $hit_count file(s) after rename; dangling reference risk (Finding 4) — grep -rl '$old_base_check' '$target' to locate." >&2
    fi
  done
  echo "$renamed"
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
# D7: STEM_KEYS are matched case-insensitively (see apply_stem_rewrites below), so
# --check must also grep case-insensitively for these to report accurately. grep -i
# on the whole PATTERN would also case-fold the persona/identity keys, which is
# undesirable (would flag e.g. lowercase "sid" collisions again). Instead append the
# stem alternatives to a SEPARATE pattern checked with grep -i.
STEM_PATTERN=""
for i in "${!STEM_KEYS[@]}"; do
  [[ -n "$STEM_PATTERN" ]] && STEM_PATTERN+="|"
  escaped_stem=$(DEPERSONALIZE_ESC_KEY="${STEM_KEYS[$i]}" perl -e '
    my $k = $ENV{DEPERSONALIZE_ESC_KEY};
    $k =~ s/([.+*?^\${}()|[\]\\])/\\$1/g;
    print $k;
  ')
  STEM_PATTERN+="${escaped_stem}"
done
PATTERN+=")"

if [[ "$MODE" == "check" ]]; then
  hits=0
  for f in "${FILES[@]}"; do
    # grep -nE gives POSIX extended regex; -H prepends filename. (Was -P, but
    # macOS BSD grep lacks -P, which made --check silently pass. PATTERN is
    # built from literal-escaped keys joined by | — pure ERE, no PCRE features
    # required.)
    file_hit=0
    if grep -nHE "$PATTERN" "$f" 2>/dev/null; then
      file_hit=1
    fi
    # D7: case-insensitive stem check (glued-identifier codename leaks).
    if [[ -n "$STEM_PATTERN" ]] && grep -nHEi "$STEM_PATTERN" "$f" 2>/dev/null; then
      file_hit=1
    fi
    if (( file_hit == 1 )); then
      hits=$((hits + 1))
    fi
  done

  if (( hits > 0 )); then
    echo ""
    echo "publish-time-transform: $hits file(s) carry persona names, identity strings, or dev-tree plugin paths."
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

  echo "publish-time-transform: clean (${#FILES[@]} file(s) scanned)."
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
  # D7: also check STEM_PATTERN case-insensitively — a file whose ONLY hit is a
  # glued stem form (e.g. "MAKIMA_PRESENT_OK", no standalone \b-bounded "makima")
  # would otherwise be skipped here and never reach apply_stem_rewrites below.
  has_exact_hit=0
  has_stem_hit=0
  grep -qE "$PATTERN" "$f" 2>/dev/null && has_exact_hit=1
  if [[ -n "$STEM_PATTERN" ]]; then
    grep -qEi "$STEM_PATTERN" "$f" 2>/dev/null && has_stem_hit=1
  fi
  if (( has_exact_hit == 0 && has_stem_hit == 0 )); then continue; fi

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
    #
    # DEPERSONALIZE_PROTECT (C8, 2026-07-09): set to "1" for LOWERCASE_SLUG_KEYS
    # members only. These lowercase slugs double as PARSED functional identifiers
    # in a few known shapes (schema `reviewer` enum entries, `"reviewer": "<slug>"`
    # field values, JSON/JS object-key literals). Blanket-rewriting those specific
    # occurrences would desync the enum from every consumer that still writes the
    # literal lowercase slug — out of scope for a mechanical pass. When protection
    # is active, lines matching one of the five functional shapes are left
    # untouched (held for hand review); all other lines still get the substitution.
    # The check-persona-slug-leak.sh guard mirrors these five patterns exactly (see
    # its is_held_line()) so --check/--fix and the guard stay in lockstep.
    protect=0
    is_lowercase_slug_key "$name" && protect=1
    DEPERSONALIZE_KEY="${name}" DEPERSONALIZE_ROLE="${role}" DEPERSONALIZE_PROTECT="$protect" \
      perl -CS -i -pe '
        my $k = $ENV{DEPERSONALIZE_KEY};
        # Escape only ASCII regex metacharacters (not non-ASCII, which quotemeta
        # would over-escape and break under -CS Unicode mode).
        # Review: code-reviewer — [ and ] omitted; unescaped [ causes fatal perl parse error
        # if any future identity key contains a bracket. Add both to the escape set.
        $k =~ s/([.+*?^\${}()|[\]])/\\$1/g;
        if ($ENV{DEPERSONALIZE_PROTECT} eq "1") {
          # Five functional-hold shapes — skip substitution on these lines (still
          # printed unchanged via the -p continue block). Mirrors
          # check-persona-slug-leak.sh is_held_line() exactly.
          next if /^\s*"(?:patrik|fru|pali|zoli|camelia|yk)",?\s*$/;
          next if /"enum":\s*\[[^\]]*"(?:patrik|fru|pali|zoli|camelia|yk)"[^\]]*\]/;
          next if /reviewer[\x27"]?:\s*[\x27"](?:patrik|fru|pali|zoli|camelia|yk)[\x27"]/;
          next if /[\x27"](?:patrik|fru|pali|zoli|camelia|yk)[\x27"]:/;
          next if /"description":.*\(e\.g\.[^)]*\b(?:patrik|fru|pali|zoli|camelia|yk)\b/;
        }
        if ($ENV{DEPERSONALIZE_KEY} =~ m{/}) {
          s/$k/$ENV{DEPERSONALIZE_ROLE}/g;
        } elsif ($ENV{DEPERSONALIZE_KEY} =~ /[^\x00-\x7F]/) {
          s/$k/$ENV{DEPERSONALIZE_ROLE}/g;
        } else {
          s/\b$k\b/$ENV{DEPERSONALIZE_ROLE}/g;
        }
      ' "$f"
  done
  # D7: boundary-free stem rewrite pass, AFTER the exact-key loop above (so any
  # occurrence already resolved by an exact compound key is already gone from the
  # buffer before this pass's bare case-insensitive stem match runs).
  apply_stem_rewrites "$f"
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

# Self-clean .bak files unless --keep-bak was passed. The publish hook
# (setup/percolate-hooks/coordinator-claude/post-rsync/10-depersonalize.sh)
# handles its own cleanup post-hook; this default-clean covers manual
# invocations outside the hook flow, which is how .bak residue ended up
# committed in the publish repo (commits 771b9f6, 6780f4a).
if [[ "$KEEP_BAK" == "false" ]]; then
  find "$TARGET" -name "*.bak" -delete 2>/dev/null || true
fi

# D6/form-c: rename codename-bearing file basenames. Runs LAST, after all
# content-level substitution (exact-key loop + apply_stem_rewrites) has already
# rewritten in-file textual references to the old basenames to their new-basename
# form via the CODENAME_ORDERED_KEYS basename entries. Only meaningful when TARGET
# is a directory (a single-file --fix invocation has nothing to search/rename
# against; the caller already named the exact file).
renamed_count=0
if [[ -d "$TARGET" ]]; then
  renamed_count="$(rename_codename_basenames "$TARGET")"
fi

if (( fixed == 0 && path_fixed_count == 0 && renamed_count == 0 )); then
  echo "publish-time-transform: no files needed rewriting."
elif (( fixed == 0 && renamed_count == 0 )); then
  echo ""
  echo "publish-time-transform: path rewrites applied to $path_fixed_count file(s); no persona/identity substitutions needed."
else
  echo ""
  echo "publish-time-transform: rewrote $fixed file(s) (persona/identity)."
  if (( renamed_count > 0 )); then
    echo "  renamed $renamed_count codename-bearing file basename(s) (see 'renamed:' lines above)."
  fi
  echo "  Review diffs:"
  if [[ "$KEEP_BAK" == "true" ]]; then
    echo "  for f in ${TARGET}/**/*.bak; do diff \"\$f\" \"\${f%.bak}\"; done"
  else
    echo "  git diff HEAD -- ${TARGET}/"
    echo "  (.bak files were removed; use git diff against the upstream branch to review changes)"
  fi
fi
exit 0
