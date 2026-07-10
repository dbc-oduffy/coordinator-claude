#!/usr/bin/env bash
# lib/release-currency.sh — Release-currency probe: installed SHA vs latest published release.
#
# Purpose: resolve the locally installed coordinator plugin version (via version.txt) and
# compare it against the latest `v*` git tag for the given owner/repo. Classifies the
# result as current, behind, differs, offline, or source_is_live. Advisory-only —
# always exits 0 (mirrors P-13 / lib/coordinator-currency.sh).
#
# Currency anchor — git tags, NOT the Release API (2026-06-01 alignment). "Latest" is the
# highest-semver `v*` tag from `git ls-remote --tags`, NOT `gh api .../releases/latest`.
# Rationale: consumers propagate via `git clone` + `/coordinator-update` (git fetch + delta)
# and never pull a Release tarball, so the Release object was never on the install path;
# the Release API also anchors stale when tags are cut ahead of the next drafted Release
# (the realized v2.0.0-anchoring bug). GitHub Releases are still cut for OSS changelog /
# discoverability — only the machine currency *check* moved to git-tags. This matches the
# project-rag host team's mechanism, converging the ecosystem on one anchor.
# → docs/wiki/release-cadence-and-currency-notification.md
#
# Spec backlink: docs/plans/2026-06-01-boot-currency-notification-hook.md § C2;
#   alignment: state/handoffs/2026-06-01_152220_currency-mechanism-git-tag-alignment.md
#
# Compose-vs-invent decision (recorded here per spec): lib/coordinator-currency.sh handles
# the SCHEMA-INTEGER onboarding-currency axis (per-repo stamp vs coordinator-schema-version).
# This file handles the GIT-SHA release-currency axis (version.txt SHA vs latest published
# release tag SHA). These are orthogonal — coordinator-currency.sh line 13 records this
# explicitly. They MUST remain separate files.
#
# Public API:
#   release_currency_probe <plugin> <owner/repo> <install-root>
#     → stdout: <status>[ <from> <to>]
#     → exit 0 ALWAYS (advisory contract)
#
# Status strings:
#   source_is_live       — authoring machine; no version.txt expected; inert skip
#   current              — installed SHA matches the latest `v*` tag's commit SHA
#   behind <from> <to>   — local SHA is a confirmed ancestor of the tag SHA
#                          <from> = local git-describe tag (or bare SHA prefix)
#                          <to>   = latest `v*` tag (highest semver)
#   differs <to>         — installed SHA differs but ancestry unverifiable or ahead/diverged;
#                          NEUTRAL framing — does NOT assert "behind"
#   offline              — tag source unreachable; result unknown
#
# source_is_live detection: COORDINATOR_CURRENCY_SOURCE_IS_LIVE=1 (explicit) OR
#   auto-detected when the install-root contains no version.txt AND the script is
#   running from inside the plugin source tree (mirrors probe-onboarding-currency.sh).
#
# Environment overrides (for testing):
#   COORDINATOR_CURRENCY_SOURCE_IS_LIVE=1   — force source_is_live skip
#   RELEASE_CURRENCY_FORCE_OFFLINE=1        — force offline classification (testing)
#
# NOTE: deliberately NO `set` options at file scope — this file is SOURCED by callers
# (boot hook, tests). A file-scope `set -e`/`set -u`/`set -o pipefail` in a sourced lib
# mutates the CALLER's shell for the rest of its run — errexit aborts the caller on the
# first non-zero, and nounset aborts it on the first unset-var reference it previously
# tolerated. Functions guard their own state explicitly: `local` declarations, `${var:-}`
# fallbacks, `:?` on required params, and `|| var=""` exit capture. (code-reviewer F1
# 2026-06-01 — the same sourced-lib hazard the original `-e` note warned about applies to
# `-u`/`pipefail`; do not reintroduce a file-scope `set`.)

# ---------------------------------------------------------------------------
# Dependency: oss-repo-constants.sh (coordinator publish URL)
# ---------------------------------------------------------------------------

_RELEASE_CURRENCY_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_RELEASE_CURRENCY_CONSTANTS="${_RELEASE_CURRENCY_LIB_DIR}/oss-repo-constants.sh"

if [[ ! -f "$_RELEASE_CURRENCY_CONSTANTS" ]]; then
    # Non-fatal: the function will still work if the caller passes owner/repo explicitly.
    # The constants file missing means the default URL constant is unavailable.
    true
else
    # shellcheck source=./oss-repo-constants.sh
    source "$_RELEASE_CURRENCY_CONSTANTS"
fi

# ---------------------------------------------------------------------------
# Dependency: coordinator-watchdog.sh (portable timeout primitive — cs_timeout)
# ---------------------------------------------------------------------------
# cs_timeout provides genuine wall-clock bounding on all platforms, including
# stock macOS where GNU coreutils `timeout` is absent. The background-kill
# fallback (Branch B) ensures the command is always bounded.
# → coordinator-watchdog.sh § cs_timeout
_RELEASE_CURRENCY_WATCHDOG="${_RELEASE_CURRENCY_LIB_DIR}/coordinator-watchdog.sh"

if [[ -f "$_RELEASE_CURRENCY_WATCHDOG" ]]; then
    # shellcheck source=./coordinator-watchdog.sh
    source "$_RELEASE_CURRENCY_WATCHDOG"
fi

# ---------------------------------------------------------------------------
# Dependency: settings-home.sh (settings-home resolver seam — C1)
# ---------------------------------------------------------------------------
# Provides _coordinator_settings_home() for portable machine-local dir resolution.
# Spec backlink: docs/plans/2026-07-06-durable-substrate-to-settings-home.md § C1
_RELEASE_CURRENCY_SETTINGS_HOME_LIB="${_RELEASE_CURRENCY_LIB_DIR}/settings-home.sh"
if [[ -f "$_RELEASE_CURRENCY_SETTINGS_HOME_LIB" ]]; then
    # shellcheck source=./settings-home.sh
    source "$_RELEASE_CURRENCY_SETTINGS_HOME_LIB"
fi

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# _rc_registry_live_path → prints live_path for coordinator-claude from machine-local
# registry, or returns 0 with empty output when registry absent/unreadable.
# Used by the contributor-clone guard in release_currency_probe (the Staff Engineer F3).
# Mirrors the technique in resolve-coordinator-clone.sh::_rcc_registry_live_path.
_rc_registry_live_path() {
    # Resolve the machine-local registry dir via the settings-home seam (C1).
    # Falls back to env-derived path when seam is unavailable (cold bootstrap).
    local _reg
    if declare -f _coordinator_settings_home >/dev/null 2>&1; then
        _reg="$(_coordinator_settings_home)/machine-local/registry.local.toml"
    else
        local _home="${CLAUDE_HOME:-${HOME:-${USERPROFILE:-}}}"
        [[ -z "$_home" ]] && return 0
        _reg="${_home}/.coordinator-claude-settings/machine-local/registry.local.toml"
    fi
    [[ -f "$_reg" ]] || return 0

    local _py=""
    for _cand in python3 python py; do
        if command -v "$_cand" >/dev/null 2>&1; then _py="$_cand"; break; fi
    done
    [[ -z "$_py" ]] && return 0

    "$_py" - "$_reg" <<'PYEOF' 2>/dev/null
import sys
from pathlib import Path
reg_path = Path(sys.argv[1])
if not reg_path.exists():
    sys.exit(0)
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        sys.exit(0)
try:
    data = tomllib.loads(reg_path.read_text(encoding="utf-8"))
except Exception:
    sys.exit(0)
nested = data.get("plugin", {}).get("mirrors", {}).get("coordinator-claude", {})
if isinstance(nested, dict):
    live = nested.get("live_path", "")
    if live:
        print(live)
        sys.exit(0)
key = "plugin.mirrors.coordinator-claude.live_path"
val = data.get(key, "")
if val:
    print(val)
sys.exit(0)
PYEOF
}

# _rc_resolve_version_txt <install-root> → prints 40-hex SHA or returns 1
_rc_resolve_version_txt() {
    local install_root="${1:?install_root required}"
    local vtxt="${install_root}/version.txt"
    if [[ ! -f "$vtxt" ]]; then
        return 1
    fi
    local sha
    sha="$(tr -d '[:space:]' < "$vtxt")"
    # Must be a 40-hex commit SHA
    if [[ "$sha" =~ ^[0-9a-f]{40}$ ]]; then
        printf '%s' "$sha"
        return 0
    fi
    return 1
}

# _rc_fetch_latest_release_tag <owner/repo> → prints highest-semver v* tag name or returns 1
# Lists the remote's `v*` tags via `git ls-remote --tags` and selects the highest by
# SEMVER, not lexically (v2.10.0 > v2.9.0). The Release *object* is never consulted —
# the latest git tag is the currency anchor (see the module header). A non-zero git exit
# or an empty tag list doubles as the offline / no-tags signal (→ caller emits offline).
_rc_fetch_latest_release_tag() {
    local owner_repo="${1:?owner_repo required}"

    # Force-offline testing shim
    if [[ "${RELEASE_CURRENCY_FORCE_OFFLINE:-0}" == "1" ]]; then
        return 1
    fi

    command -v git &>/dev/null || return 1

    local repo_url="https://github.com/${owner_repo}.git"
    local lsremote_out
    lsremote_out="$(_rc_timeout_cmd 3 git ls-remote --tags "$repo_url" 'refs/tags/v*' 2>/dev/null)" || lsremote_out=""
    if [[ -z "$lsremote_out" ]]; then
        return 1
    fi

    # Extract plain tag names: the `sed` drops peeled-ref lines (those end in `^{}`,
    # whose literal `^` is excluded by the `[^^]*$` class) and captures only the bare
    # `vX.Y.Z` names. Then pick the highest by semver — ordering uses a zero-padded
    # numeric key + plain `sort` (BSD-portable, since GNU `sort -V` is absent on macOS
    # stock). `split(t,a,/[.+-]/)` tolerates a prerelease/build suffix by sorting on the
    # numeric major.minor.patch prefix only. `%010d` is safe for any realistic component
    # (a 10-digit major/minor/patch would overflow the key, but v999.999.999 is the
    # practical ceiling).
    local latest
    latest="$(printf '%s\n' "$lsremote_out" \
        | sed -n 's#.*refs/tags/\(v[^^]*\)$#\1#p' \
        | sort -u \
        | awk '{ orig=$0; t=$0; sub(/^v/,"",t); split(t, a, /[.+-]/);
                 printf "%010d.%010d.%010d\t%s\n", a[1]+0, a[2]+0, a[3]+0, orig }' \
        | sort \
        | cut -f2- \
        | tail -1)"

    if [[ -n "$latest" ]]; then
        printf '%s' "$latest"
        return 0
    fi
    return 1
}

# _rc_resolve_tag_sha <owner/repo> <tag> → prints 40-hex commit SHA or returns 1
# Resolves the tag to its COMMIT SHA via `git ls-remote`, dereferencing annotated tags
# with the `^{}` peel suffix (an annotated tag's own object SHA is NOT the commit SHA).
# Falls back to the bare ref for lightweight tags. NEVER uses the Release API
# target_commitish — it is a ref name (often a branch), not a resolvable SHA.
_rc_resolve_tag_sha() {
    local owner_repo="${1:?owner_repo required}"
    local tag="${2:?tag required}"
    local sha=""

    # Force-offline testing shim
    if [[ "${RELEASE_CURRENCY_FORCE_OFFLINE:-0}" == "1" ]]; then
        return 1
    fi

    command -v git &>/dev/null || return 1

    local repo_url="https://github.com/${owner_repo}.git"
    local lsremote_out
    # Annotated tag: `^{}` dereferences to the underlying commit object.
    lsremote_out="$(_rc_timeout_cmd 3 git ls-remote "$repo_url" "refs/tags/${tag}^{}" 2>/dev/null)" || lsremote_out=""
    if [[ -z "$lsremote_out" ]]; then
        # Lightweight tag: no peel object — the bare ref already names the commit.
        lsremote_out="$(_rc_timeout_cmd 3 git ls-remote "$repo_url" "refs/tags/${tag}" 2>/dev/null)" || lsremote_out=""
    fi
    sha="$(printf '%s' "$lsremote_out" | awk '{print $1}' | head -1 | tr -d '[:space:]')"
    if [[ "$sha" =~ ^[0-9a-f]{40}$ ]]; then
        printf '%s' "$sha"
        return 0
    fi
    return 1
}

# _rc_timeout_cmd <secs> <cmd...>
# Portable timeout wrapper delegating to cs_timeout from coordinator-watchdog.sh.
# cs_timeout uses system timeout/gtimeout when available (Branch A); falls back to a
# pure-bash background-kill approach on stock macOS where GNU coreutils is absent
# (Branch B), ensuring the command is genuinely bounded in both cases.
#
# This replaces the prior hand-rolled wrapper that ran the command WITHOUT any timeout
# on stock macOS (the old fallback relied on the OS TCP timeout ~75s, which was
# advisory-only and unbounded in the coordinator wall-clock sense). The macOS path is
# now genuinely bounded — see coordinator-watchdog.sh § cs_timeout § Branch B.
#
# Cross-platform: BSD-portable (DR-148). Callers' `|| lsremote_out=""` error-handling
# is preserved — cs_timeout returns the command's own exit code on normal exit, or 124
# on timeout (mirroring GNU timeout's contract).
_rc_timeout_cmd() {
    local _secs="$1"; shift
    cs_timeout "$_secs" -- "$@"
}

# _rc_git_clone_behind_count <install-root> → prints "<n> <ref>" or returns 1
# Called when the install-root has no version.txt but IS a git work-tree.
# Fetches the tracked remote (quiet, up to 5s) then counts commits in HEAD..<upstream>.
# Prefers the configured upstream (@{u}); falls back to origin/main when no upstream is set.
# Returns 1 on any failure (git absent, no remote, fetch failure) — caller treats as offline.
#
# BOOT-CURRENCY-THROTTLE: callers must apply the same 3-day throttle / offline handling
# as the version.txt path. A fetch failure (no network) MUST NOT write the 3-day sentinel.
# The hook enforces this via the offline branch; this function signals failure by exiting 1.
_rc_git_clone_behind_count() {
    local install_root="${1:?install_root required}"

    # Force-offline testing shim (shared with the version.txt path)
    if [[ "${RELEASE_CURRENCY_FORCE_OFFLINE:-0}" == "1" ]]; then
        return 1
    fi

    command -v git &>/dev/null || return 1

    # Must be a git work-tree (not just a directory with a .git file — bare checkouts
    # and submodules have .git files pointing elsewhere; accept both .git dir and file).
    if ! _rc_timeout_cmd 2 git -C "$install_root" rev-parse --is-inside-work-tree &>/dev/null 2>&1; then
        return 1
    fi

    # Fetch the tracked remote (quiet; tolerate failure → offline)
    _rc_timeout_cmd 5 git -C "$install_root" fetch -q 2>/dev/null || return 1

    # Try the configured upstream first (@{u}), then fall back to origin/main.
    local ref=""
    local count=""
    if count="$(_rc_timeout_cmd 2 git -C "$install_root" rev-list --count "HEAD..@{u}" 2>/dev/null)"; then
        # Resolve the symbolic upstream ref name for the display label
        ref="$(_rc_timeout_cmd 2 git -C "$install_root" rev-parse --abbrev-ref "@{u}" 2>/dev/null)" || ref="@{u}"
    else
        # No upstream configured — fall back to origin/main
        if ! _rc_timeout_cmd 2 git -C "$install_root" rev-parse "origin/main" &>/dev/null 2>&1; then
            return 1
        fi
        count="$(_rc_timeout_cmd 2 git -C "$install_root" rev-list --count "HEAD..origin/main" 2>/dev/null)" || return 1
        ref="origin/main"
    fi

    # Validate count is a non-negative integer
    if ! [[ "$count" =~ ^[0-9]+$ ]]; then
        return 1
    fi

    printf '%s %s' "$count" "$ref"
    return 0
}

# _rc_check_ancestry <install-root> <local-sha> <tag-sha> → exits 0 if local is ancestor
# Requires a git checkout at install-root. Used only to enrich the "behind" case.
_rc_check_ancestry() {
    local install_root="${1:?install_root required}"
    local local_sha="${2:?local_sha required}"
    local tag_sha="${3:?tag_sha required}"

    # Must be a git checkout
    if [[ ! -d "${install_root}/.git" ]]; then
        return 1
    fi

    # git merge-base --is-ancestor <A> <B> exits 0 iff A is an ancestor of B
    # Review: the Staff Engineer F4 — use portable _rc_timeout_cmd wrapper (bare timeout absent on stock macOS)
    _rc_timeout_cmd 2 git -C "$install_root" merge-base --is-ancestor "$local_sha" "$tag_sha" 2>/dev/null
}

# _rc_local_describe_tag <install-root> → prints human-readable tag ref or short SHA
_rc_local_describe_tag() {
    local install_root="${1:?install_root required}"
    local local_sha="${2:?local_sha required}"

    if [[ -d "${install_root}/.git" ]]; then
        local desc
        # Review: the Staff Engineer F4 — use portable _rc_timeout_cmd wrapper (bare timeout absent on stock macOS)
        desc="$(_rc_timeout_cmd 2 git -C "$install_root" describe --tags --exact-match "$local_sha" 2>/dev/null)" || desc=""
        if [[ -n "$desc" ]]; then
            printf '%s' "$desc"
            return 0
        fi
        # Fall back to `git describe --tags` (finds nearest ancestor tag)
        desc="$(_rc_timeout_cmd 2 git -C "$install_root" describe --tags "$local_sha" 2>/dev/null)" || desc=""
        if [[ -n "$desc" ]]; then
            printf '%s' "$desc"
            return 0
        fi
    fi

    # Fall back to first 12 chars of the SHA
    printf '%s' "${local_sha:0:12}"
}

# ---------------------------------------------------------------------------
# Public: release_currency_probe
# ---------------------------------------------------------------------------
# Arguments:
#   $1 — plugin name (e.g. "coordinator" — informational, used in logging)
#   $2 — owner/repo  (e.g. "dbc-oduffy/coordinator-claude")
#   $3 — install-root (e.g. "$HOME/.claude/plugins/coordinator-claude/coordinator")
#
# Stdout: one of the status strings documented at the top of this file.
# Exit: 0 always (advisory contract).
release_currency_probe() {
    local plugin="${1:?plugin required}"
    local owner_repo="${2:?owner_repo required}"
    local install_root="${3:?install_root required}"

    # ------------------------------------------------------------------
    # 1. source_is_live detection (mirrors probe-onboarding-currency.sh)
    # ------------------------------------------------------------------
    local _source_is_live=0
    if [[ "${COORDINATOR_CURRENCY_SOURCE_IS_LIVE:-0}" == "1" ]]; then
        _source_is_live=1
    else
        # Auto-detect: if install-root has no version.txt AND this script is
        # running from inside that install-root's tree, it is the source machine.
        local _script_norm="${_RELEASE_CURRENCY_LIB_DIR%/}"
        local _install_norm="${install_root%/}"
        # `/`-terminated prefix (code-reviewer F4): a bare prefix match would fire on a
        # shared path stem (install_root=/opt/coord matching lib /opt/coord-staging/lib).
        if [[ "${_script_norm}/" == "${_install_norm}/"* ]]; then
            _source_is_live=1
        fi
    fi

    if [[ "$_source_is_live" -eq 1 ]]; then
        printf 'source_is_live'
        return 0
    fi

    # ------------------------------------------------------------------
    # 2. Resolve local installed version
    # ------------------------------------------------------------------
    local local_sha
    if ! local_sha="$(_rc_resolve_version_txt "$install_root")"; then
        # No version.txt — check whether the install-root is a git work-tree.
        # A bare/junctioned git clone (e.g. the dogfood consumer box running a
        # stale clone at fa494e0) has no version.txt but IS a git work-tree and
        # MUST NOT be silently exempt — it may be many commits behind origin/main.
        #
        # negative-spec: returning source_is_live here was the pre-fix behaviour
        # that caused the false "prereq_probe.sh not shipped" blocker (dogfood
        # runner got no "you're behind" warning despite being N commits behind).
        # Do NOT revert to unconditional source_is_live for the no-version.txt case.
        #
        # CONTRIBUTOR-CLONE GUARD (the Staff Engineer F3): before counting behind-ness, check
        # whether this clone is registered as propagation_mode=source_is_live in
        # the machine-local registry. An authoring/contributor box has a git clone
        # but no version.txt and IS source_is_live — its live_path is the very
        # content root the resolver returns. On a contributor's feature/work branch
        # a behind-count would produce a false "N commits behind origin/main" nag
        # during normal development. source_is_live-registered clones are silent.
        local _rcc_reg_live
        _rcc_reg_live="$(_rc_registry_live_path 2>/dev/null)" || _rcc_reg_live=""
        if [[ -n "$_rcc_reg_live" ]]; then
            # Canonicalize by stripping trailing slash for comparison
            local _rcc_norm_live="${_rcc_reg_live%/}"
            local _rcc_norm_root="${install_root%/}"
            if [[ "$_rcc_norm_live" == "$_rcc_norm_root" ]]; then
                printf 'source_is_live'
                return 0
            fi
        fi
        if git -C "$install_root" rev-parse --is-inside-work-tree &>/dev/null 2>&1; then
            # Git work-tree without version.txt: do a git-state behind-count.
            local _behind_result
            if _behind_result="$(_rc_git_clone_behind_count "$install_root")"; then
                local _clone_count _clone_ref
                _clone_count="$(printf '%s' "$_behind_result" | awk '{print $1}')"
                _clone_ref="$(printf '%s' "$_behind_result" | awk '{print $2}')"
                if [[ "$_clone_count" -gt 0 ]]; then
                    printf 'behind-clone %s %s' "$_clone_count" "$_clone_ref"
                else
                    # Clone is current with its remote — silent
                    printf 'current'
                fi
            else
                # Fetch failed → treat as offline (no 3-day sentinel; retry next boot)
                printf 'offline'
            fi
            return 0
        fi
        # Not a git work-tree and no version.txt — genuinely no managed install;
        # treat as source_is_live (e.g. a standalone deep-research with no install).
        printf 'source_is_live'
        return 0
    fi

    # ------------------------------------------------------------------
    # 3. Fetch latest published release tag
    # ------------------------------------------------------------------
    local latest_tag
    if ! latest_tag="$(_rc_fetch_latest_release_tag "$owner_repo")"; then
        printf 'offline'
        return 0
    fi

    # Security (sec-audit HIGH+MEDIUM 2026-06-01): the tag is a network-controlled
    # string that flows into a `git ls-remote` refspec (_rc_resolve_tag_sha) and the
    # stdout banner. Validate it at this single chokepoint before any interpreter sees
    # it — must start alphanumeric (blocks a leading '-' being read as a git option)
    # and contain only tag-legal chars, bounded length. A tag that fails the allowlist
    # is untrustworthy → treat as offline (no false current/behind). One gate covers
    # both downstream uses.
    if ! [[ "$latest_tag" =~ ^[A-Za-z0-9][A-Za-z0-9._/+-]{0,127}$ ]]; then
        printf 'offline'
        return 0
    fi

    # ------------------------------------------------------------------
    # 4. Resolve tag → commit SHA via git ls-remote (NEVER use target_commitish)
    # ------------------------------------------------------------------
    local tag_sha
    if ! tag_sha="$(_rc_resolve_tag_sha "$owner_repo" "$latest_tag")"; then
        printf 'offline'
        return 0
    fi

    # ------------------------------------------------------------------
    # 5. Classify
    # ------------------------------------------------------------------
    if [[ "$local_sha" == "$tag_sha" ]]; then
        printf 'current'
        return 0
    fi

    # SHAs differ — check ancestry when install-root is a git checkout
    if _rc_check_ancestry "$install_root" "$local_sha" "$tag_sha"; then
        # local SHA is a TRUE ANCESTOR of tag SHA → directional "behind"
        local from_label
        from_label="$(_rc_local_describe_tag "$install_root" "$local_sha")"
        printf 'behind %s %s' "$from_label" "$latest_tag"
    else
        # ahead / diverged / ancestry unverifiable → NEUTRAL "differs"
        printf 'differs %s' "$latest_tag"
    fi

    return 0
}
