#!/usr/bin/env bash
# Purpose: Parse the ## Acceptance Criteria oracle table from a plan file and gate on gate-bound rows.
# Spec: archive/specs/2026-05-24-acceptance-oracle-with-teeth.md §2.1 §2.3 §Task 2
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
# Per-repo test-runner resolution
# ---------------------------------------------------------------------------
# The pytest/node/cargo handlers run a per-row selector against the repo's test
# suite. Repos that mandate a test wrapper (venv activation, editable install,
# marker deselect, console-popup suppression) cannot use the bare language
# runner — bare `pytest` collects under the ambient interpreter and reports a
# false red even when the work is green. We resolve a per-repo invoker,
# defaulting to the bare runner so no repo regresses.
#
# Precedence (mirrors lib/coordinator-resolve-validation-cmd.sh):
#   1. $COORDINATOR_<RUNNER>_CMD env var (one-off / CI override)
#   2. <runner>_cmd: key in the plan-repo's coordinator.local.md frontmatter
#   3. default: the bare language runner ("pytest", "node --test", "cargo test")
#
# The resolved command receives the per-row "$args" appended, so it MUST accept
# the language's native test-selector args. This is a SEPARATE key from
# fast_test_cmd (which is run verbatim with NO appended args) — a fast_test_cmd
# like `python run-all-checks.py` cannot take a pytest node-id, so conflating the
# two would be a footgun. A repo whose fast-test is an arg-accepting pytest
# wrapper may point both keys at the same command.

# Repo root for the plan under test (for coordinator.local.md lookup).
# PLAN_PATH is already absolute here (realpath applied above when available).
PLAN_DIR="$(dirname "$PLAN_PATH")"
REPO_ROOT="$PLAN_DIR"
if git -C "$PLAN_DIR" rev-parse --show-toplevel >/dev/null 2>&1; then
    REPO_ROOT="$(git -C "$PLAN_DIR" rev-parse --show-toplevel)"
fi

# resolve_runner_cmd <frontmatter-key> <env-var-name> <default-cmd>
# Echo the resolved command string. Frontmatter parse shape matches
# lib/coordinator-resolve-validation-cmd.sh (awk frontmatter block + grep key).
resolve_runner_cmd() {
    local key="$1" env_name="$2" default_cmd="$3"
    # Defensive: keys are literal [a-z_] identifiers at all call sites. Reject
    # anything else so $key can never inject regex metacharacters into the
    # grep/sed patterns below.
    if [[ ! "$key" =~ ^[a-z_]+$ ]]; then
        printf '%s' "$default_cmd"
        return 0
    fi
    # Defensive: env_name is a literal COORDINATOR_*_CMD constant at every call
    # site. Enforce that structurally before the indirect expansion below, so the
    # safety constraint does not depend solely on call-site discipline.
    if [[ ! "$env_name" =~ ^COORDINATOR_[A-Z_]+$ ]]; then
        printf '%s' "$default_cmd"
        return 0
    fi
    # Step 1 — env var. Indirect expansion (name validated above). Safe under
    # set -u via :-.
    local env_val="${!env_name:-}"
    if [[ -n "$env_val" ]]; then
        echo "[check-acceptance-oracle] ${key}: step=env-var" >&2
        printf '%s' "$env_val"
        return 0
    fi
    # Step 2 — coordinator.local.md frontmatter key
    local local_md="$REPO_ROOT/coordinator.local.md"
    if [[ -f "$local_md" ]]; then
        local fm val
        fm=$(awk '/^---$/{n++; if (n==2) exit; next} n==1' "$local_md" 2>/dev/null)
        val=$(echo "$fm" | grep -m1 "^${key}:" \
            | sed -E "s/^${key}:[[:space:]]*//" \
            | tr -d '"' | tr -d "'" \
            | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')
        if [[ -n "$val" ]]; then
            echo "[check-acceptance-oracle] ${key}: step=local-md ($local_md)" >&2
            printf '%s' "$val"
            return 0
        fi
    fi
    # Step 3 — default (no diagnostic; the bare-runner default is the common case)
    printf '%s' "$default_cmd"
}

# run_typed_test <runner-cmd> <args-string>
# Word-split both via `read -ra` into arrays; expanded double-quoted as
# "${arr[@]}" they undergo no further word-splitting or glob/command
# substitution — unlike the prior unquoted `pytest $args` (which glob-expanded
# $args). Run with combined stdout+stderr captured. On failure, echo a
# " — last output: <tail>" suffix to stdout and return the command's exit code.
# Empty suffix on success.
run_typed_test() {
    local runner="$1" arg_str="$2"
    local -a cmd_arr args_arr
    read -ra cmd_arr <<< "$runner" || true
    read -ra args_arr <<< "$arg_str" || true
    local out_file rc out_tail
    out_file="$(mktemp)" || return 1
    # RETURN trap cleans up on every exit path, including a signal-interrupted
    # run at the interactive /merging-to-main gate (Ctrl-C during a slow suite).
    trap 'rm -f "$out_file"' RETURN
    # Combined stdout+stderr: pytest writes failure bodies to stdout and
    # collection/import errors to stderr — surfacing only one loses the signal.
    "${cmd_arr[@]}" "${args_arr[@]+"${args_arr[@]}"}" >"$out_file" 2>&1 && rc=0 || rc=$?
    if (( rc != 0 )); then
        # Bound the surfaced tail: newlines→spaces, drop non-printable bytes,
        # collapse runs, cap length. Keeps a runaway test log (or control chars)
        # from bloating/corrupting the red-message line.
        out_tail="$(tail -n 3 "$out_file" 2>/dev/null | tr '\n' ' ' | tr -cd '[:print:]' | sed -E 's/[[:space:]]+/ /g; s/^[[:space:]]+//; s/[[:space:]]+$//' | head -c 200)"
        [[ -n "$out_tail" ]] && printf ' — last output: %s' "$out_tail"
    fi
    return $rc
}

PYTEST_CMD="$(resolve_runner_cmd pytest_cmd COORDINATOR_PYTEST_CMD 'pytest')"
NODE_CMD="$(resolve_runner_cmd node_cmd COORDINATOR_NODE_CMD 'node --test')"
CARGO_CMD="$(resolve_runner_cmd cargo_cmd COORDINATOR_CARGO_CMD 'cargo test')"

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
            cell_lower="$(printf '%s' "$cell" | tr '[:upper:]' '[:lower:]')"
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
    row_class_lower="$(printf '%s' "$row_class" | tr '[:upper:]' '[:lower:]')"

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

            # Trim whitespace from the pattern symmetrically with the path side
            # (trimmed below at the per-path loop). A row written `grep: pat @path`
            # otherwise carries leading/trailing spaces into the pattern, silently
            # breaking line-anchored or exact matches.
            pattern="${pattern#"${pattern%%[![:space:]]*}"}"
            pattern="${pattern%"${pattern##*[![:space:]]}"}"

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
            # pytest:<path>::<nodeid>  — invoker resolved via $PYTEST_CMD (default: pytest)
            args="${row_test#pytest:}"
            if err_suffix="$(run_typed_test "$PYTEST_CMD" "$args")"; then
                (( green++ )) || true
            else
                red_messages+=("AC-${row_id} (${row_test}) red — '${PYTEST_CMD}' exited non-zero${err_suffix}")
                (( red++ )) || true
            fi
            ;;

        node)
            # node:<path> -t <name>  — invoker resolved via $NODE_CMD (default: node --test)
            args="${row_test#node:}"
            if err_suffix="$(run_typed_test "$NODE_CMD" "$args")"; then
                (( green++ )) || true
            else
                red_messages+=("AC-${row_id} (${row_test}) red — '${NODE_CMD}' exited non-zero${err_suffix}")
                (( red++ )) || true
            fi
            ;;

        cargo)
            # cargo:<module>::<test>  — invoker resolved via $CARGO_CMD (default: cargo test)
            # Word-split matches pytest/node; cargo's documented <module>::<test>
            # form has no spaces, so this is identical to the prior quoted "$args".
            args="${row_test#cargo:}"
            if err_suffix="$(run_typed_test "$CARGO_CMD" "$args")"; then
                (( green++ )) || true
            else
                red_messages+=("AC-${row_id} (${row_test}) red — '${CARGO_CMD}' exited non-zero${err_suffix}")
                (( red++ )) || true
            fi
            ;;

        sh|bash)
            # sh:<script-path> [args...]  — run the named script with bash.
            # bash: is an alias for sh: — both use the same dispatch path.
            # Exit 0 → PASS; non-zero → FAIL. Matches the run_typed_test idiom of
            # sibling prefixes; no per-repo runner resolution (bash is the runner).
            # The script path and any arguments are word-split by run_typed_test
            # (same as pytest/node/cargo) and passed to bash as positional args.
            args="${row_test#*:}"
            # trim leading whitespace (mirrors grep/cited whitespace trimming above)
            args="${args#"${args%%[![:space:]]*}"}"
            # Review: security-audit — path-validation guard: reject absolute paths,
            # path-traversal sequences, and non-existent files before dispatching to bash.
            # Accepts repo-relative paths only (e.g. plugins/foo/bar.sh [--flag]).
            _sh_script_path="${args%% *}"
            if [[ "$_sh_script_path" == *..* ]]; then
                red_messages+=("AC-${row_id} (${row_test}) red — script path rejected: contains '..' (path traversal not allowed)")
                (( red++ )) || true
            elif [[ "$_sh_script_path" == /* ]]; then
                red_messages+=("AC-${row_id} (${row_test}) red — script path rejected: absolute path not allowed (use repo-relative path)")
                (( red++ )) || true
            elif [[ ! -f "$_sh_script_path" ]]; then
                red_messages+=("AC-${row_id} (${row_test}) red — script path rejected: '${_sh_script_path}' is not an existing regular file")
                (( red++ )) || true
            elif err_suffix="$(run_typed_test "bash" "$args")"; then
                (( green++ )) || true
            else
                red_messages+=("AC-${row_id} (${row_test}) red — 'bash' exited non-zero${err_suffix}")
                (( red++ )) || true
            fi
            unset _sh_script_path
            ;;

        *)
            red_messages+=("AC-${row_id} (${row_test}) red — unknown typed prefix '${prefix}': supported prefixes are pytest, node, cargo, grep, cited, sh, bash")
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
