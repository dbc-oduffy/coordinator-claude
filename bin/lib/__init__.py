"""coordinator/bin/lib — the single sys.path bootstrap for the bin CLIs.

Purpose: this package's import is the ONE place `coordinator/bin/lib` is put on
`sys.path`. Every bin CLI used to carry its own three-line preamble
(`_LIB_DIR = ...` / `if _LIB_DIR not in sys.path` / `sys.path.insert(0, ...)`),
which made 273 entrypoint module bodies impure at import — mutating interpreter
global state inside the warm server that ~50 concurrent sessions share. That is
the hazard AC20 forbids and the (b) warm-loadable axis exists to exclude.

The mutation cannot be removed outright: 17 modules in this package import their
siblings by bare name (`cc_invoke` imports `engine_bootstrap`, and so on), so the
directory must be importable by bare name for those to resolve. Centralising it
here trades 273 scattered mutations for one, executed once per process, in a file
whose whole job is to declare it.

Negative-spec: a bin CLI must NOT reintroduce its own sys.path preamble. Import
`lib.<module>` and let this run. The CLI path resolves `lib` because a script's
own directory is `sys.path[0]`; the warm path resolves it because
`coordinator_core/ops/invoke_from_argv.py` puts the bin directory on `sys.path`
once, before loading any entrypoint.
"""

import os
import sys

_SELF = os.path.dirname(os.path.abspath(__file__))
if _SELF not in sys.path:
    sys.path.insert(0, _SELF)
