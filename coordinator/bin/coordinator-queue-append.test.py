#!/bin/sh
# ── sh/python polyglot trampoline ─────────────────────────────────────────────
# Matches the CLI's trampoline so `bash coordinator-queue-append.test.py` works.
''''exec "$(command -v python3 || command -v python || command -v py)" "$0" "$@" #'''
from __future__ import annotations
"""
coordinator-queue-append.test.py — integration tests for coordinator-queue-append CLI.

Spec backlink: docs/plans/2026-06-15-structured-queue-medium-rollout.md § C5

Tests:
  1. --help exits 0 with non-empty stdout. Smoke test.
  2. Unknown --schema exits non-zero; stderr names known schemas.
  3. Missing required field (debt-backlog: source, risk, suggested_action absent)
     exits non-zero; stderr names a missing field.
  4. Invalid enum value for --status exits non-zero; stderr names valid values.
  5. Valid debt-backlog write: exits 0, file exists at expected path, non-empty,
     YAML structure includes required fields.
  6. Roundtrip: emitted YAML is well-formed and all passed field values survive.
  7. Schema-doc-not-runtime-parsed (the Staff Engineer F0 guard): deleting the wiki file from
     a tmpdir does not break a valid write invocation.
  8. Explicit --id with invalid pattern format exits non-zero; stderr names pattern.

Run with: python coordinator-queue-append.test.py
"""

import datetime
import os
import shutil
import subprocess
import sys
import tempfile

# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------

TESTS_PASSED = 0
TESTS_FAILED = 0
FAILURES: list[str] = []


def _script_path() -> str:
    """Return the absolute path to coordinator-queue-append."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "coordinator-queue-append")


def _python() -> str:
    """Return the Python interpreter to use for subprocess invocations.

    Uses sys.executable — the interpreter running this test script is always a
    valid Python interpreter. This is the Windows-compatible zero-probe pattern
    (avoids FileNotFoundError from subprocess probing python3/python on Windows).
    """
    return sys.executable


def _run_cli(args: list[str], env: dict[str, str] | None = None, cwd: str | None = None) -> subprocess.CompletedProcess:
    """Invoke the CLI as a subprocess.

    Always drives via `python <script>` — the script has no .py extension and is
    not directly executable on Windows. Same pattern as coordinator-lesson-promote.test.py.
    """
    effective_env = {**os.environ}
    if env:
        effective_env.update(env)
    return subprocess.run(
        [_python(), _script_path()] + args,
        env=effective_env,
        capture_output=True,
        text=True,
        cwd=cwd,
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


def _minimal_yaml_parse(content: str) -> dict:
    """Minimal YAML parser for simple key: value lines and block scalars.

    Handles:
    - Scalar values (quoted and unquoted)
    - Block scalars (|) — collects lines until next key or end marker
    Sufficient for coordinator-queue-append output schema.
    Matches the shape used in coordinator-lesson-promote.test.py.
    """
    result: dict = {}
    lines = content.splitlines()
    i = 0

    while i < len(lines):
        line = lines[i]
        if line.strip() == "---":
            i += 1
            continue
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
                inner = value[1:]
                if inner.endswith('"'):
                    inner = inner[:-1]
                result[key] = inner.replace('\\"', '"').replace("\\\\", "\\")
            else:
                result[key] = value
        i += 1
    return result


def _parse_yaml_file(path: str) -> dict:
    """Parse a YAML file, falling back to the minimal parser if PyYAML absent."""
    try:
        import yaml as _yaml  # PyYAML — available on most coordinator installs
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        try:
            parsed = _yaml.safe_load(content)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        return _minimal_yaml_parse(content)
    except ImportError:
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        return _minimal_yaml_parse(content)
    except OSError as exc:
        raise RuntimeError(f"could not read YAML file {path}: {exc}") from exc


# ---------------------------------------------------------------------------
# Shared helpers for building valid debt-backlog invocation args
# ---------------------------------------------------------------------------

def _debt_backlog_required_args() -> list[str]:
    """Return the minimal valid CLI args for a debt-backlog entry.

    All required fields for debt-backlog:
      id (auto-generated), created (auto), title, body, status, source, risk,
      suggested_action.
    Explicit --from-repo to bypass machine-local resolution in test environments.
    """
    return [
        "--schema", "debt-backlog",
        "--title", "Test debt entry",
        "--body", "Body text for the test entry.",
        "--status", "open",
        "--source", "daily-review/test/2026-06-15",
        "--risk", "Test risk description.",
        "--suggested-action", "Take the suggested action.",
        "--from-repo", "test-repo-em",
    ]


def _today_iso() -> str:
    return datetime.date.today().isoformat()


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
# Test 2 — Unknown schema exits non-zero; stderr names known schemas
# ---------------------------------------------------------------------------

def test_unknown_schema_exits_nonzero() -> None:
    name = "Test 2 — unknown --schema exits non-zero, stderr names known schemas"
    with tempfile.TemporaryDirectory() as tmpdir:
        result = _run_cli(
            [
                "--schema", "notaschema",
                "--title", "X",
                "--body", "Y",
                "--status", "open",
            ],
            env={"QUEUE_APPEND_OUTPUT_ROOT": tmpdir},
            cwd=tmpdir,
        )
    if result.returncode == 0:
        fail_test(name, "expected non-zero exit for unknown schema; got 0")
        return
    combined = result.stdout + result.stderr
    # stderr should name at least one of the known schemas.
    if "debt-backlog" not in combined and "bug-backlog" not in combined and "improvement-queue" not in combined:
        fail_test(name, f"stderr does not name any known schema. stderr: {result.stderr!r}")
        return
    pass_test(name)


# ---------------------------------------------------------------------------
# Test 3 — Missing required field exits non-zero; stderr names a missing field
# ---------------------------------------------------------------------------

def test_missing_required_field_exits_nonzero() -> None:
    name = "Test 3 — missing required field exits non-zero, stderr names the field"
    # debt-backlog requires: source, risk, suggested_action (beyond universal fields).
    # Omit all three; the CLI should reject with one named.
    with tempfile.TemporaryDirectory() as tmpdir:
        result = _run_cli(
            [
                "--schema", "debt-backlog",
                "--title", "T",
                "--body", "B",
                "--status", "open",
                "--from-repo", "test-repo-em",
                # Missing: --source, --risk, --suggested-action
            ],
            env={"QUEUE_APPEND_OUTPUT_ROOT": tmpdir},
            cwd=tmpdir,
        )
    if result.returncode == 0:
        fail_test(name, "expected non-zero exit for missing required fields; got 0")
        return
    combined = result.stdout + result.stderr
    # At least one of the missing field names should appear in the output.
    missing_field_names = ("source", "risk", "suggested-action", "suggested_action")
    if not any(f in combined.lower() for f in missing_field_names):
        fail_test(
            name,
            f"error output does not name any missing field. stderr: {result.stderr!r}",
        )
        return
    pass_test(name)


# ---------------------------------------------------------------------------
# Test 4 — Invalid enum value exits non-zero; stderr lists valid status values
# ---------------------------------------------------------------------------

def test_invalid_enum_value_exits_nonzero() -> None:
    name = "Test 4 — invalid --status value exits non-zero, stderr names valid values"
    with tempfile.TemporaryDirectory() as tmpdir:
        # Note: enum validation runs before file I/O, so invalid enum exits before writing.
        # QUEUE_APPEND_OUTPUT_ROOT is set but the CLI should reject before touching the FS.
        result = _run_cli(
            [
                "--schema", "debt-backlog",
                "--title", "T",
                "--body", "B",
                "--status", "not-a-valid-status",
                "--source", "daily-review/test",
                "--risk", "Some risk.",
                "--suggested-action", "Some action.",
                "--from-repo", "test-repo-em",
            ],
            env={"QUEUE_APPEND_OUTPUT_ROOT": tmpdir},
            cwd=tmpdir,
        )
    if result.returncode == 0:
        fail_test(name, "expected non-zero exit for invalid --status; got 0")
        return
    combined = result.stdout + result.stderr
    # stderr should name at least one valid status value.
    if "open" not in combined:
        fail_test(
            name,
            f"error output should name valid status values (e.g. 'open'). stderr: {result.stderr!r}",
        )
        return
    pass_test(name)


# ---------------------------------------------------------------------------
# Test 5 — Valid write: exits 0, file exists at expected path, YAML has required fields
# ---------------------------------------------------------------------------

_DEBT_BACKLOG_REQUIRED_YAML_FIELDS = (
    "id",
    "created",
    "source",
    "status",
    "title",
    "body",
    "risk",
    "suggested_action",
)


def test_valid_write_creates_yaml_file() -> None:
    name = "Test 5 — valid debt-backlog write exits 0, file exists with required fields"
    with tempfile.TemporaryDirectory() as tmpdir:
        # QUEUE_APPEND_OUTPUT_ROOT is the root; schema output_dir is "state/debt-backlog"
        # so the CLI constructs: <QUEUE_APPEND_OUTPUT_ROOT>/state/debt-backlog/<file>.yaml
        result = _run_cli(
            _debt_backlog_required_args(),
            env={"QUEUE_APPEND_OUTPUT_ROOT": tmpdir},
            cwd=tmpdir,
        )
        if result.returncode != 0:
            fail_test(name, f"CLI exited {result.returncode}: {result.stderr!r}")
            return

        # Expected output dir: <tmpdir>/state/debt-backlog/
        expected_dir = os.path.join(tmpdir, "state", "debt-backlog")
        if not os.path.isdir(expected_dir):
            fail_test(name, f"output directory not created: {expected_dir}")
            return

        yaml_files = [f for f in os.listdir(expected_dir) if f.endswith(".yaml")]
        if len(yaml_files) != 1:
            fail_test(name, f"expected exactly 1 YAML file; found {len(yaml_files)}: {yaml_files}")
            return

        yaml_path = os.path.join(expected_dir, yaml_files[0])
        if os.path.getsize(yaml_path) == 0:
            fail_test(name, f"YAML file is empty: {yaml_path}")
            return

        # File name must start with today's ISO date.
        today = _today_iso()
        if not yaml_files[0].startswith(today):
            fail_test(name, f"YAML filename does not start with today's date ({today}): {yaml_files[0]}")
            return

        try:
            parsed = _parse_yaml_file(yaml_path)
        except RuntimeError as exc:
            fail_test(name, f"YAML parse error: {exc}")
            return

        missing = [f for f in _DEBT_BACKLOG_REQUIRED_YAML_FIELDS if f not in parsed]
        if missing:
            fail_test(name, f"YAML missing required fields: {missing}. Parsed: {parsed}")
            return

        pass_test(name)


# ---------------------------------------------------------------------------
# Test 6 — Roundtrip: emitted YAML is well-formed; all passed values preserved
# ---------------------------------------------------------------------------

def test_roundtrip_yaml_parseable() -> None:
    name = "Test 6 — roundtrip: emitted YAML is well-formed and field values match"
    title = "Roundtrip test entry for queue-append"
    body = "This is the roundtrip body. It verifies field preservation."
    source = "daily-review/roundtrip/2026-06-15"
    risk = "Missing roundtrip would break YAML fidelity guarantee."
    suggested_action = "Confirm all fields survive the emit-parse cycle."
    status = "open"

    with tempfile.TemporaryDirectory() as tmpdir:
        result = _run_cli(
            [
                "--schema", "debt-backlog",
                "--title", title,
                "--body", body,
                "--status", status,
                "--source", source,
                "--risk", risk,
                "--suggested-action", suggested_action,
                "--from-repo", "test-repo-em",
            ],
            env={"QUEUE_APPEND_OUTPUT_ROOT": tmpdir},
            cwd=tmpdir,
        )
        if result.returncode != 0:
            fail_test(name, f"CLI exited {result.returncode}: {result.stderr!r}")
            return

        expected_dir = os.path.join(tmpdir, "state", "debt-backlog")
        yaml_files = [f for f in os.listdir(expected_dir) if f.endswith(".yaml")]
        if len(yaml_files) != 1:
            fail_test(name, f"expected 1 YAML file; got {len(yaml_files)}")
            return

        yaml_path = os.path.join(expected_dir, yaml_files[0])
        try:
            parsed = _parse_yaml_file(yaml_path)
        except RuntimeError as exc:
            fail_test(name, f"YAML parse error: {exc}")
            return

        # Verify scalar field values round-trip exactly.
        checks = [
            ("title", title),
            ("body", body),
            ("status", status),
            ("source", source),
            ("risk", risk),
            ("suggested_action", suggested_action),
        ]
        for field, expected in checks:
            got = parsed.get(field)
            if got != expected:
                fail_test(name, f"field {field!r}: expected {expected!r}, got {got!r}")
                return

        # id must be a non-empty string (uuid4 auto-generated).
        entry_id = parsed.get("id", "")
        if not entry_id:
            fail_test(name, f"id field is empty or absent: {entry_id!r}")
            return

        # created must be a non-empty date string.
        created = parsed.get("created", "")
        if not created:
            fail_test(name, f"created field is empty or absent: {created!r}")
            return

        pass_test(name)


# ---------------------------------------------------------------------------
# Test 7 — Schema-doc-not-runtime-parsed (the Staff Engineer F0 guard)
# ---------------------------------------------------------------------------

def test_schema_doc_not_runtime_parsed() -> None:
    """Confirm the CLI does NOT read docs/wiki/<schema>-schema.md at runtime.

    Mechanism: set up a tmpdir as cwd with no docs/wiki/ subtree at all, then
    invoke a valid debt-backlog write. If the CLI tries to open that file, it
    would fail. If the SCHEMAS dict is hardcoded (per the negative-spec), the
    write succeeds regardless.
    """
    name = "Test 7 — schema docs not read at runtime (the Staff Engineer F0 guard)"
    with tempfile.TemporaryDirectory() as tmpdir:
        # Confirm there is no docs/wiki/ under tmpdir (it's a fresh tmpdir).
        wiki_path = os.path.join(tmpdir, "docs", "wiki", "debt-backlog-schema.md")
        if os.path.exists(wiki_path):
            # Shouldn't happen in a fresh tmpdir, but be defensive.
            os.remove(wiki_path)

        result = _run_cli(
            _debt_backlog_required_args(),
            env={"QUEUE_APPEND_OUTPUT_ROOT": tmpdir},
            cwd=tmpdir,
        )
        if result.returncode != 0:
            fail_test(
                name,
                f"CLI failed with no schema-doc present (exit {result.returncode}). "
                f"CLI may be reading the wiki doc at runtime. stderr: {result.stderr!r}",
            )
            return

        # Confirm a YAML file was actually produced (not a silent success with no write).
        expected_dir = os.path.join(tmpdir, "state", "debt-backlog")
        yaml_files = [f for f in os.listdir(expected_dir) if f.endswith(".yaml")] if os.path.isdir(expected_dir) else []
        if not yaml_files:
            fail_test(name, "CLI exited 0 but no YAML file was produced.")
            return

        pass_test(name)


# ---------------------------------------------------------------------------
# Test 8 — Explicit --id with invalid prefix pattern exits non-zero
# ---------------------------------------------------------------------------

def test_id_prefix_pattern_enforced_on_explicit_id() -> None:
    name = "Test 8 — invalid explicit --id format exits non-zero, stderr names pattern"
    with tempfile.TemporaryDirectory() as tmpdir:
        result = _run_cli(
            [
                "--schema", "debt-backlog",
                "--id", "invalid-format",   # Does not match ^(DSR|CDX|BS)-YYYY-MM-DD-N$
                "--title", "T",
                "--body", "B",
                "--status", "open",
                "--source", "daily-review/test",
                "--risk", "Some risk.",
                "--suggested-action", "Some action.",
                "--from-repo", "test-repo-em",
            ],
            env={"QUEUE_APPEND_OUTPUT_ROOT": tmpdir},
            cwd=tmpdir,
        )
    if result.returncode == 0:
        fail_test(name, "expected non-zero exit for invalid --id format; got 0")
        return
    combined = result.stdout + result.stderr
    # stderr should reference the pattern constraint.
    if "pattern" not in combined.lower() and "id_prefix_pattern" not in combined.lower():
        fail_test(
            name,
            f"stderr does not name the id_prefix_pattern constraint. stderr: {result.stderr!r}",
        )
        return
    pass_test(name)


# ---------------------------------------------------------------------------
# Test 9 — central queue_scope writes to CLAUDE_HOME, not cwd
# ---------------------------------------------------------------------------

def _improvement_queue_required_args(extra: list[str] | None = None) -> list[str]:
    """Return the minimal valid CLI args for an improvement-queue entry."""
    args = [
        "--schema", "improvement-queue",
        "--title", "Test central improvement entry",
        "--body", "Body describing the improvement.",
        "--surface", "state/lessons.md:42",
        "--proposed-target", "plugins/coordinator/skills/workstream-complete/SKILL.md",
        "--change-kind", "skill-edit",
        "--status", "open",
        "--from-repo", "test-repo-em",
    ]
    if extra:
        args.extend(extra)
    return args


def test_central_scope_writes_to_claude_home() -> None:
    """With CLAUDE_HOME set (no QUEUE_APPEND_OUTPUT_ROOT), --queue-scope central must write
    to <CLAUDE_HOME>/state/improvement-queue/, even when cwd is a different tmpdir.

    This is the load-bearing fix: a session in a sibling repo must not write central
    entries into the sibling's state/improvement-queue/ — they must always land in
    the meta-repo.

    Spec backlink: docs/plans/2026-06-23-stale-doctrine-central-queue-fix.md § Part 1 test
    """
    name = "Test 9a — --queue-scope central writes to CLAUDE_HOME, not cwd"
    with tempfile.TemporaryDirectory() as claude_home_dir, \
         tempfile.TemporaryDirectory() as sibling_cwd:
        # claude_home_dir simulates ~/.claude; sibling_cwd simulates a sibling repo.
        env = {"CLAUDE_HOME": claude_home_dir}
        # Do NOT set QUEUE_APPEND_OUTPUT_ROOT — that would override the central redirect.

        result = _run_cli(
            _improvement_queue_required_args(["--queue-scope", "central"]),
            env=env,
            cwd=sibling_cwd,
        )
        if result.returncode != 0:
            fail_test(name, f"CLI exited {result.returncode}: {result.stderr!r}")
            return

        # Entry must be under CLAUDE_HOME, not under sibling_cwd.
        expected_dir = os.path.join(claude_home_dir, "state", "improvement-queue")
        if not os.path.isdir(expected_dir):
            fail_test(name, f"expected output dir not created under CLAUDE_HOME: {expected_dir}")
            return

        yaml_files = [f for f in os.listdir(expected_dir) if f.endswith(".yaml")]
        if len(yaml_files) != 1:
            fail_test(name, f"expected 1 YAML in CLAUDE_HOME; found {len(yaml_files)}: {yaml_files}")
            return

        # Confirm nothing was written to the sibling cwd.
        sibling_queue_dir = os.path.join(sibling_cwd, "state", "improvement-queue")
        if os.path.isdir(sibling_queue_dir):
            sibling_files = [f for f in os.listdir(sibling_queue_dir) if f.endswith(".yaml")]
            if sibling_files:
                fail_test(name, f"YAML written to sibling cwd (wrong): {sibling_files}")
                return

        # Review: code-reviewer — F4: verify YAML content, not just file location.
        # queue_scope must be "central" and from_repo must match the passed value.
        yaml_path = os.path.join(expected_dir, yaml_files[0])
        try:
            parsed = _parse_yaml_file(yaml_path)
        except RuntimeError as exc:
            fail_test(name, f"YAML parse error: {exc}")
            return

        got_scope = parsed.get("queue_scope")
        if got_scope != "central":
            fail_test(name, f"expected queue_scope='central' in YAML; got {got_scope!r}")
            return

        got_from_repo = parsed.get("from_repo")
        if got_from_repo != "test-repo-em":
            fail_test(name, f"expected from_repo='test-repo-em' in YAML; got {got_from_repo!r}")
            return

        pass_test(name)


def test_project_scope_still_writes_cwd_relative() -> None:
    """Regression guard: project-scoped improvement-queue writes must remain cwd-relative.

    Ensure the central-scope redirect does NOT affect the default project-scope path.
    """
    name = "Test 9b — project scope (default) still writes cwd-relative (regression guard)"
    with tempfile.TemporaryDirectory() as claude_home_dir, \
         tempfile.TemporaryDirectory() as project_cwd:
        # Set CLAUDE_HOME to a different dir to confirm it is NOT used for project scope.
        env = {"CLAUDE_HOME": claude_home_dir}

        result = _run_cli(
            _improvement_queue_required_args(),  # no --queue-scope → defaults to project
            env=env,
            cwd=project_cwd,
        )
        if result.returncode != 0:
            fail_test(name, f"CLI exited {result.returncode}: {result.stderr!r}")
            return

        # Entry must be under project_cwd, not under claude_home_dir.
        expected_dir = os.path.join(project_cwd, "state", "improvement-queue")
        if not os.path.isdir(expected_dir):
            fail_test(name, f"expected output dir not created under cwd: {expected_dir}")
            return

        yaml_files = [f for f in os.listdir(expected_dir) if f.endswith(".yaml")]
        if len(yaml_files) != 1:
            fail_test(name, f"expected 1 YAML in cwd; found {len(yaml_files)}: {yaml_files}")
            return

        # Confirm nothing was written to claude_home_dir.
        home_queue_dir = os.path.join(claude_home_dir, "state", "improvement-queue")
        if os.path.isdir(home_queue_dir):
            home_files = [f for f in os.listdir(home_queue_dir) if f.endswith(".yaml")]
            if home_files:
                fail_test(name, f"YAML written to CLAUDE_HOME (wrong for project scope): {home_files}")
                return

        # Review: code-reviewer — F5: verify queue_scope is absent or None in project-scope output.
        # _build_yaml skips None-valued optional fields, so queue_scope must not appear in the YAML.
        yaml_path = os.path.join(expected_dir, yaml_files[0])
        try:
            parsed = _parse_yaml_file(yaml_path)
        except RuntimeError as exc:
            fail_test(name, f"YAML parse error: {exc}")
            return

        got_scope = parsed.get("queue_scope")
        if got_scope is not None and got_scope != "" and got_scope != "null":
            fail_test(name, f"expected queue_scope absent/None in project-scope YAML; got {got_scope!r}")
            return

        pass_test(name)


# ---------------------------------------------------------------------------
# Test 10 — --queue-scope central rejected for non-improvement-queue schemas (F1 guard)
# ---------------------------------------------------------------------------

def test_queue_scope_central_rejected_for_non_improvement_schemas() -> None:
    """Review: code-reviewer — F1: --schema debt-backlog --queue-scope central must exit non-zero.

    Without the schema guard, a caller could silently redirect debt-backlog entries
    into ~/.claude/state/debt-backlog/ — wrong semantics, undocumented behaviour.
    """
    name = "Test 10 — --queue-scope central rejected for non-improvement-queue schemas"
    with tempfile.TemporaryDirectory() as tmpdir:
        result = _run_cli(
            [
                "--schema", "debt-backlog",
                "--queue-scope", "central",
                "--title", "T",
                "--body", "B",
                "--status", "open",
                "--source", "daily-review/test",
                "--risk", "Some risk.",
                "--suggested-action", "Some action.",
                "--from-repo", "test-repo-em",
            ],
            env={"QUEUE_APPEND_OUTPUT_ROOT": tmpdir},
            cwd=tmpdir,
        )
    if result.returncode == 0:
        fail_test(name, "--schema debt-backlog --queue-scope central should exit non-zero; got 0")
        return
    combined = result.stdout + result.stderr
    if "improvement-queue" not in combined:
        fail_test(
            name,
            f"error output should mention 'improvement-queue' as the only valid schema. stderr: {result.stderr!r}",
        )
        return
    pass_test(name)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    print("coordinator-queue-append.test.py")
    print("=" * 50)

    test_help_exits_zero()
    test_unknown_schema_exits_nonzero()
    test_missing_required_field_exits_nonzero()
    test_invalid_enum_value_exits_nonzero()
    test_valid_write_creates_yaml_file()
    test_roundtrip_yaml_parseable()
    test_schema_doc_not_runtime_parsed()
    test_id_prefix_pattern_enforced_on_explicit_id()
    test_central_scope_writes_to_claude_home()
    test_project_scope_still_writes_cwd_relative()
    test_queue_scope_central_rejected_for_non_improvement_schemas()

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
