#!/usr/bin/env bash
# coordinator/lib/setup-detect-test-cmd.sh — Detect project stack test commands and seed
# them into the target repo's coordinator.local.md frontmatter.
#
# Purpose: sourceable repo-setup-time helper that inspects common stack markers
# (package.json, pyproject.toml / pytest.ini, Cargo.toml) in a target repo, proposes
# fast_test_cmd and full_test_cmd values, and upserts them into coordinator.local.md as
# flat top-level frontmatter keys — matching the exact shape cs_resolve_fast_test_cmd /
# cs_resolve_full_test_cmd consume (coordinator-resolve-validation-cmd.sh lines 15-22).
#
# Detection by stack:
#   Node.js  — package.json scripts.test / scripts.test:unit / scripts.lint
#   Python   — pyproject.toml [tool.pytest.ini_options] or pytest.ini / setup.cfg [tool:pytest]
#   Rust     — Cargo.toml (cargo test --lib / cargo test)
#
# Interaction model:
#   Interactive (default) — presents candidates and asks for confirmation before writing.
#   --non-interactive      — accepts the detected command set without prompting; for tests
#                            and fresh-machine automation. Optionally followed by two
#                            positional preset overrides: <fast_cmd> <full_cmd>.
#   SETUP_DETECT_NONINTERACTIVE=1 — env-var equivalent of --non-interactive.
#
# Detect-then-fail-loud: when MULTIPLE plausible fast candidates exist and none is
# unambiguously cheapest (e.g. multiple stacks each emit a fast candidate), the function
# surfaces all candidates and exits 1 without writing — the caller must disambiguate.
# No silent fallback. Never silently picks one.
#
# Idempotency: if fast_test_cmd AND full_test_cmd are already present in
# coordinator.local.md, the function is a no-op (exits 2) unless --force is passed.
#
# Usage (sourceable):
#   source setup-detect-test-cmd.sh
#   sdtc_detect_and_write_test_cmds <repo_root> [--non-interactive [fast_cmd] [full_cmd]] [--force]
#
# Arguments:
#   repo_root           — target repo root (required positional).
#   --non-interactive   — accept proposed commands without prompting.
#   --force             — overwrite even if keys already exist.
#   --help | -h         — print usage and exit 0 (only in direct-run mode).
#
# Exit codes:
#   0  — commands written successfully.
#   1  — detection found ambiguous candidates; human disambiguation required.
#         OR operator declined the proposal in interactive mode.
#         OR a write error occurred.
#   2  — no test commands could be detected for any known stack;
#         OR keys already present and --force not passed (idempotent no-op).
#   3  — coordinator.local.md is missing or its frontmatter is malformed.
# Review: code-reviewer — removed "already present without --force" from exit-0 line;
#   impl and tests use exit 2 for that path, not exit 0.
#
# Write shape — flat top-level YAML frontmatter keys written/upserted:
#   fast_test_cmd: <cmd>
#   full_test_cmd: <cmd>
#
# Spec backlink: docs/plans/2026-06-23-setup-time-substrate-completeness.md § C1
# Key-shape contract: coordinator-resolve-validation-cmd.sh lines 15-21 (flat top-level
# YAML frontmatter between first two --- markers).
#
# Negative-spec: this file MUST be sourced by callers that want the function interface.
# It also works when executed directly (direct-run guard at the bottom delegates to the
# function). It does NOT commit or stage any files — the caller owns git operations.
#
# Cross-platform portability:
#   - Targets bash >= 4 + BSD coreutils (macOS default).
#   - No GNU-isms: no sed -i; no grep -P; no realpath; no date -d.
#   - All in-place file edits use a portable tmp-file + mv pattern.
#   - Uses bash 4 features (declare -a, [[ ]]). Guard below requires bash 4.

# ---------------------------------------------------------------------------
# Bash-4 guard — MUST be syntactically reachable on bash 3.2 (plain [ ] only,
# no [[ ]], no (( )), no bash-4 builtins above this line).
# ---------------------------------------------------------------------------
if [ "${BASH_VERSINFO[0]:-0}" -lt 4 ]; then
  echo "[setup-detect-test-cmd] ERROR: bash >= 4 required (found ${BASH_VERSION:-unknown})." >&2
  echo "  On macOS: brew install bash && add /opt/homebrew/bin/bash to /etc/shells" >&2
  # return when sourced, exit when run directly
  return 1 2>/dev/null || exit 1
fi

# ---------------------------------------------------------------------------
# Detection helpers
# Each function emits protocol lines to stdout:
#   FAST:<cmd>
#   FULL:<cmd>
# Returns nothing to stdout (and exits 0 silently) when the stack is absent.
# ---------------------------------------------------------------------------

# _sdtc_detect_node <repo_root>
# Inspect package.json scripts. Prefer test:unit as fast (unit only), then test.
# If both test:unit and test exist they are unambiguously ordered — not ambiguous.
_sdtc_detect_node() {
  local root="$1"
  local pkg="$root/package.json"
  [[ -f "$pkg" ]] || return 0

  # Extract presence of known script keys — portable grep, no jq/python required.
  local has_test has_test_unit has_lint has_test_ci
  has_test=$(grep -c '"test"[[:space:]]*:' "$pkg" 2>/dev/null || true)
  has_test_unit=$(grep -c '"test:unit"[[:space:]]*:' "$pkg" 2>/dev/null || true)
  has_lint=$(grep -c '"lint"[[:space:]]*:' "$pkg" 2>/dev/null || true)
  has_test_ci=$(grep -c '"test:ci"[[:space:]]*:' "$pkg" 2>/dev/null || true)

  # Determine package manager: prefer pnpm > yarn > npm
  local pm="npm"
  if [[ -f "$root/pnpm-lock.yaml" ]] || [[ -f "$root/.pnpmfile.cjs" ]]; then
    pm="pnpm"
  elif [[ -f "$root/yarn.lock" ]]; then
    pm="yarn"
  fi

  local fast_cmd="" full_cmd=""

  if [[ "${has_test_unit:-0}" -gt 0 && "${has_test:-0}" -gt 0 ]]; then
    # Unambiguous: unit for fast, full test for full
    fast_cmd="$pm run test:unit"
    full_cmd="$pm run test"
  elif [[ "${has_test_unit:-0}" -gt 0 ]]; then
    fast_cmd="$pm run test:unit"
  elif [[ "${has_test:-0}" -gt 0 ]]; then
    fast_cmd="$pm run test"
  fi

  # test:ci is a common full-suite alias
  if [[ "${has_test_ci:-0}" -gt 0 && -z "$full_cmd" && -n "$fast_cmd" ]]; then
    full_cmd="$pm run test:ci"
  fi

  # lint — lightweight, a fast candidate if no test scripts exist
  if [[ "${has_lint:-0}" -gt 0 && -z "$fast_cmd" ]]; then
    fast_cmd="$pm run lint"
  fi

  [[ -n "$fast_cmd" ]] && printf 'FAST:%s\n' "$fast_cmd"
  [[ -n "$full_cmd" ]] && printf 'FULL:%s\n' "$full_cmd"
}

# _sdtc_detect_python <repo_root>
# Detect pytest / pyproject.toml usage.
_sdtc_detect_python() {
  local root="$1"

  local has_pyproject=0 has_pytest_ini=0 has_setup_cfg=0
  [[ -f "$root/pyproject.toml" ]] && has_pyproject=1
  [[ -f "$root/pytest.ini" ]]    && has_pytest_ini=1
  [[ -f "$root/setup.cfg" ]]     && has_setup_cfg=1

  [[ $has_pyproject -eq 0 && $has_pytest_ini -eq 0 && $has_setup_cfg -eq 0 ]] && return 0

  # Confirm pytest is the test runner
  local pytest_marker=0
  if [[ $has_pyproject -eq 1 ]]; then
    grep -q '\[tool\.pytest' "$root/pyproject.toml" 2>/dev/null && pytest_marker=1
  fi
  [[ $has_pytest_ini -eq 1 ]] && pytest_marker=1
  if [[ $has_setup_cfg -eq 1 ]]; then
    grep -q '\[tool:pytest\]' "$root/setup.cfg" 2>/dev/null && pytest_marker=1
  fi

  # pyproject.toml with [build-system] is still likely pytest; emit as heuristic
  if [[ $pytest_marker -eq 0 && $has_pyproject -eq 1 ]]; then
    grep -q '\[build-system\]' "$root/pyproject.toml" 2>/dev/null && pytest_marker=1
  fi

  [[ $pytest_marker -eq 0 ]] && return 0

  # Fast: bare pytest; Full: pytest --tb=long -v (or with marker filter)
  local fast_cmd="pytest" full_cmd="pytest"

  # Check if slow/integration markers are declared — enables a tighter fast subset
  local has_markers=0
  if [[ $has_pyproject -eq 1 ]]; then
    grep -qE '^\s*markers\s*=' "$root/pyproject.toml" 2>/dev/null && has_markers=1
  fi
  if [[ $has_pytest_ini -eq 1 ]]; then
    grep -qE '^markers\s*=' "$root/pytest.ini" 2>/dev/null && has_markers=1
  fi

  if [[ $has_markers -eq 1 ]]; then
    fast_cmd='pytest -m "not slow and not integration"'
    full_cmd="pytest"
  fi

  printf 'FAST:%s\n' "$fast_cmd"
  [[ "$fast_cmd" != "$full_cmd" ]] && printf 'FULL:%s\n' "$full_cmd"
}

# _sdtc_detect_rust <repo_root>
# Detect Cargo.toml workspace or package.
_sdtc_detect_rust() {
  local root="$1"
  [[ -f "$root/Cargo.toml" ]] || return 0
  # Fast: lib tests only (quick compile); Full: all tests
  printf 'FAST:%s\n' "cargo test --lib"
  printf 'FULL:%s\n' "cargo test"
}

# ---------------------------------------------------------------------------
# _sdtc_collect_candidates <repo_root>
# Run all detectors and emit structured output:
#   STACK_COUNT:<n>
#   STACK_NAME:<name>       (one per detected stack)
#   FAST_CANDIDATE:<cmd>    (one per fast candidate)
#   FULL_CANDIDATE:<cmd>    (one per full candidate)
# ---------------------------------------------------------------------------
_sdtc_collect_candidates() {
  local root="$1"
  local -a fast_cands=() full_cands=() stack_names=()
  local line

  # Node
  local node_out
  node_out=$(_sdtc_detect_node "$root")
  if [[ -n "$node_out" ]]; then
    stack_names+=("node")
    while IFS= read -r line; do
      case "$line" in
        FAST:*) fast_cands+=("${line#FAST:}") ;;
        FULL:*) full_cands+=("${line#FULL:}") ;;
      esac
    done <<< "$node_out"
  fi

  # Python
  local py_out
  py_out=$(_sdtc_detect_python "$root")
  if [[ -n "$py_out" ]]; then
    stack_names+=("python")
    while IFS= read -r line; do
      case "$line" in
        FAST:*) fast_cands+=("${line#FAST:}") ;;
        FULL:*) full_cands+=("${line#FULL:}") ;;
      esac
    done <<< "$py_out"
  fi

  # Rust
  local rust_out
  rust_out=$(_sdtc_detect_rust "$root")
  if [[ -n "$rust_out" ]]; then
    stack_names+=("rust")
    while IFS= read -r line; do
      case "$line" in
        FAST:*) fast_cands+=("${line#FAST:}") ;;
        FULL:*) full_cands+=("${line#FULL:}") ;;
      esac
    done <<< "$rust_out"
  fi

  # Emit structured output for caller to parse
  printf 'STACK_COUNT:%d\n' "${#stack_names[@]}"
  local s
  for s in "${stack_names[@]}"; do
    printf 'STACK_NAME:%s\n' "$s"
  done
  local fc
  for fc in "${fast_cands[@]}"; do
    printf 'FAST_CANDIDATE:%s\n' "$fc"
  done
  local fu
  for fu in "${full_cands[@]}"; do
    printf 'FULL_CANDIDATE:%s\n' "$fu"
  done
}

# ---------------------------------------------------------------------------
# _sdtc_upsert_frontmatter_key <file> <key> <value>
# Sets or replaces a flat top-level key in the YAML frontmatter of <file>.
#
# Behaviour:
#   - If the key exists in the frontmatter block, its value is replaced in-place.
#   - If the key is absent from frontmatter but frontmatter exists, it is
#     appended before the closing --- marker.
#   - If no frontmatter block exists at all, a minimal block is prepended.
#
# Value is written WITHOUT surrounding quotes (matches the shape the resolver
# awk parser expects — it strips quotes via tr -d '"' / tr -d "'").
#
# Portability: uses tmp-file + mv (no sed -i — not BSD-portable with -i '').
# ---------------------------------------------------------------------------
_sdtc_upsert_frontmatter_key() {
  local file="$1" key="$2" value="$3"

  # Case: file does not exist — create minimal frontmatter
  if [[ ! -f "$file" ]]; then
    {
      printf -- '---\n'
      printf '%s: %s\n' "$key" "$value"
      printf -- '---\n'
    } > "$file"
    return 0
  fi

  local tmp
  tmp="${file}.sdtc.$$"

  # Check whether a complete frontmatter block exists (>=2 --- lines)
  local dash_count
  dash_count=$(grep -c '^---$' "$file" 2>/dev/null || true)
  if [[ "${dash_count:-0}" -lt 2 ]]; then
    # No complete frontmatter — prepend one
    {
      printf -- '---\n'
      printf '%s: %s\n' "$key" "$value"
      printf -- '---\n'
      cat "$file"
    } > "$tmp"
    mv "$tmp" "$file"
    return 0
  fi

  # Check if the key already appears in the frontmatter block
  local key_exists=0
  # awk: track inside-frontmatter state; exit on second ---
  if awk -v k="$key" \
    '/^---$/{n++; if(n==2) exit; next}
     n==1 && index($0, k":") == 1 {found=1; exit}
     END{exit !found}' "$file" 2>/dev/null; then
    # Review: code-reviewer — index() is a string-prefix check (POSIX awk, BSD-portable);
    # regex match $0 ~ "^"k":" would corrupt on keys with regex metacharacters
    key_exists=1
  fi

  if [[ $key_exists -eq 1 ]]; then
    # Replace the key's value only within the frontmatter block
    awk -v k="$key" -v v="$value" '
      /^---$/ { n++; print; next }
      n==1 && index($0, k":") == 1 { print k ": " v; next }
      { print }
    ' "$file" > "$tmp"
    # Review: code-reviewer — index() replaces regex match to handle metacharacters in key names
  else
    # Key absent — insert before the closing --- (second ---)
    awk -v k="$key" -v v="$value" '
      /^---$/ {
        n++
        if (n == 2) { print k ": " v }
        print; next
      }
      { print }
    ' "$file" > "$tmp"
  fi

  mv "$tmp" "$file"
}

# ---------------------------------------------------------------------------
# _sdtc_key_present <file> <key>
# Returns 0 (true) if <key>: appears as a non-empty flat top-level frontmatter
# key in <file>. Returns 1 otherwise.
# ---------------------------------------------------------------------------
_sdtc_key_present() {
  local file="$1" key="$2"
  [[ -f "$file" ]] || return 1
  local val
  val=$(awk -v k="$key" '
    /^---$/{n++; if(n==2) exit; next}
    n==1 && index($0, k":") == 1 {
      # Review: code-reviewer — index() replaces $0 ~ "^"k":" to avoid metacharacter corruption
      sub("^"k":[[:space:]]*","")
      gsub(/^[[:space:]]+|[[:space:]]+$/,"")
      gsub(/^"|"$/,"")
      gsub(/^'"'"'|'"'"'$/,"")
      print
      exit
    }
  ' "$file" 2>/dev/null)
  [[ -n "$val" ]]
}

# ---------------------------------------------------------------------------
# sdtc_detect_and_write_test_cmds <repo_root>
#                                 [--non-interactive [fast_cmd] [full_cmd]]
#                                 [--force]
#
# Main public entry point (call after sourcing this file).
# Detect the test command for <repo_root> and write fast_test_cmd + full_test_cmd
# into coordinator.local.md.
#
# See file header for full argument/exit-code documentation.
# ---------------------------------------------------------------------------
sdtc_detect_and_write_test_cmds() {
  local repo_root=""
  local non_interactive=0
  local preset_fast=""
  local preset_full=""
  local force=0

  # ---- Argument parsing ----
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --non-interactive)
        non_interactive=1
        shift
        # Optionally followed by two preset values (not starting with --)
        if [[ $# -gt 0 && "$1" != --* ]]; then
          preset_fast="$1"; shift
        fi
        if [[ $# -gt 0 && "$1" != --* ]]; then
          preset_full="$1"; shift
        fi
        ;;
      --force)
        force=1; shift
        ;;
      --help|-h)
        # Print the header comment block from this file as usage
        grep '^#' "${BASH_SOURCE[0]}" | head -60 | sed -E 's/^#[[:space:]]?//'
        # Review: code-reviewer — \? is a GNU BRE extension; -E + [[:space:]]? is BSD-portable
        return 0
        ;;
      -*)
        echo "[setup-detect-test-cmd] ERROR: unknown flag '$1'" >&2
        return 1
        ;;
      *)
        if [[ -z "$repo_root" ]]; then
          repo_root="$1"
        else
          echo "[setup-detect-test-cmd] ERROR: unexpected argument '$1'" >&2
          return 1
        fi
        shift
        ;;
    esac
  done

  # Honour env-var equivalent
  [[ "${SETUP_DETECT_NONINTERACTIVE:-0}" == "1" ]] && non_interactive=1

  # ---- Validate repo_root ----
  if [[ -z "$repo_root" ]]; then
    echo "[setup-detect-test-cmd] ERROR: repo_root argument is required" >&2
    return 1
  fi
  if [[ ! -d "$repo_root" ]]; then
    echo "[setup-detect-test-cmd] ERROR: repo_root '$repo_root' does not exist" >&2
    return 1
  fi

  local local_md="$repo_root/coordinator.local.md"

  # ---- Validate coordinator.local.md exists and has frontmatter ----
  # This is a required pre-condition — coordinator:repo-setup creates this file;
  # if it is missing, the caller has a setup ordering bug. We do NOT auto-create it.
  if [[ ! -f "$local_md" ]]; then
    echo "[setup-detect-test-cmd] ERROR: $local_md not found." >&2
    echo "  Remediation: run coordinator:repo-setup first to create coordinator.local.md," >&2
    echo "  or create it manually with a YAML frontmatter block (--- ... ---)." >&2
    return 3
  fi

  local dash_count
  dash_count=$(grep -c '^---$' "$local_md" 2>/dev/null || true)
  if [[ "${dash_count:-0}" -lt 2 ]]; then
    echo "[setup-detect-test-cmd] ERROR: $local_md has no valid YAML frontmatter (need two --- lines)." >&2
    echo "  Remediation: add a frontmatter block at the top of the file:" >&2
    echo "    ---" >&2
    echo "    project_type: <type>" >&2
    echo "    ---" >&2
    return 3
  fi

  # ---- Idempotency check ----
  # If both keys already exist and --force is not set, exit 2 (no-op).
  if [[ $force -eq 0 ]] \
      && _sdtc_key_present "$local_md" "fast_test_cmd" \
      && _sdtc_key_present "$local_md" "full_test_cmd"; then
    echo "[setup-detect-test-cmd] fast_test_cmd + full_test_cmd already present — skipping (pass --force to overwrite)" >&2
    return 2
  fi

  # ---- Preset fast-path ----
  # If the caller supplied preset commands (--non-interactive fast full),
  # skip detection entirely and write them directly.
  if [[ -n "$preset_fast" ]]; then
    local pf="$preset_fast"
    local pF="${preset_full:-$preset_fast}"
    _sdtc_upsert_frontmatter_key "$local_md" "fast_test_cmd" "$pf" || return 1
    _sdtc_upsert_frontmatter_key "$local_md" "full_test_cmd" "$pF" || return 1
    echo "[setup-detect-test-cmd] wrote preset commands:" >&2
    echo "  fast_test_cmd: $pf" >&2
    echo "  full_test_cmd: $pF" >&2
    return 0
  fi

  # ---- Detection phase ----
  echo "[setup-detect-test-cmd] Scanning $repo_root for test stack markers..." >&2

  local collected
  collected=$(_sdtc_collect_candidates "$repo_root")

  local -a FAST_CANDIDATES=() FULL_CANDIDATES=() STACK_NAMES=()
  local stack_count=0
  local line
  while IFS= read -r line; do
    case "$line" in
      STACK_COUNT:*) stack_count="${line#STACK_COUNT:}" ;;
      STACK_NAME:*)  STACK_NAMES+=("${line#STACK_NAME:}") ;;
      FAST_CANDIDATE:*) FAST_CANDIDATES+=("${line#FAST_CANDIDATE:}") ;;
      FULL_CANDIDATE:*) FULL_CANDIDATES+=("${line#FULL_CANDIDATE:}") ;;
    esac
  done <<< "$collected"

  local num_fast="${#FAST_CANDIDATES[@]}"
  local num_full="${#FULL_CANDIDATES[@]}"

  # ---- Case: nothing detected ----
  if [[ $num_fast -eq 0 && $num_full -eq 0 ]]; then
    echo "[setup-detect-test-cmd] No test stack markers found in $repo_root." >&2
    echo "  Checked: package.json (Node), pyproject.toml/pytest.ini (Python), Cargo.toml (Rust)." >&2
    echo "  Remediation: set fast_test_cmd manually in coordinator.local.md." >&2
    return 2
  fi

  # ---- Case: ambiguous — multiple stacks, multiple fast candidates ----
  # DETECT-THEN-FAIL-LOUD: if multiple fast candidates exist from distinct stacks
  # (or within a single stack), surface all and exit 1.
  if [[ $num_fast -gt 1 ]]; then
    echo "[setup-detect-test-cmd] AMBIGUOUS: multiple fast_test_cmd candidates detected." >&2
    echo "  Stacks: ${STACK_NAMES[*]:-unknown}" >&2
    echo "  Candidates:" >&2
    local _i
    for (( _i=0; _i<num_fast; _i++ )); do
      echo "    [$_i] ${FAST_CANDIDATES[$_i]}" >&2
    done
    echo "" >&2
    echo "  Resolve by passing a preset to sdtc_detect_and_write_test_cmds, e.g.:" >&2
    echo "    sdtc_detect_and_write_test_cmds \"$repo_root\" --non-interactive \"<fast_cmd>\" \"<full_cmd>\"" >&2
    echo "  Or set fast_test_cmd manually in coordinator.local.md." >&2
    return 1
  fi

  # ---- Single candidate ----
  local proposed_fast="${FAST_CANDIDATES[0]:-}"
  local proposed_full="${FULL_CANDIDATES[0]:-}"
  # If full equals fast or is empty, use fast for both (resolver handles missing full
  # gracefully, but writing it makes the config explicit)
  [[ -z "$proposed_full" ]] && proposed_full="$proposed_fast"

  echo "[setup-detect-test-cmd] Detected stack(s): ${STACK_NAMES[*]:-unknown}" >&2
  echo "  fast_test_cmd: $proposed_fast" >&2
  echo "  full_test_cmd: $proposed_full" >&2

  # ---- Confirmation phase ----
  if [[ $non_interactive -eq 0 ]]; then
    local answer
    printf '\nAccept these commands? [Y/n] ' >&2
    read -r answer </dev/tty
    case "${answer:-Y}" in
      [Yy]*|"") : ;;  # accept
      *)
        echo "[setup-detect-test-cmd] Declined. No changes written." >&2
        return 1
        ;;
    esac
  fi

  # ---- Write phase ----
  _sdtc_upsert_frontmatter_key "$local_md" "fast_test_cmd" "$proposed_fast" || return 1
  _sdtc_upsert_frontmatter_key "$local_md" "full_test_cmd" "$proposed_full" || return 1

  echo "[setup-detect-test-cmd] Done. Keys written to coordinator.local.md:" >&2
  echo "  fast_test_cmd: $proposed_fast" >&2
  echo "  full_test_cmd: $proposed_full" >&2
  return 0
}

# ---------------------------------------------------------------------------
# Direct-execution shim — when run as a script (not sourced), delegate to the
# function with translated flags.
#
# Accepts: [--root <path>] [--non-interactive] [--force] [--help|-h]
# This keeps the file usable both as a sourced library and as a standalone tool.
# ---------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  _direct_root=""
  _direct_args=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --root) shift; _direct_root="$1"; shift ;;
      *) _direct_args+=("$1"); shift ;;
    esac
  done
  _direct_root="${_direct_root:-$PWD}"
  sdtc_detect_and_write_test_cmds "$_direct_root" "${_direct_args[@]}"
  exit $?
fi
