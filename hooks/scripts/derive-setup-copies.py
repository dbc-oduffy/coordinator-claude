"""PostToolUse(Write|Edit|MultiEdit) hook: re-derive DERIVED install-template
copies from their CANONICAL repo-root sources whenever a canonical row is
written.

Why this exists — several `setup/` files live in two places (repo-root
canonical, plus an install-template derived copy under the templates tree,
e.g. the `percolate-hooks/percolate-store.yaml` row) with
no code-level sync mechanism between them. This hook was originally scoped to one such pair (`percolate-store.yaml`
alone); it is now a small canonical->template TABLE (`ROWS` below) covering
every such pair, each row declaring its own parity MODE:

- **byte-copy** — the derived copy should be byte-identical to canonical
  (`percolate-store.yaml`). On a canonical write, this hook copies
  canonical -> derived directly.
- **contract-only** — this hook never rewrites the derived copy.
    * `publish_sync.py` — a PERMANENT, deliberate, hand-maintained divergence.
      The install template keeps its own `_locate_percolate_lib()` resolver
      ladder that a live install needs and a byte-copy would destroy. Parity is
      enforced on the *public callable signature*, not on bytes.
  Signature parity for the permanent case is checked by
  `coordinator/tests/test_publish_sync_copies_parity.py`. This hook never
  copies a contract-only row: `_handle_canonical_write` routes every
  canonical write through `_derive_or_raise` (the single choke point), which
  checks the mode first and raises `ContractOnlyNotOverwritten` before any
  file I/O happens, and `Row.__post_init__` rejects any mode outside
  `{byte-copy, contract-only}` at row-construction time — so no row, known or
  mistyped, can reach `shutil.copyfile` for a contract-only mode.

`coordinator/tests/test_percolate_store_copies_parity.py` DETECTS drift on the
byte-copy rows, but detection fires only when someone runs pytest — until then
the copies diverge silently, and the only discharge is "the operator remembers
to run the copy by hand." That is precisely the failure shape this repo's
north star (`coordinator/docs/wiki/invisible-doctrine.md`) names. This hook
makes byte-copy derivation automatic, keeping the parity gate green without
anyone remembering.

Direction is CANONICAL -> DERIVED, never the reverse. A write to a derived
copy is therefore an edit to a derived artifact: this hook does NOT silently
clobber it (that would destroy the operator's work) and does NOT propagate it
(that would promote a derived copy to canonical). It emits a loud advisory
naming the canonical path as the place to re-author, and leaves the file
alone — this applies to both parity modes.

<!-- Review (C3, 2026-08-01): the third rung this hook used to mirror into --
     the live shared install at `<CLAUDE_HOME|HOME>/.claude/setup/...` -- is
     RETIRED here, not generalized into the table. Once the engine's
     percolate-root resolver reorders its rungs, nothing resolves
     `~/.claude/setup/` as a percolate root in the ordinary case, so that
     rung was an unguarded `shutil.copyfile` into a file tracked (and dirty)
     in a foreign, unrelated repo, whose product nothing reads. PM-ratified
     2026-08-01. This hook now only ever touches paths inside THIS repo. -->

Contract (house PostToolUse-advisory convention, matching
derive-global-doctrine-live-copy.py — exit 2 + stderr reaches the model's next
turn without blocking; exit 0 + silence is the non-firing no-op):
  stdin   -- PostToolUse JSON (tool_name, tool_input.file_path, ...)
  stderr  -- one advisory block on a MATCHING write (success or failure)
  exit 2  -- advisory fired (matching write, success or failure)
  exit 0  -- non-matching path; NOTHING on stdout/stderr (this hook runs on
             every write in the session, so silence on the common case is
             required)

Fail-loud, not fail-silent, on the paths this hook owns (canonical matched but
a read or write failed) — a bare `except Exception: pass` would silently
reintroduce the exact staleness gap the hook exists to close. Every other guard
(path did not match, repo root undiscoverable) fails open/silent by design.

Portability: macOS + Windows + Linux. No subprocess/`cp` — `shutil.copyfile`
only. Repo root resolves from `Path(__file__)` upward (parents[3]: scripts ->
hooks -> coordinator -> repo root), never from cwd or a hardcoded path.

Spec backlink: coordinator/tests/test_percolate_store_copies_parity.py,
coordinator/tests/test_publish_sync_copies_parity.py (the two detection gates
this hook keeps green, one per parity mode), tasks/2026-07-23-store-drift/
scout-topology.md § 3 (percolate-store.yaml: canonical tracks derived exactly).
"""

from __future__ import annotations

import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

from _message_envelope import CHANNEL_STOP, compose, emit  # noqa: E402

#: Wiki section carrying the relocated parity-mode explanation (permanent vs
#: temporary contract-only rows, and the canonical->derived direction
#: contract) -- see this hook's own relocation fragment
#: (state/relocations/guard-message-cap/derive-setup-copies.py.md).
_WIKI_ANCHOR = (
    # Review: code-reviewer -- bare fragment produced an unresolvable
    # `render()` citation. Full path matches every other converted hook.
    "coordinator/docs/wiki/guard-message-concision.md"
    "#derive-setup-copies-parity-modes-and-remedies"
)

BYTE_COPY = "byte-copy"
CONTRACT_ONLY = "contract-only"


_VALID_MODES = frozenset({BYTE_COPY, CONTRACT_ONLY})


@dataclass(frozen=True)
class Row:
    """One canonical->derived pair, relative to the repo root.

    `parity_test` names the test file that guards a contract-only row's
    divergence (e.g. `test_publish_sync_copies_parity.py`), or `None` if no
    such test exists yet (e.g. the README row, whose divergence is TEMPORARY
    and unreconciled — see its own comment in ROWS below). Advisory text
    reads this field rather than hardcoding a test name, so a row whose
    divergence has no guarding test cannot be told it does.
    """

    canonical: Path
    derived: Path
    mode: str
    parity_test: str | None = None

    def __post_init__(self) -> None:
        # Review (code-reviewer, 2026-08-02, Finding 2): fail loudly at
        # row-construction time on any mode outside the known set, so a typo,
        # a `None`, or a future third mode can never reach `_derive_or_raise`
        # and silently fall through to `shutil.copyfile`.
        if self.mode not in _VALID_MODES:
            raise ValueError(
                f"Row for {self.canonical} has unrecognized mode {self.mode!r}; "
                f"must be one of {sorted(_VALID_MODES)}"
            )


@dataclass(frozen=True)
class ResolvedRow:
    """A `Row` with both sides resolved to absolute paths against one repo root."""

    canonical: Path
    derived: Path
    mode: str
    parity_test: str | None = None

    def __post_init__(self) -> None:
        # Same guard as Row.__post_init__ — a ResolvedRow can also be
        # hand-constructed directly (see tests), so it must not accept an
        # unrecognized mode either.
        if self.mode not in _VALID_MODES:
            raise ValueError(
                f"ResolvedRow for {self.canonical} has unrecognized mode "
                f"{self.mode!r}; must be one of {sorted(_VALID_MODES)}"
            )


ROWS: tuple[Row, ...] = (
    Row(
        canonical=Path("setup") / "percolate-hooks" / "percolate-store.yaml",
        derived=Path("coordinator") / "templates" / "setup" / "percolate-hooks" / "percolate-store.yaml",
        mode=BYTE_COPY,
    ),
    Row(
        canonical=Path("setup") / "percolate-hooks" / "README.md",
        derived=Path("coordinator") / "templates" / "setup" / "percolate-hooks" / "README.md",
        mode=BYTE_COPY,
    ),
    Row(
        canonical=Path("setup") / "publish_sync.py",
        derived=Path("coordinator") / "templates" / "setup" / "publish_sync.py",
        mode=CONTRACT_ONLY,
        parity_test="test_publish_sync_copies_parity.py",
    ),
)


class ContractOnlyNotOverwritten(Exception):
    """Raised by `_derive_or_raise` when a canonical write matches a
    contract-only row. The derived copy is hand-maintained and guarded by a
    signature-parity test where one exists (see the row's own comment
    above); this exception is how the hook avoids a blind byte-copy of it —
    the mode is checked before any file I/O, and `Row.__post_init__` rejects
    any mode outside the known set, so no code path here can reach
    `shutil.copyfile` for a contract-only row."""

    def __init__(self, row: ResolvedRow) -> None:
        super().__init__(f"contract-only row, not overwritten: {row.derived}")
        self.row = row


def _read_stdin() -> str:
    try:
        if sys.stdin.isatty():
            return ""
        return sys.stdin.read()
    except Exception:
        return ""


def _parse_input(raw: str) -> dict:
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _repo_root() -> Path:
    # coordinator/hooks/scripts/<this file> -> parents[3] is the repo root.
    return Path(__file__).resolve().parents[3]


def _resolve(path: Path) -> Path:
    try:
        return path.resolve()
    except Exception:
        return path


def _resolved_rows(repo_root: Path) -> tuple[ResolvedRow, ...]:
    return tuple(
        ResolvedRow(
            canonical=_resolve(repo_root / row.canonical),
            derived=_resolve(repo_root / row.derived),
            mode=row.mode,
            parity_test=row.parity_test,
        )
        for row in ROWS
    )


def _derive_or_raise(row: ResolvedRow) -> None:
    """Perform the canonical->derived derivation for one row, or raise.

    `byte-copy` rows are copied directly. `contract-only` rows raise
    `ContractOnlyNotOverwritten` BEFORE any file is touched — there is no
    fallthrough path from a contract-only row to `shutil.copyfile` in this
    function. Combined with `Row.__post_init__` rejecting any mode outside
    `{byte-copy, contract-only}`, no row can reach `shutil.copyfile` while
    carrying a contract-only mode, known or mistyped."""
    if row.mode == CONTRACT_ONLY:
        raise ContractOnlyNotOverwritten(row)
    row.derived.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(row.canonical, row.derived)


def _compose_derived_write_advisory(file_path: str, row: ResolvedRow):
    """Pure composer for a write landing on a DERIVED copy directly (either
    parity mode) -- separable from stdin/exit-code plumbing so it can be
    called directly per emission site. Full carve-out prose (permanent vs
    temporary contract-only reasoning) relocated to `_WIKI_ANCHOR` -- see
    this hook's own relocation fragment."""
    if row.mode == CONTRACT_ONLY:
        if row.parity_test:
            prose = (
                f"{file_path} is hand-maintained DERIVED copy -- NOT reverted. "
                f"Keep {row.parity_test} passing; re-author canonical."
            )
        else:
            prose = (
                f"{file_path} is hand-maintained DERIVED copy -- NOT "
                "reverted (no parity test yet; divergence is temporary)."
            )
        return compose(prose, alternative=str(row.canonical), anchor=_WIKI_ANCHOR)
    prose = (
        f"{file_path} is a DERIVED copy -- NOT propagated (lost on next "
        "canonical write). Re-author canonical."
    )
    return compose(prose, alternative=str(row.canonical), anchor=_WIKI_ANCHOR)


def _advise_derived_write(file_path: str, row: ResolvedRow) -> None:
    # Routed through `_message_envelope.emit()` (CHANNEL_STOP) rather than
    # hand-rolling `render()` + a text-mode `sys.stderr.write()` -- `emit()`'s
    # CHANNEL_STOP branch writes via `sys.stderr.buffer.write()`, which
    # bypasses Python's Windows text-mode LF->CRLF translation (a real
    # byte-fidelity loss the hand-rolled path used to carry silently). See
    # `state/bug-backlog/2026-08-06-derive-hooks-hand-roll-stop-shape-and-lo-4c1e9a7b03d5.yaml`.
    emit(_compose_derived_write_advisory(file_path, row), CHANNEL_STOP)


def _exc_reason(exc: Exception) -> str:
    """Short OS-error reason, without the embedded filename `OSError.__str__`
    normally repeats (the path is already carried separately, in the
    composer's own `alternative` slot -- printing it twice was the bulk of
    these sites' pre-conversion length). Falls back to `str(exc)` for a
    non-OSError exception, which carries no such duplication to begin with."""
    return getattr(exc, "strerror", None) or str(exc)


def _compose_read_failure_message(row: ResolvedRow, exc: Exception):
    """Pure composer for a canonical-read failure. Fail-loud contract
    rationale relocated to `_WIKI_ANCHOR`; `row.canonical` rides the exempt
    `alternative` slot instead of being repeated inline (see `_exc_reason`)."""
    prose = f"FAILED to read canonical -- derived NOT re-derived ({_exc_reason(exc)})."
    return compose(prose, alternative=str(row.canonical), anchor=_WIKI_ANCHOR)


def _compose_contract_only_message(row: ResolvedRow):
    """Pure composer for a canonical write matching a contract-only row.
    Permanent-vs-temporary parity-mode reasoning relocated to
    `_WIKI_ANCHOR`; `row.derived` (the file to confirm or hand-edit) rides
    the exempt `alternative` slot."""
    if row.parity_test:
        prose = (
            f"canonical is contract-only -- derived NOT re-derived. Confirm "
            f"{row.parity_test} passes, or hand-edit derived instead."
        )
    else:
        prose = (
            "canonical is contract-only -- derived NOT re-derived. No "
            "parity test yet; divergence is temporary."
        )
    return compose(prose, alternative=str(row.derived), anchor=_WIKI_ANCHOR)


def _compose_write_failure_message(row: ResolvedRow, exc: Exception, source_bytes: bytes):
    """Pure composer for a derived-write failure after a successful
    canonical read. `row.derived` rides the exempt `alternative` slot."""
    prose = (
        f"FAILED to write derived -- canonical read OK, derivation did NOT "
        f"complete ({_exc_reason(exc)})."
    )
    return compose(prose, alternative=str(row.derived), anchor=_WIKI_ANCHOR)


def _compose_success_message(row: ResolvedRow, source_bytes: bytes):
    """Pure composer for a successful byte-copy re-derivation. `row.derived`
    (the file to inspect) rides the exempt `alternative` slot instead of
    being repeated inline alongside `row.canonical`."""
    prose = f"re-derived derived copy from canonical ({len(source_bytes)} bytes)."
    return compose(prose, alternative=str(row.derived), anchor=_WIKI_ANCHOR)


def _handle_canonical_write(row: ResolvedRow) -> int:
    # Routed through `_message_envelope.emit()` -- see `_advise_derived_write`
    # above for the CRLF byte-fidelity rationale.
    try:
        source_bytes = row.canonical.read_bytes()
    except Exception as exc:
        rc = emit(_compose_read_failure_message(row, exc), CHANNEL_STOP)
        return rc if rc is not None else 2

    try:
        _derive_or_raise(row)
    except ContractOnlyNotOverwritten:
        rc = emit(_compose_contract_only_message(row), CHANNEL_STOP)
        return rc if rc is not None else 2
    except Exception as exc:
        rc = emit(_compose_write_failure_message(row, exc, source_bytes), CHANNEL_STOP)
        return rc if rc is not None else 2

    rc = emit(_compose_success_message(row, source_bytes), CHANNEL_STOP)
    return rc if rc is not None else 2


def main() -> int:
    data = _parse_input(_read_stdin())

    tool_input = data.get("tool_input")
    file_path = ""
    if isinstance(tool_input, dict):
        file_path = tool_input.get("file_path", "") or ""
    if not isinstance(file_path, str) or not file_path:
        return 0

    try:
        written = Path(PureWindowsPath(file_path).as_posix()).resolve()
    except Exception:
        return 0

    rows = _resolved_rows(_repo_root())

    for row in rows:
        if written == row.derived:
            _advise_derived_write(file_path, row)
            return 2

    for row in rows:
        if written == row.canonical:
            return _handle_canonical_write(row)

    return 0


if __name__ == "__main__":
    sys.exit(main())
