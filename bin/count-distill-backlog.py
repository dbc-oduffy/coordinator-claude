# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""count-distill-backlog.py — heuristic count of completion-log entries pending
wiki distillation.

Scans archive/completed entries older than
threshold_days and reports how many have not yet been absorbed into the wiki.
The count is approximate — chain:null entries cannot be matched by chain slug
and will always count as pending.

Usage:
    count-distill-backlog.py                # prints pending_count integer
    count-distill-backlog.py --format json  # prints single-line JSON object

Spec backlink: docs/plans/2026-06-22-cockpit-tc-3-coordinator-emission.md § C1
Spec backlink: docs/plans/2026-07-19-debash-coordinator-windows.md (Wave E3-c)

Negative-spec: does NOT spawn `date`/`awk`/`grep`/`jq` subprocesses — cutoff
date, frontmatter extraction, and JSON emission are all native Python
(this is a straight behavioral port, not merely a shell-out wrapper).
"""
from __future__ import annotations

import datetime
import glob
import json
import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from coordinator_registry import _DoeUnresolvable, doe_root  # noqa: E402

PROG = "count-distill-backlog.py"

THRESHOLD_DAYS = 30


def _resolve_root() -> str:
    """Resolve the archive/wiki scan root: the DoE-claude repo, whose
    `archive/completed` + `docs/wiki` (source layout) or the live-installed
    `~/.claude` + `plugins/coordinator/docs/wiki`
    (live-install layout) hold the completion-log corpus this script counts
    against — this is DoE doctrine's own distill backlog, not the calling
    repo's.

    An EXPLICIT CLAUDE_HOME env var always wins over registry resolution
    (test/sandbox override, matching the precedence resolve-repo-path.py
    already gives it). Two conventions for what CLAUDE_HOME points AT are
    tolerated (parent-of-.claude, matching the documented
    `${CLAUDE_HOME:-$HOME}/.claude` bash-oracle form; or the .claude
    directory itself) — tried in that order, first-match wins, falling back
    to the documented parent-of-.claude form when neither contains
    archive/completed (this ambiguity is inherent in the sole consumer of
    this override, the test suite's synthetic fixtures, not a behavior this
    port invents).

    Absent CLAUDE_HOME, resolves via `coordinator_registry.doe_root()`
    (DOE_ROOT / REPO_DOE_CLAUDE env -> machine-local `repos.doe_claude` ->
    raise).

    THIS DOES NOT DERIVE FROM __file__. b644d5a9 migrated this executable
    from DoE-claude into claude-klabauter's `coordinator/bin/`, while
    `archive/completed` and `docs/wiki` (the corpus this script counts)
    stayed in DoE-claude. Claude-klabauter ALSO has its own `archive/completed`
    — a distinct, unrelated completion log — so the retired hop-count
    resolution below (bin/ -> up N levels) would silently land on and count
    claude-klabauter's OWN backlog instead of DoE-claude's: wrong answer, zero
    errors, the nastiest failure shape. A future reader must not restore
    script-location inference to "fix" this — self-location is no longer a
    valid proxy for the DoE root once this script lives outside it, and
    restoring it is precisely the shape of the original bug.

    Fails loud (`sys.exit(1)`) when `doe_root()` cannot resolve — this is a
    reporting/gate script, not a never-block hook, so an unresolvable root
    must not silently degrade to counting the wrong repo's backlog.
    """
    claude_home_env = os.environ.get("CLAUDE_HOME")
    if claude_home_env:
        parent_form = os.path.join(claude_home_env, ".claude")
        if os.path.isdir(os.path.join(parent_form, "archive", "completed")):
            return parent_form
        if os.path.isdir(os.path.join(claude_home_env, "archive", "completed")):
            return claude_home_env
        return parent_form

    try:
        return doe_root()
    except _DoeUnresolvable as exc:
        print(
            f"{PROG}: cannot resolve the coordinator doctrine repo root ({exc}). "
            "Set repos.doe_claude in the machine-local registry, or set the "
            "DOE_ROOT/REPO_DOE_CLAUDE env var, or set CLAUDE_HOME directly.",
            file=sys.stderr,
        )
        sys.exit(1)


def _read_wiki_corpus(wiki_local: str, wiki_coord: str) -> str:
    """Concatenate every *.md file under both wiki roots into one corpus
    string. A missing/empty glob on either side contributes nothing — mirrors
    the bash oracle's `cat ... 2>/dev/null || true` degrade-to-empty.
    """
    parts: list[str] = []
    for root in (wiki_local, wiki_coord):
        for path in sorted(glob.glob(os.path.join(root, "*.md"))):
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    parts.append(fh.read())
            except OSError:
                continue
    return "\n".join(parts)


def _extract_frontmatter(path: str) -> tuple[str, str]:
    """Return (created, chain) from the first `created:`/`chain:` line found
    in the file, matching the bash oracle's one-pass-per-file awk semantics
    (FNR==1 style: first non-empty value per field per file wins). Empty
    string for either field when absent. Zero-byte files return ("", "").
    """
    created = ""
    chain = ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            content = fh.read()
    except OSError:
        return "", ""
    if not content:
        return "", ""
    for line in content.splitlines():
        if not created and line.startswith("created:"):
            fields = line.split()
            if len(fields) >= 2:
                created = fields[1]
        if not chain and line.startswith("chain:"):
            fields = line.split()
            if len(fields) >= 2:
                chain = fields[1]
    return created, chain


def _derive_slug(entry_path: str, chain: str) -> str:
    if chain and chain != "null":
        return chain
    base = os.path.basename(entry_path)
    if base.endswith(".md"):
        base = base[: -len(".md")]
    # strip trailing 6-char hex suffix (e.g. -a62b94)
    no_hash = base
    if len(base) > 7 and base[-7] == "-":
        suffix = base[-6:]
        if all(c in "0123456789abcdef" for c in suffix.lower()):
            no_hash = base[:-7]
    # strip leading YYYY-MM-DD- date prefix
    slug = no_hash
    if len(no_hash) > 11 and no_hash[4] == "-" and no_hash[7] == "-" and no_hash[10] == "-":
        date_part = no_hash[:10]
        if date_part[:4].isdigit() and date_part[5:7].isdigit() and date_part[8:10].isdigit():
            slug = no_hash[11:]
    return slug


def main(argv: list[str]) -> int:
    fmt_json = False
    if len(argv) >= 2 and argv[1] == "--format" and len(argv) >= 3 and argv[2] == "json":
        fmt_json = True
    elif len(argv) >= 2 and argv[1] == "--format=json":
        fmt_json = True

    root = _resolve_root()
    archive_root = os.path.join(root, "archive", "completed")
    wiki_local = os.path.join(root, "docs", "wiki")
    wiki_coord = os.path.join(root, "plugins", "coordinator-claude", "coordinator", "docs", "wiki")

    if not os.path.isdir(archive_root):
        print(f"ERROR: archive root not found: {archive_root}", file=sys.stderr)
        return 1

    wiki_corpus = _read_wiki_corpus(wiki_local, wiki_coord)

    cutoff = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=THRESHOLD_DAYS)
    ).strftime("%Y-%m-%d")

    md_files = sorted(glob.glob(os.path.join(archive_root, "*", "*.md")))

    total_entries = 0
    pending_count = 0
    archive_files_found = 0

    for entry in md_files:
        # A genuinely zero-byte file never triggers the bash oracle's awk
        # FNR==1 record — it produces no record at all and is excluded from
        # archive_files_found. Any non-zero-byte file (with or without
        # created:/chain: lines) DOES produce a record.
        try:
            if os.path.getsize(entry) == 0:
                continue
        except OSError:
            continue

        archive_files_found += 1

        created, chain = _extract_frontmatter(entry)

        if not created:
            continue  # no frontmatter — skip (legacy rollup files)

        if not (created < cutoff):
            continue

        total_entries += 1

        slug = _derive_slug(entry, chain)

        found = slug in wiki_corpus
        if not found:
            pending_count += 1

    if archive_files_found == 0:
        computed_state = "unknown"
    elif pending_count == 0:
        computed_state = "fresh"
    elif pending_count <= 5:
        computed_state = "mild"
    else:
        computed_state = "stale"

    if fmt_json:
        print(
            json.dumps(
                {
                    "pending_count": pending_count,
                    "threshold_days": THRESHOLD_DAYS,
                    "computed_state": computed_state,
                },
                separators=(",", ":"),
            )
        )
    else:
        print(pending_count)

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
