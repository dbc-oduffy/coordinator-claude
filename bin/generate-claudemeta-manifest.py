#!/usr/bin/env python3
"""Generate the `--file-list` manifest for project-rag's `claudemeta` band.

Implements both axes of `state/reference/state-subtree-retrieval-priority-index.md` —
the subtree tier (P0-P2 keep set, default-deny) and the lifecycle predicate over each
artifact's own `status:` frontmatter, which no `--source-root` list can express.

Contract (project-rag-em, memo 2026-08-15-project-rag-em-file-list-landed-manifest-contract):
entries are newline-delimited, forward-slash, relative to `--source-root`; `#` and blank
lines are skipped by the consumer; every entry must resolve to an existing file under the
root or the build fails loud. Source-root for this manifest is whichever repo invokes it
(the CALLER's repo, not this engine's own tree — see path resolution note below).

Provenance header (`generated_at`/`repo_head`/`p_index_sha`, all `#`-prefixed so the
consumer's skip contract holds — verified against project-rag's `--file-list` parser,
`cli.py:9524-9612` on `work/machine-a/2026-08-08to11`) lets a reader determine staleness
without re-deriving the keep set: compare `repo_head` against the DoE HEAD it can read
directly.

Negative spec: this does NOT rank or re-decide tiers. The index is the ruling; this file
is its executable projection. Changing what gets indexed means editing the index first.

Arrived from DoE-claude state/reference/generate-claudemeta-manifest.py
(docs/plans/2026-09-18-doe-holds-no-scripts.md, chunk W3-C7). Published commands (workday-complete)
cite this row by name.

PATH RESOLUTION — "session repo" class (§ Path resolution), not "engine": this CLI's repo root is
whichever repo the caller stands in when it invokes `workday-complete`, which is any consumer repo
running the ceremony, never claude-klabauter's own tree in the general case. DoE's copy derived its
`REPO_ROOT` from `Path(__file__).resolve().parents[2]`, which was correct there only because the
script's own tree WAS the repo it indexed — exactly the DoE-claude@b644d5a9 lesson this move must
not repeat. `_repo_root()` below resolves through the caller's cwd
(`coordinator_core.git.repo_root.show_toplevel`) instead, called fresh on every `main()` call
(never memoized at module import) so a long-lived warm-door process serving one call from
Claude-klabauter's own cwd and the next from a different consumer repo's cwd resolves each
correctly. `REPO_ROOT`/`P_INDEX_PATH` remain module-level names — a test seam only, `None` in
production — so the ported DoE tests' `monkeypatch.setattr(mod, "REPO_ROOT", root)` idiom still
overrides them exactly as it did in DoE.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_ENGINE_ROOT = Path(__file__).resolve().parents[2]

# Test seam only (§ Path resolution note above) — production code never assigns these; each
# `main()` call resolves fresh from the caller's cwd instead. Ported DoE tests monkeypatch both.
REPO_ROOT: Path | None = None
P_INDEX_PATH: Path | None = None

#: Populated by `_repo_root()`, deferred out of module scope so the `sys.path` mutation and the
#: non-stdlib import it guards are not a module-body-inertness violation
#: (`coordinator_core.warm.serve_classifier`).
_show_toplevel = None  # type: ignore[assignment]


def _repo_root() -> Path:
    if REPO_ROOT is not None:
        return REPO_ROOT
    global _show_toplevel
    if _show_toplevel is None:
        if str(_ENGINE_ROOT) not in sys.path:
            sys.path.insert(0, str(_ENGINE_ROOT))
        from coordinator_core.git.repo_root import show_toplevel as _st

        _show_toplevel = _st
    resolved = _show_toplevel()
    if resolved is None:
        print("ERROR: not inside a git work tree", file=sys.stderr)
        raise SystemExit(2)
    return Path(resolved)


def _p_index_path() -> Path:
    if P_INDEX_PATH is not None:
        return P_INDEX_PATH
    return _repo_root() / "state/reference/state-subtree-retrieval-priority-index.md"


def _no_console_creationflags() -> dict:
    """Suppresses the conhost.exe popup a Windows console-subsystem child (git.exe
    included) allocates when spawned from a headless/no-controlling-terminal parent.
    No-op on POSIX. Inlined rather than imported from coordinator_core's Windows-portability
    module to keep this script runnable standalone (AC5: a plain command project-rag can invoke
    against its own checkout)."""
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}

# Subtree axis. Order matters: first matching prefix wins, so more specific paths lead.
P0 = (
    "docs/wiki/",
    "docs/architecture/",
    "docs/decisions/",
    "docs/contracts/",
    "state/reference/",
)
P1 = (
    "docs/plans/",
    "docs/roadmaps/",
    "state/roadmap/",
    "state/handoffs/",
    "state/audits/",
    "docs/problems/",
    "docs/research/",
)
P2 = (
    "archive/",
    "state/week-changelog/",
    "state/lessons/",
)

# Lifecycle axis. `superseded` always drops to never, at any tier.
TERMINAL = {
    "implemented",
    "shipped",
    "landed",
    "complete",
    "closed",
    "actioned",
    "final-approved",
}
DEAD = {"superseded"}

# Subtrees whose `status:` over-reports liveness (a crashed holder's claim is never
# auto-abandoned), so liveness is recency-bounded instead of taken at face value.
RECENCY_BOUNDED = ("state/handoffs/",)


def tier_of(rel: str) -> str | None:
    if rel.startswith(P0):
        return "P0"
    if rel.startswith(P1):
        return "P1"
    if rel.startswith(P2):
        return "P2"
    return None


def read_status(path: Path) -> str | None:
    """Read `status:` out of YAML frontmatter without parsing the whole document."""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            if fh.readline().strip() != "---":
                return None
            for _ in range(60):
                line = fh.readline()
                if not line or line.strip() == "---":
                    return None
                if line.startswith("status:"):
                    return line.split(":", 1)[1].strip().strip("\"'").lower()
    except OSError:
        return None
    return None


def last_commit_times() -> dict[str, int]:
    """One `git log` pass — per-file spawns would be ~200 processes on a shared machine."""
    out = subprocess.run(
        ["git", "log", "--no-merges", "--name-only", "--format=@%ct"],
        cwd=_repo_root(),
        capture_output=True,
        text=True,
        errors="replace",
        **_no_console_creationflags(),
    ).stdout
    times: dict[str, int] = {}
    stamp = 0
    for line in out.splitlines():
        if line.startswith("@"):
            stamp = int(line[1:])
        elif line and line not in times:
            times[line] = stamp
    return times


def git_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=_repo_root(),
        capture_output=True,
        text=True,
        errors="replace",
        **_no_console_creationflags(),
    ).stdout.strip()


def p_index_sha() -> str:
    return subprocess.run(
        ["git", "hash-object", str(_p_index_path())],
        cwd=_repo_root(),
        capture_output=True,
        text=True,
        errors="replace",
        **_no_console_creationflags(),
    ).stdout.strip()


def derive_keep_set(
    handoff_recency_days: int, drop_terminal_plans: bool
) -> tuple[list[str], dict[str, int], int]:
    repo_root = _repo_root()
    commit_times = last_commit_times()
    cutoff = time.time() - handoff_recency_days * 86400

    kept: list[str] = []
    counts: dict[str, int] = {}
    bytes_kept = 0

    for path in repo_root.rglob("*.md"):
        rel = path.relative_to(repo_root).as_posix()
        if rel.startswith(".git/"):
            continue
        tier = tier_of(rel)
        if tier is None:
            continue

        status = read_status(path)
        if status in DEAD:
            continue

        if tier == "P1":
            terminal = status in TERMINAL
            if rel.startswith("docs/plans/") and terminal:
                if drop_terminal_plans:
                    continue
                tier = "P2"
            elif terminal:
                tier = "P2"
            if rel.startswith(RECENCY_BOUNDED) and commit_times.get(rel, 0) < cutoff:
                continue

        kept.append(rel)
        counts[tier] = counts.get(tier, 0) + 1
        bytes_kept += path.stat().st_size

    kept.sort()
    return kept, counts, bytes_kept


def build_header(
    kept: list[str], bytes_kept: int, generated_at: str, repo_head: str, p_index_sha_val: str
) -> list[str]:
    return [
        "# claudemeta keep-set manifest",
        "# generated by coordinator/bin/generate-claudemeta-manifest.py",
        "# ruling: state/reference/state-subtree-retrieval-priority-index.md (P0-P2, default-deny)",
        "# paths are relative to --source-root, which for this manifest is the caller's repo root",
        f"# generated_at: {generated_at}",
        f"# repo_head: {repo_head}",
        f"# p_index_sha: {p_index_sha_val}",
        f"# {len(kept)} files, {bytes_kept / 1_048_576:.1f} MB",
    ]


def parse_existing(path: Path) -> tuple[set[str], str | None, str | None]:
    """Split an on-disk manifest into (entries, repo_head, p_index_sha) — never generated_at."""
    entries: set[str] = set()
    repo_head: str | None = None
    p_index_sha_val: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# repo_head:"):
            repo_head = line.split(":", 1)[1].strip()
        elif line.startswith("# p_index_sha:"):
            p_index_sha_val = line.split(":", 1)[1].strip()
        elif line.startswith("# generated_at:"):
            continue
        elif not line.strip() or line.startswith("#"):
            continue
        else:
            entries.add(line)
    return entries, repo_head, p_index_sha_val


def cadence(args) -> int:
    """Ceremony entry point — check, and regenerate-plus-commit only on real drift.

    One process rather than a shell conditional: the ceremonies that call this run on
    Windows as often as POSIX, and this repo treats structural bash as a portability
    defect. Also the cheaper shape — a shell `if` costs three spawns to this one's one,
    on a machine where spawn count is the standing tax.
    """
    rc = main_check(args)
    if rc == 0:
        return 0

    rc = main_generate(args)
    if rc != 0:
        return rc

    settings_home = os.environ.get("COORDINATOR_SETTINGS_HOME") or str(
        Path.home() / ".coordinator-claude-settings"
    )
    commit_cli = shutil.which("coordinator-safe-commit", path=str(Path(settings_home) / "bin"))
    if commit_cli is None:
        # Regenerated but uncommitted is a legitimate standalone-run outcome (AC5), not a
        # failure — say so rather than exiting non-zero into a ceremony that would halt.
        print(
            "claudemeta manifest regenerated but NOT committed: coordinator-safe-commit "
            f"not found under {settings_home}/bin",
            file=sys.stderr,
        )
        return 0

    proc = subprocess.run(
        [
            commit_cli,
            "chore: regenerate claudemeta keep-manifest",
            "--",
            "state/reference/claudemeta-keep-manifest.txt",
        ],
        cwd=_repo_root(),
        capture_output=True,
        text=True,
        errors="replace",
        **_no_console_creationflags(),
    )
    if proc.returncode != 0:
        print(f"claudemeta manifest commit failed: {proc.stderr.strip()}", file=sys.stderr)
        return proc.returncode
    print(proc.stdout.strip())
    return 0


def main_check(args) -> int:
    """Exit 1 on drift, 0 when current. Never writes — safe to run anywhere, by anyone."""
    kept, _counts, _bytes_kept = derive_keep_set(args.handoff_recency_days, args.drop_terminal_plans)
    out_path = Path(args.out)
    if not out_path.exists():
        print(f"claudemeta manifest missing at {out_path}", file=sys.stderr)
        return 1

    disk_entries, _disk_head, disk_p_index = parse_existing(out_path)
    cur_entries = set(kept)
    added = cur_entries - disk_entries
    removed = disk_entries - cur_entries

    # `repo_head` is provenance, never a drift signal. Comparing on it would make --check
    # dirty after every commit in the repo, so the cadence would regenerate and commit a
    # byte-identical entry list at every gate — noise that trains the reader to ignore the
    # line. Drift is a changed keep set, or a changed ruling.
    drift_reasons = []
    if added or removed:
        drift_reasons.append(f"+{len(added)} -{len(removed)} entries")
    if disk_p_index != p_index_sha():
        drift_reasons.append("p_index_sha changed")

    if drift_reasons:
        print(f"claudemeta manifest drift: {', '.join(drift_reasons)}", file=sys.stderr)
        return 1
    return 0


def main_generate(args) -> int:
    kept, counts, bytes_kept = derive_keep_set(args.handoff_recency_days, args.drop_terminal_plans)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    header = build_header(kept, bytes_kept, generated_at, git_head(), p_index_sha())
    Path(args.out).write_text("\n".join(header + kept) + "\n", encoding="utf-8", newline="\n")

    print(f"claudemeta manifest regenerated: {len(kept)} files")

    if args.stats:
        for tier in sorted(counts):
            print(f"{tier}: {counts[tier]}", file=sys.stderr)
        print(f"total: {len(kept)} files, {bytes_kept / 1_048_576:.1f} MB", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    repo_root = _repo_root()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(repo_root / "state/reference/claudemeta-keep-manifest.txt"))
    ap.add_argument(
        "--handoff-recency-days",
        type=int,
        default=60,
        help="a baton untouched this long is not live regardless of its status:",
    )
    ap.add_argument(
        "--drop-terminal-plans",
        action="store_true",
        help="cut the P2 terminal-plan tier (the distillation backlog) as well",
    )
    ap.add_argument("--stats", action="store_true", help="print per-tier counts to stderr")
    ap.add_argument(
        "--check",
        action="store_true",
        help="re-derive in memory and compare against --out; exit 1 on drift, never write",
    )
    ap.add_argument(
        "--cadence",
        action="store_true",
        help="ceremony entry point: check, and on drift regenerate and commit — one process, "
        "no shell. Silent and exit 0 when the manifest is already current.",
    )
    args = ap.parse_args(argv)

    if args.cadence:
        return cadence(args)
    if args.check:
        return main_check(args)
    return main_generate(args)


if __name__ == "__main__":
    raise SystemExit(main())
