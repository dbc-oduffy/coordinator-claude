"""Resolve the engine commit a DoE plugin round pins from the last published stamp.

The newest `[source-head <sha>]`-stamped commit reachable from the engine
mirror's published ref names the engine commit that klabauter round ran
from. Trust premise: the stamp is honest only once
docs/plans/2026-09-30-publish-round-stamps-the-tree-it-copied.md lands and
percolate-round stamps its round-start pin.

Never reads the mirror's HEAD, never fetches, never falls back to the
engine's working HEAD. At most two read-only git spawns per call.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from coordinator_core.git.git_state import parse_source_sha_suffix
from coordinator_core.git.run import GitResult, run_git

_STAMP_WALK_LIMIT = 50


@dataclass(frozen=True)
class PublishedEnginePin:
    source_sha: str
    mirror_commit: str
    engine_toplevel: Path


class PublishedEnginePinError(Exception):
    """One fact plus the remedy; the round refuses before any write."""


def _git(repo: Path, *args: str) -> GitResult:
    return run_git(["--no-optional-locks", "-C", str(repo), *args])


def resolve_published_engine_pin(
    engine_toplevel: Path, mirror_root: Path, published_ref: str
) -> PublishedEnginePin:
    """Return the engine commit named by the newest stamped commit on `published_ref`.

    Raises PublishedEnginePinError when the ref does not resolve, no stamp
    appears within `_STAMP_WALK_LIMIT` subjects, or the stamped sha is not a
    commit in `engine_toplevel`.
    """
    log = _git(
        mirror_root,
        "log",
        f"--max-count={_STAMP_WALK_LIMIT}",
        "--format=%H%x00%s",
        published_ref,
        "--",
    )
    if not log.ok:
        raise PublishedEnginePinError(
            f"{published_ref} does not resolve in mirror {mirror_root}; "
            "fetch or push the engine mirror's release channel."
        )
    for line in log.stdout.splitlines():
        commit, sep, subject = line.partition("\x00")
        if not sep:
            continue
        hex_sha = parse_source_sha_suffix(subject)
        if hex_sha is None:
            continue
        check = _git(
            engine_toplevel,
            "rev-parse",
            "--verify",
            "--quiet",
            "--end-of-options",
            f"{hex_sha}^{{commit}}",
        )
        full = check.stdout.strip()
        if not check.ok or not full:
            raise PublishedEnginePinError(
                f"stamped sha {hex_sha[:12]} (mirror {mirror_root} {published_ref} "
                f"{commit[:12]}) is not a commit in {engine_toplevel}; "
                f"fetch the engine so {hex_sha[:12]} resolves."
            )
        return PublishedEnginePin(
            source_sha=full, mirror_commit=commit, engine_toplevel=engine_toplevel
        )
    raise PublishedEnginePinError(
        f"no [source-head] stamp within {_STAMP_WALK_LIMIT} commits of {published_ref} "
        f"in mirror {mirror_root}; publish a klabauter round."
    )
