#!/bin/sh
''''exec "$(command -v python3 || command -v python || command -v py)" "$0" "$@" #'''
from __future__ import annotations
"""
cross-repo-memo.test.py — smoke tests for the cross-repo-memo dispatcher CLI.

Spec backlink: docs/plans/2026-05-23-cross-repo-single-surface-and-canonical-scaffold.md § Chunk 3
Prior spec: docs/plans/2026-05-21-cross-repo-memo-discoverability.md § Chunk 2
Extended by: docs/plans/2026-05-23-cross-repo-inbox-archive-restructure.md § Chunk B
Extended by: docs/plans/2026-05-23-cross-repo-inbox-archive-restructure.md § Chunk H
Extended by: docs/plans/2026-05-30-pickup-cross-repo-memo-fork.md § C2

Purpose: Verify single-delivery-copy behaviour of the dispatcher:
  - Test 1: receiver-repo delivery writes ONE dirty file to receiver's cross-repo/inbox/
             NO archive/sender copy is written.
  - Test 2: unregistered receiver hard-errors (exit non-zero, no file written) —
             single-surface model has no central-only fallback.
  - Test 3: --self-receipt sets action_taken lifecycle fields in receiver-side file
  - Test 4: --self-receipt without --decision exits non-zero
  - Test 5: path-traversal --topic is rejected (F2 regression)
  - Test 6: --decision superseded is accepted (F1 regression)
  - Test 7: title with YAML-special chars round-trips through parser (F3 regression)
  - Test 8: receiver identity resolves to repos.<name> by convention
  - Test 9: hard-error message lists known receivers (hint path)
  - Test 10: sender identity is derived from the repo, never hardcoded
  - Test 11 (B1/T1): traversal-attempt fixture — --topic validated; _write_file
              rejects a path that escapes the receiver root
  - Tests 12-17 (B2): central receiver resolution
      - Test 12: --to claude-central-em resolves to DoE-claude repo (repos.doe_claude)
      - Test 13: --to central alias resolves to DoE-claude repo
      - Test 14: --to central-em (middle alias / DM5a) resolves to DoE-claude repo
      - Test 15: case/whitespace normalisation (DM5b)
      - Test 16: unregistered repo STILL hard-errors (no regression of no-implicit-fallback)
      - Test 17 (new): central with repos.doe_claude absent hard-errors with remediation message
  - Tests 18-21 (B3): gitignore delivery guard
      - Test 18: gitignored receiver → hard-error, no file written, no orphan dir
      - Test 19: normal (non-ignored) receiver → delivery proceeds silently
      - Test 20: non-git receiver (exit 128) → PROCEED, not block (DM5c)
      - Test 21: no orphan cross-repo/inbox/ dir on gitignore hard-error path (DM5d)
  - Test 14b (C2a): --to doe-claude-em delivers to DoE-claude repo
  - Tests 21-26 (H/D6): publish-target receiver rejection
      - Test 21: --to coordinator-claude-em → rejected with publish-target message
      - Test 22: --to coordinator-claude (shortname) → rejected
      # Review: code-reviewer — F4: corrected 22-27→21-26, fixed doubled Test 22→Test 21, added Test 14b
      - Test 23: --to deep-research-claude-em → rejected
      - Test 24: COORDINATOR_OVERRIDE_PUBLISH_TARGET_RECEIVER=1 → publish-target check bypassed
      - Test 25: case/whitespace normalisation — mixed-case and padded forms → rejected
      - Test 26: canonical EM receivers NOT rejected (project-rag-em, example-game-repo-em,
                 claude-central-em) → proceed past publish-target check

Run with: python bin/cross-repo-memo.test.py
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


def _load_dispatcher_module():
    """Import the extensionless cross-repo-memo script as a module.

    The script has no .py extension and is not directly executable on Windows,
    but it is valid Python — importlib loads it by path. Loaded under a name
    other than __main__ so the `if __name__ == "__main__"` guard does not fire.
    """
    import importlib.util
    from importlib.machinery import SourceFileLoader

    # Explicit SourceFileLoader: spec_from_file_location can't infer a loader
    # for an extensionless path, leaving spec.loader is None.
    loader = SourceFileLoader("cross_repo_memo", _script_path())
    spec = importlib.util.spec_from_loader("cross_repo_memo", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


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

    code-review F4: value parser is now quoted-string aware. When the value
    starts with a double-quote, it reads until the matching closing double-quote
    (not just the first ':' character), so titles containing ':' round-trip
    correctly (e.g. 'Fix: gate-check failures — see #42 [urgent]').
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
            # Quoted-string aware: if the value opens with a double-quote, find
            # the matching closing quote rather than truncating at the next ':'.
            if v.startswith('"'):
                # Re-parse from the full remainder (after 'key: ') to find the
                # complete quoted string, handling embedded ':' in the value.
                raw_rest = line[len(key) + 1:].strip()  # everything after 'key:'
                if raw_rest.startswith('"'):
                    # Walk forward to find the closing unescaped double-quote.
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
                            elif nc == 't':
                                chars.append('\t')
                            else:
                                chars.append(nc)
                            i += 2
                            continue
                        if c == '"':
                            break  # closing quote
                        chars.append(c)
                        i += 1
                    v = ''.join(chars)
                else:
                    # Unquoted fallback.
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


def _find_inbox_file(inbox_dir: str, topic: str) -> str | None:
    """Return the path of the first receiver inbox file matching *-<topic>.md.

    The receiver filename is now <date>-<from>-<topic>.md — the exact sender
    component varies by test environment.  This helper locates the file by its
    topic suffix so integration tests are portable across environments.

    Returns None if no matching file is found.
    """
    import glob
    pattern = os.path.join(inbox_dir, f"*-{topic}.md")
    matches = glob.glob(pattern)
    return matches[0] if matches else None


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


def _make_mock_machine_local_subcommand_aware(tmpdir: str, keys: list[str]) -> str:
    """Create a stub machine-local that distinguishes `get` from `keys`.

    `get <key>` always exits non-zero (key absent — drives the hard-error path).
    `keys` prints the supplied key list, one per line (drives _known_receiver_ids).
    This exercises the repo-absent error message's "Known receivers" hint, which
    a single-return stub cannot reach.
    """
    stub_path = os.path.join(tmpdir, "_mock_machine_local_subcmd.py")
    keys_repr = repr(keys)
    script = textwrap.dedent(f"""\
        #!/usr/bin/env python3
        import sys
        argv = sys.argv[1:]
        if argv and argv[0] == "keys":
            for k in {keys_repr}:
                print(k)
            sys.exit(0)
        print("machine-local: key not found", file=sys.stderr)
        sys.exit(1)
    """)
    with open(stub_path, "w") as f:
        f.write(script)
    return stub_path


# ---------------------------------------------------------------------------
# Test 1 — receiver-repo delivery mode: single dirty copy in cross-repo/
# ---------------------------------------------------------------------------

def test_receiver_repo_delivery() -> None:
    name = "Test 1 — receiver-repo delivery: single dirty copy in cross-repo/"
    import datetime

    with tempfile.TemporaryDirectory() as receiver_tmpdir, \
         tempfile.TemporaryDirectory() as claude_home_tmpdir:

        mock_impl = _make_mock_machine_local(receiver_tmpdir, receiver_tmpdir)

        env = {
            **os.environ,
            "MACHINE_LOCAL_IMPL": mock_impl,
            "CLAUDE_HOME": claude_home_tmpdir,
        }

        result = _run_dispatcher(
            ["--to", "project-rag-em", "--topic", "test-topic", "--title", "Test Memo"],
            env=env,
            stdin_text="This is the test memo body.\n",
        )

        if result.returncode != 0:
            fail_test(name, f"dispatcher exited {result.returncode}: {result.stderr}")
            return

        # Receiver filename is now <date>-<from>-<topic>.md; locate by topic suffix.
        inbox_dir = os.path.join(receiver_tmpdir, "cross-repo", "inbox")
        receiver_file = _find_inbox_file(inbox_dir, "test-topic")
        if receiver_file is None:
            fail_test(name, f"receiver-side file not found in {inbox_dir} (pattern *-test-topic.md)")
            return

        # Assert NO archive/sender copy is written — single-delivery-copy model.
        today = datetime.date.today().isoformat()
        archive_file = os.path.join(claude_home_tmpdir, "archive", "cross-repo", f"{today}-test-topic.md")
        if os.path.isfile(archive_file):
            fail_test(name, f"NO archive copy should be written; found unexpected file at {archive_file}")
            return

        # Parse frontmatter from receiver-side file.
        with open(receiver_file) as f:
            receiver_content = f.read()

        receiver_fm = _parse_frontmatter(receiver_content)

        if receiver_fm.get("status") != "open":
            fail_test(name, f"receiver status should be 'open', got: {receiver_fm.get('status')}")
            return
        if receiver_fm.get("delivery_mode") != "receiver-repo":
            fail_test(name, f"receiver delivery_mode should be 'receiver-repo', got: {receiver_fm.get('delivery_mode')}")
            return

        # Assert no receiver_copy_path field — removed from single-copy model.
        if "receiver_copy_path" in receiver_fm:
            fail_test(name, f"receiver_copy_path should NOT be in frontmatter (single-copy model)")
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
        # The memo should appear as untracked under cross-repo/inbox/. Git may surface it as:
        #   - `?? cross-repo/inbox/<file>` (if inbox/ was already tracked)
        #   - `?? cross-repo/` (if cross-repo/ itself is untracked — new repo)
        # Either form confirms the file is NOT staged.
        memo_basename = os.path.basename(receiver_file)
        memo_rel = os.path.relpath(receiver_file, receiver_tmpdir).replace("\\", "/")
        staged_in_output = (
            f"A  {memo_rel}" in status_output
            or f"A  cross-repo/inbox/{memo_basename}" in status_output
        )
        untracked_in_output = (
            f"?? {memo_rel}" in status_output
            or f"?? cross-repo/inbox/{memo_basename}" in status_output
            or "?? cross-repo/" in status_output
            or "?? cross-repo\\" in status_output
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

        # Assert stdout contains PM-relay reminder and receiver path.
        if "PM-relay is still the primary channel" not in result.stdout:
            fail_test(name, f"PM-relay reminder missing from stdout: {result.stdout!r}")
            return
        if "Hand the PM this path for relay" not in result.stdout:
            fail_test(name, f"'Hand the PM this path for relay' missing from stdout: {result.stdout!r}")
            return

        pass_test(name)


# ---------------------------------------------------------------------------
# Test 2 — unregistered receiver hard-errors (single-surface model)
#
# A receiver whose repo isn't registered on this machine cannot receive a dirty
# memo. The CLI hard-errors (exit non-zero), writes NO file, and points the
# operator at PM-relay. There is no central-only fallback.
# ---------------------------------------------------------------------------

def test_unregistered_receiver_hard_errors() -> None:
    name = "Test 2 — unregistered receiver: hard error, no file written"
    import datetime

    with tempfile.TemporaryDirectory() as claude_home_tmpdir, \
         tempfile.TemporaryDirectory() as receiver_tmpdir:
        # Mock machine-local to report the key as absent (unregistered repo).
        mock_impl = _make_mock_machine_local(receiver_tmpdir, None)
        env = {
            **os.environ,
            "MACHINE_LOCAL_IMPL": mock_impl,
            "CLAUDE_HOME": claude_home_tmpdir,
        }

        result = _run_dispatcher(
            ["--to", "nonexistent-repo-em", "--topic", "test", "--title", "Test"],
            env=env,
            stdin_text="Body.\n",
        )

        # Assert hard error (non-zero exit).
        if result.returncode == 0:
            fail_test(name, f"dispatcher should exit non-zero for unregistered receiver; got 0. stdout: {result.stdout!r}")
            return

        # Assert NO file written anywhere — inbox should be absent or empty.
        inbox_dir = os.path.join(receiver_tmpdir, "cross-repo", "inbox")
        stray = _find_inbox_file(inbox_dir, "test") if os.path.isdir(inbox_dir) else None
        if stray is not None:
            fail_test(name, f"NO file should be written for unregistered receiver; found {stray}")
            return
        today = datetime.date.today().isoformat()
        archive_file = os.path.join(claude_home_tmpdir, "archive", "cross-repo", f"{today}-test.md")
        if os.path.isfile(archive_file):
            fail_test(name, f"NO archive copy should be written; found {archive_file}")
            return

        # Assert the error names the unresolved key and points at PM-relay.
        combined = result.stdout + result.stderr
        if "not registered" not in combined.lower() and "cannot deliver" not in combined.lower():
            fail_test(name, f"error should explain the repo is not registered. stderr: {result.stderr!r}")
            return
        if "pm" not in combined.lower():
            fail_test(name, f"error should point at PM-relay. stderr: {result.stderr!r}")
            return

        pass_test(name)


# ---------------------------------------------------------------------------
# Test 3 — --self-receipt mode
#
# Single-delivery-copy model: --self-receipt still writes ONE file to receiver's
# cross-repo/ (the dispatcher IS the receiver). No archive copy.
# ---------------------------------------------------------------------------

def test_self_receipt() -> None:
    name = "Test 3 — --self-receipt mode: single file in cross-repo/inbox/, no archive copy"
    import datetime

    with tempfile.TemporaryDirectory() as receiver_tmpdir, \
         tempfile.TemporaryDirectory() as claude_home_tmpdir:

        mock_impl = _make_mock_machine_local(receiver_tmpdir, receiver_tmpdir)

        env = {
            **os.environ,
            "MACHINE_LOCAL_IMPL": mock_impl,
            "CLAUDE_HOME": claude_home_tmpdir,
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

        # Receiver filename is now <date>-<from>-test.md; locate by topic suffix.
        inbox_dir = os.path.join(receiver_tmpdir, "cross-repo", "inbox")
        receiver_file = _find_inbox_file(inbox_dir, "test")
        if receiver_file is None:
            fail_test(name, f"receiver-side file not found in {inbox_dir} (pattern *-test.md)")
            return

        # Assert NO archive copy — single-delivery-copy model.
        today = datetime.date.today().isoformat()
        archive_file = os.path.join(claude_home_tmpdir, "archive", "cross-repo", f"{today}-test.md")
        if os.path.isfile(archive_file):
            fail_test(name, f"NO archive copy should be written; found unexpected file at {archive_file}")
            return

        with open(receiver_file) as f:
            receiver_content = f.read()

        receiver_fm = _parse_frontmatter(receiver_content)

        if receiver_fm.get("status") != "actioned":
            fail_test(name, f"receiver status should be 'actioned' (canonical terminal), got: {receiver_fm.get('status')}")
            return
        if receiver_fm.get("decision") != "accepted":
            fail_test(name, f"receiver decision should be 'accepted', got: {receiver_fm.get('decision')}")
            return
        if not receiver_fm.get("action_taken_at"):
            fail_test(name, "receiver action_taken_at should be populated")
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
#
# Uses --self-receipt with receiver-repo delivery (machine-local mocked) so
# the single delivery copy lands in cross-repo/ for assertion.
# ---------------------------------------------------------------------------

def test_decision_superseded_accepted() -> None:
    name = "decision_superseded_accepted"
    with tempfile.TemporaryDirectory() as receiver_tmpdir, \
         tempfile.TemporaryDirectory() as claude_home_tmpdir:
        mock_impl = _make_mock_machine_local(receiver_tmpdir, receiver_tmpdir)
        env = {
            **os.environ,
            "MACHINE_LOCAL_IMPL": mock_impl,
            "CLAUDE_HOME": claude_home_tmpdir,
        }
        result = _run_dispatcher(
            ["--to", "project-rag-em", "--topic", "test-superseded",
             "--title", "T", "--self-receipt", "--decision", "superseded"],
            env=env,
            stdin_text="Body.\n",
        )
        if result.returncode != 0:
            fail_test(name, f"dispatcher should accept --decision superseded; exit {result.returncode}, stderr: {result.stderr!r}")
            return
        # Confirm receiver frontmatter carries decision: superseded.
        inbox_dir = os.path.join(receiver_tmpdir, "cross-repo", "inbox")
        receiver_file = _find_inbox_file(inbox_dir, "test-superseded")
        if receiver_file is None:
            fail_test(name, f"receiver file not found in {inbox_dir} (pattern *-test-superseded.md)")
            return
        with open(receiver_file) as f:
            fm = _parse_frontmatter(f.read())
        if fm.get("decision") != "superseded":
            fail_test(name, f"decision field should be 'superseded', got: {fm.get('decision')!r}")
            return
        pass_test(name)


# ---------------------------------------------------------------------------
# Test 7 — title with YAML-special chars round-trips through parser (F3 regression)
#
# Uses receiver-repo delivery so the single delivery copy exists for assertion.
# ---------------------------------------------------------------------------

def test_title_yaml_special_chars() -> None:
    name = "title_yaml_special_chars"
    with tempfile.TemporaryDirectory() as receiver_tmpdir, \
         tempfile.TemporaryDirectory() as claude_home_tmpdir:
        mock_impl = _make_mock_machine_local(receiver_tmpdir, receiver_tmpdir)
        env = {
            **os.environ,
            "MACHINE_LOCAL_IMPL": mock_impl,
            "CLAUDE_HOME": claude_home_tmpdir,
        }
        nasty_title = 'Fix: gate-check failures — see #42 [urgent]'
        result = _run_dispatcher(
            ["--to", "project-rag-em", "--topic", "test-yaml",
             "--title", nasty_title],
            env=env,
            stdin_text="Body.\n",
        )
        if result.returncode != 0:
            fail_test(name, f"dispatcher should accept title with special chars; exit {result.returncode}")
            return
        inbox_dir = os.path.join(receiver_tmpdir, "cross-repo", "inbox")
        receiver_file = _find_inbox_file(inbox_dir, "test-yaml")
        if receiver_file is None:
            fail_test(name, f"receiver file not found in {inbox_dir} (pattern *-test-yaml.md)")
            return
        with open(receiver_file) as f:
            fm = _parse_frontmatter(f.read())
        if fm.get("title") != nasty_title:
            fail_test(name, f"title should round-trip exactly. Expected: {nasty_title!r}, got: {fm.get('title')!r}")
            return
        pass_test(name)


# ---------------------------------------------------------------------------
# Test 8 — receiver identity resolves to repos.<name> by convention
#
# Regression for the 2026-05-23 gap: project-rag-ue-addon-em fell through the
# old hardcoded RECEIVER_EM_TO_REPO_KEY table (only 3 entries) to central-only,
# with no dirty-file backstop in the addon repo. Convention derivation + the
# divergent-only alias map covers every registered repo with no per-repo edit.
# ---------------------------------------------------------------------------

def test_receiver_key_convention() -> None:
    name = "receiver_key_convention — convention + alias resolution"
    mod = _load_dispatcher_module()
    cases = {
        "project-rag-em": "repos.project_rag",
        "example-sim-repo-em": "repos.example-sim-repo",
        "project-rag-ue-addon-em": "repos.project_rag_ue_addon",  # the reported gap
        # Pure key-derivation only — delivery to coordinator-claude-em is still
        # rejected by the publish-target guard (Tests 21-26) BEFORE this key is used.
        "coordinator-claude-em": "repos.coordinator_claude",
        "example-game-repo-em": "repos.example_game_workbench_repo",  # divergent alias
        # No trailing -em: treated as a bare shortname.
        "project-rag": "repos.project_rag",
    }
    for receiver, expected in cases.items():
        got = mod._receiver_repo_key(receiver)
        if got != expected:
            fail_test(name, f"{receiver!r} → {got!r}, expected {expected!r}")
            return
    pass_test(name)


# ---------------------------------------------------------------------------
# Test 9 — hard-error message lists known receivers (hint path)
#
# A single-return mock can't reach _known_receiver_ids (it ignores the `keys`
# subcommand). This uses a subcommand-aware stub so the "Known receivers on this
# machine: ..." hint in the repo-absent error is actually exercised.
# ---------------------------------------------------------------------------

def test_unregistered_receiver_lists_known() -> None:
    name = "unregistered_receiver_lists_known — error names known receivers"
    with tempfile.TemporaryDirectory() as claude_home_tmpdir, \
         tempfile.TemporaryDirectory() as impl_tmpdir:
        mock_impl = _make_mock_machine_local_subcommand_aware(
            impl_tmpdir,
            ["repos.project_rag", "repos.example_game_workbench_repo", "schema"],
        )
        env = {
            **os.environ,
            "MACHINE_LOCAL_IMPL": mock_impl,
            "CLAUDE_HOME": claude_home_tmpdir,
        }
        result = _run_dispatcher(
            ["--to", "nonexistent-repo-em", "--topic", "test", "--title", "T"],
            env=env,
            stdin_text="Body.\n",
        )
        if result.returncode == 0:
            fail_test(name, "should hard-error for unregistered receiver")
            return
        # The hint reverses repos.* keys to <name>-em identities; non-repos. keys
        # (e.g. 'schema') must be filtered out.
        if "project-rag-em" not in result.stderr:
            fail_test(name, f"error should list 'project-rag-em' as a known receiver. stderr: {result.stderr!r}")
            return
        if "example-game-repo-em" not in result.stderr:
            fail_test(name, f"error should reverse the alias to 'example-game-repo-em'. stderr: {result.stderr!r}")
            return
        if "schema-em" in result.stderr:
            fail_test(name, f"non-repos. key 'schema' should be filtered, not surfaced as 'schema-em'. stderr: {result.stderr!r}")
            return
        pass_test(name)


# ---------------------------------------------------------------------------
# Test 10 — sender identity is derived from the repo, never hardcoded
#
# `from:` must reflect the repo the CLI runs in: repos.doe_claude →
# claude-central-em; a registered sibling reverses to <name>-em (incl. alias);
# an unregistered repo falls back to its basename; no root → unknown-sender-em.
# ~/.claude is no longer a central-identity anchor (C2a flip).
# ---------------------------------------------------------------------------

def test_sender_identity_from_repo() -> None:
    name = "sender_identity_from_repo — from: derived, not hardcoded"
    mod = _load_dispatcher_module()

    doe_path = os.path.normpath("/work/doe-claude")
    repo_paths = {
        "repos.doe_claude": doe_path,
        "repos.project_rag": os.path.normpath("/work/project-rag"),
        "repos.example_game_workbench_repo": os.path.normpath("/work/example-game-workbench-repo"),
    }
    cases = [
        # (root, expected)
        # repos.doe_claude → claude-central-em (central identity anchor post-C2a)
        (doe_path, "claude-central-em"),
        # ~/.claude is no longer central — falls through to basename
        (os.path.normpath("/home/op/.claude"), ".claude-em"),
        (os.path.normpath("/work/project-rag"), "project-rag-em"),
        # alias reversal: the example-game-repo repo registers under its full name
        (os.path.normpath("/work/example-game-workbench-repo"), "example-game-repo-em"),
        # unregistered repo → basename fallback (still "the repo the session is in")
        (os.path.normpath("/work/some-unregistered-repo"), "some-unregistered-repo-em"),
        # not in a git repo at all
        (None, "unknown-sender-em"),
    ]
    for root, expected in cases:
        got = mod.em_id_for_root(root, repo_paths)
        if got != expected:
            fail_test(name, f"root={root!r} → {got!r}, expected {expected!r}")
            return

    # Inverse-conversion round-trip: _receiver_repo_key and repo_key_to_em_id
    # are exact inverses for every registered identity.
    # DELIBERATELY EXCLUDES claude-central-em / doe-claude-em: both resolve to the
    # single repos.doe_claude path (canonical + alias → one path), so the mapping is
    # intentionally NOT a bijection there — repo_key_to_em_id('repos.doe_claude') is
    # 'claude-central-em' (canonical), never 'doe-claude-em'. Do NOT add either central
    # id to this list; it is not a bug, and adding it would break the exact-inverse assertion.
    for em_id in ("project-rag-ue-addon-em", "example-sim-repo-em", "example-game-repo-em"):
        key = mod._receiver_repo_key(em_id)
        if mod.repo_key_to_em_id(key) != em_id:
            fail_test(name, f"round-trip broke for {em_id!r}: key={key!r} → {mod.repo_key_to_em_id(key)!r}")
            return
    pass_test(name)


# ---------------------------------------------------------------------------
# Test 11 (B1/T1) — path-traversal guard: _write_file rejects escape from receiver root
#
# T1 correctness trap: with the inbox subdir, walking up ONE parent from the
# composed path yields cross-repo/inbox/ — NOT the repo root. The fix anchors
# expected_root to receiver_path directly. This test provides a fixture that
# verifies a crafted symlink-escaping path is rejected, exercising the real guard.
#
# Spec backlink: docs/plans/2026-05-23-cross-repo-inbox-archive-restructure.md § B1 (T1)
# ---------------------------------------------------------------------------

def test_write_file_traversal_guard() -> None:
    name = "Test 11 (B1/T1) — _write_file path-traversal guard rejects escape from receiver root"
    mod = _load_dispatcher_module()
    import datetime

    with tempfile.TemporaryDirectory() as receiver_tmpdir, \
         tempfile.TemporaryDirectory() as outside_tmpdir:

        today = datetime.date.today().isoformat()

        # Craft a path that is OUTSIDE the receiver root — e.g. a sibling of tmpdir.
        # Simulates a registry value or symlink shenanigan that resolves outside the
        # declared receiver repo root.
        evil_path = os.path.join(outside_tmpdir, "cross-repo", "inbox", f"{today}-evil.md")

        # _write_file(path, content, receiver_path) should raise ValueError when
        # the realpath of `path` escapes `receiver_path`.
        try:
            mod._write_file(evil_path, "# evil\n", receiver_tmpdir)
            # If no exception: the guard failed.
            fail_test(name, "ValueError expected for path that escapes receiver root; none raised")
        except ValueError as exc:
            if "traversal" not in str(exc).lower() and "escapes" not in str(exc).lower():
                fail_test(name, f"ValueError raised but message doesn't mention traversal: {exc!r}")
                return
            pass_test(name)
        except Exception as exc:
            fail_test(name, f"unexpected exception type {type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Tests 12-17 (B2) — central receiver resolution
#
# Spec backlink: docs/plans/2026-05-23-cross-repo-inbox-archive-restructure.md § B2 (DM1)
#
# Key assertions:
#   - --to claude-central-em → DoE-claude repo (repos.doe_claude), NOT CLAUDE_HOME
#   - --to central → same (alias)
#   - --to central-em → same (DM5a middle alias)
#   - Case/whitespace normalization (DM5b)
#   - Unregistered repo STILL hard-errors (no regression)
#   - central with repos.doe_claude absent hard-errors with remediation message
# ---------------------------------------------------------------------------

def _make_mock_machine_local_key_absent(tmpdir: str) -> str:
    """Stub that always exits non-zero (key absent). Used to exercise hard-error paths
    for unregistered receivers."""
    stub_path = os.path.join(tmpdir, "_mock_ml_absent.py")
    script = textwrap.dedent("""\
        #!/usr/bin/env python3
        import sys
        print("machine-local: key not found", file=sys.stderr)
        sys.exit(1)
    """)
    with open(stub_path, "w") as f:
        f.write(script)
    return stub_path


def _make_mock_machine_local_doe_claude(tmpdir: str, doe_path: str) -> str:
    """Stub that returns doe_path for repos.doe_claude and exits non-zero for other keys.

    Models the invocation contract of _machine_local_get:
      called as: [python, impl, "get", key]
      repos.doe_claude → print(doe_path), exit 0
      keys subcommand → exit 0, no output (no mirrors configured)
      any other key → exit 1

    The keys branch prevents a spurious publish-mirror WARNING on tests that call
    _assert_central_delivery, where the publish-target guard expects a zero exit
    from `machine-local keys` to enumerate mirror owners.
    """
    # Review: code-reviewer — added keys branch; without it _machine_local_mirror_keys()
    # sees exit 1 and emits a spurious WARNING on every _assert_central_delivery call.
    stub_path = os.path.join(tmpdir, "_mock_ml_doe.py")
    escaped = doe_path.replace("\\", "\\\\")
    script = textwrap.dedent(f"""\
        #!/usr/bin/env python3
        import sys
        argv = sys.argv[1:]
        if len(argv) == 2 and argv[0] == "get" and argv[1] == "repos.doe_claude":
            print("{escaped}")
            sys.exit(0)
        if len(argv) == 1 and argv[0] == "keys":
            sys.exit(0)
        print("machine-local: key not found", file=sys.stderr)
        sys.exit(1)
    """)
    with open(stub_path, "w") as f:
        f.write(script)
    return stub_path


def _assert_central_delivery(name: str, to_arg: str) -> bool:
    """Helper: run dispatcher with --to <to_arg>, repos.doe_claude registered to a
    tmpdir, and assert it delivers to <doe_tmpdir>/cross-repo/inbox/<file>.
    Returns True on pass, False on fail (also calls fail_test)."""
    import datetime
    with tempfile.TemporaryDirectory() as doe_tmpdir, \
         tempfile.TemporaryDirectory() as claude_home_tmpdir, \
         tempfile.TemporaryDirectory() as stub_tmpdir:
        mock_impl = _make_mock_machine_local_doe_claude(stub_tmpdir, doe_tmpdir)
        env = {
            **os.environ,
            "MACHINE_LOCAL_IMPL": mock_impl,
            "CLAUDE_HOME": claude_home_tmpdir,
        }
        result = _run_dispatcher(
            ["--to", to_arg, "--topic", "central-test", "--title", "Central Test"],
            env=env,
            stdin_text="Body.\n",
        )
        if result.returncode != 0:
            fail_test(name, f"--to {to_arg!r}: dispatcher exited {result.returncode}: {result.stderr}")
            return False
        # Must deliver to DoE-claude repo, NOT CLAUDE_HOME.
        # Receiver filename is <date>-<from>-central-test.md; locate by topic suffix.
        doe_inbox = os.path.join(doe_tmpdir, "cross-repo", "inbox")
        expected_file = _find_inbox_file(doe_inbox, "central-test")
        if expected_file is None:
            fail_test(name, f"--to {to_arg!r}: expected delivery at DoE path {doe_inbox}/*-central-test.md, not found. stdout: {result.stdout!r}")
            return False
        claude_home_inbox = os.path.join(claude_home_tmpdir, "cross-repo", "inbox")
        wrong_file = _find_inbox_file(claude_home_inbox, "central-test") if os.path.isdir(claude_home_inbox) else None
        if wrong_file is not None:
            fail_test(name, f"--to {to_arg!r}: memo was WRONGLY delivered to CLAUDE_HOME {wrong_file} — must deliver only to DoE-claude repo")
            return False
        return True


def test_central_receiver_canonical() -> None:
    name = "Test 12 (B2) — --to claude-central-em delivers to DoE-claude repo (repos.doe_claude)"
    if _assert_central_delivery(name, "claude-central-em"):
        pass_test(name)


def test_central_receiver_alias_central() -> None:
    name = "Test 13 (B2) — --to central alias delivers to DoE-claude repo (repos.doe_claude)"
    if _assert_central_delivery(name, "central"):
        pass_test(name)


def test_central_receiver_alias_central_em() -> None:
    name = "Test 14 (B2/DM5a) — --to central-em (middle alias) delivers to DoE-claude repo (repos.doe_claude)"
    if _assert_central_delivery(name, "central-em"):
        pass_test(name)


def test_central_receiver_alias_doe_claude_em() -> None:
    """C2a: doe-claude-em was added to centralReceiverIds in the manifest (C1).

    --to doe-claude-em must route centrally — to the DoE-claude repo, not a
    sibling working tree.  Mirrors Tests 12-14 via _assert_central_delivery.
    """
    name = "Test 14b (C2a) — --to doe-claude-em delivers to DoE-claude repo (repos.doe_claude)"
    if _assert_central_delivery(name, "doe-claude-em"):
        pass_test(name)


def test_central_receiver_case_whitespace_normalization() -> None:
    """DM5b: _is_central_receiver normalises case and whitespace.

    Spec: _is_central_receiver does receiver_em_id.strip().lower() in _CENTRAL_RECEIVER_IDS.
    Test the pure function directly (no subprocess needed for normalisation assertion).
    """
    name = "Test 15 (B2/DM5b) — _is_central_receiver: case+whitespace normalisation"
    mod = _load_dispatcher_module()
    cases = [
        "Claude-Central-EM",   # mixed case
        " central ",           # leading/trailing whitespace
        "CENTRAL",             # all-caps
        "Central-Em",          # mixed case, middle alias
    ]
    for s in cases:
        if not mod._is_central_receiver(s):
            fail_test(name, f"_is_central_receiver({s!r}) returned False; expected True")
            return
    # Negative: a genuinely unregistered id must NOT match.
    unregistered = ["project-rag-em", "example-sim-repo-em", ""]
    for s in unregistered:
        if mod._is_central_receiver(s):
            fail_test(name, f"_is_central_receiver({s!r}) returned True; expected False")
            return
    pass_test(name)


def test_unregistered_repo_still_hard_errors() -> None:
    """B2 no-regression: --to <unregistered> still hard-errors.

    Verifies the 'no implicit fallback' guarantee is untouched — adding
    central as an explicit receiver must NOT silently swallow unknown repo ids.
    """
    name = "Test 16 (B2) — unregistered repo STILL hard-errors (no implicit fallback regression)"
    with tempfile.TemporaryDirectory() as claude_home_tmpdir, \
         tempfile.TemporaryDirectory() as stub_tmpdir:
        mock_impl = _make_mock_machine_local_key_absent(stub_tmpdir)
        env = {
            **os.environ,
            "MACHINE_LOCAL_IMPL": mock_impl,
            "CLAUDE_HOME": claude_home_tmpdir,
        }
        result = _run_dispatcher(
            ["--to", "some-unknown-repo-em", "--topic", "test", "--title", "Test"],
            env=env,
            stdin_text="Body.\n",
        )
        if result.returncode == 0:
            fail_test(name, "dispatcher should exit non-zero for unregistered receiver; got 0")
            return
        # Error must mention the repo is unreachable / not registered.
        combined = result.stdout + result.stderr
        if "not registered" not in combined.lower() and "cannot deliver" not in combined.lower():
            fail_test(name, f"error should explain unreachable repo. stderr: {result.stderr!r}")
            return
        pass_test(name)


def test_central_hard_errors_when_doe_unregistered() -> None:
    """B2 new requirement: central with repos.doe_claude absent must hard-error
    with a central-specific remediation message — NOT fall back to ~/.claude.
    """
    name = "Test 17 (B2) — central with repos.doe_claude absent hard-errors with remediation message"
    with tempfile.TemporaryDirectory() as claude_home_tmpdir, \
         tempfile.TemporaryDirectory() as stub_tmpdir:
        mock_impl = _make_mock_machine_local_key_absent(stub_tmpdir)
        env = {
            **os.environ,
            "MACHINE_LOCAL_IMPL": mock_impl,
            "CLAUDE_HOME": claude_home_tmpdir,
        }
        result = _run_dispatcher(
            ["--to", "claude-central-em", "--topic", "test", "--title", "Test"],
            env=env,
            stdin_text="Body.\n",
        )
        if result.returncode == 0:
            fail_test(name, "dispatcher should exit non-zero when repos.doe_claude absent; got 0")
            return
        # Error must mention repos.doe_claude and remediation.
        combined = result.stdout + result.stderr
        if "repos.doe_claude" not in combined:
            fail_test(name, f"error should mention repos.doe_claude. stderr: {result.stderr!r}")
            return
        # Must NOT have delivered to CLAUDE_HOME
        import datetime
        today = datetime.date.today().isoformat()
        wrong_file = os.path.join(claude_home_tmpdir, "cross-repo", "inbox", f"{today}-test.md")
        if os.path.isfile(wrong_file):
            fail_test(name, f"memo was WRONGLY delivered to CLAUDE_HOME {wrong_file} on error path")
            return
        pass_test(name)


# ---------------------------------------------------------------------------
# Tests 18-21 (B3) — gitignore delivery guard
#
# Spec backlink: docs/plans/2026-05-23-cross-repo-inbox-archive-restructure.md § B3
#
# Exit-code semantics for `git check-ignore`:
#   exit 0  → ignored → hard-error (no file written, no orphan dir)
#   exit 1  → not ignored → proceed
#   exit 128 → not-a-git-repo → PROCEED-not-block (DM5c)
# ---------------------------------------------------------------------------

def _make_receiver_with_gitignore(parent_tmpdir: str, gitignore_content: str) -> str:
    """Create a git-initialised receiver dir with the given .gitignore content.
    Returns the receiver dir path."""
    receiver_dir = os.path.join(parent_tmpdir, "receiver_repo")
    os.makedirs(receiver_dir)
    subprocess.run(["git", "init", receiver_dir], capture_output=True, check=False)
    subprocess.run(
        ["git", "-C", receiver_dir, "config", "user.email", "test@test.com"],
        capture_output=True, check=False,
    )
    subprocess.run(
        ["git", "-C", receiver_dir, "config", "user.name", "Test"],
        capture_output=True, check=False,
    )
    gitignore_path = os.path.join(receiver_dir, ".gitignore")
    with open(gitignore_path, "w") as f:
        f.write(gitignore_content)
    subprocess.run(
        ["git", "-C", receiver_dir, "add", ".gitignore"],
        capture_output=True, check=False,
    )
    subprocess.run(
        ["git", "-C", receiver_dir, "commit", "-m", "init gitignore"],
        capture_output=True, check=False,
    )
    return receiver_dir


def test_gitignored_receiver_hard_errors() -> None:
    """B3 Test 18: a receiver whose .gitignore swallows cross-repo/ → hard-error.

    Exit 0 from `git check-ignore` (path IS ignored) must produce a non-zero
    exit from the dispatcher and leave no file behind.
    """
    # Review: code-reviewer — B3 renumbered to 18-21 when Test 17 (B2) was inserted; name/docstring updated to match
    name = "Test 18 (B3) — gitignored receiver → hard-error, no file written"
    import datetime
    with tempfile.TemporaryDirectory() as tmpdir:
        receiver_dir = _make_receiver_with_gitignore(tmpdir, "cross-repo/\n")
        mock_impl_path = os.path.join(tmpdir, "_ml.py")
        escaped = receiver_dir.replace("\\", "\\\\")
        with open(mock_impl_path, "w") as f:
            f.write(textwrap.dedent(f"""\
                #!/usr/bin/env python3
                import sys
                print("{escaped}")
                sys.exit(0)
            """))
        env = {
            **os.environ,
            "MACHINE_LOCAL_IMPL": mock_impl_path,
            "CLAUDE_HOME": tmpdir,
        }
        result = _run_dispatcher(
            ["--to", "project-rag-em", "--topic", "test-ignored", "--title", "T"],
            env=env,
            stdin_text="Body.\n",
        )
        if result.returncode == 0:
            fail_test(name, f"dispatcher should exit non-zero when receiver gitignores cross-repo/; got 0. stdout: {result.stdout!r}")
            return
        # Error must mention gitignored / invisible.
        combined = result.stdout + result.stderr
        if "gitignore" not in combined.lower() and "ignored" not in combined.lower():
            fail_test(name, f"error should mention gitignored. stderr: {result.stderr!r}")
            return
        # No file should exist.
        today = datetime.date.today().isoformat()
        inbox_file = os.path.join(receiver_dir, "cross-repo", "inbox", f"{today}-test-ignored.md")
        if os.path.isfile(inbox_file):
            fail_test(name, f"no file should be written on gitignore hard-error; found {inbox_file}")
            return
        pass_test(name)


def test_normal_receiver_proceeds() -> None:
    """B3 Test 19: normal receiver (cross-repo/ NOT in .gitignore) → delivery proceeds."""
    name = "Test 19 (B3) — normal receiver (not gitignored) → delivery proceeds"
    import datetime
    with tempfile.TemporaryDirectory() as tmpdir:
        # .gitignore exists but does NOT ignore cross-repo/.
        receiver_dir = _make_receiver_with_gitignore(tmpdir, "*.log\n*.tmp\n")
        mock_impl_path = os.path.join(tmpdir, "_ml.py")
        escaped = receiver_dir.replace("\\", "\\\\")
        with open(mock_impl_path, "w") as f:
            f.write(textwrap.dedent(f"""\
                #!/usr/bin/env python3
                import sys
                print("{escaped}")
                sys.exit(0)
            """))
        env = {
            **os.environ,
            "MACHINE_LOCAL_IMPL": mock_impl_path,
            "CLAUDE_HOME": tmpdir,
        }
        result = _run_dispatcher(
            ["--to", "project-rag-em", "--topic", "test-normal", "--title", "T"],
            env=env,
            stdin_text="Body.\n",
        )
        if result.returncode != 0:
            fail_test(name, f"dispatcher should succeed for non-ignored receiver; exit {result.returncode}, stderr: {result.stderr!r}")
            return
        inbox_dir = os.path.join(receiver_dir, "cross-repo", "inbox")
        inbox_file = _find_inbox_file(inbox_dir, "test-normal")
        if inbox_file is None:
            fail_test(name, f"expected file not found in {inbox_dir} (pattern *-test-normal.md)")
            return
        pass_test(name)


def test_non_git_receiver_proceeds() -> None:
    """B3/DM5c Test 20: receiver path is NOT a git repo → git check-ignore exits 128 → PROCEED.

    A freshly-registered or non-git receiver cannot gitignore anything; treating
    exit-128 as a block would deny legitimate delivery.
    """
    name = "Test 20 (B3/DM5c) — non-git receiver (exit 128) → delivery proceeds"
    import datetime
    with tempfile.TemporaryDirectory() as tmpdir:
        # A plain directory — no git init → git check-ignore exits 128.
        receiver_dir = os.path.join(tmpdir, "plain_dir")
        os.makedirs(receiver_dir)
        mock_impl_path = os.path.join(tmpdir, "_ml.py")
        escaped = receiver_dir.replace("\\", "\\\\")
        with open(mock_impl_path, "w") as f:
            f.write(textwrap.dedent(f"""\
                #!/usr/bin/env python3
                import sys
                print("{escaped}")
                sys.exit(0)
            """))
        env = {
            **os.environ,
            "MACHINE_LOCAL_IMPL": mock_impl_path,
            "CLAUDE_HOME": tmpdir,
        }
        result = _run_dispatcher(
            ["--to", "project-rag-em", "--topic", "test-nongit", "--title", "T"],
            env=env,
            stdin_text="Body.\n",
        )
        if result.returncode != 0:
            fail_test(name, f"dispatcher should proceed for non-git receiver; exit {result.returncode}, stderr: {result.stderr!r}")
            return
        inbox_dir = os.path.join(receiver_dir, "cross-repo", "inbox")
        inbox_file = _find_inbox_file(inbox_dir, "test-nongit")
        if inbox_file is None:
            fail_test(name, f"expected file not found in {inbox_dir} (pattern *-test-nongit.md)")
            return
        pass_test(name)


def test_no_orphan_dir_on_gitignore_block() -> None:
    """B3/DM5d Test 21: on gitignore hard-error, no empty cross-repo/inbox/ dir is created.

    The ordering constraint (DM2): check BEFORE _write_file's makedirs. An orphaned
    empty inbox/ dir is a half-completed side-effect that should not exist.
    """
    name = "Test 21 (B3/DM5d) — no orphan cross-repo/inbox/ dir on gitignore hard-error"
    with tempfile.TemporaryDirectory() as tmpdir:
        receiver_dir = _make_receiver_with_gitignore(tmpdir, "cross-repo/\n")
        mock_impl_path = os.path.join(tmpdir, "_ml.py")
        escaped = receiver_dir.replace("\\", "\\\\")
        with open(mock_impl_path, "w") as f:
            f.write(textwrap.dedent(f"""\
                #!/usr/bin/env python3
                import sys
                print("{escaped}")
                sys.exit(0)
            """))
        env = {
            **os.environ,
            "MACHINE_LOCAL_IMPL": mock_impl_path,
            "CLAUDE_HOME": tmpdir,
        }
        result = _run_dispatcher(
            ["--to", "project-rag-em", "--topic", "test-orphan", "--title", "T"],
            env=env,
            stdin_text="Body.\n",
        )
        # Should have hard-errored.
        if result.returncode == 0:
            fail_test(name, "dispatcher should have hard-errored on gitignored receiver")
            return
        # Assert no cross-repo/inbox/ directory was created in the receiver.
        inbox_dir = os.path.join(receiver_dir, "cross-repo", "inbox")
        if os.path.isdir(inbox_dir):
            fail_test(name, f"orphan inbox dir should not exist on blocked delivery; found {inbox_dir}")
            return
        pass_test(name)


# ---------------------------------------------------------------------------
# Tests 21-26 (H/D6) — publish-target receiver rejection
#
# Spec backlink: docs/plans/2026-05-23-cross-repo-inbox-archive-restructure.md § H (D6)
#
# Publish-target repos (OSS distribution mirrors) are outward publish.sh
# destinations, not EM working trees. The CLI must reject them at parse time,
# before _resolve_receiver_path runs. The reject message must NAME THE OWNER
# (claude-central-em for coordinator/deep-research) so the EM knows where to
# route the concern — not a generic "did you mean" (2026-06-17 ownership fix).
#
# Override: COORDINATOR_OVERRIDE_PUBLISH_TARGET_RECEIVER=1 bypasses the check.
# ---------------------------------------------------------------------------

def _assert_publish_target_rejected(name: str, to_arg: str) -> bool:
    """Helper: assert --to <to_arg> is rejected as a publish target.

    Returns True on pass (rejection confirmed), False on fail (also calls fail_test).

    C9: MACHINE_LOCAL_IMPL is required so the subprocess's _get_publish_target_owners()
    can enumerate publish.mirrors.* — CLAUDE_HOME alone is not enough (it makes
    _machine_local_impl() resolve to <tmpdir>/bin/_machine_local.py which does not
    exist, so mirror-key enumeration silently returns [] and the rejection guard
    never fires). Schema-derived (C4): mirrors live in publish.mirrors.*, not repos.*.
    """
    with tempfile.TemporaryDirectory() as tmpdir, \
         tempfile.TemporaryDirectory() as impl_tmpdir:
        mock_impl = _make_mock_machine_local_keys_and_get(
            impl_tmpdir,
            {
                "publish.mirrors.coordinator_claude.owner": "claude-central-em",
                "publish.mirrors.deep_research_claude.owner": "claude-central-em",
                # aliases cover legacy short-forms (deep-research, deep-research-em)
                # not derivable from the key name alone.
                "publish.mirrors.deep_research_claude.aliases": "deep-research\ndeep-research-em",
            },
        )
        env = {
            **os.environ,
            "CLAUDE_HOME": tmpdir,
            "MACHINE_LOCAL_IMPL": mock_impl,
        }
        result = _run_dispatcher(
            ["--to", to_arg, "--topic", "test-topic", "--title", "T"],
            env=env,
            stdin_text="Body.\n",
        )
        if result.returncode == 0:
            fail_test(name, f"--to {to_arg!r}: dispatcher should exit non-zero (publish-target rejection); got 0. stdout: {result.stdout!r}")
            return False
        combined = result.stdout + result.stderr
        if "publish-target" not in combined.lower():
            fail_test(name, f"--to {to_arg!r}: error should mention 'publish-target'. stderr: {result.stderr!r}")
            return False
        if "owned by" not in combined.lower():
            fail_test(name, f"--to {to_arg!r}: error should NAME the owner ('owned by ...'). stderr: {result.stderr!r}")
            return False
        if "claude-central-em" not in combined:
            fail_test(name, f"--to {to_arg!r}: error should name owner 'claude-central-em'. stderr: {result.stderr!r}")
            return False
        return True


def test_publish_target_coordinator_claude_em_rejected() -> None:
    """H Test 21: --to coordinator-claude-em is rejected with publish-target message."""
    name = "Test 21 (H/D6) — --to coordinator-claude-em rejected as publish target"
    if _assert_publish_target_rejected(name, "coordinator-claude-em"):
        pass_test(name)


def test_publish_target_coordinator_claude_shortname_rejected() -> None:
    """H Test 22: --to coordinator-claude (bare shortname) is rejected."""
    name = "Test 22 (H/D6) — --to coordinator-claude (shortname) rejected as publish target"
    if _assert_publish_target_rejected(name, "coordinator-claude"):
        pass_test(name)


def test_publish_target_deep_research_em_rejected() -> None:
    """H Test 23: --to deep-research-claude-em is rejected with publish-target message."""
    name = "Test 23 (H/D6) — --to deep-research-claude-em rejected as publish target"
    if _assert_publish_target_rejected(name, "deep-research-claude-em"):
        pass_test(name)


def test_publish_target_override_bypasses_check() -> None:
    """H Test 24: COORDINATOR_OVERRIDE_PUBLISH_TARGET_RECEIVER=1 bypasses the publish-target check.

    The override disables only the publish-target gate. Downstream _resolve_receiver_path
    may still fail (e.g. coordinator-claude is not in machine-local registry). The test
    asserts the publish-target rejection is bypassed by confirming the publish-target
    message does NOT appear in stderr — regardless of what happens downstream.
    """
    name = "Test 24 (H/D6) — COORDINATOR_OVERRIDE_PUBLISH_TARGET_RECEIVER=1 bypasses publish-target check"
    with tempfile.TemporaryDirectory() as tmpdir:
        # Machine-local absent so downstream _resolve_receiver_path fails, but
        # the publish-target check must be bypassed before we reach that point.
        mock_impl = _make_mock_machine_local_key_absent(tmpdir)
        env = {
            **os.environ,
            "COORDINATOR_OVERRIDE_PUBLISH_TARGET_RECEIVER": "1",
            "MACHINE_LOCAL_IMPL": mock_impl,
            "CLAUDE_HOME": tmpdir,
        }
        result = _run_dispatcher(
            ["--to", "coordinator-claude-em", "--topic", "test-override", "--title", "T"],
            env=env,
            stdin_text="Body.\n",
        )
        # Confirm the publish-target rejection message did NOT appear.
        combined = result.stdout + result.stderr
        if "publish target" in combined.lower():
            fail_test(name, f"publish-target rejection should be bypassed with override; got: {result.stderr!r}")
            return
        # The call may fail downstream (registry absent) — that is expected.
        # The important assertion: no publish-target message means the gate was bypassed.
        pass_test(name)


def test_publish_target_case_whitespace_normalization() -> None:
    """H Test 25: case/whitespace normalisation — mixed-case and padded forms are rejected.

    _is_publish_target_em uses .strip().lower() just like _is_central_receiver.

    Review: code-reviewer (F1) — converted to subprocess+MACHINE_LOCAL_IMPL mock pattern
    so the test is machine-independent. Previously called _load_dispatcher_module() without
    setting MACHINE_LOCAL_IMPL, causing _machine_local_mirror_keys() to hit the real
    registry — on a fresh machine with no publish.mirrors.* set, the test silently failed.
    """
    name = "Test 25 (H/D6) — case/whitespace normalisation: mixed-case and padded publish targets rejected"
    with tempfile.TemporaryDirectory() as tmpdir, \
         tempfile.TemporaryDirectory() as impl_tmpdir:
        mock_impl = _make_mock_machine_local_keys_and_get(
            impl_tmpdir,
            {
                "publish.mirrors.coordinator_claude.owner": "claude-central-em",
                "publish.mirrors.deep_research_claude.owner": "claude-central-em",
                "publish.mirrors.deep_research_claude.aliases": "deep-research\ndeep-research-em",
            },
        )
        old_impl = os.environ.get("MACHINE_LOCAL_IMPL")
        old_home = os.environ.get("CLAUDE_HOME")
        try:
            os.environ["MACHINE_LOCAL_IMPL"] = mock_impl
            os.environ["CLAUDE_HOME"] = tmpdir
            mod = _load_dispatcher_module()
            cases = [
                "Coordinator-Claude-EM",    # mixed case
                "  coordinator-claude  ",   # leading/trailing whitespace
                "DEEP-RESEARCH-CLAUDE-EM",  # all-caps
                "Coordinator-Claude",       # bare name, mixed case
            ]
            for s in cases:
                if not mod._is_publish_target_em(s):
                    fail_test(name, f"_is_publish_target_em({s!r}) returned False; expected True")
                    return
            # Negative: canonical EM receivers must NOT be matched.
            non_targets = ["project-rag-em", "example-game-repo-em", "claude-central-em", "example-sim-repo-em", ""]
            for s in non_targets:
                if mod._is_publish_target_em(s):
                    fail_test(name, f"_is_publish_target_em({s!r}) returned True; expected False")
                    return
            pass_test(name)
        finally:
            if old_impl is None:
                os.environ.pop("MACHINE_LOCAL_IMPL", None)
            else:
                os.environ["MACHINE_LOCAL_IMPL"] = old_impl
            if old_home is None:
                os.environ.pop("CLAUDE_HOME", None)
            else:
                os.environ["CLAUDE_HOME"] = old_home


def test_canonical_receivers_not_rejected_by_publish_target_check() -> None:
    """H Test 26: canonical EM receivers (project-rag-em, example-game-repo-em, claude-central-em)
    proceed past the publish-target check — no spurious rejection.

    Uses the pure function directly; downstream behaviour (registry lookup) is not
    under test here.

    Review: code-reviewer (F1) — converted to subprocess+MACHINE_LOCAL_IMPL mock pattern
    so the test is machine-independent. Previously called _load_dispatcher_module() without
    MACHINE_LOCAL_IMPL, causing _machine_local_mirror_keys() to hit the real registry.
    On a fresh machine the cache was {} and the test passed for the wrong reason (empty
    map means nothing is rejected, which vacuously satisfies the negative assertion).
    With the mock, coordinator_claude and deep_research_claude ARE registered, so the test
    now proves the positive case (mirrors present) and the negative case (real siblings not
    in the mirror map) simultaneously.
    """
    name = "Test 26 (H/D6) — canonical EM receivers NOT rejected by publish-target check"
    with tempfile.TemporaryDirectory() as tmpdir, \
         tempfile.TemporaryDirectory() as impl_tmpdir:
        mock_impl = _make_mock_machine_local_keys_and_get(
            impl_tmpdir,
            {
                "publish.mirrors.coordinator_claude.owner": "claude-central-em",
                "publish.mirrors.deep_research_claude.owner": "claude-central-em",
                "publish.mirrors.deep_research_claude.aliases": "deep-research\ndeep-research-em",
            },
        )
        old_impl = os.environ.get("MACHINE_LOCAL_IMPL")
        old_home = os.environ.get("CLAUDE_HOME")
        try:
            os.environ["MACHINE_LOCAL_IMPL"] = mock_impl
            os.environ["CLAUDE_HOME"] = tmpdir
            mod = _load_dispatcher_module()
            canonical_receivers = [
                "project-rag-em",
                "project-rag-ue-addon-em",
                "example-game-repo-em",
                "claude-central-em",
                "central-em",
                "central",
                "example-sim-repo-em",
                "example-repo-em",
            ]
            for receiver in canonical_receivers:
                if mod._is_publish_target_em(receiver):
                    fail_test(name, f"_is_publish_target_em({receiver!r}) returned True; canonical receiver should NOT be rejected")
                    return
            pass_test(name)
        finally:
            if old_impl is None:
                os.environ.pop("MACHINE_LOCAL_IMPL", None)
            else:
                os.environ["MACHINE_LOCAL_IMPL"] = old_impl
            if old_home is None:
                os.environ.pop("CLAUDE_HOME", None)
            else:
                os.environ["CLAUDE_HOME"] = old_home


# ---------------------------------------------------------------------------
# Tests 27-30 — summary field (Chunk 4: producer template updates)
#
# Spec backlink: docs/plans/2026-05-29-handoff-schema-category-summary.md § Chunk 4
#
# Key assertions:
#   - Test 27: summary is emitted in frontmatter when --summary is provided
#   - Test 28: summary is derived from first body line when --summary is omitted
#   - Test 29: a >120-char --summary is truncated to ≤120 chars at compose time
#   - Test 30: a >120-char body-derived summary is also truncated to ≤120 chars
# ---------------------------------------------------------------------------

def test_summary_emitted_when_provided() -> None:
    """Test 27: --summary is written to the summary: frontmatter field."""
    name = "Test 27 — summary: field emitted when --summary is provided"
    mod = _load_dispatcher_module()

    body = "This is the memo body.\n"
    explicit_summary = "Explicit one-line tl;dr for this memo"

    fm_text = mod._compose_frontmatter(
        title="Test Memo",
        to="project-rag-em",
        topic="test-topic",
        body=body,
        summary=explicit_summary,
    )
    fm = _parse_frontmatter(fm_text + "\n# no body\n")  # wrap so parser sees ---...---
    if fm.get("summary") != explicit_summary:
        fail_test(name, f"summary should be {explicit_summary!r}, got: {fm.get('summary')!r}")
        return
    pass_test(name)


def test_summary_derived_from_body_when_omitted() -> None:
    """Test 28: when --summary is omitted, summary is derived from the first non-empty body line."""
    name = "Test 28 — summary: derived from first body line when --summary omitted"
    mod = _load_dispatcher_module()

    body = "\nFirst real line of the body.\n\nSecond line.\n"

    fm_text = mod._compose_frontmatter(
        title="Test Memo",
        to="project-rag-em",
        topic="test-topic",
        body=body,
        summary=None,
    )
    fm = _parse_frontmatter(fm_text + "\n# no body\n")
    expected = "First real line of the body."
    if fm.get("summary") != expected:
        fail_test(name, f"summary should be {expected!r} (derived), got: {fm.get('summary')!r}")
        return
    pass_test(name)


def test_summary_truncated_when_over_120_chars() -> None:
    """Test 29: a >120-char explicit --summary is truncated to ≤120 chars at compose time."""
    name = "Test 29 — summary truncated to ≤120 chars when explicit --summary > 120"
    mod = _load_dispatcher_module()

    # 130 chars — well over the cap.
    long_summary = "A" * 130

    fm_text = mod._compose_frontmatter(
        title="Test Memo",
        to="project-rag-em",
        topic="test-topic",
        body="Body.\n",
        summary=long_summary,
    )
    fm = _parse_frontmatter(fm_text + "\n# no body\n")
    got_summary = fm.get("summary", "")
    if len(got_summary) > mod._SUMMARY_MAX_CHARS:
        fail_test(
            name,
            f"summary length {len(got_summary)} exceeds _SUMMARY_MAX_CHARS "
            f"({mod._SUMMARY_MAX_CHARS}); summary: {got_summary!r}",
        )
        return
    # Confirm it was actually truncated (not the original value).
    if got_summary == long_summary:
        fail_test(name, "summary was not truncated — still equals the original long value")
        return
    pass_test(name)


def test_body_derived_summary_truncated_when_over_120_chars() -> None:
    """Test 30: a body first-line that is >120 chars is also truncated to ≤120 when derived."""
    name = "Test 30 — body-derived summary truncated to ≤120 chars when first line > 120"
    mod = _load_dispatcher_module()

    # First body line is 150 chars.
    long_first_line = "B" * 150
    body = long_first_line + "\nSecond line.\n"

    fm_text = mod._compose_frontmatter(
        title="Test Memo",
        to="project-rag-em",
        topic="test-topic",
        body=body,
        summary=None,
    )
    fm = _parse_frontmatter(fm_text + "\n# no body\n")
    got_summary = fm.get("summary", "")
    if len(got_summary) > mod._SUMMARY_MAX_CHARS:
        fail_test(
            name,
            f"body-derived summary length {len(got_summary)} exceeds _SUMMARY_MAX_CHARS "
            f"({mod._SUMMARY_MAX_CHARS}); summary: {got_summary!r}",
        )
        return
    if got_summary == long_first_line:
        fail_test(name, "body-derived summary was not truncated — still equals the original long first line")
        return
    pass_test(name)


# ---------------------------------------------------------------------------
# Tests 31-35 (C2) — --kind flag: enum round-trip, absent-is-no-line, invalid rejected
#
# Spec backlink: docs/plans/2026-05-30-pickup-cross-repo-memo-fork.md § C2
#
# Key assertions:
#   - Each of ask/consult/fyi round-trips into `kind: <value>` in composed frontmatter.
#   - Omitting --kind produces NO `kind:` line at all (absence is meaningful).
#   - An invalid --kind value is rejected by argparse (exit 2, choices validation).
# ---------------------------------------------------------------------------

def test_kind_ask_round_trips() -> None:
    """Test 31 (C2): --kind ask emits kind: ask in frontmatter."""
    name = "Test 31 (C2) — --kind ask round-trips into kind: ask in frontmatter"
    mod = _load_dispatcher_module()

    fm_text = mod._compose_frontmatter(
        title="Test Memo",
        to="project-rag-em",
        topic="test-kind",
        body="Body.\n",
        kind="ask",
    )
    fm = _parse_frontmatter(fm_text + "\n# no body\n")
    if fm.get("kind") != "ask":
        fail_test(name, f"kind should be 'ask', got: {fm.get('kind')!r}. frontmatter:\n{fm_text}")
        return
    pass_test(name)


def test_kind_consult_round_trips() -> None:
    """Test 32 (C2): --kind consult emits kind: consult in frontmatter."""
    name = "Test 32 (C2) — --kind consult round-trips into kind: consult in frontmatter"
    mod = _load_dispatcher_module()

    fm_text = mod._compose_frontmatter(
        title="Test Memo",
        to="project-rag-em",
        topic="test-kind",
        body="Body.\n",
        kind="consult",
    )
    fm = _parse_frontmatter(fm_text + "\n# no body\n")
    if fm.get("kind") != "consult":
        fail_test(name, f"kind should be 'consult', got: {fm.get('kind')!r}. frontmatter:\n{fm_text}")
        return
    pass_test(name)


def test_kind_fyi_round_trips() -> None:
    """Test 33 (C2): --kind fyi emits kind: fyi in frontmatter."""
    name = "Test 33 (C2) — --kind fyi round-trips into kind: fyi in frontmatter"
    mod = _load_dispatcher_module()

    fm_text = mod._compose_frontmatter(
        title="Test Memo",
        to="project-rag-em",
        topic="test-kind",
        body="Body.\n",
        kind="fyi",
    )
    fm = _parse_frontmatter(fm_text + "\n# no body\n")
    if fm.get("kind") != "fyi":
        fail_test(name, f"kind should be 'fyi', got: {fm.get('kind')!r}. frontmatter:\n{fm_text}")
        return
    pass_test(name)


def test_kind_proposal_round_trips() -> None:
    """Test 33b (C2): --kind proposal emits kind: proposal in frontmatter.

    proposal is action-requiring (urgent band) — sender presents a concrete change +
    recommendation; receiver decides adoption. Added per contract Deliverable D.
    """
    name = "Test 33b (C2) — --kind proposal round-trips into kind: proposal in frontmatter"
    mod = _load_dispatcher_module()

    fm_text = mod._compose_frontmatter(
        title="Test Memo",
        to="project-rag-em",
        topic="test-kind",
        body="Body.\n",
        kind="proposal",
    )
    fm = _parse_frontmatter(fm_text + "\n# no body\n")
    if fm.get("kind") != "proposal":
        fail_test(name, f"kind should be 'proposal', got: {fm.get('kind')!r}. frontmatter:\n{fm_text}")
        return
    pass_test(name)


def test_kind_omitted_produces_no_kind_line() -> None:
    """Test 34 (C2): omitting kind=None emits NO kind: line — absence is meaningful.

    The reader applies an 'ask' default for unlabelled memos. The CLI must NOT
    stamp a default — absence must be preserved so back-compat memos are treated
    as ask without being retroactively rewritten.
    """
    name = "Test 34 (C2) — omitting --kind produces NO kind: line in frontmatter"
    mod = _load_dispatcher_module()

    fm_text = mod._compose_frontmatter(
        title="Test Memo",
        to="project-rag-em",
        topic="test-kind",
        body="Body.\n",
        kind=None,
    )
    fm = _parse_frontmatter(fm_text + "\n# no body\n")
    if "kind" in fm:
        fail_test(
            name,
            f"kind: line should NOT be emitted when kind=None; got kind={fm['kind']!r}. "
            f"frontmatter:\n{fm_text}",
        )
        return
    # Also verify the raw text contains no `kind:` at all.
    if "\nkind:" in fm_text:
        fail_test(
            name,
            f"Raw frontmatter text contains 'kind:' line despite kind=None:\n{fm_text}",
        )
        return
    pass_test(name)


def test_kind_invalid_value_rejected() -> None:
    """Test 35 (C2): an invalid --kind value (e.g. 'ack') is rejected by argparse → exit 2.

    argparse choices=["ask","consult","fyi","proposal"] enforces the enum at parse time.
    'ack' is explicitly not a valid kind (it is receipt-state, not sender-declared shape).
    """
    name = "Test 35 (C2) — invalid --kind value is rejected by argparse (exit 2)"
    with tempfile.TemporaryDirectory() as tmpdir:
        env = {**os.environ, "CLAUDE_HOME": tmpdir}
        result = _run_dispatcher(
            [
                "--to", "project-rag-em",
                "--topic", "test-kind",
                "--title", "Test",
                "--kind", "ack",  # 'ack' is NOT a valid kind — receipt-state only
            ],
            env=env,
            stdin_text="Body.\n",
        )
        if result.returncode != 2:
            fail_test(
                name,
                f"expected exit code 2 (argparse choices rejection); got {result.returncode}. "
                f"stderr: {result.stderr!r}",
            )
            return
        # argparse emits an error mentioning the invalid choice.
        if "invalid choice" not in result.stderr.lower() and "choose from" not in result.stderr.lower():
            fail_test(
                name,
                f"argparse error message about invalid choice not found in stderr: {result.stderr!r}",
            )
            return
        pass_test(name)


def _base_valid_draft_fm() -> dict[str, str]:
    """Minimal well-formed outbox draft frontmatter dict.

    Satisfies every key in _OUTBOX_REQUIRED_FIELDS so _validate_outbox_frontmatter
    returns no non-kind errors; tests vary only the `kind` key on top of this base.
    """
    return {
        "title": "Test Memo",
        "from": "project-rag-em",
        "to": "claude-central-em",
        "created": "2026-07-10T00:00:00Z",
        "status": "draft",
        "delivery_mode": "receiver-repo",
        "summary": "A test summary.",
    }


def test_send_side_kind_validation_rejects_invalid_value() -> None:
    """Test 35b (send-side guard): _validate_outbox_frontmatter rejects kind: reply.

    Spec: sender-side pre-flight for a hand-authored/compose-edited outbox file
    that bypasses the `draft --kind` argparse choices guard (which only fires
    when --kind is passed on that exact command). A malformed kind must fail
    loud at `send` time, before delivery — not at the receiver's stamp time.
    """
    name = "Test 35b — _validate_outbox_frontmatter rejects kind: reply"
    mod = _load_dispatcher_module()

    fm = _base_valid_draft_fm()
    fm["kind"] = "reply"
    errors = mod._validate_outbox_frontmatter(fm)
    kind_errors = [e for e in errors if "kind" in e.lower()]
    if not kind_errors:
        fail_test(name, f"expected a kind-related error for kind='reply'; got errors: {errors!r}")
        return
    pass_test(name)


def test_send_side_kind_validation_allows_absent_kind() -> None:
    """Test 35c (send-side guard): kind key omitted entirely is valid (no error)."""
    name = "Test 35c — _validate_outbox_frontmatter allows absent kind"
    mod = _load_dispatcher_module()

    fm = _base_valid_draft_fm()
    assert "kind" not in fm
    errors = mod._validate_outbox_frontmatter(fm)
    kind_errors = [e for e in errors if "kind" in e.lower()]
    if kind_errors:
        fail_test(name, f"expected no kind-related error when kind is absent; got: {kind_errors!r}")
        return
    pass_test(name)


def test_send_side_kind_validation_allows_each_valid_kind() -> None:
    """Test 35d (send-side guard): each canonical kind value passes with no kind error."""
    name = "Test 35d — _validate_outbox_frontmatter allows each valid kind (ask/consult/fyi/proposal)"
    mod = _load_dispatcher_module()

    for valid_kind in ("ask", "consult", "fyi", "proposal"):
        fm = _base_valid_draft_fm()
        fm["kind"] = valid_kind
        errors = mod._validate_outbox_frontmatter(fm)
        kind_errors = [e for e in errors if "kind" in e.lower()]
        if kind_errors:
            fail_test(
                name,
                f"expected no kind-related error for kind={valid_kind!r}; got: {kind_errors!r}",
            )
            return
    pass_test(name)


# ---------------------------------------------------------------------------
# Tests 36-40 — --list-receivers discovery surface + publish-target asymmetry guard
#
# Doctrine: docs/wiki/cross-repo-communication.md § CLI (Discovering valid receivers).
#
# Regression target: an EM enumerating receivers via `machine-local keys` sees
# only repos.* siblings and concludes claude-central-em is not a valid target,
# then hand-authors into ~/.claude/cross-repo/inbox/. --list-receivers is the
# enumerator that ALWAYS includes central, decoupled from the registry.
# ---------------------------------------------------------------------------

def _make_mock_machine_local_keys_and_get(tmpdir: str, key_paths: dict) -> str:
    """Stub machine-local where `keys` lists keys and `get <key>` resolves a path.

    Unlike _make_mock_machine_local_subcommand_aware (get always fails), this
    resolves get so --list-receivers can render the sibling path column.
    """
    stub_path = os.path.join(tmpdir, "_mock_ml_keys_get.py")
    kp_repr = repr(key_paths)
    script = textwrap.dedent(f"""\
        #!/usr/bin/env python3
        import sys
        kp = {kp_repr}
        argv = sys.argv[1:]
        if argv and argv[0] == "keys":
            for k in kp:
                print(k)
            sys.exit(0)
        if len(argv) == 2 and argv[0] == "get" and argv[1] in kp:
            print(kp[argv[1]])
            sys.exit(0)
        print("machine-local: key not found", file=sys.stderr)
        sys.exit(1)
    """)
    with open(stub_path, "w") as f:
        f.write(script)
    return stub_path


def test_list_receivers_includes_central() -> None:
    name = "Test 36 — --list-receivers names claude-central-em even with siblings registered"
    with tempfile.TemporaryDirectory() as claude_home_tmpdir, \
         tempfile.TemporaryDirectory() as impl_tmpdir:
        mock_impl = _make_mock_machine_local_keys_and_get(
            impl_tmpdir,
            {"repos.project_rag": "/work/project-rag",
             "repos.example_game_workbench_repo": "/work/example-game-workbench-repo"},
        )
        env = {**os.environ, "MACHINE_LOCAL_IMPL": mock_impl, "CLAUDE_HOME": claude_home_tmpdir}
        # No --to/--topic/--title — discovery mode must not require them.
        result = _run_dispatcher(["--list-receivers"], env=env, stdin_text="")
        if result.returncode != 0:
            fail_test(name, f"--list-receivers should exit 0; got {result.returncode}. stderr: {result.stderr!r}")
            return
        if "claude-central-em" not in result.stdout:
            fail_test(name, f"central must be listed. stdout: {result.stdout!r}")
            return
        pass_test(name)


def test_list_receivers_lists_registered_siblings() -> None:
    name = "Test 37 — --list-receivers lists registered siblings (incl. alias reversal)"
    with tempfile.TemporaryDirectory() as claude_home_tmpdir, \
         tempfile.TemporaryDirectory() as impl_tmpdir:
        mock_impl = _make_mock_machine_local_keys_and_get(
            impl_tmpdir,
            {"repos.project_rag": "/work/project-rag",
             "repos.example_game_workbench_repo": "/work/example-game-workbench-repo"},
        )
        env = {**os.environ, "MACHINE_LOCAL_IMPL": mock_impl, "CLAUDE_HOME": claude_home_tmpdir}
        result = _run_dispatcher(["--list-receivers"], env=env, stdin_text="")
        if result.returncode != 0:
            fail_test(name, f"--list-receivers should exit 0; got {result.returncode}. stderr: {result.stderr!r}")
            return
        if "project-rag-em" not in result.stdout:
            fail_test(name, f"sibling project-rag-em must be listed. stdout: {result.stdout!r}")
            return
        if "example-game-repo-em" not in result.stdout:
            fail_test(name, f"alias must reverse to example-game-repo-em. stdout: {result.stdout!r}")
            return
        if "/work/project-rag" not in result.stdout:
            fail_test(name, f"resolved sibling path must be shown. stdout: {result.stdout!r}")
            return
        pass_test(name)


def test_list_receivers_shows_mirror_owners() -> None:
    name = "Test 38 — --list-receivers shows publish-target mirrors WITH their owner (deep-research-claude-em incl.)"
    with tempfile.TemporaryDirectory() as claude_home_tmpdir, \
         tempfile.TemporaryDirectory() as impl_tmpdir:
        # C9 (C4 schema-derived): mirrors live in publish.mirrors.* — NOT repos.*.
        # coordinator_claude produces coordinator-claude-em; deep_research_claude
        # produces deep-research-claude-em (+ legacy aliases via .aliases field).
        # repos.project_rag is the only real sibling in this fixture.
        mock_impl = _make_mock_machine_local_keys_and_get(
            impl_tmpdir,
            {
                "repos.project_rag": "/work/project-rag",
                "publish.mirrors.coordinator_claude.owner": "claude-central-em",
                "publish.mirrors.deep_research_claude.owner": "claude-central-em",
                "publish.mirrors.deep_research_claude.aliases": "deep-research\ndeep-research-em",
            },
        )
        env = {**os.environ, "MACHINE_LOCAL_IMPL": mock_impl, "CLAUDE_HOME": claude_home_tmpdir}
        result = _run_dispatcher(["--list-receivers"], env=env, stdin_text="")
        if result.returncode != 0:
            fail_test(name, f"--list-receivers should exit 0; got {result.returncode}. stderr: {result.stderr!r}")
            return
        # DELIBERATE FORMAT COUPLING: mirror rows use the OWNER format
        # "    {em_id}   → owned by {owner}" while sibling rows use
        # "    {em_id}   → {path}". The distinction is the 'owned by' token. If the
        # row format changes, update both sites (mirror_rows template lives in
        # _format_receiver_listing in the CLI).
        if "    coordinator-claude-em   → owned by claude-central-em" not in result.stdout:
            fail_test(name, f"coordinator-claude-em should be listed as a mirror owned by claude-central-em. stdout: {result.stdout!r}")
            return
        # C9: mirror key deep_research_claude → canonical listing form is
        # deep-research-claude-em (the <hyphenated-key>-em pair). Legacy short-forms
        # (deep-research-em) live in the .aliases field but are not expanded in
        # the listing; they ARE rejected by the publish-target guard (Test 39).
        if "    deep-research-claude-em   → owned by claude-central-em" not in result.stdout:
            fail_test(name, f"deep-research-claude-em should be listed as a mirror owned by claude-central-em. stdout: {result.stdout!r}")
            return
        # Mirrors must NOT appear as plain sibling path-rows (→ /work/...).
        if "    deep-research-claude-em   → /work/" in result.stdout:
            fail_test(name, f"deep-research-claude-em must not be a plain sibling path row (it is a mirror). stdout: {result.stdout!r}")
            return
        if "    project-rag-em   → /work/project-rag" not in result.stdout:
            fail_test(name, f"real sibling project-rag-em should still be listed with its path. stdout: {result.stdout!r}")
            return
        pass_test(name)


def test_deep_research_em_rejected_as_publish_target() -> None:
    name = "Test 39 — --to deep-research-em rejected, error names the owner (asymmetry guard)"
    with tempfile.TemporaryDirectory() as claude_home_tmpdir, \
         tempfile.TemporaryDirectory() as impl_tmpdir:
        # C9 (C4 schema-derived): deep_research_claude mirror key with .aliases
        # makes deep-research-em (a non-derivable legacy short-form) a recognised
        # publish target. Old fixture used repos.deep_research which caused the CLI
        # to attempt delivery to /work (read-only) instead of rejecting it.
        mock_impl = _make_mock_machine_local_keys_and_get(
            impl_tmpdir,
            {
                "publish.mirrors.deep_research_claude.owner": "claude-central-em",
                "publish.mirrors.deep_research_claude.aliases": "deep-research\ndeep-research-em",
            },
        )
        env = {**os.environ, "MACHINE_LOCAL_IMPL": mock_impl, "CLAUDE_HOME": claude_home_tmpdir}
        result = _run_dispatcher(
            ["--to", "deep-research-em", "--topic", "t", "--title", "T"],
            env=env, stdin_text="Body.\n",
        )
        if result.returncode != 1:
            fail_test(name, f"expected exit 1 (publish-target rejection); got {result.returncode}. stderr: {result.stderr!r}")
            return
        if "publish-target" not in result.stderr.lower():
            fail_test(name, f"error should name the publish-target reason. stderr: {result.stderr!r}")
            return
        if "owned by `claude-central-em`" not in result.stderr:
            fail_test(name, f"error should NAME the owner claude-central-em. stderr: {result.stderr!r}")
            return
        pass_test(name)


def test_deep_research_bare_alias_rejected_as_publish_target() -> None:
    """Test 39c — --to deep-research (bare legacy alias, no -em suffix) is rejected.

    AC4 names all 6 aliases including the legacy bare 'deep-research'. This alias is
    stored in publish.mirrors.deep_research_claude.aliases (not derivable from the key
    name alone). The test uses the subprocess send-path to prove the rejection guard
    fires at the CLI level, not just in the pure function.

    Review: code-reviewer (F2) — AC4 send-path coverage gap: bare 'deep-research'
    was unexercised on the subprocess send-path. Mirrored from T39 which covers
    'deep-research-em'; this test covers the bare form.
    """
    name = "Test 39c (F2) — --to deep-research (bare legacy alias) rejected as publish target"
    if _assert_publish_target_rejected(name, "deep-research"):
        pass_test(name)


def test_publish_target_owner_resolves() -> None:
    """Test 39b — _publish_target_owner maps each mirror identity to claude-central-em.

    Review: code-reviewer (F1) — converted to subprocess+MACHINE_LOCAL_IMPL mock pattern
    so the test is machine-independent. Previously called _load_dispatcher_module() without
    MACHINE_LOCAL_IMPL — on a fresh machine _publish_target_owner returned None for all
    inputs (cache empty), silently failing the assertion.
    """
    name = "Test 39b — _publish_target_owner resolves mirror → owning EM"
    with tempfile.TemporaryDirectory() as tmpdir, \
         tempfile.TemporaryDirectory() as impl_tmpdir:
        mock_impl = _make_mock_machine_local_keys_and_get(
            impl_tmpdir,
            {
                "publish.mirrors.coordinator_claude.owner": "claude-central-em",
                "publish.mirrors.deep_research_claude.owner": "claude-central-em",
                "publish.mirrors.deep_research_claude.aliases": "deep-research\ndeep-research-em",
            },
        )
        old_impl = os.environ.get("MACHINE_LOCAL_IMPL")
        old_home = os.environ.get("CLAUDE_HOME")
        try:
            os.environ["MACHINE_LOCAL_IMPL"] = mock_impl
            os.environ["CLAUDE_HOME"] = tmpdir
            mod = _load_dispatcher_module()
            for mirror in [
                "coordinator-claude-em", "coordinator-claude",
                "deep-research-claude-em", "deep-research-claude",
                "deep-research-em", "deep-research",
                # case/whitespace normalisation — cover BOTH families so a one-sided
                # normalisation drift (the F1 divergence scenario) is caught here too.
                "  DEEP-RESEARCH-EM  ", "Coordinator-Claude-EM", "  coordinator-claude  ",
            ]:
                owner = mod._publish_target_owner(mirror)
                if owner != "claude-central-em":
                    fail_test(name, f"_publish_target_owner({mirror!r}) = {owner!r}; expected 'claude-central-em'")
                    return
            # Non-mirror identities resolve to None.
            for non_mirror in ["project-rag-em", "example-game-repo-em", "claude-central-em", ""]:
                if mod._publish_target_owner(non_mirror) is not None:
                    fail_test(name, f"_publish_target_owner({non_mirror!r}) should be None")
                    return
            pass_test(name)
        finally:
            if old_impl is None:
                os.environ.pop("MACHINE_LOCAL_IMPL", None)
            else:
                os.environ["MACHINE_LOCAL_IMPL"] = old_impl
            if old_home is None:
                os.environ.pop("CLAUDE_HOME", None)
            else:
                os.environ["CLAUDE_HOME"] = old_home


def test_body_file_dash_reads_stdin() -> None:
    """--body-file - is the Unix stdin sentinel; body must be read from stdin, not from a file named '-'.

    Regression for: cross-repo-memo --body-file - failing with
    'cannot read body file: [Errno 2] No such file or directory: '-''.
    """
    name = "Test 41 — --body-file - reads body from stdin (Unix sentinel)"
    import datetime

    with tempfile.TemporaryDirectory() as receiver_tmpdir, \
         tempfile.TemporaryDirectory() as claude_home_tmpdir:

        mock_impl = _make_mock_machine_local(receiver_tmpdir, receiver_tmpdir)

        env = {
            **os.environ,
            "MACHINE_LOCAL_IMPL": mock_impl,
            "CLAUDE_HOME": claude_home_tmpdir,
        }

        result = _run_dispatcher(
            ["--to", "project-rag-em", "--topic", "test-dash-stdin", "--title", "Dash Sentinel",
             "--body-file", "-"],
            env=env,
            stdin_text="Body via dash sentinel.\n",
        )

        if result.returncode != 0:
            fail_test(name, f"dispatcher exited {result.returncode}: {result.stderr}")
            return

        # Receiver filename is now <date>-<from>-<topic>.md; locate by topic suffix.
        inbox_dir = os.path.join(receiver_tmpdir, "cross-repo", "inbox")
        receiver_file = _find_inbox_file(inbox_dir, "test-dash-stdin")
        if receiver_file is None:
            fail_test(name, f"receiver-side file not found in {inbox_dir} (pattern *-test-dash-stdin.md)")
            return

        with open(receiver_file) as f:
            content = f.read()

        if "Body via dash sentinel" not in content:
            fail_test(name, f"memo body should contain 'Body via dash sentinel'; got: {content!r}")
            return

        pass_test(name)


def test_missing_send_args_points_at_list_receivers() -> None:
    name = "Test 40 — missing --to (no --list-receivers) → exit 2, points at --list-receivers"
    with tempfile.TemporaryDirectory() as claude_home_tmpdir:
        env = {**os.environ, "CLAUDE_HOME": claude_home_tmpdir}
        # --topic/--title present but --to absent: conditional-required enforcement.
        result = _run_dispatcher(["--topic", "t", "--title", "T"], env=env, stdin_text="Body.\n")
        if result.returncode != 2:
            fail_test(name, f"expected exit 2 for missing --to; got {result.returncode}. stderr: {result.stderr!r}")
            return
        if "--list-receivers" not in result.stderr:
            fail_test(name, f"error should point at --list-receivers. stderr: {result.stderr!r}")
            return
        pass_test(name)


# ---------------------------------------------------------------------------
# Tests 42-44 — central receiver delivers to DoE-claude (repos.doe_claude)
#
# Post-migration: central delivery target is the DoE-claude repo (repos.doe_claude),
# NOT ~/.claude. There is no dual-delivery — ONE file lands in DoE-claude's inbox.
#
#   Test 42: central legacy-flag path — delivers to DoE-claude, not ~/.claude
#   Test 42b: central subcommand send path — delivers to DoE-claude, not ~/.claude
#   Test 43: hard-error when repos.doe_claude absent (legacy --to flag path)
#   Test 43b: hard-error when repos.doe_claude absent (subcommand send path)
#   Test 44: non-central send — delivers to sibling repo, not DoE-claude
# ---------------------------------------------------------------------------

def test_central_delivers_to_doe_claude() -> None:
    """Test 42 — central legacy-flag path: memo delivered to DoE-claude repo, NOT ~/.claude."""
    name = "Test 42 — central delivery (legacy --to flag): delivers to DoE-claude repo only"
    import datetime

    with tempfile.TemporaryDirectory() as claude_home_tmpdir, \
         tempfile.TemporaryDirectory() as doe_tmpdir, \
         tempfile.TemporaryDirectory() as impl_tmpdir:

        mock_impl = _make_mock_machine_local_keys_and_get(
            impl_tmpdir,
            {"repos.doe_claude": doe_tmpdir},
        )
        env = {
            **os.environ,
            "MACHINE_LOCAL_IMPL": mock_impl,
            "CLAUDE_HOME": claude_home_tmpdir,
        }
        result = _run_dispatcher(
            ["--to", "claude-central-em", "--topic", "doe-delivery-test", "--title", "DoE Delivery Test"],
            env=env,
            stdin_text="Body for DoE delivery test.\n",
        )
        if result.returncode != 0:
            fail_test(name, f"dispatcher exited {result.returncode}: {result.stderr}")
            return

        # Receiver filename is now <date>-<from>-<topic>.md; locate by topic suffix.
        doe_inbox = os.path.join(doe_tmpdir, "cross-repo", "inbox")
        doe_file = _find_inbox_file(doe_inbox, "doe-delivery-test")
        if doe_file is None:
            fail_test(name, f"DoE file not found in {doe_inbox}. stdout: {result.stdout!r}")
            return

        # Must NOT land in ~/.claude.
        claude_home_inbox = os.path.join(claude_home_tmpdir, "cross-repo", "inbox")
        claude_home_file = _find_inbox_file(claude_home_inbox, "doe-delivery-test") if os.path.isdir(claude_home_inbox) else None
        if claude_home_file is not None:
            fail_test(name, f"memo was WRONGLY written to CLAUDE_HOME {claude_home_file}")
            return

        pass_test(name)


def test_central_subcommand_delivers_to_doe_claude() -> None:
    """Test 42b — subcommand send path: draft + send delivers to DoE-claude, NOT ~/.claude.

    The _cmd_send subcommand path (cross-repo-memo send <topic>) is a distinct code
    location from the legacy --to flag path. This test exercises it so a regression
    (e.g. accidentally passing the old home path) would be caught.
    """
    name = "Test 42b — central delivery (subcommand send path): delivers to DoE-claude repo only"
    import datetime

    with tempfile.TemporaryDirectory() as work_tmpdir, \
         tempfile.TemporaryDirectory() as claude_home_tmpdir, \
         tempfile.TemporaryDirectory() as doe_tmpdir, \
         tempfile.TemporaryDirectory() as impl_tmpdir:

        # Use a known subdirectory name so _sender_em_id() produces a predictable
        # basename-derived identity (sender-42b-repo → sender-42b-repo-em).
        sender_repo = os.path.join(work_tmpdir, "sender-42b-repo")
        os.makedirs(sender_repo)
        subprocess.run(
            ["git", "init", sender_repo],
            capture_output=True,
            check=False,
        )

        mock_impl = _make_mock_machine_local_keys_and_get(
            impl_tmpdir,
            {"repos.doe_claude": doe_tmpdir},
        )
        env = {
            **os.environ,
            "MACHINE_LOCAL_IMPL": mock_impl,
            "CLAUDE_HOME": claude_home_tmpdir,
        }

        topic = "subcmd-doe-delivery-test"

        # Step 1: draft.
        draft_result = subprocess.run(
            [_python(), _script_path(), "draft", topic,
             "--to", "claude-central-em",
             "--title", "Subcmd DoE Delivery Test"],
            env={**os.environ, **env},
            capture_output=True,
            text=True,
            cwd=sender_repo,
        )
        if draft_result.returncode != 0:
            fail_test(name, f"draft exited {draft_result.returncode}: {draft_result.stderr}")
            return

        # Step 2: send.
        send_result = subprocess.run(
            [_python(), _script_path(), "send", topic],
            env={**os.environ, **env},
            capture_output=True,
            text=True,
            cwd=sender_repo,
        )
        if send_result.returncode != 0:
            fail_test(name, f"send exited {send_result.returncode}: {send_result.stderr}")
            return

        # Receiver filename is now <date>-<from>-<topic>.md; locate by topic suffix.
        doe_inbox = os.path.join(doe_tmpdir, "cross-repo", "inbox")
        doe_file = _find_inbox_file(doe_inbox, topic)
        if doe_file is None:
            fail_test(name, f"DoE file not found in {doe_inbox}. stdout: {send_result.stdout!r}")
            return

        # Must NOT land in ~/.claude.
        claude_home_inbox = os.path.join(claude_home_tmpdir, "cross-repo", "inbox")
        claude_home_file = _find_inbox_file(claude_home_inbox, topic) if os.path.isdir(claude_home_inbox) else None
        if claude_home_file is not None:
            fail_test(name, f"memo was WRONGLY written to CLAUDE_HOME {claude_home_file}")
            return

        pass_test(name)


def test_central_hard_errors_when_doe_absent_legacy_path() -> None:
    """Test 43 — legacy flag path: central hard-errors when repos.doe_claude is absent.

    There is no graceful fallback to ~/.claude — the CLI must exit non-zero and
    emit a central-specific remediation message naming repos.doe_claude.
    The subcommand path variant is covered by Test 43b below.
    """
    # Review: code-reviewer — removed false claim that "Test 17 (B2) covers subcommand path";
    # _assert_central_delivery uses --to flag only; Test 43b covers _cmd_send's central branch.
    name = "Test 43 — central hard-errors when repos.doe_claude absent (legacy --to flag path)"
    import datetime

    with tempfile.TemporaryDirectory() as claude_home_tmpdir, \
         tempfile.TemporaryDirectory() as impl_tmpdir:

        # All machine-local keys absent — repos.doe_claude is not registered.
        mock_impl = _make_mock_machine_local_key_absent(impl_tmpdir)
        env = {
            **os.environ,
            "MACHINE_LOCAL_IMPL": mock_impl,
            "CLAUDE_HOME": claude_home_tmpdir,
        }
        result = _run_dispatcher(
            ["--to", "claude-central-em", "--topic", "doe-absent-test", "--title", "DoE Absent Test"],
            env=env,
            stdin_text="Body.\n",
        )

        if result.returncode == 0:
            fail_test(name, "should hard-error when repos.doe_claude absent; got exit 0")
            return

        combined = result.stdout + result.stderr
        if "repos.doe_claude" not in combined:
            fail_test(name, f"error must mention repos.doe_claude. stderr: {result.stderr!r}")
            return

        # Must NOT have delivered to ~/.claude.
        today = datetime.date.today().isoformat()
        wrong_file = os.path.join(claude_home_tmpdir, "cross-repo", "inbox", f"{today}-doe-absent-test.md")
        if os.path.isfile(wrong_file):
            fail_test(name, f"memo was WRONGLY delivered to CLAUDE_HOME {wrong_file}")
            return

        pass_test(name)


def test_central_hard_errors_subcommand_path_when_doe_unregistered() -> None:
    """Test 43b — subcommand send path: central hard-errors when repos.doe_claude is absent.

    _cmd_send has its own central-specific hard-error branch (lines ~1222-1229 in
    cross-repo-memo) that is distinct from the legacy --to flag path tested by Test 43.
    Pattern: init a sender git repo, draft --to claude-central-em, then send with a
    stub that returns None for all keys. Asserts non-zero exit and repos.doe_claude in
    stderr.
    """
    # Review: code-reviewer (Finding 1) — new test covering _cmd_send's central hard-error
    # branch, which had no test coverage; Test 43 (legacy path) is the companion.
    name = "Test 43b — subcommand send path: central hard-errors when repos.doe_claude absent"

    with tempfile.TemporaryDirectory() as sender_tmpdir, \
         tempfile.TemporaryDirectory() as claude_home_tmpdir, \
         tempfile.TemporaryDirectory() as impl_tmpdir:

        # _cmd_send calls _current_repo_root() which requires a git repo as the sender.
        subprocess.run(
            ["git", "init", sender_tmpdir],
            capture_output=True,
            check=False,
        )

        # All machine-local keys absent — repos.doe_claude is not registered.
        mock_impl = _make_mock_machine_local_key_absent(impl_tmpdir)
        env = {
            **os.environ,
            "MACHINE_LOCAL_IMPL": mock_impl,
            "CLAUDE_HOME": claude_home_tmpdir,
        }

        topic = "subcmd-doe-absent-test"

        # Step 1: draft — creates the outbox file without resolving the receiver path.
        draft_result = subprocess.run(
            [_python(), _script_path(), "draft", topic,
             "--to", "claude-central-em",
             "--title", "Subcmd DoE Absent Test"],
            env={**os.environ, **env},
            capture_output=True,
            text=True,
            cwd=sender_tmpdir,
        )
        if draft_result.returncode != 0:
            fail_test(name, f"draft exited {draft_result.returncode}: {draft_result.stderr}")
            return

        # Step 2: send — repos.doe_claude absent → _cmd_send must hard-error.
        send_result = subprocess.run(
            [_python(), _script_path(), "send", topic],
            env={**os.environ, **env},
            capture_output=True,
            text=True,
            cwd=sender_tmpdir,
        )
        if send_result.returncode == 0:
            fail_test(name, "send should hard-error when repos.doe_claude absent; got exit 0")
            return

        combined = send_result.stdout + send_result.stderr
        if "repos.doe_claude" not in combined:
            fail_test(name, f"error must mention repos.doe_claude. stderr: {send_result.stderr!r}")
            return

        pass_test(name)


def test_non_central_send_delivers_to_sibling_not_doe() -> None:
    """Test 44 — non-central send: delivers to sibling repo only, not DoE-claude.

    When --to project-rag-em, the memo must land in the project-rag repo's inbox
    and must NOT appear in the DoE-claude inbox (even when repos.doe_claude is registered).
    """
    name = "Test 44 — non-central send: delivers to sibling repo, NOT DoE-claude"
    import datetime

    with tempfile.TemporaryDirectory() as receiver_tmpdir, \
         tempfile.TemporaryDirectory() as doe_tmpdir, \
         tempfile.TemporaryDirectory() as impl_tmpdir, \
         tempfile.TemporaryDirectory() as claude_home_tmpdir:

        # Register BOTH repos.project_rag (the sibling) AND repos.doe_claude.
        mock_impl = _make_mock_machine_local_keys_and_get(
            impl_tmpdir,
            {
                "repos.project_rag": receiver_tmpdir,
                "repos.doe_claude": doe_tmpdir,
            },
        )
        env = {
            **os.environ,
            "MACHINE_LOCAL_IMPL": mock_impl,
            "CLAUDE_HOME": claude_home_tmpdir,
        }
        result = _run_dispatcher(
            ["--to", "project-rag-em", "--topic", "sibling-test", "--title", "Sibling Test"],
            env=env,
            stdin_text="Body for sibling test.\n",
        )
        if result.returncode != 0:
            fail_test(name, f"dispatcher exited {result.returncode}: {result.stderr}")
            return

        # Receiver filename is now <date>-<from>-<topic>.md; locate by topic suffix.
        sibling_inbox = os.path.join(receiver_tmpdir, "cross-repo", "inbox")
        sibling_file = _find_inbox_file(sibling_inbox, "sibling-test")
        if sibling_file is None:
            fail_test(name, f"sibling file not found in {sibling_inbox}. stdout: {result.stdout!r}")
            return

        # DoE file must NOT exist.
        doe_inbox = os.path.join(doe_tmpdir, "cross-repo", "inbox")
        doe_file = _find_inbox_file(doe_inbox, "sibling-test") if os.path.isdir(doe_inbox) else None
        if doe_file is not None:
            fail_test(name, f"DoE inbox must NOT receive non-central memo; found {doe_file}")
            return

        pass_test(name)


# ---------------------------------------------------------------------------
# Test 45 — _memo_filename unit tests (sender folded in, fallback, sanitize)
#
# Regression for: same-sender+same-topic+same-day → clobber guard still fires;
#                 different-senders+same-topic+same-day → distinct filenames (no clobber).
# ---------------------------------------------------------------------------

def test_memo_filename_unit() -> None:
    """Test 45a — _memo_filename: sender folded in, empty-sender fallback, slug sanitize."""
    name = "Test 45a — _memo_filename unit: sender folded, fallback, sanitize"
    mod = _load_dispatcher_module()
    today = mod._today()

    cases = [
        # (topic, sender, expected)
        ("gate-check", "claude-central-em", f"{today}-claude-central-em-gate-check.md"),
        ("gate-check", "project-rag-em", f"{today}-project-rag-em-gate-check.md"),
        # Empty sender → fallback to <date>-<topic>.md (no double-dash)
        ("gate-check", "", f"{today}-gate-check.md"),
        # Slug sanitize: uppercase, underscores, symbols → lowercase, dash-collapsed
        ("t", "MyRepo_EM!", f"{today}-myrepo-em-t.md"),
        # Slug sanitize strips leading/trailing dashes and collapses consecutive dashes
        ("t", "-weird--sender-", f"{today}-weird-sender-t.md"),
        # Slug sanitize: all-dashes → empty after strip → fallback shape
        ("t", "---", f"{today}-t.md"),
        # Doubled-date guard: topic already carries a YYYY-MM-DD- prefix (e.g.
        # copied from a dated state/memo-outbox/ listing) — must NOT double
        # the date in the output filename.
        # Spec backlink: cross-repo/inbox/2026-07-02-cross-repo-memo-doubles-date-prefix.md
        ("2026-07-04-gate-check", "claude-central-em", f"{today}-claude-central-em-gate-check.md"),
        ("2026-07-04-gate-check", "", f"{today}-gate-check.md"),
        # Doubled-date strip is syntactic-only (regex `^\d{4}-\d{2}-\d{2}-`), NOT
        # calendar-validated — a non-calendar-date-shaped prefix (month 13, day 40)
        # is still stripped. This locks that in as intentional: a future reader must
        # not "fix" this into calendar validation, which would break a legitimately
        # date-shaped-but-not-a-real-date topic slug.
        # Review: code-reviewer (F5/nit) — added to lock in syntactic-only behavior.
        ("0000-13-40-weird-topic", "sender", f"{today}-sender-weird-topic.md"),
        # Doubled-prefix RUN guard: topic already carries TWO leading
        # YYYY-MM-DD- prefixes back-to-back (e.g. a topic string round-tripped
        # from an already-doubled filename). A single-strip regex only removes
        # one prefix, leaving the result still doubled after _today() is
        # re-prepended — the fix strips a run of one-or-more leading date
        # prefixes so the output carries exactly one date.
        # Regression for sub-bug #4 (fix2-report.md): prior fix (commit
        # d716a7df) only stripped a single leading date prefix.
        (
            "2026-07-06-2026-07-06-workstream-complete-tooling-friction",
            "claude-central-em",
            f"{today}-claude-central-em-workstream-complete-tooling-friction.md",
        ),
    ]

    for topic, sender, expected in cases:
        got = mod._memo_filename(topic, sender)
        if got != expected:
            fail_test(name, f"_memo_filename({topic!r}, {sender!r}) → {got!r}, expected {expected!r}")
            return

    pass_test(name)


def test_memo_filename_different_senders_no_clobber() -> None:
    """Test 45b — different senders, same topic, same day → distinct filenames (no clobber)."""
    name = "Test 45b — different senders + same topic → distinct receiver filenames (no clobber)"
    mod = _load_dispatcher_module()
    today = mod._today()

    fn_a = mod._memo_filename("shared-topic", "sender-a-em")
    fn_b = mod._memo_filename("shared-topic", "sender-b-em")

    if fn_a == fn_b:
        fail_test(name, f"different senders produced same filename: {fn_a!r}")
        return

    expected_a = f"{today}-sender-a-em-shared-topic.md"
    expected_b = f"{today}-sender-b-em-shared-topic.md"
    if fn_a != expected_a:
        fail_test(name, f"sender-a filename: got {fn_a!r}, expected {expected_a!r}")
        return
    if fn_b != expected_b:
        fail_test(name, f"sender-b filename: got {fn_b!r}, expected {expected_b!r}")
        return

    pass_test(name)


def test_memo_filename_same_sender_clobber_guard() -> None:
    """Test 45c — same sender + same topic + same day → O_EXCL guard still fires.

    Verifies that the clobber guard (_write_file O_EXCL) fires correctly when
    the same sender sends the same topic twice on the same day.  Both calls
    produce the same filename, so the second write must raise FileExistsError.
    """
    name = "Test 45c — same sender + same topic → O_EXCL clobber guard fires on second write"
    mod = _load_dispatcher_module()

    import tempfile as _tmpmod
    with _tmpmod.TemporaryDirectory() as receiver_tmpdir:
        receiver_inbox = os.path.join(receiver_tmpdir, "cross-repo", "inbox")
        os.makedirs(receiver_inbox, exist_ok=True)

        today = mod._today()
        sender = "collision-sender-em"
        topic = "collision-topic"
        filename = mod._memo_filename(topic, sender)
        path = os.path.join(receiver_inbox, filename)

        # First write must succeed.
        try:
            mod._write_file(path, "first content\n", receiver_tmpdir)
        except Exception as exc:
            fail_test(name, f"first write should succeed, got: {exc}")
            return

        if not os.path.isfile(path):
            fail_test(name, f"file not found after first write: {path}")
            return

        # Second write with the same sender + topic → FileExistsError (O_EXCL guard).
        try:
            mod._write_file(path, "second content\n", receiver_tmpdir)
            fail_test(name, "second write should have raised FileExistsError (clobber guard); it succeeded instead")
            return
        except FileExistsError:
            pass  # expected
        except Exception as exc:
            fail_test(name, f"second write raised unexpected exception (expected FileExistsError): {exc}")
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
        test_unregistered_receiver_hard_errors,
        test_self_receipt,
        test_self_receipt_requires_decision,
        test_topic_path_traversal_rejected,
        test_decision_superseded_accepted,
        test_title_yaml_special_chars,
        test_receiver_key_convention,
        test_unregistered_receiver_lists_known,
        test_sender_identity_from_repo,
        # B1/T1 — traversal guard
        test_write_file_traversal_guard,
        # B2 — central receiver resolution
        test_central_receiver_canonical,
        test_central_receiver_alias_central,
        test_central_receiver_alias_central_em,
        test_central_receiver_alias_doe_claude_em,
        test_central_receiver_case_whitespace_normalization,
        test_unregistered_repo_still_hard_errors,
        test_central_hard_errors_when_doe_unregistered,
        # B3 — gitignore delivery guard
        test_gitignored_receiver_hard_errors,
        test_normal_receiver_proceeds,
        test_non_git_receiver_proceeds,
        test_no_orphan_dir_on_gitignore_block,
        # H/D6 — publish-target receiver rejection
        test_publish_target_coordinator_claude_em_rejected,
        test_publish_target_coordinator_claude_shortname_rejected,
        test_publish_target_deep_research_em_rejected,
        test_publish_target_override_bypasses_check,
        test_publish_target_case_whitespace_normalization,
        test_canonical_receivers_not_rejected_by_publish_target_check,
        # Tests 27-30 — summary field (Chunk 4)
        test_summary_emitted_when_provided,
        test_summary_derived_from_body_when_omitted,
        test_summary_truncated_when_over_120_chars,
        test_body_derived_summary_truncated_when_over_120_chars,
        # Tests 31-35b (C2) — --kind flag
        test_kind_ask_round_trips,
        test_kind_consult_round_trips,
        test_kind_fyi_round_trips,
        test_kind_proposal_round_trips,
        test_kind_omitted_produces_no_kind_line,
        test_kind_invalid_value_rejected,
        # Tests 35b-d — send-side kind validation guard (_validate_outbox_frontmatter)
        test_send_side_kind_validation_rejects_invalid_value,
        test_send_side_kind_validation_allows_absent_kind,
        test_send_side_kind_validation_allows_each_valid_kind,
        # Tests 36-40 — --list-receivers discovery surface + publish-target asymmetry guard
        test_list_receivers_includes_central,
        test_list_receivers_lists_registered_siblings,
        test_list_receivers_shows_mirror_owners,
        test_deep_research_em_rejected_as_publish_target,
        test_deep_research_bare_alias_rejected_as_publish_target,
        test_publish_target_owner_resolves,
        test_missing_send_args_points_at_list_receivers,
        # Test 41 — --body-file - stdin sentinel regression
        test_body_file_dash_reads_stdin,
        # Tests 42-44 — central delivery goes to DoE-claude repo (repos.doe_claude)
        test_central_delivers_to_doe_claude,
        test_central_subcommand_delivers_to_doe_claude,
        test_central_hard_errors_when_doe_absent_legacy_path,
        test_central_hard_errors_subcommand_path_when_doe_unregistered,
        test_non_central_send_delivers_to_sibling_not_doe,
        # Tests 45a-c — sender-in-filename: unit, no-clobber, clobber-guard
        test_memo_filename_unit,
        test_memo_filename_different_senders_no_clobber,
        test_memo_filename_same_sender_clobber_guard,
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
