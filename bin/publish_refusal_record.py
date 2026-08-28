"""coordinator/bin/publish_refusal_record.py — the cheap capture, and only the
cheap capture, for a publish swap refused by a held Windows handle.

Spec backlink: state/dispatch-briefs/2026-08-19-a-refused-swap-names-what-
blocked-it/C1.md (plan: docs/plans/2026-08-19-a-refused-swap-names-what-
blocked-it.md, chunk C1).

WHY (2026-08-19 failure): a publish swap refused with a held handle, and the
only evidence was one session's transcript — this plan could not answer its
own "who held it" question because nothing durable recorded the refusal at
all. The wall-clock time of that failure is the single fact whose absence
forced the whole premise question, and it costs a dict and a file write. This
module writes exactly that: the refused path, the swap branch taken
(root-dest vs whole-tree), the failing operation (one of the six call sites
enumerated in `coordinator/bin/publish.py`), the round's own pid, and a UTC
timestamp.

NEGATIVE SPEC (deliberate narrowing, decided 2026-08-19 after the staff-eng
review — recorded here so the omission reads as a decision, not an
oversight): no Restart Manager arm, no `psutil` arm, no holder identification
of any kind in this round.

  - The only hypothesis the evidence still admits is a TRANSIENT append
    handle under the mirror's `state/`. A probe run after the exception
    unwinds finds a transient handle already gone.
  - For a PERSISTENT holder, this cheap record already answers the question
    one step later and for free: a persistent holder is by definition still
    holding when an operator runs Restart Manager by hand against the path
    this record names.
  - The `psutil` arm was measured WEAK: `Process.open_files()` failed on
    this box this session with `SystemExtendedHandleInformation buffer too
    big` under ordinary load — precisely the condition a failing publish
    round runs in.
  - Restart Manager is proven on this box, and is deferred not because it is
    unproven but because it answers a question this cheap record makes
    answerable anyway.

FOLLOW-ON, gated on evidence, not a date: when the first real record lands,
read it. If it names a path an operator can still find a holder for, the
manual Restart Manager run closes the question and no arm is ever built. If
the records show a refusal nobody can catch after the fact, THAT is the
trigger to build in-round identification. Do not pre-build it on the
strength of this plan.

COLD-PATH module (`docs/reference/interactive-launch-chain.md` cold-path
rule; guard: `coordinator/tests/test_cold_path_remediation_is_runnable.py`):
this can run out of a cron round with no agentic session to fix a failure,
so the operator-facing text below names a runnable command line, never a
slash command.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

#: `coordinator/bin/publish_refusal_record.py` -> `coordinator/bin` -> `coordinator` -> repo root.
_REPO_ROOT = Path(__file__).resolve().parents[2]

#: Under THIS repo — never the dest clone being published, which is mid-
#: rewrite of its own tree during a swap and would destroy or publish a
#: record written into it as a side effect of the very operation that
#: produced it (§ EVIDENCE, dispatch brief C1).
AUDITS_DIR = _REPO_ROOT / "state" / "audits" / "publish-swap-refusals"

#: ERROR_ACCESS_DENIED, ERROR_SHARING_VIOLATION — never `.errno`, which
#: CPython maps identically to `EACCES` for both codes and so cannot
#: discriminate a real holder refusal from any other `PermissionError`.
_HOLDER_WINERRORS = (5, 32)


def is_holder_refusal(exc: BaseException) -> bool:
    """True only for the discriminated holder shape this plan exists to
    record: a `PermissionError` whose `.winerror` is 5 or 32. Any other
    exception (`FileExistsError`, `NotADirectoryError`, a `PermissionError`
    with a different `.winerror`) is not a holder refusal — a blanket
    `except OSError` would mint junk records for refusals with no holder at
    all, diluting the corpus this plan exists to build."""
    return isinstance(exc, PermissionError) and getattr(exc, "winerror", None) in _HOLDER_WINERRORS


def record_publish_swap_refusal(
    *,
    refused_path: Path,
    aside_path: Optional[Path],
    swap_branch: str,
    failing_operation: str,
    exc: BaseException,
) -> Path:
    """Writes one append-only record for a refused publish-swap operation,
    then prints the two operator-facing cold-path lines to stderr. Never
    called on the success path — every call site in `publish.py` reaches
    this only from inside an `except` handler, and lazily imports this
    module to reach it (§ CALL SITES, dispatch brief C1) — so the success
    path never pays the import or the write.

    One file per event, no rotation logic: these should be rare, and if
    they are not, that is itself the finding (§ EVIDENCE)."""
    timestamp = datetime.now(timezone.utc)
    pid = os.getpid()
    record = {
        "refused_path": str(refused_path),
        "aside_path": str(aside_path) if aside_path is not None else None,
        "swap_branch": swap_branch,
        "failing_operation": failing_operation,
        "pid": pid,
        "timestamp": timestamp.isoformat(),
        "reason": str(exc),
    }

    AUDITS_DIR.mkdir(parents=True, exist_ok=True)
    record_path = AUDITS_DIR / f"{timestamp.strftime('%Y%m%dT%H%M%S.%f')}Z-{pid}.json"
    record_path.write_text(json.dumps(record, indent=2), encoding="utf-8", newline="\n")

    # Two lines, the second `Remediation:`-prefixed — the guard's check is
    # scoped by `stripped.startswith(("Remediation:", "Then:"))`, so a
    # remediation sentence folded into the first line is never inspected
    # (§ FAILURE TEXT, dispatch brief C1). `python` not `python3`: a stock
    # Windows install has no `python3` on PATH.
    print(
        f"Publish swap refused: {exc}. Diagnostic recorded to {record_path}.",
        file=sys.stderr,
    )
    print(f"Remediation: python -m json.tool {record_path}", file=sys.stderr)

    return record_path


def main(argv: list[str]) -> int:
    """This module is a library — `record_publish_swap_refusal` is called
    only from `publish.py`'s own `except` handlers (§ CALL SITES above), and
    ships no standalone CLI behavior of its own. This entrypoint exists so
    the name resolves on the warm door like every other allowlisted
    `coordinator/bin` name; it has nothing to route to and always reports a
    usage error."""
    print(
        "publish_refusal_record: library module, no standalone CLI — "
        "invoked only via record_publish_swap_refusal() from publish.py's "
        "own except handlers.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
