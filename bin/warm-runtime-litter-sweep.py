"""warm-runtime-litter-sweep.py — one-shot removal of abandoned warm-engine
clone-key directories under the operator's real runtime base.

Spec backlink: state/handoffs/2026-08-20-warm-breadcrumbs-litter-the-operators-runtime-base.md

WHAT LEFT THE LITTER. `breadcrumb.svc_dir(engine_root)` resolves to
`<runtime base>/coordinator/warm/<sha1(engine_root)[:16]>`. Until the
`COORDINATOR_WARM_RUNTIME_BASE` seam landed, the warm test suite passed a
pytest `tmp_path` as `engine_root` believing that isolated it; it varied
only the clone-hash component, so every run minted a brand-new REAL
directory under the operator's `%LOCALAPPDATA%` and filled it with
breadcrumb and telemetry fixtures nothing ever removed. Measured on the
authoring box 2026-08-20: 1027 clone-key directories, 412 carrying a
`warm.json`, 192 a `telemetry.jsonl`, 244 holding obviously synthetic
fixture content, ~150KB total.

THIS SCRIPT IS THE SECOND HALF OF THE FIX, NEVER THE WHOLE OF IT. The
seam is what stops the litter returning; a sweeper alone deletes exactly
what the next suite run re-creates, and reads as a discharge while
discharging nothing. Run it only on a tree where the seam is present.

LIVENESS, NOT AGE, IS THE PREDICATE. A LIVE warm server's breadcrumb
lives in this same tree, and deleting it while that server runs
desynchronises every client from a running process: `should_spawn` reads
the missing breadcrumb as "no spawn in flight" so the debounce silently
stops debouncing, and `warm-engine-stop.py` — which identifies its target
solely from that file — reports "nothing to stop" for a server that is
still serving. So a directory is skipped whenever its breadcrumb names a
pid that `stable_pid_alive` still vouches for.

    `stable_pid_alive` takes THE PID, not the breadcrumb dict. Passing
    the record returns a spurious False, which is exactly the misread
    that produced a wrong "the warm server is dead" conclusion during the
    session that found this defect.

Conservative by construction, in the same register as its sibling
`warm-engine-stop.py`: anything this script cannot positively classify as
abandoned is KEPT. An unreadable directory, a psutil failure, a
breadcrumb whose pid it cannot evaluate — each keeps the directory and is
counted, never deleted on doubt. Reporting is the default; removal
requires an explicit `--apply`.

COLD-PATH RULE: runnable, never a slash command — naked argparse, no
session or agent surface imported.

Usage:
    python3 coordinator/bin/warm-runtime-litter-sweep.py            # report only
    python3 coordinator/bin/warm-runtime-litter-sweep.py --apply    # remove
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

from pathlib import Path

_EXIT_OK = 0
_EXIT_NO_BASE = 0
_EXIT_REMOVAL_FAILURES = 1

BREADCRUMB_FILENAME = "warm.json"


def _real_runtime_base() -> Path:
    """The operator's real base, resolved WITHOUT the test override.

    Deliberately does not import `warm.breadcrumb._runtime_base`: this
    script's whole job is to clean the REAL tree, and honouring the test
    seam here would let a stray env var point a deleting sweep at some
    other directory entirely.
    """
    local = os.environ.get("LOCALAPPDATA")
    base = Path(local) if local else Path.home() / ".cache"
    return base / "coordinator" / "warm"


def _read_breadcrumb(svc_dir: Path) -> dict | None:
    """The breadcrumb record, or None when absent, unreadable, or not a
    JSON object — mirroring `breadcrumb.read_breadcrumb`'s own
    never-raises contract."""
    try:
        text = (svc_dir / BREADCRUMB_FILENAME).read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        record = json.loads(text)
    except json.JSONDecodeError:
        return None
    return record if isinstance(record, dict) else None


def _names_a_live_server(record: dict | None) -> bool:
    """True iff this breadcrumb still vouches for a running process.

    Returns True on ANY uncertainty — an unresolvable pid, a missing
    psutil, an unexpected raise — because the cost of a false "dead" is
    deleting a live server's breadcrumb, and the cost of a false "alive"
    is one directory left on disk.
    """
    if record is None:
        return False
    pid = record.get("pid")
    if not isinstance(pid, int):
        return False

    stored_epoch = record.get("stable_pid_start_epoch")
    stored_epoch_str = str(stored_epoch) if stored_epoch is not None else ""

    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    try:
        require_dispatch_engine_on_path()
        from coordinator_core.session.core import stable_pid_alive
    except Exception:
        return True

    try:
        # THE PID, not the record — see module docstring.
        return bool(stable_pid_alive(pid, stored_start_epoch=stored_epoch_str))
    except Exception:
        return True


def _sweep(base: Path, *, apply: bool) -> tuple[int, int, int, list[str]]:
    removed = kept_live = kept_unreadable = 0
    failures: list[str] = []

    try:
        entries = sorted(entry for entry in base.iterdir() if entry.is_dir())
    except OSError as exc:
        return 0, 0, 0, [f"{base}: {exc}"]

    for entry in entries:
        record = _read_breadcrumb(entry)
        if record is not None and _names_a_live_server(record):
            kept_live += 1
            print(f"  keep (live pid {record.get('pid')}): {entry.name}")
            continue

        if not apply:
            removed += 1
            continue

        try:
            shutil.rmtree(entry)
            removed += 1
        except OSError as exc:
            kept_unreadable += 1
            failures.append(f"{entry.name}: {exc}")

    return removed, kept_live, kept_unreadable, failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually remove the abandoned directories (default: report only)",
    )
    args = parser.parse_args(argv)

    base = _real_runtime_base()
    if not base.is_dir():
        print(f"no warm runtime base at {base} — nothing to sweep")
        return _EXIT_NO_BASE

    print(f"warm runtime base: {base}")
    removed, kept_live, kept_unreadable, failures = _sweep(base, apply=args.apply)

    verb = "removed" if args.apply else "would remove"
    print(f"{verb}: {removed}")
    print(f"kept (live server breadcrumb): {kept_live}")
    if kept_unreadable:
        print(f"kept (removal failed): {kept_unreadable}")
    for failure in failures:
        print(f"  {failure}", file=sys.stderr)

    if not args.apply:
        print("dry run — re-run with --apply to remove")

    return _EXIT_REMOVAL_FAILURES if failures else _EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
