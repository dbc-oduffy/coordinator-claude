"""whats-next.py — Prioritized next-work surface for /workday-start Step 4.

Spec backlink: archive/specs/2026-05-05-script-first-deterministic-ops.md §T3

Purpose: Replace the 7-file manual read chain in /workday-start Step 4 with a
single deterministic entry point. Emits two priority surfaces to stdout:
  1. Top 5 central entries from state/improvement-queue/*.yaml (queue_scope: central).
  2. Open handoffs (filename + line-1 heading), excluding archived/superseded.

Output is plaintext for the EM to frame. No clustering or narrative.

Exit codes: 0 in normal operation; 1 only when not inside a git repository.
Missing files produce "(not found)" notices, not errors.

Port of: whats-next.sh (DoE 8fa54776, 2026-07-21) — Windows-first de-bash:
zero bash anywhere on the reporter's critical path. State-root resolution
shells out to `python3 -m coordinator_core.state_root` (the same native
module the improved bash oracle itself called), not bash.

Negative-spec: does NOT extend bin/query-records. No tracker render is read
or emitted — docs/project-tracker.md is being retired fleet-wide (docs/plans/
2026-08-14-retire-the-handoff-tracker-and-project-tracker-renders.md; file
deletion deferred to that plan's AC8, coordinated with § C6); this tool never
depended on it and runs clean whether or not a tracker file is present.
"""

import os
import re
import subprocess
import sys

# Review: code-reviewer — F1 (P1): whats-next.py had regressed behind its own bash
# oracle, reintroducing a `bash <seam>.sh` shell-out the oracle had already
# removed (raises uncaught FileNotFoundError on a bash-less Windows box — the
# exact audience this campaign exists for). Replaced with the improved oracle's
# own call shape: `python3 -m coordinator_core.state_root`, CLAUDE_KLABAUTER_ROOT resolved
# natively via the shared cc_invoke ladder (zero bash anywhere in the chain).


def _resolve_claude_klabauter_root_silent() -> "str | None":
    """Resolve CLAUDE_KLABAUTER_ROOT via the shared cc_invoke resolver (self-location-first);
    None on any failure."""
    try:
        lib_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
        if lib_dir not in sys.path:
            sys.path.insert(0, lib_dir)
        import cc_invoke  # noqa: E402  (path injected above)

        return cc_invoke.resolve_engine_root(__file__)
    except Exception:
        return None


def _no_console_window() -> dict:
    """`**no_console_creationflags()` when coordinator_core is resolvable;
    falls back to the inline literal (0 elsewhere) if CLAUDE_KLABAUTER_ROOT cannot be
    resolved yet — this CLI's own repo-root discovery (`main`'s call into
    `repo_identity.resolve_checked_repo_root`) may run before CLAUDE_KLABAUTER_ROOT is
    known.

    Review: coordinator:code-reviewer — consolidated onto the single
    resolution path this file already owns (`_resolve_claude_klabauter_root_silent`),
    matching sibling standup.py's pattern instead of re-deriving the
    lib_dir/sys.path/cc_invoke import boilerplate a second time in this file.
    """
    try:
        claude_klabauter_root = _resolve_claude_klabauter_root_silent()
        if claude_klabauter_root is None:
            raise RuntimeError("CLAUDE_KLABAUTER_ROOT unresolved")
        import cc_invoke  # noqa: E402  (path injected by _resolve_claude_klabauter_root_silent)

        return cc_invoke._no_console_kw(claude_klabauter_root)
    except Exception:
        return (
            {"creationflags": subprocess.CREATE_NO_WINDOW}
            if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW")
            else {}
        )


def _resolve_state_root(*args: str):
    """Invoke `python3 -m coordinator_core.state_root` natively.

    Returns (path_or_None, returncode). Callers decide whether a non-zero rc is
    fatal — the improvement-queue read degrades gracefully on failure while the
    handoffs read relies on the default (no-arg) resolution succeeding.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root_silent()
    if not claude_klabauter_root:
        return None, 2
    env = dict(os.environ)
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{claude_klabauter_root}{os.pathsep}{existing_pp}" if existing_pp else claude_klabauter_root
    result = subprocess.run(
        [sys.executable, "-m", "coordinator_core.state_root", *args],
        capture_output=True,
        text=True,
        env=env,
        **_no_console_window(),
    )
    if result.returncode != 0:
        return None, result.returncode
    return result.stdout.strip(), 0


def _heading(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return "(no heading)"
    return re.sub(r"^#* *", "", first.rstrip("\n"))


def main() -> int:
    # Resolve repo root via the checked resolver. READER (AC10): a MISMATCH
    # verdict is warned to stderr and the resolved root used anyway (DR-277);
    # UNRESOLVED never refuses either (AC4).
    lib_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
    if lib_dir not in sys.path:
        sys.path.insert(0, lib_dir)
    from repo_identity import resolve_checked_repo_root  # noqa: E402  (path injected above)

    repo_root, verdict = resolve_checked_repo_root(explicit_root=None)
    if repo_root is None:
        sys.stderr.write("ERROR: not inside a git repository\n")
        return 1
    if verdict["verdict"] == "MISMATCH":
        sys.stderr.write(verdict["message"] + "\n")

    # -----------------------------------------------------------------------
    # Section 1: Coordinator improvement queue — top 5 central entries
    # -----------------------------------------------------------------------
    print("== Improvement queue (top 5 central) ==")
    # Graceful-degradation: --subject doctrine fails loud on non-DoE machines.
    doctrine_root, rc = _resolve_state_root("--central", "--subject", "doctrine")
    if rc == 0 and doctrine_root:
        queue_dir = os.path.join(doctrine_root, "improvement-queue")
    else:
        sys.stderr.write(
            "  WARN: central doctrine state root unresolvable — skipping "
            "improvement queue (non-DoE machine)\n"
        )
        queue_dir = ""

    if queue_dir and os.path.isdir(queue_dir):
        central_titles = []
        yaml_files = sorted(
            fn for fn in os.listdir(queue_dir)
            if fn.endswith(".yaml") and os.path.isfile(os.path.join(queue_dir, fn))
        )
        for fn in yaml_files:
            fp = os.path.join(queue_dir, fn)
            is_central = False
            title = "(no title)"
            title_found = False
            try:
                with open(fp, "r", encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        line = line.rstrip("\n")
                        if line.startswith("queue_scope: central"):
                            is_central = True
                        if not title_found and line.startswith("title:"):
                            title = re.sub(r"^title:\s*", "", line)
                            title_found = True
            except OSError:
                continue
            if is_central:
                central_titles.append(title)
        total = len(central_titles)
        if total > 0:
            show = min(total, 5)
            for i in range(show):
                print(f"  - {central_titles[i]}")
            if total > 5:
                print(f"  ... and {total - 5} more central entries")
        else:
            print("  (no central improvement entries)")
    else:
        print("  (state/improvement-queue/ not found)")
    print()

    # -----------------------------------------------------------------------
    # Section 2: Open handoffs — filename + line-1 heading
    # -----------------------------------------------------------------------
    print("== Open handoffs ==")
    default_root, rc = _resolve_state_root()
    handoffs_dir = os.path.join(default_root, "handoffs") if rc == 0 and default_root else ""
    if handoffs_dir and os.path.isdir(handoffs_dir):
        files = sorted(
            fn for fn in os.listdir(handoffs_dir)
            if fn.endswith(".md") and os.path.isfile(os.path.join(handoffs_dir, fn))
        )
        hit = False
        for fn in files:
            fp = os.path.join(handoffs_dir, fn)
            fm_status = ""
            try:
                with open(fp, "r", encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        if line.startswith("status:"):
                            fm_status = line.rstrip("\n").replace(" ", "")
                            break
            except OSError:
                fm_status = ""
            if fm_status in ("status:archived", "status:superseded"):
                continue
            print(f"  {fn:<50}  # {_heading(fp)}")
            hit = True
        if not hit:
            print("  (no open handoffs)")
    else:
        print("  (state/handoffs/ not found)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
