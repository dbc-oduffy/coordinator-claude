# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
workday-complete-reconcile.py — /workday-complete Step 1.5 (cruft-sweep
dispatch) + Step 2.6 (completion-entry reconcile sweep with cross-machine
liveness gating), ported to naked Python. Bash-kill campaign, M3 chunk WDC-2.

Two subcommands, each mirroring one bash fence from the DoE ceremony file
verbatim in behavior (both non-blocking — neither ever fails the ceremony):

    cruft-sweep
        Invokes the co-located `cruft-sweep --class all --apply --quiet`
        binary. On a non-zero exit, prints a WARN pointing at the central
        cruft-sweep-log.md (resolved via the co-located
        coordinator-state-root.py --central) and returns 0 regardless —
        Layer 1 is lock-protected/idempotent and advisory-only by design
        (docs/wiki/cruft-sweep-cadence.md § Layer 1).

    completion-reconcile
        Enumerates this month's `archive/completed/<YYYY-MM>/*.md` entries,
        filters to `status: pending-release`, and for each one resolves
        whether it belongs to THIS session or a cross-machine peer session.
        Own-session entries always reconcile. Cross-machine entries reconcile
        only when their authoring session is confirmed DEAD via the sanctioned
        liveness predicate (coordinator_core.session.liveness.
        resolve_live_session_ids — the native successor to the retired bash
        `cs_live_session_ids` / the js_bridge_cli subprocess bridge the DoE
        bash fence shelled out to; this port calls the Python liveness module
        directly, no subprocess hop needed since this file is already
        in-process Python). A live cross-machine session is mid-edit — stand
        down to avoid stomping its entry. For each entry cleared to reconcile,
        dispatches the co-located reconcile-completion-commits.py in --append
        mode (passing the entry's OWN authored_by as --session-id for
        cross-machine entries, never the wrapping session's id — this is the
        F1 fix already present in the bash oracle, preserved here), stages any
        amended entry via `git add -- <entry>` (Step 9 sweeps staged paths
        into its own scoped changelog commit), and prints a one-line summary
        feeding Step 11.

RAW-PID-LIVENESS: this script NEVER shells out to `ps -p`/`kill -0` a stored
pid — resolve_live_session_ids() is the sole sanctioned liveness predicate.
→ docs/wiki/coordinator-tripwires.md § RAW-PID-LIVENESS

Negative-spec: does NOT re-implement completion-commits reconciliation
itself (session-id resolution tiers 1-3, merge-base/delta computation,
chain-slug expansion) — that lives in the co-located
reconcile-completion-commits.py / coordinator_core.ops.completion_ops. This
script owns only the outer month-scoped scan/frontmatter-gate/liveness-gate/
dispatch loop the retired bash Step 2.6 fence performed BEFORE calling that
helper, plus the Step 1.5 cruft-sweep dispatch wrapper.

Spec backlink: DoE-claude coordinator/commands/workday-complete.md § Step 1.5
    (Cruft Sweep Apply), § Step 2.6 (Completion-Entry Reconcile Sweep)
Port source: DoE-claude coordinator/commands/workday-complete.md Step 1.5 +
    Step 2.6 bash fences, ported verbatim to naked Python as part of the
    bash-kill campaign (2026-07-23, M3 chunk WDC-2).
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

_BIN_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_BIN_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
import cc_invoke  # noqa: E402
from cc_invoke import _resolve_claude_klabauter_root, child_env  # noqa: E402


def _no_console_kw() -> dict:
    """Windows: suppresses the console popup a subprocess.run(...) would
    otherwise trigger under the headless Claude Code Bash-tool parent.
    Splat-ready; empty dict elsewhere / on any resolution failure."""
    return cc_invoke._no_console_kw(_resolve_claude_klabauter_root())


def _no_console_passthrough_kw() -> dict:
    """`_no_console_kw` for a child whose output must reach the operator.

    Console suppression alone makes the child bind its standard handles to the
    window-less console CREATE_NO_WINDOW allocates instead of inheriting this
    process's, so its output is lost. See
    `cc_invoke._no_console_passthrough_kw` for the mechanism.
    """
    return cc_invoke._no_console_passthrough_kw(_resolve_claude_klabauter_root())


_APPENDED_RE = re.compile(r"appended=(\d+)")


# ---------------------------------------------------------------------------
# Shared frontmatter helpers (mirror the bash oracle's awk single-key scan;
# same shape as the sibling workday-start-reconcile-sweep.py port).
# ---------------------------------------------------------------------------


def _frontmatter_field(content: str, key: str) -> str:
    """Return the first `^{key}:` line's value within the first `---`
    fence block, prefix-and-whitespace-stripped. "" on a miss — matches the
    bash awk oracle's silent-empty behavior.
    """
    n = 0
    prefix_re = re.compile(rf"^{re.escape(key)}:[ \t]*")
    for line in content.splitlines():
        if line == "---":
            n += 1
            if n == 2:
                return ""
            continue
        if n == 1:
            m = prefix_re.match(line)
            if m:
                return line[m.end():]
    return ""


def _authored_by_field(content: str) -> str:
    """`authored_by:` with the oracle's extra scrub: strip a trailing
    ` # comment` and surrounding double-quotes on top of the plain
    key-prefix strip `_frontmatter_field` already performs.
    """
    raw = _frontmatter_field(content, "authored_by")
    raw = re.sub(r"[ \t]*#.*$", "", raw)
    if len(raw) >= 2 and raw.startswith('"') and raw.endswith('"'):
        raw = raw[1:-1]
    return raw


# ---------------------------------------------------------------------------
# Step 1.5 — cruft-sweep dispatch
# ---------------------------------------------------------------------------


def _default_cruft_sweep_bin() -> str:
    return os.path.join(_BIN_DIR, "cruft-sweep.py")


def _cruft_sweep_argv(cruft_sweep_bin: str) -> list[str]:
    """Build the invocation argv for ``cruft_sweep_bin``.

    Only a ``.cmd`` sibling is directly executable. Everything else this
    function can be handed — the shipped ``cruft-sweep.py`` default, the
    extensionless installed shim, an extensionless test double — fails a bare
    launch on BOTH platforms: CreateProcess raises WinError 193 ("%1 is not a
    valid Win32 application") and does not interpret ``#!`` lines, and POSIX
    refuses a source file carrying no exec bit. Route through this interpreter
    explicitly rather than depend on a ``.cmd`` sibling existing on disk for a
    path this function does not itself control.

    Negative-spec: the extension test must NOT be "extensionless only" and the
    platform test must NOT be ``os.name == "nt"`` only. Both narrowings were
    live here until 2026-08-16 and left the shipped default (``.py``, set by
    ``_default_cruft_sweep_bin``) on the bare-launch rung, so Step 1.5 raised
    WinError 193 on every Windows run and degraded to its non-blocking WARN —
    the sweep never once executed. Mirrors ``wsc-session-disposition.py``'s
    ``_session_claim_cli_argv``, which already cites this function as its
    precedent.
    """
    if os.path.splitext(cruft_sweep_bin)[1] == ".cmd":
        return [cruft_sweep_bin]
    return [sys.executable, cruft_sweep_bin]


def _default_state_root_script() -> str:
    return os.path.join(_BIN_DIR, "..", "lib", "coordinator-state-root.py")


def _cruft_sweep_log_path(state_root_script: str) -> str:
    """Best-effort resolve `<central-state-root>/cruft-sweep-log.md` for the
    WARN pointer. Falls back to a bare filename on any resolution failure —
    the WARN is advisory, never a gate, so a broken resolver must not raise.
    """
    try:
        result = subprocess.run(
            [sys.executable, state_root_script, "--central"],
            capture_output=True,
            text=True,
            env=child_env(),
            **_no_console_kw(),
        )
        central_root = result.stdout.strip()
        if result.returncode == 0 and central_root:
            return os.path.join(central_root, "cruft-sweep-log.md")
    except OSError:
        pass
    return "cruft-sweep-log.md"


def run_cruft_sweep(
    cruft_sweep_bin: str | None = None,
    state_root_script: str | None = None,
    out=sys.stdout,
    err=sys.stderr,
) -> int:
    """Invoke `cruft-sweep --class all --apply --quiet`. Non-blocking: always
    returns 0 — a non-zero cruft-sweep exit prints a WARN (mirroring the bash
    `|| echo ... WARN ...` fallthrough) and the sweep proceeds regardless.
    """
    cruft_sweep_bin = cruft_sweep_bin or _default_cruft_sweep_bin()
    state_root_script = state_root_script or _default_state_root_script()

    try:
        result = subprocess.run(
            [*_cruft_sweep_argv(cruft_sweep_bin), "--class", "all", "--apply", "--quiet"],
            **_no_console_passthrough_kw(),
        )
        rc = result.returncode
    except OSError as exc:
        print(
            f"[workday-complete] WARN: cruft-sweep Step 1.5 could not be invoked "
            f"({exc}) (non-blocking)",
            file=err,
        )
        return 0

    if rc != 0:
        log_path = _cruft_sweep_log_path(state_root_script)
        print(
            "[workday-complete] WARN: cruft-sweep Step 1.5 exited non-zero "
            f"(non-blocking) — check {log_path}",
            file=err,
        )
    return 0


# ---------------------------------------------------------------------------
# Step 2.6 — completion-entry reconcile sweep with cross-machine liveness gate
# ---------------------------------------------------------------------------


def _resolve_session_id() -> str:
    """Delegates to ``coordinator_core.session.core.resolve_session_id``
    (KS-6, 2026-08-07): the full 3-tier ``SESSION_ENV_PRECEDENCE`` ladder
    (``COORDINATOR_SESSION_ID``, ``CLAUDE_SESSION_ID``,
    ``CLAUDE_CODE_SESSION_ID``), widened from the prior
    ``CLAUDE_CODE_SESSION_ID``-only read to match the canonical reference —
    see that constant's own docstring for the prior break-class defect two
    disagreeing copies of this ladder caused. Returns "" when unresolved,
    including on an import/CLAUDE_KLABAUTER_ROOT resolution failure (fail-soft,
    mirroring ``_resolve_live_session_ids``' own degrade contract just
    below) — degrading to "session unknown" is the pre-existing behaviour
    of this function's own env-var-only predecessor, never a hard failure.

    The `.current-session-id` sentinel tier that used to sit here was
    REMOVED (KS-4, 2026-08-07): unsound under concurrency (documented
    last-writer-wins across concurrent sessions sharing one worktree — see
    coordinator_core/bash_guards/guard_inprocess_search.py ~L84) AND its
    sole writer (session-init.py, the DoE-claude SessionStart hook) was
    deleted by PM directive 2026-07-15 — no production writer survives.
    """
    try:
        claude_klabauter_root = _resolve_claude_klabauter_root()
        if claude_klabauter_root not in sys.path:
            sys.path.insert(0, claude_klabauter_root)
        from coordinator_core.session.core import resolve_session_id

        return resolve_session_id()
    except Exception:  # noqa: BLE001 — fail-soft, matches the prior env-only read's contract
        return ""


def _resolve_live_session_ids() -> frozenset[str]:
    """Sanctioned liveness predicate — direct in-process import of
    coordinator_core.session.liveness.resolve_live_session_ids(), never a
    raw pid check (RAW-PID-LIVENESS). Fails softly to an empty set on any
    CLAUDE_KLABAUTER_ROOT/import/runtime error — the bash oracle degraded the same way
    (its `2>/dev/null || true` on the js_bridge_cli subprocess call), so an
    unresolvable liveness signal here means "reconcile only own-session
    entries," never a hard failure of the whole sweep.
    """
    try:
        claude_klabauter_root = _resolve_claude_klabauter_root()
        if claude_klabauter_root not in sys.path:
            sys.path.insert(0, claude_klabauter_root)
        from coordinator_core.session.liveness import resolve_live_session_ids

        return resolve_live_session_ids()
    except Exception:  # noqa: BLE001 — fail-soft by design, mirrors bash `|| true`
        return frozenset()


def _iter_month_entries(archive_root: str, year_month: str) -> list[str]:
    """Sorted `<archive_root>/<year_month>/*.md` — mirrors the bash oracle's
    `for _ENTRY in "archive/completed/${_TODAY_YM}/"*.md; do ... done`,
    made deterministic (bash glob order is filesystem-dependent) via sort.
    """
    pattern = os.path.join(archive_root, year_month, "*.md")
    return sorted(glob.glob(pattern))


def _run_reconcile_append(
    reconcile_script: str, session_id: str, entry_path: str
) -> tuple[int, str]:
    """Invoke the co-located reconcile-completion-commits.py in --append
    (mutating) mode. Returns (returncode, stdout); stderr is discarded,
    mirroring the bash oracle's `2>/dev/null` on this call.
    """
    try:
        result = subprocess.run(
            [
                sys.executable,
                reconcile_script,
                "--append",
                "--session-id",
                session_id,
                entry_path,
            ],
            capture_output=True,
            text=True,
            env=child_env(),
            **_no_console_kw(),
        )
    except OSError as exc:
        return 1, str(exc)
    return result.returncode, result.stdout


def _git_add(entry_path: str) -> None:
    """Best-effort `git add -- <entry>` — mirrors the bash oracle's
    `git add -- "$_ENTRY" 2>/dev/null || true` (staging failure here is
    never fatal to the sweep; Step 9 re-verifies what actually staged).
    """
    try:
        subprocess.run(
            ["git", "add", "--", entry_path],
            capture_output=True,
            **_no_console_kw(),
        )
    except OSError:
        pass


def _default_reconcile_script() -> str:
    return os.path.join(_BIN_DIR, "reconcile-completion-commits.py")


def run_completion_reconcile(
    archive_root: str = "archive/completed",
    year_month: str | None = None,
    reconcile_script: str | None = None,
    session_id: str | None = None,
    live_session_ids: frozenset[str] | None = None,
    git_add: bool = True,
    out=sys.stdout,
    err=sys.stderr,
) -> int:
    """Run the Step 2.6 completion-entry reconcile sweep. Always returns 0 —
    non-blocking, mirrors the bash oracle's `|| echo ... WARN ...` wrapper
    around the whole block.
    """
    year_month = year_month or date.today().strftime("%Y-%m")
    reconcile_script = reconcile_script or _default_reconcile_script()

    reconcile_sid = session_id if session_id is not None else _resolve_session_id()
    if not reconcile_sid:
        print(
            "[workday-complete] WARN: reconcile sweep Step 2.6 skipped — "
            "session-id unresolvable (non-blocking)",
            file=err,
        )
        return 0

    live_ids = live_session_ids if live_session_ids is not None else _resolve_live_session_ids()

    n_entries = 0
    n_commits = 0

    for entry_path in _iter_month_entries(archive_root, year_month):
        try:
            content = Path(entry_path).read_text(encoding="utf-8")
        except OSError:
            continue

        status = _frontmatter_field(content, "status")
        if status != "pending-release":
            continue

        entry_author = _authored_by_field(content)
        # Malformed entry: missing or null authored_by — skip explicitly
        # rather than letting an empty string false-match a live-id check.
        if not entry_author or entry_author == "null":
            continue

        if entry_author != reconcile_sid:
            # Cross-machine entry: stand down if the authoring session is
            # still live — it is mid-edit.
            if entry_author in live_ids:
                continue
            # F1 fix (ported verbatim): pass the entry's OWN authored_by as
            # the session-id for cross-machine dead entries so reconcile
            # collects THAT peer's commits, not the wrapping session's.
            call_sid = entry_author
        else:
            call_sid = reconcile_sid

        rc, stdout = _run_reconcile_append(reconcile_script, call_sid, entry_path)
        if rc != 0:
            print(
                f"[workday-complete] WARN: reconcile-completion-commits failed "
                f"for {entry_path} (non-blocking)",
                file=err,
            )
            continue

        m = _APPENDED_RE.search(stdout)
        appended = int(m.group(1)) if m else 0
        if appended > 0:
            if git_add:
                _git_add(entry_path)
            n_entries += 1
            n_commits += appended

    if n_entries > 0:
        print(f"Completion reconcile: {n_entries} entr(ies) folded {n_commits} commit(s)", file=out)
    else:
        print("Completion reconcile: clean", file=out)
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "workday-complete-reconcile.py — Step 1.5 cruft-sweep dispatch + "
            "Step 2.6 completion-entry reconcile sweep with cross-machine "
            "liveness gating."
        )
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_cruft = sub.add_parser("cruft-sweep", help="Step 1.5: dispatch cruft-sweep --class all --apply --quiet")
    p_cruft.add_argument("--cruft-sweep-bin", default=None, help="Path to the cruft-sweep binary (default: co-located sibling).")
    p_cruft.add_argument("--state-root-script", default=None, help="Path to coordinator-state-root.py (default: co-located lib sibling).")

    p_reconcile = sub.add_parser(
        "completion-reconcile",
        help="Step 2.6: completion-entry reconcile sweep with cross-machine liveness gating",
    )
    p_reconcile.add_argument("--archive-root", default="archive/completed", help="Root dir to scan for <root>/<YYYY-MM>/*.md completion entries (default: cwd-relative archive/completed).")
    p_reconcile.add_argument("--year-month", default=None, help="Override the YYYY-MM scanned (default: local this-month).")
    p_reconcile.add_argument("--reconcile-script", default=None, help="Path to reconcile-completion-commits.py (default: co-located sibling).")
    p_reconcile.add_argument("--session-id", default=None, help="Override this session's id (default: env/sentinel resolution ladder).")
    p_reconcile.add_argument("--no-git-add", action="store_true", help="Skip staging amended entries via git add (test/dry-run convenience).")

    return parser


def main(argv: list[str]) -> int:
    # `argv` is args-only (no leading program-name token) -- the convention
    # every sibling consumes-manifest CLI's `main(argv)` follows (see e.g.
    # `workday-complete-args-and-validate.py`'s `subcmd, rest = argv[0],
    # argv[1:]`, `workday-complete-close.py`'s `parser.parse_args(argv)`),
    # and the one `workday_complete.apply._invoke_cli_main` relies on when
    # it calls `main_fn(list(directive_args))` in-process with no argv[0]
    # placeholder. This function previously did `argv[1:]` here (compensating
    # for an `if __name__ == "__main__": sys.exit(main(sys.argv))` guard
    # below that passed the real `sys.argv` untouched) -- an off-by-one
    # relative to every sibling, which silently ate the real `cruft-sweep`/
    # `completion-reconcile` subcommand token under in-process apply
    # dispatch (2026-07-26 arg-mismatch audit; both directives read as
    # "clean" in that audit's per-directive table, but that row was
    # spot-checked, not re-verified -- this was the actual live defect).
    args = _build_parser().parse_args(argv)

    if args.subcommand == "cruft-sweep":
        return run_cruft_sweep(
            cruft_sweep_bin=args.cruft_sweep_bin,
            state_root_script=args.state_root_script,
        )

    if args.subcommand == "completion-reconcile":
        return run_completion_reconcile(
            archive_root=args.archive_root,
            year_month=args.year_month,
            reconcile_script=args.reconcile_script,
            session_id=args.session_id,
            git_add=not args.no_git_add,
        )

    return 1  # unreachable — argparse enforces required subparser choice


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
