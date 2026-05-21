"""test_claude_machine_local — pytest coverage for the shell-out ergonomic wrapper.

Spec backlink: docs/plans/2026-05-20-portable-code-substrate.md §5.1 (Chunk 1 tests)

Coverage (per plan AC7):
  1. repos.coordinator_claude (known-set on Striker) returns pathlib.Path matching
     subprocess.run(["machine-local","get","repos.coordinator_claude"]).stdout.strip().
  2. repos.this_key_does_not_exist_12345 raises AttributeError whose message contains
     the dotted key AND a remediation phrase ("Fix:" or "registry.local.toml").
  3. repos._foo raises AttributeError without consulting the registry
     (mock subprocess.run; assert it was NOT called).
  4. Re-import idempotency: from claude_machine_local import repos twice yields a repos
     that resolves correctly (Python caches modules; smoke test).
  5. Memoization: call repos.coordinator_claude twice; verify subprocess.run called
     only once (via mock cache-dict inspection).
  6. Empty-value case: monkeypatch reader via MACHINE_LOCAL_REGISTRY_DIR to a tmp
     directory containing a registry.toml that declares "repos.empty_test" = "";
     assert repos.empty_test raises AttributeError with "declared but has no value".

All tests that require a live registry key skip gracefully (pytest.skip) when the key
is absent — operator config is not guaranteed in CI or on fresh setups.
"""
import importlib
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# sys.path bootstrap — ensure ~/.claude/bin is importable without installation
# ---------------------------------------------------------------------------
_BIN_DIR = os.path.join(os.path.expanduser("~"), ".claude", "bin")
if _BIN_DIR not in sys.path:
    sys.path.insert(0, _BIN_DIR)


def _fresh_module():
    """Return a freshly-imported claude_machine_local module (bypasses cache).

    Used for tests that need a pristine _Namespace instance without cached
    attribute state from a prior test in the same process.
    """
    mod_name = "claude_machine_local"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


def _cli_get(key: str) -> str | None:
    """Return CLI output for key, or None if unset.

    Uses the public machine-local shell wrapper as the oracle so the test
    validates the Python wrapper against the documented CLI contract.
    On Windows, machine-local is a bash script; invoke via the .cmd wrapper.
    """
    if sys.platform == "win32":
        ml_path = os.path.join(_BIN_DIR, "machine-local.cmd")
    else:
        ml_path = os.path.join(_BIN_DIR, "machine-local")
    result = subprocess.run(
        [ml_path, "get", key],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return None


# ---------------------------------------------------------------------------
# Test 1 — known key returns Path matching CLI output
# ---------------------------------------------------------------------------

def test_repos_coordinator_claude_matches_cli():
    """repos.coordinator_claude returns a Path whose str() matches CLI output."""
    cli_val = _cli_get("repos.coordinator_claude")
    if cli_val is None:
        pytest.skip("repos.coordinator_claude not set on this machine")

    mod = _fresh_module()
    result = mod.repos.coordinator_claude
    assert isinstance(result, Path), f"Expected Path, got {type(result)}"
    assert str(result) == str(Path(cli_val).expanduser()), (
        f"Wrapper returned {result!r}, CLI returned {cli_val!r}"
    )


# ---------------------------------------------------------------------------
# Test 2 — missing key raises AttributeError with dotted key + remediation
# ---------------------------------------------------------------------------

def test_missing_key_raises_attribute_error_with_message():
    """repos.this_key_does_not_exist_12345 raises AttributeError with key + remediation."""
    mod = _fresh_module()
    with pytest.raises(AttributeError) as exc_info:
        _ = mod.repos.this_key_does_not_exist_12345
    msg = str(exc_info.value)
    assert "repos.this_key_does_not_exist_12345" in msg, (
        f"Dotted key not in error message: {msg!r}"
    )
    # Remediation phrase — plan AC7 says "Fix:" or "registry.local.toml"
    assert ("Fix:" in msg or "registry.local.toml" in msg), (
        f"No remediation phrase in error message: {msg!r}"
    )


# ---------------------------------------------------------------------------
# Test 3 — underscore-attribute guard raises without consulting the registry
# ---------------------------------------------------------------------------

def test_underscore_attr_raises_without_subprocess():
    """repos._foo raises AttributeError without invoking subprocess.run."""
    mod = _fresh_module()
    with patch("subprocess.run") as mock_run:
        with pytest.raises(AttributeError) as exc_info:
            _ = mod.repos._foo
        # subprocess.run must NOT have been called — guard fires before lookup.
        # This is the load-bearing assertion; the name-preservation check below
        # is cosmetic (Python's AttributeError(name) preserves it by definition).
        mock_run.assert_not_called()
    # Attribute name is preserved in the AttributeError (Python protocol).
    assert "_foo" in str(exc_info.value), (
        f"Expected '_foo' in AttributeError message, got: {exc_info.value!r}"
    )


# ---------------------------------------------------------------------------
# Test 4 — re-import idempotency (smoke test — Python module cache)
# ---------------------------------------------------------------------------

def test_reimport_idempotency():
    """Importing claude_machine_local twice yields the same module object."""
    mod_name = "claude_machine_local"
    # Ensure module is in cache from a prior import.
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    mod_a = importlib.import_module(mod_name)
    mod_b = importlib.import_module(mod_name)
    assert mod_a is mod_b, "Second import returned a different module object"

    cli_val = _cli_get("repos.coordinator_claude")
    if cli_val is None:
        pytest.skip("repos.coordinator_claude not set — skipping resolution smoke")

    # Both access through the same cached module resolve correctly.
    result_a = mod_a.repos.coordinator_claude
    result_b = mod_b.repos.coordinator_claude
    assert result_a == result_b, (
        f"Same module, different results: {result_a!r} vs {result_b!r}"
    )


# ---------------------------------------------------------------------------
# Test 5 — memoization: subprocess.run called only once for repeated access
# ---------------------------------------------------------------------------

def test_memoization_subprocess_called_once():
    """Accessing repos.coordinator_claude twice calls subprocess.run exactly once."""
    cli_val = _cli_get("repos.coordinator_claude")
    if cli_val is None:
        pytest.skip("repos.coordinator_claude not set on this machine")

    mod = _fresh_module()

    # Patch subprocess.run on the claude_machine_local module's own reference
    # so we capture calls from within the module's __getattr__.
    with patch.object(mod, "subprocess") as mock_subprocess_mod:
        fake_result = MagicMock()
        fake_result.returncode = 0
        fake_result.stdout = cli_val
        fake_result.stderr = ""
        mock_subprocess_mod.run.return_value = fake_result

        _ = mod.repos.coordinator_claude  # first access — subprocess called
        _ = mod.repos.coordinator_claude  # second access — cache hit, no call

        assert mock_subprocess_mod.run.call_count == 1, (
            f"Expected subprocess.run called once, got {mock_subprocess_mod.run.call_count}"
        )


# ---------------------------------------------------------------------------
# Test 6 — empty-value case raises AttributeError with "declared but has no value"
# ---------------------------------------------------------------------------

def test_empty_value_raises_attribute_error(tmp_path, monkeypatch):
    """repos.empty_test raises AttributeError when key is declared with empty string."""
    # Write a minimal registry.toml declaring repos.empty_test = "".
    registry_toml = tmp_path / "registry.toml"
    registry_toml.write_text(
        textwrap.dedent("""\
            schema = 1

            "repos.empty_test" = ""
        """),
        encoding="utf-8",
    )

    # Point the machine-local reader at our tmp registry.
    monkeypatch.setenv("MACHINE_LOCAL_REGISTRY_DIR", str(tmp_path))

    mod = _fresh_module()
    with pytest.raises(AttributeError) as exc_info:
        _ = mod.repos.empty_test
    msg = str(exc_info.value)
    assert "declared but has no value" in msg, (
        f"Expected 'declared but has no value' in message, got: {msg!r}"
    )
    assert "repos.empty_test" in msg, (
        f"Expected 'repos.empty_test' in message, got: {msg!r}"
    )
