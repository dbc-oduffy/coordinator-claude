
import os
import re
import subprocess
import sys
from datetime import date, datetime, time


def _resolve_claude_klabauter_root_silent() -> str | None:
    try:
        lib_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
        if lib_dir not in sys.path:
            sys.path.insert(0, lib_dir)
        import cc_invoke  # noqa: E402  (path injected above)

        return cc_invoke.resolve_engine_root(__file__)
    except Exception:
        return None


def _no_console_window() -> dict:
    try:
        lib_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
        if lib_dir not in sys.path:
            sys.path.insert(0, lib_dir)
        import cc_invoke  # noqa: E402  (path injected above)

        claude_klabauter_root = cc_invoke.resolve_engine_root(__file__)
        return cc_invoke._no_console_kw(claude_klabauter_root)
    except Exception:
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def _resolve_state_root(*args: str) -> str:
    claude_klabauter_root = _resolve_claude_klabauter_root_silent()
    if not claude_klabauter_root:
        sys.stderr.write(
            "coordinator_state_root: cannot resolve CLAUDE_KLABAUTER_ROOT "
            "(see docs/wiki/machine-local-registry.md)\n"
        )
        sys.exit(2)
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
        sys.stderr.write(result.stderr)
        sys.exit(result.returncode)
    return result.stdout.strip()


def _git(args, cwd):
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, **_no_console_window()
    )


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

    state_root = _resolve_state_root()

    baseline_sha = _git(
        ["log", "--oneline", "-E",
         "--grep=^(workday-complete|workday-start):",
         "--since=3 days ago", "-1", "--format=%H"],
        repo_root,
    ).stdout.strip()

    if baseline_sha:
        r = _git(["log", "-1", "--format=%ai", baseline_sha], repo_root)
        baseline_ts = r.stdout.strip() if r.returncode == 0 else "unknown"
    else:
        out = _git(["log", "--since=24 hours ago", "--format=%H"], repo_root).stdout
        shas = [ln for ln in out.splitlines() if ln.strip()]
        if shas:
            baseline_sha = shas[-1]
            r = _git(["log", "-1", "--format=%ai", baseline_sha], repo_root)
            baseline_ts = r.stdout.strip() if r.returncode == 0 else "unknown"
        else:
            baseline_sha = "HEAD"
            baseline_ts = "(no commits in 24h)"

    print(f"> Baseline: {baseline_sha} ({baseline_ts})")
    print()

    print("== Commits today ==")
    if baseline_sha == "HEAD":
        print("  (no commits since baseline)")
    else:
        r = _git(["log", f"{baseline_sha}..HEAD", "--oneline", "--stat"], repo_root)
        if r.returncode == 0:
            sys.stdout.write(r.stdout)
        else:
            print("  (git log failed)")
    print()

    print("== Files changed by dir ==")
    if baseline_sha != "HEAD":
        r = _git(["diff", "--name-only", f"{baseline_sha}..HEAD"], repo_root)
        if r.returncode == 0:
            counts: dict[str, int] = {}
            for path in r.stdout.splitlines():
                if not path:
                    continue
                parts = path.split("/")
                key = parts[0] if len(parts) == 1 else parts[0] + "/"
                counts[key] = counts.get(key, 0) + 1
            for dir_, cnt in sorted(counts.items(), key=lambda kv: (kv[1], kv[0]), reverse=True):
                print(f"  {dir_:<20} {cnt}")
        else:
            print("  (diff failed)")
    else:
        print("  (no baseline commit)")
    print()

    today_anchor = date.today()
    midnight = datetime.combine(today_anchor, time(0, 0, 0)).timestamp()

    def _touched_today(path: str) -> bool:
        try:
            return os.path.getmtime(path) > midnight
        except OSError:
            return False

    print("== Handoffs touched today ==")
    handoffs_dir = os.path.join(state_root, "handoffs")
    if os.path.isdir(handoffs_dir):
        hits = []
        for root, _dirs, files in os.walk(handoffs_dir):
            for fn in files:
                if fn.endswith(".md"):
                    p = os.path.join(root, fn)
                    if _touched_today(p):
                        hits.append(p)
        if hits:
            for p in sorted(hits, key=os.path.basename):
                print(f"  {os.path.basename(p):<50}  # {_heading(p)}")
        else:
            print("  (none modified today)")
    else:
        print("  (state/handoffs/ not found)")
    print()

    print("== Todo files touched today ==")
    tasks_dir = os.path.join(repo_root, "tasks")
    if os.path.isdir(tasks_dir):
        hits = []
        for entry in os.listdir(tasks_dir):
            todo = os.path.join(tasks_dir, entry, "todo.md")
            if os.path.isfile(todo) and _touched_today(todo):
                hits.append(todo)
        if hits:
            for todo in sorted(hits):
                rel = os.path.relpath(todo, repo_root).replace(os.sep, "/")
                print(f"  {rel:<50}  # {_heading(todo)}")
        else:
            print("  (none modified today)")
    else:
        print("  (tasks/ not found)")
    print()

    print("== Active handoffs ==")
    if os.path.isdir(handoffs_dir):
        files = sorted(
            fn for fn in os.listdir(handoffs_dir)
            if fn.endswith(".md") and os.path.isfile(os.path.join(handoffs_dir, fn))
        )
        if files:
            for fn in files:
                print(f"  {fn:<50}  # {_heading(os.path.join(handoffs_dir, fn))}")
        else:
            print("  (no active handoffs)")
    else:
        print("  (state/handoffs/ not found)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
