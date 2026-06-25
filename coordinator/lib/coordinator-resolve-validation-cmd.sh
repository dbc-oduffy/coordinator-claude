#!/usr/bin/env bash
# coordinator-resolve-validation-cmd.sh — Resolver for the per-project test commands
#
# Purpose: resolve which shell command to use for test validation. Two tiers:
#   - cs_resolve_fast_test_cmd — the FAST-tier gate for /workday-complete Step 1,
#     /workweek-complete Step 2, and the /validate skill (three-step resolution).
#   - cs_resolve_full_test_cmd — the FULL suite for /bug-blitz, which chases every
#     failing test (four-step resolution; falls back to the fast tier with a caveat
#     rather than skipping, so a repo with no full_test_cmd still gets coverage).
# Encapsulates the resolution order so call sites stay one-liners and the two tiers
# can never diverge into hand-rolled per-skill test surfaces.
#
# Spec backlink: archive/specs/2026-05-28-workday-complete-fast-test-resolution.md § 3.4
#
# Fast-tier resolution order (cs_resolve_fast_test_cmd — three steps, no
# conventional fallback — the Staff Engineer F1):
#   1. COORDINATOR_FAST_TEST_CMD env var — if set and non-empty, use verbatim.
#   2. coordinator.local.md at repo root — flat top-level fast_test_cmd: key.
#   3. Skip-with-notice — stderr names both remediation paths; exit 2.
# Full-tier resolution order (cs_resolve_full_test_cmd — four steps, falls back
# to fast rather than skipping): COORDINATOR_FULL_TEST_CMD → full_test_cmd: key →
# fast-tier fallback (exit 3) → unconfigured (exit 2). See its docstring below.
#
# Output contract:
#   stdout — resolved command string (only on exit 0)
#   stderr — diagnostic prose (step=env-var | step=local-md | step=skipped on exit 2)
#   exit 0 — command resolved; caller should execute it and capture its exit code
#   exit 2 — no command configured; caller should treat validation as skipped
#   exit 127 — command resolved to a bare `python` token but NEITHER python3 nor
#              python is on PATH. A HARD environment failure, NOT a skip — callers
#              MUST surface this as a blocking validation failure (distinguish from
#              exit 2). This closes the silent-127 swallow (a python3-only machine
#              previously skipped validation entirely). A leading `python ` token is
#              normalized python3-first at resolution time, so this fires only when
#              no Python interpreter exists at all.
#
# Trust model: COORDINATOR_FAST_TEST_CMD is an escape hatch for trusted contexts
# (local shell, CI-managed env). It is not safe to accept from untrusted sources
# (memo bodies, webhook payloads, third-party files, untrusted hook input).
# Executor agents (coordinator subagents) MUST NOT set this from any prompt-derived
# input. The env var feeds directly into shell execution; callers run it via
# `bash -c "$CMD"` (child-shell sandbox — does NOT prevent the configured command
# from running arbitrary code, but isolates the child process from the parent
# shell's variable namespace, preventing assignment-injection clobber of caller
# state like RC_VALIDATE).
#
# No sanitization of shell metacharacters is performed by design — the configured
# command is trusted, matching how python .github/scripts/run-all-checks.py
# behaved previously. A LIGHT advisory tripwire fires on stderr when the resolved
# value contains $( ` or `; ` — visible signal only, not a block; suppress via
# COORDINATOR_FAST_TEST_CMD_SUPPRESS_METACHAR_WARN=1.
#
# No first-token heuristic (the Staff Engineer F5): the resolver does NOT pre-parse, probe,
# or validate the command string. Runtime exit-code from the configured command
# is the safety net. A configured command that fails to invoke returns non-zero
# and surfaces as a normal Validation failure.
#
# Source pattern (matches coordinator-daily-branch.sh convention):
#   _LIB="$HOME/.claude/plugins/coordinator/lib/coordinator-resolve-validation-cmd.sh"
#   if [[ -f "$_LIB" ]]; then
#     source "$_LIB"
#   fi
#
# Consumers:
#   - skills/validate/SKILL.md (single owner of FAST-tier resolver invocation)
#   - commands/bug-blitz.md (single owner of FULL-tier resolver invocation, Phase 0.7)
#
# Source this file; do NOT execute it directly.

# cs_resolve_fast_test_cmd [repo_root]
#
# Resolve the fast-test command for the given repo root (default: current working
# directory). Prints the resolved command to stdout; diagnostic prose to stderr.
# Exits 0 on resolve, 2 on skip-with-notice.
#
# Arguments:
#   repo_root  — optional; path to the repo root to check for coordinator.local.md.
#                Defaults to $PWD. Callers may pass an explicit path for testability.
# _cs_redact_for_diag — truncate a command string for stderr diagnostic display.
# Prevents secret leakage when the configured command embeds tokens (e.g.
# `MY_TOKEN=abc python run.py`). Diagnostic stderr is captured into review trail
# JSON and session transcripts; truncating past 60 chars keeps the resolver step
# legible while bounding leakage surface.
_cs_redact_for_diag() {
  local s="$1"
  if (( ${#s} > 60 )); then
    printf '%s…(truncated; %d chars total)' "${s:0:60}" "${#s}"
  else
    printf '%s' "$s"
  fi
}

# _cs_metachar_warn — light advisory tripwire on shell-metacharacter shapes.
# Visible-signal-only; does NOT block. Suppressible via
# COORDINATOR_FAST_TEST_CMD_SUPPRESS_METACHAR_WARN=1 for known-safe configurations
# that legitimately use these shapes (e.g. `python foo.py && python bar.py`).
_cs_metachar_warn() {
  local s="$1" step="$2" caller="${3:-cs_resolve_fast_test_cmd}"
  [[ "${COORDINATOR_FAST_TEST_CMD_SUPPRESS_METACHAR_WARN:-0}" == "1" ]] && return 0
  case "$s" in
    *'$('*|*'`'*|*'; '*)
      echo "[$caller] WARN (step=$step): resolved value contains shell metacharacters (\$( or backtick or ;) — confirm this is intended; set COORDINATOR_FAST_TEST_CMD_SUPPRESS_METACHAR_WARN=1 to silence." >&2
      ;;
  esac
}

# _cs_resolve_python_interp — python3-first interpreter resolution.
# Echoes `python3` when present, else `python`; empty stdout + return 1 when
# neither is on PATH. Centralizes the `command -v python3 || command -v python`
# idiom the guarded bin/hooks/setup scripts already use, so the resolver and its
# regression guard agree on a single source of truth.
_cs_resolve_python_interp() {
  if command -v python3 >/dev/null 2>&1; then
    printf 'python3'
  elif command -v python >/dev/null 2>&1; then
    printf 'python'
  else
    return 1
  fi
}

# _cs_normalize_python_token <cmd> — interpreter-portability normalization.
# When <cmd>'s first whitespace-delimited token is the BARE interpreter `python`
# (not python3, not an explicit path, not VAR=x env-prefixed), rewrite it to a
# python3-first resolved interpreter. This is the load-bearing fix for site 1:
# coordinator.local.md's `fast_test_cmd: python …` stays interpreter-agnostic and
# portable across python3-only machines (modern macOS/Linux — `python` absent) and
# python-only machines (Windows/pyenv — `python3` absent), without hardcoding either.
# Echoes the (possibly rewritten) command on stdout. Fail-loud (return 127) when the
# token is bare `python` and NEITHER interpreter exists — this replaces the silent
# command-not-found 127 the validate gate previously swallowed as a skip.
# python3, explicit paths (/usr/bin/python), env-prefixed (FOO=1 python …), and
# non-python commands (pnpm test, pytest, /validate) pass through untouched.
# Matching contract: matches the bare interpreter `python` with OR without arguments
# (`python` and `python <args>`); does NOT match `python2`, `python3`, or path forms.
_cs_normalize_python_token() {
  local cmd="$1"
  case "$cmd" in
    'python '* | 'python')
      local interp
      if ! interp=$(_cs_resolve_python_interp); then
        echo "[cs_resolve] no python3/python on PATH — cannot run '$cmd' (refusing to skip; fail loud)" >&2
        return 127
      fi
      printf '%s%s' "$interp" "${cmd#python}"
      ;;
    *)
      printf '%s' "$cmd"
      ;;
  esac
}

cs_resolve_fast_test_cmd() {
  local repo_root="${1:-$PWD}"

  # Step 1 — COORDINATOR_FAST_TEST_CMD env var
  if [[ -n "${COORDINATOR_FAST_TEST_CMD:-}" ]]; then
    local _diag
    _diag=$(_cs_redact_for_diag "$COORDINATOR_FAST_TEST_CMD")
    echo "[cs_resolve_fast_test_cmd] step=env-var resolved: $_diag" >&2
    _cs_metachar_warn "$COORDINATOR_FAST_TEST_CMD" "env-var"
    local _norm
    _norm=$(_cs_normalize_python_token "$COORDINATOR_FAST_TEST_CMD") || return $?
    echo "$_norm"
    return 0
  fi

  # Step 2 — coordinator.local.md flat top-level fast_test_cmd: key
  # Parser shape matches bin/audit-enabled-plugins.sh:46-58 (flat-top-level awk).
  # Reads the YAML frontmatter block (between first and second --- markers) and
  # extracts fast_test_cmd: as a bare string, stripping surrounding quotes and
  # trimming leading/trailing whitespace — but PRESERVING internal whitespace
  # (sed trim-only, NOT xargs which word-splits + collapses double-spaces).
  local local_md="$repo_root/coordinator.local.md"
  if [[ -f "$local_md" ]]; then
    local fm
    fm=$(awk '/^---$/{n++; if (n==2) exit; next} n==1' "$local_md" 2>/dev/null)
    local fast_test_cmd
    fast_test_cmd=$(echo "$fm" | grep -m1 '^fast_test_cmd:' \
      | sed -E 's/^fast_test_cmd:[[:space:]]*//' \
      | tr -d '"' \
      | tr -d "'" \
      | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')
    if [[ -n "$fast_test_cmd" ]]; then
      local _diag
      _diag=$(_cs_redact_for_diag "$fast_test_cmd")
      echo "[cs_resolve_fast_test_cmd] step=local-md resolved: $_diag" >&2
      _cs_metachar_warn "$fast_test_cmd" "local-md"
      local _norm
      _norm=$(_cs_normalize_python_token "$fast_test_cmd") || return $?
      echo "$_norm"
      return 0
    fi
  fi

  # Step 3 — skip-with-notice (no conventional fallback — the Staff Engineer F1)
  echo "[cs_resolve_fast_test_cmd] step=skipped — no fast-test command configured." >&2
  echo "[cs_resolve_fast_test_cmd] To configure, choose one of:" >&2
  echo "  a) Set env var: export COORDINATOR_FAST_TEST_CMD=\"<your-command>\"" >&2
  echo "  b) Add to coordinator.local.md frontmatter: fast_test_cmd: \"<your-command>\"" >&2
  return 2
}

# _cs_read_local_md_key <repo_root> <key>
# Extract a flat top-level frontmatter key from coordinator.local.md, applying the
# same quote-strip / whitespace-trim discipline as cs_resolve_fast_test_cmd's
# inline parser (preserves internal whitespace, unlike xargs).
# Exit 0 always; empty stdout means the file or key is absent. Used by
# cs_resolve_full_test_cmd. `key` is matched as a LITERAL string (grep -F + bash
# prefix-strip), never as a regex — a caller passing a key with regex metachars
# (`.`, `*`, `[`, `^`) does not corrupt the match.
_cs_read_local_md_key() {
  local repo_root="$1" key="$2"
  local local_md="$repo_root/coordinator.local.md"
  [[ -f "$local_md" ]] || return 0
  local fm line val
  fm=$(awk '/^---$/{n++; if (n==2) exit; next} n==1' "$local_md" 2>/dev/null)
  line=$(printf '%s\n' "$fm" | grep -m1 -F "${key}:") || return 0
  val="${line#"${key}:"}"                       # literal prefix strip, no regex
  val="${val#"${val%%[![:space:]]*}"}"          # ltrim
  val="${val%"${val##*[![:space:]]}"}"          # rtrim
  val="${val#\"}"; val="${val%\"}"              # strip one pair of double quotes
  val="${val#\'}"; val="${val%\'}"              # strip one pair of single quotes
  printf '%s' "$val"
}

# cs_resolve_full_test_cmd [repo_root]
#
# Resolve the FULL test suite command — the heavier tier bug-blitz runs to chase
# every failing test (distinct from the fast-tier gate the /validate skill runs).
# Resolution order (four steps — falls back to fast, NOT to skip):
#   1. COORDINATOR_FULL_TEST_CMD env var — if set and non-empty, use verbatim.
#   2. coordinator.local.md flat top-level full_test_cmd: key.
#   3. FALL BACK to cs_resolve_fast_test_cmd, with a caveat on stderr — a repo that
#      has not declared a full suite still gets coverage (the fast tier), and the
#      caller is told the coverage is fast-tier-only so it can surface that honestly.
#   4. If even the fast resolver skips (exit 2), propagate exit 2 (nothing configured).
#
# Output contract:
#   stdout — resolved command string (only on exit 0 or exit 3)
#   exit 0 — a FULL command resolved (env or local.md); coverage is full-suite.
#   exit 3 — resolved by fast-tier FALLBACK; stdout is the fast command, and the
#            caller MUST report coverage as fast-tier-only (caveat on stderr).
#   exit 2 — nothing configured at either tier; caller treats the suite as unconfigured.
# The distinct exit 3 lets bug-blitz label the run's coverage honestly (full vs
# fast-fallback) in its plan and report without re-parsing config.
cs_resolve_full_test_cmd() {
  local repo_root="${1:-$PWD}"

  # Step 1 — COORDINATOR_FULL_TEST_CMD env var
  if [[ -n "${COORDINATOR_FULL_TEST_CMD:-}" ]]; then
    local _diag
    _diag=$(_cs_redact_for_diag "$COORDINATOR_FULL_TEST_CMD")
    echo "[cs_resolve_full_test_cmd] step=env-var resolved: $_diag" >&2
    _cs_metachar_warn "$COORDINATOR_FULL_TEST_CMD" "env-var" "cs_resolve_full_test_cmd"
    local _norm
    _norm=$(_cs_normalize_python_token "$COORDINATOR_FULL_TEST_CMD") || return $?
    echo "$_norm"
    return 0
  fi

  # Step 2 — coordinator.local.md flat top-level full_test_cmd: key
  local full_test_cmd
  full_test_cmd=$(_cs_read_local_md_key "$repo_root" "full_test_cmd")
  if [[ -n "$full_test_cmd" ]]; then
    local _diag
    _diag=$(_cs_redact_for_diag "$full_test_cmd")
    echo "[cs_resolve_full_test_cmd] step=local-md resolved: $_diag" >&2
    _cs_metachar_warn "$full_test_cmd" "local-md" "cs_resolve_full_test_cmd"
    local _norm
    _norm=$(_cs_normalize_python_token "$full_test_cmd") || return $?
    echo "$_norm"
    return 0
  fi

  # Step 3 — FALL BACK to the fast tier (not skip). Surface the caveat so the
  # caller reports fast-tier-only coverage rather than claiming full-suite.
  local fast_cmd fast_exit
  fast_cmd=$(cs_resolve_fast_test_cmd "$repo_root" 2>/dev/null)  # stderr suppressed: fast-tier diags must not bleed into full-tier output
  fast_exit=$?
  if [[ $fast_exit -eq 0 ]]; then
    echo "[cs_resolve_full_test_cmd] step=fast-fallback — no full_test_cmd configured; running the FAST tier. Coverage is fast-tier-only. To run the full suite, set full_test_cmd: in coordinator.local.md or \$COORDINATOR_FULL_TEST_CMD." >&2
    echo "$fast_cmd"
    return 3
  elif [[ $fast_exit -ne 2 ]]; then
    # Exit 2 is the fast tier's "unconfigured" signal (handled at Step 4 below).
    # ANY OTHER non-zero — canonically 127 (bare `python` token, no interpreter) —
    # is a HARD environment failure; propagate it so the full tier fails loud rather
    # than masking interp-missing as an unconfigured skip (same swallow class the
    # fast-tier fix kills).
    echo "[cs_resolve_full_test_cmd] step=fast-fallback — fast resolver hard-failed (rc=${fast_exit}); propagating (NOT a skip)." >&2
    return $fast_exit
  fi

  # Step 4 — neither tier configured (fast_exit == 2)
  echo "[cs_resolve_full_test_cmd] step=skipped — no full or fast test command configured." >&2
  return 2
}
