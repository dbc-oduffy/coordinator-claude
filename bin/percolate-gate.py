#!/usr/bin/env python3
"""percolate-gate.py — naked-Python engine for the `/percolate` skill's
residual imperative gate logic (DoE-claude coordinator/skills/percolate/SKILL.md).

Ports the four genuine imperative-logic fences the skill still carries as
bash after the b644d5a9 bin/lib migration: the Branch-0 first-run setup gate
(target resolution + `.percolate-ignore` existence check — the per-target
hook-dir existence loop was removed 2026-07-24 as vestigial once the
percolate engine went declarative, see docs/plans/2026-07-24-extirpate-
orphaned-claude-central-publish-shell.md), the Step 2c three-tier
content-leakage scan (HIGH/MEDIUM/LOW regex tiers over the about-to-publish
file set, plus the peer-repo-name extension), and the Step 2d inverse-drift
anchor resolution (lastsync marker vs 30-day fallback) and its scoped
`git log` commit listing. The pre-ci guard (formerly Step 5a's
shell-hook-script execution loop) now runs declaratively inside the engine
— `publish.py`'s `dispatch_percolate_pre_ci` — with no separate hook-script
execution step; this module carries no pre-ci subcommand. Everything the
skill still names a "thin single-CLI-invocation fence" (the
`_cc_trusted`/`_cc_root` guard preamble, the `resolve-claude-klabauter-bin` resolver,
`publish.py`/`load_targets` invocations themselves) is deliberately NOT
ported here — those are D1/D2's concern, not this chunk's.

Subcommands:
  branch0-gate <target> --percolate-root <path> --claude-klabauter-root <path>
      Resolve the target row via percolate.targets.load_targets and confirm
      `<source_dir>/.percolate-ignore` exists. Prints `CONFIGURED:<source_dir>`
      and exits 0 when every check passes; on any failure prints one reason
      line per failure (`MISSING_TARGETS` / `MISSING_TARGET_ENTRY` /
      `MISSING_IGNORE`) and exits 1. Does NOT check for per-target hook
      subdirectories under `percolate-hooks/<target>/` — those are vestigial
      now that the percolate engine consumes the declarative
      `percolate-store.yaml` instead, and the pre-ci guard runs declaratively
      inside `publish.py` rather than via a shell hook-script loop.

  scan-secrets --files <file-list-path> [--identity-file <path>]
               [--peer-repos-file <repo-registry.md path>] [--target <name>]
      Run the three severity-tier grep-style scan (HIGH credential shapes,
      MEDIUM identity/internal-path/peer-repo shapes, LOW informational)
      over the newline-delimited absolute file paths in <file-list-path>.
      Renders the Step 2c panel to stdout. Exits 2 if any HIGH hit fired
      (publish-blocking contract — mirrors the skill's "HIGH >=1: abort"
      rule), else 0.

  inverse-drift <target> --percolate-root <path> --dest <dest-path>
                --files <file-list-path>
      Resolve the lastsync-marker-vs-30-day-fallback anchor, then run a
      `git log` in <dest> scoped to the (dest-relative) paths in
      <file-list-path> since that anchor. Renders the Step 2d panel.
      Prints `anchor_mode: marker|30day-fallback|marker-stale` on its own
      line first.

  list-targets --percolate-root <path> [--target <name>]
      Step 1 / Step 5. Resolves the registered target set via
      percolate.targets.load_targets (the same library publish.py itself
      calls). With no --target: prints every resolved target's name, one per
      line, in load_targets' own resolution order (PRIMARY, then SUPPLEMENT,
      then LEGACY fallback -- load_targets already dedupes by name, an
      earlier tier's row always winning, so no re-dedup is needed here).
      With --target <name>: resolves that one target's row and prints ONLY
      its absolute dest path (match-and-exit pattern -- exits 1 with no
      stdout if the target isn't found among the resolved rows). On a
      TargetsError (malformed row, unresolvable required target, no targets
      found anywhere), prints the error's message to stderr and exits 1.

  coverage-drift <source_dir> [--limit N]
      Step 2a. Portable Python replacement for the skill's `find
      "<source_dir>" -type f -newer "<source_dir>/.percolate-ignore" | head
      -20` pipe (GNU/BSD `find -newer` is directionally portable but head
      count and quoting are still shell narration). Lists files under
      <source_dir> whose mtime is strictly newer than
      `<source_dir>/.percolate-ignore`'s mtime, one absolute path per line,
      capped at --limit (default 20, matching the skill's `head -20`). If
      `.percolate-ignore` is missing, prints nothing and exits 0 (coverage-
      drift is silent until the file exists, per the skill's own note).

  ignore-mtime <source_dir>
      Step 2a "last reviewed" date. Portable Python replacement for `date -r
      "<source_dir>/.percolate-ignore" '+%Y-%m-%d'`. Prints the ignore
      file's mtime as `YYYY-MM-DD` and exits 0. Exits 1 with no stdout if
      `.percolate-ignore` doesn't exist (nothing to date).

  crlf-diff <dest_file> <source_file>
      Step 2d CRLF-only false-positive dismissal. Portable Python
      replacement for `diff --strip-trailing-cr <dest-file>
      <source-file>` — compares the two files line-by-line with trailing
      `\\r` stripped from each line before comparison (so a CRLF-vs-LF-only
      difference reads as identical, matching GNU diff's
      `--strip-trailing-cr` semantics). Exits 0 with no stdout when the
      stripped content is identical (the skill's "empty = no content
      change" signal — dismiss as CRLF-only, not real drift). Exits 1 and
      prints a unified diff of the stripped content when it differs (real
      drift signal). Exits 1 with a one-line stderr message if either path
      is missing or unreadable.

Negative-spec: this module does NOT invoke publish.py, does NOT resolve
$_cc_claude_klabauter/$_cc_trusted itself (both are caller/D2 concerns), and does NOT
mutate .percolate-ignore, publish-targets.portable, or any percolated
source/dest content — read-only gate logic only. It also does NOT execute
pre-ci shell hooks (the former `run-pre-ci-hooks` subcommand, removed
2026-07-24 once the declarative engine-side pre-ci guard reached parity —
see docs/plans/2026-07-24-extirpate-orphaned-claude-central-publish-shell.md).
It also does NOT resolve a python3/python interpreter for the skill's Step
2c/Step 5a CI-smoke invocations — that hand-rolled interpreter-discovery
prose routes through the existing resolve-python seam, not this module
(C4's L151/L274 concern, out of scope for this port).

Spec backlink: coordinator/skills/percolate/SKILL.md (DoE-claude) — Branch 0,
Step 2a, Step 2c, Step 2d. Port chunk: M3 C-PERCOLATE, W1.7/C4.
"""
from __future__ import annotations

import argparse
import difflib
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

_BIN_DIR = Path(__file__).resolve().parent
_LIB_DIR = _BIN_DIR.parent / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))


# ---------------------------------------------------------------------------
# Branch 0 — first-run setup gate
# ---------------------------------------------------------------------------

def _cmd_branch0_gate(args: argparse.Namespace) -> int:
    from percolate.targets import TargetsError, load_targets  # noqa: E402

    setup_dir = Path(args.percolate_root) / "setup"
    target = args.target
    reasons: List[str] = []
    source_dir: Optional[Path] = None

    try:
        rows = load_targets(setup_dir, target_filter=target)
    except TargetsError:
        reasons.append("MISSING_TARGETS")
    else:
        match = next(
            (row.split("|") for row in rows if row.split("|", 1)[0] == target), None
        )
        if match is None:
            reasons.append("MISSING_TARGET_ENTRY")
        else:
            source_dir = Path(match[2])
            if not (source_dir / ".percolate-ignore").is_file():
                reasons.append("MISSING_IGNORE")

    if reasons:
        for reason in reasons:
            print(reason)
        return 1

    print(f"CONFIGURED:{source_dir}")
    return 0


# ---------------------------------------------------------------------------
# Step 2c — content-leakage scan
# ---------------------------------------------------------------------------

# Tier HIGH — credential / secret shapes. Any hit blocks the publish.
_TIER_HIGH = re.compile(
    r"(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}|"
    r"AKIA[A-Z0-9]{16}|xox[bpars]-[A-Za-z0-9-]{10,}|ya29\.[A-Za-z0-9_-]{20,}|"
    r"-----BEGIN [A-Z ]+PRIVATE KEY-----)"
)

# Tier MEDIUM — generic identity/internal-path shapes (no operator-specific
# literals — see the skill's Step 2c note on why macOS/BSD grep -E's lack of
# \b support keeps this tier separate from publish.py's PERSONAL_REVIEW_PATTERNS
# audit; Python's `re` supports \b natively so that constraint does not carry
# over to this port, but the pattern SET is kept identical for parity).
_TIER_MEDIUM = re.compile(
    r"(~/\.claude/(tasks|projects|memory|plans)/|/x/[a-z-]+|[XxCc]:/[a-z-]+|"
    r"@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b)"
)

# Tier LOW — informational only (40-char hex commit SHAs, doctrine language).
_TIER_LOW = re.compile(r"(\b[0-9a-f]{40}\b|First Officer Doctrine)")


def _scan_file(path: Path, pattern: re.Pattern) -> List[Tuple[Path, int, str]]:
    hits: List[Tuple[Path, int, str]] = []
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as fh:
            for lineno, line in enumerate(fh, start=1):
                if pattern.search(line):
                    hits.append((path, lineno, line.rstrip("\n")))
    except OSError:
        pass
    return hits


def _redact_high(line: str) -> str:
    """Redact any HIGH-tier secret token to its first 4 chars + ellipsis,
    per the skill's panel-rendering contract."""

    def _sub(match: "re.Match[str]") -> str:
        token = match.group(0)
        return token[:4] + "..."

    return _TIER_HIGH.sub(_sub, line)


def _load_file_list(files_path: Path) -> List[Path]:
    if not files_path.is_file():
        return []
    lines = files_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    return [Path(line) for line in lines if line.strip()]


def _peer_repo_pattern(peer_repos_file: Optional[Path], target: str) -> Optional[re.Pattern]:
    if peer_repos_file is None or not peer_repos_file.is_file():
        return None
    text = peer_repos_file.read_text(encoding="utf-8", errors="ignore")
    names = re.findall(r"^- shortname:\s*(\S+)", text, re.M)
    names = [n for n in names if n != target]
    if not names:
        return None
    alternation = "|".join(re.escape(n) for n in names)
    return re.compile(rf"\b({alternation})\b")


def _cmd_scan_secrets(args: argparse.Namespace) -> int:
    files = _load_file_list(Path(args.files))

    high_hits: List[Tuple[Path, int, str]] = []
    medium_hits: List[Tuple[Path, int, str]] = []
    low_hits: List[Tuple[Path, int, str]] = []

    medium_pattern = _TIER_MEDIUM
    peer_pattern = _peer_repo_pattern(
        Path(args.peer_repos_file) if args.peer_repos_file else None, args.target or ""
    )

    for path in files:
        high_hits.extend(_scan_file(path, _TIER_HIGH))
        medium_hits.extend(_scan_file(path, medium_pattern))
        if peer_pattern is not None:
            medium_hits.extend(_scan_file(path, peer_pattern))
        low_hits.extend(_scan_file(path, _TIER_LOW))

    identity_file = Path(args.identity_file) if args.identity_file else None
    if identity_file is not None and not identity_file.is_file():
        print(
            "  NOTE: setup/.percolate-identity not found — machine-slug detection"
        )
        print(
            "        (PERSONAL_REVIEW_PATTERNS in publish.py Phase-4) is UNCONFIGURED."
        )
        print(
            "        Copy setup/.percolate-identity.example -> .percolate-identity and"
        )
        print("        populate PERSONAL_REVIEW_PATTERNS with your machine codenames.")
        print(
            "        This Step 2c scan covers generic shapes only; operator-specific"
        )
        print("        tokens are NOT scanned until .percolate-identity is in place.")
    elif identity_file is not None:
        try:
            from percolate.phase4_audit import parse_percolate_identity  # noqa: E402

            identity = parse_percolate_identity(identity_file)
            if not identity.review:
                print(
                    "  NOTE: setup/.percolate-identity exists but PERSONAL_REVIEW_PATTERNS is"
                )
                print(
                    "        empty — machine-slug detection is effectively unconfigured."
                )
                print("        Populate PERSONAL_REVIEW_PATTERNS with your machine codenames.")
        except Exception:
            pass

    print("Content-leakage scan:")
    print("  HIGH (credential/secret shapes -- BLOCKS publish):")
    if high_hits:
        for path, lineno, line in high_hits:
            print(f"    {path}:{lineno}: {_redact_high(line)}")
    else:
        print("    (none)")

    print("  MEDIUM (identity / internal paths / peer-repo names -- surfaces to gate):")
    if medium_hits:
        for path, lineno, line in medium_hits:
            print(f"    {path}:{lineno}: {line}")
    else:
        print("    (none)")

    print("  LOW (informational -- commit SHAs, doctrine language):")
    if low_hits:
        files_touched = len({p for p, _, _ in low_hits})
        print(f"    {len(low_hits)} hits across {files_touched} files")
    else:
        print("    (none)")

    return 2 if high_hits else 0


# ---------------------------------------------------------------------------
# Step 2d — inverse-drift detection
# ---------------------------------------------------------------------------

def _cmd_inverse_drift(args: argparse.Namespace) -> int:
    target = args.target
    percolate_root = Path(args.percolate_root)
    dest = Path(args.dest)
    files = _load_file_list(Path(args.files))

    marker = percolate_root / "setup" / "percolate-state" / f"{target}.lastsync"
    since_ref: Optional[str] = None
    anchor_mode = "30day-fallback"
    if marker.is_file():
        since_ref = marker.read_text(encoding="utf-8").strip()
        anchor_mode = "marker"

    rel_paths: List[str] = []
    for path in files:
        try:
            rel_paths.append(str(path.relative_to(dest)))
        except ValueError:
            rel_paths.append(str(path))

    log_cmd_base = ["git", "-C", str(dest), "log", "--no-merges", "--format=%h %ad %s", "--date=short"]

    if anchor_mode == "marker":
        verify = subprocess.run(
            ["git", "-C", str(dest), "rev-parse", "--verify", since_ref],
            capture_output=True,
            text=True,
        )
        if verify.returncode != 0:
            anchor_mode = "marker-stale"

    if anchor_mode == "marker":
        cmd = log_cmd_base + [f"{since_ref}..HEAD", "--"] + rel_paths
    else:
        cmd = log_cmd_base + ["--since=30 days ago", "--"] + rel_paths

    result = subprocess.run(cmd, capture_output=True, text=True)
    log_lines = [line for line in result.stdout.splitlines() if line.strip()]

    print(f"anchor_mode: {anchor_mode}")

    if not log_lines:
        return 0

    anchor_desc = {
        "marker": since_ref or "",
        "30day-fallback": "30-day fallback (no marker)",
        "marker-stale": "marker-stale (SHA not in dest history)",
    }[anchor_mode]

    print("Inverse drift -- dest commits touching files about to be overwritten:")
    print(f"  anchor: {anchor_desc}")
    for line in log_lines:
        print(f"  {line}")
    print(
        "  -> Read each commit's diff before proceeding. If it's a real fix, "
        "back-port to source FIRST,"
    )
    print("    then re-run /percolate. Confirming below will OVERWRITE these changes.")
    return 0


# ---------------------------------------------------------------------------
# Step 2a — coverage-drift detection + last-reviewed date
# ---------------------------------------------------------------------------

def _cmd_coverage_drift(args: argparse.Namespace) -> int:
    source_dir = Path(args.source_dir)
    ignore_file = source_dir / ".percolate-ignore"
    if not ignore_file.is_file():
        return 0

    anchor_mtime = ignore_file.stat().st_mtime
    hits: List[Path] = []
    for path in sorted(source_dir.rglob("*")):
        if not path.is_file():
            continue
        try:
            if path.stat().st_mtime > anchor_mtime:
                hits.append(path)
        except OSError:
            continue
        if len(hits) >= args.limit:
            break

    for path in hits:
        print(path)
    return 0


def _cmd_ignore_mtime(args: argparse.Namespace) -> int:
    ignore_file = Path(args.source_dir) / ".percolate-ignore"
    if not ignore_file.is_file():
        return 1

    mtime = datetime.fromtimestamp(ignore_file.stat().st_mtime, tz=timezone.utc)
    print(mtime.strftime("%Y-%m-%d"))
    return 0


# ---------------------------------------------------------------------------
# Step 2d — CRLF-only false-positive dismissal
# ---------------------------------------------------------------------------

def _strip_cr_lines(path: Path) -> List[str]:
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as fh:
        return [line.rstrip("\r\n") for line in fh]


def _cmd_crlf_diff(args: argparse.Namespace) -> int:
    dest_file = Path(args.dest_file)
    source_file = Path(args.source_file)

    for label, path in (("dest", dest_file), ("source", source_file)):
        if not path.is_file():
            print(f"crlf-diff: {label} file not found: {path}", file=sys.stderr)
            return 1

    try:
        dest_lines = _strip_cr_lines(dest_file)
        source_lines = _strip_cr_lines(source_file)
    except OSError as exc:
        print(f"crlf-diff: {exc}", file=sys.stderr)
        return 1

    if dest_lines == source_lines:
        return 0

    diff = difflib.unified_diff(
        dest_lines,
        source_lines,
        fromfile=str(dest_file),
        tofile=str(source_file),
        lineterm="",
    )
    for line in diff:
        print(line)
    return 1


# ---------------------------------------------------------------------------
# Step 1 / Step 5 — list-targets
# ---------------------------------------------------------------------------

def _cmd_list_targets(args: argparse.Namespace) -> int:
    from percolate.targets import TargetsError, load_targets  # noqa: E402

    setup_dir = Path(args.percolate_root) / "setup"
    try:
        rows = load_targets(setup_dir, target_filter=args.target)
    except TargetsError as exc:
        print(exc.message, file=sys.stderr)
        return 1

    if args.target:
        match = next(
            (row.split("|") for row in rows if row.split("|", 1)[0] == args.target),
            None,
        )
        if match is None:
            return 1
        print(match[3])
        return 0

    for row in rows:
        print(row.split("|", 1)[0])
    return 0


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="percolate-gate")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_branch0 = sub.add_parser("branch0-gate")
    p_branch0.add_argument("target")
    p_branch0.add_argument("--percolate-root", required=True)
    p_branch0.add_argument("--claude-klabauter-root", required=False)
    p_branch0.set_defaults(func=_cmd_branch0_gate)

    p_scan = sub.add_parser("scan-secrets")
    p_scan.add_argument("--files", required=True)
    p_scan.add_argument("--identity-file", required=False)
    p_scan.add_argument("--peer-repos-file", required=False)
    p_scan.add_argument("--target", required=False)
    p_scan.set_defaults(func=_cmd_scan_secrets)

    p_drift = sub.add_parser("inverse-drift")
    p_drift.add_argument("target")
    p_drift.add_argument("--percolate-root", required=True)
    p_drift.add_argument("--dest", required=True)
    p_drift.add_argument("--files", required=True)
    p_drift.set_defaults(func=_cmd_inverse_drift)

    p_list = sub.add_parser("list-targets")
    p_list.add_argument("--percolate-root", required=True)
    p_list.add_argument("--target", required=False)
    p_list.set_defaults(func=_cmd_list_targets)

    p_coverage = sub.add_parser("coverage-drift")
    p_coverage.add_argument("source_dir")
    p_coverage.add_argument("--limit", type=int, default=20)
    p_coverage.set_defaults(func=_cmd_coverage_drift)

    p_mtime = sub.add_parser("ignore-mtime")
    p_mtime.add_argument("source_dir")
    p_mtime.set_defaults(func=_cmd_ignore_mtime)

    p_crlf = sub.add_parser("crlf-diff")
    p_crlf.add_argument("dest_file")
    p_crlf.add_argument("source_file")
    p_crlf.set_defaults(func=_cmd_crlf_diff)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
