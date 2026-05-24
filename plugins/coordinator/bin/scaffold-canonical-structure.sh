#!/usr/bin/env bash
# scaffold-canonical-structure.sh — Idempotent canonical document-structure scaffold.
#
# Purpose: reads plugins/coordinator/canonical-structure.yaml and
# creates every `creation: eager` directory entry (path ending in /) along with a
# README.md derived from the entry's `readme:` field. Idempotent — silently skips
# dirs and READMEs that already exist; NEVER clobbers existing content.
#
# Spec backlink: docs/plans/2026-05-23-cross-repo-single-surface-and-canonical-scaffold.md § Chunk 2
#
# Usage:
#   scaffold-canonical-structure.sh [--dry-run] [--root <path>]
#
# Flags:
#   --dry-run        Print what would be created; create nothing.
#   --root <path>    Target repo root to scaffold into. Defaults to
#                    `git rev-parse --show-toplevel` of the current working dir.
#   --help | -h      Show this help and exit.
#
# The manifest path is resolved relative to THIS script's location, so the
# coordinator's bundled canonical-structure.yaml is used regardless of --root.
#
# Exit codes:
#   0  Success (or dry-run completed without error).
#   1  Usage error or missing prerequisite.
#   2  Manifest parsing error.

set -euo pipefail

# ---------------------------------------------------------------------------
# Arg parsing
# ---------------------------------------------------------------------------

DRY_RUN=0
ROOT_PATH=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --help|-h)
            sed -n '3,/^set -euo pipefail/p' "${BASH_SOURCE[0]}" | grep '^#' | sed 's/^# \?//'
            exit 0
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        --root)
            if [[ $# -lt 2 ]]; then
                echo "scaffold-canonical-structure.sh: --root requires an argument" >&2
                exit 1
            fi
            ROOT_PATH="$2"
            shift 2
            ;;
        -*)
            echo "scaffold-canonical-structure.sh: unknown flag: $1" >&2
            exit 1
            ;;
        *)
            echo "scaffold-canonical-structure.sh: unexpected argument: $1" >&2
            exit 1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Resolve target root
# ---------------------------------------------------------------------------

if [[ -z "$ROOT_PATH" ]]; then
    ROOT_PATH="$(git rev-parse --show-toplevel 2>/dev/null)" || {
        echo "scaffold-canonical-structure.sh: --root not provided and not inside a git repo" >&2
        exit 1
    }
fi

# Normalise path separators on Windows (Git-Bash/MSYS)
ROOT_PATH="${ROOT_PATH//\\//}"

if [[ ! -d "$ROOT_PATH" ]]; then
    echo "scaffold-canonical-structure.sh: root dir does not exist: $ROOT_PATH" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Locate manifest relative to THIS script
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST="${SCRIPT_DIR}/../canonical-structure.yaml"
MANIFEST="$(cd "$(dirname "$MANIFEST")" && pwd)/$(basename "$MANIFEST")"

if [[ ! -f "$MANIFEST" ]]; then
    echo "scaffold-canonical-structure.sh: manifest not found at: $MANIFEST" >&2
    exit 2
fi

# ---------------------------------------------------------------------------
# Python for YAML parsing (no third-party dep required — use inline pyyaml or
# fallback to a pure-python minimal parser for the simple structure we have).
# ---------------------------------------------------------------------------

if command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON=python
else
    echo "scaffold-canonical-structure.sh: python3 not found" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Parse manifest: emit tab-separated lines for eager directory entries.
# Format: <path>\t<readme-text>
# readme-text has internal newlines replaced with \n literal for transport.
# ---------------------------------------------------------------------------

ENTRIES="$("$PYTHON" - "$MANIFEST" <<'PYEOF'
import sys, pathlib

manifest_path = pathlib.Path(sys.argv[1])
try:
    text = manifest_path.read_text(encoding="utf-8")
except Exception as e:
    print(f"ERROR: cannot read manifest: {e}", file=sys.stderr)
    sys.exit(2)

# Minimal YAML parser for the specific structure in canonical-structure.yaml.
# The manifest is authored by the coordinator; we own both sides of this contract.
# Rather than require PyYAML (not always available), parse by walking the lines
# and collecting entry blocks ourselves.
#
# An entry starts with "  - path: <value>" and ends at the next "  - path:" or EOF.
# Fields within the entry: path, creation, schema, readme (may be a block scalar).

import re

lines = text.splitlines()
entries = []
current = None
in_readme_block = False
readme_lines = []

def flush(current, readme_lines, in_readme_block):
    if current is None:
        return
    if in_readme_block or readme_lines:
        # Preserve line structure — join with actual newlines, not flattened.
        current["readme"] = "\n".join(readme_lines)
    entries.append(current)

# Content indent for block scalars — lines at this indent (or deeper) belong to the block.
# The entry fields sit at 4-space indent; block scalar content sits at ≥6-space indent
# (yaml spec: content indent = indicator indent + 1).  We'll detect termination by checking
# whether a line is a comment at ≤4-space indent OR a dedent to ≤4-space non-blank content.
ENTRY_KEY_INDENT = 4  # '    creation:', '    readme:', etc.

for line in lines:
    stripped = line.rstrip()

    if in_readme_block:
        # A block scalar terminates when we see:
        #   (a) a new list entry:  "  - path:"
        #   (b) a top-level key:   "^[a-z]" (indent 0)
        #   (c) another field in the same entry: indent exactly ENTRY_KEY_INDENT with \S
        #   (d) a comment at indent ≤ ENTRY_KEY_INDENT  — NEVER include in content
        #   (e) a blank line inside the block is preserved (part of literal content)
        # We must NOT terminate on blank lines; a blank line is valid block content.

        if stripped == "":
            # Blank line — preserve as an empty string in the block
            readme_lines.append("")
            continue

        leading_spaces = len(line) - len(line.lstrip())
        is_comment = stripped.lstrip().startswith("#")

        # Terminate conditions:
        term_new_entry   = re.match(r'^  - path:', stripped)
        term_toplevel    = leading_spaces == 0 and not is_comment
        term_entry_field = leading_spaces == ENTRY_KEY_INDENT and not stripped.lstrip().startswith("#")
        term_comment_bleed = is_comment and leading_spaces <= ENTRY_KEY_INDENT

        if term_new_entry or term_toplevel or term_entry_field or term_comment_bleed:
            in_readme_block = False
            # Strip trailing blank lines collected at end of block
            while readme_lines and readme_lines[-1] == "":
                readme_lines.pop()
            if term_new_entry:
                flush(current, readme_lines, False)
                readme_lines = []
                path_val = stripped.split("path:", 1)[1].strip()
                current = {"path": path_val, "creation": "", "schema": None, "readme": None}
                continue
            elif term_toplevel:
                # top-level key (entries: etc) — flush and reset
                flush(current, readme_lines, False)
                current = None
                readme_lines = []
                continue
            else:
                # term_entry_field or term_comment_bleed: another field or comment — fall through
                # to normal field parsing below (don't continue — process this line normally)
                pass
        else:
            # Content line of the block scalar — strip the leading indent to get content.
            # The content indent is ENTRY_KEY_INDENT + 2 (6 spaces for a |-indented block).
            # We strip at most ENTRY_KEY_INDENT + 2 leading spaces, preserving deeper indent.
            content_indent = ENTRY_KEY_INDENT + 2
            if len(line) > content_indent and line[:content_indent] == " " * content_indent:
                content = line[content_indent:].rstrip()
            elif len(line) >= leading_spaces:
                # Partial indent — strip what's there
                content = stripped.lstrip()
            else:
                content = stripped
            readme_lines.append(content)
            continue

    # Entry start
    m_entry = re.match(r'^  - path:\s*(.+)', stripped)
    if m_entry:
        flush(current, readme_lines, False)
        readme_lines = []
        in_readme_block = False
        path_val = m_entry.group(1).strip()
        current = {"path": path_val, "creation": "", "schema": None, "readme": None}
        continue

    if current is None:
        continue

    m_creation = re.match(r'^    creation:\s*(.+)', stripped)
    if m_creation:
        current["creation"] = m_creation.group(1).strip()
        continue

    m_schema = re.match(r'^    schema:\s*(.+)', stripped)
    if m_schema:
        val = m_schema.group(1).strip()
        current["schema"] = None if val in ("null", "~", "") else val
        continue

    # Detect block scalar indicators: both folded (>) and literal (|)
    m_readme_block = re.match(r'^    readme:\s*[>|]$', stripped)
    if m_readme_block:
        in_readme_block = True
        readme_lines = []
        continue

    m_readme_inline = re.match(r'^    readme:\s*(.+)', stripped)
    if m_readme_inline:
        val = m_readme_inline.group(1).strip()
        current["readme"] = None if val in ("null", "~") else val
        continue

# Flush last entry
flush(current, readme_lines, in_readme_block)

for entry in entries:
    path = entry.get("path", "")
    creation = entry.get("creation", "")
    readme = entry.get("readme") or ""

    # Only eager directory entries (path ends with /)
    if creation != "eager" or not path.endswith("/"):
        continue

    # Transport: encode for tab-delimited line transport.
    # Replace backslashes first (so \n encoding doesn't double-escape), then newlines.
    # Bash side decodes with printf '%b' to restore structure.
    readme_transport = readme.replace("\\", "\\\\").replace("\t", "    ").replace("\n", "\\n")
    print(f"{path}\t{readme_transport}")
PYEOF
)" || {
    echo "scaffold-canonical-structure.sh: manifest parse failed" >&2
    exit 2
}

if [[ -z "$ENTRIES" ]]; then
    echo "scaffold-canonical-structure.sh: no eager directory entries found in manifest — nothing to do"
    exit 0
fi

# ---------------------------------------------------------------------------
# Scaffold
# ---------------------------------------------------------------------------

CREATED_DIRS=0
CREATED_READMES=0
SKIPPED=0

if [[ $DRY_RUN -eq 1 ]]; then
    echo "[dry-run] target root: $ROOT_PATH"
    echo "[dry-run] manifest:    $MANIFEST"
fi

while IFS=$'\t' read -r entry_path readme_text; do
    [[ -z "$entry_path" ]] && continue

    # Strip trailing slash to get the directory path
    dir_rel="${entry_path%/}"
    dir_abs="${ROOT_PATH}/${dir_rel}"
    readme_abs="${dir_abs}/README.md"

    # --- Directory ---
    if [[ ! -d "$dir_abs" ]]; then
        if [[ $DRY_RUN -eq 1 ]]; then
            echo "[dry-run] would create dir:    ${dir_rel}/"
        else
            mkdir -p "$dir_abs"
            echo "created dir:    ${dir_rel}/"
            CREATED_DIRS=$((CREATED_DIRS + 1))
        fi
    else
        if [[ $DRY_RUN -eq 1 ]]; then
            echo "[dry-run] skip (exists) dir:   ${dir_rel}/"
        fi
        SKIPPED=$((SKIPPED + 1))
    fi

    # --- README.md (only if readme text is non-empty) ---
    if [[ -n "$readme_text" ]]; then
        if [[ ! -f "$readme_abs" ]]; then
            if [[ $DRY_RUN -eq 1 ]]; then
                echo "[dry-run] would create README: ${dir_rel}/README.md"
            else
                # Write the README. Content: heading + body from readme: field.
                # No clobber — we only reach here because -f test was false.
                # readme_text has \n encoded as the two-char sequence \n; decode with printf %b.
                {
                    printf '# %s\n\n' "$dir_rel"
                    printf '%b\n' "$readme_text"
                } > "$readme_abs"
                echo "created README: ${dir_rel}/README.md"
                CREATED_READMES=$((CREATED_READMES + 1))
            fi
        else
            if [[ $DRY_RUN -eq 1 ]]; then
                echo "[dry-run] skip (exists) README: ${dir_rel}/README.md"
            fi
            SKIPPED=$((SKIPPED + 1))
        fi
    fi

done <<< "$ENTRIES"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

if [[ $DRY_RUN -eq 1 ]]; then
    echo "[dry-run] done — no files were created"
else
    echo "scaffold complete: ${CREATED_DIRS} dir(s) created, ${CREATED_READMES} README(s) created, ${SKIPPED} already-present item(s) skipped"
fi
