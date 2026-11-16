#!/usr/bin/env python3
"""Write a deterministic N-lesson queue under a repo's state/lessons for tests and the bench.

The mix is seeded: duplicates, covered rules (verbatim in an index-reachable wiki page the
generator also writes), universals (domain-tagged and untagged), malformed rows, aged rows and
genuine residue. The same --seed and --count always write byte-identical files.
Usage: make_lesson_queue.py --repo <dir> [--count 148] [--seed 7]
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

ANCHOR_DATE = date(2026, 11, 16)
DOMAIN_TAGS = ("ue", "game-dev", "web-dev", "data-science")
WIKI_DIR = "coordinator/docs/wiki/lesson-triage"
COVERED_PAGE = f"{WIKI_DIR}/fixture-covered-rules.md"
# category -> share of the queue; residue takes the remainder so the counts always sum to N.
SHARES = (
    ("duplicate", 0.12),
    ("covered", 0.10),
    ("universal_tagged", 0.06),
    ("universal_untagged", 0.06),
    ("malformed", 0.06),
    ("aged", 0.10),
)
CATEGORIES = tuple(name for name, _ in SHARES) + ("residue",)
VERBS = ("pin", "gate", "stamp", "route", "split", "cache", "probe", "fence")
NOUNS = ("journal", "manifest", "sidecar", "queue row", "index", "checkpoint", "payload", "ledger")


def category_counts(count: int) -> dict[str, int]:
    """Split `count` rows across the categories; residue absorbs the rounding remainder."""
    counts = {name: int(count * share) for name, share in SHARES}
    counts["residue"] = count - sum(counts.values())
    return counts


def _rule(rng: random.Random, serial: int) -> str:
    """A unique one-paragraph rule body; the serial keeps every normalized body distinct."""
    return (
        f"Lesson {serial:04d}: always {rng.choice(VERBS)} the {rng.choice(NOUNS)} before the "
        f"{rng.choice(NOUNS)} is read, because rule {serial:04d} was violated in run "
        f"{rng.randrange(1000, 9999)}."
    )


def _yaml_scalar(text: str) -> str:
    return json.dumps(text, ensure_ascii=True)


def render(fields: dict) -> str:
    """Render one lesson row as YAML; absent keys are omitted so a malformed row stays malformed."""
    lines = []
    for key in ("created", "title"):
        if key in fields:
            lines.append(f"{key}: {fields[key]}" if key == "created" else f"{key}: {_yaml_scalar(fields[key])}")
    lines.append("body: |-")
    lines.extend(f"  {ln}" for ln in fields["body"].splitlines())
    for key in ("status", "scope", "from_repo"):
        if key in fields:
            lines.append(f"{key}: {fields[key]}")
    if fields.get("proposed_target"):
        lines.append(f"proposed_target: {fields['proposed_target']}")
    if fields.get("tags"):
        lines.append("tags:")
        lines.extend(f"  - {t}" for t in fields["tags"])
    return "\n".join(lines) + "\n"


def generate(repo: Path, count: int = 148, seed: int = 7) -> dict:
    """Write `count` lessons under repo/state/lessons plus the wiki page covered rows cite.

    Returns {"count", "seed", "categories": {name: n}, "files": {category: [stem, ...]}}.
    """
    if count < 1:
        raise ValueError("count must be >= 1")
    rng = random.Random(seed)
    counts = category_counts(count)
    lessons = repo / "state" / "lessons"
    lessons.mkdir(parents=True, exist_ok=True)
    files: dict[str, list[str]] = {name: [] for name in CATEGORIES}
    serial = 0
    covered_bodies: list[str] = []

    def emit(category: str, fields: dict) -> None:
        nonlocal serial
        serial += 1
        stem = f"2026-11-{1 + serial % 14:02d}-{category.replace('_', '-')}-{serial:04d}"
        (lessons / f"{stem}.yaml").write_text(render(fields), encoding="utf-8", newline="\n")
        files[category].append(stem)

    def base(body: str, age_days: int = 3) -> dict:
        created = ANCHOR_DATE - timedelta(days=age_days + rng.randrange(0, 3))
        return {
            "created": created.isoformat(), "title": body.split(":")[0].lower().replace(" ", "-"),
            "body": body, "status": "open", "scope": "project", "from_repo": "fixture-repo",
        }

    residue_pool: list[str] = []
    for _ in range(counts["residue"]):
        serial += 1
        residue_pool.append(_rule(rng, serial))
    serial = 0
    for body in residue_pool:
        emit("residue", base(body))
    for i in range(counts["duplicate"]):
        # Same normalized body as a residue row but younger, so dedupe keeps the older survivor.
        body = residue_pool[i % len(residue_pool)]
        survivor = base(body, age_days=0)
        emit("duplicate", {**survivor, "body": body.upper() if rng.random() < 0.5 else body.replace(" ", "  ")})
    for _ in range(counts["covered"]):
        body = _rule(rng, serial + 1000)
        covered_bodies.append(body)
        emit("covered", {**base(body), "proposed_target": COVERED_PAGE})
    for i in range(counts["universal_tagged"]):
        emit("universal_tagged", {**base(_rule(rng, serial + 2000)), "scope": "universal",
                                  "tags": [DOMAIN_TAGS[i % len(DOMAIN_TAGS)]]})
    for _ in range(counts["universal_untagged"]):
        emit("universal_untagged", {**base(_rule(rng, serial + 3000)), "scope": "universal"})
    for i in range(counts["malformed"]):
        row = base(_rule(rng, serial + 4000))
        del row[("status", "scope", "from_repo")[i % 3]]
        emit("malformed", row)
    for _ in range(counts["aged"]):
        emit("aged", base(_rule(rng, serial + 5000), age_days=120 + rng.randrange(0, 60)))

    wiki = repo / WIKI_DIR
    wiki.mkdir(parents=True, exist_ok=True)
    page = "# Fixture covered rules\n\n" + "\n\n".join(covered_bodies) + "\n"
    (wiki / "fixture-covered-rules.md").write_text(page, encoding="utf-8", newline="\n")
    (wiki / "_index.md").write_text(
        "# lesson-triage index\n\n- [fixture-covered-rules](fixture-covered-rules.md)\n",
        encoding="utf-8", newline="\n")
    return {"count": count, "seed": seed, "categories": counts, "files": files}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", required=True, help="repo root; lessons land in <repo>/state/lessons")
    ap.add_argument("--count", type=int, default=148)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args(argv)
    result = generate(Path(args.repo), args.count, args.seed)
    print(json.dumps({k: result[k] for k in ("count", "seed", "categories")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
