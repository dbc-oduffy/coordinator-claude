"""Percolate preflight: refuse an engine publish whose shipped text names a `machine-local <verb>` the plugin lacks.

Verb set = subparsers registered in `coordinator/templates/bin/_machine_local.py`. The scan
covers the resolved engine root's shipped text; each absent verb prints with file:line and the
process exits 2. Exit 0 = every named verb exists; exit 1 = engine root or verb source unreadable.

    python _engine_remedy_verb_preflight.py [--engine-root DIR] [--machine-local FILE]
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterator
from pathlib import Path

_HERE = Path(__file__).resolve()
_DEFAULT_MACHINE_LOCAL = _HERE.parents[2] / "templates" / "bin" / "_machine_local.py"

_SCAN_SUFFIXES = {".py", ".md", ".sh", ".yaml", ".yml", ".toml", ".txt"}
_SKIP_DIRS = {".git", "node_modules", "__pycache__", "scratch", "archive", "tests", ".venv", "venv"}

_SUBPARSER_RE = re.compile(r"subparsers\.add_parser\(\s*[\"']([A-Za-z0-9_-]+)[\"']")
# A verb named in a remedy sits right after a quote, backtick, `$ ` or line start, and is
# either hyphenated or closed by a backtick or followed by a flag/placeholder. Prose such as
# "machine-local registry" or "machine-local not found" is not a command reference; a bare
# single-word absent verb quoted without flags is the accepted blind spot.
_REFERENCE_RE = re.compile(
    r"(?:^|[`\"']|\$\s)machine-local\s+(?P<verb>[a-z][a-z0-9]*(?:-[a-z0-9]+)*)(?![\w-])"
)
_INVOCATION_END_RE = re.compile(r"`|\s+--?\w|\s+<")


def _is_invocation(verb: str, rest: str) -> bool:
    return "-" in verb or _INVOCATION_END_RE.match(rest) is not None


def registered_verbs(machine_local: Path) -> set[str]:
    """Subcommand names registered via `subparsers.add_parser("<verb>"` in `machine_local`."""
    return set(_SUBPARSER_RE.findall(machine_local.read_text(encoding="utf-8")))


def _iter_text_files(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in _SCAN_SUFFIXES:
            continue
        if _SKIP_DIRS.intersection(path.relative_to(root).parts[:-1]):
            continue
        yield path


def find_absent_verbs(engine_root: Path, verbs: set[str]) -> list[tuple[Path, int, str]]:
    """Return `(file, line_no, verb)` for each `machine-local <verb>` under `engine_root` not in `verbs`."""
    hits: list[tuple[Path, int, str]] = []
    for path in _iter_text_files(engine_root):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for match in _REFERENCE_RE.finditer(line):
                verb = match["verb"]
                if _is_invocation(verb, line[match.end():]) and verb not in verbs:
                    hits.append((path, lineno, verb))
    return hits


def _resolve_engine_root() -> Path:
    sys.path.insert(0, str(_HERE.parent))
    from _prepublish_projection import _resolve_claude_klabauter_root

    return _resolve_claude_klabauter_root()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--engine-root", type=Path, default=None)
    parser.add_argument("--machine-local", type=Path, default=_DEFAULT_MACHINE_LOCAL)
    args = parser.parse_args(argv)

    try:
        engine_root = args.engine_root or _resolve_engine_root()
        verbs = registered_verbs(args.machine_local)
    except Exception as exc:  # noqa: BLE001 -- surfaced as exit 1, not swallowed
        print(f"engine-remedy-verb preflight: cannot run: {exc}", file=sys.stderr)
        return 1
    if not verbs:
        print(f"engine-remedy-verb preflight: no verbs parsed from {args.machine_local}", file=sys.stderr)
        return 1

    hits = find_absent_verbs(engine_root, verbs)
    for path, lineno, verb in hits:
        print(f"{path}:{lineno}: machine-local {verb}: verb absent from the plugin")
    return 2 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
