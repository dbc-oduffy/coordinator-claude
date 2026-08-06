#!/usr/bin/env python3
# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""merge-release-notes-derive.py -- native port of the /merging-to-main Step 5.5
pending-release reconcile sweep + release-tag attribution walk.

Purpose: DoE-claude's coordinator/skills/merging-to-main/SKILL.md Step 5.5
("Post-Merge Completion-Log Status Flip") previously embedded two blocks of
genuine imperative logic directly as bash-fenced content -- a reconcile
sweep loop and a 125-line heredoc-fed `python3 -` script that walks git tag
history to attribute completion-log entries to the earliest release tag that
actually contains their commits. Per the "a skill must LINK to an entrypoint,
not carry a command payload for the EM to transcribe" ruling
(DoE-claude/CLAUDE.local.md, 2026-07-22), that logic is lifted here as a
real, testable, self-contained naked-Python CLI. The skill-side repoint
(replacing both fenced blocks with a call to this CLI) is a separate wave
(D2) and is NOT done by this port -- this file only has to exist and be
callable with an equivalent contract.

Subcommands:
  reconcile-sweep
      Detect-only sweep over every completion-log entry with
      `status=pending-release` (queried via the sibling `query-completions.py
      --where "status=pending-release" --format paths` CLI). For each entry
      with a non-empty/non-null `authored_by:` frontmatter field, invokes the
      sibling `reconcile-completion-commits.py --session-id <authored_by>
      <entry>` CLI (detect-only -- no `--append`) and parses its
      `delta=<N>` stdout line. Entries with delta > 0 print an advisory
      warning line to stdout. Never mutates anything -- pure detection,
      mirroring the bash oracle's "DETECT-ONLY — do NOT pass --append"
      comment verbatim.

  flip-tags <release_tag_cut> <merge_sha> <merge_date> <entry_path>...
      Per-entry version resolution (NOT blanket-latest): for each entry path
      whose frontmatter `status:` is exactly `pending-release`, resolves the
      EARLIEST `${tag_prefix}v*` tag (same prefix family as release_tag_cut)
      whose commit history is an ancestor of every commit listed in the
      entry's `commits:` frontmatter block (via `git merge-base
      --is-ancestor`). Entries with no recorded commits, or none of whose
      commits are yet reachable from any existing tag (this release's own
      work), fall through to release_tag_cut/merge_sha/merge_date. Rewrites
      each entry's frontmatter in place with `status: released`,
      `released_in:`, `released_at:`, `released_sha:`, then prints one
      "<path>: released_in=<tag>" line per flipped entry (or "no
      pending-release entries to flip" when none matched). This is the exact
      logic that used to live in the SKILL.md heredoc -- see the git history
      of coordinator/skills/merging-to-main/SKILL.md in DoE-claude for the
      pre-port original.

Both subcommands are self-resolving (no cwd dependence beyond the git
commands themselves, which operate against whatever repo the caller's cwd
is inside -- same contract the bash oracle had) and idempotent: re-running
reconcile-sweep is pure detection (no state change), and re-running
flip-tags on an already-`released` entry is a silent no-op (the
`status != "pending-release"` guard skips it).

Spec backlink: DoE-claude coordinator/skills/merging-to-main/SKILL.md
  Step 5.5 items 2-3 (pre-port).
Spec backlink: cross-repo/archive/2026-07-13-project-rag-ue-addon-em-completion-log-flip-skipped-on-consolidation-release.md

Negative-spec:
  - Does NOT resolve _mkb_bin / resolve-claude-klabauter-bin itself -- that resolver
    ladder is D1/D2's concern (the skill-side repoint), not this CLI's. This
    CLI assumes it is invoked from its own coordinator/bin/ directory (or via
    an already-resolved absolute path) and locates its sibling CLIs
    (query-completions.py, reconcile-completion-commits.py) by
    Path(__file__).parent, not by re-deriving _mkb_bin.
  - Does NOT parse YAML with a YAML library -- the frontmatter reader/writer
    here is a line-oriented `---`-delimited scan, exactly mirroring the
    heredoc original (ported verbatim, not reimplemented against a schema).
  - Does NOT stage or commit anything. The caller (the skill step) owns
    `git add`/`git commit`/`git push` after this CLI returns.
  - Does NOT hardcode `git` invocation via a shell string -- every git call
    is `subprocess.run([...])` with an argv list.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

_BIN_DIR = Path(__file__).resolve().parent

# Windows: suppresses the console popup a subprocess.run(...) would otherwise
# trigger under the headless Claude Code Bash-tool parent. No-op (0) elsewhere.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _git(*args: str, cwd: Optional[str] = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        creationflags=_NO_WINDOW,
    )


# ---------------------------------------------------------------------------
# reconcile-sweep
# ---------------------------------------------------------------------------


def _run_sibling_cli(name: str, args: List[str]) -> subprocess.CompletedProcess:
    """Invoke a sibling coordinator/bin/ CLI by absolute path (self-resolving,
    matches the "self-contained, self-resolving (Path(__file__)-relative)"
    CLI contract -- never depends on cwd or PATH)."""
    script = _BIN_DIR / name
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        creationflags=_NO_WINDOW,
    )


def _frontmatter_field(text: str, key: str) -> Optional[str]:
    n = 0
    val: Optional[str] = None
    for line in text.splitlines():
        if line == "---":
            n += 1
            if n == 2:
                break
            continue
        if n == 1 and line.startswith(f"{key}:"):
            val = line[len(key) + 1:].strip()
    return val


_DELTA_RE = re.compile(r"delta=(\d+)")


def cmd_reconcile_sweep(_args: argparse.Namespace) -> int:
    """Detect-only sweep -- mirrors SKILL.md Step 5.5 item 2 verbatim (never
    passes --append; unconditional repo-wide sweep, not session-scoped)."""
    query = _run_sibling_cli(
        "query-completions.py",
        ["--where", "status=pending-release", "--format", "paths"],
    )
    entry_paths = [p for p in query.stdout.splitlines() if p.strip()]

    for entry in entry_paths:
        try:
            with open(entry, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        authored_by = _frontmatter_field(text, "authored_by")
        if not authored_by or authored_by == "null":
            continue
        result = _run_sibling_cli(
            "reconcile-completion-commits.py",
            ["--session-id", authored_by, entry],
        )
        match = _DELTA_RE.search(result.stdout)
        delta = int(match.group(1)) if match else 0
        if delta > 0:
            basename = os.path.basename(entry)
            print(
                f"⚠ entry {basename}: {delta} session commit(s) unaccounted "
                "— reconcile before release"
            )
    return 0


# ---------------------------------------------------------------------------
# flip-tags
# ---------------------------------------------------------------------------


def _tag_sha(tag: str) -> Optional[str]:
    r = _git("rev-list", "-n", "1", tag)
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None


def _tag_date(tag: str, sha: Optional[str], merge_date: str) -> str:
    r = _git("log", "-1", "--format=%ad", "--date=short", sha or tag)
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else merge_date


def _contains_all(tag: str, commits: List[str]) -> bool:
    return all(
        _git("merge-base", "--is-ancestor", c, tag).returncode == 0 for c in commits
    )


def _parse_commits(text: str) -> List[str]:
    n = 0
    in_block = False
    commits: List[str] = []
    for line in text.splitlines():
        if line == "---":
            n += 1
            if n == 2:
                break
            continue
        if n != 1:
            continue
        if line.startswith("commits:"):
            in_block = True
            continue
        if in_block:
            entry = re.match(r"^\s*-\s*(\S+)", line)
            if entry:
                commits.append(entry.group(1))
                continue
            in_block = False
    return commits


def _resolve_tag_prefix(release_tag_cut: str) -> str:
    m = re.match(r"^(.*?)v\d+\.\d+\.\d+$", release_tag_cut)
    return m.group(1) if m else ""


def _flip_entry(
    path: str,
    tags: List[str],
    release_tag_cut: str,
    merge_sha: str,
    merge_date: str,
) -> Optional[str]:
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if _frontmatter_field(text, "status") != "pending-release":
        return None

    commits = _parse_commits(text)
    resolved_tag: Optional[str] = None
    for tag in tags:
        if commits and _contains_all(tag, commits):
            resolved_tag = tag
            break
    if resolved_tag is None:
        resolved_tag, sha, date = release_tag_cut, merge_sha, merge_date
    else:
        sha = _tag_sha(resolved_tag) or merge_sha
        date = _tag_date(resolved_tag, sha, merge_date)

    fields = {
        "status": "released",
        "released_in": resolved_tag,
        "released_at": date,
        "released_sha": sha,
    }
    out: List[str] = []
    n = 0
    seen: set = set()
    for line in text.splitlines(keepends=True):
        stripped = line.rstrip("\n")
        if stripped == "---":
            n += 1
            if n == 2:
                for key, val in fields.items():
                    if key not in seen:
                        out.append(f"{key}: {val}\n")
            out.append(line)
            continue
        if n == 1:
            key = stripped.split(":", 1)[0]
            if key in fields:
                out.append(f"{key}: {fields[key]}\n")
                seen.add(key)
                continue
        out.append(line)

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(out)
    return f"{path}: released_in={resolved_tag}"


def cmd_flip_tags(args: argparse.Namespace) -> int:
    release_tag_cut = args.release_tag_cut
    merge_sha = args.merge_sha
    merge_date = args.merge_date
    entry_paths = args.entry_paths

    tag_prefix = _resolve_tag_prefix(release_tag_cut)
    tags_result = _git("tag", "--list", f"{tag_prefix}v*", "--sort=creatordate")
    tags = [t for t in tags_result.stdout.splitlines() if t]
    if release_tag_cut not in tags:
        tags.append(release_tag_cut)

    flipped = []
    for path in entry_paths:
        result = _flip_entry(path, tags, release_tag_cut, merge_sha, merge_date)
        if result is not None:
            flipped.append(result)

    print("\n".join(flipped) if flipped else "no pending-release entries to flip")
    return 0


# ---------------------------------------------------------------------------
# CLI plumbing
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="merge-release-notes-derive",
        description=(
            "Pending-release reconcile sweep + tag-history release-note "
            "attribution walk, ported from /merging-to-main Step 5.5."
        ),
    )
    sub = p.add_subparsers(dest="subcommand", required=True)

    sub.add_parser(
        "reconcile-sweep",
        help=(
            "Detect-only sweep over pending-release entries, warning on "
            "unaccounted session commits (never mutates)."
        ),
    )

    flip = sub.add_parser(
        "flip-tags",
        help=(
            "Flip every pending-release entry to released, attributed to "
            "the earliest containing release tag."
        ),
    )
    flip.add_argument("release_tag_cut", help="This merge's cut tag (e.g. v1.2.3).")
    flip.add_argument("merge_sha", help="SHA of the merge commit on main.")
    flip.add_argument("merge_date", help="YYYY-MM-DD date of the merge.")
    flip.add_argument(
        "entry_paths",
        nargs="+",
        help="Completion-log entry file paths to consider.",
    )

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.subcommand == "reconcile-sweep":
        return cmd_reconcile_sweep(args)
    if args.subcommand == "flip-tags":
        return cmd_flip_tags(args)
    parser.print_usage(sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
