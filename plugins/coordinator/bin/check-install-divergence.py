"""coordinator/bin/check-install-divergence.py

Three-way blob-SHA install-divergence classifier. Shared primitive for
agentic install integrity — see docs/wiki/agentic-install-integrity.md
for the doctrine, deferred extensions, and `version.txt` sentinel format.

Lifted verbatim-on-contract 2026-05-28 from:
  X:/project-rag/project_rag_scripts/lib/check_install_divergence.py

PUBLIC CONTRACT (pinned — downstream consumers bind to these surfaces):

  Exit codes:
    0  unchanged + forward-safe only; no divergence (safe to proceed).
    2  no/malformed baseline; ran baseline-free two-way comparison; live
       matches incoming (clean reinstall, safe to proceed).
    3  one or more consumer-modified or consumer-added files detected
       (gate fires; installer should ask `[y/N]` or abort under --force).

  Exit code 1 is RESERVED for invalid CLI input (missing/non-directory
  --source or --live). It is NOT part of the divergence-classification
  contract — downstream consumers MUST NOT bind on it.

  JSON stdout schema (when --format json):
    {
      "baseline_status": str,
      "counts": {
        "unchanged": int,
        "forward_safe": int,
        "consumer_modified": int,
        "consumer_added": int
      },
      "consumer_modified": [{"path": str, "hunk": str}, ...],
      "consumer_added": [str, ...]
    }

  CLI flags:
    --source <git-repo-root>    (required)
    --live <resident-dir>       (required)
    --baseline-sha <40-hex>     (optional; else reads <live>/version.txt)
    --format text|json          (optional, default text)

  Machine-readable contract anchor:
    setup/tests/contract/install_divergence_contract.json

  Cross-tool discipline: this file and `coordinator/bin/check-plugin-drift.sh`
  share the `git hash-object --path <relpath>` blob-SHA idiom so that
  gitattributes apply symmetrically. If you change one, review the other.

Named consumers (cross-repo contract commitments):
  - claude-unreal-holodeck: bin/check-reverse-drift.sh,
    scripts/holodeck_recover.sh --step reverse-drift
  - project-rag-ue-addon (sentinel-only adopter via separable
    install-sentinel-write)
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Sentinel objects — MUST be distinct objects that can never equal each other
# or any real 40-hex SHA string.  Using module-level object() singletons
# guarantees identity-safe sentinel comparisons (is / is not) across all
# callers within a single interpreter session.
# ---------------------------------------------------------------------------

ABSENT_LIVE = object()      # file not present in the live (resident) directory
ABSENT_BASELINE = object()  # file not recorded in the baseline git tree

# Regex that a valid 40-hex SHA must fully match.
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

# Hunk rendering caps.
_MAX_HUNK_LINES_PER_FILE = 40
_MAX_HUNK_FILES = 10

# Files/dirs to exclude when walking the live directory.
# Windows-only: suppress the console window that git.exe flashes when this
# process has no console to inherit (e.g. spawned by a scheduled task or a GUI
# Claude Code host). POSIX: empty dict — CREATE_NO_WINDOW is a Windows-only
# attribute, so the ternary short-circuits before touching it.
_NO_CONSOLE_WINDOW = (
    {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
)

_LIVE_WALK_EXCLUDES = {".git", "__pycache__"}
_LIVE_WALK_SUFFIXES_EXCLUDE = {".pyc"}
_LIVE_WALK_NAMES_EXCLUDE = {"version.txt"}


# ---------------------------------------------------------------------------
# Helpers — git subprocess wrappers
# ---------------------------------------------------------------------------

def _run_git(args: list[str], *, source: Path) -> str:
    """Run a git command rooted at *source*, return stdout stripped.

    Raises ``RuntimeError`` on non-zero exit so callers fail loud — no silent
    swallowing per the spec's "fail loud on git errors" constraint.
    """
    cmd = ["git", "-C", str(source)] + args
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        **_NO_CONSOLE_WINDOW,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git command failed (exit {result.returncode}): {' '.join(cmd)}\n"
            f"stderr: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def _git_ls_files(source: Path) -> list[str]:
    """Return the list of source-tracked relpaths (``git ls-files``)."""
    output = _run_git(["ls-files"], source=source)
    if not output:
        return []
    return output.splitlines()


def _git_ls_tree_sha(source: Path, baseline_sha: str, relpath: str) -> object:
    """Return the blob SHA of *relpath* at *baseline_sha*, or ``ABSENT_BASELINE``.

    Uses ``git ls-tree <sha> -- <relpath>``; only blob entries are considered.
    """
    # ls-tree itself failing (e.g. invalid SHA) is a hard error — let RuntimeError
    # propagate to the caller.  An absent path returns an empty string with exit 0,
    # handled below.
    output = _run_git(
        ["ls-tree", baseline_sha, "--", relpath],
        source=source,
    )

    if not output:
        return ABSENT_BASELINE

    # ls-tree line format: "<mode> <type> <sha>\t<path>"
    parts = output.split("\t", 1)
    if len(parts) < 2:
        return ABSENT_BASELINE
    meta = parts[0].split()
    if len(meta) < 3 or meta[1] != "blob":
        return ABSENT_BASELINE
    return meta[2]


def _git_hash_object(source: Path, relpath: str, file_path: Path) -> object:
    """Return the git blob SHA for *file_path* applying gitattributes via *relpath*.

    The ``--path <relpath>`` argument is load-bearing: it drives gitattributes
    resolution (e.g. ``tests/** eol=lf``) symmetrically for both live and
    incoming sides regardless of where the file physically lives.

    Returns ``ABSENT_LIVE`` when *file_path* does not exist (absent in live dir).
    """
    if not file_path.exists():
        return ABSENT_LIVE

    # RuntimeError from _run_git (non-zero git exit) propagates to the caller.
    output = _run_git(
        ["hash-object", "--path", relpath, "--", str(file_path)],
        source=source,
    )

    stripped = output.strip()
    if stripped:
        return stripped
    # Review: the Staff Engineer F8 — file exists (checked above) but git returned empty output;
    # returning ABSENT_LIVE here would silently mis-classify an existing file as absent.
    # Fail loud so the ambiguous case is visible rather than silently wrong.
    raise RuntimeError(
        f"git hash-object returned empty output for existing file: {file_path}"
    )


# ---------------------------------------------------------------------------
# File set construction
# ---------------------------------------------------------------------------

def _walk_live_dir(live: Path) -> set[str]:
    """Walk *live* and return relpaths of all files (POSIX-slashed), excluding
    ``.git/``, ``__pycache__/``, ``*.pyc``, and ``version.txt``.

    This produces side (b) of the union file set: files present in the live
    tree that may not be source-tracked.
    """
    result: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(live):
        # Prune excluded directories in-place so os.walk skips them.
        dirnames[:] = [d for d in dirnames if d not in _LIVE_WALK_EXCLUDES]

        for fname in filenames:
            if fname in _LIVE_WALK_NAMES_EXCLUDE:
                continue
            suffix = Path(fname).suffix
            if suffix in _LIVE_WALK_SUFFIXES_EXCLUDE:
                continue
            abs_path = Path(dirpath) / fname
            try:
                relpath = abs_path.relative_to(live)
            except ValueError:
                continue
            # Normalise to POSIX separators so relpaths match git ls-files output
            # on all platforms.
            result.add(relpath.as_posix())
    return result


# ---------------------------------------------------------------------------
# Hunk rendering
# ---------------------------------------------------------------------------

def _render_hunk(
    source: Path,
    relpath: str,
    live: Path,
    live_sha: object,
    incoming_file: Path,
) -> str:
    """Return a capped unified-diff hunk string for a consumer-modified file.

    Special case: if ``live_sha is ABSENT_LIVE``, the file was deleted in the
    consumer's copy and the install will restore it.  In that case we return a
    descriptive message rather than attempting to read non-existent live bytes
    (which would raise ``FileNotFoundError``).
    """
    if live_sha is ABSENT_LIVE:
        return "  [file deleted in your copy; install will restore it]"

    live_file = live / relpath

    # Read live bytes; skip hunk for binary files (heuristic: NUL in first 8 KB).
    try:
        live_bytes = live_file.read_bytes()
    except OSError:
        return "  [could not read live file; skipping hunk]"

    if b"\x00" in live_bytes[:8192]:
        return "  [binary file — skipping diff hunk]"

    # Read incoming bytes; skip hunk on binary or read error.
    try:
        incoming_bytes = incoming_file.read_bytes()
    except OSError:
        return "  [could not read incoming file; skipping hunk]"

    if b"\x00" in incoming_bytes[:8192]:
        return "  [binary file — skipping diff hunk]"

    live_lines = live_bytes.decode("utf-8", errors="replace").splitlines(keepends=True)
    incoming_lines = incoming_bytes.decode("utf-8", errors="replace").splitlines(keepends=True)

    diff_lines = list(
        difflib.unified_diff(
            live_lines,
            incoming_lines,
            fromfile=f"live/{relpath}",
            tofile=f"incoming/{relpath}",
        )
    )

    if not diff_lines:
        return "  [no textual difference]"

    capped = diff_lines[:_MAX_HUNK_LINES_PER_FILE]
    overflow = len(diff_lines) - _MAX_HUNK_LINES_PER_FILE
    hunk_text = "".join(capped)
    if overflow > 0:
        hunk_text += f"  … +{overflow} more lines\n"
    return hunk_text.rstrip("\n")


# ---------------------------------------------------------------------------
# Core classification logic
# ---------------------------------------------------------------------------

class _FileRecord(NamedTuple):
    relpath: str
    baseline_sha: object   # str | ABSENT_BASELINE | None (no baseline mode)
    incoming_sha: object   # str | ABSENT_LIVE
    live_sha: object       # str | ABSENT_LIVE


def _is_binary(file_path: Path) -> bool:
    """Heuristic binary test: NUL byte in first 8 KB."""
    try:
        return b"\x00" in file_path.read_bytes()[:8192]
    except OSError:
        return False


def _consumer_in_sync(live_blob: object, baseline: object) -> bool:
    """Return True when the consumer's live copy is in sync with the baseline.

    Two cases count as in-sync:
    1. ``live_blob == baseline`` — consumer has exactly the content that was shipped.
    2. ``live_blob is ABSENT_LIVE and baseline is ABSENT_BASELINE`` — file is new
       in the source; the consumer never had it (nothing to lose); the install will
       simply add it.  This is a normal forward-ADD, not a consumer-modified case.

    The second case is the critical correction: without it, every new file added to
    the source between two releases would be false-flagged as consumer-modified on
    copy-install update, causing non-interactive ``--force`` updates to abort on the
    dominant update path.

    Negative-spec:
    - ``live is ABSENT_LIVE, baseline is real SHA`` → NOT in_sync → consumer deleted
      a shipped file → consumer-modified (F4 absent-live hunk guard still applies).
    - ``live is real SHA, baseline is ABSENT_BASELINE`` → NOT in_sync → consumer
      created a file that now exists in source but with different content → treat as
      consumer-modified (conservative; rare in practice).
    """
    if live_blob == baseline:
        return True
    if live_blob is ABSENT_LIVE and baseline is ABSENT_BASELINE:
        return True
    return False


def _classify_with_baseline(
    source: Path,
    live: Path,
    baseline_sha: str,
    relpaths: list[str],
) -> dict[str, list]:
    """Classify *relpaths* using the three-way (baseline vs live vs incoming) algorithm.

    Bucket precedence (checked in order):
      1. ``live == incoming``          → unchanged
      2. ``_consumer_in_sync(...)``    → forward-safe  (covers both the normal
         "consumer untouched, new content coming" case AND the new-in-source
         forward-ADD case where live=ABSENT_LIVE and baseline=ABSENT_BASELINE)
      3. ``live != incoming``          → consumer-modified-will-be-overwritten

    Returns a dict with keys:
      unchanged, forward_safe, consumer_modified

    ``consumer_added`` files (live-walk paths absent from source ls-files) are
    computed by the caller from the live walk; they are not in ``relpaths``.
    """
    unchanged: list[str] = []
    forward_safe: list[str] = []
    consumer_modified: list[str] = []

    for relpath in relpaths:
        incoming_file = source / relpath
        live_file = live / relpath

        baseline = _git_ls_tree_sha(source, baseline_sha, relpath)
        incoming = _git_hash_object(source, relpath, incoming_file)
        live_blob = _git_hash_object(source, relpath, live_file)

        if live_blob == incoming:
            # Covers: clean copy, consumer already at new version, new-in-source
            # file the consumer also happens to have (live sha matches incoming sha).
            unchanged.append(relpath)
        elif _consumer_in_sync(live_blob, baseline):
            # Consumer has exactly the shipped baseline (or never had this new file)
            # and the install brings new/different content → safe forward update.
            forward_safe.append(relpath)
        else:
            # Consumer's copy diverges from both baseline and incoming → loss risk.
            # Includes: consumer edited a shipped file, consumer deleted a shipped
            # file (live=ABSENT_LIVE, baseline=real), consumer created a file that
            # is now also in source but with different content.
            consumer_modified.append(relpath)

    return {
        "unchanged": unchanged,
        "forward_safe": forward_safe,
        "consumer_modified": consumer_modified,
    }


def _classify_two_way(
    source: Path,
    live: Path,
    relpaths: list[str],
) -> list[str]:
    """Baseline-free two-way comparison: return relpaths where live != incoming.

    Two skip cases (not divergence):
    1. Both absent (``live is ABSENT_LIVE and incoming is ABSENT_LIVE``) — the
       spec-required guard; cannot happen for live-walked paths but guards
       source-tracked paths where the file is gone from both sides.
    2. New-in-source forward-ADD (``live is ABSENT_LIVE and incoming is real SHA``)
       — file exists in source but not yet in the consumer's live tree.  Under no
       baseline this is indistinguishable from "never installed" vs "consumer
       deleted it", so we treat it as a forward-add (safe) rather than divergence.
       This mirrors the three-way ``_consumer_in_sync`` logic: with a baseline the
       (ABSENT_LIVE, ABSENT_BASELINE) pair is also forward-safe; without a baseline
       we apply the same principle conservatively.  The alternative — treating every
       absent-live source-tracked file as divergence under no-baseline — would abort
       any first-time copy-install update.

    Files present in live but absent from source (``live is real, incoming is
    ABSENT_LIVE``) ARE genuine divergence: consumer added a file the source doesn't
    have → ``consumer-added-will-be-deleted`` territory.
    """
    diverged: list[str] = []
    for relpath in relpaths:
        incoming_file = source / relpath
        live_file = live / relpath

        incoming = _git_hash_object(source, relpath, incoming_file)
        live_blob = _git_hash_object(source, relpath, live_file)

        # Skip case 1: both absent (spec-required guard).
        if live_blob is ABSENT_LIVE and incoming is ABSENT_LIVE:
            continue

        # Skip case 2: new-in-source forward-ADD — live doesn't have it yet;
        # not a consumer edit, not a loss risk.
        if live_blob is ABSENT_LIVE and incoming is not ABSENT_LIVE:
            continue

        if live_blob != incoming:
            diverged.append(relpath)

    return diverged


# ---------------------------------------------------------------------------
# Baseline SHA resolution
# ---------------------------------------------------------------------------

def _resolve_baseline(live: Path, cli_sha: str | None) -> tuple[str | None, str]:
    """Return ``(sha_or_None, status_message)``.

    *sha_or_None* is a validated 40-hex SHA or ``None`` (no/malformed baseline).
    *status_message* describes what was found.
    """
    if cli_sha is not None:
        if _SHA_RE.fullmatch(cli_sha):
            return cli_sha, f"baseline SHA from --baseline-sha: {cli_sha}"
        return None, f"--baseline-sha value is malformed (not 40-hex): {cli_sha!r}"

    sentinel = live / "version.txt"
    if not sentinel.exists():
        return None, "no version.txt sentinel found in live directory"

    raw = sentinel.read_text(encoding="utf-8", errors="replace").strip("\r\n").strip()
    if _SHA_RE.fullmatch(raw):
        return raw, f"baseline SHA from version.txt: {raw}"
    return None, f"version.txt content is malformed (not 40-hex): {raw!r}"


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def _build_hunks(
    source: Path,
    live: Path,
    consumer_modified: list[str],
    live_sha_map: dict[str, object],
) -> list[dict]:
    """Return a list of ``{path, hunk}`` dicts for *consumer_modified* files."""
    result = []
    for i, relpath in enumerate(consumer_modified):
        if i >= _MAX_HUNK_FILES:
            remaining = len(consumer_modified) - _MAX_HUNK_FILES
            result.append({
                "path": f"… +{remaining} more files",
                "hunk": "",
            })
            break
        hunk = _render_hunk(
            source,
            relpath,
            live,
            live_sha_map.get(relpath, ABSENT_LIVE),
            source / relpath,
        )
        result.append({"path": relpath, "hunk": hunk})
    return result


def _print_text_report(
    counts: dict[str, int],
    consumer_modified_hunks: list[dict],
    consumer_added: list[str],
    baseline_status: str,
    *,
    file=None,
) -> None:
    """Print a human-readable text report to *file* (default stdout)."""
    if file is None:
        file = sys.stdout

    print(f"[divergence-check] {baseline_status}", file=file)
    print(
        f"  unchanged={counts['unchanged']}  "
        f"forward-safe={counts['forward_safe']}  "
        f"consumer-modified={counts['consumer_modified']}  "
        f"consumer-added={counts['consumer_added']}",
        file=file,
    )

    if consumer_modified_hunks:
        print("\nconsumer-modified files (will be overwritten by install):", file=file)
        for entry in consumer_modified_hunks:
            path = entry["path"]
            hunk = entry.get("hunk", "")
            if path.startswith("…"):
                print(f"  {path}", file=file)
            else:
                print(f"\n  --- {path}", file=file)
                if hunk:
                    for line in hunk.splitlines():
                        print(f"  {line}", file=file)

    if consumer_added:
        print("\nconsumer-added files (will be deleted — not in source):", file=file)
        for p in consumer_added:
            print(f"  {p}", file=file)


def _build_json_output(
    counts: dict[str, int],
    consumer_modified_hunks: list[dict],
    consumer_added: list[str],
    baseline_status: str,
) -> dict:
    return {
        "baseline_status": baseline_status,
        "counts": counts,
        "consumer_modified": consumer_modified_hunks,
        "consumer_added": consumer_added,
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(
    source: Path,
    live: Path,
    baseline_sha_cli: str | None = None,
    fmt: str = "text",
) -> int:
    """Classify divergence between *source* repo and *live* resident directory.

    Returns the exit code (0, 2, or 3).  All output is written to stdout.
    """
    # 1. Resolve baseline.
    baseline_sha, baseline_status = _resolve_baseline(live, baseline_sha_cli)

    # 2. Build the union file set.
    tracked = _git_ls_files(source)                # side (a) — source-tracked
    tracked_set = set(tracked)
    live_walk = _walk_live_dir(live)               # side (b) — live-present
    consumer_added = sorted(live_walk - tracked_set)
    union = sorted(tracked_set | live_walk)

    if baseline_sha is None:
        # ----------------------------------------------------------------
        # No/malformed baseline → two-way fallback (live vs incoming).
        # ----------------------------------------------------------------
        diverged = _classify_two_way(source, live, union)

        # Review: the Staff Engineer F2 — split diverged into consumer_added (live-only files not
        # tracked in source) and consumer_modified (source-tracked files with live!=incoming).
        # Previously everything was lumped under consumer_modified with consumer_added=0,
        # causing undercounting and misnaming of consumer-added files in two-way mode.
        consumer_added_2w = sorted(r for r in diverged if r not in tracked_set)
        consumer_modified_2w = sorted(r for r in diverged if r in tracked_set)

        # Build a live_sha_map for hunk rendering — only for consumer_modified files
        # (consumer_added have no incoming counterpart to diff against).
        live_sha_map_2w: dict[str, object] = {}
        for relpath in consumer_modified_2w:
            live_file = live / relpath
            live_sha_map_2w[relpath] = _git_hash_object(source, relpath, live_file)
        diverged_hunks: list[dict] = _build_hunks(
            source, live, consumer_modified_2w, live_sha_map_2w
        )

        counts_2w = {
            "unchanged": len(union) - len(diverged),
            "forward_safe": 0,
            "consumer_modified": len(consumer_modified_2w),
            "consumer_added": len(consumer_added_2w),
        }

        if fmt == "json":
            out = _build_json_output(
                counts=counts_2w,
                consumer_modified_hunks=diverged_hunks,
                consumer_added=consumer_added_2w,
                baseline_status=baseline_status,
            )
            print(json.dumps(out, indent=2))
        else:
            _print_text_report(counts_2w, diverged_hunks, consumer_added_2w, baseline_status)

        if diverged:
            # Two-way fallback found differences → cannot prove edit vs update → gate fires.
            return 3

        # Two-way clean reinstall.
        return 2

    # ----------------------------------------------------------------
    # Three-way classification (baseline present).
    # ----------------------------------------------------------------

    buckets = _classify_with_baseline(source, live, baseline_sha, tracked)
    # ``consumer_added`` already computed above from the live walk.

    # Build a live_sha_map for hunk rendering.
    live_sha_map: dict[str, object] = {}
    for relpath in buckets["consumer_modified"]:
        live_file = live / relpath
        live_sha_map[relpath] = _git_hash_object(source, relpath, live_file)

    consumer_modified_hunks = _build_hunks(
        source, live, buckets["consumer_modified"], live_sha_map
    )

    counts = {
        "unchanged": len(buckets["unchanged"]),
        "forward_safe": len(buckets["forward_safe"]),
        "consumer_modified": len(buckets["consumer_modified"]),
        "consumer_added": len(consumer_added),
    }

    if fmt == "json":
        out = _build_json_output(counts, consumer_modified_hunks, consumer_added, baseline_status)
        print(json.dumps(out, indent=2))
    else:
        _print_text_report(counts, consumer_modified_hunks, consumer_added, baseline_status)

    if buckets["consumer_modified"] or consumer_added:
        return 3

    return 0


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Three-way blob-SHA divergence classifier for install-divergence detection. "
            "Exit 0: safe to proceed. Exit 2: no baseline, two-way clean. "
            "Exit 3: consumer-modified or consumer-added files detected."
        ),
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Absolute path to the source git repository.",
    )
    parser.add_argument(
        "--live",
        required=True,
        help="Absolute path to the resident (live) plugin directory.",
    )
    parser.add_argument(
        "--baseline-sha",
        default=None,
        help=(
            "Explicit 40-hex baseline SHA. If omitted, reads <live>/version.txt. "
            "If neither is available, falls back to two-way comparison (exits 2 or 3)."
        ),
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text).",
    )
    args = parser.parse_args(argv)

    source = Path(args.source)
    live = Path(args.live)

    if not source.is_dir():
        print(f"ERROR: --source path does not exist or is not a directory: {source}", file=sys.stderr)
        return 1

    if not live.is_dir():
        print(f"ERROR: --live path does not exist or is not a directory: {live}", file=sys.stderr)
        return 1

    return run(source, live, baseline_sha_cli=args.baseline_sha, fmt=args.format)


if __name__ == "__main__":
    sys.exit(_main())
