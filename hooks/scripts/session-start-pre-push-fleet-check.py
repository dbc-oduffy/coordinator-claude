"""SessionStart report: a registered fleet repo whose pre-push hook runs a test runner or
unjustified git-lfs, or whose hook in an LFS repo never runs `git lfs pre-push`.

Rule token: PRE-PUSH-RUNS-NO-TESTS-AND-NO-LFS. The classification is
`_pre_push_policy.sweep` (file reads only, no `git` spawn); this stub relays
its violations as one short banner.

Runs on an author-profile box only, so the OSS payload imposes nothing on a
consumer's repos. Silent when the fleet is clean. Fails open: any exception
prints nothing and returns 0, because a SessionStart hook must never stand
between an operator and a session.

Negative-spec:
    Does NOT delete or rewrite any hook; the owning repo's EM removes it.
    Does NOT spawn `git` or `git lfs`.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

MAX_BANNER_CHARS = 600
TOKEN = "PRE-PUSH-RUNS-NO-TESTS-AND-NO-LFS"
_HEAD = "PRE-PUSH POLICY VIOLATION"
_REMEDY = (
    "Fix each finding as it says; tests run at merge to main, never at push. "
    + TOKEN
)


def build_banner(offenders: "list[tuple[str, str]]") -> str:
    """Compose the banner from (repo name, first reason) pairs, capped at MAX_BANNER_CHARS."""
    tail = "\n" + _REMEDY
    out = _HEAD + ":"
    shown = 0
    for name, reason in offenders:
        line = f"\n- {name}: {reason}"
        room = MAX_BANNER_CHARS - len(out) - len(tail) - len("\n(+99 more)")
        if len(line) > room:
            line = line[: max(room, 0)]
            if room > 0:
                out += line
                shown += 1
            break
        out += line
        shown += 1
    if shown < len(offenders):
        out += f"\n(+{len(offenders) - shown} more)"
    return (out + tail)[:MAX_BANNER_CHARS]


def main() -> int:
    try:
        import _machine_profile

        if not _machine_profile.is_author():
            return 0
        import _pre_push_policy

        offenders = []
        for v in _pre_push_policy.sweep():
            if v.status in ("violation", "unclassified"):
                reason = v.reasons[0] if v.reasons else v.status
                offenders.append((v.repo.name, reason))
        if not offenders:
            return 0
        banner = build_banner(offenders)
    except Exception:  # noqa: BLE001 -- fail open, see module docstring.
        return 0
    sys.stdout.buffer.write((banner + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
