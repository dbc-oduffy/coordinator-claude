#!/usr/bin/env bash
# Purpose: Parse the ## Acceptance Criteria oracle table from a plan file and gate on gate-bound rows.
# Spec: docs/plans/2026-05-24-acceptance-oracle-with-teeth.md §2.1 §2.3 §Task 2
#
# Concurrency / idempotency / resume: this script is read-only against the plan and test suite;
# it has no side-effects, is idempotent, and is safe to run concurrently across sessions.
#
# Exit-code contract (TEETH): non-zero iff any gate-bound row is red or missing/uncited.
# Message contract  (CARROT): lead with state, never blame; summary line format:
#   "<G>/<N> gate-bound acceptance tests green; <R> red; <S> skipped (reviewer-judgment)"

set -euo pipefail

# ---------------------------------------------------------------------------
# Override env var — skip gate entirely (AC-11, §2.3)
# ---------------------------------------------------------------------------
if [[ "${COORDINATOR_OVERRIDE_ACCEPTANCE_GATE:-}" == "1" ]]; then
    echo "[override active: COORDINATOR_OVERRIDE_ACCEPTANCE_GATE=1] gate skipped"
    exit 0
fi

# ---------------------------------------------------------------------------
# Argument handling
# ---------------------------------------------------------------------------
if [[ $# -lt 1 ]]; then
    echo "Usage: check-acceptance-oracle.sh <plan-path>" >&2
    exit 1
fi

PLAN_PATH="$1"

# Resolve to an absolute path if possible (portable: realpath may not exist on all platforms)
if command -v realpath >/dev/null 2>&1; then
    PLAN_PATH="$(realpath "$PLAN_PATH")"
fi

if [[ ! -f "$PLAN_PATH" ]]; then
    echo "check-acceptance-oracle.sh: plan file not found: $PLAN_PATH" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Locate the ## Acceptance Criteria section and extract the table
# ---------------------------------------------------------------------------
# We read the plan file, find the ## Acceptance Criteria heading, then collect
# lines until the next ## heading (or end of file).

section_lines=()
in_section=0
found_section=0

while IFS= read -r line; do
    if [[ "$line" =~ ^##[[:space:]]+Acceptance[[:space:]]+Criteria ]]; then
        in_section=1
        found_section=1
        continue
    fi
    if [[ $in_section -eq 1 ]]; then
        # Stop at the next ## heading
        if [[ "$line" =~ ^##[[:space:]] ]]; then
            break
        fi
        section_lines+=("$line")
    fi
done < "$PLAN_PATH"

# ---------------------------------------------------------------------------
# Check that a bindable table exists (has Binding-Class column header)
# ---------------------------------------------------------------------------
has_bindable_table=0
for line in "${section_lines[@]+"${section_lines[@]}"}"; do
    if echo "$line" | grep -qi "Binding-Class\|Binding.Class"; then
        has_bindable_table=1
        break
    fi
done

if [[ $found_section -eq 0 ]] || [[ $has_bindable_table -eq 0 ]]; then
    echo "no acceptance oracle in $PLAN_PATH; skipping gate"
    echo "(offer: add a bindable ## Acceptance Criteria table — see docs/wiki/writing-plans.md § Acceptance Oracle)"
    exit 0
fi

# ---------------------------------------------------------------------------
# Parse table rows — columns: ID | Criterion | Test | Binding-Class | Status
# We split on '|' and trim whitespace from each cell.
# ---------------------------------------------------------------------------

# Identify column positions from the header row
header_id_col=-1
header_test_col=-1
header_class_col=-1
header_found=0

parse_pipe_row() {
    # Given a pipe-delimited table row, echo each trimmed cell on its own line
    # prefixed with its 0-based column index "N:cell".
    # Strips markdown backtick wrappers from cell values (e.g. `grep:foo` → grep:foo).
    local row="$1"
    # Strip leading/trailing pipes
    row="${row#|}"
    row="${row%|}"
    local idx=0
    # Convert '|' to newlines so each cell lands on its own line, then read them.
    while IFS= read -r cell; do
        # trim leading/trailing whitespace
        cell="${cell#"${cell%%[![:space:]]*}"}"
        cell="${cell%"${cell##*[![:space:]]}"}"
        # strip markdown backtick wrappers: `value` → value
        if [[ "$cell" == \`*\` ]]; then
            cell="${cell#\`}"
            cell="${cell%\`}"
        fi
        echo "${idx}:${cell}"
        (( idx++ )) || true
    done < <(printf '%s' "$row" | tr '|' '\n')
}

# Discover column indices from the header row
for line in "${section_lines[@]+"${section_lines[@]}"}"; do
    # Identify header row: must contain both "ID" and "Binding" columns
    if echo "$line" | grep -q "|" && echo "$line" | grep -qi "Binding"; then
        header_found=1
        while IFS= read -r cell_entry; do
            idx="${cell_entry%%:*}"
            cell="${cell_entry#*:}"
            cell_lower="${cell,,}"
            if [[ "$cell_lower" == "id" ]]; then
                header_id_col=$idx
            elif echo "$cell_lower" | grep -q "^test"; then
                header_test_col=$idx
            elif echo "$cell_lower" | grep -q "binding"; then
                header_class_col=$idx
            fi
        done < <(parse_pipe_row "$line")
        break
    fi
done

if [[ $header_found -eq 0 ]]; then
    echo "no acceptance oracle in $PLAN_PATH; skipping gate"
    echo "(offer: table found but no header with Binding-Class column)"
    exit 0
fi

# ---------------------------------------------------------------------------
# Process data rows
# ---------------------------------------------------------------------------
green=0
red=0
skipped=0
total_gate_bound=0
red_messages=()

parsing_rows=0
for line in "${section_lines[@]+"${section_lines[@]}"}"; do
    # Skip blank lines and HTML comments
    [[ -z "$line" ]] && continue
    echo "$line" | grep -q "^<!--" && continue

    # Only process pipe-table rows
    if ! echo "$line" | grep -q "^|"; then
        continue
    fi

    # Skip the header row (contains "Binding") and separator rows (contain ---)
    if echo "$line" | grep -qi "Binding"; then
        parsing_rows=1
        continue
    fi
    if echo "$line" | grep -q -- "---"; then
        continue
    fi

    # Skip if we haven't seen the header yet
    [[ $parsing_rows -eq 0 ]] && continue

    # Extract cells
    row_id=""
    row_test=""
    row_class=""

    while IFS= read -r cell_entry; do
        idx="${cell_entry%%:*}"
        cell="${cell_entry#*:}"
        if [[ $idx -eq $header_id_col ]]; then
            row_id="$cell"
        elif [[ $idx -eq $header_test_col ]]; then
            row_test="$cell"
        elif [[ $idx -eq $header_class_col ]]; then
            row_class="$cell"
        fi
    done < <(parse_pipe_row "$line")

    # Normalize class to lowercase for comparison
    row_class_lower="${row_class,,}"

    # Skip rows where binding class is reviewer-judgment
    if echo "$row_class_lower" | grep -q "reviewer"; then
        (( skipped++ )) || true
        continue
    fi

    # Gate-bound row
    (( total_gate_bound++ )) || true

    # Handle "pending realization" — always red
    if echo "$row_test" | grep -qi "pending.realization"; then
        red_messages+=("AC-${row_id} (${row_test}) red — test not yet realized (pending realization)")
        (( red++ )) || true
        continue
    fi

    # Dispatch on typed prefix
    prefix="${row_test%%:*}"

    case "$prefix" in

        grep)
            # grep:pattern@path1[,path2...]
            rest="${row_test#grep:}"
            pattern="${rest%%@*}"
            paths_str="${rest#*@}"

            # Split paths on comma
            IFS=',' read -ra paths_arr <<< "$paths_str"

            row_result="green"
            failing_path=""
            for p in "${paths_arr[@]}"; do
                # trim whitespace
                p="${p#"${p%%[![:space:]]*}"}"
                p="${p%"${p##*[![:space:]]}"}"
                if ! grep -q "$pattern" "$p" 2>/dev/null; then
                    row_result="red"
                    failing_path="$p"
                    break
                fi
            done

            if [[ "$row_result" == "green" ]]; then
                (( green++ )) || true
            else
                if [[ ${#paths_arr[@]} -gt 1 ]]; then
                    red_messages+=("AC-${row_id} (${row_test}) red — all-must-match: no match for pattern '${pattern}' in ${failing_path}")
                else
                    red_messages+=("AC-${row_id} (${row_test}) red — no match for pattern '${pattern}' in ${paths_str}")
                fi
                (( red++ )) || true
            fi
            ;;

        cited)
            # cited:<ref> — validates the cited ref resolves: 40-char SHA → git cat-file -e; else file path → -f check.
            ref="${row_test#cited:}"
            # trim whitespace
            ref="${ref#"${ref%%[![:space:]]*}"}"
            ref="${ref%"${ref##*[![:space:]]}"}"

            if [[ ${#ref} -eq 40 ]] && echo "$ref" | grep -qE '^[0-9a-fA-F]{40}$'; then
                # Treat as git commit SHA
                if git -C "$(dirname "$PLAN_PATH")" cat-file -e "$ref" 2>/dev/null; then
                    echo "AC-${row_id} satisfied by citation ${ref} — NOT re-run on this host" >&2
                    (( green++ )) || true
                else
                    red_messages+=("AC-${row_id} (${row_test}) red — ref does not resolve: git SHA '${ref}' not found in local history")
                    (( red++ )) || true
                fi
            else
                # Treat as file path
                if [[ -f "$ref" ]]; then
                    echo "AC-${row_id} satisfied by citation ${ref} — NOT re-run on this host" >&2
                    (( green++ )) || true
                else
                    red_messages+=("AC-${row_id} (${row_test}) red — ref does not resolve: file path '${ref}' not found on disk")
                    (( red++ )) || true
                fi
            fi
            ;;

        pytest)
            # pytest:<path>::<nodeid>
            args="${row_test#pytest:}"
            if pytest $args 2>/dev/null; then
                (( green++ )) || true
            else
                red_messages+=("AC-${row_id} (${row_test}) red — pytest exited non-zero")
                (( red++ )) || true
            fi
            ;;

        node)
            # node:<path> -t <name>
            args="${row_test#node:}"
            if node --test $args 2>/dev/null; then
                (( green++ )) || true
            else
                red_messages+=("AC-${row_id} (${row_test}) red — node --test exited non-zero")
                (( red++ )) || true
            fi
            ;;

        cargo)
            # cargo:<module>::<test>
            args="${row_test#cargo:}"
            if cargo test "$args" 2>/dev/null; then
                (( green++ )) || true
            else
                red_messages+=("AC-${row_id} (${row_test}) red — cargo test exited non-zero")
                (( red++ )) || true
            fi
            ;;

        *)
            red_messages+=("AC-${row_id} (${row_test}) red — unknown typed prefix '${prefix}': supported prefixes are pytest, node, cargo, grep, cited")
            (( red++ )) || true
            ;;
    esac

done

# ---------------------------------------------------------------------------
# Emit per-red messages
# ---------------------------------------------------------------------------
for msg in "${red_messages[@]+"${red_messages[@]}"}"; do
    echo "$msg"
done

# ---------------------------------------------------------------------------
# Final summary (CARROT — lead with state)
# ---------------------------------------------------------------------------
echo "${green}/${total_gate_bound} gate-bound acceptance tests green; ${red} red; ${skipped} skipped (reviewer-judgment)"

# ---------------------------------------------------------------------------
# Exit code (TEETH — strictly orthogonal to message tone)
# ---------------------------------------------------------------------------
if [[ $red -gt 0 ]]; then
    exit 1
fi
exit 0
