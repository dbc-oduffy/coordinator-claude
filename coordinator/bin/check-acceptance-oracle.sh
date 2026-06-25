#!/usr/bin/env bash
# Purpose: Parse the ## Acceptance Criteria oracle table from a plan file and gate on gate-bound rows.
# Spec: archive/specs/2026-05-24-acceptance-oracle-with-teeth.md §2.1 §2.3 §Task 2
#
# Concurrency / idempotency / resume: this script is read-only against the plan and test suite;
# it has no side-effects, is idempotent, and is safe to run concurrently across sessions.
#
# Exit-code contract (TEETH): non-zero iff any gate-bound row is red or missing/uncited.
# Message contract  (CARROT): lead with state, never blame; summary line format:
#   "<G>/<N> gate-bound acceptance tests green; <R> red; <S> skipped (reviewer-judgment); <E> env-unprovisioned"
# Parsing contract: markdown code-fence blocks (``` ... ```) are excluded; only content outside fences is parsed for AC rows.
# Runner contract: a per-repo COORDINATOR_PYTEST_CMD / pytest_cmd runner SHOULD exit 4 to signal
#   "interpreter unprovisioned (not a test failure)"; the oracle maps exit 4 → ENV-UNPROVISIONED
#   (not red, not counted against the gate, surfaced as a distinct count in the summary line).
#   Exit codes 1/2/3 from the runner are genuine test failures and remain RED.
#   GATING (teeth-preservation): exit 4 → ENV-UNPROVISIONED applies ONLY when the pytest runner
#   was EXPLICITLY configured (COORDINATOR_PYTEST_CMD env or coordinator.local.md `pytest_cmd:`),
#   i.e. a per-repo runner that opted into this contract. The DEFAULT bare `pytest` runner does
#   NOT opt in: stock pytest reserves exit 4 for its own "usage error" (bad CLI args / malformed
#   selector), so for the default runner exit 4 stays RED — remapping it would silently erode the
#   gate's teeth on a real misconfiguration. (See PYTEST_RUNNER_IS_CUSTOM below.)

set -euo pipefail

# ---------------------------------------------------------------------------
# Bash 4+ guard — local -a and (( )) arithmetic require bash 4+ (DR-148).
# BASH_VERSINFO and [[ ]] are available since bash 2.x; this guard is
# reachable on bash 3.2 (no heredoc-in-$() parse trap above it).
# ---------------------------------------------------------------------------
if (( BASH_VERSINFO[0] < 4 )); then
    echo "ERROR: bash 4+ required (found ${BASH_VERSION}). Install with: brew install bash" >&2
    exit 2
fi

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
#
# Runner exit-code contract:
#   0       — test(s) passed (green)
#   1/2/3   — pytest / test-framework failure codes (red)
#   4       — interpreter unprovisioned: the runner could not find a capable
#             interpreter (e.g. missing pytest-xdist). The oracle maps this to
#             ENV-UNPROVISIONED (not red, not zero) — but ONLY when honor_exit4=1
#             (the runner explicitly opted into the contract; see
#             PYTEST_RUNNER_IS_CUSTOM). With honor_exit4=0 (default bare runner)
#             exit 4 falls through to the generic non-zero RED path, because stock
#             pytest reserves exit 4 for its own usage-error.
run_typed_test() {
    # Optional third arg: prefix name (e.g. "pytest") — enables prefix-specific
    # diagnostic hints (Fix 5, 2026-06-09). Defaults to empty for back-compat
    # with any caller that still passes only two args.
    # Optional fourth arg: honor_exit4 (0|1) — when 1, a runner exit-4 is
    # short-circuited as the ENV-UNPROVISIONED signal (bare return 4, no tail).
    # When 0 (default), exit 4 is treated as any other non-zero failure (RED with
    # diagnostic tail). Only opted-in custom runners pass 1.
    local runner="$1" arg_str="$2" prefix_name="${3:-}" honor_exit4="${4:-0}"
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
    if (( rc == 4 )) && (( honor_exit4 == 1 )); then
        # Exit 4 from an opted-in custom runner: interpreter unprovisioned (not a
        # test failure). Callers distinguish this from genuine failures (rc=1/2/3).
        # No output suffix emitted — caller emits the ENV-UNPROVISIONED note.
        # NB: for the default bare runner (honor_exit4=0) this branch is skipped
        # and exit 4 falls through to the generic non-zero path below (RED),
        # because stock pytest reserves exit 4 for its own usage-error.
        rm -f "$out_file"
        return 4
    fi
    if (( rc != 0 )); then
        # Bound the surfaced tail: newlines→spaces, drop non-printable bytes,
        # collapse runs, cap length. Keeps a runaway test log (or control chars)
        # from bloating/corrupting the red-message line.
        out_tail="$(tail -n 3 "$out_file" 2>/dev/null | LC_ALL=C tr '\n' ' ' | LC_ALL=C tr -cd '[:print:]' | LC_ALL=C sed -E 's/[[:space:]]+/ /g; s/^[[:space:]]+//; s/[[:space:]]+$//' | head -c 200)"
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

# runner_is_custom <frontmatter-key> <env-var-name>
# Return 0 (true) iff the runner was EXPLICITLY configured via env var or
# coordinator.local.md frontmatter — i.e. a per-repo runner that opted into the
# exit-4-as-ENV-UNPROVISIONED contract. The default fallback (bare `pytest` etc.)
# returns 1 (false). Mirrors resolve_runner_cmd Steps 1-2 precedence (env >
# frontmatter); deliberately a separate predicate because resolve_runner_cmd runs
# inside $(...) and cannot export an override flag to the parent shell.
runner_is_custom() {
    local key="$1" env_name="$2"
    [[ ! "$key" =~ ^[a-z_]+$ ]] && return 1
    [[ ! "$env_name" =~ ^COORDINATOR_[A-Z_]+$ ]] && return 1
    [[ -n "${!env_name:-}" ]] && return 0
    local local_md="$REPO_ROOT/coordinator.local.md"
    if [[ -f "$local_md" ]]; then
        local fm val
        fm=$(awk '/^---$/{n++; if (n==2) exit; next} n==1' "$local_md" 2>/dev/null)
        val=$(echo "$fm" | grep -m1 "^${key}:" \
            | sed -E "s/^${key}:[[:space:]]*//" \
            | tr -d '"' | tr -d "'" \
            | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')
        [[ -n "$val" ]] && return 0
    fi
    return 1
}

PYTEST_CMD="$(resolve_runner_cmd pytest_cmd COORDINATOR_PYTEST_CMD 'pytest')"
NODE_CMD="$(resolve_runner_cmd node_cmd COORDINATOR_NODE_CMD 'node --test')"
CARGO_CMD="$(resolve_runner_cmd cargo_cmd COORDINATOR_CARGO_CMD 'cargo test')"

# Only an explicitly-configured (opted-in) pytest runner gets exit-4 → ENV-UNPROVISIONED.
# Default bare `pytest` keeps exit 4 as RED (stock pytest's reserved usage-error code).
if runner_is_custom pytest_cmd COORDINATOR_PYTEST_CMD; then
    PYTEST_RUNNER_IS_CUSTOM=1
else
    PYTEST_RUNNER_IS_CUSTOM=0
fi

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

# tokenize_one <cell-text>
# Purpose: Apply the S1-S4 tokenizer to a single trimmed cell value and echo the result.
# Spec backlink: archive/specs/2026-05-24-acceptance-oracle-with-teeth.md §2.1 typed-prefix grammar.
# Negative-spec: does NOT handle combinator expressions — caller splits those before calling here.
# Returns either the normalised "prefix:value" form or "__TOK_BAD__<prefix>:<orig>" on unsupported shape.
tokenize_one() {
    local cell="$1"
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
    printf '%s' "$cell"
}

# _is_typed_prefix_token <text>
# Purpose: COARSE filter — return 0 (true) if text starts with a known prefix: after
# stripping one optional leading backtick (covering S2/S3/S4 shapes). Used by the
# combinator parser to reject prose cells containing " AND "/" OR " as combinators.
# Fine S1–S4 validation and U1/U2 detection (which emits __TOK_BAD__) is done by
# tokenize_one; this filter only checks that the prefix name is a known one — it
# does NOT validate the full cell shape.
# Known prefixes: pytest, node, cargo, grep, cited, sh, bash, bats.
_is_typed_prefix_token() {
    local t="$1"
    # Strip optional leading backtick (S2/S3/S4 shapes start with `)
    t="${t#\`}"
    case "$t" in
        pytest:*|node:*|cargo:*|grep:*|cited:*|sh:*|bash:*|bats:*) return 0 ;;
        *) return 1 ;;
    esac
}

# _strip_combinator_operand_wrap <operand>
# Bug-1 fix (whole-cell-wrapped combinator): when a combinator cell is wrapped in
# a single pair of markdown backticks (`grep:A@f AND cited:B`), the ` AND `/` OR `
# split leaves the wrap's backticks stranded on the EDGE operands — operand 0 keeps
# a leading ` with no closing match, the last operand keeps a trailing ` with no
# opening match. Strip ONLY that unbalanced edge backtick. A balanced per-operand
# wrap (`bash:true`, or the S4 form `bash:` `true`) starts AND ends with a backtick
# and is left intact for tokenize_one to handle. Echoes the cleaned operand.
_strip_combinator_operand_wrap() {
    local _o="$1"
    # The whole-cell wrap leaks exactly ONE backtick onto the first operand's left
    # edge and ONE onto the last operand's right edge. Two leak shapes per edge:
    #   bare operand + wrap:      `grep:A@f      (1 leading, 0 trailing)
    #   own-wrapped(S3/S4)+ wrap: ``bash:` `true`  (2 leading, own trailing intact)
    # Handle both. The double-backtick test fires for the own-wrapped case (a bare
    # operand never starts with a backtick; an own-wrapped one starts with exactly
    # one — so two leading backticks is an unambiguous wrap-leak signal). Leading
    # and trailing leaks never co-occur on one operand (first gets leading, last
    # gets trailing, middles get neither), so the two blocks are independent.
    if [[ "$_o" == \`\`* ]]; then
        _o="${_o#\`}"        # double leading ` → strip the outer-wrap one, keep operand's own
    elif [[ "$_o" == \`* && "$_o" != *\` ]]; then
        _o="${_o#\`}"        # single leading `, no trailing ` → bare operand + wrap leak
    fi
    if [[ "$_o" == *\`\` ]]; then
        _o="${_o%\`}"        # double trailing ` → strip the outer-wrap one, keep operand's own
    elif [[ "$_o" == *\` && "$_o" != \`* ]]; then
        _o="${_o%\`}"        # single trailing `, no leading ` → bare operand + wrap leak
    fi
    printf '%s' "$_o"
}

parse_pipe_row() {
    # Given a pipe-delimited table row, echo each trimmed cell on its own line
    # prefixed with its 0-based column index "N:cell".
    # Strips markdown backtick wrappers from cell values (e.g. `grep:foo` → grep:foo).
    # AND/OR combinator expressions are tokenised as __COMBO__:<op>:<tok1>\x1f<tok2>...
    local row="$1"
    # Strip leading/trailing pipes
    row="${row#|}"
    row="${row%|}"
    # Bug-2 fix (escaped-pipe tolerance): a literal '|' inside a sh:/bash: command
    # (e.g. `sh:cmd 2>&1 | grep -q x`) must be authored markdown-escaped as '\|'
    # (GFM table convention), otherwise the column split below truncates the cell
    # mid-expression. Swap each '\|' to a sentinel (RS, \x1e — distinct from the
    # combinator US-separator \x1f) BEFORE the column split, restore it to '|'
    # after each cell is read. An UNescaped '|' still splits (standard markdown
    # behaviour — authors must escape literal pipes in table cells).
    # Assumption: '\|' in an AC cell ALWAYS means a GFM-escaped literal pipe (the
    # only way to get a '|' past the column split), never a literal backslash-pipe
    # the command needs verbatim. A sh:/bash: command wanting alternation should use
    # `grep -E 'a|b'` (ERE, bare '|' escaped as '\|') — it still resolves to '|',
    # which ERE treats as alternation. BRE '\|' alternation is unsupported here.
    local _PIPE_SENT=$'\x1e'
    row="${row//\\|/$_PIPE_SENT}"
    local idx=0
    # Convert '|' to newlines so each cell lands on its own line, then read them.
    while IFS= read -r cell; do
        # restore escaped pipes ('\|' → '|') protected from the column split above
        cell="${cell//$_PIPE_SENT/|}"
        # trim leading/trailing whitespace
        cell="${cell#"${cell%%[![:space:]]*}"}"
        cell="${cell%"${cell##*[![:space:]]}"}"

        # --- Combinator detection (AND/OR) ---
        # Only treat " AND " / " OR " as combinators when splitting yields >=2 non-empty
        # operands each looking like a typed-prefix token — so a grep pattern containing
        # the word "AND" without spaces (e.g. "grep:FOOANDbar@file") is not misparsed.
        local _has_and=0 _has_or=0
        [[ "$cell" == *" AND "* ]] && _has_and=1
        [[ "$cell" == *" OR "* ]]  && _has_or=1

        if (( _has_and || _has_or )); then
            if (( _has_and && _has_or )); then
                # Mixed — emit __COMBO_BAD__:mixed:<orig>
                echo "${idx}:__COMBO_BAD__:mixed:${cell}"
                (( idx++ )) || true
                continue
            fi
            # Exactly one combinator kind — attempt to split and validate operands
            local _combo_op _combo_sep _combo_valid=1
            local -a _combo_parts=()
            if (( _has_and )); then
                _combo_op="AND"
                _combo_sep=" AND "
            else
                _combo_op="OR"
                _combo_sep=" OR "
            fi
            # Split on the separator. We use a loop to avoid GNU-specific tools.
            local _combo_rest="$cell"
            while [[ "$_combo_rest" == *"${_combo_sep}"* ]]; do
                _combo_parts+=("${_combo_rest%%"${_combo_sep}"*}")
                _combo_rest="${_combo_rest#*"${_combo_sep}"}"
            done
            _combo_parts+=("$_combo_rest")

            # Validate: need >=2 parts, each non-empty and typed-prefix-shaped
            if (( ${#_combo_parts[@]} < 2 )); then
                _combo_valid=0
            else
                local _cp
                for _cp in "${_combo_parts[@]}"; do
                    # trim per-operand whitespace
                    _cp="${_cp#"${_cp%%[![:space:]]*}"}"
                    _cp="${_cp%"${_cp##*[![:space:]]}"}"
                    # strip a stranded whole-cell-wrap backtick off the edge operand
                    _cp="$(_strip_combinator_operand_wrap "$_cp")"
                    if [[ -z "$_cp" ]] || ! _is_typed_prefix_token "$_cp"; then
                        _combo_valid=0
                        break
                    fi
                done
            fi

            if (( _combo_valid )); then
                # Build __COMBO__:<op>:<tok1>\x1f<tok2>...
                local _combo_encoded=""
                local _first=1
                for _cp in "${_combo_parts[@]}"; do
                    _cp="${_cp#"${_cp%%[![:space:]]*}"}"
                    _cp="${_cp%"${_cp##*[![:space:]]}"}"
                    # strip a stranded whole-cell-wrap backtick off the edge operand
                    # (must match the validation loop above so both see identical tokens)
                    _cp="$(_strip_combinator_operand_wrap "$_cp")"
                    local _tok
                    _tok="$(tokenize_one "$_cp")"
                    if (( _first )); then
                        _combo_encoded="${_tok}"
                        _first=0
                    else
                        _combo_encoded="${_combo_encoded}"$'\x1f'"${_tok}"
                    fi
                done
                echo "${idx}:__COMBO__:${_combo_op}:${_combo_encoded}"
                (( idx++ )) || true
                continue
            fi
            # Fall through: not a valid combinator (e.g. prose with "AND" but no typed-prefix operands)
        fi

        # Single cell — tokenize as before
        local _tok_result
        _tok_result="$(tokenize_one "$cell")"
        echo "${idx}:${_tok_result}"
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
            cell_lower="$(printf '%s' "$cell" | LC_ALL=C tr '[:upper:]' '[:lower:]')"
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

# run_one_test <tokenized-cell> <display-id>
# Evaluate a SINGLE tokenized typed-prefix test (one S1-S4 token, already tokenised).
# Sets globals:
#   _one_ok     = 1 (green) | 0 (red)
#   _one_reason = on red, the text that follows "red — " (caller prefixes "AC-<id> (<cell>) red — ")
# Does NOT touch green/red counters or red_messages — the caller aggregates (so this is
# reusable for both single cells and per-operand evaluation inside AND/OR combinators).
# <display-id> is used only for the cited-green informational stderr note. Always returns 0
# (the verdict travels via _one_ok, never via exit status — set -e safety for callers).
run_one_test() {
    local _cell="$1"
    local _disp_id="$2"
    _one_ok=1
    _one_reason=""

    # pending realization — always red
    if echo "$_cell" | grep -qi "pending.realization"; then
        _one_ok=0
        _one_reason="test not yet realized (pending realization)"
        return 0
    fi

    # tokenizer-shape diagnostic (sentinel from tokenize_one)
    if [[ "$_cell" == __TOK_BAD__* ]]; then
        local _tok_prefix _tok_original
        _tok_prefix="${_cell#__TOK_BAD__}"
        _tok_prefix="${_tok_prefix%%:*}"
        _tok_original="${_cell#__TOK_BAD__${_tok_prefix}:}"
        _one_ok=0
        _one_reason="tokenizer: unsupported '${_tok_prefix}:' cell shape. Supported shapes are: S1 bare 'prefix:value', S2 prefix-wrapped '\`prefix:\` value', S3 whole-cell wrap '\`prefix:value\`' (no prose), S4 prefix+selector wrap '\`prefix:\` \`selector\` [optional prose]'. Got whole-cell wrap with inline/trailing prose — rewrite to S4 (e.g. '\`${_tok_prefix}:\` \`<selector>\` (note)') so the selector and prose are separable."
        return 0
    fi

    local prefix="${_cell%%:*}"
    case "$prefix" in

        grep)
            local rest="${_cell#grep:}"
            if [[ "$rest" != *@* ]]; then
                _one_ok=0
                _one_reason="grep: cell missing '@' separator. Expected shape: 'grep:pattern@path' (multi-path: 'grep:pattern@path1,path2'). Got no '@' — did you mean 'grep:${rest}@<path>'?"
                return 0
            fi
            local pattern="${rest%%@*}"
            local paths_str="${rest#*@}"
            pattern="${pattern#"${pattern%%[![:space:]]*}"}"
            pattern="${pattern%"${pattern##*[![:space:]]}"}"
            if [[ "$pattern" == \`*\` ]]; then
                pattern="${pattern#\`}"
                pattern="${pattern%\`}"
            fi
            local -a paths_arr
            IFS=',' read -ra paths_arr <<< "$paths_str" || true
            local row_result="green" failing_path="" p
            for p in "${paths_arr[@]+"${paths_arr[@]}"}"; do
                p="${p#"${p%%[![:space:]]*}"}"
                p="${p%"${p##*[![:space:]]}"}"
                if ! grep -q "$pattern" "$p" 2>/dev/null; then
                    row_result="red"
                    failing_path="$p"
                    break
                fi
            done
            if [[ "$row_result" == "green" ]]; then
                _one_ok=1
            else
                _one_ok=0
                if [[ ${#paths_arr[@]} -gt 1 ]]; then
                    _one_reason="all-must-match: no match for pattern '${pattern}' in ${failing_path}"
                else
                    _one_reason="no match for pattern '${pattern}' in ${paths_str}"
                fi
            fi
            ;;

        cited)
            local ref_list="${_cell#cited:}"
            ref_list="${ref_list#"${ref_list%%[![:space:]]*}"}"
            ref_list="${ref_list%"${ref_list##*[![:space:]]}"}"
            local -a _cited_refs
            IFS=',' read -ra _cited_refs <<< "$ref_list" || true
            local _cited_multi=0
            if [[ ${#_cited_refs[@]} -gt 1 ]]; then
                _cited_multi=1
            fi
            local _cited_row_result="green" _cited_fail_msg="" ref
            for ref in "${_cited_refs[@]+"${_cited_refs[@]}"}"; do
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
                echo "AC-${_disp_id} satisfied by citation ${ref_list} — NOT re-run on this host" >&2
                _one_ok=1
            else
                _one_ok=0
                if (( _cited_multi == 1 )); then
                    _one_reason="all-must-resolve: ${_cited_fail_msg}"
                else
                    _one_reason="ref does not resolve: ${_cited_fail_msg}"
                fi
            fi
            ;;

        pytest)
            local args="${_cell#pytest:}" err_suffix _pytest_rc
            err_suffix="$(run_typed_test "$PYTEST_CMD" "$args" pytest "$PYTEST_RUNNER_IS_CUSTOM")" && _pytest_rc=0 || _pytest_rc=$?
            if (( _pytest_rc == 0 )); then
                _one_ok=1
            # The `&& PYTEST_RUNNER_IS_CUSTOM == 1` is redundant by construction —
            # run_typed_test only returns 4 when honor_exit4 (== PYTEST_RUNNER_IS_CUSTOM)
            # is 1 — but it is kept as intentional defense-in-depth: this is the gate
            # that protects the oracle's teeth, so the ENV-UNPROVISIONED branch must
            # NOT fire for a default runner even if a future run_typed_test refactor
            # ever lets a bare exit-4 reach here (code-reviewer F3).
            elif (( _pytest_rc == 4 && PYTEST_RUNNER_IS_CUSTOM == 1 )); then
                _one_ok=2   # sentinel: ENV-UNPROVISIONED (caller checks _one_ok==2)
                _one_reason="runner exited 4 (interpreter unprovisioned — verify against CI or a provisioned interpreter)"
            else
                _one_ok=0
                _one_reason="'${PYTEST_CMD}' exited non-zero${err_suffix}"
            fi
            ;;

        node)
            local args="${_cell#node:}" err_suffix
            if err_suffix="$(run_typed_test "$NODE_CMD" "$args")"; then
                _one_ok=1
            else
                _one_ok=0
                _one_reason="'${NODE_CMD}' exited non-zero${err_suffix}"
            fi
            ;;

        cargo)
            local args="${_cell#cargo:}" err_suffix
            if err_suffix="$(run_typed_test "$CARGO_CMD" "$args")"; then
                _one_ok=1
            else
                _one_ok=0
                _one_reason="'${CARGO_CMD}' exited non-zero${err_suffix}"
            fi
            ;;

        sh|bash)
            local args="${_cell#*:}"
            args="${args#"${args%%[![:space:]]*}"}"
            local _sh_out_file
            _sh_out_file="$(mktemp 2>/dev/null)" || _sh_out_file=""
            if [ -n "$_sh_out_file" ]; then
                if bash -c "$args" >"$_sh_out_file" 2>&1; then
                    _one_ok=1
                else
                    local _sh_rc=$?
                    local _sh_tail
                    _sh_tail="$(tail -c 240 "$_sh_out_file" 2>/dev/null | LC_ALL=C tr '\n' ' ' | LC_ALL=C sed 's/[[:space:]]\+/ /g')"
                    _one_ok=0
                    _one_reason="bash -c exited ${_sh_rc}: ${_sh_tail}"
                fi
                rm -f "$_sh_out_file" 2>/dev/null || true
            else
                if bash -c "$args" >/dev/null 2>&1; then
                    _one_ok=1
                else
                    _one_ok=0
                    _one_reason="bash -c exited non-zero (output discarded; mktemp unavailable)"
                fi
            fi
            ;;

        bats)
            # bats:<test-file> — run the test FILE under bash. Established semantics
            # (Fix 7, 2026-06-09 holodeck-em consult): bats: is a synonym for bash:
            # targeting a plain-bash .bats harness (shebang #!/usr/bin/env bash).
            # Bug-3 fix: invoke `bash <file>` (file-mode) rather than `bash -c "<file>"`
            # (command-mode). Command-mode executes the path as a command — which needs
            # the +x bit AND a ./ or PATH entry, producing a bare 126/127 red on a
            # harness authored without the exec bit. File-mode interprets the file under
            # bash directly: no exec bit, no PATH dependence, relative path resolves
            # against cwd. The shebang guarantees the file runs under bash.
            local _bats_file="${_cell#bats:}"
            _bats_file="${_bats_file#"${_bats_file%%[![:space:]]*}"}"
            _bats_file="${_bats_file%"${_bats_file##*[![:space:]]}"}"
            # Unlike sh:/bash: (which run a command string via `bash -c`), bats:
            # runs a FILE — so a missing path otherwise yields an opaque 127. Match
            # the cited: precedent with an explicit, actionable not-found red.
            if [[ ! -f "$_bats_file" ]]; then
                _one_ok=0
                _one_reason="bats: test file not found: ${_bats_file} (path is resolved relative to the plan's repo root)"
                return 0
            fi
            local _bats_out_file
            _bats_out_file="$(mktemp 2>/dev/null)" || _bats_out_file=""
            if [ -n "$_bats_out_file" ]; then
                if bash "$_bats_file" >"$_bats_out_file" 2>&1; then
                    _one_ok=1
                else
                    local _bats_rc=$?
                    local _bats_tail
                    _bats_tail="$(tail -c 240 "$_bats_out_file" 2>/dev/null | LC_ALL=C tr '\n' ' ' | LC_ALL=C sed 's/[[:space:]]\+/ /g')"
                    _one_ok=0
                    _one_reason="bats: bash <file> exited ${_bats_rc}: ${_bats_tail}"
                fi
                rm -f "$_bats_out_file" 2>/dev/null || true
            else
                if bash "$_bats_file" >/dev/null 2>&1; then
                    _one_ok=1
                else
                    _one_ok=0
                    _one_reason="bats: bash <file> exited non-zero (output discarded; mktemp unavailable)"
                fi
            fi
            ;;

        *)
            _one_ok=0
            if [ "${prefix}" = "git" ]; then
                local _git_args="${_cell#git:}"
                _one_reason="'git:' is not a supported typed prefix. Rewrite as 'sh:${_git_args}' (or 'sh:git ... | wc -l | grep -q <N>' for count assertions). Supported prefixes: pytest, node, cargo, grep, cited, sh, bash, bats."
            else
                _one_reason="unknown typed prefix '${prefix}': supported prefixes are pytest, node, cargo, grep, cited, sh, bash, bats"
            fi
            ;;
    esac
    return 0
}

# ---------------------------------------------------------------------------
# Process data rows
# ---------------------------------------------------------------------------
green=0
red=0
skipped=0
env_unprovisioned=0
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
    row_class_lower="$(printf '%s' "$row_class" | LC_ALL=C tr '[:upper:]' '[:lower:]')"

    # Skip rows where binding class is reviewer-judgment
    if echo "$row_class_lower" | grep -q "reviewer"; then
        (( skipped++ )) || true
        continue
    fi

    # Gate-bound row
    (( total_gate_bound++ )) || true

    # --- Evaluate: AND/OR combinator (__COMBO__ / __COMBO_BAD__) or a single test ---
    # parse_pipe_row tokenises a combinator cell to __COMBO__:<OP>:<tok1>\x1f<tok2>...
    # (homogeneous AND or OR), or __COMBO_BAD__:mixed:<orig> when AND and OR are mixed.
    # Each operand is evaluated via run_one_test (the same per-test engine single cells use),
    # then combined: AND → green iff all operands green; OR → green iff any operand green.

    if [[ "$row_test" == __COMBO_BAD__:mixed:* ]]; then
        _combo_orig="${row_test#__COMBO_BAD__:mixed:}"
        red_messages+=("AC-${row_id} (${_combo_orig}) red — mixed AND/OR combinators not supported; use a single combinator per cell (all AND or all OR).")
        (( red++ )) || true
        unset _combo_orig
        continue
    fi

    if [[ "$row_test" == __COMBO__:* ]]; then
        _combo_body="${row_test#__COMBO__:}"
        _combo_op="${_combo_body%%:*}"
        _combo_ops_str="${_combo_body#*:}"
        _combo_ops=()
        # Review: IFS inline scoped to this single read; no save/restore needed.
        IFS=$'\x1f' read -ra _combo_ops <<< "$_combo_ops_str" || true
        _combo_pass=0
        _combo_total=0
        _combo_fail_reasons=()
        _combo_env_unprovisioned=0
        for _op in "${_combo_ops[@]+"${_combo_ops[@]}"}"; do
            (( _combo_total++ )) || true
            run_one_test "$_op" "$row_id"
            if (( _one_ok == 1 )); then
                (( _combo_pass++ )) || true
            elif (( _one_ok == 2 )); then
                # ENV-UNPROVISIONED operand: propagate to whole row
                _combo_env_unprovisioned=1
                _combo_fail_reasons+=("[${_op}] ${_one_reason}")
            else
                _combo_fail_reasons+=("[${_op}] ${_one_reason}")
            fi
        done
        if (( _combo_env_unprovisioned )); then
            echo "AC-${row_id} (${row_test}) env-unprovisioned — ${_combo_fail_reasons[*]:-runner exited 4}" >&2
            (( env_unprovisioned++ )) || true
        else
            _combo_green=0
            if [[ "$_combo_op" == "AND" ]]; then
                if (( _combo_pass == _combo_total )); then _combo_green=1; fi
            else
                if (( _combo_pass >= 1 )); then _combo_green=1; fi
            fi
            if (( _combo_green )); then
                (( green++ )) || true
            else
                _combo_joined=""
                for _r in "${_combo_fail_reasons[@]+"${_combo_fail_reasons[@]}"}"; do
                    if [[ -n "$_combo_joined" ]]; then _combo_joined="${_combo_joined}; "; fi
                    _combo_joined="${_combo_joined}${_r}"
                done
                if [[ "$_combo_op" == "AND" ]]; then
                    red_messages+=("AC-${row_id} (combinator AND) red — failing operand(s): ${_combo_joined}")
                else
                    red_messages+=("AC-${row_id} (combinator OR) red — all ${_combo_total} operands failed: ${_combo_joined}")
                fi
                (( red++ )) || true
            fi
        fi
        unset _combo_body _combo_op _combo_ops_str _combo_ops _combo_pass _combo_total _combo_fail_reasons _combo_green _combo_joined _combo_env_unprovisioned _op _r
        continue
    fi

    # Single test
    run_one_test "$row_test" "$row_id"
    if (( _one_ok == 1 )); then
        (( green++ )) || true
    elif (( _one_ok == 2 )); then
        # ENV-UNPROVISIONED: runner exited 4 — not a test failure; not red.
        echo "AC-${row_id} (${row_test}) env-unprovisioned — ${_one_reason}" >&2
        (( env_unprovisioned++ )) || true
    else
        red_messages+=("AC-${row_id} (${row_test}) red — ${_one_reason}")
        (( red++ )) || true
    fi

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
echo "${green}/${total_gate_bound} gate-bound acceptance tests green; ${red} red; ${skipped} skipped (reviewer-judgment); ${env_unprovisioned} env-unprovisioned"

# ---------------------------------------------------------------------------
# Exit code (TEETH — strictly orthogonal to message tone)
# ---------------------------------------------------------------------------
if [[ $red -gt 0 ]]; then
    exit 1
fi
exit 0
