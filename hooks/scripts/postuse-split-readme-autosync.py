"""PostToolUse hook: keep a doctrine split directory's generated README.md in step with its bodies.

A split directory holds `_preamble.md` plus a generated `README.md` index. After an Edit/Write of
one of its body files, this hook re-renders that README through the generator's
`regenerate_split_dir` (README only; bodies and preamble are never touched). Writing nothing when
the README is already current keeps it idle for the common edit.

Contract: stdin PostToolUse JSON; stdout always empty; exit 0 on every path. A generator refusal
(untracked or unstaged-deleted bodies) or any error is a one-line stderr note, never a failed tool
call. The HEAD-based drift test stays the backstop for what the hook skips.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
from pathlib import Path

GENERATOR_NAME = "generate-doctrine-surface-split.py"
README = "README.md"
PREAMBLE = "_preamble.md"


def _generator_candidates(file_path: Path) -> list[Path]:
    """Own plugin tree first, then any `coordinator/lib` above the edited file."""
    found = [Path(__file__).resolve().parents[2] / "lib" / GENERATOR_NAME]
    found += [p / "coordinator" / "lib" / GENERATOR_NAME for p in file_path.parents]
    return found


def _load_generator(file_path: Path):
    for candidate in _generator_candidates(file_path):
        if candidate.is_file():
            spec = importlib.util.spec_from_file_location("_split_readme_generator", candidate)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    return None


def split_dir_of(file_path: Path) -> Path | None:
    """The split directory `file_path` is a body of, else None."""
    if file_path.suffix != ".md" or file_path.name in (README, PREAMBLE):
        return None
    parent = file_path.parent
    if (parent / PREAMBLE).is_file() and (parent / README).is_file():
        return parent
    return None


def sync(file_path: str) -> int:
    """Regenerate the README of the split dir owning `file_path`; 0 when nothing to do or done."""
    path = Path(file_path)
    split_dir = split_dir_of(path)
    if split_dir is None:
        return 0
    generator = _load_generator(path)
    if generator is None:
        return 0
    with contextlib.redirect_stderr(io.StringIO()):  # check mode prints the whole diff
        in_sync = generator.regenerate_split_dir(split_dir, check_mode=True) == 0
    if in_sync:
        return 0
    rc = generator.regenerate_split_dir(split_dir)
    if rc != 0:
        print(
            f"split-readme-autosync: {split_dir.name}/{README} left stale (generator exit {rc}); "
            f"run `generate-doctrine-surface-split.py {split_dir} --regenerate`",
            file=sys.stderr,
        )
    return rc


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
        tool_input = payload.get("tool_input") if isinstance(payload, dict) else None
        file_path = tool_input.get("file_path") if isinstance(tool_input, dict) else None
        if isinstance(file_path, str) and file_path:
            sync(file_path)
    except Exception as exc:  # fail open: an advisory sync must never fail a tool call
        print(f"split-readme-autosync: skipped ({type(exc).__name__}: {exc})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
