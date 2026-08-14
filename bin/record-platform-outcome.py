"""record-platform-outcome — emit a platform-outcome record from a real ceremony run.

PURPOSE: the writer for the `platform-outcome` schema
(coordinator/schemas/platform-outcome.schema.json). A thin CLI: the caller supplies
`--surface`, `--command`, and `--exit-code`; this tool RESOLVES everything else itself
(platform, machine/hostname, surface_sha, invoking_repo, observed_at) and writes the
per-platform YAML record. One record = one ceremony/entry-point surface invoked on one
platform with a real result — see the schema's own top-level description for the full
staleness/sharding contract this record format backs.

WRITE-TARGET RESOLUTION (load-bearing — do not simplify to a cwd-relative write):
records land under the SURFACE-PROVIDING repo's `state/platform-outcomes/`, not under
the invoking process's cwd. `invoking_repo` (the repo id of the tree the ceremony
actually ran in) and `surface_sha` (the SHA of the repo PROVIDING the surface under
test) diverge exactly when a canary run on one machine exercises a surface resolved
from a different repo's clone via `--plugin-dir` (see schema field descriptions for
both). The surface-providing repo here is always the DoE/coordinator repo — this tool
lives in `coordinator/bin/`, so the surface it measures is always a DoE-owned surface —
resolved via `coordinator_registry.doe_root()` (env `DOE_ROOT` -> machine-local
registry `repos.doe_claude` -> raise), NOT via `.doe-root`-file-read or cwd. `doe_root()`
delegates to the same machine-local registry the `.doe-root` pointer file itself is
generated from (`gen-doe-root-pointer.py`) — reusing the existing, already-tested seam
is preferred over re-reading the pointer file directly. Per
`coordinator/docs/wiki/state-placement-law.md`, "state/ is repo-local"; a naive
cwd-relative write would land the record in the wrong repo whenever `invoking_repo !=`
the surface-providing repo.

Record path: <surface-providing-repo-root>/state/platform-outcomes/<platform>/<machine>/<surface>.yaml
(sharded one level deeper than platform alone — see schema description's "RECORD
LOCATION" note — so two machines on the same platform never contend on one file).

CROSS-PLATFORM (this tool MEASURES Windows — it MUST be Windows-clean; this is an
execution criterion for this file specifically, not only a review criterion):
  - No argv-vector launch of a .js/.sh/extensionless path without an interpreter
    prefix — this tool only ever shells out to `git`, which is GUI-subsystem
    (per project convention, exempt from the CREATE_NO_WINDOW console-popup
    guard), and the guard is applied anyway for defense-in-depth.
  - No expanduser("~")/HOME-only assumption anywhere in this file or its test —
    home resolution is entirely delegated to `coordinator_registry` (which
    itself uses `os.path.expanduser("~")`, honoring Windows `USERPROFILE`).
  - No bash trampoline: this is invoked directly via an interpreter prefix
    (`python3 coordinator/bin/record-platform-outcome ...` /
    `python coordinator/bin/record-platform-outcome ...`), matching the
    invocation convention already used by the sibling C4 tool
    (`untested-platform-advisory.py`, invoked the same way from
    `coordinator/commands/workday-start.md`). No `.cmd` shim is needed because
    the caller always supplies the interpreter itself, exactly as C4's caller
    does — this is a "match what other recent coordinator/bin/ Python entries
    do" file, not a PATH-executable CLI shape like `cross-repo-memo`.

MACHINE/HOSTNAME RESOLUTION SEAM: mirrors the precedence chain already landed at
`coordinator/bin/cross-repo-memo.py:_resolve_machine_slug` (env `COORDINATOR_MACHINE`
override -> machine-local registry `coordinator.machine_slug` -> live `hostname`,
first label only, never raises). That function is defined inside a sh/python
polyglot trampoline script (no `.py` extension, not import-safe as a shared
library — its own docstring calls this "a cheap Python-side replica, not a fork
of the canonical resolver" because it cannot import bash-side tooling either), so
this file replicates the same three-rung precedence rather than importing it,
consistent with the pattern already established there. No dedicated hostname/
machine helper exists in `coordinator/bin/lib` as an importable module at time of
writing (grepped: only `coordinator_registry._registry_machine_local_get`, the
generic machine-local-registry reader, which this function calls for its middle
rung — this IS the consumed seam, not a re-derivation).

Spec backlink: docs/plans/2026-07-20-tested-platforms-teeth-windows-honest.md § C2
"""
from __future__ import annotations

import argparse
import datetime
import os
import platform
import socket
import subprocess
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from coordinator_registry import doe_root, _DoeUnresolvable, _registry_machine_local_get  # noqa: E402
from cc_invoke import require_engine_on_path  # noqa: E402

# The engine root must be on sys.path before any `coordinator_core` import: this
# file is also published into the claude-klabauter mirror, where coordinator_core
# is NOT pip-installed, so a bare import resolves nothing and the CLI dies at
# import time. Same bootstrap as coordinator/bin/lib/workday_ceremony_lib.py
# (landed in d2d4ec545 for the identical failure on /workday-start Step 0).
require_engine_on_path(__file__)

from coordinator_core.win_portability import no_console_creationflags  # noqa: E402

# Canonical PlatformId vocabulary — agent-install-manifest.schema.json §PlatformId,
# platform-outcome.schema.json §platform. Mirrors the identical mapping in the C4
# sibling tool (untested-platform-advisory.py) — kept as a local copy rather than
# a shared import because neither file exports the constant as a public API today;
# if the PlatformId enum ever changes at its SSOT, update both copies together.
_PLATFORM_MAP = {
    "Darwin": "macos",
    "Linux": "linux",
    "Windows": "windows",
}



GENERATES = []  # writes state/platform-outcomes/<platform>/<machine>/<surface>.yaml under _surface_root() == coordinator_registry.doe_root() (the DoE-claude repo), never claude-klabauter's own tree — see module docstring "WRITE-TARGET RESOLUTION"


class RecordPlatformOutcomeError(RuntimeError):
    """Raised for any resolvable-but-failed precondition (bad git repo, unresolvable
    platform, unsafe surface name). Caught once in main() and reported to stderr with
    a non-zero exit — never a raw traceback for an operator-facing CLI."""


def _running_platform_id() -> str:
    """Map the running OS to the PlatformId vocabulary (macos|linux|windows).

    Raises RecordPlatformOutcomeError for an unrecognized platform (e.g. an exotic
    BSD host) — unlike the advisory-only C4 sibling, this tool's job IS to attest a
    platform; silently degrading here would emit a schema-invalid record with no
    valid enum value.
    """
    system = platform.system()
    resolved = _PLATFORM_MAP.get(system)
    if resolved is None:
        raise RecordPlatformOutcomeError(
            f"unrecognized platform {system!r} — not in the PlatformId enum "
            f"(macos|linux|windows); cannot emit a schema-valid record."
        )
    return resolved


def _resolve_machine() -> str:
    """Resolve the ceremony machine's identity string.

    Three-rung precedence, mirroring `cross-repo-memo:_resolve_machine_slug`:
      1. `COORDINATOR_MACHINE` env override (test/operator escape hatch).
      2. machine-local registry key `coordinator.machine_slug` (install-time seed,
         self-healed by `/workday-start` Step 0 — see
         `coordinator/bin/workday-start-step0.py`).
      3. live `socket.gethostname()`, first label only (drops any domain suffix).

    Never raises — an OSError from the hostname probe falls through to
    "unknown-machine", matching the sibling resolver's degrade-gracefully posture.
    Unlike `_resolve_machine_slug`, no "unknown-machine" test asserts this specific
    fallback string as load-bearing; it exists purely so a live hostname probe
    failure cannot crash record emission.
    """
    override = os.environ.get("COORDINATOR_MACHINE", "").strip()
    if override:
        return override
    registry_slug = _registry_machine_local_get("coordinator.machine_slug")
    if registry_slug:
        return registry_slug
    try:
        host = socket.gethostname().strip()
        if host:
            return host.split(".")[0]
    except OSError:
        pass
    return "unknown-machine"


def _surface_root() -> str:
    """Resolve the surface-providing repo root (always the DoE/coordinator repo —
    this tool lives under `coordinator/bin/`, so the surface it measures is always
    DoE-owned). Delegates entirely to `coordinator_registry.doe_root()`; raises
    `_DoeUnresolvable` when neither `DOE_ROOT` nor the machine-local registry
    resolve it — callers must catch and report, not silently default to cwd."""
    return doe_root()


def _git_rev_parse(root: str, *args: str) -> str:
    """Run `git -C <root> rev-parse <args>` and return stripped stdout.

    Raises RecordPlatformOutcomeError on any non-zero exit or launch failure —
    a git-identity failure means the emitted record cannot carry a trustworthy
    surface_sha/invoking_repo, so this tool must not degrade to a placeholder.
    """
    cmd = ["git", "-C", root, "rev-parse", *args]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, **no_console_creationflags(),
        )
    except OSError as exc:
        raise RecordPlatformOutcomeError(f"git launch failed for {cmd!r}: {exc}") from exc
    if result.returncode != 0:
        raise RecordPlatformOutcomeError(
            f"git rev-parse failed (exit {result.returncode}) for {root!r}: "
            f"{result.stderr.strip()}"
        )
    return result.stdout.strip()


def _surface_sha(surface_root: str) -> str:
    """SHA of the surface-providing repo at HEAD (schema field `surface_sha`)."""
    return _git_rev_parse(surface_root, "HEAD")


def _invoking_repo_id() -> str:
    """Repo id (basename of git root) of the tree the ceremony actually ran in —
    resolved from the invoking process's cwd, independent of the surface root.

    Falls back to the basename of cwd itself when cwd is not inside a git repo
    (e.g. a scratch/ceremony sandbox) rather than raising — `invoking_repo` is a
    free descriptive string per the schema, not a validated identity.
    """
    cwd = os.getcwd()
    try:
        top = _git_rev_parse(cwd, "--show-toplevel")
    except RecordPlatformOutcomeError:
        top = cwd
    return os.path.basename(os.path.normpath(top))


def _now_observed_at() -> str:
    """Current UTC timestamp, ISO-8601, `Z`-suffixed (matches the schema fixture's
    `observed_at` convention exactly — `datetime.isoformat()`'s default `+00:00`
    offset form is schema-valid too, but `Z` is what the C1 fixture already uses)."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _yaml_str(value: str) -> str:
    """Emit a YAML scalar string: bare when safe, double-quoted (with `\\`/`"`
    escaped) when the value contains YAML-significant characters. Mirrors the
    identical heuristic in `coordinator/bin/migrate-central-improvement-queue.py:_yaml_str`
    — the established house pattern for hand-emitted flat YAML records (this repo
    avoids a PyYAML dependency for simple single-record writes)."""
    needs_quoting = (
        value.startswith(("- ", "| ", "> ", "!", "&", "*", "{", "[", "\"", "'", "`"))
        or ": " in value
        or value.endswith(":")
        or "\n" in value
        or value.startswith(" ")
        or value.endswith(" ")
    )
    if needs_quoting:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _yaml_quote_always(value: str) -> str:
    """Always double-quote a YAML scalar string, escaping `\\`/`"`. Used for
    `command` and `observed_at` — both free-form/argv-shaped or punctuation-heavy
    values that the C1 schema fixture (`coordinator/schemas/fixtures/platform-outcome/valid.yaml`)
    always quotes regardless of whether `_yaml_str`'s conditional heuristic would
    require it; matching that convention byte-for-byte keeps hand-inspection of
    records consistent across the fixture and every real emitted record."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _validate_surface(surface: str) -> None:
    """Reject a surface value that could escape the platform-outcomes tree (path
    separators or `..` segments) — the surface name becomes a filename component
    (`<surface>.yaml`), never a path, so traversal characters are always invalid
    input rather than a legitimate surface id."""
    if not surface or "/" in surface or "\\" in surface or ".." in surface:
        raise RecordPlatformOutcomeError(
            f"invalid --surface {surface!r}: must be a bare filename-safe id "
            f"(no path separators, no '..')."
        )


def record_path(surface_root: str, platform_id: str, machine: str, surface: str) -> str:
    """Return the full on-disk path for a platform-outcome record, per the schema's
    RECORD LOCATION convention: state/platform-outcomes/<platform>/<machine>/<surface>.yaml"""
    return os.path.join(
        surface_root, "state", "platform-outcomes", platform_id, machine, f"{surface}.yaml"
    )


def build_record(
    *,
    platform_id: str,
    surface: str,
    command: str,
    exit_code: int,
    observed_at: str,
    machine: str,
    surface_sha: str,
    invoking_repo: str,
) -> dict:
    """Assemble the record dict in schema field order (required-field set matches
    platform-outcome.schema.json exactly — see that file's `required` array)."""
    return {
        "platform": platform_id,
        "surface": surface,
        "command": command,
        "outcome": "pass" if exit_code == 0 else "fail",
        "exit_code": exit_code,
        "observed_at": observed_at,
        "machine": machine,
        "surface_sha": surface_sha,
        "invoking_repo": invoking_repo,
    }


def write_record(path: str, record: dict) -> None:
    """Write a single platform-outcome record to `path` as flat YAML (no `---`
    frontmatter delimiters — this is a standalone record file, not a doc with a
    body). Field order matches `build_record()`/the schema's `required` array."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = [
        f"platform: {record['platform']}",
        f"surface: {_yaml_str(record['surface'])}",
        f"command: {_yaml_quote_always(record['command'])}",
        f"outcome: {record['outcome']}",
        f"exit_code: {record['exit_code']}",
        f"observed_at: {_yaml_quote_always(record['observed_at'])}",
        f"machine: {_yaml_str(record['machine'])}",
        f"surface_sha: {record['surface_sha']}",
        f"invoking_repo: {_yaml_str(record['invoking_repo'])}",
        "",
    ]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def parse_args(argv: "list[str] | None" = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="record-platform-outcome",
        description=(
            "Emit a platform-outcome record from a real ceremony run. Resolves "
            "platform, machine, surface_sha, invoking_repo, and observed_at "
            "itself; the caller supplies only what it directly knows."
        ),
    )
    parser.add_argument(
        "--surface", required=True,
        help="The entry point or op id invoked (schema field `surface`).",
    )
    parser.add_argument(
        "--command", required=True,
        help="The argv actually run, as invoked (schema field `command`).",
    )
    parser.add_argument(
        "--exit-code", required=True, type=int,
        help="Process exit code observed for --command (schema field `exit_code`); "
             "0 -> outcome=pass, non-zero -> outcome=fail.",
    )
    return parser.parse_args(argv)


def main(argv: "list[str] | None" = None) -> int:
    args = parse_args(argv)
    try:
        _validate_surface(args.surface)
        platform_id = _running_platform_id()
        surface_root = _surface_root()
        surface_sha = _surface_sha(surface_root)
        invoking_repo = _invoking_repo_id()
        machine = _resolve_machine()
        observed_at = _now_observed_at()
    except _DoeUnresolvable as exc:
        print(
            f"record-platform-outcome: error: cannot resolve surface-providing "
            f"repo root (DOE_ROOT / machine-local repos.doe_claude): {exc}",
            file=sys.stderr,
        )
        return 1
    except RecordPlatformOutcomeError as exc:
        print(f"record-platform-outcome: error: {exc}", file=sys.stderr)
        return 1

    record = build_record(
        platform_id=platform_id,
        surface=args.surface,
        command=args.command,
        exit_code=args.exit_code,
        observed_at=observed_at,
        machine=machine,
        surface_sha=surface_sha,
        invoking_repo=invoking_repo,
    )
    out_path = record_path(surface_root, platform_id, machine, args.surface)
    write_record(out_path, record)
    print(out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
