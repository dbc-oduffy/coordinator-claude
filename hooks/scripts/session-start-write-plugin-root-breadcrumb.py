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

KNOWN LIMITS, recorded rather than solved: `disableAllHooks` leaves no breadcrumb, so rows fall
back to the harness's own default render — degraded, never broken. With two plugin copies on one
box, the last session to start owns the file; both copies ship the same renderer, so the cost is
which copy runs, not whether a row renders.

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


def _plugin_root() -> str | None:
    """The plugin root is name-anchored on the nearest ancestor containing a
    `.claude-plugin/` directory (`_engine_root._find_plugin_root`), never depth-counted:
    a fixed `Path.parents[]` count is correct only under the nested plugin layout and is
    silently wrong under the flat mirror layout this file is ALSO published into.
    """
    root = _find_plugin_root(Path(__file__).resolve().parent)
    if root is None:
        return None
    return root.as_posix()


def _breadcrumb_path() -> Path | None:
    home = os.environ.get("HOME") or os.path.expanduser("~")
    if not home or home == "~":
        return None
    return Path(home) / BREADCRUMB_RELATIVE_PATH


def main() -> int:
    try:
        target = _breadcrumb_path()
        if target is None:
            return 0
        root = _plugin_root()
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
