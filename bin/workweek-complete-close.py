"""workweek-complete-close.py — closing-orchestration CLI for /workweek-complete.

Ports the residual imperative logic that was still hand-authored inline as
bash fences in coordinator-content-repo `coordinator/commands/workweek-complete.md` (M3
chunk WWC-4, the bash-kill campaign). It is a composite entrypoint over
several concerns — one subcommand per concern — rather than N separate
scripts, matching the multi-concern chunk convention: the DoE ceremony step
will invoke this CLI by subcommand name once D2 repoints the fence.

Subcommands:
  week-start        Extract the "Week starting:" date from HEADER.md
                     (DoE workweek-complete.md Step 9.1's inline
                     `grep -m1 ... | sed ...` derivation, ported verbatim
                     as a reusable function — several ceremony steps need
                     this same value).
  archive            Step 13's week-close: move the closing week's daily
                     changelog files + priorities fragments to
                     archive/week-changelogs/<week-starting>/, move the
                     review-trail JSON to archive/review-trail/<week-starting>/
                     (deleting transient `.weekly-reviewer-scopes-*.json`
                     shards rather than archiving them), rewrite HEADER.md
                     to the reset state, and (unless --no-git) commit and
                     push the result. The commit goes through
                     run_close_commit (zero git spawns) and holds exactly the
                     files this run touched: under the default sweep, the files
                     under the closing directories plus every moved-from path.
                     A tracked file a third party hand-deleted under a swept
                     directory no longer rides the commit. Requires a session
                     id (COORDINATOR_SESSION_ID); exits 2 before moving files
                     without one.

Negative-spec — deliberately NOT ported here: the version-consistency gate
(Step 10, a bare `check-version-consistency.py` invocation) and the
post-ceremony command hook (Step 13.5, a bare `coordinator-ceremony-hook.py`
invocation) are thin single-CLI-invocation fences with no orchestration
logic of their own beyond the standard resolve-claude-klabauter-bin preamble — both
target scripts already live natively in this repo (coordinator/bin/) and
are the D1/D2 repoint's concern directly; wrapping them here would just be
re-indirection, not a port. See the WWC-4 dispatch brief's "what to port vs
leave" rule.

Spec backlink: coordinator-content-repo coordinator/commands/workweek-complete.md
    § Step 9.1 (week-start derivation, lines ~3337-3339)
    § Step 13 (archive + reset + commit + push, lines ~3762-3903)
"""
from __future__ import annotations

import argparse
import fnmatch
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from datetime import date, timedelta
from pathlib import Path

# Generator-provenance declaration (coordinator_core/ops/generator_census).
# perform_archive_files moves the closing week's daily/priorities files into
# archive/week-changelogs/<week-starting>/ and archive/review-trail/
# <week-starting>/, and rewrites state/week-changelog/HEADER.md -- a
# data-dependent target set keyed on week_starting, not a fixed artifact.
MUTATES = [
    "state/week-changelog/*.md",
    "archive/week-changelogs/**/*.md",
    "archive/review-trail/**",
]

_BIN_DIR = Path(__file__).resolve().parent


def _import_rel_id():
    # The same coordinator/bin/*.py ->
    # lib/cc_invoke.py -> coordinator_core bootstrap this diff already pays
    # for in misc-session-and-guards.py; routes this CLI's git-pathspec
    # construction through the single sanctioned wire_paths.rel_id helper
    # instead of a hand-rolled .as_posix() that would silently drift if
    # rel_id's contract is ever extended.
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import _resolve_claude_klabauter_root, require_dispatch_engine_on_path  # noqa: WPS433 (deferred, mirrors house style)

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.wire_paths import rel_id

    return rel_id


def _ensure_claude_klabauter_root_on_path() -> None:
    """Same lazy coordinator/bin/*.py -> lib/cc_invoke.py -> coordinator_core
    bootstrap as :func:`_import_rel_id` — shared here rather than
    duplicated, since the archive command needs TWO coordinator_core
    symbols (``resolve_session_id`` and ``relocate_touched_path``), not one."""
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path  # noqa: WPS433 (deferred, mirrors house style)

    require_dispatch_engine_on_path()


def _resolve_session_id_for_relocate() -> str:
    """Session-id resolution for the archive step's relocate-claim calls.

    This CLI has no pre-existing session-id resolver of its own (unlike
    e.g. workday-complete-reconcile.py's env-var/sentinel tier chain) — per
    the C5b dispatch brief, falls straight through to the canonical
    coordinator_core.session.core.resolve_session_id 4-tier chain. Never
    raises: an import failure (coordinator_core unreachable) or any
    resolution failure both degrade to "" — the plain-`shutil.move`
    fallback path this same "" also drives at the call site.
    """
    try:
        _ensure_claude_klabauter_root_on_path()
        from coordinator_core.session.core import resolve_session_id

        return resolve_session_id()
    except Exception:
        return ""


def _import_relocate_touched_path():
    """Lazy import of coordinator_core.session.scope.relocate_touched_path,
    mirroring :func:`_import_rel_id`'s bootstrap. Returns None (never
    raises) on any import failure — the call site's degrade-to-plain-move
    signal, so an unreachable helper never turns an otherwise-successful
    filesystem-only archive sweep into a hard failure."""
    try:
        _ensure_claude_klabauter_root_on_path()
        from coordinator_core.session.scope import relocate_touched_path

        return relocate_touched_path
    except Exception:
        return None


def _relocate_or_move(
    relocate_fn,
    session_id: str,
    src: Path,
    dst: Path,
    cwd: str | None = None,
) -> None:
    """Move `src` -> `dst`, routed through `relocate_touched_path` (which
    performs the move itself and, only when `src` is currently T-claimed by
    `session_id`, re-declares the claim on `dst` before moving) when both
    the helper and a resolved session id are available; falls back to a
    plain `shutil.move` otherwise, or if the helper call itself raises —
    an archive that ran is better than one that failed on bookkeeping.

    `perform_archive_files` stays filesystem-only by contract: this helper
    call is itself pure filesystem + local touched.txt bookkeeping, no git
    subprocess of its own (relocate_touched_path's own git_root/session_dir
    resolution degrades to a no-claim plain move when either is
    unavailable, e.g. under a tmp_path test fixture with no live session).

    `cwd`: passed straight through to `relocate_touched_path`'s own
    `cwd` parameter (its git-root/session-dir resolution root). Left
    default None (process cwd) preserves the pre-existing behaviour for
    the live ceremony, where the CLI's own cwd always IS the repo root;
    `_cmd_archive` supplies the resolved `--repo-root` explicitly so a
    caller invoking this CLI with a `--repo-root` override from a
    different process cwd still resolves claims against the right repo.
    """
    if relocate_fn is not None and session_id:
        try:
            relocate_fn(session_id, str(src), str(dst), cwd=cwd)
            return
        except Exception:
            pass
    shutil.move(str(src), str(dst))


def _no_console_kw() -> dict:
    """Splat-ready Windows console-suppression kwarg. Falls back to the same
    suppression kwargs computed inline (zero imports beyond ``subprocess``) on
    any resolution failure, rather than silently dropping console suppression —
    a resolution failure must never turn a quiet spawn into a visible console
    window (Review: code-reviewer P2 — matched to the pattern ccbdbecc2 applied
    to sweep-boot.py/standup.py/render-project-tracker/refresh-plugin-live-install.py)."""
    try:
        _ensure_claude_klabauter_root_on_path()
        from coordinator_core.win_portability import no_console_creationflags

        return no_console_creationflags()
    except Exception:  # noqa: BLE001 -- fail-open, matches this file's transport posture
        # `{}` off Windows, matching the primitive's own POSIX contract exactly --
        # `{"creationflags": 0}` splats harmlessly too, but a substitute that
        # disagrees with the thing it substitutes for is a trap for any caller
        # comparing against `no_console_creationflags()`.
        if os.name != "nt":
            return {}
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def _no_console_passthrough_kw() -> dict:
    """`_no_console_kw` for a child whose output must reach the operator.

    Console suppression alone makes the child bind its standard handles to the
    fresh window-less console CREATE_NO_WINDOW allocates instead of inheriting
    this process's, so its output (here: git's own add/commit/push reporting)
    is written where nobody can read it. Canonical implementation, kept in sync
    by hand because this file fails open without coordinator_core:
    `coordinator_core.win_portability.no_console_passthrough_kwargs`.
    """
    kwargs = dict(_no_console_kw())
    for key, stream in (("stdout", sys.stdout), ("stderr", sys.stderr)):
        try:
            fd = stream.fileno()
        except (AttributeError, ValueError, OSError):
            continue
        if fd >= 0:
            kwargs[key] = fd
    return kwargs


_WEEK_STARTING_RE = re.compile(r"\*\*Week starting:\*\*[ \t]*(.*)")
_DAILY_FILE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}.*\.md$")
_LEADING_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def _parse_leading_date(name: str) -> date | None:
    """Best-effort `YYYY-MM-DD` prefix parse for a filename stem. Returns
    None (never raises) on anything that doesn't parse — callers use this
    to fail safe (leave unparseable names in place) under week-scoping."""
    m = _LEADING_DATE_RE.match(name)
    if not m:
        return None
    try:
        return date.fromisoformat(m.group(1))
    except ValueError:
        return None


def _bare_week_date(value: str) -> str | None:
    """Leading `YYYY-MM-DD` of a `**Week starting:**` value, or None.

    Negative-spec: HEADER lines carry a conventional trailing annotation
    (`2026-08-31 (ISO 2026-W36)`, and fleet repos add `Prior week released:`
    style suffixes), while `--week-starting` is always a bare date. Comparing
    the two raw strings is never equal wherever the annotation is present, so
    the `--week-only` HEADER-rewrite predicate silently evaluated False for
    every annotated HEADER: the run exited 0, moved files correctly, reported
    success, and left the closing week's HEADER naming the archived week.
    Reported by example-game-repo-em 2026-09-06. `derive_week_start` deliberately keeps
    returning the FULL annotated value — `_cmd_week_start` prints it and
    callers may depend on the annotation — so normalisation happens only at the
    comparison site. Returns None for the "(not yet set ...)" sentinel, which
    must never compare equal to a real week.
    """
    m = _LEADING_DATE_RE.match(value.strip())
    return m.group(1) if m else None


def _week_window(d: date, week_anchor: date) -> tuple[date, date]:
    """`coordinator_core.cadence.period_mode.week_window`, imported through the
    same lazy bootstrap as the other coordinator_core symbols this CLI needs."""
    _ensure_claude_klabauter_root_on_path()
    from coordinator_core.cadence.period_mode import week_window

    return week_window(d, week_anchor)


def _is_excluded(name: str, exclude: Sequence[str]) -> bool:
    """True when `name` matches any fnmatch pattern in `exclude`."""
    return any(fnmatch.fnmatchcase(name, pat) for pat in exclude)


# ---------------------------------------------------------------------------
# week-start
# ---------------------------------------------------------------------------


def derive_week_start(header_path: Path) -> str:
    """Extract the `**Week starting:** YYYY-MM-DD` value from HEADER.md.

    Port of the DoE bash fence's `grep -m1 '\\*\\*Week starting:\\*\\*'
    state/week-changelog/HEADER.md | sed 's/.*\\*\\*Week starting:\\*\\*[[:space:]]*//'`.

    Divergence from the bash oracle (deliberate, noted in the WWC-4 executor
    report): the bash version silently produced an empty string when the
    line was absent, which then flowed unchecked into a `--since ""` query
    downstream. This port fails loud instead — an unresolvable week-start is
    exactly the kind of silent-corruption-risk this campaign exists to close
    (a downstream `--since ""` query would scope-inflate to "since forever"
    rather than fail visibly).
    """
    try:
        content = header_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"week-start: cannot read {header_path}: {exc}")
    for line in content.splitlines():
        m = _WEEK_STARTING_RE.search(line)
        if m:
            value = m.group(1).strip()
            if value:
                return value
            break
    raise SystemExit(
        f"week-start: no '**Week starting:**' value found in {header_path} "
        "— HEADER.md missing/corrupt, or /workweek-start was never run this week"
    )


def _cmd_week_start(args: argparse.Namespace) -> int:
    print(derive_week_start(Path(args.header)))
    return 0


# ---------------------------------------------------------------------------
# archive
# ---------------------------------------------------------------------------


# The directory-convention comment is carried IN FULL here, not abbreviated to a
# pointer. It previously read "<!-- Directory convention: [see HEADER.md comment
# block] -->" — a pointer whose only referent is the very block it replaced, so
# every HEADER rewrite silently destroyed the sole in-repo explanation of the
# daily-block / priorities-fragment / archive-on-complete convention and left a
# self-reference resolving to nothing. Found 2026-08-06 after a reviewer flagged
# the loss on a written HEADER; the artifact was restored first and only then was
# this producer identified as the actual source. Keep this text in sync with the
# convention it documents, and never re-abbreviate it to a pointer.
_HEADER_TEMPLATE = (
    "# Week Changelog\n\n"
    "<!-- Directory convention:\n"
    "     state/week-changelog/ holds the current week's changelog state.\n"
    "     HEADER.md (this file) is written by /workweek-complete on reset and by\n"
    "     /workweek-start on re-run. It is the only shared file in this directory\n"
    "     — all other files are per-machine daily blocks (YYYY-MM-DD-{{hostname}}.md)\n"
    "     written by /workday-complete, which avoids concurrent-write conflicts.\n\n"
    "     Priorities are NOT stored inline in HEADER.md — each /workweek-start\n"
    "     writer owns its own fragment file, HEADER.priorities.<SID_SHORT>.md,\n"
    "     to avoid a second collaborator's /workweek-start silently overwriting\n"
    "     the first's priorities in the same week. Readers merge all fragments\n"
    "     on read.\n\n"
    "     On /workweek-complete, the full directory (daily files + fragments +\n"
    "     old HEADER) is archived to archive/week-changelogs/<week-start>/ before\n"
    "     HEADER is rewritten and fragments are cleared.\n"
    "     coordinator/bin/check-weekly-staleness.py (.cmd on Windows) reads this\n"
    "     file to compute the staleness signal.\n"
    "-->\n\n"
    "**Week starting:** (not yet set — run /workweek-start to initialise)\n"
    "**Prior week released:** {version} (commit {merge_sha}, {released_date})\n"
    "**Last /workweek-start:** (none)\n"
    "**Priorities (from /workweek-start):** see `HEADER.priorities.*.md` fragments "
    "— none yet; run /workweek-start to set priorities.\n"
)


def perform_archive_files(
    week_changelog_dir: Path,
    archive_week_root: Path,
    review_trail_dir: Path,
    review_trail_archive_root: Path,
    week_starting: str,
    version: str,
    merge_sha: str,
    released_date: str,
    week_only: bool = False,
    move_priorities: bool = False,
    clean_shards: bool = False,
    week_ending: str | None = None,
    exclude: Sequence[str] = (),
    session_id: str = "",
    relocate_fn=None,
    relocate_cwd: str | None = None,
    touched_out: list[Path] | None = None,
) -> list[str]:
    """Step 13's file-move + HEADER.md reset, filesystem-only (no git).

    `week_only` (default False, byte-for-byte-identical live-ceremony
    behaviour): when True, scopes the changelog + review-trail moves to the
    half-open `[week_starting, week_starting + 7 days)` window — needed for
    a multi-week backfill run over a directory holding more than one week's
    files, where the unscoped sweep would incorrectly carry off the live
    in-flight week's artifacts too. `move_priorities` gates the
    `HEADER.priorities.*.md` fragment move independently: under
    `week_only`, only the fragment-owning week's caller should pass True;
    when `week_only` is False this parameter is ignored (fragments always
    move, matching prior behaviour). `clean_shards` gates transient
    `.weekly-reviewer-scopes-*.json` shard cleanup the same way under
    `week_only`: default False leaves shards untouched (a `week_only` run
    generally cannot attribute a shard to a specific week), and a caller
    closing the live week at a real week boundary passes True to reach
    byte-parity with the unscoped (`week_only=False`) path, which always
    deletes them. Ignored when `week_only` is False.

    `week_ending` (`YYYY-MM-DD`, inclusive) and `exclude` (fnmatch patterns on
    the bare filename) refine the `week_only` window and are ignored when
    `week_only` is False. `week_ending` closes a partial week: an ISO week
    straddling two releases archives only through the release day, leaving
    later files in place. `exclude` keeps named files out of both the
    changelog and review-trail sweeps — chiefly the live
    `YYYY-MM-DD-pending-release.md` accumulator, which the date-prefix match
    otherwise sweeps. Both default to the prior behaviour.

    `session_id` / `relocate_fn`: every real content-file move below (daily
    changelogs, priorities fragments, review-trail records) is routed
    through `_relocate_or_move`, which re-declares a T-claim on the new path
    when the source was claimed by `session_id` (plan
    docs/plans/2026-08-06-relocation-re-declares-the-touch-claim.md, C5b) —
    a plain `shutil.move` would silently strand it. Both default to the
    inert "always plain-move" case (`session_id=""`, `relocate_fn=None`),
    so this function stays filesystem-only-by-contract: no git subprocess
    of its own, callable exactly as before by any test/caller that doesn't
    pass them. `relocate_cwd` (default None -> process cwd, matching the
    live ceremony's own invocation) is the git-root/session-dir resolution
    root `_relocate_or_move` forwards to `relocate_fn` — `_cmd_archive`
    supplies the resolved `--repo-root` so a `--repo-root` override still
    resolves claims against the correct repo rather than process cwd.

    `touched_out` (optional, appended to in place): every path this run
    actually created, moved from, or rewrote. Under `week_only` the caller
    stages THIS list rather than the whole `state/week-changelog` and
    `state/review-trail` directories — a week-scoped run touches a subset,
    and directory-wide pathspecs sweep peers' uncommitted files on a shared
    tree. Reported by example-game-repo-em 2026-09-06, who worked around it with
    `--no-git`.

    Returns a list of human-readable action lines for the caller to print/log.
    """
    actions: list[str] = []
    touched = touched_out if touched_out is not None else []
    week_starting_date = date.fromisoformat(week_starting) if week_only else None
    week_ending_date = (
        date.fromisoformat(week_ending) if week_only and week_ending else None
    )
    if week_ending_date is not None and week_ending_date < week_starting_date:
        raise SystemExit(
            f"archive: --week-ending {week_ending} precedes --week-starting {week_starting}"
        )
    exclude = exclude if week_only else ()
    window_start = window_end = None
    if week_starting_date is not None:
        window_start, window_end = _week_window(week_starting_date, week_starting_date)
        if week_ending_date is not None:
            window_end = min(window_end, week_ending_date + timedelta(days=1))

    archive_dest = archive_week_root / week_starting
    archive_dest.mkdir(parents=True, exist_ok=True)

    # Daily files (bare YYYY-MM-DD.md) and any YYYY-MM-DD-pending-release.md
    # fragment — matched by leading-date pattern, which structurally excludes
    # HEADER.md and HEADER.priorities.*.md (neither starts with a date).
    for f in sorted(week_changelog_dir.glob("*.md")):
        if _DAILY_FILE_RE.match(f.name):
            if week_only:
                d = _parse_leading_date(f.name)
                if (
                    d is None
                    or not (window_start <= d < window_end)
                    or _is_excluded(f.name, exclude)
                ):
                    continue
            dest_dir = archive_dest
            if not week_only:
                d = _parse_leading_date(f.name)
                dest_dir = archive_week_root / (
                    week_starting
                    if d is None
                    else _week_window(d, date.fromisoformat(week_starting))[0].isoformat()
                )
                dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / f.name
            _relocate_or_move(relocate_fn, session_id, f, dest, cwd=relocate_cwd)
            actions.append(f"moved {f} -> {dest}")
            touched.extend((f, dest))

    # Priorities fragments — merged into the closing week's historical
    # record alongside the daily files that satisfied (or didn't) them.
    # Under week_only, gated by the separate move_priorities opt-in (only
    # the fragment-owning week's caller should sweep these).
    if not week_only or move_priorities:
        for f in sorted(week_changelog_dir.glob("HEADER.priorities.*.md")):
            dest = archive_dest / f.name
            _relocate_or_move(relocate_fn, session_id, f, dest, cwd=relocate_cwd)
            actions.append(f"moved {f} -> {dest}")
            touched.extend((f, dest))

    # Review-trail: archive real records, delete transient shards, leave
    # .gitkeep in place so the directory stays tracked after the sweep.
    review_trail_dest = review_trail_archive_root / week_starting
    review_trail_dest.mkdir(parents=True, exist_ok=True)
    if review_trail_dir.is_dir():
        for f in sorted(review_trail_dir.iterdir()):
            if not f.is_file() or f.name == ".gitkeep":
                continue
            if f.name.startswith(".weekly-reviewer-scopes-") and f.name.endswith(".json"):
                # Under week_only, transient shards are left untouched by
                # default — they may belong to the live in-flight week and
                # this leg has no way to attribute them to a specific week.
                # clean_shards opts back in for the caller closing the live
                # week, mirroring move_priorities's gate above.
                if week_only and not clean_shards:
                    continue
                f.unlink()
                actions.append(f"deleted transient shard {f}")
                touched.append(f)
                continue
            # Any other file (any extension, not just .json) is a real
            # review-trail record — the extension is not what makes it one.
            # This is the one sanctioned default-path behaviour change: a
            # stranded non-.json record (e.g. a .md finding left behind by
            # an earlier sweep) is now archived like every other record
            # instead of being left behind forever.
            if week_only:
                d = _parse_leading_date(f.name)
                if (
                    d is None
                    or not (window_start <= d < window_end)
                    or _is_excluded(f.name, exclude)
                ):
                    # Unparseable, out-of-window, or excluded — fail-safe,
                    # leave in place.
                    continue
            dest = review_trail_dest / f.name
            _relocate_or_move(relocate_fn, session_id, f, dest, cwd=relocate_cwd)
            actions.append(f"moved {f} -> {dest}")
            touched.extend((f, dest))

    header_path = week_changelog_dir / "HEADER.md"
    # Defect 2: an unconditional rewrite here is correct at a real week
    # boundary (week_only=False, the live /workweek-complete ceremony) but
    # wrong when week_only scopes this run to a historical week — HEADER.md
    # declares the *live* week, and a historical-week archive run must not
    # reset it out from under the in-flight week. Predicate: under
    # week_only, only rewrite when HEADER currently declares the same
    # week_starting this run is archiving (i.e. this run IS the one closing
    # that live week). If HEADER declares a different week, or still carries
    # the "(not yet set …)" sentinel (no live week declared at all, nothing
    # for this run to be closing), skip the rewrite — matching-only, no
    # special-casing needed since the sentinel never equals a real
    # YYYY-MM-DD week_starting value.
    # `--version none` is the catch-up directive for a missed week: no release
    # happened, so HEADER carries no release record to write and stays untouched.
    should_rewrite_header = version != "none"
    if should_rewrite_header and week_only:
        currently_declared = _bare_week_date(derive_week_start(header_path))
        should_rewrite_header = (
            currently_declared is not None and currently_declared == week_starting
        )

    if should_rewrite_header:
        header_path.write_text(
            _HEADER_TEMPLATE.format(version=version, merge_sha=merge_sha, released_date=released_date),
            encoding="utf-8", newline="\n",
        )
        actions.append(f"rewrote {header_path}")
        touched.append(header_path)

    return actions


def _expand_to_files(
    directories: Sequence[Path], repo_root: Path, rel_id: Callable[[Path, Path], str]
) -> list[str]:
    """Posix repo-relative file paths under `directories` (any depth). The
    commit takes files, never a directory pathspec."""
    return [
        rel_id(f, repo_root)
        for d in directories
        for f in sorted(d.rglob("*"))
        if f.is_file()
    ]


def commit_archive(
    repo_root: Path,
    stage_rels: Sequence[str],
    message: str,
    session_id: str,
) -> int:
    """Commit exactly `stage_rels` (posix, repo-relative; moved-from paths
    included, absent on disk) through `run_close_commit` -- zero git spawns.

    Returns 0 on a landed commit or a benign empty one, 1 on a refused commit.
    Trap: a path absent from disk is declared in `deleted_paths`, which
    `run_close_commit` also requires it to appear in `stage_paths`.
    """
    _ensure_claude_klabauter_root_on_path()
    from coordinator_core.git.git_state import head_blobs
    from coordinator_core.workstream_complete.directives_commit_tail import run_close_commit

    ordered = list(dict.fromkeys(stage_rels))
    absent = {p for p in ordered if not (repo_root / p).exists()}
    tracked = head_blobs(repo_root, sorted(absent))
    # An absent path HEAD never carried (a moved untracked file) is no deletion
    # and no stage entry: only its destination is committed.
    deleted = [p for p in ordered if p in absent and p in tracked]
    stage = [p for p in ordered if p not in absent or p in tracked]
    outcome = run_close_commit(
        repo_root,
        session_id=session_id,
        subject=message,
        stage_paths=stage,
        deleted_paths=deleted,
    )
    for line in outcome.diagnostics:
        print(f"archive: {line}", file=sys.stderr)
    if outcome.commit_failed:
        print("archive: commit refused — see diagnostics above", file=sys.stderr)
        return 1
    return 0


def push_current_branch(repo_root: Path) -> int:
    """The one remote leg: `git push origin HEAD` for the checked-out branch.

    Trap: `HEAD` rather than the branch name -- `.git/HEAD` can store a
    ref's case differently from the on-disk ref file on a case-insensitive
    filesystem, and a name pushed from there fails to resolve; `HEAD`
    resolves through the ref file itself. A detached HEAD refuses.
    """
    _ensure_claude_klabauter_root_on_path()
    from coordinator_core.git.git_state import head_branch

    branch = head_branch(repo_root)
    if not branch or branch == "HEAD":
        print("archive: could not resolve current branch — skipping push", file=sys.stderr)
        return 1
    rc = subprocess.run(
        ["git", "push", "origin", "HEAD"], cwd=repo_root, **_no_console_passthrough_kw()
    ).returncode
    if rc:
        print(
            f"archive: git push exited {rc} — the commit landed; re-run only the push",
            file=sys.stderr,
        )
    return rc


def _cmd_archive(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    if (repo_root / ".generated-mirror").exists():
        print(
            "REFUSED: generated-mirror — changelog rituals do not run in a "
            "generated-mirror repo; nothing moved",
            file=sys.stderr,
        )
        return 1
    week_changelog_dir = repo_root / args.week_changelog_dir
    archive_week_root = repo_root / args.archive_root
    review_trail_dir = repo_root / args.review_trail_dir
    review_trail_archive_root = repo_root / args.review_trail_archive_root

    header_path = week_changelog_dir / "HEADER.md"
    week_starting = args.week_starting or _bare_week_date(derive_week_start(header_path))
    if week_starting is None:
        print(
            f"archive: no dated 'Week starting:' in {header_path} — pass --week-starting; nothing moved",
            file=sys.stderr,
        )
        return 2
    released_date = args.released_date or date.today().isoformat()

    if args.move_priorities and not args.week_only:
        # --move-priorities is a no-op
        # without --week-only (fragments already move unconditionally on
        # the default sweep-everything path). Printed note only, never a
        # parser error or behaviour change -- a caller who genuinely wants
        # today's default sweep must still be able to pass both flags
        # combined with any other archive invocation without failing.
        print(
            "archive: note: --move-priorities has no effect without --week-only "
            "(fragments already move on the default sweep-everything path)",
            file=sys.stderr,
        )

    if (args.week_ending or args.exclude) and not args.week_only:
        print(
            "archive: note: --week-ending/--exclude have no effect without --week-only",
            file=sys.stderr,
        )

    session_id = _resolve_session_id_for_relocate()
    if not args.no_git and not session_id:
        print(
            "archive: no session id resolved — set COORDINATOR_SESSION_ID "
            "(the commit carries a Session-Id trailer); nothing moved",
            file=sys.stderr,
        )
        return 2

    touched: list[Path] = []
    actions = perform_archive_files(
        week_changelog_dir,
        archive_week_root,
        review_trail_dir,
        review_trail_archive_root,
        week_starting,
        args.version,
        args.merge_sha,
        released_date,
        week_only=args.week_only,
        move_priorities=args.move_priorities,
        clean_shards=args.clean_shards,
        week_ending=args.week_ending,
        exclude=args.exclude,
        session_id=session_id,
        relocate_fn=_import_relocate_touched_path(),
        relocate_cwd=str(repo_root),
        touched_out=touched,
    )
    for line in actions:
        print(line)

    if args.no_git:
        return 0

    commit_message = (
        f"chore(workweek-complete): archive week {week_starting}, "
        f"reset changelog + review-trail {args.version}"
    )
    rel_id = _import_rel_id()
    # Posix-form (`rel_id`, not `str()`): a Windows backslash is git's
    # pathspec escape character and silently collapses the path.
    touched_rels = list(dict.fromkeys(rel_id(t, repo_root) for t in touched))
    if args.week_only:
        # Negative-spec: a week-scoped run must NEVER stage the four
        # directories wholesale — a directory sweep commits a peer's
        # in-flight daily block or review record under this run's message.
        stage = touched_rels
    else:
        # Default sweep: the closing directories' files plus every moved-from
        # path (absent on disk, so the walk cannot see it). An empty
        # directory contributes no file.
        candidate_dirs = [
            week_changelog_dir,
            archive_week_root / week_starting,
            review_trail_dir,
            review_trail_archive_root / week_starting,
        ]
        candidate_dirs += sorted(
            {t.parent for t in touched if t.parent.parent == archive_week_root}
            - set(candidate_dirs)
        )
        stage = list(
            dict.fromkeys(
                _expand_to_files(candidate_dirs, repo_root, rel_id) + touched_rels
            )
        )
    if not stage:
        print("archive: nothing touched — no commit made", file=sys.stderr)
        return 0
    rc = commit_archive(repo_root, stage, commit_message, session_id)
    if rc or args.no_push:
        return rc
    return push_current_branch(repo_root)


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Closing-orchestration CLI for /workweek-complete (week-start "
        "derivation, week-close archive+push)."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_week_start = sub.add_parser("week-start", help="Print the Week starting: date from HEADER.md.")
    p_week_start.add_argument(
        "--header", default="state/week-changelog/HEADER.md", help="Path to HEADER.md (cwd-relative)."
    )
    p_week_start.set_defaults(func=_cmd_week_start)

    p_archive = sub.add_parser("archive", help="Step 13: archive the closing week + reset HEADER.md + commit + push.")
    p_archive.add_argument("--repo-root", default=".", help="Repo root (default: cwd).")
    p_archive.add_argument("--week-changelog-dir", default="state/week-changelog", help="Repo-root-relative.")
    p_archive.add_argument("--archive-root", default="archive/week-changelogs", help="Repo-root-relative.")
    p_archive.add_argument("--review-trail-dir", default="state/review-trail", help="Repo-root-relative.")
    p_archive.add_argument("--review-trail-archive-root", default="archive/review-trail", help="Repo-root-relative.")
    p_archive.add_argument("--week-starting", default=None, help="Override (default: derive from HEADER.md before rewrite).")
    p_archive.add_argument("--version", required=True, help="Released version, e.g. v2.7.0.")
    p_archive.add_argument("--merge-sha", required=True, help="Merge commit SHA for the HEADER.md 'Prior week released:' line.")
    p_archive.add_argument("--released-date", default=None, help="Default: today (local date).")
    p_archive.add_argument("--no-git", action="store_true", help="Skip git add/commit/push entirely (file moves only).")
    p_archive.add_argument("--no-push", action="store_true", help="Commit but skip the push.")
    p_archive.add_argument(
        "--week-only",
        action="store_true",
        help="Scope changelog + review-trail moves to [week_starting, week_starting+7d); "
        "leave transient reviewer-scope shards and unparseable-name records untouched. "
        "Default False preserves today's sweep-everything behaviour (live ceremony).",
    )
    p_archive.add_argument(
        "--move-priorities",
        action="store_true",
        help="Under --week-only, also move HEADER.priorities.*.md fragments (only the "
        "fragment-owning week's caller should pass this). Ignored when --week-only is not set.",
    )
    p_archive.add_argument(
        "--clean-shards",
        action="store_true",
        help="Under --week-only, also delete transient .weekly-reviewer-scopes-*.json "
        "shards (only the caller closing the live week at a real week boundary should "
        "pass this, to reach parity with the unscoped path). Ignored when --week-only "
        "is not set.",
    )
    p_archive.add_argument(
        "--week-ending",
        default=None,
        metavar="YYYY-MM-DD",
        help="Under --week-only, inclusive last day of the archived window "
        "(closes a partial week when a release ships mid-week; files dated "
        "after it stay in place). Ignored when --week-only is not set.",
    )
    p_archive.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="PATTERN",
        help="Under --week-only, fnmatch pattern on the bare filename to leave "
        "in place (repeatable), e.g. '*-pending-release.md' to keep the live "
        "accumulator out of the sweep. Ignored when --week-only is not set.",
    )
    p_archive.set_defaults(func=_cmd_archive)

    return parser


def main(argv: list[str]) -> int:
    # `argv` is args-only (no leading program-name token) -- the convention
    # every sibling consumes-manifest CLI's `main(argv)` follows (see e.g.
    # `workday-complete-reconcile.py`'s identical comment, and
    # `workweek_complete.apply._invoke_cli_main`, which calls
    # `main_fn(list(directive_args))` in-process with no argv[0]
    # placeholder). This function previously did `argv[1:]` here, an
    # off-by-one relative to every sibling that silently ate the first real
    # flag under in-process apply dispatch (2026-07-27 arg-mismatch audit —
    # mirrors the 2026-07-26 fix to `workday-complete-reconcile.py`'s
    # identical defect).
    args = _build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
