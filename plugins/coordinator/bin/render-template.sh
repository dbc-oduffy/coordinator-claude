#!/usr/bin/env bash
# bin/render-template.sh — narrow Mustache-style template renderer
#
# Purpose: substitute literal {{KEY}} tokens in a template file with
# caller-supplied KEY=VALUE pairs. Fails loudly on any unsubstituted
# {{KEY}} remaining after render; rejects keys with whitespace inside
# braces by treating them as unsubstituted.
#
# Spec backlink: docs/plans/2026-05-19-coordinator-installer-redesign-implementation.md § C1 (D3.b)
#
# Negative-spec: NO conditionals, NO loops, NO includes, NO defaults,
# NO escaping of braces, NO whitespace tolerance inside {{ }}. Any such
# feature request belongs in a different tool.
#
# Usage:
#   bin/render-template.sh <template-path> [-o <output-path>] [KEY=VALUE]...
#
# Arguments:
#   <template-path>   Path to the template file containing {{KEY}} tokens.
#   -o <output-path>  Optional. Write rendered output to <output-path>
#                     atomically (render to tempfile, mv to target).
#                     Without -o, rendered output goes to stdout.
#   KEY=VALUE         Zero or more substitution pairs. KEY must be a
#                     bare identifier (no whitespace). VALUE may be any
#                     string; it is treated as a literal replacement.
#
# Exit codes:
#   0  All {{KEY}} tokens were substituted; output written successfully.
#   1  One or more {{KEY}} tokens remain unsubstituted after render, OR
#      template file is not readable, OR output path is not writable.
#
# Error output:
#   Unsubstituted keys → stderr:
#     render-template: unsubstituted keys: KEY1, KEY2 in <template-path>

set -euo pipefail

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

if [[ $# -lt 1 ]]; then
    echo "usage: render-template.sh <template-path> [-o <output-path>] [KEY=VALUE]..." >&2
    exit 1
fi

template_path="$1"
shift

output_path=""
declare -a kv_pairs=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        -o)
            if [[ $# -lt 2 ]]; then
                echo "render-template: -o requires an argument" >&2
                exit 1
            fi
            output_path="$2"
            shift 2
            ;;
        *=*)
            kv_pairs+=("$1")
            shift
            ;;
        *)
            echo "render-template: unexpected argument: $1" >&2
            exit 1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Read template
# ---------------------------------------------------------------------------

if [[ ! -r "$template_path" ]]; then
    echo "render-template: cannot read template: $template_path" >&2
    exit 1
fi

# Read template preserving trailing newlines (command substitution would strip them)
IFS= read -r -d '' rendered < "$template_path" || true

# ---------------------------------------------------------------------------
# Apply substitutions
# ---------------------------------------------------------------------------
# Each KEY=VALUE pair replaces every occurrence of {{KEY}} literally.
# sed's delimiter is | to avoid conflicts with typical path values.
# The pattern {{KEY}} requires exactly no whitespace inside the braces —
# so {{ KEY }} is left untouched, and will trip the unsubstituted-key check.

for pair in "${kv_pairs[@]}"; do
    key="${pair%%=*}"
    value="${pair#*=}"
    # Validate key is a bare identifier — guards against sed metacharacter injection
    if ! [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
        echo "render-template: invalid key: $key (must be a bare identifier)" >&2
        exit 1
    fi
    # Escape sed replacement string: & \ newline (POSIX BRE safe)
    escaped_value="$(printf '%s\n' "$value" | sed 's|[&\\]|\\&|g; s|$|\\|; $s|\\$||')"
    # Apply substitution via temp file to preserve trailing newlines.
    # Write through a second tempfile rather than `sed -i`: BSD/macOS sed
    # requires a backup-suffix argument immediately after -i, so `sed -i SCRIPT`
    # consumes the script as the suffix and misreads the file path as the
    # script. GNU sed tolerates a bare -i, which is why this only bit on Mac.
    tmp_sed="$(mktemp)"
    tmp_out="$(mktemp)"
    printf '%s' "$rendered" > "$tmp_sed"
    sed "s|{{${key}}}|${escaped_value}|g" "$tmp_sed" > "$tmp_out"
    IFS= read -r -d '' rendered < "$tmp_out" || true
    rm -f "$tmp_sed" "$tmp_out"
done

# ---------------------------------------------------------------------------
# Unsubstituted key detection
# ---------------------------------------------------------------------------
# Match {{ANYTHING}} where ANYTHING contains no whitespace — these are
# the only patterns our contract defines as substitutable. Patterns with
# whitespace inside ({{ FOO }}) are treated as literal text, and because
# no KEY=VALUE will have matched them, they remain in the output and are
# caught here identically.
#
# We use grep -oE to extract every remaining {{...}} token, then filter
# to those whose inner content is non-empty and whitespace-free (i.e.
# patterns that look like valid keys the caller forgot to supply).

unsubstituted=""
if printf '%s\n' "$rendered" | grep -qE '\{\{[^}]+\}\}'; then
    # Extract all {{...}} tokens still present
    raw_tokens="$(printf '%s\n' "$rendered" | grep -oE '\{\{[^}]+\}\}')"
    # Keep only those whose inner content has no whitespace — these are
    # the "should have been substituted" tokens. Tokens with whitespace
    # (e.g. {{ FOO }}) are also unsubstituted, and we report them too.
    unsubstituted="$(printf '%s\n' "$raw_tokens" | sed 's/^{{//; s/}}$//; s/^[[:space:]]*//; s/[[:space:]]*$//' | sort -u | tr '\n' ',' | sed 's/,$//')"
fi

if [[ -n "$unsubstituted" ]]; then
    echo "render-template: unsubstituted keys: ${unsubstituted} in ${template_path}" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

if [[ -n "$output_path" ]]; then
    # Atomic write: render to a tempfile in the same directory, then mv
    output_dir="$(dirname "$output_path")"
    if [[ ! -d "$output_dir" ]]; then
        echo "render-template: output directory does not exist: $output_dir" >&2
        exit 1
    fi
    tmp_file="$(mktemp "${output_dir}/.render-template.XXXXXX")"
    # Ensure tempfile is cleaned up on unexpected exit
    trap 'rm -f "$tmp_file"' EXIT
    printf '%s' "$rendered" > "$tmp_file"
    mv "$tmp_file" "$output_path"
    trap - EXIT  # $tmp_file no longer exists; disarm cleanup
else
    printf '%s' "$rendered"
fi

exit 0
