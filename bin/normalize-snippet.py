"""
normalize-snippet — CLI trampoline over claude-klabauter coordinator_core.text.normalize_snippet.

Reads a snippet body on stdin, strips leading/trailing blank lines and
per-line trailing whitespace (byte-parity port of the retired
normalize-snippet.sh::normalize() awk/sed pipeline — Port of: DoE 67202df6,
2026-07-16), and
writes the result to stdout with NO trailing newline (matches the original
`printf '%s' "$1"` semantics — callers that need a newline append one
themselves).

Shebang note: the SHEBANG line above is `#!/usr/bin/env python3`, and correct
for this shape. On Windows, this file's co-located `.cmd` twin wins via
`PATHEXT` when invoked as a bareword, so the shebang is never read there; on
macOS/Linux `python3` is the right interpreter. Caution: callers must invoke
via the extensionless name or a resolved-interpreter prefix, never a bareword
`.py` through git-bash — git-bash DOES honor the shebang and would exec-127
with no `python3` present. See the carve-out in the coordinator doctrine repo's
coordinator/docs/wiki/bash-on-windows-gotchas.md § Carve-out (cross-repo —
this wiki lives in the coordinator doctrine repo, not here).

Usage (stdin, not argv — avoids arg-length limits and quoting hazards on
multi-line/special-char snippets that argv would mangle):
  printf '%s' "$x" | normalize-snippet

Spec backlink: scratch/subagent-sandbox/bash-to-python-engine-migration/recipe-normalize-snippet.md § 5
"""
from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_normalize_snippet():
    """Resolve the engine root, put it on sys.path, and import the ported function.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.text.normalize_snippet import normalize_snippet

    return normalize_snippet


def main() -> None:
    if "--help" in sys.argv[1:] or "-h" in sys.argv[1:]:
        sys.stdout.write(__doc__ or "")
        sys.exit(0)

    text = sys.stdin.read()
    if not text:
        # No piped stdin content: this is the bare/no-input invocation, not a
        # legitimate empty-snippet normalize call. Fail loud on stderr rather
        # than silently succeeding with empty output on exit 0 — a quiet
        # success here previously read as "checked, clean" to an operator or
        # agent that forgot to pipe anything in.
        sys.stderr.write(__doc__ or "")
        sys.exit(1)

    try:
        normalize_snippet = _import_normalize_snippet()
    except RuntimeError as exc:
        print(f"normalize-snippet: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except ImportError as exc:
        print(
            f"normalize-snippet: coordinator_core.text.normalize_snippet not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    result = normalize_snippet(text)
    sys.stdout.write(result)


if __name__ == "__main__":
    main()
