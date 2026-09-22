#!/usr/bin/env python3
"""check-doctrine-status -- exit non-zero the moment a wiki page's `status:`
value falls outside the closed vocabulary.

WHY THIS EXISTS. A `contract/doctrine-status-vocabulary.json` closes the
`status:` frontmatter field to a fixed vocabulary after DoE-claude's C1
repair. Nothing previously branched on the field -- a ninth spelling could
land tomorrow and nothing would notice. This is that branch.

SILENT ON ABSENCE, ALWAYS. Three page classes produce no output of any
severity: a page with no frontmatter, a page with frontmatter but no
`status:` key, and a page whose value is listed in the contract. Only a
page carrying a `status:` key with an unlisted value is a violation --
this is the frontmatter-backfill rejection
(DoE-claude docs/plans/2026-08-30-doctrine-governance-tier-2.md Anti-scope),
enforced mechanically rather than left as a convention.

Multi-OS is P0: every path goes through `pathlib`, no separator literals,
no shell is invoked.

PATH RESOLUTION -- ENGINE + SESSION REPO. `coordinator_core.doctrine_status`
resolves `WIKI_ROOT`/`CONTRACT_PATH` from the caller's own repo root, walked up
from cwd (`docs/plans/2026-09-18-doe-holds-no-scripts.md` § Path resolution) --
never from this CLI's own `__file__` chain, which would point at the ENGINE's
checkout rather than whichever repo's doctrine corpus is under test.
`--wiki-root`/`--contract` override either default explicitly.

Negative-spec: no staleness, no second unrelated function sharing this
walk, no cache/index/database written anywhere -- one pass over the corpus
per invocation, nothing persisted between runs.

Exit codes:
  0 -- no page carries a `status:` value outside the contract (including
       the corpus having no violations at all).
  1 -- at least one page carries an unlisted `status:` value; each is
       printed to stdout as `<path>: <value>`.
  2 -- the contract file or the wiki root is unusable (missing, malformed,
       or contract-shaped wrong: no `vocabulary` key, or a non-list-of-
       strings value); or a wiki page could not be read as valid UTF-8
       (path printed to stderr).

Spec: DoE-claude docs/plans/2026-08-30-doctrine-governance-tier-2.md, chunk C2.
docs/plans/2026-09-18-doe-holds-no-scripts.md, chunk W3-C2.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load_doctrine_status():
    """Engine imports happen here, inside a function, never at module scope --
    keeps the module body pure so `serve_classifier` still classifies this file
    warm-servable (the same bootstrap every engine-resident CLI in this directory uses)."""
    import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
    import cc_invoke

    cc_invoke.require_engine_on_path(__file__)
    from coordinator_core import doctrine_status as ds

    return ds


def main(argv: "list[str] | None" = None) -> int:
    ds = _load_doctrine_status()
    parser = argparse.ArgumentParser(
        prog="check-doctrine-status",
        description=(
            "Exit non-zero the moment a coordinator/docs/wiki/ page's `status:` "
            "value falls outside the closed vocabulary contract."
        ),
    )
    parser.add_argument(
        "--wiki-root",
        type=Path,
        default=None,
        help="wiki corpus root (default: coordinator/docs/wiki/ under the caller's repo)",
    )
    parser.add_argument(
        "--contract",
        type=Path,
        default=None,
        help="path to doctrine-status-vocabulary.json (default: coordinator/contract/…)",
    )
    args = parser.parse_args(argv)

    wiki_root = args.wiki_root or ds.WIKI_ROOT
    contract_path = args.contract or ds.CONTRACT_PATH

    if not contract_path.is_file():
        print(
            f"check-doctrine-status: no contract file at {contract_path}",
            file=sys.stderr,
        )
        return 2
    try:
        vocabulary = ds.load_vocabulary(contract_path)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"check-doctrine-status: malformed contract file: {exc}", file=sys.stderr)
        return 2

    if not wiki_root.is_dir():
        print(f"check-doctrine-status: no wiki root at {wiki_root}", file=sys.stderr)
        return 2

    violations = []
    for page in ds.iter_wiki_pages(wiki_root):
        try:
            finding = ds.check_page(page, vocabulary)
        except UnicodeDecodeError as exc:
            # An unreadable page must not collide
            # with exit 1 (unlisted status value); loud exit 2 naming the
            # file beats silently skipping a page the lint cannot check.
            try:
                rel = page.relative_to(ds.REPO_ROOT)
            except ValueError:
                rel = page
            print(
                f"check-doctrine-status: unreadable page (not valid UTF-8): "
                f"{rel.as_posix()}: {exc}",
                file=sys.stderr,
            )
            return 2
        if finding.is_violation:
            violations.append(finding)

    if not violations:
        return 0

    for finding in violations:
        try:
            rel = finding.path.relative_to(ds.REPO_ROOT)
        except ValueError:
            rel = finding.path
        print(f"{rel.as_posix()}: {finding.value}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
