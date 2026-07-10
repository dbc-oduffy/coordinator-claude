#!/usr/bin/env bash
# wsc-commit.sh — Workstream-complete commit ceremony helper
#
# Purpose: Compose the Step 2.67 commit message, run the structural gate
# (check-workstream-complete-deletion-blocks.sh), then issue the explicit-
# pathspec commit. Extracts the MECHANISM from SKILL.md Step 3 step 1.5–2;
# the caller retains judgment: WSC_PATHS construction, subject/prose authoring,
# and the Deleted/Kept enumeration.
#
# Usage:
#   wsc-commit.sh --subject <subject> [--prose <prose>]
#                 [--deleted <path>]...
#                 [--kept '<path> — <reason>']...
#                 [--swept-rename '<src>|<dst>']...
#                 [--dry-run]
#                 -- <commit-path>...
#
# --swept-rename '<src>|<dst>' (repeatable): fold a caller-managed archival rename
#   into this commit. The caller must have already run `git mv src dst` so that
#   src is staged-deleted and dst is staged-added. The gate scope excludes swept
#   paths (EM-authored paths only); the commit pathspec includes both src and dst
#   so the rename folds atomically. Malformed values (no |, empty src, empty dst,
#   multiple |) exit 2. A pure archival-fold invocation (--swept-rename only, zero
#   -- paths) is valid; the gate is skipped when no EM-authored paths are present
#   and the message has no Step 2.67 block.
#
# Gate scope vs commit pathspec:
#   gate_paths   = COMMIT_PATHS + DELETED_PATHS  (EM-authored only; swept excluded)
#   commit_paths = gate_paths + SWEPT_SRCS + SWEPT_DSTS  (full rename included)
#
# CLI contract: pinned by tests/wsc-asic/test-wsc-commit-parity.sh and
#   tests/wsc-asic/test-wsc-commit-swept-rename.sh.
# Spec backlink: skills/workstream-complete/SKILL.md § Step 3 step 1.5–2
# Portability: bash >=4 + BSD coreutils (DR-148). No sed -i, date %N,
#              grep -P, GNU realpath, or hardcoded absolute paths.
#
# Exit codes:
#   0 — commit landed (or --dry-run message printed to stdout)
#   1 — gate validation failed (message vs staged reality mismatch)
#   2 — usage / invocation error
#   3 — environment error (not in a git repo; applies even with --dry-run)
#   (other non-zero) — git sub-command failure; raw exit code propagated via set -e
#                      (e.g., exit 128 for absent pathspec; no collision with 0/1/2/3)
# Review: code-reviewer — F1: document raw-propagated git exit codes; F6: --dry-run repo requirement

# --- bash-4 guard (syntax parses on 3.2; execution gate reachable on 3.2) ---
if [ "${BASH_VERSINFO[0]:-0}" -lt 4 ]; then
  printf 'ERROR: bash >=4 required (found %s). On macOS: brew install bash\n' \
    "${BASH_VERSION:-unknown}" >&2
  exit 2
fi

set -euo pipefail

# ── Self-locate: gate script lives in the same bin/ directory ────────────────
# Uses BASH_SOURCE to resolve relative to THIS script — not CWD or $0 on PATH.
# No hardcoded absolute paths (DR-148); works on any machine layout.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE="$SCRIPT_DIR/check-workstream-complete-deletion-blocks.sh"

if [ ! -f "$GATE" ]; then
  printf 'wsc-commit.sh: gate script not found: %s\n' "$GATE" >&2
  exit 2
fi

# ── Argument parsing ──────────────────────────────────────────────────────────
SUBJECT=""
PROSE=""
DELETED_PATHS=()
KEPT_ENTRIES=()
COMMIT_PATHS=()
SWEPT_SRCS=()
SWEPT_DSTS=()
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --subject)
      [[ $# -ge 2 ]] || { printf 'wsc-commit.sh: --subject requires an argument\n' >&2; exit 2; }
      SUBJECT="$2"
      shift 2
      ;;
    --prose)
      [[ $# -ge 2 ]] || { printf 'wsc-commit.sh: --prose requires an argument\n' >&2; exit 2; }
      PROSE="$2"
      shift 2
      ;;
    --deleted)
      [[ $# -ge 2 ]] || { printf 'wsc-commit.sh: --deleted requires an argument\n' >&2; exit 2; }
      DELETED_PATHS+=("$2")
      shift 2
      ;;
    --kept)
      [[ $# -ge 2 ]] || { printf 'wsc-commit.sh: --kept requires an argument\n' >&2; exit 2; }
      KEPT_ENTRIES+=("$2")
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --swept-rename)
      [[ $# -ge 2 ]] || { printf 'wsc-commit.sh: --swept-rename requires an argument\n' >&2; exit 2; }
      val="$2"
      if [[ "$val" != *"|"* ]]; then
        printf 'wsc-commit.sh: --swept-rename: no | separator in value: %s\n' "$val" >&2
        exit 2
      fi
      _sr_src="${val%%|*}"
      _sr_dst="${val#*|}"
      if [ -z "$_sr_src" ]; then
        printf 'wsc-commit.sh: --swept-rename: empty src in value: %s\n' "$val" >&2
        exit 2
      fi
      if [ -z "$_sr_dst" ]; then
        printf 'wsc-commit.sh: --swept-rename: empty dst in value: %s\n' "$val" >&2
        exit 2
      fi
      if [[ "$_sr_dst" == *"|"* ]]; then
        printf 'wsc-commit.sh: --swept-rename: more than one | in value: %s\n' "$val" >&2
        exit 2
      fi
      SWEPT_SRCS+=("$_sr_src")
      SWEPT_DSTS+=("$_sr_dst")
      shift 2
      ;;
    --)
      shift
      # All remaining args are commit paths
      while [[ $# -gt 0 ]]; do
        COMMIT_PATHS+=("$1")
        shift
      done
      break
      ;;
    -*)
      printf 'wsc-commit.sh: unknown flag: %s\n' "$1" >&2
      exit 2
      ;;
    *)
      printf 'wsc-commit.sh: unexpected argument before --: %s\n' "$1" >&2
      exit 2
      ;;
  esac
done

if [ -z "$SUBJECT" ]; then
  printf 'wsc-commit.sh: --subject is required\n' >&2
  exit 2
fi

if [ "${#COMMIT_PATHS[@]}" -eq 0 ] && [ "${#SWEPT_SRCS[@]}" -eq 0 ]; then
  printf 'wsc-commit.sh: at least one commit path (after --) or --swept-rename pair is required\n' >&2
  exit 2
fi

# ── Git repo check ────────────────────────────────────────────────────────────
if ! git rev-parse --git-dir >/dev/null 2>&1; then
  printf 'wsc-commit.sh: not in a git repository\n' >&2
  exit 3
fi

# ── Compose commit message ────────────────────────────────────────────────────
# Format (byte-identical to SKILL.md Step 3 Step 1.5 + Step 2.67 fixture):
#
#   <subject>
#
#   <prose>
#
#   Deleted (Step 2.67):
#   <path>
#   ...
#
#   Kept (Step 2.67):
#   <path> — <reason>
#   ...
#   --- end Step 2.67 blocks ---
#
# Rules:
#   - Blank line after subject if ANYTHING follows.
#   - Blank line between prose and blocks if both present.
#   - Blank line between Deleted paths and Kept header if both blocks present.
#   - Footer appears once, immediately after the last Kept entry (or after the
#     last Deleted entry if no Kept block).

_has_blocks() {
  [ "${#DELETED_PATHS[@]}" -gt 0 ] || [ "${#KEPT_ENTRIES[@]}" -gt 0 ]
}

msg="$SUBJECT"$'\n'

# Blank line after subject when content follows
if [ -n "$PROSE" ] || _has_blocks; then
  msg+=$'\n'
fi

# Prose body
if [ -n "$PROSE" ]; then
  msg+="$PROSE"$'\n'
fi

# Blank line between prose and Step 2.67 blocks (only when both present)
if [ -n "$PROSE" ] && _has_blocks; then
  msg+=$'\n'
fi

# Deleted (Step 2.67): block — one bare path per line, no leading whitespace
if [ "${#DELETED_PATHS[@]}" -gt 0 ]; then
  msg+="Deleted (Step 2.67):"$'\n'
  for p in "${DELETED_PATHS[@]}"; do
    msg+="$p"$'\n'
  done
fi

# Blank line between Deleted block and Kept block (only when both present)
if [ "${#DELETED_PATHS[@]}" -gt 0 ] && [ "${#KEPT_ENTRIES[@]}" -gt 0 ]; then
  msg+=$'\n'
fi

# Kept (Step 2.67): block — "<path> — <reason>" per entry (em-dash U+2014)
if [ "${#KEPT_ENTRIES[@]}" -gt 0 ]; then
  msg+="Kept (Step 2.67):"$'\n'
  for e in "${KEPT_ENTRIES[@]}"; do
    msg+="$e"$'\n'
  done
fi

# Footer closes the Step 2.67 blocks section
if _has_blocks; then
  msg+="--- end Step 2.67 blocks ---"$'\n'
fi

# ── Write message to PID-scoped temp file under .git/ ────────────────────────
# mktemp pattern matches SKILL.md Step 3 step 1.5 ("PID-scoped scratch file
# under .git/"). The trap ensures cleanup even on non-zero exit after this point.
git_dir="$(git rev-parse --git-dir)"
msg_file=$(mktemp "$git_dir/COMMIT_EDITMSG.workstream-complete.XXXXXX")

_wsc_cleanup() {
  rm -f "$msg_file" 2>/dev/null || true
}
trap _wsc_cleanup EXIT

printf '%s' "$msg" > "$msg_file"

# ── Dry-run: print composed message to stdout, skip gate + commit, exit 0 ──────
if [ "$DRY_RUN" -eq 1 ]; then
  printf '%s' "$msg"
  exit 0
fi

# ── Compose gate_paths and commit_paths BEFORE the gate ──────────────────────
# Two path sets serve distinct roles:
#
#   gate_paths   = COMMIT_PATHS + DELETED_PATHS  (EM-authored only; swept paths excluded)
#     This is the scope the concurrent-EM gate inspects. Swept paths are excluded
#     because the gate has no Step 2.67 block to validate them against — they are
#     caller-named archival residues, not EM-authored judgment deletions.
#
#   commit_paths = gate_paths + SWEPT_SRCS + SWEPT_DSTS  (full pathspec for git commit)
#     Including swept src and dst in the commit pathspec folds the rename atomically.
#
# Concurrent-EM safety still holds: the invariant the original code protected was
# that the commit pathspec could not absorb a sibling EM's staged work. Swept paths
# are caller-named archival residues (unique inbox/archive paths by convention) —
# they are never sibling-staged files. Widening the commit pathspec with them
# therefore cannot absorb concurrent work. The EM-authored paths (COMMIT_PATHS +
# DELETED_PATHS) remain exactly gate_paths == commit_paths[0..N-1].
#
# Three arrays may be empty (COMMIT_PATHS, SWEPT_DSTS, gate_paths); guard every
# expansion with a length-check: a zero-element array expansion into a git pathspec
# argument would be silently misparsed (git sees no pathspec, not "add nothing").
# Guards are also defensive against future refactors that move these declarations.
# Review: code-reviewer — F3: corrected rationale (set -u is not the live hazard)
gate_paths=()
[ "${#COMMIT_PATHS[@]}" -gt 0 ] && gate_paths+=( "${COMMIT_PATHS[@]}" )
[ "${#DELETED_PATHS[@]}" -gt 0 ] && gate_paths+=( "${DELETED_PATHS[@]}" )

commit_paths=()
[ "${#gate_paths[@]}" -gt 0 ]  && commit_paths+=( "${gate_paths[@]}" )
[ "${#SWEPT_SRCS[@]}" -gt 0 ]  && commit_paths+=( "${SWEPT_SRCS[@]}" )
[ "${#SWEPT_DSTS[@]}" -gt 0 ]  && commit_paths+=( "${SWEPT_DSTS[@]}" )

# ── Structural gate (Step 3 step 1.5): validate blocks vs staged reality ──────
# Gate runs BETWEEN stage and commit — if it fails, we exit without committing.
# The exit-code contract of check-workstream-complete-deletion-blocks.sh:
#   0 — all claims match staged reality; safe to commit
#   1 — claim mismatch; the gate names offending paths on stderr
#   2 — usage/parse error
#   3 — environment error
#
# CRITICAL skip-gate-when-empty rule: when gate_paths is empty AND the message
# has no Step 2.67 block, SKIP the gate entirely. Do NOT call the gate with a
# bare -- and no pathspec: that reverts it to whole-index mode (documented at
# gate script :6, :46; logic at :104-108), which causes F3 to trip on the
# swept src's staged deletion even though the commit body has no Step 2.67 block
# to account for it (exactly the pure archival-fold scenario).
#
# When gate_paths is non-empty, invoke scoped to gate_paths exactly as before
# (concurrent-EM fix — 2026-07-01).
_has_step267_block=0
grep -qE '^(Deleted|Kept) \(Step 2\.67\):' "$msg_file" && _has_step267_block=1 || true

gate_exit=0
if [ "${#gate_paths[@]}" -gt 0 ]; then
  bash "$GATE" "$msg_file" -- "${gate_paths[@]}" || gate_exit=$?
elif [ "$_has_step267_block" -eq 1 ]; then
  # Step 2.67 block present but no EM-authored paths in pathspec.
  # Run gate unscoped — F3 cannot fire (message has a block), and Kept-entry
  # existence checks use ls-tree which is always whole-index anyway.
  bash "$GATE" "$msg_file" || gate_exit=$?
fi
# else: gate_paths empty + no Step 2.67 block → pure archival-fold; skip gate.

if [ "$gate_exit" -ne 0 ]; then
  printf 'wsc-commit.sh: gate exited %d — fix commit body or re-stage, then re-run\n' \
    "$gate_exit" >&2
  exit 1
fi

# ── Stage the non-deletion paths ─────────────────────────────────────────────
# Deletions (DELETED_PATHS, SWEPT_SRCS) are already staged by the caller via
# `git rm` / `git mv`; adding a staged-deleted path aborts with exit 128.
# COMMIT_PATHS are EM-authored modified/new files (may be empty for pure archival-fold).
# SWEPT_DSTS are rename destinations staged by git mv; git add is a no-op if already
# staged, but also validates that dst exists — an absent dst exits 128 (fail-loud).
[ "${#COMMIT_PATHS[@]}" -gt 0 ] && git add -- "${COMMIT_PATHS[@]}"
[ "${#SWEPT_DSTS[@]}" -gt 0 ]   && git add -- "${SWEPT_DSTS[@]}"

# ── Commit FROM the validated file with explicit pathspec ─────────────────────
# commit_paths = gate_paths + SWEPT_SRCS + SWEPT_DSTS — the explicit -- <paths>
# prevents sibling-staged files on the shared index from being absorbed
# (2026-06-24: a bare git commit -F without pathspec absorbed 6 concurrent-
# session-staged files). `git commit -m "..."` is forbidden: it would let a
# divergent message land that the gate never validated.
git commit -F "$msg_file" -- "${commit_paths[@]}"

# Emit the new HEAD SHA on stdout so callers can log/verify
git rev-parse HEAD
