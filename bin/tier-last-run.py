#!/usr/bin/env python3
"""tier-last-run — record and read the durable last-run sentinel for a declared ceremony tier.

WHY THIS EXISTS. `coordinator.local.md`'s `ceremony_test_cmds` entries have no recorded last-run
time anywhere on disk, so nothing distinguishes a tier that passed this morning from one that has
not executed since it was written. This CLI is the recording half of that feedback loop; C2 reads
its sentinel at boot, C5 reads it for blast-radius advisories.

`blast-radius` is the third verb: it compares the current change's touched paths against each
declared entry's `collection_roots` and names, per entry with a hit, how many changed files fall
under it and that tier's last-run age. It is ADVISORY ONLY — always exit 0 — and it is the one
verb here that shells out to git, which is exactly why it lives in this CLI rather than in
`project-orientation.py`'s zero-subprocess boot banner.

NEGATIVE SPEC: this CLI never runs a test command and never reads test output. It records what its
caller reports, verbatim. Conflating recording with running would turn a recorder into a second,
slower test tier — the caller (a ceremony invocation) is the sole source of truth for whether a
command ran and what it returned.

State file: `state/tier-last-run.json`, repo-relative, one object per `ceremony_test_cmds` entry
name:

    { "<entry>": { "ran_at": "<UTC ISO8601>", "cmd": "<verbatim>", "exit_code": <int> } }

Whole-file read-modify-write. A corrupt or unparseable state file is REPLACED wholesale, never
merged, and the replacement is reported on stderr — a half-parsed currency record is the
vacuous-green failure this mechanism exists to kill.

Entry names are validated against the `ceremony_test_cmds` entries declared in
`coordinator.local.md`'s frontmatter. An unknown entry name is exit 1 with the known names
listed — never a silently-created key. A declared entry whose `collection_roots` paths do not
resolve on disk is also exit 1, with the missing path named.

Zero third-party runtime dependency beyond PyYAML (already imported elsewhere in this directory,
e.g. `compose-review-wave.py`), stdlib otherwise.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

try:
    import yaml
except ImportError:  # pragma: no cover - environment defect, not a code path under test
    yaml = None

_STATE_RELATIVE = Path("state") / "tier-last-run.json"
_LOCAL_DOCTRINE_RELATIVE = Path("coordinator.local.md")
_ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%f%z"


def _repo_root(explicit: Optional[str]) -> Path:
    return Path(explicit).resolve() if explicit else Path.cwd()


def _state_path(repo_root: Path) -> Path:
    return repo_root / _STATE_RELATIVE


def _load_local_doctrine(repo_root: Path) -> dict[str, Any]:
    """Parse `coordinator.local.md`'s YAML frontmatter and return the parsed mapping.

    Raises `ValueError` (with a human-readable message) on a missing file, missing/malformed
    frontmatter delimiters, or a YAML document that is not a mapping — every caller here treats
    that as a hard failure, never a silent empty-config fallback.
    """
    path = repo_root / _LOCAL_DOCTRINE_RELATIVE
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc

    if not text.startswith("---"):
        raise ValueError(f"{path} has no YAML frontmatter (expected leading '---')")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"{path} frontmatter is not closed with a second '---'")

    if yaml is None:
        raise ValueError("PyYAML is not installed; cannot parse coordinator.local.md frontmatter")

    try:
        parsed = yaml.safe_load(parts[1])
    except yaml.YAMLError as exc:
        raise ValueError(f"{path} frontmatter is not valid YAML: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError(f"{path} frontmatter did not parse to a mapping")
    return parsed


def _ceremony_entries(repo_root: Path) -> list[dict[str, Any]]:
    """The declared `ceremony_test_cmds` list, each entry a dict carrying at least `name`."""
    doctrine = _load_local_doctrine(repo_root)
    entries = doctrine.get("ceremony_test_cmds") or []
    if not isinstance(entries, list):
        raise ValueError("coordinator.local.md's ceremony_test_cmds is not a list")
    return entries


def _entry_by_name(entries: list[dict[str, Any]], name: str) -> Optional[dict[str, Any]]:
    for entry in entries:
        if isinstance(entry, dict) and entry.get("name") == name:
            return entry
    return None


def _validate_entry(repo_root: Path, entry_name: str) -> dict[str, Any]:
    """Return the declared entry for `entry_name`, or raise `ValueError` naming the defect.

    Two independent rejection paths, both AC5: an entry name absent from `ceremony_test_cmds`,
    and a declared entry whose `collection_roots` do not resolve on disk.
    """
    entries = _ceremony_entries(repo_root)
    entry = _entry_by_name(entries, entry_name)
    if entry is None:
        known = ", ".join(sorted(e.get("name", "") for e in entries if isinstance(e, dict))) or "(none declared)"
        raise ValueError(f"unknown ceremony_test_cmds entry '{entry_name}'; known entries: {known}")

    roots = entry.get("collection_roots") or []
    for root in roots:
        root_path = repo_root / root
        if not root_path.exists():
            raise ValueError(
                f"declared collection_roots path for entry '{entry_name}' does not exist: {root_path}"
            )
    return entry


def _load_state(state_path: Path) -> dict[str, Any]:
    """Whole-file read; a corrupt/unparseable file is REPLACED, never merged (reported by caller).

    On corruption, names what is being discarded rather than just announcing a wholesale reset:
    an unreadable/unparseable file cannot say which entry keys it held, so that case is named
    explicitly as "entries unrecoverable"; a file that parses but is the wrong JSON type still
    lets us enumerate whatever keys a dict-shaped near-miss carried. Silently resetting to `{}`
    would re-render every entry's prior record as `unknown` without saying a record was lost at
    all — the exact lie this mechanism exists to prevent (module docstring).
    """
    if not state_path.exists():
        return {}
    try:
        text = state_path.read_text(encoding="utf-8")
        parsed = json.loads(text)
    except (OSError, json.JSONDecodeError) as exc:
        print(
            f"tier-last-run: {state_path} is unreadable/unparseable ({exc.__class__.__name__}: "
            f"{exc}); replacing wholesale rather than merging; entries it held are unrecoverable "
            "(could not read the file to name them)",
            file=sys.stderr,
        )
        return {}
    if not isinstance(parsed, dict):
        lost_keys = (
            sorted(str(k) for k in parsed.keys())
            if isinstance(parsed, dict)
            else "(not a JSON object; no entry keys to name)"
        )
        print(
            f"tier-last-run: {state_path} did not parse to a JSON object; replacing wholesale "
            f"rather than merging; entries lost: {lost_keys}",
            file=sys.stderr,
        )
        return {}
    return parsed


def _write_state(state_path: Path, state: dict[str, Any]) -> None:
    """Write the whole state file atomically: temp file in the same directory, then `os.replace()`.

    `os.replace()` is atomic on both POSIX and Windows (unlike a plain overwrite, which a reader
    or a concurrently-writing sibling session can observe mid-write as truncated/partial JSON) —
    load-bearing on this repo's own machine, which runs a dozen-plus concurrent EM sessions.

    This function only makes the WRITE atomic. It does not make the surrounding read-modify-write
    in `cmd_record` atomic across two concurrent writers: two sessions recording different entries
    close together can still race (A reads, B writes, A writes back and clobbers B's key) with
    last-write-wins on the whole file. That is an accepted tradeoff for now, not an oversight —
    no lock is taken here. A future write losing a sibling's just-written entry to this race is a
    known, named gap, not the silent-corruption failure `_load_state` above guards against.
    """
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = state_path.with_name(f"{state_path.name}.tmp-{os.getpid()}")
    tmp_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_path, state_path)


def cmd_record(args: argparse.Namespace) -> int:
    repo_root = _repo_root(args.repo_root)
    try:
        _validate_entry(repo_root, args.entry)
    except ValueError as exc:
        print(f"tier-last-run record: {exc}", file=sys.stderr)
        return 1

    state_path = _state_path(repo_root)
    state = _load_state(state_path)
    state[args.entry] = {
        "ran_at": datetime.now(timezone.utc).strftime(_ISO_FORMAT),
        "cmd": args.cmd,
        "exit_code": args.exit,
    }
    _write_state(state_path, state)
    print(f"recorded {args.entry}: exit={args.exit}")
    return 0


def cmd_read(args: argparse.Namespace) -> int:
    repo_root = _repo_root(args.repo_root)
    state_path = _state_path(repo_root)
    state = _load_state(state_path)

    if args.entry:
        record = state.get(args.entry)
        if record is None:
            print(json.dumps({"entry": args.entry, "status": "unknown", "record": None}))
            return 0
        print(json.dumps({"entry": args.entry, "status": "recorded", "record": record}))
        return 0

    print(json.dumps({"status": "recorded" if state else "unknown", "records": state}))
    return 0


def _format_age(ran_at: str) -> str:
    """Render an ISO8601 `ran_at` timestamp as a coarse human age (`"6h ago"`, `"3d ago"`).

    Returns the literal string `"unparseable"` on a malformed timestamp — never silently treated
    as recent.
    """
    try:
        parsed = datetime.strptime(ran_at, _ISO_FORMAT)
    except ValueError:
        return "unparseable"
    delta = datetime.now(timezone.utc) - parsed
    seconds = delta.total_seconds()
    if seconds < 0:
        return "unparseable"
    hours = seconds / 3600
    if hours < 1:
        return f"{max(1, int(seconds / 60))}m ago"
    if hours < 24:
        return f"{int(hours)}h ago"
    return f"{int(hours / 24)}d ago"


def _entry_age(state: dict[str, Any], entry_name: str) -> str:
    """The last-run age for `entry_name`, or the literal word `unknown` when unrecorded."""
    record = state.get(entry_name)
    if not isinstance(record, dict) or "ran_at" not in record:
        return "unknown"
    return _format_age(record["ran_at"])


def _changed_paths(repo_root: Path, since: str) -> list[str]:
    """`git diff --name-only <since>..HEAD`, relative POSIX-style paths from the repo root.

    Raises `ValueError` (never a raw `CalledProcessError`) naming the failing invocation, so the
    caller can report a clean exit-1 rather than a traceback on a bad `--since` ref.
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{since}..HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        raise ValueError(f"cannot invoke git: {exc}") from exc
    if result.returncode != 0:
        raise ValueError(
            f"git diff --name-only {since}..HEAD failed (exit {result.returncode}): "
            f"{result.stderr.strip()}"
        )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def cmd_blast_radius(args: argparse.Namespace) -> int:
    """ADVISORY ONLY. Always exits 0, on a hit and on no hit alike — never a gate, never blocking.

    NEGATIVE SPEC: the count reported per entry is the number of CHANGED FILES that fall under
    that entry's declared `collection_roots`, never an inferred "gates that assert on your
    change". No call-graph data exists for pytest assertions and this CLI does not fake one —
    naming a precise gate count we cannot derive is the hand-maintained-mapping rot class in a
    different costume. The signal is deliberately coarse and its output says so.
    """
    repo_root = _repo_root(args.repo_root)
    try:
        entries = _ceremony_entries(repo_root)
    except ValueError as exc:
        print(f"tier-last-run blast-radius: {exc}", file=sys.stderr)
        return 0

    try:
        changed = _changed_paths(repo_root, args.since)
    except ValueError as exc:
        print(f"tier-last-run blast-radius: {exc}", file=sys.stderr)
        return 0

    state = _load_state(_state_path(repo_root))

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        roots = entry.get("collection_roots") or []
        if not name or not roots:
            continue
        normalized_roots = [Path(root).as_posix().rstrip("/") + "/" for root in roots]
        hit_count = sum(
            1
            for path in changed
            if any(Path(path).as_posix().startswith(root) for root in normalized_roots)
        )
        if hit_count == 0:
            continue
        age = _entry_age(state, name)
        root_label = ", ".join(str(root) for root in roots)
        print(f"{name}: {hit_count} changed files under {root_label} — last ran {age}")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tier-last-run",
        description="Record and read the durable last-run sentinel for a declared ceremony tier.",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="repo root to resolve state/coordinator.local.md against (default: cwd)",
    )
    subparsers = parser.add_subparsers(dest="verb", required=True)

    record = subparsers.add_parser("record", help="record a ceremony tier's last run")
    record.add_argument("--entry", required=True, help="ceremony_test_cmds entry name")
    record.add_argument("--cmd", required=True, help="the command actually run, verbatim")
    record.add_argument("--exit", required=True, type=int, help="the command's exit code")
    record.set_defaults(func=cmd_record)

    read = subparsers.add_parser("read", help="read recorded last-run sentinels")
    read.add_argument("--entry", default=None, help="restrict to one entry name")
    read.set_defaults(func=cmd_read)

    blast_radius = subparsers.add_parser(
        "blast-radius",
        help="advise which declared ceremony tiers this change touches",
    )
    blast_radius.add_argument(
        "--since",
        default="origin/main",
        help="git diff base ref (default: origin/main)",
    )
    blast_radius.set_defaults(func=cmd_blast_radius)

    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv[1:])
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
