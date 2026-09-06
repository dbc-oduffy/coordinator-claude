#!/usr/bin/env python3
# name-personas.py — Bind user-chosen names to role-distinct reviewer personae.
#
# The publish repo ships nameless: reviewers are referred to by articulated role
# labels ("the Staff Engineer", "the Game Dev Reviewer", etc.). Some installers
# find names easier to think with. This one-shot binding script substitutes the
# articulated role-label sentinels in installed-copy prose for user-supplied names.
#
# This is NOT a renaming utility — it is a naming utility, run once per role.
# To switch from one chosen name to another, re-clone the install or edit the
# files manually; this script is not idempotent across multiple runs.
#
# What gets touched:
#   - Articulated role-label sentinel (e.g., "the Staff Engineer") in prose,
#     in any *.md or *.sh file under plugins/, plus docs/customization.md.
#   - YAML frontmatter is skipped.
#
# What is NOT touched:
#   - Agent filenames (staff-eng.md, staff-game-dev.md, etc.) — infrastructure.
#   - YAML name: fields — infrastructure.
#   - subagent_type: dispatch keys (coordinator:staff-eng, etc.) — infrastructure.
#   - Unarticulated forms like "a staff engineer" in generic prose — collision-safe.
#
# Usage: name-personas.py [--dry-run] ROLE NAME [ROLE NAME ...]
# Example:
#   name-personas.py "the Staff Engineer" "Alex" "the Game Dev Reviewer" "Jordan"
#
# Exit codes (parity-critical, preserved from the retired bash oracle):
#   0 — dry-run report printed, or live substitutions applied and reported.
#   1 — usage/validation error: odd ROLE/NAME arg count, zero pairs provided,
#       or an unrecognized role label.
#
# DELIBERATELY SELF-CONTAINED — not a claude-klabauter direct-import trampoline (unlike
# most other bash-to-Python ports in this migration). This file percolates
# verbatim into the standalone OSS `coordinator-claude` publish repo
# (`setup/name-personas.py` there — see dist/publish-repo-setup/README.md),
# which ships to third-party plugin developers with NO `claude-klabauter`
# sibling clone, no `coordinator_core`, and no `.claude-klabauter-root` machine-local
# pointer. A `from coordinator_core.ops.name_personas import main` trampoline
# would resolve the live-working-tree engine root — COORDINATOR_ENGINE_ROOT —
# successfully on a Claude-Central/DoE developer machine but raise/exit-1 for
# every OSS consumer — silently defeating the
# "customize persona names" install step for every real end user. This script
# therefore ports the bash oracle's logic directly, with zero external
# imports beyond the stdlib (no `perl`, no `bash >= 4.0` required either —
# those were the retired oracle's own preflight guards for ITS external
# dependencies, which this port has none of). A behavior-equivalent copy also
# lives claude-klabauter-side at coordinator_core/ops/name_personas.py (co-located
# pytest suite) for engine-tree test coverage / potential future reuse from
# Claude-Central tooling — that module is NOT imported by this file and the
# two must be kept in sync by hand if either changes. Mirrors the precedent
# already established for dev-sync.py / coordinator_core.ops.dev_sync in the
# same dist/publish-repo-setup/ family — keep this file's Negative-spec notes
# aligned with that module's docstring if either drifts.
#
# Negative-spec (retired/never-had patterns — do NOT reintroduce):
#   - Frontmatter reconstruction always emits a bare LF for the "---"
#     delimiter lines regardless of the source file's original line-ending
#     convention (LF vs CRLF) — faithful reproduction of the retired oracle's
#     own perl reassembly ($_ = "---\n$fm---\n$body"), not a new bug.
#   - Live-run substitution creates a "<file>.bak" sibling containing the
#     pre-substitution content for every file it modifies — faithful
#     reproduction of the oracle's `perl -i.bak` in-place-edit convention.
#     Known carried-forward install-time artifact, not a defect introduced
#     by this port.
#   - Replacement-string handling uses a plain literal string substitution
#     (never mis-interprets a persona NAME containing a backslash or a
#     digit-after-$ sequence) rather than the oracle's raw Perl replacement-
#     side interpolation — behavior-identical for any normal human name (the
#     entire intended use case); this is a strict fix of accidental Perl
#     fragility on a pathological input, not a semantic port decision.
from __future__ import annotations

import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import List, Optional, Tuple

PROG = "name-personas.py"

KNOWN_ROLES: List[str] = [
    "the Staff Engineer",
    "the Director of Engineering",
    "the VP-Product Reviewer",
    "the Game Dev Reviewer",
    "the Front-End Reviewer",
    "the UX Reviewer",
    "the Data Science Reviewer",
]

_FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?\r?\n)---\r?\n(.*)", re.DOTALL)


def to_slug(name: str) -> str:
    """Lowercase + strip combining diacritics (NFD-decompose, drop category-M, NFC-recompose)."""
    decomposed = unicodedata.normalize("NFD", name)
    stripped = "".join(c for c in decomposed if not unicodedata.category(c).startswith("M"))
    return unicodedata.normalize("NFC", stripped).lower()


def _split_frontmatter(text: str) -> Tuple[Optional[str], str]:
    m = _FRONTMATTER_RE.match(text)
    if m:
        return m.group(1), m.group(2)
    return None, text


def count_prose_matches(old: str, text: str) -> int:
    """Count non-overlapping literal occurrences of `old` in prose (frontmatter skipped)."""
    _, body = _split_frontmatter(text)
    return body.count(old)


def replace_in_prose(old: str, new: str, text: str) -> str:
    """Literal-replace all occurrences of `old` with `new` in prose (frontmatter untouched)."""
    fm, body = _split_frontmatter(text)
    new_body = body.replace(old, new)
    if fm is not None:
        return f"---\n{fm}---\n{new_body}"
    return new_body


def _repo_root() -> Path:
    script_path = Path(os.path.abspath(__file__))
    return script_path.parent.parent


def _collect_files(repo_root: Path) -> List[Path]:
    plugins_dir = repo_root / "plugins"
    files: List[Path] = []
    if plugins_dir.is_dir():
        for pattern in ("*.md", "*.sh"):
            files.extend(plugins_dir.rglob(pattern))
    customization = repo_root / "docs" / "customization.md"
    if customization.is_file():
        files.append(customization)
    return sorted(set(files))


def main(argv: List[str]) -> int:  # noqa: C901 - mirrors the retired oracle's single-pass CLI shape
    args = list(argv)

    dry_run = False
    if args and args[0] == "--dry-run":
        dry_run = True
        args = args[1:]

    if len(args) % 2 != 0:
        print("Error: arguments after [--dry-run] must be ROLE NAME pairs.", file=sys.stderr)
        print(f"Usage: {PROG} [--dry-run] ROLE NAME [ROLE NAME ...]", file=sys.stderr)
        print(
            f'Example: {PROG} "the Staff Engineer" "Alex" "the Game Dev Reviewer" "Jordan"',
            file=sys.stderr,
        )
        return 1

    if len(args) == 0:
        print("Error: no ROLE NAME pairs provided.", file=sys.stderr)
        print("Known roles:", file=sys.stderr)
        for r in KNOWN_ROLES:
            print(f"  {r}", file=sys.stderr)
        return 1

    roles: List[str] = []
    names: List[str] = []
    new_slugs: List[str] = []
    for i in range(0, len(args), 2):
        role, name = args[i], args[i + 1]
        roles.append(role)
        names.append(name)
        new_slugs.append(to_slug(name))
        if role not in KNOWN_ROLES:
            print(f"Error: '{role}' is not a known role label.", file=sys.stderr)
            print("Use one of:", file=sys.stderr)
            for r in KNOWN_ROLES:
                print(f"  {r}", file=sys.stderr)
            return 1

    sub_olds: List[str] = []
    sub_news: List[str] = []
    for role, name in zip(roles, names):
        sub_olds.append(role)
        sub_news.append(name)
        if role[:4] == "the ":
            sub_olds.append(f"The {role[4:]}")
            sub_news.append(name)

    print("Naming plan:")
    for role, name, slug in zip(roles, names, new_slugs):
        print(f"  {role} → {name} (slug: {slug})")
    print(
        "  (sentence-initial capitalization handled automatically: "
        "'The Staff Engineer' as well as 'the Staff Engineer')"
    )
    print("")

    repo_root = _repo_root()
    files = _collect_files(repo_root)
    file_texts = {f: f.read_text(encoding="utf-8", errors="surrogateescape") for f in files}

    for role in roles:
        if role[:4] != "the ":
            continue
        unarticulated = role[4:]
        pattern = re.compile(r"\b" + re.escape(unarticulated) + r"\b")
        found_files = []
        for f in files:
            _, body = _split_frontmatter(file_texts[f])
            if pattern.search(body):
                found_files.append(f)
        if found_files:
            print(
                f"Note: '{unarticulated}' (unarticulated form of '{role}') "
                f"appears in {len(found_files)} file(s)."
            )
            print("  These will NOT be substituted — only the articulated form is replaced.")
            print(
                "  This is usually correct (generic prose like 'a staff engineer' "
                "should not be renamed)."
            )
            print("")

    if dry_run:
        print("Dry-run mode — no files will be modified.")
        print("")
        for old, new in zip(sub_olds, sub_news):
            total_replacements = 0
            total_files = 0
            for f in files:
                count = count_prose_matches(old, file_texts[f])
                if count > 0:
                    print(f"  [{old} → {new}] {f}: {count} match(es)")
                    total_replacements += count
                    total_files += 1
            print(f"  {old} → {new}: {total_replacements} replacement(s) across {total_files} file(s)")
            print("")
        return 0

    pair_replacements = {old: 0 for old in sub_olds}
    pair_files = {old: 0 for old in sub_olds}
    total_files_modified = 0

    for f in files:
        text = file_texts[f]
        file_modified = False
        for old, new in zip(sub_olds, sub_news):
            count = count_prose_matches(old, text)
            if count > 0:
                bak = f.parent / (f.name + ".bak")
                bak.write_text(text, encoding="utf-8", errors="surrogateescape")
                text = replace_in_prose(old, new, text)
                pair_replacements[old] += count
                pair_files[old] += 1
                file_modified = True
        if file_modified:
            f.write_text(text, encoding="utf-8", errors="surrogateescape")
            file_texts[f] = text
            total_files_modified += 1

    print("Persona names bound:")
    for old, new in zip(sub_olds, sub_news):
        print(f"  {old} → {new}: {pair_replacements[old]} substitutions across {pair_files[old]} files")
    print("")
    print(f"Total files modified: {total_files_modified}")
    print("")
    print("Infrastructure unchanged: agent filenames (staff-eng.md, etc.), YAML name: fields,")
    print("and subagent_type dispatch keys are role-based and not affected by naming.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
