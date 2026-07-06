#!/usr/bin/env python3
"""Block persona display names from creeping into the canonical layer.

The publish repo ships with role-based labels (`the Staff Engineer`, `the Game
Dev Reviewer`, etc.). Persona names (Patrik, Sid, Camelia, Palí, Fru, Zolí,
YK) live in the meta-repo where they're authored, but must NOT appear in
tracked canonical-layer files here. Percolation from the meta-repo can
accidentally re-introduce them; this check is the regression net.

Scope:
- Tracked `*.md`, `*.sh`, `*.py` files.
- Excludes historical / scratch dirs: archive/, tasks/, experiments/, evals/,
  and the research-archive subdirs of docs/ (plans/, research/, decisions/,
  specs/) which preserve verbatim cross-repo authorship.

Suppression:
- `# noqa: persona-names` inline → skip that line.
- `.github/.persona-names-allowlist` → file-based allowlist (one
  `filepath:line_number` per line, `#` comments allowed).
"""

import pathlib
import re
import subprocess
import sys

PERSONA_NAMES = ["Patrik", "Sid", "Camelia", "Palí", "Pali", "Fru", "Zolí", "Zoli", "YK"]
PERSONA_RE = re.compile(r"\b(" + "|".join(re.escape(n) for n in PERSONA_NAMES) + r")\b")

NOQA_RE = re.compile(r"#\s*noqa:\s*persona-names", re.IGNORECASE)

EXTENSIONS = {".md", ".sh", ".py"}

EXCLUDED_PREFIXES = (
    "archive/",
    "tasks/",
    "experiments/",
    "evals/",
    "docs/plans/",
    "docs/research/",
    "docs/decisions/",
    "docs/specs/",
    ".github/scripts/check-persona-names.py",  # this file itself names the personae
    "plugins/coordinator/bin/depersonalize-for-publish.sh",  # substitution map legitimately holds persona keys
)

ALLOWLIST_PATH = pathlib.Path(".github/.persona-names-allowlist")
SELF = pathlib.Path(__file__).resolve()


def load_allowlist() -> set[str]:
    if not ALLOWLIST_PATH.exists():
        return set()
    entries = set()
    for line in ALLOWLIST_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            entries.add(stripped)
    return entries


def in_scope(path: pathlib.Path) -> bool:
    if path.suffix not in EXTENSIONS:
        return False
    rel = path.as_posix()
    return not any(rel.startswith(p) for p in EXCLUDED_PREFIXES)


def get_tracked_files() -> list[pathlib.Path]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached"],
            capture_output=True, text=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"error: cannot list tracked files: {e}", file=sys.stderr)
        sys.exit(1)
    return [pathlib.Path(f) for f in result.stdout.strip().splitlines() if f]


def main() -> int:
    tracked = get_tracked_files()
    allowlist = load_allowlist()
    errors: list[str] = []

    for fpath in tracked:
        if not in_scope(fpath) or not fpath.exists() or fpath.resolve() == SELF:
            continue
        try:
            text = fpath.read_text(encoding="utf-8", errors="ignore")
        except (OSError, UnicodeDecodeError):
            continue

        for line_num, line in enumerate(text.splitlines(), 1):
            if NOQA_RE.search(line):
                continue
            if f"{fpath.as_posix()}:{line_num}" in allowlist:
                continue
            match = PERSONA_RE.search(line)
            if match:
                excerpt = line.strip()
                if len(excerpt) > 120:
                    excerpt = excerpt[:117] + "..."
                errors.append(
                    f"{fpath.as_posix()}:{line_num}: persona name '{match.group(1)}' — {excerpt}"
                )

    if errors:
        print("Persona-name check FAILED:")
        print("  Persona display names (Patrik, Sid, Camelia, Palí, Fru, Zolí, YK)")
        print("  must not appear in canonical-layer files. Use role labels instead")
        print("  (the Staff Engineer, the Game Dev Reviewer, etc. — see")
        print("  docs/customization.md for the full table).")
        print()
        for err in errors:
            print(f"  {err}")
        print()
        print("To suppress a legitimate occurrence (rare): append '# noqa: persona-names'")
        print("to the line, or add 'filepath:line_number' to .github/.persona-names-allowlist.")
        return 1

    print(f"Persona-name check passed ({len(tracked)} tracked files scanned).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
