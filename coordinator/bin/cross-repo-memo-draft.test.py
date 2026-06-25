#!/bin/sh
''''exec "$(command -v python3 || command -v python || command -v py)" "$0" "$@" #'''
from __future__ import annotations
"""
cross-repo-memo-draft.test.py — tests for the draft lifecycle subcommands (C1 + C2).

Spec backlink: docs/plans/2026-06-15-cross-repo-memo-draft-lifecycle.md § C1, § C2

Purpose: Verify the draft verb and subcommand scaffolding:
C1 tests:
  - Test 1: draft creates state/memo-outbox/<topic>.md with valid frontmatter
  - Test 2: draft on existing topic exits 2 with collision hint (AC11)
  - Test 3: send <missing-topic> exits non-zero with hint to list (AC3 partial)

C2 tests:
  - Test 4: send consumes outbox (AC2) — verifies outbox removed + receiver file lands
  - Test 5: send missing topic hints list (AC3 full) — verifies 'list' hint in error output
  - Test 6: send malformed outbox leaves in place (AC12) — exit 2, outbox untouched
  - Test 7: send receiver unresolvable leaves in place — exit 1, outbox untouched

Fixture shape mirrors cross-repo-memo.test.py:
  - CLAUDE_HOME env var for isolation
  - MACHINE_LOCAL_IMPL env var for mock machine-local
  - _run_dispatcher / _load_dispatcher_module helpers (verbatim from sibling)
  - _parse_frontmatter helper (verbatim from sibling)

Run with: python bin/cross-repo-memo-draft.test.py
"""

import datetime
import os
import subprocess
import sys
import tempfile
import textwrap

# ---------------------------------------------------------------------------
# Test infrastructure (mirrors cross-repo-memo.test.py fixtures)
# ---------------------------------------------------------------------------

TESTS_PASSED = 0
TESTS_FAILED = 0
FAILURES: list[str] = []


def _script_path() -> str:
    """Return the absolute path to cross-repo-memo."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "cross-repo-memo")


def _load_dispatcher_module():
    """Import the extensionless cross-repo-memo script as a module.

    The script has no .py extension and is not directly executable on Windows,
    but it is valid Python — importlib loads it by path. Loaded under a name
    other than __main__ so the `if __name__ == "__main__"` guard does not fire.
    """
    import importlib.util
    from importlib.machinery import SourceFileLoader

    loader = SourceFileLoader("cross_repo_memo", _script_path())
    spec = importlib.util.spec_from_loader("cross_repo_memo", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def _python() -> str:
    """Return the Python interpreter. Uses sys.executable — zero-probe, Windows-safe."""
    return sys.executable


def _run_dispatcher(args: list[str], env: dict[str, str], stdin_text: str = "") -> subprocess.CompletedProcess:
    """Invoke the dispatcher CLI as a subprocess with the given environment."""
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
    Quoted-string aware: handles titles/fields containing ':'.
    Mirrors the implementation in cross-repo-memo.test.py.
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
            key, _, rest = line.partition(":")
            v = rest.strip()
            if v.startswith('"'):
                raw_rest = line[len(key) + 1:].strip()
                if raw_rest.startswith('"'):
                    i = 1
                    chars = []
                    while i < len(raw_rest):
                        c = raw_rest[i]
                        if c == '\\' and i + 1 < len(raw_rest):
                            nc = raw_rest[i + 1]
                            if nc == '"':
                                chars.append('"')
                            elif nc == '\\':
                                chars.append('\\')
                            elif nc == 'n':
                                chars.append('\n')
                            elif nc == 'r':
                                # Review: code-reviewer — _yaml_quote emits \r but parser did not handle it
                                chars.append('\r')
                            elif nc == 't':
                                chars.append('\t')
                            else:
                                chars.append(nc)
                            i += 2
                            continue
                        if c == '"':
                            break
                        chars.append(c)
                        i += 1
                    v = ''.join(chars)
                else:
                    v = v.replace('\\"', '"').replace("\\\\", "\\")
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
    Mirrors the sibling test file shape.
    """
    stub_path = os.path.join(tmpdir, "_mock_machine_local.py")
    if return_value is None:
        script = textwrap.dedent("""\
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


def _make_git_repo(parent_dir: str, name: str = "sender_repo") -> str:
    """Create a minimal git repo in parent_dir and return its path.

    The draft subcommand uses _current_repo_root() (git rev-parse) to find
    the sender repo. Tests that invoke draft as a subprocess must run with
    cwd set to a git repo, so draft knows where to write state/memo-outbox/.
    """
    repo_dir = os.path.join(parent_dir, name)
    os.makedirs(repo_dir)
    subprocess.run(["git", "init", repo_dir], capture_output=True, check=False)
    subprocess.run(
        ["git", "-C", repo_dir, "config", "user.email", "test@test.com"],
        capture_output=True, check=False,
    )
    subprocess.run(
        ["git", "-C", repo_dir, "config", "user.name", "Test"],
        capture_output=True, check=False,
    )
    return repo_dir


def _run_dispatcher_in_repo(
    repo_dir: str,
    args: list[str],
    env: dict[str, str],
    stdin_text: str = "",
) -> subprocess.CompletedProcess:
    """Invoke the dispatcher CLI with cwd=repo_dir so git rev-parse works."""
    return subprocess.run(
        [_python(), _script_path()] + args,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        input=stdin_text,
        cwd=repo_dir,
    )


# ---------------------------------------------------------------------------
# Test 1 — draft creates state/memo-outbox/<topic>.md with valid frontmatter
# Realises AC1
# ---------------------------------------------------------------------------

def test_draft_creates_outbox_file() -> None:
    """Draft writes state/memo-outbox/<topic>.md in sender repo.

    Asserts:
      - exit 0
      - file exists at state/memo-outbox/<topic>.md
      - frontmatter fields: status=draft, from=<sender>, to=<receiver>,
        title, summary are present
      - stdout contains the absolute outbox path
    """
    name = "test_draft_creates_outbox_file"

    with tempfile.TemporaryDirectory() as tmpdir:
        sender_repo = _make_git_repo(tmpdir, "sender_repo")
        claude_home = os.path.join(tmpdir, "claude_home")
        os.makedirs(claude_home, exist_ok=True)

        # machine-local stub — sender just needs git identity, no receiver needed
        mock_impl = _make_mock_machine_local(tmpdir, None)

        env = {
            "MACHINE_LOCAL_IMPL": mock_impl,
            "CLAUDE_HOME": claude_home,
        }

        result = _run_dispatcher_in_repo(
            sender_repo,
            [
                "draft", "test-c1-draft",
                "--to", "claude-central-em",
                "--title", "C1 draft test memo",
                "--summary", "A test summary for the draft command",
            ],
            env=env,
        )

        if result.returncode != 0:
            fail_test(name, f"draft exited {result.returncode}: stdout={result.stdout!r} stderr={result.stderr!r}")
            return

        # Assert outbox file exists
        outbox_path = os.path.join(sender_repo, "state", "memo-outbox", "test-c1-draft.md")
        if not os.path.isfile(outbox_path):
            fail_test(name, f"outbox file not found at {outbox_path}. stdout: {result.stdout!r}")
            return

        # Parse and assert frontmatter
        with open(outbox_path, encoding="utf-8") as f:
            content = f.read()

        fm = _parse_frontmatter(content)

        if fm.get("status") != "draft":
            fail_test(name, f"status should be 'draft', got: {fm.get('status')!r}. frontmatter fields: {fm}")
            return
        if not fm.get("to"):
            fail_test(name, f"'to' field missing from frontmatter. fields: {fm}")
            return
        if fm.get("to") != "claude-central-em":
            fail_test(name, f"'to' should be 'claude-central-em', got: {fm.get('to')!r}")
            return
        if fm.get("title") != "C1 draft test memo":
            fail_test(name, f"'title' should be 'C1 draft test memo', got: {fm.get('title')!r}")
            return
        if not fm.get("from"):
            fail_test(name, f"'from' field missing (sender identity). fields: {fm}")
            return
        if not fm.get("summary"):
            fail_test(name, f"'summary' field missing. fields: {fm}")
            return

        # Assert body placeholder present
        if "cross-repo-memo send" not in content:
            fail_test(name, f"body placeholder missing from outbox file. content: {content!r}")
            return

        # Assert stdout contains the absolute path
        if not result.stdout.strip():
            fail_test(name, "stdout should contain the outbox path, got empty stdout")
            return
        stdout_path = result.stdout.strip()
        if not os.path.isabs(stdout_path):
            fail_test(name, f"stdout should contain absolute path, got: {stdout_path!r}")
            return

        pass_test(name)


# ---------------------------------------------------------------------------
# Test 2 — draft collision exits 2 with hint to compose/discard
# Realises AC11
# ---------------------------------------------------------------------------

def test_draft_collision_exits_2() -> None:
    """Second draft of same topic exits 2 with collision hint; original file unmodified.

    Asserts:
      - first draft: exit 0, file created
      - second draft (same topic): exit 2
      - hint message mentions 'compose' and 'discard'
      - original file is unmodified (content unchanged)
    """
    name = "test_draft_collision_exits_2"

    with tempfile.TemporaryDirectory() as tmpdir:
        sender_repo = _make_git_repo(tmpdir, "sender_repo")
        claude_home = os.path.join(tmpdir, "claude_home")
        os.makedirs(claude_home, exist_ok=True)

        mock_impl = _make_mock_machine_local(tmpdir, None)
        env = {
            "MACHINE_LOCAL_IMPL": mock_impl,
            "CLAUDE_HOME": claude_home,
        }

        # First draft — should succeed
        result1 = _run_dispatcher_in_repo(
            sender_repo,
            [
                "draft", "collision-topic",
                "--to", "claude-central-em",
                "--title", "Original memo title",
            ],
            env=env,
        )
        if result1.returncode != 0:
            fail_test(name, f"first draft failed: exit {result1.returncode}, stderr: {result1.stderr!r}")
            return

        outbox_path = os.path.join(sender_repo, "state", "memo-outbox", "collision-topic.md")
        if not os.path.isfile(outbox_path):
            fail_test(name, f"outbox file not found after first draft: {outbox_path}")
            return

        # Capture original content
        with open(outbox_path, encoding="utf-8") as f:
            original_content = f.read()

        # Second draft — same topic, should exit 2
        result2 = _run_dispatcher_in_repo(
            sender_repo,
            [
                "draft", "collision-topic",
                "--to", "claude-central-em",
                "--title", "Different title — should not overwrite",
            ],
            env=env,
        )

        if result2.returncode != 2:
            fail_test(name, f"second draft should exit 2 (collision), got: {result2.returncode}. stderr: {result2.stderr!r}")
            return

        # Assert hint message contains compose and discard
        combined = result2.stdout + result2.stderr
        if "compose" not in combined.lower():
            fail_test(name, f"collision hint should mention 'compose'. output: {combined!r}")
            return
        if "discard" not in combined.lower():
            fail_test(name, f"collision hint should mention 'discard'. output: {combined!r}")
            return

        # Assert original file is unmodified
        with open(outbox_path, encoding="utf-8") as f:
            after_content = f.read()
        if after_content != original_content:
            fail_test(name, "original outbox file was modified by the colliding draft call")
            return

        pass_test(name)


# ---------------------------------------------------------------------------
# C2 helpers — make a git repo for the receiver side
# ---------------------------------------------------------------------------
# Review: code-reviewer — _make_receiver_git_repo was a duplicate of _make_git_repo;
# removed; call sites now use _make_git_repo(parent_dir, "receiver_repo") directly.


def _make_mock_machine_local_with_receiver(tmpdir: str, receiver_path: str) -> str:
    """Create a stub machine-local that resolves repos.* keys to receiver_path.

    The send subcommand calls _machine_local_get("repos.<name>") to resolve the
    receiver path. This stub returns receiver_path for any repos.* key lookup,
    and also returns the list of repos.* keys so _sender_em_id can identify the sender.
    """
    stub_path = os.path.join(tmpdir, "_mock_machine_local_receiver.py")
    escaped = receiver_path.replace("\\", "\\\\")
    script = textwrap.dedent(f"""\
        #!/usr/bin/env python3
        import sys
        args = sys.argv[1:]
        if args and args[0] == "get":
            key = args[1] if len(args) > 1 else ""
            if key.startswith("repos.") and key != "repos.claude_unreal_holodeck":
                print("{escaped}")
                sys.exit(0)
            # claude-central-em doesn't go through repos.*, fall through
            print("machine-local: key not found", file=sys.stderr)
            sys.exit(1)
        elif args and args[0] == "keys":
            print("repos.test_receiver")
            sys.exit(0)
        else:
            print("machine-local: key not found", file=sys.stderr)
            sys.exit(1)
    """)
    with open(stub_path, "w") as f:
        f.write(script)
    return stub_path


def _make_outbox_file(sender_repo: str, topic: str, content: str) -> str:
    """Write a pre-formed outbox file directly (bypasses the draft subcommand).

    Used in C2 tests to stage outbox files with specific content for send testing.
    Returns the absolute path of the written outbox file.
    """
    outbox_dir = os.path.join(sender_repo, "state", "memo-outbox")
    os.makedirs(outbox_dir, exist_ok=True)
    path = os.path.join(outbox_dir, f"{topic}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def _valid_outbox_content(topic: str, to: str, title: str = "Test memo title") -> str:
    """Generate a valid outbox file content (status: draft) for send tests.

    Note: 'from:' is overwritten at send time by _sender_em_id() — see _compose_frontmatter:602.
    Tests on receiver-side from: must use the dynamic value, not 'test-sender-em'.
    """
    today = datetime.date.today().isoformat()
    return textwrap.dedent(f"""\
        ---
        title: "{title}"
        from: "test-sender-em"
        to: "{to}"
        created: "{today}"
        status: draft
        delivery_mode: receiver-repo
        summary: "A test summary"
        ---

        This is the test memo body for {topic}.
    """)


# ---------------------------------------------------------------------------
# Test 4 — send consumes outbox (AC2)
# ---------------------------------------------------------------------------

def test_send_consumes_outbox() -> None:
    """send <topic> dispatches outbox draft → outbox file removed, receiver file lands.

    Asserts:
      (a) outbox file is removed after successful send
      (b) receiver-side memo lands at <receiver>/cross-repo/inbox/<date>-<topic>.md
      (c) receiver-side memo has status=open (promoted from draft)
      (d) receiver-side memo has created= today (applied at send time)

    Realises AC2.
    """
    name = "test_send_consumes_outbox"

    with tempfile.TemporaryDirectory() as tmpdir:
        sender_repo = _make_git_repo(tmpdir, "sender_repo")
        receiver_repo = _make_git_repo(tmpdir, "receiver_repo")
        claude_home = os.path.join(tmpdir, "claude_home")
        os.makedirs(claude_home, exist_ok=True)

        # machine-local stub: resolves repos.test_receiver → receiver_repo
        # We send to "test-receiver-em" which maps to repos.test_receiver
        mock_impl = _make_mock_machine_local_with_receiver(tmpdir, receiver_repo)

        env = {
            "MACHINE_LOCAL_IMPL": mock_impl,
            "CLAUDE_HOME": claude_home,
        }

        # Stage a valid outbox draft (bypass draft subcommand — we just need the file)
        topic = "c2-send-test"
        to = "test-receiver-em"
        outbox_path = _make_outbox_file(
            sender_repo, topic,
            _valid_outbox_content(topic, to),
        )

        # Review: code-reviewer — use fail_test instead of bare assert for consistent error reporting
        if not os.path.isfile(outbox_path):
            fail_test(name, f"Outbox setup failed — file not written: {outbox_path}")
            return

        # Run send
        result = _run_dispatcher_in_repo(
            sender_repo,
            ["send", topic],
            env=env,
        )

        if result.returncode != 0:
            fail_test(name, (
                f"send exited {result.returncode}: "
                f"stdout={result.stdout!r} stderr={result.stderr!r}"
            ))
            return

        # (a) outbox file removed
        if os.path.isfile(outbox_path):
            fail_test(name, f"outbox file should be removed after successful send, still exists: {outbox_path}")
            return

        # (b) receiver-side file exists
        today = datetime.date.today().isoformat()
        receiver_inbox = os.path.join(receiver_repo, "cross-repo", "inbox", f"{today}-{topic}.md")
        if not os.path.isfile(receiver_inbox):
            fail_test(name, (
                f"receiver-side file not found at {receiver_inbox}. "
                f"Receiver dir contents: {os.listdir(receiver_repo) if os.path.isdir(receiver_repo) else '(repo not found)'}"
            ))
            return

        with open(receiver_inbox, encoding="utf-8") as f:
            receiver_content = f.read()

        fm = _parse_frontmatter(receiver_content)

        # (c) status promoted to open
        if fm.get("status") != "open":
            fail_test(name, f"receiver memo status should be 'open', got: {fm.get('status')!r}. frontmatter: {fm}")
            return

        # (d) created is today
        if fm.get("created") != today:
            fail_test(name, f"receiver memo 'created' should be today {today!r}, got: {fm.get('created')!r}")
            return

        pass_test(name)


# ---------------------------------------------------------------------------
# Test 5 — send missing topic hints list (AC3 full)
# ---------------------------------------------------------------------------

def test_send_missing_topic_hint_list() -> None:
    """send <missing-topic> exits non-zero AND output mentions 'list'.

    The C1 partial test (test_send_missing_topic_no_draft) only asserted non-zero.
    This C2 test strengthens the assertion to require a 'list' hint in the output.
    Realises AC3 fully.
    """
    name = "test_send_missing_topic_hint_list"

    with tempfile.TemporaryDirectory() as tmpdir:
        sender_repo = _make_git_repo(tmpdir, "sender_repo")
        claude_home = os.path.join(tmpdir, "claude_home")
        os.makedirs(claude_home, exist_ok=True)

        mock_impl = _make_mock_machine_local(tmpdir, None)
        env = {
            "MACHINE_LOCAL_IMPL": mock_impl,
            "CLAUDE_HOME": claude_home,
        }

        result = _run_dispatcher_in_repo(
            sender_repo,
            ["send", "nonexistent-topic-xyz"],
            env=env,
        )

        if result.returncode == 0:
            fail_test(name, f"send of missing topic should exit non-zero, got 0. stdout: {result.stdout!r}")
            return

        combined = result.stdout + result.stderr
        if "list" not in combined.lower():
            fail_test(name, f"missing-topic send should hint about 'list', output: {combined!r}")
            return

        # Also confirm no filesystem mutation occurred
        outbox_dir = os.path.join(sender_repo, "state", "memo-outbox")
        if os.path.isdir(outbox_dir):
            files = os.listdir(outbox_dir)
            if files:
                fail_test(name, f"send of missing topic should not create files, found: {files}")
                return

        pass_test(name)


# ---------------------------------------------------------------------------
# Test 6 — send malformed outbox leaves in place (AC12)
# ---------------------------------------------------------------------------

def test_send_malformed_outbox_leaves_in_place() -> None:
    """send on outbox with broken frontmatter exits 2, outbox file still exists.

    Fixture: outbox with missing required 'to:' field.
    Asserts: exit 2, outbox file untouched.
    Realises AC12.
    """
    name = "test_send_malformed_outbox_leaves_in_place"

    with tempfile.TemporaryDirectory() as tmpdir:
        sender_repo = _make_git_repo(tmpdir, "sender_repo")
        claude_home = os.path.join(tmpdir, "claude_home")
        os.makedirs(claude_home, exist_ok=True)

        mock_impl = _make_mock_machine_local(tmpdir, None)
        env = {
            "MACHINE_LOCAL_IMPL": mock_impl,
            "CLAUDE_HOME": claude_home,
        }

        # Outbox with missing 'to:' field (required) → validation failure
        today = datetime.date.today().isoformat()
        malformed_content = textwrap.dedent(f"""\
            ---
            title: "A malformed draft"
            from: "test-sender-em"
            created: "{today}"
            status: draft
            delivery_mode: receiver-repo
            summary: "Missing to: field"
            ---

            Body of the malformed draft.
        """)

        topic = "malformed-draft"
        outbox_path = _make_outbox_file(sender_repo, topic, malformed_content)

        result = _run_dispatcher_in_repo(
            sender_repo,
            ["send", topic],
            env=env,
        )

        if result.returncode != 2:
            fail_test(name, (
                f"send with malformed outbox should exit 2, got {result.returncode}. "
                f"stdout={result.stdout!r} stderr={result.stderr!r}"
            ))
            return

        # Outbox file must still exist
        if not os.path.isfile(outbox_path):
            fail_test(name, f"outbox file should remain in place after validation failure, was removed: {outbox_path}")
            return

        # Output should contain validation error hint
        combined = result.stdout + result.stderr
        if "compose" not in combined.lower() and "validation" not in combined.lower():
            fail_test(name, f"validation failure output should hint at compose or mention validation. output: {combined!r}")
            return

        pass_test(name)


# ---------------------------------------------------------------------------
# Test 7 — send receiver unresolvable leaves in place
# ---------------------------------------------------------------------------

def test_send_receiver_unresolvable_leaves_in_place() -> None:
    """send with 'to: nonexistent-em' in outbox exits 1, outbox file still exists.

    Reinforces the failure-shape table: receiver-resolution failure →
    leave outbox in place, exit 1.
    """
    name = "test_send_receiver_unresolvable_leaves_in_place"

    with tempfile.TemporaryDirectory() as tmpdir:
        sender_repo = _make_git_repo(tmpdir, "sender_repo")
        claude_home = os.path.join(tmpdir, "claude_home")
        os.makedirs(claude_home, exist_ok=True)

        # machine-local stub: always returns None (no repos found) → receiver unresolvable
        mock_impl = _make_mock_machine_local(tmpdir, None)
        env = {
            "MACHINE_LOCAL_IMPL": mock_impl,
            "CLAUDE_HOME": claude_home,
        }

        # Valid frontmatter except 'to' is an EM that doesn't exist in the registry
        today = datetime.date.today().isoformat()
        content = textwrap.dedent(f"""\
            ---
            title: "Receiver unresolvable test"
            from: "test-sender-em"
            to: "nonexistent-em"
            created: "{today}"
            status: draft
            delivery_mode: receiver-repo
            summary: "Test memo"
            ---

            Body content.
        """)

        topic = "receiver-unresolvable-test"
        outbox_path = _make_outbox_file(sender_repo, topic, content)

        result = _run_dispatcher_in_repo(
            sender_repo,
            ["send", topic],
            env=env,
        )

        if result.returncode != 1:
            fail_test(name, (
                f"send with unresolvable receiver should exit 1, got {result.returncode}. "
                f"stdout={result.stdout!r} stderr={result.stderr!r}"
            ))
            return

        # Outbox file must still exist
        if not os.path.isfile(outbox_path):
            fail_test(name, f"outbox file should remain after receiver-resolution failure, was removed: {outbox_path}")
            return

        pass_test(name)


# ---------------------------------------------------------------------------
# Test 7b — send preserves supersedes field from outbox
# Realises F1 fix: supersedes was silently dropped at send time
# ---------------------------------------------------------------------------

def test_send_preserves_supersedes() -> None:
    """send <topic> carries supersedes: field from outbox draft to receiver memo.

    Fixture: outbox file with a manually-injected supersedes: field.
    Asserts: receiver-side memo frontmatter contains supersedes with the same value.
    Realises correctness fix for the supersedes silent-drop bug (code-reviewer F1).
    """
    name = "test_send_preserves_supersedes"

    with tempfile.TemporaryDirectory() as tmpdir:
        sender_repo = _make_git_repo(tmpdir, "sender_repo")
        receiver_repo = _make_git_repo(tmpdir, "receiver_repo")
        claude_home = os.path.join(tmpdir, "claude_home")
        os.makedirs(claude_home, exist_ok=True)

        mock_impl = _make_mock_machine_local_with_receiver(tmpdir, receiver_repo)
        env = {
            "MACHINE_LOCAL_IMPL": mock_impl,
            "CLAUDE_HOME": claude_home,
        }

        topic = "supersedes-test"
        to = "test-receiver-em"
        today = datetime.date.today().isoformat()

        # Build outbox content with supersedes: field manually injected
        outbox_content = textwrap.dedent(f"""\
            ---
            title: "Supersedes test memo"
            from: "test-sender-em"
            to: "{to}"
            created: "{today}"
            status: draft
            delivery_mode: receiver-repo
            summary: "Testing supersedes field propagation"
            supersedes: "2026-06-14-old-topic"
            ---

            Body of the supersedes test memo.
        """)

        outbox_path = _make_outbox_file(sender_repo, topic, outbox_content)

        if not os.path.isfile(outbox_path):
            fail_test(name, f"Outbox setup failed — file not written: {outbox_path}")
            return

        result = _run_dispatcher_in_repo(
            sender_repo,
            ["send", topic],
            env=env,
        )

        if result.returncode != 0:
            fail_test(name, (
                f"send exited {result.returncode}: "
                f"stdout={result.stdout!r} stderr={result.stderr!r}"
            ))
            return

        # Locate receiver-side memo
        receiver_inbox = os.path.join(receiver_repo, "cross-repo", "inbox", f"{today}-{topic}.md")
        if not os.path.isfile(receiver_inbox):
            fail_test(name, f"receiver-side file not found at {receiver_inbox}")
            return

        with open(receiver_inbox, encoding="utf-8") as f:
            receiver_content = f.read()

        fm = _parse_frontmatter(receiver_content)

        if fm.get("supersedes") != "2026-06-14-old-topic":
            fail_test(name, (
                f"receiver memo supersedes should be '2026-06-14-old-topic', "
                f"got: {fm.get('supersedes')!r}. frontmatter: {fm}"
            ))
            return

        pass_test(name)


# ---------------------------------------------------------------------------
# C3 tests — list / discard / compose subcommands
# ---------------------------------------------------------------------------

def _backdate_file(path: str, seconds_ago: float) -> None:
    """Set the mtime of a file to `seconds_ago` seconds in the past."""
    import time
    now = time.time()
    past = now - seconds_ago
    os.utime(path, (past, past))


# ---------------------------------------------------------------------------
# Test 8 — list enumerates drafts with age, marks stale (AC4)
# ---------------------------------------------------------------------------

def test_list_enumerates_with_age() -> None:
    """list shows both topics; backdated one carries [stale], fresh one does not.

    Fixture: 2 drafts in state/memo-outbox/. One has normal mtime (fresh),
    the other is backdated to >24h ago (stale).
    Asserts:
      - exit 0
      - both topics appear in output
      - backdated topic carries [stale]
      - fresh topic does NOT carry [stale]
    Realises AC4.
    """
    name = "test_list_enumerates_with_age"

    with tempfile.TemporaryDirectory() as tmpdir:
        sender_repo = _make_git_repo(tmpdir, "sender_repo")
        claude_home = os.path.join(tmpdir, "claude_home")
        os.makedirs(claude_home, exist_ok=True)

        mock_impl = _make_mock_machine_local(tmpdir, None)
        env = {
            "MACHINE_LOCAL_IMPL": mock_impl,
            "CLAUDE_HOME": claude_home,
        }

        # Create two outbox drafts directly (bypass the draft subcommand)
        today = datetime.date.today().isoformat()

        fresh_topic = "fresh-draft"
        stale_topic = "stale-draft"

        fresh_content = textwrap.dedent(f"""\
            ---
            title: "Fresh draft"
            from: "test-sender-em"
            to: "claude-central-em"
            created: "{today}"
            status: draft
            delivery_mode: receiver-repo
            summary: "A fresh draft"
            ---

            Fresh body.
        """)
        stale_content = textwrap.dedent(f"""\
            ---
            title: "Stale draft"
            from: "test-sender-em"
            to: "claude-central-em"
            created: "{today}"
            status: draft
            delivery_mode: receiver-repo
            summary: "A stale draft"
            ---

            Stale body.
        """)

        fresh_path = _make_outbox_file(sender_repo, fresh_topic, fresh_content)
        stale_path = _make_outbox_file(sender_repo, stale_topic, stale_content)

        # Backdate the stale file to 25 hours ago (>24h threshold)
        _backdate_file(stale_path, 25 * 3600)

        result = _run_dispatcher_in_repo(
            sender_repo,
            ["list"],
            env=env,
        )

        if result.returncode != 0:
            fail_test(name, f"list exited {result.returncode}: stdout={result.stdout!r} stderr={result.stderr!r}")
            return

        output = result.stdout
        if fresh_topic not in output:
            fail_test(name, f"fresh topic '{fresh_topic}' not in list output: {output!r}")
            return
        if stale_topic not in output:
            fail_test(name, f"stale topic '{stale_topic}' not in list output: {output!r}")
            return

        # Check [stale] appears and is associated with the stale topic
        lines = [l for l in output.splitlines() if l.strip()]
        stale_line = next((l for l in lines if stale_topic in l), None)
        fresh_line = next((l for l in lines if fresh_topic in l), None)

        if stale_line is None:
            fail_test(name, f"no output line found for stale topic. output: {output!r}")
            return
        if fresh_line is None:
            fail_test(name, f"no output line found for fresh topic. output: {output!r}")
            return
        if "[stale]" not in stale_line:
            fail_test(name, f"stale topic line should contain '[stale]'. line: {stale_line!r}")
            return
        if "[stale]" in fresh_line:
            fail_test(name, f"fresh topic line should NOT contain '[stale]'. line: {fresh_line!r}")
            return

        pass_test(name)


# ---------------------------------------------------------------------------
# Test 9 — list empty outbox prints "no drafts" (AC4)
# ---------------------------------------------------------------------------

def test_list_empty_prints_no_drafts() -> None:
    """list with empty outbox exits 0 and output contains 'no drafts'.

    Realises AC4 (empty outbox branch).
    """
    name = "test_list_empty_prints_no_drafts"

    with tempfile.TemporaryDirectory() as tmpdir:
        sender_repo = _make_git_repo(tmpdir, "sender_repo")
        claude_home = os.path.join(tmpdir, "claude_home")
        os.makedirs(claude_home, exist_ok=True)

        mock_impl = _make_mock_machine_local(tmpdir, None)
        env = {
            "MACHINE_LOCAL_IMPL": mock_impl,
            "CLAUDE_HOME": claude_home,
        }

        # Do NOT create any outbox files — empty outbox (dir may not even exist)

        result = _run_dispatcher_in_repo(
            sender_repo,
            ["list"],
            env=env,
        )

        if result.returncode != 0:
            fail_test(name, f"list empty should exit 0, got {result.returncode}: stderr={result.stderr!r}")
            return

        combined = result.stdout + result.stderr
        if "no drafts" not in combined.lower():
            fail_test(name, f"list empty should output 'no drafts'. output: {combined!r}")
            return

        pass_test(name)


# ---------------------------------------------------------------------------
# Test 10 — discard removes file (AC5)
# ---------------------------------------------------------------------------

def test_discard_removes_file() -> None:
    """discard <topic> removes the outbox file; exit 0.

    Realises AC5.
    """
    name = "test_discard_removes_file"

    with tempfile.TemporaryDirectory() as tmpdir:
        sender_repo = _make_git_repo(tmpdir, "sender_repo")
        claude_home = os.path.join(tmpdir, "claude_home")
        os.makedirs(claude_home, exist_ok=True)

        mock_impl = _make_mock_machine_local(tmpdir, None)
        env = {
            "MACHINE_LOCAL_IMPL": mock_impl,
            "CLAUDE_HOME": claude_home,
        }

        today = datetime.date.today().isoformat()
        topic = "discard-me"
        content = textwrap.dedent(f"""\
            ---
            title: "To be discarded"
            from: "test-sender-em"
            to: "claude-central-em"
            created: "{today}"
            status: draft
            delivery_mode: receiver-repo
            summary: "Will be discarded"
            ---

            Body.
        """)
        outbox_path = _make_outbox_file(sender_repo, topic, content)

        # Review: code-reviewer — use fail_test instead of bare assert for consistent error reporting
        if not os.path.isfile(outbox_path):
            fail_test(name, f"Test setup failed — file not written: {outbox_path}")
            return

        result = _run_dispatcher_in_repo(
            sender_repo,
            ["discard", topic],
            env=env,
        )

        if result.returncode != 0:
            fail_test(name, f"discard exited {result.returncode}: stdout={result.stdout!r} stderr={result.stderr!r}")
            return

        if os.path.isfile(outbox_path):
            fail_test(name, f"outbox file should be removed after discard, still exists: {outbox_path}")
            return

        pass_test(name)


# ---------------------------------------------------------------------------
# Test 11 — discard missing topic exits non-zero with list hint (AC5)
# ---------------------------------------------------------------------------

def test_discard_missing_topic() -> None:
    """discard <missing-topic> exits non-zero; hint mentions 'list'.

    Realises AC5 (error branch).
    """
    name = "test_discard_missing_topic"

    with tempfile.TemporaryDirectory() as tmpdir:
        sender_repo = _make_git_repo(tmpdir, "sender_repo")
        claude_home = os.path.join(tmpdir, "claude_home")
        os.makedirs(claude_home, exist_ok=True)

        mock_impl = _make_mock_machine_local(tmpdir, None)
        env = {
            "MACHINE_LOCAL_IMPL": mock_impl,
            "CLAUDE_HOME": claude_home,
        }

        result = _run_dispatcher_in_repo(
            sender_repo,
            ["discard", "no-such-topic-xyz"],
            env=env,
        )

        if result.returncode == 0:
            fail_test(name, f"discard of missing topic should exit non-zero, got 0. stdout: {result.stdout!r}")
            return

        combined = result.stdout + result.stderr
        if "list" not in combined.lower():
            fail_test(name, f"missing-topic discard should hint about 'list'. output: {combined!r}")
            return

        pass_test(name)


# ---------------------------------------------------------------------------
# Test 12 — compose prints absolute path by default (AC implied by C3)
# ---------------------------------------------------------------------------

def test_compose_prints_path_default() -> None:
    """compose <topic> prints the absolute outbox path; exits 0. No editor exec.

    The test runner does NOT have $EDITOR set (or it is cleared in env).
    Asserts: stdout is an absolute path, exit 0.
    CRITICAL: this test verifies the safe default — compose never execs an editor
    unconditionally (the F12 footgun the plan exists to prevent).
    """
    name = "test_compose_prints_path_default"

    with tempfile.TemporaryDirectory() as tmpdir:
        sender_repo = _make_git_repo(tmpdir, "sender_repo")
        claude_home = os.path.join(tmpdir, "claude_home")
        os.makedirs(claude_home, exist_ok=True)

        mock_impl = _make_mock_machine_local(tmpdir, None)
        env = {
            "MACHINE_LOCAL_IMPL": mock_impl,
            "CLAUDE_HOME": claude_home,
            # Explicitly clear EDITOR to cover the "no editor exec" assertion.
            # os.environ may have $EDITOR on the test runner — clear it explicitly.
        }
        # Pop EDITOR from the merged env (we pass env={**os.environ, **env_overrides})
        # The run helper merges with os.environ — ensure EDITOR is absent.
        env_with_no_editor = {**os.environ, **env}
        env_with_no_editor.pop("EDITOR", None)

        today = datetime.date.today().isoformat()
        topic = "compose-me"
        content = textwrap.dedent(f"""\
            ---
            title: "Composable draft"
            from: "test-sender-em"
            to: "claude-central-em"
            created: "{today}"
            status: draft
            delivery_mode: receiver-repo
            summary: "Will be composed"
            ---

            Body.
        """)
        _make_outbox_file(sender_repo, topic, content)

        result = subprocess.run(
            [_python(), _script_path(), "compose", topic],
            env=env_with_no_editor,
            capture_output=True,
            text=True,
            cwd=sender_repo,
        )

        if result.returncode != 0:
            fail_test(name, f"compose exited {result.returncode}: stdout={result.stdout!r} stderr={result.stderr!r}")
            return

        stdout_path = result.stdout.strip()
        if not stdout_path:
            fail_test(name, "compose should print the outbox path to stdout, got empty")
            return

        if not os.path.isabs(stdout_path):
            fail_test(name, f"compose should print absolute path, got: {stdout_path!r}")
            return

        # The path should point to the outbox file
        expected_outbox = os.path.join(sender_repo, "state", "memo-outbox", f"{topic}.md")
        if not os.path.samefile(stdout_path, expected_outbox):
            fail_test(name, f"compose path {stdout_path!r} does not match expected {expected_outbox!r}")
            return

        pass_test(name)


# ---------------------------------------------------------------------------
# Test 13 — compose missing topic exits non-zero with list hint
# ---------------------------------------------------------------------------

def test_compose_missing_topic() -> None:
    """compose <missing-topic> exits non-zero; hint mentions 'list'."""
    name = "test_compose_missing_topic"

    with tempfile.TemporaryDirectory() as tmpdir:
        sender_repo = _make_git_repo(tmpdir, "sender_repo")
        claude_home = os.path.join(tmpdir, "claude_home")
        os.makedirs(claude_home, exist_ok=True)

        mock_impl = _make_mock_machine_local(tmpdir, None)
        env = {
            "MACHINE_LOCAL_IMPL": mock_impl,
            "CLAUDE_HOME": claude_home,
        }

        result = _run_dispatcher_in_repo(
            sender_repo,
            ["compose", "no-such-topic-xyz"],
            env=env,
        )

        if result.returncode == 0:
            fail_test(name, f"compose of missing topic should exit non-zero, got 0. stdout: {result.stdout!r}")
            return

        combined = result.stdout + result.stderr
        if "list" not in combined.lower():
            fail_test(name, f"missing-topic compose should hint about 'list'. output: {combined!r}")
            return

        pass_test(name)


# ---------------------------------------------------------------------------
# Test 14 — compose --open without $EDITOR prints path + warning (AC implied by C3)
# ---------------------------------------------------------------------------

def test_compose_open_without_editor() -> None:
    """compose <topic> --open with empty $EDITOR exits 0; stdout includes path + warning.

    NOTE: Testing --open WITH $EDITOR set would actually exec the editor — skip that
    case in automated tests. The --open exec path is exercised by human use, not by
    the test suite.
    """
    name = "test_compose_open_without_editor"

    with tempfile.TemporaryDirectory() as tmpdir:
        sender_repo = _make_git_repo(tmpdir, "sender_repo")
        claude_home = os.path.join(tmpdir, "claude_home")
        os.makedirs(claude_home, exist_ok=True)

        mock_impl = _make_mock_machine_local(tmpdir, None)

        today = datetime.date.today().isoformat()
        topic = "compose-open-test"
        content = textwrap.dedent(f"""\
            ---
            title: "Open test draft"
            from: "test-sender-em"
            to: "claude-central-em"
            created: "{today}"
            status: draft
            delivery_mode: receiver-repo
            summary: "Open test"
            ---

            Body.
        """)
        _make_outbox_file(sender_repo, topic, content)

        # Set EDITOR to empty string — --open without a real editor
        env_with_no_editor = {**os.environ}
        env_with_no_editor["MACHINE_LOCAL_IMPL"] = mock_impl
        env_with_no_editor["CLAUDE_HOME"] = claude_home
        env_with_no_editor["EDITOR"] = ""  # explicitly empty

        result = subprocess.run(
            [_python(), _script_path(), "compose", topic, "--open"],
            env=env_with_no_editor,
            capture_output=True,
            text=True,
            cwd=sender_repo,
        )

        if result.returncode != 0:
            fail_test(name, f"compose --open without EDITOR should exit 0, got {result.returncode}: {result.stderr!r}")
            return

        combined = result.stdout + result.stderr
        # Should contain the path
        expected_outbox = os.path.join(sender_repo, "state", "memo-outbox", f"{topic}.md")
        # Check that SOME path appears in output that points to the right file
        if topic not in combined:
            fail_test(name, f"compose --open should include topic in output. output: {combined!r}")
            return

        # Should contain a warning about $EDITOR being unset
        if "editor" not in combined.lower() and "$editor" not in combined.lower():
            fail_test(name, f"compose --open without EDITOR should warn about EDITOR. output: {combined!r}")
            return

        pass_test(name)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main() -> int:
    print("Running cross-repo-memo draft lifecycle tests (C1 + C2 + C3)...")
    print(f"Script: {_script_path()}")
    print()

    tests = [
        test_draft_creates_outbox_file,
        test_draft_collision_exits_2,
        # C2 tests (test_send_missing_topic_no_draft deleted — superseded by test_send_missing_topic_hint_list)
        test_send_consumes_outbox,
        test_send_missing_topic_hint_list,
        test_send_malformed_outbox_leaves_in_place,
        test_send_receiver_unresolvable_leaves_in_place,
        test_send_preserves_supersedes,
        # C3 tests
        test_list_enumerates_with_age,
        test_list_empty_prints_no_drafts,
        test_discard_removes_file,
        test_discard_missing_topic,
        test_compose_prints_path_default,
        test_compose_missing_topic,
        test_compose_open_without_editor,
    ]

    for test_fn in tests:
        try:
            test_fn()
        except Exception as exc:
            fail_test(test_fn.__name__, f"unexpected exception: {exc}")

    print()
    print(f"Results: {TESTS_PASSED} passed, {TESTS_FAILED} failed out of {TESTS_PASSED + TESTS_FAILED} tests")
    if FAILURES:
        print("Failures:")
        for f in FAILURES:
            print(f"  {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
