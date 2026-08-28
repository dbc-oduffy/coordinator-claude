"""
coordinator-install.py — CLI trampoline over claude-klabauter
coordinator_core.install.coordinator_install_entry.main.

Purpose: the discoverable install entry an agent finds when it greps
``install`` in ``<settings-home>/bin/``. Before this existed that grep
returned five diagnostics and ``coordinator-uninstall`` — the destructive
inverse of what was asked for, under a name that reads correct. See the
module docstring in coordinator_core.install.coordinator_install_entry for
the full why, what it dispatches, and why it reads the manifest instead of
naming a path.

This file is a thin trampoline: resolve the engine root, import, forward argv,
forward exit code — matching coordinator-uninstall.py's shape, its closest
sibling in both naming and lifecycle.

Fail-loud-on-ambiguity: if the engine root cannot be resolved or the claude-klabauter
module is not importable, exit 1 rather than 0 — a silent no-op here would
leave an operator believing the chain was installed when nothing ran, which
is the same wrong-answer failure the entry exists to prevent.

NEGATIVE SPEC: exit 96 from the dispatched installer is a DESIGNED REFUSAL
(an interpreter this installer will not override, e.g. PEP 668
externally-managed), not a failure. It is forwarded verbatim like any other
code. Never remap it onto 1, and never wrap it in text implying breakage —
text that reads as a break trains operators to route around the guard.

Entry placement: no edit to coordinator/lib/bin-templates-manifest.py is
needed or wanted. That manifest classifies DoE-owned templates/bin/
artifacts; this CLI is picked up by substrate's dynamic agent-helper
forwarder derivation off claude-klabauter's own coordinator/bin/ listing, which is
what keeps the entry claude-klabauter-generated and out of DoE's tree.

Spec backlink: cross-repo/inbox/2026-08-17-doe-claude-em-install-entrypoint-what-we-need-from-you.md § 4a
Shape ruling:  cross-repo/inbox/2026-08-17-doe-claude-em-coordinator-install-entry-resolve-from-manifest.md § Question 1
"""

from __future__ import annotations

import os
import sys


def _import_main():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.install.coordinator_install_entry import main as _op_main
    return _op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"coordinator-install.py: engine-root resolution failed: {exc}", file=sys.stderr)
        return 1
    except ImportError as exc:
        print(
            f"coordinator-install.py: coordinator_core.install.coordinator_install_entry "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        return 1
    return op_main((sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
