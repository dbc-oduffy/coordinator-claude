"""baseline-export -- export a commit, run a runner in it, remove the export in a finally.

Direct-import trampoline over coordinator_core.testing.baseline_export.main:

  baseline-export --sha <sha> [--link <repo-relative-path>]... -- <runner argv...>

Exit status: 0 ran, 2 usage, 3 export failed or engine unresolvable, 4 removal failed.
"""

from __future__ import annotations

import json
import sys


def _load_main():
    import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import _resolve_engine_root

    root = _resolve_engine_root()
    if root not in sys.path:
        sys.path.insert(0, root)
    from coordinator_core.testing import baseline_export

    return baseline_export.main


def _sha_arg(argv: list[str]) -> str:
    for i, tok in enumerate(argv):
        if tok == "--":
            break
        if tok == "--sha" and i + 1 < len(argv):
            return argv[i + 1]
    return ""


def main(argv: list[str]) -> int:
    try:
        engine_main = _load_main()
    except (RuntimeError, ImportError) as exc:
        print(f"baseline-export: engine unavailable: {exc}", file=sys.stderr)
        print(json.dumps({"baseline_export": {
            "sha": _sha_arg(argv),
            "export": "failed",
            "why": f"engine unavailable: {exc}",
            "runner_exit": None,
            "removed": True,
        }}))
        return 3
    return engine_main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
