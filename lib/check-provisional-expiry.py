#!/usr/bin/env python3
"""check-provisional-expiry.py — outstanding provisional-decision detector.

Purpose: scans docs/plans/*.md frontmatter for a `provisional_until:` /
`revisit_by:` date (see coordinator/schemas/plan.schema.json and
coordinator/docs/wiki/doctrine-authoring/provisional-decision-expiry.md) and surfaces any whose
date has passed while the owning plan is still in a non-terminal `status:`.

This is the artifact D1b exists to build — the class it catches is an
unexecuted STAGED DECISION sitting in a plan/spec (a ratification, a second
rollout stage, a park-note hold), not an unactioned reconciler candidate
(D1's job — a distinct class, see that wiki's own scope note). No threshold,
no baseline data: a fixed field-presence-and-date check.

DoE-side only, no claude-klabauter engine involvement — frontmatter keys are read
through the stdlib helper frontmatter_scan (deliberately NOT a full YAML
parse, so this has no PyYAML dependency and no claude-klabauter import).

Negative-spec:
    - Does NOT parse full YAML frontmatter — reads column-zero `key: value`
      scalar lines only, via frontmatter_scan.
    - Does NOT cross-reference commits or handoffs (unlike draft-plan-aging's
      liveness discriminator) — a provisional_until/revisit_by date is a
      hard, human-authored commitment; its expiry is unconditional on git
      activity, not gated on it.
    - Does NOT auto-clear or mutate the plan — detect-and-surface only, per
      the DR-090 "skills name ops, not procedures" boundary: this script IS
      the op the ceremony step names.

Exit codes:
  0 — no expired provisional decisions found
  1 — one or more expired provisional decisions found (fail loud)
  2 — internal error (missing path, unparseable date)

Spec backlink: docs/plans/2026-07-26-push-side-write-discipline.md § D1b
"""
from __future__ import annotations

import datetime
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from frontmatter_scan import read_text, scan_frontmatter  # noqa: E402

# Question answered (C8b, 2026-07-27, plan-line-item-resolution-model): "is
# this plan no longer actively being executed, so an expired
# provisional_until/revisit_by date inside it is not worth chasing?" This is
# NOT the same partition as claude-klabauter's several plan-status "terminal"-
# named sets, and is not expected to agree with any of them:
#   - lifecycle_constants.PLAN_ARCHIVABLE_STATUS answers "can this plan's
#     file be git-mv'd into archive/?" — excludes 'deferred' (a deferred plan
#     stays in docs/plans/, revisitable), while THIS set includes it (a
#     deferred plan's staged decisions are deliberately parked, not chased).
#   - ops.plan_status_transition._FROZEN_STATUSES answers "is this status
#     frozen against the stamp-implemented flip?" — happens to agree with
#     this set's membership today, but for an unrelated reason (flippability,
#     not decision-chaseability); do not assume future agreement.
#   - ops.records_query.liveness()'s plan branch answers "what LIVE/BLOCKED/
#     DONE cockpit bucket does this status fall into?" — maps 'deferred' to
#     BLOCKED, a third bucket, not folded into this binary set at all.
# Renamed (2026-07-27) from `_TERMINAL_STATUSES` to state the question this
# set actually answers, now that coordinator/tests/test_plan_status_enum_parity.py
# reads this value via a real module loader (importlib.util.spec_from_file_location)
# instead of regex-matching the old literal name — the rename no longer
# silently breaks that test's parity check. See that test module's docstring
# (AC-doe-2) for the loader approach.
_NOT_ACTIVELY_EXECUTING_STATUSES = {"implemented", "deferred", "abandoned", "superseded"}

_FRONTMATTER_KEYS = ("status", "provisional_until", "revisit_by")


def _read_frontmatter_scalars(path: str) -> dict:
    """Return the non-empty string values of _FRONTMATTER_KEYS from the
    column-zero frontmatter keys. An unreadable file raises ValueError; a
    silent empty read would report an unreadable plan as "not expired"."""
    text = read_text(path)
    if text is None:
        raise ValueError(f"cannot read {path}")
    return {
        key: value
        for key, value in scan_frontmatter(text).items()
        if key in _FRONTMATTER_KEYS and isinstance(value, str) and value
    }


def _parse_date(value: str, path: str) -> datetime.date:
    try:
        return datetime.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{path}: unparseable date {value!r}") from exc


def find_expired(paths, today: datetime.date | None = None):
    """Return a list of (path, expiry_date, days_overdue, status) tuples for
    every plan whose provisional_until/revisit_by date has passed while its
    status is still non-terminal. Raises ValueError on an unparseable date
    (caller maps to exit code 2)."""
    if today is None:
        # Resolve in UTC, matching the sibling ceremony's `date -u` day
        # resolution, to avoid a machine-timezone disagreement across a day
        # boundary.
        today = datetime.datetime.now(datetime.timezone.utc).date()

    expired = []
    for path in sorted(paths):
        scalars = _read_frontmatter_scalars(path)
        provisional_until = scalars.get("provisional_until")
        revisit_by = scalars.get("revisit_by")
        if provisional_until and revisit_by:
            raise ValueError(
                f"{path}: sets both provisional_until and revisit_by — "
                "a plan carries at most one of the two synonym keys"
            )
        raw_date = provisional_until or revisit_by
        if not raw_date:
            continue
        status = scalars.get("status", "")
        if status in _NOT_ACTIVELY_EXECUTING_STATUSES:
            continue
        expiry = _parse_date(raw_date, path)
        if expiry <= today:
            days_overdue = (today - expiry).days
            expired.append((path, expiry, days_overdue, status))
    return expired


def _resolve_targets(argv):
    # No argv-less cwd-relative default: a silent empty-glob no-op on the
    # wrong cwd would be indistinguishable from "nothing expired", which
    # contradicts this script's fail-loud negative-spec.
    if not argv:
        raise ValueError("no target path given (expected a file or directory argument)")
    target = argv[0]
    if os.path.isdir(target):
        return sorted(glob.glob(os.path.join(target, "*.md")))
    return [target]


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        targets = _resolve_targets(argv)
        if not targets:
            return 0
        for t in targets:
            if not os.path.exists(t):
                print(f"check-provisional-expiry: no such path: {t}", file=sys.stderr)
                return 2
        expired = find_expired(targets)
    except ValueError as exc:
        print(f"check-provisional-expiry: {exc}", file=sys.stderr)
        return 2

    if not expired:
        return 0

    for path, expiry, days_overdue, status in expired:
        print(
            f"EXPIRED: {path} (provisional_until/revisit_by: {expiry.isoformat()}, "
            f"{days_overdue}d overdue, status: {status})"
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
