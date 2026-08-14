# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""handoff-archive-transition.py — CLI trampoline over claude-klabauter's
`handoff.archive_transition` op, covering the two dispatch shapes DoE-claude's
`coordinator/skills/handoff/SKILL.md` (predecessor chain-archival on write, and
park-with-links on supersession) previously inlined as embedded
`python3 -c` heredocs calling `cc_invoke.route_mutation` directly.

Purpose: this file is the naked-Python landing spot for that inlined logic —
the DoE skill invokes it by name instead of carrying the heredoc + resolver
boilerplate inline (M3/HO-3, the extirpation plan that ports genuine
imperative bash/heredoc logic out of skill markdown and into claude-klabauter CLIs).

Subcommands:

    chain <predecessor-path> [--exclude <path>]... [--sha <SHA>] [--force]
        Chain-archival on write (SKILL.md "Chain archival — presume the sweep
        wins"). Runs the predecessor live-children guard (co-located
        handoff-has-live-children.py, spawned as a subprocess — SAME
        engine/contract the skill's bash already called, not re-derived here)
        as a CALLER PRECONDITION, then dispatches handoff.archive_transition
        with the mode the guard result selects:
          - guard says childless (exit 1)              -> mode 'stamp_shipped'
          - guard says has-children or indeterminate    -> mode 'stamp_only'
            (exit 0 / exit 2)
        Fails loud (exit 1, one stderr line) when <predecessor-path> is
        already gone from disk — the async boot sweep beating this call to
        the archival is the common case on a sweep-active fleet, but an
        absent file is also what a bad path, a race, or a misplaced file
        produces, and this call cannot tell those apart from disk alone; it
        does not claim success on the sweep's behalf (plan chunk C1, AC1/
        AC2). An op-level refusal from handoff.archive_transition (a
        RouteMutationError) is likewise surfaced to stderr AND now fails this
        subcommand (exit 1) — a refusal is not a confirmed landing, and this
        call must never claim a mutation happened when it didn't. A genuine
        transport/engine failure (a bare RuntimeError, not a RouteMutationError)
        also returns 1 for the same reason: silently swallowing it would be
        indistinguishable from success to the caller (see Exit codes below).
        The one remaining legitimate 0 besides a confirmed archive is
        guard-retention (live children -> mode falls back to stamp_only) —
        that branch's promised outcome IS the stamp-only landing, and stays
        0. The other asymmetry worth noting: a "stamp_shipped" run whose op
        envelope reports no landing is genuinely ambiguous from the envelope
        alone (deliberate deferral vs a failed move attempt) — `cmd_chain`
        now resolves that ambiguity with an on-disk re-read (mirroring
        `cmd_supersede`'s own self-verification) before failing loud — see
        `cmd_chain`'s docstring.

    supersede <handoff-path> --continued-into <successor> [--exclude <path>]...
        Park-with-links on supersession (SKILL.md "Park-with-links on
        supersession"). Dispatches handoff.archive_transition mode='supersede'
        directly — HARD-FAILS (nonzero exit) on any refusal or transport
        error, matching the skill's original `[ "$_rc" = 0 ] || { ... exit 1;
        }` gate.
        Divergence from the skill's literal 2026-07 bash text: that fence
        called mode='supersede' with NO continued_into param, but the native
        op itself already rejects mode='supersede' with no successor as a
        usage error (exit_code 2) — see coordinator_core/archive_stamp.py's
        cs_supersede_archive_handoff docstring, which independently confirms
        this. A literal port would therefore always fail at the engine. This
        CLI instead requires --continued-into as a first-class argument
        (rejected here, before even reaching the op, on absence) so the
        DoE-side call site can be updated to pass the successor it already
        names in the body-prose link pair (SKILL.md § Park-with-links step 2)
        rather than porting a call shape that cannot succeed.

Both subcommands resolve the repo root from the target handoff's own
directory (`git -C <dirname(handoff_path)> rev-parse --show-toplevel`) — same
technique as handoff-has-live-children.py's `_resolve_repo_root` — rather
than from the process cwd. This is a deliberate improvement over the ported
skill's `git -C "$PWD" ...` (falling back to `$PWD` on failure): resolving
from the handoff's own directory has no cwd dependence at all, matching this
file's Path(__file__)-relative self-resolution contract for its OWN location.

Exit codes:
    chain:     0 on a confirmed archive (via the envelope's `moved` flag, or
               an on-disk re-read confirming `deployment_state: shipped`
               with `shipped_in` populated when the envelope's own flag is
               falsy — see `cmd_chain`'s docstring), or on a guard-retained
               stamp-only landing (the promised outcome on that branch, see
               above); 1 on a missing predecessor file, a guard subprocess
               spawn failure (OSError) that leaves the mode undecidable, an
               op-level refusal (RouteMutationError), a genuine transport/
               engine failure (a bare RuntimeError), or a falsy envelope
               landing signal whose on-disk re-read also fails to confirm
               the transition landed — none of these is a confirmed
               landing, so none of them stays 0.
    supersede: 0 on success; 1 on an op-level refusal, transport failure,
               unresolvable repo root, or a post-write re-read that does NOT
               show `deployment_state: continued` with the supplied
               `continued_into` landed on disk (§ AC3/AC4,
               `docs/plans/2026-07-28-handoff-close-path-fail-loud.md`
               chunk C13 — see `cmd_supersede`'s docstring); 2 on a usage
               error (missing --continued-into or missing handoff-path).

Negative-spec:
    - Does NOT open any UDS socket or read an auth token — routes through
      cc_invoke.route()/route_mutation(), which are command-type transports
      (fresh coordinator_core.invoke subprocess per call), same as every
      other bin/ CLI in this house style.
    - Does NOT write the `<!-- consumed: YYYY-MM-DD -->` marker — that stays
      `/pickup`'s exclusive responsibility, unaffected by this port.
    - Does NOT stamp `handoff_phase` — that is a separate concern
      (handoff.stamp_phase), out of scope for this port (see the M3/HO-3
      dispatch brief's "What to port vs leave").

Spec backlink: DoE-claude coordinator/skills/handoff/SKILL.md
    §§ "Chain archival — presume the sweep wins" (event-driven cutover /
    option a) and "Park-with-links on supersession" (relocation step).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

_BIN_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_BIN_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
import cc_invoke  # noqa: E402

PROG = "handoff-archive-transition.py"


def _no_console_kw() -> dict:
    """Lazily resolve the engine root onto sys.path (self-location-first via
    cc_invoke.ensure_engine_on_path — see that function's docstring), then
    splat the canonical no-console-window kwarg. ``{}`` on any resolution/
    import failure (fail-open)."""
    try:
        if cc_invoke.ensure_engine_on_path(__file__) is None:
            return {}
        from coordinator_core.win_portability import no_console_creationflags

        return no_console_creationflags()
    except Exception:
        return {}


_HAS_LIVE_CHILDREN_SCRIPT = os.path.join(_BIN_DIR, "handoff-has-live-children.py")


def _no_fallback():
    raise RuntimeError(
        f"{PROG}: handoff.archive_transition requires the native seam (no bash "
        "fallback -- big-bang cutover); re-run coordinator:install or verify "
        "CLAUDE_KLABAUTER_ROOT"
    )


def _resolve_repo_root(handoff_path: str) -> str | None:
    """Resolve repo root from the handoff's own directory, not the process cwd.

    Mirrors handoff-has-live-children.py's `_resolve_repo_root` technique —
    candidate-dir discovery always resolves the correct per-repo git root
    regardless of where this CLI happens to be invoked from.
    """
    handoff_abs = os.path.abspath(handoff_path)
    try:
        proc = subprocess.run(
            ["git", "-C", os.path.dirname(handoff_abs), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            **_no_console_kw(),
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    root = proc.stdout.strip()
    return root or None


def _guard_exit_code(handoff_path: str, exclude: list[str]) -> int:
    """Spawn the co-located handoff-has-live-children.py guard as a caller
    precondition. Returns its exit code verbatim: 0 has-children, 1 childless
    (safe to archive), 2 indeterminate/error (fail-closed, treat as has-children).

    A guard subprocess-spawn failure (OSError — script missing, no
    interpreter) is NOT the same as the guard's own fail-closed exit 2: it
    means the mode decision itself is undecidable, so it is surfaced distinctly
    by the caller rather than silently coerced to 2.
    """
    cmd = [sys.executable, _HAS_LIVE_CHILDREN_SCRIPT]
    for path in exclude:
        cmd += ["--exclude", path]
    cmd.append(handoff_path)
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        **_no_console_kw(),
    )
    return proc.returncode


def _locate_after_archive_move(handoff_path: str, repo_root: str | None) -> str:
    """Where to re-read frontmatter from after a transition that may have
    git-mv'd the handoff into archive/: `handoff_path` itself when the move
    did not happen (guard-retained, the move genuinely failed, or no move
    was attempted for this mode/branch), or the derived
    archive/handoffs/YYYY-MM/ destination when it did. Falls back to
    `handoff_path` verbatim when `repo_root` is falsy — the re-read then
    fails closed via `_reread_frontmatter_fields`'s own OSError handling,
    not via a path this function guesses at.

    Shared by `cmd_supersede` (originally the sole caller, as
    `_locate_after_supersede`) and `cmd_chain`'s stamp_shipped self-
    verification — the location logic has no mode-specific content, only
    "did the source path stop existing".

    Mirrors `coordinator_core.archive_stamp._locate_after_supersede` (same
    shape, independently implemented here rather than imported — this CLI's
    `repo_root` is already the `git rev-parse --show-toplevel` worktree root,
    the same value that sibling's own `worktree` param takes)."""
    if os.path.exists(handoff_path) or not repo_root:
        return handoff_path
    from coordinator_core.ops.fleet._common import handoff_archive_dest

    dest = handoff_archive_dest(Path(repo_root), Path(handoff_path))
    return str(dest) if dest.exists() else handoff_path


def _reread_frontmatter_fields(current_path: str, fields: list[str]) -> dict[str, str | None]:
    """Re-reads the named frontmatter fields straight off disk at
    `current_path` — the independent-of-the-envelope read both
    `cmd_supersede` (§ AC3, `docs/plans/2026-07-28-handoff-close-path-fail-
    loud.md` chunk C13) and `cmd_chain` (defect 1, `cross-repo/inbox/2026-
    08-04-example-market-data-repo-em-baton-lifecycle-three-defects.md`) use to
    confirm a transition actually landed, rather than trusting an envelope
    key that either was never populated for the mode in question or was
    never authoritative on its own. Returns every requested field as None
    when the file is unreadable or carries no frontmatter; that shape reads
    as a verification failure to every caller, never a silent pass.

    Originally `_reread_supersede_frontmatter` (single hardcoded field
    pair); generalized to an arbitrary field list so `cmd_chain`'s
    stamp_shipped re-read (`deployment_state` + `shipped_in`) can share the
    split/read plumbing instead of duplicating it. Mirrors
    `coordinator_core.archive_stamp._reread_supersede_frontmatter`."""
    from coordinator_core.frontmatter.primitives import read_fm_field_unquoted, split_frontmatter

    try:
        text = Path(current_path).read_text(encoding="utf-8")
    except OSError:
        return {field: None for field in fields}
    split = split_frontmatter(text)
    if split is None:
        return {field: None for field in fields}
    return {field: read_fm_field_unquoted(split.fm_text, field) for field in fields}


def cmd_chain(
    handoff_path: str,
    exclude: list[str],
    sha: str | None = None,
    force: bool = False,
) -> int:
    """Chain-archival dispatch. Every return is a promise about the mutation:
    0 means the call's promised outcome (archive, or a guard-retained
    stamp-only) is CONFIRMED landed; non-zero means it did not, whatever the
    stderr tone. The discriminator is "did the mutation this call promised
    actually land", never "did we archive" — guard-retention (live children
    -> mode falls back to stamp_only) is itself the promised outcome on that
    branch and stays 0 (plan docs/plans/2026-07-28-handoff-close-path-fail-
    loud.md chunk C1, AC1/AC2; see § S5 for the pre-fix smoking gun this
    replaces).

    `sha`/`force` (plan chunk C3, AC5): CLI-surface passthrough onto the
    `sha`/`force` params `handoff.archive_transition` has already accepted
    since 2026-07-22 (coordinator_core/ops/handoff_archive_transition.py) —
    this widens the existing param, it does not add a new resolution path.
    Position A (PM-ratified 2026-07-15) forbids the op guessing a sha; `sha`
    is a caller-supplied escape for a caller that has already independently
    derived the correct one. Omitting `--sha` leaves `params` exactly as it
    was before this chunk — byte-identical resolution to today.

    Negative-spec (C3): does NOT derive a sha from anywhere (branch tip,
    archive/completed/** ship-SHA, or otherwise) when `--sha` is absent —
    that is the D2 option (b) fallback § S10 rules out as a new resolution
    path colliding with Position A. Does NOT let `--force` stand alone;
    `handoff.archive_transition` (mirroring `stamp_shipped_in`) rejects
    `force` without `sha`, and this CLI takes that same refusal rather than
    pre-validating it, so the pairing rule lives in exactly one place.

    Self-verification (fix for defect 1, `cross-repo/inbox/2026-08-04-
    example-market-data-repo-em-baton-lifecycle-three-defects.md`): the
    `mode=stamp_shipped` branch does not trust the envelope's landing
    signal (`moved`) as its only word — when that signal is falsy, this
    function re-reads the target's frontmatter from disk before failing
    loud, mirroring `cmd_supersede`'s own re-read pattern. This closes an
    ambiguity that was observed firing on the SUCCESS path in production,
    not just as a theoretical gap: two batons landed
    `deployment_state: shipped` with a populated `shipped_in`, committed by
    the op itself, while this function reported failure because it checked
    an envelope key (`archived`) that `handoff.archive_transition` has
    never populated for any mode.
    """
    if not os.path.isfile(handoff_path):
        # Negative-spec (C1): a missing predecessor file is NOT treated as a
        # verified prior archival. The async sweep beating this call there is
        # the common case, but "absent" is also what a bad path, a race, or a
        # misplaced file produces — this call cannot tell those apart from
        # disk alone, so it cannot claim success on the sweep's behalf. Fail
        # loud; the caller (or a human) confirms which case it was.
        print(
            f"chain-archival: predecessor {handoff_path!r} not found on disk — "
            "cannot confirm archival landed (may be a prior sweep, may be a bad "
            "path or a race); treating as unperformed, not skipping",
            file=sys.stderr,
        )
        return 1

    try:
        guard_rc = _guard_exit_code(handoff_path, exclude)
    except OSError as exc:
        print(
            f"chain-archival: live-children guard could not be spawned for "
            f"{handoff_path!r} ({exc}) — mode undecidable",
            file=sys.stderr,
        )
        return 1

    repo_root = _resolve_repo_root(handoff_path)
    if not repo_root:
        print(
            f"chain-archival: cannot resolve git repo root from {handoff_path!r}'s "
            "directory — no mutation attempted",
            file=sys.stderr,
        )
        return 1

    if guard_rc == 1:
        mode = "stamp_shipped"
    else:
        mode = "stamp_only"
        print(
            f"chain-archival: {handoff_path!r} has live children (guard rc="
            f"{guard_rc}) — stamping shipped in place, not archiving",
            file=sys.stderr,
        )

    params: dict = {"handoff_path": handoff_path, "mode": mode}
    if exclude:
        params["exclude"] = list(exclude)
    if sha and sha.strip():
        params["sha"] = sha
    if force:
        params["force"] = True

    try:
        result = cc_invoke.route_mutation(
            "handoff.archive_transition", params, repo_root, _no_fallback
        )
    except cc_invoke.RouteMutationError as exc:
        print(
            f"chain-archival: handoff.archive_transition (mode={mode}) refused "
            f"for {handoff_path!r} — {exc}",
            file=sys.stderr,
        )
        return 1
    except RuntimeError as exc:
        print(
            f"chain-archival: handoff.archive_transition (mode={mode}) failed "
            f"for {handoff_path!r} — transport/engine failure: {exc}",
            file=sys.stderr,
        )
        return 1

    if mode == "stamp_only":
        # Guard-retention: the promised outcome on this branch IS the
        # stamp-only landing, already confirmed by op's non-raising return.
        # This is the one legitimate zero this function has (see docstring).
        return 0

    # mode == "stamp_shipped" from here. `moved` is the envelope's own
    # landing signal for this mode (handoff.archive_transition's return dict
    # has never carried an `archived` key — see the fix note below).
    moved = isinstance(result, dict) and bool(result.get("moved"))
    if moved:
        print(
            f"chain-archival: predecessor {handoff_path!r} archived",
            file=sys.stderr,
        )
        return 0

    # Self-verification (mirrors `cmd_supersede`'s own re-read, see that
    # function's docstring): a falsy `moved` is not, by itself, proof the
    # transition failed. This branch was observed firing on the SUCCESS
    # path in production (defect 1, `cross-repo/inbox/2026-08-04-market-
    # intelligence-em-baton-lifecycle-three-defects.md`) — two batons landed
    # `deployment_state: shipped` with a populated `shipped_in`, committed
    # by the op itself, while this CLI printed the fail-loud message below
    # because it was checking `result.get("archived")`, a key
    # handoff.archive_transition's envelope has never populated for any
    # mode. Rather than trust `moved` alone either, re-read the target's
    # frontmatter from disk (the file may have moved into
    # archive/handoffs/YYYY-MM/ as part of the transition — resolved the
    # same way `cmd_supersede` resolves it, via `_locate_after_archive_move`
    # / `coordinator_core.archive_stamp._locate_after_supersede`'s
    # precedent) and only fail loud when the re-read also shows no landing.
    current = _locate_after_archive_move(handoff_path, repo_root)
    landed_fields = _reread_frontmatter_fields(current, ["deployment_state", "shipped_in"])
    landed = landed_fields["deployment_state"] == "shipped" and bool(landed_fields["shipped_in"])
    if landed:
        print(
            f"chain-archival: predecessor {handoff_path!r} confirmed landed "
            "via on-disk re-read (deployment_state=shipped, shipped_in="
            f"{landed_fields['shipped_in']!r}) despite the envelope reporting "
            "no move",
            file=sys.stderr,
        )
        return 0

    # Negative-spec (C1): a re-read that also shows no landing is genuinely
    # ambiguous — the op's own envelope does not currently distinguish a
    # deliberate deferral it decided on internally from a move it attempted
    # and failed (§ S5's fourth site). Per the brief's conservative-split
    # instruction, an ambiguous outcome fails loud rather than defaulting to
    # success.
    reason = result.get("message") if isinstance(result, dict) else None
    reason_text = reason or "no reason reported"
    print(
        f"chain-archival: handoff.archive_transition (mode=stamp_shipped) "
        f"reported no archive for {handoff_path!r} ({reason_text}) — re-read "
        f"confirms no landing either (deployment_state="
        f"{landed_fields['deployment_state']!r}, shipped_in="
        f"{landed_fields['shipped_in']!r}) — cannot distinguish a deliberate "
        "deferral from a failed attempt, failing loud",
        file=sys.stderr,
    )
    return 1


def cmd_supersede(handoff_path: str, continued_into: str | None, exclude: list[str]) -> int:
    """Park-with-links dispatch. AC3 (`docs/plans/2026-07-28-handoff-close-
    path-fail-loud.md`, improvement-queue entry
    `state/improvement-queue/2026-07-25-archive-stamp-cli-supersede-archive-
    hand-6b71b547b70a.yaml`, fix (1)): this function does NOT trust
    `result["superseded"]` alone as proof the write landed — a mutation op
    that cannot confirm its own write must never exit 0. After the op call
    reports `superseded: True`, this re-reads the predecessor's frontmatter
    FROM DISK (`_locate_after_supersede` / `_reread_supersede_frontmatter`,
    mirroring `coordinator_core.archive_stamp.cs_supersede_archive_handoff`)
    and asserts `deployment_state: continued` with `continued_into` equal to
    the successor string just passed in — actually landed — before
    returning 0. Either mismatch fails loud (rc 1), naming the handoff and
    what was found instead.

    Negative-spec — retention is NOT failure: a guard-retained supersede
    (live children found, or indeterminate/fail-closed) legitimately
    returns 0. The status flip is NOT gated on the archival-move guard (see
    `coordinator_core.ops.handoff_archive_transition`'s own docstring — the
    2026-07-27 fix `2b4aafb7` made the flip unconditional), so this
    re-read assertion runs REGARDLESS of `retained`: a retained call must
    still show the flip on disk, and this function does not special-case
    retention into a skipped check. Swapping this for "only verify when not
    retained" would silently reintroduce the exact half-state (predecessor
    left at `deployment_state: in_flight` / `pickup_ready: true` while a
    successor also claims to be live work) the reported incident was about."""
    if not (continued_into and continued_into.strip()):
        print(
            "supersede: mode 'supersede' requires a non-empty --continued-into "
            "(successor handoff id-or-path) — see this file's module docstring "
            "for why this diverges from the skill's original param-less call",
            file=sys.stderr,
        )
        return 2

    repo_root = _resolve_repo_root(handoff_path)
    if not repo_root:
        print(
            f"supersede: cannot resolve git repo root from {handoff_path!r}'s "
            "directory",
            file=sys.stderr,
        )
        return 1

    cc_invoke.require_engine_on_path(__file__)
    from coordinator_core.archival import claimed_or_shipped_at_path

    if not claimed_or_shipped_at_path(handoff_path):
        print(
            f"supersede: refusing — {handoff_path} was never claimed or shipped "
            "(DR-242: a successor-named child is not evidence of succession; "
            "nothing to supersede)",
            file=sys.stderr,
        )
        return 1

    params: dict = {
        "handoff_path": handoff_path,
        "mode": "supersede",
        "continued_into": continued_into,
    }
    if exclude:
        params["exclude"] = list(exclude)

    try:
        result = cc_invoke.route_mutation(
            "handoff.archive_transition", params, repo_root, _no_fallback
        )
    except cc_invoke.RouteMutationError as exc:
        print(
            f"ERROR: handoff.archive_transition (mode=supersede) failed: {exc}",
            file=sys.stderr,
        )
        return 1
    except RuntimeError as exc:
        print(f"ERROR: handoff.archive_transition (mode=supersede) failed: {exc}", file=sys.stderr)
        return 1

    # Never silently succeed with no trace: route_mutation only raises on a
    # non-zero op-level exit_code, and this op deliberately returns
    # exit_code:0 even when the live-children guard retains the archival
    # move (retention is never an error — see handoff_archive_transition.py's
    # module docstring). That means an unraised, unexamined result here IS
    # the silent-no-op bug (cross-repo DoE incident, 2026-07-27): the caller
    # sees exit 0 and nothing else, indistinguishable from a real supersede.
    # Inspect the result explicitly and always print an outcome line.
    if not isinstance(result, dict):
        print(
            f"ERROR: handoff.archive_transition (mode=supersede) returned an "
            f"unexpected non-dict result: {result!r}",
            file=sys.stderr,
        )
        return 1

    superseded = bool(result.get("superseded"))
    if not superseded:
        # Defensive: as of the 2026-07-27 fix the status flip is unconditional
        # and any failure to apply it already raises RouteMutationError above
        # (op-level exit_code!=0) — reaching exit_code:0 with superseded:False
        # should not happen, but this is exactly the shape the bug we're
        # fixing had, so refuse to report success if it ever does.
        print(
            "supersede: declined — status flip did not apply "
            f"(superseded={superseded!r}): "
            f"{result.get('message') or result.get('error') or 'no reason given'}",
            file=sys.stderr,
        )
        return 1

    # AC3 — do NOT trust `superseded` alone (see this function's docstring):
    # re-read the predecessor's frontmatter FROM DISK and assert the flip
    # actually landed before reporting success. Runs regardless of
    # `retained` — retention is not failure, but it is also not a reason to
    # skip this check (see the Negative-spec paragraph above).
    current = _locate_after_archive_move(handoff_path, repo_root)
    landed_fields = _reread_frontmatter_fields(current, ["deployment_state", "continued_into"])
    landed_state = landed_fields["deployment_state"]
    landed_continued_into = landed_fields["continued_into"]
    if landed_state != "continued" or landed_continued_into != continued_into:
        print(
            f"supersede: {handoff_path}: expected deployment_state='continued' "
            f"with continued_into={continued_into!r} after supersede, re-read "
            f"{current} and found deployment_state={landed_state!r} "
            f"continued_into={landed_continued_into!r} — the status flip did "
            "not land",
            file=sys.stderr,
        )
        return 1

    message = result.get("message") or (
        f"superseded {handoff_path} (continued_into={continued_into})"
    )
    print(f"supersede: {message}", file=sys.stderr)
    if result.get("retained"):
        print(
            f"supersede: archival deferred — {result.get('retain_reason')}",
            file=sys.stderr,
        )
    for warning in result.get("warnings") or []:
        print(f"supersede: warning: {warning}", file=sys.stderr)

    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=PROG)
    sub = p.add_subparsers(dest="subcommand", required=True)

    chain = sub.add_parser(
        "chain",
        help="predecessor live-children guard + archive-transition dispatch on handoff write",
    )
    chain.add_argument("handoff_path")
    chain.add_argument("--exclude", action="append", default=[], dest="exclude")
    chain.add_argument(
        "--sha",
        dest="sha",
        default=None,
        help=(
            "caller-supplied SHA override, threaded verbatim to "
            "handoff.archive_transition's own 'sha' param (provenance-repair "
            "escape — mirrors archive-stamp-cli ship-handoff's --sha; omit to "
            "preserve today's resolution unchanged)"
        ),
    )
    chain.add_argument(
        "--force",
        dest="force",
        action="store_true",
        default=False,
        help=(
            "provenance-repair escape, threaded verbatim to "
            "handoff.archive_transition's own 'force' param — REQUIRES --sha "
            "(mirrors archive-stamp-cli ship-handoff's --force)"
        ),
    )

    supersede = sub.add_parser(
        "supersede",
        help="park a superseded handoff via handoff.archive_transition mode=supersede",
    )
    supersede.add_argument("handoff_path")
    supersede.add_argument("--continued-into", dest="continued_into", default=None)
    supersede.add_argument("--exclude", action="append", default=[], dest="exclude")

    return p


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        args = _build_parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2

    if args.subcommand == "chain":
        return cmd_chain(args.handoff_path, args.exclude, args.sha, args.force)
    if args.subcommand == "supersede":
        return cmd_supersede(args.handoff_path, args.continued_into, args.exclude)

    print(f"{PROG}: unknown subcommand {args.subcommand!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
