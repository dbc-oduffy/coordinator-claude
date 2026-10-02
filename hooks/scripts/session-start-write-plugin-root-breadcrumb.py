"""SessionStart hook — writes this plugin's own root to a fixed `$HOME` path so the
plugin-shipped `subagentStatusLine` command can locate a script inside its own plugin.

WHY A BREADCRUMB EXISTS AT ALL. `statusline.md:223` says a plugin may ship a default
`subagentStatusLine` in its settings.json, and every other plugin surface locates its own files
through `${CLAUDE_PLUGIN_ROOT}`. That placeholder does NOT resolve inside a `subagentStatusLine`
command: observed on Claude Code 2.1.269, Windows 11, the variable is absent from the command's
environment entirely, the working directory is the PROJECT rather than the plugin, and the only
path-bearing `CLAUDE_*` variable in scope is `CLAUDE_PROJECT_DIR` (upstream
anthropics/claude-code#81320, open, reproduced on Linux by a collaborator). A plugin-shipped
statusline command therefore has no in-band way to find its own script. Hooks are the seam where
`${CLAUDE_PLUGIN_ROOT}` DOES resolve, so this hook hands the statusline command the one fact it
cannot obtain for itself.

FORWARD SLASHES, ALWAYS. The breadcrumb is consumed inside a double-quoted shell word on every
platform, and `statusline.md § Troubleshooting` records that on Windows with Git Bash installed,
backslashes in a statusline command path are consumed as escape characters before the command
runs. A Windows root is written with forward slashes throughout, never with backslash separators.

`$HOME`, not `$TMPDIR` or the settings home. The consumer is a bare shell command string with no
coordinator environment loaded: `$TMPDIR` is unset in Git Bash on Windows, and
`$COORDINATOR_SETTINGS_HOME` is not guaranteed to be exported into the harness's statusline
environment. `$HOME` resolves identically in Git Bash and every POSIX shell.

ONE SOURCE OF TRUTH. The value is the `installPath` of the installed `coordinator@*` record in
`~/.claude/plugins/installed_plugins.json`, not the running hook's own `__file__`, so sessions
loaded from a cache and from a source clone write the same bytes. Only when no record resolves
does the hook fall back to its own root, and never when that root is a non-authoring source
clone (a consumer profile).

KNOWN LIMIT: `disableAllHooks` leaves no breadcrumb, so rows fall back to the harness's own
default render — degraded, never broken.

WRITTEN ATOMICALLY, because the reader is a `cat` on a hot path. The consumer runs once per
statusline refresh tick in every live session, so a plain `write_text` — open, truncate, write,
close — exposes a window where a concurrent reader sees an empty or half-written path. Writing to
a sibling temp file and `os.replace`-ing it over the target closes that window on POSIX and
Windows alike: a reader sees either the old path or the new one, never a partial one. Sessions
racing each other still last-writer-wins, which is harmless — they write identical bytes.

Contract:
  stdin   — SessionStart JSON payload (unused: this hook resolves its OWN root from `__file__`,
            per CLAUDE.md "Scripts self-resolve their own root from BASH_SOURCE, never cwd")
  stdout  — NOTHING. Folded into `sessionstart-async-dispatch.py`, whose whole membership test is
            "side-effect write, no context-bound output, must not sit on boot latency".
  exit 0  — ALWAYS. Every failure mode (unresolvable `$HOME`, an unwritable or read-only path, a
            concurrent writer) degrades to a silent no-op. A SessionStart hook that raises greets
            every session in the fleet with a stack trace; a missing breadcrumb costs a default
            statusline row.

Idempotence: reads the current value first and writes nothing when it already matches this
plugin's root, so a healthy box pays one small read per session and returns.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

BREADCRUMB_RELATIVE_PATH = ".claude/.coordinator-plugin-root"

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

try:
    from _engine_root import _find_plugin_root  # noqa: E402
except Exception:  # pragma: no cover - partial-deploy defence
    # A stub, never a second resolver: an unimportable `_engine_root` drops the breadcrumb
    # rather than depth-counting a root the shared helper exists to compute correctly.
    def _find_plugin_root(start):  # type: ignore[no-redef]
        return None


def _own_root() -> str | None:
    """Name-anchored on the nearest ancestor holding `.claude-plugin/`
    (`_engine_root._find_plugin_root`), never depth-counted: the flat mirror layout differs
    from the nested one."""
    root = _find_plugin_root(Path(__file__).resolve().parent)
    return None if root is None else root.as_posix()


def _installed_root(home: str) -> str | None:
    """The `installPath` of the installed `coordinator@*` record: the one source of truth, so
    concurrent sessions loaded from different trees write identical bytes."""
    try:
        from _hook_plane_probe import _load_json_dict, _resolve_install_path
        config_dir = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path(home) / ".claude")
        plugins = _load_json_dict(config_dir / "plugins" / "installed_plugins.json").get("plugins")
        for key in sorted(plugins) if isinstance(plugins, dict) else ():
            if not key.startswith("coordinator@"):
                continue
            install_path, _ = _resolve_install_path(config_dir, key)
            if install_path and Path(install_path).is_dir():
                return Path(install_path).as_posix()
    except Exception:
        return None
    return None


def _is_consumer_source_clone(root: str) -> bool:
    """A git checkout of the plugin that is not the authoring repo (no dev-repo sentinel)."""
    repo = Path(root).parent
    return (repo / ".git").exists() and not (repo / ".coordinator-dev-repo").exists()


def _plugin_root(home: str | None = None) -> str | None:
    if home is None:
        home = os.environ.get("HOME") or os.path.expanduser("~")
    installed = _installed_root(home)
    if installed is not None:
        return installed
    own = _own_root()
    if own is None or _is_consumer_source_clone(own):
        return None
    return own


def _breadcrumb_path() -> Path | None:
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE") or os.path.expanduser("~")
    if not home or home == "~":
        return None
    return Path(home) / BREADCRUMB_RELATIVE_PATH


def main() -> int:
    try:
        target = _breadcrumb_path()
        if target is None:
            return 0
        root = _plugin_root(str(target.parents[1]))
        if root is None:
            return 0
        try:
            if target.read_text(encoding="utf-8").strip() == root:
                return 0
        except OSError:
            pass
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(target.parent), prefix=target.name + ".")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(root + "\n")
            os.replace(tmp_name, target)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
