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
