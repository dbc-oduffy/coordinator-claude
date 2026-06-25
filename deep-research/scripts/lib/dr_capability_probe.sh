#!/usr/bin/env bash
# dr_capability_probe.sh — DR-authored harness capability probe for the deep-research plugin.
#
# Purpose: report whether deep-research's *harness capabilities* are ready, distinct from the
# vendored coordinator machine-prereq probe (coordinator_prereq/prereq_probe.sh) which reports
# machine-level prerequisites. This file owns DR-specific capability checks (agent teams env,
# pipeline presence, web access advisory, notebooklm sub-plugin, python availability).
#
# Shares the step_zero_emit primitive from the vendored coordinator_prereq unit — NDJSON
# emission is byte-identical to what the coordinator's Step Zero contract mandates.
#
# Spec backlink: docs/plans/2026-06-23-deep-research-install-parity-with-coordinator.md
#   § Amendment 2026-06-23 (PM decision: BOTH) — chunk C9.
#
# Emitter contract: each call to _co_pp_emit produces one compact NDJSON line:
#   {"name":"...","status":"...","severity":"...","detail":"...","remediation":"..."}
# Status ∈ {pass,fail,warn}; severity ∈ {hard,advisory}.
#
# Exported function: _dr_cap_probe_all — emit one NDJSON row per capability, env-only first.

# ---------------------------------------------------------------------------
# Bash version guard — bash >= 4 required (macOS ships 3.2, unsupported DR-148).
# Must be syntactically parseable on bash 3.2, so guard is a plain if-block.
# ---------------------------------------------------------------------------
if [[ "${BASH_VERSINFO[0]:-0}" -lt 4 ]]; then
  printf 'ERROR: dr_capability_probe.sh requires bash >= 4 (found: %s).\n' "${BASH_VERSION:-unknown}" >&2
  printf '  macOS ships bash 3.2 -- install via Homebrew: brew install bash\n' >&2
  exit 78  # EX_CONFIG
fi

# ---------------------------------------------------------------------------
# Idempotency guard — fires immediately after the bash-version check so that
# a re-source short-circuits before the lib-dir resolution and step_zero_emit
# sourcing side effects below.
# ---------------------------------------------------------------------------
_DR_CAP_PROBE_LOADED="${_DR_CAP_PROBE_LOADED:-0}"
if [[ "${_DR_CAP_PROBE_LOADED}" == "1" ]]; then
  return 0 2>/dev/null || true
fi
_DR_CAP_PROBE_LOADED=1

# ---------------------------------------------------------------------------
# Resolve the plugin root (two dirs above scripts/lib/).
# Strategy: BASH_SOURCE[0] → canonical path → up two dirs; fallback to git
# marker file (.git/HEAD) search from cwd if BASH_SOURCE resolution fails.
# ---------------------------------------------------------------------------
_dr_resolve_plugin_root() {
  local _script_dir
  if [[ -n "${BASH_SOURCE[0]:-}" ]]; then
    _script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd -P)"
  fi
  if [[ -n "${_script_dir:-}" && -d "${_script_dir}" ]]; then
    # scripts/lib/ → scripts/ → plugin root
    printf '%s' "$(cd "${_script_dir}/../.." 2>/dev/null && pwd -P)"
    return
  fi
  # Fallback: walk up from cwd looking for the deep-research marker (CLAUDE.md + pipelines/).
  local _d
  _d="$(pwd -P)"
  while [[ "${_d}" != "/" ]]; do
    if [[ -f "${_d}/CLAUDE.md" && -d "${_d}/pipelines" && -d "${_d}/scripts" ]]; then
      printf '%s' "${_d}"
      return
    fi
    _d="$(dirname "${_d}")"
  done
  # Cannot resolve — caller will surface a fail probe.
  printf ''
}

# ---------------------------------------------------------------------------
# Resolve the scripts/lib dir (where the vendored unit lives).
# ---------------------------------------------------------------------------
_dr_resolve_lib_dir() {
  local _script_dir
  if [[ -n "${BASH_SOURCE[0]:-}" ]]; then
    _script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd -P)"
  fi
  if [[ -n "${_script_dir:-}" && -d "${_script_dir}" ]]; then
    printf '%s' "${_script_dir}"
    return
  fi
  # Fallback: derive from plugin root
  local _plugin_root
  _plugin_root="$(_dr_resolve_plugin_root)"
  if [[ -n "${_plugin_root}" ]]; then
    printf '%s' "${_plugin_root}/scripts/lib"
    return
  fi
  printf ''
}

# ---------------------------------------------------------------------------
# Source the shared step_zero_emit primitive (standalone, self-sources nothing).
# ---------------------------------------------------------------------------
_DR_LIB_DIR="$(_dr_resolve_lib_dir)"
if [[ -z "${_DR_LIB_DIR}" || ! -f "${_DR_LIB_DIR}/coordinator_prereq/step_zero_emit.sh" ]]; then
  printf 'ERROR: dr_capability_probe.sh: cannot locate coordinator_prereq/step_zero_emit.sh\n' >&2
  exit 1
fi
# shellcheck source=coordinator_prereq/step_zero_emit.sh
source "${_DR_LIB_DIR}/coordinator_prereq/step_zero_emit.sh"

# ---------------------------------------------------------------------------
# _dr_cap_probe_all
#
# Emit one NDJSON row per DR harness capability, in ENV-ONLY-FIRST order so
# environment checks surface even when Python or shell tools are absent.
# ---------------------------------------------------------------------------
_dr_cap_probe_all() {
  local _plugin_root
  _plugin_root="$(_dr_resolve_plugin_root)"

  # 1. agent_teams (hard) — ENV ONLY, no shell tool dependency.
  if [[ "${CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS:-}" == "1" ]]; then
    _co_pp_emit "agent_teams" "pass" "hard" \
      "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1" \
      ""
  else
    _co_pp_emit "agent_teams" "fail" "hard" \
      "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS not set to \"1\" (current: \"${CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS:-<unset>}\")" \
      "set \"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS\": \"1\" in settings.json env — all DR pipelines require it"
  fi

  # 2. pipelines_present (hard) — command file + pipelines/ dir relative to plugin root.
  if [[ -z "${_plugin_root}" ]]; then
    _co_pp_emit "pipelines_present" "fail" "hard" \
      "plugin root could not be resolved" \
      "re-install the deep-research plugin"
  else
    local _cmd_file="${_plugin_root}/commands/research.md"
    local _pipelines_dir="${_plugin_root}/pipelines"
    if [[ -f "${_cmd_file}" && -d "${_pipelines_dir}" ]]; then
      local _pipeline_list=""
      local _pf
      for _pf in "${_pipelines_dir}"/*.md; do
        [[ -f "${_pf}" ]] || continue
        local _bn="${_pf%.md}"
        _bn="${_bn##*/}"
        _pipeline_list="${_pipeline_list:+${_pipeline_list} }${_bn}"
      done
      _co_pp_emit "pipelines_present" "pass" "hard" \
        "commands/research.md present; pipelines/ present (${_pipeline_list:-none})" \
        ""
    else
      local _missing=""
      [[ ! -f "${_cmd_file}" ]] && _missing="${_missing}commands/research.md missing; "
      [[ ! -d "${_pipelines_dir}" ]] && _missing="${_missing}pipelines/ dir missing"
      _co_pp_emit "pipelines_present" "fail" "hard" \
        "${_missing}" \
        "re-install the deep-research plugin"
    fi
  fi

  # 3. web_access (advisory) — harness-provided; not shell-verifiable.
  _co_pp_emit "web_access" "warn" "advisory" \
    "harness-provided; not shell-verifiable" \
    "Pipeline A (web) needs harness WebFetch/WebSearch tools — verify harness grants web access"

  # 4. notebooklm (advisory) — sub-plugin dir present under plugin root.
  if [[ -z "${_plugin_root}" ]]; then
    _co_pp_emit "notebooklm" "warn" "advisory" \
      "plugin root unresolved; cannot check notebooklm sub-plugin" \
      "enable the notebooklm sub-plugin + NotebookLM MCP server for Pipeline D"
  elif [[ -d "${_plugin_root}/notebooklm" ]]; then
    _co_pp_emit "notebooklm" "pass" "advisory" \
      "notebooklm sub-plugin dir present at ${_plugin_root}/notebooklm" \
      ""
  else
    _co_pp_emit "notebooklm" "warn" "advisory" \
      "notebooklm sub-plugin dir absent (${_plugin_root}/notebooklm)" \
      "enable the notebooklm sub-plugin + NotebookLM MCP server for Pipeline D"
  fi

  # 5. python (advisory) — interpreter on PATH; overlaps machine-prereq probe deliberately.
  local _py_bin=""
  if command -v python3 >/dev/null 2>&1; then
    _py_bin="python3"
  elif command -v python >/dev/null 2>&1; then
    _py_bin="python"
  fi
  if [[ -n "${_py_bin}" ]]; then
    local _py_ver
    _py_ver="$("${_py_bin}" --version 2>&1 | head -1)"
    _co_pp_emit "python" "pass" "advisory" \
      "${_py_ver} (${_py_bin})" \
      ""
  else
    _co_pp_emit "python" "warn" "advisory" \
      "no python3 or python interpreter found on PATH" \ # verify-no-console-flash: allow — string argument to emit function, not a spawn
      "install Python 3"
  fi
}
