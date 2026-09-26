#     the named handoff/spinoff artifact. READ-ONLY — mutates nothing.
#     artifact-path is OPTIONAL for kind=handoff (2026-07-28): when omitted,
#     dispatch table (coordinator_core.contract.apply_base). MUTATING.
#     artifact-path is OPTIONAL for kind=handoff on the SAME terms as brief

from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from entry_point_shim import run_target

    return run_target("baton-assemble", argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
