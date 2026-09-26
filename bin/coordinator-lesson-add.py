from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
import sys
import tempfile

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))


def _is_swept_tmp_root(path: str) -> bool:
    try:
        real = os.path.realpath(path)
        tmp = os.path.realpath(tempfile.gettempdir())
    except OSError:
        return False
    under_tmp = real == tmp or real.startswith(tmp + os.sep)
    return under_tmp and not os.path.isdir(path)


def _bootstrap_imports() -> None:
    global _mlir_claude_home, _mlir_machine_local_impl_path, coordinator_engine_root_env

    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from machine_local_impl_resolve import (
        claude_home as _mlir_claude_home,
        machine_local_impl_path as _mlir_machine_local_impl_path,
    )
    from cc_invoke import require_engine_on_path

    require_engine_on_path(__file__)

    from coordinator_core.engine_root import coordinator_engine_root_env


# Mirrors coordinator-queue-append._QUEUE_APPEND_OUTPUT_ROOT_ENV for test isolation.
# When set, the dedup scan looks under <QUEUE_APPEND_OUTPUT_ROOT>/state/lessons/
_QUEUE_APPEND_OUTPUT_ROOT_ENV = "QUEUE_APPEND_OUTPUT_ROOT"


def _isolation_root(env_var: str, caller_name: str) -> str | None:
    value = (os.environ.get(env_var) or "").strip()
    if not value:
        return None
    if os.environ.get("PYTEST_CURRENT_TEST"):
        if _is_swept_tmp_root(value):
            print(
                f"error: {caller_name}: refusing dedup scan under {env_var}="
                f"{value!r} — this test-isolation root resolves under the "
                f"system temp directory and no longer exists (a swept pytest "
                f"tmp_path, inherited by a long-lived process). Unset "
                f"{env_var} before invoking {caller_name} outside a test.",
                file=sys.stderr,
            )
            sys.exit(1)
        return value
    print(
        f"{caller_name}: ignoring inherited {env_var}={value} — a test-isolation "
        f"redirect outside a test run. Writing to the resolved repo path instead.",
        file=sys.stderr,
    )
    return None


def _child_cli_must_come_from_tree() -> bool:
    """True when the delegated `coordinator-queue-append` child must be run
    from THIS tree's source rather than the PATH launcher a bare name
    resolves to.

    Mirrors `coordinator-harvest-deferrals._child_cli_must_come_from_tree`
    (see that docstring for the full mechanism). A bare `coordinator-queue-
    append` on PATH resolves to the shared warm-door binary, whose JSON-RPC
    payload carries argv and cwd and NO env — the served CLI runs inside the
    resident engine under the SERVER's own environment, so a
    `QUEUE_APPEND_OUTPUT_ROOT` this process holds never reaches it, and
    `warm/server.py::_scrub_test_harness_env` drops it at boot regardless.
    A redirect this process is honouring for its own dedup scan (`_lessons_dir`)
    but cannot hand to a door-routed child is the same leak
    `coordinator-harvest-deferrals` measured for `LESSON_PROMOTE_OUTBOX_ROOT`
    (148+ stray fixture rows) — pinning the tree runs the child cold, in this
    process tree, the only route where the redirect applies by design.

    Requires BOTH a redirect and `PYTEST_CURRENT_TEST`, matching
    `_isolation_root`'s own gate above: a redirect inherited outside a test
    run is already ignored there and must not pin the tree either.

    Negative-spec: an interactive session sets no redirect, so this returns
    False and the door stays the target — warm dispatch is the contract and
    the budget for every live invocation.
    """
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    return bool((os.environ.get(_QUEUE_APPEND_OUTPUT_ROOT_ENV) or "").strip())


# Mirrors coordinator-queue-append._CLAUDE_HOME_ENV for test isolation.
# "CLAUDE_HOME" internally), but re-checked against current disk before
# (`_cli_mod._CLAUDE_HOME_ENV`) for env-isolation setup/teardown. Kept.
_CLAUDE_HOME_ENV = "CLAUDE_HOME"

# Mirrors coordinator-queue-append._MACHINE_LOCAL_IMPL_ENV for test isolation.
_MACHINE_LOCAL_IMPL_ENV = "MACHINE_LOCAL_IMPL"


def _git_root():
    from coordinator_core.git.repo_root import show_toplevel

    return show_toplevel()


def _claude_home() -> str:
    """Return the ~/.claude root, honouring CLAUDE_HOME env var for test isolation.

    Mirrors coordinator-queue-append._claude_home(). Delegates to
    machine_local_impl_resolve.claude_home() (shared resolver).
    """
    _bootstrap_imports()
    return _mlir_claude_home()


def _machine_local_get(key: str):
    _bootstrap_imports()
    impl = _mlir_machine_local_impl_path(_MACHINE_LOCAL_IMPL_ENV)
    try:
        from coordinator_core.win_portability import no_console_creationflags, no_console_passthrough_kwargs

        result = subprocess.run(
            [sys.executable, impl, "get", key],
            capture_output=True,
            text=True,
            **no_console_creationflags(),
        )
    except OSError:
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.strip()


def _claude_klabauter_root():
    """Resolve the claude-klabauter repo root, returning None when unresolvable.

    Resolution chain:
      1. COORDINATOR_ENGINE_ROOT env var, via the accessor — trusted as-is
         (§4b idempotency gate).
      2. machine-local get repos.claude_klabauter.
      3. Returns None when unresolvable (caller degrades gracefully).

    Mirrors coordinator-queue-append._claude_klabauter_root().
    Spec backlink: pln-stop-the-rot-claude-klabauter-state-home-placement-4cc787 § AC1 / AC13
    """
    _bootstrap_imports()
    override = (coordinator_engine_root_env(__name__) or "").strip()
    if override:
        return override
    val = _machine_local_get("repos.claude_klabauter")
    return val if val else None


def _same_path(a: str, b: str) -> bool:
    from coordinator_core.win_portability import no_console_passthrough_kwargs, same_path

    return same_path(a, b)


def _lessons_dir():
    """Return the directory to scan for existing lesson entries (dedup pre-check).

    Resolution mirrors the routing logic of coordinator-queue-append._output_path for the lessons schema:
      1. QUEUE_APPEND_OUTPUT_ROOT env override → <override>/state/lessons
      2. Meta-repo cwd (git root == ~/.claude) → <claude-klabauter>/state/lessons
         (mirrors queue-append._output_path else-branch stop-the-rot routing so
         the dedup scan looks where queue-append actually writes)
      3. cwd git-root → <root>/state/lessons
      4. Fallback → cwd-relative state/lessons
    Tolerates the directory not existing (returns the path; caller checks isdir).
    On unresolvable claude-klabauter root, emits a stderr warning and falls back to the
    git-root path (dedup pre-check degrades to no-op rather than crashing).

    Negative-spec: WITHOUT this meta-repo routing, cwd=~/.claude causes the dedup
    scan to look in ~/.claude/state/lessons while queue-append writes to
    <claude-klabauter>/state/lessons — the dedup check silently misses all existing entries.
    Fix: align with queue-append._output_path else-branch (stop-the-rot taxonomy).
    Spec backlink: state/bug-backlog/2026-07-06-lesson-add-dedup-scans-wrong-dir-in-meta.yaml
    """
    override = _isolation_root(
        _QUEUE_APPEND_OUTPUT_ROOT_ENV, "coordinator-lesson-add"
    )
    if override:
        return os.path.join(override, "state", "lessons")
    root = _git_root()
    if root:
        home = _claude_home()
        if _same_path(root, home):
            claude_klabauter_root = _claude_klabauter_root()
            if claude_klabauter_root is not None:
                return os.path.join(claude_klabauter_root, "state", "lessons")
            print(
                "coordinator-lesson-add: warning: claude-klabauter root unresolvable; "
                "dedup pre-check will miss all existing entries in claude-klabauter; "
                "lesson will still be written correctly by coordinator-queue-append",
                file=sys.stderr,
            )
        return os.path.join(root, "state", "lessons")
    return os.path.join(os.getcwd(), "state", "lessons")


def _tokenize(text):
    STOP = {
        "the", "a", "an", "is", "in", "on", "at", "to", "of", "and",
        "or", "for", "not", "be", "are", "was", "with", "from", "by",
        "its", "it", "has", "via",
    }
    return {t for t in re.findall(r"[a-z0-9]+", text.lower())
            if len(t) > 2 and t not in STOP}


def _title_overlap(a, b):
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta), len(tb))


def _read_yaml_title(path):
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                m = re.match(r"^title:\s*(.+)$", line.rstrip())
                if m:
                    val = m.group(1).strip()
                    if len(val) >= 2 and val[0] == '"' and val[-1] == '"':
                        try:
                            val = json.loads(val)
                        except (json.JSONDecodeError, ValueError):
                            val = val[1:-1].replace('\\"', '"')
                    return val
    except OSError:
        pass
    return None


def _dedup_check(new_title):
    lessons = _lessons_dir()
    if not os.path.isdir(lessons):
        return []
    matches = []
    for path in sorted(glob.glob(os.path.join(lessons, "*.yaml"))):
        existing = _read_yaml_title(path)
        if existing is None:
            continue
        overlap = _title_overlap(new_title, existing)
        is_substr = (
            new_title.lower() in existing.lower()
            or existing.lower() in new_title.lower()
        )
        if overlap >= 0.60 or is_substr:
            matches.append((path, existing))
    return matches


def main(argv: "list[str] | None" = None) -> int:
    _bootstrap_imports()
    parser = argparse.ArgumentParser(
        prog="coordinator-lesson-add",
        description=(
            "Add a lesson entry to state/lessons/ — thin wrapper over "
            "coordinator-queue-append --schema lessons with a dedup pre-check."
        ),
    )
    parser.add_argument(
        "--title", default=None, metavar="TEXT",
        help=(
            "One-line lesson title. Exactly one of --title / --title-file "
            "is required."
        ),
    )
    parser.add_argument(
        "--title-file", dest="title_file", default=None, metavar="PATH",
        help=(
            "Read the lesson title from PATH ('-' for stdin) instead of "
            "--title. Exactly one of --title / --title-file is required. "
            "Survives the LAUNCHER leg intact — see --title's own refusal "
            "for why. It does NOT make a title multi-line: the title becomes "
            "the output filename's slug, so it is resolved to a single-line "
            "value here and passed inline to coordinator-queue-append, which "
            "has no --title-file for that same reason."
        ),
    )
    parser.add_argument(
        "--body", default=None, metavar="TEXT",
        help="Lesson body prose. Exactly one of --body / --body-file is required.",
    )
    parser.add_argument(
        "--body-file", dest="body_file", default=None, metavar="PATH",
        help=(
            "Read the lesson body from PATH ('-' for stdin) instead of --body. "
            "Exactly one of --body / --body-file is required. The only body "
            "transport that survives every launcher leg intact — see --body's "
            "own refusal for why."
        ),
    )
    parser.add_argument(
        "--scope", required=True, metavar="VALUE",
        help="Scope classification: universal | project | wiki-only (required).",
    )
    parser.add_argument(
        "--target-wiki", dest="target_wiki", default=None, metavar="TEXT",
        help="Routing clause — belongs in <wiki>.md (optional).",
    )
    parser.add_argument(
        "--proposed-target", dest="proposed_target", default=None, metavar="TEXT",
        help="Doctrine/wiki/hook/skill the lesson routes to (optional).",
    )
    parser.add_argument(
        "--evidence", default=None, metavar="TEXT",
        help="Provenance: commit SHA, plan path, or related reference (optional).",
    )
    parser.add_argument(
        "--trigger", default=None, metavar="TEXT",
        help=(
            "The concrete situation or event that surfaced this lesson (optional). "
            "author-supplied; do NOT LLM-extract from existing prose."
        ),
    )
    parser.add_argument(
        "--why", default=None, metavar="TEXT",
        help=(
            "Root-cause explanation — why this matters and what breaks without it (optional). "
            "author-supplied; do NOT LLM-extract from existing prose."
        ),
    )
    parser.add_argument(
        "--why-file", dest="why_file", default=None, metavar="PATH",
        help=(
            "Read --why from PATH ('-' for stdin) instead of an inline "
            "value (optional). The only --why transport that survives "
            "every launcher leg intact — see --why's own refusal for why."
        ),
    )
    parser.add_argument(
        "--how-to-apply", dest="how_to_apply", default=None, metavar="TEXT",
        help=(
            "Actionable guidance for applying this lesson in future situations (optional). "
            "author-supplied; do NOT LLM-extract from existing prose."
        ),
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Skip the dedup pre-check and write unconditionally.",
    )

    args = parser.parse_args(argv)

    from coordinator_core.argv_fidelity import (
        ArgvFidelityError,
        refuse_newline_argv,
        resolve_body,
        resolve_optional_prose,
    )

    try:
        refuse_newline_argv(args.body, flag_name="--body")
        args.body = resolve_body(args.body, args.body_file)
        args.title = resolve_body(args.title, args.title_file, flag_name="--title")
        refuse_newline_argv(
            args.title,
            flag_name="--title-file" if args.title_file else "--title",
            remedy=(
                "a lesson title must be a single line -- it becomes the output "
                "filename's slug, which cannot carry a newline losslessly. "
                "Put the detail in --body/--body-file instead."
            ),
        )
        args.why = resolve_optional_prose(args.why, args.why_file, flag_name="--why")
    except ArgvFidelityError as exc:
        parser.error(str(exc))

    if not args.force:
        dupes = _dedup_check(args.title)
        if dupes:
            path, existing_title = dupes[0]
            fname = os.path.basename(path)
            print(
                'possible duplicate of ' + fname + ': "' + existing_title + '"'
                ' — re-run with --force to add anyway, or amend the existing entry',
                file=sys.stderr,
            )
            return 1

    # directory. Direct `__main__` execution implicitly puts _THIS_DIR on
    # this CLI is a CONSUMES_MANIFEST member) does not — mirrors the guard in
    if _THIS_DIR not in sys.path:
        sys.path.insert(0, _THIS_DIR)
    from _queue_append_locator import find_cli_cmd

    cli_cmd = find_cli_cmd(
        _THIS_DIR,
        "coordinator-queue-append",
        sibling_only=_child_cli_must_come_from_tree(),
    )
    if cli_cmd is None:
        print(
            "no python interpreter resolvable for coordinator-queue-append"
            " (sys.executable is " + repr(sys.executable) + ")"
            " — run coordinator-queue-append.py directly",
            file=sys.stderr,
        )
        return 1

    # FORWARD THE FILE, NEVER THE RESOLVED PROSE. `resolve_body` above reads
    cmd = [
        *cli_cmd,
        "--schema", "lessons",
        "--title", args.title,
        "--scope", args.scope,
    ]
    if args.body_file:
        cmd += ["--body-file", args.body_file]
    else:
        cmd += ["--body", args.body]
    if args.target_wiki:
        cmd += ["--target-wiki", args.target_wiki]
    if args.proposed_target:
        cmd += ["--proposed-target", args.proposed_target]
    if args.evidence:
        cmd += ["--evidence", args.evidence]
    if args.trigger:
        cmd += ["--trigger", args.trigger]
    if args.why_file:
        cmd += ["--why-file", args.why_file]
    elif args.why:
        cmd += ["--why", args.why]
    if args.how_to_apply:
        cmd += ["--how-to-apply", args.how_to_apply]

    from coordinator_core.win_portability import no_console_creationflags, no_console_passthrough_kwargs
    from coordinator_core.session.core import subprocess_identity_env

    # `env=` is not optional here. This CLI is a CONSUMES_MANIFEST member that
    # `workstream_complete.apply` loads and runs IN-PROCESS -- inside the warm
    # is a CONSUMES_MANIFEST member `workstream_complete.apply` runs
    # IN-PROCESS inside the warm server (see the `env=` note above), where
    _passthrough = no_console_passthrough_kwargs()
    _relay_stderr = "stderr" not in _passthrough
    if _relay_stderr:
        _passthrough["stderr"] = subprocess.PIPE
    result = subprocess.run(
        cmd,
        env=subprocess_identity_env(),
        **_passthrough,
    )
    if result.returncode != 0:
        child_stderr = (result.stderr or b"") if _relay_stderr else b""
        if isinstance(child_stderr, bytes):
            child_stderr = child_stderr.decode("utf-8", errors="replace")
        detail = child_stderr.strip()
        print(
            "coordinator-queue-append exited " + str(result.returncode)
            + " — no lesson was written"
            + (f"\ncoordinator-queue-append stderr:\n{detail}" if detail else ""),
            file=sys.stderr,
        )
    else:
        child_stdout = result.stdout
        if isinstance(child_stdout, bytes):
            child_stdout = child_stdout.decode("utf-8", errors="replace")
        if isinstance(child_stdout, str) and child_stdout.strip():
            print(child_stdout.strip())
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
