#!/usr/bin/env bash
# Purpose: Parse one completeness-checklist item into {class, assertion, probe} and emit
# structured output. Single source of parse+classify for the pickup skill (C4) and the
# bats test suite (C9) — round-trip-contract-tests doctrine.
#
# Spec backlink: docs/plans/2026-06-24-install-baton-completeness-claude-code-validation.md § C3
#
# Grammar (pinned):
#   <class>: <assertion text> [probe: <shell-command>]
#   - <class> in {live, restart-gated}. Anything else → malformed → exit non-zero.
#   - [probe: ...] is optional. Everything between "probe: " and the FINAL unescaped "]"
#     is the command verbatim. A literal trailing "]" inside the command is escaped as "\]".
#   - A missing "<class>:" prefix, an empty assertion, or an unterminated "[probe:" → malformed.
#
# Usage:
#   parse-completeness-item.sh '<item string>'   (reads from $1)
#   echo '<item string>' | parse-completeness-item.sh  (reads from stdin when $1 absent)
#
# Output (stdout, three lines):
#   class=<live|restart-gated>
#   assertion=<text>
#   probe=<command>      (or "probe=" when no probe)
#
# Exit codes:
#   0  — success
#   1  — malformed input (message on stderr)
#
# Negative-spec: does NOT execute the probe command; does NOT read from files; no side effects.
# Bash-3.2 safe: no declare -A, no ${v^^}, no mapfile, no [[ =~ ]] with capture groups stored
# in BASH_REMATCH beyond what 3.2 supports (we avoid =~ entirely; use case/expr/parameter ops).

set -euo pipefail

# ---------------------------------------------------------------------------
# Read input: $1 or stdin
# ---------------------------------------------------------------------------
if [ $# -ge 1 ]; then
    item="$1"
else
    # Read all of stdin into a single string (handles piped input).
    # Review: code-reviewer F8 — skip blank lines before the item is set (handles the
    # trailing newline that `echo` appends: "echo 'live: foo'" produces two read iterations:
    # first with "live: foo", second with "" — without the skip the second iteration was
    # treated as a second content line and triggered a false multi-line error).
    # After item is set, only additional NON-empty lines trigger the multi-line error.
    item=""
    while IFS= read -r line; do
        if [ -z "$line" ]; then
            # Blank line: skip pre-content blanks; ignore trailing-newline artifacts post-content.
            continue
        fi
        if [ -n "$item" ]; then
            # Multi-line input is malformed — items are single strings
            printf 'parse-completeness-item: malformed item: multi-line input not supported\n' >&2
            exit 1
        fi
        item="$line"
    done
fi

if [ -z "$item" ]; then
    printf 'parse-completeness-item: malformed item: empty input\n' >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Extract <class>: prefix
# ---------------------------------------------------------------------------
# item must start with "live: " or "restart-gated: " — check both.
item_class=""
item_rest=""

case "$item" in
    live:\ *)
        item_class="live"
        item_rest="${item#live: }"
        ;;
    restart-gated:\ *)
        item_class="restart-gated"
        item_rest="${item#restart-gated: }"
        ;;
    live:|restart-gated:)
        # Class present but no space+content after colon → empty assertion
        printf 'parse-completeness-item: malformed item: empty assertion (nothing after class prefix): %s\n' "$item" >&2
        exit 1
        ;;
    *:\ *|*:*)
        # Has a colon but an unrecognised class
        # Extract what's before the first colon for the error message
        bad_class="${item%%:*}"
        printf 'parse-completeness-item: malformed item: unknown class "%s" (must be "live" or "restart-gated"): %s\n' "$bad_class" "$item" >&2
        exit 1
        ;;
    *)
        printf 'parse-completeness-item: malformed item: missing "<class>: " prefix: %s\n' "$item" >&2
        exit 1
        ;;
esac

if [ -z "$item_rest" ]; then
    printf 'parse-completeness-item: malformed item: empty assertion after class prefix: %s\n' "$item" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Extract optional [probe: <cmd>] suffix
#
# Strategy (bash-3.2 safe, no regex engine):
#   The probe suffix, if present, starts with " [probe: " and ends at the FINAL
#   unescaped "]" in the string. We find the probe open-bracket by looking for
#   " [probe: " as a substring, then find the final "]" by walking from the right
#   and skipping "\]" escape sequences.
#
#   We use parameter expansion to split on the first occurrence of " [probe: ".
# ---------------------------------------------------------------------------
item_assertion=""
item_probe=""

# Does item_rest contain " [probe: " at all?
# Parameter expansion: if ${item_rest#*" [probe: "} differs from item_rest, the needle is present.
remainder_after_probe_open="${item_rest#*" [probe: "}"

if [ "$remainder_after_probe_open" = "$item_rest" ]; then
    # No probe suffix present.
    # Review: code-reviewer — strip trailing whitespace so YAML values with
    # incidental trailing spaces don't embed spaces in the emitted assertion= line.
    # Bash-3.2 safe: use case to detect a trailing space or tab, then ${var%?} to
    # peel one char at a time until the last char is neither space nor tab.
    item_assertion="$item_rest"
    while true; do
        case "$item_assertion" in
            *" "|*"	")
                item_assertion="${item_assertion%?}"
                ;;
            *)
                break
                ;;
        esac
    done
    item_probe=""
else
    # Split: everything before " [probe: " is the assertion; remainder_after_probe_open
    # is the content between "probe: " and the end, which must terminate with an
    # unescaped "]".

    # Assertion = item_rest up to (but not including) " [probe: "
    # We compute it as: item_rest with the " [probe: <rest>" suffix stripped.
    # The suffix is " [probe: " + remainder_after_probe_open
    probe_suffix=" [probe: ${remainder_after_probe_open}"
    item_assertion="${item_rest%"$probe_suffix"}"

    if [ -z "$item_assertion" ]; then
        printf 'parse-completeness-item: malformed item: empty assertion (probe present but assertion is empty): %s\n' "$item" >&2
        exit 1
    fi

    # remainder_after_probe_open must end with an unescaped "]"
    # Find the final unescaped "]" by scanning from the right.
    # We do this in pure bash-3.2 string ops: strip trailing content after last "]".
    #
    # Method: strip the shortest suffix that starts with "]" — that gives us everything
    # before the LAST "]". If the string doesn't end with "]" at all, it's unterminated.
    #
    # But we must also handle escaped "\]" inside. The rule: the FINAL character sequence
    # "\]" does NOT count as the closing delimiter; a bare "]" does.
    #
    # Algorithm:
    #   1. Check that remainder_after_probe_open ends with "]" (using case match).
    #   2. Check it doesn't end with "\]" (i.e., the final "]" is escaped).
    #   3. Strip the trailing "]" to get the raw command.
    #   4. Unescape any "\]" sequences inside the command to literal "]".

    # Step 1: does it end with "]"?
    case "$remainder_after_probe_open" in
        *"]")
            : # ok, ends with ]
            ;;
        *)
            printf 'parse-completeness-item: malformed item: unterminated [probe: (no closing "]"): %s\n' "$item" >&2
            exit 1
            ;;
    esac

    # Step 2: does it end with "\]" (escaped)?
    # If the string ends with "\]", the final ] is escaped — look for an earlier unescaped one.
    # We handle this by iteratively stripping trailing "\]" and checking for a bare "]".
    # In practice, the spec says the FINAL ] is the delimiter; \] inside is an escape.
    # So: strip the last char (the "]"), check if the character before it is "\".
    # If yes, the last ] was escaped — the probe is unterminated (no unescaped final ]).
    #
    # More precisely: find the last unescaped ] by peeling from the right.
    # We build a loop that strips one char at a time from the right until we find a ] not
    # preceded by \.
    #
    # Implementation: use a recursive-stripping approach with string ops.
    # We know the string ends with "]". Check what precedes it.

    probe_raw_content=""
    probe_scan="$remainder_after_probe_open"

    # Peel from the right: the last char is "]". What's before it?
    while true; do
        # probe_scan ends with "]" (we checked or stripped to this state)
        # Strip the trailing "]"
        without_close="${probe_scan%"]"}"

        # Does without_close end with "\"? (i.e., the ] we stripped was escaped)
        case "$without_close" in
            *"\\")
                # The ] was escaped. This inner ] is not the real delimiter.
                # We need to continue searching leftward — but wait, the spec says
                # the FINAL ] is the delimiter even if it appears escaped by a backslash?
                # Re-read spec: "the final ] is the delimiter; a literal trailing ] inside
                # the command is escaped as \]". So \] INSIDE the command is an escaped
                # literal. The closing ] is the FINAL UNESCAPED ] in the string.
                # That means: if the string ends with \], the closing ] is elsewhere (error).
                # If the string ends with ], and the char before it is not \, it's the close.
                # If the string ends with \], walk left to find the actual unescaped ].
                # But the string MUST end with an unescaped ] to be well-formed.
                # Since the string we have ends with ] (checked), and that ] is preceded by \,
                # it IS escaped — so the string has no unescaped trailing ]; it's unterminated.
                #
                # However: consider "cmd \] more ]" — this ends with "] " no wait, ends with "]".
                # The LAST char is ]. What precedes it is " " (a space), not \. So it's unescaped.
                # We only have a problem if the very last char before "]" is "\".
                #
                # Walk further left: strip this "\]" pair and check if there's another ].
                # Actually, the simplest correct approach: the FINAL ] that is NOT preceded
                # by a \ is the closing delimiter. We peel from the right.

                # Strip the trailing "\]" (escaped bracket) and continue searching.
                # without_close already has the ] stripped; now strip the trailing \
                probe_scan="${without_close%"\\"}"
                # Now check if probe_scan still contains a ] to be the close bracket.
                case "$probe_scan" in
                    *"]")
                        # There's still a ] further left — loop to check it
                        continue
                        ;;
                    *)
                        # No more ] to the left — unterminated
                        printf 'parse-completeness-item: malformed item: unterminated [probe: (all "]" are escaped): %s\n' "$item" >&2
                        exit 1
                        ;;
                esac
                ;;
            *)
                # The final ] was NOT preceded by \ — this is the closing delimiter.
                probe_raw_content="$without_close"
                break
                ;;
        esac
    done

    # Review: code-reviewer — removed dead found_close guard. The while-true loop's
    # only non-exit paths are: (a) break at found_close=1 or (b) exit 1 inside the loop.
    # So post-loop, found_close is always 1 — the guard was unreachable.

    if [ -z "$probe_raw_content" ]; then
        printf 'parse-completeness-item: malformed item: empty probe command in [probe: ]: %s\n' "$item" >&2
        exit 1
    fi

    # Unescape \] → ] inside the probe command
    # Pure bash-3.2 safe: use parameter expansion to replace \] with ]
    # bash 3.2 supports ${var//pattern/replacement} for global substitution.
    item_probe="${probe_raw_content//'\]'/']'}"
fi

# ---------------------------------------------------------------------------
# Validate assertion is not empty (belt-and-suspenders, already checked above)
# ---------------------------------------------------------------------------
if [ -z "$item_assertion" ]; then
    printf 'parse-completeness-item: malformed item: empty assertion: %s\n' "$item" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Emit structured output
# ---------------------------------------------------------------------------
printf 'class=%s\n' "$item_class"
printf 'assertion=%s\n' "$item_assertion"
printf 'probe=%s\n' "$item_probe"
