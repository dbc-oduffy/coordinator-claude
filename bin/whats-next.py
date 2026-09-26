
import os
import re
import sys


def _resolve_claude_klabauter_root_silent() -> "str | None":
    try:
        lib_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
        if lib_dir not in sys.path:
            sys.path.insert(0, lib_dir)
        import cc_invoke  # noqa: E402  (path injected above)

        return cc_invoke.resolve_engine_root(__file__)
    except Exception:
        return None


def _resolve_state_root(*args: str):
    import contextlib
    import io

    claude_klabauter_root = _resolve_claude_klabauter_root_silent()
    if not claude_klabauter_root:
        return None, 2
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)

    from coordinator_core.state_root import main as _state_root_main

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
        rc = _state_root_main(list(args))
    if rc != 0:
        return None, rc
    return stdout_buf.getvalue().strip(), 0


def _heading(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return "(no heading)"
    return re.sub(r"^#* *", "", first.rstrip("\n"))


def main(argv: "list[str] | None" = None) -> int:
    del argv
    # Resolve repo root via the checked resolver. READER (AC10): a MISMATCH
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

    print("== Improvement queue (top 5 central) ==")
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
