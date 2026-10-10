"""Re-verify the open side of the structured queues against what the entries themselves record.

Filing a queue entry has ceremony; retiring one has none. The consequence is measurable and this
is the instrument that measures it: entries whose author already stamped a terminal status sit
on the open side indefinitely because the `git mv` that completes closure is a thing a human has
to remember. Downstream, `status: open` is read as "this defect is live" by every skill, census
and agent that touches the queue.

Two modes, and the split between them is the whole design:

  report (default) -- classify every open-side entry and print/emit the partition. Read-only.
  --apply-archivable -- move ONLY the entries whose own status is already terminal into
      archive/<queue>/<YYYY-MM>/, normalizing an off-schema terminal spelling to the schema
      value and recording what was there before.

Negative-spec: --apply-archivable never touches an entry that still claims to be live. There is
no flag that closes an open entry, and adding one would be the defect, not the feature -- an open
entry's disposition needs a reader who checked the claim against the tree, and this program
cannot do that. The other classes are emitted as candidate sets for exactly that reader.

Moves use os.replace plus an explicit pathspec handed back to the caller, never a git subprocess
per entry: at fleet scale that is thousands of process creations, and a sweep nobody can afford
to run is indistinguishable from the missing mechanism it was built to replace.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import functools
import json
import os
import re
import subprocess
import sys
from pathlib import Path

_BIN_LIB_DIR = Path(__file__).resolve().parent / "lib"


def _qc():
    """`queue_closure`, imported on first use so a bare import of this module
    leaves `sys.path` untouched."""
    if str(_BIN_LIB_DIR) not in sys.path:
        sys.path.insert(0, str(_BIN_LIB_DIR))
    import queue_closure

    return queue_closure

ARCHIVAL_NOTE_FIELD = "archival_note"


def read_fixes_row_claims(repo_root: str, since) -> dict:
    """One bounded `git log` -> `{stem: [(sha, committer-date), ...]}`.

    `--grep` only narrows the walk; membership is decided by git's own `%(trailers)` parse of the
    final trailer block, so a `Fixes-Row:` line elsewhere in the body claims nothing. A failure
    yields no claims and one stderr line: claims are a bonus signal, never a gate on the sweep.
    """
    argv = ["git", "-C", repo_root, "log"]
    if since:
        argv.append(f"--since={since}")
    argv += [
        "-E", "--grep=^Fixes-Row:",
        "--format=%x1e%H%x09%cs%n%(trailers:key=Fixes-Row,valueonly)", "HEAD",
    ]
    try:
        proc = subprocess.run(
            argv, capture_output=True, check=False, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"skip: {repo_root} claims unread -- {exc}", file=sys.stderr)
        return {}
    if proc.returncode != 0:
        print(f"skip: {repo_root} claims unread -- git log exited {proc.returncode}",
              file=sys.stderr)
        return {}
    claims: dict = {}
    for record in proc.stdout.decode("utf-8", errors="replace").split("\x1e"):
        lines = record.splitlines()
        if not lines or "\t" not in lines[0]:
            continue
        sha, date = lines[0].split("\t", 1)
        for stem in {ln.strip() for ln in lines[1:] if ln.strip()}:
            claims.setdefault(stem, []).append((sha.strip(), date.strip()))
    return claims


def build_note(original_status: str, normalized: str, today: str) -> str:
    bits = [
        f"Archived {today} by queue-closure-sweep. The entry was already stamped "
        f"`status: {original_status}` on the open side -- its author declared the work over and "
        f"the move to archive/ never happened."
    ]
    if normalized != original_status:
        bits.append(
            f"`{original_status}` is off-schema; normalized to `{normalized}` on archival, with "
            f"the original recorded here because erasing it would destroy the only evidence of "
            f"how the spelling drifted."
        )
    bits.append(
        "No claim is made that the underlying defect was verified fixed -- this archival rests "
        "on the recorded status alone."
    )
    return " ".join(bits)


def apply_archivable(repo_root: str, entries: list, today: str) -> list:
    """Move terminal-stamped entries into archive/. Returns repo-relative paths touched."""
    touched: list = []
    for e in entries:
        if e.klass != _qc().ARCHIVABLE:
            continue
        src = os.path.join(repo_root, e.path)
        if not os.path.exists(src):
            continue
        month = (e.created[:7] if re.fullmatch(r"\d{4}-\d{2}-\d{2}", e.created or "") else today[:7])
        rel_dst = f"archive/{e.queue}/{month}/{os.path.basename(e.path)}"
        dst = os.path.join(repo_root, rel_dst)
        if os.path.exists(dst):
            # A silent skip reads identically to a successful archive to anyone reading
            # only the "archived N entries" count.
            print(
                f"skip: {e.path} not archived -- destination {rel_dst} already exists",
                file=sys.stderr,
            )
            continue
        text = Path(src).read_text(encoding="utf-8")
        # e.status is lowercased by classify_repo while the disk text may read `status: Fixed`.
        # A case-sensitive match no-ops the rewrite silently, leaving an off-schema entry in
        # archive/ under an archival_note claiming it was normalized.
        normalized = _qc().STATUS_NORMALIZATION.get(e.status, e.status)
        if normalized != e.status:
            text = re.sub(
                r"^status:\s*[\"']?%s[\"']?\s*$" % re.escape(e.status),
                f"status: {normalized}", text, count=1, flags=re.M | re.I,
            )
        if not re.search(r"^%s:" % ARCHIVAL_NOTE_FIELD, text, re.M):
            note = build_note(e.status, normalized, today).replace('"', "'")
            if not text.endswith("\n"):
                text += "\n"
            text += f'{ARCHIVAL_NOTE_FIELD}: "{note}"\n'
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        Path(dst).write_text(text, encoding="utf-8")
        if Path(dst).read_text(encoding="utf-8") != text:
            print(f"skip: {e.path} not archived -- {rel_dst} failed read-back verification",
                  file=sys.stderr)
            continue
        os.remove(src)
        touched.extend([e.path, rel_dst])
    return touched


def write_output(path: str, content: str) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")


def render_report(all_entries: list, today: str) -> str:
    by_repo: dict = collections.OrderedDict()
    for e in all_entries:
        by_repo.setdefault(e.repo, collections.Counter())[e.klass] += 1
    totals = collections.Counter(e.klass for e in all_entries)

    lines = [
        f"# Queue closure sweep -- {today}",
        "",
        f"{len(all_entries)} entries on the open side of "
        f"{len(by_repo)} repos' `state/{{{','.join(_qc().QUEUES)}}}/`.",
        "",
        "| repo | " + " | ".join(_qc().CLASSES) + " | total |",
        "|---|" + "---|" * (len(_qc().CLASSES) + 1),
    ]
    for repo, counts in by_repo.items():
        row = " | ".join(str(counts.get(c, 0)) for c in _qc().CLASSES)
        lines.append(f"| {repo} | {row} | {sum(counts.values())} |")
    lines.append(
        "| **fleet** | " + " | ".join(f"**{totals.get(c,0)}**" for c in _qc().CLASSES)
        + f" | **{len(all_entries)}** |"
    )
    lines += [
        "",
        "## What each class means",
        "",
    ]
    lines += [f"- **{c}** -- {_qc().CLASS_DESCRIPTIONS[c]}" for c in _qc().CLASSES]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo", action="append", default=[], metavar="PATH",
                    help="repo root to sweep; repeatable. Name is the directory basename.")
    ap.add_argument("--json", metavar="PATH", help="write the full per-entry partition here")
    ap.add_argument("--report", metavar="PATH", help="write the markdown report here")
    ap.add_argument("--apply-archivable", action="store_true",
                    help="move terminal-stamped entries into archive/ (never touches a live entry)")
    args = ap.parse_args(argv)

    if not args.repo:
        ap.error("at least one --repo is required")
    queues = _qc().QUEUES
    today = dt.date.today().isoformat()

    roots = []
    for root in args.repo:
        root = os.path.abspath(root)
        if not os.path.isdir(root):
            print(f"skip: {root} is not a directory", file=sys.stderr)
            continue
        roots.append((Path(root).name, root))

    all_entries: list = []
    touched_by_repo: dict = {}
    for name, root in roots:
        entries = _qc().classify_repo(root, name, queues=queues, sibling_roots=roots,
                                read_claims=functools.partial(read_fixes_row_claims, root))
        all_entries.extend(entries)
        if args.apply_archivable:
            touched = apply_archivable(root, entries, today)
            if touched:
                touched_by_repo[root] = touched

    report = render_report(all_entries, today)
    if args.report:
        write_output(args.report, report)
    else:
        sys.stdout.write(report)

    if args.json:
        payload = {
            "generated": today,
            "queues": list(queues),
            "counts": dict(collections.Counter(e.klass for e in all_entries)),
            "entries": [e.to_dict() for e in all_entries],
        }
        write_output(args.json, json.dumps(payload, indent=1))

    if args.apply_archivable:
        moved = sum(len(v) for v in touched_by_repo.values()) // 2
        print(f"\narchived {moved} terminal-stamped entries across "
              f"{len(touched_by_repo)} repo(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
