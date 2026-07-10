#!/usr/bin/env bash
# resolve-repo-path.sh — emit the on-disk path for a registered repo shortname,
# read from the machine-local [repos] registry, for machine-portable cross-repo
# path resolution.
#
# Contract:
#   1. `resolve-repo-path.sh <shortname>` maps <shortname> to a registry key via
#      s/-/_/g normalization (e.g. project-rag-ue-addon -> repos.project_rag_ue_addon)
#      and emits the resolved on-disk path on stdout.
#   2. `--wiki` flag makes it emit '<resolved-path>/docs/wiki' instead of the bare path.
#      An optional `--docs-wiki <subpath>` flag overrides the appended subpath: when
#      <subpath> is RELATIVE, emit '<resolved-path>/<subpath>' instead; when <subpath>
#      is ABSOLUTE (leading `/`, or `~`-prefixed — home-relative values are
#      machine-specific in intent and treated as absolute for this guarantee), WARN
#      to stderr (required, not optional — order-independence guarantee, see D4a)
#      and fall back to the default '<resolved-path>/docs/wiki'.
#      This script does NOT read the example-orchestration-hub-resident registry data file itself — the
#      caller (which does read that file) passes the per-entry docs_wiki value through
#      via this flag.
#   3. FAIL-LOUD-SKIP on unknown key: a shortname with NO matching repos.* key (or
#      a key that resolves empty) emits NOTHING (empty stdout) and exits 0 — the
#      caller SKIPS the unreachable/unregistered peer and reports it; never a silent
#      mis-resolution.
#   4. OSS-safe: when the machine-local registry is absent/empty entirely, degrade to
#      empty + exit 0.
#   5. Genuine internal errors (missing shortname argument, unknown flag) exit non-zero
#      on stderr — distinct from the "no such key" skip-to-empty/exit-0 path.
#
# Spec backlink: docs/plans/2026-06-19-portability-tracked-per-machine-config.md § C1
# Reference impl: bin/learn-lessons-roots.sh (same machine-local-derived, skip-absent,
#   OSS-degradation pattern).
# OSS requirement: works for any coordinator-claude installer with zero registered repos.
#
# claude-central wiki exception (FOLLOW-UP): claude-central's wiki does NOT live at
#   <path>/docs/wiki. As of this writing the machine-local registry exposes NO per-entry
#   wiki-layout override key (probed: wiki_layout.*, repos.*.wiki, wiki.*, *.wiki_path —
#   all absent), and `repos.claude_central` itself resolves empty on this machine. So
#   --wiki emits the default <path>/docs/wiki for every entry; when a claude-central
#   entry with a divergent wiki layout is registered, add an override lookup here
#   (e.g. `machine-local get wiki_layout.<key>`) before the default composition.
#
# set -uo pipefail — NOT set -e. A failed machine-local lookup must not abort the emit;
#   it must degrade to the empty-stdout/exit-0 skip path.

set -uo pipefail

# BASH_VERSINFO<4 fail-loud guard (DR-148). This script uses only POSIX-portable
# constructs today, but the guard is house convention for bin/ scripts so a 3.2 macOS
# bash fails loud with remediation rather than silently mis-behaving under future edits.
if [ "${BASH_VERSINFO:-0}" -lt 4 ]; then
  echo "resolve-repo-path.sh: requires bash >= 4 (found ${BASH_VERSION:-unknown})." >&2
  echo "  macOS ships bash 3.2; install a modern bash: brew install bash" >&2
  exit 1
fi

CLAUDE_HOME="${CLAUDE_HOME:-$HOME}/.claude"
MACHINE_LOCAL="${CLAUDE_HOME}/bin/machine-local"

# ---------------------------------------------------------------------------
# Argument parse. --wiki is an optional flag; --docs-wiki <subpath> is an optional
# flag carrying the caller-supplied per-entry docs_wiki override (relative subpath
# to append instead of the default docs/wiki — see contract item 2 above); the sole
# positional is <shortname>.
# ---------------------------------------------------------------------------
WIKI=false
DOCS_WIKI=""
SHORTNAME=""

while [ $# -gt 0 ]; do
  case "$1" in
    --wiki)
      WIKI=true
      shift
      ;;
    --docs-wiki)
      if [ $# -lt 2 ]; then
        echo "resolve-repo-path.sh: --docs-wiki requires a value" >&2
        exit 2
      fi
      # Review: code-reviewer F1 — reject a flag-like next token so --docs-wiki
      # never silently swallows a real flag (e.g. --wiki) or the `--` terminator
      # as its value.
      case "$2" in
        -*)
          echo "resolve-repo-path.sh: --docs-wiki requires a value, got flag-like '$2'" >&2
          exit 2
          ;;
      esac
      DOCS_WIKI="$2"
      shift 2
      ;;
    --)
      shift
      break
      ;;
    -*)
      echo "resolve-repo-path.sh: unknown flag: $1" >&2
      exit 2
      ;;
    *)
      if [ -n "$SHORTNAME" ]; then
        echo "resolve-repo-path.sh: unexpected extra argument: $1" >&2
        exit 2
      fi
      SHORTNAME="$1"
      shift
      ;;
  esac
done

# Any positional after `--`.
if [ $# -gt 0 ]; then
  if [ -n "$SHORTNAME" ]; then
    echo "resolve-repo-path.sh: unexpected extra argument: $1" >&2
    exit 2
  fi
  SHORTNAME="$1"
fi

# Missing shortname is a genuine internal/usage error — NOT a skip-to-empty case.
if [ -z "$SHORTNAME" ]; then
  echo "resolve-repo-path.sh: missing required <shortname> argument" >&2
  echo "  usage: resolve-repo-path.sh [--wiki] [--docs-wiki <subpath>] [--] <shortname>" >&2
  exit 2
fi

# ---------------------------------------------------------------------------
# OSS-safe degradation: no machine-local => empty stdout, exit 0.
# ---------------------------------------------------------------------------
if [ ! -x "$MACHINE_LOCAL" ]; then
  exit 0
fi

# ---------------------------------------------------------------------------
# Map shortname -> registry key via s/-/_/g normalization, then resolve.
#   project-rag-ue-addon -> repos.project_rag_ue_addon
# ---------------------------------------------------------------------------
NORMALIZED="$(printf '%s' "$SHORTNAME" | tr '-' '_')"
KEY="repos.${NORMALIZED}"

RESOLVED="$("$MACHINE_LOCAL" get "$KEY" 2>/dev/null || true)"

# FAIL-LOUD-SKIP: no such key (or key resolves empty) => empty stdout, exit 0.
# The caller treats empty as "not registered" and skips/reports the peer.
if [ -z "$RESOLVED" ]; then
  exit 0
fi

# ---------------------------------------------------------------------------
# Emit. --wiki appends /docs/wiki by default (see claude-central exception in
# header), or the caller-supplied --docs-wiki relative subpath when present.
# An absolute --docs-wiki value is a backward-tolerance case (D4a): WARN to
# stderr (required, not optional) and fall back to the default docs/wiki —
# never silently emit a machine-specific absolute path, never silently misread.
# ---------------------------------------------------------------------------
if $WIKI; then
  if [ -n "$DOCS_WIKI" ]; then
    case "$DOCS_WIKI" in
      /*|~*)
        echo "resolve-repo-path.sh: WARNING: docs_wiki value '${DOCS_WIKI}' is absolute; falling back to default docs/wiki (relative subpath required)" >&2
        printf '%s\n' "${RESOLVED}/docs/wiki"
        ;;
      *)
        printf '%s\n' "${RESOLVED}/${DOCS_WIKI}"
        ;;
    esac
  else
    printf '%s\n' "${RESOLVED}/docs/wiki"
  fi
else
  # Review: code-reviewer F2 — warn loudly when --docs-wiki was passed without
  # --wiki, matching the file's fail-loud-on-ambiguity posture elsewhere. stdout
  # contract is unchanged: still the bare resolved path.
  if [ -n "$DOCS_WIKI" ]; then
    echo "resolve-repo-path.sh: WARNING: --docs-wiki '${DOCS_WIKI}' ignored because --wiki was not passed" >&2
  fi
  printf '%s\n' "$RESOLVED"
fi

exit 0
