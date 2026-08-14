"""doctor-catalog-gen.py — SSOT metadata block generator for coordinator-doctor.md.

Purpose: read bin/doctor-probes.toml and emit a compact markdown metadata
table (id | cluster | weight | triage | severity_if_fail). The wiki keeps its
hand-authored prose catalog (Command/Pass/Fail columns — not in the manifest);
this generator adds a MACHINE-READABLE metadata block that is the single source
of truth for the structured fields the manifest carries.

Spec backlink: archive/specs/2026-05-27-doctor-shape-doe-alignment.md § Chunk 3.
Doctrine: VALIDATE-not-GENERATE — the --check mode IS the test; it exits non-zero
if the committed wiki block diverges from the current manifest.

Modes:
  (default)   print the generated block to stdout
  --write     replace the block in coordinator-doctor.md in place
  --check     exit 0 if committed block matches generation; exit 1 + diff if not

Environment:
  DOCTOR_PROBES_MANIFEST   override manifest path (default: sibling doctor-probes.toml)
  DOCTOR_WIKI_PATH         override wiki path (default: resolved via
                           coordinator_data_root.data_root("docs") / "wiki" /
                           "coordinator-doctor.md" — co-located if this repo ships
                           its own docs/, else DoE-resident via coordinator_registry.
                           doe_root(); see coordinator/bin/lib/coordinator_data_root.py)

Cross-repo write note: --write mode writes coordinator-doctor.md in place at the
resolved wiki path above. In the current split-repo layout that path resolves to
DoE-claude's coordinator/docs/wiki/coordinator-doctor.md (this repo's coordinator/docs/
does not exist), so --write is a cross-repo write into DoE's tree, same as it always
was pre-migration when this script's caller ran with a DoE-relative CWD. This module
does not change that write behavior or its governance — it only fixes path resolution
to still find the target after the executable-surface split.
"""

from __future__ import annotations

import os
import sys
import difflib
from pathlib import Path

# Defensive self-locate — mirrors the sys.path.insert convention every bin/
# entrypoint uses (see coordinator/bin/snippet-registry's own `_LIB_DIR`
# insertion) so this module resolves its `coordinator_data_root` sibling
# import regardless of caller cwd.
_LIB_DIR = Path(__file__).resolve().parent / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from coordinator_data_root import data_root  # noqa: E402

GENERATES = []  # --write targets coordinator-doctor.md at the resolved wiki path, which resolves to DoE-claude's coordinator/docs/wiki/ tree (this repo has no coordinator/docs/) — a cross-repo write, never into claude-klabauter's own tree (see module docstring "Cross-repo write note")

# ---------------------------------------------------------------------------
# Sentinel markers (must stay byte-identical across all write/check operations)
# ---------------------------------------------------------------------------

BEGIN_MARKER = "<!-- BEGIN generated-probe-metadata (from claude-klabauter coordinator/bin/doctor-probes.toml — regenerate via claude-klabauter coordinator/bin/doctor-catalog-gen.py; do not hand-edit) -->"
END_MARKER = "<!-- END generated-probe-metadata -->"


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def _manifest_path() -> Path:
    override = os.environ.get("DOCTOR_PROBES_MANIFEST")
    if override:
        return Path(override)
    return Path(__file__).parent / "doctor-probes.toml"


def _wiki_path() -> Path:
    override = os.environ.get("DOCTOR_WIKI_PATH")
    if override:
        return Path(override)
    return data_root("docs") / "wiki" / "coordinator-doctor.md"


# ---------------------------------------------------------------------------
# Manifest loading
# ---------------------------------------------------------------------------

def load_probes() -> list[dict]:
    """Load [[probe]] array from the manifest."""
    try:
        import tomllib  # type: ignore[import]
    except ImportError:
        print(
            "error: tomllib unavailable — requires Python >= 3.11",
            file=sys.stderr,
        )
        sys.exit(1)

    manifest = _manifest_path()
    try:
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"error: manifest not found at {manifest}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"error: manifest parse error — {exc}", file=sys.stderr)
        sys.exit(1)

    probes = data.get("probe", [])
    if not probes:
        print("error: manifest contains no [[probe]] entries", file=sys.stderr)
        sys.exit(1)
    return probes


# ---------------------------------------------------------------------------
# Block generation
# ---------------------------------------------------------------------------

def generate_block(probes: list[dict]) -> str:
    """Return the full generated block (markers + table) as a string."""
    lines: list[str] = []
    lines.append(BEGIN_MARKER)
    lines.append("")
    lines.append("| id | cluster | weight | triage | severity_if_fail |")
    lines.append("|---|---|---|---|---|")
    for p in probes:
        triage = "yes" if p.get("triage") else "no"
        lines.append(
            f"| **{p['id']}** | {p['cluster']} | {p['weight']} | {triage} | {p['severity_if_fail']} |"
        )
    lines.append("")
    lines.append(END_MARKER)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Wiki read / replace helpers
# ---------------------------------------------------------------------------

def read_wiki(wiki: Path) -> str:
    try:
        return wiki.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"error: wiki not found at {wiki}", file=sys.stderr)
        sys.exit(1)


def replace_block_in_wiki(wiki_text: str, new_block: str) -> str:
    """Replace the content between BEGIN/END markers with new_block.

    If markers are not present yet, appends the block at end of file.
    Exits 1 if duplicate markers are found (silently truncating on first
    occurrence would corrupt the wiki).
    """
    begin_count = wiki_text.count(BEGIN_MARKER)
    end_count = wiki_text.count(END_MARKER)
    if BEGIN_MARKER in wiki_text or END_MARKER in wiki_text:
        if begin_count != 1 or end_count != 1:
            print(
                f"error: expected exactly one BEGIN and one END marker, "
                f"found {begin_count} BEGIN and {end_count} END — "
                "manual repair required",
                file=sys.stderr,
            )
            sys.exit(1)
        before = wiki_text[: wiki_text.index(BEGIN_MARKER)]
        after = wiki_text[wiki_text.index(END_MARKER) + len(END_MARKER) :]
        return before + new_block + after
    else:
        # Markers absent: append to end of file with a blank line separator.
        sep = "\n" if wiki_text.endswith("\n") else "\n\n"
        return wiki_text + sep + new_block + "\n"


def extract_committed_block(wiki_text: str) -> str | None:
    """Return the block (including markers) currently in the wiki, or None."""
    if BEGIN_MARKER not in wiki_text or END_MARKER not in wiki_text:
        return None
    start = wiki_text.index(BEGIN_MARKER)
    end = wiki_text.index(END_MARKER) + len(END_MARKER)
    return wiki_text[start:end]


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------

def mode_print(probes: list[dict]) -> None:
    """Default: print generated block to stdout."""
    print(generate_block(probes))


def mode_write(probes: list[dict], wiki: Path) -> None:
    """--write: replace the block in the wiki in place."""
    wiki_text = read_wiki(wiki)
    new_block = generate_block(probes)
    updated = replace_block_in_wiki(wiki_text, new_block)
    wiki.write_text(updated, encoding="utf-8")
    print(f"[doctor-catalog-gen] block written to {wiki}", file=sys.stderr)


def mode_check(probes: list[dict], wiki: Path) -> None:
    """--check: exit 0 if committed block byte-matches generated; else exit 1 + diff."""
    wiki_text = read_wiki(wiki)
    committed = extract_committed_block(wiki_text)
    generated = generate_block(probes)

    if committed is None:
        print(
            f"[doctor-catalog-gen] FAIL: markers not found in {wiki} — "
            "run --write to insert the block",
            file=sys.stderr,
        )
        sys.exit(1)

    if committed == generated:
        print(f"[doctor-catalog-gen] OK: committed block matches manifest ({wiki})", file=sys.stderr)
        sys.exit(0)
    else:
        print(
            f"[doctor-catalog-gen] FAIL: committed block differs from manifest",
            file=sys.stderr,
        )
        diff_lines = list(
            difflib.unified_diff(
                committed.splitlines(keepends=True),
                generated.splitlines(keepends=True),
                fromfile="committed (wiki)",
                tofile="generated (manifest)",
            )
        )
        sys.stderr.write("".join(diff_lines))
        sys.exit(1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv[1:]

    wiki = _wiki_path()
    probes = load_probes()

    if len(argv) == 0:
        mode_print(probes)
    elif argv[0] == "--write":
        mode_write(probes, wiki)
    elif argv[0] == "--check":
        mode_check(probes, wiki)
    else:
        print(
            f"unknown argument: {argv[0]} (valid: --write, --check)",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
