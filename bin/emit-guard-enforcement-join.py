#!/usr/bin/env python3
"""Fold the four guard-enforcement join shards into the single artifact
`DoE-claude` reads to decide whether a doctrine rule is enforced here.

WHAT THIS IS THE OTHER HALF OF
    `DoE-claude docs/decisions/DR-an-omission-is-ratified-by-the-plane-that-
    enforces-the-rule.md` makes omission authority follow enforcement: a
    story may omit a rule only when the plane that ENFORCES it has said the
    enforcement is absent. It closed with the decision taken and one thing
    outstanding -- "no file bridges an `rcr-<hash>` register id to an
    engine-plane guard verdict". This emits that file. The consuming half is
    `DoE-claude coordinator/hooks/scripts/_guard_enforcement_join.py`, whose
    module docstring is the schema contract; read it before changing the
    shape emitted here.

WHY COMPLETENESS IS THE ONLY FIELD THAT MATTERS
    `complete_over_guards` is what licenses a NEGATIVE. "Guard G enforces
    rule X" needs one row; "NO guard enforces rule X" needs every guard to
    have been asked. This emitter therefore refuses to write unless the
    shards' guard set equals the live registered population exactly, in both
    directions -- a missing guard would let its rules read as unenforced, and
    an extra one means a shard is describing something that is not
    registered.

THE TWO RULE LISTS, AND WHICH WAY CAUTION POINTS
    The join is read guard-first, so a rule named by NOBODY is the rule that
    becomes omittable. Dropping a doubtful id does not keep its rule present
    -- it makes the rule easier to omit. `uncertain_rule_ids` is where a
    plausible-but-unproven link goes: the consumer resolves those to
    UNRESOLVED rather than unenforced, so a guess costs presence instead of
    buying an omission.

Regenerate (from the repo root):

    python coordinator/bin/emit-guard-enforcement-join.py

Naked Python (3.11+), stdlib plus PyYAML. Dev-time tooling, not a
session-start path.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

import yaml

_BIN_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_BIN_DIR))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

SHARD_DIR = os.path.join(
    _REPO_ROOT, "state", "audits", "2026-09-07-guard-enforcement-join"
)
SHARD_NAMES = ("shard-a.yaml", "shard-b.yaml", "shard-c.yaml", "shard-d.yaml")
DEFAULT_OUTPUT = os.path.join(SHARD_DIR, "guard-enforcement-join.yaml")

GUARD_POPULATION = (
    "bash_guards.roster.guard_roster() + write_guards.engine.discover_guard_names()"
)


def live_guard_ids() -> "set[str]":
    from coordinator_core.bash_guards.roster import guard_roster
    from coordinator_core.write_guards.engine import discover_guard_names

    write_ids, errors = discover_guard_names()
    if errors:
        raise SystemExit(f"discover_guard_names() reported errors: {errors!r}")
    return {guard.id for guard in guard_roster()} | set(write_ids)


def read_shards() -> "list[dict]":
    rows: list[dict] = []
    for name in SHARD_NAMES:
        path = os.path.join(SHARD_DIR, name)
        with open(path, "r", encoding="utf-8") as handle:
            document = yaml.safe_load(handle)
        guards = (document or {}).get("guards")
        if not isinstance(guards, list) or not guards:
            raise SystemExit(f"{name}: no `guards` list")
        rows.extend(guards)
    return rows


def check_rows(rows: "list[dict]") -> None:
    """Every refusal here is a shape the consumer cannot tell apart from a
    legitimate answer, which is why they are refusals and not warnings."""
    seen: set[str] = set()
    for row in rows:
        guard_id = row.get("guard_id")
        if not guard_id:
            raise SystemExit("a shard row names no guard_id")
        if guard_id == "none":
            raise SystemExit("'none' is the consumer's reserved unenforced answer")
        if guard_id in seen:
            raise SystemExit(f"{guard_id}: appears in more than one shard")
        seen.add(guard_id)
        if not row.get("cloud_verdict"):
            raise SystemExit(f"{guard_id}: no cloud_verdict")
        for field in ("enforces_rule_ids", "uncertain_rule_ids"):
            if not isinstance(row.get(field), list):
                raise SystemExit(
                    f"{guard_id}: {field} must be a list, empty where there is nothing "
                    "-- an absent key reads as an unexamined guard"
                )


def source_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def build_document() -> dict:
    rows = read_shards()
    check_rows(rows)

    shard_ids = {row["guard_id"] for row in rows}
    live = live_guard_ids()
    missing = sorted(live - shard_ids)
    extra = sorted(shard_ids - live)
    if missing or extra:
        raise SystemExit(
            "the join does not cover the live registered guard population exactly, so "
            "no negative it produces would be sound.\n"
            f"  registered but absent from the shards: {missing}\n"
            f"  in the shards but not registered:      {extra}"
        )

    confident: set[str] = set()
    uncertain: set[str] = set()
    for row in rows:
        confident.update(row["enforces_rule_ids"])
        uncertain.update(row["uncertain_rule_ids"])

    return {
        "source_repo": "claude-klabauter",
        "source_sha": source_sha(),
        "guard_population": GUARD_POPULATION,
        "complete_over_guards": True,
        "counts": {
            "guards": len(rows),
            "guards_naming_at_least_one_rule": sum(
                1 for row in rows if row["enforces_rule_ids"]
            ),
            "distinct_confident_rule_ids": len(confident),
            "distinct_uncertain_rule_ids": len(uncertain),
            "ids_both_confident_and_uncertain": len(confident & uncertain),
        },
        "guards": rows,
    }


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="recompute and diff against the committed output; never write",
    )
    args = parser.parse_args(argv)

    document = build_document()
    rendered = yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=100)

    if args.check:
        try:
            with open(args.output, "r", encoding="utf-8") as handle:
                committed = handle.read()
        except OSError:
            print(f"{args.output} is absent", file=sys.stderr)
            return 1
        if committed != rendered:
            print(f"{args.output} is stale", file=sys.stderr)
            return 1
        print(f"{args.output} is up to date")
        return 0

    with open(args.output, "w", encoding="utf-8") as handle:
        handle.write(rendered)
    print(f"wrote {args.output}")
    for key, value in document["counts"].items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
