"""workweek-complete-close.py — closing-orchestration CLI for /workweek-complete.

Ports the residual imperative logic that was still hand-authored inline as
bash fences in DoE-claude `coordinator/commands/workweek-complete.md` (M3
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
  reconcile-sweep    Step 9.1.5's detect-only pending-release reconcile
                     backstop: query pending-release completion entries
                     since the week start, and for each one dispatch the
                     co-located reconcile-completion-commits.py in
                     detect-only mode, surfacing any unaccounted session
                     commits. Sibling in spirit to the already-ported
                     workday-start-reconcile-sweep.py / workday-complete-
                     reconcile.py — same authored_by-keyed dispatch shape,
                     different entry-selection query (this ceremony scans
                     by week-start date via query-completions.py rather
                     than a bounded today/yesterday archive/completed scan).
  archive            Step 13's week-close: move the closing week's daily
                     changelog files + priorities fragments to
                     archive/week-changelogs/<week-starting>/, move the
                     review-trail JSON to archive/review-trail/<week-starting>/
                     (deleting transient `.weekly-reviewer-scopes-*.json`
                     shards rather than archiving them), rewrite HEADER.md
                     to the reset state, and (unless --no-git) commit and
                     push the result.

Negative-spec — deliberately NOT ported here: the version-consistency gate
(Step 10, a bare `check-version-consistency.py` invocation) and the
post-ceremony command hook (Step 13.5, a bare `coordinator-ceremony-hook.py`
invocation) are thin single-CLI-invocation fences with no orchestration
logic of their own beyond the standard resolve-claude-klabauter-bin preamble — both
target scripts already live natively in this repo (coordinator/bin/) and
are the D1/D2 repoint's concern directly; wrapping them here would just be
re-indirection, not a port. See the WWC-4 dispatch brief's "what to port vs
leave" rule.

Spec backlink: DoE-claude coordinator/commands/workweek-complete.md
    § Step 9.1 (week-start derivation, lines ~3337-3339)
    § Step 9.1.5 (reconcile sweep, lines ~3358-3505)
    § Step 13 (archive + reset + commit + push, lines ~3762-3903)
Spec backlink: docs/plans/2026-06-27-post-summary-completion-loop-closure.md § C5b
    (Step 9.1.5's detect-only backstop rationale — shared with the
    workday-side reconcile sweeps)
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

# Generator-provenance declaration (generator_provenance.py).
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
_LIB_DIR = _BIN_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))


def _import_rel_id():
    # Review: code-reviewer Finding 2 — the same coordinator/bin/*.py ->
    # lib/cc_invoke.py -> coordinator_core bootstrap this diff already pays
    # for in misc-session-and-guards.py; routes this CLI's git-pathspec
    # construction through the single sanctioned wire_paths.rel_id helper
    # instead of a hand-rolled .as_posix() that would silently drift if
    # rel_id's contract is ever extended.
    from cc_invoke import _resolve_claude_klabauter_root  # noqa: WPS433 (deferred, mirrors house style)

    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.wire_paths import rel_id

    return rel_id


def _ensure_claude_klabauter_root_on_path() -> None:
    """Same lazy coordinator/bin/*.py -> lib/cc_invoke.py -> coordinator_core
    bootstrap as :func:`_import_rel_id` — shared here rather than
    duplicated, since the archive command needs TWO coordinator_core
    symbols (``resolve_session_id`` and ``relocate_touched_path``), not one."""
    from cc_invoke import _resolve_claude_klabauter_root  # noqa: WPS433 (deferred, mirrors house style)

    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)


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


_DELTA_RE = re.compile(r"delta=(\d+)")
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


def _in_week_window(d: date, week_starting: date) -> bool:
    """Half-open `[week_starting, week_starting + 7 days)` membership."""
    return week_starting <= d < (week_starting + timedelta(days=7))


def _bin_dir() -> Path:
    """This script's own directory — every sibling CLI it dispatches to
    (query-completions.py, reconcile-completion-commits.py,
    coordinator-current-branch.py) is co-located here. Path(__file__)-relative,
    never cwd-relative, so this CLI is self-resolving regardless of caller cwd."""
    return Path(__file__).resolve().parent


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
# reconcile-sweep
# ---------------------------------------------------------------------------


def _frontmatter_field(content: str, key: str) -> str:
    """First `^{key}:` value within the leading `---`...`---` frontmatter
    fence; "" if the fence never closes or the key is absent."""
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
    """`authored_by:` value with a trailing ` # comment` and surrounding
    double-quotes stripped, mirroring the bash oracle's awk scrub
    (`sub(/[[:space:]]*#.*$/,"",v); gsub(/^"|"$/,"",v)`)."""
    raw = _frontmatter_field(content, "authored_by")
    raw = re.sub(r"[ \t]*#.*$", "", raw)
    if len(raw) >= 2 and raw.startswith('"') and raw.endswith('"'):
        raw = raw[1:-1]
    return raw


def _query_pending_release_paths(query_script: str, since: str, limit: int) -> list[str]:
    """Invoke the co-located query-completions.py to list pending-release
    completion-entry paths since `since`. Returns [] on a non-zero exit
    (mirrors the bash fence, which had no dedicated failure path here —
    an empty $RECONCILE_PATHS just means the for-loop body never runs)."""
    try:
        result = subprocess.run(
            [
                sys.executable,
                query_script,
                "--since",
                since,
                "--where",
                "status=pending-release",
                "--format",
                "paths",
                "--limit",
                str(limit),
            ],
            capture_output=True,
            text=True,
            **_no_console_kw(),
        )
    except OSError:
        return []
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def _run_reconcile_helper(reconcile_script: str, session_id: str, entry_path: str) -> tuple[int, str]:
    """Invoke reconcile-completion-commits.py in detect-only mode (never
    --append — this sweep is a cross-session bulk over entries not
    necessarily authored by the current session). Stderr is discarded,
    mirroring the bash fence's `2>/dev/null` on this call."""
    try:
        result = subprocess.run(
            [sys.executable, reconcile_script, "--session-id", session_id, entry_path],
            capture_output=True,
            text=True,
            **_no_console_kw(),
        )
    except OSError as exc:
        return 2, str(exc)
    return result.returncode, result.stdout


def run_reconcile_sweep(entry_paths: list[str], reconcile_script: str, out=sys.stdout, err=sys.stderr) -> int:
    """Detect-only reconcile pass over an already-resolved entry-path list
    (Step 9.1.5's pre-release backstop). Advisory only — always returns 0;
    the ceremony does NOT hard-fail on unaccounted commits."""
    for entry_path in entry_paths:
        try:
            content = Path(entry_path).read_text(encoding="utf-8")
        except OSError:
            continue

        authored_by = _authored_by_field(content)
        if not authored_by or authored_by == "null":
            continue

        rc, stdout = _run_reconcile_helper(reconcile_script, authored_by, entry_path)
        if rc != 0:
            # Advisory-only sweep — a helper failure is surfaced, not fatal.
            continue

        m = _DELTA_RE.search(stdout)
        if m and int(m.group(1)) > 0:
            print(
                f"⚠ entry {Path(entry_path).name}: {m.group(1)} session "
                "commit(s) unaccounted — reconcile before release",
                file=out,
            )
    return 0


def _default_query_script() -> str:
    return str(_bin_dir() / "query-completions.py")


def _default_reconcile_script() -> str:
    return str(_bin_dir() / "reconcile-completion-commits.py")


def _cmd_reconcile_sweep(args: argparse.Namespace) -> int:
    since = args.since or derive_week_start(Path(args.header))
    if args.entries_file:
        entry_paths = [
            line for line in Path(args.entries_file).read_text(encoding="utf-8").splitlines() if line.strip()
        ]
    else:
        entry_paths = _query_pending_release_paths(args.query_script, since, args.limit)
    return run_reconcile_sweep(entry_paths, args.reconcile_script)


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
    session_id: str = "",
    relocate_fn=None,
    relocate_cwd: str | None = None,
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
    move, matching prior behaviour).

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

    Returns a list of human-readable action lines for the caller to print/log.
    """
    actions: list[str] = []
    week_starting_date = date.fromisoformat(week_starting) if week_only else None

    archive_dest = archive_week_root / week_starting
    archive_dest.mkdir(parents=True, exist_ok=True)

    # Daily files (bare YYYY-MM-DD.md) and any YYYY-MM-DD-pending-release.md
    # fragment — matched by leading-date pattern, which structurally excludes
    # HEADER.md and HEADER.priorities.*.md (neither starts with a date).
    for f in sorted(week_changelog_dir.glob("*.md")):
        if _DAILY_FILE_RE.match(f.name):
            if week_only:
                d = _parse_leading_date(f.name)
                if d is None or not _in_week_window(d, week_starting_date):
                    continue
            dest = archive_dest / f.name
            _relocate_or_move(relocate_fn, session_id, f, dest, cwd=relocate_cwd)
            actions.append(f"moved {f} -> {dest}")

    # Priorities fragments — merged into the closing week's historical
    # record alongside the daily files that satisfied (or didn't) them.
    # Under week_only, gated by the separate move_priorities opt-in (only
    # the fragment-owning week's caller should sweep these).
    if not week_only or move_priorities:
        for f in sorted(week_changelog_dir.glob("HEADER.priorities.*.md")):
            dest = archive_dest / f.name
            _relocate_or_move(relocate_fn, session_id, f, dest, cwd=relocate_cwd)
            actions.append(f"moved {f} -> {dest}")

    # Review-trail: archive real records, delete transient shards, leave
    # .gitkeep in place so the directory stays tracked after the sweep.
    review_trail_dest = review_trail_archive_root / week_starting
    review_trail_dest.mkdir(parents=True, exist_ok=True)
    if review_trail_dir.is_dir():
        for f in sorted(review_trail_dir.iterdir()):
            if not f.is_file() or f.name == ".gitkeep":
                continue
            if f.name.startswith(".weekly-reviewer-scopes-") and f.name.endswith(".json"):
                # Under week_only, transient shards are left untouched
                # entirely — they may belong to the live in-flight week and
                # this leg has no way to attribute them to a specific week.
                if week_only:
                    continue
                f.unlink()
                actions.append(f"deleted transient shard {f}")
                continue
            # Any other file (any extension, not just .json) is a real
            # review-trail record — the extension is not what makes it one.
            # This is the one sanctioned default-path behaviour change: a
            # stranded non-.json record (e.g. a .md finding left behind by
            # an earlier sweep) is now archived like every other record
            # instead of being left behind forever.
            if week_only:
                d = _parse_leading_date(f.name)
                if d is None or not _in_week_window(d, week_starting_date):
                    # Unparseable or out-of-window — fail-safe, leave in place.
                    continue
            dest = review_trail_dest / f.name
            _relocate_or_move(relocate_fn, session_id, f, dest, cwd=relocate_cwd)
            actions.append(f"moved {f} -> {dest}")

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
    should_rewrite_header = True
    if week_only:
        currently_declared = derive_week_start(header_path)
        should_rewrite_header = currently_declared == week_starting

    if should_rewrite_header:
        header_path.write_text(
            _HEADER_TEMPLATE.format(version=version, merge_sha=merge_sha, released_date=released_date),
            encoding="utf-8",
        )
        actions.append(f"rewrote {header_path}")

    return actions


def _resolve_branch(repo_root: Path, branch_script: str) -> str:
    result = subprocess.run(
        [sys.executable, branch_script],
        cwd=repo_root,
        capture_output=True,
        text=True,
        **_no_console_kw(),
    )
    return result.stdout.strip()


def git_commit_and_push(
    repo_root: Path,
    paths: list[str],
    message: str,
    branch_script: str,
    push: bool = True,
) -> int:
    """Step 13's `git add -- <paths> && git commit -m <message> && git push
    origin <branch>` tail, using coordinator-current-branch.py for the
    canonical (case-correct) branch name rather than `git branch
    --show-current` — see that script's own docstring for why."""
    subprocess.run(
        ["git", "add", "--", *paths], cwd=repo_root, check=True, **_no_console_passthrough_kw()
    )
    # A3 fix: pathspec-scoped commit, not a bare `git commit -m`. This runs
    # on a shared branch (other executors/EMs may have their own staged
    # work in the index concurrently) -- a bare commit absorbs whatever else
    # is staged. Scope to exactly the paths this function staged above.
    subprocess.run(
        ["git", "commit", "-m", message, "--", *paths],
        cwd=repo_root,
        check=True,
        **_no_console_passthrough_kw(),
    )
    if push:
        branch = _resolve_branch(repo_root, branch_script)
        if not branch:
            print("archive: could not resolve current branch — skipping push", file=sys.stderr)
            return 1
        subprocess.run(
            ["git", "push", "origin", branch], cwd=repo_root, check=True, **_no_console_passthrough_kw()
        )
    return 0


def _cmd_archive(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    week_changelog_dir = repo_root / args.week_changelog_dir
    archive_week_root = repo_root / args.archive_root
    review_trail_dir = repo_root / args.review_trail_dir
    review_trail_archive_root = repo_root / args.review_trail_archive_root

    week_starting = args.week_starting or derive_week_start(week_changelog_dir / "HEADER.md")
    released_date = args.released_date or date.today().isoformat()

    if args.move_priorities and not args.week_only:
        # Review: code-reviewer Finding 2 -- --move-priorities is a no-op
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
        session_id=_resolve_session_id_for_relocate(),
        relocate_fn=_import_relocate_touched_path(),
        relocate_cwd=str(repo_root),
    )
    for line in actions:
        print(line)

    if args.no_git:
        return 0

    branch_script = args.branch_script or str(_bin_dir() / "coordinator-current-branch.py")
    commit_message = (
        f"chore(workweek-complete): archive week {week_starting}, "
        f"reset changelog + review-trail {args.version}"
    )
    rel_id = _import_rel_id()
    return git_commit_and_push(
        repo_root,
        [
            # A3 fix: posix-form (`rel_id`, not `str()`) — these strings
            # feed `git add -- *paths` below, and on Windows `str(...)`
            # renders `state\week-changelog`. `\` is git's pathspec ESCAPE
            # character, so the pathspec silently collapses to
            # `stateweek-changelog`, matches nothing, and the `check=True`
            # `git add` call raises `CalledProcessError`, killing the weekly
            # archive on every Windows session.
            rel_id(week_changelog_dir, repo_root),
            rel_id(archive_week_root / week_starting, repo_root),
            rel_id(review_trail_dir, repo_root),
            rel_id(review_trail_archive_root / week_starting, repo_root),
        ],
        commit_message,
        branch_script,
        push=not args.no_push,
    )


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Closing-orchestration CLI for /workweek-complete (week-start "
        "derivation, pending-release reconcile sweep, week-close archive+push)."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_week_start = sub.add_parser("week-start", help="Print the Week starting: date from HEADER.md.")
    p_week_start.add_argument(
        "--header", default="state/week-changelog/HEADER.md", help="Path to HEADER.md (cwd-relative)."
    )
    p_week_start.set_defaults(func=_cmd_week_start)

    p_reconcile = sub.add_parser(
        "reconcile-sweep", help="Step 9.1.5 detect-only pending-release reconcile backstop."
    )
    p_reconcile.add_argument(
        "--header", default="state/week-changelog/HEADER.md", help="Path to HEADER.md, for --since auto-derivation."
    )
    p_reconcile.add_argument("--since", default=None, help="Override the week-start date (default: derive from --header).")
    p_reconcile.add_argument("--limit", type=int, default=1000, help="query-completions.py --limit (default 1000).")
    p_reconcile.add_argument("--query-script", default=None, help="Path to query-completions.py (default: co-located sibling).")
    p_reconcile.add_argument(
        "--reconcile-script", default=None, help="Path to reconcile-completion-commits.py (default: co-located sibling)."
    )
    p_reconcile.add_argument(
        "--entries-file",
        default=None,
        help="Test/override hook: newline-delimited entry paths, bypassing the query-completions.py call.",
    )
    p_reconcile.set_defaults(func=_cmd_reconcile_sweep)

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
    p_archive.add_argument("--branch-script", default=None, help="Path to coordinator-current-branch.py (default: co-located sibling).")
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
    if args.command in ("reconcile-sweep",) and not args.query_script:
        args.query_script = _default_query_script()
    if args.command in ("reconcile-sweep",) and not args.reconcile_script:
        args.reconcile_script = _default_reconcile_script()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
