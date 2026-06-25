"""
test_machine_local.py — unit tests for _machine_local.py reader + cmd_set.

Spec backlink: docs/plans/2026-05-21-unreal-concern-ownership-3-repo.md §Chunk 1 + Chunk 1.6
Purpose: Verify reader correctness for self-named-table elision, nested-dict flatten,
         concern backward-compat, and cmd_set Windows-path round-trip + upgrade-path behavior.

Isolation: every test uses a fresh sandbox directory via MACHINE_LOCAL_REGISTRY_DIR,
           never touching the operator's real ~/.claude/machine-local/.

Negative-spec: these tests do NOT import _machine_local.py directly — they shell out to
               the `machine-local` CLI, matching the contract-surface that real callers use.
"""

import os
import sys
import shutil
import subprocess
import tempfile
import tomllib
import textwrap
import pytest


# ---------------------------------------------------------------------------
# Sandbox helpers
# ---------------------------------------------------------------------------

# Locate the machine-local CLI and the Python implementation under test.
_HERE = os.path.dirname(os.path.abspath(__file__))
_BIN_DIR = os.path.normpath(os.path.join(_HERE, "..", "templates", "bin"))
_ML_PY = os.path.join(_BIN_DIR, "_machine_local.py")
_ML_WRAPPER = os.path.join(_BIN_DIR, "machine-local")
# Live (meta-repo) bin/ copy — present only in ~/.claude, absent in the OSS
# coordinator-claude distribution. Parity tests against it skip when absent.
_LIVE_BIN_DIR = os.path.normpath(os.path.join(_HERE, "..", "..", "..", "..", "bin"))

# The CLI wrapper on non-Windows is "machine-local" (shell script); on Windows it's
# "machine-local.cmd". For cross-platform test portability, invoke the Python
# implementation directly via `python _machine_local.py <subcommand>`.
_PYTHON = sys.executable


def _run_ml(sandbox: str, args: list[str]) -> subprocess.CompletedProcess:
    """Run machine-local CLI in the given sandbox directory."""
    env = {**os.environ, "MACHINE_LOCAL_REGISTRY_DIR": sandbox}
    return subprocess.run(
        [_PYTHON, _ML_PY] + args,
        capture_output=True,
        text=True,
        env=env,
    )


def _write_file(path: str, content: str) -> None:
    """Write a text file, creating parent directories as needed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _seed_registry(sandbox: str, concerns: list[str] | None = None) -> None:
    """Seed a minimal registry.toml in the sandbox."""
    concerns_line = ""
    if concerns:
        concern_list = ", ".join(f'"{c}"' for c in concerns)
        concerns_line = f"concerns = [{concern_list}]\n"
    _write_file(
        os.path.join(sandbox, "registry.toml"),
        f"schema = 1\n{concerns_line}",
    )


# ---------------------------------------------------------------------------
# AC-2a: Self-named top-level table elision in concern file
# ---------------------------------------------------------------------------

class TestSelfNamedTableElision:
    """[unreal] inside unreal.local.toml resolves as unreal.install_root."""

    def test_self_named_table_resolves_without_doubling(self, tmp_path):
        """[unreal] table in unreal.local.toml → unreal.install_root, not unreal.unreal.install_root."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox, concerns=["unreal"])
        _write_file(
            os.path.join(sandbox, "unreal.local.toml"),
            "[unreal]\ninstall_root = 'E:/dev/UE'\n",
        )
        result = _run_ml(sandbox, ["get", "unreal.install_root"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert result.stdout.strip() == "E:/dev/UE"

    def test_doubled_prefix_does_not_resolve(self, tmp_path):
        """unreal.unreal.install_root is NOT a valid key after self-named elision."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox, concerns=["unreal"])
        _write_file(
            os.path.join(sandbox, "unreal.local.toml"),
            "[unreal]\ninstall_root = 'E:/dev/UE'\n",
        )
        result = _run_ml(sandbox, ["get", "unreal.unreal.install_root"])
        assert result.returncode != 0

    def test_top_level_key_in_concern_file_also_resolves(self, tmp_path):
        """install_root at top level of unreal.local.toml auto-prefixes to unreal.install_root."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox, concerns=["unreal"])
        _write_file(
            os.path.join(sandbox, "unreal.local.toml"),
            "install_root = 'E:/dev/UE'\n",
        )
        result = _run_ml(sandbox, ["get", "unreal.install_root"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert result.stdout.strip() == "E:/dev/UE"
        # Negative: bare key without concern prefix must NOT resolve.
        assert _run_ml(sandbox, ["get", "install_root"]).returncode != 0
        # Negative: doubled prefix must NOT resolve — guards against a regression
        # where top-level-key auto-prefix fires a second time on already-prefixed keys.
        assert _run_ml(sandbox, ["get", "unreal.unreal.install_root"]).returncode != 0


# ---------------------------------------------------------------------------
# AC-2b: Nested-dict flatten in registry layers
# ---------------------------------------------------------------------------

class TestRegistryNestedDictFlatten:
    """[somenamespace] inside registry.local.toml resolves via flatten."""

    def test_nested_table_in_registry_local_flattens(self, tmp_path):
        """[foo] table in registry.local.toml exposes foo.bar via get."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox)
        _write_file(
            os.path.join(sandbox, "registry.local.toml"),
            "schema = 1\n[foo]\nbar = 'baz'\n",
        )
        result = _run_ml(sandbox, ["get", "foo.bar"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert result.stdout.strip() == "baz"

    def test_nested_table_in_registry_toml_flattens(self, tmp_path):
        """[foo] table in registry.toml exposes foo.bar via get (when no concern covers it)."""
        sandbox = str(tmp_path)
        _write_file(
            os.path.join(sandbox, "registry.toml"),
            "schema = 1\n[tools]\nversion = '1.2.3'\n",
        )
        result = _run_ml(sandbox, ["get", "tools.version"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert result.stdout.strip() == "1.2.3"


# ---------------------------------------------------------------------------
# AC-2c: project_rag concern still resolves correctly
# ---------------------------------------------------------------------------

class TestProjectRagConcernUnchanged:
    """Existing project_rag concern keys still resolve (backward-compat guard)."""

    def test_project_rag_env_key_resolves(self, tmp_path):
        """project_rag.env.PROJECT_RAG_STRUCTURAL_INDEX resolves from project_rag.local.toml."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox, concerns=["project_rag"])
        _write_file(
            os.path.join(sandbox, "project_rag.local.toml"),
            textwrap.dedent("""\
                schema = 1
                [env]
                PROJECT_RAG_STRUCTURAL_INDEX = '/tmp/index.sqlite3'
            """),
        )
        result = _run_ml(sandbox, ["get", "project_rag.env.PROJECT_RAG_STRUCTURAL_INDEX"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert result.stdout.strip() == "/tmp/index.sqlite3"


# ---------------------------------------------------------------------------
# AC-3: cmd_set Windows-path round-trip
# ---------------------------------------------------------------------------

class TestCmdSetWindowsPath:
    """machine-local set with Windows paths produces literal-string TOML and round-trips cleanly."""

    def test_set_windows_path_round_trip(self, tmp_path):
        """Set a Windows path, read it back, assert byte-identical."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox)
        path_val = r"E:\dev\UnrealEngine"
        set_result = _run_ml(sandbox, ["set", "repos.foo", path_val])
        assert set_result.returncode == 0, f"stderr: {set_result.stderr}"
        get_result = _run_ml(sandbox, ["get", "repos.foo"])
        assert get_result.returncode == 0, f"stderr: {get_result.stderr}"
        assert get_result.stdout.strip() == path_val

    def test_set_writes_literal_string_form(self, tmp_path):
        """On-disk form is single-quoted TOML literal string (not double-quoted basic string)."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox)
        _run_ml(sandbox, ["set", "repos.foo", r"E:\dev\foo"])
        content = open(os.path.join(sandbox, "registry.local.toml"), encoding="utf-8").read()
        # Assert literal-string (single-quoted) form. First two disjuncts cover
        # backslash-preserved and forward-slash-normalised variants; the dropped
        # third disjunct ("E:\\dev\\foo" in content) was vacuously true because
        # raw path bytes appear inside basic-string form too — it would have
        # passed even if cmd_set was still writing the old double-quoted shape.
        assert "'E:\\dev\\foo'" in content or "'E:/dev/foo'" in content
        # Must NOT contain double-quoted basic-string form with backslash-escaped path
        assert '"E:\\\\dev\\\\foo"' not in content

    def test_unicode_in_path_round_trips(self, tmp_path):
        """Unicode in path value round-trips correctly."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox)
        path_val = "/usr/local/ué/bin"
        _run_ml(sandbox, ["set", "repos.bar", path_val])
        result = _run_ml(sandbox, ["get", "repos.bar"])
        assert result.returncode == 0
        assert result.stdout.strip() == path_val

    def test_path_with_spaces_round_trips(self, tmp_path):
        """Path with spaces round-trips correctly."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox)
        path_val = r"C:\Program Files\Epic Games\UE_5.7"
        _run_ml(sandbox, ["set", "repos.ue", path_val])
        result = _run_ml(sandbox, ["get", "repos.ue"])
        assert result.returncode == 0
        assert result.stdout.strip() == path_val

    def test_empty_string_round_trips(self, tmp_path):
        """Empty string value round-trips correctly."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox)
        _run_ml(sandbox, ["set", "repos.empty", ""])
        result = _run_ml(sandbox, ["get", "repos.empty"])
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_single_quote_in_value_refused(self, tmp_path):
        """Value containing single quote is refused with non-zero exit and named error."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox)
        result = _run_ml(sandbox, ["set", "repos.foo", "with'quote"])
        assert result.returncode != 0
        assert "single quote" in result.stderr.lower() or "literal" in result.stderr.lower()


# ---------------------------------------------------------------------------
# the Staff Engineer F7: double-set and mixed-quote-form-transition
# ---------------------------------------------------------------------------

class TestCmdSetDoubleSetAndUpgrade:
    """Exactly one entry after double-set; mixed-quote-form upgrade handled."""

    def test_literal_string_double_set_single_entry(self, tmp_path):
        """Set repos.foo twice → exactly ONE entry for repos.foo with the second value."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox)
        _run_ml(sandbox, ["set", "repos.foo", r"E:\dev\foo"])
        _run_ml(sandbox, ["set", "repos.foo", r"E:\dev\bar"])
        content = open(os.path.join(sandbox, "registry.local.toml"), encoding="utf-8").read()
        # Exactly one line matches
        matching_lines = [l for l in content.splitlines() if '"repos.foo"' in l]
        assert len(matching_lines) == 1, f"Expected 1 entry, got {len(matching_lines)}: {matching_lines}"
        get_result = _run_ml(sandbox, ["get", "repos.foo"])
        assert get_result.stdout.strip() == r"E:\dev\bar"

    def test_mixed_quote_form_transition(self, tmp_path):
        """Pre-existing basic-string form is replaced in-place by literal-string form."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox)
        # Pre-populate with old basic-string form (as written by pre-fix _machine_local.py)
        _write_file(
            os.path.join(sandbox, "registry.local.toml"),
            'schema = 1\n"repos.foo" = "basic-string-value"  # set 2026-01-01T00:00:00Z\n',
        )
        # Run set with a new value
        result = _run_ml(sandbox, ["set", "repos.foo", r"E:\dev\foo"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        content = open(os.path.join(sandbox, "registry.local.toml"), encoding="utf-8").read()
        # Exactly one entry for repos.foo
        matching_lines = [l for l in content.splitlines() if '"repos.foo"' in l]
        assert len(matching_lines) == 1, f"Expected 1 entry, got {len(matching_lines)}: {matching_lines}"
        # Entry must be in literal-string form
        assert "'" in matching_lines[0], f"Expected literal-string form, got: {matching_lines[0]}"
        # Value round-trips correctly
        get_result = _run_ml(sandbox, ["get", "repos.foo"])
        assert get_result.returncode == 0
        assert get_result.stdout.strip() == r"E:\dev\foo"


# ---------------------------------------------------------------------------
# AC1 + AC4: array-append creates / appends / idempotent-dedups, get round-trip
# ---------------------------------------------------------------------------

class TestArrayAppend:
    """array-append subcommand: AC1 and AC4."""

    def test_append_creates_array(self, tmp_path):
        """array-append creates the array key when absent."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox)
        result = _run_ml(sandbox, ["array-append", "publish.targets", "coordinator-claude|mirror"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        # File must parse and contain the element.
        content = open(os.path.join(sandbox, "registry.local.toml"), encoding="utf-8").read()
        parsed = tomllib.loads(content)
        assert parsed["publish.targets"] == ["coordinator-claude|mirror"]

    def test_append_is_idempotent(self, tmp_path):
        """array-append skips duplicate elements (exact-string dedup)."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox)
        _run_ml(sandbox, ["array-append", "publish.targets", "coordinator-claude|mirror"])
        result = _run_ml(sandbox, ["array-append", "publish.targets", "coordinator-claude|mirror"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        content = open(os.path.join(sandbox, "registry.local.toml"), encoding="utf-8").read()
        parsed = tomllib.loads(content)
        assert parsed["publish.targets"] == ["coordinator-claude|mirror"]

    def test_append_preserves_other_keys(self, tmp_path):
        """array-append does not clobber other keys in the file."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox)
        _run_ml(sandbox, ["set", "repos.foo", "existing-value"])
        _run_ml(sandbox, ["array-append", "publish.targets", "coordinator-claude|mirror"])
        get_result = _run_ml(sandbox, ["get", "repos.foo"])
        assert get_result.returncode == 0, f"stderr: {get_result.stderr}"
        assert get_result.stdout.strip() == "existing-value"

    def test_append_fails_on_scalar_collision(self, tmp_path):
        """array-append fails loud when key is already a scalar string."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox)
        _run_ml(sandbox, ["set", "publish.targets", "some-scalar-value"])
        result = _run_ml(sandbox, ["array-append", "publish.targets", "new-element"])
        assert result.returncode != 0
        # Review: code-reviewer (F8) — spec requires both message components, not OR.
        assert "scalar" in result.stderr.lower()
        assert "array-set" in result.stderr

    def test_append_multiple_elements(self, tmp_path):
        """array-append accumulates elements in insertion order."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox)
        _run_ml(sandbox, ["array-append", "publish.targets", "row1"])
        _run_ml(sandbox, ["array-append", "publish.targets", "row2"])
        _run_ml(sandbox, ["array-append", "publish.targets", "row3"])
        content = open(os.path.join(sandbox, "registry.local.toml"), encoding="utf-8").read()
        parsed = tomllib.loads(content)
        assert parsed["publish.targets"] == ["row1", "row2", "row3"]

    def test_append_single_quote_rejected(self, tmp_path):
        """array-append refuses elements containing a single quote."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox)
        result = _run_ml(sandbox, ["array-append", "publish.targets", "bad'element"])
        assert result.returncode != 0
        assert "single quote" in result.stderr.lower() or "literal" in result.stderr.lower()


# ---------------------------------------------------------------------------
# AC4: get round-trip — newline-joined, in order
# ---------------------------------------------------------------------------

class TestArrayGetRoundTrip:
    """get returns array elements newline-joined in order (AC4)."""

    def test_get_round_trip_newline_joined(self, tmp_path):
        """get publish.targets returns rows newline-joined in insertion order."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox)
        _run_ml(sandbox, ["array-append", "publish.targets", "row1"])
        _run_ml(sandbox, ["array-append", "publish.targets", "row2"])
        _run_ml(sandbox, ["array-append", "publish.targets", "row3"])
        result = _run_ml(sandbox, ["get", "publish.targets"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert result.stdout.strip() == "row1\nrow2\nrow3"


# ---------------------------------------------------------------------------
# AC2: array-set replaces / dedups
# ---------------------------------------------------------------------------

class TestArraySet:
    """array-set subcommand: AC2."""

    def test_array_set_replaces(self, tmp_path):
        """array-set replaces the entire array with the given elements."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox)
        _run_ml(sandbox, ["array-append", "publish.targets", "old-row"])
        result = _run_ml(sandbox, ["array-set", "publish.targets", "new-row1", "new-row2"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        content = open(os.path.join(sandbox, "registry.local.toml"), encoding="utf-8").read()
        parsed = tomllib.loads(content)
        assert parsed["publish.targets"] == ["new-row1", "new-row2"]

    def test_array_set_dedups_order_preserving(self, tmp_path):
        """array-set deduplicates elements while preserving order."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox)
        result = _run_ml(sandbox, ["array-set", "publish.targets", "row1", "row2", "row1", "row3"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        content = open(os.path.join(sandbox, "registry.local.toml"), encoding="utf-8").read()
        parsed = tomllib.loads(content)
        assert parsed["publish.targets"] == ["row1", "row2", "row3"]

    def test_array_set_fails_on_scalar_collision(self, tmp_path):
        """array-set fails loud when key is already a scalar string."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox)
        _run_ml(sandbox, ["set", "publish.targets", "some-scalar-value"])
        result = _run_ml(sandbox, ["array-set", "publish.targets", "new-element"])
        assert result.returncode != 0
        assert "scalar" in result.stderr.lower()

    def test_array_set_single_quote_rejected(self, tmp_path):
        """array-set refuses elements containing a single quote."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox)
        result = _run_ml(sandbox, ["array-set", "publish.targets", "bad'element"])
        assert result.returncode != 0
        assert "single quote" in result.stderr.lower() or "literal" in result.stderr.lower()


# ---------------------------------------------------------------------------
# AC1: --dry-run writes nothing
# ---------------------------------------------------------------------------

class TestArrayDryRun:
    """--dry-run flag: no file mutations (AC1)."""

    def test_dry_run_array_append_writes_nothing(self, tmp_path):
        """array-append --dry-run does not create or modify the registry file."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox)
        registry_local = os.path.join(sandbox, "registry.local.toml")
        # Ensure no registry.local.toml exists before dry-run.
        assert not os.path.exists(registry_local)
        result = _run_ml(sandbox, ["array-append", "--dry-run", "publish.targets", "row1"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert not os.path.exists(registry_local), "dry-run must not create the file"

    def test_dry_run_array_set_writes_nothing(self, tmp_path):
        """array-set --dry-run does not create or modify the registry file."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox)
        registry_local = os.path.join(sandbox, "registry.local.toml")
        assert not os.path.exists(registry_local)
        result = _run_ml(sandbox, ["array-set", "--dry-run", "publish.targets", "row1"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert not os.path.exists(registry_local), "dry-run must not create the file"


# ---------------------------------------------------------------------------
# AC3: set fails loud on array key (F1 guard)
# ---------------------------------------------------------------------------

class TestSetFailsOnArrayKey:
    """cmd_set guard F1: fail loud when key resolves to a list (AC3)."""

    def test_set_on_array_key_fails_loud(self, tmp_path):
        """set on a key that is already an array fails with actionable message."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox)
        # First create the array.
        _run_ml(sandbox, ["array-append", "publish.targets", "existing-row"])
        # Now attempt set — must fail.
        result = _run_ml(sandbox, ["set", "publish.targets", "overwrite-attempt"])
        assert result.returncode != 0
        # Assert exact message text (F1: must say "is an array" and name the commands).
        assert "is an array" in result.stderr
        assert "array-append" in result.stderr
        assert "array-set" in result.stderr


# ---------------------------------------------------------------------------
# AC3 + F2: array-of-tables and inline-table collision fail loud
# ---------------------------------------------------------------------------

class TestArrayWriteCollisionShapes:
    """F2 additional required tests: array-of-tables and inline-table collisions."""

    def test_array_append_fails_on_array_of_tables(self, tmp_path):
        """array-append fails loud with actionable message when key is array-of-tables."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox)
        _write_file(
            os.path.join(sandbox, "registry.local.toml"),
            "schema = 1\n[[publish.targets]]\nname = 'row1'\n",
        )
        result = _run_ml(sandbox, ["array-append", "publish.targets", "new-row"])
        assert result.returncode != 0
        # Assert actionable message text.
        assert "array-of-tables" in result.stderr or "[[" in result.stderr

    def test_array_set_fails_on_array_of_tables(self, tmp_path):
        """array-set fails loud with actionable message when key is array-of-tables."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox)
        _write_file(
            os.path.join(sandbox, "registry.local.toml"),
            "schema = 1\n[[publish.targets]]\nname = 'row1'\n",
        )
        result = _run_ml(sandbox, ["array-set", "publish.targets", "new-row"])
        assert result.returncode != 0
        assert "array-of-tables" in result.stderr or "[[" in result.stderr

    def test_array_append_fails_on_inline_table(self, tmp_path):
        """array-append fails loud with actionable message when key is inline table."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox)
        _write_file(
            os.path.join(sandbox, "registry.local.toml"),
            'schema = 1\n"publish.targets" = {name = "row1"}\n',
        )
        result = _run_ml(sandbox, ["array-append", "publish.targets", "new-row"])
        assert result.returncode != 0
        assert "inline table" in result.stderr.lower() or "hand-edit" in result.stderr.lower()

    def test_array_set_fails_on_inline_table(self, tmp_path):
        """array-set fails loud with actionable message when key is inline table."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox)
        _write_file(
            os.path.join(sandbox, "registry.local.toml"),
            'schema = 1\n"publish.targets" = {name = "row1"}\n',
        )
        result = _run_ml(sandbox, ["array-set", "publish.targets", "new-row"])
        assert result.returncode != 0
        assert "inline table" in result.stderr.lower() or "hand-edit" in result.stderr.lower()


# ---------------------------------------------------------------------------
# F2(c)(d): replace-span correctness — no duplicate definitions
# ---------------------------------------------------------------------------

class TestArrayReplaceSpan:
    """F2(c)(d): array-append/array-set replaces the span; tomllib sees exactly one definition."""

    def test_array_append_replaces_existing_span(self, tmp_path):
        """array-append against an existing multi-line array replaces the span (no dup)."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox)
        # Seed a multi-row array directly.
        _write_file(
            os.path.join(sandbox, "registry.local.toml"),
            textwrap.dedent("""\
                schema = 1
                # array-append 2026-01-01T00:00:00Z
                "publish.targets" = [
                  'row1',
                  'row2',
                ]
            """),
        )
        result = _run_ml(sandbox, ["array-append", "publish.targets", "row3"])
        assert result.returncode == 0, f"stderr: {result.stderr}"

        content = open(os.path.join(sandbox, "registry.local.toml"), encoding="utf-8").read()

        # Exactly one definition via tomllib — duplicate-definition detection.
        parsed = tomllib.loads(content)
        raw_val = parsed.get("publish.targets")
        assert isinstance(raw_val, list), f"Expected list, got {type(raw_val)}: {raw_val!r}"
        assert len(raw_val) == 3, f"Expected 3 elements, got {len(raw_val)}: {raw_val}"

        # get round-trip returns rows in order.
        get_result = _run_ml(sandbox, ["get", "publish.targets"])
        assert get_result.returncode == 0
        assert get_result.stdout.strip() == "row1\nrow2\nrow3"

    def test_array_set_replaces_n_row_array(self, tmp_path):
        """array-set replaces an N-row array; tomllib and reader agree."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox)
        _write_file(
            os.path.join(sandbox, "registry.local.toml"),
            textwrap.dedent("""\
                schema = 1
                # array-append 2026-01-01T00:00:00Z
                "publish.targets" = [
                  'old1',
                  'old2',
                  'old3',
                ]
            """),
        )
        result = _run_ml(sandbox, ["array-set", "publish.targets", "new1", "new2"])
        assert result.returncode == 0, f"stderr: {result.stderr}"

        content = open(os.path.join(sandbox, "registry.local.toml"), encoding="utf-8").read()
        parsed = tomllib.loads(content)
        raw_val = parsed.get("publish.targets")
        assert isinstance(raw_val, list), f"Expected list, got {type(raw_val)!r}"
        assert raw_val == ["new1", "new2"], f"Expected [new1, new2], got {raw_val!r}"

        # Old rows must be gone.
        assert "old1" not in content
        assert "old2" not in content
        assert "old3" not in content

        # get round-trip.
        get_result = _run_ml(sandbox, ["get", "publish.targets"])
        assert get_result.returncode == 0
        assert get_result.stdout.strip() == "new1\nnew2"

    # Review: code-reviewer (F3) — provenance-comment preservation tests.

    def test_array_append_preserves_provenance_comment(self, tmp_path):
        """array-append preserves a pre-existing # array-append <date> comment above the array."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox)
        original_comment = "# array-append 2026-01-01T00:00:00Z"
        _write_file(
            os.path.join(sandbox, "registry.local.toml"),
            textwrap.dedent(f"""\
                schema = 1
                {original_comment}
                "publish.targets" = [
                  'row1',
                ]
            """),
        )
        result = _run_ml(sandbox, ["array-append", "publish.targets", "row2"])
        assert result.returncode == 0, f"stderr: {result.stderr}"

        raw_content = open(os.path.join(sandbox, "registry.local.toml"), encoding="utf-8").read()
        # Original comment line must still be present verbatim.
        assert original_comment in raw_content, (
            f"Expected provenance comment {original_comment!r} preserved in:\n{raw_content}"
        )

    def test_array_set_preserves_provenance_comment(self, tmp_path):
        """array-set preserves a pre-existing # array-append <date> comment above the array."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox)
        original_comment = "# array-append 2026-01-01T00:00:00Z"
        _write_file(
            os.path.join(sandbox, "registry.local.toml"),
            textwrap.dedent(f"""\
                schema = 1
                {original_comment}
                "publish.targets" = [
                  'old-row',
                ]
            """),
        )
        result = _run_ml(sandbox, ["array-set", "publish.targets", "new-row"])
        assert result.returncode == 0, f"stderr: {result.stderr}"

        raw_content = open(os.path.join(sandbox, "registry.local.toml"), encoding="utf-8").read()
        # Original comment line must still be present verbatim.
        assert original_comment in raw_content, (
            f"Expected provenance comment {original_comment!r} preserved in:\n{raw_content}"
        )


# ---------------------------------------------------------------------------
# set --concern <name> <key> <value> — namespaced concern-file writer
# Spec backlink: cross-repo memo 2026-06-23-machine-local-concern-set-writer.md
# (project-rag-ue-addon-em ask; dogfood finding #3).
# ---------------------------------------------------------------------------

class TestSetConcernWriter:
    """machine-local set --concern writes namespaced keys into <name>.local.toml."""

    def _read_concern(self, sandbox: str, name: str) -> dict:
        with open(os.path.join(sandbox, f"{name}.local.toml"), encoding="utf-8") as f:
            return tomllib.loads(f.read())

    def test_writes_and_round_trips_via_get(self, tmp_path):
        sandbox = str(tmp_path)
        _seed_registry(sandbox, concerns=["unreal"])
        w = _run_ml(sandbox, ["set", "--concern", "unreal", "unreal.samples_root", "/x/Lyra"])
        assert w.returncode == 0, f"stderr: {w.stderr}"
        g = _run_ml(sandbox, ["get", "unreal.samples_root"])
        assert g.returncode == 0, f"stderr: {g.stderr}"
        assert g.stdout.strip() == "/x/Lyra"

    def test_written_under_self_named_table(self, tmp_path):
        """Writer emits the [unreal] table form (not flat dotted) so the reader elides correctly."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox, concerns=["unreal"])
        _run_ml(sandbox, ["set", "--concern", "unreal", "unreal.samples_root", "/x/Lyra"])
        data = self._read_concern(sandbox, "unreal")
        assert data.get("unreal", {}).get("samples_root") == "/x/Lyra"
        # No double-prefixed flat key.
        assert "unreal.samples_root" not in data

    def test_preserves_existing_keys(self, tmp_path):
        sandbox = str(tmp_path)
        _seed_registry(sandbox, concerns=["unreal"])
        _run_ml(sandbox, ["set", "--concern", "unreal", "unreal.samples_root", "/x/Lyra"])
        _run_ml(sandbox, ["set", "--concern", "unreal", "unreal.install_root", "/x/UE"])
        assert _run_ml(sandbox, ["get", "unreal.samples_root"]).stdout.strip() == "/x/Lyra"
        assert _run_ml(sandbox, ["get", "unreal.install_root"]).stdout.strip() == "/x/UE"

    def test_upsert_overwrites_same_key(self, tmp_path):
        sandbox = str(tmp_path)
        _seed_registry(sandbox, concerns=["unreal"])
        _run_ml(sandbox, ["set", "--concern", "unreal", "unreal.samples_root", "/x/old"])
        _run_ml(sandbox, ["set", "--concern", "unreal", "unreal.samples_root", "/x/new"])
        assert _run_ml(sandbox, ["get", "unreal.samples_root"]).stdout.strip() == "/x/new"
        # Exactly one definition (no duplicate).
        data = self._read_concern(sandbox, "unreal")
        assert data["unreal"]["samples_root"] == "/x/new"

    def test_provenance_stamped(self, tmp_path):
        sandbox = str(tmp_path)
        _seed_registry(sandbox, concerns=["unreal"])
        _run_ml(sandbox, ["set", "--concern", "unreal", "unreal.samples_root", "/x/Lyra"])
        data = self._read_concern(sandbox, "unreal")
        prov = data.get("provenance", {}).get("samples_root", {})
        assert prov.get("written_by") == "machine-local"
        assert prov.get("source") == "cli:--concern"
        assert prov.get("written_at")

    def test_cross_concern_key_rejected(self, tmp_path):
        """--concern unreal with a hardware.* key is refused (no cross-concern pollution)."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox, concerns=["unreal", "hardware"])
        r = _run_ml(sandbox, ["set", "--concern", "unreal", "hardware.cores", "24"])
        assert r.returncode == 1
        assert "not under concern namespace" in r.stderr

    def test_global_flag_rejected(self, tmp_path):
        sandbox = str(tmp_path)
        _seed_registry(sandbox, concerns=["unreal"])
        r = _run_ml(sandbox, ["set", "--concern", "unreal", "--global", "unreal.x", "y"])
        assert r.returncode == 1
        assert "mutually exclusive" in r.stderr

    def test_bare_set_still_refuses_concern_key(self, tmp_path):
        """D0 negative-spec preserved: bare `set <concern.key>` WITHOUT --concern still refuses
        (the --concern flag is an additive carve-out, not a relaxation of the registry path)."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox, concerns=["unreal"])
        r = _run_ml(sandbox, ["set", "unreal.samples_root", "/x/Lyra"])
        assert r.returncode == 1
        assert "concern namespace" in r.stderr
        # And it did NOT fall through to writing the concern file.
        assert not os.path.exists(os.path.join(sandbox, "unreal.local.toml"))

    def test_unregistered_concern_warns_but_writes(self, tmp_path):
        """Writing to an unregistered concern emits a note but still writes the file."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox, concerns=["unreal"])  # 'hardware' not registered
        r = _run_ml(sandbox, ["set", "--concern", "hardware", "hardware.cores", "24"])
        assert r.returncode == 0, f"stderr: {r.stderr}"
        assert "not in the `concerns` array" in r.stderr
        assert os.path.exists(os.path.join(sandbox, "hardware.local.toml"))

    def test_single_quote_value_refused(self, tmp_path):
        sandbox = str(tmp_path)
        _seed_registry(sandbox, concerns=["unreal"])
        r = _run_ml(sandbox, ["set", "--concern", "unreal", "unreal.x", "has'quote"])
        assert r.returncode == 1
        assert "single quote" in r.stderr

    def test_dry_run_writes_nothing(self, tmp_path):
        sandbox = str(tmp_path)
        _seed_registry(sandbox, concerns=["unreal"])
        r = _run_ml(sandbox, ["set", "--concern", "unreal", "unreal.samples_root", "/x/Lyra", "--dry-run"])
        assert r.returncode == 0
        assert not os.path.exists(os.path.join(sandbox, "unreal.local.toml"))

    def test_dotted_bare_key_nests(self, tmp_path):
        """A dotted bare key (unreal.versions.lyra) nests as a sub-table and resolves."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox, concerns=["unreal"])
        _run_ml(sandbox, ["set", "--concern", "unreal", "unreal.versions.lyra", "5.3"])
        assert _run_ml(sandbox, ["get", "unreal.versions.lyra"]).stdout.strip() == "5.3"

    def test_value_with_spaces_round_trips(self, tmp_path):
        sandbox = str(tmp_path)
        _seed_registry(sandbox, concerns=["unreal"])
        _run_ml(sandbox, ["set", "--concern", "unreal", "unreal.samples_root", "/x/Lyra Samples"])
        assert _run_ml(sandbox, ["get", "unreal.samples_root"]).stdout.strip() == "/x/Lyra Samples"


class TestSetConcernCrossWriterInterop:
    """the Staff Engineer review (2026-06-23) — type/provenance preservation across the addon↔coordinator
    two-serializer wire contract (DR-CONTRACT-001). The P1 regression net lands here.
    """

    def _seed_addon_style(self, sandbox: str) -> None:
        """Emulate an addon-seeded unreal.local.toml: an integer contract-witness
        (emit_shape_version), a string key, a nested binary-engines sub-table, and
        provenance with source='constant'.
        """
        _seed_registry(sandbox, concerns=["unreal"])
        _write_file(
            os.path.join(sandbox, "unreal.local.toml"),
            textwrap.dedent("""\
                schema = 1

                [unreal]
                emit_shape_version = 1
                install_root = 'E:/dev/UE'

                [unreal.engines]
                5_3 = 'E:/dev/UE/5.3'

                [provenance.emit_shape_version]
                written_by = '_seed_unreal_keys.py'
                written_at = '2026-06-23T00:00:00Z'
                source = 'constant'
            """),
        )

    def test_int_witness_type_preserved_across_write(self, tmp_path):
        """P1 REGRESSION: a --concern write of an unrelated key must NOT coerce the
        addon's integer emit_shape_version to a string."""
        sandbox = str(tmp_path)
        self._seed_addon_style(sandbox)
        r = _run_ml(sandbox, ["set", "--concern", "unreal", "unreal.samples_root", "/x/Lyra"])
        assert r.returncode == 0, f"stderr: {r.stderr}"
        with open(os.path.join(sandbox, "unreal.local.toml"), encoding="utf-8") as f:
            data = tomllib.loads(f.read())
        v = data["unreal"]["emit_shape_version"]
        assert v == 1 and isinstance(v, int) and not isinstance(v, bool), (
            f"emit_shape_version coerced to {v!r} ({type(v).__name__}) — type-clobber regression"
        )

    def test_provenance_table_survives_intact(self, tmp_path):
        """The addon's [provenance.emit_shape_version] (source='constant') round-trips intact."""
        sandbox = str(tmp_path)
        self._seed_addon_style(sandbox)
        _run_ml(sandbox, ["set", "--concern", "unreal", "unreal.samples_root", "/x/Lyra"])
        with open(os.path.join(sandbox, "unreal.local.toml"), encoding="utf-8") as f:
            data = tomllib.loads(f.read())
        prov = data["provenance"]["emit_shape_version"]
        assert prov["written_by"] == "_seed_unreal_keys.py"
        assert prov["source"] == "constant"

    def test_nested_addon_subtable_survives(self, tmp_path):
        """A pre-existing addon sub-table ([unreal.engines]) survives an unrelated scalar write."""
        sandbox = str(tmp_path)
        self._seed_addon_style(sandbox)
        _run_ml(sandbox, ["set", "--concern", "unreal", "unreal.samples_root", "/x/Lyra"])
        assert _run_ml(sandbox, ["get", "unreal.engines.5_3"]).stdout.strip() == "E:/dev/UE/5.3"

    def test_bool_value_preserved(self, tmp_path):
        """A pre-existing boolean is re-emitted as a TOML bool (bool tested before int)."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox, concerns=["unreal"])
        _write_file(
            os.path.join(sandbox, "unreal.local.toml"),
            "schema = 1\n\n[unreal]\nheadless = true\n",
        )
        _run_ml(sandbox, ["set", "--concern", "unreal", "unreal.x", "y"])
        with open(os.path.join(sandbox, "unreal.local.toml"), encoding="utf-8") as f:
            data = tomllib.loads(f.read())
        assert data["unreal"]["headless"] is True

    def test_from_absent_writes_managed_header_and_schema(self, tmp_path):
        sandbox = str(tmp_path)
        _seed_registry(sandbox, concerns=["unreal"])
        _run_ml(sandbox, ["set", "--concern", "unreal", "unreal.samples_root", "/x/Lyra"])
        raw = open(os.path.join(sandbox, "unreal.local.toml"), encoding="utf-8").read()
        assert "managed by `machine-local set --concern`" in raw
        assert "schema = 1" in raw

    def test_malformed_existing_fails_loud(self, tmp_path):
        sandbox = str(tmp_path)
        _seed_registry(sandbox, concerns=["unreal"])
        _write_file(os.path.join(sandbox, "unreal.local.toml"), "this is = = not valid toml [[[\n")
        r = _run_ml(sandbox, ["set", "--concern", "unreal", "unreal.x", "y"])
        assert r.returncode == 1
        assert "cannot parse existing" in r.stderr

    def test_mixed_case_key_rejected(self, tmp_path):
        """Mixed-case key fails loud with an actionable message (not a confusing round-trip None)."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox, concerns=["unreal"])
        r = _run_ml(sandbox, ["set", "--concern", "unreal", "unreal.Samples_Root", "/x/Lyra"])
        assert r.returncode == 1
        assert "lowercase" in r.stderr

    def test_mixed_case_concern_prefix_rejected(self, tmp_path):
        """A mixed-case --concern arg fails loud too (code-reviewer F2 — uniform with key reject,
        not silently lowercased)."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox, concerns=["unreal"])
        r = _run_ml(sandbox, ["set", "--concern", "Unreal", "unreal.samples_root", "/x/Lyra"])
        assert r.returncode == 1
        assert "lowercase" in r.stderr
        # No file written under either casing.
        assert not os.path.exists(os.path.join(sandbox, "unreal.local.toml"))
        assert not os.path.exists(os.path.join(sandbox, "Unreal.local.toml"))


# ---------------------------------------------------------------------------
# Read-path exit-code contract — operational failure must be distinguishable
# from a cleanly-absent key (cross-repo memo 2026-06-24, daemon read-path bug).
# Contract: 0 = found/present, 1 = clean absence, 2 = operational failure.
# ---------------------------------------------------------------------------

def _find_old_python() -> str | None:
    """Locate a Python interpreter older than 3.11 for the version-guard test,
    or None if the machine has none (test skips rather than fails)."""
    for name in ("python3.10", "python3.9", "python3.8",
                 "/usr/bin/python3"):  # absolute path catches stripped-PATH daemons where versioned names are absent but the stock macOS system Python is still reachable
        path = shutil.which(name)  # handles absolute paths and PATH lookups uniformly
        if not path:
            continue
        try:
            out = subprocess.run(
                [path, "-c", "import sys; print(sys.version_info[0], sys.version_info[1])"],
                capture_output=True, text=True,
            )
        except OSError:
            continue
        if out.returncode == 0:
            parts = out.stdout.split()
            if len(parts) == 2 and (int(parts[0]), int(parts[1])) < (3, 11):
                return path
    return None


class TestReadPathExitCodeContract:
    """get/has distinguish clean absence (1) from operational failure (2)."""

    def test_get_found_exits_0(self, tmp_path):
        sandbox = str(tmp_path)
        _seed_registry(sandbox)
        _run_ml(sandbox, ["set", "repos.foo", "/x/foo"])
        assert _run_ml(sandbox, ["get", "repos.foo"]).returncode == 0

    def test_get_not_found_exits_1(self, tmp_path):
        """A cleanly-absent key exits 1 (NOT_FOUND) — the normal fall-back signal."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox)
        r = _run_ml(sandbox, ["get", "repos.does_not_exist"])
        assert r.returncode == 1, f"expected clean-absence rc=1, got {r.returncode}"
        assert "not found" in r.stderr.lower()

    def test_has_found_exits_0(self, tmp_path):
        sandbox = str(tmp_path)
        _seed_registry(sandbox)
        _run_ml(sandbox, ["set", "repos.foo", "/x/foo"])
        assert _run_ml(sandbox, ["has", "repos.foo"]).returncode == 0

    def test_has_not_set_exits_1(self, tmp_path):
        sandbox = str(tmp_path)
        _seed_registry(sandbox)
        assert _run_ml(sandbox, ["has", "repos.does_not_exist"]).returncode == 1

    def test_has_malformed_toml_exits_2_operational(self, tmp_path):
        """`has` participates in the contract too: a broken reader exits 2, not 1 —
        so `machine-local has X || die` can tell absence from a parse failure."""
        sandbox = str(tmp_path)
        _write_file(os.path.join(sandbox, "registry.toml"), "this is = = bad toml [[[\n")
        r = _run_ml(sandbox, ["has", "anything"])
        assert r.returncode == 2, f"expected operational rc=2, got {r.returncode}: {r.stderr}"

    def test_malformed_toml_exits_2_operational(self, tmp_path):
        """Malformed registry TOML is an operational failure (2), NOT clean absence (1) —
        a consumer doing `get X || fallback` must be able to tell the reader broke."""
        sandbox = str(tmp_path)
        _write_file(os.path.join(sandbox, "registry.toml"), "this is = = bad toml [[[\n")
        r = _run_ml(sandbox, ["get", "anything"])
        assert r.returncode == 2, f"expected operational rc=2, got {r.returncode}: {r.stderr}"
        assert "malformed toml" in r.stderr.lower()

    def test_version_guard_exits_2_operational(self, tmp_path):
        """Running under Python < 3.11 trips the version guard with rc=2 (operational),
        NOT rc=1 — the exact daemon misclassification the contract prevents. Skips when
        the machine has no <3.11 interpreter to exercise the guard."""
        old_py = _find_old_python()
        if not old_py:
            pytest.skip("no Python < 3.11 interpreter available to exercise the version guard")
        sandbox = str(tmp_path)
        _seed_registry(sandbox)
        env = {**os.environ, "MACHINE_LOCAL_REGISTRY_DIR": sandbox}
        r = subprocess.run([old_py, _ML_PY, "get", "repos.x"],
                           capture_output=True, text=True, env=env)
        assert r.returncode == 2, f"expected operational rc=2 from version guard, got {r.returncode}"
        assert "3.11" in r.stderr


# ---------------------------------------------------------------------------
# Wrapper interpreter-selection — bin/machine-local must skip a guard-failing
# first `python3` and pick a >=3.11 interpreter further down PATH (memo ask #1).
# POSIX-only (the wrapper is a bash script); Windows uses machine-local.cmd.
# ---------------------------------------------------------------------------

# Portable no-console flag: CREATE_NO_WINDOW on Windows, 0 (no-op) elsewhere.
_NO_WIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@pytest.mark.skipif(sys.platform == "win32", reason="bash wrapper is POSIX-only")
class TestWrapperInterpreterSelection:
    """bin/machine-local self-heals when the first python3 on PATH is < 3.11."""

    def test_wrapper_skips_old_python3_and_picks_versioned_311(self, tmp_path):
        """PATH where `python3` resolves to <3.11 but a `python3.<minor>` >=3.11 is
        also reachable: the wrapper must pick the good one and read the key (rc=0).
        Skips unless both a <3.11 interpreter and a pinned-range (3.11-3.14) runner exist."""
        old_py = _find_old_python()
        if not old_py:
            pytest.skip("no Python < 3.11 to stand in as the bad first python3")
        minor = sys.version_info.minor
        if not (sys.version_info.major == 3 and 11 <= minor <= 14):
            pytest.skip(f"test runner 3.{minor} is outside the wrapper's pinned probe range 3.11-3.14")

        sandbox = str(tmp_path)
        _seed_registry(sandbox)
        _run_ml(sandbox, ["set", "repos.foo", "/x/foo"])

        # fakebin: a `python3` that is the OLD interpreter (must be shadowed).
        fakebin = os.path.join(sandbox, "fakebin")
        os.makedirs(fakebin)
        shim = os.path.join(fakebin, "python3")
        with open(shim, "w", encoding="utf-8") as f:
            f.write(f'#!/bin/sh\nexec "{old_py}" "$@"\n')
        os.chmod(shim, 0o755)

        # goodbin: a version-named symlink to the (>=3.11) test runner.
        goodbin = os.path.join(sandbox, "goodbin")
        os.makedirs(goodbin)
        os.symlink(sys.executable, os.path.join(goodbin, f"python3.{minor}"))

        # fakebin first → `command -v python3` hits the old shim; the wrapper must
        # still find python3.<minor> in goodbin via its pinned probe. /usr/bin:/bin
        # last so the shebang's `env`/`bash` resolve.
        env = {
            "MACHINE_LOCAL_REGISTRY_DIR": sandbox,
            "PATH": f"{fakebin}:{goodbin}:/usr/bin:/bin",
            "HOME": os.environ.get("HOME", sandbox),
        }
        r = subprocess.run([_ML_WRAPPER, "get", "repos.foo"],
                           capture_output=True, text=True, env=env,
                           creationflags=_NO_WIN)
        assert r.returncode == 0, f"wrapper failed to self-heal: rc={r.returncode} stderr={r.stderr}"
        assert r.stdout.strip() == "/x/foo"

    def test_wrapper_env_pin_bypasses_probe(self, tmp_path):
        """MACHINE_LOCAL_PYTHON is honoured verbatim, bypassing the probe loop."""
        sandbox = str(tmp_path)
        _seed_registry(sandbox)
        _run_ml(sandbox, ["set", "repos.foo", "/x/foo"])
        env = {
            "MACHINE_LOCAL_REGISTRY_DIR": sandbox,
            "MACHINE_LOCAL_PYTHON": sys.executable,  # the >=3.11 test runner
            "PATH": "/usr/bin:/bin",                 # no good python on PATH at all
            "HOME": os.environ.get("HOME", sandbox),
        }
        r = subprocess.run([_ML_WRAPPER, "get", "repos.foo"],
                           capture_output=True, text=True, env=env,
                           creationflags=_NO_WIN)
        assert r.returncode == 0, f"env-pin not honoured: rc={r.returncode} stderr={r.stderr}"
        assert r.stdout.strip() == "/x/foo"

    def test_wrapper_only_old_python3_on_path_exits_2(self, tmp_path):
        """End-to-end: PATH contains ONLY an old python3 (no versioned 3.11+).
        The wrapper probe falls through to the old interpreter, the impl's version
        guard fires, and the daemon-symptom wire path returns rc=2 (operational),
        NOT rc=1 (clean absence). Skips if no <3.11 interpreter is available.

        # Review: code-reviewer (F2) — proves the wrapper→old-python→version-guard→rc=2
        # end-to-end wire path: the exact symptom the 2026-06-24 daemon bug exposed.
        """
        old_py = _find_old_python()
        if not old_py:
            pytest.skip("no Python < 3.11 interpreter available to stand in as the bad python3")

        sandbox = str(tmp_path)
        _seed_registry(sandbox)

        # fakebin: a `python3` that IS the old interpreter and is the only python on PATH.
        # No versioned python3.11..python3.14 in the bin dir — probe must fail to find
        # a good interpreter and fall through to executing the old one, which trips the
        # version guard with rc=2.
        fakebin = os.path.join(sandbox, "fakebin_only_old")
        os.makedirs(fakebin)
        shim = os.path.join(fakebin, "python3")
        with open(shim, "w", encoding="utf-8") as f:
            f.write(f'#!/bin/sh\nexec "{old_py}" "$@"\n')
        os.chmod(shim, 0o755)

        env = {
            "MACHINE_LOCAL_REGISTRY_DIR": sandbox,
            "PATH": f"{fakebin}:/usr/bin:/bin",  # only old python3, no versioned names
            "HOME": os.environ.get("HOME", sandbox),
        }
        r = subprocess.run([_ML_WRAPPER, "get", "repos.x"],
                           capture_output=True, text=True, env=env,
                           creationflags=_NO_WIN)
        assert r.returncode == 2, (
            f"expected operational rc=2 from version guard, got rc={r.returncode} "
            f"stderr={r.stderr!r}"
        )

    def test_wrapper_env_pin_old_python_exits_2(self, tmp_path):
        """MACHINE_LOCAL_PYTHON pinned to a <3.11 interpreter still fails loud (rc=2).
        A deliberate bad pin must surface the version-guard error, not be silently
        swallowed or mistaken for a clean absence (rc=1). Skips if no <3.11 interpreter
        is available.

        # Review: code-reviewer (F3) — confirms that the env-pin bypass path does not
        # hide the version-guard; a bad pin fails loud through the impl's own guard.
        """
        old_py = _find_old_python()
        if not old_py:
            pytest.skip("no Python < 3.11 interpreter available to exercise the version guard")

        sandbox = str(tmp_path)
        _seed_registry(sandbox)

        env = {
            "MACHINE_LOCAL_REGISTRY_DIR": sandbox,
            "MACHINE_LOCAL_PYTHON": old_py,  # deliberate bad pin
            "PATH": "/usr/bin:/bin",
            "HOME": os.environ.get("HOME", sandbox),
        }
        r = subprocess.run([_ML_WRAPPER, "get", "repos.x"],
                           capture_output=True, text=True, env=env,
                           creationflags=_NO_WIN)
        assert r.returncode == 2, (
            f"expected operational rc=2 from version guard via bad env-pin, "
            f"got rc={r.returncode} stderr={r.stderr!r}"
        )


# ---------------------------------------------------------------------------
# Copy parity — the live ~/.claude/bin/ reader and the OSS templates/bin/ copy
# MUST stay byte-identical (an edit to one side that misses the other is the
# drift class this guards). Skips in the OSS distribution, which has no live bin/.
# ---------------------------------------------------------------------------

class TestBinTemplateParity:
    """Enforces byte-identity between the live meta-repo bin/ copies and the OSS templates/bin/ copies; an edit that lands on one side only (missing the twin) is the drift class this guards."""

    @pytest.mark.parametrize("fname", ["_machine_local.py", "machine-local"])
    def test_live_and_template_copies_identical(self, fname):
        live = os.path.join(_LIVE_BIN_DIR, fname)
        if not os.path.exists(live):
            pytest.skip("no live bin/ copy (OSS distribution) — parity check is meta-repo-only")
        template = os.path.join(_BIN_DIR, fname)
        with open(live, "rb") as f:
            live_bytes = f.read()
        with open(template, "rb") as f:
            template_bytes = f.read()
        assert live_bytes == template_bytes, (
            f"{fname}: live bin/ and templates/bin/ copies have drifted — "
            "an edit landed on one side only. Re-sync them."
        )
