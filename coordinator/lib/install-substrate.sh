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

# --- Partial-invocation flag (C7a) ---
# --setup-only runs ONLY the machine-local substrate seeding region (tracked
# machine-local files + bin/ resolvers + settings-manifest + hardware audit) and
# exits before the machine-environment ops (percolation setup/, claude-CLI PATH,
# fnm binary, Windows health). This is the single source of truth the OSS
# installer (dist/publish-repo-setup/install.sh) calls, so its machine-local
# layer cannot drift from coordinator:install's. Absent flag → full Phase 3,
# byte-for-byte unchanged.
# Spec backlink: docs/plans/2026-06-23-setup-time-substrate-completeness.md §C7a
SETUP_ONLY="0"
for _arg in "$@"; do
    case "$_arg" in
        --setup-only) SETUP_ONLY="1" ;;
    esac
done

# --- Resolve install destination (same precedence as claude-home) ---
_install_base="${CLAUDE_HOME:-${HOME}}"
_ml_dst="${_install_base}/.claude/machine-local"
_bin_dst="${_install_base}/.claude/bin"
mkdir -p "$_ml_dst" "$_bin_dst"

# --- Step 2: tracked machine-local files (README, .gitignore, both .example) ---
for _f in README.md .gitignore registry.toml.example registry.local.toml.example; do
    if [[ ! -f "${_ml_dst}/${_f}" ]]; then
        cp "${_ml_templates}/${_f}" "${_ml_dst}/${_f}"
    elif ! diff -q "${_ml_templates}/${_f}" "${_ml_dst}/${_f}" >/dev/null 2>&1; then
        echo "[machine-local] operator-customized ${_f} preserved; template at ${_ml_templates}/${_f} for diff reference"
    fi
done

# --- Step 2b: concern baseline files (copy .example → live name, first-install only) ---
# unreal.toml ships as the schema-only baseline for the `unreal.*` concern namespace.
# Copied only when the target does not exist — never overwrites operator-provisioned state.
# Spec backlink: cross-repo memo 2026-05-21 (unreal-concern-ownership-3-repo plan, AC-1).
if [[ ! -f "${_ml_dst}/unreal.toml" ]]; then
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
if [[ ! -f "${_ml_dst}/registry.toml" ]]; then
    cp "${_ml_templates}/registry.toml.example" "${_ml_dst}/registry.toml"
    echo "[machine-local] seeded live registry.toml from example"
fi

# --- Step 3: bin/ resolvers ---
# machine-local family + python3.cmd come from templates/bin/.
# claude-home family comes from lib/claude-home/ (load-bearing module, not template).
_install_one() {
    local src="$1" dst="$2" exec_bit="$3" warn_prefix="$4"
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

# --- Step 3c: platform-localize hook ---
# SessionStart hook that auto-generates settings.local.json with correct
# marketplace paths and plugin enablements for this machine. See
# settings-manifest.md for the full architecture.
_install_one "${_ml_bin}/platform-localize.sh" "${_bin_dst}/platform-localize.sh" "yes" "machine-local"

# --- Step 3c-ii: settings-manifest.md ---
# Companion doc for settings.json — documents the portable-vs-machine-specific
# architecture. Placed at ~/.claude/ root for orient-time visibility.
_manifest_src="${CLAUDE_PLUGIN_ROOT}/templates/settings-manifest.md"
_manifest_dst="${_install_base}/.claude/settings-manifest.md"
if [[ -f "$_manifest_src" ]]; then
    _install_one "$_manifest_src" "$_manifest_dst" "no" "machine-local"
fi

# --- Steps 3d + 3e are machine-environment ops, skipped under --setup-only ---
# (percolation setup/ and claude-CLI PATH; the OSS installer owns its own
#  setup/ delivery and PATH handling). Body intentionally left un-reindented.
if [[ "$SETUP_ONLY" != "1" ]]; then
# --- Step 3d: percolation mechanism (~/.claude/setup/) ---
# File list is the single source of truth in lib/setup-templates-manifest.sh.
SETUP_DEST="${_install_base}/.claude/setup"
mkdir -p "$SETUP_DEST"
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
    mkdir -p "$SETUP_DEST/$(dirname "$_hf")"
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
            CLAUDE_DIR_WIN="$_claude_dir_win" powershell.exe -NoProfile -WindowStyle Hidden -Command \
                "\$p = [Environment]::GetEnvironmentVariable('PATH','User'); \
                 [Environment]::SetEnvironmentVariable('PATH', \"\$env:CLAUDE_DIR_WIN;\$p\", 'User')" \
                && echo "[setup] added ${_claude_dir_win} (claude CLI) to Windows user PATH — restart shells for it to take effect" \
                || echo "[setup] WARNING: failed to add ${_claude_dir_win} to Windows user PATH" >&2
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
    if [[ -f "$_rc" ]] && grep -qF "$_claude_sentinel" "$_rc"; then
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
if [[ ! -f "${_ml_dst}/hardware.toml" ]]; then
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
if [[ -f "$_registry_live" ]]; then
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
if [[ -x "$_detect_hw" ]]; then
    bash "$_detect_hw" || echo "[setup] WARNING: hardware audit failed — re-run install or set hardware.* keys manually" >&2
elif [[ -f "$_detect_hw" ]]; then
    bash "$_detect_hw" || echo "[setup] WARNING: hardware audit failed — re-run install or set hardware.* keys manually" >&2
else
    echo "[setup] WARNING: detect-hardware.sh not found at ${_detect_hw}; skipping hardware audit" >&2
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
if command -v fnm >/dev/null 2>&1; then
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
        BIN_DST_WIN="$_bin_dst_win" powershell.exe -NoProfile -WindowStyle Hidden -Command \
            "\$p = [Environment]::GetEnvironmentVariable('PATH','User'); \
             [Environment]::SetEnvironmentVariable('PATH', \"\$env:BIN_DST_WIN;\$p\", 'User')" \
            && echo "[setup] added ${_bin_dst_win} to Windows user PATH — restart shells/Claude sessions for it to take effect" \
            || echo "[setup] WARNING: failed to add ${_bin_dst_win} to Windows user PATH" >&2
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
