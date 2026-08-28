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
import sys

GENERATES = [
    {
        "artifact": "docs/install/agent-install-manifest.json",
        "stamp_key": "tested_platforms",
        "sources": ["coordinator/bin/generate-tested-platforms.py"],
    },
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


def main(argv: list[str] | None = None) -> int:
    # Record/derivation core lives in coordinator_core.ops.platform_outcome_records
    # (extracted verbatim, byte-for-byte behavior-equivalent — see that module's
    # docstring for the two-consumer rationale: this generator, and
    # coordinator_core.ops.validate_install_contract._check_point4). Import off
    # THIS script's own on-disk location (_repo_root()), never off a
    # caller-supplied --repo-root target — see _current_repo_sha's own historical
    # review note, now moot since this import happens at module load time here.
    _own_root = _repo_root()
    if _own_root not in sys.path:
        sys.path.insert(0, _own_root)

    from coordinator_core.ops.platform_outcome_records import (
        PLATFORM_ENUM_ORDER,
        PLATFORM_OUTCOME_STALENESS_DAYS,
        REQUIRED_RECORD_FIELDS,
        current_repo_sha as _current_repo_sha,
        derive_tested_platforms,
        entry_point_surfaces,
        is_stale as _is_stale,
        iter_record_paths,
        load_record as _load_record,
        records_root as _records_root,
        yaml,
    )

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
    # DR-276: this CLI owns its own main() and writes the manifest directly
    # (no separate op `main(argv)` to route through `run_op_main` -- the
    # imports above are library helpers, not an op entrypoint), so the write
    # is wrapped in `recording_declared_writes()` with an explicit
    # `declare_write()` call at the write site, per cli_entry's documented
    # carve-out for CLIs that own their own body (see gen-launcher-shim.py's
    # `generate()`/`main()` for the same shape).
    from coordinator_core.cli_entry import recording_declared_writes
    from coordinator_core.session.declared_writes import declare_write

    with recording_declared_writes():
        with open(manifest_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(manifest, fh, indent=2)
            fh.write("\n")
        declare_write(manifest_path)
    print(f"wrote tested_platforms to {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
