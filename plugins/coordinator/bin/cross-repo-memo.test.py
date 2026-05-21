#!/usr/bin/env python3
"""
cross-repo-memo.test.py — smoke tests for the cross-repo-memo dispatcher CLI.

Spec backlink: docs/plans/2026-05-21-cross-repo-memo-discoverability.md § Chunk 2
Purpose: Verify the four critical behaviours of the dispatcher:
  - Test 1: receiver-repo delivery writes both receiver-side and archive copies
  - Test 2: central-only fallback when machine-local key is absent
  - Test 3: --self-receipt sets action_taken lifecycle fields
  - Test 4: --self-receipt without --decision exits non-zero

Run with: python3 bin/cross-repo-memo.test.py
"""

import os
import subprocess
import sys
import tempfile
import textwrap

# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------

TESTS_PASSED = 0
TESTS_FAILED = 0
FAILURES: list[str] = []


def _script_path() -> str:
    """Return the absolute path to cross-repo-memo."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "cross-repo-memo")


def _python() -> str:
    """Return the Python interpreter to use for subprocess invocations.

    Uses sys.executable directly — the interpreter running this test script
    is always a valid Python 3 interpreter. Probing python3/python via
    subprocess raises FileNotFoundError on Windows when neither alias exists.
    sys.executable is the Windows-compatible zero-probe pattern.
    """
    return sys.executable


def _run_dispatcher(args: list[str], env: dict[str, str], stdin_text: str = "") -> subprocess.CompletedProcess:
    """Invoke the dispatcher CLI as a subprocess with the given environment.

    Always drives via `python <script>` — the script has no .py extension
    and is not directly executable on Windows. Using the interpreter explicitly
    is the Windows-compatible pattern, same as how machine-local is driven.
    """
    return subprocess.run(
        [_python(), _script_path()] + args,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        input=stdin_text,
    )


def _parse_frontmatter(content: str) -> dict[str, str]:
    """Parse the YAML frontmatter block from a memo file.

    Minimal parser — handles simple key: value lines within --- delimiters.
    Sufficient for smoke-test assertions; does not handle multi-line or complex values.
    """
    lines = content.splitlines()
    in_fm = False
    fm: dict[str, str] = {}
    for line in lines:
        if line.strip() == "---":
            if not in_fm:
                in_fm = True
                continue
            else:
                break
        if in_fm and ":" in line:
            key, _, val = line.partition(":")
            v = val.strip()
            # Strip surrounding YAML double-quotes (dispatcher quotes string values
            # per F3 fix); unescape \" and \\.
            if len(v) >= 2 and v.startswith('"') and v.endswith('"'):
                v = v[1:-1].replace('\\"', '"').replace("\\\\", "\\")
            fm[key.strip()] = v
    return fm


def pass_test(name: str) -> None:
    global TESTS_PASSED
    TESTS_PASSED += 1
    print(f"  PASS: {name}")


def fail_test(name: str, reason: str) -> None:
    global TESTS_FAILED
    TESTS_FAILED += 1
    msg = f"  FAIL: {name} — {reason}"
    FAILURES.append(msg)
    print(msg)


def _make_mock_machine_local(tmpdir: str, return_value: str | None) -> str:
    """Create a stub machine-local Python script in tmpdir.

    When return_value is None, the stub exits non-zero (key not found).
    When return_value is a string, the stub prints it and exits 0.
    The stub is driven via MACHINE_LOCAL_IMPL env var.
    """
    stub_path = os.path.join(tmpdir, "_mock_machine_local.py")
    if return_value is None:
        script = textwrap.dedent(f"""\
            #!/usr/bin/env python3
            import sys
            print("machine-local: key not found", file=sys.stderr)
            sys.exit(1)
        """)
    else:
        escaped = return_value.replace("\\", "\\\\")
        script = textwrap.dedent(f"""\
            #!/usr/bin/env python3
            import sys
            print("{escaped}")
            sys.exit(0)
        """)
    with open(stub_path, "w") as f:
        f.write(script)
    return stub_path


# ---------------------------------------------------------------------------
# Test 1 — receiver-repo delivery mode (mocked machine-local)
# ---------------------------------------------------------------------------

def test_receiver_repo_delivery() -> None:
    name = "Test 1 — receiver-repo delivery mode"
    import datetime

    with tempfile.TemporaryDirectory() as receiver_tmpdir, \
         tempfile.TemporaryDirectory() as archive_tmpdir:

        mock_impl = _make_mock_machine_local(receiver_tmpdir, receiver_tmpdir)

        env = {
            **os.environ,
            "MACHINE_LOCAL_IMPL": mock_impl,
            "CLAUDE_HOME": archive_tmpdir,
        }

        result = _run_dispatcher(
            ["--to", "project-rag-em", "--topic", "test-topic", "--title", "Test Memo"],
            env=env,
            stdin_text="This is the test memo body.\n",
        )

        if result.returncode != 0:
            fail_test(name, f"dispatcher exited {result.returncode}: {result.stderr}")
            return

        today = datetime.date.today().isoformat()
        filename = f"{today}-test-topic.md"

        # Assert receiver-side file exists.
        receiver_file = os.path.join(receiver_tmpdir, "tasks", "memos", filename)
        if not os.path.isfile(receiver_file):
            fail_test(name, f"receiver-side file not found at {receiver_file}")
            return

        # Assert archive copy exists.
        archive_file = os.path.join(archive_tmpdir, "archive", "cross-repo", filename)
        if not os.path.isfile(archive_file):
            fail_test(name, f"archive copy not found at {archive_file}")
            return

        # Parse frontmatter from both.
        with open(receiver_file) as f:
            receiver_content = f.read()
        with open(archive_file) as f:
            archive_content = f.read()

        receiver_fm = _parse_frontmatter(receiver_content)
        archive_fm = _parse_frontmatter(archive_content)

        if receiver_fm.get("status") != "open":
            fail_test(name, f"receiver status should be 'open', got: {receiver_fm.get('status')}")
            return
        if receiver_fm.get("delivery_mode") != "receiver-repo":
            fail_test(name, f"receiver delivery_mode should be 'receiver-repo', got: {receiver_fm.get('delivery_mode')}")
            return
        if archive_fm.get("receiver_copy_path") != receiver_file:
            fail_test(name, f"archive receiver_copy_path mismatch: {archive_fm.get('receiver_copy_path')!r} != {receiver_file!r}")
            return

        # Assert receiver-side file is NOT staged (git init a fresh repo in tmpdir
        # to make git status meaningful — the real receiver has its own git repo).
        # We verify that the file exists as untracked rather than staged in a fake repo.
        subprocess.run(
            ["git", "init", receiver_tmpdir],
            capture_output=True,
            check=False,
        )
        git_status = subprocess.run(
            ["git", "-C", receiver_tmpdir, "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
        )
        status_output = git_status.stdout
        # The memo should appear as untracked. Git may surface it as:
        #   - `?? tasks/memos/<file>` (if tasks/memos/ was already tracked)
        #   - `?? tasks/` (if tasks/ itself is untracked — new repo, nothing staged)
        # Either form confirms the file is NOT staged. We check that no staged
        # entry (A  prefix) appears for the memo path AND that the tasks/ tree
        # appears untracked somewhere in the output.
        memo_rel = os.path.relpath(receiver_file, receiver_tmpdir).replace("\\", "/")
        staged_in_output = (
            f"A  {memo_rel}" in status_output
            or f"A  tasks/memos/{filename}" in status_output
        )
        untracked_in_output = (
            f"?? {memo_rel}" in status_output
            or f"?? tasks/memos/{filename}" in status_output
            or "?? tasks/" in status_output
            or "?? tasks\\" in status_output
        )
        if staged_in_output:
            fail_test(
                name,
                f"receiver-side file should NOT be staged, git status output: {status_output!r}",
            )
            return
        if not untracked_in_output:
            fail_test(
                name,
                f"receiver-side file should be untracked, git status output: {status_output!r}",
            )
            return

        # Assert stdout contains PM-relay reminder.
        if "PM-relay is still the primary channel" not in result.stdout:
            fail_test(name, f"PM-relay reminder missing from stdout: {result.stdout!r}")
            return

        pass_test(name)


# ---------------------------------------------------------------------------
# Test 2 — central-only fallback (machine-local mock returns empty/error)
# ---------------------------------------------------------------------------

def test_central_only_fallback() -> None:
    name = "Test 2 — central-only fallback (unknown receiver)"
    import datetime

    with tempfile.TemporaryDirectory() as archive_tmpdir:
        # No MACHINE_LOCAL_IMPL set — unknown receiver falls back automatically.
        env = {
            **os.environ,
            "CLAUDE_HOME": archive_tmpdir,
        }

        result = _run_dispatcher(
            ["--to", "unknown-em", "--topic", "test", "--title", "Test"],
            env=env,
            stdin_text="Body.\n",
        )

        if result.returncode != 0:
            fail_test(name, f"dispatcher exited {result.returncode}: {result.stderr}")
            return

        today = datetime.date.today().isoformat()
        filename = f"{today}-test.md"

        # Assert NO receiver-side file (no receiver repo for unknown-em).
        # There's no tmpdir to check — just verify archive is written.
        archive_file = os.path.join(archive_tmpdir, "archive", "cross-repo", filename)
        if not os.path.isfile(archive_file):
            fail_test(name, f"archive copy not found at {archive_file}")
            return

        with open(archive_file) as f:
            archive_content = f.read()

        archive_fm = _parse_frontmatter(archive_content)
        if archive_fm.get("delivery_mode") != "central-only":
            fail_test(name, f"archive delivery_mode should be 'central-only', got: {archive_fm.get('delivery_mode')}")
            return

        # Assert stdout contains "no dirty-file backstop" warning.
        if "dirty-file backstop" not in result.stdout and "dirty-file backstop" not in result.stderr:
            fail_test(name, f"dirty-file backstop warning missing. stdout: {result.stdout!r} stderr: {result.stderr!r}")
            return

        pass_test(name)


# ---------------------------------------------------------------------------
# Test 3 — --self-receipt mode
# ---------------------------------------------------------------------------

def test_self_receipt() -> None:
    name = "Test 3 — --self-receipt mode"
    import datetime

    with tempfile.TemporaryDirectory() as receiver_tmpdir, \
         tempfile.TemporaryDirectory() as archive_tmpdir:

        mock_impl = _make_mock_machine_local(receiver_tmpdir, receiver_tmpdir)

        env = {
            **os.environ,
            "MACHINE_LOCAL_IMPL": mock_impl,
            "CLAUDE_HOME": archive_tmpdir,
        }

        result = _run_dispatcher(
            [
                "--to", "project-rag-em",
                "--topic", "test",
                "--title", "Test",
                "--self-receipt",
                "--decision", "accepted",
            ],
            env=env,
            stdin_text="Body.\n",
        )

        if result.returncode != 0:
            fail_test(name, f"dispatcher exited {result.returncode}: {result.stderr}")
            return

        today = datetime.date.today().isoformat()
        filename = f"{today}-test.md"
        archive_file = os.path.join(archive_tmpdir, "archive", "cross-repo", filename)

        if not os.path.isfile(archive_file):
            fail_test(name, f"archive copy not found at {archive_file}")
            return

        with open(archive_file) as f:
            archive_content = f.read()

        archive_fm = _parse_frontmatter(archive_content)

        if archive_fm.get("status") != "action_taken":
            fail_test(name, f"archive status should be 'action_taken', got: {archive_fm.get('status')}")
            return
        if archive_fm.get("decision") != "accepted":
            fail_test(name, f"archive decision should be 'accepted', got: {archive_fm.get('decision')}")
            return
        if not archive_fm.get("action_taken_at"):
            fail_test(name, "archive action_taken_at should be populated")
            return

        # Assert PM-relay reminder is NOT in stdout.
        if "PM-relay is still the primary channel" in result.stdout:
            fail_test(name, "PM-relay reminder should NOT appear in --self-receipt stdout")
            return

        pass_test(name)


# ---------------------------------------------------------------------------
# Test 4 — --self-receipt without --decision exits non-zero
# ---------------------------------------------------------------------------

def test_self_receipt_requires_decision() -> None:
    name = "Test 4 — --self-receipt without --decision exits non-zero"

    with tempfile.TemporaryDirectory() as archive_tmpdir:
        env = {
            **os.environ,
            "CLAUDE_HOME": archive_tmpdir,
        }

        result = _run_dispatcher(
            [
                "--to", "project-rag-em",
                "--topic", "test",
                "--title", "Test",
                "--self-receipt",
                # --decision intentionally omitted
            ],
            env=env,
            stdin_text="Body.\n",
        )

        if result.returncode == 0:
            fail_test(name, "dispatcher should exit non-zero when --self-receipt is set without --decision")
            return

        # Assert stderr contains a clear error about --decision being required.
        if "--decision" not in result.stderr and "decision" not in result.stderr.lower():
            fail_test(name, f"error message about missing --decision not found in stderr: {result.stderr!r}")
            return

        pass_test(name)


# ---------------------------------------------------------------------------
# Test 5 — path-traversal --topic is rejected (F2 regression)
# ---------------------------------------------------------------------------

def test_topic_path_traversal_rejected() -> None:
    name = "topic_path_traversal_rejected"
    with tempfile.TemporaryDirectory() as archive_tmpdir:
        env = {**os.environ, "CLAUDE_HOME": archive_tmpdir}
        for bad_topic in ("../../etc/passwd", "foo/bar", "..\\windows\\evil", "ABC", ""):
            result = _run_dispatcher(
                ["--to", "project-rag-em", "--topic", bad_topic, "--title", "T"],
                env=env,
                stdin_text="Body.\n",
            )
            if result.returncode == 0:
                fail_test(name, f"dispatcher should reject --topic {bad_topic!r}; exited 0")
                return
        pass_test(name)


# ---------------------------------------------------------------------------
# Test 6 — --decision superseded is accepted (F1 regression)
# ---------------------------------------------------------------------------

def test_decision_superseded_accepted() -> None:
    name = "decision_superseded_accepted"
    with tempfile.TemporaryDirectory() as archive_tmpdir:
        env = {**os.environ, "CLAUDE_HOME": archive_tmpdir}
        result = _run_dispatcher(
            ["--to", "project-rag-em", "--topic", "test-superseded",
             "--title", "T", "--self-receipt", "--decision", "superseded",
             "--delivery-mode", "central-only"],
            env=env,
            stdin_text="Body.\n",
        )
        if result.returncode != 0:
            fail_test(name, f"dispatcher should accept --decision superseded; exit {result.returncode}, stderr: {result.stderr!r}")
            return
        # Confirm archive frontmatter carries decision: superseded.
        today = subprocess.run([_python(), "-c", "from datetime import date; print(date.today().isoformat())"], capture_output=True, text=True, check=True).stdout.strip()
        archive_file = os.path.join(archive_tmpdir, "archive", "cross-repo", f"{today}-test-superseded.md")
        with open(archive_file) as f:
            fm = _parse_frontmatter(f.read())
        if fm.get("decision") != "superseded":
            fail_test(name, f"decision field should be 'superseded', got: {fm.get('decision')!r}")
            return
        pass_test(name)


# ---------------------------------------------------------------------------
# Test 7 — title with YAML-special chars round-trips through parser (F3 regression)
# ---------------------------------------------------------------------------

def test_title_yaml_special_chars() -> None:
    name = "title_yaml_special_chars"
    with tempfile.TemporaryDirectory() as archive_tmpdir:
        env = {**os.environ, "CLAUDE_HOME": archive_tmpdir}
        nasty_title = 'Fix: gate-check failures — see #42 [urgent]'
        result = _run_dispatcher(
            ["--to", "project-rag-em", "--topic", "test-yaml",
             "--title", nasty_title, "--delivery-mode", "central-only"],
            env=env,
            stdin_text="Body.\n",
        )
        if result.returncode != 0:
            fail_test(name, f"dispatcher should accept title with special chars; exit {result.returncode}")
            return
        today = subprocess.run([_python(), "-c", "from datetime import date; print(date.today().isoformat())"], capture_output=True, text=True, check=True).stdout.strip()
        archive_file = os.path.join(archive_tmpdir, "archive", "cross-repo", f"{today}-test-yaml.md")
        with open(archive_file) as f:
            fm = _parse_frontmatter(f.read())
        if fm.get("title") != nasty_title:
            fail_test(name, f"title should round-trip exactly. Expected: {nasty_title!r}, got: {fm.get('title')!r}")
            return
        pass_test(name)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main() -> int:
    print(f"Running cross-repo-memo smoke tests...")
    print(f"Script: {_script_path()}")
    print()

    tests = [
        test_receiver_repo_delivery,
        test_central_only_fallback,
        test_self_receipt,
        test_self_receipt_requires_decision,
        test_topic_path_traversal_rejected,
        test_decision_superseded_accepted,
        test_title_yaml_special_chars,
    ]

    for test_fn in tests:
        try:
            test_fn()
        except Exception as exc:
            fail_test(test_fn.__name__, f"unexpected exception: {exc}")

    print()
    print(f"Results: {TESTS_PASSED} passed, {TESTS_FAILED} failed out of {len(tests)} tests")
    if FAILURES:
        print("Failures:")
        for f in FAILURES:
            print(f"  {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
