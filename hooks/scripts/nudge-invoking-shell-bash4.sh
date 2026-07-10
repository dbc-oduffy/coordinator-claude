#!/usr/bin/env bash
# hooks/scripts/nudge-invoking-shell-bash4.sh — SessionStart advisory hook.
#
# Purpose: on a fresh Mac, the Claude Code Bash tool's invoking-shell resolution
# is undocumented and can land on zsh or /bin/bash 3.2 (NOT bash>=4) even after
# `coordinator:install`'s login-shell repair (Offers A/B/C in commands/install.md
# § 1a.0) has succeeded — that repair fixes the LOGIN shell; the Bash-tool's own
# shell resolution is a separate mechanism with no settings.json override. When
# this drifts, coordinator lifecycle skills that `source` a bash>=4-guarded lib
# (e.g. /pickup's consume block sourcing strangler-facade.sh) abort mid-flow
# with an opaque "requires bash >=4 (found unknown)" error — a silent trap the
# operator only discovers when they hit that code path. This hook re-checks
# cheaply on every session start so drift (a later `chsh` back to zsh, a new
# terminal profile) is caught before the operator hits the silent trap.
#
# ADVISORY ONLY — never blocks. Always exits 0. Detection logic mirrors the
# shared probe (scripts/lib/invoking-shell-bash4-probe.sh, also used by
# install-time verification in commands/install.md § 1a.0.1) but is inlined
# here rather than invoked as a subprocess — see the IMPORTANT note below for
# why spawning a subshell to run the probe would give a WRONG answer for this
# specific caller.
#
# Output contract (SessionStart hook — stdout IS the additionalContext):
#   bash>=4 hook-runner shell : no output (silent)
#   NOT bash>=4               : one-line stdout remediation
#
# Spec backlink: tactical fix, F14 (fresh-Mac Bash-tool shell resolution trap),
#   2026-07-09. Durable fix (migrating guarded-lib logic behind cc_invoke) is
#   tracked on the pcore Python track via a separate example-orchestration-hub consult.
#
# Negative-spec:
#   - Must NEVER block session start — no `exit 1` anywhere in this file.
#   - Keep cheap: the probe does no network I/O and no subprocess spawns beyond
#     itself; safe to run on every startup/clear without a throttle sentinel.
#
# DR-148: must run on bash 3.2 + BSD coreutils — this hook itself is invoked by
# the Claude Code harness's own hook runner (not the possibly-unhealthy invoking
# shell being detected), so it may assume bash, but keep it portable regardless.

set -uo pipefail
# -e deliberately omitted — advisory hooks must fail-open on unexpected error.

# IMPORTANT: we deliberately do NOT exec/subshell the shared probe script here
# (e.g. via `sh "$PROBE"`) — /bin/sh on macOS IS bash 3.2 in POSIX mode, so
# spawning ANY subshell to do the detection would always report "not bash>=4"
# regardless of what interpreter is actually running THIS hook process.
# hooks.json invokes this hook as `bash <this-script>`, and per the F14
# finding that `bash` resolution is the SAME undocumented harness hook-runner
# mechanism as the Claude Code Bash TOOL — so the right check is simply: what
# interpreter is running the CURRENT process (this script)? We inspect our
# own $BASH_VERSINFO directly rather than delegating to a spawned probe.
if [[ -z "${BASH_VERSINFO:-}" ]] || [[ "${BASH_VERSINFO[0]:-0}" -lt 4 ]]; then
  _ibp_brew_bash=""
  if [[ -x /opt/homebrew/bin/bash ]]; then
    _ibp_brew_bash=/opt/homebrew/bin/bash
  elif [[ -x /usr/local/bin/bash ]]; then
    _ibp_brew_bash=/usr/local/bin/bash
  else
    _ibp_brew_bash="/opt/homebrew/bin/bash (or /usr/local/bin/bash on Intel — install first: brew install bash)"
  fi

  printf '📦 coordinator: this session'"'"'s hook-runner shell is bash %s (not >=4). Coordinator lifecycle skills (/pickup, /workstream-complete) will abort mid-flow with an opaque bash-version error. Fix: `chsh -s %s`, add it first on PATH in ~/.zprofile, then restart your terminal and Claude Code session.\n' \
    "${BASH_VERSION:-unknown}" "$_ibp_brew_bash"
fi

exit 0
