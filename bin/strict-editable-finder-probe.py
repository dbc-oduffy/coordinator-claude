"""strict-editable-finder-probe — detects finder-based/non-src editable installs on a shared
Python interpreter.

Scans `site-packages` for `__editable__.<dist>-<ver>.pth` files (the marker setuptools' editable
install writes) and classifies each one against `docs/decisions/DR-fleet-editables-src-layout-
before-compat.md`'s ordering rule: src-layout first, compat second, `pip config` last. A finder-
based editable install (`import-finder`) or a compat install whose `.pth` puts an entire repo root
on `sys.path` (`repo-root-on-path`) is the flat-layout hazard that ordering rule exists to prevent
on a shared interpreter — see `coordinator/docs/wiki/portability/fleet-shared-python-environment.md`
§ "One namespace, shared by every consumer" for why a repo root on `sys.path` is unsafe there in a
way it would not be in a private venv.

Why the `__editable__` filename prefix is the discriminator, not "body begins with `import`":
`distutils-precedence.pth` also begins its body with an `import` statement
(`import sys; sys.path=[p for p in sys.path if p != '']`) and ships with *every* setuptools
install, editable or not — an `import`-heuristic alone would flag every interpreter on the fleet.
`pywin32`'s `.pth` files invoke a `bootstrap.py` step through an `import` line too, and are not
editable installs at all. Requiring the `__editable__.` prefix first is what makes the subsequent
"first line is `import`" check mean "finder-based editable", instead of "any package that happens
to run import-time path setup".

INVOCATION CONTRACT — subprocess only, by absolute path, matching `host-gpu-probe.py`'s pattern:

    python <repo>/coordinator/bin/strict-editable-finder-probe.py [--site-dir DIR ...]

Prints one JSON object `{"findings": [...]}` to stdout. Each finding is
`{"pth": <filename>, "dist": <distribution name>, "class": "import-finder" | "repo-root-on-path"}`.
Exit code is 0 when `findings` is empty, 1 when it is not. With no `--site-dir`, scans
`site.getsitepackages()` plus `site.getusersitepackages()`, silently skipping any that do not
exist (a fresh interpreter, or one with no user site).

Negative spec: this module does NOT flag a compat `.pth` whose path line resolves to a `src/`
directory holding no `pyproject.toml`/`setup.py`/`setup.cfg` — that shape is clean per the DR's
rationale (setuptools' compat mode adding a `src/` dir, not a whole repo root, to `sys.path`). It
does NOT flag `distutils-precedence.pth` or any `.pth` file not named `__editable__.*.pth`. It does
NOT import torch, chromadb, or any heavy dependency — stdlib only. It does NOT mutate `sys.path`,
install anything, or touch packaging state; it only reads.

Spec backlink: docs/plans/2026-09-26-fleet-strict-mode-editable-installs.md, row C2.
"""
from __future__ import annotations

import argparse
import json
import re
import site
import sys
from pathlib import Path

_PROJECT_MARKERS = ("pyproject.toml", "setup.py", "setup.cfg")

# The version segment of `<dist>-<ver>` always starts with a digit (PEP 440); the dist segment
# itself may legitimately contain hyphens (e.g. "project-rag"), so a plain rightmost-hyphen split
# is wrong whenever the version itself contains a dot-separated hyphen-free run. Greedy `.+`
# backtracks to the LAST hyphen immediately followed by a digit, which is the version boundary.
_DIST_VERSION_RE = re.compile(r"^(?P<dist>.+)-(?P<version>\d.*)$")


def _extract_dist(filename: str) -> str | None:
    """Take the distribution name from `__editable__.<dist>-<ver>.pth`.

    Returns None for anything that is not that shape (including `distutils-precedence.pth` and
    any plain, non-editable `.pth` file) — the caller uses that None to skip the file entirely,
    which is the discriminator this module's docstring explains.
    """
    prefix = "__editable__."
    suffix = ".pth"
    if not filename.startswith(prefix) or not filename.endswith(suffix):
        return None
    stem = filename[len(prefix) : -len(suffix)]
    if not stem:
        return None
    match = _DIST_VERSION_RE.match(stem)
    if match:
        return match.group("dist") or None
    return stem


def _resolve_path_line(line: str, pth_parent: Path) -> Path | None:
    """Resolve a `.pth` path line against the `.pth` file's own parent directory when relative.

    Goes through `pathlib` throughout so a Windows backslash path line resolves the same as a
    POSIX forward-slash one.
    """
    candidate = Path(line)
    if not candidate.is_absolute():
        candidate = pth_parent / candidate
    try:
        return candidate.resolve()
    except OSError:
        return None


def _classify_pth(path: Path) -> dict | None:
    """Classify one `.pth` file, or return None if it carries no finding.

    Only the FIRST non-blank, non-`#` line decides the import-finder case (AC4). If that line is
    not an `import` line, every remaining non-blank, non-`#`, non-`import` line is evaluated as a
    candidate path line for the repo-root-on-path case — a real compat `.pth` can carry more than
    one path line.
    """
    filename = path.name
    dist = _extract_dist(filename)
    if dist is None:
        return None

    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    content_lines = [ln.strip() for ln in raw_lines if ln.strip() and not ln.strip().startswith("#")]
    if not content_lines:
        return None

    if content_lines[0].startswith("import"):
        return {"pth": filename, "dist": dist, "class": "import-finder"}

    for line in content_lines:
        if line.startswith("import"):
            continue
        resolved = _resolve_path_line(line, path.parent)
        if resolved is None:
            continue
        if any((resolved / marker).is_file() for marker in _PROJECT_MARKERS):
            return {"pth": filename, "dist": dist, "class": "repo-root-on-path"}

    return None


def classify(site_dirs: list[str]) -> list[dict]:
    """Scan each site dir's top-level `.pth` files and return every finding, in stable order."""
    findings: list[dict] = []
    for site_dir in site_dirs:
        d = Path(site_dir)
        if not d.is_dir():
            continue
        for entry in sorted(d.iterdir()):
            if not entry.is_file() or entry.suffix != ".pth":
                continue
            finding = _classify_pth(entry)
            if finding is not None:
                findings.append(finding)
    return findings


def _default_site_dirs() -> list[str]:
    dirs: list[str] = []
    try:
        dirs.extend(site.getsitepackages())
    except AttributeError:
        pass
    try:
        user_site = site.getusersitepackages()
    except AttributeError:
        user_site = None
    if user_site:
        dirs.append(user_site)
    return [d for d in dirs if Path(d).is_dir()]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--site-dir",
        action="append",
        default=None,
        help="A site-packages directory to scan; repeatable. Defaults to "
        "site.getsitepackages() + site.getusersitepackages().",
    )
    args = parser.parse_args(argv)

    site_dirs = args.site_dir if args.site_dir else _default_site_dirs()
    findings = classify(site_dirs)
    print(json.dumps({"findings": findings}))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
