#!/bin/sh
''''exec "$(command -v python3 || command -v python || command -v py)" "$0" "$@" #'''
from __future__ import annotations
"""
coordinator-lesson-promote.test.py — smoke tests for the coordinator-lesson-promote CLI.

Spec backlink: docs/plans/2026-06-15-universal-lesson-routing-mechanical-capture.md § C1

Tests:
  1. --help exits 0 with non-empty stdout.
  2. Missing --title → exit non-zero, stderr names the missing field.
  3. Missing --change-kind → exit non-zero, stderr names the missing field.
  4. Invalid --change-kind value → exit non-zero, stderr names valid enum values.
  5. Valid invocation → exit 0, exactly one YAML file produced in temp outbox,
     file parseable as YAML with all required schema fields present.
  6. Roundtrip: write entry, read YAML back, all field values match what was passed.

Run with: python coordinator-lesson-promote.test.py
"""

import os
import subprocess
import sys
import tempfile

try:
    import yaml as _yaml  # PyYAML — available on most coordinator installs
    _YAML_AVAILABLE = True
except ImportError:
    _yaml = None  # type: ignore[assignment]
    _YAML_AVAILABLE = False

# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------

TESTS_PASSED = 0
TESTS_FAILED = 0
FAILURES: list[str] = []


def _script_path() -> str:
    """Return the absolute path to coordinator-lesson-promote."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "coordinator-lesson-promote")


def _python() -> str:
    """Return the Python interpreter to use for subprocess invocations.

    Uses sys.executable — the interpreter running this test script is always a
    valid Python interpreter. This is the Windows-compatible zero-probe pattern
    (avoids FileNotFoundError from subprocess probing python3/python on Windows).
    """
    return sys.executable


def _run_cli(args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """Invoke the CLI as a subprocess.

    Always drives via `python <script>` — the script has no .py extension and is
    not directly executable on Windows. Same pattern as cross-repo-memo.test.py.
    """
    effective_env = {**os.environ}
    if env:
        effective_env.update(env)
    return subprocess.run(
        [_python(), _script_path()] + args,
        env=effective_env,
        capture_output=True,
        text=True,
    )


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


def _parse_yaml_file(path: str) -> dict:
    """Parse a YAML file. Falls back to a minimal line-parser if PyYAML unavailable."""
    try:
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        if _YAML_AVAILABLE:
            try:
                parsed = _yaml.safe_load(content)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
        # Minimal fallback: parse simple key: value lines between --- delimiters.
        return _minimal_yaml_parse(content)
    except OSError as exc:
        raise RuntimeError(f"could not read YAML file {path}: {exc}") from exc


def _minimal_yaml_parse(content: str) -> dict:
    """Minimal YAML frontmatter parser for simple key: value lines.

    Handles:
    - Scalar values (quoted and unquoted)
    - Block scalars (|) — collects lines until next key or end marker
    Sufficient for the coordinator-lesson-promote output schema.
    """
    result: dict = {}
    lines = content.splitlines()
    i = 0
    # Skip opening ---
    while i < len(lines) and lines[i].strip() == "---":
        i += 1

    while i < len(lines):
        line = lines[i]
        if line.strip() == "---":
            break
        if ":" in line and not line.startswith(" "):
            key, _, rest = line.partition(":")
            key = key.strip()
            value = rest.strip()
            if value == "|":
                # Block scalar — collect subsequent indented lines.
                block_lines = []
                i += 1
                while i < len(lines) and (lines[i].startswith("  ") or lines[i].strip() == ""):
                    block_lines.append(lines[i][2:] if lines[i].startswith("  ") else "")
                    i += 1
                result[key] = "\n".join(block_lines).rstrip("\n")
                continue
            elif value.startswith('"'):
                # Quoted string — unescape basic escapes.
                inner = value[1:]
                if inner.endswith('"'):
                    inner = inner[:-1]
                result[key] = inner.replace('\\"', '"').replace("\\\\", "\\")
            else:
                result[key] = value
        i += 1
    return result


# ---------------------------------------------------------------------------
# Test 1 — --help exits 0 with non-empty stdout
# ---------------------------------------------------------------------------

def test_help_exits_zero() -> None:
    name = "Test 1 — --help exits 0 with non-empty stdout"
    result = _run_cli(["--help"])
    if result.returncode != 0:
        fail_test(name, f"--help exited {result.returncode}, expected 0")
        return
    if not result.stdout.strip():
        fail_test(name, "--help produced empty stdout")
        return
    pass_test(name)


# ---------------------------------------------------------------------------
# Test 2 — Missing --title → exit non-zero, stderr names the missing field
# ---------------------------------------------------------------------------

def test_missing_title_fails() -> None:
    name = "Test 2 — missing --title → exit non-zero, stderr names field"
    with tempfile.TemporaryDirectory() as tmpdir:
        result = _run_cli(
            [
                "--body", "some body",
                "--change-kind", "doctrine-edit",
                "--target-wiki", "docs/wiki/some.md",
            ],
            env={"LESSON_PROMOTE_OUTBOX_ROOT": os.path.join(tmpdir, "state", "lessons-outbox")},
        )
    if result.returncode == 0:
        fail_test(name, "expected non-zero exit for missing --title; got 0")
        return
    combined = result.stdout + result.stderr
    if "title" not in combined.lower():
        fail_test(name, f"error output does not name 'title'. stderr: {result.stderr!r}")
        return
    pass_test(name)


# ---------------------------------------------------------------------------
# Test 3 — Missing --change-kind → exit non-zero, stderr names the missing field
# ---------------------------------------------------------------------------

def test_missing_change_kind_fails() -> None:
    name = "Test 3 — missing --change-kind → exit non-zero, stderr names field"
    with tempfile.TemporaryDirectory() as tmpdir:
        result = _run_cli(
            [
                "--title", "some title",
                "--body", "some body",
                "--target-wiki", "docs/wiki/some.md",
            ],
            env={"LESSON_PROMOTE_OUTBOX_ROOT": os.path.join(tmpdir, "state", "lessons-outbox")},
        )
    if result.returncode == 0:
        fail_test(name, "expected non-zero exit for missing --change-kind; got 0")
        return
    combined = result.stdout + result.stderr
    if "change-kind" not in combined.lower() and "change_kind" not in combined.lower():
        fail_test(name, f"error output does not name 'change-kind'. stderr: {result.stderr!r}")
        return
    pass_test(name)


# ---------------------------------------------------------------------------
# Test 4 — Invalid --change-kind value → exit non-zero, stderr names valid values
# ---------------------------------------------------------------------------

def test_invalid_change_kind_fails() -> None:
    name = "Test 4 — invalid --change-kind → exit non-zero, stderr names valid enum values"
    with tempfile.TemporaryDirectory() as tmpdir:
        result = _run_cli(
            [
                "--title", "some title",
                "--body", "some body",
                "--change-kind", "bogus",
                "--target-wiki", "docs/wiki/some.md",
            ],
            env={"LESSON_PROMOTE_OUTBOX_ROOT": os.path.join(tmpdir, "state", "lessons-outbox")},
        )
    if result.returncode == 0:
        fail_test(name, "expected non-zero exit for invalid --change-kind; got 0")
        return
    combined = result.stdout + result.stderr
    # stderr should name at least one valid value to serve as a hint.
    if "doctrine-edit" not in combined:
        fail_test(name, f"error output should name valid enum values (e.g. 'doctrine-edit'). stderr: {result.stderr!r}")
        return
    pass_test(name)


# ---------------------------------------------------------------------------
# Test 5 — Valid invocation produces exactly one YAML file with required fields
# ---------------------------------------------------------------------------

_REQUIRED_SCHEMA_FIELDS = ("id", "created", "from_repo", "title", "body", "change_kind", "target_wiki")


def test_valid_invocation_writes_yaml() -> None:
    name = "Test 5 — valid invocation → exit 0, one YAML file with required fields"
    with tempfile.TemporaryDirectory() as tmpdir:
        outbox = os.path.join(tmpdir, "state", "lessons-outbox")
        result = _run_cli(
            [
                "--title", "Lesson about executor retries",
                "--body", "Executors should not retry after structural failure.",
                "--change-kind", "doctrine-edit",
                "--target-wiki", "docs/wiki/executor-discipline.md",
            ],
            env={"LESSON_PROMOTE_OUTBOX_ROOT": outbox},
        )
        if result.returncode != 0:
            fail_test(name, f"CLI exited {result.returncode}: {result.stderr!r}")
            return

        # Exactly one YAML file must exist.
        if not os.path.isdir(outbox):
            fail_test(name, f"outbox directory not created: {outbox}")
            return

        yaml_files = [f for f in os.listdir(outbox) if f.endswith(".yaml")]
        if len(yaml_files) != 1:
            fail_test(name, f"expected exactly 1 YAML file; found {len(yaml_files)}: {yaml_files}")
            return

        yaml_path = os.path.join(outbox, yaml_files[0])
        try:
            parsed = _parse_yaml_file(yaml_path)
        except RuntimeError as exc:
            fail_test(name, f"YAML parse error: {exc}")
            return

        missing = [f for f in _REQUIRED_SCHEMA_FIELDS if f not in parsed]
        if missing:
            fail_test(name, f"YAML missing required fields: {missing}. Parsed: {parsed}")
            return

        pass_test(name)


# ---------------------------------------------------------------------------
# Test 6 — Roundtrip: field values match what was passed
# ---------------------------------------------------------------------------

def test_roundtrip_field_values() -> None:
    name = "Test 6 — roundtrip: all passed field values preserved in YAML"
    title = "Roundtrip test lesson title"
    body = "This is the roundtrip lesson body prose."
    change_kind = "wiki-append"
    target_wiki = "docs/wiki/roundtrip-test.md"
    scope_tags = "executor,plan-authoring"
    evidence = "abc1234def5678"

    with tempfile.TemporaryDirectory() as tmpdir:
        outbox = os.path.join(tmpdir, "state", "lessons-outbox")
        result = _run_cli(
            [
                "--title", title,
                "--body", body,
                "--change-kind", change_kind,
                "--target-wiki", target_wiki,
                "--scope-tags", scope_tags,
                "--evidence", evidence,
            ],
            env={"LESSON_PROMOTE_OUTBOX_ROOT": outbox},
        )
        if result.returncode != 0:
            fail_test(name, f"CLI exited {result.returncode}: {result.stderr!r}")
            return

        yaml_files = [f for f in os.listdir(outbox) if f.endswith(".yaml")]
        if len(yaml_files) != 1:
            fail_test(name, f"expected 1 YAML file; got {len(yaml_files)}")
            return

        yaml_path = os.path.join(outbox, yaml_files[0])
        try:
            parsed = _parse_yaml_file(yaml_path)
        except RuntimeError as exc:
            fail_test(name, f"YAML parse error: {exc}")
            return

        # Verify all passed fields round-trip exactly.
        checks = [
            ("title", title),
            ("body", body),
            ("change_kind", change_kind),
            ("target_wiki", target_wiki),
            ("evidence", evidence),
        ]
        for field, expected in checks:
            got = parsed.get(field)
            if got != expected:
                fail_test(name, f"field {field!r}: expected {expected!r}, got {got!r}")
                return

        # id must be a non-empty UUID-shaped string.
        entry_id = parsed.get("id", "")
        if not entry_id or len(entry_id) < 32:
            fail_test(name, f"id field looks wrong: {entry_id!r}")
            return

        # created must be a non-empty ISO timestamp.
        created = parsed.get("created", "")
        if not created or "T" not in created:
            fail_test(name, f"created field looks wrong: {created!r}")
            return

        # from_repo must be non-empty.
        from_repo = parsed.get("from_repo", "")
        if not from_repo:
            fail_test(name, "from_repo field is empty")
            return

        pass_test(name)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    print("coordinator-lesson-promote.test.py")
    print("=" * 50)

    test_help_exits_zero()
    test_missing_title_fails()
    test_missing_change_kind_fails()
    test_invalid_change_kind_fails()
    test_valid_invocation_writes_yaml()
    test_roundtrip_field_values()

    print()
    print(f"Results: {TESTS_PASSED} passed, {TESTS_FAILED} failed")
    if FAILURES:
        print()
        print("Failures:")
        for msg in FAILURES:
            print(msg)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
