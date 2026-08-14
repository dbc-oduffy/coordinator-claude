"""verify-doe-root-seam-sync.py — verify (or fix) that every cold-path `.doe-root`
literal READ in the coordinator corpus is durable-first (DR-072): it must try
the settings-home pointer
(`${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/machine-local/.doe-root`)
BEFORE falling back to the legacy `${CLAUDE_HOME:-$HOME}/.claude/.doe-root`
read. A site that resolves ONLY to the resettable/synced `~/.claude` tree —
no settings-home rung at all — strands the moment C5 (untrack) lands and the
machine gets reset, because `~/.claude/.doe-root` no longer survives reset.

Distinct from the sibling `verify-cc-root-source-guard-sync.py` (retired
2026-07-23 — zero remaining resolve-sites, see docs/plans/2026-07-23-skills-
carry-no-code-extirpation.md task M4), which verified the CLAUDE_PLUGIN_ROOT
TRUST-GUARD (an unrelated concern — whether a resolved root is inside a
trusted prefix) — this script verifies the `.doe-root` POINTER READ ITSELF.
Mirrors that retired script's --list/--dry-run/--fix CLI contract and
corpus-wide grep-discovery shape (dynamic-discovery, not registry-enrolled —
see
docs/wiki/coordinator-tripwires.md § CLAUDE-PLUGIN-ROOT-SOURCE-GUARD for the
established rationale, which applies equally here).

TWO POPULATIONS (Review: the Director of Engineering F1, docs/plans/2026-07-21-durable-coordinator-
root-pointer.md § C3): the 198-shape sites (`CLAUDE_PLUGIN_ROOT:-` ∩
`doe-root` on one line, e.g. `_cc_root=`) are a strict SUBSET of the
reset-critical reader population — the bare-`cat` `_cc_doe=` sibling lines
(no `CLAUDE_PLUGIN_ROOT:-` token) and the 217-form `~/.claude/.doe-root`
PROSE occurrences must also be considered. This script's discovery regex
(DOE_ROOT_CAT_RE below) matches on the underlying `cat "…/.doe-root"` READ
call itself, not on `CLAUDE_PLUGIN_ROOT:-` co-occurrence — so it catches
BOTH populations uniformly. A checker that only re-discovered the 198-shape
would not catch a stranded bare-`cat` reader (the exact gap this script
exists to close).

KNOWN-BUG note (state/bug-backlog/2026-07-20-verify-cc-root-source-guard-
sync-sh-fix-45a068a7b9c1.yaml): the sibling script's `--fix` broke by
extracting the WRONG fenced block from a multi-block markdown SSOT doc
(`snippets/cc-root-source-guard.md`). This script's `--fix` has no
SSOT-doc-fenced-block-extraction step — the replacement is a single fixed
literal substitution (not an extracted markdown block), so that specific
bug class does not apply structurally. As a defense-in-depth measure
against a *similar* class of defect, `--fix` re-verifies every file it
touches immediately after writing (see apply_fix()) and reports a hard
error — not a silent "fixed" claim — if a post-fix re-scan still finds an
unmigrated site in a file it just rewrote.

Usage:
    verify-doe-root-seam-sync.py             Verify all in-scope sites. Exit non-zero on any UNMIGRATED site.
    verify-doe-root-seam-sync.py --list       List all in-scope consumer files (after exclusion filter).
    verify-doe-root-seam-sync.py --dry-run    Print unified diff of the mechanical fix (alias: --diff).
    verify-doe-root-seam-sync.py --fix        Idempotent auto-fix: rewrite unmigrated sites durable-first.

Exit codes: 0 clean/fixed, 1 UNMIGRATED site(s) found (verify) or a file
still fails re-verify after --fix, 2 usage error.

Prior art (script shape mirrored): coordinator/bin/verify-cc-root-source-guard-sync.py (retired 2026-07-23)
"""
# Spec backlink: DoE-claude:pln-durable-coordinator-root-point-37e1e6 § C3, § AC2

from __future__ import annotations

import difflib
import os
import re
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
SCRIPT_DIR = SCRIPT_PATH.parent

GENERATES = []  # --fix rewrites discovered `.doe-root` cat-read sites in place, but `--list` against this checkout resolves zero in-scope sites inside claude-klabauter's own tree today (all live matches are under the DoE-claude checkout) — no fixed or currently-realized claude-klabauter artifact

# Defensive self-locate for the coordinator_registry sibling import — mirrors
# the sys.path.insert convention every bin/ entrypoint already uses (see
# coordinator/bin/verify-templates-bin-sync.py's own _LIB_DIR insertion).
_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from coordinator_registry import _DoeUnresolvable, doe_root  # noqa: E402

_HELP_TEXT = __doc__ or ""

# ---------------------------------------------------------------------------
# Exclusion list — files that legitimately keep a bare/legacy `.doe-root` cat
# read and must NOT be flagged or rewritten by this script.
# ---------------------------------------------------------------------------
EXCLUDED_SUFFIXES = [
    # already durable-first (C1/C2) — their bare-cat line is the intentional
    # FALLBACK rung after an already-attempted settings-home read, not an
    # unmigrated site. Rewriting these would double-wrap the fallback.
    "coordinator/lib/read-doe-root-pointer.sh",
    "coordinator/lib/coordinator-trusted-root-guard.sh",
    "coordinator/snippets/cc-root-source-guard.md",
    # self-reference — this script's own header/body prose contains the
    # pattern as documentation, not as a live resolve-site.
    "coordinator/bin/verify-doe-root-seam-sync.py",
    "coordinator/bin/verify-doe-root-seam-sync.sh",
    # NOTE: the sibling CLAUDE_PLUGIN_ROOT trust-guard verifier
    # (verify-cc-root-source-guard-sync.{sh,py}) used to need an entry here —
    # its INLINE_CORE_MARKERS array hardcoded the LEGACY fallback literal as
    # fixture-DATA for an unrelated system, not a live .doe-root resolve-site.
    # That script was retired 2026-07-23 (zero remaining resolve-sites in the
    # corpus it scanned — see docs/plans/2026-07-23-skills-carry-no-code-
    # extirpation.md task M4), so the entry is gone rather than dangling.
    # this script's OWN characterization pytest (2026-07-21 de-bash port,
    # chunk E3-a-doeroot) — the legacy-shape literals it asserts against are
    # fixture-DATA for the transform-pattern tests, not live resolve-sites.
    "coordinator/tests/test_verify_doe_root_seam_sync.py",
    # sibling guard's OWN test infrastructure — tests the trust-guard's
    # behavior against a synthetic/isolated pointer file; out of this
    # script's scope (a different system's test fixtures/data). Now the
    # pytest ports (2026-07-21 de-bash port, plan docs/plans/2026-07-21-
    # bash-kill-fast-tier-pytest-port.md C1-C4) — same fixture-DATA .doe-root
    # read as their bash predecessors, not a live resolve-site. __pycache__
    # compiled artifacts embed the same string constants and match the same
    # discovery grep — excluded as a whole directory so a stale/regenerated
    # .pyc filename (Python-version-tagged, unstable) never has to be
    # enumerated by name.
    "coordinator/tests/test_cc_root_guard_fixer_sync.py",
    "coordinator/tests/test_cc_root_guard_placement_lint.py",
    "coordinator/tests/test_cc_root_source_guard.py",
    "coordinator/tests/__pycache__",
    "coordinator/bin/tests/fixtures/cc-root-source-guard-fix",
    # peer-authored regression net (docs/plans/2026-07-21-durable-coordinator-
    # root-pointer.md § C4) — deliberately simulates a reset (legacy pointer
    # present, settings-home absent) to prove fallback behavior; its
    # intentionally-bare legacy-only read is test setup, not a live site.
    "coordinator/bin/tests/test-doe-root-durable-resolution.sh",
]

# ---------------------------------------------------------------------------
# Discovery: every file containing at least one `cat "…/.doe-root"` READ.
# Matches the underlying read call, not `CLAUDE_PLUGIN_ROOT:-` co-occurrence —
# this is what makes the discovery cover the full reset-critical population,
# not just the 198-shape subset.
# ---------------------------------------------------------------------------
DOE_ROOT_CAT_RE = re.compile(r'cat "[^"]*\.doe-root"')
MARKER_RE = re.compile(r"COORDINATOR_SETTINGS_HOME")

# A file's `.doe-root` cat-read LINE is UNMIGRATED iff it matches the read
# pattern AND no settings-home durable-first marker appears on that line OR
# within the preceding LOOKBACK_WINDOW lines of the SAME file — i.e. the read
# resolves ONLY to the legacy `~/.claude` tree, with no settings-home rung
# reachable ahead of it. The window (not same-line-only) is required because
# several legitimate shapes split the durable-first read and its legacy
# fallback across two lines (e.g. claude-doe-shim.sh.tmpl's `claude()`
# function body, git_hook_install.py's rung-2 loop) — a same-line-only check
# would false-flag the second (fallback) line of an already-migrated pair.
LOOKBACK_WINDOW = 10

# Directories never worth walking into for a text-pattern discovery scan
# (binary/compiled/VCS-internal content that cannot carry a live shell
# resolve-site). Faithful to the bash predecessor's `grep -rlE` in practice
# (grep would traverse these too, but zlib-compressed git objects never
# textually match), while avoiding the wasted walk cost.
_SKIP_DIR_NAMES = {".git", "__pycache__", "node_modules", ".claude"}


def is_excluded(fpath: str) -> bool:
    # `EXCLUDED_SUFFIXES` entries are forward-slash-delimited; `fpath` comes
    # from `str(Path(...))`, which is backslash-separated on Windows. Without
    # normalizing, every suffix/infix comparison below silently never matches
    # on Windows and every excluded file false-flags as UNMIGRATED.
    fpath = Path(fpath).as_posix()
    for suffix in EXCLUDED_SUFFIXES:
        if fpath == suffix or fpath.endswith("/" + suffix) or ("/" + suffix + "/") in fpath:
            return True
    return False


def _iter_candidate_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIR_NAMES]
        for name in filenames:
            yield Path(dirpath) / name


def discover_files(roots: Path | list[Path]) -> list[str]:
    """Discover in-scope `.doe-root` cat-read sites under one or more roots.

    Accepts either a single Path (back-compat) or a list of Paths — the
    latter unions claude-klabauter's own coordinator/ tree with the DoE-resident
    coordinator/ tree (see _resolve_scan_roots()), deduping by resolved
    path so a root nested inside another root's walk is not double-counted.
    """
    root_list = [roots] if isinstance(roots, Path) else list(roots)
    seen_paths: set[Path] = set()
    found = []
    for root in root_list:
        for path in _iter_candidate_files(root):
            resolved = path.resolve()
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except (OSError, UnicodeDecodeError):
                continue
            if not DOE_ROOT_CAT_RE.search(text):
                continue
            fpath = str(path)
            if not is_excluded(fpath):
                found.append(fpath)
    return sorted(found)


def file_unmigrated_lines(fpath: str) -> list[tuple[int, str]]:
    """Return the (lineno, text) pairs for cat-read lines with no reachable
    settings-home marker within LOOKBACK_WINDOW lines above them (inclusive
    of the marker line itself)."""
    try:
        text = Path(fpath).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    lines = text.splitlines()
    marker_linenos = [i + 1 for i, line in enumerate(lines) if MARKER_RE.search(line)]

    unmigrated = []
    for i, line in enumerate(lines):
        if not DOE_ROOT_CAT_RE.search(line):
            continue
        lineno = i + 1
        migrated = any(
            mline <= lineno and (lineno - mline) <= LOOKBACK_WINDOW
            for mline in marker_linenos
        )
        if not migrated:
            unmigrated.append((lineno, line))
    return unmigrated


# ---------------------------------------------------------------------------
# Fix generator (verify / dryrun / fix all share this). Mirrors the
# durable-first literal used by C1's read-doe-root-pointer.sh / C2's
# cc-root-source-guard.md WARM shape, but inlines the computed default with
# NO lib-sourcing (COLD shape — settings-home.sh:35-39 is the canonical
# expansion cited by C3; these sites run before coordinator is on PATH and
# cannot source a lib).
# ---------------------------------------------------------------------------
DURABLE = '${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/machine-local/.doe-root'
DURABLE_HOME_ONLY = '${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/machine-local/.doe-root'

_PAT1 = re.compile(r'cat "\$\{CLAUDE_HOME:-\$\{?HOME\}?\}/\.claude/\.doe-root" 2>/dev/null')
_PAT2 = re.compile(r'cat "\$HOME/\.claude/\.doe-root" 2>/dev/null')
_PAT3 = re.compile(r'cat "\$HOME/\.claude/\.doe-root"\)')


def _repl1(_m: re.Match) -> str:
    return f'cat "{DURABLE}" 2>/dev/null || cat "${{CLAUDE_HOME:-$HOME}}/.claude/.doe-root" 2>/dev/null'


def _repl2(_m: re.Match) -> str:
    return f'cat "{DURABLE_HOME_ONLY}" 2>/dev/null || cat "$HOME/.claude/.doe-root" 2>/dev/null'


def _repl3(_m: re.Match) -> str:
    return f'cat "{DURABLE_HOME_ONLY}" 2>/dev/null || cat "$HOME/.claude/.doe-root")'


def transform_text(text: str) -> tuple[str, bool]:
    """Apply the durable-first mechanical rewrite line-by-line. Returns
    (new_text, changed)."""
    out = []
    changed = False
    for line in text.splitlines(keepends=True):
        if "COORDINATOR_SETTINGS_HOME:-" in line:
            out.append(line)
            continue
        new = line
        if _PAT1.search(new):
            new = _PAT1.sub(_repl1, new)
        elif _PAT2.search(new):
            new = _PAT2.sub(_repl2, new)
        elif _PAT3.search(new):
            new = _PAT3.sub(_repl3, new)
        if new != line:
            changed = True
        out.append(new)
    return "".join(out), changed


def apply_fix(fpath: str) -> str:
    """Rewrite fpath durable-first if the transform changes it. Returns
    'CHANGED' or 'UNCHANGED', mirroring the original PY_TRANSFORM contract."""
    text = Path(fpath).read_text(encoding="utf-8")
    new_text, changed = transform_text(text)
    if changed:
        Path(fpath).write_text(new_text, encoding="utf-8")
        return "CHANGED"
    return "UNCHANGED"


def dry_run_diff(fpath: str) -> str:
    text = Path(fpath).read_text(encoding="utf-8")
    new_text, _changed = transform_text(text)
    diff = difflib.unified_diff(
        text.splitlines(keepends=True),
        new_text.splitlines(keepends=True),
        fromfile=fpath,
        tofile=f"{fpath} (proposed)",
    )
    return "".join(diff)


def _resolve_plugin_root() -> Path:
    env_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env_root:
        return Path(env_root)
    return SCRIPT_DIR.parent


def _resolve_scan_roots() -> list[Path]:
    """Union the two coordinator/ trees this corpus scan must cover.

    (i) claude-klabauter's own coordinator/ tree (via _resolve_plugin_root() — either
    CLAUDE_PLUGIN_ROOT or this script's own parent directory), and (ii) the
    DoE-resident coordinator/ tree (<doe_root()>/coordinator), since
    coordinator/ content post-migration is split across both repos and a
    `.doe-root` cat-read site can live in either half.

    If doe_root() is unresolvable (no DoE clone on this machine), the DoE
    half is WARN+skipped — this gate must still run standalone on a
    claude-klabauter-only checkout, not hard-fail for lacking a sibling clone.
    """
    roots = [_resolve_plugin_root()]
    try:
        doe_coordinator = Path(doe_root()) / "coordinator"
    except _DoeUnresolvable as exc:
        print(
            f"verify-doe-root-seam-sync.py: WARNING — coordinator doctrine repo root "
            f"unresolvable ({exc}); skipping the DoE-resident coordinator/ "
            "tree half of the scan.",
            file=sys.stderr,
        )
        return roots
    roots.append(doe_coordinator)
    return roots


def _print_help() -> None:
    # Mirrors the bash original's `sed -n '2,45p' ... | sed 's/^# \{0,1\}//'`
    # (module docstring body, minus the shebang line and the file's own
    # leading `#!/usr/bin/env python3` marker equivalent).
    print(_HELP_TEXT.strip("\n"))


def main(argv: list[str] | None = None) -> int:
    # Line-buffer stdout so interleaved stdout/stderr prints (verify's
    # per-file UNMIGRATED lines vs the trailing stderr FAIL summary) land in
    # the same relative order when both streams are redirected to one file
    # or terminal — matches the original bash script's line-buffered tty
    # behavior instead of Python's default full-buffering-when-not-a-tty.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, ValueError):
        pass
    argv = sys.argv[1:] if argv is None else argv

    mode = "verify"
    dry_run = False
    for arg in argv:
        if arg == "--fix":
            mode = "fix"
        elif arg in ("--dry-run", "--diff"):
            dry_run = True
        elif arg == "--list":
            mode = "list"
        elif arg in ("-h", "--help"):
            _print_help()
            return 0
        else:
            print(f"verify-doe-root-seam-sync.py: unknown argument '{arg}'", file=sys.stderr)
            return 2
    if dry_run:
        mode = "dryrun"

    scan_roots = _resolve_scan_roots()

    if mode == "list":
        for f in discover_files(scan_roots):
            print(f)
        return 0

    found = False
    for f in discover_files(scan_roots):
        unmigrated = file_unmigrated_lines(f)
        if not unmigrated:
            continue

        if mode == "verify":
            found = True
            print(f"UNMIGRATED: {f}")
            for lineno, text in unmigrated:
                print(f"    {lineno}:{text}")
        elif mode == "dryrun":
            found = True
            diff_text = dry_run_diff(f)
            if diff_text:
                print(diff_text, end="")
        elif mode == "fix":
            found = True
            result = apply_fix(f)
            if result == "CHANGED":
                # Re-verify immediately — defense-in-depth against the
                # sibling script's known --fix-defect class (see module
                # docstring KNOWN-BUG note above).
                remaining = file_unmigrated_lines(f)
                if remaining:
                    print(
                        f"ERROR: --fix rewrote {f} but an unmigrated site remains "
                        "post-fix — not a clean fix, refusing to claim success",
                        file=sys.stderr,
                    )
                    for lineno, text in remaining:
                        print(f"    {lineno}:{text}", file=sys.stderr)
                    return 1
                print(f"FIXED: {f}")
            else:
                print(
                    f"WARNING: {f} flagged UNMIGRATED but the transform made no "
                    "change — investigate a pattern gap",
                    file=sys.stderr,
                )

    if mode == "verify":
        if found:
            print("", file=sys.stderr)
            print(
                "verify-doe-root-seam-sync: FAIL — one or more .doe-root reads "
                "resolve ONLY to the legacy ~/.claude tree (no settings-home "
                "durable-first rung). Run with --fix to rewrite them durable-first, "
                "or --dry-run to preview.",
                file=sys.stderr,
            )
            return 1
        print("verify-doe-root-seam-sync: all in-scope .doe-root reads are durable-first. OK")
        return 0

    if mode == "dryrun" and not found:
        print(
            "verify-doe-root-seam-sync: nothing to fix — all in-scope .doe-root "
            "reads are already durable-first."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
