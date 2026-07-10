"""test_claude_home.py — coverage for coordinator/lib/claude-home/_claude_home.py.

Run directly:  python plugins/coordinator/lib/claude-home/tests/test_claude_home.py
Run via unittest discovery:  python -m unittest discover plugins/coordinator/lib/claude-home/tests

Stdlib-only — no pytest dependency. The module under test is also stdlib-only,
so this test suite runs anywhere Python 3.9+ runs.

Covers:
  - Path resolution: CLAUDE_HOME / HOME / USERPROFILE / Path.home() precedence
  - Sub-location helpers (machine-local, plugins, .claude.json, .claude/)
  - read_config: missing file, valid JSON, malformed JSON enrichment, BOM tolerance
  - write_config: round-trip, parent-dir creation, no tmp files left, overwrite
  - CLI: each subcommand prints the expected path; unknown subcommand exits 2

Spec backlink: coordinator/docs/wiki/machine-local-registry.md §4a
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

# Module under test sits alongside this tests/ dir at
# coordinator/lib/claude-home/_claude_home.py.
_MODULE_DIR = Path(__file__).resolve().parent.parent
if str(_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(_MODULE_DIR))

# pylint: disable=wrong-import-position
import _claude_home  # noqa: E402
from _claude_home import (  # noqa: E402
    claude_config_path,
    claude_home_dir,
    coordinator_root,
    home_dir,
    machine_local_dir,
    plugins_dir,
    read_config,
    write_config,
)


@contextmanager
def _isolated_env(**overrides):
    """Drop CLAUDE_HOME/HOME/USERPROFILE, then apply *overrides*; restore on exit."""
    # Review: code-reviewer (F3) — add COORDINATOR_SETTINGS_HOME so _isolated_env-based
    # test classes are fully environment-isolated; host/CI shells with this var set would
    # otherwise cause settings_home() to return the wrong path.
    saved = {k: os.environ.get(k) for k in ("CLAUDE_HOME", "HOME", "USERPROFILE", "COORDINATOR_SETTINGS_HOME")}
    for k in saved:
        os.environ.pop(k, None)
    for k, v in overrides.items():
        if v is not None:
            os.environ[k] = v
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


class TestHomeResolution(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_claude_home_wins(self):
        with _isolated_env(
            CLAUDE_HOME=str(self.tmp_path / "custom"),
            HOME=str(self.tmp_path / "real_home"),
            USERPROFILE=str(self.tmp_path / "win_home"),
        ):
            self.assertEqual(home_dir(), self.tmp_path / "custom")
            self.assertEqual(claude_home_dir(), self.tmp_path / "custom" / ".claude")
            self.assertEqual(claude_config_path(), self.tmp_path / "custom" / ".claude.json")
            # Neither new (<settings-home>/machine-local) nor legacy (.claude/machine-local)
            # exists in this sandbox, so machine_local_dir() returns the canonical new path.
            self.assertEqual(
                machine_local_dir(),
                self.tmp_path / "custom" / ".coordinator-claude-settings" / "machine-local",
            )
            self.assertEqual(plugins_dir(), self.tmp_path / "custom" / ".claude" / "plugins")

    def test_home_fallback(self):
        with _isolated_env(
            HOME=str(self.tmp_path / "real_home"),
            USERPROFILE=str(self.tmp_path / "win_home"),
        ):
            self.assertEqual(home_dir(), self.tmp_path / "real_home")
            self.assertEqual(claude_config_path(), self.tmp_path / "real_home" / ".claude.json")

    def test_userprofile_fallback(self):
        with _isolated_env(USERPROFILE=str(self.tmp_path / "win_home")):
            self.assertEqual(home_dir(), self.tmp_path / "win_home")
            self.assertEqual(claude_config_path(), self.tmp_path / "win_home" / ".claude.json")

    def test_stdlib_fallback(self):
        fake = self.tmp_path / "stdlib_home"
        with _isolated_env(), patch.object(Path, "home", classmethod(lambda cls: fake)):
            self.assertEqual(home_dir(), fake)
            self.assertEqual(claude_config_path(), fake / ".claude.json")

    def test_filesystem_layout_invariant(self):
        """`.claude.json` and `.claude/` are SIBLINGS under the home dir, never nested."""
        with _isolated_env(CLAUDE_HOME=str(self.tmp_path)):
            cfg = claude_config_path()
            cdir = claude_home_dir()
            self.assertEqual(cfg.parent, cdir.parent, ".claude.json must be sibling of .claude/, not inside it")
            self.assertNotEqual(cfg, cdir / ".claude.json")

    def test_relative_claude_home_fails_loud(self):
        # CLAUDE_HOME is a deliberate operator override — a relative value is
        # a configuration error, not a soft fallback. Spec: 2026-05-28
        # addon-pluggy audit, INFO finding on env-var absolute-path validation.
        with _isolated_env(CLAUDE_HOME="relative/sandbox"):
            with self.assertRaises(ValueError) as cm:
                home_dir()
            self.assertIn("CLAUDE_HOME", str(cm.exception))
            self.assertIn("absolute", str(cm.exception))

    def test_empty_claude_home_fails_loud(self):
        # Review: code-reviewer — an empty string set in the environment is unambiguously
        # malformed; the docstring contract on CLAUDE_HOME is fail-loud, not silent
        # fallthrough. Common when CI clears a variable with `CLAUDE_HOME=`
        # instead of `unset CLAUDE_HOME`.
        with _isolated_env(CLAUDE_HOME=""):
            with self.assertRaises(ValueError) as cm:
                home_dir()
            self.assertIn("empty", str(cm.exception))

    def test_relative_home_is_skipped(self):
        # Relative HOME (OS-provided) is ignored; resolution falls through to
        # USERPROFILE or stdlib. Prevents env-derived relative path from
        # anchoring later path-joins at the process cwd.
        fake = self.tmp_path / "win_home"
        with _isolated_env(HOME="../escape", USERPROFILE=str(fake)):
            self.assertEqual(home_dir(), fake)

    def test_relative_userprofile_is_skipped(self):
        fake = self.tmp_path / "stdlib_home"
        with _isolated_env(USERPROFILE="../escape"), patch.object(
            Path, "home", classmethod(lambda cls: fake)
        ):
            self.assertEqual(home_dir(), fake)


# ---------------------------------------------------------------------------
# coordinator_root
# ---------------------------------------------------------------------------


class TestCoordinatorRoot(unittest.TestCase):
    """Coverage for coordinator_root() — Python-accessible tiers only.

    The full precedence chain (registry live_path, versioned cache glob) lives in
    resolve-coordinator-clone.sh; this class covers the Python-addressable subset.

    Spec backlink: docs/plans/2026-06-23-coordinator-install-surface-dogfood-hardening.md § C2a
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_claude_plugin_root_wins(self):
        """CLAUDE_PLUGIN_ROOT (harness injection) beats every other tier."""
        override = str(self.tmp_path / "plugin_root")
        with _isolated_env(CLAUDE_HOME=str(self.tmp_path)):
            with patch.dict(os.environ, {"CLAUDE_PLUGIN_ROOT": override}, clear=False):
                result = coordinator_root()
                self.assertEqual(result, Path(override))

    def test_coordinator_root_env_wins_over_flat(self):
        """COORDINATOR_ROOT env var beats the flat-layout tier."""
        override = str(self.tmp_path / "content_root")
        with _isolated_env(CLAUDE_HOME=str(self.tmp_path)):
            # Remove CLAUDE_PLUGIN_ROOT so COORDINATOR_ROOT tier fires.
            env_overrides = {"COORDINATOR_ROOT": override}
            # Ensure CLAUDE_PLUGIN_ROOT is absent.
            with patch.dict(os.environ, env_overrides, clear=False):
                os.environ.pop("CLAUDE_PLUGIN_ROOT", None)
                result = coordinator_root()
                self.assertEqual(result, Path(override))

    def test_flat_layout_fallback(self):
        """Falls back to plugins_dir()/coordinator-claude/coordinator when no env set."""
        with _isolated_env(CLAUDE_HOME=str(self.tmp_path)):
            os.environ.pop("CLAUDE_PLUGIN_ROOT", None)
            os.environ.pop("COORDINATOR_ROOT", None)
            result = coordinator_root()
            expected = self.tmp_path / ".claude" / "plugins" / "coordinator-claude" / "coordinator"
            self.assertEqual(result, expected)

    def test_claude_plugin_root_beats_coordinator_root(self):
        """CLAUDE_PLUGIN_ROOT (tier 1) beats COORDINATOR_ROOT (tier 2)."""
        cpr = str(self.tmp_path / "cpr")
        cr = str(self.tmp_path / "cr")
        with _isolated_env(CLAUDE_HOME=str(self.tmp_path)):
            with patch.dict(os.environ, {"CLAUDE_PLUGIN_ROOT": cpr, "COORDINATOR_ROOT": cr}, clear=False):
                result = coordinator_root()
                self.assertEqual(result, Path(cpr))

    def test_cli_coordinator_root_subcommand(self):
        """'claude-home coordinator-root' prints the resolved coordinator root."""
        buf_out, buf_err = __import__("io").StringIO(), __import__("io").StringIO()
        cpr = str(self.tmp_path / "cpr_cli")
        with _isolated_env(CLAUDE_HOME=str(self.tmp_path)):
            with patch.dict(os.environ, {"CLAUDE_PLUGIN_ROOT": cpr}, clear=False):
                from contextlib import redirect_stdout, redirect_stderr
                with redirect_stdout(buf_out), redirect_stderr(buf_err):
                    rc = _claude_home._main(["claude-home", "coordinator-root"])
                self.assertEqual(rc, 0, f"exited {rc}; stderr={buf_err.getvalue()!r}")
                self.assertEqual(buf_out.getvalue().rstrip("\n"), cpr)


# ---------------------------------------------------------------------------
# read_config
# ---------------------------------------------------------------------------


class TestReadConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_file_returns_empty_dict(self):
        with _isolated_env(CLAUDE_HOME=str(self.tmp_path)):
            self.assertEqual(read_config(), {})

    def test_reads_existing_file(self):
        payload = {"mcpServers": {"project-rag": {"type": "stdio"}}}
        with _isolated_env(CLAUDE_HOME=str(self.tmp_path)):
            (self.tmp_path / ".claude.json").write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(read_config(), payload)

    def test_malformed_json_raises_with_path(self):
        with _isolated_env(CLAUDE_HOME=str(self.tmp_path)):
            (self.tmp_path / ".claude.json").write_text("{not valid", encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError) as cm:
                read_config()
            self.assertIn(".claude.json", str(cm.exception))

    def test_bom_utf8_tolerated(self):
        """UTF-8 BOM (U+FEFF) from Windows editors does not break parsing."""
        payload = {"projects": {}}
        with _isolated_env(CLAUDE_HOME=str(self.tmp_path)):
            (self.tmp_path / ".claude.json").write_text(
                "﻿" + json.dumps(payload), encoding="utf-8"
            )
            self.assertEqual(read_config(), payload)


# ---------------------------------------------------------------------------
# write_config
# ---------------------------------------------------------------------------


class TestWriteConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_roundtrip(self):
        payload = {"mcpServers": {"x": {"type": "stdio", "command": "/usr/bin/python3"}}}
        with _isolated_env(CLAUDE_HOME=str(self.tmp_path)):
            write_config(payload)
            self.assertEqual(read_config(), payload)

    def test_creates_parent_directory(self):
        nested = self.tmp_path / "deep" / "nested"
        with _isolated_env(CLAUDE_HOME=str(nested)):
            write_config({"k": "v"})
            self.assertTrue((nested / ".claude.json").exists())

    def test_no_tmp_files_left_behind(self):
        with _isolated_env(CLAUDE_HOME=str(self.tmp_path)):
            write_config({"sentinel": True})
            leftovers = list(self.tmp_path.glob(".claude.json.*.tmp"))
            self.assertEqual(leftovers, [], f"orphan tmp files: {leftovers}")

    def test_overwrite_replaces_not_appends(self):
        with _isolated_env(CLAUDE_HOME=str(self.tmp_path)):
            write_config({"version": 1})
            write_config({"version": 2})
            self.assertEqual(read_config(), {"version": 2})

    def test_failure_path_cleans_up_tmp(self):
        """If os.replace raises, the tempfile must be unlinked (no orphan .tmp files)."""
        with _isolated_env(CLAUDE_HOME=str(self.tmp_path)):
            with patch("_claude_home.os.replace", side_effect=OSError("simulated failure")):
                with self.assertRaises(OSError):
                    write_config({"any": "data"})
            leftovers = list(self.tmp_path.glob(".claude.json.*.tmp"))
            self.assertEqual(leftovers, [], f"orphan tmp files after failure: {leftovers}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _run_cli(self, *args):
        buf_out, buf_err = io.StringIO(), io.StringIO()
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            rc = _claude_home._main(["claude-home", *args])
        return rc, buf_out.getvalue().rstrip("\n"), buf_err.getvalue()

    def test_each_subcommand(self):
        # machine-local: neither new (<settings-home>/machine-local) nor legacy
        # (.claude/machine-local) exist in this sandbox, so the canonical new path is returned.
        # Review: code-reviewer (F5) — added settings-home case (previously untested subcommand).
        cases = [
            ("home", str(self.tmp_path)),
            ("path", str(self.tmp_path / ".claude.json")),
            ("dir", str(self.tmp_path / ".claude")),
            ("machine-local", str(self.tmp_path / ".coordinator-claude-settings" / "machine-local")),
            ("plugins", str(self.tmp_path / ".claude" / "plugins")),
            ("settings-home", str(self.tmp_path / ".coordinator-claude-settings")),
        ]
        with _isolated_env(CLAUDE_HOME=str(self.tmp_path)):
            for sub, expected in cases:
                with self.subTest(subcommand=sub):
                    # Review: code-reviewer (F2) — reset both once-guards (split from single flag)
                    _claude_home._legacy_machine_local_divergence_warned = False  # reset one-time guard
                    _claude_home._legacy_machine_local_deprecated_warned = False  # reset one-time guard
                    rc, out, err = self._run_cli(sub)
                    self.assertEqual(rc, 0, f"{sub} exited {rc}; stderr={err!r}")
                    self.assertEqual(out, expected)

    def test_unknown_subcommand_exits_2(self):
        with _isolated_env(CLAUDE_HOME=str(self.tmp_path)):
            rc, _out, err = self._run_cli("bogus")
            self.assertEqual(rc, 2)
            self.assertIn("unknown subcommand", err)
            self.assertIn("Usage:", err)

    def test_no_arg_exits_2_with_usage(self):
        with _isolated_env(CLAUDE_HOME=str(self.tmp_path)):
            rc, _out, err = self._run_cli()
            self.assertEqual(rc, 2)
            self.assertIn("Usage:", err)

    def test_machine_local_cli_legacy_only(self):
        """Legacy-only sandbox: rc=0, stdout=legacy path, stderr contains DEPRECATED.

        Review: code-reviewer (F4) — end-to-end CLI wire-path test for the case where
        only the legacy ~/.claude/machine-local home exists. _check_machine_local_divergence()
        returns silently (new absent) and machine_local_dir() falls back to legacy with a
        DEPRECATED warning.
        """
        legacy = self.tmp_path / ".claude" / "machine-local"
        legacy.mkdir(parents=True)
        with _isolated_env(CLAUDE_HOME=str(self.tmp_path)):
            _claude_home._legacy_machine_local_divergence_warned = False
            _claude_home._legacy_machine_local_deprecated_warned = False
            rc, out, err = self._run_cli("machine-local")
        self.assertEqual(rc, 0, f"expected rc=0; stderr={err!r}")
        self.assertEqual(out, str(legacy))
        self.assertIn("DEPRECATED", err)

    def test_machine_local_cli_divergent(self):
        """Divergent-both sandbox: rc=0, stdout=new path, stderr contains DIVERGENT.

        Review: code-reviewer (F4) — end-to-end CLI wire-path test for the case where
        both homes exist with distinct realpaths. _check_machine_local_divergence() emits
        a DIVERGENT warning; machine_local_dir() then returns the new (settings-home) path.
        """
        new = self.tmp_path / ".coordinator-claude-settings" / "machine-local"
        new.mkdir(parents=True)
        legacy = self.tmp_path / ".claude" / "machine-local"
        legacy.mkdir(parents=True)
        # Both dirs exist and are distinct non-symlink directories: resolve() differs.
        with _isolated_env(CLAUDE_HOME=str(self.tmp_path)):
            _claude_home._legacy_machine_local_divergence_warned = False
            _claude_home._legacy_machine_local_deprecated_warned = False
            rc, out, err = self._run_cli("machine-local")
        self.assertEqual(rc, 0, f"expected rc=0; stderr={err!r}")
        self.assertEqual(out, str(new))
        self.assertIn("DIVERGENT", err)


# ---------------------------------------------------------------------------
# _check_machine_local_divergence — warn-and-continue semantics
# ---------------------------------------------------------------------------


class TestMachineLocalDivergence(unittest.TestCase):
    """_check_machine_local_divergence() warns loud but does NOT abort the process.

    Path layout under test:
      CLAUDE_HOME         → self.tmp_path / "home"
      claude_home_dir()   → self.tmp_path / "home" / ".claude"   (adds .claude)
      legacy path         → self.tmp_path / "home" / ".claude" / "machine-local"
      COORDINATOR_SETTINGS_HOME → self.tmp_path / "settings"
      new path            → self.tmp_path / "settings" / "machine-local"

    Spec backlink: docs/plans/2026-07-06-durable-substrate-to-settings-home.md § C1
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        # Review: code-reviewer (F2) — reset both once-guards (split from single flag)
        _claude_home._legacy_machine_local_divergence_warned = False
        _claude_home._legacy_machine_local_deprecated_warned = False

    def tearDown(self):
        self.tmp.cleanup()
        _claude_home._legacy_machine_local_divergence_warned = False
        _claude_home._legacy_machine_local_deprecated_warned = False

    def _legacy_path(self):
        # claude_home_dir() = CLAUDE_HOME / ".claude", so legacy = CLAUDE_HOME/.claude/machine-local
        return self.tmp_path / "home" / ".claude" / "machine-local"

    def _new_path(self):
        return self.tmp_path / "settings" / "machine-local"

    def _env(self):
        return {
            "CLAUDE_HOME": str(self.tmp_path / "home"),
            "COORDINATOR_SETTINGS_HOME": str(self.tmp_path / "settings"),
        }

    def test_divergence_warns_not_exits(self):
        """Both homes exist with different realpaths → emit warning, return normally (no sys.exit)."""
        self._legacy_path().mkdir(parents=True)
        self._new_path().mkdir(parents=True)

        buf = io.StringIO()
        with patch.dict(os.environ, self._env(), clear=False):
            with redirect_stderr(buf):
                # Must NOT raise SystemExit
                _claude_home._check_machine_local_divergence()

        err = buf.getvalue()
        self.assertIn("DIVERGENT MACHINE-LOCAL HOMES", err)
        self.assertIn("CONTINUING", err)
        self.assertIn("coordinator/lib/migrate-substrate-to-settings-home.sh", err)
        self.assertIn("Legacy realpath", err)
        self.assertIn("New    realpath", err)

    def test_compat_symlink_no_warn(self):
        """Both paths resolve to the same realpath (compat-symlink) → no warning emitted."""
        self._new_path().mkdir(parents=True)
        # Create legacy path as a symlink pointing at the new path (same realpath)
        self._legacy_path().parent.mkdir(parents=True, exist_ok=True)
        self._legacy_path().symlink_to(self._new_path())

        buf = io.StringIO()
        with patch.dict(os.environ, self._env(), clear=False):
            with redirect_stderr(buf):
                _claude_home._check_machine_local_divergence()

        self.assertEqual(buf.getvalue(), "", "compat-symlink must not emit any warning")

    def test_one_absent_no_warn(self):
        """Only new home exists → no warning (no divergence possible)."""
        self._new_path().mkdir(parents=True)

        buf = io.StringIO()
        with patch.dict(os.environ, self._env(), clear=False):
            with redirect_stderr(buf):
                _claude_home._check_machine_local_divergence()

        self.assertEqual(buf.getvalue(), "", "single-home must not emit any warning")


# ---------------------------------------------------------------------------
# machine_local_dir — prefer-new-fallback-to-legacy
# ---------------------------------------------------------------------------


class TestMachineLocalDir(unittest.TestCase):
    """machine_local_dir() resolution: prefer new, fall back to legacy, canonical new otherwise.

    Path layout under test:
      CLAUDE_HOME         → self.tmp_path / "home"
      claude_home_dir()   → self.tmp_path / "home" / ".claude"   (adds .claude)
      legacy path         → self.tmp_path / "home" / ".claude" / "machine-local"
      COORDINATOR_SETTINGS_HOME → self.tmp_path / "settings"
      new path            → self.tmp_path / "settings" / "machine-local"

    Spec backlink: docs/plans/2026-07-06-durable-substrate-to-settings-home.md § C1
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        # Review: code-reviewer (F2) — reset both once-guards (split from single flag)
        _claude_home._legacy_machine_local_divergence_warned = False
        _claude_home._legacy_machine_local_deprecated_warned = False

    def tearDown(self):
        self.tmp.cleanup()
        _claude_home._legacy_machine_local_divergence_warned = False
        _claude_home._legacy_machine_local_deprecated_warned = False

    def _new_path(self):
        return self.tmp_path / "settings" / "machine-local"

    def _legacy_path(self):
        # claude_home_dir() = CLAUDE_HOME / ".claude", legacy = that / "machine-local"
        return self.tmp_path / "home" / ".claude" / "machine-local"

    def _env(self):
        return {
            "CLAUDE_HOME": str(self.tmp_path / "home"),
            "COORDINATOR_SETTINGS_HOME": str(self.tmp_path / "settings"),
        }

    def test_prefer_new_when_both_exist(self):
        """new exists → return new regardless of legacy presence."""
        self._new_path().mkdir(parents=True)
        self._legacy_path().mkdir(parents=True)

        with patch.dict(os.environ, self._env(), clear=False):
            result = _claude_home.machine_local_dir()

        self.assertEqual(result, self._new_path())

    def test_prefer_new_no_warning_when_new_exists(self):
        """new exists → no deprecation warning even if legacy also exists."""
        self._new_path().mkdir(parents=True)
        self._legacy_path().mkdir(parents=True)

        buf = io.StringIO()
        with patch.dict(os.environ, self._env(), clear=False):
            with redirect_stderr(buf):
                _claude_home.machine_local_dir()

        self.assertEqual(buf.getvalue(), "", "no warning expected when new path exists")

    def test_fallback_to_legacy_when_new_absent(self):
        """new absent, legacy present → return legacy + emit one-time warning."""
        self._legacy_path().mkdir(parents=True)

        buf = io.StringIO()
        with patch.dict(os.environ, self._env(), clear=False):
            with redirect_stderr(buf):
                result = _claude_home.machine_local_dir()

        self.assertEqual(result, self._legacy_path())
        err = buf.getvalue()
        self.assertIn("DEPRECATED LEGACY HOME IN USE", err)
        self.assertIn("coordinator/lib/migrate-substrate-to-settings-home.sh", err)

    def test_canonical_new_when_neither_exists(self):
        """Neither new nor legacy exists → return canonical new path, no warning."""
        buf = io.StringIO()
        with patch.dict(os.environ, self._env(), clear=False):
            with redirect_stderr(buf):
                result = _claude_home.machine_local_dir()

        self.assertEqual(result, self._new_path())
        self.assertEqual(buf.getvalue(), "", "no warning expected when neither path exists")

    def test_warn_only_once_on_repeated_calls(self):
        """One-time guard: a second call with legacy-only setup must not re-emit the warning."""
        self._legacy_path().mkdir(parents=True)

        lines = []
        with patch.dict(os.environ, self._env(), clear=False):
            for _ in range(3):
                buf = io.StringIO()
                with redirect_stderr(buf):
                    _claude_home.machine_local_dir()
                if buf.getvalue():
                    lines.append(buf.getvalue())

        self.assertEqual(len(lines), 1, "deprecation warning must appear exactly once across multiple calls")

    def test_never_return_nonexistent_legacy(self):
        """When legacy does not exist, must never return legacy path — return new instead."""
        with patch.dict(os.environ, self._env(), clear=False):
            result = _claude_home.machine_local_dir()

        self.assertNotEqual(result, self._legacy_path(), "must not return a non-existent legacy path")


if __name__ == "__main__":
    unittest.main(verbosity=2)
