#!/bin/sh
''''exec "$(command -v python3 || command -v python || command -v py)" "$0" "$@" #'''
from __future__ import annotations
"""
cross-repo-memo-roundtrip.test.py — normative round-trip conformance fixture for the
5 lockstep cross-repo-memo path sites.

Spec backlink: cross-repo/inbox/strang-03-fixture-executor-brief (example-orchestration-hub-repo engine
`send` op validation — this fixture is the conformance bar it must clear).

Purpose: exercise each of the 5 coupled path-declaration sites end-to-end (a memo
written → schema-valid → own-inbox-guarded → surfaced → swept), independently, so a
deliberately-broken single site turns exactly that test red. Also encodes the pinned
DoE collision contract (2 tests): cross-sender same-day-same-topic survives; same-sender
same-day-same-topic loud-fails via O_EXCL.

Writer-agnostic: every assertion keys on path + frontmatter + on-disk file shape, never
on who wrote the file. Sites 2-5 build their fixture memo by direct file placement
(simulating the example-orchestration-hub engine's direct filesystem write) rather than via the CLI — only
Site 1 (and the collision tests) drive the CLI directly, because Site 1's own contract
IS "the CLI writes to this path."

The 5 sites (see docs/wiki/cross-repo-communication.md § Five coupled path declarations):
  1. CLI write target      — bin/cross-repo-memo (_write_file → cross-repo/inbox/)
  2. Schema applies_to     — schemas/cross-repo-memo.schema.json
  3. Own-inbox guard regex — hooks/scripts/validate-frontmatter-schema.js
  4. Surface glob          — bin/workday-start-cross-repo-memo-surface.sh
  5. Archival sweep        — cs_sweep_actioned_memos in lib/coordinator-session.sh

Run with: python bin/cross-repo-memo-roundtrip.test.py
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap

# ---------------------------------------------------------------------------
# Test infrastructure — conventions copied from cross-repo-memo.test.py
# ---------------------------------------------------------------------------

TESTS_PASSED = 0
TESTS_FAILED = 0
FAILURES: list[str] = []


def _bin_dir() -> str:
    """Return the absolute path to coordinator/bin (this file's directory)."""
    return os.path.dirname(os.path.abspath(__file__))


def _script_path() -> str:
    """Return the absolute path to cross-repo-memo."""
    return os.path.join(_bin_dir(), "cross-repo-memo")


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
    """Return the Python interpreter to use for subprocess invocations.

    Uses sys.executable directly — the interpreter running this test script is
    always a valid Python 3 interpreter; this process is a test harness driving
    other short-lived test subprocesses, not a hot-path spawn.
    """
    return sys.executable  # popup-safe-env-suppressed: test-harness subprocess, not hot-path


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

    Minimal parser — handles simple key: value lines (quoted-string aware)
    within --- delimiters. Sufficient for round-trip assertions.
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


def _find_inbox_file(inbox_dir: str, topic: str) -> str | None:
    """Return the path of the first inbox file matching *-<topic>.md."""
    import glob
    pattern = os.path.join(inbox_dir, f"*-{topic}.md")
    matches = glob.glob(pattern)
    return matches[0] if matches else None


def _make_mock_machine_local(tmpdir: str, return_value: str | None) -> str:
    """Create a stub machine-local Python script in tmpdir (see cross-repo-memo.test.py)."""
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
            argv = sys.argv[1:]
            if argv and argv[0] == "keys":
                sys.exit(0)
            print("{escaped}")
            sys.exit(0)
        """)
    with open(stub_path, "w") as f:
        f.write(script)
    return stub_path


def _write_direct_memo(inbox_dir: str, *, date: str, sender: str, topic: str,
                        title: str, status: str, extra_fm: dict[str, str] | None = None,
                        body: str = "Round-trip fixture body.\n") -> str:
    """Hand-place a memo file directly on disk — simulating a non-CLI writer (e.g. the
    example-orchestration-hub engine's direct filesystem write). Sites 2-5 must treat this identically to a
    CLI-written memo: this is the writer-agnosticism proof.

    Filename shape mirrors _memo_filename's contract: <date>-<sender>-<topic>.md.
    """
    os.makedirs(inbox_dir, exist_ok=True)
    fname = f"{date}-{sender}-{topic}.md"
    path = os.path.join(inbox_dir, fname)
    lines = [
        "---",
        f'title: "{title}"',
        f"from: {sender}",
        f"to: some-receiver-em",
        f"created: {date}",
        f"status: {status}",
        "delivery_mode: receiver-repo",
        'summary: "Round-trip fixture memo."',
    ]
    if extra_fm:
        for k, v in extra_fm.items():
            lines.append(f"{k}: {v}")
    lines.append("---")
    content = "\n".join(lines) + "\n\n" + body
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


# ---------------------------------------------------------------------------
# Site 1 — CLI write target: bin/cross-repo-memo writes into
# <receiver>/cross-repo/inbox/YYYY-MM-DD-<from>-<topic>.md
# ---------------------------------------------------------------------------

def test_site1_cli_write_target() -> None:
    name = "Site 1 — CLI write target: cross-repo-memo writes to cross-repo/inbox/<date>-<from>-<topic>.md"
    with tempfile.TemporaryDirectory() as receiver_tmpdir, \
         tempfile.TemporaryDirectory() as claude_home_tmpdir:
        mock_impl = _make_mock_machine_local(receiver_tmpdir, receiver_tmpdir)
        env = {
            "MACHINE_LOCAL_IMPL": mock_impl,
            "CLAUDE_HOME": claude_home_tmpdir,
        }
        result = _run_dispatcher(
            ["--to", "project-rag-em", "--topic", "roundtrip-site1", "--title", "Site 1 Roundtrip"],
            env=env,
            stdin_text="Site 1 body.\n",
        )
        if result.returncode != 0:
            fail_test(name, f"dispatcher exited {result.returncode}: {result.stderr}")
            return
        inbox_dir = os.path.join(receiver_tmpdir, "cross-repo", "inbox")
        receiver_file = _find_inbox_file(inbox_dir, "roundtrip-site1")
        if receiver_file is None:
            fail_test(name, f"expected file not found in {inbox_dir} (pattern *-roundtrip-site1.md)")
            return
        basename = os.path.basename(receiver_file)
        # Filename shape: YYYY-MM-DD-<from>-<topic>.md
        if not re.match(r"^\d{4}-\d{2}-\d{2}-.+-roundtrip-site1\.md$", basename):
            fail_test(name, f"filename does not match <date>-<from>-<topic>.md shape: {basename!r}")
            return
        pass_test(name)


# ---------------------------------------------------------------------------
# Site 2 — Schema applies_to: schemas/cross-repo-memo.schema.json
# ---------------------------------------------------------------------------

def test_site2_schema_applies_to() -> None:
    name = "Site 2 — Schema applies_to glob matches cross-repo/inbox/<file> and frontmatter satisfies required fields"
    schema_path = os.path.join(_bin_dir(), "..", "schemas", "cross-repo-memo.schema.json")
    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)

    applies_to = schema.get("applies_to")
    if not applies_to:
        fail_test(name, "schema has no applies_to field")
        return
    required = schema.get("required", [])
    if not required:
        fail_test(name, "schema has no required field list")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        inbox_dir = os.path.join(tmpdir, "cross-repo", "inbox")
        memo_path = _write_direct_memo(
            inbox_dir, date="2026-07-09", sender="engine-writer-em",
            topic="roundtrip-site2", title="Site 2 Roundtrip", status="open",
        )
        rel_path = os.path.relpath(memo_path, tmpdir).replace("\\", "/")

        # applies_to is the literal glob "cross-repo/inbox/[0-9]*.md" — a POSIX character
        # class + star, not a regex; translate it directly rather than via re.escape
        # (re.escape would mangle the [0-9] character class).
        if applies_to != "cross-repo/inbox/[0-9]*.md":
            fail_test(name, f"applies_to glob changed shape unexpectedly ({applies_to!r}); update this test's translation")
            return
        glob_re = r"^cross-repo/inbox/[0-9][^/]*\.md$"
        if not re.match(glob_re, rel_path):
            fail_test(name, f"applies_to glob {applies_to!r} does not match written path {rel_path!r}")
            return

        # (b) required fields present in written frontmatter.
        with open(memo_path, encoding="utf-8") as f:
            fm = _parse_frontmatter(f.read())
        missing = [field for field in required if not fm.get(field)]
        if missing:
            fail_test(name, f"written memo frontmatter missing required schema fields: {missing}")
            return
        pass_test(name)


# ---------------------------------------------------------------------------
# Site 3 — Own-inbox guard regex: hooks/scripts/validate-frontmatter-schema.js
# ---------------------------------------------------------------------------

def _run_own_inbox_hook(cwd: str, file_path: str, content: str) -> subprocess.CompletedProcess:
    """Drive validate-frontmatter-schema.js via subprocess, piping a Write-shaped
    PreToolUse payload on stdin. Always exits 0 (offer-shape hook contract).

    Both cwd and file_path are realpath-resolved before dispatch: the hook's
    resolveRepoRoot() calls `git rev-parse --show-toplevel`, which returns the
    REALPATH of the repo root. On macOS, tempfile.mkdtemp() returns a path under
    /var/... which is itself a symlink to /private/var/...; toRepoRelative() does
    a literal startsWith comparison between repoRoot and file_path, so an
    un-resolved /var/... path silently fails to match /private/var/... and the
    hook's own-inbox branch never fires (confirmed by direct repro: identical
    empty-stdout/exit-0 symptom). Resolving both to realpath avoids the mismatch.
    """
    cwd = os.path.realpath(cwd)
    file_path = os.path.realpath(file_path)
    hook_path = os.path.join(_bin_dir(), "..", "hooks", "scripts", "validate-frontmatter-schema.js")
    payload = json.dumps({
        "tool_name": "Write",
        "tool_input": {"file_path": file_path, "content": content},
        "cwd": cwd,
    })
    return subprocess.run(
        ["node", hook_path],
        input=payload,
        capture_output=True,
        text=True,
    )


def test_site3_own_inbox_guard_fires() -> None:
    name = "Site 3a — own-inbox guard regex fires on cross-repo/inbox/[0-9]... write with from==thisRepo"
    with tempfile.TemporaryDirectory() as repo_tmpdir:
        subprocess.run(["git", "init", repo_tmpdir], capture_output=True, check=False)
        subprocess.run(["git", "-C", repo_tmpdir, "config", "user.email", "t@t.com"], capture_output=True, check=False)
        subprocess.run(["git", "-C", repo_tmpdir, "config", "user.name", "T"], capture_output=True, check=False)

        repo_basename = os.path.basename(repo_tmpdir.rstrip("/"))
        this_em_id = repo_basename.replace("_", "-") + "-em"

        target = os.path.join(repo_tmpdir, "cross-repo", "inbox", "2026-07-09-own-inbox-test.md")
        content = (
            "---\n"
            'title: "Outbound memo misplaced in own inbox"\n'
            f"from: {this_em_id}\n"
            "to: some-other-repo-em\n"
            "created: 2026-07-09\n"
            "status: open\n"
            "delivery_mode: receiver-repo\n"
            'summary: "Test."\n'
            "---\n"
        )
        result = _run_own_inbox_hook(repo_tmpdir, target, content)
        if result.returncode != 0:
            fail_test(name, f"hook must always exit 0 (offer-shape); got {result.returncode}")
            return
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            fail_test(name, f"hook stdout not valid JSON: {result.stdout!r}")
            return
        reason = (
            payload.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
            or payload.get("hookSpecificOutput", {}).get("additionalContext", "")
        )
        if "own cross-repo/inbox" not in reason and "own inbox" not in reason.lower():
            fail_test(name, f"expected own-inbox redirect offer in hook output; got: {result.stdout!r}")
            return
        pass_test(name)


def test_site3_own_inbox_guard_does_not_fire_on_archive() -> None:
    name = "Site 3b — own-inbox guard regex does NOT fire on cross-repo/archive/ write (proves the regex gates, not over-fires)"
    with tempfile.TemporaryDirectory() as repo_tmpdir:
        subprocess.run(["git", "init", repo_tmpdir], capture_output=True, check=False)
        subprocess.run(["git", "-C", repo_tmpdir, "config", "user.email", "t@t.com"], capture_output=True, check=False)
        subprocess.run(["git", "-C", repo_tmpdir, "config", "user.name", "T"], capture_output=True, check=False)

        repo_basename = os.path.basename(repo_tmpdir.rstrip("/"))
        this_em_id = repo_basename.replace("_", "-") + "-em"

        # Same from==thisRepo, to!=thisRepo shape as the firing test — but landing under
        # cross-repo/archive/ instead of cross-repo/inbox/[0-9]. The regex is anchored to
        # inbox/, so this must NOT trigger the own-inbox deny.
        target = os.path.join(repo_tmpdir, "cross-repo", "archive", "2026-07-09-own-inbox-test.md")
        content = (
            "---\n"
            'title: "Closed memo in archive"\n'
            f"from: {this_em_id}\n"
            "to: some-other-repo-em\n"
            "created: 2026-07-09\n"
            "status: actioned\n"
            "delivery_mode: receiver-repo\n"
            'summary: "Test."\n'
            "---\n"
        )
        result = _run_own_inbox_hook(repo_tmpdir, target, content)
        if result.returncode != 0:
            fail_test(name, f"hook must always exit 0 (offer-shape); got {result.returncode}")
            return
        try:
            payload = json.loads(result.stdout) if result.stdout.strip() else {}
        except json.JSONDecodeError:
            fail_test(name, f"hook stdout not valid JSON: {result.stdout!r}")
            return
        reason = (
            payload.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
            or payload.get("hookSpecificOutput", {}).get("additionalContext", "")
        )
        if "own cross-repo/inbox" in reason or "own inbox" in reason.lower():
            fail_test(name, f"own-inbox deny incorrectly fired for cross-repo/archive/ write: {result.stdout!r}")
            return
        pass_test(name)


# ---------------------------------------------------------------------------
# Site 4 — Surface glob: bin/workday-start-cross-repo-memo-surface.sh
# ---------------------------------------------------------------------------

def test_site4_surface_glob() -> None:
    name = "Site 4 — surface script (CROSS_REPO_INBOX_DIR override) surfaces a directly-placed open memo"
    surface_script = os.path.join(_bin_dir(), "workday-start-cross-repo-memo-surface.sh")
    with tempfile.TemporaryDirectory() as tmpdir:
        inbox_dir = os.path.join(tmpdir, "cross-repo", "inbox")
        _write_direct_memo(
            inbox_dir, date="2026-07-01", sender="site4-sender-em",
            topic="roundtrip-site4", title="Site 4 Roundtrip Topic", status="open",
        )
        result = subprocess.run(
            ["bash", surface_script],
            env={**os.environ, "CROSS_REPO_INBOX_DIR": inbox_dir, "MOCK_TODAY": "2026-07-09"},
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            fail_test(name, f"surface script exited {result.returncode}: {result.stderr}")
            return
        if "site4-sender-em" not in result.stdout or "Site 4 Roundtrip Topic" not in result.stdout:
            fail_test(name, f"surfaced memo's sender/title not found in stdout: {result.stdout!r}")
            return
        pass_test(name)


# ---------------------------------------------------------------------------
# Site 5 — Archival sweep: cs_sweep_actioned_memos in lib/coordinator-session.sh
# ---------------------------------------------------------------------------

def test_site5_archival_sweep() -> None:
    name = "Site 5 — cs_sweep_actioned_memos git-mv's a status:actioned memo from inbox/ to archive/"
    lib_path = os.path.join(_bin_dir(), "..", "lib", "coordinator-session.sh")
    if not os.path.isfile(lib_path):
        fail_test(name, f"coordinator-session.sh lib not found at {lib_path}")
        return

    # Coverage note: this site's round-trip is node-availability-conditional — if node is
    # missing on PATH, the test below reports a failure rather than a true pass, so silent
    # loss of Site 5 coverage in a node-less CI environment will surface as a red run, not
    # a green one that quietly skipped.
    node_available = subprocess.run(["node", "--version"], capture_output=True).returncode == 0
    if not node_available:
        fail_test(name, "node not available on PATH — sweep requires node for query-records.js; cannot exercise real round-trip")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(["git", "init", tmpdir], capture_output=True, check=False)
        subprocess.run(["git", "-C", tmpdir, "config", "user.email", "t@t.com"], capture_output=True, check=False)
        subprocess.run(["git", "-C", tmpdir, "config", "user.name", "T"], capture_output=True, check=False)

        inbox_dir = os.path.join(tmpdir, "cross-repo", "inbox")
        memo_path = _write_direct_memo(
            inbox_dir, date="2026-07-01", sender="site5-sender-em",
            topic="roundtrip-site5", title="Site 5 Roundtrip", status="actioned",
            extra_fm={
                "decision": "accepted",
                "action_taken_at": "2026-07-02T10:00:00Z",
                "realized_by": "inline",
            },
        )
        subprocess.run(["git", "-C", tmpdir, "add", "cross-repo/inbox"], capture_output=True, check=False)
        subprocess.run(["git", "-C", tmpdir, "commit", "-m", "seed actioned memo"], capture_output=True, check=False)
        fname = os.path.basename(memo_path)

        # Drive via a bash -c subprocess that sources the lib and calls the function —
        # mirrors the brief's instruction; no existing unit test for this function was
        # found (grepped bin/*.test.* for cs_sweep_actioned_memos — no hits).
        bash_cmd = (
            f'set -e; source "{lib_path}"; cs_sweep_actioned_memos "{tmpdir}"'
        )
        result = subprocess.run(
            ["bash", "-c", bash_cmd],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            fail_test(name, f"sweep bash invocation exited {result.returncode}: {result.stderr}")
            return

        archived_path = os.path.join(tmpdir, "cross-repo", "archive", fname)
        inbox_path_after = os.path.join(tmpdir, "cross-repo", "inbox", fname)
        if not os.path.isfile(archived_path):
            fail_test(name, f"memo not found at expected archive path {archived_path} after sweep. sweep stdout: {result.stdout!r} stderr: {result.stderr!r}")
            return
        if os.path.isfile(inbox_path_after):
            fail_test(name, f"memo still present at inbox path {inbox_path_after} after sweep — should have been moved")
            return
        pass_test(name)


# ---------------------------------------------------------------------------
# Collision case 1 — cross-sender, same day, same topic → BOTH memos survive
# ---------------------------------------------------------------------------

def test_collision_cross_sender_both_survive() -> None:
    name = "Collision 1 — cross-sender same-day same-topic: BOTH memos survive (sender folded into filename)"
    with tempfile.TemporaryDirectory() as receiver_tmpdir, \
         tempfile.TemporaryDirectory() as claude_home_a, \
         tempfile.TemporaryDirectory() as claude_home_b:
        mock_impl = _make_mock_machine_local(receiver_tmpdir, receiver_tmpdir)

        # Simulate two distinct sender repos so em_id_for_root resolves two different
        # `from:` identities (both unregistered siblings → basename fallback), proving
        # the sender-folded-into-filename guarantee for the real N-repo-broadcast case.
        sender_a_root = os.path.join(claude_home_a, "sender-repo-alpha")
        sender_b_root = os.path.join(claude_home_b, "sender-repo-beta")
        os.makedirs(sender_a_root)
        os.makedirs(sender_b_root)
        subprocess.run(["git", "init", sender_a_root], capture_output=True, check=False)
        subprocess.run(["git", "init", sender_b_root], capture_output=True, check=False)

        env_a = {"MACHINE_LOCAL_IMPL": mock_impl, "CLAUDE_HOME": claude_home_a}
        env_b = {"MACHINE_LOCAL_IMPL": mock_impl, "CLAUDE_HOME": claude_home_b}

        result_a = subprocess.run(
            [_python(), _script_path(), "--to", "project-rag-em", "--topic", "roundtrip-collision",
             "--title", "From Alpha"],
            cwd=sender_a_root,
            env={**os.environ, **env_a},
            capture_output=True, text=True, input="Alpha body.\n",
        )
        result_b = subprocess.run(
            [_python(), _script_path(), "--to", "project-rag-em", "--topic", "roundtrip-collision",
             "--title", "From Beta"],
            cwd=sender_b_root,
            env={**os.environ, **env_b},
            capture_output=True, text=True, input="Beta body.\n",
        )
        if result_a.returncode != 0:
            fail_test(name, f"sender A dispatch failed: {result_a.returncode}: {result_a.stderr}")
            return
        if result_b.returncode != 0:
            fail_test(name, f"sender B dispatch failed: {result_b.returncode}: {result_b.stderr}")
            return

        inbox_dir = os.path.join(receiver_tmpdir, "cross-repo", "inbox")
        import glob
        matches = sorted(glob.glob(os.path.join(inbox_dir, "*-roundtrip-collision.md")))
        if len(matches) != 2:
            fail_test(name, f"expected 2 distinct memo files (cross-sender, same day/topic); found {len(matches)}: {matches}")
            return
        titles = set()
        for m in matches:
            with open(m, encoding="utf-8") as f:
                fm = _parse_frontmatter(f.read())
            titles.add(fm.get("title"))
        if titles != {"From Alpha", "From Beta"}:
            fail_test(name, f"both memo contents should survive distinctly; got titles: {titles}")
            return
        pass_test(name)


# ---------------------------------------------------------------------------
# Collision case 2 — same-sender, same day, same topic → LOUD FAIL, no silent clobber
# ---------------------------------------------------------------------------

def test_collision_same_sender_loud_fail() -> None:
    name = "Collision 2 — same-sender same-day same-topic: second write LOUD FAILS (O_EXCL), first memo unchanged"
    mod = _load_dispatcher_module()
    with tempfile.TemporaryDirectory() as receiver_tmpdir:
        target_path = os.path.join(receiver_tmpdir, "cross-repo", "inbox", "2026-07-09-same-sender-em-roundtrip-collision2.md")
        first_content = "---\ntitle: \"First\"\n---\nFirst content.\n"
        second_content = "---\ntitle: \"Second\"\n---\nSecond content.\n"

        # First write succeeds.
        try:
            mod._write_file(target_path, first_content, receiver_tmpdir)
        except Exception as exc:
            fail_test(name, f"first write should succeed; raised {type(exc).__name__}: {exc}")
            return
        if not os.path.isfile(target_path):
            fail_test(name, "first write reported success but file is not present on disk")
            return
        with open(target_path, encoding="utf-8") as f:
            after_first = f.read()
        if after_first != first_content:
            fail_test(name, "first file content does not match what was written")
            return

        # Second write to the SAME path (same sender+date+topic) must LOUD FAIL.
        try:
            mod._write_file(target_path, second_content, receiver_tmpdir)
            fail_test(name, "second write should raise FileExistsError (O_EXCL guard); no exception raised")
            return
        except FileExistsError:
            pass
        except Exception as exc:
            fail_test(name, f"second write raised wrong exception type {type(exc).__name__}: {exc}")
            return

        # First file's content must be UNCHANGED after the rejected second write.
        with open(target_path, encoding="utf-8") as f:
            after_second_attempt = f.read()
        if after_second_attempt != first_content:
            fail_test(name, f"first file content changed after rejected second write — silent clobber occurred. Got: {after_second_attempt!r}")
            return
        pass_test(name)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    tests = [
        test_site1_cli_write_target,
        test_site2_schema_applies_to,
        test_site3_own_inbox_guard_fires,
        test_site3_own_inbox_guard_does_not_fire_on_archive,
        test_site4_surface_glob,
        test_site5_archival_sweep,
        test_collision_cross_sender_both_survive,
        test_collision_same_sender_loud_fail,
    ]

    print(f"Running {len(tests)} round-trip conformance tests...\n")
    for test_fn in tests:
        try:
            test_fn()
        except Exception as exc:
            fail_test(test_fn.__name__, f"unhandled exception: {type(exc).__name__}: {exc}")

    print(f"\n{TESTS_PASSED} passed, {TESTS_FAILED} failed")
    if FAILURES:
        print("\nFailures:")
        for f in FAILURES:
            print(f)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
