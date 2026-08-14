"""coordinator/lib/percolate/targets.py — 4-tier publish-target resolution.

Native-Python port of `setup/publish.sh`'s `_load_targets` (lines ~252-424).
Composes the full set of resolved publish-target rows a `publish.sh`-style
driver iterates, in strict precedence order:

  1. PRIMARY — tracked portable topology (`setup/publish-targets.portable`,
     `PORTABLE_TARGETS_FILE` env override for test isolation).
  2. SUPPLEMENT — machine-local registry `publish.targets` key (per-machine
     addition; dedup by target name, an earlier tier's row always wins).
  3. LEGACY fallback — deprecated `setup/publish-targets.sh`, sourced only if
     tiers 1+2 together resolved nothing, gated by an owner+mode security
     check (it is executed as shell code by the bash original; this port
     never executes it — it is parsed as a `TARGETS=( … )` string-literal
     array, matching the divergence already documented in
     `ensure_required_targets.py`).
  4. NONE resolved anywhere — loud `TargetsError` with remediation text.

Every row (`repo:`, `publish-mirror:`, or legacy pass-through) is normalized
via `resolve_target.resolve_publish_row`, imported rather than reimplemented.

The subtle part of this port is the rc3-vs-rc2 asymmetry from
`resolve_publish_row` / `resolve_machine_local_bin`:
  - rc 3 (machine-local CLI absent) is a *bootstrap* signal, not corruption:
    step 1 abandons the portable topology and falls through to the legacy
    tier rather than aborting; step 3 (legacy) keeps the *raw* unresolved row
    on rc 3 rather than dropping it, since the legacy fallback is the last
    resort and an unresolved-but-present row beats no row.
  - rc 2 (malformed row / security-gate failure) is shared-data corruption,
    not a per-machine gap: it unconditionally aborts the ENTIRE resolution
    (every tier), never falls through.
  - rc 1 (registry key genuinely unset) sits between the two: skip-with-
    warning if a `target_filter` is active and names a different target
    (the unresolvable row is irrelevant to the requested publish), else
    abort loud (the key is required for the request at hand).

Return contract: `load_targets` returns the resolved rows (list[str]) on
success, or raises `TargetsError` — `.code` 1 mirrors the bash original's
`exit 1` (fail-loud abort, whole-process in bash; whole-call here) and `.code`
2 mirrors its `return 2` (the legacy-file security gate, a distinct signal a
driver may want to handle differently than a plain abort).

Spec backlink: docs/plans/2026-06-22-portable-registry-resolved-publish-targets.md
Port: docs/plans/2026-07-21-percolate-python-port.md (chunk C-W1a).

Negative-spec: this module performs no top-level side effects, executes no
shell code (the legacy `TARGETS=( … )` array is parsed as string literals,
never sourced), and contains no driver/CLI wiring — importable library only.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import IO, List, Optional

from coordinator_core.win_portability import is_executable
from coordinator.lib.percolate.resolve_target import (
    ResolveError,
    resolve_machine_local_bin,
    resolve_publish_row,
)


class TargetsError(Exception):
    """Raised by `load_targets` for a non-zero bash `_load_targets` outcome.

    `code` 1 mirrors the bash original's `exit 1` fail-loud abort paths
    (malformed row, unresolvable required target, no targets found anywhere).
    `code` 2 mirrors its `return 2` — the legacy-file owner/mode security gate
    and the propagated `MACHINE_LOCAL_BIN` SECURITY validation failure.
    """

    def __init__(self, message: str, code: int):
        super().__init__(message)
        self.message = message
        self.code = code


def _paths_tried_desc(root: Path) -> str:
    """Human-readable rung list for machine-local-bin resolution diagnostics,
    independent of whether resolution actually succeeded."""
    rung2 = root / "bin" / "machine-local"
    rung3 = root / "coordinator" / "bin" / "machine-local"
    env_bin = os.environ.get("MACHINE_LOCAL_BIN")
    if env_bin:
        return f"MACHINE_LOCAL_BIN={env_bin}, {rung2}, {rung3}, machine-local on PATH"
    return f"MACHINE_LOCAL_BIN env var (unset), {rung2}, {rung3}, machine-local on PATH"


def _machine_local_has(machine_local_bin: str, key: str) -> bool:
    """`<machine_local_bin> has <key>` — direct shebang-honoring exec (the
    bash-wrap the original used breaks now that machine-local is a Python
    forwarder; see resolve_target._machine_local_get). True iff the key is
    present (exit 0)."""
    try:
        result = subprocess.run(
            [machine_local_bin, "has", key],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    return result.returncode == 0


def _machine_local_get_multi(machine_local_bin: str, key: str) -> str:
    """`<machine_local_bin> get <key>` — direct shebang-honoring exec (see
    _machine_local_has) — raw stdout, trailing newline stripped (matching
    bash `$(...)` command substitution). Empty string on any failure
    (mirrors the bash original invoking `get` only after `has` already
    confirmed the key's presence — a subsequent failure is not expected but
    must not raise)."""
    try:
        result = subprocess.run(
            [machine_local_bin, "get", key],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.rstrip("\n")


def _iter_portable_rows(path: Path) -> List[str]:
    """Read `publish-targets.portable`-shaped rows: trailing `\\r` stripped,
    blank lines and `#`-comment lines skipped."""
    rows: List[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        row = raw_line[:-1] if raw_line.endswith("\r") else raw_line
        stripped = row.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        rows.append(row)
    return rows


_TARGETS_ARRAY_ELEMENT_RE = re.compile(r'"((?:[^"\\]|\\.)*)"|\'([^\']*)\'')


def _extract_quoted(line: str) -> List[str]:
    found = []
    for match in _TARGETS_ARRAY_ELEMENT_RE.finditer(line):
        literal = match.group(1) if match.group(1) is not None else match.group(2)
        found.append(literal.replace('\\"', '"'))
    return found


def _parse_legacy_targets_array(text: str) -> List[str]:
    """Extract the literal string elements of a bash `TARGETS=( ... )` array
    without sourcing the file as shell code — same technique (and the same
    documented scope limit: plain pipe-delimited string literals only, no
    shell interpolation inside an entry) as
    `ensure_required_targets._parse_targets_array`.

    Expected file shape (what a user's own `setup/publish-targets.sh` looks
    like — `coordinator/templates/setup/publish-targets.example.sh`, the
    formerly-shipped copy-template, was deleted 2026-07-22 as inert
    documentation-by-example; this is now the canonical reference):

        TARGETS=(
          "coordinator-claude|mirror|/path/to/source/plugins/coordinator-claude|/path/to/coordinator-claude/plugins"
          "example-target|manifest|/path/to/source/plugins/example-plugin|/path/to/example-publish-repo|your-marketplace-slug"
        )

    Pipe-separated fields: name|mode|source|dest[|native_slugs]. See
    `setup/publish-targets.portable` for the portable `publish-mirror:<key>`
    source form this legacy shape coexists with.
    """
    lines = text.splitlines()
    in_targets = False
    elements: List[str] = []
    for line in lines:
        if not in_targets:
            if re.match(r"^TARGETS=\(", line):
                in_targets = True
                remainder = line[line.index("(") + 1 :]
                elements.extend(_extract_quoted(remainder))
            continue
        if re.match(r"^\s*\)\s*$", line):
            break
        elements.extend(_extract_quoted(line))
    return elements


def _legacy_file_security_gate(targets_file: Path, err: IO[str]) -> Optional[str]:
    """Owner + mode pre-source sanity check (secaudit MEDIUM, ported from the
    `[[ ! -O "$targets_file" ]]` / world-writable-mode check). Returns an
    error message string if the gate fails, else None.

    Windows divergence: `os.getuid` does not exist there and NTFS has no
    equivalent POSIX owner/mode-bits model, so this gate is a documented
    no-op on Windows (the bash original never ran there either — it is a
    bash script). POSIX behavior is unchanged."""
    getuid = getattr(os, "getuid", None)
    if getuid is None:
        return None
    st = targets_file.stat()
    if st.st_uid != getuid():
        return (
            f"[publish.sh] SECURITY: {targets_file} is not owned by the current "
            "user — refusing to source."
        )
    mode = stat.S_IMODE(st.st_mode)
    if mode & (stat.S_IWGRP | stat.S_IWOTH):
        return (
            f"[publish.sh] SECURITY: {targets_file} has group/world-writable "
            f"permissions (mode {oct(mode)[2:]}) — refusing to source."
        )
    return None


def _resolve_portable_file(
    setup_dir: Path, portable_targets_file: Optional[Path] = None
) -> Path:
    """Same portable-file resolution `load_targets` step 1 uses (explicit
    arg > `PORTABLE_TARGETS_FILE` env override > `setup_dir`-relative
    default) — factored out so a resolution-free reader can agree with the
    real loader on which file it is reading without duplicating the rule."""
    if portable_targets_file is not None:
        return portable_targets_file
    env_portable = os.environ.get("PORTABLE_TARGETS_FILE")
    if env_portable:
        return Path(env_portable)
    return setup_dir / "publish-targets.portable"


def raw_dest_sigil_by_name(
    setup_dir: Path, *, portable_targets_file: Optional[Path] = None
) -> "dict[str, str]":
    """Resolution-free scan of the tracked PRIMARY portable topology
    (`setup/publish-targets.portable`) mapping each row's `name` (field 0)
    to its literal, UNRESOLVED dest field (field 2) — e.g.
    `publish-mirror:claude_klabauter` or `repo:some-key`.

    Deliberately does not execute `resolve_publish_row`/machine-local: this
    exists ONLY to answer "which other rows share this row's destination",
    not to resolve a publishable path, so it never touches machine-local,
    never raises `ResolveError`/`TargetsError`, and is safe to call before
    any of the heavier `load_targets` preconditions are known to hold.

    Scope: PRIMARY (tier 1) rows only. A mirror composed entirely of
    machine-local-registry-supplement or legacy-`publish-targets.sh` rows
    (tiers 2/3) is not covered — the portable topology is the tracked,
    committed source of truth every row in the observed defect (the
    `claude-klabauter` mirror) lives in; ANC per `docs/plans/
    2026-06-22-portable-registry-resolved-publish-targets.md`, tiers 2/3
    are per-machine/deprecated overrides layered on top of it, not where a
    mirror's row set is expected to live. Returns `{}` if the portable file
    is absent (mirrors `load_targets` step 1's own `.is_file()` guard).
    """
    portable_file = _resolve_portable_file(setup_dir, portable_targets_file)
    result: "dict[str, str]" = {}
    if not portable_file.is_file():
        return result
    for raw_row in _iter_portable_rows(portable_file):
        fields = raw_row.split("|")
        if len(fields) < 3:
            continue
        result[fields[0]] = fields[2]
    return result


def load_targets(
    setup_dir: Path,
    *,
    target_filter: str = "",
    portable_targets_file: Optional[Path] = None,
    err: IO[str] = sys.stderr,
) -> List[str]:
    """Resolve the full 4-tier publish-target set. `setup_dir` is the
    `setup/`-shaped directory holding `publish-targets.sh` /
    `publish-targets.portable` (the bash original's `$SCRIPT_DIR`); the
    machine-local registry root is `setup_dir.parent` (its
    `dirname "$SCRIPT_DIR"`).

    `target_filter` accepts either a single target name (unchanged, prior
    behavior) or a COMMA-SEPARATED list of names (task brief "Deliverable
    1 — one invocation, all rows": lets a caller name every row of a
    logical target — e.g. `claude-klabauter,claude-klabauter-bin,...` — in
    one `load_targets` call instead of one process invocation per row).
    Whitespace around each name is stripped; an empty filter (`""`, the
    default) means unfiltered, exactly as before.

    Returns the resolved rows (list[str], `name|mode|ABSsource|ABSdest[...]`
    form) in first-tier-wins-on-name-collision order. Raises `TargetsError`
    (see class docstring for the `.code` 1/2 split) on any abort path.
    """
    target_filter_set = (
        frozenset(n.strip() for n in target_filter.split(",") if n.strip())
        if target_filter
        else frozenset()
    )
    root = setup_dir.parent
    targets_file = setup_dir / "publish-targets.sh"

    portable_file = _resolve_portable_file(setup_dir, portable_targets_file)

    mlb_tried_desc = _paths_tried_desc(root)
    try:
        machine_local_bin = resolve_machine_local_bin(root)
    except ResolveError as exc:
        # SECURITY validation failure (MACHINE_LOCAL_BIN env) already carries
        # its own message; propagate as the security-gate error class.
        raise TargetsError(exc.message, 2) from exc
    if machine_local_bin is None:
        # No rung resolved; keep the guessed path so the -x check below
        # fails closed, matching the bash original's fallback assignment.
        machine_local_bin = str(root / "bin" / "machine-local")

    targets: List[str] = []
    seen_names: dict = {}
    cli_absent_fallthrough = False

    def add_resolved(resolved_row: str, src: str) -> None:
        name = resolved_row.split("|", 1)[0]
        if name in seen_names:
            print(
                f"[publish.sh] target '{name}' from {src} shadowed by earlier "
                f"{seen_names[name]} — skipping.",
                file=err,
            )
            return
        seen_names[name] = src
        targets.append(resolved_row)

    def rc1_skip_or_abort(raw_row: str, src: str) -> None:
        name = raw_row.split("|", 1)[0]
        if target_filter_set and name not in target_filter_set:
            print(
                f"[publish.sh] target '{name}' unresolvable (unset registry key) "
                f"in {src} — skipping; not the filtered target '{target_filter}'.",
                file=err,
            )
            return
        print(
            f"[publish.sh] cannot resolve target '{name}' in {src} (unset "
            "registry key — see remediation above). Aborting.",
            file=err,
        )
        raise TargetsError(
            f"cannot resolve target '{name}' in {src} (unset registry key)", 1
        )

    # --- Step 1: tracked portable topology (PRIMARY) ---
    # meta_root=root threaded into every resolve_publish_row call: the resolver's
    # own _default_meta_root() walks up from resolve_target.py's file location,
    # which post-split lands on claude-klabauter's root — KNOWN-WRONG for the
    # percolation source tree (its plugins/ fallback and machine-local rungs
    # live under setup_dir.parent, the same root machine_local_bin above uses).
    if portable_file.is_file():
        for raw_row in _iter_portable_rows(portable_file):
            try:
                resolved = resolve_publish_row(raw_row, meta_root=root)
            except ResolveError as exc:
                if exc.code == 1:
                    rc1_skip_or_abort(raw_row, "publish-targets.portable")
                    continue
                if exc.code == 2:
                    print(
                        f"[publish.sh] malformed portable row in {portable_file}: "
                        f"{raw_row} — aborting.",
                        file=err,
                    )
                    raise TargetsError(
                        f"malformed portable row in {portable_file}: {raw_row}", 1
                    ) from exc
                if exc.code == 4:
                    # Transport failure — the CLI exists but could not be
                    # executed. Distinct from rc 1 ("ran fine, key unset"):
                    # abort loud with the REAL error, never the "unset
                    # registry key" framing above, which would send the
                    # operator to re-set a key that isn't the problem.
                    print(exc.message, file=err)
                    raise TargetsError(exc.message, 1) from exc
                # exc.code == 3: machine-local CLI absent — bootstrap window
                # owns this; abandon portable, fall through to legacy.
                print(
                    "[publish.sh] portable topology present but machine-local "
                    f"CLI unavailable (tried: {mlb_tried_desc}) — falling back "
                    "to publish-targets.sh",
                    file=err,
                )
                cli_absent_fallthrough = True
                targets = []
                seen_names = {}
                break
            else:
                add_resolved(resolved, "publish-targets.portable")

    # --- Step 2: machine-local registry publish.targets (per-machine supplement) ---
    if (
        not cli_absent_fallthrough
        and is_executable(machine_local_bin)
        and _machine_local_has(machine_local_bin, "publish.targets")
    ):
        raw = _machine_local_get_multi(machine_local_bin, "publish.targets")
        for row in raw.splitlines():
            if not row:
                continue
            try:
                resolved = resolve_publish_row(row, meta_root=root)
            except ResolveError as exc:
                if exc.code == 1:
                    rc1_skip_or_abort(row, "registry publish.targets")
                    continue
                if exc.code == 2:
                    print(
                        "[publish.sh] malformed registry publish.targets row: "
                        f"{row} — aborting.",
                        file=err,
                    )
                    raise TargetsError(
                        f"malformed registry publish.targets row: {row}", 1
                    ) from exc
                if exc.code == 4:
                    # Transport failure, not "unset" — abort loud with the
                    # real error (see Step 1's rc-4 handling above).
                    print(exc.message, file=err)
                    raise TargetsError(exc.message, 1) from exc
                # exc.code == 3: CLI was already confirmed -x above; rc3 here
                # is unexpected — ignore the row (matches bash `3) : ;;`).
                continue
            else:
                add_resolved(resolved, "registry publish.targets")

    if targets:
        return targets

    # --- Step 3: deprecated publish-targets.sh fallback ---
    if targets_file.is_file():
        print(
            "[publish.sh] DEPRECATED: publish-targets.sh — migrate to "
            "machine-local registry (publish.targets key) or the tracked "
            "setup/publish-targets.portable. See "
            "~/.claude/machine-local/README.md",
            file=err,
        )

        security_error = _legacy_file_security_gate(targets_file, err)
        if security_error is not None:
            print(security_error, file=err)
            raise TargetsError(security_error, 2)

        text = targets_file.read_text(encoding="utf-8")
        legacy_rows = _parse_legacy_targets_array(text)

        targets = []
        seen_names = {}
        for row in legacy_rows:
            if not row:
                continue
            try:
                resolved = resolve_publish_row(row, meta_root=root)
            except ResolveError as exc:
                if exc.code == 1:
                    rc1_skip_or_abort(row, "publish-targets.sh")
                    continue
                if exc.code == 2:
                    print(
                        f"[publish.sh] malformed row in publish-targets.sh: "
                        f"{row} — aborting.",
                        file=err,
                    )
                    raise TargetsError(
                        f"malformed row in publish-targets.sh: {row}", 1
                    ) from exc
                if exc.code == 4:
                    # Transport failure, not "unset" — abort loud with the
                    # real error (see Step 1's rc-4 handling above).
                    print(exc.message, file=err)
                    raise TargetsError(exc.message, 1) from exc
                # exc.code == 3: CLI absent — keep the row as-is (last resort;
                # unresolved beats absent).
                add_resolved(row, "publish-targets.sh (unresolved)")
            else:
                add_resolved(resolved, "publish-targets.sh")

        if targets:
            return targets

    # --- Step 4: neither source available ---
    message_lines = [
        "Error: no publish targets found.",
        "Either:",
        "  (a) Set publish.mirrors.<key>.path (for publish-mirror: rows) or "
        "repos.<key> (for legacy repo: rows)",
        "      and use the tracked setup/publish-targets.portable topology,",
        "      or add publish.targets to ~/.claude/machine-local/registry.toml.",
        "      See ~/.claude/machine-local/README.md for the key format.",
        "  (b) Hand-write setup/publish-targets.sh (legacy fallback) — a bash "
        "TARGETS=( ... ) array of pipe-separated",
        "      \"name|mode|source|dest[|native_slugs]\" rows; see the shape "
        "documented next to _parse_legacy_targets_array",
        "      in coordinator/lib/percolate/targets.py.",
        f"  Note: a missing machine-local CLI (tried: {mlb_tried_desc}) can "
        "also cause this —",
        "      not just an unset registry key. Verify machine-local resolves "
        "before assuming (a)/(b).",
    ]
    for line in message_lines:
        print(line, file=err)
    raise TargetsError("no publish targets found", 1)
