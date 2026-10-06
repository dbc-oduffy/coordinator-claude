"""SessionStart self-heal: this repo's `.git/hooks/pre-commit` gate chain is
installed on every box that runs a session here.

`.git/hooks` is per-clone and untracked, so a gate chain that only an operator
installs by hand is installed nowhere. The gates the installer lays down -- the
doctrine-surface admission leg, the doctrine-weight ratchet's enforcing leg,
and the phantom-staged-deletion leg of the committer P0 -- never run on a
commit unless something installs them. The admission leg is the one porcelain
`git commit` needs: engine commits get the same check in-process, because they
run no git hook at all.

This loads the pre-commit installer that ships inside the session's own repo
(`install_content_root_precommit_hook.py` under the repo's plugin `bin/lib`) by
file path and calls its `main([root])`. The installer is idempotent ("already
installed and current -- no-op"), refuses any repo other than the doctrine repo
it targets, and appends to rather than clobbering a foreign hook, so calling it
on every boot costs one file read on a healthy box.

The repo root is the payload cwd's first ancestor holding `.git` (pure pathlib,
no subprocess), and only a root whose `.coordinator-dev-repo` carries
`slug: coordinator-content-repo` is acted on.

Silent unless the installer fails. Fails open everywhere: a missing installer,
an import error or an exception returns 0 without a word, because a
SessionStart hook must never stand between an operator and a session.

Negative-spec:
    Does NOT author the hook body or the gate list -- both belong to the
    installer, so there is one definition of what this repo's pre-commit runs.
    Does NOT touch a repo other than the session's own working directory.
"""


from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
from pathlib import Path

_SENTINEL_NAME = ".coordinator-dev-repo"
_EXPECTED_SLUG = "coordinator-content-repo"
_INSTALLER_REL = Path("coordinator") / "bin" / "lib" / "install_content_root_precommit_hook.py"
_PRIVATE_MODULE_NAME = "_doe_session_precommit_installer"


def _payload_cwd() -> "str | None":
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    cwd = payload.get("cwd")
    return cwd if isinstance(cwd, str) and cwd else None


def _repo_root(start: str) -> "Path | None":
    here = Path(start).resolve()
    for candidate in (here, *here.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _is_content_root(root: Path) -> bool:
    try:
        text = (root / _SENTINEL_NAME).read_text(encoding="utf-8")
    except OSError:
        return False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("slug:"):
            return stripped[len("slug:"):].strip() == _EXPECTED_SLUG
    return False


def _load_installer(root: Path):
    path = root / _INSTALLER_REL
    spec = importlib.util.spec_from_file_location(_PRIVATE_MODULE_NAME, path)
    if spec is None or spec.loader is None:
        raise ImportError(str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    try:
        root = _repo_root(_payload_cwd() or os.getcwd())
        if root is None or not _is_content_root(root):
            return 0
        installer = _load_installer(root)
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            rc = installer.main([str(root)])
        if rc != 0:
            sys.stderr.write(captured.getvalue())
    except Exception:  # noqa: BLE001 -- fail open, see module docstring.
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
