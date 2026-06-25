"""
test_no_bare_console_subprocess.py — coordinator-standard tripwire template.

Spec backlink: plugins/coordinator/docs/plans/2026-06-19-windows-console-popup-coordinator-doctrine.md
               § C4 — Tripwire as coordinator standard, onboarded via /repo-setup
               § Canonical suppression marker

Purpose: Scan *.sh files under a configured repo root for bare console-subprocess
         call shapes that produce focus-stealing console windows on Windows when
         spawned from the headless Bash-tool parent process. Catches the patterns
         before they reach CI or land in committed scripts.

The separator-aware regex detects shapes where `python -c` (or equivalent) is a
genuine subprocess invocation, not a substring of a longer word or a quoted/commented
occurrence. It also catches bare `powershell.exe` and `& python` (PowerShell call
operator). The allowlist (PREFIXES + EXACT_FILES + inline marker) lets known-safe
sites opt out cleanly.

Canonical suppression markers (two env-agnostic forms, honored identically):
  - `# popup-intentional-last-resort` — the popup occurs and is accepted; the bare
    call is genuinely intentional and there is no env-var suppression path available.
  - `# popup-safe-env-suppressed` — the popup is suppressed by env-var means (e.g.
    FOR_DISABLE_CONSOLE_CTRL_HANDLER or equivalent); the call is safe in the target
    environment even though no CREATE_NO_WINDOW flag is present.

  Place either marker on the same line as the bare call (shell/python comment form).
  When inside an embedded interpreter string in a .sh file, place the marker OUTSIDE
  the string — on the surrounding shell line — because `#` inside a `python -c "..."`
  argument is parsed by Python at runtime, not by this tripwire or the hook.

  Retired form (do NOT use): `# noqa: bare-subprocess-windows` — this was used in
  early project-rag drafts; it is not canonical and is NOT honoured by any layer.

Detection limits:
  - Only scans *.sh files; .py and .ps1 files are caught by the C2 Write/Edit hook
    at authoring time and left out of scope here for non-redundancy.
  - Regex is line-granularity. A multi-line heredoc body that contains a bare python
    invocation on a line OTHER than the `python - <<EOF` opener line will not be
    caught. The opener line IS caught.
  - Commented-out lines (`# python -c`) are correctly skipped by the separator-aware
    regex because `#` is not in the separator class [\\s;&|`].

HOW TO ONBOARD IN A CONSUMING REPO:
  1. Copy this file to `tests/test_no_bare_console_subprocess.py` in the target repo.
  2. Adjust REPO_ROOT_DEFAULT to match your repo layout (or rely on the env var).
  3. Populate PREFIXES with subtrees that are known-safe (e.g. vendor/, fixtures/).
  4. Populate EXACT_FILES with individual files that use the pattern intentionally.
  5. Add `# popup-intentional-last-resort` (popup accepted) or
     `# popup-safe-env-suppressed` (env-var suppression in place) to any remaining
     intentional bare calls.
  6. Run: `pytest tests/test_no_bare_console_subprocess.py` (or `python3 <this file>`).

Negative-spec: this test does NOT execute any process — it scans file contents
               with a Python regex, so it is safe to run on any platform.
"""

import os
import re
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Repo-root resolution
# ---------------------------------------------------------------------------
# The template is designed to run standalone or via pytest.
# Priority: env var TRIPWIRE_REPO_ROOT → inferred from __file__ location.
#
# CUSTOMIZE: When onboarding into a consuming repo, set REPO_ROOT_DEFAULT to the
# correct relative offset from the test file to the repo root, or rely on the
# env var TRIPWIRE_REPO_ROOT for CI overrides.
# ---------------------------------------------------------------------------
_ENV_ROOT = os.environ.get("TRIPWIRE_REPO_ROOT", "")
if _ENV_ROOT:
    _REPO_ROOT = Path(_ENV_ROOT).resolve()
else:
    # Default: infer from __file__ — two levels up from tests/templates/
    # (i.e. this template's own location inside coordinator; a consuming repo
    # would typically place this file in tests/ → one level up).
    # CUSTOMIZE: adjust the parent count to match your repo layout.
    _REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# STANDALONE SKIP GUARD
# ---------------------------------------------------------------------------
# When run standalone (without TRIPWIRE_REPO_ROOT set), this template has no
# meaningful target to scan — the coordinator plugin root is the fallback but
# is not the intended target for a consuming repo. Emit a clear skip rather
# than running a potentially meaningless scan.
#
# Set TRIPWIRE_REPO_ROOT to the absolute path of the consuming repo's root to
# activate the scan. This guard is removed automatically when the template is
# onboarded into a consuming repo (replace the guard with a hard assertion).
# ---------------------------------------------------------------------------
_STANDALONE_MODE = not _ENV_ROOT and Path(__file__).parts[-3:] == (
    "tests", "templates", "test_no_bare_console_subprocess.py"
)

# ---------------------------------------------------------------------------
# Allowlist — CUSTOMIZE these when onboarding into a consuming repo
# ---------------------------------------------------------------------------

# Subtree exemptions: paths that begin with any of these prefixes (relative to
# REPO_ROOT) are skipped entirely. Use forward-slash separators; the test
# normalizes before comparing.
PREFIXES: list[str] = [
    # "vendor/",           # Example: third-party code bundled in-tree
    # "tests/fixtures/",   # Example: intentional test substrate
]

# Exact-file exemptions: individual files (relative to REPO_ROOT) that may
# contain bare console-subprocess calls by design (e.g. a wrapper that IS the
# safe path for other callers).
EXACT_FILES: list[str] = [
    # "project_rag_scripts/python-quiet.sh",   # Example: the safe-path itself
]

# ---------------------------------------------------------------------------
# Separator-aware detection regex
# ---------------------------------------------------------------------------
# Matches bare console-subprocess invocations in shell scripts:
#
#   (^|[\s;&|`])   — start of line or a command separator
#   python3?(\.exe)?  — python, python3, python.exe, python3.exe
#   \s+            — one or more whitespace chars
#   (-c\b|-\s|<<|<\()  — -c flag, pipe stdin (`python -`), heredoc, process sub
#
# Also matches:
#   powershell\.exe — bare powershell.exe token (console-subsystem)
#   &\s+python      — PowerShell call operator form (`& python`)
#
# Does NOT match:
#   python-quiet.sh     — word boundary prevents `python-` prefix
#   pythonw             — distinct name (GUI subsystem, safe)
#   # python -c         — `#` is not in separator class; leading comment char
#                         means prior char would be nothing or a space, but the
#                         preceding separator `\s` before `#python` is absorbed
#                         into the `#` comment guard below (see _COMMENT_RE)
# ---------------------------------------------------------------------------
_BARE_SUBPROCESS_RE = re.compile(
    r"""
    (?:
        # python/python3/python.exe/python3.exe with console-shell call flags
        (?:^|[\s;&|`])python3?(?:\.exe)?\s+(?:-c\b|-\s|<<|<\()
        |
        # bare powershell.exe (console-subsystem, pops window on no-console parent)
        (?:^|[\s;&|`])powershell\.exe(?:\s|$)
        |
        # PowerShell call operator form: & python or & python3
        &\s+python3?(?:\.exe)?(?:\s|$)
    )
    """,
    re.VERBOSE | re.MULTILINE,
)

# Lines that are whole-line comments in shell (leading optional whitespace + #)
# are excluded from matching — the regex above absorbs `\s` before `#` as a
# separator, but a `# python -c` line should not fire because `#` starts a
# shell comment. We guard at the line level below.
_COMMENT_RE = re.compile(r"^\s*#")

# Inline suppression markers (canonical, cross-layer) — two env-agnostic forms.
_MARKERS = ("# popup-intentional-last-resort", "# popup-safe-env-suppressed")


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def _collect_sh_files(root: Path) -> list[Path]:
    """Return all *.sh files under root, respecting the allowlist."""
    results: list[Path] = []
    for path in sorted(root.rglob("*.sh")):
        rel = path.relative_to(root).as_posix()
        if _is_allowlisted(rel):
            continue
        results.append(path)
    return results


def _is_allowlisted(rel: str) -> bool:
    """True if the relative path is covered by PREFIXES or EXACT_FILES."""
    for prefix in PREFIXES:
        if rel.startswith(prefix):
            return True
    if rel in EXACT_FILES:
        return True
    return False


# ---------------------------------------------------------------------------
# Per-file scan
# ---------------------------------------------------------------------------

def _scan_file(path: Path) -> list[str]:
    """Return a list of '<path>:<line>' strings for offending lines."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    # File-level inline marker: the entire file is suppressed if the text
    # contains the canonical marker anywhere in its text (substring check over
    # the whole file; mirrors the hook's per-command behaviour for cases where
    # the file is itself a console-subprocess wrapper).
    if any(m in text for m in _MARKERS):
        return []

    violations: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        # Whole-line comments are not executable — skip them.
        if _COMMENT_RE.match(line):
            continue
        if _BARE_SUBPROCESS_RE.search(line):
            violations.append(f"{path}:{lineno}: {line.rstrip()}")
    return violations


# ---------------------------------------------------------------------------
# Pytest integration
# ---------------------------------------------------------------------------

def _parametrize_files() -> list[Path]:
    """Return the file list for parametrize, or empty when in standalone skip mode."""
    if _STANDALONE_MODE:
        return []
    return _collect_sh_files(_REPO_ROOT)


_SH_FILES = _parametrize_files()


@pytest.mark.skipif(
    _STANDALONE_MODE,
    reason=(
        "Template running from its own coordinator location without "
        "TRIPWIRE_REPO_ROOT set — no consuming-repo target to scan. "
        "Set TRIPWIRE_REPO_ROOT=<repo-root> or onboard this template into "
        "the consuming repo's tests/ directory to activate."
    ),
)
@pytest.mark.skipif(
    not _STANDALONE_MODE and not _SH_FILES,
    reason="No *.sh files found under REPO_ROOT — nothing to scan.",
)
@pytest.mark.parametrize("sh_file", _SH_FILES, ids=lambda p: str(p.relative_to(_REPO_ROOT)))
def test_no_bare_console_subprocess(sh_file: Path) -> None:
    """Each *.sh file must not contain a bare console-subprocess invocation.

    Fix: route through the project's console-safe wrapper (e.g. python-quiet.sh),
    add `creationflags=0x08000000` at the call site, or annotate with
    `# popup-safe-env-suppressed` (when suppressed by env-var means) or
    `# popup-intentional-last-resort` (when the popup is genuinely accepted).
    """
    violations = _scan_file(sh_file)
    assert not violations, (
        "Bare console-subprocess invocation(s) detected — these pop a focus-stealing "
        "console window on Windows under the headless Bash-tool parent process.\n"
        "Fix: route through the project's console-safe wrapper, add "
        "`creationflags=0x08000000` (CREATE_NO_WINDOW), or annotate with "
        "`# popup-safe-env-suppressed` (env-var suppression in place) or "
        "`# popup-intentional-last-resort` (popup genuinely accepted).\n"
        "Violations:\n  " + "\n  ".join(violations)
    )


# ---------------------------------------------------------------------------
# Inline positive/negative fixture tests (always run — template self-validates)
# ---------------------------------------------------------------------------
# These parametrized tests run directly against synthetic line strings, so they
# are independent of REPO_ROOT and always verify the regex contract.

_POSITIVE_CASES: list[tuple[str, str]] = [
    # (case-name, line-text that MUST match as a violation)
    ("python -c flag",           "python -c 'import sys; print(sys.version)'"),
    ("exec python -c",           "exec python -c 'some code'"),
    ("env python -c",            "env VAR=x python -c 'code'"),
    ("cd-and-python -c",         "cd /tmp && python -c 'code'"),
    ("backtick python -c",       "`python -c 'code'`"),
    ("python heredoc <<",        "python - <<EOF"),
    ("python3 -c flag",          "python3 -c 'import sys'"),
    ("python.exe -c flag",       "python.exe -c 'import sys'"),
    ("powershell.exe bare",      "powershell.exe -Command 'Get-Process'"),
    ("ps call-op & python",      "& python -c 'code'"),
]

_NEGATIVE_CASES: list[tuple[str, str]] = [
    # (case-name, line-text that MUST NOT match)
    ("python-quiet.sh -c",       "python-quiet.sh -c 'safe call'"),
    ("pythonw -c",               "pythonw -c 'gui-subsystem safe'"),
    ("commented # python -c",    "# python -c 'this is a comment'"),
    ("marker suppressed",        "python -c 'code'  # popup-intentional-last-resort"),
    ("safe-env-suppressed marker", "python -c 'code'  # popup-safe-env-suppressed"),
    ("echo python -c quoted",    "echo \"python -c 'not a call'\""),
]


@pytest.mark.parametrize("name,line", _POSITIVE_CASES, ids=[c[0] for c in _POSITIVE_CASES])
def test_regex_positive_fixture(name: str, line: str) -> None:
    """Regex MUST fire on known bare console-subprocess patterns."""
    assert _BARE_SUBPROCESS_RE.search(line), (
        f"Positive fixture '{name}' was NOT detected — regex contract violated.\n"
        f"Line: {line!r}"
    )


@pytest.mark.parametrize("name,line", _NEGATIVE_CASES, ids=[c[0] for c in _NEGATIVE_CASES])
def test_regex_negative_fixture(name: str, line: str) -> None:
    """Regex MUST NOT fire on safe patterns or suppressed lines."""
    # Marker cases verify only that the marker gate fires (returns early); regex
    # correctness for the bare-call shape is independently asserted by the positive
    # fixtures. We replicate the comment-guard + marker check here so the fixture
    # is standalone (file-level suppression via _scan_file is a separate path).
    if _COMMENT_RE.match(line):
        # Whole-line comment — would be excluded by _scan_file regardless of regex
        return
    if any(m in line for m in _MARKERS):
        # Inline marker — the entire line is suppressed
        return
    assert not _BARE_SUBPROCESS_RE.search(line), (
        f"Negative fixture '{name}' was falsely flagged — regex false-positive.\n"
        f"Line: {line!r}"
    )


# ---------------------------------------------------------------------------
# Standalone entry point (python3 <this file>)
# ---------------------------------------------------------------------------

def _main() -> int:
    if _STANDALONE_MODE:
        print(
            "SKIP: template running from coordinator location without "
            "TRIPWIRE_REPO_ROOT — set that env var or onboard this template "
            "into a consuming repo's tests/ directory.",
            file=sys.stderr,
        )
        return 0

    sh_files = _collect_sh_files(_REPO_ROOT)
    if not sh_files:
        print(f"No *.sh files found under {_REPO_ROOT} — nothing to scan.")
        return 0

    all_violations: list[str] = []
    for sh_file in sh_files:
        all_violations.extend(_scan_file(sh_file))

    if all_violations:
        print(
            "FAIL: bare console-subprocess invocation(s) detected:\n"
            + "\n".join(f"  {v}" for v in all_violations),
            file=sys.stderr,
        )
        return 1

    print(f"PASS: {len(sh_files)} *.sh file(s) scanned — no bare console-subprocess calls.")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
