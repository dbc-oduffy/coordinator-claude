#!/usr/bin/env python3
"""Block persona display names from creeping into the canonical layer.

The publish repo ships with role-based labels (`the Staff Engineer`, `the Game
Dev Reviewer`, etc.). Persona names live in the meta-repo where they're
authored, but must NOT appear in tracked canonical-layer files here.
Percolation from the meta-repo can accidentally re-introduce them; this check
is the regression net.

This file itself must never carry the roster in plaintext -- it ships into
the public mirror. Instead it matches salted SHA-256 digests of each
lowercased, NFC-normalized persona-name token against digests of candidate
tokens found in scanned files. This is obfuscation of a published wordlist,
not a security boundary: SALT is a fixed, in-repo constant chosen only to
keep the digests unrecognizable at a glance, not to resist a deliberate
dictionary attack. Anyone with this file can brute-force short names trivially.

Scope:
- Tracked `*.md`, `*.sh`, `*.py` files.
- Excludes historical / scratch dirs: archive/, tasks/, experiments/, evals/,
  and the research-archive subdirs of docs/ (plans/, research/, decisions/,
  specs/) which preserve verbatim cross-repo authorship.

Suppression:
- `# noqa: persona-names` inline -> skip that line.
- `.github/.persona-names-allowlist` -> file-based allowlist (one
  `filepath:line_number` per line, `#` comments allowed).

Regenerating ROSTER_DIGESTS:
- The plaintext roster is NOT stored in this file or anywhere in the public
  mirror; it lives only in the private meta-repo's depersonalize table
  (setup/percolate-hooks/percolate-store.yaml).
- To add or change an entry, compute its digest without ever writing the
  plaintext name into this file: run, from the private meta-repo,
  `python3 check-persona-names.py --hash "<Name>"` for each roster name and
  paste the printed digest into ROSTER_DIGESTS below.
"""

import hashlib
import pathlib
import re
import subprocess
import sys
import unicodedata

SALT = b"coordinator-persona-guard-v1"

ROSTER_DIGESTS = frozenset(
    [
        "686580a197d3b3ead183ae70d23bd8cb8d0ab1aa0ef08f7fc8d9e1d1f04a9b37",
        "ec3536b4bcae512aff1ddcd4195d999c4138683a7b2a85ec456569a8aceb381a",
        "0ffdedb7dbd0b439ebeeff856fa42631219c47f7b5b8a48734772b3adc13a094",
        "b391786942cd3c79627c33288e70293ac5ccf3e062cadc15bc4954c1d42ab062",
        "08aaf9e5b6c9869c8d9a849bf69c8659c7da089e92364122c462a3be21392616",
        "8fd4433b833d9d57e41783ad40e6e924e4ef17f0084fcf465397e0a4104918a4",
        "d7c23c6f87abe03a30058d59abb0e467eb16035740488324f9cb80d85176371f",
        "2cacfe148c1d1938571a0b38b5a6cef7ab56810cbd5882cbfe2d2ea596395bc0",
        "b184037e644ced94278ea760b30b7c3faa9936401ab8dad6c6de4c539deb0f3c",
    ]
)

TOKEN_RE = re.compile(r"\w+", re.UNICODE)

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
    ".github/scripts/check-persona-names.py",  # this file itself carries the digest table
    # Review: code-reviewer — the depersonalize-for-publish.sh entry that lived here
    # named a script retired in favour of percolate-store.yaml's config-driven
    # depersonalize hook; it does not exist in current source. Removed as stale.
)

ALLOWLIST_PATH = pathlib.Path(".github/.persona-names-allowlist")
SELF = pathlib.Path(__file__).resolve()


def token_digest(token: str) -> str:
    normalized = unicodedata.normalize("NFC", token).lower()
    return hashlib.sha256(SALT + normalized.encode("utf-8")).hexdigest()


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


def find_match(line: str) -> str | None:
    for token in TOKEN_RE.finditer(line):
        digest = token_digest(token.group(0))
        if digest in ROSTER_DIGESTS:
            return digest
    return None


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--hash":
        print(token_digest(sys.argv[2]))
        return 0

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
            digest = find_match(line)
            if digest:
                excerpt = line.strip()
                if len(excerpt) > 120:
                    excerpt = excerpt[:117] + "..."
                errors.append(
                    f"{fpath.as_posix()}:{line_num}: persona name (digest {digest[:12]}...) — {excerpt}"
                )

    if errors:
        print("Persona-name check FAILED:")
        print("  Persona display names must not appear in canonical-layer files.")
        print("  Use role labels instead (the Staff Engineer, the Game Dev")
        print("  Reviewer, etc. — see docs/customization.md for the full table).")
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
