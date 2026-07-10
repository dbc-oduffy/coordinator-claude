#!/usr/bin/env bash
# install-substrate.sh — coordinator-setup Phase 3 mechanical work.
#
# Lays down ~/.claude/machine-local/ substrate, installs bin/ resolvers
# (machine-local + claude-home families), and runs Windows PATH/AppX
# health checks. Called by coordinator/commands/install.md Phase 3.
#
# MUST be executed as a subprocess, never sourced. Uses _-prefixed globals
# and `exit` (not `return`); sourcing would pollute the caller's env.
#
# Idempotent: re-runs preserve operator-customized files, emit notices
# instead of overwriting. Fail-loud on missing templates (hard precondition
# for downstream skills).
#
# Env:
#   CLAUDE_PLUGIN_ROOT — required; the coordinator plugin install root.
#   CLAUDE_HOME        — optional; $HOME substitute (see lib/claude-home).
#   COORDINATOR_NON_INTERACTIVE — optional; set to "1" to suppress the AppX
#                                 stub deletion consent prompt. Any other
#                                 value is treated as unset (interactive).

set -euo pipefail

# D2-15: derive CLAUDE_PLUGIN_ROOT from BASH_SOURCE when not set in env.
# This file lives at <root>/lib/install-substrate.sh, so the root is the
# parent of lib/. Env var takes precedence when set (allows test overrides).
# Spec backlink: docs/plans/2026-06-23-coordinator-install-surface-dogfood-hardening.md D2-15
if [[ -z "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
    # Review: code-reviewer F6 — guard against BASH_SOURCE[0] being empty (e.g. bash -c "source ...").
    # When BASH_SOURCE[0] is empty or not a real file, dirname derives "." and cd ../.. silently
    # resolves to cwd's parent — fail loud instead of trusting a wrong path.
    if [[ -z "${BASH_SOURCE[0]:-}" ]] || [[ ! -f "${BASH_SOURCE[0]}" ]]; then
        echo "install-substrate: cannot derive CLAUDE_PLUGIN_ROOT from BASH_SOURCE (empty or not a real file) — set CLAUDE_PLUGIN_ROOT explicitly" >&2
        exit 1
    fi
    CLAUDE_PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi

# Validate the resolved root has the expected layout before proceeding.
# Fail-loud if the layout is wrong — a silently bad root is worse than no root.
if [[ ! -d "${CLAUDE_PLUGIN_ROOT}/lib" ]] || [[ ! -d "${CLAUDE_PLUGIN_ROOT}/templates" ]]; then
    echo "install-substrate: CLAUDE_PLUGIN_ROOT does not have expected layout (lib/ and templates/ must exist)" >&2
    echo "  Resolved root: ${CLAUDE_PLUGIN_ROOT}" >&2
    echo "  Set CLAUDE_PLUGIN_ROOT explicitly to override the BASH_SOURCE derivation." >&2
    exit 1
fi

_ml_templates="${CLAUDE_PLUGIN_ROOT}/templates/machine-local"
_ml_bin="${CLAUDE_PLUGIN_ROOT}/templates/bin"
_ch_bin="${CLAUDE_PLUGIN_ROOT}/lib/claude-home"
_setup_src="${CLAUDE_PLUGIN_ROOT}/templates/setup"

# --- Source the settings-home seam (C1) ---
# Provides _coordinator_settings_home() used to resolve the durable substrate home.
# Sourced early so the migration helper and all subsequent steps can use it.
# Spec backlink: docs/plans/2026-07-06-durable-substrate-to-settings-home.md § C3
_sh_lib="${CLAUDE_PLUGIN_ROOT}/lib/settings-home.sh"
if [[ ! -f "$_sh_lib" ]]; then
    echo "install-substrate: settings-home.sh not found at ${_sh_lib} — cannot resolve settings home" >&2
    exit 1
fi
source "$_sh_lib"

# --- Single source of truth for the setup/ percolation file list ---
# F8: pre-source existence check (matches dist/install.sh posture) — under
# `set -euo pipefail` a missing manifest dies with a raw bash error before the
# array-emptiness diagnostic below can fire, so check explicitly first.
_manifest="${CLAUDE_PLUGIN_ROOT}/lib/setup-templates-manifest.sh"
[[ -f "$_manifest" ]] || { echo "install-substrate: setup-templates-manifest.sh not found at ${_manifest}" >&2; exit 1; }
source "$_manifest"

# --- Hard precondition: templates must exist ---
for _required in "$_ml_templates" "$_ml_bin" "$_ch_bin" "$_setup_src"; do
    if [[ ! -d "$_required" ]]; then
        cat >&2 <<EOF
Phase 3 FATAL: required directory not found at $_required.
Cannot lay down machine-local substrate or percolation mechanism, and downstream skills depend on it.
The coordinator plugin install is broken or incomplete. Remediation:
  (a) reinstall the coordinator plugin via the marketplace,
  (b) verify CLAUDE_PLUGIN_ROOT resolves correctly (echo \$CLAUDE_PLUGIN_ROOT),
  (c) if this is a meta-repo dev checkout, confirm the missing dir is present.
EOF
        exit 1
    fi
done
[[ ${#SETUP_TEMPLATE_FILES[@]} -gt 0 ]] || { echo "install-substrate: SETUP_TEMPLATE_FILES is empty — setup-templates-manifest.sh failed to source or is corrupt" >&2; exit 1; }

# --- Partial-invocation flags (C7a + check-only contract) ---
# --setup-only runs ONLY the machine-local substrate seeding region (tracked
# machine-local files + bin/ resolvers + settings-manifest + hardware audit) and
# exits before the machine-environment ops (percolation setup/, claude-CLI PATH,
# fnm binary, Windows health). This is the single source of truth the OSS
# installer (dist/publish-repo-setup/install.sh) calls, so its machine-local
# layer cannot drift from coordinator:install's. Absent flag → full Phase 3,
# byte-for-byte unchanged.
# Spec backlink: docs/plans/2026-06-23-setup-time-substrate-completeness.md §C7a
#
# --check-only / CHECK_ONLY=1: report would-do, write nothing. Propagated via
# env by the install.md orchestrator (export CHECK_ONLY=1 before subprocess),
# also accepted as a CLI arg for direct invocation. All drop-in callers MUST
# honour this — any code path that mutates the filesystem gates on ${CHECK_ONLY}.
# Spec backlink: coordinator/commands/install.md §Phase 3 / check-only contract.
SETUP_ONLY="0"
CHECK_ONLY="${CHECK_ONLY:-}"
for _arg in "$@"; do
    case "$_arg" in
        --setup-only) SETUP_ONLY="1" ;;
        --check-only) CHECK_ONLY="1" ;;
    esac
done

# --- One-time idempotent migration (C3): MUST run before mkdir-p and seed ---
# Copies legacy ~/.claude/{machine-local/,setup/,settings-manifest.md} into the
# settings home and installs the compat symlink at ~/.claude/machine-local.
# Running BEFORE mkdir-p prevents the absent-guard in the migration from being
# defeated by a freshly created empty dst dir, which would orphan the operator's
# registry.local.toml (repos.*/plugin.mirrors.*) carried from the old location.
# Spec backlink: docs/plans/2026-07-06-durable-substrate-to-settings-home.md § C3 — F1 ordering
_migrate_script="${CLAUDE_PLUGIN_ROOT}/lib/migrate-substrate-to-settings-home.sh"
if [[ -f "$_migrate_script" ]]; then
    # Under CHECK_ONLY, pass --dry-run so the migration reports would-do actions
    # without writing any files, creating the settings-home dir, or swapping the
    # ~/.claude/machine-local real-dir to a symlink. The migration script already
    # honours --dry-run end-to-end; this is the sole call site that must propagate it.
    bash "$_migrate_script" ${CHECK_ONLY:+--dry-run} || {
        echo "install-substrate: migration helper failed (exit $?) — resolve the conflict in ${_migrate_script} output and re-run install" >&2
        exit 1
    }
fi

# --- Resolve install destination ---
# _ml_dst writes to <settings-home>/machine-local/ (not ${_install_base}/.claude/).
# SETUP_DEST writes to ${_install_base}/.claude/setup/ — the canonical runtime location;
#   nothing reads setup/ from settings-home, so percolation targets ~/.claude/setup/ only.
# _bin_dst writes to <settings-home>/bin/ (C4: resolver bin/ family relocated).
# _compat_bin_dst retains the legacy ~/.claude/bin/ as a transitional compat layer:
#   project-rag-ue-addon probes ~/.claude/bin/machine-local absolutely; other
#   consumers reach the resolver via PATH injection of ~/.claude/bin/. Compat
#   forwarders are removed only at the gated phase-2 tail (after all 5 consumers
#   confirm migration). NEVER blank rm -rf the compat dir — it may hold non-coordinator shims.
# Spec backlink: docs/plans/2026-07-06-durable-substrate-to-settings-home.md § C4
_install_base="${CLAUDE_HOME:-${HOME}}"
_settings_home_path="$(_coordinator_settings_home)"
_ml_dst="${_settings_home_path}/machine-local"
_bin_dst="${_settings_home_path}/bin"
_compat_bin_dst="${_install_base}/.claude/bin"
# Under check-only, skip all directory creation — the install must be zero-mutation.
if [[ -z "${CHECK_ONLY:-}" ]]; then
    mkdir -p "$_ml_dst" "$_bin_dst" "$_compat_bin_dst"
fi

# --- Step 2: tracked machine-local files (README, .gitignore, both .example) ---
if [[ -n "${CHECK_ONLY:-}" ]]; then
    echo "[install-substrate] would: seed tracked machine-local files (README.md .gitignore *.example)"
else
    for _f in README.md .gitignore registry.toml.example registry.local.toml.example; do
        if [[ ! -f "${_ml_dst}/${_f}" ]]; then
            cp "${_ml_templates}/${_f}" "${_ml_dst}/${_f}"
        elif ! diff -q "${_ml_templates}/${_f}" "${_ml_dst}/${_f}" >/dev/null 2>&1; then
            echo "[machine-local] operator-customized ${_f} preserved; template at ${_ml_templates}/${_f} for diff reference"
        fi
    done
fi

# --- Step 2b: concern baseline files (copy .example → live name, first-install only) ---
# unreal.toml ships as the schema-only baseline for the `unreal.*` concern namespace.
# Copied only when the target does not exist — never overwrites operator-provisioned state.
# Spec backlink: cross-repo memo 2026-05-21 (unreal-concern-ownership-3-repo plan, AC-1).
if [[ -z "${CHECK_ONLY:-}" && ! -f "${_ml_dst}/unreal.toml" ]]; then
    cp "${_ml_templates}/unreal.toml.example" "${_ml_dst}/unreal.toml"
    echo "[machine-local] installed unreal.toml baseline (schema-only; add values to unreal.local.toml)"
fi

# --- Step 2c: seed live registry.toml on first install (D2-16) ---
# registry.toml is the primary machine-local key/value store. The .example is
# consumer-valid (schema=1, concerns=["project_rag","unreal"]) and used as the
# baseline. Copied only when the target does not exist — never overwrites an
# operator-customized registry.toml. Runs in both interactive and non-interactive
# modes (non-interactive installs previously left only the .example with no live file).
# Spec backlink: docs/plans/2026-06-23-coordinator-install-surface-dogfood-hardening.md D2-16
if [[ -z "${CHECK_ONLY:-}" && ! -f "${_ml_dst}/registry.toml" ]]; then
    cp "${_ml_templates}/registry.toml.example" "${_ml_dst}/registry.toml"
    echo "[machine-local] seeded live registry.toml from example"
fi

# --- Step 2c-notice: cockpit emit identity keys ---
# These per-machine values cannot be supplied by the installer; emit a proactive
# non-interactive notice so the operator knows what to configure before cockpit
# emit will work. The fail-loud belongs on the emit path; this is a heads-up only.
# Review: code-reviewer (F1) — probe the merged runtime value rather than grepping
# the base registry.toml (which always carries "" for unset keys). This prevents a
# false-positive NOTICE on every re-install after the operator has configured the key.
# Probe order: (1) machine-local CLI at the compat path (present on re-install, gives
# the merged value); (2) grep registry.local.toml directly (handles re-install where
# machine-local is not yet at the compat path but the operator has a local override);
# (3) fall through to the base-file grep only when neither confirms the key is set.
if [[ -f "${_ml_dst}/registry.toml" ]]; then
    _meta_slug_set=0
    # (1) Prefer the merged value via machine-local (reliable on re-install).
    if [[ -x "${_compat_bin_dst}/machine-local" ]]; then
        _ml_get_val="$("${_compat_bin_dst}/machine-local" get cockpit.meta_repo_slug 2>/dev/null || true)"
        [[ -n "$_ml_get_val" ]] && _meta_slug_set=1
    fi
    # (2) Direct local-override check (fallback when machine-local not yet installed).
    if [[ "$_meta_slug_set" -eq 0 && -f "${_ml_dst}/registry.local.toml" ]]; then
        if grep -qE '^"cockpit\.meta_repo_slug"[[:space:]]*=[[:space:]]*"[^"]+"' "${_ml_dst}/registry.local.toml" 2>/dev/null; then
            _meta_slug_set=1
        fi
    fi
    # (3) Only emit the NOTICE when neither runtime probe found a set value.
    if [[ "$_meta_slug_set" -eq 0 ]]; then
        if grep -qE '^"cockpit\.meta_repo_slug"[[:space:]]*=[[:space:]]*""' "${_ml_dst}/registry.toml"; then
            echo "[machine-local] NOTICE: cockpit emit key unset — set this before using cockpit emit:"
            echo "[machine-local]   machine-local set cockpit.meta_repo_slug \"<owner/repo, e.g. myowner/my-meta-repo>\""
        fi
    fi
fi

# --- Step 3: bin/ resolvers ---
# Installed to <settings-home>/bin/ (C4: _bin_dst relocated from ~/.claude/bin/).
# machine-local family + python3.cmd come from templates/bin/.
# claude-home family comes from lib/claude-home/ (load-bearing module, not template).
# coordinator-settings-home is the new settings-home CLI resolver (C1 seam entry point).
_install_one() {
    local src="$1" dst="$2" exec_bit="$3" warn_prefix="$4"
    # Check-only: report would-do and return immediately — no cp, no chmod.
    # This single guard covers every _install_one call site (bin resolvers, compat
    # forwarders, settings-manifest, percolation files) without per-call duplication.
    if [[ -n "${CHECK_ONLY:-}" ]]; then
        echo "[install-substrate] would: install $(basename "$dst") → ${dst}"
        return 0
    fi
    # Overwrite policy — code files vs config files.
    # Code files (*.py, *.sh): force-overwrite when content differs. Stale code
    # silently breaks callers — issue #6: stale _machine_local.py kept by
    # preserve-on-diff means the old parser stays, so the new caller
    # (detect-hardware.sh --concern) hits "unrecognized arguments: --concern".
    # Skip cp when content is already identical to avoid mtime churn.
    # Config files (*.toml and all others): preserve-on-diff — protect operator
    # customizations (e.g. registry.toml concern edits, unreal.toml overrides).
    # Spec backlink: docs/plans/2026-06-26-coordinator-install-update-friction-fix-slate.md C-R3b
    local _force_overwrite=no
    case "$src" in
        *.py|*.sh) _force_overwrite=yes ;;
        # Review: reviewer (C-F1) — extension-less code wrappers and .cmd files fall into
        # preserve-on-diff under the *.py|*.sh arm alone; stale machine-local/claude-home
        # binaries break callers the same way a stale _machine_local.py does (issue #6).
        */machine-local|*/resolve-coordinator-clone|*/claude-home|*.cmd) _force_overwrite=yes ;;
    esac

    if [[ ! -f "$dst" ]]; then
        cp "$src" "$dst"
        if [[ "$exec_bit" == "yes" ]]; then chmod +x "$dst"; fi
    elif [[ "$_force_overwrite" == "yes" ]]; then
        if ! diff -q "$src" "$dst" >/dev/null 2>&1; then
            echo "[${warn_prefix}] updated $(basename "$dst") (code file; re-install overwrites)"
            cp "$src" "$dst"
            # Review: reviewer (C-F8) — chmod only after cp (content change); avoids ctime
            # churn when content is already identical and no cp occurred.
            if [[ "$exec_bit" == "yes" ]]; then chmod +x "$dst"; fi
        fi
    elif diff -q "$src" "$dst" >/dev/null 2>&1; then
        if [[ "$exec_bit" == "yes" ]]; then chmod +x "$dst"; fi
    else
        if [[ "$warn_prefix" == "claude-home" ]]; then
            echo "[claude-home] WARNING: operator-customized $(basename "$dst") preserved, but claude-home is a cross-repo contract surface — customization is anti-doctrine. Diff against $src and restore unless intentional."
        else
            echo "[machine-local] operator-customized $(basename "$dst") preserved; template at $src for diff reference"
        fi
    fi
    # Explicit return 0 — `set -e` traps non-zero from the last evaluated test
    # when the function returns via fall-through. The `if` form above guards
    # the short-circuit, this guarantees clean exit regardless of which branch ran.
    return 0
}

for _f in machine-local _machine_local.py machine-local.cmd python3.cmd resolve-coordinator-clone; do
    _exec=no
    [[ "$_f" == "machine-local" ]] && _exec=yes
    [[ "$_f" == "resolve-coordinator-clone" ]] && _exec=yes
    _install_one "${_ml_bin}/${_f}" "${_bin_dst}/${_f}" "$_exec" "machine-local"
done

for _f in claude-home _claude_home.py claude-home.cmd; do
    _exec=no
    [[ "$_f" == "claude-home" ]] && _exec=yes
    _install_one "${_ch_bin}/${_f}" "${_bin_dst}/${_f}" "$_exec" "claude-home"
done

# coordinator-settings-home: the C1 settings-home CLI resolver (new in C4 install).
_install_one "${_ml_bin}/coordinator-settings-home" "${_bin_dst}/coordinator-settings-home" "yes" "machine-local"

# --- Step 3c: platform-localize hook ---
# SessionStart hook that auto-generates settings.local.json with correct
# marketplace paths and plugin enablements for this machine. See
# settings-manifest.md for the full architecture.
# Installed to <settings-home>/bin/; compat forwarder retained at ~/.claude/bin/ (Step 3c-compat).
_install_one "${_ml_bin}/platform-localize.sh" "${_bin_dst}/platform-localize.sh" "yes" "machine-local"

# --- Step 3c-compat: retained-and-repointed ~/.claude/bin/ compat forwarders (C4) ---
# RETAIN legacy ~/.claude/bin/ coordinator resolver names — NEVER rm them.
# Rationale: project-rag-ue-addon probes ~/.claude/bin/machine-local as an absolute
# path; other consumers reach bare-name `machine-local` via PATH injection of
# ~/.claude/bin/. The templates are now settings-home-aware (use COORDINATOR_SETTINGS_HOME
# seam), so installing them at the legacy path gives a compat forwarder that
# correctly delegates to <settings-home>/bin/_machine_local.py at runtime.
# Removal of these compat forwarders is gated to the single phase-2 tail step,
# triggered only after all 5 consumers (example-game-repo, project-rag, project-rag-ue-addon,
# cockpit, example-orchestration-hub) confirm they have migrated off the legacy surfaces.
# Spec backlink: docs/plans/2026-07-06-durable-substrate-to-settings-home.md § C4 — compat window
for _f in machine-local _machine_local.py machine-local.cmd python3.cmd resolve-coordinator-clone; do
    _exec=no
    [[ "$_f" == "machine-local" ]] && _exec=yes
    [[ "$_f" == "resolve-coordinator-clone" ]] && _exec=yes
    _install_one "${_ml_bin}/${_f}" "${_compat_bin_dst}/${_f}" "$_exec" "machine-local-compat"
done

for _f in claude-home _claude_home.py claude-home.cmd; do
    _exec=no
    [[ "$_f" == "claude-home" ]] && _exec=yes
    _install_one "${_ch_bin}/${_f}" "${_compat_bin_dst}/${_f}" "$_exec" "claude-home-compat"
done

# Compat: coordinator-settings-home (new resolver; no legacy to retain, but install at compat path
# so bare-name `coordinator-settings-home` resolves via the harness-injected ~/.claude/bin/ PATH).
_install_one "${_ml_bin}/coordinator-settings-home" "${_compat_bin_dst}/coordinator-settings-home" "yes" "machine-local-compat"

# Compat: platform-localize.sh hook retained at ~/.claude/bin/.
# hooks.json references `bash ~/.claude/bin/platform-localize.sh`; the compat copy keeps
# that hook path working through the transition window.
_install_one "${_ml_bin}/platform-localize.sh" "${_compat_bin_dst}/platform-localize.sh" "yes" "machine-local-compat"

# --- Step 3c-ii: settings-manifest.md ---
# Companion doc for settings.json — documents the portable-vs-machine-specific
# architecture. Placed at ~/.claude/ root for orient-time visibility.
_manifest_src="${CLAUDE_PLUGIN_ROOT}/templates/settings-manifest.md"
_manifest_dst="${_settings_home_path}/settings-manifest.md"
if [[ -f "$_manifest_src" ]]; then
    _install_one "$_manifest_src" "$_manifest_dst" "no" "machine-local"
fi

# --- Steps 3d + 3e are machine-environment ops, skipped under --setup-only ---
# (percolation setup/ and claude-CLI PATH; the OSS installer owns its own
#  setup/ delivery and PATH handling). Body intentionally left un-reindented.
if [[ "$SETUP_ONLY" != "1" ]]; then
# --- Step 3d: percolation mechanism (~/.claude/setup/) ---
# File list is the single source of truth in lib/setup-templates-manifest.sh.
# SETUP_DEST is the canonical ~/.claude/setup/ — nothing reads setup/ from settings-home
# at runtime, so percolation must land here. The migration helper (C3) does NOT copy
# setup/ to settings-home for the same reason; the two locations would otherwise diverge
# and the fail-loud guard would block every re-run.
SETUP_DEST="${_install_base}/.claude/setup"
if [[ -z "${CHECK_ONLY:-}" ]]; then mkdir -p "$SETUP_DEST"; fi
for _f in "${SETUP_TEMPLATE_FILES[@]}"; do
    _exec=no
    for _e in "${SETUP_TEMPLATE_EXEC_FILES[@]}"; do
        [[ "$_f" == "$_e" ]] && _exec=yes && break
    done
    _install_one "$_setup_src/$_f" "$SETUP_DEST/$_f" "$_exec" "machine-local"
done

# percolate-hooks/ doctrine README (subdirectory destination) — also manifest-driven.
# Only the generic README is shipped; per-target hook subdirectories
# (~/.claude/setup/percolate-hooks/<target>/) are operator-authored and
# never templated.
for _hf in "${SETUP_TEMPLATE_HOOK_FILES[@]}"; do
    if [[ -z "${CHECK_ONLY:-}" ]]; then mkdir -p "$SETUP_DEST/$(dirname "$_hf")"; fi
    _install_one "$_setup_src/$_hf" "$SETUP_DEST/$_hf" "no" "machine-local"
done

# --- Step 3e: ensure the standalone `claude` CLI dir is on the user PATH (cross-platform) ---
# The native Claude Code installer places the `claude` binary at ~/.local/bin on
# every platform. Operators who install Claude Code via the desktop app (or whose
# login shell never picked up ~/.local/bin) hit "claude: command not found" the
# moment they open a terminal to follow the CLI install steps. We detect a CLI
# binary in the standard location and idempotently add ITS dir to PATH.
#
# We deliberately probe the standard install dir rather than `command -v claude`:
# inside a desktop-app session `claude` may resolve to an app-bundled binary whose
# internal dir must NOT be put on the shell PATH. Only a real CLI binary in a
# conventional location is actionable.
_claude_bin=""
for _cand in "${_install_base}/.local/bin/claude" "${_install_base}/.local/bin/claude.exe"; do
    if [[ -x "$_cand" || -f "$_cand" ]]; then _claude_bin="$_cand"; break; fi
done
if [[ -z "$_claude_bin" ]]; then
    echo "[setup] note: no standalone \`claude\` CLI found at ${_install_base}/.local/bin —"
    echo "[setup]   if \`claude\` is not on your terminal PATH, install the CLI (https://docs.anthropic.com/en/docs/claude-code) so non-app shells can run it."
elif [[ "${OSTYPE:-}" == "msys" || "${OSTYPE:-}" == "cygwin" || "${OS:-}" == "Windows_NT" ]]; then
    # Windows: add the claude dir to the user PATH (mirrors Step 3b; env-var passing
    # keeps the path out of the PowerShell string to defend against quoting injection).
    _claude_dir_win=$(cygpath -w "$(dirname "$_claude_bin")" 2>/dev/null || echo "")
    if [[ -z "$_claude_dir_win" ]]; then
        echo "[setup] WARNING: cygpath unavailable; cannot resolve Windows path for the claude CLI dir; skipping PATH integration" >&2
    else
        _claude_set=$(CLAUDE_DIR_WIN="$_claude_dir_win" powershell.exe -NoProfile -WindowStyle Hidden -Command \
            "\$p=[Environment]::GetEnvironmentVariable('PATH','User'); \
             \$t=\$env:CLAUDE_DIR_WIN; \
             if (\$p -split ';' | Where-Object {\$_ -ieq \$t}) {'yes'} else {'no'}" \
            2>/dev/null | tr -d '\r')
        if [[ -z "$_claude_set" ]]; then
            echo "[setup] WARNING: could not read Windows user PATH; skipping claude-CLI PATH integration" >&2
        elif [[ "$_claude_set" != "yes" ]]; then
            if [[ -n "${CHECK_ONLY:-}" ]]; then
                echo "[install-substrate] would: add ${_claude_dir_win} (claude CLI) to Windows user PATH"
            else
                CLAUDE_DIR_WIN="$_claude_dir_win" powershell.exe -NoProfile -WindowStyle Hidden -Command \
                    "\$p = [Environment]::GetEnvironmentVariable('PATH','User'); \
                     [Environment]::SetEnvironmentVariable('PATH', \"\$env:CLAUDE_DIR_WIN;\$p\", 'User')" \
                    && echo "[setup] added ${_claude_dir_win} (claude CLI) to Windows user PATH — restart shells for it to take effect" \
                    || echo "[setup] WARNING: failed to add ${_claude_dir_win} to Windows user PATH" >&2
            fi
        fi
    fi
else
    # macOS / Linux: idempotently prepend the claude dir via a sentinel-guarded
    # block in the login rc (mirrors install.md Phase 1 Offer C). The written
    # guard is re-source-safe (case match) so it never duplicates PATH entries.
    _claude_dir="$(dirname "$_claude_bin")"
    case "$(basename "${SHELL:-zsh}")" in
        zsh)  _rc="${_install_base}/.zprofile" ;;
        bash) _rc="${_install_base}/.bash_profile" ;;
        *)    _rc="${_install_base}/.profile" ;;
    esac
    _claude_sentinel="# coordinator-install: ensure claude CLI on PATH"
    if [[ -n "${CHECK_ONLY:-}" ]]; then
        echo "[install-substrate] would: add ${_claude_dir} (claude CLI) to PATH via ${_rc}"
    elif [[ -f "$_rc" ]] && grep -qF "$_claude_sentinel" "$_rc"; then
        : # already wired
    elif { [[ -e "$_rc" ]] && [[ ! -w "$_rc" ]]; } || { [[ ! -e "$_rc" ]] && [[ ! -w "$(dirname "$_rc")" ]]; }; then
        echo "[setup] WARNING: $_rc not writable; add this to your shell profile manually:" >&2
        echo "[setup]   export PATH=\"$_claude_dir:\$PATH\"" >&2
    else
        {
            printf '%s\n' "$_claude_sentinel"
            printf 'case ":$PATH:" in *":%s:"*) ;; *) export PATH="%s:$PATH" ;; esac\n' "$_claude_dir" "$_claude_dir"
        } >> "$_rc" \
            && echo "[setup] added $_claude_dir (claude CLI) to PATH via $_rc — open a new shell or \`source $_rc\` to use \`claude\`" \
            || echo "[setup] WARNING: failed to append claude-CLI PATH block to $_rc" >&2
    fi
fi
fi  # end --setup-only guard for Steps 3d/3e

# --- Step 3f: hardware concern baseline (copy .example → live name, first-install only) ---
# hardware.toml ships as the schema-only baseline for the `hardware.*` concern namespace.
# Copied only when the target does not exist — never overwrites operator-provisioned state.
# Spec backlink: docs/plans/2026-06-23-coordinator-install-surface-dogfood-hardening.md §C4
if [[ -z "${CHECK_ONLY:-}" && ! -f "${_ml_dst}/hardware.toml" ]]; then
    cp "${_ml_templates}/hardware.toml.example" "${_ml_dst}/hardware.toml"
    echo "[machine-local] installed hardware.toml baseline (schema-only; values written by detect-hardware.sh)"
fi

# --- Step 3g: ensure `hardware` is registered in concerns (idempotent migration) ---
# Existing installs have concerns = ["project_rag","unreal"] with no `hardware`.
# Without this, machine-local get hardware.* resolves nothing.
# Uses an inline Python TOML-aware upsert so both the inline-array form (the
# existing registry.toml shape) and the flat-multiline form are handled correctly.
# machine-local array-append uses the flat multiline shape and cannot update the
# inline array without a round-trip conflict; Python tomllib + regex is safer here.
# Spec backlink: docs/plans/2026-06-23-coordinator-install-surface-dogfood-hardening.md §C4 (AC10)
_registry_live="${_ml_dst}/registry.toml"
if [[ -z "${CHECK_ONLY:-}" && -f "$_registry_live" ]]; then
    # Resolve python interpreter (same logic as machine-local wrapper).
    _py3=""
    if command -v python3 >/dev/null 2>&1; then _py3=python3
    elif command -v python >/dev/null 2>&1; then _py3=python
    fi
    if [[ -n "$_py3" ]]; then
        "$_py3" - "${_registry_live}" <<'PYEOF' || echo "[setup] WARNING: could not register 'hardware' in concerns — add it manually to ${_registry_live}" >&2
import sys, re, os

# Review: reviewer — Finding 2 (P1): tomllib is stdlib only in Python 3.11+;
# Ubuntu 22.04 LTS ships 3.10 where `import tomllib` raises ImportError.
# The || echo WARNING on the heredoc swallows the error and hardware is never
# registered. Portable fallback: try tomllib (3.11+), then tomli (pip package),
# then degrade to regex-only write path with a loud remediation message.
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]

path = sys.argv[1]
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Parse to check if hardware already listed (requires a working TOML parser).
if tomllib is not None:
    try:
        data = tomllib.loads(content)
    except Exception:
        sys.exit(0)  # malformed — don't touch it; install-substrate has already seeded a valid file

    concerns = data.get('concerns')
    if not isinstance(concerns, list):
        sys.exit(0)  # unexpected shape — leave it alone

    if 'hardware' in concerns:
        sys.exit(0)  # already registered — no-op
else:
    # No TOML parser available — check via regex so we still skip if already present.
    # Review: reviewer — if neither tomllib nor tomli is importable, we cannot safely
    # round-trip a multiline array; emit loud remediation rather than silently no-op.
    if re.search(r'["\']hardware["\']', content):
        sys.exit(0)  # already present — no-op
    print('[setup] WARNING: neither tomllib (Python 3.11+) nor tomli (pip install tomli) '
          'available. Falling back to regex-only write for concerns migration. '
          'Install tomli (`pip install tomli`) to ensure full TOML safety.', file=sys.stderr)

# Try to update the inline or multiline array form: concerns = [...].
# Falls back to appending a new top-level key when no array is found.
# Review: reviewer — Finding 1 (P1 DATA LOSS): original regex lacked re.DOTALL so
# multiline array form (concerns = [\n  "a",\n  "b",\n]) did not match and the
# else-branch inserted a SECOND top-level key; TOML last-key-wins silently dropped
# existing entries. Fix: (1) add re.DOTALL; (2) detect multiline vs inline by
# presence of newline in captured inner text and insert a new element line before
# the closing ] rather than appending to rstripped inner (which produced double-comma).
inline_pat = re.compile(r'^(concerns\s*=\s*\[)([^\]]*?)(\])', re.MULTILINE | re.DOTALL)
m = inline_pat.search(content)
if m:
    inner = m.group(2)
    if '\n' in inner:
        # Multiline form: insert a new element line before the closing ].
        lines = inner.rstrip().split('\n')
        last_line = lines[-1] if lines else ''
        indent_count = len(last_line) - len(last_line.lstrip())
        indent_str = ' ' * indent_count if indent_count else '  '
        insert = indent_str + '"hardware",\n'
        new_content = content[:m.end(2)] + insert + content[m.end(2):]
    else:
        # Inline form: append within the same line.
        inner_stripped = inner.strip()
        if inner_stripped:
            new_inner = inner_stripped + ', "hardware"'
        else:
            new_inner = '"hardware"'
        new_content = content[:m.start(2)] + new_inner + content[m.end(2):]
else:
    # Absent concerns key — append a flat concerns line before first [section].
    section_pat = re.compile(r'^\[', re.MULTILINE)
    sm = section_pat.search(content)
    insert_line = 'concerns = ["hardware"]\n'
    if sm:
        new_content = content[:sm.start()] + insert_line + '\n' + content[sm.start():]
    else:
        new_content = content.rstrip('\n') + '\n' + insert_line

# Sanity: new content must parse, contain hardware, AND preserve pre-existing concerns.
if tomllib is not None:
    try:
        parsed = tomllib.loads(new_content)
        new_concerns = parsed.get('concerns', [])
        if 'hardware' not in new_concerns:
            sys.exit(1)
        # Verify pre-existing entries survived the migration (not just that hardware is present).
        orig_concerns = tomllib.loads(content).get('concerns', [])
        for c in orig_concerns:
            if c not in new_concerns:
                print(f'[setup] ERROR: concern "{c}" was lost during migration — aborting write',
                      file=sys.stderr)
                sys.exit(1)
    except Exception:
        sys.exit(1)

tmp = path + '.tmp.' + str(os.getpid())
try:
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(new_content)
    os.replace(tmp, path)
except Exception as e:
    if os.path.exists(tmp):
        os.remove(tmp)
    print(f'[setup] WARNING: could not update {path}: {e}', file=sys.stderr)
    sys.exit(1)

print('[machine-local] registered hardware concern in registry.toml')
PYEOF
    else
        echo "[setup] WARNING: python3/python not found; cannot register 'hardware' in concerns — add it manually to ${_registry_live}" >&2
    fi
fi

# --- Step 3h: hardware audit (cross-platform; runs BEFORE the non-Windows exit guard) ---
# detect-hardware.sh probes CPU cores, RAM, and (best-effort) GPU/VRAM and
# persists values into hardware.local.toml via the --concern writer. Idempotent.
# Spec backlink: docs/plans/2026-06-23-coordinator-install-surface-dogfood-hardening.md §C4 (AC11)
_detect_hw="${CLAUDE_PLUGIN_ROOT}/lib/detect-hardware.sh"
if [[ -n "${CHECK_ONLY:-}" ]]; then
    echo "[install-substrate] would: run hardware audit (detect-hardware.sh)"
elif [[ -x "$_detect_hw" ]]; then
    bash "$_detect_hw" || echo "[setup] WARNING: hardware audit failed — re-run install or set hardware.* keys manually" >&2
elif [[ -f "$_detect_hw" ]]; then
    bash "$_detect_hw" || echo "[setup] WARNING: hardware audit failed — re-run install or set hardware.* keys manually" >&2
else
    echo "[setup] WARNING: detect-hardware.sh not found at ${_detect_hw}; skipping hardware audit" >&2
fi

# --- Steps C10a-1/2/3: whoami relocation, registry key, and venv rebuild ---
# Single idempotent entry for the durable-substrate C10a deliverables. Runs in
# BOTH full-install and --setup-only modes (substrate ops, not machine-env ops).
# Machine-local CLI is resolvable after Step 3; ensure-coordinator-venv.sh uses it.
# Spec backlink: docs/plans/2026-07-06-durable-substrate-to-settings-home.md § C10

_c10a_legacy_whoami="${_install_base}/.claude/coordinator-whoami"
_c10a_dst_whoami="${_settings_home_path}/coordinator-whoami"

# Step C10a-1: whoami directory relocation + compat pointer.
# Per-file guard mirrors _copy_one_file/_migrate_tree from migrate-substrate-to-settings-home.sh.
# Source-absent → skip; dest-absent → copy; identical → no-op; divergent → FAIL LOUD exit 1.
#
# After the file copy, the legacy real directory is replaced with a compat pointer
# (POSIX: symlink; Windows: directory junction) → <settings-home>/coordinator-whoami.
# Single source of truth at settings-home; legacy path resolves through the pointer
# for any straggler reader during the compat window. Mirrors the machine-local pattern
# in migrate-substrate-to-settings-home.sh.
# Guard on both the copy loop and the pointer step: [[ ! -L ]] (or _c10a_is_pointer)
# ensures a second run skips both when the pointer is already in place.
#
# _c10a_is_pointer: detect POSIX symlink ([[ -L ]]) or Windows directory junction
# (Python 3.8+ os.path.islink returns True for junctions). Same pattern as
# migrate-substrate-to-settings-home.sh::_is_pointer.
_c10a_is_pointer() {
    local _p="$1"
    [[ -L "$_p" ]] && return 0
    local _py=""
    if command -v python3 >/dev/null 2>&1; then _py=python3
    elif command -v python >/dev/null 2>&1; then _py=python
    fi
    if [[ -n "$_py" ]]; then
        "$_py" -c "import os,sys; exit(0 if os.path.islink(sys.argv[1]) else 1)" "$_p" 2>/dev/null \
            && return 0
        return 1
    fi
    echo "[install-substrate] WARNING: no python3 or python found; cannot detect Windows junctions; treating '${_p}' as pointer." >&2
    return 0
}

_c10a_copy_one() {
    local _c10a_src="$1" _c10a_dst="$2"
    [[ -f "$_c10a_src" ]] || return 0         # source absent — skip
    if [[ ! -f "$_c10a_dst" ]]; then
        mkdir -p "$(dirname "$_c10a_dst")"
        cp -p "$_c10a_src" "$_c10a_dst"
    elif diff -q "$_c10a_src" "$_c10a_dst" >/dev/null 2>&1; then
        : # identical — no-op
    else
        echo "install-substrate C10a: DIVERGENT whoami file — cannot safely relocate." >&2
        printf '  Source : %s\n' "$_c10a_src" >&2
        printf '  Dest   : %s\n' "$_c10a_dst" >&2
        echo "  Remediation: manually reconcile the two files, then re-run install." >&2
        exit 1
    fi
}

# Effective copy source: legacy real dir takes precedence (in-place-migration case);
# ${CLAUDE_PLUGIN_ROOT}/whoami is the fresh-machine bundled fallback; absent if neither.
if [[ -d "$_c10a_legacy_whoami" ]] && ! _c10a_is_pointer "$_c10a_legacy_whoami"; then
    _c10a_src_whoami="$_c10a_legacy_whoami"
elif [[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]] && [[ -d "${CLAUDE_PLUGIN_ROOT}/whoami" ]]; then
    _c10a_src_whoami="${CLAUDE_PLUGIN_ROOT}/whoami"
else
    _c10a_src_whoami=""
fi

# Copy loop: only when a source is resolved and dest is absent or empty of real files.
# Idempotent: a second run on an already-populated settings-home is a no-op — avoids
# re-copying and the DIVERGENT guard. find returns empty when dest missing or unpopulated
# (excluding .venv/.egg-info which pip regenerates with differing content/timestamps).
# `|| true` is load-bearing under `set -euo pipefail`: on a fresh machine _c10a_dst_whoami
# does not exist yet, so `find` exits 1 (and `head -1` can also SIGPIPE-close the pipe early
# on a large tree, propagating 141) — either way the pipeline's non-zero status would abort
# the whole script here without it. The intended semantics are empty-output-means-relocate,
# so a failed/short-circuited pipeline collapsing to empty-and-continue is correct, not a bug.
if [[ -n "$_c10a_src_whoami" ]]; then
    _c10a_dst_has_files="$(find "$_c10a_dst_whoami" -type f \
        -not -path '*/.venv/*' -not -path '*/*.egg-info/*' 2>/dev/null | head -1 || true)"
    if [[ -z "$_c10a_dst_has_files" ]]; then
        if [[ -n "${CHECK_ONLY:-}" ]]; then
            echo "[install-substrate] would: relocate coordinator-whoami/ from ${_c10a_src_whoami} to ${_c10a_dst_whoami}"
        else
            mkdir -p "$_c10a_dst_whoami"
            # Exclusion approach: exclude derived/ephemeral artifacts that cause DIVERGENT failures on
            # re-run (pip and setuptools regenerate these at the dest with different content/timestamps).
            # Excluded beyond the original __pycache__/pyc: .venv (full nested venv), *.egg-info,
            # *.egg-link, .pytest_cache, .git, build/, dist/.
            # Rationale for exclusion over allowlist: allowlist is cleaner in principle but brittle
            # across coordinator-whoami layout changes; exclusion list tolerates package evolution.
            while IFS= read -r _c10a_rel; do
                _c10a_copy_one "${_c10a_src_whoami}/${_c10a_rel}" "${_c10a_dst_whoami}/${_c10a_rel}"
            done < <(cd "$_c10a_src_whoami" && find . -type f \
                ! -path '*/__pycache__/*' ! -name '*.pyc' \
                ! -path '*/.venv/*' \
                ! -path '*/*.egg-info/*' ! -name '*.egg-link' \
                ! -path '*/.pytest_cache/*' \
                ! -path '*/.git/*' \
                ! -path '*/build/*' \
                ! -path '*/dist/*' \
                | sed 's|^\./||')
            while IFS= read -r _c10a_rel; do
                mkdir -p "${_c10a_dst_whoami}/${_c10a_rel}"
            done < <(cd "$_c10a_src_whoami" && find . -mindepth 1 -type d -empty \
                ! -path '*/__pycache__' \
                ! -path '*/.venv' \
                ! -path '*/*.egg-info' \
                ! -path '*/.pytest_cache' \
                ! -path '*/.git' \
                ! -path '*/build' \
                ! -path '*/dist' \
                2>/dev/null | sed 's|^\./||')
        fi
    fi
fi

# Compat pointer: replace legacy coordinator-whoami real dir with a platform-appropriate
# pointer → <settings-home>/coordinator-whoami (single source of truth).
# Mirrors the machine-local compat-symlink/junction in migrate-substrate-to-settings-home.sh.
# Guards: legacy must be a real dir (not already a pointer) AND dest must exist.
# Idempotency: once the pointer is in place _c10a_is_pointer fires → this block is skipped.
if [[ -d "$_c10a_legacy_whoami" ]] && ! _c10a_is_pointer "$_c10a_legacy_whoami" && [[ -d "$_c10a_dst_whoami" ]]; then
    if [[ -n "${CHECK_ONLY:-}" ]]; then
        echo "[install-substrate] would: replace ${_c10a_legacy_whoami} (real dir) with compat pointer → ${_c10a_dst_whoami}"
    else
        _c10a_platform="$(uname -s 2>/dev/null || true)"
        case "$_c10a_platform" in
            MINGW*|MSYS*|CYGWIN*)
                if ! command -v cygpath >/dev/null 2>&1; then
                    echo "install-substrate C10a: FATAL — cygpath not found on Windows host; cannot create coordinator-whoami junction." >&2
                    echo "  Remediation: ensure cygpath is on PATH (provided by MSYS2, Cygwin, or Git-for-Windows)." >&2
                    exit 1
                fi
                _c10a_win_legacy="$(cygpath -w "$_c10a_legacy_whoami")"
                _c10a_win_dst="$(cygpath -w "$_c10a_dst_whoami")"
                # rmdir removes a junction link without recursing; falls back to rm -rf for a
                # real non-empty dir (files already migrated to dest above).
                rmdir "$_c10a_legacy_whoami" 2>/dev/null || rm -rf "$_c10a_legacy_whoami"
                if ! cmd //c mklink /J "$_c10a_win_legacy" "$_c10a_win_dst" >/dev/null; then
                    echo "install-substrate C10a: FATAL — mklink /J failed for coordinator-whoami." >&2
                    echo "  Link path: ${_c10a_win_legacy}" >&2
                    echo "  Target   : ${_c10a_win_dst}" >&2
                    echo "  Note: mklink /J does not require elevation or Developer Mode." >&2
                    exit 1
                fi
                echo "[install-substrate] installed coordinator-whoami compat junction: ${_c10a_legacy_whoami} → ${_c10a_dst_whoami}"
                ;;
            *)
                rm -rf "$_c10a_legacy_whoami"
                ln -s "$_c10a_dst_whoami" "$_c10a_legacy_whoami"
                echo "[install-substrate] installed coordinator-whoami compat symlink: ${_c10a_legacy_whoami} → ${_c10a_dst_whoami}"
                ;;
        esac
    fi
fi

# Step C10a-2: register coordinator.whoami_src registry key.
# Always set to <settings-home>/coordinator-whoami regardless of whether that dir
# exists yet: ensure-coordinator-venv.sh checks for dir presence and falls back to
# the plugin root's whoami/ when absent (not-a-directory guard in that script).
# Idempotent: skip the set call when the current value already matches.
_c10a_ml_cli="${_bin_dst}/machine-local"
if [[ -x "$_c10a_ml_cli" ]]; then
    _c10a_cur="$("$_c10a_ml_cli" get coordinator.whoami_src 2>/dev/null || true)"
    if [[ -n "${CHECK_ONLY:-}" ]]; then
        # Check-only: read is safe; write is not — report would-do instead of writing.
        if [[ "$_c10a_cur" != "$_c10a_dst_whoami" ]]; then
            echo "[install-substrate] would: set coordinator.whoami_src → ${_c10a_dst_whoami}"
        fi
    elif [[ "$_c10a_cur" != "$_c10a_dst_whoami" ]]; then
        "$_c10a_ml_cli" set coordinator.whoami_src "$_c10a_dst_whoami"
        echo "[install-substrate] set coordinator.whoami_src → ${_c10a_dst_whoami}"
    fi
else
    echo "[install-substrate] WARNING: machine-local CLI not found at ${_c10a_ml_cli}; coordinator.whoami_src not persisted" >&2
fi

# Step C10a-3: venv rebuild at <settings-home>/.coordinator-venv + legacy venv removal.
# NEVER remove the legacy venv unless rebuild AND health probe both succeed.
# Health probe: import coordinator_whoami under the rebuilt venv interpreter.
# Portability: venv python path branches on uname -s (mirrors ensure-coordinator-venv.sh).
#
# Failure semantics (P2-1):
#   Fresh install (no pre-existing fallback venv — neither legacy nor settings-home venv
#     existed before this attempt): exit 1 on rebuild/probe failure — no working interpreter
#     to fall back to; the substrate is incomplete without a functional coordinator venv.
#   Upgrade (a fallback venv existed pre-rebuild): emit WARNING and continue (exit 0) —
#     substrate already seeded, legacy/prior venv still functional; transient failures
#     (e.g., PyPI outage) should not brick a working installation. Mirrors the posture of
#     the optional fnm step: substrate core is unaffected by non-critical build failures.
#
# COORDINATOR_TEST_VENV_SCRIPT: test seam that overrides the ensure-venv script path
#   (mirrors COORDINATOR_NON_INTERACTIVE pattern for test isolation — unset in production).
_c10a_ensure_venv="${COORDINATOR_TEST_VENV_SCRIPT:-${CLAUDE_PLUGIN_ROOT}/bin/ensure-coordinator-venv.sh}"
_c10a_legacy_venv="${_install_base}/.claude/.coordinator-venv"
case "$(uname -s 2>/dev/null)" in
    MINGW*|MSYS*|CYGWIN*) _c10a_venv_py="${_settings_home_path}/.coordinator-venv/Scripts/python.exe" ;;
    *)                     _c10a_venv_py="${_settings_home_path}/.coordinator-venv/bin/python" ;;
esac

# Verify a viable whoami package source exists before invoking the builder.
# ensure-coordinator-venv.sh resolves whoami via coordinator.whoami_src (if set+valid-dir)
# then falls back to ${CLAUDE_PLUGIN_ROOT}/whoami. If neither is a valid Python package
# (has pyproject.toml or setup.py), skip the rebuild with a warning rather than failing
# hard — an absent source is a config gap, not a rebuild failure.
_c10a_has_viable_whoami=0
if [[ -f "${_c10a_dst_whoami}/pyproject.toml" || -f "${_c10a_dst_whoami}/setup.py" ]]; then
    _c10a_has_viable_whoami=1
elif [[ -f "${CLAUDE_PLUGIN_ROOT}/whoami/pyproject.toml" || -f "${CLAUDE_PLUGIN_ROOT}/whoami/setup.py" ]]; then
    _c10a_has_viable_whoami=1
fi

# Capture pre-rebuild fallback state: a legacy venv OR an already-built settings-home venv
# means a working interpreter exists to fall back to. Must be captured BEFORE the rebuild
# attempt because ensure-coordinator-venv.sh removes its partial output on failure.
_c10a_has_fallback_venv=0
if [[ -d "${_settings_home_path}/.coordinator-venv" || -d "$_c10a_legacy_venv" ]]; then
    _c10a_has_fallback_venv=1
fi

if [[ -n "${CHECK_ONLY:-}" ]]; then
    # Check-only: invoke ensure-venv in --check mode (read-only health report); never
    # rebuild the venv and never remove the legacy venv — removal is the most destructive
    # action in this file and must not happen without an explicit normal install run.
    if [[ -f "$_c10a_ensure_venv" && "$_c10a_has_viable_whoami" -eq 1 ]]; then
        bash "$_c10a_ensure_venv" --check || true
    elif [[ ! -f "$_c10a_ensure_venv" ]]; then
        echo "[install-substrate] WARNING: ensure-coordinator-venv.sh not found at ${_c10a_ensure_venv}; skipping venv check" >&2
    else
        echo "[install-substrate] WARNING: no valid coordinator_whoami package source found; skipping venv check" >&2
    fi
    if [[ -d "$_c10a_legacy_venv" ]]; then
        echo "[install-substrate] would: remove legacy venv at ${_c10a_legacy_venv} (after settings-home venv health probe)"
    fi
elif [[ -f "$_c10a_ensure_venv" && "$_c10a_has_viable_whoami" -eq 1 ]]; then
    _c10a_venv_rc=0
    bash "$_c10a_ensure_venv" || _c10a_venv_rc=$?
    if [[ "$_c10a_venv_rc" -ne 0 ]]; then
        if [[ "$_c10a_has_fallback_venv" -eq 1 ]]; then
            # Upgrade: substrate already seeded; fallback venv retained. Do not brick the install.
            echo "[install-substrate] WARNING: venv rebuild failed (exit ${_c10a_venv_rc}) — substrate seeded; fallback venv retained." >&2
            echo "[install-substrate]   Transient failure — re-run install or it self-heals at next session-init." >&2
        else
            # Fresh install: no fallback interpreter. Fail loud.
            echo "install-substrate C10a: venv rebuild failed (exit ${_c10a_venv_rc}); no fallback venv available" >&2
            exit 1
        fi
    else
        # Rebuild succeeded: run health probe.
        _c10a_probe_rc=0
        "$_c10a_venv_py" -c 'import coordinator_whoami' >/dev/null 2>&1 || _c10a_probe_rc=$?
        if [[ "$_c10a_probe_rc" -ne 0 ]]; then
            if [[ "$_c10a_has_fallback_venv" -eq 1 ]]; then
                # Upgrade: health probe failed; fallback venv intact.
                echo "[install-substrate] WARNING: venv health probe failed (coordinator_whoami not importable under ${_c10a_venv_py}); fallback venv retained." >&2
                echo "[install-substrate]   Re-run install or it self-heals at next session-init." >&2
            else
                # Fresh install: probe failed with no fallback.
                echo "install-substrate C10a: venv health probe failed — coordinator_whoami not importable under ${_c10a_venv_py}" >&2
                exit 1
            fi
        else
            # Rebuild + probe both green: remove legacy venv if it still exists.
            if [[ -d "$_c10a_legacy_venv" ]]; then
                rm -rf "$_c10a_legacy_venv"
                echo "[install-substrate] removed legacy venv at ${_c10a_legacy_venv} (settings-home venv healthy)"
            fi
        fi
    fi
elif [[ ! -f "$_c10a_ensure_venv" ]]; then
    echo "[install-substrate] WARNING: ensure-coordinator-venv.sh not found at ${_c10a_ensure_venv}; skipping venv rebuild" >&2
else
    echo "[install-substrate] WARNING: no valid coordinator_whoami package source found (neither ${_c10a_dst_whoami} nor ${CLAUDE_PLUGIN_ROOT}/whoami has pyproject.toml/setup.py); skipping venv rebuild — run ensure-coordinator-venv.sh manually once whoami source is in place" >&2
fi

# --- --setup-only stops here: machine-local layer is fully seeded ---
# Everything beyond is a machine-environment op (fnm binary, Windows health) the
# OSS installer does not delegate. The full coordinator:install path falls through.
if [[ "$SETUP_ONLY" == "1" ]]; then
    echo "[install-substrate] --setup-only: machine-local substrate seeded; skipping fnm/Windows machine-env steps"
    exit 0
fi

# --- Step 3i: fnm binary install (cross-platform; runs BEFORE the non-Windows exit guard) ---
# Ensures the fnm (Fast Node Manager) binary is present on the machine.
# Machine-level binary install ONLY — per-repo pin resolution (fnm install <ver>)
# lives in lib/setup-fnm-pin.sh and is not duplicated here.
# Idempotent: if fnm is already on PATH, emit a notice and skip.
# Spec backlink: docs/plans/2026-06-23-coordinator-install-surface-dogfood-hardening.md §C5a
if [[ -n "${CHECK_ONLY:-}" ]]; then
    echo "[install-substrate] would: install fnm binary if not already present"
elif command -v fnm >/dev/null 2>&1; then
    echo "[setup] fnm already installed at $(command -v fnm) — skipping binary install"
else
    # fnm is an OPTIONAL per-repo Node convenience — a failure here must NOT abort
    # the install after the core substrate already succeeded. All paths WARN and
    # continue (never `exit 1`). The curl installer is invoked with `--skip-shell`
    # to dodge its "Could not infer shell type" failure in non-interactive Git Bash.
    _fnm_manual="install fnm manually if you need per-repo Node pinning: https://github.com/Schniz/fnm#installation"
    if command -v brew >/dev/null 2>&1; then
        echo "[setup] installing fnm via brew..."
        if brew install fnm; then
            echo "[setup] fnm installed via brew"
        else
            echo "[setup] WARNING: brew install fnm failed — optional, core substrate unaffected; ${_fnm_manual}" >&2
        fi
    elif command -v curl >/dev/null 2>&1; then
        echo "[setup] installing fnm via official curl installer..."
        if curl -fsSL https://fnm.vercel.app/install | bash -s -- --skip-shell; then
            echo "[setup] fnm installed via curl installer"
        else
            echo "[setup] WARNING: curl installer for fnm failed — optional, core substrate unaffected; ${_fnm_manual}" >&2
        fi
    else
        echo "[setup] WARNING: cannot install fnm — neither brew nor curl available; optional, core substrate unaffected; ${_fnm_manual}" >&2
    fi
fi

# --- Step 3b/3c: Windows-only PATH + AppX Python health ---
# Skip silently on non-Windows.
if [[ "${OSTYPE:-}" != "msys" && "${OSTYPE:-}" != "cygwin" && "${OS:-}" != "Windows_NT" ]]; then
    exit 0
fi

# 3b: ensure the resolved bin dir on Windows user PATH.
# Convert POSIX `_bin_dst` to a Windows path so the PATH comparison/write
# targets the actual install location (honors CLAUDE_HOME, not just USERPROFILE).
_bin_dst_win=$(cygpath -w "${_bin_dst}" 2>/dev/null || echo "")
if [[ -z "$_bin_dst_win" ]]; then
    echo "[setup] WARNING: cygpath unavailable; cannot resolve Windows path for ${_bin_dst}; skipping PATH integration" >&2
else
    # Pass the path via env var so PowerShell sees a clean literal (no bash
    # interpolation into a PS string — defends against quoting injection).
    _already_set=$(BIN_DST_WIN="$_bin_dst_win" powershell.exe -NoProfile -WindowStyle Hidden -Command \
        "\$p=[Environment]::GetEnvironmentVariable('PATH','User'); \
         \$t=\$env:BIN_DST_WIN; \
         if (\$p -split ';' | Where-Object {\$_ -ieq \$t}) {'yes'} else {'no'}" \
        2>/dev/null | tr -d '\r')
    # Empty string = powershell.exe unavailable or check failed silently
    # (stderr redirected to /dev/null upstream). "yes"/"no" are the only
    # valid values; treat empty as "cannot determine" and skip rather than
    # blindly writing PATH on missing-information.
    if [[ -z "$_already_set" ]]; then
        echo "[setup] WARNING: could not read Windows user PATH (powershell.exe unavailable or check failed); skipping PATH integration" >&2
    elif [[ "$_already_set" != "yes" ]]; then
        if [[ -n "${CHECK_ONLY:-}" ]]; then
            echo "[install-substrate] would: add ${_bin_dst_win} to Windows user PATH"
        else
            BIN_DST_WIN="$_bin_dst_win" powershell.exe -NoProfile -WindowStyle Hidden -Command \
                "\$p = [Environment]::GetEnvironmentVariable('PATH','User'); \
                 [Environment]::SetEnvironmentVariable('PATH', \"\$env:BIN_DST_WIN;\$p\", 'User')" \
                && echo "[setup] added ${_bin_dst_win} to Windows user PATH — restart shells/Claude sessions for it to take effect" \
                || echo "[setup] WARNING: failed to add ${_bin_dst_win} to Windows user PATH" >&2
        fi
    fi
fi

# 3c-1: orphan AppX stub detection (zero-byte reparse-points from uninstalled Store Python)
for _stub_name in python.exe python3.exe; do
    _stub_path=$(powershell.exe -NoProfile -WindowStyle Hidden -Command \
        "\$p = \"\$env:LOCALAPPDATA\Microsoft\WindowsApps\\${_stub_name}\"; \
         if (Test-Path -LiteralPath \$p) { \$i = Get-Item -LiteralPath \$p -Force; \
         if (\$i.Length -eq 0 -and \$i.LinkType -eq 'ReparsePoint' -and -not \$i.Target) { Write-Output \$p } }" \
        2>/dev/null | tr -d '\r')
    if [[ -n "$_stub_path" ]]; then
        echo "[setup] Detected orphan AppX stub: ${_stub_path}"
        echo "[setup]   Zero-byte reparse-point from an uninstalled Store Python package."
        echo "[setup]   Intercepts python3/python invocations via AppX App-Execution-Alias,"
        echo "[setup]   popping the 'Select an app' picker (PATH lookup never runs)."
        echo "[setup]   Regenerates if Store Python is reinstalled."
        if [[ -t 0 ]] && [[ "${COORDINATOR_NON_INTERACTIVE:-}" != "1" ]]; then
            read -r -p "[setup] Delete this orphan stub? [y/N] " _consent
            if [[ "$_consent" =~ ^[Yy] ]]; then
                # Pass path via env var, not shell-interpolated — defends against
                # any shell-special characters in the path (semicolons, quotes,
                # backticks, $(); the path comes from PowerShell output through
                # `tr -d '\r'` and shell-interpolating it directly would be an
                # injection sink).
                STUB_PATH="${_stub_path}" powershell.exe -NoProfile -WindowStyle Hidden -Command \
                    'Remove-Item -LiteralPath $env:STUB_PATH -Force'
                echo "[setup]   Deleted."
            fi
        else
            echo "[setup]   (non-interactive context: skipping deletion; re-run in interactive shell to clean up)"
        fi
    fi
done

# 3c-2: store-alias-on-PATH warning
_py_resolved=$(powershell.exe -NoProfile -WindowStyle Hidden -Command \
    "\$c = Get-Command python3 -ErrorAction SilentlyContinue; \
     if (-not \$c) { \$c = Get-Command python -ErrorAction SilentlyContinue }; \
     if (\$c) { Write-Output \$c.Source }" 2>/dev/null | tr -d '\r')
case "$_py_resolved" in
    *WindowsApps*)
        echo "[setup] WARNING: python/python3 resolves under WindowsApps: ${_py_resolved}"
        echo "[setup]   Install Python from python.org OR disable App Execution Aliases via"
        echo "[setup]   Settings → Apps → Advanced app settings → App execution aliases."
        ;;
esac

# 3c-3: no-Python-at-all detection
_have_py=$(powershell.exe -NoProfile -WindowStyle Hidden -Command \
    "\$p = Get-Command py -ErrorAction SilentlyContinue; \
     if (\$p) { Write-Output 'yes' } else { Write-Output 'no' }" 2>/dev/null | tr -d '\r')
if [[ "$_have_py" != "yes" && -z "$_py_resolved" ]]; then
    echo "[setup] WARNING: neither py.exe nor python/python3 found."
    echo "[setup]   Install Python 3 from https://www.python.org/downloads/windows/ —"
    echo "[setup]   the installer ships py.exe by default. Without it, python3.cmd has nothing to call."
fi
