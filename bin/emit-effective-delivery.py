#!/usr/bin/env python3
"""emit-effective-delivery -- regenerate the `x-effective-delivery` manifest
block that `coordinator_core.ops.session.hook_delivery_manifest` and
`guard_settings_integrity.detect_hook_delivery_duplication` read at boot.

The generator itself is `coordinator_core.ops.session.emit_effective_delivery`;
this file is only its warm-door entrypoint. Print mode by default; `--write`
writes `<doe content root>/hooks/effective-delivery.json`. Run it after a
change to DoE's `hooks/hooks.json`.

Negative-spec: not a hook and never wired as one -- it is a build-time
generator an operator or ceremony runs on demand.
"""
from __future__ import annotations

import sys
from typing import List, Optional


def main(argv: Optional[List[str]] = None) -> int:
    try:
        import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
        from cc_invoke import require_dispatch_engine_on_path

        require_dispatch_engine_on_path()
        from coordinator_core.ops.session import emit_effective_delivery
    except (RuntimeError, ImportError) as exc:
        sys.stderr.write("emit-effective-delivery: engine unreachable (%s)\n" % exc)
        return 2
    return emit_effective_delivery.main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
