#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# coordinator-trusted-root-guard.sh — shared trusted-prefix guard for every
# site that resolves a coordinator content root via CLAUDE_PLUGIN_ROOT.
#
# Purpose: promotes the byte-identical `_cc_doe`/`_cc_trusted` trust-core
# (previously duplicated inline at ~68 call sites — 46 Variant A + 22
# Variant B, per the C1 substrate map) into ONE sourced function. Exposes a
# single public function: coordinator_trusted_root_guard.
#
# Spec backlink: docs/plans/2026-07-09-resolver-unification-v3split-01.md § C5
# Canonical definition (prose + trust-core listing) lives in
# coordinator/snippets/cc-root-source-guard.md — this file is the sourced
# implementation; the snippet is the doc-of-record. Keep them in sync by
# hand (the snippet is dynamic-discovery, NOT registry-enrolled — see the
# snippet's own header note).
#
# Trust boundary: a resolved root is trusted iff it sits under one of three
# anchors — (1) the marketplace-cache install (${CLAUDE_HOME:-$HOME}/.claude/),
# (2) the DoE clone at the `.doe-root` sentinel's content, or (3) an
# arbitrary --plugin-dir checkout with the explicit
# COORDINATOR_PLUGIN_ROOT_TRUSTED=1 developer opt-out — AND does not contain
# a `/..` traversal segment (closes the $HOME/.claude/../../tmp/evil bypass
# that plain prefix-matching would miss; realpath is banned per DR-148).
#
# --mode is REQUIRED and has NO default. This is the load-bearing corpus
# fact: the two modes are NOT interchangeable safety levels — they are
# byte-identical trust-core checks wired to two functionally opposite tails
# (Variant A hard-exits; Variant B degrades and warns, never exiting). A
# defaulted mode is exactly the mechanism by which a Variant-B advisory-hook
# site would get silently promoted to hard-exit during mechanical migration,
# terminating a hook chain it must never terminate. Every call site names
# its mode explicitly; there is no "sensible default" here.
#
# ONE function, TWO modes — not two functions. Splitting into
# coordinator_trusted_root_guard_loud / _open would re-duplicate the
# identical trust-core across two bodies, reintroducing the exact drift
# this promotion exists to kill.
#
# No bash-4 nameref (`local -n`): DR-148 requires bash 3.2 syntax
# compatibility, and 3.2 has no namerefs. The function therefore does NOT
# mutate the caller's root variable by name — it takes the resolved value as
# an explicit argument, returns trust status via exit code, and (in
# fail-open mode) prints the caller's desired replacement value to stdout
# for the caller to assign. Callers keep their own LHS variable name; the
# guard never needs to know it.
#
# Usage:
#   coordinator_trusted_root_guard --mode=fail-loud --root="$_cc_root" --site="$0"
#     Exit 0 if trusted. Exit 1 (with an ERROR line on stderr) and hard-exit
#     the caller's script if untrusted — Variant A: skills / commands / lib /
#     bin sites where sourcing an untrusted root must not proceed silently.
#
#   coordinator_trusted_root_guard --mode=fail-open --root="$_cc_root" --site="$0"
#     Exit 0 if trusted (caller's root variable is unchanged). Exit 1 if
#     untrusted — the caller must then blank its own root variable (the
#     function cannot do this via nameref on bash 3.2); prints exactly one
#     WARNING line to stderr when the anomaly is security-relevant (root was
#     non-empty-and-existing-but-untrusted), stays silent on routine absence
#     (empty or non-existent root). NEVER hard-exits — advisory hooks must
#     not terminate the hook chain.
#
#   Typical Variant B call-site shape (since the function cannot blank the
#   caller's variable itself):
#     if ! coordinator_trusted_root_guard --mode=fail-open --root="$_cc_root" --site="$0"; then
#       _cc_root=''
#     fi
#
# This lib is sourced, not executed — no 'set -e' (a sourced script's
# 'set -e' leaks into the caller's shell and changes its error-handling
# semantics). 'set -uo pipefail' is safe to source.
# ---------------------------------------------------------------------------
set -uo pipefail

# ---------------------------------------------------------------------------
# coordinator_trusted_root_guard — trust-check a resolved CLAUDE_PLUGIN_ROOT-
# derived path against the shared trust-core, then apply the named mode's
# tail behavior.
#
# Args (all named, order-independent):
#   --mode=fail-loud|fail-open   REQUIRED. No default — see header rationale.
#   --root=<path>                REQUIRED. The resolved root value to check
#                                 (the site's LHS var value, passed by value —
#                                 no nameref, see header).
#   --site=<label>                Optional. Included in the fail-loud ERROR
#                                 line for caller identification; defaults to
#                                 "coordinator root" if omitted.
#
# Returns (exit code):
#   0  — root is trusted. Caller proceeds unchanged in both modes.
#   1  — root is untrusted.
#         --mode=fail-loud: prints ERROR to stderr and calls `exit 1` —
#           terminates the CALLING SCRIPT (not a subshell no-op: this
#           function must be invoked in the caller's main shell, not inside
#           a command-substitution subshell, or the exit only ends the
#           subshell and the caller silently proceeds untrusted).
#         --mode=fail-open: prints at most one WARNING to stderr (only when
#           the anomaly is security-relevant — root non-empty and existing
#           but untrusted; stays silent on routine absence) and returns 1
#           WITHOUT exiting. Caller is responsible for blanking its own root
#           variable on a 1 return (see header usage example) — the function
#           has no nameref path to do this on bash 3.2.
# ---------------------------------------------------------------------------
coordinator_trusted_root_guard() {
  local _mode=""
  local _root=""
  local _site="coordinator root"

  local _arg
  for _arg in "$@"; do
    case "$_arg" in
      --mode=*) _mode="${_arg#--mode=}" ;;
      --root=*) _root="${_arg#--root=}" ;;
      --site=*) _site="${_arg#--site=}" ;;
      *)
        echo "coordinator_trusted_root_guard: unrecognized arg '$_arg'" >&2
        return 1
        ;;
    esac
  done

  case "$_mode" in
    fail-loud|fail-open) ;;
    "")
      echo "coordinator_trusted_root_guard: --mode is REQUIRED (fail-loud|fail-open) — no default is provided on purpose; see coordinator/snippets/cc-root-source-guard.md" >&2
      return 1
      ;;
    *)
      echo "coordinator_trusted_root_guard: unrecognized --mode='$_mode' (expected fail-loud|fail-open)" >&2
      return 1
      ;;
  esac

  # --- shared trust-core (byte-identical to the snippet's documented core) ---
  local _cc_doe
  _cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
  _cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
  local _cc_trusted=0
  case "$_root" in
    "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
  esac
  [ -n "$_cc_doe" ] && case "$_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
  case "$_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
  [ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
  # --- end shared trust-core ---

  if [ "$_cc_trusted" = 1 ]; then
    return 0
  fi

  case "$_mode" in
    fail-loud)
      echo "ERROR: ${_site} '${_root}' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2
      exit 1
      ;;
    fail-open)
      if [ -n "$_root" ] && [ -d "$_root" ]; then
        echo "[coordinator] WARNING: '${_root}' outside trusted prefix — hook degraded" >&2
      fi
      return 1
      ;;
  esac
}
