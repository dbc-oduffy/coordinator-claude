"""Idempotent backfill of the coordinator-claude toplevel flat-mirror publish
targets (`coordinator-claude-toplevel-wiki`, `coordinator-claude-toplevel-install`).

Given that a `coordinator-claude|mirror` target is registered — either in the
machine-local registry (`publish.targets`, via `coordinator/bin/machine-local`)
or the legacy `setup/publish-targets.sh` — this module derives and appends the
two toplevel targets if they are absent, eliminating the per-machine hand-copy
failure mode: a fresh device with only the bare `coordinator-claude|mirror` row
gets the derived targets added automatically.

Precedence, checked in order, first match wins:
  1. Tracked portable topology (`setup/publish-targets.portable`) already
     encoding both derived target names — no-op, nothing to backfill.
  2. Machine-local registry (`publish.targets`) has a `coordinator-claude|mirror`
     row — derive and `array-append` any missing rows there.
  3. Legacy `setup/publish-targets.sh` — derive and rewrite the `TARGETS=( … )`
     array in place with any missing rows appended.

Ported from `setup/bin/ensure-required-targets.sh` (bash-kill campaign). Faithful
port with one documented divergence: the legacy branch no longer *sources*
`publish-targets.sh` as bash (this module is pure Python) — it parses the
`TARGETS=( … )` array as a sequence of quoted string literals. That is exact for
every row this project ever writes (plain pipe-delimited strings with no shell
interpolation); a legacy file that relies on bash variable expansion inside a
`TARGETS` entry will not round-trip correctly. No such file is known to exist.

Negative-spec: this module never hardcodes absolute paths; all derivation is
from the existing `coordinator-claude|mirror` row. If that row is absent, it
fails loud with a remediation message — no silent skip.

Spec backlink: docs/plans/2026-06-17-coordinator-install-seed-phase-and-manifest-alignment.md § C0
Spec backlink: docs/plans/2026-06-17-publish-targets-machine-local-migration.md § C2
Spec backlink: docs/plans/2026-06-22-portable-registry-resolved-publish-targets.md § C3
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import IO, NamedTuple

from coordinator_core.win_portability import is_executable
from coordinator.lib.percolate.publish_modes import MIRROR_WIRE_NAME
from coordinator.lib.percolate.resolve_target import (
    resolve_machine_local_bin as _resolve_machine_local_bin_canonical,
)

WIKI_TARGET_NAME = "coordinator-claude-toplevel-wiki"
INSTALL_TARGET_NAME = "coordinator-claude-toplevel-install"
MIRROR_TARGET_NAME = "coordinator-claude"
# Named-row lookup, not a mode-vocabulary consumer (Problem-table site 5,
# plan AC2) — reads the `mirror` wire name from C1's single source rather
# than holding a private copy. The equality test below stays exact.
MIRROR_TARGET_MODE = MIRROR_WIRE_NAME


class DerivedRows(NamedTuple):
    """The two toplevel flat-mirror rows derived from a `coordinator-claude|mirror` row."""

    wiki_row: str
    install_row: str


def derive_rows(mirror_source: str, mirror_dest: str) -> DerivedRows:
    """Shared row-derivation arithmetic — the one place the formula lives.

    Not reentrant in the bash original's sense is moot here (no globals); this
    is a pure function of its two arguments.
    """
    wiki_source = f"{mirror_source}/coordinator/docs/wiki"
    wiki_dest = f"{mirror_dest}/docs/wiki"
    install_source = f"{mirror_source}/coordinator/docs/install"
    install_dest = f"{mirror_dest}/docs/install"

    wiki_row = f"{WIKI_TARGET_NAME}|flat-mirror|{wiki_source}|{wiki_dest}"
    install_row = f"{INSTALL_TARGET_NAME}|flat-mirror|{install_source}|{install_dest}"
    return DerivedRows(wiki_row=wiki_row, install_row=install_row)


def _split_row(row: str) -> list[str]:
    """Split a pipe-delimited target row into its fields, unpadded."""
    return row.split("|")


def _row_name(row: str) -> str:
    fields = _split_row(row)
    return fields[0] if fields else ""


def _find_mirror_row(rows: list[str]) -> tuple[str, str] | None:
    """Locate the `coordinator-claude|mirror` row and return (source, dest), or None."""
    for row in rows:
        fields = _split_row(row)
        name = fields[0] if len(fields) > 0 else ""
        mode = fields[1] if len(fields) > 1 else ""
        if name == MIRROR_TARGET_NAME and mode == MIRROR_TARGET_MODE:
            source = fields[2] if len(fields) > 2 else ""
            dest = fields[3] if len(fields) > 3 else ""
            return source, dest
    return None


def _portable_topology_satisfied(portable_file: Path) -> bool:
    """True if the tracked portable topology already encodes both derived targets."""
    has_wiki = False
    has_install = False
    for raw_line in portable_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name = line.split("|", 1)[0]
        if name == WIKI_TARGET_NAME:
            has_wiki = True
        elif name == INSTALL_TARGET_NAME:
            has_install = True
    return has_wiki and has_install


def _run_machine_local(machine_local_bin: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Invoke `<machine_local_bin> <args>`. Raises OSError on an exec/transport
    failure (e.g. Windows WinError 193 from CreateProcess-ing an extensionless
    shebang script directly) — callers that can tolerate a failed lookup catch
    it themselves (see `_machine_local_has_publish_targets`); callers that
    cannot (the `_registry_branch` mutation calls) let it propagate rather
    than silently returning a fabricated non-zero CompletedProcess, which
    would misreport a transport failure as "machine-local ran and said no".

    Windows note: every row this module passes as an argument (the derived
    `coordinator-claude-toplevel-{wiki,install}` rows) is pipe-delimited. When
    `machine_local_bin` resolves to a `.cmd`/`.bat` shim (the Windows launcher
    shape — see `resolve_target.py`'s module docstring), `CreateProcess` cannot
    exec it directly and Python's own subprocess machinery silently retries via
    `cmd.exe /c <cmdline>` — at which point an UNQUOTED `|` in a plain
    `subprocess.run([...])` list argument (list2cmdline only quotes args
    containing whitespace, never `|`) is reinterpreted by cmd.exe as a real
    shell pipe, splitting one `array-append` call into several broken
    commands. Quoting every argument ourselves and passing a single command
    string sidesteps list2cmdline's whitespace-only quoting rule and keeps
    the pipe-delimited row literal through the cmd.exe retry. This has no
    effect on POSIX, where `machine_local_bin` is a direct shebang exec and
    `str` vs `list` args behave identically for arguments with no spaces."""
    if os.name == "nt":
        # Review: code-reviewer — the naive f'"{arg}"' wrapping below performs
        # NO escaping, so an argument containing a literal `"` breaks the
        # quoting outright, and an argument ending in `\` immediately before
        # the appended closing `"` is a classic Windows command-line escape
        # hazard. A general Windows command-line escaper is a known trap and
        # deliberately NOT attempted here — instead, fail loudly on the
        # unhandled case rather than risk silently corrupting a
        # pipe-delimited row (see the retry mechanism explained above).
        for arg in (str(machine_local_bin), *args):
            if '"' in arg or arg.endswith("\\"):
                raise ValueError(
                    "_run_machine_local: cannot safely quote argument for the "
                    f"cmd.exe retry path (contains a literal double-quote or "
                    f"ends in a backslash): {arg!r}"
                )
        cmdline = " ".join(f'"{arg}"' for arg in (str(machine_local_bin), *args))
        return subprocess.run(
            cmdline,
            capture_output=True,
            text=True,
            check=False,
        )
    return subprocess.run(
        [str(machine_local_bin), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _machine_local_has_publish_targets(machine_local_bin: Path) -> bool:
    if not (machine_local_bin.exists() and is_executable(machine_local_bin)):
        return False
    try:
        result = _run_machine_local(machine_local_bin, "has", "publish.targets")
    except OSError:
        return False
    return result.returncode == 0


def _registry_branch(machine_local_bin: Path, out: IO[str], err: IO[str]) -> int:
    """Derive/backfill via the machine-local registry (`publish.targets`)."""
    get_result = _run_machine_local(machine_local_bin, "get", "publish.targets")
    if get_result.returncode != 0:
        err.write(get_result.stderr)
        err.write(f"ERROR: failed to read publish.targets from {machine_local_bin}\n")
        return 1

    rows = [line for line in get_result.stdout.splitlines() if line]

    mirror = _find_mirror_row(rows)
    if mirror is None:
        err.write(
            "ERROR: coordinator-claude|mirror target not found in the machine-local registry (publish.targets).\n"
        )
        err.write("       This script derives the toplevel flat-mirror targets from that row.\n")
        err.write("       Register it first:\n")
        err.write(
            '       machine-local array-append publish.targets "coordinator-claude|mirror|<source>|<dest>"\n'
        )
        return 1

    mirror_source, mirror_dest = mirror
    if not mirror_source or not mirror_dest:
        err.write(
            "ERROR: coordinator-claude|mirror target not found in the machine-local registry (publish.targets).\n"
        )
        err.write("       This script derives the toplevel flat-mirror targets from that row.\n")
        err.write("       Register it first:\n")
        err.write(
            '       machine-local array-append publish.targets "coordinator-claude|mirror|<source>|<dest>"\n'
        )
        return 1

    wiki_row, install_row = derive_rows(mirror_source, mirror_dest)

    existing_names = {_row_name(row) for row in rows}
    needs_wiki = WIKI_TARGET_NAME not in existing_names
    needs_install = INSTALL_TARGET_NAME not in existing_names

    if not needs_wiki and not needs_install:
        out.write("ensure-required-targets: all derived targets already present in registry — no changes needed.\n")
        return 0

    out.write("ensure-required-targets: registry (publish.targets) updated.\n")

    if needs_wiki:
        append_result = _run_machine_local(machine_local_bin, "array-append", "publish.targets", wiki_row)
        if append_result.returncode != 0:
            err.write(append_result.stderr)
            return 1
        out.write(f"  + appended {WIKI_TARGET_NAME}    ({wiki_row})\n")
    if needs_install:
        append_result = _run_machine_local(machine_local_bin, "array-append", "publish.targets", install_row)
        if append_result.returncode != 0:
            err.write(append_result.stderr)
            return 1
        out.write(f"  + appended {INSTALL_TARGET_NAME} ({install_row})\n")

    return 0


_TARGETS_ARRAY_ELEMENT_RE = re.compile(r'"((?:[^"\\]|\\.)*)"|\'([^\']*)\'')


def _parse_targets_array(text: str) -> list[str]:
    """Extract the literal string elements of a bash `TARGETS=( ... )` array.

    Handles double- and single-quoted elements exactly as this project ever
    writes them (plain pipe-delimited strings, no shell interpolation). Lines
    outside `TARGETS=( … )` are ignored; the closing `)` is a standalone line
    containing only whitespace and `)`.
    """
    lines = text.splitlines()
    in_targets = False
    elements: list[str] = []
    for line in lines:
        if not in_targets:
            if re.match(r"^TARGETS=\(", line):
                in_targets = True
                # Content after "TARGETS=(" on the same line, if any.
                remainder = line[line.index("(") + 1 :]
                elements.extend(_extract_quoted(remainder))
            continue
        if re.match(r"^\s*\)\s*$", line):
            break
        elements.extend(_extract_quoted(line))
    return elements


def _extract_quoted(line: str) -> list[str]:
    found = []
    for match in _TARGETS_ARRAY_ELEMENT_RE.finditer(line):
        literal = match.group(1) if match.group(1) is not None else match.group(2)
        found.append(literal.replace('\\"', '"'))
    return found


def _find_targets_closing_paren_index(lines: list[str]) -> int | None:
    """Index of the standalone `)` line closing the first `TARGETS=(` block, or None."""
    in_targets = False
    for index, line in enumerate(lines):
        if not in_targets:
            if re.match(r"^TARGETS=\(", line):
                in_targets = True
            continue
        if re.match(r"^\s*\)\s*$", line):
            return index
    return None


def _name_present_outside_comments(text: str, name: str) -> bool:
    for line in text.splitlines():
        if re.match(r"^\s*#", line):
            continue
        if name in line:
            return True
    return False


def _legacy_branch(targets_file: Path, out: IO[str], err: IO[str]) -> int:
    """Derive/backfill via the legacy `setup/publish-targets.sh` file."""
    if not targets_file.is_file():
        err.write(f"ERROR: setup/publish-targets.sh not found at {targets_file}\n")
        err.write(
            "       Create setup/publish-targets.sh (a bash TARGETS=( ... ) array of\n"
        )
        err.write(
            "       pipe-separated rows — see coordinator/lib/percolate/targets.py's\n"
        )
        err.write(
            "       _parse_legacy_targets_array docstring for the expected shape) and\n"
        )
        err.write("       register the coordinator-claude|mirror target before running this script.\n")
        return 1

    text = targets_file.read_text(encoding="utf-8")
    rows = _parse_targets_array(text)

    if not rows:
        err.write(f"ERROR: TARGETS array is empty in {targets_file}\n")
        return 1

    mirror = _find_mirror_row(rows)
    if mirror is None or not mirror[0] or not mirror[1]:
        err.write(f"ERROR: coordinator-claude|mirror target not found in {targets_file}\n")
        err.write("       This script derives the toplevel flat-mirror targets from that row.\n")
        err.write("       Register coordinator-claude|mirror first, then re-run this script.\n")
        return 1

    mirror_source, mirror_dest = mirror
    wiki_row, install_row = derive_rows(mirror_source, mirror_dest)

    needs_wiki = not _name_present_outside_comments(text, WIKI_TARGET_NAME)
    needs_install = not _name_present_outside_comments(text, INSTALL_TARGET_NAME)

    if not needs_wiki and not needs_install:
        out.write("ensure-required-targets: all derived targets already present — no changes needed.\n")
        return 0

    append_lines: list[str] = []
    if needs_wiki:
        append_lines.append(
            f"  # {WIKI_TARGET_NAME}: auto-derived by ensure_required_targets.py from coordinator-claude|mirror row."
        )
        append_lines.append(f'  "{wiki_row}"')
    if needs_install:
        append_lines.append(
            f"  # {INSTALL_TARGET_NAME}: auto-derived by ensure_required_targets.py from coordinator-claude|mirror row."
        )
        append_lines.append(f'  "{install_row}"')
    append_block = "\n".join(append_lines)

    lines = text.splitlines()
    closing_index = _find_targets_closing_paren_index(lines)
    if closing_index is None:
        err.write(f"ERROR: could not locate the closing ')' of the TARGETS array in {targets_file}\n")
        err.write("       Inspect the file manually and append the following rows inside TARGETS=():\n")
        err.write(append_block + "\n")
        return 1

    new_lines = lines[:closing_index] + [append_block] + lines[closing_index:]
    new_text = "\n".join(new_lines)
    if text.endswith("\n"):
        new_text += "\n"

    fd, tmp_path = tempfile.mkstemp(dir=str(targets_file.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(new_text)
        os.replace(tmp_path, targets_file)
    except BaseException:
        Path(tmp_path).unlink(missing_ok=True)
        raise

    out.write(f"ensure-required-targets: updated {targets_file}\n")
    if needs_wiki:
        out.write(f"  + appended {WIKI_TARGET_NAME}    ({wiki_row})\n")
    if needs_install:
        out.write(f"  + appended {INSTALL_TARGET_NAME} ({install_row})\n")

    return 0


def _default_repo_root() -> Path:
    """Post-split default root: the percolation SOURCE tree (the one holding
    `setup/`), not this file's own repo root. The 2026-07-22 executable-surface
    migration moved this module into claude-klabauter while `setup/` stayed in
    the percolation source (DoE-claude / a `~/.claude` shared install), so the
    old `parents[3]` walk lands on a tree with no `setup/` at all. Rung order:
      1. Co-located `setup/` beside this module's repo root — the pre-split
         layout and any install shipping both halves together; costs nothing.
      2. `coordinator_core.percolate.runtime_root`'s explained resolver (env
         override → cwd git root → DoE-root pointer → shared install), whose
         root marker is `setup/publish-targets.portable`, exactly the data
         this module exists to reach — BUT pinned to never accept an answer
         that resolves to the DoE clone itself (docs/plans/2026-08-01-percolate-
         root-rung-ordering.md, chunk C4, "ENSURE_REQUIRED_TARGETS DECISION").
         This module is a machine-local backfill tool, not a doctrine editor:
         `_legacy_branch` rewrites `targets_file` (`setup/publish-targets.sh`)
         in place, and landing the DoE clone as this caller's answer would
         redirect that rewrite into a foreign git repo's tracked file — the
         exact write-into-a-foreign-clone hazard C6/C8 exist to stop,
         arriving through this caller instead of the installer.
         The pin compares the resolved PATH (normalized via `Path.resolve()`)
         against `doe_root_pointer.read_doe_root_pointer()`'s answer (also
         normalized) rather than checking the rung *label* — the label alone
         is an incomplete proxy: a cwd *inside* the DoE clone resolves via
         rung 2 (`"repo-local-git"`), not rung 3 (`"doe-root-pointer"`), and a
         label-only check would miss it. The `"doe-root-pointer"` rung label
         is still excluded too, belt-and-braces, but the path comparison is
         what carries the guarantee. Any such hit is treated exactly like a
         resolver miss here, falling through to step 3.
      3. Degrade to the co-located guess so the existing fail-loud
         remediation messages downstream fire unchanged.
    """
    co_located = Path(__file__).resolve().parents[3]
    if (co_located / "setup").is_dir():
        return co_located
    if str(co_located) not in sys.path:
        sys.path.insert(0, str(co_located))
    try:
        from coordinator_core.percolate.runtime_root import (
            coordinator_percolate_runtime_root_explained,
        )
        from coordinator_core.doe_root_pointer import read_doe_root_pointer

        resolved, rung = coordinator_percolate_runtime_root_explained()
    except (ImportError, RuntimeError):
        return co_located
    if rung == "doe-root-pointer":
        return co_located
    # Review: code-reviewer — pin on the resolved *path* being the DoE clone,
    # not the rung label; a cwd-inside-DoE-clone hit resolves via rung 2
    # ("repo-local-git"), which the label-only check never caught (Finding 1).
    resolved_path = Path(resolved).resolve()
    try:
        doe_root_raw = read_doe_root_pointer()
    except Exception:
        doe_root_raw = ""
    if doe_root_raw and resolved_path == Path(doe_root_raw).resolve():
        return co_located
    return Path(resolved)


def ensure_required_targets(
    *,
    repo_root: Path | None = None,
    targets_file: Path | None = None,
    portable_file: Path | None = None,
    machine_local_bin: Path | None = None,
    stdout: IO[str] | None = None,
    stderr: IO[str] | None = None,
) -> int:
    """Run the full ensure-required-targets flow. Returns a process exit code.

    Intended as the clean importable entrypoint for a future `publish.py`
    driver's preflight step — call this directly rather than shelling out to
    a script. All paths are resolvable either by argument (preferred for
    callers/tests) or by env var, matching the ported bash script's
    `PORTABLE_TARGETS_FILE` / `MACHINE_LOCAL_BIN` escape hatches.
    """
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr

    if repo_root is None:
        repo_root = _default_repo_root()
    setup_dir = repo_root / "setup"

    if targets_file is None:
        targets_file = setup_dir / "publish-targets.sh"

    if portable_file is None:
        env_portable = os.environ.get("PORTABLE_TARGETS_FILE")
        portable_file = Path(env_portable) if env_portable else setup_dir / "publish-targets.portable"

    if portable_file.is_file() and _portable_topology_satisfied(portable_file):
        out.write(
            "ensure-required-targets: derived targets present in tracked portable topology — no changes needed.\n"
        )
        return 0

    if machine_local_bin is None:
        env_machine_local = os.environ.get("MACHINE_LOCAL_BIN")
        if env_machine_local:
            machine_local_bin = Path(env_machine_local)
        else:
            # Delegate to the canonical resolver (resolve_target.py) rather
            # than hardcoding the extensionless `bin/machine-local` path
            # directly: on Windows that bare file cannot be exec'd at all
            # (WinError 193 — CreateProcess cannot run a shebang script), and
            # the canonical resolver already knows to prefer the delivered
            # `.cmd` sibling there. Falls back to the historical extensionless
            # guess only if the resolver finds nothing, so downstream
            # existence/X_OK checks still fail closed exactly as before.
            resolved = _resolve_machine_local_bin_canonical(repo_root)
            machine_local_bin = (
                Path(resolved) if resolved is not None else repo_root / "bin" / "machine-local"
            )

    if _machine_local_has_publish_targets(machine_local_bin):
        return _registry_branch(machine_local_bin, out, err)

    return _legacy_branch(targets_file, out, err)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint — no arguments; all configuration is via env vars, matching
    the ported bash script's invocation contract (`bash setup/bin/ensure-required-targets.sh`).
    """
    del argv
    return ensure_required_targets()


if __name__ == "__main__":
    sys.exit(main())
