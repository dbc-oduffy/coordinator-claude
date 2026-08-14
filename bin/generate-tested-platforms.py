"""
generate-tested-platforms — derive `tested_platforms` from platform-outcome records.

MECHANISM (DR-047: DoE owns the generator; claude-klabauter owns the confirming engine — that
half is C3b, out of scope here). `tested_platforms` is a DERIVED field: this script
reads `state/platform-outcomes/<platform>/<machine>/<surface>.yaml` records (C1's
schema — coordinator/schemas/platform-outcome.schema.json) and computes the set of
platforms with at least one PASSING, NON-STALE record whose `surface` matches a
manifest-declared ENTRY POINT.

ENTRY-POINT SCOPE (per the plan's "Open question for the PM" resolution, F4/the Director of Engineering):
point 4 of the install contract is about the repo's install entry point
(`standalone_setup_script` / `programmatic_entry_point` —
agent-install-contract.md:1571-1574, agent-install-manifest.schema.json:167), NOT the
ceremony hot path (that is C5's separate KR-2 derivation, same record store, different
`surface` values). A record counts as backing evidence for `tested_platforms` only when
its `surface` field equals one of the manifest's own entry-point KEY NAMES —
"standalone_setup_script" or "programmatic_entry_point" — not a ceremony op id.

STALENESS (C1's two rules, both checked — mirrors platform-outcome.schema.json's
schema-level description verbatim):
  PRIMARY   — surface_sha no longer matches this repo's current HEAD SHA.
  SECONDARY — observed_at is more than PLATFORM_OUTCOME_STALENESS_DAYS (30) days old.
A record failing either rule is stale and cannot promote a platform.

TWO SAFETY BEHAVIORS (mandatory — prevent a D1 grandfather regression):
  1. DRY-RUN BY DEFAULT. With no --write flag this script only PRINTS the derived
     tested_platforms value; it writes nothing. --write is required to mutate
     agent-install-manifest.json.
  2. GRANDFATHER CLAUSE. A platform already present in the manifest's tested_platforms
     that has ZERO backing entry-point-surface records (not "zero passing records" —
     literally no record of that surface kind exists for it yet) is PRESERVED, with an
     advisory line ("grandfathered: <platform> has no backing records"), never silently
     demoted for lack of evidence. This is what keeps DoE's pre-record macos/linux
     claims intact until real records exist. A platform that DOES have entry-point
     records but none passing/fresh is legitimately demoted (the demotion rule, per
     the point-4 subsection C3a2 documents) — grandfather only protects claims with
     literally no backing evidence at all, never protects a claim contradicted by a
     failing/stale record. Promoting a NEW platform (one not already in
     tested_platforms) always requires a real passing, non-stale record — grandfather
     never promotes, only preserves.

USAGE
    generate-tested-platforms [--write] [--repo-root DIR]
        --write       Update agent-install-manifest.json's tested_platforms field.
                       Omit to dry-run (print only, write nothing).
        --repo-root   Override the repo root (default: derived from this file's
                       on-disk location — coordinator/bin/../.. — never cwd/HOME).

Windows-clean: no shell-out except a single `git rev-parse HEAD` (guarded via
`coordinator_core.win_portability.no_console_creationflags()`, a no-op off Windows), no
expanduser("~")/HOME dependency — repo root defaults to `__file__`-derived (this
script's own location) but is overridable via `--repo-root` to probe a target repo
other than claude-klabauter's own checkout; manifest/records paths are then derived from
whichever repo_root is in effect. `coordinator_core` itself is always imported off
this script's own location, never off `--repo-root`, since `coordinator_core` lives
in claude-klabauter's checkout regardless of which repo is being probed.

Spec backlink: DoE-claude:pln-platform-verified-is-a-distinc-a076aa § C3a1
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

try:
    import yaml
except ImportError:  # pragma: no cover - exercised only on a broken environment
    yaml = None

GENERATES = [
    {
        "artifact": "docs/install/agent-install-manifest.json",
        "stamp_key": "tested_platforms",
        "sources": ["coordinator/bin/generate-tested-platforms.py"],
    },
]

# Mirrors platform-outcome.schema.json's SECONDARY staleness constant
# (PLATFORM_OUTCOME_STALENESS_DAYS = 30), named here rather than encoded as a
# bare magic number, per that schema's own stated convention.
PLATFORM_OUTCOME_STALENESS_DAYS = 30

# PlatformId vocabulary SSOT: agent-install-manifest.schema.json #/$defs/PlatformId.
# Canonical ordering used when writing tested_platforms, so a no-op run never
# reorders an unchanged value into a spurious diff.
PLATFORM_ENUM_ORDER = ["macos", "linux", "windows"]

REQUIRED_RECORD_FIELDS = [
    "platform",
    "surface",
    "command",
    "outcome",
    "exit_code",
    "observed_at",
    "machine",
    "surface_sha",
    "invoking_repo",
]

# Two known layouts for the manifest, relative to repo root:
#   - DoE-claude:  coordinator/docs/install/agent-install-manifest.json
#   - claude-klabauter:      docs/install/agent-install-manifest.json
# `--repo-root` lets this tool probe either shape, so a single hardcoded
# relative path cannot serve both (review: carried loose end, slice-3 review).
_MANIFEST_RELATIVE_CANDIDATES = (
    os.path.join("coordinator", "docs", "install", "agent-install-manifest.json"),
    os.path.join("docs", "install", "agent-install-manifest.json"),
)
_RECORDS_RELATIVE = os.path.join("state", "platform-outcomes")


def _repo_root() -> str:
    """coordinator/bin/<this file> -> repo root, two levels up. Never assumes cwd."""
    bin_dir = os.path.dirname(os.path.abspath(__file__))
    coordinator_dir = os.path.dirname(bin_dir)
    return os.path.dirname(coordinator_dir)


def _manifest_path(repo_root: str) -> str:
    """Resolve whichever manifest layout exists under `repo_root`, preferring
    the repo's own shape. Neither exists -> raise FileNotFoundError naming
    both attempted paths (fail loud, not a silent pick of the wrong one)."""
    attempted = [os.path.join(repo_root, rel) for rel in _MANIFEST_RELATIVE_CANDIDATES]
    for candidate in attempted:
        if os.path.isfile(candidate):
            return candidate
    raise FileNotFoundError(
        "no agent-install-manifest.json found under repo root "
        f"{repo_root!r}; tried: {', '.join(attempted)}"
    )


def _records_root(repo_root: str) -> str:
    return os.path.join(repo_root, _RECORDS_RELATIVE)


def _current_repo_sha(repo_root: str) -> str | None:
    """HEAD SHA of the repo providing the entry-point surfaces (`repo_root`,
    which `--repo-root` lets a caller point at a target repo other than
    claude-klabauter's own checkout). Feeds the PRIMARY staleness rule. Returns None
    (fail-safe: treats every record as stale) if git is unavailable or the
    repo has no commits yet.

    Review: code-reviewer P3 — `coordinator_core.win_portability` must be
    imported off THIS script's own location (`_repo_root()`), never off
    `repo_root`: `repo_root` is the TARGET repo being probed, not necessarily
    claude-klabauter's own checkout, so inserting it onto sys.path only resolved the
    import by coincidence when the target happened to be claude-klabauter itself. For
    any other `--repo-root` target the import raised ImportError, was
    swallowed by the except clause below, and silently returned None —
    marking every staleness record stale.
    """
    try:
        own_root = _repo_root()
        if own_root not in sys.path:
            sys.path.insert(0, own_root)
        from coordinator_core.win_portability import no_console_creationflags

        proc = subprocess.run(
            ["git", "-C", repo_root, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            **no_console_creationflags(),
        )
    except (OSError, subprocess.SubprocessError, ImportError):
        return None
    if proc.returncode != 0:
        return None
    sha = proc.stdout.strip()
    return sha or None


def entry_point_surfaces(manifest: dict) -> set[str]:
    """Surface names counted as manifest-declared ENTRY POINTS — compared against
    the manifest's own top-level key names (`standalone_setup_script`,
    `programmatic_entry_point`), not free-form script paths, since those two keys
    are exactly what point 4 defines as the install entry point (see module
    docstring § ENTRY-POINT SCOPE). Ceremony-hot-path surfaces (C5's KR-2 reader)
    are deliberately excluded — same record store, disjoint surface set."""
    names: set[str] = set()
    if manifest.get("standalone_setup_script"):
        names.add("standalone_setup_script")
    if manifest.get("programmatic_entry_point"):
        names.add("programmatic_entry_point")
    return names


def _load_record(path: str) -> dict | None:
    """Parse one platform-outcome YAML record. Returns None (skip, don't crash)
    on any parse failure or schema-shape mismatch — a malformed record must never
    take down the generator run."""
    if yaml is None:
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(data, dict):
        return None
    if any(field not in data for field in REQUIRED_RECORD_FIELDS):
        return None
    if data.get("platform") not in {"macos", "linux", "windows"}:
        return None
    if data.get("outcome") not in {"pass", "fail"}:
        return None
    return data


def _is_stale(record: dict, current_sha: str | None, now: datetime) -> bool:
    """PRIMARY: surface_sha mismatch against `current_sha`. SECONDARY: observed_at
    more than PLATFORM_OUTCOME_STALENESS_DAYS calendar days before `now`. Either
    condition alone makes the record stale (platform-outcome.schema.json's
    schema-level rule — both are independently checked, neither alone suffices
    as a freshness proof, but either alone suffices to invalidate)."""
    if current_sha is not None and record.get("surface_sha") != current_sha:
        return True
    observed_raw = record.get("observed_at")
    try:
        observed = datetime.fromisoformat(str(observed_raw).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return True  # unparsable timestamp -> fail closed, treat as stale
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    if now - observed > timedelta(days=PLATFORM_OUTCOME_STALENESS_DAYS):
        return True
    return False


def iter_record_paths(records_root: str):
    """Yield every state/platform-outcomes/<platform>/<machine>/<surface>.yaml
    path on disk, in deterministic (sorted) order. Silent (yields nothing) if
    the records root doesn't exist yet — that is the expected state before any
    canary has run."""
    if not os.path.isdir(records_root):
        return
    for platform_name in sorted(os.listdir(records_root)):
        platform_dir = os.path.join(records_root, platform_name)
        if not os.path.isdir(platform_dir):
            continue
        for machine_name in sorted(os.listdir(platform_dir)):
            machine_dir = os.path.join(platform_dir, machine_name)
            if not os.path.isdir(machine_dir):
                continue
            for fname in sorted(os.listdir(machine_dir)):
                if fname.endswith((".yaml", ".yml")):
                    yield os.path.join(machine_dir, fname)


def _sort_platforms(platforms) -> list[str]:
    """Canonical PLATFORM_ENUM_ORDER first, then any unrecognized value
    alphabetically appended (defensive — schema-valid input never hits this)."""
    known = [p for p in PLATFORM_ENUM_ORDER if p in platforms]
    unknown = sorted(p for p in platforms if p not in PLATFORM_ENUM_ORDER)
    return known + unknown


def derive_tested_platforms(
    records_root: str,
    manifest: dict,
    current_sha: str | None,
    now: datetime | None = None,
) -> tuple[list[str], list[str]]:
    """Pure derivation (no I/O beyond the records-root walk) — returns
    (derived_tested_platforms_sorted, advisory_lines).

    Promotion: a platform is included iff it has >=1 PASSING, non-stale record
    whose `surface` is a manifest-declared entry point.

    Grandfather: a platform already present in manifest['tested_platforms'] that
    has ZERO entry-point-surface records at all (pass or fail, fresh or stale —
    no evidence exists yet either way) is preserved with an advisory. A platform
    with entry-point records that fail or are all stale is NOT grandfathered —
    that is a legitimate demotion, records exist and don't currently support the
    claim.
    """
    surfaces = entry_point_surfaces(manifest)
    existing = list(manifest.get("tested_platforms") or [])
    now = now or datetime.now(timezone.utc)

    seen_entry_platforms: set[str] = set()  # has >=1 entry-point-surface record at all
    passing_platforms: set[str] = set()

    for path in iter_record_paths(records_root):
        record = _load_record(path)
        if record is None:
            continue
        if record.get("surface") not in surfaces:
            continue  # not an entry-point surface -> not backing evidence for tested_platforms
        platform = record["platform"]
        seen_entry_platforms.add(platform)
        if record.get("outcome") == "pass" and not _is_stale(record, current_sha, now):
            passing_platforms.add(platform)

    derived = set(passing_platforms)
    advisories: list[str] = []
    for platform in existing:
        if platform in passing_platforms:
            continue
        if platform not in seen_entry_platforms:
            derived.add(platform)
            advisories.append(f"grandfathered: {platform} has no backing records")
        # else: platform has entry-point records but none currently pass/fresh
        # -> legitimate demotion, not added, no advisory (this is the intended
        # "failing/stale record removes the claim" behavior).

    return _sort_platforms(derived), advisories


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Derive tested_platforms from state/platform-outcomes/ records "
        "(dry-run by default; --write to update agent-install-manifest.json)."
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write the derived value into agent-install-manifest.json. Omit for dry-run.",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Override the repo root (default: derived from this script's own location).",
    )
    args = parser.parse_args(argv)

    repo_root = args.repo_root or _repo_root()
    try:
        manifest_path = _manifest_path(repo_root)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    records_root = _records_root(repo_root)

    try:
        with open(manifest_path, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"ERROR: cannot read manifest at {manifest_path}: {exc}", file=sys.stderr)
        return 1

    if yaml is None:
        print(
            "ERROR: PyYAML is required to parse platform-outcome records "
            "(pip install pyyaml).",
            file=sys.stderr,
        )
        return 1

    current_sha = _current_repo_sha(repo_root)
    derived, advisories = derive_tested_platforms(records_root, manifest, current_sha)

    for line in advisories:
        print(line)
    print("tested_platforms (derived): " + json.dumps(derived))

    if not args.write:
        print("(dry-run — pass --write to update agent-install-manifest.json)")
        return 0

    if manifest.get("tested_platforms") == derived:
        print(f"{manifest_path} already up to date; nothing written.")
        return 0

    manifest["tested_platforms"] = derived
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")
    print(f"wrote tested_platforms to {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
