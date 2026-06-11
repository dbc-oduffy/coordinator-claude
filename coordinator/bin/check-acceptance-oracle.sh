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
# Parsing contract: markdown code-fence blocks (``` ... ```) are excluded; only content outside fences is parsed for AC rows.

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

# Review: F1 — portable absolute-path resolution with no subprocess dependency.
# `realpath` is GNU-specific (absent on macOS stock bash 3.2); the `case` form
# is POSIX-safe and avoids a subprocess entirely. The cd guard at ~89 already
# handles the remaining relative-path risk when REPO_ROOT comes from git rev-parse
# (which always produces an absolute path), but making PLAN_PATH absolute here
# removes that dependency on REPO_ROOT being set before first use.
case $PLAN_PATH in
    /*) ;;
    *) PLAN_PATH="$(cd "$(dirname "$PLAN_PATH")" && pwd)/$(basename "$PLAN_PATH")" ;;
esac

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
# Single rev-parse: capture output on success, fall through to PLAN_DIR on
# failure (code-reviewer F5 — was a double-call; one subprocess is enough).
PLAN_DIR="$(dirname "$PLAN_PATH")"
if REPO_ROOT="$(git -C "$PLAN_DIR" rev-parse --show-toplevel 2>/dev/null)"; then
    :
else
    REPO_ROOT="$PLAN_DIR"
fi

# Resolve all relative paths in AC rows (cited:, grep:, pytest:, sh:) against
# the plan's repo root, not the caller's cwd. Without this cd, an oracle run
# from a subdir cwd reports false reds on cited:/grep:/pytest: rows whose paths
# are written repo-root-relative (the canonical form). PLAN_PATH was made
# absolute above, so the cd is safe to perform here.
#
# Guard: only cd when PLAN_DIR is *genuinely* in a git repo. When the
# `git rev-parse --show-toplevel` above failed, REPO_ROOT fell through to
# PLAN_DIR (the plan's own directory). For plans outside any git repo
# (e.g. test fixtures synthesized in /tmp), cd'ing to PLAN_DIR would defeat
# the caller's intent — the caller's cwd is the correct resolution surface
# for repo-relative selectors. Detect the fallback by checking whether
# REPO_ROOT was set by the git rev-parse path: if PLAN_DIR is in a git repo,
# REPO_ROOT is the git toplevel; otherwise it equals PLAN_DIR and we skip.
if [[ "$REPO_ROOT" != "$PLAN_DIR" ]]; then
    # REPO_ROOT differs from PLAN_DIR only when the rev-parse above succeeded.
    # Code-reviewer F1: test the invariant directly (was re-running git rev-parse,
    # introducing a third subprocess + an undefined-contract gap if filesystem
    # state changed between calls).
    cd "$REPO_ROOT" || {
        echo "check-acceptance-oracle.sh: cannot cd to repo root '$REPO_ROOT'" >&2
        exit 1
    }
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
    # Optional third arg: prefix name (e.g. "pytest") — enables prefix-specific
    # diagnostic hints (Fix 5, 2026-06-09). Defaults to empty for back-compat
    # with any caller that still passes only two args.
    local runner="$1" arg_str="$2" prefix_name="${3:-}"
    local -a cmd_arr args_arr
    read -ra cmd_arr <<< "$runner" || true
    read -ra args_arr <<< "$arg_str" || true
    local out_file rc out_tail
    out_file="$(mktemp)" || return 1
    # Review: F3 — RETURN trap is not portable to bash 3.2 (stock macOS); it silently
    # no-ops, leaking the tmpfile. Replaced with explicit rm -f before each return path.
    # Combined stdout+stderr: pytest writes failure bodies to stdout and
    # collection/import errors to stderr — surfacing only one loses the signal.
    "${cmd_arr[@]}" "${args_arr[@]+"${args_arr[@]}"}" >"$out_file" 2>&1 && rc=0 || rc=$?
    if (( rc != 0 )); then
        # Bound the surfaced tail: newlines→spaces, drop non-printable bytes,
        # collapse runs, cap length. Keeps a runaway test log (or control chars)
        # from bloating/corrupting the red-message line.
        out_tail="$(tail -n 3 "$out_file" 2>/dev/null | tr '\n' ' ' | tr -cd '[:print:]' | sed -E 's/[[:space:]]+/ /g; s/^[[:space:]]+//; s/[[:space:]]+$//' | head -c 200)"
        [[ -n "$out_tail" ]] && printf ' — last output: %s' "$out_tail"
        # 0-collected hint (Fix 5, revised 2026-06-09 per project-rag-em decline of
        # the wrapper-bug premise): pytest reporting 0-collected on a 'path::nodeid'
        # selector most commonly means the *selector* is malformed, not that the
        # wrapper is broken. Class-scoped tests need 'path::ClassName::method';
        # plan authors often write 'path::method' (the bare-function form) for
        # tests that are actually class-bound. Wrapper-side bugs are also possible
        # but rarer; both bisect steps are surfaced.
        if [[ "$prefix_name" == "pytest" ]] && grep -q "collected 0 items" "$out_file" 2>/dev/null; then
            printf " — 0-collected hint: pytest reported 0 collected for the given selector. Most common cause is a class-scoped test written as 'path::method' — pytest needs 'path::ClassName::method' for class-bound tests. Bisect: (1) run 'bash <pytest_cmd> <path>' (bare path) — collects N → selector form is the issue; (2) run 'bash <pytest_cmd> <path> -k <method_substring>' — collects M → confirm the class name and rewrite the AC to 'path::ClassName::method'; (3) if (1) also collects 0, the per-repo pytest_cmd wrapper is rewriting argv (rarer)."
        fi
        rm -f "$out_file"
        return $rc
    fi
    rm -f "$out_file"
    return 0
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
in_fence=0

while IFS= read -r line; do
    # Track markdown code-fence state. A line starting with ``` (optionally
    # with a language tag) toggles in_fence. Inside a fence, no parsing fires —
    # headings and table rows are illustrative, not live. Without this guard,
    # any plan demonstrating AC table grammar inside a ```markdown code fence
    # would have the example rows parsed as live AC tests (2026-06-09 dogfood:
    # this skill's own plan tripped on it).
    # Simple toggle, not depth-counter — repo convention: no nested fences in plan bodies.
    if [[ "$line" =~ ^[[:space:]]*\`\`\` ]]; then
        in_fence=$((1 - in_fence))
        continue
    fi
    if [[ $in_fence -eq 1 ]]; then
        # Still check for section boundary even inside a fence.
        # Review: F8 — without this, a ## heading inside a fenced block within the AC
        # section never fires the section-stop break, causing post-fence content from
        # the next logical section to be wrongly appended to section_lines.
        if [[ $in_section -eq 1 ]] && [[ "$line" =~ ^##[[:space:]] ]]; then
            break
        fi
        continue
    fi
    # Case-insensitive header (2026-06-09): plan authors commonly write
    # sentence-case "## Acceptance criteria" — Title-Case-only made the
    # header miss-fire SILENT SKIP (worst class). Wiki convention stays
    # Title Case; sentence-case accepted, not promoted.
    if [[ "$line" =~ ^##[[:space:]]+[Aa]cceptance[[:space:]]+[Cc]riteria ]]; then
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
        # Defined-grammar tokenizer (2026-06-09): one of four accepted shapes,
        # else preserved as-is and rejected downstream by the unknown-prefix
        # arm OR diagnosed here with a tokenizer hint when we can recognize
        # the prefix but not the wrap.
        #
        # Accepted shapes (and ONLY these):
        #   S1 bare:                       prefix:value
        #   S2 prefix-wrapped:             `prefix:` value
        #   S3 whole-cell wrapped:         `prefix:value`   (no prose inside or outside)
        #   S4 prefix+selector-wrapped:    `prefix:` `selector` [trailing prose]
        #
        # Unsupported shapes that we MUST diagnose (not silently mangle):
        #   U1 whole-cell wrap + inline prose:  `prefix:selector` <prose>
        #   U2 whole-cell wrap + trailing word: `prefix:selector` exists
        #
        # PREFIX_RE matches the prefix token only ([a-z0-9_]+).
        local _tok_diag=""
        if [[ "$cell" =~ ^\`([a-z0-9_]+):\`[[:space:]]*\`([^\`]+)\`([[:space:]].*)?$ ]]; then
            # S4 — `prefix:` `selector` [trailing prose]
            cell="${BASH_REMATCH[1]}:${BASH_REMATCH[2]}"
        elif [[ "$cell" =~ ^\`([a-z0-9_]+):\`(.*)$ ]]; then
            # S2 — `prefix:` value
            # Strip ONE leading space. For single-token-selector prefixes
            # (grep, cited, pytest, node, cargo), additionally strip trailing
            # prose after the first whitespace boundary — covers shapes like
            # `grep:` `pat`@path (note) where the trailing parenthetical is
            # commentary, not part of the path. sh/bash keep their internal
            # whitespace because they accept argv (script.sh --flag).
            local _s2_prefix="${BASH_REMATCH[1]}"
            local _s2_rest="${BASH_REMATCH[2]# }"
            # Review: F4+F10 — strip trailing prose only for single-token-selector prefixes
            # (grep, cited, pytest). sh/bash/bats/node/cargo all accept multi-word argv
            # (e.g. `node:` `path -t "test name"`, `cargo:` `module::test --nocapture`)
            # so their internal whitespace must be preserved.
            case "$_s2_prefix" in
                grep|cited|pytest)
                    _s2_rest="${_s2_rest%% *}"
                    ;;
            esac
            cell="${_s2_prefix}:${_s2_rest}"
        elif [[ "$cell" =~ ^\`([a-z0-9_]+):([^\`]*)\`([[:space:]].+)?$ ]]; then
            # Whole-cell wrap variants:
            #   S3 when the trailing-prose group is empty: `prefix:value`
            #   U1/U2 when there IS trailing prose: `prefix:value` <prose>
            if [[ -z "${BASH_REMATCH[3]}" ]]; then
                cell="${BASH_REMATCH[1]}:${BASH_REMATCH[2]}"
            else
                _tok_diag="${BASH_REMATCH[1]}"
            fi
        fi
        if [[ -n "$_tok_diag" ]]; then
            # Emit a tokenizer-shape diagnostic. We prefix the cell with a
            # sentinel ("__TOK_BAD__<prefix>:") so the downstream dispatch
            # produces a diagnostic red instead of running grep/git against a
            # malformed selector. The dispatcher matches on "__TOK_BAD__*" and
            # renders the four-shape hint with the recognized prefix name.
            # Review: F12 — collision risk: a plan author whose cell literally
            # starts with __TOK_BAD__ would be falsely routed through this arm.
            # Acceptable: __TOK_BAD__ is not a valid typed-prefix name (no
            # [a-z0-9_]+ prefix can start with _), so real AC cells cannot
            # collide with this sentinel under the defined grammar.
            cell="__TOK_BAD__${_tok_diag}:${cell}"
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

    # Tokenizer-shape diagnostic (Fix 2, 2026-06-09): parse_pipe_row prefixes
    # malformed cells with __TOK_BAD__<recognized-prefix>: so we can render a
    # shape-naming red message rather than running the dispatcher against
    # mangled input.
    if [[ "$row_test" == __TOK_BAD__* ]]; then
        # Review: F2 — two-step strip; "${row_test#__TOK_BAD__*:}" is glob-greedy through
        # colons and would truncate display for cells like `cited:path/file.py:42` exists.
        # Step 1 strips the __TOK_BAD__ prefix to isolate the recognized-prefix token,
        # step 2 strips __TOK_BAD__<prefix>: to recover the verbatim original cell.
        _tok_prefix="${row_test#__TOK_BAD__}"
        _tok_prefix="${_tok_prefix%%:*}"
        _tok_original="${row_test#__TOK_BAD__${_tok_prefix}:}"
        red_messages+=("AC-${row_id} (${_tok_original}) red — tokenizer: unsupported '${_tok_prefix}:' cell shape. Supported shapes are: S1 bare 'prefix:value', S2 prefix-wrapped '\`prefix:\` value', S3 whole-cell wrap '\`prefix:value\`' (no prose), S4 prefix+selector wrap '\`prefix:\` \`selector\` [optional prose]'. Got whole-cell wrap with inline/trailing prose — rewrite to S4 (e.g. '\`${_tok_prefix}:\` \`<selector>\` (note)') so the selector and prose are separable.")
        (( red++ )) || true
        unset _tok_prefix _tok_original
        continue
    fi

    # Dispatch on typed prefix
    prefix="${row_test%%:*}"

    case "$prefix" in

        grep)
            # grep:pattern@path1[,path2...]
            rest="${row_test#grep:}"
            # Fix 3 (2026-06-09): require '@' separator. Without it,
            # paths_str="${rest#*@}" silently equals rest, making both pattern
            # and path the same junk string and reporting a misleading
            # "no match" red.
            if [[ "$rest" != *@* ]]; then
                red_messages+=("AC-${row_id} (${row_test}) red — grep: cell missing '@' separator. Expected shape: 'grep:pattern@path' (multi-path: 'grep:pattern@path1,path2'). Got no '@' — did you mean 'grep:${rest}@<path>'?")
                (( red++ )) || true
                continue
            fi
            pattern="${rest%%@*}"
            paths_str="${rest#*@}"

            # Trim whitespace from the pattern symmetrically with the path side
            # (trimmed below at the per-path loop). A row written `grep: pat @path`
            # otherwise carries leading/trailing spaces into the pattern, silently
            # breaking line-anchored or exact matches.
            pattern="${pattern#"${pattern%%[![:space:]]*}"}"
            pattern="${pattern%"${pattern##*[![:space:]]}"}"
            # Strip a wrapping backtick pair from the pattern: `pattern` → pattern.
            # Plan authors commonly backtick-wrap the pattern as code-formatting
            # in the rendered table — `grep:` `pat`@path. Without this strip, the
            # backticks become literal pattern characters and silently break the
            # match. Only strips when BOTH leading and trailing backtick are present.
            if [[ "$pattern" == \`*\` ]]; then
                pattern="${pattern#\`}"
                pattern="${pattern%\`}"
            fi

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
            # cited:<ref>[,<ref>...] — validates each cited ref resolves: 40-char SHA → git cat-file -e; else file path → -f check.
            # Fix 4 (2026-06-09): comma-separated refs supported, mirroring
            # grep:'s multi-path semantics. All must resolve (all-must-resolve).
            ref_list="${row_test#cited:}"
            # trim whitespace
            ref_list="${ref_list#"${ref_list%%[![:space:]]*}"}"
            ref_list="${ref_list%"${ref_list##*[![:space:]]}"}"

            IFS=',' read -ra _cited_refs <<< "$ref_list"
            _cited_multi=0
            if [[ ${#_cited_refs[@]} -gt 1 ]]; then
                _cited_multi=1
            fi
            _cited_row_result="green"
            _cited_fail_msg=""
            for ref in "${_cited_refs[@]}"; do
                # per-element trim
                ref="${ref#"${ref%%[![:space:]]*}"}"
                ref="${ref%"${ref##*[![:space:]]}"}"
                if [[ ${#ref} -eq 40 ]] && echo "$ref" | grep -qE '^[0-9a-fA-F]{40}$'; then
                    if ! git -C "$(dirname "$PLAN_PATH")" cat-file -e "$ref" 2>/dev/null; then
                        _cited_row_result="red"
                        _cited_fail_msg="git SHA '${ref}' not found in local history"
                        break
                    fi
                else
                    if [[ ! -f "$ref" ]]; then
                        _cited_row_result="red"
                        _cited_fail_msg="file path '${ref}' not found on disk"
                        break
                    fi
                fi
            done

            if [[ "$_cited_row_result" == "green" ]]; then
                echo "AC-${row_id} satisfied by citation ${ref_list} — NOT re-run on this host" >&2
                (( green++ )) || true
            else
                if (( _cited_multi == 1 )); then
                    red_messages+=("AC-${row_id} (${row_test}) red — all-must-resolve: ${_cited_fail_msg}")
                else
                    red_messages+=("AC-${row_id} (${row_test}) red — ref does not resolve: ${_cited_fail_msg}")
                fi
                (( red++ )) || true
            fi
            unset _cited_refs _cited_multi _cited_row_result _cited_fail_msg
            ;;

        pytest)
            # pytest:<path>::<nodeid>  — invoker resolved via $PYTEST_CMD (default: pytest)
            args="${row_test#pytest:}"
            if err_suffix="$(run_typed_test "$PYTEST_CMD" "$args" pytest)"; then
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

        sh|bash|bats)
            # sh:<script-path> [args...]  — run the named script with bash.
            # bash: and bats: are aliases for sh: — all three use the same dispatch path.
            # bats: was added 2026-06-09 per holodeck-em consult: plan authors
            # reach for 'bats:' because the typed-prefix vocabulary mirrors
            # runner names (pytest → pytest, cargo → cargo, bats → bats).
            # bats files ARE bash scripts; bash is the right runner.
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
            red_messages+=("AC-${row_id} (${row_test}) red — unknown typed prefix '${prefix}': supported prefixes are pytest, node, cargo, grep, cited, sh, bash, bats")
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
