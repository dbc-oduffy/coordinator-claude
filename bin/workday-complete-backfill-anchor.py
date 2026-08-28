# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""workday-complete-backfill-anchor.py — Phase A0 descendant-tip resolution +
mechanical anchor-injection orchestration for `/workday-complete` Step 3.5.

Native port of the Phase A0 bash block that used to live inline in
`commands/workday-complete.md` (coordinator doctrine repo): a nested while-loop pairwise
`git merge-base --is-ancestor` walk that finds the single per-day "descendant
tip" (the commit that is a descendant of, or equal to, every other candidate
tip for that day), followed by a per-date call into
`workday-complete-backfill-inject-anchor.py`, exit-code routing, and a single
batched `git add -- <injected files> && git commit` for every date the anchor
was mechanically resolved for. Chunk WDC-3, M3 extirpation wave — see
`docs/plans/2026-07-16-bash-clean-slate-residual-migration.md`.

Subcommands:

  descendant-tip <ROOT> <SHA> [<SHA> ...]
      Resolve each SHA to its full 40-char form (git rev-parse --verify
      "<sha>^{commit}}"), dedupe, then walk pairwise via `git merge-base
      --is-ancestor` to find the one candidate that is a descendant of (or
      equal to) every other candidate. Prints the resolved full SHA to
      stdout and exits 0. With a single (deduped) candidate, that candidate
      IS the descendant tip directly — no ancestor walk needed. Exits 1 with
      a stderr message when no SHA resolves, or when no single candidate is
      a descendant of all others (diverged branches on the same day — a
      true content gap, not an A0-mechanical case).

  run <ROOT> [--today YYYY-MM-DD] [--no-commit]
      Reads Phase A0 gap-row TSV on stdin — the same
      `<date>\\t<commit_count>\\t<base>\\t<tip>` rows
      `workday-complete-backfill-scan.py` emits (see that script's module
      docstring; the 2026-07-19 de-machine ruling collapsed the format to
      one row per DAY, no machine column — see § Divergence below). Groups
      rows by date, resolves the descendant tip per date via the
      `descendant-tip` logic above, calls
      `workday-complete-backfill-inject-anchor.py`'s own `main()` in-process
      per date, and routes by its documented 0/10/20/30/other exit-code
      contract:
        0/10  -> mechanically resolved (0 also may carry an injected file
                 path on stdout as `TARGET=<path>`); accumulate into
                 INJECTED_DATES (and INJECTED_FILES for rc==0).
        20    -> true content gap (no summary file); accumulate into
                 TRUE_GAP_DATES for the caller's Phase A analyst fan-out.
        30    -> content-completeness guard fired; accumulate into
                 CONTENT_GAP_DATES for the caller's Phase A content-assembly
                 analyst.
        other -> WARN to stderr, then treated as TRUE_GAP_DATES (never a
                 silent drop).
      After the per-date loop, batches every rc==0 injected file into one
      `git add -- <files> && git commit -m "chore(daily-summaries): backfill
      anchor migration"` (skipped entirely with --no-commit, or when no
      files were injected). Prints a machine-parseable summary block to
      stdout:
        INJECTED_DATES=<space-separated dates>
        CONTENT_GAP_DATES=<space-separated dates>
        TRUE_GAP_DATES=<space-separated dates>
        INJECTED_FILES=<space-separated paths>
        COMMITTED=<0|1>

Divergence from the ported bash prose (executor note, WDC-3): the bash
source describes deriving a per-date `machine` value from a gap row's `$2`
column via `awk` (assuming one row per machine per date) and forwarding it
to inject-anchor.py's MACHINE argument. The scan's actual current TSV shape
(`coordinator_core.ops.workday_complete_backfill_scan`, post the 2026-07-19
"daily changelogs are per-DAY, not per-device" ruling) has no machine column
at all — column 2 is `commit_count`. This port therefore always passes an
empty MACHINE argument and lets `workday-complete-backfill-inject-anchor.py`'s
own `_derive_machine()` fallback (for-each-ref over `work/<machine>/*` refs,
then `coordinator_core.machine_resolver.compute_machine()`) resolve it — the
same fallback path the bash's own `awk` miss (no match) would silently take
today. The pairwise descendant-tip walk itself is preserved verbatim and
generalizes cleanly to the current single-row-per-date shape (a one-element
candidate list short-circuits to that element).

Spec backlink: docs/plans/2026-07-02-backfill-anchor-injection-contract.md § Deliverable A
Spec backlink: pln-de-machine-workday-complete-ba-f1b7e6 § C1
Spec backlink: cross-repo/inbox/2026-07-02-backfill-scan-legacy-anchor-migration.md (example-game-repo-em)
Spec backlink: cross-repo/inbox/2026-07-02-workday-backfill-covered-tip.md (cockpit-em)
Port source: coordinator doctrine repo coordinator/commands/workday-complete.md § Step 3.5 Phase A0
  (nested while-loop `_DESC_TIP` walk + `_A0_INJECTED_*` accumulation + the
  scoped `git add -- "${_A0_INJECTED_FILES[@]}"` commit block)
"""
from __future__ import annotations

import argparse
import contextlib
import datetime
import importlib.util
import io
import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_INJECT_ANCHOR_PATH = os.path.join(_THIS_DIR, "workday-complete-backfill-inject-anchor.py")


_BOOTSTRAP_DONE = False


def _bootstrap_engine() -> None:
    """Put `coordinator/bin/lib` on `sys.path` -- idempotent, safe to call
    more than once.

    What moved and what did not: this mutation used to run at MODULE scope,
    which made every import of this file mutate the `sys.path` of a warm
    server ~50 sessions share. Only the trigger moved; the value inserted is
    byte-for-byte the same.
    """
    global _BOOTSTRAP_DONE
    if _BOOTSTRAP_DONE:
        return
    lib_dir = os.path.join(_THIS_DIR, "lib")
    if lib_dir not in sys.path:
        sys.path.insert(0, lib_dir)
    _BOOTSTRAP_DONE = True


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def _load_inject_anchor_module():
    """In-process import of the sibling hyphenated-filename CLI module.

    Direct-import variant (no subprocess re-exec): the module's own `main()`
    already returns a plain int exit code rather than calling `sys.exit()`
    itself except under its `if __name__ == "__main__":` guard, so importing
    it via `importlib.util.spec_from_file_location` and calling `.main(argv)`
    reuses its full inject/idempotency/content-gap logic in-process.
    """
    spec = importlib.util.spec_from_file_location(
        "workday_complete_backfill_inject_anchor", _INJECT_ANCHOR_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def resolve_full_sha(root: str, sha: str) -> str | None:
    """Full 40-char SHA for `sha` in `root`, or None if it doesn't resolve to a commit."""
    _bootstrap_engine()
    import workday_ceremony_lib as wc

    full = wc.git_out("-C", root, "rev-parse", "--verify", f"{sha}^{{commit}}")
    return full or None


def compute_descendant_tip(root: str, tips: list[str]) -> str | None:
    """The candidate that is a descendant of (or equal to) every other candidate.

    Resolves each of `tips` to its full SHA first (deduping), then — with more
    than one distinct candidate — resolves the dominant tip via one
    `git rev-list --topo-order` walk over the whole candidate set plus one
    ancestor-set walk from the leading candidate, instead of the previous
    O(n^2) pairwise `git merge-base --is-ancestor` walk.

    `git rev-list --topo-order` orders commits so a commit never precedes any
    of its descendants: if a single candidate dominates the rest (is a
    descendant of, or equal to, every other candidate), that candidate is
    necessarily the first of the candidate set to appear in this ordering,
    since every other candidate is one of its ancestors. That gives a
    necessary-but-not-sufficient leading candidate in one spawn; a second
    spawn (`git rev-list <leading-candidate>`, its own ancestor closure) then
    confirms sufficiency by checking every other candidate is a member. Two
    candidates that are mutually incomparable (diverged branches — neither an
    ancestor of the other) fail that confirmation check and fall through to
    the same `None` diverged-branches result the old pairwise walk returned;
    a candidate appearing twice in `tips` was already deduped above and
    contributes one entry to `resolved`.

    Any resolved candidate SHA absent from the `--topo-order` output (it
    should always be present as one of the walk's own start points) is
    treated as a resolution failure and reconciled explicitly rather than
    silently read as "not the answer" — see module test
    `test_missing_topo_output_is_not_silently_ignored`.

    Returns None when no SHA resolves, or when no single candidate dominates
    all others (diverged branches on the same day — a true gap, not an
    A0-mechanical case).
    """
    _bootstrap_engine()
    import workday_ceremony_lib as wc

    resolved: list[str] = []
    for t in tips:
        full = resolve_full_sha(root, t)
        if full is not None and full not in resolved:
            resolved.append(full)

    if not resolved:
        return None
    if len(resolved) == 1:
        return resolved[0]

    topo_out = wc.git_out("-C", root, "rev-list", "--topo-order", *resolved)
    topo_lines = topo_out.splitlines()
    position = {sha: idx for idx, sha in enumerate(topo_lines)}

    missing = [cand for cand in resolved if cand not in position]
    if missing:
        _err(
            "ERROR: candidate SHA(s) absent from `git rev-list --topo-order` "
            f"output (unresolved, not treated as non-dominant): {' '.join(missing)}"
        )
        return None

    leading = min(resolved, key=position.get)

    ancestor_out = wc.git_out("-C", root, "rev-list", leading)
    ancestor_set = set(ancestor_out.splitlines())
    ancestor_set.add(leading)

    if all(other == leading or other in ancestor_set for other in resolved):
        return leading
    return None


def _cmd_descendant_tip(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="workday-complete-backfill-anchor.py descendant-tip",
        description=__doc__,
    )
    parser.add_argument("root")
    parser.add_argument("shas", nargs="+")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.root):
        _err(f"ERROR: ROOT does not exist or is not accessible: {args.root}")
        return 1
    root = os.path.abspath(args.root)

    tip = compute_descendant_tip(root, args.shas)
    if tip is None:
        _err(
            "ERROR: no single SHA is a descendant of all others "
            f"(diverged branches, or none resolved) among: {' '.join(args.shas)}"
        )
        return 1
    print(tip)
    return 0


def _parse_gap_rows(text: str) -> "dict[str, list[str]]":
    """Group gap-row TSV by date, collecting the tip column (col index 3) per row.

    Accepts the scan's current single-row-per-day shape
    (`<date>\\t<commit_count>\\t<base>\\t<tip>`) and degrades gracefully to
    multiple rows sharing one date (a future per-machine format, or hand-fed
    test fixtures) by collecting every distinct tip seen for that date.
    """
    grouped: "dict[str, list[str]]" = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        cols = line.split("\t")
        if len(cols) < 4:
            _err(f"WARN: skipping malformed gap row (expected >=4 tab-separated columns): {line!r}")
            continue
        date, tip = cols[0], cols[3]
        bucket = grouped.setdefault(date, [])
        if tip not in bucket:
            bucket.append(tip)
    return grouped


def _cmd_run(argv: list[str]) -> int:
    _bootstrap_engine()
    import workday_ceremony_lib as wc

    parser = argparse.ArgumentParser(
        prog="workday-complete-backfill-anchor.py run",
        description=__doc__,
    )
    parser.add_argument("root")
    parser.add_argument("--today", default=None, help="Override 'today' (YYYY-MM-DD); defaults to local today.")
    parser.add_argument("--no-commit", action="store_true", help="Skip the batched git add+commit of injected files.")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.root):
        _err(f"ERROR: ROOT does not exist or is not accessible: {args.root}")
        return 1
    root = os.path.abspath(args.root)
    today = args.today or datetime.date.today().strftime("%Y-%m-%d")

    gap_text = sys.stdin.read()
    grouped = _parse_gap_rows(gap_text)

    inject_mod = _load_inject_anchor_module()

    injected_dates: list[str] = []
    content_gap_dates: list[str] = []
    true_gap_dates: list[str] = []
    injected_files: list[str] = []

    for date, tips in grouped.items():
        desc_tip = compute_descendant_tip(root, tips)
        if desc_tip is None:
            _err(f"WARN: no single descendant tip for {date} (diverged branches) — skipping A0, true-gap")
            true_gap_dates.append(date)
            continue

        # Divergence (see module docstring): machine is left empty here and
        # resolved by inject-anchor's own _derive_machine() fallback, since
        # the current scan TSV carries no machine column to forward.
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = inject_mod.main([root, date, desc_tip, today, ""])
        captured = buf.getvalue()

        if rc in (0, 10):
            injected_dates.append(date)
            if rc == 0:
                for out_line in captured.splitlines():
                    if out_line.startswith("TARGET="):
                        target_file = out_line.split("=", 1)[1]
                        if target_file and target_file not in injected_files:
                            injected_files.append(target_file)
        elif rc == 20:
            true_gap_dates.append(date)
        elif rc == 30:
            content_gap_dates.append(date)
        else:
            _err(f"WARN: inject-anchor returned unexpected exit {rc} for {date}; routing to Phase A analyst as true-gap")
            true_gap_dates.append(date)

    committed = 0
    if injected_files and not args.no_commit:
        add_proc = wc.git("-C", root, "add", "--", *injected_files)
        if add_proc.returncode != 0:
            _err(f"ERROR: git add failed for injected files: {add_proc.stderr.strip()}")
            return 1
        commit_proc = wc.git(
            "-C", root, "commit", "-m", "chore(daily-summaries): backfill anchor migration"
        )
        if commit_proc.returncode != 0:
            _err(f"ERROR: git commit failed for injected anchor files: {commit_proc.stderr.strip()}")
            return 1
        committed = 1

    print(f"INJECTED_DATES={' '.join(injected_dates)}")
    print(f"CONTENT_GAP_DATES={' '.join(content_gap_dates)}")
    print(f"TRUE_GAP_DATES={' '.join(true_gap_dates)}")
    print(f"INJECTED_FILES={' '.join(injected_files)}")
    print(f"COMMITTED={committed}")
    return 0


def main(argv: list[str]) -> int:
    _bootstrap_engine()
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if argv and argv[0] in ("-h", "--help") else 1

    sub, rest = argv[0], argv[1:]
    if sub == "descendant-tip":
        return _cmd_descendant_tip(rest)
    if sub == "run":
        return _cmd_run(rest)

    _err(f"ERROR: unknown subcommand '{sub}' (expected 'descendant-tip' or 'run')")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
