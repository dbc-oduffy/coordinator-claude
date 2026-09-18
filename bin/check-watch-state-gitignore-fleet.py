#!/usr/bin/env python3
"""check-watch-state-gitignore-fleet — box-local state must be ignored in EVERY fleet repo.

WHY THIS EXISTS. `state/group-em-watch.json`, `state/group-em-watch-parked.json` and
`state/group-em-watch-spool.jsonl` are per-machine runtime state written by a live poller and by
every session's own `Stop` hook. DoE-claude's `/coordinator:repo-setup` already prescribes them in
its canonical `.gitignore` block (`skills/repo-setup/residue/mechanics.md`) -- but that block is
laid down once, at setup, and a repo onboarded before the trio existed never receives it. Nothing
else checks.

That gap is not theoretical: `claude-klabauter` was found on 2026-09-02 with the spool TRACKED, i.e.
one machine's park records syncing to every other machine through git. The failure is silent in
exactly the way the starter template's own header warns about -- invisible until a second machine
exists, and then wrong rather than merely untidy.

REPORT-ONLY BY DEFAULT, AND `--apply` STOPS SHORT OF UNTRACKING. Same stance as its sibling
`check-gitignore-template-drift.py`, for the same reason: an ignore rule added for an
already-tracked path is inert until the path leaves the index, and `git rm --cached` in a repo this
script does not own is not a call it gets to make unattended. `--apply` appends the missing rules
under one header and then PRINTS the exact untracking command for a human or the owning repo's EM
to run. It never runs git.

NEVER `git rm` (without `--cached`) ON THE SPOOL. A `Stop` hook appends to it live, on a box
carrying a dozen-plus concurrent sessions; deleting it mid-append costs a peer's watch records for
no benefit, since the file is regenerated on the next park anyway. The remediation is to drop it
from the INDEX and leave the working copy alone.

Repos come from the machine-local registry (`repos.*`), by shell-out -- importing the reader is
barred by its own module contract. A repo key that resolves to a path that is not a git worktree is
SKIPPED, not failed: the registry declares intent, never live state, and a fleet map naming a repo
this machine has not cloned is normal.

Exit codes: 0 = every resolvable repo is clean, or nothing resolved. 1 = at least one repo is
missing a rule or is tracking one of the trio. 2 = usage/environment error (no `machine-local`).

Spec backlink: docs/plans/2026-09-18-doe-holds-no-scripts.md, chunk W2-C5.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# Every path here is box-local: written by a live poller or a hook on THIS machine, read by
# nothing in any other clone. Spelled exactly as DoE-claude's skills/repo-setup/residue/mechanics.md
# prescribes them; DoE-claude's test_watch_state_gitignore_fleet.py pins the two spellings together
# so the instrument and the prose that documents it cannot drift apart.
#
# The script keeps its watch-state name because a rename would strand the memos, handoffs and the
# tripwire-registry entry that cite it by path. The remit is wider than the name: each group below
# gets its own `.gitignore` header, so a widened sweep never files a new path under a header that
# does not describe it.
WATCH_STATE_PATHS = (
    "state/group-em-watch.json",
    "state/group-em-watch-parked.json",
    "state/group-em-watch-spool.jsonl",
)

ENGINE_PROVENANCE_PATHS = ("state/engine-provenance-counts.jsonl",)

BOX_LOCAL_STATE_GROUPS = (
    ("# Group-EM watch runtime state — per-machine, never committed", WATCH_STATE_PATHS),
    (
        "# Engine-provenance ledger — this box's engine-root resolution, appended on every hook fire",
        ENGINE_PROVENANCE_PATHS,
    ),
)

CHECKED_PATHS = WATCH_STATE_PATHS + ENGINE_PROVENANCE_PATHS


def _settings_home() -> Path:
    explicit = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if explicit:
        return Path(explicit)
    home = os.environ.get("CLAUDE_HOME") or os.path.expanduser("~")
    return Path(home) / ".coordinator-claude-settings"


def _machine_local() -> list[str]:
    """The invocation prefix for the machine-local CLI, per resolve-coordinator-bin.md.

    `machine-local` is one of the six pre-engine bootstrap resolvers, so it carries a real `.cmd`
    on Windows alongside the extensionless POSIX launcher.
    """
    binroot = _settings_home() / "bin"
    name = "machine-local.cmd" if os.name == "nt" else "machine-local"
    return [str(binroot / name)]


def _no_console() -> int:
    """Suppress the console window each subprocess would flash under headless Windows Bash.

    Zero on every other platform, where the flag does not exist.
    """
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _run(argv: list[str]) -> str | None:
    try:
        out = subprocess.run(
            argv, capture_output=True, text=True, timeout=60, creationflags=_no_console()
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout


def _repo_paths() -> dict[str, Path]:
    """Every `repos.*` registry key that resolves to a real git worktree on this machine.

    One `machine-local dump` resolves every key in a single process; `keys` plus a `get` per key
    cost 1+N processes for the same file read."""
    dumped = _run(_machine_local() + ["dump"])
    if dumped is None:
        return {}
    try:
        registry = json.loads(dumped)
    except ValueError:
        return {}
    resolved: dict[str, Path] = {}
    for key, value in registry.items():
        if not key.startswith("repos.") or not isinstance(value, str) or not value.strip():
            continue
        path = Path(value.strip())
        if (path / ".git").exists():
            resolved[key[len("repos.") :]] = path
    return resolved


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        timeout=60,
        creationflags=_no_console(),
    )


def audit_repo(repo: Path) -> tuple[list[str], list[str]]:
    """Return (paths not ignored, paths tracked in the index) for one repo.

    HEAD IS CHECKED ALONGSIDE THE INDEX, because they disagree in exactly the state this sweep
    creates. `ls-files` reads the INDEX, so a `git rm --cached` that has been staged and not yet
    committed reads as untracked while `HEAD` still carries the file and every fresh clone still
    gets it. Reporting that repo clean is the worst possible answer: the operator is mid-remedy and
    the tool tells them they are done. Either surface carrying the path counts as tracked.

    `--no-index` IS LOAD-BEARING, NOT A TIDINESS FLAG. Plain `git check-ignore` answers "would git
    ignore this path", and for a TRACKED path the answer is always no -- tracking beats every
    ignore rule, so the rule is not consulted. Without the flag this function reports
    "rule missing" for a repo whose rule is present and whose file is merely tracked, and `--apply`
    then appends a duplicate of a rule already there. Measured on `claude-klabauter`, 2026-09-02,
    which is exactly the shape this sweep exists to find -- so the misread lands on precisely the
    repos that matter. The two questions are independent and both are asked: is the RULE present
    (`--no-index`), and is the path in the INDEX (`ls-files`).
    """
    paths = list(CHECKED_PATHS)
    ignored = set(
        _git(repo, "check-ignore", "--no-index", "--", *paths).stdout.splitlines()
    )
    in_index = _git(repo, "ls-files", "--", *paths).stdout.splitlines()
    in_head = _git(repo, "ls-tree", "-r", "HEAD", "--name-only", "--", *paths).stdout.splitlines()
    present = set(in_index) | set(in_head)

    def _carried(rel: str) -> bool:
        prefix = rel.rstrip("/") + "/"
        return rel in present or any(p.startswith(prefix) for p in present)

    unignored = [rel for rel in paths if rel not in ignored]
    tracked = [rel for rel in paths if _carried(rel)]
    return unignored, tracked


def apply_rules(repo: Path, missing: list[str]) -> None:
    """Append the missing rules, each under its own group header. Never touches the index.

    Grouped rather than filed under one banner: the two path families are box-local for
    different reasons, and a rule sitting under a header that does not describe it is the
    kind of thing a later reader deletes as stale.
    """
    wanted = set(missing)
    chunks = []
    for header, group in BOX_LOCAL_STATE_GROUPS:
        rows = [rel for rel in group if rel in wanted]
        if rows:
            chunks.append(
                "\n" + header + "\n" + "".join(rel + "\n" for rel in rows)
            )
    if not chunks:
        return
    gitignore = repo / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    suffix = "" if existing.endswith("\n") or not existing else "\n"
    with gitignore.open("a", encoding="utf-8") as fh:
        fh.write(suffix + "".join(chunks))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument(
        "--apply",
        action="store_true",
        help="append missing rules to each repo's .gitignore; still never untracks anything",
    )
    ap.add_argument(
        "--repo",
        action="append",
        default=None,
        help="audit this path instead of the registry's repos.* set (repeatable)",
    )
    args = ap.parse_args(argv)

    if args.repo:
        repos = {Path(r).name: Path(r) for r in args.repo}
    else:
        repos = _repo_paths()
        if not repos:
            print("SKIP: machine-local resolved no repos.* worktrees on this machine")
            return 0

    findings = 0
    untrack: list[tuple[Path, list[str]]] = []
    for name, repo in sorted(repos.items()):
        unignored, tracked = audit_repo(repo)
        if not unignored and not tracked:
            continue
        findings += 1
        print(f"{name}  ({repo})")
        if unignored:
            print("  not ignored: " + ", ".join(unignored))
            if args.apply:
                apply_rules(repo, unignored)
                print("  -> appended to .gitignore")
        if tracked:
            print("  TRACKED IN GIT: " + ", ".join(tracked))
            untrack.append((repo, tracked))

    if untrack:
        print()
        print("Untracking is NOT done for you. In each repo:")
        for repo, paths in untrack:
            print(f'  git -C "{repo}" rm --cached -- ' + " ".join(paths))
        print()
        print("Use `rm --cached`, never a bare `git rm`: a Stop hook appends to the spool live.")
        print()
        print("THEN COMMIT FROM THE INDEX, and VERIFY -- `git commit -- <paths>` CANNOT do this.")
        print("Pathspec (`--only`) mode commits WORKTREE state for the named paths and bypasses")
        print("the index, so it silently re-adds the file you just removed and exits 0. Measured")
        print("twice on claude-klabauter, 2026-09-02. Afterwards, always confirm with:")
        print("  git -C <repo> ls-files --error-unmatch -- <path>   # non-zero means untracked")

    if findings == 0:
        print(
            f"clean: {len(repos)} repo(s), all {len(CHECKED_PATHS)} box-local paths "
            "ignored and untracked"
        )
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
