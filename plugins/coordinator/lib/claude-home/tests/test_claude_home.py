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
    home_dir,
    machine_local_dir,
    plugins_dir,
    read_config,
    write_config,
)


@contextmanager
def _isolated_env(**overrides):
    """Drop CLAUDE_HOME/HOME/USERPROFILE, then apply *overrides*; restore on exit."""
    saved = {k: os.environ.get(k) for k in ("CLAUDE_HOME", "HOME", "USERPROFILE")}
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
            self.assertEqual(machine_local_dir(), self.tmp_path / "custom" / ".claude" / "machine-local")
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
        cases = [
            ("home", str(self.tmp_path)),
            ("path", str(self.tmp_path / ".claude.json")),
            ("dir", str(self.tmp_path / ".claude")),
            ("machine-local", str(self.tmp_path / ".claude" / "machine-local")),
            ("plugins", str(self.tmp_path / ".claude" / "plugins")),
        ]
        with _isolated_env(CLAUDE_HOME=str(self.tmp_path)):
            for sub, expected in cases:
                with self.subTest(subcommand=sub):
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
