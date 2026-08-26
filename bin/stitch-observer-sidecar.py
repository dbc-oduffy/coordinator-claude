# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""stitch-observer-sidecar.py — /workday-complete Step 4d: fold the strategic
observer's sidecar (Step 4c output) into the day's canonical daily summary.

Step 4c writes `## Strategic Review (Sonnet daily observer)` to a transient
sidecar file (`archive/daily-summaries/YYYY-MM-DD-<machine>.observer.md`) run
in parallel with Step 4b's main-summary analyst. Step 4d's job is to append
that sidecar onto the main summary and delete the sidecar, so the sidecar
never survives past one ceremony run.

Replaces the inline `cat "$OBSERVER_SIDECAR" >> "$DAILY_SUMMARY"; rm
"$OBSERVER_SIDECAR"` in DoE's workday-complete.md Step 4d, which had no
existence check, no idempotency, and no failure surface: a missing daily
summary made `cat` fail while `rm` ran anyway, silently discarding the
sidecar's content with no error visible to the operator. Confirmed on disk
2026-07-23: three backfilled days (2026-07-19..21) each left an orphaned
`*.observer.md` sidecar with zero `## Strategic Review` heading in the
corresponding main summary — the exact leak this script closes.

Behavior (in order):
  1. Sidecar absent — normal for backfill/skip days (Step 4c is deliberately
     not run on backfilled days per the daily-summary-procedure.md § Skip
     Condition). No-op, exit 0.
  2. Sidecar present but the daily summary is missing — the leak condition.
     Refuses to delete the sidecar. Fails LOUD (visible stderr line), exit 1.
  3. The discriminator between "already stitched" and "not yet stitched" is
     whether a `## Strategic Review` heading survives placeholder-stripping
     (see `_strip_placeholder`): strip any placeholder first, then count
     headings in the result.
       - If a heading survives: a real section exists independent of the
         placeholder — already stitched (re-run, or a hand-stitch already
         happened). Idempotent: does NOT append a second copy, removes the
         now-redundant sidecar, reports it, exit 0. Deletion here is gated on
         the sidecar's own body being verifiably present in the summary, not
         on the heading alone (see below). A co-resident placeholder in this
         case is residue from an incomplete cleanup and is stripped/rewritten
         to disk as part of this same idempotent path.
       - If no heading survives: any heading present belonged to the
         placeholder itself (per `_strip_placeholder`'s own adjacency rule) —
         not yet stitched. Falls through to the normal append path (4) below,
         appending onto the placeholder-stripped content. This is what keeps
         the case where the analyst brief writes `## Strategic Review`
         directly above the placeholder, with the sidecar's content not yet
         in the file, on the automatic append path instead of erroring.
  3b. Negative-spec: a heading alone (before placeholder-stripping) is NOT a
     sufficient already-stitched signal — see the discriminator above, and
     the sidecar's body marker must also be present in the summary before the
     idempotent path deletes anything. An analyst-brief heading with the
     sidecar's own content absent is a marker false-positive, not a completed
     stitch: the pre-2026-08-07 shape took that branch, deleted the sidecar,
     and exited 0 — destroying the observer's entire output while every exit
     code reported success. Deletion must never be reachable from a state
     where the sidecar's content is absent from the summary.
  4. Otherwise — the normal path. Appends the sidecar's content verbatim
     (never re-authored/summarized) onto the end of the daily summary, then
     re-reads the daily summary to confirm exactly one `## Strategic Review`
     heading is now present before deleting the sidecar. Deletion is gated on
     that verification, not merely on the write call returning without
     raising. Failed verification rolls the daily summary back to its exact
     pre-write bytes before returning 1 — the one code path that exists to
     detect corruption must not also be the path that leaves it in place.

  Negative-spec (placeholder ambiguity, narrowed by 3 above): before this
  fix, a co-resident heading+placeholder fell through the idempotent branch
  straight to a duplicate append whenever a real section already existed,
  corrupting the file. The discriminator above closes that specific case: a
  placeholder co-resident with a heading that survives stripping is always
  residue, never a "not yet stitched" signal. The placeholder still means
  "not yet stitched" on its own (no surviving heading) or when it sits
  directly above the only heading present (that heading is the placeholder's
  own, per `_strip_placeholder`) — those two states are still distinguished
  correctly, they just no longer collide with the residue case above.

Usage:
    stitch-observer-sidecar.py <daily_summary_path> <observer_sidecar_path>
    stitch-observer-sidecar.py --scan <archive/daily-summaries-dir>

The two-arg form is the ceremony call site (one date/machine pair per Step 4d
invocation, no backfill-vs-live distinction — a sidecar's mere presence is
"needs stitching", regardless of why Step 4c ran).

The `--scan` form is a standalone sweep, independent of any single ceremony
run: it globs `*.observer.md` under the given directory and reports every one
found. A sidecar surviving to scan time is BY DEFINITION unstitched (the
normal path deletes it on success) — so any hit is reported and the scan
exits non-zero, whether the day was live or backfilled, and whether Step 4c
ran through the ceremony or was produced by some other path. This is what
makes a leak like the 2026-07-19..21 incident (three sidecars sitting
committed for days, invisible unless someone thought to `ls` for them)
detectable on its own, without depending on Step 4d having been invoked for
that date at all.

Exit codes (two-arg / stitch form):
  0 — no-op (sidecar absent), idempotent no-op (already stitched), or stitched.
  1 — LEAK: sidecar exists but daily summary is missing/unwritable, or the
      post-append verification failed (heading count != 1). Sidecar is left
      in place in both cases so the leak is investigable, not compounded. On
      a failed post-append verification the daily summary is additionally
      restored to its pre-write bytes before returning, so the target file is
      never left corrupted on disk.
  2 — usage error.

Exit codes (--scan form):
  0 — no orphaned sidecars found.
  1 — one or more orphaned sidecars found (reported to stderr, one line each).
  2 — usage error (e.g. directory does not exist).

Spec backlink: coordinator/commands/workday-complete.md § Step 4d (DoE-claude)
"""
from __future__ import annotations

import glob
import os
import sys

GENERATES = []  # writes only to `<daily_summary_path>`, an arbitrary CLI positional argument (archive/daily-summaries/... in whichever repo invokes it) — caller-supplied, not a fixed claude-klabauter artifact

_HEADING = "## Strategic Review"
_SIDECAR_SUFFIX = ".observer.md"

#: The analyst's stand-in for the section this script appends, per DoE-claude
#: coordinator/docs/wiki/daily-summary-procedure.md's summary template. Its
#: presence proves the stitch has NOT run, regardless of what headings the
#: summary carries.
_PLACEHOLDER = "_Strategic Review section will be appended by the reviewer agent._"


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def _heading_count(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.startswith(_HEADING))


def _sidecar_body_marker(sidecar_content: str) -> str:
    """First substantive (non-blank, non-heading) line of the sidecar.

    Proves the sidecar's content is genuinely present in the summary before
    the already-stitched branch deletes it. A heading match alone is not
    proof: a placeholder, a hand-written stub, or an unrelated section can
    carry the same heading while the observer's output is nowhere in the file.
    Returns "" for a heading-only sidecar, which disables the check rather
    than failing a legitimately empty section.
    """
    for line in sidecar_content.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return ""


def _strip_placeholder(main_content: str) -> str:
    """Remove the placeholder line, plus a `## Strategic Review` heading
    directly above it when the analyst brief emitted one.

    Negative-spec: that heading is dropped ONLY when it belongs to the
    placeholder — adjacent, separated at most by blank lines. The sidecar
    carries its own heading, so leaving the placeholder's behind would yield
    two and trip the post-append verification.
    """
    lines = main_content.splitlines()
    try:
        idx = next(i for i, line in enumerate(lines) if _PLACEHOLDER in line)
    except StopIteration:
        return main_content

    start = idx
    probe = idx - 1
    while probe >= 0 and not lines[probe].strip():
        probe -= 1
    if probe >= 0 and lines[probe].startswith(_HEADING):
        start = probe

    return "\n".join(lines[:start] + lines[idx + 1:]).rstrip("\n") + "\n"


def stitch(daily_summary_path: str, observer_sidecar_path: str) -> int:
    try:
        with open(observer_sidecar_path, "r", encoding="utf-8") as f:
            sidecar_content = f.read()
    except FileNotFoundError:
        _err(f"[stitch-observer-sidecar] sidecar absent ({observer_sidecar_path}) — "
             "normal for backfilled/skip days. No-op.")
        return 0

    try:
        with open(daily_summary_path, "r", encoding="utf-8") as f:
            main_content = f.read()
    except FileNotFoundError:
        _err(f"[stitch-observer-sidecar] LEAK: sidecar '{observer_sidecar_path}' exists but "
             f"daily summary '{daily_summary_path}' is missing — refusing to delete the "
             "sidecar. Step 4b (main-summary analyst) must have failed or not run. "
             "Investigate before re-running Step 4d.")
        return 1

    placeholder_present = _PLACEHOLDER in main_content
    cleaned = _strip_placeholder(main_content) if placeholder_present else main_content

    if _heading_count(cleaned) >= 1:
        # A heading survives placeholder-stripping — a real section exists
        # independent of the placeholder — idempotent path.
        marker = _sidecar_body_marker(sidecar_content)
        if marker and marker not in main_content:
            _err(f"[stitch-observer-sidecar] LEAK: '{daily_summary_path}' carries a "
                 f"'{_HEADING}' heading but NOT the sidecar's content — refusing to "
                 f"delete '{observer_sidecar_path}' on a marker false-positive. "
                 "Reconcile the two by hand before re-running.")
            return 1
        residue_note = ""
        if cleaned != main_content:
            with open(daily_summary_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(cleaned)
            residue_note = " Stripped residual placeholder text left in the file."
        os.remove(observer_sidecar_path)
        _err(f"[stitch-observer-sidecar] '{daily_summary_path}' already contains "
             f"'{_HEADING}' and the sidecar's content — idempotent no-op. Removed "
             f"redundant sidecar '{observer_sidecar_path}'.{residue_note}")
        return 0

    # No heading survives placeholder-stripping — any heading present
    # belonged to the placeholder itself. Normal append path onto `cleaned`.
    original_content = main_content
    main_content = cleaned

    separator = "" if main_content.endswith("\n\n") else ("\n" if main_content.endswith("\n") else "\n\n")
    with open(daily_summary_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(main_content)
        f.write(separator)
        f.write(sidecar_content)

    with open(daily_summary_path, "r", encoding="utf-8") as f:
        verify_content = f.read()
    count = _heading_count(verify_content)
    if count != 1:
        with open(daily_summary_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(original_content)
        _err(f"[stitch-observer-sidecar] LEAK: post-append verification failed — "
             f"'{daily_summary_path}' had {count} '{_HEADING}' headings after the write "
             "(expected 1). Restored the file to its pre-write content; the sidecar "
             f"'{observer_sidecar_path}' is retained. Investigate before re-running.")
        return 1

    os.remove(observer_sidecar_path)
    _err(f"[stitch-observer-sidecar] stitched '{observer_sidecar_path}' onto "
         f"'{daily_summary_path}' and removed the sidecar.")
    return 0


def scan(directory: str) -> int:
    """Sweep `directory` for `*.observer.md` sidecars and report every one found.

    A sidecar's existence at scan time is itself the anomaly (see module
    docstring) — no backfill/live distinction is needed here. For each hit,
    names whether it's a never-stitched orphan, an already-stitched-but-
    uncleaned duplicate, or missing its main summary entirely, so the
    operator knows which of stitch()'s branches to expect on re-run.
    """
    if not os.path.isdir(directory):
        _err(f"[stitch-observer-sidecar --scan] '{directory}' is not a directory.")
        return 2

    sidecars = sorted(glob.glob(os.path.join(directory, f"*{_SIDECAR_SUFFIX}")))
    if not sidecars:
        _err(f"[stitch-observer-sidecar --scan] no orphaned sidecars found under '{directory}'.")
        return 0

    for sidecar in sidecars:
        main_path = sidecar[: -len(_SIDECAR_SUFFIX)] + ".md"
        if not os.path.isfile(main_path):
            _err(f"ORPHAN (main summary missing): '{sidecar}' — no corresponding '{main_path}'.")
            continue
        with open(main_path, "r", encoding="utf-8") as f:
            main_content = f.read()
        if _heading_count(main_content) >= 1:
            _err(f"ORPHAN (already stitched, sidecar not cleaned up): '{sidecar}' — "
                 f"'{main_path}' already has '{_HEADING}'; re-run stitch to remove the "
                 "redundant sidecar.")
        else:
            _err(f"ORPHAN (never stitched): '{sidecar}' — '{main_path}' exists but has no "
                 f"'{_HEADING}' heading; its content is stranded.")
    return 1


def main(argv: list[str]) -> int:
    if len(argv) == 3 and argv[1] == "--scan":
        return scan(argv[2])
    if len(argv) == 3:
        return stitch(argv[1], argv[2])
    _err(f"usage: {argv[0]} <daily_summary_path> <observer_sidecar_path>\n"
         f"       {argv[0]} --scan <archive/daily-summaries-dir>")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
