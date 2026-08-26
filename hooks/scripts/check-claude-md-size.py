#!/usr/bin/env python3
"""PreToolUse hook: gate Write/Edit/MultiEdit on a GOVERNED CLAUDE.md by
the C7 admission predicate AND a soft post-edit size warning.

Claude Code emits a load-time performance warning at 40KB on auto-loaded
CLAUDE.md files. This hook simulates the pending edit, then applies the
Claude-klabauter-owned SSOT thresholds (`coordinator_core.claude_md_budget`):
  - > SOFT_LIMIT_BYTES → exit 1 (advisory, stderr shown to user)
  - otherwise          → exit 0

The HARD_LIMIT_BYTES (exit 2, BLOCK) leg of this same budget has been
ported to the claude-klabauter engine as `coordinator_core.write_guards.
check_claude_md_size` (2026-07-29, `docs/plans/2026-07-29-hook-fan-in-
write-path.md` § C8) and no longer runs here — this hook now only ever
soft-warns (exit 1) on size, never hard-blocks on it. It still hard-blocks
(exit 2) on the C7 admission-gate check below, which is a wholly separate,
doctrine-plane-resident-permanently predicate — see that section's own docstring for
why it does not fold into the engine.

Fires only when the target path is a GOVERNED (fleet-loaded) CLAUDE.md-class
surface per `coordinator_core.claude_md_budget.is_governed_claude_md` —
`~/.claude/CLAUDE.md` or `<dev-repo>/coordinator/CLAUDE.md` — NOT a bare
basename match. A repo-scoped `CLAUDE.md` (this doctrine-plane repo's own repo-root file,
any sibling repo's) is a project file, not fleet-loaded, and must not share
this budget; see `coordinator/docs/wiki/claude-md-surfaces.md`. All other
paths, and any path that fails the governed-surface check, fast-exit 0.
Simulation failures fail open (exit 0) — never block on a parse error in the
gate itself. If the claude-klabauter engine (thresholds + discriminant SSOT) cannot be
resolved/imported on this machine, this hook falls back to its own local
copy of the prior thresholds/basename-match behaviour rather than going
fully silent — see `_fallback_is_governed`/`_HARD_FALLBACK`/`_SOFT_FALLBACK`
below.

C7 ADMISSION GATE (this hook's second, independent check, added on top of the
size gate above): REPOINTED AND WIDENED by C7a (`docs/plans/2026-07-30-boot-
doctrine-cut-and-refill-gate.md` § C7a) off the derived-copy-only
`~/.claude/CLAUDE.md` target onto the full audience-governed AUTHORING
surface set `_claude_md_ledger.GOVERNED_AUTHORING_SURFACES` — the tracked
files agents actually edit, not only their derived/live copies. For any
governed surface the edit targets, any heading section that GREW is refused
unless a ledger row for it pre-exists with a non-empty disposition from the
closed enum, and — where that disposition is FLOOR — a named demote target;
a governed surface with no per-surface ledger yet at all blocks growth and
permits shrinkage (the bootstrap disposition). This admission-gate check
runs independently of the SIZE-budget `governed` check above — a surface can
be admission-governed (e.g. `global-doctrine/CLAUDE.md`, `CLAUDE.md`) without
being SIZE-governed (that budget targets only the two `CLAUDE.md`-class
fleet-loaded files), and vice versa. This is the fast-path enforcement
point; the slow/CI-path twin is `coordinator/tests/
test_claude_md_ledger_invariant.py`, which catches write paths this hook's
`Write|Edit|MultiEdit` tool-name matcher cannot see (e.g. a future
`verify-snippet-sync --fix` enrolment writing via subprocess). Both import
the SAME predicate composition (`_claude_md_ledger.admission_check_for_
surface`) rather than defining a rival. A missing/unparseable ledger fails
LOUD (BLOCK, exit 2) here too — never a silent admit.

Spec backlink: docs/plans/2026-07-30-boot-doctrine-cut-and-refill-gate.md § C7a

RUNNER FOLD (C3, `docs/plans/2026-08-06-hook-spawn-fan-in-finish-and-extend.md`
§ C3) — PROTOCOL TRANSLATION, not merely a residency move. `main()` no longer
calls `sys.exit()` internally (contract clause 1,
`_guard_runner_contract.py`); it `return`s the exit code instead, and
`__main__` still does `sys.exit(main())` so standalone invocation (and
`COORDINATOR_HOOK_MESSAGE_MEASURE` measurement mode, which is standalone-
invocation-only per contract clause 9) is byte-identical to before this fold:
same stderr text, same exit codes. This guard predates `_message_envelope`
and authors its own stderr prose directly (`_compose_*_message`, not
`compose`/`emit`) — routing that prose through `_message_envelope.emit()`
here would additionally enrol it in the Category-A message-budget census
(`coordinator/tests/test_hook_message_budget.py`), a distinct 280-char-cap
concern this chunk's surface does not touch. Instead, `verdict_from_exit`
and `run_via_runner` below translate this guard's OWN exit-code protocol
(`sys.exit(2)`/`sys.exit(1)`/`sys.exit(0)` + stderr prose) into the runner's
verdict shape, per the PM ruling: exit 2 (read failure / `LedgerError` /
admission denial) -> `CHANNEL_DENY`, carrying the captured stderr text as
`permissionDecisionReason`; exit 1 (the size soft-warn) -> `CHANNEL_
ADDITIONAL_CONTEXT`, per PM ruling 2026-08-06 (the soft-warn's prior
stderr-only audience does not read the terminal that stream renders to);
exit 0 -> no verdict. The guard's predicate, thresholds, and surface set are
untouched by this fold — only the channel the advisory/deny travels on.
"""

import contextlib
import io
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
try:
    from _engine_root import (  # noqa: E402
        arm_lazy_ops as _arm_lazy_ops,
        resolve_claude_klabauter_root as _resolve_claude_klabauter_root,
    )
except Exception:
    def _resolve_claude_klabauter_root():
        return None

    def _arm_lazy_ops():
        return None

from _claude_md_ledger import (  # noqa: E402
    LedgerError,
    admission_check_for_surface,
    resolve_governed_surface,
)
from _guard_runner_contract import (  # noqa: E402
    CHANNEL_ADDITIONAL_CONTEXT,
    CHANNEL_DENY,
)

#: Repo root is this file's great-great-grandparent:
#: coordinator/hooks/scripts/<this file>. Used both to resolve which
#: `GOVERNED_AUTHORING_SURFACES` entry (if any) a write targets, and to
#: resolve that surface's own per-surface classification ledger.
_REPO_ROOT = Path(__file__).resolve().parents[3]

# Fallback thresholds/discriminant used ONLY when the claude-klabauter engine (the
# actual SSOT, `coordinator_core.claude_md_budget`) cannot be resolved or
# imported on this machine — degrade to a conservative local approximation
# rather than fail fully open (a missing sibling engine should narrow this
# hook's coverage, not disable it outright). Kept intentionally close to the
# unified SSOT values (40000/38000) rather than the pre-unification doctrine-plane-local
# 39900/39000 pair, so a fallback firing does not itself reintroduce drift.
_HARD_FALLBACK = 40000
_SOFT_FALLBACK = 38000


def _fallback_is_governed(file_path: str) -> bool:
    """Basename-only approximation used only when the claude-klabauter SSOT is
    unresolvable. Deliberately narrower than a bare basename match where
    cheaply possible: still excludes anything not literally named
    CLAUDE.md, but — unlike the claude-klabauter-owned discriminant — cannot
    distinguish a repo-scoped CLAUDE.md from a governed one without the
    dev-repo-sentinel logic that lives in `coordinator_core.claude_md_budget`.
    """
    return os.path.basename(file_path) == "CLAUDE.md"


def _load_budget():
    """Resolve the claude-klabauter-owned SSOT module, or None on any failure."""
    root = _resolve_claude_klabauter_root()
    if not root:
        return None
    if root not in sys.path:
        sys.path.append(root)
    try:
        from coordinator_core import claude_md_budget
        return claude_md_budget
    except Exception:
        return None


def _estimate_tokens(text):
    """Best-effort token estimate via the claude-klabauter token oracle
    (`coordinator_core.ops.measure_token_envelope.estimate_tokens`), or None
    if the engine is unresolvable/unimportable. Reported alongside bytes in
    the block/warning messages so this hook's output covers BOTH units
    (AC1) rather than bytes only -- see that module's docstring for why the
    estimate is a ~4-chars/token heuristic, not an exact tokenizer count.
    """
    root = _resolve_claude_klabauter_root()
    if not root:
        return None
    if root not in sys.path:
        sys.path.append(root)
    # Direct-import of ONE op module, never a dispatch-by-name -- without this
    # the `coordinator_core.ops` package-init eagerly imports ~80 op modules
    # (~78ms measured) to populate a registry this call never reads. Safe here
    # because `_load_budget()`'s earlier import is `coordinator_core.claude_md_budget`,
    # outside the `ops` package, so `ops` is still unimported at this point.
    _arm_lazy_ops()
    try:
        from coordinator_core.ops.measure_token_envelope import estimate_tokens
        return estimate_tokens(text)
    except Exception:
        return None


def simulate(tool, inp):
    file_path = inp.get("file_path", "")
    if file_path:
        file_path = os.path.abspath(file_path)
    if tool == "Write":
        return inp.get("content", "")
    if tool == "Edit":
        with open(file_path, "r", encoding="utf-8") as f:
            cur = f.read()
        old_s = inp.get("old_string", "")
        new_s = inp.get("new_string", "")
        return cur.replace(old_s, new_s) if inp.get("replace_all") else cur.replace(old_s, new_s, 1)
    if tool == "MultiEdit":
        with open(file_path, "r", encoding="utf-8") as f:
            buf = f.read()
        for edit in inp.get("edits", []):
            old_s = edit.get("old_string", "")
            new_s = edit.get("new_string", "")
            buf = buf.replace(old_s, new_s) if edit.get("replace_all") else buf.replace(old_s, new_s, 1)
        return buf
    return None


def _compose_read_failure_message(file_path: str, exc: BaseException) -> str:
    """Pure composer, separated from `main()`'s stdin/exit-code plumbing so
    C1b's in-process harness can call it directly per the plan's
    Measurement mechanism section. Behaviour-preserving extraction."""
    return (
        f"BLOCKED: could not read existing {file_path}: {exc}. Not "
        "silently skipping the C7 admission check.\n"
    )


def _compose_ledger_error_message(exc: BaseException) -> str:
    """Pure composer for the `LedgerError` branch -- see
    `_compose_read_failure_message`'s docstring for the separation
    rationale."""
    return f"BLOCKED: {exc}\n"


def _compose_admission_denied_message(file_path: str, size: int, token_note: str, refusal_message: str) -> str:
    """Pure composer for the "admission_check_for_surface disallows" branch."""
    return (
        f"BLOCKED: this edit to {file_path} costs {size} bytes{token_note}. "
        f"{refusal_message}\n"
    )


def _compose_soft_warn_message(file_path: str, size: int, token_note: str, soft: int, hard: int) -> str:
    """Pure composer for the size-budget soft-warn branch."""
    return (
        f"WARNING: {file_path} would be {size} bytes{token_note} "
        f"(soft {soft}; hard-block at {hard}). Approaching 40KB perf threshold.\n"
    )


def main() -> int:
    """Contract clause 1 (`_guard_runner_contract.py`): no `sys.exit()` for
    control flow in here -- every leg `return`s its exit code instead, and
    `__main__` below still does `sys.exit(main())`, so standalone invocation
    is byte-identical (same codes, same stderr text) to this guard's
    pre-fold behaviour. See this module's docstring, "RUNNER FOLD (C3)",
    for why the translation to the runner's verdict shape happens in
    `verdict_from_exit`/`run_via_runner` below rather than in here."""
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0

    tool = data.get("tool_name", "")
    if tool not in ("Write", "Edit", "MultiEdit"):
        return 0

    inp = data.get("tool_input") or {}
    file_path = inp.get("file_path", "")
    if not file_path:
        return 0
    abs_file_path = os.path.abspath(file_path)

    budget = _load_budget()
    if budget is not None:
        size_governed = budget.is_governed_claude_md(abs_file_path)
        hard, soft = budget.HARD_LIMIT_BYTES, budget.SOFT_LIMIT_BYTES
    else:
        size_governed = _fallback_is_governed(abs_file_path)
        hard, soft = _HARD_FALLBACK, _SOFT_FALLBACK

    # The SIZE-budget check (40KB perf warning, `~/.claude/CLAUDE.md` and a
    # dev-repo-sentinel-marked `coordinator/CLAUDE.md` only) and the C7
    # admission-gate check (the widened `GOVERNED_AUTHORING_SURFACES` set)
    # are INDEPENDENT predicates over independent surface sets -- a write
    # must clear this fast-exit only if it is governed by NEITHER.
    admission_surface = resolve_governed_surface(abs_file_path, _REPO_ROOT)
    if not size_governed and admission_surface is None:
        return 0

    try:
        new_content = simulate(tool, inp)
    except Exception:
        return 0

    if new_content is None:
        return 0

    size = len(new_content.encode("utf-8"))
    tokens = _estimate_tokens(new_content)
    token_note = f", ~{tokens} tokens (estimate)" if tokens is not None else ""

    if admission_surface is not None:
        # Review: code-reviewer — F1: a read failure on an EXISTING target
        # (permission error, transient encoding problem, symlink race, a
        # locked file on Windows) must fail loud, never silently skip the
        # whole admission-check block below. A genuinely missing file (not
        # yet created) is still the legitimate empty-string case -- only a
        # read failure on a file that IS present escalates.
        target_path = Path(abs_file_path)
        if target_path.is_file():
            try:
                old_content = target_path.read_text(encoding="utf-8")
            except Exception as exc:
                sys.stderr.write(_compose_read_failure_message(file_path, exc))
                return 2
        else:
            old_content = ""

        try:
            # admission_check_for_surface's own composition (bootstrap
            # disposition, per-heading admission_check, then the AC4
            # ratchet) can raise LedgerError at any of those three stages --
            # covered by this one catch so any of them fails loud instead of
            # an uncaught traceback.
            allowed, refusal_message = admission_check_for_surface(
                admission_surface, old_content, new_content, _REPO_ROOT
            )
        except LedgerError as exc:
            sys.stderr.write(_compose_ledger_error_message(exc))
            return 2

        if not allowed:
            sys.stderr.write(
                _compose_admission_denied_message(file_path, size, token_note, refusal_message)
            )
            return 2

    if size_governed and size > soft:
        sys.stderr.write(_compose_soft_warn_message(file_path, size, token_note, soft, hard))
        return 1

    return 0


# --------------------------------------------------------------------------
# Runner fold (C3) -- PROTOCOL TRANSLATION. See this module's docstring,
# "RUNNER FOLD (C3)", for why this guard's own exit-code + stderr-prose
# protocol is translated here rather than routed through `_message_envelope`.
# --------------------------------------------------------------------------

#: This guard's `GuardScopeDescriptor` (contract clause 12) lives in
#: `_guard_runner_contract.CHECK_CLAUDE_MD_SIZE_SCOPE_DESCRIPTOR`, NOT here
#: -- moved there by C4 (`docs/plans/2026-08-06-hook-spawn-fan-in-finish-
#: and-extend.md` § C4) when `_guard_runner.REAL_GUARD_REGISTRY` was wired
#: for real. A descriptor referenced at `_guard_runner.py` module-import
#: time (i.e. on every edit, to build the registry tuple) but DEFINED
#: inside this guard's own body module would force an eager import of this
#: whole file on every edit just to read the descriptor -- exactly the
#: ~63ms cost clause 12 exists to defer, and exactly the same reasoning
#: that already put `guard-doctrine-changelog-prose.py`'s descriptor in the
#: contract module rather than its own body (C3b). See that constant's own
#: docstring for the descriptor's shape and why it is a sound superset over
#: the SIZE-budget + C7 admission-gate governed-path union.


def verdict_from_exit(exit_code: int, stderr_text: str) -> Optional[dict]:
    """Pure translator: this guard's own `(exit_code, captured stderr text)`
    pair -> the `{"channel", "text"}` verdict shape `_guard_runner.run_guards`
    aggregates. Per the C3 chunk's PM-ruled mapping:
      - 2 (read failure / `LedgerError` / admission denial) -> `CHANNEL_DENY`,
        text is the captured stderr (this guard's existing `_compose_*_message`
        prose -- unchanged wording, just moved off a channel with a reader
        (the terminal) the deny already also had, onto the one the runner
        aggregates into `permissionDecisionReason`).
      - 1 (the size soft-warn) -> `CHANNEL_ADDITIONAL_CONTEXT`, per PM ruling
        2026-08-06: the soft-warn's prior stderr-only audience does not read
        the terminal that stream renders to, so this is the fix, not a
        side effect of the fold.
      - 0, or any other exit code, or blank stderr on 1/2 -- no verdict
        (`None`), matching this guard's existing "print nothing on allow"
        contract; a blank-stderr 1/2 would otherwise be indistinguishable
        from a genuine advisory/deny with empty prose, which is not a shape
        this guard's own legs ever produce (every 1/2 return writes stderr
        first), so treating it as "no verdict" never masks a real one.
    """
    text = stderr_text.strip()
    if not text:
        return None
    if exit_code == 2:
        return {"channel": CHANNEL_DENY, "text": text}
    if exit_code == 1:
        return {"channel": CHANNEL_ADDITIONAL_CONTEXT, "text": text}
    return None


def run_via_runner(payload: Any) -> Optional[dict]:
    """The runner-facing entrypoint: matches the `(name, callable)`
    `GuardEntry` shape `_guard_runner.run_guards` consumes directly --
    `Callable[[Any], Optional[GuardVerdict]]`. Re-serializes `payload` (the
    parsed PreToolUse payload dict) back to the JSON text `main()` expects on
    stdin (mirroring what a real hook process feeds it), runs `main()` under
    the same stdin-swap/stderr-capture technique `_guard_runner.
    _invoke_guard_main` uses for the other three enrolled guards, and
    translates the resulting `(exit_code, stderr_text)` pair via
    `verdict_from_exit`. Never raises on a bad payload -- returns `None`,
    matching every other guard's fail-open contract; exceptions from `main()`
    itself are the CALLER's responsibility to isolate (contract clause 11,
    same division of labour `_guard_runner.run_guards` already assumes for
    every enrolled guard)."""
    try:
        stdin_text = json.dumps(payload)
    except Exception:
        return None

    stdin_buf = io.StringIO(stdin_text)
    stderr_buf = io.StringIO()
    old_stdin = sys.stdin
    with contextlib.redirect_stderr(stderr_buf):
        sys.stdin = stdin_buf
        try:
            exit_code = main()
        finally:
            sys.stdin = old_stdin

    return verdict_from_exit(exit_code, stderr_buf.getvalue())


if __name__ == "__main__":
    sys.exit(main())
