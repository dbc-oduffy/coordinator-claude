"""lib/release_currency.py — Release-currency probe: installed SHA vs latest published release.

Resolves the locally installed coordinator plugin version (via version.txt) and
compares it against the latest `v*` git tag for the given owner/repo. Classifies
the result as current, behind, differs, offline, or source_is_live. Advisory-only
— the public entry point never raises for a network/git failure, it returns
"offline" (mirrors P-13 / lib/coordinator_currency.py).

Currency anchor — git tags, NOT the Release API (2026-06-01 alignment). "Latest" is
the highest-semver `v*` tag from `git ls-remote --tags`, NOT `gh api .../releases/latest`.
Rationale: consumers propagate via `git clone` + `/coordinator-update` (git fetch + delta)
and never pull a Release tarball, so the Release object was never on the install path;
the Release API also anchors stale when tags are cut ahead of the next drafted Release
(the realized v2.0.0-anchoring bug). GitHub Releases are still cut for OSS changelog /
discoverability — only the machine currency *check* moved to git-tags.
→ docs/wiki/release-cadence-and-currency-notification.md

Spec backlink: docs/plans/2026-06-01-boot-currency-notification-hook.md § C2;
  port: docs/plans/2026-07-19-debash-coordinator-windows.md (chunk E2-a).

Compose-vs-invent decision (recorded here per spec): lib/coordinator_currency.py
handles the SCHEMA-INTEGER onboarding-currency axis (per-repo stamp vs
coordinator-schema-version). This module handles the GIT-SHA release-currency axis
(version.txt SHA vs latest published release tag SHA). These are orthogonal and
MUST remain separate.

Public API:
    release_currency_probe(plugin, owner_repo, install_root) -> str
        Returns one of the status strings below. Never raises for a network/git
        failure — advisory contract.

Status strings:
    source_is_live       — authoring machine; no version.txt expected; inert skip
    current               — installed SHA matches the latest `v*` tag's commit SHA
    behind <from> <to>    — local SHA is a confirmed ancestor of the tag SHA
                             <from> = local git-describe tag (or bare SHA prefix)
                             <to>   = latest `v*` tag (highest semver)
    differs <to>           — installed SHA differs but ancestry unverifiable or
                              ahead/diverged; NEUTRAL framing — does NOT assert "behind"
    offline                — tag source unreachable; result unknown
    behind-clone <n> <ref> — no version.txt, IS a git work-tree, N commits behind
                              the tracked/origin-main ref

source_is_live detection: COORDINATOR_CURRENCY_SOURCE_IS_LIVE=1 (explicit) OR
auto-detected when the install-root contains no version.txt AND this module is
running from inside the plugin source tree.

Environment overrides (for testing):
    COORDINATOR_CURRENCY_SOURCE_IS_LIVE=1   — force source_is_live skip
    RELEASE_CURRENCY_FORCE_OFFLINE=1        — force offline classification (testing)

No CLI entrypoint — this is an importable library module (mirrors
lib/coordinator_session.py), not a bin/ trampoline; no .cmd launcher is generated
because nothing invokes it directly.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from typing import Optional, Tuple

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))

_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_TAG_ALLOWLIST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/+-]{0,127}$")
_TAG_REF_RE = re.compile(r"refs/tags/(v[^^]*)$")
_COUNT_RE = re.compile(r"^[0-9]+$")


# ---------------------------------------------------------------------------
# Subprocess helper — Python's native timeout= replaces the bash
# cs_timeout/_rc_timeout_cmd portable-timeout wrapper (that machinery existed
# only to work around bash lacking a built-in bounded-subprocess primitive on
# stock macOS; subprocess.run(timeout=...) is cross-platform out of the box).
# Returns stdout on a zero exit within the deadline, else None.
# ---------------------------------------------------------------------------
def _run(args: list, timeout: float) -> Optional[str]:
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def _git_available() -> bool:
    return shutil.which("git") is not None


def _force_offline() -> bool:
    return os.environ.get("RELEASE_CURRENCY_FORCE_OFFLINE", "0") == "1"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _rc_registry_live_path() -> str:
    """Return live_path for coordinator-claude from the settings-home registry,
    or "" when the registry/entry is absent/unreadable/coordinator_core is not
    importable.

    Used by the contributor-clone guard in release_currency_probe (the Staff Engineer F3).
    Mirrors resolve-coordinator-clone.py::_registry_live_path.

    Delegates to `coordinator_core.machine_resolver.registry_get` — the
    canonical registry.local.toml-before-registry.toml reader with
    empty-string-is-a-miss semantics — rather than a hand-rolled TOML parse.
    A plain `try/except ImportError` (no CLAUDE_KLABAUTER_ROOT sys.path bootstrap) is
    correct here: this is an importable library module consumed in-process by
    callers that already share coordinator_core's interpreter/venv (see
    session_ensure_branch.py::_parses_as_branch_span for the same pattern),
    not a bin/ trampoline that might run under a foreign Python.

    Negative-spec: this function used to hand-parse
    `<settings-home>/machine-local/registry.local.toml` directly and never
    fall through to the tracked `registry.toml` — `.local`-only, silently
    degrading to "" on every miss (parse error, absent entry, tracked-only
    declaration). Do not re-introduce that inline TOML read.
    """
    try:
        from coordinator_core.machine_resolver import registry_get
    except ImportError:
        return ""
    return registry_get("plugin.mirrors.coordinator-claude.live_path") or ""


def _rc_resolve_version_txt(install_root: str) -> Optional[str]:
    """Return the 40-hex SHA from <install_root>/version.txt, or None."""
    vtxt = os.path.join(install_root, "version.txt")
    if not os.path.isfile(vtxt):
        return None
    try:
        with open(vtxt, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return None
    sha = re.sub(r"\s+", "", content)
    if _SHA40_RE.match(sha):
        return sha
    return None


def _semver_key(tag: str) -> Tuple[int, int, int, str]:
    """Numeric (major, minor, patch) key + the raw tag as a tie-break — mirrors
    the bash %010d.%010d.%010d zero-padded-key + full-line `sort` tie-break
    (tags sharing a numeric prefix, e.g. a prerelease suffix, break on the raw
    string so selection is deterministic, not iteration-order-dependent).
    """
    t = tag[1:] if tag.startswith("v") else tag
    parts = re.split(r"[.+-]", t)

    def _num(i: int) -> int:
        try:
            return int(parts[i])
        except (IndexError, ValueError):
            return 0

    return (_num(0), _num(1), _num(2), tag)


def _rc_fetch_latest_release_tag(owner_repo: str) -> Optional[str]:
    """Return the highest-semver `v*` tag name for owner_repo's remote, or None.

    Lists the remote's `v*` tags via `git ls-remote --tags` and selects the
    highest by SEMVER, not lexically (v2.10.0 > v2.9.0). The Release *object*
    is never consulted — the latest git tag is the currency anchor.
    """
    if _force_offline():
        return None
    if not _git_available():
        return None

    repo_url = f"https://github.com/{owner_repo}.git"
    out = _run(["git", "ls-remote", "--tags", repo_url, "refs/tags/v*"], timeout=3)
    if not out:
        return None

    tags = set()
    for line in out.splitlines():
        m = _TAG_REF_RE.search(line.strip())
        if m:
            tags.add(m.group(1))

    if not tags:
        return None
    return max(tags, key=_semver_key)


def _rc_resolve_tag_sha(owner_repo: str, tag: str) -> Optional[str]:
    """Resolve `tag` to its COMMIT SHA via `git ls-remote`, or None.

    Dereferences annotated tags with the `^{}` peel suffix (an annotated tag's
    own object SHA is NOT the commit SHA). Falls back to the bare ref for
    lightweight tags. NEVER uses the Release API target_commitish — it is a
    ref name (often a branch), not a resolvable SHA.
    """
    if _force_offline():
        return None
    if not _git_available():
        return None

    repo_url = f"https://github.com/{owner_repo}.git"
    out = _run(["git", "ls-remote", repo_url, f"refs/tags/{tag}^{{}}"], timeout=3)
    if not out:
        out = _run(["git", "ls-remote", repo_url, f"refs/tags/{tag}"], timeout=3)
    if not out:
        return None

    lines = out.splitlines()
    if not lines:
        return None
    fields = lines[0].split()
    if not fields:
        return None
    sha = fields[0].strip()
    if _SHA40_RE.match(sha):
        return sha
    return None


def _rc_is_git_worktree(install_root: str) -> bool:
    if not _git_available():
        return False
    return _run(["git", "-C", install_root, "rev-parse", "--is-inside-work-tree"], timeout=5) is not None


def _rc_git_clone_behind_count(install_root: str) -> Optional[Tuple[int, str]]:
    """Return (n, ref) commits install_root's HEAD is behind its tracked
    remote, or None on any failure (git absent, no remote, fetch failure —
    caller treats None as offline).

    Called when the install-root has no version.txt but IS a git work-tree.
    Fetches the tracked remote (quiet, bounded) then counts commits in
    HEAD..<upstream>. Prefers the configured upstream (@{u}); falls back to
    origin/main when no upstream is set.

    BOOT-CURRENCY-THROTTLE: callers must apply the same 3-day throttle /
    offline handling as the version.txt path. A fetch failure (no network)
    MUST NOT write the 3-day sentinel.
    """
    if _force_offline():
        return None
    if not _git_available():
        return None

    if _run(["git", "-C", install_root, "rev-parse", "--is-inside-work-tree"], timeout=2) is None:
        return None

    if _run(["git", "-C", install_root, "fetch", "-q"], timeout=5) is None:
        return None

    count_out = _run(["git", "-C", install_root, "rev-list", "--count", "HEAD..@{u}"], timeout=2)
    if count_out is not None:
        count_str = count_out.strip()
        ref_out = _run(["git", "-C", install_root, "rev-parse", "--abbrev-ref", "@{u}"], timeout=2)
        ref = ref_out.strip() if ref_out and ref_out.strip() else "@{u}"
    else:
        if _run(["git", "-C", install_root, "rev-parse", "origin/main"], timeout=2) is None:
            return None
        count_out = _run(["git", "-C", install_root, "rev-list", "--count", "HEAD..origin/main"], timeout=2)
        if count_out is None:
            return None
        count_str = count_out.strip()
        ref = "origin/main"

    if not _COUNT_RE.match(count_str):
        return None
    return (int(count_str), ref)


def _rc_check_ancestry(install_root: str, local_sha: str, tag_sha: str) -> bool:
    """True iff local_sha is an ancestor of tag_sha. Requires a git checkout at
    install_root. Used only to enrich the "behind" case.
    """
    if not os.path.isdir(os.path.join(install_root, ".git")):
        return False
    return _run(["git", "-C", install_root, "merge-base", "--is-ancestor", local_sha, tag_sha], timeout=2) is not None


def _rc_local_describe_tag(install_root: str, local_sha: str) -> str:
    """Return a human-readable tag ref for local_sha, or the first 12 chars of
    the SHA when no describable tag is found.
    """
    if os.path.isdir(os.path.join(install_root, ".git")):
        desc = _run(["git", "-C", install_root, "describe", "--tags", "--exact-match", local_sha], timeout=2)
        if desc and desc.strip():
            return desc.strip()
        desc = _run(["git", "-C", install_root, "describe", "--tags", local_sha], timeout=2)
        if desc and desc.strip():
            return desc.strip()
    return local_sha[:12]


# ---------------------------------------------------------------------------
# Public: release_currency_probe
# ---------------------------------------------------------------------------
def release_currency_probe(plugin: str, owner_repo: str, install_root: str) -> str:
    """Classify install_root's release currency against owner_repo's latest
    published `v*` tag. Advisory-only — never raises for a network/git
    failure; returns one of the status strings documented at module top.

    Args:
        plugin       — plugin name (e.g. "coordinator" — informational, logging only)
        owner_repo   — "owner/repo" (e.g. "dbc-oduffy/coordinator-claude")
        install_root — e.g. "$HOME/.claude/plugins/coordinator-claude/coordinator"
    """
    if not plugin:
        raise ValueError("plugin required")
    if not owner_repo:
        raise ValueError("owner_repo required")
    if not install_root:
        raise ValueError("install_root required")

    # ------------------------------------------------------------------
    # 1. source_is_live detection
    # ------------------------------------------------------------------
    source_is_live = os.environ.get("COORDINATOR_CURRENCY_SOURCE_IS_LIVE", "0") == "1"
    if not source_is_live:
        # Auto-detect: if install-root has no version.txt AND this module is
        # running from inside that install-root's tree, it is the source machine.
        script_norm = _LIB_DIR.rstrip("/")
        install_norm = install_root.rstrip("/")
        # `/`-terminated prefix (code-reviewer F4 parity): a bare prefix match
        # would fire on a shared path stem (install_root=/opt/coord matching
        # lib /opt/coord-staging/lib).
        if (script_norm + "/").startswith(install_norm + "/"):
            source_is_live = True

    if source_is_live:
        return "source_is_live"

    # ------------------------------------------------------------------
    # 2. Resolve local installed version
    # ------------------------------------------------------------------
    local_sha = _rc_resolve_version_txt(install_root)
    if local_sha is None:
        # No version.txt — check whether the install-root is a git work-tree.
        # A bare/junctioned git clone has no version.txt but IS a git
        # work-tree and MUST NOT be silently exempt — it may be many commits
        # behind origin/main.
        #
        # negative-spec: returning source_is_live here was the pre-fix
        # behaviour that caused a false "not shipped" blocker (a stale clone
        # got no "you're behind" warning). Do NOT revert to unconditional
        # source_is_live for the no-version.txt case.
        #
        # CONTRIBUTOR-CLONE GUARD (the Staff Engineer F3): before counting behind-ness,
        # check whether this clone is registered as
        # propagation_mode=source_is_live in the machine-local registry. An
        # authoring/contributor box has a git clone but no version.txt and IS
        # source_is_live — its live_path is the very content root the
        # resolver returns. On a contributor's feature/work branch a
        # behind-count would produce a false "N commits behind origin/main"
        # nag during normal development. source_is_live-registered clones are
        # silent.
        reg_live = _rc_registry_live_path()
        if reg_live and reg_live.rstrip("/") == install_root.rstrip("/"):
            return "source_is_live"

        if _rc_is_git_worktree(install_root):
            behind = _rc_git_clone_behind_count(install_root)
            if behind is None:
                # Fetch failed → treat as offline (no 3-day sentinel; retry next boot)
                return "offline"
            count, ref = behind
            if count > 0:
                return f"behind-clone {count} {ref}"
            return "current"

        # Not a git work-tree and no version.txt — genuinely no managed
        # install; treat as source_is_live (e.g. a standalone tool with no install).
        return "source_is_live"

    # ------------------------------------------------------------------
    # 3. Fetch latest published release tag
    # ------------------------------------------------------------------
    latest_tag = _rc_fetch_latest_release_tag(owner_repo)
    if latest_tag is None:
        return "offline"

    # Security (sec-audit HIGH+MEDIUM 2026-06-01): the tag is a
    # network-controlled string that flows into a `git ls-remote` refspec and
    # the return value. Validate it at this single chokepoint before any
    # further use — must start alphanumeric (blocks a leading '-' being read
    # as a git option) and contain only tag-legal chars, bounded length. A tag
    # that fails the allowlist is untrustworthy → treat as offline (no false
    # current/behind).
    if not _TAG_ALLOWLIST_RE.match(latest_tag):
        return "offline"

    # ------------------------------------------------------------------
    # 4. Resolve tag → commit SHA via git ls-remote (NEVER use target_commitish)
    # ------------------------------------------------------------------
    tag_sha = _rc_resolve_tag_sha(owner_repo, latest_tag)
    if tag_sha is None:
        return "offline"

    # ------------------------------------------------------------------
    # 5. Classify
    # ------------------------------------------------------------------
    if local_sha == tag_sha:
        return "current"

    # SHAs differ — check ancestry when install-root is a git checkout
    if _rc_check_ancestry(install_root, local_sha, tag_sha):
        # local SHA is a TRUE ANCESTOR of tag SHA → directional "behind"
        from_label = _rc_local_describe_tag(install_root, local_sha)
        return f"behind {from_label} {latest_tag}"

    # ahead / diverged / ancestry unverifiable → NEUTRAL "differs"
    return f"differs {latest_tag}"
